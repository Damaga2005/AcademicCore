"""Equations: parsing, safe evaluation, dimensional analysis, no eval."""
from decimal import Decimal

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
