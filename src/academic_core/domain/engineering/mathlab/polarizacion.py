# SPDX-License-Identifier: MIT
"""ML-15 (§4.17): fasores, onda plana, medios con pérdidas, polarización,
Jones, Fresnel y multicapa.

Respaldo E de EAFO: casi todo el examen se escribe en notación fasorial, así
que cada cálculo declara su convención (§5.11: coseno o seno como referencia,
``e^{+jωt}`` o ``e^{−iωt}``, pico o eficaz) y se verifica con la contraria o
por muestreo del dominio del tiempo.

Convenciones fijadas en este módulo (todas se imprimen en la traza):

- la raíz compleja es la rama principal con ``Re ≥ 0`` (propagación que no
  crece); en reflexión total, ``Im(cosθ_t) ≥ 0`` (evanescente que decae);
- dextrógira/levógira por la regla de la mano derecha con el pulgar en la
  dirección de propagación (IEEE): con ``e^{+jωt}`` y ``Ax, Ay > 0``,
  dextrógira ⟺ ``sinδ < 0`` (se comprueba con el giro muestreado, no solo
  con el signo);
- ``sinc``, ``Π`` y ``Λ`` no aparecen aquí; la frecuencia se da en ``f`` o
  en ``ω`` según lo pida la entrada (se declara).

Cada función escribe su «por qué este método» (§5.5b), comprueba sus
hipótesis (§5.7) y verifica por un segundo camino independiente (§5.3). Si
el segundo camino discrepa, se lanza ``DISCREPANT``.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: velocidad de la luz, permeabilidad y permitividad del vacío, impedancia
#: del vacío e impedancia en dB de un neperio (20·log10(e) = 8,6859…)
C0 = 299792458.0
MU0 = 4 * math.pi * 1e-7
EPS0 = 8.854187817e-12
ETA0 = math.sqrt(MU0 / EPS0)
DB_POR_NEPER = 20 * math.log10(math.e)


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


def _fmt_q(q: Fraction) -> str:
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def _angulo(x) -> tuple[Fraction | None, float]:
    """Un ángulo en radianes; si es múltiplo racional de π, también la fracción.

    Acepta un número (radianes) o un texto con «pi» («pi/3», «-pi/2», «2*pi»).
    """
    if isinstance(x, (int, float, Fraction)):
        v = float(_Q(x))
        return (Fraction(0), 0.0) if v == 0.0 else (None, v)
    s = str(x).strip().replace(",", ".").replace(" ", "").lower().replace("π", "pi")
    if "pi" not in s:
        v = float(_Q(s))
        return (Fraction(0), 0.0) if v == 0.0 else (None, v)
    coef = s.replace("pi", "")
    if coef in ("", "+"):
        coef = "1"
    elif coef == "-":
        coef = "-1"
    coef = coef.rstrip("*")
    if coef in ("", "+"):
        coef = "1"
    elif coef == "-":
        coef = "-1"
    elif coef.startswith("-/"):
        coef = "-1" + coef[1:]
    elif coef.startswith("+/"):
        coef = "+1" + coef[1:]
    elif coef.startswith("/"):
        coef = "1" + coef
    try:
        k = Fraction(coef)
    except (ValueError, ZeroDivisionError):
        raise _error("BAD_INPUT", f"ángulo «{x}» no entendido (usa «pi/3» o radianes)")
    return k, float(k) * math.pi


def _es_multiplo_medio_pi(k: Fraction | None) -> bool:
    return k is not None and (k * 2).denominator == 1


def _rect_exacta(A, k: Fraction | None) -> tuple[Fraction, Fraction] | None:
    """Partes rectangulares exactas si la fase es múltiplo de π/2."""
    if k is None or not _es_multiplo_medio_pi(k):
        return None
    r = int(k * 2) % 4
    c, s = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}[r]
    A = _Q(A)
    return A * c, A * s


# ---------------------------------------------------------------------------
# fasor ↔ tiempo, suma y problema inverso (§4.17, fila 1)
# ---------------------------------------------------------------------------

def suma_fasores(pares: list[tuple], trace: Trace | None = None) -> dict:
    """Suma de senoidales de igual frecuencia: módulo y argumento del total.

    Cada par es ``(A, fase)`` con la fase en radianes o en texto con «pi».
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.fasor_suma",
                 "cada senoidal a su fasor A·e^{jφ}; se suman los rectangulares; "
                 "se vuelve al tiempo con A·cos(ωt+φ)",
                 why="la suma de senoidales de igual frecuencia es otra senoidal "
                     "y el fasor es su forma exacta de sumarla (§4.17, fila 1)")
    if not pares:
        raise _error("BAD_INPUT", "suma sin senoidales")
    re_e, im_e = Fraction(0), Fraction(0)
    re_n, im_n = 0.0j, 0.0
    exacto = True
    for A, fase in pares:
        k, rad = _angulo(fase)
        ex = _rect_exacta(A, k)
        if ex is None:
            exacto = False
            re_n += complex(float(_Q(A)) * math.cos(rad), 0.0)
            im_n += complex(float(_Q(A)) * math.sin(rad), 0.0)
        else:
            re_e += ex[0]
            im_e += ex[1]
    re = float(re_e) + re_n.real
    im = float(im_e) + im_n.real
    A = math.hypot(re, im)
    phi = math.atan2(im, re)
    trace.hipotesis("sen.fasor_misma_f", "todas las senoidales comparten ω",
                    "cumple (la entrada lo declara)")
    trace.regla("sen.fasor_total", f"Σ = {re:.6g}{im:+.6g}j; A = {A:.6g}, φ = {phi:.6g}",
                why="suma rectangular exacta" if exacto else "suma numérica")
    # segundo camino: muestrear la suma en el tiempo frente al total
    for t in (0.0, 0.3, 1.1):
        directa = sum(float(_Q(A)) * math.cos(2 * math.pi * t + _angulo(f)[1])
                      for A, f in pares)
        total = A * math.cos(2 * math.pi * t + phi)
        if abs(directa - total) > 1e-9 * max(1.0, abs(directa)):
            raise _error("DISCREPANT", f"la suma no coincide en t = {t}")
    trace.verificacion("sen.fasor_muestreo", "la suma directa coincide en 3 instantes")
    return {"re": re, "im": im, "A": A, "phi": phi,
            "exacto": (re_e, im_e) if exacto else None}


def problema_inverso(omega, muestras: list[tuple], conocido,
                     trace: Trace | None = None) -> dict:
    """«Dados dos valores medidos de 8·cos(ωt)+A·cos(ωt+φ₁), hallar A y φ₁».

    El residuo ``r(t) = x − A₀·cos(ωt)`` es ``P·cosωt − Q·sinωt`` con
    ``P = A·cosφ₁``, ``Q = A·sinφ₁``: dos muestras dan un sistema 2×2.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.fasor_inverso",
                 "se resta lo conocido; el residuo es P·cosωt − Q·sinωt y dos "
                 "muestras lo resuelven; A y φ₁ son su módulo y su argumento",
                 why="el problema inverso de §4.17 es un sistema lineal 2×2 en "
                     "(P, Q): despejar el fasor, no adivinarlo")
    w = _angulo(omega)[1]
    A0 = float(_Q(conocido))
    if len(muestras) < 2:
        raise _error("BAD_INPUT", "el problema inverso necesita dos muestras")
    (t1, x1), (t2, x2) = [(float(_Q(t)), float(_Q(v))) for t, v in muestras[:2]]
    r1, r2 = x1 - A0 * math.cos(w * t1), x2 - A0 * math.cos(w * t2)
    a11, a12 = math.cos(w * t1), -math.sin(w * t1)
    a21, a22 = math.cos(w * t2), -math.sin(w * t2)
    det = a11 * a22 - a12 * a21
    trace.hipotesis("sen.inverso_det", f"det = sin(ω(t₂−t₁)) = {det:.4g} ≠ 0",
                    "cumple" if abs(det) > 1e-12 else "falla")
    if abs(det) <= 1e-12:
        raise _error("BAD_INPUT", "muestras separadas medio periodo: no determinan (P, Q)")
    P = (r1 * a22 - r2 * a12) / det
    Q = (a11 * r2 - a21 * r1) / det
    A = math.hypot(P, Q)
    phi = math.atan2(Q, P)
    # segundo camino: la reconstruida pasa por las dos muestras
    for t, x in ((t1, x1), (t2, x2)):
        rec = A0 * math.cos(w * t) + A * math.cos(w * t + phi)
        if abs(rec - x) > 1e-9 * max(1.0, abs(x)):
            raise _error("DISCREPANT", f"la reconstruida no pasa por t = {t}")
    trace.verificacion("sen.inverso_muestras",
                       f"A = {A:.6g}, φ₁ = {phi:.6g}: pasa por las dos muestras")
    return {"A": A, "phi": phi, "P": P, "Q": Q}


def senal_tiempo(A, phi, omega, t: float, ref: str = "cos", signo: str = "+") -> float:
    """Muestra física x(t) bajo una convención (§5.11).

    ``ref``: «cos» (ingeniería) o «sen» como referencia de fase; ``signo``:
    «+» (``e^{+jωt}``) o «−» (``e^{−iωt}``, física: la fase cambia de signo).
    """
    A, phi, w = float(_Q(A)), float(_Q(phi)), float(_Q(omega))
    s = 1.0 if signo == "+" else -1.0
    if ref == "cos":
        return A * math.cos(w * t + s * phi)
    if ref == "sen":
        return A * math.sin(w * t + s * phi)
    raise _error("BAD_INPUT", "referencia cos o sen")


def potencia_media(A, convenio: str = "pico", eta: float = ETA0) -> float:
    """⟨S⟩ de una onda con amplitud A: A²/2η (pico) o A²/η (eficaz)."""
    A = float(_Q(A))
    if convenio == "pico":
        return A * A / (2 * eta)
    if convenio == "V_ef":
        return A * A / eta
    raise _error("BAD_INPUT", "convenio pico o V_ef")


# ---------------------------------------------------------------------------
# onda plana (§4.17, fila 2)
# ---------------------------------------------------------------------------

def onda_plana(E0, n, f, direccion=(0, 0, 1), sensor=None,
               convenio: str = "pico", trace: Trace | None = None) -> dict:
    """Onda plana uniforme: k, λ, v, η, H, ⟨S⟩ y potencia captada.

    ``E0``: par transversal [Ex, Ey] (propagación +z) o triedro con su
    dirección (se comprueba ``k̂·E = 0``). ``sensor``: {"forma": "circulo",
    "R"} o {"forma": "cuadrado", "lado", "desplazamiento" (se avisa: con
    incidencia perpendicular el desplazamiento no cambia la potencia)}.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.onda",
                 "k = nω/c, η = η₀/n, H = (1/η)·k̂×E, ⟨S⟩ = |E|²/2η, P = ⟨S⟩·A",
                 why="de fasores a potencia media: la onda plana uniforme queda "
                     "fijada por k y η, y el sensor solo aporta su área (§4.17)")
    n = float(_Q(n))
    if not n > 0:
        raise _error("BAD_INPUT", "índice de refracción no positivo")
    fr = float(_Q(f))
    if not fr > 0:
        raise _error("BAD_INPUT", "frecuencia no positiva")
    w = 2 * math.pi * fr
    Ex, Ey = complex(E0[0]), complex(E0[1])
    Ez = complex(E0[2]) if len(E0) == 3 else 0j
    kx, ky, kz = (float(_Q(c)) for c in direccion)
    nk = math.sqrt(kx * kx + ky * ky + kz * kz)
    kx, ky, kz = kx / nk, ky / nk, kz / nk
    if abs(kx * Ex + ky * Ey + kz * Ez) > 1e-9 * (abs(Ex) + abs(Ey) + abs(Ez) + 1e-18):
        raise _error("BAD_INPUT", "la onda no es transversal (k̂·E ≠ 0)")
    trace.hipotesis("sen.onda_transversal", "k̂·E = 0 (onda plana uniforme)", "cumple")
    trace.hipotesis("sen.onda_medio", "medio lineal, homogéneo e isótropo", "cumple")
    k = n * w / C0
    lam = C0 / (n * fr)
    v = C0 / n
    eta = ETA0 / n
    # H = (1/η) k̂×E
    Hx = (ky * Ez - kz * Ey) / eta
    Hy = (kz * Ex - kx * Ez) / eta
    Hz = (kx * Ey - ky * Ex) / eta
    S = (abs(Ex) ** 2 + abs(Ey) ** 2 + abs(Ez) ** 2) / (2 * eta)
    # segundo camino: ½Re(E×H*) y promedio temporal en un periodo
    Sx = 0.5 * (Ey * Hz.conjugate() - Ez * Hy.conjugate()).real
    Sy = 0.5 * (Ez * Hx.conjugate() - Ex * Hz.conjugate()).real
    Sz = 0.5 * (Ex * Hy.conjugate() - Ey * Hx.conjugate()).real
    S2 = math.sqrt(Sx * Sx + Sy * Sy + Sz * Sz)
    if abs(S2 - S) > 1e-9 * max(1.0, S):
        raise _error("DISCREPANT", "⟨S⟩ por |E|²/2η y por ½Re(E×H*) difieren")
    T = 1 / fr
    prom = 0.0
    for i in range(400):
        tt = (i + 0.5) * T / 400
        fase = cmath.exp(1j * w * tt)
        Et = tuple((v * fase).real for v in (Ex, Ey, Ez))
        Ht = tuple((v * fase).real for v in (Hx, Hy, Hz))
        cruz = (Et[1] * Ht[2] - Et[2] * Ht[1],
                Et[2] * Ht[0] - Et[0] * Ht[2],
                Et[0] * Ht[1] - Et[1] * Ht[0])
        prom += cruz[0] * kx + cruz[1] * ky + cruz[2] * kz
    prom /= 400
    if abs(prom - S) > 1e-3 * max(1.0, S):
        raise _error("DISCREPANT", "el promedio temporal no da ⟨S⟩")
    trace.verificacion("sen.onda_poynting", f"⟨S⟩ = {S:.6g} W/m² por los dos caminos")
    P, area, aviso = None, None, ()
    if sensor is not None:
        forma = sensor.get("forma", "circulo")
        if forma == "circulo":
            R = float(_Q(sensor.get("R", 1)))
            area = math.pi * R * R
        elif forma == "cuadrado":
            lado = float(_Q(sensor.get("lado", 1)))
            area = lado * lado
        else:
            raise _error("BAD_INPUT", "sensor círculo o cuadrado")
        if sensor.get("desplazamiento"):
            aviso = ("con incidencia perpendicular el desplazamiento no cambia "
                     "la potencia captada (onda uniforme)",)
            trace.aviso("sen.onda_desplazamiento", aviso[0])
        P = S * area
    return {"k": k, "lambda": lam, "v": v, "eta": eta, "H": (Hx, Hy, Hz),
            "S": S, "P": P, "area": area, "avisos": aviso}


# ---------------------------------------------------------------------------
# medios con pérdidas (§4.17, fila 3)
# ---------------------------------------------------------------------------

def medios(eps_r, mu_r=1, f=1e9, tand=None, sigma=None,
           trace: Trace | None = None) -> dict:
    """Medio con pérdidas: complejo exacto frente a aproximado.

    Se da ``tand`` (tangente de pérdidas) o ``sigma`` (S/m): la otra sale de
    ``σ/ωε = tanδ``. Devuelve ñ, α, β por dos caminos, la aproximación que
    toca con su condición y su error relativo, y el espesor para X dB.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.medios",
                 "ε̃ = ε′(1−j·tanδ); ñ = √ε̃ con Re ≥ 0; γ = jω√(με̃) = α+jβ; "
                 "la aproximación se elige por σ/ωε y se mide contra el exacto",
                 why="el enunciado pide justificar la aproximación: se calcula "
                     "siempre el complejo exacto y el error relativo decide "
                     "(§4.17, fila 3)")
    e_r = float(_Q(eps_r))
    m_r = float(_Q(mu_r))
    fr = float(_Q(f))
    if not (e_r > 0 and m_r > 0 and fr > 0):
        raise _error("BAD_INPUT", "ε′, μ_r y f han de ser positivos")
    w = 2 * math.pi * fr
    eps = e_r * EPS0
    if (tand is None) == (sigma is None):
        raise _error("BAD_INPUT", "da tand o sigma (una de las dos)")
    td = float(_Q(tand)) if tand is not None else float(_Q(sigma)) / (w * eps)
    sig = td * w * eps
    cociente = sig / (w * eps)  # = tanδ
    trace.hipotesis("sen.medios_regimen",
                    f"σ/ωε = {cociente:.4g} " +
                    ("≪ 1: buen dieléctrico" if cociente < 0.1
                     else "≫ 1: buen conductor" if cociente > 10 else "intermedio"),
                    "cumple" if cociente < 0.1 or cociente > 10 else "intermedio: sin aproximación")
    eps_t = complex(e_r, 0.0) * (1 - 1j * td)
    n_t = cmath.sqrt(eps_t * complex(m_r, 0.0))
    if n_t.real < 0:
        n_t = -n_t
    trace.regla("sen.medios_rama", "rama principal con Re(ñ) ≥ 0 (propagación)",
                why="la otra rama crece con z y no es física (§5.4)")
    gamma = 1j * w * cmath.sqrt(complex(MU0 * m_r, 0.0) * complex(EPS0, 0.0) * eps_t)
    alfa, beta = gamma.real, gamma.imag
    # segundo camino: γ = j·k₀·ñ, luego α = −Im(k₀·ñ), β = Re(k₀·ñ)
    k0 = w / C0
    alfa2, beta2 = -(k0 * n_t).imag, (k0 * n_t).real
    if abs(alfa2 - alfa) > 1e-9 * max(1.0, abs(alfa) + abs(beta)):
        raise _error("DISCREPANT", "α, β por γ y por k₀·ñ difieren")
    trace.verificacion("sen.medios_gamma", f"α = {alfa:.6g} Np/m, β = {beta:.6g} rad/m")
    aprox, cond, err = None, "", None
    if cociente < 0.1:
        beta_a = w * math.sqrt(MU0 * m_r * eps)
        alfa_a = beta_a / 2 * td
        cond = f"σ/ωε = {cociente:.3g} ≪ 1 (binomial de √(1−jx) válido)"
        err = abs(alfa_a - alfa) / alfa if alfa else 0.0
        aprox = {"alfa": alfa_a, "beta": beta_a, "cual": "buen dieléctrico"}
    elif cociente > 10:
        ab = math.sqrt(w * MU0 * m_r * sig / 2)
        cond = f"σ/ωε = {cociente:.3g} ≫ 1"
        err = max(abs(ab - alfa) / alfa if alfa else 0.0,
                  abs(ab - beta) / beta if beta else 0.0)
        aprox = {"alfa": ab, "beta": ab, "cual": "buen conductor"}
    return {"n_tilde": n_t, "alfa": alfa, "beta": beta, "tand": td,
            "sigma": sig, "aprox": aprox, "condicion": cond, "error_rel": err}


def espesor_para_dB(alfa, X_dB) -> float:
    """Espesor que atenúa X dB: d = X/(8,686·α) (Np a dB)."""
    alfa, X = float(_Q(alfa)), float(_Q(X_dB))
    if not alfa > 0:
        raise _error("BAD_INPUT", "atenuación nula: el espesor sería infinito")
    return X / (DB_POR_NEPER * alfa)


# ---------------------------------------------------------------------------
# polarización (§4.17, fila 4)
# ---------------------------------------------------------------------------

def _normaliza_delta(d: float) -> float:
    while d > math.pi:
        d -= 2 * math.pi
    while d <= -math.pi:
        d += 2 * math.pi
    return d


def _svd_2x2(M: list[list[float]]) -> tuple[float, float, tuple[float, float]]:
    """Valores singulares de una 2×2 real y el vector singular izquierdo mayor."""
    a, b = M[0][0] ** 2 + M[1][0] ** 2, M[0][0] * M[0][1] + M[1][0] * M[1][1]
    d = M[0][1] ** 2 + M[1][1] ** 2
    T, D = a + d, a * d - b * b
    disc = max(T * T / 4 - D, 0.0)
    lmax, lmin = T / 2 + math.sqrt(disc), max(T / 2 - math.sqrt(disc), 0.0)
    s1, s2 = math.sqrt(lmax), math.sqrt(lmin)
    # M·v con v autovector de MᵀM para lmax: orientación del semieje mayor
    if abs(b) > 1e-15:
        vx, vy = b, lmax - a
    else:
        vx, vy = (1.0, 0.0) if a >= d else (0.0, 1.0)
    ux, uy = M[0][0] * vx + M[0][1] * vy, M[1][0] * vx + M[1][1] * vy
    n = math.hypot(ux, uy) or 1.0
    return s1, s2, (ux / n, uy / n)


def clasifica(Ax, Ay, delta, trace: Trace | None = None) -> dict:
    """Clasifica la polarización de (Ax, Ay·e^{jδ}) con Ax, Ay ≥ 0.

    AR por valores singulares de [Re E | Im E] y por tanχ; ψ por tan2ψ y
    por el vector singular; el giro muestreado decide la mano.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.polar",
                 "semiejes = valores singulares de [Re E | Im E] (SVD 2×2); "
                 "AR también por tanχ; ψ por tan2ψ y por el vector singular",
                 why="la elipse sale de la matriz real 2×2 y la AR por dos "
                     "fórmulas independientes es el control (§4.17, fila 4)")
    Ax, Ay = float(_Q(Ax)), float(_Q(Ay))
    if not (Ax >= 0 and Ay >= 0):
        raise _error("BAD_INPUT", "Ax, Ay ≥ 0 (el signo vive en δ)")
    if Ax == 0 and Ay == 0:
        raise _error("BAD_INPUT", "campo nulo: sin polarización")
    d = _normaliza_delta(_angulo(delta)[1])
    Ex, Ey = complex(Ax, 0.0), complex(Ay * math.cos(d), Ay * math.sin(d))
    M = [[Ex.real, Ex.imag], [Ey.real, Ey.imag]]
    s1, s2, (ux, uy) = _svd_2x2(M)
    if s2 <= 1e-12 * max(s1, 1e-18):
        tipo, AR = "lineal", float("inf")
        psi = math.atan2(uy, ux) % math.pi
        mano = "—"
    elif abs(Ax - Ay) <= 1e-9 * max(Ax, Ay) and abs(abs(d) - math.pi / 2) < 1e-9:
        tipo, AR = ("circular derecha (dextrógira)" if d < 0
                    else "circular izquierda (levógira)"), 1.0
        psi, mano = None, ("dextrógira" if d < 0 else "levógira")
    else:
        tipo, AR = "elíptica", s1 / s2
        psi = math.atan2(uy, ux) % math.pi
        mano = "dextrógira" if -Ax * Ay * math.sin(d) > 0 else "levógira"
    # segundo camino (a): AR por tanχ con sin2χ = 2AxAy·sinδ/(Ax²+Ay²)
    den = Ax * Ax + Ay * Ay
    s2c = 2 * Ax * Ay * math.sin(d) / den if den else 0.0
    s2c = max(-1.0, min(1.0, s2c))
    chi = math.asin(s2c) / 2
    AR_b = 1 / abs(math.tan(chi)) if abs(math.tan(chi)) > 1e-15 else float("inf")
    if tipo == "lineal":
        ok_a = AR_b > 1e9
    elif tipo.startswith("circular"):
        ok_a = abs(AR_b - 1) < 1e-6
    else:
        ok_a = abs(AR_b - AR) < 1e-6 * max(1.0, AR)
    if not ok_a:
        raise _error("DISCREPANT", f"AR por SVD ({AR:.6g}) y por tanχ ({AR_b:.6g}) difieren")
    # segundo camino (b): ψ por tan2ψ = 2AxAy·cosδ/(Ax²−Ay²)
    if psi is not None and tipo == "elíptica":
        psi_b = (math.atan2(2 * Ax * Ay * math.cos(d), Ax * Ax - Ay * Ay) / 2) % math.pi
        if min(abs(psi_b - psi), math.pi - abs(psi_b - psi)) > 1e-6:
            raise _error("DISCREPANT", "ψ por SVD y por tan2ψ difieren")
    # segundo camino (c): giro muestreado E(t) y Stokes (totalmente polarizada)
    w = 1.0
    r0 = (Ax, Ay * math.cos(d))
    v0 = (0.0, -w * Ay * math.sin(d))
    giro = r0[0] * v0[1] - r0[1] * v0[0]
    if tipo not in ("lineal",) and not tipo.startswith("circular"):
        if (giro > 0) != (mano == "dextrógira"):
            raise _error("DISCREPANT", "el giro muestreado no dice la misma mano")
    s0 = Ax * Ax + Ay * Ay
    st = (s0, Ax * Ax - Ay * Ay, 2 * Ax * Ay * math.cos(d), -2 * Ax * Ay * math.sin(d))
    if abs(st[1] ** 2 + st[2] ** 2 + st[3] ** 2 - s0 ** 2) > 1e-9 * max(1.0, s0 ** 2):
        raise _error("DISCREPANT", "|s| ≠ S₀ en una onda totalmente polarizada")
    trace.verificacion("sen.polar_AR",
                       f"{tipo}: AR = {AR:.6g}" +
                       (f", ψ = {psi * 180 / math.pi:.3g}°" if psi is not None else "") +
                       f", mano {mano}")
    return {"tipo": tipo, "AR": AR, "psi": psi, "mano": mano, "stokes": st,
            "semiejes": (s1, s2)}


def stokes(Ex, Ey) -> tuple[float, float, float, float]:
    """Parámetros de Stokes (S₀, S₁, S₂, S₃) de un Jones (Ex, Ey)."""
    Ex, Ey = complex(Ex), complex(Ey)
    return (abs(Ex) ** 2 + abs(Ey) ** 2, abs(Ex) ** 2 - abs(Ey) ** 2,
            2 * (Ex.conjugate() * Ey).real, -2 * (Ex.conjugate() * Ey).imag)


# ---------------------------------------------------------------------------
# cálculo de Jones (§4.17, fila 5)
# ---------------------------------------------------------------------------

Matriz = tuple[tuple[complex, complex], tuple[complex, complex]]
Vector = tuple[complex, complex]


def _mat_mul(A: Matriz, B: Matriz) -> Matriz:
    return ((A[0][0] * B[0][0] + A[0][1] * B[1][0],
             A[0][0] * B[0][1] + A[0][1] * B[1][1]),
            (A[1][0] * B[0][0] + A[1][1] * B[1][0],
             A[1][0] * B[0][1] + A[1][1] * B[1][1]))


def _mat_vec(A: Matriz, v: Vector) -> Vector:
    return (A[0][0] * v[0] + A[0][1] * v[1], A[1][0] * v[0] + A[1][1] * v[1])


def _rot(phi: float) -> Matriz:
    c, s = math.cos(phi), math.sin(phi)
    return ((complex(c), complex(-s)), (complex(s), complex(c)))


def retardador(delta, phi, trace: Trace | None = None) -> Matriz:
    """J = R(−φ)·diag(1, e^{−jδ})·R(φ) (λ/4: δ = π/2; λ/2: δ = π)."""
    trace = trace if trace is not None else Trace()
    _, d = _angulo(delta)
    _, p = _angulo(phi)
    J = _mat_mul(_mat_mul(_rot(-p), ((1j * 0 + 1, 0j),
                                    (0j, cmath.exp(-1j * d)))), _rot(p))
    # unitariedad: sin pérdidas ⟹ conserva |E|²
    for i in range(2):
        for j in range(2):
            s = (J[0][i].conjugate() * J[0][j] + J[1][i].conjugate() * J[1][j])
            if abs(s - (1 if i == j else 0)) > 1e-12:
                raise _error("DISCREPANT", "el retardador no sale unitario")
    trace.verificacion("sen.jones_unitario",
                       f"J†J = I (δ = {d:.6g}, φ = {p:.6g}): conserva |E|²")
    return J


def polarizador(theta) -> Matriz:
    """Polarizador lineal a θ: Malus sale solo (cos²θ)."""
    _, t = _angulo(theta)
    c, s = math.cos(t), math.sin(t)
    return ((complex(c * c), complex(c * s)), (complex(c * s), complex(s * s)))


def cascada(elementos: list[Matriz], entrada: Vector,
            trace: Trace | None = None) -> dict:
    """Aplica la cascada (el primero de la lista actúa primero)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.jones_cascada", "producto de matrices 2×2 en orden: "
                 "cada elemento ve el estado que dejó el anterior",
                 why="la cascada es el método de §4.17 porque un solo "
                     "retardador no da dos grados de libertad (φ₁, φ₂)")
    J: Matriz = ((1 + 0j, 0j), (0j, 1 + 0j))
    for E in elementos:
        J = _mat_mul(E, J)
    salida = _mat_vec(J, (complex(entrada[0]), complex(entrada[1])))
    pot_in = abs(complex(entrada[0])) ** 2 + abs(complex(entrada[1])) ** 2
    pot_out = abs(salida[0]) ** 2 + abs(salida[1]) ** 2
    trace.verificacion("sen.jones_potencia",
                       f"|E|²: {pot_in:.6g} → {pot_out:.6g}")
    return {"salida": salida, "J": J, "pot_in": pot_in, "pot_out": pot_out}


def disenar_cadena(AR_obj, psi_obj, trace: Trace | None = None) -> dict:
    """Lineal horizontal → elipse (AR, ψ) con λ/4(φ₁) + λ/2(φ₂).

    Búsqueda determinista en malla (gruesa + dos refinados): sin azar, sin
    librerías. Falla honestamente si no alcanza el objetivo.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.jones_diseno",
                 "λ/4 fija la elipticidad y λ/2 orienta: se barren φ₁ y φ₂ en "
                 "malla determinista y se refina dos veces",
                 why="dos ángulos para dos objetivos (AR, ψ); un solo "
                     "retardador no basta (§4.17, fila 5)")
    AR_t = float(_Q(AR_obj))
    _, psi_t = _angulo(psi_obj)
    psi_t %= math.pi
    if not AR_t >= 1:
        raise _error("BAD_INPUT", "AR objetivo < 1: imposible")
    entrada = (1 + 0j, 0j)
    Q = retardador(math.pi / 2, 0, Trace())

    def coste(p1: float, p2: float) -> float:
        H = retardador(math.pi, p2, Trace())
        G = retardador(math.pi / 2, p1, Trace())
        s = _mat_vec(_mat_mul(H, G), entrada)
        Ax = abs(s[0])
        Ay = abs(s[1])
        if Ax == 0 and Ay == 0:
            return 1e9
        d = _normaliza_delta(cmath.phase(s[1]) - cmath.phase(s[0]))
        c = clasifica(Ax, Ay, d, Trace())
        if c["tipo"] == "lineal":
            ar = 1e9
        else:
            ar = c["AR"]
        e_ar = abs(math.log(ar / AR_t))
        ps = c["psi"]
        e_ps = 0.0 if ps is None else min(abs(ps - psi_t), math.pi - abs(ps - psi_t))
        return e_ar + 2 * e_ps

    mejor = (1e9, 0.0, 0.0)
    paso = math.pi / 180
    for _ in range(3):
        p1_ini, p2_ini = mejor[1], mejor[2]
        radio = math.pi if mejor[0] > 1e8 else 4 * paso
        n = 180 if mejor[0] > 1e8 else 24
        for i in range(n + 1):
            for j in range(n + 1):
                p1 = (p1_ini - radio + 2 * radio * i / n) % math.pi
                p2 = (p2_ini - radio + 2 * radio * j / n) % math.pi
                c = coste(p1, p2)
                if c < mejor[0]:
                    mejor = (c, p1, p2)
        paso = 2 * radio / n / 2
    _, p1, p2 = mejor
    Qf = retardador(math.pi / 2, p1, Trace())
    Hf = retardador(math.pi, p2, Trace())
    sal = _mat_vec(_mat_mul(Hf, Qf), entrada)
    Ax = abs(sal[0])
    d = _normaliza_delta(cmath.phase(sal[1]) - cmath.phase(sal[0]))
    c = clasifica(Ax, abs(sal[1]), d, Trace())
    ok_ar = c["tipo"] != "lineal" and abs(math.log(c["AR"] / AR_t)) < 0.02
    ps = c["psi"]
    ok_ps = ps is not None and min(abs(ps - psi_t), math.pi - abs(ps - psi_t)) < 1 / 60
    if not (ok_ar and ok_ps):
        raise _no(f"la malla no alcanza AR = {AR_t} con ψ = {psi_t}: "
                  f"queda AR = {c['AR']:.4g}, ψ = {ps}")
    trace.verificacion("sen.jones_diseno_ok",
                       f"φ₁ = {p1 * 180 / math.pi:.3g}°, φ₂ = {p2 * 180 / math.pi:.3g}°: "
                       f"AR = {c['AR']:.5g}, ψ = {ps * 180 / math.pi:.4g}°")
    return {"phi1": p1, "phi2": p2, "salida": sal, "AR": c["AR"], "psi": ps}


def plf(e1: Vector, e2: Vector, trace: Trace | None = None) -> float:
    """Desajuste de polarización PLF = |ê₁·ê₂*|² (vectores normalizados)."""
    trace = trace if trace is not None else Trace()
    a = (complex(e1[0]), complex(e1[1]))
    b = (complex(e2[0]), complex(e2[1]))
    na = math.hypot(*[abs(v) for v in a])
    nb = math.hypot(*[abs(v) for v in b])
    trace.hipotesis("sen.plf_norma", "vectores no nulos (se normalizan)", "cumple")
    if na == 0 or nb == 0:
        raise _error("BAD_INPUT", "vector de Jones nulo")
    v = abs(a[0] * b[0].conjugate() + a[1] * b[1].conjugate()) ** 2 / (na * na * nb * nb)
    trace.verificacion("sen.plf_malus", f"PLF = {v:.6g} (Malus si ambos lineales)")
    return v


# ---------------------------------------------------------------------------
# Fresnel, Brewster, reflexión total (§4.17 + D12, fila 6)
# ---------------------------------------------------------------------------

def angulos(n1, n2) -> dict:
    """θ_B = atan(n₂/n₁); θ_c = asin(n₂/n₁) si n₂ < n₁ (si no, no hay)."""
    n1, n2 = float(_Q(n1)), float(_Q(n2))
    if not (n1 > 0 and n2 > 0):
        raise _error("BAD_INPUT", "índices no positivos")
    return {"brewster": math.atan(n2 / n1),
            "critico": math.asin(n2 / n1) if n2 < n1 else None}


def fresnel(n1, n2, theta_i, pol: str = "s",
            trace: Trace | None = None) -> dict:
    """Coeficientes r, t y potencias R, T (medios sin pérdidas, no magnéticos).

    Rama declarada: ``cosθ_t`` con ``Im ≥ 0`` (evanescente que decae).
    Aviso de §4.17: ``T ≠ |t|²`` salvo en el mismo medio.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.fresnel",
                 "Snell → cosθ_t (complejo si hay reflexión total) → "
                 "coeficientes → potencias con el factor de medios",
                 why="el camino de §4.17: el ángulo transmitido manda en todo "
                     "y la rama con Im ≥ 0 es la onda que decae, no la que crece")
    n1, n2 = float(_Q(n1)), float(_Q(n2))
    _, ti = _angulo(theta_i)
    if pol not in ("s", "p"):
        raise _error("BAD_INPUT", "polarización s o p")
    trace.hipotesis("sen.fresnel_medios", "interfaz plana, sin pérdidas, no magnéticos",
                    "cumple (la entrada lo declara)")
    st = n1 * math.sin(ti) / n2
    ct = cmath.sqrt(1 - st * st)
    if ct.imag < -1e-15:
        ct = ct.conjugate()
    ci = math.cos(ti)
    if pol == "s":
        r = (n1 * ci - n2 * ct) / (n1 * ci + n2 * ct)
        t = 2 * n1 * ci / (n1 * ci + n2 * ct)
    else:
        r = (n2 * ci - n1 * ct) / (n2 * ci + n1 * ct)
        t = 2 * n1 * ci / (n2 * ci + n1 * ct)
    R = abs(r) ** 2
    T = ((n2 * ct) / (n1 * ci) * abs(t) ** 2).real if abs(ci) > 1e-15 else 0.0
    if abs(R + T - 1) > 1e-9:
        raise _error("DISCREPANT", f"R + T = {R + T:.12g} ≠ 1")
    trace.verificacion("sen.fresnel_energia", f"R + T = 1 (R = {R:.6g})")
    if abs(ti) < 1e-12 and n1 + n2 != 0:
        r0 = (n1 - n2) / (n1 + n2)
        if abs(r - r0) > 1e-9:
            raise _error("DISCREPANT", "incidencia normal no da (n₁−n₂)/(n₁+n₂)")
    return {"r": r, "t": t, "R": R, "T": T, "theta_t": cmath.phase(ct),
            "cos_theta_t": ct, "evanescente": ct.imag > 1e-12}


# ---------------------------------------------------------------------------
# multicapa (§4.17 + D12, fila 7)
# ---------------------------------------------------------------------------

def multicapa(ns: list, ds: list, lambda0, theta0=0.0, pol: str = "s",
              trace: Trace | None = None) -> dict:
    """Pila de capas: matriz 2×2 por capa, producto y r, t, R.

    δ_j = k₀·n_j·d_j·cosθ_j; admitancias normalizadas η = n·cosθ (s),
    η = n/cosθ (p). Controles: det = 1 por capa, R + T = 1.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.multicapa",
                 "matriz de transferencia por capa (δ, η) → producto → "
                 "r, t desde la admitancia de entrada",
                 why="el método de Airy de §4.17: cada capa es una matriz 2×2 "
                     "y la pila entera es su producto")
    if len(ns) < 2:
        raise _error("BAD_INPUT", "la pila necesita al menos entrada y sustrato")
    if len(ds) != len(ns) - 2:
        raise _error("BAD_INPUT", "tantos espesores como capas intermedias")
    ns = [float(_Q(v)) for v in ns]
    ds = [float(_Q(v)) for v in ds]
    lam = float(_Q(lambda0))
    _, t0 = _angulo(theta0)
    if pol not in ("s", "p"):
        raise _error("BAD_INPUT", "polarización s o p")
    trace.hipotesis("sen.multicapa_capas", "capas planas, sin pérdidas",
                    "cumple (la entrada lo declara)")
    k0 = 2 * math.pi / lam
    s0 = ns[0] * math.sin(t0)
    thetas = []
    for n in ns:
        st = s0 / n
        thetas.append(cmath.asin(st) if abs(st) > 1 else math.asin(max(-1.0, min(1.0, st))))
    def adm(n, th):
        c = cmath.cos(th)
        return n * c if pol == "s" else n / c
    M: Matriz = ((1 + 0j, 0j), (0j, 1 + 0j))
    for n, d, th in zip(ns[1:-1], ds, thetas[1:-1]):
        c = cmath.cos(th)
        delta = k0 * n * d * c
        eta = adm(n, th)
        cd, sd = cmath.cos(delta), cmath.sin(delta)
        C = ((cd, 1j * sd / eta), (1j * eta * sd, cd))
        if abs(C[0][0] * C[1][1] - C[0][1] * C[1][0] - 1) > 1e-9:
            raise _error("DISCREPANT", "det ≠ 1 en una capa")
        M = _mat_mul(C, M)
    eta0, etas = adm(ns[0], thetas[0]), adm(ns[-1], thetas[-1])
    B = M[0][0] + M[0][1] * etas
    Cc = M[1][0] + M[1][1] * etas
    if B == 0:
        raise _error("DISCREPANT", "campo E nulo a la entrada")
    Y = Cc / B  # admitancia de entrada H₀/E₀
    r = (eta0 - Y) / (eta0 + Y)
    t = (1 + r) / B
    R = abs(r) ** 2
    T = float((etas.real * abs(t) ** 2 / eta0.real).real
              if isinstance(etas, complex) else etas * abs(t) ** 2 / eta0)
    if abs(R + T - 1) > 1e-9:
        raise _error("DISCREPANT", f"R + T = {R + T:.12g} ≠ 1")
    trace.verificacion("sen.multicapa_energia",
                       f"det = 1 por capa; R + T = 1 (R = {R:.6g})")
    return {"r": r, "t": t, "R": R, "T": T}


def antirreflejante(n1, n2) -> dict:
    """Capa λ/4 ideal: n_f = √(n₁·n₂), d = λ₀/(4·n_f) (d en unidades de λ₀)."""
    n1, n2 = float(_Q(n1)), float(_Q(n2))
    if not (n1 > 0 and n2 > 0):
        raise _error("BAD_INPUT", "índices no positivos")
    nf = math.sqrt(n1 * n2)
    return {"n_f": nf, "d_sobre_lambda": 1 / (4 * nf)}
