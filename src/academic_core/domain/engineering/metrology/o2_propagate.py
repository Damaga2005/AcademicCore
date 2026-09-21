"""F8-O O2/O3/O5/O7/O8/O11 propagation (WRAP ``gum.evaluate_gum``).

Implements the law of propagation of uncertainty::

    u_c^2 = sum_i c_i^2 u_i^2 + 2 sum_{i<j} c_i c_j cov(X_i, X_j)

with ``cov_ij = r_ij u_i u_j``, Welch-Satterthwaite effective degrees of
freedom, Student-t coverage and ``U = k u_c`` — all computed by the
certified F7-B7 engine. This module contributes no new statistics: only
deterministic ingress validation, typed error mapping and thin builders.

Sensitivity order (delegated to ``MeasurementModel.get_sensitivity``):
EXPLICIT (user-supplied) > ANALYTIC (closed patterns: sum, difference,
product, quotient, voltage divider) > NUMERICAL (central finite difference
with ``h = max(|x| * 1e-6, 1e-9)``, bilateral, full Decimal precision).
ADAPT: if the ANALYTIC closed form raises ``ArithmeticError`` at a singular
point, the same gate step rule is applied through the certified
``model.evaluate`` (tagged NUMERICAL, never silent).

Reuse: WRAP ``gum.MeasurementModel`` / ``gum.CorrelationMatrix`` /
``gum.evaluate_gum`` / ``gum.calculate_coverage_factor``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Mapping, Sequence

from academic_core.domain.engineering.gum import (
    CorrelationMatrix,
    GUMResult,
    InputQuantity,
    MeasurementModel,
    calculate_coverage_factor,
    evaluate_gum,
)

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)
from academic_core.domain.engineering.metrology.o1_inputs import MAX_METROLOGY_INPUTS

DEFAULT_COVERAGE_PROBABILITY = 0.95
MC_AGREEMENT_TOLERANCE = Decimal("0.05")


def build_model(
    measurand: str,
    equation: str | None = None,
    evaluator: Callable[[dict], object] | None = None,
    input_names: tuple[str, ...] = (),
    sensitivities: dict[str, Decimal | Callable[[dict[str, Decimal]], Decimal]] | None = None,
    output_unit: str = "",
    input_units: dict[str, str] | None = None,
) -> MeasurementModel:
    """Build a measurement model ``Y = f(X)`` (WRAP ``gum.MeasurementModel``).

    Exactly one of ``equation`` / ``evaluator`` is required (INVALID
    otherwise). Dimensional evaluators must follow the ``Quantity ->
    Quantity`` contract enforced by the wrapped model.
    """
    cleaned = measurand.strip() if isinstance(measurand, str) else ""
    if not cleaned:
        raise MetrologyError(MetrologyStatus.INVALID, "measurand name cannot be empty")
    if (equation is None) == (evaluator is None):
        raise MetrologyError(
            MetrologyStatus.INVALID, "model requires exactly one of equation / evaluator"
        )
    try:
        return MeasurementModel(
            measurand=cleaned,
            equation=equation,
            input_names=tuple(input_names),
            evaluator=evaluator,  # type: ignore[arg-type]
            sensitivities=sensitivities,
            output_unit=output_unit,
            input_units=dict(input_units) if input_units else {},
        )
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc


def build_correlation(pairs: Sequence[tuple[str, str, Decimal | int | str]]) -> CorrelationMatrix:
    """Build a correlation matrix from ``(var1, var2, r)`` pairs (WRAP gum).

    ``r`` outside ``[-1, 1]``, asymmetric or non-unit-diagonal entries raise
    ``MetrologyError(INVALID)`` at construction; a non-PSD matrix raises
    ``MetrologyError(SINGULAR)`` — whether the wrapped engine rejects it at
    construction or at ``evaluate_budget`` validation time.
    """
    cleaned: dict[tuple[str, str], Decimal] = {}
    for raw_v1, raw_v2, raw_r in pairs:
        v1 = raw_v1.strip() if isinstance(raw_v1, str) else ""
        v2 = raw_v2.strip() if isinstance(raw_v2, str) else ""
        if not v1 or not v2:
            raise MetrologyError(MetrologyStatus.INVALID, "correlation variable names need values")
        try:
            r = Decimal(str(raw_r)) if not isinstance(raw_r, Decimal) else raw_r
        except Exception as exc:
            raise MetrologyError(MetrologyStatus.INVALID, f"bad correlation value {raw_r!r}") from exc
        cleaned[(v1, v2)] = r
    try:
        return CorrelationMatrix(cleaned)
    except ValueError as exc:
        message = str(exc)
        if "positive semi-definite" in message.lower():
            raise MetrologyError(MetrologyStatus.SINGULAR, message) from exc
        raise MetrologyError(MetrologyStatus.INVALID, message) from exc


def _fd_fallback(
    model: MeasurementModel,
    var_name: str,
    nominals: Mapping[str, Decimal],
    input_units: dict[str, str] | None = None,
) -> tuple[Decimal, str]:
    """Central finite difference via the certified ``model.evaluate`` (ADAPT).

    Used ONLY when the ANALYTIC path raises ``ArithmeticError`` (e.g. a
    quotient pole at ``x_j = 0``). Step rule exactly per gate (bilateral,
    ``h = max(|x| * 1e-6, 1e-9)``, full Decimal precision, no rounding).
    The result is tagged ``NUMERICAL`` so a pole FD can never pass as an
    analytic derivative; evaluation failure maps to ``NUMERIC_ERROR``.
    """
    x_val = nominals[var_name]
    step = abs(x_val) * Decimal("1e-6")
    if step < Decimal("1e-9"):
        step = Decimal("1e-9")
    try:
        up_inputs = dict(nominals)
        up_inputs[var_name] = x_val + step
        y_plus = model.evaluate(up_inputs, input_units=input_units)
        down_inputs = dict(nominals)
        down_inputs[var_name] = x_val - step
        y_minus = model.evaluate(down_inputs, input_units=input_units)
    except (ValueError, ArithmeticError) as exc:
        raise MetrologyError(MetrologyStatus.NUMERIC_ERROR, str(exc)) from exc
    return (y_plus - y_minus) / (Decimal(2) * step), "NUMERICAL"


def sensitivity_of(
    model: MeasurementModel,
    var_name: str,
    nominals: Mapping[str, Decimal],
    input_units: dict[str, str] | None = None,
) -> tuple[Decimal, str]:
    """Sensitivity ``c_i = df/dX_i`` with method tag (WRAP ``model.get_sensitivity``).

    Order EXPLICIT > ANALYTIC > NUMERICAL (delegated). If the ANALYTIC
    closed form raises ``ArithmeticError`` (singular point, e.g. quotient
    with zero divisor), the gate-mandated bilateral FD fallback applies
    (tagged ``NUMERICAL``). Genuinely inevaluable perturbations surface as
    ``MetrologyError(NUMERIC_ERROR)`` rather than a silent plausible value.
    """
    if not isinstance(model, MeasurementModel):
        raise MetrologyError(MetrologyStatus.INVALID, "sensitivity_of needs a MeasurementModel")
    if var_name not in nominals:
        raise MetrologyError(MetrologyStatus.INVALID, f"unknown variable {var_name!r}")
    try:
        return model.get_sensitivity(var_name, dict(nominals), input_units=input_units)
    except ArithmeticError:
        return _fd_fallback(model, var_name, nominals, input_units=input_units)
    except (ValueError, KeyError) as exc:
        raise MetrologyError(MetrologyStatus.NUMERIC_ERROR, str(exc)) from exc


def _check_coverage_probability(p: float) -> float:
    if isinstance(p, bool) or not isinstance(p, (float, int)):
        raise MetrologyError(MetrologyStatus.INVALID, "coverage probability must be a number")
    pf = float(p)
    if not (0.0 < pf < 1.0):
        raise MetrologyError(MetrologyStatus.INVALID, "coverage probability must lie in (0, 1)")
    if pf != pf:  # NaN guard without math
        raise MetrologyError(MetrologyStatus.INVALID, "coverage probability must not be NaN")
    return pf


def coverage_factor(coverage_probability: float, nu_eff: float) -> Decimal:
    """Coverage factor ``k = t_{(1+p)/2}(nu_eff)`` (WRAP ``gum``).

    The wrapped helper rounds ``k`` to 6 decimals at its boundary; that
    rounding happens exactly there and nowhere else (no intermediate
    rounding in this layer).
    """
    pf = _check_coverage_probability(coverage_probability)
    try:
        nu = float(nu_eff)
    except (TypeError, ValueError) as exc:
        raise MetrologyError(MetrologyStatus.INVALID, f"bad degrees of freedom {nu_eff!r}") from exc
    if nu != nu or (nu not in (float("inf"),) and nu <= 0.0):
        raise MetrologyError(MetrologyStatus.INVALID, "degrees of freedom must be positive or inf")
    try:
        return calculate_coverage_factor(pf, nu)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc


def _classify_gum_failure(message: str) -> MetrologyStatus:
    lowered = message.lower()
    if "positive semi-definite" in lowered:
        return MetrologyStatus.SINGULAR
    if "combined variance is negative" in lowered:
        return MetrologyStatus.NUMERIC_ERROR
    return MetrologyStatus.INVALID


def evaluate_budget(
    model: MeasurementModel,
    inputs: Mapping[str, InputQuantity],
    correlation: CorrelationMatrix | None = None,
    coverage_probability: float = DEFAULT_COVERAGE_PROBABILITY,
    explicit_k: Decimal | int | str | None = None,
) -> GUMResult:
    """Analytic GUM budget ``u_c -> nu_eff -> k -> U`` (WRAP ``gum.evaluate_gum``).

    Ingress validated here (``1 <= N <= 64``, ``p in (0,1)``, finite
    ``explicit_k > 0``); the statistics themselves are the certified
    engine's. Failures map to typed states: non-PSD correlation ->
    ``SINGULAR``; negative combined variance -> ``NUMERIC_ERROR``; any other
    ``ValueError`` -> ``INVALID``. Never clamps, never takes ``abs()``.
    """
    if not isinstance(model, MeasurementModel):
        raise MetrologyError(MetrologyStatus.INVALID, "evaluate_budget needs a MeasurementModel")
    names = sorted(inputs.keys())
    if len(names) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "budget requires at least one input")
    if len(names) > MAX_METROLOGY_INPUTS:
        raise MetrologyError(
            MetrologyStatus.INVALID,
            f"budget supports at most {MAX_METROLOGY_INPUTS} inputs, got {len(names)}",
        )
    for key in names:
        if not isinstance(inputs[key], InputQuantity):
            raise MetrologyError(MetrologyStatus.INVALID, f"input {key!r} is not an InputQuantity")
    pf = _check_coverage_probability(coverage_probability)
    if explicit_k is not None:
        if isinstance(explicit_k, bool):
            raise MetrologyError(MetrologyStatus.INVALID, "explicit_k must be a positive number")
        try:
            k_check = Decimal(str(explicit_k))
        except Exception as exc:
            raise MetrologyError(MetrologyStatus.INVALID, f"bad explicit_k {explicit_k!r}") from exc
        if not k_check.is_finite() or k_check <= 0:
            raise MetrologyError(MetrologyStatus.INVALID, "explicit_k must be finite and > 0")
    corr = correlation if correlation is not None else CorrelationMatrix()
    if not isinstance(corr, CorrelationMatrix):
        raise MetrologyError(MetrologyStatus.INVALID, "correlation must be a CorrelationMatrix")
    try:
        corr.validate_psd(variables=names)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.SINGULAR, str(exc)) from exc
    try:
        return evaluate_gum(
            model,
            {key: inputs[key] for key in names},
            correlation=corr,
            coverage_probability=pf,
            explicit_k=explicit_k,
        )
    except MetrologyError:
        raise
    except ValueError as exc:
        raise MetrologyError(_classify_gum_failure(str(exc)), str(exc)) from exc
