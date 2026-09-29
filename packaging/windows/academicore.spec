# SPDX-License-Identifier: MIT
# AcademicCore Windows product spec (PyInstaller, onedir).
#
# Reproducible: version is read from src/academic_core/__init__.py
# (single source; tests/test_windows_runtime.py pins propagation).
# Migrations ship as data (importlib.resources needs real files).
# No console window. Icon + version metadata embedded.

import re
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent.parent
SRC = ROOT / "src"

text = (SRC / "academic_core" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)

a = Analysis(
    [str(SRC / "academic_core" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(SRC / "academic_core" / "infrastructure" / "migrations"),
         "academic_core/infrastructure/migrations"),
        (str(SRC / "academic_core" / "resources" / "academicore.ico"),
         "academic_core/resources"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_qt", "tkinter", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AcademicCore",
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
    icon=str(HERE / "academicore.ico"),
    version=str(HERE / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AcademicCore",
)
