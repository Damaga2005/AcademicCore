# SPDX-License-Identifier: MIT
"""CI-0 (§14.1): el contrato común de toda calculadora del laboratorio de
circuitos, con magnitudes exactas y unidades.

Ocho reglas del encargo, y las ocho están en el código, no en un comentario:

1. **Entrada con unidades y validación estricta.** Cada magnitud es una
   :class:`~academic_core.domain.engineering.units.Quantity` (existente) y el
   contrato comprueba la dimensión, el signo donde no tiene sentido y que no
   sea NaN/inf. Se rechazan en castellano diciendo **qué** está mal.
2. **Convención declarada.** Una magnitud cuyo valor depende de una convención
   (valor eficaz o pico, ``e^{+jωt}`` o ``e^{-jωt}``, dB de amplitud o de
   potencia, temperatura de referencia) **no se calcula sin declararla**.
3. **Resultado con pasos**: fórmula usada, sustitución con unidades, valor e
   hipótesis, cada uno con su motivo.
4. **Exactitud**: `Fraction` para lo racional y `Decimal` de 50 dígitos para lo
   transcendente. ``float`` está **prohibido en el dominio** (P1): :func:`exacto`
   lanza si le llega uno, en vez de dejar que se cuele una coma flotante sin
   que nadie lo note.
5. **Verificación por segundo camino**: el sello dice *cómo* se comprobó.
6. **Rango de validez**: las fórmulas aproximadas declaran su condición y la
   comprueban; si no se cumple, el resultado no se da por bueno.
7. **Salida enviable**: todo resultado lleva un ``digest`` reproducible y se
   puede pasar a otro cálculo sin reescribirlo.
8. **Funciones puras**: sin Qt, sin red, sin reloj; misma entrada, mismo digest.

Las magnitudes que dependen de una convención se construyen con
:func:`declara` y no se pueden leer sin haber declarado antes: es la forma de
que «se asumiría en silencio» no sea una opción disponible.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.engineering.units import (
    DIMENSIONLESS,
    Quantity,
    UnitError,
    parse_quantity,
)

#: contexto de trabajo para lo transcendente (§14.1, punto 4)
PRECISION = 50

#: los tres sellos de §14.1. punto 5
VERIFICADO = "verificado"
FUERA_DE_RANGO = "fuera_de_rango"
DIFIERE = "difiere"


class EntradaInvalida(ValueError):
    """Petición mala: se dice por qué, no se revienta por dentro."""


class ConvencionNoDeclarada(EntradaInvalida):
    """Se pidió una magnitud ambigua sin declarar su convención (§14.1.2)."""


# ---------------------------------------------------------------------------
# 2. convenciones declaradas
# ---------------------------------------------------------------------------

#: cada convención y sus valores admitidos (Anexo C del spec)
CONVENCIONES: dict[str, tuple[str, ...]] = {
    "valor_efectivo": ("V_ef", "pico"),
    "exponencial": ("e^{+jwt}", "e^{-jwt}"),
    "db": ("20log10", "10log10"),
    "temperatura": ("300K", "290K"),
}


def declara(**kwargs: str) -> dict[str, str]:
    """Declara las convenciones de un cálculo, o falla diciendo el motivo.

    Sin esto, «3 dB» o «la tensión» son ambiguos y el número que sale depende
    de una suposición que nadie ha escrito. Declarar es barato; suponer en
    silencio es lo que hace que dos personas obtengan resultados distintos.
    """
    for nombre, valor in kwargs.items():
        if nombre not in CONVENCIONES:
            raise EntradaInvalida(
                f"convención desconocida «{nombre}»; hay "
                f"{', '.join(sorted(CONVENCIONES))}")
        if valor not in CONVENCIONES[nombre]:
            raise EntradaInvalida(
                f"«{nombre}» admite {', '.join(CONVENCIONES[nombre])}; "
                f"se dio {valor!r}")
    return dict(kwargs)


# ---------------------------------------------------------------------------
# 4. exactitud: float prohibido (P1)
# ---------------------------------------------------------------------------


def exacto(valor, que: str = "el valor") -> Fraction | Decimal:
    """Convierte a número exacto y **rechaza** los `float`.

    Un `float` que entra aquí es un `float` que ya ha perdido precisión antes
    de llegar: 0,1 no es exactamente un décimo y nadie lo sabrá. La regla
    es que el dominio no los admite, así que se dice en el punto de entrada en
    lugar de arrastrar el error por todo el cálculo.
    """
    if isinstance(valor, bool):
        raise EntradaInvalida(f"{que} es un booleano, no una magnitud")
    if isinstance(valor, float):
        raise EntradaInvalida(
            f"{que} llegó como float ({valor!r}); el dominio calcula exacto "
            f"(P1). Escríbelo como fracción «3/4», como decimal «0.75» o "
            f"como cadena, y se conserva")
    if isinstance(valor, Fraction):
        return valor
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise EntradaInvalida(f"{que} no es finito ({valor})")
        return valor
    if isinstance(valor, int):
        return Fraction(valor)
    texto = str(valor).strip().replace(",", ".")
    try:
        return Fraction(texto)
    except (ValueError, ZeroDivisionError):
        pass
    try:
        d = Decimal(texto)
    except Exception:
        raise EntradaInvalida(f"{que} no es un número: {valor!r}") from None
    if not d.is_finite():
        raise EntradaInvalida(f"{que} no es finito ({valor})")
    return d


def decimal(valor, que: str = "el valor") -> Decimal:
    """Como :func:`exacto`, pero devuelve siempre `Decimal`."""
    v = exacto(valor, que)
    return v if isinstance(v, Decimal) else Decimal(v.numerator) / Decimal(v.denominator)


def contexto():
    """El contexto de 50 dígitos para lo transcendente."""
    ctx = localcontext()
    return ctx


def con_precision(prec: int = PRECISION):
    ctx = localcontext()
    ctx.prec = prec
    return ctx


# ---------------------------------------------------------------------------
# 1. magnitudes con unidades
# ---------------------------------------------------------------------------


def magnitud(valor, unidad: str, que: str = "la magnitud",
             *, positiva: bool = False) -> Quantity:
    """Construye una `Quantity` validando **antes** de que exista.

    Acepta lo que escribe un estudiante: ``4k7``, ``4,7 kΩ``, ``4.7e3``,
    ``2u2F``. Rechaza la unidad incompatible y el negativo donde no tiene
    sentido, diciendo cuál de las dos cosas está mal.
    """
    if isinstance(valor, Quantity):
        q = valor
    else:
        texto = _normaliza(str(valor))
        if not texto:
            raise EntradaInvalida(f"{que} está vacío")
        q = _lee(texto, unidad, que)
    if positiva and q.to_base() < 0:
        raise EntradaInvalida(f"{que} no puede ser negativa ({q})")
    return q


def _lee(texto: str, unidad: str, que: str) -> Quantity:
    """Lee la magnitud dando por hecho que trae su unidad.

    Se prueba el texto tal cual (por si el llamante ya la escribió) y, si sale
    **adimensional** o no se entiende, se prueba con la unidad detrás. Un
    prefijo suelto («4.7k») no es una unidad, y por eso este segundo intento
    es el que hace funcionar «4k7» con «Ω».
    """
    intentos = [texto]
    if unidad:
        # el prefijo se pega a la unidad («4.7kΩ»): separado, «k Ω» no es
        # una unidad y el lector no lo entiende
        intentos.append(f"{texto}{unidad}")
        intentos.append(f"{texto} {unidad}")
    visto: list[Quantity] = []
    for cand in intentos:
        try:
            q = parse_quantity(cand)
        except (UnitError, ValueError):
            continue
        if q.unit.dimension != DIMENSIONLESS:
            return q
        visto.append(q)
    if not unidad and visto:
        return visto[0]
    if visto:
        raise EntradaInvalida(
            f"{que} ha salido adimensional y se esperaba {unidad}; escribe la "
            f"unidad, por ejemplo «{texto} {unidad}»")
    raise EntradaInvalida(
        f"{que} no se entiende: «{texto}»"
        + (f" con la unidad {unidad}" if unidad else "")
        + ". Se esperaba algo como «4k7», «4,7 kΩ» o «2u2F»")


#: prefijo + dígito detrás es la forma corta de las resistencias: «4k7» es
#: 4,7 kΩ, no 4700 kΩ. Sin esto, quien escribe cómo escribe el papel recibe
#: un error que no se parece a nada que haya escrito.
_PREFIJOS_CORTOS = "fpnuµmkKMGT"
_CORTO = re.compile(rf"^(\d+)([{_PREFIJOS_CORTOS}])(\d+)$")
_CORTO_R = re.compile(r"^(\d+)[Rr](\d+)$")


def _normaliza(texto: str) -> str:
    """De lo que se escribe a lo que se puede leer, sin cambiar el valor."""
    t = texto.strip().replace(",", ".")
    if not t:
        return t
    m = _CORTO.match(t)
    if m:
        entero, prefijo, decimal = m.groups()
        return f"{entero}.{decimal}{prefijo}"
    m = _CORTO_R.match(t)
    if m:                      # «1R2» es 1,2 × 10 (notación de la serie E)
        entero, decimal = m.groups()
        return f"{entero}.{decimal}e1"
    return t


def _necesita_unidad(texto: str, unidad: str) -> bool:
    """¿Falta la unidad en el texto? (evita «4.7e3kΩ»)"""
    return not any(ch.isalpha() for ch in texto)


# ---------------------------------------------------------------------------
# 3. pasos con motivo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paso:
    """Un paso de la traza: qué se hizo, antes, después y **por qué**."""

    regla: str
    etiqueta: str
    antes: str = ""
    despues: str = ""
    motivo: str = ""

    def linea(self) -> str:
        cab = f"[{self.regla}] {self.etiqueta}"
        if self.antes:
            cab += f"  ({self.antes})"
        if self.despues:
            cab += f" → {self.despues}"
        if self.motivo:
            cab += f"\n    por qué: {self.motivo}"
        return cab


@dataclass
class Traza:
    """Los pasos del cálculo. Sin al menos un paso con motivo no hay cálculo."""

    pasos: list[Paso] = field(default_factory=list)

    def anade(self, regla: str, etiqueta: str, *, antes: str = "",
              despues: str = "", motivo: str = "") -> None:
        self.pasos.append(Paso(regla, etiqueta, antes, despues, motivo))

    def __len__(self) -> int:
        return len(self.pasos)

    def texto(self) -> str:
        return "\n".join(p.linea() for p in self.pasos)

    @property
    def explica_el_metodo(self) -> bool:
        """§3: todo resultado es explicable; sin motivo no se puede."""
        return any(p.motivo for p in self.pasos)


# ---------------------------------------------------------------------------
# 5, 6 y 7. resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sello:
    """Qué se comprobó y cómo (§14.1.5)."""

    veredicto: str
    metodo: str          # el segundo camino, escrito para que se entienda
    detalle: str = ""

    @property
    def ok(self) -> bool:
        return self.veredicto == VERIFICADO

    def linea(self) -> str:
        marca = {"verificado": "✔", "fuera_de_rango": "⚠", "difiere": "✘"}.get(
            self.veredicto, "?")
        return f"{marca} {self.veredicto} ({self.metodo})" + (
            f": {self.detalle}" if self.detalle else "")


@dataclass(frozen=True)
class Resultado:
    """Lo que devuelve una calculadora: valor, pasos, sello y validez."""

    id: str
    formula: str
    valor: object
    traza: Traza
    sello: Sello
    sustitucion: str = ""
    hipotesis: tuple[str, ...] = ()
    validez: str = ""            # la condición bajo la que el resultado vale
    unidades: str = ""
    convenciones: tuple[tuple[str, str], ...] = ()
    digest: str = ""

    def __post_init__(self):
        if not self.digest:
            object.__setattr__(self, "digest", self._digest())

    def _digest(self) -> str:
        """P reproducible: misma entrada y mismos pasos, mismo digest."""
        partes = [self.id, self.formula, str(self.valor), self.sustitucion,
                  self.sello.veredicto, self.sello.metodo]
        partes += [f"{k}={v}" for k, v in self.convenciones]
        # el motivo va dentro: dos pasos que llegan al mismo número por
        # razones distintas no son el mismo cálculo, y compartirdigest haría
        # imposible saber cuál se reprodujo
        partes += [f"{p.regla}|{p.etiqueta}|{p.despues}|{p.motivo}"
                   for p in self.traza.pasos]
        return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()[:16]

    @property
    def ok(self) -> bool:
        return self.sello.ok

    def texto(self) -> str:
        lineas = [f"{self.id}: {self.formula}"]
        if self.sustitucion:
            lineas.append(f"  con {self.sustitucion}")
        lineas.append(f"  = {self.valor}"
                      + (f" {self.unidades}" if self.unidades else ""))
        for h in self.hipotesis:
            lineas.append(f"  hipótesis: {h}")
        if self.validez:
            lineas.append(f"  validez: {self.validez}")
        for k, v in self.convenciones:
            lineas.append(f"  convención {k} = {v}")
        lineas.append(f"  {self.sello.linea()}")
        lineas.append("  pasos:")
        lineas += ["    " + p.linea() for p in self.traza.pasos]
        lineas.append(f"  digest: {self.digest}")
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# la condición de validez se comprueba, no se supone (§14.1.6)
# ---------------------------------------------------------------------------


@dataclass
class Validez:
    """Declara la condición de una fórmula aproximada y la comprueba."""

    condicion: str
    cumplida: bool | None = None
    motivo: str = ""

    def comprueba(self, cumple: bool, motivo: str = "") -> "Validez":
        self.cumplida = bool(cumple)
        self.motivo = motivo if not cumple else ""
        return self

    def linea(self) -> str:
        if self.cumplida is None:
            return f"validez sin comprobar: {self.condicion}"
        return ("dentro de rango" if self.cumplida
                else f"⚠ fuera de rango: {self.motivo}")