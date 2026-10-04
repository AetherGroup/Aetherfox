"""Aether local MAR: a port of tools/update-packaging/make_full_update.sh.

The original .sh fails on Windows: it passes ~8000 files per command line to
mar.exe and goes over CreateProcess's 32 KB limit. This script generates the
same updatev3.manifest and packs it with the `mardor` library (pip install mar,
from Mozilla RelEng) in-process, with no command line limit. Development only,
with --enable-unverified-updates (unsigned MARs).

SRCDIR must be the OMNI tree (obj-aether/dist/aether), not dist/bin (flat,
development only): that way the MAR matches the official ones (omni.ja, real
precomplete/removed-files) and cold starts stay fast.

Usage:
  python scripts/make-mar-local.py --srcdir <firefox-src>/obj-aether/dist/aether
      --out Documents/aether-mar/aether-153.0.complete.mar
      --version 153.0 --channel aether-release
"""
import argparse
import os
import re
import sys

MANIFEST_EXCLUDE = {"update.manifest", "updatev2.manifest", "updatev3.manifest"}
# NOTE: the root chrome.manifest does not exist in the omni staging (the packager
# omits it; upstream's removed-files.in asks for its removal there). It is not
# needed in omni (the registry lives inside omni.ja); in flat it is essential.
# That is why MARs ALWAYS come out of the omni tree (see --srcdir).
# Flat layout directories that do not exist in omni: removed explicitly so that
# flat->omni transitions are clean (rmrfdir on a missing dir succeeds, no risk).
FLAT_LEFTOVER_DIRS = ["chrome/", "modules/"]

# Mirror of check_for_add_if_not_update() in common.sh, with ONE development
# exception: distribution.ini goes as a normal `add` (not add-if-not) so that
# DistroVersion bumps (0.0.1, 0.0.2...) propagate through update. Upstream
# protects it; in development we want the new version to show up.
ADD_IF_NOT_RE = re.compile(
    r"(^|/)(channel-prefs\.js|update-settings\.ini|"
    r"ChannelPrefs\.framework|UpdateSettings\.framework)$"
)


def manifest_line(rel):
    norm = rel.replace(os.sep, "/")
    if ADD_IF_NOT_RE.search(norm):
        return 'add-if-not "{}" "{}"'.format(rel, rel)
    if "/distribution/extensions/" in rel.replace(os.sep, "/"):
        testdir = re.sub(r"(.*distribution/extensions/[^/]*)/.*", r"\1",
                         rel.replace(os.sep, "/"))
        return 'add-if "{}" "{}"'.format(testdir, rel)
    return 'add "{}"'.format(rel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srcdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--channel", required=True)
    args = ap.parse_args()

    srcdir = os.path.abspath(args.srcdir)
    if not os.path.isfile(os.path.join(srcdir, "precomplete")):
        raise SystemExit("no precomplete in srcdir (doc: touch precomplete after mach package)")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    files = []
    for root, _dirs, names in os.walk(srcdir):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, srcdir)
            if os.path.basename(rel) in MANIFEST_EXCLUDE:
                continue
            files.append(rel.replace(os.sep, "/"))
    files.sort(reverse=True)
    print("[mar-local] {} files".format(len(files)))

    lines = ['type "complete"'] + [manifest_line(f) for f in files]

    # removed-files from staging (same as append_remove_instructions in
    # common.sh): leftover rmvalues plus the upstream `remove "chrome.manifest"`
    # (correct in omni, where it must not exist).
    rf = os.path.join(srcdir, "removed-files")
    if os.path.isfile(rf):
        with open(rf, encoding="utf-8", errors="replace") as fh:
            entries = sorted(
                (l.strip() for l in fh.read().splitlines()
                 if l.strip() and not l.strip().startswith("#")),
                reverse=True)
        for f in entries:
            if f.endswith("/*"):
                lines.append('rmrfdir "{}"'.format(f[:-1]))
            elif f.endswith("/"):
                lines.append('rmdir "{}"'.format(f))
            else:
                lines.append('remove "{}"'.format(f))

    # Clean up flat leftovers when switching to omni (no-op if absent).
    for d in FLAT_LEFTOVER_DIRS:
        lines.append('rmrfdir "{}"'.format(d))

    manifest = "\r\n".join(lines) + "\r\n"
    with open(os.path.join(srcdir, "updatev3.manifest"), "w",
              encoding="utf-8", newline="") as fh:
        fh.write(manifest)
    print("[mar-local] updatev3.manifest ({} lines)".format(len(lines)))

    from mardor.writer import MarWriter
    ordered = ["updatev3.manifest"] + files
    old_cwd = os.getcwd()
    os.chdir(srcdir)
    try:
        with open(args.out, "w+b") as f:
            with MarWriter(f, productversion=args.version,
                           channel=args.channel) as m:
                for i, rel in enumerate(ordered):
                    if i % 1000 == 0:
                        print("[mar-local] {}/{}".format(i, len(ordered)))
                    m.add(rel, compress="xz", bcj="x86")
    finally:
        os.chdir(old_cwd)
    size = os.path.getsize(args.out)
    print("[mar-local] OK {} ({} bytes)".format(args.out, size))

    # Sidecar with the BuildID for aus-local.py (client vs MAR comparison).
    buildid = ""
    try:
        for line in open(os.path.join(srcdir, "application.ini"),
                         encoding="utf-8", errors="replace"):
            if line.startswith("BuildID="):
                buildid = line.strip().split("=", 1)[1]
    except OSError:
        pass
    with open(args.out + ".buildid", "w", encoding="utf-8") as fh:
        fh.write(buildid)
    print("[mar-local] buildid={}".format(buildid))


if __name__ == "__main__":
    sys.exit(main())