"""P0-03/P0-04/P0-05: Decimal math edge battery + ambient-context isolation.

Covers sqrt/sin/cos/tan/atan2/log10/nth_root over edge values
(zeros, negatives, singularities, extremes) and asserts each result is
bit-identical under getcontext().prec = 6/28/50/100 — no precision-critical
path may read the ambient global Decimal context (same bug class as the
F8-D4 DecimalComplex.modulus() im==0 fast path).
"""
from decimal import Decimal, getcontext

import pytest

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.logarithm import (
    decimal_log10,
    decimal_nth_root,
)
from academic_core.domain.engineering.math.trig import (
    decimal_atan2,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context as make_trig_context,
)

PRECS = (6, 28, 50, 100)
TOL = Decimal("1e-30")

# Working-precision context for building reference multiples (2*pi, pi/2,
# ...). Bare Decimal operators (2 * pi, pi / 2) would round through the
# ambient global context and are banned in this file for that reason.
WC = make_trig_context()


def _mul(a: Decimal, b: Decimal) -> Decimal:
    return WC.multiply(a, b)


def _div(a: Decimal, b: Decimal) -> Decimal:
    return WC.divide(a, b)


def _close(a: Decimal, b: Decimal) -> bool:
    scale = b.copy_abs()
    if scale < 1:
        scale = Decimal(1)
    return (a - b).copy_abs() <= TOL * scale


def _run_under_all_precs(fn):
    """Run fn() under each ambient prec; return list of results."""
    old = getcontext().prec
    try:
        out = []
        for p in PRECS:
            getcontext().prec = p
            out.append(fn())
        return out
    finally:
        getcontext().prec = old


def test_sqrt_edges_and_context_isolation():
    assert decimal_sqrt(Decimal(0)) == Decimal(0)
    assert decimal_sqrt(Decimal(1)) == Decimal(1)
    assert decimal_sqrt(Decimal(4)) == Decimal(2)
    assert _close(decimal_sqrt(Decimal(2)), Decimal("1.41421356237309504880168872421"))
    # Exact powers of ten via context scaleb (bare ** would round
    # through the ambient global context).
    assert _close(
        decimal_sqrt(WC.scaleb(Decimal(1), 100)), WC.scaleb(Decimal(1), 50)
    )
    assert _close(
        decimal_sqrt(WC.scaleb(Decimal(1), -100)), WC.scaleb(Decimal(1), -50)
    )
    with pytest.raises(ValueError):
        decimal_sqrt(Decimal(-1))
    results = _run_under_all_precs(lambda: decimal_sqrt(Decimal(2)))
    assert all(r == results[0] for r in results)


def test_sin_edges_and_context_isolation():
    pi = decimal_pi()
    half_pi = _div(pi, Decimal(2))
    assert decimal_sin(Decimal(0)).copy_abs() < TOL
    assert _close(decimal_sin(half_pi), Decimal(1))
    assert decimal_sin(pi).copy_abs() < TOL
    assert _close(decimal_sin(_mul(pi, Decimal(2))), Decimal(0))
    assert _close(decimal_sin(WC.minus(half_pi)), Decimal(-1))
    # Large and tiny arguments must not crash or depend on ambient prec.
    for x in (Decimal(10), Decimal(1000), Decimal("1e-30"), Decimal("-1e-30")):
        results = _run_under_all_precs(lambda: decimal_sin(x))
        assert all(r == results[0] for r in results)
    results = _run_under_all_precs(lambda: decimal_sin(_div(pi, Decimal(6))))
    assert all(r == results[0] for r in results)
    assert _close(results[0], Decimal("0.5"))


def test_cos_edges_and_context_isolation():
    pi = decimal_pi()
    assert _close(decimal_cos(Decimal(0)), Decimal(1))
    assert decimal_cos(_div(pi, Decimal(2))).copy_abs() < TOL
    assert _close(decimal_cos(pi), Decimal(-1))
    for x in (Decimal(10), Decimal(1000), Decimal("1e-30")):
        results = _run_under_all_precs(lambda: decimal_cos(x))
        assert all(r == results[0] for r in results)


def test_tan_edges_and_context_isolation():
    pi = decimal_pi()
    assert _close(_tan(Decimal(0)), Decimal(0))
    assert _close(_tan(_div(pi, Decimal(4))), Decimal(1))
    assert _close(_tan(WC.minus(_div(pi, Decimal(4)))), Decimal(-1))
    from academic_core.domain.engineering.equations import EquationError

    with pytest.raises(EquationError):
        _tan_checked(_div(pi, Decimal(2)))
    results = _run_under_all_precs(lambda: _tan(Decimal(1)))
    assert all(r == results[0] for r in results)


def _tan(x: Decimal) -> Decimal:
    from academic_core.domain.engineering.math.trig import make_context

    ctx = make_context()
    return ctx.divide(decimal_sin(x, ctx), decimal_cos(x, ctx))


def _tan_checked(x: Decimal) -> Decimal:
    """tan through the equations.py domain guard (singularities raise)."""
    from academic_core.domain.engineering.equations import _apply_func
    from academic_core.domain.engineering.units import (
        DIMENSIONLESS,
        Quantity,
        Unit,
    )

    one = Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
    return _apply_func("tan", Quantity(x, one)).to_base()


def test_atan2_quadrants_and_context_isolation():
    pi = decimal_pi()
    q = _div(pi, Decimal(4))
    assert _close(decimal_atan2(Decimal(1), Decimal(1)), q)
    assert _close(decimal_atan2(Decimal(1), Decimal(-1)), _mul(q, Decimal(3)))
    assert _close(decimal_atan2(Decimal(-1), Decimal(-1)), WC.minus(_mul(q, Decimal(3))))
    assert _close(decimal_atan2(Decimal(-1), Decimal(1)), WC.minus(q))
    assert decimal_atan2(Decimal(0), Decimal(0)) == Decimal(0)
    assert _close(decimal_atan2(Decimal(1), Decimal(0)), _mul(q, Decimal(2)))
    assert _close(decimal_atan2(Decimal(-1), Decimal(0)), WC.minus(_mul(q, Decimal(2))))
    results = _run_under_all_precs(lambda: decimal_atan2(Decimal(2), Decimal(3)))
    assert all(r == results[0] for r in results)


def test_log10_edges_and_context_isolation():
    assert decimal_log10(Decimal(1)) == Decimal(0)
    assert decimal_log10(Decimal(10)) == Decimal(1)
    assert decimal_log10(Decimal(100)) == Decimal(2)
    assert decimal_log10(Decimal("0.1")) == Decimal(-1)
    assert decimal_log10(Decimal("0.01")) == Decimal(-2)
    assert _close(decimal_log10(WC.scaleb(Decimal(1), 100)), Decimal(100))
    assert _close(decimal_log10(WC.scaleb(Decimal(1), -100)), Decimal(-100))
    with pytest.raises(ValueError):
        decimal_log10(Decimal(0))
    with pytest.raises(ValueError):
        decimal_log10(Decimal(-5))
    results = _run_under_all_precs(lambda: decimal_log10(Decimal("12345.6789")))
    assert all(r == results[0] for r in results)


def test_nth_root_edges_and_context_isolation():
    assert decimal_nth_root(Decimal(0), 2) == Decimal(0)
    assert decimal_nth_root(Decimal(1), 2) == Decimal(1)
    assert _close(decimal_nth_root(Decimal(27), 3), Decimal(3))
    assert _close(decimal_nth_root(Decimal(16), 4), Decimal(2))
    assert decimal_nth_root(Decimal("5.5"), 1) == Decimal("5.5")
    assert _close(
        decimal_nth_root(Decimal("0.001"), 3), Decimal("0.1")
    )
    assert _close(
        decimal_nth_root(WC.scaleb(Decimal(1), 100), 10),
        WC.scaleb(Decimal(1), 10),
    )
    with pytest.raises(ValueError):
        decimal_nth_root(Decimal(-4), 2)
    with pytest.raises(ValueError):
        decimal_nth_root(Decimal(4), 0)
    results = _run_under_all_precs(lambda: decimal_nth_root(Decimal(2), 3))
    assert all(r == results[0] for r in results)


def test_f8d4_modulus_keeps_precision_under_prec_28():
    """P0-05: Decimal with >28 digits through modulus() at prec=28."""
    old = getcontext().prec
    try:
        getcontext().prec = 28
        big_re = Decimal("3.14159265358979323846264338327950288419716939937510")
        result = DecimalComplex(big_re, Decimal(0)).modulus()
        assert result == big_re.copy_abs()
    finally:
        getcontext().prec = old
