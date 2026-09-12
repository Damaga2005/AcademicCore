"""Academic templates (Phase 5): functions returning structured AST.

Templates generate NODES, never hardcoded Markdown blocks. Each returns a
fresh `Document` with placeholder text the author replaces.
"""

from __future__ import annotations

from academic_core.documents import ast as A


def _sec(title: str, *body) -> A.Node:
    return A.section(title, (A.heading(2, [A.text(title)]), *body))


def _p(text: str) -> A.Node:
    return A.paragraph([A.text(text)])


def lecture_notes(topic: str = "Tema") -> A.Document:
    doc = A.Document(
        A.Metadata(title=f"Apunts — {topic}", origin="template:lecture-notes"),
        ({"parser": "template", "version": "5.0", "template": "lecture-notes"},),
        (A.heading(1, [A.text(f"Apunts — {topic}")]),
         _sec("Objectius", _p("…")),
         _sec("Conceptes clau", A.bullet_list([A.list_item([_p("…")])])),
         _sec("Fórmules", A.paragraph([A.equation("E = mc^2", "latex", True)])),
         _sec("Exemples", _p("…")),
         _sec("Dubtes", _p("…"))))
    A.validate(doc)
    return doc


def lab_report(title: str = "Informe de laboratori") -> A.Document:
    doc = A.Document(
        A.Metadata(title=title, origin="template:lab-report"),
        ({"parser": "template", "version": "5.0", "template": "lab-report"},),
        (A.heading(1, [A.text(title)]),
         _sec("Objectiu", _p("…")),
         _sec("Material", A.bullet_list([A.list_item([_p("…")])])),
         _sec("Procediment", A.bullet_list(
             [A.list_item([_p("Pas 1")]), A.list_item([_p("Pas 2")])], ordered=True)),
         _sec("Resultats", A.table(
             A.table_row([A.table_cell([A.text("Magnitud")], header=True),
                          A.table_cell([A.text("Valor")], header=True)]),
             [A.table_row([A.table_cell([A.text("…")]), A.table_cell([A.text("…")])])])),
         _sec("Conclusions", _p("…"))))
    A.validate(doc)
    return doc


def assignment_doc(title: str = "Enunciat") -> A.Document:
    doc = A.Document(
        A.Metadata(title=title, origin="template:assignment"),
        ({"parser": "template", "version": "5.0", "template": "assignment"},),
        (A.heading(1, [A.text(title)]),
         _sec("Enunciat", _p("…")),
         _sec("Requisits", A.bullet_list([A.list_item([_p("…")])])),
         _sec("Lliurament", _p("…"))))
    A.validate(doc)
    return doc


def project_report(title: str = "Memòria del projecte") -> A.Document:
    doc = A.Document(
        A.Metadata(title=title, origin="template:project-report"),
        ({"parser": "template", "version": "5.0", "template": "project-report"},),
        (A.heading(1, [A.text(title)]),
         _sec("Introducció", _p("…")),
         _sec("Disseny", _p("…")),
         _sec("Implementació", A.code_block("…", "")),
         _sec("Resultats", _p("…")),
         _sec("Bibliografia", A.bullet_list([A.list_item([_p("…")])]))))
    A.validate(doc)
    return doc


def exam_notes(title: str = "Resum d'examen") -> A.Document:
    doc = A.Document(
        A.Metadata(title=title, origin="template:exam-notes"),
        ({"parser": "template", "version": "5.0", "template": "exam-notes"},),
        (A.heading(1, [A.text(title)]),
         _sec("Temari", A.bullet_list([A.list_item([_p("…")])])),
         _sec("Fórmules clau", A.paragraph([A.equation("…", "latex", True)])),
         _sec("Errors freqüents", A.quote([_p("…")]))))
    A.validate(doc)
    return doc


TEMPLATES = {"lecture-notes": lecture_notes, "lab-report": lab_report,
             "assignment": assignment_doc, "project-report": project_report,
             "exam-notes": exam_notes}
