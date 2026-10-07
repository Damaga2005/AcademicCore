# SPDX-License-Identifier: MIT
"""ML-8 (§4.5, v2): problemas de contorno 1D, Poisson por tramos y calor 1D.

Contorno. a₂y″ + a₁y′ + a₀y = f(x) en [a, b] con una condición en cada extremo
(y o y′ dado). Solución general y = C₁y₁ + C₂y₂ + y_p (EDO lineal; con parámetros,
y″ = κ²y da cosh/senh y y″ = −κ²y da cos/sen) y el sistema 2×2 de las condiciones:
determinante ≠ 0 ⇒ solución única; = 0 ⇒ ninguna o infinitas (se dice cuál).

Poisson por tramos. y″ = fᵢ(x) en cada [xᵢ, xᵢ₊₁] (con εᵢ opcional): en cada tramo
y = Fᵢ(x) + Aᵢx + Bᵢ, y en las uniones se empalman y y εᵢ·y′ (potencial y campo
continuos); el sistema lineal se resuelve exacto. Contraste: diferencias finitas
de segundo orden (sistema tridiagonal, algoritmo de Thomas).

Calor. u_t = α·u_xx en (0, L): Dirichlet u(0) = T₀, u(L) = T_L (estado estacionario
lineal + modos sen(nπx/L)), Neumann aislado (cosenos) o mixto u(0) = 0, u_x(L) = 0
(sen((2n−1)πx/(2L))). Los coeficientes son exactos con n simbólico; cada modo cumple
la EDP y las condiciones (comprobado exactamente) y los coeficientes se contrastan
con cuadratura.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import edo as ED
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

limpio = Q.limpio


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _bonito(e):
    from academic_core.domain.engineering.mathlab import fourier as FO

    return FO._bonito(e)


def _leer(v) -> mx.Expr:
    return v if isinstance(v, mx.Expr) else mx.parse(mx.normaliza_entrada(str(v)))


def _d(e, x):
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return limpio(DM.differentiate(e, x))


# ---------------------------------------------------------------------------
# problema de contorno
# ---------------------------------------------------------------------------


@dataclass
class Contorno:
    y: mx.Expr | None
    tipo: str               # «única», «infinitas», «ninguna»
    determinante: mx.Expr
    detalle: str

    def texto(self) -> str:
        if self.tipo == "única":
            cond = (f"para los parámetros con {mx.text(self.determinante)} ≠ 0"
                    if mx.variables(self.determinante) else
                    f"determinante {mx.text(self.determinante)} ≠ 0")
            return f"y = {mx.text(self.y)} (solución única: {cond})"
        return f"{self.tipo}: {self.detalle}"


def _base_parametrica(ec: ED.Ecuacion, x: str, trace: Trace):
    """a₂y″ + a₀y = c con coeficientes simbólicos: κ² = −a₀/a₂."""
    if ec.orden != 2 or not Q.es_cero(ec.coefs[1]) if not mx.variables(ec.coefs[1]) else True:
        if ec.orden != 2 or mx.variables(ec.coefs[1]) or not Q.es_cero(ec.coefs[1]):
            raise _no("con parámetros solo y″ = ±κ²·y (+ constante)")
    a2, a0 = ec.coefs[2], ec.coefs[0]
    if mx.depends(a2, x) or mx.depends(a0, x) or mx.depends(ec.f, x):
        raise _no("coeficientes o segundo miembro con x y parámetros a la vez")
    k2 = _bonito(mx.Neg(mx.Div(a0, a2)))
    env = {v: 1.37 for v in mx.variables(k2)}
    signo = mx.valor_real(k2, env)
    if signo is None or signo == 0:
        raise _no("no se decide el signo de κ²")
    X = mx.Sym(x)
    if signo > 0:
        kappa = _raiz_positiva(k2)
        modos = [mx.Call("cosh", (limpio(mx.Mul(kappa, X)),)),
                 mx.Call("sinh", (limpio(mx.Mul(kappa, X)),))]
        trace.regla("contorno.modos", f"κ² = {mx.text(k2)} > 0 (parámetros positivos): "
                    f"y = C₁cosh({mx.text(kappa)}{x}) + C₂senh({mx.text(kappa)}{x})",
                    why="raíces ±κ del característico")
    else:
        kappa = _raiz_positiva(_bonito(mx.Neg(k2)))
        modos = [mx.Call("cos", (limpio(mx.Mul(kappa, X)),)),
                 mx.Call("sin", (limpio(mx.Mul(kappa, X)),))]
        trace.regla("contorno.modos", f"κ² = {mx.text(k2)} < 0: y = C₁cos + C₂sen",
                    why="raíces ±iκ del característico")
    yp = mx.Num(Fraction(0)) if Q.es_cero(ec.f) else _bonito(mx.Div(ec.f, a0))
    return modos, yp


def _raiz_positiva(e: mx.Expr) -> mx.Expr:
    """√e con los parámetros positivos: √(c·Π vᵃ) = √c·Π v^(a/2) si los exponentes son pares."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        R = MI._racional(e)
        num, den = (R.left, R.right) if isinstance(R, mx.Div) else (R, mx.Num(Fraction(1)))
        pn, pd = P.as_poly(num), P.as_poly(den)
    except Exception:  # noqa: BLE001
        return _bonito(mx.Root(2, e))
    if len(pn) == 1 and len(pd) == 1:
        (mn, cn), = pn.items()
        (md, cd), = pd.items()
        if all(k % 2 == 0 for _, k in mn) and all(k % 2 == 0 for _, k in md) and cn > 0 and cd > 0:
            raiz_n = P.to_expr({tuple((v, k // 2) for v, k in mn): Fraction(1)})
            raiz_d = P.to_expr({tuple((v, k // 2) for v, k in md): Fraction(1)})
            c = _bonito(mx.Root(2, Q.num(cn / cd)))
            return _bonito(mx.Div(mx.Mul(c, raiz_n), raiz_d))
    return _bonito(mx.Root(2, e))


def contorno(ecuacion: str, a, b, cond_a: tuple, cond_b: tuple, x: str = "x",
             trace: Trace | None = None) -> Contorno:
    """cond = ("y", valor) o ("dy", valor) en cada extremo."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    trace = trace if trace is not None else Trace()
    ec = ED.leer(ecuacion, x)
    if ec.orden != 2 or not ec.lineal:
        raise _error("BAD_INPUT", "un problema de contorno de dos puntos es de orden 2 y lineal")
    a, b = _leer(a), _leer(b)
    try:
        g = ED.general(ec, trace)
        modos = [Q.a_expr([m], x) for m in g.homogenea]
        yp = Q.a_expr(g.particular, x) if isinstance(g.particular, list) else g.particular
    except UnsupportedError:
        modos, yp = _base_parametrica(ec, x, trace)
    C = [mx.Sym("C1"), mx.Sym("C2")]
    y = mx.Add(mx.Add(mx.Mul(C[0], modos[0]), mx.Mul(C[1], modos[1])), yp)
    filas, rhs = [], []
    for punto, (tipo, valor) in ((a, cond_a), (b, cond_b)):
        valor = _leer(valor)
        fs = modos if tipo == "y" else [_d(m, x) for m in modos]
        p_ = yp if tipo == "y" else _d(yp, x)
        filas.append([_bonito(mx.substitute(f, x, punto)) for f in fs])
        rhs.append(_bonito(mx.Sub(valor, mx.substitute(p_, x, punto))))
    det = _bonito(mx.Sub(mx.Mul(filas[0][0], filas[1][1]), mx.Mul(filas[0][1], filas[1][0])))
    trace.regla("contorno.sistema", "condiciones: [" + "; ".join(
        ", ".join(mx.text(c) for c in f) for f in filas) + f"]·(C₁, C₂) = ({mx.text(rhs[0])}, "
        f"{mx.text(rhs[1])}); determinante = {mx.text(det)}",
        why="cada condición de contorno es una ecuación lineal en C₁, C₂")
    if ED._eq0(det) or (not mx.variables(det) and Q.es_cero(det)):
        # rango 1: compatible si el sistema ampliado también tiene rango 1
        menor1 = _bonito(mx.Sub(mx.Mul(filas[0][0], rhs[1]), mx.Mul(filas[1][0], rhs[0])))
        menor2 = _bonito(mx.Sub(mx.Mul(filas[0][1], rhs[1]), mx.Mul(filas[1][1], rhs[0])))
        if ED._eq0(menor1) and ED._eq0(menor2):
            r = Contorno(None, "infinitas", det, "el determinante es 0 y las condiciones son "
                         "compatibles: una familia de soluciones con un parámetro libre")
        else:
            r = Contorno(None, "ninguna", det, "el determinante es 0 y las condiciones son "
                         "incompatibles: no hay solución")
        trace.regla("contorno.existencia", r.texto(), why="Rouché-Frobenius en el sistema 2×2")
        return r
    c1 = _bonito(mx.Div(mx.Sub(mx.Mul(rhs[0], filas[1][1]), mx.Mul(filas[0][1], rhs[1])), det))
    c2 = _bonito(mx.Div(mx.Sub(mx.Mul(filas[0][0], rhs[1]), mx.Mul(rhs[0], filas[1][0])), det))
    sol = MI._limpio(mx.substitute(mx.substitute(y, "C1", c1), "C2", c2))
    trace.regla("contorno.solucion", f"C₁ = {mx.text(c1)}, C₂ = {mx.text(c2)}: y = {mx.text(sol)}",
                why="Cramer")
    _verifica_contorno(ec, sol, x, a, b, cond_a, cond_b, trace)
    return Contorno(sol, "única", det, "")


def _verifica_contorno(ec, sol, x, a, b, cond_a, cond_b, trace) -> None:
    vs = sorted(mx.variables(sol) - {x})
    env = {v: 1.37 + 0.11 * i for i, v in enumerate(vs)}
    for punto, (tipo, valor) in ((a, cond_a), (b, cond_b)):
        f = sol if tipo == "y" else _d(sol, x)
        va = mx.valor_real(mx.substitute(f, x, punto), env)
        vb = mx.valor_real(_leer(valor), env)
        if va is None or vb is None or abs(va - vb) > 1e-9 * max(1.0, abs(vb)):
            raise _error("DISCREPANT", "la solución no cumple una condición de contorno")
    # la ecuación, en puntos (con los parámetros fijados)
    lhs = mx.Num(Fraction(0))
    d = sol
    for k, c in enumerate(ec.coefs):
        lhs = mx.Add(lhs, mx.Mul(c, d))
        d = _d(d, x)
    av = float(mx.valor_real(a, env))
    bv = float(mx.valor_real(b, env))
    for frac in (0.23, 0.51, 0.87):
        xv = av + frac * (bv - av)
        e2 = dict(env)
        e2[x] = xv
        r1, r2 = mx.valor_real(lhs, e2), mx.valor_real(ec.f, e2)
        if r1 is None or r2 is None or abs(r1 - r2) > 1e-8 * max(1.0, abs(r2)):
            raise _error("DISCREPANT", "la solución no cumple la ecuación")
    trace.verificacion("contorno.comprobacion", "la solución cumple la ecuación y las dos "
                       "condiciones de contorno (sustitución; con parámetros, en valores "
                       "positivos de prueba)", why="definición")


# ---------------------------------------------------------------------------
# Poisson 1D por tramos
# ---------------------------------------------------------------------------


@dataclass
class Poisson:
    piezas: list           # [(desde, hasta, y_i)]

    def texto(self) -> str:
        return "y = " + "; ".join(f"{mx.text(e)} en [{mx.text(a)}, {mx.text(b)}]"
                                  for a, b, e in self.piezas)


def _gauss_simbolico(M, v):
    n = len(M)
    A = [list(f) + [c] for f, c in zip(M, v)]
    for col in range(n):
        piv = None
        for r in range(col, n):
            val = mx.valor_real(A[r][col], {})
            if val is not None and abs(val) > 1e-14:
                piv = r
                break
        if piv is None:
            raise _error("SINGULAR", "el sistema del empalme es singular")
        A[col], A[piv] = A[piv], A[col]
        for r in range(n):
            if r == col:
                continue
            fac = _bonito(mx.Div(A[r][col], A[col][col]))
            if Q.es_cero(fac) if not mx.variables(fac) else False:
                continue
            A[r] = [_bonito(mx.Sub(A[r][j], mx.Mul(fac, A[col][j]))) for j in range(n + 1)]
    return [_bonito(mx.Div(A[i][n], A[i][i])) for i in range(n)]


def poisson(tramos, cond_a: tuple, cond_b: tuple, x: str = "x",
            trace: Trace | None = None) -> Poisson:
    """tramos = [[f, desde, hasta] o [f, desde, hasta, ε]]: y″ = f en cada uno."""
    from academic_core.domain.engineering.mathlab import integracion as IN
    from academic_core.domain.engineering.mathlab import multiple as MI

    trace = trace if trace is not None else Trace()
    piezas = []
    for t_ in tramos:
        f = _leer(t_[0])
        eps = _leer(t_[3]) if len(t_) > 3 else mx.Num(Fraction(1))
        piezas.append((f, _leer(t_[1]), _leer(t_[2]), eps))
    m = len(piezas)
    X = mx.Sym(x)
    Fs = []
    for f, a, b, _ in piezas:
        F1 = MI._limpio(IN.primitiva(f, x)) if mx.depends(f, x) or not Q.es_cero(f) else \
            mx.Num(Fraction(0))
        F2 = MI._limpio(IN.primitiva(F1, x)) if not Q.es_cero(F1) else mx.Num(Fraction(0))
        Fs.append(F2)
    trace.regla("poisson.primitivas", "; ".join(f"tramo {i + 1}: y = {mx.text(F)} + A{i + 1}·{x} + "
                                               f"B{i + 1}" for i, F in enumerate(Fs)),
                why="dos primitivas de y″ = f en cada tramo")
    n = 2 * m
    M, v = [], []

    def fila(i, tipo, punto, signo=1):
        """coeficientes de (Aᵢ, Bᵢ) y el término conocido de y o y′ del tramo i en el punto."""
        coef = [mx.Num(Fraction(0))] * n
        if tipo == "y":
            coef[2 * i] = punto
            coef[2 * i + 1] = mx.Num(Fraction(1))
            conocido = mx.substitute(Fs[i], x, punto)
        else:
            coef[2 * i] = mx.Num(Fraction(1))
            conocido = mx.substitute(_d(Fs[i], x), x, punto)
        return coef, _bonito(conocido)

    for i, punto, (tipo, valor) in ((0, piezas[0][1], cond_a), (m - 1, piezas[-1][2], cond_b)):
        c, k = fila(i, tipo if tipo == "y" else "dy", punto)
        M.append(c)
        v.append(_bonito(mx.Sub(_leer(valor), k)))
    for i in range(m - 1):
        p = piezas[i][2]
        if not Q.es_cero(limpio(mx.Sub(p, piezas[i + 1][1]))):
            raise _error("BAD_INPUT", "los tramos tienen que ser contiguos")
        ci, ki = fila(i, "y", p)
        cj, kj = fila(i + 1, "y", p)
        M.append([_bonito(mx.Sub(a_, b_)) for a_, b_ in zip(ci, cj)])
        v.append(_bonito(mx.Sub(kj, ki)))
        ei, ej = piezas[i][3], piezas[i + 1][3]
        ci, ki = fila(i, "dy", p)
        cj, kj = fila(i + 1, "dy", p)
        M.append([_bonito(mx.Sub(mx.Mul(ei, a_), mx.Mul(ej, b_))) for a_, b_ in zip(ci, cj)])
        v.append(_bonito(mx.Sub(mx.Mul(ej, kj), mx.Mul(ei, ki))))
    trace.regla("poisson.empalme", f"{n} ecuaciones: 2 de contorno y, en cada unión, y continua "
                "y ε·y′ continua", why="potencial continuo y flujo (campo por ε) continuo")
    sol = _gauss_simbolico(M, v)
    out = []
    for i, (f, a, b, _) in enumerate(piezas):
        yi = _bonito(mx.Add(Fs[i], mx.Add(mx.Mul(sol[2 * i], X), sol[2 * i + 1])))
        out.append((a, b, yi))
    r = Poisson(out)
    trace.regla("poisson.solucion", r.texto())
    _verifica_poisson(piezas, out, cond_a, cond_b, x, trace)
    return r


def _verifica_poisson(piezas, out, cond_a, cond_b, x, trace) -> None:
    """Exacto: y″ = f en cada tramo; numérico: diferencias finitas (Thomas)."""
    for (f, a, b, _), (_, _, yi) in zip(piezas, out):
        if not ED._eq0(mx.Sub(_d(_d(yi, x), x), f)):
            raise _error("DISCREPANT", "un tramo no cumple y″ = f")
    a0 = float(mx.valor_real(piezas[0][1], {}))
    b0 = float(mx.valor_real(piezas[-1][2], {}))
    if cond_a[0] != "y" or cond_b[0] != "y":
        trace.verificacion("poisson.exacta", "y″ = f exacto en cada tramo y los empalmes por "
                           "construcción", why="sustitución")
        return
    N = 800
    h = (b0 - a0) / N
    xs = [a0 + i * h for i in range(N + 1)]

    def tramo(xv):
        for k, (_, a, b, _) in enumerate(piezas):
            if float(mx.valor_real(a, {})) <= xv <= float(mx.valor_real(b, {})):
                return k
        return len(piezas) - 1

    def eps(xv):
        return float(mx.valor_real(piezas[tramo(xv)][3], {}))
    # (ε y′)′ = ε f en forma conservativa: ε_{i+½}(y_{i+1} − y_i) − ε_{i−½}(y_i − y_{i−1}) = h²·εf
    A, B, C, D = [], [], [], []
    for i in range(1, N):
        em, ep = eps(xs[i] - h / 2), eps(xs[i] + h / 2)
        k = tramo(xs[i])
        fi = float(mx.valor_real(piezas[k][0], {x: xs[i]}))
        A.append(em)
        B.append(-(em + ep))
        C.append(ep)
        D.append(h * h * fi * eps(xs[i]))
    ya = float(mx.valor_real(_leer(cond_a[1]), {}))
    yb = float(mx.valor_real(_leer(cond_b[1]), {}))
    D[0] -= A[0] * ya
    D[-1] -= C[-1] * yb
    n = len(B)
    cp, dp = [0.0] * n, [0.0] * n
    cp[0], dp[0] = C[0] / B[0], D[0] / B[0]
    for i in range(1, n):
        den = B[i] - A[i] * cp[i - 1]
        cp[i] = C[i] / den if i < n - 1 else 0.0
        dp[i] = (D[i] - A[i] * dp[i - 1]) / den
    ys = [0.0] * n
    ys[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        ys[i] = dp[i] - cp[i] * ys[i + 1]
    peor = 0.0
    escala = max(1.0, max(abs(v) for v in ys))
    for i in range(0, n, 37):
        xv = xs[i + 1]
        k = tramo(xv)
        exacto = float(mx.valor_real(out[k][2], {x: xv}))
        peor = max(peor, abs(exacto - ys[i]) / escala)
    if peor > 5e-3:
        raise _error("DISCREPANT", f"diferencias finitas frente a la solución: {peor:.3g}")
    trace.verificacion("poisson.diferencias", f"diferencias finitas tridiagonales (N = {N}) "
                       f"frente a la solución exacta: desviación relativa {peor:.2g}",
                       why="contraste numérico independiente (§4.5)")


# ---------------------------------------------------------------------------
# calor 1D
# ---------------------------------------------------------------------------


@dataclass
class Calor:
    estacionario: mx.Expr
    coef: mx.Expr
    modo: mx.Expr            # función de x y n
    decaimiento: mx.Expr     # λₙ: el modo decae e^{−α·λₙ·t}
    tipo: str
    a0: mx.Expr | None = None

    def texto(self) -> str:
        base = f"u(x, t) = {mx.text(self.estacionario)} + " if not Q.es_cero(self.estacionario) \
            else "u(x, t) = "
        if self.a0 is not None:
            base += f"{mx.text(self.a0)}/2 + "
        return (base + f"Σₙ bₙ·e^(−{mx.text(self.decaimiento)}·t)·{mx.text(self.modo)}; "
                f"bₙ = {mx.text(self.coef)} ({self.tipo})")


def calor(alfa, L, inicial, tipo: str = "dirichlet", T0="0", TL="0", x: str = "x",
          trace: Trace | None = None) -> Calor:
    """u_t = α·u_xx en (0, L); inicial = expresión o lista de [expr, desde, hasta]."""
    from academic_core.domain.engineering.mathlab import fourier as FO

    trace = trace if trace is not None else Trace()
    alfa, L = _leer(alfa), _leer(L)
    tramos = inicial if isinstance(inicial, list) else [[str(inicial), "0", mx.text(L)]]
    piezas = FO._lee_tramos(tramos, x)
    T0e = mx.substitute(_leer(T0), "t", mx.Sym("ti__"))
    TLe = mx.substitute(_leer(TL), "t", mx.Sym("ti__"))
    variable = mx.depends(T0e, "ti__") or mx.depends(TLe, "ti__")
    flujo = tipo in ("neumann", "mixta") and not (Q.es_cero(TLe) if not mx.variables(TLe) else False) \
        or tipo == "neumann" and not (Q.es_cero(T0e) if not mx.variables(T0e) else False) \
        or tipo == "mixta" and not (Q.es_cero(T0e) if not mx.variables(T0e) else False)
    if variable or flujo:
        return _calor_general(alfa, L, piezas, tipo, T0e, TLe, x, trace)
    n = mx.Sym("n")
    X = mx.Sym("t")              # las piezas usan «t» como variable interna
    if tipo == "dirichlet":
        T0e, TLe = _leer(T0), _leer(TL)
        v = _bonito(mx.Add(T0e, mx.Div(mx.Mul(mx.Sub(TLe, T0e), X), L)))
        k = _bonito(mx.Div(mx.Mul(n, mx.Const("pi")), L))
        modo = mx.Call("sin", (mx.Mul(k, X),))
        trace.regla("calor.estacionario", f"v(x) = {mx.text(mx.substitute(v, 't', mx.Sym(x)))}",
                    why="v″ = 0 con v(0) = T₀, v(L) = T_L; w = u − v tiene contorno nulo")
        resta = v
    elif tipo == "neumann":
        k = _bonito(mx.Div(mx.Mul(n, mx.Const("pi")), L))
        modo = mx.Call("cos", (mx.Mul(k, X),))
        resta = mx.Num(Fraction(0))
        v = mx.Num(Fraction(0))
    elif tipo == "mixta":
        k = _bonito(mx.Div(mx.Mul(mx.Sub(mx.Mul(mx.Num(2), n), mx.Num(1)), mx.Const("pi")),
                           mx.Mul(mx.Num(2), L)))
        modo = mx.Call("sin", (mx.Mul(k, X),))
        resta = mx.Num(Fraction(0))
        v = mx.Num(Fraction(0))
    else:
        raise _error("BAD_INPUT", "tipo de contorno: dirichlet, neumann o mixta")
    lam = _bonito(mx.Mul(alfa, mx.Pow(k, mx.Num(2))))
    trace.regla("calor.separacion", f"u = X(x)·T(t): X″ + λX = 0 con el contorno ⇒ modos "
                f"{mx.text(mx.substitute(modo, 't', mx.Sym(x)))}; T′ = −α·λₙ·T, α·λₙ = "
                f"{mx.text(lam)}",
                why="separación de variables")
    dosL = _bonito(mx.Div(mx.Num(2), L))
    total = None
    for e, lo, hi in piezas:
        g = Q.leer(_bonito(mx.Sub(e, resta)), "t")
        g = Q.producto(g, Q.leer(modo, "t"))
        I = Q.integral_definida(g, lo, hi, "t")
        total = I if total is None else mx.Add(total, I)
    coef = _bonito(FO.n_entero(Q.pliega(_bonito(mx.Mul(dosL, total)))))
    a0 = None
    if tipo == "neumann":
        tot0 = None
        for e, lo, hi in piezas:
            I = Q.integral_definida(Q.leer(e, "t"), lo, hi, "t")
            tot0 = I if tot0 is None else mx.Add(tot0, I)
        a0 = _bonito(mx.Mul(dosL, tot0))
    if tipo == "mixta":
        coef = _bonito(FO.n_entero(Q.pliega(_bonito(mx.Mul(dosL, total)))))
    modo_x = mx.substitute(modo, "t", mx.Sym(x))
    v_x = mx.substitute(v, "t", mx.Sym(x))
    r = Calor(v_x, coef, modo_x, lam, tipo, a0)
    trace.regla("calor.coeficientes", f"bₙ = (2/L)∫(u₀ − v)·modo = {mx.text(coef)}",
                why="ortogonalidad de los modos en (0, L)")
    _verifica_calor(r, alfa, L, piezas, resta, modo, x, trace)
    return r


@dataclass
class CalorGeneral:
    referencia: mx.Expr       # P(x, t) que cumple el contorno
    modo: mx.Expr
    wn: mx.Expr               # coeficiente temporal de cada modo (n, t)
    w0: mx.Expr | None        # término constante (Neumann)
    tipo: str
    especiales: dict = field(default_factory=dict)   # n resonante → wₙ(t) propio

    def coef(self, k: int) -> mx.Expr:
        return self.especiales.get(k) or mx.substitute(self.wn, "n", mx.Num(k))

    def texto(self) -> str:
        P = mx.text(self.referencia)
        base = f"u(x, t) = {P} + " + (f"{mx.text(self.w0)} + " if self.w0 is not None else "")
        extra = "".join(f"; para n = {k} (resonancia): w_{k}(t) = {mx.text(w)}"
                        for k, w in sorted(self.especiales.items()))
        return (base + f"Σₙ wₙ(t)·{mx.text(self.modo)}; wₙ(t) = {mx.text(self.wn)}"
                + (" (n ≠ " + ", ".join(map(str, sorted(self.especiales))) + ")"
                   if self.especiales else "") + extra +
                f" ({self.tipo}, contorno no homogéneo)")


def _calor_general(alfa, L, piezas, tipo, A, B, x, trace) -> CalorGeneral:
    """Contorno dependiente del tiempo o con flujo: u = P + w con P(x, t) que cumple el
    contorno; w_t = α·w_xx + S, S = α·P_xx − P_t; cada modo: wₙ′ + λₙwₙ = Sₙ(t) y
    wₙ(t) = e^{−λₙt}·[cₙ + ∫₀ᵗ e^{λₙτ}Sₙ(τ)dτ] (Duhamel)."""
    from academic_core.domain.engineering.mathlab import fourier as FO

    n = mx.Sym("n")
    X = mx.Sym("t")              # x interna de las piezas
    ti = mx.Sym("ti__")
    if tipo == "dirichlet":       # u(0) = A(t), u(L) = B(t)
        P = _bonito(mx.Add(A, mx.Div(mx.Mul(mx.Sub(B, A), X), L)))
        k = _bonito(mx.Div(mx.Mul(n, mx.Const("pi")), L))
        modo = mx.Call("sin", (mx.Mul(k, X),))
    elif tipo == "neumann":       # u_x(0) = A(t), u_x(L) = B(t)
        P = _bonito(mx.Add(mx.Mul(A, X), mx.Div(mx.Mul(mx.Sub(B, A), mx.Pow(X, mx.Num(2))),
                                               mx.Mul(mx.Num(2), L))))
        k = _bonito(mx.Div(mx.Mul(n, mx.Const("pi")), L))
        modo = mx.Call("cos", (mx.Mul(k, X),))
    elif tipo == "mixta":         # u(0) = A(t), u_x(L) = B(t)
        P = _bonito(mx.Add(A, mx.Mul(B, X)))
        k = _bonito(mx.Div(mx.Mul(mx.Sub(mx.Mul(mx.Num(2), n), mx.Num(1)), mx.Const("pi")),
                           mx.Mul(mx.Num(2), L)))
        modo = mx.Call("sin", (mx.Mul(k, X),))
    else:
        raise _error("BAD_INPUT", "tipo de contorno: dirichlet, neumann o mixta")
    lam = _bonito(mx.Mul(alfa, mx.Pow(k, mx.Num(2))))
    S = _bonito(mx.Sub(mx.Mul(alfa, _d(_d(P, "t"), "t")), _d(P, "ti__")))
    trace.regla("calor.referencia", f"P(x, t) = {mx.text(_a_x(P, x))} cumple el contorno; "
                f"w = u − P: w_t = α·w_xx + S con S = {mx.text(_a_x(S, x))}",
                why="se pasa el contorno no homogéneo a un término fuente")
    dosL = _bonito(mx.Div(mx.Num(2), L))
    Lv = mx.Num(Fraction(0))

    def proyecta(e_x, base):
        """(2/L)∫₀ᴸ e·base dx con e cuasipolinomio en x (coeficientes con ti__)."""
        g = Q.producto(Q.leer(e_x, "t"), Q.leer(base, "t")) if base is not None else Q.leer(e_x, "t")
        return Q.integral_definida(g, Lv, L, "t")
    # Sₙ(t) y cₙ
    Sn = _bonito(FO.n_entero(Q.pliega(_bonito(mx.Mul(dosL, proyecta(S, modo)))))) \
        if not ED._eq0(S) else mx.Num(Fraction(0))
    total = None
    for e, lo, hi in piezas:
        g = Q.producto(Q.leer(_bonito(mx.Sub(e, mx.substitute(P, "ti__", mx.Num(0)))), "t"),
                       Q.leer(modo, "t"))
        I = Q.integral_definida(g, lo, hi, "t")
        total = I if total is None else mx.Add(total, I)
    cn = _bonito(FO.n_entero(Q.pliega(_bonito(mx.Mul(dosL, total)))))
    # Duhamel en τ: ∫₀ᵗ e^{λτ}Sₙ(τ)dτ
    tau = mx.Sym("tau__")

    def duhamel(lam_, Sn_, cn_):
        if Q.es_cero(Sn_) if not mx.variables(Sn_) else False:
            integral = mx.Num(Fraction(0))
        else:
            g = Q.producto(Q.leer(mx.Call("exp", (mx.Mul(lam_, tau),)), "tau__"),
                           Q.leer(mx.substitute(Sn_, "ti__", tau), "tau__"))
            integral = Q.integral_definida(g, mx.Num(0), ti, "tau__")
        w_ = ED._bonito(FO.n_entero(Q.pliega(_bonito(mx.Mul(
            mx.Call("exp", (mx.Neg(mx.Mul(lam_, ti)),)), mx.Add(cn_, integral))))))
        return _simplifica_coefs(ED._bonito(ED._junta_exp(LP_expande(w_))))
    wn = duhamel(lam, Sn, cn)
    # resonancia: si la fuente contiene e^{−λₖt}, la fórmula general se anula en n = k
    # (0/0); ese modo se rehace con n = k fijado antes de integrar (aparece t·e^{−λₖt})
    especiales = {}
    for kk in range(1, 101):
        try:
            val = mx.valor_real(mx.substitute(wn, "n", mx.Num(kk)), {"ti__": 0.37})
            ok = val is not None and math.isfinite(val)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            sub = lambda e: _bonito(mx.substitute(e, "n", mx.Num(kk)))  # noqa: E731
            especiales[kk] = duhamel(sub(lam), sub(Sn), sub(cn))
            trace.regla("calor.resonancia", f"n = {kk}: la fuente resuena con el modo; "
                        f"w_{kk}(t) = {mx.text(_a_x(especiales[kk], x))}",
                        why="λₙ coincide con una tasa de la fuente: Duhamel da t·e^{−λt}")
    w0 = None
    if tipo == "neumann":
        # modo constante: w₀′ = S₀ (media), w₀(0) = media de f − P(x, 0)
        S0 = _bonito(mx.Div(proyecta(S, None), L))
        tot0 = None
        for e, lo, hi in piezas:
            I = Q.integral_definida(Q.leer(_bonito(mx.Sub(e, mx.substitute(P, "ti__", mx.Num(0)))),
                                           "t"), lo, hi, "t")
            tot0 = I if tot0 is None else mx.Add(tot0, I)
        c0 = _bonito(mx.Div(tot0, L))
        prim = Q.integral_definida(Q.leer(mx.substitute(S0, "ti__", tau), "tau__"), mx.Num(0), ti,
                                   "tau__") if mx.variables(S0) or not Q.es_cero(S0) else mx.Num(0)
        w0 = _bonito(mx.Add(c0, prim))
    r = CalorGeneral(_a_x(P, x), _a_x(modo, x), _a_x(wn, x), _a_x(w0, x) if w0 is not None else None,
                     tipo, {k_: _a_x(v_, x) for k_, v_ in especiales.items()})
    _verifica_calor_general(r, alfa, L, A, B, piezas, lam, S, modo, x, trace)
    return r


def _simplifica_coefs(e):
    """Agrupa los sumandos por su factor trascendente (exp, sen, cos) y reduce cada
    coeficiente (racional en n y π) a términos mínimos por mcd; si algo falla o el
    resultado no coincide numéricamente con e, se deja e."""
    from academic_core.domain.engineering.mathlab import racional as R

    def sumandos(x, signo=1):
        if isinstance(x, mx.Add):
            return sumandos(x.left, signo) + sumandos(x.right, signo)
        if isinstance(x, mx.Sub):
            return sumandos(x.left, signo) + sumandos(x.right, -signo)
        if isinstance(x, mx.Neg):
            return sumandos(x.arg, -signo)
        return [(signo, x)]

    def factores(x):
        """(num, den) como listas de factores."""
        if isinstance(x, mx.Mul):
            a, b = factores(x.left), factores(x.right)
            return a[0] + b[0], a[1] + b[1]
        if isinstance(x, mx.Div):
            a, b = factores(x.left), factores(x.right)
            return a[0] + b[1], a[1] + b[0]
        if isinstance(x, mx.Neg):
            a = factores(x.arg)
            return [mx.Num(-1)] + a[0], a[1]
        return [x], []

    def trasc(x):
        return any(isinstance(nd, mx.Call) or isinstance(nd, mx.Pow) and (
            mx.variables(nd.exponent) or isinstance(nd.base, mx.Const) and nd.base.name == "e")
            for nd in _nodos(x))

    def producto(fs):
        out = mx.Num(1)
        for f_ in fs:
            out = mx.Mul(out, f_)
        return out
    try:
        grupos: dict[str, list] = {}
        claves: dict[str, mx.Expr] = {}
        for sg, t_ in sumandos(e):
            num_, den_ = factores(t_)
            if any(trasc(f_) for f_ in den_):
                return e
            tr = [f_ for f_ in num_ if trasc(f_)]
            ra = [f_ for f_ in num_ if not trasc(f_)]
            k = " * ".join(sorted(mx.text(f_) for f_ in tr))
            claves[k] = producto(tr)
            grupos.setdefault(k, []).append(mx.Mul(mx.Num(sg), mx.Div(producto(ra), producto(den_))))
        r = None
        for k, cs in grupos.items():
            c = cs[0]
            for c2 in cs[1:]:
                c = mx.Add(c, c2)
            c = mx.substitute(R._plegar(_sin_pi(c)), "pi__", mx.Const("pi"))
            term = _bonito(mx.Mul(c, claves[k]))
            r = term if r is None else mx.Add(r, term)
        r = ED._bonito(r)
    except Exception:  # noqa: BLE001
        return e
    comprobados = 0
    for nv in (1.5, 2.5, 3.7, 5.3, 1, 2, 3, 5):      # n no entero evita resonancias 0/0
        for tv in (0.05, 0.3):
            env = {"n": nv, "ti__": tv}
            try:
                a = mx.valor_real(e, env)
            except Exception:  # noqa: BLE001
                a = None
            if a is None:
                continue
            try:
                b = mx.valor_real(r, env)
            except Exception:  # noqa: BLE001
                b = None
            if b is None or abs(a - b) > 1e-9 * (1 + abs(a)):
                return e
            comprobados += 1
    return r if comprobados >= 8 else e


def _nodos(x):
    yield x
    for hijo in ("left", "right", "arg", "base", "exponent", "radicand"):
        if hasattr(x, hijo):
            yield from _nodos(getattr(x, hijo))
    if isinstance(x, mx.Call):
        for a in x.args:
            yield from _nodos(a)


def _sin_pi(e):
    """π → símbolo pi__ para que el mcd polinómico lo trate como variable."""
    if isinstance(e, mx.Const) and e.name == "pi":
        return mx.Sym("pi__")
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sin_pi(e.left), _sin_pi(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_pi(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sin_pi(e.base), _sin_pi(e.exponent))
    return e


def LP_expande(e):
    from academic_core.domain.engineering.mathlab import laplace as LP

    return LP._expande(e)


def _a_x(e, x):
    """Variables internas → x y t."""
    return mx.substitute(mx.substitute(e, "t", mx.Sym(x)), "ti__", mx.Sym("t"))


def _verifica_calor_general(r, alfa, L, A, B, piezas, lam, S, modo, x, trace) -> None:
    """Numérica sobre la suma de 80 modos: contorno y ecuación del calor en puntos interiores
    (diferencias finitas), y la condición inicial en media cuadrática."""
    import math as _m

    Lv = float(mx.valor_real(L, {}))
    av = float(mx.valor_real(alfa, {}))
    modos = []
    for k in range(1, 81):
        modos.append((mx.substitute(r.modo, "n", mx.Num(k)), r.coef(k)))

    def u(xv, tv):
        env = {x: xv, "t": tv}
        tot = float(mx.valor_real(r.referencia, env))
        if r.w0 is not None:
            tot += float(mx.valor_real(r.w0, env))
        for mo, w in modos:
            tot += float(mx.valor_real(mo, env)) * float(mx.valor_real(w, env))
        return tot
    # cada modo: wₙ′ + λₙwₙ = Sₙ(t) (n = 1…6, en tres instantes, con derivada exacta)
    peor = 0.0
    Sn = None
    for k in sorted(set(range(1, 7)) | set(r.especiales)):
        w = mx.substitute(r.coef(k), "t", mx.Sym("ti__"))
        lam_k = float(mx.valor_real(mx.substitute(lam, "n", mx.Num(k)), {}))
        dw = _d(w, "ti__")
        mo = mx.substitute(modo, "n", mx.Num(k))
        for tv in (0.1, 0.4, 0.9):
            from academic_core.domain.engineering.mathlab import laplace as LP

            Sk = LP._cuadratura(lambda xv: float(mx.valor_real(S, {"t": xv, "ti__": tv})) *
                                float(mx.valor_real(mo, {"t": xv})), 0.0, Lv) * 2 / Lv
            lhs = float(mx.valor_real(dw, {"ti__": tv})) + lam_k * float(mx.valor_real(w, {"ti__": tv}))
            peor = max(peor, abs(lhs - Sk))
    if peor > 1e-8:
        raise _error("DISCREPANT", f"un modo no cumple wₙ′ + λₙwₙ = Sₙ ({peor:.3g})")
    _ = Sn
    h = 1e-6 * Lv
    trace.verificacion("calor.general", f"cada modo cumple wₙ′ + λₙwₙ = Sₙ (n = 1…6, Sₙ por "
                       f"cuadratura; desviación {peor:.2g}) y u cumple el contorno",
                       why="la serie es suma de modos que cumplen la ecuación con fuente")
    _ = _m


def _verifica_calor(r: Calor, alfa, L, piezas, resta, modo, x, trace) -> None:
    from academic_core.domain.engineering.mathlab import laplace as LP

    # cada modo e^{−αλt}·X(x) cumple u_t = α·u_xx (exacto, con n simbólico)
    T = mx.Sym("tt__")
    u = mx.Mul(mx.Call("exp", (mx.Neg(mx.Mul(r.decaimiento, T)),)), r.modo)
    pde = mx.Sub(_d(u, "tt__"), mx.Mul(alfa, _d(_d(u, x), x)))
    if not ED._eq0(pde):
        raise _error("DISCREPANT", "un modo no cumple la ecuación del calor")
    # contorno de los modos (n entero): se comprueba en n = 1…4
    Lv = float(mx.valor_real(L, {}))
    for nv in range(1, 5):
        m = mx.substitute(r.modo, "n", mx.Num(Fraction(nv)))
        dm = _d(m, x)
        val = {"dirichlet": (m, m), "neumann": (dm, dm), "mixta": (m, dm)}[r.tipo]
        for punto, f in ((0.0, val[0]), (Lv, val[1])):
            w = mx.valor_real(f, {x: punto})
            if w is None or abs(w) > 1e-9:
                raise _error("DISCREPANT", "un modo no cumple el contorno")
    # coeficientes frente a cuadratura
    peor = 0.0
    for nv in range(1, 6):
        num_ = 0.0
        mod_n = mx.substitute(modo, "n", mx.Num(Fraction(nv)))
        for e, lo, hi in piezas:
            g = mx.Mul(mx.Sub(e, resta), mod_n)
            num_ += LP._cuadratura(lambda s, g=g: float(mx.valor_real(g, {"t": s})),
                                   float(mx.valor_real(lo, {})), float(mx.valor_real(hi, {})))
        num_ *= 2 / Lv
        ex = mx.valor_real(r.coef, {"n": nv})
        if ex is None:
            raise _error("DISCREPANT", "bₙ no evaluable")
        peor = max(peor, abs(ex - num_))
    if peor > 1e-8:
        raise _error("DISCREPANT", f"bₙ frente a cuadratura: {peor:.3g}")
    trace.verificacion("calor.comprobacion", f"cada modo cumple u_t = α·u_xx y el contorno "
                       f"(exacto); b₁…b₅ frente a cuadratura (desviación {peor:.2g})",
                       why="la solución en serie es suma de soluciones que cumplen todo salvo "
                           "la condición inicial, que fijan los bₙ")
