"""UI gate: application boots on Windows and offscreen with real domain."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from academic_core.application import AcademicApp  # noqa: E402
from academic_core.config import Settings  # noqa: E402
from academic_core.ui.main_window import AcademicMainWindow  # noqa: E402


def test_main_window_boots_with_real_domain(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    assert "Academic Core" in win.windowTitle()
    assert win.tabs.count() == 7  # Overview Activities Grades Planning Resources Authoring Engineering
    assert win.tree.topLevelItemCount() >= 1  # demo hierarchy present
    assert "Select a subject" in win.tab_overview.toPlainText()
