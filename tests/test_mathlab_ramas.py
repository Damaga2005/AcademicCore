"""MATH_LAB T-11: inverse compositions and their branches.

The test that matters most is :func:`test_el_motor_no_se_traga_la_identidad_falsa`.
``asin(sin(x)) = x`` is the single most common false identity in elementary
trigonometry, and an engine that applies it confidently is worse than one that
does nothing. Here it is pinned three ways: the engine refuses, the counterexample
is computed, and the branches are checked by substitution.
"""

import cmath
import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import ramas as R
from academic_core.domain.engineering.mathlab import trig
from academic_core.domain.engineering.mathlab import verify as V


# ---------------------------------------------------------------------------
# the direction that is true everywhere gets simplified
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ["sin(asin(u))", "cos(acos(u))", "tan(atan(u))",
                                   "sinh(asinh(u))", "cosh(acosh(u))",
                                   "tanh(atanh(u))"])
def test_la_composicion_directa_se_reduce(origen):
    assert mx.text(trig.simplify(mx.parse(origen))) == "u"


@pytest.mark.parametrize("nombre,hipotesis", [
    ("sin", "arcsen"), ("cos", "arccos"), ("tan", "arctangente"),
    ("sinh", "inyectivas"), ("tanh", "arctanh"),
])
def test_cada_identidad_directa_declara_su_condicion(nombre, hipotesis):
    """§5.7: the domain travels with the rule, not forgotten in a comment."""
    texto = R.HIPOTESIS_INVERSAS[nombre]
    assert hipotesis in texto and texto.strip()


# ---------------------------------------------------------------------------
# the direction that is false must not be applied
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ["asin(sin(x))", "acos(cos(x))",
                                   "atan(tan(x))", "acosh(cosh(x))",
                                   "asinh(sinh(x))"])
def test_el_motor_no_se_traga_la_identidad_falsa(origen):
    """The bug this guards against, which the engine actually had once."""
    assert mx.text(trig.simplify(mx.parse(origen))) == texto(origen)


def test_el_motor_no_se_traga_la_identidad_falsa_tampoco_en_expansion():
    for objetivo in (trig.expand, trig.product_to_sum, trig.sum_to_product,
                     trig.reduce_powers):
        assert mx.text(objetivo(mx.parse("asin(sin(x))"))) == "asin(sin(x))"


@pytest.mark.parametrize("nombre", ["asin(sin)", "acos(cos)", "atan(tan)",
                                   "acosh(cosh)"])
def test_cada_rechazo_dice_por_que(nombre):
    """A refusal without a reason is not a refusal, it is a shrug."""
    assert R.RECHAZADAS[nombre].strip()
    evidencia = R.evidencia_global(nombre)
    assert "Por eso el motor no lo reescribe" in evidencia


def test_el_contraejemplo_es_real():
    """The evidence must be a number the checker computed, not an assertion."""
    evidencia = R.evidencia_global("asin(sin)")
    assert "en 2·π vale" in evidencia
    # independently: asin(sin(2pi)) is 0, and 2pi is not 0
    assert abs(cmath.asin(cmath.sin(2 * math.pi)).real) < 1e-12


# ---------------------------------------------------------------------------
# domains
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre,esperado", [
    ("asin", "[-1, 1]"), ("acos", "[-1, 1]"),
    ("atan", "ℝ"), ("asinh", "ℝ"),
    ("acosh", "[1, ∞)"), ("atanh", "(-1, 1)"),
])
def test_los_dominios_de_las_inversas(nombre, esperado):
    assert R.dominio_de(nombre).texto() == esperado


def test_los_dominios_no_se_confunden_entre_si():
    """``asin`` reaches ±1 and ``atanh`` does not: atanh(1) does not exist."""
    asin, atanh = R.dominio_de("asin"), R.dominio_de("atanh")
    assert asin.contiene(D.punto(Fraction(1))) is True
    assert atanh.contiene(D.punto(Fraction(1))) is False
    assert asin.contiene(D.punto(Fraction(-1))) is True
    assert atanh.contiene(D.punto(Fraction(-1))) is False


def test_un_intervalo_cerrado_incluye_el_extremo():
    intervalo = D.Intervalo(D.punto(Fraction(-1)), D.punto(Fraction(1)),
                            False, False)
    assert intervalo.contiene(D.punto(Fraction(1)))
    assert intervalo.texto() == "[-1, 1]"
    abierto = D.Intervalo(D.punto(Fraction(-1)), D.punto(Fraction(1)))
    assert abierto.contiene(D.punto(Fraction(1))) is False
    assert abierto.texto() == "(-1, 1)"


# ---------------------------------------------------------------------------
# the branches, checked by substitution
# ---------------------------------------------------------------------------


def texto(origen: str) -> str:
    return mx.text(mx.parse(origen))


def _evaluar_rama(nombre: str, rama: R.Rama, valor: float):
    """``f⁻¹(f(x))`` and the branch, both at ``valor``."""
    expresion = R._compone(mx.Sym("x"), nombre)
    return (mx.evaluate(expresion, {"x": valor}),
            mx.evaluate(rama.expresion, {"x": valor}))


def _muestras(intervalo: D.Intervalo, cuantas: int = 9) -> list[float]:
    """Points strictly inside the interval, so no branch is tested at its edge."""
    if intervalo.izq is None or intervalo.der is None:
        return [0.3, 0.9, 1.7, -0.4, -1.2]
    a, b = intervalo.izq.valor(), intervalo.der.valor()
    ancho = (b - a) or 1.0
    return [a + ancho * (i + 1) / (cuantas + 1) for i in range(cuantas)]


@pytest.mark.parametrize("nombre", ["asin(sin)", "acos(cos)", "atan(tan)",
                                   "asinh(sinh)", "atanh(tanh)"])
def test_cada_rama_satisface_la_composicion(nombre):
    """The point of the whole module: every branch, checked where it claims to hold.

    Sampling strictly inside each interval is deliberate: at the endpoints a
    branch belongs to two intervals and the check would be ambiguous.
    """
    for rama in R.ramas(nombre):
        for valor in _muestras(rama.intervalo):
            calculada, esperado = _evaluar_rama(nombre, rama, valor)
            if calculada is None or abs(calculada.imag) > 1e-9:
                continue
            escala = max(1.0, abs(esperado.real))
            assert abs(calculada.real - esperado.real) / escala < 1e-9, (
                f"{nombre}: en x={valor:.6f} la rama vale "
                f"{esperado.real:.6g} pero la composición vale "
                f"{calculada.real:.6g}  [{rama.intervalo.texto()}]")


def test_las_ramas_cubren_el_periodo_principal():
    """Between them the branches must cover a whole period, with no hole."""
    for nombre, periodo in (("asin(sin)", 2), ("acos(cos)", 2)):
        ramas = R.ramas(nombre)
        assert R.periodo_de_ramas(nombre) == Fraction(periodo)
        uniones = D.desde_intervalos([r.intervalo for r in ramas], )
        for i in range(periodo):
            punto = D.punto_pi(Fraction(i) + Fraction(1, 2))
            assert uniones.contiene(punto), f"{nombre}: hueco en {punto.texto()}"


def test_la_rama_principal_es_la_que_es_x():
    for nombre in ("asin(sin)", "acos(cos)", "atan(tan)"):
        principal = R.rama_principal(nombre)
        assert mx.text(principal.expresion) == "x"
        assert principal.nota.strip()


def test_la_tangente_abre_por_sus_polos():
    """``atan(tan(x)) = x`` is *open* at ±pi/2: tan has poles there."""
    rama = R.rama_principal("atan(tan)")
    assert rama.intervalo.abierto_izq is True
    assert rama.intervalo.abierto_der is True
    assert "polos" in rama.nota


def test_una_familia_desconocida_se_dice():
    with pytest.raises(ValueError):
        R.ramas("log(exp)")


def test_el_rechazo_cubre_todas_las_familas_peligrosas():
    for nombre in ("asin(sin)", "acos(cos)", "atan(tan)", "acosh(cosh)"):
        assert nombre in R.RECHAZADAS
    assert "asinh(sinh)" not in R.RECHAZADAS   # injective: nothing to refuse
