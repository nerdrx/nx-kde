# NX for KDE Plasma 6 — build brief

This repo brings the NX design language ("liquid glass on deep space", see
[DESIGN.md](DESIGN.md)) to KDE Plasma 6.7+. Every component below reads this
section first; the color mapping here is **the contract** — desktoptheme,
color scheme, aurorae, icons, cursors, SDDM and splash must all agree.

## Canonical KDE color mapping

| Role | Hex | Token |
| --- | --- | --- |
| Window background | `#171028` | `--panel` |
| Button / alternate surface | `#1d1433` | `--panel-2` |
| View (editor/list) background | `#0d0818` | well between `--bg-top` and `--panel` |
| View alternate (zebra rows) | `#120c22` | |
| Tooltip background | `#1d1433` | tier-2 sheet |
| Complementary / OSD background | `#0a0714` | `--bg-top` |
| Normal text | `#efeaff` | `--text` |
| Inactive/secondary text | `#9a8fc0` | `--muted` |
| Disabled text | `#6b6288` | muted @ ~60% |
| Selection background | `#7700ff` | `--violet` (selection text `#ffffff`) |
| Focus decoration | `#7700ff` | `--violet` |
| Hover decoration | `#9a3cff` | `--violet-soft` |
| Link | `#00e5ff` | `--cyan` |
| Visited link | `#9a3cff` | `--violet-soft` |
| Negative | `#ff5470` | `--danger` |
| Neutral / attention | `#ffb300` | `--amber` |
| Positive | `#00e5ff` | `--cyan` (NX has no green; cyan = "live/ok") |
| Separator / line | `#2a1f45` | `--line` |
| Titlebar (active) | `#171028` fg `#efeaff` | |
| Titlebar (inactive) | `#12091f` fg `#9a8fc0` | |

Rules that survive translation to every component:

- Light from the **upper-left** in every gradient, bevel, and edge.
- Violet leads; cyan is a light inside materials, never a surface color.
- No solid gray dividers — hairlines fade at both ends.
- Translucency is low-alpha; if you can see a gradient from across the room,
  halve it.
- The NX mark ([assets/icon.svg](../assets/icon.svg)) is a pointy-top hexagon,
  never flat-top. `icon-small.svg` for ≤32px rasters, `tray.svg` for
  monochrome/tinted contexts.

## Components and install targets

| Repo dir | Installs to | What |
| --- | --- | --- |
| `colors/` | `~/.local/share/color-schemes/` | `NX.colors` Qt/KDE color scheme |
| `konsole/` | `~/.local/share/konsole/` | `NX.colorscheme` terminal scheme |
| `desktoptheme/nx/` | `~/.local/share/plasma/desktoptheme/nx/` | Plasma theme (panel, dialogs, tooltips as glass) |
| `aurorae/NX/` | `~/.local/share/aurorae/themes/NX/` | Window decorations |
| `icons/NX/` | `~/.local/share/icons/NX/` | Icon theme, inherits breeze-dark |
| `cursors/NX-Cursors/` | `~/.local/share/icons/NX-Cursors/` | Cursor theme (xcursor + cursors_scalable) |
| `wallpapers/NX-Nebula/` | `~/.local/share/wallpapers/NX-Nebula/` | Generated nebula + starfield wallpaper |
| `lookandfeel/com.nerdrx.nx/` | `~/.local/share/plasma/look-and-feel/` | Global Theme package + splash |
| `sddm/nx/` | `/usr/share/sddm/themes/nx/` (root) | Login screen |

Generators live in `tools/` (Python 3, PIL + numpy, rsvg-convert). Everything
generated is committed, so users never need the toolchain to install.
