# SPDX-License-Identifier: MIT
"""ML-2 (T3): limits, with the indetermination named and the method justified.

The engine
----------

Every limit is turned into one at ``+∞``: ``x → a⁺`` is ``x = a + 1/w``, ``x → a⁻`` is
``x = a − 1/w``, ``x → −∞`` is ``x = −w``; then ``w → +∞``.

Each sub-expression is described by its **principal term** on the scale

    c · w^p · e^(q·w) · (ln w)^r          (p, q, r rational, c an exact constant)

compared by ``q``, then ``p``, then ``r``. Products and quotients combine principal
terms; a sum keeps the dominant one. When the principal terms of a sum CANCEL
(``∞ − ∞``, ``0/0`` after combining), the engine falls back to the Laurent series
of that sub-expression in ``u = 1/w`` — computed by the exact formal-series
engine after taking the radicals' leading powers out
(``√(x² + x) = x·√(1 + 1/x)``) — and reads the first non-zero coefficient.

That covers the course's indeterminations: 0/0 and ∞/∞ (equivalent infinitesimals,
Taylor), ∞ − ∞ (conjugate or common denominator, done by the series), 1^∞, 0⁰ and
∞⁰ (``f^g = e^(g·ln f)``), and the hierarchy ``ln ≪ potencia ≪ exponencial``.

What it does not do, it says: an oscillating factor without a vanishing partner
(``sin x`` at ∞), ``exp`` of a super-linear growth, ``ln ln``, a radical whose
leading power is not integral after factoring. Never a sampled guess.

Second path: the value is checked numerically by evaluating approaching the point
(Richardson extrapolation on a geometric sequence); an infinite limit is checked
by growth of the samples. L'Hôpital is shown, for 0/0 and ∞/∞ quotients, as the
textbook alternative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

W = "_w"              # the variable that runs to +∞
U = "_u"              # 1/w, for the Laurent fallback
MAX_LAURENT = 8       # u^k multipliers tried
TERMINOS = 7          # coefficients asked of the series engine


class NoSe(UnsupportedError):
    pass


def _no(mensaje: str) -> NoSe:
    return NoSe(f"UNSUPPORTED: {mensaje}")


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


# ---------------------------------------------------------------------------
# the scale
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Termino:
    """c·w^p·e^(q·w)·(ln w)^r. ``c`` is an exact constant expression, never 0."""

    c: mx.Expr
    p: Fraction = Fraction(0)
    q: Fraction = Fraction(0)
    r: Fraction = Fraction(0)
    #: ±1 for e^(±g) with g growing faster than linear (e^(−w²)): beyond every e^(qw)
    sup: int = 0

    @property
    def escala(self) -> tuple[Fraction, Fraction, Fraction]:
        if self.sup:
            return (Fraction(self.sup * 10 ** 9), Fraction(0), Fraction(0))
        return (self.q, self.p, self.r)

    @property
    def valor_c(self) -> float:
        v = mx.valor_real(self.c, {})
        if v is None:
            raise _no(f"el coeficiente {mx.text(self.c)} no es un número real")
        return float(v)

    def tiende(self) -> str:
        """«inf», «-inf», «0» or «finito»."""
        s = self.escala
        if s > (0, 0, 0):
            return "inf" if self.valor_c > 0 else "-inf"
        if s < (0, 0, 0):
            return "0"
        return "finito"


class Acotada:
    """A bounded factor without a limit (sin w, cos w): only a vanishing partner
    gives it one."""


ACOTADA = Acotada()


class Oscila(Acotada):
    """No limit and not necessarily bounded (w·cos w): nothing can dominate it."""


OSCILA = Oscila()


def _pi_por(q: Fraction) -> mx.Expr:
    pi = mx.Const("pi")
    if q == 0:
        return mx.Num(Fraction(0))
    base = pi if abs(q) == 1 else (mx.Div(pi, mx.Num(Fraction(abs(q).denominator)))
                                     if abs(q).numerator == 1 else
                                     mx.Mul(mx.Num(abs(q)), pi))
    return mx.Neg(base) if q < 0 else base


_NOTABLES = {
    "asin": {Fraction(1): _pi_por(Fraction(1, 2)), Fraction(-1): _pi_por(Fraction(-1, 2)),
             Fraction(1, 2): _pi_por(Fraction(1, 6)), Fraction(-1, 2): _pi_por(Fraction(-1, 6)),
             Fraction(0): mx.Num(Fraction(0))},
    "acos": {Fraction(1): mx.Num(Fraction(0)), Fraction(-1): _pi_por(Fraction(1)),
             Fraction(0): _pi_por(Fraction(1, 2)), Fraction(1, 2): _pi_por(Fraction(1, 3)),
             Fraction(-1, 2): _pi_por(Fraction(2, 3))},
    "atan": {Fraction(1): _pi_por(Fraction(1, 4)), Fraction(-1): _pi_por(Fraction(-1, 4)),
             Fraction(0): mx.Num(Fraction(0))},
}


class _NoCuadratico(Exception):
    pass


def _en_q_raiz(e: mx.Expr, r: list) -> tuple[Fraction, Fraction]:
    """e = a + b·√r exactly, for ONE square-free r (shared through the list ``r``)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    if isinstance(e, mx.Num):
        return Fraction(e.value), Fraction(0)
    if isinstance(e, mx.Neg):
        a, b = _en_q_raiz(e.arg, r)
        return -a, -b
    raiz = None
    if isinstance(e, mx.Root) and e.degree == 2:
        raiz = e.radicand
    elif isinstance(e, mx.Call) and e.name in ("sqrt", "raiz", "raiz2"):
        raiz = e.args[0]
    elif isinstance(e, mx.Pow) and mx.exact_value(e.exponent) == Fraction(1, 2):
        raiz = e.base
    if raiz is not None:
        q = mx.exact_value(raiz)
        if q is None or q < 0:
            raise _NoCuadratico
        k, libre = RZ._raiz_simplificada(Fraction(q))
        if libre == 1:
            return k, Fraction(0)
        if r and r[0] != libre:
            raise _NoCuadratico
        r[:] = [libre]
        return Fraction(0), k
    if isinstance(e, (mx.Add, mx.Sub)):
        a1, b1 = _en_q_raiz(e.left, r)
        a2, b2 = _en_q_raiz(e.right, r)
        s = 1 if isinstance(e, mx.Add) else -1
        return a1 + s * a2, b1 + s * b2
    if isinstance(e, mx.Mul):
        a1, b1 = _en_q_raiz(e.left, r)
        a2, b2 = _en_q_raiz(e.right, r)
        rr = r[0] if r else Fraction(0)
        return a1 * a2 + b1 * b2 * rr, a1 * b2 + a2 * b1
    if isinstance(e, mx.Div):
        a1, b1 = _en_q_raiz(e.left, r)
        a2, b2 = _en_q_raiz(e.right, r)
        rr = r[0] if r else Fraction(0)
        n = a2 * a2 - b2 * b2 * rr
        if n == 0:
            raise _NoCuadratico
        # (a1 + b1√r)(a2 − b2√r)/n
        return (a1 * a2 - b1 * b2 * rr) / n, (b1 * a2 - a1 * b2) / n
    if isinstance(e, mx.Pow):
        k = mx.exact_value(e.exponent)
        if k is None or Fraction(k).denominator != 1 or abs(k) > 32:
            raise _NoCuadratico
        a, b = _en_q_raiz(e.base, r)
        ra, rb = Fraction(1), Fraction(0)
        rr = r[0] if r else Fraction(0)
        for _ in range(abs(int(k))):
            ra, rb = ra * a + rb * b * rr, ra * b + rb * a
        if k < 0:
            n = ra * ra - rb * rb * rr
            if n == 0:
                raise _NoCuadratico
            ra, rb = ra / n, -rb / n
        return ra, rb
    raise _NoCuadratico


def _pliega(e: mx.Expr) -> mx.Expr:
    """Fold exact constants: sqrt(1) → 1, 2·(1/ln 2)·(1/1) → 2/ln 2,
    1/(2·√2)² → 1/8, and anything in ℚ(√r) to a + b·√r."""
    if isinstance(e, (mx.Num, mx.Sym, mx.Const)):
        return e
    if not mx.variables(e):
        v = mx.exact_value(e)
        if v is not None:
            return _num(v)
        r: list = []
        try:
            a, b = _en_q_raiz(e, r)
        except (_NoCuadratico, ZeroDivisionError):
            pass
        else:
            from academic_core.domain.engineering.mathlab import raices as RZ

            return RZ._mas_raiz(a, b, r[0] if r else Fraction(1))
    if isinstance(e, mx.Neg):
        a = _pliega(e.arg)
        v = mx.exact_value(a) if not mx.variables(a) else None
        return _num(-v) if v is not None else (a.arg if isinstance(a, mx.Neg) else mx.Neg(a))
    if isinstance(e, (mx.Mul, mx.Div)):
        a, b = _pliega(e.left), _pliega(e.right)
        va = mx.exact_value(a) if not mx.variables(a) else None
        vb = mx.exact_value(b) if not mx.variables(b) else None
        if isinstance(e, mx.Mul):
            if va == 1:
                return b
            if vb == 1:
                return a
            if isinstance(b, mx.Div) and mx.exact_value(b.left) == 1:
                return _pliega(mx.Div(a, b.right))
            if isinstance(a, mx.Div) and mx.exact_value(a.left) == 1:
                return _pliega(mx.Div(b, a.right))
            if isinstance(a, mx.Div) and isinstance(b, mx.Div):
                return mx.Div(_pliega(mx.Mul(a.left, b.left)), _pliega(mx.Mul(a.right, b.right)))
            if isinstance(a, mx.Div):
                return mx.Div(_pliega(mx.Mul(a.left, b)), a.right)
            if isinstance(b, mx.Div):
                return mx.Div(_pliega(mx.Mul(a, b.left)), b.right)
            return mx.Mul(a, b)
        if vb == 1:
            return a
        if isinstance(a, mx.Div):
            return mx.Div(a.left, _pliega(mx.Mul(a.right, b)))
        return mx.Div(a, b)
    if isinstance(e, (mx.Add, mx.Sub)):
        return type(e)(_pliega(e.left), _pliega(e.right))
    if isinstance(e, mx.Pow):
        return mx.Pow(_pliega(e.base), _pliega(e.exponent))
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _pliega(e.radicand))
    if isinstance(e, mx.Call):
        args = tuple(_pliega(x) for x in e.args)
        if e.name in _NOTABLES and not mx.variables(args[0]):
            v = mx.exact_value(args[0])
            if v is not None and v in _NOTABLES[e.name]:
                return _NOTABLES[e.name][v]
        if e.name in ("abs", "valor_abs") and not mx.variables(args[0]):
            v = mx.exact_value(args[0])
            if v is not None:
                return _num(abs(v))
            r: list = []
            try:
                a, b = _en_q_raiz(args[0], r)
                valor = mx.valor_real(args[0], {})
                if valor is not None:
                    return _pliega(args[0] if valor >= 0 else mx.Neg(args[0]))
            except (_NoCuadratico, ZeroDivisionError):
                pass
        # ln(e^k) = k, e^(ln k) = k (k > 0)
        if e.name in ("ln", "log") and len(args) == 1 and isinstance(args[0], mx.Call) \
                and args[0].name == "exp":
            return args[0].args[0]
        if e.name == "exp" and isinstance(args[0], mx.Call) and args[0].name in ("ln", "log"):
            v = mx.valor_real(args[0].args[0], {}) if not mx.variables(args[0]) else None
            if v is not None and v > 0:
                return args[0].args[0]
        return mx.Call(e.name, args)
    return e


def _limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import calculators as K

    e = _pliega(e)
    try:
        r = K._presentable(e, Trace())
    except Exception:  # noqa: BLE001
        return e
    return r if len(mx.text(r)) <= len(mx.text(e)) else e


def _num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


def _cero(e: mx.Expr) -> bool:
    v = mx.exact_value(e)
    if v is not None:
        return v == 0
    if mx.variables(e):
        return False
    z = mx.evaluate(e)
    return z is not None and abs(z) < 1e-13


def _identico_cero(e: mx.Expr) -> bool:
    """Exactly 0 as an element of the polynomial ring over its atoms (w − 1·w,
    ln w − ln w); a sampled «looks like 0» never counts."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        if P.is_zero(P.as_poly(e)):
            return True
    except Exception:  # noqa: BLE001
        pass
    for var in mx.variables(e):
        try:
            razon = P.as_ratio(e, var)
        except Exception:  # noqa: BLE001
            razon = None
        if razon is not None:
            return P.is_zero(razon.numerator)
    return _cero(_limpio(e))


def _mul(a: Termino, b: Termino) -> Termino:
    if a.sup and b.sup:
        raise _no("producto de dos exponenciales de crecimiento superlineal: sus "
                  "exponentes podrían compensarse y aquí no se comparan")
    return Termino(_limpio(mx.Mul(a.c, b.c)), a.p + b.p, a.q + b.q, a.r + b.r, a.sup or b.sup)


def _inv(a: Termino) -> Termino:
    return Termino(_limpio(mx.Div(mx.Num(Fraction(1)), a.c)), -a.p, -a.q, -a.r, -a.sup)


# ---------------------------------------------------------------------------
# Laurent fallback in u = 1/w
# ---------------------------------------------------------------------------


# A truncated Laurent series: u^m · (c₀ + c₁u + … + c_{n−1}u^{n−1} + O(uⁿ)), c₀ ≠ 0.
# Coefficients are exact constant expressions; precision (n) is tracked and an
# operation that would need more terms than are known raises instead of guessing.


@dataclass(frozen=True)
class _Serie:
    m: int
    c: tuple[mx.Expr, ...]


def _s(e: mx.Expr) -> mx.Expr:
    return _limpio(e)


def _sm(a, b):
    return _s(mx.Mul(a, b))


def _sa(a, b):
    return _s(mx.Add(a, b))


def _constante(k: mx.Expr, n: int) -> _Serie:
    return _Serie(0, (k,) + (mx.Num(Fraction(0)),) * (n - 1))


def _normaliza(m: int, c: list) -> _Serie | None:
    j = 0
    while j < len(c) and _cero(c[j]):
        j += 1
    if j == len(c):
        # all known coefficients vanish: that is not a proof of 0, ask for more terms
        raise _no("hace falta más precisión en la serie (cancelación profunda)")
    return _Serie(m + j, tuple(c[j:]))


def _s_mul(a: _Serie, b: _Serie) -> _Serie:
    n = min(len(a.c), len(b.c))
    c = []
    for k in range(n):
        t = mx.Num(Fraction(0))
        for i in range(k + 1):
            t = mx.Add(t, mx.Mul(a.c[i], b.c[k - i]))
        c.append(_s(t))
    return _Serie(a.m + b.m, tuple(c))


def _s_inv(a: _Serie) -> _Serie:
    n = len(a.c)
    b0 = _s(mx.Div(mx.Num(Fraction(1)), a.c[0]))
    b = [b0]
    for k in range(1, n):
        t = mx.Num(Fraction(0))
        for i in range(1, k + 1):
            t = mx.Add(t, mx.Mul(a.c[i], b[k - i]))
        b.append(_s(mx.Neg(mx.Mul(b0, t))))
    return _Serie(-a.m, tuple(b))


def _s_add(a: _Serie | None, b: _Serie | None) -> _Serie | None:
    if a is None:
        return b
    if b is None:
        return a
    m = min(a.m, b.m)
    la, lb = len(a.c) + a.m - m, len(b.c) + b.m - m
    n = min(la, lb)
    cero = mx.Num(Fraction(0))
    A = [cero] * (a.m - m) + list(a.c)
    B = [cero] * (b.m - m) + list(b.c)
    return _normaliza(m, [_sa(A[k], B[k]) for k in range(n)])


def _s_neg(a: _Serie | None) -> _Serie | None:
    return None if a is None else _Serie(a.m, tuple(_s(mx.Neg(x)) for x in a.c))


def _binomial(q: Fraction, k: int) -> Fraction:
    r = Fraction(1)
    for i in range(k):
        r = r * (q - i) / (i + 1)
    return r


def _s_compone(coefs_f: list[mx.Expr], t: _Serie | None, n: int) -> _Serie | None:
    """Σ fₖ·tᵏ with t = O(u) (t.m ≥ 1)."""
    total = _constante(coefs_f[0], n) if not _cero(coefs_f[0]) else None
    if t is None:
        return total if total is not None else None
    potencia = None
    for k in range(1, n):
        potencia = t if potencia is None else _s_mul(potencia, t)
        if potencia.m >= n + (total.m if total else 0) + 2:
            break
        if _cero(coefs_f[k]):
            continue
        termino = _Serie(potencia.m, tuple(_sm(coefs_f[k], x) for x in potencia.c))
        total = _s_add(total, termino) if total is not None else _normaliza(termino.m,
                                                                           list(termino.c))
    return total


def _s_pot(a: _Serie, q: Fraction, n: int) -> _Serie:
    """(c₀u^m(1 + t))^q, with c₀ > 0 unless q is an integer."""
    if (a.m * q).denominator != 1:
        raise _no(f"orden {a.m}·{q} no entero: haría falta una serie de Puiseux")
    c0 = a.c[0]
    if q.denominator != 1 and (mx.valor_real(c0, {}) or 0) <= 0:
        raise _error("UNDEFINED", "raíz de una cantidad negativa cerca del punto")
    t = _Serie(1, tuple(_s(mx.Div(x, c0)) for x in a.c[1:])) if len(a.c) > 1 else None
    coefs = [mx.Num(_binomial(q, k)) for k in range(n)]
    uno_mas_t = _s_compone(coefs, t, min(n, len(a.c)))
    c0q = _s(mx.Pow(c0, _num(q)))
    return _Serie(int(a.m * q) + uno_mas_t.m, tuple(_sm(c0q, x) for x in uno_mas_t.c))


_REESCRITURAS = {
    "tan": lambda z: mx.Div(mx.Call("sin", (z,)), mx.Call("cos", (z,))),
    "cot": lambda z: mx.Div(mx.Call("cos", (z,)), mx.Call("sin", (z,))),
    "sec": lambda z: mx.Div(mx.Num(Fraction(1)), mx.Call("cos", (z,))),
    "csc": lambda z: mx.Div(mx.Num(Fraction(1)), mx.Call("sin", (z,))),
    "tanh": lambda z: mx.Div(mx.Call("sinh", (z,)), mx.Call("cosh", (z,))),
}


def _taylor_funcion(nombre: str, a0: mx.Expr, n: int) -> list[mx.Expr]:
    """fₖ = f⁽ᵏ⁾(a₀)/k!, each one checked to exist."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    z = "_z"
    f: mx.Expr = mx.Call(nombre, (mx.Sym(z),))
    salida = []
    factorial = 1
    for k in range(n):
        if k:
            f = _s(DM.differentiate(f, z))
            factorial *= k
        valor = _s(mx.Div(mx.substitute(f, z, a0), mx.Num(Fraction(factorial))))
        v = mx.evaluate(valor)
        if v is None or not math.isfinite(abs(v)) or abs(v) > 1e12:
            raise _error("UNDEFINED", f"{nombre} no es analítica en {mx.text(a0)}")
        salida.append(valor)
    return salida


def _laurent(e: mx.Expr, n: int = TERMINOS) -> _Serie | None:
    if not mx.depends(e, U):
        return None if _cero(e) else _constante(_s(e), n)
    if isinstance(e, mx.Sym):
        return _Serie(1, (mx.Num(Fraction(1)),) + (mx.Num(Fraction(0)),) * (n - 1))
    if isinstance(e, mx.Neg):
        return _s_neg(_laurent(e.arg, n))
    if isinstance(e, mx.Mul):
        a, b = _laurent(e.left, n), _laurent(e.right, n)
        return None if a is None or b is None else _s_mul(a, b)
    if isinstance(e, mx.Div):
        a, b = _laurent(e.left, n), _laurent(e.right, n)
        if b is None:
            raise _error("UNDEFINED", "división por algo idénticamente 0")
        return None if a is None else _s_mul(a, _s_inv(b))
    if isinstance(e, mx.Add):
        return _s_add(_laurent(e.left, n), _laurent(e.right, n))
    if isinstance(e, mx.Sub):
        return _s_add(_laurent(e.left, n), _s_neg(_laurent(e.right, n)))
    if isinstance(e, (mx.Pow, mx.Root)) or (isinstance(e, mx.Call) and
                                            e.name in ("sqrt", "raiz", "raiz2")):
        if isinstance(e, mx.Pow):
            base, expo = e.base, e.exponent
        elif isinstance(e, mx.Root):
            base, expo = e.radicand, mx.Num(Fraction(1, e.degree))
        else:
            base, expo = e.args[0], mx.Num(Fraction(1, 2))
        if mx.depends(expo, U):
            return _laurent(mx.Call("exp", (mx.Mul(expo, mx.Call("ln", (base,))),)), n)
        q = mx.exact_value(expo)
        a = _laurent(base, n)
        if q is None:
            raise _no(f"exponente no racional en {mx.text(e)}")
        if a is None:
            if q > 0:
                return None
            raise _error("UNDEFINED", f"{mx.text(e)}: 0 elevado a un exponente ≤ 0")
        return _s_pot(a, Fraction(q), n)
    if isinstance(e, mx.Call):
        if e.name in _REESCRITURAS:
            return _laurent(_REESCRITURAS[e.name](e.args[0]), n)
        if e.name in ("log",) or len(e.args) != 1:
            raise _no(f"no sé desarrollar {mx.text(e)}")
        a = _laurent(e.args[0], n)
        if a is not None and a.m < 0:
            raise _no(f"{e.name} de algo que tiende a infinito: fuera de las series")
        if a is None or a.m > 0:
            a0, t = mx.Num(Fraction(0)), a
        else:
            a0 = a.c[0]
            t = _normaliza(1, list(a.c[1:])) if len(a.c) > 1 else None
        if e.name in ("abs", "valor_abs"):
            v = mx.valor_real(a0, {}) if a is not None and a.m == 0 else None
            if v is None or v == 0:
                raise _no("|·| en un cero de su argumento")
            return a if v > 0 else _s_neg(a)
        coefs = _taylor_funcion(e.name, a0, min(n, len(a.c) if a else n))
        return _s_compone(coefs, t, min(n, len(a.c) if a else n))
    raise _no(f"no sé desarrollar {mx.text(e)}")


def _principal_laurent(e: mx.Expr) -> Termino | None:
    ultimo = None
    for n in (TERMINOS, 2 * TERMINOS):
        try:
            serie = _laurent(e, n)
        except NoSe as exc:
            ultimo = exc
            if "precisión" not in str(exc):
                raise
            continue
        if serie is None:
            return None
        return Termino(_limpio(serie.c[0]), Fraction(-serie.m))     # u^m = w^(−m)
    raise ultimo


def _en_u(e: mx.Expr) -> mx.Expr:
    return mx.substitute(e, W, mx.Div(mx.Num(Fraction(1)), mx.Sym(U)))


# ---------------------------------------------------------------------------
# the principal term, recursively
# ---------------------------------------------------------------------------


_ANALITICAS = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
               "asinh", "atanh", "exp", "cot", "sec", "csc"}


def principal(e: mx.Expr) -> Termino | Acotada | None:
    """Principal term of ``e(w)`` as w → +∞; None means identically 0 near ∞."""
    if not mx.depends(e, W):
        if _cero(e):
            return None
        return Termino(_limpio(e))
    if isinstance(e, mx.Sym):
        return Termino(mx.Num(Fraction(1)), Fraction(1))
    if isinstance(e, mx.Neg):
        a = principal(e.arg)
        if a is None or isinstance(a, Acotada):
            return a
        return Termino(_limpio(mx.Neg(a.c)), a.p, a.q, a.r, a.sup)
    if isinstance(e, (mx.Add, mx.Sub)):
        return _suma(e)
    if isinstance(e, mx.Mul):
        a, b = principal(e.left), principal(e.right)
        return _producto(a, b, e)
    if isinstance(e, mx.Div):
        a, b = principal(e.left), principal(e.right)
        if b is None:
            raise _error("UNDEFINED", f"el denominador {mx.text(e.right)} es idénticamente 0")
        if isinstance(b, Acotada):
            raise _no(f"dividir por una función oscilante ({mx.text(e.right)})")
        return _producto(a, _inv(b), e)
    if isinstance(e, (mx.Pow, mx.Root)):
        base, expo = (e.base, e.exponent) if isinstance(e, mx.Pow) else \
            (e.radicand, mx.Num(Fraction(1, e.degree)))
        if mx.depends(expo, W):
            # f^g = e^(g·ln f)
            return principal(mx.Call("exp", (mx.Mul(expo, mx.Call("ln", (base,))),)))
        q = mx.exact_value(expo)
        a = principal(base)
        if a is None:
            if q is not None and q > 0:
                return None
            raise _error("UNDEFINED", f"{mx.text(e)}: 0 elevado a un exponente ≤ 0")
        if isinstance(a, Acotada):
            raise _no(f"potencia de una función oscilante ({mx.text(e)})")
        if q is None:
            # constant but not rational exponent: c^k with c > 0
            if a.escala != (0, 0, 0):
                raise _no(f"exponente irracional sobre una magnitud que crece ({mx.text(e)})")
            return Termino(_limpio(mx.Pow(a.c, expo)))
        q = Fraction(q)
        if q.denominator != 1 and a.valor_c < 0:
            raise _error("UNDEFINED", f"{mx.text(e)}: raíz par de un número negativo")
        c = _limpio(mx.Pow(a.c, _num(q)))
        if a.escala == (0, 0, 0) and q.denominator != 1:
            return Termino(c)
        return Termino(c, a.p * q, a.q * q, a.r * q, (a.sup if q > 0 else -a.sup) if a.sup else 0)
    if isinstance(e, mx.Call):
        return _funcion(e)
    raise _no(f"no sé el comportamiento de {mx.text(e)}")


def _producto(a, b, e) -> Termino | Acotada | None:
    if a is None or b is None:
        if isinstance(a, Acotada) or isinstance(b, Acotada):
            return None   # 0 · bounded is 0 (but a «None» factor is an identical zero)
        return None
    if isinstance(a, Acotada) and isinstance(b, Acotada):
        return ACOTADA
    if isinstance(a, Acotada) or isinstance(b, Acotada):
        otro = b if isinstance(a, Acotada) else a
        if otro.escala < (0, 0, 0):
            return _CERO_ACOTADO
        return OSCILA    # c·sin w or w·cos w: no limit
    return _mul(a, b)


class _CeroAcotado(Termino):
    """bounded × vanishing: its limit is 0 but it has no principal term."""


_CERO_ACOTADO = _CeroAcotado(mx.Num(Fraction(1)), Fraction(-1), Fraction(0), Fraction(0))


def _suma(e: mx.Expr) -> Termino | Acotada | None:
    a = principal(e.left)
    b = principal(e.right)
    if isinstance(e, mx.Sub) and isinstance(b, Termino):
        b = Termino(_limpio(mx.Neg(b.c)), b.p, b.q, b.r, b.sup)
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, Termino) and isinstance(b, Termino) and a.escala == b.escala \
            and _identico_cero(e):
        return None      # an exact identical zero (w − 1·w), not a cancellation to expand
    if isinstance(a, Oscila) or isinstance(b, Oscila):
        raise _no(f"{mx.text(e)}: un sumando oscila sin acotar; no sé si otro lo domina")
    if isinstance(a, Acotada) or isinstance(b, Acotada):
        otro = b if isinstance(a, Acotada) else a
        if isinstance(otro, Acotada) or otro.escala <= (0, 0, 0):
            return ACOTADA
        return otro
    if isinstance(a, _CeroAcotado) or isinstance(b, _CeroAcotado):
        otro = b if isinstance(a, _CeroAcotado) else a
        if otro.escala >= (0, 0, 0) and not isinstance(otro, _CeroAcotado):
            return otro
        raise _no(f"{mx.text(e)}: suma de un término oscilante amortiguado con otro que "
                  "también tiende a 0")
    if a.escala != b.escala:
        return a if a.escala > b.escala else b
    if a.sup or b.sup:
        raise _no(f"{mx.text(e)}: dos términos superexponenciales del mismo signo")
    c = _limpio(mx.Add(a.c, b.c))
    if not _cero(c):
        return Termino(c, a.p, a.q, a.r, a.sup)
    # the principal terms cancel: the series of the whole sum decides
    if a.q != 0 or a.r != 0:
        raise _no(f"{mx.text(e)}: los términos principales se cancelan y hay exponenciales "
                  "o logaritmos en juego")
    return _principal_laurent(_en_u(e))


def _funcion(e: mx.Call) -> Termino | Acotada | None:
    nombre = e.name
    if nombre in _REESCRITURAS:
        # tan = sin/cos: its poles become zeros of a denominator, which the
        # quotient handles; tan(π/2) is never «evaluated» to a huge float
        return principal(_REESCRITURAS[nombre](e.args[0]))
    if nombre in ("ln", "log") and len(e.args) == 1:
        a = principal(e.args[0])
        if a is None:
            raise _error("UNDEFINED", f"ln de algo idénticamente 0")
        if isinstance(a, Acotada):
            raise _no("ln de una función oscilante")
        if a.valor_c <= 0:
            raise _error("UNDEFINED", f"{mx.text(e)}: logaritmo de algo negativo")
        if a.escala == (0, 0, 0):
            if _cero(_limpio(mx.Sub(a.c, mx.Num(Fraction(1))))):
                # ln(1 + v) ~ v
                return principal(mx.Sub(e.args[0], mx.Num(Fraction(1))))
            return Termino(_limpio(mx.Call("ln", (a.c,))))
        if a.q != 0:
            return Termino(_num(a.q), Fraction(1))
        if a.p != 0:
            return Termino(_num(a.p), Fraction(0), Fraction(0), Fraction(1))
        raise _no("ln(ln) no está implementado")
    if nombre == "exp":
        arg = e.args[0]
        a = principal(arg)
        if a is None:
            return Termino(mx.Num(Fraction(1)))
        if isinstance(a, Acotada):
            raise _no("exp de una función oscilante")
        if a.escala < (0, 0, 0) or a.escala == (0, 0, 0):
            if a.escala == (0, 0, 0):
                return Termino(_limpio(mx.Call("exp", (a.c,))))
            return Termino(mx.Num(Fraction(1)))
        if a.escala == (0, 1, 0):
            resto = mx.Sub(arg, mx.Mul(a.c, mx.Sym(W)))
            k = mx.exact_value(a.c)
            if k is None:
                # 2^x = e^(x·ln 2): an irrational rate, compared by its value
                k = Fraction(a.valor_c)
            b = principal(resto)
            if b is None or b.escala < (0, 0, 0):
                return Termino(mx.Num(Fraction(1)), Fraction(0), Fraction(k))
            if b.escala == (0, 0, 0):
                return Termino(_limpio(mx.Call("exp", (b.c,))), Fraction(0), Fraction(k))
            raise _no(f"exp({mx.text(arg)}): el resto tras la parte lineal no tiende a un número")
        if a.escala == (0, 0, 1):
            # exp(k·ln w + resto) = w^k·e^resto
            resto = mx.Sub(arg, mx.Mul(a.c, mx.Call("ln", (mx.Sym(W),))))
            k = mx.exact_value(a.c)
            b = principal(resto)
            if k is not None and (b is None or b.escala <= (0, 0, 0)):
                c = mx.Num(Fraction(1)) if b is None or b.escala < (0, 0, 0) else \
                    _limpio(mx.Call("exp", (b.c,)))
                return Termino(c, Fraction(k))
        if a.escala < (0, 0, 1) and a.escala > (0, 0, 0):
            raise _no(f"exp({mx.text(arg)}) crece más lento que una potencia: no implementado")
        # e^(g) with g ~ c·w^p, p > 1 (or faster): beyond every exponential of the scale.
        # Only its sign of growth matters for what it multiplies or is added to.
        return Termino(mx.Num(Fraction(1)), sup=1 if a.valor_c > 0 else -1)
    if nombre in ("sqrt", "raiz", "raiz2"):
        return principal(mx.Pow(e.args[0], mx.Num(Fraction(1, 2))))
    if nombre in ("abs", "valor_abs"):
        a = principal(e.args[0])
        if a is None or isinstance(a, Acotada):
            return a
        return Termino(_limpio(mx.Call("abs", (a.c,))), a.p, a.q, a.r, a.sup)
    if nombre in _ANALITICAS:
        arg = e.args[0]
        a = principal(arg)
        if isinstance(a, Acotada):
            raise _no(f"{nombre} de una función oscilante")
        if a is not None and a.escala > (0, 0, 0):
            if nombre in ("sin", "cos"):
                return ACOTADA
            if nombre == "atan":
                return Termino(_limpio(mx.Mul(_num(1 if a.valor_c > 0 else -1),
                                              mx.Div(mx.Const("pi"), mx.Num(Fraction(2))))))
            if nombre in ("sinh", "cosh"):
                return principal(mx.Div(mx.Add(mx.Call("exp", (arg,)),
                                               mx.Mul(_num(-1 if nombre == "sinh" else 1),
                                                      mx.Call("exp", (mx.Neg(arg),)))),
                                        mx.Num(Fraction(2))))
            if nombre == "tanh":
                return Termino(_num(1 if a.valor_c > 0 else -1))
            raise _no(f"{nombre} de algo que crece: sin límite o fuera del dominio")
        limite = mx.Num(Fraction(0)) if a is None or a.escala < (0, 0, 0) else a.c
        valor = _limpio(mx.Call(nombre, (limite,)))
        if mx.evaluate(valor) is None:
            raise _error("UNDEFINED", f"{nombre}({mx.text(limite)}) no existe")
        if not _cero(valor):
            return Termino(valor)
        # f(L) = 0: f(arg) ~ f′(L)·(arg − L)
        from academic_core.domain.engineering.mathlab import derive_mv as DM

        z = mx.Sym("_z")
        derivada = _limpio(mx.substitute(DM.differentiate(mx.Call(nombre, (z,)), "_z"),
                                         "_z", limite))
        if _cero(derivada):
            return _principal_laurent(_en_u(e))
        return _producto(Termino(derivada), principal(mx.Sub(arg, limite)), e)
    raise _no(f"no sé el comportamiento de {nombre}(…)")


# ---------------------------------------------------------------------------
# the limit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Limite:
    valor: str                    # exact text, «+∞», «−∞», or «no existe»
    expr: mx.Expr | None
    laterales: tuple[tuple[str, str], ...] = ()
    indeterminacion: str = ""

    def texto(self) -> str:
        if self.laterales and self.valor == "no existe":
            return "no existe: " + ", ".join(f"por {lado} {v}" for lado, v in self.laterales)
        return self.valor


def _a_w(e: mx.Expr, var: str, punto: str, lado: int) -> mx.Expr:
    w = mx.Sym(W)
    if punto in ("oo", "+oo", "inf", "+inf", "∞", "+∞"):
        return mx.substitute(e, var, w)
    if punto in ("-oo", "-inf", "-∞"):
        return mx.substitute(e, var, mx.Neg(w))
    a = mx.parse(punto)
    paso = mx.Div(mx.Num(Fraction(1)), w)
    return mx.substitute(e, var, mx.Add(a, paso) if lado > 0 else mx.Sub(a, paso))


def _valor(t: Termino | Acotada | None) -> tuple[str, mx.Expr | None]:
    if t is None or isinstance(t, _CeroAcotado):
        return "0", mx.Num(Fraction(0))
    if isinstance(t, Acotada):
        return "no existe (oscila)", None
    tendencia = t.tiende()
    if tendencia == "inf":
        return "+∞", None
    if tendencia == "-inf":
        return "−∞", None
    if tendencia == "0":
        return "0", mx.Num(Fraction(0))
    return mx.text(t.c), t.c


def _tipo(e: mx.Expr, var: str, punto: str, lado: int) -> str:
    """Name the indetermination, the first thing a student must see."""
    def clase(x):
        try:
            t = principal(_a_w(x, var, punto, lado))
        except Exception:  # noqa: BLE001
            return "?"
        if t is None or isinstance(t, _CeroAcotado):
            return "0"
        if isinstance(t, Acotada):
            return "acotada"
        tend = t.tiende()
        if tend in ("inf", "-inf"):
            return "∞"
        if tend == "0":
            return "0"
        return "1" if _cero(_limpio(mx.Sub(t.c, mx.Num(Fraction(1))))) else "k"

    if isinstance(e, mx.Div):
        n, d = clase(e.left), clase(e.right)
        if (n, d) in (("0", "0"), ("∞", "∞")):
            return f"{n}/{d}"
    if isinstance(e, mx.Mul):
        a, b = clase(e.left), clase(e.right)
        if {a, b} == {"0", "∞"}:
            return "0·∞"
    if isinstance(e, mx.Sub) or isinstance(e, mx.Add):
        a, b = clase(e.left), clase(e.right)
        if a == b == "∞":
            return "∞ − ∞ (posible)"
    if isinstance(e, mx.Pow) and mx.depends(e.exponent, var):
        b, x = clase(e.base), clase(e.exponent)
        if (b, x) in (("1", "∞"), ("0", "0"), ("∞", "0")):
            return {"1": "1^∞", "0": "0⁰", "∞": "∞⁰"}[b]
    return ""


def limite(expresion: mx.Expr, var: str, punto: str, lado: str = "",
           trace: Trace | None = None) -> Limite:
    """``lado`` = «+», «-» or «» (both sides when the point is finite)."""
    trace = trace if trace is not None else Trace()
    infinito = punto.strip().lstrip("+-") in ("oo", "inf", "∞")
    lados = [1] if infinito else ([1] if lado == "+" else [-1] if lado == "-" else [1, -1])
    tipo = _tipo(expresion, var, punto, lados[0])
    if tipo:
        trace.regla("limite.indeterminacion", f"indeterminación {tipo}",
                    why="sustituir directamente no decide: hay que comparar órdenes")
    trace.metodo("limite.ordenes", "término principal en la escala potencia · exponencial · "
                 "logaritmo, con series de Taylor/Laurent cuando los principales se cancelan",
                 why="es el método de los infinitésimos equivalentes y de Taylor hecho "
                     "exacto: no depende de muestrear cerca del punto",
                 alternatives=(("L'Hôpital", "derivar arriba y abajo da lo mismo en 0/0 y "
                                "∞/∞, pero puede no terminar (e^x/e^x) y no sirve para ∞−∞ "
                                "sin reescribir"),))
    resultados = []
    for s in lados:
        w = _a_w(expresion, var, punto, s)
        t = principal(w)
        texto, valor = _valor(t)
        if isinstance(t, Termino) and not isinstance(t, _CeroAcotado):
            trace.regla("limite.principal",
                        f"{'x → ' + punto + ('⁺' if s > 0 else '⁻') if not infinito else ''}"
                        f" término principal: {_texto_termino(t, var, punto, s)}",
                        after=texto)
        resultados.append((s, texto, valor))
    if len(resultados) == 2 and not _iguales(resultados[0], resultados[1]):
        laterales = tuple(("la derecha" if s > 0 else "la izquierda", v) for s, v, _ in resultados)
        return Limite("no existe", None, laterales, tipo)
    _, texto, valor = resultados[0]
    return Limite(texto, valor, (), tipo)


def _iguales(a, b) -> bool:
    """Two one-sided results agree by VALUE (their texts may be written differently)."""
    if a[2] is None or b[2] is None:
        return a[1] == b[1]
    x, y = mx.evaluate(a[2]), mx.evaluate(b[2])
    return x is not None and y is not None and abs(x - y) <= 1e-12 * max(1.0, abs(x))


def _texto_termino(t: Termino, var: str, punto: str, lado: int) -> str:
    """The principal term in the student's variable."""
    infinito = punto.strip().lstrip("+-") in ("oo", "inf", "∞")
    if infinito:
        base = var if not punto.strip().startswith("-") else f"(−{var})"
    else:
        a = punto.strip()
        base = f"({var} − {a})" if lado > 0 else f"({a} − {var})"
        base = f"1/{base}"
    partes = [mx.text(t.c)]
    if t.p:
        partes.append(base if t.p == 1 else f"{base}^{t.p}")
    if t.q:
        q = t.q if t.q.denominator < 10 ** 4 else f"{float(t.q):.6g}"
        partes.append(f"e^({q}·{base})")
    if t.r:
        partes.append(f"ln({base})" + ("" if t.r == 1 else f"^{t.r}"))
    return "·".join(partes)


# ---------------------------------------------------------------------------
# second path
# ---------------------------------------------------------------------------


def comprobacion_numerica(expresion: mx.Expr, var: str, punto: str, lado: int,
                          resultado: Limite) -> tuple[bool, str]:
    """Evaluate approaching the point; Richardson on h = 2⁻ᵏ for a finite value."""
    infinito = punto.strip().lstrip("+-") in ("oo", "inf", "∞")
    signo_inf = -1 if punto.strip().startswith("-") else 1

    def x_de(h: float) -> float:
        if infinito:
            return signo_inf / h
        return float(mx.valor_real(mx.parse(punto), {})) + lado * h

    valores = []
    pasos = range(2, 12) if infinito else range(6, 22, 2)
    for k in pasos:
        h = 2.0 ** (-k if not infinito else -k)
        if infinito:
            h = 1.0 / (2.0 ** k)       # x = 4, 8, …, 2048: far enough, short of overflow
        try:
            v = mx.valor_real(expresion, {var: x_de(h)})
        except (OverflowError, ValueError, ZeroDivisionError):
            v = None
        if v is not None and math.isfinite(v):
            valores.append((h, float(v)))
    if len(valores) < 3:
        return False, "no se puede evaluar cerca del punto"
    ultimo = valores[-1][1]
    if resultado.valor in ("+∞", "−∞"):
        # only the tail matters: e^x/x¹⁰ decreases until x = 10 before it explodes
        cola = valores[-3:]
        crece = all(abs(b[1]) >= abs(a[1]) * 0.999 for a, b in zip(cola, cola[1:]))
        signo = (ultimo > 0) == (resultado.valor == "+∞")
        return crece and signo and abs(ultimo) > 1e3, f"último valor {ultimo:.4g}"
    if resultado.expr is None:
        return True, "sin valor que comparar"
    objetivo = float(mx.valor_real(resultado.expr, {}))
    # Richardson with the two finest samples (error ~ h^m, m unknown: take the better)
    (h1, v1), (h2, v2) = valores[-2], valores[-1]
    extrapolado = v2 + (v2 - v1) * (h2 / (h1 - h2))
    err = min(abs(v2 - objetivo), abs(extrapolado - objetivo))
    tol = 1e-3 * max(1.0, abs(objetivo))
    return err < tol, f"f cerca del punto ≈ {v2:.8g} (extrapolado {extrapolado:.8g})"
