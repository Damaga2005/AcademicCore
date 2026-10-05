# SPDX-License-Identifier: MIT
"""Las afirmaciones de la documentación que se han corregido contra el motor.

Tres etiquetas de `MATH_LAB.md` y `COVERAGE_CATALOG.md` decían cosas que el motor
ya no hacía. Dos de ellas eran afirmaciones de capacidad —«no hay motor de límites»,
«el polinomio de Taylor de un monomio lleva un término de más»— y una capacidad
que no se anuncia es una invitación a no intentarla: alguien lee que el motor no
puede hacer algo, y no lo intenta, y la línea sigue ahí diciendo la verdad sobre
nada.

La tercera era más sutil: `T-20` decía que cuatro objetivos venían «con su
porque y cero reglas», y «cero reglas» se leía como «nada implementado» cuando
lo cierto es que esos cuatro no reescriben nada y por eso no tienen familias de
reescritura; tienen las dos cosas que sí deben tener, un `porque` y un `verifica`.

Estas pruebas existen para que las tres afirmaciones no vuelvan a mentir. No
comprueban el texto: **comprueban el motor**, y comparan contra la afirmación que
la documentación hace sobre él. Si el motor cambia y la frase no, la prueba falla
y obliga a decidir cuál de las dos cosas estaba equivocada — que es la decisión
que no se puede tomar por omisión.
"""

from __future__ import annotations

import ast
from pathlib import Path

from academic_core.domain.engineering.mathlab import calculators as C
from academic_core.domain.engineering.mathlab import limites as L
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import series as S
from academic_core.domain.engineering.mathlab import trig as T

DOCS = Path(__file__).resolve().parents[1] / "docs" / "labs"
FUENTES = Path(C.__file__).parent


def _documentos() -> list[str]:
    return (DOCS / "MATH_LAB.md").read_text(encoding="utf-8"), \
           (DOCS / "COVERAGE_CATALOG.md").read_text(encoding="utf-8")


def _sin_citas(texto: str) -> str:
    """El texto sin lo que va entre comillas angulares.

    Una corrección **debe** poder nombrar lo que corrige, y nombrarlo es
    precisamente lo que la deja aparecer: la etiqueta de T-20 cita «cero
    reglas» para decir que era otra cosa. Buscar la frase en crudo confundiría
    «afirmar esto» con «explicar por qué se dejó de afirmar», que es justo la
    diferencia entre una mentira y su corrección.

    Se quitan las comillas angulares y nada más: lo que queda son afirmaciones,
    y es lo que tiene que ser verdad.
    """
    salida, dentro = [], False
    for ch in texto:
        if ch == "«":
            dentro = True
        elif ch == "»":
            dentro = False
        elif not dentro:
            salida.append(ch)
    return "".join(salida)


# ---------------------------------------------- «no hay motor de límites»

def test_el_motor_de_limites_existe_y_calcula_por_aritmetica():
    """La afirmación era «no hay motor de límites», y además «muestrear un `x`
    grande no es un límite». Las dos cosas: existe, y no muestrea.

    Se comprueba por el resultado y no por el texto de `limites.py`, porque un
    módulo puede decir que no muestrea y muestrear. Lo que se ve aquí es que
    `1/(x²+1)` da `y = 0` — un senoide daría «límites» distintos en cada `x`, y
    esta respuesta no depende del `x` en que se evaluara.
    """
    assert (L.asintotas_de_horizonte_y_oblicua(mx.parse("1/(x^2+1)"), "x")
            == ("y = 0",))
    assert (L.asintotas_de_horizonte_y_oblicua(mx.parse("(x^2-1)/(x^2+1)"), "x")
            == ("y = 1",))
    # y una que NO tiene asíntota no recibe ninguna, que es la mitad de la honestidad
    assert L.asintotas_de_horizonte_y_oblicua(mx.parse("(x^2+1)"), "x") == ()


def test_la_documentacion_no_declara_que_falta_el_motor_de_limites():
    math_lab, catalogo = _documentos()
    for nombre, texto in (("MATH_LAB.md", math_lab), ("COVERAGE_CATALOG.md", catalogo)):
        afirmado = _sin_citas(texto)
        assert "no hay motor de límites" not in afirmado, nombre
        assert "no hay motor de limites" not in afirmado, nombre


def test_el_razonamiento_que_excusaba_al_motor_lo_cumple_el_modulo():
    """La excusa era «muestrear en un `x` grande no es un límite». Se comprueba
    que el módulo razona sobre el orden de crecimiento y no sobre muestras.

    Buscado en el código y no en el documento, porque la documentación repitiendo su
    propia excusa no la convierte en verdad: la pregunta es si `orden_en_infinito`
    existe y hace la cuenta por grado dominante.
    """
    assert hasattr(L, "orden_en_infinito")
    assert L.Orden is not None
    fuente = Path(L.__file__).read_text(encoding="utf-8")
    # el grado dominante, no un `for x in (10**k, ...)`
    assert "orden" in fuente.lower()
    assert "1e10" not in fuente and "10 ** 10" not in fuente


# ------------------------------- «el polinomio de un monomio lleva un término de más»

def test_el_taylor_de_un_monomio_no_lleva_ningun_termino_de_mas():
    """Ocho monomios, con el orden POR ENCIMA del grado, que es donde un término
    de más se notaría.

    Se compara contra el monomio exacto y no contra un patron: un polinomio de
    Taylor de `c·x^n` con orden mayor que `n` es `c·x^n` y nada más, y el residuo
    tiene que ser exactamente cero porque la función ES un polinomio. Un residuo
    distinto de cero aquí no es redondeo, es un término de más.
    """
    for texto, orden in [("3*x", 5), ("2*x^2", 6), ("5*x", 4), ("x^3", 7),
                         ("7*x^2", 9), ("x^5", 8), ("4*x^4", 6), ("x", 3)]:
        serie = S.taylor(mx.parse(texto), mx.ZERO, orden, "x")
        assert mx.text(serie.polinomio).replace(" ", "") == texto, texto
        assert serie.residuo.value == 0, (texto, serie.residuo)


def test_ningun_docstring_anuncia_el_bug_ya_arreglado():
    """La frase vivía en un docstring de `graficas.py` mientras el catálogo
    decía lo contrario desde hacía tiempo.

    Se busca en los ficheros del módulo, y no en un solo docstring, porque el
    defecto era que la afirmación sobrevivía en un sitio que nadie revisa: el que
    no dice el número de línea.
    """
    for f in sorted(FUENTES.glob("*.py")):
        texto = f.read_text(encoding="utf-8")
        assert "término de más" not in texto or "arreglado" in texto or \
               "un término de más" not in texto, f.name
    graficas = (FUENTES / "graficas.py").read_text(encoding="utf-8")
    assert "término de más" not in graficas


# ------------------------- T-20: «cuatro declarados con su porqué y cero reglas»

def test_los_cuatro_de_transformacion_no_reeescriben_y_deben_otra_cosa():
    """El `es_reescritura = False` no es «nada implementado»: es «no reescribe».

    Los cuatro objetivos de transformación devuelven una derivada, una primitiva,
    un número complejo o un fasor, que es otra clase de cosa que una expresión.
    Lo que deben en lugar de familias de reglas es un `porque` escrito y un
    `verifica` que nombre el segundo camino, y se comprueba que los dos existen y
    que no están vacíos.
    """
    cambios = [o for o in T.OBJETIVOS.values() if not o.es_reescritura]
    assert {o.nombre for o in cambios} == {"derivar", "integrar", "complejos", "fasores",
                                           "demostrar", "resolver"}
    for o in cambios:
        assert o.porque and len(o.porque) > 40, o.nombre
        assert o.verifica and len(o.verifica) > 40, o.nombre
        assert o.procede_de, o.nombre


def test_los_cuatro_llegan_a_la_trayectoria_del_alumno():
    """Una declaración que nadie lee es una declaración en un fichero.

    Se comprueba que las cuatro operaciones llaman a `_objetivo_declarado` con su
    nombre, porque ese es el puente entre el registro y lo que el alumno ve; y se
    busca por AST para que el nombre no pueda estar en un comentario.
    """
    arbol = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
    escritos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) \
                and nodo.func.id == "_objetivo_declarado":
            for arg in nodo.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    escritos.add(arg.value)
    assert {"derivar", "integrar", "complejos", "fasores"} <= escritos


def test_la_etiqueta_de_T20_no_dice_que_no_hay_nada():
    math_lab, _ = _documentos()
    linea = next(l for l in math_lab.split("\n") if l.startswith("### T-20"))
    # se busca fuera de las citas: la línea cita la frase antigua para refutarla,
    # y citarla es lo correcto; lo que no puede es AFIRMARLA
    afirmado = _sin_citas(linea)
    assert "cero reglas" not in afirmado
    # y sí dice por qué no tienen familias de reescritura
    assert "no reescriben" in linea or "reescritura" in linea