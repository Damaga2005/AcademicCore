# SPDX-License-Identifier: MIT
"""MATH_LAB T-15: complex numbers, Euler and De Moivre."""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import complejos as K
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.errors import UnsupportedError

PI = 3.141592653589793


def z(texto: str) -> K.Complejo:
    return K.Complejo.de_texto(texto)


# ---------------------------------------------------------------------------
# parsing and printing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto,real,imag", [
    ("3+4i", 3, 4),
    ("1-i", 1, -1),
    ("i", 0, 1),
    ("-i", 0, -1),
    ("2i", 0, 2),
    ("-2i", 0, -2),
    ("1+i", 1, 1),
    ("2", 2, 0),
    ("-1-0i", -1, 0),
    ("0+1i", 0, 1),
])
def test_se_lee_cualquier_literales(texto, real, imag):
    numero = z(texto)
    assert mx.exact_value(numero.real) == real
    assert mx.exact_value(numero.imag) == imag


def test_un_complejo_tiene_que_ser_exacto():
    """A pair of floats is an approximation wearing the costume of a number."""
    with pytest.raises(UnsupportedError) as exc:
        K.Complejo(0.5, 0.25)
    assert "expresión exacta" in str(exc.value)


def test_la_unidad_imaginaria_no_se_multiplica_como_una_expresion():
    """``i·i = -1`` is not a product rule, and the representation has to know it.

    ``|3+4i|`` is 5. With the imaginary unit written as a factor, the modulus would
    be ``sqrt(16·i·i)`` — a square root of something that is not a number. The two
    parts are stored as real expressions and the pairing rule is where the ``-1``
    lives.
    """
    numero = z("3+4i")
    assert mx.exact_value(numero.modulo()) == 5
    assert numero.imag == mx.Num(Fraction(4))


# ---------------------------------------------------------------------------
# arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("a,b,real,imag", [
    ("3+4i", "1-2i", 11, -2),
    ("3+4i", "3-4i", 25, 0),
    ("i", "i", -1, 0),
    ("2+3i", "0", 0, 0),
    ("-1-1i", "1-1i", -2, 0),
])
def test_el_producto_es_exacto(a, b, real, imag):
    producto = z(a) * z(b)
    assert mx.exact_value(producto.real) == real
    assert mx.exact_value(producto.imag) == imag


@pytest.mark.parametrize("a,b,real,imag", [
    ("3+4i", "1-2i", -1, 2),
    ("(3+4i)/(1-2i)", "(3+4i)/(1-2i)", 1, 0),
])
def test_el_cociente_es_exacto(a, b, real, imag):
    cociente = z(a) / z(b)
    assert abs(mx.evaluate(cociente.real) - real) < 1e-12
    assert abs(mx.evaluate(cociente.imag) - imag) < 1e-12


def test_dividir_por_el_cero_dice_que_es_el_cero():
    with pytest.raises(ZeroDivisionError):
        z("1+i") / z("0")


@pytest.mark.parametrize("base,exponente,real,imag", [
    ("i", 2, -1, 0),
    ("i", 4, 1, 0),
    ("-1-0i", 3, -1, 0),
    ("1+i", 2, 0, 2),
    ("2", 10, 1024, 0),
])
def test_las_potencias_enteras(base, exponente, real, imag):
    potencia = z(base) ** exponente
    assert abs(mx.evaluate(potencia.real) - real) < 1e-9, potencia.texto()
    assert abs(mx.evaluate(potencia.imag) - imag) < 1e-9, potencia.texto()


def test_una_potencia_no_entera_no_es_univoca_y_se_dice():
    """``z^w`` is multivalued: the log is. Silently taking a branch is not solving."""
    with pytest.raises(UnsupportedError) as exc:
        z("3+4i") ** 0.5
    assert "rama" in str(exc.value) or "unívocas" in str(exc.value)


def test_el_conjugado_cambia_el_signo_de_la_imaginaria():
    conjugado = z("3-4i").conjugado()
    assert mx.exact_value(conjugado.imag) == 4
    assert (z("3+4i") * z("3+4i").conjugado()).es_real
    assert mx.exact_value((z("3+4i") * z("3+4i").conjugado()).real) == 25


# ---------------------------------------------------------------------------
# modulus and argument — where the branch matters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto,modulo", [
    ("3+4i", 5), ("5+12i", 13), ("1+i", math.sqrt(2)), ("i", 1), ("7", 7),
])
def test_el_modulo_es_exacto(texto, modulo):
    assert abs(mx.evaluate(z(texto).modulo()) - modulo) < 1e-12


@pytest.mark.parametrize("texto,argumento", [
    ("1", 0.0), ("i", PI / 2), ("-i", -PI / 2), ("-1-0i", PI), ("2", 0.0),
])
def test_el_argumento_principal_usa_el_rango_declarado(texto, argumento):
    """``(-pi, pi]``. ``arg(-1-0i) = pi`` and ``arg(-1+0i) = -pi``: same point,
    and picking the other one silently shifts every downstream phase."""
    assert abs(mx.evaluate(z(texto).argumento()).real - argumento) < 1e-12


def test_el_argumento_del_cero_no_esta_definido():
    with pytest.raises(ZeroDivisionError):
        K.Complejo(mx.ZERO, mx.ZERO).argumento()


def test_argumento_no_principal_gana_una_vuelta_entera():
    """``principal=False`` must name the SAME angle one whole turn away.

    This test used to assert the two were EQUAL, which is the opposite of what its
    name says, and it did it on ``3+4i`` — first quadrant, where the unfolded
    ``atan(y/x)`` is already principal and the flag changes nothing. So it passed
    for an implementation that ignored the flag entirely, and it could never have
    caught the second quadrant, where the unfolded ``atan(y/x)`` is not an
    argument of ``z`` at all.
    """
    for fuente in ("3+4i", "-3+4i", "3-4i", "-3-4i", "1+1i", "-1+1i"):
        base = mx.evaluate(z(fuente).argumento())
        otro = mx.evaluate(z(fuente).argumento(principal=False))
        assert abs(abs(otro.real - base.real) - 2 * math.pi) < 1e-12, fuente
        assert abs(math.sin(otro.real) - math.sin(base.real)) < 1e-12, fuente


@pytest.mark.parametrize("coordenadas", [
    (3, 4), (-3, 4), (3, -4), (-3, -4), (1, 1), (1, -1), (-1, 1), (-1, -1),
    (7, 1), (-7, 1),
])
def test_el_argumento_principal_cae_en_el_rango_declarado(coordenadas):
    """``(-pi, pi]`` for every quadrant, including both negative-real ones.

    The second and third quadrants fold in OPPOSITE directions — there ``y/x`` is
    negative in one and positive in the other — and folding them alike put
    ``arg(-3+4i)`` at -4.069, outside the range it declares. ``atan2`` is the
    authority: it shares no code with the engine.
    """
    re, im = coordenadas
    zc = K.Complejo(mx.Num(Fraction(re)), mx.Num(Fraction(im)))
    a = mx.evaluate(zc.argumento()).real
    assert abs(a - math.atan2(im, re)) < 1e-12, coordenadas
    assert -math.pi <= a <= math.pi, coordenadas


def test_el_argumento_no_principal_reconstruye_el_mismo_numero():
    """A turn away is the same point on the circle, and that has to be checked.

    Comparing the two angles is not enough: an angle with the wrong sign on its
    cosine is a whole turn from nothing. So the number is rebuilt and compared.
    """
    for re, im in ((3, 4), (-3, 4), (-3, -4), (-1, 1)):
        zc = K.Complejo(mx.Num(Fraction(re)), mx.Num(Fraction(im)))
        modulo = mx.evaluate(zc.modulo()).real
        a = mx.evaluate(zc.argumento(principal=False)).real
        assert abs(complex(modulo * math.cos(a), modulo * math.sin(a))
                    - complex(re, im)) < 1e-9


# ---------------------------------------------------------------------------
# the four forms, and the identity between them
# ---------------------------------------------------------------------------


def test_euler_en_un_notable_da_el_valor_exacto():
    assert K.euler(mx.ZERO).texto() == "1"
    assert K.euler(mx.PI).texto() == "-1"
    assert K.euler(mx.Mul(mx.Num(Fraction(1, 2)), mx.PI)).texto() == "i"


@pytest.mark.parametrize("k", [0, 1, 2, 3, 4, 5, 6])
def test_euler_coincide_con_el_cercle_unitario(k):
    """The second opinion, numerically, at angles around the circle.

    ``euler`` *is* the definition, so this cannot prove it. What it does catch is an
    evaluator or a printer that disagrees with the definition, which is a different
    failure and would otherwise reach every phasor built on top of it.
    """
    angulo = mx.Mul(mx.Num(Fraction(k, 6)), mx.PI)
    esperado = cmath.exp(1j * k * PI / 6)
    obtenido = K.euler(angulo)
    assert abs(mx.evaluate(obtenido.real) - esperado.real) < 1e-12
    assert abs(mx.evaluate(obtenido.imag) - esperado.imag) < 1e-12


def test_verifica_euler_lo_dice():
    ok, detalle = K.verifica_euler(mx.Sym("x"))
    assert ok, detalle
    assert "puntos de control" in detalle


@pytest.mark.parametrize("texto", ["3+4i", "1+i", "-2+0i", "5-3i", "i"])
def test_la_ida_y_vuelta_a_polar_devuelve_el_mismo_numero(texto):
    original = z(texto)
    vuelta = K.a_polar(original).a_rectangular()
    assert abs(mx.evaluate(vuelta.real) - mx.evaluate(original.real)) < 1e-12
    assert abs(mx.evaluate(vuelta.imag) - mx.evaluate(original.imag)) < 1e-12


def test_la_forma_polar_se_imprime_en_las_dos_notaciones():
    polar = K.a_polar(z("3+4i"))
    assert "cos(" in polar.texto() and "sen(" in polar.texto()
    assert polar.texto().startswith("5·(")
    assert polar.como_exponencial().startswith("5·e^(i·")


def test_de_moivre_da_todas_las_raices_y_son_distintas():
    for n in (2, 3, 4, 5):
        raices = K.de_moivre(mx.Num(1), mx.ZERO, n)
        assert len(raices) == n
        for primera in range(len(raices)):
            for segunda in range(primera + 1, len(raices)):
                diferencia = abs(mx.evaluate(raices[primera].real)
                                 - mx.evaluate(raices[segunda].real)) \
                    + abs(mx.evaluate(raices[primera].imag)
                          - mx.evaluate(raices[segunda].imag))
                assert diferencia > 1e-9, (n, primera, segunda)


def test_las_raices_cubicas_de_la_unidad_son_exactas():
    raices = K.de_moivre(mx.Num(1), mx.ZERO, 3)
    assert raices[0].texto() == "1"
    assert raices[1].texto() == "-1/2 + 1/2·√3·i"
    assert raices[2].texto() == "-1/2 - 1/2·√3·i"


def test_las_raices_cuadradas_de_menos_uno_son_mas_menos_i():
    raices = K.de_moivre(mx.Num(1), mx.PI, 2)
    assert abs(mx.evaluate(raices[0].real)) < 1e-12
    assert abs(mx.evaluate(raices[0].imag) - 1) < 1e-12
    assert abs(mx.evaluate(raices[1].real)) < 1e-12
    assert abs(mx.evaluate(raices[1].imag) + 1) < 1e-12


@pytest.mark.parametrize("modulo,angulo,n", [
    (1, 0, 3), (1, PI, 2), (4, 0, 3), (8, 0, 4), (2, PI / 2, 3),
])
def test_cada_raiz_al_elevado_n_vuelve_al_numero(modulo, angulo, n):
    modulo, angulo = mx.Num(modulo), mx.Mul(mx.Num(angulo), mx.PI)
    """The property that defines a root, checked by raising it.

    Not a substitute for the exact form — it is the property itself, and it is
    what a wrong sign in ``(θ + 2kπ)/n`` would break.
    """
    ok, detalle = K.verifica_de_moivre(modulo, angulo, n)
    assert ok, detalle


def test_de_moivre_rechaza_un_numero_de_raices_imposible():
    for n in (0, -2):
        with pytest.raises(UnsupportedError):
            K.de_moivre(mx.Num(1), mx.ZERO, n)


# ---------------------------------------------------------------------------
# branches
# ---------------------------------------------------------------------------


def test_el_logaritmo_tiene_una_rama_principal_y_las_demas():
    principal = K.log_multi(z("3+4i"))
    otra = K.log_multi(z("3+4i"), 1)
    assert "ln(5)" in principal.texto()
    assert "2·π" in K.Complejo(otra.modulo, otra.angulo).texto()


def test_las_ramas_del_log_difieren_en_vueltas_enteras():
    numero = z("3+4i")
    valores = [mx.evaluate(K.log_multi(numero, k).angulo) for k in (-2, -1, 0, 1, 2)]
    for k, valor in enumerate(valores):
        assert abs(valor - valores[0] - 2 * k * PI) < 1e-9, (k, valor)


def test_la_potencia_principal_usa_el_log_principal():
    potencia = K.potencia_principal(z("-1"), mx.Num(Fraction(1, 2)))
    assert abs(mx.evaluate(potencia.real)) < 1e-12
    assert abs(mx.evaluate(potencia.imag) - 1) < 1e-12      # sqrt(-1) = i


# ---------------------------------------------------------------------------
# complex trigonometry
# ---------------------------------------------------------------------------


def test_seno_y_coseno_se_descomponen_en_una_parte_real_y_una_imaginaria():
    seno = K.seno(K.Complejo.de_texto("i"))
    coseno = K.coseno(K.Complejo.de_texto("i"))
    # sin(i) = i·sinh(1) and cos(i) = cosh(1), both real expressions in i
    assert abs(mx.evaluate(seno.real)) < 1e-12
    assert abs(mx.evaluate(seno.imag) - math.sinh(1)) < 1e-12
    assert abs(mx.evaluate(coseno.real) - math.cosh(1)) < 1e-12
    assert abs(mx.evaluate(coseno.imag)) < 1e-12


@pytest.mark.parametrize("real,imag", [(0.3, 0.7), (-1.2, 0.4), (2.0, -0.5)])
def test_seno_y_coseno_coinciden_con_la_definicion_exponencial(real, imag):
    """``sin z = (e^(iz) - e^(-iz))/2i`` — the route the module does not take.

    A different definition agreeing with the one used is the only cross-check
    available here, and it is a real one: the decomposition could be wrong in a way
    that only shows when the two disagree.
    """
    numero = K.Complejo(mx.Num(Fraction(int(real * 100))), mx.Num(Fraction(int(imag * 100))))
    propio = K.seno(numero)
    x = mx.evaluate(numero.real).real
    y = mx.evaluate(numero.imag).real
    esperado = complex(math.sin(x) * math.cosh(y), math.cos(x) * math.sinh(y))
    assert abs(complex(mx.evaluate(propio.real).real,
                       mx.evaluate(propio.imag).real) - esperado) < 1e-12


def test_las_identidades_de_uno_se_cumplen_sobre_complejos():
    """``sin² + cos² = 1`` with a complex argument too, not only a real one."""
    numero = K.Complejo(mx.Num(Fraction(2)), mx.Num(Fraction(3, 2)))
    suma = K.seno(numero) ** 2 + K.coseno(numero) ** 2
    assert abs(mx.evaluate(suma.real) - 1) < 1e-9
    assert abs(mx.evaluate(suma.imag)) < 1e-9


def test_la_tangente_es_el_cociente_y_su_polo_dice_que_lo_es():
    numero = K.Complejo(mx.Num(Fraction(1, 2)), mx.Num(Fraction(1, 4)))
    cociente = K.tangente(numero)
    propio = K.seno(numero) / K.coseno(numero)
    assert abs(mx.evaluate(cociente.real) - mx.evaluate(propio.real)) < 1e-12
    with pytest.raises(UnsupportedError) as exc:
        K.tangente(K.Complejo(mx.Mul(mx.Num(Fraction(1, 2)), mx.PI), mx.ZERO))
    assert "polo" in str(exc.value)


# ---------------------------------------------------------------------------
# the engine underneath is the one already verified
# ---------------------------------------------------------------------------


def test_las_tabla_de_notables_cubren_toda_la_vuelta():
    """The notable table held 0..pi and the circle does not stop there.

    ``sin(7*pi/6) = -1/2`` is as ordinary a value as ``sin(pi/6)``, and reading the
    same table two ways is how ``sin(0)`` came back unevaluated while ``sin(pi)``
    came back as 0.
    """
    esperado = {
        "sin(0)": 0, "cos(0)": 1, "sin(pi)": 0, "cos(pi)": -1,
        "sin(pi/2)": 1, "cos(pi/2)": 0,
        "sin(3*pi/2)": -1, "cos(3*pi/2)": 0,
        "sin(4*pi/3)": -math.sqrt(3) / 2, "cos(4*pi/3)": -0.5,
        "sin(7*pi/6)": -0.5, "cos(11*pi/6)": math.sqrt(3) / 2,
        "tan(5*pi/4)": 1, "tan(3*pi/4)": -1,
    }
    for texto, valor in esperado.items():
        obtenido = mx.evaluate(T.simplify(mx.parse(texto)))
        assert abs(obtenido - valor) < 1e-12, (texto, obtenido, valor)


def test_el_signo_del_reflejo_es_el_de_la_funcion():
    """``f(2*pi - u)`` is ``-f(u)`` for sine and ``+f(u)`` for cosine.

    Getting that backwards does not produce a wrong sign in one place; it produces
    a table that reads as though it knew both and does.
    """
    for nombre, texto, valor in [
        ("sin", "sin(4*pi/3)", -math.sqrt(3) / 2),
        ("cos", "cos(4*pi/3)", -0.5),
        ("sin", "sin(5*pi/4)", -math.sqrt(2) / 2),
        ("cos", "cos(5*pi/4)", -math.sqrt(2) / 2),
    ]:
        assert abs(mx.evaluate(T.simplify(mx.parse(texto))) - valor) < 1e-12, nombre


def test_negar_dentro_no_cambia_el_valor():
    """The rule that fixes a reflected angle has to keep the expression's value.

    The objective is monotone in node count, so ``Neg(v)`` for an ``n``-node value
    is ``n+1`` nodes and gets rejected as «not an improvement» — which silently
    dropped the sign and gave ``sin(7*pi/6)`` as ``+1/2``. The sign has to go into
    the scalar, which costs nothing.
    """
    assert mx.text(T.simplify(mx.parse("-(-8)"))) == "8"
    assert mx.text(T.simplify(mx.parse("3 + -(-8)"))) == "3 + 8"
    for x in (-0.7, 0.3, 1.1):
        # -(-x) = x, so the reduced value has to equal x, not its opposite
        assert abs(mx.evaluate(mx.parse("-(-x)"), {"x": x}).real - x) < 1e-12
