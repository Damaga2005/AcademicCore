# SPDX-License-Identifier: MIT
"""Trigonometric equations, checked by substitution and against a numeric root scan.

Found 2026-10-05 by generating equations at random: the Pythagorean rewrite turned
``cos(x - pi/4)**2`` into ``1 - sen(x)**2`` — dropping the argument — so
``cos(x - pi/4)**2 = 1`` published ``x = 0 + 2k·pi`` and ``x = pi + 2k·pi``; and every
case reported families that fail the equation as «espurias» while still publishing
them as solutions.
"""
from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import mvexpr as mx


def _raices_numericas(ecuacion: str) -> list[float]:
    izquierda, derecha = E.separar(ecuacion)
    g = mx.parse(f"({izquierda}) - ({derecha})")

    def valor(x):
        return mx.valor_real(g, {"x": x})

    raices, n = [], 20000
    anterior = (0.0, valor(0.0))
    for i in range(1, n + 1):
        x = 2 * math.pi * i / n
        y = valor(x)
        x0, y0 = anterior
        if y is not None and y0 is not None:
            if y0 == 0:
                raices.append(x0)
            elif y0 * y < 0 and abs(y - y0) < 1:
                lo, hi = x0, x
                for _ in range(60):
                    m = (lo + hi) / 2
                    if (valor(m) < 0) == (valor(lo) < 0):
                        lo = m
                    else:
                        hi = m
                raices.append((lo + hi) / 2)
        anterior = (x, y)
    return raices


def _miembros(resolucion) -> list[float]:
    salida = []
    for familia in resolucion.familias:
        for k in range(-4, 5):
            v = mx.valor_real(familia.miembro(k, "x"), {})
            if v is not None:
                salida.append(v)
    return salida


@pytest.mark.parametrize("ecuacion", [
    "cos(x-pi/4)^2 = 1", "sin(x+pi/3)^2 = 1/4", "cos(x)^2 = 1/2",
    "2*cos(x-pi/4)^2 = 2", "1/2*cos(3*x-pi/4)^2 = 1/2", "cos(2*x+pi/6)^2 = 3/4",
    "sin(x)^2 = 1/4", "2*cos(x) = -sqrt(3)", "sin(2*x) = 1/2",
])
def test_cada_familia_cumple_y_no_falta_ninguna_raiz(ecuacion):
    resolucion = E.resolver(ecuacion)
    izquierda, derecha = E.separar(ecuacion)
    g = mx.parse(f"({izquierda}) - ({derecha})")
    miembros = _miembros(resolucion)
    assert miembros, ecuacion
    for m in miembros:
        assert abs(mx.valor_real(g, {"x": m})) < 1e-9, (ecuacion, m)
    for r in _raices_numericas(ecuacion):
        assert any(abs(r - m) < 1e-6 for m in miembros), (
            ecuacion, r, [f.texto("x") for f in resolucion.familias])


def test_cos_desplazado_al_cuadrado_conserva_la_fase():
    resolucion = E.resolver("cos(x-pi/4)^2 = 1")
    miembros = _miembros(resolucion)
    assert any(abs(m - math.pi / 4) < 1e-12 for m in miembros)
    assert not any(abs(m) < 1e-12 for m in miembros)   # x = 0 is NOT a solution


@pytest.mark.parametrize("ecuacion", [
    "2*cos(x+pi/6)^2+2*cos(x+pi/3)^2 = 0",
    "cos(x)+sin(2*x+pi/6)^2 = 1/3",
])
def test_lo_que_no_sabe_resolver_lo_dice_y_no_publica_familias_falsas(ecuacion):
    resolucion = E.resolver(ecuacion)
    izquierda, derecha = E.separar(ecuacion)
    g = mx.parse(f"({izquierda}) - ({derecha})")
    for m in _miembros(resolucion):
        assert abs(mx.valor_real(g, {"x": m})) < 1e-9, (ecuacion, m)
    if not resolucion.familias:
        assert resolucion.refusos
