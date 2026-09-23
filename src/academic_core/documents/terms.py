# SPDX-License-Identifier: MIT
"""Heuristic term→definition / question→answer extractors (F3.1 §15-16).

Extraction only: finds pairs ALREADY present in the document. Never
generates questions. Output is F4-ready with provenance (source+locator).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEF = re.compile(r"(?m)^\s*\*\*(.{2,60}?)\*\*\s*:\s*(.{20,600})")
Q_BLOCK = re.compile(
    r"(?ims)^(?:#{1,4}\s*)?(.{8,300}\?)\s*\n+(?:(?:respuesta|solución|solution|answer)\s*:?\s*\n?)?(.{1,800}?)(?=^\s*#{1,4}\s|\Z)")


@dataclass(frozen=True)
class ExtractedTerm:
    term: str
    definition: str
    source: str = ""
    locator: str = ""
    heuristic: bool = True


@dataclass(frozen=True)
class ExtractedQA:
    question: str
    answer: str
    source: str = ""
    locator: str = ""
    heuristic: bool = True


def extract_terms(text: str, source: str = "") -> list[ExtractedTerm]:
    out = []
    for i, m in enumerate(DEF.finditer(text or "")):
        term, definition = m.group(1).strip(), m.group(2).strip()
        if len(term) > 60 or len(definition) < 20:
            continue
        out.append(ExtractedTerm(term, definition, source, f"term:{i}", True))
        if len(out) >= 2000:
            break
    return out


def extract_qa(text: str, source: str = "") -> list[ExtractedQA]:
    out = []
    for i, m in enumerate(Q_BLOCK.finditer(text or "")):
        q, a = m.group(1).strip(), m.group(2).strip()
        if len(a) < 1:
            continue
        out.append(ExtractedQA(q, a, source, f"qa:{i}", True))
        if len(out) >= 1000:
            break
    return out
