"""Patches 7zSD.Win32.sfx with the Aetherfox icon and versioninfo.

The final installer is a prebuilt 7z SFX wrapper (other-licenses/7zstub)
whose icon and FileDescription are Firefox's. NSIS MUI_ICON only affects the
inner installer: the icon Explorer shows on AetherfoxSetup-<version>.exe is the
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


# --------------------------------------------------------------------------
# VS_VERSIONINFO rewrite.
#
# The upstream stub's file properties say CompanyName "Mozilla",
# FileDescription/ProductName "Firefox". They are longer than the slots they
# live in ("Aether Group", "Aetherfox Setup"), so the old equal-length
# in-place substitution cannot express them: the resource is parsed into its
# block tree, the string values are replaced, and the tree is re-serialized
# and written back with UpdateResourceW (which takes any length).
#
# This file stores wValueLength in bytes (a string's value includes its NUL),
# unlike the "words" the MSDN page mentions; the parser keeps that convention,
# which is proven by a byte-identical parse/serialize round-trip.
# --------------------------------------------------------------------------

def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _align4(n):
    return (n + 3) & ~3


def read_rt_version(path):
    """Raw bytes of (type=RT_VERSION, id=1), located without pefile."""
    data = Path(path).read_bytes()
    e_lfanew = _u32(data, 0x3C)
    assert data[e_lfanew:e_lfanew + 4] == b"PE\x00\x00", "not a PE"
    coff = e_lfanew + 4
    nsec = _u16(data, coff + 2)
    opt = coff + 20
    dd = opt + (112 if _u16(data, opt) == 0x20B else 96)
    res_rva = _u32(data, dd + 2 * 8)
    sections = []
    so = opt + _u16(data, coff + 16)
    for i in range(nsec):
        e = so + 40 * i
        sections.append((_u32(data, e + 12), _u32(data, e + 8),
                         _u32(data, e + 16), _u32(data, e + 20)))

    def rva2off(rva):
        for va, vsize, raw_size, raw_ptr in sections:
            if va <= rva < va + max(vsize, raw_size):
                return raw_ptr + (rva - va)
        raise SystemExit(f"rva {rva:#x} not in any section")

    base = rva2off(res_rva)

    def walk(off, want, depth):
        n_named, n_id = _u16(data, off + 12), _u16(data, off + 14)
        for i in range(n_named + n_id):
            e = off + 16 + 8 * i
            name, sub = _u32(data, e), _u32(data, e + 4)
            if depth == 0 and name != want:
                continue
            if sub & 0x80000000:
                got = walk(base + (sub & 0x7FFFFFFF), want, depth + 1)
                if got:
                    return got
            else:
                d = base + sub
                return rva2off(_u32(data, d)), _u32(data, d + 4)
        return None

    got = walk(base, RT_VERSION, 0)
    if not got:
        raise SystemExit("no RT_VERSION resource in the SFX")
    off, size = got
    return data[off:off + size]


def parse_vs_block(buf, off):
    w_len, w_val, w_type = _u16(buf, off), _u16(buf, off + 2), _u16(buf, off + 4)
    p = off + 6
    kstart = p
    while _u16(buf, p) != 0:
        p += 2
    key = buf[kstart:p].decode("utf-16-le")
    p = _align4(p + 2)
    value = buf[p:p + w_val]
    p = _align4(p + w_val)
    children = []
    while p < off + w_len:
        child, p = parse_vs_block(buf, p)
        children.append(child)
    return {"key": key, "type": w_type, "value": value,
            "children": children}, off + w_len


def serialize_vs_block(b):
    body = b"".join(serialize_vs_block(c) for c in b["children"])
    out = bytearray(6)
    struct.pack_into("<HHH", out, 0, 0, len(b["value"]), b["type"])
    out += b["key"].encode("utf-16-le") + b"\x00\x00"
    while len(out) % 4:
        out += b"\x00"
    out += b["value"]
    while len(out) % 4:
        out += b"\x00"
    out += body
    struct.pack_into("<H", out, 0, len(out))
    return bytes(out)


def vs_strings(node, path=()):
    """Every string-valued leaf, as (index path, node)."""
    if node["type"] == 1 and not node["children"] and node["key"] not in (
            "VS_VERSION_INFO", "StringFileInfo", "VarFileInfo"):
        yield path, node
    for i, c in enumerate(node["children"]):
        yield from vs_strings(c, path + (i,))


VERSION_MAP = {
    "CompanyName": "Aether Group",
    "FileDescription": "Aetherfox Setup",
    "ProductName": "Aetherfox",
    "LegalCopyright": "Aether Group",
}


def rewrite_versioninfo(raw):
    tree, end = parse_vs_block(raw, 0)
    if end != len(raw):
        raise SystemExit("RT_VERSION did not parse to its end")
    assert serialize_vs_block(tree) == raw, "round-trip changed the resource"
    changed = 0
    for _, node in vs_strings(tree):
        new = VERSION_MAP.get(node["key"])
        if new is None:
            continue
        node["value"] = (new + "\x00").encode("utf-16-le")
        changed += 1
    return serialize_vs_block(tree), changed



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
    print("[sfx] icons ok")

    # Versioninfo: parse the block tree, rename the values, re-serialize. Read
    # from the pristine upstream file: the temp copy's RT_VERSION is identical
    # at this point and reading it mid-update-session would be undefined.
    raw = read_rt_version(tree_sfx)
    new_raw, changed = rewrite_versioninfo(raw)
    update(RT_VERSION, 1, new_raw)
    print("[sfx] versioninfo: %d cadenas renombradas, %d -> %d bytes"
          % (changed, len(raw), len(new_raw)))

    assert W.EndUpdateResourceW(h, False), "EndUpdateResource"

    shutil.move(str(tmp), str(OUT_REPO))
    print("[sfx] OK", OUT_REPO, OUT_REPO.stat().st_size, "bytes")



if __name__ == "__main__":
    main()
