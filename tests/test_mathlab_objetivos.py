"""T-20: the engine says what it can do.

An objective you cannot enumerate is one you cannot promise. Four of them —
``derivar``, ``integrar``, ``complejos`` and ``fasores`` — lived in the modules
that need them, so the engine could not answer the question and the inventory was
silently half the size of the laboratory.
"""
from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import complejos as K
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig
from academic_core.domain.engineering.mathlab import verify as V

#: the four that used to be scattered, and where each one now lives
TRANSFORMACION = {
    "derivar": "derive_mv.py",
    "integrar": "integrate.py",
    "complejos": "complejos.py",
    "fasores": "fasores.py",
}

REESCRITURA = ("simplificar", "expandir", "producto_a_suma", "suma_a_producto",
               "potencias", "sustitucion_universal", "hiperbolicas", "exponencial")


# ---------------------------------------------------------------------------
# the inventory is complete and declared, not scattered
# ---------------------------------------------------------------------------


def test_los_doce_objetivos_estan_declarados_en_el_motor():
    assert set(trig.OBJETIVOS) == set(REESCRITURA) | set(TRANSFORMACION)


@pytest.mark.parametrize("nombre", sorted(TRANSFORMACION))
def test_cada_objetivo_de_transformacion_dice_de_donde_viene(nombre):
    """«the engine can do it» and «the engine knows how it does it» are the same
    claim, so the module is written down next to the method."""
    objetivo = trig.objetivo(nombre)
    assert objetivo.procede_de.endswith(TRANSFORMACION[nombre]), objetivo.procede_de
    assert callable(objetivo.metodo)


@pytest.mark.parametrize("nombre", sorted(TRANSFORMACION) + sorted(REESCRITURA))
def test_todo_objetivo_declara_su_metodo_y_su_segundo_camino(nombre):
    """§5.5b writes the method down; T-22 names the path that checks it.

    A transformation has no families because it rewrites nothing, and what it
    owes instead is these two. Without them the four would be objectives in name
    only.
    """
    objetivo = trig.objetivo(nombre)
    assert objetivo.porque.strip(), nombre
    assert len(objetivo.porque) > 40, (nombre, objetivo.porque)
    assert objetivo.verifica.strip(), nombre


@pytest.mark.parametrize("nombre", sorted(TRANSFORMACION))
def test_un_objetivo_de_transformacion_no_declara_familias_que_no_tiene(nombre):
    """They rewrite nothing, so a family list would be an invention.

    The reverse is the real guard: the eight rewrite objectives MUST have one.
    """
    assert trig.objetivo(nombre).familias == ()
    assert trig.objetivo(nombre).es_reescritura is False


@pytest.mark.parametrize("nombre", sorted(REESCRITURA))
def test_un_objetivo_de_reescritura_tiene_al_menos_una_regla(nombre):
    assert trig.familias(nombre), nombre
    for familia in trig.familias(nombre):
        assert familia in trig.identities(), (nombre, familia)


def test_el_inventario_no_promete_una_familia_sin_regla():
    """Every advertised family has a callable behind it, in one sweep."""
    for nombre in trig.identities():
        assert callable(trig.regla(nombre)), nombre
        assert trig.descripcion(nombre).strip(), nombre


# ---------------------------------------------------------------------------
# the four objectives actually run
# ---------------------------------------------------------------------------


def test_derivar_como_objetivo_del_motor():
    metodo = trig.objetivo("derivar").metodo
    assert mx.text(metodo(mx.parse("sin(2*x)"))) == "cos(2*x)*2*1"
    # 2*x^1 is the same derivative as 2*x and reads worse; compared numerically so
    # the test is about the derivative and not about a printing choice
    ok, _metodo, _detalle = V.numeric_agreement(
        metodo(mx.parse("x^2")), mx.parse("2*x"), samples=8)
    assert ok


def test_integrar_como_objetivo_del_motor_atraviesa_los_dos_arboles():
    """``symbolic.integrate`` was written against the other expression tree.

    The conversion is here and not inside the integrator, because a conversion
    hidden in the middle of a module is one nobody looks at twice.
    """
    metodo = trig.objetivo("integrar").metodo
    assert mx.text(metodo(mx.parse("x^2"))) == "x^3/3"
    assert mx.text(metodo(mx.parse("sin(x)"))) == "-cos(x)"


def test_la_primitiva_devuelta_se_deriva_para_comprobarla():
    """The verification the objective declares, run here by hand."""
    from academic_core.domain.engineering.mathlab import derive_mv

    metodo = trig.objetivo("integrar").metodo
    for integrando in ("x^2", "sin(x)", "cos(2*x)", "exp(x)"):
        primitiva = metodo(mx.parse(integrando))
        vuelta = derive_mv.differentiate(primitiva, "x")
        ok, _metodo, _detalle = V.numeric_agreement(vuelta, mx.parse(integrando),
                                                   samples=10)
        assert ok, (integrando, mx.text(primitiva), mx.text(vuelta))


def test_complejos_como_objetivo_del_motor():
    metodo = trig.objetivo("complejos").metodo
    i = K.Complejo(mx.ZERO, mx.Num(1))
    # sin(i) = i·sinh(1) and cos(i) = cosh(1), with the hyperbolic ones exact
    assert metodo("sin", i).texto() == "sinh(1)i"
    assert metodo("cos", i).texto() == "cosh(1)"
    # cos(3 + 4i) is NOT 3 + 4i: the whole point is that it is not
    assert metodo("cos", K.Complejo(mx.Num(3), mx.Num(4))).texto() != "(3 + 4i)"


def test_complejos_se_niega_a_una_funcion_sin_contrapartida():
    """A refusal with a reason, not a KeyError and not a wrong answer."""
    with pytest.raises(Exception) as exc:
        trig.objetivo("complejos").metodo("sen", K.Complejo(mx.ZERO, mx.Num(1)))
    assert "complejo" in str(exc.value).lower()


def test_fasores_como_objetivo_del_motor():
    """A phasor is a complex number plus the frequency that must not be dropped.

    3 + 4i has modulus 5 exactly, and the ωt that disappears when the phasor is
    formed is exactly what stops two phasors of different frequencies from
    being added.
    """
    from academic_core.domain.engineering.mathlab import fasores as F

    fasor = trig.objetivo("fasores").metodo(3, 0, 50)
    assert mx.exact_value(fasor.magnitud) == 3
    assert mx.exact_value(fasor.frecuencia) == 50
    ok, _razon = F.verifica_contrato()
    assert ok


# ---------------------------------------------------------------------------
# the declaration reaches the student
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operacion,entrada,objetivo", [
    ("derivar", "sin(2*x)", "derivar"),
    ("integrar", "int(x^2, x)", "integrar"),
    ("complejo", "3+4i", "complejos"),
    ("fasor", {"amplitud": 3, "frecuencia": 50}, "fasores"),
])
def test_la_calculadora_escribe_el_objetivo_en_la_traza(operacion, entrada,
                                                      objetivo):
    """A declaration nobody reads is a declaration in a file."""
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion(operacion, entrada))
    reglas = [s.rule for s in resultado.traza]
    assert f"objetivo.{objetivo}" in reglas, reglas
    assert f"objetivo.{objetivo}.verifica" in reglas, reglas


def test_el_paso_del_objetivo_lleva_el_por_que_y_no_una_etiqueta():
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion("derivar", "sin(2*x)"))
    pasos = [s for s in resultado.traza if s.rule == "objetivo.derivar"]
    assert pasos
    paso = pasos[0]
    assert len(paso.why) > 40, paso.why
    assert paso.alternatives, "un método sin alternativa escrita no estájustificado"


def test_el_inventario_es_lo_que_la_calculadora_dice():
    """One declaration, read by the inventory, the trajectory and the docs."""
    import academic_core.domain.engineering.mathlab as ML

    declarados = {nombre for nombre, _, _, _, _ in trig.inventario()}
    resultado = ML.calcular(ML.Peticion("integrar", "int(x^2, x)"))
    en_la_traza = {s.rule.split(".")[1] for s in resultado.traza
                   if s.rule.startswith("objetivo.")}
    assert en_la_traza == {"integrar"}
    assert en_la_traza <= declarados
