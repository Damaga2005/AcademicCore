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
    """Return a fresh explicit context (never the ambient global one).

    Always constructs a new ``Context`` object, even for ``extra == 0``.
    ``decimal.Context`` construction is cheap, and never sharing a single
    instance means no caller can ever contaminate another's rounding
    state via ``.traps``/``.flags`` mutation, even latently.
    """
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
    # copy_abs() flips the sign bit only: no rounding, never touches the
    # ambient global decimal context. Bare abs(t) would round through
    # getcontext() (same bug class as DecimalComplex.modulus()).
    if t.copy_abs() > half:
        one_p_t2 = ctx.add(Decimal(1), ctx.multiply(t, t))
        u = ctx.divide(t, ctx.add(Decimal(1), ctx.sqrt(one_p_t2)))
        t = u
        factor = 2
    eps = ctx.scaleb(Decimal(1), -(ctx.prec + 2))
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
        if term.copy_abs() < eps:
            return ctx.multiply(Decimal(factor), total)
    raise ArithmeticError(
        f"arctan Taylor series failed to converge in {_SERIES_MAX_TERMS} "
        f"terms (|t| = {t.copy_abs()} after reduction); refusing silent truncation"
    )


def _arctan(t: Decimal, ctx: Context) -> Decimal:
    """arctan(t) for any finite Decimal t, with argument reduction."""
    one = Decimal(1)
    if t.copy_abs() > one:
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
    # Context-explicit integral value: the Decimal method without a
    # context argument would round through the ambient global context.
    q = ctx.to_integral_value(ctx.divide(x, two_pi))
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
    eps = g.scaleb(Decimal(1), -(g.prec + 2))
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
        if term.copy_abs() < eps:
            break
        n += 1
    return c.plus(total)


def decimal_cos(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """Cosine of x (radians, approximate) via range-reduced Taylor series."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    r = _reduce_angle(_as_decimal(x), g)
    eps = g.scaleb(Decimal(1), -(g.prec + 2))
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
        if term.copy_abs() < eps:
            break
        n += 1
    return c.plus(total)


#: The reciprocals of the circular functions, and the inverse circular
#: functions, closed over the certified kernels above. Each one is written as
#: the identity that defines it OUT of ``sin``/``cos``, rather than as its own
#: series, so there is exactly one implementation of each idea in this module
#: and a reader can see which reduction a number went through.
#:
#: Domain errors raise ``ValueError`` whose text states the CONDITION and never
#: the function's own name («outside the range |x| <= 1», not «asin domain»).
#: Naming the function is the caller's job: these kernels nest — ``acos`` is
#: built on ``asin`` — so a message that named the innermost function would
#: report a call the reader never made and send them to the wrong one.
def _is_zero(value: Decimal) -> bool:
    """Is ``value`` indistinguishable from zero at working precision?

    A decimal Taylor series evaluated at exactly 0 returns exactly 0, but
    evaluated at a pole it returns the residue of the series, which is small
    and NOT zero. Testing ``== 0`` therefore lets ``sec(pi/2)`` and
    ``csc(pi)`` return an enormous number instead of refusing: the caller gets
    a plausible-looking value built on a denominator that had no digits left.

    The threshold is measured at the module's ``WORKING_PRECISION`` and NOT at
    the guard precision the series itself runs in. That distinction is load
    bearing: with an exact 50-digit argument for pi/2, ``cos`` leaves a residue
    near 1e-60, which is below a 1e-48 threshold and so refuses — but it is
    ABOVE the 1e-63 a guard-precision threshold would use, and the guard
    threshold lets the pole straight through. It is also the criterion ``tan``
    already applies in ``equations``, and ``sec``/``csc``/``cot`` refusing at
    exactly the points where ``tan`` refuses is the whole point.
    """
    c = make_context()
    return value.copy_abs() < c.scaleb(Decimal(1), -(c.prec - 2))


def decimal_sec(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """sec(x) = 1/cos(x)."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    cos_x = decimal_cos(_as_decimal(x), g)
    if _is_zero(cos_x):
        raise ValueError(f"cos(x) is 0 to working precision near {cos_x}")
    return c.plus(g.divide(Decimal(1), cos_x))


def decimal_csc(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """csc(x) = 1/sin(x)."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    sin_x = decimal_sin(_as_decimal(x), g)
    if _is_zero(sin_x):
        raise ValueError(f"sin(x) is 0 to working precision near {sin_x}")
    return c.plus(g.divide(Decimal(1), sin_x))


def decimal_cot(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """cot(x) = cos(x)/sin(x).

    The quotient, and not ``1/tan(x)``: ``tan`` is itself guarded as a
    division by a near-zero cosine, so routing through it would raise on a
    point where cot is perfectly well defined.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    sin_x = decimal_sin(v, g)
    if _is_zero(sin_x):
        raise ValueError(f"sin(x) is 0 to working precision near {sin_x}")
    return c.plus(g.divide(decimal_cos(v, g), sin_x))


def decimal_atan(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """arctan(x) in (-pi/2, pi/2), by the certified argument reduction.

    ``decimal_atan2`` is the four-quadrant version and would answer the same
    thing for an x of 1, but going through it would read as though this were
    a quadrant question. It is not: one argument, one interval.
    """
    c = ctx or make_context()
    return c.plus(_arctan(_as_decimal(x), make_context(_GUARD_DIGITS)))


def decimal_asin(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """arcsin(x) for |x| <= 1, as arctan2(x, sqrt(1 - x^2)).

    Two choices, both about not throwing digits away:

    - The radicand is ``(1-x)*(1+x)`` and not ``1 - x*x``. Near |x| = 1 the
      subtraction of two near-equal numbers is where the last digits go, and
      they are exactly the digits that decide the size of the answer.
    - The result is an ``arctan2``, not an ``arctan(x/sqrt(...))``. At |x| = 1
      the second form divides by zero at a point where the answer is simply
      pi/2, which is a domain error the caller would report as if the input
      were out of range. ``arctan2(+-1, 0)`` is +-pi/2.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v.copy_abs() > 1:
        raise ValueError(f"{v} is outside the range |x| <= 1")
    one = Decimal(1)
    radicand = g.multiply(g.subtract(one, v), g.add(one, v))
    return c.plus(decimal_atan2(v, g.sqrt(radicand), g))


def decimal_acos(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """arccos(x) for |x| <= 1, as pi/2 - arcsin(x).

    Written as that subtraction, and not as an ``arctan2`` of its own: the
    two share one reduction and one ``arcsin``, and the identity is exact.
    The range check belongs to ``arcsin`` and is left to it — a second copy
    here would be a second place for the bound to be wrong.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    half_pi = g.divide(decimal_pi(g), Decimal(2))
    return c.plus(g.subtract(half_pi, decimal_asin(x, g)))


def decimal_sinh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """sinh(x) = (exp(x) - exp(-x))/2.

    Both exponentials are taken in a guard context BEFORE the subtraction.
    For small x that subtraction is the only place digits are lost, and there
    the result is small too, so the relative error stays put.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    return c.plus(g.divide(g.subtract(g.exp(v), g.exp(g.minus(v))), Decimal(2)))


def decimal_cosh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """cosh(x) = (exp(x) + exp(-x))/2."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    return c.plus(g.divide(g.add(g.exp(v), g.exp(g.minus(v))), Decimal(2)))


def decimal_tanh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """tanh(x), by two formulas split at |x| = 1.

    Near zero it is ``sinh/cosh``: both are small or both near 1, and the
    quotient is exact to working precision. Away from zero it is
    ``1 - 2/(exp(2x)+1)``: there ``sinh`` and ``cosh`` are two enormous
    numbers whose quotient is 1 to far more digits than anyone asked for, and
    the subtraction loses all of them.

    A single formula cannot do both. ``1 - 2/(exp(2x)+1)`` at x = 0.001 is
    1 - 0.9990005, and the answer it loses is the one digit the reader came
    for.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v.copy_abs() <= 1:
        return c.plus(g.divide(decimal_sinh(v, g), decimal_cosh(v, g)))
    den = g.add(g.exp(g.multiply(v, Decimal(2))), Decimal(1))
    return c.plus(g.subtract(Decimal(1), g.divide(Decimal(2), den)))


def decimal_coth(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """coth(x) = 1/tanh(x), undefined at x = 0.

    The reciprocal of ``tanh`` and not ``cosh/sinh``, because ``tanh`` is the
    one of the two computed stably across the whole range.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v == 0:
        raise ValueError("undefined at x = 0, where tanh(x) is 0")
    return c.plus(g.divide(Decimal(1), decimal_tanh(v, g)))


def decimal_sech(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """sech(x) = 2/(exp(x) + exp(-x)).

    Not ``1/cosh``: for large |x| that divides 1 by a number that has already
    overflowed the working context, and reports a domain error where the true
    answer is merely very small.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    return c.plus(g.divide(Decimal(2), g.add(g.exp(v), g.exp(g.minus(v)))))


def decimal_csch(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """csch(x) = 2/(exp(x) - exp(-x)), undefined at x = 0."""
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v == 0:
        raise ValueError("undefined at x = 0, where sinh(x) is 0")
    return c.plus(g.divide(Decimal(2), g.subtract(g.exp(v), g.exp(g.minus(v)))))


def decimal_asinh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """asinh(x) = sign(x) * ln(|x| + sqrt(x^2 + 1)).

    The sign is applied OUTSIDE the logarithm. Inside, the formula for x < 0
    is ln(-|x| + sqrt(x^2+1)), and those two terms agree to working precision
    for every large negative x: the logarithm returns 0 where the true answer
    is large and negative. Factoring the sign out is the whole difference
    between the identity and the identity plus a silent zero.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    radicand = g.add(g.multiply(v, v), Decimal(1))
    total = g.ln(g.add(v.copy_abs(), g.sqrt(radicand)))
    return c.plus(g.minus(total) if v < 0 else total)


def decimal_acosh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """acosh(x) = ln(x + sqrt(x^2 - 1)), for x >= 1.

    No absolute value and no sign: the range already excludes every negative
    argument, so a formula that handled one would be handling a case that
    cannot arrive.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v < 1:
        raise ValueError(f"{v} is below the range x >= 1")
    radicand = g.subtract(g.multiply(v, v), Decimal(1))
    return c.plus(g.ln(g.add(v, g.sqrt(radicand))))


def decimal_atanh(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """atanh(x) = ln((1+x)/(1-x))/2, for |x| < 1.

    The ratio is taken before the logarithm, never as ln(1+x) - ln(1-x):
    that difference cancels to nothing near the ends of the interval, which
    is the only part of it anyone uses.
    """
    c = ctx or make_context()
    g = make_context(_GUARD_DIGITS)
    v = _as_decimal(x)
    if v.copy_abs() >= 1:
        raise ValueError(f"{v} is on or outside the range |x| < 1")
    ratio = g.divide(g.add(Decimal(1), v), g.subtract(Decimal(1), v))
    return c.plus(g.divide(g.ln(ratio), Decimal(2)))
