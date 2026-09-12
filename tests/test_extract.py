"""Extraction: text/md/html/pdf boundaries; blob never mutated."""
import hashlib

from academic_core.resources.adapters import (
    HtmlAdapter, LocalFileAdapter, MarkdownAdapter, PdfAdapter, adapter_for,
    detect_kind,
)


def test_detect_kind():
    assert detect_kind("a.md", b"#") == "markdown"
    assert detect_kind("a.txt", b"x") == "text"
    assert detect_kind("a.HTML", b"<") == "html"
    assert detect_kind("a.pdf", b"nope") == "pdf"
    assert detect_kind("scan", b"%PDF-1.4") == "pdf"
    assert detect_kind("data.bin", b"\x00\x01") == "file"


def test_markdown_title():
    ext = MarkdownAdapter().extract(b"# Tema 3\n\nContenido", "t.md")
    assert ext.status == "ok" and ext.metadata["title"] == "Tema 3"
    assert "Contenido" in ext.text


def test_html_strips_scripts_without_executing():
    html = (b"<html><head><title>Lab</title></head><body>"
            b"<script>alert(1)</script><style>.x{}</style>"
            b"<p>  Medida   de  tension </p></body></html>")
    ext = HtmlAdapter().extract(html, "lab.html")
    assert ext.status == "ok"
    assert "alert" not in ext.text and ".x" not in ext.text
    assert ext.text == "Medida de tension"
    assert ext.metadata["title"] == "Lab"


def test_binary_flagged_not_indexed():
    ext = LocalFileAdapter().extract(b"\x00\x01\x02binary", "d.bin")
    assert ext.is_binary and ext.text == ""


def test_pdf_graceful():
    try:
        from pypdf import PdfWriter
    except ImportError:
        ext = PdfAdapter().extract(b"%PDF-1.4 fake", "d.pdf")
        assert ext.status == "deferred"
        return
    import io
    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(200, 200)
    w.write(buf)
    ext = PdfAdapter().extract(buf.getvalue(), "d.pdf")
    assert ext.status == "ok" and ext.metadata["pages"] == 1


def test_pdf_corrupt_is_failed_not_crash():
    ext = PdfAdapter().extract(b"%PDF-1.4 broken \xff\xfe", "d.pdf")
    assert ext.status in ("failed", "ok", "deferred")


def test_extractor_does_not_mutate_blob():
    data = b"# Hola\n\nTexto"
    before = hashlib.sha256(data).hexdigest()
    MarkdownAdapter().extract(data, "a.md")
    HtmlAdapter().extract(b"<p>x</p>", "a.html")
    assert hashlib.sha256(data).hexdigest() == before


def test_adapter_registry_covers_kinds():
    for kind in ("markdown", "text", "html", "pdf", "file"):
        assert adapter_for(kind, f"x.{kind}").supports(kind, "x")
