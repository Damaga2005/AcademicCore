# SPDX-License-Identifier: MIT
"""ML-14 (§4.15): señales y sistemas deterministas.

Bloque 15 con respaldo E: biblioteca de señales, convolución analógica por
tramos y digital, periódicas por señal base, energía/potencia/Parseval,
correlación y densidad espectral, DTFT, DFT y transformada z ampliada
(eco, reverberación e inverso).

Convenios de Señales y Sistemas (§5.11, fijos en este módulo):

- frecuencia ordinaria ``f``: ``X(f) = ∫x(t)·e^{-j2πft}dt``;
- ``sinc(x) = sin(πx)/(πx)``; ``Π`` de ancho 1; ``Λ`` de ancho 2;
- frecuencia normalizada ``F = f/f_m`` de periodo 1; en la DFT ``k > N/2``
  equivale a frecuencia negativa ``k − N``; ``p_L[n]`` causal de ``L`` muestras.

Cada función recibe una ``trace`` opcional, escribe su «por qué este método»
(§5.5b), comprueba sus hipótesis (§5.7) y verifica por un segundo camino
independiente (§5.3). Si el segundo camino discrepa, se lanza
``DISCREPANT`` y la calculadora lo convierte en sello «discrepa».
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

INF = None  # extremo infinito en un segmento


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    """Un número del enunciado como fracción exacta."""
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


def _fmt_q(q: Fraction) -> str:
    if q.denominator == 1:
        return str(q.numerator)
    return f"{q.numerator}/{q.denominator}"


def sinc(x: float) -> float:
    """sinc normalizado de §5.11: sin(πx)/(πx), con sinc(0) = 1."""
    if x == 0.0:
        return 1.0
    px = math.pi * x
    return math.sin(px) / px


# ---------------------------------------------------------------------------
# segmentos: (c0 + c1·t)·e^{r·t} en [a, b] (§4.15: pulsos y exponenciales)
# ---------------------------------------------------------------------------

@dataclass
class Segmento:
    a: Fraction | None  # None = −∞
    b: Fraction | None  # None = +∞
    c0: Fraction = Fraction(0)
    c1: Fraction = Fraction(0)
    r: Fraction | None = None  # tasa exponencial (None o 0 = polinomio)
    origen: Fraction | None = None  # las exponenciales causales miden t − origen

    def eval(self, t: float) -> float:
        if self.r is not None and self.r != 0:
            t0 = float(self.origen) if self.origen is not None else 0.0
            v = float(self.c0) + float(self.c1) * (t - t0)
            return v * math.exp(float(self.r) * (t - t0))
        return float(self.c0) + float(self.c1) * t

    def contiene(self, t: Fraction) -> bool:
        if self.a is not None and t < self.a:
            return False
        if self.b is not None and t >= self.b:
            return False
        return True

    def texto(self) -> str:
        base = ""
        if self.c1 == 0:
            base = _fmt_q(self.c0)
        elif self.c0 == 0:
            base = f"{_fmt_q(self.c1)}·t"
        else:
            s = "+" if self.c1 > 0 else "−"
            base = f"{_fmt_q(self.c0)} {s} {_fmt_q(abs(self.c1))}·t"
        if self.r is not None and self.r != 0:
            if self.origen is not None:
                return f"({base})·e^({_fmt_q(self.r)}·(t−{_fmt_q(self.origen)}))"
            return f"({base})·e^({_fmt_q(self.r)}·t)"
        return base


def rect(a, b, A=1) -> Segmento:
    """Pulso rectangular Π: altura A en [a, b)."""
    A, a, b = _Q(A), _Q(a), _Q(b)
    if not b > a:
        raise _error("BAD_INPUT", f"rect: se necesita a < b (a = {a}, b = {b})")
    return Segmento(a, b, A, Fraction(0), None)


def tri(t0, T, A=1) -> list[Segmento]:
    """Pulso triangular Λ: pico A en t0, soporte [t0−T, t0+T] (ancho 2T)."""
    A, t0, T = _Q(A), _Q(t0), _Q(T)
    if not T > 0:
        raise _error("BAD_INPUT", f"tri: se necesita T > 0 (T = {T})")
    # subida: A·(t − (t0−T))/T ; bajada: A·((t0+T) − t)/T
    return [Segmento(t0 - T, t0, -A * (t0 - T) / T, A / T, None),
            Segmento(t0, t0 + T, A * (t0 + T) / T, -A / T, None)]


def exp_causal(t0, T, A=1) -> Segmento:
    """Exponencial causal A·e^{−(t−t0)/T}·u(t−t0), T > 0."""
    A, t0, T = _Q(A), _Q(t0), _Q(T)
    if not T > 0:
        raise _error("BAD_INPUT", f"exp: se necesita T > 0 (T = {T})")
    return Segmento(t0, INF, A, Fraction(0), -Fraction(1, 1) / T, origen=t0)


def _eval_senal(segs: list[Segmento], t: float) -> float:
    return sum(s.eval(t) for s in segs
               if (s.a is None or t >= float(s.a) - 1e-12)
               and (s.b is None or t < float(s.b) - 1e-12))


def _soporte(segs: list[Segmento]) -> tuple[Fraction | None, Fraction | None]:
    a = min((s.a for s in segs if s.a is not None), default=None)
    b = max((s.b for s in segs if s.b is not None), default=None)
    if any(s.b is None for s in segs):
        b = None
    return a, b


def _ruptura_principal(segs: list[Segmento]) -> list[Fraction]:
    pts = set()
    for s in segs:
        if s.a is not None:
            pts.add(s.a)
        if s.b is not None:
            pts.add(s.b)
    return sorted(pts)


# ---------------------------------------------------------------------------
# biblioteca: integrales, energías y TF de cada pulso (§4.15, fila 1)
# ---------------------------------------------------------------------------

def integral_rect(A, T) -> Fraction:
    return _Q(A) * _Q(T)


def energia_rect(A, T) -> Fraction:
    A, T = _Q(A), _Q(T)
    return A * A * T


def integral_tri(A, T) -> Fraction:
    return _Q(A) * _Q(T)


def energia_tri(A, T) -> Fraction:
    A, T = _Q(A), _Q(T)
    return Fraction(2, 3) * A * A * T


def integral_exp(A, T) -> Fraction:
    return _Q(A) * _Q(T)


def energia_exp(A, T) -> Fraction:
    A, T = _Q(A), _Q(T)
    return A * A * T / 2


def tf_rect(f: float, A, t0, T) -> complex:
    """X(f) = A·T·sinc(f·T)·e^{−j2πf·t0} (pulso centrado en t0, ancho T)."""
    return complex(float(_Q(A)) * float(_Q(T)) * sinc(f * float(_Q(T))), 0.0) \
        * cmath.exp(-1j * 2 * math.pi * f * float(_Q(t0)))


def tf_tri(f: float, A, t0, T) -> complex:
    """X(f) = A·T·sinc²(f·T)·e^{−j2πf·t0} (Λ = Π ∗ Π normalizado)."""
    s = sinc(f * float(_Q(T)))
    return complex(float(_Q(A)) * float(_Q(T)) * s * s, 0.0) \
        * cmath.exp(-1j * 2 * math.pi * f * float(_Q(t0)))


def tf_exp(f: float, A, t0, T) -> complex:
    """X(f) = A·T/(1 + j2πfT)·e^{−j2πf·t0} (causal)."""
    A, T = float(_Q(A)), float(_Q(T))
    return (A * T / (1 + 1j * 2 * math.pi * f * T)) \
        * cmath.exp(-1j * 2 * math.pi * f * float(_Q(t0)))


def biblioteca(pulsos: list[dict], trace: Trace | None = None) -> dict:
    """Energía e integral de una suma de pulsos + su TF en f = 0.

    Cada pulso: {"tipo": "rect"|"tri"|"exp", "A", "t0", "T"} con T = ancho
    (rect), semi-ancho (tri) o constante de tiempo (exp).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.biblioteca",
                 "pulsos → integral y energía por fórmulas cerradas; TF por la tabla",
                 why="cada pulso básico tiene su integral, su energía y su TF "
                     "en forma cerrada (§4.15, fila 1); la tabla es el método "
                     "directo y la cuadratura fina el segundo camino")
    if not pulsos:
        raise _error("BAD_INPUT", "faltan los pulsos de la señal")
    E = Fraction(0)
    S = Fraction(0)
    for p in pulsos:
        tipo = p.get("tipo", "rect")
        A, t0, T = _Q(p.get("A", 1)), _Q(p.get("t0", 0)), _Q(p.get("T", 1))
        if not T > 0:
            raise _error("BAD_INPUT", f"pulso {tipo}: se necesita T > 0")
        trace.hipotesis(f"sen.pulso_{tipo}", f"T = {_fmt_q(T)} > 0",
                        "cumple" if T > 0 else "falla")
        if tipo == "rect":
            S += integral_rect(A, T)
            E += energia_rect(A, T)
        elif tipo == "tri":
            S += integral_tri(A, T)
            E += energia_tri(A, T)
        elif tipo == "exp":
            S += integral_exp(A, T)
            E += energia_exp(A, T)
        else:
            raise _error("BAD_INPUT", f"pulso desconocido: {tipo} (rect, tri, exp)")
        trace.regla("sen.biblioteca_pulso",
                    f"{tipo} A={_fmt_q(A)} t0={_fmt_q(t0)} T={_fmt_q(T)}: "
                    f"∫ = {_fmt_q(S)}, E parcial = {_fmt_q(E)}",
                    why="se suma pulso a pulso; los soportes disjuntos no se "
                        "exigen: la energía cruzada se avisa abajo")
    # segundo camino: cuadratura fina de la suma de pulsos
    segs: list[Segmento] = []
    for p in pulsos:
        tipo = p.get("tipo", "rect")
        A, t0, T = _Q(p.get("A", 1)), _Q(p.get("t0", 0)), _Q(p.get("T", 1))
        if tipo == "rect":
            segs.append(rect(t0 - T / 2, t0 + T / 2, A))
        elif tipo == "tri":
            segs.extend(tri(t0, T, A))
        else:
            segs.append(exp_causal(t0, T, A))
    # soportes: rect [t0 ± T/2], tri [t0 ± T], exp [t0, ∞)
    soportes = []
    for p in pulsos:
        tipo = p.get("tipo", "rect")
        t0, T = float(_Q(p.get("t0", 0))), float(_Q(p.get("T", 1)))
        soportes.append((t0 - T / 2, t0 + T / 2) if tipo == "rect" else
                        (t0 - T, t0 + T) if tipo == "tri" else (t0, math.inf))
    solapan = any(max(u[0], v[0]) < min(u[1], v[1])
                  for i, u in enumerate(soportes) for v in soportes[i + 1:])
    # cuadratura de Gauss-Legendre (5 nodos, solo interiores) entre puntos de
    # ruptura: exacta para x² de pulsos lineales y sin evaluar en los saltos
    cortes = set()
    for sg in segs:
        cortes.add(float(sg.a))
        if sg.b is not None:
            cortes.add(float(sg.b))
    for p, sop in zip(pulsos, soportes):
        if sop[1] == math.inf:
            T = float(_Q(p.get("T", 1)))
            cortes.update(sop[0] + k * T / 4 for k in range(1, 161))   # e^(−80) despreciable
    cortes = sorted(cortes)
    nodos = ((0.0, 128 / 225), (0.5384693101056831, 0.4786286704993665),
             (-0.5384693101056831, 0.4786286704993665),
             (0.9061798459386640, 0.2369268850561891),
             (-0.9061798459386640, 0.2369268850561891))
    num_E = num_S = 0.0
    for u, v in zip(cortes, cortes[1:]):
        c, r = (u + v) / 2, (v - u) / 2
        for x, w in nodos:
            val = _eval_senal(segs, c + r * x)
            num_E += w * r * val * val
            num_S += w * r * val
    if abs(num_S - float(S)) > 1e-7 * max(1.0, abs(float(S))):
        raise _error("DISCREPANT", f"∫x por tabla {float(S):.9g} ≠ cuadratura {num_S:.9g}")
    if solapan:
        # con solape la energía NO es la suma de energías: falta el término
        # cruzado 2∫xᵢxⱼ. Se da la de la cuadratura, que sí lo incluye.
        trace.aviso("sen.solape",
                    f"los pulsos se solapan: la suma de energías {float(E):.6g} "
                    f"omite la energía cruzada; E = ∫x² = {num_E:.9g} (cuadratura)")
        E = num_E
    elif abs(num_E - float(E)) > 1e-7 * max(1.0, abs(float(E))):
        raise _error("DISCREPANT", f"E por tabla {float(E):.9g} ≠ cuadratura {num_E:.9g}")
    trace.verificacion("sen.biblioteca_cuadratura",
                       f"E = {_fmt_q(E) if isinstance(E, Fraction) else f'{E:.9g}'}, "
                       f"∫ = {_fmt_q(S)}"
                       + (" (con solape: E por cuadratura)" if solapan
                          else ", tabla y cuadratura coinciden"))
    return {"integral": S, "energia": E, "solapan": solapan}


def transforma_eje(pulso: dict, a, b, trace: Trace | None = None) -> dict:
    """y(t) = x(a·t − b): nuevo centro y ancho del pulso (a ≠ 0)."""
    trace = trace if trace is not None else Trace()
    A, t0, T = _Q(pulso.get("A", 1)), _Q(pulso.get("t0", 0)), _Q(pulso.get("T", 1))
    a, b = _Q(a), _Q(b)
    if a == 0:
        raise _error("BAD_INPUT", "transformación del eje con a = 0: no es invertible")
    trace.metodo("sen.eje", "y(t) = x(a·t − b): el centro va a (t0 + b)/a "
                 "y el ancho se divide por |a|",
                 why="un cambio de variable afín mueve el centro y escala el "
                     "ancho; es la regla de la fila 1 de §4.15")
    trace.hipotesis("sen.eje_a", f"a = {_fmt_q(a)} ≠ 0", "cumple")
    out = dict(pulso)
    out["t0"] = (t0 + b) / a
    out["T"] = T / abs(a)
    trace.regla("sen.eje_resultado",
                f"t0: {_fmt_q(t0)} → {_fmt_q(out['t0'])}; T: {_fmt_q(T)} → {_fmt_q(out['T'])}",
                why="sustitución u = a·t − b")
    # segundo camino: la energía escala con 1/|a| (E_desp = E_antes/|a|)
    e_antes = biblioteca([pulso], Trace())["energia"]
    e_desp = biblioteca([out], Trace())["energia"]
    if e_antes != e_desp * abs(a):
        raise _error("DISCREPANT", "la energía no escala como E/|a|")
    trace.verificacion("sen.eje_energia", f"E/|a| = {_fmt_q(e_desp)}")
    return out


# ---------------------------------------------------------------------------
# convolución analógica por tramos (§4.15, fila 2)
# ---------------------------------------------------------------------------

def _a_fracciones(trozos: list) -> list[Segmento]:
    """Trozos constantes [[a, b, v], …] como segmentos."""
    segs = []
    for a, b, v in trozos:
        segs.append(rect(a, b, v))
    return segs


def _eval_conv_pc(x: list[Segmento], h: list[Segmento], t: Fraction) -> Fraction:
    """y(t) = ∫x(τ)h(t−τ)dτ exacto para trozos constantes."""
    total = Fraction(0)
    for s1 in x:
        for s2 in h:
            lo = max(s1.a, t - s2.b)
            hi = min(s1.b, t - s2.a)
            if hi > lo:
                total += s1.c0 * s2.c0 * (hi - lo)
    return total


def _eval_conv_general(x: list[Segmento], h: list[Segmento], t: float) -> float:
    """Evaluación numérica fina de y(t) = ∫x(u)·h(t−u)du (segundo camino).

    Pareja a pareja de trozos: el integrando es suave dentro del solape
    [max(a₁, t−b₂), min(b₁, t−a₂)], y Gauss-Legendre compuesta (5 nodos, paso ≤ T/4
    de la exponencial más rápida) da ~1e-12. La versión anterior, punto medio con
    1200 celdas sobre todo el soporte, erraba en la tercera cifra."""
    xs = [sg for sg in x if isinstance(sg, Segmento)]
    hs = [sg for sg in h if isinstance(sg, Segmento)]
    nodos = ((0.0, 128 / 225), (0.5384693101056831, 0.4786286704993665),
             (-0.5384693101056831, 0.4786286704993665),
             (0.9061798459386640, 0.2369268850561891),
             (-0.9061798459386640, 0.2369268850561891))
    escala = [abs(1 / float(sg.r)) for sg in xs + hs if sg.r not in (None, 0)]
    paso_max = min(escala) / 4 if escala else None
    total = 0.0
    for s1 in xs:
        for s2 in hs:
            lo = max(v for v in (float(s1.a) if s1.a is not None else -math.inf,
                                 t - float(s2.b) if s2.b is not None else -math.inf))
            hi = min(v for v in (float(s1.b) if s1.b is not None else math.inf,
                                 t - float(s2.a) if s2.a is not None else math.inf))
            if not hi > lo or math.isinf(lo) or math.isinf(hi):
                continue
            n = 4 if paso_max is None else max(4, min(4000, int(math.ceil((hi - lo) / paso_max))))
            ancho = (hi - lo) / n
            for k in range(n):
                c, r = lo + (k + 0.5) * ancho, ancho / 2
                for z, w in nodos:
                    u = c + r * z
                    total += w * r * s1.eval(u) * s2.eval(t - u)
    return total


def _int_poly_exp(coef: list[Fraction], k: float, lo: float, hi: float) -> float:
    """∫_{lo}^{hi} (Σ coef[m] τ^m) e^{kτ} dτ (numérico-estable para el 2.º camino)."""
    n = 400
    h = (hi - lo) / n
    if h <= 0:
        return 0.0
    s = 0.0
    for i in range(n):
        tau = lo + (i + 0.5) * h
        p = sum(float(c) * tau**m for m, c in enumerate(coef))
        s += p * math.exp(k * tau)
    return s * h


def convolucion(x: list[Segmento], h: list[Segmento],
                trace: Trace | None = None) -> dict:
    """y = x ∗ h por puntos de ruptura = sumas de extremos (§4.15, fila 2).

    Acepta trozos constantes, triangulares (lineales) y exponenciales
    causales, además de deltas {"delta": A, "t0"}. Devuelve rupturas,
    tramos con su expresión, integral, duración y continuidad en rupturas.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conv",
                 "reflejar y desplazar h(t−λ); rupturas = sumas de extremos; "
                 "integrar por intervalo; continuidad en las rupturas",
                 why="es el método de §4.15 para pulsos y exponenciales: los "
                     "extremos de los trozos fijan dónde cambia la fórmula, y "
                     "dentro de cada intervalo la integral es elemental")
    deltas_x = [s for s in x if isinstance(s, dict) and "delta" in s]
    deltas_h = [s for s in h if isinstance(s, dict) and "delta" in s]
    xs = [s for s in x if isinstance(s, Segmento)]
    hs = [s for s in h if isinstance(s, Segmento)]
    for s in xs + hs:
        if s.b is not None and not s.b > s.a:
            raise _error("BAD_INPUT", "trozo con b ≤ a")
    trace.hipotesis("sen.conv_soporte",
                    "soporte compacto o h ∈ L¹ (exponencial causal)",
                    "cumple")
    # deltas: desplazan y escalan
    for d in deltas_x + deltas_h:
        A, t0 = _Q(d.get("delta", 1)), _Q(d.get("t0", 0))
        trace.regla("sen.conv_delta", f"δ: A = {_fmt_q(A)} en t0 = {_fmt_q(t0)}",
                    why="f ∗ δ(t−t0) = f(t−t0); el área multiplica")
    des_x = sum(_Q(d.get("t0", 0)) for d in deltas_x)
    des_h = sum(_Q(d.get("t0", 0)) for d in deltas_h)
    des = des_x + des_h
    esc = Fraction(1)
    for d in deltas_x + deltas_h:
        esc *= _Q(d.get("delta", 1))
    if not xs and not hs:
        # solo deltas: una delta de área esc en des
        trace.verificacion("sen.conv_deltas", f"y = {esc}·δ(t−{des})")
        return {"rupturas": [des], "tramos": [], "integral": esc,
                "desplazamiento_deltas": des, "escala_deltas": esc,
                "verificado": True}
    if not xs or not hs:
        # un lado es solo deltas: el otro lado desplazado y escalado
        lado = hs if xs == [] else xs
        movidos = [Segmento(s.a + des if s.a is not None else None,
                            s.b + des if s.b is not None else None,
                            s.c0 * esc, s.c1 * esc, s.r, s.origen + des
                            if s.origen is not None else None)
                   for s in lado]
        rupturas = sorted({p for s in movidos for p in (s.a, s.b) if p is not None})
        tramos = [{"a": movidos[i].a, "b": movidos[i].b,
                   "expr": movidos[i].texto(), "ya": None, "yb": None, "ym": None}
                  for i in range(len(movidos)) if movidos[i].b is not None]
        int_y = _int_exacta(lado, deltas_x + deltas_h)
        trace.verificacion("sen.conv_delta_lado", f"∫y = ∫lado·ΠA = {_fmt_q(int_y)}")
        return {"rupturas": rupturas, "tramos": tramos, "integral": int_y,
                "desplazamiento_deltas": des, "escala_deltas": esc,
                "verificado": True}
    base_x, base_h = xs, hs
    # rupturas finitas = sumas de extremos finitos
    rup = set()
    for s1 in base_x:
        for s2 in base_h:
            for u in (s1.a, s1.b):
                for v in (s2.a, s2.b):
                    if u is not None and v is not None:
                        rup.add(u + v)
    rupturas = sorted(rup)
    rupturas = [r + des for r in rupturas]
    # valores exactos en puntos medios (trozos constantes → lineal a trozos)
    solo_const = all(s.c1 == 0 and (s.r is None or s.r == 0) for s in base_x + base_h)
    tramos = []
    if rupturas:
        if solo_const:
            for i in range(len(rupturas) - 1):
                a, b = rupturas[i], rupturas[i + 1]
                if b <= a:
                    continue
                ya = _eval_conv_pc(base_x, base_h, a) * esc
                yb = _eval_conv_pc(base_x, base_h, b) * esc
                ym = _eval_conv_pc(base_x, base_h, (a + b) / 2) * esc
                if ya == yb:
                    expr = f"{_fmt_q(ya)}"
                else:
                    p1 = (yb - ya) / (b - a)
                    p0 = ya - p1 * a
                    mag = "t" if abs(p1) == 1 else f"{_fmt_q(abs(p1))}·t"
                    expr = ((("−" if p1 < 0 else "") + mag) if p0 == 0 else
                            f"{_fmt_q(p0)} {'−' if p1 < 0 else '+'} {mag}")
                tramos.append({"a": a, "b": b, "expr": expr,
                               "ya": ya, "yb": yb, "ym": ym})
        else:
            exactos = _conv_exacta(base_x, base_h, rupturas, des, esc)
            if exactos is not None:
                tramos = exactos
                trace.regla("sen.conv_exacta",
                            "en cada intervalo: Σ ∫ x(u)·h(t−u) du con los límites del solape",
                            why="dentro de un intervalo entre rupturas los límites no cambian "
                                "de fórmula: la integral es elemental y sale exacta")
            else:
                for i in range(len(rupturas) - 1):
                    a, b = rupturas[i], rupturas[i + 1]
                    if b <= a:
                        continue
                    m = (float(a) + float(b)) / 2
                    ym = _eval_conv_general(base_x, base_h, m - float(des)) * float(esc)
                    tramos.append({"a": a, "b": b, "expr": f"y({m:.4g}) = {ym:.6g}",
                                   "ya": None, "yb": None, "ym": ym})
    # integral y duración: ∫y = ∫x·∫h (exacta por familias)
    int_x = _int_exacta(base_x, deltas_x)
    int_h = _int_exacta(base_h, deltas_h)
    int_y = int_x * int_h
    # segundo camino: ∫y por cuadratura de la evaluadora + duración
    if tramos and solo_const:
        num = sum(float(t["ym"]) * float(t["b"] - t["a"]) for t in tramos)
        if abs(num - float(int_y)) > 1e-6 * max(1.0, abs(float(int_y))):
            raise _error("DISCREPANT",
                         f"∫y = {float(int_y):.6g} frente a cuadratura {num:.6g}")
    elif tramos and all(t.get("exacto") for t in tramos):
        pass        # tramos exactos: ya contrastados punto a punto con la evaluadora
    elif tramos:
        # malla fina en el soporte finito + cuadratura de la cola exponencial
        rmin, rmax = float(min(rupturas)), float(max(rupturas))
        n_fin = 3000
        paso = (rmax - rmin) / n_fin if rmax > rmin else 0.0
        num = sum(_eval_conv_general(base_x, base_h,
                                     rmin + (k + 0.5) * paso - float(des)) * float(esc)
                  for k in range(n_fin)) * paso if paso > 0 else 0.0
        # cola exponencial hasta el infinito (los extremos finitos no la ven)
        colas = [s for s in base_x + base_h if s.b is None]
        if colas:
            T_cola = max(float(-Fraction(1, 1) / s.r) for s in colas
                         if s.r is not None and s.r != 0)
            n_cola = 3000
            ancho = 15 * T_cola
            num += sum(_eval_conv_general(base_x, base_h,
                                         rmax + (k + 0.5) * ancho / n_cola - float(des))
                       * float(esc) for k in range(n_cola)) * ancho / n_cola
            tramos.append({"a": max(rupturas), "b": None,
                           "expr": f"cola exponencial (T = {T_cola:.4g})",
                           "ya": None, "yb": None, "ym": None})
        if abs(num - float(int_y)) > 2e-3 * max(1.0, abs(float(int_y))):
            raise _error("DISCREPANT",
                         f"∫y numérica {num:.6g} frente a ∫x·∫h = {float(int_y):.6g}")
    exactos_ok = bool(tramos) and all(t.get("exacto") for t in tramos)
    verificado = solo_const or exactos_ok
    trace.verificacion("sen.conv_integral",
                       f"∫y = ∫x·∫h = {_fmt_q(int_y)}"
                       + ("" if solo_const else
                          "; tramos exactos contrastados con la evaluadora numérica" if exactos_ok
                          else " (solo numérico en tramos no constantes)"))
    return {"rupturas": rupturas, "tramos": tramos, "integral": int_y,
            "desplazamiento_deltas": des, "escala_deltas": esc,
            "verificado": verificado}


def _q_txt(q: Fraction) -> str:
    q = Fraction(q)
    return f"({q.numerator}/{q.denominator})"


def _seg_txt(sg: "Segmento", var: str) -> str:
    """El trozo como expresión en ``var`` (``u`` o ``t-u``) para el integrador."""
    if sg.r is not None and sg.r != 0:
        o = sg.origen if sg.origen is not None else Fraction(0)
        return (f"({_q_txt(sg.c0)} + {_q_txt(sg.c1)}*(({var}) - {_q_txt(o)}))"
                f"*exp({_q_txt(sg.r)}*(({var}) - {_q_txt(o)}))")
    return f"({_q_txt(sg.c0)} + {_q_txt(sg.c1)}*({var}))"


def _producto_txt(s1: "Segmento", s2: "Segmento") -> str:
    """x(u)·h(t−u) con UNA sola exponencial: e^{r₁(u−o₁)}·e^{r₂(t−u−o₂)} se escribe
    e^{(r₁−r₂)u + r₂t − r₁o₁ − r₂o₂}, que el integrador sí sabe integrar en u."""
    def pol(sg, var):
        o = sg.origen if (sg.r not in (None, 0) and sg.origen is not None) else Fraction(0)
        if sg.r not in (None, 0):
            return f"({_q_txt(sg.c0)} + {_q_txt(sg.c1)}*(({var}) - {_q_txt(o)}))"
        return f"({_q_txt(sg.c0)} + {_q_txt(sg.c1)}*({var}))"
    r1 = s1.r if s1.r not in (None, 0) else Fraction(0)
    r2 = s2.r if s2.r not in (None, 0) else Fraction(0)
    o1 = s1.origen if (r1 and s1.origen is not None) else Fraction(0)
    o2 = s2.origen if (r2 and s2.origen is not None) else Fraction(0)
    base = f"{pol(s1, 'u')}*{pol(s2, 't - u')}"
    if r1 == 0 and r2 == 0:
        return base
    return (f"{base}*exp({_q_txt(r1 - r2)}*u + {_q_txt(r2)}*t + "
            f"{_q_txt(-r1 * o1 - r2 * o2)})")


def _conv_exacta(base_x, base_h, rupturas, des, esc):
    """Tramos exactos de x ∗ h: en cada intervalo, Σ ∫ x(u)·h(t−u) du con límites
    constantes o t − c (fijos dentro del intervalo). None si algo no se integra."""
    import importlib
    C_ = importlib.import_module("academic_core.domain.engineering.mathlab.contract")
    mx_ = importlib.import_module("academic_core.domain.engineering.mathlab.mvexpr")
    puntos = list(rupturas)
    con_cola = any(sg.b is None for sg in base_x + base_h)
    intervalos = [(puntos[i], puntos[i + 1]) for i in range(len(puntos) - 1)
                  if puntos[i + 1] > puntos[i]]
    if con_cola:
        intervalos.append((puntos[-1], None))
    tramos = []
    for a, b in intervalos:
        # el intervalo en el tiempo de la convolución sin deltas
        a0 = a - des
        b0 = None if b is None else b - des
        m = (a0 + b0) / 2 if b0 is not None else a0 + 1
        piezas = []
        for s1 in base_x:
            for s2 in base_h:
                inf1 = s1.a if s1.a is not None else None
                sup1 = s1.b
                # u ∈ [s1.a, s1.b) ∩ (m − s2.b, m − s2.a]
                lo_c = [] if inf1 is None else [(inf1, _q_txt(inf1))]
                if s2.b is not None:
                    lo_c.append((m - s2.b, f"t - {_q_txt(s2.b)}"))
                hi_c = [] if sup1 is None else [(sup1, _q_txt(sup1))]
                if s2.a is not None:
                    hi_c.append((m - s2.a, f"t - {_q_txt(s2.a)}"))
                if not lo_c or not hi_c:
                    return None
                lo = max(lo_c, key=lambda z: z[0])
                hi = min(hi_c, key=lambda z: z[0])
                if not hi[0] > lo[0]:
                    continue
                f = _producto_txt(s1, s2)
                try:
                    r = C_.calcular(C_.Peticion("integrar", {"integrando": f, "var": "u",
                                                             "desde": lo[1], "hasta": hi[1]}))
                except Exception:
                    return None
                if r.sello.verdict != "verificado" or not isinstance(r.exacto_expr, mx_.Expr):
                    return None
                piezas.append(r.exacto_expr)
        if not piezas:
            expr = mx_.Num(Fraction(0))
        else:
            expr = piezas[0]
            for pz in piezas[1:]:
                expr = mx_.Add(expr, pz)
        if esc != 1:
            expr = mx_.Mul(mx_.Num(esc), expr)
        if des != 0:
            expr = mx_.substitute(expr, "t", mx_.parse(f"t - {_q_txt(des)}"))
        try:
            from academic_core.domain.engineering.mathlab.calculators import _presentable
            expr = _presentable(expr, Trace(), profunda=True)
        except Exception:
            pass
        tramos.append({"a": a, "b": b, "expr": mx_.pretty(expr), "_expr": expr,
                       "ya": None, "yb": None, "ym": None, "exacto": True})
    # segundo camino: la evaluadora numérica independiente en 3 puntos por tramo
    for tr in tramos:
        a, b = float(tr["a"]), (float(tr["b"]) if tr["b"] is not None else float(tr["a"]) + 5)
        for frac in (0.17, 0.5, 0.83):
            t = a + (b - a) * frac
            num = _eval_conv_general(base_x, base_h, t - float(des)) * float(esc)
            try:
                ex = complex(mx_.evaluate(tr["_expr"], {"t": t}))
            except Exception:
                return None
            if abs(ex - num) > 1e-6 * max(1.0, abs(num)):
                return None
        tr.pop("_expr")
    return tramos


def _int_seg_exacta(s: Segmento) -> Fraction:
    """∫s exacta: constante, lineal o exponencial causal."""
    if s.r is not None and s.r != 0:
        if not s.r < 0:
            raise _no("cola no integrable: se necesita exponencial decreciente")
        T = -Fraction(1, 1) / s.r
        return s.c0 * T
    if s.b is None:
        raise _no("cola polinómica no integrable")
    if s.c1 == 0:
        return s.c0 * (s.b - s.a)
    return s.c0 * (s.b - s.a) + s.c1 * (s.b * s.b - s.a * s.a) / 2


def _int_exacta(segs: list[Segmento], deltas: list) -> Fraction:
    tot = sum((_int_seg_exacta(s) for s in segs), Fraction(0)) \
        if segs else Fraction(1)
    for d in deltas:
        tot *= _Q(d.get("delta", 1))
    return tot


def _exp_cuadratura(s: Segmento) -> Fraction:
    """∫_{a}^{∞} e^{r·t} dt con r < 0, como fracción de e^{r·a}/(−r)."""
    # exacto: e^{r·a}/(−r); se devuelve como Fraction solo si r·a es 0;
    # en general se integra numéricamente fino y se devuelve exacto aparte.
    a = float(s.a)
    r = float(s.r)
    n = 4000
    T = 12 / abs(r)
    h = T / n
    return Fraction(sum(math.exp(r * (a + (k + 0.5) * h)) for k in range(n)) * h
                    ).limit_denominator(10**9)


def _poly_cuadratura(s: Segmento) -> Fraction:
    a, b = float(s.a), float(s.b)
    n = 2000
    h = (b - a) / n
    return Fraction(sum(float(s.c0) + float(s.c1) * (a + (k + 0.5) * h)
                        for k in range(n)) * h).limit_denominator(10**9)


def ventana_movil(senal: list[Segmento], T, trace: Trace | None = None) -> dict:
    """Ventana móvil: y = x ∗ (1/T)·Π_T (media en ventana de ancho T)."""
    trace = trace if trace is not None else Trace()
    T = _Q(T)
    if not T > 0:
        raise _error("BAD_INPUT", "ventana móvil con T ≤ 0")
    trace.metodo("sen.ventana", "la media en ventana es una convolución con "
                 "un rectangular normalizado",
                 why="§4.15 fila 2: la ventana móvil es el caso de h más "
                     "sencillo, y su integral es la de x")
    h = [Segmento(-T / 2, T / 2, Fraction(1, 1) / T, Fraction(0), None)]
    return convolucion(senal, h, trace)


# ---------------------------------------------------------------------------
# convolución digital y regímenes (§4.15, fila 3)
# ---------------------------------------------------------------------------

def conv_lineal(x: list, h: list, trace: Trace | None = None) -> dict:
    """y[n] = Σ x[k]·h[n−k], longitud L1+L2−1, con sus tres tramos."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conv_digital", "tabla de solapes: longitud L1+L2−1 con "
                 "transitorio de subida, régimen y transitorio de bajada",
                 why="la definición discreta es finita y exacta en ℚ; la vía z "
                     "y la DFT con N ≥ L1+L2−1 son los segundos caminos")
    xs = [_Q(v) for v in x]
    hs = [_Q(v) for v in h]
    if not xs or not hs:
        raise _error("BAD_INPUT", "convolución digital con una secuencia vacía")
    trace.hipotesis("sen.dig_longitud", f"L1 = {len(xs)}, L2 = {len(hs)}",
                    "cumple")
    y = [Fraction(0)] * (len(xs) + len(hs) - 1)
    for i, a in enumerate(xs):
        for j, b in enumerate(hs):
            y[i + j] += a * b
    L1, L2 = len(xs), len(hs)
    m = min(L1, L2)
    tramos = {"subida": y[:m - 1] if m > 1 else [],
              "regimen": y[m - 1:len(y) - m + 1],
              "bajada": y[len(y) - m + 1:] if m > 1 else []}
    # segundo camino: Σy = Σx·Σh + DFT con N ≥ L1+L2−1
    if sum(y) != sum(xs) * sum(hs):
        raise _error("DISCREPANT", "Σy ≠ Σx·Σh")
    N = len(y)
    X = dft([float(v) for v in xs], N)
    H = dft([float(v) for v in hs], N)
    Y = dft([float(v) for v in y], N)
    for k in range(N):
        if abs(Y[k] - X[k] * H[k]) > 1e-6 * max(1.0, abs(Y[k])):
            raise _error("DISCREPANT", f"DFT: Y[{k}] ≠ X[{k}]·H[{k}]")
    trace.verificacion("sen.dig_dft", f"Σy = {_fmt_q(sum(y))}; DFT con N = {N} conforme")
    return {"y": y, "tramos": tramos}


def salida_exp(a, x: list, trace: Trace | None = None) -> dict:
    """Régimen de y[n] = a·y[n−1] + x[n] con |a| < 1 (suma geométrica)."""
    trace = trace if trace is not None else Trace()
    a = _Q(a)
    trace.hipotesis("sen.regimen_a", f"|a| = {abs(float(a)):.4g} < 1",
                    "cumple" if abs(float(a)) < 1 else "falla")
    if not abs(float(a)) < 1:
        raise _error("BAD_INPUT", "régimen con |a| ≥ 1: la suma infinita no converge")
    trace.metodo("sen.regimen", "tres tramos con sumas geométricas: antes, "
                 "transitorio y régimen",
                 why="la recursión de primer orden se cierra con la suma "
                     "geométrica cuando |a| < 1 (§4.15, fila 3)")
    xs = [_Q(v) for v in x]
    if not xs:
        raise _error("BAD_INPUT", "falta la entrada x[n]")
    y, estado = [], Fraction(0)
    for v in xs:
        estado = a * estado + v
        y.append(estado)
    # segundo camino (exacto): la convolución con la respuesta al impulso aⁿ
    if any(y[n] != sum(a ** (n - k) * xs[k] for k in range(n + 1)) for n in range(len(xs))):
        raise _error("DISCREPANT", "la recursión no coincide con y = h * x, h[n] = aⁿ")
    trace.verificacion("sen.regimen_recurrencia",
                       f"último: y = a·y + x = {_fmt_q(y[-1])}")
    return {"y": y}


# ---------------------------------------------------------------------------
# periódicas por señal base (§4.15, fila 4)
# ---------------------------------------------------------------------------

def periodo_comun(T1, T2) -> Fraction:
    """Periodo de la suma de dos periódicas: mcm de T1 y T2 racionales.

    Con T1 = p1/q1 y T2 = p2/q2 reducidas: mcm = mcm(p1,p2)/mcd(q1,q2).
    """
    from math import gcd
    a, b = _Q(T1), _Q(T2)
    if a <= 0 or b <= 0:
        raise _error("BAD_INPUT", "periodos no positivos")
    num = abs(a.numerator * b.numerator) // gcd(abs(a.numerator), abs(b.numerator))
    den = gcd(a.denominator, b.denominator)
    return Fraction(num, den)


def ck_base(base: list[dict], T0, K: int = 5,
            trace: Trace | None = None) -> dict:
    """c_k = (1/T0)·X_b(k/T0) por el método de la señal base (§4.15, fila 4).

    ``base``: pulsos de un periodo como en :func:`biblioteca` (con t0 dentro
    del periodo). Devuelve k, c_k (complejos), potencia y armónicos nulos.
    """
    trace = trace if trace is not None else Trace()
    T0 = _Q(T0)
    if not T0 > 0:
        raise _error("BAD_INPUT", "periodo no positivo")
    if not base:
        raise _error("BAD_INPUT", "señal base vacía")
    trace.metodo("sen.periodica",
                 "c_k = (1/T0)·X_b(k/T0): TF del pulso base en vez de la "
                 "integral de periodo",
                 why="cuando los pulsos son básicos (Π, Λ, exponencial), su TF "
                     "es cerrada y el método de la señal base evita integrar "
                     "el periodo (§4.15, fila 4)")
    trace.hipotesis("sen.periodica_base", "pulsos sin solape entre periodos",
                    "cumple (se comprueba por los extremos)")
    for p in base:
        t0, T = _Q(p.get("t0", 0)), _Q(p.get("T", 1))
        if abs(float(t0)) + float(T) / (2 if p.get("tipo") == "rect" else 1) > float(T0) / 2 + 1e-9 \
                and p.get("tipo") in ("rect", "tri"):
            trace.aviso("sen.periodica_solape",
                        f"el pulso en t0 = {_fmt_q(t0)} puede solaparse entre periodos")
    f0 = 1 / float(T0)
    cks = {}
    for k in range(-K, K + 1):
        f = k * f0
        Xb = 0j
        for p in base:
            tipo = p.get("tipo", "rect")
            A, t0, T = p.get("A", 1), p.get("t0", 0), p.get("T", 1)
            if tipo == "rect":
                Xb += tf_rect(f, A, t0, T)
            elif tipo == "tri":
                Xb += tf_tri(f, A, t0, T)
            elif tipo == "exp":
                Xb += tf_exp(f, A, t0, T)
            else:
                raise _error("BAD_INPUT", f"pulso base desconocido: {tipo}")
        cks[k] = Xb / float(T0)
    P = sum(abs(c) ** 2 for c in cks.values())
    nulos = [k for k, c in cks.items() if abs(c) < 1e-9 * max(1.0, abs(cks.get(0, 1.0)))]
    # segundo camino: Parseval P = (1/T0)∫|x|² por cuadratura fina
    segs: list[Segmento] = []
    for p in base:
        tipo = p.get("tipo", "rect")
        A, t0, T = _Q(p.get("A", 1)), _Q(p.get("t0", 0)), _Q(p.get("T", 1))
        if tipo == "rect":
            segs.append(rect(t0 - T / 2, t0 + T / 2, A))
        elif tipo == "tri":
            segs.extend(tri(t0, T, A))
        else:
            segs.append(exp_causal(t0, T, A))
    n = 4000
    h = float(T0) / n
    t_ini = -float(T0) / 2
    pot_t = sum(_eval_senal(segs, t_ini + (i + 0.5) * h) ** 2 for i in range(n)) * h / float(T0)
    # la suma truncada a ±K subestima: se compara con tolerancia de cola
    if P > pot_t * (1 + 1e-6) + 1e-9:
        raise _error("DISCREPANT", f"Parseval: Σ|c_k|² = {P:.6g} > P_tiempo = {pot_t:.6g}")
    trace.verificacion("sen.periodica_parseval",
                       f"P = Σ|c_k|² = {P:.6g} ≤ P_tiempo = {pot_t:.6g} (cola fuera de ±{K})")
    return {"ck": cks, "potencia": P, "potencia_tiempo": pot_t, "nulos": nulos, "T0": T0}


# ---------------------------------------------------------------------------
# energía, potencia y Parseval (§4.15, fila 5)
# ---------------------------------------------------------------------------

def energia(senal: list[Segmento], trace: Trace | None = None) -> dict:
    """E = ∫|x|² por tramos, con Plancherel como segundo camino."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.energia", "E = ∫|x|² tramo a tramo (fórmulas de la biblioteca)",
                 why="la energía de pulsos es cerrada; la TF da el segundo "
                     "camino por Plancherel E = ∫|X|² (§4.15, fila 5)")
    E = Fraction(0)
    for s in senal:
        if s.r is not None and s.r != 0:
            if not s.r < 0:
                raise _no("energía de cola no integrable")
            T = -Fraction(1, 1) / s.r
            E += s.c0 * s.c0 * T / 2
        elif s.c1 == 0:
            E += s.c0 * s.c0 * (s.b - s.a)
        else:
            E += _energia_lineal_exacta(s)
    # segundo camino: cuadratura fina
    pts = _ruptura_principal([s for s in senal if s.b is not None])
    if pts:
        lo, hi = float(min(pts)), float(max(pts))
        if any(s.b is None for s in senal):
            hi = lo + 20
        n = 3000
        h = (hi - lo) / n
        num = sum(_eval_senal(senal, lo + (k + 0.5) * h) ** 2 for k in range(n)) * h
        if abs(num - float(E)) > 1e-4 * max(1.0, abs(float(E))):
            raise _error("DISCREPANT", f"E = {float(E):.6g} frente a {num:.6g}")
        trace.verificacion("sen.energia_cuadratura", f"E = {_fmt_q(E)}")
    return {"energia": E}


def _energia_lineal_exacta(s: Segmento) -> Fraction:
    """∫(c0+c1·t)² exacta en [a, b]."""
    a, b = s.a, s.b
    return (s.c0 * s.c0 * (b - a) + s.c0 * s.c1 * (b * b - a * a)
            + s.c1 * s.c1 * (b * b * b - a * a * a) / 3)


def _cuad_cuadrado(s: Segmento) -> Fraction:
    return _energia_lineal_exacta(s)


def clasificar(senal: list[Segmento], T0=None) -> str:
    """Energía finita, potencia finita o ninguna (§4.15, fila 5)."""
    egang = energia(senal)["energia"]
    ifegang = float(egang) < 1e18
    if any(s.b is None for s in senal):
        return "energia_finita" if ifegang else "ninguna"
    if T0 is not None:
        return "potencia_finita"
    return "energia_finita" if ifegang else "ninguna"


def potencia_sinusoide(A, trace: Trace | None = None) -> Fraction:
    """P = A²/2 de una sinusoide de amplitud A."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.potencia_sinusoide", "P = (1/T)∫A²cos²(ωt)dt = A²/2",
                 why="la media de cos² en un periodo es ½")
    A = _Q(A)
    P = A * A / 2
    # segundo camino: la media de A²cos² en un periodo por cuadratura (16 puntos
    # equiespaciados integran cos² exactamente)
    media = sum(float(A) ** 2 * math.cos(2 * math.pi * k / 16) ** 2 for k in range(16)) / 16
    if abs(media - float(P)) > 1e-12 * max(1.0, float(P)):
        raise _error("DISCREPANT", "la media de A²cos² no es A²/2")
    trace.verificacion("sen.potencia_media", f"P = A²/2 = {P}")
    return P


def energia_eco(E_x, a, trace: Trace | None = None) -> Fraction:
    """E_y = E_x·(1+a²) para y = x + a·x(t−T) sin solape (§4.15, fila 5)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.energia_eco", "E_y = ∫(x + a·x_T)² = E_x + a²E_x + 2a·r_x(T)",
                 why="desarrollar el cuadrado: el término cruzado es la autocorrelación "
                     "en el retardo")
    trace.hipotesis("sen.eco_sin_solape", "x y su copia retardada no se solapan: r_x(T) = 0",
                    "supuesto (con solape hay que sumar 2a·r_x(T))")
    Ex, a = _Q(E_x), _Q(a)
    if Ex < 0:
        raise _error("BAD_INPUT", "E_x ≥ 0")
    E = Ex * (1 + a ** 2)
    trace.verificacion("sen.energia_eco_ok",
                       f"E_y = E_x·(1 + a²) = {E}, válido solo bajo la hipótesis de no solape")
    return E


# ---------------------------------------------------------------------------
# correlación y densidad espectral (§4.15, fila 6)
# ---------------------------------------------------------------------------

def correlacion_rect(A, T, taus: list[float] | None = None) -> dict:
    """r(τ) = A²·(T − |τ|) para |τ| < T (Π de ancho T)."""
    A, T = _Q(A), _Q(T)
    if taus is None:
        taus = [-float(T), -float(T) / 2, 0.0, float(T) / 2, float(T)]
    r = {}
    for tau in taus:
        t = float(tau)
        r[tau] = float(A * A) * max(0.0, float(T) - abs(t))
    E = float(A * A * T)
    if abs(r[0.0] - E) > 1e-9:
        raise _error("DISCREPANT", "r(0) ≠ E")
    for tau, v in r.items():
        if v > r[0.0] * (1 + 1e-9):
            raise _error("DISCREPANT", f"|r({tau})| > r(0) (Schwarz)")
    return {"r": r, "E": E}


def correlacion_exp(A, T, taus: list[float] | None = None) -> dict:
    """r(τ) = (A²T/2)·e^{−|τ|/T} (exponencial causal)."""
    A, T = _Q(A), _Q(T)
    if taus is None:
        taus = [0.0, float(T) / 2, float(T), 2 * float(T)]
    r = {t: float(A * A * T) / 2 * math.exp(-abs(float(t)) / float(T)) for t in taus}
    return {"r": r, "E": float(A * A * T) / 2}


def densidad_desde_tf(Xs: list[complex], trace: Trace | None = None) -> list[float]:
    """S_x = |X|² punto a punto (Wiener-Khinchin, §4.15 fila 6)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.densidad", "S_x(f) = |X(f)|² punto a punto",
                 why="la densidad de energía es el módulo al cuadrado de la TF: "
                     "Wiener-Khinchin determinista")
    S = [abs(X) ** 2 for X in Xs]
    if any(abs(s - (X * X.conjugate()).real) > 1e-12 * max(1.0, s) for s, X in zip(S, Xs)):
        raise _error("DISCREPANT", "|X|² ≠ X·X*")
    trace.verificacion("sen.densidad_ok", "S = X·X* ≥ 0 en cada punto")
    return S


def retardo_por_pico(r_xy: dict[float, float]) -> float:
    """Retardo τ del pico de r_yx (atenuación + retardo)."""
    return max(r_xy, key=lambda t: r_xy[t])


# ---------------------------------------------------------------------------
# DTFT (§4.15, fila 7)
# ---------------------------------------------------------------------------

def dtft_pulso(F: float, L: int) -> complex:
    """P_L(F) = sin(πLF)/sin(πF)·e^{−jπ(L−1)F}, máximo L en F = 0, ceros en k/L."""
    if L <= 0:
        raise _error("BAD_INPUT", "p_L con L ≤ 0")
    if F == 0.0 or abs(math.sin(math.pi * F)) < 1e-15:
        k = round(F)
        return complex(float(L), 0.0) * cmath.exp(-1j * math.pi * (L - 1) * k)
    return (math.sin(math.pi * L * F) / math.sin(math.pi * F)) \
        * cmath.exp(-1j * math.pi * (L - 1) * F)


def dtft_exp(F: float, a) -> complex:
    """aⁿu[n] → 1/(1 − a·e^{−j2πF}), |H|² = 1/(1+a²−2a·cos2πF)."""
    a = float(_Q(a))
    if not abs(a) < 1:
        raise _error("BAD_INPUT", "DTFT de aⁿu[n] con |a| ≥ 1: no sumable")
    return 1 / (1 - a * cmath.exp(-1j * 2 * math.pi * F))


def dtft_delta(F: float, n0: int) -> complex:
    """δ[n−n0] → e^{−j2πF·n0}."""
    return cmath.exp(-1j * 2 * math.pi * F * n0)


def modulo_cuadrado_exp(a, F: float) -> float:
    a = float(_Q(a))
    return 1 / (1 + a * a - 2 * a * math.cos(2 * math.pi * F))


def salida_sinusoides(A, B, F, H) -> dict:
    """Salida a A + B·cos(2πFn): cada raya por su H(F) (linealidad)."""
    trace_note = ("cada componente de frecuencia distinta sale con su "
                  "propio H(F); las potencias se suman por ortogonalidad")
    return {"nota": trace_note,
            "continuo": complex(A) * H(0.0),
            "cos": complex(B) * H(F)}


def comprobar_dtft(a, L: int, trace: Trace | None = None) -> dict:
    """Parseval Σ|x|² = ∫₀¹|X|²dF + hermiticidad (segundo camino, §4.15)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.dtft", "fórmula cerrada de P_L y de aⁿu[n]; la suma "
                 "truncada y la DFT con relleno largo verifican",
                 why="la DTFT de secuencias básicas es cerrada; Parseval y la "
                     "hermiticidad de secuencias reales son el control (§4.15)")
    n = 2000
    h = 1 / n
    E_f = sum(abs(dtft_pulso((k + 0.5) * h, L)) ** 2 for k in range(n)) * h
    if abs(E_f - L) > 1e-6 * L:
        raise _error("DISCREPANT", f"Parseval de p_{L}: {E_f:.6g} ≠ {L}")
    for F in (0.1, 0.25):
        if abs(dtft_pulso(-F, L) - dtft_pulso(F, L).conjugate()) > 1e-9:
            raise _error("DISCREPANT", "hermiticidad de p_L")
    trace.verificacion("sen.dtft_parseval", f"Σ|p_{L}|² = ∫|P_{L}|² = {L}")
    return {"parseval": E_f}


# ---------------------------------------------------------------------------
# DFT (§4.15, fila 8)
# ---------------------------------------------------------------------------

def dft(x: list[float], N: int | None = None) -> list[complex]:
    """X[k] = Σ x[n]·e^{−j2πkn/N} (definición, sin librerías)."""
    n0 = len(x)
    N = N or n0
    if N < n0:
        raise _error("BAD_INPUT", f"DFT con N = {N} < L = {n0}")
    xz = list(x) + [0.0] * (N - n0)
    return [sum(xz[n] * cmath.exp(-1j * 2 * math.pi * k * n / N) for n in range(N))
            for k in range(N)]


def idft(X: list[complex]) -> list[complex]:
    """x[n] = (1/N)·Σ X[k]·e^{+j2πkn/N}."""
    N = len(X)
    return [sum(X[k] * cmath.exp(1j * 2 * math.pi * k * n / N) for k in range(N)) / N
            for n in range(N)]


def conv_circular(x: list[float], h: list[float]) -> list[float]:
    """Convolución circular por DFT (igual longitud)."""
    N = max(len(x), len(h))
    X, H = dft(x, N), dft(h, N)
    return [round((idft([X[k] * H[k] for k in range(N)])[n]).real, 9) for n in range(N)]


def comprobar_dft(x: list[float], trace: Trace | None = None) -> dict:
    """X[0] = Σx, hermiticidad (x real) y Parseval (1/N)Σ|X|² = Σ|x|²."""
    trace = trace if trace is not None else Trace()
    N = len(x)
    X = dft(x)
    if abs(X[0].real - sum(x)) > 1e-9 or abs(X[0].imag) > 1e-9:
        raise _error("DISCREPANT", "X[0] ≠ Σx")
    for k in range(1, N):
        if abs(X[N - k] - X[k].conjugate()) > 1e-9:
            raise _error("DISCREPANT", "simetría hermítica X[N−k] = X*[k]")
    E_t = sum(v * v for v in x)
    E_f = sum(abs(Xk) ** 2 for Xk in X) / N
    if abs(E_t - E_f) > 1e-9 * max(1.0, abs(E_t)):
        raise _error("DISCREPANT", "Parseval de la DFT")
    trace.verificacion("sen.dft_parseval", f"Σ|x|² = (1/N)Σ|X|² = {E_t:.6g}")
    return {"X": X, "energia": E_t}


def lineal_vs_circular(x: list[float], h: list[float],
                       trace: Trace | None = None) -> dict:
    """Circular = lineal ⟺ N ≥ L1+L2−1 (§4.15, fila 8)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.dft_circular", "con N ≥ L1+L2−1 no hay solape temporal "
                 "(aliasing); con N menor, las primeras muestras se solapan",
                 why="es la condición de §4.15: el relleno de ceros hasta la "
                     "longitud lineal evita el aliasing temporal")
    L1, L2 = len(x), len(h)
    N = L1 + L2 - 1
    X, H = dft(x, N), dft(h, N)
    y_lin = [sum(x[i] * h[n - i] for i in range(max(0, n - L2 + 1), min(n + 1, L1)))
             for n in range(N)]
    y_dft = [idft([X[k] * H[k] for k in range(N)])[n].real for n in range(N)]
    for n in range(N):
        if abs(y_lin[n] - y_dft[n]) > 1e-9:
            raise _error("DISCREPANT", f"circular ≠ lineal en n = {n}")
    trace.verificacion("sen.dft_lineal", f"N = {N} ≥ {L1}+{L2}−1: coinciden")
    return {"N": N, "y": y_lin}


# ---------------------------------------------------------------------------
# eco, reverberación e inverso (§4.15, fila 9)
# ---------------------------------------------------------------------------

def eco_h(a, L: int, N: int | None = None) -> list:
    """h[n] = δ[n] + a·δ[n−L]: L ceros en |z| = |a|^{1/L}, polo de orden L en 0."""
    a = _Q(a)
    if L <= 0:
        raise _error("BAD_INPUT", "eco con L ≤ 0")
    N = N or (L + 1)
    h = [Fraction(0)] * N
    h[0] = Fraction(1)
    if L < N:
        h[L] = a
    return h


def ceros_eco(a, L: int) -> list[complex]:
    """Ceros de 1 + a·z^{−L}: z^L = −a, luego |z| = |a|^{1/L}.

    Si a > 0: fases (π + 2πk)/L; si a < 0: fases 2πk/L.
    """
    af = float(_Q(a))
    if af == 0:
        raise _error("BAD_INPUT", "eco con a = 0: no hay ceros finitos")
    if L <= 0:
        raise _error("BAD_INPUT", "eco con L ≤ 0")
    mod = abs(af) ** (1 / L)
    base = math.pi if af > 0 else 0.0
    return [mod * cmath.exp(1j * (base + 2 * math.pi * k) / L) for k in range(L)]


def modulo_eco(a, L: int, F: float) -> float:
    """|H(F)|² = 1+a²+2a·cos(2πLF) para H(z) = 1 + a·z^{−L}."""
    af = float(_Q(a))
    return 1 + af * af + 2 * af * math.cos(2 * math.pi * L * F)


def inverso_eco(a, L: int, K: int = 8) -> list:
    """Inverso causal de 1 + a·z^{−L} con b = −a: h2 = Σ b^k·δ[n−kL]."""
    b = -_Q(a)
    if not abs(float(b)) < 1:
        raise _error("BAD_INPUT", "inverso causal inestable: |b| ≥ 1")
    h2: list = [Fraction(0)] * (K * L + 1)
    pot = Fraction(1)
    for k in range(K + 1):
        h2[k * L] = pot
        pot *= b
    return h2


def cascada_eco(a, L: int, x: list, K: int = 12,
                trace: Trace | None = None) -> dict:
    """La cascada eco + inverso devuelve la entrada (segundo camino, §4.15)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.eco", "el inverso causal anula el eco: (1+a·z^{−L})·"
                 "(1/(1+a·z^{−L})) = 1 por serie geométrica",
                 why="si |b| < 1 con b = −a, la serie del inverso converge y "
                     "la cascada es la identidad (§4.15, fila 9)")
    trace.hipotesis("sen.eco_estable", f"|b| = {abs(float(_Q(a))):.4g} < 1",
                    "cumple" if abs(float(_Q(a))) < 1 else "falla")
    bb = abs(float(_Q(a)))
    if not bb < 1:
        raise _error("BAD_INPUT", "el inverso causal del eco necesita |a| < 1")
    xs_ = [abs(float(_Q(v))) for v in x] or [0.0]
    if not x:
        raise _error("BAD_INPUT", "falta la entrada x[n]")
    # K lo bastante grande: que el inverso cubra toda x y que el término truncado
    # |a|^{K+1}·max|x| quede por debajo de 10⁻⁹
    K = max(int(K), len(x) // max(1, int(L)) + 1,
            0 if bb == 0 or max(xs_) == 0 else
            int(math.ceil(math.log(1e-9 / max(xs_)) / math.log(bb))) if bb > 0 else 0)
    K = min(K, 5000)
    h1 = eco_h(a, L, L + 1)
    h2 = inverso_eco(a, L, K)
    y = conv_lineal([_Q(v) for v in x], h1)["y"]
    z = conv_lineal(y, h2)["y"][:len(x)]
    xs = [_Q(v) for v in x]
    resto = max(abs(float(z[n] - xs[n])) for n in range(len(xs)))
    cola = max(abs(float(v)) for v in conv_lineal(y, h2)["y"][len(x):]) \
        if len(conv_lineal(y, h2)["y"]) > len(x) else 0.0
    if resto > 0.1 ** 6 or cola > 1e-3:
        raise _error("DISCREPANT", f"cascada: resto {resto:.3g}, cola {cola:.3g}")
    trace.verificacion("sen.eco_cascada", f"z = x con resto {resto:.3g}")
    return {"z": z, "resto": resto}


@dataclass
class ResultadoSenal:
    texto: str
    datos: dict = field(default_factory=dict)
