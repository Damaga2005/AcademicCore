# SPDX-License-Identifier: MIT
"""ML-9 (§4.6, §8.2 G): distribuciones, tablas y aproximaciones.

Todo en Python puro (sin SciPy en el dominio). Dos reglas de §5.3:

- **Exacto donde se puede.** Con parámetros racionales, la binomial, la geométrica,
  la hipergeométrica, la uniforme y la beta de parámetros enteros dan fracciones
  exactas; la Poisson, la exponencial, la Erlang, la Weibull y la Rayleigh dan
  expresiones exactas con ``exp``. La normal, la t, la χ² y la F se dan con su
  valor numérico y el redondeo «de tabla» al lado, declarado (§15.2 punto 9).
- **Segundo camino independiente.** La función de distribución sale de su forma
  cerrada (o de la función especial: gamma o beta incompletas) y se contrasta con
  la **cuadratura tanh-sinh de la densidad**, que no comparte código con ella; las
  discretas se contrastan sumando la función de probabilidad término a término. La
  simulación sembrada (SplitMix64 de ``eventos``) se hace con el **mecanismo
  constructivo** de cada ley (suma de Bernoulli, ensayos hasta el éxito, Box-Muller,
  suma de exponenciales…), nunca invirtiendo la misma F que se quiere comprobar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.eventos import Generador
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def fraccion(v, que: str = "el parámetro") -> Fraction:
    """Un número del enunciado como fracción exacta: ``"0,3"``, ``"1/6"``, ``2``."""
    if isinstance(v, Fraction):
        return v
    if isinstance(v, bool):
        raise _error("BAD_INPUT", f"{que} no es un número")
    if isinstance(v, int):
        return Fraction(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise _error("BAD_INPUT", f"{que} no es finito")
        return Fraction(str(v))
    texto = str(v).strip().replace(",", ".").replace("−", "-")
    try:
        return Fraction(texto)
    except (ValueError, ZeroDivisionError):
        pass
    try:
        e = mx.parse(texto)
    except ValidationError:
        raise _error("BAD_INPUT", f"{que} «{v}» no es un número") from None
    q = mx.exact_value(e)
    if q is not None:
        return Fraction(q)
    val = mx.valor_real(e, {})
    if val is None:
        raise _error("BAD_INPUT", f"{que} «{v}» no es un número real")
    return Fraction(val).limit_denominator(10 ** 12)


def es_exacta(q: Fraction) -> bool:
    return q.denominator < 10 ** 9


# ---------------------------------------------------------------------------
# funciones especiales
# ---------------------------------------------------------------------------

SQRT2 = math.sqrt(2.0)


def Phi(z: float) -> float:
    """Función de distribución de la normal estándar."""
    return 0.5 * math.erfc(-z / SQRT2)


def Q(x: float) -> float:
    """Cola de la normal estándar: ``Q(x) = 1 − Φ(x) = ½·erfc(x/√2)``."""
    return 0.5 * math.erfc(x / SQRT2)


def phi(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def Phi_inv(p: float) -> float:
    """Cuantil de la normal estándar: aproximación racional de Acklam y dos pasos de
    Halley sobre ``erfc`` (error relativo < 1e-15)."""
    if not 0.0 < p < 1.0:
        raise _error("BAD_INPUT", "el cuantil necesita 0 < p < 1")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > 1 - 0.02425:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    for _ in range(2):
        e = Phi(x) - p if p < 0.5 else (1 - p) - Q(x)
        u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
        x = x - u / (1 + x * u / 2)
    return x


def gamma_inc_p(a: float, x: float) -> float:
    """Gamma incompleta regularizada inferior ``P(a, x)``: serie si ``x < a + 1``,
    fracción continua de Lentz si no."""
    if a <= 0:
        raise _error("BAD_INPUT", "P(a, x) necesita a > 0")
    if x <= 0:
        return 0.0
    lg = math.lgamma(a)
    if x < a + 1:
        termino = suma = 1.0 / a
        ap = a
        for _ in range(10000):
            ap += 1
            termino *= x / ap
            suma += termino
            if abs(termino) < abs(suma) * 1e-17:
                break
        return min(1.0, suma * math.exp(-x + a * math.log(x) - lg))
    return max(0.0, 1.0 - _gamma_cf(a, x, lg))


def _gamma_cf(a: float, x: float, lg: float) -> float:
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return math.exp(-x + a * math.log(x) - lg) * h


def beta_inc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada ``I_x(a, b)`` (fracción continua de Lentz con la
    simetría ``I_x(a, b) = 1 − I_{1−x}(b, a)``)."""
    if a <= 0 or b <= 0:
        raise _error("BAD_INPUT", "I_x(a, b) necesita a, b > 0")
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return math.exp(ln_bt) * _beta_cf(a, b, x) / a
    return 1.0 - math.exp(ln_bt) * _beta_cf(b, a, 1 - x) / b


def _beta_cf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1 / d
    h = d
    for m in range(1, 10000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return h


def bessel_i0(x: float) -> float:
    """``I₀(x)`` por su serie (todas las sumas positivas: sin cancelación)."""
    termino = suma = 1.0
    y = x * x / 4
    for k in range(1, 2000):
        termino *= y / (k * k)
        suma += termino
        if termino < suma * 1e-17:
            break
    return suma


def marcum_q1(a: float, b: float) -> float:
    """Función Q de Marcum de orden 1, ``Q₁(a, b) = P(R > b)`` para la envolvente de Rice
    de parámetro ``a`` con σ = 1 (serie de Poisson ponderada por gammas incompletas)."""
    if b <= 0:
        return 1.0
    # Q1(a, b) = Σ_k e^{-a²/2}(a²/2)^k/k! · (1 − P(k+1, b²/2))
    mu = a * a / 2
    y = b * b / 2
    total = 0.0
    peso = math.exp(-mu)
    acumulado = 0.0
    for k in range(0, 5000):
        if k:
            peso *= mu / k
        total += peso * (1 - gamma_inc_p(k + 1, y))
        acumulado += peso
        if acumulado > 1 - 1e-16 and k > mu:
            break
    return min(1.0, max(0.0, total))


def tanh_sinh(f: Callable[[float], float], a: float, b: float, nivel: int = 7) -> float:
    """Cuadratura doble exponencial en ``[a, b]``; tolera singularidades integrables en
    los extremos (χ² con 1 grado de libertad). Es el segundo camino de las F."""
    if a == b:
        return 0.0
    c, m = (a + b) / 2, (b - a) / 2
    h = 2.0 ** -nivel
    total = 0.0
    k = 0
    while True:
        t = k * h
        u = math.pi / 2 * math.sinh(t)
        ch = math.cosh(u)
        x = math.tanh(u)
        w = math.pi / 2 * math.cosh(t) / (ch * ch)
        if w < 1e-300 or 1 - x < 1e-300:
            break
        for s in ((1,) if k == 0 else (1, -1)):
            xi = c + m * s * x
            if a < xi < b:
                try:
                    v = f(xi)
                except (ValueError, ZeroDivisionError, OverflowError):
                    v = 0.0
                if math.isfinite(v):
                    total += w * v
        k += 1
        if t > 6.5:
            break
    return total * h * m


def integral_a_infinito(f: Callable[[float], float], a: float) -> float:
    """``∫_a^∞ f`` con ``x = a + t/(1 − t)``."""
    return tanh_sinh(lambda t: f(a + t / (1 - t)) / (1 - t) ** 2, 0.0, 1.0)


def _biseccion(F: Callable[[float], float], p: float, lo: float, hi: float) -> float:
    """``F(x) = p`` por bisección (F creciente), ampliando el intervalo si hace falta."""
    for _ in range(200):
        if F(lo) <= p:
            break
        lo = lo - max(1.0, abs(lo))
    for _ in range(200):
        if F(hi) >= p:
            break
        hi = hi + max(1.0, abs(hi))
    for _ in range(300):
        mid = (lo + hi) / 2
        if mid in (lo, hi):
            break
        if F(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# muestreo constructivo (segundo camino de la simulación)
# ---------------------------------------------------------------------------


def normal_std(g: Generador) -> float:
    """Box-Muller (solo el coseno: cada llamada consume dos uniformes)."""
    u1 = 1.0 - g.uniforme()
    u2 = g.uniforme()
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def gamma_muestra(g: Generador, forma: float, tasa: float) -> float:
    """Marsaglia–Tsang (forma ≥ 1) con el impulso ``U^(1/a)`` para forma < 1."""
    if forma < 1:
        return gamma_muestra(g, forma + 1, tasa) * (1.0 - g.uniforme()) ** (1 / forma)
    d = forma - 1 / 3
    c = 1 / math.sqrt(9 * d)
    while True:
        x = normal_std(g)
        v = (1 + c * x) ** 3
        if v <= 0:
            continue
        u = 1.0 - g.uniforme()
        if math.log(u) < 0.5 * x * x + d - d * v + d * math.log(v):
            return d * v / tasa


# ---------------------------------------------------------------------------
# distribuciones
# ---------------------------------------------------------------------------


def _expr_exp(coef: Fraction, exponente: Fraction, extra: str = "") -> mx.Expr:
    """``coef·e^(exponente)`` como expresión exacta."""
    base = f"exp({exponente})" if exponente != 0 else "1"
    texto = f"({coef})*{base}" if coef != 1 else base
    if extra:
        texto = f"{texto}*{extra}"
    return mx.parse(texto)


@dataclass
class Distribucion:
    """Una ley con sus parámetros, su densidad o probabilidad, su F, su cuantil y sus
    momentos. ``exacta_*`` devuelven ``Fraction``, ``mx.Expr`` o ``None``."""

    nombre: str
    parametros: dict
    discreta: bool
    soporte: tuple[float, float]
    densidad: Callable[[float], float]
    F: Callable[[float], float]
    media_f: Callable[[], object]
    varianza_f: Callable[[], object]
    muestra: Callable[[Generador], float]
    pmf_exacta: Callable[[int], object] | None = None
    F_exacta: Callable[[object], object] | None = None
    convenciones: tuple[str, ...] = ()
    hipotesis: tuple[str, ...] = ()
    formula: str = ""
    formula_F: str = ""
    especial: str = ""        # la función especial de la que sale F (segundo camino)
    tabla: bool = False       # ley de tabla: se da el redondeo «de tabla»
    extra: dict = field(default_factory=dict)
    coste: float = 1.0        # operaciones por muestra simulada (para acotar el tiempo)

    def muestras_asequibles(self, deseadas: int = 20000, presupuesto: float = 4e6) -> int:
        """Cuántas muestras caben en el presupuesto; 0 si ni 1000 caben."""
        n = int(min(deseadas, presupuesto / max(1.0, self.coste)))
        return n if n >= 1000 else 0

    def titulo(self) -> str:
        ps = ", ".join(f"{k} = {_fmt(v)}" for k, v in self.parametros.items())
        return f"{self.nombre}({ps})"

    def cuantil(self, p: float) -> float:
        if not 0 < p < 1:
            raise _error("BAD_INPUT", "el cuantil necesita 0 < p < 1")
        if self.discreta:
            k = int(max(self.soporte[0], 0))
            limite = 10 ** 7
            while self.F(k) < p - 1e-15 and k < limite:
                k += 1
            return float(k)
        lo = self.soporte[0] if math.isfinite(self.soporte[0]) else -10.0
        hi = self.soporte[1] if math.isfinite(self.soporte[1]) else 10.0
        if self.nombre == "normal":
            mu = float(self.parametros["μ"])
            return mu + math.sqrt(float(self.extra["var"])) * Phi_inv(p)
        return _biseccion(self.F, p, lo, hi)

    def cuantil_exacto(self, p: Fraction):
        """El menor ``k`` con ``F(k) ≥ p`` en exacto (discretas)."""
        if not self.discreta or self.F_exacta is None:
            return None
        k = int(max(self.soporte[0], 0))
        while k < 10 ** 6:
            Fk = self.F_exacta(k)
            if isinstance(Fk, Fraction) and Fk >= p:
                return k
            if not isinstance(Fk, Fraction):
                return None
            k += 1
        return None


def _fmt(v) -> str:
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v}"
    return str(v)


def _comb(n: int, k: int) -> int:
    return math.comb(n, k) if 0 <= k <= n else 0


def _entero(v, que: str, minimo: int = 0) -> int:
    q = fraccion(v, que)
    if q.denominator != 1 or q < minimo:
        raise _error("BAD_INPUT", f"{que} tiene que ser un entero ≥ {minimo}")
    return int(q)


def _prob(v, que: str = "p") -> Fraction:
    q = fraccion(v, que)
    if not 0 <= q <= 1:
        raise _error("BAD_INPUT", f"{que} = {q} no es una probabilidad (0 ≤ {que} ≤ 1)")
    return q


def _positivo(v, que: str) -> Fraction:
    q = fraccion(v, que)
    if q <= 0:
        raise _error("BAD_INPUT", f"{que} tiene que ser positivo")
    return q


ALIAS = {
    "bernoulli": "bernoulli", "binomial": "binomial", "geometrica": "geometrica",
    "geométrica": "geometrica", "poisson": "poisson", "hipergeometrica": "hipergeometrica",
    "hipergeométrica": "hipergeometrica", "pascal": "binomial_negativa",
    "binomial_negativa": "binomial_negativa", "uniforme_discreta": "uniforme_discreta",
    "uniforme": "uniforme", "exponencial": "exponencial", "gamma": "gamma",
    "erlang": "gamma", "normal": "normal", "gaussiana": "normal", "t": "t",
    "student": "t", "t_student": "t", "chi2": "chi2", "chi-cuadrado": "chi2",
    "ji2": "chi2", "f": "f", "fisher": "f", "beta": "beta", "weibull": "weibull",
    "rayleigh": "rayleigh", "rice": "rice", "laplace": "laplace",
}


def distribucion(nombre: str, params: dict, trace: Trace | None = None) -> Distribucion:
    """Construye la ley ``nombre`` con sus parámetros y declara las convenciones
    que cambian el resultado (tasa o media, σ o σ², geométrica desde 0 o desde 1)."""
    trace = trace if trace is not None else Trace()
    clave = ALIAS.get(str(nombre).strip().lower())
    if clave is None:
        raise _no(f"distribución «{nombre}» no reconocida (disponibles: "
                  f"{', '.join(sorted(set(ALIAS.values())))})")
    d = globals()["_d_" + clave](params)
    for c in d.convenciones:
        trace.convencion(f"dist.{clave}.convencion", c)
    for h in d.hipotesis:
        trace.hipotesis(f"dist.{clave}.hipotesis", h, "se asume")
    return d


def _p(params, *claves, defecto=None):
    for c in claves:
        if c in params and params[c] is not None:
            return params[c]
    if defecto is not None:
        return defecto
    raise _error("BAD_INPUT", f"falta el parámetro {claves[0]}")


# --- discretas -------------------------------------------------------------


def _d_bernoulli(params) -> Distribucion:
    params = dict(params)
    params.setdefault("n", 1)
    d = _d_binomial(params)
    d.nombre = "Bernoulli"
    d.parametros = {"p": d.parametros["p"]}
    d.formula = "P(X = 1) = p, P(X = 0) = 1 − p"
    return d


def _d_binomial(params) -> Distribucion:
    n = _entero(_p(params, "n"), "n", 1)
    p = _prob(_p(params, "p"))
    pf = float(p)
    if n > EXACTO_MAX:
        return _d_binomial_grande(n, p)

    def pmf_e(k: int) -> Fraction:
        return Fraction(_comb(n, k)) * p ** k * (1 - p) ** (n - k) if 0 <= k <= n else Fraction(0)

    def F_e(x) -> Fraction:
        k = math.floor(x)
        return sum((pmf_e(j) for j in range(0, min(k, n) + 1)), Fraction(0))

    def muestra(g: Generador) -> float:
        return float(sum(1 for _ in range(n) if g.uniforme() < pf))

    return Distribucion(
        "binomial", {"n": n, "p": p}, True, (0, n),
        lambda k: float(pmf_e(int(k))) if float(k).is_integer() else 0.0,
        lambda x: float(F_e(x)) if x >= 0 else 0.0,
        lambda: n * p, lambda: n * p * (1 - p), muestra, pmf_e,
        lambda x: F_e(x) if x >= 0 else Fraction(0),
        hipotesis=("n ensayos independientes con la misma probabilidad p de éxito",),
        formula="P(X = k) = C(n, k)·p^k·(1 − p)^(n−k)",
        formula_F="F(k) = Σ_{j ≤ k} P(X = j)", coste=float(n))


#: por encima, las sumas exactas en ℚ serían enormes y lentas: se usa la beta incompleta
EXACTO_MAX = 2000


def _d_binomial_grande(n: int, p: Fraction) -> Distribucion:
    pf = float(p)

    def pmf(k: float) -> float:
        if not float(k).is_integer() or not 0 <= k <= n:
            return 0.0
        if pf in (0.0, 1.0):
            return float((k == 0) if pf == 0 else (k == n))
        k = int(k)
        return math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                        + k * math.log(pf) + (n - k) * math.log1p(-pf))

    def F(x: float) -> float:
        k = math.floor(x)
        if k < 0:
            return 0.0
        if k >= n:
            return 1.0
        return beta_inc(n - k, k + 1, 1 - pf) if 0 < pf < 1 else float(pf == 0)

    def muestra(g: Generador) -> float:
        return float(sum(1 for _ in range(n) if g.uniforme() < pf))

    return Distribucion(
        "binomial", {"n": n, "p": p}, True, (0, n), pmf, F, lambda: n * p,
        lambda: n * p * (1 - p), muestra,
        hipotesis=("n ensayos independientes con la misma probabilidad p de éxito",),
        formula="P(X = k) = C(n, k)·p^k·(1 − p)^(n−k)",
        formula_F="F(k) = I_{1−p}(n − k, k + 1) (beta incompleta)", especial="beta incompleta",
        convenciones=(f"n = {n} > {EXACTO_MAX}: valores en coma flotante por la beta "
                      "incompleta, sin la suma exacta",), coste=float(n))


def _d_geometrica(params) -> Distribucion:
    p = _prob(_p(params, "p"))
    if p == 0:
        raise _error("BAD_INPUT", "con p = 0 no hay éxito nunca")
    desde = _entero(_p(params, "desde", defecto=1), "desde")
    if desde not in (0, 1):
        raise _error("BAD_INPUT", "la geométrica cuenta desde 1 (ensayos) o desde 0 (fracasos)")
    pf = float(p)
    qf = 1 - pf

    def pmf_e(k: int) -> Fraction:
        return p * (1 - p) ** (k - desde) if k >= desde else Fraction(0)

    def F_e(x) -> Fraction:
        k = math.floor(x)
        return 1 - (1 - p) ** (k - desde + 1) if k >= desde else Fraction(0)

    def muestra(g: Generador) -> float:
        k = desde
        while g.uniforme() >= pf:
            k += 1
            if k > 10 ** 7:
                break
        return float(k)

    conv = ("X = número de ENSAYOS hasta el primer éxito (k = 1, 2, …)" if desde == 1 else
            "X = número de FRACASOS antes del primer éxito (k = 0, 1, …)",)
    return Distribucion(
        "geométrica", {"p": p, "desde": desde}, True, (desde, math.inf),
        lambda k: (pf * qf ** (int(k) - desde)) if float(k).is_integer() and int(k) >= desde else 0.0,
        lambda x: 1 - qf ** (math.floor(x) - desde + 1) if math.floor(x) >= desde else 0.0,
        lambda: (1 / p) if desde == 1 else (1 - p) / p,
        lambda: (1 - p) / p ** 2, muestra, pmf_e, F_e, convenciones=conv,
        hipotesis=("ensayos de Bernoulli independientes; falta de memoria: "
                   "P(X > s + t | X > s) = P(X > t)",), coste=float(1 / p),
        formula=f"P(X = k) = p·(1 − p)^(k − {desde})",
        formula_F=f"P(X ≤ k) = 1 − (1 − p)^(k − {desde} + 1)")


def _d_binomial_negativa(params) -> Distribucion:
    r = _entero(_p(params, "r"), "r", 1)
    p = _prob(_p(params, "p"))
    pf = float(p)

    def pmf_e(k: int) -> Fraction:
        return Fraction(_comb(k - 1, r - 1)) * p ** r * (1 - p) ** (k - r) if k >= r else Fraction(0)

    def F_e(x) -> Fraction:
        k = math.floor(x)
        return sum((pmf_e(j) for j in range(r, k + 1)), Fraction(0))

    def muestra(g: Generador) -> float:
        exitos = k = 0
        while exitos < r:
            k += 1
            if g.uniforme() < pf:
                exitos += 1
        return float(k)

    return Distribucion(
        "Pascal", {"r": r, "p": p}, True, (r, math.inf),
        lambda k: float(pmf_e(int(k))) if float(k).is_integer() else 0.0,
        lambda x: float(F_e(x)), lambda: r / p, lambda: r * (1 - p) / p ** 2, muestra,
        pmf_e, F_e, convenciones=("X = número de ensayos hasta el r-ésimo éxito",),
        coste=float(r / p),
        formula="P(X = k) = C(k − 1, r − 1)·p^r·(1 − p)^(k − r)")


def _d_hipergeometrica(params) -> Distribucion:
    N = _entero(_p(params, "N", "poblacion"), "N", 1)
    K = _entero(_p(params, "K", "exitos"), "K")
    n = _entero(_p(params, "n", "muestra"), "n", 1)
    if K > N or n > N:
        raise _error("BAD_INPUT", "K y n no pueden superar a N")
    if n > EXACTO_MAX:
        raise _error("BAD_INPUT", f"muestra de n = {n} > {EXACTO_MAX}: demasiado grande para "
                                  "el cálculo exacto (usa la aproximación binomial)")
    total = _comb(N, n)

    def pmf_e(k: int) -> Fraction:
        return Fraction(_comb(K, k) * _comb(N - K, n - k), total)

    def F_e(x) -> Fraction:
        k = math.floor(x)
        return sum((pmf_e(j) for j in range(0, min(k, n) + 1)), Fraction(0))

    def muestra(g: Generador) -> float:
        buenos, quedan, k = K, N, 0
        for _ in range(n):
            if g.uniforme() * quedan < buenos:
                k += 1
                buenos -= 1
            quedan -= 1
        return float(k)

    return Distribucion(
        "hipergeométrica", {"N": N, "K": K, "n": n}, True, (max(0, n - (N - K)), min(n, K)),
        lambda k: float(pmf_e(int(k))) if float(k).is_integer() else 0.0,
        lambda x: float(F_e(x)) if x >= 0 else 0.0,
        lambda: Fraction(n * K, N),
        lambda: Fraction(n * K * (N - K) * (N - n), N * N * (N - 1)) if N > 1 else Fraction(0),
        muestra, pmf_e, lambda x: F_e(x) if x >= 0 else Fraction(0),
        hipotesis=("muestra de n SIN reemplazamiento de una población de N con K éxitos",),
        coste=float(n),
        formula="P(X = k) = C(K, k)·C(N − K, n − k)/C(N, n)")


def _d_uniforme_discreta(params) -> Distribucion:
    a = _entero(_p(params, "a"), "a", -10 ** 9)
    b = _entero(_p(params, "b"), "b", -10 ** 9)
    if b < a:
        raise _error("BAD_INPUT", "b < a")
    m = b - a + 1

    def pmf_e(k: int) -> Fraction:
        return Fraction(1, m) if a <= k <= b else Fraction(0)

    def F_e(x) -> Fraction:
        k = math.floor(x)
        return Fraction(min(max(k - a + 1, 0), m), m)

    return Distribucion(
        "uniforme discreta", {"a": a, "b": b}, True, (a, b),
        lambda k: float(pmf_e(int(k))) if float(k).is_integer() else 0.0,
        lambda x: float(F_e(x)), lambda: Fraction(a + b, 2), lambda: Fraction(m * m - 1, 12),
        lambda g: float(a + min(int(g.uniforme() * m), m - 1)), pmf_e, F_e,
        formula="P(X = k) = 1/(b − a + 1)")


def _d_poisson(params) -> Distribucion:
    lam = _positivo(_p(params, "λ", "lambda", "lam", "media"), "λ")
    t = fraccion(params.get("t", 1), "t")
    lam_t = lam * t
    lf = float(lam_t)
    if lf > 1e7:
        raise _error("BAD_INPUT", f"λ·t = {lf:g} demasiado grande (máximo 10⁷)")

    def pmf_e(k: int) -> mx.Expr | None:
        if k > EXACTO_MAX:
            return None
        return _expr_exp(lam_t ** k / math.factorial(k), -lam_t) if k >= 0 else mx.ZERO

    def F_e(x) -> mx.Expr | None:
        k = math.floor(x)
        if k < 0:
            return mx.ZERO
        if k > EXACTO_MAX:
            return None
        s = sum((lam_t ** j / math.factorial(j) for j in range(0, k + 1)), Fraction(0))
        return _expr_exp(s, -lam_t)

    def pmf(k: float) -> float:
        if not float(k).is_integer() or k < 0:
            return 0.0
        return math.exp(-lf + k * math.log(lf) - math.lgamma(k + 1))

    def F(x: float) -> float:
        k = math.floor(x)
        return 0.0 if k < 0 else 1.0 - gamma_inc_p(k + 1, lf)

    def muestra(g: Generador) -> float:
        # proceso de Poisson: cuántas llegadas exponenciales caben en [0, 1]
        tiempo, k = g.exponencial(lf), 0
        while tiempo <= 1.0:
            k += 1
            tiempo += g.exponencial(lf)
        return float(k)

    conv = (f"λ es la TASA por unidad; en un intervalo de longitud t la media es λ·t = {lam_t}",) \
        if t != 1 else ("el parámetro es la media λ (= tasa × tiempo)",)
    return Distribucion(
        "Poisson", {"λ·t" if t != 1 else "λ": lam_t}, True, (0, math.inf), pmf, F, coste=lf + 1,
        media_f=lambda: lam_t, varianza_f=lambda: lam_t, muestra=muestra, pmf_exacta=pmf_e,
        F_exacta=F_e, convenciones=conv,
        hipotesis=("sucesos raros e independientes a tasa constante",),
        formula="P(X = k) = e^(−λ)·λ^k/k!", formula_F="F(k) = e^(−λ)·Σ_{j ≤ k} λ^j/j!",
        especial="1 − P(k + 1, λ) (gamma incompleta)")


# --- continuas -------------------------------------------------------------


def _d_uniforme(params) -> Distribucion:
    a = fraccion(_p(params, "a"), "a")
    b = fraccion(_p(params, "b"), "b")
    if b <= a:
        raise _error("BAD_INPUT", "uniforme(a, b) necesita a < b")
    af, bf = float(a), float(b)

    def F_e(x) -> Fraction:
        x = Fraction(x)
        return Fraction(0) if x <= a else Fraction(1) if x >= b else (x - a) / (b - a)

    return Distribucion(
        "uniforme", {"a": a, "b": b}, False, (af, bf),
        lambda x: 1 / (bf - af) if af <= x <= bf else 0.0,
        lambda x: min(1.0, max(0.0, (x - af) / (bf - af))),
        lambda: (a + b) / 2, lambda: (b - a) ** 2 / 12,
        lambda g: af + (bf - af) * g.uniforme(), None, F_e,
        formula="f(x) = 1/(b − a) en [a, b]", formula_F="F(x) = (x − a)/(b − a)")


def _d_exponencial(params) -> Distribucion:
    if "media" in params and params["media"] is not None:
        media = _positivo(params["media"], "la media")
        lam = 1 / media
        conv = (f"se da la MEDIA 1/λ = {media}; la tasa es λ = {lam}",)
    else:
        lam = _positivo(_p(params, "λ", "lambda", "lam", "tasa"), "λ")
        conv = (f"se da la TASA λ = {lam}; la media es 1/λ = {1 / lam}",)
    lf = float(lam)

    def F_e(x):
        x = Fraction(x)
        return mx.ZERO if x <= 0 else mx.Sub(mx.ONE, _expr_exp(Fraction(1), -lam * x))

    return Distribucion(
        "exponencial", {"λ": lam}, False, (0.0, math.inf),
        lambda x: lf * math.exp(-lf * x) if x >= 0 else 0.0,
        lambda x: -math.expm1(-lf * x) if x > 0 else 0.0,
        lambda: 1 / lam, lambda: 1 / lam ** 2, lambda g: g.exponencial(lf), None, F_e,
        convenciones=conv,
        hipotesis=("falta de memoria: P(X > s + t | X > s) = P(X > t)",),
        formula="f(x) = λ·e^(−λx), x ≥ 0", formula_F="F(x) = 1 − e^(−λx)")


def _d_gamma(params) -> Distribucion:
    k = _positivo(_p(params, "k", "forma", "alfa", "α", "n"), "la forma k")
    if "escala" in params or "θ" in params:
        theta = _positivo(_p(params, "escala", "θ"), "la escala θ")
        lam = 1 / theta
        conv = (f"parámetros (forma k = {k}, ESCALA θ = {theta}); tasa λ = 1/θ = {lam}",)
    else:
        lam = _positivo(_p(params, "λ", "lambda", "tasa", "beta", "β"), "la tasa λ")
        conv = (f"parámetros (forma k = {k}, TASA λ = {lam}); escala θ = 1/λ = {1 / lam}",)
    kf, lf = float(k), float(lam)
    erlang = k.denominator == 1

    def F_e(x):
        if not erlang:
            return None
        x = Fraction(x)
        if x <= 0:
            return mx.ZERO
        # Erlang: 1 − e^(−λx)·Σ_{j<k} (λx)^j/j!
        s = sum(((lam * x) ** j / math.factorial(j) for j in range(int(k))), Fraction(0))
        return mx.Sub(mx.ONE, _expr_exp(s, -lam * x))

    def pdf(x: float) -> float:
        if x <= 0:
            return 0.0 if kf >= 1 or x < 0 else math.inf
        return math.exp(kf * math.log(lf) + (kf - 1) * math.log(x) - lf * x - math.lgamma(kf))

    def muestra(g: Generador) -> float:
        if erlang:
            return sum(g.exponencial(lf) for _ in range(int(k)))
        return gamma_muestra(g, kf, lf)

    return Distribucion(
        "Erlang" if erlang else "gamma", {"k": k, "λ": lam}, False, (0.0, math.inf), pdf,
        lambda x: gamma_inc_p(kf, lf * x) if x > 0 else 0.0,
        lambda: k / lam, lambda: k / lam ** 2, muestra, None, F_e if erlang else None,
        convenciones=conv,
        hipotesis=(("suma de k exponenciales independientes de tasa λ (tiempo hasta la "
                    "k-ésima llegada de un proceso de Poisson)",) if erlang else ()),
        formula="f(x) = λ^k·x^(k−1)·e^(−λx)/Γ(k)",
        formula_F=("F(x) = 1 − e^(−λx)·Σ_{j<k} (λx)^j/j!" if erlang else "F(x) = P(k, λx)"),
        especial="P(k, λx) (gamma incompleta)")


def _d_normal(params) -> Distribucion:
    mu = fraccion(_p(params, "μ", "mu", "media", defecto=0), "μ")
    if any(c in params for c in ("σ2", "sigma2", "varianza", "var")):
        var = _positivo(_p(params, "σ2", "sigma2", "varianza", "var"), "σ²")
        conv = (f"N(μ, σ²) con la VARIANZA σ² = {var} (σ = √{var})",)
        sigma_f = math.sqrt(float(var))
    else:
        sigma = _positivo(_p(params, "σ", "sigma", "desviacion", defecto=1), "σ")
        var = sigma ** 2
        conv = (f"N(μ, σ) con la DESVIACIÓN típica σ = {sigma} (σ² = {var})",)
        sigma_f = float(sigma)
    mf = float(mu)
    return Distribucion(
        "normal", {"μ": mu, "σ²": var}, False, (-math.inf, math.inf),
        lambda x: phi((x - mf) / sigma_f) / sigma_f, lambda x: Phi((x - mf) / sigma_f),
        lambda: mu, lambda: var, lambda g: mf + sigma_f * normal_std(g),
        convenciones=conv, formula="f(x) = e^(−(x−μ)²/(2σ²))/(σ√(2π))",
        formula_F="F(x) = Φ((x − μ)/σ)", especial="Φ = ½·erfc(−z/√2)", tabla=True,
        extra={"var": var})


def _d_t(params) -> Distribucion:
    nu = _positivo(_p(params, "ν", "nu", "gl", "n"), "los grados de libertad ν")
    v = float(nu)
    c = math.exp(math.lgamma((v + 1) / 2) - math.lgamma(v / 2)) / math.sqrt(v * math.pi)

    def F(x: float) -> float:
        ib = beta_inc(v / 2, 0.5, v / (v + x * x))
        return 1 - ib / 2 if x > 0 else ib / 2

    def muestra(g: Generador) -> float:
        z = normal_std(g)
        chi = gamma_muestra(g, v / 2, 0.5)
        return z / math.sqrt(chi / v)

    return Distribucion(
        "t de Student", {"ν": nu}, False, (-math.inf, math.inf),
        lambda x: c * (1 + x * x / v) ** (-(v + 1) / 2), F,
        lambda: Fraction(0) if v > 1 else None,
        lambda: (nu / (nu - 2)) if v > 2 else None, muestra,
        formula="f(t) = Γ((ν+1)/2)/(√(νπ)·Γ(ν/2))·(1 + t²/ν)^(−(ν+1)/2)",
        formula_F="F(t) = 1 − ½·I_{ν/(ν+t²)}(ν/2, ½) para t > 0",
        especial="beta incompleta", tabla=True)


def _d_chi2(params) -> Distribucion:
    k = _positivo(_p(params, "k", "gl", "ν", "nu", "n"), "los grados de libertad k")
    kf = float(k)

    def pdf(x: float) -> float:
        if x <= 0:
            return 0.0
        return math.exp((kf / 2 - 1) * math.log(x) - x / 2 - (kf / 2) * math.log(2)
                        - math.lgamma(kf / 2))

    def muestra(g: Generador) -> float:
        if k.denominator == 1 and k <= 60:
            return sum(normal_std(g) ** 2 for _ in range(int(k)))
        return gamma_muestra(g, kf / 2, 0.5)

    return Distribucion(
        "χ²", {"k": k}, False, (0.0, math.inf), pdf,
        lambda x: gamma_inc_p(kf / 2, x / 2) if x > 0 else 0.0,
        lambda: k, lambda: 2 * k, muestra,
        hipotesis=("suma de k cuadrados de normales estándar independientes",),
        formula="f(x) = x^(k/2−1)·e^(−x/2)/(2^(k/2)·Γ(k/2))", formula_F="F(x) = P(k/2, x/2)",
        especial="gamma incompleta", tabla=True)


def _d_f(params) -> Distribucion:
    d1 = _positivo(_p(params, "d1", "m", "gl1"), "d1")
    d2 = _positivo(_p(params, "d2", "gl2"), "d2")
    a, b = float(d1), float(d2)
    lc = (a / 2) * math.log(a / b) - (math.lgamma(a / 2) + math.lgamma(b / 2) - math.lgamma((a + b) / 2))

    def pdf(x: float) -> float:
        if x <= 0:
            return 0.0
        return math.exp(lc + (a / 2 - 1) * math.log(x) - (a + b) / 2 * math.log1p(a * x / b))

    def muestra(g: Generador) -> float:
        return (gamma_muestra(g, a / 2, 0.5) / a) / (gamma_muestra(g, b / 2, 0.5) / b)

    return Distribucion(
        "F de Snedecor", {"d1": d1, "d2": d2}, False, (0.0, math.inf), pdf,
        lambda x: beta_inc(a / 2, b / 2, a * x / (a * x + b)) if x > 0 else 0.0,
        lambda: d2 / (d2 - 2) if b > 2 else None,
        lambda: (2 * d2 ** 2 * (d1 + d2 - 2) / (d1 * (d2 - 2) ** 2 * (d2 - 4))) if b > 4 else None,
        muestra, formula="F = (χ²_{d1}/d1)/(χ²_{d2}/d2)",
        formula_F="F(x) = I_{d1·x/(d1·x + d2)}(d1/2, d2/2)", especial="beta incompleta",
        tabla=True)


def _d_beta(params) -> Distribucion:
    a = _positivo(_p(params, "a", "α", "alfa"), "a")
    b = _positivo(_p(params, "b", "β", "beta"), "b")
    af, bf = float(a), float(b)
    enteros = a.denominator == 1 and b.denominator == 1
    lB = math.lgamma(af) + math.lgamma(bf) - math.lgamma(af + bf)

    def F_e(x):
        if not enteros:
            return None
        x = Fraction(x)
        if x <= 0:
            return Fraction(0)
        if x >= 1:
            return Fraction(1)
        n = int(a + b - 1)
        return sum((Fraction(_comb(n, j)) * x ** j * (1 - x) ** (n - j)
                    for j in range(int(a), n + 1)), Fraction(0))

    def pdf(x: float) -> float:
        if not 0 < x < 1:
            return 0.0
        return math.exp((af - 1) * math.log(x) + (bf - 1) * math.log1p(-x) - lB)

    def muestra(g: Generador) -> float:
        x = gamma_muestra(g, af, 1.0)
        y = gamma_muestra(g, bf, 1.0)
        return x / (x + y)

    return Distribucion(
        "beta", {"a": a, "b": b}, False, (0.0, 1.0), pdf,
        lambda x: beta_inc(af, bf, x) if x > 0 else 0.0,
        lambda: a / (a + b), lambda: a * b / ((a + b) ** 2 * (a + b + 1)), muestra, None,
        F_e if enteros else None,
        formula="f(x) = x^(a−1)·(1 − x)^(b−1)/B(a, b)",
        formula_F=("F(x) = Σ_{j=a}^{a+b−1} C(a+b−1, j)·x^j·(1−x)^(a+b−1−j)" if enteros
                   else "F(x) = I_x(a, b)"), especial="beta incompleta")


def _d_weibull(params) -> Distribucion:
    k = _positivo(_p(params, "k", "forma"), "la forma k")
    lam = _positivo(_p(params, "λ", "lambda", "escala"), "la escala λ")
    kf, lf = float(k), float(lam)

    def F_e(x):
        x = Fraction(x)
        if x <= 0:
            return mx.ZERO
        return mx.parse(f"1 - exp(-({x / lam})^({k}))")

    return Distribucion(
        "Weibull", {"k": k, "λ": lam}, False, (0.0, math.inf),
        lambda x: (kf / lf) * (x / lf) ** (kf - 1) * math.exp(-(x / lf) ** kf) if x > 0 else 0.0,
        lambda x: -math.expm1(-(x / lf) ** kf) if x > 0 else 0.0,
        lambda: lf * math.gamma(1 + 1 / kf), lambda: lf ** 2 * (math.gamma(1 + 2 / kf)
                                                              - math.gamma(1 + 1 / kf) ** 2),
        lambda g: lf * (-math.log(1.0 - g.uniforme())) ** (1 / kf), None, F_e,
        convenciones=("F(x) = 1 − e^(−(x/λ)^k): λ es la ESCALA, no la tasa",),
        formula="f(x) = (k/λ)(x/λ)^(k−1)·e^(−(x/λ)^k)", formula_F="F(x) = 1 − e^(−(x/λ)^k)")


def _d_rayleigh(params) -> Distribucion:
    if any(c in params for c in ("Ω", "omega", "potencia")):
        omega = _positivo(_p(params, "Ω", "omega", "potencia"), "Ω = E[R²]")
        s2 = omega / 2
        conv = (f"se da Ω = E[R²] = 2σ² = {omega}",)
    else:
        sigma = _positivo(_p(params, "σ", "sigma"), "σ")
        s2 = sigma ** 2
        conv = (f"σ es la desviación de CADA componente gaussiana (σ² = {s2}); E[R²] = 2σ²",)
    sf = math.sqrt(float(s2))

    def F_e(x):
        x = Fraction(x)
        return mx.ZERO if x <= 0 else mx.Sub(mx.ONE, _expr_exp(Fraction(1), -x * x / (2 * s2)))

    return Distribucion(
        "Rayleigh", {"σ²": s2}, False, (0.0, math.inf),
        lambda r: r / sf ** 2 * math.exp(-r * r / (2 * sf ** 2)) if r > 0 else 0.0,
        lambda r: -math.expm1(-r * r / (2 * sf ** 2)) if r > 0 else 0.0,
        lambda: sf * math.sqrt(math.pi / 2), lambda: (4 - math.pi) / 2 * sf ** 2,
        lambda g: sf * math.hypot(normal_std(g), normal_std(g)), None, F_e,
        convenciones=conv,
        hipotesis=("envolvente de una señal con componentes en fase y cuadratura gaussianas "
                   "independientes de media 0 (sin trayecto directo)",),
        formula="f(r) = (r/σ²)·e^(−r²/(2σ²))", formula_F="F(r) = 1 − e^(−r²/(2σ²))")


def _d_rice(params) -> Distribucion:
    sigma2 = None
    if "K" in params:
        K = fraccion(params["K"], "K")
        omega = _positivo(_p(params, "Ω", "omega", defecto=1), "Ω")
        nu2 = K * omega / (K + 1)
        sigma2 = omega / (2 * (K + 1))
        conv = (f"factor K = ν²/(2σ²) = {K} (lineal, no en dB) y Ω = ν² + 2σ² = {omega}",)
    else:
        nu = fraccion(_p(params, "ν", "nu"), "ν")
        sigma2 = _positivo(_p(params, "σ2", "sigma2", "σ²"), "σ²") if any(
            c in params for c in ("σ2", "sigma2", "σ²")) else _positivo(_p(params, "σ", "sigma"), "σ") ** 2
        nu2 = nu * nu
        conv = (f"ν = amplitud del trayecto directo, σ² = {sigma2} por componente",)
    nu_f, s = math.sqrt(float(nu2)), math.sqrt(float(sigma2))

    def pdf(r: float) -> float:
        if r <= 0:
            return 0.0
        z = r * nu_f / s ** 2
        # I0(z)·e^(−z) evitando el desbordamiento
        i0e = bessel_i0(z) * math.exp(-z) if z < 700 else 1 / math.sqrt(2 * math.pi * z)
        return r / s ** 2 * math.exp(-(r - nu_f) ** 2 / (2 * s ** 2)) * i0e

    return Distribucion(
        "Rice", {"ν²": nu2, "σ²": sigma2}, False, (0.0, math.inf), pdf,
        lambda r: 1 - marcum_q1(nu_f / s, r / s) if r > 0 else 0.0,
        lambda: None, lambda: None,
        lambda g: math.hypot(nu_f + s * normal_std(g), s * normal_std(g)),
        convenciones=conv,
        hipotesis=("trayecto directo de amplitud ν más dispersión gaussiana σ² por componente",),
        formula="f(r) = (r/σ²)·e^(−(r²+ν²)/(2σ²))·I₀(rν/σ²)",
        formula_F="F(r) = 1 − Q₁(ν/σ, r/σ)", especial="Q de Marcum",
        extra={"E[R²]": float(nu2 + 2 * sigma2)})


def _d_laplace(params) -> Distribucion:
    mu = fraccion(_p(params, "μ", "mu", defecto=0), "μ")
    b = _positivo(_p(params, "b", "escala"), "b")
    mf, bf = float(mu), float(b)

    def F(x: float) -> float:
        return 0.5 * math.exp((x - mf) / bf) if x < mf else 1 - 0.5 * math.exp(-(x - mf) / bf)

    def muestra(g: Generador) -> float:
        return mf + bf * (g.exponencial(1.0) - g.exponencial(1.0))

    return Distribucion(
        "Laplace", {"μ": mu, "b": b}, False, (-math.inf, math.inf),
        lambda x: math.exp(-abs(x - mf) / bf) / (2 * bf), F, lambda: mu, lambda: 2 * b * b,
        muestra, formula="f(x) = e^(−|x−μ|/b)/(2b)")


# ---------------------------------------------------------------------------
# sucesos: «P(X <= 3)», «P(2 < X <= 5)», «P(X > 1 | X > 0.5)»
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Intervalo:
    lo: Fraction | None
    lo_cerrado: bool
    hi: Fraction | None
    hi_cerrado: bool

    def texto(self, v: str = "X") -> str:
        if self.lo is not None and self.hi is not None and self.lo == self.hi:
            return f"{v} = {_fmt(self.lo)}"
        partes = []
        if self.lo is not None:
            partes.append(f"{_fmt(self.lo)} {'≤' if self.lo_cerrado else '<'} ")
        partes.append(v)
        if self.hi is not None:
            partes.append(f" {'≤' if self.hi_cerrado else '<'} {_fmt(self.hi)}")
        return "".join(partes)

    def interseca(self, otro: "Intervalo") -> "Intervalo":
        lo, lc = self.lo, self.lo_cerrado
        if otro.lo is not None and (lo is None or otro.lo > lo or (otro.lo == lo and not otro.lo_cerrado)):
            lo, lc = otro.lo, otro.lo_cerrado
        hi, hc = self.hi, self.hi_cerrado
        if otro.hi is not None and (hi is None or otro.hi < hi or (otro.hi == hi and not otro.hi_cerrado)):
            hi, hc = otro.hi, otro.hi_cerrado
        return Intervalo(lo, lc, hi, hc)

    def vacio(self) -> bool:
        if self.lo is None or self.hi is None:
            return False
        return self.lo > self.hi or (self.lo == self.hi and not (self.lo_cerrado and self.hi_cerrado))


_OPS = {"<=": "≤", ">=": "≥", "=<": "≤", "=>": "≥"}


def lee_suceso(texto: str) -> tuple[Intervalo, Intervalo | None]:
    """``"P(2 < X <= 5)"`` → intervalo; ``"P(X > 3 | X > 1)"`` → (A, B)."""
    t = texto.strip().replace(" ", "").replace("−", "-")
    for a, b in _OPS.items():
        t = t.replace(a, b)
    if t[:2].upper() == "P(" and t.endswith(")"):
        t = t[2:-1]
    if "|" in t:
        a, b = t.split("|", 1)
        return _un_suceso(a), _un_suceso(b)
    return _un_suceso(t), None


def _un_suceso(t: str) -> Intervalo:
    import re

    m = re.fullmatch(r"([^<>≤≥=]+)(<|≤)([A-Za-z])(<|≤)([^<>≤≥=]+)", t)
    if m:
        return Intervalo(fraccion(m.group(1), "el extremo"), m.group(2) == "≤",
                         fraccion(m.group(5), "el extremo"), m.group(4) == "≤")
    m = re.fullmatch(r"([A-Za-z])(<|≤|>|≥|=|==)([^<>≤≥=]+)", t)
    if m:
        v = fraccion(m.group(3), "el valor")
        op = m.group(2)
    else:
        m = re.fullmatch(r"([^<>≤≥=]+)(<|≤|>|≥|=|==)([A-Za-z])", t)
        if not m:
            raise _error("BAD_INPUT", f"no entiendo el suceso «{t}» (ejemplos: X <= 3, "
                                      "2 < X <= 5, X > 1 | X > 0.5)")
        v = fraccion(m.group(1), "el valor")
        op = {"<": ">", "≤": "≥", ">": "<", "≥": "≤"}.get(m.group(2), m.group(2))
    if op in ("=", "=="):
        return Intervalo(v, True, v, True)
    if op == "<":
        return Intervalo(None, False, v, False)
    if op == "≤":
        return Intervalo(None, False, v, True)
    if op == ">":
        return Intervalo(v, False, None, False)
    return Intervalo(v, True, None, False)


def probabilidad_intervalo(d: Distribucion, I: Intervalo) -> tuple[float, object]:
    """``(valor, exacto)`` de ``P(X ∈ I)``; ``exacto`` es Fraction, Expr o None."""
    if I.vacio():
        return 0.0, Fraction(0)
    if d.discreta:
        lo = -math.inf if I.lo is None else (math.ceil(I.lo) if I.lo_cerrado else math.floor(I.lo) + 1)
        hi = math.inf if I.hi is None else (math.floor(I.hi) if I.hi_cerrado else math.ceil(I.hi) - 1)
        lo = max(lo, d.soporte[0])
        hi = min(hi, d.soporte[1])
        if lo > hi:
            return 0.0, Fraction(0)

        def Fd(k):
            return 0.0 if k < d.soporte[0] else (1.0 if k >= d.soporte[1] else d.F(k))

        valor = Fd(hi) - Fd(lo - 1)
        exacto = None
        if d.F_exacta is not None:
            Fhi = Fraction(1) if hi == math.inf or hi >= d.soporte[1] else d.F_exacta(int(hi))
            Flo = Fraction(0) if lo <= d.soporte[0] else d.F_exacta(int(lo) - 1)
            exacto = _resta(Fhi, Flo)
        return valor, exacto
    a = -math.inf if I.lo is None else float(I.lo)
    b = math.inf if I.hi is None else float(I.hi)
    Fb = 1.0 if b == math.inf else d.F(b)
    Fa = 0.0 if a == -math.inf else d.F(a)
    exacto = None
    if d.F_exacta is not None:
        Eb = Fraction(1) if I.hi is None else d.F_exacta(I.hi)
        Ea = Fraction(0) if I.lo is None else d.F_exacta(I.lo)
        if Eb is not None and Ea is not None:
            exacto = _resta(Eb, Ea)
    return Fb - Fa, exacto


def _resta(a, b):
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        return a - b
    if a is None or b is None:
        return None
    ea = mx.num(a) if isinstance(a, Fraction) else a
    eb = mx.num(b) if isinstance(b, Fraction) else b
    return simplifica(mx.Sub(ea, eb))


def simplifica(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import calculators as K

    try:
        e = K.pliega_constante(e)
    except Exception:  # noqa: BLE001
        pass
    q = mx.exact_value(e)
    return mx.num(q) if q is not None else e


def texto_exacto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Fraction):
        if v.denominator > 10 ** 40 or abs(v.numerator) > 10 ** 40:
            return ""          # una fracción de cientos de cifras no se lee: solo el decimal
        return str(v)
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, mx.Expr):
        return mx.text(v).replace("+ -", "- ")
    return str(v)


def valor_de(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (Fraction, int, float)):
        return float(v)
    r = mx.valor_real(v, {})
    return None if r is None else float(r)


# ---------------------------------------------------------------------------
# segundos caminos
# ---------------------------------------------------------------------------


def F_por_cuadratura(d: Distribucion, x: float) -> float:
    """``F(x)`` integrando la densidad (tanh-sinh), sin usar la forma cerrada."""
    lo, hi = d.soporte
    if x <= lo:
        return 0.0
    if x >= hi:
        return 1.0
    if math.isfinite(lo):
        return tanh_sinh(d.densidad, lo, x)
    # simétricas respecto de su centro (normal, t, Laplace): ½ ± ∫ desde el centro
    centro = float(d.parametros.get("μ", 0)) if d.nombre in ("normal", "Laplace") else 0.0
    if x >= centro:
        return 0.5 + tanh_sinh(d.densidad, centro, x)
    return 0.5 - tanh_sinh(d.densidad, x, centro)


def momentos_numericos(d: Distribucion) -> tuple[float, float] | None:
    """``(E[X], Var X)`` sumando o integrando, sin las fórmulas de la familia."""
    if d.discreta:
        lo = int(d.soporte[0])
        try:   # una ventana de ±40σ alrededor de la media (Poisson con λ = 10⁶)
            m0, v0 = float(d.media_f()), float(d.varianza_f())
            lo = max(lo, int(m0 - 40 * math.sqrt(v0) - 1))
        except (TypeError, ValueError):
            pass
        s0 = s1 = s2 = 0.0
        k = lo
        while k <= d.soporte[1] and k < lo + 200000:
            p = float(d.densidad(k))  # vía numérica: en float (en Fraction,
            # (1−p)^k con k ~ 1/p cuelga con miles de cifras: P1c de PPE-2025)
            s0 += p
            s1 += k * p
            s2 += k * k * p
            if k > lo + 50 and s0 > 1 - 1e-15 and p < 1e-18:
                break
            k += 1
        m = s1 / s0
        return m, s2 / s0 - m * m
    lo, hi = d.soporte
    if math.isfinite(lo) and math.isfinite(hi):
        m = tanh_sinh(lambda x: x * d.densidad(x), lo, hi)
        m2 = tanh_sinh(lambda x: x * x * d.densidad(x), lo, hi)
        return m, m2 - m * m
    if math.isfinite(lo):
        m = integral_a_infinito(lambda x: x * d.densidad(x), lo)
        m2 = integral_a_infinito(lambda x: x * x * d.densidad(x), lo)
        return m, m2 - m * m
    c = float(d.parametros.get("μ", 0)) if d.nombre in ("normal", "Laplace") else 0.0
    m = c + integral_a_infinito(lambda x: x * d.densidad(c + x), 0) - integral_a_infinito(
        lambda x: x * d.densidad(c - x), 0)
    m2 = integral_a_infinito(lambda x: (c + x) ** 2 * d.densidad(c + x), 0) + \
        integral_a_infinito(lambda x: (c - x) ** 2 * d.densidad(c - x), 0)
    return m, m2 - m * m


@dataclass(frozen=True)
class Simulacion:
    valor: float
    error_tipico: float
    muestras: int
    semilla: int

    def dentro(self, objetivo: float, sigmas: float = 5.0) -> bool:
        return abs(self.valor - objetivo) <= sigmas * max(self.error_tipico, 1e-12) + 1e-12

    def texto(self) -> str:
        return (f"{self.valor:.6g} ± {self.error_tipico:.2g} (1σ, {self.muestras} muestras, "
                f"semilla {self.semilla})")


def simula(indicador: Callable[[Generador], float], muestras: int = 20000,
           semilla: int = 20261007) -> Simulacion:
    g = Generador(semilla)
    s = s2 = 0.0
    for _ in range(muestras):
        v = indicador(g)
        s += v
        s2 += v * v
    m = s / muestras
    var = max(0.0, (s2 - muestras * m * m) / (muestras - 1))
    return Simulacion(m, math.sqrt(var / muestras), muestras, semilla)


def en_intervalo(I: Intervalo, x: float) -> bool:
    if I.lo is not None:
        if x < I.lo or (x == I.lo and not I.lo_cerrado):
            return False
    if I.hi is not None:
        if x > I.hi or (x == I.hi and not I.hi_cerrado):
            return False
    return True


# ---------------------------------------------------------------------------
# tablas (§15.2 punto 9): calculadas, con el redondeo «de tabla» declarado
# ---------------------------------------------------------------------------


def redondeo_tabla(v: float, cifras: int = 2) -> str:
    return f"{v:.{cifras}f}".replace(".", ",")


def cuantil_tabla(ley: str, p: float, **gl) -> tuple[float, float]:
    """``(cuantil, comprobación F(cuantil))``: el cuantil por la función especial
    y la F por cuadratura de la densidad (independiente)."""
    d = distribucion(ley, gl)
    q = d.cuantil(p)
    return q, F_por_cuadratura(d, q)
