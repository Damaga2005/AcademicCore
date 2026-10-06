# SPDX-License-Identifier: MIT
"""ML-12: motor lineal con el cuerpo como parámetro (ℚ, GF(p)), contrastado con
Laplace y con fuerza bruta sobre GF(p)."""
from __future__ import annotations

import itertools
import random
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import lineal as L


def test_el_cuerpo_cambia_la_respuesta():
    A = [[2, 1], [1, 2]]
    Q, K3 = L.cuerpo("Q"), L.cuerpo("GF(3)")
    assert L.determinante(L.matriz(A, Q), Q) == 3
    assert L.determinante(L.matriz(A, K3), K3) == 0
    assert L.rango(L.matriz(A, K3), K3) == 1


def test_gf_no_primo_se_rechaza():
    with pytest.raises(Exception):
        L.cuerpo("GF(4)")


def test_determinante_y_rango_contra_laplace_y_fuerza_bruta():
    rng = random.Random(3)
    for _ in range(200):
        n, m = rng.randint(1, 4), rng.randint(1, 4)
        A = [[rng.randint(-3, 3) for _ in range(m)] for _ in range(n)]
        for nombre in ("Q", "GF(2)", "GF(5)"):
            K = L.cuerpo(nombre)
            M = L.matriz(A, K)
            if n == m:
                assert L.determinante(M, K) == L._laplace(M, K)
            if nombre != "Q":
                p = int(nombre[3:-1])
                ceros = sum(1 for v in itertools.product(range(p), repeat=m)
                            if all(sum(a * x for a, x in zip(f, v)) % p == 0 for f in A))
                assert p ** (m - L.rango(M, K)) == ceros


def test_inversa_y_sistemas():
    Q = L.cuerpo("Q")
    A = L.matriz([[1, 2], [3, 4]], Q)
    assert L.producto(A, L.inversa(A, Q), Q) == [[1, 0], [0, 1]]
    s = L.resolver_sistema(L.matriz([[1, 1], [2, 2]], Q), [Fraction(1), Fraction(3)], Q)
    assert s.tipo == "incompatible"
    s = L.resolver_sistema(L.matriz([[1, 1], [2, 2]], Q), [Fraction(1), Fraction(2)], Q)
    assert s.tipo == "compatible indeterminado" and len(s.nucleo) == 1


@pytest.mark.parametrize("entrada,texto", [
    ({"calculo": "determinante", "matriz": [[2, 1], [1, 2]], "cuerpo": "GF(3)"}, "det = 0"),
    ({"calculo": "rango", "matriz": [[1, 2], [2, 4]]}, "rango = 1"),
])
def test_la_calculadora(entrada, texto):
    r = ML.calcular(ML.Peticion("lineal", entrada))
    assert r.exacto == texto
    assert len(r.traza.steps) >= 1
