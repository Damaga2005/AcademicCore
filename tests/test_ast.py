"""AST: creation, validation, deterministic serialization, schema, rejects."""
import json

import pytest

from academic_core.documents import ast as A


def sample():
    return A.Document(
        A.Metadata(title="T", source_resource_id="resource:g:r:00001"),
        ({"parser": "x", "version": "1"},),
        (A.heading(1, [A.text("Hi")]),
         A.paragraph([A.text("a "), A.strong([A.text("b")]),
                      A.equation("x^2", "latex", False)]),
         A.table(A.table_row([A.table_cell([A.text("h")], header=True)]),
                 [A.table_row([A.table_cell([A.text("c")], colspan=2)])])))


def test_creation_and_validate():
    A.validate(sample())


def test_serialization_roundtrip_and_deterministic():
    d1 = sample().to_dict()
    assert d1["schema_version"] == 1
    s1 = json.dumps(d1, sort_keys=True)
    doc2 = A.Document.from_dict(json.loads(s1))
    assert json.dumps(doc2.to_dict(), sort_keys=True) == s1
    assert doc2.meta.title == "T"


def test_schema_version_rejected():
    d = sample().to_dict()
    d["schema_version"] = 999
    with pytest.raises(A.AstError):
        A.Document.from_dict(d)


def test_invalid_nodes_rejected():
    with pytest.raises(A.AstError):
        A.Node("script", {}, ())
    with pytest.raises(A.AstError):
        A.Node.from_dict({"kind": "nope", "attrs": {}, "children": []})
    with pytest.raises(A.AstError):
        A.heading(9, [])
    with pytest.raises(A.AstError):
        A.table_cell([], colspan=0)
    with pytest.raises(A.AstError):
        A.equation("x", format="weird")
    bad = A.Document(A.Metadata(), (), (A.table(A.table_row([A.text("x")])),))
    with pytest.raises(A.AstError):
        A.validate(bad)  # row children must be cells
    with pytest.raises(A.AstError):
        A.Document.from_dict({"schema_version": 1, "children": [],
                              "history": [{"no": "parser"}]})


def test_image_is_reference_not_blob():
    img = A.image("cas:" + "ab" * 32, "alt")
    assert len(img.attrs["blob_ref"]) == 68 and img.kind == "image"
