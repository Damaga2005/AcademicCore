"""Performance smoke (Phase 3): measure, don't micro-opt. Generous bounds."""
import time

from academic_core.documents import render_html as RH
from academic_core.documents import render_markdown as RM
from academic_core.documents.html_parser import parse_html
from academic_core.documents.markdown_parser import parse_markdown


def _timed(label, fn, bound):
    start = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - start
    print(f"\n[perf] {label}: {dt:.2f}s (bound {bound}s)")
    assert dt < bound, f"{label} too slow: {dt:.2f}s"
    return out


def test_perf_html_parse_and_render():
    para = "<p>Texto con <strong>negrita</strong> y <em>cursiva</em>.</p>"
    html = f"<html><body><h1>T</h1>{para * 400}</body></html>".encode()
    doc = _timed("html-parse ~100KB", lambda: parse_html(html), 10)
    _timed("ast->md", lambda: RM.render(doc), 5)
    _timed("ast->html", lambda: RH.render(doc), 5)


def test_perf_markdown_roundtrip():
    md = ("# T\n\n" + "Párrafo con **énfasis**.\n\n" + "| a | b |\n|---|---|\n| 1 | 2 |\n\n") * 200
    doc = _timed("md-parse", lambda: parse_markdown(md), 10)
    _timed("md-serialize", lambda: __import__("json").dumps(doc.to_dict()), 5)
