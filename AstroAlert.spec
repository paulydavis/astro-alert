# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AstroAlert — cross-platform.

macOS   → dist/AstroAlert.app   (drag to Applications)
Windows → dist/AstroAlert.exe   (single-file, double-click)
Linux   → dist/AstroAlert       (single-file binary)
"""

import sys
import os
from pathlib import Path

block_cipher = None

# ── Find bundled Playwright Chromium ─────────────────────────────────────────
def _find_chromium():
    """Return (src_glob, dest) tuples for the Playwright Chromium install, or []."""
    try:
        from playwright._impl._driver import compute_driver_executable
        import subprocess, json
        driver = compute_driver_executable()
        result = subprocess.run(
            [str(driver), "print-api-json"],
            capture_output=True, text=True
        )
        # Fallback: just find the browsers dir from env or default
    except Exception:
        pass
    # Find where playwright installed chromium
    import glob
    search_roots = []
    if sys.platform == "win32":
        search_roots.append(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright")
    else:
        search_roots += [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
    # Also check PLAYWRIGHT_BROWSERS_PATH env override
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        search_roots.insert(0, Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]))

    for root in search_roots:
        if root.exists():
            chromium_dirs = sorted(root.glob("chromium-*"))
            if chromium_dirs:
                chromium_dir = chromium_dirs[-1]  # newest
                return [(str(chromium_dir), "chromium")]
    return []

_chromium_datas = _find_chromium()

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('sites.json',          '.'),
        ('sites.example.json',  '.'),
        ('targets.json',        '.'),
    ] + _chromium_datas,
    hiddenimports=[
        # stdlib
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'smtplib',
        'email.message',
        'email.mime.multipart',
        'email.mime.text',
        'email.mime.image',
        'zoneinfo',
        'zoneinfo.tzdata',
        'json',
        'threading',
        'webbrowser',
        'base64',
        'math',
        'io',
        # third-party
        'ephem',
        'requests',
        'requests.adapters',
        'urllib3',
        'dotenv',
        'python_dotenv',
        'openai',
        'PIL',
        'PIL.Image',
        'PIL.ImageStat',
        'PIL.ImageEnhance',
        'PIL.ImageOps',
        'PIL.ImageChops',
        'tkintermapview',
        'playwright',
        'playwright.sync_api',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── macOS: .app bundle ────────────────────────────────────────────────────────
if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='AstroAlert',
        debug=False,
        strip=False,
        upx=True,
        console=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='AstroAlert',
    )
    app = BUNDLE(
        coll,
        name='AstroAlert.app',
        icon=None,
        bundle_identifier='com.paulydavis.astroalert',
        info_plist={
            'CFBundleName':            'AstroAlert',
            'CFBundleDisplayName':     'Astro Alert',
            'CFBundleVersion':         '1.4.5',
            'CFBundleShortVersionString': '1.4.5',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion':  '10.13.0',
        },
    )

# ── Windows / Linux: single-file executable ───────────────────────────────────
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        name='AstroAlert',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
