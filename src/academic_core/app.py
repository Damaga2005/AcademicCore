"""Academic Core entry point (thin): settings -> facade -> Qt window.

No business logic, no repositories, no SQL here — only wiring.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from academic_core import __version__
from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.ui.main_window import AcademicMainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config_path = next((a.split("=", 1)[1] for a in argv if a.startswith("--config=")), None)
    settings = Settings.load(config_path)
    settings.ensure_dirs()
    core = AcademicApp(settings)
    app = QApplication(argv)
    app.setApplicationName("Academic Core")
    app.setOrganizationName("Academic Core")
    win = AcademicMainWindow(core)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
