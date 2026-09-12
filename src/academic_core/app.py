"""Academic Core — minimal Windows-native shell (Phase 0 gate G).

PySide6/Qt: native window, dockable panels, tabs, DPI-aware, multi-window ready.
Proves: packaging path, event loop, config + storage wiring, panel boundaries.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QLabel, QMainWindow, QTabWidget, QTextEdit,
)

from academic_core import __version__
from academic_core.config import Settings


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(f"Academic Core — Fase 0 (v{__version__})")
        self.resize(1100, 700)

        tabs = QTabWidget()
        tabs.addTab(QLabel("Dashboard — Phase 1 wiring pending"), "Dashboard")
        tabs.addTab(QLabel("Resources — Resource Engine lands in Phase 2"), "Resources")
        tabs.addTab(QLabel("Documents — Document/PDF Engine lands in Phase 3"), "Documents")
        tabs.addTab(QLabel("Labs — Engineering/Simulation lands in Phase 6-8"), "Labs")
        self.setCentralWidget(tabs)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setPlainText(
            f"Academic Core v{__version__}\n"
            f"data: {settings.storage.location}\n"
            f"ai: {settings.ai.provider} ({settings.ai.ollama_host})\n"
            "Status: Fase 0 skeleton OK. See docs/roadmap/ROADMAP.md."
        )
        dock = QDockWidget("Session log")
        dock.setWidget(log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config_path = next((a.split("=", 1)[1] for a in argv if a.startswith("--config=")), None)
    settings = Settings.load(config_path)
    settings.ensure_dirs()
    app = QApplication(argv)
    app.setApplicationName("Academic Core")
    app.setOrganizationName("Academic Core")
    win = MainWindow(settings)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
