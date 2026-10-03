# SPDX-License-Identifier: MIT
"""MATH_LAB T-13: trigonometric inequalities and sign charts."""

from __future__ import annotations

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError

#: everything numeric is checked against this rather than against the code's own
#: arithmetic, so a wrong answer cannot agree with itself
PI = 3.141592653589793

#: a value this large is a pole seen through floating point, not a real answer
POLO = 1e12


def texto(caso: str) -> str:
    return I.resolver_inequidad(caso).texto()


def ceros_de(caso: str) -> list[str]:
    return [mx.text(c) for c in I.ceros(mx.parse(caso))]


# ---------------------------------------------------------------------------
# the answers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso,esperado", [
    ("sin(x) > 1/2", "(1/6·π, 5/6·π)   y se repite cada 2·pi"),
    ("sin(x) >= 1/2", "[1/6·π, 5/6·π]   y se repite cada 2·pi"),
    ("sin(x) < 1/2", "[0, 1/6·π) ∪ (5/6·π, 2·π]   y se repite cada 2·pi"),
    ("sin(x) <= 1/2", "[0, 1/6·π] ∪ [5/6·π, 2·π]   y se repite cada 2·pi"),
    ("cos(x) <= 0", "[1/2·π, 3/2·π]   y se repite cada 2·pi"),
    ("cos(x) > 0", "[0, 1/2·π) ∪ (3/2·π, 2·π]   y se repite cada 2·pi"),
    ("cos(x) > -1/2", "[0, 2/3·π) ∪ (4/3·π, 2·π]   y se repite cada 2·pi"),
    ("cos(x) > 1/2", "[0, 1/3·π) ∪ (5/3·π, 2·π]   y se repite cada 2·pi"),
    ("sin(x) + cos(x) > 0", "[0, 3/4·π) ∪ (7/4·π, 2·π]   y se repite cada 2·pi"),
    ("tan(x) > 0", "(0, 1/2·π)   y se repite cada 1·pi"),
    ("tan(x) >= 0", "[0, 1/2·π)   y se repite cada 1·pi"),
    ("cos(2x) > 0", "[0, 1/4·π) ∪ (3/4·π, π]   y se repite cada 1·pi"),
])
def test_las_inecuaciones_basicas_dan_el_conjunto_correcto(caso, esperado):
    assert texto(caso) == esperado


def test_el_signo_estricto_abre_los_extremos_y_el_no_estricto_los_cierra():
    """The endpoints are the whole difference between these two answers.

    The two sets look nearly identical and are genuinely different: a point where
    sin(x) is exactly 1/2 belongs to one and not to the other.
    """
    abierto = I.resolver_inequidad("sin(x) > 1/2")
    cerrado = I.resolver_inequidad("sin(x) >= 1/2")
    assert abierto.conjunto.texto() == "(1/6·π, 5/6·π)"
    assert cerrado.conjunto.texto() == "[1/6·π, 5/6·π]"


def test_el_elegido_tiene_el_extremo_cerrado_y_el_descartado_tambien():
    """The mirror image of the previous test, on the other inequality.

    0 and 2*pi are in both sets here, because sin is 0 there and 0 <= 1/2. Only
    the zeros of the difference are in question, and those are exactly the ends
    that flip between the two answers.
    """
    elegido = I.resolver_inequidad("sin(x) <= 1/2")
    descartado = I.resolver_inequidad("sin(x) < 1/2")
    assert elegido.conjunto.texto() == "[0, 1/6·π] ∪ [5/6·π, 2·π]"
    assert descartado.conjunto.texto() == "[0, 1/6·π) ∪ (5/6·π, 2·π]"


def test_el_extremo_del_periodo_se_lee_en_la_funcion_y_no_se_asume_abierto():
    """0 and 2*pi are points of the chart like any other.

    Leaving the origin always open quietly drops a solution: ``cos(x)^2 > 1/2``
    holds at 0 and the chart begins there. It is the one failure mode that
    survives every check which only looks at the inside of an interval.
    """
    assert I.resolver_inequidad("cos(x)^2 > 1/2").conjunto.texto() \
        == "[0, 1/4·π) ∪ (3/4·π, π]"
    assert I.resolver_inequidad("cos(x) > 0").conjunto.contiene(D.punto_pi(Fraction(0)))
    assert not I.resolver_inequidad("tan(x) > 0").conjunto.contiene(D.punto_pi(Fraction(0)))


def test_el_periodo_minimo_acorta_la_carta_de_signos():
    """sin^2 has period pi, and saying 2*pi would double every interval.

    A valid-but-loose period is not an error in the set — the points are right —
    but it makes the answer twice as long and hides the symmetry that explains it.
    """
    solucion = I.resolver_inequidad("sin(x)^2 - 1/2 > 0")
    assert solucion.periodo == 1
    assert solucion.conjunto.texto() == "(1/4·π, 3/4·π)"


def test_el_producto_de_seno_y_coseno_tambien_acorta_a_pi():
    assert I.resolver_inequidad("sin(x)*cos(x) > 0").periodo == 1
    assert I.resolver_inequidad("sin(x) > 1/2").periodo == 2
    assert I.resolver_inequidad("tan(x) < 1").periodo == 1


def test_las_raices_irracionales_dan_intervalos_exactos_y_no_decimales():
    solucion = I.resolver_inequidad("sin(x) > sqrt(2)/2")
    assert solucion.conjunto.texto() == "(1/4·π, 3/4·π)"
    assert "." not in solucion.conjunto.texto()
    assert I.resolver_inequidad("cos(x) > sqrt(3)/2").conjunto.texto() \
        == "[0, 1/6·π) ∪ (11/6·π, 2·π]"


def test_una_solucion_vacia_lo_dice_y_no_inventa_intervalos():
    solucion = I.resolver_inequidad("sin(x) > 2")
    assert solucion.vacia
    assert solucion.texto() == "no hay soluciones"
    assert solucion.conjunto.texto() == "∅" or not solucion.conjunto.intervalos


def test_una_expresion_que_no_alcanza_el_valor_tampoco_da_soluciones():
    assert I.resolver_inequidad("sin(x) > 2").vacia
    assert I.resolver_inequidad("sin(x) >= 2").vacia
    assert I.resolver_inequidad("cos(x) < -2").vacia


# ---------------------------------------------------------------------------
# poles, denominators, singularities: the part that is easy to forget
# ---------------------------------------------------------------------------


def test_el_polo_de_la_tangente_corta_el_intervalo_por_mitad():
    """tan(x) < 1 is two intervals, and only the poles make it two.

    Looking only at the zeros gives one interval from pi/4 to pi, and that
    interval contains pi/2, where tan does not exist.
    """
    assert texto("tan(x) < 1") == "[0, 1/4·π) ∪ (1/2·π, π]   y se repite cada 1·pi"


def test_la_tangente_al_cuadrado_tiene_el_polo_en_medio_y_sigue_dos_partes():
    assert texto("tan(x)^2 > 1") == "(1/4·π, 1/2·π) ∪ (1/2·π, 3/4·π)   y se repite cada 1·pi"


def test_la_cotangente_tiene_su_polo_cerca_del_cero():
    assert texto("cot(x) > 0") == "(0, 1/2·π)   y se repite cada 1·pi"


def test_un_cociente_de_tangente_no_tiene_ceros_pero_su_polo_sigue_ahi():
    """1/tan(x) never vanishes; what it has is a pole, and the sign flips there."""
    assert ceros_de("1/tan(x)") == []
    assert texto("1/tan(x) > 0") == "(0, 1/2·π)   y se repite cada 1·pi"


def test_la_secante_cambia_de_signo_en_su_polo_sin_tener_ceros():
    assert ceros_de("sec(x)") == []
    assert texto("sec(x) > 0") == "[0, 1/2·π) ∪ (3/2·π, 2·π]   y se repite cada 2·pi"


def test_el_denominador_que_se_anula_es_un_punto_critico_mas():
    """1/cos(x) > 0 holds where cos > 0, and nowhere else."""
    assert texto("1/cos(x) > 0") == "[0, 1/2·π) ∪ (3/2·π, 2·π]   y se repite cada 2·pi"


def test_los_ceros_de_un_denominador_tambien_cortan_la_solucion():
    """cos(x)*sin(x) > 0 must exclude both kinds of zero, not just one."""
    assert texto("sin(x)*cos(x) > 0") == "(0, 1/2·π)   y se repite cada 1·pi"


def test_el_producto_de_dos_funciones_toma_los_ceros_de_las_dos():
    assert set(ceros_de("sin(x)*cos(x)")) == {"0*pi", "1/2*pi", "1*pi", "3/2*pi"}


def test_un_cociente_hereda_solo_los_ceros_del_numerador():
    """The zeros of a/b are the zeros of a; the poles of b are a separate matter."""
    ceros = ceros_de("sin(x)/cos(x)")
    assert "1/2*pi" not in ceros      # that is where the denominator dies
    assert "0*pi" in ceros


def test_elevar_a_una_potencia_no_mueve_los_ceros():
    """f^n = 0 exactly where f = 0, for every positive integer n.

    Squaring does not double the zeros and does not move them anywhere; treating
    an even power as a separate case is the error, and it is an error that would
    report «there are none» about an expression full of them.
    """
    for exponente in (2, 3, 4, 5):
        assert set(ceros_de(f"sin(x)^{exponente}")) == set(ceros_de("sin(x)"))
    assert set(ceros_de("(sin(x) - 1/2)^2")) == set(ceros_de("(sin(x) - 1/2)"))


def test_las_singularidades_de_las_funciones_no_necesitan_denominador():
    """tan(x) has a pole at pi/2 with nothing in the expression that divides."""
    assert {mx.text(s) for s in I.singularidades(mx.parse("tan(x)"))} \
        == {"1/2*pi", "3/2*pi"}
    assert {mx.text(s) for s in I.singularidades(mx.parse("cot(x)"))} \
        == {"0*pi", "1*pi"}
    assert {mx.text(s) for s in I.singularidades(mx.parse("sec(x)"))} \
        == {"1/2*pi", "3/2*pi"}


def test_una_funcion_sin_polos_no_declara_ninguno():
    assert I.singularidades(mx.parse("sin(x)*cos(x)")) == []
    assert I.singularidades(mx.parse("sin(x) - 1/2")) == []


# ---------------------------------------------------------------------------
# where the expression exists at all — the other half of T-13
# ---------------------------------------------------------------------------


#: What the engine publishes for each expression. The note at the end of a
#: periodic set is the whole point of this list and it used not to be there:
#: `dominio()` found the holes of ONE period, took them out of the whole line,
#: and published `(-inf, 0) U (0, pi) U (pi, 2pi) U (2pi, inf)` for `1/sen(x)`
#: as if `3*pi` were in the domain. It is not: asked about it, the set said yes
#: and the evaluator said `None`. A set whose holes are infinite has to SAY it
#: repeats, or the finite list of holes it prints lies about every point outside
#: the first period. The intervals themselves did not change: what was wrong was
#: the claim that a window onto one period was the whole line.
#: What the engine publishes for each expression. The note at the end of a
#: periodic set is the whole point of this list and it used not to be there:
#: `dominio()` found the holes of ONE period, took them out of the whole line,
#: and published `(-inf, 0) U (0, pi) U (pi, 2pi) U (2pi, inf)` for `1/sen(x)`
#: as if `3*pi` were in the domain. It is not: asked about it, the set said yes
#: and the evaluator said `None`. A set whose holes are infinite has to SAY it
#: repeats, or the finite list of holes it prints lies about every point outside
#: the first period.
#:
#: The intervals themselves did not change. What was wrong was the claim that a
#: window onto one period was the whole line.
DOMINIOS = [
    ("sin(x)", 'ℝ'),
    ("cos(x)", 'ℝ'),
    ("tan(x)", '(-∞, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, ∞)   y se repite cada π'),
    ("cot(x)", '(-∞, 0) ∪ (0, π) ∪ (π, ∞)   y se repite cada π'),
    ("csc(x)", '(-∞, 0) ∪ (0, π) ∪ (π, ∞)   y se repite cada 2·π'),
    ("sec(x)", '(-∞, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, ∞)   y se repite cada 2·π'),
    ("1/sin(x)", '(-∞, 0) ∪ (0, π) ∪ (π, 2·π) ∪ (2·π, ∞)   y se repite cada 2·π'),
    ("1/cos(x)", '(-∞, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, ∞)   y se repite cada 2·π'),
    ("tan(x) + 1/cos(x)", '(-∞, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, ∞)   y se repite cada 2·π'),
    ("asin(sin(x))", '[0, 1/2·π] ∪ [1/2·π, 3/2·π] ∪ [3/2·π, 2·π]   y se repite cada 2·π'),
    ("asin(2*sin(x))", '[0, 1/6·π] ∪ [5/6·π, 7/6·π] ∪ [11/6·π, 2·π]   y se repite cada 2·π'),
    ("atanh(sin(x))", '[0, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, 2·π]   y se repite cada 2·π'),
    ("acosh(1+cos(x))", '[0, 1/2·π] ∪ [3/2·π, 2·π]   y se repite cada 2·π'),
    ("ln(sin(x))", '(0, π)   y se repite cada 2·π'),
    ("sqrt(sin(x))", '[0, π]   y se repite cada 2·π'),
    ("sqrt(cos(x))", '[0, 1/2·π] ∪ [3/2·π, 2·π]   y se repite cada 2·π'),
    ("asin(x)", '[-1, 1]'),
    ("acos(x)", '[-1, 1]'),
    ("atanh(x)", '(-1, 1)'),
    ("acosh(x)", '[1, ∞)'),
    ("ln(x)", '(0, ∞)'),
    ("ln(-x)", '(-∞, 0)'),
    ("ln(x^2-1)", '(-∞, -1) ∪ (1, ∞)'),
    ("sqrt(x-1)", '[1, ∞)'),
    ("asin(2*x-1)", '[0, 1]'),
    ("1/(x^2-1)", '(-∞, -1) ∪ (-1, 1) ∪ (1, ∞)'),
    ("asinh(x)", 'ℝ'),
    ("atan(x)", 'ℝ'),
]




@pytest.mark.parametrize("caso,esperado", DOMINIOS)
def test_el_dominio_sabe_donde_existe_la_expresion(caso, esperado):
    assert I.dominio(mx.parse(caso)).texto() == esperado


@pytest.mark.parametrize("caso,esperado", DOMINIOS)
def test_el_dominio_no_incluye_un_punto_onde_no_existe(caso, esperado):
    """The independent path: sample the reported set and evaluate there.

    The set algebra could be right while the set is wrong — a chart that forgot a
    pole would say so and be consistent with itself. Evaluating the original
    expression at points the set claims is the only thing that catches it.
    """
    conjunto = I.dominio(mx.parse(caso))
    for coeficiente in [Fraction(k, 97) for k in range(-200, 200)]:
        punto = D.punto_pi(coeficiente)
        if not conjunto.contiene(punto):
            continue
        valor = mx.evaluate(mx.parse(caso),
                            {"x": float(coeficiente) * 3.141592653589793})
        assert valor is None or abs(valor) < 1e12 or abs(valor.imag) < 1e-12, (
            f"{caso}: {coeficiente}*pi entra en el dominio pero allí vale "
            f"{valor}")


def test_el_dominio_de_un_polono_no_necesita_que_se_sepa_que_es_periodico():
    """``asin(x)`` is not periodic, and its answer has no period in it.

    Reading «the zeros are unknown» as «this is periodic» sends every aperiodic
    condition down the periodic chart, where it is refused for the wrong reason.
    """
    conjunto = I.dominio(mx.parse("asin(x)"))
    assert conjunto.contiene(D.punto(Fraction(0)))
    assert conjunto.contiene(D.punto(Fraction(1)))
    assert not conjunto.contiene(D.punto(Fraction(2)))
    assert not conjunto.contiene(D.punto(Fraction(-2)))


def test_un_extremo_infinito_nunca_se_cierra():
    """Printing ``(0, inf]`` claims a point at infinity."""
    texto = I.dominio(mx.parse("ln(x)")).texto()
    assert texto == "(0, ∞)"
    assert "]" not in texto


def test_el_dominio_rechaza_lo_que_no_sabe_en_vez_de_adivinar():
    """A denominator whose zeros are an irrational pair cannot be named exactly."""
    with pytest.raises(UnsupportedError) as exc:
        I.dominio(mx.parse("1/(x^2-2)"))
    assert "no se saben los ceros" in str(exc.value) or "no lo sabe" in str(exc.value)


def test_ceros_en_puntos_solo_acepta_conjuntos_finitos():
    """A trigonometric zero is a multiple of pi, and there are infinitely many."""
    assert I.ceros_en_puntos(mx.parse("x^2-1")) == [D.punto(Fraction(-1)),
                                                    D.punto(Fraction(1))]
    assert I.ceros_en_puntos(mx.parse("sin(x)")) is None
    assert I.ceros_en_puntos(mx.parse("x^2+1")) == []


def test_el_dominio_excluye_cada_polo_y_cada_cero_de_denominador():
    """The two halves of T-13 must not disagree about what exists.

    A zero is not the same thing as a hole: ``tan(0)`` is a zero *and* the function
    exists there. What has to be outside the domain are the poles and the zeros of
    the denominators, and asking for those is the whole point of computing them
    twice by different routes.
    """
    for caso in ("1/sin(x)", "tan(x)", "cot(x)", "sec(x)", "1/cos(x)",
                 "1/(sin(x)*cos(x))", "tan(x) + 1/cos(x)"):
        expresion = mx.parse(caso)
        conjunto = I.dominio(expresion)
        excluidos: list = []
        for denominador in D.denominadores(expresion):
            c = I.ceros(denominador, "x")
            if c is not None:
                excluidos.extend(D.punto_pi(I._coeficiente_pi(v)) for v in c)
        polos = I.singularidades(expresion, "x")
        if polos is not None:
            excluidos.extend(D.punto_pi(I._coeficiente_pi(v)) for v in polos)
        assert excluidos, caso
        for punto in excluidos:
            assert not conjunto.contiene(punto), (
                f"{caso}: {punto} es un punto donde no existe y el dominio lo "
                f"incluye: {conjunto.texto()}")


# ---------------------------------------------------------------------------
# «no lo sé» is not «no hay soluciones»
# ---------------------------------------------------------------------------


def test_una_expresion_no_periodica_se_rechaza_diciendo_por_que():
    with pytest.raises(UnsupportedError) as exc:
        I.resolver_inequidad("x > 0")
    assert "no es periódica" in str(exc.value)


def test_un_cero_exacto_fuera_de_la_rejilla_de_pi_se_coloca_igual():
    """0.1234567 no es un multiplo de pi, su arcseno tampoco, y aun asi se puede.

    Esta prueba estuvo Years asserting the OPPOSITE: que ``sen(x) > 0.1234567``
    tenia que negarse porque no se podia nombrar ningun punto critico exacto. La
    negativa era cierta en su momento y falsa en cuanto se pudo resolver, y una
    prueba que documenta un hueco se acaba convirtiendo en una prueba que lo
    bloquea. Por eso esta comprueba la RESPUESTA, y no la ausencia de respuesta.

    El punto critico no es ``pi/2``: es ``arcsen(1234567/10000000)``, que el
    solucionador de ecuaciones ya escribia desde hacia tiempo. Lo que faltaba era
    una carta de signos que aceptara un punto que no cae en la rejilla de
    multiplos de pi.
    """
    s = I.resolver_inequidad("sen(x) > 0.1234567")
    # `texto()` is the ASCII form, so the function prints as `asin`; the Spanish
    # spelling is `mx.pretty`, and this engine is careful about which one round-trips
    assert s.conjunto.texto() == (
        "(asin(1234567/10000000), pi - asin(1234567/10000000))"), s.conjunto.texto()
    assert s.periodo == Fraction(2), s.periodo


def test_una_expresion_cuyos_ceros_no_se_saben_sigue_negandose():
    """El rechazo sigue existiendo, y con el motivo escrito.

    Lo que se cerro fue la carta de signos, no el solucionador de ecuaciones:
    ``sen(x)*cos(x) - 0.1234567`` sigue sin ceros que el motor sepa escribir, y ahi
    la respuesta correcta es negarse y decirlo.
    """
    with pytest.raises(UnsupportedError) as exc:
        I.resolver_inequidad("1/(sen(x)*cos(x) - 0.1234567) > 0")
    assert "no se saben" in str(exc.value)


def test_un_denominador_desconocido_tambien_rehusa_y_lo_dice():
    with pytest.raises(UnsupportedError) as exc:
        I.resolver_inequidad("1/(sin(x)*cos(x) - 0.1234567) > 0")
    assert "no se saben" in str(exc.value)


def test_ceros_devuelve_none_y_no_una_lista_vacia_cuando_no_sabe():
    """None means «I don't know». [] would mean «there are none», which is a claim."""
    # `sen(x) - 0.1234567` estuvo aqui: sus ceros son `arcsen(1234567/10000000)` y su
    # reflejo, el motor los escribe exactamente, y una lista de ceros que declara
    # no saber escribir un numero que si sabe escribir es una lista equivocada.
    assert [mx.text(v) for v in I.ceros(mx.parse("sin(x) - 0.1234567"))] == [
        "asin(1234567/10000000)", "pi - asin(1234567/10000000)"]
    assert I.ceros(mx.parse("(sin(x)*cos(x) - 0.1234567)^2")) is None
    assert I.ceros(mx.parse("sin(x) - 1/2")) is not None


def test_una_constante_sin_incógnita_no_tiene_ceros_que_buscar():
    assert I.ceros(mx.parse("1 - 2")) == []
    assert I.ceros(mx.parse("2 - 2")) is None    # the whole expression is zero


def test_falta_el_signo_de_comparacion_se_dice_que_falta():
    with pytest.raises(UnsupportedError) as exc:
        I.resolver_inequidad("sin(x) 1/2")
    assert "comparación" in str(exc.value)


def test_un_lado_vacio_se_dice_que_falta():
    with pytest.raises(UnsupportedError) as exc:
        I.resolver_inequidad("sin(x) >")
    assert "vacío" in str(exc.value)


def test_una_ecuacion_tambien_se_puede_plantear_como_desigualdad():
    """«=» is a legitimate operator, and it does not go through the sign chart.

    An equation has no interior: the solution is the zeros themselves, so they are
    reported as points rather than as intervals. Squeezing them into a degenerate
    interval would read as an empty one, which is the opposite of the truth.
    """
    solucion = I.resolver_inequidad("sin(x) = 1/2")
    assert [p.texto() for p in solucion.puntos] == ["1/6·π", "5/6·π"]
    assert solucion.conjunto.vacio
    assert not solucion.vacia
    assert solucion.texto().startswith("x = 1/6·π, 5/6·π")


def test_una_ecuacion_sin_solucion_lo_dice_como_tal():
    assert I.resolver_inequidad("sin(x) = 2").vacia
    assert I.resolver_inequidad("sin(x) = 2").texto() == "no hay soluciones"


def test_los_polos_no_son_solucion_de_una_ecuacion():
    """tan(x) = 0 has 0 and pi as solutions and not pi/2, where tan does not exist."""
    solucion = I.resolver_inequidad("tan(x) = 0")
    assert [p.texto() for p in solucion.puntos] == ["0"]
    assert not solucion.contiene(Fraction(1, 2))


def test_la_ecuacion_tambien_se_repite_y_lo_dice():
    assert "se repite cada 2·pi" in I.resolver_inequidad("sin(x) = 1/2").texto()
    assert "se repite cada 1·pi" in I.resolver_inequidad("tan(x) = 1").texto()


# ---------------------------------------------------------------------------
# the answers agree with the inequality, checked point by point
# ---------------------------------------------------------------------------


def _cumplice(operador: str, valor: float | None) -> bool:
    if valor is None:
        return False
    if operador == ">":
        return valor > 1e-9
    if operador == ">=":
        return valor > -1e-9
    if operador == "<":
        return valor < -1e-9
    if operador == "<=":
        return valor < 1e-9
    return abs(valor) < 1e-9


CASOS_NUMERICOS = [
    "sin(x) > 1/2", "sin(x) >= 1/2", "sin(x) < 1/2", "sin(x) <= 1/2",
    "cos(x) <= 0", "cos(x) > 0", "cos(x) > -1/2", "tan(x) < 1", "tan(x) >= 0",
    "1/tan(x) > 0", "sin(x)*cos(x) > 0", "sec(x) > 0", "cot(x) > 0",
    "sin(x)+cos(x) > 0", "sin(x)^2 - 1/2 > 0", "cos(x)^2 > 1/2",
    "sin(x) > sqrt(2)/2", "cos(x) < -sqrt(2)/2", "cos(x) > sqrt(3)/2",
    "csc(x) > 0", "1/cos(x) > 0", "tan(x)^2 > 1", "sin(x) > 2",
    "cos(x) >= -1/2", "1/sin(x) > 0", "sin(x) = 1/2", "cos(x) = 0",
]


@pytest.mark.parametrize("caso", CASOS_NUMERICOS)
def test_la_solucion_reportada_es_exactamente_donde_se_cumple(caso):
    """The independent path: sample, then compare membership against the value.

    Every point is tested in both directions — it must be in the set exactly when
    the inequality holds, and outside it exactly when it fails. A set that were
    merely a subset of the truth would pass one direction and fail the other, so
    the two-way comparison is what makes this a check and not a smoke test.

    Points are exact rationals, not floats, so the ones that land on an endpoint
    test the open/closed flags instead of dodging them.
    """
    operador, izquierda, derecha = I._separa(caso)
    expresion = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    solucion = I.resolver_inequidad(caso)

    for coeficiente in _muestras(solucion.periodo):
        x = float(coeficiente) * PI
        valor = mx.evaluate(expresion, {"x": x})
        dentro = solucion.contiene(coeficiente)
        if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > POLO:
            # where the expression does not exist, the set must not claim it
            assert not dentro, f"{caso}: {coeficiente}*pi no existe y aun así entra"
            continue
        assert dentro == _cumplice(operador, valor.real), (
            f"{caso}: en {coeficiente}*pi el conjunto dice {dentro} pero "
            f"f vale {valor.real}")


@pytest.mark.parametrize("caso", CASOS_NUMERICOS)
def test_lo_que_queda_fuera_tambien_se_puede_justificar(caso):
    """The complement is checked too: a set with a hole in it would pass the above.

    Same sampling, same expression, but now the claim is about the points that
    were left out — they must fail the inequality.
    """
    operador, izquierda, derecha = I._separa(caso)
    expresion = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    solucion = I.resolver_inequidad(caso)

    for coeficiente in _muestras(solucion.periodo):
        x = float(coeficiente) * PI
        valor = mx.evaluate(expresion, {"x": x})
        if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > POLO:
            continue
        if not solucion.contiene(coeficiente):
            assert not _cumplice(operador, valor.real), (
                f"{caso}: {coeficiente}*pi queda fuera del conjunto pero "
                f"la desigualdad sí se cumple (f vale {valor.real})")


def _muestras(periodo_pi: Fraction) -> list[Fraction]:
    """Exact rationals across one period, so endpoints are hit exactly."""
    return [Fraction(i, 400) % periodo_pi for i in range(1, 2 * 400)]


# ---------------------------------------------------------------------------
# what the answer says about how it got there
# ---------------------------------------------------------------------------


def test_la_hipotesis_explica_que_el_signo_se_decide_numericamente():
    solucion = I.resolver_inequidad("sin(x) > 1/2")
    assert any("numéricamente" in h for h in solucion.hipotesis)
    assert any("una prueba y no una aproximación" in h
               for h in solucion.hipotesis)


def test_un_periodo_en_vez_de_una_enumeracion_infinita():
    solucion = I.resolver_inequidad("sin(x) > 1/2")
    assert "se repite cada 2·pi" in solucion.texto()
    assert any("un solo periodo" in h for h in solucion.hipotesis)


def test_con_un_polo_de_por_medio_se_avisa_de_que_eso_tambien_corta():
    solucion = I.resolver_inequidad("tan(x) < 1")
    assert any("no existe" in h for h in solucion.hipotesis)


def test_sin_polos_no_hay_que_avisar_de_ellos():
    solucion = I.resolver_inequidad("sin(x) > 1/2")
    assert not any("no existe" in h for h in solucion.hipotesis)


def test_el_operador_sobrevive_en_la_solucion():
    assert I.resolver_inequidad("sin(x) > 1/2").operador == ">"
    assert I.resolver_inequidad("sin(x) <= 1/2").operador == "<="
    assert I.resolver_inequidad("sin(x) = 1/2").operador == "="


def test_el_codigo_tiene_un_refuslo_por_cada_razon_por_la_que_se_rechaza():
    """Each refusal has to be a real, reachable one — not decoration."""
    import inspect

    fuente = inspect.getsource(I.resolver_inequidad)
    for motivo in ("no es periódica", "no se saben los ceros",
                   "denominador", "no se sabe dónde están los polos",
                   "no se pueden escribir como múltiplos"):
        assert motivo in fuente, f"falta el refuslo por: {motivo}"


def test_el_signo_que_cambia_dentro_de_un_hueco_se_rechaza_en_lugar_de_adivinarse():
    """The safety net that protects every other case.

    If a gap ever held a sign change with no zero and no pole inside it, the chart
    would be wrong. Rather than pick a side, the module refuses — because the
    honest reading of that situation is «I have missed something», not «I know
    which half it is».
    """
    import inspect

    fuente = inspect.getsource(I._signo_del_hueco)
    assert "sin_refuso" in fuente
    assert "no debería pasar" in fuente
