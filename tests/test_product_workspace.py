# SPDX-License-Identifier: MIT
"""Lab workspace contracts (UX 2026 prompt 7): one skeleton for every lab.

Experiment -> Setup -> (toolbar) -> Visualization -> Instruments -> Results.
Supersedes the earlier Experiment/Inputs/Execution/Results grouping. Widget
names, texts and engine behavior stay pinned.
"""

from __future__ import annotations

import os

SECTIONS = ("Experimento", "Configuración", "Visualización", "Instrumentos", "Resultados")


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _sections(panel):
    from academic_core.ui.workspace import Panel
    return {p.title_label.text(): p for p in panel.findChildren(Panel)}


def test_virtual_lab_workspace_sections(qtbot, tmp_path):
    from academic_core.ui.virtual_lab import VirtualLabPanel
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    sections = _sections(panel)
    for title in SECTIONS:
        assert title in sections, sorted(sections)
    # Pinned widgets preserved, each in the zone that owns it.
    assert panel.btn_run.text() == "Añadir y ejecutar" and panel.btn_replay.text() == "Repetir el último"
    assert sections["Experimento"].isAncestorOf(panel.session_id)
    assert sections["Experimento"].isAncestorOf(panel.circuit)
    assert sections["Configuración"].isAncestorOf(panel.analysis)
    assert sections["Configuración"].isAncestorOf(panel.dc_value)
    assert sections["Resultados"].isAncestorOf(panel.output)
    assert sections["Resultados"].isAncestorOf(panel.btn_explain)
    for b in (panel.btn_run, panel.btn_new, panel.btn_replay):
        assert not any(p.isAncestorOf(b) for p in sections.values())  # tools live in the toolbar


def test_simulation_workspace_sections(qtbot, tmp_path):
    from academic_core.ui.simulation import SimulationPanel
    panel = SimulationPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    sections = _sections(panel)
    for title in SECTIONS:
        assert title in sections, sorted(sections)
    assert panel.btn_run.text() == "Ejecutar"
    assert sections["Configuración"].isAncestorOf(panel.analysis)
    assert sections["Resultados"].isAncestorOf(panel.output)
    assert not any(p.isAncestorOf(panel.btn_run) for p in sections.values())
    titles = [p.title_label.text() for p in panel.findChildren(type(sections["Configuración"]))]
    assert len(titles) == len(set(titles))  # no repeated section title (audit H-02)


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
