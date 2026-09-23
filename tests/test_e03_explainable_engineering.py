"""E0.3 Explainable Engineering Completeness -- the engine internals E0.2 declared unavailable.

Sections:

- AC: the real complex MNA system A(jω), b(jω), x(jω) (F8-D3 and F8-J), magnitude, phase,
  verification, matrix bounds (FULL / OMITTED + digest)
- DC sweep: every point, the real initial guess (warm/cold), the real Newton iterations per point
- transient: method, time and state sequences, Δt, predictor, LTE, accepted/rejected attempts
- AC sweep: frequency sequence, point results, determinism
- transfer function: evaluation, magnitude, phase, the engine's ZPK form
- BJT (F8-I, certified): NPN, PNP, Ebers-Moll values, Jacobian block, Newton, errors
- F15: service registry, Virtual Lab «Explicar en detalle», replay, EQUIVALENT, unsupported kinds
- anti-fake-step: nothing that was not observed ever appears
- observer contract (observer=None inert), performance, boundedness, determinism, security
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

from academic_core.domain.engineering.ac.phasors import magnitude, phase
from academic_core.domain.engineering.ac.problem import build_ac_problem
from academic_core.domain.engineering.ac.small_signal import solve_small_signal_ac
from academic_core.domain.engineering.ac.solver import solve_ac
from academic_core.domain.engineering.control.tf import make_tf, tf_to_zpk
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.mna.analysis import GridSpec, ObservableSpec, ParamAddress, SweepConfig, \
    solve_dc_sweep
from academic_core.domain.engineering.mna.bjt import bjt_jacobian, bjt_terminal_currents, extract_bjt_params
from academic_core.domain.engineering.mna.nonlinear import solve_nonlinear_dc
from academic_core.domain.engineering.mna.transient import TransientConfig, solve_transient
from academic_core.domain.execution import (
    EQUIVALENT,
    MAX_JSON_BYTES,
    RESULT_DIFFERS,
    CheckStatus,
    EventKind,
    ExecutionTrace,
    Outcome,
    VerificationStatus,
    compare,
    verification_kind,
)
from academic_core.domain.execution import analog as ana
from academic_core.domain.execution import analog_detail as det
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
RLC = "* rlc\nV1 in 0 1V\nR1 in a 10ohm\nL1 a out 1mH\nC1 out 0 1uF\n.end\n"
DRC = f"* drc\nV1 in 0 5V\nR1 in a 1kohm\nD1 a out D\nC1 out 0 1uF\n{P1}\n.param C1 ic=0V\n.end\n"
QPARAMS = "Is=1e-15A Bf=100 Br=1 Nf=1 Nr=1 Vt=0.02585V"
NPN = f"* npn\nV1 vcc 0 5V\nV2 bb 0 1V\nR1 bb b 10kohm\nR2 vcc c 1kohm\nQ1 c b 0 Q\n.param Q1 polarity=NPN {QPARAMS}\n.end\n"
PNP = f"* pnp\nV1 vcc 0 5V\nV2 bb 0 4V\nR1 bb b 10kohm\nR2 c 0 1kohm\nQ1 c b vcc Q\n.param Q1 polarity=PNP {QPARAMS}\n.end\n"
TRANSIENT_ARGS = ("BE", "0.001", "0.0001", "0.000000001", "0.0001")
TIGHT_TR = ("TR", "0.005", "0.001", "0.000000001", "0.001", "1e-6", "1e-9")


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
        _immutable(v.re)
        _immutable(v.im)
        return
    assert isinstance(v, (tuple, Decimal, Fraction, str, bool, int, type(None))), type(v)
    if isinstance(v, tuple):
        for item in v:
            _immutable(item)


# =============================================================== AC

def test_e03_ac01_matrix_rhs_solution_are_the_engines():
    circuit = nwt.parse_circuit_spec(RC)
    rec = Recorder()
    sol = solve_ac(circuit, "1 kHz", observer=rec)
    (_n, (labels, matrix, rhs, kind, f_hz, omega), _k), = rec.named("ac_system")
    problem = build_ac_problem(circuit, sol.operating_point, sol.numeric_mode)
    assert matrix == tuple(tuple(r) for r in problem.matrix) and rhs == tuple(problem.rhs)  # exactly the solver's
    assert labels == ("V(in)", "V(out)", "I(V1)") and f_hz == D(1000) and omega == sol.operating_point.omega
    t = det.explain_ac_mna(RC, "1 kHz")
    a = values(events(t, "2. Matriz MNA compleja")[0])
    meta = values(events(t, "Matriz: metadatos")[0])
    assert meta["matrix_detail"].text == "FULL" and meta["size"].number == 3 and meta["digest"].text == det._digest(matrix)
    for i in range(3):
        for j in range(3):
            assert a[f"A.{i}.{j}"].text == det._cx(matrix[i][j])
    b = values(events(t, "3. Vector de excitación")[0])
    assert [b[f"b.{i}"].text for i in range(3)] == [det._cx(v) for v in rhs]
    (_n, (status, mode, _rank, x, _r, _b), _k), = rec.named("ac_outcome")
    xs = values(events(t, "6. Vector solución")[0])
    assert status == "solved" and xs["re.V_out"].number == x[1].re and xs["im.V_out"].number == x[1].im
    assert x[1] == sol.voltage_of("out")
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    assert compare(t, det.replay_detail(t)).status == EQUIVALENT


def test_e03_ac02_pedagogy_magnitude_phase_and_labelled_checks():
    t = det.explain_ac_mna(RC, "1 kHz")
    titles = [e.title for e in t.events if e.kind is EventKind.STEP]
    for step in ("1. Incógnitas", "2. Matriz MNA compleja", "3. Vector de excitación", "4. Ecuación 1",
                 "5. Resolución", "6. Vector solución", "7. Magnitud", "8. Fase"):
        assert any(x.startswith(step) for x in titles), step
    z = solve_ac(nwt.parse_circuit_spec(RC), "1 kHz").voltage_of("out")
    assert values(events(t, "7. Magnitud")[0])["abs.V_out"].number == magnitude(z)
    assert values(events(t, "8. Fase")[0])["arg.V_out"].number == phase(z)
    assert verification_kind(check(t, "9. Comprobación: magnitud")) == "NUMERIC"
    assert verification_kind(check(t, "9. Comprobación: A·x = b")) == "NUMERIC"  # HIGH_PRECISION solve
    assert verification_kind(check(t, "9. Comprobación: la solución observada es la publicada")) == "SYMBOLIC"
    assert all(c.check.status is CheckStatus.PASS for c in t.checks())
    exact = det.explain_ac_mna(DIVIDER, "1 kHz")  # resistive: rational system, exact elimination
    assert values(events(exact, "5. Resolución")[0])["numeric_mode"].text == "exact"
    axb = check(exact, "9. Comprobación: A·x = b")
    assert verification_kind(axb) == "SYMBOLIC" and axb.actual.text == "0"


def test_e03_ac03_matrix_bounds_full_and_omitted():
    t = det.explain_ac_mna(LADDER, "1 kHz")  # 9 unknowns > MAX_MATRIX_FULL
    rec = Recorder()
    solve_ac(nwt.parse_circuit_spec(LADDER), "1 kHz", observer=rec)
    matrix = rec.named("ac_system")[0][1][1]
    head = values(events(t, "2. Matriz MNA compleja A(jω) (detalle omitido)")[0])
    assert head["matrix_detail"].text == "OMITTED" and head["size"].number == 9
    assert head["digest"].text == det._digest(matrix)
    assert head["nonzero"].number == sum(1 for r in matrix for z in r if not z.is_zero_exact())
    assert not any(n.startswith("A.") for n in value_names(t)) and not events(t, "4. Ecuación 1")
    assert t.verification.status is VerificationStatus.PASS


def test_e03_ac04_small_signal_engine_and_errors():
    t = det.explain_ac_mna(RC, "1 kHz", "small-signal")
    rec = Recorder()
    ss = solve_small_signal_ac(nwt.parse_circuit_spec(RC), "1 kHz", observer=rec)
    assert rec.named("ac_system") and ss.status.value == "solved"
    assert values(events(t, "Punto de operación AC")[0])["engine"].text == "F8-J solve_small_signal_ac"
    assert t.verification.status is VerificationStatus.PASS
    bad = det.explain_ac_mna(RC, "-5 Hz")
    assert bad.outcome is Outcome.FAILED and events(bad, "MNA matrix unavailable")
    assert not any(n.startswith(("A.", "b.")) for n in value_names(bad))  # nothing invented when nothing observed
    assert det.explain_ac_mna(RC, "1 kHz", "spice").outcome is Outcome.FAILED
    with pytest.raises(ValidationError):
        det.explain_ac_mna(RC, 1000)


# =============================================================== DC sweep

def _sweep(spec, warm=True):
    return solve_dc_sweep(nwt.parse_circuit_spec(spec), SweepConfig(
        ParamAddress("V1", "value"), GridSpec.linear(D(0), D(2), D("0.5")), (ObservableSpec("node_voltage", "a"),),
        warm_start=warm))


def test_e03_s01_every_point_with_its_real_iterations_and_warm_start():
    t = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", "a")
    result = _sweep(DIODE)
    points = [e for e in events(t, "Punto ") if ":" in e.title]
    assert len(points) == len(result.points) == 5  # all points kept
    for e, p in zip(points, result.points):
        v = values(e)
        assert v["iterations"].number == p.iterations and v["init_mode"].text == p.init_mode
        assert v["obs.node_voltage:a"].number == p.observables["node_voltage:a"]
        assert len(events(t, f"Punto {p.index} · iteración")) == p.iterations  # the real Newton iterations
    rec = Recorder()
    solve_dc_sweep(nwt.parse_circuit_spec(DIODE), SweepConfig(
        ParamAddress("V1", "value"), GridSpec.linear(D(0), D(2), D("0.5")), (ObservableSpec("node_voltage", "a"),)),
        observer=rec)
    attempts, ends = rec.named("sweep_attempt"), rec.named("sweep_attempt_end")
    assert attempts[0][1][3] == "cold" and attempts[0][1][4] is None
    for k in range(1, len(attempts)):
        assert attempts[k][1][3] == "warm" and attempts[k][1][4] == ends[k - 1][1][4]  # x0 = previous solution
    for k, e in enumerate(events(t, "Punto 1 · arranque en caliente")):
        x0 = {n: v.number for n, v in e.values if n.startswith("x0.")}
        assert list(x0.values()) == list(attempts[1][1][4])
    assert check(t, "Comprobación: arranque en caliente").status is CheckStatus.PASS
    assert check(t, "Comprobación: iteraciones por punto").status is CheckStatus.PASS
    assert not events(t, "Iteraciones internas por punto no expuestas")  # now observable
    assert compare(t, det.replay_detail(t)).status == EQUIVALENT


def test_e03_s02_cold_start_is_stated_never_inferred():
    t = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", "a", warm_start=False)
    assert not events(t, "Punto 1 · arranque en caliente")
    assert len([e for e in t.events if "arranque en frío" in e.title]) == 5
    assert check(t, "Comprobación: arranque en caliente").status is CheckStatus.NOT_APPLICABLE
    result = _sweep(DIODE, warm=False)
    assert [values(e)["init_mode"].text for e in events(t, "Punto ") if ":" in e.title] == \
        [p.init_mode for p in result.points] == ["cold"] * 5


def test_e03_s03_sweep_bounds_and_determinism():
    big = det.explain_dc_sweep_detail(DIODE, "V1", "0", "10", "0.01")  # 1001 points > MAX_DETAIL_POINTS
    assert big.outcome is Outcome.FAILED and errors(big) == ["INVALID_LIMIT"]
    one = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", "a")
    two = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", "a")
    assert one.digest() == two.digest() and one.to_json() == two.to_json()
    with pytest.raises(ValidationError):
        det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", warm_start="yes")


# =============================================================== transient

def test_e03_r01_time_state_and_dt_sequences_are_the_engines():
    t = det.explain_transient_detail(RC_IC, *TRANSIENT_ARGS)
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), TransientConfig(
        "BE", D("0.001"), D("0.0001"), D("0.000000001"), D("0.0001"), D("1e-3"), D("1e-6")))
    steps = events(t, "Paso ")
    assert len(steps) == len(result.times) - 1
    for k, e in enumerate(steps):
        v = values(e)
        assert v["t_n"].number == result.times[k] and v["t_next"].number == result.times[k + 1]
        assert make_context().add(v["t_n"].number, v["dt"].number) == result.times[k + 1]  # t_(n+1) = t_n + Δt
        assert v["x_next.V_out"].number == result.node_trajectories["out"][k + 1]
        assert v["x_n.V_out"].number == result.node_trajectories["out"][k]
    method = events(t, "Método de integración")[0]
    assert method.title.endswith("Euler implícito (Backward Euler)") and values(method)["order"].number == 1
    assert not events(t, "Detalle interno por paso no expuesto")
    assert t.verification.status is VerificationStatus.PASS
    assert compare(t, det.replay_detail(t)).status == EQUIVALENT


def test_e03_r02_adaptive_decisions_and_rejections_are_real():
    t = det.explain_transient_detail(RC_IC, *TIGHT_TR)
    cfg = TransientConfig(*[TIGHT_TR[0]] + [D(v) for v in TIGHT_TR[1:]])
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), cfg)
    rejected = events(t, "Intento rechazado")
    assert len(rejected) == result.stats["rejected"] > 0
    for e in rejected:
        v = values(e)
        assert v["cause"].text == "lte" and v["E_max"].number > 1 and v["retry_dt"].number < v["dt_tried"].number
    for e in events(t, "Paso "):
        v = values(e)
        assert v["E_max"].number <= 1 and v["decision"].text.startswith("aceptado")
        assert any(n.startswith("E.C.") for n in values(e))  # the per-state LTE estimate
    assert check(t, "Comprobación: decisiones del control de paso").status is CheckStatus.PASS
    assert check(t, "Comprobación: rechazos").status is CheckStatus.PASS
    assert check(t, "Comprobación: iteraciones de Newton").status is CheckStatus.PASS


def test_e03_r03_method_startup_and_fixed_step():
    t = det.explain_transient_detail(RC_IC, "BDF2", *TIGHT_TR[1:])
    cfg = TransientConfig("BDF2", *[D(v) for v in TIGHT_TR[1:]])
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), cfg)
    startup = [e for e in events(t, "Paso ") if values(e)["methods"].text == "BE"]
    assert len(startup) == result.stats["be_startup_steps"] >= 1  # BDF2 starts with BE, as the engine reports
    assert events(t, "Método de integración: BDF2")
    fixed = det.explain_transient_detail(RC_IC, "TR", "0.001", "0.0001", "0.0001", "0.0001", adaptive=False)
    assert fixed.outcome is Outcome.SUCCESS and not events(fixed, "Intento rechazado")
    assert all(values(e)["next_dt"].text == "-" for e in events(fixed, "Paso "))  # no controller in fixed mode
    assert check(fixed, "Comprobación: decisiones del control de paso").status is CheckStatus.NOT_APPLICABLE


def test_e03_r04_nonlinear_transient_newton_iterations():
    t = det.explain_transient_detail(DRC, "BE", "0.002", "0.0001", "0.000000001", "0.0005")
    cfg = TransientConfig("BE", D("0.002"), D("0.0001"), D("0.000000001"), D("0.0005"), D("1e-3"), D("1e-6"))
    result = solve_transient(nwt.parse_circuit_spec(DRC), cfg)
    observed = sum(values(e)["newton_iterations"].number for e in events(t, "Paso ") + events(t, "Intento rechazado"))
    assert observed == result.stats["newton_total"] > 0
    for e in events(t, "Paso "):
        v = values(e)
        n = v["newton_iterations"].number
        assert ("newton_alpha" in v) == (n > 0)
        if n:
            assert len(v["newton_alpha"].text.split(", ")) == len(v["newton_residual"].text.split(", ")) == n
    assert t.verification.status is VerificationStatus.PASS


def test_e03_r05_inductor_states_and_failure():
    t = det.explain_transient_detail(RLC, "TR", "0.0005", "0.00001", "0.000000001", "0.00005")
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    init = values(events(t, "Estado inicial t = 0")[0])
    assert "i.L.L1" in init and "v.C.C1" in init
    small = det.explain_transient_detail(RC_IC, "BE", "0.001", "0.0001", "0.0001", "0.0001")
    assert small.outcome is Outcome.FAILED and errors(small) == ["TIMESTEP_TOO_SMALL"]  # the engine's verdict
    assert not events(small, "Paso ")  # it aborted before committing any step: none is shown
    (stop,) = events(small, "Intento fallido")  # the real attempt that stopped the integrator
    v = values(stop)
    assert v["cause"].text == "lte" and v["E_max"].number > 1 and v["retry_dt"].text == "-"


# =============================================================== AC sweep

def test_e03_w01_frequency_sequence_and_point_results():
    from academic_core.domain.engineering.ac.response import ResponseDefinition, frequency_response, voltage_between
    freqs = "10 Hz, 100 Hz, 1 kHz, 10 kHz"
    t = det.explain_ac_sweep(RC, "V1", "out", "0", freqs)
    sweep = frequency_response(nwt.parse_circuit_spec(RC), ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1")), freqs.split(", "))
    points = events(t, "Frecuencia ")
    assert [values(e)["f"].number for e in points] == [p.frequency.to_base() for p in sweep.points] == \
        [D(10), D(100), D(1000), D(10000)]
    for e, p in zip(points, sweep.points):
        v = values(e)
        assert v["re_H"].number == p.value.value.re and v["abs_H"].number == p.value.magnitude()
        assert v["arg_H"].number == p.value.phase() and v["status"].text == "solved"
    assert events(t, "internal iteration details unavailable")
    assert values(events(t, "Respuesta en frecuencia")[0])["digest"].text == sweep.digest
    assert t.verification.status is VerificationStatus.PASS
    assert compare(t, det.replay_detail(t)).status == EQUIVALENT
    assert t.digest() == det.explain_ac_sweep(RC, "V1", "out", "0", freqs).digest()


def test_e03_w02_ac_sweep_inputs_are_validated():
    assert errors(det.explain_ac_sweep(RC, "V1", "out", "0", "")) == ["INVALID_LIMIT"]
    assert errors(det.explain_ac_sweep(RC, "V1", "out", "0", "1 V")) == ["INVALID_INPUT"]
    assert errors(det.explain_ac_sweep(RC, "R1", "out", "0", "1 kHz")) == ["INVALID_INPUT"]
    many = ", ".join(f"{k} Hz" for k in range(1, det.MAX_DETAIL_POINTS + 2))
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):  # the input itself is bounded by the transport
        det.explain_ac_sweep(RC, "V1", "out", "0", many)


# =============================================================== transfer function

def test_e03_f01_evaluation_magnitude_phase_and_zpk():
    t = det.explain_tf_analysis("2", "1, 3, 2, 0", "1")
    h = make_tf((D(2),), (D(1), D(3), D(2), D(0)))
    value = h.evaluate(DecimalComplex(D(0), D(1)))
    zpk = tf_to_zpk(h)
    zp = values(events(t, "Polos y ceros")[0])
    assert zp["gain"].number == zpk.gain and [zp[f"pole.{k}"].text for k in range(3)] == [det._cx(p) for p in zpk.poles]
    assert not any(n.startswith("zero.") for n in zp)  # constant numerator: no finite zeros
    assert values(events(t, "Módulo y fase")[0])["magnitude"].number == value.modulus()
    assert values(events(t, "Evaluación en s = jω")[0])["re"].number == value.re
    assert check(t, "Comprobación: forma ZPK").status is CheckStatus.PASS
    assert verification_kind(check(t, "Comprobación: forma ZPK")) == "NUMERIC"
    assert compare(t, det.replay_detail(t)).status == EQUIVALENT
    e02 = ana.explain_tf_point("2", "1, 3, 2, 0", "1")  # the E0.2 trace is unchanged
    assert [e.title for e in e02.events if e.kind is not EventKind.INPUT] == \
        ["Función de transferencia", "Evaluación en s = jω", "Módulo y fase", "Comprobación: módulo"]


def test_e03_f02_zpk_unavailable_is_declared():
    t = det.explain_tf_analysis("0", "1, 1", "1")  # zero transfer: the engine has no ZPK form
    assert events(t, "Polos y ceros no disponibles") and not events(t, "Polos y ceros (")
    assert t.outcome is Outcome.SUCCESS and not events(t, "Evaluación en forma ZPK")


# =============================================================== BJT (F8-I certified)

def _bjt_trace_facts(spec):
    circuit = nwt.parse_circuit_spec(spec)
    q = next(c for c in circuit.components if c.type.upper() == "Q")
    return nwt.explain_nonlinear_dc(spec), extract_bjt_params(q), circuit


@pytest.mark.parametrize("spec, polarity, vf, vr", [(NPN, "NPN", "V_BE", "V_BC"), (PNP, "PNP", "V_EB", "V_CB")])
def test_e03_b01_ebers_moll_values_are_the_engines(spec, polarity, vf, vr):
    t, params, _circuit = _bjt_trace_facts(spec)
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    model = values(events(t, f"Modelo de Ebers-Moll: Q1 ({polarity})")[0])
    assert model["alpha_F"].number == params.alphaF and model["alpha_R"].number == params.alphaR
    ctx = make_context()
    for e in events(t, "Evaluación de Ebers-Moll: Q1"):
        v = values(e)
        vc, vb, ve = v["V_C"].number, v["V_B"].number, v["V_E"].number
        ic, ib, ie = bjt_terminal_currents(vc, vb, ve, params, ctx)
        assert (v["I_C"].number, v["I_B"].number, v["I_E"].number) == (ic, ib, ie)
        if polarity == "NPN":
            assert v[vf].number == ctx.subtract(vb, ve) and v[vr].number == ctx.subtract(vb, vc)
        else:
            assert v[vf].number == ctx.subtract(ve, vb) and v[vr].number == ctx.subtract(vc, vb)
    last = values(events(t, "Evaluación de Ebers-Moll: Q1")[-1])
    if polarity == "NPN":
        assert last["I_C"].number > 0 and last["I_E"].number < 0  # active NPN: current enters C, leaves E
    else:
        assert last["I_C"].number < 0 and last["I_E"].number > 0  # active PNP: the opposite
    assert check(t, "Comprobación: conservación en Q1").status is CheckStatus.PASS


@pytest.mark.parametrize("spec", [NPN, PNP])
def test_e03_b02_jacobian_block_and_newton(spec):
    t, params, circuit = _bjt_trace_facts(spec)
    ctx = make_context()
    rec = Recorder()
    result = solve_nonlinear_dc(circuit, observer=rec)
    iters = rec.named("newton_iteration")
    assert len(events(t, "Iteración ")) == len(iters) == result.provenance["iterations"]
    for (_n, _a, kw), e in zip(iters, events(t, "Evaluación de Ebers-Moll: Q1")):
        (_ref, _pol, vc, vb, ve, _vf, _vr, gf, gr, block), = kw["bjt_jacobians"]
        assert block == bjt_jacobian(vc, vb, ve, params, ctx)
        v = values(e)
        assert [v[f"J.{r}.{c}"].number for r in "CBE" for c in "CBE"] == [x for row in block for x in row]
    assert check(t, "Comprobación: el sistema lineal de Newton").status is CheckStatus.PASS
    assert not events(t, "Detalle de dispositivo no expuesto")  # the BJT is observed now


def test_e03_b03_bjt_errors_and_text_form():
    assert errors(nwt.explain_nonlinear_dc(NPN.replace("polarity=NPN", "polarity=XYZ"))) == ["INVALID_INPUT"]
    missing = nwt.explain_nonlinear_dc(NPN.replace(" Nr=1", ""))
    assert missing.outcome is Outcome.FAILED and errors(missing) == ["INVALID"]  # the engine's own verdict
    assert events(missing, "Detalle de dispositivo no expuesto") and not events(missing, "Evaluación de Ebers-Moll")
    circuit = nwt.parse_circuit_spec(NPN)
    assert circuit.components[-1].parameters["polarity"] == "NPN"
    assert nwt.explain_nonlinear_circuit(circuit).digest() == nwt.explain_nonlinear_dc(nwt.circuit_spec(circuit)).digest()
    assert compare(nwt.explain_nonlinear_dc(PNP), nwt.replay_nonlinear_dc(nwt.explain_nonlinear_dc(PNP))).status \
        == EQUIVALENT


def test_e03_b04_bjt_trace_argument_is_inert():
    params = extract_bjt_params(nwt.parse_circuit_spec(NPN).components[-1])
    ctx = make_context()
    args = (D("2.3"), D("0.74"), D(0), params, ctx)
    probe: list = []
    assert bjt_terminal_currents(*args) == bjt_terminal_currents(*args, probe)
    assert bjt_jacobian(*args) == bjt_jacobian(*args, [])
    assert len(probe) == 1 and len(probe[0]) == 4


# =============================================================== F15

@pytest.fixture
def core(tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    return app


def test_e03_g01_service_registry_and_replay(core):
    ex = core.explain
    for view in (ex.explain_detail("ac-mna", RC, "1 kHz"), ex.explain_detail("ac-sweep", RC, "V1", "out", "0", "1 kHz"),
                 ex.explain_detail("dc-sweep-detail", DIODE, "V1", "0", "1", "0.5"),
                 ex.explain_detail("transient-detail", RC_IC, *TRANSIENT_ARGS),
                 ex.explain_detail("tf-analysis", "2", "1, 3, 2, 0", "1"), ex.explain_detail("bjt-dc", NPN)):
        assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.lessons
        assert ex.replay(view.trace_json).status == EQUIVALENT
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        ex.explain_detail("noise", RC)
    with pytest.raises(ValidationError, match="INVALID_INPUT"):
        ex.explain_lab_run_detail("not a session", "x")


@pytest.mark.parametrize("circuit, kind", [(0, "OP"), (0, "DC_SWEEP"), (1, "TRANSIENT"), (2, "AC_POINT"),
                                           (2, "AC_SWEEP")])
def test_e03_g02_virtual_lab_explains_the_last_run_in_detail(qtbot, core, monkeypatch, circuit, kind):
    from academic_core.ui import errors as ui_errors
    from academic_core.ui.virtual_lab import VirtualLabPanel
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(ui_errors.QMessageBox, name, staticmethod(lambda *a, **k: None))
    panel = VirtualLabPanel(core)
    qtbot.addWidget(panel)
    panel.circuit.setCurrentIndex(circuit)
    panel.btn_new.click()
    panel.analysis.setCurrentText(kind)
    panel.btn_run.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=60000)
    panel.btn_explain_detail.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=120000)
    view = panel.explanation
    assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.operation == "lab.run-detail"
    text = panel.output.toPlainText()
    assert "Paso a paso" in text and f"Experimento {kind} (detalle)" in text
    trace = ExecutionTrace.from_json(view.trace_json)
    if kind != "AC_SWEEP":
        assert check(trace, "Comprobación: mismo resultado que el run").status is CheckStatus.PASS
    marker = {"OP": "Iteración 1 de Newton", "DC_SWEEP": "Punto 0 · arranque", "TRANSIENT": "Paso 1:",
              "AC_POINT": "2. Matriz MNA compleja", "AC_SWEEP": "Frecuencia 0"}[kind]
    assert events(trace, marker)
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        core.explain.replay(view.trace_json)  # the lab replays its own runs (result digest)
    assert core.lab.replay(panel.session, panel.last_run_id).status == "EQUIVALENT"
    assert core.explain.explain_lab_run_detail(panel.session, panel.last_run_id).digest == view.digest
    panel.btn_explain.click()  # the E0.2 explanation is still there, unchanged
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=60000)
    assert panel.explanation.operation == "lab.run"


def test_e03_g03_unsupported_lab_kind_is_declared(core):
    from academic_core.domain.engineering.lab.model import AnalysisSpec, ExperimentDefinition
    from academic_core.domain.engineering.lab.serialize import experiment_id
    from academic_core.domain.engineering.mna.analysis import ParamSweepConfig
    session = core.lab.create_session("e03-unsupported", core.simulation.demo_divider())
    ref = session.circuit.components[1].ref
    definition = ExperimentDefinition(analysis=AnalysisSpec(kind="PARAM_SWEEP", param_sweep=ParamSweepConfig(
        "grid", target=ParamAddress(ref, "value"), grid=GridSpec.linear(D(1000), D(3000), D(1000)))))
    session, report = core.lab.add_experiment(session, definition)
    assert report.ok, report.errors
    session, summary = core.lab.run_experiment(session, experiment_id(definition, session.circuit))
    trace = core.explain.lab_run_detail_trace(session, summary.run_id)
    assert trace.outcome is Outcome.FAILED and errors(trace) == ["UNSUPPORTED"]
    assert events(trace, "Explicación detallada no disponible para PARAM_SWEEP")
    with pytest.raises(ValidationError, match="UNKNOWN_RUN"):
        core.explain.lab_run_detail_trace(session, "nope#1")


# =============================================================== anti-fake-step

def test_e03_a01_no_invented_matrix_or_device_contribution():
    t = det.explain_ac_mna(RC, "1 kHz")
    rec = Recorder()
    solve_ac(nwt.parse_circuit_spec(RC), "1 kHz", observer=rec)
    labels, matrix, rhs = rec.named("ac_system")[0][1][:3]
    for i, e in enumerate(events(t, "4. Ecuación ")):
        terms = e.formula.split(" = ")[0].split(" + (")
        assert len(terms) == sum(1 for z in matrix[i] if not z.is_zero_exact())  # only observed non-zero stamps
    assert len(events(t, "4. Ecuación ")) == len(labels)
    for tr in (ana.explain_ac(RC, "1 kHz"), det.explain_transient_detail(RC_IC, *TRANSIENT_ARGS),
               det.explain_ac_sweep(RC, "V1", "out", "0", "1 kHz")):
        assert not any(n.startswith(("A.", "J.")) for n in value_names(tr))


def test_e03_a02_no_invented_iteration_derivative_or_method():
    sweep = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", "a")
    assert sum(1 for e in sweep.events if "· iteración" in e.title) == sum(p.iterations for p in _sweep(DIODE).points)
    tr = det.explain_transient_detail(RC_IC, *TRANSIENT_ARGS)
    names = value_names(tr)
    assert not any(n.lower().startswith(("deriv", "dvdt", "dxdt", "rk", "k1")) for n in names)
    assert [e.title for e in events(tr, "Método de integración")] == \
        ["Método de integración: Euler implícito (Backward Euler)"]
    invalid = det.explain_transient_detail("* bad\nV1 a 0 1V\nX1 a 0 1ohm\n.end\n", *TRANSIENT_ARGS)
    assert invalid.outcome is Outcome.FAILED and not events(invalid, "Método de integración")


def test_e03_a03_no_invented_rejection_or_warm_start():
    fixed = det.explain_transient_detail(RC_IC, "BE", "0.001", "0.0001", "0.0001", "0.0001", adaptive=False)
    assert not events(fixed, "Intento rechazado")
    t = det.explain_transient_detail(RC_IC, *TIGHT_TR)
    cfg = TransientConfig(*[TIGHT_TR[0]] + [D(v) for v in TIGHT_TR[1:]])
    assert len(events(t, "Intento rechazado")) == solve_transient(nwt.parse_circuit_spec(RC_IC), cfg).stats["rejected"]
    cold = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5", warm_start=False)
    assert not any("caliente" in e.title for e in events(cold, "Punto "))
    assert check(cold, "Comprobación: arranque en caliente").status is CheckStatus.NOT_APPLICABLE
    first = det.explain_dc_sweep_detail(DIODE, "V1", "0", "2", "0.5")
    assert events(first, "Punto 0 · arranque en frío")  # the first point never has a previous solution


def test_e03_a04_no_invented_bjt_current():
    for spec in (DIODE, DIVIDER.replace("12V", "1V")):
        t = nwt.explain_nonlinear_dc(spec)
        assert not any(n.startswith(("I_C", "I_B", "I_E", "I_F", "I_R")) for n in value_names(t))
        assert not events(t, "Modelo de Ebers-Moll")
    bad = nwt.explain_nonlinear_dc(NPN.replace(" Bf=100", ""))
    assert not events(bad, "Evaluación de Ebers-Moll") and not events(bad, "Modelo de Ebers-Moll")


# =============================================================== observer contract / performance / bounds

def test_e03_z01_observer_none_is_inert_for_every_modified_engine():
    rc = nwt.parse_circuit_spec(RC)
    a, b = solve_ac(rc, "1 kHz"), solve_ac(rc, "1 kHz", observer=Recorder())
    assert a.to_dict() == b.to_dict() and a.diagnostics == b.diagnostics and a.digest == b.digest
    a, b = solve_small_signal_ac(rc, "1 kHz").to_dict(), solve_small_signal_ac(rc, "1 kHz", observer=Recorder()).to_dict()
    for doc in (a, b):  # the certified linear-DC provenance carries a wall-clock timestamp: excluded (documented)
        doc["dc_operating_point"]["provenance"].pop("timestamp")
    assert a == b
    for warm in (True, False):
        x = _sweep(DIODE, warm)
        rec = Recorder()
        y = solve_dc_sweep(nwt.parse_circuit_spec(DIODE), SweepConfig(
            ParamAddress("V1", "value"), GridSpec.linear(D(0), D(2), D("0.5")), (ObservableSpec("node_voltage", "a"),),
            warm_start=warm), observer=rec)
        assert x.to_dict() == y.to_dict() and x.digest == y.digest and [p.iterations for p in x.points] == \
            [p.iterations for p in y.points]
    for spec, cfg in ((RC_IC, TransientConfig(*[TIGHT_TR[0]] + [D(v) for v in TIGHT_TR[1:]])),
                      (DRC, TransientConfig("BE", D("0.002"), D("0.0001"), D("0.000000001"), D("0.0005"), D("1e-3"),
                                            D("1e-6")))):
        c = nwt.parse_circuit_spec(spec)
        x, y = solve_transient(c, cfg), solve_transient(c, cfg, observer=Recorder())
        assert x.to_dict() == y.to_dict() and x.diagnostics == y.diagnostics and x.stats == y.stats
    for spec in (NPN, PNP, NPN.replace(" Nr=1", "")):
        c = nwt.parse_circuit_spec(spec)
        x, y = solve_nonlinear_dc(c), solve_nonlinear_dc(c, observer=Recorder())
        assert x.status is y.status and x.to_dict() == y.to_dict() and x.diagnostics == y.diagnostics


def test_e03_z02_performance_with_and_without_observer():
    """Observer overhead stays reasonable (measured, generous bounds; numbers printed for the gate)."""
    rc, diode = nwt.parse_circuit_spec(RC), nwt.parse_circuit_spec(DIODE)
    cfg = TransientConfig("BE", D("0.001"), D("0.0001"), D("0.000000001"), D("0.0001"), D("1e-3"), D("1e-6"))
    sweep = SweepConfig(ParamAddress("V1", "value"), GridSpec.linear(D(0), D(2), D("0.25")))
    cases = {"ac": lambda o: solve_ac(rc, "1 kHz", observer=o),
             "dc_sweep": lambda o: solve_dc_sweep(diode, sweep, observer=o),
             "transient": lambda o: solve_transient(nwt.parse_circuit_spec(RC_IC), cfg, observer=o)}
    for name, run in cases.items():
        best = {}
        for label, obs in (("none", None), ("recording", Recorder())):
            times = []
            for _ in range(3):
                start = time.perf_counter()
                run(obs)
                times.append(time.perf_counter() - start)
            best[label] = min(times)
        print(f"E0.3 performance {name}: none={best['none']:.4f}s recording={best['recording']:.4f}s")
        assert best["recording"] <= 3 * best["none"] + 0.5


def test_e03_z03_boundedness_and_trace_truncated(monkeypatch):
    monkeypatch.setattr(det, "MAX_DETAIL_EVENTS", 20)
    one = det.explain_transient_detail(RC_IC, *TIGHT_TR)
    two = det.explain_transient_detail(RC_IC, *TIGHT_TR)
    assert one.digest() == two.digest()  # deterministic truncation
    (cut,) = events(one, det.TRUNCATED)
    cfg = TransientConfig(*[TIGHT_TR[0]] + [D(v) for v in TIGHT_TR[1:]])
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), cfg)
    attempts = len(result.times) - 1 + result.stats["rejected"]
    assert cut.kind is EventKind.WARNING and values(cut)["omitted_events"].number == attempts - 20
    assert len(events(one, "Paso ")) + len(events(one, "Intento rechazado")) == 20
    assert one.verification.status is VerificationStatus.PASS  # the checks still cover the whole run
    monkeypatch.setattr(det, "MAX_DETAIL_EVENTS", 4000)
    big = det.explain_transient_detail(RC_IC, *TIGHT_TR)  # 3051 attempts: the byte budget truncates, explicitly
    assert events(big, det.TRUNCATED) and len(big.to_json().encode()) < MAX_JSON_BYTES
    assert big.verification.status is VerificationStatus.PASS
    small = det.explain_transient_detail(RC_IC, *TRANSIENT_ARGS)
    assert not events(small, det.TRUNCATED)
    sweep = det.explain_dc_sweep_detail(DIODE, "V1", "0", "4.99", "0.01")  # 500 points: all kept
    assert len([e for e in events(sweep, "Punto ") if ":" in e.title]) == 500
    assert len(sweep.to_json().encode()) < MAX_JSON_BYTES
    assert ExecutionTrace.from_json(sweep.to_json()).digest() == sweep.digest()  # strict decode round trip


def test_e03_z04_first_difference_and_canonical_json():
    a = det.explain_ac_mna(RC, "1 kHz")
    b = det.explain_ac_mna(RC.replace("1kohm", "2kohm"), "1 kHz")
    report = compare(a, b)
    assert report.status == RESULT_DIFFERS and report.first_difference
    assert ExecutionTrace.from_json(a.to_json()).to_json() == a.to_json()


_CHILD = """
import sys
sys.path.insert(0, {src!r})
from academic_core.domain.execution import analog_detail as det, newton as nwt
ts = [det.explain_ac_mna({rc!r}, "1 kHz"), det.explain_ac_mna({rc!r}, "1 kHz", "small-signal"),
      det.explain_dc_sweep_detail({diode!r}, "V1", "0", "1", "0.5"),
      det.explain_transient_detail({rcic!r}, "BE", "0.001", "0.0001", "0.000000001", "0.0001"),
      det.explain_ac_sweep({rc!r}, "V1", "out", "0", "10 Hz, 1 kHz"), det.explain_tf_analysis("2", "1, 3, 2, 0", "1"),
      nwt.explain_nonlinear_dc({npn!r}), nwt.explain_nonlinear_dc({pnp!r})]
print(" ".join(t.digest() for t in ts))
"""


def test_e03_z05_identical_across_processes_and_hash_seeds():
    code = _CHILD.format(src=str(ROOT / "src"), rc=RC, diode=DIODE, rcic=RC_IC, npn=NPN, pnp=PNP)
    outs = set()
    for seed in ("0", "11", "2024", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=300, check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1 and len(next(iter(outs)).split()) == 8


def test_e03_z06_security_and_layering():
    banned_calls = {"eval", "exec", "compile", "__import__", "open", "globals", "locals", "getattr", "setattr"}
    banned_mods = {"pickle", "marshal", "importlib", "subprocess", "os", "sys", "shutil", "socket"}
    for f in (SRC / "domain" / "execution" / "analog_detail.py", SRC / "domain" / "execution" / "newton.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (f.name, node.func.id)
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_mods
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned_mods
                assert not node.module.startswith(("academic_core.ui", "academic_core.application", "PySide6"))
    engines = [SRC / "domain" / "engineering" / p for p in
               ("ac/solver.py", "ac/small_signal.py", "mna/analysis.py", "mna/transient.py", "mna/nonlinear.py",
                "mna/bjt.py", "lab/run.py")]
    for f in engines:
        text = f.read_text(encoding="utf-8")
        assert "academic_core.domain.execution" not in text and "TraceRecorder" not in text  # no trace built inside
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__"}, (f.name, node.func.id)
    for f in (SRC / "domain" / "engineering" / "mna" / "nonlinear.py", SRC / "domain" / "engineering" / "mna" / "bjt.py"):
        assert "float(" not in f.read_text(encoding="utf-8")
