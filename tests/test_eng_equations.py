"""Equations: parsing, safe evaluation, dimensional analysis, no eval."""
from decimal import Decimal, getcontext

import pytest

from academic_core.domain.engineering.equations import (
    EquationError, evaluate, parse_equation,
)
from academic_core.domain.engineering.units import Quantity, UnitError, parse_quantity

EvalFailure = (EquationError, UnitError)  # both controlled, never raw


def env(**kw):
    return {k: parse_quantity(v) for k, v in kw.items()}


def test_parse_collects_names_and_preserves_source():
    eq = parse_equation("Vout = Vi * R2 / (R1 + R2)")
    assert eq.output == "Vout" and eq.source == "Vout = Vi * R2 / (R1 + R2)"
    assert eq.variables == ("R1", "R2", "Vi")


def test_ohm_and_power():
    assert evaluate(parse_equation("I = V / R"),
                    env(V="5 V", R="1 kohm")).format() == "0.005 A"
    assert evaluate(parse_equation("P = V ** 2 / R"),
                    env(V="12 V", R="100 ohm")).convert_to("W").value == Decimal("1.44")


def test_dimensional_validation():
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("X = V + I"), env(V="5 V", I="2 A"))
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("I = V / R"), env(V="5 V"))  # missing R
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("X = V / 0"), env(V="5 V"))
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("X = foo(5 V)"), {})
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("X = V ** R"), env(V="5 V", R="2 ohm"))
    with pytest.raises(EvalFailure):
        evaluate(parse_equation("X = sqrt(-4 V)"), {})


def test_abs_func_ignores_ambient_decimal_context():
    """Regression test: abs() in _apply_func used to be a bare builtin.

    ``abs(Decimal)`` implicitly rounds through the ambient/global
    decimal context (default 28 significant digits) rather than an
    explicit context, unlike every sibling branch of ``_apply_func``
    (sin/cos/tan/exp/log/log10), which threads its own working-precision
    Context explicitly. The fix uses ``Decimal.copy_abs()`` (sign flip
    only, no rounding). This test degrades the ambient context to its
    default 28 digits and checks a >28-digit value survives abs() whole.
    """
    old = getcontext().prec
    try:
        getcontext().prec = 28
        big = "-1.2345678901234567890123456789012345678901234567890"  # 50 sig digits
        q = evaluate(parse_equation("X = abs(V)"), env(V=f"{big} V"))
        assert len(q.value.as_tuple().digits) > 28
        assert q.value == Decimal(big).copy_abs()
    finally:
        getcontext().prec = old


def test_no_eval_no_exec_no_imports():
    for evil in ("X = __import__('os').system('x')", "X = V.attr",
                 "X = eval('1')", "X = 5 V @ 2", "X = `id`", "X = "):
        with pytest.raises(EvalFailure):
            parse_equation(evil)
    # whitelisted funcs only (sqrt needs square dimensions)
    assert evaluate(parse_equation("X = sqrt(9)"), {}).value == 3
    assert evaluate(parse_equation("X = sqrt(V ** 2)"), env(V="3 V")).format() == "3 V"
    with pytest.raises(EquationError):
        parse_equation("X = sqrt")
    with pytest.raises(EquationError):
        evaluate(parse_equation("X = log(-1)"), {})
    import inspect
    import academic_core.domain.engineering.equations as m
    src = inspect.getsource(m)
    assert "eval(" not in src and "exec(" not in src


def test_sqrt_func_ignores_ambient_decimal_context():
    """Regression test (audit finding, fixed): the ``sqrt`` branch of
    ``_apply_func`` used to call the bare ``Decimal.sqrt()`` instance
    method on ``arg.to_base()`` with no context argument, rounding
    through ``decimal.getcontext()`` (default 28 significant digits) --
    the same bug class already fixed for ``abs()`` (see
    test_abs_func_ignores_ambient_decimal_context above) and for
    DecimalComplex.modulus()'s im==0 fast path. It now uses
    ``make_context().sqrt(...)``, like every sibling branch
    (sin/cos/tan/exp/log/log10). This test degrades the ambient context
    to its default 28 digits and pins that sqrt(2) still comes back at
    (approximately) the module's 50-digit WORKING_PRECISION.
    """
    old = getcontext().prec
    try:
        getcontext().prec = 28
        q = evaluate(parse_equation("X = sqrt(V)"), env(V="2"))
        # WORKING_PRECISION is 50; a healthy (context-independent) sqrt
        # should return far more than 28 significant digits here.
        assert len(q.value.as_tuple().digits) > 28, (
            f"sqrt(2) came back with only {len(q.value.as_tuple().digits)} "
            f"significant digits ({q.value!r}) -- it silently rounded "
            "through the ambient global Decimal context (28 digits) "
            "instead of the module's own explicit working-precision "
            "Context, exactly like the already-fixed abs() bug."
        )
    finally:
        getcontext().prec = old
