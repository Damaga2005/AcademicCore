# SPDX-License-Identifier: MIT
"""El solucionador no puede responder una ecuacion que no le han Asked.

Dos bugs distintos, los dos del mismounderlying tipo: mirar una cosa y no mirar
la otra.

**La sustitucion sin mirar el argumento.** ``_como_polinomio`` reemplazaba todo
``cos(·)`` por ``u`` sin mirar que habia dentro, de modo que ``cos(x) + cos(2x)``
se converitia en ``2u`` y el motor contestaba ``cos(x) = 0`` — las soluciones de
OTRA ecuacion — a la que se le Ask. ``cos(x) + cos(2x) = 0`` publicaba
``{pi/2, -pi/2}`` y el dominio de ``1/(cos(x) + cos(2x))`` heredaba dos huecos
que no lo son mientras se le escapaban los tres que si lo son.

**La comprobacion asimetrica del argumento.** En ``_caso_fase`` el argumento se
comprobaba en la rama del coseno y no en la del seno, que ademas asignaba ``u``
sin mirar. ``cos(x) - sen(2x)`` se leia como una sola funcion de un solo angulo
con dos nombres, y contestaba ``{pi/8, 5pi/8, ...}``, que son las soluciones de
``tg(2x) = 1``.

Las dos formas de fallo son la misma: una sustitucion que no se comprueba donde se
hace. Y el guardia que ya existia no las veia, porque al borrar ``2x`` no queda
nada fuera de sitio.

Este fichero mide las dos cosas que sí se pueden medir sin la opinión del motor:

- **sonido** — cada punto publicado tiene que anular la ecuacion;
- **completitud** — cada raiz real tiene que estar cerca de un punto publicado,
  y las raices se buscan por CAMBIO DE SIGNO, que no depende de donde caiga la
  raiz. Buscar «si es exactamente cero» solo ve las que caen en la rejilla, y
  entonce una respuesta erronea parece incompleta en vez de erronea.
"""

from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import mvexpr as mx

MUESTRAS = 1500


def _f(ecuacion: str):
    """``izq - der`` as a callable of x, through Python's own arithmetic."""
    izq, der = ecuacion.split("=")
    txt = (izq.strip() + " - (" + der.strip() + ")").replace("^", "**")
    for nombre in ("cos", "sin", "tan", "tg"):
        txt = txt.replace(f"{nombre}(", f"math.{nombre}(")
    return eval(f"lambda x: {txt}", dict(math=math))       # noqa: S307


def _fusiona(valores, tol=1e-6):
    salida = []
    for v in sorted(valores):
        if not salida or v - salida[-1] > tol:
            salida.append(v)
    return salida


def _raices(ecuacion: str) -> list[float]:
    """Roots over one period by sign change, in multiples of pi."""
    f = _f(ecuacion)
    paso = 2 * math.pi / MUESTRAS
    brutos, anterior = [], None
    for j in range(MUESTRAS + 1):
        x = j * paso
        try:
            v = f(x)
        except (ValueError, ZeroDivisionError):
            v = None
        if v is None:
            anterior = None                 # a pole only suspends the test
            continue
        if abs(v) < 1e-11:
            brutos.append(x)
        elif anterior is not None and anterior * v < 0:
            izq, der = x - paso, x
            for _ in range(50):
                medio = (izq + der) / 2
                vm = f(medio)
                if vm is None:
                    break
                if f(izq) * vm <= 0:
                    der = medio
                else:
                    izq = medio
            raiz = (izq + der) / 2
            # A sign change ACROSS A POLE is not a root, and the bisection cannot
            # tell the two apart by where it lands: both converge. What separates
            # them is that a root is where the function IS zero, and a pole is
            # where it is not. Checking |f| at the root is the difference between
            # four solutions and four phantom ones for `tg(2x) = 1`, whose poles
            # sit at pi/4 + k·pi/2 — close enough to the sampling that no
            # magnitude threshold on the neighbours sees them coming.
            if abs(f(raiz)) < 1e-6:
                brutos.append(raiz)
        anterior = v

    def en_periodo(b: float) -> float:
        b %= 2 * math.pi
        # The sweep ENDS exactly at 2·pi, and the modulo of that is a residue of
        # about 1e-15 rather than 0 — so `x = 2·pi` gets counted as a root distinct
        # from `x = 0`, which is the same point. It showed up as a seventh root of
        # `sen(x)**3 - sen(x)/2 = 0`, an equation with six, and it is worth writing
        # down why: the harness is the instrument, and an instrument that ADDS
        # points accuses the engine of inventing solutions.
        return 0.0 if b > 2 * math.pi - 1e-6 else b

    return _fusiona(en_periodo(b) for b in brutos)


def _publicados(ecuacion: str):
    """``(valores exactos, conjunto redondeado, numero de familias)`` or None."""
    r = E.resolver(ecuacion)
    if r.refusos:
        return None
    exactos, crudos = [], []
    for f in r.familias:
        if not f.en_x:
            return None
        for k in range(-8, 9):
            v = mx.evaluate(f.miembro(k, "x"), {"x": 0})
            if v is None or abs(getattr(v, "imag", 0.0)) > 1e-9:
                return None
            exactos.append(float(v.real) / math.pi)
            crudos.append((float(v.real) / math.pi) % 2.0)
    return exactos, _fusiona(crudos), len(r.familias)


#: Equations the engine answers today. Every one of these is checked for SOUNDNESS
#: and COMPLETENESS, so a wrong answer fails here even when it looks plausible.
RESPONDIDAS = [
    "cos(x) = 0", "cos(2*x) = 0", "sin(x) = 0", "sin(2*x) = 0",
    "cos(3*x) = 1/2", "sin(3*x) = 1/2", "tan(2*x) = 1", "cos(x)^2 = 1/2",
    "sin(x) + sin(x)^2 = 0", "cos(x) + 1 = 0", "2*sin(2*x) = 1",
    "sin(x) + cos(x) = 0", "cos(x/2) = 1/2", "sin(x/2) = 1/3",
    "1 + 2*cos(x) = 0", "sin(x)*sin(x) = 1/4",
    "sin(x)*cos(x) = 0", "sin(2*x)*cos(x) = 0",
    "cos(x)*sin(2*x) = 0", "sin(x)^2*cos(x) = 0", "sin(x)*cos(x)^2 = 0",
    "(sin(x) - 1/2)*cos(x) = 0", "sin(x)*x = 0",
    # Four that used to be answered with HALF the solutions and no warning: the
    # polynomial in one trigonometric function is cubic and the rational root
    # theorem could only see the rational root of it.
    "sin(x)^3 - sin(x)/2 = 0", "cos(x)^3 - cos(x)/2 = 0",
    "sin(x) - sin(x)^3/2 = 0", "cos(x) - cos(x)^3 = 0",
    "1/cos(x)^5 = 32", "1/cos(x)^6 = 64",
    # Eight that used to be refused because a MULTIPLE ANGLE sat next to another
    # term: `cos(x) + cos(2x) = 0` is not a cosine equation and not a polynomial in
    # one function, because the second term is a cosine of a DIFFERENT argument.
    # Written in powers of the same function it is `cos x + 2cos²x - 1`, which is
    # the shape that was already solved — `cos(x)² = 1/2` — and the root finder finishes
    # the rest.
    "cos(x) + cos(2*x) = 0", "cos(x) + cos(2*x) = 1",
    "cos(x) - cos(2*x) = 0", "cos(2*x) - cos(x) = 0",
    "2*cos(2*x) + 2*cos(x) = 0", "cos(2*x) + cos(x) - 1 = 0",
    "cos(3*x) + cos(x) = 0", "sin(3*x) - sin(x) = 0",
    # Four that were refused for the same reason one step further along: after the
    # multiple angle is developed they are a SUM with a factor repeated in every
    # term — `sen x + 2sen x cos x` — and the product rule cannot see a product in
    # that. Pulling the common factor out gives `sen x·(1 + 2cos x) = 0`, which asks
    # the two questions the engine already answered on its own.
    "sin(x) + sin(2*x) = 0", "sin(x) - sin(2*x) = 0",
    "cos(x) - sin(2*x) = 0", "sin(2*x) - sin(x) = 0",
    # `tg(x)·sen(x) = 0` has `tg` undefined at pi/2 + k·pi, so the FACTORS have
    # different domains — and the solution set is `k·pi`, none of which is a hole.
    # The rule that refused it compared the factors against each other, which is
    # too strong; asking the domain of the PRODUCT and checking each point is the
    # exact condition.
    "tan(x)*sin(x) = 0",
    # `tg(x) + cos(x) = 0` is `sen(x)/cos(x) + cos(x) = 0`. `as_ratio` could not see
    # the quotient because it reads `tg(x)` as an ATOM — there is no division in
    # `cos(x) + tg(x)` — so the rational case never fired. Written as the quotient
    # it is, the denominator appears, and with `cos**2 = 1 - sen**2` it becomes a
    # polynomial in one function: `sen²x - sen x - 1 = 0`.
    "tan(x) + cos(x) = 0",
    # A cubic by Cardano. Irreducible means «no RATIONAL root», not «unsolvable»:
    # a cubic always has a real root, and refusing this one was refusing arithmetic
    # rather than the engine. `cos(3x) + cos(x) = 1` develops to `4c^3 - 2c - 1`.
    "cos(3*x) + cos(x) = 1",
]

#: The two that used to be answered with a DIFFERENT equation's solutions. They
#: are in the list because a refusal is now the right answer for them, and a
#: refusal is a result that can be checked: no family may be published.
NEGADAS_ANTES = [
    "sin(x) + sin(2*x) = 1",
    "sin(2*x) + sin(x) = 1",
    # Two products whose factors do NOT share a domain. `tg(x)` does not exist at
    # pi/2 and `sen(x)` does, so `A·B = 0` is not `A = 0` or `B = 0` there: at
    # `x = pi/2` the product is `0·0·undefined` and the equation is not even
    # posed. A family cannot be published with holes, so the whole thing refuses.
    "sin(x)*cos(x)*tan(x) = 0",
]


#: Equations the engine answers with SOME of the roots and has to SAY SO. Each is a
#: polynomial in one trigonometric function whose degree is 3 or more, so factoring
#: out the rational roots leaves a factor of degree 4 that this engine does not
#: solve. They were the hole in this file: not one of the 41 equations in
#: RESPONDIDAS produced a polynomial with irrational roots, so a wrong answer here
#: passed 41 soundness and completeness checks without being seen.
#:
#: They are in RESPONDIDAS too, and that is not a contradiction: for THESE the roots
#: that are left out are complex, so the answer is right. What is pinned here is not
#: that the answer is wrong but that the engine does not KNOW that it is right — it
#: got there by finding the rational roots and cannot prove the others are not
#: real, and the difference between those two states is what the note says.
PARCIALES = [
    "1/cos(x)^5 = 32",
    "1/cos(x)^6 = 64",
]


@pytest.mark.parametrize("ecuacion", PARCIALES)
def test_una_respuesta_parcial_dice_que_lo_es(ecuacion):
    """A partial answer is a wrong answer unless it says it is partial.

    The gap is real and this file does not close it: completing the roots needs a
    quadratic formula on what is left after dividing out the rational ones, and
    every attempt so far has broken something else. What is asserted here is the
    lesser and still necessary thing — that the engine stops presenting half an
    answer as a whole one. The sentence existed and was thrown away one line after
    it was computed.
    """
    r = E.resolver(ecuacion)
    assert r.familias, f"{ecuacion}: se nega, y no deberia"
    motivos = [h for h in r.hipotesis if "racional" in h or "grado" in h]
    assert motivos, (f"{ecuacion} publica {[mx.text(f.base) for f in r.familias]} "
                     f"sin decir que le faltan raíces: {r.hipotesis}")


def test_completar_las_raices_quito_cuatro_de_las_seis():
    """What the completion bought, counted, so that «better» means something.

    ``sen(x)³ - sen(x)/2 = 0`` is ``-u³ + u/2``, and the rational root theorem finds
    ``u = 0`` and stops. The engine used to publish ``{0, pi}`` — **four of the six
    solutions** — and say nothing: ``sen x = 0`` gives two of them and
    ``sen²x = 1/2`` gives the other four. Factoring out the rational roots leaves a
    quadratic, and ``-4u³ + 2u`` is the plainest case of it.

    The count is written down because getting it wrong is easy and the arithmetic is
    not the engine's: a test that asserted «eight» here failed against a sweep that
    found seven distinct points modulo ``2·pi`` and seven of them right.

    If a future change ever loses this, the answer is incomplete again and this
    fails. If a future change completes it further, the assertion on the count has
    to be updated deliberately, which is the point of writing it down.
    """
    ecuacion = "sin(x)^3 - sin(x)/2 = 0"
    verdad = {round(v / math.pi, 4) for v in _raices(ecuacion)}
    _exactos, puntos, _n = _publicados(ecuacion)
    faltan = [p for p in sorted(verdad)
              if all(min(abs(p - q), 2.0 - abs(p - q)) > 5e-3 for q in puntos)]
    assert len(verdad) == 6, sorted(verdad)          # six is six
    assert not faltan, f"vuelve a faltar {faltan}"


def test_una_nota_que_no_puede_afirmar_no_dice_que_sea_falso():
    """The wording is the claim, and there are three different things to say.

    «No hay raíces» — false, the answer would be wrong. «No lo sí» — true and
    useless. «Sén estas, y de las demás no puedo afirmar que sean reales» — true, and
    the only one of the three that leaves the student able to act on it. The third
    is what this engine can actually support, so the second is out.
    """
    for ecuacion in PARCIALES:
        r = E.resolver(ecuacion)
        notas = [h for h in r.hipotesis if "no puede" in h]
        assert notas, (ecuacion, r.hipotesis)
        assert not any("no hay raíces" in h or "no existen" in h
                       for h in r.hipotesis), r.hipotesis


@pytest.mark.parametrize("ecuacion", RESPONDIDAS)
def test_ninguna_solucion_publicada_inventa_un_punto(ecuacion):
    """Soundness: every published point has to annul the equation.

    Evaluated at the EXACT value of a member, not at the rounded one used to
    compare sets: rounding a position to five decimals and then demanding the
    equation vanish to 1e-7 there calls `4/3` a false solution, which is how a
    previous version of this file accused the engine of inventing things.
    """
    f = _f(ecuacion)
    falsos = [p for p in _publicados(ecuacion)[0] if abs(f(p * math.pi)) > 1e-7]
    assert not falsos, f"{ecuacion}: publica {[round(p, 4) for p in falsos]}, que no la anulan"


@pytest.mark.parametrize("ecuacion", RESPONDIDAS)
def test_no_deja_sin_contar_ninguna_solucion(ecuacion):
    """Completeness: every real root has to be near a published point."""
    _exactos, puntos, _n = _publicados(ecuacion)
    perdidos = [round(v / math.pi, 4) for v in _raices(ecuacion)
                if all(min(abs(v / math.pi - p), 2.0 - abs(v / math.pi - p)) > 5e-3
                       for p in puntos)]
    assert not perdidos, f"{ecuacion}: no publica {perdidos}"


@pytest.mark.parametrize("ecuacion", NEGADAS_ANTES)
def test_una_ecuacion_que_no_se_sabe_no_publica_familias(ecuacion):
    """A refusal is the honest answer; publishing families is not one.

    These used to be answered with the solutions of a different equation. Each of
    them has real solutions — the sign-change sweep finds them — so «se niega» is
    an admission of a gap, not a claim that there is none. That is the whole point:
    §5.4 says «no lo sé» is not «no hay».
    """
    r = E.resolver(ecuacion)
    publicas = [mx.text(f.base) for f in r.familias]
    assert not publicas, (f"{ecuacion} publica {publicas} sin saber resolverla")
    if r.refusos:
        assert any("no" in h for h in r.refusos), r.refusos


def test_la_sustitucion_mira_el_argumento_y_no_solo_el_nombre():
    """The bug in one assertion: `cos(2x)` is not a value of `cos(x)`.

    ``cos(x) + cos(2x) = 0`` in one substitution is ``2u``, whose only root is
    ``u = 0``; read back through ``cos(x) = 0`` that is ``{pi/2, -pi/2}``, and the
    equation that was asked has solutions at ``pi/3, pi, 5pi/3``.
    """
    from academic_core.domain.engineering.mathlab import mvexpr as M
    from academic_core.domain.engineering.mathlab.ecuaciones import _como_polinomio

    u = M.Sym("u")
    assert _como_polinomio(M.parse("cos(x) + cos(2*x)"), "cos", u, "x") is None
    assert _como_polinomio(M.parse("cos(x) + cos(x)"), "cos", u, "x") is not None


def test_el_argumento_compartido_se_deshace_con_su_escala():
    """``tg(x/2) = -1`` is ``x = -pi/2 + 2k·pi``, not ``x = -pi/4 + k·pi``.

    The polynomial gives a VALUE of ``tg(·)``, and the scale inside the argument is
    what turns it back into a value of ``x``. Passing ``x`` as the substitution
    variable skipped that step and the two answers differ by a factor of two.
    """
    r = E.resolver("tan(x/2) = -1")
    assert r.familias, "debe responder: es un caso directo"
    punto = mx.evaluate(r.familias[0].miembro(0, "x"), {"x": 0})
    assert abs(float(punto.real) / math.pi - 1.5) < 1e-9, mx.text(punto)


# ---------------------------------------------------------------------------
# el producto


PRODUCTO = [
    ("sin(x)*cos(x) = 0", ["0", "pi", "1/2*pi", "-1/2*pi"]),
    ("sin(2*x)*cos(x) = 0", ["0", "1/2*pi"]),
    ("cos(x)*sin(2*x) = 0", ["0", "1/2*pi"]),
    ("sin(x)^2*cos(x) = 0", ["0", "pi", "1/2*pi", "-1/2*pi"]),
]


@pytest.mark.parametrize("ecuacion,esperados", PRODUCTO)
def test_un_producto_se_parte_en_sus_factores(ecuacion, esperados):
    """`A·B = 0` asks both questions at once, and the engine now asks both.

    ``sen(x)·cos(x) = 0`` was refused, and it is the simplest equation in the
    family, so the refusal was not a limitation to declare but a gap that made the
    whole family invisible: the engine could solve ``sen(x) = 0`` and ``cos(x) = 0``
    separately and could not notice that a product asks both at once.
    """
    bases = {mx.text(f.base) for f in E.resolver(ecuacion).familias}
    for esperado in esperados:
        assert esperado in bases, (ecuacion, sorted(bases))


def test_un_potente_no_negativo_no_aporta_factores_nuevos():
    """`a^k = 0` exactly when `a = 0`, so `sen(x)^2` counts as `sen(x)`."""
    r = E.resolver("sin(x)^2*cos(x) = 0")
    assert r.familias
    f = _f("sin(x)^2*cos(x) = 0")
    for familia in r.familias:
        for k in range(-4, 5):
            x = float(mx.evaluate(familia.miembro(k, "x"), {"x": 0}).real)
            assert abs(f(x)) < 1e-7, (familia.base, k, x)


def test_un_factor_que_no_se_sabe_hace_negarse_el_producto_entero():
    """A partial answer to `A·B = 0` is a wrong answer, so the whole thing refuses.

    `sen(x)·(x^5 - x^7 + 1) = 0` has one factor the engine cannot solve. Publishing
    only the solutions of ``sen(x) = 0`` would look like a complete answer to a
    question that was not fully answered, and §5.4 asks for the refusal instead.
    """
    r = E.resolver("sin(x)*(x^5 - x^7 + 1) = 0")
    assert not r.familias or r.refusos, (r.familias, r.refusos)


def test_el_paso_dice_que_un_producto_se_anula_si_alguno_de_sus_factores():
    paso = "un producto se anula si y solo si se anula alguno de sus factores"
    hipotesis = " ".join(E.resolver("sin(x)*cos(x) = 0").hipotesis)
    assert paso in hipotesis, hipotesis


#: Products whose factors do NOT share a domain, and what the right answer is for
#: each. `A·B = 0` is `A = 0` or `B = 0` only where the WHOLE PRODUCT exists, and
#: the condition that decides it is not «the factors have the same domain» — that
#: is too strong — but «no solution point lands in a hole of the product».
PRODUCTOS_CON_DOMINIOS_DISTINTOS = [
    # `tg` dies at pi/2 + k·pi; the solutions are `k·pi`, and none of those is
    # a hole. Published, and complete.
    ("tan(x)*sin(x) = 0", True),
    ("sin(x)*tan(x) = 0", True),
    # `cos(x) = 0` gives pi/2 + k·pi, which IS a hole: refused.
    ("cos(x)*tan(x) = 0", False),
    ("sin(x)*cos(x)*tan(x) = 0", False),
    # Its only solutions ARE the holes. Refused, and this is the case the old rule
    # was accidentally right about.
    ("1/(tan(x))*sin(x) = 0", False),
]


@pytest.mark.parametrize("ecuacion,responde",
                         PRODUCTOS_CON_DOMINIOS_DISTINTOS)
def test_el_producto_publica_si_ningun_punto_cae_en_un_agujero(ecuacion, responde):
    """The soundness condition on the product rule, as one table.

    It used to be «the factors share a domain», and that refused `tg(x)·sen(x) = 0`
    — whose answer is `k·pi`, with not one hole in it. The refusal was an admission
    of a gap that was not there, and it cost a correct answer.

    The condition is exact and it is asked of the DOMAIN of the product, never of
    the evaluator: at `x = pi/2` the evaluator sees `cos = 6·10⁻¹⁷` and
    `tg = 1.6·10¹⁶` and calls the product a large ordinary number where there
    is nothing at all. Asking «does this exist here?» of a float gets an answer, and
    that answer is a lie.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as Iq

    r = E.resolver(ecuacion)
    if responde:
        assert r.familias, (ecuacion, r.hipotesis)
    else:
        assert not r.familias, (ecuacion, [f.texto("x") for f in r.familias])

    # And the factors really do have different domains, or the table proves
    # nothing about the condition it is meant to exercise.
    piezas = [p.strip() for p in ecuacion.split("*")]
    primero = piezas[0]
    ultimo = piezas[-1].split("=")[0].strip()
    assert primero != ultimo
    assert Iq.dominio(mx.parse(primero)).texto() != \
        Iq.dominio(mx.parse(ultimo)).texto(), ecuacion
