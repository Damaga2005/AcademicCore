"""F5 security: malformed AST, invalid ids/refs, traversal, oversize, CAS."""
import json

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.documents import ast as A
from academic_core.documents.validate import MAX_TEXT_CHARS, validate_document
from academic_core.domain import authoring as AU


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_malformed_ast_rejected_not_sanitized():
    with pytest.raises(Exception):
        A.Document.from_dict({"schema_version": 1, "metadata": {},
                              "history": [],
                              "children": [{"kind": "script", "attrs": {},
                                            "children": []}]})
    with pytest.raises(Exception):
        A.Document.from_dict({"schema_version": 1})  # missing arrays
    with pytest.raises(Exception):
        A.Node.from_dict({"kind": "paragraph"})  # missing attrs/children


def test_invalid_ids_and_refs_reported():
    doc = A.Document(A.Metadata(), (),
                     (A.paragraph([A.image("../../../etc/passwd", "x")]),
                      A.paragraph([A.image("cas:NOTHEX", "y")]),
                      A.paragraph([A.link("JaVaScRiPt:alert(1)", [A.text("z")])]),))
    codes = {i.code for i in validate_document(doc, lambda h: False)}
    assert {"image_ref", "link_unsafe"} <= codes


def test_oversize_rejected_with_report(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    st = core.authoring.open(sid)
    big = A.paragraph([A.text("x" * (MAX_TEXT_CHARS + 1))])
    st.execute(AU.InsertNode((len(st.doc.children),), big))
    codes = {i.code for i in core.authoring.validate(st)}
    assert "oversize" in codes


def test_missing_cas_blob_reported_not_crash(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    st = core.authoring.open(sid)
    st.execute(AU.InsertNode((0,), A.paragraph(
        [A.image("cas:" + "ff" * 32, "ghost")])))
    codes = {i.code for i in core.authoring.validate(st)}
    assert "image_missing" in codes
    # ...but saving still works (report, don't block); validation is advisory
    rep = core.authoring.save(st, sid)
    assert rep.outcome == "saved"


def test_autosave_cap_and_bad_payload(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    st = core.authoring.open(sid)
    with pytest.raises(ValueError):
        core.authoring.paste_nodes("application/x-academic-ast", "[1,2]")
    # tampered autosave file is rejected on recover, never loaded
    path = core.authoring._auto_path(sid)
    core.authoring.autosave_dir.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": 999}', encoding="utf-8")
    with pytest.raises(Exception):
        core.authoring.recover(sid)


def test_no_shell_no_exec_in_authoring_surface(tmp_path):
    import inspect
    import academic_core.application.authoring as mod
    src = inspect.getsource(mod)
    assert "shell=True" not in src and "eval(" not in src and "exec(" not in src
    assert "import os" not in src  # no filesystem except via injected blobs/dir
