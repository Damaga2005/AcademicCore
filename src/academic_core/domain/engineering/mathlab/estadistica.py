# SPDX-License-Identifier: MIT
"""ML-9 (§4.6, tipos 4, 5 y 11 de §15.1): estadística.

- **Descriptiva** exacta con fracciones: media, mediana, moda, cuartiles (método
  declarado), varianza con ``n`` y con ``n − 1`` (las dos, convención declarada,
  §15.2 punto 5), atípicos por ``1,5·RIC`` y los datos del histograma y del
  diagrama de caja.
- **Intervalos de confianza**: media (z con σ conocida, t con σ estimada: la
  elección se justifica), varianza (χ²), proporción, diferencias y **tamaño de
  muestra**. Segundo camino: el cuantil se comprueba con la F por cuadratura y el
  **método** se contrasta con su cobertura en una simulación sembrada.
- **Contrastes** z, t, χ² (varianza, bondad de ajuste, independencia), con
  p-valor por la función especial y por cuadratura.
- **Regresión** por mínimos cuadrados exacta: ``Xᵀe = 0`` comprobado en ℚ.
- **Estimadores** por momentos y máxima verosimilitud de las familias del curso
  (forma cerrada) y de una densidad con parámetro (numérico, declarado), con la
  log-verosimilitud dibujada y su máximo buscado por otro camino (sección áurea).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import probabilidad as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _datos(xs) -> list[Fraction]:
    if xs is None:
        raise _error("BAD_INPUT", "no hay datos")
    if isinstance(xs, str):
        xs = [t for t in xs.replace(";", " ").replace("\n", " ").split() if t]
    datos = [P.fraccion(v, "un dato") for v in xs]
    if not datos:
        raise _error("BAD_INPUT", "no hay datos")
    return datos


def _f(v) -> float:
    return float(v)


def _num(v: Fraction | float) -> str:
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        return f"{v} ≈ {float(v):.6g}"
    return f"{v:.6g}"


# ---------------------------------------------------------------------------
# descriptiva
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Descriptiva:
    n: int
    media: Fraction
    mediana: Fraction
    modas: tuple[Fraction, ...]
    q1: Fraction
    q3: Fraction
    var_n: Fraction
    var_n1: Fraction | None
    minimo: Fraction
    maximo: Fraction
    atipicos: tuple[Fraction, ...]
    bigotes: tuple[Fraction, Fraction]
    histograma: tuple[tuple[float, float, int], ...]

    @property
    def ric(self) -> Fraction:
        return self.q3 - self.q1

    def texto(self) -> str:
        partes = [f"n = {self.n}", f"x̄ = {_num(self.media)}", f"mediana = {_num(self.mediana)}",
                  "moda = " + (", ".join(_num(m) for m in self.modas) if self.modas else "no hay"),
                  f"Q1 = {_num(self.q1)}, Q3 = {_num(self.q3)}, RIC = {_num(self.ric)}",
                  f"varianza con n: {_num(self.var_n)} (σ = {math.sqrt(self.var_n):.6g})"]
        if self.var_n1 is not None:
            partes.append(f"cuasivarianza con n − 1: {_num(self.var_n1)} "
                          f"(s = {math.sqrt(self.var_n1):.6g})")
        if self.atipicos:
            partes.append("atípicos: " + ", ".join(_num(a) for a in self.atipicos))
        return "; ".join(partes)


def _cuantil_tipo7(orden: list[Fraction], p: Fraction) -> Fraction:
    """Interpolación lineal entre estadísticos de orden en ``h = (n − 1)·p`` (la de R
    por defecto y la de las hojas de cálculo)."""
    n = len(orden)
    h = (n - 1) * p
    i = int(h)
    frac = h - i
    if i + 1 >= n:
        return orden[-1]
    return orden[i] + frac * (orden[i + 1] - orden[i])


def descriptiva(xs, trace: Trace | None = None) -> Descriptiva:
    trace = trace if trace is not None else Trace()
    datos = _datos(xs)
    n = len(datos)
    orden = sorted(datos)
    media = sum(datos, Fraction(0)) / n
    trace.regla("desc.media", f"x̄ = Σxᵢ/n = {sum(datos, Fraction(0))}/{n} = {_num(media)}")
    mediana = orden[n // 2] if n % 2 else (orden[n // 2 - 1] + orden[n // 2]) / 2
    trace.regla("desc.mediana", f"mediana = {_num(mediana)}",
                why="dato central de los ordenados (media de los dos centrales si n es par)")
    cuenta: dict[Fraction, int] = {}
    for x in datos:
        cuenta[x] = cuenta.get(x, 0) + 1
    maxc = max(cuenta.values())
    modas = tuple(sorted(x for x, c in cuenta.items() if c == maxc)) if maxc > 1 else ()
    q1 = _cuantil_tipo7(orden, Fraction(1, 4))
    q3 = _cuantil_tipo7(orden, Fraction(3, 4))
    trace.convencion("desc.cuartiles", "cuartiles por interpolación lineal en h = (n − 1)·p "
                                       "(tipo 7: R, hojas de cálculo); otros libros usan la "
                                       "posición (n + 1)·p y dan valores algo distintos")
    trace.regla("desc.cuartiles", f"Q1 = {_num(q1)}, Q3 = {_num(q3)}")
    sc = sum(((x - media) ** 2 for x in datos), Fraction(0))
    var_n = sc / n
    var_n1 = sc / (n - 1) if n > 1 else None
    trace.convencion("desc.varianza", "se dan las dos: con n (varianza de los datos) y con "
                                      "n − 1 (cuasivarianza, estimador insesgado)")
    trace.regla("desc.varianza", f"Σ(xᵢ − x̄)² = {_num(sc)}; /n = {_num(var_n)}"
                + (f"; /(n − 1) = {_num(var_n1)}" if var_n1 is not None else ""))
    # segundo camino: identidad Σx² − n·x̄² (exacta) y mediana por recuento
    sc2 = sum((x * x for x in datos), Fraction(0)) - n * media * media
    if sc2 != sc:
        raise _error("DISCREPANT", "Σ(x − x̄)² ≠ Σx² − n·x̄²")
    menores = sum(1 for x in datos if x < mediana)
    mayores = sum(1 for x in datos if x > mediana)
    if menores > n // 2 or mayores > n // 2:
        raise _error("DISCREPANT", "la mediana no deja la mitad a cada lado")
    trace.verificacion("desc.identidad", "Σ(xᵢ − x̄)² = Σxᵢ² − n·x̄² (exacto) y la mediana deja "
                                         f"{menores} datos por debajo y {mayores} por encima")
    ric = q3 - q1
    lo_b, hi_b = q1 - Fraction(3, 2) * ric, q3 + Fraction(3, 2) * ric
    atip = tuple(x for x in orden if x < lo_b or x > hi_b)
    dentro = [x for x in orden if lo_b <= x <= hi_b]
    bigotes = (dentro[0], dentro[-1]) if dentro else (orden[0], orden[-1])
    k = max(1, math.ceil(math.log2(n) + 1))
    trace.convencion("desc.histograma", f"{k} clases por la regla de Sturges, ⌈log₂ n + 1⌉")
    a, b = float(orden[0]), float(orden[-1])
    ancho = (b - a) / k if b > a else 1.0
    clases = []
    for i in range(k):
        lo, hi = a + i * ancho, a + (i + 1) * ancho
        c = sum(1 for x in datos if (lo <= float(x) < hi) or (i == k - 1 and float(x) == hi))
        clases.append((lo, hi, c))
    return Descriptiva(n, media, mediana, modas, q1, q3, var_n, var_n1, orden[0], orden[-1],
                       atip, bigotes, tuple(clases))


# ---------------------------------------------------------------------------
# intervalos de confianza
# ---------------------------------------------------------------------------


@dataclass
class Intervalo:
    tipo: str
    estimacion: float
    lo: float
    hi: float
    nivel: Fraction
    cuantiles: dict
    formula: str
    exacto: str = ""
    cobertura: P.Simulacion | None = None
    extra: dict = field(default_factory=dict)

    def texto(self) -> str:
        return (f"IC al {float(self.nivel) * 100:g} % para {self.tipo}: "
                f"[{self.lo:.6g}, {self.hi:.6g}]" + (f" = {self.exacto}" if self.exacto else ""))


def _resumen(e: dict, trace: Trace) -> tuple[int, Fraction, Fraction | None]:
    """``(n, x̄, s²)`` de los datos o del resumen dado (``n``, ``media``, ``s`` o ``s2``)."""
    if e.get("datos") is not None:
        d = descriptiva(e["datos"], Trace())
        trace.regla("ic.resumen", f"de los datos: n = {d.n}, x̄ = {_num(d.media)}, "
                                  f"s² (n − 1) = {_num(d.var_n1) if d.var_n1 is not None else '—'}")
        return d.n, d.media, d.var_n1
    n = int(P.fraccion(e["n"], "n"))
    media = P.fraccion(e.get("media", e.get("x")), "la media")
    s2 = None
    if e.get("s2") is not None:
        s2 = P.fraccion(e["s2"], "s²")
    elif e.get("s") is not None:
        s2 = P.fraccion(e["s"], "s") ** 2
    return n, media, s2


def _z(alfa_medio: float) -> float:
    return P.Phi_inv(1 - alfa_medio)


def _comprueba_cuantil(ley: str, q: float, p: float, trace: Trace, **gl) -> None:
    d = P.distribucion(ley, gl)
    Fq = P.F_por_cuadratura(d, q)
    if abs(Fq - p) > 1e-7:
        raise _error("DISCREPANT", f"F({q}) por cuadratura = {Fq} y no {p}")
    trace.verificacion("ic.cuantil", f"{d.titulo()}: F({q:.6g}) = {Fq:.10f} por cuadratura de "
                                     f"la densidad (se buscaba {p})")


def intervalo(e: dict, trace: Trace | None = None, semilla: int = 20261007) -> Intervalo:
    """``e["parametro"]`` ∈ media, varianza, proporcion, dif_medias, dif_proporciones,
    tamano_media, tamano_proporcion; ``e["nivel"]`` (0,95 por defecto)."""
    trace = trace if trace is not None else Trace()
    nivel = P.fraccion(e.get("nivel", "0.95"), "el nivel de confianza")
    if not 0 < nivel < 1:
        raise _error("BAD_INPUT", "el nivel tiene que estar entre 0 y 1")
    alfa = 1 - nivel
    par = str(e.get("parametro", "media")).lower()
    trace.convencion("ic.nivel", f"nivel 1 − α = {nivel}: α = {alfa}, α/2 = {alfa / 2}")
    if par == "media":
        return _ic_media(e, nivel, trace, semilla)
    if par == "varianza":
        return _ic_varianza(e, nivel, trace, semilla)
    if par == "proporcion":
        return _ic_proporcion(e, nivel, trace, semilla)
    if par == "dif_medias":
        return _ic_dif_medias(e, nivel, trace)
    if par == "dif_proporciones":
        return _ic_dif_prop(e, nivel, trace)
    if par in ("tamano_media", "tamano_proporcion"):
        return _tamano(e, par, nivel, trace)
    raise _error("BAD_INPUT", f"parámetro «{par}» no reconocido")


def _ic_media(e, nivel, trace, semilla) -> Intervalo:
    n, media, s2 = _resumen(e, trace)
    a2 = float(1 - nivel) / 2
    sigma = e.get("sigma")
    if sigma is not None:
        sig = P.fraccion(sigma, "σ")
        q = _z(a2)
        trace.metodo("ic.eleccion", f"σ = {sig} conocida → z",
                     why="con σ conocida, (X̄ − μ)/(σ/√n) es N(0, 1) exacta (población normal) o "
                         "aproximada (TCL); no hay nada que estimar en el denominador",
                     alternatives=(("t de Student", "solo cuando σ se sustituye por s"),))
        _comprueba_cuantil("normal", q, 1 - a2, trace)
        ancho = q * float(sig) / math.sqrt(n)
        formula = f"x̄ ± z_(α/2)·σ/√n = {_num(media)} ± {q:.6g}·{sig}/√{n}"
        sim = _cobertura(lambda g: _cubre_z(g, n, float(sig), q), nivel, semilla)
        cuant = {"z": q}
    else:
        if s2 is None:
            raise _error("BAD_INPUT", "falta σ (conocida) o s / los datos")
        if n < 2:
            raise _error("BAD_INPUT", "con un dato no se puede estimar la varianza")
        q = P.distribucion("t", {"nu": n - 1}).cuantil(1 - a2)
        trace.metodo("ic.eleccion", f"σ desconocida → t de Student con ν = n − 1 = {n - 1}",
                     why="al sustituir σ por s, (X̄ − μ)/(s/√n) sigue una t de Student con n − 1 "
                         "grados de libertad si la población es normal; con n grande se parece "
                         "a z, pero t es la correcta",
                     alternatives=(("z", f"subestima el ancho con n = {n}" if n < 30 else
                                    "aproximación aceptable con n ≥ 30, pero t sigue siendo "
                                    "la exacta"),))
        trace.hipotesis("ic.normalidad", "población normal (o n grande, por el TCL)", "se asume")
        _comprueba_cuantil("t", q, 1 - a2, trace, nu=n - 1)
        ancho = q * math.sqrt(float(s2)) / math.sqrt(n)
        formula = f"x̄ ± t_(n−1, α/2)·s/√n = {_num(media)} ± {q:.6g}·{math.sqrt(float(s2)):.6g}/√{n}"
        sim = _cobertura(lambda g: _cubre_t(g, n, q), nivel, semilla) if n <= 400 else None
        cuant = {"t": q, "ν": n - 1}
    trace.regla("ic.media", formula + f" = [{float(media) - ancho:.6g}, {float(media) + ancho:.6g}]")
    I = Intervalo("la media μ", float(media), float(media) - ancho, float(media) + ancho, nivel,
                  cuant, formula, cobertura=sim)
    I.extra["tabla"] = {k: P.redondeo_tabla(v, 3) for k, v in cuant.items() if k != "ν"}
    return I


def _cubre_z(g, n, sigma, q) -> float:
    m = sum(sigma * P.normal_std(g) for _ in range(n)) / n
    return 1.0 if abs(m) <= q * sigma / math.sqrt(n) else 0.0


def _cubre_t(g, n, q) -> float:
    xs = [P.normal_std(g) for _ in range(n)]
    m = sum(xs) / n
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return 1.0 if abs(m) <= q * s / math.sqrt(n) else 0.0


def _cobertura(experimento, nivel, semilla, repeticiones: int = 3000) -> P.Simulacion | None:
    sim = P.simula(experimento, repeticiones, semilla)
    if not sim.dentro(float(nivel), 5):
        raise _error("DISCREPANT", f"la cobertura simulada del método es {sim.texto()}, no "
                                   f"{float(nivel)}")
    return sim


def _ic_varianza(e, nivel, trace, semilla) -> Intervalo:
    n, media, s2 = _resumen(e, trace)
    if s2 is None or n < 2:
        raise _error("BAD_INPUT", "hacen falta s² (o los datos) y n ≥ 2")
    a2 = float(1 - nivel) / 2
    chi = P.distribucion("chi2", {"k": n - 1})
    qa, qb = chi.cuantil(a2), chi.cuantil(1 - a2)
    trace.metodo("ic.varianza", f"(n − 1)s²/σ² ~ χ²_{n - 1}",
                 why="con población normal, la cuasivarianza escalada sigue una χ²; el intervalo "
                     "no es simétrico porque la χ² no lo es")
    trace.hipotesis("ic.normalidad", "población normal (aquí el TCL no basta)", "se asume")
    _comprueba_cuantil("chi2", qa, a2, trace, k=n - 1)
    _comprueba_cuantil("chi2", qb, 1 - a2, trace, k=n - 1)
    lo, hi = (n - 1) * float(s2) / qb, (n - 1) * float(s2) / qa
    formula = f"[(n−1)s²/χ²_(1−α/2), (n−1)s²/χ²_(α/2)] con χ² = {qb:.6g} y {qa:.6g}"
    trace.regla("ic.varianza_res", formula + f" = [{lo:.6g}, {hi:.6g}]")

    def cubre(g):
        xs = [P.normal_std(g) for _ in range(n)]
        m = sum(xs) / n
        s = sum((x - m) ** 2 for x in xs) / (n - 1)
        return 1.0 if (n - 1) * s / qb <= 1 <= (n - 1) * s / qa else 0.0
    sim = _cobertura(cubre, nivel, semilla) if n <= 400 else None
    I = Intervalo("la varianza σ²", float(s2), lo, hi, nivel, {"χ²_inf": qa, "χ²_sup": qb},
                  formula, cobertura=sim)
    I.extra["desviacion"] = (math.sqrt(lo), math.sqrt(hi))
    return I


def _ic_proporcion(e, nivel, trace, semilla) -> Intervalo:
    n = int(P.fraccion(e["n"], "n"))
    if e.get("exitos") is not None:
        x = int(P.fraccion(e["exitos"], "los éxitos"))
        p = Fraction(x, n)
    else:
        p = P.fraccion(e["p"], "p̂")
    a2 = float(1 - nivel) / 2
    q = _z(a2)
    _comprueba_cuantil("normal", q, 1 - a2, trace)
    se = math.sqrt(float(p * (1 - p)) / n)
    trace.metodo("ic.proporcion", "p̂ ± z·√(p̂(1 − p̂)/n) (Wald, aproximación normal)",
                 why="por el TCL, p̂ es aproximadamente normal con varianza p(1 − p)/n")
    cumple = n * p >= 5 and n * (1 - p) >= 5
    trace.hipotesis("ic.np5", f"n·p̂ = {_num(n * p)} ≥ 5 y n·(1 − p̂) = {_num(n * (1 - p))} ≥ 5",
                    "se cumple" if cumple else "NO se cumple: la aproximación es pobre")
    lo, hi = float(p) - q * se, float(p) + q * se
    # Wilson como contraste (mejor cobertura con n pequeño)
    z2 = q * q
    centro = (float(p) + z2 / (2 * n)) / (1 + z2 / n)
    semi = q * math.sqrt(float(p * (1 - p)) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    trace.regla("ic.proporcion_res", f"[{lo:.6g}, {hi:.6g}]; Wilson (contraste): "
                                     f"[{centro - semi:.6g}, {centro + semi:.6g}]")
    I = Intervalo("la proporción p", float(p), lo, hi, nivel, {"z": q},
                  f"p̂ ± z·√(p̂(1−p̂)/n) con p̂ = {p}")
    I.extra["wilson"] = (centro - semi, centro + semi)
    I.extra["condicion"] = cumple
    return I


def _ic_dif_medias(e, nivel, trace) -> Intervalo:
    g1, g2 = e["grupo1"], e["grupo2"]
    t1, t2 = Trace(), Trace()
    n1, m1, s1 = _resumen(g1, t1)
    n2, m2, s2 = _resumen(g2, t2)
    a2 = float(1 - nivel) / 2
    dif = float(m1 - m2)
    if g1.get("sigma") is not None and g2.get("sigma") is not None:
        v = float(P.fraccion(g1["sigma"], "σ1")) ** 2 / n1 + float(P.fraccion(g2["sigma"], "σ2")) ** 2 / n2
        q = _z(a2)
        trace.metodo("ic.dif_z", "σ₁ y σ₂ conocidas → z", why="la diferencia de medias normales "
                                                            "es normal con varianza σ₁²/n₁ + σ₂²/n₂")
        cuant = {"z": q}
    elif e.get("varianzas_iguales", True):
        sp2 = ((n1 - 1) * float(s1) + (n2 - 1) * float(s2)) / (n1 + n2 - 2)
        v = sp2 * (1 / n1 + 1 / n2)
        q = P.distribucion("t", {"nu": n1 + n2 - 2}).cuantil(1 - a2)
        trace.metodo("ic.dif_t", f"varianzas iguales → t con ν = n₁ + n₂ − 2 = {n1 + n2 - 2} y "
                                 f"s_p² = {sp2:.6g}",
                     why="la varianza común se estima ponderando las dos cuasivarianzas")
        trace.hipotesis("ic.igualdad", "σ₁² = σ₂² (declarado)", "se asume")
        _comprueba_cuantil("t", q, 1 - a2, trace, nu=n1 + n2 - 2)
        cuant = {"t": q, "ν": n1 + n2 - 2}
    else:
        a, b = float(s1) / n1, float(s2) / n2
        nu = (a + b) ** 2 / (a * a / (n1 - 1) + b * b / (n2 - 1))
        v = a + b
        q = P.distribucion("t", {"nu": Fraction(nu).limit_denominator(10 ** 6)}).cuantil(1 - a2)
        trace.metodo("ic.dif_welch", f"varianzas distintas → Welch, ν ≈ {nu:.4g}",
                     why="Welch-Satterthwaite aproxima los grados de libertad")
        cuant = {"t": q, "ν": nu}
    ancho = q * math.sqrt(v)
    trace.regla("ic.dif_medias", f"(x̄₁ − x̄₂) ± q·√V = {dif:.6g} ± {ancho:.6g}")
    return Intervalo("μ₁ − μ₂", dif, dif - ancho, dif + ancho, nivel, cuant,
                     "(x̄₁ − x̄₂) ± q·√V")


def _ic_dif_prop(e, nivel, trace) -> Intervalo:
    def lee(g):
        n = int(P.fraccion(g["n"], "n"))
        p = Fraction(int(P.fraccion(g["exitos"], "éxitos")), n) if g.get("exitos") is not None \
            else P.fraccion(g["p"], "p")
        return n, p
    n1, p1 = lee(e["grupo1"])
    n2, p2 = lee(e["grupo2"])
    a2 = float(1 - nivel) / 2
    q = _z(a2)
    se = math.sqrt(float(p1 * (1 - p1)) / n1 + float(p2 * (1 - p2)) / n2)
    dif = float(p1 - p2)
    trace.metodo("ic.dif_prop", "(p̂₁ − p̂₂) ± z·√(p̂₁q̂₁/n₁ + p̂₂q̂₂/n₂)",
                 why="dos proporciones independientes, aproximación normal")
    trace.regla("ic.dif_prop_res", f"{dif:.6g} ± {q * se:.6g}")
    return Intervalo("p₁ − p₂", dif, dif - q * se, dif + q * se, nivel, {"z": q},
                     "(p̂₁ − p̂₂) ± z·SE")


def _tamano(e, par, nivel, trace) -> Intervalo:
    a2 = float(1 - nivel) / 2
    q = _z(a2)
    E = P.fraccion(e["error"], "el error máximo E")
    if par == "tamano_media":
        sigma = P.fraccion(e["sigma"], "σ")
        bruto = (q * float(sigma) / float(E)) ** 2
        formula = f"n ≥ (z·σ/E)² = ({q:.6g}·{sigma}/{E})² = {bruto:.6g}"
    else:
        p = P.fraccion(e.get("p", "0.5"), "p")
        if e.get("p") is None:
            trace.convencion("ic.p_conservador", "sin estimación previa se toma p = 1/2, que "
                                                 "maximiza p(1 − p) (el caso peor)")
        bruto = q * q * float(p * (1 - p)) / float(E) ** 2
        formula = f"n ≥ z²·p(1 − p)/E² = {bruto:.6g}"
    n = math.ceil(bruto - 1e-9)
    trace.regla("ic.tamano", formula + f" → n = {n}",
                why="se despeja n del semiancho del intervalo y se redondea HACIA ARRIBA")
    # segundo camino: con n el semiancho es ≤ E y con n − 1 ya no
    def semi(m):
        if par == "tamano_media":
            return q * float(sigma) / math.sqrt(m)
        return q * math.sqrt(float(p * (1 - p)) / m)
    if semi(n) > float(E) + 1e-12 or (n > 1 and semi(n - 1) <= float(E) - 1e-12):
        raise _error("DISCREPANT", "el tamaño no es el mínimo")
    trace.verificacion("ic.tamano_min", f"con n = {n} el semiancho es {semi(n):.6g} ≤ {E}; con "
                                        f"n − 1 sería {semi(n - 1) if n > 1 else math.inf:.6g}")
    return Intervalo("el tamaño de muestra", n, n, n, nivel, {"z": q}, formula, exacto=str(n))


# ---------------------------------------------------------------------------
# contrastes de hipótesis
# ---------------------------------------------------------------------------


@dataclass
class Contraste:
    nombre: str
    estadistico: float
    ley: str
    p_valor: float
    critico: tuple[float, ...]
    rechaza: bool
    alfa: Fraction
    alternativa: str
    detalle: dict = field(default_factory=dict)

    def texto(self) -> str:
        decision = "se rechaza H₀" if self.rechaza else "no se rechaza H₀"
        return (f"{self.nombre}: estadístico = {self.estadistico:.6g} ({self.ley}), "
                f"p-valor = {self.p_valor:.6g}; con α = {self.alfa}: {decision}")


def _p_valor(d: P.Distribucion, t: float, alternativa: str) -> tuple[float, float]:
    """``(p por F cerrada, p por cuadratura)``."""
    F = d.F(t)
    Fq = P.F_por_cuadratura(d, t)
    if alternativa == "mayor":
        return 1 - F, 1 - Fq
    if alternativa == "menor":
        return F, Fq
    return 2 * min(F, 1 - F), 2 * min(Fq, 1 - Fq)


def contraste(e: dict, trace: Trace | None = None) -> Contraste:
    """``e["tipo"]`` ∈ media, proporcion, varianza, bondad, independencia;
    ``alternativa`` ∈ distinta (bilateral), mayor, menor."""
    trace = trace if trace is not None else Trace()
    alfa = P.fraccion(e.get("alfa", "0.05"), "α")
    alt = str(e.get("alternativa", "distinta")).lower()
    if alt not in ("distinta", "mayor", "menor"):
        raise _error("BAD_INPUT", "alternativa: distinta, mayor o menor")
    tipo = str(e.get("tipo", "media")).lower()
    simbolo = {"distinta": "≠", "mayor": ">", "menor": "<"}[alt]
    if tipo == "media":
        n, media, s2 = _resumen(e, trace)
        mu0 = P.fraccion(e["mu0"], "μ₀")
        if e.get("sigma") is not None:
            sigma = float(P.fraccion(e["sigma"], "σ"))
            d = P.distribucion("normal", {})
            ley = "N(0, 1)"
        else:
            if s2 is None:
                raise _error("BAD_INPUT", "falta σ o s")
            sigma = math.sqrt(float(s2))
            d = P.distribucion("t", {"nu": n - 1})
            ley = f"t con {n - 1} g.l."
        if sigma <= 0 or n < 2:
            raise _error("BAD_INPUT", "con σ (o s) = 0 o un solo dato el estadístico no está "
                                      "definido")
        t = (float(media) - float(mu0)) / (sigma / math.sqrt(n))
        nombre = f"H₀: μ = {mu0} frente a H₁: μ {simbolo} {mu0}"
        trace.metodo("contraste.media", f"T = (x̄ − μ₀)/(σ/√n) = {t:.6g} ~ {ley} bajo H₀",
                     why="σ conocida da z; estimada por s da t con n − 1 grados")
    elif tipo == "proporcion":
        n = int(P.fraccion(e["n"], "n"))
        x = int(P.fraccion(e["exitos"], "éxitos"))
        p0 = P.fraccion(e["p0"], "p₀")
        if not 0 < p0 < 1 or n < 1:
            raise _error("BAD_INPUT", "p₀ entre 0 y 1 (sin incluirlos) y n ≥ 1")
        t = (x / n - float(p0)) / math.sqrt(float(p0 * (1 - p0)) / n)
        d = P.distribucion("normal", {})
        ley = "N(0, 1) aproximada"
        nombre = f"H₀: p = {p0} frente a H₁: p {simbolo} {p0}"
        trace.metodo("contraste.proporcion", f"Z = (p̂ − p₀)/√(p₀(1 − p₀)/n) = {t:.6g}",
                     why="bajo H₀ la varianza es la de p₀, no la de p̂")
    elif tipo == "varianza":
        n, media, s2 = _resumen(e, trace)
        v0 = P.fraccion(e["sigma2_0"], "σ₀²")
        t = (n - 1) * float(s2) / float(v0)
        d = P.distribucion("chi2", {"k": n - 1})
        ley = f"χ² con {n - 1} g.l."
        nombre = f"H₀: σ² = {v0} frente a H₁: σ² {simbolo} {v0}"
        trace.metodo("contraste.varianza", f"(n − 1)s²/σ₀² = {t:.6g} ~ {ley}",
                     why="población normal: la cuasivarianza escalada es χ²")
    elif tipo in ("bondad", "independencia"):
        return _chi2_tabla(e, tipo, alfa, trace)
    else:
        raise _error("BAD_INPUT", f"contraste «{tipo}» no reconocido")
    p, pq = _p_valor(d, t, alt)
    if abs(p - pq) > 1e-7:
        raise _error("DISCREPANT", f"p-valor {p} frente a cuadratura {pq}")
    trace.verificacion("contraste.p_cuadratura", f"p-valor por la función especial {p:.10g} y "
                                                 f"por cuadratura de la densidad {pq:.10g}")
    a = float(alfa)
    if alt == "distinta":
        crit = (d.cuantil(a / 2), d.cuantil(1 - a / 2))
    elif alt == "mayor":
        crit = (d.cuantil(1 - a),)
    else:
        crit = (d.cuantil(a),)
    rechaza = p < a
    en_region = (t < crit[0] or t > crit[1]) if alt == "distinta" else \
        (t > crit[0] if alt == "mayor" else t < crit[0])
    if en_region != rechaza:
        raise _error("DISCREPANT", "la región crítica y el p-valor no coinciden")
    trace.verificacion("contraste.region", "región crítica " + ", ".join(f"{c:.6g}" for c in crit)
                       + f": el estadístico {'cae' if en_region else 'no cae'} en ella, como dice "
                         "el p-valor")
    trace.regla("contraste.decision", f"p = {p:.6g} {'<' if rechaza else '≥'} α = {alfa}: "
                                      f"{'se rechaza' if rechaza else 'no se rechaza'} H₀",
                why="el p-valor es la probabilidad, bajo H₀, de un estadístico tan extremo o más")
    return Contraste(nombre, t, ley, p, crit, rechaza, alfa, alt)


def _chi2_tabla(e, tipo, alfa, trace) -> Contraste:
    if tipo == "bondad":
        obs = [P.fraccion(v, "observada") for v in e["observadas"]]
        n = sum(obs, Fraction(0))
        if e.get("probabilidades") is not None:
            ps = [P.fraccion(v, "p") for v in e["probabilidades"]]
            if sum(ps, Fraction(0)) != 1:
                raise _error("BAD_INPUT", "las probabilidades no suman 1")
            esp = [n * p for p in ps]
        else:
            esp = [n / len(obs)] * len(obs)
        estimados = int(e.get("parametros_estimados", 0))
        gl = len(obs) - 1 - estimados
        celdas = list(zip(obs, esp))
        nombre = "bondad de ajuste χ²"
    else:
        tabla = [[P.fraccion(v, "frecuencia") for v in fila] for fila in e["tabla"]]
        filas = [sum(f, Fraction(0)) for f in tabla]
        cols = [sum((f[j] for f in tabla), Fraction(0)) for j in range(len(tabla[0]))]
        n = sum(filas, Fraction(0))
        celdas = [(tabla[i][j], filas[i] * cols[j] / n) for i in range(len(tabla))
                  for j in range(len(cols))]
        gl = (len(tabla) - 1) * (len(cols) - 1)
        nombre = "independencia χ² (tabla de contingencia)"
    if gl < 1:
        raise _error("BAD_INPUT", "sin grados de libertad")
    estad = sum(((o - E) ** 2 / E for o, E in celdas), Fraction(0))
    pocas = [float(E) for _, E in celdas if E < 5]
    trace.metodo("contraste.chi2", f"χ² = Σ(O − E)²/E = {_num(estad)} con {gl} g.l.",
                 why="la discrepancia entre observadas y esperadas bajo H₀ es aproximadamente χ²")
    trace.hipotesis("contraste.esperadas5", "todas las frecuencias esperadas ≥ 5",
                    "se cumple" if not pocas else f"NO se cumple ({len(pocas)} celdas < 5)")
    d = P.distribucion("chi2", {"k": gl})
    p, pq = _p_valor(d, float(estad), "mayor")
    if abs(p - pq) > 1e-7:
        raise _error("DISCREPANT", f"p-valor {p} frente a cuadratura {pq}")
    trace.verificacion("contraste.p_cuadratura", f"p-valor {p:.10g} (gamma incompleta) y "
                                                 f"{pq:.10g} (cuadratura)")
    crit = d.cuantil(1 - float(alfa))
    rechaza = p < float(alfa)
    if (float(estad) > crit) != rechaza:
        raise _error("DISCREPANT", "la región crítica y el p-valor no coinciden")
    return Contraste(nombre, float(estad), f"χ² con {gl} g.l.", p, (crit,), rechaza, alfa,
                     "mayor", {"esperadas": [str(E) for _, E in celdas], "exacto": str(estad)})


# ---------------------------------------------------------------------------
# regresión lineal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Regresion:
    a: Fraction
    b: Fraction
    r2: Fraction
    residuos: tuple[Fraction, ...]
    sxx: Fraction
    sxy: Fraction
    syy: Fraction

    def r(self) -> float:
        return math.copysign(math.sqrt(float(self.r2)), float(self.b))

    def texto(self) -> str:
        return (f"ŷ = {_num(self.a)} + {_num(self.b)}·x; r = {self.r():.6g}, "
                f"r² = {_num(self.r2)}")


def regresion(xs, ys, trace: Trace | None = None) -> Regresion:
    trace = trace if trace is not None else Trace()
    X, Y = _datos(xs), _datos(ys)
    if len(X) != len(Y) or len(X) < 2:
        raise _error("BAD_INPUT", "hacen falta al menos dos pares (x, y)")
    n = len(X)
    mx_, my = sum(X, Fraction(0)) / n, sum(Y, Fraction(0)) / n
    sxx = sum(((x - mx_) ** 2 for x in X), Fraction(0))
    sxy = sum(((x - mx_) * (y - my) for x, y in zip(X, Y)), Fraction(0))
    syy = sum(((y - my) ** 2 for y in Y), Fraction(0))
    if sxx == 0:
        raise _error("BAD_INPUT", "todas las x son iguales: la recta no está determinada")
    b = sxy / sxx
    a = my - b * mx_
    trace.metodo("regresion.mc", f"b = Sxy/Sxx = {_num(sxy)}/{_num(sxx)} = {_num(b)}; "
                                 f"a = ȳ − b·x̄ = {_num(a)}",
                 why="mínimos cuadrados: anular las derivadas de Σ(yᵢ − a − bxᵢ)² da las "
                     "ecuaciones normales")
    res = tuple(y - a - b * x for x, y in zip(X, Y))
    s0 = sum(res, Fraction(0))
    s1 = sum((r * x for r, x in zip(res, X)), Fraction(0))
    if s0 != 0 or s1 != 0:
        raise _error("DISCREPANT", "los residuos no son ortogonales")
    trace.verificacion("regresion.ortogonal", "Σeᵢ = 0 y Σeᵢxᵢ = 0 exactos (Xᵀe = 0)")
    r2 = sxy * sxy / (sxx * syy) if syy else Fraction(1)
    sce = sum((r * r for r in res), Fraction(0))
    if syy and sce != syy * (1 - r2):
        raise _error("DISCREPANT", "SCE ≠ Syy·(1 − r²)")
    trace.verificacion("regresion.descomposicion", f"Σeᵢ² = {_num(sce)} = Syy·(1 − r²) (exacto)")
    trace.regla("regresion.r", f"r² = Sxy²/(Sxx·Syy) = {_num(r2)}")
    return Regresion(a, b, r2, res, sxx, sxy, syy)


# ---------------------------------------------------------------------------
# estimadores: momentos y máxima verosimilitud
# ---------------------------------------------------------------------------


@dataclass
class Estimadores:
    familia: str
    momentos: dict
    mv: dict
    logL: object = None      # función θ → log L para dibujar
    rango: tuple[float, float] | None = None
    numerico: bool = False


def estimadores(familia: str, xs, trace: Trace | None = None, params: dict | None = None
                ) -> Estimadores:
    trace = trace if trace is not None else Trace()
    datos = _datos(xs)
    n = len(datos)
    m1 = sum(datos, Fraction(0)) / n
    m2 = sum((x * x for x in datos), Fraction(0)) / n
    var_n = m2 - m1 * m1
    fam = familia.lower()
    params = params or {}
    trace.regla("est.momentos_muestrales", f"m₁ = x̄ = {_num(m1)}, m₂ = {_num(m2)}, "
                                           f"m₂ − m₁² = {_num(var_n)}")
    if fam == "poisson":
        mom = {"λ": m1}
        mv = {"λ": m1}
        logL = lambda l: sum(float(x) * math.log(l) - l - math.lgamma(float(x) + 1) for x in datos)  # noqa: E731
        rango = (max(1e-6, float(m1) / 4), float(m1) * 3 + 1e-6)
        why = "E[X] = λ; la log-verosimilitud Σxᵢ·ln λ − nλ se anula en derivada en λ = x̄"
    elif fam == "exponencial":
        mom = {"λ": 1 / m1}
        mv = {"λ": 1 / m1}
        logL = lambda l: n * math.log(l) - l * float(sum(datos))  # noqa: E731
        rango = (float(1 / m1) / 4, float(1 / m1) * 3)
        why = "E[X] = 1/λ; ∂/∂λ (n ln λ − λΣxᵢ) = 0 da λ = 1/x̄"
    elif fam == "bernoulli":
        mom = {"p": m1}
        mv = {"p": m1}
        s = float(sum(datos))
        logL = lambda p: s * math.log(p) + (n - s) * math.log(1 - p)  # noqa: E731
        rango = (0.01, 0.99)
        why = "E[X] = p; la proporción muestral maximiza la verosimilitud"
    elif fam == "geometrica":
        mom = {"p": 1 / m1}
        mv = {"p": 1 / m1}
        s = float(sum(datos))
        logL = lambda p: n * math.log(p) + (s - n) * math.log(1 - p)  # noqa: E731
        rango = (0.01, 0.99)
        why = "geométrica desde 1: E[X] = 1/p; ∂/∂p (n ln p + (Σx − n) ln(1 − p)) = 0"
        trace.convencion("est.geometrica", "X = número de ensayos hasta el primer éxito (≥ 1)")
    elif fam == "binomial":
        N = int(P.fraccion(params.get("n"), "n de la binomial"))
        mom = {"p": m1 / N}
        mv = {"p": m1 / N}
        s = float(sum(datos))
        logL = lambda p: s * math.log(p) + (n * N - s) * math.log(1 - p)  # noqa: E731
        rango = (0.01, 0.99)
        why = f"E[X] = {N}·p"
    elif fam == "normal":
        mom = {"μ": m1, "σ²": var_n}
        mv = {"μ": m1, "σ²": var_n}
        logL = lambda mu: -n / 2 * math.log(2 * math.pi * float(var_n)) - sum(  # noqa: E731
            (float(x) - mu) ** 2 for x in datos) / (2 * float(var_n))
        rango = (float(m1) - 3 * math.sqrt(float(var_n)), float(m1) + 3 * math.sqrt(float(var_n)))
        why = "μ̂ = x̄ y σ̂² = (1/n)Σ(xᵢ − x̄)² (sesgado: el insesgado divide por n − 1)"
        trace.aviso("est.sesgo", "el EMV de σ² divide por n: es sesgado; s² (n − 1) es el "
                                 "insesgado")
    elif fam == "uniforme":
        mx_ = max(datos)
        mom = {"θ": 2 * m1}
        mv = {"θ": mx_}
        logL = lambda t: -n * math.log(t) if t >= float(mx_) else -math.inf  # noqa: E731
        rango = (float(mx_) / 2, float(mx_) * 2)
        why = ("U(0, θ): E[X] = θ/2 da θ̃ = 2x̄; la verosimilitud θ^(−n) decrece y solo vale "
               "si θ ≥ máx xᵢ, así que el máximo está en θ̂ = máx xᵢ (no se anula la derivada)")
    elif fam == "densidad":
        return _estimadores_densidad(params, datos, trace)
    else:
        raise _no(f"familia «{familia}» (poisson, exponencial, bernoulli, geometrica, binomial, "
                  "normal, uniforme o densidad con parámetro)")
    trace.metodo("est.formulas", "; ".join(f"momentos: {k} = {_num(v)}" for k, v in mom.items())
                 + "; " + "; ".join(f"MV: {k} = {_num(v)}" for k, v in mv.items()), why=why)
    # segundo camino: máximo numérico de log L (sección áurea) en el parámetro principal
    clave = next(iter(mv))
    objetivo = float(mv[clave])
    lo, hi = rango
    for _ in range(200):
        a, b = lo + (hi - lo) * 0.381966, lo + (hi - lo) * 0.618034
        if logL(a) < logL(b):
            lo = a
        else:
            hi = b
    hallado = (lo + hi) / 2
    if abs(hallado - objetivo) > 1e-5 * max(1, abs(objetivo)):
        raise _error("DISCREPANT", f"el máximo numérico de log L está en {hallado}, no en "
                                   f"{objetivo}")
    trace.verificacion("est.aurea", f"máximo de log L por sección áurea en {clave} ≈ "
                                    f"{hallado:.8g} (coincide con la fórmula)")
    return Estimadores(fam, mom, mv, logL, rango)


def _estimadores_densidad(params: dict, datos: list[Fraction], trace: Trace) -> Estimadores:
    """``f(x; θ)`` dada con su soporte; MV por sección áurea sobre log L y momentos
    resolviendo E_θ[X] = x̄ por bisección (los dos numéricos, declarados)."""
    from academic_core.domain.engineering.mathlab import va_continua as VC

    f = mx.parse(str(params["f"]))
    th = str(params.get("parametro", "θ"))
    var = str(params.get("var", "x"))
    a, b = VC._extremo(params.get("desde", "0")), VC._extremo(params.get("hasta", "oo"))
    lo, hi = (float(P.fraccion(v)) for v in params.get("rango", ("0.01", "20")))
    xs = [float(x) for x in datos]

    def logL(t: float) -> float:
        total = 0.0
        for x in xs:
            v = mx.valor_real(f, {var: x, th: t})
            if v is None or v <= 0:
                return -math.inf
            total += math.log(v)
        return total

    l, h = lo, hi
    for _ in range(200):
        p, q = l + (h - l) * 0.381966, l + (h - l) * 0.618034
        if logL(p) < logL(q):
            l = p
        else:
            h = q
    mv = (l + h) / 2
    media = sum(xs) / len(xs)

    def E(t: float) -> float:
        g = lambda x: x * float(mx.valor_real(f, {var: x, th: t}) or 0.0)  # noqa: E731
        return VC._num_integral(g, None if a is None else float(a), None if b is None else float(b))

    try:
        lo_e, hi_e = E(lo), E(hi)
        sube = hi_e > lo_e
        l2, h2 = lo, hi
        for _ in range(100):
            m = (l2 + h2) / 2
            if (E(m) < media) == sube:
                l2 = m
            else:
                h2 = m
        mom = (l2 + h2) / 2
    except Exception:  # noqa: BLE001
        mom = math.nan
    # comprobación: la derivada numérica de log L se anula en el MV
    dl = (logL(mv + 1e-5) - logL(mv - 1e-5)) / 2e-5
    trace.metodo("est.densidad", f"MV: {th} ≈ {mv:.8g} (máximo de log L); momentos: E_{th}[X] "
                                 f"= x̄ = {media:.6g} da {th} ≈ {mom:.8g}",
                 why="sin forma cerrada general: se maximiza Σ ln f(xᵢ; θ) y se resuelve la "
                     "ecuación de momentos numéricamente")
    trace.verificacion("est.score", f"∂ log L/∂{th} ≈ {dl:.3g} en el máximo")
    return Estimadores("densidad", {th: mom}, {th: mv}, logL, (lo, hi), numerico=True)
