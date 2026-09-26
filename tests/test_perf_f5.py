"""F5 performance: open/save/undo/serialize/roundtrips/large docs."""
import time

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.documents import ast as A
from academic_core.documents import render_html as RH
from academic_core.documents import render_markdown as RM
from academic_core.documents.markdown_parser import parse_markdown
from academic_core.domain import authoring as AU

pytestmark = pytest.mark.perf


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_perf_authoring_cycle(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    t0 = time.perf_counter()
    st = core.authoring.open(sid)
    t_open = time.perf_counter() - t0
    t0 = time.perf_counter()
    for i in range(50):
        st.execute(AU.InsertNode((len(st.doc.children),),
                                 A.paragraph([A.text(f"p{i}")])))

    for _ in range(50):
        st.undo()
    for _ in range(50):
        st.redo()
    t_edit = time.perf_counter() - t0
    t0 = time.perf_counter()
    rep = core.authoring.save(st, sid)
    t_save = time.perf_counter() - t0
    assert rep.outcome == "saved"
    print(f"\n[perf] open {t_open:.2f}s, 150 undo/redo ops {t_edit:.2f}s, save {t_save:.2f}s")
    assert t_open < 5 and t_edit < 15 and t_save < 10


def test_perf_large_document(tmp_path):
    paras = "\n\n".join(f"Pàragraf {i} amb **text**." for i in range(2000))
    t0 = time.perf_counter()
    doc = parse_markdown("# Gran\n\n" + paras)
    t_parse = time.perf_counter() - t0
    t0 = time.perf_counter()
    back = parse_markdown(RM.render(doc))
    t_rt = time.perf_counter() - t0
    t0 = time.perf_counter()
    RH.render(doc)
    t_html = time.perf_counter() - t0
    assert len(back.children) == len(doc.children) == 2001
    print(f"\n[perf] 2000-para parse {t_parse:.2f}s, md-rt {t_rt:.2f}s, html {t_html:.2f}s")
    assert t_parse < 20 and t_rt < 30 and t_html < 15
