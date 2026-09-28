# SPDX-License-Identifier: MIT
"""Installer contracts: names, version, paths, registry, shortcuts."""

from __future__ import annotations

import pathlib


def _nsi() -> str:
    root = pathlib.Path(__file__).resolve().parents[1] / "packaging" / "windows"
    return (root / "installer.nsi").read_text(encoding="utf-8")


def test_installer_names_product():
    text = _nsi()
    assert 'Name "AcademicCore"' in text
    assert "AcademicCore.exe" in text


def test_installer_version_matches_package():
    import re
    from academic_core import __version__
    text = _nsi()
    assert __version__ in text
    assert re.search(r"VIProductVersion", text)


def test_installer_registers_uninstall_and_start_menu():
    text = _nsi()
    assert "Uninstall" in text
    assert "StartMenu" in text or "SMPROGRAMS" in text
    assert "Microsoft\\Windows\\CurrentVersion\\Uninstall\\AcademicCore" in text


def test_installer_points_at_onedir_output():
    text = _nsi()
    assert "dist\\AcademicCore" in text or "dist/AcademicCore" in text
