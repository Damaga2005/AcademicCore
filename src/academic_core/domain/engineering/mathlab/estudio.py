# SPDX-License-Identifier: MIT
"""ML-2 (T4, T5, T7): the complete study of a function of one variable.

Domain, symmetry, intercepts, asymptotes (vertical by one-sided limits, horizontal
and oblique by limits at ±∞), monotony and extrema from the sign of f′, concavity
and inflection from the sign of f″ — and, for an interval [a, b], the absolute
extrema (Weierstrass, with its hypothesis checked) and the number of solutions of
f = 0 (Bolzano on each interval of strict monotony).

How the partition is exact
--------------------------

Every boundary of the domain is a zero of something: a denominator, the argument
of a logarithm, the radicand of an even root, ``g ∓ 1`` inside ``asin``/``acos``.
All of those zeros come from :mod:`raices` — exact, or isolated by Sturm with an
exact count — so the list of boundary points is COMPLETE, and testing one point
inside each piece decides that whole piece. The same holds for the zeros of f′
and f″. When a factor is transcendental and its zeros are only searched for on a
window, the study says so.

Second paths: each extremum is checked by the sign change of f′ around it, each
asymptote by the limit engine (whose own second path is numeric), and f′, f″ are
the derivative engine's (verified on its own).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import math

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import raices as RZ
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import limite as LM

    return LM._limpio(e)


def _valor(e: mx.Expr, var: str, x: float) -> float | None:
    try:
        v = mx.valor_real(e, {var: x})
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    return None if v is None else float(v)


def _texto_punto(r: RZ.Raiz | None, lado: str = "") -> str:
    if r is None:
        return "−∞" if lado == "izq" else "+∞"
    return mx.text(r.valor) if r.exacta else f"≈{r.x:.10g}"


# ---------------------------------------------------------------------------
# where the function may stop being defined
# ---------------------------------------------------------------------------


def _fronteras(e: mx.Expr) -> list[mx.Expr]:
    """Expressions whose zeros are the only candidates for domain boundaries."""
    salida: list[mx.Expr] = []

    def recorre(n: mx.Expr):
        if isinstance(n, mx.Div):
            salida.append(n.right)
        if isinstance(n, mx.Pow):
            k = mx.exact_value(n.exponent)
            if k is not None and k < 0:
                salida.append(n.base)
            if k is not None and Fraction(k).denominator % 2 == 0:
                salida.append(n.base)
            if k is None:
                salida.append(n.base)
        if isinstance(n, mx.Root) and n.degree % 2 == 0:
            salida.append(n.radicand)
        if isinstance(n, mx.Call):
            a = n.args[0] if n.args else None
            if n.name in ("ln", "log", "sqrt", "raiz", "raiz2", "log10"):
                salida.append(a)
            if n.name in ("asin", "acos"):
                salida.extend([mx.Sub(a, mx.Num(Fraction(1))), mx.Add(a, mx.Num(Fraction(1)))])
            if n.name in ("tan", "sec"):
                salida.append(mx.Call("cos", (a,)))
            if n.name in ("cot", "csc"):
                salida.append(mx.Call("sin", (a,)))
        for hijo in _hijos(n):
            recorre(hijo)

    recorre(e)
    return salida


def _hijos(n: mx.Expr):
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


def _une_raices(listas: list[RZ.Ceros]) -> tuple[list[RZ.Raiz], bool, list[str]]:
    puntos: dict[float, RZ.Raiz] = {}
    completo, avisos = True, []
    for c in listas:
        completo &= c.completo
        avisos += list(c.avisos)
        for r in c.raices:
            clave = round(r.x, 9)
            if clave not in puntos or (r.exacta and not puntos[clave].exacta):
                puntos[clave] = r
    return sorted(puntos.values(), key=lambda r: r.x), completo, list(dict.fromkeys(avisos))


@dataclass(frozen=True)
class Tramo:
    """(a, b) with a, b None for ±∞; ``cerrado_*`` when the endpoint itself belongs."""

    a: RZ.Raiz | None
    b: RZ.Raiz | None
    cerrado_a: bool = False
    cerrado_b: bool = False

    def texto(self) -> str:
        return (("[" if self.cerrado_a else "(") + _texto_punto(self.a, "izq") + ", "
                + _texto_punto(self.b, "der") + ("]" if self.cerrado_b else ")"))

    def medio(self) -> float:
        if self.a is None and self.b is None:
            return 0.0
        if self.a is None:
            return self.b.x - 1
        if self.b is None:
            return self.a.x + 1
        return (self.a.x + self.b.x) / 2


@dataclass(frozen=True)
class Dominio:
    tramos: tuple[Tramo, ...]
    puntos_aislados: tuple[RZ.Raiz, ...]
    completo: bool
    avisos: tuple[str, ...]

    def texto(self) -> str:
        if not self.tramos and not self.puntos_aislados:
            return "∅"
        partes = [t.texto() for t in self.tramos]
        partes += ["{" + _texto_punto(p) + "}" for p in self.puntos_aislados]
        texto = " ∪ ".join(partes)
        return "ℝ" if texto == "(−∞, +∞)" else texto

    def contiene(self, x: float) -> bool:
        for t in self.tramos:
            izq = t.a is None or t.a.x < x or (t.cerrado_a and abs(t.a.x - x) < 1e-12)
            der = t.b is None or x < t.b.x or (t.cerrado_b and abs(t.b.x - x) < 1e-12)
            if izq and der:
                return True
        return any(abs(p.x - x) < 1e-12 for p in self.puntos_aislados)


def dominio(e: mx.Expr, var: str, trace: Trace | None = None) -> Dominio:
    trace = trace if trace is not None else Trace()
    ceros = []
    for g in _fronteras(e):
        if mx.depends(g, var):
            ceros.append(RZ.ceros(g, var))
    puntos, completo, avisos = _une_raices(ceros)
    bordes: list[RZ.Raiz | None] = [None] + puntos + [None]
    tramos: list[Tramo] = []
    aislados: list[RZ.Raiz] = []
    for a, b in zip(bordes, bordes[1:]):
        t = Tramo(a, b)
        if _valor(e, var, t.medio()) is not None:
            tramos.append(t)
    # the boundary points themselves (√(4 − x²) is defined at ±2)
    for p in puntos:
        if _valor(e, var, p.x) is None:
            continue
        izq = next((i for i, t in enumerate(tramos) if t.b is not None and t.b.x == p.x), None)
        der = next((i for i, t in enumerate(tramos) if t.a is not None and t.a.x == p.x), None)
        if izq is not None and der is not None:
            fusion = Tramo(tramos[izq].a, tramos[der].b, tramos[izq].cerrado_a,
                           tramos[der].cerrado_b)
            tramos[izq] = fusion
            del tramos[der]
        elif izq is not None:
            t = tramos[izq]
            tramos[izq] = Tramo(t.a, t.b, t.cerrado_a, True)
        elif der is not None:
            t = tramos[der]
            tramos[der] = Tramo(t.a, t.b, True, t.cerrado_b)
        else:
            aislados.append(p)
    d = Dominio(tuple(tramos), tuple(aislados), completo, tuple(avisos))
    trace.regla("estudio.dominio", f"dominio = {d.texto()}",
                why="se anulan denominadores, argumentos de ln y radicandos pares en un "
                    "número finito de puntos; entre ellos, un punto de prueba decide el tramo")
    return d


# ---------------------------------------------------------------------------
# sign charts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TramoSigno:
    tramo: Tramo
    signo: int


def _ceros_exactos(g: mx.Expr, var: str, rolle: bool = True):
    """Ceros de g: primero el resolvedor general (exacto y completo con
    exponenciales, logaritmos, radicales y Lambert); si no da la lista completa y
    exacta, la búsqueda de siempre."""
    from academic_core.domain.engineering.mathlab import ecuacion_general as EG

    base = RZ.ceros(g, var)
    if base.completo and all(r.exacta for r in base.raices):
        return base
    if not base.completo:
        from academic_core.domain.engineering.mathlab import multiple as MI

        try:
            g2 = MI._limpio(g)
            if mx.text(g2) != mx.text(g):
                otra = RZ.ceros(g2, var)
                if otra.completo:
                    base = RZ.Ceros(tuple(r for r in otra.raices
                                          if _valor(g, var, r.x) is not None), True, otra.avisos)
        except Exception:  # noqa: BLE001
            pass
    if not base.completo:
        por_radical = _ceros_por_radical(g, var)
        if por_radical is not None:
            base = por_radical
    if not base.completo:
        por_comun = _ceros_por_factor_comun(g, var)
        if por_comun is not None:
            base = por_comun
    if not base.completo and rolle:
        por_rolle = _ceros_por_rolle(g, var)
        if por_rolle is not None:
            base = por_rolle
    if base.completo and not all(r.exacta for r in base.raices):
        base = RZ.Ceros(tuple(_exactifica(g, var, r) for r in base.raices), True, base.avisos)
        if all(r.exacta for r in base.raices):
            return base
    try:
        r = EG.resolver(g, var)
    except Exception:  # noqa: BLE001
        return base
    if not r.completo or any(s.exacta is None for s in r.soluciones):
        return base
    from academic_core.domain.engineering.mathlab.numericos import _multiplicidad_num

    def _mult(f, v, x):
        try:
            return _multiplicidad_num(f, v, x)
        except Exception:  # noqa: BLE001
            return 1

    raices = tuple(RZ.Raiz(s.exacta, s.valor, _mult(g, var, s.valor))
                   for s in r.soluciones)
    return RZ.Ceros(raices, True)


def _ceros_por_radical(g: mx.Expr, var: str):
    """x^(p/q) and ⁿ√x only: x = tⁿ (n = lcm of the indices, odd) turns g into a
    rational function of t, whose zeros are complete and exact; x = tⁿ is a
    bijection of ℝ for odd n."""
    indices: set[int] = set()

    def busca(n):
        if isinstance(n, mx.Root) and n.radicand == mx.Sym(var):
            indices.add(n.degree)
        elif isinstance(n, mx.Pow) and n.base == mx.Sym(var):
            k = mx.exact_value(n.exponent)
            if k is None:
                raise ValueError
            indices.add(Fraction(k).denominator)
        elif isinstance(n, mx.Call) and n.name in ("raiz", "sqrt") and n.args[0] == mx.Sym(var):
            indices.add(2 if n.name == "sqrt" else int(mx.exact_value(n.args[1]) or 0))
        elif isinstance(n, (mx.Root, mx.Pow, mx.Call)) or not isinstance(
                n, (mx.Add, mx.Sub, mx.Mul, mx.Div, mx.Neg, mx.Num, mx.Sym, mx.Const)):
            for h in _hijos(n):
                busca(h)
            if isinstance(n, mx.Call) and n.name not in ("raiz", "sqrt"):
                raise ValueError
        else:
            for h in _hijos(n):
                busca(h)

    try:
        busca(g)
    except (ValueError, TypeError):
        return None
    n = 1
    for k in indices:
        if k <= 0:
            return None
        n = n * k // math.gcd(n, k)
    if n == 1 or n % 2 == 0:
        return None
    t = mx.Sym("_t" if var != "_t" else "_u")

    def cambia(e):
        if e == mx.Sym(var):
            return mx.Pow(t, mx.Num(Fraction(n)))
        if isinstance(e, mx.Root) and e.radicand == mx.Sym(var):
            return mx.Pow(t, mx.Num(Fraction(n, e.degree)))
        if isinstance(e, mx.Call) and e.name in ("raiz", "sqrt") and e.args[0] == mx.Sym(var):
            k = 2 if e.name == "sqrt" else int(mx.exact_value(e.args[1]))
            return mx.Pow(t, mx.Num(Fraction(n, k)))
        if isinstance(e, mx.Pow) and e.base == mx.Sym(var):
            return mx.Pow(t, mx.Num(Fraction(mx.exact_value(e.exponent)) * n))
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(e)(cambia(e.left), cambia(e.right))
        if isinstance(e, mx.Neg):
            return mx.Neg(cambia(e.arg))
        if isinstance(e, mx.Pow):
            return mx.Pow(cambia(e.base), cambia(e.exponent))
        if isinstance(e, mx.Root):
            return mx.Root(e.degree, cambia(e.radicand))
        if isinstance(e, mx.Call):
            return mx.Call(e.name, tuple(cambia(a) for a in e.args))
        return e

    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        c = RZ.ceros(MI._racional(cambia(g)), t.name)
    except Exception:  # noqa: BLE001
        return None
    if not c.completo:
        return None
    raices = []
    for r in c.raices:
        x = r.x ** n
        if _valor(g, var, x) is None:
            continue
        if r.exacta:
            raices.append(RZ.Raiz(_limpio(mx.Pow(r.valor, mx.Num(Fraction(n)))), x,
                                  r.multiplicidad, True))
        else:   # t = ∛2 is not exact but x = t³ = 2 may be
            raices.append(_exactifica(g, var, RZ.Raiz(mx.Num(Fraction(x)), x,
                                                      r.multiplicidad, False)))
    return RZ.Ceros(tuple(raices), True)


def _terminos(e: mx.Expr, var: str):
    """g as Σ c·∏ bᵢ^qᵢ with rational qᵢ; bases are kept whole (by text)."""
    if isinstance(e, mx.Add):
        return _terminos(e.left, var) + _terminos(e.right, var)
    if isinstance(e, mx.Sub):
        return _terminos(e.left, var) + [(-c, m) for c, m in _terminos(e.right, var)]
    if isinstance(e, mx.Neg):
        return [(-c, m) for c, m in _terminos(e.arg, var)]
    if isinstance(e, mx.Mul):
        a, b = _terminos(e.left, var), _terminos(e.right, var)
        if len(a) * len(b) > 64:
            raise ValueError
        salida = []
        for ca, ma in a:
            for cb, mb in b:
                m = dict(ma)
                for k, (base, q) in mb.items():
                    m[k] = (base, m[k][1] + q) if k in m else (base, q)
                salida.append((ca * cb, m))
        return salida
    if isinstance(e, mx.Div):
        d = _terminos(e.right, var)
        if len(d) != 1:
            return [(c, m) for c, m in _terminos(mx.Mul(e.left, mx.Pow(e.right, mx.Num(Fraction(-1)))),
                                                    var)] if mx.depends(e.right, var) else _escala(
                _terminos(e.left, var), e.right)
        cd, md = d[0]
        inv = {k: (b, -q) for k, (b, q) in md.items()}
        return [(c / cd, {**m, **{k: (inv[k][0], (m[k][1] if k in m else 0) + inv[k][1])
                                  for k in inv}}) for c, m in _terminos(e.left, var)]
    if not mx.depends(e, var):
        v = mx.exact_value(e)
        if v is None:
            raise ValueError
        return [(Fraction(v), {})]
    if isinstance(e, mx.Pow):
        q = mx.exact_value(e.exponent)
        if q is None:
            raise ValueError
        q = Fraction(q)
        if isinstance(e.base, (mx.Pow, mx.Root)):
            interior = _terminos(e.base, var)
            if len(interior) == 1 and interior[0][0] == 1:
                return [(Fraction(1), {k: (b, r * q) for k, (b, r) in interior[0][1].items()})]
        if q.denominator == 1 and q > 0 and isinstance(e.base, (mx.Add, mx.Sub)):
            pass
        return [(Fraction(1), {mx.text(e.base): (e.base, q)})]
    if isinstance(e, mx.Root):
        return [(Fraction(1), {mx.text(e.radicand): (e.radicand, Fraction(1, e.degree))})]
    if isinstance(e, mx.Call) and e.name in ("sqrt",):
        return [(Fraction(1), {mx.text(e.args[0]): (e.args[0], Fraction(1, 2))})]
    if isinstance(e, mx.Call):
        raise ValueError
    return [(Fraction(1), {mx.text(e): (e, Fraction(1))})]


def _escala(terminos, d):
    v = mx.exact_value(d)
    if v is None or v == 0:
        raise ValueError
    return [(c / Fraction(v), m) for c, m in terminos]


def _ceros_por_factor_comun(g: mx.Expr, var: str):
    """Σ c·∏ bᵢ^qᵢ: sacando ∏ bᵢ^(min qᵢ) queda un polinomio en las bases (exponentes
    enteros ≥ 0). Ceros de g = ceros de ese resto ∪ ceros de las bases con
    exponente común > 0, siempre donde g está definida."""
    try:
        terminos = _terminos(g, var)
    except (ValueError, ZeroDivisionError, TypeError):
        return None
    if len(terminos) < 2:
        return None
    claves = {k for _, m in terminos for k in m}
    bases = {k: next(m[k][0] for _, m in terminos if k in m) for k in claves}
    minimo = {k: min((m[k][1] if k in m else Fraction(0)) for _, m in terminos) for k in claves}
    if all(q == 0 for q in minimo.values()):
        return None
    resto = None
    for c, m in terminos:
        t: mx.Expr = mx.Num(c)
        for k in claves:
            q = (m[k][1] if k in m else Fraction(0)) - minimo[k]
            if q.denominator != 1:
                return None
            if q:
                t = mx.Mul(t, mx.Pow(bases[k], mx.Num(q)))
        resto = t if resto is None else mx.Add(resto, t)
    try:
        partes = [RZ.ceros(_limpio(resto), var)]
        for k, q in minimo.items():
            if q > 0 and mx.depends(bases[k], var):
                partes.append(RZ.ceros(bases[k], var))
    except Exception:  # noqa: BLE001
        return None
    puntos, completo, avisos = _une_raices(partes)
    if not completo:
        return None
    raices = tuple(r for r in puntos
                   if (v := _valor(g, var, r.x)) is not None and abs(v) < 1e-9)
    return RZ.Ceros(raices, True)


def _exactifica(g, var, r):
    """A decimal zero that is really 0, a rational, a + b√r, q·π, ln q or e^q,
    accepted only when substituting it annuls g exactly."""
    if r.exacta:
        return r
    from academic_core.domain.engineering.mathlab import ecuacion_general as EG

    try:
        e = EG.exactifica(g, var, r.x)
    except Exception:  # noqa: BLE001
        e = None
    return r if e is None else RZ.Raiz(e, r.x, r.multiplicidad, True)


def _ceros_por_rolle(g: mx.Expr, var: str):
    """Rolle: between consecutive zeros of g′ (all of them, exact) g is strictly
    monotone, so each piece holds at most one zero, present iff g changes sign
    between its ends (limits at ±∞). Gives the COMPLETE list for g defined and
    differentiable on all of ℝ, e.g. atan(x) − x/2."""
    from academic_core.domain.engineering.mathlab import limite as LM

    if any(mx.depends(h, var) for h in _fronteras(g)):
        return None
    try:
        dg = _limpio(DM_differentiate(g, var))
        cd = RZ.ceros(dg, var)
        if not cd.completo:
            cd = _ceros_exactos(dg, var, rolle=False)
    except Exception:  # noqa: BLE001
        return None
    if not cd.completo or any(_valor(dg, var, r.x) is None for r in cd.raices):
        return None

    def extremo(signo):
        try:
            r = LM.limite(g, var, "oo" if signo > 0 else "-oo")
            if r.valor == "+∞":
                return math.inf
            if r.valor == "−∞":
                return -math.inf
            v = None if r.expr is None else mx.valor_real(r.expr, {})
            return None if v is None else float(v)
        except Exception:  # noqa: BLE001
            return None

    puntos = sorted(cd.raices, key=lambda r: r.x)
    xs = [None] + [r.x for r in puntos] + [None]
    raices: list[RZ.Raiz] = []
    for r in puntos:
        v = _valor(g, var, r.x)
        if v is not None and abs(v) < 1e-13:
            raices.append(RZ.Raiz(r.valor, r.x, 2, r.exacta))
    for a, b in zip(xs, xs[1:]):
        ga = extremo(-1) if a is None else _valor(g, var, a)
        gb = extremo(1) if b is None else _valor(g, var, b)
        if ga is None or gb is None:
            return None
        if ga == 0 or gb == 0 or (ga > 0) == (gb > 0):
            continue
        lo = a if a is not None else (b if b is not None else 0.0) - 1.0
        while a is None and (_valor(g, var, lo) or 0) * gb > 0:
            lo = lo * 2 - 1 if lo < 0 else -1.0
        hi = b if b is not None else (lo + 1.0)
        while b is None and (_valor(g, var, hi) or 0) * (ga) > 0:
            hi = hi * 2 + 1 if hi > 0 else 1.0
        flo = _valor(g, var, lo)
        for _ in range(200):
            m = (lo + hi) / 2
            fm = _valor(g, var, m)
            if fm is None:
                return None
            if fm == 0:
                lo = hi = m
                break
            if (fm > 0) == (flo > 0):
                lo, flo = m, fm
            else:
                hi = m
        x = (lo + hi) / 2
        cerca = next((r for r in base_exactas(g, var) if abs(r.x - x) < 1e-9), None)
        raices.append(cerca or RZ.Raiz(mx.Num(Fraction(x)), x, 1, False))
    return RZ.Ceros(tuple(sorted(raices, key=lambda r: r.x)), True)


def base_exactas(g, var):
    try:
        return [r for r in RZ.ceros(g, var).raices if r.exacta]
    except Exception:  # noqa: BLE001
        return []


def DM_differentiate(g, var):
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return DM.differentiate(g, var)


def _sin_repetir(raices) -> list[RZ.Raiz]:
    vistos: dict[float, RZ.Raiz] = {}
    for r in raices:
        vistos.setdefault(round(r.x, 9), r)
    return list(vistos.values())


def _singulares(g: mx.Expr, var: str, dom: Dominio) -> list[RZ.Raiz]:
    """Points of the domain of f where g (f′ or f″) is not defined: the sign
    chart of g must also be cut there (x^(2/3) at 0)."""
    salida = []
    for h in _fronteras(g):
        if not mx.depends(h, var):
            continue
        try:
            c = RZ.ceros(h, var)
        except Exception:  # noqa: BLE001
            continue
        for r in c.raices:
            if dom.contiene(r.x) and _valor(g, var, r.x) is None:
                salida.append(r)
    return salida


def _tabla(g: mx.Expr, var: str, dom: Dominio) -> tuple[list[TramoSigno], list[RZ.Raiz], bool,
                                                         list[str]]:
    """Sign of g on the pieces of the domain cut at the zeros of g."""
    ceros = _ceros_exactos(g, var)
    corte, completo, avisos = _une_raices([ceros])
    singulares = _singulares(g, var, dom)
    salida = []
    for t in dom.tramos:
        dentro = [r for r in sorted(list(corte) + [q for q in singulares if all(
            abs(q.x - c.x) > 1e-12 for c in corte)], key=lambda r: r.x) if (t.a is None or r.x > t.a.x) and (t.b is None or r.x < t.b.x)]
        bordes = [t.a] + dentro + [t.b]
        for i, (a, b) in enumerate(zip(bordes, bordes[1:])):
            pieza = Tramo(a, b, t.cerrado_a and i == 0, t.cerrado_b and i == len(bordes) - 2)
            v = _valor(g, var, pieza.medio())
            if v is None:
                continue
            salida.append(TramoSigno(pieza, (v > 0) - (v < 0)))
    return salida, corte, completo, avisos


@dataclass(frozen=True)
class Punto:
    x: RZ.Raiz
    y: mx.Expr
    tipo: str

    def texto(self) -> str:
        y = mx.valor_real(self.y, {})
        yt = mx.text(self.y) if self.x.exacta else f"≈{y:.10g}"
        return f"{self.tipo} en ({_texto_punto(self.x)}, {yt})"


def _f_en(e: mx.Expr, var: str, r: RZ.Raiz) -> mx.Expr:
    if r.exacta:
        from academic_core.domain.engineering.mathlab import multiple as MI

        v = _limpio(mx.substitute(e, var, r.valor))
        try:
            w = MI._limpio(v)
            return w if len(mx.text(w)) <= len(mx.text(v)) else v
        except Exception:  # noqa: BLE001
            return v
    return mx.Num(Fraction(_valor(e, var, r.x) or 0))


# ---------------------------------------------------------------------------
# the study
# ---------------------------------------------------------------------------


@dataclass
class Estudio:
    f: mx.Expr
    var: str
    dominio: Dominio
    simetria: str = ""
    cortes: list[str] = field(default_factory=list)
    asintotas: list[str] = field(default_factory=list)
    crece: list[str] = field(default_factory=list)
    decrece: list[str] = field(default_factory=list)
    extremos: list[Punto] = field(default_factory=list)
    concava_arriba: list[str] = field(default_factory=list)
    concava_abajo: list[str] = field(default_factory=list)
    inflexiones: list[Punto] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    completo: bool = True

    def texto(self) -> str:
        lineas = [f"dominio: {self.dominio.texto()}"]
        if self.simetria:
            lineas.append(f"simetría: {self.simetria}")
        lineas.append("cortes: " + ("; ".join(self.cortes) or "ninguno"))
        lineas.append("asíntotas: " + ("; ".join(self.asintotas) or "ninguna"))
        lineas.append("crece en: " + (" ∪ ".join(self.crece) or "—"))
        lineas.append("decrece en: " + (" ∪ ".join(self.decrece) or "—"))
        lineas.append("extremos relativos: " + ("; ".join(p.texto() for p in self.extremos)
                                                or "ninguno"))
        lineas.append("cóncava hacia arriba (∪) en: " + (" ∪ ".join(self.concava_arriba) or "—"))
        lineas.append("cóncava hacia abajo (∩) en: " + (" ∪ ".join(self.concava_abajo) or "—"))
        lineas.append("puntos de inflexión: " + ("; ".join(p.texto() for p in self.inflexiones)
                                                 or "ninguno"))
        return "\n".join(lineas)


def _simetria(e: mx.Expr, var: str, dom: Dominio) -> str:
    """Compared on points of the domain whose opposite is also in it — the symbolic
    equivalence check samples on the whole line, and √(4 − x²) is not defined there."""
    from academic_core.domain.engineering.mathlab import verify as V

    xs = [x for x in V.sample_values(count=24) + [0.37, 1.29, 2.71, 0.05]
          if dom.contiene(x) and dom.contiene(-x) and abs(x) > 1e-9]
    pares = [(_valor(e, var, x), _valor(e, var, -x)) for x in xs]
    pares = [(a, b) for a, b in pares if a is not None and b is not None]
    if len(pares) < 4:
        return "ni par ni impar (el dominio no es simétrico)" if not xs else ""
    tol = lambda a, b: abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))   # noqa: E731
    if all(tol(a, b) for a, b in pares):
        return "par: f(−x) = f(x), simétrica respecto del eje Y"
    if all(tol(a, -b) for a, b in pares):
        return "impar: f(−x) = −f(x), simétrica respecto del origen"
    return "ni par ni impar"


def estudiar(e: mx.Expr, var: str = "x", trace: Trace | None = None) -> Estudio:
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    dom = dominio(e, var, trace)
    est = Estudio(e, var, dom, avisos=list(dom.avisos), completo=dom.completo)
    est.simetria = _simetria(e, var, dom)
    # intercepts
    if dom.contiene(0.0):
        est.cortes.append(f"eje Y en (0, {mx.text(_limpio(mx.substitute(e, var, mx.Num(Fraction(0)))))})")
    ceros = _ceros_exactos(e, var)
    for r in ceros.raices:
        if dom.contiene(r.x):
            est.cortes.append(f"eje X en ({_texto_punto(r)}, 0)")
    est.completo &= ceros.completo
    est.avisos += list(ceros.avisos)
    # vertical asymptotes: at the finite ends of the domain pieces
    vistos = set()
    for t in dom.tramos:
        for punto, lado in ((t.a, "+"), (t.b, "-")):
            if punto is None or round(punto.x, 9) in vistos and lado == "-":
                continue
            p = mx.text(punto.valor) if punto.exacta else repr(punto.x)
            try:
                lim = LM.limite(e, var, p, lado)
            except Exception:  # noqa: BLE001
                continue
            if lim.valor in ("+∞", "−∞"):
                vistos.add(round(punto.x, 9))
                est.asintotas.append(f"vertical x = {_texto_punto(punto)} "
                                     f"(por la {'derecha' if lado == '+' else 'izquierda'} "
                                     f"→ {lim.valor})")
    # horizontal / oblique
    for inf, nombre in (("oo", "+∞"), ("-oo", "−∞")):
        extremo = dom.tramos[-1].b if inf == "oo" else dom.tramos[0].a if dom.tramos else 0
        if not dom.tramos or extremo is not None:
            continue
        try:
            L = LM.limite(e, var, inf)
        except Exception:  # noqa: BLE001
            est.avisos.append(f"no sé el límite en {nombre}")
            continue
        if L.expr is not None:
            est.asintotas.append(f"horizontal y = {L.valor} en {nombre}")
        elif L.valor in ("+∞", "−∞"):
            try:
                m = LM.limite(mx.Div(e, mx.Sym(var)), var, inf)
                if m.expr is not None and mx.exact_value(m.expr) != 0:
                    n = LM.limite(mx.Sub(e, mx.Mul(m.expr, mx.Sym(var))), var, inf)
                    if n.expr is not None:
                        recta = _limpio(mx.Add(mx.Mul(m.expr, mx.Sym(var)), n.expr))
                        est.asintotas.append(f"oblicua y = {mx.text(recta)} en {nombre}")
            except Exception:  # noqa: BLE001
                est.avisos.append(f"no sé si hay asíntota oblicua en {nombre}")
    trace.regla("estudio.asintotas", "; ".join(est.asintotas) or "ninguna",
                why="vertical: límite lateral infinito en un borde del dominio; horizontal "
                    "u oblicua: m = lím f/x, n = lím (f − m·x) en ±∞")
    # monotony
    d1 = _limpio(DM.differentiate(e, var))
    trace.regla("estudio.derivada", f"f′({var}) = {mx.text(d1)}")
    tabla, criticos, comp1, av1 = _tabla(d1, var, dom)
    est.completo &= comp1
    est.avisos += av1
    for ts in tabla:
        (est.crece if ts.signo > 0 else est.decrece if ts.signo < 0 else []).append(
            ts.tramo.texto())
    for r in _sin_repetir(list(criticos) + _singulares(d1, var, dom)):
        if not dom.contiene(r.x):
            continue
        antes = next((ts.signo for ts in tabla if ts.tramo.b is not None
                      and abs(ts.tramo.b.x - r.x) < 1e-12), None)
        despues = next((ts.signo for ts in tabla if ts.tramo.a is not None
                        and abs(ts.tramo.a.x - r.x) < 1e-12), None)
        if antes is None or despues is None or antes == despues:
            continue
        tipo = "máximo relativo" if antes > despues else "mínimo relativo"
        est.extremos.append(Punto(r, _f_en(e, var, r), tipo))
    trace.regla("estudio.monotonia", "crece en " + (" ∪ ".join(est.crece) or "—")
                + "; decrece en " + (" ∪ ".join(est.decrece) or "—"),
                why="signo de f′ en cada tramo entre sus ceros y los bordes del dominio")
    # concavity
    d2 = _limpio(DM.differentiate(d1, var))
    trace.regla("estudio.segunda", f"f″({var}) = {mx.text(d2)}")
    tabla2, puntos2, comp2, av2 = _tabla(d2, var, dom)
    est.completo &= comp2
    est.avisos += av2
    for ts in tabla2:
        (est.concava_arriba if ts.signo > 0 else est.concava_abajo if ts.signo < 0 else []).append(
            ts.tramo.texto())
    for r in _sin_repetir(list(puntos2) + _singulares(d2, var, dom)):
        if not dom.contiene(r.x):
            continue
        antes = next((ts.signo for ts in tabla2 if ts.tramo.b is not None
                      and abs(ts.tramo.b.x - r.x) < 1e-12), None)
        despues = next((ts.signo for ts in tabla2 if ts.tramo.a is not None
                        and abs(ts.tramo.a.x - r.x) < 1e-12), None)
        if antes is not None and despues is not None and antes != despues and antes and despues:
            est.inflexiones.append(Punto(r, _f_en(e, var, r), "inflexión"))
    est.avisos = list(dict.fromkeys(est.avisos))
    return est


# ---------------------------------------------------------------------------
# on a closed interval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Absolutos:
    maximo: tuple[mx.Expr, list[str]]
    minimo: tuple[mx.Expr, list[str]]
    candidatos: list[tuple[str, mx.Expr]]

    def texto(self) -> str:
        return (f"máximo absoluto {mx.text(self.maximo[0])} en x = {', '.join(self.maximo[1])}; "
                f"mínimo absoluto {mx.text(self.minimo[0])} en x = {', '.join(self.minimo[1])}")


def extremos_absolutos(e: mx.Expr, var: str, a: mx.Expr, b: mx.Expr,
                       trace: Trace | None = None) -> Absolutos:
    """Weierstrass on [a, b]: hypothesis checked (continuity on the closed interval),
    candidates = ends + critical points + points where f′ does not exist."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    trace = trace if trace is not None else Trace()
    xa, xb = float(mx.valor_real(a, {})), float(mx.valor_real(b, {}))
    if xa >= xb:
        raise _error("BAD_INPUT", "el intervalo tiene que cumplir a < b")
    dom = dominio(e, var, trace)
    tramo = next((t for t in dom.tramos
                  if (t.a is None or t.a.x < xa or (t.cerrado_a and t.a.x <= xa))
                  and (t.b is None or t.b.x > xb or (t.cerrado_b and t.b.x >= xb))), None)
    if tramo is None:
        raise _error("HYPOTHESIS", f"f no es continua en [{mx.text(a)}, {mx.text(b)}]: el "
                                   "intervalo sale del dominio o lo cruza un borde, así que "
                                   "Weierstrass no garantiza extremos absolutos")
    trace.hipotesis("weierstrass", f"f continua en el cerrado [{mx.text(a)}, {mx.text(b)}]",
                    "se cumple: el intervalo está dentro de un tramo del dominio")
    d1 = _limpio(DM.differentiate(e, var))
    candidatos: list[tuple[str, mx.Expr, float]] = []
    for x in (a, b):
        candidatos.append((mx.text(x), _limpio(mx.substitute(e, var, x)),
                           float(mx.valor_real(x, {}))))
    crit = RZ.ceros(d1, var, (xa, xb))
    for r in crit.raices:
        if xa < r.x < xb:
            candidatos.append((_texto_punto(r), _f_en(e, var, r), r.x))
    for g in _fronteras(d1):
        if mx.depends(g, var):
            for r in RZ.ceros(g, var, (xa, xb)).raices:
                if xa < r.x < xb and _valor(e, var, r.x) is not None:
                    candidatos.append((_texto_punto(r) + " (f′ no existe)", _f_en(e, var, r), r.x))
    valores = [(t, y, float(mx.valor_real(y, {}))) for t, y, _ in candidatos]
    for t, y, v in valores:
        trace.regla("weierstrass.candidato", f"f({t}) = {mx.text(y)} ≈ {v:.10g}")
    vmax = max(v for _, _, v in valores)
    vmin = min(v for _, _, v in valores)
    tol = 1e-12 * max(1.0, abs(vmax), abs(vmin))
    maximo = next(y for _, y, v in valores if abs(v - vmax) <= tol)
    minimo = next(y for _, y, v in valores if abs(v - vmin) <= tol)
    return Absolutos((maximo, [t for t, _, v in valores if abs(v - vmax) <= tol]),
                     (minimo, [t for t, _, v in valores if abs(v - vmin) <= tol]),
                     [(t, y) for t, y, _ in valores])


@dataclass(frozen=True)
class Soluciones:
    numero: int
    raices: tuple[RZ.Raiz, ...]
    justificacion: tuple[str, ...]
    completo: bool

    def texto(self) -> str:
        return (f"{self.numero} " + ("solución" if self.numero == 1 else "soluciones") + ": "
                + (", ".join(_texto_punto(r) for r in self.raices) or "—"))


def numero_de_soluciones(e: mx.Expr, var: str, a: mx.Expr | None = None,
                         b: mx.Expr | None = None, trace: Trace | None = None) -> Soluciones:
    """How many solutions f = 0 has (on [a, b] or on the domain), justified as an exam
    asks: Bolzano for existence on each interval of strict monotony, monotony for
    uniqueness."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    trace = trace if trace is not None else Trace()
    xa = float(mx.valor_real(a, {})) if a is not None else -RZ.VENTANA
    xb = float(mx.valor_real(b, {})) if b is not None else RZ.VENTANA
    dom = dominio(e, var, trace)
    d1 = _limpio(DM.differentiate(e, var))
    tabla, _, completo, _ = _tabla(d1, var, dom)
    raices = [r for r in RZ.ceros(e, var, (xa, xb)).raices
              if xa <= r.x <= xb and dom.contiene(r.x)]
    justificacion = []
    for ts in tabla:
        t = ts.tramo
        lo = max(xa, t.a.x if t.a else xa)
        hi = min(xb, t.b.x if t.b else xb)
        if lo >= hi or ts.signo == 0:
            continue
        dentro = [r for r in raices if lo <= r.x <= hi]
        mono = "estrictamente creciente" if ts.signo > 0 else "estrictamente decreciente"
        if dentro:
            justificacion.append(
                f"en {t.texto()} f es {mono} (f′ {'>' if ts.signo > 0 else '<'} 0): a lo sumo un "
                f"cero; hay cambio de signo, y por Bolzano exactamente uno, en "
                f"{_texto_punto(dentro[0])}")
        else:
            justificacion.append(f"en {t.texto()} f es {mono} y no cambia de signo: ningún cero")
    for linea in justificacion:
        trace.regla("bolzano.tramo", linea, why="Bolzano da existencia; la monotonía estricta, "
                                                "unicidad")
    return Soluciones(len(raices), tuple(raices), tuple(justificacion), completo)



# ---------------------------------------------------------------------------
# inequalities by sign chart (T1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conjunto:
    tramos: tuple[Tramo, ...]
    puntos: tuple[RZ.Raiz, ...]
    completo: bool

    def texto(self) -> str:
        partes = [t.texto() for t in self.tramos] + ["{" + _texto_punto(p) + "}" for p in self.puntos]
        if not partes:
            return "∅"
        t = " ∪ ".join(partes)
        return "ℝ" if t == "(−∞, +∞)" else t

    def contiene(self, x: float) -> bool:
        return Dominio(self.tramos, self.puntos, True, ()).contiene(x)


def desigualdad(g: mx.Expr, var: str, operador: str, trace: Trace | None = None) -> Conjunto:
    """{x : g(x) op 0} with op in <, ≤, >, ≥: domain pieces cut at the zeros of g,
    one test point per piece (every boundary and zero is known), the zeros added
    for ≤ and ≥."""
    trace = trace if trace is not None else Trace()
    dom = dominio(g, var, trace)
    tabla, ceros, completo, _ = _tabla(g, var, dom)
    quiere = {"<": -1, "<=": -1, "≤": -1, ">": 1, ">=": 1, "≥": 1}[operador]
    con_igual = operador in ("<=", ">=", "≤", "≥")
    tramos: list[Tramo] = []
    for ts in tabla:
        if ts.signo != quiere:
            continue
        t = ts.tramo
        ca = t.cerrado_a or (con_igual and t.a is not None and abs(_valor(g, var, t.a.x)) < 1e-12
                             if t.a is not None and _valor(g, var, t.a.x) is not None else False)
        cb = t.cerrado_b or (con_igual and t.b is not None and abs(_valor(g, var, t.b.x)) < 1e-12
                             if t.b is not None and _valor(g, var, t.b.x) is not None else False)
        # a closed end must still satisfy the inequality
        if ca and t.a is not None:
            v = _valor(g, var, t.a.x)
            ca = v is not None and (abs(v) < 1e-12 and con_igual or v * quiere > 0)
        if cb and t.b is not None:
            v = _valor(g, var, t.b.x)
            cb = v is not None and (abs(v) < 1e-12 and con_igual or v * quiere > 0)
        nuevo = Tramo(t.a, t.b, ca, cb)
        if tramos and tramos[-1].b is not None and t.a is not None and \
                abs(tramos[-1].b.x - t.a.x) < 1e-12 and (tramos[-1].cerrado_b or ca):
            prev = tramos.pop()
            nuevo = Tramo(prev.a, t.b, prev.cerrado_a, cb)
        tramos.append(nuevo)
    puntos = []
    if con_igual:
        for r in ceros:
            if not dom.contiene(r.x):
                continue
            dentro = any((t.a is None or t.a.x < r.x or (t.cerrado_a and abs(t.a.x - r.x) < 1e-12))
                         and (t.b is None or r.x < t.b.x or (t.cerrado_b and abs(t.b.x - r.x) < 1e-12))
                         for t in tramos)
            if dentro:
                continue
            for i, t in enumerate(tramos):     # a zero at an open end closes that end
                if t.a is not None and abs(t.a.x - r.x) < 1e-12:
                    tramos[i] = t = Tramo(t.a, t.b, True, t.cerrado_b)
                    break
                if t.b is not None and abs(t.b.x - r.x) < 1e-12:
                    tramos[i] = Tramo(t.a, t.b, t.cerrado_a, True)
                    break
            else:
                puntos.append(r)
    trace.regla("inecuacion.signos", "signo de g en cada tramo entre ceros y bordes del dominio",
                why="g continua en cada tramo y sin ceros dentro: no cambia de signo")
    return Conjunto(tuple(tramos), tuple(puntos), completo)
