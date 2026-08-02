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
ARCH="$(dpkg --print-architecture)"
PACKAGE_ROOT="$ROOT/build/debian-package"
INSTALL_ROOT="$PACKAGE_ROOT/opt/knightboard"

rm -rf "$PACKAGE_ROOT"
mkdir -p \
    "$PACKAGE_ROOT/DEBIAN" \
    "$INSTALL_ROOT" \
    "$PACKAGE_ROOT/usr/bin" \
    "$PACKAGE_ROOT/usr/share/applications" \
    "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps" \
    "$PACKAGE_ROOT/usr/share/doc/knightboard"

cp -a dist/Knightboard/. "$INSTALL_ROOT/"
cp README.md "$PACKAGE_ROOT/usr/share/doc/knightboard/README.md"
cp build/icons/Knightboard.png \
    "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps/knightboard.png"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: knightboard
Version: $VERSION
Section: games
Priority: optional
Architecture: $ARCH
Maintainer: Joshua Wang
Depends: libc6 (>= 2.35), libgl1, libglib2.0-0, libx11-6, libxcb1
Description: Camera-based over-the-board chess PGN recorder
 Knightboard is an offline chess studio with camera game recording, PGN,
 clocks, local history, analysis, opening and endgame tools.
EOF

cat > "$PACKAGE_ROOT/usr/bin/knightboard" <<'EOF'
#!/usr/bin/env bash
set -e
export KNIGHTBOARD_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/knightboard"
exec /opt/knightboard/Knightboard "$@"
EOF
chmod 0755 "$PACKAGE_ROOT/usr/bin/knightboard"

cat > "$PACKAGE_ROOT/usr/share/applications/knightboard.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Knightboard
Comment=Offline chess studio with camera game recording
Exec=knightboard
Icon=knightboard
Terminal=false
Categories=Game;Utility;
Keywords=Chess;Camera;PGN;Analysis;Opening;Endgame;
StartupNotify=true
EOF

find "$PACKAGE_ROOT" -type d -exec chmod 0755 {} +
chmod 0755 "$INSTALL_ROOT/Knightboard"

OUTPUT="release/knightboard_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$OUTPUT"

echo "Built $OUTPUT"
echo "Install with: sudo apt install ./$OUTPUT"
