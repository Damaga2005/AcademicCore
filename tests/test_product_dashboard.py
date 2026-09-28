# SPDX-License-Identifier: MIT
"""Dashboard editorial contracts: greeting + real recent activity."""

from __future__ import annotations

import os


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_editorial_header_present(qtbot, tmp_path):
    from academic_core.ui.dashboard import DashboardPanel
    dash = DashboardPanel(_core(tmp_path))
    qtbot.addWidget(dash)
    assert "Good morning" in dash.greeting_label.text()
    assert "Continue where you left off" in dash.greeting_sub.text()


def test_empty_state_without_activity(qtbot, tmp_path):
    from academic_core.ui.dashboard import DashboardPanel
    dash = DashboardPanel(_core(tmp_path))
    qtbot.addWidget(dash)
    assert "No recent activity yet" in dash.recent_label.text()


def test_recent_activity_is_real(qtbot, tmp_path):
    from academic_core.ui.dashboard import DashboardPanel
    core = _core(tmp_path)
    core.search_history.record_recent("asignatura", "subject:x", "Álgebra", "subject:x")
    dash = DashboardPanel(core)
    qtbot.addWidget(dash)
    assert "Álgebra" in dash.recent_label.text()
    assert "No recent activity" not in dash.recent_label.text()
