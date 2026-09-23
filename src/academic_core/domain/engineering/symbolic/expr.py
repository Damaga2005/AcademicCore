# SPDX-License-Identifier: MIT
"""E0.1 symbolic expressions: exact AST, safe parser, printers.

This is a small, bounded, rule-based symbolic layer. It is the only one:
the repository had no computer-algebra engine before E0.1. Expressions
are data. Parsing is done by an explicit recursive-descent parser over
an allow-listed token set, and nothing is ever evaluated with
``eval``/``exec``.

Nodes are frozen dataclasses:

- ``Num``: an exact ``Fraction``
- ``Sym``: a name
- ``Add`` / ``Sub`` / ``Mul`` / ``Div`` / ``Pow`` (binary, as written by
  the user, so that the rules follow the written structure)
- ``Neg``
- ``Fn``: one of ``FUNCTIONS``

Two printers:

- ``text(e)``: human form (``x^2``, ``2*x``, ``sin(x^2 + 1)``). Only the
  parentheses that precedence requires are printed.
- ``code(e)``: the same expression in the syntax of the certified
  equation evaluator (``**``). It is used only to *verify* numerically
  through that evaluator.

Bounds: source ≤ ``MAX_SOURCE`` characters, depth ≤ ``MAX_DEPTH``, and
every printed expression ≤ ``MAX_TEXT`` characters. Anything larger is
refused with a D2 ``ValidationError``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from academic_core.errors import UnsupportedError, ValidationError

FUNCTIONS = ("sin", "cos", "tan", "exp", "log", "sqrt", "abs")  # log = natural logarithm (engine semantics)
MAX_SOURCE = 256
MAX_DEPTH = 48
MAX_TEXT = 480

_TOKEN = re.compile(r"\s*(?:(?P<num>[0-9]+(?:\.[0-9]+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>\*\*|[-+*/^()]))")


def invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")


class Expr:
    """Base of all nodes (frozen dataclasses below)."""

    __slots__ = ()


@dataclass(frozen=True)
class Num(Expr):
    value: Fraction


@dataclass(frozen=True)
class Sym(Expr):
    name: str


@dataclass(frozen=True)
class Add(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Sub(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Mul(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Div(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Pow(Expr):
    base: Expr
    exponent: Expr


@dataclass(frozen=True)
class Neg(Expr):
    arg: Expr


@dataclass(frozen=True)
class Fn(Expr):
    name: str
    arg: Expr


ZERO, ONE = Num(Fraction(0)), Num(Fraction(1))


def num(value) -> Num:
    return Num(Fraction(value))


# ---------------------------------------------------------------- parsing

def _tokens(source: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(source):
        m = _TOKEN.match(source, pos)
        if not m or m.end() == pos:
            if source[pos:].strip() == "":
                break
            raise invalid("PARSE_ERROR", f"unexpected character {source[pos]!r} at {pos}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.pos = tokens, 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expr(self, depth):
        if depth > MAX_DEPTH:
            raise invalid("EXPRESSION_LIMIT", f"nesting deeper than {MAX_DEPTH}")
        node = self.term(depth)
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            rhs = self.term(depth)
            node = Add(node, rhs) if op == "+" else Sub(node, rhs)
        return node

    def term(self, depth):
        node = self.unary(depth)
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            rhs = self.unary(depth)
            node = Mul(node, rhs) if op == "*" else Div(node, rhs)
        return node

    def unary(self, depth):
        if self.peek() == ("op", "-"):
            self.take()
            return Neg(self.unary(depth + 1))
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary(depth + 1)
        return self.power(depth)

    def power(self, depth):
        base = self.primary(depth)
        if self.peek() in (("op", "^"), ("op", "**")):
            self.take()
            return Pow(base, self.unary(depth + 1))  # right-associative
        return base

    def primary(self, depth):
        kind, val = self.take()
        if kind == "num":
            return Num(Fraction(val))
        if kind == "name":
            if val in FUNCTIONS:
                if self.take() != ("op", "("):
                    raise invalid("PARSE_ERROR", f"{val} needs (...)")
                arg = self.expr(depth + 1)
                if self.take() != ("op", ")"):
                    raise invalid("PARSE_ERROR", "missing )")
                return Fn(val, arg)
            if self.peek() == ("op", "("):
                raise invalid("PARSE_ERROR", f"unknown function {val!r} (allowed: {', '.join(FUNCTIONS)})")
            return Sym(val)
        if (kind, val) == ("op", "("):
            node = self.expr(depth + 1)
            if self.take() != ("op", ")"):
                raise invalid("PARSE_ERROR", "missing )")
            return node
        raise invalid("PARSE_ERROR", f"unexpected {val!r}" if val else "unexpected end of expression")


def parse(source: str) -> Expr:
    """Parse ``source`` (numbers, names, + - * / ^ **, parentheses, FUNCTIONS)."""
    if not isinstance(source, str) or not source.strip():
        raise invalid("PARSE_ERROR", "empty expression")
    if len(source) > MAX_SOURCE:
        raise invalid("EXPRESSION_LIMIT", f"expression longer than {MAX_SOURCE} characters")
    p = _Parser(_tokens(source))
    node = p.expr(0)
    if p.pos != len(p.tokens):
        kind, val = p.peek()
        hint = " (write products explicitly, e.g. 2*x)" if kind in ("name", "num", None) or val == "(" else ""
        raise invalid("PARSE_ERROR", f"unexpected {val!r}{hint}")
    return node


# ---------------------------------------------------------------- queries

def depends(e: Expr, var: str) -> bool:
    if isinstance(e, Num):
        return False
    if isinstance(e, Sym):
        return e.name == var
    if isinstance(e, (Neg, Fn)):
        return depends(e.arg, var)
    if isinstance(e, Pow):
        return depends(e.base, var) or depends(e.exponent, var)
    return depends(e.left, var) or depends(e.right, var)


def substitute(e: Expr, var: str, value: Expr) -> Expr:
    """Replace ``var`` by ``value`` structurally (no evaluation)."""
    if isinstance(e, Sym):
        return value if e.name == var else e
    if isinstance(e, Num):
        return e
    if isinstance(e, Neg):
        return Neg(substitute(e.arg, var, value))
    if isinstance(e, Fn):
        return Fn(e.name, substitute(e.arg, var, value))
    if isinstance(e, Pow):
        return Pow(substitute(e.base, var, value), substitute(e.exponent, var, value))
    return type(e)(substitute(e.left, var, value), substitute(e.right, var, value))


def exact_value(e: Expr) -> Fraction | None:
    """Exact rational value of a variable-free expression built from + - * / and
    integer powers; ``None`` if it needs a function or an irrational power."""
    if isinstance(e, Num):
        return e.value
    if isinstance(e, (Sym, Fn)):
        return None
    if isinstance(e, Neg):
        v = exact_value(e.arg)
        return None if v is None else -v
    if isinstance(e, Pow):
        b, x = exact_value(e.base), exact_value(e.exponent)
        if b is None or x is None or x.denominator != 1 or abs(x) > 64 or (b == 0 and x < 0):
            return None
        return b ** int(x)
    a, b = exact_value(e.left), exact_value(e.right)
    if a is None or b is None:
        return None
    if isinstance(e, Add):
        return a + b
    if isinstance(e, Sub):
        return a - b
    if isinstance(e, Mul):
        return a * b
    return None if b == 0 else a / b


# ---------------------------------------------------------------- printing

_PREC = {Add: 1, Sub: 1, Mul: 2, Div: 2, Neg: 3, Pow: 4}


def _prec(e: Expr) -> int:
    if isinstance(e, Num):
        if e.value < 0:
            return 1  # a negative literal is parenthesised as a factor: 3*(-3), (-2)^2
        return 2 if e.value.denominator != 1 else 5
    return _PREC.get(type(e), 5)


def _fraction(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _print(e: Expr, power: str) -> str:
    def wrap(child: Expr, need: int, strict: bool = False) -> str:
        s = _print(child, power)
        p = _prec(child)
        return f"({s})" if p < need or (strict and p == need) else s

    if isinstance(e, Num):
        return _fraction(e.value)
    if isinstance(e, Sym):
        return e.name
    if isinstance(e, Fn):
        return f"{e.name}({_print(e.arg, power)})"
    if isinstance(e, Neg):
        return "-" + wrap(e.arg, 2)  # -(a*b) = (-a)*b and -(a/b) = (-a)/b: no parentheses needed
    if isinstance(e, Pow):
        # the certified evaluator only accepts a primary as exponent, so code() wraps harder
        return f"{wrap(e.base, 5)}{power}{wrap(e.exponent, 4 if power == '^' else 5)}"
    if isinstance(e, Add):
        return f"{wrap(e.left, 1)} + {wrap(e.right, 1)}"
    if isinstance(e, Sub):
        return f"{wrap(e.left, 1)} - {wrap(e.right, 1, strict=True)}"
    if isinstance(e, Mul):
        return f"{wrap(e.left, 2)}*{wrap(e.right, 2)}"
    return f"{wrap(e.left, 2)}/{wrap(e.right, 2, strict=True)}"


def text(e: Expr) -> str:
    out = _print(e, "^")
    if len(out) > MAX_TEXT:
        raise invalid("EXPRESSION_LIMIT", f"expression grows beyond {MAX_TEXT} characters")
    return out


def code(e: Expr) -> str:
    """Syntax of the certified equation evaluator (``**``), used only for verification."""
    return _print(e, " ** ")
