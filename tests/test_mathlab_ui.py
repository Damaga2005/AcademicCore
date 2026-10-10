# SPDX-License-Identifier: MIT
"""La interfaz de §9 de MATH_LAB.md, usada como la usa el alumno: con los botones
y el teclado, no llamando al motor por debajo."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt

from academic_core.domain.engineering.mathlab import ejercicios as E
from academic_core.ui import math_lab as M


@pytest.fixture(scope="module")
def ops():
    return M.operaciones()


@pytest.fixture()
def panel(qtbot):
    w = M.MathLabPanel()
    qtbot.addWidget(w)
    return w


def _calcula(qtbot, vista, op, entrada):
    vista.operacion.setCurrentText(op)
    vista.editor.setPlainText(entrada)
    vista.btn_calcular.click()
    qtbot.waitUntil(lambda: vista.btn_calcular.isEnabled(), timeout=60000)


def test_cada_operacion_esta_en_un_bloque_y_ninguna_se_inventa(ops):
    en_bloques = [o for _, b in M.BLOQUES for o in b]
    assert len(en_bloques) == len(set(en_bloques)), "una operación en dos bloques"
    assert set(en_bloques) <= set(ops)
    # las que no son de ningún bloque son utilidades: solo en «Calculadoras»
    assert set(ops) - set(en_bloques) == {"convencion", "ejercicio", "pulido"}


def test_pestanas_de_bloque_calculadoras_y_ejercicios(panel, ops):
    nombres = [panel.pestanas.tabText(i) for i in range(panel.pestanas.count())]
    assert nombres[:8] == [b for b, _ in M.BLOQUES[:8]]
    assert {"Discreta y códigos", "Datos e IA", "Señales y detección", "Campos y física"} <= set(nombres)
    assert nombres[-2:] == ["Calculadoras", "Ejercicios"]
    assert panel.calculadoras["Calculadoras"].operacion.count() == len(ops)


def test_vista_previa_en_vivo(panel):
    v = panel.calculadoras["2 · Cálculo"]
    v.editor.setPlainText("x^2*sqrt(x)")
    assert v.previa.text() == "x²·√x"
    v.editor.setPlainText("x^2*(")
    assert v.previa.text().startswith("⚠")
    v.editor.setPlainText('{"expr": "sin(x)^2", "a": "0"}')
    assert v.previa.text() == "expr = sen(x)²"


def test_calcular_da_resultado_pasos_y_grafica(qtbot, panel):
    v = panel.calculadoras["2 · Cálculo"]
    _calcula(qtbot, v, "derivar", "x^3+2*x")
    assert "3·x² + 2" in v.salida.toPlainText() and "sello: verificado" in v.salida.toPlainText()
    assert v.pasos.lista.count() >= 2 and v.pasos.lista.currentRow() == 0
    assert v.grafica.series and "derivada" in v.descripcion.text()
    # una polilínea con los x desordenados se dibuja como una maraña
    assert all(xs == sorted(xs) for _, xs, _ in v.grafica.series)


def test_pasos_navegables_y_reproducir(qtbot, panel):
    v = panel.calculadoras["2 · Cálculo"]
    _calcula(qtbot, v, "derivar", "x^3+2*x")
    p = v.pasos
    n = len(p.pasos)
    assert not p.btn_anterior.isEnabled() and p.btn_siguiente.isEnabled()
    p.btn_siguiente.click()
    assert p.lista.currentRow() == 1 and p.posicion.text() == f"paso 2 de {n}"
    p.btn_anterior.click()
    assert p.lista.currentRow() == 0
    p.timer.setInterval(5)
    p.btn_reproducir.click()
    qtbot.waitUntil(lambda: not p.timer.isActive(), timeout=5000)
    assert p.lista.currentRow() == n - 1 and p.btn_reproducir.text() == "&Reproducir"


def test_el_trozo_afectado_se_resalta():
    from academic_core.domain.engineering.mathlab.trace import Step
    paso = Step(index=0, kind="regla", rule="r", label="derivar el producto",
                before="x^2*sin(x) + 1", piece="x^2*sin(x)", after="2*x*sin(x) + x^2*cos(x) + 1")
    h = M.paso_html(paso)
    assert "<mark>x^2*sin(x)</mark> + 1" in h and "después" in h


def test_el_nivel_de_detalle_filtra_los_pasos(qtbot, panel):
    v = panel.calculadoras["2 · Cálculo"]
    _calcula(qtbot, v, "derivar", "x^3+2*x")
    en_paso = len(v.pasos.pasos)
    v.nivel.setCurrentText("detallado")
    assert len(v.pasos.pasos) >= en_paso
    v.nivel.setCurrentText("resumen")
    assert len(v.pasos.pasos) <= en_paso


def test_un_error_se_ensena_en_espanol_sin_dialogo(qtbot, panel):
    v = panel.calculadoras["2 · Cálculo"]
    _calcula(qtbot, v, "derivar", "x^2*(")
    assert v.salida.toPlainText().startswith("⚠") and v.pasos.posicion.text() == "sin pasos"
    v.editor.setPlainText('{"expr": ')
    v.btn_calcular.click()
    assert "JSON" in v.salida.toPlainText()


def test_teclado_ctrl_intro_y_alt_flechas(qtbot, panel):
    v = panel.calculadoras["Calculadoras"]
    panel.pestanas.setCurrentWidget(v)
    panel.show()
    panel.activateWindow()
    qtbot.waitActive(panel)
    v.operacion.setCurrentText("derivar")
    v.editor.setPlainText("x^3+2*x")
    v.editor.setFocus()
    qtbot.waitUntil(v.editor.hasFocus)        # el atajo es de la calculadora con el foco
    qtbot.keyClick(v.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: v.pasos.lista.count() >= 2, timeout=60000)
    qtbot.keyClick(v.editor, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    assert v.pasos.lista.currentRow() == 1
    qtbot.keyClick(v.editor, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    assert v.pasos.lista.currentRow() == 0


def test_todo_control_lleva_nombre_accesible(panel):
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox
    sin_nombre = [w for t in (QComboBox, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox)
                  for w in panel.findChildren(t)
                  if not (w.accessibleName() or (isinstance(w, QPushButton) and w.text()))
                  and not isinstance(w.parent(), (QComboBox, QSpinBox))]
    assert sin_nombre == []


def test_ejercicio_con_insignia_convenciones_pistas_y_correccion(panel):
    e = panel.ejercicios
    e.tema.setCurrentText("ecuaciones")
    e.semilla.setValue(3)
    e.btn_generar.click()
    ex = E.genera("ecuaciones", "media", 3)
    assert e.enunciado.text() == ex.enunciado
    assert e.insignia.text().startswith("[E · sale en exámenes reales]")
    assert e.convenciones.text().startswith("convenciones:")
    e.respuesta.setText(str(ex.solucion))
    e.btn_corregir.click()
    assert "✔" in e.salida.toPlainText() or "✓" in e.salida.toPlainText()
    e.respuesta.setText("999")
    e.respuesta.returnPressed.emit()
    assert "✘" in e.salida.toPlainText()
    e.btn_pista.click()
    assert e.salida.toPlainText().startswith("pista 1:")
    e.btn_solucion.click()
    assert e.salida.toPlainText().startswith(f"solución: {ex.solucion}")


def test_sin_ejercicio_no_se_puede_corregir(panel):
    e = panel.ejercicios
    assert not e.btn_corregir.isEnabled() and not e.respuesta.isEnabled()


def test_la_ruta_lleva_a_matematicas():
    from academic_core.ui import routes
    r = routes.resolve("math")
    assert r.id == "learn/math" and r.target == "math" and r.label == "Matemáticas"
