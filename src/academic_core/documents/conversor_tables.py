"""Table grid ADAPTED from Conversor-HTML-A-MD (CONVERSOR-REUSE-MAP.md).

Provenance: `conversor_html_notebooklm.py` L1175–1293, MIT © 2026 Damaga2005,
adapted 2026-09-12: output is a structural grid (spans preserved as data)
instead of GFM text with `(cont.)` markers; inline formatting defers to the
caller via `inline(cell_tag) -> list[InlineNode]` so math/images survive.
"""

from __future__ import annotations

import re


def is_code_table(table_tag) -> bool:
    classes = " ".join(table_tag.get("class", []) or []).lower()
    if any(k in classes for k in ("highlight", "syntaxhighlighter", "code-table", "blob-wrapper")):
        return True
    cells = table_tag.find_all(["td", "th"])
    cell_classes = " ".join(" ".join(c.get("class", []) or []) for c in cells).lower()
    return (("gutter" in cell_classes or "line-numbers" in cell_classes
             or "hljs-ln-numbers" in cell_classes)
            and ("code" in cell_classes or "blob-code" in cell_classes
                 or "hljs-ln-code" in cell_classes))


def extract_code_cells(table_tag) -> tuple[str, str]:
    """(language, code) from a line-numbered code table."""
    code_cells = table_tag.find_all(
        lambda el: el.name == "td" and any(
            k in " ".join(el.get("class", []) or []).lower()
            for k in ("code", "blob-code", "hljs-ln-code", "lines")))
    if not code_cells:
        code_cells = [td for td in table_tag.find_all("td")
                      if not any(g in " ".join(td.get("class", []) or []).lower()
                                 for g in ("gutter", "line-number", "lineno"))]
    lang = ""
    lines = []
    for c in code_cells:
        pre = c.find("pre") or c
        m = re.search(r"(?:lang(?:uage)?-|brush:\s*)([a-zA-Z0-9_+#-]+)",
                      " ".join(pre.get("class", []) or []), re.I)
        if m:
            lang = m.group(1).lower()
        lines.append(c.get_text().strip("\r\n"))
    return lang, "\n".join(lines)


def _align_of(cell) -> str:
    align = (cell.get("align", "") or "").lower()
    if not align and cell.has_attr("style"):
        s = cell["style"].lower().replace(" ", "")
        for key, val in (("text-align:center", "center"), ("text-align:right", "right"),
                         ("text-align:left", "left")):
            if key in s:
                align = val
                break
    return align if align in ("left", "center", "right") else ""


def table_grid(table_tag, inline) -> tuple[list[list[dict]], bool]:
    """Return (rows, is_code_table). Each cell: {inline, header, colspan,
    rowspan, align}. Spanned continuations are EMPTY with spans recorded —
    no `(cont.)` text injected (structural spans instead)."""
    if is_code_table(table_tag):
        return [], True
    from bs4 import NavigableString, Tag
    grid: dict[tuple[int, int], dict] = {}
    rows = table_tag.find_all("tr")
    for r_idx, row in enumerate(rows):
        c_idx = 0
        for cell in row.find_all(["th", "td"]):
            while (r_idx, c_idx) in grid:
                c_idx += 1
            try:
                rowspan, colspan = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
            except (TypeError, ValueError):
                rowspan, colspan = 1, 1
            rowspan, colspan = max(rowspan, 1), max(colspan, 1)
            kids = inline(cell)
            entry = {"inline": kids, "header": cell.name == "th",
                     "colspan": colspan, "rowspan": rowspan, "align": _align_of(cell)}
            for dr in range(rowspan):
                for dc in range(colspan):
                    grid[(r_idx + dr, c_idx + dc)] = (
                        entry if (dr == 0 and dc == 0)
                        else {"inline": [], "header": False, "colspan": 1,
                              "rowspan": 1, "align": "", "spanned": True})
            c_idx += colspan
    if not grid:
        return [], False
    max_r = max(r for r, _ in grid) + 1
    max_c = max(c for _, c in grid) + 1
    return [[grid.get((r, c), {"inline": [], "header": False, "colspan": 1,
                               "rowspan": 1, "align": ""}) for c in range(max_c)]
            for r in range(max_r)], False
