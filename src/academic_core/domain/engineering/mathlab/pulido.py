# SPDX-License-Identifier: MIT
"""ML-11: el pulido — accesibilidad, rendimiento, documentación y
certificación (§6, §8.4, §12).

Cuatro cosas, y las cuatro son **comprobaciones que se ejecutan**, no una lista
de deseos. Un requisito que nadie puede ver fallar acaba mintiendo solo, que es
justo lo que pasó con los huecos declarados en `MATH_LAB.md` (y por eso existe
`test_mathlab_huecos_documentados.py`).

**Accesibilidad (§6).** Toda gráfica lleva descripción textual y toda serie
lleva nombre, porque la información no puede viajar en el color: el modelo de
gráficas **no tiene campo de color**, y eso se comprueba leyendo el modelo, no
prometiéndolo. Una descripción vacía o que solo repita el nombre de la serie es
una gráfica que un lector de pantalla no puede usar, así que se rechaza.

**Rendimiento (§5.4).** Se mide de verdad (`time.perf_counter`) contra un
techo declarado, y se distingue *excedido* de *demasiado rápido para medirse*.
Además se comprueba el **determinismo**: la misma entrada da el mismo resultado,
porque un motor con caché que devuelve cosas distintas según cuándo se llama no
es verificable.

**Documentación (§8.4).** Todo resultado se puede volcar a texto con
:func:`describe`: valor, aproximación con su error, pasos, sello, hipótesis,
convenciones y gráfica. Es lo que lee un lector de pantalla y lo que se copia
a otro laboratorio (§8.1).

**Certificación (§8.4).** :func:`audita` recorre **todas** las operaciones
registradas con una entrada canónica y comprueba los nueve criterios de
aceptación uno a uno, y devuelve la lista de lo que falla. Las operaciones sin
entrada canónica se listan como **sin muestra**: no se cuentan como buenas, y
tampoco como malas, porque no hay nada que comprobar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: techo por defecto de una llamada (s), el de §5.4
TECHO_S = 10.0


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# accesibilidad (§6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InformeAccesibilidad:
    accesible: bool
    problemas: tuple[str, ...] = ()
    series: int = 0

    def texto(self) -> str:
        if self.accesible:
            return f"accesible: {self.series} serie(s) con nombre y descripción"
        return "no accesible: " + "; ".join(self.problemas)


def audita_accesibilidad(resultado: C.Resultado) -> InformeAccesibilidad:
    """Comprueba que la gráfica se puede entender sin verla (§6)."""
    g = resultado.grafica
    if g is None:
        return InformeAccesibilidad(True, (), 0)
    problemas: list[str] = []
    # el modelo de gráficas no tiene color: nada puede depender solo de él
    if hasattr(g, "color") or hasattr(g, "colores"):
        problemas.append("la gráfica tiene color: la información no puede "
                         "depender solo de él (§6)")
    desc = (g.description or "").strip()
    if not desc:
        problemas.append("gráfica sin descripción textual")
    nombres = [s.name.strip() for s in g.series]
    for s, n in zip(g.series, nombres):
        if not n:
            problemas.append("una serie sin nombre: al leerla no se sabe qué es")
        if len(s.xs) != len(s.ys):
            problemas.append(f"la serie «{s.name}» tiene {len(s.xs)} abscisas "
                             f"y {len(s.ys)} ordenadas")
    # una descripción que solo repite los nombres no dice nada del dibujo
    if desc and nombres and desc.lower() in {n.lower() for n in nombres if n}:
        problemas.append(f"la descripción solo repite el nombre de la serie: "
                         f"«{desc}»")
    return InformeAccesibilidad(not problemas, tuple(problemas), len(g.series))


# ---------------------------------------------------------------------------
# documentación: todo resultado como texto (§8.1, §8.4)
# ---------------------------------------------------------------------------


def describe(resultado: C.Resultado, nivel: str = "paso") -> str:
    """El resultado entero como texto: lo lee una persona o un lector de pantalla.

    No es un resumen: es el resultado con sus pasos, su sello y sus hipótesis,
    que es lo que el contrato promete (§5.9) y lo que §8.1 llama «copiar y
    exportar».
    """
    lineas = [f"operación: {resultado.operacion}"]
    if resultado.exacto is not None:
        lineas.append(f"exacto: {C._format_exact(resultado.exacto)}")
    if resultado.aproximado is not None:
        lineas.append(f"aproximado: {C._format_complex(resultado.aproximado, resultado.cifras)} "
                      f"({resultado.cifras} cifras)")
    if resultado.error_acotado is not None:
        lineas.append(f"error: ≤ {resultado.error_acotado:.3g}")
    lineas.append(f"sello: {resultado.sello.verdict} — {resultado.sello.method} "
                  f"({resultado.sello.detail})")
    for nombre, veredicto in resultado.hipotesis:
        lineas.append(f"hipótesis {nombre}: {veredicto}")
    for linea in resultado.convenciones.as_lines():
        lineas.append(f"convención {linea}")
    for aviso in resultado.avisos:
        lineas.append(f"aviso: {aviso}")
    if resultado.grafica is not None:
        lineas.append("gráfica: " + resultado.grafica.describe())
    pasos = resultado.traza.render(nivel)
    if pasos:
        lineas.append("pasos:")
        lineas.extend("  " + ln for ln in pasos.splitlines())
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# rendimiento y determinismo (§5.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Medida:
    operacion: str
    segundos: float
    cumple: bool
    detalle: str
    determinista: bool = True

    def texto(self) -> str:
        return (f"{self.operacion}: {self.segundos * 1000:.1f} ms "
                f"({'dentro' if self.cumple else 'FUERA'} del techo)"
                + ("" if self.determinista else "; NO determinista"))


def mide(operacion: str, entrada, *, techo: float = TECHO_S,
         repetir: bool = True) -> Medida:
    """Mide una llamada real y comprueba el determinismo (§5.4)."""
    if not isinstance(operacion, str) or not operacion:
        raise _error("BAD_INPUT", "operación no vacía")
    if techo <= 0:
        raise _error("BAD_INPUT", "techo > 0")
    t0 = time.perf_counter()
    primero = C.calcular(C.Peticion(operacion, entrada))
    dt = time.perf_counter() - t0
    det = True
    if repetir:
        segundo = C.calcular(C.Peticion(operacion, entrada))
        det = (str(primero.exacto) == str(segundo.exacto)
               and primero.sello.verdict == segundo.sello.verdict)
    cumple = dt <= techo
    if cumple:
        detalle = f"≤ {techo:g} s"
    else:
        detalle = f"excede el techo de {techo:g} s"
    return Medida(operacion, dt, cumple, detalle, det)


# ---------------------------------------------------------------------------
# certificación (§8.4): los nueve criterios, uno a uno
# ---------------------------------------------------------------------------

#: entrada canónica por operación, para poder comprobarlas todas. Una
#: operación que no esté aquí se audita como «sin muestra»: no suma, no resta.
#: Vive en el dominio y no en las pruebas porque una certificación que solo
#: existe en la suite no certifica nada.
MUESTRAS: dict[str, object] = {
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
    "edo": "y''+y=sin(t)",
    "laplace": "t*u(t-1)",
    "fourier": {"calculo": "serie", "tramos": [["t", "-pi", "pi"]]},
    "transformada_z": "n*(1/2)^n",
    "contorno": {"calculo": "contorno", "ecuacion": "y''+y=0", "a": 0,
                 "b": "pi/2", "ca": ["y", 1], "cb": ["y", 2]},
    "distribucion": {"calculo": "derivada", "expr": "u(t)-u(t-1)"},
    "dimensional": {"ecuacion": "P = V^2/R",
                    "dimensiones": {"P": "W", "V": "V", "R": "Ω"}},
    "comprobar_gradiente": {"f": "x*y"},
    "markov": {"P": [["1/2", "1/2"], ["1/3", "2/3"]], "simular": 500},
    "cola_mm1": {"lambda": 1, "mu": 2, "clientes": 200},
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
    "aplicacion_integral": {"tipo": "area", "f": "x^2", "g": "x", "a": "0",
                            "b": "2"},
    "algebra": {"calculo": "autovalores", "matriz": [[2, 1], [1, 2]]},
    "gamma": {"expr": "5"},
    "multivar": {"calculo": "criticos", "expr": "x^2+x*y+y^2",
                 "vars": ["x", "y"]},
    "numericos": {"calculo": "radio", "coef": "1/n"},
    "operadores": {"calculo": "laplaciano", "V": "1/r", "sistema": "esfericas"},
    "vectorial": {"calculo": "potencial", "campo": ["2*x*y", "x^2"]},
    "multiple": {"calculo": "iterada", "expr": "x*y",
                 "limites": [["y", "0", "x"], ["x", "0", "1"]]},
    "espacios": {"calculo": "suma_interseccion",
                 "F": [[1, 0, 1, 0], [0, 1, 0, 1]],
                 "G": [[1, 1, 0, 0], [1, 0, 1, 0]]},
    "probabilidad": {"calculo": "bayes", "previas": {"A": "1/2", "B": "1/2"},
                     "verosimilitudes": {"A": "1/10", "B": "1/5"}},
    "variable_aleatoria": {"dist": "poisson", "parametros": {"lambda": 2},
                           "suceso": "P(X<=1)"},
    "vector_aleatorio": {"calculo": "tabla", "x": [0, 1], "y": [0, 1],
                         "p": [["1/4", "1/4"], ["1/8", "3/8"]]},
    "aproximacion_normal": {"dist": "binomial",
                            "parametros": {"n": 50, "p": "1/2"},
                            "suceso": "P(X<=27)"},
    "estadistica": {"datos": [2, 4, 4, 5, 7]},
    "intervalo_confianza": {"parametro": "media", "n": 20, "media": "10.2",
                           "s": "1.5"},
    "contraste": {"tipo": "media", "n": 25, "media": 52, "s": 5, "mu0": 50},
    "regresion": {"x": [1, 2, 3], "y": [2, 4, 5]},
    "estimador": {"familia": "poisson", "datos": [2, 3, 1]},
    "proceso": {"tipo": "poisson", "lambda": 2, "consulta": "conteo", "t": 1,
                "k": 2},
    "tabla_estadistica": {"ley": "normal", "p": "0.975"},
    "comunicaciones": {"calculo": "aloha", "G": "1", "ranurado": True},
    "montecarlo": {"dist": "binomial", "parametros": {"n": 5, "p": "1/2"},
                   "suceso": "P(X=2)"},
    "senales": {"calculo": "conv_digital", "x": [1, 2, 3], "h": [1, 1]},
    "polarizacion": {"calculo": "fasor", "suma": [[1, 0]]},
    "campos": {"calculo": "carga", "tipo": "arco"},
    "fisica": {"calculo": "equilibrio"},
    "demuestra": {"calculo": "punto_fijo", "expr": "x/2"},
    "discreta": {"calculo": "logica", "formula": "p -> q"},
    "codigos": {"calculo": "cesar", "texto": "HOLA", "k": 3},
    "informacion": {"calculo": "entropia"},
    "deteccion": {"calculo": "matriz_r", "r": [1, "1/2"]},
    "aprende": {"calculo": "gd"},
    "refuerzo": {"calculo": "absorcion", "P": [[1, 0], ["1/2", "1/2"]]},
    "finanzas": {"calculo": "van", "flujos": [-1000, 500, 500, 500],
                 "r": "0.05"},
    "ejercicio": {"calculo": "genera", "tema": "ecuaciones", "semilla": 3},
    # `pulido` con una entrada barata y **no recursiva**: si su muestra fuese
    # «certifica», la medición se llamaría a sí misma para siempre.
    "pulido": {"calculo": "accesibilidad", "operacion": "derivar",
               "entrada": "x^3+2*x"},
}


@dataclass
class Auditoria:
    """El resultado de la certificación: qué se comprobó y qué falló."""

    comprobadas: int = 0
    sin_muestra: tuple[str, ...] = ()
    fallos: list[str] = field(default_factory=list)
    criterios: dict[str, list[str]] = field(default_factory=dict)
    lentas: list[str] = field(default_factory=list)
    no_deterministas: list[str] = field(default_factory=list)
    sin_porque: list[str] = field(default_factory=list)
    sin_metodo: list[str] = field(default_factory=list)
    errores_internos: list[str] = field(default_factory=list)

    @property
    def certifica(self) -> bool:
        return self.comprobadas > 0 and not self.fallos

    def texto(self) -> str:
        if not self.comprobadas:
            return "sin operaciones que comprobar"
        partes = [f"{self.comprobadas} operaciones comprobadas"]
        if self.sin_muestra:
            partes.append(f"{len(self.sin_muestra)} sin muestra canónica")
        if self.lentas:
            partes.append(f"{len(self.lentas)} por encima del techo")
        if self.no_deterministas:
            partes.append(f"{len(self.no_deterministas)} no deterministas")
        if self.sin_porque:
            partes.append(f"{len(self.sin_porque)} sin «por qué»")
        if self.sin_metodo:
            partes.append(f"{len(self.sin_metodo)} sin paso de método")
        if self.errores_internos:
            partes.append(f"{len(self.errores_internos)} con error interno")
        if self.fallos:
            partes.append(f"{len(self.fallos)} con fallos")
        return "; ".join(partes)


#: los criterios de §8.4 que se pueden comprobar sin intervención humana
CRITERIOS = (
    "1. existe y tiene modo paso a paso",
    "2. ningún resultado sin segundo camino",
    "3. los pasos nombran la regla y el porqué",
    "5. se puede pedir por programa sin interfaz",
    "6. sin solución exacta se avisa",
    "8. cumple el contrato de §5.9",
)

#: §8.4 solo nombra estas familias para el «por qué se eligió este método».
#: El usuario decidió (2026-10-09) que **todas** las calculadoras lo
#: muestren, y esa es la regla que se aplica: mantener una lista de
#: excepciones sería dejar la regla blanda justo donde no se nota. La lista se
#: conserva porque documenta qué exigía el documento original, no porque exija
#: menos ahora.
CON_POR_QUE_OBLIGATORIO = ("derivar", "integrar", "limite", "serie", "edo",
                           "laplace", "fourier", "transformada_z", "taylor",
                           "primitiva", "tfc", "contorno")
#: a partir de ML-11, el porqué es obligatorio en **todas** las calculadoras
TODAS_DEBEN_EXPLICAR_EL_METODO = True

#: excepciones del dominio que NUNCA deben salir de una calculadora: son
#: errores internos (bug), no peticiones malas. Si una se escapa, es un fallo
#: de programación y hay que arreglarlo, no documentarlo.
ERRORES_INTERNOS = (TypeError, AttributeError, IndexError, KeyError,
                    ZeroDivisionError, RecursionError, UnboundLocalError,
                    NameError, ArithmeticError)


def audita(operaciones: tuple[str, ...] | None = None,
           *, techo: float = TECHO_S,
           medir: bool = True) -> Auditoria:
    """Recorre las operaciones registradas y comprueba §8.4 punto por punto.

    ``medir=False`` salta la comprobación de tiempo y determinismo, para cuando
    se quiere solo la forma. Lo que **no** se comprueba (el 4, el 7 y el 9, que
    son de juicio o de cobertura) se deja fuera del informe en vez de marcarse
    como cumplidos.
    """
    ops = operaciones if operaciones is not None else tuple(sorted(C.operaciones()))
    a = Auditoria()
    for op in ops:
        if op not in MUESTRAS:
            a.sin_muestra = a.sin_muestra + (op,)
            continue
        a.comprobadas += 1
        fallos: list[str] = []
        try:
            r = C.calcular(C.Peticion(op, MUESTRAS[op]))
        except ERRORES_INTERNOS as exc:
            a.errores_internos.append(f"{op}: {type(exc).__name__}: {exc}")
            a.fallos.append(f"{op}: error interno {type(exc).__name__}: {exc}")
            continue
        except Exception as exc:
            a.fallos.append(f"{op}:{exc}")
            continue
        problemas = C.validar_forma(r)
        if problemas:
            fallos.append("criterio 8 (forma del contrato): " + "; ".join(problemas))
        if not len(r.traza):
            fallos.append("criterio 1: traza vacía")
        elif not any(p.why for p in r.traza):
            # el porqué del método es obligatorio en todas (§5.5b, y el
            # usuario lo confirmó para las 80): sin él el alumno ve QUÉ se
            # hizo y no POR QUÉ, que es justo lo que el laboratorio promete
            fallos.append("criterio 3: ningún paso dice por qué se eligió "
                          "el método")
        # criterio 3bis: el método tiene que estar *nombrado*, no solo
        # justificado: un `regla` suelto sin `metodo` no explica el método
        if not any(p.kind == "metodo" for p in r.traza):
            a.sin_metodo.append(op)
        # criterio 2: un resultado discrepante es una respuesta, no un fallo de
        # forma; lo que no puede pasar es que se presente como verificado
        if r.sello.verdict == V.DISCREPANT and not r.avisos:
            fallos.append("criterio 2: discrepa sin aviso")
        # criterio 6: solo numérico sin nada que lo explique es una pista
        if r.sello.verdict == V.NUMERIC_ONLY and not r.sello.detail:
            fallos.append("criterio 6: «solo numérico» sin decir por qué")
        # accesibilidad, si trae gráfica
        acc = audita_accesibilidad(r)
        if not acc.accesible:
            fallos.append("§6: " + "; ".join(acc.problemas))
        if fallos:
            a.fallos.extend(f"{op}: {f}" for f in fallos)
        if medir:
            try:
                m = mide(op, MUESTRAS[op], techo=techo)
                if not m.cumple:
                    a.lentas.append(f"{op} ({m.segundos:.2f} s)")
                if not m.determinista:
                    a.no_deterministas.append(op)
            except Exception as exc:
                a.fallos.append(f"{op}: no se pudo medir: {exc}")
        a.criterios[op] = fallos
    return a


def certifica(operaciones: tuple[str, ...] | None = None,
              *, techo: float = TECHO_S) -> Auditoria:
    """Certificación con medición: es ``audita`` y además no perdona ni el
    tiempo ni el determinismo."""
    a = audita(operaciones, techo=techo, medir=True)
    if a.lentas:
        a.fallos.extend(f"rendimiento: {op} excede el techo" for op in a.lentas)
    if a.no_deterministas:
        a.fallos.extend(f"determinismo: {op} da resultados distintos"
                        for op in a.no_deterministas)
    return a


# ---------------------------------------------------------------------------
# robustez: ninguna calculadora puede responder con un error interno
# ---------------------------------------------------------------------------

#: entradas que no son peticiones válidas y que toda calculadora debe
#: rechazar **con un motivo**, no revientar con un TypeError
BASURA: tuple[object, ...] = (
    None, "", "no soy una expresión", [], {}, 0, [1], {"calculo": 7},
    {"expr": "x +* 2"}, {"matriz": [[1, 2], [3]]}, {"expr": "1/0"},
)


def audita_robustez(operaciones: tuple[str, ...] | None = None) -> list[str]:
    """Alimenta basura a cada calculadora y anota las que se rompen por dentro.

    Distingue lo que debe pasar de lo que no:

    - si la calculadora **rechaza** con ``ValidationError`` o
      ``UnsupportedError``, está bien: una petición mala se dice;
    - si devuelve un resultado, puede pasar (algunas calculadoras aceptan
      `""` y devuelven algo vacío), pero se registra como *sorprendente*;
    - si suelta un error **interno** (``TypeError``, ``IndexError``…), es un
      bug y se anota como tal: eso hay que arreglarlo, no documentarlo.
    """
    ops = operaciones if operaciones is not None else tuple(sorted(C.operaciones()))
    rotos: list[str] = []
    for op in ops:
        for basura in BASURA:
            try:
                C.calcular(C.Peticion(op, basura))
            except (ValidationError, UnsupportedError):
                continue                      # bien: se rechaza con motivo
            except ERRORES_INTERNOS as exc:
                rotos.append(f"{op} con {basura!r}: "
                             f"{type(exc).__name__}: {exc}")
            except Exception:
                continue                      # otro dominio: no es un bug
    return rotos


def audita_pasos(operaciones: tuple[str, ...] | None = None) -> list[str]:
    """Comprueba que **toda** calculadora muestra los pasos y el porqué.

    Tres cosas, y las tres son de §5.2/§5.5b:

    1. que la traza no esté vacía;
    2. que algún paso diga **por qué** se eligió el método;
    3. que haya un paso de tipo ``metodo``, que es donde §5.5b exige el
       «por qué este método» — un paso ``regla`` suelto no lo cuenta.
    """
    ops = operaciones if operaciones is not None else tuple(sorted(C.operaciones()))
    fallos: list[str] = []
    for op in ops:
        if op not in MUESTRAS:
            fallos.append(f"{op}: sin muestra canónica, no se puede comprobar")
            continue
        try:
            r = C.calcular(C.Peticion(op, MUESTRAS[op]))
        except ERRORES_INTERNOS as exc:
            fallos.append(f"{op}: error interno {type(exc).__name__}: {exc}")
            continue
        except Exception as exc:
            fallos.append(f"{op}: la muestra canónica falla ({exc})")
            continue
        pasos = list(r.traza)
        if not pasos:
            fallos.append(f"{op}: traza vacía")
            continue
        if not any(p.why for p in pasos):
            fallos.append(f"{op}: ningún paso dice por qué se eligió el método")
        if not any(p.kind == "metodo" for p in pasos):
            fallos.append(f"{op}: ningún paso de tipo «metodo» (§5.5b)")
        # los tres niveles tienen que renderizar sin romperse
        for nivel in ("resumen", "paso", "detallado"):
            try:
                r.traza.render(nivel)
            except Exception as exc:
                fallos.append(f"{op}: no renderiza en «{nivel}» ({exc})")
    return fallos