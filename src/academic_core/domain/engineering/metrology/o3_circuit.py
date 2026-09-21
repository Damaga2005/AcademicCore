"""F8-O O3/O4/O12 circuit anchoring (REUSE F8-M + NEW copula/validation).

No new solver, no new sampler core, no new sensitivity engine:

- REUSE ``solve_dc_sensitivity`` / ``solve_ac_sensitivity`` (F8-M M4/M4-AC)
  for circuit-anchored ``c_i`` over the closed ``PARAM_REGISTRY``.
- REUSE ``run_monte_carlo_native`` / ``native_statistics`` /
  ``build_mc_plan`` semantics (F8-M M5, Decimal, seed-required) for Monte
  Carlo propagation; the seed is mandatory and a missing seed is INVALID.
- NEW ``correlated_normal_samples``: deterministic Gaussian copula in pure
  ``Decimal`` (Cholesky + Box-Muller via certified ``math.trig`` /
  ``math.logarithm`` helpers, local ``random.Random(seed)`` stream, canonical
  variable order). Needed because F8-M MC draws independent
  per-distribution samples while analytic budgets carry correlations.
- NEW ``validate_mc_vs_analytic``: diagnostic agreement criterion
  ``|u_MC - u_c| / u_c <= 5 %`` (statistical ``1/sqrt(M)`` guard, never a
  correctness proof on its own).
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Mapping, Sequence

from academic_core.domain.engineering.math.logarithm import decimal_ln10, decimal_log10
from academic_core.domain.engineering.math.trig import (
    decimal_cos,
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context,
)
from academic_core.domain.engineering.mna.analysis import (
    MAX_MC_ITERATIONS,
    MCConfig,
    ObservableSpec,
    ParamAddress,
    native_statistics,
    run_monte_carlo_native,
)
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.mna.sensitivity import (
    ACSensitivityConfig,
    SensitivityConfig,
    solve_ac_sensitivity,
    solve_dc_sensitivity,
)

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)

MC_AGREEMENT_TOLERANCE = Decimal("0.05")
_TWO = Decimal(2)
_HALF_PI_FACTOR = Decimal(2)


def _require_seed(seed: int | None) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise MetrologyError(
            MetrologyStatus.INVALID, "Monte Carlo requires an integer seed >= 0 (no random fallback)"
        )
    return seed


def dc_sensitivities(
    circuit: object,
    parameters: Sequence[ParamAddress],
    observables: Sequence[ObservableSpec],
    normalized: bool = False,
):  # REUSE F8-M M4
    """Circuit DC sensitivities ``dx/dp = -J^-1 dF/dp`` (REUSE ``solve_dc_sensitivity``)."""
    if len(tuple(parameters)) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "at least one parameter is required")
    if len(tuple(observables)) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "at least one observable is required")
    try:
        return solve_dc_sensitivity(
            circuit,  # type: ignore[arg-type]
            SensitivityConfig(
                parameters=tuple(parameters), observables=tuple(observables), normalized=normalized
            ),
        )
    except InvalidCircuitError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc


def ac_sensitivities(
    circuit: object,
    frequency: object,
    parameters: Sequence[ParamAddress],
    observables: Sequence[ObservableSpec],
):  # REUSE F8-M M4-AC
    """Circuit AC sensitivities (REUSE ``solve_ac_sensitivity``)."""
    if len(tuple(parameters)) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "at least one parameter is required")
    if len(tuple(observables)) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "at least one observable is required")
    try:
        return solve_ac_sensitivity(
            circuit,  # type: ignore[arg-type]
            ACSensitivityConfig(
                frequency=frequency,  # type: ignore[arg-type]
                parameters=tuple(parameters),
                observables=tuple(observables),
            ),
        )
    except InvalidCircuitError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc


def run_mc(circuit: object, config: MCConfig):  # REUSE F8-M M5
    """Monte Carlo propagation (REUSE ``run_monte_carlo_native``).

    The config seed is mandatory (F8-M raises without it); a missing or
    invalid seed maps to ``MetrologyError(INVALID)`` here. Non-converged
    iterations are recorded by the engine (``COMPLETED_WITH_FAILURES``),
    never hidden.
    """
    if not isinstance(config, MCConfig):
        raise MetrologyError(MetrologyStatus.INVALID, "run_mc needs an F8-M MCConfig")
    _require_seed(config.seed)
    try:
        return run_monte_carlo_native(circuit, config)  # type: ignore[arg-type]
    except InvalidCircuitError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc


def mc_observable_values(mc_result: object, observable_key: str) -> tuple[Decimal, ...]:
    """Extract converged-iteration observable values as Decimals.

    Consumes the public ``to_dict()`` (stable contract); failed iterations
    are skipped (their count is preserved by the engine result).
    """
    to_dict = mc_result.to_dict  # type: ignore[union-attr]
    doc = to_dict()
    iterations = doc.get("iterations", ())
    out: list[Decimal] = []
    for entry in iterations:
        if entry.get("status") != "ok":
            continue
        observables = entry.get("observables", {})
        if observable_key not in observables:
            raise MetrologyError(
                MetrologyStatus.INVALID, f"observable {observable_key!r} absent from MC iteration"
            )
        try:
            out.append(Decimal(str(observables[observable_key])))
        except Exception as exc:
            raise MetrologyError(MetrologyStatus.NUMERIC_ERROR, "bad MC observable value") from exc
    return tuple(out)


def mc_statistics(values: Sequence[Decimal]) -> dict:
    """Descriptive statistics in Decimal (REUSE ``native_statistics``)."""
    if len(tuple(values)) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "statistics need at least one value")
    try:
        return native_statistics(list(values))
    except (ValueError, ArithmeticError) as exc:
        raise MetrologyError(MetrologyStatus.NUMERIC_ERROR, str(exc)) from exc


def validate_mc_vs_analytic(
    mc_std: Decimal,
    analytic_uc: Decimal,
    tolerance: Decimal = MC_AGREEMENT_TOLERANCE,
) -> dict:
    """Diagnostic MC-vs-analytic agreement (NEW, criterion only).

    ``relative = |u_MC - u_c| / max(u_c, eps)`` with ``eps = 1e-30``; the
    ``5 %`` gate reflects ``1/sqrt(M)`` sampling noise at ``M >= 10^4`` and
    is a diagnostic flag, not a proof of correctness. Degenerate
    ``u_c = 0`` requires ``u_MC = 0`` exactly.
    """
    if not isinstance(mc_std, Decimal) or not isinstance(analytic_uc, Decimal):
        raise MetrologyError(MetrologyStatus.INVALID, "validate_mc_vs_analytic needs Decimals")
    if mc_std < 0 or analytic_uc < 0:
        raise MetrologyError(MetrologyStatus.INVALID, "uncertainties must be non-negative")
    if tolerance <= 0:
        raise MetrologyError(MetrologyStatus.INVALID, "tolerance must be positive")
    if analytic_uc == 0:
        agreement = mc_std == 0
        relative = Decimal(0) if agreement else Decimal("Infinity")
    else:
        diff = mc_std - analytic_uc
        relative = abs(diff) / analytic_uc
        agreement = relative <= tolerance
    return {
        "mc_std": str(mc_std),
        "analytic_uc": str(analytic_uc),
        "relative_difference": str(relative),
        "tolerance": str(tolerance),
        "agreement": agreement,
    }


def _decimal_ln(x: Decimal) -> Decimal:
    """Natural log in Decimal via ``ln(x) = log10(x) * ln(10)`` (REUSE certified helpers)."""
    if x <= 0:
        raise MetrologyError(MetrologyStatus.NUMERIC_ERROR, "ln of non-positive value")
    return decimal_log10(x) * decimal_ln10()


def _cholesky(corr: Sequence[Sequence[Decimal]]) -> list[list[Decimal]]:
    """Cholesky ``L L^T = R`` in Decimal (NEW, exact, no float).

    Raises ``MetrologyError(SINGULAR)`` for a degenerate pivot (matrix
    unfit for correlated sampling) — never silently clamped.
    """
    n = len(corr)
    lower: list[list[Decimal]] = [[Decimal(0)] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            acc = corr[i][j]
            for k in range(j):
                acc = acc - lower[i][k] * lower[j][k]
            if i == j:
                if acc < 0:
                    raise MetrologyError(
                        MetrologyStatus.SINGULAR, "correlation matrix degenerate for Cholesky"
                    )
                if acc == 0:
                    lower[i][j] = Decimal(0)
                else:
                    lower[i][j] = decimal_sqrt(acc)
            else:
                pivot = lower[j][j]
                if pivot == 0:
                    if acc != 0:
                        raise MetrologyError(
                            MetrologyStatus.SINGULAR, "correlation matrix degenerate for Cholesky"
                        )
                    lower[i][j] = Decimal(0)
                else:
                    lower[i][j] = acc / pivot
    return lower


def correlated_normal_samples(
    means: Sequence[Decimal],
    stds: Sequence[Decimal],
    pairs: Sequence[tuple[str, str, Decimal]],
    names: Sequence[str],
    n: int,
    seed: int,
) -> tuple[tuple[Decimal, ...], ...]:
    """Deterministic correlated Gaussian samples (NEW copula, Decimal-only).

    Joint draws ``X = mean + diag(std) L Z`` with ``L`` the Cholesky factor
    of the validated PSD correlation over canonical (sorted) ``names`` and
    ``Z`` iid standard normals from Box-Muller over a local
    ``random.Random(seed)`` uniform stream (``getrandbits(53)/2^53`` exact
    fractions; ``u == 0`` resampled deterministically). No global random,
    no float, no timestamp. ``std = 0`` yields the constant mean while still
    consuming the stream (position-stable). Bounds: ``1 <= n <= 10000``.
    """
    ordered = tuple(sorted(names))
    dim = len(ordered)
    if dim == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "copula needs at least one variable")
    if len(tuple(means)) != dim or len(tuple(stds)) != dim:
        raise MetrologyError(MetrologyStatus.INVALID, "means/stds must match names")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1 or n > MAX_MC_ITERATIONS:
        raise MetrologyError(
            MetrologyStatus.INVALID, f"copula samples n must lie in [1, {MAX_MC_ITERATIONS}]"
        )
    seed = _require_seed(seed)
    mean_map = {key: means[idx] for idx, key in enumerate(ordered)}
    std_map = {key: stds[idx] for idx, key in enumerate(ordered)}
    for key in ordered:
        if std_map[key] < 0:
            raise MetrologyError(MetrologyStatus.INVALID, f"std of {key!r} must be non-negative")
        if not mean_map[key].is_finite():
            raise MetrologyError(MetrologyStatus.INVALID, f"mean of {key!r} must be finite")
    pair_map: dict[tuple[str, str], Decimal] = {}
    for v1, v2, r in pairs:
        if v1 not in mean_map or v2 not in mean_map:
            raise MetrologyError(MetrologyStatus.INVALID, "correlation pair outside names")
        if r < -1 or r > 1:
            raise MetrologyError(MetrologyStatus.INVALID, "correlation outside [-1, 1]")
        pair_map[(v1, v2)] = r
        pair_map[(v2, v1)] = r
    matrix: list[list[Decimal]] = []
    for v1 in ordered:
        row: list[Decimal] = []
        for v2 in ordered:
            if v1 == v2:
                row.append(Decimal(1))
            else:
                row.append(pair_map.get((v1, v2), Decimal(0)))
        matrix.append(row)
    lower = _cholesky(matrix)
    ctx = make_context()
    two_pi = _HALF_PI_FACTOR * decimal_pi(ctx)
    rng = random.Random(seed)
    denom = Decimal(2**53)

    def _uniform() -> Decimal:
        while True:
            candidate = Decimal(rng.getrandbits(53)) / denom
            if candidate != 0 and candidate != 1:
                return candidate

    rows: list[tuple[Decimal, ...]] = []
    for _ in range(n):
        normals: list[Decimal] = []
        while len(normals) < dim:
            u1 = _uniform()
            u2 = _uniform()
            radius = decimal_sqrt(-_TWO * _decimal_ln(u1))
            angle = two_pi * u2
            normals.append(radius * decimal_cos(angle))
            if len(normals) < dim:
                normals.append(radius * decimal_sin(angle))
        correlated: list[Decimal] = []
        for i in range(dim):
            acc = Decimal(0)
            for k in range(i + 1):
                acc = acc + lower[i][k] * normals[k]
            key = ordered[i]
            correlated.append(mean_map[key] + std_map[key] * acc)
        rows.append(tuple(correlated))
    _ = ctx
    return tuple(rows)


def copula_marginal_stats(
    samples: Sequence[Sequence[Decimal]],
) -> Mapping[str, dict]:
    """Marginal native statistics per column index (REUSE ``native_statistics``)."""
    rows = tuple(samples)
    if len(rows) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "no copula samples")
    dim = len(rows[0])
    out: dict[str, dict] = {}
    for idx in range(dim):
        out[f"var_{idx}"] = mc_statistics(tuple(row[idx] for row in rows))
    return out
