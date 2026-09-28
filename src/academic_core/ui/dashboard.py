# SPDX-License-Identifier: MIT
"""F15 Dashboard (F15 §8): real navigation over real capabilities.

Every card leads to a real tab or is explicitly marked unavailable.
No fictitious features. Summaries are live facade state, guarded per
source so one failing query never breaks the home.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from academic_core import __version__


def _safe(fn, fallback: str) -> str:
    try:
        value = fn()
    except Exception:
        return fallback
    return str(value) if value else fallback


class DashboardPanel(QWidget):
    """Landing view. Emits ``navigate(str)`` with a tab key."""

    navigate = Signal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("AcademicCore — Dashboard")
        title.setObjectName("AppTitle")
        title.setToolTip("Application home: pick a capability")
        header.addWidget(title)
        self.state_label = QLabel(
            f"Academic Core v{__version__} · db: {app.db.path}")
        self.state_label.setObjectName("Caption")
        self.state_label.setToolTip("Version and state information")
        header.addWidget(self.state_label)
        self.greeting_label = QLabel("Good morning.")
        self.greeting_label.setObjectName("SectionTitle")
        header.addWidget(self.greeting_label)
        self.greeting_sub = QLabel("Continue where you left off.")
        self.greeting_sub.setObjectName("Caption")
        header.addWidget(self.greeting_sub)
        self.recent_label = QLabel()
        self.recent_label.setObjectName("Caption")
        self.recent_label.setWordWrap(True)
        header.addWidget(self.recent_label)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid, 1)

        self._cards: dict[str, QPushButton] = {}
        self._summaries: dict[str, QLabel] = {}
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
            box = QFrame()
            box.setObjectName("Card")
            inner = QVBoxLayout(box)
            inner.setContentsMargins(16, 14, 16, 14)
            inner.setSpacing(6)
            name = QLabel(label)
            name.setObjectName("CardTitle")
            inner.addWidget(name)
            desc = QLabel(tip)
            desc.setObjectName("Caption")
            desc.setWordWrap(True)
            inner.addWidget(desc)
            summary = QLabel("—")
            summary.setObjectName("CardStatus")
            summary.setWordWrap(True)
            inner.addWidget(summary)
            self._summaries[key] = summary
            row = QHBoxLayout()
            row.addStretch(1)
            btn = QPushButton("Open" if enabled else "Not available")
            btn.setProperty("class", "subtle")
            btn.setToolTip(tip)
            btn.setEnabled(enabled)
            btn.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            row.addWidget(btn)
            inner.addLayout(row)
            self._cards[key] = btn
            grid.addWidget(box, i // 2, i % 2)

        self.about_label = QLabel(
            "All capabilities above are functional vertical slices over "
            "certified domain engines. GREELEC: no integration "
            "(UNKNOWN / REQUIRES INPUT).")
        self.about_label.setObjectName("Caption")
        self.about_label.setWordWrap(True)
        layout.addWidget(self.about_label)
        self.refresh_state()

    def _summary_for(self, key: str) -> str:
        app = self.app
        if key == "exercises":
            return _safe(lambda: f"{len(list(app.exercises.library_keys()))} exercises in library",
                         "Engineering exercise library")
        if key == "simulation":
            return _safe(lambda: f"{len(app.engineering.backend_status_lines())} backends · OP / sweep / transient",
                         "OP / sweep / transient analyses")
        if key == "lab":
            return "F8-N sessions · instruments · deterministic replay"
        if key == "logic":
            return _safe(lambda: f"{len(tuple(app.digital.demos()))} demo circuits · edge trigger",
                         "Digital capture · edge trigger")
        if key == "resources":
            return _safe(lambda: f"{len(app.records.all_ids())} indexed records",
                         "Indexed records")
        if key == "settings":
            return f"v{__version__} · offline-first"
        return "—"

    def refresh_state(self) -> None:
        self.state_label.setText(
            f"Academic Core v{__version__} · db: {self.app.db.path}")
        for key, label in self._summaries.items():
            label.setText(self._summary_for(key))
        self.recent_label.setText(self._recent_text())

    def _recent_text(self) -> str:
        try:
            recents = self.app.search_history.list_recents()[:3]
        except Exception:
            return "Recent: unavailable"
        if not recents:
            return "No recent activity yet — open a subject, run a lab, or search."
        return "Recent: " + " · ".join(r.label for r in recents)
