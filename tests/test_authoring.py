"""Authoring model: commands, undo/redo, lifecycle, determinism."""
import pytest

from academic_core.documents import ast as A
from academic_core.domain import authoring as AU


def doc():
    return A.Document(A.Metadata(title="T"), (),
                      (A.heading(1, [A.text("H")]),
                       A.paragraph([A.text("hello")])))


def test_insert_delete_replace_move():
    st = AU.AuthoringDocument(doc())
    st.execute(AU.InsertNode((2,), A.paragraph([A.text("new")])))
    assert len(st.doc.children) == 3
    st.execute(AU.DeleteNode((0,)))
    assert st.doc.children[0].kind == "paragraph"
    st.execute(AU.ReplaceNode((0,), A.heading(2, [A.text("H2")])))
    assert st.doc.children[0].attrs["level"] == 2
    st.execute(AU.MoveNode((0,), (2,)))
    assert st.doc.children[1].attrs["level"] == 2
    assert st.dirty and st.revision == 4


def test_update_text_metadata_attribute():
    st = AU.AuthoringDocument(doc())
    st.execute(AU.UpdateText((1, 0), "bye"))
    assert st.doc.children[1].children[0].attrs["value"] == "bye"
    st.execute(AU.UpdateMetadata(A.Metadata(title="T2")))
    assert st.doc.meta.title == "T2"
    st.execute(AU.SetAttribute((0,), "level", 3))
    assert st.doc.children[0].attrs["level"] == 3
    with pytest.raises(AU.AuthoringError):
        st.execute(AU.SetAttribute((0,), "kind", "paragraph"))
    with pytest.raises(AU.AuthoringError):
        st.execute(AU.UpdateText((0,), "x"))  # heading is not text


def test_undo_redo_roundtrip_and_invalidation():
    st = AU.AuthoringDocument(doc())
    before = st.doc
    st.execute(AU.UpdateText((1, 0), "one"))
    st.execute(AU.UpdateText((1, 0), "two"))
    assert st.undo() and st.undo()
    assert st.doc == before
    assert st.redo() and st.redo()
    assert st.doc.children[1].children[0].attrs["value"] == "two"
    st.undo()
    st.execute(AU.UpdateText((1, 0), "three"))  # invalidates redo
    assert not st.redo()
    assert st.doc.children[1].children[0].attrs["value"] == "three"
    # history cap
    for i in range(AU.UNDO_LIMIT + 10):
        st.execute(AU.UpdateText((1, 0), f"v{i}"))
    assert len(st._undo) == AU.UNDO_LIMIT


def test_lifecycle_graph():
    assert AU.transition("DRAFT", "REVIEW") == "REVIEW"
    assert AU.transition("REVIEW", "PUBLISHED") == "PUBLISHED"
    assert AU.transition("PUBLISHED", "ARCHIVED") == "ARCHIVED"
    assert AU.transition("DRAFT", "ARCHIVED") == "ARCHIVED"
    for bad in (("DRAFT", "PUBLISHED"), ("ARCHIVED", "DRAFT"), ("X", "DRAFT")):
        with pytest.raises(AU.AuthoringError):
            AU.transition(*bad)


def test_invalid_paths_rejected():
    st = AU.AuthoringDocument(doc())
    with pytest.raises(AU.AuthoringError):
        st.execute(AU.DeleteNode(()))
    with pytest.raises(AU.AuthoringError):
        st.execute(AU.InsertNode((9,), A.paragraph([])))
    with pytest.raises(AU.AuthoringError):
        st.execute(AU.MoveNode((0,), (0, 5)))
