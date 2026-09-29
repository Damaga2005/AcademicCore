# SPDX-License-Identifier: MIT
"""Command palette (Ctrl+K): "Go to" routes + content search.

Content matching stays in application.search (UnifiedSearchService): no
second search engine. "Go to" rows come from the route table. Up/Down move
the selection from the search box; Enter opens the *selected* row.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout


class SearchDialog(QDialog):
    """Ctrl+K palette: type to search or jump, Enter opens the selection."""

    def __init__(self, core, parent=None, goto=None):
        super().__init__(parent)
        self.core = core
        self._goto = list(goto or [])  # [(label, route_id)]
        self.setWindowTitle("Search AcademicCore")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search or go to — subjects, tasks, notes, documents, sections…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setAccessibleName("Search or go to")
        layout.addWidget(self.search_box)
        self.result_list = QListWidget()
        self.result_list.setObjectName("PaletteList")
        self.result_list.setAccessibleName("Results")
        layout.addWidget(self.result_list)
        hint = QLabel("↑↓ select · Enter opens · Esc closes")
        hint.setObjectName("Caption")
        layout.addWidget(hint)
        self.search_box.installEventFilter(self)
        self.search_box.textChanged.connect(lambda _t: self.refresh())
        self.search_box.returnPressed.connect(self.accept)
        self.result_list.itemActivated.connect(lambda _i: self.accept())
        self._hits: list = []
        self._rows: list[tuple] = []  # ("route", route_id) | ("hit", hit)
        self.search_box.setFocus()
        self.refresh()

    def showEvent(self, event) -> None:
        from academic_core.ui.motion import pop_in
        super().showEvent(event)
        pop_in(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if obj is self.search_box and event.type() == QEvent.Type.KeyPress:
            step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1}.get(event.key())
            if step and self.result_list.count():
                row = self.result_list.currentRow() + step
                self.result_list.setCurrentRow(max(0, min(row, self.result_list.count() - 1)))
                return True
        return super().eventFilter(obj, event)

    def run_search(self, query: str) -> list:
        """Query the certified service (min 2 chars, enforced there)."""
        self._hits = self.core.unified_search.search(query, limit=30)
        return self._hits

    def refresh(self) -> None:
        text = self.search_box.text().strip()
        self.result_list.clear()
        self._rows = []
        needle = text.lower()
        for label, route_id in self._goto:
            if not needle or needle in label.lower():
                self._rows.append(("route", route_id))
                self.result_list.addItem(label)
        for hit in self.run_search(self.search_box.text()):
            title = hit.title if len(hit.title) <= 90 else hit.title[:87] + "…"
            self._rows.append(("hit", hit))
            self.result_list.addItem(f"{hit.kind}: {title}")
        if self.result_list.count():
            self.result_list.setCurrentRow(0)

    def accept(self) -> None:
        if not self._rows:
            self.refresh()
        super().accept()

    def selection(self):
        """Selected row as ``("route", id)`` or ``("hit", hit)``; None when empty."""
        row = self.result_list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def chosen(self):
        """Selected content hit, else the first hit; None when empty."""
        sel = self.selection()
        if sel is not None and sel[0] == "hit":
            return sel[1]
        return self._hits[0] if self._hits else None
