# SPDX-License-Identifier: MIT
"""Canonical LaTeX normalization (F3.1 §10): single implementation.

Unifies the two diverged `clean_latex_formula` copies found in F3.0
(`conversor_html_notebooklm.py:281` asymmetric balance vs
`universal_converters.py:934` symmetric balance). Canonical = UC variant.

Rules: symmetric brace balance, idempotent, semantics-preserving,
`decimal_comma` and `frac_aggressive` opt-in flags (defaults safe).
Never applied silently to `Equation.source`; callers keep raw source.
"""

from __future__ import annotations

import re

NORMALIZATION_VERSION = "f3-latex-norm/1"


def clean_latex_formula(tex: str, *, decimal_comma: bool = True,
                        frac_aggressive: bool = False) -> str:
    """Normalize LaTeX; idempotent: clean(clean(x)) == clean(x)."""
    if not tex:
        return ""
    tex = tex.strip()
    m = re.match(r"^\{\\displaystyle\s*(.*)\}$", tex, flags=re.DOTALL)
    if m:
        tex = m.group(1).strip()
    # sqrt shorthands
    tex = re.sub(r"√\s*\[\s*(.*?)\s*\]", r"\\sqrt{\1}", tex)
    tex = re.sub(r"√\s*\(\s*(.*?)\s*\)", r"\\sqrt{\1}", tex)
    tex = re.sub(r"√\s*([a-zA-Z0-9])", r"\\sqrt{\1}", tex)
    old = tex
    tex = re.sub(r"\\sqrt\{([^{}]*?/[^{}]*?)\}",
                 lambda mm: "\\sqrt{\\frac{%s}}" % mm.group(1)
                 if "\\frac" not in mm.group(1) else mm.group(0), tex)
    if tex == old:
        pass
    # dy/dx -> frac (word-boundary guarded, avoids matching inside words)
    tex = re.sub(r"\bd([a-zA-Z])\s*/\s*d([a-zA-Z])\b",
                 r"\\frac{\\mathrm{d}\1}{\\mathrm{d}\2}", tex)
    if frac_aggressive:
        tex = re.sub(r"\b1\s*/\s*\(\s*([^()]{1,80})\s*\)", r"\\frac{1}{\1}", tex)
        tex = re.sub(r"\b1\s*/\s*([a-zA-Z0-9\\{]{1,40})\b", r"\\frac{1}{\1}", tex)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&le;", r"\le "), ("&ge;", r"\ge "),
                 ("&ne;", r"\ne "), ("&plusmn;", r"\pm "), ("&times;", r"\times "),
                 ("&amp;", r"\&")):
        tex = tex.replace(a, b)
    tex = re.sub(r"(?<!\\)%", r"\\%", tex)
    if decimal_comma:
        tex = re.sub(r"(\d+),(\d+)", r"\1{,}\2", tex)
    tex = re.sub(r"(?<!\\)\b(ln|log|exp|sin|cos|tan|cot|sec|csc|sinh|cosh|tanh|"
                 r"arcsin|arccos|arctan|det|lim|sup|inf)\b", r"\\\1", tex)
    # Catalan/Spanish names -> operators (idempotent: skip if already \cmd)
    tex = re.sub(r"(?<!\\)\b(màx|máx|max)\b", r"\\max", tex)
    tex = re.sub(r"(?<!\\)\b(mín|mínimo|min)\b", r"\\min", tex)
    tex = re.sub(r"(?<!\\)\b(lím|limite|límit)\b", r"\\lim", tex)

    def _text_sub(m: re.Match) -> str:
        inner = m.group(1)
        if inner in ("max", "min", "lim", "sup", "inf") or "\\" in inner:
            return m.group(0)
        return "_{\\text{%s}}" % inner
    tex = re.sub(r"_\{([a-zA-Zà-ÿÀ-ÞçÇ]{2,20})\}", _text_sub, tex)
    open_b, close_b = tex.count("{"), tex.count("}")
    if open_b > close_b:
        tex += "}" * (open_b - close_b)
    elif close_b > open_b:
        tex = "{" * (close_b - open_b) + tex
    return re.sub(r"\s+", " ", tex).strip()
