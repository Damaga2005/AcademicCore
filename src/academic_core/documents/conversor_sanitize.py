"""Sanitize + metadata ADAPTED from Conversor-HTML-A-MD (CONVERSOR-REUSE-MAP.md).

Provenance: `clean_soup_noise` L620–638 + `extract_metadata` L1139–1168,
MIT © 2026 Damaga2005, adapted 2026-09-12 (pure functions, no Tk).
Complements (not replaces) the F2 stdlib HTML text adapter: this layer runs
BEFORE AST conversion with full bs4 semantics.
"""

from __future__ import annotations

import re


def _is_javascript_scheme(target: str) -> bool:
    """True if `target` resolves to a javascript: URL once whitespace/control
    characters (which browsers ignore when scheme-matching) are stripped out."""
    return re.sub(r"[\x00-\x20]", "", target.lower()).startswith("javascript:")


def clean_soup_noise(soup):
    """Drop comments, script/style/noscript, hidden and cookie/chrome nodes."""
    from bs4 import Comment
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for el in soup.find_all(attrs={"aria-hidden": "true"}):
        if not any("katex" in c.lower() for c in el.get("class", [])):
            el.decompose()
    for el in soup.find_all(
            lambda t: t.has_attr("style") and (
                "display:none" in t["style"].replace(" ", "").lower()
                or "visibility:hidden" in t["style"].replace(" ", "").lower())):
        el.decompose()
    for el in soup.find_all(
            lambda t: t.has_attr("class") and any(
                "cookie" in c.lower() or "gdpr" in c.lower() or "popup-modal" in c.lower()
                for c in (t["class"] if isinstance(t["class"], list) else [t["class"]]))):
        el.decompose()
    # Event handlers + javascript: URLs never survive into the AST.
    for el in soup.find_all(True):
        for attr in [a for a in el.attrs if a.lower().startswith("on")]:
            del el.attrs[attr]
        for attr in ("href", "src", "action"):
            if isinstance(el.get(attr), str) and _is_javascript_scheme(el[attr]):
                del el.attrs[attr]
    return soup


def extract_metadata(soup) -> dict:
    meta: dict = {}
    title_tag = soup.find("title")
    og_title = soup.find("meta", property="og:title")
    meta_title = soup.find("meta", attrs={"name": "title"})
    if og_title and og_title.get("content"):
        meta["title"] = og_title["content"].strip()
    elif meta_title and meta_title.get("content"):
        meta["title"] = meta_title["content"].strip()
    elif title_tag and title_tag.string:
        meta["title"] = title_tag.string.strip()
    author = soup.find("meta", attrs={"name": re.compile(r"author", re.I)}) \
        or soup.find(class_=re.compile(r"author", re.I))
    if author:
        meta["author"] = author.get("content", "") or author.get_text().strip()
    date = soup.find("meta", attrs={"name": re.compile(r"date|publish", re.I)}) \
        or soup.find("time")
    if date:
        meta["date"] = date.get("content", "") or date.get("datetime", "") \
            or date.get_text().strip()
    desc = soup.find("meta", attrs={"name": "description"}) \
        or soup.find("meta", property="og:description")
    if desc and desc.get("content"):
        meta["description"] = desc["content"].strip()
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        meta["source"] = canonical["href"].strip()
    lang = soup.find("html")
    if lang and lang.get("lang"):
        meta["language"] = lang.get("lang").strip()
    return meta
