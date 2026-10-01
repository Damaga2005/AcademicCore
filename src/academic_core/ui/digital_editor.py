# SPDX-License-Identifier: MIT
"""Visual editor for digital circuits: gates, inputs and wires on a grid.

Pure view over ``DigitalDesign`` (application layer): every gesture is one
design operation, errors come back as ``ValidationError`` and are shown in
the hint line. No solver, no engine call.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from academic_core.application.digital_design import GATES, INPUT, DigitalDesign
from academic_core.errors import ValidationError
from academic_core.ui.theme import current_tokens

CELL = 20
TOOLS = (("select", "Mover"), (INPUT, "Entrada"), *((g, g) for g in GATES), ("wire", "Cable"), ("delete", "Borrar"))
HINTS = {
    "select": "Arrastra para mover. Doble clic: editar la entrada (estímulo) o el número de pines de una puerta.",
    INPUT: "Clic en el lienzo para colocar una entrada.",
    "wire": "Clic en una entrada o puerta (su salida) y luego en un pin de una puerta.",
    "delete": "Clic en un elemento o sobre un cable para borrarlo.",
}
INVERTED = {"NOT", "NAND", "NOR", "XNOR"}
SYMBOL = {"NOT": "1", "AND": "&", "NAND": "&", "OR": "≥1", "NOR": "≥1", "XOR": "=1", "XNOR": "=1"}


def size(el: dict) -> tuple[int, int]:
    if el["type"] == INPUT:
        return 3 * CELL, 2 * CELL
    return 4 * CELL, (el["n"] + 1) * CELL


def out_pos(el: dict) -> QPointF:
    w, h = size(el)
    return QPointF(el["x"] * CELL + w, el["y"] * CELL + h / 2)


def pin_pos(el: dict, pin: int) -> QPointF:
    return QPointF(el["x"] * CELL, el["y"] * CELL + (pin + 1) * CELL)


class DigitalEditorView(QWidget):
    changed = Signal()
    hint = Signal(str)
    tool_changed = Signal(str)

    def __init__(self, design: DigitalDesign | None = None, parent=None):
        super().__init__(parent)
        self.design = design or DigitalDesign()
        self.tool = "select"
        self._src: str | None = None  # wire in progress
        self._drag: tuple[str, QPointF] | None = None
        self.setMinimumSize(420, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName("Editor de circuito digital")
        self.setToolTip("Lienzo del circuito digital")

    # -- state -------------------------------------------------------------
    def set_design(self, design: DigitalDesign) -> None:
        self.design, self._src, self._drag = design, None, None
        self.changed.emit()
        self.update()

    def set_tool(self, tool: str) -> None:
        self.tool, self._src = tool, None
        self.hint.emit(HINTS.get(tool, "Clic en el lienzo para colocar la puerta."))
        self.tool_changed.emit(tool)
        self.update()

    def _do(self, fn, *args, **kw):
        try:
            result = fn(*args, **kw)
        except ValidationError as exc:
            self.hint.emit(str(exc).removeprefix("INVALID_DESIGN: "))
            return None
        self.changed.emit()
        self.update()
        return result if result is not None else True

    # -- gestures (also callable from tests) ---------------------------------
    def place(self, kind: str, gx: int, gy: int):
        gx, gy = max(0, gx), max(0, gy)
        return self._do(self.design.add_input if kind == INPUT else self.design.add_gate,
                        *(() if kind == INPUT else (kind,)), gx, gy)

    def wire(self, src: str, dst: str, pin: int):
        return self._do(self.design.connect, src, dst, pin)

    # -- hit testing ---------------------------------------------------------
    def element_at(self, p: QPointF) -> str | None:
        for eid, el in reversed(list(self.design.elements.items())):
            w, h = size(el)
            if QRectF(el["x"] * CELL, el["y"] * CELL, w, h).contains(p):
                return eid
        return None

    def pin_at(self, p: QPointF) -> tuple[str, int] | None:
        for eid, el in self.design.elements.items():
            if el["type"] == INPUT:
                continue
            for pin in range(el["n"]):
                q = pin_pos(el, pin)
                if abs(q.x() - p.x()) <= CELL * 0.75 and abs(q.y() - p.y()) <= CELL / 2:
                    return eid, pin
        return None

    def wire_at(self, p: QPointF) -> tuple[str, int] | None:
        for s, d, pin in self.design.wires:
            a, b = out_pos(self.design.elements[s]), pin_pos(self.design.elements[d], pin)
            if QRectF(min(a.x(), b.x()) - 4, min(a.y(), b.y()) - 4, abs(a.x() - b.x()) + 8,
                      abs(a.y() - b.y()) + 8).contains(p) and self._near_path(a, b, p):
                return d, pin
        return None

    @staticmethod
    def _near_path(a: QPointF, b: QPointF, p: QPointF) -> bool:
        mx = (a.x() + b.x()) / 2
        for (x1, y1), (x2, y2) in (((a.x(), a.y()), (mx, a.y())), ((mx, a.y()), (mx, b.y())), ((mx, b.y()), (b.x(), b.y()))):
            if min(x1, x2) - 5 <= p.x() <= max(x1, x2) + 5 and min(y1, y2) - 5 <= p.y() <= max(y1, y2) + 5:
                return True
        return False

    # -- mouse ---------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802 — Qt override
        p = e.position()
        gx, gy = round(p.x() / CELL), round(p.y() / CELL)
        if self.tool in (INPUT, *GATES):
            self.place(self.tool, gx - 2, gy - 1)
        elif self.tool == "select":
            eid = self.element_at(p)
            if eid:
                el = self.design.elements[eid]
                self._drag = (eid, QPointF(p.x() - el["x"] * CELL, p.y() - el["y"] * CELL))
        elif self.tool == "wire":
            pin = self.pin_at(p)
            if self._src and pin:
                self.wire(self._src, *pin)
                self._src = None
                self.hint.emit(HINTS["wire"])
            elif (eid := self.element_at(p)) and not pin:
                self._src = eid
                self.hint.emit(f"Origen: {eid}. Ahora clic en un pin de una puerta.")
            self.update()
        elif self.tool == "delete":
            if (eid := self.element_at(p)):
                self._do(self.design.delete, eid)
            elif (w := self.wire_at(p)):
                self._do(self.design.disconnect, *w)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag:
            eid, off = self._drag
            p = e.position()
            self.design.move(eid, max(0, round((p.x() - off.x()) / CELL)), max(0, round((p.y() - off.y()) / CELL)))
            self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag:
            self._drag = None
            self.changed.emit()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        if self.tool != "select" or not (eid := self.element_at(e.position())):
            return
        el = self.design.elements[eid]
        if el["type"] == INPUT:
            self.edit_input(eid)
        else:
            n, ok = QInputDialog.getInt(self, "Pines de entrada", f"Entradas de {eid}", el["n"], 1, 8)
            if ok:
                self._do(self.design.set_arity, eid, n)

    def edit_input(self, eid: str) -> None:
        from academic_core.ui.dialogs import prompt_form
        el = self.design.elements[eid]
        modes = [("Constante", "const"), ("Alternante (toggle)", "toggle"), ("Patrón", "pattern")]
        states = [("BAJO", "LOW"), ("ALTO", "HIGH")]
        got = prompt_form(self, f"Entrada {eid}", [
            ("mode", "Tipo de señal", modes, "combo"),
            ("initial", "Valor si es constante", states, "combo"),
            ("first", "Primer flanco (alternante)", states, "combo"),
            ("start", "Inicio (s)", el["start"], "text"),
            ("period", "Periodo (s, alternante)", el["period"], "text"),
            ("count", "Nº de flancos (alternante)", el["count"], "int"),
            ("step", "Paso (s, patrón)", el["step"], "text"),
            ("states", "Patrón H/L", el["states"], "text"),
        ], context="Cómo cambia esta entrada durante la simulación.", primary="Aplicar")
        if got:
            self._do(self.design.set_stimulus, eid, **got)

    # -- painting --------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.base())
        p.setPen(QPen(pal.mid().color(), 1))
        for x in range(0, self.width(), CELL * 2):
            for y in range(0, self.height(), CELL * 2):
                p.drawPoint(x, y)
        ink, accent = pal.text().color(), pal.highlight().color()
        els = self.design.elements
        p.setPen(QPen(ink, 1.6))
        for s, d, pin in self.design.wires:
            a, b = out_pos(els[s]), pin_pos(els[d], pin)
            mx = (a.x() + b.x()) / 2
            path = QPainterPath(a)
            path.lineTo(mx, a.y())
            path.lineTo(mx, b.y())
            path.lineTo(b)
            p.drawPath(path)
        for eid, el in els.items():
            w, h = size(el)
            r = QRectF(el["x"] * CELL, el["y"] * CELL, w, h)
            selected = eid == self._src
            p.setPen(QPen(accent if selected else ink, 2 if selected else 1.4))
            p.setBrush(pal.window())
            if el["type"] == INPUT:
                p.drawRoundedRect(r, 4, 4)
                label = {"const": "cte " + ("1" if el["initial"] == "HIGH" else "0"),
                         "toggle": "∿", "pattern": el["states"][:6]}[el["mode"]]
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{eid}\n{label}")
            else:
                p.drawRect(r)
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{SYMBOL[el['type']]}\n{eid}")
                for pin in range(el["n"]):
                    q = pin_pos(el, pin)
                    p.drawLine(QPointF(q.x() - 6, q.y()), q)
                    if self.design.source_of(eid, pin) is None:
                        p.setPen(QPen(QColor(current_tokens().error_ink), 1.6))
                        p.drawEllipse(QPointF(q.x() - 8, q.y()), 3, 3)
                        p.setPen(QPen(ink, 1.4))
            o = out_pos(el)
            if el["type"] in INVERTED:
                p.drawEllipse(QPointF(o.x() + 4, o.y()), 4, 4)
                o = QPointF(o.x() + 8, o.y())
            p.drawLine(QPointF(o.x() - (8 if el["type"] in INVERTED else 0), o.y()), QPointF(o.x() + 6, o.y()))
        p.end()


class DigitalEditorPage(QWidget):
    """Tool palette + canvas + hint line."""

    applied = Signal(str)  # design registered in the service; payload = channel-source key

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.buttons: dict[str, QPushButton] = {}
        self.canvas = DigitalEditorView()
        for tool, label in TOOLS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setAccessibleName(f"Herramienta {label}")
            b.clicked.connect(lambda _=False, t=tool: self.canvas.set_tool(t))
            bar.addWidget(b)
            self.buttons[tool] = b
        bar.addStretch(1)
        self.btn_use = QPushButton("&Usar en el analizador")
        self.btn_use.setProperty("class", "primary")
        self.btn_use.setToolTip("Valida el circuito y lo añade a la lista de circuitos del analizador")
        self.btn_save = QPushButton("Guardar…")
        self.btn_load = QPushButton("Abrir…")
        for b in (self.btn_save, self.btn_load, self.btn_use):
            bar.addWidget(b)
        self.hint = QLabel("")
        self.hint.setObjectName("CardStatus")
        self.hint.setWordWrap(True)
        root.addLayout(bar)
        root.addWidget(self.canvas, 1)
        root.addWidget(self.hint)
        self.canvas.hint.connect(self.hint.setText)
        self.canvas.tool_changed.connect(self._sync)
        self.btn_use.clicked.connect(self.apply)
        self.btn_save.clicked.connect(self._save)
        self.btn_load.clicked.connect(self._load)
        self.canvas.set_tool("select")

    def _sync(self, tool: str) -> None:
        for t, b in self.buttons.items():
            b.setChecked(t == tool)

    def apply(self) -> str | None:
        try:
            key = self.service.register_design(self.canvas.design)
        except ValidationError as exc:
            self.hint.setText(str(exc).removeprefix("INVALID_DESIGN: "))
            return None
        self.hint.setText("Circuito listo: elígelo en «Circuito» y pulsa Capturar.")
        self.applied.emit(key)
        return key

    def _save(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Guardar diseño", f"{self.canvas.design.name}.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.canvas.design.to_json())

    def _load(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Abrir diseño", "", "JSON (*.json)")
        if path:
            try:
                with open(path, "rb") as fh:
                    self.canvas.set_design(DigitalDesign.from_json(fh.read(2_000_000)))
            except (ValidationError, OSError) as exc:
                self.hint.setText(str(exc).removeprefix("INVALID_DESIGN: "))
