# SPDX-License-Identifier: MIT
"""Teaching-guide (guía docente) extraction — F4.1 port of Gestion
`guia_docente.py` (heuristic, 100 % local, text only).

Input is plain text (normally produced from the F3/F3.1 Document AST of an
imported resource, so provenance is the resource id/version/content hash).
Output is a *proposal*: nothing here writes anything, and every weight that
was derived from a formula instead of read literally is flagged
``needs_review``. The heuristic never invents a weight: formulas that do
not sum to 100 % (±1.5) are not proposed.

Separation from data: this module knows the section headings of the UPC
teaching-guide template (configurable via ``headings``) but no subject,
professor or degree content.

Bounded: input text and line lengths are capped (no pathological regex
input); all patterns are linear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_TEXT = 2 * 1024 * 1024
MAX_LINE = 4000
SUM_TOLERANCE = 1.5  # percentage points

DEFAULT_HEADINGS = (
    "PROFESORADO", "CAPACIDADES PREVIAS",
    "COMPETENCIAS DE LA TITULACIÓN A LAS QUE CONTRIBUYE LA ASIGNATURA",
    "METODOLOGÍAS DOCENTES", "OBJETIVOS DE APRENDIZAJE DE LA ASIGNATURA",
    "HORAS TOTALES DE DEDICACIÓN DEL ESTUDIANTADO", "CONTENIDOS",
    "SISTEMA DE CALIFICACIÓN", "BIBLIOGRAFÍA", "RECURSOS",
)
GRADING_HEADINGS = ("SISTEMA DE CALIFICACIÓN", "SISTEMA DE CALIFICACION")

_GROUP_LINE = re.compile(r"^(.+?)\s*-\s*(\d+(?:\s*,\s*\d+)*)\s*$")
_WITH_COLON = re.compile(r"^(.+?):\s*(\d+(?:[.,]\d+)?)\s*%\.?\s*$")
_NO_COLON = re.compile(r"^([^:]+?)\s+(\d+(?:[.,]\d+)?)\s*%\.?\s*$")
_ASSIGN = re.compile(r"^([A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ_ ]*?)\s*=\s*(.+)$")
_TERM = re.compile(r"(\d+(?:[.,]\d+)?)\s*\*\s*([A-Za-zÀ-ÿ_]+)")


class SyllabusError(ValueError):
    pass


@dataclass(frozen=True)
class ProposedProfessor:
    name: str
    role: str  # "" when the guide gives none


@dataclass(frozen=True)
class ProposedComponent:
    name: str
    kind: str
    weight: str  # Decimal text
    needs_review: bool


@dataclass(frozen=True)
class ProposedBlock:
    name: str
    weight: str
    needs_review: bool
    components: tuple[ProposedComponent, ...]


@dataclass(frozen=True)
class ProposedScheme:
    name: str
    components: tuple[ProposedComponent, ...]
    blocks: tuple[ProposedBlock, ...] = ()
    needs_review: bool = False
    unparsed_text: str = ""


@dataclass(frozen=True)
class SyllabusProposal:
    professors: tuple[ProposedProfessor, ...]
    schemes: tuple[ProposedScheme, ...]
    provenance: dict = field(default_factory=dict)


def _upper(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().upper()


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _w(value: float) -> str:
    """Weight text with at most 2 decimals, trailing zeros stripped."""
    s = f"{round(value, 2):.2f}".rstrip("0").rstrip(".")
    return s or "0"


def section(text: str, heading: str, headings=DEFAULT_HEADINGS) -> str | None:
    m = re.search(rf"{re.escape(heading)}\s*\n", text)
    if not m:
        return None
    rest = text[m.end():]
    end = len(rest)
    for other in headings:
        if other == heading:
            continue
        n = re.search(rf"\n{re.escape(other)}\s*\n", rest)
        if n and n.start() < end:
            end = n.start()
    return rest[:end].strip()


def infer_kind(name: str) -> str:
    n = _upper((name or "").replace("_", " "))
    if "LABORATOR" in n or "PRACTIC" in n or "PRÁCTIC" in n or re.search(r"\bLAB\b", n):
        return "laboratorio"
    if "FINAL" in n:
        return "examen_final"
    if "PARCIAL" in n or "CONTROL" in n:
        return "parcial"
    if "TEOR" in n:
        return "teoria"
    return "otro"


def professors(text: str, headings=DEFAULT_HEADINGS) -> list[ProposedProfessor]:
    block = section(text, "PROFESORADO", headings)
    if not block:
        return []
    m = re.search(r"Profesorado responsable:[ \t]*([^\n]*)", block)
    responsible = (m.group(1).strip() if m else "") or None
    found: list[list[str]] = []
    if responsible:
        found.append([responsible, ""])
    for line in block.splitlines():
        g = _GROUP_LINE.match(line.strip())
        if not g:
            continue
        name = g.group(1).strip()
        if name.lower().startswith("profesorado responsable"):
            continue
        groups = re.sub(r"\s+", "", g.group(2)).replace(",", ", ")
        label = f"grupos {groups}" if "," in groups else f"grupo {groups}"
        same = next((p for p in found if _upper(p[0]) == _upper(name)), None)
        if same:
            same[1] = f"Responsable ({label})"
        else:
            found.append([name, label.capitalize()])
    return [ProposedProfessor(n, r) for n, r in found]


def _flat_components(block: str) -> tuple[list[ProposedComponent], str]:
    comps, rest = [], []
    for line in block.splitlines():
        clean = line.strip()
        m = _WITH_COLON.match(clean)
        if not m:
            m2 = _NO_COLON.match(clean)
            if m2 and len(m2.group(1).split()) <= 5:
                m = m2
        if m:
            name = m.group(1).strip()
            comps.append(ProposedComponent(name, infer_kind(name), _w(_num(m.group(2))), False))
        else:
            rest.append(line)
    return comps, "\n".join(rest)


def _terms(expr: str) -> list[tuple[float, str]] | None:
    out, rest = [], expr
    for m in _TERM.finditer(expr):
        out.append((_num(m.group(1)), m.group(2)))
        rest = rest.replace(m.group(0), " ", 1)
    if re.sub(r"[+\-\s]", "", rest):
        return None  # unexplained text: not confident
    return out


def _split_max(expr: str) -> list[str]:
    depth, parts, cur = 0, [], []
    for c in expr:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _pretty(var: str) -> str:
    return var.replace("_", " ").strip().capitalize()


def _formula(text: str) -> list[ProposedScheme] | None:
    assigns: dict[str, str] = {}
    order: list[str] = []
    for line in text.splitlines():
        m = _ASSIGN.match(line.strip())
        if m:
            assigns[_upper(m.group(1))] = m.group(2).strip()
            order.append(m.group(1).strip())
    if not order:
        return None
    main_key = _upper(order[0])
    main = assigns[main_key]
    mm = re.search(r"MAX\s*\((.+)\)(.*)", main, re.IGNORECASE)
    alternatives, tail = (_split_max(mm.group(1)), mm.group(2)) if mm else ([main], "")
    tail_terms = _terms(tail) if tail.strip() else []
    if tail.strip() and tail_terms is None:
        return None
    schemes = []
    for alt in alternatives:
        terms = _terms(alt)
        if terms is None:
            return None
        comps, blocks, total = [], [], 0.0
        for coef, var in list(terms) + list(tail_terms):
            definition = assigns.get(_upper(var))
            sub = None
            if definition and _upper(var) != main_key:
                sub = _terms(definition)
                if sub is None:
                    return None
            if sub is None:
                comps.append(ProposedComponent(_pretty(var), infer_kind(var), _w(coef * 100), True))
                total += coef
            elif abs(sum(c for c, _ in sub) * 100 - 100) <= SUM_TOLERANCE:
                blocks.append(ProposedBlock(_pretty(var), _w(coef * 100), True, tuple(
                    ProposedComponent(_pretty(v), infer_kind(v), _w(c * 100), True)
                    for c, v in sub)))
                total += coef
            else:
                return None
        if abs(total * 100 - 100) > SUM_TOLERANCE:
            return None
        if len(alternatives) > 1:
            partial = any("PARCIAL" in _upper(c.name) or "CONTROL" in _upper(c.name)
                          for c in comps)
            name = "Con examen parcial" if partial else "Solo examen final"
        else:
            name = "Evaluación"
        schemes.append(ProposedScheme(name, tuple(comps), tuple(blocks)))
    return schemes


def grading(text: str, headings=DEFAULT_HEADINGS) -> list[ProposedScheme]:
    block = None
    for h in GRADING_HEADINGS:
        block = section(text, h, headings)
        if block:
            break
    if not block:
        return []
    flat, rest = _flat_components(block)
    schemes: list[ProposedScheme] = []
    if flat and abs(sum(float(c.weight) for c in flat) - 100) <= SUM_TOLERANCE:
        schemes.append(ProposedScheme("Evaluación", tuple(flat)))
    else:
        rest = block
    schemes.extend(_formula(rest) or [])
    if not schemes:
        schemes.append(ProposedScheme("Evaluación", (), (), True, block))
    return schemes


def analyze(text: str, *, provenance: dict | None = None,
            headings=DEFAULT_HEADINGS) -> SyllabusProposal:
    if len(text) > MAX_TEXT:
        raise SyllabusError("teaching guide text too large")
    text = "\n".join(line[:MAX_LINE] for line in text.replace("\r\n", "\n").split("\n"))
    return SyllabusProposal(tuple(professors(text, headings)), tuple(grading(text, headings)),
                            dict(provenance or {}))


def document_lines(doc) -> str:
    """Plain text of a Document AST, one line per block-level node (the
    shape the line-oriented heuristics expect)."""
    lines: list[str] = []

    def inline(n) -> str:
        if n.kind in ("text", "inline_code"):
            return n.attrs.get("value", n.attrs.get("code", ""))
        if n.kind == "equation":
            return n.attrs.get("source", "")
        return "".join(inline(c) for c in n.children)

    def walk(n) -> None:
        if n.kind in ("paragraph", "heading", "table_cell", "code_block"):
            if n.kind == "code_block":
                lines.extend(n.attrs.get("code", "").splitlines())
            else:
                lines.extend(inline(n).splitlines() or [""])
            return
        if n.kind == "section" and n.attrs.get("title"):
            lines.append(n.attrs["title"])
        for c in n.children:
            walk(c)

    for child in doc.children:
        walk(child)
    return "\n".join(lines)
