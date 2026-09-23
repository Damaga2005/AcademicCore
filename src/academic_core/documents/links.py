# SPDX-License-Identifier: MIT
"""Deterministic link rewriting (F3.1 §24): exact `.html→.md` + `#anchor`.

No filesystem access, no fuzzy resolution (opt-in fuzzy lives outside the
domain and is OFF by default). Dangerous schemes are left untouched here;
sanitizer/validator/renderer reject them (defense in depth).
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

_HTML_EXT = re.compile(r"\.html?$", re.IGNORECASE)


def rewrite_target(target: str) -> str:
    """Rewrite a single link target deterministically."""
    if not target or target.startswith(("#", "mailto:", "tel:")):
        return target
    low = re.sub(r"[\x00-\x20]", "", target.lower())
    if low.startswith(("javascript:", "data:", "vbscript:")):
        return target  # rejected downstream, never rewritten here
    try:
        parts = urlsplit(target)
    except ValueError:
        return target
    if parts.scheme or parts.netloc:
        return target  # absolute URLs untouched
    path = _HTML_EXT.sub(".md", parts.path)
    anchor = "#" + slug_anchor(parts.fragment) if parts.fragment else ""
    query = ("?" + parts.query) if parts.query else ""
    return f"{path}{query}{anchor}"


def slug_anchor(fragment: str) -> str:
    norm = unicodedata.normalize("NFKD", fragment or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\-_]", "", norm.lower().replace(" ", "-")).strip("-")
    return slug or fragment


def rewrite_soup_links(soup) -> int:
    """Rewrite `<a href>` in place; returns count of rewritten links."""
    n = 0
    for a in soup.find_all("a", href=True):
        new = rewrite_target(a["href"])
        if new != a["href"]:
            a["href"] = new
            n += 1
    return n
