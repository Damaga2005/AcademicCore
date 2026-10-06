# SPDX-License-Identifier: MIT
"""ML-12: aritmética entera con trazas, contrastada con fuerza bruta y pow()."""
from __future__ import annotations

import math
import random

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import enteros as Z


def test_bezout_y_inverso_contra_python():
    rng = random.Random(1)
    for _ in range(500):
        a, n = rng.randint(-300, 300), rng.randint(2, 300)
        b = Z.euclides_extendido(a, n)
        assert b.d == math.gcd(a, n) and a * b.s + n * b.t == b.d
        if math.gcd(a, n) == 1:
            assert Z.inverso_modular(a, n) == pow(a, -1, n)
        else:
            with pytest.raises(Exception):
                Z.inverso_modular(a, n)


def test_potencia_por_cuadrados_sucesivos_es_pow():
    rng = random.Random(2)
    for _ in range(300):
        a, e, n = rng.randint(-99, 99), rng.randint(0, 10**9), rng.randint(1, 10**6)
        assert Z.potencia_modular(a, e, n) == pow(a, e, n)


def test_congruencias_y_chino_contra_fuerza_bruta():
    rng = random.Random(3)
    for _ in range(300):
        a, b, n = rng.randint(-50, 50), rng.randint(-50, 50), rng.randint(1, 60)
        fuerza = tuple(x for x in range(n) if (a * x - b) % n == 0)
        assert Z.congruencia_lineal(a, b, n).soluciones == fuerza
    for _ in range(300):
        ms = [rng.randint(1, 30) for _ in range(rng.randint(1, 3))]
        rs = [rng.randint(-40, 40) for _ in ms]
        mcm = math.lcm(*ms)
        fuerza = [x for x in range(mcm) if all((x - r) % m == 0 for r, m in zip(rs, ms))]
        c = Z.teorema_chino(rs, ms)
        assert (c.resto is None) == (not fuerza)
        if fuerza:
            assert c.resto == fuerza[0] and c.modulo == mcm


def test_raiz_primitiva_y_orden():
    assert Z.raiz_primitiva(7) == 3 and Z.orden(3, 7) == 6
    assert Z.raiz_primitiva(8) is None          # ℤ₈* no es cíclico
    assert Z.es_cuerpo(13) and not Z.es_cuerpo(12)


@pytest.mark.parametrize("entrada,texto", [
    ({"calculo": "euclides", "a": 240, "b": 46}, "mcd(240, 46) = 2 = 240·(-9) + 46·(47)"),
    ({"calculo": "inverso", "a": 3, "n": 11}, "3⁻¹ ≡ 4 (mod 11)"),
    ({"calculo": "chino", "restos": [2, 3, 2], "modulos": [3, 5, 7]}, "x ≡ 23 (mod 105)"),
])
def test_la_calculadora_escribe_el_resultado_y_los_pasos(entrada, texto):
    r = ML.calcular(ML.Peticion("modular", entrada))
    assert r.exacto == texto
    assert len(r.traza.steps) >= 2
