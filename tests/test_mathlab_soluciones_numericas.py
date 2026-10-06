# SPDX-License-Identifier: MIT
"""Equations and inequalities with no closed form: answered numerically, certified.

Until 2026-10-06 they were refused («no se resuelve todavía»). A quintic in sin(x)
has no formula by radicals; its solutions are still real numbers, and bracketing
each one by bisection on a sign change (Bolzano) gives it with a proven error.
"""
from __future__ import annotations

import math
import random

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx


@pytest.mark.parametrize("ecuacion", [
    "tan(3*x+pi/6)+cos(3*x)^2 = 0",
    "sin(x)^5 - sin(x) + 1/3 = 0",
    "1/2*cos(x)+2*tan(2*x) = -1/2",
])
def test_toda_solucion_de_un_periodo_esta_y_cumple(ecuacion):
    r = E.resolver(ecuacion)
    izquierda, derecha = E.separar(ecuacion)
    g = mx.parse(f"({izquierda}) - ({derecha})")
    for raiz in r.aproximadas:
        assert raiz.certificada
        a = mx.valor_real(g, {"x": raiz.valor - raiz.error})
        b = mx.valor_real(g, {"x": raiz.valor + raiz.error})
        assert a * b <= 0 or abs(mx.valor_real(g, {"x": raiz.valor})) < 1e-12
    miembros = [r_.valor for r_ in r.aproximadas]
    for familia in r.familias:
        miembros.append(mx.valor_real(familia.miembro(0, "x"), {}) % r.periodo)
    # a sign scan finds nothing the answer misses
    n = 20000
    for i in range(n):
        x0, x1 = r.periodo * i / n, r.periodo * (i + 1) / n
        y0, y1 = mx.valor_real(g, {"x": x0}), mx.valor_real(g, {"x": x1})
        if y0 is not None and y1 is not None and y0 * y1 < 0 and abs(y1 - y0) < 1:
            assert any(x0 - 1e-9 <= m % r.periodo <= x1 + 1e-9 for m in miembros), (x0, x1)


def test_sin_soluciones_reales_se_certifica():
    r = E.resolver("2*cos(x+pi/6)^2+2*cos(x+pi/3)^2 = 0")
    assert r.sin_soluciones_reales
    assert r.texto("x") == "no hay soluciones reales"


@pytest.mark.parametrize("texto", ["sin(x)^5+cos(x)^3 > 0.1234567",
                                   "tan(x)^5 + tan(x) <= 1",
                                   "sin(x)^5 - sin(x) + 1/3 >= 0"])
def test_la_inecuacion_sin_ceros_exactos_se_resuelve_numericamente(texto):
    r = ML.calcular(ML.Peticion("resolver_inequidad", texto))
    assert "extremos numéricos" in r.exacto
    s = I.resolver_inequidad_numerica(texto)
    op, iz, de = I._separa(texto)
    g = mx.parse(f"({iz}) - ({de})")
    rng = random.Random(3)
    for _ in range(2000):
        x = rng.uniform(-10, 10)
        v = mx.valor_real(g, {"x": x})
        if v is None or abs(v) < 1e-7:
            continue
        assert s.contiene_valor(x) == {">": v > 0, ">=": v >= 0,
                                       "<": v < 0, "<=": v <= 0}[op], (texto, x, v)


def test_una_raiz_en_el_inicio_del_periodo_no_se_escapa_y_sale_exacta():
    """x = 0 cambia de signo justo a la izquierda de 0 en coma flotante; 0 y pi
    son exactas y se prueban sustituyendo (2026-10-06)."""
    r = E.resolver("tan(3*x-pi/4)+sin(x) = -1")
    textos = [f.texto("x") for f in r.familias]
    assert any(t.startswith("x = 0 ") for t in textos), textos
    assert any(t.startswith("x = π ") for t in textos), textos
    assert all(abs(a.valor) > 1e-6 and abs(a.valor - math.pi) > 1e-6 for a in r.aproximadas)


def test_dos_senoidales_que_se_cancelan_suman_cero():
    from academic_core.domain.engineering.mathlab import fasores as Fa

    texto, _h = Fa.sumar_senoidales((1, mx.parse("0"), 50), (1, mx.PI, 50))
    assert texto == "0"


@pytest.mark.parametrize("texto,valor", [
    ("int(sin(2*x/x), x, 3, 13)", 10 * math.sin(2)),
    ("int(atan(x^2-x^2), x, -3, 3)", 0.0),
    ("int(ln(x/(2*x)), x, 3, 5)", 2 * math.log(0.5)),
])
def test_un_integrando_constante_disfrazado_no_rompe_la_calculadora(texto, valor):
    r = ML.calcular(ML.Peticion("integrar", texto))
    assert abs(r.aproximado.real - valor) < 1e-12
