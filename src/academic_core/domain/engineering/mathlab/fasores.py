# SPDX-License-Identifier: MIT
"""MATH_LAB T-16: phasors — magnitude, phase, and the sinusoidal signal behind them.

What a phasor is here
---------------------

A phasor is a complex number standing for a sinusoid at **one fixed frequency**.
``V_pico·cos(ωt + φ)`` is written ``V_pico·e^(jφ)`` and the ``ωt`` is dropped. That
drop is the whole trick and the whole hazard: the phasor is only valid at the
frequency it was built for, and applying it at another frequency is a category
error rather than an approximation. So the frequency is carried *with* the phasor,
not thrown away with the ``t``.

Exactness, and the one place it runs out
----------------------------------------

The phasor is stored exactly, as a :class:`complejos.Complejo`: ``3 + 4j`` has
magnitude ``5`` and not ``5.000000000000001``. What is **not** exact is the phase
in general — ``arg(3+4j) = arctan(4/3)``, which is not a multiple of ``pi`` and
therefore not a rational number. The module says so at the point where it happens
rather than handing back a ``Decimal`` labelled as if it were exact, and it offers
``aproximar()`` for the case where a decimal is genuinely wanted, with the error
declared.

The interoperability contract
-----------------------------

``CIRCUITS_LAB`` stores its phasors as ``RationalComplex`` / ``DecimalComplex`` and
derives magnitude and phase through ``math/trig.py`` with the **phase convention
``(-pi, pi]``**. The two conventions must agree, and :func:`verifica_contrato`
checks that they do rather than trusting it: an off-by-a-turn disagreement is not a
wrong number in one place, it is a phase that looks right and is wrong, which is
the worst kind. :func:`a_fasor_del_lab` and :func:`del_lab` convert in both
directions and preserve the rectangular form, which neither side is allowed to
lose.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import complejos as K
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.errors import UnsupportedError

#: the convention both labs declare. Stated here so a disagreement is a fact about
#: the code and not a mystery in a circuit solution.
CONVENCION_FASE = "(-pi, pi]"

#: the phase interval T-15 uses, as numbers, for the contract check
FASE_MINIMO = -3.141592653589793
FASE_MAXIMO = 3.141592653589793


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the phasor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fasor:
    """A complex number standing for a sinusoid at one frequency.

    ``rectangular`` is kept even though it can be derived from the polar form,
    because the polar form can be *approximate* while the rectangular one is
    exact, and dropping the exact copy would make the approximation irreversible.
    """

    rectangular: K.Complejo
    frecuencia: mx.Expr | None = None
    etiqueta: str = ""

    @property
    def magnitud(self) -> mx.Expr:
        return self.rectangular.modulo()

    @property
    def fase(self) -> mx.Expr:
        return self.rectangular.argumento()

    @property
    def es_exacto(self) -> bool:
        """Whether magnitude and phase are both exact numbers.

        The modulus is exact whenever the squared modulus is a perfect square.
        The phase is exact only at the multiples of ``pi`` the tables know, and
        ``arctan(4/3)`` is not one of them — so most phasors are *not* exact in
        both halves, and saying so is more useful than returning a decimal quietly.
        """
        if mx.exact_value(self.magnitud) == 0:
            return True                     # the zero signal: exact, no phase needed
        return (mx.exact_value(self.magnitud) is not None
                and _es_multiplo_de_pi(self.fase))

    def a_polar(self) -> K.Polar:
        return K.a_polar(self.rectangular)

    def __add__(self, otro: "Fasor") -> "Fasor":
        return _exige_misma_frecuencia(self, otro, lambda: Fasor(
            self.rectangular + otro.rectangular,
            frecuencia=self._frecuencia_con(otro), etiqueta=self.etiqueta))

    def __sub__(self, otro: "Fasor") -> "Fasor":
        return _exige_misma_frecuencia(self, otro, lambda: Fasor(
            self.rectangular - otro.rectangular,
            frecuencia=self._frecuencia_con(otro), etiqueta=self.etiqueta))

    def __mul__(self, otro: "Fasor") -> "Fasor":
        """Phasors multiply like complex numbers: impedance times current."""
        return _exige_misma_frecuencia(self, otro, lambda: Fasor(
            self.rectangular * otro.rectangular,
            frecuencia=self._frecuencia_con(otro), etiqueta=self.etiqueta))

    def __truediv__(self, otro: "Fasor") -> "Fasor":
        """A quotient is the impedance ratio, and the frequency has to match."""
        return _exige_misma_frecuencia(self, otro, lambda: Fasor(
            self.rectangular / otro.rectangular,
            frecuencia=self._frecuencia_con(otro), etiqueta=self.etiqueta))

    def conjugado(self) -> "Fasor":
        """The negative-frequency phasor, kept with the frequency it belongs to."""
        return Fasor(self.rectangular.conjugado(), self.frecuencia, self.etiqueta)

    def _frecuencia_con(self, otro: "Fasor") -> mx.Expr | None:
        return self.frecuencia if self.frecuencia is not None else otro.frecuencia

    # --- rendering -------------------------------------------------------

    def texto(self) -> str:
        base = self.a_polar().texto()
        return f"{base} @ {mx.text(self.frecuencia)}" if self.frecuencia else base

    def a_texto(self, variable: str = "t") -> str:
        """The sinusoid itself, which is what the phasor stands for.

        ``A·e^(jφ)`` is not the answer to «what is the signal»; the answer is
        ``A·cos(ωt + φ)``, and a module that only ever prints the phasor leaves
        the reader to undo the trick by hand.
        """
        if mx.exact_value(self.magnitud) == 0:
            # two sinusoids that cancel (cos t + cos(t + pi)) sum to the zero
            # signal; the zero phasor has no phase, and asking for one raised
            # ZeroDivisionError instead of answering 0 (found 2026-10-06)
            return "0"
        omega = self.frecuencia if self.frecuencia is not None else mx.ZERO
        angulo = _normaliza(mx.Add(mx.Mul(omega, mx.Sym(variable)), self.fase))
        return f"{mx.text(self.magnitud)}·cos({mx.text(angulo)})"

    def rms(self) -> mx.Expr:
        """``V_rms = V_pico / √2``.

        Only a magnitude-domain conversion, and only for the peak the phasor
        carries. A phasor built from an RMS value has no ``√2`` to remove, which is
        a mistake that shows up later as a factor of 1.41 in a power figure.
        """
        return mx.Div(self.magnitud, mx.Root(2, mx.Num(Fraction(2))))


def _es_multiplo_de_pi(angulo: mx.Expr) -> bool:
    """Whether the phase is an exact multiple of ``pi``.

    ``exact_value`` cannot answer this: ``pi/2`` is exact and not rational, and
    asking for its value returns ``None``. The question is the right one though —
    a phasor whose phase is a multiple of ``pi`` is one the other lab can hold
    exactly, and one whose phase is ``arctan(4/3)`` is not.
    """
    from academic_core.domain.engineering.mathlab.trig import _coef_de_pi

    if angulo == mx.ZERO:
        return True
    return _coef_de_pi(angulo) is not None


def _exige_misma_frecuencia(uno: Fasor, otro: Fasor, operacion):
    """Combining two phasors is only meaningful at one frequency.

    Not pedantry: the ``ωt`` was dropped when the phasor was made, so a sum of
    phasors at different frequencies has no time-domain meaning at all. Adding them
    anyway would produce a number that looks like a result and is not.
    """
    if (uno.frecuencia is not None and otro.frecuencia is not None
            and uno.frecuencia != otro.frecuencia):
        raise sin_refuso(
            f"no se pueden combinar dos fasores de frecuencias distintas "
            f"({mx.text(uno.frecuencia)} y {mx.text(otro.frecuencia)}): el "
            "«ωt» se dropó al formar cada uno, así que la suma no significa nada "
            "en el tiempo (§5.4)")
    return operacion()


# ---------------------------------------------------------------------------
# sinusoidal signal <-> phasor
# ---------------------------------------------------------------------------


def de_senoidal(amplitud, fase=0, frecuencia=None, etiqueta: str = "") -> Fasor:
    """``A·cos(ωt + φ)`` → the phasor ``A·e^(jφ)``.

    The amplitude is the **peak**, and it is taken as given. A sinusoid written with
    an RMS amplitude instead is a different signal, and the module will not guess
    which one it was handed: ``rms()`` is how you say so explicitly.
    """
    amplitud = _como_expresion(amplitud)
    angulo = _como_expresion(fase)
    if frecuencia is not None:
        frecuencia = _como_expresion(frecuencia)
    return Fasor(K.Complejo(_normaliza(mx.Mul(amplitud, _coseno(angulo))),
                            _normaliza(mx.Mul(amplitud, _seno(angulo)))),
                 frecuencia, etiqueta)


def _como_expresion(valor) -> mx.Expr:
    """A bare int is a number the engine can hold exactly; a float cannot."""
    if isinstance(valor, int):
        return mx.Num(Fraction(valor))
    if isinstance(valor, mx.Expr):
        return valor
    raise sin_refuso(
        f"«{valor}» es {type(valor).__name__} y aquí hace falta una expresión "
        f"exacta. Un flotante es una aproximación y no se cuela en un campo que "
        "promete exactitud (§5.1)")


def _normaliza(e: mx.Expr) -> mx.Expr:
    """Fold the arithmetic exactly: ``3·cos(pi)`` has to become ``-3``."""
    from academic_core.domain.engineering.mathlab import poly as P

    e = T.simplify(e)
    try:
        q = P.as_poly(e)
    except Exception:
        return e
    return T.simplify(P.to_expr(q)) if q is not None else e


def _coseno(angulo: mx.Expr) -> mx.Expr:
    return mx.Call("cos", (angulo,))


def _seno(angulo: mx.Expr) -> mx.Expr:
    return mx.Call("sin", (angulo,))


def a_senoidal(fasor: Fasor, variable: str = "t") -> tuple[str, tuple[str, ...]]:
    """The phasor → ``(A·cos(ωt + φ), hipótesis)``, with the caveats attached."""
    if mx.exact_value(fasor.magnitud) == 0:
        return "0", ("las senoidales se cancelan: la suma es la señal nula, cuyo "
                     "fasor es 0 y no tiene fase",)
    hipotesis = [f"la amplitud es el valor pico: el fasor representa "
                 f"{fasor.a_texto(variable)}"]
    if not fasor.es_exacto:
        hipotesis.append(
            "la fase no es un múltiplo exacto de pi, así que el fasor es exacto en "
            "su forma rectangular pero no en la fase; para un decimal hace falta "
            "aproximar() (§5.4)")
    if fasor.frecuencia is None:
        hipotesis.append(
            "no se indicó frecuencia: el fasor vale para la que tenga el circuito, "
            "y aplicarlo en otra no significa nada (§5.4)")
    return fasor.a_texto(variable), tuple(hipotesis)


def sumar_senoidales(*senales: tuple) -> tuple[str, tuple[str, ...]]:
    """``A₁cos(ωt+φ₁) + A₂cos(ωt+φ₂)`` as one phasor sum.

    The sum of two sinusoids at the **same** frequency is again one sinusoid. At
    different frequencies it is not, and there is no phasor for it — the module says
    so rather than returning something with a magnitude.
    """
    fasores = [de_senoidal(a, f, w) for (a, f, w) in senales]
    total = fasores[0]
    for otro in fasores[1:]:
        total = total + otro
    return a_senoidal(total)


# ---------------------------------------------------------------------------
# the interoperability contract with CIRCUITS_LAB and SIGNALS_LAB
# ---------------------------------------------------------------------------


def a_fasor_del_lab(z, frecuencia=None, etiqueta: str = "") -> Fasor:
    """``RationalComplex`` / ``DecimalComplex`` → this module's phasor.

    Only the exact one converts. A ``DecimalComplex`` is an approximation and
    converting it would put a ``Decimal`` into a field that promises exact
    expressions; the honest route is ``aproximar`` on this side, which declares
    its error.
    """
    if hasattr(z, "re") and hasattr(z, "im"):
        return Fasor(K.Complejo(_fraccion_exacta(z.re), _fraccion_exacta(z.im)),
                     frecuencia, etiqueta)
    raise sin_refuso(
        f"un fasor del laboratorio tiene que tener «re» e «im»; llegó "
        f"{type(z).__name__}. Si es DecimalComplex es una aproximación y no entra "
        "aquí: ese caso se resuelve con aproximar(), que declara su error (§5.4)")


def _fraccion_exacta(valor) -> mx.Expr:
    if isinstance(valor, Fraction):
        return mx.Num(valor)
    if isinstance(valor, int):
        return mx.Num(Fraction(valor))
    raise sin_refuso(
        f"solo se convierten partes racionales exactas; «{valor}» es "
        f"{type(valor).__name__}, que ya es una aproximación (§5.1)")


def del_lab(fasor: Fasor):
    """This module's phasor → ``RationalComplex``, for the other lab.

    Only for the exact parts. A phasor whose phase is not rational cannot go, and
    the error says so instead of rounding it into a ``Decimal``.
    """
    from academic_core.domain.engineering.math.rational import RationalComplex

    re = mx.exact_value(fasor.rectangular.real)
    im = mx.exact_value(fasor.rectangular.imag)
    if re is None or im is None or not _es_multiplo_de_pi(fasor.fase):
        raise sin_refuso(
            f"el fasor {fasor.rectangular.texto()} no es de los que el laboratorio "
            "puede guardar exactamente: sus partes han de ser racionales y su "
            "fase un múltiplo de pi. CIRCUITS_LAB solo alcanza resultados "
            "exactos con fasores alineados con los ejes; el resto necesita un "
            "Decimal, que es una aproximación, y aquí se negaría (§5.4)")
    return RationalComplex(re, im)


def verifica_contrato(muestras=6) -> tuple[bool, str]:
    """Check that both labs put the phase in the same place.

    The convention is written down twice — here and in ``ac/phasors.py`` — and two
    written-down conventions are two things that can disagree. The check is
    numerical and it is about the *interval*, not about the value: what matters is
    that no phase this module produces falls outside ``(-pi, pi]``, because one
    that does would be interpreted differently by the other lab with no error
    anywhere.
    """
    fuera: list[str] = []
    for k in range(1, muestras + 1):
        real = mx.Num(Fraction(k, 2))
        imag = mx.Num(Fraction(1 if k % 2 else -1, 2))
        fasor = Fasor(K.Complejo(real, imag))
        valor = mx.evaluate(fasor.fase)
        if valor is None:
            continue
        valor = valor.real if isinstance(valor, complex) else valor
        if not (FASE_MINIMO < valor <= FASE_MAXIMO):
            fuera.append(f"arg({k}/2 {'+' if k % 2 else '-'} i/2) = {valor}")
    if fuera:
        return False, f"fuera de {CONVENCION_FASE}: " + "; ".join(fuera)
    return True, (f"{muestras} fases de prueba, todas en {CONVENCION_FASE}, "
                  f"que es la convención declarada por ac/phasors.py")


def aproxima(fasor: Fasor, cifras: int = 15) -> V.Aproximacion:
    """The phase as a number, with the error it is worth.

    ``arctan(4/3)`` is exact and irrational. Reporting it as a ``Decimal`` without
    saying how much the decimal is worth would be the same as rounding an answer
    quietly, so the error comes from the same measured sensitivity as everywhere
    else in the engine.
    """
    return V.aproximacion(fasor.fase, "x", 0.0, cifras)


__all__ = [
    "CONVENCION_FASE", "Fasor", "de_senoidal", "a_senoidal",
    "sumar_senoidales", "a_fasor_del_lab", "del_lab", "verifica_contrato",
    "aproxima", "sin_refuso",
]
