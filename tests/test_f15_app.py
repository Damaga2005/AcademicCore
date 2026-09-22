# SPDX-License-Identifier: MIT
"""F15 application tests (F15-001..F15-020 + F15-INT-001..008).

Covers: startup, dashboard, navigation, exercise/service flows,
simulation flows, virtual-lab flows, instruments, serialization,
replay, error UI, logging determinism, license/package, security,
architecture edges, F8 regression spot-checks, determinism.
"""
import ast
import logging
import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.errors import (
    AcademicCoreError,
    ConfigurationError,
    UiError,
    ValidationError,
    to_ui_error,
    ui_error_for_code,
)
from academic_core.ui.main_window import AcademicMainWindow

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"


@pytest.fixture()
def core(tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


# -- F15-001 startup -------------------------------------------------------
def test_f15_001_startup(qtbot, core):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    assert "Academic Core" in win.windowTitle()
    assert core.lab is not None and core.exercises is not None
    assert core.simulation is not None


def test_f15_int_001_application_startup(core):
    assert core.db is not None and core.engineering is not None
    assert core.assessment is not None


# -- F15-002 dashboard / F15-003 navigation --------------------------------
def test_f15_002_dashboard_lists_real_capabilities(qtbot, core):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    dash = win.dashboard_panel
    assert "v" in dash.state_label.text()
    assert "GREELEC" in dash.about_label.text()  # limitation explicit


def test_f15_003_navigation(qtbot, core):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    win.dashboard_panel.navigate.emit("simulation")
    assert win.tabs.currentWidget() is win.simulation_panel
    win.dashboard_panel.navigate.emit("lab")
    assert win.tabs.currentWidget() is win.virtual_lab_panel
    win.dashboard_panel.navigate.emit("exercises")
    assert win.tabs.currentWidget() is win.exercise_panel


def test_f15_int_002_dashboard(qtbot, core):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    assert win.tabs.tabText(0) == "Dashboard"


# -- F15-004 exercise -------------------------------------------------------
def test_f15_004_exercise_end_to_end(core):
    keys = core.exercises.library_keys()
    assert "ohm-v" in keys
    result = core.exercises.solve("ohm-v", {"I": "0.005 A", "R": "1000 ohm"})
    assert "5 V" in result.text and len(result.digest) >= 8
    with pytest.raises(ConfigurationError):
        core.exercises.solve("no-such-exercise", {})
    with pytest.raises(ValidationError):
        core.exercises.solve("ohm-v", {"I": "banana", "R": "1000 ohm"})


def test_f15_int_003_exercise_end_to_end(core):
    first = core.exercises.solve("ohm-v", {"I": "0.005 A", "R": "1000 ohm"})
    second = core.exercises.solve("ohm-v", {"I": "0.005 A", "R": "1000 ohm"})
    assert first.digest == second.digest  # determinism


# -- F15-005 simulation -----------------------------------------------------
def test_f15_005_simulation_op(core):
    from academic_core.domain.engineering.lab.model import (
        MeasurementSpec,
        VoltageProbe,
    )
    sim = core.simulation.run_op(
        "f15-op", core.simulation.demo_divider(),
        probes=(("vout", VoltageProbe("n2", "0")),),
        measurements=(("vdc", MeasurementSpec(kind="dc_value", probe="vout")),))
    assert sim.run.status == "COMPLETED"
    assert sim.digest == sim.run.result_digest


def test_f15_int_004_simulation_end_to_end(core):
    from academic_core.domain.engineering.lab.model import (
        MeasurementSpec,
        VoltageProbe,
    )
    one = core.simulation.run_op(
        "f15-sim", core.simulation.demo_divider(),
        probes=(("vout", VoltageProbe("n2", "0")),),
        measurements=(("vdc", MeasurementSpec(kind="dc_value", probe="vout")),))
    assert one.run.measurements and one.run.measurements[0].status == "OK"


# -- F15-006 virtual lab / instruments --------------------------------------
def _op_definition():
    from academic_core.domain.engineering.lab.model import (
        AnalysisKind,
        AnalysisSpec,
        ExperimentDefinition,
        InstrumentKind,
        InstrumentSpec,
        MeasurementKind,
        MeasurementSpec,
        VoltageProbe,
    )
    return ExperimentDefinition(
        analysis=AnalysisSpec(kind=AnalysisKind.OP.value),
        probes=(("vout", VoltageProbe("n2", "0")),),
        instruments=(("meter", InstrumentSpec(
            InstrumentKind.VOLTMETER.value, probe="vout")),),
        measurements=(("vdc", MeasurementSpec(
            kind=MeasurementKind.DC_VALUE.value, probe="vout")),))


def test_f15_006_virtual_lab_flow(core):
    session = core.lab.create_session("f15-lab", core.simulation.demo_divider())
    session, report = core.lab.add_experiment(session, _op_definition())
    assert report.ok
    from academic_core.domain.engineering.lab.serialize import experiment_id
    eid = experiment_id(_op_definition(), session.circuit)
    session, summary = core.lab.run_experiment(session, eid)
    assert summary.status == "COMPLETED"
    assert summary.measurements[0].status == "OK"
    assert summary.readings[0].status == "OK"  # F15-008 multimeter


def test_f15_007_dc_supply_via_stimulus(core):
    from academic_core.domain.engineering.lab.model import (
        StimulusKind,
        StimulusSpec,
    )
    from academic_core.domain.engineering.units import parse_quantity
    definition = _op_definition()
    stim = StimulusSpec("V1", StimulusKind.DC.value,
                        value=parse_quantity("9 V"))
    changed = type(definition)(**{**definition.__dict__, "stimuli": (stim,)})
    session = core.lab.create_session("f15-dc", core.simulation.demo_divider())
    session, report = core.lab.add_experiment(session, changed)
    assert report.ok
    from academic_core.domain.engineering.lab.serialize import experiment_id
    session, summary = core.lab.run_experiment(
        session, experiment_id(changed, session.circuit))
    assert summary.status == "COMPLETED"


def test_f15_009_oscilloscope_transient(core):
    from decimal import Decimal as _D
    from academic_core.domain.engineering.lab.model import (
        AnalysisKind,
        AnalysisSpec,
        ExperimentDefinition,
        InstrumentKind,
        InstrumentSpec,
        MeasurementKind,
        MeasurementSpec,
        ScopeChannel,
        VoltageProbe,
    )
    from academic_core.domain.engineering.mna.transient import TransientConfig
    definition = ExperimentDefinition(
        analysis=AnalysisSpec(
            kind=AnalysisKind.TRANSIENT.value,
            transient=TransientConfig("TR", _D("0.005"), _D("0.00005"),
                                      _D("1E-12"), _D("0.0005"),
                                      _D("1E-4"), _D("1E-6"))),
        probes=(("vout", VoltageProbe("out", "0")),),
        instruments=(("scope", InstrumentSpec(
            InstrumentKind.OSCILLOSCOPE.value,
            channels=(ScopeChannel("vout"),),
            window=(_D("0"), _D("0.005")))),),
        measurements=(("vmax", MeasurementSpec(
            kind=MeasurementKind.MAX.value, probe="vout")),))
    session = core.lab.create_session("f15-scope",
                                      core.simulation.demo_rc_step())
    session, report = core.lab.add_experiment(session, definition)
    assert report.ok, report.errors
    from academic_core.domain.engineering.lab.serialize import experiment_id
    session, summary = core.lab.run_experiment(
        session, experiment_id(definition, session.circuit))
    assert summary.status == "COMPLETED"
    kinds = {type(r.data).__name__ for r in summary.readings}
    assert "ScopeData" in kinds  # real waveform data, never fiction


def test_f15_010_function_generator(core):
    from academic_core.domain.engineering.lab import function_generator
    from academic_core.domain.engineering.units import parse_quantity
    from decimal import Decimal as _D
    spec = function_generator("V1", "sine", amplitude=parse_quantity("1 V"),
                              offset=parse_quantity("0 V"),
                              frequency=_D("1000"))
    assert spec.kind == "SINE"
    with pytest.raises(Exception):
        function_generator("V1", "triangle",
                           amplitude=parse_quantity("1 V"))


def test_f15_011_logic_analyzer_limitation(core):
    # F8-N has no digital-signal instrument: the UI must not invent one.
    from academic_core.domain.engineering.lab.model import InstrumentKind
    kinds = {k.value for k in InstrumentKind}
    assert "logic_analyzer" not in kinds


def test_f15_int_005_virtual_lab_flow(core):
    test_f15_006_virtual_lab_flow(core)


# -- F15-012/013 serialization + replay --------------------------------------
def test_f15_012_serialization_roundtrip(core):
    session = core.lab.create_session("f15-ser", core.simulation.demo_divider())
    session, report = core.lab.add_experiment(session, _op_definition())
    assert report.ok
    from academic_core.domain.engineering.lab.serialize import experiment_id
    session, summary = core.lab.run_experiment(
        session, experiment_id(_op_definition(), session.circuit))
    text = core.lab.save_text(session)
    loaded = core.lab.load_text(text)
    assert loaded.status == "OK"
    assert len(loaded.session.experiments) == 1


def test_f15_013_replay_equivalent(core):
    session = core.lab.create_session("f15-rep", core.simulation.demo_divider())
    session, _ = core.lab.add_experiment(session, _op_definition())
    from academic_core.domain.engineering.lab.serialize import experiment_id
    session, summary = core.lab.run_experiment(
        session, experiment_id(_op_definition(), session.circuit))
    result = core.lab.replay(session, summary.run_id)
    assert result.status == "EQUIVALENT"
    tampered = core.lab.load_text(
        core.lab.save_text(session).__class__("x")
        if False else core.lab.save_text(session).replace("divider", "dividER"))
    assert tampered.status in ("OK", "INVALID_SERIALIZATION", "SCHEMA_MISMATCH")


def test_f15_int_007_serialization(core):
    test_f15_012_serialization_roundtrip(core)


def test_f15_int_008_replay(core):
    test_f15_013_replay_equivalent(core)


# -- F15-014 error UI ----------------------------------------------------------
def test_f15_014_error_ui_safe():
    ui = to_ui_error(ValueError("V=banana with /home/secret/x.sql: boom"))
    assert isinstance(ui, UiError)
    assert ui.error_code and ui.safe_message and ui.user_action
    assert "/home/secret" not in ui.safe_message
    assert "Traceback" not in ui.safe_message
    ui2 = to_ui_error(ConfigurationError("VERSION_MISMATCH stored != running"))
    assert "version" in ui2.safe_message.lower()
    ui3 = ui_error_for_code("EQUIVALENT")
    assert "identical" in ui3.safe_message.lower()


def test_f15_int_006_error_boundary(core):
    with pytest.raises(ValidationError):
        core.exercises.solve("ohm-v", {"I": "xx", "R": "1 ohm"})


# -- F15-015 logging -------------------------------------------------------------
def test_f15_015_logging_determinism_and_redaction(core):
    from academic_core import logging_config as LC
    assert LC.redact("token=abc path " + os.path.expanduser("~") + "/f") == \
        LC.redact("token=abc path " + os.path.expanduser("~") + "/f")
    red = LC.redact("api_key=hunter2 ok")
    assert "hunter2" not in red
    with pytest.raises(ValueError):
        LC.get_logger("academic_core.domain.engineering.mna")
    first = core.exercises.solve("ohm-v", {"I": "0.005 A", "R": "1000 ohm"})
    logger = logging.getLogger("academic_core")
    logger.setLevel(logging.DEBUG)
    second = core.exercises.solve("ohm-v", {"I": "0.005 A", "R": "1000 ohm"})
    logger.setLevel(logging.INFO)
    assert first.digest == second.digest


# -- F15-016 license/package -------------------------------------------------------
def test_f15_016_license_package():
    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text and "Copyright (c) 2026 Damaga2005" in text
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = { text = "MIT" }' in pyproject
    assert "Damaga2005" in pyproject and "academic-core" in pyproject
    assert (root / "THIRD_PARTY_NOTICES.md").exists()
    assert (root / "sbom.json").exists()


# -- F15-017 security --------------------------------------------------------------
def test_f15_017_security_no_unsafe_primitives():
    bad = []
    for f in SRC.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("eval", "exec", "compile"):
                bad.append(f"{f.relative_to(SRC)}:{node.lineno}")
    assert not bad, bad
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "shell=True" not in text, f
        assert "pickle.loads" not in text, f


# -- F15-018 architecture ------------------------------------------------------------
def test_f15_018_architecture_edges():
    violations = []
    for f in (SRC / "ui").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for bad in ("from academic_core.infrastructure", "import sqlite3",
                    "from academic_core.domain.engineering.circuit import",
                    "from academic_core.domain.engineering import simulation",
                    "from academic_core.domain import authoring",
                    "from academic_core.documents import",
                    "from academic_core.documents.",
                    "from academic_core.domain import results"):
            if bad in text:
                violations.append(f"{f.name}: {bad}")
    assert not violations, violations
    for f in (SRC / "domain").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "getLogger" not in text, f"domain logging: {f.name}"
        assert "PySide6" not in text, f"domain Qt: {f.name}"


# -- F15-019 F8 regression spot --------------------------------------------------------
def test_f15_019_f8_regression_spot(core):
    from academic_core.domain.engineering.lab.model import SCHEMA
    assert SCHEMA == "f8n-lab/1"
    test_f15_005_simulation_op(core)


# -- F15-020 determinism -----------------------------------------------------------------
def test_f15_020_determinism(core):
    from academic_core.domain.engineering.lab.serialize import experiment_id
    definition = _op_definition()
    sessions = []
    for i in range(2):
        session = core.lab.create_session(
            f"f15-det-{i}", core.simulation.demo_divider())
        session, _ = core.lab.add_experiment(session, definition)
        session, summary = core.lab.run_experiment(
            session, experiment_id(definition, session.circuit))
        sessions.append(summary.result_digest)
    assert sessions[0] == sessions[1]
