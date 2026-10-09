# SPDX-License-Identifier: MIT
"""ML-12 (§5.10.3): seeded event simulator — the «second path» for stochastic models.

No ``random`` in the domain (the architecture test forbids it): the generator is
SplitMix64, written here, so a simulation is replayable bit for bit from its seed
on any machine and any Python version.

What is here:

- :class:`Generador` — uniform, exponential, a choice by weights;
- :func:`markov` — a finite Markov chain: the EXACT stationary distribution (a
  linear system over ℚ, solved with the field-parametrised engine) and the exact
  n-step distribution, then a seeded simulation as an independent check, judged
  against its own statistical error (never «close enough» by eye);
- :class:`Simulador` — a discrete-event loop (a heap of timed events), used by
  :func:`cola_mm1` and reusable for ALOHA, schedulers or anything with clocks;
- :func:`montecarlo` — a seeded estimate with its standard error.

A simulation never replaces an exact result here: it confirms or contradicts it,
and its tolerance is stated (``k`` standard errors).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

MASK = (1 << 64) - 1
#: a simulated frequency agrees when it is within this many standard errors
SIGMAS = 4.0
MAX_PASOS = 2_000_000


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


class Generador:
    """SplitMix64 (Steele, Lea & Flood, 2014): small, fast, and fully specified."""

    def __init__(self, semilla: int):
        self.estado = semilla & MASK

    def _siguiente(self) -> int:
        self.estado = (self.estado + 0x9E3779B97F4A7C15) & MASK
        z = self.estado
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        return z ^ (z >> 31)

    def uniforme(self) -> float:
        """In [0, 1), 53 random bits."""
        return (self._siguiente() >> 11) * 2.0 ** -53

    def exponencial(self, tasa: float) -> float:
        if tasa <= 0:
            raise _error("BAD_INPUT", "la tasa tiene que ser positiva")
        return -math.log(1.0 - self.uniforme()) / tasa

    def eleccion(self, pesos) -> int:
        u = self.uniforme() * float(sum(pesos))
        acumulado = 0.0
        for i, p in enumerate(pesos):
            acumulado += float(p)
            if u < acumulado:
                return i
        return len(pesos) - 1


# ---------------------------------------------------------------------------
# Markov chains
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Markov:
    P: tuple[tuple[Fraction, ...], ...]
    estacionaria: tuple[Fraction, ...] | None      # None = not unique
    distribucion_n: tuple[Fraction, ...] | None
    frecuencias: tuple[float, ...]
    pasos_simulados: int
    coincide: bool
    peor_desviacion: float      # in standard errors

    def texto(self) -> str:
        partes = []
        if self.estacionaria is None:
            partes.append("la distribución estacionaria no es única (cadena reducible)")
        else:
            partes.append("π = (" + ", ".join(str(x) for x in self.estacionaria) + ")")
        if self.distribucion_n is not None:
            partes.append("p(n) = (" + ", ".join(str(x) for x in self.distribucion_n) + ")")
        if self.pasos_simulados:
            partes.append("simulación: (" + ", ".join(f"{f:.4f}" for f in self.frecuencias)
                          + f") en {self.pasos_simulados} pasos")
        return "; ".join(partes)


def _matriz_estocastica(P) -> list[list[Fraction]]:
    from academic_core.domain.engineering.mathlab import lineal as L

    Q = L.cuerpo("Q")
    M = L.matriz(P, Q)
    n = len(M)
    if any(len(f) != n for f in M):
        raise _error("BAD_INPUT", "la matriz de transición tiene que ser cuadrada")
    for i, f in enumerate(M):
        if any(x < 0 for x in f):
            raise _error("NOT_STOCHASTIC", f"la fila {i + 1} tiene probabilidades negativas")
        if sum(f) != 1:
            raise _error("NOT_STOCHASTIC", f"la fila {i + 1} suma {sum(f)}, no 1")
    return M


def estacionaria(P, trace: Trace | None = None) -> tuple[Fraction, ...] | None:
    """Solve π·P = π, Σπ = 1 exactly over ℚ; None if the solution is not unique."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    M = _matriz_estocastica(P)
    n = len(M)
    Q = L.cuerpo("Q")
    # (Pᵀ − I)·πᵀ = 0 plus the normalisation row
    A = [[M[j][i] - (1 if i == j else 0) for j in range(n)] for i in range(n)] + [[Fraction(1)] * n]
    b = [Fraction(0)] * n + [Fraction(1)]
    trace.metodo("markov.estacionaria", "sistema π·(P − I) = 0 con Σπ = 1 sobre ℚ",
                 why="la distribución estacionaria es exacta: es un sistema lineal racional")
    sistema = L.resolver_sistema(A, b, Q, trace)
    if sistema.particular is None or sistema.nucleo:
        trace.aviso("markov.no_unica", "π no es única: hay más de una clase recurrente")
        return None
    pi = tuple(sistema.particular)
    nuevo = [sum(pi[i] * M[i][j] for i in range(n)) for j in range(n)]
    if tuple(nuevo) != pi:
        raise _error("INTERNAL", "π·P ≠ π")
    trace.verificacion("markov.sustitucion", "π·P = π y Σπ = 1, exacto")
    return pi


def distribucion_tras(P, inicial: int, pasos: int) -> tuple[Fraction, ...]:
    M = _matriz_estocastica(P)
    n = len(M)
    p = [Fraction(1 if i == inicial else 0) for i in range(n)]
    for _ in range(pasos):
        p = [sum(p[i] * M[i][j] for i in range(n)) for j in range(n)]
    return tuple(p)


def markov(P, *, inicial: int = 0, pasos: int | None = None, simular: int = 0,
           semilla: int = 1, trace: Trace | None = None) -> Markov:
    trace = trace if trace is not None else Trace()
    M = _matriz_estocastica(P)
    n = len(M)
    if not 0 <= inicial < n:
        raise _error("BAD_INPUT", f"estado inicial {inicial} fuera de 0..{n - 1}")
    if simular > MAX_PASOS:
        raise _error("EXPRESSION_LIMIT", f"más de {MAX_PASOS} pasos de simulación")
    pi = estacionaria(M, trace)
    pn = distribucion_tras(M, inicial, pasos) if pasos is not None else None
    if pn is not None:
        trace.regla("markov.potencia", f"p({pasos}) = p(0)·P^{pasos}",
                    after="(" + ", ".join(str(x) for x in pn) + ")")
    frecuencias: tuple[float, ...] = ()
    coincide, peor = True, 0.0
    if simular:
        g = Generador(semilla)
        lotes = 50
        por_lote = max(1, simular // lotes)
        estado, visitas = inicial, [0] * n
        medias: list[list[float]] = []
        for k in range(lotes * por_lote):
            estado = g.eleccion(M[estado])
            visitas[estado] += 1
            if (k + 1) % por_lote == 0:
                medias.append([v / por_lote for v in visitas])
                visitas = [0] * n
        total = lotes * por_lote
        frecuencias = tuple(sum(m[j] for m in medias) / lotes for j in range(n))
        simular = total
        if pi is not None:
            # visits are correlated, so the error is estimated by batch means:
            # 50 batches, each long enough to be nearly independent of the next
            for j, p in enumerate(pi):
                var = sum((m[j] - frecuencias[j]) ** 2 for m in medias) / (lotes - 1)
                sigma = max(math.sqrt(var / lotes), 1.0 / total)
                peor = max(peor, abs(frecuencias[j] - float(p)) / sigma)
            coincide = peor <= SIGMAS
            trace.verificacion("markov.simulacion",
                               f"frecuencias simuladas con semilla {semilla} ({lotes} lotes): "
                               f"peor desviación {peor:.2f} errores típicos "
                               f"(se acepta hasta {SIGMAS:g})")
    return Markov(tuple(tuple(f) for f in M), pi, pn, frecuencias, simular, coincide, peor)


# ---------------------------------------------------------------------------
# discrete events
# ---------------------------------------------------------------------------


@dataclass(order=True)
class _Evento:
    tiempo: float
    orden: int
    tipo: str = field(compare=False)
    datos: object = field(compare=False, default=None)


class Simulador:
    """A clock and a heap of events; ties broken by insertion order (deterministic)."""

    def __init__(self, semilla: int):
        self.gen = Generador(semilla)
        self.reloj = 0.0
        self._cola: list[_Evento] = []
        self._n = 0

    def programar(self, retardo: float, tipo: str, datos: object = None) -> None:
        self._n += 1
        heapq.heappush(self._cola, _Evento(self.reloj + retardo, self._n, tipo, datos))

    def siguiente(self) -> _Evento | None:
        if not self._cola:
            return None
        ev = heapq.heappop(self._cola)
        self.reloj = ev.tiempo
        return ev


@dataclass(frozen=True)
class ColaMM1:
    lam: float
    mu: float
    teoria_L: float
    teoria_W: float
    simulado_L: float
    simulado_W: float
    clientes: int

    def texto(self) -> str:
        return (f"ρ = {self.lam / self.mu:.4g}; teoría L = ρ/(1−ρ) = {self.teoria_L:.4g}, "
                f"W = 1/(μ−λ) = {self.teoria_W:.4g}; simulación ({self.clientes} clientes) "
                f"L = {self.simulado_L:.4g}, W = {self.simulado_W:.4g}")


def cola_mm1(lam: float, mu: float, clientes: int = 20000, semilla: int = 1,
             trace: Trace | None = None) -> ColaMM1:
    trace = trace if trace is not None else Trace()
    if not 0 < lam < mu:
        raise _error("UNSTABLE", "M/M/1 solo es estable con 0 < λ < μ (ρ < 1)")
    if clientes > MAX_PASOS // 2:
        raise _error("EXPRESSION_LIMIT", "demasiados clientes")
    if clientes < 2:
        raise _error("BAD_INPUT", "hacen falta al menos 2 clientes que simular")
    rho = lam / mu
    L_t, W_t = rho / (1 - rho), 1 / (mu - lam)
    trace.metodo("mm1.estacionario",
                 "fórmulas de la cola en régimen estacionario, contrastadas "
                 "con una simulación de clientes sembrada",
                 why="una cola se estabiliza solo si ρ = λ/μ < 1; entonces la "
                     "longitud media de la cola y la espera media tienen "
                     "fórmula cerrada, y la simulación sirve de segundo camino "
                     "porque si la fórmula fuera falsa el promedio empírico la "
                     "contradiría")
    trace.regla("mm1.teoria", f"L = ρ/(1−ρ) = {L_t:.6g}, W = 1/(μ−λ) = {W_t:.6g}",
                why="fórmulas de M/M/1 en régimen estacionario; Little: L = λ·W")
    sim = Simulador(semilla)
    sim.programar(sim.gen.exponencial(lam), "llegada")
    en_sistema: list[float] = []      # arrival times, FIFO
    area, ultimo, atendidos, espera_total = 0.0, 0.0, 0, 0.0
    while atendidos < clientes:
        ev = sim.siguiente()
        area += len(en_sistema) * (ev.tiempo - ultimo)
        ultimo = ev.tiempo
        if ev.tipo == "llegada":
            en_sistema.append(ev.tiempo)
            if len(en_sistema) == 1:
                sim.programar(sim.gen.exponencial(mu), "salida")
            sim.programar(sim.gen.exponencial(lam), "llegada")
        else:
            espera_total += ev.tiempo - en_sistema.pop(0)
            atendidos += 1
            if en_sistema:
                sim.programar(sim.gen.exponencial(mu), "salida")
    L_s, W_s = area / ultimo, espera_total / atendidos
    trace.verificacion("mm1.simulacion", f"simulación sembrada (semilla {semilla}): "
                                         f"L = {L_s:.4g}, W = {W_s:.4g}")
    return ColaMM1(lam, mu, L_t, W_t, L_s, W_s, clientes)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimacion:
    valor: float
    error_tipico: float
    muestras: int
    semilla: int

    def texto(self) -> str:
        return (f"{self.valor:.6g} ± {self.error_tipico:.2g} (1σ, {self.muestras} muestras, "
                f"semilla {self.semilla})")


def montecarlo(muestra: Callable[[Generador], float], muestras: int, semilla: int = 1
               ) -> Estimacion:
    if not 2 <= muestras <= MAX_PASOS:
        raise _error("BAD_INPUT", f"entre 2 y {MAX_PASOS} muestras")
    g = Generador(semilla)
    s = s2 = 0.0
    for _ in range(muestras):
        x = muestra(g)
        s += x
        s2 += x * x
    media = s / muestras
    var = max(0.0, (s2 - muestras * media * media) / (muestras - 1))
    return Estimacion(media, math.sqrt(var / muestras), muestras, semilla)
