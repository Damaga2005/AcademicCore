# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: multivariate exact expressions, text input and preview.

The engine of E0.1 (``symbolic/``) is single-variable by design and is left
untouched: it is used by many certified features and its behaviour must not
change (MATH_LAB §11.2, criterion 9). ML-0 *extends* it instead of rewriting
it (MATH_LAB §12, "se amplía lo existente, no se reescribe"):

- this module holds the **multivariate** expression layer: any number of
  variables, exact numbers including ``pi``, ``e``, ``i`` and exact roots,
  and calculus objects (``Integral``, ``Limit``, ``Sum``, ``Derivative``) as
  first-class nodes so an exercise can *state* something not yet solved;
- ``to_symbolic`` hands a single-variable expression to the existing engine,
  which keeps owning differentiation, integration, linear solving and the
  step log.

Design rules inherited from ``symbolic/expr.py`` and kept on purpose:

- expressions are data (frozen dataclasses), never code;
- parsing is an explicit recursive-descent parser over an allow-listed token
  set; nothing is ever ``eval``-ed;
- every printer output is bounded, and a violation is a D2 ``ValidationError``;
- a failure to parse says *where* the problem is, in Spanish.

Text input accepts what §8.1 requires (``x^2``, ``sqrt(x)``, ``sen``/``sin``,
``e^x``, ``pi``, ``i``/``j``) and additionally the Spanish decimal comma
(``0,5``), Spanish function names (``sen``, ``arcsen``, ``raiz``) and
implicit multiplication (``2x``, ``3pi``, ``(x+1)(x-1)``).

Naming rule (deliberate, and stated because it is ambiguous)
------------------------------------------------------------

A bare run of letters is split into single-letter variables, so ``xy`` is
``x·y`` and ``2xy`` is what a student means by it. A name that carries a digit
or an underscore is kept whole, because those are indexed variables:
``x1`` is one variable, not ``x·1``, and ``t_0`` is one variable, not
``t·_·0``.

The reserved names (``pi``, ``e``, ``i``, and the function names) always win
over the split, and ``parse(..., reserved=...)`` removes a name from the
reserved set when a variable really is called ``i`` or ``e``.


Three printers are provided: ``text`` (canonical ASCII, round-trips through
``parse``), ``pretty`` (Unicode notation for the preview, §5.1) and ``latex``.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass
from fractions import Fraction

from academic_core.errors import UnsupportedError, ValidationError

# ---------------------------------------------------------------------------
# limits (same spirit as symbolic/expr.py, larger: exercises are long)
# ---------------------------------------------------------------------------

MAX_SOURCE = 512
MAX_DEPTH = 64
MAX_TEXT = 2000
MAX_CALL_ARGS = 4
MAX_ROOT_DEGREE = 64

#: constants recognised as names: pi/e/i (§5.1 exact numbers)
CONSTANTS = ("pi", "e", "i")

#: canonical function names -> (accepted spellings, arity or None for variadic)
_FUNCTIONS: dict[str, tuple[tuple[str, ...], int | None]] = {
    "sin": (("sin", "sen"), 1),
    "cos": (("cos",), 1),
    "tan": (("tan",), 1),
    "cot": (("cot",), 1),
    "sec": (("sec",), 1),
    "csc": (("csc",), 1),
    "asin": (("asin", "arcsen", "arcsin"), 1),
    "acos": (("acos", "arccos", "arccos"), 1),
    "atan": (("atan", "arctan", "arctan"), 1),
    "sinh": (("sinh", "senh"), 1),
    "cosh": (("cosh",), 1),
    "tanh": (("tanh", "tanh"), 1),
    "coth": (("coth",), 1),
    "sech": (("sech",), 1),
    "csch": (("csch",), 1),
    "asinh": (("asinh", "arcsenh", "arsinh"), 1),
    "acosh": (("acosh", "arccosh", "arccosh"), 1),
    "atanh": (("atanh", "arctanh", "arctanh"), 1),
    "exp": (("exp",), 1),
    "ln": (("ln",), 1),
    "log10": (("log10",), 1),
    "log": (("log", "logb"), 2),
    "abs": (("abs", "valor_abs"), 1),
    "sign": (("sign", "signo"), 1),
    "floor": (("floor", "parte_entera"), 1),
    "ceil": (("ceil", "techo"), 1),
}

#: two-argument root written ``raiz(x, n)`` / ``root(x, n)`` -> n-th root of x
_ROOT_SPELLINGS = ("raiz", "raizn", "root")
_SQRT_SPELLINGS = ("sqrt", "raiz2", "sqr")

_SPELLING_TO_NAME: dict[str, str] = {
    spelling: name for name, (spellings, _) in _FUNCTIONS.items() for spelling in spellings
}
_SPELLING_TO_NAME.update({s: "sqrt" for s in _SQRT_SPELLINGS})
_SPELLING_TO_NAME.update({s: "root" for s in _ROOT_SPELLINGS})

#: spellings that are never a variable and never an implicit product
_RESERVED = frozenset(_SPELLING_TO_NAME) | {"pi", "e", "i", "j"}


def invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


class Expr:
    """Base of all nodes (frozen dataclasses below)."""

    __slots__ = ()


@dataclass(frozen=True)
class Num(Expr):
    """Exact rational.

    A ``float`` is accepted and converted through its exact binary value, rather
    than refused: refusing gives ``'float' object has no attribute 'numerator'``
    three frames away from the mistake, and accepting gives the only thing a float
    can honestly become here — a rational, however ugly. Nothing downstream ever
    sees the float again, so it cannot quietly propagate.
    """

    value: Fraction

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            object.__setattr__(self, "value", Fraction(self.value))
        elif isinstance(self.value, int):
            object.__setattr__(self, "value", Fraction(self.value))
        elif not isinstance(self.value, Fraction):
            raise no_rule(
                f"un número exacto tiene que ser Fraction o int; llegó "
                f"{type(self.value).__name__}")


@dataclass(frozen=True)
class Sym(Expr):
    """A variable or named constant defined by the student (§8.1)."""

    name: str


@dataclass(frozen=True)
class Const(Expr):
    """``pi``, ``e`` or ``i`` — exact, never a decimal."""

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
class Call(Expr):
    """A registered function; ``args`` is non-empty and bounded."""

    name: str
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class Root(Expr):
    """Exact ``degree``-th root. ``sqrt(x)`` is ``Root(2, x)``."""

    degree: int
    radicand: Expr


@dataclass(frozen=True)
class Integral(Expr):
    """``integral(integrand, var)`` (indefinite) or with ``lower``/``upper``.

    ``None`` bounds mean "indefinite" / "not stated": the object can be shown
    and printed, but it is not a value.
    """

    integrand: Expr
    var: str
    lower: Expr | None = None
    upper: Expr | None = None


@dataclass(frozen=True)
class Limit(Expr):
    """``limit(expr, var, point[, side])``; ``side`` is ``""``, ``"+"`` or ``"-"``."""

    expr: Expr
    var: str
    point: Expr
    side: str = ""


@dataclass(frozen=True)
class Sum(Expr):
    body: Expr
    var: str
    lower: Expr
    upper: Expr


@dataclass(frozen=True)
class Derivative(Expr):
    expr: Expr
    var: str
    order: int = 1


ZERO, ONE = Num(Fraction(0)), Num(Fraction(1))
PI, E, I = Const("pi"), Const("e"), Const("i")


def num(value) -> Num:
    return Num(Fraction(value))


# ---------------------------------------------------------------------------
# tokeniser
# ---------------------------------------------------------------------------

#: ``,`` is ALWAYS a separate token. A decimal comma is not a lexical fact:
#: ``f(8,3)`` is two arguments while ``0,5`` is one half, and only the parser
#: can tell them apart (it knows whether it is reading a call's argument list).
_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<num>[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>\*\*|\^|[-+*/()=,])"
    r")"
)


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    pos: int


def _tokenize(source: str) -> list[_Token]:
    out: list[_Token] = []
    pos = 0
    while pos < len(source):
        m = _TOKEN.match(source, pos)
        if not m or m.end() == pos:
            rest = source[pos:]
            if rest.strip() == "":
                break
            raise invalid("PARSE_ERROR", f"carácter no válido {source[pos]!r} en la posición {pos + 1}")
        kind = m.lastgroup
        assert kind is not None
        out.append(_Token(kind, m.group(kind), m.start(kind)))
        pos = m.end()
    return out


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


class _Parser:
    """Recursive descent. Products may be implicit (§8.1 convenience)."""

    def __init__(self, tokens: list[_Token], reserved: frozenset[str],
                 nombres: frozenset[str] = frozenset()):
        self.tokens = tokens
        self.pos = 0
        self.reserved = reserved
        #: declared multi-letter variable names, never split into products
        self.nombres = nombres
        # inside a call's argument list, ',' separates arguments (never a decimal)
        self.in_args = False

    # -- token helpers
    def peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> _Token | None:
        tok = self.peek()
        self.pos += 1
        return tok

    def at_op(self, *ops: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "op" and tok.value in ops

    def at_name(self, *names: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "name" and tok.value in names

    def expect_op(self, op: str, what: str) -> _Token:
        tok = self.take()
        if tok is None or tok.kind != "op" or tok.value != op:
            where = "al final de la expresión" if tok is None else f"en la posición {tok.pos + 1}"
            raise invalid("PARSE_ERROR", f"falta «{op}» {what} ({where})")
        return tok

    # -- grammar
    def expression(self, depth: int) -> Expr:
        if depth > MAX_DEPTH:
            raise invalid("EXPRESSION_LIMIT", f"anidamiento mayor que {MAX_DEPTH}")
        node = self.additive(depth)
        if self.at_op("="):
            tok = self.take()
            assert tok is not None
            raise invalid(
                "PARSE_ERROR",
                f"una igualdad no es una expresión (posición {tok.pos + 1}); "
                "usa la calculadora de ecuaciones",
            )
        return node

    def additive(self, depth: int) -> Expr:
        node = self.multiplicative(depth)
        while self.at_op("+", "-"):
            op = self.take().value
            rhs = self.multiplicative(depth)
            node = Add(node, rhs) if op == "+" else Sub(node, rhs)
        return node

    def multiplicative(self, depth: int) -> Expr:
        node = self.unary(depth)
        while True:
            if self.at_op("*", "/"):
                op = self.take().value
                rhs = self.unary(depth)
                node = Mul(node, rhs) if op == "*" else Div(node, rhs)
                continue
            # implicit products must be re-checked after each explicit one, so
            # that "(x+2)(x+3)/(x+3)" groups as ((x+2)*(x+3))/(x+3)
            stepped = self._implicit(node, depth)
            if stepped is node:
                return node
            node = stepped

    def _is_call_ahead(self) -> bool:
        nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
        return nxt is not None and nxt.kind == "op" and nxt.value == "("

    def _implicit(self, left: Expr, depth: int) -> Expr:
        """``2x``, ``3pi``, ``2sin(x)``, ``(x+1)(x-1)``, ``xy``.

        A function name not followed by ``(`` ends the product, so a typo like
        ``2 sin x`` is reported instead of silently becoming ``2*sen(x)``.
        """
        while True:
            tok = self.peek()
            if tok is None:
                return left
            if tok.kind == "op" and tok.value == "(":
                right = self.unary(depth + 1)
            elif tok.kind == "name":
                # a reserved word that is not being called is pi, e or i; either
                # way it is a factor, so the product continues
                if tok.value in _SPELLING_TO_NAME and not self._is_call_ahead():
                    return left
                right = self.unary(depth + 1)
            else:
                return left
            if depth > MAX_DEPTH:
                raise invalid("EXPRESSION_LIMIT", f"anidamiento mayor que {MAX_DEPTH}")
            left = Mul(left, right)

    def unary(self, depth: int) -> Expr:
        if self.at_op("-"):
            self.take()
            return Neg(self.unary(depth + 1))
        if self.at_op("+"):
            self.take()
            return self.unary(depth + 1)
        return self.power(depth)

    def power(self, depth: int) -> Expr:
        base = self.primary(depth)
        if self.at_op("^", "**"):
            self.take()
            exponent = self.unary(depth + 1)  # right-associative
            return _make_pow(base, exponent)
        return base

    def primary(self, depth: int) -> Expr:
        tok = self.take()
        if tok is None:
            raise invalid("PARSE_ERROR",
                          "la expresión termina antes de tiempo, donde se esperaba un valor")
        if tok.kind == "num":
            return self._number(tok)
        if tok.kind == "name":
            return self._name(tok, depth)
        if tok.value == "(":
            node = self.expression(depth + 1)
            self.expect_op(")", "al cerrar el paréntesis")
            return node
        raise invalid("PARSE_ERROR", f"no se esperaba {tok.value!r} en la posición {tok.pos + 1}")

    def _name(self, tok: _Token, depth: int) -> Expr:
        name = tok.value
        if name == "j":
            return I  # engineering spelling of the imaginary unit
        if name in ("pi",):
            return PI
        if name in ("e", "i"):
            return Const(name)
        if name in _SPELLING_TO_NAME:
            return self._call(_SPELLING_TO_NAME[name], self._args(tok, depth), depth)
        if self.at_op("("):
            raise invalid(
                "PARSE_ERROR",
                f"«{name}» no es una función conocida (posición {tok.pos + 1}; "
                f"disponibles: {', '.join(sorted(_SPELLING_TO_NAME))})",
            )
        if len(name) > 32:
            raise invalid("PARSE_ERROR", f"nombre de variable demasiado largo en la posición {tok.pos + 1}")
        producto = None if name in self.nombres else _split_letters(name)
        return producto if producto is not None else Sym(name)

    def _args(self, tok: _Token, depth: int) -> list[Expr]:
        self.expect_op("(", f"después de «{tok.value}»")
        outer, self.in_args = self.in_args, True
        try:
            args = [self.expression(depth + 1)]
            while self.at_op(","):
                self.take()
                if len(args) >= MAX_CALL_ARGS:
                    raise invalid("EXPRESSION_LIMIT", f"más de {MAX_CALL_ARGS} argumentos")
                args.append(self.expression(depth + 1))
        finally:
            self.in_args = outer
        self.expect_op(")", f"al cerrar la llamada a «{tok.value}»")
        return args

    def _number(self, tok: _Token) -> "Num":
        """Read a number, accepting a Spanish decimal comma outside arguments.

        The comma must be glued to both sides (``0,5``), otherwise ``f(1, 2)``
        would be read as the single number ``1.2`` with a stray ``2``.
        """
        literal = tok.value
        if not self.in_args:
            nxt = self.tokens[self.pos] if self.pos < len(self.tokens) else None
            after = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if (nxt is not None and nxt.kind == "op" and nxt.value == ","
                    and nxt.pos == tok.pos + len(literal)
                    and after is not None and after.kind == "num"
                    and after.pos == nxt.pos + 1):
                self.pos += 2
                literal = f"{literal},{after.value}"
        return _number(literal)

    def _call(self, name: str, args: list[Expr], depth: int) -> Expr:
        if name == "root":
            if len(args) != 2:
                raise invalid("PARSE_ERROR", "raiz(x, n) necesita exactamente 2 argumentos")
            degree = exact_integer(args[1])
            if degree is None or not 1 <= degree <= MAX_ROOT_DEGREE:
                raise invalid(
                    "PARSE_ERROR",
                    f"el índice de la raíz debe ser un entero entre 1 y "
                    f"{MAX_ROOT_DEGREE} (posición {self.pos + 1})",
                )
            return Root(degree, args[0])
        if name == "sqrt":
            return Root(2, args[0])
        arity = _FUNCTIONS[name][1]
        if arity is not None and len(args) != arity:
            raise invalid("PARSE_ERROR", f"«{name}» necesita {arity} argumento(s), recibió {len(args)}")
        return Call(name, tuple(args))


def _number(literal: str) -> Num:
    return Num(Fraction(literal.replace(",", ".")))


def _split_letters(name: str) -> Expr | None:
    """``xy`` -> ``x*y``; ``x1`` and ``t_0`` stay whole.

    Splitting applies only to a run of plain letters longer than one. A digit or
    an underscore marks an indexed variable (``x1``, ``t_0``), which must not be
    torn apart into a product — and a reserved name (``pi``, ``sen``) never
    reaches here, because the parser resolves those first.
    """
    if len(name) < 2 or not name.isalpha() or not name.isascii():
        return None
    node: Expr = Sym(name[0])
    for letra in name[1:]:
        node = Mul(node, Sym(letra))
    return node


def exact_integer(e: Expr) -> int | None:
    """Integer value of a closed expression, or ``None``."""
    v = exact_value(e)
    if v is None or v.denominator != 1:
        return None
    return int(v)


def _make_pow(base: Expr, exponent: Expr) -> Expr:
    """``x^(1/2)`` is stored as an exact root, so ``sqrt(x)^2`` is exactly ``x``.

    The exponent is read as a *value* (``1/3`` parses as a ``Div``), and a
    negative base is left as a power: ``(-8)^(1/3)`` is a real root but not a
    ``Root`` node, and pretending otherwise would hide the sign case (§5.4).
    """
    if not isinstance(exponent, Num):
        value = exact_value(exponent)
        if value is None:
            return Pow(base, exponent)
        exponent = Num(value)
    if exponent.value.denominator > 1:
        degree = exponent.value.denominator
        numerador = exponent.value.numerator
        if 2 <= degree <= MAX_ROOT_DEGREE:
            whole = exact_value(base)
            if whole is None or whole > 0:
                entero, resto = divmod(numerador, degree)
                if resto == 0:
                    return Pow(base, Num(Fraction(entero)))
                if resto == 1:
                    # x^(3/2) is x·√x and NOT x^3·√x: the integer part goes
                    # BELOW the root and not above it. Getting that backwards gave
                    # x^(7/2), and the derivative of the primitive of √x came out
                    # 35 times too big — an answer that looked fine and was not.
                    raiz = Root(degree, base)
                    return raiz if entero == 0 else Mul(Pow(base, Num(Fraction(entero))), raiz)
                if degree % 2 == 1:
                    # an ODD root is real for every base: x^(2/3) is (∛x)², and left
                    # as a power it evaluated on the complex branch for x < 0 while
                    # x^(1/3) was already the real root (found 2026-10-06)
                    return Pow(Root(degree, base), Num(Fraction(numerador)))
                return Pow(base, exponent)
    return Pow(base, exponent)


# ---------------------------------------------------------------------------
# public parsing entry points
# ---------------------------------------------------------------------------

#: calculus objects that are *stated* rather than computed (§5.1)
STATEMENTS = ("integral", "int", "limite", "limit", "suma", "sum", "derivada", "diff")


def parse(source: str, *, reserved: frozenset[str] | None = None,
          nombres: frozenset[str] | set[str] | None = None) -> Expr:
    """Parse a formula typed by the student into an exact multivariate ``Expr``.

    ``reserved`` optionally removes names from the constant/function set so a
    variable may be called ``i`` or ``e`` (``reserved=...`` is *added* to).
    ``nombres`` declares multi-letter variables (``Lb``, ``m1``, ``Vcc``) that must
    stay whole instead of reading as the implicit product ``L·b``.
    """
    if not isinstance(source, str) or not source.strip():
        raise invalid("PARSE_ERROR", "expresión vacía")
    if len(source) > MAX_SOURCE:
        raise invalid("EXPRESSION_LIMIT", f"expresión de más de {MAX_SOURCE} caracteres")
    keep = frozenset(reserved) if reserved else frozenset()
    parser = _Parser(_tokenize(source), _RESERVED - keep, frozenset(nombres or ()))
    node = parser.expression(0)
    if parser.pos != len(parser.tokens):
        tok = parser.peek()
        assert tok is not None
        raise invalid("PARSE_ERROR", f"sobra {tok.value!r} en la posición {tok.pos + 1}")
    return node


def parse_calculus(source: str) -> Expr:
    """Parse a *stated* calculus object into its first-class node.

    Accepted forms, as §5.1 writes them::

        int(x^2*sin(x), x, 0, pi)      integral(f, x) | integral(f, x, a, b)
        limite(sin(x)/x, x, 0)        limite(f, x, a, '+') | limite(f, x, a, '-')
        suma(k^2, k, 1, n)             derivada(x^3, x) | derivada(x^3, x, 2)
    """
    if not isinstance(source, str) or not source.strip():
        raise invalid("PARSE_ERROR", "expresión vacía")
    if len(source) > MAX_SOURCE:
        raise invalid("EXPRESSION_LIMIT", f"expresión de más de {MAX_SOURCE} caracteres")
    head, _, rest = source.partition("(")
    name = head.strip().lower()
    if name not in STATEMENTS:
        raise invalid(
            "PARSE_ERROR",
            f"objeto de cálculo desconocido {name!r} (disponibles: integral, limite, suma, derivada)",
        )
    if not rest.endswith(")"):
        raise invalid("PARSE_ERROR", f"falta el paréntesis de cierre de «{name}»")
    args = _split_args(rest[:-1])
    if len(args) < 2:
        raise invalid("PARSE_ERROR", f"«{name}» necesita al menos el integrando y la variable")
    integrand = parse(args[0])
    var = args[1].strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var):
        raise invalid("PARSE_ERROR", f"«{var}» no es un nombre de variable válido")
    if name in ("integral", "int"):
        if len(args) == 2:
            return Integral(integrand, var)
        if len(args) == 4:
            return Integral(integrand, var, parse(args[2]), parse(args[3]))
        raise invalid("PARSE_ERROR", "integral(f, x) o integral(f, x, a, b)")
    if name in ("derivada", "diff"):
        if len(args) == 2:
            return Derivative(integrand, var)
        if len(args) == 3 and exact_integer(parse(args[2])) is not None:
            return Derivative(integrand, var, exact_integer(parse(args[2])))
        raise invalid("PARSE_ERROR", "derivada(f, x) o derivada(f, x, n)")
    if name == "suma" or name == "sum":
        if len(args) != 4:
            raise invalid("PARSE_ERROR", "suma(f, x, a, b)")
        return Sum(integrand, var, parse(args[2]), parse(args[3]))
    # limite(f, x, a) or limite(f, x, a, '+')
    side = ""
    if len(args) == 4:
        side = args[3].strip().strip("'\"")
        if side not in ("", "+", "-"):
            raise invalid("PARSE_ERROR", "el lado del límite debe ser «+» o «-»")
    elif len(args) != 3:
        raise invalid("PARSE_ERROR", "limite(f, x, a) o limite(f, x, a, '+')")
    return Limit(integrand, var, parse(args[2]), side)


def _split_args(body: str) -> list[str]:
    """Split on top-level commas, keeping nested parentheses intact."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise invalid("PARSE_ERROR", "paréntesis desbalanceado")
        elif ch == "," and depth == 0:
            out.append(body[start:i])
            start = i + 1
    out.append(body[start:])
    if depth != 0:
        raise invalid("PARSE_ERROR", "paréntesis desbalanceado")
    return [a.strip() for a in out]


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------


def _walk(e: Expr, bound: frozenset[str] = frozenset()):
    """Yield every node. ``bound`` holds the variables captured by a calculus
    object: the ``x`` of ``∫x²dx`` or of ``d/dx`` is bound, not free."""
    yield e
    if isinstance(e, (Sym, Num, Const)):
        return
    if isinstance(e, Neg):
        yield from _walk(e.arg, bound)
    elif isinstance(e, (Add, Sub, Mul, Div)):
        yield from _walk(e.left, bound)
        yield from _walk(e.right, bound)
    elif isinstance(e, Pow):
        yield from _walk(e.base, bound)
        yield from _walk(e.exponent, bound)
    elif isinstance(e, Call):
        for a in e.args:
            yield from _walk(a, bound)
    elif isinstance(e, Root):
        yield from _walk(e.radicand, bound)
    elif isinstance(e, Integral):
        # the differential binds the variable in the integrand only
        yield from _walk(e.integrand, bound | {e.var})
        for b in (e.lower, e.upper):
            if b is not None:
                yield from _walk(b, bound)
    elif isinstance(e, Limit):
        yield from _walk(e.expr, bound)
        yield from _walk(e.point, bound)
    elif isinstance(e, Sum):
        yield from _walk(e.body, bound | {e.var})
        yield from _walk(e.lower, bound)
        yield from _walk(e.upper, bound)
    elif isinstance(e, Derivative):
        yield from _walk(e.expr, bound | {e.var})


def variables(e: Expr) -> set[str]:
    """Free variable names (calculus bindings excluded), sorted for determinism."""
    return {n.name for n in _walk(e) if isinstance(n, Sym)} - _bound_names(e)


def _bound_names(e: Expr) -> set[str]:
    bound: set[str] = set()
    for node in _walk(e):
        if isinstance(node, (Integral, Sum, Derivative)):
            bound.add(node.var)
    return bound


def depends(e: Expr, var: str) -> bool:
    """Does ``var`` appear anywhere, *including* as a calculus binding?

    Unlike ``variables``, this is a raw mention: ``depends(integral(x, x), "x")``
    is ``True``. Use it to ask "where does this name show up at all".
    """
    return any(isinstance(n, Sym) and n.name == var for n in _walk(e))


def constants(e: Expr) -> set[str]:
    return {n.name for n in _walk(e) if isinstance(n, Const)}


def substitute(e: Expr, var: str, value: Expr, *, inside: str = "") -> Expr:
    """Replace free occurrences of ``var`` by ``value`` (no evaluation, no rule).

    ``inside`` names the calculus binding we are inside, so that substituting
    ``x`` never rewrites the ``x`` of a nested ``d/dx`` or ``∫…dx``.
    """
    if isinstance(e, Sym):
        return value if e.name == var and var != inside else e
    if isinstance(e, (Num, Const)):
        return e
    if isinstance(e, Neg):
        return Neg(substitute(e.arg, var, value, inside=inside))
    if isinstance(e, Call):
        return Call(e.name, tuple(substitute(a, var, value, inside=inside) for a in e.args))
    if isinstance(e, Pow):
        return _make_pow(substitute(e.base, var, value, inside=inside),
                         substitute(e.exponent, var, value, inside=inside))
    if isinstance(e, Root):
        return Root(e.degree, substitute(e.radicand, var, value, inside=inside))
    if isinstance(e, Integral):
        return Integral(substitute(e.integrand, var, value, inside=e.var), e.var,
                        substitute(e.lower, var, value, inside=inside) if e.lower is not None else None,
                        substitute(e.upper, var, value, inside=inside) if e.upper is not None else None)
    if isinstance(e, Limit):
        return Limit(substitute(e.expr, var, value, inside=inside), e.var,
                     substitute(e.point, var, value, inside=inside), e.side)
    if isinstance(e, Sum):
        return Sum(substitute(e.body, var, value, inside=e.var), e.var,
                   substitute(e.lower, var, value, inside=inside),
                   substitute(e.upper, var, value, inside=inside))
    if isinstance(e, Derivative):
        return Derivative(substitute(e.expr, var, value, inside=e.var), e.var, e.order)
    return type(e)(substitute(e.left, var, value, inside=inside),
                   substitute(e.right, var, value, inside=inside))


def exact_value(e: Expr) -> Fraction | None:
    """Exact rational value of a *closed* expression, or ``None``.

    A calculus object is never a value: ``exact_value(integral(x^2, x))`` is
    ``None``, because an indefinite integral is a *function*, not a number, and
    the engine that solves it is what turns it into one.

    A bare Python number is refused rather than coerced. Coercing would be
    convenient and wrong in the other direction: ``exact_value(4)`` returning 4
    hides the mistake one frame later, in whatever arithmetic was meant to receive
    an expression, as an attribute error about ``left``.
    """
    if not isinstance(e, Expr):
        raise no_rule(
            f"exact_value recibe una expresión y recibió {type(e).__name__}; "
            f"envuélvelo con Num({e!r})")
    """Exact rational value of a closed expression, or ``None``.

    ``None`` means "not an exact rational": a variable, a transcendental
    function, ``pi``/``e``/``i``, or a root that is not exact.
    """
    if isinstance(e, Num):
        return e.value
    if isinstance(e, (Sym, Const, Integral, Limit, Sum, Derivative)):
        # a calculus object is a *function*, not a number: it is never a value
        return None
    if isinstance(e, Neg):
        v = exact_value(e.arg)
        return None if v is None else -v
    if isinstance(e, Pow):
        b, x = exact_value(e.base), exact_value(e.exponent)
        if b is None or x is None or x.denominator != 1 or abs(x) > 64 or (b == 0 and x < 0):
            return None
        return b ** int(x)
    if isinstance(e, Root):
        r = exact_value(e.radicand)
        if r is None or e.degree > 32:
            return None
        if r >= 0:
            k = _exact_root(r, e.degree)
            return k
        if e.degree % 2 == 0:
            return None  # no real even root of a negative number
        k = _exact_root(-r, e.degree)
        return None if k is None else -k
    if isinstance(e, Call):
        return None
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


def _exact_root(value: Fraction, degree: int) -> Fraction | None:
    """Exact ``degree``-th root of a nonnegative rational, or ``None``.

    Integer bisection only: no floating point is used, so ``sqrt(4)`` is
    exactly ``2`` and ``sqrt(2)`` is honestly ``None`` (§5.1, §5.4).
    """
    if value == 0:
        return Fraction(0)
    if value < 0 or degree > 32:
        return None
    rn, rd = _perfect_root(value.numerator, degree), _perfect_root(value.denominator, degree)
    if rn is None or rd is None:
        return None
    return Fraction(rn, rd)


MAX_ROOT_BITS = 4096  # keeps the bisection bounded on absurd numerators


def _perfect_root(n: int, degree: int) -> int | None:
    """Exact non-negative integer ``degree``-th root of ``n``, or ``None``."""
    if n < 0 or n.bit_length() > MAX_ROOT_BITS:
        return None
    if n in (0, 1):
        return n
    lo, hi = 1, 1 << ((n.bit_length() + degree - 1) // degree + 1)
    while lo <= hi:
        mid = (lo + hi) // 2
        power = mid ** degree
        if power == n:
            return mid
        if power < n:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


# ---------------------------------------------------------------------------
# numeric evaluation (verification only, never for a displayed exact value)
# ---------------------------------------------------------------------------

_CONST_NUMERIC = {"pi": complex(math.pi), "e": complex(math.e), "i": complex(0, 1)}

#: numeric evaluation is for *verification and graphs* only (§5.3, §6).
#: ``cmath`` handles the whole plane, so no branch is wrong off the real axis.
def _reciproca(z: complex) -> complex:
    """``1/z``, refusing the poles instead of returning a huge wrong number."""
    if z == 0:
        raise ZeroDivisionError("la recíproca de cero no existe")
    return 1 / z


_FN_NUMERIC = {
    "sin": cmath.sin, "cos": cmath.cos, "tan": cmath.tan,
    # cot, sec and csc are reciprocals, and the trig engine produces them: a
    # verification that could not evaluate them would silently check nothing.
    "cot": lambda z: _reciproca(cmath.tan(z)),
    "sec": lambda z: _reciproca(cmath.cos(z)),
    "csc": lambda z: _reciproca(cmath.sin(z)),
    "asin": cmath.asin, "acos": cmath.acos, "atan": cmath.atan,
    "sinh": cmath.sinh, "cosh": cmath.cosh, "tanh": cmath.tanh,
    # same reasoning for the hyperbolic reciprocals: T-14 emits them
    "coth": lambda z: _reciproca(cmath.tanh(z)),
    "sech": lambda z: _reciproca(cmath.cosh(z)),
    "csch": lambda z: _reciproca(cmath.sinh(z)),
    "asinh": cmath.asinh, "acosh": cmath.acosh, "atanh": cmath.atanh,
    "exp": cmath.exp, "ln": cmath.log, "log10": cmath.log10,
    "abs": lambda z: complex(abs(z)),
    "sign": lambda z: complex(0 if z == 0 else (1 if z.real > 0 else -1)),
    "floor": lambda z: complex(math.floor(z.real), 0),
    "ceil": lambda z: complex(math.ceil(z.real), 0),
}


def evaluate(e: Expr, env: dict[str, complex | float | int | Fraction] | None = None) -> complex | None:
    """Numeric value, or ``None`` when undefined/unclosed.

    Used only to *verify* (§5.3) and to draw graphs (§6). A displayed exact
    result never comes from here.
    """
    env = env or {}
    try:
        return _eval(e, env, 0)
    except (ArithmeticError, ValueError, OverflowError, RecursionError):
        return None


def valor_real(e: Expr, env: dict[str, complex | float | int | Fraction] | None = None
              ) -> float | None:
    """The real value when there is one, and ``None`` when there is not.

    :func:`evaluate` answers in COMPLEX numbers for everything — ``Num(0)`` arrives
    as ``0j`` — because it exists to *verify* (§5.3), not to decide. So a guard like
    ``isinstance(valor, complex)`` rejects every single comparison and says nothing
    about why anything was rejected, which is how ``x = pi + 2k·pi`` and
    ``x = -pi + 2k·pi`` stayed two families when they are one.

    This is the accessor for the other question: «is this a real number, and which?».
    The imaginary part is allowed to be rounding and nothing else.
    """
    valor = evaluate(e, env)
    if valor is None:
        return None
    if isinstance(valor, complex):
        return None if abs(valor.imag) > 1e-12 else float(valor.real)
    return float(valor)


def _eval(e: Expr, env: dict, depth: int) -> complex:
    if depth > MAX_DEPTH:
        raise ValueError("too deep")
    if isinstance(e, Num):
        return complex(e.value.numerator / e.value.denominator)
    if isinstance(e, Const):
        return _CONST_NUMERIC[e.name]
    if isinstance(e, Sym):
        if e.name not in env:
            raise ValueError(f"variable libre {e.name}")
        return complex(env[e.name])
    if isinstance(e, Neg):
        return -_eval(e.arg, env, depth + 1)
    if isinstance(e, Add):
        return _eval(e.left, env, depth + 1) + _eval(e.right, env, depth + 1)
    if isinstance(e, Sub):
        return _eval(e.left, env, depth + 1) - _eval(e.right, env, depth + 1)
    if isinstance(e, Mul):
        return _eval(e.left, env, depth + 1) * _eval(e.right, env, depth + 1)
    if isinstance(e, Div):
        d = _eval(e.right, env, depth + 1)
        if d == 0:
            raise ZeroDivisionError("división por cero")
        return _eval(e.left, env, depth + 1) / d
    if isinstance(e, Pow):
        return _eval(e.base, env, depth + 1) ** _eval(e.exponent, env, depth + 1)
    if isinstance(e, Root):
        r = _eval(e.radicand, env, depth + 1)
        if r.imag != 0:
            return _croot(r, e.degree)
        if r.real < 0:
            if e.degree % 2 == 0:
                raise ValueError("raíz par de un número negativo")
            return -((-r.real) ** (1.0 / e.degree))  # odd root of a negative: real
        return r.real ** (1.0 / e.degree)
    if isinstance(e, Call):
        if e.name == "log":
            base, arg = _eval(e.args[0], env, depth + 1), _eval(e.args[1], env, depth + 1)
            if base in (0, 1):
                raise ValueError("base de logaritmo inválida")
            if arg == 0:
                raise ValueError("logaritmo de cero")
            return cmath.log(arg) / cmath.log(base)
        if e.name not in _FN_NUMERIC:
            raise ValueError(f"función no evaluable {e.name}")
        if e.name == "ln" and _eval(e.args[0], env, depth + 1) == 0:
            raise ValueError("logaritmo de cero")
        return _FN_NUMERIC[e.name](_eval(e.args[0], env, depth + 1))
    if isinstance(e, Integral):
        if e.lower is None or e.upper is None:
            raise ValueError("integral indefinida: no es un valor")
        raise ValueError("integral: se resuelve con el motor, no se evalúa")
    raise ValueError(f"no evaluable: {type(e).__name__}")


def _croot(z: complex, degree: int) -> complex:
    """Principal ``degree``-th root on the whole plane."""
    return cmath.exp(cmath.log(z) / degree)


# ---------------------------------------------------------------------------
# printing
# ---------------------------------------------------------------------------

_PREC = {Add: 1, Sub: 1, Mul: 2, Div: 2, Neg: 3, Pow: 4}
_LATEX_FN = {
    "cot": r"\cot", "sec": r"\sec", "csc": r"\csc",
    "sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "asin": r"\arcsen", "acos": r"\arccos",
    "atan": r"\arctan", "sinh": r"\operatorname{senh}", "cosh": r"\operatorname{cosh}",
    "tanh": r"\operatorname{tanh}", "coth": r"\operatorname{cothg}",
    "sech": r"\operatorname{sech}", "csch": r"\operatorname{csch}",
    "asinh": r"\operatorname{arcsenh}", "acosh": r"\operatorname{arccosh}",
    "atanh": r"\operatorname{arctanh}",
    "exp": r"\exp", "ln": r"\ln", "log10": r"\log_{10}",
    "log": r"\log", "abs": r"\left|", "sign": r"\operatorname{sgn}", "floor": r"\lfloor",
    "ceil": r"\rceil",
}
_PRETTY_FN = {
    "cot": "cotg", "sec": "sec", "csc": "cosec",
    "sin": "sen", "cos": "cos", "tan": "tan", "asin": "arcsen", "acos": "arccos",
    "atan": "arctan", "sinh": "senh", "cosh": "cosh", "tanh": "tanh",
    "coth": "cotgh", "sech": "sech", "csch": "cschg",
    "asinh": "arcsenh", "acosh": "arccosh", "atanh": "arctanh",
    "exp": "exp",
    "ln": "ln", "log10": "log₁₀", "log": "log", "abs": "|", "sign": "sgn",
    "floor": "⌊", "ceil": "⌉",
}
_SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻", "n": "ⁿ"}


def _prec(e: Expr) -> int:
    if isinstance(e, (int, Fraction)):
        return 1 if e < 0 else (2 if Fraction(e).denominator != 1 else 5)
    if isinstance(e, Num):
        return 1 if e.value < 0 else (2 if e.value.denominator != 1 else 5)
    if isinstance(e, (Sym, Const)):
        return 5
    return _PREC.get(type(e), 5)


def _frac(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _print(e: Expr, power: str, style: str) -> str:
    def wrap(child: Expr, need: int, strict: bool = False) -> str:
        s = _print(child, power, style)
        p = _prec(child)
        return f"({s})" if p < need or (strict and p == need) else s

    if isinstance(e, (int, Fraction)):
        # exact_value() returns a bare Fraction; printing it must not raise. A bare
        # int is accepted for the same reason and not for symmetry's sake: `text(2)`
        # raising while `text(Fraction(2, 1))` returns "2" is the kind of asymmetry
        # that turns a caller's ordinary `0` into «no se sabe imprimir int» from
        # four frames away, which is exactly how a Taylor centre of 0 failed.
        return _frac(Fraction(e))
    if isinstance(e, Num):
        return _frac(e.value)
    if isinstance(e, Sym):
        return e.name
    if isinstance(e, Const):
        if style == "pretty":
            return {"pi": "π", "e": "e", "i": "i"}[e.name]
        return e.name
    if isinstance(e, Neg):
        if style == "latex":
            return "-" + wrap(e.arg, 2)
        return "-" + wrap(e.arg, 2)
    if isinstance(e, Pow):
        base = wrap(e.base, 5)
        if style == "latex":
            return f"{base}^{{{_print(e.exponent, power, style)}}}"
        if style == "pretty" and isinstance(e.exponent, Num) and e.exponent.value.denominator == 1:
            digits = str(abs(int(e.exponent.value)))
            if all(d in _SUP for d in digits) and len(digits) <= 2:
                # the superscript minus: a plain "-" printed x^(-1) as «x-¹», which
                # reads as x minus one (found 2026-10-06)
                sign = "⁻" if e.exponent.value < 0 else ""
                return f"{base}{sign}{''.join(_SUP[d] for d in digits)}"
        return f"{base}{power}{wrap(e.exponent, 4 if power == '^' else 5)}"
    if isinstance(e, Root):
        inner = _print(e.radicand, power, style)
        if style == "latex":
            return rf"\sqrt[{e.degree}]{{{inner}}}" if e.degree != 2 else rf"\sqrt{{{inner}}}"
        if e.degree == 2:
            if style != "pretty":
                return f"sqrt({inner})"
            # «√x² + 1» reads as (√x²) + 1: a compound radicand keeps its
            # parentheses (found 2026-10-06)
            if isinstance(e.radicand, (Sym, Num, Const, Call)) and not (
                    isinstance(e.radicand, Num) and e.radicand.value.denominator != 1):
                return f"√{inner}"
            return f"√({inner})"
        return f"raiz({inner}, {e.degree})"
    if isinstance(e, Call):
        if e.name == "abs":
            if style == "text":
                # the canonical form must round-trip through parse(), and "|x|"
                # is not in the grammar, so the call form is kept here
                return f"abs({_print(e.args[0], power, style)})"
            # "|(" is unreadable and a stray parenthesis would dangle, so the
            # bar closes over a self-contained argument
            inner = _print(e.args[0], power, style)
            if isinstance(e.args[0], (Add, Sub, Mul, Div)):
                inner = f"({inner})"
            if style == "latex":
                return rf"\left|{inner}\right|"
            return f"|{inner}|"
        name = _LATEX_FN.get(e.name, e.name) if style == "latex" else (
            _PRETTY_FN.get(e.name, e.name) if style == "pretty" else e.name)
        args = ", ".join(_print(a, power, style) for a in e.args)
        if style == "latex" and e.name == "log" and len(e.args) == 2:
            return rf"\log_{{{_print(e.args[0], power, style)}}} {_print(e.args[1], power, style)}"
        if style == "pretty" and e.name == "log" and len(e.args) == 2:
            return f"log_{_print(e.args[0], power, style)}({_print(e.args[1], power, style)})"
        return f"{name}({args})"
    if isinstance(e, Add):
        return f"{wrap(e.left, 1)} + {wrap(e.right, 1)}"
    if isinstance(e, Sub):
        return f"{wrap(e.left, 1)} - {wrap(e.right, 1, strict=True)}"
    if isinstance(e, Mul):
        dot = "·" if style == "pretty" else "*"
        return f"{wrap(e.left, 2)}{dot}{wrap(e.right, 2)}"
    if isinstance(e, Div):
        # the denominator always needs its parentheses when it is a product,
        # otherwise "x^2/(3y)" would read as "x^2/3 * y"
        return f"{wrap(e.left, 2)}/{wrap(e.right, 2, strict=True)}"
    if isinstance(e, Integral):
        body = _print(e.integrand, power, style)
        lo = _print(e.lower, power, style) if e.lower is not None else None
        hi = _print(e.upper, power, style) if e.upper is not None else None
        if style == "pretty":
            bounds = f"[{lo},{hi}]" if lo is not None and hi is not None else ""
            return f"∫{bounds} {body} d{e.var}"
        if lo is None or hi is None:
            return f"integral({body}, {e.var})"
        return f"integral({body}, {e.var}, {lo}, {hi})"
    if isinstance(e, Limit):
        body, point = _print(e.expr, power, style), _print(e.point, power, style)
        side = e.side or ""
        if style == "pretty":
            # the side goes after the point: x -> 0+, never x+ -> 0
            return f"lím {e.var}→{point}{side} {body}"
        tail = f", '{side}'" if side else ""
        return f"limite({body}, {e.var}, {point}{tail})"
    if isinstance(e, Sum):
        body = _print(e.body, power, style)
        lo, hi = _print(e.lower, power, style), _print(e.upper, power, style)
        if style == "pretty":
            return f"Σ[{lo},{hi}]{e.var} {body}"
        return f"suma({body}, {e.var}, {lo}, {hi})"
    if isinstance(e, Derivative):
        body = _print(e.expr, power, style)
        order = max(e.order, 1)
        if style == "pretty":
            if order == 1:
                return f"d{body}/d{e.var}"
            num = "".join(_SUP[d] for d in str(order)) if all(d in _SUP for d in str(order)) else str(order)
            return f"d{num}{body}/d{e.var}{num}"
        tail = "" if order == 1 else f", {order}"
        return f"derivada({body}, {e.var}{tail})"
    raise no_rule(f"no se sabe imprimir {type(e).__name__}")


def text(e: Expr) -> str:
    """Canonical ASCII form. ``parse(text(e)) == e`` for every node type.

    A bare ``int``/``Fraction`` is printed as well, and that is a contract rather
    than an accident: ``exact_value`` returns a ``Fraction``, so printing the answer
    of ``exact_value`` with ``text`` is a round trip the test suite performs on every
    exact value the engine produces. Refusing it here would have been tidier and
    wrong.
    """
    out = _print(e, "^", "text")
    if len(out) > MAX_TEXT:
        raise invalid("EXPRESSION_LIMIT", f"la expresión crece a más de {MAX_TEXT} caracteres")
    return out


def pretty(e: Expr) -> str:
    """Unicode notation for the preview panel (§5.1)."""
    out = _print(e, "^", "pretty")
    if len(out) > MAX_TEXT:
        raise invalid("EXPRESSION_LIMIT", f"la expresión crece a más de {MAX_TEXT} caracteres")
    return out


def latex(e: Expr) -> str:
    out = _print(e, "^", "latex")
    if len(out) > MAX_TEXT:
        raise invalid("EXPRESSION_LIMIT", f"la expresión crece a más de {MAX_TEXT} caracteres")
    return out


def preview(source: str) -> str:
    """Live preview for the formula editor: canonical form or a Spanish error.

    Never raises: the editor shows the message under the field (§5.1).
    """
    try:
        return pretty(parse(source))
    except ValidationError as exc:
        return f"⚠ {exc.message}"


# ---------------------------------------------------------------------------
# bridge to the E0.1 engine (single variable only, by its design)
# ---------------------------------------------------------------------------


#: the name pi takes inside the one-variable engine (see _to_symbolic)
PI_SIMBOLICO = "pi"


def to_symbolic(e: Expr):
    """Convert to ``symbolic.expr.Expr`` to reuse derive/integrate/solve/normal.

    Only expressions that E0.1 can represent are accepted: one variable, no
    ``pi``/``e``/``i`` and no calculus object. Anything else raises
    ``UnsupportedError`` with a reason in Spanish, never a silent fallback.
    """
    from academic_core.domain.engineering.symbolic import expr as sx

    return _to_symbolic(e, sx, set())


def _to_symbolic(e: Expr, sx, seen: set[str]):
    if isinstance(e, Num):
        return sx.Num(e.value)
    if isinstance(e, Sym):
        return sx.Sym(e.name)
    if isinstance(e, Const):
        if e.name == "pi":
            # pi travels as a symbol: the rules treat it as the constant it is (it
            # does not depend on the variable), symbolic.numeric gives it its value,
            # and from_symbolic turns it back into the constant. The parser never
            # produces a VARIABLE called «pi», so the name cannot collide. Without
            # this, cos(x + pi/6) could be neither differentiated nor integrated
            # (found 2026-10-06).
            return sx.Sym(PI_SIMBOLICO)
        raise no_rule(
            f"«{e.name}» solo se puede pasar al motor de una variable dentro de una potencia "
            f"como e^x, no suelto"
        )
    if isinstance(e, Neg):
        return sx.Neg(_to_symbolic(e.arg, sx, seen))
    if isinstance(e, Add):
        return sx.Add(_to_symbolic(e.left, sx, seen), _to_symbolic(e.right, sx, seen))
    if isinstance(e, Sub):
        return sx.Sub(_to_symbolic(e.left, sx, seen), _to_symbolic(e.right, sx, seen))
    if isinstance(e, Mul):
        return sx.Mul(_to_symbolic(e.left, sx, seen), _to_symbolic(e.right, sx, seen))
    if isinstance(e, Div):
        return sx.Div(_to_symbolic(e.left, sx, seen), _to_symbolic(e.right, sx, seen))
    if isinstance(e, Pow):
        # e^u must become exp(u): E0.1 has no rule for exp(1)^u ("base y
        # exponente variables"), so a literal exp(1) would be a dead end.
        if isinstance(e.base, Const) and e.base.name == "e":
            return sx.Fn("exp", _to_symbolic(e.exponent, sx, seen))
        if isinstance(e.base, Const) and e.base.name == "pi" and variables(e.exponent):
            # pi^u = exp(u·ln pi): the a^x rule of E0.1 wants a numeric base
            return sx.Fn("exp", sx.Mul(_to_symbolic(e.exponent, sx, seen),
                                       sx.Fn("log", sx.Sym(PI_SIMBOLICO))))
        if isinstance(e.base, Const) and e.base.name != "pi":
            raise no_rule(f"«{e.base.name}» elevado a algo no tiene forma en el motor de una variable")
        return sx.Pow(_to_symbolic(e.base, sx, seen), _to_symbolic(e.exponent, sx, seen))
    if isinstance(e, Root):
        if e.degree == 2:
            return sx.Fn("sqrt", _to_symbolic(e.radicand, sx, seen))
        # an n-th root is the power 1/n, which the power rule already knows: x^(1/3)
        # could be neither derived nor integrated before (found 2026-10-06)
        return sx.Pow(_to_symbolic(e.radicand, sx, seen),
                      sx.Num(Fraction(1, e.degree)))
    if isinstance(e, Call):
        name = {"ln": "log", "log10": None, "log": None, "abs": "abs"}.get(e.name, e.name)
        if name is None or len(e.args) != 1:
            raise no_rule(f"«{e.name}» no se puede pasar al motor de una variable")
        return sx.Fn(name, _to_symbolic(e.args[0], sx, seen))
    raise no_rule(f"«{type(e).__name__}» no se puede pasar al motor de una variable")


def from_symbolic(sxe):
    """Convert an ``symbolic.expr.Expr`` back into the multivariate layer."""
    from academic_core.domain.engineering.symbolic import expr as sx

    _BINARY = {sx.Add: Add, sx.Sub: Sub, sx.Mul: Mul, sx.Div: Div}

    def conv(e):
        if isinstance(e, sx.Num):
            return Num(e.value)
        if isinstance(e, sx.Sym):
            return PI if e.name == PI_SIMBOLICO else Sym(e.name)
        if isinstance(e, sx.Neg):
            return Neg(conv(e.arg))
        if isinstance(e, sx.Fn):
            if e.name == "log":
                return Call("ln", (conv(e.arg),))
            if e.name == "sqrt":
                return Root(2, conv(e.arg))
            if e.name == "exp":
                return _exp_as_power(conv(e.arg))
            if e.name in _FUNCTIONS:
                return Call(e.name, (conv(e.arg),))
            raise no_rule(f"«{e.name}» no tiene equivalente en varias variables")
        if isinstance(e, sx.Pow):
            return _make_pow(conv(e.base), conv(e.exponent))
        return _BINARY[type(e)](conv(e.left), conv(e.right))

    return conv(sxe)


def _exp_as_power(arg: Expr) -> Expr:
    """``exp(u)`` came from ``e^u``; only ``exp(1)`` is a bare ``e``.

    A bare ``exp(2)`` from E0.1 is *not* re-read as ``e^2``: the two spellings
    mean different exact things and the honest form of ``exp(2)`` here is a
    call, not a power.
    """
    value = exact_value(arg)
    if value is not None and value == 1:
        return E
    return Call("exp", (arg,))
