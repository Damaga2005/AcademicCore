"""F3 compatibility: v1 golden documents stay readable (no silent breakage)."""
import json

from academic_core.documents import ast as A
from academic_core.documents.validate import validate_document

# Minimal faithful v1 shape (as produced by F3 parsers/serializers).
GOLDEN_V1 = {
    "schema_version": 1,
    "metadata": {"title": "F3 doc", "author": "", "language": "ca",
                 "created_at": "", "modified_at": "", "source_resource_id": "r",
                 "source_version": 1, "origin": "html", "encoding": "utf-8",
                 "extra": {}},
    "history": [{"parser": "html-parser", "version": "3.0"}],
    "children": [
        {"kind": "heading", "attrs": {"level": 1},
         "children": [{"kind": "text", "attrs": {"value": "H"}, "children": []}]},
        {"kind": "paragraph", "attrs": {},
         "children": [{"kind": "equation",
                       "attrs": {"source": "x^2", "format": "latex",
                                 "display": False}, "children": []}]},
        {"kind": "table", "attrs": {"caption": ""},
         "children": [
             {"kind": "table_row", "attrs": {},
              "children": [{"kind": "table_cell",
                            "attrs": {"header": True, "colspan": 1,
                                      "rowspan": 1, "align": ""},
                            "children": [{"kind": "text",
                                          "attrs": {"value": "c"},
                                          "children": []}]}]}]},
    ],
}


def test_golden_v1_parses_validates_and_reserializes():
    doc = A.Document.from_dict(json.loads(json.dumps(GOLDEN_V1)))
    A.validate(doc)
    assert validate_document(doc) == [] or all(
        i.severity == "warning" for i in validate_document(doc))
    again = A.Document.from_dict(doc.to_dict())
    assert again == doc


def test_unknown_future_kind_is_rejected_loudly():
    bad = json.loads(json.dumps(GOLDEN_V1))
    bad["children"].append({"kind": "hologram", "attrs": {}, "children": []})
    try:
        A.Document.from_dict(bad)
        raised = False
    except A.AstError:
        raised = True
    assert raised
