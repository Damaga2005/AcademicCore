# SPDX-License-Identifier: MIT
"""ML-2: the real zeros of an expression in one variable — exact when possible,
certified when not, and never a list that silently misses one.

Polynomials (rational coefficients)
-----------------------------------

1. rational roots by the rational root theorem, each divided out exactly
   (multiplicity counted);
2. what is left is made square-free (``p / gcd(p, p′)``); degree ≤ 2 by the
   formula, exactly (``±√2``);
3. degree ≥ 3 without rational roots: the **Sturm sequence** counts the real
   roots in any interval EXACTLY (rational arithmetic), so each root is isolated
   in its own interval and bisected to machine precision. The number of roots is
   a theorem, not a sample; only their decimal value is approximate, and it is
   marked so.

Other expressions
-----------------

Taken apart by factors: a product vanishes where a factor does, a quotient
where the numerator does and the denominator does not; ``exp`` never vanishes,
``ln g = 0 ⇔ g = 1``, ``√g = 0 ⇔ g = 0``, ``gᵏ = 0 ⇔ g = 0``. A rational factor
goes to the polynomial path. A transcendental factor (``cos x − x``) is solved
numerically on a declared window, each root certified by a sign change, and the
answer says that outside the window nothing was looked at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError

VENTANA = 50.0


@dataclass(frozen=True)
class Raiz:
    valor: mx.Expr            # exact expression, or a decimal Num when not exact
    x: float
    multiplicidad: int = 1
    exacta: bool = True

    def texto(self) -> str:
        t = mx.text(self.valor) if self.exacta else f"≈ {self.x:.12g}"
        return t + (f" (multiplicidad {self.multiplicidad})" if self.multiplicidad > 1 else "")


@dataclass(frozen=True)
class Ceros:
    raices: tuple[Raiz, ...]
    completo: bool            # all real zeros, or only those in the window
    avisos: tuple[str, ...] = ()

    def texto(self) -> str:
        if not self.raices:
            return "ninguno" + ("" if self.completo else " en la ventana estudiada")
        return ", ".join(r.texto() for r in self.raices)


# ---------------------------------------------------------------------------
# polynomials over ℚ, as coefficient lists (index = degree)
# ---------------------------------------------------------------------------


def _recorta(p: list[Fraction]) -> list[Fraction]:
    p = list(p)
    while p and p[-1] == 0:
        p.pop()
    return p


def _eval(p, x):
    r = 0
    for c in reversed(p):
        r = r * x + c
    return r


def _deriv(p):
    return [c * k for k, c in enumerate(p)][1:]


def _divmod(a, b):
    a, b = _recorta(a), _recorta(b)
    q = [Fraction(0)] * max(len(a) - len(b) + 1, 1)
    r = list(a)
    while len(_recorta(r)) >= len(b) and _recorta(r):
        r = _recorta(r)
        k = len(r) - len(b)
        c = r[-1] / b[-1]
        q[k] = c
        for i, bi in enumerate(b):
            r[i + k] -= c * bi
        r = _recorta(r)
    return _recorta(q), _recorta(r)


def _mcd(a, b):
    a, b = _recorta(a), _recorta(b)
    while b:
        _, r = _divmod(a, b)
        a, b = b, r
    return [c / a[-1] for c in a] if a else a


def _divisores(n: int) -> list[int]:
    n = abs(n)
    if n == 0:
        return [1]
    if n > 10 ** 12:
        return [1]
    salida = set()
    i = 1
    while i * i <= n:
        if n % i == 0:
            salida.update((i, n // i))
        i += 1
    return sorted(salida)


def _sturm(p) -> list[list[Fraction]]:
    seq = [_recorta(p), _recorta(_deriv(p))]
    while seq[-1] and len(seq[-1]) > 1:
        _, r = _divmod(seq[-2], seq[-1])
        if not r:
            break
        seq.append([-c for c in r])
    return seq


def _cambios(seq, x) -> int:
    signos = [s for s in (_signo(_eval(q, x)) for q in seq if q) if s != 0]
    return sum(1 for a, b in zip(signos, signos[1:]) if a != b)


def _signo(v) -> int:
    return (v > 0) - (v < 0)


def _cota(p) -> Fraction:
    """Cauchy: every real root lies in (−B, B)."""
    return 1 + max(abs(c / p[-1]) for c in p[:-1]) if len(p) > 1 else Fraction(1)


def _aisla(p, lo: Fraction, hi: Fraction, seq, n: int, salida: list):
    """Split (lo, hi] until each piece holds exactly one root (Sturm counts)."""
    if n == 0:
        return
    if n == 1:
        salida.append((lo, hi))
        return
    medio = (lo + hi) / 2
    if _eval(p, medio) == 0:
        medio += (hi - lo) / 7     # step off an exact root to keep counts clean
    izq = _cambios(seq, lo) - _cambios(seq, medio)
    _aisla(p, lo, medio, seq, izq, salida)
    _aisla(p, medio, hi, seq, n - izq, salida)


def _biseca(p, lo: Fraction, hi: Fraction) -> float:
    flo = _signo(_eval(p, lo))
    if flo == 0:
        return float(lo)
    a, b = float(lo), float(hi)
    for _ in range(200):
        m = (a + b) / 2
        if m in (a, b):
            break
        fm = _signo(_eval(p, Fraction(m)))
        if fm == 0:
            return m
        if fm == flo:
            a = m
        else:
            b = m
    return (a + b) / 2


def raices_polinomio(coefs) -> Ceros:
    """Real roots of Σ cₖ·xᵏ, all of them (completo is always True)."""
    p = _recorta([Fraction(c) for c in coefs])
    if not p:
        raise UnsupportedError("UNSUPPORTED: el polinomio nulo se anula en todas partes")
    raices: list[Raiz] = []
    # x^k
    k = 0
    while p and p[0] == 0:
        p, k = p[1:], k + 1
    if k:
        raices.append(Raiz(mx.Num(Fraction(0)), 0.0, k))
    # rational roots (integer coefficients first)
    if len(p) > 1:
        comun = math.lcm(*[c.denominator for c in p])
        enteros = [int(c * comun) for c in p]
        candidatos = sorted({Fraction(s * a, b) for a in _divisores(enteros[0])
                             for b in _divisores(enteros[-1]) for s in (1, -1)})
        for r in candidatos:
            m = 0
            while len(p) > 1 and _eval(p, r) == 0:
                p, _ = _divmod(p, [-r, Fraction(1)])
                m += 1
            if m:
                raices.append(Raiz(_num(r), float(r), m))
    # the rest: square-free part keeps each remaining root once; multiplicity by division
    if len(p) > 1:
        libre, _ = _divmod(p, _mcd(p, _deriv(p))) if len(p) > 2 else (p, None)
        libre = [c / libre[-1] for c in libre]
        if len(libre) == 3:
            c, b, a = libre
            disc = b * b - 4 * a * c
            if disc >= 0:
                for s in (-1, 1):
                    expr = _cuadratica(a, b, disc, s)
                    x = (-float(b) + s * math.sqrt(float(disc))) / (2 * float(a))
                    raices.append(Raiz(expr, x, _multiplicidad(p, x)))
        elif len(libre) == 2:
            r = -libre[0] / libre[1]
            raices.append(Raiz(_num(r), float(r), _multiplicidad(p, float(r))))
        elif len(libre) == 5 and libre[1] == 0 and libre[3] == 0:
            # biquadratic: y = x², then x = ±√y for each y ≥ 0
            c, _, b, _, a = libre
            disc = b * b - 4 * a * c
            if disc >= 0:
                for s in (-1, 1):
                    k, r = _raiz_simplificada(disc)
                    y_expr = _mas_raiz(-b / (2 * a), s * k / (2 * a), r)
                    y = (-float(b) + s * math.sqrt(float(disc))) / (2 * float(a))
                    if y < 0:
                        continue
                    if y == 0:
                        raices.append(Raiz(mx.Num(Fraction(0)), 0.0, 2))
                        continue
                    yq = mx.exact_value(y_expr)
                    if yq is not None:
                        kk, rr = _raiz_simplificada(Fraction(yq))
                        raiz_y = _mas_raiz(Fraction(0), kk, rr)
                    else:
                        raiz_y = mx.Root(2, y_expr)
                    for t in (-1, 1):
                        expr = raiz_y if t > 0 else mx.Neg(raiz_y)
                        x = t * math.sqrt(y)
                        raices.append(Raiz(expr, x, _multiplicidad(p, x)))
        elif len(libre) > 3:
            seq = _sturm(libre)
            B = _cota(libre)
            n = _cambios(seq, -B) - _cambios(seq, B)
            intervalos: list = []
            _aisla(libre, -B, B, seq, n, intervalos)
            for lo, hi in intervalos:
                x = _biseca(libre, lo, hi)
                raices.append(Raiz(mx.Num(Fraction(x)), x, _multiplicidad(p, x), exacta=False))
    raices.sort(key=lambda r: r.x)
    return Ceros(tuple(raices), True)


def _multiplicidad(p, x: float) -> int:
    m, q = 1, _deriv(p)
    while q and abs(float(_eval(q, Fraction(x)))) < 1e-9 * max(1.0, max(abs(float(c)) for c in q)):
        m, q = m + 1, _deriv(q)
    return m


def _num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


def _raiz_simplificada(q: Fraction) -> tuple[Fraction, Fraction]:
    """√q = k·√r with r a square-free integer (q ≥ 0)."""
    num, den = q.numerator * q.denominator, q.denominator   # √(n/d) = √(n·d)/d
    k, r, f = 1, num, 2
    while f * f <= r:
        while r % (f * f) == 0:
            r //= f * f
            k *= f
        f += 1
    return Fraction(k, den), Fraction(r)


def _mas_raiz(c1: Fraction, c2: Fraction, r: Fraction) -> mx.Expr:
    """c1 + c2·√r, written cleanly."""
    if r == 1 or c2 == 0:
        return _num(c1 + c2 * (1 if r == 1 else 0))
    raiz = mx.Root(2, mx.Num(r))
    termino = raiz if abs(c2) == 1 else mx.Mul(mx.Num(abs(c2)), raiz)
    if c1 == 0:
        return mx.Neg(termino) if c2 < 0 else termino
    return mx.Sub(_num(c1), termino) if c2 < 0 else mx.Add(_num(c1), termino)


def _cuadratica(a: Fraction, b: Fraction, disc: Fraction, s: int) -> mx.Expr:
    k, r = _raiz_simplificada(disc)
    return _mas_raiz(-b / (2 * a), s * k / (2 * a), r)


# ---------------------------------------------------------------------------
# expressions
# ---------------------------------------------------------------------------


def _polinomio_de(e: mx.Expr, var: str) -> list[Fraction] | None:
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return None
    grado = 0
    coefs: dict[int, Fraction] = {}
    for mono, c in p.items():
        d = dict(mono)
        if set(d) - {var}:
            return None
        k = d.get(var, 0)
        coefs[k] = Fraction(c)
        grado = max(grado, k)
    return [coefs.get(k, Fraction(0)) for k in range(grado + 1)]


def ceros(e: mx.Expr, var: str, ventana: tuple[float, float] = (-VENTANA, VENTANA)) -> Ceros:
    """Real zeros of ``e`` where it is defined."""
    from academic_core.domain.engineering.mathlab import poly as P

    if not mx.depends(e, var):
        v = mx.valor_real(e, {})
        if v is not None and v == 0:
            raise UnsupportedError("UNSUPPORTED: la expresión es idénticamente 0")
        return Ceros((), True)
    p = _polinomio_de(e, var)
    if p is not None:
        return raices_polinomio(p)
    try:
        razon = P.as_ratio(e, var)
    except Exception:  # noqa: BLE001
        razon = None
    if razon is not None:
        num = _polinomio_de(P.to_expr(razon.numerator), var)
        den = _polinomio_de(P.to_expr(razon.denominator), var)
        if num is not None and den is not None:
            r = raices_polinomio(num)
            return _filtra(r, e, var)
    return _filtra(_por_factores(e, var, ventana), e, var)


def _filtra(r: Ceros, e: mx.Expr, var: str) -> Ceros:
    """Keep the zeros where ``e`` is defined and really vanishes."""
    buenas = []
    for raiz in r.raices:
        v = mx.valor_real(e, {var: raiz.x})
        if v is None:
            continue
        cerca = [mx.valor_real(e, {var: raiz.x + d}) for d in (-1e-6, 1e-6)]
        escala = max([1.0] + [abs(y) for y in cerca if y is not None])
        if abs(v) <= 1e-7 * escala:
            buenas.append(raiz)
    return Ceros(tuple(sorted(buenas, key=lambda q: q.x)), r.completo, r.avisos)


def _une(*grupos: Ceros) -> Ceros:
    vistos: dict[float, Raiz] = {}
    completo, avisos = True, []
    for g in grupos:
        completo &= g.completo
        avisos += list(g.avisos)
        for r in g.raices:
            clave = round(r.x, 9)
            if clave in vistos:
                previa = vistos[clave]
                vistos[clave] = Raiz(previa.valor if previa.exacta else r.valor, previa.x,
                                     previa.multiplicidad + r.multiplicidad,
                                     previa.exacta or r.exacta)
            else:
                vistos[clave] = r
    return Ceros(tuple(sorted(vistos.values(), key=lambda q: q.x)), completo,
                 tuple(dict.fromkeys(avisos)))


def _aislada(e: mx.Expr, var: str, ventana) -> Ceros | None:
    """c ± f(g) = 0 with f invertible: ln g = k ⇒ g = eᵏ, eᵍ = k ⇒ g = ln k, √g = k ⇒ g = k²."""
    if not isinstance(e, (mx.Add, mx.Sub)):
        return None
    izq, der = e.left, e.right
    if mx.depends(izq, var) == mx.depends(der, var):
        return None
    if mx.depends(izq, var):
        f, k = izq, (mx.Neg(der) if isinstance(e, mx.Add) else der)
    else:
        f, k = (der, mx.Neg(izq)) if isinstance(e, mx.Add) else (mx.Neg(der), mx.Neg(izq))
    signo = 1
    while isinstance(f, mx.Neg):
        f, signo = f.arg, -signo
    if signo < 0:
        k = mx.Neg(k)
    if isinstance(f, mx.Root) and f.degree == 2:
        f = mx.Call("sqrt", (f.radicand,))
    if isinstance(f, mx.Pow) and mx.exact_value(f.exponent) == Fraction(1, 2):
        f = mx.Call("sqrt", (f.base,))
    if not isinstance(f, mx.Call) or len(f.args) != 1:
        return None
    g = f.args[0]
    kv = mx.valor_real(k, {})
    if kv is None:
        return None
    from academic_core.domain.engineering.mathlab import limite as LM

    if f.name in ("ln", "log"):
        return _igual_a(g, LM._limpio(mx.Call("exp", (k,))), var, ventana)
    if f.name == "exp":
        return Ceros((), True) if kv <= 0 else \
            _igual_a(g, LM._limpio(mx.Call("ln", (k,))), var, ventana)
    if f.name in ("sqrt", "raiz", "raiz2"):
        return Ceros((), True) if kv < 0 else \
            _igual_a(g, LM._limpio(mx.Pow(k, mx.Num(Fraction(2)))), var, ventana)
    return None


def _igual_a(g: mx.Expr, K: mx.Expr, var: str, ventana) -> Ceros:
    """g(x) = K with K an exact constant (maybe irrational: e, ln 3): exact when g is a
    polynomial of degree ≤ 2 with rational coefficients."""
    from academic_core.domain.engineering.mathlab import limite as LM

    q = mx.exact_value(K)
    if q is not None:
        return ceros(mx.Sub(g, _num(q)), var, ventana)
    p = _polinomio_de(g, var)
    if p is None or len(p) > 3:
        return ceros(mx.Sub(g, K), var, ventana)
    if len(p) == 2:
        expr = LM._limpio(mx.Div(mx.Sub(K, _num(p[0])), _num(p[1])))
        x = (float(mx.valor_real(K, {})) - float(p[0])) / float(p[1])
        return Ceros((Raiz(expr, x),), True)
    c, b, a = p
    disc = LM._limpio(mx.Sub(_num(b * b), mx.Mul(_num(4 * a), mx.Sub(_num(c), K))))
    dv = mx.valor_real(disc, {})
    if dv is None or dv < 0:
        return Ceros((), True)
    salida = []
    for sgn in (-1, 1):
        if b == 0:
            # a·x² + c = K  ⇒  x = ±√((K − c)/a)
            r = mx.Root(2, LM._limpio(mx.Div(mx.Sub(K, _num(c)), _num(a))))
            expr = r if sgn > 0 else mx.Neg(r)
        else:
            expr = LM._limpio(mx.Div(mx.Add(_num(-b), mx.Mul(_num(sgn),
                                                             mx.Root(2, disc))),
                                     _num(2 * a)))
        x = (-float(b) + sgn * math.sqrt(dv)) / (2 * float(a))
        salida.append(Raiz(expr, x))
    return Ceros(tuple(sorted(salida, key=lambda r: r.x)), True)


def _por_factores(e: mx.Expr, var: str, ventana) -> Ceros:
    aislada = _aislada(e, var, ventana)
    if aislada is not None:
        return aislada
    if isinstance(e, mx.Neg):
        return _por_factores(e.arg, var, ventana)
    if isinstance(e, mx.Mul):
        return _une(ceros(e.left, var, ventana), ceros(e.right, var, ventana))
    if isinstance(e, mx.Div):
        return ceros(e.left, var, ventana)          # filtered later where e is undefined
    if isinstance(e, mx.Pow):
        k = mx.exact_value(e.exponent)
        if k is not None and k > 0:
            return ceros(e.base, var, ventana)
    if isinstance(e, mx.Root):
        return ceros(e.radicand, var, ventana)
    if isinstance(e, mx.Call):
        if e.name == "exp":
            return Ceros((), True)
        if e.name in ("sqrt", "raiz", "raiz2", "abs", "valor_abs", "sinh", "tanh", "asin",
                      "atan", "asinh"):
            return ceros(e.args[0], var, ventana)
        if e.name in ("ln", "log"):
            return ceros(mx.Sub(e.args[0], mx.Num(Fraction(1))), var, ventana)
    return _numericos(e, var, ventana)


def _numericos(e: mx.Expr, var: str, ventana) -> Ceros:
    from academic_core.domain.engineering.mathlab import continuidad as K

    a, b = ventana
    raices = []
    for c in K.ceros_numericos(e, var, a, b):
        r = K.raiz_certificada(e, var, c)
        raices.append(Raiz(mx.Num(Fraction(r.valor)), r.valor, 1, exacta=False))
    aviso = (f"«{mx.text(e)}» no tiene solución exacta conocida: raíces numéricas "
             f"certificadas por cambio de signo en [{a:g}, {b:g}]; fuera de ese intervalo no "
             "se ha buscado")
    return Ceros(tuple(raices), False, (aviso,))
