# SPDX-License-Identifier: MIT
"""Barrow's rule only where it holds — found 2026-10-05 auditing against SymPy.

Four definite integrals came out wrong, two by a pole between the probe points
and two by a jump of the antiderivative; and the universal substitution produced
a FALSE primitive for any integrand with a bare ``x``. Every expected value here is
the textbook one, and each test names the wrong answer the engine used to give.
"""
from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import continuidad as K
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.symbolic import integrate as I


def _calcula(texto):
    return ML.calcular(ML.Peticion("integrar", texto))


@pytest.mark.parametrize("texto,esperado,antes", [
    ("int(sin(x)*sin(x), x, 0, 2*pi)", math.pi, 0.0),
    ("int(1/(2+cos(x)), x, 0, 2*pi)", 2 * math.pi / math.sqrt(3), 0.0),
    ("int(1/(2+cos(x)), x, 7, 0)", None, None),
])
def test_la_primitiva_que_salta_se_corrige_por_tramos(texto, esperado, antes):
    r = _calcula(texto)
    q = K.cuadratura(mx.parse("1/(2+cos(x))"), "x", 0, 7)[0]
    esperado = -q if esperado is None else esperado
    assert r.aproximado is not None
    assert abs(r.aproximado.real - esperado) < 1e-9, (texto, r.aproximado, antes)
    # an exact value is fine (sin·sin now integrates by product-to-sum, without
    # jumps, and π is exact); a jump-corrected value is never presented as exact
    if "tramos" in r.sello.method:
        assert r.sello.verdict != V.VERIFIED


@pytest.mark.parametrize("texto,antes", [
    ("int(1/(x-1/10), x, 0, 1)", 2.197),
    ("int(tan(x), x, 0, 2)", 0.877),
    ("int(1/x^3, x, -1, 2)", 0.375),
    ("int(1/(x-1)^2, x, 0, 3)", None),
])
def test_un_polo_entre_los_puntos_de_prueba_ya_no_pasa(texto, antes):
    """Divergent integrals: no number, and the reason says improper.

    The verdict «diverge» is the result itself (2026-10-07): a result with neither an
    exact nor an approximate value broke the §5.9 contract (``validar_forma``)."""
    from academic_core.domain.engineering.mathlab import contract as C

    r = _calcula(texto)
    assert r.aproximado is None, (texto, r.aproximado, antes)
    assert r.exacto is None or "diverge" in str(r.exacto), r.exacto
    assert "impropia" in r.sello.detail
    if r.exacto is not None:
        assert C.validar_forma(r) == []


def test_una_singularidad_evitable_no_se_confunde_con_un_polo():
    assert K.puntos_singulares(mx.parse("sin(x)/x"), "x", -1, 1) == []
    assert K.puntos_singulares(mx.parse("(x^2-1)/(x-1)"), "x", 0, 2) == []


@pytest.mark.parametrize("integrando", ["sin(x)/x", "cos(x)/x", "x*cos(x)/(1+sin(x))",
                                        "x/(1+cos(x))", "x*sin(x)^2"])
def test_la_sustitucion_universal_no_toca_una_x_suelta(integrando):
    """Under u = tg(x/2), x is 2·arctg(u), not u. Mapping it to u returned
    x + sin x as a primitive of sin(x)/x. Whatever comes back now must
    differentiate to the integrand, or there must be nothing."""
    from academic_core.domain.engineering.mathlab import derive_mv as D

    try:
        primitiva, _ = I.integrate(mx.to_symbolic(mx.parse(integrando)), "x", I.StepLog())
    except Exception:  # noqa: BLE001 - refusing is a correct answer here
        return
    derivada = D.differentiate(mx.from_symbolic(primitiva), "x")
    ok, _m, detalle = V.numeric_agreement(derivada, mx.parse(integrando), samples=12)
    assert ok, (integrando, mx.text(mx.from_symbolic(primitiva)), detalle)


def test_una_primitiva_que_no_deriva_en_el_integrando_no_se_muestra():
    # sen(x)/x no tiene primitiva elemental: ahora se da con la función especial Si,
    # y solo porque al derivarla vuelve el integrando (verificada)
    r = _calcula("int(sin(x)/x, x)")
    assert r.exacto == "Si(x)" and r.sello.verdict == "verificado"


def test_sin_primitiva_elemental_la_definida_cae_a_simpson_y_acierta():
    r = _calcula("int(sin(x)/x, x, 1, 2)")
    # Si(2) - Si(1)
    assert abs(r.aproximado.real - 0.659329906435512) < 1e-9


@pytest.mark.parametrize("texto,esperado", [
    ("int(x^2, x, 0, 3)", 9.0), ("int(sin(x), x, 0, pi)", 2.0),
    ("int(cos(x)*cos(2*x), x, 0, 4)", (math.sin(4) + math.sin(12) / 3) / 2),
    ("int(exp(x), x, 0, 1)", math.e - 1),
])
def test_lo_que_ya_estaba_bien_sigue_bien_y_ahora_esta_contrastado(texto, esperado):
    r = _calcula(texto)
    assert abs(r.aproximado.real - esperado) < 1e-9
    reglas = [s.rule for s in r.traza]
    assert "integral.cuadratura" in reglas, reglas


@pytest.mark.parametrize("texto,a,b,valor", [
    ("exp(x)", 0, 1, math.e - 1), ("sin(x)^2", 0, 2 * math.pi, math.pi),
    ("sqrt(x)", 0, 4, 16 / 3), ("1/(1+x^2)", -1, 1, math.pi / 2),
])
def test_la_cuadratura_independiente_es_exacta_a_doble_precision(texto, a, b, valor):
    q, err = K.cuadratura(mx.parse(texto), "x", a, b)
    assert abs(q - valor) < 1e-12 and err < 1e-9


@pytest.mark.parametrize("integrando,esperada", [
    ("sin(x)*cos(3*x)", "cos(2*x)/4 - cos(4*x)/8"),
    ("cos(x)*cos(2*x)", "sin(3*x)/6 + sin(x)/2"),
    ("sin(x)*sin(x)", "x/2 - sin(2*x)/4"),
])
def test_producto_a_suma_da_la_primitiva_de_los_libros(integrando, esperada):
    """It used to be a degree-8 polynomial in 1/(1 + tg(x/2)²), or atan(tan(x/2))."""
    primitiva, _ = I.integrate(mx.to_symbolic(mx.parse(integrando)), "x", I.StepLog())
    assert mx.text(mx.from_symbolic(primitiva)) == esperada


@pytest.mark.parametrize("nombre", ["sin", "cos", "tan", "sinh", "cosh", "tanh",
                                    "sec", "csc", "cot", "coth", "csch", "sech"])
@pytest.mark.parametrize("n", range(1, 9))
def test_toda_potencia_de_una_trigonometrica_o_hiperbolica_deriva_en_si_misma(nombre, n):
    """∫cosh(x)^5 used to return the primitive of cosh(x)^2 — the table read the
    base and not the exponent — and ∫coth(x)^2 returned ∫coth. Each primitive
    here is differentiated and compared with its integrand."""
    from academic_core.domain.engineering.mathlab import derive_mv as D

    texto = f"{nombre}(x)^{n}" if n > 1 else f"{nombre}(x)"
    primitiva, _ = I.integrate(mx.to_symbolic(mx.parse(texto)), "x", I.StepLog())
    derivada = D.differentiate(mx.from_symbolic(primitiva), "x")
    ok, _m, detalle = V.numeric_agreement(derivada, mx.parse(texto), samples=16)
    assert ok, (texto, mx.text(mx.from_symbolic(primitiva)), detalle)


@pytest.mark.parametrize("texto,a,b,exacto", [
    # values from the closed forms, not from another quadrature
    ("ln(3*x^2)", "-1", "11",
     (11 * math.log(363) - 22) - (-math.log(3) + 2)),
    ("ln(x^2)", "-2", "1", -2 - (-2 * math.log(4) + 4)),
    ("e^(x^2)", "0", "1", 1.4626517459071816),
])
def test_el_error_declarado_sin_primitiva_cubre_el_error_real(texto, a, b, exacto):
    """The Simpson/Richardson estimate it replaced declared 0.0046 for an error
    of 0.069 on the first one — an «error acotado» smaller than the error."""
    r = _calcula(f"int({texto}, x, {a}, {b})")
    if r.error_acotado is None:          # ahora con forma cerrada (erfi…): valor exacto
        assert r.exacto is not None and abs(r.aproximado.real - exacto) < 1e-10, (
            texto, r.exacto, r.aproximado)
        return
    assert abs(r.aproximado.real - exacto) <= r.error_acotado, (
        texto, r.aproximado.real, exacto, r.error_acotado)
