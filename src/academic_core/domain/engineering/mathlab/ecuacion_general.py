# SPDX-License-Identifier: MIT
"""Ecuaciones reales en una incógnita que no son trigonométricas (o no solo).

El resolvedor de T-12 (:mod:`ecuaciones`) trabaja por familias trigonométricas;
este módulo cubre el resto con el mismo criterio de «todas las soluciones, cada
una comprobada»:

1. polinómicas, racionales, con valor absoluto y con raíces: :func:`raices.ceros`
   (Sturm, exacto y completo cuando el caso lo permite);
2. exponenciales: si es un polinomio en u = b^(g·x) se resuelve en u > 0 y
   x = log_b(u)/g (exacto y completo);
3. logarítmicas: polinomio en u = ln(x), o suma de logaritmos de la misma base
   igual a una constante ⇒ producto de argumentos = b^c (dominio comprobado);
4. el resto: todas las raíces reales en una ventana (barrido + Brent, raíces
   dobles incluidas) y, para cada una, una forma exacta (racional, √, π, ln)
   aceptada solo si al sustituirla la ecuación se anula exactamente.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

VENTANA = 50.0


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


@dataclass(frozen=True)
class Solucion:
    exacta: mx.Expr | None
    valor: float

    def texto(self) -> str:
        return mx.text(self.exacta) if self.exacta is not None else f"≈ {self.valor:.12g}"


@dataclass(frozen=True)
class Resultado:
    soluciones: tuple[Solucion, ...]
    completo: bool
    metodo: str

    def texto(self, var: str = "x") -> str:
        if not self.soluciones:
            base = "sin soluciones reales"
        else:
            base = ", ".join(f"{var} = {s.texto()}" for s in self.soluciones)
        if not self.completo:
            base += f" (todas las de [−{VENTANA:g}, {VENTANA:g}])"
        return base


def _limpio(e):
    from academic_core.domain.engineering.mathlab import multiple as MI

    return MI._limpio(e)


def _es_cero_exacto(e: mx.Expr) -> bool:
    from academic_core.domain.engineering.mathlab import verify as V

    s = _limpio(e)
    if mx.exact_value(s) == 0:
        return True
    try:
        iguales, _, _ = V.check_equivalence(s, mx.Num(Fraction(0)))
        return bool(iguales)
    except Exception:  # noqa: BLE001
        return False


def _dominio_ok(f: mx.Expr, var: str, x: float) -> bool:
    try:
        v = mx.valor_real(f, {var: x})
    except (ValueError, ZeroDivisionError, OverflowError):
        return False
    return v is not None and abs(v) < 1e-7 * max(1.0, _escala(f, var, x))


def _escala(f, var, x) -> float:
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(f)
        tot = 0.0
        for m, c in p.items():
            t = abs(float(c))
            for v, k in m:
                val = x if v == var else 1.0
                if P.is_atom(v):
                    w = mx.valor_real(mx.parse(P.atom_text(v)), {var: x})
                    val = abs(w) if w is not None else 1.0
                t *= abs(val) ** k
            tot += t
        return tot
    except Exception:  # noqa: BLE001
        return 1.0


# ---------------------------------------------------------------------------
# exponenciales: polinomio en u = b^(g·x)
# ---------------------------------------------------------------------------


def _exponenciales(f: mx.Expr, var: str):
    """Lista de (base, coeficiente de x) de cada b^(c·x) o e^(c·x) que aparece."""
    out = []

    def visita(n):
        if isinstance(n, mx.Pow) and var in mx.variables(n.exponent) and \
                var not in mx.variables(n.base):
            out.append((n.base, n.exponent))
        if isinstance(n, mx.Call) and n.name == "exp" and var in mx.variables(n.args[0]):
            out.append((mx.Const("e"), n.args[0]))
        for h in ("left", "right", "arg", "base", "exponent", "radicand"):
            c = getattr(n, h, None)
            if isinstance(c, mx.Expr):
                visita(c)
        for a in getattr(n, "args", ()) or ():
            if isinstance(a, mx.Expr):
                visita(a)
    visita(f)
    return out


def _por_exponencial(f: mx.Expr, var: str, trace: Trace) -> Resultado | None:
    from academic_core.domain.engineering.mathlab import raices as RZ

    exps = _exponenciales(f, var)
    if not exps:
        return None
    # misma base (por valor) y exponentes c·x + d con c racional
    b0 = float(mx.valor_real(exps[0][0], {}))
    if b0 <= 0 or b0 == 1:
        return None
    coefs = []
    for b, ex in exps:
        bv = float(mx.valor_real(b, {}))
        pe = RZ._polinomio_de(ex, var)
        if pe is None or len(RZ._recorta(pe)) > 2:
            return None
        pe = RZ._recorta(pe) + [Fraction(0)] * 2
        # b^(c x + d) = b^d·(b0^(c·ln b/ln b0))^x: se exige b = b0^q con q racional
        q = Fraction(math.log(bv) / math.log(b0)).limit_denominator(64)
        if abs(float(q) * math.log(b0) - math.log(bv)) > 1e-12:
            return None
        coefs.append(pe[1] * q)
    g = Fraction(0)
    for c in coefs:
        g = Fraction(math.gcd(g.numerator * c.denominator, c.numerator * g.denominator),
                     g.denominator * c.denominator) if g else abs(c)
    if g == 0:
        return None
    U = "u__"
    base = exps[0][0]
    # sustituye x = log_{b0}(u)/g: b^(c x + d) = b^d · u^(c·q/g)
    sust = mx.Div(mx.Call("ln", (mx.Sym(U),)), mx.Mul(mx.Num(g), mx.Call("ln", (base,))))
    h = _reescribe_exp(f, var, base, g, U)
    if h is None or var in mx.variables(h):
        return None
    coefs_u = RZ._polinomio_de(_limpio(h), U)
    if coefs_u is None:
        try:
            from academic_core.domain.engineering.mathlab import poly as P

            from academic_core.domain.engineering.mathlab import multiple as MI

            razon = P.as_ratio(MI._racional(_limpio(h)), U)
            coefs_u = RZ._polinomio_de(P.to_expr(razon.numerator), U) if razon else None
        except Exception:  # noqa: BLE001
            coefs_u = None
    if coefs_u is None or len(RZ._recorta(coefs_u)) < 2:
        return None
    raices = RZ.raices_polinomio(coefs_u).raices
    trace.regla("ecuacion.cambio_exp", f"u = {mx.text(base)}^({g}·{var}): "
                f"{mx.text(_limpio(h))} = 0 → u ∈ {{" +
                ", ".join(r.texto() for r in raices) + "}",
                why="la ecuación es un polinomio en una sola exponencial")
    sols = []
    for r in raices:
        if r.x <= 0:
            trace.regla("ecuacion.descarta", f"u = {r.texto()} ≤ 0: una exponencial es > 0")
            continue
        x = math.log(r.x) / (float(g) * math.log(b0))
        ex = _limpio(mx.substitute(sust, U, r.valor)) if r.exacta else None
        sols.append(Solucion(ex, x))
    return Resultado(tuple(sorted(sols, key=lambda s: s.valor)), True,
                     "cambio u = exponencial")


def _reescribe_exp(f, var, base, g, U):
    """f con cada exponencial escrita como potencia de u = base^(g·x)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    b0 = float(mx.valor_real(base, {}))

    def rec(n):
        if isinstance(n, mx.Pow) and var in mx.variables(n.exponent) and \
                var not in mx.variables(n.base):
            b, ex = n.base, n.exponent
        elif isinstance(n, mx.Call) and n.name == "exp" and var in mx.variables(n.args[0]):
            b, ex = mx.Const("e"), n.args[0]
        else:
            if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
                return type(n)(rec(n.left), rec(n.right))
            if isinstance(n, mx.Neg):
                return mx.Neg(rec(n.arg))
            if isinstance(n, mx.Pow):
                return mx.Pow(rec(n.base), n.exponent)
            return n
        bv = float(mx.valor_real(b, {}))
        q = Fraction(math.log(bv) / math.log(b0)).limit_denominator(64)
        pe = RZ._recorta(RZ._polinomio_de(ex, var)) + [Fraction(0)] * 2
        k = pe[1] * q / g
        cte = mx.Pow(b, mx.Num(pe[0])) if pe[0] != 0 else None
        pot = mx.Pow(mx.Sym(U), mx.Num(k))
        return pot if cte is None else mx.Mul(cte, pot)
    return rec(f)


# ---------------------------------------------------------------------------
# logaritmos
# ---------------------------------------------------------------------------


def _por_logaritmo(f: mx.Expr, var: str, trace: Trace) -> Resultado | None:
    """Σ kᵢ·log_b(pᵢ(x)) = c con kᵢ enteros: Πpᵢ^kᵢ = b^c, y polinomios en ln(x)."""
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    # polinomio en ln(x)
    U = "u__"
    g = mx.substitute(f, var, mx.Call("exp", (mx.Sym(U),)))
    g = _limpio(g)
    if var not in mx.variables(g) and U in mx.variables(g):
        coefs = RZ._polinomio_de(g, U)
        if coefs is not None and len(RZ._recorta(coefs)) >= 2:
            raices = RZ.raices_polinomio(coefs).raices
            trace.regla("ecuacion.cambio_ln", f"u = ln({var}): {mx.text(g)} = 0 → u ∈ {{" +
                        ", ".join(r.texto() for r in raices) + "}",
                        why="polinomio en ln x; x = e^u > 0")
            sols = [Solucion(_limpio(mx.Call("exp", (r.valor,))) if r.exacta else None,
                             math.exp(r.x)) for r in raices]
            return Resultado(tuple(sorted(sols, key=lambda s: s.valor)), True,
                             "cambio u = ln x")
    # suma de logaritmos: misma base b en todos ⇒ se multiplica por ln b
    f = _misma_base(f)
    try:
        p = P.as_poly(_a_ln(f))
    except Exception:  # noqa: BLE001
        return None
    logs, resto = {}, Fraction(0)
    for m, c in p.items():
        if not m:
            resto += c
            continue
        if len(m) == 1 and m[0][1] == 1 and P.is_atom(m[0][0]) and \
                P.es_llamada(m[0][0], "ln"):
            logs[m[0][0]] = c          # también ln(constante): entra en el producto
        else:
            return None
    if not logs:
        return None
    # todos con el mismo factor 1/ln(b): c·ln(p) → k = c/c0 entero
    c0 = min(logs.values(), key=abs)
    ks = {a: v / c0 for a, v in logs.items()}
    if any(k.denominator != 1 for k in ks.values()):
        return None
    # Σ k·ln(p) = −resto/c0 ⇒ Π p^k = e^(−resto/c0)
    lado = -resto / c0
    args = {a: mx.parse(P.atom_text(a)[3:-1]) for a in ks}
    num, den = [], []
    for a, k in ks.items():
        (num if k > 0 else den).append(mx.Pow(args[a], mx.Num(abs(k))))
    prod_num = num[0] if num else mx.Num(Fraction(1))
    for t in num[1:]:
        prod_num = mx.Mul(prod_num, t)
    prod_den = den[0] if den else mx.Num(Fraction(1))
    for t in den[1:]:
        prod_den = mx.Mul(prod_den, t)
    eq = mx.Sub(prod_num, mx.Mul(mx.Call("exp", (mx.Num(lado),)), prod_den))
    eq = _limpio(eq)
    trace.regla("ecuacion.logs", f"Σ logaritmos = cte ⇒ {mx.text(eq)} = 0",
                why="ln a + ln b = ln(ab); se exponencia y luego se exige dominio")
    try:
        r = RZ.ceros(eq, var)
    except Exception:  # noqa: BLE001
        return None
    sols = []
    for z in r.raices:
        if all(mx.valor_real(arg, {var: z.x}) is not None and
               float(mx.valor_real(arg, {var: z.x})) > 0 for arg in args.values()):
            sols.append(Solucion(z.valor if z.exacta else None, z.x))
        else:
            trace.regla("ecuacion.descarta", f"{var} = {z.texto()} fuera del dominio de los "
                        "logaritmos (argumento ≤ 0)")
    return Resultado(tuple(sols), r.completo, "propiedades de los logaritmos")


def _terminos(e: mx.Expr, signo: int = 1):
    if isinstance(e, mx.Add):
        yield from _terminos(e.left, signo)
        yield from _terminos(e.right, signo)
    elif isinstance(e, mx.Sub):
        yield from _terminos(e.left, signo)
        yield from _terminos(e.right, -signo)
    elif isinstance(e, mx.Neg):
        yield from _terminos(e.arg, -signo)
    else:
        yield signo, e


def _misma_base(f: mx.Expr) -> mx.Expr:
    """Si todos los logaritmos son log(b, ·) con la misma base constante b, la
    ecuación se multiplica por ln b: log_b(X) → ln X y cada término sin
    logaritmo t → t·ln b. Mismo conjunto de soluciones (ln b ≠ 0)."""
    bases = set()

    def busca(n):
        if isinstance(n, mx.Call) and n.name in ("log", "log10"):
            b = n.args[0] if n.name == "log" else mx.Num(Fraction(10))
            if mx.variables(b):
                bases.add("var")
            bases.add(mx.text(b))
        for h in ("left", "right", "arg", "base", "exponent", "radicand"):
            c = getattr(n, h, None)
            if isinstance(c, mx.Expr):
                busca(c)
        for a in getattr(n, "args", ()) or ():
            if isinstance(a, mx.Expr):
                busca(a)
    busca(f)
    if len(bases) != 1 or "var" in bases:
        return f
    b = mx.parse(next(iter(bases)))

    def quita(n):
        if isinstance(n, mx.Call) and n.name == "log":
            return mx.Call("ln", (quita(n.args[1]),))
        if isinstance(n, mx.Call) and n.name == "log10":
            return mx.Call("ln", (quita(n.args[0]),))
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(n)(quita(n.left), quita(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(quita(n.arg))
        return n
    lnb = mx.Call("ln", (b,))
    out = None
    for sg, t in _terminos(f):
        tiene = any(isinstance(x, mx.Call) and x.name in ("log", "log10") for x in _nodos(t))
        nuevo = quita(t) if tiene else mx.Mul(t, lnb)
        nuevo = nuevo if sg > 0 else mx.Neg(nuevo)
        out = nuevo if out is None else mx.Add(out, nuevo)
    return out


def _nodos(e):
    yield e
    for h in ("left", "right", "arg", "base", "exponent", "radicand"):
        c = getattr(e, h, None)
        if isinstance(c, mx.Expr):
            yield from _nodos(c)
    for a in getattr(e, "args", ()) or ():
        if isinstance(a, mx.Expr):
            yield from _nodos(a)


def _a_ln(e: mx.Expr) -> mx.Expr:
    if isinstance(e, mx.Call):
        args = tuple(_a_ln(a) for a in e.args)
        if e.name == "log" and len(args) == 2:
            return mx.Div(mx.Call("ln", (args[1],)), mx.Call("ln", (args[0],)))
        if e.name == "log10":
            return mx.Div(mx.Call("ln", args), mx.Call("ln", (mx.Num(Fraction(10)),)))
        return mx.Call(e.name, args)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_a_ln(e.left), _a_ln(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_ln(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_a_ln(e.base), _a_ln(e.exponent))
    return e


# ---------------------------------------------------------------------------
# radicales: s² = g y eliminación (completo)
# ---------------------------------------------------------------------------


def _por_radicales(f: mx.Expr, var: str, trace: Trace) -> Resultado | None:
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ
    from academic_core.domain.engineering.mathlab import sistemas as S

    raices_ = {}

    def rec(n):
        if isinstance(n, mx.Root) and var in mx.variables(n.radicand):
            t = mx.text(n)
            if t not in raices_:
                raices_[t] = (f"s{len(raices_)}__", n.degree, rec(n.radicand))
            return mx.Sym(raices_[t][0])
        if isinstance(n, mx.Pow) and var in mx.variables(n.base):
            k = mx.exact_value(n.exponent)
            if k is not None and Fraction(k).denominator in (2, 3) and not mx.variables(n.exponent):
                k = Fraction(k)
                r = mx.Root(k.denominator, n.base)
                return mx.Pow(rec(r), mx.Num(Fraction(k.numerator)))
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(n)(rec(n.left), rec(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(rec(n.arg))
        if isinstance(n, mx.Pow):
            return mx.Pow(rec(n.base), n.exponent)
        if isinstance(n, mx.Call) and var in mx.variables(n):
            raise _no("función trascendente")
        return n
    try:
        g = rec(f)
    except UnsupportedError:
        return None
    if not raices_:
        return None
    nombres = [v[0] for v in raices_.values()]
    try:
        razon = P.as_ratio(g, var)
        base = P.to_expr(razon.numerator) if razon is not None else g
        polis = [S.a_polinomio(base, nombres + [var], Trace())]
        for nom, grado, rad in raices_.values():
            rr = P.as_ratio(rad, var)
            if rr is None:
                return None
            # s^grado·den − num = 0
            polis.append(P.add(P.mul({((nom, grado),): Fraction(1)}, rr.denominator),
                               rr.numerator, -1))
        orden = nombres + [var]
        G = S.grobner([S._a_exp(p, orden) for p in polis if p])
    except (UnsupportedError, ValidationError, ArithmeticError):
        return None
    solo = [q for q in G if all(e == 0 for e in S._lider(q)[:-1])]
    if not solo:
        return None
    uni = [Fraction(0)] * (S._lider(solo[0])[-1] + 1)
    for e, c in solo[0].items():
        uni[e[-1]] = c
    cand = RZ.raices_polinomio(uni).raices
    trace.regla("ecuacion.radicales", "se eliminan las raíces (s² = g, s ≥ 0): las soluciones "
                f"están entre las raíces de un polinomio de grado {len(uni) - 1}: " +
                ", ".join(r.texto() for r in cand),
                why="elevar al cuadrado no pierde soluciones; las que añade se descartan "
                    "sustituyendo en la ecuación original")
    sols = []
    for r in cand:
        if _dominio_ok(f, var, r.x):
            ex = _limpio(r.valor) if r.exacta else exactifica(f, var, r.x)
            sols.append(Solucion(ex, r.x))
        else:
            trace.regla("ecuacion.descarta", f"{var} = {r.texto()} no cumple la ecuación "
                        "original (solución añadida al elevar)")
    return Resultado(tuple(sols), True, "eliminación de radicales")


# ---------------------------------------------------------------------------
# Lambert: a·x·e^(bx) + c = 0 y x^x = c
# ---------------------------------------------------------------------------


def _por_lambert(f: mx.Expr, var: str, trace: Trace) -> Resultado | None:
    from academic_core.domain.engineering.mathlab import numericos as NU
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    # x^x − c
    if isinstance(f, mx.Sub) and isinstance(f.left, mx.Pow) and f.left.base == mx.Sym(var) \
            and f.left.exponent == mx.Sym(var) and not mx.variables(f.right):
        c = float(mx.valor_real(f.right, {}))
        if c <= 0:
            return Resultado((), True, "x^x > 0")
        lc = math.log(c)
        sols = []
        for rama in ([0, -1] if -1 / math.e <= lc < 0 else [0] if lc >= -1 / math.e else []):
            ex, w = NU.lambert_w(mx.Call("ln", (f.right,)), rama, trace)
            x = lc / w if w != 0 else 1.0
            exacta = exactifica(f, var, x)
            if exacta is None and w != 0:
                lnc = mx.Call("ln", (f.right,))
                exacta = mx.Div(lnc, mx.Call("W" if rama == 0 else "Wm1", (lnc,)))
            sols.append(Solucion(exacta, x))
        trace.regla("ecuacion.lambert", "x^x = c ⇔ ln x·e^(ln x) = ln c ⇔ x = e^(W(ln c))")
        return Resultado(tuple(sorted(sols, key=lambda s: s.valor)), True, "Lambert W")
    try:
        p = P.as_poly(_limpio(f))
    except Exception:  # noqa: BLE001
        return None
    atomos = {v for m in p for v, _ in m if P.is_atom(v)}
    if len(atomos) != 1:
        return None
    at = next(iter(atomos))
    texto = P.atom_text(at)
    nodo = mx.parse(texto)
    if isinstance(nodo, mx.Call) and nodo.name == "exp":
        arg = nodo.args[0]
    elif isinstance(nodo, mx.Pow) and nodo.base == mx.Const("e"):
        arg = nodo.exponent
    else:
        return None
    pb = RZ._polinomio_de(arg, var)
    if pb is None or len(RZ._recorta(pb)) != 2 or RZ._recorta(pb)[0] != 0:
        return None
    b = RZ._recorta(pb)[1]
    a = c = Fraction(0)
    for m, k in p.items():
        d = dict(m)
        if d == {var: 1, at: 1}:
            a = k
        elif not d:
            c = k
        else:
            return None
    if a == 0:
        return None
    sols = NU.resolver_x_exp(RZ._num(a), RZ._num(b), RZ._num(-c), trace)
    out = [Solucion(xe if xe is not None else exactifica(f, var, x), x) for xe, x in sols]
    return Resultado(tuple(sorted(out, key=lambda s: s.valor)), True, "Lambert W")


# ---------------------------------------------------------------------------
# forma exacta de una raíz numérica
# ---------------------------------------------------------------------------


def exactifica(f: mx.Expr, var: str, x: float) -> mx.Expr | None:
    """Racional, cuadrática (a + b√r), q·π, ln(q) o e^q: se acepta la primera que
    anula f exactamente al sustituirla."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    cands = []
    q = Fraction(x).limit_denominator(1000)
    if abs(float(q) - x) < 1e-10:
        cands.append(RZ._num(q))
    for den in range(1, 13):
        y = x * den
        for s in range(0, 13):
            a2 = y * y
            # x = (s ± √D)/den
            D = (y - s) ** 2
            Dq = Fraction(D).limit_denominator(1000)
            if Dq > 0 and abs(float(Dq) - D) < 1e-8:
                k, r = RZ._raiz_simplificada(Dq)
                if r != 1:
                    signo = 1 if y - s > 0 else -1
                    cands.append(RZ._mas_raiz(Fraction(s, den), signo * k / den, r))
            del a2
    qp = Fraction(x / math.pi).limit_denominator(48)
    if abs(float(qp) * math.pi - x) < 1e-10 and qp != 0:
        cands.append(_limpio(mx.Mul(RZ._num(qp), mx.Const("pi"))))
    if x != 0:
        ql = Fraction(math.exp(x)).limit_denominator(1000)
        if ql > 0 and abs(math.log(float(ql)) - x) < 1e-10:
            cands.append(mx.Call("ln", (RZ._num(ql),)))
    if x > 0:
        qe = Fraction(math.log(x)).limit_denominator(1000)
        if abs(math.exp(float(qe)) - x) < 1e-10 * max(1.0, x):
            cands.append(mx.Call("exp", (RZ._num(qe),)))
    vistos = set()
    for c in cands:
        t = mx.text(c)
        if t in vistos:
            continue
        vistos.add(t)
        try:
            if abs(float(mx.valor_real(c, {})) - x) > 1e-9 * max(1.0, abs(x)):
                continue
        except (TypeError, ValueError):
            continue
        if _es_cero_exacto(mx.substitute(f, var, c)):
            return c
    return None


# ---------------------------------------------------------------------------
# entrada
# ---------------------------------------------------------------------------


def resolver(f: mx.Expr, var: str = "x", trace: Trace | None = None) -> Resultado:
    """Todas las soluciones reales de f(x) = 0."""
    from academic_core.domain.engineering.mathlab import numericos as NU
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    otras = mx.variables(f) - {var}
    if otras:
        raise _no(f"más de una incógnita ({', '.join(sorted(otras))}); fija su valor")
    if var not in mx.variables(f):
        if _es_cero_exacto(f):
            raise _no("identidad 0 = 0: toda x del dominio es solución")
        trace.regla("ecuacion.constante", "la incógnita no aparece y no es 0 = 0")
        return Resultado((), True, "sin incógnita")
    for nombre, metodo in (("exponencial", _por_exponencial), ("logaritmo", _por_logaritmo),
                           ("radicales", _por_radicales), ("lambert", _por_lambert)):
        try:
            r = metodo(f, var, trace)
        except (UnsupportedError, ValidationError, ArithmeticError, ValueError, TypeError):
            r = None
        if r is not None:
            return _comprueba(f, var, r, trace)
    try:
        c = RZ.ceros(f, var, (-VENTANA, VENTANA))
        sols = tuple(Solucion(z.valor if z.exacta else exactifica(f, var, z.x), z.x)
                     for z in c.raices)
        r = Resultado(sols, c.completo, "Sturm / casos de raíces")
        trace.regla("ecuacion.ceros", f"{mx.text(f)} = 0: {c.texto()}",
                    why="raíces reales por casos exactos (polinomios, racionales, valor "
                        "absoluto, radicales) y, si no, por aislamiento numérico")
        return _comprueba(f, var, r, trace)
    except (UnsupportedError, ValidationError):
        pass
    rr = NU.todas_las_raices(f, var, -VENTANA, VENTANA, trace)
    sols = tuple(Solucion(ex if ex is not None else exactifica(f, var, v), v)
                 for ex, v, _ in rr.raices)
    return _comprueba(f, var, Resultado(sols, False, rr.metodo), trace)


def _comprueba(f, var, r: Resultado, trace: Trace) -> Resultado:
    limpias = []
    for s in r.soluciones:
        ex = s.exacta
        if ex is not None:
            ex = _limpio(ex)
            corta = exactifica(f, var, s.valor)
            if corta is not None and len(mx.text(corta)) < len(mx.text(ex)):
                ex = corta
        limpias.append(Solucion(ex, s.valor))
    r = Resultado(tuple(limpias), r.completo, r.metodo)
    for s in r.soluciones:
        if s.exacta is not None and not _es_cero_exacto(mx.substitute(f, var, s.exacta)):
            v = mx.valor_real(mx.substitute(f, var, s.exacta), {})
            if v is None or abs(v) > 1e-9:
                raise _error("INTERNAL", f"{mx.text(s.exacta)} no cumple la ecuación")
        if not _dominio_ok(f, var, s.valor):
            raise _error("INTERNAL", f"x ≈ {s.valor:.10g} no anula la ecuación")
    trace.verificacion("ecuacion.sustitucion", "cada solución sustituida en la ecuación "
                       "original (exacta si tiene forma cerrada)")
    return r
