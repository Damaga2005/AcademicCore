# SPDX-License-Identifier: MIT
"""Demostraciones asistidas: punto fijo, desigualdades, subespacios,
invariancia e inducción (§4.8, §15.2.7)."""

from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import demuestra as D
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("demuestra", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def test_punto_fijo():
    r = D.punto_fijo("x/2", "x", 0, 1)
    assert r["c"] == pytest.approx(0.0, abs=1e-9)
    r = pedir({"calculo": "punto_fijo", "expr": "x/2", "a": 0, "b": 1})
    assert r.sello.verdict == V.VERIFIED


def test_punto_fijo_sin_contencion():
    # 2x sale de [0, 1]: sin teorema y se dice
    with pytest.raises(Exception):
        D.punto_fijo("2*x", "x", 0, 1)


def test_desigualdad_probada_y_refutada():
    r = D.desigualdad("x", "log(1+x)", "x", 0, 2)
    assert r["veredicto"] == "cierta"
    r = D.desigualdad("x^2", "2*x", "x", 0, 3)
    assert r["veredicto"] == "falsa" and r["contraejemplo"] == pytest.approx(1.0)
    r = pedir({"calculo": "desigualdad", "f": "exp(x)", "g": "1+x",
               "a": 0, "b": 1})
    assert r.sello.verdict == V.VERIFIED and "cierta" in r.exacto


def test_subespacio_si_y_no():
    assert D.subespacio(["x+y"], ["x", "y"])["es"] is True
    r = D.subespacio(["x-1"], ["x", "y"])
    assert r["es"] is False and "0" in r["motivo"]
    with pytest.raises(Exception):
        D.subespacio(["x^2+y"], ["x", "y"])
    r = pedir({"calculo": "subespacio", "conds": ["x+y"], "vars": ["x", "y"]})
    assert r.sello.verdict == V.VERIFIED


def test_invariante():
    assert D.invariante([[0, 1, 1], [1, 0, 1], [1, 1, 2]],
                        [[1, 1, 0], [0, 0, 1]])["es"] is True
    # el nilpotente manda e1 al 0, que está en todo subespacio: SÍ invariante
    assert D.invariante([[0, 1], [0, 0]], [[1, 0]])["es"] is True
    # el intercambio saca (1,0) de su recta: NO invariante
    assert D.invariante([[0, 1], [1, 0]], [[1, 0]])["es"] is False
    r = pedir({"calculo": "invariante",
               "matriz": [[0, 1, 1], [1, 0, 1], [1, 1, 2]],
               "F": [[1, 1, 0], [0, 0, 1]]})
    assert r.sello.verdict == V.VERIFIED


def test_induccion_suma():
    r = D.induccion("n*(n+1)/2 = 0", "n", 1, termino="n")
    assert r["veredicto"] == "probada"
    r = D.induccion("n^2 = 0", "n", 1, termino="2*n-1")
    assert r["veredicto"] == "probada"
    r = pedir({"calculo": "induccion", "igualdad": "n*(n+1)/2 = 0",
               "var": "n", "base": 1, "termino": "n"})
    assert r.sello.verdict == V.VERIFIED


def test_induccion_falsa_y_no_polinomica():
    r = D.induccion("2^n = 0", "n", 1, termino="2^n")
    assert r["veredicto"] in ("falsa_en_base", "falsa_en_paso")
    with pytest.raises(Exception):
        # Bernoulli: paso no polinómico (indicio, no prueba)
        D.induccion("(1+x)^n = 0", "n", 0, termino="(1+x)^n")


def test_demuestra_pasa_el_contrato():
    for entrada in ({"calculo": "punto_fijo", "expr": "x/2"},
                    {"calculo": "desigualdad", "f": "x", "g": "0"},
                    {"calculo": "subespacio", "conds": ["x"]},
                    {"calculo": "induccion", "igualdad": "n = n"}):
        assert C.validar_forma(pedir(entrada)) == []
