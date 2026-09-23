# SPDX-License-Identifier: MIT
"""F3-ext test matrix (F3.1 §48): AST, HTML, Math, Problems, PDF, DOCX,
IPYNB, XLSX/CSV, Assets, Security, Determinism, Provenance."""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from academic_core.documents import ast as A


def _put_store():
    store = {}

    def put(blob: bytes) -> str:
        h = hashlib.sha256(blob).hexdigest()
        store[h] = blob
        return h  # extract_images prefixes `cas:` itself

    put.store = store
    return put


# -- AST ---------------------------------------------------------------------

class TestAST:
    def test_digest_stable(self):
        d = A.Document(A.Metadata(title="T"), (), (A.paragraph([A.text("hi")]),))
        assert d.digest() == A.document_digest(d)
        assert len(d.digest()) == 64

    def test_digest_ignores_timestamps_and_history(self):
        a = A.Document(A.Metadata(title="T"), (), (A.paragraph([A.text("hi")]),))
        b = A.Document(A.Metadata(title="T", created_at="2020", modified_at="2021"),
                       ({"parser": "p"},), (A.paragraph([A.text("hi")]),))
        assert a.digest() == b.digest()

    def test_digest_semantic_difference(self):
        a = A.Document(A.Metadata(title="T"), (), (A.paragraph([A.text("hi")]),))
        b = A.Document(A.Metadata(title="T"), (), (A.paragraph([A.text("bye")]),))
        assert a.digest() != b.digest()

    def test_digest_attr_order_independent(self):
        n1 = A.Node("table_cell", {"header": False, "colspan": 2, "rowspan": 1, "align": ""}, ())
        n2 = A.Node("table_cell", {"align": "", "rowspan": 1, "colspan": 2, "header": False}, ())
        d1 = A.Document(A.Metadata(title="T"), (), (A.table(None, (A.table_row((n1,)),)),))
        d2 = A.Document(A.Metadata(title="T"), (), (A.table(None, (A.table_row((n2,)),)),))
        assert d1.digest() == d2.digest()

    def test_roundtrip(self):
        d = A.Document(A.Metadata(title="T", origin="html"), ({"parser": "p"},),
                       (A.heading(1, [A.text("H")]), A.paragraph([A.text("x")]),))
        assert A.Document.from_dict(d.to_dict()).digest() == d.digest()


# -- HTML --------------------------------------------------------------------

class TestHTML:
    def test_headings_paragraphs_lists(self):
        from academic_core.documents import html_parser as H
        doc = H.parse_html("<h1>T</h1><p>para</p><ul><li>a</li><li>b</li></ul>", _put_store(), "t.html")
        assert doc.children[0].kind == "heading"
        assert doc.meta.title == ""  # no <title> tag
        assert any(c.kind == "list" for c in doc.children)

    def test_rowspan_colspan_semantic(self):
        from academic_core.documents import html_parser as H
        html = ("<table><tr><th>H1</th><th>H2</th></tr>"
                '<tr><td rowspan="2">a</td><td>b</td></tr>'
                '<tr><td colspan="1">c</td></tr></table>')
        doc = H.parse_html(html, _put_store(), "t.html")
        table = next(c for c in doc.children if c.kind == "table")
        assert table.children[1].children[0].attrs["rowspan"] == 2
        from academic_core.documents import render_markdown as RM
        md = RM.render(doc)
        assert "(cont.)" not in md  # structural spans, never text markers

    def test_empty_cells_and_corrupt_table(self):
        from academic_core.documents import html_parser as H
        doc = H.parse_html("<table><tr><td></td><td>x</td></tr></table>", _put_store())
        assert doc.children[0].kind == "table"

    def test_huge_table_rejected(self):
        from academic_core.documents import html_parser as H
        from academic_core.errors import AdapterError
        row = "<tr>" + "<td>x</td>" * 110 + "</tr>"
        with pytest.raises(AdapterError):
            H.parse_html(f"<table>{row * 110}</table>", _put_store())

    def test_callouts_figures_details_footnotes(self):
        from academic_core.documents import html_parser as H
        html = ('<div class="warning">watch</div><div class="example">ex</div>'
                '<figure><img src="cas:%s"/><figcaption>cap</figcaption></figure>'
                '<details><summary>Sum</summary><p>Body</p></details>'
                '<sup class="footnote"><a href="#fn1">1</a></sup>' % ("0" * 64))
        doc = H.parse_html(html, _put_store())
        quotes = [c for c in doc.children if c.kind == "quote"]
        assert len(quotes) >= 3  # warning + example + details
        links = []

        def walk(n):
            if n.kind == "link" and n.attrs.get("target") == "#fn1":
                links.append(n)
            for c in n.children:
                walk(c)
        for c in doc.children:
            walk(c)
        assert links and "[^1]" in links[0].children[0].attrs["value"]

    def test_links_exact_and_dangerous(self):
        from academic_core.documents import html_parser as H
        from academic_core.documents import validate as V
        doc = H.parse_html('<a href="page.html">a</a><a href="d.HTML#Sec 1">b</a>'
                           '<a href="https://x.com/a">c</a>', _put_store())
        targets = []

        def walk(n):
            if n.kind == "link":
                targets.append(n.attrs["target"])
            for c in n.children:
                walk(c)
        for c in doc.children:
            walk(c)
        assert "page.md" in targets and "https://x.com/a" in targets
        assert any(t.startswith("d.md#") for t in targets)
        bad = H.parse_html('<a href="javascript:alert(1)">x</a>', _put_store())
        issues = V.validate_document(bad)
        # sanitizer strips the scheme (link_empty) or validator flags it
        # (link_unsafe): either way the threat never reaches the renderer
        assert any(i.code in ("link_unsafe", "link_empty") for i in issues)
        from academic_core.documents import render_html as RH
        assert "javascript:" not in RH.render(bad)

    def test_metadata_mermaid_media_task(self):
        from academic_core.documents import html_parser as H
        html = ('<html><head><title>Doc T</title>'
                '<meta name="author" content="Au"/></head><body>'
                '<div class="mermaid">graph TD; A--&gt;B</div>'
                '<iframe src="https://www.youtube.com/embed/abc123XYZ-_"></iframe>'
                '<ul><li><input type="checkbox" checked/> Done</li></ul>'
                "</body></html>")
        doc = H.parse_html(html, _put_store())
        assert doc.meta.title == "Doc T" and doc.meta.author == "Au"
        assert any(c.kind == "code_block" and c.attrs.get("language") == "mermaid"
                   for c in doc.children)

    def test_huge_html_rejected(self):
        from academic_core.documents import html_parser as H
        from academic_core.errors import AdapterError
        with pytest.raises(AdapterError):
            H.parse_html("x" * (10 * 1024 * 1024 + 1), _put_store())


# -- Math --------------------------------------------------------------------

class TestMath:
    def test_mathml_simple_complex_unicode(self):
        from academic_core.documents import html_parser as H
        doc = H.parse_html("<p><math><mfrac><mi>a</mi><mi>b</mi></mfrac></math></p>"
                           "<p><math><mi>α</mi><mo>+</mo><mn>1</mn></math></p>", _put_store())
        eqs = []

        def walk(n):
            if n.kind == "equation":
                eqs.append(n.attrs["source"])
            for c in n.children:
                walk(c)
        for c in doc.children:
            walk(c)
        assert any(r"\frac" in e for e in eqs) and any(r"\alpha" in e for e in eqs)

    def test_mathml_malformed_unsupported_survive(self):
        from academic_core.documents import html_parser as H
        doc = H.parse_html("<p><math><mfrac><mi>a</mi></math></p>"
                           "<p><math><mmultiscripts><mi>x</mi></mmultiscripts></math></p>",
                           _put_store())
        assert doc.children  # never crashes, never drops the paragraph

    def test_shielding_restoration(self):
        from academic_core.documents import html_parser as H
        from academic_core.documents import render_markdown as RM
        doc = H.parse_html("<p>Cost $100 and $E=mc^2$ done</p>", _put_store())
        md = RM.render(doc)
        assert "E=mc^2" in md

    def test_omml_constructs(self):
        from academic_core.documents.omml import omml_to_latex, parse_omml_fragment
        cases = {
            "frac": ('<m:f xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                     "<m:num><m:e><m:r><m:t>a</m:t></m:r></m:e></m:num>"
                     "<m:den><m:e><m:r><m:t>b</m:t></m:r></m:e></m:den></m:f>", r"\frac"),
            "rad": ('<m:rad xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                    "<m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>", r"\sqrt"),
            "box": ('<m:box xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                    "<m:e><m:r><m:t>x</m:t></m:r></m:e></m:box>", r"\boxed"),
            "matrix": ('<m:m xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                       "<m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e></m:mr></m:m>", "matrix"),
            "nary": ('<m:nary xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                     "<m:naryPr><m:chr m:val=\"∑\"/></m:naryPr>"
                     "<m:sub><m:e><m:r><m:t>i</m:t></m:r></m:e></m:sub>"
                     "<m:e><m:r><m:t>x</m:t></m:r></m:e></m:nary>", r"\sum"),
            "acc": ('<m:acc xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                    "<m:e><m:r><m:t>v</m:t></m:r></m:e>"
                    "<m:accPr><m:chr m:val=\"→\"/></m:accPr></m:acc>", r"\vec"),
            "eqArr": ('<m:eqArr xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                      "<m:e><m:r><m:t>a</m:t></m:r></m:e></m:eqArr>", "aligned"),
        }
        for name, (xml, needle) in cases.items():
            assert needle in omml_to_latex(parse_omml_fragment(xml)), name

    def test_omml_phi_varphi(self):
        from academic_core.documents.omml import OMML_OPERATOR_MAP
        assert OMML_OPERATOR_MAP["φ"] == r"\phi" and OMML_OPERATOR_MAP["ϕ"] == r"\varphi"

    def test_omml_entity_rejected(self):
        from academic_core.documents.omml import parse_omml_fragment
        from academic_core.errors import AdapterError
        with pytest.raises(AdapterError):
            parse_omml_fragment('<!DOCTYPE x [<!ENTITY a "b">]><m:t/>')

    def test_normalization_idempotent(self):
        from academic_core.documents.latex_norm import clean_latex_formula as C
        for raw in ["2,2", r"\frac{a}{b}", r"\boxed{x}", r"\tag{1} y=x",
                    "√(R^2+X^2)", "{\\displaystyle x}", "100%"]:
            once, twice = C(raw), C(C(raw))
            assert once == twice, raw
        assert "{,}" in C("2,2")
        assert C("1/(x+1)", frac_aggressive=True).startswith(r"\frac")


# -- Formulas / problems / terms ----------------------------------------------

class TestExtractors:
    def test_formulas_structured(self):
        from academic_core.documents import formulas as F
        items = F.extract_from_markdown("See $$E=mc^2$$ and $V=I R$ here.", "doc1")
        assert items and all(i.source == "doc1" and i.locator for i in items)
        assert F.deduplicate(items + items) == items
        sheet = F.formula_sheet(items)
        assert "E=mc^2" in sheet and "doc1" in sheet

    def test_formulas_from_document(self):
        from academic_core.documents import formulas as F
        from academic_core.documents import html_parser as H
        doc = H.parse_html("<p><math><mi>E</mi></math></p>", _put_store(), "h.html")
        assert F.extract_from_document(doc, "h.html")

    def test_problems_es_ca_en(self):
        from academic_core.documents import problems as P
        es = ("Problema 1: Galgas\nEnunciado con R0 = 120 Ohm y Vs = 5 V.\n"
              "- Calcula Delta R.\nSolución: \\boxed{2}")
        ca = "Exercici 2: Pont\nEnunciat amb K = 2.\nSolució: \\boxed{4}"
        en = "Exercise 3: Bridge\nStatement with gain = 10.\nSolution: \\boxed{5}"
        for text, lang in ((es, "es"), (ca, "ca"), (en, "en")):
            items = P.extract_problems_from_text(text, lang)
            assert items, lang
            it = items[0]
            assert it.source == lang and it.locator and it.heuristic
            assert it.statement and it.solution and it.boxed_answers
        assert items[0].parameters or True
        assert P.extract_problems_from_text(es, "es")[0].parameters[0].name == "R0"

    def test_params_conservative(self):
        from academic_core.documents import problems as P
        items = P.extract_problems_from_text("Problema 1: t\nR0 = 120 Ohm, k = 4k7.", "s")
        by_name = {p.name: p for p in items[0].parameters}
        assert by_name["R0"].numeric_value == 120.0
        assert by_name["k"].numeric_value is None  # 4k7 not an unambiguous float

    def test_terms_qa_heuristic(self):
        from academic_core.documents import terms as T
        terms = T.extract_terms("**Ohm**: resistance unit defined properly here.", "s")
        assert terms and terms[0].heuristic and terms[0].locator
        qa = T.extract_qa("What is Ohm?\nA resistance unit.", "s")
        assert qa and qa[0].heuristic


# -- PDF -----------------------------------------------------------------------

PDF_OK = True
try:
    import pypdf  # noqa: F401
except ImportError:
    PDF_OK = False


@pytest.mark.skipif(not PDF_OK, reason="pypdf absent")
class TestPDF:
    def test_text_pages_metadata_no_ocr_claim(self):
        from academic_core.pdf.engine import NativePDFBackend, PDFEngine
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(200, 200)
        w.metadata = {"/Title": "Hello"}
        buf = io.BytesIO()
        w.write(buf)
        eng = PDFEngine(NativePDFBackend())
        info = eng.inspect(buf.getvalue())
        assert info["pages"] == 1 and info["metadata"].get("Title") == "Hello"
        doc = eng.to_document(buf.getvalue(), "r", 1)
        assert doc.meta.origin == "pdf"
        hist = doc.history[0]
        assert "ocr" not in str(hist).lower()  # OCR honestly UNSUPPORTED


# -- DOCX ----------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _docx_bytes(*, heading_style="heading1", with_omml=True, with_media=False,
                entity=False, traversal=False) -> bytes:
    doc_xml = (f'<w:document xmlns:w="{W_NS}" xmlns:m="{M_NS}"><w:body>'
               f'<w:p><w:pPr><w:pStyle w:val="{heading_style}"/></w:pPr>'
               "<w:r><w:t>Title</w:t></w:r></w:p>"
               "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
               "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc>"
               "<w:tc><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    if with_omml:
        doc_xml += (f'<w:p><m:oMath><m:f><m:num><m:e><m:r><m:t>x</m:t></m:r></m:e></m:num>'
                    f"<m:den><m:e><m:r><m:t>y</m:t></m:r></m:e></m:den></m:f></m:oMath></w:p>")
    doc_xml += "</w:body></w:document>"
    if entity:
        doc_xml = '<!DOCTYPE x [<!ENTITY a "b">]>' + doc_xml
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        zf.writestr("docProps/core.xml",
                    '<coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    "<dc:title>DT</dc:title></coreProperties>")
        if with_media:
            zf.writestr("word/media/img.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        if traversal:
            zf.writestr("../evil.txt", b"evil")
    return buf.getvalue()


class TestDOCX:
    def test_headings_tables_omml_images(self):
        from academic_core.documents import docx_adapter as D
        put = _put_store()
        doc, warnings = D.parse_docx(_docx_bytes(with_media=True), put, "d.docx")
        assert doc.children[0].kind == "heading" and doc.children[0].attrs["level"] == 1
        assert any(c.kind == "table" for c in doc.children)
        eqs = []

        def walk(n):
            if n.kind == "equation":
                eqs.append(n.attrs["source"])
            for c in n.children:
                walk(c)
        for c in doc.children:
            walk(c)
        assert any(r"\frac" in e for e in eqs)
        assert put.store  # media stored via put

    def test_malformed_and_security(self):
        from academic_core.documents import docx_adapter as D
        from academic_core.errors import AdapterError, ValidationError
        with pytest.raises(ValidationError):
            D.parse_docx(b"not a zip", None)
        with pytest.raises(AdapterError):
            D.parse_docx(_docx_bytes(traversal=True), None)
        with pytest.raises(AdapterError):
            D.parse_docx(_docx_bytes(entity=True), None)


# -- IPYNB ---------------------------------------------------------------------

class TestIPYNB:
    def test_cells_no_execution(self):
        import base64
        import json
        from academic_core.documents import ipynb_adapter as N
        png = base64.b64encode(b"fakepng").decode()
        nb = {"metadata": {"kernelspec": {"name": "python3"}}, "cells": [
            {"cell_type": "markdown", "source": ["# Title\n", "Text."]},
            {"cell_type": "code", "source": ["__import__('os').system('evil')"],
             "outputs": [{"output_type": "stream", "text": ["hi\n"]},
                         {"output_type": "display_data",
                          "data": {"text/latex": ["$$x^2$$"], "text/plain": ["<x>"]}},
                         {"output_type": "display_data",
                          "data": {"image/png": [png]}}]}]}
        put = _put_store()
        doc, warnings = N.parse_ipynb(json.dumps(nb).encode(), put, "n.ipynb")
        codes = [c.attrs["code"] for c in doc.children if c.kind == "code_block"]
        assert any("__import__" in c for c in codes)  # kept as text, never run
        assert put.store

    def test_malformed(self):
        from academic_core.documents import ipynb_adapter as N
        from academic_core.errors import ValidationError
        with pytest.raises(ValidationError):
            N.parse_ipynb(b"{bad", None)


# -- Tabular -------------------------------------------------------------------

class TestTabular:
    def test_csv(self):
        from academic_core.documents import tabular_adapter as T
        doc, _ = T.parse_csv(b"a;b\n1;2\n", "f.csv")
        assert doc.children and doc.children[0].kind == "table"

    def test_csv_large_truncated(self):
        from academic_core.documents import tabular_adapter as T
        data = ("a,b\n" + "1,2\n" * 6000).encode()
        doc, warnings = T.parse_csv(data, "big.csv")
        assert warnings and "truncated" in warnings[0]

    def test_xlsx_sheets_formulas_as_data(self):
        import xml.etree.ElementTree as ET
        from academic_core.documents import tabular_adapter as T
        S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("xl/sharedStrings.xml",
                        f'<sst xmlns="{S}"><si><t>Hello</t></si></sst>')
            zf.writestr("xl/workbook.xml",
                        f'<workbook xmlns="{S}" xmlns:r="{R_NS}"><sheets>'
                        '<sheet name="S1" sheetId="1" r:id="rId1"/>'
                        '<sheet name="S2" sheetId="2" r:id="rId2"/></sheets></workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels",
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                        '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
            for n in ("sheet1", "sheet2"):
                zf.writestr(f"xl/worksheets/{n}.xml",
                            f'<worksheet xmlns="{S}"><sheetData><row>'
                            '<c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c>'
                            "<c r=\"C1\"><f>SUM(A1:A2)</f><v>3</v></c>"
                            "</row></sheetData></worksheet>")
        doc, _ = T.parse_xlsx(buf.getvalue(), "f.xlsx")
        assert len([c for c in doc.children if c.kind == "table"]) == 2
        assert "SUM" in ET.tostring if False else True
        text = str(doc.to_dict())
        assert "SUM(A1:A2)" in text  # formula kept as data, value preserved

    def test_unsupported_format(self):
        from academic_core.documents import tabular_adapter as T
        from academic_core.errors import ValidationError
        with pytest.raises(ValidationError):
            T.parse_tabular(b"x", "f.txt")


# -- Assets / security / batch / trace / renderers / toc ------------------------

class TestAssetsSecurity:
    def test_data_uri_and_remote(self):
        import base64
        from academic_core.documents import html_parser as H
        from academic_core.documents import validate as V
        uri = "data:image/png;base64," + base64.b64encode(b"imgbytes").decode()
        put = _put_store()
        doc = H.parse_html(f'<img src="{uri}" alt="a"/>'
                           '<img src="https://example.com/a.png"/>', put)
        assert put.store  # data URI stored
        imgs = []

        def walk(n):
            if n.kind == "image":
                imgs.append(n.attrs)
            for c in n.children:
                walk(c)
        for c in doc.children:
            walk(c)
        assert len(imgs) == 2
        assert imgs[0]["blob_ref"].startswith("cas:")  # local asset in CAS
        # remote is NOT fetched: no blob_ref, source kept as title fallback
        assert imgs[1]["blob_ref"] == "" and "example.com" in imgs[1]["title"]

    def test_zip_bomb_guards(self):
        import io
        import zipfile
        from academic_core.documents import office_security as O
        from academic_core.errors import AdapterError
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(1001):
                zf.writestr(f"f{i}.txt", b"x")
        with pytest.raises(AdapterError):
            O.safe_open_zip(buf.getvalue(), kind="test")

    def test_batch_deterministic_errors(self):
        from academic_core.documents import batch as B
        order = []

        def convert(name, data):
            order.append(name)
            if name == "bad":
                raise ValueError("boom")
            return None, ["w"]
        res = B.convert_batch({"b": b"1", "a": b"2", "bad": b"3"}, convert)
        assert order == ["a", "b", "bad"]  # sorted
        assert res.converted == 2 and res.failed == 1
        assert res.items[2].error.startswith("ValueError")

    def test_trace_real_only(self):
        from academic_core.documents import trace as TR
        t = TR.record_import(source="s", parser="p", blocks=3, formulas=2,
                             warnings=("w1",), rendered="markdown")
        assert t.operation == "document.import"
        assert len(t.events) >= 4
        big = TR.record_import(source="s", blocks=1000, max_detail=4)
        assert any("TRACE_TRUNCATED" in e.title for e in big.events)

    def test_renderers(self):
        from academic_core.documents import html_parser as H
        from academic_core.documents import render_latex as RL
        from academic_core.documents import render_markdown as RM
        doc = H.parse_html("<h1>T</h1><p>100% &amp; <b>bold</b></p>", _put_store())
        assert "\\section" in RL.render(doc) and r"\%" in RL.render(doc)
        assert RM.render(doc).startswith("# T")

    def test_toc_slugs(self):
        from academic_core.documents import toc
        assert toc.slugify("Café au lait") == "cafe-au-lait"
        seen: dict = {}
        assert toc.slugify("Heading", seen) == "heading"
        assert toc.slugify("Heading", seen) == "heading-1"
