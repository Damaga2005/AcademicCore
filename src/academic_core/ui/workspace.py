# SPDX-License-Identifier: MIT
"""Engineering workspace kit (DESIGN-SYSTEM-2026 §4.4, §5).

Context -> Inputs -> Tools -> Visualization -> Results share one
vocabulary: a ``Panel`` per zone, ``Metric`` tiles for measured values
with their units, ``KeyValueList`` for facts. Presentation only.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget,
)


def tabular(label: QLabel) -> QLabel:
    """Tabular figures where Qt supports the OpenType feature (>= 6.7)."""
    try:
        font = label.font()
        font.setFeature(QFont.Tag("tnum"), 1)
        label.setFont(font)
    except Exception:
        pass
    return label


class Panel(QFrame):
    """A titled zone of a workspace. Add content through ``body``/``add``."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PanelTitle")
        self.title_label.setAccessibleName(title)
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.actions = QHBoxLayout()  # controls that belong to the panel header
        self.actions.setSpacing(6)
        head.addLayout(self.actions)
        outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)
        self.setAccessibleName(title)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget


class Metric(QFrame):
    """One measured value with its unit: label above, figure + unit below."""

    EMPTY = "—"

    def __init__(self, label: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Metric")
        self._label_text, self._unit = label, unit
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(2)
        self.label = QLabel(label)
        self.label.setProperty("role", "metric-label")
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.value = tabular(QLabel(self.EMPTY))
        self.value.setProperty("role", "metric-value")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.unit = QLabel(unit)
        self.unit.setProperty("role", "metric-unit")
        row.addWidget(self.value)
        row.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        lay.addLayout(row)
        self._sync_name()

    def set_value(self, text: str, unit: str | None = None) -> None:
        self.value.setText(text)
        if unit is not None:
            self._unit = unit
            self.unit.setText(unit)
        self._sync_name()

    def clear(self) -> None:
        self.set_value(self.EMPTY)

    def text(self) -> str:
        return self.value.text()

    def _sync_name(self) -> None:
        shown = self.value.text()
        self.setAccessibleName(f"{self._label_text}: {shown} {self._unit}".strip()
                               if shown != self.EMPTY else f"{self._label_text}: no value")


class KeyValueList(QWidget):
    """Facts as aligned ``key  value`` rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(6)
        self._grid.setColumnStretch(1, 1)
        self.rows: list[tuple[str, str]] = []

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.rows = list(rows)
        for i, (key, value) in enumerate(rows):
            k = QLabel(key)
            k.setProperty("role", "key")
            v = tabular(QLabel(value))
            v.setProperty("role", "value")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(k, i, 0, Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(v, i, 1)


class EmptyState(QFrame):
    """Honest empty state: what is missing and the one next step."""

    def __init__(self, title: str, text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyState")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setWordWrap(True)
        self.text = QLabel(text)
        self.text.setObjectName("CardStatus")
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # Word-wrapped text needs its height reserved: a scroll area or panel does not ask for
        # height-for-width, and the last line would be cut (audit F-05).
        self.text.setMinimumHeight(self.text.fontMetrics().height() * 3)
        lay.addWidget(self.title)
        lay.addWidget(self.text)

    def set(self, title: str, text: str = "") -> None:
        self.title.setText(title)
        self.text.setText(text)


class HintList(QListWidget):
    """A list that says what it is for while it is empty, instead of a blank box (audit F-09)."""

    def __init__(self, hint: str = "", parent=None):
        super().__init__(parent)
        self._hint = hint

    def set_hint(self, hint: str) -> None:
        self._hint = hint
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().paintEvent(event)
        if self.count() == 0 and self._hint:
            from academic_core.ui.theme import current_tokens
            p = QPainter(self.viewport())
            p.setPen(QColor(current_tokens().secondary))
            p.drawText(self.viewport().rect().adjusted(12, 12, -12, -12),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), self._hint)
            p.end()


class Notice(QLabel):
    """One-line status under a toolbar; takes no room while it is empty (audit F-13)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self.setObjectName("CardStatus")
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 — Qt override
        super().setText(text)
        self.setVisible(bool(text))
