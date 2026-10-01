# SPDX-License-Identifier: MIT
"""MATH_LAB: exact trigonometric identities and canonical transformations.

This module is deliberately rule-based: identities are structural rewrites on
the expression AST, never numerical guesses. It is the first trig rule set
used by simplification; calculus and numerical verification can reuse it.
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx

MAX_PASSES = 12


def _num(n: int) -> mx.Num:
    return mx.Num(Fraction(n))


def _call(name: str, arg: mx.Expr) -> mx.Call:
    return mx.Call(name, (arg,))


def _pow(base: mx.Expr, n: int) -> mx.Expr:
    return mx.Pow(base, _num(n))


def _is_call(e: mx.Expr, name: str) -> bool:
    return isinstance(e, mx.Call) and e.name == name and len(e.args) == 1


def _arg(e: mx.Expr, name: str) -> mx.Expr | None:
    return e.args[0] if _is_call(e, name) else None


def _neg_arg(e: mx.Expr) -> mx.Expr | None:
    if isinstance(e, mx.Neg):
        return e.arg
    return None


def _same(a: mx.Expr, b: mx.Expr) -> bool:
    return a == b


def _mul2(e: mx.Expr) -> mx.Expr | None:
    if isinstance(e, mx.Mul):
        if isinstance(e.left, mx.Num) and e.left.value == 2:
            return e.right
        if isinstance(e.right, mx.Num) and e.right.value == 2:
            return e.left
    return None


def _add_terms(e: mx.Expr) -> tuple[mx.Expr, mx.Expr] | None:
    if isinstance(e, mx.Add):
        return e.left, e.right
    return None


def _sub_terms(e: mx.Expr) -> tuple[mx.Expr, mx.Expr] | None:
    if isinstance(e, mx.Sub):
        return e.left, e.right
    return None


def _sq_call(e: mx.Expr, name: str) -> mx.Expr | None:
    if isinstance(e, mx.Pow) and e.exponent == _num(2):
        return _arg(e.base, name)
    return None


def _match_sq_pair(a: mx.Expr, b: mx.Expr, first: str, second: str) -> mx.Expr | None:
    xa, xb = _sq_call(a, first), _sq_call(b, second)
    if xa is not None and xb is not None and _same(xa, xb):
        return xa
    xa, xb = _sq_call(a, second), _sq_call(b, first)
    if xa is not None and xb is not None and _same(xa, xb):
        return xa
    return None


def _rewrite(e: mx.Expr) -> mx.Expr:
    # recurse first
    if isinstance(e, mx.Neg):
        arg = _rewrite(e.arg)
        # parity
        for odd in ("sin", "tan", "cot", "csc", "asin", "atan", "sinh", "tanh"):
            x = _arg(arg, odd)
            if x is not None:
                return _call(odd, mx.Neg(x))
        for even in ("cos", "sec", "acos", "cosh"):
            x = _arg(arg, even)
            if x is not None:
                return _call(even, x)
        return mx.Neg(arg)

    if isinstance(e, mx.Call):
        args = tuple(_rewrite(a) for a in e.args)
        e = mx.Call(e.name, args)
        if e.name in {"sin", "cos", "tan", "cot", "sec", "csc"}:
            x = e.args[0]
            # cofunction shifts
            if isinstance(x, mx.Sub):
                # sin(pi/2-x)=cos(x), cos(pi/2-x)=sin(x)
                if isinstance(x.left, mx.Div) and x.left.left == mx.Const("pi") and x.left.right == _num(2):
                    if e.name == "sin":
                        return _call("cos", x.right)
                    if e.name == "cos":
                        return _call("sin", x.right)
            # period 2pi for a syntactically explicit full period
            if isinstance(x, mx.Add) and isinstance(x.right, mx.Mul):
                if x.right.left == _num(2) and x.right.right == mx.Const("pi"):
                    return _call(e.name, x.left)
        return e

    if isinstance(e, mx.Pow):
        return mx.Pow(_rewrite(e.base), _rewrite(e.exponent))

    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        left = _rewrite(e.left)
        right = _rewrite(e.right)
        e = type(e)(left, right)

        # sin²(x)+cos²(x)=1
        if isinstance(e, mx.Add):
            x = _match_sq_pair(e.left, e.right, "sin", "cos")
            if x is not None and isinstance(e.left, mx.Pow) and isinstance(e.right, mx.Pow):
                return _num(1)

            # 1 - sin²(x) = cos²(x), and 1 - cos²(x) = sin²(x)
        if isinstance(e, mx.Sub):
            if e.left == _num(1):
                if isinstance(e.right, mx.Pow) and isinstance(e.right.exponent, mx.Num) and e.right.exponent.value == 2:
                    if _is_call(e.right.base, "sin"):
                        return _pow(_call("cos", e.right.base.args[0]), 2)
                    if _is_call(e.right.base, "cos"):
                        return _pow(_call("sin", e.right.base.args[0]), 2)

        # tan = sin/cos, cot = cos/sin, sec/csc reciprocals
        if isinstance(e, mx.Div):
            sa, ca = _arg(e.left, "sin"), _arg(e.right, "cos")
            if sa is not None and ca is not None and sa == ca:
                return _call("tan", sa)
            ca, sa = _arg(e.left, "cos"), _arg(e.right, "sin")
            if ca is not None and sa is not None and ca == sa:
                return _call("cot", ca)

        if isinstance(e, mx.Add):
            # 1 + tan²x = sec²x ; 1 + cot²x = csc²x
            for fn, recip in (("tan", "sec"), ("cot", "csc")):
                terms = (e.left, e.right)
                for a, b in (terms, (terms[1], terms[0])):
                    if a == _num(1) and isinstance(b, mx.Pow) and b.exponent == _num(2) and _is_call(b.base, fn):
                        return _pow(_call(recip, b.base.args[0]), 2)

        # product-to-double-angle: 2 sin x cos x = sin 2x
        factors = []
        def collect_mul(node):
            if isinstance(node, mx.Mul):
                collect_mul(node.left); collect_mul(node.right)
            else:
                factors.append(node)
        collect_mul(e)
        if len(factors) == 3 and any(isinstance(x, mx.Num) and x.value == 2 for x in factors):
            trig = [x for x in factors if not (isinstance(x, mx.Num) and x.value == 2)]
            if len(trig) == 2 and (
                (_is_call(trig[0], "sin") and _is_call(trig[1], "cos"))
                or (_is_call(trig[1], "sin") and _is_call(trig[0], "cos"))
            ) and trig[0].args[0] == trig[1].args[0]:
                return _call("sin", mx.Mul(_num(2), trig[0].args[0]))

        return e

    return e


def simplify(expr: mx.Expr) -> mx.Expr:
    """Apply bounded exact trig rewrites to a fixed point."""
    current = expr
    for _ in range(MAX_PASSES):
        nxt = _rewrite(current)
        if nxt == current:
            return current
        current = nxt
    return current


def identities() -> tuple[str, ...]:
    """Machine-readable inventory of the current exact identity families."""
    return (
        "paridad",
        "pitagorica",
        "reciprocas_y_cocientes",
        "cofuncion",
        "periodicidad_2pi",
        "angulo_doble_seno",
        "angulo_doble_coseno",
        "angulo_doble_tangente",
        "medio_angulo",
        "producto_doble_seno",
    )
