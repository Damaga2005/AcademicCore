"""Decimal high-precision transcendental helpers (F8-D1).

Pure-``Decimal`` implementations: arctangent via the Machin identity,
sine/cosine via range-reduced Taylor series, square root via the
explicit ``decimal.Context`` operation. No ``math``, no ``cmath``, no
``float`` and no ``complex`` anywhere in this module.

Every routine builds its own explicit ``decimal.Context`` and never
reads or mutates the ambient global context (``decimal.getcontext()``).

``WORKING_PRECISION = 50`` counts significant decimal digits of the
working context. It is a *working precision*, not a claim of 50
mathematically correct digits: series truncation and per-operation
rounding make every result a high-precision numerical approximation.
Callers that surface these values (``DecimalComplex.modulus``,
``DecimalComplex.phase``, ``complex_from_polar``) document that fact.
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN

WORKING_PRECISION = 50

#: Extra guard digits used internally so the final rounding to working
#: precision is not contaminated by intermediate truncation error.
_GUARD_DIGITS = 15


def make_context(extra: int = 0) -> Context:
    """Return a fresh explicit context (never the ambient global one)."""
    return Context(prec=WORKING_PRECISION + extra, rounding=ROUND_HALF_EVEN)


def _as_decimal(value: int | Decimal) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("bool is not an accepted numeric input")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    raise TypeError(f"expected int or Decimal, got {type(value).__name__}")


def decimal_sqrt(value: Decimal | int, ctx: Context | None = None) -> Decimal:
    """Square root of a non-negative value under an explicit context."""
    x = _as_decimal(value)
    c = ctx or make_context()
    if x < 0:
        raise ValueError("decimal_sqrt of negative value")
    if x == 0:
        return c.plus(Decimal(0))
    return c.sqrt(x)


#: Iteration tripwire for Taylor series. With argument reduction every
#: call below converges in well under 100 terms (proven ratios); hitting
#: this bound means an internal defect, and raising is mandatory — a
#: silently truncated series must never be returned as correct.
_SERIES_MAX_TERMS = 10000


def _arctan_series(t: Decimal, ctx: Context) -> Decimal:
    """arctan(t) Taylor series, valid for |t| <= 1.

    Argument reduction: for |t| > 1/2 the half-angle identity
    ``arctan(t) = 2 * arctan(t / (1 + sqrt(1 + t^2)))`` is applied once
    first. The reduced argument satisfies |u| <= 1/(1+sqrt(2)) < 0.42
    (monotonic in |t|, maximum at |t| = 1), so series terms shrink by a
    ratio below 0.18 per step and the truncation threshold below is
    reached after a few dozen terms. Without this step, arguments near
    |t| = 1 converge as ~1/n per term and any fixed iteration budget
    silently returns a wrong value (observed: 5e-5 error at t = 1).

    Raises ArithmeticError if the series does not converge within
    ``_SERIES_MAX_TERMS`` terms (tripwire, never hit in practice).
    """
    half = ctx.divide(Decimal(1), Decimal(2))
    factor = 1
    if abs(t) > half:
        one_p_t2 = ctx.add(Decimal(1), ctx.multiply(t, t))
        u = ctx.divide(t, ctx.add(Decimal(1), ctx.sqrt(one_p_t2)))
        t = u
        factor = 2
    eps = Decimal(1).scaleb(-(ctx.prec + 2))
    total = ctx.plus(Decimal(0))
    t2 = ctx.multiply(t, t)
    power = t  # t^(2n+1), starts at n = 0
    n = 0
    sign = 1
    for _ in range(_SERIES_MAX_TERMS):
        term = ctx.divide(power, Decimal(2 * n + 1))
        total = ctx.add(total, term) if sign > 0 else ctx.subtract(total, term)
        power = ctx.multiply(power, t2)
        n += 1
        sign = -sign
        if abs(term) < eps:
            return ctx.multiply(Decimal(factor), total)
    raise ArithmeticError(
        f"arctan Taylor series failed to converge in {_SERIES_MAX_TERMS} "
        f"terms (|t| = {abs(t)} after reduction); refusing silent truncation"
    )


def _arctan(t: Decimal, ctx: Context) -> Decimal:
    """arctan(t) for any finite Decimal t, with argument reduction."""
    one = Decimal(1)
    if abs(t) > one:
        # arctan(t) = sign(t) * pi/2 - arctan(1/t)
        inv = ctx.divide(one, t)
        small = _arctan_series(inv, ctx)
        half_pi = ctx.divide(decimal_pi(), Decimal(2))
        return ctx.subtract(half_pi, small) if t > 0 else ctx.subtract(ctx.minus(half_pi), small)
    return _arctan_series(t, ctx)


_PI_CACHE: Decimal | None = None


def decimal_pi(ctx: Context | None = None) -> Decimal:
    """Pi to working precision via Machin's identity.

    pi = 16*arctan(1/5) - 4*arctan(1/239), evaluated with guard digits
    and rounded once to the caller's (or working) precision. The result
    is a high-precision approximation, never an exact object.
    """
    global _PI_CACHE
    if _PI_CACHE is None:
        g = make_context(_GUARD_DIGITS)
        a = _arctan_series(g.divide(Decimal(1), Decimal(5)), g)
        b = _arctan_series(g.divide(Decimal(1), Decimal(239)), g)
        full = g.subtract(g.multiply(Decimal(16), a), g.multiply(Decimal(4), b))
        _PI_CACHE = make_context().plus(full)
    if ctx is None:
        return _PI_CACHE
    return ctx.plus(_PI_CACHE)


def decimal_atan2(y: Decimal | int, x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """Four-quadrant arctangent, result in (-pi, pi] radians (approximate).

    Convention: atan2(0, 0) returns Decimal(0), matching widespread
    numerical practice; the true angle of 0+0j is mathematically
    undefined and callers must not read physical meaning into it.
    """
    yy = _as_decimal(y)
    xx = _as_decimal(x)
    c = ctx or make_context()
    if xx == 0 and yy == 0:
        return c.plus(Decimal(0))
    if xx == 0:
        half = c.divide(decimal_pi(), Decimal(2))
        return half if yy > 0 else c.minus(half)
    if yy == 0:
        return c.plus(Decimal(0)) if xx > 0 else decimal_pi(c)
    t = c.divide(yy, xx)
    base = _arctan(t, make_context(_GUARD_DIGITS))
    base = c.plus(base)
    if xx > 0:
        return base
    pi = decimal_pi(c)
    return c.add(base, pi) if yy > 0 else c.subtract(base, pi)


def _reduce_angle(x: Decimal, ctx: Context) -> Decimal:
    """Reduce x modulo 2*pi into [-pi, pi] under the given context."""
    pi = decimal_pi()
    two_pi = ctx.multiply(pi, Decimal(2))
    q = (ctx.divide(x, two_pi)).to_integral_value(rounding=ROUND_HALF_EVEN)
    r = ctx.subtract(x, ctx.multiply(q, two_pi))
    if r > pi:
        r = ctx.subtract(r, two_pi)
    elif r < ctx.minus(pi):
        r = ctx.add(r, two_pi)
    return r


def decimal_sin(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """Sine of x (radians, approximate) via range-reduced Taylor series."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    r = _reduce_angle(_as_decimal(x), g)
    eps = Decimal(1).scaleb(-(g.prec + 2))
    total = r
    term = r
    r2 = g.multiply(r, r)
    n = 1
    for _ in range(5000):
        term = g.multiply(term, r2)
        term = g.divide(term, Decimal((2 * n) * (2 * n + 1)))
        if n % 2 == 1:
            total = g.subtract(total, term)
        else:
            total = g.add(total, term)
        if abs(term) < eps:
            break
        n += 1
    return c.plus(total)


def decimal_cos(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """Cosine of x (radians, approximate) via range-reduced Taylor series."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    r = _reduce_angle(_as_decimal(x), g)
    eps = Decimal(1).scaleb(-(g.prec + 2))
    total = g.plus(Decimal(1))
    term = g.plus(Decimal(1))
    r2 = g.multiply(r, r)
    n = 1
    for _ in range(5000):
        term = g.multiply(term, r2)
        term = g.divide(term, Decimal((2 * n - 1) * (2 * n)))
        if n % 2 == 1:
            total = g.subtract(total, term)
        else:
            total = g.add(total, term)
        if abs(term) < eps:
            break
        n += 1
    return c.plus(total)
