"""F8-P3 closed-form impedance matching (NEW): conjugate, quarter-wave,
single-stub (shunt/series, short/open), single series/shunt LC.

Only the closed-form solvable set of gate §18 is implemented; anything
outside a documented realizability predicate returns UNSUPPORTED
(never a generic numeric optimizer or third-party search routine).
Every solution
is verifiable by the caller through the mandatory invariant of gate
§18: cascading the match with the load must reproduce the target
input impedance/reflection within the certified residual (<=1e-30).

The single-stub distances/lengths below are derived directly from the
gate's own Zin identities (§6/§8) -- there is no second Zin engine:
the quadratic-in-``tan(beta*d)`` conditions and the resulting stub
lengths are closed algebraic consequences of
``Zin = Z0*(ZL + j*Z0*tan(beta*l))/(Z0 + j*ZL*tan(beta*l))``
specialised to ``ZL = 0`` (short) / ``ZL -> infinity`` (open).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, decimal_atan2, decimal_pi, decimal_sqrt, make_context

ENGINE_VERSION = "f8p3-rf/1"

MAX_MATCH_CANDIDATES = 8


def _require_complex(value, name: str) -> DecimalComplex:
    if not isinstance(value, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, f"{name} must be DecimalComplex")
    if not value.re.is_finite() or not value.im.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


def _require_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, f"{name} must be Decimal")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


# -- (a) conjugate match ----------------------------------------------------


def conjugate_match(zs: DecimalComplex) -> DecimalComplex:
    """ZL = conj(Zs): the closed-form maximum power transfer condition."""
    _require_complex(zs, "Zs")
    return zs.conjugate()


# -- (b) quarter-wave transformer -------------------------------------------


@dataclass(frozen=True)
class QuarterWaveResult:
    transformer_z0: Decimal


def quarter_wave_match(z0: Decimal, zl: Decimal, ctx=None) -> QuarterWaveResult:
    """Z_lambda/4 = sqrt(Z0*ZL) for real ZL > 0 (Zin = Z0^2/ZL verified
    by the caller against the transformer line, gate §18/§25)."""
    c = ctx or make_context()
    z0 = _require_decimal(z0, "Z0")
    zl = _require_decimal(zl, "ZL")
    if z0 <= 0:
        raise ControlError(ControlStatus.INVALID, "quarter-wave needs Z0 > 0")
    if zl <= 0:
        raise ControlError(ControlStatus.UNSUPPORTED, "quarter-wave needs a real ZL > 0")
    return QuarterWaveResult(decimal_sqrt(c.multiply(z0, zl), c))


# -- (e) single series/shunt LC ----------------------------------------------


@dataclass(frozen=True)
class LMatchSolution:
    topology: str  # "series-then-shunt" | "shunt-then-series"
    series_reactance: Decimal  # Ohm, at the load-adjacent element (0 if none)
    shunt_susceptance: Decimal  # Siemens, at the load-adjacent element (0 if none)


def lc_match(zl: DecimalComplex, z0: Decimal, ctx=None) -> tuple:
    """Analytic L-section reactance/susceptance matching a complex load
    ZL = RL+jXL to a real Z0 at the design frequency (gate §18(e)).

    Two topologies, each admitting two sign candidates:

    * RL <= Z0: series reactance Xs at the load, then a shunt
      susceptance Bp toward the source (``series-then-shunt``).
    * RL >= Z0: shunt susceptance Bp at the load, then a series
      reactance Xs toward the source (``shunt-then-series``).

    RL <= 0 -> UNSUPPORTED (no real resistive part to match)."""
    c = ctx or make_context()
    z0 = _require_decimal(z0, "Z0")
    if z0 <= 0:
        raise ControlError(ControlStatus.INVALID, "lc_match needs Z0 > 0")
    _require_complex(zl, "ZL")
    rl, xl = zl.re, zl.im
    if rl <= 0:
        raise ControlError(ControlStatus.UNSUPPORTED, "lc_match needs Re(ZL) > 0")

    solutions: list = []
    if rl <= z0:
        disc = c.multiply(rl, c.subtract(z0, rl))
        if disc >= 0:
            root = decimal_sqrt(disc, c) if disc > 0 else Decimal(0)
            for sign in (Decimal(1), Decimal(-1)):
                x_prime = c.multiply(sign, root)
                xs = c.subtract(x_prime, xl)
                bp = c.divide(x_prime, c.multiply(rl, z0))
                solutions.append(LMatchSolution("series-then-shunt", xs, bp))
                if disc == 0:
                    break
    if rl >= z0:
        rl2xl2 = c.add(c.multiply(rl, rl), c.multiply(xl, xl))
        if rl2xl2 == 0:
            raise ControlError(ControlStatus.SINGULAR, "lc_match singular (ZL == 0)")
        gl = c.divide(rl, rl2xl2)
        bl = c.minus(c.divide(xl, rl2xl2))
        inner = c.subtract(Decimal(1), c.multiply(gl, z0))
        disc = c.multiply(gl, c.divide(inner, z0))
        if disc >= 0:
            root = decimal_sqrt(disc, c) if disc > 0 else Decimal(0)
            for sign in (Decimal(1), Decimal(-1)):
                b_prime = c.multiply(sign, root)
                bp = c.subtract(b_prime, bl)
                xs = c.divide(c.multiply(b_prime, z0), gl)
                solutions.append(LMatchSolution("shunt-then-series", xs, bp))
                if disc == 0:
                    break
    if not solutions:
        raise ControlError(ControlStatus.UNSUPPORTED, "lc_match: no closed-form solution")
    return tuple(solutions)


# -- (c)/(d) single stub matching ---------------------------------------------


def _quadratic_roots(a: Decimal, b: Decimal, c_coef: Decimal, ctx) -> tuple:
    c = ctx
    if a == 0:
        if b == 0:
            return ()
        return (c.minus(c.divide(c_coef, b)),)
    disc = c.subtract(c.multiply(b, b), c.multiply(Decimal(4), c.multiply(a, c_coef)))
    if disc < 0:
        return ()
    root = decimal_sqrt(disc, c) if disc > 0 else Decimal(0)
    t1 = c.divide(c.add(c.minus(b), root), c.multiply(Decimal(2), a))
    if disc == 0:
        return (t1,)
    t2 = c.divide(c.subtract(c.minus(b), root), c.multiply(Decimal(2), a))
    return (t1, t2)


def _length_from_tan(target_tan: Decimal, beta: Decimal, ctx) -> Decimal:
    theta = decimal_atan2(target_tan, Decimal(1), ctx)
    if theta < 0:
        theta = ctx.add(theta, decimal_pi(ctx))
    return ctx.divide(theta, beta)


def _length_from_cot(target_cot: Decimal, beta: Decimal, ctx) -> Decimal:
    theta = decimal_atan2(Decimal(1), target_cot, ctx)
    return ctx.divide(theta, beta)


@dataclass(frozen=True)
class StubSolution:
    tap_distance: Decimal  # m, distance from the load to the stub tap
    stub_kind: str  # "short" | "open"
    stub_length: Decimal  # m


def single_stub_shunt_match(zl: DecimalComplex, z0: Decimal, beta: Decimal, ctx=None) -> tuple:
    """Single shunt-stub matching (gate §18(c)): distance ``d`` from
    the load solving ``Re(y(d)) = 1`` (normalized), then a shunt
    stub cancelling the residual susceptance. Up to
    ``2 solutions x {short, open}`` candidates."""
    c = ctx or make_context()
    z0 = _require_decimal(z0, "Z0")
    beta = _require_decimal(beta, "beta")
    if z0 <= 0 or beta <= 0:
        raise ControlError(ControlStatus.INVALID, "single_stub_shunt_match needs Z0 > 0, beta > 0")
    _require_complex(zl, "ZL")
    rl = c.divide(zl.re, z0)
    xl = c.divide(zl.im, z0)
    if rl <= 0:
        raise ControlError(ControlStatus.UNSUPPORTED, "shunt-stub matching needs Re(ZL) > 0")

    a = c.subtract(rl, Decimal(1))
    b = c.minus(c.multiply(Decimal(2), xl))
    c_coef = c.subtract(rl, c.add(c.multiply(rl, rl), c.multiply(xl, xl)))
    t_roots = _quadratic_roots(a, b, c_coef, c)
    if not t_roots:
        raise ControlError(ControlStatus.UNSUPPORTED, "shunt-stub matching: no real solution")

    solutions: list = []
    for t in t_roots:
        one_plus_t2 = c.add(Decimal(1), c.multiply(t, t))
        b_stub = c.divide(
            c.subtract(c.multiply(xl, c.subtract(Decimal(1), c.multiply(t, t))), c.multiply(t, c.subtract(c.add(c.multiply(rl, rl), c.multiply(xl, xl)), Decimal(1)))),
            c.multiply(rl, one_plus_t2),
        )
        d = _length_from_tan(t, beta, c)
        if b_stub == 0:
            l_short = c.divide(decimal_pi(c), c.multiply(Decimal(2), beta))
            l_open = Decimal(0)
        else:
            l_short = _length_from_cot(c.minus(b_stub), beta, c)
            l_open = _length_from_tan(b_stub, beta, c)
        solutions.append(StubSolution(d, "short", l_short))
        solutions.append(StubSolution(d, "open", l_open))
    return tuple(solutions[:MAX_MATCH_CANDIDATES])


def single_stub_series_match(zl: DecimalComplex, z0: Decimal, beta: Decimal, ctx=None) -> tuple:
    """Single series-stub matching (gate §18(d), dual of the shunt
    case): distance ``d`` solving ``Re(z(d)) = 1`` (normalized), then
    a series stub cancelling the residual reactance."""
    c = ctx or make_context()
    z0 = _require_decimal(z0, "Z0")
    beta = _require_decimal(beta, "beta")
    if z0 <= 0 or beta <= 0:
        raise ControlError(ControlStatus.INVALID, "single_stub_series_match needs Z0 > 0, beta > 0")
    _require_complex(zl, "ZL")
    rl = c.divide(zl.re, z0)
    xl = c.divide(zl.im, z0)
    if rl <= 0:
        raise ControlError(ControlStatus.UNSUPPORTED, "series-stub matching needs Re(ZL) > 0")

    a = c.subtract(c.multiply(rl, c.subtract(Decimal(1), rl)), c.multiply(xl, xl))
    b = c.multiply(Decimal(2), xl)
    c_coef = c.subtract(rl, Decimal(1))
    t_roots = _quadratic_roots(a, b, c_coef, c)
    if not t_roots:
        raise ControlError(ControlStatus.UNSUPPORTED, "series-stub matching: no real solution")

    solutions: list = []
    for t in t_roots:
        one_plus_t2 = c.add(Decimal(1), c.multiply(t, t))
        x_stub = c.minus(
            c.divide(
                c.add(xl, c.subtract(c.multiply(t, c.subtract(Decimal(1), c.add(c.multiply(xl, xl), c.multiply(rl, rl)))), c.multiply(xl, c.multiply(t, t)))),
                c.multiply(rl, one_plus_t2),
            )
        )
        d = _length_from_tan(t, beta, c)
        if x_stub == 0:
            l_open = c.divide(decimal_pi(c), c.multiply(Decimal(2), beta))
            l_short = Decimal(0)
        else:
            l_short = _length_from_tan(x_stub, beta, c)
            l_open = _length_from_cot(c.minus(x_stub), beta, c)
        solutions.append(StubSolution(d, "short", l_short))
        solutions.append(StubSolution(d, "open", l_open))
    return tuple(solutions[:MAX_MATCH_CANDIDATES])
