# SPDX-License-Identifier: MIT
"""Product shell widgets (UX IA 2026 §4): nav rail, top bar, section bar.

Presentation only: they emit route ids and never touch services. The main
window owns routing and maps route targets onto the pinned pages.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from academic_core.ui import motion
from academic_core.ui.routes import AREAS, area_default, area_label

RAIL_EXPANDED, RAIL_COLLAPSED = 216, 64
ICON_PX = 20

_AREA_ICON = {"home": "home", "learn": "book", "practice": "check",
              "engineering": "wave", "settings": "sliders"}


def _path_for(name: str) -> QPainterPath:
    """Line icons on a 20 px grid (1.6 px strokes)."""
    p = QPainterPath()
    if name == "home":
        p.moveTo(3, 10); p.lineTo(10, 3.5); p.lineTo(17, 10)
        p.moveTo(5, 8.5); p.lineTo(5, 16.5); p.lineTo(15, 16.5); p.lineTo(15, 8.5)
        p.moveTo(8.5, 16.5); p.lineTo(8.5, 12); p.lineTo(11.5, 12); p.lineTo(11.5, 16.5)
    elif name == "book":
        p.moveTo(10, 5); p.lineTo(10, 16)
        p.moveTo(10, 5); p.cubicTo(8, 3.5, 5, 3.5, 3, 4.5); p.lineTo(3, 15.5)
        p.cubicTo(5, 14.5, 8, 14.5, 10, 16)
        p.moveTo(10, 5); p.cubicTo(12, 3.5, 15, 3.5, 17, 4.5); p.lineTo(17, 15.5)
        p.cubicTo(15, 14.5, 12, 14.5, 10, 16)
    elif name == "check":
        p.addEllipse(QRectF(3, 3, 14, 14))
        p.moveTo(6.8, 10.3); p.lineTo(9, 12.5); p.lineTo(13.3, 7.8)
    elif name == "wave":
        p.moveTo(2.5, 10); p.cubicTo(4.5, 3.5, 7, 3.5, 10, 10)
        p.cubicTo(13, 16.5, 15.5, 16.5, 17.5, 10)
    elif name == "sliders":
        for y, x in ((5, 7), (10, 13), (15, 9)):
            p.moveTo(3, y); p.lineTo(17, y)
            p.addEllipse(QPointF(x, y), 2, 2)
    elif name == "search":
        p.addEllipse(QRectF(3.5, 3.5, 9, 9)); p.moveTo(11.5, 11.5); p.lineTo(16.5, 16.5)
    elif name == "chevron-left":
        p.moveTo(12, 5); p.lineTo(7, 10); p.lineTo(12, 15)
    elif name == "chevron-right":
        p.moveTo(8, 5); p.lineTo(13, 10); p.lineTo(8, 15)
    return p


def make_icon(name: str, normal: str, active: str | None = None) -> QIcon:
    """Icon drawn from ``name``; ``active`` colours the checked state."""
    icon = QIcon()
    for color, state in ((normal, QIcon.State.Off), (active or normal, QIcon.State.On)):
        scale = 2
        pm = QPixmap(ICON_PX * scale, ICON_PX * scale)
        pm.setDevicePixelRatio(scale)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(_path_for(name))
        painter.end()
        icon.addPixmap(pm, QIcon.Mode.Normal, state)
    return icon


class NavRail(QFrame):
    """Primary navigation: five areas, Settings anchored at the bottom."""

    route_requested = Signal(str)
    collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRail")
        self.setAccessibleName("Primary navigation")
        self._collapsed = False
        self._anim: QVariantAnimation | None = None
        self.setFixedWidth(RAIL_EXPANDED)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)
        self.brand = QLabel("AcademicCore")
        self.brand.setObjectName("RailBrand")
        layout.addWidget(self.brand)
        layout.addSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        for i, (area, label) in enumerate(AREAS, start=1):
            btn = QToolButton()
            btn.setProperty("role", "nav")
            btn.setText(label)
            btn.setCheckable(True)
            btn.setAccessibleName(label)
            btn.setToolTip(f"{label}  (Ctrl+{i})")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIconSize(QSize(ICON_PX, ICON_PX))
            btn.setSizePolicy(btn.sizePolicy().horizontalPolicy(), btn.sizePolicy().verticalPolicy())
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda _c=False, a=area: self.route_requested.emit(a))
            self._group.addButton(btn)
            self.buttons[area] = btn
            if area == "settings":
                layout.addStretch(1)
            layout.addWidget(btn)
        self.toggle = QToolButton()
        self.toggle.setProperty("role", "nav")
        self.toggle.setAccessibleName("Collapse navigation")
        self.toggle.setToolTip("Collapse navigation")
        self.toggle.setIconSize(QSize(ICON_PX, ICON_PX))
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setText("Collapse")
        self.toggle.setMinimumHeight(40)
        self.toggle.clicked.connect(lambda _c=False: self.set_collapsed(not self._collapsed))
        layout.addWidget(self.toggle)
        for btn in self.buttons.values():
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.refresh_icons(None)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_area(self, area: str) -> None:
        btn = self.buttons.get(area)
        if btn is not None:
            btn.setChecked(True)

    def refresh_icons(self, tokens) -> None:
        from academic_core.ui.theme import LIGHT
        tokens = tokens or LIGHT
        normal, active = tokens.secondary, tokens.accent_text
        for area, btn in self.buttons.items():
            btn.setIcon(make_icon(_AREA_ICON[area], normal, active))
        self.toggle.setIcon(make_icon("chevron-right" if self._collapsed else "chevron-left", normal))

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        if collapsed == self._collapsed and self.width() == (RAIL_COLLAPSED if collapsed else RAIL_EXPANDED):
            return
        self._collapsed = collapsed
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed
                 else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for btn in (*self.buttons.values(), self.toggle):
            btn.setToolButtonStyle(style)
        self.brand.setVisible(not collapsed)
        self.toggle.setToolTip("Expand navigation" if collapsed else "Collapse navigation")
        self.toggle.setAccessibleName(self.toggle.toolTip())
        self.toggle.setIcon(make_icon(
            "chevron-right" if collapsed else "chevron-left",
            self.toggle.palette().buttonText().color().name()))
        target = RAIL_COLLAPSED if collapsed else RAIL_EXPANDED
        ms = motion.duration(motion.SLOW) if animate else 0
        if self._anim is not None:
            self._anim.stop()
        if ms == 0:
            self.setFixedWidth(target)
        else:
            self._anim = QVariantAnimation(self)
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target)
            self._anim.setDuration(ms)
            from PySide6.QtCore import QEasingCurve
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.valueChanged.connect(lambda v: self.setFixedWidth(int(v)))
            self._anim.start()
        self.collapsed_changed.emit(collapsed)


class SectionBar(QFrame):
    """Contextual navigation: the sections of the current area."""

    section_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SectionBar")
        self.setAccessibleName("Sections")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(24, 8, 24, 0)
        self._layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        self._area: str | None = None

    def set_sections(self, area: str, routes, current: str) -> None:
        if area != self._area:
            for btn in self.buttons.values():
                self._group.removeButton(btn)
                btn.hide()
                btn.setParent(None)
                btn.deleteLater()
            self.buttons.clear()
            while self._layout.count():
                self._layout.takeAt(0)
            for r in routes:
                btn = QPushButton(r.label)
                btn.setProperty("role", "section")
                btn.setCheckable(True)
                btn.clicked.connect(lambda _c=False, rid=r.id: self.section_selected.emit(rid))
                self._group.addButton(btn)
                self.buttons[r.id] = btn
                self._layout.addWidget(btn)
            self._layout.addStretch(1)
            self._area = area
        if current in self.buttons:
            self.buttons[current].setChecked(True)
        else:
            checked = self._group.checkedButton()
            if checked is not None:
                self._group.setExclusive(False)
                checked.setChecked(False)
                self._group.setExclusive(True)
        self.setVisible(len(self.buttons) > 1)


class TopBar(QFrame):
    """Breadcrumbs, subject context chip and the search entry."""

    crumb_clicked = Signal(str)
    context_clicked = Signal()
    search_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)
        layout.setSpacing(8)
        self._crumbs = QHBoxLayout()
        self._crumbs.setSpacing(2)
        layout.addLayout(self._crumbs)
        layout.addStretch(1)
        self.context_chip = QPushButton("No subject")
        self.context_chip.setObjectName("ContextChip")
        self.context_chip.setAccessibleName("Active subject")
        self.context_chip.setToolTip("Active subject: click to choose in Learn")
        self.context_chip.clicked.connect(self.context_clicked)
        layout.addWidget(self.context_chip)
        self.search_button = QPushButton("Search   Ctrl+K")
        self.search_button.setObjectName("SearchButton")
        self.search_button.setAccessibleName("Search and commands")
        self.search_button.setToolTip("Search and go to… (Ctrl+K)")
        self.search_button.clicked.connect(self.search_clicked)
        layout.addWidget(self.search_button)
        self.crumb_texts: list[str] = []

    def set_crumbs(self, trail) -> None:
        while self._crumbs.count():
            item = self._crumbs.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.crumb_texts = [text for text, _ in trail]
        for i, (text, route_id) in enumerate(trail):
            last = i == len(trail) - 1
            if route_id is None or last:
                w: QWidget = QLabel(text)
                w.setProperty("role", "crumb-current")
                if last:
                    w.setAccessibleName(f"Current: {text}")
            else:
                w = QPushButton(text)
                w.setProperty("role", "crumb")
                w.setFlat(True)
                w.clicked.connect(lambda _c=False, rid=route_id: self.crumb_clicked.emit(rid))
            self._crumbs.addWidget(w)
            if not last:
                sep = QLabel("›")
                sep.setProperty("role", "crumb-sep")
                self._crumbs.addWidget(sep)

    def set_context(self, text: str) -> None:
        self.context_chip.setText(text or "No subject")


__all__ = ["NavRail", "SectionBar", "TopBar", "make_icon", "area_default", "area_label"]
