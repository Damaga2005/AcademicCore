# SPDX-License-Identifier: MIT
"""MATH_LAB T-12: solving trigonometric equations.

What this solves, and what it refuses
-------------------------------------

An equation is moved to one side (``f(x) − g(x) = 0``) and matched structurally.
The cases are the ones a technical course actually asks for:

- ``sin(u) = c``, ``cos(u) = c``, ``tan(u) = c``;
- ``a·sin(u) + b·cos(u) = c``, which is brought to a single sine by a phase
  shift — §5.5b, because it is the only form that integrates as well;
- a polynomial in ``sin(u)``, ``cos(u)`` or ``tan(u)``, whose exact roots are
  found first and then fed back into the cases above.

Anything else is **refused with a reason in Spanish** rather than guessed. That
is §5.4, and for this family it is not politeness: a solver that answers
``x = 0`` for something it does not understand is worse than one that says no.

Spurious solutions
------------------

Every family is checked by substitution into the *original* equation, which is
what T-12 asks for and the only thing that catches a root introduced by a
transformation. The rejected candidates are reported by name, not dropped: a
spurious solution that vanishes without explanation is the thing that teaches a
student to distrust the whole method.

Exactness
---------

``arcsin(1/3)`` is an exact real number, so ``x = arcsin(1/3) + 2k·pi`` is an
exact answer even though it is not a multiple of ``pi``. Only the notable angles
are rewritten in multiples of ``pi``. Where a polynomial has no exact root the
refusal says so and offers the numeric value with its error bound (§5.4).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab import trig
from academic_core.errors import UnsupportedError

#: how many members of a family are substituted back to check it
MIEMBROS_COMPROBADOS = 5

#: how close to zero a substituted value has to land, relative to its size
TOLERANCIA = 1e-9


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# what a solution looks like
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Familia:
    """One family of solutions: ``variable = base + paso·k``, ``k ∈ ℤ``."""

    base: mx.Expr
    paso: mx.Expr
    metodo: str = ""
    hipotesis: str = ""
    #: Whether ``base`` is a value of ``x`` or of the substitution variable.
    #: A family left in ``u`` —«sen(sen(x)) = 0», donde no hay cambio de variable
    #: que deshacer— reads as a value of ``x`` unless something says otherwise,
    #: and a caller that places it en la rejilla de pi publica un cero que
    #: pertenece a otra variable.
    en_x: bool = True

    @property
    def es_punto_unico(self) -> bool:
        """Whether this is ONE solution rather than a family.

        A step of zero says exactly that: ``x = 0 + 0·k`` is ``x = 0`` for
        every ``k``. Written as a family it would print ``x = 0 + 0·k`` and
        read as «x is anything»; written as a single value it says what it is.
        """
        return mx.exact_value(self.paso) == 0

    def texto(self, var: str) -> str:
        if self.es_punto_unico:
            return f"{var} = {mx.pretty(self.base)}"
        paso = "" if mx.text(self.paso) == "1" else f" + {mx.pretty(self.paso)}·k"
        return f"{var} = {mx.pretty(self.base)}{paso},  k ∈ ℤ"

    def miembro(self, k: int, var: str) -> mx.Expr:
        return mx.Add(self.base, mx.Mul(mx.Num(Fraction(k)), self.paso))


@dataclass(frozen=True)
class Resolucion:
    """The families found, how, and what was thrown away on the way."""

    familias: tuple[Familia, ...]
    metodo: str = ""
    hipotesis: tuple[str, ...] = ()
    espurias: tuple[str, ...] = ()
    refusos: tuple[str, ...] = ()

    def texto(self, var: str) -> str:
        if self.refusos:
            return "no se resuelve todavía: " + self.refusos[0]
        if not self.familias:
            return "no hay soluciones"
        return "   ó   ".join(f.texto(var) for f in self.familias)

    @property
    def vacia(self) -> bool:
        return not self.familias

    @property
    def sin_respuesta(self) -> bool:
        """True when the engine declined, as opposed to having found nothing."""
        return bool(self.refusos) and not self.familias


# ---------------------------------------------------------------------------
# exact angles
# ---------------------------------------------------------------------------

def _indice_notable(funcion: str, valor: mx.Expr) -> Fraction | None:
    """``k`` such that ``funcion(k*pi) == valor``, or ``None``.

    Read out of the same table the simplifier uses, so the solver and the
    simplifier cannot disagree about what ``sin(pi/6)`` is.

    Two comparisons, in that order. Exact first, through ``exact_value``, which
    settles every rational. Then, for an exact **surd** such as ``sqrt(2)/2``, a
    numeric one — but only ever against a value built from roots, never a
    decimal. That restriction is the point: it is what turns
    ``arcsin(sqrt(2)/2)`` into ``pi/4`` exactly, without ever letting the engine
    decide that some decimal is close enough to a notable angle.
    """
    for k, valores in trig._NOTABLES.items():
        exacto = valores.get(funcion)
        if exacto is None:
            continue
        a, b = mx.exact_value(exacto), mx.exact_value(valor)
        # both sides must be *known*: two Nones compare equal, and that made every
        # surd look like the first notable angle in the table
        if a is not None and b is not None and a == b:
            return k
    if not _es_exacta(valor):
        return None
    objetivo = mx.evaluate(valor)
    for k, valores in trig._NOTABLES.items():
        exacto = valores.get(funcion)
        if exacto is None or not _es_exacta(exacto):
            continue
        lado = mx.evaluate(exacto)
        if (lado is not None and objetivo is not None
                and abs(lado.imag) < 1e-12 and abs(objetivo.imag) < 1e-12
                and abs(lado.real - objetivo.real) < 1e-12):
            return k
    return None


def _es_negativo(e: mx.Expr) -> bool:
    valor = mx.evaluate(e)
    return valor is not None and valor.imag == 0 and valor.real < 0


def _es_exacta(e: mx.Expr) -> bool:
    """True when ``e`` is an exact surd: numbers and roots only, never decimals."""
    if isinstance(e, mx.Num):
        return True
    if isinstance(e, mx.Root):
        return _es_exacta(e.radicand)
    if isinstance(e, mx.Neg):
        return _es_exacta(e.arg)
    if isinstance(e, mx.Pow):
        return _es_exacta(e.base)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _es_exacta(e.left) and _es_exacta(e.right)
    if isinstance(e, mx.Const):
        return e.name == "pi"
    if isinstance(e, mx.Call):
        return e.name == "sqrt" and len(e.args) == 1 and _es_exacta(e.args[0])
    return False


#: which inverse each family needs, by the name the expression uses
_ARC = {"sin": "asin", "cos": "acos", "tan": "atan"}


def _inversa(funcion: str, valor) -> tuple[mx.Expr, bool, str]:
    """``arcsin`` / ``arccos`` / ``arctan`` of an exact value.

    ``(angulo, es_multiplo_de_pi, nota)``. A value that is not notable is *not* a
    problem: ``arcsin(1/3)`` and ``arcsin(1/sqrt(2))`` are exact real numbers, so
    the answer stays exact and is written symbolically instead of as a decimal.
    """
    expresion = valor if isinstance(valor, mx.Expr) else mx.Num(valor)
    k = _indice_notable(funcion, expresion)
    if k is not None:
        return D.punto_pi(k).expr(), True, ""
    # the table only holds angles in [0, pi], where every sine is >= 0; a negative
    # value is the same angle reflected, so it is looked up by its modulus
    if _es_negativo(expresion):
        k_negativo = _indice_notable(funcion, mx.Neg(expresion))
        if k_negativo is not None:
            return mx.Neg(D.punto_pi(k_negativo).expr()), True, ""
    if mx.exact_value(expresion) is not None:
        nota = (f"{funcion}({mx.text(expresion)}) no es un ángulo notable: se deja "
                "como expresión exacta y no como decimal (§5.4)")
    else:
        nota = (f"{funcion}({mx.text(expresion)}) no es racional, pero su inversa "
                "sigue siendo exacta: por eso la solución es exacta aunque no "
                "sea múltiplo de pi")
    return mx.Call(_ARC[funcion], (expresion,)), False, nota


def _arcoseno_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("sin", c)
    return angulo, multiplo


def _arccoseno_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("cos", c)
    return angulo, multiplo


def _arctangente_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("tan", c)
    return angulo, multiplo


def _dos_pi() -> mx.Expr:
    return mx.Mul(mx.Num(Fraction(2)), mx.PI)


def _pi() -> mx.Expr:
    return mx.PI


# ---------------------------------------------------------------------------
# the solver
# ---------------------------------------------------------------------------


def _aviso_de_completitud(f: mx.Expr, familias, var: str) -> str | None:
    """A sentence when the families miss a root that a numeric scan finds.

    Each case answers the equations of its shape, and an equation of a mixed shape
    can be answered only in part: ``cos(x)/2 + 2·tg(2x) = -1/2`` published
    ``x = pi + 2k·pi`` alone and nothing said the list stopped there (found
    2026-10-05). One period is scanned; every root found there must be a member of
    some family, and the ones that are not are named with their approximate value,
    because «faltan soluciones» without saying where is not much of an answer.
    """
    from academic_core.domain.engineering.mathlab import continuidad as K

    periodo = D.periodo_minimo(f, var)
    if periodo is None:
        return None
    longitud = float(periodo) * 3.141592653589793
    raices = K.ceros_numericos(f, var, 0.0, longitud)
    valores = []
    for familia in familias:
        base = mx.valor_real(familia.miembro(0, var), {})
        siguiente = mx.valor_real(familia.miembro(1, var), {})
        if base is None or siguiente is None:
            return None        # a family that cannot be evaluated: no claim either way
        valores.append((base, siguiente - base))
    faltan = K.no_cubiertos(raices, valores)
    if not faltan:
        return None
    lista = ", ".join(f"x ≈ {r:.6g}" for r in faltan[:8])
    return ("la lista de soluciones está INCOMPLETA: en un periodo, [0, "
            f"{longitud:.6g}), hay soluciones que ninguna familia exacta cubre "
            f"({lista}); se dan como aproximaciones numéricas, y se repiten con el "
            "periodo")


def separar(ecuacion: str) -> tuple[str, str]:
    """``"sin(x) = 1/2"`` → ``("sin(x)", "1/2")``."""
    if "=" not in ecuacion:
        raise sin_refuso(
            "falta el signo «=»: la ecuación tiene que venir con los dos lados, "
            "por ejemplo «sin(x) = 1/2»")
    izquierda, _, derecha = ecuacion.partition("=")
    if not izquierda.strip() or not derecha.strip():
        raise sin_refuso("uno de los dos lados de la ecuación está vacío")
    return izquierda.strip(), derecha.strip()


def resolver(ecuacion: str, var: str = "x") -> Resolucion:
    """Solve a trigonometric equation and return every solution family."""
    izquierda, derecha = separar(ecuacion)
    try:
        a, b = mx.parse(izquierda), mx.parse(derecha)
    except Exception as exc:  # a parse error already says where, in Spanish
        raise sin_refuso(f"no se pudo interpretar la ecuación: {exc}") from exc
    if sorted(mx.variables(a) | mx.variables(b)) not in ([], [var]):
        otras = sorted((mx.variables(a) | mx.variables(b)) - {var})
        raise sin_refuso(
            f"la ecuación tiene más de una incógnita ({', '.join(otras)}): "
            f"ahora mismo solo se resuelve con una, la «{var}»")
    original = mx.Sub(a, b)
    familias, hipotesis, espurias = _casos(original, var)
    if not familias:
        # The expansion PRESERVES THE VALUE, so it cannot answer a different
        # equation — and that is why the ORIGINAL goes first and its answer is the
        # one published. `cos(2x) = 0` already had a clean answer of two families,
        # and expanding first would replace it with four that describe the same set
        # less clearly. The expansion is for the equations with no answer at all,
        # which is where it was missing.
        diferencia = _desarrolla_angulos_multiples(original, var)
        if diferencia != original:
            familias, hipotesis, espurias = _casos(diferencia, var)
    # A family that fails the ORIGINAL equation is not a solution, whatever case
    # produced it. Each case reported such families in `espurias` and published
    # them anyway, so `cos(x - pi/4)**2 = 1` printed two families that do not
    # satisfy it next to a note saying so. They are removed here, once, for every
    # case — and if nothing is left the answer is «not solved», never «no
    # solutions», because a wrong case is not evidence that there are none.
    validas, descartadas = [], []
    for familia in familias:
        if _comprobar([familia], original, var):
            descartadas.append(familia)
        else:
            validas.append(familia)
    if descartadas:
        espurias = list(espurias) + [
            f"{familia.texto(var)} no satisface la ecuación original y se descarta"
            for familia in descartadas]
        hipotesis = list(hipotesis) + [
            "se descartaron familias que no cumplen la ecuación original; las que "
            "quedan sí la cumplen, pero la lista puede estar incompleta"]
        if not validas:
            hipotesis.append(MOTIVO_SIN_CASO)
    familias = validas
    aviso = _aviso_de_completitud(original, familias, var)
    if aviso:
        hipotesis = list(hipotesis) + [aviso]
    refusos = tuple(h for h in hipotesis if MOTIVO_SIN_CASO in h)
    return Resolucion(tuple(familias), hipotesis=tuple(h for h in hipotesis
                                                       if h not in refusos),
                      espurias=tuple(espurias), refusos=refusos)


def _casos(f: mx.Expr, var: str):
    """The case analysis, in the order that avoids dividing by something."""
    # «f(x) = 0» arrives as «f(x) - 0», and that trailing zero hides the single
    # subtraction the cases rest on. Taken off HERE rather than inside the first
    # case: every case needs it, and a case that does not know about it refuses
    # an equation it could solve — which is how «x = 0» ended up unresolved.
    while isinstance(f, mx.Sub) and f.right == mx.ZERO and isinstance(f.left, mx.Sub):
        f = f.left
    directo = _caso_directo(f, var)
    if directo is not None:
        return directo
    fase = _caso_fase(f, var)
    if fase is not None:
        return fase
    racional = _caso_racional(f, var)
    if racional is not None:
        return racional
    polinomio = _caso_polinomio(f, var)
    if polinomio is not None:
        return polinomio
    lineal = _caso_lineal(f, var)
    if lineal is not None:
        return lineal
    producto = _caso_producto(f, var)
    if producto is not None:
        return producto
    tangente = _caso_tangente(f, var)
    if tangente is not None:
        return tangente
    universal = _caso_sustitucion_universal(
        _desarrolla_angulos_multiples(f, var), var)
    if universal is not None:
        return universal
    cuadrado = _cuadrado_elimina_una_funcion(
        _desarrolla_angulos_multiples(f, var), var)
    if cuadrado is not None:
        return cuadrado
    # No case matched. That is *not* the same as «there is no solution»: it is
    # «this engine does not solve this», and the difference is the whole point of
    # §5.4. Saying «no solutions» here would be a false answer presented with
    # the same confidence as a solved one.
    return [], [MOTIVO_SIN_CASO], []


# --- case 5: a·x + b = c ------------------------------------------------------


def _caso_lineal(f: mx.Expr, var: str):
    """``a·var + b = c``, and the two constant cases around it.

    The most elementary equation there is, and it was missing. That is not a
    cosmetic gap: ``ceros`` asks the solver for the zeros of a denominator, gets
    «I don't solve this one», and then has to keep a point that does not exist —
    ``sen(x)/x`` published a zero at 0 because ``x = 0`` was out of reach. The
    quotient filter asks the DOMAIN now, which is the right dependency, and this
    case closes the equation for its own sake.

    Three outcomes and they are not interchangeable:

    * ``a ≠ 0``: one solution, ``x = (c - b)/a``, as a family of step 0;
    * ``a = 0`` and ``b = c``: every ``x``, which is not a family and is refused;
    * ``a = 0`` and ``b ≠ c``: NO solution, and that one is said as such —
      a contradiction is the one case where «no hay soluciones» is the answer.
    """
    if not isinstance(f, mx.Sub):
        return None
    izquierda, derecha = f.left, f.right
    cte = _valor_exacto(derecha)
    if cte is None:
        izquierda, derecha = derecha, izquierda
        cte = _valor_exacto(izquierda)
    if cte is None:
        return None
    a, b = _afine(izquierda, var)
    if a is None or a == 0:
        # The left side is not a constant, it is something this case cannot
        # handle — x^2, sin(x), 1/x. Calling that «una constante» produced
        # «x^2 = 0 no tiene soluciones», which is a false answer with the same
        # confidence as a solved one: x = 0 IS a solution.
        if mx.variables(izquierda):
            return None
        if mx.exact_value(izquierda) == mx.exact_value(derecha):
            return None              # every x solves it: not a family, refused
        return ([], ["una constante distinta de otra no tiene soluciones: el "
                     "miembro izquierdo no depende de x y no puede igualar al "
                     "derecho"], [])
    base = _simplifica_base(_divide_por_constante(
        _simplifica_base(mx.Sub(derecha, b)) if b != mx.ZERO
        else _simplifica_base(derecha), a))
    metodo = (f"a·{var} + b = c con a = {_frac(a)} y b = {mx.text(b)}: "
              f"la ecuación lineal se deshace en una sola solución, "
              f"x = (c - b)/a")
    familia = Familia(base, mx.ZERO, metodo,
                      "una solución aislada, no una familia: el paso es 0 y no "
                      "hay ningún k que la mueva")
    espurias = _comprobar([familia], f, var)
    return [familia], [f"la ecuación es lineal y tiene una única solución"], espurias


def _frac(a: Fraction) -> str:
    return str(a)


#: the refusal that replaces a wrong «no hay soluciones»
MOTIVO_SIN_CASO = (
    "ninguno de los casos de T-12 encaja aquí (sin/cos/tangente igual a una "
    "constante, a·sin+b·cos, o un polinomio en una de las tres). Eso NO quiere "
    "decir que no haya soluciones: quiere decir que este motor todavía no lo "
    "resuelve, y no va a devolver una respuesta inventada (§5.4)")


# --- case 1: sin(u) = c, cos(u) = c, tan(u) = c -----------------------------


#: How far a multiple angle is developed. Two is the one that matters and three is
#: free; past that the expression grows faster than the solving improves, which is
#: the trade §5.5b asks to be judged rather than assumed.
MAXIMO_ANGULO_MULTIPLE = 3


def _reconstruir(reescribe, e: mx.Expr) -> mx.Expr:
    """Rebuild ``e`` with the rewrite applied to its children."""
    if isinstance(e, mx.Call):
        args = tuple(reescribe(a) for a in e.args)
        return e if args == e.args else mx.Call(e.name, args)
    if isinstance(e, mx.Pow):
        base = reescribe(e.base)
        return e if base == e.base else mx.Pow(base, e.exponent)
    if isinstance(e, mx.Neg):
        return mx.Neg(reescribe(e.arg))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        izquierda, derecha = reescribe(e.left), reescribe(e.right)
        if (izquierda, derecha) == (e.left, e.right):
            return e
        if isinstance(e, mx.Add):
            return mx.Add(izquierda, derecha)
        if isinstance(e, mx.Sub):
            return mx.Sub(izquierda, derecha)
        if isinstance(e, mx.Mul):
            return mx.Mul(izquierda, derecha)
        return mx.Div(izquierda, derecha)
    return e


def _desarrolla_angulos_multiples(f: mx.Expr, var: str) -> mx.Expr:
    """``cos(2x)`` written as ``2cos²(x) - 1``, so the cases below can see it.

    A multiple angle NEXT TO another term is what no case could read. The analysis
    is good at ``a·cos(u) + b = c`` and at polynomials in ONE function, and
    ``cos(x) + cos(2x) = 0`` has neither shape: the second term is a cosine of a
    different argument, and no case was willing to call both of them ``cos``.

    Writing the multiple angle in powers of the same function costs nothing and is
    exact — ``cos(2x) = 2cos²(x) - 1``, ``sen(3x) = -4sen³(x) + 3sen(x)`` — and from
    there the path that already solved ``cos(x)² = 1/2`` solves these. The root
    finder then divides out the rational roots and closes the leftover quadratic,
    which is what turns ``-4u³ + 2u`` into ``0`` and ``±1/√2`` instead of ``0`` alone.

    Only the ARGUMENT of a sine or a cosine with slope ``>= 2`` is touched, and a
    slope of 1 is left alone: that case already worked, and rewriting it would be
    churn with a blast radius. A shift is left alone too, because ``cos(2x + 1)``
    has no such expansion.

    The expansion PRESERVES THE VALUE, so this can never answer a different
    equation. What it can do is answer it in a less clear form, which is why the
    original goes first and this only runs when the original produced nothing.
    """
    from academic_core.domain.engineering.mathlab import trig as T

    def reescribe(e: mx.Expr) -> mx.Expr:
        if isinstance(e, mx.Call) and e.name in ("sin", "cos") and len(e.args) == 1:
            a, b = _afine(e.args[0], var)
            if a is None or abs(a) < 2 or abs(a) > MAXIMO_ANGULO_MULTIPLE \
                    or b != mx.ZERO:
                return _reconstruir(reescribe, e)
            try:
                developed = T.multiple_angle(e.name, mx.Sym(var), int(abs(a)))
            except Exception:              # noqa: BLE001 — sin desarrollar, mejor
                return _reconstruir(reescribe, e)
            return mx.Neg(developed) if a < 0 else developed
        return _reconstruir(reescribe, e)

    return reescribe(f)


def _caso_directo(f: mx.Expr, var: str):
    """``sin(u) − c``, ``cos(u) − c`` and ``tan(u) − c``, with ``u`` affine in x."""
    if not isinstance(f, mx.Sub):
        return None
    cociente, resto = f.left, f.right
    # the right-hand side may be a rational *or* an exact surd: sin(x) = sqrt(2)/2
    # is a perfectly ordinary exercise, and refusing it because the value is
    # irrational would be refusing to be exact
    cte = _valor_exacto(resto)
    if cte is None:
        cociente, cte = resto, _valor_exacto(cociente)
    if cte is None:
        return _caso_directo_escalado(f, var)
    nombre, u = _una_trig(cociente)
    if u is None:
        return _caso_directo_escalado(f, var)
    if nombre == "sin":
        familias, hipotesis = _soluciones_seno(cte, u, var)
    elif nombre == "cos":
        familias, hipotesis = _soluciones_coseno(cte, u, var)
    else:
        familias, hipotesis = _soluciones_tangente(cte, u, var)
    if not familias:
        return None
    espurias = _comprobar(familias, f, var)
    return familias, hipotesis, espurias


def _caso_directo_escalado(f: mx.Expr, var: str):
    """``a·sin(u) + b = c`` with exact constants: the direct case after dividing.

    ``2·cos(x) = -sqrt(3)`` was refused as «ningún caso encaja» while
    ``cos(x) = -sqrt(3)/2`` was solved: the direct case only accepted the bare
    function, and the polynomial case reads ``sqrt(3)`` as an atom it cannot hold.
    (Found 2026-10-05 generating equations at random.) Only ONE term may contain
    the variable, and it must be a constant times one ``sin``/``cos``/``tan`` —
    anything else is a different case and goes to it.
    """
    from academic_core.domain.engineering.mathlab import trig as T

    con_variable, constantes = [], []
    for signo, termino in _sumandos(f):
        (con_variable if var in mx.variables(termino) else constantes).append(
            (signo, termino))
    if len(con_variable) != 1:
        return None
    signo, termino = con_variable[0]
    factor: mx.Expr = mx.Num(signo)
    while True:
        if isinstance(termino, mx.Neg):
            factor, termino = mx.Neg(factor), termino.arg
        elif isinstance(termino, mx.Mul) and var not in mx.variables(termino.left):
            factor, termino = mx.Mul(factor, termino.left), termino.right
        elif isinstance(termino, mx.Mul) and var not in mx.variables(termino.right):
            factor, termino = mx.Mul(factor, termino.right), termino.left
        elif isinstance(termino, mx.Div) and var not in mx.variables(termino.right):
            factor, termino = mx.Div(factor, termino.right), termino.left
        else:
            break
    nombre, u = _una_trig(termino)
    if u is None:
        return None
    suma = mx.ZERO
    for s_, t_ in constantes:
        suma = mx.Add(suma, t_) if s_ > 0 else mx.Sub(suma, t_)
    if mx.valor_real(factor, {}) in (None, 0.0):
        return None
    despejada = mx.Div(mx.Neg(suma), factor)
    try:
        # the ring normal form folds «-(0 - sqrt(2)/2)/2» into «1/4*sqrt(2)», so
        # the answer reads arccos(√2/4) and not arccos(-(0 - √2/2)/2)
        despejada = P.to_expr(P.as_poly(despejada))
    except Exception:  # noqa: BLE001 - the unfolded form is still exact
        pass
    cte = _valor_exacto(T.simplify(despejada))
    if cte is None:
        return None
    if nombre == "sin":
        familias, hipotesis = _soluciones_seno(cte, u, var)
    elif nombre == "cos":
        familias, hipotesis = _soluciones_coseno(cte, u, var)
    else:
        familias, hipotesis = _soluciones_tangente(cte, u, var)
    hipotesis = [f"se despeja {nombre}({mx.text(u)}) dividiendo entre "
                 f"{mx.text(T.simplify(factor))}"] + list(hipotesis)
    if not familias:
        # out of range is a real answer («no hay solución») and travels as one
        return [], hipotesis, []
    return familias, hipotesis, _comprobar(familias, f, var)


def _valor_exacto(e: mx.Expr):
    """The exact value of ``e``: a ``Fraction``, an exact surd as an expression,
    or ``None`` when it is neither."""
    racional = _constante(e)
    if racional is not None:
        return racional
    return e if _es_exacta(e) else None


def _constante(e: mx.Expr) -> Fraction | None:
    """The exact rational value of ``e``, or ``None`` when it is not one.

    ``mx.exact_value`` is the authority on what is exactly a rational, so the
    solver and the simplifier cannot disagree about ``1/2`` or about ``pi``.
    """
    valor = mx.exact_value(e)
    return valor if valor is not None else None


def _una_trig(e: mx.Expr) -> tuple[str, mx.Expr] | tuple[None, None]:
    if isinstance(e, mx.Call) and e.name in {"sin", "cos", "tan"} and len(e.args) == 1:
        return e.name, e.args[0]
    return None, None


def _invertir(u: mx.Expr, base: mx.Expr, paso: mx.Expr, var: str
              ) -> tuple[mx.Expr, mx.Expr, str] | None:
    """Turn ``u = base + paso·k`` into ``x = ...``, when ``u`` is affine in x.

    ``u = a·x + b`` → ``x = (base − b)/a + (paso/a)·k``. When ``u`` is anything
    else the inversion is simply not available, and that is said instead of
    approximated.
    """
    a, b = _afine(u, var)
    if a is None or a == 0:
        return None
    nuevo_base = _simplifica_base(mx.Sub(base, b) if b != mx.ZERO else base)
    if a != 1:
        nuevo_base = _divide_por_constante(nuevo_base, a)
    nuevo_paso = paso if a == 1 else _divide_por_constante(paso, a)
    return _simplifica_base(nuevo_base), _simplifica_paso(nuevo_paso), ""


def _divide_por_constante(e: mx.Expr, a: Fraction) -> mx.Expr:
    """``2·pi`` over 2 as ``pi``, and ``-pi/2`` over 2 as ``-pi/4``.

    Folding the coefficient instead of writing a quotient is the difference
    between an answer a student recognises and one they have to re-read, and it
    is also what keeps ``1/2·(-1/2·pi)`` from ever appearing.
    """
    if isinstance(e, mx.Neg):
        return mx.Neg(_divide_por_constante(e.arg, a))
    if mx.exact_value(e) == 0:
        # 0 over anything is 0, and writing it as a quotient is how «x/2» came
        # back with a constant term of «0/2» that then leaked into every answer
        # derived from it
        return mx.ZERO
    if isinstance(e, mx.Div) and isinstance(e.right, mx.Num) and e.right.value != 0:
        acumulado = e.right.value * a
        if acumulado.denominator == 1 and acumulado != 0:
            return _divide_por_constante(e.left, acumulado)
    # sqrt(m)/k is sqrt(m/k²): writing it as a quotient leaves sqrt(12)/2 where
    # the student expects sqrt(3)
    if isinstance(e, mx.Div) and isinstance(e.left, mx.Root) \
            and e.left.degree == 2 and isinstance(e.right, mx.Num):
        dentro = mx.exact_value(e.left.radicand)
        if dentro is not None and e.right.value != 0:
            nuevo = Fraction(dentro) / (e.right.value ** 2)
            if nuevo.denominator == 1 and nuevo >= 0:
                return mx.Root(2, mx.Num(nuevo))
    coeficiente, factores = trig._factores(e)
    nuevo = coeficiente / a if a != 0 else coeficiente
    if nuevo == 0:
        # a coefficient of zero must come out as the plain zero: handing it to
        # _desde_factores is what wrote «-0» as the base of a whole family
        return mx.ZERO
    if factores:
        return trig._desde_factores(nuevo, factores)
    # A bare quotient of two rationals is one rational. Writing «-6/3» as the
    # answer to «3x = -6» is not wrong, it is unreadable, and the student has to
    # reduce it by hand to find out the solver got it right.
    racional = mx.exact_value(e)
    return mx.Num(racional / a) if racional is not None else mx.Div(e, mx.Num(a))


def _simplifica_base(e: mx.Expr) -> mx.Expr:
    """``pi − 0·pi`` → ``pi`` and ``pi − pi/6`` → ``5·pi/6``: the answer must read well."""
    if isinstance(e, mx.Sub) and e.left == e.right:
        # «sin(3x + pi/2) = 1» gives pi/2 - pi/2, and the factor reader turns
        # that into a negative zero that then travels through the whole answer
        return mx.ZERO
    # Recurse into children first. «pi - 0*pi - pi/4» only folds once its own
    # children have folded, and that is not obvious until it has happened once.
    if isinstance(e, mx.Sub):
        e = mx.Sub(_simplifica_base(e.left), _simplifica_base(e.right))
    elif isinstance(e, mx.Neg):
        e = mx.Neg(_simplifica_base(e.arg))
    coeficiente, factores = trig._factores(e)
    if coeficiente == 0:
        return mx.ZERO
    if isinstance(e, mx.Sub):
        izquierda, derecha = e.left, e.right
        # the sign is read through _terminos, not _factores: a negative angle is
        # written «Neg(...)», and _factores does not look inside one, so
        # «pi - -pi/4» came back unfolded and the chart lost a critical point
        t1, t2 = trig._terminos(izquierda), trig._terminos(derecha)
        if len(t1) == 1 and len(t2) == 1:
            s1, n1 = t1[0]
            s2, n2 = t2[0]
            c1 = trig._multiplo_de_pi(n1)
            c2 = trig._multiplo_de_pi(n2)
            if c1 is not None and c2 is not None:
                total = s1 * c1 - s2 * c2
                if total == 0:
                    return mx.ZERO
                return mx.PI if total == 1 else _medio_pi(total)
        if derecha == mx.ZERO:
            return izquierda
        if izquierda == mx.ZERO:
            return mx.Neg(derecha)
    if coeficiente != 1 and len(factores) == 1:
        return trig._desde_factores(coeficiente, factores)
    return e


def _simplifica_paso(paso: mx.Expr) -> mx.Expr:
    """``2·pi/2`` → ``pi`` and ``1·pi`` → ``pi``: the step reads as the student writes it."""
    coeficiente, factores = trig._factores(paso)
    if factores == [mx.Const("pi")]:
        if coeficiente == 1:
            return mx.PI
        if coeficiente == -1:
            return mx.Neg(mx.PI)
        return mx.Mul(mx.Num(coeficiente), mx.PI)
    return paso


def _sumandos(e: mx.Expr):
    """``(signo, término)`` over the additive tree, so a shift shows up as one.

    ``trig._factores`` splits products and never splits a sum: it hands back
    ``x + pi/3`` as ONE factor, so the constant term was invisible and every
    shifted argument came out as «not affine». Splitting the sum is what turns
    ``x + pi/3`` into ``(1, pi/3)`` and makes ``sen(x + pi/3) = 0`` solvable.
    """
    if isinstance(e, mx.Add):
        yield from _sumandos(e.left)
        yield from _sumandos(e.right)
    elif isinstance(e, mx.Sub):
        yield from _sumandos(e.left)
        for signo, termino in _sumandos(e.right):
            yield -signo, termino
    elif isinstance(e, mx.Neg):
        for signo, termino in _sumandos(e.arg):
            yield -signo, termino
    else:
        yield Fraction(1), e


def _escalar_de_x(termino: mx.Expr, var: str) -> Fraction | None:
    """``a`` when the term is exactly ``a·var``, and ``None`` when it is not.

    ``x^2`` arrives as a ``Pow`` and is not ``a·x``: reading the power as a
    scaling would give ``sen(x^2)`` a frequency of 2. ``1/x`` is a ``Div`` with
    the variable below and is not affine either — inverting ``u = 1/x`` gives
    ``x = 1/u``, which is not ``(base − b)/a`` and has to be refused rather than
    mangled into ``x = base``.
    """
    if termino == mx.Sym(var):
        return Fraction(1)
    if isinstance(termino, mx.Div):
        return None                          # handled by _afine, or not affine
    coeficiente, factores = trig._factores(termino)
    return coeficiente if factores == [mx.Sym(var)] else None


def _afine(e: mx.Expr, var: str) -> tuple[Fraction | None, mx.Expr]:
    """``(a, b)`` for ``e = a·var + b``; ``a is None`` when ``e`` is not affine.

    ``a is None`` covers two cases the caller has to tell apart: a constant
    argument (``u = 3``) and a genuinely non-affine one (``u = sin(x)``).
    Neither can be inverted, and both are reported rather than approximated.

    ``u = a·var + b`` exactly, so with no constant term ``b`` is zero — reading
    the coefficient as the constant term is what produced the nonsense
    «x = (pi/2 − 1)» for ``sin(x) = 1``.
    """
    # A quotient by a plain number scales the whole affine form and stays affine:
    # (2·x + 1)/3 is (2/3)·x + 1/3, and refusing it threw away a family of
    # perfectly good solutions. It also fixes x/2, whose coefficient is 1/2 and
    # not the 2 of the divisor — reading the divisor as the scale gave
    # «sen(x/2) = 1 → x = pi/4» where the answer is pi/2.
    if isinstance(e, mx.Div) and isinstance(e.right, mx.Num) \
            and not mx.variables(e.right) and e.right.value != 0:
        divisor = e.right.value
        a, b = _afine(e.left, var)
        return (a / divisor if a is not None else None,
                _divide_por_constante(b, divisor))
    a = Fraction(0)
    constantes: list[mx.Expr] = []
    for signo, termino in _sumandos(e):
        escalar = _escalar_de_x(termino, var)
        if escalar is not None:
            a += signo * escalar
        elif mx.variables(termino):
            return None, mx.ZERO                 # sin(x), x^2, x/(x+1)
        else:
            constantes.append(termino if signo > 0 else mx.Neg(termino))
    if not constantes:
        b = mx.ZERO
    elif len(constantes) == 1:
        b = constantes[0]
    else:
        b = mx.Add(*constantes)
    return (a if a != 0 else None), b


def _como_expresion(c) -> mx.Expr:
    return c if isinstance(c, mx.Expr) else mx.Num(c)


def _fuera_de_rango(c) -> bool:
    """``|c| > 1`` for sine and cosine — numerically when it is not rational."""
    racional = mx.exact_value(_como_expresion(c))
    if racional is not None:
        return racional < -1 or racional > 1
    valor = mx.evaluate(_como_expresion(c))
    return valor is not None and abs(valor.real) > 1


def _es_uno(c) -> bool:
    return mx.exact_value(_como_expresion(c)) == 1


def _es_menos_uno(c) -> bool:
    return mx.exact_value(_como_expresion(c)) == -1


def _medio_pi(media: Fraction) -> mx.Expr:
    """``pi/2`` and ``-pi/2`` written as a multiple of pi, not as a fraction."""
    return mx.Mul(mx.Num(media), mx.PI)


def _soluciones_seno(c, u: mx.Expr, var: str):
    """``sin(u) = c``: two families, one when ``c = ±1`` where they merge."""
    if _fuera_de_rango(c):
        return [], [f"|{mx.text(_como_expresion(c))}| > 1: el seno no pasa de 1, "
                    "así que no hay solución"]
    alfa, multiplo, nota = _inversa("sin", c)
    hipotesis = [nota] if nota else [
        "el valor es notable: la solución se escribe como múltiplo exacto de pi"]
    if _es_uno(c) or _es_menos_uno(c):
        # sin(u) = 1 gives u = pi/2 + 2k·pi ; sin(u) = -1 gives u = -pi/2 + 2k·pi
        media = Fraction(1, 2) if _es_uno(c) else Fraction(-1, 2)
        familias = [Familia(_medio_pi(media), _dos_pi(),
                            "sin(u)=±1 en u = ±pi/2 + 2k·pi")]
    else:
        beta = mx.Sub(_pi(), alfa)
        familias = [
            Familia(alfa, _dos_pi(), "sin(u)=c en u = arcsin(c) + 2k·pi"),
            Familia(beta, _dos_pi(), "sin(u)=c en u = pi − arcsin(c) + 2k·pi"),
        ]
    return _trasladar(familias, u, var), hipotesis


def _soluciones_coseno(c, u: mx.Expr, var: str):
    if _fuera_de_rango(c):
        return [], [f"|{mx.text(_como_expresion(c))}| > 1: el coseno no pasa de "
                    "1, así que no hay solución"]
    alfa, _multiplo, nota = _inversa("cos", c)
    familias = [
        Familia(alfa, _dos_pi(), "cos(u)=c en u = arccos(c) + 2k·pi"),
        Familia(mx.Neg(alfa), _dos_pi(), "cos(u)=c en u = −arccos(c) + 2k·pi"),
    ]
    if _es_uno(c):
        familias = familias[:1]  # both branches are the same angle at c = 1
    return _trasladar(familias, u, var), [nota] if nota else []


def _soluciones_tangente(c, u: mx.Expr, var: str):
    alfa, _multiplo, nota = _inversa("tan", c)
    hipotesis = ["la tangente tiene periodo pi, no 2pi: por eso el paso es pi"]
    if nota:
        hipotesis.append(nota)
    familias = [Familia(alfa, _pi(), "tan(u)=c en u = arctan(c) + k·pi")]
    return _trasladar(familias, u, var), hipotesis


def _trasladar(familias: list[Familia], u: mx.Expr, var: str) -> list[Familia]:
    """Invert ``u = ...`` into ``x = ...`` when possible; otherwise say so."""
    salida: list[Familia] = []
    for familia in familias:
        invertida = _invertir(u, familia.base, familia.paso, var)
        if invertida is None:
            familia = Familia(
                familia.base, familia.paso, familia.metodo,
                f"las soluciones son para «{mx.text(u)}»; deshacer ese cambio de "
                "variable no está resuelto todavía, así que no se escribe en x (§5.4)",
                en_x=False)
            salida.append(familia)
            continue
        base, paso, _ = invertida
        salida.append(Familia(base, paso, familia.metodo, familia.hipotesis))
    return salida


# --- case 2: a·sin(u) + b·cos(u) = c ---------------------------------------


def _caso_fase(f: mx.Expr, var: str):
    """``a·sin(u) + b·cos(u) = c``, brought to one sine with a phase shift."""
    from academic_core.domain.engineering.mathlab.trig import _factores

    if not isinstance(f, (mx.Add, mx.Sub)):
        return None
    terminos = trig._terminos(f)
    # At least two terms, not exactly three: the equation arrives as «f - c», so
    # the constant is usually a term of its own — but the rational case hands over
    # a bare numerator with no constant in it, and «a·sin + b·cos = 0» is the same
    # family with c = 0, not a different one.
    if len(terminos) < 2:
        return None
    a = b = None
    cte = Fraction(0)
    u = None
    for signo, termino in terminos:
        coeficiente, factores = _factores(termino)
        if not factores:
            cte = cte + signo * coeficiente
            continue
        if len(factores) != 1 or isinstance(factores[0], mx.Pow):
            return None
        funcion = factores[0]
        if not (isinstance(funcion, mx.Call) and len(funcion.args) == 1):
            return None
        # The argument is checked ONCE, for both functions and before either is
        # taken. It used to be checked in the cosine branch only, and the sine
        # branch assigned `u` outright — so `cos(x) - sen(2x)` was read as one
        # function of one angle with two names on it, and answered as though both
        # were `u`. That published `{pi/8, 5pi/8, ...}`, the solutions of
        # `tg(2x) = 1`, for an equation none of whose solutions that is.
        if funcion.name in ("sin", "cos"):
            if u is None:
                u = funcion.args[0]
            elif u != funcion.args[0]:
                return None
        if funcion.name == "sin" and a is None:
            a = signo * coeficiente
        elif funcion.name == "cos" and b is None:
            b = signo * coeficiente
        else:
            return None
    if a is None or b is None or u is None or (a == 0 and b == 0):
        return None
    # f = a·sin + b·cos + cte = 0, so a·sin + b·cos = −cte. Reading cte as the
    # right-hand side is what produced arcsin(−1/√13) for 2·sin+3·cos = 1.
    familias, hipotesis = _resolver_por_fase(a, b, -cte, u, var)
    espurias = _comprobar(familias, f, var)
    return familias, hipotesis, espurias


def _resolver_por_fase(a: Fraction, b: Fraction, cte: Fraction, u: mx.Expr, var: str):
    """``a·sin+b·cos = R·sin(u+phi)``, then solve the sine.

    ``R = sqrt(a²+b²)`` and ``phi = atan2(b, a)``. §5.5b: the phase shift is the
    reason this family is solvable at all, and the reason it is *only* worth
    doing when ``a² + b²`` is a square.
    """
    R2 = a * a + b * b
    if cte * cte > R2:
        return [], [f"|{cte}| > {float(math.sqrt(float(R2))):.6g}: la amplitud de "
                    "a·sin+b·cos no llega, así que no hay solución"]
    norma = _raiz_exacta(R2)
    # 0/raiz is 0: leaving the quotient there made exact_value give up and the
    # solution came out as asin(0/sqrt(2)) instead of asin(0)
    c = mx.ZERO if cte == 0 else mx.Div(mx.Num(cte), norma)
    alfa, _ = _inversa("sin", c)[:2]
    beta = mx.Sub(_pi(), alfa)
    # the phase goes through _inversa so that atan(1) comes out as pi/4 instead of
    # an unevaluated atan, which is the difference between an exact critical
    # point and one this engine cannot place
    if a != 0:
        phi, _multiplo, _nota = _inversa("tan", Fraction(b, a))
    else:
        phi = mx.Mul(mx.Num(Fraction(1, 2)), mx.PI)
    familias = [
        Familia(mx.Sub(alfa, phi), _dos_pi(),
                "a·sin(u)+b·cos(u) = R·sin(u+phi), luego u = arcsin(c) − phi"),
        Familia(mx.Sub(beta, phi), _dos_pi(),
                "la segunda rama del seno, u = pi − arcsin(c) − phi"),
    ]
    hipotesis = [
        f"R = {mx.pretty(norma)} y phi = atan2(b,a): el desplazamiento de fase es "
        "lo que convierte la suma en un solo seno (§5.5b)",
    ]
    return _trasladar(familias, u, var), hipotesis


def _raiz_cuadratica(c2: Fraction, c1: Fraction, discriminante: Fraction,
                     signo: int) -> mx.Expr:
    """``(-c1 + signo·sqrt(D))/(2·c2)`` as ``A ± B·sqrt(r)``, ``r`` square-free.

    ``sqrt(p/q) = sqrt(p·q)/q``, and the largest square ``s²`` dividing ``p·q``
    comes out as ``s``. Exact in every step; only the form changes.
    """
    a = -c1 / (2 * c2)
    if discriminante == 0:
        return mx.Num(a)
    producto = discriminante.numerator * discriminante.denominator
    fuera, dentro, d = 1, producto, 2
    while d * d <= dentro:
        while dentro % (d * d) == 0:
            dentro //= d * d
            fuera *= d
        d += 1
    b = Fraction(signo * fuera, discriminante.denominator) / (2 * c2)
    if dentro == 1 or b == 0:
        return mx.Num(a + (b if dentro == 1 else 0))
    radical = mx.Root(2, mx.Num(Fraction(dentro)))
    termino = radical if abs(b) == 1 else mx.Mul(mx.Num(abs(b)), radical)
    if a == 0:
        return termino if b > 0 else mx.Neg(termino)
    return mx.Add(mx.Num(a), termino) if b > 0 else mx.Sub(mx.Num(a), termino)


def _raiz_exacta(valor: Fraction) -> mx.Expr:
    """``sqrt(valor)`` exactly: a rational root when there is one, else the root."""
    from academic_core.domain.engineering.mathlab.mvexpr import _exact_root
    raiz = _exact_root(valor, 2)
    if raiz is not None:
        return mx.Num(raiz)
    return mx.Root(2, mx.Num(valor))


# --- case 3: a polynomial in sin, cos or tan --------------------------------


def _caso_racional(f: mx.Expr, var: str):
    """``N/D = 0`` reduces to ``N = 0``, and that is the whole strategy (T-20).

    This is the case that makes a reciprocal equation solvable at all:
    ``sec(x) = 1`` is ``1/cos(x) - 1 = 0``, whose rational normal form is
    ``(1 - cos(x)) / cos(x)``. Its zeros are the zeros of the **numerator**, never
    the denominator's — the points where the denominator dies are poles, and a
    pole is not a solution to anything.

    The pre-pass that turns ``sec`` into ``1/cos`` lives in :func:`_a_cocientes`
    rather than here, because a rule that expands and another that shrinks cannot
    share a fixed point.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as I

    f = I._a_cocientes(f)
    if not mx.depends(f, var):
        return None
    ratio = P.as_ratio(f, var)
    if ratio is None or ratio.is_constant_ratio():
        return None
    # to_expr rebuilds the expression faithfully but not canonically: it comes back
    # as «1*cos(x) + (-1)*sin(x)», and no case below recognises that shape. One pass
    # of the normaliser turns it into «cos(x) - sin(x)», which they all do.
    from academic_core.domain.engineering.mathlab import trig as T

    numerador = T.simplify(P.to_expr(ratio.numerator))
    if mx.text(numerador) == mx.text(f):
        return None                     # nothing was actually divided out
    if mx.exact_value(numerador) == 0:
        return [], ["el numerador se anula en todas partes, así que la ecuación "
                    "se cumple siempre que el denominador no se anule"], []
    hipotesis = [f"el lado izquierdo se lleva a un cociente: se multiplica por el "
                 f"denominador y queda «{mx.text(numerador)} = 0». Los puntos donde "
                 f"el denominador se anula son polos, no soluciones"]
    familias, h, espurias = _casos(numerador, var)
    # Multiplying by the denominator ADDS candidates: every zero of that denominator
    # now satisfies `N/D = 0`, and none of them satisfies the equation, because the
    # equation is not posed there. `1/tg(x)*sen(x) = 0` becomes `sen(x) = 0` over
    # `tg(x)`, and `x = 0` solves THAT \u2014 where the original is `1/0`.
    #
    # The hypothesis said the poles were not solutions; this makes it true. Asked of
    # the DOMAIN and never of the evaluator, which at `x = pi/2` sees `tg = 1.6*10^16`
    # and calls a pole a large ordinary number.
    if familias:
        publicables = _publica_si_el_punto_existe(familias, f, var)
        if publicables is None:
            return [], hipotesis + list(h), []
        familias = publicables
        espurias = _comprobar(familias, f, var)
    hipotesis = hipotesis + list(h)
    return familias, hipotesis, espurias


def _factores_planos(e: mx.Expr) -> list[mx.Expr]:
    """``e`` as the factors of a product, with a non-negative power folded in.

    ``Mul`` takes only two children, so a product is a nest of two-child nodes and
    has to be flattened. ``sen(x)^2·cos(x)`` counts as two factors, because
    ``a^k = 0`` exactly when ``a = 0`` for a non-negative ``k`` — and a NEGATIVE
    power is left alone, since ``1/sen(x)`` has no zeros to contribute and putting
    it in the list would be claiming that the product has a root where it has none.
    """
    if isinstance(e, mx.Mul):
        return _factores_planos(e.left) + _factores_planos(e.right)
    if isinstance(e, mx.Pow) and isinstance(e.exponent, mx.Num) \
            and e.exponent.value.denominator == 1 and e.exponent.value >= 0:
        return _factores_planos(e.base)
    return [e]


def _saca_nombre(factorizado: mx.Expr) -> str:
    """The common factor of a factored expression, written for the trace."""
    factores = [g for g in _factores_planos(factorizado)
                if not isinstance(g, mx.Num)]
    comun = [g for g in factores
             if sum(1 for h in factores if mx.text(h) == mx.text(g)) > 1]
    return "·".join(mx.text(g) for g in comun) or mx.text(factorizado)


def _factores_de_un_termino(e: mx.Expr) -> list[mx.Expr]:
    """A term as a flat list of factors, its numeric coefficient last."""
    if isinstance(e, mx.Mul):
        salida: list[mx.Expr] = []
        for hijo in (e.left, e.right):
            salida.extend(_factores_de_un_termino(hijo))
        return salida
    return [e]


def _saca_factor_comun(f: mx.Expr, var: str):
    """``sen(x) + 2·sen(x)·cos(x)`` as ``sen(x)·(1 + 2·cos(x))``, or ``None``.

    This is the step that was missing between the multiple angle and the product
    rule. ``sen(x) + sen(2x) = 0`` develops to ``sen x + 2sen x cos x``, and the
    product rule cannot see a product in that: it is written as a SUM, with the
    factor repeated in each term instead of pulled out in front. Factoring it gives
    ``sen x·(1 + 2cos x) = 0``, which asks the two questions the engine can already
    answer on its own — ``sen x = 0`` and ``cos x = -1/2``.

    **The result is checked by SAMPLING before it is used.** A factorisation that is
    not one is a different equation, and the cheapest way to be wrong here is to be
    wrong quietly: the guard is the value at seven points, and if they disagree by
    anything the answer is ``None``. Asking the DOMAIN would not do — both forms
    exist wherever either does — and asking the algebra would mean trusting the
    algebra that is being checked.
    """
    from academic_core.domain.engineering.mathlab.trig import _terminos

    if not isinstance(f, (mx.Add, mx.Sub)):
        return None
    terminos = [termino for _, termino in _terminos(f) if termino is not None]
    if len(terminos) < 2:
        return None

    listas = []
    for coeficiente, termino in _terminos(f):
        if termino is None:
            continue
        # The coefficient is PART of the term. Leaving it out is how
        # `cos x - 2cos x sin x` came out as `cos x(cos x - sin x)` — a different
        # function — and the sampling below caught it, which is what it is for.
        factores = _factores_de_un_termino(termino)
        if coeficiente is not None and coeficiente != 1:
            factores = [mx.Num(coeficiente)] + factores
        if not any(not isinstance(g, mx.Num) for g in factores):
            return None               # a constant term: nothing common to pull out
        listas.append(factores)
    if len(listas) < 2:
        return None

    comun: list[mx.Expr] = []
    for factor in listas[0]:
        if isinstance(factor, mx.Num):
            continue
        clave = mx.text(factor)
        if all(any(mx.text(g) == clave for g in otros) for otros in listas[1:]):
            comun.append(factor)
    if not comun:
        return None

    comas_claves = {mx.text(g) for g in comun}

    def cociente(factores: list[mx.Expr]) -> mx.Expr | None:
        quedan = list(factores)
        for clave in comas_claves:
            for i, g in enumerate(quedan):
                if mx.text(g) == clave:
                    quedan.pop(i)
                    break
            else:
                return None
        if not quedan:
            # The term IS the common factor. Its quotient is one, not nothing:
            # `sen x + 2 sen x cos x` has a term that is exactly `sen x`, and
            # returning None here is what made this refuse every equation it was
            # written for.
            return mx.Num(1)
        salida = quedan[0]
        for g in quedan[1:]:
            salida = mx.Mul(salida, g)
        return salida

    cocientes = []
    for factores in listas:
        c = cociente(factores)
        if c is None:
            return None
        cocientes.append(c)
    if len(cocientes) < 2:
        return None                   # factoring it out would gain nothing

    fuera = cocientes[0]
    for c in cocientes[1:]:
        fuera = mx.Add(fuera, c)
    comun_expr = comun[0]
    for g in comun[1:]:
        comun_expr = mx.Mul(comun_expr, g)
    factorizado = mx.Mul(comun_expr, fuera)

    # The same function, asked of the two forms at seven points.
    comparados = 0
    for k in range(1, 15, 2):
        x = k * 0.37
        antes = mx.valor_real(f, {var: x})
        despues = mx.valor_real(factorizado, {var: x})
        if antes is None or despues is None:
            continue
        comparados += 1
        escala = max(1.0, abs(antes))
        if abs(antes - despues) > 1e-9 * escala:
            return None                # no es la misma función: no se usa
    return factorizado if comparados >= 3 else None


def _caso_producto(f: mx.Expr, var: str):
    """``A·B = 0`` is ``A = 0`` or ``B = 0``: one factor at a time.

    The engine already solves ``sen(x) = 0`` and ``cos(x) = 0``; what it could not
    do was notice that a product of them asks both questions at once. ``sen(x)·cos(x)
    = 0`` was refused, and it is the simplest equation in this family — so the
    refusal was not a limitation to declare but a gap that made the whole family
    invisible.

    Every factor has to be answered, and the answers are checked back against the
    ORIGINAL product rather than against each factor: ``A·B = 0`` with a root of
    ``A`` is a root of the product whatever ``B`` does there, and _comprobar is
    what proves it rather than this function.
    """
    if isinstance(f, mx.Sub) and f.right == mx.ZERO:
        f = f.left                      # «A·B - 0» es «A·B», no otra cosa
    if isinstance(f, (mx.Add, mx.Sub)):
        # A sum with a common factor is a product written the long way round. The
        # factors go in front and the rule below asks each of them, so the only
        # thing missing was pulling them out.
        factorizado = _saca_factor_comun(f, var)
        if factorizado is None:
            return None
        parcial = _caso_producto(factorizado, var)
        if parcial is None:
            return None
        familias, hipotesis, espurias = parcial
        comas = "el lado izquierdo se escribe como producto sacando el factor "
        comun = _saca_nombre(factorizado)
        hipotesis = [f"{comas}común «{comun}» y se pregunta cada factor por separado"] \
            + list(hipotesis)
        # checked against the ORIGINAL sum, not against the factored form
        return _deduplica(familias), hipotesis, _comprobar(familias, f, var)
    if not isinstance(f, mx.Mul):
        return None
    from academic_core.domain.engineering.mathlab import inequaciones as Iq

    factores = [g for g in _factores_planos(f) if var in mx.variables(g)]
    if len(factores) < 2:
        return None
    familias: list[Familia] = []
    hipotesis = ["un producto se anula si y solo si se anula alguno de sus "
                 "factores, así que la ecuación se parte en una por factor y "
                 "se responden todas"]
    for factor in factores:
        parcial = _casos(mx.Sub(factor, mx.ZERO), var)
        if parcial is None:
            return None
        nuevas, pasos, _ = parcial
        if not nuevas and any(MOTIVO_SIN_CASO in h for h in pasos):
            return None                 # un factor que no se sabe: no se responde
        familias.extend(nuevas)
        hipotesis.extend(pasos)
    if not familias:
        return None
    # ``A·B = 0`` is ``A = 0`` or ``B = 0`` only where the WHOLE PRODUCT exists, and
    # the question is asked of the product, NOT of the factors against each other.
    #
    # Comparing the factors' domains was too strong, and it refused two equations it
    # could answer. ``tg(x)·sen(x) = 0`` has ``tg`` undefined at ``pi/2 + k·pi`` and
    # ``sen`` defined there, so their domains differ and the check said no. But the
    # solutions are ``x = k·pi``, and not one of those is ``pi/2 + k·pi``: the
    # solution set has **no holes at all** and the refusal was an admission of a gap
    # that was not there. The same for ``sen(x)·cos(x)·tg(x) = 0``.
    #
    # So: ask the domain of the PRODUCT and check every published point against it.
    # That is the exact condition — a point solves ``A·B = 0`` when it is a zero of
    # some factor AND the product exists there — and it is neither too strong nor
    # too weak. A point that lands in a hole refuses the whole product, because a
    # family cannot be published with holes in it.
    #
    # Asked of the DOMAIN and never of the evaluator, which at `x = pi/2` sees
    # `cos = 6·10⁻¹⁷` and `tg = 1.6·10¹⁶` and calls the product a large ordinary
    # number where there is nothing at all. Asking «does this exist here?» of a
    # float gets an answer, and that answer is a lie.
    try:
        dominio_producto = Iq.dominio(f, var)
    except Exception:                       # noqa: BLE001 «no lo sé» es respuesta
        return None
    for familia in familias:
        for k in (-2, -1, 0, 1, 2):
            valor = mx.valor_real(familia.miembro(k, var), {})
            if valor is None:
                return None
            punto = D.Punto(
                expresion=mx.Num(Fraction(valor).limit_denominator(10 ** 9)))
            if not dominio_producto.contiene(punto):
                return None
    espurias = _comprobar(familias, f, var)
    return _deduplica(familias), hipotesis, espurias


def _potencia_de_pitagoras(argumento, exponente: int, nombre: str):
    """``(1 - sen(u)**2)**k`` written out, as a sum of powers of ``sen(u)``.

    The expansion is done with ``Fraction`` arithmetic because a ``Pow`` of a ``Sub``
    is an ATOM to :func:`poly.as_poly`, and an atom is exactly what
    :func:`_como_polinomio` refuses: it cannot see that ``cos(x)**2`` and
    ``sen(x)**2`` are the same thing squared.

    Only even powers are rewritten, and only for the pair ``sen``/``cos``:
    ``cos**2 = 1 - sen**2`` holds everywhere, so this changes no domain at all.
    ``tg**2`` has no such form and is left alone.

    ``argumento`` is the symbol the trig function is applied to, and it has to be the
    one the caller already uses \u2014 ``x``, not ``u``. :func:`_como_polinomio` replaces
    ``nombre(·)`` by ``u`` and then hands back the argument it replaced, and
    :func:`_trasladar` undoes exactly that substitution afterwards. Writing ``cos(u)``
    here made the argument ``u`` before the substitution ever happened, so the undo
    step shifted every solution by ``u`` instead of by ``x`` and
    ``cos(x)**2 > 1/2`` lost its critical points.
    """
    base = mx.Call(nombre, (argumento,))
    cociente = P.as_poly(mx.Sub(mx.Num(1), mx.Pow(base, mx.Num(2))))
    polinomio = cociente
    for _ in range(max(0, exponente - 1)):
        polinomio = P.mul(polinomio, cociente)
    return P.to_expr(polinomio)


def _pitagoras_para(f: mx.Expr, nombre: str, var: str):
    """``cos(x)**2`` as ``1 - sen(x)**2``, so a SUM of two functions becomes a
    polynomial in one of them.

    ``sen(x) + cos**2(x) = 0`` has two functions in it and no case could read it,
    which is why ``tg(x) + cos(x) = 0`` refused: the quotient brings it to
    ``sen(x) + cos²(x) = 0`` and then it is stuck one step short. With Pythagoras it
    is ``sen²(x) - sen(x) - 1 = 0``, whose roots are ``(1 ± √5)/2`` \u2014 and only one of
    the two is a value of the sine.

    Written here and not added to ``trig.simplify`` because the solvers read that
    one, and this GROWS the expression: ``sen\u00b2x`` is five characters where ``cos\u00b2x``
    is six. A rewrite that makes the expression longer belongs to its own objective
    (\u00a75.5b), and the only thing that wants it is the solver.

    Returned **per candidate function**, and only tried when the plain reading of
    the same candidate has failed: ``1/cos(x)**4 = 16`` read as ``cos`` is
    ``cos**4 = 1/16`` and solved, and read as ``sen`` through Pythagoras it is
    ``(1 - sen**2)**2 = 1/16``, a quartic with no rational roots. A rewrite that
    helps in one place and hides the answer in another is worse than not having it.
    """
    if nombre not in ("sin", "cos"):
        return None
    otro = "cos" if nombre == "sin" else "sin"
    simbolo = mx.Sym(var)

    def reescribe(e: mx.Expr) -> mx.Expr:
        if isinstance(e, mx.Call) and e.name == otro and len(e.args) == 1 \
                and e.args[0] == simbolo:
            return mx.Call(otro, (simbolo,))
        if isinstance(e, mx.Call):
            return mx.Call(e.name, tuple(reescribe(a) for a in e.args))
        if isinstance(e, mx.Neg):
            return mx.Neg(reescribe(e.arg))
        if isinstance(e, mx.Pow):
            base, exponente = reescribe(e.base), e.exponent
            if isinstance(base, mx.Call) and base.name == otro \
                    and isinstance(exponente, mx.Num) \
                    and exponente.value.denominator == 1 \
                    and exponente.value >= 2 and exponente.value % 2 == 0:
                # HALF the exponent: `cos**2 = 1 - sen**2`, so `cos**(2k)` is
                # `(1 - sen**2)**k`. Using the whole exponent gives `cos**4` the
                # value of `cos**8`, and `cos(x)**2 = 1/2` came out with no
                # solutions at all.
                #
                # And with the base's OWN argument. Writing `simbolo` here turned
                # `cos(x - pi/4)**2` into `1 - sen(x)**2`, a different equation:
                # `cos(x - pi/4)**2 = 1` published `x = 0 + 2k·pi` and `x = pi + 2k·pi`
                # where the answer is `x = pi/4 + k·pi` (found 2026-10-05).
                # `_como_polinomio` still demands ONE argument for every call, so
                # mixing `sen(x)` with `cos(2x)**2` is refused, not merged.
                return _potencia_de_pitagoras(base.args[0], int(exponente.value) // 2,
                                              nombre)
            return mx.Pow(base, exponente)
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            izquierda, derecha = reescribe(e.left), reescribe(e.right)
            if isinstance(e, mx.Add):
                return mx.Add(izquierda, derecha)
            if isinstance(e, mx.Sub):
                return mx.Sub(izquierda, derecha)
            if isinstance(e, mx.Mul):
                return mx.Mul(izquierda, derecha)
            return mx.Div(izquierda, derecha)
        return e

    resultado = reescribe(f)
    return None if resultado == f else resultado


def _cociente_de_tangente(f: mx.Expr, var: str):
    """``tg`` and ``cotg`` written as the quotient they are, or ``None``.

    ``as_ratio`` cannot help with ``tg(x) + cos(x) = 0`` because it treats
    ``tg(x)`` as an ATOM: there is no division in ``cos(x) + tg(x)``, so the
    quotient never appears and the rational case never fires. The ratio only exists
    after this rewrite.

    ``tg(u) = sen(u)/cos(u)`` and ``cotg(u) = cos(u)/sen(u)`` are equal wherever
    BOTH sides exist, and they do not exist at the same points: the quotient is dead
    at ``cos(u) = 0`` and the tangent is alive there, and vice versa. So this is not
    something to put in ``trig.simplificar`` \u2014 the solvers read that one, and it would
    change the domain of ``1/tg(x)`` without saying so (\u00a75.7). It is applied HERE,
    once, and every published point is then checked against the domain of the
    ORIGINAL expression, which is where the poles get excluded.
    """
    if not _tiene_tangente_o_cotangente(f):
        return None
    reemplazos = {"tan": ("sin", "cos"), "cot": ("cos", "sin")}

    def reescribe(e: mx.Expr) -> mx.Expr:
        if isinstance(e, mx.Call) and e.name in reemplazos and len(e.args) == 1:
            numerador, denominador = reemplazos[e.name]
            u = e.args[0]
            return mx.Div(mx.Call(numerador, (u,)), mx.Call(denominador, (u,)))
        if isinstance(e, mx.Call):
            return mx.Call(e.name, tuple(reescribe(a) for a in e.args))
        if isinstance(e, mx.Neg):
            return mx.Neg(reescribe(e.arg))
        if isinstance(e, mx.Pow):
            return mx.Pow(reescribe(e.base), e.exponent)
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            izquierda, derecha = reescribe(e.left), reescribe(e.right)
            if isinstance(e, mx.Add):
                return mx.Add(izquierda, derecha)
            if isinstance(e, mx.Sub):
                return mx.Sub(izquierda, derecha)
            if isinstance(e, mx.Mul):
                return mx.Mul(izquierda, derecha)
            return mx.Div(izquierda, derecha)
        return e

    cociente = reescribe(f)
    return None if cociente == f else cociente


def _tiene_tangente_o_cotangente(e: mx.Expr) -> bool:
    if isinstance(e, mx.Call):
        return e.name in ("tan", "cot") or any(
            _tiene_tangente_o_cotangente(a) for a in e.args)
    if isinstance(e, mx.Neg):
        return _tiene_tangente_o_cotangente(e.arg)
    if isinstance(e, mx.Pow):
        return _tiene_tangente_o_cotangente(e.base)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return (_tiene_tangente_o_cotangente(e.left)
                or _tiene_tangente_o_cotangente(e.right))
    return False


def _publica_si_el_punto_existe(familias: list[Familia], original: mx.Expr,
                                var: str):
    """Publish only if every point of every family is a point where ``original``
    exists.

    A family ``base + paso·k`` cannot express a hole, so a solution with holes in it
    cannot be published at all. Asked of the DOMAIN and never of the evaluator,
    which at ``x = pi/2`` sees ``cos = 6·10⁻¹⁷`` and calls the tangent a large
    ordinary number where there is nothing at all.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as Iq

    try:
        dominio = Iq.dominio(original, var)
    except Exception:                       # noqa: BLE001 «no lo sé» es respuesta
        return None
    for familia in familias:
        for k in range(-3, 4):
            valor = mx.valor_real(familia.miembro(k, var), {})
            if valor is None:
                return None
            # The point has to be built the way the DOMAIN builds its own, or the two
            # are not the same kind of point and the comparison says nothing useful.
            # `Punto(expresion=Num(6.28...))` and `Punto(es_pi=True, coeficiente=2)`
            # are the same place and two different objects; asking a rational-expressed
            # point whether it is inside a domain whose holes are multiples of pi
            # answers the wrong question, and the answer was «yes».
            cociente = valor / math.pi
            racional = Fraction(cociente).limit_denominator(10 ** 6)
            candidatos = [D.Punto(
                expresion=mx.Num(Fraction(valor).limit_denominator(10 ** 9)))]
            if abs(float(racional) - cociente) < 1e-9:
                candidatos.append(D.punto_pi(racional))
            for punto in candidatos:
                try:
                    dentro = dominio.contiene(punto)
                except Exception:       # noqa: BLE001 «no lo sé» es respuesta
                    return None
                if not dentro:
                    return None
    return _deduplica(familias)


def _caso_tangente(f: mx.Expr, var: str):
    """``tg(x) + cos(x) = 0``, which is a polynomial in ``sen`` once divided.

    ``tg(x) + cos(x) = 0`` is ``sen(x)/cos(x) + cos(x) = 0``, the rational case
    multiplies by the denominator and gets ``sen(x) + cos²(x) = 0``, and Pythagoras
    turns that into ``sen²(x) - sen(x) - 1 = 0``. Its roots are ``(1 ± √5)/2``, and
    only one of the two is a value of the sine.
    """
    cociente = _cociente_de_tangente(f, var)
    if cociente is None:
        return None
    familias, hipotesis, espurias = _casos(cociente, var)
    if not familias:
        return None
    publicables = _publica_si_el_punto_existe(familias, f, var)
    if publicables is None:
        return None
    hipotesis = [
        "la tangente se escribe como su cociente, que es donde aparece el "
        "denominador; los puntos donde ese denominador se anula quedan fuera, y "
        "no son soluciones de la ecuación original"] + list(hipotesis)
    return publicables, hipotesis, _comprobar(publicables, f, var)


def _a_racional_en_u(e: mx.Expr, var: str):
    """``e`` as a rational function of ``u = tg(x/2)``, or ``None``.

    The substitution that makes every trigonometric expression rational, written
    down here rather than taken from :mod:`trig` because the solver needs the
    DIRECTION \u2014 from ``x`` to ``u`` \u2014 and the module only had the way back.

    **The argument has to BE the unknown.** ``sen(2x)`` is not ``2u/(1+u^2)``: that
    table entry is ``sen(v)`` for ``v = x``, and reading ``2x`` as an affine ``v`` is
    the same mistake :func:`_como_polinomio` used to make \u2014 substituting a function by
    its name without looking at what is inside. It answered
    ``cos(x) + cos(2x) = 0`` with ``2*arctg(1)``, and at ``x = pi/2`` the left side is
    ``-1``.

    A multiple angle is handled BEFORE this, by writing it in powers of the same
    function, so ``cos(2x)`` is never still a ``cos(2x)`` by the time the substitution
    looks at it.
    """
    from academic_core.domain.engineering.mathlab import mvexpr as M

    u = M.Sym("u")
    u2 = M.Pow(u, M.Num(2))
    uno_mas = M.Add(M.Num(1), u2)
    tabla = {
        "sin": M.Div(M.Mul(M.Num(2), u), uno_mas),
        "cos": M.Div(M.Sub(M.Num(1), u2), uno_mas),
        "tan": M.Div(M.Mul(M.Num(2), u), M.Sub(M.Num(1), u2)),
    }

    def baja(nodo: mx.Expr) -> mx.Expr:
        if isinstance(nodo, mx.Call) and len(nodo.args) == 1 \
                and nodo.name in tabla:
            if not (isinstance(nodo.args[0], mx.Sym)
                    and nodo.args[0].name == var):
                return nodo
            return tabla[nodo.name]
        if isinstance(nodo, mx.Call):
            return M.Call(nodo.name, tuple(baja(a) for a in nodo.args))
        if isinstance(nodo, mx.Neg):
            return M.Neg(baja(nodo.arg))
        if isinstance(nodo, mx.Pow):
            return M.Pow(baja(nodo.base), baja(nodo.exponent))
        if isinstance(nodo, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(nodo)(baja(nodo.left), baja(nodo.right))
        return nodo

    ratio = P.as_ratio(baja(e), "u")
    if ratio is None or ratio.is_constant_ratio():
        return None
    # `u` has to be the only variable left. `sen(x) = x` becomes `2u/(1+u^2) = x`,
    # and a rational function of `u` AND `x` is not a polynomial in `u`, so without
    # this the case would claim to solve it and then answer with the roots of a
    # polynomial in the wrong variable.
    if P.real_variables(ratio.numerator) - {"u"} \
            or P.real_variables(ratio.denominator) - {"u"}:
        return None
    if P.atoms_of(ratio.numerator) or P.atoms_of(ratio.denominator):
        # A division that is not by a constant becomes an ATOM, and an atom is a
        # variable this case cannot see the value of. `degree_in` then counts the
        # exponent of the `u^2` buried inside the atom and reports «degree 2», the
        # quadratic formula runs on a fraction, and the roots come out as `0/0`.
        return None
    return ratio


def _cuadrado_elimina_una_funcion(f: mx.Expr, var: str):
    """``sen(x) + sen(2x) = 1`` as a CUBIC, by squaring once.

    The universal substitution makes this equation a quintic in ``t = tg(x/2)``, and a
    quintic has no solution by radicals. **That is an artefact of the SUBSTITUTION,
    not of the equation**: ``t = tg(x/2)`` sends a point to infinity and the degree
    that comes with it is not the equation's degree.

    The other way round it is a cubic. ``sen x + 2sen x cos x = 1`` is
    ``sen x (1 + 2cos x) = 1``, so ``sen x = 1/(1 + 2cos x)``, and squaring once with
    ``sen²x = 1 - cos²x`` gives

    ``1 = (1 - c²)(1 + 2c)²``  ->  ``c * (4c³ + 4c² - 3c - 4) = 0``

    a cubic, which Cardano closes. So the equation that looked unsolvable is
    solvable, and the way to see it is that the quintic was never the problem.

    **Squaring ADDS solutions**, and that is not a detail: every root of the squared
    equation is a candidate and only some of them satisfy the original. So each one
    is checked against ``f`` at the angles that give that cosine, and only the ones
    that annul it are published. The check is numerical on purpose — it answers «does
    this candidate actually work?», which is not another piece of algebra.
    """
    polinomio = P.as_poly(f)
    if not polinomio:
        return None
    from academic_core.domain.engineering.mathlab import mvexpr as M
    texto_sen = M.text(M.Call("sin", (M.Sym(var),)))
    texto_cos = M.text(M.Call("cos", (M.Sym(var),)))
    # `atoms_of` gives the atom NAMES \u2014 with the `@` prefix the monomial keys carry \u2014
    # so both are read from there rather than rebuilt, and rebuilding them is how the
    # comparison below failed on the first try with an empty set.
    nombres = P.atoms_of(polinomio)
    if len(nombres) != 2:
        return None
    texto_sen = next((a for a in nombres if a.endswith("sin(x)")), None)
    texto_cos = next((a for a in nombres if a.endswith("cos(x)")), None)
    if texto_sen is None or texto_cos is None:
        return None                    # not one sine and one cosine of the unknown
    # `atoms_of` gives the names WITHOUT the `@` that the monomial keys carry, so the
    # two have to be in the same shape before anything is compared. Rebuilding the
    # names from scratch failed on the first try for exactly that reason: an empty
    # match reads exactly like a refusal.
    if not texto_sen.startswith("@"):
        texto_sen = "@" + texto_sen
    if not texto_cos.startswith("@"):
        texto_cos = "@" + texto_cos

    def desglose(monomio):
        """``(exponent of sen, [exponents of cos])``, or ``None`` for a third atom."""
        exponente_sen, del_cos = 0, []
        for nombre_atomo, exponente in monomio:
            if nombre_atomo == texto_sen:
                exponente_sen += exponente
            elif nombre_atomo == texto_cos:
                del_cos.append(exponente)
            else:
                return None
        return exponente_sen, del_cos

    def en_c(del_cos: list[int]):
        producto = M.Num(1)
        for exponente in del_cos:
            producto = M.Mul(producto, M.Pow(M.Sym("c"), M.Num(exponente)))
        return producto

    coeficiente_sen, coeficiente_resto = M.Num(0), M.Num(0)
    for monomio, coeficiente in polinomio.items():
        partes = desglose(monomio)
        if partes is None:
            return None
        exponente_sen, del_cos = partes
        if exponente_sen > 1:
            return None                # `sen` is not linear: it cannot be isolated
        # A term with no `cos` factor contributes its coefficient ALONE, and that is
        # an ADD and not a multiplication: `1*sen` is the `1` of `(1 + 2cos u)`.
        # Losing it dropped `(1 + 2c)²` out of the square, and what came out was a
        # quartic with no real roots where a cubic with one was sitting all along.
        if exponente_sen == 1 and not del_cos:
            termino = M.Num(coeficiente)
        else:
            termino = M.Mul(M.Num(coeficiente), en_c(del_cos))
        if exponente_sen == 1:
            coeficiente_sen = M.Add(coeficiente_sen, termino)
        else:
            coeficiente_resto = M.Add(coeficiente_resto, termino)
    if mx.text(coeficiente_sen) == "0":
        return None                    # there is no `sen` term to isolate

    c = M.Sym("c")
    uno_menos_c2 = M.Sub(M.Num(1), M.Pow(c, M.Num(2)))
    cuadrado_sen = P.as_poly(M.Pow(coeficiente_sen, M.Num(2)))
    cuadrado_resto = P.as_poly(M.Pow(coeficiente_resto, M.Num(2)))
    final = P.add(P.mul(cuadrado_sen, P.as_poly(uno_menos_c2)),
                  cuadrado_resto, -1)
    if not final:
        return None
    raices, _motivo = _raices_reales(final, c)
    if not raices:
        return None

    hipotesis = [
        "se despeja el seno, se eleva al cuadrado y se usa sen²u + cos²u = 1: en "
        "vez de un grado alto en t = tg(x/2) queda un polinomio en cos(u). Elevar "
        "al cuadrado AÑADE soluciones, así que cada candidata se comprueba contra la "
        "ecuación original y solo se publica la que la anula"]
    paso = mx.Mul(mx.Num(2), mx.PI)
    validas: list[Familia] = []
    for raiz in raices:
        coseno = mx.valor_real(trig.reducir_radicales(raiz).expresion, {})
        if coseno is None or abs(coseno) > 1.0 + 1e-12:
            continue                    # no cosine is out there
        # The angle carries the EXACT root, not a decimal of it. The first version
        # published `arccos(193072653/205929908)` — a rational approximation of a
        # cubic root, off in the tenth decimal — and a solution that is off in the
        # tenth decimal is not a solution, it is a plausible-looking lie (§5.4).
        angulo, _multiplo = _arccoseno_exacto(raiz)
        if mx.valor_real(angulo, {}) is None:
            continue                    # the angle is exact but not numeric
        for signo in (1, -1):
            base = mx.Neg(angulo) if signo < 0 else angulo
            valor_f = _evaluar(mx.substitute(f, var, base))
            if valor_f is not None and abs(valor_f) < 1e-9:
                validas.append(Familia(
                    base, paso, "cos(u) = la raíz del polinomio al cuadrado"))
    if not validas:
        return None
    espurias = _comprobar(validas, f, var)
    return _deduplica(validas), hipotesis, espurias

def _caso_sustitucion_universal(f: mx.Expr, var: str):
    """``t = tg(x/2)``: every trigonometric expression becomes rational.

    What it buys: two trigonometric terms with DIFFERENT arguments become a
    polynomial, and the product rule already knows how to solve the factors. This is
    the last path for the equations that survive every other one.

    Three things are checked rather than assumed, because each one is a way of
    answering a different question:

    - a root where the DENOMINATOR vanishes is SPURIOUS \u2014 it came from clearing
      denominators, not from the equation, and ``tg``'s denominator is dead at
      ``u = \u00b11``;
    - ``x = pi`` is where the substitution is not defined (``tg(pi/2)``), so it is
      asked separately instead of being silently absent;
    - every published family goes back through :func:`_comprobar` against the
      ORIGINAL expression.
    """
    ratio = _a_racional_en_u(f, var)
    if ratio is None:
        return None
    raices, motivo = _raices_reales(ratio.numerator, mx.Sym("u"))
    if not raices:
        return None
    if motivo:
        # The roots are PARTIAL and this case must refuse rather than publish half.
        # `sen(x) + sen(2x) = 1` is `u^6 - 4u^5 + 2u^4 + 3u^3 + 3u^2 - 6u + 1` in
        # `t = tg(x/2)`, and its only rational root is `u = 1`: what is left over is a
        # quintic. Publishing the one root that was found is publishing `pi/2` and
        # saying nothing about the other solution, which is the failure §5.4 is about
        # in the exact place that demands exactness.
        return None
    paso = mx.Mul(mx.Num(2), mx.PI)
    hipotesis = ["con t = tg(x/2) el lado izquierdo se vuelve racional en t y su "
                 f"numerador es de grado {P.degree_in(ratio.numerator, 'u')}: se "
                 "buscan sus raíces exactas y luego se deshace el cambio de variable"]
    validas: list[Familia] = []
    for raiz in raices:
        valor_den = _valor_de_la_raiz(ratio.denominator, raiz)
        if valor_den is not None and abs(valor_den) < 1e-9:
            hipotesis.append(
                f"la raíz t = {mx.text(raiz)} se descarta: ahí el denominador se "
                "anula y la ecuación ni siquiera está planteada")
            continue
        limpia = trig.reducir_radicales(raiz).expresion
        base = mx.Add(mx.Mul(mx.Num(2), mx.Call("atan", (limpia,))), paso)
        validas.append(Familia(base, paso, "u = t y x = 2·arctg(t) + 2k·pi"))
    hipotesis.append(
        "t = tg(x/2) no está definida en x = pi, que es el punto que el cambio de "
        "variable no alcanza: se pregunta aparte")
    en_pi = _evaluar(mx.substitute(f, var, mx.PI))
    if en_pi is not None and abs(en_pi) < 1e-9:
        validas.append(Familia(mx.PI, mx.Num(Fraction(0)), "x = pi", en_x=False))
        hipotesis.append("x = pi sí anula la ecuación: el cambio de variable no la "
                         "alcanza porque tg(pi/2) no existe")
    if not validas:
        return None
    # Every published point has to be a point where the ORIGINAL expression exists.
    # `1/tg(x)*sen(x) = 0` reduces to `(1 - u^2)/(1 + u^2) = 0`, whose roots `u = ±1`
    # are perfectly good zeros of that rational function \u2014 and at `x = 0` the original
    # is `1/0`, which is not a number. The substitution cannot see that: it made a
    # quotient of two quotients and lost the inner pole. So the domain of what was
    # ASKED is the last word, and it is asked per point.
    publicables = _publica_si_el_punto_existe(validas, f, var)
    if publicables is None:
        return None
    espurias = _comprobar(publicables, f, var)
    return _deduplica(publicables), hipotesis, espurias


def _valor_de_la_raiz(polinomio, raiz: mx.Expr):
    """A polynomial at a root that may be a radical, as a float, or ``None``.

    The root is evaluated FIRST and handed over as a number: it arrives as an
    expression \u2014 ``sqrt(2)/2`` is a ``Div`` of a ``Root`` \u2014 and the evaluator takes
    numbers in its environment, not trees.
    """
    valor_raiz = mx.valor_real(raiz, {})
    if valor_raiz is None:
        return None
    return mx.valor_real(P.to_expr(polinomio), {"u": valor_raiz})


def _caso_polinomio(f: mx.Expr, var: str):
    """``P(sin(u)) = 0`` and its sisters: exact roots first, then back up."""
    from academic_core.domain.engineering.mathlab.trig import _terminos

    if not isinstance(f, (mx.Add, mx.Sub)):
        return None
    terminos = _terminos(f)
    if len(terminos) < 2:
        return None
    primer_rechazo: list[str] | None = None
    for nombre in ("sin", "cos", "tan"):
        sub = mx.Sym("u")
        # Pythagoras is a SECOND TRY, not the first one. `1/cos(x)**4 = 16` read as
        # `cos` is a quadratic; read as `sen` through Pythagoras it is a quartic with
        # no rational roots. So the plain reading is asked first, per candidate, and
        # the rewrite only happens when that candidate failed.
        encontrado = _como_polinomio(f, nombre, sub, var)
        if encontrado is None:
            reescrito = _pitagoras_para(f, nombre, var)
            if reescrito is None:
                continue
            encontrado = _como_polinomio(reescrito, nombre, sub, var)
            if encontrado is None:
                continue
        polinomio, angulo = encontrado
        raices, motivo = _raices_reales(polinomio, sub)
        grado = P.degree_in(polinomio, sub.name)
        if not raices:
            if primer_rechazo is None:
                primer_rechazo = [motivo]
            continue
        familias: list[Familia] = []
        hipotesis = [f"el lado izquierdo es un polinomio de grado {grado} en "
                     f"{nombre}(u): se buscan sus raíces exactas y luego se "
                     "deshace el cambio"]
        if motivo:
            # The sentence that says the answer above is PARTIAL. It was dropped
            # here — computed on the line before and never read — and that is why
            # `sen(x)³ - sen(x)/2 = 0` could publish `{0, pi}` without a word.
            #
            # What happened there: the polynomial in `sen(u)` is `-u³ + u/2`, and
            # the rational root theorem finds `u = 0` and stops, because the other
            # two roots are `±1/√2` and no theorem that only looks for rational
            # numbers is going to find them. Four of the eight solutions were
            # missing and the engine said nothing about it.
            #
            # So this does not FIX the answer, and it is not claiming to. It stops
            # the answer from pretending to be complete, which is the difference
            # between a gap the user can see and one they cannot.
            hipotesis.append(motivo)
        for raiz in raices:
            # The polynomial gave the value of ``cos(angulo)``, so the next equation
            # is ``cos(u) = raiz`` in ``u``, and then ``u = angulo`` has to be undone.
            # Passing ``x`` as ``u`` skips that step, and it is not a no-op:
            # ``tg(x/2) = -1`` came out as ``x = -pi/4 + k·pi`` when the answer is
            # ``x = -pi/2 + 2k·pi``. The scale inside the argument is the whole
            # difference between those two, and it was being thrown away.
            if nombre == "sin":
                nuevas, h = _soluciones_seno(raiz, mx.Sym("u"), "u")
            elif nombre == "cos":
                nuevas, h = _soluciones_coseno(raiz, mx.Sym("u"), "u")
            else:
                nuevas, h = _soluciones_tangente(raiz, mx.Sym("u"), "u")
            nuevas = _trasladar(nuevas, angulo, var)
            familias.extend(nuevas)
            hipotesis.extend(h)
        espurias = _comprobar(familias, f, var)
        return _deduplica(familias), hipotesis, espurias
    # Nobody answered. The first refusal is reported, so the reason the student sees
    # is a real one and not the leftover of a candidate that was the wrong shape.
    return ([], primer_rechazo, []) if primer_rechazo else None


def _misma_familia(a: Familia, b: Familia) -> bool:
    """Whether two families describe the same set of points.

    Comparing the printed base is not enough, and ``cos(x) - cos(x)³ = 0`` shows
    why: it publishes ``x = pi + 2k·pi`` AND ``x = -pi + 2k·pi``, which are one
    family — both are the odd multiples of pi — written two ways. The student counts
    solutions and finds five where there are four, and this function's own comment
    already said that duplicates are a bug worth reporting.

    So the bases are compared BY VALUE through the step: the two are the same when
    their difference is a whole number of steps. Asked of ``mx.valor_real`` and never
    of ``mx.evaluate``, which answers in complex numbers for everything — ``Num(0)``
    arrives as ``0j`` — so a bare ``isinstance(valor, complex)`` guard would reject
    every single comparison here, silently.
    """
    if a.en_x != b.en_x:
        return False
    if not a.en_x:
        return mx.text(a.base) == mx.text(b.base)
    valor = mx.valor_real(mx.Div(mx.Sub(a.base, b.base), a.paso), {})
    return valor is not None and abs(valor - round(valor)) < 1e-9


def _deduplica(familias: list[Familia]) -> list[Familia]:
    """The same family twice is a bug the student would report; drop it.

    ``sin(x)³ − sin(x) = 0`` has roots 0, 1 and −1, and the root 0 reaches the
    sine case by more than one route. Compared by value, so that ``pi`` and ``-pi``
    with the same step are recognised as the one family they are.
    """
    salida: list[Familia] = []
    for familia in familias:
        if not any(_misma_familia(familia, visto) for visto in salida):
            salida.append(familia)
    return salida


def _como_polinomio(f: mx.Expr, nombre: str, sub: mx.Expr, var: str = "x"):
    """``f`` seen as a polynomial in ``sub``, or ``None``.

    **The argument is checked, and not checking it invents solutions.** Replacing
    every ``cos(·)`` by ``u`` regardless of what is inside turns ``cos(x) + cos(2x)``
    into ``2u``, and the solver then answers ``cos(x) = 0`` — the solutions of a
    DIFFERENT equation — for the equation that was asked. That is the worst thing
    this engine can do: ``cos(x) + cos(2x) = 0`` published ``{pi/2, -pi/2}``, and the
    domain of ``1/(cos(x) + cos(2x))`` inherited two holes that are not holes while
    missing the three that are.

    The guard below could not catch it either: nothing is left over, because
    ``2x`` was deleted along with the ``cos``. A substitution has to be checked
    where it is made, and this is the place.
    """
    comun: list[mx.Expr] = []

    def sustituir(e: mx.Expr) -> mx.Expr:
        if isinstance(e, mx.Call) and e.name == nombre and len(e.args) == 1:
            comun.append(e.args[0])
            return sub
        if isinstance(e, mx.Neg):
            return mx.Neg(sustituir(e.arg))
        if isinstance(e, mx.Pow):
            return mx.Pow(sustituir(e.base), sustituir(e.exponent))
        if isinstance(e, mx.Call):
            return mx.Call(e.name, tuple(sustituir(a) for a in e.args))
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(e)(sustituir(e.left), sustituir(e.right))
        return e

    try:
        polinomio = P.as_poly(sustituir(f))
    except Exception:
        return None
    if not polinomio:
        return None
    # Anything left as an *atom* means the substitution never applied to it:
    # 2·cos(x) − 1 is not a polynomial in sin(u), and accepting it as one made
    # the solver report «no hay soluciones» for an equation with four of them.
    if P.atoms_of(polinomio):
        return None
    variables = P.real_variables(polinomio)
    if variables - {sub.name} or sub.name not in variables:
        return None
    # One argument for every call of this name, or there is no single substitution.
    # ``cos(x) + cos(2x)`` is not a polynomial in ``cos(.)``: replacing both by ``u``
    # turns it into ``2u``, and the solver then answers ``cos(x) = 0`` — the
    # solutions of a DIFFERENT equation — for the one that was asked. That is the
    # worst thing this engine can do, and the guard that was here could not see it
    # because nothing is left over: ``2x`` was deleted along with the ``cos``.
    distintos = {mx.text(a) for a in comun}
    if len(distintos) != 1:
        return None
    return polinomio, comun[0]


def _raices_reales(polinomio: P.Polynomial, sub: mx.Expr,
                   completar: bool = True):
    """Exact real roots, with a Spanish reason when there are none to give.

    ``completar`` exists for the caller that needs the roots as POINTS rather than
    as expressions: the inequality sign chart draws one point per zero and cannot
    name a radical, so completing the roots with a quadratic formula would only
    turn a chart it CAN draw into one it refuses. The equation solver wants the
    opposite — there a radical root is a solution, and leaving it out is a wrong
    answer — so it asks for the complete set.
    """
    grado = P.degree_in(polinomio, sub.name)
    if grado < 1:
        return [], "el polinomio es constante y no se anula: no hay solución"
    if grado == 1:
        c0 = polinomio.get((), Fraction(0))
        c1 = polinomio.get(((sub.name, 1),), Fraction(0))
        if c1 == 0:
            return [], "el coeficiente de u se anula: la ecuación es degenerada"
        return [mx.Num(-c0 / c1)], ""
    if grado == 2:
        c2 = polinomio.get(((sub.name, 2),), Fraction(0))
        c1 = polinomio.get(((sub.name, 1),), Fraction(0))
        c0 = polinomio.get((), Fraction(0))
        discriminante = c1 * c1 - 4 * c2 * c0
        if discriminante < 0:
            return [], (f"el discriminante es {discriminante} < 0: no hay raíces "
                        "reales, y por tanto no hay soluciones reales")
        # written as A ± B·sqrt(r) with r square-free: the formula's own shape is
        # «(-0 + sqrt(8/3))/4», and it reached the student as atan((-0 + …)/4)
        return [_raiz_cuadratica(c2, c1, discriminante, 1),
                _raiz_cuadratica(c2, c1, discriminante, -1)], ""
    # Degree three and up. The rational root theorem on its own gives a PARTIAL
    # set, and that partial set was published as if it were the answer:
    # `sen(x)**3 - sen(x)/2` is `-u**3 + u/2`, whose roots are `0`, `+/-1/√2`;
    # the theorem finds `u = 0` and stops, and the engine published `{0, pi}` —
    # four of the SIX solutions, `sen x = 0` gives two and `sen²x = 1/2` gives the
    # other four — saying only now, after 8c680ce, that it had left them out.
    #
    # So the rational roots are divided OUT and what is left is solved exactly.
    # `-4u**3 + 2u` is `-2u(2u**2 - 1)` and `2u**2 - 1` is a quadratic this engine
    # has always done. Not a trick and not numerical: factoring by the rational
    # root, then a closed form for the rest.
    #
    # What is left when a factor of degree three or more SURVIVES is stated, not
    # hidden — `u**5 - 1/32` is one, and proving that its other four roots are
    # complex is not something this engine can do.
    if not completar:
        exactas = [mx.Num(r) for r in _divisores_racionales(polinomio, sub.name)
                   if _valor_en(polinomio, r, sub.name) == 0]
        if exactas:
            return exactas, ("solo se dan las raíces racionales exactas: el resto "
                             "depende de una cúbica o de un grado mayor y se dice "
                             "(§5.4)")
        return [], (f"el polinomio es de grado {grado} y no tiene raíces racionales: "
                    "este motor no resuelve ese caso y no va a devolver un decimal "
                    "disfrazado de solución exacta (§5.4)")

    raices, resto = [], polinomio
    for _ in range(MAX_FACTORES_RACIONALES):
        candidatas = [r for r in _divisores_racionales(resto, sub.name)
                      if _valor_en(resto, r, sub.name) == 0]
        if not candidatas:
            break
        nuevo_resto = resto
        for r in candidatas:
            cociente, residuo = P._divide_linear(
                nuevo_resto, P.add(P.variable(sub.name), P.const(-r)), sub.name)
            if cociente and P.is_zero(residuo):
                nuevo_resto = cociente
                raices.append(mx.Num(r))
        if P.degree_in(nuevo_resto, sub.name) >= P.degree_in(resto, sub.name):
            break                       # no progress: stop rather than loop (§5.5)
        resto = nuevo_resto

    grado_resto = P.degree_in(resto, sub.name)
    if grado_resto == 0:
        return _limpias(raices), ""
    if grado_resto <= 2:
        c2 = resto.get(((sub.name, 2),), Fraction(0))
        c1 = resto.get(((sub.name, 1),), Fraction(0))
        c0 = resto.get((), Fraction(0))
        discriminante = c1 * c1 - 4 * c2 * c0
        if discriminante >= 0:
            raiz = _raiz_exacta(discriminante)
            raices.extend([
                mx.Div(mx.Add(mx.Neg(mx.Num(c1)), raiz), mx.Num(2 * c2)),
                mx.Div(mx.Sub(mx.Neg(mx.Num(c1)), raiz), mx.Num(2 * c2))])
        return _limpias(raices), ""
    if grado_resto == 3:
        # A cubic always has a real root, so refusing it as «irreducible» is refusing
        # arithmetic rather than the engine. Cardano reaches it exactly, and the
        # coefficients are all `Fraction`, so `p`, `q` and the discriminant are exact
        # and the cube roots nest. `cos(3x) + cos(x) = 1` develops to `4c^3 - 2c - 1`,
        # which is one of them.
        #
        # Only `Δ > 0`. `Δ < 0` is the casus irreducibilis: three real roots that
        # Cardano only reaches through COMPLEX cube roots, and writing those down is
        # a worse answer than not writing one (§5.4). `Δ == 0` never arrives, because
        # a cubic with a repeated root has a rational one and the branch above took
        # it.
        cubica = _raiz_cubica(resto, sub.name)
        if cubica is not None:
            return _limpias(raices + cubica), ""
    return _limpias(raices), (
        f"el polinomio es de grado {grado}; se han divididos sus factores lineales "
        "y "
        f"queda uno de grado {grado_resto}, que este motor no resuelve. Las raíces "
        "racionales que se han encontrado están todas; de las demás **no puede "
        "afirmar** que sean reales, y eso no es lo mismo que decir que no lo sean "
        "(§5.4)")


def _raiz_cubica(polinomio: P.Polynomial, var: str):
    """The real root of a cubic with ``Δ > 0`` by Cardano, or ``None``.

    The depressed form ``v³ + pv + q`` has the single real root
    ``∛(-q/2 + √Δ) + ∛(-q/2 - √Δ)`` with ``Δ = (q/2)² + (p/3)³``, and going back is
    ``u = v - b/(3a)``. Written with :class:`~mvexpr.Root` so the cube roots nest
    inside the square root rather than becoming decimals, which is the whole
    difference between an exact answer and a rounded one (§5.4).
    """
    c3 = polinomio.get(((var, 3),), Fraction(0))
    c2 = polinomio.get(((var, 2),), Fraction(0))
    c1 = polinomio.get(((var, 1),), Fraction(0))
    c0 = polinomio.get((), Fraction(0))
    if c3 == 0:
        return None
    p = (3 * c3 * c1 - c2 * c2) / (3 * c3 * c3)
    q = (2 * c2 ** 3 - 9 * c3 * c2 * c1 + 27 * c3 * c3 * c0) / (27 * c3 ** 3)
    if p == 0:
        return None                    # biquadratic wearing a cubic's coat
    delta = (q / 2) ** 2 + (p / 3) ** 3
    if delta <= 0:
        return None
    raiz_delta = _raiz_exacta(delta)
    medio = mx.Num(-q / 2)
    v = mx.Add(mx.Root(3, mx.Add(medio, raiz_delta)),
               mx.Root(3, mx.Sub(medio, raiz_delta)))
    return [mx.Sub(v, mx.Num(c2 / (3 * c3)))]


#: How many times a rational root is divided out before giving up. Bounded so a
#: polynomial with a repeated root — `u**4`, whose only root is `0` with multiplicity four
#: — terminates instead of looping (§5.5).
MAX_FACTORES_RACIONALES = 8


def _limpias(raices: list[mx.Expr]) -> list[mx.Expr]:
    """Each root once, and written as plainly as it can be written.

    ``-4u**3 + 2u`` gives ``u = 0`` twice, and it is one root. The quadratic formula
    hands back ``(-0 + 0)/(-8)`` where the answer is ``1/2``, which is correct and
    unreadable, and a root that turns out to be a plain rational is rebuilt as a
    ``Num`` so that it reads as one.

    Deduplicated by EXACT value where there is one — `exact_value` knows a radical
    that is really a rational — and by the printed text otherwise, because two
    spellings of the same irrational are the same root and the student only has to
    read one of them.
    """
    vistos: dict[str, mx.Expr] = {}
    for raiz in raices:
        valor = mx.exact_value(raiz)
        if valor is not None:
            raiz = mx.Num(valor)
            clave = f"r:{valor}"
        else:
            # The quadratic and cubic formulas hand back `(-0 - sqrt(8))/2` where
            # the answer is `-sqrt(2)`, and `sqrt(19/1728)` where it is
            # `sqrt(57)/72`. Exact either way, and unreadable, which is a different
            # thing from wrong — but the student is owed the readable one.
            raiz = trig.reducir_radicales(raiz).expresion
            clave = "t:" + mx.text(raiz)
        vistos.setdefault(clave, raiz)
    return list(vistos.values())


def _divisores_racionales(polinomio: P.Polynomial, var: str) -> list[Fraction]:
    """Candidates of the rational root theorem, bounded (§5.5).

    When the constant term is zero, ``0`` is a root but the *others* are not
    found by dividing by it: ``u³ − u`` has roots 0, 1 and −1, and returning only
    ``0`` because the theorem degenerated is how half the solutions disappear.
    The polynomial is deflated by ``u`` and the theorem applied to the rest.
    """
    constante = polinomio.get((), Fraction(0))
    if constante == 0:
        desinflado: P.Polynomial = {}
        for monomio, coeficiente in polinomio.items():
            # the name must *disappear* at exponent zero, not stay as (u,0):
            # keeping it means the deflated polynomial still looks constant-free
            # and the recursion never terminates
            clave = tuple(sorted((n, g - 1) for n, g in monomio if g > 0))
            desinflado[clave] = desinflado.get(clave, Fraction(0)) + coeficiente
        if not desinflado:
            return [Fraction(0)]
        return [Fraction(0)] + _divisores_racionales(desinflado, var)
    numerador = abs(constante.numerator)
    denominador = constante.denominator
    principal = _coeficiente_principal(polinomio)
    divisores_n = _divisores(numerador)[:32]
    divisores_d = _divisores(denominador)[:32]
    # The rational root theorem says «divisor of the constant term OVER divisor of
    # the LEADING coefficient». Using only the constant gives ±1 for `1 − 8·u³`,
    # whose root is `1/2` — so `1/cos(x)^3 = 8` came back with no solutions while
    # `1/cos(x)^2 = 4` was solved, and the only difference was the degree.
    #
    # Both sets are generated: this only ADDS candidates, so it cannot lose a root
    # that was being found before, and the cap keeps the bound of §5.5.
    # `q` divides the LEADING coefficient, numerator and denominator both: for
    # `-16·u^4 + 1` that is 1, 2, 4, 8 and 16, which is where 1/2 comes from.
    denominadores_p = [1]
    if principal:
        denominadores_p = (_divisores(abs(principal.numerator))[:32]
                           + _divisores(principal.denominator)[:32]) or [1]
    salida: list[Fraction] = []
    for n in divisores_n:
        for d in divisores_d:
            for signo in (1, -1):
                valor = Fraction(signo * n, d)
                if valor not in salida:
                    salida.append(valor)
    for n in divisores_n:
        for d in denominadores_p:
            for signo in (1, -1):
                valor = Fraction(signo * n, d)
                if valor not in salida:
                    salida.append(valor)
    return salida[:256]


def _coeficiente_principal(polinomio: P.Polynomial) -> Fraction | None:
    """The coefficient of the highest total degree, or ``None`` when there is none.

    A monomial is a tuple of ``(variable, exponent)`` pairs, so the degree is the
    sum of the exponents and not the length of the tuple — which is how the first
    version of this asked for the length of a pair and got a `TypeError`.
    """
    if not polinomio:
        return None
    clave = max(polinomio, key=lambda m: (sum(g for _n, g in m), m))
    return polinomio[clave]


def _divisores(n: int) -> list[int]:
    if n == 0:
        return [1]
    salida = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            salida.extend({i, n // i})
        i += 1
    return sorted(salida)


def _valor_en(polinomio: P.Polynomial, valor: Fraction, var: str) -> Fraction:
    total = Fraction(0)
    for monomio, coeficiente in polinomio.items():
        grado = dict(monomio).get(var, 0)
        total += coeficiente * valor ** grado
    return total


def _deshacer(nombre: str, familias: list[Familia], var: str) -> list[Familia]:
    """Replace the ``u`` the polynomial was solved in by the real angle."""
    salida = []
    for familia in familias:
        base = _sustituir_u(familia.base, nombre)
        paso = _sustituir_u(familia.paso, nombre)
        salida.append(Familia(base, paso, familia.metodo, familia.hipotesis))
    return salida


def _sustituir_u(e: mx.Expr, nombre: str) -> mx.Expr:
    if isinstance(e, mx.Sym) and e.name == "u":
        return mx.Call(nombre, (mx.Sym("x"),))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sustituir_u(e.arg, nombre))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sustituir_u(e.base, nombre), _sustituir_u(e.exponent, nombre))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_sustituir_u(a, nombre) for a in e.args))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sustituir_u(e.left, nombre), _sustituir_u(e.right, nombre))
    return e


# ---------------------------------------------------------------------------
# verification: every solution goes back into the original equation
# ---------------------------------------------------------------------------


def verifica_miembro(familia: Familia, ecuacion: mx.Expr, var: str = "x") -> bool:
    """Whether one family really solves ``ecuacion``, checked by substitution.

    Public because it is the check that gives T-12 its teeth, and the calculator
    runs it as its independent path: substituting a member back into the original
    equation never looks at how the family was derived, so it cannot inherit a
    mistake from the derivation.
    """
    return not _comprobar([familia], ecuacion, var)


def _comprobar(familias: list[Familia], ecuacion: mx.Expr, var: str) -> list[str]:
    """Substitute members of each family; report the families that fail."""
    espurias: list[str] = []
    for familia in familias:
        peor = 0.0
        for k in range(-MIEMBROS_COMPROBADOS // 2, MIEMBROS_COMPROBADOS // 2 + 1):
            if k == 0:
                continue
            valor = familia.miembro(k, var)
            # No guard against a constant member: a solved family *is* a constant
            # for each k, and substituting it to get a residual is the whole
            # check. Skipping those members left _comprobar unable to flag
            # anything at all — it returned an empty list for every family,
            # including ones that do not satisfy the equation.
            resto = mx.substitute(ecuacion, var, valor)
            numerico = _evaluar(resto)
            if numerico is None:
                continue  # undefined there: not evidence either way
            escala = max(1.0, abs(numerico))
            peor = max(peor, abs(numerico) / escala)
        if peor > TOLERANCIA:
            espurias.append(f"{familia.texto(var)} no satisface la ecuación "
                            f"(residuo {peor:.3g}); se descarta como espuria")
    return espurias


def _evaluar(e: mx.Expr) -> float | None:
    """Best effort numeric value of a no-variable expression, with its error."""
    try:
        valor = mx.evaluate(e)
    except Exception:
        return None
    if valor is None:
        return None
    if abs(valor.imag) > 1e-9:
        return None
    return abs(valor.real)
