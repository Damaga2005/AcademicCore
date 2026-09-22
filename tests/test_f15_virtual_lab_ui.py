"""F15 Virtual Lab widget regression: the real "Add + Run" button path.

Earlier F15 tests exercised ``LabService`` directly, never the widget. Two
defects hid there:

1. ``_build_definition`` used ``ExperimentDefinition`` without importing it
   (``NameError`` on every click).
2. ``_on_result`` read ``summary.run.*``, but ``LabRunSummary`` exposes the
   fields directly (``AttributeError``).

These tests click the button, let the F15 ``ServiceWorker`` run, and check
the rendered result for every supported analysis. They also check that
replay reports ``EQUIVALENT``.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.ui.virtual_lab import VirtualLabPanel

CASES = [(0, "OP"), (0, "DC_SWEEP"), (1, "TRANSIENT"), (2, "AC_POINT"), (2, "AC_SWEEP")]


@pytest.fixture()
def panel(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    shown = []
    from academic_core.ui import errors as ui_errors
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(ui_errors.QMessageBox, name,
                            staticmethod(lambda parent, title, body, _n=name: shown.append((_n, title, body))))
    widget = VirtualLabPanel(core)
    qtbot.addWidget(widget)
    widget.dialogs = shown
    return widget


@pytest.mark.parametrize("circuit, kind", CASES)
def test_f15_vl_add_run_button_end_to_end(qtbot, panel, circuit, kind):
    panel.circuit.setCurrentIndex(circuit)
    panel.btn_new.click()
    panel.analysis.setCurrentText(kind)
    panel.btn_run.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=60000)
    assert panel.state.value == "SUCCESS", (kind, panel.status.text(), panel.dialogs)
    text = panel.output.toPlainText()
    assert text.startswith("run: exp-") and "status: COMPLETED" in text and "digest: " in text
    assert panel.last_run_id and panel.dialogs == []
    panel.btn_replay.click()
    assert panel.dialogs and "identical result" in panel.dialogs[-1][2]
    assert f"replay {panel.last_run_id}: EQUIVALENT" in panel.output.toPlainText()


def test_f15_vl_incompatible_analysis_is_a_d2_dialog_not_a_crash(qtbot, panel):
    panel.circuit.setCurrentIndex(0)  # divider
    panel.btn_new.click()
    panel.analysis.setCurrentText("TRANSIENT")  # needs rc-step
    panel.btn_run.click()
    assert panel.state.value == "IDLE" and panel.dialogs
    assert panel.dialogs[-1][1] == "Experiment" and "NameError" not in panel.dialogs[-1][2]
