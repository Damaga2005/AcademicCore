# SPDX-License-Identifier: MIT
"""graficas.caracteristicas, checked against a numeric scan (found 2026-10-05).

Before: any curve with a constant radical (``3·cos(x) − sqrt(3)/2``) had no
characteristics at all; an empty list of zeros meant both «none» and «unknown»;
partial lists of zeros were printed as complete; sen(x)/x at 0 was called a pole;
and the lists of poles were taken from a window that was not one period.
"""
from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import graficas as G
from academic_core.domain.engineering.mathlab import mvexpr as mx


def k(texto):
    return G.caracteristicas(mx.parse(texto))


@pytest.mark.parametrize("texto", ["3*cos(x)-sqrt(3)/2", "tan(x+pi/2)-sqrt(3)/2",
                                   "cos(3*x+pi/6)^2-sqrt(3)/2"])
def test_un_radical_constante_no_impide_describir_la_curva(texto):
    c = k(texto)
    assert c.ceros or c.ceros_aproximados


def test_una_lista_de_ceros_incompleta_lo_dice():
    c = k("1/2*cos(3*x)+tan(x+pi/2)")
    assert not c.ceros_completos
    assert len(c.ceros_aproximados) == 2
    assert "sin forma exacta" in c.texto()


def test_una_lista_completa_no_lleva_aviso():
    c = k("sin(x)")
    assert c.ceros_completos and not c.ceros_aproximados


def test_seno_entre_x_tiene_un_hueco_con_limite_uno():
    c = k("sin(x)/x")
    assert [(p.texto(), v) for p, v in c.huecos] == [("0", 1.0)]
    assert "hueco removible en 0: el límite es 1" in c.texto()


def test_los_polos_se_dan_en_un_periodo_y_se_dice_que_se_repiten():
    c = k("1/(1/2*tan(2*x-pi/4))")
    assert [p.texto() for p in c.discontinuidades] == ["1/8·π", "3/8·π"]
    assert [p.texto() for p, _ in c.huecos] == ["3/8·π"]
    assert "se repiten cada 1/2·pi" in c.texto()


def test_un_hueco_no_se_lista_como_cero():
    assert k("1/tan(x)").ceros_aproximados == ()
