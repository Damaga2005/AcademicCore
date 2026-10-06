# SPDX-License-Identifier: MIT
"""ML-12 (§5.10.5): dimensional analysis as a universal checker of formulas and constants.

Each variable gets a dimension, written as a unit (``V``, ``kg*m/s^2``, ``Ω``, ``µF``)
or in base dimensions between brackets (``[M L^2 T^-3 I^-1]``). Then:

- :func:`dimension_de` walks an expression: sums need equal dimensions, products
  add exponents, a power needs an exact rational exponent, and the argument of
  ``exp``, ``ln``, ``sin``… must be dimensionless — the error says which term breaks
  homogeneity and what dimensions it compared;
- :func:`comprobar` checks an equation ``lhs = rhs``;
- :func:`dimension_necesaria` finds the dimension a constant must have for the
  equation to be homogeneous (``F = G·m1·m2/r^2`` → ``[G] = M⁻¹·L³·T⁻²``). Dimensions
  are linear in the unknown's exponents, so this is solving ``k·X = b`` exactly, and
  the answer is checked by substituting it back.

Exponents are fractions, so ``sqrt(L/g)`` is a time. Dimensional homogeneity is
necessary, not sufficient: a formula can pass and still be wrong by a factor 2π —
that is said in every result, not hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

BASES = ("M", "L", "T", "I", "Θ", "N", "J")
_NOMBRES_BASE = {"M": "masa", "L": "longitud", "T": "tiempo", "I": "corriente",
                 "Θ": "temperatura", "N": "cantidad de sustancia", "J": "intensidad luminosa"}
#: units the electrical table in ``units.py`` does not have
_EXTRA = {
    "K": (0, 0, 0, 0, 1, 0, 0), "mol": (0, 0, 0, 0, 0, 1, 0), "cd": (0, 0, 0, 0, 0, 0, 1),
    "T": (1, 0, -2, -1, 0, 0, 0),        # tesla
    "Wb": (1, 2, -2, -1, 0, 0, 0), "Pa": (1, -1, -2, 0, 0, 0, 0),
    "rad": (0,) * 7, "sr": (0,) * 7, "g": (1, 0, 0, 0, 0, 0, 0),
    "min": (0, 0, 1, 0, 0, 0, 0), "h": (0, 0, 1, 0, 0, 0, 0), "eV": (1, 2, -2, 0, 0, 0, 0),
}
NO_SUFICIENTE = ("la homogeneidad dimensional es necesaria, no suficiente: no detecta "
                 "factores numéricos (2, π, ½) que falten o sobren")


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


@dataclass(frozen=True)
class Dimension:
    exps: tuple[Fraction, ...] = (Fraction(0),) * 7

    def __mul__(self, otra: "Dimension") -> "Dimension":
        return Dimension(tuple(a + b for a, b in zip(self.exps, otra.exps)))

    def __truediv__(self, otra: "Dimension") -> "Dimension":
        return Dimension(tuple(a - b for a, b in zip(self.exps, otra.exps)))

    def __pow__(self, k: Fraction) -> "Dimension":
        return Dimension(tuple(a * k for a in self.exps))

    @property
    def adimensional(self) -> bool:
        return all(a == 0 for a in self.exps)

    def texto(self) -> str:
        if self.adimensional:
            return "adimensional"
        sup = str.maketrans("-0123456789/", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹ᐟ")
        partes = []
        for base, e in zip(BASES, self.exps):
            if e == 0:
                continue
            partes.append(base if e == 1 else base + str(e).translate(sup))
        return "·".join(partes)


ADIMENSIONAL = Dimension()


def _de_tupla(t) -> Dimension:
    return Dimension(tuple(Fraction(x) for x in t))


def _unidad(simbolo: str) -> Dimension:
    if simbolo in _EXTRA:
        return _de_tupla(_EXTRA[simbolo])
    from academic_core.domain.engineering import units as U

    try:
        return _de_tupla(U.parse_unit(simbolo).dimension)
    except Exception:  # noqa: BLE001
        pass
    # a prefixed extra unit: kPa, mK, mmol, ns...
    for base, dim in sorted(_EXTRA.items(), key=lambda kv: -len(kv[0])):
        if simbolo.endswith(base) and simbolo[:-len(base)] in ("k", "M", "G", "m", "u", "µ",
                                                               "n", "p", "c", "d"):
            return _de_tupla(dim)
    raise _error("BAD_UNIT", f"unidad desconocida «{simbolo}»")


_FACTOR = re.compile(r"\s*([*/])?\s*([^\s*/^]+)\s*(?:\^\s*\(?\s*(-?\d+(?:/\d+)?)\s*\)?)?")


def leer(texto: str) -> Dimension:
    """``"kg*m/s^2"``, ``"V/A"``, ``"1"`` or ``"[M L^2 T^-2]"``."""
    t = str(texto).strip()
    if t in ("", "1", "-", "adimensional"):
        return ADIMENSIONAL
    if t.startswith("["):
        d = ADIMENSIONAL
        for base, e in re.findall(r"([MLTIΘNJ]|Th)\s*(?:\^\s*(-?\d+(?:/\d+)?))?",
                                  t.strip("[]").replace("][", " ")):
            base = "Θ" if base == "Th" else base
            k = Fraction(e) if e else Fraction(1)
            d = d * Dimension(tuple(k if b == base else Fraction(0) for b in BASES))
        return d
    d = ADIMENSIONAL
    pos = 0
    while pos < len(t):
        m = _FACTOR.match(t, pos)
        if not m or m.end() == pos:
            raise _error("BAD_UNIT", f"no entiendo la unidad «{texto}»")
        signo, simbolo, e = m.groups()
        k = Fraction(e) if e else Fraction(1)
        u = _unidad(simbolo) ** k
        d = d / u if signo == "/" else d * u
        pos = m.end()
    return d


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

_CONSTANTES = {"pi", "e", "i", "π"}
_CONSERVAN = {"abs", "valor_abs", "floor", "ceil", "techo", "parte_entera"}


def dimension_de(e: mx.Expr, dims: dict[str, Dimension], trace: Trace | None = None
                 ) -> Dimension:
    trace = trace if trace is not None else Trace()
    if isinstance(e, mx.Num):
        return ADIMENSIONAL
    if isinstance(e, mx.Const):
        return ADIMENSIONAL
    if isinstance(e, mx.Sym):
        if e.name not in dims:
            raise _error("MISSING_DIMENSION", f"declara la dimensión de «{e.name}»")
        return dims[e.name]
    if isinstance(e, mx.Neg):
        return dimension_de(e.arg, dims, trace)
    if isinstance(e, (mx.Add, mx.Sub)):
        a = dimension_de(e.left, dims, trace)
        b = dimension_de(e.right, dims, trace)
        if a != b:
            raise _error("NOT_HOMOGENEOUS",
                         f"se suman «{mx.text(e.left)}» [{a.texto()}] y «{mx.text(e.right)}» "
                         f"[{b.texto()}]: no se pueden sumar magnitudes de distinta dimensión")
        return a
    if isinstance(e, mx.Mul):
        return dimension_de(e.left, dims, trace) * dimension_de(e.right, dims, trace)
    if isinstance(e, mx.Div):
        return dimension_de(e.left, dims, trace) / dimension_de(e.right, dims, trace)
    if isinstance(e, mx.Pow):
        base = dimension_de(e.base, dims, trace)
        exp_dim = dimension_de(e.exponent, dims, trace)
        if not exp_dim.adimensional:
            raise _error("NOT_HOMOGENEOUS", f"el exponente «{mx.text(e.exponent)}» tiene "
                                            f"dimensión {exp_dim.texto()}")
        if base.adimensional:
            return ADIMENSIONAL
        k = mx.exact_value(e.exponent)
        if k is None:
            raise _error("NOT_HOMOGENEOUS",
                         f"«{mx.text(e)}»: una magnitud con dimensión ({base.texto()}) solo se "
                         "eleva a un exponente racional fijo")
        return base ** Fraction(k)
    if isinstance(e, mx.Root):
        base = dimension_de(e.radicand, dims, trace)
        grado = mx.exact_value(e.degree) if isinstance(e.degree, mx.Expr) else e.degree
        return base ** (Fraction(1) / Fraction(grado))
    if isinstance(e, mx.Call):
        args = [dimension_de(a, dims, trace) for a in e.args]
        nombre = e.name
        if nombre in ("sqrt", "raiz", "raiz2", "sqr"):
            return args[0] ** Fraction(1, 2)
        if nombre in _CONSERVAN:
            return args[0]
        if nombre in ("sign", "signo"):
            return ADIMENSIONAL
        for a, d in zip(e.args, args):
            if not d.adimensional:
                raise _error("NOT_HOMOGENEOUS",
                             f"el argumento de {nombre}(…) tiene que ser adimensional y "
                             f"«{mx.text(a)}» es {d.texto()}")
        return ADIMENSIONAL
    raise _error("UNSUPPORTED", f"no sé la dimensión de «{mx.text(e)}»")


def _lados(ecuacion: str) -> tuple[mx.Expr, mx.Expr]:
    if ecuacion.count("=") != 1:
        raise _error("BAD_INPUT", "una ecuación lleva exactamente un «=»")
    izq, der = ecuacion.split("=")
    return mx.parse(izq), mx.parse(der)


@dataclass(frozen=True)
class Comprobacion:
    homogenea: bool
    izquierda: Dimension | None
    derecha: Dimension | None
    motivo: str

    def texto(self) -> str:
        if self.homogenea:
            return (f"homogénea: ambos lados son {self.izquierda.texto()} "
                    f"({NO_SUFICIENTE})")
        return f"NO homogénea: {self.motivo}"


def comprobar(ecuacion: str, dims: dict[str, Dimension], trace: Trace | None = None
              ) -> Comprobacion:
    trace = trace if trace is not None else Trace()
    izq, der = _lados(ecuacion)
    try:
        a = dimension_de(izq, dims, trace)
        b = dimension_de(der, dims, trace)
    except ValidationError as exc:
        if "NOT_HOMOGENEOUS" not in str(exc):
            raise
        motivo = str(exc).split(": ", 1)[1]
        trace.aviso("dim.fallo", motivo)
        return Comprobacion(False, None, None, motivo)
    trace.regla("dim.lados", f"[{mx.text(izq)}] = {a.texto()}; [{mx.text(der)}] = {b.texto()}",
                why="se recorre la expresión: productos suman exponentes, sumas exigen igualdad")
    if a != b:
        motivo = f"izquierda {a.texto()} ≠ derecha {b.texto()}"
        return Comprobacion(False, a, b, motivo)
    trace.aviso("dim.necesaria", NO_SUFICIENTE)
    return Comprobacion(True, a, b, "")


def dimension_necesaria(ecuacion: str, incognita: str, dims: dict[str, Dimension],
                        trace: Trace | None = None) -> Dimension:
    """The dimension ``incognita`` must have for ``ecuacion`` to be homogeneous.

    Dimensions are monomials, so ``[expr]`` is ``[incognita]^k · R`` for a rational
    ``k``; it is found by evaluating with the unknown set to two independent probe
    dimensions, then ``[incognita] = ([otro lado] / R)^(1/k)``. Checked by substitution.
    """
    trace = trace if trace is not None else Trace()
    izq, der = _lados(ecuacion)
    lado, otro = (izq, der) if incognita in mx.variables(izq) else (der, izq)
    if incognita in mx.variables(otro):
        raise _error("UNSUPPORTED", f"«{incognita}» aparece en los dos lados")
    if incognita not in mx.variables(lado):
        raise _error("BAD_INPUT", f"«{incognita}» no aparece en la ecuación")
    objetivo = dimension_de(otro, dims, trace)
    sonda = Dimension((Fraction(1),) + (Fraction(0),) * 6)       # M
    r = dimension_de(lado, {**dims, incognita: ADIMENSIONAL}, trace)
    con_sonda = dimension_de(lado, {**dims, incognita: sonda}, trace)
    k = (con_sonda / r).exps[0]
    if k == 0:
        raise _error("UNSUPPORTED", f"la dimensión de «{incognita}» no influye en la ecuación")
    resultado = (objetivo / r) ** (1 / k)
    final = comprobar(ecuacion, {**dims, incognita: resultado})
    if not final.homogenea:
        raise _error("INTERNAL", "la dimensión hallada no hace homogénea la ecuación")
    trace.regla("dim.despeje", f"[{incognita}]^{k} · {r.texto()} = {objetivo.texto()} ⇒ "
                               f"[{incognita}] = {resultado.texto()}",
                why="las dimensiones son monomios: se despeja el exponente")
    trace.verificacion("dim.sustitucion", "con esa dimensión la ecuación es homogénea")
    return resultado
