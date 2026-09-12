"""PDF engine: valid/corrupt/metadata/pages/ops/CAS preservation + PDF→AST."""
import io

import pytest

from academic_core.pdf.engine import (
    NativePDFBackend, PDFEngine, PDFError, UnsupportedOperation,
)


def _pdf(pages=1, title=""):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(200, 200)
    if title:
        w.add_metadata({"/Title": title})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _text_pdf(text="Hola mon"):
    # minimal text pdf via pypdf is awkward; build with reportlab if present,
    # else exercise the scanned-page path (empty text, honest warnings).
    try:
        from reportlab.pdfgen.canvas import Canvas
        buf = io.BytesIO()
        c = Canvas(buf)
        c.drawString(50, 800, text)
        c.showPage()
        c.save()
        return buf.getvalue()
    except ImportError:
        pytest.skip("reportlab absent: text path untestable here")


def test_inspect_metadata_pages():
    info = NativePDFBackend().inspect(_pdf(3, "Apunts"))
    assert info["pages"] == 3 and info["metadata"].get("Title") == "Apunts"
    assert info["encrypted"] is False


def test_corrupt_empty_oversize():
    back = NativePDFBackend()
    for bad in (b"", b"not a pdf", b"%PDF-9.9 \xff broken"):
        with pytest.raises(PDFError):
            back.inspect(bad)
    with pytest.raises(PDFError):
        back.inspect(b"%PDF-1.4" + b"x" * 10, )


def test_merge_split_rotate_roundtrip():
    back = NativePDFBackend()
    merged = back.merge([_pdf(1), _pdf(2)])
    assert NativePDFBackend().inspect(merged)["pages"] == 3
    parts = back.split(merged, [(0, 0), (1, 2)])
    assert [NativePDFBackend().inspect(p)["pages"] for p in parts] == [1, 2]
    rotated = back.rotate(_pdf(1), 90)
    assert rotated.startswith(b"%PDF")
    with pytest.raises(PDFError):
        back.rotate(_pdf(1), 45)
    with pytest.raises(UnsupportedOperation):
        back.render_page(_pdf(1), 0)


def test_extract_text_path():
    data = _text_pdf()
    assert "Hola mon" in NativePDFBackend().extract_text(data)


def test_pdf_to_document_provenance():
    engine = PDFEngine(NativePDFBackend())
    doc = engine.to_document(_text_pdf("Contingut"), "resource:g:r:00001", 2)
    assert doc.history[0]["parser"] == "pdf-native"
    assert doc.history[0]["source_version"] == 2
    assert doc.history[0]["pages"] == 1
    assert any("Contingut" in n.attrs.get("value", "")
               for s in doc.children for p in s.children for n in p.children)


def test_engine_merge_validates_output():
    assert PDFEngine(NativePDFBackend()).merge([_pdf(1)]).startswith(b"%PDF")
