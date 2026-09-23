# SPDX-License-Identifier: MIT
"""F4.1 M2 — assessment schemes/blocks/components/min grade (Decimal).

Golden: tests/fixtures/gestion/golden_eval.json holds 400 seeded cases whose
expected outputs were produced by the REAL Gestion-Academica@187a614
`calcular_estado_notas` / `esquemas_con_ganador` (generate_golden_eval.py).
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.gestion_oracle import gestion_estado_notas
from academic_core.domain import evaluation as EV
from academic_core.domain.entities import DomainError

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "gestion" / "golden_eval.json")
                    .read_text(encoding="utf-8"))
dec_text = EV.legacy_float_text
MEAN_TOL = Decimal("0.0001")  # ADR-0011: HALF_UP vs float round, 4dp
PCT_TOL = Decimal("0.01")


def _to_schemes(case) -> list[EV.AssessmentScheme]:
    rows = case["input"]
    out = []
    n = 0

    def nid(kind):
        nonlocal n
        n += 1
        return f"{kind}:s:{ {'scheme': 'sch', 'block': 'blk', 'component': 'cmp'}[kind]}:{n:05d}"

    for e in sorted(rows["esquemas"], key=lambda e: (e["orden"], e["id"])):
        sc = EV.AssessmentScheme(nid("scheme"), "subject:s", f"E{e['id']}", order=e["orden"])
        blocks = {}
        for b in sorted((b for b in rows["bloques"] if b["esquema_id"] == e["id"]),
                        key=lambda b: (b["orden"], b["id"])):
            blocks[b["id"]] = EV.AssessmentBlock(nid("block"), "B", dec_text(b["porcentaje"]),
                                                 order=b["orden"])
            sc.blocks.append(blocks[b["id"]])
        for c in sorted((c for c in rows["componentes"] if c["esquema_id"] == e["id"]),
                        key=lambda c: (c["orden"], c["id"])):
            comp = EV.AssessmentComponent(nid("component"), "C", dec_text(c["porcentaje"]),
                                          "otro", dec_text(c["nota"]),
                                          dec_text(c["nota_minima"]), c["orden"])
            (blocks[c["bloque_id"]].components if c["bloque_id"] else sc.components).append(comp)
        out.append(sc)
    return out


def test_golden_has_real_coverage():
    states = {c["expected"]["estado_notas"] for c in GOLDEN["cases"]}
    assert states == {"aprobada", "suspendida", "en_progreso", "sin_evaluar"}
    assert sum(c["expected"]["minimo_incumplido"] for c in GOLDEN["cases"]) > 10
    assert len(GOLDEN["cases"]) == 400


@pytest.mark.parametrize("i", range(400))
def test_oracle_port_equals_real_gestion(i):
    """The float oracle used by migration validation is an exact port."""
    c = GOLDEN["cases"][i]
    r = c["input"]
    got = gestion_estado_notas(r["asignatura"], r["esquemas"], r["bloques"], r["componentes"])
    assert got == c["expected"]


@pytest.mark.parametrize("i", range(400))
def test_decimal_evaluation_matches_gestion_golden(i):
    c = GOLDEN["cases"][i]
    exp = c["expected"]
    ev = EV.evaluate_subject(_to_schemes(c), dec_text(c["input"]["asignatura"]["nota_final"]))
    assert ev.state == exp["estado_notas"]
    assert ev.evaluated_items == exp["evaluaciones_realizadas"]
    assert ev.pending_items == exp["evaluaciones_pendientes"]
    assert ev.min_grade_violated == exp["minimo_incumplido"]
    if exp["nota_actual"] is None:
        assert ev.grade is None
    else:
        assert abs(ev.grade - Decimal(str(exp["nota_actual"]))) <= MEAN_TOL
    assert abs(ev.percent_evaluated - Decimal(str(exp["porcentaje_evaluado"]))) <= PCT_TOL
    flags = [o.applied for o in ev.schemes]
    assert flags == c["winner_flags"]


def _c(n, w, s=None, m=None, order=0):
    return EV.AssessmentComponent(f"component:x:cmp:{n:05d}", f"c{n}", w, "otro", s, m, order)


def _scheme(n, comps=(), blocks=(), order=0):
    return EV.AssessmentScheme(f"scheme:x:sch:{n:05d}", "subject:x", f"s{n}", list(comps),
                               list(blocks), order)


def test_block_weight_is_relative_to_block():
    blk = EV.AssessmentBlock("block:x:blk:00001", "Lab", "40",
                             [_c(1, "50", "10"), _c(2, "50", "6")])
    sc = _scheme(1, [_c(3, "60", "5")], [blk])
    r = sc.result()
    assert blk.result().media_ponderada == Decimal("8.0000")
    assert r.aggregate.media_ponderada == Decimal("6.2000")  # 0.6*5 + 0.4*8
    assert r.complete


def test_min_grade_forces_fail_even_with_passing_mean():
    sc = _scheme(1, [_c(1, "50", "10"), _c(2, "50", "3.9", "4")])
    ev = EV.evaluate_subject([sc])
    assert ev.grade == Decimal("6.9500") and ev.min_grade_violated and ev.state == "suspendida"


def test_final_override_wins_and_counts_items():
    sc = _scheme(1, [_c(1, "50", "2"), _c(2, "50")])
    ev = EV.evaluate_subject([sc], "5.5")
    assert (ev.state, ev.grade, ev.evaluated, ev.percent_evaluated) == (
        "aprobada", Decimal("5.5"), True, Decimal("100.00"))
    assert (ev.evaluated_items, ev.pending_items) == (1, 1)


def test_partial_is_in_progress_never_projected():
    ev = EV.evaluate_subject([_scheme(1, [_c(1, "30", "10"), _c(2, "70")])])
    assert ev.state == "en_progreso" and ev.grade is None
    assert ev.percent_evaluated == Decimal("30.00")


def test_winner_first_on_ties_and_single_scheme_always_applies():
    a = _scheme(1, [_c(1, "100", "7")], order=0)
    b = _scheme(2, [_c(2, "100", "7")], order=1)
    assert [o.applied for o in EV.rank_schemes([b, a])] == [True, False]
    assert [o.applied for o in EV.rank_schemes([_scheme(3, [_c(3, "100")])])] == [True]
    assert [o.applied for o in EV.rank_schemes([_scheme(4, [_c(4, "100")]),
                                                _scheme(5, [_c(5, "100")], order=1)])] == [
        False, False]


def test_required_score():
    sc = _scheme(1, [_c(1, "40", "4"), _c(2, "60")])
    assert EV.required_score(sc) == Decimal("5.67")
    assert EV.required_score(_scheme(2, [_c(3, "100", "9")])) is None


@pytest.mark.parametrize("bad", [{"weight": "101"}, {"weight": "-1"}, {"score": "10.5"},
                                 {"weight": 33.3}, {"weight": "NaN"}, {"weight": "abc"},
                                 {"min_grade": "11"}])
def test_invalid_values_rejected(bad):
    kw = {"weight": "10", "score": None, "min_grade": None} | bad
    with pytest.raises(DomainError):
        EV.AssessmentComponent("component:x:cmp:00001", "c", kw["weight"], "otro",
                               kw["score"], kw["min_grade"])


def test_rounding_is_half_up_decimal_not_float():
    # 3 x 33.33/33.33/33.34 with 5/5/6 -> exact 5.3334 (float path gives 5.3334 too),
    # and a HALF_UP boundary where binary floats would round-half-even.
    sc = _scheme(1, [_c(1, "50", "5.00005"), _c(2, "50", "5.00005")])
    assert sc.result().aggregate.media_ponderada == Decimal("5.0001")


def test_dec_text_is_exact_for_legacy_floats():
    assert dec_text(33.33) == "33.33" and dec_text(66.67) == "66.67"
    assert dec_text(6.0) == "6" and dec_text(None) is None and dec_text(0.1) == "0.1"
