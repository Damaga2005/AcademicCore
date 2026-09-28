# SPDX-License-Identifier: MIT
"""Product startup: splash + first-run (UI only, logic-free wiring).

- Splash: product name + version while the facade migrates.
- First-run: one Continue screen, completion persisted in QSettings.
  No accounts, no keys, no network. Offline by construction.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QSplashScreen, QVBoxLayout

from academic_core import __version__

ORG = "Academic Core"
APP = "Academic Core"
SEEN_KEY = "firstrun/seen"


def is_first_run(settings) -> bool:
    """True until the welcome screen has been accepted once."""
    return settings.value(SEEN_KEY, "0") != "1"


def mark_seen(settings) -> None:
    settings.setValue(SEEN_KEY, "1")


class FirstRunDialog(QDialog):
    """Single welcome screen (no wizard, no configuration)."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("AcademicCore")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        title = QLabel("AcademicCore")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        body = QLabel("Your academic workspace.\n\n"
                      "Everything you need to learn, solve and explore engineering.\n"
                      "Everything stays on this computer.")
        body.setWordWrap(True)
        layout.addWidget(body)
        self.continue_button = QPushButton("Continue →")
        self.continue_button.setDefault(True)
        self.continue_button.clicked.connect(self.accept)
        layout.addWidget(self.continue_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.continue_button.setFocus()

    def showEvent(self, event) -> None:
        from academic_core.ui.motion import pop_in
        super().showEvent(event)
        pop_in(self)

    def accept(self) -> None:
        mark_seen(self._settings)
        super().accept()


def make_splash(app) -> QSplashScreen:
    """Splash pixmap with product name + version (font-safe: app exists)."""
    from PySide6.QtGui import QColor, QPainter, QPixmap
    px = QPixmap(520, 300)
    px.fill(QColor("#1D1D1F"))
    painter = QPainter(px)
    painter.setPen(QColor("#F5F5F7"))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(px.rect().adjusted(32, 40, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                     "AcademicCore")
    font.setPointSize(11)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QColor("#AEAEB2"))
    painter.drawText(px.rect().adjusted(34, 0, 0, -32), Qt.AlignLeft | Qt.AlignBottom,
                     f"Your academic workspace · v{__version__}")
    painter.setPen(QColor("#007AFF"))
    painter.drawRect(32, 210, 120, 6)
    painter.fillRect(32, 210, 120, 6, QColor("#007AFF"))
    painter.end()
    splash = QSplashScreen(px)
    splash.showMessage(f"v{__version__}", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                       QColor("#AEAEB2"))
    return splash
