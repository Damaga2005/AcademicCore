# SPDX-License-Identifier: MIT
"""ML-2 (T8): primitives done the way the exam writes them.

Partial fractions (exam type 9)
-------------------------------

N/D with rational coefficients: polynomial division first; then D is factored
over ℚ — rational roots with multiplicity, and what is left must be a product of
irreducible quadratics (degree 2 left: irreducible by its discriminant; degree 4:
tried as a product of two monic quadratics with rational coefficients). The
ansatz

    Σ Aᵢⱼ/(x − rᵢ)ʲ + Σ (Bₖ·x + Cₖ)/qₖ(x)

is turned into a LINEAR SYSTEM for the unknowns by equating coefficients, solved
exactly by the ℚ-linear engine, and every piece integrated by its table formula:

    ∫ A/(x − r) = A·ln|x − r|,   ∫ A/(x − r)ʲ = −A/((j − 1)(x − r)^(j−1)),
    ∫ (Bx + C)/(x² + px + q) = (B/2)·ln(x² + px + q)
                               + (C − Bp/2)·(2/√Δ)·atan((2x + p)/√Δ),  Δ = 4q − p².

Trigonometric/hyperbolic substitution (exam type 10)
----------------------------------------------------

k·(a·x² + b·x + c)^(±1/2): completing the square, u = x + b/(2a), it is one of
√(m² − u²), √(u² + m²), √(u² − m²) (times √|a|), and the substitution
u = m·sen t, u = m·senh t or u = m·cosh t is written, with why it removes the root.

Every result is verified by differentiating it back (numerically, at seeded points
of its domain).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import limite as LM
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import raices as RZ
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError


def _no(m: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {m}")


def _num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


def _desplaza(X: mx.Expr, r: Fraction) -> mx.Expr:
    """x − r written as x, x − r or x + |r|."""
    if r == 0:
        return X
    return mx.Sub(X, mx.Num(r)) if r > 0 else mx.Add(X, mx.Num(-r))


def _poly_expr(c: list[Fraction], x: str) -> mx.Expr:
    total = None
    for k in range(len(c) - 1, -1, -1):
        if c[k] == 0:
            continue
        pot = mx.Num(Fraction(1)) if k == 0 else (mx.Sym(x) if k == 1 else
                                                  mx.Pow(mx.Sym(x), mx.Num(Fraction(k))))
        t = mx.Num(abs(c[k])) if k == 0 else (pot if abs(c[k]) == 1 else mx.Mul(mx.Num(abs(c[k])), pot))
        if total is None:
            total = t if c[k] > 0 else mx.Neg(t)
        else:
            total = mx.Add(total, t) if c[k] > 0 else mx.Sub(total, t)
    return total if total is not None else mx.Num(Fraction(0))


def _mul(a, b):
    r = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            r[i + j] += x * y
    return r


def _pow(a, k):
    r = [Fraction(1)]
    for _ in range(k):
        r = _mul(r, a)
    return r


# ---------------------------------------------------------------------------
# factoring over ℚ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Factor:
    poli: tuple[Fraction, ...]      # monic, degree 1 or 2
    multiplicidad: int


def factoriza(D: list[Fraction]) -> tuple[Fraction, list[Factor]]:
    D = RZ._recorta(list(D))
    lider = D[-1]
    p = [c / lider for c in D]
    factores: list[Factor] = []
    raices = RZ.raices_polinomio(p).raices
    for r in raices:
        q = mx.exact_value(r.valor) if r.exacta else None
        if q is None:
            continue
        m = 0
        while len(p) > 1 and RZ._eval(p, q) == 0:
            p, _ = RZ._divmod(p, [-q, Fraction(1)])
            m += 1
        if m:
            factores.append(Factor((-q, Fraction(1)), m))
    p = [c / p[-1] for c in p]
    if len(p) == 1:
        return lider, factores
    if len(p) == 3:
        return lider, factores + [Factor(tuple(p), 1)]
    # repeated irreducible quadratic: p = q^k
    g = RZ._mcd(p, [c * k for k, c in enumerate(p)][1:])
    if len(g) == 3:
        k = 0
        resto = p
        while len(resto) >= 3:
            cociente, r = RZ._divmod(resto, g)
            if r:
                break
            resto, k = cociente, k + 1
        if len(resto) == 1:
            return lider, factores + [Factor(tuple(g), k)]
    if len(p) == 5:
        # x⁴ + … = (x² + a x + b)(x² + c x + d) over ℚ: try b, d among divisors
        c0 = p[0]
        for b in _candidatos(c0):
            if b == 0:
                continue
            d = c0 / b
            # a + c = p3, b + d + a c = p2, a d + b c = p1
            s = p[3]
            # a·d + b·(s − a) = p1 → a (d − b) = p1 − b s
            if d != b:
                pares = [(p[1] - b * s) / (d - b)]
            elif p[1] == b * s:
                # b = d: a + c = s y a·c = p2 − 2b, raíces de t² − s·t + (p2 − 2b)
                r = _raiz_racional(s * s - 4 * (p[2] - 2 * b))
                pares = [(s + r) / 2] if r is not None else []
            else:
                pares = []
            for a in pares:
                c = s - a
                if b + d + a * c == p[2]:
                    q1, q2 = (b, a, Fraction(1)), (d, c, Fraction(1))
                    if all(x[1] ** 2 - 4 * x[0] < 0 for x in (q1, q2)):
                        return lider, factores + [Factor(q1, 1), Factor(q2, 1)]
    return lider, factores + _sin_raices_racionales(p)


def _raiz_racional(q: Fraction) -> Fraction | None:
    if q < 0:
        return None
    n, d = math.isqrt(q.numerator), math.isqrt(q.denominator)
    return Fraction(n, d) if n * n == q.numerator and d * d == q.denominator else None


def _divide(p: list[Fraction], q) -> list[Fraction] | None:
    cociente, r = RZ._divmod(p, list(q))
    return None if any(r) else cociente


def _bicuadrada(p) -> bool:
    """x⁴ + P·x² + s² con s ∈ ℚ⁺ y |P| < 2s: irreducible sobre ℚ (si no, ya se habría
    partido), pero x⁴ + P·x² + s² = (x² + s)² − (2s − P)·x² = (x² + αx + s)(x² − αx + s)
    con α = √(2s − P) sobre ℝ, y los dos factores sin raíces reales (Δ = 2s + P > 0)."""
    if len(p) != 5 or p[1] or p[3] or p[4] != 1:
        return False
    s = _raiz_racional(p[0])
    return s is not None and s > 0 and abs(p[2]) < 2 * s


def _sin_raices_racionales(p: list[Fraction]) -> list[Factor]:
    """Lo que queda sin raíces racionales, partido en cuadráticos sobre ℚ y, a lo
    sumo, cuárticos bicuadrados x⁴ + Px² + s². Las raíces complejas (Durand-Kerner)
    solo PROPONEN los factores, x² − 2Re(z)·x + |z|² por cada par conjugado y sus
    productos dos a dos; cada uno se acepta solo si divide EXACTAMENTE en ℚ."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    falla = _no("el denominador no se factoriza sobre ℚ en lineales, cuadráticos "
                "irreducibles y cuárticos x⁴ + px² + s²")
    if len(RZ._mcd(p, [c * k for k, c in enumerate(p)][1:])) > 1:
        raise falla          # factores repetidos: fuera de este camino
    zs = AL.raices_complejas(p)
    if any(abs(z.imag) <= 1e-9 for z in zs):
        raise falla          # raíz real irracional: no da un cuadrático sobre ℚ
    pares = [(-2 * z.real, abs(z) ** 2) for z in zs if z.imag > 0]

    def q(*c):
        return tuple(Fraction(v).limit_denominator(10 ** 6) for v in c)
    factores: list[Factor] = []
    restantes = []
    for b, c in pares:
        cand = q(c, b, 1)
        if len(p) == 3 and cand == tuple(p):
            factores.append(Factor(cand, 1))
            p = [Fraction(1)]
            continue
        cociente = _divide(p, cand) if len(p) > 3 else None
        if cociente is not None:
            factores.append(Factor(cand, 1))
            p = cociente
        else:
            restantes.append((b, c))
    usados: set[int] = set()
    for i, (b1, c1) in enumerate(restantes):
        for j in range(i + 1, len(restantes)):
            if len(p) <= 5 or i in usados or j in usados:
                continue
            b2, c2 = restantes[j]
            cand = q(c1 * c2, b1 * c2 + b2 * c1, c1 + c2 + b1 * b2, b1 + b2, 1)
            cociente = _divide(p, cand) if _bicuadrada(list(cand)) else None
            if cociente is not None:
                factores.append(Factor(cand, 1))
                usados |= {i, j}
                p = cociente
    if len(p) == 5 and _bicuadrada(p):
        factores.append(Factor(tuple(p), 1))
        p = [Fraction(1)]
    if len(p) != 1:
        raise falla
    return factores


def _coef_txt(a: Fraction) -> str:
    return str(a) if a.denominator == 1 and a >= 0 else f"({a})"


def _candidatos(c0: Fraction) -> list[Fraction]:
    num, den = abs(c0.numerator), c0.denominator
    salida = set()
    for a in RZ._divisores(num):
        for b in RZ._divisores(den):
            salida.update((Fraction(a, b), Fraction(-a, b)))
    return sorted(salida)


# ---------------------------------------------------------------------------
# partial fractions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fracciones:
    entera: list[Fraction]
    terminos: list[tuple]           # ("lineal", r, j, A) or ("cuadratico", (q0, q1), j, B, C)
    primitiva: mx.Expr

    def descomposicion(self, x: str) -> str:
        partes = []
        if any(self.entera):
            partes.append(mx.text(_poly_expr(self.entera, x)))
        for t in self.terminos:
            if t[0] == "lineal":
                _, r, j, A = t
                base = x if r == 0 else (f"({x} − {r})" if r > 0 else f"({x} + {-r})")
                partes.append(f"{_coef_txt(A)}/{base}" + (f"^{j}" if j > 1 else ""))
            elif t[0] == "cuartico":
                partes.append(f"({mx.text(_poly_expr(list(t[3:]), x))})/"
                              f"({mx.text(_poly_expr(list(t[1]), x))})")
            else:
                _, q, j, B, C = t
                quad = mx.text(_poly_expr(list(q) + [Fraction(1)], x))
                num = mx.text(_poly_expr([C, B], x))
                num = num if B == 0 and C.denominator == 1 and C >= 0 else f"({num})"
                partes.append(f"{num}/({quad})" + (f"^{j}" if j > 1 else ""))
        return " + ".join(partes)


def fracciones_simples(N: list[Fraction], D: list[Fraction], x: str,
                       trace: Trace | None = None) -> Fracciones:
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    N, D = RZ._recorta(list(N)), RZ._recorta(list(D))
    entera: list[Fraction] = [Fraction(0)]
    if len(N) >= len(D):
        entera, N = RZ._divmod(N, D)
        trace.regla("fracciones.division", f"división: cociente {mx.text(_poly_expr(entera, x))}, "
                                           f"resto {mx.text(_poly_expr(N, x))}",
                    why="el grado del numerador tiene que ser menor que el del denominador")
    lider, factores = factoriza(D)
    texto_fact = " · ".join(
        f"({mx.text(_poly_expr(list(f.poli), x))})" + (f"^{f.multiplicidad}" if f.multiplicidad > 1 else "")
        for f in factores)
    trace.regla("fracciones.factorizacion", f"denominador = {lider}·{texto_fact}",
                why="raíces racionales con su multiplicidad; el resto, cuadráticos sin raíces reales")
    # unknowns
    incognitas = []      # (kind, factor, j)
    for f in factores:
        for j in range(1, f.multiplicidad + 1):
            if len(f.poli) == 2:
                incognitas.append(("A", f, j))
            elif len(f.poli) == 5:
                incognitas.extend(("Q", f, k) for k in range(4))
            else:
                incognitas.append(("B", f, j))
                incognitas.append(("C", f, j))
    n = len(D) - 1
    columnas = []
    Dm = [c / lider for c in D]
    for kind, f, j in incognitas:
        fp = list(f.poli)
        resto, _ = RZ._divmod(Dm, _pow(fp, j))
        if kind == "Q":            # aquí j es el grado: resto·xʲ
            resto, _ = RZ._divmod(Dm, fp)
            col = _mul(resto, [Fraction(0)] * j + [Fraction(1)])
        else:
            col = _mul(resto, [Fraction(0), Fraction(1)]) if kind == "B" else resto
        col = col + [Fraction(0)] * (n - len(col))
        columnas.append(col[:n])
    filas = [[columnas[c][k] for c in range(len(incognitas))] for k in range(n)]
    Nm = [c / lider for c in N] + [Fraction(0)] * n
    Q = L.cuerpo("Q")
    sistema = L.resolver_sistema(filas, Nm[:n], Q, Trace())
    if sistema.particular is None or sistema.nucleo:
        raise _no("el sistema de coeficientes no tiene solución única")
    valores = sistema.particular
    trace.regla("fracciones.sistema", "igualando coeficientes: sistema lineal de "
                                      f"{len(incognitas)} incógnitas, resuelto exacto",
                why="dos polinomios son iguales si lo son sus coeficientes")
    terminos = []
    i = 0
    for kind, f, j in incognitas:
        if kind == "A":
            terminos.append(("lineal", -f.poli[0], j, valores[i]))
            i += 1
        elif kind == "B":
            terminos.append(("cuadratico", (f.poli[0], f.poli[1]), j, valores[i], valores[i + 1]))
            i += 2
        elif kind == "Q" and j == 0:
            terminos.append(("cuartico", f.poli, 1, *valores[i:i + 4]))
            i += 4
    terminos = [t for t in terminos if any(v != 0 for v in t[3:])]
    primitiva = _integra(entera, terminos, x, trace)
    frac = Fracciones(entera, terminos, primitiva)
    trace.regla("fracciones.descomposicion", f"integrando = {frac.descomposicion(x)}")
    trace.regla("fracciones.primitiva", f"∫ = {mx.text(primitiva)} + C",
                why="cada fracción tiene primitiva de tabla: ln|x − r|, potencia, ln y arctan")
    return frac


def _integra(entera, terminos, x: str, trace=None) -> mx.Expr:
    from academic_core.domain.engineering.mathlab.trace import Trace as _Trace

    trace = trace if trace is not None else _Trace()
    X = mx.Sym(x)
    total: mx.Expr | None = None
    # polynomial part
    integral = [Fraction(0)] + [c / (k + 1) for k, c in enumerate(entera)]
    if any(integral):
        total = _poly_expr(integral, x)
    for t in terminos:
        if t[0] == "cuartico":
            term = _integra_bicuadrada(t[1], t[3:], x, trace)
        elif t[0] == "lineal":
            _, r, j, A = t
            base = _desplaza(X, r)
            if j == 1:
                term = mx.Mul(_num(A), mx.Call("ln", (mx.Call("abs", (base,)),)))
            else:
                term = mx.Div(_num(-A / (j - 1)), base if j == 2 else
                              mx.Pow(base, mx.Num(Fraction(j - 1))))
        else:
            _, (q0, q1), j, B, C = t
            if j != 1:
                term = _integra_cuadratico_repetido(q0, q1, j, B, C, x, trace)
            else:
                quad = _poly_expr([q0, q1, Fraction(1)], x)
                delta = 4 * q0 - q1 * q1
                k = C - B * q1 / 2
                r = _raiz_racional(abs(delta))
                if delta < 0:
                    # raíces reales irracionales (x² − 2): no es un cuadrático irreducible,
                    # (C − Bp/2)/√Δ′·ln|(2x + p − √Δ′)/(2x + p + √Δ′)|
                    parte_ln = mx.Mul(_num(B / 2), mx.Call("ln", (mx.Call("abs", (quad,)),)))
                    rd = mx.Root(2, mx.Num(-delta))
                    dos_x_p = _desplaza(mx.Mul(mx.Num(Fraction(2)), X), -q1)
                    atan = mx.Mul(mx.Div(_num(k), rd), mx.Call("ln", (mx.Call("abs", (
                        mx.Div(mx.Sub(dos_x_p, rd), mx.Add(dos_x_p, rd)),)),)))
                elif r is not None:
                    # Δ cuadrado perfecto: atan((2x + p)/r) escrito ya simplificado
                    parte_ln = mx.Mul(_num(B / 2), mx.Call("ln", (quad,)))
                    atan = mx.Mul(_num(2 * k / r),
                                  mx.Call("atan", (_poly_expr([q1 / r, 2 / r], x),)))
                else:
                    raiz = mx.Root(2, mx.Num(delta))
                    parte_ln = mx.Mul(_num(B / 2), mx.Call("ln", (quad,)))
                    atan = mx.Mul(mx.Mul(_num(2 * k), mx.Div(mx.Num(Fraction(1)), raiz)),
                                  mx.Call("atan", (mx.Div(_desplaza(mx.Mul(mx.Num(Fraction(2)), X),
                                                                    -q1), raiz),)))
                term = mx.Add(parte_ln, atan) if k != 0 else parte_ln
                if B == 0:
                    term = atan
        total = term if total is None else mx.Add(total, term)
    return LM._limpio(total) if total is not None else mx.Num(Fraction(0))


def _integra_bicuadrada(poli, N, x: str, trace) -> mx.Expr:
    """∫ (n₀ + n₁x + n₂x² + n₃x³)/(x⁴ + Px² + s²) con Q± = x² ± αx + s, α = √k,
    k = 2s − P, y Δ = 2s + P el discriminante (cambiado de signo) de los dos.

    Fracciones simples sobre ℚ(α), resueltas a mano: con u = n₃/2,
    v = (n₂ − n₀/s)/(2k), w = n₀/(2s), z = (n₁ − s·n₃)/(2k),
        N/D = ((u − vα)x + (w − zα))/Q₊ + ((u + vα)x + (w + zα))/Q₋,
    y cada una por su tabla. Agrupando, con g = w + vk/2 y h = z + u/2:
        ∫ = (u/2)·ln D − (vα/2)·ln(Q₊/Q₋)
            + (2g/√Δ)·[atan((2x + α)/√Δ) + atan((2x − α)/√Δ)]
            + (2hα/√Δ)·[atan((2x − α)/√Δ) − atan((2x + α)/√Δ)]."""
    P = poli[2]
    s = _raiz_racional(poli[0])
    n0, n1, n2, n3 = N
    k, m = 2 * s - P, 2 * s + P
    u, v, w, z = n3 / 2, (n2 - n0 / s) / (2 * k), n0 / (2 * s), (n1 - s * n3) / (2 * k)
    g, h = w + v * k / 2, z + u / 2
    X = mx.Sym(x)
    alfa, raiz = mx.Root(2, mx.Num(k)), mx.Root(2, mx.Num(m))
    x2 = mx.Pow(X, mx.Num(Fraction(2)))
    Qmas = mx.Add(mx.Add(x2, mx.Mul(alfa, X)), mx.Num(s))
    Qmenos = mx.Add(mx.Sub(x2, mx.Mul(alfa, X)), mx.Num(s))
    dosx = mx.Mul(mx.Num(Fraction(2)), X)
    at_mas = mx.Call("atan", (mx.Div(mx.Add(dosx, alfa), raiz),))
    at_menos = mx.Call("atan", (mx.Div(mx.Sub(dosx, alfa), raiz),))
    partes = []
    if u:
        partes.append(mx.Mul(_num(u / 2), mx.Call("ln", (_poly_expr(list(poli), x),))))
    if v:
        partes.append(mx.Mul(mx.Mul(_num(-v / 2), alfa), mx.Call("ln", (mx.Div(Qmas, Qmenos),))))
    if g:
        partes.append(mx.Mul(mx.Div(_num(2 * g), raiz), mx.Add(at_mas, at_menos)))
    if h:
        partes.append(mx.Mul(mx.Div(mx.Mul(_num(2 * h), alfa), raiz), mx.Sub(at_menos, at_mas)))
    trace.regla("fracciones.bicuadrada",
                f"{mx.text(_poly_expr(list(poli), x))} = ({mx.text(Qmas)})·({mx.text(Qmenos)})",
                why="(x² + s)² − (2s − P)·x²: diferencia de cuadrados sobre ℝ; los dos "
                    "factores no tienen raíces reales y cada fracción va a ln y arctan")
    total = partes[0] if partes else mx.Num(Fraction(0))
    for p_ in partes[1:]:
        total = mx.Add(total, p_)
    return total


# ---------------------------------------------------------------------------
# trigonometric / hyperbolic substitution for √(quadratic)
# ---------------------------------------------------------------------------


def _forma_raiz(e: mx.Expr, x: str) -> tuple[Fraction, list[Fraction], int] | None:
    """k·(quadratic)^(±1/2) → (k, quadratic coefficients, ±1)."""
    k = Fraction(1)
    while True:
        if isinstance(e, mx.Neg):
            k, e = -k, e.arg
            continue
        if isinstance(e, mx.Mul) and mx.exact_value(e.left) is not None:
            k, e = k * mx.exact_value(e.left), e.right
            continue
        if isinstance(e, mx.Div) and mx.exact_value(e.right) is not None and \
                mx.exact_value(e.left) is None:
            k, e = k / mx.exact_value(e.right), e.left
            continue
        break
    signo = 1
    if isinstance(e, mx.Div) and mx.exact_value(e.left) is not None:
        k, e, signo = k * mx.exact_value(e.left), e.right, -1
    base = None
    if isinstance(e, mx.Root) and e.degree == 2:
        base = e.radicand
    elif isinstance(e, mx.Pow) and mx.exact_value(e.exponent) in (Fraction(1, 2), Fraction(-1, 2)):
        base = e.base
        if mx.exact_value(e.exponent) < 0:
            signo = -signo
    elif isinstance(e, mx.Call) and e.name in ("sqrt", "raiz", "raiz2"):
        base = e.args[0]
    if base is None:
        return None
    q = RZ._polinomio_de(base, x)
    if q is None or len(RZ._recorta(q)) != 3:
        return None
    return k, RZ._recorta(q), signo


def sustitucion_trigonometrica(f: mx.Expr, x: str, trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    forma = _forma_raiz(f, x)
    if forma is None:
        raise _no("no es k·√(ax² + bx + c) ni k/√(ax² + bx + c)")
    k, (c, b, a), signo = forma
    h = b / (2 * a)
    resto = c - b * b / (4 * a)                  # a·(x + h)² + resto
    u = _desplaza(mx.Sym(x), -h)
    X = mx.Sym(x)
    trace.regla("sustitucion.completar", f"{mx.text(_poly_expr([c, b, a], x))} = "
                                         f"{a}·({mx.text(u)})² + {resto}",
                why="completar el cuadrado deja una de las tres formas estándar")
    m2 = abs(resto / a)
    m = mx.Root(2, mx.Num(m2)) if m2 else mx.Num(Fraction(0))
    sa = mx.Root(2, mx.Num(abs(a)))
    if a < 0 and resto > 0:
        tipo = "√(m² − u²)"
        cambio = "u = m·sen t (cos t ≥ 0 en [−π/2, π/2]: √(m² − m²sen²t) = m·cos t)"
        uq = mx.Div(u, m)
        if signo > 0:
            base = mx.Mul(mx.Num(Fraction(1, 2)), mx.Add(
                mx.Mul(u, mx.Root(2, mx.Sub(mx.Num(m2), mx.Pow(u, mx.Num(Fraction(2)))))),
                mx.Mul(mx.Num(m2), mx.Call("asin", (uq,)))))
            prim = mx.Mul(sa, base)
        else:
            prim = mx.Div(mx.Call("asin", (uq,)), sa)
    elif a > 0 and resto > 0:
        tipo = "√(u² + m²)"
        cambio = "u = m·senh t (cosh t > 0: √(m²senh²t + m²) = m·cosh t)"
        raiz = mx.Root(2, mx.Add(mx.Pow(u, mx.Num(Fraction(2))), mx.Num(m2)))
        if signo > 0:
            prim = mx.Mul(sa, mx.Mul(mx.Num(Fraction(1, 2)), mx.Add(
                mx.Mul(u, raiz), mx.Mul(mx.Num(m2), mx.Call("ln", (mx.Add(u, raiz),))))))
        else:
            prim = mx.Div(mx.Call("ln", (mx.Add(u, raiz),)), sa)
    elif a > 0 and resto < 0:
        tipo = "√(u² − m²)"
        cambio = "u = m·cosh t (t ≥ 0, senh t ≥ 0: √(m²cosh²t − m²) = m·senh t)"
        raiz = mx.Root(2, mx.Sub(mx.Pow(u, mx.Num(Fraction(2))), mx.Num(m2)))
        if signo > 0:
            prim = mx.Mul(sa, mx.Mul(mx.Num(Fraction(1, 2)), mx.Sub(
                mx.Mul(u, raiz), mx.Mul(mx.Num(m2), mx.Call("ln", (mx.Call("abs", (mx.Add(u, raiz),)),))))))
        else:
            prim = mx.Div(mx.Call("ln", (mx.Call("abs", (mx.Add(u, raiz),)),)), sa)
    else:
        raise _no("el radicando no es positivo en ningún intervalo")
    trace.metodo("sustitucion.trigonometrica", f"forma {tipo}: {cambio}",
                 why="la identidad pitagórica (trigonométrica o hiperbólica) convierte la raíz "
                     "en una función sin raíz")
    resultado = LM._limpio(mx.Mul(_num(k), prim))
    trace.regla("sustitucion.resultado", f"∫ = {mx.text(resultado)} + C",
                why="se deshace el cambio con t = arcsen(u/m), argsenh(u/m) o argcosh(u/m)")
    del X
    return resultado


def _integra_cuadratico_repetido(q0: Fraction, q1: Fraction, j: int, B: Fraction,
                                  C: Fraction, x: str, trace) -> mx.Expr:
    """∫(Bx+C)/(x²+q1·x+q0)^j con j > 1 y discriminante negativo.

    Bx+C = (B/2)(2x+q1) + (C−Bq1/2): la primera parte es inmediata
    −(B/2)/((j−1)·quad^{j−1}); la segunda usa la reducción
    J_j = u/(2m²(j−1)·quad^{j−1}) + (2j−3)/(2m²(j−1))·J_{j−1} con
    u = x+q1/2, m² = Δ/4, hasta J_1 = (2/√Δ)·atan((2x+q1)/√Δ).
    Con Δ ≤ 0 se rechaza con su motivo (no es irreducible sobre ℝ).
    """
    delta = 4 * q0 - q1 * q1
    if delta <= 0:
        raise _no("potencia de una cuadrática con discriminante ≤ 0: no es irreducible "
                  "sobre ℝ y la reducción con atan no vale")
    quad = _poly_expr([q0, q1, Fraction(1)], x)
    total: mx.Expr = mx.Num(Fraction(0))
    if B != 0:
        total = mx.Div(mx.Mul(_num(B / 2), mx.Num(Fraction(-1))),
                       mx.Mul(mx.Num(Fraction(j - 1)),
                              mx.Pow(quad, mx.Num(Fraction(j - 1)))))
        trace.regla("fracciones.reduccion_directa",
                    f"∫(B/2)(2x+q1)/quad^{j} = {mx.text(total)}",
                    why="el numerador es la derivada del denominador salvo constante")
    k2 = C - B * q1 / 2
    if k2 != 0:
        total = mx.Add(total, mx.Mul(_num(k2), _cadena_j(q0, q1, j, x, trace)))
    return LM._limpio(total)


def _cadena_j(q0: Fraction, q1: Fraction, j: int, x: str, trace) -> mx.Expr:
    """J_j = ∫dx/quad^j por reducción hasta J_1 (atan).

    J_nivel = a·u/quad^{nivel−1} + b·J_{nivel−1} con a = 1/(2m²(nivel−1)),
    b = (2nivel−3)/(2m²(nivel−1)): se despliega de j hacia abajo acumulando
    el producto de los b superiores.
    """
    X = mx.Sym(x)
    delta = 4 * q0 - q1 * q1
    m2 = delta / 4
    raiz = mx.Root(2, mx.Num(delta))
    u = _desplaza(X, -q1 / 2)
    quad = _poly_expr([q0, q1, Fraction(1)], x)
    j1 = mx.Mul(mx.Mul(_num(Fraction(2)), mx.Div(mx.Num(Fraction(1)), raiz)),
                mx.Call("atan", (mx.Div(_desplaza(mx.Mul(mx.Num(Fraction(2)), X), -q1),
                                                raiz),)))
    if j == 1:
        return j1
    resto: mx.Expr = mx.Num(Fraction(0))
    coef = Fraction(1)
    for nivel in range(j, 1, -1):
        a = Fraction(1, 2 * m2 * (nivel - 1))
        b = Fraction(2 * nivel - 3, 2 * m2 * (nivel - 1))
        termino_u = mx.Mul(_num(a * coef),
                           mx.Div(u, mx.Pow(quad, mx.Num(Fraction(nivel - 1)))))
        resto = mx.Add(resto, termino_u)
        coef = coef * b
    resultado = mx.Add(resto, mx.Mul(_num(coef), j1))
    trace.regla("fracciones.reduccion", f"J_{j} reducido a J_1 con Δ = {delta}",
                why="J_j = u/(2m²(j−1)·quad^{j−1}) + (2j−3)/(2m²(j−1))·J_{j−1}, "
                    "exacto por derivación del producto")
    return LM._limpio(resultado)


def comprueba(primitiva: mx.Expr, integrando: mx.Expr, x: str) -> tuple[bool, str]:
    """Differentiate back (central differences) at points where both are defined."""
    from academic_core.domain.engineering.mathlab import verify as V

    malos, buenos = 0, 0
    for p in V.sample_values(count=24):
        h = 1e-6 * max(1.0, abs(p))
        try:
            a = mx.valor_real(primitiva, {x: p + h})
            b = mx.valor_real(primitiva, {x: p - h})
            f = mx.valor_real(integrando, {x: p})
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if None in (a, b, f):
            continue
        d = (a - b) / (2 * h)
        if abs(d - f) > 1e-5 * max(1.0, abs(f)):
            malos += 1
        else:
            buenos += 1
    return malos == 0 and buenos >= 4, f"F′ = f en {buenos} puntos" + (
        f", falla en {malos}" if malos else "")
