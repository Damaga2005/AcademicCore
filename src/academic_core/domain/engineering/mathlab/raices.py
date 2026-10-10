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
    # tanteo solo hasta ∛n: lo que queda no tiene factores ≤ ∛n, luego tiene a lo
    # sumo dos primos (1, p, p·q o p²) y basta mirar si es un cuadrado. Exacto y
    # O(n^⅓); el tanteo hasta √n tardaba 10 ms por llamada con n ~ 10⁹
    k, libre, m = 1, 1, num
    tope = round(num ** (1 / 3)) + 2
    f = 2
    while f <= tope and f * f <= m:
        e = 0
        while m % f == 0:
            m //= f
            e += 1
        k *= f ** (e // 2)
        libre *= f ** (e % 2)
        f += 1 if f == 2 else 2
    t = math.isqrt(m)
    if t * t == m:
        k *= t
    else:
        libre *= m
    return Fraction(k, den), Fraction(libre)


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
    if _sin_ceros(e, var):
        return Ceros((), True)
    if isinstance(e, mx.Neg):
        return ceros(e.arg, var, ventana)
    if isinstance(e, (mx.Mul, mx.Div)):
        # a product vanishes where a factor does (and the product is defined there);
        # the denominator of a quotient contributes no zeros
        partes = (e.left, e.right) if isinstance(e, mx.Mul) else (e.left,)
        partes = tuple(f for f in partes if mx.depends(f, var) and not _sin_ceros(f, var))
        if not partes:
            return Ceros((), True)
        acumulado = Ceros((), True)
        for f in partes:
            acumulado = _une(acumulado, ceros(f, var, ventana))
        return _filtra(acumulado, e, var)
    trozos = _por_trozos(e, var, ventana)
    if trozos is not None:
        return trozos
    por_atomos = _por_atomos(e, var, ventana)
    if por_atomos is not None:
        return _filtra(por_atomos, e, var)
    return _filtra(_por_factores(e, var, ventana), e, var)


_TROCEABLES = ("abs", "valor_abs", "sign", "signo")


def _troceables(e: mx.Expr, var: str) -> list[mx.Expr]:
    salida = []
    if isinstance(e, mx.Call) and e.name in _TROCEABLES and mx.depends(e.args[0], var):
        salida.append(e.args[0])
    for hijo in _hijos_de(e):
        salida.extend(_troceables(hijo, var))
    return salida


def _hijos_de(n: mx.Expr):
    if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return (n.left, n.right)
    if isinstance(n, mx.Neg):
        return (n.arg,)
    if isinstance(n, mx.Pow):
        return (n.base, n.exponent)
    if isinstance(n, mx.Root):
        return (n.radicand,)
    if isinstance(n, mx.Call):
        return n.args
    return ()


def _sin_valor_absoluto(e: mx.Expr, var: str, x: float) -> mx.Expr:
    """On a piece where every |g| and sign(g) has a fixed sign, replace them."""
    if isinstance(e, mx.Call) and e.name in _TROCEABLES and mx.depends(e.args[0], var):
        g = _sin_valor_absoluto(e.args[0], var, x)
        v = mx.valor_real(g, {var: x})
        s = 1 if v > 0 else -1
        if e.name in ("sign", "signo"):
            return mx.Num(Fraction(s)) if s > 0 else mx.Neg(mx.Num(Fraction(1)))
        return g if s > 0 else mx.Neg(g)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sin_valor_absoluto(e.left, var, x), _sin_valor_absoluto(e.right, var, x))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_valor_absoluto(e.arg, var, x))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sin_valor_absoluto(e.base, var, x), e.exponent)
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _sin_valor_absoluto(e.radicand, var, x))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_sin_valor_absoluto(a, var, x) for a in e.args))
    return e


def _por_trozos(e: mx.Expr, var: str, ventana) -> Ceros | None:
    """|g| and sign(g): cut at the zeros of every g, solve each piece without them."""
    args = _troceables(e, var)
    if not args:
        return None
    cortes_c = _une(*[ceros(g, var, ventana) for g in args])
    cortes = [r.x for r in cortes_c.raices]
    bordes = [None] + cortes + [None]
    partes = []
    for a, b in zip(bordes, bordes[1:]):
        x = 0.0 if a is None and b is None else (b - 1 if a is None else a + 1 if b is None
                                                 else (a + b) / 2)
        try:
            liso = _sin_valor_absoluto(e, var, x)
        except Exception:  # noqa: BLE001
            return None
        try:
            trozo = ceros(liso, var, ventana)
        except UnsupportedError:
            # identically 0 on the whole piece: no isolated zero there
            partes.append(Ceros((), True, (f"«{mx.text(e)}» es idénticamente 0 en un tramo",)))
            continue
        dentro = tuple(r for r in trozo.raices
                       if (a is None or r.x > a + 1e-12) and (b is None or r.x < b - 1e-12))
        partes.append(Ceros(dentro, trozo.completo, trozo.avisos))
    # the cut points themselves
    propios = tuple(r for r in cortes_c.raices
                    if (v := mx.valor_real(e, {var: r.x})) is not None and abs(v) < 1e-12)
    partes.append(Ceros(propios, cortes_c.completo))
    return _une(*partes)


def _por_atomos(e: mx.Expr, var: str, ventana) -> Ceros | None:
    """Seen as a polynomial in x and in atoms like e^(−x) or ln x:
    - an atom e^(…) that divides every term never vanishes: divide it out
      (e^(−x) − x·e^(−x) = e^(−x)·(1 − x));
    - if what is left involves ONE atom f(x) with f invertible and no bare x,
      it is a polynomial in y = f(x): solve for y exactly, then x = f⁻¹(y)
      (2·ln x − 3 = 0 ⇒ ln x = 3/2 ⇒ x = e^(3/2))."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return None
    atomos = {n for mono in p for n, _ in mono if P.is_atom(n)}
    if not atomos:
        return None
    textos = {a: P.atom_text(a) for a in atomos}
    # never-vanishing atoms: exp(...)
    for a in list(atomos):
        if P.es_llamada(textos[a], "exp"):
            minimo = min(dict(m).get(a, 0) for m in p)
            if minimo > 0:
                p = {tuple((n, k - minimo) if n == a else (n, k) for n, k in m if
                           not (n == a and k == minimo)): c for m, c in p.items()}
    restantes = {n for mono in p for n, _ in mono if P.is_atom(n)}
    if not restantes:
        return ceros(P.to_expr(p), var, ventana)
    if len(restantes) != 1 or any(n == var for mono in p for n, _ in mono):
        nuevo = P.to_expr(p)
        return None if mx.text(nuevo) == mx.text(e) else _filtra(_por_factores(nuevo, var, ventana),
                                                              nuevo, var)
    atomo = restantes.pop()
    interno = mx.parse(P.atom_text(atomo))
    if not isinstance(interno, mx.Call) or interno.name not in ("ln", "exp") or \
            len(interno.args) != 1:
        return None
    y = "_y"
    poli_y = {tuple((y if n == atomo else n, k) for n, k in m): c for m, c in p.items()}
    soluciones = raices_polinomio(_polinomio_de(P.to_expr(poli_y), y) or [Fraction(0)])
    partes = []
    for r in soluciones.raices:
        valor = r.valor if r.exacta else mx.Num(Fraction(r.x))
        if interno.name == "ln":
            objetivo = mx.Call("exp", (valor,))
        else:
            if r.x <= 0:
                continue
            objetivo = mx.Call("ln", (valor,))
        from academic_core.domain.engineering.mathlab import limite as LM

        partes.append(_igual_a(interno.args[0], LM._limpio(objetivo), var, ventana))
    return _une(*partes) if partes else Ceros((), True)


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


def _sin_ceros(e: mx.Expr, var: str) -> bool:
    """Factors that never vanish: e^u, c^u with c > 0, 1/u, cosh u, nonzero constants."""
    if not mx.depends(e, var):
        v = mx.valor_real(e, {})
        return v is not None and v != 0
    if isinstance(e, mx.Call) and e.name in ("exp", "cosh"):
        return True
    if isinstance(e, mx.Neg):
        return _sin_ceros(e.arg, var)
    if isinstance(e, mx.Pow):
        k = mx.exact_value(e.exponent)
        if k is not None and k < 0:
            return True
        if not mx.depends(e.base, var):
            v = mx.valor_real(e.base, {})
            return v is not None and v > 0
        if k is not None and k > 0:
            return _sin_ceros(e.base, var)
    if isinstance(e, mx.Div):
        return _sin_ceros(e.left, var)
    if isinstance(e, mx.Mul):
        return _sin_ceros(e.left, var) and _sin_ceros(e.right, var)
    return False


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
    if isinstance(e, mx.Call) and e.name in ("sin", "cos") and len(e.args) == 1:
        lineal = _polinomio_de(e.args[0], var)
        if lineal is not None and len(_recorta(lineal)) == 2:
            # sin(m·x + q) = 0 ⇔ m·x + q = kπ;  cos: = π/2 + kπ — exact, inside the window
            q, m = lineal[0], lineal[1]
            desfase = Fraction(0) if e.name == "sin" else Fraction(1, 2)
            raices = []
            a, b = ventana
            kmin = math.floor((m * a + q) / math.pi - 1) if m > 0 else math.floor((m * b + q) / math.pi - 1)
            kmax = math.ceil((m * b + q) / math.pi + 1) if m > 0 else math.ceil((m * a + q) / math.pi + 1)
            for k in range(kmin, kmax + 1):
                # x = ((k + desfase)·π − q)/m
                expr = mx.Div(mx.Sub(mx.Mul(_num(k + desfase), mx.Const("pi")), _num(q)), _num(m))
                from academic_core.domain.engineering.mathlab import limite as LM

                expr = LM._limpio(expr)
                x = (float(k + desfase) * math.pi - float(q)) / float(m)
                if a <= x <= b:
                    raices.append(Raiz(expr, x))
            aviso = (f"«{mx.text(e)}» tiene infinitos ceros (periódica): se dan los de "
                     f"[{a:g}, {b:g}]")
            return Ceros(tuple(raices), False, (aviso,))
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
