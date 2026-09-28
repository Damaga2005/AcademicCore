# SPDX-License-Identifier: MIT
"""F16 two-body circular/elliptic relations + orbital energy (NEW).

All quantities are ``Decimal`` SI (m, kg, s, J). Angles are plain Decimal
radians. Each formula lives in exactly one function:

- circular: ``v = sqrt(mu/r)``, ``T = 2*pi*sqrt(r^3/mu)`` + inverses.
- vis-viva: ``v^2 = mu*(2/r - 1/a)`` (+ semimajor inverse).
- energy: kinetic / potential / total / specific (total vs specific
  never confused: specific is per unit mass, J/kg).
- escape: ``v_esc = sqrt(2*mu/r)``.
- ellipse: ``rp = a*(1-e)``, ``ra = a*(1+e)`` (+ apsides inverse).

``r`` is always the radius from the body's centre; ``h`` the altitude
above the surface. The two are never mixed: conversion helpers are
explicit and the below-surface case is rejected, never clamped.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import decimal_sqrt, make_context


def _cbrt(value: Decimal) -> Decimal:
    """Principal real cbrt via Newton from above (explicit budget).

    ``decimal_nth_root`` refuses inputs whose residual cannot clear its
    50-digit gates; orbital radii need a documented looser contract:
    relative step <= 1E-40 within 500 iterations, else MAX_ITERATIONS.
    """
    ctx = make_context()
    if value <= 0:
        raise ControlError(ControlStatus.INVALID, "cbrt needs x > 0")
    exp = value.adjusted()
    cur = Decimal(10) ** ((exp // 3) + 1)
    three = Decimal(3)
    tol = Decimal("1E-40")
    for _ in range(500):
        nxt = ctx.divide(ctx.add(ctx.multiply(Decimal(2), cur),
                                 ctx.divide(value, ctx.multiply(cur, cur))), three)
        if abs(ctx.subtract(nxt, cur)) <= abs(cur) * tol:
            return ctx.plus(nxt)
        cur = nxt
    raise ControlError(ControlStatus.MAX_ITERATIONS, "cbrt did not converge")


def _pos(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ControlError(ControlStatus.INVALID, label + " must be finite and > 0")
    return value


def _ctx():
    return make_context()


# -- radius <-> altitude ------------------------------------------------

def radius_from_altitude_m(altitude_m: Decimal, body_radius_m: Decimal) -> Decimal:
    """r = R + h (m from the body centre). h >= 0."""
    if isinstance(altitude_m, bool) or not isinstance(altitude_m, Decimal):
        raise ControlError(ControlStatus.INVALID, "altitude must be Decimal")
    if not altitude_m.is_finite() or altitude_m < 0:
        raise ControlError(ControlStatus.INVALID, "altitude must be finite and >= 0")
    body = _pos(body_radius_m, "body radius")
    return altitude_m + body


def altitude_from_radius_m(radius_m: Decimal, body_radius_m: Decimal) -> Decimal:
    """h = r - R. r < R is rejected (below the surface), never clamped."""
    r = _pos(radius_m, "radius")
    body = _pos(body_radius_m, "body radius")
    if r < body:
        raise ControlError(ControlStatus.INVALID, "radius below the body surface")
    return r - body


# -- circular orbit ------------------------------------------------------

def circular_velocity_m_s(radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """v = sqrt(mu/r) (m/s)."""
    r = _pos(radius_m, "radius")
    mu = _pos(mu_m3_s2, "mu")
    return decimal_sqrt(_ctx().divide(mu, r))


def circular_period_s(radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """T = 2*pi*sqrt(r^3/mu) (s)."""
    from academic_core.domain.engineering.math import decimal_pi
    r = _pos(radius_m, "radius")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    ratio = ctx.divide(ctx.multiply(ctx.multiply(r, r), r), mu)
    return ctx.multiply(ctx.multiply(Decimal(2), decimal_pi()), decimal_sqrt(ratio))


def period_from_radius_s(radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """Alias of the circular period (bound orbit of semimajor axis r)."""
    return circular_period_s(radius_m, mu_m3_s2)


def radius_from_period_m(period_s: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """r = cbrt(mu*(T/2pi)^2) (m). Exact inverse of the circular period."""
    from academic_core.domain.engineering.math import decimal_pi
    t = _pos(period_s, "period")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    half = ctx.divide(t, ctx.multiply(Decimal(2), decimal_pi()))
    return _cbrt(ctx.multiply(mu, ctx.multiply(half, half)))


# -- vis-viva --------------------------------------------------------------

def vis_viva_velocity_m_s(radius_m: Decimal, semimajor_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """v = sqrt(mu*(2/r - 1/a)) (m/s). Reduces to circular for a == r."""
    r = _pos(radius_m, "radius")
    a = _pos(semimajor_m, "semimajor axis")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    inner = ctx.subtract(ctx.divide(Decimal(2), r), ctx.divide(Decimal(1), a))
    if inner <= 0:
        raise ControlError(ControlStatus.INVALID, "vis-viva radicand must be > 0")
    return decimal_sqrt(ctx.multiply(mu, inner))


def vis_viva_semimajor_m(radius_m: Decimal, velocity_m_s: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """1/a = 2/r - v^2/mu (m). Inverse of vis-viva; a <= 0 rejected
    (unbound or inconsistent input, never silently returned)."""
    r = _pos(radius_m, "radius")
    v = _pos(velocity_m_s, "velocity")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    inv_a = ctx.subtract(ctx.divide(Decimal(2), r),
                         ctx.divide(ctx.multiply(v, v), mu))
    if inv_a <= 0:
        raise ControlError(ControlStatus.INVALID, "unbound trajectory (a <= 0)")
    return ctx.divide(Decimal(1), inv_a)


# -- energy ------------------------------------------------------------------

def kinetic_energy_j(mass_kg: Decimal, velocity_m_s: Decimal) -> Decimal:
    """K = m*v^2/2 (J)."""
    m = _pos(mass_kg, "mass")
    v = _pos(velocity_m_s, "velocity")
    ctx = _ctx()
    return ctx.divide(ctx.multiply(m, ctx.multiply(v, v)), Decimal(2))


def potential_energy_j(mass_kg: Decimal, radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """U = -m*mu/r (J), zero at infinity."""
    m = _pos(mass_kg, "mass")
    r = _pos(radius_m, "radius")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    return ctx.divide(ctx.multiply(ctx.multiply(m, mu), Decimal(-1)), r)


def total_energy_j(mass_kg: Decimal, velocity_m_s: Decimal,
                   radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """E = K + U (J, total mechanical energy of mass m)."""
    return (kinetic_energy_j(mass_kg, velocity_m_s)
            + potential_energy_j(mass_kg, radius_m, mu_m3_s2))


def specific_energy_j_kg(velocity_m_s: Decimal, radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """eps = v^2/2 - mu/r (J/kg, per unit mass)."""
    v = _pos(velocity_m_s, "velocity")
    r = _pos(radius_m, "radius")
    mu = _pos(mu_m3_s2, "mu")
    ctx = _ctx()
    return ctx.subtract(ctx.divide(ctx.multiply(v, v), Decimal(2)),
                        ctx.divide(mu, r))


# -- escape --------------------------------------------------------------------

def escape_velocity_m_s(radius_m: Decimal, mu_m3_s2: Decimal) -> Decimal:
    """v_esc = sqrt(2*mu/r) (m/s) from the given centre radius."""
    r = _pos(radius_m, "radius")
    mu = _pos(mu_m3_s2, "mu")
    return decimal_sqrt(_ctx().divide(_ctx().multiply(Decimal(2), mu), r))


# -- ellipse ---------------------------------------------------------------------

def periapsis_m(semimajor_m: Decimal, eccentricity: Decimal) -> Decimal:
    """rp = a*(1-e) (m). Bound ellipse: 0 <= e < 1."""
    a = _pos(semimajor_m, "semimajor axis")
    e = _check_eccentricity(eccentricity)
    return _ctx().multiply(a, _ctx().subtract(Decimal(1), e))


def apoapsis_m(semimajor_m: Decimal, eccentricity: Decimal) -> Decimal:
    """ra = a*(1+e) (m)."""
    a = _pos(semimajor_m, "semimajor axis")
    e = _check_eccentricity(eccentricity)
    return _ctx().multiply(a, _ctx().add(Decimal(1), e))


def ellipse_from_apsides_m(periapsis: Decimal, apoapsis: Decimal) -> tuple:
    """(a, e) from rp/ra (m). rp <= ra required."""
    for label, v in (("periapsis", periapsis), ("apoapsis", apoapsis)):
        _pos(v, label)
    if apoapsis < periapsis:
        raise ControlError(ControlStatus.INVALID, "apoapsis must be >= periapsis")
    ctx = _ctx()
    a = ctx.divide(ctx.add(periapsis, apoapsis), Decimal(2))
    e = ctx.divide(ctx.subtract(apoapsis, periapsis), ctx.add(apoapsis, periapsis))
    return a, e


def _check_eccentricity(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, "eccentricity must be Decimal")
    if not value.is_finite() or value < 0 or value >= 1:
        raise ControlError(ControlStatus.INVALID, "eccentricity must satisfy 0 <= e < 1")
    return value


# -- explicit SI conversions (never silent, always Decimal) ------------------

def km_to_m(km: Decimal) -> Decimal:
    """km -> m (exact x1000)."""
    return _ctx().multiply(_pos(km, "km"), Decimal(1000))


def m_to_km(m: Decimal) -> Decimal:
    """m -> km (exact /1000)."""
    return _ctx().divide(_pos(m, "m"), Decimal(1000))


def day_to_s(days: Decimal) -> Decimal:
    """days -> s (exact x86400)."""
    return _ctx().multiply(_pos(days, "days"), Decimal(86400))


def hour_to_s(hours: Decimal) -> Decimal:
    """h -> s (exact x3600)."""
    return _ctx().multiply(_pos(hours, "hours"), Decimal(3600))


def minute_to_s(minutes: Decimal) -> Decimal:
    """min -> s (exact x60)."""
    return _ctx().multiply(_pos(minutes, "minutes"), Decimal(60))


def deg_to_rad(degrees: Decimal) -> Decimal:
    """deg -> rad via the 50-digit pi (single place for the factor)."""
    from academic_core.domain.engineering.math import decimal_pi
    if isinstance(degrees, bool) or not isinstance(degrees, Decimal):
        raise ControlError(ControlStatus.INVALID, "degrees must be Decimal")
    if not degrees.is_finite():
        raise ControlError(ControlStatus.INVALID, "degrees must be finite")
    ctx = _ctx()
    return ctx.divide(ctx.multiply(degrees, decimal_pi()), Decimal(180))
