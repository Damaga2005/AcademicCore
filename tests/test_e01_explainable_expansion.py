"""E0.1 Explainable Execution Expansion -- test suite.

Sections:

- symbolic engine: parser, printers, safety, normal form
- derivatives: power, sum, product, quotient, chain, table, NO_RULE
- integrals: power, n = -1, linearity, constant factor, substitution
  (linear and general), by parts, definite (Barrow + Simpson),
  discontinuity refusal, NO_RULE
- linear equations and simplification
- anti-fake-step guarantees: 1:1 engine step ↔ event, tampering, removed
  events, reported gaps, the renderer invents nothing
- GUM, F8-N Newton, F8-P bisection
- F8-Q pedagogical causality and ``digital-circuit/1``
- equation pedagogical mode, and E0 unchanged
- renderer lessons, application service, UI
- determinism across processes and hash seeds, security / AST,
  architecture

Deterministic data only (no RNG, no hypothesis).
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.application.explain_render import (
    LESSON_FIELDS,
    build_view,
    lesson_lines,
    render_markdown,
    render_text,
)
from academic_core.application.explain_service import transition_explanation
from academic_core.domain.engineering import digital_circuit as DC
from academic_core.domain.engineering import gum as G
from academic_core.domain.engineering.control.margins import margins
from academic_core.domain.engineering.control.tf import make_tf
from academic_core.domain.engineering.digital import LogicAnalyzer
from academic_core.domain.engineering.mna.nonlinear import solve_nonlinear_dc
from academic_core.domain.engineering.symbolic import derive, expr, integrate, normal, solve
from academic_core.domain.engineering.symbolic.steps import MAX_STEPS, StepLog
from academic_core.domain.execution import (
    EQUIVALENT,
    RESULT_DIFFERS,
    CheckStatus,
    EventKind,
    ExecutionTrace,
    Outcome,
    VerificationStatus,
    compare,
)
from academic_core.domain.execution import control as ctl
from academic_core.domain.execution import digital as dig
from academic_core.domain.execution import equation as eqn
from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution import symbolic as sym
from academic_core.domain.execution import uncertainty as unc
from academic_core.errors import (
    IntegrationError,
    SerializationError,
    UnsupportedError,
    ValidationError,
    VersionMismatchError,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "execution_trace"
D = Decimal
DIODE = """* diode_demo
V1 in 0 5V
R1 in a 1kohm
D1 a 0 D
.param D1 Is=1e-14A n=1 Vt=0.02585V
.end
"""
DIVIDER = ({"Vi": "12 V", "R1": "1 kohm", "R2": "2 kohm"}, "Vout = Vi * R2 / (R1 + R2)", "voltage")
SVC = DigitalAnalysisService()
HALF = AnalyzerRequest("half_adder", ("a", "b", "sum", "carry"), "0", "5")


def steps_of(trace):
    """(rule, before, after) of every symbolic STEP event, in order."""
    out = []
    for e in trace.events:
        names = dict(e.values)
        if e.kind is EventKind.STEP and "rule" in names:
            out.append((names["rule"].text, names["before"].text, names["after"].text))
    return out


def rules(trace):
    return [r for r, _b, _a in steps_of(trace)]


def check_status(trace):
    return [c.check.status for c in trace.checks()]


def pedagogical_capture(demo="half_adder", channels=("a", "b", "sum", "carry"), end="5"):
    req = AnalyzerRequest(demo, channels, "0", end)
    return dig.explain_capture(SVC.new_circuit(demo), SVC.build_config(req), context=(("demo", demo),),
                               pedagogical=True)


def demo_factory(ctx):
    return SVC.new_circuit(ctx["demo"])


# =============================================================== symbolic engine: parser / printers

@pytest.mark.parametrize("source,printed", [
    ("x^2 + 3*x - 1", "x^2 + 3*x - 1"),
    ("x**3", "x^3"),
    ("-(x+1)", "-(x + 1)"),
    ("sin(x^2+1)", "sin(x^2 + 1)"),
    ("2.5*x", "5/2*x"),
    ("x - (y - z)", "x - (y - z)"),
    ("a/(b*c)", "a/(b*c)"),
    ("(-2)^2", "(-2)^2"),
])
def test_e01_p01_parse_and_print(source, printed):
    assert expr.text(expr.parse(source)) == printed


@pytest.mark.parametrize("source,reason", [
    ("", "PARSE_ERROR"),
    ("2x", "PARSE_ERROR"),
    ("foo(x)", "PARSE_ERROR"),
    ("__import__('os')", "PARSE_ERROR"),
    ("x;y", "PARSE_ERROR"),
    ("x" * 300, "EXPRESSION_LIMIT"),
    ("(" * 60 + "x" + ")" * 60, "EXPRESSION_LIMIT"),
])
def test_e01_p02_parser_refuses(source, reason):
    with pytest.raises(ValidationError, match=reason):
        expr.parse(source)


def test_e01_p03_code_printer_matches_certified_evaluator():
    from academic_core.domain.engineering.symbolic.numeric import value
    for source, x, expected in (("x^2", "3", "9"), ("x^-1", "2", "0.5"), ("x^2^2", "2", "16"),
                                ("-x^2", "3", "-9"), ("2^x", "3", None)):
        got = value(expr.parse(source), {"x": D(x)})
        if expected is None:
            assert abs(got - 8) < D("1e-20")
        else:
            assert got == D(expected)


def test_e01_p04_normal_form_rules_are_named():
    simple, fired = normal.simplify(expr.parse("(x+1)^2 - x^2"), "x", expand=True)
    assert expr.text(simple) == "2*x + 1"
    assert "desarrollo de potencia" in fired and "agrupar términos semejantes" in fired
    assert normal.equivalent(expr.parse("(x+1)*(x-1)"), expr.parse("x^2 - 1"), "x")
    assert not normal.equivalent(expr.parse("x^2"), expr.parse("x^3"), "x")
    assert normal.linear_parts(expr.parse("3*x + 2 - x"), "x") == (2, 2)
    assert normal.linear_parts(expr.parse("x^2"), "x") is None


def test_e01_p05_step_log_bounds():
    log = StepLog()
    with pytest.raises(ValidationError, match="EXPRESSION_LIMIT"):
        log.add("op", "r", "x" * 501, "y")
    for _ in range(MAX_STEPS):
        log.add("op", "r", "a", "b")
    with pytest.raises(ValidationError, match="EXPRESSION_LIMIT"):
        log.add("op", "r", "a", "b")


# =============================================================== derivatives

@pytest.mark.parametrize("source,result,needed", [
    ("x^3", "3*x^2", ["regla de la potencia"]),
    ("3*x^2 + 2*x - 5", "6*x + 2", ["regla de la suma", "regla de la resta", "factor constante"]),
    ("x*sin(x)", "x*cos(x) + sin(x)", ["regla del producto: identificar factores", "regla del producto: sustituir"]),
    ("(x^2+1)/(x-1)", "(x^2 - 2*x - 1)/(x - 1)^2",
     ["regla del cociente: identificar numerador y denominador", "regla del cociente: sustituir"]),
    ("sin(x^2+1)", "2*x*cos(x^2 + 1)",
     ["regla de la cadena: identificar función exterior e interior", "regla de la cadena: sustituir"]),
    ("(x^2+1)^3", "6*x*(x^2 + 1)^2", ["derivar la exterior (regla de la potencia)"]),
    ("exp(2*x)", "2*exp(2*x)", ["derivar la exterior (tabla: d/du exp(u) = exp(u))"]),
    ("log(x)", "1/x", ["tabla: d/du log(u) = 1/u"]),
    ("2^x", "2^x*log(2)", ["exponencial de base constante: sustituir"]),
])
def test_e01_d01_derivative_rules(source, result, needed):
    t = sym.explain_derivative(source)
    assert t.outcome is Outcome.SUCCESS and t.result.text == result
    assert t.verification.status is VerificationStatus.PASS
    for rule in needed:
        assert rule in rules(t), (rule, rules(t))


def test_e01_d02_power_rule_shows_the_substitution():
    t = sym.explain_derivative("x^5")
    step = next(e for e in t.events if dict(e.values).get("rule") and dict(e.values)["rule"].text == "regla de la potencia")
    values = dict(step.values)
    assert values["substitution"].text == "n = 5" and values["after"].text == "5*x^(5 - 1)"
    assert step.why == "d/dx x^n = n·x^(n-1)"


def test_e01_d03_chain_rule_is_four_real_steps_in_order():
    t = sym.explain_derivative("sin(x^2)")
    r = rules(t)
    first = r.index("regla de la cadena: identificar función exterior e interior")
    outer = r.index("derivar la exterior (tabla: d/du sin(u) = cos(u))")
    inner = r.index("regla de la potencia")
    subst = r.index("regla de la cadena: sustituir")
    assert first < outer < inner < subst


def test_e01_d04_numeric_verification_is_independent():
    t = sym.explain_derivative("x^3*exp(x)")
    numeric = [c for c in t.checks() if "diferencia central" in c.check.what][0]
    assert numeric.check.status is CheckStatus.PASS and numeric.check.tolerance.number == sym.DERIVATIVE_TOL
    assert "x=0.7" in numeric.check.detail and "x=2.9" in numeric.check.detail


def test_e01_d05_parameters_make_the_numeric_check_not_applicable():
    t = sym.explain_derivative("a*x^2")
    assert t.result.text == "2*x*a"
    assert CheckStatus.NOT_APPLICABLE in check_status(t) and CheckStatus.PASS in check_status(t)


def test_e01_d06_no_rule_is_reported_and_partial_steps_kept():
    t = sym.explain_derivative("x^2 + x^x")
    assert t.outcome is Outcome.FAILED and t.result is None
    err = [e for e in t.events if e.kind is EventKind.ERROR][0].error
    assert err.code == "AC-UNS-001" and err.reason == "NO_RULE"
    assert "regla de la potencia" in rules(t)  # x^2 was really differentiated before x^x stopped it
    assert t.verification.status is VerificationStatus.NONE


# =============================================================== integrals

@pytest.mark.parametrize("source,result,needed", [
    ("3*x^2 + 2*x + 1", "x^3 + x^2 + x + C", ["linealidad: separar términos", "regla de la potencia"]),
    ("1/x", "log(abs(x)) + C", ["potencia n = -1: ∫x^(-1) dx = log(abs(x))"]),
    ("1/x^2", "-1/x + C", ["escribir como c·x^n", "regla de la potencia"]),
    ("sin(3*x+1)", "-cos(3*x + 1)/3 + C", ["cambio de variable (lineal): elegir u", "tabla: ∫sin(u) du = -cos(u)"]),
    ("(2*x+1)^5", "(2*x + 1)^6/12 + C", ["cambio de variable (lineal): elegir u"]),
    ("2*x*cos(x^2)", "sin(x^2) + C", ["cambio de variable (general): elegir u", "cambio de variable: deshacer el cambio"]),
    ("x/(x^2+1)", "log(abs(x^2 + 1))/2 + C", ["cambio de variable: reescribir en u"]),
    ("log(x)/x", "log(x)^2/2 + C", ["cambio de variable (general): elegir u"]),
    ("x*exp(x)", "x*exp(x) - exp(x) + C", ["integración por partes: elegir u y dv", "integración por partes: combinar"]),
    ("log(x)", "-x + x*log(x) + C", ["integración por partes: elegir u y dv"]),
    ("x^2*sin(x)", "-x^2*cos(x) + 2*x*sin(x) + 2*cos(x) + C", ["integración por partes: aplicar la fórmula"]),
    ("(x+1)*(x-1)", "x^3/3 - x + C", ["integrar la forma reescrita"]),
    ("tan(x)", "-log(abs(cos(x))) + C", ["tabla: ∫tan(u) du = -log(abs(cos(u)))"]),
])
def test_e01_i01_integral_rules(source, result, needed):
    t = sym.explain_integral(source)
    assert t.outcome is Outcome.SUCCESS and t.result.text == result, t.result
    assert t.verification.status is VerificationStatus.PASS
    for rule in needed:
        assert rule in rules(t), (rule, rules(t))
    assert rules(t)[-1] == "constante de integración"


def test_e01_i02_by_parts_twice_is_recorded_twice():
    t = sym.explain_integral("x^2*sin(x)")
    assert rules(t).count("integración por partes: elegir u y dv") == 2


def test_e01_i03_failed_attempts_are_never_shown():
    # x*exp(x): a substitution is tried first (on a scratch log) and abandoned; only by parts is shown
    t = sym.explain_integral("x*exp(x)")
    assert not any(r.startswith("cambio de variable") for r in rules(t))


def test_e01_i04_definite_integral_exact_and_simpson():
    t = sym.explain_integral("3*x^2", "x", "0", "2")
    assert t.result.text == "8"
    r = rules(t)
    assert r[-3:] == ["regla de Barrow: evaluar en el límite superior", "regla de Barrow: evaluar en el límite inferior",
                      "regla de Barrow: restar"]
    simpson = [c for c in t.checks() if "Simpson" in c.check.what][0]
    assert simpson.check.status is CheckStatus.PASS


def test_e01_i05_definite_integral_decimal_value():
    t = sym.explain_integral("sin(x)", "x", "0", "1")
    assert t.outcome is Outcome.SUCCESS and D(t.result.text).quantize(D("1e-12")) == D("0.459697694132")
    assert t.verification.status is VerificationStatus.PASS


def test_e01_i06_discontinuity_is_refused_not_hidden():
    t = sym.explain_integral("1/x", "x", "-1", "1")
    err = [e for e in t.events if e.kind is EventKind.ERROR][0].error
    assert t.outcome is Outcome.FAILED and err.reason == "DOMAIN"
    assert "constante de integración" in rules(t)  # the antiderivative was really found before refusing


def test_e01_i07_no_rule_and_bad_limits():
    t = sym.explain_integral("abs(x)")
    assert [e.error.reason for e in t.events if e.kind is EventKind.ERROR] == ["NO_RULE"]
    with pytest.raises(ValidationError, match="both limits"):
        sym.explain_integral("x", "x", "0")
    t = sym.explain_integral("x", "x", "0", "pi")
    assert [e.error.reason for e in t.events if e.kind is EventKind.ERROR] == ["INVALID_INPUT"]


def test_e01_i08_log_abs_verification_is_numeric_and_says_so():
    t = sym.explain_integral("1/x")
    c = t.checks()[0].check
    assert c.status is CheckStatus.PASS and c.detail.startswith("numérica")


def test_e01_i09_normal_form_verification_proves_polynomials():
    t = sym.explain_integral("x^3 - 2*x")
    assert t.checks()[0].check.detail.startswith("demostrado")


# =============================================================== equations / simplification

def test_e01_e01_linear_equation_steps_and_exact_verification():
    t = sym.explain_linear_equation("3*x + 2 = x - 4")
    assert t.result.text == "x = -3"
    assert rules(t) == ["plantear la ecuación", "transponer el término en la incógnita",
                        "transponer el término independiente", "despejar: dividir ambos lados entre el coeficiente"]
    c = t.checks()[0].check
    assert c.status is CheckStatus.PASS and c.actual.text == c.expected.text == "-7"
    assert c.detail == "3*(-3) + 2 = -3 - 4"


def test_e01_e02_identity_contradiction_and_nonlinear():
    ident = sym.explain_linear_equation("2*(x+1) = 2*x + 2")
    assert ident.result.text == "todo x es solución" and ident.verification.status is VerificationStatus.PASS
    assert "simplificar el lado izquierdo" in rules(ident)
    contra = sym.explain_linear_equation("x = x + 1")
    assert contra.result.text == "sin solución" and contra.verification.status is VerificationStatus.PASS
    nonlin = sym.explain_linear_equation("x^2 = 4")
    assert [e.error.reason for e in nonlin.events if e.kind is EventKind.ERROR] == ["NO_RULE"]
    bad = sym.explain_linear_equation("x = 1 = 2")
    assert [e.error.reason for e in bad.events if e.kind is EventKind.ERROR] == ["PARSE_ERROR"]


def test_e01_e03_fractional_coefficient():
    t = sym.explain_linear_equation("x/2 = 3")
    assert t.result.text == "x = 6"
    step = [e for e in t.events if dict(e.values).get("rule") and "despejar" in dict(e.values)["rule"].text][0]
    assert dict(step.values)["substitution"].text == "3 / (1/2) = 6"


def test_e01_e04_simplify_before_rule_after():
    t = sym.explain_simplify("(x+1)^2 - x^2")
    assert t.result.text == "2*x + 1"
    for rule, before, after in steps_of(t):
        assert rule and before and after and before != after
    unchanged = sym.explain_simplify("x")
    assert any(e.kind is EventKind.DECISION and e.title == "Sin cambios" for e in unchanged.events)


def test_e01_e05_variable_validation():
    for bad in ("", "2x", "sin", "x y", None):
        with pytest.raises(ValidationError):
            sym.explain_derivative("x", bad)


# =============================================================== anti-fake-step guarantees

def test_e01_f01_every_engine_step_is_exactly_one_event():
    for source in ("x*sin(x)", "(x^2+1)/(x-1)", "sin(x^2+1)"):
        log = StepLog()
        derive.derivative(expr.parse(source), "x", log)
        engine = [(s.rule, s.before, s.after) for s in log.steps]
        assert steps_of(sym.explain_derivative(source)) == engine
    for source in ("2*x*cos(x^2)", "x*exp(x)"):
        log = StepLog()
        integrate.antiderivative(expr.parse(source), "x", log)
        assert steps_of(sym.explain_integral(source)) == [(s.rule, s.before, s.after) for s in log.steps]


def test_e01_f02_step_refs_follow_the_engine_uses():
    t = sym.explain_derivative("x*sin(x)")
    subst = [e for e in t.events if dict(e.values).get("rule") and dict(e.values)["rule"].text == "regla del producto: sustituir"][0]
    used = [dict(t.event(r).values)["rule"].text for r in subst.refs]
    assert used[0] == "regla del producto: identificar factores" and len(used) == 3


def test_e01_f03_modifying_a_step_breaks_digest_and_replay():
    t = sym.explain_integral("2*x*cos(x^2)")
    doc = json.loads(t.to_json())
    for e in doc["events"]:
        for v in e["values"]:
            if v["name"] == "after" and v["value"] == {"text": "sin(u)"}:
                v["value"] = {"text": "cos(u)"}  # a fake step
    forged = ExecutionTrace.from_json(json.dumps(doc))
    assert forged.digest() != t.digest()
    report = compare(forged, sym.replay_math(forged))
    assert report.status == RESULT_DIFFERS and report.first_difference.startswith("events[")


def test_e01_f04_removing_an_event_is_not_filled_in():
    t = sym.explain_derivative("sin(x^2)")
    doc = json.loads(t.to_json())
    del doc["events"][5]
    with pytest.raises(ValidationError):
        ExecutionTrace.from_json(json.dumps(doc))
    # renumbering to hide the gap still leaves a dangling reference or a different replay
    for k, e in enumerate(doc["events"]):
        e["id"] = f"e{k + 1}"
    try:
        forged = ExecutionTrace.from_json(json.dumps(doc))
    except ValidationError:
        return
    assert compare(forged, sym.replay_math(forged)).status == RESULT_DIFFERS


def test_e01_f05_missing_internal_steps_are_reported():
    assert any(e.kind is EventKind.WARNING and "coma flotante" in (e.why or "")
               for e in unc.explain_gum("S", "S = A + B", {"A": "value=1; u=0.1", "B": "value=2; u=0.2"}).events)
    ped = pedagogical_capture("xor3_glitch", ("a", "b", "c", "y"), "4")
    assert any(e.kind is EventKind.WARNING and "no expone" in (e.why or "") for e in ped.events)
    failed = sym.explain_derivative("x^x")
    assert failed.outcome is Outcome.FAILED and failed.result is None


def test_e01_f06_the_renderer_invents_nothing():
    for t in (sym.explain_integral("x*exp(x)"), sym.explain_linear_equation("3*x + 2 = x - 4"),
              unc.explain_gum("R", "R = V / I", {"V": "value=5; unit=V; u=0.01", "I": "value=0.002; unit=A; u=0.00001"}, "ohm"),
              ctl.explain_margins("2", "1, 3, 2, 0"), pedagogical_capture()):
        view = build_view(t)
        ids = {e.event_id for e in t.events}
        non_input = [e for e in t.events if e.kind is not EventKind.INPUT]
        assert [lesson.event_id for lesson in view.lessons] == [e.event_id for e in non_input]
        for lesson, e in zip(view.lessons, non_input):
            assert lesson.event_id in ids
            names = dict(e.values)
            if "rule" in names and "before" in names:
                assert lesson.rule == names["rule"].text and lesson.output == names["after"].text
                assert lesson.input == names["before"].text
            recorded = json.dumps(t.to_dict(), ensure_ascii=False)
            for field in (lesson.rule, lesson.explanation):
                if field and not field.endswith("…"):
                    assert field in recorded or field in (e.check.what if e.check else ""), field


def test_e01_f07_renderer_does_not_mutate_and_imports_no_engine():
    t = sym.explain_derivative("x*sin(x)")
    before = t.to_json()
    build_view(t)
    assert t.to_json() == before
    tree = ast.parse((SRC / "application" / "explain_render.py").read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"__future__", "dataclasses", "academic_core.domain.execution", "academic_core.errors"}


def test_e01_f08_lesson_verification_follows_causal_chain():
    view = build_view(sym.explain_derivative("x^2"))
    assert all(lesson.verification.startswith(("cubierto por", "e")) for lesson in view.lessons)
    gum_view = build_view(unc.explain_gum("S", "S = A + B", {"A": "value=1; u=0.1", "B": "value=2; u=0.2"}))
    warn = [lesson for lesson in gum_view.lessons if lesson.kind == "Aviso"][0]
    assert warn.verification == "sin comprobación que dependa de este paso"


# =============================================================== GUM

GUM_R = ("R", "R = V / I", {"V": "value=5; unit=V; u=0.01; type=B; distribution=rectangular; dof=inf",
                             "I": "value=0.002; unit=A; u=0.00001; type=A; distribution=normal; dof=9"}, "ohm")


def test_e01_g01_budget_steps_and_checks():
    t = unc.explain_gum(*GUM_R)
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    titles = [e.title for e in t.events]
    for needed in ("Valor del mensurando", "Coeficiente de sensibilidad c_I", "Contribución de V", "Varianza combinada",
                   "Incertidumbre típica combinada", "Grados de libertad efectivos (Welch–Satterthwaite)",
                   "Factor de cobertura k", "Incertidumbre expandida"):
        assert needed in titles
    whats = [c.check.what for c in t.checks()]
    assert "U = k·u_c" in whats and "c_I = ∂f/∂I" in whats
    result = G.evaluate_gum(G.MeasurementModel("R", "R = V / I", output_unit="ohm"),
                            {n: unc.parse_spec(n, s) for n, s in GUM_R[2].items()})
    assert t.result.text == result.summary()


def test_e01_g02_sensitivity_facts_are_the_engine_facts():
    t = unc.explain_gum("P", "P = V^2/R", {"V": "value=10; unit=V; u=0.05", "R": "value=50; unit=ohm; u=0.1"}, "W")
    c_v = [e for e in t.events if e.title == "Coeficiente de sensibilidad c_V"][0]
    values = dict(c_v.values)
    assert values["method"].text == "NUMERICAL" and values["h"].number == D("0.000010")
    assert (values["f_x_plus_h"].number - values["f_x_minus_h"].number) / (2 * values["h"].number) == c_v.result.number
    analytic = unc.explain_gum(*GUM_R)
    c_i = [e for e in analytic.events if e.title == "Coeficiente de sensibilidad c_I"][0]
    assert dict(c_i.values)["rule"].text == "quotient: d(X1/X2)/dX2 = -X1/X2^2"


def test_e01_g03_correlation_adds_covariance_step():
    t = unc.explain_gum("S", "S = A + B", {"A": "value=1; u=0.1", "B": "value=2; u=0.2"}, correlations="A,B=0.5")
    cov = [e for e in t.events if e.title == "Términos de covarianza"][0]
    assert cov.result.number == D("0.020") * 1 or cov.result.number == D("0.02")
    assert t.verification.status is VerificationStatus.PASS


def test_e01_g04_replay_errors_and_refusals():
    t = unc.explain_gum(*GUM_R)
    assert compare(t, unc.replay_gum(t)).status == EQUIVALENT
    bad = unc.explain_gum("R", "R = V / I", {"V": "value=5; u=-1", "I": "value=1; u=0.1"})
    assert bad.outcome is Outcome.FAILED
    with pytest.raises(ValidationError):
        unc.explain_gum("R", "R = V", {"equation": "value=1; u=0.1"})
    with pytest.raises(ValidationError):
        unc.parse_spec("V", "value=1; u=0.1; color=red")
    with pytest.raises(UnsupportedError):
        unc.explain_gum_model(G.MeasurementModel("Y", evaluator=lambda env: env["X"]), {})


def test_e01_g05_hook_is_optional_and_changes_nothing():
    model = G.MeasurementModel("R", "R = V / I", output_unit="ohm")
    inputs = {n: unc.parse_spec(n, s) for n, s in GUM_R[2].items()}

    class Obs:
        def __init__(self):
            self.n = 0

        def sensitivity(self, *args):
            self.n += 1

    obs = Obs()
    a, b = G.evaluate_gum(model, inputs), G.evaluate_gum(model, inputs, observer=obs)
    assert a.budget == b.budget and a.expanded_uncertainty == b.expanded_uncertainty and obs.n == 2


# =============================================================== F8-N Newton

def test_e01_n01_iterations_are_the_solver_iterations():
    t = nwt.explain_nonlinear_dc(DIODE)
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    iterations = [e for e in t.events if e.title.startswith("Iteración")]
    reference = solve_nonlinear_dc(nwt.parse_circuit_spec(DIODE))
    assert len(iterations) == reference.provenance["iterations"] == 10
    last = dict(iterations[-1].values)
    assert last["res_ok"].text == "sí" and last["step_ok"].text == "sí"
    va = [nv.voltage.value for nv in reference.node_voltages if nv.node == "a"][0]
    assert last["V.a"].number == va
    assert [dict(e.values)["alpha"].number for e in iterations[:2]] == [D("0.125"), D("0.5")]


def test_e01_n02_failures_and_spec_round_trip():
    t = nwt.explain_nonlinear_dc(DIODE.replace(".param D1 Is=1e-14A n=1 Vt=0.02585V\n", ""))
    err = [e for e in t.events if e.kind is EventKind.ERROR][0].error
    assert t.outcome is Outcome.FAILED and err.code == "AC-VAL-001" and err.reason == "INVALID"
    for bad in (".param D9 Is=1A\n" + DIODE, DIODE.replace("Is=1e-14A", "Is=abc"), "R1 a\n"):
        assert nwt.explain_nonlinear_dc(bad).outcome is Outcome.FAILED
    for bad in (42, "x" * 600, "R1 a 0 1ohm\n" * 300):
        with pytest.raises(ValidationError, match="INVALID_INPUT"):
            nwt.explain_nonlinear_dc(bad)
    lines = [name for name, _ in nwt.explain_nonlinear_dc(DIODE).inputs]
    assert lines == [f"circuit.{k:03d}" for k in range(1, 7)]
    spec = nwt.circuit_spec(nwt.parse_circuit_spec(DIODE))
    assert nwt.circuit_spec(nwt.parse_circuit_spec(spec)) == spec


def test_e01_n03_replay_and_optional_hook():
    t = nwt.explain_nonlinear_dc(DIODE)
    assert compare(t, nwt.replay_nonlinear_dc(t)).status == EQUIVALENT
    circuit = nwt.parse_circuit_spec(DIODE)
    assert solve_nonlinear_dc(circuit).provenance["solver_digest"] == \
        solve_nonlinear_dc(circuit, observer=None).provenance["solver_digest"]


# =============================================================== F8-P bisection

def test_e01_c01_bisection_steps_and_checks():
    t = ctl.explain_margins("2", "1, 3, 2, 0")
    report = margins(make_tf((D(2),), (D(1), D(3), D(2), D(0))))
    assert t.outcome is Outcome.SUCCESS and t.verification.status is VerificationStatus.PASS
    decisions = [e for e in t.events if e.kind is EventKind.DECISION]
    assert [d.result.number for d in decisions][0] == D(report.omega_gc)
    assert all("BISECT_REL_TOL" in d.why for d in decisions)
    bisections = [e for e in t.events if e.title.startswith("Bisección")]
    assert len(bisections) > 20
    for e in bisections:
        v = dict(e.values)
        assert v["lo"].number <= v["omega_mid"].number <= v["hi"].number


def test_e01_c02_no_crossover_and_bad_input():
    t = ctl.explain_margins("1", "1, 1")
    assert t.verification.status is VerificationStatus.NONE and CheckStatus.NOT_APPLICABLE in check_status(t)
    assert ctl.explain_margins("1", "a, b").outcome is Outcome.FAILED
    assert ctl.explain_margins("", "1").outcome is Outcome.FAILED


def test_e01_c03_replay_and_hook_neutral():
    t = ctl.explain_margins("10", "1, 2, 1, 0")
    assert compare(t, ctl.replay_margins(t)).status == EQUIVALENT
    loop = make_tf((D(10),), (D(1), D(2), D(1), D(0)))
    assert margins(loop) == margins(loop, observer=None)


# =============================================================== F8-Q pedagogical + digital-circuit/1

def test_e01_q01_non_pedagogical_capture_is_unchanged():
    req = AnalyzerRequest("xor3_glitch", ("a", "y"), "0", "4", "y", "BOTH", "0", "1")
    t = dig.explain_capture(SVC.new_circuit("xor3_glitch"), SVC.build_config(req), context=(("demo", "xor3_glitch"),))
    assert "mode" not in dict(t.inputs) and not any(e.title.startswith("Causa") for e in t.events)
    assert build_view(t).lessons == ()


def test_e01_q02_gate_causes_are_the_certified_evaluation():
    t = pedagogical_capture()
    causes = [e for e in t.events if e.kind is EventKind.STEP and "puerta" in e.title]
    assert causes and all(dict(e.values)["consistent"].text == "sí" for e in causes)
    carry = [e for e in causes if e.title.startswith("Causa de carry → HIGH en t = 1.5 s")][0]
    assert carry.formula == "C = AND(A=HIGH, B=HIGH)"
    transition = t.event(carry.refs[0])
    assert transition.title == "carry: LOW → HIGH en t = 1.5 s"
    cause_titles = [t.event(r).title for r in carry.refs[1:]]
    assert "a: LOW → HIGH en t = 1.5 s" in cause_titles


def test_e01_q03_stimulus_causes_and_transients():
    t = pedagogical_capture("xor3_glitch", ("a", "b", "c", "y"), "4")
    stim = [e for e in t.events if e.title.startswith("Causa de a") and "estímulo" in e.title]
    assert stim and all("PatternStimulus" in e.why for e in stim)
    transients = [e for e in t.events if "transitoria" in e.title]
    assert transients and all(e.kind is EventKind.WARNING for e in transients)


def test_e01_q04_unprobed_inputs():
    t = pedagogical_capture("wide_nand", ("in0", "y"), "3")
    gate = [e for e in t.events if "puerta nand16" in e.title]
    assert gate and "i01=HIGH" in gate[0].formula  # undriven net: its declared state, a topology fact
    circuit = SVC.new_circuit("half_adder")
    req = AnalyzerRequest("half_adder", ("sum",), "0", "5")
    only_sum = dig.explain_capture(circuit, SVC.build_config(req), pedagogical=True)
    hidden = [e for e in only_sum.events if "no observable" in e.title]
    assert hidden and all(e.kind is EventKind.WARNING for e in hidden)


def test_e01_q05_pedagogical_replay_demo_and_document():
    t = pedagogical_capture()
    assert compare(t, dig.replay_capture(t, demo_factory)).status == EQUIVALENT
    doc = DC.circuit_to_json(SVC.new_circuit("half_adder"))
    circuit = DC.circuit_from_json(doc)
    digest = DC.circuit_digest(circuit)
    t2 = dig.explain_capture(circuit, SVC.build_config(HALF), context=(("circuit_digest", digest),), pedagogical=True)

    def from_doc(ctx):
        c = DC.circuit_from_json(doc)
        assert DC.circuit_digest(c) == ctx["circuit_digest"]
        return c
    assert compare(t2, dig.replay_capture(t2, from_doc)).status == EQUIVALENT
    with pytest.raises(ValidationError, match="reserved"):
        dig.explain_capture(circuit, SVC.build_config(HALF), context=(("mode", "x"),))


@pytest.mark.parametrize("demo", sorted(d.key for d in SVC.demos()))
def test_e01_q06_digital_circuit_round_trip_and_same_simulation(demo):
    circuit = SVC.new_circuit(demo)
    text = DC.circuit_to_json(circuit)
    back = DC.circuit_from_json(text)
    assert DC.circuit_to_json(back) == text and DC.circuit_from_json(text.encode()) is not None
    assert text == json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
    channels = tuple(p.probe_id for p in circuit.probes())
    req = AnalyzerRequest(demo, channels, "0", "3")
    a = LogicAnalyzer().capture(SVC.new_circuit(demo), SVC.build_config(req))
    b = LogicAnalyzer().capture(DC.circuit_from_json(text), SVC.build_config(req))
    assert a.trace.digest() == b.trace.digest()


def _doc():
    return json.loads(DC.circuit_to_json(SVC.new_circuit("half_adder")))


@pytest.mark.parametrize("mutate,error", [
    (lambda d: d.update(version=2), VersionMismatchError),
    (lambda d: d.update(schema="x"), ValidationError),
    (lambda d: d.update(extra=1), ValidationError),
    (lambda d: d["nets"].reverse(), ValidationError),
    (lambda d: d["nets"][0].update(initial="1"), ValidationError),
    (lambda d: d["gates"][0].update(kind="MAJ"), ValidationError),
    (lambda d: d["stimuli"][0].update(type="clock"), ValidationError),
    (lambda d: d["stimuli"][0].update(period="0.50"), ValidationError),
    (lambda d: d["stimuli"][0].update(count=True), ValidationError),
    (lambda d: d["gates"].append({"id": "zz", "inputs": ["A"], "kind": "NOT", "output": "S"}), ValidationError),
])
def test_e01_q07_digital_circuit_strict_decoding(mutate, error):
    d = _doc()
    mutate(d)
    with pytest.raises(error):
        DC.circuit_from_json(json.dumps(d))


def test_e01_q08_digital_circuit_json_layer():
    text = DC.circuit_to_json(SVC.new_circuit("half_adder"))
    for bad in (text.replace('"version":1', '"version":1.0'), '{"a":1,"a":2}', "[" * 10 + "]" * 10, "NaN", 3,
                b"\xff"):
        with pytest.raises((SerializationError, ValidationError)):
            DC.circuit_from_json(bad)
    with pytest.raises(SerializationError, match="CIRCUIT_LIMIT"):
        DC.circuit_from_json(" " * (DC.MAX_JSON_BYTES + 1))


def test_e01_q09_transition_explanation_extracts_recorded_events():
    t = pedagogical_capture()
    x = transition_explanation(t, "carry", 0)
    assert (x.time, x.previous, x.new, x.driver, x.available) == ("1.5", "LOW", "HIGH", "and_c", True)
    assert x.cause == "C = AND(A=HIGH, B=HIGH)" and any("and_c" in c for c in x.checks)
    assert all(t.event(i) for i in x.event_ids)
    transient = transition_explanation(t, "sum", 1)
    assert not transient.available and "no expone" in transient.why
    missing = transition_explanation(t, "carry", 999)
    assert not missing.available and missing.event_ids == ()
    plain = dig.explain_capture(SVC.new_circuit("half_adder"), SVC.build_config(HALF))
    assert not transition_explanation(plain, "carry", 0).available


# =============================================================== equation pedagogical mode / E0 unchanged

def test_e01_x01_equation_pedagogical_steps():
    t = eqn.explain_equation(*DIVIDER[:2], DIVIDER[2], pedagogical=True)
    titles = [e.title for e in t.events]
    assert "Conversión a unidades SI: R1" in titles and "Sustitución" in titles
    subst = [e for e in t.events if e.title == "Sustitución"][0]
    assert subst.formula == "Vout = (12 V) * (2 kohm) / ((1 kohm) + (2 kohm))"
    conv = [e for e in t.events if e.title == "Conversión a unidades SI: R2"][0]
    assert conv.result.number == D("2000") and conv.result.unit == "Ω"
    assert compare(t, eqn.replay_equation(t)).status == EQUIVALENT
    kinds = [lesson.kind for lesson in build_view(t).lessons]
    order = [kinds.index(k) for k in ("Fórmula", "Datos", "Conversión de unidades", "Sustitución", "Cálculo",
                                      "Resultado", "Verificación")]
    assert order == sorted(order)


def test_e01_x02_e0_golden_trace_unchanged():
    golden = (FIXTURES / "voltage_divider.json").read_text(encoding="utf-8").strip()
    t = eqn.explain_equation(*DIVIDER[:2], DIVIDER[2])
    assert t.to_json() == golden and "e0.mode" not in dict(t.inputs)
    with pytest.raises(ValidationError, match="reserved"):
        eqn.explain_equation({"e0.mode": "1 V"}, "y = 2")


# =============================================================== renderer / service / UI

def test_e01_r01_lesson_format():
    view = build_view(sym.explain_derivative("x^3"))
    lines = lesson_lines(view.lessons[1])
    assert tuple(line.split(":")[0] for line in lines) == LESSON_FIELDS
    text = render_text(view)
    assert "Paso a paso" in text and "Regla: regla de la potencia" in text and "Transformación: n = 3" in text
    md = render_markdown(view)
    assert "## Paso a paso" in md and "### Paso 1" in md


def test_e01_r02_e0_views_have_no_lessons():
    view = build_view(eqn.explain_equation(*DIVIDER[:2], DIVIDER[2]))
    assert view.lessons == () and "Paso a paso" not in render_text(view)


@pytest.fixture
def core(tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    return AcademicApp(Settings.load())


def test_e01_s01_service_operations_and_replay(core):
    ex = core.explain
    for view in (ex.explain_math("derivative", "x*sin(x)"), ex.explain_math("integral", "x", "x", "0", "1"),
                 ex.explain_math("linear-equation", "2*x = 4"), ex.explain_math("simplify", "x + x"),
                 ex.explain_gum(*GUM_R), ex.explain_nonlinear(DIODE), ex.explain_margins("2", "1, 3, 2, 0"),
                 ex.explain_exercise("voltage-divider", DIVIDER[0], pedagogical=True),
                 ex.explain_capture(HALF, pedagogical=True)):
        assert view.outcome == "SUCCESS" and view.lessons
        assert ex.replay(view.trace_json).status == EQUIVALENT
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        ex.explain_math("limit", "x")


def test_e01_s02_service_circuit_documents(core):
    ex = core.explain
    doc = ex.circuit_document("half_adder")
    trace = ex.document_capture_trace(doc, HALF, pedagogical=True)
    assert "demo" not in dict(trace.inputs) and "circuit_digest" in dict(trace.inputs)
    assert ex.replay(trace.to_json(), doc).status == EQUIVALENT
    with pytest.raises(ValidationError, match="MISSING_CIRCUIT"):
        ex.replay(trace.to_json())
    with pytest.raises(IntegrationError, match="CIRCUIT_MISMATCH"):
        ex.replay(trace.to_json(), doc.replace('"period":"0.5"', '"period":"0.25"'))
    x = ex.explain_transition(HALF, "carry", 0)
    assert x.driver == "and_c" and x.available


def test_e01_u01_exercise_math_row(qtbot, core):
    from academic_core.ui.exercises import ExercisePanel
    panel = ExercisePanel(core)
    qtbot.addWidget(panel)
    panel.math_expr.setText("x^2*sin(x)")
    panel.btn_derive.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    text = panel.output.toPlainText()
    assert panel.state.value == "SUCCESS" and "Paso a paso" in text and "regla del producto" in text
    panel.math_expr.setText("3*x^2")
    panel.math_lower.setText("0")
    panel.math_upper.setText("2")
    panel.btn_integrate.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    assert "regla de Barrow: restar" in panel.output.toPlainText() and panel.explanation.lessons
    panel.math_lower.clear()
    panel.math_upper.clear()
    panel.math_expr.setText("3*x + 2 = x - 4")
    panel.btn_solve_eq.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    assert "x = -3" in panel.output.toPlainText()
    panel.math_expr.setText("x^x")
    panel.btn_derive.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    assert panel.state.value == "WARNING" and "NO_RULE" in panel.output.toPlainText()


def test_e01_u02_exercise_step_by_step_button(qtbot, core):
    from academic_core.ui.exercises import ExercisePanel
    panel = ExercisePanel(core)
    qtbot.addWidget(panel)
    panel.selector.setCurrentText("ohm-v")
    panel.inputs.setPlainText("I=5 mA; R=1 kohm")
    panel.btn_steps.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    text = panel.output.toPlainText()
    assert panel.state.value == "SUCCESS" and "Tipo: Sustitución" in text and "Tipo: Conversión de unidades" in text


def test_e01_u03_logic_analyzer_transition_panel(qtbot, core):
    from academic_core.ui.logic_analyzer import LogicAnalyzerPanel
    panel = LogicAnalyzerPanel(core)
    qtbot.addWidget(panel)
    panel.demo.setCurrentIndex(panel.demo.findData("half_adder"))
    panel.end.setText("5")
    panel.start_capture()
    qtbot.waitUntil(lambda: panel.view is not None, timeout=20000)
    row = next(k for k, t in enumerate(panel.view.transitions) if t.channel_id == "carry")
    panel.table.selectRow(row)
    qtbot.waitUntil(lambda: "Driver: and_c" in panel.explanation.toPlainText(), timeout=20000)
    text = panel.explanation.toPlainText()
    for needed in ("Tiempo: 1.5 s", "Canal: carry", "Anterior: LOW", "Nuevo: HIGH", "Por qué cambió:",
                   "Comprobaciones: PASS"):
        assert needed in text
    panel.load_text(panel.view.trace_json)
    panel.explain_row(0)
    assert "no se puede explicar sin inventarla" in panel.explanation.toPlainText()


# =============================================================== determinism / security / architecture

_CHILD = """
import sys
sys.path.insert(0, {src!r})
from academic_core.domain.execution import symbolic as sym, uncertainty as unc, newton as nwt, control as ctl
from academic_core.domain.execution import digital as dig
from academic_core.application.digital_service import DigitalAnalysisService, AnalyzerRequest
svc = DigitalAnalysisService()
req = AnalyzerRequest("half_adder", ("a", "b", "sum", "carry"), "0", "5")
ts = [sym.explain_derivative("sin(x^2+1)*x"), sym.explain_integral("x^2*sin(x)"), sym.explain_integral("3*x^2", "x", "0", "2"),
      sym.explain_linear_equation("3*x + 2 = x - 4"), sym.explain_simplify("(x+1)^3"),
      unc.explain_gum("P", "P = V^2/R", {{"V": "value=10; unit=V; u=0.05", "R": "value=50; unit=ohm; u=0.1"}}, "W"),
      nwt.explain_nonlinear_dc({diode!r}), ctl.explain_margins("2", "1, 3, 2, 0"),
      dig.explain_capture(svc.new_circuit("half_adder"), svc.build_config(req), pedagogical=True)]
print(" ".join(t.digest() for t in ts))
"""


def test_e01_z01_identical_across_processes_and_hash_seeds():
    code = _CHILD.format(src=str(ROOT / "src"), diode=DIODE)
    outs = set()
    for seed in ("0", "1", "4242", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=300, check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    assert sym.explain_derivative("sin(x^2+1)*x").digest() == next(iter(outs)).split()[0]


NEW_MODULES = [SRC / "domain" / "engineering" / "symbolic" / f for f in
               ("__init__.py", "expr.py", "normal.py", "steps.py", "derive.py", "integrate.py", "solve.py", "numeric.py")] + [
    SRC / "domain" / "engineering" / "digital_circuit.py",
    SRC / "domain" / "execution" / "symbolic.py", SRC / "domain" / "execution" / "uncertainty.py",
    SRC / "domain" / "execution" / "newton.py", SRC / "domain" / "execution" / "control.py"]


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def test_e01_z02_no_dynamic_execution():
    banned_calls = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "globals", "locals", "open"}
    banned_mods = {"pickle", "marshal", "importlib", "subprocess", "os", "sys", "shutil", "socket", "ctypes"}
    for f in NEW_MODULES + [SRC / "application" / "explain_render.py", SRC / "application" / "explain_service.py"]:
        for node in ast.walk(_tree(f)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (f.name, node.func.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("system", "popen", "check_output"), f.name
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_mods, f.name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned_mods, f.name


def test_e01_z03_symbolic_engine_is_exact():
    for f in NEW_MODULES[:8]:
        text = f.read_text(encoding="utf-8")
        assert "float(" not in text and "import math" not in text, f.name
        for node in ast.walk(_tree(f)):
            assert not (isinstance(node, ast.Constant) and isinstance(node.value, float)), f.name


def test_e01_z04_layering():
    for f in NEW_MODULES:
        for node in ast.walk(_tree(f)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("academic_core.ui", "academic_core.application", "PySide6",
                                                   "academic_core.infrastructure")), (f.name, node.module)
    for name in ("exercises.py", "logic_analyzer.py"):
        for node in ast.walk(_tree(SRC / "ui" / name)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("academic_core.domain"), (name, node.module)
    engine = SRC / "domain" / "engineering"
    for f in engine.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "academic_core.domain.execution" not in text, f  # engines never import the trace layer


def test_e01_z05_f8q_package_untouched_and_hooks_are_optional():
    out = subprocess.run(["git", "diff", "--name-only", "0cf3554", "--", "src/academic_core/domain/engineering/digital"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 or out.stdout.strip() == ""
    import inspect
    for fn, name in ((solve_nonlinear_dc, "observer"), (margins, "observer"), (G.evaluate_gum, "observer"),
                     (G.MeasurementModel.get_sensitivity, "observer")):
        assert inspect.signature(fn).parameters[name].default is None


def test_e01_z06_limits_reject_huge_inputs():
    assert sym.explain_derivative("x+" * 200 + "x").outcome is Outcome.FAILED
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc("R1 a 0 1ohm\n" * 1000)
    assert ctl.explain_margins(", ".join(["1"] * 40), "1").outcome is Outcome.FAILED
    assert Fraction(1, 3) == integrate.point_value(expr.parse("x^3/3"), "x", Fraction(1))[1]
    with pytest.raises(UnsupportedError, match="NO_RULE"):
        integrate.integrate(expr.parse("x^x"), "x", StepLog())
    assert solve.solve_linear("x = 2", "x", StepLog()).value == 2
