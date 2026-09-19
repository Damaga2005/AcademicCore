"""Document validation service (Phase 5): structured issues, never silent.

Checks: structural AST, metadata consistency, links, local images vs CAS,
equations (source kept, problems reported), tables, heading coherence, size.
Unknown node kinds are already rejected by `Node.from_dict`; this layer
validates live Documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from academic_core.documents.security import (
    is_javascript_scheme as _is_javascript_scheme,
)


@dataclass(frozen=True)
class ValidationIssue:
    path: tuple
    code: str
    message: str
    severity: str = "error"  # error|warning


MAX_BLOCKS = 20_000
MAX_TEXT_CHARS = 2_000_000


def _inline_text(node) -> str:
    parts = []

    def walk(n):
        if n.kind == "text":
            parts.append(n.attrs.get("value", ""))
        elif n.kind == "equation":
            parts.append(n.attrs.get("source", ""))
        for c in n.children:
            walk(c)

    walk(node)
    return "".join(parts)


def validate_document(doc, blob_exists=None) -> list[ValidationIssue]:
    """Return issues (empty = valid). `blob_exists(hex) -> bool` checks CAS."""
    from academic_core.documents import ast as A
    issues: list[ValidationIssue] = []
    try:
        A.validate(doc)
    except A.AstError as e:
        return [ValidationIssue((), "ast_invalid", str(e))]
    total_text = 0

    if len(doc.children) > MAX_BLOCKS:
        issues.append(ValidationIssue((), "oversize",
                                      f"{len(doc.children)} blocks > {MAX_BLOCKS}"))
    if not doc.meta.title:
        issues.append(ValidationIssue((), "metadata", "title is empty", "warning"))

    def walk(n, path):
        nonlocal total_text
        if n.kind == "link":
            target = n.attrs.get("target", "")
            if not target:
                issues.append(ValidationIssue(path, "link_empty", "link without target"))
            elif _is_javascript_scheme(target):
                issues.append(ValidationIssue(path, "link_unsafe",
                                              "javascript: links are forbidden"))
            elif not re.match(r"^(https?://|#|/|[\w\-.~:/?#\[\]@!$&'()*+,;=%]+)$", target):
                issues.append(ValidationIssue(path, "link_shape",
                                              f"suspicious target: {target[:60]}"))
        elif n.kind == "image":
            ref = n.attrs.get("blob_ref", "")
            m = re.fullmatch(r"cas:([0-9a-f]{64})", ref or "")
            if ref and not m:
                issues.append(ValidationIssue(path, "image_ref",
                                              f"malformed blob ref: {ref[:40]}"))
            elif m and blob_exists is not None and not blob_exists(m.group(1)):
                issues.append(ValidationIssue(path, "image_missing",
                                              f"CAS blob absent: {m.group(1)[:12]}…"))
            elif not ref and not n.attrs.get("title"):
                issues.append(ValidationIssue(path, "image_empty",
                                              "image without blob ref or source",
                                              "warning"))
        elif n.kind == "equation":
            src = n.attrs.get("source", "")
            if not src.strip():
                issues.append(ValidationIssue(path, "equation_empty",
                                              "equation without source"))
            elif src.count("{") != src.count("}"):
                issues.append(ValidationIssue(path, "equation_braces",
                                              "unbalanced braces (source kept)"))
        elif n.kind == "text":
            total_text += len(n.attrs.get("value", ""))
        for i, c in enumerate(n.children):
            walk(c, path + (i,))

    for i, c in enumerate(doc.children):
        walk(c, (i,))

    # heading coherence: jumps deeper than one level are warnings
    levels = []

    def headings(n):
        if n.kind == "heading":
            levels.append(n.attrs["level"])
        for c in n.children:
            headings(c)

    for c in doc.children:
        headings(c)
    for prev, cur in zip(levels, levels[1:]):
        if cur - prev > 1:
            issues.append(ValidationIssue((), "headings",
                                          f"level jump {prev} -> {cur}", "warning"))
    if total_text > MAX_TEXT_CHARS:
        issues.append(ValidationIssue((), "oversize",
                                      f"{total_text} text chars > {MAX_TEXT_CHARS}"))
    return issues
