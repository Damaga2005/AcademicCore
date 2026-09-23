# SPDX-License-Identifier: MIT
"""AST → LaTeX renderer (F3.1 §42): deterministic, no external calls.

Covers equations, tables, figures, captions, callouts (quote + [!TYPE]),
headings, code, links, footnotes-as-links. Declares only what tests prove.
"""

from __future__ import annotations

_LATEX_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
                  "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
                  "}": r"\}", "~": r"\textasciitilde{}",
                  "^": r"\textasciicircum{}"}


def escape(s: str) -> str:
    return "".join(_LATEX_ESCAPES.get(c, c) for c in s or "")


def render(doc) -> str:
    parts = ["% AcademicCore F3-ext LaTeX (deterministic)"]
    for c in doc.children:
        parts.append(_block(c))
    return "\n\n".join(p for p in parts if p) + "\n"


def _inline(n) -> str:
    k, a = n.kind, n.attrs
    if k == "text":
        return escape(a.get("value", ""))
    if k == "emphasis":
        return f"\\emph{{{''.join(_inline(c) for c in n.children)}}}"
    if k == "strong":
        return f"\\textbf{{{''.join(_inline(c) for c in n.children)}}}"
    if k == "inline_code":
        return f"\\texttt{{{escape(a.get('code', ''))}}}"
    if k == "link":
        inner = "".join(_inline(c) for c in n.children)
        target = a.get("target", "")
        if target.startswith("#"):
            return f"{inner}\\footnote{{\\texttt{{{escape(target)}}}}}"
        return f"\\href{{{escape(target)}}}{{{inner}}}"
    if k == "image":
        ref = a.get("blob_ref") or a.get("title") or "image"
        alt = escape(a.get("alt", ""))
        return f"% figure {escape(ref)}\n\\includegraphics{{{escape(ref)}}}% {alt}"
    if k == "equation":
        src = a.get("source", "")
        return f"\\[{src}\\]" if a.get("display") else f"${src}$"
    return "".join(_inline(c) for c in n.children)


def _block(n) -> str:
    k, a = n.kind, n.attrs
    if k == "heading":
        cmd = {1: "section", 2: "subsection", 3: "subsubsection"}.get(a.get("level", 1), "paragraph")
        return f"\\{cmd}*{{{''.join(_inline(c) for c in n.children)}}}"
    if k == "paragraph":
        return "".join(_inline(c) for c in n.children)
    if k == "quote":
        kids = list(n.children)
        tag = ""
        if kids and kids[0].kind == "paragraph":
            first = "".join(_inline(c) for c in kids[0].children).strip()
            if first.startswith("[!") and "]" in first:
                tag = first[2:first.index("]")]
                kids = kids[1:]
        body = "\n\n".join(_block(c) for c in kids)
        label = f"\\textbf{{[{escape(tag)}]}} " if tag else ""
        return f"\\begin{{quote}}\n{label}{body}\n\\end{{quote}}"
    if k == "list":
        env = "enumerate" if a.get("ordered") else "itemize"
        items = "\n".join(f"\\item {_block_item(it)}" for it in n.children)
        return f"\\begin{{{env}}}\n{items}\n\\end{{{env}}}"
    if k == "list_item":
        return "\n".join(_block(c) for c in n.children)
    if k == "code_block":
        lang = f"[{escape(a.get('language', ''))}]" if a.get("language") else ""
        return f"\\begin{{verbatim}}{lang}\n{a.get('code', '')}\n\\end{{verbatim}}"
    if k == "thematic_break":
        return "\\hrule"
    if k == "table":
        kids = list(n.children)
        ncols = max((len(r.children) for r in kids), default=0)
        spec = "l" * max(ncols, 1)
        rows = []
        for r in kids:
            cells = " & ".join("".join(_inline(x) for x in c.children) for c in r.children)
            rows.append(f"{cells} \\\\")
        cap = f"\n% caption: {escape(a['caption'])}" if a.get("caption") else ""
        return f"\\begin{{tabular}}{{{spec}}}\n" + "\n".join(rows) + f"\n\\end{{tabular}}{cap}"
    if k == "section":
        title = f"\\subsection*{{{escape(a.get('title', ''))}}}\n" if a.get("title") else ""
        return title + "\n\n".join(_block(c) for c in n.children)
    return "\n\n".join(_block(c) for c in n.children)


def _block_item(it) -> str:
    parts = []
    for c in it.children:
        if c.kind in ("paragraph", "heading", "quote", "code_block", "table",
                      "list", "thematic_break", "section"):
            parts.append(_block(c))
        else:
            parts.append(_inline(c))
    return " ".join(parts)
