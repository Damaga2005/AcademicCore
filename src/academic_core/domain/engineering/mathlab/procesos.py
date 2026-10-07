# SPDX-License-Identifier: MIT
"""ML-9 (§4.6, tipos 3, 12, 13 y 14 de §15.1; comunicaciones de D12).

- **Aproximación normal** (De Moivre–Laplace, TCL) con corrección de continuidad,
  siempre al lado del valor exacto y con la diferencia.
- **Proceso de Poisson**: recuentos, incrementos independientes, condicionada
  binomial, tiempos de llegada (Erlang), autocovarianza ``λ·mín(t₁, t₂)``.
- **Paseo de Bernoulli o ±1**: media, varianza y autocorrelación exactas; segundo
  camino por **enumeración de los 2ⁿ caminos** (n pequeño).
- **Procesos construidos con variables aleatorias** (``A·cos(ωt + Θ)``…): media y
  autocorrelación **exactas** integrando sobre cada variable con el motor de
  ML-2; estacionariedad decidida comprobando que la media no depende de t y que
  ``R(t + τ, t)`` no depende de t; segundo camino por simulación sembrada.
- **Comunicaciones (G, D12)**: BER con ``Q``, ALOHA, Rayleigh y Rice, ARQ, cada
  fórmula con sus hipótesis declaradas y un contraste por simulación sembrada o
  por cuadratura.
"""

from __future__ import annotations

import itertools
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


# ---------------------------------------------------------------------------
# aproximación normal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Aproximacion:
    exacta: float
    exacta_txt: str
    aproximada: float
    sin_correccion: float
    z: tuple[float, ...]
    condicion: str

    def texto(self) -> str:
        return (f"exacta {self.exacta:.6g}" + (f" (= {self.exacta_txt})" if self.exacta_txt else "")
                + f"; normal con corrección de continuidad {self.aproximada:.6g} "
                f"(error {abs(self.aproximada - self.exacta):.2g}); sin corrección "
                f"{self.sin_correccion:.6g}")


def aproximacion_normal(dist: str, params: dict, suceso: str,
                        trace: Trace | None = None) -> Aproximacion:
    """Binomial o Poisson (o cualquier discreta con media y varianza) por la normal."""
    trace = trace if trace is not None else Trace()
    d = P.distribucion(dist, params, trace)
    if not d.discreta:
        raise _error("BAD_INPUT", "la corrección de continuidad es para leyes discretas")
    A, B = P.lee_suceso(suceso)
    if B is not None:
        raise _error("BAD_INPUT", "una condicionada no se aproxima directamente")
    exacta, exacto = P.probabilidad_intervalo(d, A)
    mu, var = float(d.media_f()), float(d.varianza_f())
    if var == 0:
        raise _error("BAD_INPUT", "la varianza es 0 (p = 0 o p = 1): la ley es degenerada y no "
                                  "hay nada que aproximar")
    s = math.sqrt(var)
    trace.metodo("aprox.normal", f"X ≈ N(μ = {mu:.6g}, σ² = {var:.6g})",
                 why="De Moivre–Laplace / TCL: una suma de muchas variables independientes es "
                     "aproximadamente normal con su media y su varianza")
    if d.nombre == "binomial":
        n, p = d.parametros["n"], d.parametros["p"]
        cond = f"n·p = {float(n * p):.4g} y n·(1 − p) = {float(n * (1 - p)):.4g} (≥ 5)"
        ok = n * p >= 5 and n * (1 - p) >= 5
    else:
        cond = f"μ = {mu:.4g} (≥ 10 para Poisson)" if "λ" in str(d.parametros) else f"μ = {mu:.4g}"
        ok = mu >= 10
    trace.hipotesis("aprox.condicion", cond, "se cumple" if ok else "NO se cumple: la "
                    "aproximación será pobre")
    # enteros incluidos y corrección ±1/2
    lo = None if A.lo is None else (math.ceil(A.lo) if A.lo_cerrado else math.floor(A.lo) + 1)
    hi = None if A.hi is None else (math.floor(A.hi) if A.hi_cerrado else math.ceil(A.hi) - 1)
    za = None if lo is None else (lo - 0.5 - mu) / s
    zb = None if hi is None else (hi + 0.5 - mu) / s
    aprox = (1.0 if zb is None else P.Phi(zb)) - (0.0 if za is None else P.Phi(za))
    za0 = None if lo is None else (lo - mu) / s
    zb0 = None if hi is None else (hi - mu) / s
    sin = (1.0 if zb0 is None else P.Phi(zb0)) - (0.0 if za0 is None else P.Phi(za0))
    rango = f"{'−∞' if lo is None else lo} ≤ X ≤ {'+∞' if hi is None else hi}"
    trace.regla("aprox.correccion", f"{rango} → P({'' if lo is None else f'{lo} − 0,5 < '}Y"
                                    f"{'' if hi is None else f' < {hi} + 0,5'})",
                why="cada entero k de la discreta se reparte el intervalo [k − ½, k + ½] de la "
                    "continua")
    trace.verificacion("aprox.exacta", f"valor exacto {exacta:.10g}: la aproximación se equivoca "
                                       f"en {abs(aprox - exacta):.3g}")
    return Aproximacion(exacta, P.texto_exacto(exacto), aprox, sin,
                        tuple(z for z in (za, zb) if z is not None), cond)


def tcl_suma(n: int, media, varianza, suceso: str, trace: Trace | None = None) -> dict:
    """``S = X₁ + … + Xₙ`` iid: ``P(S ∈ I) ≈ Φ(…)`` con ``E = nμ`` y ``Var = nσ²``."""
    trace = trace if trace is not None else Trace()
    mu = float(P.fraccion(media, "μ"))
    var = float(P.fraccion(varianza, "σ²"))
    A, _ = P.lee_suceso(suceso)
    m, s = n * mu, math.sqrt(n * var)
    trace.metodo("tcl", f"S ≈ N({m:.6g}, {n * var:.6g})", why="teorema central del límite: la "
                 "suma de n iid de varianza finita, estandarizada, tiende a N(0, 1)")
    a = -math.inf if A.lo is None else float(A.lo)
    b = math.inf if A.hi is None else float(A.hi)
    p = (1.0 if b == math.inf else P.Phi((b - m) / s)) - (0.0 if a == -math.inf else P.Phi((a - m) / s))
    return {"media": m, "varianza": n * var, "p": p}


# ---------------------------------------------------------------------------
# proceso de Poisson
# ---------------------------------------------------------------------------


def poisson_proceso(e: dict, trace: Trace | None = None, semilla: int = 20261007) -> dict:
    """``{"lambda": 2, "consulta": "conteo", "t": 3, "k": 4}``; consultas: conteo,
    dos_tiempos (N(t1) = a y N(t2) = b), condicionada (N(s) = a | N(t) = b),
    llegada (T_k ≤ t), autocovarianza."""
    trace = trace if trace is not None else Trace()
    lam = P._positivo(e.get("lambda", e.get("λ")), "λ")
    lf = float(lam)
    consulta = str(e.get("consulta", "conteo"))
    for clave in ("k", "a", "b"):
        if e.get(clave) is not None:
            v = P.fraccion(e[clave], clave)
            if v < 0 or v.denominator != 1:
                raise _error("BAD_INPUT", f"{clave} es un número de llegadas: entero ≥ 0")
            if v > P.EXACTO_MAX:
                raise _error("BAD_INPUT", f"{clave} = {v} demasiado grande para el cálculo exacto")
    tiempos = [float(P.fraccion(e[c], c)) for c in ("t", "t1", "t2", "s") if e.get(c) is not None]
    if not tiempos:
        raise _error("BAD_INPUT", "falta el tiempo t")
    horizonte = max(tiempos)
    if min(tiempos) <= 0:
        raise _error("BAD_INPUT", "los tiempos tienen que ser positivos")
    if lf * horizonte > 1e6:
        raise _error("BAD_INPUT", f"λ·t = {lf * horizonte:g}: demasiadas llegadas (máximo 10⁶)")
    trace.hipotesis("poisson.proceso", "llegadas independientes a tasa λ constante: incrementos "
                                       "independientes y estacionarios, N(t) ~ Poisson(λt)",
                    "se asume")
    if consulta == "conteo":
        t = P.fraccion(e["t"], "t")
        k = int(P.fraccion(e["k"], "k"))
        exacto = P._expr_exp((lam * t) ** k / math.factorial(k), -lam * t)
        trace.regla("poisson.conteo", f"P(N({t}) = {k}) = e^(−λt)(λt)^k/k! = "
                                      f"{P.texto_exacto(exacto)}")
        valor = float(mx.valor_real(exacto, {}))

        def exp_(g):
            tt, c = g.exponencial(lf), 0
            while tt <= float(t):
                c += 1
                tt += g.exponencial(lf)
            return 1.0 if c == k else 0.0
    elif consulta == "dos_tiempos":
        t1, t2 = P.fraccion(e["t1"], "t1"), P.fraccion(e["t2"], "t2")
        a, b = int(e["a"]), int(e["b"])
        if not (t1 < t2 and a <= b):
            raise _error("BAD_INPUT", "t1 < t2 y a ≤ b")
        c1 = (lam * t1) ** a / math.factorial(a)
        c2 = (lam * (t2 - t1)) ** (b - a) / math.factorial(b - a)
        exacto = P._expr_exp(c1 * c2, -lam * t2)
        trace.metodo("poisson.incrementos", f"P(N({t1}) = {a}, N({t2}) = {b}) = P(N({t1}) = {a})·"
                                            f"P(N({t2}) − N({t1}) = {b - a}) = "
                                            f"{P.texto_exacto(exacto)}",
                     why="los incrementos en intervalos disjuntos son independientes y "
                         "N(t2) − N(t1) ~ Poisson(λ(t2 − t1))")
        valor = float(mx.valor_real(exacto, {}))

        def exp_(g):
            tt, c1_, c2_ = g.exponencial(lf), 0, 0
            while tt <= float(t2):
                if tt <= float(t1):
                    c1_ += 1
                c2_ += 1
                tt += g.exponencial(lf)
            return 1.0 if (c1_, c2_) == (a, b) else 0.0
    elif consulta == "condicionada":
        s, t = P.fraccion(e["s"], "s"), P.fraccion(e["t"], "t")
        a, b = int(e["a"]), int(e["b"])
        q = s / t
        exacto = Fraction(math.comb(b, a)) * q ** a * (1 - q) ** (b - a)
        trace.metodo("poisson.condicionada", f"P(N({s}) = {a} | N({t}) = {b}) = C({b},{a})·"
                                             f"({q})^{a}·(1 − {q})^{b - a} = {exacto}",
                     why="dadas b llegadas en [0, t], sus instantes son uniformes e "
                         "independientes: cada una cae en [0, s] con probabilidad s/t")
        valor = float(exacto)
        # segundo camino exacto: por la definición con incrementos
        num = P._expr_exp((lam * s) ** a / math.factorial(a) * (lam * (t - s)) ** (b - a)
                          / math.factorial(b - a), -lam * t)
        den = P._expr_exp((lam * t) ** b / math.factorial(b), -lam * t)
        cociente = float(mx.valor_real(num, {})) / float(mx.valor_real(den, {}))
        if abs(cociente - valor) > 1e-12:
            raise _error("DISCREPANT", "la condicionada por definición no coincide")
        trace.verificacion("poisson.definicion", "P(N(s) = a, N(t) − N(s) = b − a)/P(N(t) = b) "
                                                 "da lo mismo (λ se cancela)")

        def exp_(g):
            while True:
                tt, c1_, c2_ = g.exponencial(lf), 0, 0
                while tt <= float(t):
                    if tt <= float(s):
                        c1_ += 1
                    c2_ += 1
                    tt += g.exponencial(lf)
                if c2_ == b:
                    return 1.0 if c1_ == a else 0.0
    elif consulta == "llegada":
        k = int(P.fraccion(e["k"], "k"))
        t = P.fraccion(e["t"], "t")
        d = P.distribucion("gamma", {"k": k, "lambda": lam})
        exacto = d.F_exacta(t)
        trace.metodo("poisson.llegada", f"T_{k} ~ Erlang({k}, λ): P(T_{k} ≤ {t}) = P(N({t}) ≥ {k}) "
                                        f"= {P.texto_exacto(exacto)}",
                     why="la k-ésima llegada ocurre antes de t si y solo si hay al menos k "
                         "llegadas en [0, t]")
        valor = float(mx.valor_real(exacto, {}))

        def exp_(g):
            return 1.0 if sum(g.exponencial(lf) for _ in range(k)) <= float(t) else 0.0
    elif consulta == "autocovarianza":
        t1, t2 = P.fraccion(e["t1"], "t1"), P.fraccion(e["t2"], "t2")
        c = lam * min(t1, t2)
        R = c + lam * lam * t1 * t2
        trace.regla("poisson.autocov", f"C(t1, t2) = λ·mín(t1, t2) = {c}; R = C + λ²t1t2 = {R}",
                    why="Cov(N(t1), N(t2)) = Var N(mín) por incrementos independientes")
        trace.aviso("poisson.no_estacionario", "N(t) no es estacionario: su media λt crece")
        valor = float(c)
        exacto = c

        def exp_(g):
            tt, n1, n2 = g.exponencial(lf), 0, 0
            while tt <= float(max(t1, t2)):
                if tt <= float(t1):
                    n1 += 1
                if tt <= float(t2):
                    n2 += 1
                tt += g.exponencial(lf)
            return (n1 - lf * float(t1)) * (n2 - lf * float(t2))
    else:
        raise _error("BAD_INPUT", f"consulta «{consulta}» no reconocida")
    muestras = int(min(20000, 4e6 / (lf * horizonte + 1)))
    if muestras < 1000:
        trace.aviso("poisson.sin_simulacion", f"λ·t = {lf * horizonte:g}: la simulación sería "
                                              "demasiado larga; solo la fórmula exacta")
        return {"valor": valor, "exacto": P.texto_exacto(exacto), "simulacion": None}
    sim = P.simula(exp_, muestras, semilla)
    if not sim.dentro(valor, 5):
        raise _error("DISCREPANT", f"la simulación da {sim.texto()} y la fórmula {valor}")
    trace.verificacion("poisson.simulacion", f"simulación sembrada de las llegadas: {sim.texto()}")
    return {"valor": valor, "exacto": P.texto_exacto(exacto), "simulacion": sim}


# ---------------------------------------------------------------------------
# paseo ±1 y proceso de Bernoulli
# ---------------------------------------------------------------------------


def paseo(e: dict, trace: Trace | None = None) -> dict:
    """``{"tipo": "pm1"|"bernoulli", "p": "1/2", "n": 6, "m": 4, "k": 2}``:
    X_n = Σ Zᵢ con Zᵢ = +1 (p) / −1 (1 − p), o S_n = número de éxitos."""
    trace = trace if trace is not None else Trace()
    tipo = str(e.get("tipo", "pm1"))
    p = P._prob(e.get("p", "1/2"))
    n = int(P.fraccion(e["n"], "n"))
    m = int(P.fraccion(e.get("m", n), "m"))
    if tipo == "pm1":
        mu1, v1 = 2 * p - 1, 4 * p * (1 - p)
        trace.convencion("paseo.pm1", "Zᵢ = +1 con probabilidad p, −1 con 1 − p; X_n = Z₁ + … + Z_n")
    else:
        mu1, v1 = p, p * (1 - p)
        trace.convencion("paseo.bernoulli", "Zᵢ ∈ {0, 1}; S_n = Z₁ + … + Z_n ~ Binomial(n, p)")
    media_n = n * mu1
    var_n = n * v1
    cov = min(n, m) * v1
    R = cov + n * m * mu1 * mu1
    trace.regla("paseo.momentos", f"E[X_n] = n·E[Z] = {media_n}; Var X_n = n·Var Z = {var_n}; "
                                  f"C(n, m) = mín(n, m)·Var Z = {cov}; R(n, m) = C + nm·E[Z]² = {R}",
                why="las Zᵢ son independientes: las comunes a X_n y X_m aportan la covarianza")
    if mu1 != 0:
        trace.aviso("paseo.no_estacionario", "la media depende de n: no es estacionario")
    else:
        trace.aviso("paseo.no_estacionario", "media constante 0, pero la varianza crece con n: "
                                             "no es estacionario")
    resultado: dict = {"media": media_n, "varianza": var_n, "cov": cov, "R": R}
    if e.get("k") is not None:
        k = int(P.fraccion(e["k"], "k"))
        if tipo == "pm1":
            if (n + k) % 2:
                pk = Fraction(0)
                trace.regla("paseo.paridad", f"X_{n} = {k} es imposible: X_n tiene la paridad de n")
            else:
                j = (n + k) // 2
                pk = Fraction(math.comb(n, j)) * p ** j * (1 - p) ** (n - j) if 0 <= j <= n \
                    else Fraction(0)
                trace.regla("paseo.prob", f"X_{n} = {k} ⇔ {j} subidas y {n - j} bajadas: "
                                          f"C({n},{j})·p^{j}·(1−p)^{n - j} = {pk}")
        else:
            pk = Fraction(math.comb(n, k)) * p ** k * (1 - p) ** (n - k) if 0 <= k <= n else Fraction(0)
        resultado["P"] = pk
    # segundo camino: enumeración de los caminos (n, m ≤ 16)
    N = max(n, m)
    if N <= 16:
        valores = (1, -1) if tipo == "pm1" else (1, 0)
        sE = sE2 = sR = sP = Fraction(0)
        for camino in itertools.product((0, 1), repeat=N):
            peso = Fraction(1)
            zs = []
            for c in camino:
                peso *= p if c == 0 else 1 - p
                zs.append(valores[c])
            xn, xm = sum(zs[:n]), sum(zs[:m])
            sE += peso * xn
            sE2 += peso * xn * xn
            sR += peso * xn * xm
            if "P" in resultado and xn == int(P.fraccion(e["k"])):
                sP += peso
        if sE != media_n or sE2 - sE * sE != var_n or sR != R or ("P" in resultado and sP != resultado["P"]):
            raise _error("DISCREPANT", "la enumeración de caminos no coincide")
        trace.verificacion("paseo.enumeracion", f"enumeración exacta de los 2^{N} = {2 ** N} "
                                                "caminos: media, varianza, R y probabilidad "
                                                "coinciden")
    else:
        trace.aviso("paseo.sin_enumeracion", "n > 16: sin enumeración (solo las fórmulas)")
    return resultado


# ---------------------------------------------------------------------------
# procesos construidos con variables aleatorias
# ---------------------------------------------------------------------------


@dataclass
class VA:
    nombre: str
    tipo: str                 # "uniforme", "discreta", "normal", "densidad"
    datos: dict = field(default_factory=dict)

    def muestra(self, g) -> float:
        if self.tipo == "uniforme":
            a, b = float(self.datos["a"]), float(self.datos["b"])
            return a + (b - a) * g.uniforme()
        if self.tipo == "discreta":
            i = g.eleccion([float(q) for q in self.datos["p"]])
            return float(self.datos["valores"][i])
        if self.tipo == "normal":
            return float(self.datos["mu"]) + math.sqrt(float(self.datos["var"])) * P.normal_std(g)
        raise _no("muestreo de esta variable")


def lee_va(nombre: str, spec) -> VA:
    if isinstance(spec, dict):
        tipo = str(spec.get("tipo", "uniforme")).lower()
        if tipo == "uniforme":
            return VA(nombre, "uniforme", {"a": mx.parse(str(spec["a"])), "b": mx.parse(str(spec["b"]))})
        if tipo == "discreta":
            vals = [mx.parse(str(v)) for v in spec["valores"]]
            ps = [P.fraccion(q, "p") for q in spec["p"]]
            if sum(ps, Fraction(0)) != 1:
                raise _error("BAD_INPUT", f"las probabilidades de {nombre} no suman 1")
            return VA(nombre, "discreta", {"valores": vals, "p": ps})
        if tipo == "normal":
            return VA(nombre, "normal", {"mu": P.fraccion(spec.get("mu", 0), "μ"),
                                         "var": P.fraccion(spec.get("var", spec.get("sigma2", 1)), "σ²")})
    raise _error("BAD_INPUT", f"variable «{nombre}»: tipo uniforme, discreta o normal")


def _momento_normal(mu: Fraction, var: Fraction, k: int) -> Fraction:
    m = [Fraction(1), mu]
    for j in range(2, k + 1):
        m.append(mu * m[j - 1] + (j - 1) * var * m[j - 2])
    return m[k]


def esperanza(g: mx.Expr, v: VA, trace: Trace) -> mx.Expr:
    """``E_v[g]`` exacto (las demás letras quedan como parámetros)."""
    from academic_core.domain.engineering.mathlab import poly as PO
    from academic_core.domain.engineering.mathlab import va_continua as VC

    if not mx.depends(g, v.nombre):
        return g
    if v.tipo == "discreta":
        total: mx.Expr = mx.ZERO
        for val, q in zip(v.datos["valores"], v.datos["p"]):
            total = mx.Add(total, mx.Mul(mx.num(q), mx.substitute(g, v.nombre, val)))
        return VC.simplifica(total)
    if v.tipo == "uniforme":
        a, b = v.datos["a"], v.datos["b"]
        integral = VC.integra(_expande_trig(g), v.nombre, a, b)
        return VC.simplifica(mx.Div(integral, mx.Sub(b, a)))
    if v.tipo == "normal":
        try:
            pol = PO.as_poly(g)
        except Exception:  # noqa: BLE001
            raise _no(f"E sobre la normal {v.nombre} solo para polinomios en {v.nombre}") from None
        grado = PO.degree_in(pol, v.nombre)
        total = mx.ZERO
        for k in range(grado, -1, -1):
            # coeficiente de v^k: derivar k veces y evaluar en 0, dividido por k!
            from academic_core.domain.engineering.mathlab import derive_mv as D

            c = g
            for _ in range(k):
                c = D.differentiate(c, v.nombre)
            c = mx.substitute(c, v.nombre, mx.ZERO)
            total = mx.Add(total, mx.Mul(mx.num(_momento_normal(v.datos["mu"], v.datos["var"], k)
                                                / math.factorial(k)), c))
        return VC.simplifica(total)
    raise _no(f"tipo de variable «{v.tipo}»")


def _expande_trig(g: mx.Expr) -> mx.Expr:
    """``cos(a)·cos(b)`` → ``½[cos(a − b) + cos(a + b)]`` (y seno con seno, seno con
    coseno), que el integrador de ML-2 sí sabe hacer."""
    if isinstance(g, (mx.Add, mx.Sub)):
        return type(g)(_expande_trig(g.left), _expande_trig(g.right))
    if isinstance(g, mx.Neg):
        return mx.Neg(_expande_trig(g.arg))
    if isinstance(g, mx.Div):
        return mx.Div(_expande_trig(g.left), g.right)
    if not isinstance(g, (mx.Mul, mx.Pow)):
        return g
    factores: list[mx.Expr] = []

    def plano(x):
        if isinstance(x, mx.Mul):
            plano(x.left)
            plano(x.right)
        elif isinstance(x, mx.Pow) and mx.exact_value(x.exponent) is not None and \
                Fraction(mx.exact_value(x.exponent)).denominator == 1 and \
                2 <= mx.exact_value(x.exponent) <= 6 and isinstance(x.base, mx.Call) and \
                x.base.name in ("cos", "sin", "sen"):
            for _ in range(int(mx.exact_value(x.exponent))):
                factores.append(x.base)
        else:
            factores.append(x)
    plano(g)
    trig = [f for f in factores if isinstance(f, mx.Call) and f.name in ("cos", "sin", "sen")]
    if len(trig) < 2:
        return g
    resto = [f for f in factores if f not in trig or factores.count(f) and False]
    resto = []
    usados = 0
    for f in factores:
        if isinstance(f, mx.Call) and f.name in ("cos", "sin", "sen") and usados < 2:
            usados += 1
            continue
        resto.append(f)
    u, w = trig[0], trig[1]
    a, b = u.args[0], w.args[0]
    nu, nw = ("sin" if u.name == "sen" else u.name), ("sin" if w.name == "sen" else w.name)
    medio = mx.num(Fraction(1, 2))
    if nu == "cos" and nw == "cos":
        prod = mx.Mul(medio, mx.Add(mx.Call("cos", (mx.Sub(a, b),)), mx.Call("cos", (mx.Add(a, b),))))
    elif nu == "sin" and nw == "sin":
        prod = mx.Mul(medio, mx.Sub(mx.Call("cos", (mx.Sub(a, b),)), mx.Call("cos", (mx.Add(a, b),))))
    else:
        s_, c_ = (a, b) if nu == "sin" else (b, a)
        prod = mx.Mul(medio, mx.Add(mx.Call("sin", (mx.Add(s_, c_),)), mx.Call("sin", (mx.Sub(s_, c_),))))
    r: mx.Expr = prod
    for f in resto:
        r = mx.Mul(f, r)
    return _expande_trig(_distribuye(r))


def _distribuye(e: mx.Expr) -> mx.Expr:
    if isinstance(e, mx.Mul):
        l, r = _distribuye(e.left), _distribuye(e.right)
        if isinstance(r, (mx.Add, mx.Sub)):
            return type(r)(_distribuye(mx.Mul(l, r.left)), _distribuye(mx.Mul(l, r.right)))
        if isinstance(l, (mx.Add, mx.Sub)):
            return type(l)(_distribuye(mx.Mul(l.left, r)), _distribuye(mx.Mul(l.right, r)))
        return mx.Mul(l, r)
    if isinstance(e, (mx.Add, mx.Sub)):
        return type(e)(_distribuye(e.left), _distribuye(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_distribuye(e.arg))
    return e


@dataclass
class ProcesoVA:
    expr: mx.Expr
    media: mx.Expr
    R: mx.Expr                       # R(t1, t2)
    R_tau: mx.Expr | None            # R(τ) si es estacionario en sentido amplio
    estacionario: bool
    motivo: str
    potencia: mx.Expr | None = None


def proceso_va(expr: str, variables: dict, t: str = "t", trace: Trace | None = None,
               semilla: int = 20261007) -> ProcesoVA:
    """``X(t) = expr`` con las variables aleatorias de ``variables`` (independientes)."""
    from academic_core.domain.engineering.mathlab import va_continua as VC

    trace = trace if trace is not None else Trace()
    X = mx.parse(expr)
    vas = [lee_va(n, s) for n, s in variables.items()]
    trace.hipotesis("proceso.independencia", "las variables " + ", ".join(v.nombre for v in vas)
                    + " son independientes entre sí", "se asume")
    libres = mx.variables(X) - {t} - {v.nombre for v in vas}
    media = X
    for v in vas:
        media = esperanza(media, v, trace)
    media = VC.simplifica(media)
    trace.regla("proceso.media", f"E[X({t})] = {mx.text(media)}",
                why="se integra la expresión respecto a cada variable aleatoria con su ley")
    X1 = mx.substitute(X, t, mx.Sym("t1"))
    X2 = mx.substitute(X, t, mx.Sym("t2"))
    R = mx.Mul(X1, X2)
    for v in vas:
        R = esperanza(R, v, trace)
    R = VC.simplifica(_expande_trig(_distribuye(VC.simplifica(R))))
    trace.regla("proceso.autocorrelacion", f"R(t1, t2) = E[X(t1)·X(t2)] = {mx.text(R)}",
                why="producto de dos instantes y esperanza respecto a las variables")
    # decidir: media constante y R(t + τ, t) sin t, comprobado numéricamente
    pruebas_p = {n: 0.7 + 0.31 * i for i, n in enumerate(sorted(libres))}
    medias = [mx.valor_real(media, {**pruebas_p, t: tv}) for tv in (0.0, 0.37, 1.9, 4.2)]
    media_cte = all(m is not None and abs(m - medias[0]) < 1e-9 for m in medias)
    Rv = {}
    for tau in (0.0, 0.53):
        Rv[tau] = [mx.valor_real(R, {**pruebas_p, "t1": tv + tau, "t2": tv})
                   for tv in (0.0, 0.41, 1.3, 3.7)]
    R_dep = all(all(x is not None and abs(x - vs[0]) < 1e-9 for x in vs) for vs in Rv.values())
    est = media_cte and R_dep
    if est:
        R_tau = VC.simplifica(mx.substitute(mx.substitute(R, "t1", mx.Sym("τ")), "t2", mx.ZERO))
        motivo = "la media no depende de t y R(t + τ, t) solo depende de τ"
        potencia = VC.simplifica(mx.substitute(R_tau, "τ", mx.ZERO))
        trace.regla("proceso.estacionario", f"estacionario en sentido amplio: R(τ) = "
                                            f"{mx.text(R_tau)}; potencia R(0) = {mx.text(potencia)}")
    else:
        R_tau = None
        potencia = None
        motivo = ("la media depende de t" if not media_cte else
                  "R(t + τ, t) depende de t, no solo de τ")
        trace.regla("proceso.no_estacionario", f"no es estacionario en sentido amplio: {motivo}")
    # segundo camino: simulación sembrada de E[X(t)] y E[X(t1)X(t2)]
    t1v, t2v = 0.8, 0.3
    if not any(v.tipo not in ("uniforme", "discreta", "normal") for v in vas):
        def valores(g):
            env = dict(pruebas_p)
            for v in vas:
                d = dict(v.datos)
                if v.tipo == "uniforme":
                    a = float(mx.valor_real(d["a"], env))
                    b = float(mx.valor_real(d["b"], env))
                    env[v.nombre] = a + (b - a) * g.uniforme()
                elif v.tipo == "discreta":
                    i = g.eleccion([float(q) for q in d["p"]])
                    env[v.nombre] = float(mx.valor_real(d["valores"][i], env))
                else:
                    env[v.nombre] = v.muestra(g)
            return env

        def prod(g):
            env = valores(g)
            return float(mx.valor_real(X, {**env, t: t1v})) * float(mx.valor_real(X, {**env, t: t2v}))
        sim = P.simula(prod, 20000, semilla)
        objetivo = float(mx.valor_real(R, {**pruebas_p, "t1": t1v, "t2": t2v}))
        if not sim.dentro(objetivo, 5):
            raise _error("DISCREPANT", f"R({t1v}, {t2v}) = {objetivo} y la simulación "
                                       f"{sim.texto()}")
        trace.verificacion("proceso.simulacion", f"R({t1v}, {t2v}) = {objetivo:.6g}; simulación "
                                                 f"sembrada {sim.texto()}"
                           + (f" (con {', '.join(f'{k} = {v:.4g}' for k, v in pruebas_p.items())})"
                              if pruebas_p else ""))
    return ProcesoVA(X, media, R, R_tau, est, motivo, potencia)


# ---------------------------------------------------------------------------
# comunicaciones (G, D12)
# ---------------------------------------------------------------------------


def db_a_lineal(db: float) -> float:
    return 10 ** (db / 10)


BER_MODULACIONES = {
    "bpsk": ("Q(√(2Eb/N0))", lambda g: P.Q(math.sqrt(2 * g)), "coherente, AWGN"),
    "qpsk": ("Q(√(2Eb/N0)) (por bit, Gray)", lambda g: P.Q(math.sqrt(2 * g)), "coherente, Gray, AWGN"),
    "bfsk": ("Q(√(Eb/N0))", lambda g: P.Q(math.sqrt(g)), "coherente, tonos ortogonales"),
    "ook": ("Q(√(Eb/N0))", lambda g: P.Q(math.sqrt(g)), "coherente, Eb media"),
    "dpsk": ("½·e^(−Eb/N0)", lambda g: 0.5 * math.exp(-g), "detección diferencial"),
    "bfsk_nc": ("½·e^(−Eb/(2N0))", lambda g: 0.5 * math.exp(-g / 2), "FSK no coherente"),
    "bpsk_rayleigh": ("½·(1 − √(γ̄/(1 + γ̄)))", lambda g: 0.5 * (1 - math.sqrt(g / (1 + g))),
                      "BPSK coherente con desvanecimiento Rayleigh lento, γ̄ = Eb/N0 medio"),
}


def ber(modulacion: str, ebn0_db: float | None = None, objetivo: float | None = None,
        trace: Trace | None = None, semilla: int = 20261007) -> dict:
    trace = trace if trace is not None else Trace()
    m = modulacion.lower()
    if m not in BER_MODULACIONES:
        raise _error("BAD_INPUT", f"modulación «{modulacion}» ({', '.join(BER_MODULACIONES)})")
    formula, f, hip = BER_MODULACIONES[m]
    trace.hipotesis("ber.modelo", hip, "se asume")
    trace.convencion("ber.db", "Eb/N0 en dB: γ = 10^(dB/10) (cociente de POTENCIAS)")
    if objetivo is None and ebn0_db is None:
        raise _error("BAD_INPUT", "falta Eb/N0 (EbN0_dB) o la BER objetivo")
    if objetivo is not None and not 0 < objetivo < 0.5:
        raise _error("BAD_INPUT", "la BER objetivo tiene que estar entre 0 y 0,5")
    if objetivo is not None:
        lo, hi = -10.0, 60.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(db_a_lineal(mid)) > objetivo:
                lo = mid
            else:
                hi = mid
        ebn0_db = (lo + hi) / 2
        trace.metodo("ber.inversa", f"P_b = {objetivo:g} se alcanza con Eb/N0 = {ebn0_db:.4f} dB",
                     why="P_b decrece con Eb/N0: bisección sobre la fórmula")
    g = db_a_lineal(float(ebn0_db))
    pb = f(g)
    trace.regla("ber.formula", f"P_b = {formula} con Eb/N0 = {ebn0_db:.4g} dB = {g:.6g} → "
                               f"P_b = {pb:.6g}")
    res = {"P_b": pb, "EbN0_dB": ebn0_db, "gamma": g, "formula": formula}
    # segundo camino
    if m in ("bpsk", "qpsk") and pb > 1e-4:
        a = math.sqrt(2 * g)
        sim = P.simula(lambda gen: 1.0 if a + math.sqrt(2) * 0 + P.normal_std(gen) < 0 else 0.0,
                       200000 if pb > 1e-3 else 400000, semilla)
        if not sim.dentro(pb, 5):
            raise _error("DISCREPANT", f"simulación BPSK {sim.texto()} frente a {pb}")
        trace.verificacion("ber.simulacion", f"BPSK en AWGN simulado (símbolo ±√(2γ), ruido "
                                             f"N(0, 1)): {sim.texto()}")
    elif "Q(" in formula:
        x = math.sqrt(2 * g) if "2Eb" in formula else math.sqrt(g)
        cola = P.integral_a_infinito(P.phi, x)
        if abs(cola - pb) > 1e-9 * max(1.0, pb) + 1e-15:
            raise _error("DISCREPANT", "Q por cuadratura no coincide")
        trace.verificacion("ber.cuadratura", f"Q({x:.6g}) por cuadratura de la gaussiana: {cola:.6g}")
    elif m == "bpsk_rayleigh":
        num = P.integral_a_infinito(lambda s: P.Q(math.sqrt(2 * s)) * math.exp(-s / g) / g, 0.0)
        if abs(num - pb) > 1e-8:
            raise _error("DISCREPANT", "promedio sobre el desvanecimiento no coincide")
        trace.verificacion("ber.promedio", f"∫ Q(√(2γ))·e^(−γ/γ̄)/γ̄ dγ = {num:.6g} (cuadratura)")
    else:
        trace.verificacion("ber.monotonia", "fórmula cerrada; P_b ≤ ½ y decreciente en Eb/N0")
    return res


def aloha(G: float, ranurado: bool, trace: Trace | None = None, semilla: int = 20261007) -> dict:
    trace = trace if trace is not None else Trace()
    if G < 0:
        raise _error("BAD_INPUT", "G ≥ 0")
    if ranurado:
        S, Smax, Gopt, formula = G * math.exp(-G), 1 / math.e, 1.0, "S = G·e^(−G)"
        why = "una transmisión en una ranura tiene éxito si nadie más transmite en ella: " \
              "P(0 llegadas en 1 ranura) = e^(−G)"
    else:
        S, Smax, Gopt, formula = G * math.exp(-2 * G), 1 / (2 * math.e), 0.5, "S = G·e^(−2G)"
        why = "periodo vulnerable de dos tramas: P(0 llegadas en 2T) = e^(−2G)"
    trace.hipotesis("aloha.modelo", "llegadas (nuevas y retransmisiones) de Poisson con G tramas "
                                    "por tiempo de trama", "se asume")
    trace.metodo("aloha.formula", f"{formula} = {S:.6g}", why=why)
    trace.regla("aloha.maximo", f"máximo S = {'1/e' if ranurado else '1/(2e)'} ≈ {Smax:.6g} en "
                                f"G = {Gopt:g} (dS/dG = 0)")
    # segundo camino: simulación sembrada de ranuras / tramas
    def experimento(g):
        if ranurado:
            k = 0
            t = g.exponencial(G) if G > 0 else 2.0
            while t <= 1.0:
                k += 1
                t += g.exponencial(G)
            return 1.0 if k == 1 else 0.0
        # una trama de referencia en t = 0: éxito si nadie más en (−1, 1)
        if G == 0:
            return 1.0
        t = g.exponencial(G)
        return 1.0 if t > 2.0 else 0.0
    sim = P.simula(experimento, 40000, semilla)
    objetivo = S if ranurado else math.exp(-2 * G)
    if not sim.dentro(objetivo, 5):
        raise _error("DISCREPANT", f"simulación {sim.texto()} frente a {objetivo}")
    trace.verificacion("aloha.simulacion", ("ranuras simuladas con exactamente una trama: "
                                            if ranurado else "probabilidad de éxito de una trama "
                                            "(nadie más en 2T): ") + sim.texto())
    return {"S": S, "Smax": Smax, "Gopt": Gopt}


def desvanecimiento(e: dict, trace: Trace | None = None) -> dict:
    """Probabilidad de fallo ``P(γ < γ_th)`` (Rayleigh) o ``P(R < r)`` (Rice)."""
    trace = trace if trace is not None else Trace()
    modelo = str(e.get("modelo", "rayleigh")).lower()
    if modelo == "rayleigh" and e.get("snr_media_db") is not None:
        gm = db_a_lineal(float(P.fraccion(e["snr_media_db"])))
        gth = db_a_lineal(float(P.fraccion(e["umbral_db"])))
        pout = -math.expm1(-gth / gm)
        trace.metodo("fading.rayleigh_snr", f"γ ~ exponencial de media γ̄: P(γ < γ_th) = "
                                            f"1 − e^(−γ_th/γ̄) = {pout:.6g}",
                     why="con envolvente Rayleigh, la potencia instantánea es exponencial")
        num = P.tanh_sinh(lambda x: math.exp(-x / gm) / gm, 0.0, gth)
        if abs(num - pout) > 1e-9:
            raise _error("DISCREPANT", "cuadratura de la exponencial no coincide")
        trace.verificacion("fading.cuadratura", f"∫₀^γth e^(−γ/γ̄)/γ̄ = {num:.10g}")
        return {"P_fallo": pout}
    d = P.distribucion(modelo, e, trace)
    r = float(P.fraccion(e["r"], "r"))
    pf = d.F(r)
    pq = P.F_por_cuadratura(d, r)
    if abs(pf - pq) > 1e-8:
        raise _error("DISCREPANT", f"F({r}) = {pf} frente a cuadratura {pq}")
    trace.regla("fading.F", f"P(R < {r}) = {d.formula_F} = {pf:.6g}")
    trace.verificacion("fading.cuadratura", f"cuadratura de la densidad: {pq:.10g}")
    sim = P.simula(lambda g: 1.0 if d.muestra(g) < r else 0.0, 20000)
    if not sim.dentro(pf, 5):
        raise _error("DISCREPANT", f"simulación {sim.texto()}")
    trace.verificacion("fading.simulacion", f"envolvente simulada (componentes gaussianas): "
                                            f"{sim.texto()}")
    return {"P_fallo": pf, "dist": d}


def arq(e: dict, trace: Trace | None = None, semilla: int = 20261007) -> dict:
    """Eficiencia de parada y espera, retroceso N y repetición selectiva.

    Convención (Stallings): ``a = t_prop/t_trama``, ``P`` = probabilidad de error de
    trama, ACK instantáneos y sin error, ventana ``N``."""
    trace = trace if trace is not None else Trace()
    protocolo = str(e.get("protocolo", "parada_espera")).lower()
    Pe = float(P._prob(e.get("P", e.get("p", 0))))
    if e.get("a") is not None:
        a = float(P.fraccion(e["a"], "a"))
    else:
        a = float(P.fraccion(e["t_prop"], "t_prop")) / float(P.fraccion(e["t_trama"], "t_trama"))
    trace.convencion("arq.a", f"a = t_prop/t_trama = {a:.6g}; un ciclo de parada y espera dura "
                              "1 + 2a tramas")
    trace.hipotesis("arq.modelo", "errores independientes de trama con probabilidad P; ACK/NAK "
                                  "sin error y de duración despreciable", "se asume")
    N = int(e.get("N", 1))
    K = 1 + 2 * a
    if protocolo == "parada_espera":
        U = (1 - Pe) / K
        formula = "U = (1 − P)/(1 + 2a)"
        why = "cada intento ocupa 1 + 2a y hacen falta 1/(1 − P) intentos de media"
    elif protocolo == "retroceso_n":
        if N >= K:
            U = (1 - Pe) / (1 + 2 * a * Pe)
            formula = "U = (1 − P)/(1 + 2aP) (N ≥ 1 + 2a)"
        else:
            U = N * (1 - Pe) / (K * (1 - Pe + N * Pe))
            formula = "U = N(1 − P)/((1 + 2a)(1 − P + NP)) (N < 1 + 2a)"
        why = "cada error obliga a reenviar la trama y las que van detrás (hasta 1 + 2a o N)"
    elif protocolo == "repeticion_selectiva":
        U = (1 - Pe) if N >= K else N * (1 - Pe) / K
        formula = "U = 1 − P (N ≥ 1 + 2a)" if N >= K else "U = N(1 − P)/(1 + 2a) (N < 1 + 2a)"
        why = "solo se reenvía la trama errónea; la ventana limita si N < 1 + 2a"
    else:
        raise _error("BAD_INPUT", "protocolo: parada_espera, retroceso_n o repeticion_selectiva")
    trace.metodo("arq.formula", f"{formula} = {U:.6g}", why=why)
    # segundo camino: simulación sembrada del modelo de cuentas de la fórmula
    from academic_core.domain.engineering.mathlab.eventos import Generador

    g = Generador(semilla)
    tramas, tiempo = 20000, 0.0
    if protocolo == "parada_espera":
        for _ in range(tramas):
            while True:
                tiempo += K
                if g.uniforme() >= Pe:
                    break
    elif protocolo == "repeticion_selectiva":
        envios = 0
        for _ in range(tramas):
            while True:
                envios += 1
                if g.uniforme() >= Pe:
                    break
        tiempo = envios * (1.0 if N >= K else K / N)
    else:
        coste = K if N >= K else float(N)
        for _ in range(tramas):
            while True:
                if g.uniforme() >= Pe:
                    tiempo += 1.0 if N >= K else K / N
                    break
                tiempo += coste if N >= K else coste * K / N
    U_sim = tramas / tiempo
    if protocolo == "retroceso_n" and N < K:
        trace.aviso("arq.gbn_aprox", "con N < 1 + 2a la fórmula de retroceso N es una "
                                     "aproximación de libro; la simulación usa el mismo modelo")
    if abs(U_sim - U) > 0.03 * U + 1e-9:
        raise _error("DISCREPANT", f"simulación U ≈ {U_sim:.4g} frente a {U:.4g}")
    trace.verificacion("arq.simulacion", f"simulación sembrada de {tramas} tramas: U ≈ {U_sim:.5g}")
    return {"U": U, "formula": formula, "a": a, "U_sim": U_sim}
