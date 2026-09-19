"""HTML→AST: structure, sanitization, escaping, malformed input."""
from academic_core.documents import ast as A
from academic_core.documents import render_html as RH
from academic_core.documents import render_markdown as RM
from academic_core.documents.html_parser import parse_html

RICH = b"""<html lang="ca"><head><title>Apunts</title>
<meta name="author" content="D. Marti"></head><body>
<script>alert(1)</script>
<h1>Tema 1</h1>
<p>La llei <var>U</var><sub>ef</sub> amb <a href="t2.html">enlla\xc3\xa7</a>.</p>
<math><mfrac><mi>Q</mi><mi>t</mi></mfrac></math>
<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
<ul><li>a</li><li>b</li></ul>
<blockquote><p>Nota</p></blockquote>
<pre><code class="language-python">x = 1</code></pre>
<img src="fig.png" alt="figura"/>
<hr/>
</body></html>"""


def test_html_structure_and_metadata():
    doc = parse_html(RICH, filename="t1.html")
    A.validate(doc)
    assert doc.meta.title == "Apunts" and doc.meta.author == "D. Marti"
    assert doc.meta.language == "ca"
    kinds = [c.kind for c in doc.children]
    assert kinds == ["heading", "paragraph", "paragraph", "table", "list",
                     "quote", "code_block", "paragraph", "thematic_break"]
    eqs = {n.attrs["source"]: n for p in doc.children if p.kind == "paragraph"
           for n in p.children if n.kind == "equation"}
    assert eqs[r"\frac{Q}{t}"].attrs["display"] is False
    assert r"U_{\text{ef}}" in eqs  # var+sub adapted from the Conversor
    assert doc.history[0]["parser"] == "html-parser"


def test_no_scripts_or_handlers_survive():
    evil = b"""<p onclick="x()" style="color:red">t</p>
    <a href="javascript:alert(1)">clic</a><div style="display:none">hide</div>"""
    doc = parse_html(evil)
    md, html = RM.render(doc), RH.render(doc)
    assert "onclick" not in html and "javascript:" not in html and "hide" not in md
    assert "clic" in md  # label kept, dangerous href dropped


def test_javascript_scheme_with_embedded_whitespace_is_dropped():
    """Regression: browsers ignore tabs/newlines/CR when scheme-matching a URL,
    so `jav\tascript:` etc. must be treated as `javascript:` and stripped."""
    evil = (b'<a href="jav\tascript:alert(1)">a</a>'
            b'<a href="jav\nascript:alert(2)">b</a>'
            b'<a href="jav\rascript:alert(3)">c</a>')
    doc = parse_html(evil)
    md, html = RM.render(doc), RH.render(doc)
    assert "javascript:" not in html.lower().replace("\t", "").replace("\n", "").replace("\r", "")
    assert "alert(1)" not in html and "alert(2)" not in html and "alert(3)" not in html


def test_javascript_scheme_single_shared_implementation_all_layers():
    """The three defense layers (sanitizer, validator, renderer) must use
    exactly one shared predicate, so a future bypass variant can never be
    blocked in one layer but missed in another. Covers the full variant
    matrix (case, tabs, newlines, CR, NUL, vertical tab, form feed,
    spaces) end-to-end through every layer."""
    from bs4 import BeautifulSoup

    from academic_core.documents import conversor_sanitize as SAN
    from academic_core.documents import security as SEC
    from academic_core.documents import validate as VAL
    from academic_core.documents.validate import validate_document

    assert SAN._is_javascript_scheme is SEC.is_javascript_scheme
    assert VAL._is_javascript_scheme is SEC.is_javascript_scheme
    assert RH._is_javascript_scheme is SEC.is_javascript_scheme

    variants = ["javascript:alert(1)", "JAVASCRIPT:alert(1)", "JaVaScRiPt:alert(1)",
                "jav\tascript:alert(1)", "jav\nascript:alert(1)",
                "jav\rascript:alert(1)", "jav\x00ascript:alert(1)",
                "jav\x0bascript:alert(1)", "jav\x0cascript:alert(1)",
                "  javascript:alert(1)", "java\tscript:alert(1)"]
    for v in variants:
        assert SEC.is_javascript_scheme(v), f"predicate missed {v!r}"
        # Validator layer flags it.
        vdoc = A.Document(A.Metadata(title="t"), (),
                          (A.paragraph([A.link(v, [A.text("x")])]),))
        assert any(i.code == "link_unsafe" for i in validate_document(vdoc)), v
        # Renderer layer drops the href but keeps the label.
        html = RH.render(vdoc)
        assert "alert(1)" not in html, v
        # Sanitizer layer strips the attribute value. The value is set
        # directly on the parsed element: a raw NUL byte in HTML source
        # never even reaches this layer (the HTML parser itself truncates
        # the attribute there, so no link is formed at all).
        soup = BeautifulSoup('<a href="placeholder">x</a>', "lxml")
        soup.a["href"] = v
        SAN.clean_soup_noise(soup)
        assert soup.a.get("href") is None, v


def test_malformed_html_never_drops_text():
    doc = parse_html(b"<div><p>sin cerrar<li>item<p>otro")
    A.validate(doc)
    assert "sin cerrar" in RM.render(doc) and "otro" in RM.render(doc)


def test_renderers_escape_and_stay_deterministic():
    doc = parse_html(b"<p>5 &lt; 6 &amp; \"x\"</p>")
    h1 = RH.render(doc)
    assert "&lt;" in h1 and "<script" not in h1
    assert RH.render(doc) == h1 and RM.render(doc) == RM.render(doc)


def test_images_become_cas_references():
    import base64
    payload = base64.b64encode(b"PNGDATA").decode()
    doc = parse_html(f'<img src="data:image/png;base64,{payload}" alt="f"/>'.encode(),
                     put=lambda d: "00" * 32)
    imgs = [n for p in doc.children if p.kind == "paragraph" for n in p.children
            if n.kind == "image"]
    assert imgs and imgs[0].attrs["blob_ref"] == "cas:" + "00" * 32
