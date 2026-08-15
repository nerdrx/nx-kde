#!/usr/bin/env bash
# NX for KDE Plasma 6 — installer
# Installs everything user-local (no root). The SDDM login theme is system-wide
# and optional: rerun with --sddm to install it via sudo.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPLY=0
SDDM=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --sddm) SDDM=1 ;;
    -h|--help)
      echo "Usage: ./install.sh [--apply] [--sddm]"
      echo "  --apply  switch the current session to NX after installing"
      echo "  --sddm   also install the login screen theme (needs sudo)"
      exit 0 ;;
    *) echo "Unknown option: $arg (see --help)"; exit 1 ;;
  esac
done

say() { printf '\033[38;5;93m::\033[0m %s\n' "$1"; }

say "Installing NX components to $DATA"

install -Dm644 "$HERE/colors/NX.colors" "$DATA/color-schemes/NX.colors"
say "color scheme"

install -Dm644 "$HERE/konsole/NX.colorscheme" "$DATA/konsole/NX.colorscheme"
say "konsole scheme"

mkdir -p "$DATA/plasma/desktoptheme" "$DATA/plasma/look-and-feel" \
         "$DATA/aurorae/themes" "$DATA/icons" "$DATA/wallpapers"
cp -r "$HERE/desktoptheme/nx"              "$DATA/plasma/desktoptheme/" && say "plasma theme"
cp -r "$HERE/aurorae/NX"                   "$DATA/aurorae/themes/"      && say "window decorations"
cp -r "$HERE/icons/NX"                     "$DATA/icons/"               && say "icon theme"
cp -r "$HERE/cursors/NX-Cursors"           "$DATA/icons/"               && say "cursor theme"
cp -r "$HERE/wallpapers/NX-Nebula"         "$DATA/wallpapers/"          && say "wallpaper"
cp -r "$HERE/lookandfeel/com.nerdrx.nx"    "$DATA/plasma/look-and-feel/" && say "global theme + splash"

if [ "$SDDM" -eq 1 ]; then
  say "Installing SDDM theme (sudo)"
  sudo mkdir -p /usr/share/sddm/themes
  sudo cp -r "$HERE/sddm/nx" /usr/share/sddm/themes/
  sudo cp "$HERE/wallpapers/NX-Nebula/contents/images/3840x2160.png" \
          /usr/share/sddm/themes/nx/background.png
  sudo mkdir -p /etc/sddm.conf.d
  printf '[Theme]\nCurrent=nx\n' | sudo tee /etc/sddm.conf.d/10-nx-theme.conf >/dev/null
  say "SDDM theme set (takes effect on next login screen)"
fi

if [ "$APPLY" -eq 1 ]; then
  say "Applying NX to the current session"
  lookandfeeltool -a com.nerdrx.nx || true
  plasma-apply-colorscheme NX || true
  plasma-apply-desktoptheme nx || true
  plasma-apply-cursortheme NX-Cursors || true
  plasma-apply-wallpaperimage "$DATA/wallpapers/NX-Nebula/contents/images/3840x2160.png" || true
  say "Done. Some pieces (decorations, icons) may need a logout/login to fully settle."
else
  say "Installed. Apply via System Settings → Colors & Themes → Global Theme → NX,"
  say "or rerun with --apply."
fi
