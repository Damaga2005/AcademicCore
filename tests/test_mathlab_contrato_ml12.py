# SPDX-License-Identifier: MIT
"""ML-12 (§5.9): prueba de contrato — cada operación registrada devuelve un resultado
con la forma prometida, y los plug-ins solo verifican lo que les corresponde."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V

EJEMPLOS = {
    "derivar": "x^3+2*x",
    "gradiente": {"expr": "x^2*y"},
    "simplificar": "sin(x)^2+cos(x)^2",
    "transformar": {"expr": "sin(x+y)", "objetivo": "expandir"},
    "modular": {"calculo": "inverso", "a": 3, "n": 11},
    "lineal": {"calculo": "determinante", "matriz": [[1, 2], [3, 4]]},
    "racional": {"expr": "(s^2-1)/(s-1)", "var": "s"},
    "evaluar": {"expr": "x^2", "valores": {"x": 3}},
    "igualdad": {"a": "(x^2-1)/(x-1)", "b": "x+1"},
    "integrar": {"integrando": "x^2", "var": "x", "desde": "0", "hasta": "1"},
    "resolver": "2*x-4=0",
    "resolver_inequidad": "sin(x) > 1/2",
    "ramas": "asin(sin)",
    "aproximar": {"expr": "sqrt(2)"},
    "complejo": "(1+i)^2",
    "fasor": {"expr": "3*cos(2*t+pi/4)"},
    "caracteristicas": "x^2-1",
    "distribucion": {"calculo": "derivada", "expr": "u(t)-u(t-1)"},
    "dimensional": {"ecuacion": "P = V^2/R", "dimensiones": {"P": "W", "V": "V", "R": "Ω"}},
    "comprobar_gradiente": {"f": "x*y"},
    "markov": {"P": [["1/2", "1/2"], ["1/3", "2/3"]], "simular": 5000},
    "cola_mm1": {"lambda": 1, "mu": 2, "clientes": 2000},
    "grafo": {"calculo": "bfs", "aristas": [["a", "b"], ["b", "c"]]},
    "huffman": {"probabilidades": {"a": "1/2", "b": "1/4", "c": "1/4"}},
    "convencion": {"tipo": "db", "razon": 2, "convencion": "20log10"},
    "limite": {"expr": "sin(x)/x", "punto": "0"},
    "estudio": {"expr": "x^3-3*x"},
    "extremos_absolutos": {"expr": "x^2", "a": "-1", "b": "2"},
    "soluciones": {"expr": "x^3+x-1"},
    "impropia": {"expr": "1/x^2", "a": "1", "b": "oo"},
    "serie": {"calculo": "convergencia", "termino": "1/n^2"},
    "taylor": {"expr": "exp(x)", "centro": "0", "orden": 3, "x0": "1/2"},
    "primitiva": {"expr": "(x+3)/(x^2-3*x+2)"},
    "tfc": {"f": "exp(-t^2)", "desde": "0", "hasta": "x^2"},
    "inversa": {"expr": "x^3+x", "y0": "2"},
    "a_trozos": {"izquierda": "a*x+b", "derecha": "x^2", "punto": "1",
                 "parametros": ["a", "b"], "derivable": True},
    "teorema": {"teorema": "rolle", "expr": "x^2-4*x", "a": "0", "b": "4"},
    "riemann": {"expr": "x^2", "a": "0", "b": "1", "n": 10},
    "metodo_numerico": {"metodo": "newton", "expr": "x^2-2", "x0": 1},
    "aplicacion_integral": {"tipo": "area", "f": "x^2", "g": "x", "a": "0", "b": "2"},
    "algebra": {"calculo": "autovalores", "matriz": [[2, 1], [1, 2]]},
    "gamma": {"expr": "5"},
    "multivar": {"calculo": "criticos", "expr": "x^2+x*y+y^2", "vars": ["x", "y"]},
    "vectorial": {"calculo": "potencial", "campo": ["2*x*y", "x^2"]},
    "multiple": {"calculo": "iterada", "expr": "x*y", "limites": [["y", "0", "x"], ["x", "0", "1"]]},
    "espacios": {"calculo": "suma_interseccion",
                 "F": [[1, 0, 1, 0], [0, 1, 0, 1]],
                 "G": [[1, 1, 0, 0], [1, 0, 1, 0]]},
}


def test_todas_las_operaciones_tienen_ejemplo():
    assert set(C.operaciones()) <= set(EJEMPLOS), set(C.operaciones()) - set(EJEMPLOS)


@pytest.mark.parametrize("operacion", sorted(EJEMPLOS))
def test_forma_del_resultado(operacion):
    if operacion not in C.operaciones():
        pytest.skip("operación no registrada")
    try:
        r = ML.calcular(ML.Peticion(operacion, EJEMPLOS[operacion]))
    except Exception as exc:  # the example itself must be valid
        pytest.fail(f"{operacion}: {exc}")
    assert C.validar_forma(r) == [], (operacion, C.validar_forma(r))


def test_un_plug_in_solo_mira_sus_operaciones_y_no_asciende_el_sello():
    vistos = []

    def bode(resultado):
        vistos.append(resultado.operacion)
        return (True, "coincide")

    try:
        C.registrar_verificador("circuitos", bode, operaciones=("racional",))
        ML.calcular(ML.Peticion("derivar", "x^2"))
        assert vistos == []
        r = ML.calcular(ML.Peticion("racional", {"expr": "(s^2-1)/(s-1)", "var": "s"}))
        assert vistos == ["racional"] and "circuitos" in r.sello.detail
        # a numeric-only answer stays numeric-only even if a plug-in agrees
        C.registrar_verificador("todo", lambda r: (True, "sí"))
        n = ML.calcular(ML.Peticion("igualdad", {"a": "sin(x)^2 + cos(x)^2", "b": "1"}))
        assert n.sello.verdict == V.NUMERIC_ONLY
    finally:
        C.withdraw_verificador("circuitos")
        C.withdraw_verificador("todo")


def test_un_plug_in_roto_o_que_no_aplica_no_verifica_nada():
    try:
        C.registrar_verificador("no_aplica", lambda r: None)
        n = ML.calcular(ML.Peticion("igualdad", {"a": "sin(x)^2 + cos(x)^2", "b": "1"}))
        assert n.sello.verdict == V.NUMERIC_ONLY
        C.withdraw_verificador("no_aplica")

        def roto(_):
            raise RuntimeError("falta el módulo")
        C.registrar_verificador("roto", roto)
        n = ML.calcular(ML.Peticion("igualdad", {"a": "sin(x)^2 + cos(x)^2", "b": "1"}))
        assert n.sello.verdict == V.NUMERIC_ONLY and any("roto" in a for a in n.avisos)
    finally:
        C.withdraw_verificador("no_aplica")
        C.withdraw_verificador("roto")
