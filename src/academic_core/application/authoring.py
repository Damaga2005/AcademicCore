"""Authoring service (Phase 5 application): working state → versions.

Authored documents live as `document`-kind Resources whose bytes are the
canonical AST JSON. Editing (commands/undo) touches working state only;
`save()` mints versions; autosave never contaminates versions. No Qt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from academic_core.documents import ast as A
from academic_core.domain import authoring as AU
from academic_core.domain import resources as R

EDITOR = "authoring"
EDITOR_VERSION = "5.0"
AUTOSAVE_CAP = 1 << 20


def canonical_json(doc: A.Document) -> bytes:
    return json.dumps(doc.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")


def extract_text(doc: A.Document) -> str:
    parts = []

    def walk(n):
        if n.kind == "text":
            parts.append(n.attrs.get("value", ""))
        elif n.kind in ("inline_code",):
            parts.append(n.attrs.get("code", ""))
        elif n.kind == "code_block":
            parts.append(n.attrs.get("code", ""))
        elif n.kind == "equation":
            parts.append(n.attrs.get("source", ""))
        for c in n.children:
            walk(c)

    for c in doc.children:
        walk(c)
    return "\n".join(parts)


def _title_explicitly_touched(state: AU.AuthoringDocument) -> bool:
    """True iff the session's undo history holds any UpdateMetadata step
    (i.e. the user is explicitly managing metadata this session, so the
    current title — even an empty one — is intent, not an untouched
    default). A bare body-only edit leaves no such step and an empty
    AST title must not wipe the stored title."""
    for form in getattr(state, "_undo", ()):
        if hasattr(form, "meta") and hasattr(form, "old"):
            return True
    return False


@dataclass(frozen=True)
class SaveReport:
    stable_id: str
    version: int
    content_hash: str
    outcome: str  # saved|noop-identical
    blocks: int


class AuthoringService:
    def __init__(self, blobs, records, indexer, documents, store, academic=None,
                 planning=None, autosave_dir: str | Path = ""):
        self.blobs = blobs
        self.records = records
        self.indexer = indexer
        self.documents = documents
        self.store = store
        self.academic = academic
        self.planning = planning
        self.autosave_dir = Path(autosave_dir) if autosave_dir else None

    # -- creation ---------------------------------------------------------------
    def _mint(self, doc: A.Document, title: str, origin: str, scope: str,
              note: str) -> str:
        from academic_core.domain.identity import make
        data = canonical_json(doc)
        content_hash = self.blobs.put_bytes(data)
        counters = self.academic.load_counters() if self.academic else {}
        n = counters.get("resource", 0) + 1
        sid = make("resource", scope, f"{n:05d}")
        if self.academic:
            counters["resource"] = n
            self.academic.save_counters(counters)
        prov = R.ResourceProvenance(origin, "", title, content_hash,
                                    datetime.now(timezone.utc).isoformat(),
                                    EDITOR, EDITOR_VERSION, "ok", 0, note)
        with self.records.unit_of_work() as cx:
            self.records.save_new(
                R.Resource(sid, "document", title or doc.meta.title, 1,
                           [R.ResourceVersion(sid, 1, content_hash, len(data), prov)]), cx)
        self.store.touch(sid)
        self.indexer.index(sid, "document", title or doc.meta.title, extract_text(doc))
        return sid

    def create_from_template(self, template: str, scope: str = "general") -> str:
        from academic_core.documents import templates as T
        if template not in T.TEMPLATES:
            raise ValueError(f"unknown template: {template}")
        doc = T.TEMPLATES[template]()
        sid = self._mint(doc, doc.meta.title, "generated", scope, f"template:{template}")
        self.store.set_lifecycle(sid, "DRAFT", template)
        return sid

    def create_from_resource(self, resource_id: str, version: int | None = None,
                             scope: str = "general") -> str:
        doc, pname, pver = self.documents.load_ast(resource_id, version)
        res = self.records.get(resource_id)
        ver = res.current_version if version is None else version
        title = res.title or doc.meta.title
        # provenance chain: authored doc descends from the source resource
        sid = self._mint(doc, title, "manual", scope,
                         f"authored-from:{resource_id}:v{ver}:{pname}")
        self.store.set_lifecycle(sid, "DRAFT")
        return sid

    # -- open / save ---------------------------------------------------------------
    def open(self, resource_id: str) -> AU.AuthoringDocument:
        doc, _, _ = self.documents.load_ast(resource_id)
        state = AU.AuthoringDocument(doc)
        state.mark_clean()
        return state

    def save(self, state: AU.AuthoringDocument, resource_id: str) -> SaveReport:
        A.validate(state.doc)
        data = canonical_json(state.doc)
        res = self.records.get(resource_id)
        if res is None or res.kind != "document":
            raise ValueError(f"not an authored document: {resource_id}")
        if res.current().content_hash == self.blobs.put_bytes(data):
            return SaveReport(resource_id, res.current_version,
                              res.current().content_hash, "noop-identical",
                              len(state.doc.children))
        content_hash = self.blobs.put_bytes(data)
        prov = R.ResourceProvenance(
            "manual", "", res.title, content_hash,
            datetime.now(timezone.utc).isoformat(), EDITOR, EDITOR_VERSION,
            "ok", res.current_version)
        with self.records.unit_of_work() as cx:
            self.records.append_version(
                R.ResourceVersion(resource_id, res.current_version + 1,
                                  content_hash, len(data), prov), cx)
        # P0-07 title policy: canonical record and FTS index always agree.
        # An empty meta.title with a non-empty stored title is ambiguous:
        # it is an intentional clear ONLY when the user explicitly ran
        # UpdateMetadata in this session (visible in undo history);
        # otherwise it is an accidental empty (e.g. body-only edit on a
        # doc whose AST title was never set) and the stored title is
        # preserved instead of wiped.
        new_title = state.doc.meta.title
        if new_title != res.title:
            if new_title == "" and res.title != "" and not _title_explicitly_touched(state):
                new_title = res.title
            if new_title != res.title:
                self.records.update_title(resource_id, new_title)
        self.store.touch(resource_id)
        self.indexer.index(resource_id, "document", new_title, extract_text(state.doc))
        self.cleanup_autosave(resource_id)
        state.mark_clean()
        return SaveReport(resource_id, res.current_version + 1, content_hash,
                          "saved", len(state.doc.children))

    # -- validation / links / lifecycle ----------------------------------------------
    def validate(self, state: AU.AuthoringDocument) -> list:
        from academic_core.documents.validate import validate_document
        return validate_document(state.doc, self.blobs.exists)

    def set_lifecycle(self, resource_id: str, to: str) -> None:
        self.store.set_lifecycle(resource_id, to)

    def link(self, resource_id: str, target_kind: str, target_id: str) -> None:
        self._check_target(target_kind, target_id)
        self.store.add_link(resource_id, target_kind, target_id)

    def _check_target(self, kind: str, tid: str) -> None:
        if kind == "subject" and self.academic is not None:
            if self.academic.get_subject(tid) is None:
                raise ValueError(f"unknown subject: {tid}")
            return
        if kind == "topic" and self.academic is not None:
            tids = [t.stable_id for s in self.academic.all_subjects()
                    for t in self.academic.topics_of(s.stable_id)]
            if tid not in tids:
                raise ValueError(f"unknown topic: {tid}")
            return
        if kind in ("assignment", "exam", "project", "lab") and self.planning is not None:
            found = {"assignment": self.planning.get_assignment,
                     "exam": lambda i: next(
                         (e for s in self.academic.all_subjects()
                          for e in self.planning.exams_of(s.stable_id)
                          if e.stable_id == i), None),
                     "project": lambda i: next(
                         (p for s in self.academic.all_subjects()
                          for p in self.planning.projects_of(s.stable_id)
                          if p.stable_id == i), None),
                     "lab": lambda i: next(
                         (lb for s in self.academic.all_subjects()
                          for lb in self.planning.labs_of(s.stable_id)
                          if lb.stable_id == i), None)}[kind](tid)
            if found is None:
                raise ValueError(f"unknown {kind}: {tid}")
            return
        # no registries injected: accept ids that validate structurally
        from academic_core.domain.identity import validate
        validate(tid)

    # -- autosave -----------------------------------------------------------------------
    def _auto_path(self, resource_id: str) -> Path:
        if self.autosave_dir is None:
            raise ValueError("autosave not configured")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in resource_id)
        return self.autosave_dir / f"{safe}.json"

    def autosave(self, state: AU.AuthoringDocument, resource_id: str) -> int:
        data = canonical_json(state.doc)
        if len(data) > AUTOSAVE_CAP:
            raise ValueError("document exceeds autosave cap")
        self.autosave_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._auto_path(resource_id).with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(self._auto_path(resource_id))
        return len(data)

    def recover(self, resource_id: str):
        path = self._auto_path(resource_id)
        if not path.is_file():
            return None
        doc = A.Document.from_dict(json.loads(path.read_bytes().decode("utf-8")))
        A.validate(doc)
        return AU.AuthoringDocument(doc)

    def cleanup_autosave(self, resource_id: str) -> None:
        try:
            self._auto_path(resource_id).unlink(missing_ok=True)
        except ValueError:
            pass

    # -- F15 block editing (D1 AI-001: UI calls these, never domain) ----
    def template_names(self) -> list[str]:
        from academic_core.documents import templates as T
        return sorted(T.TEMPLATES)

    def top_block_labels(self, state: AU.AuthoringDocument) -> list[str]:
        return [self._block_label(b) for b in state.doc.children]

    @staticmethod
    def _block_label(node) -> str:
        if node.kind == "heading":
            kids = "".join(c.attrs.get("value", "") for c in node.children
                            if c.kind == "text")
            return f"H{node.attrs.get('level', '?')} {kids[:40]}"
        if node.kind == "paragraph":
            kids = "".join(c.attrs.get("value", "") for c in node.children
                            if c.kind == "text")
            return f"¶ {kids[:40]}"
        if node.kind == "equation":
            return f"= {node.attrs.get('source', '')[:40]}"
        if node.kind == "code_block":
            return f"<> {node.attrs.get('language', '')}"
        if node.kind == "table":
            return f"▦ {len(node.children)} rows"
        if node.kind == "image":
            return f"🖼 {node.attrs.get('alt', '')[:30]}"
        return node.kind

    def block_editor_text(self, state: AU.AuthoringDocument,
                          path: tuple) -> tuple[str, str, bool]:
        """Plain-data view of one block: (kind, editable text, display flag)."""
        from academic_core.documents import render_markdown as RM
        node = AU._get(state.doc, path)
        if node.kind == "equation":
            return node.kind, node.attrs.get("source", ""), bool(node.attrs.get("display"))
        if node.kind == "code_block":
            return node.kind, node.attrs.get("code", ""), False
        return node.kind, RM.render(
            A.Document(A.Metadata(), (), (node,))).strip(), False

    def apply_equation(self, state: AU.AuthoringDocument, path: tuple,
                       source: str, display: bool) -> None:
        state.execute(AU.ReplaceNode(path, A.equation(source, "latex", display)))

    def apply_code(self, state: AU.AuthoringDocument, path: tuple,
                   code: str) -> None:
        node = AU._get(state.doc, path)
        state.execute(AU.ReplaceNode(
            path, A.code_block(code, node.attrs.get("language", ""))))

    def apply_markdown(self, state: AU.AuthoringDocument, path: tuple,
                       text: str) -> None:
        from academic_core.documents.markdown_parser import parse_markdown
        parsed = parse_markdown(text)
        if len(parsed.children) != 1:
            raise ValueError(
                f"expected 1 block, got {len(parsed.children)} (nothing applied)")
        state.execute(AU.ReplaceNode(path, parsed.children[0]))

    def delete_block(self, state: AU.AuthoringDocument, path: tuple) -> None:
        state.execute(AU.DeleteNode(path))

    def insert_paragraph(self, state: AU.AuthoringDocument, anchor: int) -> None:
        state.execute(AU.InsertNode((anchor,), A.paragraph([A.text("…")])))

    def set_title(self, state: AU.AuthoringDocument, title: str) -> None:
        meta = A.Metadata(**{**state.doc.meta.to_dict(), "title": title})
        state.execute(AU.UpdateMetadata(meta))

    def doc_title(self, state: AU.AuthoringDocument) -> str:
        return state.doc.meta.title

    def doc_status(self, state: AU.AuthoringDocument) -> tuple:
        return (state.revision, state.dirty, len(state.doc.children))

    def export_markdown(self, state: AU.AuthoringDocument) -> str:
        from academic_core.documents import render_markdown as RM
        return RM.render(state.doc)

    def export_html(self, state: AU.AuthoringDocument) -> str:
        from academic_core.documents import render_html as RH
        return RH.render(state.doc)

    # -- copy / paste ----------------------------------------------------------------------
    @staticmethod
    def copy_nodes(nodes: list) -> str:
        return json.dumps([n.to_dict() for n in nodes], ensure_ascii=False, sort_keys=True)

    @staticmethod
    def paste_nodes(mime: str, data: str) -> tuple[list, tuple]:
        """Returns (nodes, warnings). Rejects or degrades explicitly — never
        silently drops content."""
        if mime == "application/x-academic-ast":
            try:
                raw = json.loads(data)
                if not isinstance(raw, list) or not raw:
                    raise ValueError("empty node list")
                return [A.Node.from_dict(d) for d in raw], ()
            except Exception as e:
                raise ValueError(f"bad AST clipboard payload: {e}")
        if mime == "text/markdown":
            from academic_core.documents.markdown_parser import parse_markdown
            doc = parse_markdown(data)
            return list(doc.children), ("reparsed from markdown",)
        if mime == "text/html":
            from academic_core.documents.html_parser import parse_html
            doc = parse_html(data.encode("utf-8", errors="replace"))
            return list(doc.children), ("reparsed from html",)
        raise ValueError(f"unsupported clipboard mime: {mime} (paste rejected, nothing lost)")
