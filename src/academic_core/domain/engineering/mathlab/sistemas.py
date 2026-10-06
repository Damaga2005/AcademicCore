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
        if minimo > 0 and texto.startswith("exp("):
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


def _lider(p: Poli) -> Exp:
    return max(p)


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
    """Forma normal completa de p módulo G."""
    resto: Poli = {}
    p = dict(p)
    while p:
        lp = _lider(p)
        for g in G:
            t = _divide_mono(lp, _lider(g))
            if t is not None:
                p = _resta_mult(p, p[lp] / g[_lider(g)], t, g)
                break
        else:
            resto[lp] = p.pop(lp)
        if len(p) + len(resto) > MAX_TERMINOS:
            raise _no("la base de Gröbner crece demasiado")
    return resto


def _spoli(f: Poli, g: Poli) -> Poli:
    lf, lg = _lider(f), _lider(g)
    mcm = tuple(max(a, b) for a, b in zip(lf, lg))
    tf = tuple(a - b for a, b in zip(mcm, lf))
    tg = tuple(a - b for a, b in zip(mcm, lg))
    s = _resta_mult({}, -1 / f[lf], tf, f)
    return _resta_mult(s, 1 / g[lg], tg, g)


def grobner(polis: list[Poli]) -> list[Poli]:
    """Base de Gröbner reducida (orden lex sobre la tupla de exponentes)."""
    G = [_monico(p) for p in polis if p]
    pares = [(i, j) for i in range(len(G)) for j in range(i)]
    pasos = 0
    limite = time.monotonic() + MAX_SEGUNDOS
    while pares:
        pasos += 1
        if pasos > MAX_PASOS or time.monotonic() > limite:
            raise _no("la base de Gröbner no termina en un tamaño razonable")
        i, j = pares.pop(0)
        li, lj = _lider(G[i]), _lider(G[j])
        if all(a == 0 or b == 0 for a, b in zip(li, lj)):
            continue                                   # criterio del producto
        r = _reduce(_spoli(G[i], G[j]), G)
        if r:
            G.append(_monico(r))
            if all(x == 0 for x in _lider(r)):
                return [G[-1]]                         # 1 ∈ ideal
            pares.extend((len(G) - 1, k) for k in range(len(G) - 1))
    # minimal y reducida
    G = [g for k, g in enumerate(G)
         if not any(_divide_mono(_lider(g), _lider(h)) is not None and
                    (_lider(h) != _lider(g) or m < k)
                    for m, h in enumerate(G) if m != k)]
    return [_monico(_reduce(g, [h for h in G if h is not g])) or g for g in G]


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


def _valor_en(p: P.Polynomial, punto: dict[str, float]) -> tuple[float, float]:
    total, escala = 0.0, 0.0
    for m, c in p.items():
        t = float(c)
        for v, e in m:
            t *= punto[v] ** e
        total += t
        escala += abs(t)
    return total, escala


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
    for v in incognitas:
        orden = [u for u in incognitas if u != v] + [v]
        G = grobner([_a_exp(p, orden) for p in polis])
        if len(G) == 1 and all(x == 0 for x in _lider(G[0])):
            trace.regla("sistema.incompatible", "1 está en el ideal (base de Gröbner {1})",
                        why="el sistema no tiene solución ni siquiera compleja")
            return []
        solo_v = [g for g in G if all(x == 0 for x in _lider(g)[:-1])]
        if not solo_v:
            from academic_core.domain.engineering.mathlab import multiple as MI

            def a_expr(g):
                return MI._bonito(P.to_expr({tuple((n, e) for n, e in zip(orden, ex) if e): c
                                             for ex, c in g.items()}))
            # x^k = 0 ⇔ x = 0: con un monomio puro en una variable basta esa variable,
            # y las ecuaciones que ya se anulan con ella sobran
            ceros = {i for g in G if len(g) == 1 for ex in g
                     if sum(1 for e in ex if e) == 1 for i, e in enumerate(ex) if e}
            G2 = [{tuple(1 if i == j else 0 for j in range(len(orden))): Fraction(1)}
                  for i in sorted(ceros)]
            G2 += [g for g in G if not any(all(ex[i] > 0 for ex in g) for i in ceros)]
            desc = "; ".join(f"{mx.text(a_expr(g))} = 0" for g in G2)
            trace.regla("sistema.no_aislado", f"conjunto de soluciones: {desc}",
                        why="base de Gröbner reducida: describe el mismo conjunto, y no "
                            "tiene ninguna ecuación en una sola variable")
            raise _no(f"las soluciones no están aisladas (hay una curva o superficie de "
                      f"soluciones): {desc}")
        g = solo_v[0]
        uni = [Fraction(0)] * (_lider(g)[-1] + 1)
        for e, c in g.items():
            uni[e[-1]] = c
        sin_rep = RZ._divmod(uni, RZ._mcd(uni, RZ._deriv(uni)))[0] if len(uni) > 2 else uni
        candidatas[v] = raices_exactas(sin_rep)
        from academic_core.domain.engineering.mathlab import poly as Pm

        from academic_core.domain.engineering.mathlab import multiple as MI

        poli_v = MI._bonito(Pm.to_expr({((v, k),) if k else (): c for k, c in enumerate(sin_rep) if c}))
        trace.regla("sistema.eliminacion",
                    f"eliminando {', '.join(orden[:-1]) or 'nada'}: {mx.text(poli_v)} = 0 → "
                    f"{v} ∈ {{" + ", ".join(mx.text(z.expr) if z.exacto else f"≈ {z.x:.10g}"
                                           for z in candidatas[v]) + "}",
                    why="base de Gröbner lex: su elemento en una sola variable genera la "
                        "proyección de todas las soluciones; raíces reales por Sturm")
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
