# SPDX-License-Identifier: MIT
"""MATH_LAB ML-1: integer arithmetic written as it is written on paper.

The first calculator of §8.2 A, «Operaciones básicas»:

    Suma, resta, producto y **división larga** con llevadas, como en papel

Column arithmetic is not a pretty interface over ``Fraction`` arithmetic — it
is a *method*, and §5.5b makes justifying a method an acceptance criterion. A
student who is told ``345 + 278 = 623`` has learned nothing; a student who sees

    5 + 8 = 13 → se escribe 3 y se lleva 1
    4 + 7 + 1 = 12 → se escribe 2 y se lleva 1
    3 + 2 + 1 = 6

has learned the carry. So every function here produces a step per column, in
the order the column is worked, naming the carry or the borrow.

Exactness
---------

Everything is ``int``: no floats, no rounding, no limit on size beyond the
bounds below. Division reports a quotient **and** a remainder, because ``7/2``
is not ``3.5`` in this laboratory — it is ``3`` with remainder ``1``, and the
decimal form is a later, explicitly approximate step.

Verification
------------

Every operation is checked by an independent second path (§5.3): the column
result is re-derived with Python's own exact arithmetic and compared. The
comparison is the seal, and it can fail, so a bug here would be *reported*
rather than displayed as a correct answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

#: bounds: enough for any exercise, small enough to keep a trace bounded
MAX_DIGITS = 60
MAX_RESULT_DIGITS = 120


def _error(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def _comprobar_entero(valor: object, que: str) -> int:
    """Accept an ``int`` (or an integral string) and nothing else.

    A float is refused rather than truncated: ``3.0`` as a dividend is either a
    typo or a rounding already made somewhere, and neither should be guessed.
    """
    if isinstance(valor, bool):
        raise _error("BAD_INPUT", f"{que} debe ser un número entero")
    if isinstance(valor, int):
        entero = valor
    elif isinstance(valor, str):
        texto = valor.strip()
        signo = ""
        if texto[:1] in "+-":
            signo, texto = ("-" if texto[0] == "-" else ""), texto[1:]
        if not texto.isdigit():
            raise _error("BAD_INPUT", f"{que} no es un entero: {valor!r}")
        entero = int(signo + texto)
    else:
        raise _error("BAD_INPUT", f"{que} debe ser un número entero, no {type(valor).__name__}")
    if abs(entero) >= 10 ** MAX_DIGITS:
        raise _error("EXPRESSION_LIMIT", f"{que} tiene más de {MAX_DIGITS} cifras")
    return entero


def _columnas(n: int) -> list[int]:
    """Digits of the absolute value, most significant first."""
    return [int(c) for c in str(abs(n))]


def _dígito(n: int, indice: int) -> int:
    """The digit of ``n`` in column ``indice`` counted from the right (0 = units)."""
    return (abs(n) // 10 ** indice) % 10


# ---------------------------------------------------------------------------
# addition and subtraction
# ---------------------------------------------------------------------------


def sumar(a: object, b: object, trace: Trace | None = None) -> int:
    """Column addition, one step per column, naming every carry."""
    trace = trace if trace is not None else Trace()
    x, y = _comprobar_entero(a, "el primer sumando"), _comprobar_entero(b, "el segundo sumando")
    if (x < 0) != (y < 0):
        # Mixed signs: a difference of magnitudes, decided by which is larger.
        # Stated as a method step, not silently reordered.
        trace.metodo(
            "suma.signos_distintos",
            "los sumandos tienen signos distintos: se restan las magnitudes",
            why=("con un sumando negativo la suma es una diferencia; se opera con los "
                 "valores absolutos y el signo se decide al final, según cuál magnitud "
                 "sea mayor"),
            before=f"{x} + {y}", after=str(x + y),
        )
        if x < 0:
            return -restar_cifras(abs(y), abs(x), trace)
        return restar_cifras(abs(x), abs(y), trace)
    signo = -1 if x < 0 else 1
    x, y = abs(x), abs(y)
    total = x + y
    if total >= 10 ** MAX_RESULT_DIGITS:
        raise _error("EXPRESSION_LIMIT", "el resultado es demasiado grande")
    ancho = max(len(_columnas(x)), len(_columnas(y)), len(_columnas(total)))
    lleva = 0
    for indice in range(ancho):
        dx, dy = _dígito(x, indice), _dígito(y, indice)
        suma_columna = dx + dy + lleva
        nueva, digito = divmod(suma_columna, 10)
        donde = _nombre_columna(indice)
        cuenta = f"{dx} + {dy}" + (f" + {lleva} (llevada de la derecha)" if lleva else "")
        if lleva or nueva:
            cuenta += f" = {suma_columna} → se escribe {digito}"
            if nueva:
                cuenta += f" y se lleva {nueva}"
            trace.regla(
                "suma.columna",
                f"columna de las {donde}",
                before=cuenta.split("→")[0].strip(), after=str(digito),
                piece=f"columna {donde}", why=cuenta,
                conditions=(f"la cifra que se lleva a la columna izquierda es {nueva}",)
                if nueva else (),
            )
        lleva = nueva
    trace.regla("suma.resultado", "resultado de la suma en columna",
                before=f"{x} + {y}", after=str(signo * total),
                why=("cada columna se suma con la llevada de la anterior; la columna de "
                     "la izquierda puede dejar una cifra nueva"))
    return signo * total


def restar(a: object, b: object, trace: Trace | None = None) -> int:
    """Column subtraction, one step per column, naming every borrow."""
    trace = trace if trace is not None else Trace()
    x, y = _comprobar_entero(a, "el minuendo"), _comprobar_entero(b, "el sustraendo")
    if (x < 0) != (y < 0):
        trace.metodo(
            "resta.signos_distintos",
            "los operandos tienen signos distintos: se suman las magnitudes",
            why=("restar un negativo es sumar; se opera con los valores absolutos y el "
                 "signo se decide al final"),
            before=f"{x} - {y}", after=str(x - y),
        )
        if x < 0:
            return -sumar(abs(x), abs(y), trace)
        return sumar(abs(x), abs(y), trace)
    if abs(x) < abs(y):
        trace.metodo(
            "resta.resultado_negativo",
            "el minuendo es menor que el sustraendo: el resultado es negativo",
            why=("la resta en columna solo se hace con magnitudes; como aquí no se puede, "
                 "se cambia el orden y se cambia el signo, que es la definición"),
            before=f"{x} - {y}", after=str(x - y),
        )
        return -restar_cifras(abs(y), abs(x), trace)
    return restar_cifras(abs(x), abs(y), trace)


def restar_cifras(mayor: int, menor: int, trace: Trace) -> int:
    """``mayor - menor`` on non-negative magnitudes, with the borrows recorded."""
    ancho = len(_columnas(mayor))
    prestado = 0
    resultado = 0
    for indice in range(ancho):
        dg = _dígito(mayor, indice)
        de = _dígito(menor, indice)
        entra = prestado
        db = de + entra
        base = f"{dg} - {de}" + (" - 1 (préstamo de la derecha)" if entra else "")
        if dg < db:
            # not enough in this column: borrow one from the left
            digito = dg + 10 - db
            prestado = 1
            texto = (f"{base} = {dg - db} no alcanza; se pide 1 a la columna de la "
                     f"izquierda, así que {dg} + 10 = {dg + 10} y "
                     f"{dg + 10} - {db} = {digito}")
            regla = "resta.prestamo"
        else:
            digito = dg - db
            prestado = 0
            texto = f"{base} = {digito}" if (dg or de) else None
            regla = "resta.columna"
        if texto is not None:
            trace.regla(regla, f"columna de las {_nombre_columna(indice)}",
                        before=base, after=str(digito),
                        piece=f"columna {_nombre_columna(indice)}", why=texto)
        resultado += digito * 10 ** indice
    trace.regla("resta.resultado", "resultado de la resta en columna",
                before=f"{mayor} - {menor}", after=str(resultado),
                why=("cada columna resta el dígito del sustraendo y el préstamo de la "
                     "columna de la derecha; si falta, se pide uno a la izquierda"))
    return resultado


def _nombre_columna(indice: int) -> str:
    nombres = ("unidades", "decenas", "centenas", "miles de unidades",
               "diez mil", "cien mil", "millones")
    return nombres[indice] if indice < len(nombres) else f"10^{indice}"


# ---------------------------------------------------------------------------
# multiplication
# ---------------------------------------------------------------------------


def multiplicar(a: object, b: object, trace: Trace | None = None) -> int:
    """School multiplication: one partial product per digit of the multiplier."""
    trace = trace if trace is not None else Trace()
    x, y = _comprobar_entero(a, "el primer factor"), _comprobar_entero(b, "el segundo factor")
    signo = -1 if (x < 0) != (y < 0) else 1
    x, y = abs(x), abs(y)
    if y > x:  # the shorter number multiplies, as on paper
        x, y = y, x
    if x * y >= 10 ** MAX_RESULT_DIGITS:
        raise _error("EXPRESSION_LIMIT", "el producto es demasiado grande")
    total = 0
    digitos = _columnas(y)
    for posicion, digito in enumerate(reversed(digitos)):
        parcial = x * digito
        total += parcial * 10 ** posicion
        if digito == 0:
            continue
        trace.regla(
            "producto.parcial",
            f"producto parcial por la cifra {digito} "
            f"({_nombre_columna(posicion)} del segundo factor)",
            before=f"{x} × {digito}", after=str(parcial * 10 ** posicion),
            piece=f"cifra {digito} en {_nombre_columna(posicion)}",
            conditions=("el desplazamiento de la posición se hace al final",)
            if posicion else (),
            why=("se multiplica por una cifra cada vez y el resultado se desplaza un "
                 "lugar por cada posición a la derecha, que es la cuenta en papel"),
        )
    trace.regla("producto.resultado", "resultado del producto en columna",
                before=f"{x} × {y}", after=str(signo * total),
                why="se suman los productos parciales, cada uno en su posición")
    return signo * total


# ---------------------------------------------------------------------------
# long division
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Division:
    """A quotient with its remainder. Exact when ``resto == 0``."""

    cociente: int
    resto: int
    divisor: int
    dividendo: int

    @property
    def exacta(self) -> bool:
        return self.resto == 0

    @property
    def verificador(self) -> int:
        return self.cociente * self.divisor + self.resto

    def como_texto(self) -> str:
        if self.exacta:
            return str(self.cociente)
        return f"{self.cociente} resto {self.resto} (decimal: {self.cociente}.{_cifras_decimales(self.resto, self.divisor, 6)})"


def _cifras_decimales(resto: int, divisor: int, cifras: int) -> str:
    out = []
    r = resto
    for _ in range(cifras):
        r *= 10
        out.append(str(r // divisor))
        r %= divisor
        if r == 0:
            break
    return "".join(out)


def dividir(dividendo: object, divisor: object, trace: Trace | None = None) -> Division:
    """Long division, one step per quotient digit, showing the partial dividend.

    The remainder is part of the answer, never discarded: ``7/2`` is
    ``3 resto 1`` and its decimal form is marked as an approximation.
    """
    trace = trace if trace is not None else Trace()
    a = _comprobar_entero(dividendo, "el dividendo")
    b = _comprobar_entero(divisor, "el divisor")
    if b == 0:
        raise _error("DIVISION_BY_ZERO", "no se puede dividir entre cero")
    signo = -1 if (a < 0) != (b < 0) else 1
    a, b = abs(a), abs(b)
    if a < b:
        trace.metodo(
            "division.cociente_cero",
            "el dividendo es menor que el divisor: el cociente es 0",
            why=("ninguna cifra del dividendo llega al divisor, así que el cociente "
                 "empieza por 0 y el dividendo entero es el resto"),
            before=f"{a} / {b}", after="0",
        )
        return Division(0, a, b, a)
    texto = str(a)
    cociente = 0
    parcial = 0
    for indice, cifra in enumerate(texto):
        parcial = parcial * 10 + int(cifra)
        while parcial >= b:
            digito = parcial // b
            cociente = cociente * 10 + digito
            parcial -= digito * b
            trace.regla(
                "division.digito",
                f"cifra {digito} del cociente (posición {indice + 1})",
                before=f"dividendo parcial {parcial + digito * b}",
                after=str(parcial),
                piece=f"columna {indice + 1} de la izquierda",
                conditions=(f"se cumple {digito} × {b} ≤ {parcial + digito * b} < "
                            f"{digito + 1} × {b}",),
                why=("se toma la mayor cifra cuyo producto por el divisor no pase del "
                     "dividendo parcial; esa desigualdad es la definición de la cifra "
                     "del cociente"),
            )
        if cociente == 0 and indice + 1 < len(texto):
            trace.regla("division.cifra_cero",
                        f"cifra 0 del cociente (se baja el {cifra})",
                        before=f"dividendo parcial {parcial}", after=str(parcial),
                        piece=f"columna {indice + 1}",
                        why=(f"el dividendo parcial {parcial} es menor que el divisor "
                             f"{b}, así que en esta posición va un 0"))
    trace.regla("division.resultado", "resultado de la división larga",
                before=f"{a} / {b}",
                after=f"{cociente} resto {parcial}" if parcial else str(cociente),
                why=("el cociente son las cifras tomadas; el resto es lo que queda, y "
                     "satisface 0 ≤ resto < divisor"))
    return Division(signo * cociente, signo * parcial, signo * b if b < 0 else b, a)


# ---------------------------------------------------------------------------
# verification (the second path of §5.3)
# ---------------------------------------------------------------------------


def verificar(calculado: object, esperado: object) -> V.Seal:
    """Compare a column result with the host's own exact arithmetic."""
    try:
        marca, metodo, detalle = V.check_equivalence(
            _como_expresion(calculado), _como_expresion(esperado))
    except Exception as exc:  # pragma: no cover - defensive
        return V.Seal(V.NUMERIC_ONLY, "sin comprobación", str(exc))
    if marca:
        return V.Seal(V.VERIFIED, metodo, detalle)
    return V.Seal(V.DISCREPANT, metodo, detalle)


def _como_expresion(valor: object):
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    return mx.num(valor)
