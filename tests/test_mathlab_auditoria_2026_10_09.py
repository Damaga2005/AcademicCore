# SPDX-License-Identifier: MIT
"""Regresiones de la auditoría de MathLab del 2026-10-09: cada test falla con el
código anterior."""

import importlib
import math
import pkgutil

import pytest

import academic_core.domain.engineering.mathlab as pkg
from academic_core.domain.engineering.mathlab import campos as CA
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import fisica as FI
from academic_core.domain.engineering.mathlab import graficas as G
from academic_core.domain.engineering.mathlab import ramas as RA
from academic_core.errors import ValidationError

for _m in pkgutil.iter_modules(pkg.__path__):
    importlib.import_module(f"{pkg.__name__}.{_m.name}")


def _bad_input(op, entrada):
    with pytest.raises(ValidationError, match="BAD_INPUT"):
        C.calcular(C.Peticion(op, entrada))


# --- faraday -----------------------------------------------------------------

def test_faraday_acepta_angulo_en_texto():
    # antes: NameError, _angulo no existía en campos
    r = CA.faraday(1, 50, 100, "0.01", theta="pi/3")
    assert r["fem_amp"] == pytest.approx(100 * 0.01 * 2 * math.pi * 50 * 0.5)


def test_faraday_signo_de_lenz():
    # Φ = NAB₀cosθ·sen(ωt) ⇒ ε = −NAB₀ω·cosθ·cos(ωt): el signo va en el resultado
    r = C.calcular(C.Peticion("campos", {"calculo": "faraday"}))
    assert "ε = −" in str(r.exacto)


# --- floats pequeños -----------------------------------------------------------

@pytest.mark.parametrize("x", [1.6e-19, 4.65e-26, 1.23456789e-7, 0.1])
def test_float_conserva_su_valor(x):
    # antes: limit_denominator(10**9) hacía 1.6e-19 → 0 y recortaba cifras
    assert FI._f(x) == x
    assert CA._f(x) == x


def test_carga_del_electron_no_da_campo_nulo():
    r = CA.e_anillo(1.6e-19, 0.1, 0.1)
    k = 8.9875517923e9
    assert r["E"] == pytest.approx(k * 1.6e-19 * 0.1 / 0.02 ** 1.5, rel=1e-6)


def test_maxwell_boltzmann_con_masa_en_float():
    r = FI.maxwell_boltzmann(4.65e-26, 300)
    assert r  # antes: BAD_INPUT «m, T > 0» porque m se redondeaba a 0


# --- r_ar1 con los valores por defecto ---------------------------------------------

def test_r_ar1_por_defecto():
    r = C.calcular(C.Peticion("deteccion", {"calculo": "r_ar1"}))
    assert "r = " in str(r.exacto)


# --- excepciones crudas → BAD_INPUT ----------------------------------------------

@pytest.mark.parametrize("op, entrada", [
    ("aprende", {"calculo": "regresion"}),
    ("aprende", {"calculo": "lasso"}),
    ("aprende", {"calculo": "em"}),
    ("finanzas", {"calculo": "tir"}),
    ("finanzas", {"calculo": "frontera"}),
    ("fisica", {"calculo": "mezcla"}),
    ("discreta", {"calculo": "tiempo_real"}),
    ("refuerzo", {"calculo": "mdp_optimo"}),
    ("senales", {"calculo": "regimen"}),
    ("senales", {"calculo": "regimen", "x": []}),
])
def test_lista_vacia_es_bad_input(op, entrada):
    _bad_input(op, entrada)


@pytest.mark.parametrize("op", ["tfc", "inversa", "teorema", "riemann", "primitiva"])
def test_texto_donde_va_un_diccionario_es_bad_input(op):
    _bad_input(op, "x")


def test_numero_enorme_es_bad_input():
    _bad_input("tabla_estadistica", {"expresion": "1e400", "f": "1e400", "funcion": "1e400",
                                     "valor": "1e400", "x": "1e400", "theta": "1e400"})


# --- limpieza ----------------------------------------------------------------------

def test_graficas_all_solo_nombra_lo_que_existe():
    assert all(hasattr(G, n) for n in G.__all__)


def test_ramas_dominio_de_no_arrastra_codigo_muerto():
    import inspect
    assert "INVERSAS" not in inspect.getsource(RA.dominio_de)


def test_potencial_2d_no_arrastra_codigo_muerto():
    import inspect
    assert "planck" not in inspect.getsource(FI.potencial_2d)
