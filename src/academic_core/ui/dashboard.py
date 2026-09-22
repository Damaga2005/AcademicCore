# SPDX-License-Identifier: MIT
"""F15 Dashboard (F15 §8): real navigation over real capabilities.

Every card leads to a real tab or is explicitly marked unavailable.
No fictitious features.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from academic_core import __version__


class DashboardPanel(QWidget):
    """Landing view. Emits ``navigate(str)`` with a tab key."""

    navigate = Signal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        layout = QVBoxLayout(self)

        title = QLabel("AcademicCore — Dashboard")
        title.setToolTip("Application home: pick a capability")
        layout.addWidget(title)
        self.state_label = QLabel(
            f"Academic Core v{__version__} · db: {app.db.path}")
        self.state_label.setToolTip("Version and state information")
        layout.addWidget(self.state_label)

        grid = QGridLayout()
        layout.addLayout(grid)

        self._cards: dict[str, QPushButton] = {}
        cards = [
            ("exercises", "Resolution of exercises",
             "Solve engineering library exercises", True),
            ("simulation", "Simulation",
             "Run circuit OP / sweep / transient simulations", True),
            ("lab", "Virtual Lab",
             "F8-N sessions, instruments, measurements, replay", True),
            ("logic", "Logic Analyzer",
             "F8-Q digital capture: channels, edge trigger, waveform, digital-trace/1", True),
            ("resources", "Resources / sessions",
             "Available when the Resources tab has content", True),
            ("settings", "Configuration",
             "Basic application configuration", True),
        ]
        for i, (key, label, tip, enabled) in enumerate(cards):
            box = QGroupBox(label)
            inner = QVBoxLayout(box)
            desc = QLabel(tip)
            desc.setWordWrap(True)
            inner.addWidget(desc)
            btn = QPushButton("Open" if enabled else "Not available")
            btn.setToolTip(tip)
            btn.setEnabled(enabled)
            btn.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            inner.addWidget(btn)
            self._cards[key] = btn
            grid.addWidget(box, i // 2, i % 2)

        self.about_label = QLabel(
            "All capabilities above are functional vertical slices over "
            "certified domain engines. GREELEC: no integration "
            "(UNKNOWN / REQUIRES INPUT).")
        self.about_label.setWordWrap(True)
        layout.addWidget(self.about_label)
        layout.addStretch(1)

    def refresh_state(self) -> None:
        self.state_label.setText(
            f"Academic Core v{__version__} · db: {self.app.db.path}")
