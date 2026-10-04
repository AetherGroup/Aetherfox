"""Aether rebase: run the patch series against a clean tag.

Helium/ungoogled-chromium flow: the firefox-src tree is disposable, the changes
live in patches/series. This script clones the requested tag into a work
directory of its own (it never touches the dev checkout) and applies the series
in order, reporting per patch.

Usage:
  python scripts/rebase.py --tag FIREFOX_154_0_RELEASE [--workdir ..\\firefox-rebase-lab]
      [--series patches/series] [--keep] [--report rebase-report.md]

Exit status: 0 if everything applied; 1 if something failed (with a per-patch
breakdown). With --keep the workdir is preserved for inspection. Without it the
workdir is only removed when everything succeeded; on failure it is kept for
debugging either way.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIREFOX_REPO = "https://github.com/mozilla-firefox/firefox.git"


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--series", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    series_file = Path(args.series) if args.series else ROOT / "patches" / "series"
    series = [l.strip() for l in series_file.read_text(
        encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")]

    tmpdir = None
    if args.workdir:
        work = Path(args.workdir)
    else:
        tmpdir = tempfile.mkdtemp(prefix="aether-rebase-")
        work = Path(tmpdir)
    print(f"[rebase] tag={args.tag} work={work} patches={len(series)}")

    ok_all = True
    results = []
    try:
        if not (work / ".git").exists():
            print(f"[rebase] cloning {args.tag} (shallow)...")
            r = run(["git", "clone", "--depth", "1", "--branch", args.tag,
                     FIREFOX_REPO, str(work)])
            if r.returncode != 0:
                print("[rebase] ERROR cloning:")
                print((r.stdout + r.stderr)[-2000:])
                ok_all = False
                return 1
        else:
            print("[rebase] existing workdir, reusing it as is")

        for p in series:
            pf = ROOT / "patches" / p
            r = run(["git", "-c", "core.autocrlf=false", "apply",
                     "--whitespace=nowarn", str(pf)], cwd=str(work))
            if r.returncode == 0:
                print(f"  OK   {p}")
                results.append((p, True, ""))
            else:
                ok_all = False
                err = (r.stdout + r.stderr).strip().splitlines()
                err = "\n".join(err[:6])[:600]
                print(f"  FAIL {p}\n{err}")
                results.append((p, False, err))

        ok_n = sum(1 for _, ok, _ in results if ok)
        print(f"[rebase] {ok_n}/{len(results)} patches apply on {args.tag}")
    finally:
        if tmpdir and ok_all and not args.keep:
            shutil.rmtree(tmpdir, ignore_errors=True)
            print("[rebase] temporary workdir removed")
        elif not ok_all:
            print(f"[rebase] workdir kept for debugging: {work}")

    if args.report:
        lines = [f"# Rebase {args.tag}", "",
                 f"{ok_n}/{len(results)} patches OK", ""]
        for p, ok, err in results:
            lines.append(f"- [{'x' if ok else ' '}] {p}")
            if err:
                lines.append(f"  ```\n  {err}\n  ```")
        Path(args.report).write_text("\n".join(lines), encoding="utf-8")
        print(f"[rebase] report at {args.report}")

    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())