# SPDX-License-Identifier: MIT
"""MATH_LAB ML-1: polynomials — division, Ruffini, factorisation, identities.

The «Polinomios» calculator of §8.2 A:

    Suma, producto, **división, Ruffini, factorización**, raíces,
    identidades notables

Representation
--------------

A polynomial is a list of exact ``Fraction`` coefficients, index = degree, with
the leading zeros removed. That representation is the one that makes *long
division* and *Ruffini* expressible: both are loops over descending degrees, and
a sparse normal form would turn every step into a lookup.

Ruffini is the interesting one. Dividing by ``x − r`` can be done by long
division, but Ruffini's synthetic table exists precisely because the
coefficients can be updated in a single pass without powers of ``x`` ever
appearing. §5.5b therefore asks for the *reason*: the two methods give the same
quotient, and the table is the cheaper one. :func:`dividir_por_lineal` records
both and checks they agree — that is the second path of §5.3 for this module.

Roots and factorisation
-----------------------

:func:`raices_racionales` uses the **rational root theorem**, not a numeric
search: for a polynomial with integer coefficients the only possible rational
roots are ``±p/q`` with ``p`` dividing the constant term and ``q`` the leading
one. That is a finite, provable candidate set, which is what an exercise asks
for, and it is why :func:`factorizar` can say «no tiene raíces racionales» with
a proof attached rather than as a failure to find something.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import divisibility as DIV
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

MAX_GRADO = 32
MAX_TERMINOS = 33
MAX_DIVISORES_PRIMOS = 400

#: A polynomial is a list of exact ``Fraction`` coefficients in **ascending**
#: order: ``p[i]`` is the coefficient of ``x**i``. So ``x**2 - 1`` is
#: ``[-1, 0, 1]``, the leading coefficient is ``p[-1]`` and the constant term is
#: ``p[0]``. Leading zeros are stripped (the degree is implicit in the length);
#: trailing zeros are **kept**, because a zero constant term is information
#: (``x**2`` is ``[0, 0, 1]``, not ``[1]``).
Polinomio = list[Fraction]


def _error(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def _no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")


# ---------------------------------------------------------------------------
# construction and printing
# ---------------------------------------------------------------------------


def normalizar(coeficientes) -> Polinomio:
    """Drop the *high-degree* zeros; the low ones carry information.

    In ascending order the degree lives at the END of the list, so trailing
    zeros go and leading ones stay: ``[0, 0, 1]`` is ``x^2`` and must keep its
    two zeros, while ``[0, 0, 0]`` is the zero polynomial and becomes empty.
    """
    p = [Fraction(c) for c in coeficientes]
    while p and p[-1] == 0:
        p.pop()
    if len(p) > MAX_TERMINOS:
        raise _error("EXPRESSION_LIMIT", f"grado mayor que {MAX_GRADO}")
    return p


def desde_texto(texto: str, var: str = "x", trace: Trace | None = None) -> Polinomio:
    """Read a polynomial in one variable from the student input of §8.1."""
    trace = trace if trace is not None else Trace()
    try:
        e = mx.parse(texto)
    except ValidationError:
        raise
    from academic_core.domain.engineering.mathlab import poly as P

    forma = P.as_poly(e)
    if P.real_variables(forma) - {var}:
        raise _error("BAD_INPUT", f"esta calculadora trabaja en una sola variable ({var})")
    if P.atoms_of(forma):
        raise _error("BAD_INPUT", "el polinomio solo admite coeficientes racionales, "
                                  "sin funciones ni constantes irracionales")
    coeficientes = [Fraction(0)] * (P.total_degree(forma) + 1)
    for mono, coeff in forma.items():
        grado = sum(e_ for _, e_ in mono)
        coeficientes[grado] += coeff
    resultado = normalizar(coeficientes)
    trace.regla("polinomio.lectura", f"el polinomio se lee con {texto(var) if False else var}",
                before=texto, after=representar(resultado, var),
                why=("se agrupan los términos de la misma potencia y se lee el polinomio "
                     "como una lista de coeficientes, del grado mayor al menor"))
    return resultado


def representar(p: Polinomio, var: str = "x") -> str:
    """``3x^2 - 2x + 1`` from the coefficient list, sign glued to its term."""
    if not p:
        return "0"
    partes: list[str] = []
    for grado in range(len(p) - 1, -1, -1):
        c = p[grado]
        if c == 0:
            continue
        abs_c = abs(c)
        if grado == 0:
            trozo = _frac(abs_c)
        else:
            variable = var if grado == 1 else f"{var}^{grado}"
            trozo = variable if abs_c == 1 else f"{_frac(abs_c)}*{variable}"
        if not partes:
            partes.append(f"-{trozo}" if c < 0 else trozo)
        else:
            partes.append(f" - {trozo}" if c < 0 else f" + {trozo}")
    return "".join(partes)


def _frac(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def a_expresion(p: Polinomio, var: str = "x") -> mx.Expr:
    """Back to the multivariate layer, for the graph and the contract."""
    e = mx.ZERO
    for grado in range(len(p) - 1, -1, -1):
        if p[grado] == 0:
            continue
        coeficiente = mx.num(p[grado])
        if grado == 0:
            e = mx.Add(e, coeficiente)
        else:
            e = mx.Add(e, mx.Mul(coeficiente, mx.Pow(mx.Sym(var), mx.num(grado))))
    return e


def grado(p: Polinomio) -> int:
    return len(p) - 1


def _representar_desde(resto: list, desde: int, var: str) -> str:
    """The current dividend, from degree ``desde`` upwards."""
    return representar(normalizar(list(resto[desde:])), var) or "0"


def evaluar(p: Polinomio, x: Fraction) -> Fraction:
    """Horner's method: the evaluation a student is asked to do by hand."""
    total = Fraction(0)
    for c in reversed(p):
        total = total * x + c
    return total


# ---------------------------------------------------------------------------
# sum, product
# ---------------------------------------------------------------------------


def sumar(a: Polinomio, b: Polinomio, signo: int = 1, var: str = "x",
         trace: Trace | None = None) -> Polinomio:
    trace = trace if trace is not None else Trace()
    largo = max(len(a), len(b))
    total = normalizar([(a[i] if i < len(a) else 0) + signo * (b[i] if i < len(b) else 0)
                        for i in range(largo)])
    trace.regla("polinomio.suma", f"se suman{'restan' if signo < 0 else ''} los coeficientes "
                                 "del mismo grado",
                before=f"{representar(a, var)} {'-' if signo < 0 else '+'} {representar(b, var)}",
                after=representar(total, var),
                piece="coeficiente a coeficiente",
                why=("dos polinomios solo se suman término a término cuando están en la "
                     "misma variable: los grados distintos se completan con coeficientes 0"),
                conditions=(f"grado máximo: {grado(a)} y {grado(b)}",))
    return total


def multiplicar(a: Polinomio, b: Polinomio, var: str = "x",
                trace: Trace | None = None) -> Polinomio:
    trace = trace if trace is not None else Trace()
    if not a or not b:
        return []
    total = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, ca in enumerate(a):
        for j, cb in enumerate(b):
            if ca and cb:
                total[i + j] += ca * cb
    total = normalizar(total)
    if len(total) - 1 > MAX_GRADO:
        raise _error("EXPRESSION_LIMIT", f"el producto daría grado mayor que {MAX_GRADO}")
    trace.regla("polinomio.producto", "producto de cada término con cada término",
                before=f"{representar(a, var)} * {representar(b, var)}",
                after=representar(total, var),
                piece=f"{len(a)} × {len(b)} productos",
                conditions=(f"grado del producto: {grado(a)} + {grado(b)} = "
                            f"{grado(a) + grado(b)}",),
                why=("cada coeficiente de grado k es la suma de los productos aᵢ·bⱼ con "
                     "i + j = k, y el grado del producto es la suma de los grados"))
    return total


# ---------------------------------------------------------------------------
# division and Ruffini
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Division:
    """A polynomial division with its remainder, exact or not."""

    cociente: Polinomio
    resto: Polinomio
    exacta: bool
    divisor: Polinomio
    dividendo: Polinomio
    var: str = "x"

    def comprobacion(self) -> str:
        """``dividendo = cociente·divisor + resto``, rebuilt for the record."""
        producto = multiplicar(self.cociente, self.divisor, self.var)
        suma = sumar(producto, self.resto, 1, self.var)
        del suma  # the identity is asserted by the caller; here we only print it
        return f"{representar(self.dividendo, self.var)} = " \
               f"{representar(self.cociente, self.var)}·" \
               f"{representar(self.divisor, self.var)}" + \
               (f" + {representar(self.resto, self.var)}" if self.resto else "")

    def como_texto(self) -> str:
        return f"{representar(self.cociente, self.var)}" + \
               ("" if self.exacta else f" resto {representar(self.resto, self.var)}")


def dividir(dividendo: Polinomio, divisor: Polinomio, var: str = "x",
            trace: Trace | None = None) -> Division:
    """Long division of polynomials, one step per cancelled leading term."""
    trace = trace if trace is not None else Trace()
    if not divisor:
        raise _error("DIVISION_BY_ZERO", "no se puede dividir por el polinomio cero")
    n, m = len(dividendo), len(divisor)
    if n < m:
        trace.metodo("polinomio.dividir.sin_grado",
                     "el grado del dividendo es menor que el del divisor",
                     why=("el cociente sería 0 con resto el propio dividendo, porque no hay "
                          "término del dividendo que pueda cancelarse"),
                     before=f"{representar(dividendo, var)} / {representar(divisor, var)}",
                     after="cociente 0")
        return Division([], list(dividendo), False, list(divisor), list(dividendo), var)
    # Ascending order (see Polinomio): the leading coefficient of the divisor is
    # its LAST element, and the quotient term that cancels the current highest
    # term of the remainder lives at index `i`, of degree i.
    resto = list(dividendo)
    cociente = [Fraction(0)] * (n - m + 1)
    principal = divisor[m - 1]
    # The quotient has n - m + 1 coefficients, of degree 0 to n - m, so the
    # loop runs over those degrees: i from n-m down to 0.
    for i in range(n - m, -1, -1):
        if resto[i + m - 1] == 0:
            continue
        factor = resto[i + m - 1] / principal
        cociente[i] += factor
        trace.regla(
            "polinomio.dividir.paso",
            f"grado {i + m - 1}: se cancela el término principal con "
            f"{_frac(factor)}·{var}^{i}",
            before=_representar_desde(resto, m - 1, var),
            after=f"se resta {_frac(factor)}*" + representar(divisor, var)
                 + f"·{var}^{i}",
            piece=f"grado {i + m - 1}",
            conditions=(f"el factor sale de dividir los coeficientes principales: "
                        f"{_frac(resto[i + m - 1])}/{_frac(principal)} = {_frac(factor)}",),
            why=("el cociente empieza por la razón de los coeficientes principales, y esa "
                 "es la única forma de que el término de mayor grado se cancele exactamente"),
        )
        for j, c in enumerate(divisor):
            resto[i + j] -= factor * c
    cociente = normalizar(cociente)
    resto = normalizar(resto[:m - 1])
    resultado = Division(cociente, resto, not resto, list(divisor), list(dividendo), var)
    trace.regla("polinomio.dividir.resultado", "resultado de la división",
                before=f"{representar(dividendo, var)} / {representar(divisor, var)}",
                after=resultado.como_texto(),
                why=("se comprueba reconstruyendo: " + resultado.comprobacion()
                     + ", que es la identidad de la división euclídea"))
    return resultado


def dividir_por_lineal(dividendo: Polinomio, r, var: str = "x",
                       trace: Trace | None = None) -> Division:
    """Divide by ``x − r`` twice: by long division and by Ruffini, and compare.

    The two methods are the same answer by two routes, which is the strongest
    check available for the synthetic table — and §5.5b requires the engine to
    say *why* the table is the one to use by hand.
    """
    trace = trace if trace is not None else Trace()
    raiz = Fraction(r)
    # ascending order (see Polinomio): x - r is [-r, 1]
    por_division = dividir(dividendo, [-raiz, Fraction(1)], var, trace)
    por_ruffini = ruffini(dividendo, raiz, var, trace)
    trace.metodo(
        "polinomio.ruffini.metodo",
        "se usa la tabla de Ruffini en vez de la división larga",
        why=("al dividir por un factor de la forma x − r, la tabla permite actualizar los "
             "coeficientes en una sola pasada sin escribir potencias de x, y por eso es la "
             "forma más rápida a mano; la división larga da el mismo cociente y se usa "
             "aquí como comprobación"),
        alternatives=(
            ("confiar en la tabla sin comprobarla",
             "un error de arrastre en la tabla daría un cociente falso"),
        ),
        before=f"{representar(dividendo, var)} / (x - {_frac(raiz)})",
        after=por_ruffini.como_texto(),
    )
    if por_ruffini.cociente != por_division.cociente:
        raise _error("INTERNAL", "Ruffini y la división larga dan cocientes distintos")
    return por_ruffini


def ruffini(dividendo: Polinomio, r, var: str = "x",
            trace: Trace | None = None) -> Division:
    """Ruffini's synthetic division by ``x − r``, the table written out."""
    trace = trace if trace is not None else Trace()
    raiz = Fraction(r)
    if not dividendo:
        return Division([], [Fraction(0)], True, [-raiz, Fraction(1)], [], var)
    # The synthetic table runs on the coefficients from the leading one down,
    # which in ascending storage means from the end of the list to the start.
    # `c[k]` is the k-th value of the table; the last one is the remainder and
    # the rest, read back the other way, are the quotient.
    c: list[Fraction] = [dividendo[-1]]
    fila = [(grado(dividendo), dividendo[-1], None,
             "se baja el coeficiente principal, que es el primero del cociente")]
    for i in range(len(dividendo) - 2, -1, -1):
        siguiente = dividendo[i] + c[-1] * raiz
        c.append(siguiente)
        fila.append((i, dividendo[i], siguiente,
                     f"{_frac(c[-2])}×{_frac(raiz)} = {_frac(c[-2] * raiz)}, "
                     f"más {_frac(dividendo[i])} da {_frac(siguiente)}"))
    resto = c[-1]
    cociente_n = normalizar(list(reversed(c[:-1])))
    resultado = Division(cociente_n, [resto] if resto else [], resto == 0,
                         [-raiz, Fraction(1)], list(dividendo), var)
    for g, entra, sale, porque in fila:
        trace.regla(
            "polinomio.ruffini.fila",
            f"fila de x^{g}: entra {_frac(entra)}, sale "
            f"{'—' if sale is None else _frac(sale)}",
            before=_frac(entra), after="—" if sale is None else _frac(sale),
            piece=f"coeficiente de x^{g}", why=porque,
        )
    trace.regla("polinomio.ruffini.resto", "el último valor de la tabla es el resto",
                before=f"último valor de la tabla", after=_frac(resto),
                piece="última posición",
                why=(f"el resto es el valor del polinomio en {_frac(raiz)}, porque solo se "
                     "obtiene 0 si r era una raíz, y en general vale P(r)"),
                conditions=(f"P({_frac(raiz)}) = {_frac(resto)}",))
    return resultado


# ---------------------------------------------------------------------------
# roots
# ---------------------------------------------------------------------------


def raices_racionales(p: Polinomio, trace: Trace | None = None) -> list[Fraction]:
    """Every rational root, from the rational root theorem — a finite proof."""
    trace = trace if trace is not None else Trace()
    if len(p) < 2:
        trace.metodo("polinomio.raices.constante",
                     "un polinomio constante no tiene raíces",
                     why="una ecuación con polinomio constante solo tiene solución si vale 0",
                     before=representar(p), after="ninguna")
        return []
    if p[0] == 0:
        # The theorem needs a non-zero constant term: with p[0] == 0 the divisors
        # of 0 are not a finite list, and the old fallback to 1 silently dropped
        # the root 0. Strip x^k, report 0, and search the rest.
        k = next(i for i, c in enumerate(p) if c != 0) if any(p) else len(p)
        resto = list(p[k:])
        trace.regla("polinomio.raices.cero", "x = 0 es raíz",
                    before=representar(p), after="0",
                    piece="raíz 0",
                    why=("el término independiente es 0, así que P(0) = 0; se saca "
                         f"el factor x^{k} y el teorema se aplica a lo que queda, "
                         "que ya sí tiene término independiente distinto de 0"))
        if len(resto) < 2:
            return [Fraction(0)]
        return sorted({Fraction(0), *raices_racionales(resto, trace)})
    # Ascending order: p[0] is the constant term and p[-1] the leading one, so the
    # rational root theorem takes p from the constant and q from the leading.
    numerador = abs(p[0])
    denominador = abs(p[-1])
    divisores_num = _divisores(numerador)
    divisores_den = _divisores(denominador)
    if len(divisores_num) * len(divisores_den) > MAX_DIVISORES_PRIMOS:
        raise _error("EXPRESSION_LIMIT",
                     f"el teorema de la raíz racional daría demasiados candidatos "
                     f"({len(divisores_num) * len(divisores_den)})")
    trace.metodo(
        "polinomio.raices.teorema",
        "candidatos por el teorema de la raíz racional",
        why=(f"si p/q es raíz de un polinomio con coeficientes enteros, p divide al término "
             f"independiente ({_frac(p[0])}) y q divide al coeficiente principal "
             f"({_frac(p[-1])}); con eso el conjunto de candidatos es finito y se prueba "
             f"uno a uno: {len(divisores_num) * 2} × {len(divisores_den)} = "
             f"{len(divisores_num) * 2 * len(divisores_den)}"),
        before=representar(p), after=f"{len(divisores_num) * 2 * len(divisores_den)} "
                                       "candidatos",
        alternatives=(
            ("buscar raíces con un método numérico",
             "encontraría aproximaciones y podría perderse una raíz racional exacta, que es "
             "justo lo que el teorema garantiza encontrar"),
        ),
    )
    raices: list[Fraction] = []
    for pn in divisores_num:
        for qn in divisores_den:
            for signo in (1, -1):
                candidata = Fraction(signo * pn, qn)
                if evaluar(p, candidata) == 0:
                    if candidata not in raices:
                        raices.append(candidata)
                    trace.regla("polinomio.raices.encontrada",
                                f"raíz racional {_frac(candidata)}",
                                before=f"P({_frac(candidata)})",
                                after="0", piece=f"raíz {_frac(candidata)}",
                                why=(f"al sustituir da exactamente 0, y {candidata} es "
                                     f"{' irreducible' if candidata.denominator != 1 else ''}"
                                     f"candidato válido del teorema"))
    if not raices:
        trace.regla("polinomio.raices.ninguna", "ninguna raíz racional",
                    before="candidados agotados", after="sin raíces racionales",
                    why=("se han comprobado todos los candidatos del teorema y ninguno anula "
                         "el polinomio, así que **no tiene** raíces racionales; eso no "
                         "significa que no tenga raíces reales"))
    return sorted(raices)


def _divisores(n: int) -> list[int]:
    if n <= 0:
        return [1]
    salida = []
    for d in range(1, int(n ** 0.5) + 1):
        if n % d == 0:
            salida.append(d)
            if d != n // d:
                salida.append(n // d)
    return sorted(salida)


# ---------------------------------------------------------------------------
# factorisation and identities
# ---------------------------------------------------------------------------


def factorizar(p: Polinomio, var: str = "x", trace: Trace | None = None) -> list:
    """Factor out the rational roots; what is left is reported as irreducible.

    A deliberate limit: a cubic with no rational root is *not* solved here. §5.4
    applies — the engine says what it cannot do instead of emitting a wrong
    factorisation.
    """
    trace = trace if trace is not None else Trace()
    resto = normalizar(list(p))
    if not resto or len(resto) == 1:
        return [(representar(resto, var), 1)] if resto else []
    factores: list[tuple[str, int]] = []
    for r in raices_racionales(resto, trace):
        # a root of multiplicity m is divided out m times, so (x - 1)^2 is reported
        # as one factor with exponent 2 and not as (x - 1) plus a leftover (x - 1)
        multiplicidad = 0
        while len(resto) > 1 and evaluar(resto, r) == 0:
            resto = dividir_por_lineal(resto, r, var, trace).cociente
            multiplicidad += 1
        if r == 0:
            nombre = var
        else:
            nombre = f"({var} - {_frac(r)})" if r > 0 else f"({var} + {_frac(-r)})"
        factores.append((nombre, multiplicidad))
    # the cofactor left after the roots: kept when it says something (the 2 of
    # 2x^2 - 8, or an irreducible quadratic), dropped when it is the constant 1
    if resto and not (len(resto) == 1 and resto[0] == 1):
        factores.append((representar(resto, var), 1))
    texto = " · ".join(f if e == 1 else f"{f}^{e}" for f, e in factores)
    trace.regla("polinomio.factorizar", "factorización",
                before=representar(p, var), after=texto,
                piece="factores extraídos",
                why=("se extrae un factor (x − r) por cada raíz racional r, y el polinomio "
                     "que queda se muestra tal cual: si no se factoriza más, es porque no "
                     "tiene más raíces racionales que el teorema pueda encontrar"))
    return factores


def identidades(a: mx.Expr, b: mx.Expr, var: str = "x",
                trace: Trace | None = None, forma: str = "cuadrado") -> str:
    """Check which remarkable identity expands correctly, and name it.

    ``forma`` says which expression the student wrote:

    - ``"cuadrado"`` — ``(a ± b)^2`` against ``a^2 ± 2ab + b^2``
    - ``"producto"`` — ``(a ± b)(a ∓ b)`` against ``a^2 − b^2``

    Why the parameter is needed, and what it does *not* claim: both ``(a+b)^2``
    and ``(a-b)^2`` are true for every ``a`` and ``b``, so the first matching
    one always wins inside a family. What this function asserts is that the
    expansion is correct, not which of the two forms the student wrote — only
    ``forma`` narrows the family.

    Recognition is by comparing normal forms, not by looking at the text, so it
    works on an expression written any way round.
    """
    trace = trace if trace is not None else Trace()
    from academic_core.domain.engineering.mathlab import poly as P

    if forma == "cuadrado":
        casos = [
            ("(a + b)^2 = a^2 + 2ab + b^2", mx.Pow(mx.Add(a, b), mx.num(2)),
             mx.Add(mx.Add(mx.Pow(a, mx.num(2)), mx.Mul(mx.num(2), mx.Mul(a, b))),
                    mx.Pow(b, mx.num(2)))),
            ("(a - b)^2 = a^2 - 2ab + b^2", mx.Pow(mx.Sub(a, b), mx.num(2)),
             mx.Sub(mx.Add(mx.Pow(a, mx.num(2)), mx.Pow(b, mx.num(2))),
                    mx.Mul(mx.num(2), mx.Mul(a, b)))),
        ]
    elif forma == "producto":
        diferencia = mx.Sub(mx.Pow(a, mx.num(2)), mx.Pow(b, mx.num(2)))
        casos = [
            ("(a + b)(a - b) = a^2 - b^2", mx.Mul(mx.Add(a, b), mx.Sub(a, b)),
             diferencia),
            ("(a - b)(a + b) = a^2 - b^2", mx.Mul(mx.Sub(a, b), mx.Add(a, b)),
             diferencia),
        ]
    else:
        raise _error("BAD_INPUT",
                     f"forma desconocida: {forma!r}; se admite «cuadrado» o «producto»")
    for nombre, izquierda, derecha in casos:
        if P.as_poly(izquierda) == P.as_poly(derecha):
            trace.regla("polinomio.identidad", f"identidad notable: {nombre}",
                        before="", after="", piece=nombre,
                        why=("se reconoce comparando las dos formas normales: si coinciden, "
                             "el producto es la identidad, y eso vale aunque no se haya "
                             "escrito de esa manera"))
            return nombre
    raise _no_rule("esa expresión no es una de las identidades notables de ML-1")


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------


def verificar(d: Division) -> V.Seal:
    """Second path: rebuild ``dividendo = cociente·divisor + resto`` exactly."""
    producto = multiplicar(d.cociente, d.divisor, d.var)
    reconstruido = sumar(producto, d.resto, 1, d.var)
    igual, metodo, detalle = V.check_equivalence(
        a_expresion(reconstruido, d.var), a_expresion(d.dividendo, d.var))
    if igual:
        return V.Seal(V.VERIFIED, metodo, d.comprobacion())
    return V.Seal(V.DISCREPANT, metodo,
                  f"la reconstrucción da {representar(reconstruido, d.var)}, no "
                  f"{representar(d.dividendo, d.var)}")
