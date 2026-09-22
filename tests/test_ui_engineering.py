"""Engineering UI offscreen smoke: project, circuit, topology, calculation."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.ui.main_window import AcademicMainWindow


def test_engineering_tab_boots(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    assert win.tabs.count() == 12  # F15: Dashboard + legacy + Exercises + Simulation + Virtual Lab + Settings
    assert win.engineering_panel.projects.count() == 0
    core.engineering.create_project("demo")
    win.engineering_panel.refresh_projects()
    assert win.engineering_panel.projects.count() == 1
