# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

VERSION = re.search(
    r'__version__ = "([^"]+)"',
    Path("tempbox/__init__.py").read_text(encoding="utf-8"),
).group(1)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("LICENSE", "."),
        ("NOTICE", "."),
        ("THIRD_PARTY_LICENSES.md", "."),
        ("licenses", "licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TempBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/TempBox.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TempBox",
)

app = BUNDLE(
    coll,
    name="TempBox.app",
    icon="assets/TempBox.icns",
    bundle_identifier="com.tempbox.app",
    info_plist={
        "CFBundleDisplayName": "TempBox",
        "CFBundleName": "TempBox",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundleDevelopmentRegion": "en",
        "CFBundleIdentifier": "com.tempbox.app",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright 2026 giaoWH",
        "NSPrincipalClass": "NSApplication",
    },
)
