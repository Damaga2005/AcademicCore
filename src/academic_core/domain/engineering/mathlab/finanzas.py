# SPDX-License-Identifier: MIT
"""ML-21, bloque 14 (G): interés, VAN/TIR, bonos, futuros, opciones
(CRR, Black-Scholes, Monte Carlo) y Markowitz con su frontera eficiente.

Convenciones declaradas (§5.11): ``r`` es la tasa **nominal** anual
repartida en ``m`` capitalizaciones (la periódica es ``r/m`` y la TAE
``(1+r/m)^m − 1``); Florida continua ``e^{rt}``; Markowitz **con cortos**
(sin cortos la frontera es cuadrática y no se resuelve: se avisa). Todo
determinista; el azar sembrado sale del Generador de ``eventos``.
"""

from __future__ import annotations

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


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _NORMAL():
    """Normal estándar, reutilizada (VaR necesita su cuantil)."""
    from statistics import NormalDist

    return NormalDist()


# ---------------------------------------------------------------------------
# interés
# ---------------------------------------------------------------------------

def interes(C0, r, t, modo="compuesto", m=1, trace: Trace | None = None) -> dict:
    """Simple, compuesto (m veces), continuo; TAE y regla del 72."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.interes", "elegir la composición y aplicar su fórmula",
                 why="cada capitalización tiene su fórmula cerrada (§4.14)")
    C0, r, t = _f(C0), _f(r), _f(t)
    if not (C0 >= 0 and t >= 0):
        raise _error("BAD_INPUT", "C₀, t ≥ 0")
    trace.hipotesis("sen.interes_tasa", "tasa constante en el periodo", "cumple")
    if modo == "simple":
        C = C0 * (1 + r * t)
    elif modo == "compuesto":
        m = _f(m)
        C = C0 * (1 + r / m) ** (m * t)
    elif modo == "continuo":
        C = C0 * math.exp(r * t)
    else:
        raise _error("BAD_INPUT", "modo simple, compuesto o continuo")
    # segundo camino: periodo a periodo frente a la fórmula cerrada. Con
    # m·t entero son m·t periodos completos; si no, el último va fraccionado
    # (despejar_tiempo devuelve t no entero y sin esto el control mentía).
    if modo == "compuesto":
        p = r / m
        n = int(m * t)
        cm = C0
        for _ in range(n):
            cm *= 1 + p
        if n < m * t:
            cm *= (1 + p) ** (m * t - n)
        if abs(cm - C) > 1e-9 * max(1.0, abs(C)):
            raise _error("DISCREPANT", "periodo a periodo ≠ fórmula")
    # TAE: la efectiva de un año según el modo (en simple es la propia r)
    if modo == "compuesto":
        tae = (1 + r / m) ** m - 1
    elif modo == "continuo":
        tae = math.exp(r) - 1
    else:
        tae = r
    trace.verificacion("sen.interes_tae", f"C = {C:.6g}; TAE = {tae:.6g}")
    return {"C": C, "TAE": tae, "regla72": 72 / (r * 100) if r > 0 else None}


def despejar_tiempo(C0, C, r, modo="compuesto", m=1,
                    trace: Trace | None = None) -> dict:
    """Tiempo para llegar a C con ln (continuo/compuesto)."""
    trace = trace if trace is not None else Trace()
    C0, C, r = _f(C0), _f(C), _f(r)
    if not (C0 > 0 and C > 0 and r > 0):
        raise _error("BAD_INPUT", "C₀, C, r > 0")
    m = _f(m)
    t = math.log(C / C0) / (m * math.log(1 + r / m)) if modo == "compuesto" \
        else math.log(C / C0) / r
    if abs(interes(C0, r, t, modo, m, Trace())["C"] - C) > 1e-9 * C:
        raise _error("DISCREPANT", "el tiempo no devuelve el capital")
    trace.verificacion("sen.interes_despeje", f"t = {t:.6g} redondea el ciclo")
    return {"t": t}


# ---------------------------------------------------------------------------
# VAN, TIR, anualidades, amortización
# ---------------------------------------------------------------------------

def van(flujos: list, r, trace: Trace | None = None) -> dict:
    """VAN por la línea temporal con factor de descuento."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.van", "cada flujo descontado a su periodo y suma",
                 why="el valor temporal es el factor (1+r)^−t (§4.14)")
    r = _f(r)
    if not r > -1:
        raise _error("BAD_INPUT", "r > −1")
    F = [_f(v) for v in flujos]
    if not F:
        raise _error("BAD_INPUT", "faltan los flujos")
    V = sum(f / (1 + r) ** t for t, f in enumerate(F))
    # segundo camino: Horner hacia atrás, V = F₀ + (F₁ + (F₂ + …)/(1+r))/(1+r)
    h = 0.0
    for f in reversed(F):
        h = f + h / (1 + r)
    if abs(h - V) > 1e-9 * max(1.0, sum(abs(f) for f in F)):
        raise _error("DISCREPANT", "VAN por suma y por Horner difieren")
    trace.verificacion("sen.van_linea", f"VAN = {V:.6g}")
    return {"VAN": V}


def _cambios_signo(xs: list) -> int:
    return sum(1 for a, b in zip(xs, xs[1:]) if a == 0 or b == 0 or (a < 0) != (b < 0))


def tir(flujos: list, trace: Trace | None = None) -> dict:
    """TIR por bisección; un solo cambio de signo ⇒ única (Descartes)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.tir", "bisección en el cambio de signo acotado",
                 why="VAN continua y monótona entre cambios: la bisección la "
                     "encierra (§4.14)")
    F = [_f(v) for v in flujos]
    n = _cambios_signo([v for v in F if v != 0])
    trace.hipotesis("sen.tir_descartes",
                    f"{n} cambio(s) de signo" + (" ⇒ TIR única" if n == 1 else ""),
                    "cumple" if n == 1 else "varias TIR posibles (se avisa)")
    lo, hi = -0.9999, 10.0
    vlo = sum(f / (1 + lo) ** t for t, f in enumerate(F))
    vhi = sum(f / (1 + hi) ** t for t, f in enumerate(F))
    if vlo * vhi > 0:
        raise _no("sin cambio de signo acotado: no hay TIR que encerrar")
    for _ in range(200):
        m = (lo + hi) / 2
        if sum(f / (1 + m) ** t for t, f in enumerate(F)) * vlo <= 0:
            hi = m
        else:
            lo = m
    r = (lo + hi) / 2
    if abs(sum(f / (1 + r) ** t for t, f in enumerate(F))) > 1e-6 * max(1.0, abs(F[0])):
        raise _error("DISCREPANT", "VAN(TIR) ≠ 0")
    trace.verificacion("sen.tir_cero", f"VAN({r:.10g}) = 0")
    return {"TIR": r, "cambios": n}


def anualidad(A, r, n, trace: Trace | None = None) -> dict:
    """Cuota de amortización: A·r/(1−(1+r)^−n)."""
    trace = trace if trace is not None else Trace()
    A, r = _f(A), _f(r)
    n = int(_Q(n))
    if not (A > 0 and r > 0 and n > 0):
        raise _error("BAD_INPUT", "A, r, n > 0")
    c = A * r / (1 - (1 + r) ** -n)
    # segundo camino: simular la tabla de amortización; el saldo tras n
    # cuotas es 0 (comprobación real, no una identidad tautológica)
    saldo, pagado = A, 0.0
    for _ in range(n):
        saldo += saldo * r - c
        pagado += c
    if abs(saldo) > 1e-9 * max(1.0, A):
        raise _error("DISCREPANT", f"saldo final {saldo:g} ≠ 0")
    trace.verificacion("sen.anualidad_cuadre",
                       f"cuota {c:.6g}; saldo tras n cuotas = 0")
    return {"cuota": c, "total": pagado, "intereses": pagado - A}


# ---------------------------------------------------------------------------
# bonos
# ---------------------------------------------------------------------------

def bono(flujos: list, y, trace: Trace | None = None) -> dict:
    """Precio, duración de Macaulay/modificada y convexidad."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bono", "descontar cada flujo; ∂P/∂y del sumatorio",
                 why="el precio es la suma descontada y la duración su "
                     "elasticidad (§4.14)")
    F = [_f(v) for v in flujos]
    y = _f(y)
    if not F:
        raise _error("BAD_INPUT", "flujos vacíos: no hay bono que valorar")
    if y <= -1:
        raise _error("BAD_INPUT", "y > −1")
    trace.convencion("sen.bono_tiempos",
                     "flujos[k] vence en t = k periodos: el primero es HOY (t = 0) y no "
                     "se descuenta; un bono que paga desde t = 1 empieza por 0")
    P = sum(f / (1 + y) ** t for t, f in enumerate(F))
    if P == 0:
        # sin precio no hay duración ni convexidad que dividir: se rechaza
        # con motivo en vez de devolver ceros o reventar con ZeroDivision
        raise _error("BAD_INPUT",
                     f"el precio del bono sale 0 (flujos {F}): duración y "
                     f"convexidad no están definidas")
    D = sum(t * f / (1 + y) ** t for t, f in enumerate(F)) / P
    Dmod = D / (1 + y)
    C = sum(t * (t + 1) * f / (1 + y) ** (t + 2) for t, f in enumerate(F)) / P
    # segundo camino: derivada numérica de P(y) frente a la duración
    h = 1e-6
    P2 = sum(f / (1 + y + h) ** t for t, f in enumerate(F))
    if abs(-(P2 - P) / h / P - Dmod) > 1e-4 * max(1.0, abs(Dmod)):
        raise _error("DISCREPANT", "duración ≠ −P′/P")
    trace.verificacion("sen.bono_duracion",
                       f"P = {P:.6g}; D = {D:.6g}; convexidad {C:.6g}")
    return {"P": P, "duracion": D, "modificada": Dmod, "convexidad": C}


# ---------------------------------------------------------------------------
# futuros, opciones CRR, Black-Scholes, Monte Carlo
# ---------------------------------------------------------------------------

def futuro(S0, r, T, trace: Trace | None = None) -> dict:
    """F = S₀·e^{rT}; el contrato vale 0 al inicio (arbitraje)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.futuro", "capitalizar el spot a T",
                 why="sin fricciones ni arbitraje: el futuro replica el spot")
    S0, r, T = _f(S0), _f(r), _f(T)
    F = S0 * math.exp(r * T)
    # segundo camino: la cartera réplica (comprar el spot y PEDIR prestado
    # el valor presente del futuro) vale 0: S₀ − F·e^{−rT} = 0
    if abs(S0 - F * math.exp(-r * T)) > 1e-9 * max(1.0, S0):
        raise _error("DISCREPANT", "la réplica del futuro no vale 0")
    trace.verificacion("sen.futuro_cero",
                       f"F = {F:.6g}; S₀ − F·e^{{-rT}} = 0 (valor inicial 0)")
    return {"F": F}


def payoff(S, K, tipo="call", trace: Trace | None = None) -> dict:
    """Payoff europeo: max(S−K,0) / max(K−S,0)."""
    trace = trace if trace is not None else Trace()
    S, K = _f(S), _f(K)
    if tipo == "call":
        v = max(S - K, 0.0)
    elif tipo == "put":
        v = max(K - S, 0.0)
    else:
        raise _error("BAD_INPUT", "tipo call o put")
    trace.verificacion("sen.payoff_max", f"payoff = {v:.6g}")
    return {"payoff": v}


def crr(S0, K, r, sigma, T, n, tipo="call", americana=False,
        trace: Trace | None = None, _comprobar: bool = True) -> dict:
    """Árbol CRR con u, d, q; americanas comparan con ejercicio inmediato."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.crr", "árbol de precios → payoffs en hojas → retroceso "
                 "descontado (con ejercicio si americana)",
                 why="valoración por réplica discreta sin arbitraje (§4.14)")
    S0, K, r, sg, T = _f(S0), _f(K), _f(r), _f(sigma), _f(T)
    n = int(_Q(n))
    if not (n >= 1 and sg > 0 and T > 0):
        raise _error("BAD_INPUT", "n ≥ 1, σ, T > 0")
    dt = T / n
    u = math.exp(sg * math.sqrt(dt))
    d = 1 / u
    q = (math.exp(r * dt) - d) / (u - d)
    trace.hipotesis("sen.crr_noarb", f"0 < q = {q:.6g} < 1",
                    "cumple" if 0 < q < 1 else "FALLA: arbitraje")
    if not 0 < q < 1:
        raise _error("BAD_INPUT", "d < e^{rΔt} < u para no arbitraje")
    S = [[S0 * u ** (i - j) * d ** j for j in range(i + 1)] for i in range(n + 1)]
    V = [payoff(s, K, tipo)["payoff"] for s in S[n]]
    for i in range(n - 1, -1, -1):
        V = [math.exp(-r * dt) * (q * V[j] + (1 - q) * V[j + 1]) for j in range(i + 1)]
        if americana:
            V = [max(v, payoff(s, K, tipo)["payoff"]) for v, s in zip(V, S[i])]
    # segundos caminos: europea → paridad put-call exacta en el árbol;
    # americana → nunca vale menos que la europea ni que ejercer ya
    if not _comprobar:
        return {"precio": V[0], "u": u, "d": d, "q": q}
    if not americana:
        otro = crr(S0, K, r, sg, T, n, "put" if tipo == "call" else "call", False, Trace(),
                   _comprobar=False)
        c_, p_ = (V[0], otro["precio"]) if tipo == "call" else (otro["precio"], V[0])
        if abs((c_ - p_) - (S0 - K * math.exp(-r * T))) > 1e-9 * max(1.0, S0, K):
            raise _error("DISCREPANT", "el árbol no cumple la paridad put-call")
    else:
        euro = crr(S0, K, r, sg, T, n, tipo, False, Trace(), _comprobar=False)["precio"]
        if V[0] < euro - 1e-12 or V[0] < payoff(S0, K, tipo)["payoff"] - 1e-12:
            raise _error("DISCREPANT", "la americana vale menos que la europea o que ejercer")
    trace.verificacion("sen.crr_hojas", f"precio = {V[0]:.6g} con n = {n}")
    return {"precio": V[0], "u": u, "d": d, "q": q}


def black_scholes(S0, K, r, sigma, T, tipo="call",
                  trace: Trace | None = None) -> dict:
    """BSM europeo con griegas; paridad put-call como control."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs", "d₁ → d₂ → Φ con la normal del bloque 6",
                 why="fórmula cerrada bajo GBM con σ, r constantes")
    S0, K, r, sg, T = _f(S0), _f(K), _f(r), _f(sigma), _f(T)
    if not (S0 > 0 and K > 0 and sg > 0 and T > 0):
        raise _error("BAD_INPUT", "S₀, K, σ, T > 0")
    trace.hipotesis("sen.bs_hip", "GBM; europea; sin dividendos", "cumple")
    d1 = (math.log(S0 / K) + (r + sg * sg / 2) * T) / (sg * math.sqrt(T))
    d2 = d1 - sg * math.sqrt(T)
    disc = math.exp(-r * T)
    if tipo == "call":
        P = S0 * _phi(d1) - K * disc * _phi(d2)
    elif tipo == "put":
        P = K * disc * _phi(-d2) - S0 * _phi(-d1)
    else:
        raise _error("BAD_INPUT", "tipo call o put")
    delta = _phi(d1) if tipo == "call" else _phi(d1) - 1
    gamma = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (S0 * sg * math.sqrt(T))
    vega = S0 * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(T)
    # paridad C − P = S₀ − K·e^{−rT}
    call = S0 * _phi(d1) - K * disc * _phi(d2)
    put = K * disc * _phi(-d2) - S0 * _phi(-d1)
    if abs((call - put) - (S0 - K * disc)) > 1e-9 * max(1.0, S0):
        raise _error("DISCREPANT", "paridad put-call falla")
    trace.verificacion("sen.bs_paridad", f"C − P = S₀ − Ke^{{-rT}}")
    return {"precio": P, "d1": d1, "d2": d2, "delta": delta, "gamma": gamma,
            "vega": vega}


def vol_implicita(precio, S0, K, r, T, tipo="call",
                  trace: Trace | None = None) -> dict:
    """σ implícita por Newton sobre la vega (siempre positiva: unicidad)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.volimpl", "Newton en σ con la vega como derivada",
                 why="vega > 0 siempre: el cero es único (§4.14)")
    sg = 0.5
    for _ in range(100):
        bs = black_scholes(S0, K, r, sg, T, tipo, Trace())
        f = bs["precio"] - _f(precio)
        if abs(f) < 1e-10 * max(1.0, abs(_f(precio))):
            break
        sg -= f / bs["vega"]
        if sg <= 0:
            sg = 0.01
    if abs(black_scholes(S0, K, r, sg, T, tipo, Trace())["precio"] - _f(precio)) > \
            1e-6 * max(1.0, abs(_f(precio))):
        raise _error("DISCREPANT", "no converge a ese precio")
    trace.verificacion("sen.volimpl_unica", f"σ = {sg:.6g}")
    return {"sigma": sg}


def montecarlo_opcion(S0, K, r, sigma, T, N=20000, semilla=7, tipo="call",
                      trace: Trace | None = None) -> dict:
    """MC con Z ~ N(0,1) sembrada; error ∝ 1/√N con intervalo."""
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mc", "S_T lognormal exacta + payoff + media descontada",
                 why="sin discretizar: la ley de S_T es cerrada y la semilla "
                     "la reproduce")
    S0, K, r, sg, T = _f(S0), _f(K), _f(r), _f(sigma), _f(T)
    N = int(_Q(N))
    if N < 100:
        raise _error("BAD_INPUT", "N ≥ 100")
    g = EV.Generador(int(semilla))
    tot = tot2 = 0.0
    for _ in range(N):
        u1 = max(g.uniforme(), 1e-12)
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * g.uniforme())
        ST = S0 * math.exp((r - sg * sg / 2) * T + sg * math.sqrt(T) * z)
        po = max(ST - K, 0.0) if tipo == "call" else max(K - ST, 0.0)
        tot += po
        tot2 += po * po
    media = tot / N
    var = max(tot2 / N - media * media, 0.0)
    err = math.exp(-r * T) * math.sqrt(var / N)
    precio = math.exp(-r * T) * media
    # segundo camino: Black-Scholes cerrado tiene que caer en ±5 errores típicos
    bs = black_scholes(S0, K, r, sg, T, tipo, Trace())["precio"]
    if abs(precio - bs) > 5 * err + 1e-12:
        raise _error("DISCREPANT", f"Monte Carlo {precio:.6g} lejos de Black-Scholes {bs:.6g}")
    trace.verificacion("sen.mc_error",
                       f"precio {precio:.6g} ± {err:.3g} (1/√N)")
    return {"precio": precio, "error": err}


# ---------------------------------------------------------------------------
# Markowitz
# ---------------------------------------------------------------------------

def _dir_tangente(mu, n):
    """d no nula con 1ᵀd = 0 y μᵀd = 0, exacta por eliminación en ℚ.

    None si no existe (n < 3, o μ constante): entonces las dos restricciones
    fijan w y la unicidad ya hace de verificación.
    """
    M = [[Fraction(1)] * n, list(mu)]
    piv, col = [], 0
    for f in range(2):
        p = next((c for c in range(col, n) if M[f][c] != 0), None)
        if p is None:
            return None
        piv.append(p)
        M[f] = [x / M[f][p] for x in M[f]]
        for r in range(2):
            if r != f and M[r][p] != 0:
                k = M[r][p]
                M[r] = [x - k * y for x, y in zip(M[r], M[f])]
        col = p + 1
    libre = next(c for c in range(n) if c not in piv)
    d = [Fraction(0)] * n
    d[libre] = Fraction(1)
    for f in reversed(range(2)):
        d[piv[f]] = -sum(M[f][c] * d[c] for c in range(n) if c != piv[f])
    return d if any(d) else None


def markowitz(mu, Sigma, m=None, trace: Trace | None = None) -> dict:
    """Cartera de mínima varianza / con retorno m (KKT lineal, con cortos)."""
    from academic_core.domain.engineering.mathlab import deteccion as DT

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.markowitz", "lagrangiano con wᵀ1 = 1 (y wᵀμ = m): KKT "
                 "lineal exacto en ℚ",
                 why="con cortos es un sistema lineal; sin cortos sería "
                     "cuadrática y se avisa (§4.14)")
    mu = [_Q(v) for v in mu]
    Sg = [[_Q(v) for v in fila] for fila in Sigma]
    n = len(mu)
    if n == 0:
        raise _error("BAD_INPUT", "faltan μ y Σ: la cartera necesita al menos un activo")
    if len(Sg) != n or any(len(f) != n for f in Sg):
        raise _error("BAD_INPUT", "Σ n×n con μ de n")
    # Hipótesis que sí se comprueba: Σ definida positiva por el criterio de
    # Sylvester (menores principales-leading > 0). Sin ella, «mínima
    # varianza» no es un mínimo y la frontera no tiene sentido.
    D = [[Sg[i][j] for j in range(n)] for i in range(n)]
    for k in range(1, n + 1):
        L = [[D[i][j] for j in range(k)] for i in range(k)]
        piv = []
        det = Fraction(1)
        ok = True
        for c in range(k):
            p = next((r for r in range(c, k) if L[r][c] != 0), None)
            if p is None:
                ok = False
                break
            L[c], L[p] = L[p], L[c]
            det *= L[c][c]
            for r in range(c + 1, k):
                f = L[r][c] / L[c][c]
                L[r] = [x - f * y for x, y in zip(L[r], L[c])]
        if not ok or det <= 0:
            raise _error("BAD_INPUT",
                         f"Σ no es definida positiva (menor principal de orden {k})")
    trace.hipotesis("sen.mark_defpos",
                    f"Σ definida positiva (Sylvester: {n} menores > 0)",
                    "cumple")
    uno = [Fraction(1)] * n
    if m is None:
        # mínima varianza: w = Σ⁻¹1/(1ᵀΣ⁻¹1)
        w = DT._gauss([r[:] for r in Sg], uno)
        if w is None or any(v is None for v in w):
            raise _error("BAD_INPUT", "Σ singular")
        den = sum(w)
        w = [v / den for v in w]
        # segundo camino: en el mínimo, Σw = λ·1 (todas las componentes iguales)
        Sw = [sum(Sg[i][j] * w[j] for j in range(n)) for i in range(n)]
        if any(v != Sw[0] for v in Sw):
            raise _error("DISCREPANT", "Σw no es proporcional a 1: no es el mínimo")
    else:
        m = _Q(m)
        A = [[Sg[i][j] for j in range(n)] + [-mu[i], -uno[i]] for i in range(n)]
        A += [[-mu[j] for j in range(n)] + [Fraction(0), Fraction(0)]]
        A += [[-uno[j] for j in range(n)] + [Fraction(0), Fraction(0)]]
        b = [Fraction(0)] * n + [-m, -1]
        w = DT._gauss([r[:] for r in A], b)
        if w is None or any(v is None for v in w):
            raise _error("BAD_INPUT", "KKT singular")
        w = w[:n]
    if sum(w) == 0 or abs(sum(w) - 1) > Fraction(1, 10 ** 9):
        raise _error("DISCREPANT", "wᵀ1 ≠ 1")
    mu_p = sum(a * b for a, b in zip(w, mu))
    var_p = sum(w[i] * Sg[i][j] * w[j] for i in range(n) for j in range(n))
    # segundo camino: la estacionariedad 2Σw = λ1 + νμ implica que el
    # gradiente es ORTOGONAL a toda dirección factible, es decir a las d con
    # 1ᵀd = 0 y μᵀd = 0. Se busca una d no nula en ese espacio tangente y se
    # comprueba 2Σw·d = 0; con n = 2 las dos restricciones fijan w y no hay
    # dirección factible (la unicidad ya es la verificación).
    if m is not None and n >= 3:
        d = _dir_tangente(mu, n)
        if d is not None:
            izq = 2 * sum(w[i] * Sg[i][j] * d[j]
                          for i in range(n) for j in range(n))
            if izq != 0:
                raise _error("DISCREPANT",
                             f"2Σw·d = {float(izq):g} ≠ 0 en una dirección factible")
    trace.verificacion("sen.mark_kkt", f"wᵀ1 = 1; μₚ = {float(mu_p):.6g}")
    return {"w": w, "mu_p": mu_p, "var_p": var_p}


def frontera_eficiente(mu, Sigma, puntos=15, trace: Trace | None = None) -> dict:
    """Frontera eficiente barriendo el retorno objetivo y quedarse con la
    parte no decreciente de σ(m).

    Cada punto sale del mismo KKT lineal exacto de :func:`markowitz`; los
    objetivos fuera de [min μ, max μ] no son alcanzables y se descartan.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.frontera", "barrido de m con el KKT de markowitz; se "
                 "queda con la rama σ creciente",
                 why="la frontera es el lugar de mínima varianza para cada "
                     "retorno exigido (§4.14)")
    mus = [_Q(v) for v in mu]
    lo, hi = min(mus), max(mus)
    if hi == lo:
        raise _error("BAD_INPUT", "todos los μ son iguales: no hay frontera")
    curva = []
    for k in range(int(puntos)):
        m = lo + (hi - lo) * Fraction(k, max(int(puntos) - 1, 1))
        r = markowitz(mus, Sigma, m, Trace())
        curva.append((r["mu_p"], r["var_p"], r["w"]))
    # la rama eficiente es la que no empeora: desde el mínimo de varianza
    # hacia el mayor μ disponible, σ² no baja
    vs = [c[1] for c in curva]
    i_min = min(range(len(vs)), key=lambda i: vs[i])
    frontera = curva[i_min:]
    # segundo camino: (a) σ² no baja a lo largo de la rama; (b) cada punto es
    # un mínimo de verdad: se mueve la cartera por una dirección factible d
    # (1ᵀd = μᵀd = 0, la única que KKT no restringe) y la varianza tiene que
    # SUBIR. Comparar los puntos de la curva entre sí no probaría nada: con la
    # forma en C que produce el KKT, ningún par puede batirse.
    for a, b in zip(frontera, frontera[1:]):
        if b[1] < a[1]:
            raise _error("DISCREPANT", "σ² decrece en la rama eficiente")
    n_ = len(mus)
    Sg_f = [[_Q(x) for x in fila] for fila in Sigma]
    d = _dir_tangente(mus, n_) if n_ >= 3 else None
    if d is not None:
        e = Fraction(1, 1000)
        for m2, v2, w2 in frontera:
            w2 = list(w2)
            for signo in (1, -1):
                w_p = [w2[i] + signo * e * d[i] for i in range(n_)]
                var_p = sum(w_p[i] * Sg_f[i][j] * w_p[j]
                            for i in range(n_) for j in range(n_))
                if var_p < v2:
                    raise _error("DISCREPANT",
                                 f"en μ = {float(m2):g} hay una cartera factible "
                                 f"con menos riesgo que {float(v2):g}")
    trace.verificacion("sen.frontera_monotona",
                       f"{len(frontera)} puntos; σ² creciente y mínima "
                       f"frente a la dirección factible")
    return {"frontera": [(m, v) for m, v, _ in frontera],
            "pesos": [[float(x) for x in w] for _, _, w in frontera]}


def sharpe_var(mu_p, var_p, rf=0.0, alpha=0.05,
               trace: Trace | None = None) -> dict:
    """Sharpe (μ−rf)/σ y VaR gaussiano μ + σ·Φ⁻¹(α)."""
    trace = trace if trace is not None else Trace()
    mu_p, var_p, rf = _f(mu_p), _f(var_p), _f(rf)
    if not var_p > 0:
        raise _error("BAD_INPUT", "varianza > 0")
    sg = math.sqrt(var_p)
    q = _NORMAL().inv_cdf(_f(alpha))
    var = mu_p + sg * q
    # segundo camino: P(R ≤ VaR) = α en la normal N(μ, σ²)
    if abs(_NORMAL().cdf((var - mu_p) / sg) - _f(alpha)) > 1e-9:
        raise _error("DISCREPANT", "P(R ≤ VaR) ≠ α")
    trace.verificacion("sen.sharpe_var",
                       f"Sharpe = {(mu_p - rf) / sg:.6g}; VaR = {var:.6g}")
    return {"sharpe": (mu_p - rf) / sg, "VaR": var}
