"""HTML → Document AST (Phase 3): Conversor-adapted preprocessing + AST walk.

Pipeline: BeautifulSoup(lxml) → clean_soup_noise → callouts → figs harvest →
images→CAS → shield_math → block/inline walk. bs4 lives ONLY in this layer;
output is pure `documents.ast` nodes.
"""

from __future__ import annotations

import re

from academic_core.documents import ast as A
from academic_core.documents.conversor_images import extract_images, harvest_figs_from_scripts
from academic_core.documents.conversor_math import shield_math
from academic_core.documents.conversor_sanitize import clean_soup_noise, extract_metadata

PARSER_NAME = "html-parser"
PARSER_VERSION = "3.0"

CALLOUT_TYPES = {
    "warning": "WARNING", "warn": "WARNING", "alert": "WARNING",
    "danger": "CAUTION", "error": "CAUTION", "caution": "CAUTION",
    "attention": "IMPORTANT", "atencion": "IMPORTANT", "atencio": "IMPORTANT",
    "tip": "TIP", "consejo": "TIP", "note": "NOTE", "nota": "NOTE",
    "info": "NOTE", "important": "IMPORTANT", "importante": "IMPORTANT",
}


def _preprocess_callouts(soup):
    for tag in soup.find_all(["div", "aside"]):
        classes = " ".join(tag.get("class", []) or []).lower()
        found = next((v for k, v in CALLOUT_TYPES.items() if k in classes), None)
        if found:
            tag.name = "blockquote"
            marker = soup.new_tag("p")
            marker.string = f"[!{found}]"
            tag.insert(0, marker)
            tag["class"] = []
    return soup


def parse_html(raw: bytes | str, put=None, filename: str = "") -> A.Document:
    """Parse HTML bytes/str into a Document. `put` stores image blobs in CAS."""
    from bs4 import BeautifulSoup, NavigableString, Tag
    from academic_core.documents.encoding import read_html_bytes
    if isinstance(raw, bytes):
        html, encoding = read_html_bytes(raw)
    else:
        html, encoding = raw, "utf-8-str"
    soup = BeautifulSoup(html, "lxml")
    meta = extract_metadata(soup)
    clean_soup_noise(soup)
    _preprocess_callouts(soup)
    harvest_figs_from_scripts(soup)
    image_records = extract_images(soup, put or (lambda data: "nocas"))
    soup, math = shield_math(soup)

    body = soup.find("body") or soup
    blocks = _blocks(body, math)

    history = [{"parser": PARSER_NAME, "version": PARSER_VERSION,
                "source": filename, "encoding": encoding,
                "math_findings": len(math), "images": len(image_records)}]
    return A.Document(
        A.Metadata(title=meta.get("title", ""), author=meta.get("author", ""),
                   language=meta.get("language", ""),
                   created_at=meta.get("date", ""), origin="html",
                   encoding=encoding,
                   extra={"description": meta.get("description", "")}),
        tuple(history), tuple(blocks))


# -- walk -----------------------------------------------------------------------
def _text_of(node) -> str:
    return node.get_text(separator=" ", strip=True)


def _inline(node, math) -> list:
    from bs4 import NavigableString, Tag
    out = []
    for child in getattr(node, "children", []):
        out.extend(_inline_node(child, math))
    return out


def _inline_node(child, math) -> list:
    from bs4 import NavigableString, Tag
    if isinstance(child, NavigableString):
        s = str(child)
        return [A.text(s)] if s.strip() else []
    if not isinstance(child, Tag):
        return []
    name = child.name.lower()
    if name == "math-shield":
        i = int(child.get("data-i", -1))
        latex, display = math[i] if 0 <= i < len(math) else ("", False)
        return [A.equation(latex, "latex", display)]
    if name in ("em", "i"):
        return [A.emphasis(_inline(child, math))]
    if name in ("strong", "b"):
        return [A.strong(_inline(child, math))]
    if name == "code":
        return [A.inline_code(child.get_text())]
    if name == "a":
        return [A.link(child.get("href", ""), _inline(child, math) or [A.text(child.get_text())])]
    if name == "img":
        src = child.get("src", "")
        m = re.match(r"cas:([0-9a-f]{64})", src or "")
        return [A.image(f"cas:{m.group(1)}" if m else "", child.get("alt", ""), title="" if m else (src or ""))]
    if name == "br":
        return [A.text("\n")]
    if name in ("sub", "sup"):
        inner = _text_of(child)
        mark = "_" if name == "sub" else "^"
        return [A.text(f"{mark}{{{inner}}}")]
    # transparent containers: var, span, font, etc.
    out = []
    for c in child.children:
        out.extend(_inline_node(c, math))
    return out


def _blocks(parent, math) -> list:
    from bs4 import NavigableString, Tag
    from academic_core.documents.conversor_tables import (
        extract_code_cells, table_grid)
    out = []
    for child in parent.children:
        if isinstance(child, NavigableString):
            if child.strip():
                out.append(A.paragraph([A.text(child.strip())]))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in ("script", "style", "noscript"):
            continue
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            out.append(A.heading(int(name[1]), _inline(child, math)))
        elif name == "p":
            kids = _inline(child, math)
            if kids:
                out.append(A.paragraph(kids))
        elif name == "blockquote":
            kids = _blocks(child, math)
            if kids:
                out.append(A.quote(kids))
        elif name in ("ul", "ol"):
            items = []
            for li in child.find_all("li", recursive=False):
                items.append(A.list_item(_blocks(li, math) or [A.paragraph(_inline(li, math))]))
            if items:
                out.append(A.bullet_list(items, ordered=(name == "ol")))
        elif name == "pre":
            code = child.find("code")
            lang = ""
            if code and code.get("class"):
                m = re.search(r"(?:lang(?:uage)?-)([\w+#-]+)", " ".join(code.get("class")), re.I)
                if m:
                    lang = m.group(1).lower()
            out.append(A.code_block(child.get_text().strip("\n"), lang))
        elif name == "table":
            grid, is_code = table_grid(child, lambda cell: _inline(cell, math))
            if is_code:
                lang, code = extract_code_cells(child)
                out.append(A.code_block(code, lang))
            elif grid:
                rows = []
                for r in grid:
                    rows.append(A.table_row([
                        A.table_cell(c["inline"], header=c["header"],
                                     colspan=c["colspan"], rowspan=c["rowspan"],
                                     align=c["align"]) for c in r]))
                first_all_header = all(c["header"] for c in grid[0])
                out.append(A.table(rows[0] if first_all_header else None,
                                   rows[1:] if first_all_header else rows))
        elif name == "img":
            for node in _inline_node(child, math):
                out.append(A.paragraph([node]))
        elif name == "hr":
            out.append(A.thematic_break())
        elif name == "math-shield":
            for node in _inline_node(child, math):
                out.append(A.paragraph([node]))
        elif name == "figure":
            for node in _inline(child, math):
                if node.kind == "image":
                    out.append(A.paragraph([node]))
            cap = child.find("figcaption")
            if cap and cap.get_text(strip=True):
                out.append(A.paragraph([A.emphasis([A.text(cap.get_text(strip=True))])]))
        elif name == "dl":
            items = []
            for dt in child.find_all("dt", recursive=False):
                dd = dt.find_next_sibling("dd")
                label = f"{_text_of(dt)} — {dd.get_text(strip=True)}" if dd else _text_of(dt)
                items.append(A.list_item([A.paragraph([A.text(label)])]))
            if items:
                out.append(A.bullet_list(items))
        elif name == "details":
            kids = []
            summary = child.find("summary")
            if summary:
                kids.append(A.paragraph([A.strong([A.text(summary.get_text(strip=True))])]))
                summary.decompose()
            kids.extend(_blocks(child, math))
            if kids:
                out.append(A.quote(kids))
        elif name in ("div", "section", "article", "main", "aside", "header", "footer", "nav"):
            if any("mermaid" in c.lower() for c in (child.get("class", []) or [])):
                out.append(A.code_block(child.get_text().strip(), "mermaid"))
            else:
                out.extend(_blocks(child, math))
        else:
            # unknown wrappers: descend, never drop text
            sub = _blocks(child, math)
            if sub:
                out.extend(sub)
            else:
                kids = _inline(child, math)
                if kids:
                    out.append(A.paragraph(kids))
    return out
