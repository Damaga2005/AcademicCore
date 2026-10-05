# SPDX-License-Identifier: MIT
"""Raíces y factorización racionales de `polynomials`, contrastadas con SymPy.

Hallado el 2026-10-05 al auditar el módulo contra una referencia externa:
`raices_racionales` no devolvía la raíz 0 cuando el término independiente era 0
(sustituía el 0 por un 1 para poder tomar divisores) y `factorizar` dejaba una raíz
doble como factor simple más un resto.
"""
from __future__ import annotations

import random
from fractions import Fraction

import pytest
import sympy as sp

from academic_core.domain.engineering.mathlab import polynomials as PL

x = sp.symbols("x")


def _poli(coef):
    return sum(c * x**i for i, c in enumerate(coef))


@pytest.mark.parametrize("coef", [[0, 1], [0, 0, 1], [0, 6, -4, -4, -1, -5],
                                  [0, -5, -5, -1, 3, 1], [0, -2, 1], [0, 0, -3, 1]])
def test_la_raiz_cero_aparece_cuando_el_termino_independiente_es_cero(coef):
    obtenidas = {sp.Rational(r.numerator, r.denominator)
                 for r in PL.raices_racionales(PL.normalizar(coef))}
    esperadas = set(sp.roots(sp.Poly(_poli(coef), x), filter="Q"))
    assert obtenidas == esperadas
    assert 0 in obtenidas


def test_raices_racionales_coinciden_con_sympy_en_polinomios_aleatorios():
    rng = random.Random(7)
    for _ in range(200):
        coef = [rng.randint(-6, 6) for _ in range(rng.randint(2, 6))]
        coef[-1] = coef[-1] or 1
        obtenidas = {sp.Rational(r.numerator, r.denominator)
                     for r in PL.raices_racionales(PL.normalizar(coef))}
        assert obtenidas == set(sp.roots(sp.Poly(_poli(coef), x), filter="Q")), coef


def test_factorizar_saca_x_con_su_multiplicidad():
    # el "1" final es el cociente constante que el módulo siempre ha devuelto
    assert PL.factorizar(PL.normalizar([0, 0, 1]))[0] == ("x", 2)
    assert PL.factorizar(PL.normalizar([1, -2, 1]))[0] == ("(x - 1)", 2)


def test_el_producto_de_los_factores_devueltos_es_el_polinomio():
    rng = random.Random(11)
    for _ in range(100):
        coef = [rng.randint(-5, 5) for _ in range(rng.randint(2, 6))]
        coef[-1] = coef[-1] or 1
        original = _poli(coef)
        producto = sp.Integer(1)
        for texto, exponente in PL.factorizar(PL.normalizar(coef)):
            producto *= sp.sympify(texto.replace("^", "**")) ** exponente
        # el resto irreducible se devuelve sin factor numérico delante: lo único
        # que puede diferir es una constante multiplicativa
        cociente = sp.simplify(original / producto)
        assert cociente.is_number and cociente != 0, (coef, cociente)
