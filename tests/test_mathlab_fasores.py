# SPDX-License-Identifier: MIT
"""MATH_LAB T-16: phasors, and the contract with CIRCUITS_LAB."""

from __future__ import annotations

import math
from fractions import Fraction as Fr

import pytest

from academic_core.domain.engineering.mathlab import complejos as K
from academic_core.domain.engineering.mathlab import fasores as F
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError

PI = 3.141592653589793
W = mx.Num(Fr(2))          # omega = 2 rad/s


def fasor(amplitud, fase=0, frecuencia=W, etiqueta=""):
    angulo = mx.Num(Fr(fase)) if isinstance(fase, int) else fase
    return F.de_senoidal(amplitud, angulo, frecuencia, etiqueta)


# ---------------------------------------------------------------------------
# a phasor is exact where it can be
# ---------------------------------------------------------------------------


def test_un_fasor_rectangular_exacto_tiene_modulo_exacto():
    fas = F.Fasor(K.Complejo.de_texto("3+4i"), W)
    assert mx.exact_value(fas.magnitud) == 5
    assert fas.es_exacto is False       # the phase is not
    assert fas.rectangular.texto() == "3 + 4i"


def test_un_fasor_en_los_ejes_si_es_exacto_en_ambos_lados():
    assert fasor(3).es_exacto is True
    assert fasor(3, mx.Mul(mx.Num(Fr(1, 2)), mx.PI)).es_exacto is True
    fasor(3, mx.Mul(mx.Num(Fr(1, 4)), mx.PI))


def test_la_forma_rectangular_se_conserva_aunque_la_polar_seaproxime():
    """The polar form of a non-notable phase is not exact; the rectangular is.

    Dropping the exact copy would make the approximation irreversible, and the
    next thing anyone wants is the exact one back.
    """
    fas = F.Fasor(K.Complejo.de_texto("3+4i"), W)
    assert mx.exact_value(fas.rectangular.real) == 3
    assert mx.exact_value(fas.rectangular.imag) == 4


# ---------------------------------------------------------------------------
# sinusoidal signal <-> phasor
# ---------------------------------------------------------------------------


def test_el_fasor_de_una_senoidal_es_amplitud_por_la_fase():
    assert fasor(3).rectangular.texto() == "3"
    assert fasor(1, mx.Mul(mx.Num(Fr(1, 2)), mx.PI)).rectangular.texto() == "i"
    assert fasor(1, mx.PI).rectangular.texto() == "-1"


def test_el_fasor_sabe_devolver_la_senoidal():
    fas = fasor(3)
    assert fas.a_texto() == "3·cos(2*t)"
    texto, hipotesis = F.a_senoidal(fasor(3))
    assert texto == "3·cos(2*t)"
    assert any("pico" in h for h in hipotesis)


def test_sin_frecuencia_la_hipotesis_lo_dice():
    _, hipotesis = F.a_senoidal(fasor(3, frecuencia=None))
    assert any("no se indicó frecuencia" in h for h in hipotesis)


def test_la_fase_no_exacta_avisa_en_la_hipotesis():
    _, hipotesis = F.a_senoidal(F.Fasor(K.Complejo.de_texto("3+4i"), W))
    assert any("no es un múltiplo exacto de pi" in h for h in hipotesis)


def test_la_señal_se_verifica_puntualmente_contra_la_senoidal():
    """The independent path: evaluate the sinusoid and check it against the phasor.

    The conversion is the identity ``A·cos(ωt + φ) = Re(A e^(j(ωt+φ)))``, and
    checking the real part at several ``t`` is the only way to catch a φ that came
    out with the wrong sign — which is a number that looks perfectly reasonable.
    """
    # the phase is given as an exact multiple of pi where it can be, because a
    # float phase is refused on the way in and that refusal is the point
    for amplitud, fase in [(3, mx.Mul(mx.Num(Fr(1, 12)), mx.PI)),
                           (2, mx.Mul(mx.Num(Fr(1, 4)), mx.PI)),
                           (5, mx.PI),
                           (1, mx.Neg(mx.Div(mx.Num(1), mx.Num(3))))]:
        fas = fasor(amplitud, fase)
        angulo = mx.evaluate(fas.fase).real
        omega = mx.evaluate(fas.frecuencia).real
        real = mx.evaluate(fas.rectangular.real).real
        imag = mx.evaluate(fas.rectangular.imag).real
        for t in (0.0, 0.37, 1.9, -2.5):
            # A·cos(ωt+φ) and Re(A·e^(j(ωt+φ))) have to be the same number, and
            # the second form is what the phasor actually carries
            desde_fasor = real * math.cos(omega * t) - imag * math.sin(omega * t)
            desde_senoidal = amplitud * math.cos(omega * t + angulo)
            assert abs(desde_fasor - desde_senoidal) < 1e-9, (amplitud, t)


# ---------------------------------------------------------------------------
# operations, and the frequency that constrains them
# ---------------------------------------------------------------------------


def test_las_operaciones_de_fasores_son_las_de_complejos():
    v, i = fasor(3), fasor(1, mx.Mul(mx.Num(Fr(1, 2)), mx.PI))
    assert (v * i).rectangular.texto() == "3i"
    assert (v / i).rectangular.texto() == "-3i"   # 3/i is -3i
    assert (v + i).rectangular.texto() == "3 + i"   # coeficiente 1: «i», no «1i»
    assert (v - v).rectangular.texto() == "0"
    assert v.conjugado().rectangular.texto() == "3"


def test_la_suma_de_dos_senoidales_es_una_senoidal():
    texto, hipotesis = F.sumar_senoidales(
        (3, mx.ZERO, W), (1, mx.Mul(mx.Num(Fr(1, 2)), mx.PI), W))
    assert "cos" in texto
    assert hipotesis


def test_no_se_combinan_fasores_de_frecuencias_distintas():
    """The ``ωt`` was dropped when each was made, so the sum has no meaning."""
    with pytest.raises(UnsupportedError) as exc:
        fasor(1, 0, mx.Num(Fr(1))) + fasor(1, 0, mx.Num(Fr(2)))
    assert "frecuencias distintas" in str(exc.value)


def test_una_frecuencia_ausente_no_impide_combinar():
    suma = fasor(1, frecuencia=None) + fasor(1, frecuencia=None)
    assert suma.rectangular.texto() == "2"


def test_el_rms_es_el_pico_partido_por_raiz_de_dos():
    assert abs(mx.evaluate(fasor(3).rms()) - 3 / math.sqrt(2)) < 1e-12


def test_el_rms_es_solo_una_conversion_de_magnitud():
    """A phasor built from an RMS value has no √2 to remove.

    Getting this wrong shows up later as a factor of 1.41 in a power figure, which
    is why the conversion is a named function and not a convention.
    """
    fas = fasor(3)
    assert mx.text(fas.magnitud) == "3"
    assert mx.text(fas.rms()).startswith("3/")


# ---------------------------------------------------------------------------
# the interoperability contract
# ---------------------------------------------------------------------------


def test_la_convencion_de_fase_esta_declarada():
    assert F.CONVENCION_FASE == "(-pi, pi]"
    assert "(−pi, pi]" in F.__doc__ or "(-pi, pi]" in F.__doc__


def test_el_contrato_con_circuits_lab_se_verifica():
    ok, detalle = F.verifica_contrato()
    assert ok, detalle
    assert "(-pi, pi]" in detalle
    assert "ac/phasors.py" in detalle


def test_todas_las_fases_producidas_caen_en_el_intervalo_declarado():
    for k in range(1, 13):
        for signo in (1, -1):
            fas = F.Fasor(K.Complejo(mx.Num(Fr(k)), mx.Num(Fr(signo))))
            valor = mx.evaluate(fas.fase).real
            assert F.FASE_MINIMO < valor <= F.FASE_MAXIMO, (k, signo, valor)


def test_ida_y_vuelta_al_laboratorio_conserva_el_rectangular():
    from academic_core.domain.engineering.math.rational import RationalComplex

    # aligned with the axes: that is the only shape the lab can hold exactly,
    # and going through with anything else would be handing over an approximation
    original = RationalComplex(Fr(0), Fr(4))
    fasor_mathlab = F.a_fasor_del_lab(original, W)
    assert fasor_mathlab.es_exacto
    vuelto = F.del_lab(fasor_mathlab)
    assert vuelto.re == 0 and vuelto.im == 4


def test_no_se_entrega_al_laboratorio_un_fasor_irracional():
    """The lab stores rational or decimal phasors; a decimal is an approximation.

    Handing it over as if it were exact would be the mistake, so the conversion
    refuses and says which route exists instead.
    """
    fas = F.Fasor(K.Complejo(mx.Num(Fr(3)), mx.Num(Fr(4))), W)
    assert fas.es_exacto is False
    with pytest.raises(UnsupportedError) as exc:
        F.del_lab(fas)
    assert "no es de los que el laboratorio" in str(exc.value)


def test_no_se_convierte_un_fasor_decimal_del_laboratorio():
    from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
    from decimal import Decimal

    with pytest.raises(UnsupportedError) as exc:
        F.a_fasor_del_lab(DecimalComplex(Decimal(3), Decimal(4)))
    assert "aproximación" in str(exc.value)


def test_la_fase_aproximada_declara_su_error():
    fas = F.Fasor(K.Complejo.de_texto("3+4i"), W)
    aprox = F.aproxima(fas)
    assert abs(aprox.valor.real - math.atan(4 / 3)) < 1e-12
    assert aprox.error > 0 or aprox.valor.real == 0
    assert "sensibilidad" in aprox.metodo


def test_un_fasor_con_la_fase_irracional_no_tiene_ida_y_vuelta_exacta():
    """and the module says so rather than rounding on the way out."""
    fas = F.Fasor(K.Complejo.de_texto("3+4i"), W)
    assert fas.es_exacto is False


def test_la_division_por_el_cero_dice_que_es_el_cero():
    with pytest.raises(ZeroDivisionError):
        fasor(1) / fasor(0, frecuencia=None)
