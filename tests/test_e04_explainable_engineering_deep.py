"""E0.4 Explainable Engineering Deep Observability & Resolver Retrofit.

Sections:

- transient: the inner Newton of every attempt (x_k, F, J, Δx, α, real backtracking), acceptance, rejection,
  abort, observer equivalence
- AC sweep: the real complex MNA system of every frequency, solution, H / magnitude / phase, equivalence
- F8-K: MOSFET (NMOS, PMOS), JFET, Zener, LED, Schottky, photodiode through the F8-H Newton trace
- F8-M: parameter sweep, worst case, DC sensitivity, Monte Carlo, limits
- F8-O: the GUM budget observed through the certified engine (no second implementation)
- F8-P1..P5: Routh, FFT, sampling, reflection, BPSK, link budget
- F15: service registry, Virtual Lab F8-M runs re-observed, replay, EQUIVALENT, unsupported kinds
- anti-fake-step, determinism, boundedness, security AST, observer equivalence, serialization, performance
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import time
from decimal import Decimal
from fractions import Fraction

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.domain.engineering.ac.problem import build_ac_problem
from academic_core.domain.engineering.ac.response import ResponseDefinition, frequency_response, voltage_between
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.mna.analysis import (
    GridSpec,
    MCConfig,
    ObservableSpec,
    ParamAddress,
    ParamSweepConfig,
    UniformDist,
    WorstCaseConfig,
    run_monte_carlo_native,
    solve_param_sweep,
    solve_worst_case,
)
from academic_core.domain.engineering.mna.nonlinear import solve_nonlinear_dc
from academic_core.domain.engineering.mna.sensitivity import SensitivityConfig, solve_dc_sensitivity
from academic_core.domain.engineering.mna.transient import TransientConfig, solve_transient
from academic_core.domain.execution import (
    EQUIVALENT,
    MAX_JSON_BYTES,
    CheckStatus,
    EventKind,
    ExecutionTrace,
    Outcome,
    VerificationStatus,
    compare,
    verification_kind,
)
from academic_core.domain.execution import analog_detail as det
from academic_core.domain.execution import engineering_deep as dp
from academic_core.domain.execution import newton as nwt
from academic_core.errors import ValidationError

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
D = Decimal
P1 = ".param D1 Is=1e-14A n=1 Vt=0.02585V"
DIODE = f"* diode\nV1 in 0 5V\nR1 in a 1kohm\nD1 a 0 D\n{P1}\n.end\n"
DIVIDER = "* divider\nV1 in 0 12V\nR1 in out 1kohm\nR2 out 0 2kohm\n.end\n"
LADDER = "* ladder\nV1 n1 0 10V\n" + "".join(f"R{k} n{k} n{k + 1} 1kohm\n" for k in range(1, 8)) + "R8 n8 0 1kohm\n.end\n"
RC = "* rc\nV1 in 0 1V\nR1 in out 1kohm\nC1 out 0 1uF\n.end\n"
RC_IC = "* rc\nV1 in 0 1V\nR1 in out 1kohm\nC1 out 0 1uF\n.param C1 ic=0V\n.end\n"
DRC = f"* drc\nV1 in 0 5V\nR1 in a 1kohm\nD1 a out D\nC1 out 0 1uF\n{P1}\n.param C1 ic=0V\n.end\n"
MOS_RC = ("* m\nV1 vdd 0 5V\nR1 vdd d 1kohm\nC1 g 0 1uF\nR2 vdd g 1kohm\nM1 d g 0 0 M\n"
          ".param M1 polarity=NMOS Kp=0.02A/V2 Vto=1V Lambda=0/V Phi=0.6V Gamma=0\n.param C1 ic=0V\n.end\n")
MOS_ARGS = ("BE", "0.005", "0.001", "0.000000000000001", "0.001")
NMOS = ("* nmos\nV1 vdd 0 5V\nV2 g 0 2V\nR1 vdd d 1kohm\nM1 d g 0 0 M\n"
        ".param M1 polarity=NMOS Kp=0.002A/V2 Vto=1V Lambda=0.01/V Phi=0.6V Gamma=0\n.end\n")
PMOS = ("* pmos\nV1 vdd 0 5V\nV2 g 0 3V\nR1 d 0 1kohm\nM1 d g vdd vdd M\n"
        ".param M1 polarity=PMOS Kp=0.002A/V2 Vto=1V Lambda=0.01/V Phi=0.6V Gamma=0.5\n.end\n")
JFET = ("* jfet\nV1 vdd 0 10V\nV2 g 0 -1V\nR1 vdd d 1kohm\nJ1 d g 0 J\n"
        ".param J1 polarity=NCHAN Idss=10mA Vp=4V Lambda=0.01/V\n.end\n")


def diode_kind(kind, extra="", v="5V"):
    return (f"* {kind.lower()}\nV1 in 0 {v}\nR1 in a 1kohm\nD1 a 0 D\n"
            f".param D1 kind={kind} Is=1e-14A n=1 Vt=0.02585V{extra}\n.end\n")


ZENER = diode_kind("ZENER", " Vz=5.1V nz=1 Iz=1mA", "-10V")
LED = diode_kind("LED").replace("n=1 ", "n=2 ")
SCHOTTKY = diode_kind("SCHOTTKY").replace("Is=1e-14A", "Is=1e-8A")
PHOTO = diode_kind("PHOTO", " Iph=100uA", "-1V")
LEG = ("direction=downlink; ptx_w=100; gtx_dbi=30; ltx_db=1; freq_hz=12e9; distance_m=36e6; grx_dbi=40; lrx_db=0.5; "
       "tsys_k=150; bandwidth_hz=36e6; rb_bps=10e6")


def events(trace, prefix):
    return [e for e in trace.events if e.title.startswith(prefix)]


def values(event):
    return dict(event.values)


def errors(trace):
    return [e.error.reason for e in trace.events if e.kind is EventKind.ERROR]


def check(trace, title):
    found = [e for e in trace.events if e.kind is EventKind.CHECK and e.title == title]
    assert len(found) == 1, title
    return found[0].check


def value_names(trace):
    return {n for e in trace.events for n, _v in e.values}


def passes(trace):
    assert trace.outcome is Outcome.SUCCESS, [e.error for e in trace.events if e.error]
    assert trace.verification.status is VerificationStatus.PASS
    assert compare(trace, dp.replay_deep(trace)).status == EQUIVALENT if trace.operation in dp.OPERATIONS else True


class Recorder:
    """Records every observer call; asserts every received value is an immutable snapshot."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            for v in list(args) + list(kwargs.values()):
                _immutable(v)
            self.calls.append((name, args, kwargs))
        return call

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


def _immutable(v):
    from academic_core.domain.engineering.math.rational import RationalComplex
    if isinstance(v, (DecimalComplex, RationalComplex)):
        return
    assert isinstance(v, (tuple, Decimal, Fraction, str, bool, int, type(None))), type(v)
    if isinstance(v, tuple):
        for item in v:
            _immutable(item)


def cfg(args, adaptive=True, reltol="1e-3", abstol="1e-6"):
    return TransientConfig(args[0], *[D(v) for v in args[1:]], D(reltol), D(abstol), adaptive=adaptive)


# =============================================================== transient: the inner Newton

def test_e04_t01_newton_data_are_the_integrators():
    circuit = nwt.parse_circuit_spec(DRC)
    args = ("BE", "0.002", "0.0001", "0.000000001", "0.0005")
    rec = Recorder()
    result = solve_transient(circuit, cfg(args), observer=rec)
    rows = [r for _n, a, kw in rec.named("transient_accept") + rec.named("transient_reject") for r in kw["newton"]]
    assert sum(len(kw["newton"]) for *_x, kw in rec.named("transient_accept") + rec.named("transient_reject")) \
        == result.stats["newton_total"] > 0
    t = dp.explain_transient_newton(DRC, *args)
    passes(t)
    newton_events = [e for e in t.events if " · Newton " in e.title and "backtracking" not in e.title]
    assert len(newton_events) == len(rows) == result.stats["newton_total"]
    accepted = rec.named("transient_accept")
    first = accepted[0][2]["newton"][0] if accepted[0][2]["newton"] else None
    if first is not None:
        v = values(events(t, f"Paso {accepted[0][1][0]} · Newton 1")[0])
        labels = rec.named("transient_start")[0][1][4]
        names = [det._lab(x) for x in labels]
        k, alpha, _p, _k, _a, _r, _s, x, f, jac, dx, _tr = first
        assert v["alpha"].number == alpha
        assert [v[f"x_k.{n}"].number for n in names] == list(x)
        assert [v[f"F_k.{n}"].number for n in names] == list(f)
        assert [v[f"dx.{n}"].number for n in names] == list(dx)
        assert [v[f"J.{a}.{b}"].number for a in names for b in names] == [e for row in jac for e in row]
    assert check(t, "Comprobación: el sistema lineal de Newton").status is CheckStatus.PASS
    assert check(t, "Comprobación: continuidad de Newton").status is CheckStatus.PASS
    assert verification_kind(check(t, "Comprobación: iteraciones de Newton")) == "SYMBOLIC"


def test_e04_t02_real_backtracking_trials():
    circuit = nwt.parse_circuit_spec(MOS_RC)
    rec = Recorder()
    solve_transient(circuit, cfg(MOS_ARGS, adaptive=False), observer=rec)
    trials = [row[11] for *_x, kw in rec.named("transient_accept") for row in kw["newton"]]
    multi = [tr for tr in trials if len(tr) > 1]
    assert multi  # this circuit really backtracks (piecewise MOSFET regions)
    t = dp.explain_transient_newton(MOS_RC, *MOS_ARGS, adaptive=False)
    passes(t)
    bt = [e for e in t.events if "backtracking" in e.title]
    assert len(bt) == sum(len(tr) for tr in multi)
    for tr in multi:
        assert [a for a, _n, _ok in tr] == [D(1) / D(2) ** k for k in range(len(tr))]  # α halves from 1
        assert [ok for *_x, ok in tr] == [False] * (len(tr) - 1) + [True]  # only the last is accepted
    assert all(values(e)["decision"].text in ("aceptado", "rechazado") for e in bt)


def test_e04_t03_rejection_and_abort_are_real():
    args = ("TR", "0.005", "0.001", "0.000000001", "0.001")
    rec = Recorder()
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), cfg(args, reltol="1e-6", abstol="1e-9"), observer=rec)
    rejected = [c for c in rec.named("transient_reject") if c[1][4] is not None]
    assert len(rejected) == result.stats["rejected"] > 0  # real LTE rejections, each with its retry Δt
    assert all(c[1][0] == "lte" and c[1][5] > 1 and c[1][4] < c[1][2] for c in rejected)  # E > 1, retry < tried
    t = dp.explain_transient_newton(RC_IC, *args, "1e-6", "1e-9")
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    abort = dp.explain_transient_newton(RC_IC, "BE", "0.001", "0.0001", "0.0001", "0.0001")
    assert abort.outcome is Outcome.FAILED and errors(abort) == ["TIMESTEP_TOO_SMALL"]
    (stop,) = events(abort, "Intento fallido")
    assert values(stop)["cause"].text == "lte" and values(stop)["retry_dt"].text == "-"
    assert not events(abort, "Paso ")  # nothing was committed


def test_e04_t04_observer_equivalence_and_no_invented_newton():
    for spec, args, adaptive in ((MOS_RC, MOS_ARGS, False), (MOS_RC, MOS_ARGS, True), (DRC, ("BE", "0.002", "0.0001",
                                  "0.000000001", "0.0005"), True)):
        c = nwt.parse_circuit_spec(spec)
        a, b = solve_transient(c, cfg(args, adaptive)), solve_transient(c, cfg(args, adaptive), observer=Recorder())
        assert a.to_dict() == b.to_dict() and a.diagnostics == b.diagnostics and a.stats == b.stats
    t = dp.explain_transient_newton(DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005")
    assert not events(t, "backtracking") or all("· Newton" in e.title for e in events(t, "backtracking"))
    assert not [e for e in t.events if "Newton sin convergencia" in e.title]  # no failure was observed


# =============================================================== AC sweep: the matrix of every frequency

def test_e04_w01_every_frequency_has_its_real_system():
    freqs = "10 Hz, 1 kHz, 100 kHz"
    t = dp.explain_ac_sweep_mna(RC, "V1", "out", "0", freqs)
    passes(t)
    circuit = nwt.parse_circuit_spec(RC)
    rec = Recorder()
    definition = ResponseDefinition("transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sweep = frequency_response(circuit, definition, freqs.split(", "), observer=rec)
    systems = rec.named("ac_system")
    assert [c[1][0] for c in rec.named("sweep_frequency")] == [0, 1, 2] and len(systems) == 3
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.math.linsolve import NumericMode
    for k, (_n, (labels, matrix, rhs, _kind, f_hz, _w), _kw) in enumerate(systems):
        problem = build_ac_problem(circuit, ACOperatingPoint.from_frequency(freqs.split(", ")[k], "0"),
                                   NumericMode.AUTO)
        assert matrix == tuple(tuple(r) for r in problem.matrix)  # exactly the solved matrix
        a = values(events(t, f"f{k} = {f_hz} Hz: A(jω)")[0])
        assert [a[f"A.{i}.{j}"].text for i in range(3) for j in range(3)] == \
            [det._cx(matrix[i][j]) for i in range(3) for j in range(3)]
        h = values(events(t, f"f{k}: H(jω)")[0])
        p = sweep.points[k]
        assert h["abs_H"].number == p.value.magnitude() and h["arg_H"].number == p.value.phase()
    assert check(t, "Comprobación: A·x = b por frecuencia").status is CheckStatus.PASS


def test_e04_w02_bounds_and_equivalence():
    t = dp.explain_ac_sweep_mna(LADDER, "V1", "n8", "0", "1 kHz, 2 kHz")
    passes(t)
    head = values(events(t, "f0 = 1000 Hz: A(jω) (detalle omitido)")[0])
    assert head["matrix_detail"].text == "OMITTED" and head["size"].number == 9 and not any(
        n.startswith("A.") for n in value_names(t))
    circuit = nwt.parse_circuit_spec(RC)
    definition = ResponseDefinition("transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    a = frequency_response(circuit, definition, ["10 Hz", "1 kHz"])
    b = frequency_response(circuit, definition, ["10 Hz", "1 kHz"], observer=Recorder())
    assert a.to_dict() == b.to_dict() and a.digest == b.digest
    assert dp.explain_ac_sweep_mna(RC, "V1", "out", "0", "").outcome is Outcome.FAILED


# =============================================================== F8-K

@pytest.mark.parametrize("spec, kind", [(NMOS, "MOSFET"), (PMOS, "MOSFET"), (JFET, "JFET"), (ZENER, "Diodo"),
                                        (LED, "Diodo"), (SCHOTTKY, "Diodo"), (PHOTO, "Diodo")])
def test_e04_k01_semiconductor_values_are_the_engines(spec, kind):
    from academic_core.domain.engineering.mna.diode import extract_diode_variant_params, variant_companion
    from academic_core.domain.engineering.mna.jfet import extract_jfet_params, jfet_operating_point
    from academic_core.domain.engineering.mna.mosfet import extract_mosfet_params, mos_operating_point
    t = nwt.explain_nonlinear_dc(spec)
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    assert events(t, f"Modelo {kind}") and not events(t, "Detalle de dispositivo no expuesto")
    evals = events(t, f"Evaluación {kind}")
    assert evals
    circuit = nwt.parse_circuit_spec(spec)
    comp = next(c for c in circuit.components if c.type.upper() in ("M", "J", "D"))
    ctx = make_context()
    rec = Recorder()
    solve_nonlinear_dc(circuit, observer=rec)
    last = rec.named("newton_iteration")[-1][2]["fk_devices"][0]
    v = values(evals[-1])
    if kind == "MOSFET":
        p = extract_mosfet_params(comp)
        op = mos_operating_point(*last[3:7], p, ctx)
        assert v["region"].text == op[0] and v["gm"].number == op[2] and v["Vth"].number == op[5]
        assert v["ID"].number == last[17]
    elif kind == "JFET":
        p = extract_jfet_params(comp)
        op = jfet_operating_point(*last[3:6], p, ctx)
        assert v["region"].text == op[0] and v["gm"].number == op[2] and v["gds"].number == op[3]
    else:
        p = extract_diode_variant_params(comp)
        i, _g, _eq = variant_companion(v["Vd"].number, p, ctx)
        assert v["I"].number == i and v["branch"].text == last[3]
    c2 = nwt.parse_circuit_spec(spec)
    a, b = solve_nonlinear_dc(c2), solve_nonlinear_dc(c2, observer=Recorder())
    assert a.to_dict() == b.to_dict() and a.diagnostics == b.diagnostics
    text = nwt.circuit_spec(circuit)  # the text form round-trips: same circuit, same parameters, same trace
    assert nwt.explain_nonlinear_circuit(circuit).digest() == nwt.explain_nonlinear_dc(text).digest()
    again = nwt.parse_circuit_spec(text)
    assert {c.ref: dict(c.parameters) for c in again.components} == {c.ref: dict(c.parameters)
                                                                     for c in circuit.components}


def test_e04_k02_zener_branch_and_text_form_errors():
    t = nwt.explain_nonlinear_dc(ZENER)
    assert values(events(t, "Evaluación Diodo")[-1])["branch"].text == "zener-breakdown"
    fwd = nwt.explain_nonlinear_dc(ZENER.replace("-10V", "5V"))
    assert values(events(fwd, "Evaluación Diodo")[-1])["branch"].text == "zener-forward"
    assert errors(nwt.explain_nonlinear_dc(NMOS.replace("polarity=NMOS", "polarity=NPNX"))) == ["INVALID_INPUT"]
    assert errors(nwt.explain_nonlinear_dc(ZENER.replace("kind=ZENER", "kind=TUNNEL"))) == ["INVALID_INPUT"]
    assert errors(nwt.explain_nonlinear_dc(NMOS.replace("Kp=0.002A/V2", "Kp=0.002A/V3"))) == ["INVALID_INPUT"]


# =============================================================== F8-M

def test_e04_m01_parameter_sweep_points_are_real():
    t = dp.explain_param_sweep(DIODE, "R1", "500", "2000", "500", "a")
    passes(t)
    result = solve_param_sweep(nwt.parse_circuit_spec(DIODE), ParamSweepConfig(
        "grid", target=ParamAddress("R1", "value"), grid=GridSpec.linear(D(500), D(2000), D(500)),
        observables=(ObservableSpec("node_voltage", "a"),)))
    points = [e for e in events(t, "Punto ") if ":" in e.title]
    assert len(points) == len(result.points) == 4
    for e, p in zip(points, result.points):
        assert values(e)["iterations"].number == p.iterations and values(e)["init_mode"].text == p.init_mode
        assert len(events(t, f"Punto {p.index} · iteración")) == p.iterations
    assert check(t, "Comprobación: arranque en caliente").status is CheckStatus.PASS


def test_e04_m02_worst_case_corners_and_extrema():
    t = dp.explain_worst_case(DIVIDER, "R1=900:1100, R2=1800:2200", "out")
    passes(t)
    result = solve_worst_case(nwt.parse_circuit_spec(DIVIDER), WorstCaseConfig(
        ((ParamAddress("R1", "value"), D(900), D(1100)), (ParamAddress("R2", "value"), D(1800), D(2200))),
        (ObservableSpec("node_voltage", "out"),)))
    assert len([e for e in events(t, "Punto ") if ":" in e.title]) == len(result.corners) == 4
    ext = values(events(t, "Extremos de node_voltage:out")[0])
    assert ext["min.value"].number == result.extrema["node_voltage:out"]["min"]["value"]
    assert ext["max.corner"].text == result.extrema["node_voltage:out"]["max"]["arg_corner"]
    assert check(t, "Comprobación: extremos").status is CheckStatus.PASS


def test_e04_m03_sensitivity_is_the_engines_single_way():
    t = dp.explain_dc_sensitivity(DIODE, "R1, V1", "a")
    passes(t)
    rec = Recorder()
    config = SensitivityConfig((ParamAddress("R1", "value"), ParamAddress("V1", "value")),
                               (ObservableSpec("node_voltage", "a"),))
    result = solve_dc_sensitivity(nwt.parse_circuit_spec(DIODE), config, observer=rec)
    (_n, (labels, _x, _jac), _k), = rec.named("sensitivity_system")
    for (_n, (key, _df, dx), _k), e in zip(rec.named("sensitivity_parameter"), events(t, "Parámetro ")):
        v = values(e)
        assert [v[f"dx_dp.{det._lab(lab)}"].number for lab in labels] == list(dx)
        engine = result.state[key]["values"]
        assert [engine[lab]["value"] for lab in labels] == list(dx)  # the engine's own result, not a second way
    obs = values(events(t, "Observable node_voltage:a")[0])
    assert obs["d.R1_value"].number == result.observables["node_voltage:a"]["sensitivities"]["R1.value"]["derivative"]
    assert check(t, "Comprobación: sistema de sensibilidad").status is CheckStatus.PASS
    plain = solve_dc_sensitivity(nwt.parse_circuit_spec(DIODE), config)
    assert plain.digest == result.digest


def test_e04_m04_monte_carlo_samples_and_seed():
    dists = "R1=uniform:900:1100, R2=normal:2000:50:1800:2200"
    t = dp.explain_monte_carlo(DIVIDER, dists, "20", "7", "out")
    passes(t)
    config = MCConfig(20, ((ParamAddress("R1", "value"), UniformDist(D(900), D(1100))),
                           (ParamAddress("R2", "value"), dp._distributions(dists)[1][1])), 7,
                      (ObservableSpec("node_voltage", "out"),))
    result = run_monte_carlo_native(nwt.parse_circuit_spec(DIVIDER), config)
    samples = events(t, "Muestra ")
    assert len(samples) == len(result.iterations) == 20
    for e, it in zip(samples, result.iterations):
        v = values(e)
        assert v["param.R1_value"].number == dict(it.parameters)["R1.value"]
        assert v["sub_seed.0"].text == str(it.sub_seeds[0])
    assert values(events(t, "Semilla")[0])["seed"].number == 7  # the seed given, never an implicit one
    assert dp.explain_monte_carlo(DIVIDER, dists, "20", "7", "out").digest() == t.digest()
    other = dp.explain_monte_carlo(DIVIDER, dists, "20", "8", "out")
    assert values(events(other, "Muestra 0")[0])["param.R1_value"].number != \
        values(samples[0])["param.R1_value"].number
    stats = values(events(t, "Estadística de node_voltage:out")[0])
    assert stats["mean"].number == result.statistics["node_voltage:out"]["mean"]


def test_e04_m05_limits():
    assert errors(dp.explain_param_sweep(DIODE, "R1", "1", "10000", "10")) == ["INVALID_LIMIT"]
    assert errors(dp.explain_dc_sensitivity(DIODE, ",".join(["R1"] * 9))) == ["INVALID_LIMIT"]
    assert errors(dp.explain_monte_carlo(DIVIDER, "R1=triangle:1:2", "5", "1", "out")) == ["INVALID_INPUT"]
    assert errors(dp.explain_monte_carlo(DIVIDER, "R1=uniform:900:1100", "5", "-1", "out")) == ["INVALID_INPUT"]
    big = dp.explain_monte_carlo(DIVIDER, "R1=uniform:900:1100", str(dp.MAX_SAMPLES + 5), "3", "out")
    (cut,) = events(big, det.TRUNCATED)
    assert values(cut)["omitted_events"].number == 5 and len(events(big, "Muestra ")) == dp.MAX_SAMPLES
    assert big.verification.status is VerificationStatus.PASS


# =============================================================== F8-O

def test_e04_o01_gum_budget_through_the_certified_engine():
    from academic_core.domain.engineering import gum as G
    from academic_core.domain.engineering.metrology.o2_propagate import evaluate_budget
    from academic_core.domain.execution import uncertainty as unc
    specs = {"V": "value=12; u=0.1; dof=10", "I": "value=2; u=0.05; dof=20"}
    trace = unc.explain_gum("P", "V*I", specs)  # the E0.1 trace of the same certified engine
    assert trace.outcome is Outcome.SUCCESS and trace.verification.status is VerificationStatus.PASS
    model = G.MeasurementModel(measurand="P", equation="V*I")
    inputs = {n: unc.parse_spec(n, v) for n, v in specs.items()}
    a, b = Recorder(), Recorder()
    ra = G.evaluate_gum(model, inputs, observer=a)
    rb = evaluate_budget(model, inputs, observer=b)
    assert a.calls == b.calls and a.calls  # one engine, one observation stream: no second GUM
    plain = evaluate_budget(model, inputs)
    assert ra.combined_standard_uncertainty == rb.combined_standard_uncertainty == plain.combined_standard_uncertainty
    assert rb.expanded_uncertainty == plain.expanded_uncertainty


# =============================================================== F8-P1..P5

def test_e04_p1_routh_table_is_the_engines():
    from academic_core.domain.engineering.control.stability import routh_of_tf
    from academic_core.domain.engineering.control.tf import make_tf
    t = dp.explain_routh("1", "1, 2, 3, 4, 5")
    passes(t)
    r = routh_of_tf(make_tf((D(1),), (D(1), D(2), D(3), D(4), D(5))))
    rows = events(t, "Fila ")
    assert [tuple(v.text for _n, v in e.values) for e in rows] == [tuple(row) for row in r.table]
    res = values(events(t, "Criterio de Routh")[0])
    assert res["verdict"].text == r.verdict == "UNSTABLE" and res["rhp_poles"].number == r.rhp_count == 2
    stable = dp.explain_routh("1", "1, 3, 3, 1")
    assert values(events(stable, "Criterio de Routh")[0])["verdict"].text == "STABLE"


def test_e04_p2_fft_stages_and_sampling():
    from academic_core.domain.engineering.dsp.dft import fft
    t = dp.explain_fft("1, 2, 3, 4, 0, 0, 0, 0")
    passes(t)
    rec = Recorder()
    out = fft([D(v) for v in (1, 2, 3, 4, 0, 0, 0, 0)], observer=rec)
    stages = rec.named("fft_stage")
    assert [s[1][0] for s in stages] == [2, 4, 8] and stages[-1][1][2] == out
    assert len(events(t, "Etapa de longitud")) == 3
    for e, (_n, (length, tw, data), _k) in zip(events(t, "Etapa"), stages):
        assert [values(e)[f"W.{j}"].text for j in range(len(tw))] == [det._cx(w) for w in tw]
    assert fft([D(1), D(2)]) == fft([D(1), D(2)], observer=Recorder())
    assert dp.explain_fft("1, 2, 3").outcome is Outcome.FAILED  # N = 3 is not a power of two: the engine refuses
    s = dp.explain_sampling("700", "1000")
    passes(s)
    assert values(events(s, "Frecuencia aparente")[0])["alias"].number == 300
    assert events(s, "Veredicto: ALIASED")


def test_e04_p3_reflection_chain():
    from academic_core.domain.engineering.rf.margins import vswr
    t = dp.explain_reflection("75+25j", "50")
    passes(t)
    g = DecimalComplex(D(25), D(25)) / DecimalComplex(D(125), D(25))
    assert values(events(t, "VSWR")[0])["VSWR"].number == vswr(g).value
    matched = dp.explain_reflection("50", "50")
    assert matched.outcome is Outcome.SUCCESS
    (rl,) = events(matched, "RL_dB")
    assert rl.kind is EventKind.WARNING and values(rl)["status"].text == "UNSUPPORTED"  # infinite RL declared


def test_e04_p4_bpsk_every_bit_and_seed():
    from academic_core.domain.engineering.comms.simulation import simulate_bpsk
    t = dp.explain_bpsk("4", "40", "11")
    passes(t)
    report = simulate_bpsk(D(4), 40, 11)
    assert simulate_bpsk(D(4), 40, 11, observer=Recorder()) == report
    bits = events(t, "Bit ")
    assert len(bits) == 40 and sum(values(b)["error"].text == "sí" for b in bits) == report.errors
    assert values(events(t, "Canal AWGN")[0])["seed"].number == 11
    big = dp.explain_bpsk("4", "100", "11")
    assert values(events(big, det.TRUNCATED)[0])["omitted_events"].number == 100 - dp.MAX_BITS


def test_e04_p5_link_budget_chain():
    from academic_core.domain.engineering.satcom.synthesis import forward_budget
    t = dp.explain_link_budget(LEG)
    passes(t)
    b = forward_budget(dp._leg(LEG))
    assert values(events(t, "EIRP")[0])["eirp_dbw"].number == b.eirp_dbw
    assert values(events(t, "C/N0")[0])["cn0_dbhz"].number == b.cn0_dbhz
    assert values(events(t, "Eb/N0")[0])["ebno_db"].number == b.ebno_db
    assert errors(dp.explain_link_budget("direction=downlink")) == ["INVALID_INPUT"]


# =============================================================== F15

@pytest.fixture
def core(tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    return app


def test_e04_f01_service_registry_and_replay(core):
    ex = core.explain
    calls = {"transient-newton": (DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005"),
             "ac-sweep-mna": (RC, "V1", "out", "0", "1 kHz"), "param-sweep": (DIODE, "R1", "500", "1000", "500"),
             "worst-case": (DIVIDER, "R1=900:1100", "out"), "dc-sensitivity": (DIODE, "R1"),
             "monte-carlo": (DIVIDER, "R1=uniform:900:1100", "5", "1", "out"), "routh": ("1", "1, 3, 3, 1"),
             "fft": ("1, 0, 0, 0",), "sampling": ("100", "1000"), "reflection": ("100", "50"),
             "bpsk": ("6", "10", "3"), "link-budget": (LEG,)}
    assert set(calls) == set(ex.DEEP_KINDS)
    for kind, args in calls.items():
        view = ex.explain_deep(kind, *args)
        assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.lessons, kind
        assert ex.replay(view.trace_json).status == EQUIVALENT
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        ex.explain_deep("spice", RC)


def _lab_run(core, definition, name="e04"):
    from academic_core.domain.engineering.lab.serialize import experiment_id
    session = core.lab.create_session(name, core.simulation.demo_divider())
    session, report = core.lab.add_experiment(session, definition)
    assert report.ok, report.errors
    return core.lab.run_experiment(session, experiment_id(definition, session.circuit))


def _lab_defs(core):
    from academic_core.domain.engineering.lab.model import AnalysisSpec, ExperimentDefinition
    obs = (ObservableSpec("node_voltage", "n2"),)
    r1 = ParamAddress("R1", "value")
    return {
        "PARAM_SWEEP": ExperimentDefinition(analysis=AnalysisSpec(kind="PARAM_SWEEP", param_sweep=ParamSweepConfig(
            "grid", target=r1, grid=GridSpec.linear(D(1000), D(3000), D(1000)), observables=obs))),
        "CORNERS": ExperimentDefinition(analysis=AnalysisSpec(kind="CORNERS", corners=WorstCaseConfig(
            ((r1, D(900), D(1100)),), obs))),
        "SENS_DC": ExperimentDefinition(analysis=AnalysisSpec(kind="SENS_DC", sens=SensitivityConfig((r1,), obs))),
        "MONTE_CARLO": ExperimentDefinition(analysis=AnalysisSpec(kind="MONTE_CARLO", mc=MCConfig(
            10, ((r1, UniformDist(D(900), D(1100))),), None, obs)), seed=5),
    }


@pytest.mark.parametrize("kind", ["PARAM_SWEEP", "CORNERS", "SENS_DC", "MONTE_CARLO"])
def test_e04_f02_virtual_lab_f8m_runs_re_observed(core, kind):
    session, summary = _lab_run(core, _lab_defs(core)[kind], f"e04-{kind.lower()}")
    view = core.explain.explain_lab_run_analysis(session, summary.run_id)
    assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.operation == "lab.run-analysis"
    trace = ExecutionTrace.from_json(view.trace_json)
    assert check(trace, "Comprobación: mismo resultado que el run").status is CheckStatus.PASS
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        core.explain.replay(view.trace_json)  # the lab replays its own runs
    assert core.lab.replay(session, summary.run_id).status == "EQUIVALENT"
    assert core.explain.explain_lab_run_analysis(session, summary.run_id).digest == view.digest


def test_e04_f03_unsupported_lab_kinds(core):
    from academic_core.domain.engineering.lab.model import AnalysisSpec, ExperimentDefinition
    session, summary = _lab_run(core, ExperimentDefinition(analysis=AnalysisSpec(kind="OP")), "e04-op")
    trace = core.explain.lab_run_analysis_trace(session, summary.run_id)
    assert trace.outcome is Outcome.FAILED and errors(trace) == ["UNSUPPORTED"]
    with pytest.raises(ValidationError, match="INVALID_INPUT"):
        core.explain.lab_run_analysis_trace("nope", "x")


# =============================================================== anti-fake-step

def test_e04_a01_nothing_unobserved_appears():
    t = dp.explain_transient_newton(DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005")
    rec = Recorder()
    solve_transient(nwt.parse_circuit_spec(DRC), cfg(("BE", "0.002", "0.0001", "0.000000001", "0.0005")),
                    observer=rec)
    multi = sum(len(r[11]) for *_x, kw in rec.named("transient_accept") + rec.named("transient_reject")
                for r in kw["newton"] if len(r[11]) > 1)
    assert len([e for e in t.events if "backtracking" in e.title]) == multi  # no invented trial
    assert len(events(t, "Intento rechazado")) == len([c for c in rec.named("transient_reject") if c[1][4] is not None])
    big = dp.explain_transient_newton(LADDER.replace("R8 n8 0 1kohm", "R8 n8 0 1kohm\nC1 n8 0 1uF"),
                                      "BE", "0.0002", "0.0001", "0.000000001", "0.0001")
    assert not any(n.startswith(("J.", "dx.", "x_k.")) for n in value_names(big))  # above 4×4: digest only
    assert "jacobian_digest" in value_names(big) or not [e for e in big.events if " · Newton " in e.title]
    for spec in (DIODE, DIVIDER):
        names = value_names(nwt.explain_nonlinear_dc(spec))
        assert not names & {"ID", "IS", "region", "VGS", "branch", "I_C"}  # no invented MOS/JFET/BJT value
    mc = dp.explain_monte_carlo(DIVIDER, "R1=uniform:900:1100", "3", "9", "out")
    assert len(events(mc, "Muestra ")) == 3  # no sample the engine did not produce
    fft_trace = dp.explain_fft("1, 1")
    assert len(events(fft_trace, "Etapa")) == 1  # N = 2: exactly one stage was executed


# =============================================================== determinism / bounds / security / performance

_CHILD = """
import sys
sys.path.insert(0, {src!r})
from academic_core.domain.execution import engineering_deep as dp, newton as nwt
ts = [dp.explain_transient_newton({drc!r}, "BE", "0.002", "0.0001", "0.000000001", "0.0005"),
      dp.explain_ac_sweep_mna({rc!r}, "V1", "out", "0", "10 Hz, 1 kHz"),
      dp.explain_param_sweep({diode!r}, "R1", "500", "1500", "500", "a"),
      dp.explain_monte_carlo({div!r}, "R1=uniform:900:1100", "10", "3", "out"),
      dp.explain_fft("1, 2, 3, 4"), dp.explain_bpsk("4", "20", "5"), nwt.explain_nonlinear_dc({nmos!r}),
      dp.explain_link_budget({leg!r}), nwt.explain_nonlinear_dc({pmos!r}), nwt.explain_nonlinear_dc({jfet!r}),
      nwt.explain_nonlinear_dc({zener!r})]
print(" ".join(t.digest() for t in ts))
"""


def test_e04_z01_identical_across_processes_and_hash_seeds():
    code = _CHILD.format(src=str(ROOT / "src"), drc=DRC, rc=RC, diode=DIODE, div=DIVIDER, nmos=NMOS, leg=LEG, pmos=PMOS,
                         jfet=JFET, zener=ZENER)
    outs = set()
    for seed in ("0", "11", "2024", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=300, check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1 and len(next(iter(outs)).split()) == 11


def test_e04_z02_boundedness(monkeypatch):
    monkeypatch.setattr(det, "MAX_DETAIL_EVENTS", 15)
    one = dp.explain_transient_newton(DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005")
    two = dp.explain_transient_newton(DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005")
    assert one.digest() == two.digest()
    (cut,) = events(one, det.TRUNCATED)
    assert cut.kind is EventKind.WARNING and values(cut)["omitted_events"].number > 0
    assert one.verification.status is VerificationStatus.PASS  # checks still cover the whole run
    monkeypatch.setattr(det, "MAX_DETAIL_EVENTS", 4000)
    full = dp.explain_transient_newton(MOS_RC, *MOS_ARGS)
    assert len(full.to_json().encode()) < MAX_JSON_BYTES
    assert ExecutionTrace.from_json(full.to_json()).digest() == full.digest()


def test_e04_z03_security_and_layering():
    banned_calls = {"eval", "exec", "compile", "__import__", "open", "globals", "locals", "getattr", "setattr"}
    banned_mods = {"pickle", "marshal", "importlib", "subprocess", "os", "sys", "shutil", "socket"}
    for f in (SRC / "domain" / "execution" / "engineering_deep.py", SRC / "domain" / "execution" / "newton.py",
              SRC / "domain" / "execution" / "analog_detail.py"):
        text = f.read_text(encoding="utf-8")
        assert "shell=True" not in text and "os.system" not in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (f.name, node.func.id)
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_mods
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned_mods
                assert not node.module.startswith(("academic_core.ui", "academic_core.application", "PySide6"))
    engines = [SRC / "domain" / "engineering" / p for p in
               ("mna/transient.py", "mna/nonlinear.py", "mna/mosfet.py", "mna/jfet.py", "mna/diode.py",
                "mna/analysis.py", "mna/sensitivity.py", "ac/response.py", "dsp/dft.py", "comms/simulation.py",
                "metrology/o2_propagate.py")]
    for f in engines:
        text = f.read_text(encoding="utf-8")
        assert "academic_core.domain.execution" not in text and "PySide6" not in text and "academic_core.ui" not in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__"}, (f.name, node.func.id)


def test_e04_z04_performance_with_and_without_observer():
    """Measured (numbers printed for the gate); observer overhead stays within generous bounds."""
    from academic_core.domain.engineering.comms.simulation import simulate_bpsk
    from academic_core.domain.engineering.dsp.dft import fft
    mos, rc, diode = nwt.parse_circuit_spec(MOS_RC), nwt.parse_circuit_spec(RC), nwt.parse_circuit_spec(DIODE)
    definition = ResponseDefinition("transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sens = SensitivityConfig((ParamAddress("R1", "value"), ParamAddress("V1", "value")))
    samples = [D(k % 5) for k in range(64)]
    cases = {"transient_newton": lambda o: solve_transient(mos, cfg(MOS_ARGS), observer=o),
             "ac_sweep": lambda o: frequency_response(rc, definition, ["10 Hz", "1 kHz", "100 kHz"], observer=o),
             "dc_sensitivity": lambda o: solve_dc_sensitivity(diode, sens, observer=o),
             "fft64": lambda o: fft(samples, observer=o),
             "bpsk200": lambda o: simulate_bpsk(D(4), 200, 3, observer=o)}
    for name, run in cases.items():
        best = {}
        for label, obs in (("none", None), ("recording", Recorder())):
            times = []
            for _ in range(3):
                start = time.perf_counter()
                run(obs)
                times.append(time.perf_counter() - start)
            best[label] = min(times)
        print(f"E0.4 performance {name}: none={best['none']:.4f}s recording={best['recording']:.4f}s "
              f"overhead={(best['recording'] / best['none'] - 1) * 100:.0f}%")
        assert best["recording"] <= 3 * best["none"] + 0.5
