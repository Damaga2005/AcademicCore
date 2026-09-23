# SPDX-License-Identifier: MIT
"""OMML → LaTeX (F3.1 §9): adapted from Conversor `omml_to_latex`.

Covers frac/sup/sub/rad/delim/matrix/nary/lim/accents + cases/borderBox.
Safe XML: stdlib ElementTree (no external entities), explicit depth/node
limits, byte cap. Never executes macros. Stdlib-only: safe in documents layer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from academic_core.documents import limits as L
from academic_core.errors import AdapterError, ValidationError

OMML_OPERATOR_MAP = {
    "∑": r"\sum", "∫": r"\int", "∏": r"\prod", "±": r"\pm", "×": r"\times",
    "÷": r"\div", "·": r"\cdot", "≤": r"\le", "≥": r"\ge", "≠": r"\ne",
    "∈": r"\in", "→": r"\to", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "λ": r"\lambda", "μ": r"\mu", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma",
    "τ": r"\tau", "φ": r"\phi", "ϕ": r"\varphi", "χ": r"\chi", "ψ": r"\psi",
    "ω": r"\omega", "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta",
    "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}

_M_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


class _Budget:
    def __init__(self) -> None:
        self.nodes = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes > L.MAX_XML_NODES:
            raise AdapterError("TRACE_LIMIT: OMML exceeds node budget",
                               code="AC-ADP-221")


def parse_omml_fragment(xml_text: str | bytes) -> ET.Element:
    """Parse an OMML fragment/element safely (raises AdapterError/ValidationError)."""
    if isinstance(xml_text, str):
        raw = xml_text.encode("utf-8", "surrogatepass")
    else:
        raw = bytes(xml_text)
    if len(raw) > L.MAX_ZIP_MEMBER_BYTES:
        raise AdapterError("TRACE_LIMIT: OMML fragment too large", code="AC-ADP-220")
    if b"<!ENTITY" in raw.upper() or b"<!DOCTYPE" in raw.upper():
        raise AdapterError("SECURITY: OMML with DOCTYPE/ENTITY rejected",
                           code="AC-ADP-222")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as e:
        raise ValidationError(f"MALFORMED_OMML: {e}", code="AC-VAL-220") from None


def omml_to_latex(node: ET.Element | None, *, _depth: int = 0,
                  _budget: _Budget | None = None) -> str:
    """Recursive OMML element → LaTeX (pure, deterministic)."""
    if node is None:
        return ""
    if _depth > L.MAX_XML_DEPTH:
        raise AdapterError("TRACE_LIMIT: OMML nesting too deep", code="AC-ADP-223")
    budget = _budget or _Budget()
    budget.tick()

    def kids(tag: ET.Element) -> list[ET.Element]:
        return [c for c in tag if isinstance(c.tag, str)]

    def find_child(tag: ET.Element, *names: str) -> ET.Element | None:
        for c in kids(tag):
            if _local(c.tag) in names:
                return c
        return None

    def text_of(tag: ET.Element) -> str:
        parts: list[str] = []
        for c in tag.iter():
            if _local(c.tag) == "t" and c.text:
                t = c.text
                for a, b in OMML_OPERATOR_MAP.items():
                    t = t.replace(a, f" {b} ")
                parts.append(t)
        return "".join(parts)

    name = _local(node.tag) if isinstance(node.tag, str) else ""
    if name == "t":
        t = node.text or ""
        for a, b in OMML_OPERATOR_MAP.items():
            t = t.replace(a, f" {b} ")
        return t
    if name in ("oMath", "oMathPara", "e", "r", "deg", "sup", "sub", "lim",
                "f", "sSup", "sSub", "sSubSup", "sPre", "rad", "d", "m",
                "nary", "limLow", "limUpp", "bar", "acc", "box", "borderBox",
                "groupChr", "eqArr", "mr", "mc", "ctrlPr"):
        pass  # handled below; unknown wrappers fall through to generic concat
    else:
        return "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(node)) + (node.text or "")

    if name == "f":
        num = find_child(node, "num")
        den = find_child(node, "den")
        n = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                    for c in kids(num)) if num is not None else ""
        d = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                    for c in kids(den)) if den is not None else ""
        return f"\\frac{{{n.strip()}}}{{{d.strip()}}}"
    if name in ("sSup", "sSub", "sSubSup", "sPre"):
        e = find_child(node, "e")
        base = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)) if e is not None else ""
        out = base.strip()
        for role, wrap in (("sub", "_{%s}"), ("sup", "^{%s}")):
            part = find_child(node, role)
            if part is not None:
                t = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                            for c in kids(part)).strip()
                if t:
                    out += wrap % t
        return out
    if name == "rad":
        deg = find_child(node, "deg")
        e = find_child(node, "e")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        idx = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                      for c in kids(deg)).strip() if deg is not None else ""
        if idx:
            return f"\\sqrt[{idx}]{{{body}}}"
        return f"\\sqrt{{{body}}}"
    if name == "d":
        beg = end = ""
        for c in kids(node):
            if _local(c.tag) in ("dPr",):
                for g in kids(c):
                    if _local(g.tag) in ("begChr", "endChr"):
                        val = g.get(f"{_M_NS}val", "") or g.get("val", "")
                        if _local(g.tag) == "begChr":
                            beg = val or "("
                        else:
                            end = val or ")"
        e = find_child(node, "e")
        inner = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                        for c in kids(e)).strip() if e is not None else ""
        left = {"(": r"\left(", "[": r"\left[", "{": r"\left\{"}.get(beg, f"\\left{beg}" if beg else "")
        right = {")": r"\right)", "]": r"\right]", "}": r"\right\}"}.get(end, f"\\right{end}" if end else "")
        return f"{left} {inner} {right}".strip()
    if name == "m":
        rows = []
        for r in kids(node):
            if _local(r.tag) != "mr":
                continue
            cells = []
            for c in kids(r):
                if _local(c.tag) == "e":
                    cells.append("".join(omml_to_latex(g, _depth=_depth + 1, _budget=budget)
                                        for g in kids(c)).strip())
            rows.append(" & ".join(cells))
        return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"
    if name == "nary":
        op = r"\int"
        for c in kids(node):
            if _local(c.tag) in ("naryPr",):
                for g in kids(c):
                    if _local(g.tag) == "chr":
                        op = OMML_OPERATOR_MAP.get(g.get(f"{_M_NS}val", "")
                                                   or g.get("val", ""), op)
        out = op
        for role, wrap in (("sub", "_{%s}"), ("sup", "^{%s}")):
            part = find_child(node, role)
            if part is not None:
                t = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                            for c in kids(part)).strip()
                if t:
                    out += wrap % t
        e = find_child(node, "e")
        if e is not None:
            body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                           for c in kids(e)).strip()
            if body:
                out += f" {body}"
        return out
    if name == "limLow":
        e = find_child(node, "e")
        lim = find_child(node, "lim")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        under = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                        for c in kids(lim)).strip() if lim is not None else ""
        if body.strip() in (r"\lim", "lim"):
            return f"\\lim_{{{under}}}"
        return f"\\underset{{{under}}}{{{body}}}"
    if name == "limUpp":
        e = find_child(node, "e")
        lim = find_child(node, "lim")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        over = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(lim)).strip() if lim is not None else ""
        return f"\\overset{{{over}}}{{{body}}}"
    if name == "bar":
        e = find_child(node, "e")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        pos = ""
        for c in kids(node):
            if _local(c.tag) == "barPr":
                for g in kids(c):
                    if _local(g.tag) == "pos":
                        pos = g.get(f"{_M_NS}val", "") or g.get("val", "")
        return f"\\underline{{{body}}}" if pos == "bot" else f"\\overline{{{body}}}"
    if name == "acc":
        e = find_child(node, "e")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        chr_v = ""
        for c in kids(node):
            if _local(c.tag) == "accPr":
                for g in kids(c):
                    if _local(g.tag) == "chr":
                        chr_v = g.get(f"{_M_NS}val", "") or g.get("val", "")
        return {"^": f"\\hat{{{body}}}", "→": f"\\vec{{{body}}}",
                ".": f"\\dot{{{body}}}", "..": f"\\ddot{{{body}}}",
                "~": f"\\tilde{{{body}}}", "¯": f"\\bar{{{body}}}"}.get(chr_v, f"\\hat{{{body}}}")
    if name in ("box", "borderBox"):
        inner = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                        for c in kids(node)).strip()
        inner = re.sub(r"\\boxed\{(.*)\}", r"\1", inner)
        return f"\\boxed{{{inner}}}"
    if name == "groupChr":
        e = find_child(node, "e")
        body = "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                       for c in kids(e)).strip() if e is not None else ""
        pos = ""
        for c in kids(node):
            if _local(c.tag) == "groupChrPr":
                for g in kids(c):
                    if _local(g.tag) == "pos":
                        pos = g.get(f"{_M_NS}val", "") or g.get("val", "")
        return f"\\underbrace{{{body}}}" if pos == "bot" else f"\\overbrace{{{body}}}"
    if name == "eqArr":
        rows = []
        for c in kids(node):
            if _local(c.tag) == "e":
                rows.append("".join(omml_to_latex(g, _depth=_depth + 1, _budget=budget)
                                    for g in kids(c)).strip())
        return "\\begin{aligned} " + " \\\\ ".join(rows) + " \\end{aligned}"
    # generic container (oMath, e, r, mr, mc, ctrlPr...)
    return "".join(omml_to_latex(c, _depth=_depth + 1, _budget=budget)
                   for c in kids(node)) + (text_of(node) if not kids(node) else "")
