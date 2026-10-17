"""Aether prune: remove files/dirs listed in a manifest, without fragile hunks.

Deletions carried as patch hunks break on any upstream refactor of the file.
This alternative does not: it removes whatever is there and loudly reports
what is missing (e.g. upstream moved the file -> update the list).

Manifest (prune-manifest.txt): one path per line, relative to the source tree.
`#` lines and blank lines are ignored. A trailing `/` means directory
(recursive).

Usage:
  python scripts/prune.py --src ..\\firefox-src [--manifest prune-manifest.txt]

Generate the manifest from the current patches:
  python scripts/prune.py --dump-series > prune-manifest.txt
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def iter_manifest(text):
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--dump-series", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.dump_series:
        paths = set()
        series = [l.strip() for l in
                  (ROOT / "patches" / "series").read_text(
                      encoding="utf-8").splitlines()
                  if l.strip() and not l.strip().startswith("#")]
        for p in series:
            data = (ROOT / "patches" / p).read_bytes().decode(
                "utf-8", errors="replace").split("\n")
            cur, is_del = None, False
            for l in data:
                m = re.match(r"diff --git a/(\S+) b/\S+$", l)
                if m:
                    cur, is_del = m.group(1), False
                    continue
                if l.startswith("deleted file mode"):
                    is_del = True
                if is_del and cur and l.startswith("+++ /dev/null"):
                    paths.add(cur)
        text = "\n".join(sorted(paths)) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8", newline="")
            print(f"[prune] manifest at {args.out} ({len(paths)} paths)")
        else:
            print(text, end="")
        return 0

    src = Path(args.src) if args.src else ROOT.parent / "firefox-src"
    mf = Path(args.manifest) if args.manifest \
        else ROOT / "prune-manifest.txt"
    missing, removed = [], 0
    for rel in iter_manifest(mf.read_text(encoding="utf-8")):
        target = src / rel.replace("/", "\\")
        if target.is_dir():
            shutil.rmtree(target)
            removed += 1
        elif target.is_file():
            target.unlink()
            removed += 1
        else:
            missing.append(rel)
    print(f"[prune] removed={removed} missing={len(missing)}")
    for m in missing:
        print(f"  MISSING (moved upstream?): {m}")
    return 0 if not missing else 2


if __name__ == "__main__":
    sys.exit(main())