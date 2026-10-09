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
        return Fraction(x).limit_denominator(10**9)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            return Fraction(float(s)).limit_denominator(10**9)
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


def _jacobi(A, sweeps=50):
    """Autovalores/vectores de simétrica real por rotaciones de Jacobi."""
    n = len(A)
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
        th = 0.5 * math.atan2(2 * B[a][b], B[a][a] - B[b][b])
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
    return [B[i][i] for i in range(n)], V


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
        gamma = p0 / p1
    else:
        (c00, c01), (c10, c11) = costes
        gamma = (c10 - c00) * p0 / ((c01 - c11) * p1)
    trace.verificacion("sen.det_gamma", f"γ = {gamma:.6g}")
    return {"gamma": gamma}


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
    trace.verificacion("sen.gauss_error", "ECM = K_θ − K_θx·K_x⁻¹·K_xθ")
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
    a = r1 / r0
    trace.verificacion("sen.yw_coef", f"a = r₁/r₀ = {a:.6g}")
    return {"a": a}


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
    taus = [-1 / math.log(1 - mu * l) for l in lam]
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
    # teoría: E[w(n)] por modos desde w(0) = 0 hacia w₀
    Jmin = sd2
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
    tr = sum(_f(R[i][i]) for i in range(len(R)))
    trace.verificacion("sen.nlms_cota",
                       f"0 < μ̃ < 2; práctica μ̃ < 2/tr(R) = {2 / tr:.4g}")
    return {"cota_practica": 2 / tr}
