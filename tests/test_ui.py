"""UI gate: application boots on Windows and offscreen with real domain."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from academic_core.app import MainWindow  # noqa: E402
from academic_core.config import Settings  # noqa: E402


def test_main_window_boots_with_real_domain(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    settings = Settings.load()
    settings.ensure_dirs()
    win = MainWindow(settings)
    qtbot.addWidget(win)
    assert "Academic Core" in win.windowTitle()
    assert win.tabs.count() == 5  # Assignments Tasks Schedule Grades Resources
    assert win.subjects.count() >= 0
    assert win.cb_uni.count() >= 1  # demo hierarchy present
