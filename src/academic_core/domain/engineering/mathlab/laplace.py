# SPDX-License-Identifier: MIT
"""ML-8 (§4.5): transformada de Laplace exacta, directa e inversa.

Directa. La señal se lee con :mod:`distribuciones` (tramos, escalones u(t − a) y
deltas δ⁽ᵏ⁾(t − a)); cada tramo [a, b) de t ≥ 0 con expresión g aporta
``e^{−as}·L{g(t + a)} − e^{−bs}·L{g(t + b)}`` (segundo teorema de traslación) y
cada impulso ``A·s^k·e^{−t₀s}``. ``L{g}`` sale de la tabla para cuasipolinomios:
``L{tⁿe^{αt}cos βt} = n!·Re[(s−α+iβ)^{n+1}]/((s−α)²+β²)^{n+1}`` (y con Im para el
seno), que contiene todas las reglas de la tabla (traslación en s, multiplicación
por tⁿ). Región de convergencia: Re s > máx Re α de los tramos que llegan a +∞.

Inversa. F(s) = Σ e^{−aₖs}·Rₖ(s) con Rₖ racional de denominador en ℚ[s]: parte
entera (deltas y sus derivadas), factores irreducibles de ℚ[s] (lineales y
cuadráticos, con cualquier multiplicidad), fracciones simples por un sistema
lineal exacto y la tabla inversa; los cuadráticos repetidos con
``L⁻¹{s/(s²+ω²)^{k+1}} = t/(2k)·L⁻¹{1/(s²+ω²)^k}`` y
``1/(s²+ω²)^{k+1} = [1/(s²+ω²)^k − s²/(s²+ω²)^{k+1}]/ω²``.

Segundos caminos: la directa se compara con ∫₀^∞ e^{−st}f(t)dt por cuadratura en
varios s reales de la región; la inversa se vuelve a transformar y se compara
exactamente (y en puntos) con F.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

S = "s"


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


limpio = Q.limpio


def _racional(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        r = MI._racional(limpio(e))
        return r if r is not None else limpio(e)
    except Exception:  # noqa: BLE001
        return limpio(e)


# ---------------------------------------------------------------------------
# polinomios con coeficientes expresión (listas de grado bajo a alto)
# ---------------------------------------------------------------------------


def _p_suma(a, b):
    n = max(len(a), len(b))
    cero = mx.Num(Fraction(0))
    return [limpio(mx.Add(a[i] if i < len(a) else cero, b[i] if i < len(b) else cero))
            for i in range(n)]


def _p_mul(a, b):
    out = [mx.Num(Fraction(0))] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] = mx.Add(out[i + j], mx.Mul(x, y))
    return [limpio(c) for c in out]


def _p_expr(p, var: str = S) -> mx.Expr:
    total = None
    for k, c in enumerate(p):
        if Q.es_cero(c):
            continue
        m = c if k == 0 else mx.Mul(c, mx.Sym(var) if k == 1 else mx.Pow(mx.Sym(var), mx.Num(k)))
        total = m if total is None else mx.Add(total, m)
    return limpio(total) if total is not None else mx.Num(Fraction(0))


def _exp_retardo(a: mx.Expr, var: str = S) -> str:
    """e^(−a·s) legible: e^(−s), e^(−2s), e^(−π·s)."""
    v = mx.exact_value(a)
    if v is not None and not mx.variables(a):
        v = Fraction(v)
        return f"e^(−{var})" if v == 1 else f"e^(−{v}{var})" if v.denominator == 1 else \
            f"e^(−({v}){var})"
    return f"e^(−{mx.pretty(a)}·{var})"


def decimales(texto: str) -> str:
    """Fracciones enormes (decimales binarios exactos) → ≈ con 10 cifras."""
    import re

    def cambia(m):
        a, b = int(m.group(1)), int(m.group(2))
        return f"{a / b:.10g}"
    return re.sub(r"(-?\d+)/(\d{7,})", cambia, texto)


def _poli_txt(p, var: str = S) -> str:
    """Polinomio en potencias decrecientes: «s^2 + 4·s + 13»."""
    partes = []
    for k in range(len(p) - 1, -1, -1):
        c = p[k]
        if Q.es_cero(c):
            continue
        v = mx.exact_value(c)
        pot = "" if k == 0 else var if k == 1 else f"{var}^{k}"
        if v is not None and not mx.variables(c):
            v = Fraction(v)
            signo = "-" if v < 0 else "+"
            mag = abs(v)
            cuerpo = (str(mag) if not pot else (pot if mag == 1 else f"{mag}·{pot}"))
        else:
            ct = mx.text(c)
            signo = "+"
            if ct.startswith("-"):
                signo, ct = "-", ct[1:]
            if any(op in ct for op in " +-") and pot:
                ct = f"({ct})"
            cuerpo = ct if not pot else f"{ct}·{pot}"
        partes.append((signo, cuerpo))
    if not partes:
        return "0"
    texto = ("-" if partes[0][0] == "-" else "") + partes[0][1]
    for signo, cuerpo in partes[1:]:
        texto += f" {signo} {cuerpo}"
    return texto


def _q_a_expr(p: list[Fraction], var: str = S) -> mx.Expr:
    return _p_expr([mx.Num(c) if c >= 0 else mx.Neg(mx.Num(-c)) for c in p], var)


# ---------------------------------------------------------------------------
# directa
# ---------------------------------------------------------------------------


@dataclass
class Fraccion:
    """e^{−a·s}·num(s)/den(s): num con coeficientes expresión, den en ℚ si se puede."""

    retardo: mx.Expr
    num: list
    den: list            # list[Fraction] o list[mx.Expr]

    def expr(self) -> mx.Expr:
        r = mx.Div(_p_expr(self.num), _p_expr(self.den) if not isinstance(self.den[0], Fraction)
                   else _q_a_expr(self.den))
        r = _racional(r)
        if Q.es_cero(self.retardo):
            return r
        return mx.Mul(mx.Call("exp", (limpio(mx.Neg(mx.Mul(self.retardo, mx.Sym(S)))),)), r)


def _re_im(m: int, X: list, beta: mx.Expr, parte: str) -> list:
    """Re o Im de (X + iβ)^m con X un polinomio en s (coeficientes expresión)."""
    total = [mx.Num(Fraction(0))]
    Xk = [[mx.Num(Fraction(1))]]
    for _ in range(m):
        Xk.append(_p_mul(Xk[-1], X))
    for k in range(m + 1):
        if (parte == "re") != (k % 2 == 0):
            continue
        signo = (-1) ** (k // 2) if k % 2 == 0 else (-1) ** ((k - 1) // 2)
        c = limpio(mx.Mul(mx.Num(Fraction(signo * math.comb(m, k))),
                          mx.Pow(beta, mx.Num(Fraction(k))) if k else mx.Num(Fraction(1))))
        total = _p_suma(total, _p_mul(Xk[m - k], [c]))
    return total


def _como_q(p) -> list | None:
    out = []
    for c in p:
        v = mx.exact_value(c)
        if v is None or mx.variables(c):
            return None
        out.append(Fraction(v))
    return out


def transformada_termino(x: Q.Termino) -> Fraccion:
    """L{c·tⁿe^{αt}·f(βt)}."""
    X = [limpio(mx.Neg(x.alfa)), mx.Num(Fraction(1))]          # s − α
    fact = mx.Num(Fraction(math.factorial(x.n)))
    m = x.n + 1
    if x.tipo == "1":
        den = [mx.Num(Fraction(1))]
        for _ in range(m):
            den = _p_mul(den, X)
        num = [limpio(mx.Mul(fact, x.coef))]
    else:
        base = _p_suma(_p_mul(X, X), [limpio(mx.Pow(x.beta, mx.Num(2)))])
        den = [mx.Num(Fraction(1))]
        for _ in range(m):
            den = _p_mul(den, base)
        num = [limpio(mx.Mul(mx.Mul(fact, x.coef), c))
               for c in _re_im(m, X, x.beta, "re" if x.tipo == "cos" else "im")]
    dq = _como_q(den)
    return Fraccion(mx.Num(Fraction(0)), num, dq if dq is not None else den)


@dataclass
class Directa:
    fracciones: list                  # list[Fraccion]
    abscisa: float | None             # Re s > abscisa (None: toda s)
    abscisa_txt: str
    señal: object                     # la distribución leída

    def expr(self) -> mx.Expr:
        total = None
        for f in self.fracciones:
            e = f.expr()
            total = e if total is None else mx.Add(total, e)
        return limpio(total) if total is not None else mx.Num(Fraction(0))

    def agrupada_texto(self) -> list[tuple[mx.Expr, str]]:
        """[(a, «N(s)/D(s)»)] sumando las fracciones de cada retardo sobre ℚ[s]."""
        from academic_core.domain.engineering.mathlab import algebra as AL

        grupos: dict[str, list] = {}
        for f in self.fracciones:
            grupos.setdefault(mx.text(f.retardo), [f.retardo, []])[1].append(f)
        out = []
        for a, fs in sorted(grupos.values(), key=lambda g: float(mx.valor_real(g[0], {}))):
            if not all(isinstance(f.den[0], Fraction) for f in fs):
                out.append((a, mx.text(_racional(mx.Add(*[f.expr() for f in fs]))
                                       if len(fs) == 2 else self._suma_expr(fs))))
                continue
            D = [Fraction(1)]
            for f in fs:
                g = AL._p_gcd(D, f.den)
                D = AL._p_recorta(AL._p_divmod(AL._p_mul(D, f.den), g)[0])
            N = [mx.Num(Fraction(0))]
            for f in fs:
                factor = AL._p_recorta(AL._p_divmod(D, f.den)[0])
                N = _p_suma(N, _p_mul(f.num, [mx.Num(c) if c >= 0 else mx.Neg(mx.Num(-c))
                                               for c in factor]))
            Nq = _como_q(N)
            if Nq is not None:
                if all(c == 0 for c in Nq):
                    continue
                g = AL._p_gcd(Nq, D)
                if len(g) > 1:
                    Nq = AL._p_recorta(AL._p_divmod(Nq, g)[0])
                    D = AL._p_recorta(AL._p_divmod(D, g)[0])
                N = [Q.num(c) for c in Nq]
            # coeficientes enteros en el denominador y líder positivo
            escala_ = Fraction(math.lcm(*[c.denominator for c in D]))
            lider = D[-1] * escala_
            escala_ = escala_ / abs(lider) * abs(lider).denominator if False else escala_
            if lider < 0:
                escala_ = -escala_
            D = [c * escala_ for c in D]
            N = [limpio(mx.Mul(c, Q.num(escala_))) for c in N]
            g_int = math.gcd(*[int(c) for c in D if c]) if all(c.denominator == 1 for c in D) else 1
            Nq2 = _como_q(N)
            if Nq2 is not None and all(c.denominator == 1 for c in Nq2):
                g_int = math.gcd(g_int, *[int(c) for c in Nq2 if c]) if any(Nq2) else g_int
            if g_int > 1:
                D = [c / g_int for c in D]
                N = [limpio(mx.Div(c, mx.Num(Fraction(g_int)))) for c in N]
            nt, dt = _poli_txt(N), _poli_txt([Q.num(c) for c in D])
            if " " in nt.strip("-"):
                nt = f"({nt})"
            if " " in dt:
                dt = f"({dt})"
            out.append((a, nt if dt == "1" else f"{nt}/{dt}"))
        return out

    @staticmethod
    def _suma_expr(fs):
        total = fs[0].expr()
        for f in fs[1:]:
            total = mx.Add(total, f.expr())
        return limpio(total)

    def agrupada(self) -> list[tuple[mx.Expr, mx.Expr]]:
        """[(a, Rₐ(s))] con Rₐ en una sola fracción por retardo."""
        grupos: dict[str, tuple[mx.Expr, mx.Expr]] = {}
        for f in self.fracciones:
            clave = mx.text(f.retardo)
            r = mx.Div(_p_expr(f.num), _p_expr(f.den) if not isinstance(f.den[0], Fraction)
                       else _q_a_expr(f.den))
            if clave in grupos:
                grupos[clave] = (f.retardo, mx.Add(grupos[clave][1], r))
            else:
                grupos[clave] = (f.retardo, r)
        return [(a, _racional(r)) for a, r in sorted(
            grupos.values(), key=lambda g: float(mx.valor_real(g[0], {})))]

    def texto(self) -> str:
        partes = []
        for a, r in self.agrupada_texto():
            if Q.es_cero(a):
                partes.append(r)
            else:
                partes.append(f"{_exp_retardo(a)}·{r if r.startswith('(') or ' ' not in r else '(' + r + ')'}")
        cuerpo = " + ".join(partes) or "0"
        return f"F(s) = {cuerpo}; región de convergencia: {self.abscisa_txt}"


def prepara(texto: str, t: str = "t") -> str:
    """u(·), H(·) → heaviside(·); δ(·) → delta(·); notación de pizarra normalizada."""
    import re

    texto = texto.replace("δ", "delta").replace("**", "^")
    texto = re.sub(r"(?<![A-Za-z_])(u|H)\s*\(", "heaviside(", texto)
    return mx.normaliza_entrada(texto)


def _expande(e: mx.Expr) -> mx.Expr:
    """Distribuye productos sobre sumas: t·(u(t) − u(t − 1)) = t·u(t) − t·u(t − 1)."""
    if isinstance(e, (mx.Add, mx.Sub)):
        return type(e)(_expande(e.left), _expande(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_expande(e.arg))
    if isinstance(e, mx.Mul):
        a, b = _expande(e.left), _expande(e.right)
        for x, y, izq in ((a, b, True), (b, a, False)):
            if isinstance(x, (mx.Add, mx.Sub)):
                l_ = _expande(mx.Mul(x.left, y) if izq else mx.Mul(y, x.left))
                r_ = _expande(mx.Mul(x.right, y) if izq else mx.Mul(y, x.right))
                return type(x)(l_, r_)
            if isinstance(x, mx.Neg):
                return mx.Neg(_expande(mx.Mul(x.arg, y) if izq else mx.Mul(y, x.arg)))
        return mx.Mul(a, b)
    if isinstance(e, mx.Div) and not mx.variables(e.right):
        n = _expande(e.left)
        if isinstance(n, (mx.Add, mx.Sub)):
            return type(n)(_expande(mx.Div(n.left, e.right)), _expande(mx.Div(n.right, e.right)))
        return mx.Div(n, e.right)
    return e


def _lee_senal(texto: str, t: str, trace: Trace):
    from academic_core.domain.engineering.mathlab import distribuciones as DI

    if "'" in texto or "′" in texto:
        # δ′, δ″…: el lector de distribuciones las entiende; el de expresiones no
        import re

        crudo = texto.replace("′", "'").replace("δ", "delta").replace("**", "^")
        crudo = re.sub(r"(?<![A-Za-z_])(u|H)\s*\(", "heaviside(", crudo)
        return DI.leer(crudo, t, trace)
    e = _expande(mx.parse(prepara(texto, t)))
    planos: list[tuple[int, mx.Expr]] = []

    def aplana(n, signo):
        if isinstance(n, mx.Add):
            aplana(n.left, signo)
            aplana(n.right, signo)
        elif isinstance(n, mx.Sub):
            aplana(n.left, signo)
            aplana(n.right, -signo)
        elif isinstance(n, mx.Neg):
            aplana(n.arg, -signo)
        elif not Q.es_cero(n) if not mx.variables(n) else True:
            planos.append((signo, n))

    aplana(e, 1)
    if not planos:
        return DI.leer("0", t, trace)
    texto_plano = ""
    for i, (signo, n) in enumerate(planos):
        tt = mx.text(n)
        if i == 0:
            texto_plano = ("-" if signo < 0 else "") + tt
        else:
            texto_plano += (" - " if signo < 0 else " + ") + tt
    return DI.leer(texto_plano, t, trace)


def transformada(texto: str, t: str = "t", trace: Trace | None = None) -> Directa:
    """L{f}(s) = ∫₀⁻^∞ e^{−st} f(t) dt."""
    trace = trace if trace is not None else Trace()
    D = _lee_senal(texto, t, trace)
    fracs: list[Fraccion] = []
    abscisa = None
    for tramo in D.tramos:
        if Q.es_cero(tramo.expr):
            continue
        a = tramo.desde
        b = tramo.hasta
        if b is not None and b.x <= 0:
            continue
        a_expr = mx.Num(Fraction(0)) if a is None or a.x <= 0 else a.expr
        g = Q.leer(mx.substitute(tramo.expr, t, mx.Sym("t")) if t != "t" else tramo.expr, "t")
        desde = Q.desplaza(g, a_expr)
        for term in desde:
            fr = transformada_termino(term)
            fracs.append(Fraccion(a_expr, fr.num, fr.den))
        trace.regla("laplace.tramo", f"{mx.text(tramo.expr)} en ({mx.text(a_expr)}, "
                    f"{'+∞' if b is None else mx.text(b.expr)}): e^(−{mx.text(a_expr)}s)·"
                    f"L{{g({t} + {mx.text(a_expr)})}}" + ("" if b is None else
                                                         f" − e^(−{mx.text(b.expr)}s)·L{{g({t} + "
                                                         f"{mx.text(b.expr)})}}"),
                    why="g·[u(t − a) − u(t − b)] y el segundo teorema de traslación: "
                        "L{g(t)·u(t − a)} = e^(−as)·L{g(t + a)}")
        if b is None:
            for term in g:
                al = mx.valor_real(term.alfa, {})
                if al is not None and (abscisa is None or al > abscisa):
                    abscisa = float(al)
        else:
            hasta = Q.desplaza(g, b.expr)
            for term in hasta:
                fr = transformada_termino(term)
                fracs.append(Fraccion(b.expr, [limpio(mx.Neg(c)) for c in fr.num], fr.den))
    for imp in D.impulsos:
        if imp.posicion.x < 0:
            continue
        num = [mx.Num(Fraction(0))] * imp.orden + [imp.area]
        fracs.append(Fraccion(imp.posicion.expr if imp.posicion.x > 0 else mx.Num(Fraction(0)),
                              num, [Fraction(1)]))
        trace.regla("laplace.delta", f"L{{δ{'′' * imp.orden}({t} − {imp.posicion})}} = "
                    f"s^{imp.orden}·e^(−{imp.posicion}·s)",
                    why="propiedad de criba de la delta (convenio 0⁻: la delta en 0 cuenta)")
    if abscisa is None:
        txt = "toda s (señal de soporte acotado)"
    else:
        al = Fraction(abscisa).limit_denominator(10 ** 6)
        txt = f"Re s > {al if abs(float(al) - abscisa) < 1e-12 else f'{abscisa:.10g}'}"
    r = Directa(fracs, abscisa, txt, D)
    trace.regla("laplace.resultado", r.texto(),
                why="tabla: L{tⁿe^(αt)cos βt} = n!·Re[(s−α+iβ)^(n+1)]/((s−α)²+β²)^(n+1) "
                    "y la parte imaginaria para el seno")
    _verifica_directa(D, r, t, trace)
    return r


def valor_senal(D, t: float) -> float:
    total = 0.0
    for tramo in D.tramos:
        if tramo.contiene(t):
            try:
                v = mx.valor_real(tramo.expr, {D.var: t})
            except (OverflowError, ValueError):
                v = None
            total += float(v) if v is not None else 0.0
    return total


def _verifica_directa(D, r: Directa, t: str, trace: Trace) -> None:
    from academic_core.domain.engineering.mathlab import multiple as MI

    base = 0.0 if r.abscisa is None else r.abscisa
    F = r.expr()
    peor = 0.0
    probados = 0
    cortes = sorted({0.0} | {p.x for tr in D.tramos for p in (tr.desde, tr.hasta)
                             if p is not None and p.x > 0})
    for s in (base + 1.3, base + 2.7, base + 4.1):
        total = 0.0
        tramos = list(zip(cortes, cortes[1:])) + [(cortes[-1], None)]
        for a, b in tramos:
            if b is None:
                # [a, ∞): t = a + u/(1 − u), u ∈ [0, 1)
                def g(u, a=a):
                    if u >= 1:
                        return 0.0
                    tt = a + u / (1 - u)
                    try:
                        return math.exp(-s * tt) * valor_senal(D, tt) / (1 - u) ** 2
                    except (OverflowError, ValueError):
                        return 0.0      # cola: la integral converge (s en la región)
                total += _cuadratura(g, 0.0, 1.0)
            else:
                total += _cuadratura(lambda x: math.exp(-s * x) * valor_senal(D, x), a, b)
        for imp in D.impulsos:
            if imp.posicion.x >= 0:
                area = float(mx.valor_real(imp.area, {}))
                total += area * (s ** imp.orden) * math.exp(-s * imp.posicion.x)
        exacto = mx.valor_real(F, {S: s})
        if exacto is None:
            continue
        probados += 1
        peor = max(peor, abs(total - exacto) / max(1.0, abs(exacto)))
    if probados and peor < 1e-7:
        trace.verificacion("laplace.cuadratura", f"F(s) frente a ∫₀^∞ e^(−st)f(t)dt por "
                           f"cuadratura en {probados} valores de s: desviación {peor:.2g}",
                           why="la definición calculada por otro camino")
        return
    raise _error("DISCREPANT", f"la transformada no coincide con la integral (desviación "
                 f"{peor:.3g})")


def _gauss_legendre(n: int) -> tuple[list[float], list[float]]:
    """Nodos y pesos de Gauss-Legendre por Newton sobre Pₙ (recurrencia de Bonnet)."""
    xs, ws = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, x
            for k in range(2, n + 1):
                p0, p1 = p1, ((2 * k - 1) * x * p1 - (k - 1) * p0) / k
            dp = n * (x * p1 - p0) / (x * x - 1)
            dx = p1 / dp
            x -= dx
            if abs(dx) < 1e-16:
                break
        xs.append(x)
        ws.append(2 / ((1 - x * x) * dp * dp))
    return xs, ws


_GL = _gauss_legendre(20)


def _cuadratura(f, a: float, b: float, n: int = 400) -> float:
    """Gauss-Legendre compuesta (40 trozos de 20 nodos)."""
    x, w = _GL
    total = 0.0
    trozos = 40
    h = (b - a) / trozos
    for k in range(trozos):
        m = a + (k + 0.5) * h
        for xi, wi in zip(x, w):
            total += wi * f(m + 0.5 * h * xi) * 0.5 * h
    return total


# ---------------------------------------------------------------------------
# fracciones simples sobre ℚ
# ---------------------------------------------------------------------------


@dataclass
class Simple:
    """A(s)/q(s)^k con q irreducible de grado 1 o 2 y A de grado < grado q."""

    q: list                 # list[Fraction] mónico
    k: int
    A: list                 # coeficientes (expresión) de A


def _divmod_q(a: list[Fraction], b: list[Fraction]):
    from academic_core.domain.engineering.mathlab import algebra as AL

    return AL._p_divmod(a, b)


def _resuelve_q(M: list[list[Fraction]], v: list[Fraction]) -> list[Fraction]:
    from academic_core.domain.engineering.mathlab import lineal as L

    K = L.cuerpo("Q")
    sol = L.resolver_sistema([list(f) for f in M], list(v), K, Trace())
    if sol.particular is None or sol.nucleo:
        raise _error("INTERNAL", "el sistema de las fracciones simples no es determinado")
    return [Fraction(x) for x in sol.particular]


def simples(num: list, den: list[Fraction]) -> tuple[list, list[Simple]]:
    """num/den = parte entera + Σ simples. num con coeficientes expresión, den ∈ ℚ[s]."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    den = AL._p_recorta(list(den))
    lider = den[-1]
    den = [c / lider for c in den]
    num = [limpio(mx.Div(c, mx.Num(lider))) for c in num]
    factores = AL.factores_irreducibles(den)
    for q, _ in factores:
        if len(q) - 1 > 2:
            raise _no(f"el denominador tiene el factor irreducible {AL._texto_poli(q)} de "
                      "grado ≥ 3: sus raíces no tienen forma exacta sencilla")
    n = len(den) - 1
    # base: para cada factor q^j y cada sᵗ (t < grado q): sᵗ·den/q^j
    base: list[tuple[int, int, int]] = []
    columnas: list[list[Fraction]] = []
    for i, (q, m) in enumerate(factores):
        for j in range(1, m + 1):
            cociente = den
            for _ in range(j):
                cociente, resto = AL._p_divmod(cociente, q)
            for t in range(len(q) - 1):
                col = [Fraction(0)] * t + list(cociente)
                columnas.append((col + [Fraction(0)] * n)[:n])
                base.append((i, j, t))
    if len(columnas) != n:
        raise _error("INTERNAL", "la base de fracciones simples no tiene grado(den) elementos")
    M = [[columnas[c][r] for c in range(n)] for r in range(n)]
    # parte entera y resto, monomio a monomio del numerador
    entera: list = [mx.Num(Fraction(0))]
    coefs: list[mx.Expr] = [mx.Num(Fraction(0))] * n
    for grado, c in enumerate(num):
        if Q.es_cero(c):
            continue
        mono = [Fraction(0)] * grado + [Fraction(1)]
        if grado >= n:
            cociente, resto = AL._p_divmod(mono, den)
            entera = _p_suma(entera, [limpio(mx.Mul(c, mx.Num(x))) for x in cociente])
            mono = (list(resto) + [Fraction(0)] * n)[:n] if resto else [Fraction(0)] * n
        else:
            mono = (mono + [Fraction(0)] * n)[:n]
        if all(x == 0 for x in mono):
            continue
        sol = _resuelve_q(M, mono)
        coefs = [limpio(mx.Add(a, mx.Mul(c, mx.Num(x)))) for a, x in zip(coefs, sol)]
    out: list[Simple] = []
    for i, (q, m) in enumerate(factores):
        for j in range(1, m + 1):
            A = [coefs[k] for k, (ii, jj, _) in enumerate(base) if ii == i and jj == j]
            if all(Q.es_cero(a) for a in A):
                continue
            out.append(Simple(list(q), j, A))
    return entera, out


def inversa_racional(num: list, den: list[Fraction]):
    """(exacto, simbólico | None, definiciones, entera, aproximada) de L⁻¹{num/den}:
    fracciones simples; cúbicas irreducibles por Cardano exacto; grado ≥ 4 irreducible
    (sin fórmula manejable) por residuos numéricos."""
    from academic_core.domain.engineering.mathlab import cubica as CU

    try:
        entera, fs = simples(num, den)
        g: Q.Cuasi = []
        for f in fs:
            g = Q.suma(g, inversa_simple(f))
        return g, None, [], entera, False
    except UnsupportedError as exc:
        if "grado ≥ 3" not in str(exc):
            raise
    try:
        sep = CU.separa(num, den)
    except UnsupportedError:
        sep = None
    if sep is not None:
        cubicas, num1, P, num2, R = sep
        exacto, simb, defs = CU.inversa_residuos(num1, P, cubicas)
        entera: list = []
        if len(R) > 1:
            entera, fs = simples(num2, R)
            resto: Q.Cuasi = []
            for f in fs:
                resto = Q.suma(resto, inversa_simple(f))
            exacto = Q.suma(exacto, resto)
            simb = list(simb) + list(resto)
        else:
            entera = [limpio(mx.Div(c, Q.num(R[0]))) for c in num2]
        return exacto, simb, defs, entera, False
    if len(num) >= len(den):
        raise _no("parte entera con un denominador sin raíces exactas")
    return inversa_numerica(num, den), None, [], [], True


def inversa_numerica(num: list, den: list[Fraction]) -> Q.Cuasi:
    """L⁻¹{num/den} por residuos en raíces numéricas simples (Durand-Kerner):
    A = num(p)/den′(p); un par conjugado da e^{at}(2Re A·cos bt − 2Im A·sen bt).
    Los coeficientes son decimales: el resultado es solo numérico."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    den = AL._p_recorta(list(den))
    raices = AL._raices_complejas([c / den[-1] for c in den])
    for i, a in enumerate(raices):
        for b in raices[i + 1:]:
            if abs(a - b) < 1e-7:
                raise _no("raíces múltiples sin forma exacta: fuera del alcance numérico")
    numf = [complex(mx.valor_real(c, {})) for c in num]
    dpf = [float(k * den[k]) for k in range(1, len(den))]

    def ev(p, z):
        tot = 0j
        for c in reversed(p):
            tot = tot * z + c
        return tot
    cero = mx.Num(Fraction(0))
    out: Q.Cuasi = []
    usados = set()
    for i, r in enumerate(raices):
        if i in usados:
            continue
        A = ev(numf, r) / ev(dpf, r)
        if abs(r.imag) < 1e-12:
            out.append(Q.Termino(mx.Num(Fraction(A.real)), 0, mx.Num(Fraction(r.real)), "1", cero))
            continue
        j = min((k for k in range(len(raices)) if k != i and k not in usados),
                key=lambda k: abs(raices[k] - r.conjugate()))
        usados.update((i, j))
        a, b = r.real, abs(r.imag)
        if r.imag < 0:
            A = A.conjugate()
        out.append(Q.Termino(mx.Num(Fraction(2 * A.real)), 0, mx.Num(Fraction(a)), "cos",
                             mx.Num(Fraction(b))))
        out.append(Q.Termino(mx.Num(Fraction(-2 * A.imag)), 0, mx.Num(Fraction(a)), "sin",
                             mx.Num(Fraction(b))))
    return Q.normaliza(out)


# ---------------------------------------------------------------------------
# inversa
# ---------------------------------------------------------------------------


def _cuad_base(omega: mx.Expr, k: int, sigma: int = 1) -> tuple[Q.Cuasi, Q.Cuasi]:
    """(L⁻¹{1/(s²+σω²)^k}, L⁻¹{s/(s²+σω²)^k}) como cuasipolinomios (σ = ±1)."""
    cero = mx.Num(Fraction(0))
    t = [Q.Termino(mx.Num(Fraction(1)), 1, cero, "1", cero)]
    if sigma > 0:
        uno_ = [Q.Termino(limpio(mx.Div(mx.Num(1), omega)), 0, cero, "sin", omega)]  # sen ωt/ω
        s_ = [Q.Termino(mx.Num(Fraction(1)), 0, cero, "cos", omega)]                 # cos ωt
    else:
        medio = mx.Num(Fraction(1, 2))
        mw = limpio(mx.Neg(omega))
        dw = limpio(mx.Div(medio, omega))
        uno_ = Q.normaliza([Q.Termino(dw, 0, omega, "1", cero),                      # senh ωt/ω
                            Q.Termino(limpio(mx.Neg(dw)), 0, mw, "1", cero)])
        s_ = Q.normaliza([Q.Termino(medio, 0, omega, "1", cero),                     # cosh ωt
                          Q.Termino(medio, 0, mw, "1", cero)])
    w2 = limpio(mx.Mul(Q.num(sigma), mx.Pow(omega, mx.Num(2))))
    for kk in range(1, k):
        nuevo_s = Q.escala(Q.producto(t, uno_), mx.Num(Fraction(1, 2 * kk)))
        # 1/(…)^{k+1} = [1/(…)^k − s·(s/(…)^{k+1})]/ω²; L⁻¹{s·G} = g′ (g(0) = 0)
        nuevo_1 = Q.escala(Q.suma(uno_, Q.escala(Q.deriva(nuevo_s), mx.Num(-1))),
                           limpio(mx.Div(mx.Num(1), w2)))
        uno_, s_ = nuevo_1, nuevo_s
    return uno_, s_


def inversa_simple(f: Simple) -> Q.Cuasi:
    cero = mx.Num(Fraction(0))
    if len(f.q) == 2:
        r = -f.q[0]
        c = limpio(mx.Div(f.A[0], mx.Num(Fraction(math.factorial(f.k - 1)))))
        return Q.normaliza([Q.Termino(c, f.k - 1, Q.num(r), "1", cero)])
    c0, b = f.q[0], f.q[1]
    p = -b / 2
    w2 = c0 - b * b / 4
    if w2 == 0:
        raise _error("INTERNAL", "un factor cuadrático «irreducible» que es un cuadrado")
    sigma = 1 if w2 > 0 else -1          # σ = −1: raíces reales irracionales p ± ω
    omega = limpio(mx.Root(2, Q.num(abs(w2))))
    B = f.A[1] if len(f.A) > 1 else cero
    C = f.A[0]
    D = limpio(mx.Add(C, mx.Mul(B, Q.num(p))))     # B·s + C = B·X + (C + B·p), X = s − p
    uno_, s_ = _cuad_base(omega, f.k, sigma)
    g = Q.suma(Q.escala(s_, B), Q.escala(uno_, D))
    return Q.producto(g, [Q.Termino(mx.Num(Fraction(1)), 0, Q.num(p), "1", cero)])


@dataclass
class Inversa:
    piezas: list           # list[(retardo, cuasi, impulsos)]; impulsos = [(orden, coef)]
    t: str = "t"
    texto_simples: list = field(default_factory=list)
    aproximada: bool = False
    simbolicas: list = field(default_factory=list)    # cuasi con raíces nombradas (o None)
    definiciones: list = field(default_factory=list)  # [(nombre, raíz exacta)]

    def expr(self) -> mx.Expr:
        total = None
        T = mx.Sym(self.t)
        for a, cuasi, imp in self.piezas:
            g = Q.a_expr(cuasi, self.t)
            if not Q.es_cero(a):
                g = mx.Mul(mx.Call("heaviside", (limpio(mx.Sub(T, a)),)),
                           limpio(mx.substitute(g, self.t, mx.Sub(T, a))))
            for orden, c in imp:
                d = mx.Call("delta" + "1" * 0, (limpio(mx.Sub(T, a)),))
                g = mx.Add(g, mx.Mul(c, d)) if orden == 0 else g
            total = g if total is None else mx.Add(total, g)
        return limpio(total) if total is not None else mx.Num(Fraction(0))

    def texto(self) -> str:
        partes = []
        for i, (a, cuasi, imp) in enumerate(self.piezas):
            simb = self.simbolicas[i] if i < len(self.simbolicas) else None
            g = Q.a_expr(simb if simb else cuasi, self.t)
            desplazado = "(t)" if Q.es_cero(a) else f"(t − {mx.pretty(a)})"
            if not Q.es_cero(g):
                gt = mx.pretty(g) if Q.es_cero(a) else mx.pretty(limpio(mx.substitute(
                    g, self.t, mx.Sub(mx.Sym(self.t), a))))
                partes.append(gt if Q.es_cero(a) else f"u{desplazado}·({gt})")
            for orden, c in imp:
                d = f"δ{'′' * orden}{desplazado}"
                partes.append(d if mx.exact_value(c) == 1 else f"{mx.pretty(c)}·{d}")
        texto = "f(t) = " + (" + ".join(partes) if partes else "0") + " (t ≥ 0)"
        if self.definiciones:
            texto += " donde " + "; ".join(f"{n} = {mx.pretty(e)}" for n, e in self.definiciones)
        return decimales(texto) + (" (coeficientes numéricos)" if self.aproximada else "")


def _separa_retardos(F: mx.Expr, s: str) -> list[tuple[mx.Expr, mx.Expr]]:
    """F = Σ e^{−aₖs}·Rₖ(s)."""
    from academic_core.domain.engineering.mathlab import poly as P

    terminos = []

    def suma(e, signo):
        if isinstance(e, mx.Div) and isinstance(e.left, (mx.Add, mx.Sub, mx.Neg)):
            n = e.left
            if isinstance(n, mx.Neg):
                suma(mx.Div(n.arg, e.right), -signo)
            else:
                suma(mx.Div(n.left, e.right), signo)
                suma(mx.Div(n.right, e.right), signo if isinstance(n, mx.Add) else -signo)
            return
        if isinstance(e, mx.Mul) and isinstance(e.left, (mx.Add, mx.Sub)) and \
                any(isinstance(x, mx.Call) and x.name == "exp" or
                    isinstance(x, mx.Pow) and x.base == mx.Const("e") for x in _hojas(e.left)):
            suma(mx.Mul(e.left.left, e.right), signo)
            suma(mx.Mul(e.left.right, e.right), signo if isinstance(e.left, mx.Add) else -signo)
            return
        if isinstance(e, mx.Add):
            suma(e.left, signo)
            suma(e.right, signo)
        elif isinstance(e, mx.Sub):
            suma(e.left, signo)
            suma(e.right, -signo)
        elif isinstance(e, mx.Neg):
            suma(e.arg, -signo)
        else:
            terminos.append(e if signo > 0 else mx.Neg(e))

    suma(F, 1)
    grupos: dict[str, list] = {}

    def retardo_de(e):
        """(a, resto) con e = e^{−as}·resto."""
        a = mx.Num(Fraction(0))
        factores = []

        def recorre(n, dividir=False):
            nonlocal a
            if isinstance(n, mx.Mul) and not dividir:
                recorre(n.left)
                recorre(n.right)
                return
            if isinstance(n, mx.Neg):
                factores.append(mx.Num(Fraction(-1)))
                recorre(n.arg, dividir)
                return
            arg = None
            if isinstance(n, mx.Call) and n.name == "exp":
                arg = n.args[0]
            elif isinstance(n, mx.Pow) and n.base == mx.Const("e"):
                arg = n.exponent
            if arg is not None and mx.depends(arg, s):
                lin = Q._lineal(arg, s)
                if lin is None or not Q.es_cero(lin[1]):
                    raise _no(f"«{mx.text(n)}»: solo exponenciales e^(−a·s)")
                a = limpio(mx.Add(a, mx.Neg(lin[0])))
                return
            factores.append(n)

        signo = 1
        while isinstance(e, mx.Neg):
            e, signo = e.arg, -signo
        if isinstance(e, mx.Div):
            recorre(e.left)
            resto = mx.Div(_prod(factores), e.right)
        else:
            recorre(e)
            resto = _prod(factores)
        return a, (resto if signo > 0 else mx.Neg(resto))

    for e in terminos:
        a, resto = retardo_de(e)
        clave = mx.text(a)
        grupos.setdefault(clave, [a, []])[1].append(resto)
    out = []
    for a, restos in grupos.values():
        total = restos[0]
        for r in restos[1:]:
            total = mx.Add(total, r)
        out.append((a, _racional(total)))
    out.sort(key=lambda g: float(mx.valor_real(g[0], {})))
    _ = P
    return out


def _hojas(e):
    yield e
    for h in ("left", "right", "arg", "base", "exponent"):
        c = getattr(e, h, None)
        if isinstance(c, mx.Expr):
            yield from _hojas(c)


def _prod(fs):
    if not fs:
        return mx.Num(Fraction(1))
    r = fs[0]
    for f in fs[1:]:
        r = mx.Mul(r, f)
    return r


def _num_den(R: mx.Expr, s: str) -> tuple[list, list[Fraction]]:
    """R = num/den con den ∈ ℚ[s] y num con coeficientes constantes (expresión)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    R = _racional(R)
    if isinstance(R, mx.Div):
        n_e, d_e = R.left, R.right
    else:
        n_e, d_e = R, mx.Num(Fraction(1))
    den = _coefs(d_e, s)
    dq = _como_q(den)
    if dq is None:
        # factor constante común no racional en el denominador: se pasa al numerador
        lider = den[-1]
        den2 = [limpio(mx.Div(c, lider)) for c in den]
        dq = _como_q(den2)
        if dq is None:
            raise _no(f"el denominador {mx.text(d_e)} no tiene coeficientes racionales")
        n_e = mx.Div(n_e, lider)
    num = _coefs(n_e, s)
    _ = DM
    return num, dq


def _coefs(e: mx.Expr, s: str) -> list:
    """Coeficientes de e como polinomio en s (derivando en 0)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    out = []
    g = limpio(e)
    fact = 1
    for k in range(40):
        if not mx.depends(g, s):
            out.append(limpio(mx.Div(g, mx.Num(Fraction(fact)))))
            break
        out.append(limpio(mx.Div(mx.substitute(g, s, mx.Num(Fraction(0))), mx.Num(Fraction(fact)))))
        g = limpio(DM.differentiate(g, s))
        fact *= k + 1
    else:
        raise _no(f"«{mx.text(e)}» no es un polinomio en {s}")
    while len(out) > 1 and Q.es_cero(out[-1]):
        out.pop()
    # comprobación: el polinomio reconstruido coincide con e
    if _p_comprueba(out, e, s):
        return out
    raise _no(f"«{mx.text(e)}» no es un polinomio en {s}")


def _p_comprueba(p, e, s) -> bool:
    for x in (0.37, 1.91, -2.3):
        a = mx.valor_real(_p_expr(p, s), {s: x})
        b = mx.valor_real(e, {s: x})
        if a is None or b is None or abs(a - b) > 1e-9 * max(1.0, abs(b)):
            return False
    return True


def inversa(F: mx.Expr | str, s: str = S, t: str = "t", trace: Trace | None = None) -> Inversa:
    """L⁻¹{F} para F = Σ e^{−as}·R(s) con R racional (denominador en ℚ[s])."""
    trace = trace if trace is not None else Trace()
    if isinstance(F, str):
        F = mx.parse(mx.normaliza_entrada(F))
    piezas = []
    textos = []
    aproximada = False
    simbolicas: list = []
    definiciones: list = []
    for a, R in _separa_retardos(F, s):
        num, den = _num_den(R, s)
        try:
            entera, fs = simples(num, den)
        except UnsupportedError as exc:
            if "grado ≥ 3" not in str(exc):
                raise
            g, simb, defs, entera, aprox = inversa_racional(num, den)
            impulsos = [(k, c) for k, c in enumerate(entera) if not Q.es_cero(c)]
            piezas.append((a, g, impulsos))
            simbolicas.append(simb)
            definiciones.extend(defs)
            aproximada = aproximada or aprox
            if aprox:
                trace.aviso("laplace.numerica", f"{mx.text(R)}: factor irreducible de grado ≥ 4; "
                            "residuos en raíces numéricas")
            else:
                trace.regla("laplace.cardano", f"{mx.text(R)}: cúbica irreducible resuelta "
                            "exactamente (Cardano / forma trigonométrica); residuos "
                            "A = N(r)/P′(r) en cada raíz",
                            why="Bézout separa la cúbica del resto del denominador")
            textos.append("residuos exactos" if not aprox else "residuos numéricos")
            continue
        texto = " + ".join(
            [f"{mx.text(_p_expr([c]))}·s^{k}" for k, c in enumerate(entera) if not Q.es_cero(c)] +
            [f"({mx.text(_p_expr(f.A))})/({mx.text(_q_a_expr(f.q))})" + (f"^{f.k}" if f.k > 1 else "")
             for f in fs])
        textos.append(texto)
        trace.regla("laplace.simples", f"{mx.text(R)} = {texto}" + (
            "" if Q.es_cero(a) else f" (multiplicado por e^(−{mx.text(a)}s))"),
            why="factores irreducibles de ℚ[s] y coeficientes por un sistema lineal exacto")
        g: Q.Cuasi = []
        for f in fs:
            g = Q.suma(g, inversa_simple(f))
        impulsos = [(k, c) for k, c in enumerate(entera) if not Q.es_cero(c)]
        piezas.append((a, g, impulsos))
        simbolicas.append(None)
    r = Inversa(piezas, t, textos, aproximada, simbolicas, definiciones)
    trace.regla("laplace.inversa", r.texto(),
                why="tabla inversa: A/(s−r)ᵏ → A·t^(k−1)e^(rt)/(k−1)!; (B·s+C)/((s−p)²+ω²) → "
                    "e^(pt)[B cos ωt + (C+Bp)/ω·sen ωt]; e^(−as)·G(s) → u(t−a)·g(t−a)")
    _verifica_inversa(F, r, s, trace)
    return r


def _verifica_inversa(F: mx.Expr, r: Inversa, s: str, trace: Trace) -> None:
    """Se vuelve a transformar cada pieza y se compara con F en varios s."""
    total = None
    for a, cuasi, imp in r.piezas:
        for term in cuasi:
            fr = transformada_termino(term)
            e = Fraccion(a, fr.num, fr.den).expr()
            total = e if total is None else mx.Add(total, e)
        for k, c in imp:
            e = mx.Mul(c, mx.Pow(mx.Sym(S), mx.Num(Fraction(k))))
            if not Q.es_cero(a):
                e = mx.Mul(e, mx.Call("exp", (limpio(mx.Neg(mx.Mul(a, mx.Sym(S)))),)))
            total = e if total is None else mx.Add(total, e)
    G = total if total is not None else mx.Num(Fraction(0))
    if s != S:
        G = mx.substitute(G, S, mx.Sym(s))
    peor = 0.0
    for x in (2.3, 3.7, 5.9, 8.1):
        a = mx.valor_real(G, {s: x})
        b = mx.valor_real(F, {s: x})
        if a is None or b is None:
            raise _error("DISCREPANT", "la inversa no se puede volver a transformar")
        peor = max(peor, abs(a - b) / max(1.0, abs(b)))
    if peor > (1e-7 if r.aproximada else 1e-9):
        raise _error("DISCREPANT", f"L{{f}} ≠ F (desviación {peor:.3g})")
    trace.verificacion("laplace.ida_vuelta", f"L{{f}} vuelve a dar F(s) en 4 valores de s "
                       f"(desviación {peor:.2g})", why="la directa de la inversa, por la tabla")
