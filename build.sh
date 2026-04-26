#!/usr/bin/env bash
# Build AstroAlert.app with PyInstaller.
# Usage: bash build.sh
set -euo pipefail

echo "==> Installing / upgrading PyInstaller…"
pip install --quiet --upgrade pyinstaller

echo "==> Cleaning previous build…"
rm -rf build dist

echo "==> Building AstroAlert.app…"
pyinstaller AstroAlert.spec

echo ""
echo "✓ Build complete: dist/AstroAlert.app"
echo ""
echo "To install:"
echo "  cp -r dist/AstroAlert.app /Applications/"
echo ""
echo "Then double-click AstroAlert in your Applications folder."
