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
