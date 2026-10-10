# SPDX-License-Identifier: MIT
"""ML-10: la plantilla única de ejercicio, su corrector por equivalencia y
el generador sembrado (§7).

Tres decisiones que separan esto de un simple banco de respuestas:

**El corrector compara formas, no textos.** Reutiliza
:func:`verify.check_equivalence` (formas normales exactas) y, solo si eso no
decide, :func:`verify.numeric_agreement` — que **no puede probar una
identidad** y por eso deja el sello en ``solo_numerico`` (§5.3). Se acepta
``2x+2x`` por ``4x`` y ``1/2`` por ``0,5``; no se acepta ``x²`` por ``2x``.

**El generador no escribe la solución: la pide al motor.** Cada constructor
llama a la calculadora real del bloque correspondiente, de modo que la
respuesta del ejercicio viene con el segundo camino del motor, no con una
fórmula escrita a mano en el generador. Un ejercicio generado es, por tanto,
un ejercicio ya verificado; y su enunciado y su solución no pueden
desincronizarse porque salen del mismo paso.

**Nada se corrige por parecido.** Un ejercicio cuya respuesta no es única
(una base ortonormal, un sistema de generadores) se corrige por **propiedad**
—«¿tu matriz da ``AᵀA = I``?»— nunca por su forma (§7, soluciones no únicas).

Todo determinista: el generador es sembrado (``semilla``) y reproduce el
mismo ejercicio, y las pistas son graduadas (de menos a más ayuda).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: tipos de entrega de §7
TIPOS = ("expresion", "numero", "matriz", "vector", "conjunto", "grafica",
         "demostracion")


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# veredicto
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Veredicto:
    """Qué se responde de una corrección. ``sello`` usa los tres de §5.3."""

    correcto: bool
    metodo: str
    detalle: str
    sello: str = V.VERIFIED
    pistas_usadas: tuple[int, ...] = ()

    def texto(self) -> str:
        marca = "✔" if self.correcto else "✘"
        extra = ""
        if self.sello == V.NUMERIC_ONLY:
            extra = " (solo coincidencias numéricas: no prueba la identidad)"
        return f"{marca} {self.metodo}: {self.detalle}{extra}"


# ---------------------------------------------------------------------------
# la plantilla única (§7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ejercicio:
    """Enunciado, datos, tipo de entrega, pistas, respaldo y solución.

    Es la plantilla única de §7: los mismos campos valen para un límite, una
    integral, una base ortonormal o una demostración, que es lo que permite
    que el corrector, el generador y la interfaz sean uno solo.
    """

    id: str
    tema: str
    asignatura: str
    tipo: str
    enunciado: str
    datos: dict = field(default_factory=dict)
    solucion: object = None
    pistas: tuple[str, ...] = ()
    respaldo: str = "G"          # E = sale en exámenes reales (§3)
    dificultad: str = "media"     # facil | media | dificil
    grafica: object = None        # C.Graph: la figura esperada, como datos
    solucion_pasos: str = ""      # la solución paso a paso, como texto
    convenciones: tuple[tuple[str, str], ...] = ()

    def pistas_hasta(self, n: int) -> tuple[str, ...]:
        if n < 0:
            raise _error("BAD_INPUT", "n ≥ 0")
        return self.pistas[:n]


# ---------------------------------------------------------------------------
# comparación de respuestas por tipo
# ---------------------------------------------------------------------------

_TOL = 1e-9


def _num(x) -> float | None:
    """Lee un número escrito como el escriba el alumno: «1/2», «0,5», «π»."""
    if isinstance(x, (int, float, Fraction)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(Fraction(s))
    except (ValueError, ZeroDivisionError):
        pass
    try:
        return float(s)
    except ValueError:
        pass
    try:                                   # π, e, o «2π/3»
        return float(mx.evaluate(mx.parse(s)))
    except Exception:
        return None


def _expresion(a: str, b: str) -> tuple[bool, str, str, str]:
    """(iguales, método, detalle, sello) por formas normales exactas."""
    ea, eb = mx.parse(a), mx.parse(b)
    iguales, metodo, detalle = V.check_equivalence(ea, eb)
    if iguales:
        return True, metodo, detalle, V.VERIFIED
    ok, metodo_num, detalle_num = V.numeric_agreement(ea, eb)
    if ok:
        # agreeing at sample points is evidence, not proof (§5.3)
        return True, f"{metodo_num} (sin prueba exacta)", f"{metodo_num}: {detalle_num}", \
            V.NUMERIC_ONLY
    return False, metodo, detalle, V.VERIFIED


def _matriz(a, b) -> tuple[bool, str, str]:
    """Elemento a elemento en ℚ: una matriz es una lista de filas."""
    try:
        fa, fb = list(a), list(b)
    except TypeError:
        raise _error("BAD_INPUT", "una matriz es una lista de filas")
    if len(fa) != len(fb):
        return False, "dimensiones", f"{len(fa)} filas frente a {len(fb)}"
    for i, (ra, rb) in enumerate(zip(fa, fb)):
        try:
            la, lb = list(ra), list(rb)
        except TypeError:
            raise _error("BAD_INPUT", f"fila {i} que no es una lista")
        if len(la) != len(lb):
            return False, "dimensiones", f"fila {i}: {len(la)} frente a {len(lb)}"
        for j, (x, y) in enumerate(zip(la, lb)):
            nx, ny = _num(x), _num(y)
            if nx is None or ny is None:
                return False, "no numérico", f"posición ({i}, {j}): «{x}» o «{y}»"
            if abs(nx - ny) > _TOL * max(1.0, abs(nx), abs(ny)):
                return False, "elemento a elemento", f"({i}, {j}): {nx:g} ≠ {ny:g}"
    return True, "elemento a elemento", "todas las entradas coinciden"


def _conjunto(a, b) -> tuple[bool, str, str]:
    """Conjuntos e intervalos como conjuntos de extremos, sin importar el orden."""
    try:
        na = {_num(v) for v in (a if isinstance(a, (list, tuple)) else [a])}
        nb = {_num(v) for v in (b if isinstance(b, (list, tuple)) else [b])}
    except TypeError:
        raise _error("BAD_INPUT", "un conjunto es una lista de valores")
    if None in na or None in nb:
        raise _error("BAD_INPUT", "algún valor del conjunto no es un número")
    if na == nb:
        return True, "conjuntos", "mismos elementos"
    return False, "conjuntos", f"{sorted(na)} frente a {sorted(nb)}"


def corrige(ex: Ejercicio, respuesta, *, con_evidencia: bool = False) -> Veredicto:
    """Corrige por equivalencia (§7) y devuelve el veredicto con su sello.

    ``con_evidencia`` devuelve además la prueba que se usó, para que el
    estudiante vea *por qué* se acepta: la forma normal común o las muestras.
    """
    if ex.tipo not in TIPOS:
        raise _error("BAD_INPUT", f"tipo de entrega desconocido: {ex.tipo}")
    if respuesta is None or (isinstance(respuesta, str) and not respuesta.strip()):
        raise _error("BAD_INPUT", "respuesta vacía")
    if ex.tipo == "expresion":
        ok, metodo, detalle, sello = _expresion(str(respuesta), str(ex.solucion))
        return Veredicto(ok, metodo, detalle, sello)
    if ex.tipo == "demostracion":
        # se corrige la igualdad que hay que demostrar, no su redacción
        ok, metodo, detalle, sello = _expresion(str(respuesta), str(ex.solucion))
        return Veredicto(ok, "identidad " + metodo, detalle, sello)
    if ex.tipo == "numero":
        nv, ne = _num(respuesta), _num(ex.solucion)
        if nv is None or ne is None:
            raise _error("BAD_INPUT", "respuesta o solución no numérica")
        if abs(nv - ne) <= _TOL * max(1.0, abs(nv), abs(ne)):
            return Veredicto(True, "valor", f"{nv:g} = {ne:g}")
        return Veredicto(False, "valor", f"{nv:g} ≠ {ne:g}")
    if ex.tipo in ("matriz", "vector"):
        ok, metodo, detalle = _matriz(respuesta, ex.solucion)
        return Veredicto(ok, metodo, detalle)
    if ex.tipo == "conjunto":
        ok, metodo, detalle = _conjunto(respuesta, ex.solucion)
        return Veredicto(ok, metodo, detalle)
    if ex.tipo == "grafica":
        # una gráfica no se corrige: se comprueba que la describe (§6). La
        # comparación real es contra la serie esperada, y sin datos no hay
        # nada que decir: se pide la figura, no se corrige texto.
        raise _no("una gráfica no se corrige por texto: se compara su "
                  "descripción y sus puntos de control")
    raise _error("BAD_INPUT", f"tipo sin corrector: {ex.tipo}")


# ---------------------------------------------------------------------------
# generador sembrado (§7: por tema y dificultad, con solución incluida)
# ---------------------------------------------------------------------------


class Generador:
    """Determinista: la misma ``semilla`` da el mismo ejercicio."""

    def __init__(self, semilla: int = 1):
        self.semilla = int(semilla)

    def _azar(self, a: int, b: int, k: int = 0) -> int:
        """Entero en [a, b], determinista y con mezcla de bits.

        No basta con ``semilla·C + k·D`` módulo el rango: si dos claves se
        separan un múltiplo del rango, salían **iguales** (con cuatro datos en
        [1, 6] bastaba para que la matriz saliera siempre singular y el
        ejercicio, degenerado). Aquí el cambio de clave se propaga a todos los
        bits antes de reducir.
        """
        n = b - a + 1
        x = (self.semilla * 2654435761 + (k + 1) * 374761393) & 0xFFFFFFFF
        x = ((x ^ (x >> 15)) * 2246822519) & 0xFFFFFFFF
        x = ((x ^ (x >> 13)) * 3266489917) & 0xFFFFFFFF
        x ^= x >> 16
        return a + x % n


#: intentos antes de rendirse con un tema
INTENTOS = 12


def _reintenta(tema: str, semilla: int, dif: str, fab, vale):
    """Genera hasta que el ejercicio esté **bien planteado**.

    Un ejercicio degenerado (un determinante 0, un límite que «no existe»)
    no es un ejercicio: es ruido con la misma forma. En vez de emitirlo —que
    es lo que haría un generador que no mira lo que ha generado— se prueba
    con otro(parameters) y, si tras varios intentos no sale uno sano, se
    dice con el motivo en vez de fingir que sí.
    """
    for intento in range(INTENTOS):
        g = Generador(semilla + intento)
        try:
            ex = fab(g, dif)
        except (ValidationError, UnsupportedError):
            continue        # datos degenerados (vectores ligados…): otro intento
        if vale(ex):
            return ex
    raise _no(f"«{tema}»: con la semilla {semilla} no sale un ejercicio "
              f"planteado tras {INTENTOS} intentos; se cambian los parámetros "
              f"a mano en vez de dar uno degenerado")


# --- generadores por tema; la solución la pide el motor, no la escribe ---

def _g_limite(g: Generador, dif: str) -> Ejercicio:
    """El límite notable de la potencia, resuelto por el motor de límites."""
    from academic_core.domain.engineering.mathlab import limite as LI
    a = g._azar(2, 5, 1)
    b = g._azar(1, 4, 2)
    if b == 0:
        b = 1
    t = Trace()
    r = LI.limite(mx.parse(f"(x^{a}-1)/(x-{b})"), "x", str(b), trace=t)
    return Ejercicio(
        id="lim-notable", tema="limites", asignatura="Cálculo",
        tipo="expresion", respaldo="E", dificultad=dif,
        enunciado=f"Calcula el límite de (x^{a} − 1)/(x − {b}) cuando x → {b}.",
        datos={"a": a, "b": b},
        solucion=r.valor,
        pistas=(f"sale 0/0: factoriza x^{a} − 1 como diferencia de potencias",
                f"al cancelar queda una suma de {a} términos, cada uno b^{a-1}",
                f"el límite es {a}·{b}^{a - 1}"),
        solucion_pasos=t.render(),
    )


def _limite_vale(ex: Ejercicio) -> bool:
    """El límite notable existe siempre: si el motor dice que no, es otro caso."""
    return ex.solucion not in ("no existe", "+8", "-8", "8")


def _g_derivada(g: Generador, dif: str) -> Ejercicio:
    from academic_core.domain.engineering.mathlab import derive_mv as D
    from academic_core.domain.engineering.mathlab import limite as LM
    a, n = g._azar(2, 6, 3), g._azar(2, 4, 4)
    expr = f"x^{a}*exp({n}*x)"
    t = Trace()
    d = D.differentiate(mx.parse(expr), "x", t)
    return Ejercicio(
        id="der-prod", tema="derivadas", asignatura="Cálculo",
        tipo="expresion", respaldo="E", dificultad=dif,
        enunciado=f"Deriva f(x) = {expr} respecto de x.",
        datos={"expr": expr},
        solucion=mx.text(LM._limpio(d)),
        pistas=(f"separa en producto: u = x^{a}, v = exp({n}·x)",
                f"u' = {a}·x^{a - 1} y v' = {n}·exp({n}·x)",
                "aplica (uv)' = u'v + uv' y simplifica"),
        solucion_pasos=t.render(),
    )


def _g_integral(g: Generador, dif: str) -> Ejercicio:
    """Integral definida: la pide al motor, con su segundo camino."""
    from academic_core.domain.engineering.mathlab import contract as C
    a = g._azar(1, 4, 5)
    b = g._azar(1, 3, 6)
    r = C.calcular(C.Peticion("integrar", {"integrando": f"x^{a}", "var": "x",
                                          "desde": "0", "hasta": str(b)}))
    return Ejercicio(
        id="int-def", tema="integrales", asignatura="Cálculo",
        tipo="numero", respaldo="E", dificultad=dif,
        enunciado=f"Calcula ∫₀^{b} x^{a} dx.",
        datos={"integrando": f"x^{a}", "desde": 0, "hasta": b},
        solucion=str(r.exacto),
        pistas=(f"busca la primitiva de x^{a}",
                f"usa la potencia: ∫x^{a}dx = x^(%d)/(%d)" % (a + 1, a + 1),
                f"aplica Barrow entre 0 y {b}"),
        solucion_pasos=r.traza.render(),
    )


def _g_lineal(g: Generador, dif: str) -> Ejercicio:
    """Determinante, resuelto por el motor lineal (no por la fórmula escrita)."""
    from academic_core.domain.engineering.mathlab import lineal as L
    a = g._azar(1, 6, 7)
    b = g._azar(1, 6, 8)
    c = g._azar(1, 6, 9)
    d = g._azar(1, 6, 10)
    t = Trace()
    det = L.determinante([[a, b], [c, d]], L.cuerpo("Q"), t)
    return Ejercicio(
        id="lin-det", tema="algebra lineal", asignatura="Álgebra Lineal",
        tipo="numero", respaldo="E", dificultad=dif,
        enunciado=f"Calcula el determinante de [[{a}, {b}], [{c}, {d}]].",
        datos={"matriz": [[a, b], [c, d]]},
        solucion=str(det),
        pistas=("escribe la primera fila y la segunda",
                "det = a·d − b·c (el segundo producto va con signo menos)",
                f"sustituye: {a}·{d} − {b}·{c}"),
        solucion_pasos=t.render(),
    )


def _det_val(e: Ejercicio) -> bool:
    """Una matriz singular daría un ejercicio trivial (det = 0 siempre)."""
    return e.solucion != "0"


def _g_ecuacion(g: Generador, dif: str) -> Ejercicio:
    from academic_core.domain.engineering.mathlab import contract as C
    a = g._azar(2, 9, 11)
    b = g._azar(1, 9, 12)
    r = C.calcular(C.Peticion("resolver", f"{a}*x={b}"))
    sols = list(r.exacto) if not isinstance(r.exacto, str) else [r.exacto]
    return Ejercicio(
        id="eq-lin", tema="ecuaciones", asignatura="Cálculo",
        tipo="numero", respaldo="E", dificultad=dif,
        enunciado=f"Resuelve {a}·x = {b}.",
        datos={"a": a, "b": b},
        solucion=str(sols[0]) if len(sols) == 1 else sols,
        pistas=("despeja el factor que multiplica a x",
                f"divide entre {a} por los dos lados",
                f"x = {b}/{a}"),
        solucion_pasos=r.traza.render(),
    )


def _g_espacio(g: Generador, dif: str) -> Ejercicio:
    """Base ortonormal: respuesta NO única, se corrige por propiedad (§7)."""
    from academic_core.domain.engineering.mathlab import algebra as AL
    a, b, c, d = (g._azar(1, 4, 13), g._azar(1, 4, 14),
                  g._azar(1, 4, 15), g._azar(1, 4, 16))
    t = Trace()
    orto = AL.gram_schmidt([[a, b], [c, d]], t)      # exacta, sin normalizar
    base = []
    for u in orto:
        norma = math.sqrt(float(sum(x * x for x in u)))
        base.append([float(x) / norma for x in u])
    ex = Ejercicio(
        id="esp-orton", tema="espacios vectoriales",
        asignatura="Álgebra Lineal", tipo="matriz", respaldo="E",
        dificultad=dif,
        enunciado=f"Da una base ortonormal de span⟨({a}, {b}), ({c}, {d})⟩.",
        datos={"vectores": [[a, b], [c, d]]},
        solucion=base,
        pistas=("normaliza el primer vector: u₁ = v₁/|v₁|",
                "proyecta v₂ sobre u₁ y réstalo; normaliza el resultado",
                "se corrige por propiedad: ¿tu matriz cumple Aᵀ·A = I?"),
        solucion_pasos=t.render(),
    )
    # el generador se autocomprueba por la misma propiedad con la que se
    # corrige: si su propia solución no fuera ortonormal, el ejercicio saldría
    # mal, y eso se ve aquí y no cuando un alumno lo entrega
    v = comprueba_propiedad("ortonormal", base)
    if not v.correcto:
        raise _error("INTERNAL", f"la solución generada no es ortonormal: {v.detalle}")
    return ex


def _g_transformada(g: Generador, dif: str) -> Ejercicio:
    from academic_core.domain.engineering.mathlab import contract as C
    a = g._azar(1, 4, 17)
    r = C.calcular(C.Peticion("laplace", {"expr": f"exp(-{a}*t)", "var": "t"}))
    # el texto de la calculadora trae la región de convergencia detrás; aquí
    # solo la expresión, que es lo que se pide
    sol = str(r.exacto).split(";")[0].replace("F(s) = ", "").strip()
    return Ejercicio(
        id="tra-lap", tema="transformadas", asignatura="EDO y Transformadas",
        tipo="expresion", respaldo="E", dificultad=dif,
        enunciado=f"Calcula la transformada de Laplace de f(t) = exp(−{a}·t).",
        datos={"a": a},
        solucion=sol,
        pistas=(f"usa L{{exp(−a·t)}}(s) = 1/(s + a)",
                "sustituye a por el valor del enunciado",
                f"el resultado es 1/(s + {a})"),
        solucion_pasos=r.traza.render(),
        grafica=r.grafica,
    )


#: qué es un ejercicio **planteado** en cada tema (§7: no valen los
#: degenerados). Todo lo que no esté aquí se considera sano.
_SANO = {
    "limites": _limite_vale,
    "algebra lineal": _det_val,
}

TEMAS: dict[str, dict] = {
    "limites": {"generador": _g_limite, "asignatura": "Cálculo"},
    "derivadas": {"generador": _g_derivada, "asignatura": "Cálculo"},
    "integrales": {"generador": _g_integral, "asignatura": "Cálculo"},
    "algebra lineal": {"generador": _g_lineal, "asignatura": "Álgebra Lineal"},
    "ecuaciones": {"generador": _g_ecuacion, "asignatura": "Cálculo"},
    "espacios vectoriales": {"generador": _g_espacio,
                              "asignatura": "Álgebra Lineal"},
    "transformadas": {"generador": _g_transformada,
                      "asignatura": "EDO y Transformadas"},
}


def genera(tema: str = "limites", dificultad: str = "media",
           semilla: int = 1) -> Ejercicio:
    """Un ejercicio sembrado del tema, con su solución verificada.

    Reintenta con otros parámetros si el primero sale degenerado (§7: mejor
    decirlo que emitir un ejercicio que no tiene sentido).
    """
    if tema not in TEMAS:
        raise _error("BAD_INPUT",
                     f"tema desconocido: {tema}. Hay {', '.join(sorted(TEMAS))}")
    if dificultad not in ("facil", "media", "dificil"):
        raise _error("BAD_INPUT", "dificultad facil, media o dificil")
    return _reintenta(tema, int(semilla), dificultad,
                      TEMAS[tema]["generador"], _SANO.get(tema, lambda e: True))


# ---------------------------------------------------------------------------
# propiedades: corrección de respuestas no únicas (§7)
# ---------------------------------------------------------------------------


def comprueba_propiedad(nombre: str, candidata) -> Veredicto:
    """Corrige por propiedad, para lo que no tiene una única respuesta.

    Hoy: base ortonormal (``Aᵀ·A = I``). No se compara con la del ejercicio:
    se comprueba la propiedad, que es lo que la hace no única.
    """
    if nombre == "ortonormal":
        ok, metodo, detalle = _matriz_gram(candidata)
        if not ok:
            return Veredicto(False, "propiedad Aᵀ·A = I", detalle)
        return Veredicto(True, "propiedad Aᵀ·A = I", detalle)
    raise _error("BAD_INPUT", f"propiedad sin comprobador: {nombre}")


def _matriz_gram(a) -> tuple[bool, str, str]:
    filas = [list(f) for f in a]
    n = len(filas)
    if any(len(f) != n for f in filas):
        return False, "propiedad Aᵀ·A = I", "no es una matriz cuadrada"
    cols = [[filas[i][j] for i in range(n)] for j in range(n)]
    for j in range(n):
        for k in range(n):
            p = sum(_num(cols[j][i]) * _num(cols[k][i]) for i in range(n))
            if p is None or abs(p - (1.0 if j == k else 0.0)) > 1e-9:
                return (False, "propiedad Aᵀ·A = I",
                        f"la posición ({j}, {k}) de Aᵀ·A vale {p}")
    return True, "propiedad Aᵀ·A = I", "Aᵀ·A = I"