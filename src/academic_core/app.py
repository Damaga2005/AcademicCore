"""Academic Core — validation UI (Phase 1 gate UI).

PySide6/Qt: university > degree > year > term selectors, subjects list with
create/edit, and Assignments / Tasks / Schedule / Grades tabs wired to the
Application layer over SQLite. Styling is intentionally plain: this UI proves
the domain, it is not the final product look.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFormLayout,
    QHBoxLayout, QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from academic_core import __version__
from academic_core.application import (
    AcademicService, DocumentService, GradingService, IngestionService,
    ScheduleService, SimpleSearchService,
)
from academic_core.application.services import ApplicationError
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.domain.identity import slugify
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    GradingRepository, PlanningRepository, SqliteResourceRecords,
    StudyRepository,
)


def _db(settings: Settings) -> Database:
    return Database(Path(settings.storage.location) / "academic.db")


def ensure_demo(academic: AcademicRepository) -> None:
    """Generic, deletable demo hierarchy (never UPC/GREELEC-specific)."""
    if academic.list_universities():
        return
    academic.add_university(E.University("university:demo", "Universidad Demo"))
    academic.add_degree(E.Degree("degree:demo-grado", "Grado Demo", "university:demo"))
    academic.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:demo-grado"))
    academic.add_term(E.Term("term:demo-c1", "Cuatrimestre 1", "cuatrimestre", 1,
                             "year:2025-26", date(2025, 9, 1), date(2026, 1, 31)))


class _SubjectDialog(QDialog):
    def __init__(self, parent, sub: E.Subject | None = None):
        super().__init__(parent)
        self.setWindowTitle("Subject")
        self.name = QLineEdit(sub.name if sub else "")
        self.code = QLineEdit(sub.code if sub else "")
        self.acronym = QLineEdit(sub.acronym if sub else "")
        self.credits = QLineEdit(str(sub.credits) if sub else "6.0")
        form = QFormLayout(self)
        form.addRow("Name", self.name)
        form.addRow("Code", self.code)
        form.addRow("Acronym", self.acronym)
        form.addRow("Credits", self.credits)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> dict:
        return {"name": self.name.text(), "code": self.code.text(),
                "acronym": self.acronym.text(),
                "credits": float(self.credits.text() or 0)}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(f"Academic Core — Fase 1 (v{__version__})")
        self.resize(1150, 720)

        db = _db(settings)
        self.academic = AcademicRepository(db)
        self.planning = PlanningRepository(db)
        self.grading_repo = GradingRepository(db)
        self.study = StudyRepository(db)
        self.svc = AcademicService(self.academic)
        self.grading = GradingService(self.grading_repo)
        self.schedule = ScheduleService(self.planning)
        self.search = SimpleSearchService(self.academic, self.planning)
        cas_root = Path(settings.ingest.cas_dir or Path(settings.storage.location) / "cas")
        self.blobs = FileBlobStore(cas_root)
        self.resources = SqliteResourceRecords(db)
        self.fts = FtsResourceIndexer(db)
        self.ingest = IngestionService(
            self.blobs, self.resources, self.fts, self.academic, self.planning,
            max_bytes=settings.ingest.max_bytes)
        self.documents = DocumentService(self.blobs, self.resources, db)
        from academic_core.pdf.stirling import StirlingRuntime
        self.stirling = StirlingRuntime(settings.tools.stirling_url)
        ensure_demo(self.academic)

        # -- left: hierarchy selectors + subjects ---------------------------
        self.cb_uni = QComboBox()
        self.cb_deg = QComboBox()
        self.cb_year = QComboBox()
        self.cb_term = QComboBox()
        self.subjects = QListWidget()
        left = QVBoxLayout()
        for label, cb in (("University", self.cb_uni), ("Degree", self.cb_deg),
                          ("Year", self.cb_year), ("Term", self.cb_term)):
            left.addWidget(QLabel(label))
            left.addWidget(cb)
        left.addWidget(QLabel("Subjects"))
        left.addWidget(self.subjects)
        row = QHBoxLayout()
        self.btn_add_sub = QPushButton("Add")
        self.btn_edit_sub = QPushButton("Edit")
        row.addWidget(self.btn_add_sub)
        row.addWidget(self.btn_edit_sub)
        left.addLayout(row)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(320)

        # -- tabs -------------------------------------------------------------
        self.tabs = QTabWidget()
        self.tab_assign = QTextEdit(readOnly=True)
        self.tab_tasks = QTextEdit(readOnly=True)
        self.tab_sched = QTextEdit(readOnly=True)
        self.tab_grades = QTextEdit(readOnly=True)
        self.tabs.addTab(self.tab_assign, "Assignments")
        self.tabs.addTab(self.tab_tasks, "Tasks")
        self.tabs.addTab(self.tab_sched, "Schedule")
        self.tabs.addTab(self.tab_grades, "Grades")
        # Resources tab: thin validation panel over IngestionService.
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
        res_row.addWidget(self.res_search)
        res_row.addWidget(self.btn_res_import)
        res_row.addWidget(self.btn_res_reindex)
        res_row.addWidget(self.btn_res_build)
        res_row.addWidget(self.btn_res_export_md)
        res_row.addWidget(self.btn_res_export_html)
        res_layout.addLayout(res_row)
        self.stirling_label = QLabel()
        res_layout.addWidget(self.stirling_label)
        self.res_list = QListWidget()
        self.res_detail = QTextEdit(readOnly=True)
        res_layout.addWidget(self.res_list)
        res_layout.addWidget(self.res_detail)
        self.tabs.addTab(res_tab, "Resources")
        self.btn_res_import.clicked.connect(self._import_resource)
        self.btn_res_reindex.clicked.connect(self._reindex_resources)
        self.btn_res_build.clicked.connect(self._build_document)
        self.btn_res_export_md.clicked.connect(lambda: self._export_document("md"))
        self.btn_res_export_html.clicked.connect(lambda: self._export_document("html"))
        self.res_search.textChanged.connect(lambda _t: self._refresh_resources())
        self.res_list.currentRowChanged.connect(lambda _i: self._show_resource())
        # one action row above the tabs (no business logic in UI slots beyond
        # calling Application services)
        actions = QHBoxLayout()
        self.btn_assignment = QPushButton("Add assignment")
        self.btn_task = QPushButton("Add task")
        self.btn_series = QPushButton("Add class series")
        self.btn_scheme = QPushButton("Record grade scheme")
        for b, fn in ((self.btn_assignment, self._add_assignment),
                      (self.btn_task, self._add_task),
                      (self.btn_series, self._add_series),
                      (self.btn_scheme, self._add_scheme)):
            b.clicked.connect(fn)
            actions.addWidget(b)

        central = QHBoxLayout()
        central.addWidget(left_w)
        right = QVBoxLayout()
        right.addLayout(actions)
        right.addWidget(self.tabs)
        right_w = QWidget()
        right_w.setLayout(right)
        central.addWidget(right_w)
        root = QWidget()
        root.setLayout(central)
        self.setCentralWidget(root)

        log = QTextEdit(readOnly=True)
        log.setPlainText(
            f"Academic Core v{__version__} — Fase 1\n"
            f"db: {db.path}\n"
            f"ai: {settings.ai.provider} (wired in Phase 10, interface only)")
        dock = QDockWidget("Session log")
        dock.setWidget(log)
        from PySide6.QtCore import Qt
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # -- wiring -------------------------------------------------------------
        self.cb_uni.currentIndexChanged.connect(self._refresh_degrees)
        self.cb_deg.currentIndexChanged.connect(self._refresh_years)
        self.cb_year.currentIndexChanged.connect(self._refresh_terms)
        self.cb_term.currentIndexChanged.connect(self._refresh_subjects)
        self.subjects.currentRowChanged.connect(lambda _i: self._refresh_tabs())
        self.btn_add_sub.clicked.connect(self._add_subject)
        self.btn_edit_sub.clicked.connect(self._edit_subject)
        self._refresh_unis()

    # -- selectors ------------------------------------------------------------
    def _fill(self, cb: QComboBox, items: list[tuple[str, str]]) -> None:
        cb.blockSignals(True)
        cb.clear()
        for label, data in items:
            cb.addItem(label, data)
        cb.blockSignals(False)

    def _refresh_unis(self) -> None:
        unis = self.academic.list_universities()
        self._fill(self.cb_uni, [(u.name, u.stable_id) for u in unis])
        self._refresh_degrees()

    def _refresh_degrees(self) -> None:
        uid = self.cb_uni.currentData()
        degs = self.academic.degrees_of(uid) if uid else []
        self._fill(self.cb_deg, [(d.name, d.stable_id) for d in degs])
        self._refresh_years()

    def _refresh_years(self) -> None:
        did = self.cb_deg.currentData()
        years = self.academic.years_of(did) if did else []
        self._fill(self.cb_year, [(y.label, y.stable_id) for y in years])
        self._refresh_terms()

    def _refresh_terms(self) -> None:
        yid = self.cb_year.currentData()
        terms = self.academic.terms_of(yid) if yid else []
        self._fill(self.cb_term, [(t.label, t.stable_id) for t in terms])
        self._refresh_subjects()

    def _refresh_subjects(self) -> None:
        tid = self.cb_term.currentData()
        subs = self.academic.subjects_of_term(tid) if tid else []
        self.subjects.clear()
        for s in subs:
            self.subjects.addItem(f"{s.name} [{s.stable_id}]")
        self._subs_cache = subs
        self._refresh_tabs()

    def _current_subject(self) -> E.Subject | None:
        subs = getattr(self, "_subs_cache", [])
        i = self.subjects.currentRow()
        return subs[i] if 0 <= i < len(subs) else None

    # -- subject CRUD ------------------------------------------------------------
    def _add_subject(self) -> None:
        tid = self.cb_term.currentData()
        if not tid:
            QMessageBox.warning(self, "Subject", "Select a term first")
            return
        dlg = _SubjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.svc.create_subject(term_id=tid, **dlg.values())
        except (ApplicationError, ValueError) as e:
            QMessageBox.warning(self, "Subject", str(e))
            return
        self._refresh_subjects()

    def _edit_subject(self) -> None:
        sub = self._current_subject()
        if not sub:
            return
        dlg = _SubjectDialog(self, sub)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        sub.name, sub.code, sub.acronym, sub.credits = (
            v["name"], v["code"], v["acronym"].upper(), v["credits"])
        try:
            self.svc.update_subject(sub)
        except (ApplicationError, ValueError) as e:
            QMessageBox.warning(self, "Subject", str(e))
            return
        self._refresh_subjects()

    # -- tab actions ---------------------------------------------------------------
    def _add_assignment(self) -> None:
        sub = self._current_subject()
        if not sub:
            QMessageBox.warning(self, "Assignment", "Select a subject first")
            return
        try:
            self.svc.create_assignment(self.planning, sub.stable_id, "Nueva entrega")
        except (ApplicationError, ValueError) as e:
            QMessageBox.warning(self, "Assignment", str(e))
        self._refresh_tabs()

    def _add_task(self) -> None:
        sub = self._current_subject()
        if not sub:
            QMessageBox.warning(self, "Task", "Select a subject first")
            return
        try:
            self.svc.create_task(self.planning, self.study, sub.stable_id,
                                 "Nueva tarea", kind="entrega")
        except (ApplicationError, ValueError) as e:
            QMessageBox.warning(self, "Task", str(e))
        self._refresh_tabs()

    def _add_series(self) -> None:
        sub = self._current_subject()
        if not sub:
            QMessageBox.warning(self, "Schedule", "Select a subject first")
            return
        try:
            self.schedule.add_series(
                sub.stable_id, kind="teoria", weekday=2, start="09:00", end="11:00",
                first_day=date(2025, 9, 1), last_day=date(2025, 12, 19),
                interval_weeks=1, room="A1")
        except ValueError as e:
            QMessageBox.warning(self, "Schedule", str(e))
        self._refresh_tabs()

    def _add_scheme(self) -> None:
        sub = self._current_subject()
        if not sub:
            QMessageBox.warning(self, "Grades", "Select a subject first")
            return
        self.grading.record_scheme(
            sub.stable_id, "continua",
            [E.GradeComponent("Parcial", "parcial", "40", "7.5"),
             E.GradeComponent("Final", "examen_final", "60", None)])
        self._refresh_tabs()

    def _refresh_tabs(self) -> None:
        sub = self._current_subject()
        if not sub:
            for tab in (self.tab_assign, self.tab_tasks, self.tab_sched, self.tab_grades):
                tab.setPlainText("Select a subject")
            self._refresh_resources()
            return
        assigns = self.planning.assignments_of(sub.stable_id)
        self.tab_assign.setPlainText("\n".join(
            f"• {a.title} [{a.status}] {a.stable_id}" for a in assigns) or "(none)")
        tasks = self.planning.tasks_of(sub.stable_id)
        self.tab_tasks.setPlainText("\n".join(
            f"• {t.title} ({t.kind}, {t.state}) {t.stable_id}" for t in tasks) or "(none)")
        series = self.planning.series_of(sub.stable_id)
        self.tab_sched.setPlainText("\n".join(
            f"• {r['kind']} weekday={r['weekday']} {r['start']}-{r['end']} "
            f"{r['first_day']}..{r['last_day']} x{r['interval_weeks']}" for r in series) or "(none)")
        verdict = self.grading.calculate(sub.stable_id)
        self.tab_grades.setPlainText(
            f"grade={verdict.grade} evaluated={verdict.evaluated} state={verdict.state}")
        self._refresh_resources()

    # -- resources ---------------------------------------------------------------
    def _refresh_resources(self) -> None:
        query = self.res_search.text().strip()
        self.res_list.clear()
        self._res_cache = []
        try:
            state = self.stirling.detect()
            self.stirling_label.setText(
                f"Stirling: {state['state']} ({state['url']}) · native PDF ready")
        except Exception:
            self.stirling_label.setText("Stirling: UNKNOWN · native PDF ready")
        if query:
            hits = self.fts.search(query, limit=50)
            for h in hits:
                self._res_cache.append(h["stable_id"])
                item = QListWidgetItem(f"{h['title']} [{h['kind']}] {h['stable_id']}")
                self.res_list.addItem(item)
        else:
            for sid in self.resources.all_ids():
                res = self.resources.get(sid)
                self._res_cache.append(sid)
                self.res_list.addItem(
                    QListWidgetItem(f"{res.title} [{res.kind}] v{res.current_version} {sid}"))

    def _show_resource(self) -> None:
        i = self.res_list.currentRow()
        cache = getattr(self, "_res_cache", [])
        if not (0 <= i < len(cache)):
            return
        res = self.resources.get(cache[i])
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
        for v in res.versions:
            lines.append(f"  v{v.version}: {v.content_hash[:12]}… {v.provenance.imported_at}")
        self.res_detail.setPlainText("\n".join(lines))

    def _import_resource(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import resource")
        if not path:
            return
        sub = self._current_subject()
        try:
            rep = self.ingest.import_file(
                path, subject_id=sub.stable_id if sub else None)
        except Exception as e:  # UnsupportedType / TooLarge / SecurityError surface here
            QMessageBox.warning(self, "Import", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(
            self, "Import", f"{rep.outcome}: {rep.stable_id} v{rep.version}")
        self._refresh_resources()

    def _reindex_resources(self) -> None:
        n = self.ingest.reindex()
        QMessageBox.information(self, "Reindex", f"{n} entries rebuilt from canonical store")
        self._refresh_resources()

    def _selected_resource_id(self) -> str | None:
        i = self.res_list.currentRow()
        cache = getattr(self, "_res_cache", [])
        return cache[i] if 0 <= i < len(cache) else None

    def _build_document(self) -> None:
        sid = self._selected_resource_id()
        if not sid:
            QMessageBox.warning(self, "Document", "Select a resource first")
            return
        try:
            summary = self.documents.build(sid)
        except Exception as e:
            QMessageBox.warning(self, "Document", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(
            self, "Document",
            f"{summary['parser']}: {summary['blocks']} blocks, '{summary['title']}'")
        self._show_resource()

    def _export_document(self, fmt: str) -> None:
        sid = self._selected_resource_id()
        if not sid:
            QMessageBox.warning(self, "Export", "Select a resource first")
            return
        rows = self.documents.list(sid)
        if not rows:
            QMessageBox.warning(self, "Export", "Build a document first")
            return
        row = rows[0]
        doc = self.documents.get(sid, row["resource_version"], row["parser"])
        if fmt == "md":
            from academic_core.documents import render_markdown as RM
            out, filtr = RM.render(doc), "Markdown (*.md)"
        else:
            from academic_core.documents import render_html as RH
            out, filtr = RH.render(doc), "HTML (*.html)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", "", filtr)
        if path:
            Path(path).write_text(out, encoding="utf-8")


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
