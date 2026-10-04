"""Assembles the Aether installer: AetherSetup.exe + the payload ZIP appended.

Format understood by Backend.LocatePayload: exe + zip + u64 LE footer
holding the offset where the zip starts inside the exe.

Uso:
  python scripts/make-installer.py
      --exe installer/ui/aether-setup/bin/Release/net9.0-windows/AetherSetup.exe
      --zip <firefox-src>/obj-aether/dist/aether-156.0.1.en-US.win64.zip
      --out <firefox-src>/obj-aether/dist/AetherSetup-156.0.1.exe
"""
import argparse
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    exe = Path(a.exe)
    payload = Path(a.zip)
    out = Path(a.out)
    for p in (exe, payload):
        if not p.is_file():
            print(f"missing: {p}")
            return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(exe, "rb") as f:
        stub = f.read()
    with open(payload, "rb") as f:
        data = f.read()
    if not data.startswith(b"PK"):
        print("warning: the payload does not look like a ZIP")
    with open(out, "wb") as f:
        f.write(stub)
        off = f.tell()
        f.write(data)
        f.write(struct.pack("<Q", off))
    print(f"[make-installer] {out} ({out.stat().st_size} bytes, "
          f"payload en {off})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
