#!/usr/bin/env bash
# Build AstroAlert for macOS or Linux using PyInstaller.
# Usage: bash build.sh
set -euo pipefail

PLATFORM="$(uname -s)"

echo "==> Platform: $PLATFORM"
echo "==> Installing / upgrading PyInstaller…"
pip install --quiet --upgrade pyinstaller

echo "==> Cleaning previous build…"
rm -rf build dist

echo "==> Building AstroAlert…"
pyinstaller AstroAlert.spec

echo ""
if [ "$PLATFORM" = "Darwin" ]; then
    echo "✓ Build complete: dist/AstroAlert.app"
    echo ""
    echo "To install:"
    echo "  cp -r dist/AstroAlert.app /Applications/"
    echo ""
    echo "Then double-click AstroAlert in your Applications folder."
    echo ""
    echo "Note: macOS Gatekeeper will block unsigned apps downloaded from the internet."
    echo "Users can right-click → Open to bypass this on their own machine."
else
    echo "✓ Build complete: dist/AstroAlert"
    echo ""
    echo "To install:"
    echo "  cp dist/AstroAlert ~/bin/AstroAlert   # or any directory on your PATH"
    echo "  chmod +x ~/bin/AstroAlert"
    echo ""
    echo "Or run directly:"
    echo "  chmod +x dist/AstroAlert && ./dist/AstroAlert"
    echo ""
    echo "To create a desktop launcher, copy dist/AstroAlert somewhere permanent"
    echo "and create a .desktop file in ~/.local/share/applications/."
fi
