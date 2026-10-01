# SPDX-License-Identifier: MIT
"""Schematic editor: pure operations, canvas gestures, and a circuit drawn with the mouse that then solves."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    return app


def _place(core, circuit, ctype, x, y, **over):
    from academic_core.application import schematic as S
    spec = core.engineering.component_spec(ctype)
    raw = {p.key: p.default for p in spec.params}
    raw.update(over)
    return S.place(circuit, spec, x, y, core.engineering.make_parameters(ctype, raw))


# -- pure operations ---------------------------------------------------------------------------------
def test_connecting_pins_is_a_net_rename_and_ground_wins(core):
    from academic_core.application import schematic as S
    c = core.engineering.new_circuit("t")
    c = _place(core, c, "V", 4, 10)
    c = _place(core, c, "R", 12, 4)
    c = S.connect(c, ("V1", "+"), ("R1", "1"))
    assert c.components[0].pins["+"] == c.components[1].pins["1"]
    c = S.ground(c, "V1", "-")
    c = S.connect(c, ("R1", "2"), ("V1", "-"))
    assert {p for comp in c.components for p in comp.pins.values() if p == "0"}  # ground survives the merge
    assert sorted(S.nets_of(c)["0"]) == [("R1", "2"), ("V1", "-")]


def test_a_name_the_student_chose_beats_an_auto_net(core):
    from academic_core.application import schematic as S
    c = _place(core, _place(core, core.engineering.new_circuit("t"), "R", 4, 4), "R", 12, 4)
    c = S.rename_net(c, c.components[0].pins["2"], "out")
    c = S.connect(c, ("R2", "1"), ("R1", "2"))
    assert S.nets_of(c)["out"] == [("R1", "2"), ("R2", "1")]


def test_detach_moves_one_pin_and_delete_removes_the_part(core):
    from academic_core.application import schematic as S
    c = _place(core, _place(core, core.engineering.new_circuit("t"), "R", 4, 4), "R", 12, 4)
    c = S.connect(c, ("R1", "2"), ("R2", "1"))
    c = S.detach(c, "R1", "2")
    assert c.components[0].pins["2"] != c.components[1].pins["1"]
    assert [x.ref for x in S.delete(c, "R1").components] == ["R2"]


def test_placement_rotation_and_value_persist_through_storage(core):
    from academic_core.application import schematic as S
    core.engineering.create_project("P")
    c = S.rotate(S.move(_place(core, core.engineering.new_circuit("t"), "R", 4, 4), "R1", 10, 6), "R1")
    c = S.set_value(c, "R1", "2 kohm")
    core.engineering.repo.save_circuit("P", c)
    back = core.engineering.repo.load_circuit("P", "t").components[0]
    assert back.metadata == {"x": 10, "y": 6, "rot": 90} and back.value.compact() == "2kohm"


def test_old_circuits_without_positions_get_a_stable_tidy_layout(core):
    from academic_core.application import schematic as S
    d = core.simulation.demo_divider()
    lay = S.layout(d)
    assert len({(x, y) for x, y, _ in lay.values()}) == len(d.components) and S.layout(d) == lay
    frozen = S.freeze_layout(d)
    assert S.layout(frozen) == lay and d.to_netlist() == frozen.to_netlist()  # the netlist never changes


def test_rotating_moves_the_pins_a_quarter_turn(core):
    from academic_core.application import schematic as S
    comp = _place(core, core.engineering.new_circuit("t"), "R", 10, 10).components[0]
    assert S.pin_positions(comp, (10, 10, 0)) == {"1": (8, 10), "2": (12, 10)}
    assert S.pin_positions(comp, (10, 10, 90)) == {"1": (10, 8), "2": (10, 12)}


def test_every_component_type_has_pins_in_the_editor():
    from academic_core.application import schematic as S
    from academic_core.domain.engineering.circuit import COMPONENT_PINS
    assert {t: set(p) for t, p in S.PIN_OFFSETS.items()} == {t: set(p) for t, p in COMPONENT_PINS.items()}


# -- canvas gestures -----------------------------------------------------------------------------------
def _view(qtbot, core, circuit):
    from academic_core.ui.schematic import SchematicView
    v = SchematicView()
    qtbot.addWidget(v)
    v.resize(700, 500)
    v.show()
    v.set_circuit(circuit)
    return v


def _at(v, gx, gy):
    return v.to_px(gx, gy).toPoint()


def _two_resistors(core):
    from academic_core.application import schematic as S
    c = _place(core, core.engineering.new_circuit("t"), "R", 4, 4)
    return _place(core, c, "R", 14, 4)


def test_click_with_a_place_tool_asks_for_a_component_at_the_grid_point(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, core.engineering.new_circuit("t"))
    v.set_tool("place:R")
    with qtbot.waitSignal(v.place_requested) as got:
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 6, 5))
    assert got.args == ["R", 6, 5]


def test_two_clicks_with_the_wire_tool_ask_to_connect_two_pins(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, _two_resistors(core))
    v.set_tool("wire")
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 6, 4))  # R1.2
    with qtbot.waitSignal(v.connect_requested) as got:
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 12, 4))  # R2.1
    assert got.args == [("R1", "2"), ("R2", "1")]


def test_dragging_from_a_pin_with_the_select_tool_also_wires(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, _two_resistors(core))
    QTest.mousePress(v, Qt.MouseButton.LeftButton, pos=_at(v, 6, 4))
    QTest.mouseMove(v, _at(v, 9, 4))
    with qtbot.waitSignal(v.connect_requested) as got:
        QTest.mouseRelease(v, Qt.MouseButton.LeftButton, pos=_at(v, 12, 4))
    assert got.args == [("R1", "2"), ("R2", "1")]


def test_ground_tool_right_click_and_keys(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, _two_resistors(core))
    v.set_tool("ground")
    with qtbot.waitSignal(v.ground_requested) as g:
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 6, 4))
    assert g.args == ["R1", "2"]
    QTest.keyClick(v, Qt.Key.Key_Escape)
    assert v.tool == "select"
    with qtbot.waitSignal(v.detach_requested) as d:
        QTest.mouseClick(v, Qt.MouseButton.RightButton, pos=_at(v, 6, 4))
    assert d.args == ["R1", "2"]
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 4, 4))  # select R1 by its body
    assert v.selected == "R1"
    with qtbot.waitSignal(v.rotate_requested) as r:
        QTest.keyClick(v, Qt.Key.Key_R)
    assert r.args == ["R1"]
    with qtbot.waitSignal(v.delete_requested) as x:
        QTest.keyClick(v, Qt.Key.Key_Delete)
    assert x.args == ["R1"]


def test_dragging_a_body_reports_its_new_grid_position(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, _two_resistors(core))
    QTest.mousePress(v, Qt.MouseButton.LeftButton, pos=_at(v, 4, 4))
    QTest.mouseMove(v, _at(v, 7, 7))
    with qtbot.waitSignal(v.moved) as m:
        QTest.mouseRelease(v, Qt.MouseButton.LeftButton, pos=_at(v, 7, 7))
    assert m.args == ["R1", 7, 7]


def test_double_click_a_body_edits_it_and_a_pin_names_its_net(qtbot, core):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = _view(qtbot, core, _two_resistors(core))
    with qtbot.waitSignal(v.edit_requested) as e:
        QTest.mouseDClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 4, 4))
    assert e.args == ["R1"]
    with qtbot.waitSignal(v.rename_net_requested) as n:
        QTest.mouseDClick(v, Qt.MouseButton.LeftButton, pos=_at(v, 6, 4))
    assert n.args == [v.circuit.components[0].pins["2"]]


# -- a circuit drawn with the mouse solves ---------------------------------------------------------------
def test_a_student_draws_a_divider_with_the_mouse_and_solves_it(qtbot, core):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from academic_core.application import schematic as S
    from academic_core.ui.engineering import EngineeringPanel
    core.engineering.create_project("P")
    core.engineering.repo.save_circuit("P", core.engineering.new_circuit("draw"))
    panel = EngineeringPanel(core)
    qtbot.addWidget(panel)
    panel.resize(1300, 800)
    panel.show()
    panel.refresh_projects()
    panel.projects.setCurrentRow(0)
    panel.circuits.setCurrentRow(0)
    v = panel.schematic.canvas
    assert panel.view_stack.currentWidget() is panel.schematic
    v._auto_fit, v._zoom = False, 1.0  # a fixed view, so grid points map to known pixels
    v._pan = QPointF(v.width() / 2, v.height() / 2)

    def click(gx, gy):
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=_at(v, gx, gy))

    for tool, (gx, gy) in (("place:V", (-6, 0)), ("place:R", (2, -6)), ("place:R", (2, 6))):
        v.set_tool(tool)
        click(gx, gy)
    v.set_tool("wire")
    pins = lambda ref, pin: S.pin_positions(  # noqa: E731
        next(c for c in core.engineering.repo.load_circuit("P", "draw").components if c.ref == ref),
        v.layout[ref])[pin]
    for a, b in ((("V1", "+"), ("R1", "1")), (("R1", "2"), ("R2", "1"))):
        click(*pins(*a))
        click(*pins(*b))
    v.set_tool("ground")
    for ref, pin in (("V1", "-"), ("R2", "2")):
        click(*pins(ref, pin))
    drawn = core.engineering.repo.load_circuit("P", "draw")
    assert [c.ref for c in drawn.components] == ["R1", "R2", "V1"]
    nets = S.nets_of(drawn)
    assert sorted(nets["0"]) == [("R2", "2"), ("V1", "-")] and len(nets) == 3
    # the drawing is the circuit: the exact engine solves it and the conservation checks pass
    sim = core.simulation
    node = next(n for n in sim.circuit_info(drawn)[0] if ("R1", "2") in nets[n])
    plan = sim.plan_project(drawn, "OP", node, "V1")
    plan.pop("circuit")
    run = sim.run_analysis("draw", drawn, **plan).run
    assert run.status == "COMPLETED" and run.conservation.passed is True
    assert run.measurements[0].value.value == 2.5  # 5 V across two equal resistors


def test_keyboard_and_form_paths_still_add_components(qtbot, core, monkeypatch):
    """The mouse is not the only way: the Add component form keeps working."""
    from academic_core.ui import engineering
    from academic_core.ui.engineering import EngineeringPanel
    core.engineering.create_project("P")
    core.engineering.repo.save_circuit("P", core.engineering.new_circuit("kb"))
    panel = EngineeringPanel(core)
    qtbot.addWidget(panel)
    panel.refresh_projects()
    panel.projects.setCurrentRow(0)
    panel.circuits.setCurrentRow(0)
    answers = iter([{"type": "R"}, {"ref": "R1", "pin:1": "a", "pin:2": "0", "value": "1 kohm"}])
    monkeypatch.setattr(engineering, "prompt_form", lambda *a, **k: next(answers))
    panel._add_component()
    assert [c.ref for c in core.engineering.repo.load_circuit("P", "kb").components] == ["R1"]
