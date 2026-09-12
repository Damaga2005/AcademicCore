"""AcademicMainWindow (Phase 4): tree navigation + subject workspace.

Uses ONLY the application facade (AcademicApp) + domain. No repositories,
no SQLite, no CAS imports here — enforced by architecture tests.
Tabs: Overview · Activities · Grades · Planning · Resources.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from academic_core import __version__
from academic_core.ui.dialogs import confirm, prompt_form

LEVELS = ("university", "degree", "year", "term", "subject")


class AcademicMainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app  # AcademicApp facade
        self.setWindowTitle(f"Academic Core — F4 Academic Management (v{__version__})")
        self.resize(1250, 780)

        # -- left: hierarchy tree ------------------------------------------------
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Academic tree")
        left = QVBoxLayout()
        left.addWidget(self.tree)
        row = QHBoxLayout()
        self.btn_add = QPushButton("Add…")
        self.btn_del = QPushButton("Delete")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_del)
        left.addLayout(row)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(330)

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

        actions = QHBoxLayout()
        self.btn_topic = QPushButton("Add topic")
        self.btn_assignment = QPushButton("Add assignment")
        self.btn_task = QPushButton("Add task")
        self.btn_exam = QPushButton("Add exam")
        self.btn_grade = QPushButton("Record grade")
        self.btn_export = QPushButton("Export JSON")
        self.btn_import = QPushButton("Import JSON")
        for b in (self.btn_topic, self.btn_assignment, self.btn_task, self.btn_exam,
                  self.btn_grade, self.btn_export, self.btn_import):
            actions.addWidget(b)
        right = QVBoxLayout()
        right.addLayout(actions)
        right.addWidget(self.tabs)
        right_w = QWidget()
        right_w.setLayout(right)

        root = QHBoxLayout()
        root.addWidget(left_w)
        root.addWidget(right_w)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

        log = QTextEdit(readOnly=True)
        log.setPlainText(f"Academic Core v{__version__} — F4\n"
                         f"db: {app.db.path}\nStirling optional; native PDF default.")
        dock = QDockWidget("Session log")
        dock.setWidget(log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # -- wiring ---------------------------------------------------------------
        self.app.ensure_demo()
        self.tree.itemSelectionChanged.connect(self._refresh_detail)
        self.btn_add.clicked.connect(self._add_level)
        self.btn_del.clicked.connect(self._delete_level)
        self.btn_topic.clicked.connect(self._add_topic)
        self.btn_assignment.clicked.connect(self._add_assignment)
        self.btn_task.clicked.connect(self._add_task)
        self.btn_exam.clicked.connect(self._add_exam)
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
        self._refresh_tree()
        self._refresh_detail()

    # -- tree ---------------------------------------------------------------------
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
            from decimal import Decimal
            from academic_core.domain import results as R
            scales = {"n10": R.N_10, "n100": R.N_100,
                      "letters": R.LETTERS_ES, "pf": R.PASS_FAIL}
            self.app.results.record(sid, R.Grade(v["key"], v["value"],
                                                 scales[v["scale"]],
                                                 Decimal(v["weight"] or 0)))
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
        doc = self.app.documents.get(sid, row["resource_version"], row["parser"])
        if fmt == "md":
            from academic_core.documents import render_markdown as RM
            out, filtr = RM.render(doc), "Markdown (*.md)"
        else:
            from academic_core.documents import render_html as RH
            out, filtr = RH.render(doc), "HTML (*.html)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", "", filtr)
        if path:
            Path(path).write_text(out, encoding="utf-8")
