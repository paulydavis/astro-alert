#!/usr/bin/env bash
# Build AstroAlert for macOS or Linux using PyInstaller.
# On Windows, run this from Git Bash or WSL: bash build.sh
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
    echo "Note: macOS Gatekeeper will block unsigned apps on first launch."
    echo "Right-click → Open to bypass on your own machine."
elif [[ "$PLATFORM" == MINGW* ]] || [[ "$PLATFORM" == CYGWIN* ]] || [[ "$PLATFORM" == MSYS* ]]; then
    echo "✓ Build complete: dist/AstroAlert.exe"
    echo ""
    echo "Double-click dist/AstroAlert.exe to run."
    echo "Copy it anywhere — it is fully self-contained."
    echo ""
    echo "Note: Windows SmartScreen may warn on first launch of an unsigned app."
    echo "Click 'More info' → 'Run anyway' to proceed."
else
    echo "✓ Build complete: dist/AstroAlert"
    echo ""
    echo "To install:"
    echo "  cp dist/AstroAlert ~/bin/AstroAlert"
    echo "  chmod +x ~/bin/AstroAlert"
    echo ""
    echo "Or run directly:"
    echo "  chmod +x dist/AstroAlert && ./dist/AstroAlert"
    echo ""
    echo "To create a desktop launcher:"
    echo "  Copy dist/AstroAlert somewhere permanent, then create"
    echo "  ~/.local/share/applications/astroalert.desktop with:"
    echo "    [Desktop Entry]"
    echo "    Name=AstroAlert"
    echo "    Exec=/path/to/AstroAlert"
    echo "    Type=Application"
    echo "    Categories=Science;"
fi
