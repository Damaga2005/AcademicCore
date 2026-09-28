# SPDX-License-Identifier: MIT
"""Lab workspace contracts: intent-grouped sections, widgets preserved.

Sections (Experiment/Inputs/Execution/Results) only reparent the pinned
widgets — names, texts and engine behavior are untouched.
"""

from __future__ import annotations

import os


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _sections(panel):
    from PySide6.QtWidgets import QGroupBox
    return {b.title(): b for b in panel.findChildren(QGroupBox)}


def test_virtual_lab_workspace_sections(qtbot, tmp_path):
    from academic_core.ui.virtual_lab import VirtualLabPanel
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    sections = _sections(panel)
    for title in ("Experiment", "Inputs", "Execution", "Results"):
        assert title in sections, sorted(sections)
    # Pinned widgets preserved inside the workspace.
    assert panel.btn_run.text() == "Add + Run"
    assert panel.btn_replay.text() == "Replay last"
    assert sections["Execution"].isAncestorOf(panel.btn_run)
    assert sections["Results"].isAncestorOf(panel.output)


def test_simulation_workspace_sections(qtbot, tmp_path):
    from academic_core.ui.simulation import SimulationPanel
    panel = SimulationPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    sections = _sections(panel)
    for title in ("Experiment", "Inputs", "Execution", "Results"):
        assert title in sections, sorted(sections)
    assert panel.btn_run.text() == "Run"
    assert sections["Execution"].isAncestorOf(panel.btn_run)
    assert sections["Results"].isAncestorOf(panel.output)


def test_run_transitions_state(qtbot, tmp_path):
    from academic_core.ui.state import UiState
    from academic_core.ui.virtual_lab import VirtualLabPanel
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    assert panel.state == UiState.IDLE
    panel._new_session()
    panel.analysis.setCurrentText("OP")
    panel._add_run()
    assert panel.state == UiState.RUNNING
    qtbot.waitUntil(lambda: panel.state == UiState.SUCCESS, timeout=30000)
