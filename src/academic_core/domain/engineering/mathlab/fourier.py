# SPDX-License-Identifier: MIT
"""ML-8 (§4.5): series y transformada de Fourier exactas.

Serie de una función T-periódica dada a trozos en un periodo [a, a + T) (cada trozo
un cuasipolinomio): ω₀ = 2π/T,

    a₀ = (2/T)∫f,  aₙ = (2/T)∫f·cos(nω₀t),  bₙ = (2/T)∫f·sen(nω₀t),
    f ~ a₀/2 + Σ (aₙ cos nω₀t + bₙ sen nω₀t),   cₙ = (aₙ − i·bₙ)/2.

Las integrales son exactas con n simbólico (primitivas de cuasipolinomios) y se
simplifican con n entero: sen(kπn + d) = (−1)^{kn}·sen d, cos(kπn + d) = (−1)^{kn}·cos d.
Los n en los que la fórmula general divide entre cero (resonancia de una
componente de f con nω₀) se calculan aparte. Parseval:
(2/T)∫f² = a₀²/2 + Σ(aₙ² + bₙ²). Suma por evaluación: la serie en t₀ vale la media
de los límites laterales de la extensión periódica (Dirichlet).

Transformada (convenio de frecuencia ordinaria, Señales y Sistemas):
X(f) = ∫x(t)·e^{−i2πft}dt = ∫x·cos(2πft) − i∫x·sen(2πft), por tramos (los
infinitos tienen que decaer), con deltas A·δ(t − t₀) → A·e^{−i2πft₀} y la
gaussiana e^{−at²} → √(π/a)·e^{−π²f²/a}.

Comprobación: coeficientes y transformada frente a cuadratura numérica en varios
n o f; Parseval de la serie frente a sumas parciales.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

limpio = Q.limpio
N = "n"


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _bonito(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import multiple as MI

    e = Q.pliega(e)
    try:
        r = Q.pliega(MI._limpio(e))
        r = MI._limpio(r)
    except Exception:  # noqa: BLE001
        r = limpio(e)
    return cancela(r)


def _quita_abs(e: mx.Expr, lo: mx.Expr, hi: mx.Expr) -> list[tuple[mx.Expr, mx.Expr, mx.Expr]]:
    """|u(t)| con u lineal: se trocea en el cero de u y se quita el valor absoluto."""
    abs_args = []

    def busca(n):
        if isinstance(n, mx.Call) and n.name == "abs":
            abs_args.append(n.args[0])
        for h in ("left", "right", "arg", "base", "exponent"):
            c = getattr(n, h, None)
            if isinstance(c, mx.Expr):
                busca(c)
        for a in getattr(n, "args", ()) or ():
            if isinstance(a, mx.Expr):
                busca(a)
    busca(e)
    if not abs_args:
        return [(e, lo, hi)]
    u = abs_args[0]
    lin = Q._lineal(u, "t")
    if lin is None or Q.es_cero(lin[0]):
        raise _no(f"|{mx.text(u)}| con argumento no lineal: dalo a trozos")
    cero = limpio(mx.Div(mx.Neg(lin[1]), lin[0]))
    lv, hv, cv = (float(mx.valor_real(x, {})) for x in (lo, hi, cero))
    cortes = [lo] + ([cero] if lv < cv < hv else []) + [hi]
    out = []
    for a, b in zip(cortes, cortes[1:]):
        medio = (float(mx.valor_real(a, {})) + float(mx.valor_real(b, {}))) / 2
        signo = 1 if mx.valor_real(u, {"t": medio}) >= 0 else -1
        sin_abs = _reemplaza_abs(e, u, signo)
        out.extend(_quita_abs(sin_abs, a, b))
    return out


def _reemplaza_abs(e, u, signo):
    if isinstance(e, mx.Call) and e.name == "abs" and mx.text(e.args[0]) == mx.text(u):
        return u if signo > 0 else mx.Neg(u)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_reemplaza_abs(e.left, u, signo), _reemplaza_abs(e.right, u, signo))
    if isinstance(e, mx.Neg):
        return mx.Neg(_reemplaza_abs(e.arg, u, signo))
    if isinstance(e, mx.Pow):
        return mx.Pow(_reemplaza_abs(e.base, u, signo), _reemplaza_abs(e.exponent, u, signo))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_reemplaza_abs(a, u, signo) for a in e.args))
    return e


def cancela(e: mx.Expr) -> mx.Expr:
    """N/D con factores comunes en varias variables (n, (−1)ⁿ, π…) cancelados por mcd
    de polinomios (bases de Gröbner); se acepta solo si sigue valiendo lo mismo."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import sistemas as S

    try:
        R = MI._racional(e)
    except Exception:  # noqa: BLE001
        return e
    if not isinstance(R, mx.Div):
        return e
    sust: dict[str, mx.Expr] = {}

    def atomiza(n):
        if isinstance(n, mx.Pow) and n.base == mx.Num(Fraction(-1)) or (
                isinstance(n, mx.Pow) and isinstance(n.base, mx.Neg) and
                n.base.arg == mx.Num(Fraction(1))):
            clave = f"S{len(sust)}__"
            for k, v in sust.items():
                if mx.text(v) == mx.text(n):
                    return mx.Sym(k)
            sust[clave] = n
            return mx.Sym(clave)
        if isinstance(n, mx.Const) or isinstance(n, mx.Call):
            for k, v in sust.items():
                if mx.text(v) == mx.text(n):
                    return mx.Sym(k)
            clave = f"K{len(sust)}__"
            sust[clave] = n
            return mx.Sym(clave)
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(n)(atomiza(n.left), atomiza(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(atomiza(n.arg))
        if isinstance(n, mx.Pow):
            return mx.Pow(atomiza(n.base), n.exponent)
        return n
    try:
        num, den = atomiza(R.left), atomiza(R.right)
        vs = sorted(mx.variables(num) | mx.variables(den))
        if not vs:
            return e
        pn = S._a_exp(S.a_polinomio(num, vs, Trace()), vs)
        pd = S._a_exp(S.a_polinomio(den, vs, Trace()), vs)
        g = S.mcd(pn, pd)
        if len(g) == 1 and all(x == 0 for x in next(iter(g))):
            qn, qd = pn, pd
        else:
            qn, qd = S.divide_exacto(pn, g), S.divide_exacto(pd, g)
            if qn is None or qd is None:
                return e
        # contenido numérico: coeficientes enteros primos entre sí, denominador «positivo»
        coefs = list(qn.values()) + list(qd.values())
        mcm = math.lcm(*[c.denominator for c in coefs])
        mcd_ = math.gcd(*[int(c * mcm) for c in coefs if c])
        escala_ = Fraction(mcm, mcd_ or 1)
        lider = qd[max(qd, key=lambda ex: (sum(ex), ex))]
        if lider < 0:
            escala_ = -escala_
        qn = {k: v * escala_ for k, v in qn.items()}
        qd = {k: v * escala_ for k, v in qd.items()}

        def a_expr(p):
            return P.to_expr({tuple((v, k) for v, k in zip(vs, ex) if k): c
                              for ex, c in p.items()}) if p else mx.Num(Fraction(0))
        r = mx.Div(a_expr(qn), a_expr(qd))
        for k, v in sust.items():
            r = mx.substitute(r, k, v)
        r = MI._limpio(r)
    except Exception:  # noqa: BLE001
        return e
    from academic_core.domain.engineering.mathlab import verify as V

    vs_orig = sorted(mx.variables(e))
    for x in (2.0, 3.0, 5.0):
        env = {v: x for v in vs_orig}
        a, b = mx.valor_real(e, env), mx.valor_real(r, env)
        if a is None or b is None or abs(a - b) > 1e-9 * max(1.0, abs(a)):
            return e
    _ = V
    return r if len(mx.text(r)) <= len(mx.text(e)) else e


def n_entero(e: mx.Expr, n: str = N) -> mx.Expr:
    """sen/cos(q·π·n + d) con q entero → (−1)^{qn}·sen/cos d."""
    if isinstance(e, mx.Call) and e.name in ("sin", "cos") and len(e.args) == 1:
        arg = n_entero(e.args[0], n)
        lin = Q._lineal(arg, n) if mx.depends(arg, n) else None
        if lin is not None:
            m, d = lin
            q = None
            mv = mx.valor_real(m, {}) if not mx.variables(m) else None
            if mv is not None:
                qq = Fraction(mv / math.pi).limit_denominator(1000)
                if abs(float(qq) * math.pi - mv) < 1e-12 * max(1.0, abs(mv)):
                    q = qq
            if q is not None and Fraction(q).denominator == 1:
                q = int(q)
                base = limpio(mx.Call(e.name, (d,)))
                if q % 2 == 0:
                    return base
                return limpio(mx.Mul(mx.Pow(mx.Num(Fraction(-1)), mx.Sym(n)), base))
        return mx.Call(e.name, (arg,))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(n_entero(e.left, n), n_entero(e.right, n))
    if isinstance(e, mx.Neg):
        return mx.Neg(n_entero(e.arg, n))
    if isinstance(e, mx.Pow):
        return mx.Pow(n_entero(e.base, n), n_entero(e.exponent, n))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(n_entero(a, n) for a in e.args))
    return e


def _lee_tramos(tramos, t: str) -> list[tuple[mx.Expr, mx.Expr, mx.Expr]]:
    out = []
    for item in tramos:
        if len(item) != 3:
            raise _error("BAD_INPUT", "cada trozo es [expresión, desde, hasta]")
        e = mx.parse(mx.normaliza_entrada(str(item[0])))
        a = mx.parse(mx.normaliza_entrada(str(item[1])))
        b = mx.parse(mx.normaliza_entrada(str(item[2])))
        if t != "t":
            e = mx.substitute(e, t, mx.Sym("t"))
        out.extend(_quita_abs(e, a, b))
    return out


def _integra(e: mx.Expr, a: mx.Expr, b: mx.Expr | None, peso: mx.Expr | None) -> mx.Expr:
    g = Q.leer(e, "t")
    if peso is not None:
        g = Q.producto(g, Q.leer(peso, "t"))
    return Q.integral_definida(g, a, b, "t")


@dataclass
class Serie:
    T: mx.Expr
    a0: mx.Expr
    an: mx.Expr
    bn: mx.Expr
    especiales: dict           # n → (aₙ, bₙ) donde la fórmula general no vale
    parseval: mx.Expr          # Σ(aₙ² + bₙ²) exacto
    t: str = "t"

    def omega0(self) -> mx.Expr:
        return _bonito(mx.Div(mx.Mul(mx.Num(2), mx.Const("pi")), self.T))

    def texto(self) -> str:
        w = mx.text(self.omega0())
        t = (f"T = {mx.text(self.T)}, ω₀ = {w}; a₀ = {mx.text(self.a0)}; "
             f"aₙ = {mx.text(self.an)}; bₙ = {mx.text(self.bn)}")
        if self.especiales:
            t += "; " + "; ".join(f"n = {k}: a = {mx.text(a)}, b = {mx.text(b)}"
                                  for k, (a, b) in sorted(self.especiales.items()))
        arg = f"n·{self.t}" if w == "1" else f"n·{w}·{self.t}"
        t += (f"; f ~ a₀/2 + Σ (aₙ·cos({arg}) + bₙ·sen({arg})); "
              f"Parseval: Σ(aₙ² + bₙ²) = {mx.text(self.parseval)}")
        return t


def serie(tramos, t: str = "t", trace: Trace | None = None) -> Serie:
    trace = trace if trace is not None else Trace()
    piezas = _lee_tramos(tramos, t)
    a = piezas[0][1]
    b = piezas[-1][2]
    T = _bonito(mx.Sub(b, a))
    if (mx.valor_real(T, {}) or 0) <= 0:
        raise _error("BAD_INPUT", "el periodo tiene que ser positivo")
    for (_, _, hi), (_, lo, _) in zip(piezas, piezas[1:]):
        if not Q.es_cero(limpio(mx.Sub(hi, lo))):
            raise _error("BAD_INPUT", "los trozos tienen que cubrir el periodo sin huecos")
    w0 = _bonito(mx.Div(mx.Mul(mx.Num(2), mx.Const("pi")), T))
    nw = limpio(mx.Mul(mx.Sym(N), mx.Mul(w0, mx.Sym("t"))))
    dosT = limpio(mx.Div(mx.Num(2), T))
    trace.regla("fourier.periodo", f"T = {mx.text(T)}, ω₀ = 2π/T = {mx.text(w0)}",
                why="la serie usa las frecuencias n·ω₀")
    a0 = _bonito(mx.Mul(dosT, _suma([_integra(e, lo, hi, None) for e, lo, hi in piezas])))
    an_raw = mx.Mul(dosT, _suma([_integra(e, lo, hi, mx.Call("cos", (nw,)))
                                 for e, lo, hi in piezas]))
    bn_raw = mx.Mul(dosT, _suma([_integra(e, lo, hi, mx.Call("sin", (nw,)))
                                 for e, lo, hi in piezas]))
    an = _bonito(n_entero(Q.pliega(_bonito(an_raw))))
    bn = _bonito(n_entero(Q.pliega(_bonito(bn_raw))))
    trace.regla("fourier.coeficientes", f"a₀ = {mx.text(a0)}; aₙ = {mx.text(an)}; "
                f"bₙ = {mx.text(bn)}",
                why="integrales exactas por trozos con n entero: sen(kπn) = 0, cos(kπn) = (−1)^(kn)")
    # n especiales: donde la fórmula general no es evaluable
    especiales = {}
    for k in range(1, 13):
        va = mx.valor_real(an, {N: k})
        vb = mx.valor_real(bn, {N: k})
        if va is None or vb is None or not math.isfinite(va) or not math.isfinite(vb):
            kk = mx.Num(Fraction(k))
            wk = limpio(mx.Mul(kk, mx.Mul(w0, mx.Sym("t"))))
            ak = _bonito(mx.Mul(dosT, _suma([_integra(e, lo, hi, mx.Call("cos", (wk,)))
                                             for e, lo, hi in piezas])))
            bk = _bonito(mx.Mul(dosT, _suma([_integra(e, lo, hi, mx.Call("sin", (wk,)))
                                             for e, lo, hi in piezas])))
            especiales[k] = (ak, bk)
    if especiales:
        trace.regla("fourier.especiales", "; ".join(
            f"n = {k}: a = {mx.text(a)}, b = {mx.text(b)}" for k, (a, b) in especiales.items()),
            why="la fórmula general divide entre cero en esos n (resonancia con una "
                "componente de f): se integran aparte")
    energia = _bonito(mx.Mul(dosT, _suma([_integra(mx.Mul(e, e), lo, hi, None)
                                          for e, lo, hi in piezas])))
    parseval = _bonito(mx.Sub(energia, mx.Div(mx.Pow(a0, mx.Num(2)), mx.Num(2))))
    trace.regla("fourier.parseval", f"(2/T)∫f² = {mx.text(energia)} = a₀²/2 + Σ(aₙ² + bₙ²) ⇒ "
                f"Σ(aₙ² + bₙ²) = {mx.text(parseval)}", why="identidad de Parseval")
    s = Serie(T, a0, an, bn, especiales, parseval, t)
    _verifica_serie(piezas, s, trace)
    return s


def _suma(es):
    total = es[0]
    for e in es[1:]:
        total = mx.Add(total, e)
    return total


def _f_periodica(piezas, x: float, T: float, a: float) -> float:
    y = a + ((x - a) % T)
    for e, lo, hi in piezas:
        lv, hv = float(mx.valor_real(lo, {})), float(mx.valor_real(hi, {}))
        if lv <= y < hv:
            return float(mx.valor_real(e, {"t": y}))
    return 0.0


def _verifica_serie(piezas, s: Serie, trace: Trace) -> None:
    from academic_core.domain.engineering.mathlab import laplace as LP

    T = float(mx.valor_real(s.T, {}))
    w0 = 2 * math.pi / T
    peor = 0.0
    for k in range(1, 7):
        num_a = num_b = 0.0
        for e, lo, hi in piezas:
            lv, hv = float(mx.valor_real(lo, {})), float(mx.valor_real(hi, {}))
            num_a += LP._cuadratura(lambda x, e=e: float(mx.valor_real(e, {"t": x})) *
                                    math.cos(k * w0 * x), lv, hv)
            num_b += LP._cuadratura(lambda x, e=e: float(mx.valor_real(e, {"t": x})) *
                                    math.sin(k * w0 * x), lv, hv)
        num_a *= 2 / T
        num_b *= 2 / T
        if k in s.especiales:
            ea, eb = (float(mx.valor_real(v, {})) for v in s.especiales[k])
        else:
            ea = float(mx.valor_real(s.an, {N: k}))
            eb = float(mx.valor_real(s.bn, {N: k}))
        peor = max(peor, abs(ea - num_a), abs(eb - num_b))
    if peor > 1e-8:
        raise _error("DISCREPANT", f"coeficientes frente a cuadratura: desviación {peor:.3g}")
    trace.verificacion("fourier.cuadratura", f"a₁…a₆ y b₁…b₆ frente a cuadratura numérica "
                       f"(desviación {peor:.2g})", why="las mismas integrales por otro camino")


def suma_en(s: Serie, t0, trace: Trace | None = None, piezas=None) -> str:
    """La serie evaluada en t₀: a₀/2 + Σ(aₙcos nω₀t₀ + bₙsen nω₀t₀) = valor de Dirichlet."""
    trace = trace if trace is not None else Trace()
    t0e = mx.parse(mx.normaliza_entrada(str(t0)))
    arg = limpio(mx.Mul(mx.Sym(N), mx.Mul(s.omega0(), t0e)))
    termino = _bonito(n_entero(_bonito(mx.Add(mx.Mul(s.an, mx.Call("cos", (arg,))),
                                              mx.Mul(s.bn, mx.Call("sin", (arg,)))))))
    texto = f"a₀/2 + Σₙ {mx.text(termino)}"
    if piezas is not None:
        T = float(mx.valor_real(s.T, {}))
        a = float(mx.valor_real(piezas[0][1], {}))
        x = float(mx.valor_real(t0e, {}))
        izq = _f_periodica(piezas, x - 1e-12, T, a)
        der = _f_periodica(piezas, x + 1e-12, T, a)
        texto += f" = (f(t₀⁻) + f(t₀⁺))/2 ≈ {(izq + der) / 2:.12g}"
    trace.regla("fourier.evaluacion", texto, why="Dirichlet: la serie converge a la media de "
                                                 "los límites laterales")
    return texto


# ---------------------------------------------------------------------------
# transformada de Fourier (frecuencia ordinaria f)
# ---------------------------------------------------------------------------


@dataclass
class TransformadaF:
    re: mx.Expr
    im: mx.Expr
    energia: mx.Expr | None

    def texto(self) -> str:
        r, i = mx.text(self.re), mx.text(self.im)
        if Q.es_cero(self.im) if not mx.variables(self.im) else False:
            cuerpo = r
        elif Q.es_cero(self.re) if not mx.variables(self.re) else False:
            cuerpo = f"i·({i})"
        else:
            cuerpo = f"{r} + i·({i})"
        t = f"X(f) = {cuerpo}"
        if self.energia is not None:
            t += f"; energía ∫|x|²dt = {mx.text(self.energia)} = ∫|X(f)|²df (Parseval)"
        return t


def transformada(texto: str, t: str = "t", trace: Trace | None = None) -> TransformadaF:
    from academic_core.domain.engineering.mathlab import laplace as LP

    trace = trace if trace is not None else Trace()
    primas = "'" in texto or "′" in texto
    e0 = None if primas else mx.parse(LP.prepara(texto, t))
    gauss = _gaussiana(e0, t) if e0 is not None else None
    if gauss is not None:
        A, a = gauss
        X = _bonito(mx.Mul(A, mx.Mul(mx.Root(2, mx.Div(mx.Const("pi"), a)),
                                     mx.Call("exp", (mx.Neg(mx.Div(
                                         mx.Mul(mx.Pow(mx.Const("pi"), mx.Num(2)),
                                                mx.Pow(mx.Sym("f"), mx.Num(2))), a)),)))))
        trace.regla("fourier.gaussiana", f"x = A·e^(−a{t}²) → X(f) = A·√(π/a)·e^(−π²f²/a)",
                    why="tabla (se comprueba por cuadratura)")
        r = TransformadaF(X, mx.Num(Fraction(0)), None)
        _verifica_tf(lambda x: float(mx.valor_real(e0, {t: x})), r, trace, (-40.0, 40.0, []))
        return r
    if e0 is not None:
        texto = _abs_a_escalones(e0, t) or texto
    D = LP._lee_senal(texto, t, trace)
    w = mx.Mul(mx.Mul(mx.Num(2), mx.Const("pi")), mx.Mul(mx.Sym("f"), mx.Sym("t")))
    re_parts, im_parts, energia = [], [], []
    for tramo in D.tramos:
        if Q.es_cero(tramo.expr) if not mx.variables(tramo.expr) else False:
            continue
        g = mx.substitute(tramo.expr, t, mx.Sym("t")) if t != "t" else tramo.expr
        lo = tramo.desde.expr if tramo.desde is not None else None
        hi = tramo.hasta.expr if tramo.hasta is not None else None
        re_parts.append(_integral_recta(g, lo, hi, mx.Call("cos", (w,))))
        im_parts.append(mx.Neg(_integral_recta(g, lo, hi, mx.Call("sin", (w,)))))
        energia.append(_integral_recta(mx.Mul(g, g), lo, hi, None))
    for imp in D.impulsos:
        # A·δ⁽ᵏ⁾(t − t₀) → A·(i2πf)ᵏ·e^{−i2πft₀}
        ang = limpio(mx.Mul(mx.Mul(mx.Num(2), mx.Const("pi")), mx.Mul(mx.Sym("f"),
                                                                       imp.posicion.expr)))
        k = imp.orden
        mag = mx.Mul(imp.area, mx.Pow(mx.Mul(mx.Mul(mx.Num(2), mx.Const("pi")), mx.Sym("f")),
                                      mx.Num(Fraction(k)))) if k else imp.area
        c, s_ = mx.Call("cos", (ang,)), mx.Call("sin", (ang,))
        # iᵏ·(cos − i·sen): k = 0: (c, −s); 1: (s, c); 2: (−c, s); 3: (−s, −c)
        re_, im_ = [(c, mx.Neg(s_)), (s_, c), (mx.Neg(c), s_), (mx.Neg(s_), mx.Neg(c))][k % 4]
        re_parts.append(mx.Mul(mag, re_))
        im_parts.append(mx.Mul(mag, im_))
        if k:
            trace.regla("fourier.delta_derivada", f"δ{'′' * k}(t − t₀) → (i2πf)^{k}·e^(−i2πft₀)",
                        why="propiedad de derivación: F{x′} = i2πf·X(f)")
    zero = mx.Num(Fraction(0))
    r = TransformadaF(_bonito(_suma(re_parts)) if re_parts else zero,
                      _bonito(_suma(im_parts)) if im_parts else zero,
                      _bonito(_suma(energia)) if energia and not D.impulsos else None)
    trace.regla("fourier.transformada", r.texto(),
                why="X(f) = ∫x(t)cos(2πft)dt − i∫x(t)sen(2πft)dt, exacto por tramos")
    _verifica_tf(lambda x: LP.valor_senal(D, x), r, trace, _soporte(D), D.impulsos)
    return r


def _abs_a_escalones(e: mx.Expr, t: str) -> str | None:
    """|u(t)| con u lineal → g₊(t)·u(t − c) + g₋(t)·u(c − t) (texto para las distribuciones)."""
    abs_args = []

    def busca(n):
        if isinstance(n, mx.Call) and n.name == "abs" and mx.depends(n.args[0], t):
            abs_args.append(n.args[0])
        for h in ("left", "right", "arg", "base", "exponent"):
            c = getattr(n, h, None)
            if isinstance(c, mx.Expr):
                busca(c)
        for a in getattr(n, "args", ()) or ():
            if isinstance(a, mx.Expr):
                busca(a)
    busca(e)
    if not abs_args:
        return None
    u = abs_args[0]
    lin = Q._lineal(u, t)
    if lin is None or Q.es_cero(lin[0]):
        raise _no(f"|{mx.text(u)}| con argumento no lineal")
    c = limpio(mx.Div(mx.Neg(lin[1]), lin[0]))
    creciente = (mx.valor_real(lin[0], {}) or 0) > 0
    mas = Q.pliega(_reemplaza_abs(e, u, 1 if creciente else -1))
    menos = Q.pliega(_reemplaza_abs(e, u, -1 if creciente else 1))
    ct = mx.text(c)
    return (f"({mx.text(mas)})*heaviside({t} - ({ct})) + "
            f"({mx.text(menos)})*heaviside(({ct}) - {t})")


def _gaussiana(e: mx.Expr, t: str):
    """A·e^{−a·t²} con a > 0."""
    from academic_core.domain.engineering.mathlab import poly as P

    A = mx.Num(Fraction(1))
    base = e
    if isinstance(e, mx.Mul) and not mx.depends(e.left, t):
        A, base = e.left, e.right
    arg = None
    if isinstance(base, mx.Call) and base.name == "exp":
        arg = base.args[0]
    elif isinstance(base, mx.Pow) and base.base == mx.Const("e"):
        arg = base.exponent
    if arg is None:
        return None
    try:
        p = P.as_poly(limpio(arg))
    except Exception:  # noqa: BLE001
        return None
    if set(p) != {((t, 2),)}:
        return None
    a = -p[((t, 2),)]
    if a <= 0:
        return None
    return A, Q.num(a)


def _integral_recta(g, lo, hi, peso):
    """∫_lo^hi g·peso con extremos ±∞ (cambio t → −t para −∞)."""
    if lo is None and hi is None:
        cero = mx.Num(Fraction(0))
        return mx.Add(_integral_recta(g, None, cero, peso), _integral_recta(g, cero, None, peso))
    if lo is None:
        gm = mx.substitute(g, "t", mx.Neg(mx.Sym("t")))
        pm = mx.substitute(peso, "t", mx.Neg(mx.Sym("t"))) if peso is not None else None
        return _integra(gm, limpio(mx.Neg(hi)), None, pm)
    return _integra(g, lo, hi, peso)


def _soporte(D) -> tuple[float, float]:
    xs = [p.x for tr in D.tramos for p in (tr.desde, tr.hasta) if p is not None]
    lo = min(xs) if xs else 0.0
    hi = max(xs) if xs else 0.0
    if any(tr.desde is None for tr in D.tramos):
        lo = lo - 60.0
    if any(tr.hasta is None for tr in D.tramos):
        hi = hi + 60.0
    return lo, hi, xs


def _verifica_tf(x, r: TransformadaF, trace: Trace, soporte, impulsos=()) -> None:
    from academic_core.domain.engineering.mathlab import laplace as LP

    lo, hi = soporte[0], soporte[1]
    cortes = sorted(set([lo, hi] + [c for c in (soporte[2] if len(soporte) > 2 else [])
                                    if lo < c < hi]))
    tramos_num = []
    for a, b in zip(cortes, cortes[1:]):
        k = max(1, int((b - a) / 4))
        tramos_num.extend((a + (b - a) * j / k, a + (b - a) * (j + 1) / k) for j in range(k))
    peor = 0.0
    for fv in (0.13, 0.41, 0.77):
        re_n = im_n = 0.0
        for a, b in tramos_num:
            re_n += LP._cuadratura(lambda u: x(u) * math.cos(2 * math.pi * fv * u), a, b)
            im_n -= LP._cuadratura(lambda u: x(u) * math.sin(2 * math.pi * fv * u), a, b)
        for imp in impulsos:
            A = float(mx.valor_real(imp.area, {}))
            z = A * (2j * math.pi * fv) ** imp.orden * complex(
                math.cos(2 * math.pi * fv * imp.posicion.x), -math.sin(2 * math.pi * fv * imp.posicion.x))
            re_n += z.real
            im_n += z.imag
        re_e = mx.valor_real(r.re, {"f": fv})
        im_e = mx.valor_real(r.im, {"f": fv})
        if re_e is None or im_e is None:
            raise _error("DISCREPANT", "la transformada no se puede evaluar")
        peor = max(peor, abs(re_e - re_n), abs(im_e - im_n))
    if peor > 1e-6:
        raise _error("DISCREPANT", f"X(f) frente a la cuadratura: desviación {peor:.3g}")
    trace.verificacion("fourier.tf_cuadratura", f"X(f) frente a ∫x(t)e^(−i2πft)dt por "
                       f"cuadratura en 3 frecuencias (desviación {peor:.2g})",
                       why="la definición calculada por otro camino")
