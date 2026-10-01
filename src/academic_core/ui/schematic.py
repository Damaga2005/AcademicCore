# SPDX-License-Identifier: MIT
"""Schematic editor: a canvas and a palette over one circuit.

The canvas draws and asks; it never decides. Wires are not stored: two pins are joined when they
share a net name, so every connection the student draws is a rename in the netlist and the drawing
is always what the solver will get. Edits leave as signals (``place_requested``, ``changed`` ...);
the panel applies them through ``application.schematic`` and saves.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from academic_core.application import schematic as S

GRID = 20
PIN_HIT = 8
MARGIN = 3  # grid units of breathing room around the drawing


# -- symbols -----------------------------------------------------------------------------------------
def draw_symbol(p: QPainter, ctype: str, u: float, polarity: str = "") -> None:
    """Draw ``ctype`` centred on the origin; ``u`` is one grid unit in pixels. Pins sit at +-2u."""
    t = ctype.upper()
    line = p.drawLine

    def seg(x1, y1, x2, y2):
        line(QPointF(x1 * u, y1 * u), QPointF(x2 * u, y2 * u))

    def poly(points):
        p.drawPolyline(QPolygonF([QPointF(x * u, y * u) for x, y in points]))

    def circle(r, cx=0.0, cy=0.0):
        p.drawEllipse(QPointF(cx * u, cy * u), r * u, r * u)

    def arrow(x, y, dx, dy, size=0.22):
        ang = math.atan2(dy, dx)
        tip = QPointF(x * u, y * u)
        pts = [tip] + [QPointF(tip.x() - size * u * math.cos(ang + s * 0.45),
                               tip.y() - size * u * math.sin(ang + s * 0.45)) for s in (-1, 1)]
        p.setBrush(p.pen().color())
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(Qt.BrushStyle.NoBrush)

    p.setBrush(Qt.BrushStyle.NoBrush)
    if t == "R":
        poly([(-2, 0), (-1, 0), (-0.75, -0.4), (-0.25, 0.4), (0.25, -0.4), (0.75, 0.4), (1, 0), (2, 0)])
    elif t == "C":
        seg(-2, 0, -0.25, 0); seg(0.25, 0, 2, 0); seg(-0.25, -0.6, -0.25, 0.6); seg(0.25, -0.6, 0.25, 0.6)
    elif t == "L":
        seg(-2, 0, -1, 0); seg(1, 0, 2, 0)
        for i in range(4):
            p.drawArc(QRectF((-1 + i * 0.5) * u, -0.25 * u, 0.5 * u, 0.5 * u), 0, 180 * 16)
    elif t in "VI":
        seg(0, -2, 0, -1); seg(0, 1, 0, 2); circle(1)
        if t == "V":
            seg(-0.15, -0.55, 0.15, -0.55); seg(0, -0.7, 0, -0.4); seg(-0.15, 0.55, 0.15, 0.55)
        else:
            seg(0, 0.55, 0, -0.45); arrow(0, -0.6, 0, -1)
    elif t == "D":
        seg(-2, 0, -0.5, 0); seg(0.5, 0, 2, 0); seg(0.5, -0.6, 0.5, 0.6)
        p.drawPolygon(QPolygonF([QPointF(-0.5 * u, -0.6 * u), QPointF(-0.5 * u, 0.6 * u), QPointF(0.5 * u, 0)]))
    elif t == "Q":
        seg(-2, 0, -0.4, 0); seg(-0.4, -0.9, -0.4, 0.9)
        poly([(-0.4, -0.45), (1, -1), (1, -2)]); poly([(-0.4, 0.45), (1, 1), (1, 2)])
        circle(1.45, 0.2, 0)
        if str(polarity).upper() == "PNP":
            arrow(0.0, 0.6, -1.4, -0.55)   # emitter arrow points at the base
        else:
            arrow(0.75, 0.9, 1.4, 0.55)    # NPN: away from the base
    elif t in "MJ":
        seg(-2, 0, -0.9, 0)
        seg(-0.9, -0.8, -0.9, 0.8)
        seg(-0.55, -0.85, -0.55, 0.85) if t == "M" else seg(-0.55, -0.85, -0.55, 0.85)
        poly([(-0.55, -0.6), (1, -0.6), (1, -2)]); poly([(-0.55, 0.6), (1, 0.6), (1, 2)])
        if t == "M":
            seg(-0.55, 0, 2, 0)
            arrow(-0.45, 0, 0.6, 0) if "N" in str(polarity).upper() else arrow(1, 0, -0.6, 0)
    elif t in "EGHF":
        seg(0, -2, 0, -1.2); seg(0, 1.2, 0, 2)
        p.drawPolygon(QPolygonF([QPointF(0, -1.2 * u), QPointF(1.2 * u, 0), QPointF(0, 1.2 * u), QPointF(-1.2 * u, 0)]))
        f = QFont(p.font()); f.setPointSizeF(max(u * 0.55, 6)); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(-u, -u * 0.6, 2 * u, 1.2 * u), int(Qt.AlignmentFlag.AlignCenter), t)
    elif t == "O":
        seg(-2, -1, -1.4, -1); seg(-2, 1, -1.4, 1); seg(1.4, 0, 2, 0)
        p.drawPolygon(QPolygonF([QPointF(-1.4 * u, -1.8 * u), QPointF(-1.4 * u, 1.8 * u), QPointF(1.4 * u, 0)]))
        f = QFont(p.font()); f.setPointSizeF(max(u * 0.6, 6)); p.setFont(f)
        p.drawText(QPointF(-1.25 * u, -0.85 * u), "+"); p.drawText(QPointF(-1.25 * u, 1.3 * u), "−")
    elif t == "T":
        seg(-2, -1, -1, -1); seg(-2, 1, -1, 1); seg(1, -1, 2, -1); seg(1, 1, 2, 1)
        for side in (-1, 1):
            path = QPainterPath()
            for i in range(4):
                path.arcMoveTo(QRectF(side * 1.0 * u - 0.25 * u, (-1 + i * 0.5) * u, 0.5 * u, 0.5 * u), 90)
                path.arcTo(QRectF(side * 1.0 * u - 0.25 * u, (-1 + i * 0.5) * u, 0.5 * u, 0.5 * u), 90, -180 * side)
            p.drawPath(path)
        seg(-0.1, -1, -0.1, 1); seg(0.1, -1, 0.1, 1)


def ground_symbol(p: QPainter, u: float) -> None:
    p.drawLine(QPointF(0, 0), QPointF(0, 0.6 * u))
    for i, half in enumerate((0.55, 0.36, 0.17)):
        y = (0.6 + i * 0.2) * u
        p.drawLine(QPointF(-half * u, y), QPointF(half * u, y))


def symbol_icon(ctype: str, colour: QColor, size: int = 34) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(colour, 2.4))
    p.translate(size, size)
    draw_symbol(p, ctype, size / 2.9)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


# -- the canvas -------------------------------------------------------------------------------------
class SchematicView(QWidget):
    """Draws a circuit and turns mouse and keys into edit requests."""

    place_requested = Signal(str, int, int)        # type, grid x, grid y
    moved = Signal(str, int, int)                  # ref, grid x, grid y
    connect_requested = Signal(object, object)     # (ref, pin), (ref, pin)
    ground_requested = Signal(str, str)
    detach_requested = Signal(str, str)
    rotate_requested = Signal(str)
    delete_requested = Signal(str)
    edit_requested = Signal(str)                   # double click: change value / model
    rename_net_requested = Signal(str)             # net name
    tool_changed = Signal(str)
    hint = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.circuit = None
        self.tool = "select"                       # select | wire | ground | place:<type>
        self.layout: dict[str, tuple[int, int, int]] = {}
        self.selected: str | None = None
        self.voltages: dict[str, str] = {}         # net -> "2.5 V", shown after a run
        self._zoom, self._pan = 1.0, QPointF(0, 0)
        self._drag: tuple[str, QPointF, tuple[int, int, int]] | None = None
        self._wire_from: tuple[str, str] | None = None
        self._cursor = QPointF()
        self._hover_pin: tuple[str, str] | None = None
        self._panning: QPointF | None = None
        self._auto_fit = True
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 280)
        self.setAccessibleName("Editor de esquemas")
        self.setAccessibleDescription("Lienzo del esquema. Elige una herramienta en la paleta y haz clic; "
                                      "Supr borra, R gira, Esc vuelve a seleccionar.")

    # -- data ------------------------------------------------------------------------------------
    def set_circuit(self, circuit, fit: bool = True) -> None:
        self.circuit = circuit
        self.layout = S.layout(circuit) if circuit is not None else {}
        if self.selected and (circuit is None or self.selected not in self.layout):
            self.selected = None
        self._wire_from = None
        if fit:
            self._auto_fit = True
            self.fit()
        self.update()

    def set_voltages(self, voltages: dict[str, str]) -> None:
        self.voltages = dict(voltages)
        self.update()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._wire_from = None
        self.setCursor(Qt.CursorShape.ArrowCursor if tool == "select" else Qt.CursorShape.CrossCursor)
        self.tool_changed.emit(tool)
        self.hint.emit({"select": "Clic en un componente: seleccionar. Arrastra para moverlo; arrastra desde un pin para cablear.",
                        "wire": "Cable: clic en un pin y luego en otro para conectarlos.",
                        "ground": "Tierra: clic en un pin para conectarlo al nodo 0."}.get(
                            tool, "Clic en el lienzo para colocar. Esc termina."))
        self.update()

    # -- geometry --------------------------------------------------------------------------------
    @property
    def u(self) -> float:
        return GRID * self._zoom

    def to_px(self, gx: float, gy: float) -> QPointF:
        return QPointF(gx * self.u, gy * self.u) + self._pan

    def to_grid(self, pt: QPointF) -> tuple[int, int]:
        q = pt - self._pan
        return round(q.x() / self.u), round(q.y() / self.u)

    def _pins(self) -> dict[tuple[str, str], tuple[int, int]]:
        out = {}
        if self.circuit is None:
            return out
        for c in self.circuit.components:
            ref = c.ref.upper()
            for pin, pos in S.pin_positions(c, self.layout[ref]).items():
                out[(ref, pin)] = pos
        return out

    def fit(self) -> None:
        pts = list(self._pins().values())
        if not pts:
            self._zoom, self._pan = 1.0, QPointF(self.width() / 2, self.height() / 2)
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w, h = (max(xs) - min(xs) + 2 * MARGIN) * GRID, (max(ys) - min(ys) + 2 * MARGIN) * GRID
        self._zoom = max(0.3, min(1.5, min(self.width() / w, self.height() / h)))
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self._pan = QPointF(self.width() / 2 - cx * self.u, self.height() / 2 - cy * self.u)

    def resizeEvent(self, _e) -> None:  # noqa: N802 - Qt override
        if self.circuit is not None and self._auto_fit:
            self.fit()

    def _pin_at(self, pt: QPointF):
        best, dist = None, PIN_HIT
        for key, (gx, gy) in self._pins().items():
            d = math.hypot(self.to_px(gx, gy).x() - pt.x(), self.to_px(gx, gy).y() - pt.y())
            if d <= dist:
                best, dist = key, d
        return best

    def _body_rect(self, ref: str) -> QRectF:
        comp = next(c for c in self.circuit.components if c.ref.upper() == ref)
        pos = S.pin_positions(comp, self.layout[ref])
        x, y, _ = self.layout[ref]
        xs = [v[0] for v in pos.values()] + [x]
        ys = [v[1] for v in pos.values()] + [y]
        a, b = self.to_px(min(xs), min(ys)), self.to_px(max(xs), max(ys))
        return QRectF(a, b).normalized().adjusted(-6, -6, 6, 6)

    def _component_at(self, pt: QPointF) -> str | None:
        if self.circuit is None:
            return None
        hits = [c.ref.upper() for c in self.circuit.components if self._body_rect(c.ref.upper()).contains(pt)]
        return hits[-1] if hits else None

    # -- painting --------------------------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt override
        from academic_core.ui.theme import current_tokens
        tk = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(tk.card))
        ink, dim, accent = QColor(tk.ink), QColor(tk.secondary), QColor(tk.accent)
        # dot grid
        p.setPen(QPen(QColor(tk.hairline), 1.4))
        step = self.u
        if step >= 8:
            x0 = self._pan.x() % step
            y0 = self._pan.y() % step
            x = x0
            while x < self.width():
                y = y0
                while y < self.height():
                    p.drawPoint(QPointF(x, y))
                    y += step
                x += step
        if self.circuit is None:
            p.setPen(dim)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "Elige un circuito para ver su esquema.")
            p.end()
            return
        if not self.circuit.components:
            p.setPen(dim)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                       "Circuito vacío. Elige un componente en la paleta y haz clic aquí para colocarlo.")
        pins = self._pins()
        nets = S.nets_of(self.circuit)
        label_font = QFont(p.font())
        label_font.setPointSizeF(max(8.0, 9.0 * self._zoom))
        # wires: one elbow chain per net; ground is drawn as symbols instead
        p.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for net, members in nets.items():
            pts = sorted({pins[m] for m in members})
            if net == S.GROUND:
                for gx, gy in pts:
                    p.save(); p.translate(self.to_px(gx, gy)); ground_symbol(p, self.u); p.restore()
                continue
            for a, b in zip(pts, pts[1:]):
                pa, pb = self.to_px(*a), self.to_px(*b)
                mid = (pa.x() + pb.x()) / 2
                p.drawPolyline(QPolygonF([pa, QPointF(mid, pa.y()), QPointF(mid, pb.y()), pb]))
            if len(pts) >= 3:
                p.setBrush(ink)
                for pt in pts:
                    p.drawEllipse(self.to_px(*pt), 3, 3)
                p.setBrush(Qt.BrushStyle.NoBrush)
        # components
        for c in self.circuit.components:
            ref = c.ref.upper()
            x, y, rot = self.layout[ref]
            chosen = ref == self.selected
            p.save()
            p.translate(self.to_px(x, y))
            p.rotate(rot)
            p.setPen(QPen(accent if chosen else ink, 2.4 if chosen else 2))
            draw_symbol(p, c.type, self.u, str((c.parameters or {}).get("polarity", "")))
            p.restore()
            p.setFont(label_font)
            pp = S.pin_positions(c, self.layout[ref]).values()
            vertical = (max(v[1] for v in pp) - min(v[1] for v in pp)) > (max(v[0] for v in pp) - min(v[0] for v in pp))
            centre = self.to_px(x, y)
            ref_at = centre + (QPointF(self.u * 1.5, -self.u * 0.2) if vertical else QPointF(-self.u * 0.6, -self.u * 1.0))
            sub_at = ref_at + (QPointF(0, self.u * 0.8) if vertical else QPointF(0, self.u * 2.4))
            p.setPen(accent if chosen else ink)
            p.drawText(ref_at, ref)
            sub = c.value.compact() if c.value is not None else str((c.parameters or {}).get("polarity", ""))
            if sub:
                p.setPen(dim)
                p.drawText(sub_at, sub)
        # pins and net names
        named_done = set()
        for (ref, pin), (gx, gy) in pins.items():
            comp = next(c for c in self.circuit.components if c.ref.upper() == ref)
            net = comp.pins[pin]
            where = self.to_px(gx, gy)
            wired = len(nets[net]) > 1 or net == S.GROUND
            hot = self._hover_pin == (ref, pin) or self._wire_from == (ref, pin)
            p.setPen(QPen(accent if hot else (ink if wired else QColor(tk.warning_ink)), 1.8))
            p.setBrush(accent if hot else (ink if wired else QColor(tk.card)))
            p.drawEllipse(where, 4 if hot else 3, 4 if hot else 3)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if net not in named_done and net != S.GROUND and not S.is_auto_net(net):
                named_done.add(net)
                p.setFont(label_font)
                p.setPen(accent)
                p.drawText(where + QPointF(-4, -9), net)
                if net in self.voltages:
                    p.setPen(dim)
                    p.drawText(where + QPointF(5, 8 + label_font.pointSizeF()), self.voltages[net])
        # wire being drawn / component about to be placed
        if self._wire_from and self._wire_from in pins:
            p.setPen(QPen(accent, 1.6, Qt.PenStyle.DashLine))
            p.drawLine(self.to_px(*pins[self._wire_from]), self._cursor)
        if self.tool.startswith("place:"):
            gx, gy = self.to_grid(self._cursor)
            p.save()
            p.translate(self.to_px(gx, gy))
            p.setOpacity(0.55)
            p.setPen(QPen(accent, 2))
            draw_symbol(p, self.tool.split(":", 1)[1], self.u)
            p.restore()
        p.end()

    # -- mouse -----------------------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt override
        self.setFocus()
        pt = e.position()
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = pt
            self._auto_fit = False
            return
        if self.circuit is None:
            return
        if e.button() == Qt.MouseButton.RightButton:
            if self.tool != "select":
                self.set_tool("select")
                return
            pin = self._pin_at(pt)
            if pin:
                self.detach_requested.emit(*pin)
            return
        pin = self._pin_at(pt)
        if self.tool == "ground":
            if pin:
                self.ground_requested.emit(*pin)
            return
        if self.tool == "wire":
            if pin and not self._wire_from:
                self._wire_from = pin
            elif pin and self._wire_from and pin != self._wire_from:
                a, self._wire_from = self._wire_from, None
                self.connect_requested.emit(a, pin)
            else:
                self._wire_from = None
            self.update()
            return
        if self.tool.startswith("place:"):
            gx, gy = self.to_grid(pt)
            self.place_requested.emit(self.tool.split(":", 1)[1], gx, gy)
            return
        # select tool: a pin starts a wire, a body selects and may drag
        if pin:
            self._wire_from = pin
            self.update()
            return
        ref = self._component_at(pt)
        self.selected = ref
        if ref:
            self._drag = (ref, pt, self.layout[ref])
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt override
        pt = e.position()
        self._cursor = pt
        if self._panning is not None:
            self._pan += pt - self._panning
            self._panning = pt
        elif self._drag:
            ref, origin, start = self._drag
            dx = round((pt.x() - origin.x()) / self.u)
            dy = round((pt.y() - origin.y()) / self.u)
            self.layout[ref] = (start[0] + dx, start[1] + dy, start[2])
        else:
            self._hover_pin = self._pin_at(pt) if self.circuit is not None else None
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802 - Qt override
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = None
            return
        if self._drag:
            ref, _origin, start = self._drag
            self._drag = None
            if self.layout[ref] != start:
                self.moved.emit(ref, self.layout[ref][0], self.layout[ref][1])
        elif self._wire_from and self.tool == "select":
            target = self._pin_at(e.position())
            a, self._wire_from = self._wire_from, None
            if target and target != a:
                self.connect_requested.emit(a, target)
        self.update()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802 - Qt override
        if self.circuit is None or self.tool != "select":
            return
        pin = self._pin_at(e.position())
        if pin:
            comp = next(c for c in self.circuit.components if c.ref.upper() == pin[0])
            self.rename_net_requested.emit(comp.pins[pin[1]])
            return
        ref = self._component_at(e.position())
        if ref:
            self.edit_requested.emit(ref)

    def wheelEvent(self, e) -> None:  # noqa: N802 - Qt override
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._auto_fit = False
            before = self.to_grid(e.position())
            self._zoom = max(0.4, min(2.5, self._zoom * (1.12 if e.angleDelta().y() > 0 else 1 / 1.12)))
            after = self.to_px(*before)
            self._pan += e.position() - after
            self.update()

    def keyPressEvent(self, e) -> None:  # noqa: N802 - Qt override
        if e.key() == Qt.Key.Key_Escape:
            self._wire_from = None
            self.set_tool("select")
        elif e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected:
            self.delete_requested.emit(self.selected)
        elif e.key() == Qt.Key.Key_R and self.selected:
            self.rotate_requested.emit(self.selected)
        elif e.key() == Qt.Key.Key_W:
            self.set_tool("wire")
        elif e.key() == Qt.Key.Key_G:
            self.set_tool("ground")
        else:
            super().keyPressEvent(e)


# -- the palette --------------------------------------------------------------------------------------
SHORT = {"R": "Resistencia", "C": "Condensador", "L": "Bobina", "V": "Fuente V", "I": "Fuente I",
         "E": "VCVS (E)", "G": "VCCS (G)", "H": "CCVS (H)", "F": "CCCS (F)", "D": "Diodo", "Q": "BJT",
         "M": "MOSFET", "J": "JFET", "O": "Op-amp", "T": "Transformador"}
GROUPS = (("Pasivos", "RCL"), ("Fuentes", "VIEGHF"), ("Semiconductores", "DQMJ"), ("Otros", "OT"))


class SchematicPalette(QScrollArea):
    """Tools on the left of the canvas: select, wire, ground, then every component type."""

    tool_chosen = Signal(str)

    def __init__(self, names: dict[str, str], parent=None):
        super().__init__(parent)
        from academic_core.ui.theme import current_tokens
        ink = QColor(current_tokens().ink)
        self.setWidgetResizable(True)
        self.setFixedWidth(152)
        self.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}

        def add(tool: str, text: str, icon: QIcon | None = None, tip: str = "") -> None:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("role", "section")
            b.setToolTip(tip or text)
            b.setAccessibleName(text)
            if icon:
                b.setIcon(icon)
                b.setIconSize(QSize(30, 30))
            b.setStyleSheet("text-align:left; padding:2px 6px;")
            b.clicked.connect(lambda _c=False, t=tool: self.tool_chosen.emit(t))
            self.group.addButton(b)
            self.buttons[tool] = b
            lay.addWidget(b)

        def heading(text: str) -> None:
            label = QLabel(text)
            label.setProperty("role", "key")
            lay.addSpacing(6)
            lay.addWidget(label)

        heading("Herramientas")
        add("select", "Seleccionar", tip="Seleccionar y mover (Esc)")
        add("wire", "Cable", tip="Conectar dos pines (W)")
        add("ground", "Tierra", tip="Conectar un pin al nodo 0 (G)")
        for title, types in GROUPS:
            heading(title)
            for t in types:
                add(f"place:{t}", SHORT.get(t, t), symbol_icon(t, ink), f"{names.get(t, t)} ({t})")
        lay.addStretch(1)
        self.setWidget(host)
        self.buttons["select"].setChecked(True)

    def sync(self, tool: str) -> None:
        b = self.buttons.get(tool)
        if b:
            b.setChecked(True)


class SchematicPage(QWidget):
    """Palette + canvas + a one-line hint, wired together."""

    def __init__(self, names: dict[str, str], parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        self.palette = SchematicPalette(names)
        self.canvas = SchematicView()
        right = QVBoxLayout()
        right.setSpacing(6)
        self.hint = QLabel("")
        self.hint.setObjectName("CardStatus")
        self.hint.setWordWrap(True)
        right.addWidget(self.canvas, 1)
        right.addWidget(self.hint)
        root.addWidget(self.palette)
        root.addLayout(right, 1)
        self.palette.tool_chosen.connect(self.canvas.set_tool)
        self.canvas.tool_changed.connect(self.palette.sync)
        self.canvas.hint.connect(self.hint.setText)
        self.canvas.set_tool("select")
