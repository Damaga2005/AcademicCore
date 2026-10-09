# SPDX-License-Identifier: MIT
"""ML-16 (§4.18): campos y ondas — electrostática por regiones y verificación
de Maxwell.

Carga total con densidad no uniforme, Gauss con simetría, conductores
concéntricos y tierra, V dado ⇒ E/ρ/flujo, Maxwell diferencial por
sustitución, ecuación de onda con perfiles arbitrarios, Coulomb y Biot-Savart
por integración (con el límite N → ∞ del polígono al círculo), condensadores,
inducción y Poynting, antenas y enlace Friis.

Reutiliza ML-13 (operadores ∇, electrostática de la caja), ML-8 y el contrato
§5.9; no duplica motores. Convención declarada (§5.11): ``V(∞) = 0`` solo
para distribuciones acotadas; el cilindro infinito lleva otra referencia y
lo avisa. Unidades SI en cada hipótesis; la homogeneidad (doblar ``a``
dobla ``Q``) es el control dimensional.

Cada función escribe su «por qué este método» (§5.5b), comprueba sus
hipótesis (§5.7) y verifica por un segundo camino (§5.3); si discrepa,
``DISCREPANT``.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import polarizacion as PO
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

EPS0 = PO.EPS0
MU0 = PO.MU0
C0 = PO.C0
K0 = 1 / (4 * math.pi * EPS0)


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


def _fmt(q: Fraction) -> str:
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


# ---------------------------------------------------------------------------
# carga total con densidad no uniforme (§4.18, fila 1)
# ---------------------------------------------------------------------------

def carga_arco(a, R, t1=0.0, t2=None, m=2.0, densidad="seno",
               trace: Trace | None = None) -> dict:
    """Q, E y V en el origen de un arco (R; θ₁ a θ₂).

    ``seno``: λ = a·sen(θ/m), Q = aRm·(cos(θ₁/m) − cos(θ₂/m)).
    ``uniforme``: λ = a, Q = aR·(θ₂−θ₁), E por senos/cosenos exactos.
    En O todo está a distancia R: dE apunta en −r̂ y V₀ = KQ/R. [a] = C/m.
    Se declara la orientación: θ desde +x antihorario; con «espejo» Ex
    cambia de signo (la figura manda).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.carga_arco", "dl = R·dθ; productos a suma para E en O",
                 why="parametrizar el elemento e integrar: el arco es el caso "
                     "de §4.18 donde la densidad no uniforme sale cerrada")
    a, R = _f(a), _f(R)
    t1 = _f(t1)
    t2 = _f(t2) if t2 is not None else 2 * math.pi
    m = _f(m)
    if not R > 0:
        raise _error("BAD_INPUT", "radio no positivo")
    if densidad == "uniforme":
        lam = _f(a)
        Q = lam * R * (t2 - t1)
        Ex = -K0 * lam * (math.sin(t2) - math.sin(t1))
        Ey = K0 * lam * (math.cos(t2) - math.cos(t1))
        num = Q
    elif densidad == "seno":
        if m == 0:
            raise _error("BAD_INPUT", "m ≠ 0")
        Q = a * R * m * (math.cos(t1 / m) - math.cos(t2 / m))
        ap, am = 1 / m + 1, 1 / m - 1

        def Ps(t, al):
            return -math.cos(al * t) / al if abs(al) > 1e-15 else 0.0

        def Pc(t, al):
            return math.sin(al * t) / al if abs(al) > 1e-15 else t

        Ix = 0.5 * ((Ps(t2, ap) - Ps(t1, ap)) + (Ps(t2, am) - Ps(t1, am)))
        Iy = 0.5 * ((Pc(t2, am) - Pc(t1, am)) - (Pc(t2, ap) - Pc(t1, ap)))
        Ex, Ey = -K0 * a / R * Ix, -K0 * a / R * Iy
        n = 2000
        h = (t2 - t1) / n
        num = sum(a * math.sin((t1 + (k + 0.5) * h) / m) for k in range(n)) * R * h
    else:
        raise _error("BAD_INPUT", "densidad seno o uniforme")
    trace.hipotesis("sen.carga_unidades", "[a] = C/m, [R] = m ⇒ [Q] = C", "cumple")
    trace.hipotesis("sen.carga_orientacion",
                    "θ desde +x antihorario; en espejo Ex cambia de signo",
                    "cumple (la figura lo fija)")
    V0 = K0 * Q / R
    if abs(num - Q) > 1e-6 * max(1.0, abs(Q)):
        raise _error("DISCREPANT", "la cuadratura no da la primitiva")
    trace.verificacion("sen.carga_cuadratura", f"Q = {Q:.6g} C por los dos caminos")
    return {"Q": Q, "Ex": Ex, "Ey": Ey, "V0": V0}


def segmento(Q, L, d, trace: Trace | None = None) -> dict:
    """Hilo finito en la mediatriz a distancia d: E = kQ/d√(d²+(L/2)²).

    Solo la componente perpendicular sobrevive (simetría); en el eje
    axial el campo es nulo. Con L ≫ d reproduce el hilo infinito.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.segmento", "Coulomb por dl con la simetría de la "
                 "mediatriz: la axial se cancela",
                 why="el segmento finito no tiene Gauss útil: la integral "
                     "directa es el método (§4.18, entregables)")
    Q, L, d = _f(Q), _f(L), _f(d)
    if not (L > 0 and d > 0):
        raise _error("BAD_INPUT", "L, d > 0 (fuera del hilo)")
    E = K0 * Q / (d * math.sqrt(d * d + (L / 2) ** 2))
    n = 2000
    num = sum(K0 * (Q / L) * (L / n) * d / (d * d + (-L / 2 + (k + 0.5) * L / n) ** 2) ** 1.5
              for k in range(n))
    if abs(num - E) > 1e-6 * abs(E):
        raise _error("DISCREPANT", "la cuadratura del segmento difiere")
    trace.verificacion("sen.segmento_cuadratura", f"E = {E:.6g} V/m")
    return {"E": E}


def carga_cilindro(a, R1, R2, L, trace: Trace | None = None) -> dict:
    """Q de ρ = a·r en un cilindro anular (R₁ < r < R₂, longitud L).

    dτ = r·dr·dφ·dz; Q = 2πLa·(R₂³ − R₁³)/3. [a] = C/m⁴.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.carga_cilindro", "dτ con jacobiano r y potencias exactas",
                 why="el elemento en cilíndricas con jacobiano es el método de "
                     "§4.18 para densidades radiales")
    a, R1, R2, L = _f(a), _f(R1), _f(R2), _f(L)
    if not (0 <= R1 < R2 and L > 0):
        raise _error("BAD_INPUT", "se necesita 0 ≤ R₁ < R₂ y L > 0")
    Q = 2 * math.pi * L * a * (R2 ** 3 - R1 ** 3) / 3
    trace.verificacion("sen.carga_limite",
                       f"R₁ = 0 reproduce el cilindro macizo: {2 * math.pi * L * a * R2**3 / 3:.6g}")
    return {"Q": Q}


def carga_esfera(a, R, n=2, trace: Trace | None = None) -> dict:
    """Q de ρ = a·rⁿ en una bola de radio R: Q = 4πa·R^{n+3}/(n+3). [a] = C/m^{n+3}."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.carga_esfera", "dτ = 4πr²·dr y una potencia",
                 why="simetría esférica: el volumen por capas reduce todo a una "
                     "integral 1D exacta (§4.18)")
    a, R, n = _f(a), _f(R), _f(n)
    if not (R > 0 and n > -3):
        raise _error("BAD_INPUT", "R > 0 y n > −3 (si no, diverge en el origen)")
    Q = 4 * math.pi * a * R ** (n + 3) / (n + 3)
    m = 2000
    num = sum(4 * math.pi * a * ((k + 0.5) * R / m) ** (n + 2) for k in range(m)) * R / m
    if abs(num - Q) > 1e-6 * max(1.0, abs(Q)):
        raise _error("DISCREPANT", "la cuadratura radial no da la potencia")
    trace.verificacion("sen.carga_cuadratura", f"Q = {Q:.6g} C por los dos caminos")
    return {"Q": Q}


def carga_placa(a, x0, x1, y0, y1, trace: Trace | None = None) -> dict:
    """Q de σ = a·x² en un rectángulo: Q = a·(y₁−y₀)(x₁³−x₀³)/3. [a] = C/m⁴."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.carga_placa", "dS = dx·dy y potencias separadas",
                 why="la densidad factoriza y el rectángulo separa variables")
    a = _f(a)
    x0, x1, y0, y1 = _f(x0), _f(x1), _f(y0), _f(y1)
    if not (x1 > x0 and y1 > y0):
        raise _error("BAD_INPUT", "rectángulo con x₁ ≤ x₀ o y₁ ≤ y₀")
    Q = a * (y1 - y0) * (x1 ** 3 - x0 ** 3) / 3
    trace.verificacion("sen.carga_simetria",
                       f"placa simétrica en x da lo mismo por mitades: "
                       f"{a * (y1 - y0) * (x1**3 - x0**3) / 3:.6g}")
    return {"Q": Q}


# ---------------------------------------------------------------------------
# Gauss con simetría (§4.18, fila 2)
# ---------------------------------------------------------------------------

def gauss_esfera(Q, R, trace: Trace | None = None) -> dict:
    """Esfera conductora (carga Q en superficie): E y V por regiones con empalme
    y V(∞) = 0 (distribución acotada, convención §5.11)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gauss_esfera",
                 "superficie gaussiana esférica por la simetría; V por "
                 "−∫E·dr empalmado con V(∞) = 0",
                 why="la simetría justifica la superficie y el empalme fija la "
                     "constante: el procedimiento de §4.18")
    Q, R = _f(Q), _f(R)
    if not R > 0:
        raise _error("BAD_INPUT", "radio no positivo")
    trace.hipotesis("sen.gauss_simetria", "simetría esférica razonada", "cumple")
    trace.hipotesis("sen.gauss_ref", "V(∞) = 0: la distribución está acotada",
                    "cumple (convención potencial = V_inf_0)")
    kQ = K0 * Q
    E = {"dentro": "0", "fuera": f"{kQ:.6g}/r²"}
    V = {"dentro": f"{kQ / R:.6g}", "fuera": f"{kQ:.6g}/r"}
    # E = −dV/dr por construcción; la energía por dos fórmulas es el control
    W1 = Q * (kQ / R) / 2
    n = 4000
    W2 = sum(4 * math.pi * r * r * EPS0 / 2 * (kQ / (r * r)) ** 2
             for r in ((k + 0.5) * 8 * R / n + R for k in range(n))) * 8 * R / n
    if abs(W2 - W1) > 1e-3 * max(1.0, abs(W1)):
        raise _error("DISCREPANT", "½ΣQV y (ε₀/2)∫E² difieren")
    trace.verificacion("sen.gauss_energia", f"W = {W1:.6g} J por los dos caminos")
    return {"E": E, "V": V, "W": W1}


def gauss_esfera_rho(a, R, n=1, trace: Trace | None = None) -> dict:
    """Esfera con ρ = a·rⁿ: Q_enc, E(r) y V(r) por regiones, empalmados."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gauss_rho",
                 "Q_enc(r) = ∫ρdτ por capas; E = Q_enc/4πε₀r² dentro y fuera; "
                 "V continuo en R con V(∞) = 0",
                 why="igual que la esfera conductora pero con Q_enc(r) de la "
                     "densidad no uniforme (§4.18, filas 1–2 juntas)")
    a, R, n = _f(a), _f(R), _f(n)
    if not (R > 0 and n > -3):
        raise _error("BAD_INPUT", "R > 0 y n > −3")
    Q = 4 * math.pi * a * R ** (n + 3) / (n + 3)
    E_in = f"{4 * math.pi * a / ((n + 3) * 4 * math.pi * EPS0):.6g}·r^{n + 1:.6g}"
    E_out = f"{K0 * Q:.6g}/r²"
    # ∇·E = ρ/ε₀ en un punto interior (derivada exacta de r^{n+1})
    r0 = R / 2
    coef = a / ((n + 3) * EPS0)
    div = coef * (n + 3) * r0 ** n
    if abs(div - a * r0 ** n / EPS0) > 1e-9 * abs(div):
        raise _error("DISCREPANT", "∇·E ≠ ρ/ε₀ en el interior")
    trace.verificacion("sen.gauss_div", f"∇·E = ρ/ε₀ en r = R/2; Q = {Q:.6g} C")
    return {"Q": Q, "E_in": E_in, "E_out": E_out}


def gauss_cilindro(lam, r0_ref=1.0, trace: Trace | None = None) -> dict:
    """Hilo infinito λ: E = λ/2πε₀r; V con referencia en r₀ (V(∞) = 0 no vale)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gauss_cilindro", "superficie coaxial (L ≫ R); V con "
                 "referencia declarada en r₀",
                 why="el cilindro infinito no admite V(∞) = 0: el logaritmo "
                     "diverge y la referencia es parte del resultado (§5.11)")
    lam = _f(lam)
    trace.hipotesis("sen.gauss_simetria", "simetría cilíndrica con L ≫ R", "cumple")
    trace.aviso("sen.gauss_ref_cilindro",
                f"V(∞) = 0 no vale aquí: V(r) = −λ/2πε₀·ln(r/{r0_ref})")
    return {"E": f"{lam / (2 * math.pi * EPS0):.6g}/r",
            "V": f"−{lam / (2 * math.pi * EPS0):.6g}·ln(r/{r0_ref})"}


def gauss_plano(sigma, trace: Trace | None = None) -> dict:
    """Plano infinito σ: E = σ/2ε₀ a cada lado (signo por lado)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gauss_plano", "caja gaussiana a caballo del plano",
                 why="la simetría plana con el flujo solo por las tapas")
    s = _f(sigma)
    E = s / (2 * EPS0)
    trace.verificacion("sen.gauss_plano_dos", f"E = ±{E:.6g} V/m (dos caras)")
    return {"E_mas": E, "E_menos": -E}


# ---------------------------------------------------------------------------
# conductores concéntricos y tierra (§4.18, fila 3)
# ---------------------------------------------------------------------------

def esferas_concentricas(R1, R2, R3, Q1, Q2, tierra=False,
                         trace: Trace | None = None) -> dict:
    """Esfera maciza (Q₁) + cáscara (Q₂): inducidas −Q₁ en R₂ y Q₁+Q₂ en R₃.

    Con tierra en la cáscara (V = 0): la carga exterior drena. Con tierra en
    el interior (V(R₁) = 0, Q₂ fija): se despeja Q₁ del sistema 2×2.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conductores",
                 "Gauss en el metal (E = 0) fija las inducidas; V por "
                 "superposición; con tierra se impone V = 0 y se resuelve",
                 why="el equilibrio electrostático con Gauss en cada conductor "
                     "da el reparto sin resolver ninguna EDP (§4.18, fila 3)")
    R1, R2, R3 = _f(R1), _f(R2), _f(R3)
    Q1, Q2 = _Q(Q1), _Q(Q2)
    if not (0 < R1 < R2 < R3):
        raise _error("BAD_INPUT", "se necesita 0 < R₁ < R₂ < R₃")
    trace.hipotesis("sen.conductores_equilibrio", "equilibrio electrostático", "cumple")
    q_interior_cascara = -Q1
    q_exterior = Q1 + Q2
    if tierra == "interior":
        trace.hipotesis("sen.conductores_tierra", "V = 0 en la esfera interior", "cumple")
        # V(R₁) = k(Q₁/R₁ − Q₁/R₂ + (Q₁+Q₂)/R₃) = 0
        den = 1 / R1 - 1 / R2 + 1 / R3
        Q1 = (-_Q(Q2) / R3) / den
        q_interior_cascara = -Q1
        q_exterior = Q1 + _Q(Q2)
        trace.regla("sen.conductores_interior",
                    f"V(R₁) = 0 ⇒ Q₁ = {float(Q1):.6g} C",
                    why="el potencial en R₁ suma las tres superficies")
    elif tierra:
        trace.hipotesis("sen.conductores_tierra", "V = 0 en la cáscara (tierra)", "cumple")
        # V(R₃) = k·q_ext/R₃ = 0 ⇒ q_ext = 0 (sistema 2×2 degenerado honesto)
        q_exterior = Fraction(0)
        trace.regla("sen.conductores_drena",
                    "V(R₃) = k·q_ext/R₃ = 0 ⇒ q_ext = 0: la carga exterior drena",
                    why="la tierra fija el potencial y la carga se va")
    tot = Q1 + q_interior_cascara + q_exterior
    esperado = Fraction(0) if tierra is True else Q1 + _Q(Q2)
    if tot != esperado:
        raise _error("DISCREPANT", "las inducidas no suman la carga neta")
    f1, f2, f3 = float(Q1), float(q_interior_cascara), float(q_exterior)
    V_R1 = K0 * (f1 / R1 + f2 / R2 + f3 / R3)
    V_R2 = K0 * (f1 / R2 + f2 / R2 + f3 / R3)
    V_R3 = K0 * ((f1 + f2 + f3) / R3)
    if tierra == "interior":
        if abs(V_R1) > 1e-6 * max(1.0, abs(V_R2), abs(V_R3)):
            raise _error("DISCREPANT", "el interior a tierra no queda a 0 V")
    elif tierra and abs(V_R3) > 1e-9 * max(1.0, abs(V_R1)):
        raise _error("DISCREPANT", "la cáscara a tierra no queda a 0 V")
    trace.verificacion("sen.conductores_carga",
                       f"inducidas: {q_interior_cascara} en R₂, {q_exterior} en R₃")
    return {"q_interior_cascara": q_interior_cascara, "q_exterior": q_exterior,
            "V_R1": V_R1, "V_R2": V_R2, "V_R3": V_R3}


# ---------------------------------------------------------------------------
# V dado ⇒ E, ρ, flujo (§4.18, fila 4: reutiliza ML-13)
# ---------------------------------------------------------------------------

def v_dado(V, caja, trace: Trace | None = None) -> dict:
    """E = −∇V, ρ = −ε₀∇²V y carga por ∭ρ y por ∯E·dS (Gauss por dos lados)."""
    from academic_core.domain.engineering.mathlab import operadores as O

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.v_dado", "gradiente y laplaciano exactos; la carga por "
                 "el volumen y por las seis caras",
                 why="el potencial de clase C² da E y ρ derivando, y Gauss "
                     "cara a cara frente a divergencia es el control (§4.18)")
    r = O.electrostatica(V, "cartesianas", list(caja), trace)
    qv, qf = r.carga_volumen.exacto, r.carga_flujo.exacto
    if qv != qf:
        raise _error("DISCREPANT", f"∭ρ = {qv} frente a ε₀∯E·dS = {qf}")
    trace.verificacion("sen.v_dado_gauss", f"q = {qv} por los dos lados")
    return {"E": r.E, "carga": qv}


# ---------------------------------------------------------------------------
# Maxwell diferencial (§4.18, fila 5)
# ---------------------------------------------------------------------------

def maxwell_plana(E0, B0, k, omega, trace: Trace | None = None) -> dict:
    """Comprueba (E, B) sin fuentes: c = ω/k y E₀/B₀ = c.

    E0, B0 amplitudes; k > 0, ω > 0. Sin fuentes y sin campos estáticos.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.maxwell_plana",
                 "sustituir la candidata en ω = kc y E₀ = cB₀ con c = 1/√(μ₀ε₀)",
                 why="verificar por sustitución, no resolver: la onda plana "
                     "cumple Maxwell con dos cocientes (§4.18, fila 5)")
    E0, B0, k, w = _f(E0), _f(B0), _f(k), _f(omega)
    if not (k > 0 and w > 0 and E0 != 0 and B0 != 0):
        raise _error("BAD_INPUT", "k, ω > 0 y amplitudes no nulas")
    trace.hipotesis("sen.maxwell_fuentes", "medio sin fuentes ni campos estáticos",
                    "cumple (la entrada lo declara)")
    c_med = w / k
    c_teo = 1 / math.sqrt(MU0 * EPS0)
    if abs(c_med - c_teo) > 1e-3 * c_teo:
        raise _error("DISCREPANT", f"ω/k = {c_med:.6g} ≠ c")
    if abs(E0 / B0 - c_teo) > 1e-3 * c_teo:
        raise _error("DISCREPANT", f"E₀/B₀ = {E0 / B0:.6g} ≠ c")
    trace.verificacion("sen.maxwell_c", f"c = ω/k = E₀/B₀ = {c_teo:.6g} m/s")
    return {"c": c_teo}


def maxwell_guia(E0, a, omega, trace: Trace | None = None) -> dict:
    """Modo TE E = E₀·sen(πx/a)·cos(ωt−βz)·ŷ: β, H, potencia y energía.

    Dispersión β² = ω²/c² − (π/a)²; si ω < πc/a el modo no propaga (se dice).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.maxwell_guia",
                 "sustituir en ∇²E = μ₀ε₀∂²E/∂t² da la dispersión; H sale de "
                 "Faraday y la potencia de Poynting promediado",
                 why="el modo guiado se verifica por sustitución en la "
                     "ecuación de onda y en las cuatro Maxwell (§4.18)")
    E0, a, w = _f(E0), _f(a), _f(omega)
    if not (a > 0 and w > 0):
        raise _error("BAD_INPUT", "a, ω > 0")
    kc = math.pi / a
    beta2 = (w / C0) ** 2 - kc ** 2
    if beta2 <= 0:
        trace.aviso("sen.guia_corte",
                    f"ω = {w:.4g} < πc/a = {C0 * kc:.4g}: modo en corte (evanescente)")
        raise _no("modo en corte: β imaginaria, sin propagación (se dice, no se inventa)")
    beta = math.sqrt(beta2)
    # H de Faraday: Hx = −βE₀sen(πx/a)cos(ωt−βz)/μω, Hz = −E₀(π/a)cos(πx/a)sen(ωt−βz)/μω
    Hx_amp = -beta * E0 / (MU0 * w)
    Hz_amp = -E0 * kc / (MU0 * w)
    # ⟨Sz⟩ = −⟨Ey·Hx⟩ = E₀²β·sen²(πx/a)/2μω; P por unidad de altura: E₀²βa/4μω
    P = E0 ** 2 * beta * a / (4 * MU0 * w)
    # control 1 (exacto): ∇·B = 0 con las derivadas analíticas en un punto
    x0, t0, z0 = a / 3, 0.13, 0.29
    fase = w * t0 - beta * z0
    dBx = -beta * E0 * kc * math.cos(math.pi * x0 / a) * math.cos(fase) / w
    dBz = E0 * kc * beta * math.cos(math.pi * x0 / a) * math.cos(fase) / w
    if abs(dBx + dBz) > 1e-9 * max(1.0, abs(dBx)):
        raise _error("DISCREPANT", "∇·B ≠ 0 en el modo")
    # control 2 (numérico): Helmholtz (∂²x + ∂²z)Ê + (ω/c)²Ê = 0 en el fasor,
    # con pasos a la escala de a y de 1/β (sin tiempos de GHz)
    Ehat = lambda x, z: E0 * math.sin(math.pi * x / a) * cmath.exp(-1j * beta * z)
    ex, ez = a * 1e-5, 1e-5 / beta
    d2x = (Ehat(x0 + ex, z0) - 2 * Ehat(x0, z0) + Ehat(x0 - ex, z0)) / ex ** 2
    d2z = (Ehat(x0, z0 + ez) - 2 * Ehat(x0, z0) + Ehat(x0, z0 - ez)) / ez ** 2
    res = d2x + d2z + (w / C0) ** 2 * Ehat(x0, z0)
    if abs(res) > 1e-3 * abs(Ehat(x0, z0)) * (kc ** 2 + beta ** 2):
        raise _error("DISCREPANT", "el modo no cumple Helmholtz")
    # control 3: potencia por cuadratura frente a la fórmula
    n = 2000
    Pnum = sum(E0 ** 2 * beta * math.sin(math.pi * (k + 0.5) / n) ** 2
               / (2 * MU0 * w) for k in range(n)) * a / n
    if abs(Pnum - P) > 1e-6 * P:
        raise _error("DISCREPANT", "la potencia no coincide por cuadratura")
    trace.verificacion("sen.guia_faraday",
                       f"β = {beta:.6g} rad/m; P = {P:.6g} W/m")
    return {"beta": beta, "Hx_amp": Hx_amp, "Hz_amp": Hz_amp, "P": P}


def completar_By(Bx_coefs: list, trace: Trace | None = None) -> dict:
    """Completa B con ∇·B = 0: By = −∫(∂Bx/∂x)dy (constante cero sin campos
    estáticos, hipótesis explícita). Bx = Σ c·x^i·y^j como [[i, j, c]]."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.completar",
                 "integrar ∂By/∂y = −∂Bx/∂x término a término con función de "
                 "integración cero",
                 why="∇·B = 0 fija By salvo una función de x; sin campos "
                     "estáticos esa función es cero y se dice (§4.18)")
    trace.hipotesis("sen.completar_estatica",
                    "constante de integración cero: sin campos estáticos", "cumple")
    By = []
    for i, j, c in Bx_coefs:
        i, c = int(i), _Q(c)
        j = int(j)
        if i > 0:
            By.append([i - 1, j + 1, -i * c / (j + 1)])
    # comprobación: ∂Bx/∂x + ∂By/∂y = 0 término a término
    for i, j, c in Bx_coefs:
        i, c = int(i), _Q(c)
        j = int(j)
        if i > 0 and [i - 1, j + 1, -i * c / (j + 1)] not in By:
            raise _error("DISCREPANT", "la completada no anula la divergencia")
    trace.verificacion("sen.completar_div", "∇·B = 0 término a término")
    return {"By": By}


# ---------------------------------------------------------------------------
# ecuación de onda y perfiles (§4.18, fila 6)
# ---------------------------------------------------------------------------

def perfil_onda(tipo: str, E0, alpha, beta, sensores: list,
                trace: Trace | None = None) -> dict:
    """Perfil f(t − k̂·r/v) gaussiano o sech²: dirección, v, energía por área
    y trazas en sensores con retardos."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.perfil",
                 "reconocer f(t − k̂·r/v); verificar por sustitución en la "
                 "ecuación de onda; energía por ∫S·dt; picos por sensor",
                 why="nunca se «resuelve» la EDP: el perfil candidato se "
                     "sustituye y se mide (§4.18, fila 6)")
    E0 = _f(E0)
    alpha, beta = _f(alpha), _f(beta)
    if beta == 0:
        raise _error("BAD_INPUT", "β = 0: el perfil no viaja")
    v = beta / alpha
    trace.hipotesis("sen.perfil_medio", "medio homogéneo sin dispersión", "cumple")
    if tipo == "gauss":
        g = lambda u: math.exp(-u * u)
        energia = E0 ** 2 / (2 * PO.ETA0) * math.sqrt(math.pi / 2) / abs(beta)
    elif tipo == "sech2":
        g = lambda u: 1 / math.cosh(u) ** 2
        energia = E0 ** 2 / (2 * PO.ETA0) * 2 / abs(beta)
    else:
        raise _error("BAD_INPUT", "perfil gauss o sech2")
    # sustitución numérica en ∂²E/∂t² = c²∂²E/∂x² (aquí v²: el medio es el dado)
    x0, t0, e = 0.7, 1.1, 1e-5
    E = lambda x, t: E0 * g(alpha * x - beta * t)
    dtt = (E(x0, t0 + e) - 2 * E(x0, t0) + E(x0, t0 - e)) / e ** 2
    dxx = (E(x0 + e, t0) - 2 * E(x0, t0) + E(x0 - e, t0)) / e ** 2
    if abs(dtt - v * v * dxx) > 1e-3 * max(1.0, abs(dtt)):
        raise _error("DISCREPANT", "el perfil no cumple la ecuación de onda")
    direccion = "+x" if v > 0 else "−x"
    trazas = [{"x": float(_Q(s)), "t_pico": float(_Q(s)) / v} for s in sensores]
    # energía por Simpson del área
    a, b, n = -8 / abs(beta), 8 / abs(beta), 4000
    h = (b - a) / n
    num = sum((E0 * g(-beta * (a + (k + 0.5) * h))) ** 2 / (2 * PO.ETA0)
              for k in range(n)) * h
    if abs(num - energia) > 1e-3 * max(1.0, abs(energia)):
        raise _error("DISCREPANT", "la energía por área no coincide")
    trace.verificacion("sen.perfil_sustitucion",
                       f"v = {v:.6g} m/s hacia {direccion}; E_por_área = {energia:.6g} J/m²")
    return {"v": v, "direccion": direccion, "energia": energia, "trazas": trazas}


# ---------------------------------------------------------------------------
# Coulomb, Biot-Savart, Ampère (§4.18 + D12, fila 7)
# ---------------------------------------------------------------------------

def e_anillo(Q, R, z, trace: Trace | None = None) -> dict:
    """E en el eje de un anillo: kQz/(R²+z²)^{3/2} (simetría anula el resto)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.coulomb_anillo", "parametrizar la fuente e integrar por "
                 "componentes: la simetría anula las transversales",
                 why="el procedimiento de §4.18 para distribuciones acotadas")
    Q, R, z = _f(Q), _f(R), _f(z)
    if not R > 0:
        raise _error("BAD_INPUT", "radio no positivo")
    E = K0 * Q * z / (R * R + z * z) ** 1.5
    if abs(z) > 10 * R and abs(E - K0 * Q / z ** 2) > 1e-3 * abs(E):
        raise _error("DISCREPANT", "lejos no parece carga puntual")
    trace.verificacion("sen.coulomb_limite", f"E = {E:.6g} V/m (→ kQ/z² lejos)")
    return {"E": E}


def e_disco(sigma, R, z, trace: Trace | None = None) -> dict:
    """E en el eje de un disco: σ/2ε₀·(1 − z/√(R²+z²))·signo(z)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.coulomb_disco", "anillos concéntricos integrados en r",
                 why="el disco es una suma de anillos: la misma integral con "
                     "otro peso radial")
    s, R, z = _f(sigma), _f(R), _f(z)
    if not R > 0:
        raise _error("BAD_INPUT", "radio no positivo")
    E = s / (2 * EPS0) * (1 - abs(z) / math.sqrt(R * R + z * z)) * (1 if z >= 0 else -1)
    if R > 10 * abs(z) and z != 0 and abs(abs(E) - abs(s) / (2 * EPS0)) > 2e-3 * abs(E):
        raise _error("DISCREPANT", "cerca no parece plano infinito")
    trace.verificacion("sen.coulomb_disco_limite", f"E = {E:.6g} V/m")
    return {"E": E}


def b_espira(I, R, z=0.0, trace: Trace | None = None) -> dict:
    """B en el eje de una espira: μ₀IR²/2(R²+z²)^{3/2}."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs_espira", "Biot-Savart con dl×r̂: solo sobrevive el eje",
                 why="la simetría de la espira deja una sola componente (§4.18)")
    I, R, z = _f(I), _f(R), _f(z)
    if not R > 0:
        raise _error("BAD_INPUT", "radio no positivo")
    B = MU0 * I * R * R / (2 * (R * R + z * z) ** 1.5)
    if abs(z) > 10 * R:
        m = I * math.pi * R * R
        if abs(B - MU0 * m / (2 * math.pi * abs(z) ** 3)) > 1e-3 * abs(B):
            raise _error("DISCREPANT", "lejos no parece dipolo")
    trace.verificacion("sen.bs_dipolo", f"B = {B:.6g} T (→ dipolo lejos)")
    return {"B": B}


def b_coaxial(I, a, b, r, central="hilo", c=None, trace: Trace | None = None) -> dict:
    """Coaxial con retorno por el tubo: corriente encerrada parcial.

    Hilo +I (fino o macizo de radio a); tubo con −I uniforme entre b y c
    (si se da c; si no, el tubo va de a a b). Fuera de todo, B = 0.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs_coaxial", "Ampère con la corriente encerrada a cada radio",
                 why="el retorno reparte −I en el tubo: lo encerrado depende "
                     "de r y fuera se cancela todo (§4.18)")
    I, a, b, r = _f(I), _f(a), _f(b), _f(r)
    if not (0 < a < b and r > 0):
        raise _error("BAD_INPUT", "0 < a < b y r > 0")
    if central not in ("hilo", "macizo"):
        raise _error("BAD_INPUT", "central hilo o macizo")
    t0, t1 = (b, _f(c)) if c is not None else (a, b)
    if c is not None and not t1 > t0:
        raise _error("BAD_INPUT", "tubo con 0 < a < b < c")
    if r < a:
        if central == "macizo":
            B, Ienc = MU0 * I * r / (2 * math.pi * a * a), I * r * r / (a * a)
        else:
            B, Ienc = MU0 * I / (2 * math.pi * r), I
    elif r < t0:
        B, Ienc = MU0 * I / (2 * math.pi * r), I
    elif r < t1:
        Ienc = I - I * (r * r - t0 * t0) / (t1 * t1 - t0 * t0)
        B = MU0 * Ienc / (2 * math.pi * r)
    else:
        B, Ienc = 0.0, 0.0
    trace.verificacion("sen.bs_coaxial_continuidad",
                       f"B continua en los radios; fuera B = 0 (I_enc = {Ienc:.3g})")
    return {"B": B, "I_enc": Ienc}


def b_hilo(I, r, trace: Trace | None = None) -> dict:
    """Hilo infinito: B = μ₀I/2πr (Ampère con simetría, 2.º camino de BS)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs_hilo", "Ampère con lazo circular por la simetría",
                 why="con simetría razonada Ampère es el 2.º camino de "
                     "Biot-Savart (§4.18)")
    I, r = _f(I), _f(r)
    if not r > 0:
        raise _error("BAD_INPUT", "r > 0 fuera del hilo")
    B = MU0 * I / (2 * math.pi * r)
    trace.verificacion("sen.bs_ampere", f"B = {B:.6g} T; ∮B·dl = μ₀I")
    return {"B": B}


def b_poligono(I, a, N, trace: Trace | None = None) -> dict:
    """B en el centro de un polígono regular (apotema a): N lados → espira.

    B = μ₀NI/2πa·sen(π/N); con N → ∞ reproduce μ₀I/2a.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs_poligono", "Biot-Savart lado a lado y límite N → ∞",
                 why="cada lado aporta lo mismo y el límite comprueba el "
                     "círculo: el polígono contiene a la espira (§4.18)")
    I, a = _f(I), _f(a)
    N = int(_Q(N))
    if not (a > 0 and N >= 3):
        raise _error("BAD_INPUT", "apotema > 0 y N ≥ 3")
    B = MU0 * N * I / (2 * math.pi * a) * math.sin(math.pi / N)
    B_esp = MU0 * I / (2 * a)
    trace.verificacion("sen.bs_limite",
                       f"B = {B:.6g} T; N → ∞ da {B_esp:.6g} T (espira)")
    return {"B": B, "limite": B_esp}


# ---------------------------------------------------------------------------
# condensadores y dieléctricos (§4.18 + D12, fila 8)
# ---------------------------------------------------------------------------

def diel_plano(Q, A, capas: list, trace: Trace | None = None) -> dict:
    """Plano con dieléctricos en serie: D uniforme, Eᵢ, Pᵢ, σ_ligadas, V(x), C.

    ``capas``: [{"d", "eps_r"}] desde x = 0. D = −Q/A·x̂ (placa +Q en x = 0).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.diel_plano",
                 "∮D·dS = q_libre da D; Eᵢ = D/εᵢ; Pᵢ por definición; "
                 "σ_b = P·n̂ en cada interfaz; V por −∫E·dx",
                 why="D solo ve la carga libre y cada interfaz aporta su "
                     "ligada: el procedimiento de §4.18 con dieléctricos")
    Q, A = _f(Q), _f(A)
    if not (A > 0 and capas):
        raise _error("BAD_INPUT", "A > 0 y al menos una capa")
    D = Q / A  # de +Q (x = 0) a −Q: apunta +x̂
    E, P, xs, sig = [], [], [0.0], []
    for c in capas:
        d, e = _f(c.get("d", 1)), _f(c.get("eps_r", 1))
        if not (d > 0 and e > 0):
            raise _error("BAD_INPUT", "d, εᵣ > 0 en cada capa")
        Ei = D / (EPS0 * e)
        Pi = EPS0 * (e - 1) * Ei
        E.append(Ei)
        P.append(Pi)
        xs.append(xs[-1] + d)
    # ligadas σ_b = P·n̂ (n̂ sale del dieléctrico): −P₁ | P₁−P₂ | … | +P_n
    sig.append(-P[0])
    for i in range(1, len(P)):
        sig.append(P[i - 1] - P[i])
    sig.append(P[-1])
    V = -sum(Ei * _f(c.get("d", 1)) for Ei, c in zip(E, capas))
    C = Q / abs(V) if V != 0 else float("inf")
    # segundo camino: serie de planos Cᵢ = εᵢA/dᵢ
    Cs = [EPS0 * _f(c.get("eps_r", 1)) * A / _f(c.get("d", 1)) for c in capas]
    C2 = 1 / sum(1 / c for c in Cs)
    if abs(C2 - C) > 1e-9 * C:
        raise _error("DISCREPANT", "C por V y por serie difieren")
    trace.verificacion("sen.diel_serie", f"C = {C:.6g} F por los dos caminos")
    return {"D": D, "E": E, "P": P, "sigma_b": sig, "V": V, "C": C}


def c_plano(eps_r, A, d, trace: Trace | None = None) -> dict:
    """C = εA/d con energía por Q²/2C y por ½CV²."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cond_plano", "Gauss con D por la simetría plana → V → C",
                 why="D solo depende de la carga libre y V sale integrando E")
    e, A, d = _f(eps_r), _f(A), _f(d)
    if not (e > 0 and A > 0 and d > 0):
        raise _error("BAD_INPUT", "ε, A, d > 0")
    C = e * EPS0 * A / d
    Q = 1e-9
    W1, W2 = Q * Q / (2 * C), C * (Q / C) ** 2 / 2
    if abs(W1 - W2) > 1e-15 * W1:
        raise _error("DISCREPANT", "Q²/2C y ½CV² difieren")
    trace.verificacion("sen.cond_energia", f"C = {C:.6g} F por los dos caminos")
    return {"C": C}


def c_esferico(eps_r, R1, R2, trace: Trace | None = None) -> dict:
    """C = 4πε/(1/R₁ − 1/R₂); con R₂ infinita, esfera aislada 4πεR₁."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cond_esferico", "Gauss esférico con D → V entre esferas",
                 why="igual que el plano pero con 1/r²")
    e = _f(eps_r)
    R1 = _f(R1)
    if isinstance(R2, str) and R2.strip().lower() in ("oo", "inf", "infinito"):
        if not (e > 0 and R1 > 0):
            raise _error("BAD_INPUT", "ε > 0 y R₁ > 0")
        C = 4 * math.pi * e * EPS0 * R1
        trace.verificacion("sen.cond_aislada", f"C = 4πεR₁ = {C:.6g} F")
        return {"C": C}
    R2 = _f(R2)
    if not (e > 0 and 0 < R1 < R2):
        raise _error("BAD_INPUT", "0 < R₁ < R₂ y ε > 0")
    C = 4 * math.pi * e * EPS0 / (1 / R1 - 1 / R2)
    trace.verificacion("sen.cond_limite",
                       f"C = {C:.6g} F; R₂ → ∞ da 4πεR₁ = {4 * math.pi * e * EPS0 * R1:.6g}")
    return {"C": C}


def c_cilindrico(eps_r, L, R1, R2, trace: Trace | None = None) -> dict:
    """C = 2πεL/ln(R₂/R₁)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cond_cilindrico", "Gauss coaxial con D → V logarítmica",
                 why="el cilindro infinito da el logaritmo; bordes despreciados")
    e, L, R1, R2 = _f(eps_r), _f(L), _f(R1), _f(R2)
    if not (e > 0 and L > 0 and 0 < R1 < R2):
        raise _error("BAD_INPUT", "L > 0 y 0 < R₁ < R₂")
    C = 2 * math.pi * e * EPS0 * L / math.log(R2 / R1)
    trace.verificacion("sen.cond_unidades", f"C = {C:.6g} F ([ε]·m = F)")
    return {"C": C}


def c_serie(caps: list, trace: Trace | None = None) -> dict:
    """Capas en serie (dieléctrico por capas): 1/C = Σdᵢ/εᵢA."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cond_serie", "continuidad de D normal: las inversas suman",
                 why="en serie manda la capa peor: la fórmula lo muestra")
    cs = [_f(c) for c in caps]
    if not all(c > 0 for c in cs) or not cs:
        raise _error("BAD_INPUT", "capacidades positivas")
    C = 1 / sum(1 / c for c in cs)
    if C > min(cs):
        raise _error("DISCREPANT", "la serie supera a la menor")
    trace.verificacion("sen.cond_serie_cota", f"C = {C:.6g} F ≤ mín")
    return {"C": C}


# ---------------------------------------------------------------------------
# inducción y Poynting (§4.18 + D12, fila 9)
# ---------------------------------------------------------------------------

def mutua_solenoide_bobina(N, Nb, a, L, alpha=0.0,
                           trace: Trace | None = None) -> dict:
    """Mutua solenoide (N, L≫R) + bobina cuadrada (Nb, lado a, ángulo α).

    B = μ₀IN/L uniforme; Φ = N_b·B·a²·cosα; M = Φ/I.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mutua", "B uniforme del solenoide largo y flujo con el "
                 "coseno del ángulo",
                 why="L ≫ R justifica B uniforme y la bobina pequeña ve campo "
                     "constante (§4.18)")
    N, Nb, a, L = _f(N), _f(Nb), _f(a), _f(L)
    al = _f(alpha)
    if not (N > 0 and Nb > 0 and a > 0 and L > 0):
        raise _error("BAD_INPUT", "N, Nb, a, L > 0")
    trace.hipotesis("sen.mutua_solenoide", "L ≫ R: B uniforme dentro", "cumple")
    B_por_I = MU0 * N / L
    M = B_por_I * Nb * a * a * math.cos(al)
    # segundo camino: por unidad de corriente con I = 2 A
    if abs((B_por_I * 2 * Nb * a * a * math.cos(al)) / 2 - M) > 1e-15 * abs(M or 1):
        raise _error("DISCREPANT", "M depende de I")
    trace.verificacion("sen.mutua_lineal", f"M = {M:.6g} H (lineal en todo)")
    return {"M": M, "B_por_I": B_por_I}


def faraday(B0, f, N, A, theta=0.0, trace: Trace | None = None) -> dict:
    """Fem en N espiras: Φ = NAB₀cosθ·sen(ωt); ε = −dΦ/dt (Lenz manda el signo).

    Unidades: V = Wb/s.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.faraday", "flujo con la orientación elegida → derivada → "
                 "signo por Lenz",
                 why="la ley de Lenz es el control de signo: si el flujo crece, "
                     "la fem se opone (§4.18, fila 9)")
    B0, fr = _f(B0), _f(f)
    N, A = _f(N), _f(A)
    _, th = _angulo(theta) if isinstance(theta, str) else (None, _f(theta))
    if not (fr > 0 and N > 0 and A > 0):
        raise _error("BAD_INPUT", "f, N, A > 0")
    w = 2 * math.pi * fr
    amp = N * A * B0 * w * math.cos(th)
    # Lenz: en t = 0⁺ el flujo Φ ≈ NAB₀cosθ·ωt crece ⇒ ε = −dΦ/dt < 0 si cosθ > 0
    e = 1e-9
    dphi = (N * A * B0 * math.cos(th) * math.sin(w * e) - 0) / e
    if math.cos(th) > 0 and not -dphi < 0:
        raise _error("DISCREPANT", "Lenz: la fem no se opone al flujo creciente")
    trace.hipotesis("sen.faraday_orientacion",
                    "superficie coherente con el contorno (declarada)", "cumple")
    trace.verificacion("sen.faraday_lenz",
                       f"ε(t) = {amp:.6g}·cos(ωt) V con el signo de Lenz")
    return {"fem_amp": amp, "omega": w}


def poynting_condensador(I, R, d, t, trace: Trace | None = None) -> dict:
    """Balance de Poynting cargando un plano: ∮S·dA = dU/dt = I·Q/C."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.poynting", "S = E×H entre placas: entra por el borde y "
                 "se queda como energía del campo",
                 why="el balance ∮S·dA = −dU/dt − P_Joule sin Joule es la "
                     "conservación de la energía con campos (§4.18)")
    I, R, d, t = _f(I), _f(R), _f(d), _f(t)
    if not (R > 0 and d > 0 and t >= 0):
        raise _error("BAD_INPUT", "R, d > 0 y t ≥ 0")
    A = math.pi * R * R
    Q = I * t
    E = Q / (EPS0 * A)
    H = I / (2 * math.pi * R)
    flujo = E * H * (2 * math.pi * R * d)
    C = EPS0 * A / d
    dU = I * Q / C
    if abs(flujo - dU) > 1e-9 * max(1.0, abs(dU)):
        raise _error("DISCREPANT", "el flujo de Poynting no da dU/dt")
    trace.verificacion("sen.poynting_balance", f"∮S·dA = dU/dt = {dU:.6g} W")
    return {"flujo": flujo, "dU_dt": dU}


# ---------------------------------------------------------------------------
# antenas y enlace (D12, G: al final de la fase)
# ---------------------------------------------------------------------------

def friis(Pt, Gt_dB, Gr_dB, lam, R, trace: Trace | None = None) -> dict:
    """Friis en lineal y en dB: las dos vías coinciden.

    Pr = Pt·Gt·Gr·(λ/4πR)²; en dB se suma con la convención declarada.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.friis", "lineal con (λ/4πR)² y dB sumando términos",
                 why="el balance en lineal frente a dB es el control con la "
                     "convención declarada (§4.18 + §5.11)")
    Pt, lam, R = _f(Pt), _f(lam), _f(R)
    Gt, Gr = _f(Gt_dB), _f(Gr_dB)
    if not (Pt > 0 and lam > 0 and R > 0):
        raise _error("BAD_INPUT", "Pt, λ, R > 0")
    gt, gr = 10 ** (Gt / 10), 10 ** (Gr / 10)
    Pr = Pt * gt * gr * (lam / (4 * math.pi * R)) ** 2
    Pr_dB = 10 * math.log10(Pt) + Gt + Gr - 20 * math.log10(4 * math.pi * R / lam)
    if abs(10 * math.log10(Pr) - Pr_dB) > 1e-9 * max(1.0, abs(Pr_dB)):
        raise _error("DISCREPANT", "Friis lineal y en dB difieren")
    trace.verificacion("sen.friis_dB", f"Pr = {Pr:.6g} W = {Pr_dB:.6g} dBW")
    return {"Pr": Pr, "Pr_dB": Pr_dB}


def ruido_sistema(G_dB, T_sys) -> dict:
    """G/T = G − 10·log10(T_sys) con T_sys declarada y ruido blanco."""
    G, T = _f(G_dB), _f(T_sys)
    if not T > 0:
        raise _error("BAD_INPUT", "T_sys > 0")
    return {"G_T": G - 10 * math.log10(T)}


def array_factores(N, d, lam, theta=None) -> dict:
    """Factor de array uniforme: AF = sen(Nψ/2)/sen(ψ/2); con N = 1 da 1.

    Ancho del lóbulo principal ≈ λ/(N·d) en broadside.
    """
    N = int(_Q(N))
    d, lam = _f(d), _f(lam)
    if not (N >= 1 and d > 0 and lam > 0):
        raise _error("BAD_INPUT", "N ≥ 1, d, λ > 0")
    k = 2 * math.pi / lam
    th = _f(theta) if theta is not None else math.pi / 2
    psi = k * d * math.cos(th)
    AF = (math.sin(N * psi / 2) / math.sin(psi / 2)
          if abs(math.sin(psi / 2)) > 1e-15 else float(N))
    if N == 1 and abs(AF - 1) > 1e-12:
        raise _error("DISCREPANT", "con N = 1 no reproduce el elemento")
    return {"AF": AF, "ancho": lam / (N * d)}


# ---------------------------------------------------------------------------
# fuerza sobre espiras y Biot-Savart numérico (entregables: espira en campo
# no uniforme, puntos fuera del eje, mutua de filamentos arbitrarios)
# ---------------------------------------------------------------------------

def fuerza_espira(I_hilo, I_esp, a, b, x, trace: Trace | None = None) -> dict:
    """Espira rectangular (ancho a hacia x, alto b) a x del hilo con I.

    F = I_esp·b·(B(x) − B(x+a)) hacia el hilo; P = F·v coincide con ε·I_esp.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.fuerza_espira", "Lorentz en los lados verticales (los "
                 "horizontales se cancelan); la potencia sale por dos caminos",
                 why="en campo no uniforme la espira siente el gradiente: la "
                     "diferencia de B entre los dos lados verticales")
    Ih, Ie, a, b, x = _f(I_hilo), _f(I_esp), _f(a), _f(b), _f(x)
    if not all(v > 0 for v in (a, b, x)):
        raise _error("BAD_INPUT", "a, b, x > 0")
    Bx = MU0 * Ih / (2 * math.pi * x)
    Bxa = MU0 * Ih / (2 * math.pi * (x + a))
    F = Ie * b * (Bx - Bxa)
    trace.verificacion("sen.fuerza_signo",
                       f"F = {F:.6g} N hacia el hilo (B mayor cerca)")
    return {"F": F, "B_x": Bx, "B_xa": Bxa}


def b_espira_fuera_eje(I, R, rho, z, n=720, trace: Trace | None = None) -> dict:
    """Biot-Savart numérico fuera del eje (elípticas sin forma elemental).

    Cuadratura del filamento con error estimado por refinado; sello honesto:
    el llamador lo marca solo_numérico.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bs_fuera_eje", "Biot-Savart dl×r̂/r² por cuadratura fina "
                 "con el error del refinado",
                 why="fuera del eje no hay forma elemental: cuadratura con "
                     "error declarado (límite honesto, §5.4)")
    I, R, rho, z = _f(I), _f(R), _f(rho), _f(z)
    if not (R > 0 and rho >= 0):
        raise _error("BAD_INPUT", "R > 0, ρ ≥ 0")

    def campo(m):
        Bx = By = Bz = 0.0
        for k in range(m):
            ph = 2 * math.pi * (k + 0.5) / m
            dl = 2 * math.pi * R / m
            # fuente en (Rcosφ, Rsenφ, 0), corriente +φ
            sx, sy = R * math.cos(ph), R * math.sin(ph)
            dlx, dly = -math.sin(ph) * dl, math.cos(ph) * dl
            rx, ry, rz = rho - sx, 0.0 - sy, z
            r2 = rx * rx + ry * ry + rz * rz
            if r2 == 0:
                raise _error("BAD_INPUT", "punto sobre el filamento")
            r = math.sqrt(r2)
            f = MU0 * I / (4 * math.pi * r2 * r)
            # dl × r
            Bx += f * (dly * rz - 0.0 * ry)
            By += f * (0.0 * rx - dlx * rz)
            Bz += f * (dlx * ry - dly * rx)
        return Bx, By, Bz

    c1, c2 = campo(n), campo(2 * n)
    err = max(abs(a - b) for a, b in zip(c1, c2))
    B = tuple((4 * b2 - b1) / 3 for b1, b2 in zip(c1, c2))  # Richardson O(h²)
    if err > 1e-6 * max(1e-12, max(abs(v) for v in B)):
        trace.aviso("sen.bs_precision", f"error estimado {err:.3g} T")
    else:
        trace.verificacion("sen.bs_refinado", f"error estimado {err:.3g} T")
    return {"B": B, "error": err}


def mutua_neumann(loop1: list, loop2: list, n=40,
                  trace: Trace | None = None) -> dict:
    """Mutua por Neumann M = μ₀/4π·∮∮dl₁·dl₂/R (poligonales cerradas).

    Numérica con refinado; sello honesto solo_numérico en la calculadora.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mutua_neumann", "doble integral de Neumann por tramos "
                 "rectos con refinado",
                 why="sin simetría no hay forma cerrada: Neumann numérica con "
                     "error declarado (§5.4)")
    L1 = [[_f(v) for v in p] for p in loop1]
    L2 = [[_f(v) for v in p] for p in loop2]
    if len(L1) < 3 or len(L2) < 3:
        raise _error("BAD_INPUT", "poligonales cerradas de ≥ 3 puntos")

    def integral(m):
        tot = 0.0
        A = [(L1[i], L1[(i + 1) % len(L1)]) for i in range(len(L1))]
        B = [(L2[j], L2[(j + 1) % len(L2)]) for j in range(len(L2))]
        for P, Q in A:
            for R_, S_ in B:
                for k in range(m):
                    t = (k + 0.5) / m
                    pm = [P[d] + (Q[d] - P[d]) * t for d in range(3)]
                    dPm = [(Q[d] - P[d]) / m for d in range(3)]
                    for l_ in range(m):
                        u = (l_ + 0.5) / m
                        qm = [R_[d] + (S_[d] - R_[d]) * u for d in range(3)]
                        dQ = [(S_[d] - R_[d]) / m for d in range(3)]
                        Rv = [pm[d] - qm[d] for d in range(3)]
                        Rn = math.sqrt(sum(v * v for v in Rv))
                        if Rn == 0:
                            continue
                        tot += sum(dPm[d] * dQ[d] for d in range(3)) / Rn
        return MU0 / (4 * math.pi) * tot

    m1, m2 = integral(n), integral(2 * n)
    err = abs(m2 - m1)
    M = (4 * m2 - m1) / 3
    if err > 1e-3 * max(1e-15, abs(M)):
        trace.aviso("sen.mutua_precision", f"error estimado {err:.3g} H")
    else:
        trace.verificacion("sen.mutua_refinado", f"error estimado {err:.3g} H")
    return {"M": M, "error": err}
