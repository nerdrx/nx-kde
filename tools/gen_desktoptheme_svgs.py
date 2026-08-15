#!/usr/bin/env python3
"""Generate the NX Plasma desktop theme frame SVGs.

Layout mirrors Breeze's 9-slice frame SVGs:
  frame tile   : (0, TY) .. (T, TY+T)          T = 2*R + 32
  shadow tile  : (SX, 0) .. (SX+T+20, T+20)    ring = 10 around a copy of the frame
  mask tile    : (MX, TY) .. (MX+T, TY+T)      opaque silhouette -> KWin blur region

All gradients use gradientUnits="userSpaceOnUse" in absolute document
coordinates, so every 9-slice piece automatically samples the correct slice of
one continuous fill/light ramp even though FrameSvg renders each piece on its
own.  Fills are hardcoded NX colors: no current-color-scheme stylesheet hookup.
"""
import os

OUT = "/run/media/nerdrx/Lex/claude/nx-kde/desktoptheme/nx"

TY = 10          # frame tile top
RING = 10        # shadow ring width
CEN = 32         # center tile size

# ---------------------------------------------------------------- geometry --


class Geo:
    def __init__(self, r):
        self.r = r
        self.T = 2 * r + CEN            # frame tile edge length
        self.fx = 0
        self.fy = TY
        self.sx = 51 if r == 8 else 47  # shadow tile left
        self.sfx = self.sx + RING       # shadow's copy of the frame, left
        self.mx = self.sx + self.T + 2 * RING + 3   # mask tile left
        self.W = self.mx + self.T
        self.H = TY + self.T + RING


def corner_fill(bx, by, r, which):
    """Filled rounded-corner wedge occupying the r x r corner box at (bx,by)."""
    if which == "topleft":
        return f"M {bx},{by+r} H {bx+r} V {by} A {r},{r} 0 0 0 {bx},{by+r} Z"
    if which == "topright":
        return f"M {bx},{by} V {by+r} H {bx+r} A {r},{r} 0 0 0 {bx},{by} Z"
    if which == "bottomleft":
        return f"M {bx+r},{by+r} V {by} H {bx} A {r},{r} 0 0 0 {bx+r},{by+r} Z"
    return f"M {bx},{by+r} V {by} H {bx+r} A {r},{r} 0 0 1 {bx},{by+r} Z"


def corner_arc(bx, by, r, which, w=1):
    """1px lit edge following a corner's outer curve, as a *filled* crescent.

    A stroked path would make QSvgRenderer report bounds inflated by half the
    stroke width (8.5x8.5 for an 8px corner); FrameSvg then squashes the corner
    into its 8x8 slot and leaves a seam against the adjacent border.  Filling
    the crescent keeps the element's bounds exactly r x r.
    """
    q = r - w
    if which == "topleft":
        return (f"M {bx+r},{by} A {r},{r} 0 0 0 {bx},{by+r} H {bx+w} "
                f"A {q},{q} 0 0 1 {bx+r},{by+w} Z")
    if which == "topright":
        return (f"M {bx+r},{by+r} A {r},{r} 0 0 0 {bx},{by} V {by+w} "
                f"A {q},{q} 0 0 1 {bx+r-w},{by+r} Z")
    if which == "bottomleft":
        return (f"M {bx},{by} A {r},{r} 0 0 0 {bx+r},{by+r} V {by+r-w} "
                f"A {q},{q} 0 0 1 {bx+w},{by} Z")
    return (f"M {bx+r},{by} A {r},{r} 0 0 1 {bx},{by+r} V {by+r-w} "
            f"A {q},{q} 0 0 0 {bx+r-w},{by} Z")


def shadow_corner(bx, by, r, which):
    """L-shaped shadow region: the (r+RING) box minus the rounded wedge."""
    k = RING
    if which == "topleft":
        # corner box (bx,by)-(bx+r,by+r); ring extends up/left
        return (f"M {bx+r},{by} A {r},{r} 0 0 0 {bx},{by+r} "
                f"H {bx-k} V {by-k} H {bx+r} Z")
    if which == "topright":
        return (f"M {bx},{by} A {r},{r} 0 0 1 {bx+r},{by+r} "
                f"H {bx+r+k} V {by-k} H {bx} Z")
    if which == "bottomleft":
        return (f"M {bx},{by} A {r},{r} 0 0 0 {bx+r},{by+r} "
                f"V {by+r+k} H {bx-k} V {by} Z")
    return (f"M {bx+r},{by} A {r},{r} 0 0 1 {bx},{by+r} "
            f"V {by+r+k} H {bx+r+k} V {by} Z")


# ------------------------------------------------------------------ colors --

def rgba(r, g, b, a):
    return f"rgb({r},{g},{b})", f"{a}"


def stop(off, col, alpha):
    return f'      <stop offset="{off}" stop-color="{col}" stop-opacity="{alpha}"/>'


# quadratic falloff shared by shadow sides and corners
FALLOFF = [(0.0, 1.0), (0.30, 0.49), (0.60, 0.16), (1.0, 0.0)]


def shadow_side_grad(gid, x1, y1, x2, y2, amax):
    """Gradient running from the frame edge (full) to the outer edge (zero)."""
    s = [f'    <linearGradient id="{gid}" gradientUnits="userSpaceOnUse"'
         f' x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">']
    for off, k in FALLOFF:
        s.append(stop(round(off, 4), "#000000", round(amax * k, 5)))
    s.append("    </linearGradient>")
    return "\n".join(s)


def shadow_corner_grad(gid, cx, cy, r, amax):
    inner = r / (r + RING)
    s = [f'    <radialGradient id="{gid}" gradientUnits="userSpaceOnUse"'
         f' cx="{cx}" cy="{cy}" r="{r + RING}">']
    s.append(stop(0, "#000000", round(amax, 5)))
    for off, k in FALLOFF:
        o = inner + off * (1.0 - inner)
        s.append(stop(round(o, 4), "#000000", round(amax * k, 5)))
    s.append("    </radialGradient>")
    return "\n".join(s)


# fill ramps, expressed as (offset, "#rrggbb", alpha)
RAMP = {
    "panel": [(0.0, "#2e1e4e", 0.62), (1.0, "#120b22", 0.72)],
    "dialog": [(0.0, "#22183a", 0.90), (0.34, "#19112b", 0.905), (1.0, "#120c20", 0.93)],
    "tooltip": [(0.0, "#2a1e48", 0.90), (0.34, "#1f1637", 0.905), (1.0, "#170f2a", 0.93)],
}
SOLID = {"panel": "#171028", "dialog": "#171028", "tooltip": "#1d1433"}

# diagonal white->black sheen (light collects upper-left, drains lower-right)
SHEEN = {
    "panel": [(0.0, "#ffffff", 0.055), (0.30, "#ffffff", 0.014),
              (0.62, "#ffffff", 0.0), (1.0, "#000000", 0.06)],
    "dialog": [(0.0, "#ffffff", 0.075), (0.26, "#ffffff", 0.022),
               (0.58, "#ffffff", 0.0), (1.0, "#000000", 0.05)],
    "tooltip": [(0.0, "#ffffff", 0.07), (0.26, "#ffffff", 0.02),
                (0.58, "#ffffff", 0.0), (1.0, "#000000", 0.045)],
}

# --edge-lit: lavender -> violet -> cyan -> shadow, around the whole sheet
EDGE_LIT = [(0.0, "#e2c8ff", 0.62), (0.24, "#9a3cff", 0.30),
            (0.52, "#00e5ff", 0.10), (1.0, "#000000", 0.30)]


def lin(gid, x1, y1, x2, y2, stops, scale=1.0):
    s = [f'    <linearGradient id="{gid}" gradientUnits="userSpaceOnUse"'
         f' x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">']
    for off, col, a in stops:
        s.append(stop(off, col, round(a * scale, 5)))
    s.append("    </linearGradient>")
    return "\n".join(s)


# ------------------------------------------------------------------ writer --

def build(kind, variant):
    r = 6 if kind == "tooltip" else 8
    g = Geo(r)
    T, fy = g.T, g.fy
    x0, x1 = 0, T
    y0, y1 = fy, fy + T
    ci, cj = r, T - r                      # center box offsets within the tile
    has_shadow = variant != "opaque"
    has_inset = variant != "opaque"
    flat = variant in ("solid", "opaque")

    d, b = [], []                          # defs, body

    # ---- fills -----------------------------------------------------------
    if flat:
        base = SOLID[kind]
        fill = f'fill="{base}"'
    else:
        d.append(lin("nx-fill", 0, y0, 0, y1, RAMP[kind]))
        d.append(lin("nx-sheen", x0, y0, x1, y1, SHEEN[kind]))
        fill = 'fill="url(#nx-fill)"'
    edge_scale = 0.62 if flat else 1.0
    if kind == "panel":
        # bar tier: 1px light top edge, cool edges elsewhere
        d.append(lin("nx-edge-v", 0, y0, 0, y1,
                     [(0.0, "#ffffff", 0.14), (1.0, "#ffffff", 0.02)], edge_scale))
        d.append(lin("nx-edge-vr", 0, y0, 0, y1,
                     [(0.0, "#000000", 0.10), (1.0, "#000000", 0.20)]))
        top_edge = f'fill="#ffffff" fill-opacity="{0.18 * edge_scale:.3f}"'
        tl_arc = f'fill="#ffffff" fill-opacity="{0.24 * edge_scale:.3f}"'
        tr_arc = f'fill="#ffffff" fill-opacity="{0.13 * edge_scale:.3f}"'
        left_edge = 'fill="url(#nx-edge-v)"'
        right_edge = 'fill="url(#nx-edge-vr)"'
        bot_edge = 'fill="#000000" fill-opacity="0.22"'
        bl_arc = br_arc = 'fill="#000000" fill-opacity="0.16"'
    else:
        d.append(lin("nx-edge-lit", x0, y0, x1, y1, EDGE_LIT, edge_scale))
        top_edge = left_edge = right_edge = bot_edge = 'fill="url(#nx-edge-lit)"'
        tl_arc = tr_arc = bl_arc = br_arc = 'fill="url(#nx-edge-lit)"'

    def piece(pid, px, py, pw, ph, extra=""):
        s = [f'  <g id="{pid}">',
             f'    <rect x="{px}" y="{py}" width="{pw}" height="{ph}" {fill}/>']
        if not flat:
            s.append(f'    <rect x="{px}" y="{py}" width="{pw}" height="{ph}"'
                     f' fill="url(#nx-sheen)"/>')
        if extra:
            s.append(extra)
        s.append('  </g>')
        return "\n".join(s)

    def cpiece(pid, bx, by, which, arc_style, arc_op=True):
        s = [f'  <g id="{pid}">',
             f'    <path d="{corner_fill(bx, by, r, which)}" {fill}/>']
        if not flat:
            s.append(f'    <path d="{corner_fill(bx, by, r, which)}"'
                     f' fill="url(#nx-sheen)"/>')
        if arc_op:
            s.append(f'    <path d="{corner_arc(bx, by, r, which)}" {arc_style}/>')
        s.append('  </g>')
        return "\n".join(s)

    # ---- visible frame ---------------------------------------------------
    b.append("  <!-- frame -->")
    b.append(cpiece("topleft", x0, y0, "topleft", tl_arc))
    b.append(piece("top", ci, y0, CEN, r,
                   f'    <rect x="{ci}" y="{y0}" width="{CEN}" height="1" {top_edge}/>'))
    b.append(cpiece("topright", cj, y0, "topright", tr_arc))
    b.append(piece("left", x0, y0 + r, r, CEN,
                   f'    <rect x="{x0}" y="{y0+r}" width="1" height="{CEN}" {left_edge}/>'))
    b.append(piece("center", ci, y0 + r, CEN, CEN))
    b.append(piece("right", cj, y0 + r, r, CEN,
                   f'    <rect x="{x1-1}" y="{y0+r}" width="1" height="{CEN}" {right_edge}/>'))
    b.append(cpiece("bottomleft", x0, y1 - r, "bottomleft", bl_arc))
    b.append(piece("bottom", ci, y1 - r, CEN, r,
                   f'    <rect x="{ci}" y="{y1-1}" width="{CEN}" height="1" {bot_edge}/>'))
    b.append(cpiece("bottomright", cj, y1 - r, "bottomright", br_arc))

    # ---- stretch hint ----------------------------------------------------
    # FrameSvg TILES border elements by default (paintBorder ->
    # drawTiledPixmap at the element's natural size) and only stretches them
    # when this marker exists. Our borders carry gradients along their run
    # axis, so tiling re-samples the ramp every 32px and scallops the edge.
    # Presence is all that is checked; position and fill are irrelevant.
    # (The centre is the opposite: stretched unless hint-tile-center exists.)
    b.append("  <!-- hints (never painted; only presence/bounds are read) -->")
    b.append('  <rect id="hint-stretch-borders" x="0" y="0" width="5" height="5" fill="#008000"/>')

    # ---- content margin / inset hints ------------------------------------
    m = 4
    b.append(f'  <rect id="hint-top-margin" x="20" y="{y0}" width="{m}" height="{m}" fill="#ff00ff"/>')
    b.append(f'  <rect id="hint-bottom-margin" x="20" y="{y1-m}" width="{m}" height="{m}" fill="#ff00ff"/>')
    b.append(f'  <rect id="hint-left-margin" x="{x0}" y="{y0+T//2-2}" width="{m}" height="{m}" fill="#ff00ff"/>')
    b.append(f'  <rect id="hint-right-margin" x="{x1-m}" y="{y0+T//2-2}" width="{m}" height="{m}" fill="#ff00ff"/>')
    if has_inset:
        z = "0.00000001"
        b.append(f'  <rect id="hint-top-inset" x="20" y="{y0}" width="{m}" height="{z}" fill="#00ff00"/>')
        b.append(f'  <rect id="hint-bottom-inset" x="20" y="{y1}" width="{m}" height="{z}" fill="#00ff00"/>')
        b.append(f'  <rect id="hint-left-inset" x="{x0}" y="{y0+T//2-2}" width="{z}" height="{m}" fill="#00ff00"/>')
        b.append(f'  <rect id="hint-right-inset" x="{x1}" y="{y0+T//2-2}" width="{z}" height="{m}" fill="#00ff00"/>')

    # ---- thick-panel variant (panel-background only) ---------------------
    if kind == "panel":
        ty = y1 + 2 * RING + 4
        d.append(lin("nx-fill-thick", 0, ty, 0, ty + CEN,
                     RAMP["panel"] if not flat else [(0.0, SOLID["panel"], 1.0),
                                                     (1.0, SOLID["panel"], 1.0)]))
        b.append("  <!-- thick panel -->")
        b.append(f'  <rect id="thick-center" x="{ci}" y="{ty}" width="{CEN}"'
                 f' height="{CEN}" fill="url(#nx-fill-thick)"/>')
        b.append(f'  <rect id="thick-hint-top-margin" x="{ci}" y="{ty-8}" width="4" height="8" fill="#800080"/>')
        b.append(f'  <rect id="thick-hint-bottom-margin" x="{ci+8}" y="{ty+CEN}" width="4" height="8" fill="#800080"/>')
        b.append(f'  <rect id="thick-hint-left-margin" x="{x0}" y="{ty}" width="8" height="4" fill="#800080"/>')
        b.append(f'  <rect id="thick-hint-right-margin" x="{x1}" y="{ty}" width="8" height="4" fill="#800080"/>')

    # ---- blur/contrast mask silhouette -----------------------------------
    mx, my = g.mx, y0
    mj = mx + T - r
    b.append("  <!-- mask: opaque silhouette, gives KWin the blur-behind region -->")
    b.append(f'  <path id="mask-topleft" d="{corner_fill(mx, my, r, "topleft")}" fill="#000000"/>')
    b.append(f'  <rect id="mask-top" x="{mx+r}" y="{my}" width="{CEN}" height="{r}" fill="#000000"/>')
    b.append(f'  <path id="mask-topright" d="{corner_fill(mj, my, r, "topright")}" fill="#000000"/>')
    b.append(f'  <rect id="mask-left" x="{mx}" y="{my+r}" width="{r}" height="{CEN}" fill="#000000"/>')
    b.append(f'  <rect id="mask-center" x="{mx+r}" y="{my+r}" width="{CEN}" height="{CEN}" fill="#000000"/>')
    b.append(f'  <rect id="mask-right" x="{mj}" y="{my+r}" width="{r}" height="{CEN}" fill="#000000"/>')
    b.append(f'  <path id="mask-bottomleft" d="{corner_fill(mx, my+T-r, r, "bottomleft")}" fill="#000000"/>')
    b.append(f'  <rect id="mask-bottom" x="{mx+r}" y="{my+T-r}" width="{CEN}" height="{r}" fill="#000000"/>')
    b.append(f'  <path id="mask-bottomright" d="{corner_fill(mj, my+T-r, r, "bottomright")}" fill="#000000"/>')

    # ---- drop shadow -----------------------------------------------------
    if has_shadow:
        sx = g.sfx                 # shadow's frame, left edge
        sj = sx + T - r
        sy0, sy1 = y0, y0 + T
        A = {"top": 0.15, "left": 0.15, "right": 0.22, "bottom": 0.30}
        C = {"topleft": 0.15, "topright": 0.22, "bottomleft": 0.22, "bottomright": 0.30}
        d.append(shadow_side_grad("nx-sh-top", 0, sy0, 0, sy0 - RING, A["top"]))
        d.append(shadow_side_grad("nx-sh-bottom", 0, sy1, 0, sy1 + RING, A["bottom"]))
        d.append(shadow_side_grad("nx-sh-left", sx, 0, sx - RING, 0, A["left"]))
        d.append(shadow_side_grad("nx-sh-right", sx + T, 0, sx + T + RING, 0, A["right"]))
        d.append(shadow_corner_grad("nx-shc-topleft", sx + r, sy0 + r, r, C["topleft"]))
        d.append(shadow_corner_grad("nx-shc-topright", sj, sy0 + r, r, C["topright"]))
        d.append(shadow_corner_grad("nx-shc-bottomleft", sx + r, sy1 - r, r, C["bottomleft"]))
        d.append(shadow_corner_grad("nx-shc-bottomright", sj, sy1 - r, r, C["bottomright"]))
        PAD = 'fill="#000000" fill-opacity="0.001"'
        b.append("  <!-- shadow (the 0.001-alpha rects only pad element bounds) -->")
        b.append(f'  <g id="shadow-topleft">\n'
                 f'    <path d="{shadow_corner(sx, sy0, r, "topleft")}" fill="url(#nx-shc-topleft)"/>\n'
                 f'    <path d="{corner_fill(sx, sy0, r, "topleft")}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-top">\n'
                 f'    <rect x="{sx+r}" y="{sy0-RING}" width="{CEN}" height="{RING}" fill="url(#nx-sh-top)"/>\n'
                 f'    <rect x="{sx+r}" y="{sy0}" width="{CEN}" height="{r}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-topright">\n'
                 f'    <path d="{shadow_corner(sj, sy0, r, "topright")}" fill="url(#nx-shc-topright)"/>\n'
                 f'    <path d="{corner_fill(sj, sy0, r, "topright")}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-left">\n'
                 f'    <rect x="{sx-RING}" y="{sy0+r}" width="{RING}" height="{CEN}" fill="url(#nx-sh-left)"/>\n'
                 f'    <rect x="{sx}" y="{sy0+r}" width="{r}" height="{CEN}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-center">\n'
                 f'    <rect x="{sx+r}" y="{sy0+r}" width="{CEN}" height="{CEN}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-right">\n'
                 f'    <rect x="{sx+T}" y="{sy0+r}" width="{RING}" height="{CEN}" fill="url(#nx-sh-right)"/>\n'
                 f'    <rect x="{sj}" y="{sy0+r}" width="{r}" height="{CEN}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-bottomleft">\n'
                 f'    <path d="{shadow_corner(sx, sy1-r, r, "bottomleft")}" fill="url(#nx-shc-bottomleft)"/>\n'
                 f'    <path d="{corner_fill(sx, sy1-r, r, "bottomleft")}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-bottom">\n'
                 f'    <rect x="{sx+r}" y="{sy1}" width="{CEN}" height="{RING}" fill="url(#nx-sh-bottom)"/>\n'
                 f'    <rect x="{sx+r}" y="{sy1-r}" width="{CEN}" height="{r}" {PAD}/>\n  </g>')
        b.append(f'  <g id="shadow-bottomright">\n'
                 f'    <path d="{shadow_corner(sj, sy1-r, r, "bottomright")}" fill="url(#nx-shc-bottomright)"/>\n'
                 f'    <path d="{corner_fill(sj, sy1-r, r, "bottomright")}" {PAD}/>\n  </g>')
        b.append("  <!-- shadow margin/inset hints -->")
        hx = sx + T // 2
        b.append(f'  <rect id="shadow-hint-top-margin" x="{hx}" y="0" width="2" height="{RING}" fill="#ff00ff"/>')
        b.append(f'  <rect id="shadow-hint-bottom-margin" x="{hx}" y="{sy1}" width="2" height="{RING}" fill="#ff00ff"/>')
        b.append(f'  <rect id="shadow-hint-left-margin" x="{sx-RING}" y="{sy0+10}" width="{RING}" height="2" fill="#ff00ff"/>')
        b.append(f'  <rect id="shadow-hint-right-margin" x="{sx+T}" y="{sy0+14}" width="{RING}" height="2" fill="#ff00ff"/>')
        b.append(f'  <rect id="shadow-hint-top-inset" x="{hx+4}" y="0" width="2" height="{RING}" fill="#00ff00"/>')
        b.append(f'  <rect id="shadow-hint-bottom-inset" x="{hx+4}" y="{sy1}" width="2" height="{RING}" fill="#00ff00"/>')
        b.append(f'  <rect id="shadow-hint-left-inset" x="{sx-RING}" y="{sy0+14}" width="{RING}" height="2" fill="#00ff00"/>')
        b.append(f'  <rect id="shadow-hint-right-inset" x="{sx+T}" y="{sy0+10}" width="{RING}" height="2" fill="#00ff00"/>')

    W, H = g.W, g.H
    title = {"panel": "NX panel background", "dialog": "NX dialog background",
             "tooltip": "NX tooltip background"}[kind]
    label = {"default": "translucent glass", "solid": "solid",
             "opaque": "opaque (no compositing)"}[variant]
    head = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"'
            f' width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
            f'  <title>{title} — {label}</title>\n'
            f'  <defs>\n' + "\n".join(d) + '\n  </defs>\n')
    return head + "\n".join(b) + "\n</svg>\n"


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)
    print("wrote", path, len(text))


TARGETS = {"panel": "widgets/panel-background.svg",
           "dialog": "dialogs/background.svg",
           "tooltip": "widgets/tooltip.svg"}

for kind, rel in TARGETS.items():
    glass = build(kind, "default")
    write(rel, glass)
    write("translucent/" + rel, glass)
    write("solid/" + rel, build(kind, "solid"))
    write("opaque/" + rel, build(kind, "opaque"))
