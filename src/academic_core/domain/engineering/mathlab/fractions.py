# SPDX-License-Identifier: MIT
r"""MATH_LAB ML-1: fractions, exactly, with the method shown.

The «Facciones» calculator of §8.2 A:

    Simplificar, operar, comparar, pasar a decimal y a periódico

Everything is :class:`fractions.Fraction`, so no result is ever a rounded
float. That is what makes the interesting part possible: the **periodic
decimal** is found by exact reasoning, not by printing digits and hoping.

Periodic decimals
------------------

``1/3 = 0.333…`` and ``1/8 = 0.125`` are different animals, and a calculator
that shows both as "a decimal" hides the distinction an exercise asks about.
:func:`decimal_exacto` decides it exactly:

- the fraction is written ``n/d`` with ``d = 2^a·5^b·m`` and ``gcd(m, 10) = 1``;
- if ``m = 1`` the decimal **terminates** after ``max(a, b)`` digits;
- otherwise the period is detected by the multiplicative order of 10 modulo
  ``m``, found by repeated multiplication (every step recorded), never by
  counting printed digits.

For example ``1/7`` gives period 6 and the cycle ``142857``, and the check
``1/7 = 0.\overline{142857}`` is verified by multiplication, not by assertion.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

MAX_DENOMINADOR = 10 ** 18
MAX_CIFRAS_PERIODO = 1000


def _error(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def fraccion(numerador: object, denominador: object, trace: Trace | None = None) -> Fraction:
    """Build a fraction, refusing a zero denominator in Spanish."""
    trace = trace if trace is not None else Trace()
    n = _entero(numerador, "el numerador")
    d = _entero(denominador, "el denominador")
    if d == 0:
        raise _error("DIVISION_BY_ZERO", "una fracción no puede tener denominador cero")
    if abs(d) > MAX_DENOMINADOR:
        raise _error("EXPRESSION_LIMIT", f"el denominador supera {MAX_DENOMINADOR}")
    if d < 0:
        n, d = -n, -d
        trace.metodo(
            "fraccion.signo",
            "el denominador es negativo: se cambia el signo de los dos",
            why=("la fracción se escribe con el denominador positivo; cambiar los dos "
                 "signos a la vez no altera el valor"),
            before=f"{n}/{d}", after=f"{-n}/{-d}",
        )
    return Fraction(n, d)


def _entero(valor: object, que: str) -> int:
    if isinstance(valor, bool):
        raise _error("BAD_INPUT", f"{que} debe ser un entero")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, Fraction):
        if valor.denominator != 1:
            raise _error("BAD_INPUT", f"{que} debe ser un entero, no {valor}")
        return int(valor)
    if isinstance(valor, str):
        texto = valor.strip()
        if "/" in texto:
            a, _, b = texto.partition("/")
            return _entero(Fraction(a.strip(), b.strip()), que)
        try:
            return int(texto)
        except ValueError as exc:
            raise _error("BAD_INPUT", f"{que} no es un entero: {valor!r}") from exc
    raise _error("BAD_INPUT", f"{que} debe ser un entero, no {type(valor).__name__}")


def texto(f: Fraction) -> str:
    """``3/4``, or an integer when the denominator is 1."""
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"


# ---------------------------------------------------------------------------
# simplification: Euclid with every quotient recorded
# ---------------------------------------------------------------------------


def mcd(a: object, b: object, trace: Trace | None = None) -> int:
    """Euclid's algorithm, with every quotient and the linear combination.

    The combination ``a·s + b·t = mcd`` is not decoration: it is how the
    extended algorithm proves the result, and it is the second path of §5.3
    for the simplification itself.
    """
    trace = trace if trace is not None else Trace()
    x, y = abs(_entero(a, "el primer número")), abs(_entero(b, "el segundo número"))
    if x == 0 and y == 0:
        raise _error("BAD_INPUT", "mcd(0, 0) no está definido")
    if x < y:
        # the first quotient would be 0, which teaches nothing; Euclid's
        # algorithm starts with the larger number, and the combination is
        # symmetric, so the answer is unchanged
        x, y = y, x
    original = (x, y)
    s0, s1, t0, t1 = 1, 0, 0, 1
    while y:
        cociente = x // y
        resto = x - cociente * y
        trace.regla(
            "mcd.paso",
            f"{x} = {cociente}·{y} + {resto}",
            before=f"{x} y {y}", after=str(resto),
            piece=f"división euclídea, cociente {cociente}",
            conditions=(f"0 ≤ {resto} < {y}",),
            why=("el algoritmo de Euclides sustituye el par por (b, a mod b); el resto es "
                 "menor que el divisor, así que el proceso termina"),
        )
        x, y = y, resto
        s0, s1 = s1, s0 - cociente * s1
        t0, t1 = t1, t0 - cociente * t1
    if x == 0:
        x, s0, t0 = y, 0, 1
    combinacion = f"{original[0]}·{s0} + {original[1]}·{t0}"
    # the extended algorithm is only worth recording if it really reproduces the
    # mcd: that identity is the proof, so a failure is a bug, not a warning
    if original[0] * s0 + original[1] * t0 != x:
        raise _error("INTERNAL", "la combinación de Euclides no reproduce el mcd")
    trace.regla("mcd.combinacion",
                "combinación lineal que demuestra el resultado",
                before=f"mcd({original[0]}, {original[1]})", after=str(x),
                why=(f"el teorema de Euclides da {combinacion} = {x}, y como el último "
                     "resto no nulo es el mcd, la combinación lo confirma")),
    return x


def simplificar(numerador: object, denominador: object,
                trace: Trace | None = None) -> Fraction:
    """Reduce a fraction, showing the common divisor that was removed."""
    trace = trace if trace is not None else Trace()
    f = fraccion(numerador, denominador, trace)
    n, d = f.numerator, f.denominator
    if d == 1:
        trace.metodo("fraccion.ya_simplificada",
                     f"{texto(f)} ya está en forma irreducible",
                     why="el denominador es 1, así que no hay nada que simplificar",
                     before=texto(f), after=texto(f))
        return f
    comun = mcd(n, d, trace)
    if comun == 1:
        trace.metodo("fraccion.ya_simplificada",
                     f"{texto(f)} ya es irreducible",
                     why=("el máximo común divisor de numerador y denominador es 1, que es "
                          "justo la definición de fracción irreducible"),
                     before=texto(f), after=texto(f))
        return f
    resultado = Fraction(n // comun, d // comun)
    trace.regla("fraccion.simplificacion", "se divide numerador y denominador entre "
                f"el mcd {comun}",
                before=texto(f), after=texto(resultado),
                piece="numerador y denominador",
                conditions=(f"{n} = {comun}·{n // comun}",
                            f"{d} = {comun}·{d // comun}"),
                why=("dividir ambos entre el mismo número conserva el valor, y al usar el "
                     "máximo común divisor el resultado es irreducible en una sola pasada"))
    return resultado


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------


def operar(a: Fraction, b: Fraction, operacion: str, trace: Trace | None = None) -> Fraction:
    """Add, subtract, multiply or divide two fractions, with the rule named."""
    trace = trace if trace is not None else Trace()
    # Every rule is built from Fraction objects, never with / on Python ints:
    # int / int is a float, and one float here would destroy the exactness the
    # whole module exists for.
    reglas = {
        "+": ("fraccion.suma", "a/b + c/d = (a·d + c·b)/(b·d)",
              "se réduit a común denominador multiplicando en cruz",
              lambda: Fraction(a.numerator * b.denominator + b.numerator * a.denominator,
                               a.denominator * b.denominator)),
        "-": ("fraccion.resta", "a/b − c/d = (a·d − c·b)/(b·d)",
              "se reduce a común denominador multiplicando en cruz",
              lambda: Fraction(a.numerator * b.denominator - b.numerator * a.denominator,
                               a.denominator * b.denominator)),
        "*": ("fraccion.producto", "a/b · c/d = (a·c)/(b·d)",
              "se multiplican arriba con arriba y abajo con abajo",
              lambda: Fraction(a.numerator * b.numerator,
                               a.denominator * b.denominator)),
        "/": ("fraccion.cociente", "a/b ÷ c/d = (a·d)/(b·c)",
              "se divide por una fracción equivale a multiplicar por su inversa",
              lambda: Fraction(a.numerator * b.denominator,
                               a.denominator * b.numerator)),
    }
    if operacion not in reglas:
        raise _error("BAD_INPUT", f"operación desconocida: {operacion!r}")
    regla, formula, por_que, calcular = reglas[operacion]
    if operacion == "/" and b == 0:
        raise _error("DIVISION_BY_ZERO", "no se puede dividir por la fracción cero")
    crudo = calcular()
    if crudo.denominator == 0:
        raise _error("DIVISION_BY_ZERO", "el resultado no tiene denominador")
    resultado = simplificar(crudo.numerator, crudo.denominator, trace)
    trace.metodo(regla, f"se aplica {formula}", why=por_que,
                 before=f"{texto(a)} {operacion} {texto(b)}", after=texto(resultado))
    return resultado


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------


def comparar(a: Fraction, b: Fraction, trace: Trace | None = None) -> int:
    """``-1``, ``0`` or ``1``, by cross-multiplication with the sign shown.

    Cross-multiplication is the method because it never converts to a decimal,
    which is where an exact comparison of large fractions is usually lost.
    """
    trace = trace if trace is not None else Trace()
    if a.denominator == b.denominator:
        metodo, motivo = ("fraccion.comparar.igual_denominador",
                          "con el mismo denominador basta comparar los numeradores")
        izquierda, derecha = a.numerator, b.numerator
    else:
        metodo, motivo = ("fraccion.comparar.cruzado",
                          "al multiplicar en cruz por el producto de los denominadores, "
                          "positivo, el orden se conserva")
        izquierda = a.numerator * b.denominator
        derecha = b.numerator * a.denominator
    trace.metodo(
        metodo, "comparación por multiplicación cruzada", why=motivo,
        before=f"{texto(a)} ? {texto(b)}",
        after=f"{izquierda} ? {derecha}",
    )
    if izquierda < derecha:
        trace.regla("fraccion.comparar.resultado", f"{texto(a)} < {texto(b)}",
                    after="-1", why="el primer producto es menor")
        return -1
    if izquierda > derecha:
        trace.regla("fraccion.comparar.resultado", f"{texto(a)} > {texto(b)}",
                    after="1", why="el primer producto es mayor")
        return 1
    trace.regla("fraccion.comparar.resultado", f"{texto(a)} = {texto(b)}",
                after="0", why="los productos cruzados coinciden")
    return 0


# ---------------------------------------------------------------------------
# exact decimal form
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecimalExacto:
    """The exact decimal of a fraction: terminating, or with a period."""

    entero: int
    decimales: tuple[int, ...]      # the digits after the point
    periodo: tuple[int, ...] | None  # None when the decimal terminates
    preperiodo: int = 0              # digits before the period starts

    @property
    def exacto(self) -> str:
        base = str(abs(self.entero))
        if not self.decimales and self.periodo is None:
            return base
        cuerpo = "".join(str(d) for d in self.decimales)
        signo = "-" if self.entero < 0 else ""
        if self.periodo is None:
            return f"{signo}{base}.{cuerpo}"
        corte = len(self.decimales) - len(self.periodo)
        antes = cuerpo[:corte]
        ciclo = "".join(str(d) for d in self.periodo)
        if not antes:
            return f"{signo}{base},\\overline{{{ciclo}}}"
        return f"{signo}{base},{antes}\\overline{{{ciclo}}}"

    @property
    def termina(self) -> bool:
        return self.periodo is None

    def como_texto(self) -> str:
        if self.termina:
            return f"{self.exacto} (decimal exacto)"
        return f"{self.exacto} (decimal periódico de periodo {len(self.periodo)})"


def decimal_exacto(f: Fraction, trace: Trace | None = None,
                   maximo: int = 60) -> DecimalExacto:
    """The exact decimal of a fraction: where the period starts and how long it is.

    The period is found with the multiplicative order of 10 modulo the part of
    the denominator coprime with 10, which is a *proof* of the period length,
    not an observation of printed digits.
    """
    trace = trace if trace is not None else Trace()
    if f.denominator == 0:
        raise _error("DIVISION_BY_ZERO", "no se puede pasar una división por cero")
    signo = -1 if f < 0 else 1
    absoluto = abs(f)
    entero = absoluto.numerator // absoluto.denominator
    resto = absoluto.numerator - entero * absoluto.denominator
    d = absoluto.denominator
    a, b, m = 0, 0, d
    for p in (2, 5):
        while m % p == 0:
            m //= p
            if p == 2:
                a += 1
            else:
                b += 1
    if m == 1:
        largo = max(a, b)
        decimales = tuple(int(c) for c in _digitos_terminantes(resto, d, largo))
        trace.metodo(
            "decimal.terminado",
            f"el decimal termina tras {largo} cifra(s)",
            why=(f"el denominador {d} solo tiene factores 2 y 5 "
                 f"({d} = 2^{a}·5^{b}); un decimal termina exactamente cuando su "
                 f"denominador reducido no tiene otros factores, y el número de cifras "
                 f"es max({a}, {b})"),
            before=texto(f), after=str(entero) + ("." + "".join(map(str, decimales))
                                                  if decimales else ""),
        )
        return DecimalExacto(signo * entero, decimales, None)
    largo_pre = max(a, b)
    orden, _ = _orden_multiplicativo(m, trace)
    if orden > MAX_CIFRAS_PERIODO:
        raise _error("EXPRESSION_LIMIT", f"el periodo excede {MAX_CIFRAS_PERIODO} cifras")
    total = largo_pre + orden
    if total > maximo:
        raise _error(
            "EXPRESSION_LIMIT",
            f"el decimal necesita {total} cifras y el máximo permitido es {maximo}",
        )
    digs = tuple(int(c) for c in _digitos_terminantes(resto, d, total))
    periodo = digs[largo_pre:]
    trace.metodo(
        "decimal.periodico",
        f"el decimal es periódico, de periodo {orden}, y el periodo empieza en la "
        f"cifra {largo_pre + 1}",
        why=(f"el denominador {d} = 2^{a}·5^{b}·{m} y {m} es coprimo con 10, así que el "
             f"decimal no puede terminar; la longitud del periodo es el orden de 10 "
             f"módulo {m}, que se calcula multiplicando 10 repetidas veces hasta "
             f"volver a 1"),
        before=texto(f),
        after=str(entero) + "," + "".join(map(str, digs[:largo_pre])) + "(" +
        "".join(map(str, periodo)) + ")",
    )
    return DecimalExacto(signo * entero, digs, periodo, largo_pre)


def _digitos_terminantes(resto: int, denominador: int, largo: int) -> str:
    out = []
    r = resto
    for _ in range(largo):
        r *= 10
        out.append(str(r // denominador))
        r %= denominador
    return "".join(out)


def _orden_multiplicativo(m: int, trace: Trace) -> tuple[int, int]:
    """Smallest ``k > 0`` with ``10^k ≡ 1 (mod m)``, and ``10^k mod m``."""
    if m == 1:
        return 1, 1
    valor = 10 % m
    for k in range(1, MAX_CIFRAS_PERIODO + 1):
        if valor == 1:
            return k, valor
        trace.regla(
            "decimal.orden", f"10^{k} módulo {m}",
            before=str((10 ** (k - 1)) % m), after=str((10 * ((10 ** (k - 1)) % m)) % m),
            piece=f"potencia {k} de 10 módulo {m}",
            why=("se multiplica por 10 cada vez; el primer 1 que aparece es el orden "
                 "multiplicativo, que es la longitud del periodo"),
        )
        valor = (valor * 10) % m
    raise _error("EXPRESSION_LIMIT", f"no se encontró el orden de 10 módulo {m}")


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------


def verificar_operacion(f: Fraction, operacion: str, a: Fraction,
                        b: Fraction) -> V.Seal:
    """Re-do the operation with the host's own ``Fraction`` and compare exactly."""
    try:
        esperado = {"+": lambda: a + b, "-": lambda: a - b,
                    "*": lambda: a * b, "/": lambda: a / b}[operacion]()
    except ZeroDivisionError:
        return V.Seal(V.DISCREPANT, "división por cero", "el segundo operando es cero")
    return V.verify_against(
        _como_expresion(f), _como_expresion(esperado))


def _como_expresion(f: Fraction):
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    return mx.num(f)
