"""Patches 7zSD.Win32.sfx with the Aether icon and versioninfo.

The final installer is a prebuilt 7z SFX wrapper (other-licenses/7zstub)
whose icon and FileDescription are Firefox's. NSIS MUI_ICON only affects the
inner installer: the icon Explorer shows on AetherSetup-<version>.exe is the
SFX module's own RT_GROUP_ICON/RT_ICON, because make-stub-offline.py
concatenates branding/sfx-7zSD.Win32.sfx + sfx-config.txt + payload.7z and
Windows reads the icon off the resulting file. This rewrites those resources
and VS_VERSIONINFO through UpdateResource (ctypes). Idempotent: it always
starts from the upstream .sfx.

Usage:
  python scripts/patch-sfx-stub.py [--src C:\\aether-156]

Paths are derived from this file's location; nothing is hardcoded."""
import argparse
import ctypes
import struct
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

W = ctypes.windll.kernel32
W.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
W.BeginUpdateResourceW.restype = ctypes.c_void_p
W.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_ushort,
                              ctypes.c_void_p, ctypes.c_uint]
W.UpdateResourceW.restype = ctypes.c_bool
W.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
W.EndUpdateResourceW.restype = ctypes.c_bool

RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
LANG = 1033  # en-US (the one the stub ships with)

OUT_REPO = REPO / "branding" / "sfx-7zSD.Win32.sfx"

# The upstream SFX is the pristine copy we always start from, so the patch is
# idempotent and re-runnable. Resolve it from --src, never from a fixed path.
UPSTREAM_REL = "other-licenses/7zstub/firefox/7zSD.Win32.sfx"

# Icon source: the one versioned in branding/, which generate-icons.py builds
# from branding/source/aether-setup.png (the box art).
LOGO = REPO / "branding" / "setup.ico"
if not LOGO.is_file():
    raise SystemExit(f"missing icon: {LOGO}")

SIZES = [16, 32, 48, 256]  # 4 slots = the ones the stub ship with (ids 1-4)


def _largest_ico_frame(path, Image):
    """Largest RGBA frame inside an .ico, read without PIL's size guessing.

    PIL's ICO plugin opens the smallest frame by default, so resizing from
    it upscales a thumbnail. Walking the ICONDIR by hand gets the master.
    """
    import io
    d = path.read_bytes()
    count = struct.unpack("<H", d[4:6])[0]
    best = None
    for i in range(count):
        w, h, _, _, _, _, sz, off = struct.unpack(
            "<BBBBHHII", d[6 + 16 * i:6 + 16 * (i + 1)])
        if best is None or (w or 256) > best[0]:
            best = (w or 256, d[off:off + sz])
    if best is None:
        raise SystemExit(f"no frames in {path}")
    return Image.open(io.BytesIO(best[1])).convert("RGBA")


def build_ico(images):
    """ICO container built from the given images [(size, png_bytes)]."""
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in images:
        w = size if size < 256 else 0
        out += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32,
                           len(data), offset)
        offset += len(data)
    for _, data in images:
        out += data
    return out


def main():
    from PIL import Image
    import io
    import shutil

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=r"C:\aether-156",
                    help="Firefox worktree (holds other-licenses/7zstub)")
    args = ap.parse_args()

    tree_sfx = Path(args.src) / UPSTREAM_REL
    if not tree_sfx.is_file():
        raise SystemExit(f"missing upstream SFX: {tree_sfx}")

    # Read the 256px entry out of the ICO explicitly. PIL's ICO plugin picks
    # the *smallest* frame by default, so a plain Image.open() + resize()
    # upscales a 16px thumbnail and the result is mush. Downscale from the
    # largest entry instead; deflate_background() in generate-icons.py has
    # already fixed the black-under-alpha bleed these sizes suffer from.
    src = _largest_ico_frame(LOGO, Image)
    print("[sfx] fuente: %dx%d de %s" % (src.width, src.height, LOGO.name))
    images = []
    for s in SIZES:
        buf = io.BytesIO()
        resample = Image.LANCZOS if s < src.width else Image.NEAREST
        src.resize((s, s), resample).save(buf, format="PNG")
        images.append((s, buf.getvalue()))
    ico = build_ico(images)
    print("[sfx] ico %d bytes, %d tamanos" % (len(ico), len(images)))

    # GRPICONDIR: reuses the existing ids 1-4 (in place, no additions).
    grp = struct.pack("<HHH", 0, 1, len(images))
    base_id = 1
    for i, (s, data) in enumerate(images):
        w = s if s < 256 else 0
        grp += struct.pack("<BBBBHHIH", w, w, 0, 0, 1, 32,
                           len(data), base_id + i)

    # Working copy from upstream (idempotent).
    tmp = OUT_REPO.parent / "7zSD.Win32.sfx.tmp"
    OUT_REPO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tree_sfx, tmp)

    h = W.BeginUpdateResourceW(str(tmp), False)
    assert h, "BeginUpdateResource"

    def update(rtype, rid, payload):
        if payload is None:
            ok = W.UpdateResourceW(h, rtype, rid, LANG, None, 0)
        else:
            buf = ctypes.create_string_buffer(bytes(payload))
            ok = W.UpdateResourceW(h, rtype, rid, LANG, buf, len(payload))
        assert ok, (rtype, rid, ctypes.GetLastError())

    # Sobrescribe iconos y grupo in-place (mismos ids).
    for i, (_, data) in enumerate(images):
        update(RT_ICON, base_id + i, data)
    update(RT_GROUP_ICON, 1, grp)
    assert W.EndUpdateResourceW(h, False), "EndUpdateResource"
    print("[sfx] icons ok")

    # Versioninfo: equal-length in-place UTF-16 substitution, ONLY inside the
    # RT_VERSION resource. Direct binary write (pefile only locates the range;
    # its write() did not persist here).
    import pefile as _pe
    _pef = _pe.PE(str(tmp))
    for entry in _pef.DIRECTORY_ENTRY_RESOURCE.entries:
        if entry.id != RT_VERSION:
            continue
        for lang in entry.directory.entries:
            for ver in lang.directory.entries:
                foff = _pef.get_offset_from_rva(
                    ver.data.struct.OffsetToData)
                size = ver.data.struct.Size
                with open(str(tmp), "r+b") as fh:
                    fh.seek(foff)
                    seg = bytearray(fh.read(size))

                def swapurascii(word, new):
                    old_b = (word + "\x00").encode("utf-16-le")
                    new_b = (new + "\x00\x00").encode("utf-16-le")
                    assert len(old_b) == 16 and len(new_b) == 16
                    n = 0
                    i = 0
                    while True:
                        i = seg.find(old_b, i)
                        if i < 0:
                            break
                        seg[i:i + 16] = new_b
                        i += 16
                        n += 1
                    return n

                n1 = swapurascii("Firefox", "Aether")
                n2 = swapurascii("Mozilla", "Aether")
                print("[sfx] versioninfo: %d Firefox, %d Mozilla" % (n1, n2))
                with open(str(tmp), "r+b") as fh:
                    fh.seek(foff)
                    fh.write(bytes(seg))
    _pef.close()

    shutil.move(str(tmp), str(OUT_REPO))
    print("[sfx] OK", OUT_REPO, OUT_REPO.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
