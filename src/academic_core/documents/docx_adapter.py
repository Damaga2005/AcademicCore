# SPDX-License-Identifier: MIT
"""DOCX → Document AST adapter (F3.1 §28): stdlib-only, safe XML, no macros.

Pipeline: ZIP → safe XML → paragraphs/headings/tables/images/relationships/
OMML → AST. Heading styles map to levels 1-6 (off-by-one fixed).
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from academic_core.documents import ast as A
from academic_core.documents import limits as L
from academic_core.documents.office_security import read_zip_member, safe_open_zip
from academic_core.documents.omml import omml_to_latex
from academic_core.errors import AdapterError, ValidationError

PARSER_NAME = "docx-adapter"
PARSER_VERSION = "1.0"

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_HEADING = re.compile(r"(?:heading|t[ií]tulo|encabezado)\s*([1-6])", re.I)


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _text_of(p) -> str:
    return "".join(t.text or "" for t in p.iter() if _local(t.tag) == "t")


def _style_of(p) -> str:
    for c in p:
        if _local(c.tag) == "pPr":
            for g in c:
                if _local(g.tag) == "pStyle":
                    return g.get(f"{_W}val", "") or ""
    return ""


def _runs(p) -> list:
    out = []
    for r in p:
        if _local(r.tag) != "r":
            continue
        t = "".join(t.text or "" for t in r.iter() if _local(t.tag) == "t")
        if not t:
            continue
        b = any(_local(x.tag) == "b" for x in r.iter())
        i = any(_local(x.tag) == "i" for x in r.iter())
        node: A.Node = A.text(t)
        if i:
            node = A.emphasis([node])
        if b:
            node = A.strong([node])
        out.append(node)
    return out


def parse_docx(data: bytes, put=None, filename: str = "") -> tuple[A.Document, list[str]]:
    """Parse DOCX bytes → (Document, warnings). `put(bytes)→hex` stores images."""
    warnings: list[str] = []
    zf = safe_open_zip(data, kind="docx")
    try:
        try:
            doc_xml = read_zip_member(zf, "word/document.xml")
        except ValidationError:
            raise
        if b"<!ENTITY" in doc_xml.upper() or b"<!DOCTYPE" in doc_xml.upper():
            raise AdapterError("SECURITY: DOCX XML with ENTITY/DOCTYPE rejected",
                               code="AC-ADP-236")
        try:
            root = ET.fromstring(doc_xml)
        except ET.ParseError as e:
            raise ValidationError(f"MALFORMED_DOCX: bad document.xml ({e})",
                                  code="AC-VAL-234") from None
        # relationships (links/images alt)
        rels: dict[str, str] = {}
        try:
            rels_xml = read_zip_member(zf, "word/_rels/document.xml.rels")
            for rel in ET.fromstring(rels_xml).iter():
                if _local(rel.tag) == "Relationship":
                    rels[rel.get("Id", "")] = rel.get("Target", "")
        except ValidationError:
            warnings.append("relationships unreadable; links kept as text")
        # core metadata
        meta = {"title": "", "author": ""}
        try:
            core_xml = read_zip_member(zf, "docProps/core.xml")
            for el in ET.fromstring(core_xml).iter():
                loc = _local(el.tag)
                if loc == "title" and el.text:
                    meta["title"] = el.text.strip()
                elif loc == "creator" and el.text:
                    meta["author"] = el.text.strip()
        except ValidationError:
            pass
        body = None
        for c in root:
            if _local(c.tag) == "body":
                body = c
                break
        if body is None:
            raise ValidationError("MALFORMED_DOCX: no w:body", code="AC-VAL-235")
        blocks: list[A.Node] = []
        math_count = images = tables = 0
        for child in body:
            kind = _local(child.tag)
            if kind == "p":
                style = _style_of(child)
                hm = _HEADING.search(style)
                # OMML in paragraph
                ommls = [g for g in child.iter() if _local(g.tag) in ("oMath", "oMathPara")]
                inlines = _runs(child)
                for o in ommls:
                    try:
                        latex = omml_to_latex(o).strip()
                    except (AdapterError, ValidationError) as e:
                        warnings.append(f"omml skipped: {e}")
                        continue
                    if latex:
                        inlines.append(A.equation(latex, "latex", _local(o.tag) == "oMathPara"))
                        math_count += 1
                if not inlines and not _text_of(child).strip():
                    continue
                if hm:
                    blocks.append(A.heading(int(hm.group(1)), inlines or [A.text(_text_of(child))]))
                else:
                    blocks.append(A.paragraph(inlines))
            elif kind == "tbl":
                tables += 1
                rows = []
                for tr in child:
                    if _local(tr.tag) != "tr":
                        continue
                    cells = []
                    for tc in tr:
                        if _local(tc.tag) != "tc":
                            continue
                        txt = " ".join(_text_of(p) for p in tc if _local(p.tag) == "p").strip()
                        cells.append(A.table_cell([A.text(txt)]))
                    if cells:
                        rows.append(A.table_row(cells))
                if rows:
                    header = rows[0] if False else None  # DOCX has no header flag; body only
                    blocks.append(A.table(header, rows))
            elif kind in ("sectPr",):
                continue
            if len(blocks) > L.MAX_DOCUMENT_NODES:
                raise AdapterError("TRACE_LIMIT: DOCX exceeds node budget",
                                   code="AC-ADP-237")
        # word/media images → CAS
        for info in zf.infolist():
            if info.filename.startswith("word/media/") and not info.is_dir():
                with zf.open(info.filename) as fh:
                    blob = fh.read(L.MAX_ASSET_BYTES + 1)
                if len(blob) > L.MAX_ASSET_BYTES:
                    warnings.append(f"asset skipped (oversize): {info.filename}")
                    continue
                if put is not None:
                    put(blob)
                images += 1
        history = [{"parser": PARSER_NAME, "version": PARSER_VERSION, "source": filename,
                    "math_findings": math_count, "images": images, "tables": tables}]
        doc = A.Document(A.Metadata(title=meta["title"], author=meta["author"],
                                    origin="docx"), tuple(history), tuple(blocks))
        return doc, warnings
    finally:
        zf.close()


def parse_docx_path(path, put=None) -> tuple[A.Document, list[str]]:
    with open(path, "rb") as fh:
        return parse_docx(fh.read(), put, filename=str(path))
