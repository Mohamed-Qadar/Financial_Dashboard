# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for the Windows desktop application.

Build with:  python -m PyInstaller --noconfirm --clean desktop.spec
Produces:    dist/DailyMoneyTransferManager/DailyMoneyTransferManager.exe  (+ _internal/)

A one-folder build is used on purpose: a one-file build of a ~300 MB Streamlit
application would have to unpack itself into %TEMP% on every start (slow and
flagged by antivirus tools). The installer and the portable ZIP both wrap this
folder.
"""
import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))
from config import APP_PUBLISHER, APP_TITLE, APP_VERSION  # noqa: E402

APP_NAME = "DailyMoneyTransferManager"
ICON = ROOT / "assets" / "icon.ico"

# --- what goes into the bundle ------------------------------------------------
datas = [
    (str(ROOT / "app.py"), "."),                          # Streamlit runs this file from disk
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
    (str(ICON), "assets"),
]
binaries = []
hiddenimports = ["config", "app"] + collect_submodules("core") + collect_submodules("ui")

# Streamlit and the chart/dataframe libraries ship data files and plugins that
# static analysis cannot see.
for package in ("streamlit", "plotly", "pyarrow"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
for dist in ("streamlit", "pandas", "numpy", "plotly", "openpyxl", "reportlab", "xlrd", "pywebview"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # metadata is only needed where importlib.metadata is queried
        pass

# Keep the bundle lean: nothing below is used by this application.
excludes = [
    "altair", "pydeck", "matplotlib", "scipy", "sklearn", "IPython", "jupyter", "notebook",
    "tkinter", "_tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "gi",
    "torch", "tensorflow", "pytest", "_pytest", "streamlit.testing", "watchdog",
    "PIL.ImageQt", "PIL.ImageTk", "qtpy", "pywebview.platforms.gtk", "webview.platforms.gtk",
    "webview.platforms.qt", "webview.platforms.cocoa", "webview.platforms.android",
]

a = Analysis(
    [str(ROOT / "desktop_main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# --- Windows version resource -------------------------------------------------
_parts = [int(p) for p in APP_VERSION.split(".")[:3]] + [0]
_parts = (_parts + [0, 0, 0, 0])[:4]
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=tuple(_parts), prodvers=tuple(_parts), mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", APP_PUBLISHER),
            StringStruct("FileDescription", APP_TITLE),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", APP_NAME),
            StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
            StringStruct("ProductName", APP_TITLE),
            StringStruct("ProductVersion", APP_VERSION),
            StringStruct("LegalCopyright", f"(c) {APP_PUBLISHER}"),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # no command prompt window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
