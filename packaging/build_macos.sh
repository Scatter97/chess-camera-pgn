#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

rm -rf build dist release
mkdir -p release

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ ! -x .venv-build/bin/python ]]; then
    "$PYTHON_BIN" -m venv .venv-build
fi

.venv-build/bin/python -m pip install --upgrade pip
.venv-build/bin/python -m pip install -r requirements.txt -r packaging/requirements-build.txt
.venv-build/bin/python packaging/prepare_frozen_sources.py
.venv-build/bin/python packaging/generate_icons.py
.venv-build/bin/python -m PyInstaller --noconfirm --clean packaging/ChessCamera.spec

VERSION="$(.venv-build/bin/python -c 'from chess_camera_app.core.version import APP_VERSION; print(APP_VERSION)')"
APP_PATH="dist/Knightboard.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "PyInstaller did not create $APP_PATH" >&2
    exit 1
fi

# Ad-hoc signing keeps the local bundle internally consistent. Public releases
# should replace this with a Developer ID signature and Apple notarization.
codesign --deep --force --sign - "$APP_PATH"

DMG_ROOT="build/dmg-root"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
cp -R "$APP_PATH" "$DMG_ROOT/Knightboard.app"
ln -s /Applications "$DMG_ROOT/Applications"

DMG_PATH="release/Knightboard-${VERSION}-macOS.dmg"
hdiutil create \
    -volname "Knightboard" \
    -srcfolder "$DMG_ROOT" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

ditto -c -k --sequesterRsrc --keepParent \
    "$APP_PATH" \
    "release/Knightboard-${VERSION}-macOS-app.zip"

echo "Built $APP_PATH"
echo "Built $DMG_PATH"
