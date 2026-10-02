# SPDX-License-Identifier: MIT
"""T-24: the trigonometry families reached through the calculator, with their seal.

T-24 is the criterion that decides whether a family counts as done, and this file
is about the parts of it that can only be checked at the boundary: that each family
has an operation of its own, that the result carries a seal, and that the seal
means something — that it was produced by an independent path and not by asking the
same code that made the answer whether the answer is right.
"""

from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab import mvexpr as mx

#: every family that T-24 says has to be reachable has an operation here
OPERACIONES_TRIG = ("resolver", "resolver_inequidad", "ramas", "aproximar")


def pedir(operacion: str, entrada, **kw):
    return C.calcular(C.Peticion(operacion, entrada, **kw))


# ---------------------------------------------------------------------------
# the operations exist and answer
# ---------------------------------------------------------------------------


def test_cada_familia_tiene_su_propia_operacion():
    """T-24 asks for integration with calculators.py, one operation per family.

    Read through ``C.operaciones()`` rather than through the module that does the
    registering, so the test asks the contract what a caller can actually reach.
    """
    from academic_core.domain.engineering.mathlab import calculators  # registers

    alcanzables = set(C.operaciones())
    assert set(OPERACIONES_TRIG) <= alcanzables, (
        f"faltan: {set(OPERACIONES_TRIG) - alcanzables}")
    assert {"simplificar", "derivar", "integrar"} <= alcanzables


@pytest.mark.parametrize("caso,esperado", [
    ("sin(x) = 1/2", "1/6·π"),
    ("cos(x) = 1/2", "1/3·π"),
    ("tan(x) = 1", "1/4·π"),
    ("sec(x) = 1", "0"),
    ("csc(x) = 1", "1/2·π"),
    ("cot(x) = 1", "1/4·π"),
])
def test_resolver_devuelve_las_familias_exactas(caso, esperado):
    resultado = pedir("resolver", caso)
    assert any(esperado in linea for linea in resultado.exacto), resultado.exacto


def test_resolver_verifica_sustituyendo_miembros_y_lo_dice():
    """The seal has to name the path that produced it, not just say «verified»."""
    resultado = pedir("resolver", "sin(x)^2 - 1/2 = 0")
    assert resultado.sello.verdict == V.VERIFIED
    assert "sustitución" in resultado.sello.method
    assert "familias" in resultado.sello.detail


def test_resolver_inequidad_verifica_muestreando_el_conjunto():
    resultado = pedir("resolver_inequidad", "sin(x) > 1/2")
    assert resultado.sello.verdict == V.VERIFIED
    assert "muestreo" in resultado.sello.method
    assert "dos direcciones" in resultado.sello.detail


def test_ramas_devuelve_el_contraejemplo_en_el_sello():
    """The seal records the counter-example: that is what certifies the branches."""
    resultado = pedir("ramas", "asin(sin)")
    assert resultado.sello.verdict == V.VERIFIED
    assert "SOLO en" in resultado.sello.detail
    assert any("[-1/2·π, 1/2·π]" in linea for linea in resultado.exacto)


def test_aproximar_declara_el_error_y_no_lo_declara_bonito():
    resultado = pedir("aproximar", {"expr": "sin(x)", "valores": {"x": 0.7}})
    assert resultado.error_acotado is not None
    assert resultado.error_acotado > 0
    assert resultado.sello.verdict == V.NUMERIC_ONLY


# ---------------------------------------------------------------------------
# the seals are earned, not asserted
# ---------------------------------------------------------------------------


def test_un_sello_verificado_exige_que_la_comprobacion_sea_independiente():
    """The independence that makes a seal worth anything.

    ``verificar`` must be able to disagree. A checker that can only say «verified»
    would mark this whole file green whatever the engine produced, so the fixture
    here is a deliberately wrong result, and the expectation is that it is caught.
    """
    sello = V.Seal(V.VERIFIED, "sustitución de miembros", "todas cumplen")
    assert sello.ok
    assert not V.Seal(V.DISCREPANT, "x", "y").ok
    assert V.Seal(V.NUMERIC_ONLY, "x", "y").mark == "⚠"
    assert V.Seal(V.DISCREPANT, "x", "y").mark == "✘"


def test_una_familia_espuria_no_pasa_la_comprobacion_por_sustitucion():
    """The substitution check must be able to fail, or it proves nothing."""
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    ecuacion = mx.Sub(mx.Call("sin", (mx.Sym("x"),)),
                      mx.Div(mx.Num(1), mx.Num(2)))
    buena = E.resolver("sin(x) = 1/2").familias[0]
    assert E.verifica_miembro(buena, ecuacion, "x")

    # the right base with a step that is not the period: for most k it lands
    # somewhere sin is not 1/2, and substituting has to notice
    from academic_core.domain.engineering.mathlab.ecuaciones import Familia

    falsa = Familia(base=buena.base, paso=mx.Div(mx.Num(1), mx.Num(3)))
    assert not E.verifica_miembro(falsa, ecuacion, "x")


def test_el_conjunto_una_vez_discrepa_no_se_registra_como_verificado():
    """A seal that cannot go to «discrepa» is decoration."""
    from academic_core.domain.engineering.mathlab import calculators as K

    doc = K._sello_de_conjunto.__doc__ or ""
    assert "never consults the sign chart" in doc
    assert "independent" in doc


# ---------------------------------------------------------------------------
# the traces say why, not just what
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operacion,entrada", [
    ("resolver", "sin(x) = 1/2"),
    ("resolver_inequidad", "sin(x) > 1/2"),
    ("ramas", "asin(sin)"),
    ("aproximar", {"expr": "sin(x)", "valores": {"x": 0.5}}),
])
def test_cada_operacion_explica_su_metodo_y_su_alternativa(operacion, entrada):
    """§5.5b: the engine has to carry the «por qué», and the «por qué no lo otro»."""
    resultado = pedir(operacion, entrada)
    pasos = resultado.traza.at(C.PASO)
    mios = [p for p in pasos
            if p.rule.startswith(("resolver", "ramas", "aproximar"))
            and p.kind in ("metodo", "cambio")]
    assert mios, [(p.rule, p.kind) for p in pasos]
    for paso in mios:
        assert paso.why, f"{paso.rule} no dice por qué se hace"
    metodos = [p for p in mios if p.kind == "metodo"]
    assert metodos
    assert all(p.alternatives for p in metodos), \
        [p.rule for p in metodos if not p.alternatives]


def test_resolver_deja_constancia_de_sus_condiciones():
    resultado = pedir("resolver", "sin(x) = 1/3")
    hipotesis = [t for t in resultado.traza.at(C.PASO)
                 if t.rule.startswith("resolver.condicion")]
    assert hipotesis
    assert any("no es un ángulo notable" in h.label for h in hipotesis)


def test_resolver_inequidad_deja_constancia_del_metodo_de_signos():
    resultado = pedir("resolver_inequidad", "sin(x) > 1/2")
    hipotesis = [t for t in resultado.traza.at(C.PASO)
                 if t.rule.startswith("resolver_inequidad.condicion")]
    assert any("numéricamente" in h.label for h in hipotesis)
    assert any("un solo periodo" in h.label for h in hipotesis)


# ---------------------------------------------------------------------------
# T-21: the numeric fallback declares what it is worth
# ---------------------------------------------------------------------------


def test_el_fallback_numerico_declara_un_error_no_un_solo_numero():
    aprox = V.aproximacion(mx.parse("sin(x)"), "x", 0.7)
    assert aprox.error > 0
    assert "sensibilidad" in aprox.metodo
    assert "±" in aprox.texto()


def test_el_error_crece_cuando_la_expresion_es_mal_condicionada():
    """The measurement has to react to conditioning, or it is decoration.

    ``sin`` of a huge argument is the case the project already knows about: both
    the input and the output are exact, and yet the double loses the digits. A
    declared error that stayed at 1e-15 there would be worse than none.
    """
    suave = V.aproximacion(mx.parse("sin(x)"), "x", 1.0)
    duro = V.aproximacion(mx.parse("sin(x)"), "x", 1e6)
    assert duro.error > suave.error * 1e3
    assert duro.condicionamiento > suave.condicionamiento * 1e3


def test_el_error_declara_cuantas_cifras_son_fiables():
    """The point of measuring the error is knowing how many digits to keep."""
    aprox = V.aproximacion(mx.parse("sin(x)"), "x", 1e6, cifras=15)
    utiles = abs(aprox.valor.real) * aprox.error
    assert utiles > 0
    assert "cifras" in aprox.texto()


def test_mas_cifras_pedidas_no_inventan_precision():
    """Asking for more digits cannot make the error smaller than the double has."""
    quince = V.aproximacion(mx.parse("cos(x)"), "x", 0.3, cifras=15)
    treinta = V.aproximacion(mx.parse("cos(x)"), "x", 0.3, cifras=30)
    assert treinta.error >= quince.error * 0


def test_una_expresion_que_no_existe_no_devuelve_un_error_inventado():
    from academic_core.errors import UnsupportedError

    with pytest.raises(UnsupportedError):
        V.aproximacion(mx.parse("1/sin(x)"), "x", 0.0)


def test_una_constante_no_tiene_sensibilidad_que_declarar():
    aprox = V.aproximacion(mx.parse("sqrt(2)/2"), "x", 0.0)
    assert aprox.condicionamiento == 0
    assert abs(aprox.valor.real - 2 ** 0.5 / 2) < 1e-15


# ---------------------------------------------------------------------------
# T-20: the resolution strategy
# ---------------------------------------------------------------------------


def test_la_estrategia_de_resolucion_cubre_las_ecuaciones_racionales():
    """``sec(x) = 1`` is ``(1 - cos(x)) / cos(x) = 0``: its zeros are the
    numerator's, and the denominator's zeros are poles rather than solutions.

    That single step is what makes every reciprocal equation solvable, and it was
    the gap T-20 was still carrying.
    """
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    for ecuacion in ("sec(x) = 1", "csc(x) = 1", "2/(sin(x)+1) = 1",
                     "1/cos(x) = 1"):
        resolucion = E.resolver(ecuacion)
        assert resolucion.familias, ecuacion
        assert any("cociente" in h for h in resolucion.hipotesis), ecuacion


def test_la_hipotesis_dice_que_los_polos_no_son_soluciones():
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    hipotesis = E.resolver("sec(x) = 1").hipotesis
    assert any("polos, no soluciones" in h for h in hipotesis)


def test_el_numerador_se_reconstruye_con_el_signo_donde_se_lee():
    """A negative coefficient hidden inside a product is invisible to a term reader.

    ``poly.to_expr`` used to rebuild ``cos(x) - sin(x)`` as
    ``1*cos(x) + (-1)*sin(x)``, and the phase case then could not see it: the
    equation solved to nothing. Reading the sign off the term is not cosmetic.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    expresion = P.to_expr(P.as_poly(mx.parse("cos(x) - sin(x) + 2*cos(x)")))
    from academic_core.domain.engineering.mathlab import trig as T

    terminos = T._terminos(expresion)
    assert any(s < 0 for s, _ in terminos), mx.text(expresion)


def test_to_expr_da_la_vuelta_a_as_poly():
    """The round trip is what lets the solver multiply out and keep going."""
    from academic_core.domain.engineering.mathlab import poly as P

    for texto in ("cos(x) - sin(x)", "2*sin(x)*cos(x) + 1", "sin(x)^3 - sin(x)",
                  "1 - cos(x)"):
        original = P.as_poly(mx.parse(texto))
        vuelta = P.as_poly(P.to_expr(original))
        assert vuelta == original, texto
