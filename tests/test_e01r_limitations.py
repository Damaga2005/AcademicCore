"""E0.1-R+ limitation closure: one section per limitation L1..L7.

Each test either proves a limitation FIXED (real implementation, no
invented step) or pins the behaviour INTENTIONALLY RETAINED (honest
``NO_RULE`` / ``UNSUPPORTED`` / ``UNOBSERVABLE_INTERNAL_DELTA`` /
``KEEP_CERTIFIED_BEHAVIOR``).
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from decimal import Decimal, localcontext

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.application.explain_render import build_view
from academic_core.application.explain_service import transition_explanation
from academic_core.domain.engineering import digital_circuit as DC
from academic_core.domain.engineering import gum as G
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.control.tf import make_tf
from academic_core.domain.engineering.digital import (
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    DigitalSimulator,
    GateKind,
    LogicState,
)
from academic_core.domain.execution import (
    EQUIVALENT,
    CheckStatus,
    EventKind,
    Outcome,
    VerificationStatus,
    compare,
    verification_kind,
)
from academic_core.domain.execution import control as ctl
from academic_core.domain.execution import digital as dig
from academic_core.domain.execution import equation as eqn
from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution import symbolic as sym
from academic_core.domain.execution import uncertainty as unc
from academic_core.errors import UnsupportedError, ValidationError

D = Decimal
SVC = DigitalAnalysisService()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIODE = """* diode_demo
V1 in 0 5V
R1 in a 1kohm
D1 a 0 D
.param D1 Is=1e-14A n=1 Vt=0.02585V
.end
"""


def rules(trace):
    return [dict(e.values)["rule"].text for e in trace.events
            if e.kind is EventKind.STEP and "rule" in dict(e.values) and "before" in dict(e.values)]


def errors(trace):
    return [e.error.reason for e in trace.events if e.kind is EventKind.ERROR]


# =============================================================== L1 symbolic engine: more real rules

@pytest.mark.parametrize("source,result,rule", [
    ("2^x", "2^x/log(2) + C", "tabla: ∫a^x dx = a^x/log(a)"),
    ("1/cos(x)^2", "tan(x) + C", "tabla: ∫1/cos(u)^2 du = tan(u)"),
    ("1/sqrt(x)", "2*x^(1/2) + C", "reescribir la raíz como potencia"),
    ("x*sqrt(x)", "2*x^(5/2)/5 + C", "reescribir la raíz como potencia"),
    ("x*sqrt(x^2+1)", "(x^2 + 1)^(3/2)/3 + C", "cambio de variable (general): elegir u"),
])
def test_r_l1_01_new_integral_rules_are_real_and_verified(source, result, rule):
    t = sym.explain_integral(source)
    assert t.outcome is Outcome.SUCCESS and t.result.text == result
    assert rule in rules(t) and t.verification.status is VerificationStatus.PASS


@pytest.mark.parametrize("source,result,rule", [
    ("x + 0", "x", "elemento neutro (u + 0 = u)"),
    ("0 + x", "x", "elemento neutro (u + 0 = u)"),
    ("x - 0", "x", "elemento neutro (u + 0 = u)"),
    ("x*1", "x", "elemento neutro (1·u = u)"),
    ("1*x", "x", "elemento neutro (1·u = u)"),
    ("x*0", "0", "producto por cero"),
    ("0*x", "0", "producto por cero"),
    ("x/1", "x", "cociente de monomios"),
    ("x - x", "0", "eliminar términos nulos"),
    ("x/x", "1", "cancelación de factores (válida si el factor ≠ 0)"),
])
def test_r_l1_02_simplification_rules_named_with_domain(source, result, rule):
    t = sym.explain_simplify(source)
    assert t.result.text == result
    assert any(rule in r for r in rules(t)), rules(t)


def test_r_l1_03_derivative_steps_follow_the_ast_and_state_domains():
    t = sym.explain_derivative("x*sin(x)")
    r = rules(t)
    order = [r.index(x) for x in ("regla del producto: identificar factores", "derivada de la variable",
                                  "tabla: d/du sin(u) = cos(u)", "regla del producto: sustituir")]
    assert order == sorted(order) and any(x.startswith("elemento neutro") for x in r)  # then simplify
    assert {c.check.status for c in t.checks()} == {CheckStatus.PASS}  # then verify
    tan = sym.explain_derivative("tan(x)")
    assert any("cos(u) ≠ 0" in (e.why or "") for e in tan.events)
    log = sym.explain_derivative("log(x^2+1)")
    assert any("u > 0" in (e.why or "") for e in log.events)


def test_r_l1_04_unsupported_stays_honest():
    assert errors(sym.explain_derivative("x^x")) == ["NO_RULE"]
    assert errors(sym.explain_integral("abs(x)")) == ["NO_RULE"]
    assert errors(sym.explain_integral("exp(x^2)")) == ["NO_RULE"]  # no elementary antiderivative: no fake step
    assert errors(sym.explain_linear_equation("x^2 = 4")) == ["NO_RULE"]
    not_factored = sym.explain_simplify("(x^2-1)/(x-1)")
    assert not_factored.result.text == "(x^2 - 1)/(x - 1)"  # no polynomial division rule: nothing invented


def test_r_l1_05_integration_by_parts_twice_and_definite_pipeline():
    t = sym.explain_integral("x^2*sin(x)")
    assert rules(t).count("integración por partes: elegir u y dv") == 2
    d = sym.explain_integral("2^x", "x", "0", "1")
    r = rules(d)
    assert r[-3:] == ["regla de Barrow: evaluar en el límite superior", "regla de Barrow: evaluar en el límite inferior",
                      "regla de Barrow: restar"]
    with localcontext() as ctx:
        ctx.prec = 40
        assert abs(D(d.result.text) - 1 / D(2).ln()) < D("1e-25")


# =============================================================== L2 symbolic vs numeric verification

def test_r_l2_01_every_math_equivalence_check_is_labelled():
    for t in (sym.explain_derivative("x^3*exp(x)"), sym.explain_integral("x^3 - 2*x"), sym.explain_integral("1/x"),
              sym.explain_integral("3*x^2", "x", "0", "2"), sym.explain_linear_equation("3*x + 2 = x - 4"),
              sym.explain_linear_equation("x = x + 1"), sym.explain_simplify("(x+1)^2"),
              sym.explain_derivative("a*x^2")):
        for c in t.checks():
            assert verification_kind(c.check) in ("SYMBOLIC", "NUMERIC", "NONE"), c.check.what


def test_r_l2_02_labels_are_honest():
    poly = sym.explain_integral("x^3 - 2*x").checks()[0].check
    assert verification_kind(poly) == "SYMBOLIC" and poly.detail.startswith("demostrado")
    logabs = sym.explain_integral("1/x").checks()[0].check
    assert verification_kind(logabs) == "NUMERIC" and "demostrado" not in logabs.detail
    definite = sym.explain_integral("3*x^2", "x", "0", "2")
    simpson = [c.check for c in definite.checks() if "Simpson" in c.check.what][0]
    assert verification_kind(simpson) == "NUMERIC"
    deriv = sym.explain_derivative("sin(x)")
    kinds = {c.check.what: verification_kind(c.check) for c in deriv.checks()}
    assert kinds["la simplificación conserva la derivada"] in ("SYMBOLIC", "NUMERIC")
    assert kinds["diferencia central en puntos fijos (h = 1e-6)"] == "NUMERIC"
    param = sym.explain_derivative("a*x^2")
    na = [c.check for c in param.checks() if c.check.status is CheckStatus.NOT_APPLICABLE][0]
    assert verification_kind(na) == "NONE"
    for c in sym.explain_linear_equation("3*x + 2 = x - 4").checks():
        assert verification_kind(c.check) == "SYMBOLIC"  # exact rational substitution
    for t in (sym.explain_integral("1/x"), sym.explain_derivative("sin(x)")):
        for c in t.checks():
            if verification_kind(c.check) == "NUMERIC":
                assert c.check.tolerance is not None  # evidence with a tolerance, never a proof


def test_r_l2_03_renderer_shows_the_kind():
    view = build_view(sym.explain_integral("1/x"))
    assert view.checks[0].kind == "NUMERIC"
    lesson = [x for x in view.lessons if x.kind == "Verificación"][0]
    assert "no es una demostración" in lesson.verification
    e0 = build_view(eqn.explain_equation({"V": "5 V", "R": "1 kohm"}, "I = V / R", "current"))
    assert all(c.kind == "" for c in e0.checks)  # E0 checks are unlabelled, unchanged


# =============================================================== L3 GUM: declarative path, callable UNSUPPORTED

def test_r_l3_01_declared_constant_sensitivities_are_data():
    t = unc.explain_gum("Y", "Y = A*B", {"A": "value=3; u=0.1", "B": "value=2; u=0.2"}, sensitivities={"A": "2"})
    assert t.outcome is Outcome.SUCCESS and dict(t.inputs)["c.A"].text == "2"
    c_a = [e for e in t.events if e.title == "Coeficiente de sensibilidad c_A"][0]
    assert dict(c_a.values)["method"].text == "EXPLICIT" and c_a.result.number == 2
    assert compare(t, unc.replay_gum(t)).status == EQUIVALENT
    model = G.MeasurementModel("Y", "Y = A*B", sensitivities={"A": D(2)})
    inputs = {"A": G.InputQuantity("A", D(3), "", D("0.1")), "B": G.InputQuantity("B", D(2), "", D("0.2"))}
    via_model = unc.explain_gum_model(model, inputs)
    assert via_model.outcome is Outcome.SUCCESS
    assert via_model.result.text == G.evaluate_gum(model, inputs).summary()


def test_r_l3_02_declarative_formula_gives_symbolic_partials():
    t = unc.explain_gum("P", "P = V^2/R", {"V": "value=10; unit=V; u=0.05", "R": "value=50; unit=ohm; u=0.1"}, "W")
    partials = [c.check for c in t.checks() if c.check.what.startswith("c_")]
    assert {p.detail.split(" evaluada")[0] for p in partials} == {"∂f/∂V = 2*V/R", "∂f/∂R = -V^2/R^2"}
    assert all(verification_kind(p) == "NUMERIC" and p.status is CheckStatus.PASS for p in partials)


def test_r_l3_03_callables_compute_but_are_not_explained():
    model = G.MeasurementModel("Y", evaluator=lambda env: env["X"] * 2)
    inputs = {"X": G.InputQuantity("X", D(3), "", D("0.1"))}
    assert G.evaluate_gum(model, inputs).measurand_value == 6  # computing stays allowed
    with pytest.raises(UnsupportedError, match="callable evaluator"):
        unc.explain_gum_model(model, inputs)
    with pytest.raises(UnsupportedError, match="callable sensitivity"):
        unc.explain_gum_model(G.MeasurementModel("Y", "Y = 2*X", sensitivities={"X": lambda env: D(2)}), inputs)
    with pytest.raises(ValidationError):
        unc.explain_gum("Y", "Y = X", {"X": "value=1; u=0.1"}, sensitivities={"Z": "1"})
    bad = unc.explain_gum("Y", "Y = X", {"X": "value=1; u=0.1"}, sensitivities={"X": "abc"})
    assert bad.outcome is Outcome.FAILED


# =============================================================== L4 F8-Q delta cycles

def delta_capture(demo, channels, end="4"):
    req = AnalyzerRequest(demo, channels, "0", end)
    return dig.explain_capture(SVC.new_circuit(demo), SVC.build_config(req), context=(("demo", demo),),
                               pedagogical=True, delta=True)


def test_r_l4_01_glitches_are_explained_by_the_real_delta_event():
    t = delta_capture("xor3_glitch", ("a", "b", "c", "y"))
    assert t.verification.status is VerificationStatus.PASS
    consistent = [c for c in t.checks() if "ejecución observacional" in c.check.what][0]
    assert consistent.check.status is CheckStatus.PASS
    glitches = [e for e in t.events if e.kind is EventKind.STEP and "puerta" in e.title
                and dict(e.values)["transient"].text == "sí"]
    assert glitches and not any("no expone" in (e.why or "") for e in t.events)
    assert all(dict(e.values)["consistent"].text == "sí" for e in glitches)


@pytest.mark.parametrize("demo,channels", [("xor3_glitch", ("a", "b", "c", "y")), ("half_adder", ("sum", "carry")),
                                           ("repeated_inputs", ("xor_aab", "nor_aba")), ("wide_nand", ("y",))])
def test_r_l4_02_causes_match_an_independent_certified_run(demo, channels):
    t = delta_capture(demo, channels)
    sim = DigitalSimulator(SVC.new_circuit(demo))
    processed = sim.run_until(D(4))
    gates = {g.component_id: g for g in SVC.new_circuit(demo).components()}
    causes = [e for e in t.events if e.kind is EventKind.STEP and "puerta" in e.title]
    assert causes
    for e in causes:
        v = dict(e.values)
        me = processed[int(v["delta_index"].number) - 1]
        assert me.stable_id == v["driver"].text and me.sequence == int(v["sequence"].number)
        found = re.search(r"el evento #(\d+) \(", e.why)
        if found:  # not the start-up evaluation
            cause = processed[int(found.group(1)) - 1]
            assert cause.net_id in gates[me.stable_id].inputs and cause.time == me.time
            assert int(found.group(1)) < int(v["delta_index"].number)
        assert v["consistent"].text == "sí"


def test_r_l4_03_unprobed_internal_nets_are_observed():
    t = delta_capture("half_adder", ("sum",))
    assert not any("no observable" in e.title for e in t.events)
    assert any(e.kind is EventKind.STEP and "puerta xor_s" in e.title for e in t.events)


def test_r_l4_04_fallback_is_declared(monkeypatch):
    monkeypatch.setattr(dig, "MAX_DELTA_STEPS", 3)
    t = delta_capture("half_adder", ("a", "b", "sum", "carry"))
    assert any(dig.UNOBSERVABLE in e.title and e.kind is EventKind.WARNING for e in t.events)
    assert any("transitoria" in e.title for e in t.events)  # stable-instant causality, honestly


def test_r_l4_05_replay_transition_and_quiet_circuit():
    t = delta_capture("xor3_glitch", ("a", "b", "c", "y"))
    assert dict(t.inputs)["mode"].text == "pedagogical-delta"
    assert compare(t, dig.replay_capture(t, lambda ctx: SVC.new_circuit(ctx["demo"]))).status == EQUIVALENT
    x = transition_explanation(t, "y", 0)
    assert x.available and x.driver == "x3" and "evento #1" in x.why
    quiet = DigitalCircuit()
    quiet.add_net("A", LogicState.LOW)
    quiet.add_net("Y", LogicState.HIGH)
    quiet.add_component(DigitalComponent("n", GateKind.NOT, ("A",), "Y"))
    quiet.add_probe(DigitalProbe("y", "Y"))
    from academic_core.domain.engineering.digital import CaptureConfig
    q = dig.explain_capture(quiet, CaptureConfig(("y",), D(0), D(1)), pedagogical=True, delta=True)
    assert q.outcome is Outcome.SUCCESS
    with pytest.raises(ValidationError, match="pedagogical"):
        dig.explain_capture(SVC.new_circuit("half_adder"), CaptureConfig(("a",), D(0), D(1)), delta=True)


def test_r_l4_06_digital_package_still_untouched():
    out = subprocess.run(["git", "diff", "--name-only", "0cf3554", "--", "src/academic_core/domain/engineering/digital"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 or out.stdout.strip() == ""


# =============================================================== L5 F8-N input limits

def test_r_l5_01_limits_belong_to_the_transport_and_are_configurable():
    lines = DIODE.splitlines()
    assert nwt.explain_nonlinear_dc(DIODE, max_lines=len(lines)).outcome is Outcome.SUCCESS  # exactly at the limit
    assert nwt.explain_nonlinear_dc(DIODE, max_lines=len(lines) + 1).outcome is Outcome.SUCCESS  # below
    with pytest.raises(ValidationError, match="INVALID_INPUT"):
        nwt.explain_nonlinear_dc(DIODE, max_lines=len(lines) - 1)  # just above
    longest = max(len(x) for x in lines)
    assert nwt.explain_nonlinear_dc(DIODE, max_line_length=longest).outcome is Outcome.SUCCESS
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc(DIODE, max_line_length=longest - 1)
    assert nwt.explain_nonlinear_dc(DIODE, max_total_chars=len(DIODE)).outcome is Outcome.SUCCESS
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc(DIODE, max_total_chars=len(DIODE) - 1)


def test_r_l5_02_larger_circuits_within_ceilings():
    # a documented netlist: the line count is a transport matter, not a solver matter
    notes = "".join(f"* note {k}: documentation line kept verbatim in the trace\n" for k in range(230))
    spec = "* documented\n" + notes + DIODE.split("\n", 1)[1]
    assert len(spec.splitlines()) > nwt.MAX_LINES
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc(spec)  # default stays safe
    t = nwt.explain_nonlinear_dc(spec, max_lines=nwt.CEILING_LINES)
    assert t.outcome is Outcome.SUCCESS and len(t.inputs) == len(spec.splitlines())
    assert compare(t, nwt.replay_nonlinear_dc(t)).status == EQUIVALENT


def test_r_l5_03_ceilings_and_pathological_payloads():
    for bad in ({"max_lines": 0}, {"max_lines": nwt.CEILING_LINES + 1}, {"max_line_length": 513},
                {"max_total_chars": nwt.CEILING_TOTAL + 1}, {"max_lines": True}):
        with pytest.raises(ValidationError, match="INVALID_LIMIT"):
            nwt.explain_nonlinear_dc(DIODE, **bad)
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc("R1 a 0 1ohm\n" * 100_000, max_lines=nwt.CEILING_LINES)  # large payload
    with pytest.raises(ValidationError):
        nwt.explain_nonlinear_dc("R1 a 0 1ohm\x00\n")  # control characters never reach a trace
    t = nwt.explain_nonlinear_dc("x" * 512, max_line_length=512)
    assert t.outcome is Outcome.FAILED  # bounded, typed, reported


# =============================================================== L6 GUM float √ / ν_eff (KEEP_CERTIFIED_BEHAVIOR)

@pytest.mark.parametrize("equation,spec", [
    ("R = V / I", {"V": ("5", "0.01", "inf"), "I": ("0.002", "0.00001", "9")}),
    ("Y = A^2 / B", {"A": ("10", "0.05", "4"), "B": ("50", "0.1", "12")}),
    ("S = A + B", {"A": ("1", "0.1", "3"), "B": ("2", "0.2", "5")}),
    ("P = A * B", {"A": ("3", "0.1", "inf"), "B": ("2", "0.2", "inf")}),
])
def test_r_l6_01_decimal_path_measured_engine_kept(equation, spec):
    model = G.MeasurementModel(equation.split("=")[0].strip(), equation)
    inputs = {n: G.InputQuantity(n, D(v), "", D(u), degrees_of_freedom=float(dof)) for n, (v, u, dof) in spec.items()}
    result = G.evaluate_gum(model, inputs)
    # the certified engine is unchanged: u_c is still the float square root
    assert result.combined_standard_uncertainty == D(str(math.sqrt(float(result.budget.combined_variance))))
    uc, uc_diff, nu, nu_diff = unc.decimal_audit(result)
    assert uc_diff <= unc.DECIMAL_SQRT_TOL
    if nu is not None:
        assert nu_diff <= unc.DECIMAL_NU_TOL
    trace = unc.explain_gum(model.measurand, equation, {n: f"value={v}; u={u}; dof={dof}" for n, (v, u, dof) in spec.items()})
    audits = [c.check for c in trace.checks() if "Decimal" in c.check.what]
    assert len(audits) == 2 and all(c.status is CheckStatus.PASS for c in audits)


# =============================================================== L7 trace entry points

def test_r_l7_01_objects_are_traced_through_their_exact_data():
    circuit = nwt.parse_circuit_spec(DIODE)
    assert nwt.explain_nonlinear_circuit(circuit).digest() == nwt.explain_nonlinear_dc(nwt.circuit_spec(circuit)).digest()
    opaque = Circuit("opaque")
    opaque.add(Component("D1", "D", None, {"A": "a", "K": "0"}, {"kind": object()}))
    with pytest.raises(ValidationError, match="UNSUPPORTED_PARAMETER"):
        nwt.explain_nonlinear_circuit(opaque)
    loop = make_tf((D(2),), (D(1), D(3), D(2), D(0)))
    assert ctl.explain_margins_tf(loop).digest() == ctl.explain_margins("2", "1, 3, 2, 0").digest()
    with pytest.raises(ValidationError):
        ctl.explain_margins_tf("1/(s+1)")


# =============================================================== equations / units / pedagogy

@pytest.mark.parametrize("equation,result", [
    ("(x+1)/3 = x/2 - 1", "x = 8"),
    ("2*(x - 3) = 4*(x + 1)", "x = -5"),
    ("x/4 + 1/2 = 1", "x = 2"),
])
def test_r_eq_01_fractions_and_parentheses(equation, result):
    t = sym.explain_linear_equation(equation)
    assert t.result.text == result and t.verification.status is VerificationStatus.PASS
    assert rules(t)[0] == "plantear la ecuación" and rules(t)[-1].startswith("despejar")


def test_r_un_01_only_executed_conversions_and_dimensional_check():
    t = eqn.explain_equation({"R1": "1 kohm", "R2": "500 ohm"}, "R = R1 + R2", "resistance", pedagogical=True)
    conv = [e for e in t.events if e.title.startswith("Conversión")]
    assert [e.title for e in conv] == ["Conversión de unidades: R2"]
    assert conv[0].result.number == D("0.5") and conv[0].result.unit == "kΩ"
    dim = [c.check for c in t.checks() if "dimensión" in c.check.what][0]
    assert dim.status is CheckStatus.PASS
    plain = eqn.explain_equation({"V": "5 V", "R": "1000 ohm"}, "I = V / R", "current", pedagogical=True)
    assert not any(e.title.startswith("Conversión") for e in plain.events)  # nothing converted, nothing shown


def test_r_nw_01_iteration_shows_x_f_j_dx():
    t = nwt.explain_nonlinear_dc(DIODE)
    first = [e for e in t.events if e.title == "Iteración 1 de Newton"][0]
    names = {n for n, _ in first.values}
    for needed in ("alpha", "step_peak", "kcl_residual", "res_ok", "step_ok", "x_k.a", "F_k.a", "dx.a", "J.a.a"):
        assert needed in names
    continuity = [c.check for c in t.checks() if "x_(k+1)" in c.check.what]
    assert continuity[0].status is CheckStatus.PASS


def test_r_nw_02_large_systems_say_detail_is_omitted():
    spec = """* two
V1 in 0 3V
R1 in a 220ohm
R2 a b 100ohm
D1 b c D
D2 c 0 D
.param D1 Is=1e-14A n=1 Vt=0.02585V
.param D2 Is=2e-14A n=1.5 Vt=0.02585V
.end
"""
    t = nwt.explain_nonlinear_dc(spec)
    it = [e for e in t.events if e.title.startswith("Iteración")][0]
    assert "detalle omitido" in dict(it.values)["jacobian"].text


def test_r_bi_01_bisection_shows_interval_values_and_stop():
    t = ctl.explain_margins("2", "1, 3, 2, 0")
    gain = [e for e in t.events if e.title.startswith("Bisección") and "ganancia" in e.title]
    for e in gain:
        v = dict(e.values)
        assert v["f_lo"].number is not None and v["f_hi"].number is not None
        same = (v["f_lo"].number > 0) == (v["f_mid"].number > 0)
        assert (v["new_lo"].number == v["omega_mid"].number) == same
    phase = [e for e in t.events if e.title.startswith("Bisección") and "fase" in e.title]
    assert all(dict(e.values)["f_hi"].text == "no calculado por el motor" for e in phase)
    stops = [e for e in t.events if e.kind is EventKind.DECISION]
    assert stops and all("BISECT_REL_TOL" in dict(e.values)["reason"].text for e in stops)


# =============================================================== digital-circuit/1

def test_r_dc_01_round_trip_digest_and_simulation():
    for info in SVC.demos():
        circuit = SVC.new_circuit(info.key)
        text = DC.circuit_to_json(circuit)
        twin = DC.circuit_from_json(text)
        assert DC.circuit_digest(twin) == DC.circuit_digest(circuit) and DC.circuit_to_json(twin) == text
        a = DigitalSimulator(SVC.new_circuit(info.key)).run_until(D(4))
        b = DigitalSimulator(DC.circuit_from_json(text)).run_until(D(4))
        assert a == b  # identical processed events: same simulation
    doc = json.loads(DC.circuit_to_json(SVC.new_circuit("half_adder")))
    doc["gates"][0]["inputs"] = ["A", "NOPE"]
    with pytest.raises(ValueError):
        DC.circuit_from_json(json.dumps(doc, sort_keys=True))
    source = (ROOT + "/src/academic_core/domain/engineering/digital_circuit.py")
    text = open(source, encoding="utf-8").read()
    assert ".evaluate(" not in text and "TRUTH_TABLES" not in text  # no gate logic in the serializer
