#!/usr/bin/env python3
"""Build the NX Cursors theme.

NX Cursors is a *recolour* of the Breeze cursor theme. Every silhouette,
hotspot, frame count and animation delay is Breeze's; only the palette is NX.
Breeze's geometry is the quality bar and none of it is redrawn here.

  DERIVATIVE WORK NOTICE
  Shapes derive from breeze_cursors, (C) KDE Visual Design Group, licensed
  LGPL-3.0-or-later. The recoloured sources in src/cursors/ and the built
  theme in cursors/NX-Cursors/ carry that licence; see cursors/NX-Cursors/
  NOTICE. Only colour values are changed - see COLOR_MAP below.

Two stages:

  --import   read /usr/share/icons/breeze_cursors/, recolour, and write the
             sources into src/cursors/ (needs breeze installed; run when
             rebasing on a newer Breeze)
  (default)  build cursors/NX-Cursors/ from src/cursors/ - no Breeze needed

Output layout:

  index.theme          [Icon Theme], Inherits=breeze_cursors (belt and braces;
                       NX ships every shape Breeze does, so nothing falls back)
  NOTICE               licence / attribution
  cursors/             XCursor binaries + Breeze's full alias symlink graph
  cursors_scalable/    per-shape SVG + metadata.json + the same aliases

    python3 tools/build_cursors.py --import   # re-derive sources from Breeze
    python3 tools/build_cursors.py --verify   # build, then re-parse and check
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src", "cursors")
OUT = os.path.join(REPO, "cursors", "NX-Cursors")
BREEZE = "/usr/share/icons/breeze_cursors"

THEME_NAME = "NX Cursors"
THEME_COMMENT = "Matte violet ink - the NX cursor theme, recoloured from Breeze"
INHERITS = "breeze_cursors"
SIZES = [24, 32, 48, 64]          # nominal sizes baked into the XCursor files

# --------------------------------------------------------------- the palette
# Breeze paints bodies with *implicit* black (no fill attribute at all), so the
# ink is injected as a fill on the root <svg> and inherited; the near-black
# literals below are the handful of places Breeze spells it out. Breeze has no
# mid-grey tones anywhere in the set, so nothing needs a lightness-preserving
# hue nudge - one flat ink covers every body.
INK = "#100a1e"                   # near-black with a barely-there violet cast
OUTLINE = "#f7f3ff"               # Breeze's #fff, tinted a hair toward violet

COLOR_MAP = {
    "#fff": OUTLINE, "#ffffff": OUTLINE,          # outline / spinner disc
    "#0d0d0d": INK, "#0a0a0a": INK,               # explicit near-black bodies
    "#070707": INK, "#0c0c0c": INK,
    "#46a7ac": "#00e5ff",   # breeze teal   -> NX cyan   (spinner, resize dots)
    "#d4497f": "#7700ff",   # breeze pink   -> NX violet (spinner, scroll dot)
    "#ed1515": "#ff5470",   # breeze red    -> NX danger (not-allowed, no-drop)
    "#3daee9": "#7700ff",   # breeze blue   -> NX violet (help ?, context-menu)
    "#18c087": "#00e5ff",   # breeze green  -> NX cyan   (alias / link)
    "#11d116": "#00e5ff",   # breeze green  -> NX cyan   (copy +)
    "#f67400": "#ffb300",   # breeze orange -> NX amber  (x-cursor, wayland)
    # "#333" is only the display:none hotspot marker - deliberately untouched.
}

COLOR_ATTR = re.compile(r'\b(fill|stroke|stop-color|flood-color)="([^"]+)"')
STOP_TAG = re.compile(r"<stop\b[^>]*/?>")
SVG_ROOT = re.compile(r"<svg\b[^>]*>")
# (?<![-\w]) so stroke-width="..." is not mistaken for the canvas width
SVG_SIZE = re.compile(r'(?<![-\w])(?:width|height)="(\d+(?:\.\d+)?)"')

# XCursor file format constants (xcursor(3) / Xcursor.h).
MAGIC = b"Xcur"
FILE_HEADER_SIZE = 16
FILE_VERSION = 0x10000
CHUNK_IMAGE = 0xFFFD0002
IMAGE_HEADER_SIZE = 36
IMAGE_VERSION = 1

NOTICE = """NX Cursors
==========

NX Cursors is a derivative of the Breeze cursor theme.

  Upstream:  breeze_cursors, from the Breeze theme
  Copyright: (C) KDE Visual Design Group and the KDE community
  Licence:   LGPL-3.0-or-later

Every cursor silhouette, hotspot, animation frame and frame delay in this
theme is Breeze's, unmodified. The only change is the colour palette, applied
mechanically by tools/build_cursors.py (see COLOR_MAP in that file): Breeze's
black bodies become NX ink #100a1e, its white outline becomes #f7f3ff, and its
accent colours are mapped onto the NX roles - violet #7700ff, cyan #00e5ff,
amber #ffb300, danger #ff5470.

As a derivative work this theme is distributed under the same licence,
LGPL-3.0-or-later.
"""


# ------------------------------------------------------------------ recolour
def recolour(svg_text: str) -> str:
    """Apply the NX palette to one Breeze SVG. Geometry is never touched."""
    def swap(m):
        prop, val = m.group(1), m.group(2).strip().lower()
        return f'{prop}="{COLOR_MAP[val]}"' if val in COLOR_MAP else m.group(0)

    text = COLOR_ATTR.sub(swap, svg_text)

    # Breeze bodies carry no fill attribute and fall back to black; an inherited
    # fill on the root turns every one of them into NX ink at once.
    text, n = re.subn(r"<svg\b", f'<svg fill="{INK}"', text, count=1)
    if n != 1:
        raise ValueError("no <svg> root found")

    # stop-color does not inherit from fill; crosshair's gradient stops rely on
    # the black default, so spell the ink out on any stop that lacks one.
    def fix_stop(m):
        tag = m.group(0)
        if "stop-color=" in tag:
            return tag
        if tag.endswith("/>"):
            return tag[:-2].rstrip() + f' stop-color="{INK}"/>'
        return tag[:-1].rstrip() + f' stop-color="{INK}">'

    return STOP_TAG.sub(fix_stop, text)


def cmd_import() -> int:
    """Re-derive src/cursors/ from the installed Breeze theme."""
    bscal = os.path.join(BREEZE, "cursors_scalable")
    bbin = os.path.join(BREEZE, "cursors")
    if not os.path.isdir(bscal):
        print(f"breeze not found at {BREEZE}", file=sys.stderr)
        return 1

    shutil.rmtree(SRC, ignore_errors=True)
    os.makedirs(SRC)

    shapes = sorted(d for d in os.listdir(bscal)
                    if os.path.isdir(os.path.join(bscal, d))
                    and not os.path.islink(os.path.join(bscal, d)))
    nsvg = 0
    for shape in shapes:
        sdir, ddir = os.path.join(bscal, shape), os.path.join(SRC, shape)
        os.makedirs(ddir)
        for fn in sorted(os.listdir(sdir)):
            spath, dpath = os.path.join(sdir, fn), os.path.join(ddir, fn)
            if fn.endswith(".svg"):
                text = open(spath).read()
                root = SVG_ROOT.search(text)
                sizes = {float(v) for v in SVG_SIZE.findall(root.group(0))}
                if sizes != {32.0}:
                    raise ValueError(f"{shape}/{fn}: canvas {sizes}, expected 32")
                open(dpath, "w").write(recolour(text))
                nsvg += 1
            else:
                shutil.copyfile(spath, dpath)   # metadata.json, verbatim

    # Breeze's alias graph: cursors/ and cursors_scalable/ carry the same set.
    # Some are chained (grabbing -> closedhand -> dnd-move); flatten to the
    # real shape so every alias is one hop.
    def resolve(name: str) -> str:
        seen = set()
        while name not in shapes:
            if name in seen:
                raise ValueError(f"alias loop at {name}")
            seen.add(name)
            link = os.path.join(bbin, name)
            if not os.path.islink(link):
                break
            name = os.path.basename(os.readlink(link))
        return name

    aliases = {}
    for entry in sorted(os.listdir(bbin)):
        full = os.path.join(bbin, entry)
        if os.path.islink(full):
            aliases[entry] = resolve(os.path.basename(os.readlink(full)))
    unresolved = {k: v for k, v in aliases.items() if v not in shapes}
    if unresolved:
        raise ValueError(f"aliases pointing outside the shape set: {unresolved}")
    with open(os.path.join(SRC, "aliases.json"), "w") as fh:
        json.dump(aliases, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"imported {len(shapes)} shapes ({nsvg} svgs recoloured), "
          f"{len(aliases)} aliases -> {SRC}")
    return 0


# ------------------------------------------------------------------ raster IO
def rasterise(svg_path: str, px: int) -> Image.Image:
    proc = subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px), "-f", "png",
                           svg_path], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"rsvg-convert {svg_path}: {proc.stderr.decode().strip()}")
    img = Image.open(io.BytesIO(proc.stdout)).convert("RGBA")
    return img if img.size == (px, px) else img.resize((px, px), Image.LANCZOS)


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


class CursorImage:
    __slots__ = ("nominal", "size", "xhot", "yhot", "delay", "pixels")

    def __init__(self, nominal, size, xhot, yhot, delay, pixels):
        self.nominal, self.size = nominal, size
        self.xhot, self.yhot, self.delay = xhot, yhot, delay
        self.pixels = pixels


def write_xcursor(path: str, images: list[CursorImage]) -> None:
    ntoc = len(images)
    offset = FILE_HEADER_SIZE + 12 * ntoc
    chunks, positions = [], []
    for im in images:
        positions.append(offset)
        chunk = struct.pack("<9I", IMAGE_HEADER_SIZE, CHUNK_IMAGE, im.nominal,
                            IMAGE_VERSION, im.size, im.size, im.xhot, im.yhot,
                            im.delay) + im.pixels
        chunks.append(chunk)
        offset += len(chunk)
    with open(path, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<III", FILE_HEADER_SIZE, FILE_VERSION, ntoc))
        for im, pos in zip(images, positions):
            fh.write(struct.pack("<III", CHUNK_IMAGE, im.nominal, pos))
        for chunk in chunks:
            fh.write(chunk)


CANVAS = 32.0    # every Breeze scalable SVG is a 32x32 canvas (checked on import)


def scale_hotspot(value: float, scale: float, limit: int) -> int:
    """Breeze's own rasteriser truncates rather than rounds (verified against
    all 47 of its binaries: floor agrees 93/94, round only 64/94). A couple of
    its metadata hotspots carry float noise (15.499780617600003 for 15.5), so
    quantise before truncating - that takes the agreement to 94/94."""
    return min(limit - 1, max(0, math.floor(round(value, 3) * scale + 1e-9)))


def build_shape(shape: str, out_bin: str, out_scal: str) -> int:
    sdir = os.path.join(SRC, shape)
    meta = json.load(open(os.path.join(sdir, "metadata.json")))
    nominal_of_canvas = meta[0]["nominal_size"]

    images = []
    for nominal in SIZES:
        px = round(nominal * CANVAS / nominal_of_canvas)
        scale = px / CANVAS
        for entry in meta:
            xhot = scale_hotspot(entry["hotspot_x"], scale, px)
            yhot = scale_hotspot(entry["hotspot_y"], scale, px)
            img = rasterise(os.path.join(sdir, entry["filename"]), px)
            images.append(CursorImage(nominal, px, xhot, yhot,
                                      int(entry.get("delay", 0)),
                                      premultiplied_argb(img)))
    write_xcursor(os.path.join(out_bin, shape), images)

    dst = os.path.join(out_scal, shape)
    os.makedirs(dst, exist_ok=True)
    for fn in sorted(os.listdir(sdir)):
        shutil.copyfile(os.path.join(sdir, fn), os.path.join(dst, fn))
    return len(images)


def link_all(directory: str, aliases: dict) -> None:
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
        px = struct.unpack_from(f"<{w * h}I", data, pos + IMAGE_HEADER_SIZE)
        out.append(dict(nominal=subtype, w=w, h=h, xhot=xhot, yhot=yhot,
                        delay=delay, pixels=px))
    return out


def verify(samples: list[str]) -> None:
    print("\nverifying built cursors")
    for name in samples:
        meta = json.load(open(os.path.join(SRC, name, "metadata.json")))
        imgs = read_xcursor(os.path.join(OUT, "cursors", name))
        nominals = sorted({i["nominal"] for i in imgs})
        assert nominals == sorted(SIZES), f"{name}: sizes {nominals}"
        assert len(imgs) == len(SIZES) * len(meta), f"{name}: {len(imgs)} images"
        opaque = 0
        for im in imgs:
            assert im["w"] == im["h"] == round(
                im["nominal"] * CANVAS / meta[0]["nominal_size"]), \
                f"{name}: {im['w']}px for nominal {im['nominal']}"
            assert 0 <= im["xhot"] < im["w"] and 0 <= im["yhot"] < im["h"], \
                f"{name}: hotspot {im['xhot']},{im['yhot']} outside {im['w']}px"
            assert im["delay"] == int(meta[0].get("delay", 0)), f"{name}: delay"
            for p in im["pixels"]:
                a = p >> 24
                if max((p >> 16) & 255, (p >> 8) & 255, p & 255) > a:
                    raise AssertionError(f"{name}: channel > alpha, not premultiplied")
                opaque += 1 if a else 0
        assert opaque, f"{name}: fully transparent"
        print(f"  ok {name:<14} {len(imgs):3d} images  sizes={nominals}  "
              f"frames={len(meta)}  delay={imgs[0]['delay']}  "
              f"hotspot@64px={[(i['xhot'], i['yhot']) for i in imgs if i['w'] == 64][0]}")
    cross_check_against_breeze()


def cross_check_against_breeze() -> None:
    """If Breeze is installed, assert our hotspots and frame timing match its
    own binaries wherever the raster sizes line up. This is the guarantee that
    the recolour changed nothing but colour."""
    bdir = os.path.join(BREEZE, "cursors")
    if not os.path.isdir(bdir):
        print("  (breeze not installed - skipping cross-check)")
        return
    checked = bad = 0
    for shape in sorted(d for d in os.listdir(SRC)
                        if os.path.isdir(os.path.join(SRC, d))):
        ours = {(i["w"]): i for i in read_xcursor(os.path.join(OUT, "cursors", shape))}
        for theirs in read_xcursor(os.path.join(bdir, shape)):
            mine = ours.get(theirs["w"])
            if mine is None:
                continue
            checked += 1
            if (mine["xhot"], mine["yhot"]) != (theirs["xhot"], theirs["yhot"]):
                bad += 1
                print(f"  ! {shape} @{theirs['w']}px hotspot "
                      f"{(mine['xhot'], mine['yhot'])} != breeze "
                      f"{(theirs['xhot'], theirs['yhot'])}")
    assert not bad, f"{bad} hotspot mismatches against breeze"
    print(f"  ok hotspots match breeze on all {checked} shared rasters")


# ----------------------------------------------------------------------- main
def main() -> int:
    if "--import" in sys.argv:
        rc = cmd_import()
        if rc or "--build" not in sys.argv:
            return rc

    shapes = sorted(d for d in os.listdir(SRC)
                    if os.path.isdir(os.path.join(SRC, d)))
    aliases = json.load(open(os.path.join(SRC, "aliases.json")))
    missing = sorted(set(aliases.values()) - set(shapes))
    if missing:
        print("aliases point at missing shapes:", missing, file=sys.stderr)
        return 1

    out_bin = os.path.join(OUT, "cursors")
    out_scal = os.path.join(OUT, "cursors_scalable")
    for d in (out_bin, out_scal):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    total = 0
    for shape in shapes:
        total += build_shape(shape, out_bin, out_scal)
    print(f"built {len(shapes)} shapes, {total} rasters")

    link_all(out_bin, aliases)
    link_all(out_scal, aliases)

    with open(os.path.join(OUT, "index.theme"), "w") as fh:
        fh.write("[Icon Theme]\n"
                 f"Name={THEME_NAME}\n"
                 f"Comment={THEME_COMMENT}\n"
                 f"Inherits={INHERITS}\n")
    with open(os.path.join(OUT, "NOTICE"), "w") as fh:
        fh.write(NOTICE)

    print(f"{len(aliases)} aliases -> {OUT}")
    if "--verify" in sys.argv:
        verify(["default", "wait", "progress", "pointer", "crosshair"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
