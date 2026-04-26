# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AstroAlert — cross-platform.

macOS  → dist/AstroAlert.app   (drag to Applications)
Windows → dist/AstroAlert.exe  (single-file, double-click)
Linux  → dist/AstroAlert       (single-file binary)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('sites.example.json', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'ephem',
        'requests',
        'dotenv',
        'python_dotenv',
        'smtplib',
        'email.message',
        'zoneinfo',
        'json',
        'threading',
        'webbrowser',
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

# ── macOS: multi-file bundle inside a .app ────────────────────────────────────
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
            'CFBundleName': 'AstroAlert',
            'CFBundleDisplayName': 'Astro Alert',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.13.0',
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
        console=False,         # no terminal window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
