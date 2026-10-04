"""Aether regen-patch: regenerate a patch's file section from a rebase repo.

Rebase flow (a disposable repo with one commit per applied patch):
  1. git apply <patch> (or --reject plus a manual fix until the attempt works)
  2. this script dumps git diff <base>..HEAD (or the worktree) limited to the
     patch's files, keeping the descriptive header.

Usage:
  python scripts/regen-patch.py --repo ..\\firefox-rb154 --base HEAD~1
      --patch patches/core/84-sync-wipe-leftovers.patch
      [--files a.txt b.txt...]   # default: the files of the old patch
      [--from-worktree]          # diff base..worktree instead of base..HEAD
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--patch", required=True)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--from-worktree", action="store_true")
    args = ap.parse_args()

    pf = Path(args.patch)
    old = pf.read_bytes().decode("utf-8", errors="replace").split("\n")
    try:
        i = next(n for n, l in enumerate(old)
                 if l.startswith("diff --git "))
    except StopIteration:
        print("the patch has no diff body")
        return 1
    header = "\n".join(old[:i])

    if args.files:
        files = args.files
    else:
        files = sorted({m.group(1) for m in
                        (re.match(r"diff --git a/(\S+) b/\S+$", l)
                         for l in old)
                        if m})
    print(f"[regen] {pf.name}: {len(files)} files from {args.base}")

    rev = f"{args.base}..HEAD" if not args.from_worktree else args.base
    cmd = ["git", "-c", "core.autocrlf=false", "diff", "--src-prefix=a/",
           "--dst-prefix=b/", rev, "--"] + files
    r = run(cmd, cwd=args.repo)
    body = r.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if not body.strip():
        print("[regen] empty diff (nothing to regenerate?)")
        return 1
    pf.write_bytes((header + body if header.endswith("\n")
                    else header + "\n" + body).encode("utf-8"))
    print(f"[regen] {pf.name} regenerated ({pf.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())