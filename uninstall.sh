#!/usr/bin/env bash
# NX for KDE Plasma 6 — uninstaller. Removes installed copies (repo stays).
set -euo pipefail
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

rm -f  "$DATA/color-schemes/NX.colors" \
       "$DATA/konsole/NX.colorscheme"
rm -rf "$DATA/plasma/desktoptheme/nx" \
       "$DATA/plasma/look-and-feel/com.nerdrx.nx" \
       "$DATA/aurorae/themes/NX" \
       "$DATA/icons/NX" \
       "$DATA/icons/NX-Cursors" \
       "$DATA/wallpapers/NX-Nebula"

echo "NX removed from $DATA. If it was active, pick another Global Theme in System Settings."
echo "SDDM theme (if installed): sudo rm -rf /usr/share/sddm/themes/nx /etc/sddm.conf.d/10-nx-theme.conf"
