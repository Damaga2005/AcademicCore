# SPDX-License-Identifier: MIT
"""F16 Kepler equation + anomalies (NEW).

Closed forms where they exist (M from E, true <-> eccentric); Newton with
an explicit tolerance/iteration budget and a clear non-convergence error
for E from M. Angles are plain Decimal radians in [0, 2*pi) unless noted.
No unbounded iteration anywhere.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    decimal_atan2,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

_TWO_PI = None


def _two_pi() -> Decimal:
    ctx = make_context()
    return ctx.multiply(Decimal(2), decimal_pi())


def _check_angle(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal radians")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, label + " must be finite")
    return value


def _check_e(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, "eccentricity must be Decimal")
    if not value.is_finite() or value < 0 or value >= 1:
        raise ControlError(ControlStatus.INVALID, "eccentricity must satisfy 0 <= e < 1")
    return value


def mean_from_eccentric_rad(eccentric_rad: Decimal, eccentricity: Decimal) -> Decimal:
    """M = E - e*sin(E) (rad). Closed form."""
    e_anom = _check_angle(eccentric_rad, "eccentric anomaly")
    e = _check_e(eccentricity)
    ctx = make_context()
    return ctx.subtract(e_anom, ctx.multiply(e, decimal_sin(e_anom)))


def eccentric_from_mean_rad(mean_rad: Decimal, eccentricity: Decimal,
                            tol: Decimal = Decimal("1E-40"),
                            max_iter: int = 200) -> Decimal:
    """E from M = E - e*sin(E) via Newton from E0 = M.

    Explicit tolerance (Decimal > 0) and iteration budget (int >= 1);
    ``ControlError(MAX_ITERATIONS)`` when the budget is exhausted.
    Deterministic: same input gives the same iterate sequence.
    """
    m = _check_angle(mean_rad, "mean anomaly")
    e = _check_e(eccentricity)
    if isinstance(tol, bool) or not isinstance(tol, Decimal) \
            or not tol.is_finite() or tol <= 0:
        raise ControlError(ControlStatus.INVALID, "tolerance must be Decimal > 0")
    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter < 1:
        raise ControlError(ControlStatus.INVALID, "max_iter must be int >= 1")
    ctx = make_context()
    two_pi = _two_pi()
    target = ctx.remainder(m, two_pi)
    if target < 0:
        target = ctx.add(target, two_pi)
    cur = target
    for _ in range(max_iter):
        f = ctx.subtract(ctx.subtract(cur, ctx.multiply(e, decimal_sin(cur))), target)
        fp = ctx.subtract(Decimal(1), ctx.multiply(e, decimal_cos(cur)))
        step = ctx.divide(f, fp)
        cur = ctx.subtract(cur, step)
        if abs(step) <= tol and abs(f) <= tol:
            out = ctx.remainder(cur, two_pi)
            return ctx.add(out, two_pi) if out < 0 else out
    raise ControlError(ControlStatus.MAX_ITERATIONS,
                       f"Kepler did not converge in {max_iter} iterations")


def true_from_eccentric_rad(eccentric_rad: Decimal, eccentricity: Decimal) -> Decimal:
    """nu = 2*atan2(sqrt(1+e)*sin(E/2), sqrt(1-e)*cos(E/2)) in [0, 2pi)."""
    from academic_core.domain.engineering.math import decimal_sqrt
    e_anom = _check_angle(eccentric_rad, "eccentric anomaly")
    e = _check_e(eccentricity)
    ctx = make_context()
    half = ctx.divide(e_anom, Decimal(2))
    y = ctx.multiply(decimal_sqrt(ctx.add(Decimal(1), e)), decimal_sin(half))
    x = ctx.multiply(decimal_sqrt(ctx.subtract(Decimal(1), e)), decimal_cos(half))
    nu = ctx.multiply(Decimal(2), decimal_atan2(y, x))
    two_pi = _two_pi()
    nu = ctx.remainder(nu, two_pi)
    return ctx.add(nu, two_pi) if nu < 0 else nu


def eccentric_from_true_rad(true_rad: Decimal, eccentricity: Decimal) -> Decimal:
    """E = 2*atan2(sqrt(1-e)*sin(nu/2), sqrt(1+e)*cos(nu/2)) in [0, 2pi)."""
    from academic_core.domain.engineering.math import decimal_sqrt
    nu = _check_angle(true_rad, "true anomaly")
    e = _check_e(eccentricity)
    ctx = make_context()
    half = ctx.divide(nu, Decimal(2))
    y = ctx.multiply(decimal_sqrt(ctx.subtract(Decimal(1), e)), decimal_sin(half))
    x = ctx.multiply(decimal_sqrt(ctx.add(Decimal(1), e)), decimal_cos(half))
    out = ctx.multiply(Decimal(2), decimal_atan2(y, x))
    two_pi = _two_pi()
    out = ctx.remainder(out, two_pi)
    return ctx.add(out, two_pi) if out < 0 else out
