#!/usr/bin/env python3
"""Build the installer's web fonts (WOFF) from the variable originals.

The stub pages ship @font-face WOFF, not system fonts, because the host is
IE in Edge mode: it reads the files out of $PLUGINSDIR at install time. Three
files, two families:

  quicksand-bold.woff     700   titles (Welcome splash, page headers)
  comfortaa-bold.woff     700   buttons
  comfortaa-medium.woff   500   body text

Both families are Google Fonts under the SIL Open Font License, so commercial
use and embedding are both fine; keep the OFL notice next to the sources.

Usage:
  python scripts/generate-fonts.py [--src C:\\aether-156]

The variable originals are cached under branding/source/fonts/. Pass
--refresh to re-download them. Everything else is local: fontTools pins the
weight axis and subsets to latin + latin-ext, which is everything the English
installer text needs (about 49 KB for the set, versus 128 KB unsusbetted).

Traps this exists to avoid:
  * Google dropped truetype from the css APIs: css2 now serves woff2 only, so
    fontTools needs `brotli` installed to read the download at all.
  * A modern UA makes css2 emit one @font-face per unicode subset and the
    first block is vietnamese, not latin. Pick the block labelled `latin`.
  * `pip install fonttools brotli` on the mozilla-build python.
"""
import argparse
import io
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "branding" / "source" / "fonts"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# family, css2 family name, weight, output file
FONTS = [
    ("Quicksand", "Quicksand", 700, "quicksand-bold.woff"),
    ("Comfortaa", "Comfortaa", 700, "comfortaa-bold.woff"),
    ("Comfortaa", "Comfortaa", 500, "comfortaa-medium.woff"),
]

# latin + latin-ext + the punctuation the pages actually use
UNICODES = ",".join([
    "U+0020-007E", "U+00A0-00FF", "U+0131", "U+0152-0153", "U+02BB-02BC",
    "U+02C6", "U+02DA", "U+02DC", "U+2013-2014", "U+2018-201A", "U+201C-201E",
    "U+2020-2022", "U+2026", "U+2030", "U+2039-203A", "U+2044", "U+20AC",
    "U+2122", "U+2191", "U+2193", "U+2212", "U+2215", "U+FEFF", "U+FFFD",
])


def fetch_latin(family, probe_lo=300, probe_hi=700):
    """Download the latin-subset variable TTF for a family.

    css2 speaks woff2 these days, so the bytes are converted back to sfnt in
    memory; the weight axis survives, which is what lets us pin it locally.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        sys.exit("fontTools missing: pip install fonttools brotli")

    def get(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read()

    # Ask for a weight *range*: a single value makes Google serve a static
    # instance with no fvar table, which silently drops the axis and pins
    # every weight to that one. The range must stay inside the family's real
    # axis or Google answers 400 (Quicksand is 300..700).
    css = get(f"https://fonts.googleapis.com/css2?family={family}"
              f":wght@{probe_lo}..{probe_hi}&display=swap").decode(
                  "utf-8", "replace")
    blocks = re.split(r"/\*\s*([a-z\-]+)\s*\*/", css)
    url = None
    for i in range(1, len(blocks) - 1, 2):
        if blocks[i] == "latin":                      # not latin-ext
            m = re.findall(r"url\((https://[^)]+\.woff2)\)", blocks[i + 1])
            if m:
                url = m[0]
                break
    if not url:
        raise SystemExit(f"no latin subset for {family}")
    data = get(url)
    f = TTFont(io.BytesIO(data))
    f.flavor = None
    return f


def build(family, weight, out_path, refresh=False):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    src = CACHE / f"{family}.ttf"
    if refresh or not src.is_file():
        CACHE.mkdir(parents=True, exist_ok=True)
        f = fetch_latin(family)
        f.save(str(src))
        axes = ", ".join(f"{a.axisTag} {a.minValue:g}..{a.maxValue:g}"
                         for a in f["fvar"].axes) if "fvar" in f else "static"
        print(f"[aether-fonts] {family}: downloaded ({axes})")

    font = TTFont(str(src))
    if "fvar" not in font:
        font.close()
        raise SystemExit(
            f"{src.name} is static, not variable: the download lost the "
            f"weight axis, so every weight would come out identical. Delete "
            f"it and re-run with --refresh.")
    axis = font["fvar"].axes[0]
    if not (axis.minValue <= weight <= axis.maxValue):
        font.close()
        raise SystemExit(
            f"{family} has no weight {weight}: the axis runs "
            f"{axis.minValue:g}..{axis.maxValue:g}. This is not a download "
            f"problem, the family simply stops there (Quicksand tops out at "
            f"700).")
    instancer.instantiateVariableFont(font, {"wght": weight}, inplace=True,
                                      updateFontNames=False)

    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["*"]
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = ["*"]
    opts.drop_tables += ["DSIG"]
    opts.notdef_outline = True
    opts.recalc_bounds = True
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=subset.parse_unicodes(UNICODES))
    sub.subset(font)
    subset.save_font(font, str(out_path), opts)
    font.close()

    check = TTFont(str(out_path))
    got = check["OS/2"].usWeightClass
    check.close()
    if got != weight:
        raise SystemExit(f"{out_path.name}: wrote weight {got}, wanted {weight}")
    print(f"[aether-fonts] {out_path.name}: {out_path.stat().st_size/1024:.1f} KB "
          f"(weight {got} verified)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=r"C:\aether-156",
                    help="Firefox worktree (nsis/content lives here)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the variable originals")
    args = ap.parse_args()
    content = Path(args.src) / "browser" / "installer" / "windows" / "nsis" \
        / "content"
    if not content.is_dir():
        raise SystemExit(f"no nsis/content at {content}")
    for family, cssname, weight, name in FONTS:
        build(cssname, weight, content / name, refresh=args.refresh)
    print("[aether-fonts] OK")


if __name__ == "__main__":
    main()