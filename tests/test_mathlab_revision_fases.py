# SPDX-License-Identifier: MIT
"""Revisión de fases anteriores (2026-10-07, junto con ML-9).

Cada prueba fija un fallo encontrado por un barrido de entradas sobre todas las
operaciones registradas: o un resultado vacío o falso, o un error interno
(TypeError, IndexError…) donde tocaba un resultado o un rechazo con su motivo.
"""

from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.errors import ValidationError


def pedir(op, entrada):
    r = ML.calcular(ML.Peticion(op, entrada))
    assert C.validar_forma(r) == [], (op, C.validar_forma(r))
    return r


# ---------------------------------------------------------------------------
# integrar / impropia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hasta", ["oo", "inf", "∞"])
def test_integrar_hasta_infinito_ya_no_lee_o_por_o(hasta):
    r = pedir("integrar", {"integrando": "x*exp(-2*x)", "var": "x", "desde": "0", "hasta": hasta})
    assert "1/4" in str(r.exacto) and r.sello.verdict == V.VERIFIED


@pytest.mark.parametrize("f,a,b,esperado", [
    ("k*x*(1-x)", "0", "1", "1/6·k"),
    ("x^2", "0", "a", "1/3·a³"),
    ("k*exp(-k*x)", "0", "c", "-exp(-c·k) + 1"),
])
def test_integrar_con_parametros_ya_no_dice_que_no_esta_acotada(f, a, b, esperado):
    r = pedir("integrar", {"integrando": f, "var": "x", "desde": a, "hasta": b})
    assert str(r.exacto) == esperado
    assert r.sello.verdict == V.VERIFIED
    assert "no está acotado" not in r.traza.to_text()


def test_una_integral_divergente_da_el_veredicto_como_resultado():
    r = pedir("integrar", {"integrando": "1/x", "var": "x", "desde": "0", "hasta": "1"})
    assert r.aproximado is None and "diverge" in str(r.exacto)


def test_impropia_da_el_valor_con_el_integrador_de_ml2():
    r = pedir("impropia", {"expr": "x^3*exp(-x/2)/96", "a": "0", "b": "oo"})
    assert "vale 1" in str(r.exacto)
    r = pedir("impropia", {"expr": "x^5*exp(-3*x)", "a": "0", "b": "oo"})
    assert "40/243" in str(r.exacto)


# ---------------------------------------------------------------------------
# un segundo camino que discrepa es un sello, no una excepción (ML-8)
# ---------------------------------------------------------------------------


def test_ml8_devuelve_el_sello_discrepa(monkeypatch):
    from academic_core.domain.engineering.mathlab import laplace as LP

    def roto(*_a, **_k):
        raise ValidationError("DISCREPANT: plantado")
    monkeypatch.setattr(LP, "transformada", roto)
    r = pedir("laplace", "t*u(t-1)")
    assert r.sello.verdict == V.DISCREPANT and "plantado" in r.sello.detail


# ---------------------------------------------------------------------------
# entradas que reventaban con errores internos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op,entrada,motivo", [
    ("extremos_absolutos", {"expr": "x^2", "a": "x^2", "b": "2"}, "no es un número"),
    ("impropia", {"expr": "1/x^2", "a": "x^2", "b": "oo"}, "no es un número"),
    ("taylor", {"expr": "exp(x)", "centro": "x^2", "orden": 3, "x0": "1/2"}, "no es un número"),
    ("teorema", {"teorema": "rolle", "expr": "x^2-4*x", "a": "x^2", "b": "4"}, "no es un número"),
    ("a_trozos", {"izquierda": "a*x+b", "derecha": "x^2", "punto": "y", "parametros": ["a", "b"]},
     "no es un número"),
    ("riemann", {"expr": "1/x", "a": "0", "b": "1", "n": 10}, "no está acotada"),
    ("aplicacion_integral", {"tipo": "area", "f": "k*x", "g": "x", "a": "0", "b": "2"},
     "letras sin valor"),
    ("estudio", {"expr": "k*x"}, "letras sin valor"),
    ("tfc", {"f": "exp(-t^2)", "desde": "k*x", "hasta": "x^2"}, "letras sin valor"),
    ("gradiente", {"expr": "0"}, "no tiene variables"),
    ("multivar", {"calculo": "criticos", "expr": "x-x", "vars": ["x", "y"]}, "constante"),
    ("caracteristicas", "1/0", "división por cero"),
    ("inversa", {"expr": "x^3+x"}, "falta el dato"),
    ("cola_mm1", {"lambda": "abc", "mu": 2}, "no es un número válido"),
    ("markov", {"P": [["1/2", "1/2"], ["1/3", "2/3"]], "simular": None}, "None"),
])
def test_entradas_invalidas_se_rechazan_con_su_motivo(op, entrada, motivo):
    with pytest.raises(ValidationError, match=motivo):
        ML.calcular(ML.Peticion(op, entrada))


def test_un_extremo_que_se_anula_es_un_numero():
    r = pedir("extremos_absolutos", {"expr": "x^2", "a": "x-x", "b": "2"})
    assert "mínimo absoluto 0" in str(r.exacto)


def test_riemann_con_una_singularidad_evitable():
    r = pedir("riemann", {"expr": "sin(x)/x", "a": "0", "b": "1", "n": 10})
    assert "izquierda" in str(r.exacto)


# ---------------------------------------------------------------------------
# evaluar
# ---------------------------------------------------------------------------


def test_evaluar_con_valores_en_texto_es_exacto():
    r = pedir("evaluar", {"expr": "x^2+y", "valores": {"x": 3, "y": "2/3"}})
    assert r.exacto == "29/3" or str(r.exacto) == "29/3"
    assert r.sello.verdict == V.VERIFIED


def test_evaluar_con_letras_sin_valor_sustituye_lo_que_hay():
    r = pedir("evaluar", {"expr": "k*x", "valores": {"x": 3}})
    assert mx.text(r.exacto_expr) == "3*k" or str(r.exacto) == "3·k"
    assert r.sello.verdict == V.VERIFIED
    assert any("sin valor" in a for a in r.avisos)


def test_evaluar_donde_no_esta_definida_es_un_error_no_un_resultado_vacio():
    with pytest.raises(ValidationError, match="no está definida"):
        ML.calcular(ML.Peticion("evaluar", {"expr": "1/(x-1)", "valores": {"x": 1}}))


# ---------------------------------------------------------------------------
# el contrato distingue un dato mal escrito de un fallo del motor
# ---------------------------------------------------------------------------


def test_un_fallo_interno_sigue_saliendo_como_tal():
    def roto(_p):
        raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")
    try:
        C.registrar("__prueba_rota", roto)
        with pytest.raises(TypeError):
            ML.calcular(ML.Peticion("__prueba_rota", {"x": 1}))
    finally:
        C._operaciones.pop("__prueba_rota", None)
