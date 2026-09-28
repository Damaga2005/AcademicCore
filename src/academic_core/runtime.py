# SPDX-License-Identifier: MIT
"""Windows product runtime: user-data + bundled-resource resolution.

- Dev (unfrozen): ``~/.academic-core`` (certified behavior, untouched).
- Frozen (PyInstaller): ``%LOCALAPPDATA%/AcademicCore`` with home fallback.
- Resources: ``importlib.resources`` in dev, ``sys._MEIPASS`` when frozen.

Stdlib only. No Qt (importable before QApplication exists).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PRODUCT_NAME = "AcademicCore"
LEGACY_HOME_DIRNAME = ".academic-core"


def is_frozen() -> bool:
    """True inside the PyInstaller bundle (``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """Writable per-user product root (never Program Files, never CWD)."""
    if is_frozen():
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / PRODUCT_NAME
    return Path.home() / LEGACY_HOME_DIRNAME


def resource_path(package: str, name: str):
    """Bundled data file (migrations, future assets).

    Dev: ``importlib.resources`` Traversable. Frozen: real ``Path``
    under ``_MEIPASS/academic_core/<package-path>/<name>``.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "academic_core" / Path(*package.split(".")) / name
    from importlib import resources
    return resources.files(f"academic_core.{package}").joinpath(name)
