# SPDX-License-Identifier: MIT
"""Windows product runtime contracts: user-data paths + frozen resources.

Dev behavior (unfrozen) is preserved; frozen behavior (PyInstaller)
resolves %LOCALAPPDATA%/AcademicCore and _MEIPASS.
"""

from __future__ import annotations

import pathlib
import sys

import pytest


def test_dev_user_data_dir_uses_home():
    if getattr(sys, "frozen", False):
        pytest.skip("frozen interpreter")
    from academic_core.runtime import user_data_dir
    assert user_data_dir() == pathlib.Path.home() / ".academic-core"


def test_frozen_user_data_dir_uses_localappdata(tmp_path, monkeypatch):
    from academic_core import runtime
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runtime.user_data_dir() == tmp_path / "AcademicCore"


def test_frozen_user_data_dir_falls_back_without_localappdata(monkeypatch):
    from academic_core import runtime
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert runtime.user_data_dir() == pathlib.Path.home() / ".academic-core"


def test_resource_path_dev_uses_importlib():
    if getattr(sys, "frozen", False):
        pytest.skip("frozen interpreter")
    from academic_core.runtime import resource_path
    assert resource_path("infrastructure.migrations", "001_academic.sql").is_file()


def test_version_is_product_version():
    from academic_core import __version__
    assert __version__ == "1.0.0"


def test_version_propagates_to_pyproject():
    import tomllib
    from academic_core import __version__
    root = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert tomllib.loads(root.read_text(encoding="utf-8"))["project"]["version"] == __version__


def test_version_propagates_to_windows_version_info():
    import re
    from academic_core import __version__
    root = pathlib.Path(__file__).resolve().parents[1] / "packaging" / "windows"
    text = (root / "version_info.txt").read_text(encoding="utf-8")
    assert f"'{__version__}'" in text
    assert (root / "academicore.spec").is_file()
    assert (root / "academicore.ico").is_file()
