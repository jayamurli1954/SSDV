#!/usr/bin/env bash
# Build OfficeMitra.app and OfficeMitra.dmg on macOS 12+.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" && -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi
if [[ -z "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

"$PYTHON" -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"

echo "Using Python: $PYTHON"
"$PYTHON" -m pip install -U pip
"$PYTHON" -m pip install -e ".[ui]" pyinstaller

ICON_PNG="$ROOT/assets/officemitra-app-icon.png"
ICNS="$ROOT/assets/officemitra.icns"
if [[ -f "$ICON_PNG" ]] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  echo "Building officemitra.icns from PNG..."
  ICONSET="$ROOT/build/OfficeMitra.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for size in 16 32 64 128 256 512; do
    sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    if [[ "$double" -le 1024 ]]; then
      sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    fi
  done
  iconutil -c icns "$ICONSET" -o "$ICNS"
fi

"$PYTHON" -m PyInstaller --noconfirm --clean "$ROOT/installer/OfficeMitra.spec"

APP="$ROOT/dist/OfficeMitra.app"
if [[ ! -d "$APP" ]]; then
  # onedir fallback if BUNDLE output path differs
  if [[ -d "$ROOT/dist/OfficeMitra/OfficeMitra.app" ]]; then
    APP="$ROOT/dist/OfficeMitra/OfficeMitra.app"
  elif [[ -d "$ROOT/dist/OfficeMitra" ]]; then
    echo "PyInstaller produced dist/OfficeMitra (folder). Wrapping as .app..."
    mkdir -p "$ROOT/dist/OfficeMitra.app/Contents/MacOS"
    # Prefer native .app from BUNDLE; if missing, fail clearly.
    echo "Expected dist/OfficeMitra.app — check the PyInstaller log." >&2
    exit 1
  fi
fi

if [[ ! -d "$APP" ]]; then
  echo "OfficeMitra.app was not created." >&2
  exit 1
fi

DMG="$ROOT/dist/OfficeMitra.dmg"
rm -f "$DMG"
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/OfficeMitra.app"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/installer/HOW-TO-INSTALL.txt" "$STAGE/HOW-TO-INSTALL.txt"
mkdir -p "$STAGE/docs"
for f in CLIENT_INSTALL.pdf CLIENT_MANUAL.pdf USER_MANUAL.pdf CLIENT_INSTALL.md CLIENT_MANUAL.md; do
  if [[ -f "$ROOT/docs/$f" ]]; then
    cp "$ROOT/docs/$f" "$STAGE/docs/$f"
  else
    echo "Warning: missing docs/$f" >&2
  fi
done

hdiutil create -volname "OfficeMitra" -srcfolder "$STAGE" -ov -format UDZO "$DMG"

echo
echo "Done. Customer files:"
echo "  $APP"
echo "  $DMG"
echo
echo "Note: without an Apple Developer ID the first open needs"
echo "  Right-click → Open  (Gatekeeper)."
