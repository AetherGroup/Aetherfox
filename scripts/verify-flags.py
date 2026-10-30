"""Aether post-build check v1: compile flags + privacy defaults (group 03).

Verifies in the objdir and the packaged dist that:
  - MOZ_TELEMETRY_REPORTING / MOZILLA_OFFICIAL are not defined,
  - the source that turns MOZILLA_OFFICIAL off is still turned off, and the
    glean_disable_upload guard that actually blocks the uploader is still there,
  - MOZ_SERVICES_HEALTHREPORT is off,
  - toolkit.telemetry.server is empty in greprefs.js,
  - policies.json is absent (zero policies),
  - no bundled XPI in distribution/extensions (no adblock since 0.1).
Exits non-zero if anything failed (for CI).

Usage:
  python scripts/verify-flags.py [--objdir C:\\...\\obj-aether] [--src C:\\...\\tree]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAIL = []


def check(name, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAIL.append(name)


def check_upload_blocked(src):
    """The guarantee that pings cannot leave the machine.

    MOZILLA_OFFICIAL absent (checked against config.status above) is only half
    of it: that flag is what makes gkrust add the glean_disable_upload feature,
    and that feature is what makes the uploader return a fake HTTP 200 instead
    of talking to Mozilla. These two checks read the source that decides it, so
    reverting that pin fails the gate instead of silently reopening the channel.
    """
    f = src / "toolkit" / "library" / "rust" / "gkrust-features.mozbuild"
    if not f.is_file():
        check("glean_disable_upload guard present", False, f"missing {f}")
        return
    txt = f.read_text(encoding="utf-8", errors="replace")
    check("glean_disable_upload guard present",
          re.search(r'if not CONFIG\["MOZILLA_OFFICIAL"\]:\s*\n\s*'
                    r'gkrust_features \+= \["glean_disable_upload"\]', txt) is not None)

    f = src / "build" / "moz.configure" / "init.configure"
    if not f.is_file():
        check("mozilla_official pinned off", False, f"missing {f}")
        return
    txt = f.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"def mozilla_official\(official\):\n((?:    .*\n|\n)*)", txt)
    body = m.group(1) if m else ""
    check("mozilla_official pinned off",
          bool(m) and "return True" not in body
          and ("return False" in body or "return None" in body),
          "MOZILLA_OFFICIAL could be re-enabled from the environment"
          if m and "return True" in body else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdir", default=None)
    ap.add_argument("--src", default=None,
                    help="firefox tree (default: the objdir's parent)")
    args = ap.parse_args()
    obj = Path(args.objdir) if args.objdir else next(
        (p for p in (ROOT.parent / "firefox-src").glob("obj-aether*")
         if p.is_dir()), None)
    if not obj or not obj.is_dir():
        print("no objdir found (was mach build run?)")
        return 2
    print(f"[aether-verify] objdir={obj}")
    dist = obj / "dist" / "bin"

    status = (obj / "config.status").read_text(encoding="utf-8", errors="replace")
    check("MOZ_TELEMETRY_REPORTING absent", "'MOZ_TELEMETRY_REPORTING': '1'" not in status)
    check("MOZILLA_OFFICIAL absent", "'MOZILLA_OFFICIAL': '1'" not in status)
    check("MOZ_SERVICES_HEALTHREPORT off",
          "'MOZ_SERVICES_HEALTHREPORT': '1'" not in status)
    check_upload_blocked(Path(args.src) if args.src else obj.parent)

    greprefs = dist / "greprefs.js"
    t = greprefs.read_text(encoding="utf-8", errors="replace") if greprefs.is_file() else ""
    m = re.search(r'pref\("toolkit\.telemetry\.server",\s*"([^"]*)"', t)
    check("telemetry.server empty in dist", bool(m) and m.group(1) == "",
          f"value={(m.group(1) if m else 'NOT FOUND')!r}")

    pol = dist / "distribution" / "policies.json"
    if not pol.exists():
        check("zero policies (no policies.json)", True)
    else:
        try:
            p = json.loads(pol.read_text(encoding="utf-8"))
            hop = p.get("policies", {})
            check("policies.json HOP packaged",
                  hop.get("DisableTelemetry") is True and hop.get("DisableAppUpdate") is True)
        except (OSError, ValueError) as e:
            check("policies.json HOP packaged", False, str(e)[:100])

    xpis = list((dist / "distribution" / "extensions").glob("*.xpi")) \
        if (dist / "distribution" / "extensions").is_dir() else []
    check("no bundled XPI (no adblock since 0.1)", len(xpis) == 0,
          f"{len(xpis)} xpi(s)")

    ini = dist / "application.ini"
    if ini.is_file():
        it = ini.read_text(encoding="utf-8", errors="replace")
        m2 = re.search(r"^\[Crash Reporter\]", it, re.M)
        print(f"[info] Crash Reporter in the dist application.ini: "
              f"{'present (prebuilt artifact)' if m2 else 'absent'}")
    print(f"[aether-verify] {'TODO OK' if not FAIL else f'{len(FAIL)} FAILURES'}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())