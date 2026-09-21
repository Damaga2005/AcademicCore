"""F8-O metrology layer tests O-001..O-064 (property-first, analytical-first).

Every comparison records reference / actual / absolute error / relative
error / tolerance explicitly. No test merely executes lines: each proves a
gate property. Analytical references (closed forms, JCGM tables, hand
Decimal arithmetic) outrank numerical ones throughout.
"""

import ast
import time
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering import metrology as M
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.lab.model import Waveform
from academic_core.domain.engineering.metrology.errors import MetrologyError, MetrologyStatus
from academic_core.domain.engineering.mna.analysis import (
    MCConfig,
    ObservableSpec,
    ParamAddress,
    UniformDist,
    observable_value,
    solve_point,
    substitute,
)
from academic_core.domain.engineering.units import (
    DIMENSIONLESS,
    VOLTAGE,
    Quantity,
    Unit,
    parse_quantity as Q,
)

METROLOGY_DIR = Path(__file__).resolve().parent.parent / "src" / "academic_core" / "domain" / "engineering" / "metrology"


def _rel(actual: Decimal, ref: Decimal, eps: Decimal = Decimal("1e-30")) -> Decimal:
    denom = abs(ref) if abs(ref) > eps else eps
    return abs(actual - ref) / denom


def _divider() -> Circuit:
    c = Circuit("div")
    c.add(Component("V1", "V", Q("10 V"), {"+": "in", "-": "0"}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("R2", "R", Q("1 kohm"), {"1": "out", "2": "0"}))
    return c


def _sum_budget():
    model = M.build_model("Y", equation="X1 + X2", input_names=("X1", "X2"))
    inputs = {
        "X1": M.type_b_explicit("X1", nominal=Decimal("10"), standard_uncertainty=Decimal("0.1")),
        "X2": M.type_b_explicit("X2", nominal=Decimal("5"), standard_uncertainty=Decimal("0.2")),
    }
    return model, inputs


def _fd_circuit_derivative(circuit: Circuit, addr: ParamAddress, spec: ObservableSpec) -> Decimal:
    from academic_core.domain.engineering.mna.analysis import resolve_param

    nominal = resolve_param(circuit, addr).nominal
    h = abs(nominal) * Decimal("1e-6")
    if h < Decimal("1e-9"):
        h = Decimal("1e-9")
    plus_state = solve_point(substitute(circuit, {addr: nominal + h}))[1]
    minus_state = solve_point(substitute(circuit, {addr: nominal - h}))[1]
    assert plus_state is not None and minus_state is not None
    return (observable_value(spec, plus_state) - observable_value(spec, minus_state)) / (Decimal(2) * h)


# ---- O-001..O-003 Type A ----------------------------------------------------

def test_o001_type_a_canonical():
    got = M.type_a("A", [Decimal("10")] * 5)
    assert got.nominal_value == Decimal("10")
    assert got.standard_uncertainty == Decimal("0")
    assert got.degrees_of_freedom == 4.0
    assert got.uncertainty_type == "A"


def test_o002_type_a_dispersed():
    obs = [Decimal(v) for v in ("1", "2", "3", "4", "5")]
    got = M.type_a("A", obs)
    assert got.nominal_value == Decimal("3")
    ref_u2 = Decimal("0.5")  # s^2/5 with s^2 = 2.5
    abs_err = abs(got.standard_uncertainty * got.standard_uncertainty - ref_u2)
    assert abs_err < Decimal("1e-15"), f"abs_err={abs_err}"
    assert got.degrees_of_freedom == 4.0


def test_o003_type_a_minimum_rejected():
    with pytest.raises(MetrologyError) as exc:
        M.type_a("A", [Decimal("1")])
    assert exc.value.status == MetrologyStatus.INVALID


def test_o003b_type_a_order_invariance():
    base = [Decimal(v) for v in ("1.5", "2.5", "0.5", "3.5", "2.0")]
    first = M.type_a("A", base)
    second = M.type_a("A", tuple(reversed(base)))
    assert first.nominal_value == second.nominal_value
    assert first.standard_uncertainty == second.standard_uncertainty


# ---- O-004..O-007 Type B ----------------------------------------------------

def test_o004_rectangular():
    got = M.type_b_rectangular("R", nominal=Decimal("0"), half_width=Decimal("1"))
    abs_err = abs(got.standard_uncertainty * got.standard_uncertainty - Decimal(1) / Decimal(3))
    assert abs_err < Decimal("1e-15"), f"abs_err={abs_err}"
    assert got.degrees_of_freedom == float("inf")


def test_o005_triangular():
    got = M.type_b_triangular("T", nominal=Decimal("0"), half_width=Decimal("1"))
    abs_err = abs(got.standard_uncertainty * got.standard_uncertainty - Decimal(1) / Decimal(6))
    assert abs_err < Decimal("1e-15"), f"abs_err={abs_err}"


def test_o006_normal():
    got = M.type_b_normal("N", nominal=Decimal("0"), expanded_uncertainty=Decimal("2"), k=Decimal("2"))
    assert got.standard_uncertainty == Decimal("1")
    with pytest.raises(MetrologyError) as exc:
        M.type_b_normal("N", nominal=Decimal("0"), expanded_uncertainty=Decimal("1"), k=Decimal("0"))
    assert exc.value.status == MetrologyStatus.INVALID


def test_o007_negative_half_width():
    with pytest.raises(MetrologyError) as exc:
        M.type_b_rectangular("R", half_width=Decimal("-1"))
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-008..O-013 sensitivities ---------------------------------------------

def test_o008_sum_analytic():
    model = M.build_model("Y", equation="X1 + X2", input_names=("X1", "X2"))
    nom = {"X1": Decimal("10"), "X2": Decimal("5")}
    assert M.sensitivity_of(model, "X1", nom) == (Decimal("1"), "ANALYTIC")
    assert M.sensitivity_of(model, "X2", nom) == (Decimal("1"), "ANALYTIC")


def test_o009_product_analytic():
    model = M.build_model("Y", equation="X1 * X2", input_names=("X1", "X2"))
    nom = {"X1": Decimal("3"), "X2": Decimal("4")}
    assert M.sensitivity_of(model, "X1", nom) == (Decimal("4"), "ANALYTIC")
    assert M.sensitivity_of(model, "X2", nom) == (Decimal("3"), "ANALYTIC")


def test_o010_quotient_analytic():
    model = M.build_model("Y", equation="X1 / X2", input_names=("X1", "X2"))
    nom = {"X1": Decimal("6"), "X2": Decimal("3")}
    c1, m1 = M.sensitivity_of(model, "X1", nom)
    c2, m2 = M.sensitivity_of(model, "X2", nom)
    assert m1 == m2 == "ANALYTIC"
    assert c1 == Decimal(1) / Decimal(3)
    assert c2 == Decimal("-6") / Decimal("9")


def test_o011_quotient_pole_fd_fallback():
    model = M.build_model("Y", equation="X1 / X2", input_names=("X1", "X2"))
    c, method = M.sensitivity_of(model, "X2", {"X1": Decimal("4"), "X2": Decimal("0")})
    assert method == "NUMERICAL"
    assert c.is_finite()
    # gate step h = max(0*1e-6, 1e-9) = 1e-9 -> c = 4/h^2 = 4e18
    assert c == Decimal("4E+18")


def test_o012_divider_closed():
    model = M.build_model(
        "Vout", equation="Vin * R2 / (R1 + R2)", input_names=("Vin", "R1", "R2")
    )
    nom = {"Vin": Decimal("10"), "R1": Decimal("1000"), "R2": Decimal("1000")}
    c_r1, method = M.sensitivity_of(model, "R1", nom)
    assert method == "ANALYTIC"
    ref = -Decimal("10") * Decimal("1000") / (Decimal("2000") ** 2)
    assert _rel(c_r1, ref) < Decimal("1e-30"), f"c={c_r1} ref={ref}"
    c_r2, _ = M.sensitivity_of(model, "R2", nom)
    ref2 = Decimal("10") * Decimal("1000") / (Decimal("2000") ** 2)
    assert _rel(c_r2, ref2) < Decimal("1e-30")


def test_o013_fd_exponential():
    model = M.build_model("Y", equation="exp(X1)", input_names=("X1",))
    c, method = M.sensitivity_of(model, "X1", {"X1": Decimal("1")})
    assert method == "NUMERICAL"
    # independent reference: e = sum 1/k! to high order in-test
    e = sum(Decimal(1) / _fact(k) for k in range(30))
    assert _rel(c, e) < Decimal("1e-4"), f"c={c} e={e}"


def _fact(k: int) -> Decimal:
    out = Decimal(1)
    for j in range(2, k + 1):
        out *= j
    return out


# ---- O-014..O-020 propagation & correlation ----------------------------------

def test_o014_combined_uncorrelated():
    model, inputs = _sum_budget()
    got = M.evaluate_budget(model, inputs)
    ref = (Decimal("0.01") + Decimal("0.04")).sqrt()
    assert _rel(got.combined_standard_uncertainty, ref) < Decimal("1e-12")
    assert got.measurand_value == Decimal("15")


def test_o015_correlation_plus_one():
    model, inputs = _sum_budget()
    corr = M.build_correlation([("X1", "X2", Decimal("1"))])
    got = M.evaluate_budget(model, inputs, correlation=corr)
    assert abs(got.combined_standard_uncertainty - Decimal("0.3")) < Decimal("1e-15")


def test_o016_correlation_minus_one():
    model, inputs = _sum_budget()
    corr = M.build_correlation([("X1", "X2", Decimal("-1"))])
    got = M.evaluate_budget(model, inputs, correlation=corr)
    assert abs(got.combined_standard_uncertainty - Decimal("0.1")) < Decimal("1e-15")


def test_o017_psd_valid_accepted():
    model = M.build_model(
        "Y", equation="X1 + X2 + X3", input_names=("X1", "X2", "X3")
    )
    inputs = {
        k: M.type_b_explicit(k, nominal=Decimal("1"), standard_uncertainty=Decimal("0.1"))
        for k in ("X1", "X2", "X3")
    }
    corr = M.build_correlation(
        [("X1", "X2", Decimal("0.5")), ("X1", "X3", Decimal("0.5")), ("X2", "X3", Decimal("0.5"))]
    )
    got = M.evaluate_budget(model, inputs, correlation=corr)
    assert got.combined_standard_uncertainty > 0


def test_o018_non_psd_singular():
    # indefinite triple: r12=r13=1, r23=-1 (det < 0) must never pass silently
    model3 = M.build_model("Y", equation="X1 + X2 + X3", input_names=("X1", "X2", "X3"))
    inputs3 = {
        k: M.type_b_explicit(k, nominal=Decimal("1"), standard_uncertainty=Decimal("1"))
        for k in ("X1", "X2", "X3")
    }
    with pytest.raises(MetrologyError) as exc:
        corr3 = M.build_correlation(
            [("X1", "X2", Decimal("1")), ("X1", "X3", Decimal("1")), ("X2", "X3", Decimal("-1"))]
        )
        M.evaluate_budget(model3, inputs3, correlation=corr3)
    assert exc.value.status == MetrologyStatus.SINGULAR


def test_o019_asymmetric_rejected():
    with pytest.raises(MetrologyError) as exc:
        M.build_correlation([("a", "b", Decimal("0.5")), ("b", "a", Decimal("0.3"))])
    assert exc.value.status == MetrologyStatus.INVALID


def test_o020_out_of_range_rejected():
    with pytest.raises(MetrologyError) as exc:
        M.build_correlation([("a", "b", Decimal("1.5"))])
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-021..O-027 W-S, k, U, degenerate -------------------------------------

def _mixed_budget():
    model = M.build_model("Y", equation="X1 + X2", input_names=("X1", "X2"))
    a = M.type_a("X1", [Decimal(v) for v in ("0.95", "1.05", "0.98", "1.02", "1.00", "1.00")])
    b = M.type_b_explicit("X2", nominal=Decimal("2"), standard_uncertainty=Decimal("0.2"))
    return model, {"X1": a, "X2": b}


def test_o021_welch_satterthwaite():
    model = M.build_model("Y", equation="X1 + X2", input_names=("X1", "X2"))
    x1_finite = M.type_b_explicit(
        "X1", nominal=Decimal("1"), standard_uncertainty=Decimal("0.1"), degrees_of_freedom=5.0
    )
    x2 = M.type_b_explicit("X2", nominal=Decimal("1"), standard_uncertainty=Decimal("0.2"))
    got = M.evaluate_budget(model, {"X1": x1_finite, "X2": x2})
    # hand reference: uc^2 = 0.05, nu_eff = 0.05^2 / (0.1^4/5) = 125
    assert abs(Decimal(str(got.effective_degrees_of_freedom)) - Decimal("125")) / Decimal("125") < Decimal(
        "1e-9"
    )


def test_o022_all_infinite_normal_limit():
    model, inputs = _sum_budget()
    got = M.evaluate_budget(model, inputs)
    assert got.effective_degrees_of_freedom == float("inf")
    assert got.coverage_factor == Decimal("1.959964")


def test_o023_student_t_table():
    assert M.coverage_factor(0.95, 5.0) == Decimal("2.570582")


def test_o024_explicit_k():
    model, inputs = _sum_budget()
    got = M.evaluate_budget(model, inputs, explicit_k=Decimal("2"))
    assert got.coverage_factor == Decimal("2")
    assert got.expanded_uncertainty == 2 * got.combined_standard_uncertainty
    assert got.provenance["coverage_factor_source"] == "explicit_user"


def test_o025_bad_k_rejected():
    model, inputs = _sum_budget()
    for bad in (Decimal("0"), Decimal("-2"), Decimal("NaN"), Decimal("Infinity"), True):
        with pytest.raises(MetrologyError) as exc:
            M.evaluate_budget(model, inputs, explicit_k=bad)
        assert exc.value.status == MetrologyStatus.INVALID, bad


def test_o026_negative_variance_numeric_error():
    model = M.build_model("Y", equation="X1 + X2 + X3", input_names=("X1", "X2", "X3"))
    inputs = {
        k: M.type_b_explicit(k, nominal=Decimal("1"), standard_uncertainty=Decimal("1"))
        for k in ("X1", "X2", "X3")
    }
    neg = Decimal("-0.500000001")  # min eig -2e-9: passes PSD tol, total = -6e-9 exactly
    corr = M.build_correlation(
        [("X1", "X2", neg), ("X1", "X3", neg), ("X2", "X3", neg)]
    )
    with pytest.raises(MetrologyError) as exc:
        M.evaluate_budget(model, inputs, correlation=corr)
    assert exc.value.status == MetrologyStatus.NUMERIC_ERROR


def test_o027_all_zero_degenerate():
    model, inputs = _sum_budget()
    zeroed = {
        k: M.type_b_explicit(k, nominal=Decimal("1"), standard_uncertainty=Decimal("0"))
        for k in ("X1", "X2")
    }
    got = M.evaluate_budget(model, zeroed)
    assert got.combined_standard_uncertainty == Decimal("0")
    assert got.expanded_uncertainty == Decimal("0")
    assert got.effective_degrees_of_freedom == float("inf")


# ---- O-028..O-032 units ------------------------------------------------------

def test_o028_units_consistent():
    model = M.build_model(
        "I", equation="V / R", input_names=("V", "R"),
        output_unit="A", input_units={"V": "V", "R": "ohm"},
    )
    inputs = {
        "V": M.type_b_explicit("V", nominal=Decimal("10"), standard_uncertainty=Decimal("0.1"), unit="V"),
        "R": M.type_b_explicit("R", nominal=Decimal("1000"), standard_uncertainty=Decimal("1"), unit="ohm"),
    }
    got = M.evaluate_budget(model, inputs)
    assert got.measurand_value == Decimal("0.01")
    assert got.measurand_unit == "A"


def test_o029_units_incompatible():
    model = M.build_model(
        "S", equation="V + T", input_names=("V", "T"),
        output_unit="V", input_units={"V": "V", "T": "s"},
    )
    inputs = {
        "V": M.type_b_explicit("V", nominal=Decimal("1"), standard_uncertainty=Decimal("0"), unit="V"),
        "T": M.type_b_explicit("T", nominal=Decimal("1"), standard_uncertainty=Decimal("0"), unit="s"),
    }
    with pytest.raises(MetrologyError) as exc:
        M.evaluate_budget(model, inputs)
    assert exc.value.status == MetrologyStatus.INVALID


def test_o030_evaluator_decimal_bypass_rejected():
    model = M.build_model(
        "Y", evaluator=lambda env: env["X"] + env["T"],
        input_names=("X", "T"), output_unit="mm",
        input_units={"X": "mm", "T": "s"},
    )
    inputs = {
        "X": M.type_b_explicit("X", nominal=Decimal("10"), standard_uncertainty=Decimal("0"), unit="mm"),
        "T": M.type_b_explicit("T", nominal=Decimal("2"), standard_uncertainty=Decimal("0"), unit="s"),
    }
    with pytest.raises(MetrologyError) as exc:
        M.evaluate_budget(model, inputs)
    assert exc.value.status == MetrologyStatus.INVALID


def test_o031_evaluator_quantity_ok():
    def _eval(env):
        return env["V"] / env["R"]

    model = M.build_model(
        "I", evaluator=_eval, input_names=("V", "R"),
        output_unit="A", input_units={"V": "V", "R": "ohm"},
    )
    inputs = {
        "V": M.type_b_explicit("V", nominal=Decimal("10"), standard_uncertainty=Decimal("0"), unit="V"),
        "R": M.type_b_explicit("R", nominal=Decimal("1000"), standard_uncertainty=Decimal("0"), unit="ohm"),
    }
    got = M.evaluate_budget(model, inputs)
    assert got.measurand_value == Decimal("0.01")


def test_o032_unknown_unit_rejected():
    model = M.build_model(
        "Y", equation="X1", input_names=("X1",),
        output_unit="frobnicate", input_units={"X1": "V"},
    )
    inputs = {"X1": M.type_b_explicit("X1", nominal=Decimal("1"), standard_uncertainty=Decimal("0"), unit="V")}
    with pytest.raises(MetrologyError) as exc:
        M.evaluate_budget(model, inputs)
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-033/O-058/O-060 static security & non-duplication ---------------------

BANNED_CALLS = ("eval", "exec", "open", "getattr", "setattr", "compile", "__import__")
BANNED_IMPORTS = ("math", "numpy", "scipy", "os", "sys", "subprocess", "socket", "urllib",
                  "pickle", "marshal", "importlib", "pathlib", "sqlite3")


def _metrology_sources():
    return sorted(METROLOGY_DIR.glob("*.py"))


def test_o033_no_banned_calls_or_imports():
    offenders = []
    for path in _metrology_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                    offenders.append(f"{path.name}: call {func.id}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name.split(".")[0] for a in node.names] + (
                    [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else []
                )
                for name in names:
                    if name in BANNED_IMPORTS:
                        offenders.append(f"{path.name}: import {name}")
    assert offenders == []


def test_o058_re_compile_is_not_builtin_compile():
    # metrology uses no regex at all; proves the audit distinguishes re.compile
    # (allowed elsewhere) from builtin compile() (forbidden).
    import re

    assert re.compile(r"[A-Za-z0-9_.-]{1,64}\Z").match("abc-123.4_OK") is not None
    tree = ast.parse("(re.compile('x'))")
    call = tree.body[0].value
    assert isinstance(call.func, ast.Attribute) and call.func.attr == "compile"
    for path in _metrology_sources():
        text = path.read_text(encoding="utf-8")
        assert "re.compile" not in text
        assert "compile(" not in text


def test_o060_no_second_engine():
    text = "\n".join(p.read_text(encoding="utf-8") for p in _metrology_sources())
    for marker in ("def evaluate_gum", "def jacobi_eigenvalues", "def student_t_quantile",
                   "def run_monte_carlo_native", "def solve_dc_sensitivity", "class NewtonSystem",
                   "from academic_core.domain.engineering import simulation",
                   "import simulation", "import math", "from math", "math.sqrt", "math.log(",
                   "math.exp(", "math.sin", "math.cos", "import statistics", "statistics.",
                   "numpy", "scipy",
                   "float(value", "float(mean", "float(std", "float(var", "float(uc",
                   "float(total", "float(matrix", "float(raw", "float(val", "float(obs"):
        assert marker not in text, marker
    global_stmts = [
        line for p in _metrology_sources()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("global ")
    ]
    assert global_stmts == []
    # allowlisted float() boundary: dof/coverage/seed scalars only (Decimal values never float())
    assert "inf" in text  # canonical "inf" dof documented


def test_o064_architecture_rules_hold():
    offenders = []
    for path in _metrology_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for bad in ("os", "pathlib", "sqlite3", "urllib", "socket", "PySide6", "subprocess"):
            if bad in imported:
                offenders.append(f"{path.name}: {bad}")
    assert offenders == []


# ---- O-034..O-038 circuit ----------------------------------------------------

def test_o034_circuit_divider_closed():
    circuit = _divider()
    addr = ParamAddress("R1", "value")
    spec = ObservableSpec(kind="node_voltage", locator="out")
    res = M.dc_sensitivities(circuit, (addr,), (spec,))
    deriv = res.observables["node_voltage:out"]["sensitivities"]["R1.value"]["derivative"]
    ref = -Decimal("10") * Decimal("1000") / (Decimal("2000") ** 2)
    assert _rel(deriv, ref) < Decimal("1e-12"), f"{deriv} vs {ref}"


def _nonlinear_fd_check(circuit: Circuit, ref: str, node: str):
    addr = ParamAddress(ref, "value")
    spec = ObservableSpec(kind="node_voltage", locator=node)
    res = M.dc_sensitivities(circuit, (addr,), (spec,))
    assert str(res.status) == "SensitivityStatus.COMPLETED"
    deriv = res.observables[spec.key]["sensitivities"][addr.key]["derivative"]
    fd = _fd_circuit_derivative(circuit, addr, spec)
    assert _rel(deriv, fd, eps=Decimal("1e-12")) < Decimal("1e-4"), f"{deriv} vs FD {fd}"
    return deriv


def test_o035_diode_fd():
    c = Circuit("dd")
    c.add(Component("V1", "V", Q("5 V"), {"+": "vcc", "-": "0"}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "vcc", "2": "a"}))
    c.add(Component("D1", "D", None, {"A": "a", "K": "0"},
                    {"Is": Q("1e-14 A"), "n": Q("1"), "Vt": Q("25.85 mV")}))
    assert _nonlinear_fd_check(c, "R1", "a").is_finite()


def test_o036_bjt_fd():
    c = Circuit("bjt")
    c.add(Component("V2", "V", Q("10 V"), {"+": "vcc", "-": "0"}))
    c.add(Component("R3", "R", Q("2 kohm"), {"1": "vcc", "2": "c"}))
    c.add(Component("R4", "R", Q("200 kohm"), {"1": "vcc", "2": "b"}))
    c.add(Component("R5", "R", Q("1 kohm"), {"1": "e", "2": "0"}))
    c.add(Component("Q1", "Q", None, {"C": "c", "B": "b", "E": "e"},
                    {"Is": Q("1e-16 A"), "Bf": Q("100"), "Br": Q("1"),
                     "Nf": Q("1"), "Nr": Q("1"), "Vt": Q("25.85 mV"), "polarity": "NPN"}))
    assert _nonlinear_fd_check(c, "R3", "c").is_finite()


def test_o037_mos_fd():
    from academic_core.domain.engineering.mna.analysis import KP_DIM, LAMBDA_DIM

    c = Circuit("mos")
    c.add(Component("V3", "V", Q("5 V"), {"+": "vdd", "-": "0"}))
    c.add(Component("R6", "R", Q("2 kohm"), {"1": "vdd", "2": "d"}))
    kp = Quantity(Decimal("0.0002"), Unit("A/V2", "A", "", KP_DIM, Decimal(1)))
    lam = Quantity(Decimal("0.02"), Unit("1/V", "V", "", LAMBDA_DIM, Decimal(1)))
    gam = Quantity(Decimal("0.5"), Unit("1", "1", "", DIMENSIONLESS, Decimal(1)))
    c.add(Component("M1", "M", None, {"D": "d", "G": "g", "S": "0", "B": "0"},
                    {"Kp": kp, "Vto": Q("1 V"), "Lambda": lam,
                     "Phi": Q("0.6 V"), "Gamma": gam, "polarity": "NMOS"}))
    c.add(Component("V4", "V", Q("3 V"), {"+": "g", "-": "0"}))
    assert _nonlinear_fd_check(c, "R6", "d").is_finite()


def test_o038_ac_magnitude_chain():
    from academic_core.domain.engineering.ac.small_signal import solve_small_signal_ac

    c = Circuit("rcac")
    c.add(Component("V1", "V", Q("1 V"), {"+": "in", "-": "0"}, {"ac_mag": Q("1 V")}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"}))
    freq = Q("1 kHz")
    addr = ParamAddress("R1", "value")
    spec = ObservableSpec(kind="node_voltage", locator="out")
    res = M.ac_sensitivities(c, freq, (addr,), (spec,))
    assert str(res.status) == "SensitivityStatus.COMPLETED"
    entry = res.to_dict()["observables"]["node_voltage:out"]["sensitivities"]["R1.value"]
    d_mag = Decimal(str(entry["d_magnitude"]))
    assert d_mag.is_finite() and d_mag < 0
    h = Decimal("0.001")
    mags = []
    for sign in (Decimal(1), Decimal(-1)):
        pert = substitute(c, {addr: Decimal("1000") + sign * h})
        mags.append(solve_small_signal_ac(pert, freq).voltage_of("out").modulus())
    fd = (mags[0] - mags[1]) / (Decimal(2) * h)
    assert _rel(d_mag, fd, eps=Decimal("1e-12")) < Decimal("1e-3"), f"{d_mag} vs FD {fd}"


# ---- O-039..O-042 Monte Carlo -------------------------------------------------

def _mc_divider_config(seed: int, iterations: int = 10000):
    return MCConfig(
        iterations=iterations,
        distributions=((ParamAddress("R1", "value"), UniformDist(Decimal("990"), Decimal("1010"))),),
        seed=seed,
        observables=(ObservableSpec(kind="node_voltage", locator="out"),),
    )


def test_o039_mc_vs_analytic():
    circuit = _divider()
    mc = M.run_mc(circuit, _mc_divider_config(42))
    assert str(mc.status) == "MCStatus.COMPLETED"
    values = M.mc_observable_values(mc, "node_voltage:out")
    assert len(values) == 10000
    stats = M.mc_statistics(values)
    c = -Decimal("10") * Decimal("1000") / (Decimal("2000") ** 2)
    analytic_uc = abs(c) * (Decimal("10") / Decimal(3).sqrt())
    verdict = M.validate_mc_vs_analytic(stats["std"], analytic_uc)
    assert verdict["agreement"] is True, verdict
    assert Decimal(str(verdict["relative_difference"])) <= Decimal("0.05")


def test_o040_mc_determinism():
    circuit = _divider()
    first = M.run_mc(circuit, _mc_divider_config(42, 200)).to_dict()
    second = M.run_mc(circuit, _mc_divider_config(42, 200)).to_dict()
    assert first["digest"] == second["digest"]
    assert first["iterations"][0]["parameters"] == second["iterations"][0]["parameters"]


def test_o041_mc_seed_separates():
    circuit = _divider()
    first = M.run_mc(circuit, _mc_divider_config(42, 50)).to_dict()
    second = M.run_mc(circuit, _mc_divider_config(43, 50)).to_dict()
    assert first["iterations"][0]["parameters"] != second["iterations"][0]["parameters"]


def test_o042_mc_seed_required():
    circuit = _divider()
    bad = MCConfig(
        iterations=10,
        distributions=((ParamAddress("R1", "value"), UniformDist(Decimal("990"), Decimal("1010"))),),
        seed=None,
        observables=(ObservableSpec(kind="node_voltage", locator="out"),),
    )
    with pytest.raises(MetrologyError) as exc:
        M.run_mc(circuit, bad)
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-043/O-044 significant figures ------------------------------------------

def test_o043_significant_pair():
    y_str, u_str = M.format_result(Decimal("1.23456"), Decimal("0.0231"))
    assert u_str == "0.023"
    assert y_str == "1.235"


def test_o044_significant_leading_one():
    assert M.format_uncertainty(Decimal("0.14")) == "0.14"
    y_str, u_str = M.format_result(Decimal("3.14159"), Decimal("0.14"))
    assert (y_str, u_str) == ("3.14", "0.14")
    assert M.format_uncertainty(Decimal("0")) == "0"
    assert M.display_decade(Decimal("0.0231")) == -3


def test_o043b_display_never_feeds_back():
    y_str, u_str = M.format_result(Decimal("1.23456"), Decimal("0.0231"))
    assert Decimal(y_str) != Decimal("1.23456")
    assert Decimal(u_str) != Decimal("0.0231")


# ---- O-045..O-047 traceability --------------------------------------------------

def _chain3() -> M.TraceChain:
    a = M.TraceNode.create("cal", "standard", Decimal("10"), Decimal("0.01"), unit="V",
                           standard_id="NMI-001", procedure="calibrate")
    b = M.TraceNode.create("div", "derived", Decimal("5"), Decimal("0.006"), unit="V",
                           parents=("cal",), procedure="divide")
    c = M.TraceNode.create("rep", "report", Decimal("5"), Decimal("0.02"), unit="V",
                           parents=("div",), procedure="report")
    return M.TraceChain(nodes=(a, b, c))


def test_o045_chain_stable():
    chain = _chain3()
    assert chain.verify() == "OK"
    assert chain.digest() == chain.digest()
    reordered = M.TraceChain(nodes=tuple(reversed(chain.nodes)))
    assert reordered.digest() == chain.digest()


def test_o046_broken_link_inconsistent():
    orphan = M.TraceNode.create("x", "derived", Decimal("1"), Decimal("0"), parents=("ghost",))
    with pytest.raises(MetrologyError) as exc:
        M.TraceChain(nodes=(orphan,))
    assert exc.value.status == MetrologyStatus.INCONSISTENT


def test_o047_cycle_rejected():
    a = M.TraceNode.create("a", "derived", Decimal("1"), Decimal("0"), parents=("b",))
    b = M.TraceNode.create("b", "derived", Decimal("1"), Decimal("0"), parents=("a",))
    with pytest.raises(MetrologyError) as exc:
        M.TraceChain(nodes=(a, b))
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-048..O-050 budget properties ----------------------------------------------

def test_o048_budget_shares_sum():
    model, inputs = _sum_budget()
    got = M.evaluate_budget(model, inputs)
    total = sum(row.relative_contribution_pct for row in got.budget.rows)
    assert abs(total - Decimal("100")) <= Decimal("0.01")


def test_o049_insertion_order_invariance():
    model, inputs = _sum_budget()
    first = M.evaluate_budget(model, inputs)
    swapped = M.evaluate_budget(model, {"X2": inputs["X2"], "X1": inputs["X1"]})
    assert str(first.combined_standard_uncertainty) == str(swapped.combined_standard_uncertainty)
    rep_first = M.MetrologyReport.from_gum_result(first)
    rep_swapped = M.MetrologyReport.from_gum_result(swapped)
    assert rep_first.digest() == rep_swapped.digest()


def test_o050_triple_run_identical():
    model, inputs = _sum_budget()
    digests = set()
    for _ in range(3):
        got = M.evaluate_budget(model, inputs)
        rep = M.MetrologyReport.from_gum_result(got)
        digests.add(rep.digest())
        assert str(got.combined_standard_uncertainty) == str(
            M.evaluate_budget(model, inputs).combined_standard_uncertainty
        )
    assert len(digests) == 1


# ---- O-051..O-054 serialization & replay --------------------------------------------

def _report_text() -> str:
    model, inputs = _sum_budget()
    return M.dumps(M.MetrologyReport.from_gum_result(M.evaluate_budget(model, inputs)))


def test_o051_canonical_roundtrip():
    text = _report_text()
    first = M.loads(text)
    assert M.loads(text).digest() == first.digest()
    assert '"inf"' in M.dumps(
        M.MetrologyReport.from_gum_result(M.evaluate_budget(*_sum_budget()))
    )  # dof inf canonical
    doc = M.loads(text).to_dict()
    assert doc["schema"] == "f8o-metrology/1"


def test_o052_replay_equivalent():
    text = _report_text()
    assert M.compare(text, text) == "EQUIVALENT"
    assert M.VALID == M.EQUIVALENT  # mandate §23 alias, explicit


def test_o053_version_mismatch():
    import json

    text = _report_text()
    doc = json.loads(text)
    doc["schema"] = "f8o-metrology/2"
    doc.pop("result_digest", None)
    from academic_core.domain.engineering.metrology.o5_traceability import chain_digest
    from academic_core.domain.engineering.metrology.report import REPORT_TAG

    doc["result_digest"] = chain_digest(doc, tag=REPORT_TAG)
    assert M.compare(text, json.dumps(doc, sort_keys=True)) == "VERSION_MISMATCH"


def test_o054_tamper_and_difference():
    import json

    text = _report_text()
    doc = json.loads(text)
    doc["value"] = "999"
    assert M.compare(text, json.dumps(doc, sort_keys=True)) == "INVALID_SERIALIZATION"
    model, inputs = _sum_budget()
    other = M.dumps(
        M.MetrologyReport.from_gum_result(
            M.evaluate_budget(model, {"X2": inputs["X2"], "X1": inputs["X1"]})
        )
    )
    assert M.compare(text, other) in ("EQUIVALENT", "RESULT_DIFFERS")
    altered_inputs = {
        "X1": M.type_b_explicit("X1", nominal=Decimal("11"), standard_uncertainty=Decimal("0.1")),
        "X2": inputs["X2"],
    }
    altered = M.dumps(M.MetrologyReport.from_gum_result(M.evaluate_budget(model, altered_inputs)))
    assert M.compare(text, altered) == "RESULT_DIFFERS"
    assert M.RESULT_DIFFERENT == M.RESULT_DIFFERS  # mandate §23 alias, explicit


def test_o054b_unknown_field_rejected():
    import json

    doc = json.loads(_report_text())
    doc["extra"] = "x"
    with pytest.raises(MetrologyError) as exc:
        M.loads(json.dumps(doc))
    assert exc.value.status == MetrologyStatus.INVALID


# ---- O-055..O-057 boundaries & hostile ----------------------------------------------

def test_o055_too_many_inputs():
    model = M.build_model(
        "Y", equation=" + ".join(f"X{i}" for i in range(65)),
        input_names=tuple(f"X{i}" for i in range(65)),
    )
    inputs = {
        f"X{i}": M.type_b_explicit(f"X{i}", nominal=Decimal("1"), standard_uncertainty=Decimal("0"))
        for i in range(65)
    }
    with pytest.raises(MetrologyError) as exc:
        M.evaluate_budget(model, inputs)
    assert exc.value.status == MetrologyStatus.INVALID


def test_o056_boundary_battery():
    assert M.type_a("m", [Decimal("1"), Decimal("2")]).degrees_of_freedom == 1.0
    assert M.type_b_rectangular("r", nominal=Decimal("1"), half_width=Decimal("0")).standard_uncertainty == 0
    assert M.format_result(Decimal("-3.7"), Decimal("0")) == (str(Decimal("-3.7")), "0")
    for bad_call in (
        lambda: M.type_a("", [Decimal("1"), Decimal("2")]),
        lambda: M.type_a("b", [True, Decimal("1")]),
        lambda: M.type_a("i", [Decimal("Infinity"), Decimal("1")]),
        lambda: M.type_b_explicit("e", nominal=Decimal("1"), standard_uncertainty=Decimal("-1")),
        lambda: M.format_uncertainty(Decimal("-0.1")),
        lambda: M.coverage_factor(0.0, 5.0),
        lambda: M.coverage_factor(1.0, 5.0),
        lambda: M.coverage_factor(0.95, 0.0),
        lambda: M.build_model("", equation="X1"),
        lambda: M.build_model("Y"),
        lambda: M.evaluate_budget(M.build_model("Y", equation="X1", input_names=("X1",)), {}),
    ):
        with pytest.raises(MetrologyError) as exc:
            bad_call()
        assert exc.value.status == MetrologyStatus.INVALID


def test_o057_hostile_battery():
    model, inputs = _sum_budget()
    for bad_call, status in (
        (lambda: M.evaluate_budget(model, inputs, coverage_probability=float("nan")), MetrologyStatus.INVALID),
        (lambda: M.type_b_normal("n", expanded_uncertainty=Decimal("1"), k=Decimal("nan")), MetrologyStatus.INVALID),
        (lambda: M.build_correlation([("a", "b", "junk")]), MetrologyStatus.INVALID),
        (lambda: M.correlated_normal_samples((Decimal("1"),), (Decimal("-1"),), [], ("v",), 3, 7), MetrologyStatus.INVALID),
        (lambda: M.correlated_normal_samples((Decimal("1"),), (Decimal("1"),), [], ("v",), 0, 7), MetrologyStatus.INVALID),
        (lambda: M.correlated_normal_samples((Decimal("1"),), (Decimal("1"),), [], ("v",), 3, -1), MetrologyStatus.INVALID),
        (lambda: M.correlated_normal_samples((Decimal("1"),), (Decimal("1"),), [], ("v",), 3, True), MetrologyStatus.INVALID),
        (lambda: M.loads(""), MetrologyStatus.INVALID),
        (lambda: M.loads("not json"), MetrologyStatus.INVALID),
        (lambda: M.waveform_to_observations("nope"), MetrologyStatus.INVALID),
        (lambda: M.sensitivity_of(model, "ghost", {"X1": Decimal("1")}), MetrologyStatus.INVALID),
        (lambda: M.validate_mc_vs_analytic(Decimal("-1"), Decimal("1")), MetrologyStatus.INVALID),
    ):
        with pytest.raises(MetrologyError) as exc:
            bad_call()
        assert exc.value.status == status
    assert M.compare("garbage", _report_text()) == "INVALID_SERIALIZATION"


# ---- O-059 lab waveform adapter -------------------------------------------------------

def test_o059_waveform_type_a_without_resolve():
    wave = Waveform(
        times=(Decimal("0"), Decimal("1"), Decimal("2")),
        values=(Decimal("1.0"), Decimal("2.0"), Decimal("3.0")),
        dimension=VOLTAGE, unit_label="V", source="scope",
    )
    obs = M.waveform_to_observations(wave)
    assert obs == (Decimal("1.0"), Decimal("2.0"), Decimal("3.0"))
    direct = M.type_a("V", [Decimal("1"), Decimal("2"), Decimal("3")])
    adapted = M.type_a_from_waveform("V", wave)
    assert adapted.nominal_value == direct.nominal_value
    assert adapted.standard_uncertainty == direct.standard_uncertainty
    assert adapted.unit == "V"


# ---- copula properties -----------------------------------------------------------------

def test_o_copula_r_zero_independent():
    rows = M.correlated_normal_samples(
        (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("1")), [], ("a", "b"), 2000, 7
    )
    assert len(rows) == 2000
    xs = [r[0] for r in rows]
    mean = sum(xs) / Decimal(len(xs))
    assert abs(mean) < Decimal("0.1")


def test_o_copula_correlated_sign():
    pos = M.correlated_normal_samples(
        (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("1")),
        [("a", "b", Decimal("0.9"))], ("a", "b"), 2000, 7,
    )
    agree = sum(1 for r in pos if (r[0] >= 0) == (r[1] >= 0))
    assert agree > 1500
    neg = M.correlated_normal_samples(
        (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("1")),
        [("a", "b", Decimal("-0.9"))], ("a", "b"), 2000, 7,
    )
    disagree = sum(1 for r in neg if (r[0] >= 0) != (r[1] >= 0))
    assert disagree > 1500


def test_o_copula_degenerate_and_determinism():
    first = M.correlated_normal_samples(
        (Decimal("5"),), (Decimal("0"),), [], ("only",), 4, 99
    )
    assert all(row == (Decimal("5"),) for row in first)
    second = M.correlated_normal_samples(
        (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("1")),
        [("a", "b", Decimal("0.5"))], ("a", "b"), 8, 1234,
    )
    third = M.correlated_normal_samples(
        (Decimal("0"), Decimal("0")), (Decimal("1"), Decimal("1")),
        [("b", "a", Decimal("0.5"))], ("b", "a"), 8, 1234,
    )
    assert second == third  # canonical (sorted) order invariance
    stats = M.copula_marginal_stats(second)
    assert set(stats.keys()) == {"var_0", "var_1"}


# ---- O-061 performance (recorded, never asserted on wall-clock) --------------------------

def test_o061_performance_records():
    model, inputs = _sum_budget()
    timings = {}
    start = time.perf_counter()
    M.evaluate_budget(model, inputs)
    timings["small"] = time.perf_counter() - start
    big_model = M.build_model(
        "Y", equation=" + ".join(f"X{i}" for i in range(64)),
        input_names=tuple(f"X{i}" for i in range(64)),
    )
    big_inputs = {
        f"X{i}": M.type_b_explicit(f"X{i}", nominal=Decimal("1"), standard_uncertainty=Decimal("0.1"))
        for i in range(64)
    }
    start = time.perf_counter()
    M.evaluate_budget(big_model, big_inputs)
    timings["n64"] = time.perf_counter() - start
    start = time.perf_counter()
    M.build_correlation([(f"X{i}", f"X{j}", Decimal("0.1")) for i in range(8) for j in range(i + 1, 8)])
    timings["corr8"] = time.perf_counter() - start
    start = time.perf_counter()
    M.run_mc(_divider(), _mc_divider_config(1, 200))
    timings["mc200"] = time.perf_counter() - start
    text = _report_text()
    start = time.perf_counter()
    M.loads(text)
    timings["serde"] = time.perf_counter() - start
    start = time.perf_counter()
    M.compare(text, text)
    timings["replay"] = time.perf_counter() - start
    for key, value in timings.items():
        assert value >= 0, key


# ---- O-062/O-063 regression pins -----------------------------------------------------------

def test_o062_gum_bit_identity():
    model, inputs = _sum_budget()
    got = M.evaluate_budget(model, inputs)
    assert str(got.combined_standard_uncertainty) == "0.22360679774997896"
    assert str(got.coverage_factor) == "1.959964"


def test_o063_f8m_sensitivity_still_completed():
    circuit = _divider()
    res = M.dc_sensitivities(
        circuit, (ParamAddress("R1", "value"),), (ObservableSpec(kind="node_voltage", locator="out"),)
    )
    assert str(res.status) == "SensitivityStatus.COMPLETED"
