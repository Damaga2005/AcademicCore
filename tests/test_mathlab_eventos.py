# SPDX-License-Identifier: MIT
"""ML-12: simulador sembrado de eventos — Markov exacto + simulación, M/M/1, Monte Carlo."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import eventos as E

P3 = [["1/2", "1/2", 0], ["1/4", "1/2", "1/4"], [0, "1/3", "2/3"]]


def test_splitmix64_valor_de_referencia_y_reproducible():
    assert E.Generador(0)._siguiente() == 0xE220A8397B1DCDAF
    a = [E.Generador(42).uniforme() for _ in range(1)]
    assert a == [E.Generador(42).uniforme()]


def test_estacionaria_exacta_y_simulacion_calibrada():
    m = E.markov(P3, pasos=3, simular=50000, semilla=7)
    assert m.estacionaria == (F(2, 9), F(4, 9), F(1, 3))
    assert m.distribucion_n == (F(5, 16), F(23, 48), F(5, 24))
    assert m.coincide
    # over many seeds the 4σ rule must not fire spuriously
    assert sum(not E.markov(P3, simular=20000, semilla=s).coincide for s in range(30)) == 0


def test_cadena_reducible_y_matriz_no_estocastica():
    assert E.markov([[1, 0], [0, 1]]).estacionaria is None
    with pytest.raises(Exception, match="NOT_STOCHASTIC"):
        E.markov([["1/2", "1/3"], [0, 1]])


def test_mm1_cerca_de_la_teoria_e_inestable_rechazada():
    r = E.cola_mm1(0.5, 1.0, 50000, 3)
    assert abs(r.simulado_L - 1) < 0.1 and abs(r.simulado_W - 2) < 0.2
    with pytest.raises(Exception, match="UNSTABLE"):
        E.cola_mm1(1.0, 1.0)


def test_montecarlo_pi_cuartos_dentro_de_su_error():
    est = E.montecarlo(lambda g: 1.0 if g.uniforme() ** 2 + g.uniforme() ** 2 < 1 else 0.0,
                       100000, semilla=5)
    assert abs(est.valor - 0.7853981633974483) < 4 * est.error_tipico


def test_calculadora_usa_la_semilla_de_la_peticion():
    entrada = {"P": P3, "simular": 10000}
    a = ML.calcular(ML.Peticion("markov", entrada, semilla=11))
    b = ML.calcular(ML.Peticion("markov", entrada, semilla=11))
    c = ML.calcular(ML.Peticion("markov", entrada, semilla=12))
    assert a.exacto == b.exacto != c.exacto
    assert a.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("cola_mm1", {"lambda": 1, "mu": 2, "clientes": 5000}))
    assert "teoría L" in r.exacto
