from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig


def p(text: str):
    return mx.parse(text)


def test_pythagorean_identity():
    assert mx.pretty(trig.simplify(p("sin(x)^2 + cos(x)^2"))) == "1"


def test_pythagorean_complement():
    assert mx.pretty(trig.simplify(p("1-cos(x)^2"))) == "sin(x)^2"


def test_parity():
    assert mx.pretty(trig.simplify(p("sin(-x)"))) == "-sin(x)"
    assert mx.pretty(trig.simplify(p("cos(-x)"))) == "cos(x)"


def test_tangent_cotangent_ratios():
    assert mx.pretty(trig.simplify(p("sin(x)/cos(x)"))) == "tan(x)"
    assert mx.pretty(trig.simplify(p("cos(x)/sin(x)"))) == "cot(x)"


def test_double_angle():
    assert mx.pretty(trig.simplify(p("2*sin(x)*cos(x)"))) == "sin(2*x)"


def test_numeric_evaluation_of_reciprocals():
    assert abs(mx.evaluate(p("sec(pi/4)")).real - 2 ** 0.5) < 1e-12
    assert abs(mx.evaluate(p("csc(pi/4)")).real - 2 ** 0.5) < 1e-12
    assert abs(mx.evaluate(p("cot(pi/4)")).real - 1) < 1e-12
