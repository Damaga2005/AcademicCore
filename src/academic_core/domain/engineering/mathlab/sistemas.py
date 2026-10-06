# SPDX-License-Identifier: MIT
"""ML-5: sistemas polinómicos con solución aislada (puntos críticos y Lagrange).

    ∇f = 0                      (puntos críticos)
    ∇f = λ₁∇g₁ + …, gᵢ = 0      (Lagrange)

no son lineales en general (x³ − 3x + y², ligadura x² + y² = 1). El método:

1. Cada ecuación se pasa a polinomio exacto sobre ℚ. Un factor exp(·) común a
   todos los términos se quita (exp > 0 no se anula); otra función no polinómica
   se rechaza con su motivo.
2. Eliminación por bases de Gröbner en orden lex con v la última: el elemento
   de la base que solo tiene v genera el ideal de eliminación, así que sus ceros
   son exactamente las proyecciones de las soluciones (complejas): nada se pierde
   y no aparecen factores sobrantes.
3. Las raíces reales de cada p_v salen de :mod:`raices` (Sturm: todas, con
   certificado): racionales exactas, cuadráticas en ℚ(√r) exactas (también las
   que vienen de un factor cuadrático escondido en un p_v de grado alto, que se
   detecta y se comprueba por división exacta) y, si no, numéricas.
4. Las combinaciones candidatas se filtran sustituyendo en el sistema original;
   las exactas se comprueban además con aritmética exacta.

Si la base no tiene elemento en una sola variable las soluciones no están aisladas (una curva
de puntos críticos): se dice, no se inventa una lista.
"""

from __future__ import annotations

import itertools
import time
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

MAX_INCOGNITAS = 5
MAX_CANDIDATOS = 20000
MAX_TERMINOS = 4000
MAX_PASOS = 4000
MAX_SEGUNDOS = 8.0


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# expresión → polinomio sobre ℚ
# ---------------------------------------------------------------------------


def _prelin(e: mx.Expr) -> mx.Expr:
    if isinstance(e, mx.Div):
        c = mx.exact_value(e.right)
        if c is not None and c != 0 and not mx.variables(e.right):
            return mx.Mul(_prelin(e.left), mx.Num(Fraction(1) / Fraction(c)))
        return mx.Div(_prelin(e.left), _prelin(e.right))
    if isinstance(e, (mx.Mul, mx.Add, mx.Sub)):
        return type(e)(_prelin(e.left), _prelin(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_prelin(e.arg))
    return e


def a_polinomio(e: mx.Expr, incognitas: list[str], trace: Trace) -> P.Polynomial:
    """Polinomio exacto en las incógnitas; quita un factor exp(·) > 0 común."""
    try:
        p = P.as_poly(_prelin(e))
    except (ValidationError, UnsupportedError) as exc:
        raise _no(f"«{mx.text(e)}» no se lleva a polinomio: {exc}") from None
    for atomo in sorted({v for m in p for v, _ in m if P.is_atom(v)}):
        texto = P.atom_text(atomo)
        minimo = min(P.mono_exp(m, atomo) for m in p)
        if minimo > 0 and P.es_llamada(texto, "exp"):
            p = {P.mono_div(m, ((atomo, minimo),)): c for m, c in p.items()}
            trace.regla("sistema.exp", f"se divide entre {texto}" +
                        (f"^{minimo}" if minimo > 1 else ""),
                        why="la exponencial es > 0: no aporta ceros")
    resto = {P.atom_text(v) for m in p for v, _ in m if P.is_atom(v)}
    if resto:
        raise _no(f"«{mx.text(e)}» contiene {', '.join(sorted(resto))}, que no es "
                  "polinómico en las incógnitas: el sistema no se resuelve exacto aquí")
    libres = P.real_variables(p) - set(incognitas)
    if libres:
        raise _no(f"parámetros libres {', '.join(sorted(libres))}: fija su valor")
    return p


# ---------------------------------------------------------------------------
# bases de Gröbner en orden lexicográfico (Buchberger con criterio del producto)
# ---------------------------------------------------------------------------

Exp = tuple[int, ...]
Poli = dict[Exp, Fraction]


def _a_exp(p: P.Polynomial, orden: list[str]) -> Poli:
    out: Poli = {}
    for m, c in p.items():
        e = tuple(P.mono_exp(m, v) for v in orden)
        out[e] = out.get(e, Fraction(0)) + c
    return {e: c for e, c in out.items() if c}


def lex(e: Exp):
    return e


def grevlex(e: Exp):
    """Grado total y, a igualdad, el menor exponente de la última variable gana."""
    return (sum(e), tuple(-x for x in reversed(e)))


_ORDEN = [lex]          # orden activo (lo fija ``grobner``; lex por defecto)


def _lider(p: Poli) -> Exp:
    return max(p, key=_ORDEN[0])


def _monico(p: Poli) -> Poli:
    c = p[_lider(p)]
    return {e: x / c for e, x in p.items()}


def _divide_mono(a: Exp, b: Exp) -> Exp | None:
    if all(x >= y for x, y in zip(a, b)):
        return tuple(x - y for x, y in zip(a, b))
    return None


def _resta_mult(p: Poli, c: Fraction, t: Exp, g: Poli) -> Poli:
    out = dict(p)
    for e, x in g.items():
        k = tuple(a + b for a, b in zip(e, t))
        v = out.get(k, Fraction(0)) - c * x
        if v:
            out[k] = v
        else:
            out.pop(k, None)
    return out


def _reduce(p: Poli, G: list[Poli]) -> Poli:
    """Forma normal completa de p módulo G (en el orden activo)."""
    resto: Poli = {}
    p = dict(p)
    lideres = [(_lider(g), g) for g in G]
    while p:
        lp = _lider(p)
        for lg, g in lideres:
            t = _divide_mono(lp, lg)
            if t is not None:
                p = _resta_mult(p, p[lp] / g[lg], t, g)
                break
        else:
            resto[lp] = p.pop(lp)
        if len(p) + len(resto) > MAX_TERMINOS:
            raise _no("la base de Gröbner crece demasiado")
    return resto


def _mcm(a: Exp, b: Exp) -> Exp:
    return tuple(max(x, y) for x, y in zip(a, b))


def _spoli(f: Poli, g: Poli) -> Poli:
    lf, lg = _lider(f), _lider(g)
    m = _mcm(lf, lg)
    tf = tuple(a - b for a, b in zip(m, lf))
    tg = tuple(a - b for a, b in zip(m, lg))
    s = _resta_mult({}, -1 / f[lf], tf, f)
    return _resta_mult(s, 1 / g[lg], tg, g)


def grobner(polis: list[Poli], orden=lex) -> list[Poli]:
    """Base de Gröbner reducida. Buchberger con estrategia normal (par de menor mcm
    primero), criterio del producto y criterio de la cadena."""
    _ORDEN[0] = orden
    G = [_monico(p) for p in polis if p]
    for g in G:
        if all(x == 0 for x in _lider(g)):
            return [{_lider(g): Fraction(1)}]
    hechos: set[tuple[int, int]] = set()
    pares = {(i, j) for i in range(len(G)) for j in range(i)}
    pasos = 0
    limite = time.monotonic() + MAX_SEGUNDOS
    while pares:
        pasos += 1
        if pasos > MAX_PASOS or time.monotonic() > limite:
            raise _no("la base de Gröbner no termina en un tamaño razonable")
        i, j = min(pares, key=lambda ij: orden(_mcm(_lider(G[ij[0]]), _lider(G[ij[1]]))))
        pares.discard((i, j))
        hechos.add((i, j))
        li, lj = _lider(G[i]), _lider(G[j])
        if all(a == 0 or b == 0 for a, b in zip(li, lj)):
            continue                                   # criterio del producto
        m = _mcm(li, lj)
        if any(k not in (i, j) and _divide_mono(m, _lider(G[k])) is not None
               and (max(i, k), min(i, k)) in hechos and (max(j, k), min(j, k)) in hechos
               for k in range(len(G))):
            continue                                   # criterio de la cadena
        r = _reduce(_spoli(G[i], G[j]), G)
        if r:
            G.append(_monico(r))
            if all(x == 0 for x in _lider(r)):
                return [G[-1]]                         # 1 ∈ ideal
            n = len(G) - 1
            pares.update((n, k) for k in range(n))
    G = [g for k, g in enumerate(G)
         if not any(_divide_mono(_lider(g), _lider(h)) is not None and
                    (_lider(h) != _lider(g) or m < k)
                    for m, h in enumerate(G) if m != k)]
    return [_monico(_reduce(g, [h for h in G if h is not g])) or g for g in G]


def dimension_cero(G: list[Poli], n: int) -> bool:
    """Finitas soluciones (complejas) ⇔ cada variable tiene una potencia pura líder."""
    puras = {k for g in G for k in range(n)
             if (l := _lider(g))[k] > 0 and sum(l) == l[k]}
    return len(puras) == n


def polinomio_minimo(G: list[Poli], k: int, n: int, max_grado: int = 200) -> list[Fraction]:
    """Polinomio de menor grado en x_k dentro del ideal (FGLM en una variable):
    formas normales de 1, x_k, x_k², … hasta la primera dependencia lineal."""
    uno = tuple(0 for _ in range(n))
    xk = tuple(1 if i == k else 0 for i in range(n))
    filas: list[tuple[Poli, list[Fraction]]] = []     # (vector reducido, combinación)
    actual: Poli = _reduce({uno: Fraction(1)}, G)
    for grado in range(max_grado + 1):
        vec = dict(actual)
        comb = [Fraction(0)] * (grado + 1)
        comb[grado] = Fraction(1)
        for piv, (fv, fc) in [(max(fv, key=_ORDEN[0]), (fv, fc)) for fv, fc in filas]:
            c = vec.get(piv)
            if c:
                vec = _resta_mult(vec, c / fv[piv], uno, fv)
                for t, x in enumerate(fc):
                    comb[t] -= c / fv[piv] * x
        if not vec:
            return comb                                # Σ comb[t]·x_k^t ∈ ideal
        filas.append((vec, comb))
        actual = _reduce({tuple(a + b for a, b in zip(e, xk)): c
                          for e, c in actual.items()}, G)
    raise _no(f"el polinomio en una variable supera grado {max_grado}")


@dataclass(frozen=True)
class Valor:
    expr: mx.Expr
    x: float
    exacto: bool

    @property
    def fraccion(self) -> Fraction | None:
        q = mx.exact_value(self.expr) if self.exacto else None
        return Fraction(q) if q is not None else None


def raices_exactas(coefs: list[Fraction]) -> list[Valor]:
    """Raíces reales (sin repetir) de un polinomio de ℚ[x]; las de un factor
    cuadrático escondido salen exactas también (se halla por pares y se
    comprueba con división exacta)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    r = RZ.raices_polinomio(coefs)
    vals = [Valor(z.valor, z.x, z.exacta) for z in r.raices]
    sueltas = [i for i, v in enumerate(vals) if not v.exacto]
    p = RZ._recorta([Fraction(c) for c in coefs])
    usados: set[int] = set()
    for i, j in itertools.combinations(sueltas, 2):
        if i in usados or j in usados:
            continue
        s = Fraction(vals[i].x + vals[j].x).limit_denominator(10 ** 6)
        q = Fraction(vals[i].x * vals[j].x).limit_denominator(10 ** 6)
        cuad = [q, -s, Fraction(1)]
        _, resto = RZ._divmod(p, cuad)
        if resto:
            continue
        disc = s * s - 4 * q
        for k, sg in ((i, -1 if vals[i].x < vals[j].x else 1),
                      (j, 1 if vals[i].x < vals[j].x else -1)):
            vals[k] = Valor(RZ._cuadratica(Fraction(1), -s, disc, sg), vals[k].x, True)
        usados.update((i, j))
    return vals


def factores(coefs: list[Fraction]) -> list[tuple[list[Fraction], list[Valor]]]:
    """Agrupa las raíces reales de p ∈ ℚ[x] por factor racional: (x − r) para cada
    racional, el cuadrático de cada par en ℚ(√r) y, para las numéricas, el resto de p.
    Cada factor tiene coeficientes racionales (sirve para plantear m(f) = 0)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    p = RZ._recorta([Fraction(c) for c in coefs])
    vals = raices_exactas(p)
    grupos: list[tuple[list[Fraction], list[Valor]]] = []
    usados: set[int] = set()
    for i, v in enumerate(vals):
        q = v.fraccion
        if q is not None:
            grupos.append(([-q, Fraction(1)], [v]))
            usados.add(i)
    for i, j in itertools.combinations(range(len(vals)), 2):
        if i in usados or j in usados or not (vals[i].exacto and vals[j].exacto):
            continue
        s_ = Fraction(vals[i].x + vals[j].x).limit_denominator(10 ** 6)
        q_ = Fraction(vals[i].x * vals[j].x).limit_denominator(10 ** 6)
        cuad = [q_, -s_, Fraction(1)]
        if not RZ._divmod(p, cuad)[1]:
            grupos.append((cuad, [vals[i], vals[j]]))
            usados.update((i, j))
    resto = [v for i, v in enumerate(vals) if i not in usados]
    if resto:
        q = p
        for m, _ in grupos:
            while not RZ._divmod(q, m)[1] and len(q) > 1:
                q = RZ._divmod(q, m)[0]
        grupos.append((q, resto))
    return grupos


def _valor_en(p: P.Polynomial, punto: dict[str, float]) -> tuple[float, float]:
    total, escala = 0.0, 0.0
    for m, c in p.items():
        t = float(c)
        for v, e in m:
            t *= punto[v] ** e
        total += t
        escala += abs(t)
    return total, escala


def radical_monomios(G: list[Poli], n: int) -> list[Poli]:
    """Descripción más simple del mismo conjunto: un monomio x^a·y^b se cambia por
    x·y (mismo conjunto de ceros); x = 0 absorbe a los generadores que divide; se
    quitan repetidos."""
    out: list[Poli] = []
    for g in G:
        if len(g) == 1:
            (e, _), = g.items()
            g = {tuple(1 if x else 0 for x in e): Fraction(1)}
        if g not in out:
            out.append(g)
    ceros = {i for g in out if len(g) == 1 for e in g if sum(e) == 1 for i, x in enumerate(e) if x}
    final = []
    for g in out:
        es_cero = len(g) == 1 and sum(next(iter(g))) == 1
        if not es_cero and any(all(e[i] > 0 for e in g) for i in ceros):
            continue
        final.append(g)
    # un monomio múltiplo de otro monomio presente sobra
    mon = [next(iter(g)) for g in final if len(g) == 1]
    return [g for g in final if not (len(g) == 1 and any(
        m != next(iter(g)) and _divide_mono(next(iter(g)), m) is not None for m in mon))]


def resolver(ecuaciones: list[mx.Expr], incognitas: list[str],
             trace: Trace | None = None) -> list[dict[str, Valor]]:
    """Todas las soluciones reales aisladas del sistema; UNSUPPORTED si no lo están."""
    trace = trace if trace is not None else Trace()
    if len(incognitas) > MAX_INCOGNITAS:
        raise _no(f"más de {MAX_INCOGNITAS} incógnitas")
    polis = []
    for e in ecuaciones:
        p = a_polinomio(e, incognitas, trace)
        if not p:
            continue
        if len(p) == 1 and () in p:
            trace.regla("sistema.incompatible", f"{mx.text(e)} = 0 es imposible")
            return []
        polis.append(p)
    if not polis:
        raise _no("todas las ecuaciones son 0 = 0: las soluciones no están aisladas")
    from academic_core.domain.engineering.mathlab import raices as RZ

    candidatas: dict[str, list[Valor]] = {}
    n = len(incognitas)
    G = grobner([_a_exp(p, incognitas) for p in polis], grevlex)
    if len(G) == 1 and all(x == 0 for x in _lider(G[0])):
        trace.regla("sistema.incompatible", "1 está en el ideal (base de Gröbner {1})",
                    why="el sistema no tiene solución ni siquiera compleja")
        return []
    if not dimension_cero(G, n):
        from academic_core.domain.engineering.mathlab import multiple as MI

        orden = list(incognitas)

        def a_expr(g):
            return MI._bonito(P.to_expr({tuple((nm, e) for nm, e in zip(orden, ex) if e): c
                                         for ex, c in g.items()}))
        desc = "; ".join(f"{mx.text(a_expr(g))} = 0" for g in radical_monomios(G, n))
        trace.regla("sistema.no_aislado", f"conjunto de soluciones: {desc}",
                    why="base de Gröbner reducida: describe el mismo conjunto, y alguna "
                        "variable no tiene potencia pura entre los términos líderes")
        raise _no(f"las soluciones no están aisladas (hay una curva o superficie de "
                  f"soluciones): {desc}")
    for k, v in enumerate(incognitas):
        orden = [u for u in incognitas if u != v] + [v]
        uni = polinomio_minimo(G, k, n)
        sin_rep = RZ._divmod(uni, RZ._mcd(uni, RZ._deriv(uni)))[0] if len(uni) > 2 else uni
        candidatas[v] = raices_exactas(sin_rep)
        from academic_core.domain.engineering.mathlab import poly as Pm

        from academic_core.domain.engineering.mathlab import multiple as MI

        poli_v = MI._bonito(Pm.to_expr({((v, k),) if k else (): c for k, c in enumerate(sin_rep) if c}))
        trace.regla("sistema.eliminacion",
                    f"eliminando {', '.join(orden[:-1]) or 'nada'}: {mx.text(poli_v)} = 0 → "
                    f"{v} ∈ {{" + ", ".join(mx.text(z.expr) if z.exacto else f"≈ {z.x:.10g}"
                                           for z in candidatas[v]) + "}",
                    why="polinomio mínimo de la variable en el ideal (formas normales "
                        "respecto de la base de Gröbner): sus raíces son las proyecciones "
                        "de todas las soluciones; raíces reales por Sturm")
    total = math.prod(len(c) for c in candidatas.values())
    if total > MAX_CANDIDATOS:
        raise _no(f"{total} combinaciones candidatas: demasiadas")
    soluciones: list[dict[str, Valor]] = []
    for combo in itertools.product(*(candidatas[v] for v in incognitas)):
        punto = {v: z.x for v, z in zip(incognitas, combo)}
        if all(abs(val) <= 1e-9 * max(1.0, esc) for val, esc in
               (_valor_en(p, punto) for p in polis)):
            soluciones.append(dict(zip(incognitas, combo)))
    for s in soluciones:
        _comprueba_exacta(polis, s)
    trace.verificacion("sistema.sustitucion",
                       f"{len(soluciones)} solución(es); cada una sustituida en el sistema "
                       "(exacta cuando las coordenadas lo son)")
    return soluciones


def _comprueba_exacta(polis: list[P.Polynomial], s: dict[str, Valor]) -> None:
    """Las coordenadas racionales se sustituyen en ℚ; con √ se comprueba en ℚ(√r)."""
    from academic_core.domain.engineering.mathlab import verify as V

    if not all(z.exacto for z in s.values()):
        return
    for p in polis:
        e = P.to_expr(p)
        for v, z in s.items():
            e = mx.substitute(e, v, z.expr)
        iguales, _, _ = V.check_equivalence(e, mx.Num(Fraction(0)))
        if not iguales:
            q = mx.valor_real(e, {})
            if q is None or abs(q) > 1e-9:
                raise ValidationError("INTERNAL: la solución exacta no cumple el sistema")


# ---------------------------------------------------------------------------
# mcd de polinomios en varias variables (conjuntos de soluciones no aislados)
# ---------------------------------------------------------------------------


def _por(a: Poli, b: Poli) -> Poli:
    out: Poli = {}
    for ea, ca in a.items():
        for eb, cb in b.items():
            e = tuple(x + y for x, y in zip(ea, eb))
            out[e] = out.get(e, Fraction(0)) + ca * cb
    return {e: c for e, c in out.items() if c}


def divide_exacto(p: Poli, d: Poli) -> Poli | None:
    """p/d si d divide a p (división larga en orden lex); None si no."""
    _ORDEN[0] = lex
    p, q = dict(p), {}
    ld = _lider(d)
    while p:
        lp = _lider(p)
        t = _divide_mono(lp, ld)
        if t is None:
            return None
        c = p[lp] / d[ld]
        q[t] = q.get(t, Fraction(0)) + c
        p = _resta_mult(p, c, t, d)
    return q


def mcd(a: Poli, b: Poli) -> Poli:
    """mcd(a, b) = a·b / mcm(a, b); el mcm genera ⟨a⟩ ∩ ⟨b⟩, que se obtiene
    eliminando t de ⟨t·a, (1 − t)·b⟩ (Gröbner lex con t la mayor)."""
    if not a:
        return b
    if not b:
        return a
    n = len(next(iter(a)))
    ta = {(1,) + e: c for e, c in a.items()}
    unomenost = {(0,) + (0,) * n: Fraction(1), (1,) + (0,) * n: Fraction(-1)}
    tb = _por(unomenost, {(0,) + e: c for e, c in b.items()})
    G = grobner([ta, tb], lex)
    sin_t = [g for g in G if all(e[0] == 0 for e in g)]
    if not sin_t:
        return {(0,) * n: Fraction(1)}
    m = min(sin_t, key=lambda g: (sum(_lider(g)), len(g)))
    m = {e[1:]: c for e, c in m.items()}
    g = divide_exacto(_por(a, b), m)
    if g is None:
        raise _no("el mcd no divide (no debería ocurrir)")
    return _monico(g) if g else {(0,) * n: Fraction(1)}


def factor_comun(polis: list[Poli]) -> tuple[Poli, list[Poli]]:
    """h = mcd de todos y los cofactores pᵢ/h."""
    h = polis[0]
    for p in polis[1:]:
        h = mcd(h, p)
    return h, [divide_exacto(p, h) or {} for p in polis]
