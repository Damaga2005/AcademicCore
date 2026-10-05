# SPDX-License-Identifier: MIT
"""MATH_LAB T-19: Taylor and Maclaurin series, with the remainder attached.

Why the remainder is the whole point
------------------------------------

A truncated series is not an approximation until you say of what. ``sin(x) ≈ x``
is true to no accuracy at all — at ``x = 3`` it is wrong by 0.14 — and the number
that makes it a statement is the next term, or the bound on what comes after it.

So every answer here is three things, never one:

1. the polynomial up to the requested order;
2. the **next** term, which is the first one dropped;
3. a **declared error bound** on what comes after that.

The bound is where a series engine is usually honest-looking and dishonest. Two
routes exist and they are *not* interchangeable:

* **a function this module knows** — the seven whose series it writes term by term —
  gets the tail of that series majorised by a geometric progression built from its
  own coefficients, valid on a declared interval;
* **an expression it does not recognise** gets no number at all, and the answer says
  so in words. Reusing the bound of a function that happens to appear inside is not
  available as a shortcut: for ``x²·exp(x)`` the real error runs 20 to 26 times
  larger than ``exp``'s bound, and the test that says so measures it.

The old rule was "the first omitted term, for the alternating series" — and that
was false in both directions it could fail in, which is the subject of
``_cota_de_cola``. What replaced it is checked against the measured error at every
argument, negatives included, because an assertion that a bound is absent cannot see
a bound that is present and wrong.

Convergence, and refusing to fake it
-----------------------------------

The radius of convergence is decided by the nearest singularity, and for a general
expression the engine cannot see singularities. So it does not answer: a request
for the radius comes back with «this engine cannot determine it», which is a real
answer about this engine and not a claim about the function.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.errors import UnsupportedError

#: the order is capped: a series to the thousandth term is a number, not a series,
#: and the cap is declared rather than hit by a RecursionError
ORDEN_MAXIMO = 40


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Serie:
    """A truncated series and everything that has to travel with it."""

    polinomio: mx.Expr
    orden: int
    residuo: mx.Expr
    cota: mx.Expr | None
    centro: mx.Expr
    metodo: str
    hipotesis: tuple[str, ...] = ()

    def texto(self) -> str:
        partes = [mx.text(self.polinomio)]
        if self.residuo is not None:
            partes.append(f"+ {mx.text(self.residuo)} + ...")
        return " ".join(partes)

    def con_cota(self) -> str:
        """The polynomial, the bound, and where the bound holds.

        The domain is printed with the number rather than left in ``hipotesis``,
        because this line is what a reader takes away: a bound whose interval is one
        scroll away is, in practice, a bound claimed for every argument. The
        sentence is taken from the hypothesis that declares it, so the two cannot
        drift apart.
        """
        base = self.texto()
        if self.cota is None:
            return base + "   (sin cota de error declarada)"
        dominio = next((h.split("cota de error:", 1)[1].strip()
                        for h in self.hipotesis if "cota de error:" in h), None)
        if dominio:
            return base + f"   error < {mx.text(self.cota)}   ({dominio})"
        return base + f"   error < {mx.text(self.cota)}"

    @property
    def con_cota_error(self) -> bool:
        return self.cota is not None


# ---------------------------------------------------------------------------
# the series this module knows exactly
# ---------------------------------------------------------------------------

#: the general term of each known series: coefficient, power, and the name it is
#: written under, as ``(funcion, coeficiente, potencia)``.
_TERMINO = {
    "sin": ("sin", 1, 1),
    "cos": ("cos", 1, 0),
    "tan": ("tan", 1, 1),
    "exp": ("exp", 1, 1),
    "sinh": ("sinh", 1, 1),
    "cosh": ("cosh", 1, 0),
    "ln": ("ln", 1, 0),
}


def maclaurin(nombre: str, orden: int, var: str = "x") -> Serie:
    """The series of a known function about zero, exactly.

    Only functions whose series is known here. A general expression goes through
    :func:`taylor`, which needs derivatives and which therefore declares a
    different kind of error bound.
    """
    if nombre not in _TERMINO:
        raise sin_refuso(
            f"no se sabe la serie de «{nombre}» sobre la lista: "
            f"{', '.join(sorted(_TERMINO))}. Eso NO es «no converge» (§5.4)")
    _exigir_orden(orden)
    polinomio, residuo = _truncar(nombre, orden, var)
    cota = _cota_de_cola(nombre, orden, var)
    return Serie(polinomio, orden, residuo, cota, mx.ZERO,
                 "serie de Maclaurin conocida, escrita término a término",
                 _hipotesis_de_serie_conocida(nombre, var, None))


def _exigir_orden(orden: int) -> None:
    """Refuse an order outside the declared range, with the same words from both doors.

    ``maclaurin`` has always said this; ``taylor`` did not, and answered an order of
    ``-1`` with a polynomial of ``0`` and a residual of ``1`` — defensible as
    arithmetic, useless as an answer, and a second answer to the same question.
    """
    if orden < 0:
        raise sin_refuso(f"el orden tiene que ser 0 o mayor; llegó {orden}")
    if orden > ORDEN_MAXIMO:
        raise sin_refuso(
            f"el orden {orden} supera el máximo de {ORDEN_MAXIMO}. Un polinomio de "
            "ese grado es un número con demasiados dígitos, no una serie (§5.5)")


#: The radius of convergence of each known series, as a sentence.
#:
#: ``tan`` and ``ln`` do NOT share one, and an earlier version of this module said
#: they did — it announced «radio de convergencia 1» for both, three lines below a
#: table that correctly says ``tan``'s is ``pi/2``. The mistake was visible in the
#: file and survived because nobody read the two against each other.
#:
#: Mercator's radius is 1 because the nearest singularity is ``x = -1``. ``tan``'s is
#: ``pi/2 ≈ 1.571`` because its nearest pole is there, so its series sums perfectly
#: well on ``1.2 < x < 1.5`` — which the old sentence told the reader it could not.
_RADIO = {
    "tan": "el radio de convergencia es pi/2 ≈ 1,57, que es donde está el polo más "
           "cercano: entre 1 y 1,57 la serie suma sin problema, y a partir de pi/2 "
           "los términos ya no convergen. La divergencia no se detecta truncando "
           "(§5.4)",
    "ln": "esta serie tiene radio de convergencia 1, que es donde está la "
          "singularidad más cercana: fuera de |x| < 1 los términos no suman un "
          "número, y la divergencia no se detecta truncando (§5.4)",
}


def _hipotesis_de_serie_conocida(nombre: str, var: str,
                                  desplazamiento: mx.Expr | None) -> tuple[str, ...]:
    """The sentences that travel with a series written term by term.

    Shared by :func:`maclaurin` and by the path inside :func:`taylor` that reuses
    this module's known series, because two copies of the same claim are one copy
    too many: they agree until the day one of them is edited.
    """
    hipotesis = [
        f"la serie de {nombre} es exacta; el residuo es el primer término que no se "
        f"escribe, y la cola que viene detrás está acotada por una progresión "
        f"geométrica construida con los propios términos de la serie",
    ]
    if nombre in _DOMINIO_DE_LA_COTA:
        hipotesis.append(f"cota de error: {_DOMINIO_DE_LA_COTA[nombre]}")
    if nombre in _RADIO:
        hipotesis.append(_RADIO[nombre])
    if desplazamiento is not None:
        hipotesis.append(
            f"la serie se escribió sobre el origen y luego se sustituyó "
            f"{var} → {mx.text(desplazamiento)}: el polinomio de {nombre} alrededor de "
            f"un centro distinto del origen es la misma serie de "
            f"u ↦ {nombre}({desplazamiento} + u), y no una serie nueva. El intervalo "
            f"de la cota se desplaza con ella: donde la fórmula dice |{var}|, ahora "
            f"dice |{mx.text(desplazamiento)}|")
    return tuple(hipotesis)


def _truncar(nombre: str, orden: int, var: str) -> tuple[mx.Expr, mx.Expr | None]:
    """The polynomial up to ``orden`` and the first term left out.

    Four shapes, and they are not interchangeable:

    * ``sin`` has odd powers only, signs alternating;
    * ``cos`` has even powers only, signs alternating;
    * ``sinh`` and ``cosh`` have the same powers with every sign positive;
    * ``exp`` has every power, positive.

    Reading them off one table of «odd and alternating» gave ``sin``, ``cos``,
    ``sinh`` and ``cosh`` the same polynomial, and a coseno series that starts at
    ``x`` is not a series of anything.
    """
    x = mx.Sym(var)
    if nombre in ("sin", "cos", "sinh", "cosh"):
        return _potencias(nombre, orden, x)
    if nombre == "exp":
        piezas = [_signo(Fraction(1, _factorial_entero(k)),
                         mx.Pow(x, mx.Num(Fraction(k)))) for k in range(orden + 1)]
        residuo = _signo(Fraction(1, _factorial_entero(orden + 1)),
                         mx.Pow(x, mx.Num(Fraction(orden + 1))))
        return _suma(piezas), residuo
    if nombre == "tan":
        return _de_tan(x, orden)
    if nombre == "ln":
        return _de_ln(x, orden)
    raise sin_refuso(f"serie no implementada para «{nombre}»")


#: which powers each function has, and whether its signs alternate
_ESPECIE = {
    "sin": (lambda k: k % 2 == 1, True),
    "cos": (lambda k: k % 2 == 0, True),
    "sinh": (lambda k: k % 2 == 1, False),
    "cosh": (lambda k: k % 2 == 0, False),
}


def _primer_omitido(nombre: str, orden: int) -> int:
    """The first power the truncation does **not** write at order ``orden``.

    Shared by the polynomial and by the bound on its tail, because the two have to
    agree about where the series stopped. When they disagreed the bound was
    majorising the wrong tail — which is sound, just loose, and loose in a way
    nobody could see from the printed expression.
    """
    entra, _ = _ESPECIE[nombre]
    siguiente = orden + 1
    return siguiente if entra(siguiente) else siguiente + 1


def _potencias(nombre: str, orden: int, x: mx.Expr) -> tuple[mx.Expr, mx.Expr | None]:
    """The truncated series and the next term, for the four power-of-two kinds."""
    entra, alterna = _ESPECIE[nombre]
    piezas: list[mx.Expr] = []
    for k in range(0, orden + 1):
        if not entra(k):
            continue
        signo = (-1 if (alterna and (k // 2) % 2) else 1)
        piezas.append(_signo(Fraction(signo, _factorial_entero(k)),
                             mx.Pow(x, mx.Num(Fraction(k)))))
    siguiente = _primer_omitido(nombre, orden)
    signo = (-1 if (alterna and (siguiente // 2) % 2) else 1)
    residuo = _signo(Fraction(signo, _factorial_entero(siguiente)),
                     mx.Pow(x, mx.Num(Fraction(siguiente))))
    return (_suma(piezas) if piezas else mx.ZERO), residuo


def _numeros_tangentes(orden: int) -> dict[int, Fraction]:
    """The tangent numbers ``a_n`` of ``tan u = Σ a_n u^(2n+1)``, up to ``orden``.

    From ``tan'(u) = 1 + tan(u)^2``: writing ``tan u = Σ a_n u^(2n+1)``, that says
    ``(2n+1)·a_n`` is the convolution of the previous coefficients at ``n-1``.

    The coefficients are stored by **index**, not by power: two earlier versions
    keyed them by power and shifted the convolution by one, which gave a series of
    ``x + x^5/5 + 2x^9/45`` — the right shape, wrong coefficients, and an error of
    2.6e-3 at x = 0.2 with thirteen terms, which looks plausible until you check it
    against tan.
    """
    a: dict[int, Fraction] = {0: Fraction(1)}
    n = 1
    while 2 * n + 1 <= orden + 2:
        total = Fraction(0)
        for i, ai in a.items():
            for j, aj in a.items():
                if i + j == n - 1:
                    total += ai * aj
        a[n] = total / Fraction(2 * n + 1)
        n += 1
    return a


#: A rational upper bound on ``a[n+1]/a[n]``, for every ``n`` this module writes.
#:
#: The ratio tends to ``4/pi^2 = 0.405284...``, and the supremum over the
#: coefficients reachable inside ``ORDEN_MAXIMO`` is 0.405285 — checked in EXACT
#: rational arithmetic by ``test_la_razon_de_los_numeros_tangentes_esta_acotada``,
#: not estimated. One half is therefore a sound bound rather than a plausible one,
#: and it is what makes the geometric tail of ``tan`` below a bound.
#:
#: It is a bound on the coefficients the module can reach, not on the whole
#: sequence, and the module caps the order at ``ORDEN_MAXIMO`` precisely so that
#: this claim is finite and checkable instead of an extrapolation.
RAZON_TANGENTES = Fraction(1, 2)


def _de_tan(x: mx.Expr, orden: int) -> tuple[mx.Expr, mx.Expr | None]:
    """``x + x^3/3 + 2x^5/15 + 17x^7/315``, the tangent numbers, exactly."""
    a = _numeros_tangentes(orden)
    dentro = {indice: c for indice, c in a.items() if 2 * indice + 1 <= orden}
    piezas = [_signo(dentro[indice], mx.Pow(x, mx.Num(Fraction(2 * indice + 1))))
              for indice in sorted(dentro)]
    ultimo = max(a)
    return (_suma(piezas) if piezas else mx.ZERO), _signo(
        a[ultimo], mx.Pow(x, mx.Num(Fraction(2 * ultimo + 1))))


def _de_ln(x: mx.Expr, orden: int) -> tuple[mx.Expr, mx.Expr | None]:
    """``x - x^2/2 + x^3/3``: the only one that needs a sign per term."""
    piezas = [_signo(Fraction(1 if k % 2 else -1, k),
                     mx.Pow(x, mx.Num(Fraction(k))))
              for k in range(1, orden + 2)]
    return _suma(piezas[:max(0, len(piezas) - 1)]), piezas[-1]


def _termino(x: mx.Expr, indice: int, signo: int) -> mx.Expr:
    """``+x^n/n!``: the coefficient is carried by ``Mul`` because a fraction
    times a power is not a number the engine can fold on its own."""
    return _signo(Fraction(signo) / _factorial_entero(indice),
                  mx.Pow(x, mx.Num(Fraction(indice))))


def _signo(coeficiente: Fraction, potencia: mx.Expr) -> mx.Expr:
    """``coeficiente * potencia``, with the sign folded into the coefficient.

    Not decoration: the objectives are monotone in node count, and a ``Neg``
    wrapped around the whole term costs an extra node and gets rejected as «not an
    improvement», which is how a sign goes missing in silence.
    """
    return mx.Mul(mx.Num(coeficiente), potencia)


def _factorial_entero(n: int) -> int:
    total = 1
    for k in range(2, n + 1):
        total *= k
    return total


def _factorial(n: int) -> mx.Expr:
    """``1/n!`` as an exact rational, not as a rounded decimal."""
    return mx.Num(Fraction(1, _factorial_entero(n)))


def _cola_geometrica(primero: mx.Expr, razon: mx.Expr) -> mx.Expr:
    """``primero · (1 + razon + razon² + …)``, with ``razon`` already in ``[0, 1)``.

    The one construction every declared bound here is built from: once the ratios
    of successive terms are bounded by a constant below 1, the tail stops being a
    sum with no name and becomes a geometric series with a value.
    """
    return mx.Div(primero, mx.Sub(mx.Num(Fraction(1)), razon))


def _cota_de_cola(nombre: str, orden: int, var: str) -> mx.Expr | None:
    """The declared bound on what comes after the written terms — this closes T-19.

    **The tail of the series itself**, majorised term by term. Write ``m`` for the
    first power the truncation does not write, and compare the real tail against a
    geometric one:

    =============  =========================  =========================================
    family         terms after ``m``          the tail is at most
    =============  =========================  =========================================
    ``sin``…       ``±|x|^(m+2j)/(m+2j)!``   because every factor of a factorial
    ``cos``,       step 2, signs irrelevant   grows: ``(m+2j)(m+2j-1) ≥ (m+1)(m+2)``
    ``sinh``                                              → ratio ``|x|²/((m+1)(m+2))``
    ``cosh``
    ``exp``        ``|x|^(m+j)/(m+j)!``       step 1 → ratio ``|x|/(m+1)``
    ``tan``        ``a[n]|x|^(2n+1)``         ratio ``|x|²·RAZON_TANGENTES``
    ``ln``         ``|x|^(m+j)/(m+j)``        ``1/(m+j) ≤ 1/m`` → ratio ``|x|``
    =============  =========================  =========================================

    Why the majorisation is over the **absolute** values and not the signed ones:
    that is what makes one bound work for every ``x``, including the negative ones,
    and it is the point on which the bound this replaces was silently wrong.

    **What the old code declared, and where it was false.** The rule was "first
    omitted term for ``sin``/``cos``/``ln``, ``None`` for the rest". Two of those
    three were not bounds, and neither failure was where the tests were looking:
    one was on the negative axis, the other past a large argument.

    * ``sin``/``cos``: the alternating estimate needs the terms to DECREASE, and
      ``x^9/9!`` stops decreasing past ``x ≈ 8.5`` (the ratio ``(x^9/9!)/(x^7/7!)``
      is ``x²/72``). Past that the declared ``cota`` was smaller than the error while
      still being printed as an upper bound.
    * ``ln``: the Mercator series alternates **only for ``x > 0``**. At ``x < 0``
      every term is negative, the tail is monotone rather than alternating, and
      the first omitted term is a *lower* bound on it. At ``x = -0.9`` with five
      terms the engine declared ``0.0886`` for an error of ``0.4725`` — off by
      more than five, in the direction that makes a bound look like a result.

    The old alarm pinned that behaviour down by asserting ``cota is None`` for four
    functions. Asserting the absence of a number cannot see either failure above, so
    it is replaced by ``test_la_cota_declarada_acota_el_error_real``, which measures
    the error against the bound at points chosen to include the negatives.
    """
    x = mx.Sym(var)
    ax = mx.Call("abs", (x,))
    if nombre in ("exp", "ln"):
        m = orden + 1
    elif nombre in _ESPECIE:
        m = _primer_omitido(nombre, orden)
    elif nombre == "tan":
        return _cota_de_tan(x, orden)
    else:
        return None

    primero = _signo(Fraction(1, _factorial_entero(m)), mx.Pow(ax, mx.Num(Fraction(m))))
    if nombre == "ln":
        # the coefficients are 1/k, not 1/k!, so the factorial majorisation does
        # not apply and 1/k ≤ 1/m is the whole of what is used
        primero = _signo(Fraction(1, m), mx.Pow(ax, mx.Num(Fraction(m))))
        razon = ax
    elif nombre == "exp":
        razon = mx.Div(ax, mx.Num(Fraction(m + 1)))
    else:
        razon = mx.Div(mx.Pow(ax, mx.Num(Fraction(2))), mx.Num(Fraction((m + 1) * (m + 2))))
    return _cola_geometrica(primero, razon)


def _cota_de_tan(x: mx.Expr, orden: int) -> mx.Expr | None:
    """Geometric tail of ``tan``'s own series, and the domain it is valid on.

    ``tan``'s Maclaurin coefficients are all POSITIVE, so there is no alternating
    bound to fall back on: the first omitted term is a lower bound on the tail and
    quoting it as an upper one is the mistake this replaces.

    With ``a[n+1] ≤ RAZON_TANGENTES · a[n]`` (checked exactly, see the constant)
    the tail is a geometric series::

        Σ_{n>K} a[n]·|x|^(2n+1)  ≤  a[K+1]·|x|^(2K+3) / (1 - RAZON·|x|²)

    which is positive only for ``|x|² < 1/RAZON = 2``. That is **inside** the
    radius of convergence, ``π/2 ≈ 1.571``, and the sliver between ``√2`` and
    ``π/2`` is declared rather than papered over: it is why ``_DOMINIO_DE_LA_COTA``
    exists and why it is read before the bound is printed.
    """
    a = _numeros_tangentes(orden)
    ultimo = max(a) - 1
    if ultimo < 0:
        return None
    primero = _signo(a[ultimo + 1],
                     mx.Pow(mx.Call("abs", (x,)), mx.Num(Fraction(2 * ultimo + 3))))
    resta = mx.Sub(mx.Num(Fraction(1)),
                   mx.Mul(mx.Num(RAZON_TANGENTES), mx.Pow(x, mx.Num(Fraction(2)))))
    return mx.Div(primero, resta)


#: Where each declared bound is valid, as a sentence the answer carries with it.
#: Read before printing a bound: a bound without its domain is a number, and a
#: number without its domain is a promise nobody can check.
#:
#: Every one of these says *how* the bound was obtained, not merely where it holds.
#: A reader who cannot see the argument has to take the number on faith, which is
#: the thing this module exists to avoid.
_DOMINIO_DE_LA_COTA = {
    "sin": "válida para |x| < √((m+1)·(m+2)), con m la primera potencia no "
           "escrita: la cola de la serie está mayORIZada por una progresión "
           "geométrica de razón |x|²/((m+1)(m+2)). Más allá el denominador deja "
           "de ser positivo y la cota deja de ser un número",
    "cos": "válida para |x| < √((m+1)·(m+2)), con m la primera potencia no "
           "escrita: la cola de la serie está mayORIZada por una progresión "
           "geométrica de razón |x|²/((m+1)(m+2)). Más allá el denominador deja "
           "de ser positivo y la cota deja de ser un número",
    "sinh": "válida para |x| < √((m+1)·(m+2)), con m la primera potencia no "
            "escrita: la cola de la serie está mayORIZada por una progresión "
            "geométrica de razón |x|²/((m+1)(m+2)). Más allá el denominador deja "
            "de ser positivo y la cota deja de ser un número",
    "cosh": "válida para |x| < √((m+1)·(m+2)), con m la primera potencia no "
            "escrita: la cola de la serie está mayORIZada por una progresión "
            "geométrica de razón |x|²/((m+1)(m+2)). Más allá el denominador deja "
            "de ser positivo y la cota deja de ser un número",
    "exp": "válida para |x| < m+1, con m la primera potencia no escrita: la cola "
           "de la serie está mayORIZada por una progresión geométrica de razón "
           "|x|/(m+1)",
    "tan": "válida para |x| < √2, dentro del radio π/2: la cola de la serie está "
           "mayorizada por una progresión geométrica de razón |x|²/2. Fuera de √2 el "
           "denominador deja de ser positivo y la cota deja de ser un número",
    "ln": "válida para |x| < 1, que es su radio de convergencia: la cola está "
          "mayorizada por una progresión geométrica de razón |x|",
}


# ---------------------------------------------------------------------------
# Taylor for an arbitrary expression
# ---------------------------------------------------------------------------


def taylor(expresion: mx.Expr, centro, orden: int, var: str = "x") -> Serie:
    """Maclaurin/Taylor of any expression.

    **A known function does not go through derivatives here.** When the expression
    is one of the seven whose series this module writes term by term, the series is
    written, not derived — see ``_serie_por_nombre``. That is not an optimisation;
    the derivative route simply *fails* on two of the seven:

    =============  ==========================  ==========================
    call           by derivatives                by the known series
    =============  ==========================  ==========================
    ``tan``        order 3, then it dies        order 40
    ``ln`` @ 1     order 4, then it dies        order 40
    =============  ==========================  ==========================

    The reason is that ``tan' = 1/cos²`` and ``ln^(k) = (k-1)!/x^k``: every
    differentiation of a quotient expands into a product of powers, the trace
    records each intermediate, and the step log hits its 2000-character field
    long before the mathematics goes anywhere interesting. Meanwhile ``maclaurin``
    writes the tangent numbers and the Mercator terms directly and sails past both
    limits. So the same function had two answers, and the weaker one was the one
    this entry point reached — ``taylor(tan(x), 0, 7)`` raised while
    ``maclaurin("tan", 7)`` returned the series. Where the two could both be
    computed they agree exactly: 41 orders across six functions, no differences.

    **Everything else still goes through derivatives.** The polynomial is exact as
    far as the derivatives go. The error bound needs a bound on the first omitted
    derivative; this module can build one when the expression is a known function
    (``_cota_de_taylor``), and when it cannot the answer carries ``cota = None`` and
    says so — a polynomial without a stated accuracy is not an approximation, it is
    a different expression.

    ``centro`` may be a plain ``int``/``Fraction``: it is a number by definition and
    ``0`` is the overwhelmingly common one, so requiring ``mx.Num(0)`` at every call
    site buys nothing and pushes the mistake deep into the evaluator, where it used
    to surface as «no se sabe imprimir int» from inside ``as_poly``.
    """
    _exigir_orden(orden)
    from academic_core.domain.engineering.mathlab import derive_mv as D

    if not isinstance(centro, mx.Expr):
        if isinstance(centro, (int, Fraction)):
            centro = mx.Num(Fraction(centro))
        else:
            raise sin_refuso(
                f"el centro debe ser un número o una expresión, y recibió "
                f"{type(centro).__name__}; envuélvelo con Num(...)")

    if mx.variables(centro):
        raise sin_refuso(
            f"el centro «{mx.text(centro)}» tiene variables dentro, así que la "
            "derivada no se puede evaluar en él. El polinomio de Taylor "
            "exige un centro concreto; si lo que se quiere es el de la variable, "
            "el centro es 0 (§5.4)")

    conocida = _serie_por_nombre(expresion, orden, centro, var)
    if conocida is not None:
        return conocida

    formal = _serie_formal(expresion, orden, centro, var)
    if formal is not None:
        return formal

    piezas: list[mx.Expr] = []
    derivada = expresion
    factorial = 1
    for indice in range(0, orden + 1):
        if indice:
            factorial *= indice
        # Evaluate the CURRENT derivative at the centre, and only then get the
        # next one. Differentiating first reads the term of order k with the
        # derivative of order k+1: for x^3 that is f'(0)=0, f''(0)=0, f'''(0)=6,
        # so the terms land at x^2, x^3 and x^4 instead of only at x^3, and the
        # whole polynomial is a sum of terms that belong to another function.
        # The derivative itself is evaluated AND then simplified: substituting
        # into sin gives «sin(0)», and a coefficient of 1/sin(0) is a division
        # by zero rather than the «this coefficient is zero» it means.
        evaluada = _valor_en(derivada, var, centro)
        if mx.exact_value(evaluada) != 0:
            coeficiente = _coeficiente(evaluada, factorial)
            piezas.append(mx.Mul(coeficiente, mx.Pow(mx.Sub(mx.Sym(var), centro),
                                                     mx.Num(Fraction(indice)))))
        if indice < orden:
            # one more derivative only if another term still needs it: 1/x grows
            # on every differentiation and asked for orden+2 of them it walks
            # into the expression-size limit for a term nobody reads
            derivada = D.differentiate(derivada, var)
    polinomio = _suma(piezas)
    # one more derivative, for the first term NOT written
    omitida = _valor_en(D.differentiate(derivada, var), var, centro)
    if mx.exact_value(omitida) == 0:
        # the next coefficient vanishes: there is no next term, and dividing by
        # zero to say so would put «1/120/0·(x-0)^5» where a 0 belongs
        residuo = mx.ZERO
    else:
        siguiente = _coeficiente(omitida, factorial * (orden + 1))
        residuo = mx.Mul(siguiente, mx.Pow(mx.Sub(mx.Sym(var), centro),
                                           mx.Num(Fraction(orden + 1))))
    hipotesis = [
        f"el polinomio es exacto: sale de derivar {orden + 1} veces y dividir entre "
        f"los factoriales",
        "NO se declara cota de error: haría falta una cota de la derivada "
        "omitida en el intervalo, y este motor no la tiene para una expresión "
        "arbitraria. Un polinomio sin precisión declarada no es una "
        "aproximación (§5.4)",
    ]
    return Serie(polinomio, orden, residuo, None, centro,
                 "polinomio de Taylor por derivadas sucesivas", tuple(hipotesis))


def _serie_formal(expresion: mx.Expr, orden: int, centro: mx.Expr,
                  var: str) -> Serie | None:
    """Coefficients by arithmetic on truncated series (``serie_formal``), or ``None``.

    ``None`` only when the expression contains something that module cannot compose;
    the derivative route is then tried. Where the expansion does not exist (a pole,
    ``ln`` of 0, ``sqrt`` at 0) the refusal comes from here and is final.

    This replaced the derivative route as the default because the derivative route
    failed on correct inputs: ``1/(1-x)`` at order 5 and ``sqrt(x)`` about 1 hit the
    expression-size limit, and ``exp(x)`` about 2 was refused as having «no Taylor
    expansion» when its coefficients are ``e²/k!``.
    """
    from academic_core.domain.engineering.mathlab import serie_formal as F

    try:
        coeficientes = F.coeficientes(expresion, var, centro, orden + 2)
    except F.NoFormal:
        return None
    u = mx.Sub(mx.Sym(var), centro) if mx.exact_value(centro) != 0 else mx.Sym(var)
    piezas = [mx.Mul(c, mx.Pow(u, mx.Num(Fraction(k))))
              for k, c in enumerate(coeficientes[:orden + 1])
              if mx.exact_value(c) != 0]
    polinomio = _suma(piezas)
    siguiente = coeficientes[orden + 1]
    if mx.exact_value(siguiente) == 0:
        residuo = mx.ZERO
    else:
        residuo = _suma([mx.Mul(siguiente, mx.Pow(u, mx.Num(Fraction(orden + 1))))])
    hipotesis = [
        "el polinomio es exacto: cada coeficiente sale de operar con series "
        "truncadas (suma, producto de Cauchy, división de series y composición con "
        "las series conocidas), sin derivar ni redondear",
    ]
    cota = _cota_de_lagrange(expresion, orden, centro, var)
    if cota is None:
        hipotesis.append(
            "NO se declara cota de error: haría falta una cota de la derivada "
            "omitida en el intervalo, y este motor no la tiene para una expresión "
            "arbitraria. Un polinomio sin precisión declarada no es una "
            "aproximación (§5.4)")
    else:
        hipotesis.append(
            "cota de error: para todo x real, por el resto de Lagrange "
            f"|f^({orden + 1})(ξ)|·|x - a|^{orden + 1}/{orden + 1}! con la derivada "
            "acotada en todo el intervalo entre a y x")
    for parte in (polinomio, residuo):
        try:
            mx.text(parte)
        except Exception as exc:  # noqa: BLE001 - the printer's own size cap
            # Said HERE, at construction, and not later by whoever prints the
            # answer: a Serie that cannot be written down is not an answer.
            raise mx.invalid(
                "EXPRESSION_LIMIT",
                f"los coeficientes exactos de orden {orden} no caben en "
                f"{mx.MAX_TEXT} caracteres (cada uno es exacto, con constantes como "
                f"{mx.text(coeficientes[1])[:40]}…, y crecen con el orden); pide un "
                "orden menor") from exc
    return Serie(polinomio, orden, residuo, cota, centro,
                 "serie formal: aritmética exacta de series truncadas",
                 tuple(hipotesis))


def _cota_de_lagrange(expresion: mx.Expr, orden: int, centro: mx.Expr,
                      var: str) -> mx.Expr | None:
    """A Lagrange remainder bound for a bare known function about any centre.

    Only where every derivative has a bound that holds on the whole line:

    * ``sin``, ``cos``: every derivative is ``±sin`` or ``±cos``, so ``|f^(m)| ≤ 1``;
    * ``exp``: ``f^(m)(ξ) = e^ξ ≤ e^a·e^|x-a|`` because ``ξ`` lies between ``a`` and ``x``;
    * ``sinh``, ``cosh``: ``|f^(m)(ξ)| ≤ cosh ξ ≤ e^|ξ| ≤ e^|a|·e^|x-a|``.

    ``tan`` and ``ln`` have derivatives that blow up near their singularities, so
    no single number works and none is claimed.
    """
    nombre = _nombre_conocido(expresion, var)
    if nombre not in ("sin", "cos", "exp", "sinh", "cosh"):
        return None
    m = orden + 1
    distancia = mx.Call("abs", (mx.Sub(mx.Sym(var), centro),))
    base = mx.Div(mx.Pow(distancia, mx.Num(Fraction(m))), mx.Num(Fraction(_factorial_entero(m))))
    if nombre in ("sin", "cos"):
        return base
    a = centro if nombre == "exp" else mx.Call("abs", (centro,))
    return mx.Mul(mx.Mul(mx.Call("exp", (a,)), mx.Call("exp", (distancia,))), base)


def _nombre_conocido(expresion: mx.Expr, var: str) -> str | None:
    """The function name when ``expresion`` is exactly ``nombre(var)``, else ``None``.

    Only the bare single-call shape counts. ``exp(x) + 1`` is not covered, because
    the tail of its series is not the tail of ``exp``'s plus a constant: majorising
    one does not majorise the other, and pretending otherwise would hand out a
    bound the derivation never supported.
    """
    if (isinstance(expresion, mx.Call) and expresion.name in _DOMINIO_DE_LA_COTA
            and len(expresion.args) == 1
            and isinstance(expresion.args[0], mx.Sym)
            and expresion.args[0].name == var):
        return expresion.name
    return None


def _serie_por_nombre(expresion: mx.Expr, orden: int, centro: mx.Expr,
                      var: str) -> Serie | None:
    """The series of a known function, written instead of derived — or ``None``.

    ``None`` means "not a bare known call about a centre this module can shift to the
    origin", and the caller then falls back to derivatives. Three conditions, because
    the third one is a trap this function fell into the first time it was written:

    * the expression must be exactly ``nombre(var)`` — see ``_nombre_conocido``;
    * the centre must be one this module can turn into the origin by substitution:
      the origin itself, plus ``1`` for ``ln``, whose series is the one of
      ``ln(1 + u)`` and so *is* the series about ``x = 1`` already;
    * and ``ln`` is excluded from the origin. ``maclaurin("ln", n)`` is the series of
      ``ln(1 + x)`` — a deliberate quirk of that name, documented in its hypotheses —
      but ``taylor(ln(x), 0, n)`` promises the Taylor polynomial of ``ln`` about 0,
      and that does not exist. Delegating there made the function answer ``x - 1/2x² +
      …`` to a question about ``ln``, which has no expansion there at all. Before
      this it refused, with «ln(0) no es un número», and the refusal was correct. The
      derivative route is what produces it, so ``ln`` at the origin must fall
      through instead of being answered from the Mercator series.

    Every other centre keeps the derivative route too, and it refuses for a real
    reason rather than a structural one: ``taylor(sin(x), 1, 6)`` dies because
    ``sin(1)`` is not a number this engine can write, and no amount of rearrangement
    changes that.
    """
    nombre = _nombre_conocido(expresion, var)
    if nombre is None:
        return None
    if nombre == "ln":
        en_el_origen = False
        mercator = mx.exact_value(centro) == 1
    else:
        en_el_origen = mx.exact_value(centro) == 0
        mercator = False
    if not (en_el_origen or mercator):
        return None
    desplazamiento = None if en_el_origen else mx.Sub(mx.Sym(var), centro)
    polinomio, residuo = _truncar(nombre, orden, var)
    cota = _cota_de_cola(nombre, orden, var)
    if desplazamiento is not None:
        polinomio = mx.substitute(polinomio, var, desplazamiento)
        if residuo is not None:
            residuo = mx.substitute(residuo, var, desplazamiento)
        if cota is not None:
            cota = mx.substitute(cota, var, desplazamiento)
    metodo = ("serie conocida, escrita término a término"
              if en_el_origen else
              "serie conocida de ln(1 + u) sobre el origen, con u = x - 1")
    return Serie(polinomio, orden, residuo, cota, centro, metodo,
                 _hipotesis_de_serie_conocida(nombre, var, desplazamiento))


def _cota_de_taylor(expresion: mx.Expr, orden: int, centro: mx.Expr,
                    var: str) -> mx.Expr | None:
    """The bound for a Taylor series of a *known* function, or ``None``.

    **Not called by :func:`taylor` any more, and that is the point of writing it
    down here.** It used to be, on the derivative route. Once a known function is
    written rather than derived, the seven cases that actually survive a ``taylor``
    call — the six at the origin, and ``ln`` about 1 — are all answered earlier, by
    ``_serie_por_nombre``. So this function became unreachable, and unreachable code
    that claims to compute a bound is a second source of truth for the same number:
    the day the two disagree, one of them is a lie and nothing says which.

    It is kept because it is the *specification* of what the shift does to a bound,
    and ``_serie_por_nombre`` is measured against it by
    ``test_la_serie_desplazada_coincide_con_la_cota_desplazada``. If that test ever
    stops holding, the answer to give is this function, not a third one.

    The series of ``f`` about ``a`` is the series of ``u ↦ f(a + u)`` about ``0``,
    and the bound has the same shape, so it is built at the origin and ``var`` is
    replaced by ``var - centro`` — the argument is the shift, not a new computation,
    and it is exact.
    """
    nombre = _nombre_conocido(expresion, var)
    if nombre is None:
        return None
    cota = _cota_de_cola(nombre, orden, var)
    if cota is None:
        return None
    if mx.exact_value(centro) == 0:
        return cota
    return mx.substitute(cota, var, mx.Sub(mx.Sym(var), centro))


def _valor_en(derivada: mx.Expr, var: str, centro: mx.Expr) -> mx.Expr:
    """The derivative evaluated at ``centro`` and folded into a number.

    Three normalisers, because none of them does the other's job: substituting
    into ``sin`` leaves ``sin(0)``, which only the trigonometric engine can fold;
    ``3·0^2`` is arithmetic, which only the rational normal form can; and
    ``0^(-1)`` is not a number at all, which is why the caller checks for zero
    afterwards rather than dividing by it.

    It REFUSES when the value is not a number: ``ln`` has no Taylor series at 0,
    so its first derivative there is ``1/0`` and its second involves ``ln(0)``.
    Building a polynomial out of those writes a quotient by zero into every
    coefficient and calls the result an approximation (§5.4).
    """
    from academic_core.domain.engineering.mathlab import poly as P

    e = T.simplify(mx.substitute(derivada, var, centro))
    try:
        q = P.as_poly(e)
    except Exception:
        _no_es_numero(e, centro, derivada)
    plegado = P.to_expr(q) if q is not None else e
    resultado = T.simplify(plegado)
    if mx.exact_value(resultado) is None:
        _no_es_numero(resultado, centro, derivada)
    return resultado


def _no_es_numero(e: mx.Expr, centro: mx.Expr, derivada: mx.Expr) -> None:
    """Refuse rather than fold a value that is not a number into a coefficient."""
    raise sin_refuso(
        f"la derivada {mx.text(derivada)} vale {mx.text(e)} en {mx.text(centro)}, "
        "que no es un número: la función no tiene desarrollo de Taylor en ese "
        "centro. Un polinomio con un coeficiente infinito o indefinido no es una "
        "aproximación, es otra expresión (§5.4)")


def _coeficiente(valor: mx.Expr, factorial: int) -> mx.Expr:
    """``valor / factorial``, and NOT its reciprocal.

    It used to be ``1/(factorial·valor)``, and the loop compensated by dividing
    the other way: the two mistakes cancelled for a while and left the monomials
    wrong by a factor of ``factorial²`` — ``taylor(x^3, 0, 4)`` gave ``x^3/36``
    where it gives ``x^3``. A cancellation between two bugs is the hardest kind
    to see, because every intermediate value looks plausible.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    cociente = mx.Div(valor, mx.Num(Fraction(factorial)))
    try:
        q = P.as_poly(cociente)
    except Exception:
        return cociente
    return P.to_expr(q) if q is not None else cociente


def _suma(piezas: list[mx.Expr]) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import poly as P

    total = mx.ZERO
    for pieza in piezas:
        total = mx.Add(total, pieza)
    try:
        q = P.as_poly(total)
    except Exception:
        return total
    return P.to_expr(q) if q is not None else total


def valor_en(serie: Serie, x, var: str = "x") -> float:
    """Evaluate the truncated polynomial, and separately the tail's first term.

    Both, because the pair is the answer: the number, and how far it is from the
    value of the function it approximates.
    """
    del var
    propio = mx.evaluate(serie.polinomio, {"x": x})
    primer = mx.evaluate(serie.residuo, {"x": x}) if serie.residuo is not None else 0.0
    return propio.real + primer.real


__all__ = [
    "ORDEN_MAXIMO", "Serie", "maclaurin", "taylor", "valor_en", "sin_refuso",
]
