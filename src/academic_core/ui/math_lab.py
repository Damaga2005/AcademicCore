# SPDX-License-Identifier: MIT
"""Laboratorio de Matemáticas: la interfaz de §9 de ``docs/labs/MATH_LAB.md``.

Pestañas por bloque (0 a 7, y 8 a 19 agrupados en «Discreta y códigos»,
«Datos e IA», «Señales y detección» y «Campos y física») más
**Calculadoras** (las 80 operaciones) y **Ejercicios**. Cada pestaña de
bloque es la misma calculadora filtrada a sus operaciones.

- Editor de fórmulas con vista previa en vivo (``mvexpr.preview``); la
  entrada estructurada se escribe como JSON y se previsualizan sus fórmulas.
- Panel de pasos navegable: anterior, siguiente y reproducir; el paso actual
  resalta el trozo afectado (``Step.piece``) dentro de su «antes».
- Gráfica enlazada al resultado (``Resultado.grafica``) con su descripción
  textual, que es la alternativa accesible de §6.
- Ejercicios con su insignia de respaldo (E examen, G guía) y sus
  convenciones declaradas; corrección por el corrector del motor.
- Todo con teclado: Ctrl+Intro calcula, Alt+← / Alt+→ recorren los pasos,
  Alt+R reproduce; cada control lleva nombre accesible. En español.

Aquí no se calcula nada: todo pasa por ``contract.calcular``.
"""

from __future__ import annotations

import html
import importlib
import json
import pkgutil

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from academic_core.domain.engineering import mathlab as _ml
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.ui.lab_view import PlotView
from academic_core.ui.workers import ServiceWorker

#: §9: bloques 0 a 7 y los cuatro grupos de v2; cada operación en su bloque
BLOQUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("0 · Aritmética y álgebra", ("simplificar", "evaluar", "racional", "resolver",
                                  "resolver_inequidad", "igualdad", "transformar", "dimensional")),
    ("1 · Funciones", ("ramas", "caracteristicas", "estudio", "soluciones")),
    ("2 · Cálculo", ("derivar", "limite", "taylor", "integrar", "primitiva", "riemann", "impropia",
                     "tfc", "inversa", "teorema", "aplicacion_integral", "extremos_absolutos",
                     "a_trozos", "aproximar", "serie", "gamma")),
    ("3 · Álgebra lineal", ("algebra", "lineal", "espacios", "complejo")),
    ("4 · Vectorial", ("gradiente", "multivar", "multiple", "vectorial", "operadores",
                       "comprobar_gradiente")),
    ("5 · EDO y transformadas", ("edo", "laplace", "fourier", "transformada_z", "contorno",
                                 "distribucion")),
    ("6 · Probabilidad", ("probabilidad", "variable_aleatoria", "vector_aleatorio",
                          "aproximacion_normal", "estadistica", "intervalo_confianza", "contraste",
                          "regresion", "estimador", "proceso", "tabla_estadistica", "comunicaciones",
                          "montecarlo", "cola_mm1")),
    ("7 · Numéricos", ("metodo_numerico", "numericos")),
    ("Discreta y códigos", ("discreta", "modular", "codigos", "informacion", "huffman", "grafo",
                            "demuestra")),
    ("Datos e IA", ("markov", "refuerzo", "aprende", "finanzas")),
    ("Señales y detección", ("senales", "deteccion", "fasor", "polarizacion")),
    ("Campos y física", ("campos", "fisica")),
)

#: claves de una entrada estructurada que llevan una fórmula a previsualizar
_FORMULAS = ("expr", "f", "g", "termino", "integrando", "V", "ecuacion", "funcion", "F")

RESPALDO = {"E": "E · sale en exámenes reales", "G": "G · de la guía"}


def operaciones() -> tuple[str, ...]:
    """Todas las operaciones registradas (cargar los módulos las registra)."""
    for m in pkgutil.iter_modules(_ml.__path__):
        importlib.import_module(f"{_ml.__name__}.{m.name}")
    return C.operaciones()


def muestra(op: str) -> str:
    """La entrada de ejemplo de la operación, como se escribe en el editor."""
    from academic_core.domain.engineering.mathlab import pulido as P

    e = P.MUESTRAS.get(op, "")
    return e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)


def leer_entrada(texto: str) -> object:
    """Texto del editor → entrada: JSON si empieza por «{» o «[», si no la fórmula."""
    t = texto.strip()
    if t[:1] in "{[":
        try:
            return json.loads(t)
        except json.JSONDecodeError as exc:
            raise C.error("BAD_INPUT", f"la entrada estructurada no es JSON válido "
                                       f"(línea {exc.lineno}, columna {exc.colno})") from exc
    return t


def vista_previa(texto: str) -> str:
    """Lo que se ve bajo el editor mientras se escribe; nunca lanza."""
    t = texto.strip()
    if not t:
        return ""
    if t[:1] not in "{[":
        return mx.preview(t)
    try:
        e = json.loads(t)
    except json.JSONDecodeError as exc:
        return f"⚠ JSON incompleto (línea {exc.lineno}, columna {exc.colno})"
    if not isinstance(e, dict):
        return "entrada estructurada (lista)"
    partes = [f"{k} = {mx.preview(str(e[k]))}" for k in _FORMULAS
              if isinstance(e.get(k), str) and e[k].strip()]
    return "; ".join(partes) or f"entrada estructurada: {', '.join(map(str, e))}"


def paso_html(paso) -> str:
    """El paso con su trozo afectado resaltado dentro del «antes» (§9)."""
    def marca(texto: str) -> str:
        t = html.escape(texto)
        if paso.piece and paso.piece in texto:
            p = html.escape(paso.piece)
            t = t.replace(p, f"<mark>{p}</mark>", 1)
        return t
    filas = [f"<p><b>{html.escape(paso.label)}</b></p>"]
    if paso.before:
        filas.append(f"<p>antes: {marca(paso.before)}</p>")
    elif paso.piece:
        filas.append(f"<p>trozo: <mark>{html.escape(paso.piece)}</mark></p>")
    if paso.after:
        filas.append(f"<p>después: {html.escape(paso.after)}</p>")
    if paso.why:
        filas.append(f"<p><i>por qué:</i> {html.escape(paso.why)}</p>")
    for metodo, motivo in paso.alternatives:
        filas.append(f"<p>descartado: {html.escape(metodo)} — {html.escape(motivo)}</p>")
    return "".join(filas)


def series_de(grafica) -> list[tuple[str, list[float], list[float]]]:
    """Las series del resultado para ``PlotView``, partidas en sus discontinuidades."""
    out = []
    for s in grafica.series if grafica else ():
        cortes = [0, *sorted(set(s.discontinuities)), len(s.xs)]
        for a, b in zip(cortes, cortes[1:]):
            if b - a > 1:
                out.append((s.name, list(s.xs[a:b]), list(s.ys[a:b])))
    return out


def texto_resultado(r: C.Resultado) -> str:
    lineas = [f"resultado: {r.exacto}"]
    if r.aproximado is not None:
        lineas.append(f"aproximado: {r.aproximado}")
    if r.error_acotado is not None:
        lineas.append(f"error acotado: {r.error_acotado:.3g}")
    lineas.append(f"sello: {r.sello.verdict} — {r.sello.method}")
    lineas += [f"hipótesis: {h}" for h in r.hipotesis]
    lineas += [f"convención: {c}" for c in r.convenciones.as_lines()]
    lineas += [f"aviso: {a}" for a in r.avisos]
    return "\n".join(lineas)


class PasosPanel(QWidget):
    """Pasos navegables: anterior, siguiente y reproducir, con el trozo resaltado."""

    INTERVALO_MS = 1200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pasos: list = []
        self.lista = QListWidget()
        self.lista.setAccessibleName("Pasos")
        self.lista.setWordWrap(True)
        self.detalle = QTextBrowser()
        self.detalle.setAccessibleName("Paso actual")
        self.btn_anterior = QPushButton("◀ &Anterior")
        self.btn_siguiente = QPushButton("&Siguiente ▶")
        self.btn_reproducir = QPushButton("&Reproducir")
        for b, nombre in ((self.btn_anterior, "Paso anterior"), (self.btn_siguiente, "Paso siguiente"),
                          (self.btn_reproducir, "Reproducir los pasos")):
            b.setAccessibleName(nombre)
        self.posicion = QLabel("sin pasos")
        barra = QHBoxLayout()
        for w in (self.btn_anterior, self.btn_siguiente, self.btn_reproducir, self.posicion):
            barra.addWidget(w)
        barra.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(barra)
        split = QSplitter()
        split.addWidget(self.lista)
        split.addWidget(self.detalle)
        split.setSizes([260, 420])
        lay.addWidget(split, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(self.INTERVALO_MS)
        self.timer.timeout.connect(self._avanza)
        self.btn_anterior.clicked.connect(lambda: self.ir(self.lista.currentRow() - 1))
        self.btn_siguiente.clicked.connect(lambda: self.ir(self.lista.currentRow() + 1))
        self.btn_reproducir.clicked.connect(self.reproducir)
        self.lista.currentRowChanged.connect(self._mostrar)
        self._mostrar(-1)

    def poner(self, traza, nivel: str) -> None:
        self.timer.stop()
        self.btn_reproducir.setText("&Reproducir")
        self.pasos = [p for p in (traza.steps if traza else ()) if p.at_level(nivel)]
        self.lista.clear()
        self.lista.addItems([f"{i + 1}. {p.label}" for i, p in enumerate(self.pasos)])
        self.ir(0 if self.pasos else -1)

    def ir(self, i: int) -> None:
        if not self.pasos:
            self._mostrar(-1)
            return
        self.lista.setCurrentRow(max(0, min(i, len(self.pasos) - 1)))

    def reproducir(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.btn_reproducir.setText("&Reproducir")
            return
        if self.lista.currentRow() >= len(self.pasos) - 1:
            self.ir(0)
        self.btn_reproducir.setText("&Pausa")
        self.timer.start()

    def _avanza(self) -> None:
        if self.lista.currentRow() >= len(self.pasos) - 1:
            self.reproducir()          # al final se para solo
            return
        self.ir(self.lista.currentRow() + 1)

    def _mostrar(self, i: int) -> None:
        hay = 0 <= i < len(self.pasos)
        self.detalle.setHtml(paso_html(self.pasos[i]) if hay else "")
        self.posicion.setText(f"paso {i + 1} de {len(self.pasos)}" if hay else "sin pasos")
        self.btn_anterior.setEnabled(hay and i > 0)
        self.btn_siguiente.setEnabled(hay and i < len(self.pasos) - 1)
        self.btn_reproducir.setEnabled(len(self.pasos) > 1)


class CalculadoraView(QWidget):
    """Una calculadora sobre ``ops``: editor, vista previa, resultado, pasos y gráfica."""

    def __init__(self, ops: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.ultimo: C.Resultado | None = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)   # el motor tiene límites de tiempo globales
        self.operacion = QComboBox()
        self.operacion.setAccessibleName("Operación")
        self.operacion.addItems(list(ops))
        self.nivel = QComboBox()
        self.nivel.setAccessibleName("Nivel de detalle de los pasos")
        self.nivel.addItems(["resumen", "paso", "detallado"])
        self.nivel.setCurrentText("paso")
        self.editor = QPlainTextEdit()
        self.editor.setAccessibleName("Entrada: fórmula o JSON")
        self.editor.setTabChangesFocus(True)
        self.editor.setMaximumHeight(90)
        self.previa = QLabel()
        self.previa.setAccessibleName("Vista previa")
        self.previa.setWordWrap(True)
        self.btn_calcular = QPushButton("&Calcular")
        self.btn_calcular.setAccessibleName("Calcular (Ctrl+Intro)")
        self.btn_ejemplo = QPushButton("&Ejemplo")
        self.btn_ejemplo.setAccessibleName("Cargar la entrada de ejemplo")
        self.salida = QPlainTextEdit(readOnly=True)
        self.salida.setAccessibleName("Resultado")
        self.pasos = PasosPanel()
        self.grafica = PlotView("Gráfica")
        self.descripcion = QLabel()
        self.descripcion.setWordWrap(True)
        self.descripcion.setAccessibleName("Descripción de la gráfica")

        form = QFormLayout()
        form.addRow("Operación", self.operacion)
        form.addRow("Entrada", self.editor)
        form.addRow("Vista previa", self.previa)
        botones = QHBoxLayout()
        for w in (self.btn_calcular, self.btn_ejemplo, QLabel("Detalle"), self.nivel):
            botones.addWidget(w)
        botones.addStretch(1)
        izquierda = QWidget()
        li = QVBoxLayout(izquierda)
        li.setContentsMargins(0, 0, 0, 0)
        li.addLayout(form)
        li.addLayout(botones)
        li.addWidget(self.salida, 1)
        derecha = QTabWidget()
        derecha.addTab(self.pasos, "Pasos")
        figura = QWidget()
        lf = QVBoxLayout(figura)
        lf.addWidget(self.grafica, 1)
        lf.addWidget(self.descripcion)
        derecha.addTab(figura, "Gráfica")
        self.derecha = derecha
        split = QSplitter()
        split.addWidget(izquierda)
        split.addWidget(derecha)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        self.editor.textChanged.connect(lambda: self.previa.setText(
            vista_previa(self.editor.toPlainText())))
        self.operacion.currentTextChanged.connect(self.cargar_ejemplo)
        self.btn_ejemplo.clicked.connect(self.cargar_ejemplo)
        self.btn_calcular.clicked.connect(self.calcular)
        self.nivel.currentTextChanged.connect(
            lambda n: self.pasos.poner(self.ultimo.traza if self.ultimo else None, n))
        # cada pestaña tiene su calculadora: el atajo es de la que tiene el foco, si no
        # serían trece atajos iguales en la ventana y Qt no dispararía ninguno
        for tecla, accion in (("Ctrl+Return", self.btn_calcular.click),
                              ("Ctrl+Enter", self.btn_calcular.click),
                              ("Alt+Left", self.pasos.btn_anterior.click),
                              ("Alt+Right", self.pasos.btn_siguiente.click)):
            atajo = QShortcut(QKeySequence(tecla), self, activated=accion)
            atajo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.cargar_ejemplo()

    def cargar_ejemplo(self, *_):
        self.editor.setPlainText(muestra(self.operacion.currentText()))

    def calcular(self) -> None:
        try:
            pet = C.Peticion(self.operacion.currentText(), leer_entrada(self.editor.toPlainText()),
                             nivel=self.nivel.currentText())
        except Exception as exc:  # noqa: BLE001 — el error se enseña, no se propaga
            self._error(exc)
            return
        self.btn_calcular.setEnabled(False)
        self.salida.setPlainText("calculando…")
        w = ServiceWorker(C.calcular, pet)
        w.signals.finished.connect(self._resultado)
        w.signals.failed.connect(self._error)
        self.pool.start(w)

    def _resultado(self, r: C.Resultado) -> None:
        self.btn_calcular.setEnabled(True)
        self.ultimo = r
        self.salida.setPlainText(texto_resultado(r))
        self.pasos.poner(r.traza, self.nivel.currentText())
        self.grafica.set_series(series_de(r.grafica))
        self.descripcion.setText(r.grafica.describe() if r.grafica else "este resultado no tiene gráfica")
        self.derecha.setTabEnabled(1, r.grafica is not None)

    def _error(self, exc) -> None:
        self.btn_calcular.setEnabled(True)
        self.ultimo = None
        msg = getattr(exc, "message", None) or str(exc)
        self.salida.setPlainText(f"⚠ {msg}")
        self.pasos.poner(None, self.nivel.currentText())
        self.grafica.set_series([])
        self.descripcion.setText("")


class EjerciciosView(QWidget):
    """Ejercicios sembrados con insignia E/G, convenciones, pistas y corrección (§7, §9)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from academic_core.domain.engineering.mathlab import ejercicios as E

        self.E = E
        self.ejercicio = None
        self.n_pistas = 0
        self.tema = QComboBox()
        self.tema.setAccessibleName("Tema")
        self.tema.addItems(list(E.TEMAS))
        self.dificultad = QComboBox()
        self.dificultad.setAccessibleName("Dificultad")
        self.dificultad.addItems(["facil", "media", "dificil"])
        self.dificultad.setCurrentText("media")
        self.semilla = QSpinBox()
        self.semilla.setAccessibleName("Semilla")
        self.semilla.setRange(1, 10 ** 6)
        self.btn_generar = QPushButton("&Generar")
        self.insignia = QLabel()
        self.insignia.setAccessibleName("Respaldo del ejercicio")
        self.insignia.setObjectName("Badge")
        self.enunciado = QLabel()
        self.enunciado.setWordWrap(True)
        self.enunciado.setAccessibleName("Enunciado")
        self.convenciones = QLabel()
        self.convenciones.setWordWrap(True)
        self.convenciones.setAccessibleName("Convenciones declaradas")
        self.respuesta = QLineEdit()
        self.respuesta.setAccessibleName("Tu respuesta")
        self.previa = QLabel()
        self.previa.setAccessibleName("Vista previa de la respuesta")
        self.btn_corregir = QPushButton("C&orregir")
        self.btn_pista = QPushButton("&Pista")
        self.btn_solucion = QPushButton("&Ver solución")
        self.salida = QTextBrowser()
        self.salida.setAccessibleName("Corrección, pistas y solución")

        arriba = QHBoxLayout()
        for etiqueta, w in (("Tema", self.tema), ("Dificultad", self.dificultad), ("Semilla", self.semilla)):
            arriba.addWidget(QLabel(etiqueta))
            arriba.addWidget(w)
        arriba.addWidget(self.btn_generar)
        arriba.addStretch(1)
        acciones = QHBoxLayout()
        for w in (self.btn_corregir, self.btn_pista, self.btn_solucion):
            acciones.addWidget(w)
        acciones.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addLayout(arriba)
        lay.addWidget(self.insignia)
        lay.addWidget(self.enunciado)
        lay.addWidget(self.convenciones)
        form = QFormLayout()
        form.addRow("Respuesta", self.respuesta)
        form.addRow("Vista previa", self.previa)
        lay.addLayout(form)
        lay.addLayout(acciones)
        lay.addWidget(self.salida, 1)

        self.btn_generar.clicked.connect(self.generar)
        self.btn_corregir.clicked.connect(self.corregir)
        self.respuesta.returnPressed.connect(self.btn_corregir.click)
        self.btn_pista.clicked.connect(self.pista)
        self.btn_solucion.clicked.connect(self.solucion)
        self.respuesta.textChanged.connect(lambda t: self.previa.setText(vista_previa(t)))
        self._activa(False)

    def _activa(self, si: bool) -> None:
        for w in (self.respuesta, self.btn_corregir, self.btn_pista, self.btn_solucion):
            w.setEnabled(si)

    def _peticion(self, calculo: str, **extra) -> dict:
        return {"calculo": calculo, "tema": self.tema.currentText(),
                "dificultad": self.dificultad.currentText(), "semilla": self.semilla.value(), **extra}

    def generar(self) -> None:
        try:
            ex = self.E.genera(self.tema.currentText(), self.dificultad.currentText(),
                               self.semilla.value())
        except Exception as exc:  # noqa: BLE001 — se dice por qué, no se inventa uno
            self.ejercicio = None
            self._activa(False)
            self.salida.setPlainText(f"⚠ {getattr(exc, 'message', None) or exc}")
            return
        self.ejercicio, self.n_pistas = ex, 0
        self.insignia.setText(f"[{RESPALDO.get(ex.respaldo, ex.respaldo)}] · {ex.asignatura} · "
                              f"{ex.dificultad} · se entrega: {ex.tipo}")
        self.enunciado.setText(ex.enunciado)
        self.convenciones.setText(
            "convenciones: " + "; ".join(f"{k} = {v}" for k, v in ex.convenciones)
            if ex.convenciones else "convenciones: las del motor por defecto")
        self.respuesta.clear()
        self.salida.clear()
        self._activa(True)
        self.respuesta.setFocus()

    def corregir(self) -> None:
        if self.ejercicio is None:
            return
        try:
            r = C.calcular(C.Peticion("ejercicio", self._peticion(
                "corrige", respuesta=leer_entrada(self.respuesta.text()))))
            self.salida.setPlainText(f"{r.exacto}\n(sello: {r.sello.verdict})")
        except Exception as exc:  # noqa: BLE001
            self.salida.setPlainText(f"⚠ {getattr(exc, 'message', None) or exc}")

    def pista(self) -> None:
        if self.ejercicio is None:
            return
        self.n_pistas = min(self.n_pistas + 1, len(self.ejercicio.pistas))
        dadas = self.ejercicio.pistas_hasta(self.n_pistas)
        self.salida.setPlainText("\n".join(f"pista {i + 1}: {p}" for i, p in enumerate(dadas))
                                 or "este ejercicio no tiene pistas")

    def solucion(self) -> None:
        if self.ejercicio is None:
            return
        ex = self.ejercicio
        self.salida.setPlainText(f"solución: {ex.solucion}\n\n{ex.solucion_pasos}".rstrip())


class MathLabPanel(QWidget):
    """Laboratorio de Matemáticas (§9): bloques, Calculadoras y Ejercicios."""

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self.app = app
        todas = operaciones()
        self.pestanas = QTabWidget()
        self.pestanas.setAccessibleName("Bloques del laboratorio de matemáticas")
        self.calculadoras: dict[str, CalculadoraView] = {}
        for nombre, ops in BLOQUES:
            vista = CalculadoraView(tuple(o for o in ops if o in todas))
            self.calculadoras[nombre] = vista
            self.pestanas.addTab(vista, nombre)
        self.calculadoras["Calculadoras"] = CalculadoraView(todas)
        self.pestanas.addTab(self.calculadoras["Calculadoras"], "Calculadoras")
        self.ejercicios = EjerciciosView()
        self.pestanas.addTab(self.ejercicios, "Ejercicios")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.pestanas)
