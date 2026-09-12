"""In-document search (Phase 5): deterministic text/headings/metadata hits.

Returns [(path, kind, excerpt)] in document order. Lexical only — no
semantics, no Knowledge Engine.
"""

from __future__ import annotations


def _text_of(node) -> str:
    parts = []

    def walk(n):
        if n.kind in ("text", "inline_code"):
            parts.append(n.attrs.get("value", n.attrs.get("code", "")))
        elif n.kind == "equation":
            parts.append(n.attrs.get("source", ""))
        for c in n.children:
            walk(c)

    walk(node)
    return "".join(parts)


def search_document(doc, query: str, limit: int = 50) -> list[tuple]:
    q = query.casefold()
    if not q:
        return []
    hits: list[tuple] = []
    if q in (doc.meta.title or "").casefold():
        hits.append(((), "metadata", doc.meta.title[:120]))
    for i, block in enumerate(doc.children):
        if len(hits) >= limit:
            break
        if block.kind == "heading":
            text = _text_of(block)
            if q in text.casefold():
                hits.append(((i,), "heading", text[:120]))
            continue
        text = _text_of(block)
        low = text.casefold()
        start = 0
        while len(hits) < limit:
            at = low.find(q, start)
            if at < 0:
                break
            lo, hi = max(0, at - 30), at + len(q) + 30
            hits.append(((i,), block.kind, text[lo:hi].replace("\n", " ")))
            start = at + len(q)
    return hits
