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
    from academic_core import runtime
    if runtime.is_frozen():
        # Installed product: user data under %LOCALAPPDATA%/AcademicCore
        # (Program Files is not writable). Dev behavior unchanged.
        root = runtime.user_data_dir()
        settings = Settings.load(config_path, overrides={
            "storage.location": str(root / "data"),
            "storage.cas_dir": str(root / "data" / "cas"),
            "storage.index_dir": str(root / "data" / "index"),
            "storage.cache_dir": str(root / "data" / "cache"),
        })
    from academic_core.ui import windows
    windows.set_app_user_model_id()
    app = QApplication(argv)
    app.setApplicationName("Academic Core")
    instance = windows.SingleInstance()
    if not instance.claim():
        return 0  # already running: the first window was asked to come forward
    app.setOrganizationName("Academic Core")
    from academic_core.ui.startup import APP, ORG, FirstRunDialog, is_first_run, make_splash
    from PySide6.QtCore import QSettings
    splash = make_splash(app)
    splash.show()
    app.processEvents()
    settings.ensure_dirs()
    core = AcademicApp(settings)
    from academic_core.ui.theme import apply_saved_theme
    apply_saved_theme(app)
    win = AcademicMainWindow(core)
    instance.activated.connect(lambda: windows.bring_to_front(win))
    if is_first_run(QSettings(ORG, APP)):
        FirstRunDialog(QSettings(ORG, APP), win).exec()
    win.show()
    splash.finish(win)
    code = app.exec()
    instance.release()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
