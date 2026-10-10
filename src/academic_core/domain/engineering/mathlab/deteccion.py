# SPDX-License-Identifier: MIT
"""ML-18, bloque 16 (G): matriz de correlación y PSD teórica, detección
(MAP, Neyman-Pearson, ROC), Fisher y Cramér-Rao, ML/MAP/MMSE gaussianos,
Wiener y mínimos cuadrados, gradiente, LMS y NLMS.

Todo determinista: el azar sembrado sale del Generador de ``eventos`` y la
verificación es Monte Carlo contra la teoría o residuo cero. Sin
dependencias. Cada función escribe su «por qué» (§5.5b) con hipótesis
(§5.7) y segundo camino (§5.3).
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise _error("BAD_INPUT", f"«{x}» no es un número finito")
        return Fraction(repr(x))  # decimal exacto: 1.6e-19 no se hace 0
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            return Fraction(repr(float(s)))
        except ValueError:
            raise _error("BAD_INPUT", f"«{x}» no es un número")


def _f(x) -> float:
    return float(_Q(x))


def Q(x: float) -> float:
    """Q(x) = P(N(0,1) > x) = ½·erfc(x/√2)."""
    return 0.5 * math.erfc(x / math.sqrt(2))


def Qinv(p: float) -> float:
    """Inversa de Q por bisección (0 < p < 1)."""
    if not 0 < p < 1:
        raise _error("BAD_INPUT", "0 < p < 1 para Q⁻¹")
    lo, hi = -10.0, 10.0
    for _ in range(100):
        m = (lo + hi) / 2
        if Q(m) > p:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# álgebra pequeña exacta (Gauss en ℚ) y Jacobi simétrico
# ---------------------------------------------------------------------------

def _gauss(A, b):
    """Sistema Ax = b exacto en ℚ (n pequeño); None si singular."""
    n = len(A)
    M = [[Fraction(A[i][j]) for j in range(n)] + [Fraction(b[i])] for i in range(n)]
    for col in range(n):
        piv = next((r for r in range(col, n) if M[r][col] != 0), None)
        if piv is None:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col] / M[col][col]
                M[r] = [x - f * y for x, y in zip(M[r], M[col])]
    return [M[i][n] / M[i][i] if M[i][i] != 0 else None for i in range(n)]


def _jacobi(A, sweeps=None):
    """Autovalores/vectores de simétrica real por rotaciones de Jacobi."""
    n = len(A)
    if sweeps is None:
        sweeps = 50 + 30 * n * n          # rotaciones de una en una: crece con n²
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    B = [[float(A[i][j]) for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        a, b, mx = 0, 1, 0.0
        for i in range(n):
            for j in range(i + 1, n):
                if abs(B[i][j]) > mx:
                    mx, a, b = abs(B[i][j]), i, j
        if mx < 1e-15:
            break
        # con B' = JᵀBJ el término cruzado es sc(x−y) + (c²−s²)z: se anula con
        # tan 2θ = −2z/(x−y). El signo contrario solo acertaba con x = y.
        th = 0.5 * math.atan2(-2 * B[a][b], B[a][a] - B[b][b])
        c, s = math.cos(th), math.sin(th)
        for i in range(n):
            if i not in (a, b):
                x, y = B[i][a], B[i][b]
                B[i][a] = B[a][i] = c * x - s * y
                B[i][b] = B[b][i] = s * x + c * y
        x, y, z = B[a][a], B[b][b], B[a][b]
        B[a][a] = c * c * x - 2 * s * c * z + s * s * y
        B[b][b] = s * s * x + 2 * s * c * z + c * c * y
        B[a][b] = B[b][a] = 0.0
        for i in range(n):
            x, y = V[i][a], V[i][b]
            V[i][a], V[i][b] = c * x - s * y, s * x + c * y
    lam = [B[i][i] for i in range(n)]
    # comprobación: A·v = λ·v para cada par propio (residuo relativo a ‖A‖)
    norma = max(1.0, max((abs(float(A[i][j])) for i in range(n) for j in range(n)), default=0))
    for k in range(n):
        for i in range(n):
            Av = sum(float(A[i][j]) * V[j][k] for j in range(n))
            if abs(Av - lam[k] * V[i][k]) > 1e-8 * norma:
                raise _error("DISCREPANT", "Jacobi: A·v ≠ λ·v (no ha convergido)")
    return lam, V


def _cholesky(R):
    """L con R = L·Lᵀ (definida positiva); None si no lo es."""
    n = len(R)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                v = R[i][i] - s
                if v <= 0:
                    return None
                L[i][j] = math.sqrt(v)
            else:
                L[i][j] = (R[i][j] - s) / L[j][j] if L[j][j] else 0.0
    return L


# ---------------------------------------------------------------------------
# correlación y PSD teórica (con D12)
# ---------------------------------------------------------------------------

def matriz_r(rs: list, trace: Trace | None = None) -> dict:
    """Toeplitz hermitiana desde r[0..p−1]; semidefinida positiva."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.matriz_r", "r[−k] = r*[k] y Toeplitz por estacionariedad",
                 why="WSS: la correlación solo depende del retardo (§4.16)")
    rs = [complex(_f(v[0]) if isinstance(v, (list, tuple)) else _f(v),
                  _f(v[1]) if isinstance(v, (list, tuple)) else 0.0)
          if isinstance(v, (list, tuple)) else complex(_f(v)) for v in rs]
    p = len(rs)
    if p < 1:
        raise _error("BAD_INPUT", "al menos r[0]")
    trace.hipotesis("sen.r_hermitica", "r[−k] = r*[k] (Toeplitz hermitiana)",
                    "cumple por construcción")
    R = [[rs[abs(i - j)] if i >= j else rs[abs(i - j)].conjugate()
          for j in range(p)] for i in range(p)]
    if any(abs(R[i][j] - R[j][i].conjugate()) > 1e-12 for i in range(p) for j in range(p)):
        raise _error("DISCREPANT", "R no hermitiana")
    vals, _ = _jacobi([[v.real for v in fila] for fila in R])
    if min(vals) < -1e-9 * max(1.0, max(vals)):
        raise _error("BAD_INPUT", "R no semidefinida positiva")
    for k in range(p):
        if abs(rs[k]) > abs(rs[0]) * (1 + 1e-9) + 1e-12:
            raise _error("DISCREPANT", f"|r[{k}]| > r[0]")
    trace.verificacion("sen.r_sdp",
                       f"autovalores ≥ 0; r[0] = {rs[0].real:.6g} ≥ |r[k]|")
    return {"R": R, "autovalores": vals}


def r_ar1(sigma2, a, p: int, trace: Trace | None = None) -> dict:
    """r[k] = σ²·a^|k|/(1−a²) del AR(1)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.r_ar1", "recursión r[k] = a·r[k−1] con r[0] = σ²/(1−a²)",
                 why="el AR(1) estacionario cierra la Yule-Walker de orden 1")
    s2, a = _f(sigma2), _f(a)
    if not (s2 > 0 and abs(a) < 1):
        raise _error("BAD_INPUT", "σ² > 0 y |a| < 1 (estacionario)")
    rs = [s2 * a ** abs(k) / (1 - a * a) for k in range(int(_Q(p)))]
    return matriz_r(rs, trace)


def psd_teorica(rs: list, n=512, trace: Trace | None = None) -> dict:
    """S(F) = Σ r[k]·e^{−j2πFk}; r[0] = ∫₀¹S dF (tiempo y frecuencia)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.psd", "Wiener-Khinchin discreta por suma finita",
                 why="la PSD teórica es la TF de r: dos dominios, un número")
    rs = [float(_Q(v)) for v in rs]
    def S(F):
        return sum(r * cmath.exp(-2j * math.pi * F * k)
                   for k, r in enumerate(rs)) + sum(
            r * cmath.exp(2j * math.pi * F * k) for k, r in enumerate(rs[1:], 1))
    vals = [S(k / n) for k in range(n)]
    if any(abs(v.imag) > 1e-9 * max(1.0, abs(v.real)) for v in vals):
        raise _error("DISCREPANT", "S(F) no real en proceso real")
    pot = sum(v.real for v in vals) / n
    if abs(pot - rs[0]) > 1e-6 * max(1.0, abs(rs[0])):
        raise _error("DISCREPANT", "r[0] ≠ ∫S dF")
    trace.verificacion("sen.psd_potencia", f"r[0] = ∫S = {pot:.6g}")
    return {"S": [v.real for v in vals], "potencia": pot}


def psd_salida(Sx: list, H: list, trace: Trace | None = None) -> dict:
    """S_y = S_x·|H|² punto a punto (D12)."""
    trace = trace if trace is not None else Trace()
    if len(Sx) != len(H):
        raise _error("BAD_INPUT", "S_x y H de igual longitud")
    if not Sx:
        raise _error("BAD_INPUT", "falta S_x")
    if any(float(_Q(v)) < 0 for v in Sx):
        raise _error("BAD_INPUT", "una PSD no es negativa")
    Sy = [float(_Q(s)) * abs(complex(h)) ** 2 for s, h in zip(Sx, H)]
    trace.verificacion("sen.psd_salida", f"S_y = S_x·|H|² en {len(Sy)} puntos")
    return {"Sy": Sy}


# ---------------------------------------------------------------------------
# detección: MAP/NP/ROC con señal conocida
# ---------------------------------------------------------------------------

def detector(s: list, sigma: float, Pfa: float,
             trace: Trace | None = None) -> dict:
    """Señal conocida en ruido blanco: T = sᵀx, d² = sᵀs/σ².

    Neyman-Pearson (fijar P_FA) y MAP/Bayes con a priori.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.detector", "estadístico suficiente T = sᵀx gaussiano; "
                 "el umbral lo fija P_FA (NP) o el coste con a priori (MAP)",
                 why="con ruido blanco el filtro adaptado comprime todo en "
                     "una gaussiana de distancia d (§4.16)")
    ss = [_f(v) for v in s]
    sg = _f(sigma)
    if not sg > 0:
        raise _error("BAD_INPUT", "σ > 0")
    if not 0 < Pfa < 1:
        raise _error("BAD_INPUT", "0 < P_FA < 1")
    trace.hipotesis("sen.det_ruido", "ruido blanco gaussiano conocido",
                    "cumple (la entrada lo declara)")
    d2 = sum(v * v for v in ss) / (sg * sg)
    d = math.sqrt(d2)
    umbral = Qinv(Pfa)  # sobre T/(σ·||s||): N(0,1) en H₀, N(d,1) en H₁
    Pd = Q(Qinv(Pfa) - d)
    # segundo camino: Monte Carlo sembrado de (P_FA, P_D)
    from academic_core.domain.engineering.mathlab import eventos as EV

    g = EV.Generador(20261007)
    n0 = n1 = f0 = f1 = 0
    N = 20000
    norma = math.sqrt(sum(v * v for v in ss))
    for _ in range(N):
        w = [sg * _muestra_normal(g) for _ in ss]
        x1 = [a + b for a, b in zip(ss, w)]
        t0 = sum(a * b for a, b in zip(ss, w)) / (sg * norma) if norma else 0.0
        t1 = sum(a * b for a, b in zip(ss, x1)) / (sg * norma) if norma else 0.0
        n0 += 1
        n1 += 1
        f0 += t0 > umbral
        f1 += t1 > umbral
    if abs(f0 / n0 - Pfa) > 0.02 or abs(f1 / n1 - Pd) > 0.02:
        raise _error("DISCREPANT", "Monte Carlo fuera de las tasas teóricas")
    trace.verificacion("sen.det_mc",
                       f"P_FA = {f0 / n0:.4g} (teórica {Pfa}), "
                       f"P_D = {f1 / n1:.4g} (teórica {Pd:.4g})")
    return {"d2": d2, "umbral": umbral, "Pfa": Pfa, "Pd": Pd,
            "roc": [(Q(Qinv(p) - d), p) for p in
                    [0.001, 0.01, 0.05, 0.1, 0.2, 0.5]]}


def _muestra_normal(g) -> float:
    u1 = max(g.uniforme(), 1e-12)
    u2 = g.uniforme()
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def _inversa(M):
    """Inversa por Gauss-Jordan con pivote parcial (float); None si singular."""
    n = len(M)
    A = [list(map(float, f)) + [1.0 if i == j else 0.0 for j in range(n)] for i, f in enumerate(M)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-14:
            return None
        A[c], A[piv] = A[piv], A[c]
        v = A[c][c]
        A[c] = [x / v for x in A[c]]
        for r in range(n):
            if r != c and A[r][c]:
                f = A[r][c]
                A[r] = [x - f * y for x, y in zip(A[r], A[c])]
    return [f[n:] for f in A]


def detector_map(s: list, sigma: float, p0: float, p1: float, costes=None,
                 trace: Trace | None = None) -> dict:
    """Umbral MAP/Bayes: γ = P(H₀)/P(H₁) (con costes, γ = (C10−C00)P₀/(C01−C11)P₁)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.det_map", "con a priori y costes manda Bayes; sin "
                 "ellos, Neyman-Pearson",
                 why="el criterio lo eligen los datos del problema, no el "
                     "método (§4.16)")
    p0, p1 = _f(p0), _f(p1)
    if not (p0 > 0 and p1 > 0):
        raise _error("BAD_INPUT", "a priori positivos")
    if costes is None:
        c00, c01, c10, c11 = 0.0, 1.0, 1.0, 0.0        # MAP: coste 0-1
    else:
        (c00, c01), (c10, c11) = [[_f(v) for v in fila] for fila in costes]
        if not (c10 > c00 and c01 > c11):
            raise _error("BAD_INPUT", "equivocarse tiene que costar más que acertar: "
                                      "C10 > C00 y C01 > C11")
    gamma = (c10 - c00) * p0 / ((c01 - c11) * p1)
    ss = [_f(v) for v in s]
    sg = _f(sigma)
    if not sg > 0:
        raise _error("BAD_INPUT", "σ > 0")
    d = math.sqrt(sum(v * v for v in ss)) / sg
    if d == 0:
        raise _error("BAD_INPUT", "señal nula: H₀ y H₁ no se distinguen")
    # z = sᵀx/(σ‖s‖) ~ N(0,1) en H₀ y N(d,1) en H₁; Λ(z) = e^{dz − d²/2} > γ ⇔ z > η
    eta = math.log(gamma) / d + d / 2

    def riesgo(u):
        pfa, pd = Q(u), Q(u - d)
        return (p0 * (c00 * (1 - pfa) + c10 * pfa) + p1 * (c11 * pd + c01 * (1 - pd)))

    R = riesgo(eta)
    trace.regla("sen.det_umbral", f"Λ(z) > γ ⇔ z > η = ln γ/d + d/2 = {eta:.6g} "
                                  f"(d = {d:.6g})",
                why="el cociente de verosimilitudes de dos gaussianas de igual "
                    "varianza es monótono en z")
    # segundo camino: minimizar el riesgo de Bayes en z por búsqueda de sección áurea
    lo, hi = eta - 10 - d, eta + 10 + d
    phi = (math.sqrt(5) - 1) / 2
    for _ in range(200):
        a_, b_ = hi - phi * (hi - lo), lo + phi * (hi - lo)
        if riesgo(a_) < riesgo(b_):
            hi = b_
        else:
            lo = a_
    if abs((lo + hi) / 2 - eta) > 1e-5 * max(1.0, abs(eta)):
        raise _error("DISCREPANT", f"el mínimo del riesgo está en {(lo + hi) / 2:.6g}, no en η")
    trace.verificacion("sen.det_gamma",
                       f"γ = {gamma:.6g}; η = {eta:.6g}; riesgo = {R:.6g} "
                       f"(mínimo comprobado por búsqueda)")
    return {"gamma": gamma, "eta": eta, "d": d, "riesgo": R}


# ---------------------------------------------------------------------------
# Fisher, Cramér-Rao, ML/MAP/MMSE
# ---------------------------------------------------------------------------

FISHER = {
    "gauss_media": "I = N/σ² (σ conocida)",
    "bernoulli": "I = N/(p(1−p))",
    "poisson": "I = N/λ",
}


def fisher(modelo: str, params: dict, trace: Trace | None = None) -> dict:
    """Información de Fisher cerrada + CRB = 1/I con condiciones."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.fisher", "log-verosimilitud → I = −E[∂²ln p/∂θ²]",
                 why="cada familia tiene su I cerrada; la cota es 1/I")
    if modelo == "gauss_media":
        N, s2 = _f(params.get("N", 10)), _f(params.get("sigma2", 1))
        if not (N > 0 and s2 > 0):
            raise _error("BAD_INPUT", "N, σ² > 0")
        I = N / s2
    elif modelo == "bernoulli":
        N, p = _f(params.get("N", 10)), _f(params.get("p", "1/2"))
        if not (N > 0 and 0 < p < 1):
            raise _error("BAD_INPUT", "N > 0, 0 < p < 1")
        I = N / (p * (1 - p))
    elif modelo == "poisson":
        N, lam = _f(params.get("N", 10)), _f(params.get("lambda", 1))
        if not (N > 0 and lam > 0):
            raise _error("BAD_INPUT", "N, λ > 0")
        I = N / lam
    else:
        raise _error("BAD_INPUT", "modelo gauss_media, bernoulli o poisson")
    # segundo camino: I = N·E[(∂/∂θ ln f(X; θ))²] sumando/integrando la ley
    if modelo == "gauss_media":
        from academic_core.domain.engineering.mathlab.calculo_extra import _simpson
        sd = math.sqrt(s2)
        I1 = _simpson(lambda x: (x / s2) ** 2 * math.exp(-x * x / (2 * s2))
                      / (sd * math.sqrt(2 * math.pi)), -12 * sd, 12 * sd, 4000)
    elif modelo == "bernoulli":
        I1 = p * (1 / p) ** 2 + (1 - p) * (1 / (1 - p)) ** 2
    else:
        I1, pk, k = 0.0, math.exp(-lam), 0
        while k < 50 + 20 * lam:
            I1 += pk * (k / lam - 1) ** 2
            k += 1
            pk *= lam / k
    if abs(N * I1 - I) > 1e-6 * I:
        raise _error("DISCREPANT", f"I por fórmula {I:.6g} ≠ por la esperanza {N * I1:.6g}")
    trace.hipotesis("sen.fisher_reg", "regularidad (soporte fijo, derivadas "
                    "bajo la esperanza)", "cumple en estos modelos")
    trace.verificacion("sen.fisher_crb", f"I = {I:.6g}; CRB = {1 / I:.6g}")
    return {"I": I, "CRB": 1 / I}


def gauss_conjunto(m_t: list, m_x: list, K_t: list, K_tx: list, K_x: list,
                   x_obs: list, trace: Trace | None = None) -> dict:
    """Estimador gaussiano: θ̂ = m_θ + K_θx·K_x⁻¹(x−m_x) con su error."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gauss_conj", "condicionar la conjunta: ML = MAP = MMSE",
                 why="en gaussiano los tres coinciden y la ortogonalidad "
                     "E[(θ−θ̂)xᵀ] = 0 los comprueba")
    Kx = [[_f(v) for v in fila] for fila in K_x]
    n = len(Kx)
    m_ = len(K_t)
    if n == 0 or m_ == 0 or any(len(f) != n for f in Kx) or len(x_obs) != n or \
            len(m_x) != n or len(m_t) != m_ or len(K_tx) != m_ or \
            any(len(f) != n for f in K_tx) or any(len(f) != m_ for f in K_t):
        raise _error("BAD_INPUT", "dimensiones: K_x n×n, K_θx m×n, K_θ m×m, x y m_x de n, "
                                  "m_θ de m")
    b = [float(_Q(xo) - _Q(mo)) for xo, mo in zip(x_obs, m_x)]
    w = _gauss([row[:] for row in Kx], b)
    if w is None or any(v is None for v in w):
        raise _error("BAD_INPUT", "K_x singular")
    Ktx = [[_f(v) for v in fila] for fila in K_tx]
    th = [float(m) + sum(Ktx[i][j] * w[j] for j in range(n)) for i, m in enumerate(m_t)]
    # error = K_θ − K_θx·K_x⁻¹·K_xθ: se resuelve por columnas de K_xθ
    Kt = [[_f(v) for v in fila] for fila in K_t]
    m_ = len(Kt)
    Err = []
    for i in range(m_):
        fila = []
        for j in range(m_):
            col = _gauss([row[:] for row in Kx], [Ktx[j][a] for a in range(n)])
            fila.append(Kt[i][j] - sum(Ktx[i][a] * col[a] for a in range(n)))
        Err.append(fila)
    # segundo camino: por la matriz de precisión conjunta Λ = Σ⁻¹,
    # θ̂ = m_θ − Λ_θθ⁻¹·Λ_θx·(x − m_x) y ECM = Λ_θθ⁻¹
    S = [[_f(v) for v in f] for f in K_t]
    S = [S[i] + [_f(v) for v in K_tx[i]] for i in range(m_)]
    S += [[_f(K_tx[j][i]) for j in range(m_)] + Kx[i] for i in range(n)]
    Lam = _inversa(S)
    if Lam is None:
        # θ queda determinado (en parte) por x: no hay precisión conjunta. Se
        # comprueba el principio de ortogonalidad, G·K_x = K_θx con G = K_θx·K_x⁻¹,
        # y que el ECM sea semidefinido positivo y no supere a K_θ
        G = [[sum(Ktx[i][a] * _gauss([row[:] for row in Kx],
                                     [1.0 if t == j else 0.0 for t in range(n)])[a]
                  for a in range(n)) for j in range(n)] for i in range(m_)]
        if any(abs(sum(G[i][a] * Kx[a][j] for a in range(n)) - Ktx[i][j]) >
               1e-9 * max(1.0, abs(Ktx[i][j])) for i in range(m_) for j in range(n)):
            raise _error("DISCREPANT", "el error no es ortogonal a las observaciones")
        lam_e, _ = _jacobi([[(Err[i][j] + Err[j][i]) / 2 for j in range(m_)] for i in range(m_)])
        if min(lam_e) < -1e-9 * max(1.0, max(abs(v) for f in Kt for v in f)) or                 any(Err[i][i] > Kt[i][i] + 1e-9 for i in range(m_)):
            raise _error("DISCREPANT", "ECM no semidefinido o mayor que la varianza a priori")
        trace.verificacion("sen.gauss_error",
                           "ECM = K_θ − K_θx·K_x⁻¹·K_xθ; error ortogonal a x, ECM ⪰ 0 "
                           "(θ determinado por x en parte: conjunta singular)")
        return {"theta_hat": th, "ECM": Err}
    Ltt = _inversa([fila[:m_] for fila in Lam[:m_]])
    th2 = [float(m_t[i]) - sum(Ltt[i][a] * sum(Lam[a][m_ + j] * b[j] for j in range(n))
                               for a in range(m_)) for i in range(m_)]
    esc = max(1.0, max(abs(v) for v in th))
    if any(abs(x - y) > 1e-7 * esc for x, y in zip(th, th2)) or \
            any(abs(Err[i][j] - Ltt[i][j]) > 1e-7 * max(1.0, abs(Ltt[i][j]))
                for i in range(m_) for j in range(m_)):
        raise _error("DISCREPANT", "θ̂ o el ECM no coinciden por la precisión conjunta")
    trace.verificacion("sen.gauss_error", "ECM = K_θ − K_θx·K_x⁻¹·K_xθ; θ̂ y ECM "
                                          "coinciden por la matriz de precisión conjunta")
    return {"theta_hat": th, "ECM": Err}


# ---------------------------------------------------------------------------
# Wiener, mínimos cuadrados, gradiente, LMS/NLMS
# ---------------------------------------------------------------------------

def wiener(R: list, p: list, sigma_d2: float,
           trace: Trace | None = None) -> dict:
    """Filtro de Wiener: R·w = p; J_min = σ_d² − pᴴw₀; residuos ortogonales."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.wiener", "Wiener-Hopf por Gauss exacta; el mínimo por "
                 "ortogonalidad E[e·x*] = 0",
                 why="el principio de ortogonalidad caracteriza al óptimo: "
                     "los residuos lo comprueban")
    Rf = [[_f(v) for v in fila] for fila in R]
    pf = [_f(v) for v in p]
    if len(Rf) != len(Rf[0]) or len(Rf) != len(pf):
        raise _error("BAD_INPUT", "R cuadrada y p a juego")
    trace.hipotesis("sen.wiener_R", "R definida positiva (WSS)", "se comprueba")
    w = _gauss([r[:] for r in Rf], pf)
    if w is None or any(v is None for v in w):
        raise _error("BAD_INPUT", "R singular: sin Wiener único")
    w = [float(v) for v in w]
    J = float(_Q(sigma_d2)) - sum(a * b for a, b in zip(pf, w))
    # residuos ortogonales a las columnas: R·w − p = 0
    res = [sum(Rf[i][j] * w[j] for j in range(len(w))) - pf[i] for i in range(len(w))]
    if max(abs(v) for v in res) > 1e-9 * max(1.0, max(abs(v) for v in pf)):
        raise _error("DISCREPANT", "R·w ≠ p")
    # J(w) ≥ J_min: basta un perturbado (la convexidad hace el resto)
    dw = [0.01] * len(w)
    Jp = float(_Q(sigma_d2)) - 2 * sum(
        pf[i] * (w[i] + dw[i]) for i in range(len(w))) + sum(
        (w[i] + dw[i]) * Rf[i][j] * (w[j] + dw[j])
        for i in range(len(w)) for j in range(len(w)))
    if Jp < J - 1e-9 * max(1.0, abs(J)):
        raise _error("DISCREPANT", "J(w perturbado) < J_min")
    trace.verificacion("sen.wiener_optimo",
                       f"J_min = {J:.6g}; residuos ortogonales")
    return {"w": w, "J_min": J}


def yule_walker(r0: float, r1: float, trace: Trace | None = None) -> dict:
    """Predicción AR(1) por Yule-Walker: a = r₁/r₀."""
    trace = trace if trace is not None else Trace()
    r0, r1 = _f(r0), _f(r1)
    if r0 <= 0:
        raise _error("BAD_INPUT", "r₀ > 0")
    if not abs(r1) < r0:
        raise _error("BAD_INPUT", "|r₁| < r₀: si no, no es la autocorrelación de un AR(1) "
                                  "estacionario")
    a = r1 / r0
    s2 = r0 * (1 - a * a)
    # segundo camino: el AR(1) con (σ², a) reproduce r₀ y r₁
    rr = r_ar1(s2, a, 2, Trace())["R"][0]
    if abs(complex(rr[0]).real - r0) > 1e-9 * r0 or abs(complex(rr[1]).real - r1) > 1e-9 * r0:
        raise _error("DISCREPANT", "el AR(1) de Yule-Walker no reproduce r₀, r₁")
    trace.verificacion("sen.yw_coef", f"a = r₁/r₀ = {a:.6g}; σ² = r₀(1 − a²) = {s2:.6g}; "
                                      f"el AR(1) reproduce r₀ y r₁")
    return {"a": a, "sigma2": s2}


def gradiente_modos(R: list, mu: float, trace: Trace | None = None) -> dict:
    """Descenso sobre J: modos (1−μλᵢ)ᵏ, cota 0 < μ < 2/λ_max, τᵢ."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gradiente", "diagonalizar R = QΛQᴴ y leer los modos",
                 why="en la base propia cada coordenada decae con su (1−μλᵢ)ᵏ")
    Rf = [[_f(v) for v in fila] for fila in R]
    mu = _f(mu)
    lam, _ = _jacobi(Rf)
    if min(lam) <= 0:
        raise _error("BAD_INPUT", "R definida positiva")
    lmax = max(lam)
    trace.hipotesis("sen.grad_mu", f"0 < μ = {mu} < 2/λ_max = {2 / lmax:.4g}",
                    "cumple" if 0 < mu < 2 / lmax else "FALLA: diverge")
    if not 0 < mu < 2 / lmax:
        raise _no(f"μ fuera de (0, 2/λ_max): diverge (se ve, no se itera)")
    # el modo k decae como |1 − μλ_k|ⁿ (con 1 < μλ < 2 oscila, y sigue convergiendo)
    taus = [0.0 if abs(1 - mu * l) < 1e-15 else -1 / math.log(abs(1 - mu * l)) for l in lam]
    if abs(sum(lam) - sum(Rf[i][i] for i in range(len(Rf)))) > 1e-9 * max(1.0, sum(lam)):
        raise _error("DISCREPANT", "Σλ ≠ tr(R)")
    trace.verificacion("sen.grad_modos",
                       f"dispersión λ_max/λ_min = {lmax / min(lam):.4g}")
    return {"lambdas": lam, "taus": taus,
            "dispersion": lmax / min(lam)}


def lms(R: list, p: list, mu: float, pasos: int = 200, realiz: int = 200,
        semilla: int = 7, trace: Trace | None = None) -> dict:
    """LMS w(n+1) = w(n) + μ·e*·x: E[w] y J(n) frente a la teoría.

    Con μ sobre la cota se ve la divergencia (no se esconde).
    """
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.lms", "ecuación en diferencias de E[w(n)] + Monte Carlo "
                 "sembrado frente a la teoría",
                 why="la media sigue los modos (1−μλᵏ) y la simulación lo mide")
    Rf = [[_f(v) for v in fila] for fila in R]
    pf = [_f(v) for v in p]
    mu = _f(mu)
    n = len(Rf)
    lam, _ = _jacobi(Rf)
    lmax = max(lam)
    if not mu > 0:
        raise _error("BAD_INPUT", "μ > 0")
    if mu >= 2 / lmax:
        trace.aviso("sen.lms_diverge", f"μ = {mu} ≥ 2/λ_max: diverge")
    L = _cholesky(Rf)
    if L is None:
        raise _error("BAD_INPUT", "R no definida positiva")
    sd2 = 1.0
    Ew = [[0.0] * n for _ in range(pasos + 1)]
    J = [0.0] * (pasos + 1)
    g = EV.Generador(int(semilla))
    w0 = [float(v) for v in _gauss([r[:] for r in Rf], pf)]
    for _ in range(realiz):
        w = [0.0] * n
        for t in range(pasos + 1):
            z = [_gauss_box(g) for _ in range(n)]
            x = [sum(L[i][j] * z[j] for j in range(n)) for i in range(n)]
            # modelo: d = w₀ᵀx + v con w₀ = R⁻¹p y v ~ N(0,1)
            d = sum(w0[i] * x[i] for i in range(n)) + _gauss_box(g)
            e_ = d - sum(w[i] * x[i] for i in range(n))
            for i in range(n):
                Ew[t][i] += w[i] / realiz
            J[t] += e_ * e_ / realiz
            for i in range(n):
                w[i] += mu * e_ * x[i]
    # teoría: E[w(n)] = (I − (I − μR)ⁿ)·w₀ desde w(0) = 0 (x independiente en el tiempo)
    Jmin = sd2
    if not mu >= 2 / lmax:
        Ew_t = [0.0] * n
        for _ in range(pasos):
            Ew_t = [Ew_t[i] - mu * sum(Rf[i][j] * Ew_t[j] for j in range(n)) + mu * pf[i]
                    for i in range(n)]
        tol = 10 * math.sqrt(mu * Jmin * max(1.0, lmax) / realiz) + 1e-3
        if any(abs(a - b) > tol * max(1.0, abs(b)) for a, b in zip(Ew[-1], Ew_t)):
            raise _error("DISCREPANT", "la media de LMS no sigue la teoría (I − (I−μR)ⁿ)w₀")
    trace.verificacion("sen.lms_curva",
                       f"J(0) = {J[0]:.4g} → J({pasos}) = {J[-1]:.4g} "
                       f"(J_min = {Jmin:.4g})")
    return {"Ew_final": Ew[-1], "J": J, "w0": w0, "diverge": mu >= 2 / lmax}


def _gauss_box(g) -> float:
    u1 = max(g.uniforme(), 1e-12)
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * g.uniforme())


def nlms_cota(R: list, trace: Trace | None = None) -> dict:
    """NLMS: 0 < μ̃ < 2 con traza como cota práctica 2/tr(R)."""
    trace = trace if trace is not None else Trace()
    if not R or any(len(f) != len(R) for f in R):
        raise _error("BAD_INPUT", "R cuadrada no vacía")
    tr = sum(_f(R[i][i]) for i in range(len(R)))
    if not tr > 0:
        raise _error("BAD_INPUT", "tr(R) > 0 (R es una autocorrelación)")
    trace.verificacion("sen.nlms_cota",
                       f"0 < μ̃ < 2; práctica μ̃ < 2/tr(R) = {2 / tr:.4g}")
    return {"cota_practica": 2 / tr}
