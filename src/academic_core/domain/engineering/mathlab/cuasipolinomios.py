# SPDX-License-Identifier: MIT
"""ML-8: cuasipolinomios — sumas finitas de c·tⁿ·e^{αt}·{1, cos βt, sen βt}.

Es la clase de funciones que cierran las EDO lineales de coeficientes constantes y
la transformada de Laplace de las tablas: cualquier producto, potencia entera,
desplazamiento ``t → t + a`` o derivada de cuasipolinomios es otro cuasipolinomio,
y su transformada es racional en s. Aquí se leen desde una expresión (con
sen/cos/senh/cosh/exp de argumentos lineales en t), se multiplican (producto a
suma en las trigonométricas), se desplazan y se vuelven a escribir.

Todo es exacto: los coeficientes y los α, β son expresiones constantes de
:mod:`mvexpr` (racionales, √, π…), simplificadas en cada paso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import limite as LM

    return LM._limpio(e)


def es_cero(e: mx.Expr) -> bool:
    v = mx.exact_value(e)
    if v is not None:
        return v == 0
    w = mx.valor_real(e, {})
    return w is not None and abs(w) < 1e-14 and mx.exact_value(limpio(e)) == 0


def num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


@dataclass(frozen=True)
class Termino:
    """c·tⁿ·e^{αt}·f(βt) con f ∈ {1, cos, sin} y β > 0 cuando f no es 1."""

    coef: mx.Expr
    n: int
    alfa: mx.Expr
    tipo: str          # "1", "cos" o "sin"
    beta: mx.Expr

    def clave(self) -> tuple:
        return (self.n, mx.text(self.alfa), self.tipo, mx.text(self.beta))


Cuasi = list  # list[Termino]


def _cero() -> mx.Expr:
    return mx.Num(Fraction(0))


def _uno() -> mx.Expr:
    return mx.Num(Fraction(1))


def normaliza(ts: Cuasi) -> Cuasi:
    """Agrupa términos semejantes y quita los nulos."""
    acum: dict[tuple, Termino] = {}
    orden: list[tuple] = []
    for t in ts:
        if t.tipo != "1" and es_cero(t.beta):
            if t.tipo == "sin":
                continue
            t = Termino(t.coef, t.n, t.alfa, "1", _cero())
        if t.tipo != "1":
            b = mx.valor_real(t.beta, {})
            if b is not None and b < 0:     # sen(−x) = −sen x, cos(−x) = cos x
                beta = limpio(mx.Neg(t.beta))
                coef = limpio(mx.Neg(t.coef)) if t.tipo == "sin" else t.coef
                t = Termino(coef, t.n, t.alfa, t.tipo, beta)
        k = t.clave()
        if k in acum:
            prev = acum[k]
            acum[k] = Termino(limpio(mx.Add(prev.coef, t.coef)), t.n, t.alfa, t.tipo, t.beta)
        else:
            acum[k] = Termino(limpio(t.coef), t.n, limpio(t.alfa), t.tipo, limpio(t.beta))
            orden.append(k)
    return [acum[k] for k in orden if not es_cero(acum[k].coef)]


def constante(c: mx.Expr) -> Cuasi:
    return normaliza([Termino(c, 0, _cero(), "1", _cero())])


def suma(a: Cuasi, b: Cuasi) -> Cuasi:
    return normaliza(list(a) + list(b))


def escala(a: Cuasi, c: mx.Expr) -> Cuasi:
    return normaliza([Termino(limpio(mx.Mul(c, t.coef)), t.n, t.alfa, t.tipo, t.beta) for t in a])


def _producto_termino(x: Termino, y: Termino) -> list[Termino]:
    c = limpio(mx.Mul(x.coef, y.coef))
    n = x.n + y.n
    al = limpio(mx.Add(x.alfa, y.alfa))
    if x.tipo == "1":
        return [Termino(c, n, al, y.tipo, y.beta)]
    if y.tipo == "1":
        return [Termino(c, n, al, x.tipo, x.beta)]
    medio = limpio(mx.Div(c, mx.Num(Fraction(2))))
    dif = limpio(mx.Sub(x.beta, y.beta))
    sm = limpio(mx.Add(x.beta, y.beta))
    menos = limpio(mx.Neg(medio))
    if x.tipo == "cos" and y.tipo == "cos":      # cos A cos B = ½[cos(A−B) + cos(A+B)]
        return [Termino(medio, n, al, "cos", dif), Termino(medio, n, al, "cos", sm)]
    if x.tipo == "sin" and y.tipo == "sin":      # sen A sen B = ½[cos(A−B) − cos(A+B)]
        return [Termino(medio, n, al, "cos", dif), Termino(menos, n, al, "cos", sm)]
    if x.tipo == "sin":                          # sen A cos B = ½[sen(A+B) + sen(A−B)]
        return [Termino(medio, n, al, "sin", sm), Termino(medio, n, al, "sin", dif)]
    # cos A sen B = ½[sen(A+B) − sen(A−B)]
    return [Termino(medio, n, al, "sin", sm), Termino(menos, n, al, "sin", dif)]


def producto(a: Cuasi, b: Cuasi) -> Cuasi:
    out: list[Termino] = []
    for x in a:
        for y in b:
            out.extend(_producto_termino(x, y))
    if len(out) > 400:
        raise _no("el producto de cuasipolinomios crece demasiado")
    return normaliza(out)


def _lineal(e: mx.Expr, t: str) -> tuple[mx.Expr, mx.Expr] | None:
    """e = m·t + c con m, c constantes."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    try:
        m = limpio(DM.differentiate(e, t))
    except Exception:  # noqa: BLE001
        return None
    if mx.depends(m, t):
        return None
    c = limpio(mx.substitute(e, t, _cero()))
    if mx.depends(c, t):
        return None
    return m, c


def leer(e: mx.Expr, t: str = "t") -> Cuasi:
    """La expresión como cuasipolinomio en t; UNSUPPORTED si no lo es."""
    if not mx.depends(e, t):
        return constante(e)
    if isinstance(e, mx.Sym):
        return [Termino(_uno(), 1, _cero(), "1", _cero())]
    if isinstance(e, mx.Add):
        return suma(leer(e.left, t), leer(e.right, t))
    if isinstance(e, mx.Sub):
        return suma(leer(e.left, t), escala(leer(e.right, t), mx.Num(Fraction(-1))))
    if isinstance(e, mx.Neg):
        return escala(leer(e.arg, t), mx.Num(Fraction(-1)))
    if isinstance(e, mx.Mul):
        return producto(leer(e.left, t), leer(e.right, t))
    if isinstance(e, mx.Div):
        if mx.depends(e.right, t):
            raise _no(f"«{mx.text(e)}» divide entre algo que depende de {t}")
        return escala(leer(e.left, t), limpio(mx.Div(_uno(), e.right)))
    if isinstance(e, mx.Pow):
        if not mx.depends(e.exponent, t):
            k = mx.exact_value(e.exponent)
            if k is None or Fraction(k).denominator != 1 or k < 0:
                raise _no(f"«{mx.text(e)}»: potencia no entera positiva de algo que depende "
                          f"de {t}")
            base = leer(e.base, t)
            out = constante(_uno())
            for _ in range(int(k)):
                out = producto(out, base)
            return out
        if mx.depends(e.base, t):
            raise _no(f"«{mx.text(e)}»: base y exponente dependen de {t}")
        lin = _lineal(e.exponent, t)
        if lin is None:
            raise _no(f"«{mx.text(e)}»: exponente no lineal en {t}")
        m, c = lin
        lnb = limpio(mx.Call("ln", (e.base,))) if e.base != mx.Const("e") else _uno()
        return [Termino(limpio(mx.Pow(e.base, c)), 0, limpio(mx.Mul(m, lnb)), "1", _cero())]
    if isinstance(e, mx.Call) and len(e.args) == 1:
        lin = _lineal(e.args[0], t)
        if lin is None:
            raise _no(f"«{mx.text(e)}»: argumento no lineal en {t}")
        m, c = lin
        cc, sc = limpio(mx.Call("cos", (c,))), limpio(mx.Call("sin", (c,)))
        if e.name == "exp":
            return [Termino(limpio(mx.Call("exp", (c,))), 0, m, "1", _cero())]
        if e.name == "sin":     # sen(mt + c) = sen mt·cos c + cos mt·sen c
            return normaliza([Termino(cc, 0, _cero(), "sin", m), Termino(sc, 0, _cero(), "cos", m)])
        if e.name == "cos":     # cos(mt + c) = cos mt·cos c − sen mt·sen c
            return normaliza([Termino(cc, 0, _cero(), "cos", m),
                              Termino(limpio(mx.Neg(sc)), 0, _cero(), "sin", m)])
        if e.name in ("sinh", "cosh"):
            ec, emc = limpio(mx.Call("exp", (c,))), limpio(mx.Call("exp", (mx.Neg(c),)))
            medio = mx.Num(Fraction(1, 2))
            signo = mx.Num(Fraction(1 if e.name == "cosh" else -1))
            return normaliza([Termino(limpio(mx.Mul(medio, ec)), 0, m, "1", _cero()),
                              Termino(limpio(mx.Mul(mx.Mul(medio, signo), emc)), 0,
                                      limpio(mx.Neg(m)), "1", _cero())])
    raise _no(f"«{mx.text(e)}» no es un cuasipolinomio (tⁿ·e^(αt)·sen/cos)")


def _parte_irracional(alfa: mx.Expr) -> tuple[Fraction, mx.Expr] | None:
    """α = p + ω con p racional y ω irracional (√2, −√3/2…)."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        pol = P.as_poly(limpio(alfa))
    except Exception:  # noqa: BLE001
        return None
    p = pol.get((), Fraction(0))
    resto = {m: c for m, c in pol.items() if m != ()}
    if not resto:
        return None
    return Fraction(p), limpio(P.to_expr(resto))


def a_expr(ts: Cuasi, t: str = "t") -> mx.Expr:
    """Vuelve a escribir el cuasipolinomio (forma legible); los pares
    c₁e^{(p+ω)t} + c₂e^{(p−ω)t} con ω irracional se escriben con cosh y senh."""
    T = mx.Sym(t)
    total: mx.Expr | None = None
    usados: set[int] = set()
    extra: list[mx.Expr] = []
    for i, x in enumerate(ts):
        if i in usados or x.tipo != "1":
            continue
        pi = _parte_irracional(x.alfa)
        if pi is None:
            # e^{ωt} y e^{−ωt} (racionales, opuestos) también: cosh y senh
            v = mx.exact_value(x.alfa)
            if v is None or v == 0 or mx.variables(x.alfa):
                continue
            pi = (Fraction(0), x.alfa)
        for j in range(i + 1, len(ts)):
            y = ts[j]
            if j in usados or y.tipo != "1" or y.n != x.n:
                continue
            pj = _parte_irracional(y.alfa)
            if pj is None:
                vy = mx.exact_value(y.alfa)
                pj = (Fraction(0), y.alfa) if vy is not None and not mx.variables(y.alfa) else None
            if pj is None or pj[0] != pi[0] or not es_cero(limpio(mx.Add(pi[1], pj[1]))):
                continue
            w = pi[1]
            if (mx.valor_real(w, {}) or 0) < 0:
                x, y, w = y, x, pj[1]
            ch = limpio(mx.Add(x.coef, y.coef))
            sh = limpio(mx.Sub(x.coef, y.coef))
            f: mx.Expr = mx.Add(mx.Mul(ch, mx.Call("cosh", (limpio(mx.Mul(w, T)),))),
                                mx.Mul(sh, mx.Call("sinh", (limpio(mx.Mul(w, T)),))))
            if x.n:
                f = mx.Mul(f, T if x.n == 1 else mx.Pow(T, mx.Num(Fraction(x.n))))
            if pi[0]:
                f = mx.Mul(f, mx.Call("exp", (limpio(mx.Mul(num(pi[0]), T)),)))
            extra.append(limpio(f))
            usados.update((i, j))
            break
    for i, x in enumerate(ts):
        if i in usados:
            continue
        f: mx.Expr = x.coef
        if x.n:
            f = mx.Mul(f, T if x.n == 1 else mx.Pow(T, mx.Num(Fraction(x.n))))
        if not es_cero(x.alfa):
            f = mx.Mul(f, mx.Call("exp", (limpio(mx.Mul(x.alfa, T)),)))
        if x.tipo != "1":
            f = mx.Mul(f, mx.Call(x.tipo, (limpio(mx.Mul(x.beta, T)),)))
        f = limpio(f)
        total = f if total is None else mx.Add(total, f)
    for f in extra:
        total = f if total is None else mx.Add(total, f)
    return limpio(total) if total is not None else _cero()


def desplaza(ts: Cuasi, a: mx.Expr) -> Cuasi:
    """f(t + a)."""
    T = mx.Sym("t")
    out: Cuasi = []
    for x in ts:
        base = leer(limpio(mx.Add(T, a)), "t")
        pot = constante(_uno())
        for _ in range(x.n):
            pot = producto(pot, base)
        fac = limpio(mx.Mul(x.coef, mx.Call("exp", (limpio(mx.Mul(x.alfa, a)),))))
        if x.tipo == "1":
            trig = constante(_uno())
        else:
            ba = limpio(mx.Mul(x.beta, a))
            cb, sb = limpio(mx.Call("cos", (ba,))), limpio(mx.Call("sin", (ba,)))
            if x.tipo == "cos":
                trig = normaliza([Termino(cb, 0, _cero(), "cos", x.beta),
                                  Termino(limpio(mx.Neg(sb)), 0, _cero(), "sin", x.beta)])
            else:
                trig = normaliza([Termino(cb, 0, _cero(), "sin", x.beta),
                                  Termino(sb, 0, _cero(), "cos", x.beta)])
        ex = [Termino(fac, 0, x.alfa, "1", _cero())]
        out.extend(producto(producto(pot, ex), trig))
    return normaliza(out)


def deriva(ts: Cuasi) -> Cuasi:
    """(c·tⁿ·e^{αt}·f(βt))′, término a término."""
    out: Cuasi = []
    for x in ts:
        if x.n:
            out.append(Termino(limpio(mx.Mul(mx.Num(Fraction(x.n)), x.coef)), x.n - 1, x.alfa,
                               x.tipo, x.beta))
        if not es_cero(x.alfa):
            out.append(Termino(limpio(mx.Mul(x.alfa, x.coef)), x.n, x.alfa, x.tipo, x.beta))
        if x.tipo == "cos":
            out.append(Termino(limpio(mx.Neg(mx.Mul(x.beta, x.coef))), x.n, x.alfa, "sin", x.beta))
        elif x.tipo == "sin":
            out.append(Termino(limpio(mx.Mul(x.beta, x.coef)), x.n, x.alfa, "cos", x.beta))
    return normaliza(out)


def binomial(n: int, k: int) -> int:
    return math.comb(n, k)


# ---------------------------------------------------------------------------
# integración exacta
# ---------------------------------------------------------------------------


def _pot_compleja(a: mx.Expr, b: mx.Expr, m: int) -> tuple[mx.Expr, mx.Expr]:
    """(Re, Im) de (a + i·b)^m, por el binomio."""
    re_, im_ = _cero(), _cero()
    for k in range(m + 1):
        c = mx.Mul(mx.Num(Fraction(math.comb(m, k))),
                   mx.Mul(mx.Pow(a, mx.Num(Fraction(m - k))) if m - k else _uno(),
                          mx.Pow(b, mx.Num(Fraction(k))) if k else _uno()))
        if k % 2 == 0:
            re_ = mx.Add(re_, c if (k // 2) % 2 == 0 else mx.Neg(c))
        else:
            im_ = mx.Add(im_, c if ((k - 1) // 2) % 2 == 0 else mx.Neg(c))
    return limpio(re_), limpio(im_)


def primitiva(ts: Cuasi) -> Cuasi:
    """∫ del cuasipolinomio (otro cuasipolinomio, salvo constante).

    ∫tⁿe^{zt}dt = e^{zt}·Σₖ (−1)ᵏ·n!/(n−k)!·t^{n−k}/z^{k+1}, z = α + iβ, y la parte
    real (cos) o imaginaria (sen); 1/z^m = (α − iβ)^m/(α² + β²)^m.
    """
    out: Cuasi = []
    for x in ts:
        a0 = es_cero(x.alfa)
        b0 = x.tipo == "1"
        if a0 and b0:
            out.append(Termino(limpio(mx.Div(x.coef, mx.Num(Fraction(x.n + 1)))), x.n + 1,
                               _cero(), "1", _cero()))
            continue
        al = x.alfa
        be = x.beta if not b0 else _cero()
        mod2 = limpio(mx.Add(mx.Pow(al, mx.Num(2)), mx.Pow(be, mx.Num(2))))
        for k in range(x.n + 1):
            fac = Fraction((-1) ** k * math.factorial(x.n), math.factorial(x.n - k))
            m = k + 1
            re_, im_ = _pot_compleja(al, limpio(mx.Neg(be)), m)     # (α − iβ)^m
            den = mx.Pow(mod2, mx.Num(Fraction(m)))
            Rz, Iz = limpio(mx.Div(re_, den)), limpio(mx.Div(im_, den))   # 1/z^m
            c = limpio(mx.Mul(x.coef, mx.Num(fac)))
            p = x.n - k
            if b0:
                out.append(Termino(limpio(mx.Mul(c, Rz)), p, al, "1", _cero()))
                continue
            # e^{αt}·(cos βt + i sen βt)·(Rz + i·Iz)
            if x.tipo == "cos":      # Re: cos·Rz − sen·Iz
                out.append(Termino(limpio(mx.Mul(c, Rz)), p, al, "cos", be))
                out.append(Termino(limpio(mx.Neg(mx.Mul(c, Iz))), p, al, "sin", be))
            else:                    # Im: sen·Rz + cos·Iz
                out.append(Termino(limpio(mx.Mul(c, Rz)), p, al, "sin", be))
                out.append(Termino(limpio(mx.Mul(c, Iz)), p, al, "cos", be))
    return normaliza(out)


def evalua(ts: Cuasi, t0: mx.Expr, t: str = "t") -> mx.Expr:
    return limpio(pliega(mx.substitute(a_expr(ts, t), t, t0)))


def integral_definida(ts: Cuasi, a: mx.Expr, b: mx.Expr | None, t: str = "t") -> mx.Expr:
    """∫_a^b; b = None es +∞ (exige que cada término decaiga: Re α < 0)."""
    P = primitiva(ts)
    if b is None:
        for x in P:
            al = mx.valor_real(x.alfa, {})
            if al is None or al >= 0:
                raise _no("la integral hasta +∞ no converge (algún término no decae)")
        return limpio(mx.Neg(evalua(P, a, t)))
    return limpio(mx.Sub(evalua(P, b, t), evalua(P, a, t)))


def _opuesto(a: mx.Expr) -> mx.Expr | None:
    """−a si a «empieza por menos» (−x, (−x)·y, (−c)·y); None si no."""
    if isinstance(a, mx.Neg):
        return a.arg
    if isinstance(a, mx.Num) and a.value < 0:
        return mx.Num(-a.value)
    if isinstance(a, mx.Mul):
        izq = _opuesto(a.left)
        if izq is not None:
            v = mx.exact_value(izq)
            return a.right if v == 1 and not mx.variables(izq) else mx.Mul(izq, a.right)
    if isinstance(a, mx.Div):
        izq = _opuesto(a.left)
        if izq is not None:
            return mx.Div(izq, a.right)
    return None


def pliega(e: mx.Expr) -> mx.Expr:
    """Plegado seguro: 0·x = 0, x + 0 = x, sen 0 = 0, cos 0 = 1, cos(−x) = cos x,
    sen(−x) = −sen x, 0/x = 0, x^1 = x, 1·x = x (sin reordenar nada más)."""
    def cero(n):
        v = mx.exact_value(n)
        return v is not None and v == 0 and not mx.variables(n)

    def uno(n):
        v = mx.exact_value(n)
        return v is not None and v == 1 and not mx.variables(n)

    if isinstance(e, mx.Mul):
        a, b = pliega(e.left), pliega(e.right)
        if cero(a) or cero(b):
            return _cero()
        if uno(a):
            return b
        if uno(b):
            return a
        return mx.Mul(a, b)
    if isinstance(e, mx.Div):
        a, b = pliega(e.left), pliega(e.right)
        if cero(a) and not cero(b):
            return _cero()
        if uno(b):
            return a
        return mx.Div(a, b)
    if isinstance(e, mx.Add):
        a, b = pliega(e.left), pliega(e.right)
        if cero(a):
            return b
        if cero(b):
            return a
        return mx.Add(a, b)
    if isinstance(e, mx.Sub):
        a, b = pliega(e.left), pliega(e.right)
        if cero(b):
            return a
        if cero(a):
            return mx.Neg(b)
        return mx.Sub(a, b)
    if isinstance(e, mx.Neg):
        a = pliega(e.arg)
        if cero(a):
            return _cero()
        if isinstance(a, mx.Neg):
            return a.arg
        return mx.Neg(a)
    if isinstance(e, mx.Pow):
        b, x = pliega(e.base), pliega(e.exponent)
        if uno(x):
            return b
        if cero(x):
            return _uno()
        return mx.Pow(b, x)
    if isinstance(e, mx.Call):
        args = tuple(pliega(a) for a in e.args)
        if len(args) == 1:
            a = args[0]
            if e.name in ("sin", "tan", "sinh") and cero(a):
                return _cero()
            if e.name in ("cos", "cosh", "exp") and cero(a):
                return _uno()
            pos = _opuesto(a)
            if pos is not None and e.name in ("cos", "cosh"):
                return mx.Call(e.name, (pos,))
            if pos is not None and e.name in ("sin", "sinh", "tan"):
                return mx.Neg(mx.Call(e.name, (pos,)))
        return mx.Call(e.name, args)
    return e
