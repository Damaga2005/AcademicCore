# SPDX-License-Identifier: MIT
"""ML-12 (§5.11): declared conventions, used as a second path.

Official solutions and exams mix conventions, and that produces errors. Each
calculation here is done under the declared convention AND under the opposite
one, and the two are reconciled: either the physical result is the same
(power from V_ef or from the amplitude), or it differs exactly as the convention
says (−40 dB in amplitude is −20 dB in power for the same «100 times smaller»).
A reconciliation that fails is an error of the engine, raised, never shown.

Covered: dB of amplitude or of power, rms or peak value, sample standard
deviation with n or n−1, remainder of integer division (non-negative or signed),
base of logarithms (bit, nat, hartley), ordinary or angular frequency, nominal
or effective interest rate, and Chauvenet's criterion (the course's fixed
D_max = 3 applied iteratively, against the classical N·P(|Z| > z) < ½).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


@dataclass(frozen=True)
class Doble:
    """A value under the declared convention, the same under the other one, and
    the sentence that reconciles them."""

    convencion: str
    valor: object
    otra: str
    valor_otra: object
    reconciliacion: str

    def texto(self) -> str:
        return (f"{self.valor} ({self.convencion}); con {self.otra}: {self.valor_otra}. "
                f"{self.reconciliacion}")


def _cerca(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b))


def decibelios(razon: float, magnitud: str, convencion: str, trace: Trace) -> Doble:
    """A ratio in dB. ``magnitud`` says what the ratio is a ratio OF: «amplitud»
    (V, I, E: 20·log₁₀) or «potencia» (10·log₁₀). The convention declared by the
    exercise is which formula its official solution applied."""
    if razon <= 0:
        raise _error("BAD_INPUT", "una razón en dB tiene que ser positiva")
    if magnitud not in ("amplitud", "potencia"):
        raise _error("BAD_INPUT", "magnitud = amplitud | potencia")
    a, p = 20 * math.log10(razon), 10 * math.log10(razon)
    valor, otra_val = (a, p) if convencion == "20log10" else (p, a)
    otra = "10log10" if convencion == "20log10" else "20log10"
    correcta = "20log10" if magnitud == "amplitud" else "10log10"
    # second path: the same physical ratio, seen as a power ratio, gives the same dB
    potencia = razon ** 2 if magnitud == "amplitud" else razon
    if not _cerca(10 * math.log10(potencia), a if magnitud == "amplitud" else p):
        raise _error("INTERNAL", "20·log(r) ≠ 10·log(r²)")
    trace.regla("db.dos", f"20·log₁₀({razon:g}) = {a:.6g} dB; 10·log₁₀({razon:g}) = {p:.6g} dB",
                why="el mismo cociente da el doble de dB si se trata como amplitud")
    nota = (f"la razón es de {magnitud}: lo correcto es {correcta}"
            + ("" if convencion == correcta else
               f" — la convención declarada ({convencion}) NO corresponde a una razón de "
               f"{magnitud}; revisa el enunciado"))
    return Doble(convencion, f"{valor:.6g} dB", otra, f"{otra_val:.6g} dB",
                 f"Difieren exactamente en un factor 2 ({nota}).")


def valor_eficaz(valor: float, convencion: str, resistencia: float, trace: Trace) -> Doble:
    """A sinusoid given by rms (V_ef) or by peak; the power must be the same."""
    if convencion == "V_ef":
        ef, pico = valor, valor * math.sqrt(2)
    elif convencion == "pico":
        pico, ef = valor, valor / math.sqrt(2)
    else:
        raise _error("BAD_INPUT", "convención V_ef | pico")
    if resistencia <= 0:
        raise _error("BAD_INPUT", "R > 0")
    p1, p2 = ef ** 2 / resistencia, pico ** 2 / (2 * resistencia)
    if not _cerca(p1, p2):
        raise _error("INTERNAL", "la potencia depende de la convención")
    trace.regla("vef.potencia", f"P = V_ef²/R = {p1:.6g} W = V_p²/(2R) = {p2:.6g} W",
                why="la potencia media es física: no puede depender de la convención; lo "
                    "que cambia es el ½")
    return Doble(convencion, f"V_ef = {ef:.6g}, V_p = {pico:.6g}",
                 "pico" if convencion == "V_ef" else "V_ef", f"P = {p2:.6g} W",
                 f"P = {p1:.6g} W con las dos (con amplitud la fórmula lleva ½).")


def desviacion(datos, convencion: str, trace: Trace) -> Doble:
    xs = [Fraction(str(x)) for x in datos]
    n = len(xs)
    if n < 2:
        raise _error("BAD_INPUT", "al menos dos datos")
    media = sum(xs) / n
    ss = sum((x - media) ** 2 for x in xs)
    var_n, var_n1 = ss / n, ss / (n - 1)
    if var_n1 * (n - 1) != var_n * n:
        raise _error("INTERNAL", "s²(n−1) ≠ n/(n−1)·s²(n)")
    trace.regla("s.dos", f"s² con n = {var_n}; con n−1 = {var_n1}",
                why="s²(n−1) = n/(n−1)·s²(n): la diferencia es exacta y conocida")
    a = (var_n, math.sqrt(var_n)) if convencion == "n" else (var_n1, math.sqrt(var_n1))
    b = (var_n1, math.sqrt(var_n1)) if convencion == "n" else (var_n, math.sqrt(var_n))
    return Doble(convencion, f"s² = {a[0]}, s = {a[1]:.6g}", "n-1" if convencion == "n" else "n",
                 f"s² = {b[0]}, s = {b[1]:.6g}",
                 f"Relación exacta s²(n−1) = {n}/{n - 1}·s²(n).")


def resto(a: int, n: int, convencion: str, trace: Trace) -> Doble:
    if n == 0:
        raise _error("BAD_INPUT", "división por 0")
    py = a % abs(n)                       # Euclidean: 0 ≤ r < |n|
    # C truncates the quotient toward zero: a = n·q + c, c with the sign of a
    q = abs(a) // abs(n) * (1 if (a >= 0) == (n > 0) else -1)
    c = a - n * q
    if (py - c) % abs(n) != 0 or not 0 <= py < abs(n):
        raise _error("INTERNAL", "los dos restos no son congruentes")
    trace.regla("resto.dos", f"{a} = {n}·{(a - py) // n} + {py} (euclídeo, 0 ≤ r < |n|); "
                             f"{a} = {n}·{q} + {c} (C, cociente truncado hacia 0)",
                why="el resto «no negativo» es el euclídeo; el de C lleva el signo del "
                    "dividendo (ojo: el % de Python lleva el signo del divisor)")
    v, w = (py, c) if convencion == "no_negativo" else (c, py)
    return Doble(convencion, str(v), "con_signo" if convencion == "no_negativo" else "no_negativo",
                 str(w), "Son congruentes módulo n: difieren en 0 o en ±n.")


def logaritmo(x: float, convencion: str, trace: Trace) -> Doble:
    if x <= 0:
        raise _error("BAD_INPUT", "x > 0")
    bases = {"log2": (2.0, "bit"), "ln": (math.e, "nat"), "log10": (10.0, "hartley")}
    if convencion not in bases:
        raise _error("BAD_INPUT", "log2 | ln | log10")
    valores = {k: math.log(x) / math.log(b) for k, (b, _) in bases.items()}
    if not _cerca(valores["log2"] * math.log(2), valores["ln"]):
        raise _error("INTERNAL", "cambio de base")
    otras = ", ".join(f"{valores[k]:.6g} {u}" for k, (_, u) in bases.items() if k != convencion)
    return Doble(convencion, f"{valores[convencion]:.6g} {bases[convencion][1]}", "otras bases",
                 otras, "log_b(x) = ln(x)/ln(b): 1 nat = 1/ln 2 bit ≈ 1,4427 bit.")


def frecuencia(valor: float, convencion: str, trace: Trace) -> Doble:
    if convencion == "f":
        f, w = valor, 2 * math.pi * valor
        texto, otra = f"f = {f:.6g} Hz", f"ω = {w:.6g} rad/s"
    elif convencion == "omega":
        w, f = valor, valor / (2 * math.pi)
        texto, otra = f"ω = {w:.6g} rad/s", f"f = {f:.6g} Hz"
    else:
        raise _error("BAD_INPUT", "f | omega")
    return Doble(convencion, texto, "omega" if convencion == "f" else "f", otra,
                 "ω = 2π·f; en las transformadas, δ(f − f₀) = 2π·δ(ω − ω₀) y "
                 "X(ω) = X(f)|_{f = ω/2π}.")


def interes(tasa: Fraction, periodos: int, convencion: str, trace: Trace) -> Doble:
    """Nominal annual rate j compounded m times ↔ effective annual rate i."""
    if periodos < 1:
        raise _error("BAD_INPUT", "periodos ≥ 1")
    if convencion == "nominal":
        j = Fraction(tasa)
        i = (1 + j / periodos) ** periodos - 1
        if (1 + i) != (1 + j / periodos) ** periodos:
            raise _error("INTERNAL", "capitalización")
        exacta = f" ({i})" if i.denominator < 10 ** 6 else ""
        texto, otra = f"j = {float(j):.6g} nominal", f"i = {float(i):.8g} efectiva{exacta}"
    elif convencion == "efectiva":
        i = float(tasa)
        j = periodos * ((1 + i) ** (1 / periodos) - 1)
        if not _cerca((1 + j / periodos) ** periodos, 1 + i):
            raise _error("INTERNAL", "capitalización")
        texto, otra = f"i = {i:.6g} efectiva", f"j = {j:.8g} nominal"
    else:
        raise _error("BAD_INPUT", "nominal | efectiva")
    return Doble(convencion, texto, "efectiva" if convencion == "nominal" else "nominal", otra,
                 f"(1 + j/m)^m = 1 + i con m = {periodos}: un año capitaliza igual con las dos.")


def _phi_cola(z: float) -> float:
    """P(|Z| > z) for a standard normal."""
    return math.erfc(z / math.sqrt(2))


def chauvenet(datos, convencion: str, trace: Trace) -> Doble:
    xs = [float(x) for x in datos]
    if len(xs) < 3:
        raise _error("BAD_INPUT", "al menos tres lecturas")

    def media_s(v):
        m = sum(v) / len(v)
        return m, math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))

    def fijo(v):
        v, fuera = list(v), []
        while len(v) > 2:
            m, s = media_s(v)
            if s == 0:
                break
            extremo = max(v, key=lambda x: abs(x - m))
            if abs(extremo - m) / s <= 3:
                break
            v.remove(extremo)
            fuera.append(extremo)
        return fuera

    def clasico(v):
        m, s = media_s(v)
        if s == 0:
            return []
        return [x for x in v if len(v) * _phi_cola(abs(x - m) / s) < 0.5]

    a, b = fijo(xs), clasico(xs)
    trace.regla("chauvenet.dos", f"fijo D_max = 3 iterativo descarta {a or 'nada'}; clásico "
                                 f"N·P(|Z| > z) < ½ descarta {b or 'nada'}",
                why="el umbral del curso es fijo; el clásico depende de N")
    v, w = (a, b) if convencion == "fijo_3" else (b, a)
    acuerdo = "Coinciden." if sorted(a) == sorted(b) else \
        "NO coinciden: el resultado depende de la convención; decláralo en la solución."
    return Doble(convencion, f"descarta {v or 'nada'}",
                 "clasico" if convencion == "fijo_3" else "fijo_3", f"descarta {w or 'nada'}",
                 acuerdo)
