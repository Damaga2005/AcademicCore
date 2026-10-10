# SPDX-License-Identifier: MIT
"""Engineering workspaces (UX 2026, prompt 6): Circuits, Aerospace, Digital Logic.

Layout is presentation; every number shown must come from the services.
"""

from __future__ import annotations

import os
from decimal import Decimal


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


# -- kit ------------------------------------------------------------------------------------
def test_metric_shows_value_with_unit_and_accessible_name(qtbot):
    from academic_core.ui.workspace import Metric
    m = Metric("Periodo", "min")
    qtbot.addWidget(m)
    assert m.text() == "—" and "sin valor" in m.accessibleName()
    m.set_value("92.8")
    assert m.accessibleName() == "Periodo: 92.8 min"
    m.clear()
    assert m.text() == "—"


def test_key_value_list_and_panel(qtbot):
    from academic_core.ui.workspace import KeyValueList, Panel
    kv = KeyValueList()
    qtbot.addWidget(kv)
    kv.set_rows([("a", "1"), ("b", "2")])
    kv.set_rows([("c", "3")])  # replaces, does not append
    assert kv.rows == [("c", "3")]
    panel = Panel("Resultados")
    qtbot.addWidget(panel)
    panel.add(kv)
    assert panel.title_label.text() == "Resultados" and panel.accessibleName() == "Resultados"


# -- aerospace -------------------------------------------------------------------------------
def _orbit(qtbot, tmp_path):
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    return panel


def test_aerospace_metrics_are_the_engine_values(qtbot, tmp_path):
    from academic_core.domain.engineering.orbital import (
        EARTH, circular_period_s, circular_velocity_m_s, escape_velocity_m_s)
    panel = _orbit(qtbot, tmp_path)
    panel.altitude_km.setText("420")
    panel.recompute()
    r = EARTH.radius_m + Decimal(420000)
    km = Decimal(1000)
    assert panel.metrics["v"].text() == f"{circular_velocity_m_s(r, EARTH.mu_m3_s2) / km:.3f}"
    assert panel.metrics["vesc"].text() == f"{escape_velocity_m_s(r, EARTH.mu_m3_s2) / km:.3f}"
    assert panel.metrics["T"].text().replace(" ", "") == f"{circular_period_s(r, EARTH.mu_m3_s2) / 60:.1f}"
    assert panel.metrics["h"].text() == "420.0" and panel.metrics["v"].unit.text() == "km/s"
    assert panel.status.text() == "ÉXITO"


def test_aerospace_context_shows_real_body_constants(qtbot, tmp_path):
    from academic_core.domain.engineering.orbital import EARTH
    panel = _orbit(qtbot, tmp_path)
    facts = dict(panel.body_facts.rows)
    assert facts["Cuerpo"] == "Tierra"
    assert facts["μ"].startswith(f"{EARTH.mu_m3_s2:.6e}")
    assert facts["Radio"].replace(" ", "").startswith(f"{EARTH.radius_m / 1000:.3f}")


def test_aerospace_bad_input_clears_results_and_flags_error(qtbot, tmp_path):
    panel = _orbit(qtbot, tmp_path)
    panel.recompute()
    panel.altitude_km.setText("-5")
    panel.recompute()
    assert panel.last == {} and panel.status.text() == "ERROR"
    assert all(m.text() == "—" for m in panel.metrics.values())
    assert panel.result_label.text().startswith("error:")


def test_aerospace_presets_and_enter_compute(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    panel = _orbit(qtbot, tmp_path)
    geo = next(b for b in panel.preset_buttons if b.text().endswith("35 786"))
    geo.click()
    assert panel.altitude_km.text() == "35786" and panel.last["h_m"] == Decimal(35786000)
    panel.altitude_km.setText("200")
    QTest.keyClick(panel.altitude_km, Qt.Key.Key_Return)
    assert panel.last["h_m"] == Decimal(200000)


def test_aerospace_runs_history_and_exact_replay(qtbot, tmp_path):
    panel = _orbit(qtbot, tmp_path)
    assert not panel.btn_replay.isEnabled()
    for alt in ("420", "420", "35786"):  # a repeat of the last run is not a new run
        panel.altitude_km.setText(alt)
        panel.recompute()
    assert panel.history_list.count() == 2 and not panel.runs_hint.isVisible()
    panel.history_list.setCurrentRow(0)
    assert panel.btn_replay.isEnabled()
    panel.replay()
    assert panel.altitude_km.text() == "420" and panel.status.text() == "EQUIVALENTE"
    assert panel.last == panel._runs[0]["state"]  # identical Decimals, not approximately equal


def test_orbit_view_tooltip_carries_the_real_altitude(qtbot, tmp_path):
    panel = _orbit(qtbot, tmp_path)
    panel.altitude_km.setText("420")
    panel.recompute()
    assert "420" in panel.orbit_view.toolTip()
    assert "not" not in panel.orbit_view.accessibleDescription().lower()


# -- circuits ---------------------------------------------------------------------------------
def _eng(qtbot, tmp_path):
    from academic_core.ui.engineering import EngineeringPanel
    core = _core(tmp_path)
    panel = EngineeringPanel(core)
    qtbot.addWidget(panel)
    return core, panel


def test_circuits_empty_states_lead_to_the_next_step(qtbot, tmp_path):
    core, panel = _eng(qtbot, tmp_path)
    assert panel.empty.title.text() == "Aún no hay proyectos"
    assert not panel.btn_new_ckt.isEnabled() and not panel.btn_add_comp.isEnabled()
    assert panel.view_stack.currentWidget() is panel.empty
    core.engineering.create_project("Demo")
    panel.refresh_projects()
    assert panel.empty.title.text() == "Elige un proyecto"
    panel.projects.setCurrentRow(0)
    assert panel.empty.title.text() == "Este proyecto no tiene circuitos"
    assert panel.btn_new_ckt.isEnabled() and not panel.btn_add_comp.isEnabled()
    core.engineering.save_circuit("Demo", core.engineering.new_circuit("Divisor"))
    panel._select_project()
    assert panel.empty.title.text() == "Elige un circuito"
    panel.circuits.setCurrentRow(0)
    # the drawing is the main view of a circuit; the table is one click away
    assert panel.btn_add_comp.isEnabled() and panel.view_stack.currentWidget() is panel.schematic
    panel.btn_view_components.click()
    assert panel.view_stack.currentWidget() is panel.components_table


def _with_circuit(core, panel):
    eng = core.engineering
    eng.create_project("Demo")
    eng.save_circuit("Demo", eng.new_circuit("Divisor"))
    for t, ref, val, nets in (("V", "V1", "5 V", ["in", "0"]), ("R", "R2", "2 kohm", ["out", "0"]),
                              ("R", "R1", "1 kohm", ["in", "out"])):
        eng.add_component("Demo", "Divisor", t, ref, val, dict(zip(eng.component_pins(t), nets)))
    panel.refresh_projects()
    panel.projects.setCurrentRow(0)
    panel.circuits.setCurrentRow(0)


def test_components_table_lists_the_real_circuit(qtbot, tmp_path):
    core, panel = _eng(qtbot, tmp_path)
    _with_circuit(core, panel)
    t = panel.components_table
    rows = [[t.item(r, c).text() for c in range(t.columnCount())] for r in range(t.rowCount())]
    assert [r[0] for r in rows] == ["R1", "R2", "V1"]  # sorted by reference
    assert rows[0][2] == "1kohm" and rows[2][2] == "5V"
    facts = dict(panel.facts.rows)
    assert facts["Componentes"] == "3" and facts["Topología"] == "correcta"
    assert facts["Estructura"] == "RESISTIVE"
    assert "R1 " in panel.detail.toPlainText() and panel.status.text() == "Demo / Divisor"


def test_netlist_view_toggle(qtbot, tmp_path):
    core, panel = _eng(qtbot, tmp_path)
    _with_circuit(core, panel)
    panel.btn_view_netlist.click()
    assert panel.view_stack.currentWidget() is panel.detail
    panel.btn_view_components.click()
    assert panel.view_stack.currentWidget() is panel.components_table


def test_calculation_lands_in_results_not_a_popup(qtbot, tmp_path, monkeypatch):
    from academic_core.ui import engineering
    core, panel = _eng(qtbot, tmp_path)
    _with_circuit(core, panel)
    monkeypatch.setattr(engineering, "prompt_form", lambda *a, **k: {
        "equation": "I = V / R", "inputs": "V=5 V; R=1 kohm", "name": "corriente"})
    panel._calculate()
    assert panel.last_calc.text() == "I = 0.005 A" and not panel.last_calc.isHidden()
    assert panel.pill.text() == "ÉXITO"
    assert panel.calc_table.rowCount() == 1 and panel.calc_table.item(0, 0).text() == "I"
    assert panel.calc_table.item(0, 2).text() == "A"


def test_calculation_error_goes_through_the_single_converter(qtbot, tmp_path, monkeypatch):
    from academic_core.ui import engineering
    core, panel = _eng(qtbot, tmp_path)
    shown = []
    monkeypatch.setattr(engineering, "prompt_form", lambda *a, **k: {
        "equation": "nonsense ((", "inputs": "V=5 V", "name": "x"})
    monkeypatch.setattr(engineering, "show_ui_error",
                        lambda parent, exc, title="Error": shown.append(title) or type(
                            "U", (), {"error_code": "E-TEST"})())
    panel._calculate()
    assert shown == ["Calcular"] and panel.pill.text() == "ERROR E-TEST"


def test_backend_status_is_shown_in_results(qtbot, tmp_path):
    core, panel = _eng(qtbot, tmp_path)
    assert panel.backend_label.text() == "Motores: sin comprobar"
    panel._backend_status()
    for line in core.engineering.backend_status_lines():
        assert line in panel.backend_label.text()


def test_route_switches_workspace_inside_the_pinned_page(qtbot, tmp_path):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(_core(tmp_path))
    qtbot.addWidget(win)
    win.navigate_to("engineering/aerospace")
    assert win.tabs.currentWidget() is win.engineering_panel
    assert win.engineering_panel.workspaces.currentWidget() is win.engineering_panel.orbit_panel
    win.navigate_to("engineering/circuits")
    assert win.engineering_panel.workspaces.currentWidget() is win.engineering_panel.circuits_workspace
    assert win.tabs.count() == 15


# -- digital logic ---------------------------------------------------------------------------------
def _logic(qtbot, tmp_path):
    from academic_core.ui.logic_analyzer import LogicAnalyzerPanel
    core = _core(tmp_path)
    panel = LogicAnalyzerPanel(core)
    qtbot.addWidget(panel)
    return core, panel


def test_logic_lab_context_comes_from_the_service(qtbot, tmp_path):
    core, panel = _logic(qtbot, tmp_path)
    info = next(d for d in core.digital.demos() if d.key == panel.demo.currentData())
    assert panel.context_label.text() == info.description
    other = next(i for i in range(panel.demo.count()) if i != panel.demo.currentIndex())
    panel.demo.setCurrentIndex(other)
    info2 = next(d for d in core.digital.demos() if d.key == panel.demo.currentData())
    assert panel.context_label.text() == info2.description != info.description


def test_logic_zones_are_separated_and_pinned_widgets_kept(qtbot, tmp_path):
    from PySide6.QtWidgets import QSplitter
    from academic_core.ui.workspace import Panel
    _core_, panel = _logic(qtbot, tmp_path)
    titles = {p.title_label.text(): p for p in panel.findChildren(Panel)}
    assert {"Configuración", "Forma de onda", "Transiciones", "Por qué cambió"} <= set(titles)
    assert titles["Configuración"].isAncestorOf(panel.channel_list) and titles["Configuración"].isAncestorOf(panel.pre)
    assert titles["Forma de onda"].isAncestorOf(panel.waveform)
    assert titles["Transiciones"].isAncestorOf(panel.table)
    assert titles["Por qué cambió"].isAncestorOf(panel.explanation)
    assert isinstance(panel.workspace, QSplitter) and panel.workspace.count() == 2
    assert not panel.workspace.childrenCollapsible()
    for b in (panel.btn_run, panel.btn_verify, panel.btn_save, panel.btn_load, panel.btn_replay):
        assert not titles["Configuración"].isAncestorOf(b)  # tools stay in the toolbar


def test_logic_short_labels_keep_full_accessible_names(qtbot, tmp_path):
    _core_, panel = _logic(qtbot, tmp_path)
    assert panel.start.accessibleName() == "Inicio / armar desde (s)"
    assert panel.trigger_channel.accessibleName() == "Canal de disparo"
    from PySide6.QtWidgets import QLabel
    visible = {w.text() for w in panel.findChildren(QLabel)}
    assert {"Desde (s)", "Hasta (s)", "Canal", "Flanco", "Pre (s)", "Post (s)"} <= visible


# -- labs (prompt 7) ----------------------------------------------------------------------------
def _sim(qtbot, tmp_path):
    from academic_core.ui.simulation import SimulationPanel
    panel = SimulationPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    return panel


def _run_and_wait(qtbot, panel):
    from academic_core.ui.state import UiState
    panel._run()
    qtbot.waitUntil(lambda: panel.state != UiState.RUNNING, timeout=60000)


def test_simulation_default_transient_runs_and_plots(qtbot, tmp_path):
    """Regression: `self.decimal` did not exist, so the default t_stop always failed."""
    from academic_core.ui.state import UiState
    panel = _sim(qtbot, tmp_path)
    panel.analysis.setCurrentText("TRANSIENT")  # default parameters: "t_stop=0.01 s"
    _run_and_wait(qtbot, panel)
    assert panel.state == UiState.SUCCESS, panel.output.toPlainText()
    presenter = panel.kit.presenter
    assert len(presenter.plots) == 1 and presenter.plots[0].series
    assert panel.kit.header.rows[0][0] == "Ejecución" and presenter.measure_table.rowCount() == 1


def test_simulation_scenario_is_derived_not_a_control(qtbot, tmp_path):
    panel = _sim(qtbot, tmp_path)
    assert not panel.scenario.isEnabled()
    for kind, item in (("OP", "divisor de tensión"), ("TRANSIENT", "escalón RC"), ("AC_SWEEP", "filtro RC (AC)"),
                       ("DC_SWEEP", "divisor de tensión")):
        panel.analysis.setCurrentText(kind)
        assert item in panel.scenario.currentText(), kind
    panel.analysis.setCurrentText("OP")
    assert panel.detail.isHidden() and panel.detail_label.isHidden()  # t_stop only applies to TRANSIENT
    panel.analysis.setCurrentText("TRANSIENT")
    assert not panel.detail.isHidden()


def test_simulation_results_are_structured_per_analysis(qtbot, tmp_path):
    panel = _sim(qtbot, tmp_path)
    presenter = panel.kit.presenter
    panel.analysis.setCurrentText("OP")
    _run_and_wait(qtbot, panel)
    assert [m.text() for m in presenter.metrics] == ["2.5"] and presenter.metrics[0].unit.text() == "V"
    assert not presenter.plots  # an operating point has nothing to plot, and says so
    panel.analysis.setCurrentText("AC_SWEEP")
    _run_and_wait(qtbot, panel)
    # gain and phase share one dual-axis Bode plot with a logarithmic frequency axis
    assert [p.title for p in presenter.plots] == ["Bode"] and all(p.x_log for p in presenter.plots)
    assert [label for label, _xs, _ys in presenter.plots[0].series] == ["Ganancia", "Fase"]
    assert presenter.measure_table is None  # no measurement requested: no stale table from the OP run
    assert not presenter.metrics


def test_lab_undefined_measurement_is_shown_honestly(qtbot, tmp_path):
    from academic_core.ui.state import UiState
    from academic_core.ui.virtual_lab import VirtualLabPanel
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel.circuit.setCurrentIndex(2)
    panel._new_session()
    panel.analysis.setCurrentText("AC_SWEEP")
    panel._add_run()
    qtbot.waitUntil(lambda: panel.state != UiState.RUNNING, timeout=60000)
    table = panel.kit.presenter.measure_table
    assert [table.item(0, c).text() for c in (0, 1, 3)] == ["bw", "—", "UNDEFINED"]  # never a fake 0
    assert "bandwidth not established" in table.item(0, 1).toolTip()


def test_lab_result_header_and_log(qtbot, tmp_path):
    from academic_core.ui.virtual_lab import VirtualLabPanel
    from academic_core.ui.state import UiState
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    assert panel.status.text() == "LISTO" and panel.output.isHidden()
    panel.circuit.setCurrentIndex(1)  # the session is built over the selected circuit
    panel._new_session()
    panel.analysis.setCurrentText("TRANSIENT")
    panel._add_run()
    qtbot.waitUntil(lambda: panel.state != UiState.RUNNING, timeout=60000)
    rows = dict(panel.kit.header.rows)
    assert rows["Ejecución"] == panel.last_run_id and rows["Estado"] == "COMPLETED"
    assert rows["Digest"].endswith("…") and len(rows["Digest"]) == 17
    assert len(panel.kit.presenter.plots) == 1 and panel.kit.presenter.plots[0].series
    assert panel.output.isHidden()  # the machine log is one click away, not the result
    panel.kit.log_toggle.click()
    assert not panel.output.isHidden() and panel.output.toPlainText().startswith("ejecución: exp-")


def test_new_session_clears_the_previous_result(qtbot, tmp_path):
    from academic_core.ui.virtual_lab import VirtualLabPanel
    from academic_core.ui.state import UiState
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel._new_session()
    panel._add_run()
    qtbot.waitUntil(lambda: panel.state != UiState.RUNNING, timeout=60000)
    assert panel.kit.header.rows
    panel._new_session()
    assert panel.kit.header.rows == [] and panel.status.text() == "LISTO — sesión abierta"


def test_explain_shows_computing_and_reveals_the_log(qtbot, tmp_path):
    from academic_core.ui.virtual_lab import VirtualLabPanel
    from academic_core.ui.state import UiState
    panel = VirtualLabPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel._new_session()
    panel._add_run()
    qtbot.waitUntil(lambda: panel.state != UiState.RUNNING, timeout=60000)
    panel._explain()
    assert panel.status.text() == "CALCULANDO…"  # re-deriving the trace, not running an experiment
    qtbot.waitUntil(lambda: panel.status.text() != "CALCULANDO…", timeout=60000)
    assert not panel.output.isHidden() and panel.output.toPlainText()


# -- plot ---------------------------------------------------------------------------------------
def test_nice_ticks_and_log_ticks():
    from academic_core.ui.lab_view import log_ticks, nice_ticks
    assert nice_ticks(0, 10) == [0, 2, 4, 6, 8, 10]
    assert nice_ticks(0.0, 0.01)[0] == 0 and nice_ticks(0.0, 0.01)[-1] == 0.01
    assert log_ticks(50, 20000) == [100.0, 1000.0, 10000.0]
    assert nice_ticks(3, 3) == [3]


def test_plot_drops_missing_points_and_describes_itself(qtbot):
    from academic_core.ui.lab_view import PlotView
    plot = PlotView("Gain", "frequency (Hz)", "dB", x_log=True)
    qtbot.addWidget(plot)
    plot.set_series([("gain", [Decimal(100), Decimal(1000), Decimal(0), Decimal(10000)],
                      [Decimal(-1), None, Decimal(-3), Decimal(-9)])])
    assert plot.series == [("gain", [100.0, 10000.0], [-1.0, -9.0])]  # None and x<=0 (log) dropped
    assert plot.accessibleDescription().startswith("2 puntos")
    plot.resize(400, 240)
    assert not plot.grab().isNull()  # paints without error
    plot.set_series([])
    assert plot.accessibleDescription() == "Sin datos" and not plot.grab().isNull()
