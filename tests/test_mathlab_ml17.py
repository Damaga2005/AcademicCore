# SPDX-License-Identifier: MIT
"""ML-17 (bloques 8–11): discreta, códigos e información.

Propiedades de §11.3: tabla = leyes; inclusión-exclusión = enumeración;
T(n) iterada = cerrada; contador: T(n)/g(n) → cte; PD = voraz = fuerza
bruta; RTA converge o supera D; descifrar(cifrar(x)) = x; a·a⁻¹ ≡ 1;
α^(2ᵐ−1) = 1; G·Hᵀ = 0; trama CRC con resto 0; dos subconjuntos dan el
secreto; m^(ed) ≡ m; H = log₂N; I ≥ 0; Kraft; H ≤ L̄ < H+1; C_BSC(0,5) = 0.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import codigos as K
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import discreta as D
from academic_core.domain.engineering.mathlab import informacion as N
from academic_core.domain.engineering.mathlab import verify as V


def pedir(op, entrada):
    r = ML.calcular(ML.Peticion(op, entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# bloque 8: discreta
# ---------------------------------------------------------------------------

def test_logica_tabla_y_equivalencia():
    t = D.tabla_verdad("p -> q")
    assert len(t["filas"]) == 4
    assert sum(1 for _, v in t["filas"] if v) == 3
    assert D.equivalencia("p -> q", "no p o q")["equivalentes"] is True
    assert D.equivalencia("p -> q", "q -> p")["equivalentes"] is False
    assert D.negar_cuantificador("forall", "x", "P(x)")["negacion"] == "∃x ¬(P(x))"
    r = pedir("discreta", {"calculo": "logica", "formula": "p -> q"})
    assert r.sello.verdict == V.VERIFIED


def test_conjuntos_e_inclusion_exclusion():
    r = D.operacion_conjuntos([1, 2, 3], [2, 3, 4], "union")
    assert r["elementos"] == [1, 2, 3, 4] and r["cardinal"] == 4
    r = D.potencia_n(3)
    assert r["cardinal"] == 8 and len(r["subconjuntos"]) == 8


def test_binomio_y_vandermonde():
    assert D.binomio_termino(5, 2)["C"] == 10
    assert D.vandermonde(3, 4, 2)["suma"] == math.comb(7, 2)


def test_recurrencias():
    assert D.recurrencia_lineal(1, 1, 0, 0, 1, 10)["f_n"] == 55
    assert D.teorema_maestro(2, 2, "n")["caso"].startswith("caso 2")
    assert D.teorema_maestro(2, 2, "nlogn")["caso"] == "caso 2: Θ(n·log²n)"
    assert D.teorema_maestro(4, 2, "1")["caso"].startswith("caso 1")
    with pytest.raises(Exception):
        D.teorema_maestro(2, 2, "2^n")


def test_ruina():
    r = D.ruina("1/2", 10)
    assert r["p_k"][3] == Fraction(3, 10)
    r = D.ruina("1/3", 2)
    assert r["p_k"][1] == pytest.approx(Fraction(1, 3))


def test_sumatorios():
    assert D.cerrar_sumatorio("aritmetica", 100)["suma"] == 5050
    assert D.cerrar_sumatorio("geometrica", 10, r=2)["suma"] == 2047
    assert D.cerrar_sumatorio("cuadrados", 10)["suma"] == 385


def test_mochila_y_cambio():
    assert D.mochila([2, 3, 4], [3, 4, 5], 5)["optimo"] == 7
    r = D.cambio_monedas(11, [10, 5, 2, 1])
    assert len(r["voraz"]) == r["optimo_pd"] == 2
    r = D.cambio_monedas(6, [4, 3, 1])
    assert len(r["voraz"]) == 3 and r["optimo_pd"] == 2  # voraz NO óptimo


def test_tiempo_real():
    r = D.tiempo_real([{"C": 1, "T": 4}, {"C": 2, "T": 6}])
    assert r["U"] == pytest.approx(1 / 4 + 2 / 6)
    assert r["planificable"] is True
    assert r["hiperperiodo"] == 12
    r = pedir("discreta", {"calculo": "tiempo_real",
                           "tareas": [{"C": 1, "T": 4}, {"C": 2, "T": 6}]})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# bloques 9–10: códigos (cifrado E primero)
# ---------------------------------------------------------------------------

def test_cesar_afin_vigenere_hill():
    assert K.cesar("HOLA", 3)["cifrado"] == "KROD"
    assert K.afin("HOLA", 5, 8)["cifrado"] == "RALI"
    assert K.vigenere("ATAQUE", "LIMON")["cifrado"] == "LBMEHP"
    assert K.hill("HOLA", [[3, 3], [2, 5]])["cifrado"] == "LGHW"
    with pytest.raises(Exception):
        K.afin("HOLA", 2, 0)  # gcd(2,26) ≠ 1
    r = pedir("codigos", {"calculo": "cesar", "texto": "HOLA", "k": 3})
    assert r.sello.verdict == V.VERIFIED and "KROD" in r.exacto


def test_tabla_zn_y_hash():
    assert K.tabla_zn(5)["cuerpo"] is True
    assert K.tabla_zn(4)["cuerpo"] is False
    r = K.hash_cumple(365, list(range(23)))
    assert abs(r["P"] - (1 - math.prod(1 - i / 365 for i in range(23)))) < 1e-12
    assert abs(r["montecarlo"] - r["P"]) < 0.05


def test_gf2m():
    r = K.gf2m_tabla(3, 0b1011)
    assert r["primitivo"] is True and r["orden"] == 7
    with pytest.raises(Exception):
        K.gf2m_tabla(3, 0b1111)  # reducible
    assert K.poli_gfp([1, 1, 0, 1], 2)["irreducible"] is True  # x³+x+1
    assert K.poli_gfp([1, 0, 1], 2)["irreducible"] is False  # x²+1 = (x+1)²
    r = pedir("codigos", {"calculo": "gf2m", "m": 3})
    assert r.sello.verdict == V.VERIFIED


def test_codigo_lineal_y_sindrome():
    G = [[1, 0, 0, 0, 1, 1, 0],
         [0, 1, 0, 0, 1, 0, 1],
         [0, 0, 1, 0, 0, 1, 1],
         [0, 0, 0, 1, 1, 1, 1]]
    r = K.codigo_lineal(G)
    assert (r["n"], r["k"], r["d"]) == (7, 4, 3)
    assert r["corrige"] == 1
    s = K.sindrome(r["H"], [1, 0, 0, 0, 0, 0, 0])
    assert s["corrige"] is not None
    assert K.sindrome(r["H"], r["palabras"][5])["corrige"] is None
    r = pedir("codigos", {"calculo": "codigo", "G": G})
    assert r.sello.verdict == V.VERIFIED and "[7,4,3]" in r.exacto


def test_crc_paridad_checksum():
    r = K.crc([1, 1, 0, 1], [1, 0, 1, 1])
    assert r["crc"] == [0, 0, 1]
    assert K.paridad([1, 0, 1])["palabra"] == [1, 0, 1, 0]
    assert K.checksum16([0x4500, 0x003C])["checksum"] == 0xBAC3
    r = pedir("codigos", {"calculo": "crc", "mensaje": [1, 1, 0, 1],
                          "generador": [1, 0, 1, 1]})
    assert r.sello.verdict == V.VERIFIED


def test_shamir():
    rep = K.shamir_reparto(2, 3, 11, 5, 7)
    s1 = K.shamir_reconstruye(rep["partes"][:2], 11, 2)["secreto"]
    s2 = K.shamir_reconstruye([rep["partes"][0], rep["partes"][2]], 11, 2)["secreto"]
    assert s1 == s2 == 5
    r = pedir("codigos", {"calculo": "shamir_reconstruye",
                          "partes": rep["partes"][:2], "p": 11, "t": 2})
    assert r.sello.verdict == V.VERIFIED and "= 5" in r.exacto


def test_rsa_dh():
    r = K.rsa(61, 53, 17, 65)
    assert (r["n"], r["d"], r["c"], r["m2"]) == (3233, 2753, 2790, 65)
    r = K.diffie_hellman(23, 5, 6, 15)
    assert (r["A"], r["B"], r["s"]) == (8, 19, 2)
    r = pedir("codigos", {"calculo": "rsa", "p": 61, "q": 53,
                          "e": 17, "m": 65})
    assert r.sello.verdict == V.VERIFIED and K.AVISO_PEDAGOGICO in r.avisos


def test_privacidad():
    regs = [{"edad": 20, "cp": "08001"}, {"edad": 20, "cp": "08001"},
            {"edad": 30, "cp": "08002"}]
    assert K.k_anonimato(regs, ["edad", "cp"])["k"] == 1
    r = K.dp_laplace([1.0, 2.0, 3.0], 1.0, 1.0, 1)
    assert r["b"] == pytest.approx(1.0) and len(r["ruidos"]) == 3


# ---------------------------------------------------------------------------
# bloque 11: información
# ---------------------------------------------------------------------------

def test_entropia_conjunta_kl():
    assert N.entropia(["1/2", "1/2"])["H"] == pytest.approx(1.0)
    assert N.entropia(["1", "0"])["H"] == pytest.approx(0.0)
    r = N.conjunta([["1/2", "0"], ["0", "1/2"]])
    assert r["Hxy"] == pytest.approx(1.0) and r["I"] == pytest.approx(1.0)
    r = N.divergencia(["1/2", "1/2"], ["1/4", "3/4"])
    assert r["D"] == pytest.approx(0.5 * math.log2(2) + 0.5 * math.log2(2 / 3))
    assert N.divergencia(["1/2", "1/2"], ["1", "0"])["D"] == math.inf


def test_kraft_capacidad_clave():
    assert N.kraft([2, 2, 2, 2])["K"] == 1
    assert N.kraft([1, 1, 1])["prefijo_posible"] is False
    assert N.capacidad("BSC", "0.5")["C"] == pytest.approx(0.0, abs=1e-12)
    assert N.capacidad("BEC", "0.1")["C"] == pytest.approx(0.9)
    assert N.capacidad("hartley", [1000, 20])["C"] == pytest.approx(
        1000 * math.log2(101))
    assert N.coste_clave(128)["espacio"] == 2 ** 128
    r = pedir("informacion", {"calculo": "entropia",
                              "probs": ["1/2", "1/4", "1/4"]})
    assert r.sello.verdict == V.VERIFIED and "1.5" in r.exacto
    r = pedir("informacion", {"calculo": "huffman_check",
                              "probs": {"a": "1/2", "b": "1/4", "c": "1/4"}})
    assert r.sello.verdict == V.VERIFIED


def test_ml17_pasa_el_contrato():
    for op, entrada in (
            ("discreta", {"calculo": "logica", "formula": "p -> q"}),
            ("codigos", {"calculo": "cesar", "texto": "HOLA", "k": 3}),
            ("informacion", {"calculo": "entropia"})):
        assert C.validar_forma(pedir(op, entrada)) == []
