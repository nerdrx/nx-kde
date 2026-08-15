#!/usr/bin/env python3
"""Render the NX Nebula wallpaper set (Plasma 6 wallpaper package).

Implements DESIGN.md §3 "The living background" as a static image:

    field   deep-space vertical gradient #0a0714 -> #12091f (never flat black)
    nebula  two to three enormous, very-low-alpha radial blobs --
            violet upper-left (the light source, §1/§11), cyan lower-right
            and clearly subordinate, plus a deep magenta third off-centre
    vignette edges darker than centre, biased so the lower-right falls off
            hardest -- one light source, upper-left
    stars   sparse tiny points, decoration not attraction

Everything is computed in float32 and TPDF-dithered before the 8-bit
quantisation, because near-black gradients band horribly otherwise.

Fully deterministic: one fixed seed, no clock, no unseeded randomness.

    python3 tools/gen_wallpaper.py            # write the package
    python3 tools/gen_wallpaper.py --check    # verify what was written

Requires: numpy, Pillow.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, replace

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

SEED = 0x7700FF  # NX Violet. The only source of randomness in this file.

BG_TOP = "#0a0714"
BG_BOTTOM = "#12091f"
VIOLET = "#7700ff"
VIOLET_SOFT = "#9a3cff"
CYAN = "#00e5ff"
MAGENTA = "#c31bb0"

# Landscape targets plus one portrait. Plasma picks by aspect/size.
LANDSCAPE_SIZES = ((3840, 2160), (2560, 1440), (1920, 1080))
PORTRAIT_SIZES = ((1080, 1920),)

# Reference scale: sqrt(W*H) of a 1920x1080 frame. Blob sigmas and star
# radii are expressed relative to this so every aspect gets the same
# composition rather than a naive crop.
REF_SCALE = math.sqrt(1920 * 1080)  # 1440.0

STAR_COUNT = 900  # constant across sizes -- same composition, not same density
SCREENSHOT_WIDTH = 400

PKG_DIR = os.path.join("wallpapers", "NX-Nebula")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def hex_rgb(value: str) -> np.ndarray:
    """'#7700ff' -> float32 array of three 0..1 channels."""
    value = value.lstrip("#")
    return np.array(
        [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32
    )


def smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class Blob:
    """One enormous soft radial cloud.

    cx/cy      centre in relative [0,1] frame coordinates
    sigma      radius as a fraction of the frame scale sqrt(W*H)
    amp        peak strength -- this is the restraint dial (§1: if it is
               visible from across the room, halve it)
    stretch    ellipse elongation along the blob's own axis
    angle      that axis, in degrees
    falloff    super-gaussian exponent; < 1 gives fatter, dustier tails
    """

    color: str
    amp: float
    cx: float
    cy: float
    sigma: float
    stretch: float = 1.0
    angle: float = 0.0
    falloff: float = 0.85


# Landscape composition. Violet leads from the upper-left; cyan sits far
# down-right at roughly half the strength; magenta is a deep, almost
# subliminal bloom holding the middle-right together.
BLOBS_LANDSCAPE = (
    Blob(VIOLET, 0.115, 0.19, 0.13, 0.36, stretch=1.50, angle=-28.0, falloff=0.94),
    Blob(VIOLET_SOFT, 0.075, 0.25, 0.17, 0.15, stretch=1.25, angle=-20.0, falloff=1.00),
    Blob(CYAN, 0.052, 0.84, 0.87, 0.30, stretch=1.40, angle=38.0, falloff=0.92),
    Blob(MAGENTA, 0.038, 0.55, 0.68, 0.24, stretch=1.55, angle=68.0, falloff=0.94),
)

# Portrait: the same three-body arrangement, pulled toward the vertical so
# the violet still owns the top-left and cyan still anchors the bottom-right.
BLOBS_PORTRAIT = (
    replace(BLOBS_LANDSCAPE[0], cx=0.22, cy=0.12, sigma=0.38, angle=-42.0),
    replace(BLOBS_LANDSCAPE[1], cx=0.30, cy=0.16, sigma=0.16, angle=-30.0),
    replace(BLOBS_LANDSCAPE[2], cx=0.80, cy=0.87, sigma=0.32, angle=52.0),
    replace(BLOBS_LANDSCAPE[3], cx=0.55, cy=0.62, sigma=0.26, angle=76.0),
)

# Vignette centre sits slightly up-left of frame centre, so the corner that
# falls away hardest is the one furthest from the light (§11).
VIGNETTE_CENTER = (0.455, 0.430)
VIGNETTE_STRENGTH = 0.40
VIGNETTE_POWER = 2.4


# --------------------------------------------------------------------------
# layers
# --------------------------------------------------------------------------


def field(width: int, height: int) -> np.ndarray:
    """Vertical deep-space gradient. Returns (H, W, 3) float32."""
    top = hex_rgb(BG_TOP)
    bottom = hex_rgb(BG_BOTTOM)
    t = ((np.arange(height, dtype=np.float32) + 0.5) / height).reshape(height, 1, 1)
    # A touch of ease so the darkest band hugs the top edge rather than
    # marching down at a constant rate.
    t = t ** 1.15
    return top.reshape(1, 1, 3) + (bottom - top).reshape(1, 1, 3) * t


def add_nebula(img: np.ndarray, blobs, width: int, height: int) -> None:
    """Screen-blend the blobs into img in place."""
    scale = math.sqrt(width * height)
    xs = (np.arange(width, dtype=np.float32) + 0.5 - 0.0).reshape(1, width)
    ys = (np.arange(height, dtype=np.float32) + 0.5 - 0.0).reshape(height, 1)

    for blob in blobs:
        dx = (xs - blob.cx * width) / scale
        dy = (ys - blob.cy * height) / scale
        rad = math.radians(blob.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        u = (dx * cos_a - dy * sin_a) / blob.stretch
        v = dx * sin_a + dy * cos_a
        q = (u * u + v * v) / (2.0 * blob.sigma * blob.sigma)
        # super-gaussian: exponent < 1 widens the skirt into dust
        g = np.exp(-np.power(q + 1e-9, blob.falloff, dtype=np.float32))
        contribution = g[:, :, None] * (blob.amp * hex_rgb(blob.color)).reshape(1, 1, 3)
        # screen blend keeps light additive without ever clipping
        np.subtract(1.0, (1.0 - img) * (1.0 - contribution), out=img)


def vignette_mask(width: int, height: int) -> np.ndarray:
    """(H, W) float32 multiplier, 1.0 at the bright centre."""
    cx, cy = VIGNETTE_CENTER
    # normalise in the frame's own aspect so the mask is elliptical, not round
    x = ((np.arange(width, dtype=np.float32) + 0.5) / width - cx).reshape(1, width)
    y = ((np.arange(height, dtype=np.float32) + 0.5) / height - cy).reshape(height, 1)
    r = np.sqrt((x * 2.0) ** 2 + (y * 2.0) ** 2) / math.sqrt(2.0)
    return 1.0 - VIGNETTE_STRENGTH * np.power(np.clip(r, 0.0, 1.4), VIGNETTE_POWER)


def star_palette(rng: np.random.Generator, n: int) -> np.ndarray:
    """Cool-white through lavender, with a rare cool-cyan straggler."""
    anchors = np.array(
        [
            [0.92, 0.93, 1.00],  # cool white
            [0.86, 0.83, 1.00],  # lavender
            [0.99, 0.96, 0.98],  # near-neutral
            [0.78, 0.94, 1.00],  # faint cyan
        ],
        dtype=np.float32,
    )
    weights = np.array([0.44, 0.32, 0.16, 0.08], dtype=np.float32)
    idx = rng.choice(len(anchors), size=n, p=weights)
    tint = anchors[idx]
    # tiny per-star jitter so no two stars are literally the same colour
    tint = tint * (1.0 + rng.normal(0.0, 0.02, size=(n, 3)).astype(np.float32))
    return np.clip(tint, 0.0, 1.0)


def star_positions(rng: np.random.Generator, n: int) -> np.ndarray:
    """Relative [0,1] positions, thinned out toward the centre of frame."""
    out = np.empty((n, 2), dtype=np.float32)
    filled = 0
    while filled < n:
        batch = rng.random((n * 2, 2)).astype(np.float32)
        r = np.sqrt(((batch[:, 0] - 0.5) * 2) ** 2 + ((batch[:, 1] - 0.5) * 2) ** 2)
        r = np.clip(r / math.sqrt(2.0), 0.0, 1.0)
        # centre keeps ~18% of its share; the composition breathes there
        accept = 0.18 + 0.82 * smoothstep(r * 1.25)
        keep = batch[rng.random(len(batch)).astype(np.float32) < accept]
        take = min(len(keep), n - filled)
        out[filled : filled + take] = keep[:take]
        filled += take
    return out


def add_starfield(
    img: np.ndarray, vig: np.ndarray, width: int, height: int, rng: np.random.Generator
) -> None:
    """Splat sparse gaussian points. Sub-pixel placed, so no stair-stepping."""
    scale = math.sqrt(width * height) / REF_SCALE
    pos = star_positions(rng, STAR_COUNT)
    tints = star_palette(rng, STAR_COUNT)

    # size classes: mostly pinpricks, a handful of 3px stars with a halo
    roll = rng.random(STAR_COUNT).astype(np.float32)
    core = np.where(roll < 0.72, 0.40, np.where(roll < 0.965, 0.56, 0.78)) * scale
    bright = np.where(roll < 0.72, 0.40, np.where(roll < 0.965, 0.58, 0.98))
    bright = bright * (0.50 + 0.50 * rng.random(STAR_COUNT).astype(np.float32))
    haloed = roll >= 0.965

    h, w = height, width
    for i in range(STAR_COUNT):
        px = pos[i, 0] * w
        py = pos[i, 1] * h
        # edge stars stay legible: only partly subject to the vignette
        vy = min(h - 1, max(0, int(py)))
        vx = min(w - 1, max(0, int(px)))
        dim = 1.0 - 0.55 * (1.0 - float(vig[vy, vx]))
        amp = float(bright[i]) * dim
        _splat(img, px, py, float(core[i]), tints[i], amp)
        if haloed[i]:
            _splat(img, px, py, float(core[i]) * 3.4, tints[i], amp * 0.10)


def _splat(
    img: np.ndarray, px: float, py: float, sigma: float, tint: np.ndarray, amp: float
) -> None:
    """Add one gaussian dot at sub-pixel (px, py)."""
    if amp <= 0.0:
        return
    h, w = img.shape[0], img.shape[1]
    reach = max(1, int(math.ceil(sigma * 3.0)))
    x0, x1 = int(math.floor(px)) - reach, int(math.floor(px)) + reach + 1
    y0, y1 = int(math.floor(py)) - reach, int(math.floor(py)) + reach + 1
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x0 >= x1 or y0 >= y1:
        return
    gx = (np.arange(x0, x1, dtype=np.float32) + 0.5) - px
    gy = (np.arange(y0, y1, dtype=np.float32) + 0.5) - py
    d2 = (gx * gx).reshape(1, -1) + (gy * gy).reshape(-1, 1)
    g = np.exp(-d2 / (2.0 * sigma * sigma)) * amp
    patch = img[y0:y1, x0:x1]
    # screen blend again -- stars are light, not paint
    patch += (1.0 - patch) * g[:, :, None] * tint.reshape(1, 1, 3)


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def render(width: int, height: int) -> Image.Image:
    rng = np.random.default_rng(SEED)
    img = np.ascontiguousarray(
        np.broadcast_to(field(width, height), (height, width, 3)).astype(np.float32)
    )

    blobs = BLOBS_LANDSCAPE if width >= height else BLOBS_PORTRAIT
    add_nebula(img, blobs, width, height)

    vig = vignette_mask(width, height)
    img *= vig[:, :, None]

    add_starfield(img, vig, width, height, rng)

    np.clip(img, 0.0, 1.0, out=img)
    return quantize(img, rng)


def quantize(img: np.ndarray, rng: np.random.Generator) -> Image.Image:
    """Float -> 8-bit with TPDF dither.

    A near-black vertical gradient crosses a code value roughly every 90
    rows; without dither that is a stack of visible steps on any decent
    panel. Triangular noise of +/-1 LSB decorrelates the error entirely.
    """
    scaled = img * 255.0
    noise = (
        rng.random(scaled.shape, dtype=np.float32)
        + rng.random(scaled.shape, dtype=np.float32)
        - 1.0
    )
    out = np.clip(np.rint(scaled + noise), 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


# --------------------------------------------------------------------------
# package output
# --------------------------------------------------------------------------


def save_png(image: Image.Image, path: str) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, format="PNG", optimize=True, compress_level=9)
    return os.path.getsize(path)


def human(n: int) -> str:
    return f"{n / (1024 * 1024):.2f} MB"


def build(root: str) -> None:
    images_dir = os.path.join(root, PKG_DIR, "contents", "images")
    total = 0
    preview_source = None

    for width, height in LANDSCAPE_SIZES + PORTRAIT_SIZES:
        image = render(width, height)
        path = os.path.join(images_dir, f"{width}x{height}.png")
        size = save_png(image, path)
        total += size
        print(f"  {width}x{height:<5} {human(size):>9}  {path}")
        if (width, height) == (1920, 1080):
            preview_source = image

    if preview_source is None:  # pragma: no cover - sizes are fixed
        preview_source = render(1920, 1080)

    shot_h = round(SCREENSHOT_WIDTH * preview_source.height / preview_source.width)
    shot = preview_source.resize((SCREENSHOT_WIDTH, shot_h), Image.LANCZOS)
    shot_path = os.path.join(root, PKG_DIR, "contents", "screenshot.png")
    size = save_png(shot, shot_path)
    total += size
    print(f"  screenshot   {human(size):>9}  {shot_path}")
    print(f"  total        {human(total):>9}")


def check(root: str) -> int:
    """Re-open everything that was written and assert it is sane."""
    problems = []
    base = os.path.join(root, PKG_DIR)
    expected = [
        (os.path.join(base, "contents", "images", f"{w}x{h}.png"), (w, h))
        for w, h in LANDSCAPE_SIZES + PORTRAIT_SIZES
    ]
    total = 0
    for path, (w, h) in expected:
        if not os.path.exists(path):
            problems.append(f"missing {path}")
            continue
        with Image.open(path) as im:
            if im.size != (w, h):
                problems.append(f"{path}: got {im.size}, want {(w, h)}")
            if im.mode != "RGB":
                problems.append(f"{path}: mode {im.mode}, want RGB")
        total += os.path.getsize(path)
        print(f"  ok {os.path.basename(path):<16} {human(os.path.getsize(path)):>9}")

    shot = os.path.join(base, "contents", "screenshot.png")
    if not os.path.exists(shot):
        problems.append(f"missing {shot}")
    else:
        with Image.open(shot) as im:
            if im.width != SCREENSHOT_WIDTH:
                problems.append(f"{shot}: width {im.width}, want {SCREENSHOT_WIDTH}")
        total += os.path.getsize(shot)
        print(f"  ok {'screenshot.png':<16} {human(os.path.getsize(shot)):>9}")

    meta = os.path.join(base, "metadata.json")
    if not os.path.exists(meta):
        problems.append(f"missing {meta}")
    else:
        import json

        with open(meta, encoding="utf-8") as fh:
            data = json.load(fh)
        plugin = data.get("KPlugin", {})
        if plugin.get("Id") != "NX-Nebula":
            problems.append("metadata.json: KPlugin.Id must be 'NX-Nebula'")
        for key in ("Name", "License", "Authors"):
            if not plugin.get(key):
                problems.append(f"metadata.json: KPlugin.{key} missing")
        print(f"  ok {'metadata.json':<16}")

    print(f"  total {human(total)}")
    for line in problems:
        print(f"  FAIL {line}", file=sys.stderr)
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify existing output instead of writing"
    )
    parser.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="repository root (default: parent of tools/)",
    )
    args = parser.parse_args()
    if args.check:
        return check(args.root)
    build(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
