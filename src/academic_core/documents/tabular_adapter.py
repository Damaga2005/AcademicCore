# SPDX-License-Identifier: MIT
"""CSV/XLSX → Document AST adapter (F3.1 §30): stdlib-only, no macros.

CSV: stdlib dialect sniff + encoding fallbacks + row/col caps.
XLSX: minimal stdlib ZIP+XML reader (sharedStrings + sheets, values only).
Excel formulas are DATA (cached value shown, formula text preserved in
parentheses) unless an explicit computation contract exists (none in F3).
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET

from academic_core.documents import ast as A
from academic_core.documents import limits as L
from academic_core.documents.office_security import read_zip_member, safe_open_zip
from academic_core.errors import AdapterError, ValidationError

PARSER_NAME = "tabular-adapter"
PARSER_VERSION = "1.0"

MAX_ROWS = 5_000
MAX_COLS = 100


def _rows_to_table(rows: list[list[str]], caption: str = "") -> A.Node | None:
    rows = [r[:MAX_COLS] for r in rows[:MAX_ROWS]]
    if not rows:
        return None
    header = A.table_row([A.table_cell([A.text(c)], header=True) for c in rows[0]])
    body = [A.table_row([A.table_cell([A.text(c)]) for c in r]) for r in rows[1:]]
    return A.table(header, body, caption=caption)


def parse_csv(data: bytes, filename: str = "") -> tuple[A.Document, list[str]]:
    warnings: list[str] = []
    if len(data) > L.MAX_ZIP_MEMBER_BYTES:
        raise AdapterError("TRACE_LIMIT: CSV too large", code="AC-ADP-250")
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValidationError("MALFORMED_CSV: undecodable", code="AC-VAL-250")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [[c.strip() for c in r] for r in reader if any((c or "").strip() for c in r)]
    if len(rows) > MAX_ROWS:
        warnings.append(f"rows truncated ({len(rows)} → {MAX_ROWS})")
        rows = rows[:MAX_ROWS]
    table = _rows_to_table(rows, caption=filename)
    blocks = [table] if table is not None else []
    history = [{"parser": PARSER_NAME, "version": PARSER_VERSION, "source": filename,
                "format": "csv", "rows": len(rows)}]
    return A.Document(A.Metadata(origin="csv"), tuple(history), tuple(blocks)), warnings


def _xlsx_shared_strings(zf) -> list[str]:
    try:
        raw = read_zip_member(zf, "xl/sharedStrings.xml")
    except ValidationError:
        return []
    if b"<!ENTITY" in raw.upper() or b"<!DOCTYPE" in raw.upper():
        raise AdapterError("SECURITY: XLSX strings with ENTITY rejected",
                           code="AC-ADP-251")
    out = []
    for el in ET.fromstring(raw).iter():
        if el.tag.endswith("}t") and el.text:
            out.append(el.text)
    return out


def parse_xlsx(data: bytes, filename: str = "") -> tuple[A.Document, list[str]]:
    warnings: list[str] = []
    zf = safe_open_zip(data, kind="xlsx")
    try:
        strings = _xlsx_shared_strings(zf)
        try:
            wb_raw = read_zip_member(zf, "xl/workbook.xml")
        except ValidationError as e:
            raise ValidationError(f"MALFORMED_XLSX: {e}", code="AC-VAL-251") from None
        sheets: list[tuple[str, str]] = []
        for el in ET.fromstring(wb_raw).iter():
            if el.tag.endswith("}sheet"):
                sheets.append((el.get("name", "Sheet"),
                               el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")))
        try:
            rels_raw = read_zip_member(zf, "xl/_rels/workbook.xml.rels")
            targets = {el.get("Id", ""): el.get("Target", "")
                       for el in ET.fromstring(rels_raw).iter() if el.tag.endswith("}Relationship")}
        except ValidationError:
            targets = {}
        blocks: list[A.Node] = []
        for name, rid in sheets[:50]:
            target = targets.get(rid, "")
            m = re.search(r"(worksheets/sheet\d+\.xml)\Z", target)
            if not m:
                warnings.append(f"sheet {name!r} target unresolved (skipped)")
                continue
            try:
                sheet_raw = read_zip_member(zf, f"xl/{m.group(1)}")
            except ValidationError:
                warnings.append(f"sheet {name!r} unreadable (skipped)")
                continue
            grid: dict[tuple[int, int], str] = {}
            for el in ET.fromstring(sheet_raw).iter():
                if not el.tag.endswith("}c"):
                    continue
                ref = el.get("r", "A1")
                col = sum((ord(ch) - 64) * (26 ** i)
                          for i, ch in enumerate(reversed("".join(filter(str.isalpha, ref))))) - 1
                row = int("".join(filter(str.isdigit, ref)) or 1) - 1
                if col >= MAX_COLS or row >= MAX_ROWS:
                    continue
                ctype = el.get("t", "")
                formula = v_text = ""
                for g in el:
                    if g.tag.endswith("}f") and g.text:
                        formula = g.text.strip()
                    if g.tag.endswith("}v") and g.text:
                        v_text = g.text.strip()
                if ctype == "s" and v_text.isdigit() and int(v_text) < len(strings):
                    value = strings[int(v_text)]
                else:
                    value = v_text
                if formula:
                    value = f"{value} (={formula})" if value else f"={formula}"
                grid[(row, col)] = value
            if not grid:
                warnings.append(f"sheet {name!r} empty (skipped)")
                continue
            max_r = min(max(r for r, _ in grid) + 1, MAX_ROWS)
            max_c = min(max(c for _, c in grid) + 1, MAX_COLS)
            rows = [[grid.get((r, c), "") for c in range(max_c)] for r in range(max_r)]
            table = _rows_to_table(rows, caption=f"Sheet: {name}")
            if table is not None:
                blocks.append(A.paragraph([A.strong([A.text(f"Sheet: {name}")])]))
                blocks.append(table)
        history = [{"parser": PARSER_NAME, "version": PARSER_VERSION, "source": filename,
                    "format": "xlsx", "sheets": len(blocks) // 2}]
        return A.Document(A.Metadata(origin="xlsx"), tuple(history), tuple(blocks)), warnings
    finally:
        zf.close()


def parse_tabular(data: bytes, filename: str = "") -> tuple[A.Document, list[str]]:
    low = (filename or "").lower()
    if low.endswith(".csv"):
        return parse_csv(data, filename)
    if low.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(data, filename)
    raise ValidationError("UNSUPPORTED_FORMAT: expected .csv/.xlsx",
                          code="AC-UNS-250")
