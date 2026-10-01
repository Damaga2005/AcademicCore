"""Digital circuit editor: pure design ops, service integration, canvas gestures."""
import pytest
from PySide6.QtCore import QPointF

from academic_core.application.digital_design import DigitalDesign
from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.errors import ValidationError
from academic_core.ui.digital_editor import CELL, DigitalEditorPage, pin_pos


def half_adder() -> DigitalDesign:
    d = DigitalDesign("ha")
    a, b, x, n = d.add_input(), d.add_input(), d.add_gate("XOR"), d.add_gate("AND")
    for g in (x, n):
        d.connect(a, g, 0)
        d.connect(b, g, 1)
    return d


def test_unconnected_pin_and_empty_design_are_refused():
    with pytest.raises(ValidationError):
        DigitalDesign().build()
    d = DigitalDesign()
    d.add_input()
    d.add_gate("AND")
    with pytest.raises(ValidationError, match="sin conectar"):
        d.build()


def test_edit_rules():
    d = half_adder()
    with pytest.raises(ValidationError):
        d.connect("xor1", "xor1", 0)
    with pytest.raises(ValidationError):
        d.connect("in1", "and1", 5)
    d.set_arity("and1", 3)
    assert d.source_of("and1", 2) is None
    d.set_arity("and1", 2)
    d.rename("in1", "A")
    assert d.source_of("and1", 0) == "A"
    d.delete("A")
    assert d.source_of("and1", 0) is None


def test_json_roundtrip_and_rejection():
    d = half_adder()
    d2 = DigitalDesign.from_json(d.to_json())
    assert d2.elements == d.elements and sorted(d2.wires) == sorted(d.wires)
    with pytest.raises(ValidationError):
        DigitalDesign.from_json("{not json")
    with pytest.raises(ValidationError):
        DigitalDesign.from_json('{"schema":"x"}')


def test_drawn_half_adder_captures_and_replays():
    svc = DigitalAnalysisService()
    key = svc.register_design(half_adder())
    assert key in {i.key for i in svc.demos()}
    req = AnalyzerRequest(key, ("in1", "in2", "xor1", "and1"), "0", "4")
    view = svc.capture(req)
    assert view.status == "CAPTURED" and view.transitions
    assert svc.verify(req).status == "EQUIVALENT"
    with pytest.raises(ValidationError):
        svc.register_design(DigitalDesign())


def test_canvas_gestures_build_and_use_a_circuit(qtbot):
    svc = DigitalAnalysisService()
    page = DigitalEditorPage(svc)
    qtbot.addWidget(page)
    c = page.canvas
    a, b = c.place("INPUT", 1, 1), c.place("INPUT", 1, 6)
    g = c.place("NAND", 10, 2)
    c.set_tool("wire")
    els = c.design.elements
    for src, pin in ((a, 0), (b, 1)):
        for point in (QPointF((els[src]["x"] + 1) * CELL, (els[src]["y"] + 1) * CELL), pin_pos(els[g], pin)):
            qtbot.mouseClick(c, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton,
                             pos=point.toPoint())
    assert sorted(c.design.wires) == [(a, g, 0), (b, g, 1)]
    seen = []
    page.applied.connect(seen.append)
    assert page.apply() == "usr:mi-circuito" and seen


def test_panel_lists_and_captures_a_drawn_circuit(qtbot, tmp_path, monkeypatch):
    from academic_core.app import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.main_window import AcademicMainWindow
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    panel = win.logic_analyzer_panel
    panel.editor.canvas.set_design(half_adder())
    key = panel.editor.apply()
    assert panel.demo.currentData() == key and panel.selected_channels()
    panel.start_capture()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    assert panel.view is not None and panel.view.status == "CAPTURED"
