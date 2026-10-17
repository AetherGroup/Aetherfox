"""Aether icon set generator v2.

Sources (versioned, the only inputs):
  branding/source/aether-mark.png    the O2 ribbon mark, 1024x1024 RGBA
  branding/source/aether-setup.png   the mark coming out of the box, 1024x1024 RGBA

Generates the whole raster branding set plus the SVG wordmarks and installs it
into:
  1. aether-browser/branding/  (versioned source of truth)
  2. <firefox-src>/browser/branding/aether/  (build tree)

The mark goes everywhere the browser shows an icon (window icons, the .ico
files, about-logo, the exe icon). The setup image goes to the installer hero
(content/setup-hero.png, embedded by AetherSetup.csproj) and to the in-browser
"Aether Setup" page (content/setup-icon.png, 256px).

Usage:
  python scripts/generate-icons.py [--src ..\\firefox-src]
      [--logo branding/source/aether-mark.png]
      [--setup-logo branding/source/aether-setup.png]
"""
import argparse
import base64
import io
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT.parent / "firefox-src"

PNG_SIZES = [16, 22, 24, 32, 48, 64, 128, 256]
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
# Up to this size the icons were rendered as a flat silhouette instead of the
# real mark. Disabled (0): the photographic mark stays legible down to 16px
# and the design must ship intact at every size — see silhouette(), kept for
# potential future use.
SMALL_SIZES = 0
ICO_FILES = ["firefox.ico", "firefox64.ico", "document.ico", "newtab.ico",
             "newwindow.ico"]
# NOTE: pbmode.ico is deliberately NOT generated: private windows keep the
# original white variant so they stay distinct (frozen, do not re-add).

WORDMARK_ABOUT = """<!-- Aetherfox wordmark v1 (replaces Firefox wordmark) -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 372 99">
  <text x="186" y="68" text-anchor="middle" font-family="Segoe UI, system-ui, sans-serif"
        font-size="64" font-weight="600" letter-spacing="2" fill="#ffffff">Aether</text>
</svg>
"""
WORDMARK_DARK = """<!-- Aetherfox wordmark v1 (replaces Firefox wordmark) -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 372 99">
  <text x="186" y="68" text-anchor="middle" font-family="Segoe UI, system-ui, sans-serif"
        font-size="64" font-weight="600" letter-spacing="2" fill="#20123a">Aether</text>
</svg>
"""
LOGO_SVG_TMPL = """<!-- Aetherfox logo v2: raster mark embedded (replaces Firefox fox) -->
<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 192 192">
  <image width="192" height="192" href="data:image/png;base64,{b64}"/>
</svg>
"""


def load_squared(path):
    """RGBA source centred on a square canvas with 6% margin (icons need it)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    margin = int(side * 0.06)
    canvas = Image.new("RGBA", (side + 2 * margin, side + 2 * margin), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
    return deflate_background(canvas)


def deflate_background(im):
    """Spread visible hues into fully-transparent zones (Gaussian, radius
    scaled to the image). PNG sources usually store RGB=black under alpha=0,
    and plain LANCZOS bleeds that black into every edge pixel on downscale —
    at 16-48px the whole mark goes muddy dark. Filling the invisible zones
    with neighbor hues first keeps small sizes bright and true. Radius is
    load-bearing, not cosmetic: 16 leaves the 24px entries as dark as plain
    downscale (proven side-by-side); 28 fills them bright on light AND dark
    backgrounds. Do not lower it without re-running the verdict rig."""
    from PIL import Image, ImageFilter
    rgb = im.convert("RGB")
    a = im.split()[3]
    spread = rgb.filter(ImageFilter.GaussianBlur(28))
    filled = Image.composite(rgb, spread, a)
    filled.putalpha(a)
    return filled


def silhouette(im, rgb=(0x5B, 0x3A, 0xB8)):
    """Flat version of the mark, for the tiny sizes only.

    At <=32px the 3D gradient of the real mark carries no legible detail: it
    only fills the ring with noise, and being a pale lavender it nearly vanishes
    on a light background. A solid silhouette reads clearly at 16px and still
    works on light and dark. Sizes above SMALL_SIZES keep the real mark, where
    the gradient is actually visible.
    """
    from PIL import Image
    # Push the soft gradient edge to a firm one, but keep antialiasing by
    # scaling the semi-transparent band instead of thresholding it hard.
    alpha = im.getchannel("A").point(lambda v: 255 if v > 110 else int(v * 1.7))
    flat = Image.new("RGBA", im.size, rgb + (0,))
    flat.paste(Image.new("RGBA", im.size, rgb + (255,)), (0, 0), alpha)
    return flat


def write_ico(path, layers):
    """Write a multi-size .ico from one prepared image per size.

    Pillow's save(sizes=...) resizes a single source for every entry, so the
    small entries could never differ from the large ones. The ICO container is
    simple enough to emit directly: a directory of entries, each pointing at a
    PNG payload (Vista and later read PNG-compressed entries fine).

    layers: {size: RGBA image}, where size <= 256.
    """
    import struct

    payloads = []
    for size in sorted(layers):
        buf = io.BytesIO()
        layers[size].save(buf, format="PNG")
        payloads.append((size, buf.getvalue()))

    out = bytearray(struct.pack("<HHH", 0, 1, len(payloads)))
    offset = 6 + 16 * len(payloads)
    for size, data in payloads:
        out += struct.pack("<BBBBHHII",
                           0 if size >= 256 else size,   # 0 means 256
                           0 if size >= 256 else size,
                           0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in payloads:
        out += data
    path.write_bytes(bytes(out))


def main():
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--logo", default=str(ROOT / "branding" / "source" / "aether-mark.png"))
    ap.add_argument("--setup-logo",
                    default=str(ROOT / "branding" / "source" / "aether-setup.png"))
    args = ap.parse_args()
    src = Path(args.src)
    for p in (args.logo, args.setup_logo):
        assert Path(p).is_file(), f"source not found: {p}"

    mark = load_squared(args.logo)
    setup = load_squared(args.setup_logo)
    print(f"[aether-icons] mark: {mark.size}  setup: {setup.size}")

    out_repo = ROOT / "branding"
    (out_repo / "content").mkdir(parents=True, exist_ok=True)

    # 1. defaultNN.png (window/taskbar icons). Sizes up to SMALL_SIZES come
    # from the silhouette, the rest from the real mark.
    mark_flat = silhouette(mark)
    for s in PNG_SIZES:
        base = mark_flat if s <= SMALL_SIZES else mark
        base.resize((s, s), Image.LANCZOS).save(out_repo / f"default{s}.png")
    print(f"[aether-icons] {len(PNG_SIZES)} PNGs "
          f"(<= {SMALL_SIZES}px from the silhouette)")

    # 2. Multi-size ICOs for the browser from the mark; setup.ico (the setup
    # exe icon and the uninstaller icon) comes from the setup image: the file
    # is literally called aether-setup, there is nothing to decide here.
    # Same small-size rule as the PNGs, hence the hand-rolled container.
    def layers_from(img):
        flat = silhouette(img)
        return {size: (flat if size <= SMALL_SIZES else img).resize(
            (size, size), Image.LANCZOS) for size, _ in ICO_SIZES}

    for name in ICO_FILES:
        write_ico(out_repo / name, layers_from(mark))
    print(f"[aether-icons] {len(ICO_FILES)} ICOs")
    write_ico(out_repo / "setup.ico", layers_from(setup))
    print("[aether-icons] setup.ico (from the setup image)")

    # 3. content/ rasters from the mark: about-logo.png 192, @2x 384, lockup
    mark.resize((192, 192), Image.LANCZOS).save(out_repo / "content" / "about-logo.png")
    mark.resize((384, 384), Image.LANCZOS).save(out_repo / "content" / "about-logo@2x.png")
    mark.resize((512, 512), Image.LANCZOS).save(out_repo / "content" / "aether-lockup.png")
    # about.png 300x236: mark centred on the dialog background (#130829)
    banner = Image.new("RGBA", (300, 236), (0x13, 0x08, 0x29, 255))
    m = mark.resize((200, 200), Image.LANCZOS)
    banner.paste(m, ((300 - 200) // 2, (236 - 200) // 2), m)
    banner.convert("RGB").save(out_repo / "content" / "about.png")
    print("[aether-icons] about-logo.png/@2x, aether-lockup.png, about.png")

    # 4. Installer hero: the mark at full source resolution, no downscale.
    # (The box art pixelates at hero size; it stays on the exe icon and the
    # in-browser setup page, where it renders small.)
    mark.save(out_repo / "content" / "setup-hero.png")
    setup.resize((256, 256), Image.LANCZOS).save(out_repo / "content" / "setup-icon.png")
    print("[aether-icons] setup-hero.png (mark, full res), setup-icon.png (box)")

    # 5. about-logo.svg = a wrapper around the embedded 192 PNG
    # newline="": on Windows write_text would convert to CRLF and dirty the tree.
    buf = io.BytesIO()
    mark.resize((192, 192), Image.LANCZOS).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    (out_repo / "content" / "about-logo.svg").write_text(
        LOGO_SVG_TMPL.format(b64=b64), encoding="utf-8", newline="")
    (out_repo / "content" / "about-wordmark.svg").write_text(
        WORDMARK_ABOUT, encoding="utf-8", newline="")
    (out_repo / "content" / "firefox-wordmark.svg").write_text(
        WORDMARK_DARK, encoding="utf-8", newline="")
    print("[aether-icons] about-logo.svg, about-wordmark.svg, firefox-wordmark.svg")

    # 6. Install into the firefox-src tree (everything the browser packages;
    #    setup-hero.png is installer-only and stays out of the tree)
    dst = src / "browser" / "branding" / "aether"
    dst_content = dst / "content"
    assert dst.is_dir(), f"{dst} does not exist (sync + the branding patch applied?)"
    n = 0
    for s in PNG_SIZES:
        shutil.copy2(out_repo / f"default{s}.png", dst / f"default{s}.png")
        n += 1
    for name in ICO_FILES + ["setup.ico"]:
        shutil.copy2(out_repo / name, dst / name)
        n += 1
    for name in ["about-logo.png", "about-logo@2x.png", "about.png",
                 "about-logo.svg", "about-wordmark.svg", "firefox-wordmark.svg",
                 "aether-lockup.png", "setup-icon.png"]:
        shutil.copy2(out_repo / "content" / name, dst_content / name)
        n += 1
    print(f"[aether-icons] installed {n} files in {dst}")
    print("[aether-icons] OK")


if __name__ == "__main__":
    main()
