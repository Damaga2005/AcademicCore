# SPDX-License-Identifier: MIT
"""Formula extraction with provenance (F3.1 §11-12): structured, not strings.

Operates on Markdown/text and on the canonical AST (equation nodes).
HTML/MathML/OMML sources feed in via the importers (which already produce
equation nodes); this module never parses XML itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from academic_core.documents.latex_norm import NORMALIZATION_VERSION, clean_latex_formula

_PATTERNS = [
    (re.compile(r"\$\$(.+?)\$\$", re.DOTALL), True),
    (re.compile(r"\\\[(.+?)\\\]", re.DOTALL), True),
    (re.compile(r"\\\((.+?)\\\)", re.DOTALL), False),
]
_INLINE_DOLLAR = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\\)\$(?!\$)", re.DOTALL)
_INLINE_HINT = re.compile(r"=|\\frac|\\sqrt|\\int|\\sum|\\alpha|\\beta|\\Delta|\\cdot|\\times")


@dataclass(frozen=True)
class ExtractedFormula:
    formula: str
    source: str = ""
    locator: str = ""
    format: str = "latex"
    normalization_version: str = NORMALIZATION_VERSION
    heuristic: bool = False


def canonical_formula(tex: str) -> str:
    """Canonical key for dedup: normalized + whitespace-collapsed (not aggressive)."""
    t = clean_latex_formula(tex, decimal_comma=False, frac_aggressive=False)
    return re.sub(r"\s+", "", t)


def _clean(tex: str) -> str:
    return clean_latex_formula(tex)


def extract_from_markdown(text: str, source: str = "") -> list[ExtractedFormula]:
    out: list[ExtractedFormula] = []
    for rx, display in _PATTERNS:
        for i, m in enumerate(rx.finditer(text or "")):
            raw = m.group(1).strip()
            if len(raw) < 1 or len(raw) > 4000:
                continue
            if "http" in raw[:8] or raw.startswith("!"):
                continue
            out.append(ExtractedFormula(_clean(raw), source, f"md:{i}", "latex",
                                       NORMALIZATION_VERSION, display is False))
    for i, m in enumerate(_INLINE_DOLLAR.finditer(text or "")):
        raw = m.group(1).strip()
        if len(raw) < 4 or len(raw) > 2000 or not _INLINE_HINT.search(raw):
            continue
        out.append(ExtractedFormula(_clean(raw), source, f"md-inline:{i}", "latex",
                                   NORMALIZATION_VERSION, True))
    return out


def extract_from_document(doc, source: str = "") -> list[ExtractedFormula]:
    """Walk AST equation nodes (plus $ spans missed by parsers are out of scope)."""
    out: list[ExtractedFormula] = []

    def walk(n, path: tuple) -> None:
        if n.kind == "equation":
            src = n.attrs.get("source", "")
            if src.strip():
                loc = "/" + "/".join(map(str, path)) if path else "/"
                out.append(ExtractedFormula(
                    _clean(src), source or doc.meta.source_resource_id or "ast",
                    f"ast{loc}", n.attrs.get("format", "latex"),
                    NORMALIZATION_VERSION, False))
        for i, c in enumerate(n.children):
            walk(c, path + (i,))

    for i, c in enumerate(doc.children):
        walk(c, (i,))
    return out


def deduplicate(items: list[ExtractedFormula]) -> list[ExtractedFormula]:
    """Keep first occurrence per (canonical, source); never merges across sources."""
    seen: set[tuple[str, str]] = set()
    out: list[ExtractedFormula] = []
    for it in items:
        key = (canonical_formula(it.formula), it.source)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def formula_sheet(items: list[ExtractedFormula], title: str = "Formula sheet") -> str:
    """Render a sheet preserving document order (no alphabetical resort)."""
    lines = [f"# {title}", ""]
    for i, it in enumerate(items, 1):
        cell = it.formula.replace("|", r"\|")
        lines.append(f"| {i} | `${cell}$` | {it.source} |")
    if len(items) > 1:
        lines.insert(2, "| Nº | LaTeX | Source |")
        lines.insert(3, "| --- | --- | --- |")
    return "\n".join(lines) + "\n"
