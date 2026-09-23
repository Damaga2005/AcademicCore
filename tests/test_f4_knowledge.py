# SPDX-License-Identifier: MIT
"""F4.1 M6 — knowledge: teaching-guide extraction over F3/F3.1 ASTs with
provenance (golden vs REAL Gestion guia_docente.py) + F3.1 extractor reuse."""
import json
import os
from pathlib import Path

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.documents import syllabus as SY
from academic_core.domain import entities as E
from academic_core.errors import AcademicManagementError

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "gestion" / "golden_syllabus.json")
                    .read_text(encoding="utf-8"))


def make_pdf(lines: list[str]) -> bytes:
    """Minimal one-page text PDF (Helvetica, one line per Tj) — test only."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F1 10 Tf", "12 TL", "40 800 Td"] + [f"({esc(t)}) Tj T*" for t in lines]
    stream = "\n".join(ops + ["ET"]).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font"
            b" << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, x)


def _comp(c) -> tuple:
    return (c["nombre"], c["tipo"], float(c["porcentaje"]), c["pendiente_revision"])


@pytest.mark.parametrize("i", range(len(GOLDEN["cases"])))
def test_syllabus_port_matches_real_gestion(i):
    case = GOLDEN["cases"][i]
    exp = case["expected"]
    got = SY.analyze(case["text"])
    assert [(p.name, p.role or None) for p in got.professors] == [
        (p["nombre"], p["rol"]) for p in exp["profesores"]]
    assert len(got.schemes) == len(exp["esquemas"])
    for s, e in zip(got.schemes, exp["esquemas"]):
        assert (s.name, s.needs_review) == (e["nombre"], e["pendiente_revision"])
        assert (s.unparsed_text or None) == e["texto_sin_analizar"]
        assert [(c.name, c.kind, float(c.weight), c.needs_review) for c in s.components] == [
            _comp(c) for c in e["componentes"]]
        assert [(b.name, float(b.weight), b.needs_review,
                 [(c.name, c.kind, float(c.weight), c.needs_review) for c in b.components])
                for b in s.blocks] == [
            (b["nombre"], float(b["porcentaje"]), b["pendiente_revision"],
             [_comp(c) for c in b["componentes"]]) for b in e.get("bloques", [])]


def test_syllabus_is_bounded():
    with pytest.raises(SY.SyllabusError):
        SY.analyze("x" * (SY.MAX_TEXT + 1))
    # a pathological single line is truncated, never regex-bombed
    SY.analyze("SISTEMA DE CALIFICACIÓN\n" + "a " * 200_000 + "\n")


@pytest.fixture
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    c = AcademicApp(Settings.load())
    c.settings.ensure_dirs()
    ac = c.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Y1", "degree:g"))
    ac.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1"))
    c.svc.create_subject("Diseño Digital", "term:q1", acronym="DD")
    return c


GUIDE = ["PROFESORADO", "Profesorado responsable: Ana Perez", "Otros:", "Ana Perez - 10",
         "Luis Gil - 11, 12", "SISTEMA DE CALIFICACION",
         "Nota final = MAX(0.6*Examen_final + 0.4*Nota_lab, 0.3*Examen_parcial +"
         " 0.3*Examen_final + 0.4*Nota_lab)", "Nota_lab = 0.5*Practicas + 0.5*Control_lab",
         "RECURSOS", "Ninguno"]


def test_teaching_guide_pdf_to_subject_with_provenance(core):
    doc = core.material.add_document("subject:dd", make_pdf(GUIDE), "guia.pdf",
                                     category="guia_docente")
    prop = core.knowledge.analyze_syllabus(doc.resource_id)
    cur = core.records.get(doc.resource_id).current()
    assert prop.provenance == {"resource_id": doc.resource_id, "version": 1,
                               "content_hash": cur.content_hash, "parser": "pdf-native",
                               "parser_version": "3.0", "extractor": "syllabus/1"}
    assert [(p.name, p.role) for p in prop.professors] == [
        ("Ana Perez", "Responsable (grupo 10)"), ("Luis Gil", "Grupos 11, 12")]
    assert [s.name for s in prop.schemes] == ["Solo examen final", "Con examen parcial"]
    assert all(c.needs_review for s in prop.schemes for c in s.components)
    assert core.evaluation.schemes("subject:dd") == []  # analysis never writes
    with pytest.raises(AcademicManagementError):
        core.knowledge.apply_syllabus("subject:dd", prop)
    rep = core.knowledge.apply_syllabus("subject:dd", prop, confirmed=True)
    assert (rep.professors_created, rep.professors_linked, rep.schemes_created) == (2, 2, 2)
    schemes = core.evaluation.schemes("subject:dd")
    assert [len(s.blocks) for s in schemes] == [1, 1]
    assert [str(c.weight) for c in schemes[0].blocks[0].components] == ["50", "50"]
    again = core.knowledge.apply_syllabus("subject:dd", prop, confirmed=True)
    assert (again.professors_created, again.professors_linked) == (0, 0)


def test_unparsed_guide_is_skipped_not_invented(core):
    prop = core.knowledge.analyze_syllabus_text(
        "SISTEMA DE CALIFICACIÓN\nSe evaluará con una rúbrica.\nBIBLIOGRAFÍA\nx\n")
    assert prop.schemes[0].needs_review and prop.schemes[0].components == ()
    rep = core.knowledge.apply_syllabus("subject:dd", prop, confirmed=True)
    assert (rep.schemes_created, rep.skipped_for_review) == (0, 1)


def test_subject_knowledge_reuses_f31_extractors(core):
    md = ("# Circuitos\n\n**Ley de Ohm**: relación lineal entre tensión y corriente en un "
          "resistor.\n\n$$V = I R$$\n").encode()
    d = core.material.add_document("subject:dd", md, "ohm.md", category="apuntes")
    core.material.add_document("subject:dd", b"PK\x03\x04", "x.bin")  # kind=file: no AST
    k = core.knowledge.subject_knowledge("subject:dd")
    assert k.sources == (d.resource_id,)
    assert [t.term for t in k.terms] == ["Ley de Ohm"] and k.terms[0].source == d.resource_id
    assert any("V" in f.formula and f.source == d.resource_id for f in k.formulas)
    assert len(k.skipped) == 1
