# SPDX-License-Identifier: MIT
"""E0.1 canonical normal form (simplification) with recorded rules.

An expression becomes a *sum of monomials*: an exact ``Fraction``
coefficient times a product of atoms raised to ``Fraction`` exponents.
An atom is:

- a symbol
- a function application, with its argument normalised
- the base of a power that cannot be expanded, e.g. a sum raised to a
  negative power
- a power with a symbolic exponent

Every rule that actually changes something is recorded by name, at the
node where it fired:

- plegado de constantes
- agrupar términos semejantes
- propiedad distributiva
- potencias de igual base
- potencia de un monomio
- desarrollo de potencia
- cociente de monomios
- eliminar términos nulos
- elemento neutro (1·u = u, u + 0 = u), producto por cero
- cancelación de factores (válida si el factor ≠ 0): u/u = 1 changes the
  domain, so the condition is stated in the rule itself
- orden canónico de términos y factores (when only the order changed)

With a ``StepLog`` the simplifier records ``before → rule → after`` for
every node where a rule fired. Without one it only returns the rule
names. The result is deterministic: terms are ordered by descending
degree in the main variable, then by printed atoms.

Bounds: ``MAX_TERMS`` terms per node, integer power expansion only up
to ``MAX_EXPAND``. Anything larger is refused with ``EXPRESSION_LIMIT``.
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.symbolic.expr import (
    ZERO,
    Add,
    Div,
    Expr,
    Fn,
    Mul,
    Neg,
    Num,
    Pow,
    Sub,
    Sym,
    exact_value,
    invalid,
    text,
)

CANCEL = "cancelación de factores (válida si el factor ≠ 0)"
MAX_TERMS = 256
MAX_EXPAND = 8

Monomial = tuple  # ((atom_key, Fraction exponent), ...) sorted by key


class _Poly:
    __slots__ = ("terms", "atoms")

    def __init__(self, terms=None, atoms=None):
        self.terms: dict = terms if terms is not None else {}
        self.atoms: dict = atoms if atoms is not None else {}


def _const(v: Fraction) -> _Poly:
    return _Poly({(): v} if v != 0 else {}, {})


def _merge_atoms(a: dict, b: dict) -> dict:
    out = dict(a)
    out.update(b)
    return out


def _mono_mul(m1: Monomial, m2: Monomial, fired: list) -> Monomial:
    exps = dict(m1)
    for key, e in m2:
        if key in exps:
            if "potencias de igual base" not in fired:
                fired.append("potencias de igual base")
            if exps[key] + e == 0 and CANCEL not in fired:
                fired.append(CANCEL)  # u^a·u^(-a) = 1 only where u ≠ 0: the condition is part of the rule name
            exps[key] += e
        else:
            exps[key] = e
    return tuple(sorted((k, e) for k, e in exps.items() if e != 0))


def _add(p: _Poly, q: _Poly, sign: int, fired: list) -> _Poly:
    if (not p.terms or not q.terms) and "elemento neutro (u + 0 = u)" not in fired:
        fired.append("elemento neutro (u + 0 = u)")
    terms = dict(p.terms)
    for m, c in q.terms.items():
        if m in terms:
            rule = "plegado de constantes" if m == () else "agrupar términos semejantes"
            if rule not in fired:
                fired.append(rule)
            terms[m] = terms[m] + sign * c
        else:
            terms[m] = sign * c
    return _clean(_Poly(terms, _merge_atoms(p.atoms, q.atoms)), fired)


def _clean(p: _Poly, fired: list) -> _Poly:
    zeros = [m for m, c in p.terms.items() if c == 0]
    if zeros:
        if "eliminar términos nulos" not in fired:
            fired.append("eliminar términos nulos")
        for m in zeros:
            del p.terms[m]
    if len(p.terms) > MAX_TERMS:
        raise invalid("EXPRESSION_LIMIT", f"more than {MAX_TERMS} terms")
    return p


def _mul(p: _Poly, q: _Poly, fired: list) -> _Poly:
    one = {(): Fraction(1)}
    if (p.terms == one or q.terms == one) and "elemento neutro (1·u = u)" not in fired:
        fired.append("elemento neutro (1·u = u)")
    if (not p.terms or not q.terms) and "producto por cero" not in fired:
        fired.append("producto por cero")
    if len(p.terms) > 1 and len(q.terms) > 1 and "propiedad distributiva" not in fired:
        fired.append("propiedad distributiva")
    if p.terms.keys() == {()} and q.terms.keys() == {()} and "plegado de constantes" not in fired:
        fired.append("plegado de constantes")
    terms: dict = {}
    for m1, c1 in p.terms.items():
        for m2, c2 in q.terms.items():
            m = _mono_mul(m1, m2, fired)
            if m in terms and "agrupar términos semejantes" not in fired:
                fired.append("agrupar términos semejantes")
            terms[m] = terms.get(m, Fraction(0)) + c1 * c2
            if len(terms) > MAX_TERMS:
                raise invalid("EXPRESSION_LIMIT", f"more than {MAX_TERMS} terms")
    return _clean(_Poly(terms, _merge_atoms(p.atoms, q.atoms)), fired)


def _atom(key: str, base: Expr, exponent: Fraction = Fraction(1)) -> _Poly:
    return _Poly({((key, exponent),): Fraction(1)}, {key: base})


def _pow_int_monomial(p: _Poly, n: Fraction, fired: list) -> _Poly | None:
    (m, c), = p.terms.items()
    if n.denominator != 1 and c != 1:
        return None  # a rational power of a coefficient is not exact
    if "potencia de un monomio" not in fired and (m or n != 1):
        fired.append("potencia de un monomio")
    coef = c ** int(n) if n.denominator == 1 else Fraction(1)
    return _Poly({tuple((k, e * n) for k, e in m): coef}, dict(p.atoms))


def _poly(e: Expr, var: str, log, depth: int, expand: bool = True) -> _Poly:
    if depth > 64:
        raise invalid("EXPRESSION_LIMIT", "expression too deep to simplify")
    fired: list = []
    if isinstance(e, Num):
        return _const(e.value)
    if isinstance(e, Sym):
        return _atom(e.name, e)
    if isinstance(e, Fn):
        arg = normal_expr(e.arg, var, log, depth + 1, expand)
        base = Fn(e.name, arg)
        return _atom(text(base), base)
    if isinstance(e, Neg):
        p = _poly(e.arg, var, log, depth + 1, expand)
        return _Poly({m: -c for m, c in p.terms.items()}, p.atoms)
    if isinstance(e, (Add, Sub)):
        out = _add(_poly(e.left, var, log, depth + 1, expand), _poly(e.right, var, log, depth + 1, expand),
                   1 if isinstance(e, Add) else -1, fired)
    elif isinstance(e, Mul):
        out = _mul(_poly(e.left, var, log, depth + 1, expand), _poly(e.right, var, log, depth + 1, expand), fired)
    elif isinstance(e, Div):
        num_p, den_p = _poly(e.left, var, log, depth + 1, expand), _poly(e.right, var, log, depth + 1, expand)
        if not den_p.terms:
            raise invalid("DIVISION_BY_ZERO", f"division by zero in {text(e)}")
        if len(den_p.terms) == 1:
            fired.append("cociente de monomios")
            inv = _pow_int_monomial(den_p, Fraction(-1), [])
            out = _mul(num_p, inv, fired)
        else:
            base = _build(den_p, var)
            out = _mul(num_p, _atom(text(base), base, Fraction(-1)), fired)
    elif isinstance(e, Pow):
        base_p = _poly(e.base, var, log, depth + 1, expand)
        exponent_expr = normal_expr(e.exponent, var, log, depth + 1, expand)
        exponent = exact_value(exponent_expr)
        if exponent is None:  # symbolic exponent: the whole power is an atom
            node = Pow(_build(base_p, var), exponent_expr)
            return _atom(text(node), node)
        if not base_p.terms:
            if exponent <= 0:
                raise invalid("DIVISION_BY_ZERO", f"0 raised to {exponent}")
            return _const(Fraction(0))
        if len(base_p.terms) == 1:
            out = _pow_int_monomial(base_p, exponent, fired)
            if out is None:
                base = _build(base_p, var)
                out = _atom(text(base), base, exponent)
        elif expand and exponent.denominator == 1 and 2 <= exponent <= MAX_EXPAND:
            fired.append("desarrollo de potencia")
            out = base_p
            for _ in range(int(exponent) - 1):
                out = _mul(out, base_p, fired)
        elif exponent == 1:
            out = base_p
        else:
            base = _build(base_p, var)
            out = _atom(text(base), base, exponent)
    else:  # pragma: no cover - every node type is handled above
        raise invalid("PARSE_ERROR", f"unknown node {type(e).__name__}")
    if log is not None:
        after = text(_build(out, var))
        if after != text(e) and not fired:
            fired.append("orden canónico de términos y factores")
        if fired and after != text(e):  # a rule that changed nothing visible is not a step
            log.add("simplificación", ", ".join(fired), text(e), after,
                    explanation="Transformación algebraica exacta aplicada por el simplificador.")
    return out


def _degree(m: Monomial, var: str) -> Fraction:
    return next((e for k, e in m if k == var), Fraction(0))


def _factor_order(key: str, atoms: dict, var: str) -> tuple:
    base = atoms[key]
    return (0 if key == var else 1 if isinstance(base, Sym) else 2, key)


def _term(m: Monomial, c: Fraction, atoms: dict, var: str) -> Expr:
    numer: Expr | None = None
    denom: Expr | None = None
    for key, e in sorted(m, key=lambda ke: _factor_order(ke[0], atoms, var)):
        base = atoms[key]
        factor = base if abs(e) == 1 else Pow(base, Num(abs(e)))
        if e > 0:
            numer = factor if numer is None else Mul(numer, factor)
        else:
            denom = factor if denom is None else Mul(denom, factor)
    mag = abs(c)
    if mag.numerator != 1 or numer is None:
        numer = Num(Fraction(mag.numerator)) if numer is None else Mul(Num(Fraction(mag.numerator)), numer)
    if mag.denominator != 1:
        denom = Num(Fraction(mag.denominator)) if denom is None else Mul(Num(Fraction(mag.denominator)), denom)
    return numer if denom is None else Div(numer, denom)


def _join(parts: list) -> Expr:
    """parts: [(negative?, Expr)] -> signed sum."""
    result: Expr | None = None
    for negative, term in parts:
        if result is None:
            result = Neg(term) if negative else term
        else:
            result = Sub(result, term) if negative else Add(result, term)
    return ZERO if result is None else result


def _build(p: _Poly, var: str) -> Expr:
    ordered = sorted(p.terms.items(), key=lambda mc: (-_degree(mc[0], var), len(mc[0]),
                                                    ",".join(f"{k}^{e}" for k, e in mc[0])))
    # terms sharing the same symbolic denominator are written over it once: (a + b)/d
    groups: dict = {}
    for m, c in ordered:
        den = tuple((k, e) for k, e in m if e < 0)
        groups.setdefault(den, []).append((m, c))
    parts = []
    for den, members in groups.items():
        if den and len(members) > 1:
            numer = _build(_Poly({tuple((k, e) for k, e in m if e > 0): c for m, c in members}, p.atoms), var)
            denom = _term(tuple((k, -e) for k, e in den), Fraction(1), p.atoms, var)
            parts.append((False, Div(numer, denom)))
        else:
            parts.extend((c < 0, _term(m, c, p.atoms, var)) for m, c in members)
    return _join(parts)


def normal_expr(e: Expr, var: str, log=None, depth: int = 0, expand: bool = True) -> Expr:
    """Canonical form of ``e``, recording per-node rules into ``log`` if given.

    ``expand=False`` keeps integer powers of sums as powers, e.g.
    ``(2*x + 1)^6/12``. This is the presentation form. Equivalence checks
    always expand."""
    return _build(_poly(e, var, log, depth, expand), var)


def simplify(e: Expr, var: str, expand: bool = False) -> tuple[Expr, tuple[str, ...]]:
    """Presentation form + the names of the rules that visibly fired (in order)."""
    names: list = []

    class _Names:
        def add(self, _op, rule, *_a, **_k):
            for r in rule.split(", "):
                if r not in names:
                    names.append(r)
            return -1

    out = normal_expr(e, var, _Names(), expand=expand)
    return out, tuple(names)


def is_zero(e: Expr, var: str) -> bool:
    return not _poly(e, var, None, 0).terms


def equivalent(a: Expr, b: Expr, var: str) -> bool:
    """Proven equal by normal form (sufficient, not necessary: e.g. trig identities)."""
    return is_zero(Sub(a, b), var)


def linear_parts(e: Expr, var: str) -> tuple[Fraction, Fraction] | None:
    """(a, b) with e == a*var + b and exact numeric a, b; else None."""
    p = _poly(e, var, None, 0)
    a, b = Fraction(0), Fraction(0)
    for m, c in p.terms.items():
        if m == ():
            b = c
        elif m == ((var, Fraction(1)),):
            a = c
        else:
            return None
    return a, b


def constant_ratio(a: Expr, b: Expr, var: str) -> Fraction | None:
    """Numeric k with a == k*b term by term in normal form, else None."""
    pa, pb = _poly(a, var, None, 0), _poly(b, var, None, 0)
    if not pb.terms or pa.terms.keys() != pb.terms.keys():
        return None
    ratios = {pa.terms[m] / pb.terms[m] for m in pb.terms}
    return ratios.pop() if len(ratios) == 1 else None
