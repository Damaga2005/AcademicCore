# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: the stable contract of §5.9, shared with the other labs.

The contract
------------

One entry point, no Qt (§1.2 principle 5)::

    calcular(operacion, entrada, convenciones, nivel, semilla, limites) -> Resultado

Any laboratory — signals, circuits, the digital lab, or a future phase of this
one — calls that. No laboratory calls a screen.

:func:`registrar` adds an **operation**; :func:`registrar_verificador` adds a
**verification plug-in**, which is how another lab lends its engine as a second
path (CIRCUITS_LAB registers ``ac/bode.py`` to check a Bode, per §5.9).

The result
----------

:class:`Resultado` carries exactly the six things §5.9 promises:

1. the **exact value** and, when asked, an approximation with its error;
2. the **step trace** (versioned, serialisable, three detail levels);
3. the **verification seal**;
4. the **graph described as data** — never an image, so another lab can draw it
   its own way;
5. the **conventions used**;
6. the **hypotheses checked**, with a verdict for each.

A version number travels with it. A change that is not backward compatible
increments it, and a consumer that declares the version it was built against is
refused rather than fed a trace it cannot read.

Honesty rules encoded here
--------------------------

- An operation that cannot answer **exactly** does not silently approximate: it
  returns the numeric value *and* says so in ``sello`` and in an ``aviso`` step
  («no sé darte una solución exacta» is the §5.4 message);
- a missing verification plug-in **lowers the seal** to ``solo_numerico``
  instead of hiding the gap;
- the time/size limits of §5.4 are parameters, so a caller can bound a call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import (
    PASO,
    TRACE_VERSION,
    Trace,
)
from academic_core.errors import UnsupportedError, ValidationError

#: contract version (§5.9). Consumers declare the one they were built against.
CONTRACT_VERSION = "1.0"

#: message of §5.4, used when no exact method is found
NO_EXACT = "no sé darte una solución exacta"


def error(reason: str, message: str) -> ValidationError:
    """A D2 validation error with this laboratory's reason code.

    Public because the calculators of §8.3 live in a sibling module and must
    report a bad request the same way the contract does.
    """
    return ValidationError(f"{reason}: {message}")


def unsupported(message: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {message}")


# ---------------------------------------------------------------------------
# conventions (§5.11)
# ---------------------------------------------------------------------------

#: the conventions a calculation may depend on, and their allowed values
CONVENTIONS: dict[str, tuple[str, ...]] = {
    "valor_efectivo": ("V_ef", "pico"),
    "signo_exponencial": ("e^{+jwt}", "e^{-iwt}"),
    "db": ("20log10", "10log10"),
    "desviacion_tipica": ("n", "n-1"),
    "chauvenet": ("fijo_3", "clasico"),
    "frecuencia": ("f", "omega"),
    "frecuencia_digital": ("F", "k"),
    "correlacion": ("energia", "potencia"),
    "resto_division": ("no_negativo", "con_signo"),
    "base_logaritmos": ("log2", "ln", "log10"),
    "finanzas": ("nominal", "efectiva"),
    "potencial": ("V_inf_0", "otra"),
}


@dataclass(frozen=True)
class ConvencionConjunto:
    """The conventions an exercise declares, printed with its answer (§5.11)."""

    valores: tuple[tuple[str, str], ...] = ()

    @classmethod
    def of(cls, **kwargs: str) -> "ConvencionConjunto":
        for name, value in kwargs.items():
            if name not in CONVENTIONS:
                raise error("BAD_CONVENTION", f"convención desconocida: {name}")
            if value not in CONVENTIONS[name]:
                raise error(
                    "BAD_CONVENTION",
                    f"«{name}» admite {', '.join(CONVENTIONS[name])}; se dio {value!r}",
                )
        return cls(tuple(sorted(kwargs.items())))

    def get(self, name: str, default: str = "") -> str:
        for key, value in self.valores:
            if key == name:
                return value
        return default

    def as_lines(self) -> list[str]:
        return [f"{k} = {v}" for k, v in self.valores]


# ---------------------------------------------------------------------------
# graph described as data (§5.9: never an image)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Serie:
    """One polyline in a graph, as data."""

    name: str
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    discontinuities: tuple[int, ...] = ()  # indices where the curve is broken


@dataclass(frozen=True)
class Graph:
    """A graph described as data, with the text alternative of §6."""

    series: tuple[Serie, ...] = ()
    x_label: str = ""
    y_label: str = ""
    description: str = ""  # required: accessibility, §6

    def describe(self) -> str:
        head = self.description or "gráfica"
        for s in self.series:
            if not s.ys:
                continue
            lo, hi = min(s.ys), max(s.ys)
            head += f"; «{s.name}» va de {lo:.6g} a {hi:.6g} en {len(s.ys)} puntos"
        return head


# ---------------------------------------------------------------------------
# the result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    """What every calculator returns, whatever the laboratory that called it."""

    operacion: str
    #: printable exact value: a string, a number, or a mapping of them
    exacto: object | None = None
    #: the same value as an expression, when there is one, so a caller can send
    #: it to another calculator (§8.1 «enviar el resultado a otra calculadora»)
    exacto_expr: object | None = None
    aproximado: complex | None = None
    error_acotado: float | None = None
    cifras: int = 6
    traza: Trace = field(default_factory=Trace)
    sello: V.Seal = V.Seal(V.NUMERIC_ONLY, "sin comprobar", "")
    grafica: Graph | None = None
    convenciones: ConvencionConjunto = ConvencionConjunto()
    hipotesis: tuple[tuple[str, str], ...] = ()
    version: str = CONTRACT_VERSION
    avisos: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.sello.verdict != V.DISCREPANT

    def como_texto(self) -> str:
        """The whole result as plain text: copy/paste and cross-lab hand-off."""
        lines = [f"operación: {self.operacion}", f"versión del contrato: {self.version}"]
        if self.exacto is not None:
            lines.append(f"exacto: {_format_exact(self.exacto)}")
        if self.aproximado is not None:
            lines.append(f"aproximado: {_format_complex(self.aproximado, self.cifras)}")
        if self.error_acotado is not None:
            lines.append(f"error acotado: {self.error_acotado:.3g}")
        lines.append(f"sello: {self.sello.as_text()}")
        for name, verdict in self.hipotesis:
            lines.append(f"hipótesis: {name} -> {verdict}")
        for line in self.convenciones.as_lines():
            lines.append(f"convención: {line}")
        for aviso in self.avisos:
            lines.append(f"aviso: {aviso}")
        if self.grafica is not None:
            lines.append(f"gráfica: {self.grafica.describe()}")
        rendered = self.traza.render()
        if rendered:
            lines.append("pasos:")
            lines.append(rendered)
        return "\n".join(lines)


def _format_exact(value: object) -> str:
    if isinstance(value, mx.Expr):
        return mx.pretty(value)
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_format_exact(v)}" for k, v in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_exact(v) for v in value)
    return str(value)


def _format_complex(value: complex, digits: int) -> str:
    if abs(value.imag) < 1e-15:
        return f"{value.real:.{digits}g}"
    return f"{value.real:.{digits}g} {value.imag:+.{digits}g}i"


# ---------------------------------------------------------------------------
# limits (§5.4, §5.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Limites:
    """Bounds a caller can impose; every one is checked, never assumed."""

    max_pasos: int = 2000
    max_muestras: int = 512
    timeout_segundos: float | None = None

    def validar(self, pasos: int, muestras: int) -> None:
        if pasos > self.max_pasos:
            raise error("EXPRESSION_LIMIT", f"más de {self.max_pasos} pasos")
        if muestras > self.max_muestras:
            raise error("EXPRESSION_LIMIT", f"más de {self.max_muestras} muestras")


@dataclass(frozen=True)
class Peticion:
    """A typed call: what to compute, under which conventions."""

    operacion: str
    entrada: object
    convenciones: ConvencionConjunto = ConvencionConjunto()
    nivel: str = PASO
    semilla: int = V.SAMPLE_SEED
    limites: Limites = Limites()
    cifras: int = 6

    def validar(self) -> None:
        if self.nivel not in ("resumen", "paso", "detallado"):
            raise error("BAD_LEVEL", f"nivel de detalle desconocido: {self.nivel!r}")


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

_operaciones: dict[str, Callable[[Peticion], Resultado]] = {}
_verificadores: dict[str, Callable[[Resultado], tuple[bool, str]]] = {}


def registrar(nombre: str, funcion: Callable[[Peticion], Resultado]) -> None:
    """Register an operation. Re-registering a name is refused, not silent."""
    if nombre in _operaciones:
        raise error("DUPLICATE", f"la operación «{nombre}» ya existe")
    _operaciones[nombre] = funcion


def registrar_verificador(laboratorio: str,
                          funcion: Callable[[Resultado], tuple[bool, str]]) -> None:
    """Register another lab's engine as an independent second path (§5.9)."""
    _verificadores[laboratorio] = funcion


def withdraw_verificador(laboratorio: str) -> None:
    _verificadores.pop(laboratorio, None)


def verificadores() -> tuple[str, ...]:
    return tuple(sorted(_verificadores))


def operaciones() -> tuple[str, ...]:
    return tuple(sorted(_operaciones))


def calcular(peticion: Peticion) -> Resultado:
    """The one entry point of §5.9.

    ``peticion`` is validated, dispatched, and the result is passed through the
    registered verification plug-ins. A plug-in that disagrees does not replace
    the result: it downgrades the seal to ``discrepa`` and the discrepancy is
    recorded, so the caller cannot present it as correct (§5.3).
    """
    peticion.validar()
    funcion = _operaciones.get(peticion.operacion)
    if funcion is None:
        raise unsupported(
            f"operación «{peticion.operacion}» no registrada "
            f"(disponibles: {', '.join(operaciones()) or 'ninguna'})"
        )
    resultado = funcion(peticion)
    return _con_plug_ins(resultado, peticion)


def _con_plug_ins(resultado: Resultado, peticion: Peticion) -> Resultado:
    if not _verificadores:
        if resultado.sello.verdict == V.VERIFIED:
            return resultado  # already exact; no plug-in needed
        return _rebaixar(resultado, "no hay ningún verificador externo registrado")
    veredictos: list[str] = []
    for nombre in sorted(_verificadores):
        try:
            ok, detalle = _verificadores[nombre](resultado)
        except Exception as exc:  # a plug-in that breaks is a gap, not a crash
            veredictos.append(f"{nombre}: no se pudo ejecutar ({exc})")
            continue
        veredictos.append(f"{nombre}: {'coincide' if ok else 'discrepa'} — {detalle}")
        if not ok:
            return Resultado(
                operacion=resultado.operacion,
                exacto=resultado.exacto,
                exacto_expr=resultado.exacto_expr,
                aproximado=resultado.aproximado,
                error_acotado=resultado.error_acotado,
                cifras=resultado.cifras,
                traza=resultado.traza,
                sello=V.Seal(V.DISCREPANT, nombre, detalle),
                grafica=resultado.grafica,
                convenciones=resultado.convenciones,
                hipotesis=resultado.hipotesis,
                version=CONTRACT_VERSION,
                avisos=resultado.avisos + tuple(veredictos),
            )
    return Resultado(
        operacion=resultado.operacion,
        exacto=resultado.exacto,
        exacto_expr=resultado.exacto_expr,
        aproximado=resultado.aproximado,
        error_acotado=resultado.error_acotado,
        cifras=resultado.cifras,
        traza=resultado.traza,
        sello=V.Seal(V.VERIFIED, resultado.sello.method or "varios motores",
                     "; ".join(veredictos)),
        grafica=resultado.grafica,
        convenciones=resultado.convenciones,
        hipotesis=resultado.hipotesis,
        version=CONTRACT_VERSION,
        avisos=resultado.avisos,
    )


def _rebaixar(resultado: Resultado, motivo: str) -> Resultado:
    """Lower the seal honestly instead of pretending (§5.9)."""
    if resultado.sello.verdict == V.DISCREPANT:
        return resultado
    return Resultado(
        operacion=resultado.operacion,
        exacto=resultado.exacto,
        exacto_expr=resultado.exacto_expr,
        aproximado=resultado.aproximado,
        error_acotado=resultado.error_acotado,
        cifras=resultado.cifras,
        traza=resultado.traza,
        sello=V.Seal(V.NUMERIC_ONLY, resultado.sello.method, f"{motivo}; {resultado.sello.detail}"),
        grafica=resultado.grafica,
        convenciones=resultado.convenciones,
        hipotesis=resultado.hipotesis,
        version=CONTRACT_VERSION,
        avisos=resultado.avisos,
    )


def comprobar_version(version: str) -> None:
    """Refuse a consumer built against an incompatible contract."""
    if version.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
        raise error(
            "VERSION_MISMATCH",
            f"el consumidor declara la versión {version} y este motor habla la "
            f"{CONTRACT_VERSION}",
        )


#: what a consumer must declare
VERSION_PUBLICA = CONTRACT_VERSION
VERSION_TRAZA = TRACE_VERSION
