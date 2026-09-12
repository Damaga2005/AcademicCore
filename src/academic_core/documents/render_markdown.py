"""AST → Markdown renderer (Phase 3, REWRITE). Deterministic output."""

from __future__ import annotations

_INLINE = {"text", "emphasis", "strong", "link", "inline_code", "image", "equation"}


def _any_block(n) -> str:
    """Render a child that may be a block or bare inline (list items)."""
    if n.kind in _INLINE:
        return _inline(n)
    return _block(n)


def render(doc) -> str:
    return "\n\n".join(_block(c) for c in doc.children) + ("\n" if doc.children else "")


def _inline(n) -> str:
    k, a = n.kind, n.attrs
    if k == "text":
        return a["value"]
    if k == "emphasis":
        return f"*{''.join(_inline(c) for c in n.children)}*"
    if k == "strong":
        return f"**{''.join(_inline(c) for c in n.children)}**"
    if k == "inline_code":
        return f"`{a['code']}`"
    if k == "link":
        inner = "".join(_inline(c) for c in n.children)
        title = f' "{a["title"]}"' if a.get("title") else ""
        return f"[{inner}]({a['target']}{title})"
    if k == "image":
        ref = a.get("blob_ref") or a.get("title") or ""
        return f"![{a.get('alt', '')}]({ref})"
    if k == "equation":
        return f"$${a['source']}$$" if a.get("display") else f"${a['source']}$"
    return "".join(_inline(c) for c in n.children)


def _block(n) -> str:
    k, a = n.kind, n.attrs
    if k == "heading":
        return f"{'#' * a['level']} {''.join(_inline(c) for c in n.children)}"
    if k == "paragraph":
        return "".join(_inline(c) for c in n.children)
    if k == "quote":
        return "\n".join("> " + line for line in
                         "\n\n".join(_block(c) for c in n.children).splitlines())
    if k == "list":
        out = []
        for i, item in enumerate(n.children):
            body = "\n".join(_any_block(c) for c in item.children).replace("\n", "\n  ")
            out.append(f"{i + 1}. {body}" if a.get("ordered") else f"- {body}")
        return "\n".join(out)
    if k == "list_item":
        return "\n".join(_any_block(c) for c in n.children)
    if k == "code_block":
        return f"```{a.get('language', '')}\n{a.get('code', '')}\n```"
    if k == "thematic_break":
        return "---"
    if k == "table":
        rows = []
        kids = list(n.children)
        header = kids[0] if kids and all(
            c.attrs.get("header") for c in kids[0].children) else None
        body = kids[1:] if header is not None else kids
        if header is not None:
            rows.append("| " + " | ".join(_cell(c) for c in header.children) + " |")
            rows.append("| " + " | ".join("---" for _ in header.children) + " |")
        for r in body:
            rows.append("| " + " | ".join(_cell(c) for c in r.children) + " |")
        cap = f"\n\n*{a['caption']}*" if a.get("caption") else ""
        return "\n".join(rows) + cap
    if k == "section":
        inner = "\n\n".join(_block(c) for c in n.children)
        return f"## {a.get('title', '')}\n\n{inner}" if a.get("title") else inner
    return "\n\n".join(_block(c) for c in n.children)


def _cell(c) -> str:
    s = "".join(_inline(k) for k in c.children).replace("\n", "<br>").replace("|", "\\|")
    if c.attrs.get("colspan", 1) > 1 or c.attrs.get("rowspan", 1) > 1:
        s += f" (×{c.attrs['colspan']} ↕{c.attrs['rowspan']})"
    return s.strip()
