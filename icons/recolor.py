#!/usr/bin/env python3
"""
Generate the NX icon theme's colour overrides from breeze-dark.

NX inherits breeze-dark wholesale; the only icons we ship are the ones whose
identity is carried by *colour* rather than by shape:

  * the places/ folder family, whose body Breeze paints with the colour-scheme
    accent (#3daee9 blue) -> the NX violet ramp, and
  * the NX hexagon mark under the start-here / distributor-logo names.

Everything else -- monochrome action glyphs, device renders, mimetypes, the
16/22/24px monochrome folder outlines -- already follows the colour scheme and
is deliberately left inherited.

Why the body becomes a gradient instead of a recoloured accent class: Plasma
rewrites the contents of <style id="current-color-scheme"> at load time with
the active scheme's colours, so a folder that keeps class="ColorScheme-Accent"
would be painted with NX's raw accent (#7700ff) and glow radioactively. A
`fill="url(#nx-folder)"` is immune to that rewrite, which is what lets us ship
a *darkened* violet body while the scheme keeps its bright accent.

Usage:  python3 icons/recolor.py [--src /usr/share/icons/breeze-dark]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------
# colour contract (docs/BRIEF.md)
# --------------------------------------------------------------------------

# Folder body: Breeze accent blue -> NX violet ramp, lit from the upper left.
# Deliberately darker than --violet (#7700ff): a folder filled with the raw
# brand violet is a light source, not a container.
NX_BODY_TOP = "#5c19c4"   # upper-left, lit
NX_BODY_MID = "#4a1499"
NX_BODY_BOT = "#3d1478"   # lower-right, in shadow

NX_TEXT = "#efeaff"       # --text, engraved folder glyphs
NX_CYAN = "#00e5ff"       # --cyan, glyphs on "live / connected" folders only
NX_ACCENT_FALLBACK = "#5c19c4"

GRADIENT_ID = "nx-folder"
GRADIENT = (
    f'<linearGradient id="{GRADIENT_ID}" x1="0" y1="0" x2="0.82" y2="1">'
    f'<stop offset="0" stop-color="{NX_BODY_TOP}"/>'
    f'<stop offset="0.55" stop-color="{NX_BODY_MID}"/>'
    f'<stop offset="1" stop-color="{NX_BODY_BOT}"/>'
    f"</linearGradient>"
)

# Folders that mean "somewhere else, and it is live": cyan is the light inside
# the material, per DESIGN.md 5 (cyan = live/connected). Everything else keeps
# a lavender engraving so violet stays the lead.
CYAN_GLYPH = {
    "folder-cloud.svg",
    "folder-gdrive.svg",
    "folder-network.svg",
    "folder-publicshare.svg",
    "network-workgroup.svg",
}

# Breeze paints these with a hard-coded fill instead of the accent class, but
# they are still folder bodies and still off-palette for NX.
EXTRA_BODY_FILLS = {
    "folder-trash.svg": "#3bad7e",   # NX has no green
}

# user-desktop is a little monitor showing the *Breeze* wallpaper -- two teal
# and magenta triangles. It sits in Dolphin's Places list right next to the
# violet folders, so it gets NX's field instead: a violet glow in the upper
# left draining into deep space, with the frame retinted off its Breeze green.
LITERAL_MAPS = {
    "user-desktop.svg": {
        "#1abc9c": "#7a2ce6",   # wallpaper, lit
        "#2980b9": "#4614a0",
        "#4ce0c6": "#8a3cf0",   # ...the 32px file uses brighter teals
        "#3b85b5": "#4614a0",
        "#cc4a5e": "#2a1354",   # wallpaper, in shadow
        "#aa478a": "#150c2c",
        "#536161": "#241a44",   # monitor frame, lit
        "#334545": "#150e2b",   # monitor frame, in shadow
        "#4d4d4d": "#221a3c",   # panel bar
    },
}

# Manual folder colours the user picks in Dolphin (folder-red, folder-green...)
# are left inherited: they are a user choice, not theme identity.
PLACE_SIZES = ("32", "48", "64", "96")

# DESIGN.md 8: the master mark is never scaled below 48px -- below that the
# bevel, the well and the cyan fringe collapse into one smudge. 16/22/24/32 get
# the small variant (wider hexagon, flat monogram); -symbolic names, which land
# in tinted contexts, get the tray variant (flat violet, knocked-out monogram).
# Breeze's 16/22/24 places dirs are monochrome-only by design, so the mark is
# the only thing we add there.
MARK_SMALL_SIZES = ("16", "22", "24", "32")
MARK_MASTER_SIZES = ("48", "64", "96")

STARTHERE_COLOR = "start-here-kde.svg"          # canonical colour name
STARTHERE_COLOR_ALIASES = [
    "start-here.svg",
    "start-here-kde-plasma.svg",
]
STARTHERE_SYMBOLIC = "start-here-kde-symbolic.svg"
STARTHERE_SYMBOLIC_ALIASES = [
    "start-here-symbolic.svg",
    "start-here-kde-plasma-symbolic.svg",
]

TAG_RE = re.compile(r'<([A-Za-z][\w:.-]*)((?:[^<>"]|"[^"]*")*?)(/?)>', re.S)


def has_accent_body(text: str) -> bool:
    """True if some element is painted with the colour scheme's accent."""
    for m in TAG_RE.finditer(text):
        attrs = m.group(2)
        cls = CLASS_RE.search(attrs)
        style = STYLE_RE.search(attrs)
        if (cls and "ColorScheme-Accent" in cls.group(1)
                and style and "fill:currentColor" in style.group(1)):
            return True
    return False

CLASS_RE = re.compile(r'\s*class="([^"]*)"')
STYLE_RE = re.compile(r'style="([^"]*)"')


# --------------------------------------------------------------------------
# recolour
# --------------------------------------------------------------------------

def _strip_class(attrs: str) -> str:
    return CLASS_RE.sub("", attrs)


def _set_fill(attrs: str, value: str) -> str:
    """Replace fill:currentColor inside the style attribute."""
    def repl(m: re.Match) -> str:
        return 'style="%s"' % m.group(1).replace("fill:currentColor", f"fill:{value}")
    return STYLE_RE.sub(repl, attrs, count=1)


def recolor_literal(text: str, name: str) -> tuple[str, dict]:
    """Straight hex-for-hex substitution, for illustrations that have no
    folder body to gradient-fill (see LITERAL_MAPS)."""
    stats = {"body": 0, "glyph": 0}
    for old, new in LITERAL_MAPS[name].items():
        for spelling in (old, old.upper()):
            if spelling in text:
                stats["body"] += text.count(spelling)
                text = text.replace(spelling, new)
    if not stats["body"]:
        raise ValueError(f"{name}: literal map matched nothing")
    return text, stats


def recolor(text: str, name: str) -> tuple[str, dict]:
    """Return (recoloured svg, stats). Raises if nothing matched."""
    if name in LITERAL_MAPS:
        return recolor_literal(text, name)

    stats = {"body": 0, "glyph": 0}
    glyph_color = NX_CYAN if name in CYAN_GLYPH else NX_TEXT
    hard_body = EXTRA_BODY_FILLS.get(name)

    def handle(m: re.Match) -> str:
        tag, attrs, close = m.group(1), m.group(2), m.group(3)
        cls = CLASS_RE.search(attrs)
        cls = cls.group(1) if cls else ""
        style = STYLE_RE.search(attrs)
        style = style.group(1) if style else ""

        # 1. the folder body -- Breeze's accent-coloured shape
        if "ColorScheme-Accent" in cls and "fill:currentColor" in style:
            stats["body"] += 1
            return f"<{tag}{_strip_class(_set_fill(attrs, f'url(#{GRADIENT_ID})'))}{close}>"

        # 1b. bodies Breeze hard-codes off-accent (folder-trash's green).
        #     96px places are authored with presentation attributes rather
        #     than a style attribute, so handle both spellings.
        if hard_body:
            if f"fill:{hard_body}" in style:
                stats["body"] += 1
                attrs2 = STYLE_RE.sub(
                    lambda mm: 'style="%s"' % mm.group(1).replace(
                        f"fill:{hard_body}", f"fill:url(#{GRADIENT_ID})"),
                    attrs, count=1)
                return f"<{tag}{attrs2}{close}>"
            if f'fill="{hard_body}"' in attrs:
                stats["body"] += 1
                attrs2 = attrs.replace(f'fill="{hard_body}"',
                                       f'fill="url(#{GRADIENT_ID})"', 1)
                return f"<{tag}{attrs2}{close}>"

        # 2. the engraved emblem inside the folder
        if ("ColorScheme-Text" in cls
                and "fill:currentColor" in style
                and "fill-opacity:0.6" in style):
            stats["glyph"] += 1
            return f"<{tag}{_strip_class(_set_fill(attrs, glyph_color))}{close}>"

        return m.group(0)

    out = TAG_RE.sub(handle, text)

    if not stats["body"]:
        raise ValueError(f"{name}: no folder body found")

    # 3. keep the stylesheet in-palette for anything we did not rewrite. Plasma
    #    overwrites this block at runtime; it is a static-render fallback only.
    out = out.replace(".ColorScheme-Accent { color: #3daee9; }",
                      f".ColorScheme-Accent {{ color: {NX_ACCENT_FALLBACK}; }}")
    out = out.replace(".ColorScheme-Text { color: #fcfcfc; }",
                      f".ColorScheme-Text {{ color: {NX_TEXT}; }}")

    # 4. inject the ramp
    m = re.search(r"<defs\b[^>]*>", out)
    if not m:
        raise ValueError(f"{name}: no <defs> to hold the gradient")
    out = out[: m.end()] + "\n    " + GRADIENT + out[m.end():]
    return out, stats


# --------------------------------------------------------------------------
# the mark
# --------------------------------------------------------------------------

def make_mark(src: Path, size: str | None) -> str:
    """Adapt one of assets/*.svg into an icon-theme SVG."""
    svg = src.read_text()
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)          # drop the essay
    svg = re.sub(r"<title>.*?</title>\s*", "", svg, flags=re.S)
    svg = re.sub(r'\s(?:width|height)="\d+"', "", svg, count=2)
    if size:
        svg = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    svg = re.sub(r"\n\s*\n+", "\n", svg)
    return svg.strip() + "\n"


def link(dst_dir: Path, alias: str, target: str) -> None:
    p = dst_dir / alias
    if p.is_symlink() or p.exists():
        p.unlink()
    os.symlink(target, p)


# --------------------------------------------------------------------------

def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/usr/share/icons/breeze-dark", type=Path)
    ap.add_argument("--assets", default=here.parent / "assets", type=Path)
    ap.add_argument("--dst", default=here / "NX", type=Path)
    args = ap.parse_args()

    src_places = args.src / "places"
    if not src_places.is_dir():
        print(f"breeze-dark not found at {args.src}", file=sys.stderr)
        return 1

    dst_places = args.dst / "places"
    if dst_places.exists():
        shutil.rmtree(dst_places)

    total_files = total_links = 0
    for size in PLACE_SIZES:
        sdir = src_places / size
        if not sdir.is_dir():
            continue
        ddir = dst_places / size
        ddir.mkdir(parents=True, exist_ok=True)

        # pass 1 -- real files whose colour we own
        shipped: set[str] = set()
        for f in sorted(sdir.iterdir()):
            if f.is_symlink() or f.suffix != ".svg":
                continue
            text = f.read_text()
            # Some folders (folder-deb, folder-rpm...) carry the accent class
            # but override it with a hard-coded brand fill. Those are somebody
            # else's identity -- like the user-picked folder-red family -- and
            # stay inherited. We only own bodies that actually paint with the
            # colour scheme's accent.
            wanted = (has_accent_body(text)
                      or f.name in EXTRA_BODY_FILLS
                      or f.name in LITERAL_MAPS)
            if not wanted:
                continue
            out, stats = recolor(text, f.name)
            (ddir / f.name).write_text(out)
            shipped.add(f.name)
            total_files += 1

        # pass 2 -- rebuild Breeze's aliases as symlinks, not copies. Breeze
        # chains some of them (library-music -> folder-music -> folder-sound),
        # so keep resolving until nothing new lands.
        links = {f.name: os.readlink(f)
                 for f in sorted(sdir.iterdir()) if f.is_symlink()}
        added = True
        while added:
            added = False
            for name, target in links.items():
                if name in shipped or target not in shipped:
                    continue
                link(ddir, name, target)
                shipped.add(name)
                total_links += 1
                added = True

    # ---- the NX mark -------------------------------------------------
    master = args.assets / "icon.svg"
    small = args.assets / "icon-small.svg"
    tray = args.assets / "tray.svg"

    for size in MARK_MASTER_SIZES:
        ddir = dst_places / size
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / STARTHERE_COLOR).write_text(make_mark(master, size))
        for alias in STARTHERE_COLOR_ALIASES:
            link(ddir, alias, STARTHERE_COLOR)
        total_files += 1
        total_links += len(STARTHERE_COLOR_ALIASES)

    for size in MARK_SMALL_SIZES:
        ddir = dst_places / size
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / STARTHERE_COLOR).write_text(make_mark(small, size))
        for alias in STARTHERE_COLOR_ALIASES:
            link(ddir, alias, STARTHERE_COLOR)
        # -symbolic names live in tinted contexts -> the tray variant.
        (ddir / STARTHERE_SYMBOLIC).write_text(make_mark(tray, size))
        for alias in STARTHERE_SYMBOLIC_ALIASES:
            link(ddir, alias, STARTHERE_SYMBOLIC)
        total_files += 2
        total_links += len(STARTHERE_COLOR_ALIASES) + len(STARTHERE_SYMBOLIC_ALIASES)

    apps48 = args.dst / "apps" / "48"
    if apps48.exists():
        shutil.rmtree(apps48)
    apps48.mkdir(parents=True, exist_ok=True)
    (apps48 / "start-here.svg").write_text(make_mark(master, None))
    for alias in ["start-here-kde.svg", "start-here-kde-plasma.svg",
                  "start-here-kde-symbolic.svg", "start-here-symbolic.svg",
                  "start-here-kde-plasma-symbolic.svg", "nx.svg"]:
        link(apps48, alias, "start-here.svg")
    total_files += 1
    total_links += 6

    # ---- verify ------------------------------------------------------
    bad = 0
    for p in sorted(args.dst.rglob("*.svg")):
        if p.is_symlink():
            if not p.resolve().exists():
                print(f"broken symlink: {p}", file=sys.stderr)
                bad += 1
            continue
        try:
            ET.parse(p)
        except ET.ParseError as e:
            print(f"malformed: {p}: {e}", file=sys.stderr)
            bad += 1

    print(f"wrote {total_files} svg + {total_links} symlinks; {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
