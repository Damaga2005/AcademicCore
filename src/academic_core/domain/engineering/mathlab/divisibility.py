# SPDX-License-Identifier: MIT
"""MATH_LAB ML-1: divisibility, factorisation and primality.

The «MCD, MCM y factorización en primos» calculator of §8.2 A, plus the v2
additions of §4.0:

    σ(n), números perfectos, criba de Eratóstenes, primalidad hasta √n con el
    número de operaciones contado, dígitos y letra del DNI

What is worth stating about the design
--------------------------------------

**The factor tree is the answer, and it is built as data** (``ArbolDeFactores``),
because §4.0 asks for it as the exercise's graph. A list of prime factors
printed as text cannot be drawn; a tree can.

**Primality by trial division up to √n is proven, not sampled.** The test stops
at the first divisor found, so a number declared prime has been *checked* over
the whole range, and the count of divisions is reported. That count is the point
of the exercise: it is what makes the sieve better, and §5.5b asks the engine to
say why one method was chosen over the other. :func:`es_primo` and
:func:`criba` both exist precisely so the two can be compared.

**The DNI letter is a table lookup with a hypothesis.** ``resto mod 23`` maps to
``TRWAGMYFPDXBNJZSQVHLCKE``; the letter is the one at index ``resto``. The
hypothesis of §5.7 is that the number given is a valid 8-digit DNI — a wrong
length or a non-digit is refused rather than padded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.engineering.mathlab import fractions as FR
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

MAX_NUMERO = 10 ** 12
MAX_CRIBA = 10 ** 6

#: the DNI letter table of §4.0: index = remainder of the number mod 23
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def _error(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def _entero(valor: object, que: str = "el número") -> int:
    n = FR._entero(valor, que)
    if abs(n) > MAX_NUMERO:
        raise _error("EXPRESSION_LIMIT", f"{que} supera {MAX_NUMERO}")
    return n


# ---------------------------------------------------------------------------
# factorisation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArbolDeFactores:
    """A prime factorisation as a tree, so §4.0 can draw it."""

    numero: int
    primo: bool
    factores: tuple[tuple[int, int], ...] = ()   # (prime, exponent), sorted
    hijos: tuple["ArbolDeFactores", ...] = ()

    @property
    def texto(self) -> str:
        if not self.factores:
            # 0 and 1 have no prime factors; saying so beats printing nothing
            return str(self.numero)
        partes = []
        for p, e in self.factores:
            partes.append(f"{p}^{e}" if e > 1 else str(p))
        return " · ".join(partes)


def mcm(a: object, b: object, trace: Trace | None = None) -> int:
    """Least common multiple, from the identity ``mcm·mcd = |a·b|``."""
    trace = trace if trace is not None else Trace()
    x, y = _entero(a, "el primer número"), _entero(b, "el segundo número")
    if x == 0 or y == 0:
        trace.metodo("mcm.con_cero", "si uno de los números es cero, mcm = 0",
                     why="cualquier múltiplo de cero es cero, y el mínimo común es 0",
                     before=f"mcm({x}, {y})", after="0")
        return 0
    comun = FR.mcd(x, y, trace)
    comun = abs(comun)
    producto = abs(x * y)
    resultado = producto // comun
    trace.regla("mcm.identidad", "mcm a partir del mcd",
                before=f"mcm({x}, {y})", after=str(resultado),
                why=(f"mcm({x}, {y}) = |{x}·{y}| / mcd = {producto} / {comun}; la identidad "
                     "mcm·mcd = |a·b| vale porque los factores comunes se cuentan dos veces "
                     "en el producto y una sola en el mcm"),
                conditions=(f"mcd({x}, {y}) = {comun}",))
    return resultado


def factorizar(n: object, trace: Trace | None = None) -> ArbolDeFactores:
    """Prime factorisation by trial division, building the tree as it goes.

    Trial division is chosen because it is the method a first-year student can
    do by hand and *verify*; the sieve is the faster method and
    :func:`comparar_primalidad` puts the two side by side.
    """
    trace = trace if trace is not None else Trace()
    valor = _entero(n, "el número a factorizar")
    if valor < 0:
        trace.metodo("factorizar.signo", "se factoriza el valor absoluto",
                     why="un número negativo tiene los mismos factores primos que su "
                         "opuesto; el signo se registra aparte",
                     before=str(valor), after=str(-valor))
        valor = -valor
    if valor in (0, 1):
        trace.metodo("factorizar.trivial", f"{valor} no tiene factorización prima",
                     why=("0 y 1 no son primos y no se descomponen en primos; es parte de "
                          "la definición de primo"),
                     before=str(valor), after=str(valor))
        return ArbolDeFactores(valor, False, ())
    if _es_primo_silencioso(valor):
        trace.metodo("factorizar.ya_primo", f"{valor} es primo: no hay nada que descomponer",
                     why=("no se encuentra ningún divisor entre 2 y √n, y todo número "
                          "compuesto tiene uno, así que es primo"),
                     before=str(valor), after=str(valor))
        return ArbolDeFactores(valor, True, ((valor, 1),))
    factors: dict[int, int] = {}
    resto = valor
    divisor = 2
    while divisor * divisor <= resto:
        # extract this divisor as many times as it divides, *then* move on:
        # incrementing inside the inner loop would skip a factor
        while resto % divisor == 0:
            factors[divisor] = factors.get(divisor, 0) + 1
            resto //= divisor
            trace.regla("factorizar.paso",
                        f"se extrae un factor {divisor} (queda {resto})",
                        before=f"{resto * divisor} = {divisor} · {resto}", after=str(resto),
                        piece=f"factor {divisor}",
                        conditions=(f"el cociente {resto} sigue siendo divisible por {divisor}"
                                    if resto % divisor == 0 else
                                    f"el cociente {resto} ya no es divisible por {divisor}",),
                        why=("se repite mientras el divisor siga dividiendo el resto, y se "
                             f"para cuando llega a √{resto}: más allá, cualquier factor que "
                             "quedara sería mayor que su raíz y ya tendría un divisor propio "
                             "menor, que ya se habría encontrado"))
        divisor += 1 if divisor == 2 else 2  # after 2, only odd candidates
    if resto > 1:
        factors[resto] = 1
        trace.regla("factorizar.resto", f"el resto {resto} es primo",
                    before=str(resto), after=str(resto),
                    why=(f"{resto} es primo porque no tiene divisores hasta "
                         f"{int(resto ** 0.5)}, y todo compuesto los tiene"))
    orden = tuple(sorted(factors.items()))
    producto = 1
    for p, e in orden:
        producto *= p ** e
    if producto != valor:
        raise _error("INTERNAL", "la factorización no reproduce el número")
    arbol = _rama(valor)
    trace.regla("factorizar.resultado", "factorización en primos",
                before=str(valor), after=arbol.texto,
                why=(f"el producto de los factores con su exponente reproduce el número: "
                     f"{arbol.texto} = {valor}, que es la comprobación de que la "
                     "descomposición es correcta"))
    return arbol


def _menor_primo(n: int) -> int:
    d = 2
    while d * d <= n:
        if n % d == 0:
            return d
        d += 1 if d == 2 else 2
    return n


def _rama(n: int) -> ArbolDeFactores:
    """Build the factor tree by extraction, the way it is drawn on paper.

    A node is either a prime (a leaf) or a composite whose children are the
    extracted prime and the remaining quotient. Building it recursively from the
    number — not from a factor list — keeps the tree the same shape a student
    would draw, and it terminates because the quotient is strictly smaller.
    """
    if n < 2:
        raise _error("INTERNAL", "no se puede construir el árbol de 0 o 1")
    if _es_primo_silencioso(n):
        return ArbolDeFactores(n, True, ((n, 1),))
    p = _menor_primo(n)
    cociente = n // p
    hijos: tuple[ArbolDeFactores, ...] = (
        (ArbolDeFactores(p, True, ((p, 1),)),) if cociente == 1
        else (ArbolDeFactores(p, True, ((p, 1),)), _rama(cociente))
    )
    factores = _factores_propios(n)
    return ArbolDeFactores(n, False, factores, hijos)


def _factores_propios(n: int) -> tuple[tuple[int, int], ...]:
    salida: dict[int, int] = {}
    resto = n
    d = 2
    while d * d <= resto:
        while resto % d == 0:
            salida[d] = salida.get(d, 0) + 1
            resto //= d
        d += 1 if d == 2 else 2
    if resto > 1:
        salida[resto] = salida.get(resto, 0) + 1
    return tuple(sorted(salida.items()))


def _es_primo_silencioso(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def es_primo(n: object, trace: Trace | None = None) -> tuple[bool, int]:
    """``(es primo, número de divisiones)`` — the count is part of the answer."""
    trace = trace if trace is not None else Trace()
    valor = _entero(n, "el número")
    if valor < 2:
        trace.metodo("primo.menor_que_dos", f"{valor} no es primo",
                     why="por definición, 1 no es primo y los negativos se estudian por "
                         "su valor absoluto",
                     before=str(valor), after="no")
        return False, 0
    divisiones = 0
    if valor % 2 == 0:
        if valor == 2:
            trace.metodo("primo.dos", "2 es primo", why="es el único primo par",
                         before="2", after="primo")
            return True, 1
        trace.metodo("primo.par", f"{valor} es par y mayor que 2: no es primo",
                     why="todo par mayor que 2 tiene el divisor 2",
                     before=str(valor), after="compuesto")
        return False, 1
    d = 3
    while d * d <= valor:
        divisiones += 1
        if valor % d == 0:
            trace.regla("primo.divisor", f"{valor} = {d} · {valor // d}",
                        before=str(valor), after=f"{d} · {valor // d}",
                        piece=f"divisor {d}",
                        why=("ha aparecido un divisor propio, que es exactamente la "
                             "definición de número compuesto"),
                        conditions=(f"1 < {d} < {valor}",))
            return False, divisiones
        d += 2
    trace.regla("primo.sin_divisores",
                f"{valor} no tiene divisores hasta {int(valor ** 0.5)}: es primo",
                before=f"divisiones hasta {int(valor ** 0.5)}", after="primo",
                conditions=(f"{divisiones} divisiones realizadas",),
                why=("todo número compuesto tiene un divisor no trivial menor o igual "
                     f"que su raíz cuadrada, así que recorrerlos todos hasta "
                     f"{int(valor ** 0.5)} es una prueba, no una conjetura"))
    return True, divisiones


def criba(limite: int, trace: Trace | None = None) -> list[int]:
    """Sieve of Eratosthenes: the primes up to ``limite``, with the crossing-out."""
    trace = trace if trace is not None else Trace()
    n = _entero(limite, "el límite")
    if not 2 <= n <= MAX_CRIBA:
        raise _error("EXPRESSION_LIMIT", f"el límite debe estar entre 2 y {MAX_CRIBA}")
    marcas = [True] * (n + 1)
    marcas[0] = marcas[1] = False
    tachados = 0
    p = 2
    while p * p <= n:
        if marcas[p]:
            for multiplo in range(p * p, n + 1, p):
                if marcas[multiplo]:
                    marcas[multiplo] = False
                    tachados += 1
            trace.regla("criba.tacha",
                        f"se tachan los múltiplos de {p} desde {p}²",
                        before=f"{marcas.count(True)} primos vivos",
                        after=f"{marcas.count(True)} primos vivos",
                        piece=f"p = {p}",
                        conditions=(f"se empieza en {p}·{p} porque los múltiplos menores ya "
                                    "fueron tachados por primos más pequeños",),
                        why=("cualquier múltiplo de p mayor que p tiene un factor primo menor "
                             "o igual que p, así que ya estaba tachado; empezar en p² evita "
                             "repetir trabajo"),
                    )
        p += 1
    primos = [i for i, vivo in enumerate(marcas) if vivo]
    trace.regla("criba.resultado", f"primos hasta {n}",
                before=str(n), after=f"{len(primos)} primos",
                conditions=(f"{tachados} números tachados",),
                why=(f"la criba necesita {tachados} tachados, mientras que probar cada "
                     f"número por separado costaría del orden de {n // 2} divisiones; por "
                     "eso la criba es la razón de ser del ejercicio"),
                alternatives=(
                    ("probar cada número por separado",
                     "es correcto pero hace muchas más divisiones, y no se puede reutilizar "
                     "el trabajo ya hecho"),
                ))
    return primos


def sigma(n: object, trace: Trace | None = None) -> int:
    """Sum of the positive divisors of ``n`` (the v2 addition of §4.0)."""
    trace = trace if trace is not None else Trace()
    valor = _entero(n, "el número")
    if valor < 1:
        raise _error("BAD_INPUT", "σ(n) se define para n ≥ 1")
    if valor == 1:
        trace.metodo("sigma.uno", "σ(1) = 1", why="1 solo es divisor de sí mismo",
                     before="1", after="1")
        return 1
    arbol = factorizar(valor, trace)
    total = 1
    detalle = []
    for p, e in arbol.factores:
        suma = sum(p ** k for k in range(e + 1))
        total *= suma
        detalle.append(f"({' + '.join(str(p ** k) for k in range(e + 1))}) = {suma}")
    # the divisors of a product of coprime powers multiply out: that is the
    # formula, so the divisors themselves are not listed one by one
    trace.regla("sigma.formula", "σ por la fórmula del producto",
                before=str(valor), after=str(total),
                piece=" · ".join(detalle),
                why=("si n = Πpᵢ^eᵢ, cada divisor elige un exponente de 0 a eᵢ en cada "
                     "factor primo de forma independiente, así que σ(n) = Π(1 + p + … + "
                     f"p^e) = {total}; comprobarlo exige que los factores sean coprimos, "
                     "que es lo que garantiza ser primos distintos"))
    return total


def es_numero_perfecto(n: object, trace: Trace | None = None) -> tuple[bool, int, int]:
    """``(es perfecto, σ(n), suma de los divisores propios)``."""
    trace = trace if trace is not None else Trace()
    valor = _entero(n, "el número")
    total = sigma(valor, trace)
    propios = total - valor
    if valor < 2:
        trace.metodo("perfecto.menor", f"{valor} no puede ser perfecto",
                     why="un número perfecto es mayor que 1 por definición",
                     before=str(valor), after="no")
        return False, total, propios
    if propios == valor:
        trace.regla("perfecto.si", f"{valor} es un número perfecto",
                    before=f"σ({valor}) = {total}", after="perfecto",
                    why=(f"la suma de los divisores propios es {propios}, igual que {valor}: "
                         "esa es la definición, y 6, 28, 496 y 8128 son los primeros"))
    else:
        trace.regla("perfecto.no", f"{valor} no es un número perfecto",
                    before=f"σ({valor}) = {total}", after="no",
                    why=f"la suma de los divisores propios es {propios}, distinta de {valor}")
    return propios == valor, total, propios


def letra_dni(numero: object, trace: Trace | None = None) -> str:
    """The DNI letter: the number modulo 23 indexes the official table."""
    trace = trace if trace is not None else Trace()
    if isinstance(numero, str):
        texto = numero.strip().upper().replace(" ", "").replace("-", "")
        if texto and texto[-1].isalpha():
            texto = texto[:-1]  # the student typed the letter as well
        if not texto.isdigit():
            raise _error("BAD_INPUT", f"el DNI debe tener cifras: {numero!r}")
        valor = int(texto)
    else:
        valor = _entero(numero, "el número del DNI")
    if not 0 <= valor <= 99_999_999:
        raise _error("BAD_INPUT", "un DNI tiene entre 1 y 8 cifras")
    resto = valor % 23
    letra = LETRAS_DNI[resto]
    trace.regla("dni.letra", f"letra del DNI de {valor}",
                before=f"{valor} mod 23 = {resto}", after=letra,
                conditions=(f"índice {resto} dentro de la tabla de 23 letras",),
                why=("la tabla oficial «TRWAGMYFPDXBNJZSQVHLCKE» tiene 23 letras en el orden "
                     "legal y la letra es la de índice resto; el resto 0 corresponde a la "
                     "T y el 22 a la E, y el 23 no se usa porque no hay resto 23"),
                )
    return letra


def comparar_primalidad(n: int, trace: Trace | None = None) -> dict:
    """The two primality methods side by side, with their cost (§5.5b).

    The sieve decides primality of a *large* ``n`` by sieving only up to √n and
    checking divisibility by the primes found — sieving up to ``n`` would be
    correct but absurdly slow, and that choice is the substance of the exercise.
    """
    trace = trace if trace is not None else Trace()
    es, divisiones = es_primo(n, trace)
    limite = min(int(n ** 0.5) + 2, MAX_CRIBA)
    primos_hasta_raiz = criba(limite, trace)
    # p < n matters: 2 is a divisor of itself, and 2 is prime
    divisores = [p for p in primos_hasta_raiz if p < n and n % p == 0]
    por_criba = not divisores and n > 1
    trace.metodo(
        "primalidad.comparacion",
        f"prueba directa: {divisiones} divisiones; criba hasta {limite} y "
        f"{len(primos_hasta_raiz)} comprobaciones de divisibilidad",
        why=("las dos pruebas son exactas, así que la elección es de coste: la criba paga "
             "una sola vez para todos los números hasta el límite y por eso conviene a un "
             "curso; la prueba directa no necesita memoria y es la que se hace a mano para "
             "un número suelto. Ambas se detienen en √n, que es la hipótesis común: todo "
             "compuesto tiene un divisor propio no mayor que su raíz"),
        before=str(n),
        after=f"primo por división: {es}; primo por criba: {por_criba}",
        alternatives=(
            ("cribar hasta n en vez de hasta √n",
             "daría la misma respuesta con muchísimo más trabajo y memoria"),
            ("confiar en que «no parece divisible»",
             "no es una prueba: habría que comprobar hasta √n"),
        ),
    )
    if es != por_criba:
        raise _error("INTERNAL", f"las dos pruebas de primalidad discrepan: {es} vs "
                                 f"{por_criba} (divisores de la criba: {divisores})")
    return {"n": n, "es_primo": es, "divisiones": divisiones, "por_criba": por_criba,
            "limite_criba": limite}
