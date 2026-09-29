"""AcademicMainWindow (Phase 4): tree navigation + subject workspace.

Uses ONLY the application facade (AcademicApp) + domain. No repositories,
no SQLite, no CAS imports here — enforced by architecture tests.
Tabs: Overview · Activities · Grades · Planning · Resources.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from academic_core import __version__
from academic_core.ui import routes
from academic_core.ui.dialogs import confirm, prompt_form
from academic_core.ui.shell import NavRail, SectionBar, TopBar
from academic_core.ui.theme import apply_saved_theme, apply_theme, save_mode


def shell_settings():
    """UI-state store: the app's QSettings, or an .ini in ACORE_DATA_DIR when set
    (tests and portable runs stay isolated from the user's registry)."""
    import os
    from PySide6.QtCore import QSettings
    data_dir = os.environ.get("ACORE_DATA_DIR")
    if data_dir:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        return QSettings(str(Path(data_dir) / "ui-state.ini"), QSettings.Format.IniFormat)
    return QSettings("Academic Core", "Academic Core")


LEVELS = ("university", "degree", "year", "term", "subject")


class AcademicMainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app  # AcademicApp facade
        self.setWindowTitle(f"Academic Core (v{__version__})")
        self.resize(1250, 780)
        self.setMinimumSize(900, 600)
        icon = QIcon(str(Path(__file__).resolve().parents[2] / ".." / "packaging"
                         / "windows" / "academicore.ico"))
        if not icon.isNull():
            self.setWindowIcon(icon)

        # -- left: hierarchy tree ------------------------------------------------
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Academic tree")
        self.tree.setObjectName("SidebarTree")
        self.tree.setAccessibleName("Academic tree")
        left = QVBoxLayout()
        left.addWidget(self.tree)
        row = QHBoxLayout()
        self.btn_add = QPushButton("Add…")
        self.btn_del = QPushButton("Delete")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_del)
        left.addLayout(row)
        left_w = QWidget()
        left_w.setObjectName("Sidebar")
        left_w.setLayout(left)
        left_w.setFixedWidth(300)

        # -- center tabs ------------------------------------------------------------
        self.tabs = QTabWidget()
        self.tab_overview = QTextEdit(readOnly=True)
        self.tab_activities = QTextEdit(readOnly=True)
        self.tab_grades = QTextEdit(readOnly=True)
        self.tab_planning = QTextEdit(readOnly=True)
        self.tabs.addTab(self.tab_overview, "Overview")
        self.tabs.addTab(self.tab_activities, "Activities")
        self.tabs.addTab(self.tab_grades, "Grades")
        self.tabs.addTab(self.tab_planning, "Planning")
        res_tab = QWidget()
        res_layout = QVBoxLayout(res_tab)
        res_row = QHBoxLayout()
        self.res_search = QLineEdit()
        self.res_search.setPlaceholderText("Search resources (FTS5)…")
        self.btn_res_import = QPushButton("Import file…")
        self.btn_res_reindex = QPushButton("Reindex")
        self.btn_res_build = QPushButton("Build document")
        self.btn_res_export_md = QPushButton("Export MD")
        self.btn_res_export_html = QPushButton("Export HTML")
        for b in (self.btn_res_import, self.btn_res_reindex, self.btn_res_build,
                  self.btn_res_export_md, self.btn_res_export_html):
            res_row.addWidget(b)
        res_layout.addWidget(self.res_search)
        res_layout.addLayout(res_row)
        self.stirling_label = QLabel()
        res_layout.addWidget(self.stirling_label)
        self.res_list = QListWidget()
        self.res_detail = QTextEdit(readOnly=True)
        res_layout.addWidget(self.res_list)
        res_layout.addWidget(self.res_detail)
        self.tabs.addTab(res_tab, "Resources")
        self.resources_panel = res_tab
        from academic_core.ui.authoring import AuthoringPanel
        self.authoring_panel = AuthoringPanel(app)
        self.tabs.addTab(self.authoring_panel, "Authoring")
        from academic_core.ui.engineering import EngineeringPanel
        self.engineering_panel = EngineeringPanel(app)
        self.tabs.addTab(self.engineering_panel, "Engineering")
        # -- F15 tabs (dashboard first, then vertical slices) ---------------
        from academic_core.ui.dashboard import DashboardPanel
        from academic_core.ui.exercises import ExercisePanel
        from academic_core.ui.logic_analyzer import LogicAnalyzerPanel
        from academic_core.ui.simulation import SimulationPanel
        from academic_core.ui.virtual_lab import VirtualLabPanel
        self.dashboard_panel = DashboardPanel(app)
        self.exercise_panel = ExercisePanel(app)
        self.simulation_panel = SimulationPanel(app)
        self.virtual_lab_panel = VirtualLabPanel(app)
        self.logic_analyzer_panel = LogicAnalyzerPanel(app)
        self.tabs.insertTab(0, self.dashboard_panel, "Dashboard")
        self.tabs.addTab(self.exercise_panel, "Exercises")
        self.tabs.addTab(self.simulation_panel, "Simulation")
        self.tabs.addTab(self.virtual_lab_panel, "Virtual Lab")
        self.tabs.addTab(self.logic_analyzer_panel, "Logic Analyzer")
        self.dashboard_panel.navigate.connect(self._navigate)
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        self.config_label = QLabel()
        self.config_label.setWordWrap(True)
        self.config_label.setToolTip("Basic configuration and version/state")
        config_layout.addWidget(self.config_label)
        from PySide6.QtWidgets import QComboBox, QFormLayout
        settings_form = QFormLayout()
        self.appearance_box = QComboBox()
        self.appearance_box.addItems(["Follow system", "Light", "Dark"])
        self.appearance_box.setCurrentText(
            {"system": "Follow system", "light": "Light", "dark": "Dark"}.get(
                self._appearance_mode(), "Follow system"))
        self.appearance_box.currentTextChanged.connect(
            lambda t: self._set_appearance(
                {"Follow system": "system", "Light": "light"}.get(t, "dark")))
        settings_form.addRow("Appearance:", self.appearance_box)
        self.data_label = QLabel()
        self.data_label.setWordWrap(True)
        self.data_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        settings_form.addRow("Data folder:", self.data_label)
        self.btn_open_data = QPushButton("Open data folder")
        self.btn_open_data.clicked.connect(self._open_data_folder)
        settings_form.addRow("", self.btn_open_data)
        config_layout.addLayout(settings_form)
        config_layout.addStretch(1)
        self.tabs.addTab(config_tab, "Settings")
        self.settings_panel = config_tab
        self._refresh_config()

        actions = QHBoxLayout()
        # IA §5.3: one "New" menu + the primary grade action, instead of five
        # always-visible buttons. Actions keep the old attribute names.
        from PySide6.QtWidgets import QMenu
        self.btn_topic = QAction("Topic", self)
        self.btn_assignment = QAction("Assignment", self)
        self.btn_task = QAction("Task", self)
        self.btn_exam = QAction("Exam", self)
        self.new_button = QPushButton("New")
        self.new_button.setAccessibleName("New in this subject")
        new_menu = QMenu(self.new_button)
        for a in (self.btn_topic, self.btn_assignment, self.btn_task, self.btn_exam):
            new_menu.addAction(a)
        self.new_button.setMenu(new_menu)
        self.btn_grade = QPushButton("Record grade")
        self.btn_export = QPushButton("Export JSON")
        self.btn_import = QPushButton("Import JSON")
        self._subject_buttons = (self.btn_topic, self.btn_assignment, self.btn_task,
                                 self.btn_exam, self.btn_grade, self.new_button)
        actions.addWidget(self.new_button)
        actions.addWidget(self.btn_grade)
        actions.addStretch(1)
        # Data import/export lives in Settings (IA §5.3), not in a global bar.
        data_row = QHBoxLayout()
        data_row.addWidget(self.btn_export)
        data_row.addWidget(self.btn_import)
        data_row.addStretch(1)
        settings_form.addRow("Academic data:", data_row)

        # -- product shell: rail | top bar / sections / page -------------------------
        self.actions_bar = QWidget()
        self.actions_bar.setLayout(actions)
        actions.setContentsMargins(0, 0, 0, 0)
        right = QVBoxLayout()
        right.setContentsMargins(24, 12, 24, 16)
        right.setSpacing(12)
        right.addWidget(self.actions_bar)
        # Pages keep their natural minimum size; a short window scrolls
        # instead of squashing the controls (audit U-10).
        from PySide6.QtWidgets import QFrame, QScrollArea
        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("PageScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setWidget(self.tabs)
        # The stack's hint is the max of all 13 pages; use the visible page's instead.
        from PySide6.QtWidgets import QSizePolicy
        self.tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        right.addWidget(self.page_scroll, 1)
        right_w = QWidget()
        right_w.setLayout(right)
        # Routing owns navigation: the tab strip stays as the page stack
        # (13 pinned pages) but is never shown.
        self.tabs.tabBar().hide()
        left.setContentsMargins(16, 16, 16, 16)
        left_w.setFixedWidth(280)
        self.context_panel = left_w

        self.rail = NavRail()
        self.topbar = TopBar()
        self.section_bar = SectionBar()
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(left_w)
        body.addWidget(right_w, 1)
        body_w = QWidget()
        body_w.setLayout(body)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.topbar)
        column.addWidget(self.section_bar)
        column.addWidget(body_w, 1)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.rail)
        root.addLayout(column, 1)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

        log = QTextEdit(readOnly=True)
        log.setObjectName("Output")
        log.setPlainText(f"Academic Core v{__version__}\n"
                         f"db: {app.db.path}\nStirling optional; native PDF default.")
        self.session_dock = QDockWidget("Session log")
        self.session_dock.setObjectName("SessionDock")
        self.session_dock.setWidget(log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.session_dock)
        self.session_dock.hide()  # opt-in via View > Session log

        # -- appearance (theme world; logic-free wiring) ---------------------------
        from PySide6.QtWidgets import QApplication as _QApplication
        self._tokens = apply_saved_theme(_QApplication.instance())
        view_menu = self.menuBar().addMenu("&View")
        appearance = view_menu.addMenu("&Appearance")
        self._appearance_group = QActionGroup(self)
        self._appearance_group.setExclusive(True)
        from PySide6.QtCore import QSettings as _QSettings
        saved = _QSettings("Academic Core", "Academic Core").value("appearance", "system")
        for label, mode in (("Follow system", "system"), ("Light", "light"), ("Dark", "dark")):
            action = QAction(label, self, checkable=True)
            action.setChecked(saved == mode)
            action.triggered.connect(lambda _c=False, m=mode: self._set_appearance(m))
            self._appearance_group.addAction(action)
            appearance.addAction(action)
        view_menu.addSeparator()
        view_menu.addAction(self.session_dock.toggleViewAction())
        self.statusBar().showMessage(
            f"Academic Core v{__version__} · offline · {app.db.path}")

        # -- wiring ---------------------------------------------------------------
        self.app.ensure_demo()
        self.tree.itemSelectionChanged.connect(self._refresh_detail)
        self.btn_add.clicked.connect(self._add_level)
        self.btn_del.clicked.connect(self._delete_level)
        self.btn_topic.triggered.connect(self._add_topic)
        self.btn_assignment.triggered.connect(self._add_assignment)
        self.btn_task.triggered.connect(self._add_task)
        self.btn_exam.triggered.connect(self._add_exam)
        self.btn_grade.clicked.connect(self._record_grade)
        self.btn_export.clicked.connect(self._export_json)
        self.btn_import.clicked.connect(self._import_json)
        self.btn_res_import.clicked.connect(self._import_resource)
        self.btn_res_reindex.clicked.connect(self._reindex_resources)
        self.btn_res_build.clicked.connect(self._build_document)
        self.btn_res_export_md.clicked.connect(lambda: self._export_document("md"))
        self.btn_res_export_html.clicked.connect(lambda: self._export_document("html"))
        self.res_search.textChanged.connect(lambda _t: self._refresh_resources())
        self.res_list.currentRowChanged.connect(lambda _i: self._show_resource())
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._search_shortcut.activated.connect(self._open_search)
        self._build_go_menu()
        self._refresh_tree()
        self._refresh_detail()
        self._init_shell()

    # -- shell (UX IA 2026) -------------------------------------------------------
    def _init_shell(self) -> None:
        """Wire rail, top bar, section bar, history, shortcuts and restore state."""
        self._history = routes.History()
        self._last_section: dict[str, str] = {}
        self._route: routes.Route = routes.resolve("home")
        self._pages = {
            "dashboard": self.dashboard_panel, "overview": self.tab_overview,
            "activities": self.tab_activities, "grades": self.tab_grades,
            "planning": self.tab_planning, "library": self.resources_panel,
            "documents": self.authoring_panel, "exercises": self.exercise_panel,
            "circuits": self.engineering_panel, "analysis": self.simulation_panel,
            "lab": self.virtual_lab_panel, "digital": self.logic_analyzer_panel,
            "aerospace": self.engineering_panel, "settings": self.settings_panel,
        }
        self.rail.route_requested.connect(self._open_area)
        self.section_bar.section_selected.connect(self.navigate_to)
        self.topbar.crumb_clicked.connect(self.navigate_to)
        self.topbar.search_clicked.connect(self._open_search)
        self.topbar.context_clicked.connect(self._focus_context)
        self.tree.itemSelectionChanged.connect(self._sync_context)
        self.rail.refresh_icons(self._tokens)
        for i, (area, _label) in enumerate(routes.AREAS, start=1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda a=area: self._open_area(a))
        for seq, fn in (("Alt+Left", self.go_back), ("Alt+Right", self.go_forward),
                        ("Ctrl+,", lambda: self.navigate_to("settings"))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)
        self._sync_context()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # no ring on the rail at startup
        self.setFocus()
        st = shell_settings()
        geometry = st.value("shell/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.rail.set_collapsed(str(st.value("shell/rail_collapsed", "0")) == "1", animate=False)
        subject = st.value("shell/subject")
        if subject:
            self._select_subject(str(subject))
        start = routes.resolve(str(st.value("shell/route", "home")))
        self._show_route(start or routes.resolve("home"), record=True)

    def _focus_context(self) -> None:
        self.navigate_to("learn/subject/summary")
        self.tree.setFocus()

    def _sync_context(self) -> None:
        """Top-bar chip + subject-bound actions follow the tree selection."""
        sid = self._subject_id()
        name = ""
        items = self.tree.selectedItems()
        if sid and items:
            name = items[0].text(0)
        self.topbar.set_context(name)
        for b in self._subject_buttons:
            b.setEnabled(bool(sid))
            b.setToolTip("" if sid else "Choose a subject first")
        if hasattr(self, "_route"):
            self.topbar.set_crumbs(routes.crumbs(self._route, name or None))

    def _show_route(self, route: routes.Route, record: bool = True) -> None:
        page = self._pages[route.target]
        self.tabs.setCurrentWidget(page)
        self.tabs.setMinimumSize(page.minimumSizeHint().expandedTo(page.minimumSize()))
        self._route = route
        if route.section:
            self._last_section[route.area] = route.id
        if record:
            self._history.push(route.id)
        self.rail.set_area(route.area)
        self.section_bar.set_sections(route.area, routes.sections(route.area), route.id)
        self.context_panel.setVisible(route.area == "learn")
        self.actions_bar.setVisible(route.needs_subject)
        self._sync_context()
        if route.target == "aerospace":
            self.engineering_panel.orbit_panel.altitude_km.setFocus()
        try:
            st = shell_settings()
            st.setValue("shell/route", route.id)
        except Exception:
            pass

    def go_back(self) -> None:
        rid = self._history.back()
        if rid:
            self._show_route(routes.resolve(rid), record=False)

    def go_forward(self) -> None:
        rid = self._history.forward()
        if rid:
            self._show_route(routes.resolve(rid), record=False)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        try:
            st = shell_settings()
            st.setValue("shell/geometry", self.saveGeometry())
            st.setValue("shell/rail_collapsed", "1" if self.rail.collapsed else "0")
            sid = self._subject_id()
            st.setValue("shell/subject", sid or "")
            st.sync()
        except Exception:
            pass
        super().closeEvent(event)

    # -- tree ---------------------------------------------------------------------
    @staticmethod
    def _appearance_mode() -> str:
        from PySide6.QtCore import QSettings as _QSettings
        return str(_QSettings("Academic Core", "Academic Core").value("appearance", "system"))

    def _open_data_folder(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.settings.storage.location)))

    def _set_appearance(self, mode: str) -> None:
        """Persist the appearance choice and re-apply the world QSS."""
        from PySide6.QtWidgets import QApplication as _QApplication
        save_mode(mode)
        self._tokens = apply_theme(_QApplication.instance(), mode)
        if hasattr(self, "rail"):
            self.rail.refresh_icons(self._tokens)
        if hasattr(self, "appearance_box"):
            self.appearance_box.blockSignals(True)
            self.appearance_box.setCurrentText(
                {"system": "Follow system", "light": "Light", "dark": "Dark"}.get(mode, "Dark"))
            self.appearance_box.blockSignals(False)
        self.statusBar().showMessage(
            f"Academic Core v{__version__} · offline · {self.app.db.path}")

    def _navigate(self, key: str) -> None:
        """Dashboard/legacy navigation: same entry point as the shell."""
        self.navigate_to(key)

    def _refresh_config(self) -> None:
        from academic_core import __version__ as _v
        settings = self.app.settings
        self.config_label.setText(
            f"Academic Core v{_v}\n"
            f"storage: {settings.storage.location}\n"
            f"license: MIT (LICENSE)\n"
            f"lab schema: f8n-lab/1\n"
            f"GREELEC: no integration (UNKNOWN / REQUIRES INPUT)")
        if hasattr(self, "data_label"):
            self.data_label.setText(str(settings.storage.location))

    def navigate_to(self, key: str) -> None:
        """Go to a route id or a legacy key (home, overview, lab, logic ...).

        Unknown keys are ignored. The 13-page structure is untouched
        (pinned by UI tests); routing only picks the visible page.
        """
        route = routes.resolve(key)
        if route is not None:
            self._show_route(route)

    def _open_area(self, area: str) -> None:
        """Rail/Ctrl+N: land on the area's last visited section."""
        self._show_route(routes.area_default(area, self._last_section.get(area)))

    def _build_go_menu(self) -> None:
        from PySide6.QtWidgets import QMenu
        self.go_menu = QMenu("Go", self)
        self.menuBar().addMenu(self.go_menu)
        groups: tuple = (
            ("Home", (("Home", "home"),)),
            ("Learn", (("Overview", "overview"), ("Resources", "resources"))),
            ("Practice", (("Exercises", "exercises"),)),
            ("Engineering", (("Engineering", "engineering"), ("Simulation", "simulation"),
                             ("Virtual Lab", "lab"), ("Logic Analyzer", "logic"))),
            ("Settings", (("Settings", "settings"),)),
        )
        first = True
        for group, items in groups:
            if not first:
                self.go_menu.addSeparator()
            first = False
            for label, key in items:
                self.go_menu.addAction(f"{group}: {label}",
                                       lambda _c=False, k=key: self.navigate_to(k))
        self.go_menu.addSeparator()
        self.go_menu.addAction("Engineering: Modules…", lambda _c=False: self._open_modules())

    def _open_modules(self) -> None:
        from academic_core.ui.modules import ModulesDialog
        ModulesDialog(self.app, self.navigate_to, self).exec()

    def _open_search(self) -> None:
        from academic_core.ui.search import SearchDialog
        dlg = SearchDialog(self.app, self, goto=routes.goto_entries())
        if not dlg.exec():
            return
        picked = dlg.selection()
        if picked is None:
            return
        kind, value = picked
        if kind == "route":
            self.navigate_to(value)
        elif value.ref and self._select_subject(value.ref):
            self.navigate_to("learn/subject/summary")
        else:
            self.statusBar().showMessage(f"No destination yet for {value.kind} results", 4000)

    def _refresh_tree(self) -> None:
        self.tree.clear()
        self._index: dict[int, tuple[str, str]] = {}
        for uni in self.app.queries.tree():
            u = QTreeWidgetItem([uni["university"].name])
            self._index[id(u)] = ("university", uni["university"].stable_id)
            self.tree.addTopLevelItem(u)
            for deg in uni["degrees"]:
                d = QTreeWidgetItem([deg["degree"].name])
                self._index[id(d)] = ("degree", deg["degree"].stable_id)
                u.addChild(d)
                for yr in deg["years"]:
                    y = QTreeWidgetItem([yr["year"].label])
                    self._index[id(y)] = ("year", yr["year"].stable_id)
                    d.addChild(y)
                    for tm in yr["terms"]:
                        t = QTreeWidgetItem([tm["term"].label])
                        self._index[id(t)] = ("term", tm["term"].stable_id)
                        y.addChild(t)
                        for s in tm["subjects"]:
                            leaf = QTreeWidgetItem([s.name])
                            self._index[id(leaf)] = ("subject", s.stable_id)
                            t.addChild(leaf)
        self.tree.expandAll()

    def _selection(self) -> tuple[str | None, str | None]:
        items = self.tree.selectedItems()
        if not items:
            return None, None
        return self._index.get(id(items[0]), (None, None))

    def _subject_id(self) -> str | None:
        level, sid = self._selection()
        return sid if level == "subject" else None

    def _select_subject(self, stable_id: str) -> bool:
        """Select the subject node with this id (search navigation)."""
        for i in range(self.tree.topLevelItemCount()):
            if self._select_in(self.tree.topLevelItem(i), stable_id):
                return True
        return False

    def _select_in(self, item, stable_id: str) -> bool:
        if self._index.get(id(item)) == ("subject", stable_id):
            self.tree.setCurrentItem(item)
            return True
        for i in range(item.childCount()):
            if self._select_in(item.child(i), stable_id):
                self.tree.expandItem(item)
                return True
        return False

    def _add_level(self) -> None:
        level, sid = self._selection()
        svc = self.app.svc
        try:
            if level is None:
                v = prompt_form(self, "University", [("name", "Name", "", "text")])
                if v:
                    svc.create_university(v["name"])
            elif level == "university":
                v = prompt_form(self, "Degree", [("name", "Name", "", "text")])
                if v:
                    svc.create_degree(sid, v["name"])
            elif level == "degree":
                v = prompt_form(self, "Academic year", [("label", "Label (2025-26)", "", "text")])
                if v:
                    svc.create_year(sid, v["label"])
            elif level == "year":
                v = prompt_form(self, "Term",
                                [("label", "Label", "", "text"),
                                 ("kind", "Kind", [("Cuatrimestre", "cuatrimestre"),
                                                   ("Semestre", "semestre"),
                                                   ("Trimestre", "trimestre"),
                                                   ("Anual", "anual"),
                                                   ("Otro", "otro")], "combo"),
                                 ("index", "Order", 1, "int")])
                if v:
                    svc.create_term(sid, v["label"], v["kind"], v["index"])
            elif level == "term":
                v = prompt_form(self, "Subject",
                                [("name", "Name", "", "text"),
                                 ("code", "Code", "", "text"),
                                 ("acronym", "Acronym", "", "text"),
                                 ("credits", "Credits", "6.0", "text")])
                if v:
                    svc.create_subject(v["name"], sid, code=v["code"],
                                       acronym=v["acronym"],
                                       credits=float(v["credits"] or 0))
            else:
                QMessageBox.information(self, "Add", "Use the action row for subject items")
                return
        except Exception as e:
            QMessageBox.warning(self, "Add", f"{type(e).__name__}: {e}")
            return
        self._refresh_tree()

    def _delete_level(self) -> None:
        level, sid = self._selection()
        if not sid or not confirm(self, f"Delete {level} {sid}?"):
            return
        fn = {"university": self.app.svc.delete_university,
              "degree": self.app.svc.delete_degree,
              "year": self.app.svc.delete_year,
              "term": self.app.svc.delete_term,
              "subject": self.app.svc.delete_subject}.get(level)
        if fn is None:
            return
        try:
            fn(sid)
        except Exception as e:
            QMessageBox.warning(self, "Delete", f"{type(e).__name__}: {e}")
            return
        self._refresh_tree()

    # -- subject actions --------------------------------------------------------------
    def _need_subject(self) -> str | None:
        sid = self._subject_id()
        if not sid:
            QMessageBox.warning(self, "Subject", "Select a subject in the tree first")
        return sid

    def _add_topic(self) -> None:
        sid = self._need_subject()
        if not sid:
            return
        v = prompt_form(self, "Topic", [("index", "Index (01)", "01", "text"),
                                        ("title", "Title", "", "text")])
        if v:
            try:
                self.app.svc.create_topic(sid, v["index"], v["title"])
            except Exception as e:
                QMessageBox.warning(self, "Topic", str(e))
        self._refresh_detail()

    def _add_assignment(self) -> None:
        sid = self._need_subject()
        if not sid:
            return
        v = prompt_form(self, "Assignment", [("title", "Title", "", "text")])
        if v:
            try:
                self.app.svc.create_assignment(self.app.planning, sid, v["title"])
            except Exception as e:
                QMessageBox.warning(self, "Assignment", str(e))
        self._refresh_detail()

    def _add_task(self) -> None:
        sid = self._need_subject()
        if not sid:
            return
        v = prompt_form(self, "Task",
                        [("title", "Title", "", "text"),
                         ("kind", "Kind", [("Entrega", "entrega"),
                                           ("Examen final", "examen_final"),
                                           ("Parcial", "examen_parcial"),
                                           ("General", "tarea_general")], "combo")])
        if v:
            try:
                self.app.svc.create_task(self.app.planning, self.app.study, sid,
                                         v["title"], kind=v["kind"])
            except Exception as e:
                QMessageBox.warning(self, "Task", str(e))
        self._refresh_detail()

    def _add_exam(self) -> None:
        sid = self._need_subject()
        if not sid:
            return
        v = prompt_form(self, "Exam", [("title", "Title", "", "text"),
                                       ("day", "Date", None, "date")])
        if v:
            try:
                self.app.svc.create_exam(self.app.planning, sid, v["title"], day=v["day"])
            except Exception as e:
                QMessageBox.warning(self, "Exam", str(e))
        self._refresh_detail()

    def _record_grade(self) -> None:
        sid = self._need_subject()
        if not sid:
            return
        v = prompt_form(self, "Grade",
                        [("key", "Activity key", "", "text"),
                         ("value", "Value", "", "text"),
                         ("scale", "Scale", [("0–10", "n10"), ("0–100", "n100"),
                                             ("Letters", "letters"),
                                             ("Pass/Fail", "pf")], "combo"),
                         ("weight", "Weight", "100", "text")])
        if not v:
            return
        try:
            self.app.results.record_grade(
                sid, v["key"], v["value"], v["scale"], v["weight"])
        except Exception as e:
            QMessageBox.warning(self, "Grade", f"{type(e).__name__}: {e}")
        self._refresh_detail()

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export academic JSON", "",
                                              "JSON (*.json)")
        if path:
            n = self.app.io.export_file(path)
            QMessageBox.information(self, "Export", f"{n} bytes written")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import academic JSON", "",
                                              "JSON (*.json)")
        if not path:
            return
        try:
            rep = self.app.io.import_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Import", f"{type(e).__name__}: {e}")
            return
        errs = "\n".join(rep["errors"][:10])
        QMessageBox.information(self, "Import",
                                f"imported: {rep['imported']}\nerrors: {len(rep['errors'])}\n{errs}")
        self._refresh_tree()

    # -- detail ------------------------------------------------------------------------
    def _refresh_detail(self) -> None:
        sid = self._subject_id()
        if not sid:
            for tab in (self.tab_overview, self.tab_activities,
                        self.tab_grades, self.tab_planning):
                tab.setPlainText("Select a subject in the tree")
            self._refresh_resources()
            return
        acts = self.app.queries.activities_by_subject(sid)
        staff = self.app.academic.staff_of(sid)
        self.tab_overview.setPlainText(
            f"subject: {sid}\n"
            f"topics: {len(acts['topics'])} | refs: {len(acts['refs'])}\n"
            f"staff: {', '.join(p.name for p, _ in staff) or '(none)'}\n"
            f"prerequisites: {', '.join(self.app.academic.prerequisites_of(sid)) or '(none)'}")
        lines = []
        for label, items in (("assignments", acts["assignments"]), ("exams", acts["exams"]),
                             ("projects", acts["projects"]), ("labs", acts["labs"]),
                             ("tasks", acts["tasks"]), ("topics", acts["topics"])):
            lines.append(f"== {label} ({len(items)}) ==")
            for it in items:
                state = getattr(it, "status", getattr(it, "state", ""))
                lines.append(f"• {getattr(it, 'title', '?')} [{state}] "
                             f"{getattr(it, 'stable_id', '')}")
        self.tab_activities.setPlainText("\n".join(lines))
        verdict = self.app.grading.calculate(sid)
        result = self.app.results.result(sid)
        self.tab_grades.setPlainText(
            f"scheme(0-10): grade={verdict.grade} evaluated={verdict.evaluated} "
            f"state={verdict.state}\n"
            f"gradebook: ratio={result.ratio} evaluated={result.evaluated_weight}/"
            f"{result.total_weight} state={result.state} complete={result.complete}")
        today = date.today()
        up = self.app.queries.upcoming_deadlines(today, 10)
        over = self.app.queries.overdue_deadlines(today, 10)
        self.tab_planning.setPlainText(
            "upcoming:\n" + "\n".join(f"• {d.title} [{d.kind}] {d.due}" for d in up) +
            "\n\noverdue:\n" + "\n".join(f"• {d.title} [{d.kind}] {d.due}" for d in over))
        self._refresh_resources()

    # -- resources (facade-backed; same behavior as F3) -----------------------------------
    def _refresh_resources(self) -> None:
        query = self.res_search.text().strip()
        self.res_list.clear()
        self._res_cache = []
        try:
            state = self.app.stirling.detect()
            self.stirling_label.setText(
                f"Stirling: {state['state']} ({state['url']}) · native PDF ready")
        except Exception:
            self.stirling_label.setText("Stirling: UNKNOWN · native PDF ready")
        if query:
            for h in self.app.fts.search(query, limit=50):
                self._res_cache.append(h["stable_id"])
                self.res_list.addItem(QListWidgetItem(
                    f"{h['title']} [{h['kind']}] {h['stable_id']}"))
        else:
            for sid in self.app.records.all_ids():
                res = self.app.records.get(sid)
                self._res_cache.append(sid)
                self.res_list.addItem(QListWidgetItem(
                    f"{res.title} [{res.kind}] v{res.current_version} {sid}"))

    def _selected_resource_id(self) -> str | None:
        i = self.res_list.currentRow()
        cache = getattr(self, "_res_cache", [])
        return cache[i] if 0 <= i < len(cache) else None

    def _show_resource(self) -> None:
        sid = self._selected_resource_id()
        if not sid:
            return
        res = self.app.records.get(sid)
        if not res:
            return
        cur = res.current()
        p = cur.provenance
        lines = [f"id: {res.stable_id}", f"kind: {res.kind}", f"title: {res.title}",
                 f"version: {cur.version} (of {len(res.versions)})",
                 f"hash: {cur.content_hash}", f"size: {cur.size} bytes",
                 f"origin: {p.origin}", f"source: {p.source}",
                 f"adapter: {p.adapter} v{p.adapter_version}",
                 f"imported: {p.imported_at}", f"extraction: {p.extraction_status}"]
        self.res_detail.setPlainText("\n".join(lines))

    def _import_resource(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import resource")
        if not path:
            return
        try:
            rep = self.app.ingest.import_file(path, subject_id=self._subject_id())
        except Exception as e:
            QMessageBox.warning(self, "Import", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Import", f"{rep.outcome}: {rep.stable_id} v{rep.version}")
        self._refresh_resources()

    def _reindex_resources(self) -> None:
        n = self.app.ingest.reindex()
        QMessageBox.information(self, "Reindex", f"{n} entries rebuilt")
        self._refresh_resources()

    def _build_document(self) -> None:
        sid = self._selected_resource_id()
        if not sid:
            QMessageBox.warning(self, "Document", "Select a resource first")
            return
        try:
            summary = self.app.documents.build(sid)
        except Exception as e:
            QMessageBox.warning(self, "Document", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Document",
                                f"{summary['parser']}: {summary['blocks']} blocks")
        self._show_resource()

    def _export_document(self, fmt: str) -> None:
        sid = self._selected_resource_id()
        if not sid:
            QMessageBox.warning(self, "Export", "Select a resource first")
            return
        rows = self.app.documents.list(sid)
        if not rows:
            QMessageBox.warning(self, "Export", "Build a document first")
            return
        row = rows[0]
        if fmt == "md":
            out, filtr = self.app.documents.render_markdown(
                sid, row["resource_version"], row["parser"]), "Markdown (*.md)"
        else:
            out, filtr = self.app.documents.render_html(
                sid, row["resource_version"], row["parser"]), "HTML (*.html)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", "", filtr)
        if path:
            Path(path).write_text(out, encoding="utf-8")
