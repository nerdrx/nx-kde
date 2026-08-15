#!/usr/bin/env python3
"""Build the NX Cursors theme from the SVG sources in src/cursors/.

Outputs cursors/NX-Cursors/ containing

  index.theme          [Icon Theme] block, Inherits=breeze_cursors
  cursors/             XCursor binaries (X11 / XWayland) + the full alias
                       symlink set harvested from breeze_cursors
  cursors_scalable/    per-shape SVG + metadata.json (Plasma 6 Wayland) +
                       the same alias symlinks

The XCursor container is written here directly -- no xcursorgen needed. Only
rsvg-convert (rasterising) and PIL (reading the PNGs back) are required.

    python3 tools/build_cursors.py           # build
    python3 tools/build_cursors.py --verify  # build, then re-parse and check
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from collections import OrderedDict

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src", "cursors")
OUT = os.path.join(REPO, "cursors", "NX-Cursors")
BREEZE = "/usr/share/icons/breeze_cursors"

THEME_NAME = "NX Cursors"
THEME_COMMENT = "Liquid glass on deep space - the NX cursor theme"
INHERITS = "breeze_cursors"

# XCursor file format constants (see xcursor(3) / Xcursor.h).
MAGIC = b"Xcur"
FILE_HEADER_SIZE = 16
FILE_VERSION = 0x10000
CHUNK_IMAGE = 0xFFFD0002
IMAGE_HEADER_SIZE = 36
IMAGE_VERSION = 1

# Breeze shapes we deliberately do not draw; their names are still useful as
# alias sources, so map them onto the nearest NX shape. Anything not listed
# here and not shipped is left to Inherits=breeze_cursors.
BREEZE_EQUIVALENTS = {
    "fleur": "all-scroll",
    "dnd-move": "closedhand",
    "dnd-no-drop": "no-drop",
    "circle": "not-allowed",
}

# Breeze points these CSS-style names at `default`, which is almost certainly a
# packaging slip. Point them at the shape they name instead.
ALIAS_OVERRIDES = {
    "size-hor": "size_hor",
    "size-ver": "size_ver",
    "size-bdiag": "size_bdiag",
    "size-fdiag": "size_fdiag",
}

ROTATE_RE = re.compile(r'transform="rotate\(0 ([-\d.]+) ([-\d.]+)\)"')


# --------------------------------------------------------------------- config
def load_config() -> dict:
    with open(os.path.join(SRC, "hotspots.json")) as fh:
        return json.load(fh)


# ------------------------------------------------------------------ rendering
def frame_svg(source: str, angle: float) -> str:
    """Return the source SVG with every rotate(0 cx cy) turned by `angle`."""
    if not angle:
        return source
    return ROTATE_RE.sub(
        lambda m: f'transform="rotate({angle:g} {m.group(1)} {m.group(2)})"', source)


def rasterise(svg_text: str, px: int) -> Image.Image:
    proc = subprocess.run(
        ["rsvg-convert", "-w", str(px), "-h", str(px), "-f", "png"],
        input=svg_text.encode(), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"rsvg-convert failed: {proc.stderr.decode().strip()}")
    img = Image.open(io.BytesIO(proc.stdout)).convert("RGBA")
    if img.size != (px, px):
        img = img.resize((px, px), Image.LANCZOS)
    return img


def premultiplied_argb(img: Image.Image) -> bytes:
    """ARGB32, premultiplied alpha, little-endian per pixel, rows top-to-bottom."""
    raw = img.tobytes("raw", "RGBA")
    out = bytearray()
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if a == 0:
            out += b"\0\0\0\0"
            continue
        if a != 255:
            r = (r * a + 127) // 255
            g = (g * a + 127) // 255
            b = (b * a + 127) // 255
        out += struct.pack("<I", (a << 24) | (r << 16) | (g << 8) | b)
    return bytes(out)


# ------------------------------------------------------------- xcursor writer
class CursorImage:
    __slots__ = ("nominal", "size", "xhot", "yhot", "delay", "pixels")

    def __init__(self, nominal, size, xhot, yhot, delay, pixels):
        self.nominal, self.size = nominal, size
        self.xhot, self.yhot, self.delay = xhot, yhot, delay
        self.pixels = pixels


def write_xcursor(path: str, images: list[CursorImage]) -> None:
    """Serialise images into one XCursor file (little-endian throughout)."""
    # TOC first, ordered by nominal size then frame order, which is what
    # libXcursor expects when it walks the table looking for a size.
    ntoc = len(images)
    body_start = FILE_HEADER_SIZE + 12 * ntoc

    chunks, positions, offset = [], [], body_start
    for im in images:
        positions.append(offset)
        chunk = struct.pack(
            "<9I", IMAGE_HEADER_SIZE, CHUNK_IMAGE, im.nominal, IMAGE_VERSION,
            im.size, im.size, im.xhot, im.yhot, im.delay) + im.pixels
        chunks.append(chunk)
        offset += len(chunk)

    with open(path, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<III", FILE_HEADER_SIZE, FILE_VERSION, ntoc))
        for im, pos in zip(images, positions):
            fh.write(struct.pack("<III", CHUNK_IMAGE, im.nominal, pos))
        for chunk in chunks:
            fh.write(chunk)


# ------------------------------------------------------------------- building
def build_shape(name: str, spec: dict, cfg: dict, out_bin: str, out_scal: str) -> int:
    canvas = cfg["canvas"]
    nominal_of_canvas = cfg["nominal_size"]
    source = open(os.path.join(SRC, name + ".svg")).read()

    nframes = int(spec.get("frames", 1))
    delay = int(spec.get("delay", 0))
    hx, hy = spec["hotspot"]

    angles = [i * 360.0 / nframes for i in range(nframes)]
    svgs = [frame_svg(source, a) for a in angles]

    # --- XCursor binary -----------------------------------------------------
    images = []
    for nominal in cfg["sizes"]:
        px = round(nominal * canvas / nominal_of_canvas)
        scale = px / canvas
        xhot = min(px - 1, max(0, round(hx * scale)))
        yhot = min(px - 1, max(0, round(hy * scale)))
        for svg_text in svgs:
            images.append(CursorImage(nominal, px, xhot, yhot, delay,
                                      premultiplied_argb(rasterise(svg_text, px))))
    write_xcursor(os.path.join(out_bin, name), images)

    # --- cursors_scalable ---------------------------------------------------
    shape_dir = os.path.join(out_scal, name)
    os.makedirs(shape_dir, exist_ok=True)
    meta = []
    for i, svg_text in enumerate(svgs):
        fname = name + ".svg" if nframes == 1 else f"{name}-{i + 1:02d}.svg"
        with open(os.path.join(shape_dir, fname), "w") as fh:
            fh.write(svg_text)
        entry = OrderedDict()
        entry["filename"] = fname
        if nframes > 1:
            entry["delay"] = delay
        entry["hotspot_x"] = hx
        entry["hotspot_y"] = hy
        entry["nominal_size"] = nominal_of_canvas
        meta.append(entry)
    with open(os.path.join(shape_dir, "metadata.json"), "w") as fh:
        json.dump(meta, fh, indent=4)
        fh.write("\n")
    return len(images)


# --------------------------------------------------------------------- aliases
def harvest_aliases(shapes: set[str]) -> dict[str, str]:
    """Mirror breeze_cursors' symlink set for every target we actually ship."""
    src_dir = os.path.join(BREEZE, "cursors")
    if not os.path.isdir(src_dir):
        print(f"  ! {src_dir} not found - shipping without legacy aliases")
        return {}

    aliases: dict[str, str] = {}
    for entry in sorted(os.listdir(src_dir)):
        full = os.path.join(src_dir, entry)
        if not os.path.islink(full) or entry in shapes:
            continue  # we ship a real file under that name
        target = os.path.basename(os.readlink(full))
        # follow breeze-internal chains (grabbing -> closedhand -> dnd-move)
        seen = set()
        while target not in shapes and target not in BREEZE_EQUIVALENTS:
            link = os.path.join(src_dir, target)
            if not os.path.islink(link) or target in seen:
                break
            seen.add(target)
            target = os.path.basename(os.readlink(link))
        target = ALIAS_OVERRIDES.get(entry, BREEZE_EQUIVALENTS.get(target, target))
        if target in shapes:
            aliases[entry] = target

    # Breeze ships these as real files, not links; we cover them by alias.
    for legacy, shape in BREEZE_EQUIVALENTS.items():
        if shape in shapes and legacy not in shapes and legacy not in aliases:
            if os.path.exists(os.path.join(src_dir, legacy)):
                aliases[legacy] = shape
    return aliases


def link_all(directory: str, aliases: dict[str, str]) -> None:
    for name, target in aliases.items():
        path = os.path.join(directory, name)
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(target, path)


# ------------------------------------------------------------------ verifying
def read_xcursor(path: str) -> list[dict]:
    data = open(path, "rb").read()
    assert data[:4] == MAGIC, f"{path}: bad magic {data[:4]!r}"
    header, version, ntoc = struct.unpack_from("<III", data, 4)
    assert header == FILE_HEADER_SIZE, f"{path}: header size {header}"
    assert version == FILE_VERSION, f"{path}: version {version:#x}"
    out = []
    for i in range(ntoc):
        ctype, subtype, pos = struct.unpack_from("<III", data, 16 + 12 * i)
        assert ctype == CHUNK_IMAGE, f"{path}: toc[{i}] type {ctype:#x}"
        (chdr, ctype2, csub, cver, w, h, xhot, yhot,
         delay) = struct.unpack_from("<9I", data, pos)
        assert (chdr, ctype2, csub, cver) == (IMAGE_HEADER_SIZE, CHUNK_IMAGE, subtype, 1)
        px_off = pos + IMAGE_HEADER_SIZE
        px = struct.unpack_from(f"<{w * h}I", data, px_off)
        out.append(dict(nominal=subtype, w=w, h=h, xhot=xhot, yhot=yhot,
                        delay=delay, pixels=px))
    return out


def verify(cfg: dict, samples: list[str]) -> None:
    print("\nverifying built cursors")
    for name in samples:
        path = os.path.join(OUT, "cursors", name)
        imgs = read_xcursor(path)
        spec = cfg["shapes"][name]
        frames = int(spec.get("frames", 1))
        nominals = sorted({i["nominal"] for i in imgs})
        assert nominals == sorted(cfg["sizes"]), f"{name}: sizes {nominals}"
        assert len(imgs) == len(cfg["sizes"]) * frames, f"{name}: {len(imgs)} images"
        opaque = 0
        for im in imgs:
            assert im["w"] == im["h"] == round(im["nominal"] * cfg["canvas"]
                                               / cfg["nominal_size"]), \
                f"{name}: {im['w']}px for nominal {im['nominal']}"
            assert 0 <= im["xhot"] < im["w"] and 0 <= im["yhot"] < im["h"], \
                f"{name}: hotspot {im['xhot']},{im['yhot']} outside {im['w']}px"
            assert im["delay"] == (spec.get("delay", 0) if frames > 1 else 0)
            for p in im["pixels"]:
                a = p >> 24
                r, g, b = (p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF
                assert max(r, g, b) <= a, \
                    f"{name}: channel > alpha ({r},{g},{b} a={a}) - not premultiplied"
                if a:
                    opaque += 1
        assert opaque > 0, f"{name}: fully transparent"
        print(f"  ok {name:<14} {len(imgs):3d} images  sizes={nominals}  "
              f"frames={frames}  hotspot(64px)="
              f"{[(i['xhot'], i['yhot']) for i in imgs if i['nominal'] == 64][0]}")


# ----------------------------------------------------------------------- main
def main() -> int:
    cfg = load_config()
    shapes = cfg["shapes"]

    missing = [n for n in shapes if not os.path.exists(os.path.join(SRC, n + ".svg"))]
    if missing:
        print("missing sources:", ", ".join(missing), file=sys.stderr)
        return 1

    out_bin = os.path.join(OUT, "cursors")
    out_scal = os.path.join(OUT, "cursors_scalable")
    for d in (out_bin, out_scal):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    total = 0
    for name in sorted(shapes):
        total += build_shape(name, shapes[name], cfg, out_bin, out_scal)
        print(f"  built {name}")

    aliases = harvest_aliases(set(shapes))
    link_all(out_bin, aliases)
    link_all(out_scal, aliases)

    with open(os.path.join(OUT, "index.theme"), "w") as fh:
        fh.write("[Icon Theme]\n"
                 f"Name={THEME_NAME}\n"
                 f"Comment={THEME_COMMENT}\n"
                 f"Inherits={INHERITS}\n")

    print(f"\n{len(shapes)} shapes, {total} rasters, {len(aliases)} aliases -> {OUT}")

    if "--verify" in sys.argv:
        verify(cfg, ["default", "wait", "pointer"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
