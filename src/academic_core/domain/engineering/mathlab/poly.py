# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: multivariate exact normal form (the equivalence engine).

This is the "corrector por equivalencia" of §7 and the second path of §5.3 for
anything polynomial. Two answers are accepted when they are the *same
polynomial*, so ``2x+2x`` matches ``4x`` and ``1/2`` matches ``0,5``.

Normal form
-----------

A multivariate polynomial is a finite map ``coefficient -> monomial`` over
exact ``Fraction`` arithmetic, where a monomial is a sorted tuple of
``(variable, exponent)``. That representation is canonical, so two polynomials
are equal exactly when their normal forms are equal: the check is *exact*, not
a numerical coincidence. Exponents are always ``>= 1`` in a stored monomial.

Atoms
-----

A subexpression that is not rational arithmetic (``sin(x)``, ``pi``,
``sqrt(2)``, ``x^y``) is an **atom**, keyed by its canonical printed text and
stored as a pseudo-variable named ``"@<text>"``. Atoms are treated as
independent indeterminates. Two consequences, both deliberate:

- ``x*sin(x)`` and ``sin(x)*x`` are the same polynomial (same atoms) — correct;
- ``x^2*pi`` and ``3.14*x^2`` are *not* recognised as equal, because ``pi`` is
  an atom, not a number. That is the honest answer: they are not the same
  expression, and the numeric second path decides whether they are close.

Fractions and roots are folded by :mod:`mvexpr` at parse time
(``sqrt(4)`` is already ``2``), so exact numeric atoms do not arise in
practice; ``simplify`` exists for expressions that only become exact after
algebra.

Rational functions
------------------

:func:`as_ratio` normalises an expression as a rational function of one
variable, with the other variables as atoms. That is what lets the
equivalence check compare ``(x^2-1)/(x-1)`` with ``x+1`` — while
:func:`excluded_values` reports ``x = 1`` as removed from the domain, which the
UI prints (§5.7: a hypothesis is checked, not assumed).

Bounds
------

``MAX_TERMS`` (monomials per polynomial), ``MAX_ATOMS`` and ``MAX_POWER`` keep
the work bounded; crossing one raises a D2 ``ValidationError`` rather than
growing without limit (§5.4, §5.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError, ValidationError

MAX_TERMS = 512
MAX_ATOM_BYTES = 4096
MAX_POWER = 64
MAX_TOTAL_DEGREE = 64

Monomial = tuple[tuple[str, int], ...]  # sorted by name, every exponent >= 1
Polynomial = dict[Monomial, Fraction]  # coefficient per monomial

ZERO_MONO: Monomial = ()
ONE_MONO: Monomial = ()

ATOM_PREFIX = "@"


def invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")


# ---------------------------------------------------------------------------
# monomial arithmetic
# ---------------------------------------------------------------------------


def mono_mul(a: Monomial, b: Monomial) -> Monomial:
    out: dict[str, int] = {}
    for var, exp in (*a, *b):
        out[var] = out.get(var, 0) + exp
    return tuple(sorted((v, e) for v, e in out.items() if e))


def mono_div(a: Monomial, b: Monomial) -> Monomial | None:
    """``a / b`` when every exponent of ``b`` is available in ``a``."""
    out = dict(a)
    for var, exp in b:
        left = out.get(var, 0) - exp
        if left < 0:
            return None
        if left:
            out[var] = left
        else:
            out.pop(var, None)
    return tuple(sorted(out.items()))


def mono_degree(m: Monomial) -> int:
    return sum(exp for _, exp in m)


def mono_exp(m: Monomial, var: str) -> int:
    for name, exp in m:
        if name == var:
            return exp
    return 0


# ---------------------------------------------------------------------------
# polynomial arithmetic
# ---------------------------------------------------------------------------


def const(value) -> Polynomial:
    c = Fraction(value)
    return {} if c == 0 else {ONE_MONO: c}


def is_zero(p: Polynomial) -> bool:
    return not p


def degree_in(p: Polynomial, var: str) -> int:
    return max((mono_exp(m, var) for m in p), default=0)


def add(a: Polynomial, b: Polynomial, sign: int = 1) -> Polynomial:
    out = dict(a)
    for mono, coeff in b.items():
        total = out.get(mono, Fraction(0)) + sign * coeff
        if total == 0:
            out.pop(mono, None)
        else:
            out[mono] = total
    return _check(out)


def scale(a: Polynomial, factor) -> Polynomial:
    k = Fraction(factor)
    return {} if k == 0 else {m: c * k for m, c in a.items()}


def mul(a: Polynomial, b: Polynomial) -> Polynomial:
    if not a or not b:
        return {}
    out: Polynomial = {}
    for ma, ca in a.items():
        for mb, cb in b.items():
            mono = mono_mul(ma, mb)
            if mono_degree(mono) > MAX_TOTAL_DEGREE:
                raise invalid("EXPRESSION_LIMIT", f"grado total mayor que {MAX_TOTAL_DEGREE}")
            out[mono] = out.get(mono, Fraction(0)) + ca * cb
    return _check({m: c for m, c in out.items() if c != 0})


def _check(p: Polynomial) -> Polynomial:
    if len(p) > MAX_TERMS:
        raise invalid("EXPRESSION_LIMIT", f"más de {MAX_TERMS} términos en la forma normal")
    return p


def variable(name: str) -> Polynomial:
    return _check({((name, 1),): Fraction(1)})


def atom(key: str) -> Polynomial:
    """An indeterminate named by its canonical text, e.g. ``@sin(x)``."""
    if len(key) > MAX_ATOM_BYTES:
        raise invalid("EXPRESSION_LIMIT", "átomo demasiado largo")
    return _check({((ATOM_PREFIX + key, 1),): Fraction(1)})


def is_atom(name: str) -> bool:
    return name.startswith(ATOM_PREFIX)


def atom_text(name: str) -> str:
    return name[len(ATOM_PREFIX):] if is_atom(name) else name


# ---------------------------------------------------------------------------
# polynomial -> expression
# ---------------------------------------------------------------------------


def to_expr(p: Polynomial) -> mx.Expr:
    """``as_poly`` read backwards: the polynomial as the expression it came from.

    Total on the polynomials this module produces, and round-trips: an atom is
    re-parsed from its canonical text, so ``as_poly(to_expr(q)) == q``. That is
    what lets the equation solver multiply by a denominator and keep working on
    expressions, instead of on a normal form it can no longer print.
    """
    if is_zero(p):
        return mx.ZERO
    piezas: list[mx.Expr] = []
    # the constant goes last, so the result reads the way a person writes it:
    # «x^2 - 1» and not «-1 + x^2». to_expr is not the pretty-printer — callers
    # normalise when they need to — but it should not be gratuitously ugly.
    for monomio, coeficiente in sorted(p.items(), key=lambda kv: (not kv[0], kv[0])):
        if coeficiente == 0:
            continue
        producto = mx.ONE
        for nombre, exponente in monomio:
            factor = (mx.parse(atom_text(nombre)) if is_atom(nombre)
                      else mx.Sym(nombre))
            if exponente != 1:
                factor = mx.Pow(factor, mx.Num(Fraction(exponente)))
            # accumulate: assigning instead of multiplying silently drops every
            # factor but the last, which turns 2*sin(x)*cos(x) into 2*sin(x)
            producto = factor if producto == mx.ONE else mx.Mul(producto, factor)
        piezas.append(_con_signo(coeficiente, producto))
    if not piezas:
        return mx.ZERO
    if len(piezas) == 1:
        return piezas[0]
    # Add is a binary node, so the sum is folded left rather than splatted
    total = piezas[0]
    for siguiente in piezas[1:]:
        total = mx.Add(total, siguiente)
    return total


def _con_signo(coeficiente: Fraction, producto: mx.Expr) -> mx.Expr:
    """``-1·y`` as ``-y``: a negative coefficient carried inside the product is
    invisible to every pattern that reads terms by sign.

    ``trig``'s term reader sees ``1*cos(x) + (-1)*sin(x)`` as two positive terms,
    so the phase case cannot match it and the normaliser does not fold it either.
    Writing the sign where the reader looks for it is the difference between an
    expression that is *printed* correctly and one that is also *read* correctly.
    """
    if coeficiente == 1:
        return producto
    if coeficiente == -1:
        return mx.Neg(producto)
    if coeficiente < 0:
        return mx.Neg(mx.Mul(mx.Num(-coeficiente), producto))
    return mx.Mul(mx.Num(coeficiente), producto)


# ---------------------------------------------------------------------------
# expression -> polynomial
# ---------------------------------------------------------------------------


def as_poly(e: mx.Expr, *, expand: bool = True) -> Polynomial:
    """Exact normal form of ``e`` as a polynomial over atoms.

    Total by construction: a function, a constant, a non-integer power or a
    division that is not by a constant becomes one atom. Callers that must not
    accept an atom (the equivalence check wants to *know* a difference is
    genuinely zero) use :func:`real_variables` to inspect what got atomised.

    With ``expand=False`` a parenthesised power is kept whole (``(x+1)^2`` is
    the atom ``@(x + 1)^2``), which preserves the student's structure; with
    ``expand=True`` it becomes a real polynomial.
    """
    return _as_poly(e, 0, expand=expand)


def _as_poly(e: mx.Expr, depth: int, *, expand: bool = True) -> Polynomial:
    if depth > mx.MAX_DEPTH:
        raise invalid("EXPRESSION_LIMIT", "expresión demasiado anidada")
    if isinstance(e, mx.Num):
        return const(e.value)
    if isinstance(e, mx.Sym):
        return variable(e.name)
    if isinstance(e, mx.Add):
        return add(_as_poly(e.left, depth + 1, expand=expand),
                   _as_poly(e.right, depth + 1, expand=expand))
    if isinstance(e, mx.Sub):
        return add(_as_poly(e.left, depth + 1, expand=expand),
                   _as_poly(e.right, depth + 1, expand=expand), -1)
    if isinstance(e, mx.Neg):
        return scale(_as_poly(e.arg, depth + 1, expand=expand), -1)
    if isinstance(e, mx.Mul):
        return mul(_as_poly(e.left, depth + 1, expand=expand),
                   _as_poly(e.right, depth + 1, expand=expand))
    if isinstance(e, mx.Div):
        bottom = _as_poly(e.right, depth + 1, expand=expand)
        if len(bottom) == 1 and ONE_MONO in bottom:
            return scale(_as_poly(e.left, depth + 1, expand=expand), 1 / bottom[ONE_MONO])
        return _atom(e)
    if isinstance(e, mx.Pow):
        if not expand:
            return _atom(e)
        return _as_pow(e, depth, expand=True)
    if isinstance(e, mx.Call):
        # a call is an atom only if every argument is: sin(x) is one, sin(x)+1 is not
        return atom(mx.text(e))
    return _atom(e)


def _as_pow(e: mx.Pow, depth: int, *, expand: bool) -> Polynomial:
    degree = mx.exact_integer(e.exponent)
    if degree is None or not 0 <= degree <= MAX_POWER:
        return _atom(e)
    if isinstance(e.base, mx.Sym):
        out: Polynomial = const(1)
        for _ in range(degree):
            out = mul(out, variable(e.base.name))
        return out
    if isinstance(e.base, mx.Num):
        return const(e.base.value ** degree)
    if degree == 0:
        return const(1)
    if degree == 1:
        return _as_poly(e.base, depth + 1, expand=expand)
    if not expand:
        return _atom(e)
    # binomial expansion of (sum of polynomials)^n, by repeated multiplication
    base = _as_poly(e.base, depth + 1, expand=expand)
    out = const(1)
    for _ in range(degree):
        out = mul(out, base)
    return out


def _atom(e: mx.Expr) -> Polynomial:
    return atom(mx.text(e))


def real_variables(p: Polynomial) -> set[str]:
    """Variable names in the normal form, with atom pseudo-names removed."""
    return {v for m in p for v, _ in m if not is_atom(v)}


def atoms_of(p: Polynomial) -> set[str]:
    return {atom_text(v) for m in p for v, _ in m if is_atom(v)}


# ---------------------------------------------------------------------------
# rational form
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ratio:
    """``numerator / denominator`` in exact normal form.

    ``var`` is the variable the division was taken over; the other variables
    are atoms. ``denominator`` is never zero.
    """

    numerator: Polynomial
    denominator: Polynomial
    var: str
    #: values of ``var`` removed by a cancelled factor, e.g. ``1`` for
    #: ``(x^2-1)/(x-1) = x+1``. Computed *before* cancellation, so the UI can
    #: print the hypothesis instead of losing it (§5.7).
    excluded: frozenset[Fraction] = frozenset()

    def is_constant_ratio(self) -> bool:
        return len(self.denominator) == 1 and ONE_MONO in self.denominator

    def excluded_values(self) -> frozenset[Fraction]:
        return self.excluded


def excluded_of(den: Polynomial, var: str) -> set[Fraction]:
    """Values of ``var`` that make ``den`` zero, when they are provable.

    Only a *linear* dependence on ``var`` is solved, because only that has an
    exact answer by hand: the denominator is written ``a·v + b`` and the
    excluded value is ``-b/a`` when it is rational. A quadratic is left to the
    numeric path rather than guessed — reporting a wrong pole would be worse
    than reporting none.
    """
    if degree_in(den, var) != 1:
        return set()
    if total_degree(den) > 1:
        return set()  # e.g. 1/(x*y) depends on y too: not a value of x
    lead = Fraction(0)
    rest = Fraction(0)
    for mono, coeff in den.items():
        if mono_exp(mono, var) == 1:
            lead += coeff
        else:
            rest += coeff
    if lead == 0:
        return set()
    root = -rest / lead
    return {root} if isinstance(root, Fraction) else set()


def as_ratio(e: mx.Expr, var: str) -> Ratio | None:
    """Normalise ``e`` as a rational function of ``var``, or ``None``.

    ``None`` means "not rational in ``var``" (a genuinely non-rational
    expression, or the bounds were hit); the caller then falls back to the
    numeric path of §5.3.

    A sum of fractions (``1/x + 1/y``) is brought to a common denominator here
    rather than refused, because that is the whole point of having a rational
    normal form.
    """
    parts = _as_ratio_parts(e, var, 0)
    if parts is None:
        return None
    numerator, denominator = parts
    if not denominator:
        return None
    removed = excluded_of(denominator, var)  # before cancelling: the hypothesis
    numerator, denominator = _cancel(numerator, denominator)
    if is_zero(denominator):
        return None
    return Ratio(numerator, denominator, var, frozenset(removed))


def _as_ratio_parts(e: mx.Expr, var: str, depth: int
                    ) -> tuple[Polynomial, Polynomial] | None:
    """``(numerator, denominator)`` with a common denominator, or ``None``."""
    if depth > mx.MAX_DEPTH:
        raise invalid("EXPRESSION_LIMIT", "expresión demasiado anidada")
    if isinstance(e, (mx.Add, mx.Sub)):
        left = _as_ratio_parts(e.left, var, depth + 1)
        right = _as_ratio_parts(e.right, var, depth + 1)
        if left is None or right is None:
            return None
        ln, ld, rn, rd = left[0], left[1], right[0], right[1]
        return add(mul(ln, rd), mul(rn, ld), 1 if isinstance(e, mx.Add) else -1), mul(ld, rd)
    if isinstance(e, mx.Mul):
        left = _as_ratio_parts(e.left, var, depth + 1)
        right = _as_ratio_parts(e.right, var, depth + 1)
        if left is None or right is None:
            return None
        return mul(left[0], right[0]), mul(left[1], right[1])
    if isinstance(e, mx.Neg):
        inner = _as_ratio_parts(e.arg, var, depth + 1)
        return None if inner is None else (scale(inner[0], -1), inner[1])
    if isinstance(e, mx.Div):
        top = _as_ratio_parts(e.left, var, depth + 1)
        bottom = _as_ratio_parts(e.right, var, depth + 1)
        if top is None or bottom is None or not bottom[0]:
            return None
        return mul(top[0], bottom[1]), mul(top[1], bottom[0])
    return as_poly(e), const(1)


def _cancel(num: Polynomial, den: Polynomial) -> tuple[Polynomial, Polynomial]:
    """Divide out the exact common polynomial factor, then fix the sign.

    ``(x^2-1)/(x-1)`` reduces to ``x+1`` and keeps the *excluded value* in
    :meth:`Ratio.excluded_values`, computed before this point by the caller.
    """
    if len(den) == 1 and ONE_MONO in den:
        return num, den
    num, den, divided = _divide_exact(num, den)
    if divided and not is_zero(den) and len(den) == 1 and ONE_MONO in den and den[ONE_MONO] < 0:
        num, den = scale(num, -1), scale(den, -1)
    return num, den


def _divide_exact(num: Polynomial, den: Polynomial
                  ) -> tuple[Polynomial, Polynomial, bool]:
    """Cancel the common factor, returning ``(numerator, denominator, done)``.

    ``done`` says the division was **exact**, so the caller knows the result is
    a simplification and not a guess. Only two cases are attempted, both exact
    and both common in exercises: a constant denominator, and a linear
    denominator in one variable. A wider divisor is left untouched rather than
    half-simplified, and the excluded value is still reported by the caller.
    """
    shared = _shared_monomial(num, den)
    if shared:
        num = {mono_div(m, shared) or ZERO_MONO: c for m, c in num.items()}
        den = {mono_div(m, shared) or ZERO_MONO: c for m, c in den.items()}
        if not num or is_zero(den):
            return num, den, False
    if len(den) == 1:
        term = next(iter(den))
        if term == ONE_MONO:
            return scale(num, 1 / den[ONE_MONO]), const(1), True
        return num, den, False  # a monomial divisor in variables: leave it
    if _is_linear(den):
        var = _single_var(den)
        if var is not None and degree_in(num, var) >= degree_in(den, var):
            quotient, remainder = _divide_linear(num, den, var)
            if is_zero(remainder):  # exact: no leftover term
                return quotient, const(1), True
    return num, den, False


def all_vars(p: Polynomial) -> set[str]:
    return {v for m in p for v, _ in m}


def total_degree(p: Polynomial) -> int:
    return max((mono_degree(m) for m in p), default=0)


def _is_linear(p: Polynomial) -> bool:
    return total_degree(p) <= 1


def _single_var(p: Polynomial) -> str | None:
    real = {v for v in all_vars(p) if not is_atom(v)}
    return next(iter(real)) if len(real) == 1 else None


def _divide_linear(num: Polynomial, den: Polynomial, var: str
                   ) -> tuple[Polynomial, Polynomial]:
    """Exact synthetic division by a linear ``den``, in ``var``.

    ``den = a·v + b`` with ``a``, ``b`` polynomials in the other variables.
    At each step the leading term of the remainder must be divisible by ``a``;
    if it is not, the division is inexact and the original polynomial is
    returned as the remainder, so the caller leaves the expression alone
    instead of showing a wrong cancellation.
    """
    deg_den = degree_in(den, var)
    if deg_den != 1:
        return {}, num
    lead_mono = max(den, key=lambda m: mono_exp(m, var))
    a = den[lead_mono]
    if a == 0:
        return {}, num
    rest = dict(num)
    quotient: Polynomial = {}
    for _ in range(MAX_POWER + 2):
        if not rest:
            break
        top = max(rest, key=lambda m: mono_exp(m, var))
        if mono_exp(top, var) < deg_den:
            break
        term = mono_div(top, lead_mono)
        if term is None:
            return {}, num
        coeff = rest[top]
        if coeff % a != 0:
            return {}, num
        factor = coeff / a
        quotient = add(quotient, {term: factor})
        # mul() accumulates: a dict comprehension would collide two terms of
        # the divisor that share the multiplied monomial
        rest = add(rest, mul({term: factor}, den), -1)
    return quotient, rest


def _shared_monomial(a: Polynomial, b: Polynomial) -> Monomial:
    """Greatest monomial dividing *every* term of both polynomials.

    A variable is in the shared monomial only if it appears in **all** the
    terms of **both** polynomials: a term that lacks it has exponent ``0``, and
    a ``0`` kills the factor. Getting this wrong would let ``x²−1`` be
    "cancelled" by ``x−1`` down to ``x−1``, which is a wrong answer.
    """
    out: list[tuple[str, int]] = []
    for var in sorted(all_vars(a) & all_vars(b)):
        exp = min(min(mono_exp(m, var) for m in a), min(mono_exp(m, var) for m in b))
        if exp > 0:
            out.append((var, exp))
    return tuple(out)


# ---------------------------------------------------------------------------
# equality
# ---------------------------------------------------------------------------


def same_ratio(a: Ratio, b: Ratio) -> bool:
    """Exact equality of rational functions: cross-multiply."""
    if a.var != b.var:
        return False
    return mul(a.numerator, b.denominator) == mul(b.numerator, a.denominator)
