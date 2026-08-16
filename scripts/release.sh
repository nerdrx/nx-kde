#!/usr/bin/env bash
# Package the NX theme suite for NX Hub and publish a GitHub release.
#
# The tarball is laid out as `share/...` so the hub's tarball-prefix engine
# (prefix ~/.local, per-file manifest, symlink-preserving) installs, updates,
# and uninstalls every component exactly. The SDDM theme is NOT included —
# it needs root; use ./install.sh --sddm for that.
#
#   scripts/release.sh              # package + publish vX.Y.Z
#   scripts/release.sh --dry-run    # package + checksum only
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

REPO="nerdrx/nx-kde"
VERSION="$(tr -d '[:space:]' < VERSION)"
[ -n "$VERSION" ] || { echo "no VERSION file"; exit 1; }

OUT="dist"
NAME="nx-kde-${VERSION}-linux.tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

S="$STAGE/share"
mkdir -p "$S/color-schemes" "$S/konsole" "$S/plasma/desktoptheme" \
         "$S/plasma/look-and-feel" "$S/aurorae/themes" "$S/icons" \
         "$S/wallpapers" "$OUT"
cp    colors/NX.colors            "$S/color-schemes/"
cp    konsole/NX.colorscheme      "$S/konsole/"
cp -a desktoptheme/nx             "$S/plasma/desktoptheme/"
cp -a lookandfeel/com.nerdrx.nx   "$S/plasma/look-and-feel/"
cp -a aurorae/NX                  "$S/aurorae/themes/"
cp -a icons/NX                    "$S/icons/"
cp -a cursors/NX-Cursors          "$S/icons/"
cp -a wallpapers/NX-Nebula        "$S/wallpapers/"

tar -czf "$OUT/$NAME" -C "$STAGE" share
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
echo "packaged: $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1))"

if [ "${1:-}" = "--dry-run" ]; then
  echo "dry run — GitHub untouched"
  exit 0
fi

gh release create "v$VERSION" --repo "$REPO" \
  --title "NX for KDE $VERSION" \
  --notes "The NX design language as a complete KDE Plasma 6 Global Theme — colors, Plasma style, window decorations, icons, cursors, wallpaper, splash. Installable and auto-updatable through [NX Hub](https://github.com/nerdrx/nx-hub); manual install via \`install.sh\`. Apply with System Settings → Colors & Themes → Global Theme → NX. The SDDM login theme needs root: \`./install.sh --sddm\` from a clone." \
  "$OUT/$NAME" "$OUT/$NAME.sha256"
echo "published v$VERSION"
