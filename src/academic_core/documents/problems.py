# SPDX-License-Identifier: MIT
"""Problem extraction with provenance (F3.1 §13-14): heuristic, never truth.

Multilingual headers ES/CA/EN. Output preserves raw source + normalized
view + provenance + heuristic flag. Numeric parsing is conservative:
`numeric_value` is set ONLY for unambiguous dot-decimal literals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADER = re.compile(
    r"(?im)^(?:#{1,4}\s*)?(problema|probleme|problem|ejercicio|exercici|exercise|"
    r"cuesti[oó]n|q[üu]esti[oó]|question)\s*([0-9]+(?:\.[0-9]+)?)?\s*:?\s*(.{0,120})$")
SOLUTION_SPLIT = re.compile(
    r"(?im)^(?:#{1,4}\s*)?(soluci[oó]n|solució|solution|resoluci[oó]|resolució|resolucao|"
    r"paso a paso|step[- ]by[- ]step)\b\s*:?\s*(.*)$")
PARAM = re.compile(
    r"(?m)\b([A-Za-z][A-Za-z0-9_]{0,9})\s*=\s*([-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)"
    r"\s*([a-zA-ZΩµμ°%\/]{0,8})")
# Electronics shorthand (4k7, 2u2): raw preserved, never a float.
SHORTHAND = re.compile(r"(?m)\b([A-Za-z][A-Za-z0-9_]{0,9})\s*=\s*(\d+[a-zA-Z]\d+[a-zA-Z0-9]*)")
QUESTION = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)]|[a-dA-D][.)])\s+(.{10,400})$")
BOXED = re.compile(r"\\boxed\{([^{}]{1,200})\}")
RESULT_LINE = re.compile(r"(?im)^.*\*\*(resultado|respuesta|solución final|answer|result)\*\*.*$")
_NUM = re.compile(r"^[-+]?\d+\.\d+$|^[-+]?\d+$")


@dataclass(frozen=True)
class ProblemParameter:
    name: str
    raw_value: str
    unit: str = ""
    numeric_value: float | None = None


@dataclass(frozen=True)
class ExtractedProblem:
    pid: str
    title: str
    statement: str
    parameters: tuple = field(default_factory=tuple)
    questions: tuple = field(default_factory=tuple)
    solution: str = ""
    boxed_answers: tuple = field(default_factory=tuple)
    source: str = ""
    locator: str = ""
    heuristic: bool = True


def _params(block: str) -> list[ProblemParameter]:
    out = []
    taken: list[tuple[int, int]] = []
    for m in SHORTHAND.finditer(block):
        out.append(ProblemParameter(m.group(1), m.group(2), "", None))
        taken.append(m.span())
    for m in PARAM.finditer(block):
        if any(s <= m.start() < e for s, e in taken):
            continue
        name, raw, unit = m.group(1), m.group(2), m.group(3)
        if name.lower() in ("de", "el", "la", "en", "un", "se", "del", "los", "las"):
            continue
        numeric = None
        if _NUM.match(raw):
            try:
                numeric = float(raw)
            except ValueError:
                numeric = None
        out.append(ProblemParameter(name, raw, unit, numeric))
    return out


def extract_problems_from_text(text: str, source: str = "") -> list[ExtractedProblem]:
    matches = list(HEADER.finditer(text or ""))
    if not matches:
        return []
    out = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[m.start():end]
        kind, num, title = m.group(1), m.group(2) or "", m.group(3).strip()
        pid = f"{kind} {num}".strip() or f"{kind}-{idx + 1}"
        sm = SOLUTION_SPLIT.search(block)
        statement = block[:sm.start()].strip() if sm else block.strip()
        solution = ((sm.group(2) + "\n" + block[sm.end():]).strip()
                    if sm else "")
        # strip header line from statement
        statement = re.sub(r"(?im)^.*(problema|ejercicio|exercise|question).{0,120}$",
                           "", statement, count=1).strip()
        questions = [q.strip() for q in QUESTION.findall(statement)[:20]]
        boxed = tuple(BOXED.findall(solution or block)[:10])
        params = tuple(_params(statement)[:40])
        out.append(ExtractedProblem(pid, title or pid, statement, params,
                                   tuple(questions), solution, boxed, source,
                                   f"text:{m.start()}", True))
        if len(out) >= 1000:
            break
    return out


def extract_problems_from_document(doc, source: str = "") -> list[ExtractedProblem]:
    """Flatten AST text in document order, then apply the text extractor."""
    parts: list[str] = []

    def walk(n) -> None:
        if n.kind == "heading":
            parts.append("\n## " + "".join(
                c.attrs.get("value", "") for c in n.children if c.kind == "text"))
        elif n.kind == "text":
            parts.append(n.attrs.get("value", ""))
        elif n.kind == "equation":
            parts.append(f"$${n.attrs.get('source', '')}$$")
        for c in n.children:
            if n.kind not in ("heading", "text"):
                walk(c)

    for c in doc.children:
        walk(c)
    return extract_problems_from_text("\n".join(parts), source or "ast")
