# SPDX-License-Identifier: MIT
"""Deterministic slugs + TOC (F3.1 §25): NFKD, GitHub-compatible, stable collisions."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, existing: dict[str, int] | None = None) -> str:
    """GitHub-style slug: NFKD strip accents, lower, drop punctuation, spaces→hyphens.

    Collisions resolve deterministically: `heading`, `heading-1`, `heading-2`.
    """
    norm = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\s-]", "", norm.lower()).strip()
    slug = re.sub(r"[\s]+", "-", slug).strip("-") or "section"
    if existing is None:
        return slug
    n = existing.get(slug, 0)
    existing[slug] = n + 1
    return slug if n == 0 else f"{slug}-{n}"


def toc_entries(doc) -> list[tuple[int, str, str]]:
    """[(level, title, slug)] in document order (headings 1-4 + section titles)."""
    seen: dict[str, int] = {}
    out: list[tuple[int, str, str]] = []

    def text_of(n) -> str:
        parts: list[str] = []

        def walk(x) -> None:
            if x.kind == "text":
                parts.append(x.attrs.get("value", ""))
            for c in x.children:
                walk(c)
        walk(n)
        return "".join(parts).strip()

    def walk(n) -> None:
        if n.kind == "heading":
            title = text_of(n)
            if title:
                out.append((n.attrs.get("level", 1), title, slugify(title, seen)))
        elif n.kind == "section" and n.attrs.get("title"):
            out.append((2, n.attrs["title"], slugify(n.attrs["title"], seen)))
        for c in n.children:
            walk(c)

    for c in doc.children:
        walk(c)
    return out


def render_toc(doc) -> str:
    entries = toc_entries(doc)
    if len(entries) < 3:
        return ""
    lines = ["## Table of contents", ""]
    for level, title, slug in entries:
        indent = "  " * max(0, level - 2)
        lines.append(f"{indent}- [{title}](#{slug})")
    return "\n".join(lines) + "\n"
