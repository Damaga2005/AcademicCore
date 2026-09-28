# SPDX-License-Identifier: MIT
"""Global search dialog (Ctrl+K): thin view over UnifiedSearchService.

No second search engine: all matching lives in application.search.
UI only renders hits and navigates to subject-linked ones.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout


class SearchDialog(QDialog):
    """Ctrl+K palette: type to search, Enter opens the first hit."""

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.setWindowTitle("Search AcademicCore")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search AcademicCore — subjects, tasks, notes, documents…")
        self.search_box.setClearButtonEnabled(True)
        layout.addWidget(self.search_box)
        self.result_list = QListWidget()
        layout.addWidget(self.result_list)
        hint = QLabel("Enter opens · Esc closes")
        hint.setObjectName("Caption")
        layout.addWidget(hint)
        self.search_box.textChanged.connect(lambda _t: self.refresh())
        self.search_box.returnPressed.connect(self.accept)
        self._hits: list = []

    def run_search(self, query: str) -> list:
        """Query the certified service (min 2 chars, enforced there)."""
        self._hits = self.core.unified_search.search(query, limit=30)
        return self._hits

    def refresh(self) -> None:
        self.result_list.clear()
        for hit in self.run_search(self.search_box.text()):
            title = hit.title if len(hit.title) <= 90 else hit.title[:87] + "…"
            self.result_list.addItem(f"{hit.kind}: {title}")

    def accept(self) -> None:
        self.refresh()
        super().accept()

    def chosen(self):
        """First hit (Enter semantics); None when empty."""
        return self._hits[0] if self._hits else None
