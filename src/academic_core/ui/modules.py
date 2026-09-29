# SPDX-License-Identifier: MIT
"""Engineering module index: groups real labs, never invents capabilities.

Modules and entries come from certified services:
- Digital Logic <- DigitalAnalysisService.demos()
- Electronics <- ExerciseService.library_keys()
- Aerospace <- orbital central bodies (F16)

The dialog navigates to the owning tab; entries are display only.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QListWidget, QVBoxLayout


def module_index(core) -> list[dict]:
    """Real modules with their real entries."""
    from academic_core.domain.engineering.orbital.bodies import EARTH
    return [
        {"id": "digital-logic", "title": "Digital Logic",
         "tab": "logic", "entries": [d.key for d in core.digital.demos()]},
        {"id": "electronics", "title": "Electronics",
         "tab": "exercises", "entries": list(core.exercises.library_keys())},
        {"id": "aerospace", "title": "Aerospace",
         "tab": "aerospace", "entries": [EARTH.name]},
    ]


class ModulesDialog(QDialog):
    """Index of engineering modules (Go > Engineering > Modules)."""

    def __init__(self, core, navigate, parent=None):
        super().__init__(parent)
        self._navigate = navigate
        self.setWindowTitle("Engineering modules")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        self.entry_list = QListWidget()
        for mod in module_index(core):
            self.entry_list.addItem(f"{mod['title']} ({len(mod['entries'])} entries)")
        layout.addWidget(self.entry_list)
        self.entry_list.itemDoubleClicked.connect(lambda _i: self.open_current())

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
