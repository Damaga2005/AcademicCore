"""Shared builders for the F8-N lab verification suite (not a test module)."""
from decimal import Decimal as D

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.lab import (
    AnalysisKind,
    AnalysisSpec,
    CurrentProbe,
    ExperimentDefinition,
    InstrumentKind,
    InstrumentSpec,
    MeasurementKind,
    MeasurementSpec,
    VoltageProbe,
    add_experiment,
    create_session,
    run_experiment,
)
from academic_core.domain.engineering.lab.serialize import experiment_id
from academic_core.domain.engineering.mna.analysis import (
    GridSpec,
    MCConfig,
    ObservableSpec,
    ParamAddress,
    ParamSweepConfig,
    SweepConfig,
    UniformDist,
    WorstCaseConfig,
)
from academic_core.domain.engineering.mna.sensitivity import (
    ACSensitivityConfig,
    SensitivityConfig,
)
from academic_core.domain.engineering.mna.transient import TransientConfig
from academic_core.domain.engineering.units import parse_quantity as Q


def divider():
    c = Circuit("div")
    c.add(Component("V1", "V", Q("10 V"), {"+": "in", "-": "0"}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("R2", "R", Q("2 kohm"), {"1": "out", "2": "0"}))
    return c


def rc_step():
    c = Circuit("rc")
    c.add(Component("V1", "V", Q("0 V"), {"+": "in", "-": "0"},
                    {"wave": {"type": "step", "v1": Q("0 V"), "v2": Q("1 V"),
                              "t0": D("0.001")}}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"}))
    return c


def rc_ac():
    # NOTE: V1 carries a nonzero DC value (1 V) because the certified
    # F8-D5 network-transfer basis is an operating-point ratio: a zero
    # DC input admits no transfer (limit analysis out of scope).
    c = Circuit("rcac")
    c.add(Component("V1", "V", Q("1 V"), {"+": "in", "-": "0"},
                    {"ac_mag": Q("1 V")}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"}))
    return c


def diode_divider():
    c = Circuit("dd")
    c.add(Component("V1", "V", Q("5 V"), {"+": "vcc", "-": "0"}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "vcc", "2": "a"}))
    c.add(Component("D1", "D", None, {"A": "a", "K": "0"},
                    {"Is": Q("1e-14 A"), "n": Q("1"), "Vt": Q("25.85 mV")}))
    return c


def bjt_circuit():
    c = Circuit("bjt")
    c.add(Component("V2", "V", Q("10 V"), {"+": "vcc", "-": "0"}))
    c.add(Component("R3", "R", Q("2 kohm"), {"1": "vcc", "2": "c"}))
    c.add(Component("R4", "R", Q("200 kohm"), {"1": "vcc", "2": "b"}))
    c.add(Component("R5", "R", Q("1 kohm"), {"1": "e", "2": "0"}))
    c.add(Component("Q1", "Q", None, {"C": "c", "B": "b", "E": "e"},
                    {"Is": Q("1e-16 A"), "Bf": Q("100"), "Br": Q("1"),
                     "Nf": Q("1"), "Nr": Q("1"), "Vt": Q("25.85 mV"),
                     "polarity": "NPN"}))
    return c


def mos_circuit():
    from decimal import Decimal as _D
    from academic_core.domain.engineering.mna.analysis import KP_DIM, LAMBDA_DIM
    from academic_core.domain.engineering.units import DIMENSIONLESS, Quantity, Unit
    c = Circuit("mos")
    c.add(Component("V3", "V", Q("5 V"), {"+": "vdd", "-": "0"}))
    c.add(Component("R6", "R", Q("2 kohm"), {"1": "vdd", "2": "d"}))
    kp = Quantity(_D("0.0002"), Unit("A/V2", "A", "", KP_DIM, _D(1)))
    lam = Quantity(_D("0.02"), Unit("1/V", "V", "", LAMBDA_DIM, _D(1)))
    gam = Quantity(_D("0.5"), Unit("1", "1", "", DIMENSIONLESS, _D(1)))
    c.add(Component("M1", "M", None, {"D": "d", "G": "g", "S": "0", "B": "0"},
                    {"Kp": kp, "Vto": Q("1 V"), "Lambda": lam,
                     "Phi": Q("0.6 V"), "Gamma": gam, "polarity": "NMOS"}))
    c.add(Component("V4", "V", Q("3 V"), {"+": "g", "-": "0"}))
    return c


def op_definition(probes=(), instruments=(), measurements=(), label="op",
                  **kw):
    return ExperimentDefinition(
        label=label, analysis=AnalysisSpec(AnalysisKind.OP.value),
        probes=probes, instruments=instruments, measurements=measurements, **kw)


def voltmeter(key, probe_key, at=None):
    return (key, InstrumentSpec(InstrumentKind.VOLTMETER.value, probe=probe_key,
                               at=at))


def ammeter(key, probe_key, at=None):
    return (key, InstrumentSpec(InstrumentKind.AMMETER.value, probe=probe_key,
                               at=at))


def new_session(circuit=None, sid="test-session"):
    return create_session(sid, circuit or divider())


def add_ok(session, definition):
    session2, report = add_experiment(session, definition)
    assert report.ok, report.errors
    return session2


def run_ok(session, definition):
    session2 = add_ok(session, definition)
    eid = experiment_id(definition, session2.circuit)
    session3, run = run_experiment(session2, eid)
    return session3, run, eid


def transient_config(tstop="0.005"):
    # Step-capable tolerances (F8-L step regime: the LTE controller must
    # shrink far below smooth-regime floors at the edge).
    return TransientConfig("TR", D(tstop), D("0.00005"), D("1E-12"),
                           D("0.0005"), D("1E-4"), D("1E-6"))


def transient_tight_config(tstop="0.006"):
    # Tight step tolerances for analytic validation (measured max error
    # vs closed form ~7E-8 on the RC step).
    return TransientConfig("TR", D(tstop), D("0.00005"), D("1E-12"),
                           D("0.0005"), D("1E-6"), D("1E-9"))


def transient_definition(probes=(), instruments=(), measurements=(),
                         label="tran", circuit_tstop="0.005"):
    from academic_core.domain.engineering.lab import AnalysisSpec as _AS
    return ExperimentDefinition(
        label=label,
        analysis=_AS(AnalysisKind.TRANSIENT.value,
                    transient=transient_config(circuit_tstop)),
        probes=probes, instruments=instruments, measurements=measurements)
