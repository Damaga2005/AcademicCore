# SPDX-License-Identifier: MIT
"""Raíces exactas de cúbicas irreducibles sobre ℚ y fracciones simples por residuos.

x³ + ax² + bx + c con x = y − a/3: y³ + py + q, Δ = (q/2)² + (p/3)³.

* Δ < 0 (tres raíces reales, «casus irreducibilis»): forma trigonométrica
  yₖ = 2√(−p/3)·cos(⅓·arccos((3q/(2p))·√(−3/p)) − 2πk/3);
* Δ > 0: Cardano, y = ∛(−q/2 + √Δ) + ∛(−q/2 − √Δ) y el par complejo
  −(u + v)/2 ± i·(√3/2)(u − v).

Una cúbica irreducible no tiene raíces repetidas (es libre de cuadrados), así que
Δ ≠ 0. Cada raíz se contrasta con Durand-Kerner.

Residuos: para N/D con D = P·R, P producto de cúbicas irreducibles distintas y
mcd(P, R) = 1, Bézout u·P + v·R = 1 parte N/D = (N·v mód P)/P + N·u/R; la parte en
P se invierte por residuos exactos A = N₁(r)/P′(r) en cada raíz (con la parte real
e imaginaria por separado en los pares complejos).
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError

limpio = Q.limpio


def _no(m: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {m}")


def _bonito(e):
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        r = MI._limpio(e)
    except Exception:  # noqa: BLE001
        r = limpio(e)
    return r


def raices(q: list[Fraction]) -> list[tuple]:
    """[("real", r)] o [("real", r), ("par", α, β)] (raíz α ± iβ) de la cúbica mónica q."""
    q = [Fraction(c) / q[-1] for c in q]
    c0, b, a = q[0], q[1], q[2]
    p = b - a * a / 3
    qq = 2 * a ** 3 / 27 - a * b / 3 + c0
    desp = Q.num(-a / 3)
    delta = (qq / 2) ** 2 + (p / 3) ** 3
    out: list[tuple] = []
    if delta < 0:
        m = _bonito(mx.Mul(mx.Num(2), mx.Root(2, Q.num(-p / 3))))
        arg = limpio(mx.Mul(Q.num(3 * qq / (2 * p)), mx.Root(2, Q.num(-3 / p))))
        theta = mx.Div(mx.Call("acos", (arg,)), mx.Num(3))
        for k in range(3):
            ang = limpio(mx.Sub(theta, mx.Mul(Q.num(Fraction(2 * k, 3)), mx.Const("pi"))))
            out.append(("real", _bonito(mx.Add(mx.Mul(m, mx.Call("cos", (ang,))), desp))))
    else:
        sd = mx.Root(2, Q.num(delta))
        u = mx.Root(3, limpio(mx.Add(Q.num(-qq / 2), sd)))
        v = mx.Root(3, limpio(mx.Sub(Q.num(-qq / 2), sd)))
        y = mx.Add(u, v)
        out.append(("real", _bonito(mx.Add(y, desp))))
        out.append(("par", _bonito(mx.Add(mx.Neg(mx.Div(y, mx.Num(2))), desp)),
                    _bonito(mx.Mul(mx.Div(mx.Root(2, mx.Num(3)), mx.Num(2)),
                                   mx.Call("abs", (mx.Sub(u, v),))))))
    _comprueba(q, out)
    return out


def raices_cuartica(q: list[Fraction]) -> list[tuple]:
    """Ferrari: y⁴ + py² + qy + r (x = y − a/4); m raíz real de la resolvente
    8m³ + 8pm² + (2p² − 8r)m − q² = 0 hace (y² + p/2 + m)² = 2m(y − q/(4m))²."""
    q = [Fraction(c) / q[-1] for c in q]
    e0, d, c, b = q[0], q[1], q[2], q[3]
    p = c - 3 * b * b / 8
    qq = d - b * c / 2 + b ** 3 / 8
    r = e0 - b * d / 4 + b * b * c / 16 - 3 * b ** 4 / 256
    desp = Q.num(-b / 4)
    if qq == 0:
        raise _no("cuártica bicuadrada: se factoriza por otro camino")
    res = [-qq * qq, 2 * p * p - 8 * r, 8 * p, Fraction(8)]
    from academic_core.domain.engineering.mathlab import algebra as AL

    fac = AL.factores_irreducibles(res)
    m = None
    for qf, _ in fac:
        if len(qf) == 2:
            v = -qf[0] / qf[1]
            if v > 0:
                m = Q.num(v)
                break
    if m is None:
        for qf, _ in fac:
            if len(qf) == 4:
                for rr in raices(qf):
                    if rr[0] == "real" and (mx.valor_real(rr[1], {}) or 0) > 0:
                        m = rr[1]
                        break
            if len(qf) == 3:
                disc = qf[1] ** 2 - 4 * qf[0] * qf[2]
                if disc >= 0:
                    rq = _bonito(mx.Div(mx.Add(Q.num(-qf[1]), mx.Root(2, Q.num(disc))),
                                        Q.num(2 * qf[2])))
                    if (mx.valor_real(rq, {}) or 0) > 0:
                        m = rq
            if m is not None:
                break
    if m is None:
        raise _no("la resolvente no tiene raíz positiva expresable")
    s2m = _bonito(mx.Root(2, mx.Mul(mx.Num(2), m)))
    k = _bonito(mx.Div(Q.num(qq), mx.Mul(mx.Num(4), m)))
    out = []
    for signo in (1, -1):
        # y² ∓ s·y + (p/2 + m ± s·k) = 0
        B = _bonito(mx.Mul(Q.num(-signo), s2m))
        C = _bonito(mx.Add(mx.Add(Q.num(p / 2), m), mx.Mul(Q.num(signo), mx.Mul(s2m, k))))
        disc = _bonito(mx.Sub(mx.Pow(B, mx.Num(2)), mx.Mul(mx.Num(4), C)))
        dv = mx.valor_real(disc, {})
        mitad = _bonito(mx.Div(mx.Neg(B), mx.Num(2)))
        if dv is not None and dv >= 0:
            sd = mx.Root(2, disc)
            out.append(("real", _bonito(mx.Add(mx.Add(mitad, mx.Div(sd, mx.Num(2))), desp))))
            out.append(("real", _bonito(mx.Add(mx.Sub(mitad, mx.Div(sd, mx.Num(2))), desp))))
        else:
            out.append(("par", _bonito(mx.Add(mitad, desp)),
                        _bonito(mx.Div(mx.Root(2, mx.Neg(disc)), mx.Num(2)))))
    _comprueba(q, out)
    return out


def raices_irreducible(q: list[Fraction]) -> list[tuple]:
    if len(q) - 1 == 3:
        return raices(q)
    if len(q) - 1 == 4:
        return raices_cuartica(q)
    raise _no("grado ≥ 5: no hay fórmula general por radicales (Abel-Ruffini)")


def _comprueba(q, out) -> None:
    from academic_core.domain.engineering.mathlab import algebra as AL

    num = AL._raices_complejas(list(q))
    vals = []
    for r in out:
        if r[0] == "real":
            vals.append(complex(mx.valor_real(r[1], {})))
        else:
            a, b = float(mx.valor_real(r[1], {})), float(mx.valor_real(r[2], {}))
            vals += [complex(a, b), complex(a, -b)]
    for z in num:
        if min(abs(z - w) for w in vals) > 1e-8 * max(1.0, abs(z)):
            raise _no("las raíces de Cardano no coinciden con las numéricas")


# ---------------------------------------------------------------------------
# polinomios
# ---------------------------------------------------------------------------


def _eval(p, x):
    """p(x) con coeficientes expresión y x expresión (Horner)."""
    tot: mx.Expr = mx.Num(Fraction(0))
    for c in reversed(p):
        tot = mx.Add(mx.Mul(tot, x), c)
    return _bonito(tot)


def _eval_complejo(p, a, b):
    """(Re, Im) de p(a + ib)."""
    re_, im_ = mx.Num(Fraction(0)), mx.Num(Fraction(0))
    for k, c in enumerate(p):
        if Q.es_cero(c) if not mx.variables(c) else False:
            continue
        r, i = Q._pot_compleja(a, b, k) if k else (mx.Num(Fraction(1)), mx.Num(Fraction(0)))
        re_ = mx.Add(re_, mx.Mul(c, r))
        im_ = mx.Add(im_, mx.Mul(c, i))
    return _bonito(re_), _bonito(im_)


def _bezout(a: list[Fraction], b: list[Fraction]):
    """(u, v) con u·a + v·b = 1 (a, b coprimos)."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    def resta(x, y):
        n = max(len(x), len(y))
        x = list(x) + [Fraction(0)] * (n - len(x))
        y = list(y) + [Fraction(0)] * (n - len(y))
        return AL._p_recorta([p - q for p, q in zip(x, y)])
    r0, r1 = AL._p_recorta(list(a)), AL._p_recorta(list(b))
    s0, s1 = [Fraction(1)], [Fraction(0)]
    t0, t1 = [Fraction(0)], [Fraction(1)]
    while not (len(r1) == 1 and r1[0] == 0):
        c, r = AL._p_divmod(r0, r1)
        r = AL._p_recorta(r) if r else [Fraction(0)]
        r0, r1 = r1, r
        s0, s1 = s1, resta(s0, AL._p_mul(c, s1))
        t0, t1 = t1, resta(t0, AL._p_mul(c, t1))
    g = r0[0]
    return [x / g for x in s0], [x / g for x in t0]


def _divmod_expr(num: list, P: list[Fraction]):
    """(cociente, resto) de num entre P (P mónico en ℚ, num con coeficientes expresión)."""
    num = list(num)
    d = len(P) - 1
    coc = [mx.Num(Fraction(0))] * max(1, len(num) - d)
    for k in range(len(num) - 1, d - 1, -1):
        c = num[k]
        if Q.es_cero(c) if not mx.variables(c) else False:
            continue
        coc[k - d] = c
        for i in range(d + 1):
            num[k - d + i] = limpio(mx.Sub(num[k - d + i], mx.Mul(c, Q.num(P[i]))))
    return coc, (num + [mx.Num(Fraction(0))] * d)[:d]


def _resto_expr(num: list, P: list[Fraction]) -> list:
    return _divmod_expr(num, P)[1]


def separa(num: list, den: list[Fraction]):
    """(cubicas, num₁, P, num₂, R): num/den = num₁/P + num₂/R con P el producto de las
    cúbicas irreducibles simples de den. None si den no tiene ninguna."""
    from academic_core.domain.engineering.mathlab import algebra as AL
    from academic_core.domain.engineering.mathlab import laplace as LP

    den = AL._p_recorta(list(den))
    lider = den[-1]
    den = [c / lider for c in den]
    num = [limpio(mx.Div(c, Q.num(lider))) for c in num]
    factores = AL.factores_irreducibles(den)
    cubicas = [q for q, m in factores if len(q) - 1 in (3, 4) and m == 1]
    if any(len(q) - 1 >= 5 or (len(q) - 1 in (3, 4) and m > 1) for q, m in factores):
        raise _no("factor irreducible de grado ≥ 5 (o de grado 3–4 repetido): sin fórmula por "
                  "radicales manejable")
    if not cubicas:
        return None
    P = [Fraction(1)]
    for q in cubicas:
        P = AL._p_mul(P, q)
    R, resto = AL._p_divmod(den, P)
    R = AL._p_recorta(R)
    u, v = _bezout(P, R)
    vq = [Q.num(x) for x in v]
    uq = [Q.num(x) for x in u]
    coc, num1 = _divmod_expr(LP._p_mul(num, vq), P)
    # el cociente que se quita de num·v/P pasa al otro lado: + coc·R/R
    num2 = LP._p_suma(LP._p_mul(num, uq), LP._p_mul(coc, [Q.num(c) for c in R]))
    return cubicas, num1, P, num2, R


def inversa_residuos(num1: list, P: list[Fraction], cubicas, nombres: list | None = None):
    """L⁻¹{num₁/P} exacto por residuos en las raíces de Cardano.

    Devuelve (cuasi exacto, cuasi simbólico, definiciones): el simbólico usa nombres
    r₁, α₁, β₁… para las raíces y los coeficientes N₁(r)/P′(r) en función de ellos
    (legible); el exacto sustituye las raíces (para evaluar y comprobar)."""
    dP = [Q.num(k * P[k]) for k in range(1, len(P))]
    cero = mx.Num(Fraction(0))
    exacto: Q.Cuasi = []
    simb: Q.Cuasi = []
    defs: list[tuple[str, mx.Expr]] = []
    nombres = nombres if nombres is not None else []
    for q in cubicas:
        for r in raices_irreducible(q):
            if r[0] == "real":
                n = f"r{len([d for d in defs if d[0].startswith('r')]) + 1 + len(nombres)}"
                R = mx.Sym(n)
                A = _bonito(mx.Div(_eval(num1, R), _eval(dP, R)))
                defs.append((n, r[1]))
                simb.append(Q.Termino(A, 0, R, "1", cero))
                exacto.append(Q.Termino(_bonito(mx.substitute(A, n, r[1])), 0, r[1], "1", cero))
            else:
                k = len([d for d in defs if d[0].startswith("α")]) + 1
                an, bn = f"α{k}", f"β{k}"
                a, b = mx.Sym(an), mx.Sym(bn)
                nr, ni = _eval_complejo(num1, a, b)
                dr, di = _eval_complejo(dP, a, b)
                m2 = mx.Add(mx.Pow(dr, mx.Num(2)), mx.Pow(di, mx.Num(2)))
                c_cos = _bonito(mx.Mul(mx.Num(2), mx.Div(mx.Add(mx.Mul(nr, dr), mx.Mul(ni, di)), m2)))
                c_sin = _bonito(mx.Mul(mx.Num(-2), mx.Div(mx.Sub(mx.Mul(ni, dr), mx.Mul(nr, di)), m2)))
                defs += [(an, r[1]), (bn, r[2])]
                simb.append(Q.Termino(c_cos, 0, a, "cos", b))
                simb.append(Q.Termino(c_sin, 0, a, "sin", b))

                def sus(e):
                    return _bonito(mx.substitute(mx.substitute(e, an, r[1]), bn, r[2]))
                exacto.append(Q.Termino(sus(c_cos), 0, r[1], "cos", r[2]))
                exacto.append(Q.Termino(sus(c_sin), 0, r[1], "sin", r[2]))
    return Q.normaliza(exacto), simb, defs


def texto_definiciones(defs) -> str:
    return "; ".join(f"{n} = {mx.text(e)}" for n, e in defs)


def inversa_exacta(num: list, den: list[Fraction]) -> tuple[Q.Cuasi, list]:
    """(cuasipolinomio, parte entera) de L⁻¹{num/den} con cúbicas resueltas exactamente."""
    from academic_core.domain.engineering.mathlab import laplace as LP

    s = separa(num, den)
    if s is None:
        entera, fs = LP.simples(num, den)
        g: Q.Cuasi = []
        for f in fs:
            g = Q.suma(g, LP.inversa_simple(f))
        return g, entera
    cubicas, num1, P, num2, R = s
    g, _, _ = inversa_residuos(num1, P, cubicas)
    if len(R) > 1:
        entera, fs = LP.simples(num2, R)
        for f in fs:
            g = Q.suma(g, LP.inversa_simple(f))
    else:
        entera = [limpio(mx.Div(c, Q.num(R[0]))) for c in num2]
    return g, entera
