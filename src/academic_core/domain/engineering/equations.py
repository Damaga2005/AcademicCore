"""Safe equation parsing + evaluation (Phase 6): own recursive parser, no eval.

Grammar:
    equation := NAME '=' expr
    expr     := term (('+'|'-') term)*
    term     := factor (('*'|'/') factor)*
    factor   := ('+'|'-') factor | power
    power    := primary ('**' primary)?        (exponent must be dimensionless)
    primary  := NUMBER [unit] | NAME | func '(' expr ')' | '(' expr ')'
    func     := sqrt|exp|log|log10|sin|cos|tan|abs   (explicit whitelist)

Evaluation environment: {name: Quantity}. Result dimension checked against
the equation's declared output dimension when the equation is bound. No
imports, no attribute access, no calls beyond the whitelist, no filesystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from academic_core.domain.engineering.units import (
    DIMENSIONLESS, Quantity, UnitError, parse_quantity, parse_unit,
)

ENGINE_VERSION = "engcalc/6.0"

ALLOWED_FUNCS = ("sqrt", "exp", "log", "log10", "sin", "cos", "tan", "abs")

_TOKEN = re.compile(r"""
    (?P<num>[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)
  | (?P<name>[A-Za-z_µΩΩ][A-Za-z0-9_µΩΩ]*)
  | (?P<op>\*\*|[+\-*/()=,])
  | (?P<ws>\s+)
  | (?P<bad>.)
""", re.VERBOSE)


class EquationError(ValueError):
    pass


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens = []
    for m in _TOKEN.finditer(expr):
        kind = m.lastgroup
        if kind == "ws":
            continue
        if kind == "bad":
            raise EquationError(f"bad character: {m.group()!r}")
        tokens.append((kind, m.group()))
    return tokens


@dataclass(frozen=True)
class Equation:
    source: str  # original expression, preserved verbatim
    output: str  # NAME on the left-hand side
    variables: tuple  # sorted free NAMEs (excluding whitelist funcs)
    units: tuple  # unit symbols appearing literally
    provenance: dict | None = None

    def names(self) -> set:
        return set(self.variables) | {self.output}


def parse_equation(source: str) -> Equation:
    if "=" not in source:
        raise EquationError("equation needs NAME = expr")
    lhs, _, rhs = source.partition("=")
    lhs, rhs = lhs.strip(), rhs.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", lhs):
        raise EquationError(f"bad output name: {lhs!r}")
    if not rhs:
        raise EquationError("empty right-hand side")
    tokens = _tokenize(rhs)
    # validate parse + collect names/units with the real parser
    parser = _Parser(tokens)
    parser.parse_expr()
    if parser.pos != len(tokens):
        raise EquationError(f"trailing tokens: {tokens[parser.pos:]}")
    names = sorted({t for k, t in tokens if k == "name"
                    and t not in ALLOWED_FUNCS and not _is_unit_literal(t)})
    units: list[str] = []
    # unit literals: NAME tokens directly following a number
    for i, (k, t) in enumerate(tokens):
        if k == "name" and i > 0 and tokens[i - 1][0] == "num":
            # could be a unit or start of implicit... explicit multiply only,
            # so NAME after NUMBER is a unit literal candidate
            units.append(t)
    # verify each candidate parses as a unit (raises on garbage)
    for u in units:
        try:
            parse_unit(u)
        except UnitError:
            raise EquationError(f"unknown unit literal: {u!r}")
    return Equation(source, lhs, tuple(names), tuple(units), None)


def _is_unit_literal(t: str) -> bool:
    try:
        parse_unit(t)
        return True
    except UnitError:
        return False


class _Parser:
    """Validating parse (structure only). Evaluation re-parses with env."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def next(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def parse_expr(self):
        self.parse_term()
        while self.peek() in (("op", "+"), ("op", "-")):
            self.next()
            self.parse_term()

    def parse_term(self):
        self.parse_factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            self.next()
            self.parse_factor()

    def parse_factor(self):
        if self.peek() in (("op", "+"), ("op", "-")):
            self.next()
            self.parse_factor()
            return
        self.parse_power()

    def parse_power(self):
        self.parse_primary()
        if self.peek() == ("op", "**"):
            self.next()
            self.parse_primary()

    def parse_primary(self):
        kind, val = self.next()
        if kind == "num":
            # optional unit literal glued after the number
            if self.peek()[0] == "name":
                self.next()
            return
        if kind == "name":
            if val in ALLOWED_FUNCS:
                if self.next() != ("op", "("):
                    raise EquationError(f"{val} needs (...)")
                self.parse_expr()
                if self.next() != ("op", ")"):
                    raise EquationError("missing )")
                return
            return
        if (kind, val) == ("op", "("):
            self.parse_expr()
            if self.next() != ("op", ")"):
                raise EquationError("missing )")
            return
        raise EquationError(f"unexpected {val!r}")


def _span_text(tokens) -> str:
    """Readable source text of a token span (data for explanations, never executed)."""
    out = ""
    for _kind, val in tokens:
        call = val == "(" and out[-1:].isalnum()  # function call: "exp(" stays joined
        if out and not out.endswith("(") and val != ")" and not call:
            out += " "
        out += val
    return out


class _Eval:
    """Recursive-descent evaluator.

    E0 (explainable execution): an optional ``observer`` is told, in real
    evaluation order, about every value that is read (``leaf``) and every
    operation that is applied (``operation``). It receives the Quantity the
    engine actually computed. With ``observer=None`` (the default)
    behaviour is unchanged. The observer never influences evaluation.
    """

    def __init__(self, tokens, env: dict[str, Quantity], observer=None):
        self.tokens = tokens
        self.pos = 0
        self.env = env
        self.observer = observer

    def _leaf(self, kind: str, start: int, value: Quantity) -> Quantity:
        if self.observer is not None:
            self.observer.leaf(kind, _span_text(self.tokens[start:self.pos]), value)
        return value

    def _op(self, op: str, start: int, arity: int, value: Quantity) -> Quantity:
        if self.observer is not None:
            self.observer.operation(op, _span_text(self.tokens[start:self.pos]), arity, value)
        return value

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def next(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def run(self) -> Quantity:
        out = self.expr()
        if self.pos != len(self.tokens):
            raise EquationError("trailing tokens")
        return out

    def expr(self) -> Quantity:
        start = self.pos
        out = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.next()[1]
            rhs = self.term()
            out = self._op(op, start, 2, out + rhs if op == "+" else out - rhs)
        return out

    def term(self) -> Quantity:
        start = self.pos
        out = self.factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.next()[1]
            rhs = self.factor()
            out = self._op(op, start, 2, out * rhs if op == "*" else out / rhs)
        return out

    def factor(self) -> Quantity:
        if self.peek() in (("op", "+"), ("op", "-")):
            start = self.pos
            neg = self.next()[1] == "-"
            val = self.factor()
            return self._op("neg", start, 1, -val) if neg else val
        return self.power()

    def power(self) -> Quantity:
        start = self.pos
        base = self.primary()
        if self.peek() == ("op", "**"):
            self.next()
            exp = self.primary()
            if exp.dimension != DIMENSIONLESS:
                raise EquationError("exponent must be dimensionless")
            return self._op("**", start, 2, base ** exp.to_base())
        return base

    def primary(self) -> Quantity:
        start = self.pos
        kind, val = self.next()
        if kind == "num":
            try:
                number = Decimal(val)
            except InvalidOperation:
                raise EquationError(f"bad number: {val}")
            if self.peek()[0] == "name":
                unit = parse_unit(self.next()[1])
                return self._leaf("literal", start, Quantity(number, unit))
            from academic_core.domain.engineering.units import Unit
            return self._leaf("literal", start, Quantity(number, Unit("1", "1", "", DIMENSIONLESS, Decimal(1))))
        if kind == "name":
            if val in ALLOWED_FUNCS:
                if self.next() != ("op", "("):
                    raise EquationError(f"{val} needs (...)")
                arg = self.expr()
                if self.next() != ("op", ")"):
                    raise EquationError("missing )")
                return self._op(val, start, 1, _apply_func(val, arg))
            if val not in self.env:
                # Standalone unit literal (e.g. `kohm` in `49.4 * kohm`):
                # env always wins, so real variables shadow unit names.
                try:
                    return self._leaf("unit", start, Quantity(Decimal(1), parse_unit(val)))
                except UnitError:
                    raise EquationError(f"unknown variable: {val}") from None
            got = self.env[val]
            if not isinstance(got, Quantity):
                raise EquationError(f"{val} is not a Quantity")
            return self._leaf("variable", start, got)
        if (kind, val) == ("op", "("):
            out = self.expr()
            if self.next() != ("op", ")"):
                raise EquationError("missing )")
            return out
        raise EquationError(f"unexpected {val!r}")


def _apply_func(name: str, arg: Quantity) -> Quantity:
    from academic_core.domain.engineering.units import Unit
    from academic_core.domain.engineering.math.trig import (
        decimal_sin, decimal_cos, make_context,
    )
    from academic_core.domain.engineering.math.logarithm import decimal_log10
    one = Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
    if name in ("sin", "cos", "tan", "exp", "log", "log10"):
        if arg.dimension != DIMENSIONLESS:
            raise EquationError(f"{name} needs a dimensionless argument")
        x = arg.to_base()
        ctx = make_context()
        try:
            if name == "sin":
                out = decimal_sin(x, ctx)
            elif name == "cos":
                out = decimal_cos(x, ctx)
            elif name == "tan":
                cos_x = decimal_cos(x, ctx)
                # Guard against division by a cosine that is zero (or
                # numerically indistinguishable from zero at working
                # precision) instead of blowing up to Infinity/NaN.
                # copy_abs()/ctx.scaleb(): bare abs()/Decimal.scaleb()
                # would round through the ambient global context (same
                # bug class as DecimalComplex.modulus()).
                if cos_x.copy_abs() < ctx.scaleb(Decimal(1), -(ctx.prec - 2)):
                    raise EquationError(f"tan domain: cos(x) ~ 0 near {x}")
                out = ctx.divide(decimal_sin(x, ctx), cos_x)
            elif name == "exp":
                # decimal.Context.exp is a correctly-rounded Decimal-native
                # operation (General Decimal Arithmetic spec) — the same
                # primitive already used for exp() in mna/diode.py and
                # mna/bjt.py. No float round-trip.
                out = ctx.exp(x)
            elif name == "log":
                if x <= 0:
                    raise EquationError(f"log domain: {x}")
                out = ctx.ln(x)
            else:  # log10
                if x <= 0:
                    raise EquationError(f"log10 domain: {x}")
                out = decimal_log10(x, ctx)
        except InvalidOperation as e:
            raise EquationError(f"{name} domain: {e}")
        except ArithmeticError as e:
            raise EquationError(f"{name}: {e}")
        return Quantity(out, one)
    if name == "abs":
        # copy_abs() flips the sign bit only and performs no rounding; it
        # never touches the ambient global decimal context. The bare
        # builtin abs(arg.value) would be wrong here (same class of bug as
        # the DecimalComplex.modulus() im==0 fast path): every sibling
        # branch above (sin/cos/tan/exp/log/log10) explicitly threads its
        # own working-precision Context, so a bare abs() on this branch
        # alone would silently truncate the result to the ambient 28-digit
        # default context instead.
        return Quantity(arg.value.copy_abs(), arg.unit)
    if name == "sqrt":
        if arg.to_base() < 0:
            raise EquationError("sqrt of negative")
        root = make_context().sqrt(arg.to_base())
        # dimension must be an exact square
        dim = tuple(e // 2 if e % 2 == 0 else None for e in arg.dimension)
        if any(e is None for e in dim):
            raise EquationError("sqrt needs square dimensions")
        return Quantity(root, _unit_for(tuple(dim)))
    raise EquationError(f"unknown function: {name}")  # unreachable


def _unit_for(dim: tuple):
    from academic_core.domain.engineering.units import _unit_for_dim
    return _unit_for_dim(dim)


def evaluate(eq: Equation, env: dict[str, Quantity], observer=None) -> Quantity:
    """Evaluate a parsed equation. Unknown names, bad dims, div-by-zero →
    controlled EquationError/UnitError. Never eval/exec.

    ``observer`` (E0, optional): receives ``leaf(kind, text, quantity)`` and
    ``operation(op, text, arity, quantity)`` calls in evaluation order;
    see ``_Eval``. It does not change the result."""
    rhs = eq.source.partition("=")[2]
    return _Eval(_tokenize(rhs), env, observer).run()
