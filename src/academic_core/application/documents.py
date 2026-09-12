"""Document service (Phase 3 application): Resource(+Version) -> Document AST.

A Resource may gain several Document derivations (html/md/pdf parsers);
each is stored once per (resource_id, version, parser) with full provenance
chain. Originals are never mutated. No Qt here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from academic_core.documents import ast as A


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentService:
    def __init__(self, blobs, records, db):
        self.blobs = blobs
        self.records = records
        self.db = db

    def build(self, resource_id: str, version: int | None = None,
              parser: str = "auto") -> dict:
        """Parse the resource bytes into a Document; persist + return summary."""
        from academic_core.documents import html_parser, markdown_parser
        res = self.records.get(resource_id)
        if res is None:
            raise ValueError(f"unknown resource: {resource_id}")
        ver = next((v for v in res.versions
                    if version is None or v.version == (version or res.current_version)),
                   None)
        if ver is None:
            ver = res.current()
        raw = self.blobs.get_bytes(ver.content_hash)
        kind = res.kind
        if parser == "auto":
            parser = {"html": "html", "markdown": "markdown", "text": "markdown",
                      "pdf": "pdf"}.get(kind, "none")
        if parser == "html":
            doc = html_parser.parse_html(
                raw, put=self.blobs.put_bytes,
                filename=ver.provenance.original_filename)
            pname, pver = html_parser.PARSER_NAME, html_parser.PARSER_VERSION
        elif parser == "markdown":
            text = raw.decode("utf-8", errors="replace")
            doc = markdown_parser.parse_markdown(
                text, ver.provenance.original_filename)
            pname, pver = markdown_parser.PARSER_NAME, markdown_parser.PARSER_VERSION
        elif parser == "pdf":
            from academic_core.pdf.engine import PDFEngine, NativePDFBackend
            engine = PDFEngine(NativePDFBackend())
            doc = engine.to_document(raw, resource_id, ver.version)
            pname, pver = "pdf-native", "3.0"
        else:
            raise ValueError(f"no document parser for kind={kind}")
        A.validate(doc)
        payload = json.dumps(doc.to_dict(), ensure_ascii=False, sort_keys=True)
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO documents(resource_id, resource_version,"
                   " parser, parser_version, created_at, ast_json, warnings)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (resource_id, ver.version, pname, pver, _utcnow(), payload, "[]"))
        cx.commit()
        cx.close()
        return {"resource_id": resource_id, "version": ver.version,
                "parser": pname, "blocks": len(doc.children),
                "title": doc.meta.title}

    def get(self, resource_id: str, version: int, parser: str) -> A.Document:
        cx = self.db.connect()
        row = cx.execute("SELECT ast_json FROM documents WHERE resource_id=?"
                         " AND resource_version=? AND parser=?",
                         (resource_id, version, parser)).fetchone()
        cx.close()
        if not row:
            raise KeyError(f"no document {resource_id} v{version} [{parser}]")
        return A.Document.from_dict(json.loads(row["ast_json"]))

    def list(self, resource_id: str) -> list[dict]:
        cx = self.db.connect()
        rows = cx.execute("SELECT resource_version, parser, parser_version, created_at"
                          " FROM documents WHERE resource_id=? ORDER BY resource_version",
                          (resource_id,)).fetchall()
        cx.close()
        return [dict(r) for r in rows]
