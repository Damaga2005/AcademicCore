"""Math pipeline ADAPTED from Conversor-HTML-A-MD (see CONVERSOR-REUSE-MAP.md).

Provenance: `conversor_html_notebooklm.py` L41–357 + L373–613 (math sections),
MIT © 2026 Damaga2005 (same author; reuse with attribution), adapted
2026-09-12: Tk/markdownify removed, token registry replaced by a structured
list of (latex, display) findings; `clean_latex_formula` split into
`source` (preserved) vs `polish()` (optional derivation — canonical Equation
always keeps the original source per F1 formula policy).
Requires: beautifulsoup4 (mathml2latex stays lazy-optional fallback).
"""

from __future__ import annotations

import re

OPERATOR_MAP = {
    "±": r"\pm", "×": r"\times", "÷": r"\div", "·": r"\cdot", "•": r"\bullet",
    "≤": r"\le", "≥": r"\ge", "≠": r"\ne", "≈": r"\approx", "≡": r"\equiv",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "⊃": r"\supset", "⊇": r"\supseteq", "∪": r"\cup", "∩": r"\cap",
    "∖": r"\setminus", "∅": r"\emptyset", "∑": r"\sum", "∏": r"\prod",
    "∐": r"\coprod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint", "∮": r"\oint",
    "∂": r"\partial", "∇": r"\nabla", "∞": r"\infty",
    "→": r"\to", "⟶": r"\longrightarrow", "←": r"\leftarrow",
    "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow",
    "↔": r"\leftrightarrow", "↦": r"\mapsto",
    "∀": r"\forall", "∃": r"\exists", "¬": r"\neg", "∧": r"\land", "∨": r"\lor",
    "⊕": r"\oplus", "⊗": r"\otimes",
    "…": r"\dots", "⋯": r"\cdots", "⋮": r"\vdots", "⋱": r"\ddots",
    "°": r"^\circ", "∝": r"\propto", "∼": r"\sim", "≃": r"\simeq",
    "⊥": r"\perp", "∥": r"\parallel", "∠": r"\angle",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta",
    "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma",
    "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\varphi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}

NAMED_MATH_FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh",
    "arcsin", "arccos", "arctan", "ln", "log", "exp", "lim",
    "max", "min", "sup", "inf", "det",
}

UNICODE_SUP_MAP = {"⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
                   "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
                   "⁺": "^+", "⁻": "^-", "ⁿ": "^n"}
UNICODE_SUB_MAP = {"₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4",
                   "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9",
                   "₊": "_+", "₋": "_-", "ᵢ": "_i", "ₙ": "_n"}
GREEK_MAP = {g: OPERATOR_MAP[g] for g in
             ("α", "β", "γ", "δ", "ε", "ζ", "η", "θ", "ι", "κ", "λ", "μ",
              "ν", "ξ", "π", "ρ", "σ", "τ", "υ", "φ", "χ", "ψ", "ω",
              "Γ", "Δ", "Θ", "Λ", "Ξ", "Π", "Σ", "Φ", "Ψ", "Ω")}


def clean_math_text(txt: str) -> str:
    txt = txt.strip()
    return OPERATOR_MAP.get(txt, txt)


def _kids(node):
    from bs4 import NavigableString, Tag
    return [c for c in node.children
            if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]


def parse_mathml_to_latex(node) -> str:
    """Recursive MathML → LaTeX (adapted 1:1 in behavior from the Conversor)."""
    from bs4 import NavigableString
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        return clean_math_text(str(node))
    tag = node.name.lower() if node.name else ""
    if tag in ("math", "semantics"):
        ann = node.find("annotation", attrs={"encoding": re.compile(r"tex|latex", re.I)})
        if ann and ann.string and ann.string.strip():
            return ann.string.strip()
    children = _kids(node)
    if tag in ("math", "semantics", "mrow", "mstyle", "mpadded", "mphantom"):
        return "".join(parse_mathml_to_latex(c) for c in children)
    if tag == "mi":
        t = clean_math_text(node.get_text())
        if t.lower() in NAMED_MATH_FUNCS:
            return f"\\{t.lower()} "
        if t.startswith("\\"):
            return f"{t} "
        if len(t) > 1:
            return f"\\mathrm{{{t}}}"
        return t
    if tag == "mn":
        return node.get_text().strip()
    if tag == "mo":
        t = clean_math_text(node.get_text())
        if t in ("+", "-", "*", "=", "<", ">", ":", "!", "?", "/", "(", ")", "[", "]", "|"):
            return f" {t} " if t in ("+", "-", "=", "<", ">") else t
        return f" {t} " if t.startswith("\\") else t
    if tag == "mtext":
        t = node.get_text().strip()
        return f"\\text{{{t}}}" if t else ""
    if tag == "mfrac":
        num = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        den = parse_mathml_to_latex(children[1]) if len(children) > 1 else ""
        return f"\\frac{{{num.strip()}}}{{{den.strip()}}}"
    if tag == "msqrt":
        inner = "".join(parse_mathml_to_latex(c) for c in children).strip()
        return f"\\sqrt{{{inner}}}"
    if tag == "mroot":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        idx = parse_mathml_to_latex(children[1]) if len(children) > 1 else ""
        return f"\\sqrt[{idx.strip()}]{{{base.strip()}}}"
    def _base(s: str) -> str:
        s = s.strip()
        return f"{{{s}}}" if len(s) > 1 and not (s.startswith("{") and s.endswith("}")) else s

    if tag == "msup":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        exp = parse_mathml_to_latex(children[1]) if len(children) > 1 else ""
        return f"{_base(base)}^{{{exp.strip()}}}"
    if tag == "msub":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        sub = parse_mathml_to_latex(children[1]) if len(children) > 1 else ""
        return f"{_base(base)}_{{{sub.strip()}}}"
    if tag == "msubsup":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        sub = parse_mathml_to_latex(children[1]) if len(children) > 1 else ""
        exp = parse_mathml_to_latex(children[2]) if len(children) > 2 else ""
        return f"{_base(base)}_{{{sub.strip()}}}^{{{exp.strip()}}}"
    if tag == "munder":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        return f"\\underset{{{parse_mathml_to_latex(children[1]).strip()}}}{{{base.strip()}}}" if len(children) > 1 else base
    if tag == "mover":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        ovr = parse_mathml_to_latex(children[1]).strip() if len(children) > 1 else ""
        if ovr in ("^", r"\hat", "ˆ"):
            return f"\\hat{{{base.strip()}}}"
        if ovr in ("-", r"\bar", "¯"):
            return f"\\bar{{{base.strip()}}}"
        if ovr in ("→", r"\to", r"\vec"):
            return f"\\vec{{{base.strip()}}}"
        return f"\\overset{{{ovr}}}{{{base.strip()}}}"
    if tag == "munderover":
        base = parse_mathml_to_latex(children[0]) if len(children) > 0 else ""
        und = parse_mathml_to_latex(children[1]).strip() if len(children) > 1 else ""
        ovr = parse_mathml_to_latex(children[2]).strip() if len(children) > 2 else ""
        return f"{base.strip()}_{{{und}}}^{{{ovr}}}"
    if tag == "mfenced":
        op, cl = node.get("open", "("), node.get("close", ")")
        inner = "".join(parse_mathml_to_latex(c) for c in children).strip()
        return f"\\left{op} {inner} \\right{cl}"
    if tag == "menclose":
        notation = node.get("notation", "box").lower()
        inner = "".join(parse_mathml_to_latex(c) for c in children).strip()
        if "box" in notation or "roundedbox" in notation:
            return f"\\boxed{{{inner}}}"
        if "circle" in notation:
            return f"\\textcircled{{{inner}}}"
        if "strike" in notation:
            return f"\\cancel{{{inner}}}"
        return f"\\overline{{{inner}}}"
    if tag == "mtable":
        rows = []
        for r in node.find_all("mtr", recursive=False):
            cells = [parse_mathml_to_latex(d).strip()
                     for d in r.find_all("mtd", recursive=False)]
            rows.append(" & ".join(cells))
        return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"
    if tag == "mspace":
        return r"\!" if "negative" in node.get("width", "") else r"\quad "
    return "".join(parse_mathml_to_latex(c) for c in children)


def polish(tex: str) -> str:
    """Optional readability derivation (Conversor `clean_latex_formula`).

    NEVER applied silently to canonical Equation.source — callers store the
    raw source and may keep `polish(source)` as a derived rendering hint.
    """
    if not tex:
        return ""
    tex = tex.strip()
    m = re.match(r"^\{\\displaystyle\s*(.*)\}$", tex, flags=re.DOTALL)
    if m:
        tex = m.group(1).strip()
    tex = re.sub(r"√\s*\[\s*(.*?)\s*\]", r"\\sqrt{\1}", tex)
    tex = re.sub(r"√\s*\(\s*(.*?)\s*\)", r"\\sqrt{\1}", tex)
    tex = re.sub(r"\bd([a-zA-Z])\s*/\s*d([a-zA-Z])\b", r"\\frac{\\mathrm{d}\1}{\\mathrm{d}\2}", tex)
    tex = tex.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", r"\&")
    tex = re.sub(r"(?<!\\)%", r"\\%", tex)
    tex = re.sub(r"(\d+),(\d+)", r"\1{,}\2", tex)
    tex = re.sub(r"(?<!\\)\b(ln|log|exp|sin|cos|tan|det)\b", r"\\\1", tex)
    open_b, close_b = tex.count("{"), tex.count("}")
    if open_b > close_b:
        tex += "}" * (open_b - close_b)
    return re.sub(r"\s+", " ", tex).strip()


def html_formula_node_to_latex(node) -> str:
    """Enriched-HTML formula spans (var/sub/sup/ov/frac) → LaTeX (adapted)."""
    from bs4 import NavigableString
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        s = str(node)
        for a, b in (("−", "-"), ("·", r" \cdot "), ("×", r" \times "),
                     ("≈", r" \approx "), ("≠", r" \ne "),
                     ("≤", r" \le "), ("≥", r" \ge "),
                     ("Σ", r"\sum "), ("∑", r"\sum ")):
            s = s.replace(a, b)
        for mp in (UNICODE_SUP_MAP, UNICODE_SUB_MAP):
            for u, t in mp.items():
                s = s.replace(u, t)
        for g, t in GREEK_MAP.items():
            s = s.replace(g, f" {t} ")
        return s
    tag = node.name.lower() if node.name else ""
    if tag == "var":
        inner = "".join(html_formula_node_to_latex(c) for c in node.children).strip()
        for g_char, g_tex in GREEK_MAP.items():
            if inner == g_char or inner == g_tex.strip():
                return f" {g_tex} "
        return inner
    if tag in ("sub", "msub"):
        inner = "".join(html_formula_node_to_latex(c) for c in node.children).strip()
        if re.search(r"[a-zA-Z]{2,}", inner) and "\\" not in inner:
            return f"_{{\\text{{{inner}}}}}"
        return f"_{{{inner}}}"
    if tag in ("sup", "msup"):
        inner = "".join(html_formula_node_to_latex(c) for c in node.children).strip()
        return f"^{{{inner}}}"
    if tag == "span":
        classes = node.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        if any(c in ("ov", "ovl", "overline", "bar") for c in classes):
            inner = "".join(html_formula_node_to_latex(c) for c in node.children).strip()
            return f"\\bar{{{inner}}}"
        return "".join(html_formula_node_to_latex(c) for c in node.children)
    return "".join(html_formula_node_to_latex(c) for c in node.children)


def _mathml_node_to_latex(tag) -> str:
    tex_ann = tag.find("annotation", attrs={"encoding": re.compile(r"tex|latex", re.I)})
    if tex_ann and tex_ann.string and tex_ann.string.strip():
        return tex_ann.string.strip()
    try:
        if latex := parse_mathml_to_latex(tag).strip():
            return latex
    except Exception:
        pass
    try:
        import mathml2latex.mathml as m2l  # lazy fallback, as in the Conversor
        if latex := m2l.process_mathml(tag).strip():
            return latex
    except Exception:
        pass
    return tag.get_text(separator=" ", strip=True)


def shield_math(soup):
    """Find math across sources; REPLACE with placeholder tags.

    Returns (soup, findings) where findings = [(latex, display), ...] and
    each replaced node is `<math-shield data-i="N"/>` (round-trippable inside
    the soup walk; placeholders never leak into the AST).
    Covered: MathJax script tags, MathML, KaTeX semantic layer, SVG TeX
    comments/attrs, formula images (alt-LaTeX), frac spans, var+sub/sup.
    """
    from bs4 import NavigableString
    findings: list[tuple[str, bool]] = []

    def _swap(node, latex: str, display: bool) -> None:
        from bs4 import Tag as _Tag
        findings.append((latex, display))
        ph = soup.new_tag("math-shield")
        ph["data-i"] = str(len(findings) - 1)
        node.replace_with(ph)

    for script in soup.find_all("script", attrs={"type": re.compile(r"math/tex", re.I)}):
        display = "mode=display" in script.get("type", "")
        latex = script.string.strip() if script.string else ""
        _swap(script, latex, display)
    for katex in soup.find_all(class_="katex-html"):
        katex.decompose()  # visual duplicate; semantic math layer kept
    for tag in soup.find_all("math"):
        display = (tag.get("display") == "block" or tag.get("mode") == "display"
                   or (tag.parent and tag.parent.name in ("div", "p")
                       and len(tag.parent.get_text().strip()) == len(tag.get_text().strip())))
        _swap(tag, _mathml_node_to_latex(tag), display)
    for svg in soup.find_all("svg"):
        from bs4 import Comment
        tex = ""
        for c in svg.find_all(string=lambda t: isinstance(t, Comment)):
            m = re.search(r"\$(.*?)\$", c.strip())
            if m:
                tex = m.group(1).strip()
                break
        if not tex:
            cand = svg.get("data-latex", "") or svg.get("data-tex", "") or svg.get("aria-label", "")
            if cand:
                tex = cand.strip("$").strip()
        if tex:
            classes = svg.get("class", [])
            parent = svg.parent
            inline = (parent and parent.name in ("p", "li", "td", "span")
                      and len(parent.get_text().strip()) > len(tex))
            _swap(svg, tex, not inline)
    for img in soup.find_all("img"):
        classes = img.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        alt = img.get("alt", "").strip()
        src = img.get("src", "").lower()
        if alt and (any("math" in c.lower() for c in classes) or "latex" in src
                    or "codecogs.com" in src
                    or (alt.startswith(("\\", "$")) and len(alt) > 2)):
            block = ("display" in " ".join(classes).lower() or "\\\\" in alt
                     or (img.parent and img.parent.name in ("div", "p")
                         and len(img.parent.get_text(strip=True)) == 0))
            _swap(img, alt.strip("$").strip(), block)
    for frac in list(soup.find_all(
            lambda el: el.has_attr("class") and any(
                c in ("frac", "fraction") for c in (
                    el["class"] if isinstance(el["class"], list) else [el["class"]])))):
        num = frac.find(class_=re.compile(r"^(num|numerador|numerator)$"))
        den = frac.find(class_=re.compile(r"^(den|denominador|denominator)$"))
        if num and den:
            _swap(frac, f"\\frac{{{html_formula_node_to_latex(num).strip()}}}"
                        f"{{{html_formula_node_to_latex(den).strip()}}}", False)
    for var in list(soup.find_all("var")):
        if var.find_parent(["pre", "code"]):
            continue
        v_txt = var.get_text().strip()
        sib, sub, sup, drop = var.next_sibling, "", "", []
        if sib and getattr(sib, "name", None) == "sub":
            s_txt = sib.get_text().strip()
            sub = (f"_{{\\text{{{s_txt}}}}}" if len(s_txt) > 1 and s_txt.isalpha()
                   else f"_{{{s_txt}}}")
            drop.append(sib)
            sib2 = sib.next_sibling
            if sib2 and getattr(sib2, "name", None) == "sup":
                sup = f"^{{{sib2.get_text().strip()}}}"
                drop.append(sib2)
        elif sib and getattr(sib, "name", None) == "sup":
            sup = f"^{{{sib.get_text().strip()}}}"
            drop.append(sib)
        if sub or sup or v_txt in GREEK_MAP or (len(v_txt) == 1 and v_txt.isalpha()):
            for el in drop:
                el.decompose()
            _swap(var, f"${GREEK_MAP.get(v_txt, v_txt)}{sub}{sup}$".strip("$"), False)
    return soup, findings
