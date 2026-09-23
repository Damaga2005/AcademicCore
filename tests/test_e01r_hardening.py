"""E0.1-R+ hardening: the optional observers of certified engines change nothing.

For GUM, F8-N and F8-P: ``observer=None`` and a recording observer must
give identical results, errors, iterations, order, tolerances,
convergence and determinism. What an observer receives are immutable
snapshots (tuples, Decimal, str, bool, int). A diagnostic performance
record is printed; no wall-clock value is asserted.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from academic_core.domain.engineering import gum as G
from academic_core.domain.engineering.control.margins import margins
from academic_core.domain.engineering.control.tf import make_tf
from academic_core.domain.engineering.mna.nonlinear import NonlinearStatus, solve_nonlinear_dc
from academic_core.domain.execution import control as ctl
from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution import uncertainty as unc

D = Decimal
DIODE = """* diode_demo
V1 in 0 5V
R1 in a 1kohm
D1 a 0 D
.param D1 Is=1e-14A n=1 Vt=0.02585V
.end
"""
TWO_DIODES = """* two_diodes
V1 in 0 3V
R1 in a 220ohm
D1 a b D
D2 b 0 D
.param D1 Is=1e-14A n=1 Vt=0.02585V
.param D2 Is=2e-14A n=1.5 Vt=0.02585V
.end
"""
IMMUTABLE = (tuple, Decimal, str, bool, int, type(None))


class Recorder:
    """Records every call; fails if a value it receives is mutable."""

    def __init__(self):
        self.calls = []

    def _keep(self, name, args, kwargs):
        for value in list(args) + list(kwargs.values()):
            _assert_immutable(value)
        self.calls.append((name, args, tuple(sorted(kwargs.items()))))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self._keep(name, args, kwargs)


def _assert_immutable(value):
    assert isinstance(value, IMMUTABLE), type(value)
    if isinstance(value, tuple):
        for item in value:
            _assert_immutable(item)


# =============================================================== GUM

GUM_MODELS = [
    ("sum", "S = A + B", {"A": ("1", "0.1", "inf"), "B": ("2", "0.2", "inf")}, None),
    ("product", "P = A * B", {"A": ("3", "0.1", "5"), "B": ("2", "0.2", "8")}, None),
    ("quotient", "R = V / I", {"V": ("5", "0.01", "inf"), "I": ("0.002", "0.00001", "9")}, None),
    ("numerical", "Y = A^2 / B", {"A": ("10", "0.05", "4"), "B": ("50", "0.1", "12")}, None),
    ("correlated", "S = A + B", {"A": ("1", "0.1", "inf"), "B": ("2", "0.2", "inf")}, [("A", "B", "0.5")]),
    ("zero_sensitivity", "Y = A + 0*B", {"A": ("1", "0.1", "inf"), "B": ("2", "0.2", "inf")}, None),
    ("zero_uncertainty", "Y = A + B", {"A": ("1", "0", "inf"), "B": ("2", "0.2", "3")}, None),
    ("all_zero", "Y = A + B", {"A": ("1", "0", "inf"), "B": ("2", "0", "inf")}, None),
]


def _gum_inputs(spec):
    return {n: G.InputQuantity(n, D(v), "", D(u), degrees_of_freedom=float(dof)) for n, (v, u, dof) in spec.items()}


def _gum_fingerprint(r: G.GUMResult):
    b = r.budget
    return (r.measurand_value, r.combined_standard_uncertainty, r.effective_degrees_of_freedom, r.coverage_factor,
            r.expanded_uncertainty, b.combined_variance, b.covariance_term, b.to_dict(),
            r.provenance["coverage_factor_source"])


@pytest.mark.parametrize("name,equation,spec,corr", GUM_MODELS, ids=[m[0] for m in GUM_MODELS])
def test_r_h01_gum_observer_equivalence(name, equation, spec, corr):
    model = G.MeasurementModel(equation.split("=")[0].strip(), equation)
    matrix = G.CorrelationMatrix.from_pairs(corr) if corr else None
    rec = Recorder()
    plain = G.evaluate_gum(model, _gum_inputs(spec), correlation=matrix)
    observed = G.evaluate_gum(model, _gum_inputs(spec), correlation=matrix, observer=rec)
    assert _gum_fingerprint(plain) == _gum_fingerprint(observed)
    assert [c[0] for c in rec.calls] == ["sensitivity"] * len(spec)
    assert [c[1][0] for c in rec.calls] == sorted(spec)  # the engine's own order
    for _name, args, _kw in rec.calls:
        assert args[1] in ("ANALYTIC", "NUMERICAL", "EXPLICIT")


def test_r_h02_gum_errors_identical():
    model = G.MeasurementModel("Y", "Y = A + B")
    bad = None
    inputs = _gum_inputs({"A": ("1", "0.1", "inf"), "B": ("2", "0.2", "inf")})
    for kwargs in ({"explicit_k": -1}, {"explicit_k": "nan"}):
        with pytest.raises(ValueError) as a:
            G.evaluate_gum(model, inputs, correlation=bad, **kwargs)
        with pytest.raises(ValueError) as b:
            G.evaluate_gum(model, inputs, correlation=bad, observer=Recorder(), **kwargs)
        assert str(a.value) == str(b.value)
    with pytest.raises(ValueError) as a:
        G.evaluate_gum(model, {})
    with pytest.raises(ValueError) as b:
        G.evaluate_gum(model, {}, observer=Recorder())
    assert str(a.value) == str(b.value)


def test_r_h03_gum_observations_deterministic():
    model = G.MeasurementModel("Y", "Y = A^2 / B")
    spec = {"A": ("10", "0.05", "4"), "B": ("50", "0.1", "12")}
    first, second = Recorder(), Recorder()
    G.evaluate_gum(model, _gum_inputs(spec), observer=first)
    G.evaluate_gum(model, _gum_inputs(spec), observer=second)
    assert first.calls == second.calls


def test_r_h04_gum_sensitivity_hook_only_reports():
    model = G.MeasurementModel("Y", "Y = A^2 / B")
    nominal = {"A": D(10), "B": D(50)}
    for var in ("A", "B"):
        assert model.get_sensitivity(var, dict(nominal)) == model.get_sensitivity(var, dict(nominal), observer=Recorder())


# =============================================================== F8-N

@pytest.mark.parametrize("spec", [DIODE, TWO_DIODES], ids=["diode", "two_diodes"])
def test_r_h05_newton_observer_equivalence(spec):
    circuit = nwt.parse_circuit_spec(spec)
    rec = Recorder()
    plain = solve_nonlinear_dc(circuit)
    observed = solve_nonlinear_dc(circuit, observer=rec)
    assert plain.status is observed.status is NonlinearStatus.CONVERGED
    assert plain.to_dict() == observed.to_dict()
    assert plain.provenance == observed.provenance and plain.diagnostics == observed.diagnostics
    names = [c[0] for c in rec.calls]
    assert names[0] == "newton_start" and names[1:] == ["newton_iteration"] * plain.provenance["iterations"]
    its = [c[1][0] for c in rec.calls[1:]]
    assert its == list(range(1, len(its) + 1))  # iteration order as performed


def test_r_h06_newton_errors_and_limits_identical():
    missing = nwt.parse_circuit_spec(DIODE.replace(".param D1 Is=1e-14A n=1 Vt=0.02585V\n", ""))
    a, b = solve_nonlinear_dc(missing), solve_nonlinear_dc(missing, observer=Recorder())
    assert a.status is b.status is NonlinearStatus.INVALID and a.diagnostics == b.diagnostics
    circuit = nwt.parse_circuit_spec(DIODE)
    rec = Recorder()
    a, b = solve_nonlinear_dc(circuit, max_iter=2), solve_nonlinear_dc(circuit, max_iter=2, observer=rec)
    assert a.status is b.status is NonlinearStatus.MAX_ITERATIONS and a.provenance == b.provenance
    assert [c[0] for c in rec.calls] == ["newton_start", "newton_iteration", "newton_iteration"]


def test_r_h07_newton_snapshot_is_the_real_linear_solve():
    rec = Recorder()
    solve_nonlinear_dc(nwt.parse_circuit_spec(DIODE), observer=rec)
    from decimal import localcontext
    for _name, args, kwargs in rec.calls[1:]:
        kw = dict(kwargs)
        jac, dx, f = kw["jacobian"], kw["dx"], kw["residual_prev"]
        with localcontext() as ctx:
            ctx.prec = 80  # the solver works at 50 digits: check at more than that
            # J·Δx = −F holds for the recorded J, Δx and F: they are the system the solver solved
            for i, row in enumerate(jac):
                lhs = sum((row[j] * dx[j] for j in range(len(dx))), D(0)) + f[i]
                assert abs(lhs) <= D("1e-40") * max(D(1), max(abs(v) for v in row), max(abs(v) for v in dx))
            alpha = args[1]
            x_prev, x_next = kw["x_prev"], args[4]
            for k, v in enumerate(x_next):  # x_(k+1) = x_k + α·Δx (at the solver's 50-digit rounding)
                assert abs(v - (x_prev[k] + alpha * dx[k])) <= D("1e-45") * max(D(1), abs(v))


def test_r_h08_newton_observer_cannot_mutate():
    class Mutator:
        def newton_start(self, nodes, x, *args, **kwargs):
            with pytest.raises((TypeError, AttributeError)):
                x[0] = D(99)  # tuples: the solver's state cannot be touched

        def newton_iteration(self, it, alpha, halvings, step_peak, x, *args, jacobian=(), **kwargs):
            with pytest.raises((TypeError, AttributeError)):
                jacobian[0][0] = D(0)

    circuit = nwt.parse_circuit_spec(DIODE)
    assert solve_nonlinear_dc(circuit).to_dict() == solve_nonlinear_dc(circuit, observer=Mutator()).to_dict()


# =============================================================== F8-P

LOOPS = [((2,), (1, 3, 2, 0)), ((10,), (1, 2, 1, 0)), ((1,), (1, 1)), ((1, 2), (1, 1, 0)), ((5,), (1, 6, 11, 6))]


@pytest.mark.parametrize("num,den", LOOPS)
def test_r_h09_margins_observer_equivalence(num, den):
    loop = make_tf(tuple(D(v) for v in num), tuple(D(v) for v in den))
    rec = Recorder()
    assert margins(loop) == margins(loop, observer=rec)
    brackets = [c for c in rec.calls if c[0] == "bracket"]
    refined = [c for c in rec.calls if c[0] == "refined"]
    assert len(brackets) == len(refined)  # every bracket ends with a stated stop reason
    for name, args, kwargs in rec.calls:
        if name == "bisection":
            kw = dict(kwargs)
            lo, hi, mid = args[2], args[3], args[4]
            assert lo <= mid <= hi and kw["new_lo"] <= kw["new_hi"]
            assert (kw["new_lo"], kw["new_hi"]) in ((mid, hi), (lo, mid), (mid, mid))


def test_r_h10_margins_errors_identical():
    from academic_core.domain.engineering.control.errors import ControlError
    with pytest.raises(ControlError) as a:
        margins("not a loop")
    with pytest.raises(ControlError) as b:
        margins("not a loop", observer=Recorder())
    assert str(a.value) == str(b.value)


# =============================================================== determinism of the traces

def test_r_h11_traces_repeat_exactly():
    for make in (lambda: nwt.explain_nonlinear_dc(TWO_DIODES), lambda: ctl.explain_margins("5", "1, 6, 11, 6"),
                 lambda: unc.explain_gum("Y", "Y = A^2 / B", {"A": "value=10; u=0.05; dof=4",
                                                               "B": "value=50; u=0.1; dof=12"})):
        assert make().to_json() == make().to_json()


# =============================================================== performance (diagnostic only)

def test_r_h12_performance_record(capsys):
    circuit = nwt.parse_circuit_spec(TWO_DIODES)
    loop = make_tf((D(5),), (D(1), D(6), D(11), D(6)))
    rows = []
    for label, plain, observed in (
            ("F8-N", lambda: solve_nonlinear_dc(circuit), lambda: solve_nonlinear_dc(circuit, observer=Recorder())),
            ("F8-P", lambda: margins(loop), lambda: margins(loop, observer=Recorder()))):
        t0 = time.perf_counter()
        plain()
        t1 = time.perf_counter()
        observed()
        t2 = time.perf_counter()
        rows.append(f"{label}: observer=None {t1 - t0:.4f}s, recording {t2 - t1:.4f}s")
    print("E0.1-R+ PERF", "; ".join(rows))
    assert len(rows) == 2  # diagnostic: timings are printed, never asserted


# =============================================================== determinism across processes / hash seeds

_CHILD = """
import sys
sys.path.insert(0, {src!r})
from academic_core.domain.execution import digital as dig, newton as nwt, control as ctl, uncertainty as unc
from academic_core.domain.execution import symbolic as sym, equation as eqn
from academic_core.application.digital_service import DigitalAnalysisService, AnalyzerRequest
svc = DigitalAnalysisService()
req = AnalyzerRequest("xor3_glitch", ("a", "b", "c", "y"), "0", "4")
ts = [dig.explain_capture(svc.new_circuit("xor3_glitch"), svc.build_config(req), pedagogical=True, delta=True),
      nwt.explain_nonlinear_dc({spec!r}), ctl.explain_margins("5", "1, 6, 11, 6"),
      unc.explain_gum("Y", "Y = A^2 / B", {{"A": "value=10; u=0.05; dof=4", "B": "value=50; u=0.1; dof=12"}},
                      sensitivities={{"B": "-0.04"}}),
      sym.explain_integral("1/sqrt(x)"), sym.explain_simplify("x/x"),
      eqn.explain_equation({{"R1": "1 kohm", "R2": "500 ohm"}}, "R = R1 + R2", pedagogical=True)]
print(" ".join(t.digest() for t in ts))
"""


def test_r_h13_identical_across_processes_and_hash_seeds():
    import os
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    code = _CHILD.format(src=str(root / "src"), spec=TWO_DIODES)
    outs = set()
    for seed in ("0", "3", "31337", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=300, check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1 and len(next(iter(outs)).split()) == 7
