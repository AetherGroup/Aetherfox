"""Assemble the offline stub setup: the direct-install UI with payload inside.

Layout of the shipped exe (same convention as make-setup.py):

  AetherSetup-<version>.exe = sfx-7zSD.Win32.sfx + config + payload.7z

where payload.7z holds exactly two files:

  setup-stub.exe    the NSIS stub UI (direct install, no wizard page)
  aether-full.exe   the full installer, renamed so stub.nsi finds it

At runtime the SFX extracts both to a temp dir and runs setup-stub.exe. The
stub (patched: see core/32-stub-offline.patch) uses aether-full.exe from next
to itself instead of downloading, so no Mozilla network is touched and the
Mozilla cert check is skipped for our own payload. Without the bundled file
(e.g. a bare setup-stub.exe run by hand) the stub falls back to downloading.

Usage:
  python scripts/make-stub-offline.py --src C:\\oxg-156 --version 156.0.1
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 7zSD.sfx (Mozilla's fork) reads the config as UTF-8 with LF endings, same as
# branding/sfx-config.txt. RunProgram launches from the temp extraction dir.
CONFIG = (
    ';!@Install@!UTF-8!\n'
    'Title="Aetherfox Setup"\n'
    'RunProgram="setup-stub.exe"\n'
    ';!@InstallEnd@!\n'
)


def find_7z(src):
    cands = [
        shutil.which("7z"),
        r"C:\Program Files\7-Zip\7z.exe",
        str(src / "other-licenses" / "7zstub" / "src" / "bin" / "x64" / "7zr.exe"),
        str(src / "other-licenses" / "7zstub" / "src" / "bin" / "7zr.exe"),
    ]
    for c in cands:
        if c and Path(c).is_file():
            return c
    raise SystemExit("no 7z found (tried PATH, Program Files and the tree's 7zr.exe)")


def run(cmd, cwd=None):
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"failed: {cmd}\n{(r.stdout + r.stderr)[-800:]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT.parent / "firefox-src"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--stub", default=None,
                    help="setup-stub.exe (default: <src>/obj-aether/browser/installer/windows/instgen/)")
    ap.add_argument("--full", default=None,
                    help="full installer exe (default: <src>/obj-aether/dist/aether-<v>.en-US.win64.installer.exe)")
    ap.add_argument("--sfx", default=str(ROOT / "branding" / "sfx-7zSD.Win32.sfx"))
    ap.add_argument("--out", default=None,
                    help="default: <src>/obj-aether/dist/AetherSetup-<version>.exe")
    args = ap.parse_args()

    src = Path(args.src)
    obj = src / "obj-aether"
    version = args.version
    stub = Path(args.stub or str(obj / "browser/installer/windows/instgen/setup-stub.exe"))
    full = Path(args.full or str(
        obj / "dist" / f"aether-{version}.en-US.win64.installer.exe"))
    out = Path(args.out or str(obj / "dist" / f"AetherSetup-{version}.exe"))
    for p in (stub, full):
        if not p.is_file():
            raise SystemExit(f"missing input: {p}")
    sfx = Path(args.sfx)
    if not sfx.is_file():
        raise SystemExit(f"missing SFX stub: {sfx}")

    seven = find_7z(src)
    tmp = Path(tempfile.mkdtemp(prefix="aether-stub-"))
    try:
        shutil.copy2(stub, tmp / "setup-stub.exe")
        shutil.copy2(full, tmp / "aether-full.exe")
        run([seven, "a", "-t7z", "-mx=9", "-mmt=on", str(tmp / "payload.7z"),
             "setup-stub.exe", "aether-full.exe"], cwd=str(tmp))
        # The output is often locked by a installer still under test (a stuck
        # Cancel leaves the SFX parent alive). Retry briefly, then fail loud
        # telling the user to close installer windows.
        blob = sfx.read_bytes() + CONFIG.encode("utf-8") + \
            (tmp / "payload.7z").read_bytes()
        for attempt in range(6):
            try:
                with open(out, "wb") as f:
                    f.write(blob)
                break
            except PermissionError:
                if attempt == 5:
                    raise SystemExit(
                        f"cannot write {out}: locked. Close any running "
                        f"installer windows (setup-stub/AetherSetup) and retry.")
                import time
                time.sleep(10)
        print(f"[stub-offline] {out} ({out.stat().st_size} bytes)")
        # The 7z module finds the archive inside the SFX exe on its own; if it
        # lists both files, the assembly is structurally sound.
        r = run([seven, "l", str(out)])
        names = [l.split()[-1] for l in r.stdout.splitlines() if ".exe" in l]
        print(f"[stub-offline] inside: {names}")
        if not {"setup-stub.exe", "aether-full.exe"} <= set(names):
            raise SystemExit("assembled exe does not list both payload files")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("[stub-offline] OK")


if __name__ == "__main__":
    sys.exit(main())
