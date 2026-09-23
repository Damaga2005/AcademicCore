"""E0.2 Explainable Engineering Expansion -- analog engines.

Sections:

- F8-H (Shockley nonlinear DC): model parameters, real device evaluations,
  real Newton data (x, F, J, Δx, α), real backtracking trials, per-node
  KCL residual, statuses, multinode layout
- linear MNA / DC: the real A and b, exact solution, KCL rows, statuses
- DC sweep, AC, transient, transfer function (only what is observable)
- F15: service registry, Virtual Lab explanation, replay
- anti-fake-step: no fictitious Jacobian, conversion, current, iteration,
  backtracking or KCL decomposition
- observer hardening, determinism across processes, security
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application.explain_render import build_view
from academic_core.domain.engineering.ac.solver import solve_ac
from academic_core.domain.engineering.control.tf import make_tf
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.mna.diode import extract_diode_params, shockley_conductance, shockley_current
from academic_core.domain.engineering.mna.nonlinear import NonlinearStatus, solve_nonlinear_dc
from academic_core.domain.engineering.mna.problem import build_mna_problem, unknown_labels
from academic_core.domain.engineering.mna.solver import solve_linear_dc
from academic_core.domain.execution import (
    EQUIVALENT,
    CheckStatus,
    EventKind,
    Outcome,
    VerificationStatus,
    compare,
    verification_kind,
)
from academic_core.domain.execution import analog as ana
from academic_core.domain.execution import newton as nwt
from academic_core.errors import ValidationError

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
D = Decimal
P1 = ".param D1 Is=1e-14A n=1 Vt=0.02585V"
DIODE = f"* diode\nV1 in 0 5V\nR1 in a 1kohm\nD1 a 0 D\n{P1}\n.end\n"
TWO = ("* two\nV1 in 0 3V\nR1 in a 220ohm\nD1 a b D\nD2 b 0 D\n" + P1 +
       "\n.param D2 Is=2e-14A n=1.5 Vt=0.02585V\n.end\n")
CURRENT_FED = f"* ifed\nI1 0 a 1mA\nR1 a 0 1kohm\nD1 a 0 D\n{P1}\n.end\n"
DIVERGES = f"* rev\nI1 0 a 1A\nD1 0 a D\nR1 a 0 1Gohm\n{P1}\n.end\n"
SINGULAR = f"* big\nI1 0 a 1000A\nD1 a 0 D\n{P1}\n.end\n"
DIVIDER = "* divider\nV1 in 0 12V\nR1 in out 1kohm\nR2 out 0 2kohm\n.end\n"
LADDER = "* ladder\nV1 n1 0 10V\n" + "".join(f"R{k} n{k} n{k + 1} 1kohm\n" for k in range(1, 8)) + "R8 n8 0 1kohm\n.end\n"
RC = "* rc\nV1 in 0 1V\nR1 in out 1kohm\nC1 out 0 1uF\n.end\n"
RC_IC = "* rc\nV1 in 0 1V\nR1 in out 1kohm\nC1 out 0 1uF\n.param C1 ic=0V\n.end\n"


def events(trace, prefix):
    return [e for e in trace.events if e.title.startswith(prefix)]


def values(event):
    return dict(event.values)


def errors(trace):
    return [e.error.reason for e in trace.events if e.kind is EventKind.ERROR]


class Recorder:
    """Records every observer call; asserts every received value is immutable."""

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


def _immutable(v):
    assert isinstance(v, (tuple, Decimal, Fraction, str, bool, int, type(None))), type(v)
    if isinstance(v, tuple):
        for item in v:
            _immutable(item)


# =============================================================== F8-H Shockley

def test_e02_h01_shockley_parameters_are_the_solver_parameters():
    t = nwt.explain_nonlinear_dc(TWO)
    circuit = nwt.parse_circuit_spec(TWO)
    for c in circuit.components:
        if c.type == "D":
            p = extract_diode_params(c)
            model = values(events(t, f"Modelo de Shockley: {c.ref}")[0])
            assert (model["Is"].number, model["n"].number, model["Vt"].number) == (p.Is, p.n, p.Vt)
            assert events(t, f"Modelo de Shockley: {c.ref}")[0].formula == "I = Is·(exp(Vd/(n·Vt)) − 1)"


def test_e02_h02_device_evaluations_are_real():
    t = nwt.explain_nonlinear_dc(TWO)
    circuit = nwt.parse_circuit_spec(TWO)
    params = {c.ref: extract_diode_params(c) for c in circuit.components if c.type == "D"}
    ctx = make_context()
    shockley = events(t, "Evaluación de Shockley")
    assert len(shockley) == len(events(t, "Iteración ")) > 0
    for e in shockley:
        v = values(e)
        for ref, p in params.items():
            assert v[f"I_next.{ref}"].number == shockley_current(v[f"Vd_next.{ref}"].number, p, ctx)
            assert v[f"g_k.{ref}"].number == shockley_conductance(v[f"Vd_k.{ref}"].number, p, ctx)


def test_e02_h03_newton_data_is_the_real_solve():
    t = nwt.explain_nonlinear_dc(DIODE)
    reference = solve_nonlinear_dc(nwt.parse_circuit_spec(DIODE))
    assert len(events(t, "Iteración ")) == reference.provenance["iterations"]
    check = [c.check for c in t.checks() if c.check.what.startswith("J·Δx + F = 0")][0]
    assert check.status is CheckStatus.PASS and verification_kind(check) == "NUMERIC"
    first = values(events(t, "Iteración 1 de Newton")[0])
    for name in ("x_k.a", "F_k.a", "dx.a", "J.a.a", "alpha", "step_peak", "kcl_residual", "res_ok", "step_ok"):
        assert name in first


def test_e02_h04_backtracking_trials_are_the_solver_trials():
    rec = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(TWO), observer=rec)
    iterations = [c for c in rec.calls if c[0] == "newton_iteration"]
    t = nwt.explain_nonlinear_dc(TWO)
    trials = events(t, "Backtracking (iteración")
    expected = sum(len(c[2]["trials"]) for c in iterations if len(c[2]["trials"]) > 1)
    assert len(trials) == expected > 0
    for c in iterations:
        tr = c[2]["trials"]
        assert tr[-1][2] is True and all(x[2] is False for x in tr[:-1])  # only the last is accepted
        assert [x[0] for x in tr] == [D(1) / (2 ** k) for k in range(len(tr))]  # α halves from 1
        assert len(tr) == c[1][2] + 1  # halvings + 1 trials
    for e in trials:
        v = values(e)
        if v["decision"].text == "aceptado":
            assert v["trial_residual"].number < v["residual_to_beat"].number


def test_e02_h05_per_node_kcl_is_the_residual_row_only():
    rec = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(TWO), observer=rec)
    last = [c for c in rec.calls if c[0] == "newton_iteration"][-1][2]["residual"]
    t = nwt.explain_nonlinear_dc(TWO)
    kcl = values(events(t, "KCL por nodo en la solución")[0])
    labels = unknown_labels(build_mna_problem(nwt.parse_circuit_spec(TWO), allow_diodes=True))
    for k, lab in enumerate(labels):
        name = f"KCL.{lab[2:-1]}" if lab.startswith("V(") else f"aux.{nwt._label(lab)}"
        assert kcl[name].number == last[k]
    assert not any(n.startswith("term") for n in kcl)  # no invented per-element decomposition


def test_e02_h06_statuses_are_never_success():
    div = nwt.explain_nonlinear_dc(DIVERGES)
    assert div.outcome is Outcome.FAILED and errors(div) == ["DIVERGED"]
    failed = events(div, "Iteración 1 fallida")
    assert failed and "backtracking exhausted" in values(failed[0])["reason"].text
    assert len(events(div, "Backtracking (iteración 1)")) == 11  # the 11 real halvings, all rejected
    assert all(values(e)["decision"].text == "rechazado" for e in events(div, "Backtracking (iteración 1)"))
    sing = nwt.explain_nonlinear_dc(SINGULAR)
    assert errors(sing) == ["SINGULAR_JACOBIAN"] and events(sing, "Iteración 2 fallida")
    inv = nwt.explain_nonlinear_dc(DIODE.replace(P1 + "\n", ""))
    assert errors(inv) == ["INVALID"] and inv.result is None


def test_e02_h07_multinode_layout_is_real():
    fed = nwt.explain_nonlinear_dc(CURRENT_FED)
    kcl = values(events(fed, "KCL por nodo en la solución")[0])
    assert set(kcl) == {"KCL.a"}  # no voltage source: no auxiliary current exists, none is shown
    two = values(events(nwt.explain_nonlinear_dc(TWO), "KCL por nodo en la solución")[0])
    assert set(two) == {"KCL.a", "KCL.b", "KCL.in", "aux.I_V1"}


# =============================================================== linear MNA / DC

def test_e02_l01_matrix_and_rhs_are_the_solver_system():
    t = ana.explain_linear_dc(DIVIDER)
    problem = build_mna_problem(nwt.parse_circuit_spec(DIVIDER))
    v = values(events(t, "Sistema MNA A·x = b")[0])
    n = problem.size
    for i in range(n):
        assert v[f"b.{i}"].text == ana._frac(problem.rhs[i])
        for j in range(n):
            assert v[f"A.{i}.{j}"].text == ana._frac(problem.matrix[i][j])
    assert [x.text for _n, x in events(t, "Incógnitas")[0].values] == list(unknown_labels(problem))


def test_e02_l02_solution_kcl_rows_and_checks():
    t = ana.explain_linear_dc(DIVIDER)
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    sol = values(events(t, "Solución x")[0])
    assert (sol["x0.V_in"].text, sol["x1.V_out"].text, sol["x2.I_V1"].text) == ("12", "8", "-1/250")
    problem = build_mna_problem(nwt.parse_circuit_spec(DIVIDER))
    for e in events(t, "KCL en el nodo"):
        v = values(e)
        node = e.title.split()[-1]
        row = problem.node_index[node]
        nonzero = [j for j in range(problem.size) if problem.matrix[row][j] != 0]
        assert len([k for k in v if k.startswith("term.")]) == len(nonzero)  # exactly the observed row
        assert v["residual"].text == "0"
    kinds = {c.check.what: verification_kind(c.check) for c in t.checks()}
    assert kinds["A·x = b en aritmética racional exacta"] == "SYMBOLIC"
    assert compare(t, ana.replay_analog(t)).status == EQUIVALENT


def test_e02_l03_large_systems_and_statuses():
    big = ana.explain_linear_dc(LADDER)
    assert "detalle omitido" in values(events(big, "Sistema MNA")[0])["matrix"].text
    assert big.verification.status is VerificationStatus.PASS
    inconsistent = ana.explain_linear_dc("* bad\nV1 a 0 1V\nV2 a 0 2V\n.end\n")
    assert errors(inconsistent) == ["INCONSISTENT"] and events(inconsistent, "Sistema MNA")
    unsupported = ana.explain_linear_dc(f"* d\nV1 a 0 1V\nR1 a b 1ohm\nD1 b 0 D\n{P1}\n.end\n")
    assert errors(unsupported) == ["UNSUPPORTED"]
    assert any(e.title == "MNA matrix unavailable" for e in unsupported.events)  # never reconstructed
    floating = ana.explain_linear_dc("* f\nV1 a 0 1V\nR1 b c 1ohm\n.end\n")
    assert floating.outcome is Outcome.FAILED


def test_e02_l04_linear_observer_equivalence():
    for spec in (DIVIDER, LADDER, "* bad\nV1 a 0 1V\nV2 a 0 2V\n.end\n"):
        circuit = nwt.parse_circuit_spec(spec)
        rec = Recorder()
        a, b = solve_linear_dc(circuit), solve_linear_dc(circuit, observer=rec)
        da, db = a.to_dict(), b.to_dict()
        for d in (da, db):  # the certified provenance carries a wall-clock timestamp (not semantic)
            d.get("provenance", {}).pop("timestamp", None)
        assert da == db and a.status is b.status
        assert [c[0] for c in rec.calls] == ["mna_system", "linear_outcome"]


# =============================================================== DC sweep / AC / transient / TF

def test_e02_s01_dc_sweep_points_are_the_engine_points():
    from academic_core.domain.engineering.mna.analysis import GridSpec, ObservableSpec, ParamAddress, SweepConfig, \
        solve_dc_sweep
    t = ana.explain_dc_sweep(DIODE, "V1", "0", "2", "0.5", "a")
    result = solve_dc_sweep(nwt.parse_circuit_spec(DIODE), SweepConfig(
        ParamAddress("V1", "value"), GridSpec.linear(D(0), D(2), D("0.5")), (ObservableSpec("node_voltage", "a"),)))
    points = events(t, "Punto ")
    assert len(points) == len(result.points) == 5
    for e, p in zip(points, result.points):
        v = values(e)
        assert v["iterations"].number == p.iterations and v["init_mode"].text == p.init_mode
        assert v["obs.node_voltage:a"].number == p.observables["node_voltage:a"]
    assert any("no expuestas" in e.title for e in t.events)
    assert compare(t, ana.replay_analog(t)).status == EQUIVALENT


def test_e02_s02_ac_is_the_engine_solution():
    from academic_core.domain.engineering.ac.phasors import magnitude, phase
    t = ana.explain_ac(RC, "1 kHz")
    sol = solve_ac(nwt.parse_circuit_spec(RC), "1 kHz")
    v = values(events(t, "Fasores de nodo")[0])
    z = sol.voltage_of("out")
    assert v["abs_V.out"].number == magnitude(z) and v["arg_V.out"].number == phase(z)
    assert any(e.title == "MNA matrix unavailable" for e in t.events)
    assert t.verification.status is VerificationStatus.PASS
    assert compare(t, ana.replay_analog(t)).status == EQUIVALENT
    bad = ana.explain_ac(RC, "-5 Hz")
    assert bad.outcome is Outcome.FAILED


def test_e02_s03_transient_history_and_honest_gaps():
    from academic_core.domain.engineering.mna.transient import TransientConfig, solve_transient
    args = ("BE", "0.001", "0.0001", "0.000000001", "0.0001")
    t = ana.explain_transient(RC_IC, *args)
    result = solve_transient(nwt.parse_circuit_spec(RC_IC), TransientConfig(
        "BE", D("0.001"), D("0.0001"), D("0.000000001"), D("0.0001"), D("1e-3"), D("1e-6")))
    steps = events(t, "Paso aceptado")
    assert len(steps) == min(len(result.times), ana.MAX_POINTS)
    for e, k in zip(steps, range(len(result.times))):
        assert values(e)["t"].number == result.times[k]
        assert values(e)["V.out"].number == result.node_trajectories["out"][k]
    assert any(e.title == "Detalle interno por paso no expuesto" for e in t.events)
    assert compare(t, ana.replay_analog(t)).status == EQUIVALENT
    small = ana.explain_transient(RC_IC, "BE", "0.001", "0.0001", "0.0001", "0.0001", adaptive=True)
    assert small.outcome is Outcome.FAILED  # TIMESTEP_TOO_SMALL is reported, never smoothed over


def test_e02_s04_transfer_function_point():
    t = ana.explain_tf_point("2", "1, 3, 2, 0", "1")
    value = make_tf((D(2),), (D(1), D(3), D(2), D(0))).evaluate(DecimalComplex(D(0), D(1)))
    v = values(events(t, "Módulo y fase")[0])
    assert v["magnitude"].number == value.modulus()
    assert t.verification.status is VerificationStatus.PASS
    assert compare(t, ana.replay_analog(t)).status == EQUIVALENT
    assert ana.explain_tf_point("1", "a", "1").outcome is Outcome.FAILED


# =============================================================== F15

@pytest.fixture
def core(tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    return app


def test_e02_f01_service_registry_and_replay(core):
    ex = core.explain
    for view in (ex.explain_analog("linear-dc", DIVIDER), ex.explain_analog("dc-sweep", DIODE, "V1", "0", "1", "0.5"),
                 ex.explain_analog("ac", RC, "1 kHz"), ex.explain_analog("tf-point", "2", "1, 3, 2, 0", "1"),
                 ex.explain_analog("transient", RC_IC, "BE", "0.001", "0.0001", "0.000000001", "0.0001")):
        assert view.outcome == "SUCCESS" and view.lessons
        assert ex.replay(view.trace_json).status == EQUIVALENT
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        ex.explain_analog("noise", DIVIDER)


@pytest.mark.parametrize("circuit, kind", [(0, "OP"), (0, "DC_SWEEP"), (1, "TRANSIENT"), (2, "AC_POINT"),
                                           (2, "AC_SWEEP")])
def test_e02_f02_virtual_lab_explains_the_last_run(qtbot, core, monkeypatch, circuit, kind):
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
    panel.btn_explain.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=60000)
    view = panel.explanation
    assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.operation == "lab.run"
    text = panel.output.toPlainText()
    assert "Paso a paso" in text and f"Experimento {kind}" in text
    if kind == "AC_SWEEP":
        assert "Explicación detallada no disponible para AC_SWEEP" in text  # UNSUPPORTED, declared
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        core.explain.replay(view.trace_json)  # the lab replays its own runs (result digest)
    assert core.lab.replay(panel.session, panel.last_run_id).status == "EQUIVALENT"
    again = core.explain.explain_lab_run(panel.session, panel.last_run_id)
    assert again.digest == view.digest


def test_e02_f03_lab_errors(core):
    with pytest.raises(ValidationError, match="INVALID_INPUT"):
        core.explain.explain_lab_run("not a session", "x")


# =============================================================== anti-fake-step

def test_e02_a01_no_fictitious_jacobian_or_matrix():
    five = f"* five\nV1 in 0 3V\nR1 in a 220ohm\nR2 a b 100ohm\nD1 b c D\nD2 c 0 D\n{P1}\n" \
           ".param D2 Is=2e-14A n=1.5 Vt=0.02585V\n.end\n"
    t = nwt.explain_nonlinear_dc(five)
    for e in events(t, "Iteración "):
        assert not any(n.startswith("J.") for n in values(e)) and "detalle omitido" in values(e)["jacobian"].text
    for tr in (ana.explain_ac(RC, "1 kHz"), ana.explain_transient(RC_IC, "BE", "0.001", "0.0001", "0.000000001", "0.0001")):
        assert not any(n.startswith(("A.", "J.")) for e in tr.events for n, _v in e.values)


def test_e02_a02_no_fictitious_conversion_current_or_iteration():
    traces = [nwt.explain_nonlinear_dc(DIODE), ana.explain_linear_dc(DIVIDER), ana.explain_ac(RC, "1 kHz"),
              ana.explain_dc_sweep(DIODE, "V1", "0", "1", "0.5")]
    for t in traces:
        assert not any(e.title.startswith("Conversión") for e in t.events)
    fed = ana.explain_linear_dc("* i\nI1 0 a 1mA\nR1 a 0 1kohm\n.end\n")
    labels = [x.text for _n, x in events(fed, "Incógnitas")[0].values]
    assert labels == ["V(a)"]  # a current source adds no auxiliary unknown, and none is shown
    sweep = ana.explain_dc_sweep(DIODE, "V1", "0", "1", "0.5")
    assert all(values(e)["iterations"].number <= 50 for e in events(sweep, "Punto "))


def test_e02_a03_no_fictitious_backtracking():
    rec = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(DIODE), observer=rec)
    halvings = [c[1][2] for c in rec.calls if c[0] == "newton_iteration"]
    t = nwt.explain_nonlinear_dc(DIODE)
    assert len(events(t, "Backtracking")) == sum(h + 1 for h in halvings if h > 0)
    quiet = nwt.explain_nonlinear_dc(CURRENT_FED)
    rec2 = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(CURRENT_FED), observer=rec2)
    h2 = [c[1][2] for c in rec2.calls if c[0] == "newton_iteration"]
    assert len(events(quiet, "Backtracking")) == sum(h + 1 for h in h2 if h > 0)


def test_e02_a04_no_fictitious_kcl_decomposition_or_device():
    t = nwt.explain_nonlinear_dc(DIODE)
    assert not any(n.startswith("term.") for e in events(t, "KCL") for n in values(e))
    bjt = ("* q\nV1 c 0 5V\nV2 b 0 0.7V\nQ1 c b 0 Q\n"
           ".param Q1 Is=1e-15A BF=100 BR=1 Vt=0.02585V\n.end\n")
    tq = nwt.explain_nonlinear_dc(bjt)
    assert events(tq, "Detalle de dispositivo no expuesto")  # BJT internals declared, never invented
    assert not events(tq, "Modelo de Shockley")
    assert tq.outcome is Outcome.FAILED and errors(tq) == ["INVALID"]  # the engine's own verdict, reported


# =============================================================== hardening / determinism / security

def test_e02_z01_newton_observer_equivalence_with_new_data():
    for spec in (DIODE, TWO, DIVERGES, SINGULAR):
        circuit = nwt.parse_circuit_spec(spec)
        rec = Recorder()
        a, b = solve_nonlinear_dc(circuit), solve_nonlinear_dc(circuit, observer=rec)
        assert a.status is b.status and a.to_dict() == b.to_dict() and a.diagnostics == b.diagnostics
    failing = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(DIVERGES), observer=failing)
    assert failing.calls[-1][0] == "newton_failed" and "backtracking" in failing.calls[-1][1][1]


_CHILD = """
import sys
sys.path.insert(0, {src!r})
from academic_core.domain.execution import analog as ana, newton as nwt
ts = [nwt.explain_nonlinear_dc({two!r}), ana.explain_linear_dc({div!r}), ana.explain_ac({rc!r}, "1 kHz"),
      ana.explain_dc_sweep({diode!r}, "V1", "0", "1", "0.5"), ana.explain_tf_point("2", "1, 3, 2, 0", "1"),
      ana.explain_transient({rcic!r}, "BE", "0.001", "0.0001", "0.000000001", "0.0001")]
print(" ".join(t.digest() for t in ts))
"""


def test_e02_z02_identical_across_processes_and_hash_seeds():
    code = _CHILD.format(src=str(ROOT / "src"), two=TWO, div=DIVIDER, rc=RC, diode=DIODE, rcic=RC_IC)
    outs = set()
    for seed in ("0", "11", "2024", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=300, check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1 and len(next(iter(outs)).split()) == 6


def test_e02_z03_security_and_layering():
    banned_calls = {"eval", "exec", "compile", "__import__", "open", "globals", "locals"}
    banned_mods = {"pickle", "marshal", "importlib", "subprocess", "os", "sys", "shutil", "socket"}
    for f in (SRC / "domain" / "execution" / "analog.py", SRC / "domain" / "execution" / "newton.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (f.name, node.func.id)
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_mods
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned_mods
                assert not node.module.startswith(("academic_core.ui", "academic_core.application", "PySide6"))
    for f in (SRC / "domain" / "engineering" / "mna" / "nonlinear.py", SRC / "domain" / "engineering" / "mna" / "solver.py"):
        text = f.read_text(encoding="utf-8")
        assert "float(" not in text and "academic_core.domain.execution" not in text


def test_e02_z04_inputs_are_bounded():
    with pytest.raises(ValidationError):
        ana.explain_linear_dc("R1 a 0 1ohm\n" * 1000)
    with pytest.raises(ValidationError):
        ana.explain_linear_dc(DIVIDER, max_lines=1)
    with pytest.raises(ValidationError):
        ana.explain_dc_sweep(DIODE, "V1", 0, "1", "0.5")
    assert ana.explain_dc_sweep(DIODE, "V1", "a", "1", "0.5").outcome is Outcome.FAILED


def test_e02_z05_renderer_lessons_for_analog():
    view = build_view(ana.explain_linear_dc(DIVIDER))
    kinds = {lesson.kind for lesson in view.lessons}
    assert {"Fórmula", "Cálculo", "Resultado", "Verificación"} <= kinds
