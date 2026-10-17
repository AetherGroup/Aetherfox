"""Assembles AetherSetup.exe: SFX stub (Aether icon) + config + .7z payload.

RETIRED: the SFX extracts to a temp dir and launches from there (no real
install and no uninstaller; XPCOM fails if the extraction is partial). The
supported setup is the Aether one (AetherSetup-<version>.exe, built by
scripts/build.py from the .NET setup in installer/ui/aether-setup). Kept
only as a manual portable extractor.

The stub already carries the icon (scripts/patch-sfx-stub.py). This concatenates:
  setup.exe = sfx-7zSD.Win32.sfx + sfx-config.txt + payload.7z
where payload.7z holds "Aetherfox/..." (renamed from aether/
in the portable zip) so it installs into %PROGRAMFILES% without nesting.

Uso:
  python scripts/make-setup.py --zip <firefox-src>/obj-aether/dist/aether-156.0.1.en-US.win64.zip
      --out <firefox-src>/obj-aether/dist/AetherSetup-156.0.1.exe
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEVENZZ = (Path.home() / ".mozbuild" / "7zz" / "7zz.exe",
           Path(r"C:\Program Files\7-Zip\7z.exe"))


def run(cmd):
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise SystemExit("falla: %s\n%s" % (cmd, (r.stdout + r.stderr)[-800:]))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stub",
                    default=str(ROOT / "branding" / "sfx-7zSD.Win32.sfx"))
    ap.add_argument("--config",
                    default=str(ROOT / "branding" / "sfx-config.txt"))
    ap.add_argument("--folder-name", default="Aetherfox")
    args = ap.parse_args()

    seven = next((p for p in SEVENZZ if p.is_file()), None)
    if not seven:
        raise SystemExit("missing 7z (SEVENZZ)")
    tmp = Path(tempfile.mkdtemp(prefix="aether-setup-"))
    try:
        with zipfile.ZipFile(args.zip) as z:
            z.extractall(tmp / "zip")
        roots = [p for p in (tmp / "zip").iterdir() if p.is_dir()]
        assert len(roots) == 1, roots
        payload = tmp / "payload"
        (payload).mkdir(exist_ok=True)
        shutil.move(str(tmp / "zip" / roots[0].name),
                    str(payload / args.folder_name))
        archive = tmp / "payload.7z"
        run([str(seven), "a", "-t7z", "-mx=9", "-mmt=on", str(archive),
             str(payload / "*")])
        with open(args.out, "wb") as out:
            out.write(Path(args.stub).read_bytes())
            out.write(Path(args.config).read_bytes())
            out.write(archive.read_bytes())
        print("[setup] OK", args.out,
              Path(args.out).stat().st_size, "bytes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
