# SPDX-License-Identifier: MIT
"""MATH_LAB T-13: trigonometric inequalities, sign charts and periodic solution sets.

How an inequality is solved here
--------------------------------

An inequality ``f(x) > 0`` becomes a **sign chart**, and a sign chart is only as
good as its critical points. Those come from two places and both have to be
there:

1. the **zeros** of ``f``, where the sign can change;
2. the **singularities**, where ``f`` does not exist — and those are the zeros of
   its denominators.

Leaving out the second is the classic mistake: ``1/tan(x) > 0`` looks sign-constant
between the multiples of ``pi`` if the poles are ignored, and the answer comes out
plainly wrong.

From those points the sign on each gap is decided **numerically**, at one point per
gap. That is not a shortcut and it is not an approximation of the answer: a
continuous function with no zero and no pole in a gap cannot change sign in it.
What the sampling buys is the guarantee, not a guess.

Then the answer is *periodic*, so only one period is described and the repetition
is said rather than enumerated: there are infinitely many of them.

Closed endpoints are the other half of the story. ``sin(x) > 1/2`` gives open
intervals, because at the zeros the inequality is not satisfied; ``sin(x) ≥ 1/2``
gives closed ones, and getting that wrong is what makes a solution set look right
and not be.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig
from academic_core.errors import UnsupportedError

#: how many sample points per gap, so a sign flip hiding in a gap is unlikely to
#: be missed. One suffices mathematically; more is cheap insurance (§5.5).
MUESTRAS_POR_HUECO = 3

def _cambia_de_signo(e: mx.Expr, var: str) -> bool:
    """Whether ``e`` changes sign anywhere in a period, poles aside.

    A continuous function with no zero cannot change sign, so a change is PROOF
    that a zero exists. That is all it claims: it cannot say where. It is the one
    independent check available before writing «no hay ceros», and without it an
    empty family list from the equation solver reads as a fact about the FUNCTION
    when it is a fact about the SOLVER.

    `cos(x)^3 > 1` passes the same test — and there «no hay soluciones» is the
    truth — so this does not turn every unknown into a refusal. It only stops the
    opposite mistake.
    """
    periodo = D.periodo_minimo(e, var)
    if periodo is None:
        return False
    paso = float(periodo) * math.pi / 96
    anterior = 0
    hubo = False
    for i in range(1, 97):
        valor = mx.evaluate(e, {var: i * paso})
        if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > 1e12:
            continue                     # a pole says nothing about the sign
        signo = 0 if abs(valor.real) < 1e-12 else (1 if valor.real > 0 else -1)
        if hubo and signo and signo != anterior:
            return True
        if signo:
            hubo = True
            anterior = signo
    return False


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Solucion:
    """A periodic solution set: one period, plus how it repeats.

    ``puntos`` is only ever filled for ``=``, where the answer is a set of isolated
    points rather than intervals. It exists because an equation has no interior:
    a sign chart describes the gaps *between* critical points, and for ``=`` there
    are no gaps to describe, only the points themselves.
    """

    conjunto: D.Conjunto
    periodo: Fraction | None
    operador: str
    hipotesis: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    puntos: tuple[D.Punto, ...] = ()

    def texto(self) -> str:
        if self.puntos:
            base = ", ".join(f"{p.texto()}" for p in self.puntos)
            base = f"x = {base}"
        elif self.conjunto.vacio:
            return "no hay soluciones"
        else:
            base = self.conjunto.texto()
        if self.periodo is None:
            return base
        return f"{base}   y se repite cada {self.periodo}·pi"

    @property
    def vacia(self) -> bool:
        return not self.puntos and self.conjunto.vacio

    def contiene(self, coeficiente_pi: Fraction) -> bool:
        """Whether ``coeficiente_pi * pi`` is in the solution, inside one period.

        Reduced modulo the period, because the answer SAYS it repeats every
        ``periodo·pi``: ``0·pi`` and ``periodo·pi`` are the same point, and a set
        that puts one inside and the other outside is not a solution of anything.
        The chart works on ``[0, periodo]``, so the closure of the right end is
        read as well — one point, two spellings, one answer.
        """
        punto = D.punto_pi(coeficiente_pi)
        if self.periodo is not None and self.periodo != 0:
            punto = D.punto_pi(punto.coeficiente % self.periodo)
        if punto in self.puntos or self.conjunto.contiene(punto):
            return True
        if punto.coeficiente == 0 and self.periodo is not None and self.periodo != 0:
            cierre = D.punto_pi(self.periodo)
            return cierre in self.puntos or self.conjunto.contiene(cierre)
        return False


# ---------------------------------------------------------------------------
# the critical points
# ---------------------------------------------------------------------------


def ceros(e: mx.Expr, var: str = "x") -> list[mx.Expr] | None:
    """Where ``e`` vanishes, or ``None`` when this engine cannot say.

    ``None`` is the answer that matters: it is «no lo sé», not «no hay ceros»,
    and the caller must not go on to draw a sign chart as if it knew.

    The order of the cases is deliberate: reciprocals become quotients *first*,
    then the harmless ``- 0`` is taken off, and only then are products and
    quotients decomposed structurally. That order is sound and the equation
    solver cannot do it on its own — the zeros of ``a*b`` are the zeros of ``a``
    together with those of ``b``, and the zeros of ``a/b`` are those of ``a``
    alone, so ``1/tan(x)`` has none and that is a fact, not a case to refuse.
    """
    if not mx.depends(e, var):
        return [] if mx.evaluate(e) != 0 else None
    # Kept, because the existence filter asks the DOMAIN of the expression AS IT
    # WAS WRITTEN. Rewriting `sen(x)/tg(x)` to `cos(x)` does not make the quotient
    # exist where `tg` does not, and a filter that asked `cos(x)` would believe
    # it does — which is how a hole becomes a published zero.
    original = e
    e = _a_cocientes(e)
    if isinstance(e, mx.Sub) and e.right == mx.ZERO:
        return ceros(e.left, var)
    if isinstance(e, mx.Add):
        if isinstance(e.right, mx.Num) and e.right.value == 0:
            return ceros(e.left, var)
        if isinstance(e.left, mx.Num) and e.left.value == 0:
            return ceros(e.right, var)
    if isinstance(e, mx.Div):
        numerador = ceros(e.left, var)
        if numerador is None:
            return None
        return _donde_existe(numerador, original, var)
    if isinstance(e, mx.Mul):
        izquierda, derecha = ceros(e.left, var), ceros(e.right, var)
        if izquierda is None or derecha is None:
            return None
        # A product is zero where EITHER factor is, but only where the product
        # EXISTS. `tg(x)·cos(x)` used to publish `pi/2` and `3pi/2` as zeros, and
        # `tg` does not exist there: two zeros that are not zeros. The filter the
        # quotient branch has always had belongs here too — not because the
        # algebra is different, but because a shared factor is where it bites.
        # The END of the product's period, and only that. Each factor is folded
        # into its OWN period before the union, so for a product less periodic
        # than its parts the last zero is never generated: `tg(x)·cos(x)` is
        # `sen(x)`, of period 2·pi, and `pi` — a real zero — was simply missing,
        # which is also why the sign chart then refused, saying the sign changed
        # inside a gap without a critical point to explain it. That is the engine
        # telling the truth, and the reason this line is here.
        #
        # Spreading the zeros over the WHOLE product period was tried first and
        # over-generates: it moved eight tests in three files. The rule the rest
        # of this module already follows is narrower and does not: `0` and the
        # end of the period are the same point, and nothing else moves.
        # Each factor is folded into its OWN period, and a product can be less
        # periodic than its parts: `tg(x)·cos(x)` is `sen(x)`, of period 2·pi,
        # while `tg` folds at pi — so `pi`, a real zero, was never generated and
        # the sign chart then refused, saying the sign changed inside a gap with
        # no critical point to explain it. That is the engine telling the truth.
        #
        # So each factor is asked again over the PRODUCT's period: its own zeros
        # plus as many whole turns of ITS OWN period as it takes to reach. Only
        # multiples of the factor's period, and only up to the product's — which
        # is what makes this different from spreading the union over the whole
        # product period, which over-generates and cost eight tests.
        per_producto = D.periodo_minimo(e, var)
        juntos: list[mx.Expr] = []
        for factor, sus_ceros in ((e.left, izquierda), (e.right, derecha)):
            juntos = _une(juntos, _ceros_del_factor(factor, sus_ceros,
                                                   per_producto, var))
        return _donde_existe(juntos, original, var)
    if isinstance(e, mx.Pow):
        n = mx.exact_integer(e.exponent)
        if n is not None and n > 1:
            # f^n = 0 exactly where f = 0, for every positive integer n. Treating
            # an even power differently would be the error of thinking that
            # squaring moves the zeros; it does not, it only makes them double.
            return ceros(e.base, var)
    try:
        resolucion = E.resolver(f"{mx.text(e)} = 0", var)
    except UnsupportedError:
        return None
    if resolucion.sin_respuesta:
        return None
    # A solution set that is empty AND carries refusals is «I did not find them»,
    # not «there are none». `cot(x)^3 > 4` published «no hay soluciones» over an
    # expression full of them, because its zeros need `tan(x) = 4^(-1/3)`, which is
    # not a rational multiple of pi, and the equation solver said so in `refusos`
    # while reporting an empty family list. Reading only the families turns «no lo
    # sé» into «no hay», which is the one conversion this module never makes — and
    # «no hay soluciones» over an expression that has them is the worst answer
    # there is.
    if resolucion.vacia:
        if getattr(resolucion, "refusos", ()):
            return None
        # «No families» is not «no zeros» until something independent says so. A
        # continuous function with no pole and no zero cannot change sign, so a
        # sign change ANYWHERE is proof that a zero exists and that the equation
        # solver missed it — by a shape it does not handle, silently. That is how
        # `cot(x)^3 > 4` published «no hay soluciones» over an expression full of
        # them: its zeros need `tan(x) = 4^(-1/3)`, which is not a rational
        # multiple of pi, and nothing said so. `cos(x)^3 > 1` passes the same test
        # — and there «no hay soluciones» is the truth.
        return None if _cambia_de_signo(e, var) else []
    vistos: list[mx.Expr] = []
    for familia in resolucion.familias:
        if not familia.en_x:
            # The solutions are in the substitution variable, not in x. Reading
            # their base as a value of x is how «5·sen(x + pi/3)» published a
            # zero at 0, where the expression is 4.33 and the real zero is 2pi/3.
            continue
        base = _dentro_del_periodo(familia.base)
        if base is not None and all(mx.text(base) != mx.text(v) for v in vistos):
            vistos.append(base)
        elif not mx.depends(familia.base, var):
            # Not a multiple of pi, but an EXACT value and already inside one
            # period — the equation solver wrote it down and there is no reason to
            # drop it. Used to return None here, which is the same false answer as
            # «no zeros» one level down, over an engine that had the zeros.
            limpio = _punto_limpio(familia.base)
            if all(mx.text(limpio) != mx.text(v) for v in vistos):
                vistos.append(limpio)
    if not vistos and resolucion.familias:
        # there ARE zeros, and they are values this engine cannot even write as an
        # expression — an unresolved root of a quartic, say. Saying «no zeros» here
        # would be the exact same false answer as «no solutions», one level down.
        return None
    return vistos


def puntos_inexistentes(e: mx.Expr, var: str = "x") -> tuple[D.Punto, ...]:
    """Where the expression does not exist.

    The OPEN ends of the domain's intervals, and only those: a closed end is a
    point where the expression is defined, and calling it a discontinuity
    invents one wherever a function happens to stop at a finite bound — which is
    the whole domain of ``arcsen(2·sen x)``.

    One implementation for the two jobs that need it. T-13 needs it to keep an
    inexistent point out of the list of zeros, and T-23 needs it to list the
    discontinuities; a second copy is a second thing to get wrong.
    """
    if not mx.depends(e, var):
        return ()
    try:
        conjunto = dominio(e, var)
    except UnsupportedError:
        return ()
    puntos = [p for intervalo in conjunto.intervalos
              for p, abierto in ((intervalo.izq, intervalo.abierto_izq),
                                 (intervalo.der, intervalo.abierto_der))
              if p is not None and abierto]
    return tuple(sorted(set(puntos), key=lambda p: p.coeficiente))


def _donde_existe(valores: list[mx.Expr], e: mx.Expr, var: str) -> list[mx.Expr]:
    """Drop from ``valores`` the ones where ``e`` does not exist.

    The zeros of a quotient are those of its numerator ALONE, which is why
    ``1/tan(x)`` has none and that is a fact. But a point where the denominator
    vanishes is a pole, and there the expression does not exist at all: ``0/0``
    is not a zero of ``sen(x)/x``, it is a point where nothing is defined, and
    publishing it as a zero put 0 on the sign chart.

    The holes are asked of the DOMAIN rather than by solving ``denominator = 0``
    again: the equation solver declines ``x = 0`` as outside its cases —honestly,
    which is why this filter has to exist— and a domain that does not know where
    an expression stops existing is not a domain.
    """
    huecos = {p.texto() for p in puntos_inexistentes(e, var)}
    if not huecos:
        return list(valores)
    return [v for v in valores
            if not ((p := _a_punto(v)) is not None and p.texto() in huecos)]


def removibles(e: mx.Expr, var: str = "x") -> tuple[tuple[D.Punto, float], ...]:
    """The inexistence points where the value has a limit, and what the limit is.

    A domain says where an expression stops existing. It does not say whether
    that was a pole or a hole, and the difference is the whole question behind
    ``1/tan(x)`` at ``pi/2``: the expression does not exist there, and the limit
    is 0. Announcing it as a pole says the function blows up, which is the one
    thing it does not do.

    Decided by STRUCTURE, not by sampling a limit. ``trig.simplify`` writes the
    reciprocal as ``cot(x)``, and the domain of ``cot`` includes ``pi/2``: the
    point stopped being singular in the simplification, so it was a hole. A pole
    stays singular there, because cancelling it is exactly what cannot be done.

    It reads the simplified form and not the written one, so a hole the
    simplifier does not recognise is reported as a pole. That is the safe
    direction on purpose: a pole announced as a pole is right, and a hole
    announced as a hole that is not one would be a limit invented out of a
    simplification. ``sin(x)/x`` at 0 is such a case — its limit is 1 and no
    rewrite here reaches it, so it stays a pole and this function says nothing
    about it rather than guessing 1.

    The value returned is the value of the CONTINUATION at the hole, which is
    what a limit is, computed in floating point and carrying its own residue:
    ``1/tan(x)`` at ``pi/2`` comes out as 6·10⁻¹⁷ where the answer is exactly 0.
    """
    from academic_core.domain.engineering.mathlab import trig

    holes = puntos_inexistentes(e, var)
    if not holes:
        return ()
    try:
        canonica = trig.simplify(e)
    except Exception:
        return ()
    siguen_existiendo = {p.texto() for p in puntos_inexistentes(canonica, var)}
    salida: list[tuple[D.Punto, float]] = []
    for punto in holes:
        if punto.texto() in siguen_existiendo:
            continue                     # still singular: a pole, not a hole
        valor = mx.evaluate(canonica, {var: _coordenada_de(punto)})
        if valor is None or valor.imag != 0 or abs(valor.real) >= 1e12:
            continue
        salida.append((punto, valor.real))
    return tuple(salida)


def _coordenada_de(punto: D.Punto) -> float:
    """The real number a ``Punto`` names: ``1/4·pi`` is stored as ``1/4``."""
    return float(punto.coeficiente) * (math.pi if punto.es_pi else 1.0)


def _llamadas(e: mx.Expr) -> list[mx.Call]:
    salida: list[mx.Call] = []
    pila = [e]
    while pila:
        actual = pila.pop()
        if isinstance(actual, mx.Call):
            salida.append(actual)
            pila.extend(actual.args)
        elif isinstance(actual, mx.Root):
            # an even root needs its radicand >= 0, and it is reached as «sqrt»
            salida.append(mx.Call("sqrt", (actual.radicand,)))
            pila.append(actual.radicand)
        elif isinstance(actual, mx.Neg):
            pila.append(actual.arg)
        elif isinstance(actual, mx.Pow):
            pila.extend((actual.base, actual.exponent))
        elif isinstance(actual, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            pila.extend((actual.left, actual.right))
    return salida


def singularidades(e: mx.Expr, var: str = "x") -> list[mx.Expr] | None:
    """Where ``e`` does not exist, apart from its quotients.

    T-13 asks for «ceros, singularidades y denominadores», and the third one is
    not the whole story: ``tan(x)`` has a pole at ``pi/2`` with no denominator
    anywhere in the expression. Missing that pole is what makes ``tan(x) < 1``
    come out as one interval when it is two.

    The poles of ``tan`` are the zeros of ``cos``, and those of ``cot`` the zeros
    of ``sin``, so this reuses the equation solver rather than inventing a table.
    """
    salida: list[mx.Expr] = []
    for llamada in _llamadas(e):
        denominador = {"tan": "cos", "cot": "sin",
                       "sec": "cos", "csc": "sin"}.get(llamada.name)
        if denominador is None:
            continue
        ceros_del = ceros(_fn(denominador, llamada.args[0]), var)
        if ceros_del is None:
            return None
        salida = _une(salida, ceros_del)
    return salida



def _ceros_del_factor(factor: mx.Expr, ceros: list[mx.Expr],
                      per_producto: Fraction | None, var: str) -> list[mx.Expr]:
    """``ceros`` plus whole turns of the factor's own period, up to the product's.

    ``tg`` folds its zeros at ``pi`` and reports only ``0``, so a product of period
    ``2·pi`` never sees ``pi``. The turns are multiples of the FACTOR's period and
    stop at the product's, which is the difference between filling a real gap and
    inventing points: only the zeros of ``tg`` move, and only as far as ``sen``
    needs them.
    """
    if per_producto is None:
        return ceros
    propio = D.periodo_minimo(factor, var)
    if propio is None or propio >= per_producto or per_producto % propio != 0:
        return ceros
    vueltas = int(per_producto / propio) - 1
    base = {c for c in (_coeficiente_pi(v) for v in ceros) if c is not None}
    extra = [mx.Mul(mx.Num(c + k * propio), mx.PI)
             for c in sorted(base) for k in range(1, vueltas + 1)]
    return _une(ceros, extra)


def _une(a: list[mx.Expr], b: list[mx.Expr]) -> list[mx.Expr]:
    salida = list(a)
    for v in b:
        if all(mx.text(v) != mx.text(u) for u in salida):
            salida.append(v)
    return salida


def _a_cookies_base(e: mx.Expr) -> mx.Expr:
    """The base of a power, with the reciprocals unwrapped.

    Split out so that ``_a_cocientes`` can read the quotient apart before deciding
    what to do with the exponent; calling ``_a_cocientes`` again here would push
    the exponent down before the quotient has been recognised, which is the order
    that matters.
    """
    if isinstance(e, mx.Call) and len(e.args) == 1:
        for fuente, (num, den) in (("sec", ("1", "cos")), ("csc", ("1", "sin")),
                                   ("cot", ("cos", "sin"))):
            if e.name == fuente:
                return mx.Div(mx.Num(Fraction(1)) if num == "1" else _fn(num, e.args[0]),
                              _fn(den, e.args[0]))
        return mx.Call(e.name, tuple(_a_cookies_base(a) for a in e.args))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_cookies_base(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_a_cookies_base(e.base), _a_cookies_base(e.exponent))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        # The reduction is tried on the children AS WRITTEN, before the reciprocal
        # rewrite: after it, `sen(x)/tg(x)` is `sen(x)/(cos(x)/sen(x))` and the pair
        # `sen`, `tg` is no longer there to recognise.
        return type(e)(_a_cookies_base(e.left), _a_cookies_base(e.right))
    return e


def _a_cocientes(e: mx.Expr) -> mx.Expr:
    """``sec(u) → 1/cos(u)`` and friends, so the solver sees through them.

    The power goes INSIDE the quotient, which is the whole difficulty. Rewriting
    ``sec(u)^n`` as ``(1/cos(u))^n`` is the same number in a different shape, and
    it is a shape nothing downstream recognises: ``sec(x)^2 = 4`` came out refused
    while ``1/cos(x)^2 = 4`` was solved, and the student who writes the reciprocal
    spelling is the one who gets refused. So the exponent is pushed down and the
    tree comes out the way it would have been written — ``1/cos(u)^n``.

    Only for a positive integer exponent, where ``(a/b)^n = a^n/b^n`` is exact.
    A fractional power is a different question: on the reals ``(-1)^(1/2)`` does
    not exist, and folding a sign through a root to make two trees match is the
    kind of convenience that turns into a wrong answer.
    """
    if isinstance(e, mx.Call) and len(e.args) == 1:
        for fuente, (num, den) in (("sec", ("1", "cos")), ("csc", ("1", "sin")),
                                   ("cot", ("cos", "sin"))):
            if e.name == fuente:
                return mx.Div(mx.Num(Fraction(1)) if num == "1" else _fn(num, e.args[0]),
                              _fn(den, e.args[0]))
        return mx.Call(e.name, tuple(_a_cocientes(a) for a in e.args))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_cocientes(e.arg))
    if isinstance(e, mx.Pow):
        # `cot(u)^n` is `1/tan(u)^n` and NOT `(cos/sin)^n`. Both are the reciprocal
        # rewrite of the same thing, but only the first is a shape the solvers
        # recognise — which is why `cot(x)^2 > 1` came out refused while
        # `1/tan(x)^2 > 1` was solved, and why `sec` needed the same treatment.
        # The quotient form is kept for n = 1, where `tg` and `1/tg` are the same
        # question and the reciprocal spelling is the one that reads better.
        if (n_pre := mx.exact_integer(_a_cocientes(e.exponent))) is not None \
                and n_pre > 1 and isinstance(e.base, mx.Call) and e.base.name == "cot":
            return mx.Div(mx.ONE, mx.Pow(_fn("tan", e.base.args[0]),
                                         mx.Num(Fraction(n_pre))))
        base = _a_cookies_base(e.base)
        exponente = _a_cocientes(e.exponent)
        n = mx.exact_integer(exponente)
        if isinstance(base, mx.Div) and n is not None and n > 1:
            # `1^n` is `1`, and writing `1^2` above a quotient is noise that every
            # comparison downstream then has to strip
            arriba = (base.left if mx.exact_integer(base.left) == 1
                      else mx.Pow(base.left, exponente))
            return mx.Div(arriba, mx.Pow(base.right, exponente))
        return mx.Pow(base, exponente)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_a_cocientes(e.left), _a_cocientes(e.right))
    return e


# NOTA, y es un NO HECHO a proposito: `sen(u)/tg(u)` es `cos(u)` y `cos(u)/sec(u)`
# es `cos(u)^2`, y reducirlos aqui NO es una mejora. Se probo y se revirtio.
#
# La razon esta en el periodo, no en el dominio. `cos(u)^2` tiene periodo `pi` y
# `cos(u)/sec(u)` tiene periodo `2·pi`, porque `sec` no existe donde `cos` se
# anula: reescribir borra el dominio Y el periodo, y el conjunto publicado pasa a
# ser el de otra funcion —`cos(x)/sec(x) > 1/2` salia mal en 193 de 383 puntos—.
# Un filtro de existencia no lo arregla, porque el filtro quita puntos y lo que
# falta es un turno entero.
#
# El sitio correcto es la reescritura de identidades, que conserva el dominio
# mientras simplifica. Aqui no, y por eso queda escrito en vez de hecho.

def _fn(nombre: str, arg: mx.Expr) -> mx.Expr:
    return mx.Call(nombre, (arg,))


def _coeficiente_pi(e: mx.Expr) -> Fraction | None:
    """The coefficient of ``pi`` in ``e``, or ``None`` when it is not one.

    A single reader for both jobs the module has: placing a solution value inside
    the period, and turning it into a point of the chart. Having one reader is not
    tidiness — it is the reason ``0`` cannot be understood in one place and
    forgotten in the other, which is how ``tan(x) >= 0`` lost the endpoint where it
    equals zero.

    The sign is read through ``trig._terminos`` rather than ``trig._factores``,
    because ``_factores`` does not look inside a ``Neg``: a value written ``-pi/2``
    would come back as ``None`` and the chart would lose one of the two zeros of
    ``cos(x)``.
    """
    return trig._multiplo_de_pi(e)


def _dentro_del_periodo(base: mx.Expr) -> mx.Expr | None:
    """Reduce a solution value into ``[0, 2pi)``.

    ``None`` when the value is not a multiple of ``pi``: an ``asin(c)`` cannot be
    shifted by ``2k*pi`` without evaluating it, and the caller has to know that
    rather than assume it.
    """
    coeficiente = _coeficiente_pi(base)
    return mx.Mul(mx.Num(coeficiente % 2), mx.PI) if coeficiente is not None else None


def _en_un_periodo(p: D.Punto, periodo: Fraction) -> float:
    """Where a point sits inside one period, as a plain number.

    A multiple of ``pi`` folds exactly, by arithmetic. An expression point folds by
    subtracting whole turns until it is inside, and that is a FLOAT comparison on
    purpose: the alternative is refusing every point the grid cannot hold
    exactly, which is where this started.
    """
    if p.expresion is None:
        return float(p.coeficiente % periodo)
    v = p.valor() / 3.141592653589793
    return v % float(periodo)


def _punto_limpio(e: mx.Expr) -> mx.Expr:
    """A critical point written the way a textbook writes it.

    Two things happen here, and both are about what the READER sees rather than
    about the truth of the answer.

    - Arithmetic over numbers is folded, bottom up. The equation solver reaches
      ``1/3`` through the rational-root theorem and hands it over as
      ``(-0 + 6)/(-18)``, which is true and unreadable; a critical point printed
      that way is a point the reader has to re-derive before they can check it.
      Folding is done with exact rationals, so it cannot change the value.
    - a negative argument is pulled out to a negation, using the identity that
      does not move the point: ``arcsen(-t) = -arcsen(t)`` and
      ``acos(-t) = pi - acos(t)``.

      There is a third spelling here, ``arcsen(-t) = pi - arcsen(t)``, and it is
      WRONG to use: it differs from ``-arcsen(t)`` by exactly ``pi``, so it is a
      different point on the circle unless the expression happens to have period
      ``pi``. It was in this function for one measurement and produced a correct
      answer for ``cosec(x)^2 > 9`` — whose expression does have period pi — which
      is the most dangerous way to be wrong: right for the case you measured and
      wrong for every other.

    None of this changes which point it is. That is the whole requirement.
    """
    if isinstance(e, mx.Call) and e.name in ("asin", "acos", "atan") \
            and len(e.args) == 1:
        v = _racional(_plegar_mezcla(e.args[0]))
        if v is None:
            return e
        if v > 0:
            return mx.Call(e.name, (mx.Num(v),))
        positivo = mx.Call(e.name, (mx.Num(-v),))
        # arcsen and arctan are ODD: arcsen(-t) = -arcsen(t), and the point moves
        # to its mirror through the origin — which is NOT where pi - arcsen(t) is,
        # because that differs from -arcsen(t) by exactly pi, so it is a different
        # place on the circle unless the expression happens to have period pi. That
        # third spelling was in this function for one measurement and got
        # `cosec(x)^2 > 9` right, whose expression does have period pi: right for
        # the case you measured and wrong for every other.
        #
        # arccos is the even one, and even does not mean symmetric: arccos(-t) is
        # the MIRROR point, pi - arccos(t), which is where it actually is.
        return mx.Sub(mx.PI, positivo) if e.name == "acos" else mx.Neg(positivo)
    return _plegar_mezcla(e)


def _plegar(e: mx.Expr) -> mx.Expr:
    """Rebuild ``e`` with the arithmetic over numbers done exactly, bottom up."""
    if isinstance(e, mx.Num):
        return e
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        izquierda, derecha = _plegar(e.left), _plegar(e.right)
        if _solo_numeros(izquierda) and _solo_numeros(derecha):
            try:
                r = _racional_valor(mx.evaluate(_rehacer(e, izquierda, derecha), {}))
            except Exception:              # noqa: BLE001 — «no se» es respuesta
                r = None
            if r is not None:
                return mx.Num(r)
        return _rehacer(e, izquierda, derecha)
    if isinstance(e, mx.Neg):
        interior = _plegar(e.arg)
        if _solo_numeros(interior):
            r = _racional(interior)
            if r is not None:
                return mx.Num(-r)
        return mx.Neg(interior)
    if isinstance(e, mx.Call):
        # into the arguments, because that is where `pi - arcsen((-0 + 6)/(-18))`
        # hides: the arcsine is nested one level down and a rewrite that only looks
        # at the outside leaves it exactly as it was
        limpio = tuple(_punto_limpio(a) for a in e.args)
        return e if limpio == e.args else mx.Call(e.name, limpio)
    return e


def _rehacer(e: mx.Expr, izquierda: mx.Expr, derecha: mx.Expr) -> mx.Expr:
    """``e`` with its two children replaced."""
    if isinstance(e, mx.Add):
        return mx.Add(izquierda, derecha)
    if isinstance(e, mx.Sub):
        return mx.Sub(izquierda, derecha)
    if isinstance(e, mx.Mul):
        return mx.Mul(izquierda, derecha)
    return mx.Div(izquierda, derecha)


def _racional_valor(valor) -> Fraction | None:
    if abs(getattr(valor, "imag", 0.0)) > 1e-12:
        return None
    real = getattr(valor, "real", valor)
    r = Fraction(real).limit_denominator(10 ** 9)
    return r if abs(float(r) - real) < 1e-12 else None


def _lineal(e: mx.Expr) -> tuple[Fraction, Fraction] | None:
    """``e`` as ``racional + racional·pi``, or ``None`` when it is not linear.

    Needed because the canonical form of a point inside one period is a sum with a
    whole number of periods, and folding has to be able to CANCEL those again:
    ``pi - arcsen(-1/3) - pi`` is ``arcsen(1/3)``, and printed unsimplified it is a
    second spelling of a point the answer already had, which the chart then read
    as a different critical point.
    """
    if isinstance(e, mx.Num):
        return Fraction(e.value), Fraction(0)
    if isinstance(e, mx.Const) and e.name == "pi":
        return Fraction(0), Fraction(1)
    if isinstance(e, mx.Neg):
        interior = _lineal(e.arg)
        return None if interior is None else (-interior[0], -interior[1])
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul)):
        izquierda = _lineal(e.left)
        derecha = _lineal(e.right)
        if izquierda is None or derecha is None:
            return None
        if isinstance(e, mx.Mul):
            a, b = izquierda
            c, d = derecha
            if b == 0 and d == 0:
                return a * c, Fraction(0)
            if b == 0 and c == 0:
                return Fraction(0), a * d
            if b == 0:
                return a * c, a * d          # (a)·(c + d·pi)
            if d == 0:
                return c * a, c * b          # (a + b·pi)·(c)
            return None                      # pi² is not linear
        if isinstance(e, mx.Add):
            return izquierda[0] + derecha[0], izquierda[1] + derecha[1]
        return izquierda[0] - derecha[0], izquierda[1] - derecha[1]
    return None


def _de_lineal(r: Fraction, p: Fraction) -> mx.Expr | None:
    """Back to an expression, or ``None`` when it would have to be ``0``."""
    if p == 0:
        return mx.Num(r)
    if r == 0:
        return mx.PI if p == 1 else mx.Mul(mx.Num(p), mx.PI)
    return mx.Add(mx.Num(r), mx.PI if p == 1 else mx.Mul(mx.Num(p), mx.PI))


def _plegar_lineal(e: mx.Expr) -> mx.Expr | None:
    """``e`` folded exactly when it is ``r + p·pi``, else ``None``."""
    lineal = _lineal(e)
    return None if lineal is None else _de_lineal(*lineal)


def _plegar_mezcla(e: mx.Expr) -> mx.Expr:
    """Fold every linear part of the tree exactly, leave the rest alone.

    A point inside one period is usually ``pi - arcsen(-1/3) - pi``: a linear part
    that cancels completely and one function call that does not. Folding the whole
    expression as linear leaves the ``pi`` in it, and then the chart holds two
    spellings of one point — ``asin(1/3)`` and ``pi - asin(-1/3) - pi`` — finds it
    cannot establish their order, and refuses an inequality it can otherwise
    answer.

    So the linear leaves are gathered, folded among themselves, and put back once.
    Anything that is not linear is returned untouched, which is not a failure: a
    function call is a value nobody here can expand, and its presence is exactly
    why the point is not a multiple of pi.
    """
    if isinstance(e, mx.Num):
        return e
    if isinstance(e, mx.Const):
        return e
    if isinstance(e, mx.Neg):
        interior = _plegar_mezcla(e.arg)
        lineal = _lineal(interior)
        return mx.Neg(interior) if lineal is None else _de_lineal(-lineal[0],
                                                                  -lineal[1])
    if isinstance(e, mx.Call):
        if e.name in ("asin", "acos", "atan") and len(e.args) == 1:
            return _punto_limpio(e)
        args = tuple(_plegar_mezcla(a) for a in e.args)
        return e if args == e.args else mx.Call(e.name, args)
    if isinstance(e, mx.Mul):
        izquierda, derecha = _plegar_mezcla(e.left), _plegar_mezcla(e.right)
        producto = None
        if _lineal(izquierda) and _lineal(derecha):
            producto = _lineal(_rehacer(e, izquierda, derecha))
        return _de_lineal(*producto) if producto is not None \
            else _rehacer(e, izquierda, derecha)
    if isinstance(e, (mx.Add, mx.Sub)):
        return _plegar_suma(_hojas(e))
    return e


def _hojas(e: mx.Expr, signo: int = 1) -> list[tuple[int, mx.Expr]]:
    """The terms of a sum with their signs, stopping at anything not a sum."""
    if isinstance(e, mx.Add):
        return _hojas(e.left, signo) + _hojas(e.right, signo)
    if isinstance(e, mx.Sub):
        return _hojas(e.left, signo) + _hojas(e.right, -signo)
    if isinstance(e, mx.Neg):
        return _hojas(e.arg, -signo)
    return [(signo, e)]


def _plegar_suma(hojas: list[tuple[int, mx.Expr]]) -> mx.Expr:
    """Sum: the linear terms folded into one, the others left in place.

    Folding only when BOTH sides are linear is not enough, and the case that needs
    it is the ordinary one: ``pi - arcsen(-1/3) - pi`` has a ``pi`` on each side of
    a function call, so the two never meet. Gathered, they cancel, and what is left
    is the point itself.

    The subtraction is a real ``Sub`` and not ``Add`` with a negated child, because
    ``text`` promises that reading back what it wrote gives the same expression —
    and ``pi - arcsen(1/3)`` reads back as a ``Sub``, while ``pi + -arcsen(1/3)``
    reads back as the ``Add`` it was printed from. A printer fix would have been the
    wrong place to solve this.
    """
    racional, por_pi = Fraction(0), Fraction(0)
    partes: list[tuple[int, mx.Expr]] = []
    for signo, hoja in hojas:
        # the leaves are folded too, or `pi - arcsen(-1/3)` keeps the negative
        # argument that the identity two lines above exists to remove
        hoja = _plegar_mezcla(hoja)
        if isinstance(hoja, mx.Neg):
            hoja, signo = hoja.arg, -signo
        lineal = _lineal(hoja)
        if lineal is None:
            partes.append((signo, hoja))
        else:
            racional += signo * lineal[0]
            por_pi += signo * lineal[1]
    if racional or por_pi:
        partes.insert(0, (1, _de_lineal(racional, por_pi)))
    if not partes:
        return mx.Num(0)
    salida = partes[0][1] if partes[0][0] > 0 else mx.Neg(partes[0][1])
    for signo, hoja in partes[1:]:
        salida = mx.Add(salida, hoja) if signo > 0 else mx.Sub(salida, hoja)
    return salida


def _solo_numeros(e: mx.Expr) -> bool:
    """Whether the tree is arithmetic over numbers and nothing else.

    The discipline that keeps ``pi - arcsen(1/3)`` from being read as a number:
    evaluating an expression with no free variable in it gives a value for almost
    any constant, so «no unknowns left» is NOT enough to decide that a number can
    be written down. It has to be built only out of numbers.
    """
    if isinstance(e, mx.Num):
        return True
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _solo_numeros(e.left) and _solo_numeros(e.right)
    if isinstance(e, mx.Neg):
        return _solo_numeros(e.arg)
    return False


def _racional(e: mx.Expr) -> Fraction | None:
    """The exact rational ``e`` is, or ``None`` when it is not one."""
    if isinstance(e, mx.Num):
        return Fraction(e.value)
    if not _solo_numeros(e):
        return None
    try:
        valor = mx.evaluate(e, {})
    except Exception:                      # noqa: BLE001 — any failure is «no»
        return None
    if valor is None or abs(valor.imag) > 1e-12:
        return None
    racional = Fraction(valor.real).limit_denominator(10 ** 9)
    return racional if abs(float(racional) - valor.real) < 1e-12 else None


def _dentro_del_periodo_exacto(punto: D.Punto, periodo: Fraction) -> D.Punto:
    """A point moved into ``[0, periodo·pi]`` as an EXPRESSION, exactly.

    The same point has several exact spellings — ``-arcsen(1/3)`` and
    ``pi - arcsen(1/3)`` are one place on the circle — and which one a chart keeps
    used to be decided by which came off the list first. So the answer to
    ``cosec(x)^2 <= 9`` ended at ``-arcsen(1/3)`` with a duplicate of the other end
    as a separate piece: two intervals, one point, and a set whose shape no
    textbook uses.

    Adding whole periods is arithmetic on the expression, so nothing is rounded. The
    move is repeated because folding the linear terms can push the value back out:
    ``-2·pi - arcsen(1/3)`` comes out of the first fold, and it needs three more
    periods before it is inside.
    """
    if punto.expresion is None:
        return punto
    largo = float(periodo) * 3.141592653589793
    expresion = _plegar_mezcla(punto.expresion)
    for _ in range(6):
        valor = _valor_de(expresion)
        if valor is None:
            break
        # NEGATIVE of the floor, because the periods are ADDED: a point at -0.34
        # with a period of pi is at 2.80, one period up, not one period down.
        vueltas = -math.floor(valor / largo)
        if vueltas == 0:
            break
        cuantos = Fraction(vueltas * periodo)
        expresion = _plegar_mezcla(
            mx.Add(expresion, mx.PI if cuantos == 1
                   else mx.Mul(mx.Num(cuantos), mx.PI)) if cuantos > 0
            else mx.Sub(expresion, mx.PI if cuantos == -1
                        else mx.Mul(mx.Num(-cuantos), mx.PI)))
    return punto if expresion == punto.expresion else D.Punto(expresion=expresion)


def _valor_de(expresion: mx.Expr) -> float | None:
    try:
        valor = mx.evaluate(expresion, {})
    except Exception:                      # noqa: BLE001 — «no se» es respuesta
        return None
    if valor is None or abs(getattr(valor, "imag", 0.0)) > 1e-12:
        return None
    return float(valor.real)


def _posicion(punto: D.Punto, periodo: Fraction) -> float:
    """Where a point sits in one period, in units of ``pi``, to nine decimals.

    Nine decimals is the tolerance for calling two spellings the same point.
    Without it the grid carried ``0.108173247`` twice — once for ``arcsen(1/3)``
    and once for ``pi + arcsen(1/3)`` — and two spellings of one point became two
    critical points, which produced zero-width gaps and endpoints that a reader
    cannot match up.
    """
    return _en_un_periodo(punto, periodo)


def _punto(valor: Fraction) -> D.Punto:
    return D.punto_pi(valor)


def _a_punto(e: mx.Expr) -> D.Punto | None:
    """A solution value as a point: a multiple of pi, or an exact expression.

    The second form is what a value like ``arcsen(1/3)`` is. It used to come back
    as ``None`` and take the whole answer down with it — ``cosec(x)^2 > 9`` was
    refused with «no se saben los ceros» by an engine whose own equation solver had
    already written ``arcsen(1/3)`` down. Refusing to PLACE a point is not the
    same as not knowing it, and only the second one is a real gap.
    """
    coeficiente = _coeficiente_pi(e)
    if coeficiente is not None:
        return D.punto_pi(coeficiente)
    if not mx.depends(e, "x"):
        return D.Punto(expresion=e)
    return None


def resolver_inequidad(texto_inequidad: str, var: str = "x") -> Solucion:
    """Solve ``f(x) REL 0`` and describe the answer as a periodic set."""
    operador, izquierda, derecha = _separa(texto_inequidad)
    a = _parse(izquierda, var)
    b = _parse(derecha, var)
    f = mx.Sub(a, b)
    periodo = D.periodo_minimo(f, var)
    hipotesis = list(_metodo())

    # Periodicity is checked first: an aperiodic expression cannot be answered by
    # a repeating pattern at all, and saying that is more useful than reporting
    # that its zeros are unknown — which is a different problem entirely.
    if periodo is None:
        raise sin_refuso(
            "esta expresión no es periódica, así que la solución no se puede dar "
            "como un patrón que se repite; se puede calcular por intervalos, pero "
            "eso todavía no está hecho (§5.4)")

    ceros_f = ceros(f, var)
    if ceros_f is None:
        raise sin_refuso(
            "no se saben los ceros de esta expresión, y sin ellos no hay carta de "
            "signos que sea fiable. Eso NO es «no hay soluciones»: es que este "
            "motor todavía no lo resuelve (§5.4)")

    singulares: list[mx.Expr] = []
    for denominador in D.denominadores(f):
        ceros_d = ceros(denominador, var)
        if ceros_d is None:
            raise sin_refuso(
                f"no se saben los ceros de «{mx.text(denominador)}», que es un "
                "denominador: sin ellos no se sabe dónde deja de existir la "
                "expresión (§5.4)")
        singulares = _une(singulares, ceros_d)
    # and the poles the functions bring with them, which have no denominator at all
    de_funciones = singularidades(f, var)
    if de_funciones is None:
        raise sin_refuso(
            "no se sabe dónde están los polos de las funciones que aparecen "
            "(tan y cot se anulan en ciertos puntos), así que la carta de signos "
            "no sería fiable (§5.4)")
    singulares = _une(singulares, de_funciones)
    if singulares:
        hipotesis.append(
            "los denominadores también cuentan como puntos críticos: son puntos "
            "donde la expresión no existe, y el signo puede cambiar ahí sin que "
            "haya un cero de por medio")

    period_pi = periodo  # dominio.periodo_minimo ya devuelve la razón en pi
    criticos = sorted({c for c in (_a_punto(v) for v in ceros_f + singulares)
                       if c is not None},
                      key=lambda p: _en_un_periodo(p, period_pi))
    if len(criticos) < len([v for v in ceros_f if _a_punto(v)]) + \
            len([v for v in singulares if _a_punto(v)]):
        raise sin_refuso(
            "algún cero no se puede escribir como número exacto, así que el "
            "patrón periódico no se puede expresar de forma exacta (§5.4)")


    if operador == "=":
        # An equation has no interior. The sign chart describes the gaps between
        # critical points, and for "=" the answer is the critical points
        # themselves — the zeros, and not the poles, which is the one place where
        # the two are not interchangeable.
        puntos = tuple(sorted({p for p in (_a_punto(v) for v in ceros_f)
                               if p is not None},
                              key=lambda p: p.coeficiente % period_pi))
        if not puntos and ceros_f:
            raise sin_refuso(
                "los ceros existen pero no se pueden escribir como múltiplos "
                "exactos de pi, así que el conjunto de soluciones no es exacto "
                "(§5.4)")
        hipotesis.append(
            "con «=» la solución son los ceros, no los intervalos: una ecuación no "
            "tiene interior, y los polos quedan fuera porque allí la expresión no "
            "existe")
        return Solucion(D.Conjunto(), periodo, operador,
                        hipotesis=tuple(hipotesis), puntos=puntos)

    ceros_p = {p for p in (_a_punto(v) for v in ceros_f) if p is not None}
    polos_p = {p for p in (_a_punto(v) for v in singulares) if p is not None}
    piezas = _carta_de_signos(f, var, periodo, ceros_p, polos_p, operador)
    return Solucion(piezas, periodo, operador, hipotesis=tuple(hipotesis))


def _carta_de_signos(f: mx.Expr, var: str, periodo: Fraction,
                     ceros_p: set[D.Punto], polos_p: set[D.Punto],
                     operador: str) -> D.Conjunto:
    """One interval per gap, kept when the sign matches ``operador``.

    Every endpoint is decided on its own, because the three kinds of point are not
    interchangeable:

    - a **zero** is in the set for ``>=`` and out for ``>``, which is the ordinary
      business;
    - a **pole** is never in the set, for any operator, because the expression does
      not exist there — closing it would put a point in the solution at which the
      inequality cannot even be evaluated;
    - the **point where the period starts** is neither, and it has to be read off
      the the value of the function. Leaving it always open silently drops a real
      solution: ``cos(x)^2 > 1/2`` holds at 0, and 0 is where the chart begins.

    The points are ``Punto``s and not fractions of pi, because a critical point is
    not always on that grid: the zeros of ``cosec(x)^2 > 9`` are ``arcsen(1/3)``
    and ``pi - arcsen(1/3)``, and the engine knows both exactly.

    The grid keeps the POSITION and the POINT together instead of throwing one away.
    The position is what the gaps are measured in, and it has to be a float
    because two spellings of one point only agree to about fifteen digits; the
    point is what gets published, and for a multiple of pi that means the exact
    rational rather than its fifteen-digit image — rounding the grid and rebuilding
    published ``1/6·pi`` as ``83333336/500000015·pi``, which is the same number to
    a thousandth of a percent and useless to anyone checking the answer.
    """
    criticos: list[tuple[float, D.Punto]] = []

    def anota(posicion: float, punto: D.Punto) -> None:
        for i, (otra, guardada) in enumerate(criticos):
            if abs(otra - posicion) < 1e-9:
                # an exact expression is a better spelling than a rational
                # approximation of it, so it takes the slot
                if guardada.expresion is None and punto.expresion is not None:
                    criticos[i] = (otra, punto)
                return
        criticos.append((posicion, punto))

    for pto in ceros_p | polos_p:
        plegado = _dentro_del_periodo_exacto(pto, periodo)
        canonico = (plegado if plegado.expresion is not None
                    else D.punto_pi(plegado.coeficiente % periodo))
        anota(_posicion(plegado, periodo), canonico)
    anota(0.0, D.Punto(Fraction(0)))
    anota(float(periodo), D.punto_pi(periodo))
    criticos.sort(key=lambda par: par[0])

    piezas: list[D.Intervalo] = []
    for (izq, punto_izq), (der, punto_der) in zip(criticos, criticos[1:]):
        if der - izq <= 0:
            continue
        signo = _signo_del_hueco(f, var, izq, der)
        if not _cumple(signo, operador):
            continue
        abierta_izq = not _extremo_entra(f, var, izq, periodo,
                                         ceros_p, polos_p, operador)
        abierta_der = not _extremo_entra(f, var, der, periodo,
                                         ceros_p, polos_p, operador)
        piezas.append(D.Intervalo(punto_izq, punto_der, abierta_izq, abierta_der))

    # A solution can have no interior at all, and a chart of GAPS never sees it:
    # `sen(x) >= 1` holds only at the two tangencies, no gap has positive sign,
    # and the answer came out empty — a false «no hay soluciones» over an
    # expression full of them. The critical points that satisfy the inequality on
    # their own are added here, and skipped when a kept interval covers them.
    for posicion, punto in criticos:
        if abs(posicion - float(periodo)) < 1e-9:
            continue                     # the end of the period is the start of it
        if any(abs(posicion - _posicion(q, periodo)) < 1e-9 for q in polos_p):
            continue                     # a pole is never in the solution set
        if not _extremo_entra(f, var, posicion, periodo, ceros_p, polos_p,
                              operador):
            continue
        if any(intervalo.contiene(punto) for intervalo in piezas):
            continue
        piezas.append(D.Intervalo(punto, punto, False, False))
    return D.desde_intervalos(piezas, mergir_tocados=False)


def _punto_de_valor(v: float) -> D.Punto:
    """A grid coordinate, which is in units of ``pi``, as a point.

    ALWAYS a multiple of ``pi``, never a plain rational: the grid coordinate is a
    count of halves of pi, and handing it over as the rational ``1`` publishes an
    interval ``(0, 1)`` where the answer is ``(0, pi)``. That mistake made six
    inequalities come out with their endpoints moved, and the function name is the
    only warning it will ever give.
    """
    c = Fraction(v).limit_denominator(10 ** 9)
    if abs(float(c) - v) < 1e-12:
        return D.punto_pi(c)
    return D.Punto(expresion=mx.Mul(mx.Num(c), mx.PI))


def _signo_del_hueco(f: mx.Expr, var: str, izquierda: float,
                      derecha: float) -> float:
    """The sign on one gap, sampled — and refused rather than guessed.

    The gap arrives in units of ``pi``, and that is what the error message says,
    because a gap with an ``arcsen`` at one end is the normal case now and its
    bound is still a number the reader can place on the circle.
    """
    paso = (derecha - izquierda) / (MUESTRAS_POR_HUECO + 1)
    signos = set()
    for i in range(MUESTRAS_POR_HUECO):
        p = izquierda + paso * (i + 1)
        valor = mx.evaluate(f, {var: float(p) * 3.141592653589793})
        if valor is None or abs(valor.imag) > 1e-9:
            continue
        # the SIGN, not the value: two different magnitudes are the same sign,
        # and comparing them is what made every chart look inconsistent
        signos.add(0 if abs(valor.real) < 1e-9 else (1 if valor.real > 0 else -1))
    if len(signos) != 1:
        raise sin_refuso(
            f"el signo cambia dentro de ({izquierda}*pi, {derecha}*pi) sin que haya "
            "ningún cero ni singularidad: eso no debería pasar, y no se va a adivinar "
            f"(el valor «{mx.text(f)}» no es continuo, o el motor no ha visto todos "
            "sus ceros)")
    return next(iter(signos))


def _extremo_entra(f: mx.Expr, var: str, coeficiente: float, periodo: Fraction,
                   ceros_p: set[D.Punto], polos_p: set[D.Punto],
                   operador: str) -> bool:
    """Whether the endpoint at ``coeficiente * pi`` belongs to the solution.

    The endpoint arrives already folded, and it is compared against the critical
    points BY VALUE: the sets hold points that may be ``arcsen(1/3)``, and a
    membership test that went by coefficient would never match one. ``0`` and the
    end of the period are the same point, which is the rule this whole function is
    built on.
    """
    # The endpoint folds BEFORE the comparison. `_modulo` already folded the sets,
    # so comparing an unfolded endpoint against them misses the zero at the end of
    # the period — and then the value decides, and at `pi` tan(x) is 1e-16, which
    # passes `< 0`. That is how `tg(x) < 0` came out with `pi` inside it.
    punto = _punto_de_valor(coeficiente)
    # The endpoint folds FIRST: `periodo` and `0` are the same point, and that is
    # the rule this function is built on. Without the fold, `2·pi` is compared
    # against a grid of `[0, periodo)` and never matches, so the decision falls to
    # the sampled value — where `sen(2·pi)` is -1.2e-16 and passes any `< 0`, which
    # is how `tg(x) < 0` came out with `pi` inside it.
    v = float(coeficiente) % float(periodo)
    punto = _punto_de_valor(v)
    for p in polos_p:
        if abs(_en_un_periodo(p, periodo) - v) < 1e-9:
            return False        # a pole is never in the solution set
    for p in ceros_p:
        if abs(_en_un_periodo(p, periodo) - v) < 1e-9:
            return operador.endswith("=")
    valor = mx.evaluate(f, {var: float(coeficiente) * 3.141592653589793})
    if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > 1e12:
        return False
    return _cumple(valor.real, operador)


def _modulo(puntos: set[D.Punto], periodo: Fraction) -> set[D.Punto]:
    """The same points, folded into ``[0, periodo)``: 0 and the period are one."""
    return {D.punto_pi(p.coeficiente % periodo) for p in puntos}


def _cumple(signo: float, operador: str) -> bool:
    if operador in (">", ">="):
        return signo > 0
    if operador in ("<", "<="):
        return signo < 0
    return abs(signo) < 1e-9


# ---------------------------------------------------------------------------
# T-13, the other half: where the expression exists at all
# ---------------------------------------------------------------------------

#: what each function needs of its argument, as conditions on ``u`` itself.
#: ``None`` means «no restriction». The poles of ``tan`` are not here on purpose:
#: they are zeros of ``cos``, which come from the equation solver, and writing them
#: in a table here would be the same table twice with two chances to disagree.
RESTRICCIONES: dict[str, tuple[tuple[str, object], ...]] = {
    "ln": ((">", 0),),
    "log10": ((">", 0),),
    "log": ((">", 0), (">", 1)),
    "asin": ((">=", -1), ("<=", 1)),
    "acos": ((">=", -1), ("<=", 1)),
    "atanh": ((">", -1), ("<", 1)),
    "acosh": ((">=", 1),),
    "sqrt": ((">=", 0),),
}

#: where these live nowhere but on the whole real line
SIN_RESTRICCION = frozenset({"sin", "cos", "tan", "cot", "sec", "csc",
                             "asin", "acos", "atan", "sinh", "cosh", "tanh",
                             "coth", "sech", "csch", "asinh", "atan", "abs"})


def dominio(e: mx.Expr, var: str = "x") -> D.Conjunto:
    """Where ``e`` exists, as an exact set of intervals (T-13).

    Three things have to be taken out, and taking out only one of them is the
    usual mistake:

    1. the zeros of its denominators;
    2. the poles the functions bring with them — ``tan(x)`` has one at ``pi/2``
       with no denominator anywhere in the expression;
    3. what each function needs of its argument — ``ln(u)`` needs ``u > 0``,
       ``asin(u)`` needs ``|u| <= 1``, ``atanh(u)`` needs ``|u| < 1`` and ``acosh(u)``
       needs ``u >= 1``.

    The third group is resolved with the very same sign chart that solves an
    inequality, which is not an economy: the condition ``u > 0`` *is* an inequality,
    and answering it with a different method would be answering it twice.
    """
    if not mx.depends(e, var):
        return D.Conjunto() if mx.evaluate(e) is None else D.REALES
    # TRIED AND REVERTED: normalising the reciprocals here, so that `csc(x)` and
    # `1/sin(x)` take the same branch, broke ten tests in three files. It is the
    # right idea and the wrong place — the poles branch and the denominators
    # branch need to AGREE, not one of them to disappear. The inconsistency is
    # real (`csc(x)` publishes fewer holes than `1/sin(x)` for one function) and
    # it stays declared rather than half-fixed.
    resultado = D.REALES

    for denominador in D.denominadores(e):
        ceros_del = ceros(denominador, var)
        if ceros_del is not None:
            puntos = [p for p in (_a_punto(c) for c in ceros_del) if p is not None]
        else:
            # «1/(x^2 - 1)» is a denominator with no pi in it, so it is a finite
            # set of ordinary points and not a chart of multiples of pi
            puntos = ceros_en_puntos(denominador, var) or []
        if ceros_del is None and puntos == []:
            raise sin_refuso(
                f"no se saben los ceros de «{mx.text(denominador)}», que es "
                "denominador: sin ellos no se sabe dónde deja de existir la "
                "expresión (§5.4)")
        if puntos:
            # `ceros` returns ONE period, and the period's own end is the same
            # point as its start — the rule the sign chart already follows. Here
            # that omission leaked: the denominator `tg(x)` reports its zero at 0
            # and not at `pi`, so `sen(x)/tg(x)` kept `pi` in its domain and
            # published it as a zero where the expression is `0/0`. The domain
            # reports over all of R with a finite list of holes, so the holes
            # have to include the turn the period closes on.
            per = D.periodo_minimo(denominador, var)
            if per:
                extra = [D.punto_pi(per) for c in puntos
                         if c.coeficiente == 0 or c.coeficiente % per == 0]
                puntos = puntos + [q for q in extra
                                   if all(q.coeficiente != r.coeficiente
                                          for r in puntos)]
            resultado = D.quita_puntos(resultado, tuple(puntos))
            if resultado.vacio:
                return resultado

    for llamada in _llamadas(e):
        nombre, argumentos = llamada.name, llamada.args
        if not argumentos:
            continue
        if nombre in ("tan", "sec"):
            resultado = _sin_polos(resultado, _fn("cos", argumentos[0]), var)
        elif nombre in ("cot", "csc"):
            resultado = _sin_polos(resultado, _fn("sin", argumentos[0]), var)
        for operador, cota in RESTRICCIONES.get(nombre, ()):
            if nombre == "log" and operador == ">" and cota == 1:
                continue          # the second argument is the base, not an input
            resultado = _con_condicion(resultado, argumentos[0], operador, cota,
                                       var)
        if resultado.vacio:
            return resultado
    return resultado


def _sin_polos(conjunto: D.Conjunto, funcion: mx.Expr, var: str) -> D.Conjunto:
    """The set with the zeros of ``funcion`` taken out."""
    ceros_del = ceros(funcion, var)
    if ceros_del is None:
        raise sin_refuso(
            f"no se sabe dónde se anula «{mx.text(funcion)}», así que el dominio "
            "no se puede acotar (§5.4)")
    puntos = [p for p in (_a_punto(c) for c in ceros_del) if p is not None]
    return D.quita_puntos(conjunto, tuple(puntos)) if puntos else conjunto


def _con_condicion(conjunto: D.Conjunto, argumento: mx.Expr, operador: str,
                   cota: object, var: str) -> D.Conjunto:
    """Intersect with ``argumento REL cota``.

    Two paths, and which one applies is not a detail: a condition on a periodic
    argument is a sign chart, and a condition on a non-periodic one is not a sign
    chart at all — there is no period to repeat and no lattice of multiples of
    ``pi`` to lay the answer on. ``asin(x)`` needs ``x >= -1``, whose answer is
    ``[-1, inf)`` and has nothing to do with quadrants.
    """
    cota_texto = "0" if cota == 0 else str(cota)
    texto_condicion = f"{mx.text(argumento)} {operador} {cota_texto}"
    diferencia = mx.Sub(argumento, mx.Num(cota) if cota != 0 else mx.ZERO)
    # Which chart applies is decided by periodicity itself, not by whether the
    # zeros happen to be known: «no lo sé» is not «no es periódica», and reading
    # it as such sent every aperiodic condition down the periodic path to be
    # refused there.
    periodica = D.periodo_minimo(diferencia, var) is not None
    try:
        if periodica:
            solucion = resolver_inequidad(texto_condicion, var)
            return conjunto.interseccion(solucion.conjunto)
        carta = _carta_aperiodica(diferencia, var, operador)
        if carta is None:
            raise sin_refuso(
                f"los ceros de «{mx.text(diferencia)}» no son un conjunto finito "
                "de puntos exactos, así que la condición no se puede acotar (§5.4)")
        return conjunto.interseccion(carta)
    except UnsupportedError as exc:
        raise sin_refuso(
            f"el dominio necesita resolver «{texto_condicion}», que es lo que "
            f"pide «{operador} {cota_texto}» sobre el argumento, y no se sabe: "
            f"{exc}") from exc


def ceros_en_puntos(e: mx.Expr, var: str = "x") -> list[D.Punto] | None:
    """Zeros of ``e`` as exact points on the line, when they are finitely many.

    Only polynomials in the variable itself qualify. A trigonometric zero is a
    multiple of ``pi`` and there are infinitely many of those, so they cannot be
    sorted into a line of intervals the way a single root can — that is the whole
    difference between the aperiodic chart and the periodic one.

    ``None`` means «not a finite exact set»: not because the expression has no
    zeros, but because this engine cannot name all of them.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    if not mx.depends(e, var):
        return None
    if _llamadas(e):
        return None                      # a trig function: infinitely many zeros
    q = P.as_poly(e)
    if q is None or P.atoms_of(q) or P.real_variables(q) - {var}:
        return None
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    raices, _ = E._raices_reales(q, mx.Sym(var))
    puntos: list[D.Punto] = []
    for raiz in raices:
        valor = mx.exact_value(raiz)
        if valor is None:
            return None                  # irrational or not exactly representable
        puntos.append(D.punto(valor))
    return sorted(set(puntos), key=lambda p: p.coeficiente)


def _carta_aperiodica(e: mx.Expr, var: str, operador: str) -> D.Conjunto | None:
    """``e REL 0`` when ``e`` has finitely many zeros, as intervals on the line.

    The same argument as the periodic chart: between two consecutive zeros a
    continuous function cannot change sign, so one sample per gap settles it. What
    is different is the ends — there is no period to fold them onto, so the outer
    intervals reach to infinity and are signed by a sample of their own.

    Each gap is sampled *inside itself*. Sampling the leftmost gap at the right
    one's midpoint was wrong in a way that only showed on the unbounded gaps,
    where the midpoint does not exist: the sample landed in the neighbouring gap
    and the answer came out empty.
    """
    puntos = ceros_en_puntos(e, var)
    if puntos is None or not puntos:
        return None
    if D.denominadores(e):
        raise sin_refuso(
            "una expresión con denominador no se acota por carta aperiodica: "
            "habría que quitar antes sus polos (§5.4)")
    cierra = operador.endswith("=")
    coeficientes = [p.coeficiente for p in puntos]
    piezas: list[D.Intervalo] = []
    for indice, izquierda in enumerate([None] + coeficientes):
        derecha = coeficientes[indice] if indice < len(coeficientes) else None
        if izquierda is not None and derecha is not None \
                and izquierda == derecha:
            continue
        if izquierda is None:
            muestra = derecha - 1
        elif derecha is None:
            muestra = izquierda + 1
        else:
            muestra = (izquierda + derecha) / 2
        valor = mx.evaluate(e, {var: float(muestra)})
        if valor is None or abs(valor.imag) > 1e-9:
            continue
        if not _cumple(valor.real, operador):
            continue
        izq = None if izquierda is None else D.punto(izquierda)
        der = None if derecha is None else D.punto(derecha)
        # an unbounded end is open: printing «(0, ∞]» claims a point at infinity
        piezas.append(D.Intervalo(izq, der,
                                  izq is None or not cierra,
                                  der is None or not cierra))
    if not piezas:
        return D.Conjunto()
    return D.desde_intervalos(piezas)


def _separa(texto: str) -> tuple[str, str, str]:
    """Split on the comparison operator, longest match first."""
    for operador in (">=", "<=", "=", ">", "<"):
        if operador in texto:
            izquierda, _, derecha = texto.partition(operador)
            if not izquierda.strip() or not derecha.strip():
                raise sin_refuso(f"uno de los dos lados de «{operador}» está vacío")
            return operador, izquierda.strip(), derecha.strip()
    raise sin_refuso(
        "falta el signo de comparación: la desigualdad tiene que venir como "
        "«sen(x) > 1/2» (admitidos >, <, >=, <= y =)")


def _parse(texto: str, var: str) -> mx.Expr:
    try:
        return mx.parse(texto)
    except Exception as exc:
        raise sin_refuso(f"no se pudo interpretar «{texto}»: {exc}") from exc


def _metodo() -> tuple[str, ...]:
    return (
        "se recorre un solo periodo y se repite: la solución es periódica y "
        "enumerarla sería infinito (§5.5b)",
        "el signo en cada hueco se decide numéricamente, lo cual es una prueba y "
        "no una aproximación: una función continua sin ceros ni polos en un hueco "
        "no puede cambiar de signo dentro de él",
    )
