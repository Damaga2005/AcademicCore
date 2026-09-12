"""Authoring service: versioning, provenance, autosave, copy/paste, links."""
import json

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import authoring as AU
from academic_core.documents import ast as A


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_template_create_save_version_chain(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    assert sid.startswith("resource:general:r:")
    assert core.authoring_store.lifecycle_of(sid) == "DRAFT"
    st = core.authoring.open(sid)
    assert not st.dirty
    st.execute(AU.UpdateText((0, 0), "Apunts — Sistemes"))
    rep = core.authoring.save(st, sid)
    assert (rep.outcome, rep.version) == ("saved", 2)
    res = core.records.get(sid)
    assert [v.version for v in res.versions] == [1, 2]
    assert res.versions[1].provenance.parent_version == 1
    assert res.versions[1].provenance.adapter == "authoring"
    assert not st.dirty
    # identical save = noop, no artificial version
    st2 = core.authoring.open(sid)
    rep2 = core.authoring.save(st2, sid)
    assert (rep2.outcome, rep2.version) == ("noop-identical", 2)
    # undo does not touch persisted versions
    st2.execute(AU.UpdateText((0, 0), "zzz"))
    st2.undo()
    assert len(core.records.get(sid).versions) == 2


def test_create_from_resource_and_reopen(tmp_path):
    core = _app(tmp_path)
    f = tmp_path / "n.md"
    f.write_text("# N\n\ncuerpo", encoding="utf-8")
    rep = core.ingest.import_file(f)
    sid = core.authoring.create_from_resource(rep.stable_id)
    st = core.authoring.open(sid)
    assert st.doc.meta.title == "N"
    # reopen from disk: identical AST
    core2 = _app(tmp_path)
    assert core2.authoring.open(sid).doc == st.doc


def test_lifecycle_and_links(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lab-report")
    core.authoring.set_lifecycle(sid, "REVIEW")
    assert core.authoring_store.lifecycle_of(sid) == "REVIEW"
    # illegal REVIEW -> ARCHIVED must fail (graph: REVIEW -> PUBLISHED|DRAFT)
    with pytest.raises(Exception):
        core.authoring_store.set_lifecycle(sid, "ARCHIVED")
    assert core.authoring_store.lifecycle_of(sid) == "REVIEW"
    # links validate targets
    from academic_core.domain import entities as E
    core.academic.add_university(E.University("university:u", "U"))
    with pytest.raises(Exception):
        core.authoring.link(sid, "subject", "subject:nope")
    core.academic.add_subject(E.Subject("subject:s", "", "S", "S"))
    core.authoring.link(sid, "subject", "subject:s")
    assert core.authoring_store.links_of(sid) == [
        {"target_kind": "subject", "target_id": "subject:s"}]
    with pytest.raises(Exception):
        core.authoring.link(sid, "knowledge-graph", "x")


def test_autosave_recover_cleanup(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("exam-notes")
    st = core.authoring.open(sid)
    st.execute(AU.UpdateText((0, 0), "unsaved work"))
    n = core.authoring.autosave(st, sid)
    assert n > 0
    rec = core.authoring.recover(sid)
    assert rec.doc.children[0].children[0].attrs["value"] == "unsaved work"
    # versions untouched by autosave
    assert len(core.records.get(sid).versions) == 1
    core.authoring.cleanup_autosave(sid)
    assert core.authoring.recover(sid) is None


def test_copy_paste_structural_and_explicit_degrade(tmp_path):
    core = _app(tmp_path)
    nodes = [A.heading(1, [A.text("H")]), A.equation("x^2", "latex", True)]
    payload = core.authoring.copy_nodes(nodes)
    back, warnings = core.authoring.paste_nodes("application/x-academic-ast", payload)
    assert back == nodes and warnings == ()
    md_nodes, warnings = core.authoring.paste_nodes("text/markdown", "# T\n\nx")
    assert md_nodes[0].kind == "heading" and warnings == ("reparsed from markdown",)
    with pytest.raises(ValueError):
        core.authoring.paste_nodes("text/html-unknown", "<p>x</p>")
    with pytest.raises(ValueError):
        core.authoring.paste_nodes("application/x-academic-ast", "{bad json")


def test_authored_indexed_and_searchable(tmp_path):
    core = _app(tmp_path)
    sid = core.authoring.create_from_template("lecture-notes")
    hits = core.fts.search("Objectius")
    assert [h["stable_id"] for h in hits] == [sid]
