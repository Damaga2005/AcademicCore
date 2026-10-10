# SPDX-License-Identifier: MIT
"""MATH_LAB T-15: complex numbers, Euler's identity and De Moivre.

What this module is for
-----------------------

Everything in trigonometry that needs an angle to be *something else than a real
number* comes through here: the exponential form of a sinusoid, a phasor, the
``n``-th roots of a complex number, the argument of a quotient. The engine already
does real trigonometry exactly, and this module is the bridge — it does not
re-derive any identity, it *uses* the exact engine through the substitution
``e^(ix) = cos(x) + i·sin(x)`` and gives back exact results.

The three decisions worth stating up front
------------------------------------------

**A complex number is a pair of exact expressions, not a float pair.** ``3+4i`` is
``(Num(3), Num(4))`` and its magnitude is ``5``, exactly. A module that stored
floats would answer ``5.000000000000001`` and would have no way to notice it was
wrong.

**The four forms are equalities, checked, not conventions.** Going from
rectangular to polar and back has to return what it started with; a module that
merely offers the two conversions has no way to catch a sign error in the branch
of ``arg``.

**``arg`` is not ``atan2`` and the difference is not cosmetic.** The principal
argument is in ``(-pi, pi]``, and ``arg(-1 - 0i)`` is ``pi`` while ``arg(-1 + 0i)``
is ``-pi``. Picking the wrong one silently changes every downstream phase, which
is exactly what T-16 exists to get right.

Branches
--------

``Log`` and ``arg`` are the multivalued ones, and the module says which branch it
is rather than pretending there is only one. ``Log(z) = ln|z| + i·(arg z + 2k·pi)``
for every integer ``k``, and a caller who wants the principal value has to say so.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.errors import UnsupportedError

#: the imaginary unit, as a **display** token only.
#:
#: It is deliberately not an expression. ``Complejo`` stores its two parts as real
#: expressions and never multiplies by an ``i``, because ``i·i = -1`` is not the
#: ring law: writing ``4i`` as ``Mul(4, i)`` and letting the ordinary product see
#: it gives ``i·i = i·i`` and a modulus of ``sqrt(16·i·i)``. The pairing rule
#: ``(a+bi)(c+di) = (ac-bd) + (ad+bc)i`` is where the ``-1`` belongs.
UNIDAD = "i"

#: how many turns of ``arg`` :func:`log_multi` reports by default
RAMAS_POR_DEFECTO = 5


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the number
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Complejo:
    """``real + imag·i``, both exact.

    The type is deliberately thin. Almost everything interesting is a question
    about the pair, and answering it as a method keeps the arithmetic in one place
    instead of spread over free functions that each rebuild the pair.
    """

    real: mx.Expr
    imag: mx.Expr = mx.ZERO

    def __post_init__(self) -> None:
        for parte in (self.real, self.imag):
            if not isinstance(parte, mx.Expr):
                raise sin_refuso(
                    f"una parte del complejo tiene que ser una expresión exacta, "
                    f"y llegó {type(parte).__name__}. Un par de flotadores no es un "
                    "número complejo en este motor: es una aproximación con "
                    "aspecto de número (§5.1)")

    # --- construction ----------------------------------------------------

    @classmethod
    def real_(cls, valor) -> "Complejo":
        return cls(mx.Num(valor) if isinstance(valor, Fraction) or isinstance(
            valor, int) else valor, mx.ZERO)

    @classmethod
    def de_texto(cls, texto: str) -> "Complejo":
        """``3+4i``, ``-i``, ``2``, ``3-4i`` (rectangular, exactly) o cualquier
        expresión: ``(1+i)^5``, ``(3+4i)/(1-2i)``, ``exp(i*pi/3)``, ``abs(3+4i)``.

        Antes solo se leía el literal rectangular: lo demás se trataba como una
        expresión real con una variable «i» y se devolvía sin calcular, y al quitar
        los «*» ``i*pi`` se convertía en ``ipi`` (se leía p·i)."""
        import re as _re

        limpio = texto.replace(" ", "")
        if _re.fullmatch(r"[-+]?[0-9./]*[-+]?[0-9./]*\*?[ij]?", limpio) and limpio:
            plano = limpio.replace("*", "")
            for sufijo in ("i", "j"):
                if plano.endswith(sufijo):
                    real, imag = _partes(plano[:-1])
                    return cls(real, imag)
        z = cls.de_expresion(mx.parse(limpio.replace("j", "i") if "j" in limpio
                                      and "i" not in limpio else limpio))
        return cls(_fuerte(z.real), _fuerte(z.imag))

    @classmethod
    def de_expresion(cls, e: mx.Expr) -> "Complejo":
        """Evalúa exactamente una expresión con la unidad imaginaria ``i``."""
        if isinstance(e, mx.Const) and e.name == "i":
            return cls(mx.ZERO, mx.Num(Fraction(1)))
        if isinstance(e, (mx.Num, mx.Const)):
            return cls(e, mx.ZERO)
        if isinstance(e, mx.Sym):
            raise sin_refuso(f"«{e.name}» es una variable: un complejo tiene que ser un número")
        if isinstance(e, mx.Neg):
            z = cls.de_expresion(e.arg)
            return cls(_normaliza(mx.Neg(z.real)), _normaliza(mx.Neg(z.imag)))
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            a, b = cls.de_expresion(e.left), cls.de_expresion(e.right)
            return (a + b if isinstance(e, mx.Add) else a - b if isinstance(e, mx.Sub)
                    else a * b if isinstance(e, mx.Mul) else a / b)
        if isinstance(e, mx.Pow):
            base = cls.de_expresion(e.base)
            k = mx.exact_value(e.exponent)
            if k is not None and Fraction(k).denominator == 1:
                return base ** int(k)
            return potencia_principal(base, e.exponent)
        if isinstance(e, mx.Root):
            return potencia_principal(cls.de_expresion(e.radicand),
                                      mx.Num(Fraction(1, e.degree)))
        if isinstance(e, mx.Call) and len(e.args) == 1:
            z = cls.de_expresion(e.args[0])
            nombre = e.name
            if nombre in ("abs", "valor_abs"):
                return cls(z.modulo(), mx.ZERO)
            if nombre == "exp":
                # e^(a+bi) = e^a·(cos b + i·sen b)
                w = euler(z.imag)
                ea = mx.Call("exp", (z.real,))
                return cls(_normaliza(mx.Mul(ea, w.real)), _normaliza(mx.Mul(ea, w.imag)))
            if nombre in ("sin", "sen"):
                return seno(z)
            if nombre == "cos":
                return coseno(z)
            if nombre in ("tan", "tg"):
                return tangente(z)
            if nombre in ("ln", "log"):
                lg = log_multi(z, 0)
                return cls(lg.modulo, lg.angulo)
            if nombre in ("sqrt", "raiz", "raiz2"):
                return potencia_principal(z, mx.Num(Fraction(1, 2)))
            if z.es_real():
                return cls(_normaliza(mx.Call(nombre, (z.real,))), mx.ZERO)
        raise sin_refuso(f"no sé evaluar «{mx.text(e)}» como número complejo")

    # --- arithmetic -------------------------------------------------------

    def __add__(self, otro: "Complejo") -> "Complejo":
        return Complejo(_suma(self.real, otro.real), _suma(self.imag, otro.imag))

    def __sub__(self, otro: "Complejo") -> "Complejo":
        return Complejo(_suma(self.real, mx.Neg(otro.real)),
                        _suma(self.imag, mx.Neg(otro.imag)))

    def __mul__(self, otro: "Complejo") -> "Complejo":
        """``(a+bi)(c+di) = (ac - bd) + (ad + bc)i``."""
        return Complejo(
            _suma(_producto(self.real, otro.real), mx.Neg(_producto(self.imag, otro.imag))),
            _suma(_producto(self.real, otro.imag), _producto(self.imag, otro.real)))

    def __truediv__(self, otro: "Complejo") -> "Complejo":
        """Multiply by the conjugate over the squared modulus.

        The modulus squared is exact and non-negative, so the division stays exact
        whenever the numerator is — which is the whole reason to do it this way
        rather than dividing real parts.
        """
        if _es_cero(otro.real) and _es_cero(otro.imag):
            raise ZeroDivisionError("no se puede dividir por el complejo cero")
        conjugado = Complejo(otro.real, mx.Neg(otro.imag))
        numerador = self * conjugado
        denominador = _suma(_producto(otro.real, otro.real),
                            _producto(otro.imag, otro.imag))
        return Complejo(_normaliza(mx.Div(numerador.real, denominador)),
                        _normaliza(mx.Div(numerador.imag, denominador)))

    def conjugado(self) -> "Complejo":
        return Complejo(self.real, mx.Neg(self.imag))

    def __pow__(self, entero: int) -> "Complejo":
        """Integer powers only.

        A complex power with an arbitrary exponent is multivalued — the log is —
        and a function that quietly took the principal branch and returned a
        single value would be answering a different question than the one asked.
        Refusing is the honest move; :func:`potencia_principal` is there for the
        case where the principal value is genuinely wanted.
        """
        if not isinstance(entero, int):
            raise sin_refuso(
                f"las potencias enteras son unívocas; «{entero}» no lo es. Para "
                "una potencia con exponente arbitrario hay que elegir rama, y eso "
                "se hace con potencia_principal (§5.4)")
        if entero == 0:
            return Complejo.uno()
        if entero < 0:
            return Complejo.uno() / (self ** -entero)
        resultado = Complejo.uno()
        for _ in range(entero):
            resultado = resultado * self
        return resultado

    @classmethod
    def uno(cls) -> "Complejo":
        return cls(mx.Num(Fraction(1)), mx.ZERO)

    # --- reading ---------------------------------------------------------

    @property
    def es_real(self) -> bool:
        return _es_cero(self.imag)

    def modulo(self) -> mx.Expr:
        """``|z| = sqrt(a² + b²)``, exact.

        A non-negative square root of an exact number is still exact, so the
        perfect-square case is worth reducing: ``|3 + 4i|`` is ``5`` and not
        ``sqrt(3² + 4²)``. Leaving the radical in place is not wrong, but it is
        the kind of thing a student would read as «this module cannot do 3-4-5».
        """
        radicando = T.simplify(_suma(_producto(self.real, self.real),
                                    _producto(self.imag, self.imag)))
        raiz = _raiz_exacta(radicando)
        if raiz is not None:
            return mx.Num(raiz)
        return mx.Root(2, radicando)

    def argumento(self, *, principal: bool = True) -> mx.Expr:
        """``arg z``, in ``(-pi, pi]`` when principal.

        ``atan2`` is the whole content here, and the branch is what matters:
        ``arg(-1 - 0i)`` is ``pi`` and ``arg(-1 + 0i)`` is ``-pi``, and the two
        spellings are the same point on the circle. Getting it wrong does not
        produce an error later — it produces a phase that is off by a full turn,
        which is exactly the kind of mistake T-16 exists to prevent.
        """
        if _es_cero(self.real) and _es_cero(self.imag):
            raise ZeroDivisionError("el argumento del cero no está definido")
        if _es_cero(self.real):
            # the argument of a pure imaginary number is ±pi/2, and the sign is
            # the sign of the imaginary part: arg(-i) is not the same as arg(i)
            medio = mx.Mul(mx.Num(Fraction(1, 2)), mx.PI)
            return medio if not _es_negativo(self.imag) else mx.Neg(medio)
        if _es_cero(self.imag):
            return mx.PI if _es_negativo(self.real) else mx.ZERO
        angulo = mx.Call("atan", (mx.Div(self.imag, self.real),))
        if principal:
            return _principal(angulo, self)
        # NOT principal means «the same angle named with a whole turn more», which
        # is what the name has always promised. Returning the unfolded atan(y/x)
        # is not that: with a negative real part it is not an argument of this z at
        # all — its cosine has the wrong sign — so it was neither principal nor a
        # turn away, just wrong.
        vuelta = mx.Add(_principal(angulo, self), mx.Mul(mx.Num(Fraction(2)), mx.PI))
        return vuelta if _es_negativo(_principal(angulo, self)) else \
            mx.Sub(_principal(angulo, self), mx.Mul(mx.Num(Fraction(2)), mx.PI))

    def texto(self) -> str:
        """``3 + 4i``, ``-1/2 + 1/2·√3·i``, ``π·i``: notación legible; un coeficiente
        imaginario no numérico va separado de la i («√3i» se lee como √(3i))."""
        def unidad(magnitud_expr: mx.Expr) -> str:
            valor = mx.exact_value(magnitud_expr)
            if valor == 1:
                return UNIDAD
            m = mx.pretty(magnitud_expr)
            if valor is not None:
                return m + UNIDAD
            if any(c in m for c in "+-−") and not m.startswith("("):
                m = f"({m})"
            return f"{m}·{UNIDAD}"

        if _es_cero(self.imag):
            return mx.pretty(self.real)
        negativo = _es_negativo(self.imag)
        magnitud = _normaliza(mx.Neg(self.imag)) if negativo else self.imag
        parte_i = unidad(magnitud)
        if _es_cero(self.real):
            return ("-" if negativo else "") + parte_i
        return mx.pretty(self.real) + (" - " if negativo else " + ") + parte_i

    def __str__(self) -> str:   # pragma: no cover - convenience only
        return self.texto()


def _partes(cuerpo: str) -> tuple[mx.Expr, mx.Expr]:
    """Split the body of a complex literal into its real and imaginary parts.

    The four shapes are genuinely different and all four appear in exercises:
    ``3+4`` has both parts, ``4`` is *imaginary only* (which is not the same as
    the real number 4), ``+4i``/``-4i`` set the imaginary sign, and an empty body
    is ``1i``. Reading ``-2i`` as the real ``-2`` is the mistake this avoids.
    """
    from fractions import Fraction as F

    if cuerpo in ("", "+"):
        return mx.ZERO, mx.Num(F(1))
    if cuerpo == "-":
        return mx.ZERO, mx.Num(F(-1))
    if cuerpo[0] in "+-" and (cuerpo[1] in "+-" or not cuerpo[1].isdigit()):
        # «-2i» is imaginary, not real
        return mx.ZERO, mx.Num(F(cuerpo))
    for separador, signo in (("+", F(1)), ("-", F(-1))):
        if separador in cuerpo[1:]:
            cabeza, _, cola = cuerpo.rpartition(separador)
            # «1+i» has an empty tail after the sign: that is +1, not nothing
            coeficiente = F(cola) if cola else F(1)
            if not cabeza:
                return mx.ZERO, mx.Num(signo * coeficiente)
            return mx.Num(F(cabeza)), mx.Num(signo * coeficiente)
    return mx.ZERO, mx.Num(F(cuerpo))


def _principal(angulo: mx.Expr, z: "Complejo") -> mx.Expr:
    """Fold an ``atan`` into ``(-pi, pi]`` knowing which quadrant ``z`` is in.

    There are TWO quadrants with a negative real part, and they fold in opposite
    directions. The comment that used to sit here said «atan(y/x) is in
    (pi/2, pi) here», and that is only true in the THIRD quadrant: there y/x is
    positive. In the SECOND one y/x is negative, atan lands in (-pi/2, 0), and
    the principal argument is that PLUS pi, not minus. Folding both the same way
    put ``arg(-3 + 4i)`` at -4.069 instead of +2.214 — outside the principal
    range and a whole turn from the truth, which is exactly the failure this
    module's own docstring warns about.
    """
    if _es_negativo(z.real):
        if _es_negativo(z.imag):        # third quadrant: y/x > 0, fold down
            return mx.Sub(angulo, mx.PI)
        return mx.Add(angulo, mx.PI)    # second quadrant: y/x < 0, fold up
    return angulo


def _raiz_exacta(radicando: mx.Expr) -> Fraction | None:
    """The positive square root of a perfect square, or ``None``."""
    valor = mx.exact_value(radicando)
    if valor is None or valor < 0:
        return None
    numerador = math.isqrt(valor.numerator)
    denominador = math.isqrt(valor.denominator)
    if numerador ** 2 != valor.numerator or denominador ** 2 != valor.denominator:
        return None
    return Fraction(numerador, denominador)


def _es_cero(e: mx.Expr) -> bool:
    return e == mx.ZERO or mx.exact_value(e) == 0


def _es_negativo(e: mx.Expr) -> bool:
    valor = mx.evaluate(e)
    return valor is not None and abs(valor.imag) < 1e-12 and valor.real < 0


def _fuerte(e: mx.Expr) -> mx.Expr:
    """Plegado verificado (``_presentable``) más trigonometría notable: 0·ln 4 → 0,
    √4 → 2, raiz(16, 4) → 2, atan(1) → π/4, cos(π/3) → 1/2. Solo para presentar:
    _presentable no acepta una forma que cambie el valor en puntos sembrados."""
    try:
        from academic_core.domain.engineering.mathlab.calculators import _presentable
        from academic_core.domain.engineering.mathlab.trace import Trace as _T
        for _ in range(2):
            e = _presentable(T.simplify(e), _T(), profunda=True)
        return _normaliza(e)
    except Exception:  # noqa: BLE001
        return _normaliza(e)


def _normaliza(e: mx.Expr) -> mx.Expr:
    """Fold the arithmetic exactly, then the trigonometry.

    ``trig.simplify`` only knows trigonometric rules, so ``3 + 4`` came back as
    ``Add(3, 4)`` and every modulus printed its radicand unevaluated. The exact
    rational normal form is what folds arithmetic; ``pi`` and the functions become
    atoms in it, which is exactly right — they are not what is being summed.
    """
    e = T.simplify(e)
    try:
        q = P.as_poly(e)
    except Exception:       # a shape the normal form does not accept: leave it
        return e
    if q is None:
        return e
    return T.simplify(P.to_expr(q))


def _suma(a: mx.Expr, b: mx.Expr) -> mx.Expr:
    return _normaliza(mx.Add(a, b))


def _producto(a: mx.Expr, b: mx.Expr) -> mx.Expr:
    return _normaliza(mx.Mul(a, b))


# ---------------------------------------------------------------------------
# T-15: the four forms, and the identities between them
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Polar:
    """``r·e^(i·theta)``: the trigonometric and exponential forms at once."""

    modulo: mx.Expr
    angulo: mx.Expr

    def texto(self) -> str:
        m, a = mx.pretty(_fuerte(self.modulo)), mx.pretty(_fuerte(self.angulo))
        return f"{m}·(cos({a}) + i·sen({a}))"

    def como_exponencial(self) -> str:
        return (f"{mx.text(self.modulo)}·e^(i·{mx.text(self.angulo)})")

    def a_rectangular(self) -> Complejo:
        """``r(cos θ + i sin θ)``, through the exact engine — not through a float."""
        return Complejo(
            T.simplify(mx.Mul(self.modulo, mx.Call("cos", (self.angulo,)))),
            T.simplify(mx.Mul(self.modulo, mx.Call("sin", (self.angulo,)))))

    def a_complejo(self) -> Complejo:
        return self.a_rectangular()


def a_polar(z: Complejo, *, principal: bool = True) -> Polar:
    return Polar(z.modulo(), z.argumento(principal=principal))


def a_rectangular(modulo, angulo) -> Complejo:
    """The inverse. Round-tripping has to return what it started with, and there is
    a test that says so for every notable angle — a module that offers two
    conversions without that test has no way to catch a sign error."""
    return Polar(modulo, angulo).a_rectangular()


def euler(angulo: mx.Expr) -> Complejo:
    """``e^(i·x) = cos x + i·sin x``: the identity everything else is built on.

    Normalised, so ``euler(pi)`` is ``-1`` rather than ``cos(pi) + sin(pi)i``.
    The identity is the definition either way, but a form that still carries the
    functions in it has not been evaluated, and the whole point of coming through
    the exact engine is that it has been.
    """
    return Complejo(_normaliza(mx.Call("cos", (angulo,))),
                    _normaliza(mx.Call("sin", (angulo,))))


def de_moivre(modulo, angulo, n: int) -> tuple[Complejo, ...]:
    """The ``n``-th roots of ``r·e^(iθ)``: ``r^(1/n)·e^(i(θ+2kπ)/n)``.

    Every root, and they are genuinely distinct — an ``n``-th power has ``n`` of
    them, not one and not "the principal one". A function returning only the
    principal root would answer a different question than the one asked.
    """
    if n <= 0:
        raise sin_refuso(f"«{n}» no es un número de raíces: tiene que ser positivo")
    valor = mx.exact_value(modulo)
    raiz = (mx.Num(Fraction(1)) if valor == 1 else
            mx.Root(n, modulo))          # the unit root has a modulus of one
    raices = tuple(Complejo(
        _normaliza(mx.Mul(raiz, mx.Call("cos", (desplazado,)))),
        _normaliza(mx.Mul(raiz, mx.Call("sin", (desplazado,)))))
        for desplazado in (_ramas(angulo, n)))
    return tuple(Complejo(_fuerte(r.real), _fuerte(r.imag)) for r in raices)


def _ramas(angulo: mx.Expr, n: int) -> list[mx.Expr]:
    """``(θ + 2kπ)/n`` for ``k = 0 … n-1``."""
    from fractions import Fraction as F

    salida = []
    for k in range(n):
        numerador = mx.Add(angulo, mx.Mul(mx.Num(F(2 * k)), mx.PI))
        salida.append(_normaliza(mx.Div(numerador, mx.Num(F(n)))))
    return salida


def log_multi(z: Complejo, k: int = 0) -> Polar:
    """``Log z = ln|z| + i·arg z``, on the branch ``k``.

    ``k = 0`` is the principal branch. The other values are not decoration: they
    are the other logarithms of the same number, and a caller who does not know
    which one they want is asking a question with several answers.
    """
    from fractions import Fraction as F

    angulo = z.argumento()
    if k:
        angulo = mx.Add(angulo, mx.Mul(mx.Num(F(2 * k)), mx.PI))
    return Polar(mx.Call("ln", (z.modulo(),)), angulo)


def potencia_principal(z: Complejo, exponente) -> Complejo:
    """``z^w = e^(w·Log z)`` on the principal branch, and the branch is named.

    Con Log z = ln|z| + i·θ y w = c + d·i: z^w = e^(c·ln|z| − d·θ)·(cos(d·ln|z| + c·θ)
    + i·sen(…)). Antes faltaba el factor |z|^w: √(−4) daba i en lugar de 2i."""
    w = exponente if isinstance(exponente, Complejo) else Complejo.de_expresion(
        exponente if isinstance(exponente, mx.Expr) else mx.Num(Fraction(exponente)))
    lg = log_multi(z)
    ln_r, theta = lg.modulo, lg.angulo
    mod = mx.Call("exp", (mx.Sub(mx.Mul(w.real, ln_r), mx.Mul(w.imag, theta)),))
    if _es_cero(w.imag):
        mod = mx.Pow(z.modulo(), w.real)        # |z|^c, que se simplifica mejor
    ang = mx.Add(mx.Mul(w.imag, ln_r), mx.Mul(w.real, theta))
    return Complejo(_fuerte(mx.Mul(mod, mx.Call("cos", (ang,)))),
                    _fuerte(mx.Mul(mod, mx.Call("sin", (ang,)))))


# ---------------------------------------------------------------------------
# complex trigonometry
# ---------------------------------------------------------------------------


def seno(z: Complejo) -> Complejo:
    """``sin(a+bi) = sin a·cosh b + i·cos a·sinh b``.

    The decomposition rather than ``(e^(iz) - e^(-iz))/(2i)``, and the reason is
    that the decomposition is exact in both halves: ``cosh`` and ``sinh`` are
    polynomial expressions in ``e``, so no logarithm or branch is involved and the
    result is a pair of exact expressions for every ``z``.
    """
    return Complejo(
        _normaliza(mx.Mul(_sen(z.real), mx.Call("cosh", (z.imag,)))),
        _normaliza(mx.Mul(_cos(z.real), mx.Call("sinh", (z.imag,)))))


def coseno(z: Complejo) -> Complejo:
    """``cos(a+bi) = cos a·cosh b - i·sin a·sinh b``."""
    return Complejo(
        _normaliza(mx.Mul(_cos(z.real), mx.Call("cosh", (z.imag,)))),
        _normaliza(mx.Neg(mx.Mul(_sen(z.real), mx.Call("sinh", (z.imag,))))))


def tangente(z: Complejo) -> Complejo:
    """``tan z = sin z / cos z``, and the pole is the pole of the quotient."""
    s, c = seno(z), coseno(z)
    if _es_cero(c.real) and _es_cero(c.imag):
        raise sin_refuso(
            "la tangente no está definida en ese punto: el coseno se anula, que "
            "es un polo (§5.4)")
    return s / c


def _sen(e: mx.Expr) -> mx.Expr:
    return mx.Call("sin", (e,))


def _cos(e: mx.Expr) -> mx.Expr:
    return mx.Call("cos", (e,))


# ---------------------------------------------------------------------------
# verification by an independent route
# ---------------------------------------------------------------------------


def verifica_euler(angulo: mx.Expr, puntos=8) -> tuple[bool, str]:
    """Euler checked numerically at several angles, as a second opinion.

    Not the proof — the proof is that ``euler`` *is* the identity, written down.
    This is what catches a printer or an evaluator that disagrees with the
    definition, which is a different failure and worth catching.
    """
    z = euler(angulo)
    fallos: list[str] = []
    for k in range(1, puntos + 1):
        x = k * math.pi / (puntos + 1)
        if abs(mx.evaluate(z.real, {"x": x}) - math.cos(x)) > 1e-12 or \
                abs(mx.evaluate(z.imag, {"x": x}) - math.sin(x)) > 1e-12:
            fallos.append(f"x = {x:.4f}")
    if fallos:
        return False, "; ".join(fallos)
    return True, f"{puntos} puntos de control, todos de acuerdo"


def verifica_de_moivre(modulo, angulo, n: int) -> tuple[bool, str]:
    """Raise each root to the ``n``-th and check it lands on the original."""
    fallos: list[str] = []
    objetivo = Complejo(
        mx.Mul(modulo, mx.Call("cos", (angulo,))),
        mx.Mul(modulo, mx.Call("sin", (angulo,))))
    esperado_real = mx.evaluate(objetivo.real)
    esperado_imag = mx.evaluate(objetivo.imag)
    for raiz in de_moivre(modulo, angulo, n):
        elevado = raiz ** n
        if abs(mx.evaluate(elevado.real) - esperado_real) > 1e-9 or \
                abs(mx.evaluate(elevado.imag) - esperado_imag) > 1e-9:
            fallos.append(raiz.texto())
    if fallos:
        return False, "; ".join(fallos)
    return True, f"las {n} raíces, elevadas a {n}, vuelven al número"


__all__ = [
    "UNIDAD", "RAMAS_POR_DEFECTO", "Complejo", "Polar", "a_polar",
    "a_rectangular", "euler", "de_moivre", "log_multi", "potencia_principal",
    "seno", "coseno", "tangente", "verifica_euler", "verifica_de_moivre",
    "sin_refuso",
]
