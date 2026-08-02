# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


ROOT = Path(SPECPATH).resolve().parent
GENERATED = ROOT / "build" / "generated"
ICONS = ROOT / "build" / "icons"


datas = []
if (ROOT / "books").is_dir():
    datas.append((str(ROOT / "books"), "books"))

# RapidOCR ships model/configuration data that is not represented by ordinary
# Python imports. ONNX Runtime also needs its native provider libraries.
datas += collect_data_files("rapidocr")
binaries = collect_dynamic_libs("onnxruntime")
hiddenimports = sorted(
    set(
        collect_submodules("rapidocr")
        + collect_submodules("onnxruntime")
        + [
            "frozen_app",
            "tkinter",
            "tkinter.filedialog",
            "tkinter.messagebox",
        ]
    )
)

if sys.platform.startswith("win"):
    icon_path = ICONS / "Knightboard.ico"
elif sys.platform == "darwin":
    icon_path = ICONS / "Knightboard.icns"
else:
    icon_path = ICONS / "Knightboard.png"
icon_value = str(icon_path) if icon_path.is_file() else None


a = Analysis(
    [str(ROOT / "packaging" / "frozen_entry.py")],
    pathex=[str(ROOT), str(GENERATED)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Knightboard",
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
    icon=icon_value,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Knightboard",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Knightboard.app",
        icon=icon_value,
        bundle_identifier="com.joshuawang.knightboard",
        info_plist={
            "CFBundleDisplayName": "Knightboard",
            "CFBundleName": "Knightboard",
            "CFBundleShortVersionString": "0.50.0",
            "CFBundleVersion": "0.50.0",
            "NSCameraUsageDescription": (
                "Knightboard uses a connected camera to record moves played "
                "on a physical chessboard."
            ),
            "NSHighResolutionCapable": True,
        },
    )
