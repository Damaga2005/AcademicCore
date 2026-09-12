"""Conversor equivalence: tables, images, sanitize, encoding, metadata."""
import re
import types

from bs4 import BeautifulSoup

from academic_core.documents import conversor_images as I
from academic_core.documents import conversor_sanitize as S
from academic_core.documents import conversor_tables as T
from academic_core.documents.encoding import read_html_bytes
from tests.conversor_ref import load_original

TABLE_HTML = """<table>
<tr><th>Tensió</th><th>Corrent</th></tr>
<tr><td rowspan="2">5 V</td><td>1 A</td></tr>
<tr><td>2 A</td></tr>
<tr><td colspan="2" align="center">Total</td></tr>
</table>"""


def test_table_grid_equivalence():
    orig = load_original()
    tag = BeautifulSoup(TABLE_HTML, "lxml").table
    conv = types.SimpleNamespace(convert_soup=lambda t: t.get_text())
    gfm = orig.convert_html_table_to_gfm_2d(BeautifulSoup(TABLE_HTML, "lxml").table, conv)
    gfm_rows = [line.strip().strip("|").split("|")
                for line in gfm.strip().splitlines()
                if line.startswith("|") and "---" not in line]
    gfm_cells = [[c.strip().replace(" (cont.)", "") for c in row] for row in gfm_rows]
    grid, is_code = T.table_grid(tag, lambda cell: [cell.get_text()])
    assert not is_code
    assert len(grid) == len(gfm_cells)
    # Structural spans carry no duplicated text (no "(cont.)" hack); resolve
    # them to their origin for content comparison, spans asserted below.
    origins: dict = {}
    for r, grow in enumerate(grid):
        for c, x in enumerate(grow):
            if not x.get("spanned"):
                origins[(r, c)] = x["inline"][0] if x["inline"] else ""
    def cell_text(r, c):
        # Same observable rule as the original: rowspan continuations repeat
        # the origin text upward; colspan continuations render empty.
        x = grid[r][c]
        if not x.get("spanned"):
            return x["inline"][0] if x["inline"] else ""
        left_origin = next((grid[r][cc] for cc in range(c - 1, -1, -1)
                            if not grid[r][cc].get("spanned")), None)
        if left_origin is not None and left_origin.get("colspan", 1) > 1:
            return ""
        for rr in range(r - 1, -1, -1):
            if not grid[rr][c].get("spanned"):
                return grid[rr][c]["inline"][0] if grid[rr][c]["inline"] else ""
        return ""
    for r, orow in enumerate(gfm_cells):
        assert [cell_text(r, c) for c in range(len(orow))] == orow
    assert grid[1][0]["rowspan"] == 2  # structural span, not "(cont.)" text
    assert grid[3][0]["colspan"] == 2 and grid[3][0]["align"] == "center"


def test_code_table_detected():
    html = ('<table class="highlight"><tr><td class="gutter">1</td>'
            '<td class="code"><pre class="language-python">x=1</pre></td></tr></table>')
    tag = BeautifulSoup(html, "lxml").table
    assert T.is_code_table(tag)
    lang, code = T.extract_code_cells(tag)
    assert lang == "python" and code == "x=1"


def test_base64_images_same_bytes_to_cas(tmp_path):
    orig = load_original()
    import base64
    payload = base64.b64encode(b"\x89PNG" + b"\x00" * 32).decode()
    html = f'<img src="data:image/png;base64,{payload}" alt="fig"/>'
    got = {}
    recs = I.extract_images(BeautifulSoup(html, "lxml"), lambda d: got.setdefault("h", __import__("hashlib").sha256(d).hexdigest()))
    assets = tmp_path / "assets"
    n = orig.extract_base64_images(BeautifulSoup(html, "lxml"), assets, "doc")
    assert n == 1 and len(recs) == 1 and recs[0]["note"] == "cas"
    assert (assets / "doc_img_1.png").read_bytes() == b"\x89PNG" + b"\x00" * 32


def test_sanitize_superset_of_original():
    orig = load_original()
    html = ('<div><script>alert(1)</script><style>.x{}</style><!-- c -->'
            '<p style="display:none">hide</p><div class="cookie-banner">k</div>'
            '<a href="javascript:evil()" onclick="x()">t</a></div>')
    mine = str(S.clean_soup_noise(BeautifulSoup(html, "lxml")))
    theirs = str(orig.clean_soup_noise(BeautifulSoup(html, "lxml")))
    for bad in ("alert", ".x{}", "hide", "cookie-banner"):
        assert bad not in mine
    # original removes structural noise too; mine additionally strips handlers
    assert "onclick" not in mine and "javascript:" not in mine
    for bad in ("alert", "hide"):
        assert bad not in theirs


def test_encoding_vectors(tmp_path):
    orig = load_original()
    vectors = [
        (b"\xef\xbb\xbf# T\xc3\xa9", "utf-8-sig"),
        ('<meta charset="iso-8859-1"><p>acci\xf3</p>'.encode("iso-8859-1"), "iso-8859-1"),
        ("<p>acci\xf3n</p>".encode("cp1252"), "cp1252"),
        ("<p>ok</p>".encode("utf-8"), "utf-8"),
    ]
    for raw in vectors:
        f = tmp_path / "v.html"
        f.write_bytes(raw[0])
        otext, oenc = orig.read_html_file_safely(f)
        mtext, menc = read_html_bytes(raw[0])
        assert mtext == otext and menc == oenc


def test_metadata_equivalence():
    orig = load_original()
    html = ('<html lang="ca"><head><title>T</title>'
            '<meta name="author" content="A"><meta name="description" content="D">'
            '</head></html>')
    assert S.extract_metadata(BeautifulSoup(html, "lxml")) == \
        {**orig.extract_metadata(BeautifulSoup(html, "lxml")), "language": "ca"}
