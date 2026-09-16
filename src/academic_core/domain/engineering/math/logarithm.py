"""Decimal logarithm and integer-root primitives (F8-D6).

Pure-``Decimal`` implementations in the D1 numeric model: no ``math``,
no ``cmath``, no ``float``/``complex``, no numpy. Every routine builds
its own explicit ``decimal.Context`` (working precision plus guard
digits) and never reads or mutates the ambient global context.

Two primitives, one coherent source:

* ``decimal_nth_root(x, n)`` — Newton's method for ``x**(1/n)``,
  ``x > 0``. Used for log-grid ratios ``r = 10**(1/ppd)``. Starting
  point ``x0 = 1`` for ``x < 1`` else ``x0 = x`` satisfies
  ``x0**n >= x``, hence monotone convergence from above; both the step
  and the residual ``|y**n - x|`` are verified before returning.
* ``decimal_log10(x)`` — ``x = m * 10**e`` decomposition (exact,
  ``m`` in ``[1, 10)``) with ``log10(x) = e + ln(m)/ln(10)``; ``ln``
  via the atanh series ``ln(m) = 2*S((m-1)/(m+1))``; ``ln(10)`` from the
  same series as ``ln(2) + ln(5)`` (fast arguments ``1/3``, ``1/2``... as
  ``(2-1)/(2+1)``, ``(5-1)/(5+1)``), cached per precision. Used for dB
  magnitudes.

Iteration caps are tripwires that raise ``ArithmeticError`` — a series
or Newton loop that exhausts its budget never returns a silently
truncated value (D1 ``trig`` precedent).
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN

WORKING_PRECISION = 50

#: Guard digits for internal series/Newton evaluation (same margin as
#: D1 ``trig``; local constant to avoid coupling to a private name).
_GUARD_DIGITS = 15

#: Iteration tripwires (never hit in practice; see module docstring).
_MAX_NEWTON_ITERATIONS = 1000
_MAX_SERIES_TERMS = 10000


def make_context(extra: int = 0) -> Context:
    """Fresh explicit context (never the ambient global one)."""
    return Context(prec=WORKING_PRECISION + extra, rounding=ROUND_HALF_EVEN)


def _as_decimal(value: int | Decimal) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("bool is not an accepted numeric input")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    raise TypeError(f"expected int or Decimal, got {type(value).__name__}")


def _check_n(n: int) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"root index must be an int, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"root index must be >= 1, got {n}")
    return n


def decimal_nth_root(x: Decimal | int, n: int,
                     ctx: Context | None = None) -> Decimal:
    """Principal real ``x**(1/n)`` for ``x >= 0``, integer ``n >= 1``.

    Newton's method on ``y**n - x = 0`` from above (``x0 = 1`` for
    ``x < 1`` else ``x0 = x``, so ``x0**n >= x`` and convergence is
    monotone). Returns only when both the step and the residual
    ``|y**n - x|`` clear explicit tolerances derived from the working
    precision; otherwise raises ``ArithmeticError``.
    """
    n = _check_n(n)
    xv = _as_decimal(x)
    c = ctx or make_context()
    if xv < 0:
        raise ValueError("decimal_nth_root of negative value")
    if xv == 0:
        return c.plus(Decimal(0))
    if n == 1:
        return c.plus(xv)
    g = make_context(_GUARD_DIGITS)
    # Step gate: Newton converges quadratically, so a threshold a few
    # ulps above the guard-precision rounding floor is crossed in a
    # single step once close — while a threshold AT the floor (or the
    # series-style prec+2 used for genuinely vanishing Taylor terms)
    # would stall forever on rounding noise. The residual gate below is
    # the real correctness check; the step gate only stops the loop.
    eps = Decimal(1).scaleb(5 - g.prec)
    # Residual gate: y**n needs n-1 rounded multiplications at guard
    # precision, so the checkable residual floor is ~n ulps of |x|.
    # Anything tighter would be unprovable (and would trip on its own
    # rounding); anything looser would weaken the guarantee. The final
    # result is still rounded to the caller precision far above this.
    scale = xv.copy_abs()
    if scale < 1:
        scale = Decimal(1)
    tol = g.multiply(g.multiply(Decimal(n), Decimal(10).scaleb(2 - g.prec)),
                     scale)
    y = g.plus(Decimal(1)) if xv < 1 else g.plus(xv)
    nn = Decimal(n)
    for _ in range(_MAX_NEWTON_ITERATIONS):
        y_pow = g.power(y, n - 1) if n > 1 else g.plus(Decimal(1))
        y_new = g.divide(
            g.add(g.multiply(Decimal(n - 1), y), g.divide(xv, y_pow)),
            nn,
        )
        step = abs(g.subtract(y_new, y))
        y = y_new
        if step < eps:
            if abs(g.subtract(g.power(y, n), xv)) <= tol:
                return c.plus(y)
            break
    raise ArithmeticError(
        f"decimal_nth_root failed to converge for x={xv}, n={n}; "
        f"refusing silent truncation"
    )


def _atanh_series(t: Decimal, ctx: Context) -> Decimal:
    """S(t) = t + t^3/3 + t^5/5 + ... ; caller keeps |t| well below 1."""
    eps = Decimal(1).scaleb(-(ctx.prec + 2))
    total = ctx.plus(Decimal(0))
    t2 = ctx.multiply(t, t)
    power = t
    k = 0
    for _ in range(_MAX_SERIES_TERMS):
        term = ctx.divide(power, Decimal(2 * k + 1))
        total = ctx.add(total, term)
        power = ctx.multiply(power, t2)
        k += 1
        if abs(term) < eps:
            return total
    raise ArithmeticError(
        "atanh series failed to converge; refusing silent truncation"
    )


def _ln_of(m: Decimal, ctx: Context) -> Decimal:
    """ln(m) for m > 0 via t = (m-1)/(m+1), ln = 2*S(t)."""
    t = ctx.divide(ctx.subtract(m, Decimal(1)), ctx.add(m, Decimal(1)))
    return ctx.multiply(Decimal(2), _atanh_series(t, ctx))


_LN10_CACHE: dict[int, Decimal] = {}


def decimal_ln10(ctx: Context | None = None) -> Decimal:
    """ln(10) = ln(2) + ln(5) from the shared atanh series.

    Single coherent source for every logarithm here; cached per
    precision (explicit-precision key, deterministic, no ambient state).
    """
    c = ctx or make_context()
    hit = _LN10_CACHE.get(c.prec)
    if hit is not None:
        return c.plus(hit)
    g = make_context(_GUARD_DIGITS)
    value = g.add(_ln_of(Decimal(2), g), _ln_of(Decimal(5), g))
    _LN10_CACHE[g.prec] = value
    return c.plus(value)


def decimal_log10(x: Decimal | int, ctx: Context | None = None) -> Decimal:
    """log10(x) for x > 0: exact ``x = m * 10**e`` split, ``m`` in [1, 10).

    ``log10(x) = e + ln(m)/ln(10)``; ``log10(1)`` is exactly ``0`` (the
    series term vanishes and ``e`` is ``0``). Raises ``ValueError`` for
    ``x <= 0``.
    """
    xv = _as_decimal(x)
    c = ctx or make_context()
    if xv <= 0:
        raise ValueError(f"decimal_log10 domain is x > 0, got {xv}")
    g = make_context(_GUARD_DIGITS)
    e = xv.adjusted()
    m = xv.scaleb(-e)
    if m == 1:
        return c.plus(Decimal(e))
    ln_m = _ln_of(m, g)
    ln10 = decimal_ln10(g)
    return c.plus(g.add(Decimal(e), g.divide(ln_m, ln10)))
