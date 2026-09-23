# SPDX-License-Identifier: MIT
"""E0.1 integration with the certified GUM engine (``engineering.gum.evaluate_gum``).

``explain_gum`` runs ``evaluate_gum`` once, with its optional sensitivity
observer, and records what the engine really did:

- **INPUT**: the measurand, the model equation, the coverage settings and
  each input quantity as a text specification
  (``value=…; unit=…; u=…; type=…; distribution=…; dof=…``). These are the
  replay inputs.
- **NORMALIZATION**: each ``InputQuantity`` as the engine built it (x_i,
  unit, u(x_i), type, distribution, ν_i).
- **STEP "Valor del mensurando"**: the model, the substitution of the
  nominal values, and y as the engine computed it.
- **STEP "Coeficiente de sensibilidad"**, one per input: the method the
  engine used (EXPLICIT / ANALYTIC / NUMERICAL), with the facts the
  observer reported. For an analytic formula, the pattern and the values
  it used. For a central difference, h, x ± h and f(x ± h), which are the
  engine's real evaluations.
- **STEP "Contribución"**, one per input: c_i·u(x_i), (c_i·u(x_i))² and
  the percentage.
- **STEP**: covariance terms, combined variance, u_c,
  Welch–Satterthwaite ν_eff, coverage factor k (with its source) and
  U = k·u_c.
- **WARNING**: the certified engine computes √ and ν_eff in binary
  floating point. The trace says so rather than presenting those values
  as exact.
- **RESULT**: the engine's own summary line.
- **CHECK**:
  - Σ(c_i·u_i)² + covariance = u_c² (exact)
  - u_c² ≈ combined variance (relative 1e-12, because √ is float)
  - U = k·u_c (exact)
  - Σ % ≈ 100·Σ(c_i·u_i)²/u_c² (rounding of the table)
  - per input, when the model parses in the symbolic grammar and needs no
    unit scaling, c_i against the symbolic partial derivative ∂f/∂x_i
    evaluated at the nominal values. The tolerance is 1e-6 relative for
    NUMERICAL (central difference) and 1e-20 otherwise.

Only DECLARATIVE models are traceable: an equation (text), optionally
with constant sensitivities (inputs ``c.<name>``, E0.1-R+). A callable
evaluator or sensitivity is code, not data, so its explanation is refused
(``UNSUPPORTED``). Computing it with ``evaluate_gum`` stays allowed.

E0.1-R+ L6: two extra CHECKs recompute √(u_c²) and Welch–Satterthwaite
in Decimal (50 digits) from the certified budget and measure the
difference from the certified float values. The certified values are
kept (KEEP_CERTIFIED_BEHAVIOR).
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation, localcontext

from academic_core.domain.engineering import gum as G
from academic_core.domain.engineering.symbolic.derive import derivative
from academic_core.domain.engineering.symbolic.expr import parse, text
from academic_core.domain.engineering.symbolic.numeric import symbols, value
from academic_core.domain.engineering.symbolic.steps import StepLog
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.domain.execution.verification import NONE, NUMERIC, SYMBOLIC, labelled
from academic_core.errors import UnsupportedError

OPERATION = "engineering.gum"
_KEYS = ("value", "unit", "u", "type", "distribution", "dof")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}\Z")
_RESERVED = {"measurand", "equation", "output_unit", "coverage_probability", "explicit_k", "correlations"}
VARIANCE_TOL = Decimal("1e-12")
SENS_TOL_NUMERICAL = Decimal("1e-6")
SENS_TOL_EXACT = Decimal("1e-20")
SENS_PREFIX = "c."  # declared (constant) sensitivities, E0.1-R+ L3
DECIMAL_SQRT_TOL = Decimal("1e-15")  # float √: correctly rounded binary64, printed with repr (17 digits)
DECIMAL_NU_TOL = Decimal("1e-12")  # float accumulation in Welch–Satterthwaite


def quantity_spec(q: G.InputQuantity) -> str:
    dof = "inf" if math.isinf(q.degrees_of_freedom) else repr(q.degrees_of_freedom)
    return (f"value={q.nominal_value}; unit={q.unit}; u={q.standard_uncertainty}; type={q.uncertainty_type}; "
            f"distribution={q.distribution}; dof={dof}")


def parse_spec(name: str, spec: str) -> G.InputQuantity:
    fields: dict[str, str] = {}
    for part in spec.split(";"):
        if not part.strip():
            continue
        key, sep, val = part.partition("=")
        key = key.strip()
        if not sep or key not in _KEYS or key in fields:
            raise _invalid("INVALID_INPUT", f"{name}: bad field {key[:16]!r} (allowed: {', '.join(_KEYS)})")
        fields[key] = val.strip()
    if "value" not in fields or "u" not in fields:
        raise _invalid("INVALID_INPUT", f"{name}: value and u are required")
    try:
        nominal, u = Decimal(fields["value"]), Decimal(fields["u"])
    except InvalidOperation:
        raise _invalid("INVALID_INPUT", f"{name}: value and u must be decimal numbers") from None
    if not nominal.is_finite() or not u.is_finite():
        raise _invalid("INVALID_INPUT", f"{name}: value and u must be finite")
    dof_text = fields.get("dof", "inf")
    if not re.fullmatch(r"inf|[0-9]+(\.[0-9]+)?", dof_text):
        raise _invalid("INVALID_INPUT", f"{name}: dof must be a positive number or inf")
    return G.InputQuantity(name=name, nominal_value=nominal, unit=fields.get("unit", ""), standard_uncertainty=u,
                           uncertainty_type=fields.get("type", "B"), distribution=fields.get("distribution", "explicit"),
                           degrees_of_freedom=float(dof_text))


def _correlations(text: str) -> G.CorrelationMatrix | None:
    if not text.strip():
        return None
    pairs = []
    for part in text.split(";"):
        if not part.strip():
            continue
        names, sep, r = part.partition("=")
        a, comma, b = names.partition(",")
        if not sep or not comma:
            raise _invalid("INVALID_INPUT", "correlations are written A,B=r; C,D=r")
        pairs.append((a.strip(), b.strip(), r.strip()))
    return G.CorrelationMatrix.from_pairs(pairs)


def _n(v) -> TraceValue:
    return TraceValue.of_number(Decimal(v)) if isinstance(v, (Decimal, int)) else TraceValue.of_text(str(v))


def _rel(a: Decimal, b: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return abs(a - b) / max(abs(b), Decimal("1e-300"))


class _Observer:
    def __init__(self):
        self.facts: dict[str, tuple[str, str, tuple]] = {}

    def sensitivity(self, name, method, rule, details):
        self.facts[name] = (method, rule, tuple(details))


def _substituted(rhs: str, nominal: dict[str, Decimal]) -> str:
    return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", lambda m: str(nominal[m.group(0)]) if m.group(0) in nominal else m.group(0),
                  rhs)


def explain_gum(measurand: str, equation: str, quantities: dict[str, str], output_unit: str = "",
                coverage_probability: str = "0.95", explicit_k: str | None = None,
                correlations: str = "", sensitivities: dict[str, str] | None = None) -> ExecutionTrace:
    if not isinstance(quantities, dict) or not quantities or not all(
            isinstance(k, str) and _NAME_RE.fullmatch(k) and k not in _RESERVED and isinstance(v, str)
            for k, v in quantities.items()):
        raise _invalid("INVALID_INPUT", "quantities must be a non-empty {name: specification} mapping")
    for label, v in (("measurand", measurand), ("equation", equation), ("output_unit", output_unit),
                     ("coverage_probability", coverage_probability), ("correlations", correlations)):
        if not isinstance(v, str):
            raise _invalid("INVALID_INPUT", f"{label} must be text")
    rec = TraceRecorder(OPERATION)
    rec.input("measurand", TraceValue.of_text(measurand), "Mensurando")
    eq_id = rec.input("equation", TraceValue.of_text(equation), "Modelo de medida")
    rec.input("output_unit", TraceValue.of_text(output_unit), "Unidad del resultado")
    rec.input("coverage_probability", TraceValue.of_text(coverage_probability), "Probabilidad de cobertura")
    if explicit_k is not None:
        rec.input("explicit_k", TraceValue.of_text(explicit_k), "Factor de cobertura explícito")
    rec.input("correlations", TraceValue.of_text(correlations), "Correlaciones")
    raw = {n: rec.input(n, TraceValue.of_text(quantities[n]), f"Magnitud de entrada {n}") for n in sorted(quantities)}
    declared = dict(sensitivities or {})
    if not all(isinstance(k, str) and k in quantities and isinstance(v, str) for k, v in declared.items()):
        raise _invalid("INVALID_INPUT", "sensitivities must map input quantity names to decimal text")
    for n in sorted(declared):
        rec.input(f"{SENS_PREFIX}{n}", TraceValue.of_text(declared[n]), f"Coeficiente de sensibilidad declarado c_{n}")
    try:
        try:
            explicit = {n: Decimal(declared[n]) for n in declared}
        except InvalidOperation:
            raise _invalid("INVALID_INPUT", "declared sensitivities must be decimal numbers") from None
        if not all(v.is_finite() for v in explicit.values()):
            raise _invalid("INVALID_INPUT", "declared sensitivities must be finite")
        inputs = {}
        norm = {}
        for n in sorted(quantities):
            q = parse_spec(n, quantities[n])
            inputs[n] = q
            dof = "∞" if math.isinf(q.degrees_of_freedom) else repr(q.degrees_of_freedom)
            norm[n] = rec.event(
                EventKind.NORMALIZATION, f"Magnitud {n}", refs=(raw[n],), formula=f"{n} = {q.nominal_value} {q.unit}".strip(),
                why="InputQuantity del motor GUM: valor nominal, incertidumbre típica, tipo, distribución y grados de libertad.",
                values=(("x", _n(q.nominal_value)), ("unit", TraceValue.of_text(q.unit or "1")),
                        ("u", _n(q.standard_uncertainty)), ("type", TraceValue.of_text(q.uncertainty_type)),
                        ("distribution", TraceValue.of_text(q.distribution)), ("dof", TraceValue.of_text(dof))))
        model = G.MeasurementModel(measurand=measurand, equation=equation, output_unit=output_unit,
                                   sensitivities=explicit or None)
        p = float(Decimal(coverage_probability))
        k_arg = Decimal(explicit_k) if explicit_k is not None else None
        obs = _Observer()
        result = G.evaluate_gum(model, inputs, correlation=_correlations(correlations), coverage_probability=p,
                                explicit_k=k_arg, observer=obs)
        budget = result.budget
        rhs = equation.partition("=")[2].strip() if "=" in equation else equation.strip()
        nominal = {n: q.nominal_value for n, q in inputs.items()}
        unit = result.measurand_unit
        y_id = rec.event(
            EventKind.STEP, "Valor del mensurando", refs=(eq_id, *norm.values()),
            formula=f"{measurand} = {rhs}",
            why="El motor evalúa el modelo con los valores nominales (evaluador certificado, con unidades).",
            values=(("substitution", TraceValue.of_text(f"{measurand} = {_substituted(rhs, nominal)}"[:512])),),
            result=TraceValue.of_number(result.measurand_value, unit))
        contrib_ids = []
        sens_ids = {}
        for row in budget.rows:
            method, rule, details = obs.facts.get(row.quantity, (row.sensitivity_method, "", ()))
            vals = [("method", TraceValue.of_text(method))]
            if rule:
                vals.append(("rule", TraceValue.of_text(rule)))
            vals.extend((name, _n(v)) for name, v in details)
            why = {"NUMERICAL": "Derivada parcial numérica por diferencia central: el motor evalúa f(x+h) y f(x-h).",
                   "ANALYTIC": "Derivada parcial analítica: el motor reconoce un patrón registrado del modelo.",
                   "EXPLICIT": "Coeficiente suministrado explícitamente con el modelo."}.get(method, method)
            sens_ids[row.quantity] = rec.event(
                EventKind.STEP, f"Coeficiente de sensibilidad c_{row.quantity}", refs=(y_id, norm[row.quantity]),
                formula=f"c_{row.quantity} = ∂{measurand}/∂{row.quantity}", why=why, values=tuple(vals)[:64],
                result=TraceValue.of_number(row.sensitivity_coefficient))
            contrib_ids.append(rec.event(
                EventKind.STEP, f"Contribución de {row.quantity}", refs=(sens_ids[row.quantity], norm[row.quantity]),
                formula=f"u_{row.quantity}(y) = c_{row.quantity}·u({row.quantity})",
                why="Cada entrada aporta c_i·u(x_i) a la incertidumbre del mensurando.",
                values=(("c", _n(row.sensitivity_coefficient)), ("u", _n(row.standard_uncertainty)),
                        ("contribution", _n(row.contribution)), ("variance", _n(row.variance_contribution)),
                        ("percent", _n(row.relative_contribution_pct))),
                result=TraceValue.of_number(row.contribution, unit)))
        cov_refs = tuple(contrib_ids)
        if budget.covariance_term != 0:
            cov_id = rec.event(EventKind.STEP, "Términos de covarianza", refs=cov_refs,
                               formula="2·Σ_{i<j} c_i·c_j·u(x_i)·u(x_j)·r(x_i, x_j)",
                               why="Las entradas correlacionadas añaden términos cruzados a la varianza.",
                               values=(("correlations", TraceValue.of_text(correlations)),),
                               result=TraceValue.of_number(budget.covariance_term))
            cov_refs = cov_refs + (cov_id,)
        var_id = rec.event(EventKind.STEP, "Varianza combinada", refs=cov_refs,
                           formula="u_c²(y) = Σ(c_i·u(x_i))² + covarianzas",
                           why="Ley de propagación de incertidumbres (GUM, ec. 13).",
                           result=TraceValue.of_number(budget.combined_variance))
        uc_id = rec.event(EventKind.STEP, "Incertidumbre típica combinada", refs=(var_id,), formula="u_c = √(u_c²)",
                          result=TraceValue.of_number(result.combined_standard_uncertainty, unit))
        nu = result.effective_degrees_of_freedom
        nu_id = rec.event(EventKind.STEP, "Grados de libertad efectivos (Welch–Satterthwaite)",
                          refs=(uc_id, *contrib_ids), formula="ν_eff = u_c⁴ / Σ(u_i(y)⁴/ν_i)",
                          result=TraceValue.of_text("∞" if math.isinf(nu) else repr(nu)))
        source = result.provenance.get("coverage_factor_source", "")
        k_id = rec.event(EventKind.DECISION, "Factor de cobertura k", refs=(nu_id,),
                         formula=f"k(p = {coverage_probability}, ν_eff)",
                         why={"explicit_user": "k fijado explícitamente por el usuario.",
                              "student_t": "k = t de Student para p y ν_eff finitos.",
                              "normal_limit": "ν_eff = ∞: k es el cuantil de la normal."}.get(source, source or "-"),
                         values=(("source", TraceValue.of_text(source or "-")),),
                         result=TraceValue.of_number(result.coverage_factor))
        u_id = rec.event(EventKind.STEP, "Incertidumbre expandida", refs=(k_id, uc_id), formula="U = k·u_c",
                         result=TraceValue.of_number(result.expanded_uncertainty, unit))
        rec.event(EventKind.WARNING, "Precisión del motor GUM", refs=(uc_id, nu_id),
                  why="El motor GUM certificado calcula √(u_c²) y ν_eff en coma flotante binaria (math.sqrt / float); "
                      "esos dos valores no son exactos. El resto de la cadena es Decimal. Se conserva el comportamiento "
                      "certificado (KEEP_CERTIFIED_BEHAVIOR); la comprobación Decimal de abajo mide la diferencia.")
        res_id = rec.event(EventKind.RESULT, f"Resultado {measurand}", refs=(y_id, u_id), formula=result.summary()[:512],
                           result=TraceValue.of_text(result.summary()[:512]))
        _checks(rec, res_id, result, measurand, rhs, nominal, obs, sens_ids)
    except (ValueError, ArithmeticError, UnsupportedError) as exc:
        rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))
    return rec.finish()


def _checks(rec, res_id, result, measurand, rhs, nominal, obs, sens_ids) -> None:
    b = result.budget
    total = sum((r.variance_contribution for r in b.rows), Decimal(0)) + b.covariance_term
    rec.check("Σ(c_i·u_i)² + covarianza = u_c²", TraceValue.of_number(total), TraceValue.of_number(b.combined_variance),
              total == b.combined_variance, refs=(res_id,), title="Comprobación: suma de contribuciones")
    with localcontext() as ctx:
        ctx.prec = 50
        uc2 = result.combined_standard_uncertainty * result.combined_standard_uncertainty
    err = _rel(uc2, b.combined_variance) if b.combined_variance else abs(uc2)
    rec.check("u_c² ≈ varianza combinada (√ en coma flotante)", TraceValue.of_number(err), TraceValue.of_number(Decimal(0)),
              err <= VARIANCE_TOL, refs=(res_id,), tolerance=TraceValue.of_number(VARIANCE_TOL),
              title="Comprobación: raíz de la varianza")
    with localcontext() as ctx:
        ctx.prec = 50
        ku = result.coverage_factor * result.combined_standard_uncertainty
    rec.check("U = k·u_c", TraceValue.of_number(result.expanded_uncertainty), TraceValue.of_number(ku),
              result.expanded_uncertainty == ku, refs=(res_id,), title="Comprobación: incertidumbre expandida")
    if b.combined_variance > 0:
        pct = sum((r.relative_contribution_pct for r in b.rows), Decimal(0))
        with localcontext() as ctx:
            ctx.prec = 50
            expected = sum((r.variance_contribution for r in b.rows), Decimal(0)) / b.combined_variance * 100
        tol = Decimal("0.0001") * len(b.rows)
        rec.check("Σ contribuciones % = 100·Σ(c_i·u_i)²/u_c² (redondeo de la tabla)", TraceValue.of_number(pct),
                  TraceValue.of_number(expected.quantize(Decimal("1e-6"))), abs(pct - expected) <= tol, refs=(res_id,),
                  tolerance=TraceValue.of_number(tol), title="Comprobación: porcentajes del presupuesto")
    _check_decimal_path(rec, res_id, result)
    _check_partials(rec, res_id, result, rhs, nominal, obs, sens_ids)


def decimal_audit(result: G.GUMResult) -> tuple[Decimal, Decimal, Decimal | None, Decimal | None]:
    """(u_c Decimal, relative difference, ν_eff Decimal or None if ∞, relative difference or None).

    E0.1-R+ L6: the same formulas as the certified engine (√ of the combined
    variance, Welch–Satterthwaite over the budget contributions), in Decimal
    at 50 digits. It is an audit of the certified float values; it does not
    replace them."""
    b = result.budget
    with localcontext() as ctx:
        ctx.prec = 50
        uc = b.combined_variance.sqrt() if b.combined_variance > 0 else Decimal(0)
        certified = result.combined_standard_uncertainty
        uc_diff = abs(uc - certified) / uc if uc else abs(certified)
        denom = Decimal(0)
        finite = False
        for r in b.rows:
            if not math.isinf(r.degrees_of_freedom):
                finite = True
                if r.contribution != 0:
                    denom += r.contribution ** 4 / Decimal(repr(r.degrees_of_freedom))
        if not finite or denom == 0:
            return uc, uc_diff, None, None
        nu = uc ** 4 / denom
        engine_nu = result.effective_degrees_of_freedom
        nu_diff = abs(nu - Decimal(repr(engine_nu))) / nu if not math.isinf(engine_nu) else None
        return uc, uc_diff, nu, nu_diff


def _check_decimal_path(rec, res_id, result) -> None:
    uc, uc_diff, nu, nu_diff = decimal_audit(result)
    rec.check("u_c: √ Decimal (50 dígitos) frente a √ float certificada", TraceValue.of_number(uc_diff),
              TraceValue.of_number(Decimal(0)), uc_diff <= DECIMAL_SQRT_TOL, refs=(res_id,),
              tolerance=TraceValue.of_number(DECIMAL_SQRT_TOL),
              detail=labelled(f"u_c Decimal = {uc:.25g}; certificada = {result.combined_standard_uncertainty}", NUMERIC),
              title="Comprobación: ruta Decimal de u_c")
    if nu is None:
        rec.check("ν_eff Decimal frente a ν_eff certificada", TraceValue.of_text("∞"),
                  TraceValue.of_text("∞" if math.isinf(result.effective_degrees_of_freedom) else "finito"),
                  math.isinf(result.effective_degrees_of_freedom), refs=(res_id,),
                  detail=labelled("todas las entradas con ν = ∞ (o contribuciones nulas)", SYMBOLIC),
                  title="Comprobación: ruta Decimal de ν_eff")
        return
    ok = nu_diff is not None and nu_diff <= DECIMAL_NU_TOL
    rec.check("ν_eff Decimal frente a ν_eff certificada (float)",
              TraceValue.of_number(nu_diff) if nu_diff is not None else TraceValue.of_text("∞ en el motor"),
              TraceValue.of_number(Decimal(0)), ok, refs=(res_id,), tolerance=TraceValue.of_number(DECIMAL_NU_TOL),
              detail=labelled(f"ν_eff Decimal = {nu:.20g}; certificada = {result.effective_degrees_of_freedom!r}", NUMERIC),
              title="Comprobación: ruta Decimal de ν_eff")


def _check_partials(rec, res_id, result, rhs, nominal, obs, sens_ids) -> None:
    reason = ""
    try:
        f = parse(rhs)
    except ValueError:
        f, reason = None, "el modelo no se puede leer con la gramática simbólica"
    if f is not None and not symbols(f) <= set(nominal):
        f, reason = None, "el modelo usa nombres que no son magnitudes de entrada (p. ej. unidades)"
    if f is not None:
        y = value(f, dict(nominal))
        if y is None or _rel(y, result.measurand_value) > SENS_TOL_EXACT:
            f, reason = None, "el motor aplica escalado de unidades: la derivada simbólica no es comparable"
    for row in result.budget.rows:
        ref = sens_ids[row.quantity]
        title = f"Comprobación: c_{row.quantity} frente a ∂f/∂{row.quantity} simbólica"
        if f is None:
            rec.check(f"c_{row.quantity} = ∂f/∂{row.quantity}", TraceValue.of_number(row.sensitivity_coefficient),
                      TraceValue.of_text("-"), None, refs=(ref,), detail=labelled(f"no aplicable: {reason}", NONE),
                      title=title)
            continue
        _raw, d, _s = derivative(f, row.quantity, StepLog())
        expected = value(d, dict(nominal))
        tol = SENS_TOL_NUMERICAL if row.sensitivity_method == "NUMERICAL" else SENS_TOL_EXACT
        if expected is None:
            rec.check(f"c_{row.quantity} = ∂f/∂{row.quantity}", TraceValue.of_number(row.sensitivity_coefficient),
                      TraceValue.of_text("-"), None, refs=(ref,), detail=labelled("no aplicable: ∂f no evaluable", NONE),
                      title=title)
            continue
        err = _rel(row.sensitivity_coefficient, expected) if expected else abs(row.sensitivity_coefficient)
        rec.check(f"c_{row.quantity} = ∂f/∂{row.quantity}", TraceValue.of_number(row.sensitivity_coefficient),
                  TraceValue.of_number(expected), err <= tol, refs=(ref,), tolerance=TraceValue.of_number(tol),
                  detail=labelled(f"∂f/∂{row.quantity} = {text(d)} evaluada en los valores nominales", NUMERIC),
                  title=title)


def explain_gum_model(model: G.MeasurementModel, inputs: dict[str, G.InputQuantity],
                      coverage_probability: float = 0.95, explicit_k=None) -> ExecutionTrace:
    """Trace a DECLARATIVE ``MeasurementModel``: an equation (text, parsed by the certified evaluator)
    plus, optionally, constant sensitivities. A callable evaluator or a callable sensitivity is code,
    not data: it can still be computed with ``evaluate_gum``, but its explanation is ``UNSUPPORTED``."""
    if model.equation is None or model.evaluator is not None:
        raise UnsupportedError("UNSUPPORTED: a callable evaluator cannot be traced as data; use an equation model")
    declared = dict(model.sensitivities or {})
    if any(callable(v) for v in declared.values()):
        raise UnsupportedError("UNSUPPORTED: a callable sensitivity cannot be traced as data; declare a constant")
    return explain_gum(model.measurand, model.equation, {n: quantity_spec(q) for n, q in inputs.items()},
                       model.output_unit, repr(coverage_probability), None if explicit_k is None else str(explicit_k),
                       sensitivities={n: str(Decimal(str(v))) for n, v in declared.items()})


def replay_gum(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    rec = {k: v.text for k, v in trace.inputs}
    fixed = {n: rec.pop(n) for n in list(rec) if n in _RESERVED}
    declared = {n[len(SENS_PREFIX):]: rec.pop(n) for n in list(rec) if n.startswith(SENS_PREFIX)}
    return explain_gum(fixed.get("measurand", ""), fixed.get("equation", ""), rec, fixed.get("output_unit", ""),
                       fixed.get("coverage_probability", "0.95"), fixed.get("explicit_k"), fixed.get("correlations", ""),
                       sensitivities=declared or None)
