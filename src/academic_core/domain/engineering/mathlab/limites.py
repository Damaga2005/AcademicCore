"""Growth at infinity, exactly, for asymptotes that are lines.

An asymptote is a *limit*, and a sample is not a limit. ``3·sen(2x)/x`` sampled at
ten different large values gives ten different numbers, and declaring ``y = 0``
because one of them was small would be inventing a line out of a coincidence. So
this module never samples: it computes the **order of growth** of the expression as
a number, by arithmetic, and the asymptote falls out of it.

The order is a small piece of algebra rather than an approximation:

===============  ==============================================================
``grado``        exponent of ``x``. ``-1`` for ``1/x``, ``0`` for ``sen(x)`` and
                 for every constant, ``1`` for ``x``, and ``None`` for anything
                 this module refuses to classify.
``coeficiente``  the leading coefficient, exact, as a ``Fraction``.
``oscila``       whether a bounded function of ``x`` is in there with the same
                 order as the whole. ``sen(x)/x`` tends to 0 and ``sen(x)`` does
                 not, and the difference is exactly this flag.
===============  ==============================================================

From the order come the asymptotes:

- ``grado < 0`` → ``y = 0``, at both ends. The expression vanishes, oscillation and
  all: ``|sen(x)|/x`` is bounded by ``1/x``.
- ``grado == 0`` and not oscillating → ``y = coeficiente``.
- ``grado == 1`` and not oscillating → the oblique ``y = m·x + b``, with ``m`` the
  leading coefficient and ``b`` the constant term, read off the terms one by one.
- anything else → no line asymptote, which is a real answer: ``x^2`` grows faster
  than any line, and ``x·sen(x)`` never settles down to one.

What it refuses: ``exp``, ``log``, ``tg``, ``sec``, ``cosec``, ``cot``, roots and
anything it cannot classify. Not because those have no asymptotes — some do — but
because guessing at them here would be the same invention under a longer name.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx

__all__ = ["Orden", "orden_en_infinito", "asintotas_de_horizonte_y_oblicua"]


#: Functions that stay bounded as ``x`` runs to infinity and have no limit. The
#: whole difference between ``sen(x)/x → 0`` and ``sen(x)`` oscillating is here.
ACOTADAS_SIN_LIMITE = ("sin", "cos", "asin", "acos", "atan", "sinh", "cosh")


@dataclass(frozen=True)
class Orden:
    """Growth at infinity: exponent, leading coefficient, and whether it wavers."""

    grado: int | None
    coeficiente: Fraction = Fraction(0)
    oscila: bool = False
    conocido: bool = True

    @property
    def es_nulo(self) -> bool:
        """Whether the expression vanishes, oscillation included."""
        return self.conocido and self.grado is not None and self.grado < 0


def _desconocido() -> Orden:
    return Orden(None, Fraction(0), False, conocido=False)


def orden_en_infinito(expresion: mx.Expr, var: str) -> Orden:
    """The growth of ``expresion`` as ``var`` runs to infinity, exactly."""
    orden = _ordena(expresion, var)
    # Anything that vanishes tends to 0 whatever it was doing: |sen(x)|/x is bounded
    # by 1/x, so the oscillation dies with the growth that fed it. This is the one
    # place where the flag is dropped, and it is dropped because the DECAY is what
    # kills it, not because the oscillation was never there.
    if orden.es_nulo:
        return Orden(orden.grado, orden.coeficiente, False, True)
    return orden


def _ordena(e: mx.Expr, var: str) -> Orden:
    if isinstance(e, mx.Num):
        return Orden(0, Fraction(e.value))
    if isinstance(e, mx.Sym):
        return Orden(1, Fraction(1)) if e.name == var else _desconocido()
    if isinstance(e, mx.Neg):
        dentro = _ordena(e.arg, var)
        return Orden(dentro.grado, -dentro.coeficiente, dentro.oscila,
                     dentro.conocido)
    if isinstance(e, mx.Call):
        return _ordena_llamada(e, var)
    if isinstance(e, mx.Pow):
        return _ordena_potencia(e, var)
    if isinstance(e, (mx.Add, mx.Sub)):
        return _ordena_suma(e, var)
    if isinstance(e, mx.Mul):
        return _ordena_producto(e, var)
    if isinstance(e, mx.Div):
        return _ordena_cociente(e, var)
    return _desconocido()


def _ordena_llamada(e: mx.Call, var: str) -> Orden:
    """A call is only ordered when it is one this module knows to be bounded."""
    if e.name in ACOTADAS_SIN_LIMITE and len(e.args) == 1:
        return Orden(0, Fraction(1), oscila=True)
    return _desconocido()


def _ordena_potencia(e: mx.Pow, var: str) -> Orden:
    if not isinstance(e.exponent, mx.Num) or e.exponent.value.denominator != 1:
        return _desconocido()
    base = _ordena(e.base, var)
    if not base.conocido or base.grado is None:
        return _desconocido()
    exponente = int(e.exponent.value)
    if exponente == 0:
        return Orden(0, Fraction(1))
    return Orden(exponente * base.grado, base.coeficiente ** exponente, base.oscila)


def _ordena_suma(e, var: str) -> Orden:
    """The dominant term decides; a term of lower order cannot change it."""
    izquierda, derecha = _ordena(e.left, var), _ordena(e.right, var)
    if not (izquierda.conocido and derecha.conocido):
        return _desconocido()
    if izquierda.grado is None or derecha.grado is None:
        return _desconocido()
    if izquierda.grado == derecha.grado:
        # same order: the coefficients add, and that is the only way a sum of a
        # vanishing and a growing term can stay at the middle
        coeficiente = izquierda.coeficiente + (
            -derecha.coeficiente if isinstance(e, mx.Sub) else derecha.coeficiente)
        return Orden(izquierda.grado, coeficiente,
                     izquierda.oscila or derecha.oscila)
    dominante = izquierda if izquierda.grado > derecha.grado else derecha
    signo = -1 if (dominante is derecha and isinstance(e, mx.Sub)) else 1
    return Orden(dominante.grado, signo * dominante.coeficiente,
                 izquierda.oscila or derecha.oscila)


def _ordena_producto(e, var: str) -> Orden:
    """The leading coefficient of a product is the product of the leading ones."""
    ordenes = [_ordena(f, var) for f in _factores(e)]
    if any(not o.conocido or o.grado is None for o in ordenes):
        return _desconocido()
    grado = sum(o.grado for o in ordenes)
    coeficiente = Fraction(1)
    for o in ordenes:
        coeficiente *= o.coeficiente
    return Orden(grado, coeficiente, any(o.oscila for o in ordenes))


def _ordena_cociente(e, var: str) -> Orden:
    arriba, abajo = _ordena(e.left, var), _ordena(e.right, var)
    if not (arriba.conocido and abajo.conocido):
        return _desconocido()
    if arriba.grado is None or abajo.grado is None:
        return _desconocido()
    coeficiente = arriba.coeficiente / abajo.coeficiente
    if arriba.grado < abajo.grado:
        # A quotient tends to zero when the numerator grows more slowly, whatever
        # it does on its own: that is why `sen(x)/x` has an asymptote and
        # `x/sen(x)` does not, and it is decided by the ORDERS.
        return Orden(arriba.grado - abajo.grado, coeficiente)
    return Orden(arriba.grado - abajo.grado, coeficiente,
                 oscila=arriba.oscila or abajo.oscila)


def _factores(e: mx.Expr) -> list[mx.Expr]:
    """``Mul`` takes only two children, so a product is a nest of two-child nodes."""
    if isinstance(e, mx.Mul):
        return _factores(e.left) + _factores(e.right)
    return [e]


def _terminos(e: mx.Expr, signo: int = 1) -> list[tuple[int, mx.Expr]]:
    """A sum, flattened into signed terms. One term when it is not a sum."""
    if isinstance(e, mx.Add):
        return _terminos(e.left, signo) + _terminos(e.right, signo)
    if isinstance(e, mx.Sub):
        return _terminos(e.left, signo) + _terminos(e.right, -signo)
    if isinstance(e, mx.Neg):
        return _terminos(e.arg, -signo)
    return [(signo, e)]


def _recta(pendiente: Fraction, ordenada: Fraction, var: str) -> str:
    """``y = 2·x + 3``, with the terms that are zero left out."""
    partes: list[str] = []
    if pendiente == 1:
        partes.append(var)
    elif pendiente == -1:
        partes.append(f"-{var}")
    elif pendiente != 0:
        partes.append(f"{pendiente}·{var}")
    if ordenada != 0:
        partes.append(f"{'+' if ordenada > 0 else '-'} {abs(ordenada)}")
    return "y = " + " ".join(partes)


def asintotas_de_horizonte_y_oblicua(expresion: mx.Expr, var: str) -> tuple[str, ...]:
    """The horizontal and oblique asymptotes, or an empty tuple.

    An empty tuple means «none, and that is a real answer» — not «not known». The
    two are told apart by :func:`orden_en_infinito`: a known order decides, and an
    unknown one declines.

    A slant asymptote is settled term by term, because asking the whole expression
    «what is your order» cannot answer «and what is your constant term»: the two
    leading terms cancel, and a cancellation that removes the whole growth has to be
    seen for it to be noticed. ``x`` minus ``x`` is not ``0`` to something that only
    knows the order of growth, and it is exactly ``0`` here.
    """
    orden = orden_en_infinito(expresion, var)
    if not orden.conocido or orden.grado is None:
        return ()
    if orden.grado < 0:
        return ("y = 0",)
    if orden.grado == 0:
        return () if orden.oscila else (f"y = {orden.coeficiente}",)
    if orden.grado > 1:
        return ()                     # faster than any line: x^2 has none

    pendiente = ordenada = Fraction(0)
    for signo, termino in _terminos(expresion):
        o = orden_en_infinito(termino, var)
        if not o.conocido or o.grado is None:
            return ()
        if o.oscila:
            # A wave as big as the line itself never reaches it. `x/sen(x)` and
            # `x·sen(x)` both grow like `x` and both have NO asymptote, and the
            # order on its own cannot say so — it takes the oscillation flag, and
            # asking only about the term of order 1 gave `y = x` for both.
            return ()
        if o.grado == 1:
            pendiente += signo * o.coeficiente
        elif o.grado == 0:
            # `x + sen(x)` grows like a line and never reaches one, which is not a
            # thing the ORDER can say and is the reason this loop exists
            if o.oscila:
                return ()
            ordenada += signo * o.coeficiente
        elif o.grado > 1:
            return ()
        # a term that vanishes lies below every line, oscillatory or not
    return (_recta(pendiente, ordenada, var),)
