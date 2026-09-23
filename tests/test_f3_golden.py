# SPDX-License-Identifier: MIT
"""F3-ext golden corpus (F3.1 §49): small, reproducible, sanitized.

Every case pins (digest, block count). Any semantic drift fails loudly.
Bytes below are byte-identical to the generator run (2026-09-23).
"""

from __future__ import annotations

import hashlib
import io
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _put(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _raw() -> dict[str, bytes]:
    return {
        "html_simple": b"<h1>T</h1><p>Hello <b>world</b>.</p>",
        "html_complex": ("<article><h1>Guia</h1><div class=\"warning\">Compte!</div>"
                         "<table><tr><th>A</th><th>B</th></tr><tr><td rowspan=\"2\">x</td>"
                         "<td>y</td></tr><tr><td>z</td></tr></table>"
                         "<figure><img src=\"https://e.com/a.png\" alt=\"a\"/>"
                         "<figcaption>Figura 1</figcaption></figure>"
                         "<details><summary>Veure</summary><p>Cos</p></details>"
                         "<dl><dt>Terme</dt><dd>Definició</dd></dl>"
                         "<div class=\"mermaid\">graph TD; A-->B</div>"
                         "<pre class=\"plantuml\">@startuml\nA->B\n@enduml</pre>"
                         "<p>Veure <a href=\"altre.html#Secció 1\">enllaç</a>.</p>"
                         "<sup class=\"footnote\"><a href=\"#fn1\">1</a></sup></div>"
                         "</article>").encode(),
        "html_mathml": ("<p>Energia <math><mfrac><mi>E</mi><msup><mi>c</mi>"
                        "<mn>2</mn></msup></mfrac></math> i <math><mi>\u03b1</mi>"
                        "<mo>+</mo><mn>1</mn></math>.</p>").encode(),
        "html_svg_mml": ("<p>Sig <svg data-latex=\"\\\\alpha + 1\"><circle/></svg> fi.</p>").encode(),
        "html_dollar": "<p>Cost $100 and $E=mc^2$ and \\$5 and `$x$`.</p>".encode(),
        "html_dup_headings": "<h2>Tema</h2><h2>Tema</h2><h2>Café</h2>".encode("utf-8"),
        "html_cp1252": "Prix: 2,2 \u20ac <p>Ol\xe9</p>".encode("cp1252"),
        "html_malicious": ('<a href="javascript:alert(1)">x</a>'
                           '<iframe src="javascript:alert(2)"></iframe>').encode(),
    }


GOLDEN = {
    "html_simple": ("86200cc542355eb8beebca25bf5529639ba45e6515638c91d3b071f785208046", 2),
    "html_complex": ("2f254e87d4e273dd0ee25f76f2e8f323a553b31eb105f4c78dacc48421780eab", 11),
    "html_mathml": ("9b6e14de31488c016acc9499bde21abbd0cbe0e186e3e5f66982973dafbcb32c", 1),
    "html_svg_mml": ("bc1a5ba30611fb90646e528bf9d7d80ca5e027868fad3d41545ae6bc900e0ce0", 1),
    "html_dollar": ("44dc2d78563bf459cf875a99cc22ec3f5fc68b19e0d13850d9ba6b3caff6034e", 1),
    "html_dup_headings": ("296b1b37e89f784f4494be6e52299cd912509e54cd626c0457c634a170dff38d", 3),
    "html_cp1252": ("7f7d73d8e09147f643b7a30d3b14c9347dcc935ed2188c73cd793ae16728fe1b", 2),
    "html_malicious": ("0ffc04ba0bf9e87b97cd1479ac3e6d57b8f4f7621abe1ddbbd48e21e16c0aa16", 1),
    "docx_basic": ("1303bcaf5c309b91d036245149bd901ce429e713572e679ba7bb926029ebe0af", 4),
    "docx_no_omml": ("d99fb154ad285ed42b3a7a4cebcae97033f6f46503db4b4a39ddd8f9a92d0e25", 3),
}


def _docx(omml: bool) -> bytes:
    d = (f'<w:document xmlns:w="{W}" xmlns:m="{M}"><w:body>'
         '<w:p><w:pPr><w:pStyle w:val="heading1"/></w:pPr><w:r><w:t>DT</w:t></w:r></w:p>'
         '<w:p><w:r><w:t>Cos</w:t></w:r></w:p>'
         '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    if omml:
        d += (f'<w:p><m:oMath><m:m><m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e>'
              f'<m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr></m:m></m:oMath></w:p>')
    d += '</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", d)
        zf.writestr("word/_rels/document.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        zf.writestr("docProps/core.xml",
                    '<coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title></coreProperties>')
    return buf.getvalue()


class TestGolden:
    def test_html_corpus(self):
        from academic_core.documents import html_parser as H
        for name, raw in _raw().items():
            doc = H.parse_html(raw, _put, f"{name}.html")
            digest, blocks = GOLDEN[name]
            assert doc.digest() == digest, name
            assert len(doc.children) == blocks, name

    def test_docx_corpus(self):
        from academic_core.documents import docx_adapter as D
        for name, omml in (("docx_basic", True), ("docx_no_omml", False)):
            doc, _ = D.parse_docx(_docx(omml), _put, f"{name}.docx")
            digest, blocks = GOLDEN[name]
            assert doc.digest() == digest, name
            assert len(doc.children) == blocks, name

    def test_malicious_neutralized(self):
        from academic_core.documents import html_parser as H
        from academic_core.documents import render_html as RH
        from academic_core.documents import render_markdown as RM
        doc = H.parse_html(_raw()["html_malicious"], _put, "evil.html")
        assert "javascript:" not in RH.render(doc) + RM.render(doc)

    def test_slug_collision_stable(self):
        from academic_core.documents import html_parser as H
        from academic_core.documents import toc
        doc = H.parse_html(_raw()["html_dup_headings"], _put, "dup.html")
        slugs = [s for _, _, s in toc.toc_entries(doc)]
        assert slugs == ["tema", "tema-1", "cafe"]
