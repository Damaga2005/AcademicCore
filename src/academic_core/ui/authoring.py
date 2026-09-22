"""Authoring panel (Phase 5 UI): browser + outline + block editors + actions.

The service-owned AuthoringDocument is the single source of truth; this
panel reflects it (refresh functions) and sends commands back. AST<->UI is
explicit: block editing is Markdown-mediated with reparse + validation
report, equations/code/metadata have dedicated editors. No Qt state is ever
the canonical copy.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from academic_core.ui.dialogs import prompt_form


class AuthoringPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app  # AcademicApp facade
        self.sid: str | None = None
        # Opaque working document owned by AuthoringService (D1 AI-001:
        # this panel never imports domain.authoring / documents.*).
        self.state: object | None = None

        layout = QHBoxLayout(self)
        # -- browser ----------------------------------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Documents"))
        self.browser = QListWidget()
        left.addWidget(self.browser)
        row = QHBoxLayout()
        self.btn_new = QPushButton("New…")
        self.btn_open = QPushButton("Open")
        row.addWidget(self.btn_new)
        row.addWidget(self.btn_open)
        left.addLayout(row)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(260)
        layout.addWidget(left_w)

        # -- outline -------------------------------------------------------------
        mid = QVBoxLayout()
        mid.addWidget(QLabel("Outline"))
        self.outline = QTreeWidget()
        self.outline.setHeaderLabel("Structure")
        mid.addWidget(self.outline)
        mid_w = QWidget()
        mid_w.setLayout(mid)
        mid_w.setFixedWidth(300)
        layout.addWidget(mid_w)

        # -- editor -----------------------------------------------------------------
        right = QVBoxLayout()
        right.addWidget(QLabel("Block editor"))
        self.block_kind = QLabel("(no block)")
        right.addWidget(self.block_kind)
        self.block_edit = QTextEdit()
        right.addWidget(self.block_edit)
        self.eq_display = QCheckBox("Display equation")
        right.addWidget(self.eq_display)
        edit_row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply block")
        self.btn_delete = QPushButton("Delete block")
        self.btn_insert = QPushButton("Insert paragraph after")
        edit_row.addWidget(self.btn_apply)
        edit_row.addWidget(self.btn_delete)
        edit_row.addWidget(self.btn_insert)
        right.addLayout(edit_row)
        right.addWidget(QLabel("Metadata"))
        meta_row = QHBoxLayout()
        self.meta_title = QLineEdit()
        self.meta_title.setPlaceholderText("Title")
        self.btn_meta = QPushButton("Set title")
        meta_row.addWidget(self.meta_title)
        meta_row.addWidget(self.btn_meta)
        right.addLayout(meta_row)
        act_row = QHBoxLayout()
        self.btn_save = QPushButton("Save (new version)")
        self.btn_undo = QPushButton("Undo")
        self.btn_redo = QPushButton("Redo")
        self.btn_validate = QPushButton("Validate")
        self.btn_link = QPushButton("Link…")
        self.btn_life = QPushButton("Lifecycle…")
        for b in (self.btn_save, self.btn_undo, self.btn_redo,
                  self.btn_validate, self.btn_link, self.btn_life):
            act_row.addWidget(b)
        right.addLayout(act_row)
        exp_row = QHBoxLayout()
        self.btn_exp_md = QPushButton("Export MD")
        self.btn_exp_html = QPushButton("Export HTML")
        exp_row.addWidget(self.btn_exp_md)
        exp_row.addWidget(self.btn_exp_html)
        right.addLayout(exp_row)
        self.status = QLabel("No document open")
        right.addWidget(self.status)
        right_w = QWidget()
        right_w.setLayout(right)
        layout.addWidget(right_w)

        # -- wiring -------------------------------------------------------------------
        self.btn_new.clicked.connect(self._new)
        self.btn_open.clicked.connect(self._open_selected)
        self.browser.currentRowChanged.connect(lambda _i: self._preview())
        self.outline.currentItemChanged.connect(lambda cur, _p: self._load_block(cur))
        self.btn_apply.clicked.connect(self._apply_block)
        self.btn_delete.clicked.connect(self._delete_block)
        self.btn_insert.clicked.connect(self._insert_block)
        self.btn_meta.clicked.connect(self._set_title)
        self.btn_save.clicked.connect(self._save)
        self.btn_undo.clicked.connect(lambda: self._hist("undo"))
        self.btn_redo.clicked.connect(lambda: self._hist("redo"))
        self.btn_validate.clicked.connect(self._validate)
        self.btn_link.clicked.connect(self._link)
        self.btn_life.clicked.connect(self._lifecycle)
        self.btn_exp_md.clicked.connect(lambda: self._export("md"))
        self.btn_exp_html.clicked.connect(lambda: self._export("html"))
        self.refresh_browser()

    # -- browser ------------------------------------------------------------------------
    def refresh_browser(self) -> None:
        self.browser.clear()
        self._ids = []
        for sid in self.app.authoring_store.authored_ids():
            res = self.app.records.get(sid)
            if res is None:
                continue
            self._ids.append(sid)
            self.browser.addItem(QListWidgetItem(
                f"{res.title or sid} [{self.app.authoring_store.lifecycle_of(sid)}]"))

    def _new(self) -> None:
        names = [(n, n) for n in self.app.authoring.template_names()]
        v = prompt_form(self, "New document", [("t", "Template", names, "combo")])
        if not v:
            return
        try:
            sid = self.app.authoring.create_from_template(v["t"])
        except Exception as e:
            QMessageBox.warning(self, "New", str(e))
            return
        self.refresh_browser()
        self._open(sid)

    def _preview(self) -> None:
        pass  # selection shown on Open; keeps panel predictable

    def _open_selected(self) -> None:
        i = self.browser.currentRow()
        if 0 <= i < len(self._ids):
            self._open(self._ids[i])

    def _open(self, sid: str) -> None:
        try:
            self.state = self.app.authoring.open(sid)
        except Exception as e:
            QMessageBox.warning(self, "Open", f"{type(e).__name__}: {e}")
            return
        self.sid = sid
        self.refresh_all()

    # -- outline + block editors (via AuthoringService only, D1 AI-001) ----
    @staticmethod
    def _label(node) -> str:
        return str(node)

    def refresh_all(self) -> None:
        if self.state is None or self.sid is None:
            return
        res = self.app.records.get(self.sid)
        life = self.app.authoring_store.lifecycle_of(self.sid)
        revision, dirty, _n = self.app.authoring.doc_status(self.state)
        self.status.setText(
            f"{self.sid} · v{res.current_version} · rev {revision} · "
            f"{life} · {'dirty' if dirty else 'clean'}")
        self.outline.clear()
        self._paths: dict[int, tuple] = {}
        for i, label in enumerate(self.app.authoring.top_block_labels(self.state)):
            item = QTreeWidgetItem([label])
            self._paths[id(item)] = (i,)
            self.outline.addTopLevelItem(item)
        self.meta_title.setText(self.app.authoring.doc_title(self.state))

    def _current_path(self):
        items = self.outline.selectedItems()
        if not items:
            return None
        return self._paths.get(id(items[0]))

    def _load_block(self, item) -> None:
        if item is None or self.state is None:
            return
        path = self._paths.get(id(item))
        if path is None:
            return
        kind, text, display = self.app.authoring.block_editor_text(self.state, path)
        self.block_kind.setText(f"{kind} {path}")
        self.block_edit.setPlainText(text)
        self.eq_display.setChecked(display)

    def _apply_block(self) -> None:
        if self.state is None:
            return
        path = self._current_path()
        if path is None:
            QMessageBox.warning(self, "Block", "Select a block in the outline")
            return
        kind, _text, _display = self.app.authoring.block_editor_text(self.state, path)
        try:
            if kind == "equation":
                self.app.authoring.apply_equation(
                    self.state, path, self.block_edit.toPlainText(),
                    self.eq_display.isChecked())
            elif kind == "code_block":
                self.app.authoring.apply_code(
                    self.state, path, self.block_edit.toPlainText())
            else:
                self.app.authoring.apply_markdown(
                    self.state, path, self.block_edit.toPlainText())
        except Exception as e:
            QMessageBox.warning(self, "Block", f"{type(e).__name__}: {e}")
            return
        self.refresh_all()

    def _delete_block(self) -> None:
        if self.state is None:
            return
        path = self._current_path()
        if path is None:
            return
        try:
            self.app.authoring.delete_block(self.state, path)
        except Exception as e:
            QMessageBox.warning(self, "Block", str(e))
        self.refresh_all()

    def _insert_block(self) -> None:
        if self.state is None:
            return
        path = self._current_path()
        svc = self.app.authoring
        _rev, _dirty, n = svc.doc_status(self.state)
        anchor = path[0] + 1 if path else n
        try:
            svc.insert_paragraph(self.state, anchor)
        except Exception as e:
            QMessageBox.warning(self, "Block", str(e))
        self.refresh_all()

    def _set_title(self) -> None:
        if self.state is None:
            return
        self.app.authoring.set_title(self.state, self.meta_title.text())
        self.refresh_all()

    # -- history / persistence ----------------------------------------------------------------------
    def _hist(self, op: str) -> None:
        if self.state is None:
            return
        ok = self.state.undo() if op == "undo" else self.state.redo()
        if not ok:
            QMessageBox.information(self, op.title(), f"Nothing to {op}")
        self.refresh_all()

    def _save(self) -> None:
        if self.state is None or self.sid is None:
            return
        try:
            rep = self.app.authoring.save(self.state, self.sid)
        except Exception as e:
            QMessageBox.warning(self, "Save", f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Save", f"{rep.outcome}: v{rep.version}")
        self.refresh_browser()
        self.refresh_all()

    def _validate(self) -> None:
        if self.state is None:
            return
        issues = self.app.authoring.validate(self.state)
        if not issues:
            QMessageBox.information(self, "Validate", "No issues")
            return
        lines = [f"[{i.severity}] {i.path} {i.code}: {i.message}" for i in issues[:30]]
        QMessageBox.warning(self, "Validate", "\n".join(lines))

    def _link(self) -> None:
        if self.sid is None:
            return
        v = prompt_form(self, "Academic link",
                        [("kind", "Kind",
                          [("Subject", "subject"), ("Topic", "topic"),
                           ("Assignment", "assignment"), ("Project", "project"),
                           ("Lab", "lab"), ("Exam", "exam")], "combo"),
                         ("id", "Stable id", "", "text")])
        if not v:
            return
        try:
            self.app.authoring.link(self.sid, v["kind"], v["id"])
        except Exception as e:
            QMessageBox.warning(self, "Link", f"{type(e).__name__}: {e}")

    def _lifecycle(self) -> None:
        if self.sid is None:
            return
        v = prompt_form(self, "Lifecycle",
                        [("to", "State",
                          [("DRAFT", "DRAFT"), ("REVIEW", "REVIEW"),
                           ("PUBLISHED", "PUBLISHED"), ("ARCHIVED", "ARCHIVED")],
                          "combo")])
        if not v:
            return
        try:
            self.app.authoring.set_lifecycle(self.sid, v["to"])
        except Exception as e:
            QMessageBox.warning(self, "Lifecycle", f"{type(e).__name__}: {e}")
            return
        self.refresh_browser()
        self.refresh_all()

    def _export(self, fmt: str) -> None:
        if self.state is None:
            return
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path as _P
        if fmt == "md":
            out, filtr = self.app.authoring.export_markdown(self.state), "Markdown (*.md)"
        else:
            out, filtr = self.app.authoring.export_html(self.state), "HTML (*.html)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", "", filtr)
        if path:
            _P(path).write_text(out, encoding="utf-8")
