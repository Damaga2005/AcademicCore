"""Validation service + templates + in-document search."""
from academic_core.documents import ast as A
from academic_core.documents import search as S
from academic_core.documents import templates as T
from academic_core.documents.validate import validate_document


def test_templates_are_valid_structured_ast():
    for name, fn in T.TEMPLATES.items():
        doc = fn()
        A.validate(doc)
        assert doc.meta.title and doc.history[0]["template"] == name
        assert not validate_document(doc)
    assert set(T.TEMPLATES) == {"lecture-notes", "lab-report", "assignment",
                                "project-report", "exam-notes"}


def test_validation_reports_never_sanitizes():
    doc = A.Document(A.Metadata(), (),
                     (A.paragraph([A.link("", [A.text("x")])]),
                      A.paragraph([A.link("javascript:evil()", [A.text("y")])]),
                      A.paragraph([A.image("cas:zzz", "a")]),
                      A.paragraph([A.image("cas:" + "ab" * 32, "b")]),
                      A.paragraph([A.equation("", "latex", False)]),
                      A.heading(1, [A.text("a")]),
                      A.heading(4, [A.text("b")])))
    codes = {(i.code, i.severity) for i in validate_document(doc, lambda h: False)}
    assert ("link_empty", "error") in codes
    assert ("link_unsafe", "error") in codes
    assert ("image_ref", "error") in codes
    assert ("image_missing", "error") in codes
    assert ("equation_empty", "error") in codes
    assert ("metadata", "warning") in codes  # empty title
    assert ("headings", "warning") in codes  # 1 -> 4 jump
    # source is preserved even when invalid: validation reports, never rewrites
    assert doc.children[4].children[0].attrs["source"] == ""


def test_validation_catches_javascript_scheme_with_embedded_whitespace():
    """Regression: `jav\tascript:` etc. must not bypass the javascript: check."""
    doc = A.Document(A.Metadata(), (),
                     (A.paragraph([A.link("jav\tascript:alert(1)", [A.text("x")])]),
                      A.paragraph([A.link("jav\nascript:alert(2)", [A.text("y")])]),
                      A.paragraph([A.link("jav\rascript:alert(3)", [A.text("z")])])))
    codes = [i.code for i in validate_document(doc, lambda h: False)]
    assert codes.count("link_unsafe") == 3


def test_search_deterministic():
    doc = A.Document(A.Metadata(title="Guia"), (),
                     (A.heading(1, [A.text("Introducció")]),
                      A.paragraph([A.text("El corrent altern i el corrent continu")]),
                      A.paragraph([A.text("res més")]),))
    hits = S.search_document(doc, "corrent")
    assert [(p, k) for p, k, _ in hits] == [((1,), "paragraph"), ((1,), "paragraph")]
    assert S.search_document(doc, "guia")[0][1] == "metadata"
    assert S.search_document(doc, "") == []
    assert S.search_document(doc, "corrent") == hits  # deterministic
