# SPDX-License-Identifier: MIT
"""Engineering module index: groups real labs, never invents capabilities.

Modules and entries come from certified services:
- Digital Logic <- DigitalAnalysisService.demos()
- Electronics <- ExerciseService.library_keys()
- Aerospace <- orbital central bodies (F16)

The dialog navigates to the owning tab; entries are display only.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout


def module_index(core) -> list[dict]:
    """Real modules with their real entries."""
    from academic_core.domain.engineering.orbital.bodies import EARTH
    return [
        {"id": "digital-logic", "title": "Lógica digital",
         "tab": "logic", "entries": [d.key for d in core.digital.demos()]},
        {"id": "electronics", "title": "Electrónica",
         "tab": "exercises", "entries": list(core.exercises.library_keys())},
        {"id": "aerospace", "title": "Aeroespacial",
         "tab": "aerospace", "entries": [EARTH.name]},
    ]


class ModulesDialog(QDialog):
    """Index of engineering modules (Go > Engineering > Modules)."""

    def __init__(self, core, navigate, parent=None):
        super().__init__(parent)
        self._navigate = navigate
        self.setWindowTitle("Módulos de ingeniería")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("Módulos de ingeniería")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        context = QLabel("Elige un módulo para abrir su espacio de trabajo. Doble clic o Intro.")
        context.setObjectName("DialogContext")
        layout.addWidget(context)
        self.entry_list = QListWidget()
        self.entry_list.setAccessibleName("Módulos")
        for mod in module_index(core):
            self.entry_list.addItem(f"{mod['title']} ({len(mod['entries'])} entradas)")
        self.entry_list.setCurrentRow(0)
        layout.addWidget(self.entry_list)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        self.btn_open = QPushButton("Abrir")
        self.btn_open.setProperty("class", "primary")
        self.btn_open.setDefault(True)
        self.btn_open.clicked.connect(self.open_current)
        row.addWidget(close)
        row.addWidget(self.btn_open)
        layout.addLayout(row)
        self.entry_list.itemDoubleClicked.connect(lambda _i: self.open_current())
        self.entry_list.itemActivated.connect(lambda _i: self.open_current())
        self.entry_list.setFocus()

    def showEvent(self, event) -> None:
        from academic_core.ui.motion import pop_in
        super().showEvent(event)
        pop_in(self)

    def open_current(self) -> None:
        row = self.entry_list.currentRow()
        if row < 0:
            return
        self.navigate(["digital-logic", "electronics", "aerospace"][row])

    def navigate(self, module_id: str) -> None:
        tabs = {"digital-logic": "logic", "electronics": "exercises", "aerospace": "aerospace"}
        self._navigate(tabs[module_id])
        self.accept()
