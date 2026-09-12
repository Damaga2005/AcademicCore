"""Equation equivalence vs Conversor originals (1:1 behavior, adapted code)."""
from bs4 import BeautifulSoup

from academic_core.documents import conversor_math as M
from tests.conversor_ref import load_original

MATHML_CASES = [
    ("<math><mfrac><mi>x</mi><mn>2</mn></mfrac></math>", None),
    ("<math><msup><mi>x</mi><mn>2</mn></msup></math>", None),
    ("<math><msub><mi>R</mi><mi>NTC</mi></msub></math>", None),
    ("<math><msubsup><mi>V</mi><mi>out</mi><mi>max</mi></msubsup></math>", None),
    ("<math><msqrt><mfrac><mn>1</mn><mi>x</mi></mfrac></msqrt></math>", None),
    ("<math><mroot><mi>x</mi><mn>3</mn></mroot></math>", None),
    ("<math><munder><mo>∑</mo><mi>i</mi></munder></math>", None),
    ("<math><mover><mi>V</mi><mo>→</mo></mover></math>", None),
    ("<math><munderover><mo>∫</mo><mn>0</mn><mi>∞</mi></munderover></math>", None),
    ("<math><mfenced><mi>a</mi><mo>+</mo><mi>b</mi></mfenced></math>", None),
    ("<math><menclose notation='box'><mi>Z</mi></menclose></math>", None),
    ("<math><mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr></mtable></math>", None),
    ("<math><mi>sin</mi><mo>+</mo><mn>30</mn></math>", None),
    ("<math><semantics><mrow><mi>x</mi></mrow>"
     "<annotation encoding='application/x-tex'>X</annotation></semantics></math>", "X"),
]


def _parse(html):
    return BeautifulSoup(html, "lxml").math


def test_mathml_equivalence():
    orig = load_original()
    for html, _ in MATHML_CASES:
        assert M.parse_mathml_to_latex(_parse(html)) == \
            orig.parse_mathml_to_latex(BeautifulSoup(html, "lxml").math), html


def test_annotation_priority():
    assert M.parse_mathml_to_latex(_parse(MATHML_CASES[-1][0])) == "X"


def test_polish_matches_ported_rules():
    orig = load_original()
    for tex in ["{\\displaystyle x}", "√(a+b)", "dy/dx", "a &lt; b", "50%",
                "2,2 V", "sin(x)", "{a"]:
        assert M.polish(tex) == orig.clean_latex_formula(tex), tex


def test_polish_intentionally_narrower():
    # Rules the Conversor applies that F3 deliberately does NOT port
    # (documented in CONVERSOR-F3-AUDIT §Riesgos): source stays canonical.
    assert M.polish("1/(RC)") == "1/(RC)"


def test_html_formula_nodes_equivalence():
    orig = load_original()
    cases = ['<span class="f"><var>U</var><sub>ref</sub></span>',
             '<span class="f"><var>α</var><sup>2</sup></span>',
             '<span class="ov">V</span>']
    for html in cases:
        node = BeautifulSoup(html, "lxml")
        assert M.html_formula_node_to_latex(node) == \
            orig.html_formula_node_to_latex(node), html


def test_shield_math_finding_sets_match():
    orig = load_original()
    html = ('<p>Energía <math><mfrac><mi>E</mi><mi>t</mi></mfrac></math> y '
            '<script type="math/tex">x^2</script></p>'
            '<p><span class="frac"><span class="num">1</span>'
            '<span class="den">2</span></span> <var>R</var><sub>1</sub></p>')
    soup = BeautifulSoup(html, "lxml")
    _, findings = M.shield_math(soup)
    got = sorted(t.strip().strip("$") for t, _ in findings)
    _, registry, _ = orig.extract_and_shield_math(BeautifulSoup(html, "lxml"))
    want = sorted(v.replace("$$", "").replace("$", "").strip() for v in registry.values())
    assert got == want
    assert len(findings) == 4  # mathml + mathjax-script + frac + var/sub


def test_equation_node_preserves_source():
    from academic_core.documents import ast as A
    eq = A.equation("U=R\\cdot I", "latex", False)
    assert A.Document.from_dict(
        {"schema_version": 1, "metadata": {}, "history": [],
         "children": [eq.to_dict()]}).children[0].attrs["source"] == "U=R\\cdot I"
