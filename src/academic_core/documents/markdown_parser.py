"""Markdown → AST (Phase 3, REWRITE — the Conversor has no MD parser).

Supported subset (documented, deterministic): ATX headings, paragraphs,
unordered/ordered lists (single level + nesting by indent), fenced code,
GFM tables, blockquotes, thematic breaks, inline emphasis/strong/code/
links/images, `$inline$` and `$$display$$` math → Equation. Anything else
passes through as paragraph text — never dropped, never executed.
"""

from __future__ import annotations

import re

from academic_core.documents import ast as A

PARSER_NAME = "markdown-parser"
PARSER_VERSION = "3.0"

_MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.DOTALL)
# Inner capture groups are named (not positional): adding or reordering
# an alternative must never silently renumber m.group(N) references
# elsewhere. Behavior is identical to positional groups.
_INLINE_RE = re.compile(
    r"(?P<code>`(?P<code_text>[^`]+)`)"
    r"|(?P<img>!\[(?P<img_alt>[^\]]*)\]\((?P<img_target>[^)\s]+)(?:\s+\"(?P<img_title>[^\"]*)\")?\))"
    r"|(?P<link>\[(?P<link_label>[^\]]+)\]\((?P<link_target>[^)\s]+)(?:\s+\"(?P<link_title>[^\"]*)\")?\))"
    r"|(?P<strongem>\*\*\*(?P<strongem_ast>[^*]+)\*\*\*|___(?P<strongem_us>[^_]+)___)"
    r"|(?P<strong>\*\*(?P<strong_ast>[^*]+)\*\*|__(?P<strong_us>[^_]+)__)"
    r"|(?P<em>\*(?P<em_ast>[^*]+)\*|_(?P<em_us>[^_]+)_)")


def parse_inline(s: str) -> list:
    out, pos = [], 0
    # math first (shielded spans so $ content is never re-processed)
    parts, last, mi = [], 0, 0
    spans = []
    for m in _MATH_RE.finditer(s):
        spans.append((m.start(), m.end(), m.group(1) is not None,
                      m.group(1) if m.group(1) is not None else m.group(2)))
    chunks = []
    for start, end, display, latex in spans:
        chunks.append((s[last:start], None))
        chunks.append(("", (latex, display)))
        last = end
    chunks.append((s[last:], None))

    for text, math in chunks:
        if math:
            latex, display = math
            out.append(A.equation(latex.strip(), "latex", display))
            continue
        out.extend(_inline_md(text))
    return out


def _inline_md(s: str) -> list:
    out, pos = [], 0
    for m in _INLINE_RE.finditer(s):
        if m.start() > pos:
            out.append(A.text(s[pos:m.start()]))
        if m.group("code"):
            out.append(A.inline_code(m.group("code_text")))
        elif m.group("img"):
            target = m.group("img_target")
            if target.startswith("cas:"):
                out.append(A.image(target, m.group("img_alt"), title=m.group("img_title") or ""))
            else:
                out.append(A.image("", m.group("img_alt"), title=target))
        elif m.group("link"):
            label, target = m.group("link_label"), m.group("link_target")
            out.append(A.link(target, parse_inline(label), m.group("link_title") or ""))
        elif m.group("strongem"):
            inner = m.group("strongem_ast") if m.group("strongem_ast") is not None else m.group("strongem_us")
            out.append(A.strong([A.emphasis(parse_inline(inner))]))
        elif m.group("strong"):
            inner = m.group("strong_ast") if m.group("strong_ast") is not None else m.group("strong_us")
            out.append(A.strong(parse_inline(inner)))
        elif m.group("em"):
            inner = m.group("em_ast") if m.group("em_ast") is not None else m.group("em_us")
            out.append(A.emphasis(parse_inline(inner)))
        pos = m.end()
    if pos < len(s):
        out.append(A.text(s[pos:]))
    return [n for n in out if not (n.kind == "text" and n.attrs["value"] == "")]


def _is_table_sep(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return len(cells) >= 1 and all(re.match(r"^:?-{1,}:?$", c) for c in cells)


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_markdown(src: str, filename: str = "") -> A.Document:
    lines = src.splitlines()
    blocks: list = []
    i, title = 0, ""
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            kids = parse_inline(m.group(2).strip())
            if m.group(1) == "#" and not title:
                title = "".join(k.attrs.get("value", "") for k in kids if k.kind == "text")
            blocks.append(A.heading(len(m.group(1)), kids))
            i += 1
            continue
        if re.match(r"^```", line):
            lang = line.strip("`").strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append(A.code_block("\n".join(buf), lang))
            continue
        if re.match(r"^(\*\*\*|---|___)\s*$", line):
            blocks.append(A.thematic_break())
            i += 1
            continue
        if line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i][1:].lstrip())
                i += 1
            sub = parse_markdown("\n".join(buf))
            blocks.append(A.quote(sub.children))
            continue
        if (re.match(r"^(\s*[-*+]\s+)", line) or re.match(r"^(\s*\d+[.)]\s+)", line)):
            items, ordered = [], bool(re.match(r"^\s*\d+[.)]\s+", line))
            while i < len(lines) and (re.match(r"^\s*[-*+]\s+", lines[i])
                                      or re.match(r"^\s*\d+[.)]\s+", lines[i])):
                text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i])
                items.append(A.list_item([A.paragraph(parse_inline(text))]))
                i += 1
            blocks.append(A.bullet_list(items, ordered=ordered))
            continue
        if "|" in line and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            header = A.table_row([A.table_cell(parse_inline(c), header=True)
                                  for c in _split_row(line)])
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(A.table_row([A.table_cell(parse_inline(c))
                                         for c in _split_row(lines[i])]))
                i += 1
            blocks.append(A.table(header, rows))
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|```|>|\s*[-*+]\s+|\s*\d+[.)]\s+|(\*\*\*|---|___)\s*$)", lines[i]):
            if "|" in lines[i] and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
                break
            buf.append(lines[i].strip())
            i += 1
        if buf:
            blocks.append(A.paragraph(parse_inline(" ".join(buf))))
    history = [{"parser": PARSER_NAME, "version": PARSER_VERSION, "source": filename}]
    return A.Document(A.Metadata(title=title, origin="markdown"), tuple(history), tuple(blocks))
