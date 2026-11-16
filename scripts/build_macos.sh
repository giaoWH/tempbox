#!/usr/bin/env bash
# Build TempBox.app and the unsigned Apple Silicon DMG.
# Usage: conda activate tempbox && ./scripts/build_macos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON:-python}"
if ! "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller is not installed in this Python environment." >&2
    echo "Install build dependencies with: $PYTHON_BIN -m pip install -r requirements-build.txt" >&2
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
    echo "This release script currently targets Apple Silicon (arm64); got: $ARCH" >&2
    exit 1
fi

VERSION="$("$PYTHON_BIN" -c 'from tempbox import __version__; print(__version__)')"
APP="dist/TempBox.app"
DMG="dist/TempBox-${VERSION}-macOS-${ARCH}.dmg"

echo "Building TempBox ${VERSION} for ${ARCH}..."
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm TempBox.spec

if [[ ! -x "$APP/Contents/MacOS/TempBox" ]]; then
    echo "Build failed: $APP/Contents/MacOS/TempBox is missing." >&2
    exit 1
fi

echo "Preparing DMG staging..."
mkdir -p build
STAGING="$(mktemp -d build/dmg-staging.XXXXXX)"
mkdir -p "$STAGING/Licenses"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Keep license and attribution information visible alongside the app.
cp LICENSE NOTICE THIRD_PARTY_LICENSES.md "$STAGING/Licenses/"
cp -R licenses "$STAGING/Licenses/"

echo "Creating $DMG..."
hdiutil create \
    -volname "TempBox" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DMG" >/dev/null

echo "SHA-256:"
shasum -a 256 "$DMG" | tee "$DMG.sha256"

echo
echo "App:  $APP"
echo "DMG:  $DMG"
echo "Architecture: $ARCH"
echo "Version: $VERSION"
