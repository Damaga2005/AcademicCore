# SPDX-License-Identifier: MIT
"""ML-12 (§5.10.4): numerical gradient checker by central differences.

Reusable by gradient descent, logistic regression, backpropagation and Markowitz:
anything that claims «this is ∇f» — a formula or a black-box function — is
compared with central differences at seeded points.

The estimate is Richardson-extrapolated central differences::

    D(h) = (f(x + h·eᵢ) − f(x − h·eᵢ)) / (2h)        error O(h²)
    R    = (4·D(h/2) − D(h)) / 3                      error O(h⁴)

with ``h = ε^(1/5)·max(1, |xᵢ|)``, the step that balances the O(h⁴) truncation
against the O(ε/h) rounding. Agreement is judged by the relative error
``|g − R| / max(1, |g|, |R|)`` against a tolerance (1e-6 by default), and the
difference between ``D(h/2)`` and ``R`` is reported as the estimate's own error,
so a point where f is not smooth (a kink of a ReLU) shows up as «unreliable»
instead of as a false discrepancy.

Points are seeded (no ``random`` in the domain): the same call gives the same verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

EPS = 2.0 ** -52
TOLERANCIA = 1e-6


@dataclass(frozen=True)
class Componente:
    punto: tuple[float, ...]
    variable: str
    analitico: float
    numerico: float
    error_relativo: float
    error_estimacion: float     # how much the numeric estimate itself is trusted
    fiable: bool
    coincide: bool


@dataclass(frozen=True)
class Informe:
    variables: tuple[str, ...]
    componentes: tuple[Componente, ...]
    tolerancia: float

    @property
    def ok(self) -> bool:
        return all(c.coincide for c in self.componentes if c.fiable)

    @property
    def fiables(self) -> int:
        return sum(1 for c in self.componentes if c.fiable)

    def peor(self) -> Componente | None:
        fiables = [c for c in self.componentes if c.fiable]
        return max(fiables, key=lambda c: c.error_relativo, default=None)

    def texto(self) -> str:
        peor = self.peor()
        if peor is None:
            return "sin puntos donde la diferencia central sea fiable"
        if self.ok:
            return (f"el gradiente coincide en {self.fiables} comprobaciones; peor error "
                    f"relativo {peor.error_relativo:.2e} (tolerancia {self.tolerancia:.0e})")
        punto = ", ".join(f"{v} = {x:.6g}" for v, x in zip(self.variables, peor.punto))
        return (f"el gradiente NO coincide: ∂/∂{peor.variable} en ({punto}) vale "
                f"{peor.analitico:.10g} y la diferencia central da {peor.numerico:.10g} "
                f"(error relativo {peor.error_relativo:.2e})")


def _richardson(f: Callable[[list[float]], float], x: list[float], i: int
                ) -> tuple[float, float]:
    h = EPS ** 0.2 * max(1.0, abs(x[i]))

    def d(paso: float) -> float:
        mas, menos = list(x), list(x)
        mas[i] += paso
        menos[i] -= paso
        return (f(mas) - f(menos)) / (2 * paso)

    dh, dh2 = d(h), d(h / 2)
    r = (4 * dh2 - dh) / 3
    return r, abs(r - dh2)


def _pico(f: Callable[[list[float]], float], x: list[float], i: int) -> bool:
    """A kink: the one-sided slopes differ by an amount that does NOT shrink with h.

    For a smooth f, forward − backward ≈ h·f″ halves when h halves; at a kink
    (|x|, ReLU) it stays equal to the jump of the derivative. The symmetric
    difference alone cannot see this: at 0 it returns the average slope.
    """
    fx = f(x)

    def lados(paso: float) -> float:
        mas, menos = list(x), list(x)
        mas[i] += paso
        menos[i] -= paso
        return abs((f(mas) - fx) / paso - (fx - f(menos)) / paso)

    h = 1e-3 * max(1.0, abs(x[i]))
    a, b = lados(h), lados(h / 2)
    return a > 1e-7 * max(1.0, abs(fx)) and b > 0.75 * a


def comprobar(f: Callable[[list[float]], float],
              gradiente: Callable[[list[float]], Sequence[float]],
              puntos: Sequence[Sequence[float]], variables: Sequence[str],
              tolerancia: float = TOLERANCIA, trace: Trace | None = None) -> Informe:
    """Compare ``gradiente(x)`` with central differences of ``f`` at each point."""
    trace = trace if trace is not None else Trace()
    trace.metodo("gradiente.diferencias", "diferencias centrales con extrapolación de "
                 "Richardson",
                 why="error O(h⁴) con dos evaluaciones por lado; la diferencia entre "
                     "los dos pasos estima el error de la propia estimación")
    componentes = []
    for x in puntos:
        x = [float(v) for v in x]
        try:
            g = list(gradiente(x))
            fx = f(x)
        except (ZeroDivisionError, ValueError, OverflowError):
            continue
        if len(g) != len(variables):
            raise ValidationError(f"BAD_INPUT: el gradiente tiene {len(g)} componentes y hay "
                                  f"{len(variables)} variables")
        escala_f = max(1.0, abs(fx))
        for i, var in enumerate(variables):
            try:
                num, err = _richardson(f, x, i)
            except (ZeroDivisionError, ValueError, OverflowError):
                continue
            # a smooth f gives err ~ ε^(4/5)·|f|; much more means a kink or a pole near x
            fiable = (err <= 1e-4 * max(1.0, abs(num)) + 1e-9 * escala_f
                      and not _pico(f, x, i))
            rel = abs(g[i] - num) / max(1.0, abs(g[i]), abs(num))
            componentes.append(Componente(tuple(x), var, float(g[i]), num, rel, err, fiable,
                                          rel <= tolerancia))
    informe = Informe(tuple(variables), tuple(componentes), tolerancia)
    no_fiables = len(componentes) - informe.fiables
    if no_fiables:
        trace.aviso("gradiente.no_fiable",
                    f"{no_fiables} comprobaciones descartadas: la diferencia central no es "
                    "estable allí (función no derivable o casi singular)")
    trace.verificacion("gradiente.veredicto", informe.texto())
    return informe


def comprobar_expresion(f: mx.Expr, gradiente: dict[str, mx.Expr],
                        tolerancia: float = TOLERANCIA, semilla: int = V.SAMPLE_SEED,
                        trace: Trace | None = None) -> Informe:
    """The same, for a formula and a claimed gradient given as formulas."""
    variables = sorted(mx.variables(f) | set().union(*(mx.variables(g)
                                                       for g in gradiente.values())))
    faltan = [v for v in variables if v not in gradiente]
    if faltan:
        raise ValidationError(f"BAD_INPUT: falta la componente del gradiente en "
                              f"{', '.join(faltan)}")

    def valor(e: mx.Expr, x: list[float]) -> float:
        v = mx.valor_real(e, dict(zip(variables, x)))
        if v is None:
            raise ValueError("fuera del dominio")
        return float(v)

    puntos = [[env[v] for v in variables]
              for env in V.sampled_points(variables, semilla, 12)]
    return comprobar(lambda x: valor(f, x),
                     lambda x: [valor(gradiente[v], x) for v in variables],
                     puntos, variables, tolerancia, trace)
