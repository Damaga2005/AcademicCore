"""AST → HTML renderer (Phase 3, REWRITE). Safe escaping, no JavaScript."""

from __future__ import annotations

from html import escape

_INLINE = {"text", "emphasis", "strong", "link", "inline_code", "image", "equation"}


def _any_block(n) -> str:
    if n.kind in _INLINE:
        return _inline(n)
    return _block(n)


def render(doc) -> str:
    return '<div class="document">\n' + "\n".join(_block(c) for c in doc.children) + "\n</div>"


def _inline(n) -> str:
    k, a = n.kind, n.attrs
    if k == "text":
        return escape(a["value"])
    if k == "emphasis":
        return f"<em>{''.join(_inline(c) for c in n.children)}</em>"
    if k == "strong":
        return f"<strong>{''.join(_inline(c) for c in n.children)}</strong>"
    if k == "inline_code":
        return f"<code>{escape(a['code'])}</code>"
    if k == "link":
        target = a.get("target", "")
        if target.strip().lower().startswith("javascript:"):
            return "".join(_inline(c) for c in n.children)  # drop dangerous href
        title = f' title="{escape(a["title"])}"' if a.get("title") else ""
        return f'<a href="{escape(target)}"{title}>' + "".join(_inline(c) for c in n.children) + "</a>"
    if k == "image":
        ref = escape(a.get("blob_ref") or a.get("title") or "")
        return f'<img src="{ref}" alt="{escape(a.get("alt", ""))}"/>'
    if k == "equation":
        cls = "math-display" if a.get("display") else "math-inline"
        return f'<span class="{cls}">{escape(a["source"])}</span>'
    return "".join(_inline(c) for c in n.children)


def _block(n) -> str:
    k, a = n.kind, n.attrs
    if k == "heading":
        return f"<h{a['level']}>{''.join(_inline(c) for c in n.children)}</h{a['level']}>"
    if k == "paragraph":
        return f"<p>{''.join(_inline(c) for c in n.children)}</p>"
    if k == "quote":
        return "<blockquote>\n" + "\n".join(_block(c) for c in n.children) + "\n</blockquote>"
    if k == "list":
        tag = "ol" if a.get("ordered") else "ul"
        return f"<{tag}>\n" + "\n".join(_block(c) for c in n.children) + f"\n</{tag}>"
    if k == "list_item":
        return "<li>" + "\n".join(_any_block(c) for c in n.children) + "</li>"
    if k == "code_block":
        lang = f' class="language-{escape(a["language"])}"' if a.get("language") else ""
        return f"<pre><code{lang}>{escape(a.get('code', ''))}</code></pre>"
    if k == "thematic_break":
        return "<hr/>"
    if k == "table":
        parts = ["<table>"]
        kids = list(n.children)
        if kids and all(c.attrs.get("header") for c in kids[0].children):
            parts.append("<thead><tr>" + "".join(_hcell(c) for c in kids[0].children) + "</tr></thead>")
            kids = kids[1:]
        parts.append("<tbody>")
        for r in kids:
            tds = []
            for c in r.children:
                at = c.attrs
                span = (f' colspan="{at["colspan"]}"' if at.get("colspan", 1) > 1 else "") + \
                       (f' rowspan="{at["rowspan"]}"' if at.get("rowspan", 1) > 1 else "")
                align = f' style="text-align:{at["align"]}"' if at.get("align") else ""
                tag = "th" if at.get("header") else "td"
                tds.append(f"<{tag}{span}{align}>" + "".join(_inline(k) for k in c.children) + f"</{tag}>")
            parts.append("<tr>" + "".join(tds) + "</tr>")
        parts.append("</tbody></table>")
        return "\n".join(parts)
    if k == "section":
        title = f"<h2>{escape(a['title'])}</h2>\n" if a.get("title") else ""
        return f"<section>\n{title}" + "\n".join(_block(c) for c in n.children) + "\n</section>"
    return "\n".join(_block(c) for c in n.children)


def _hcell(c) -> str:
    return f"<th>{''.join(_inline(k) for k in c.children)}</th>"
