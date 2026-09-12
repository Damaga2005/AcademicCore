"""Grading equivalence with Gestion-Academica (documented Decimal divergence).

`orig_aggregate` re-implements the ORIGINAL semantics literally (float +
round(), media over scored only) so the test pins behavior, not prose.
Academic Core uses Decimal + ROUND_HALF_UP (ADR-0011); agreement must be
within 0.005 (porcentaje) / 0.00005 (media) and exact on typical cases.
"""
from decimal import Decimal

from academic_core.domain import grading as G


def orig_aggregate(items):
    con = [(w, n) for w, n in items if n is not None]
    total = sum(w for w, _ in items)
    ev = sum(w for w, _ in con)
    pct = round((ev / total) * 100, 2) if total else 0.0
    media = round(sum(w * n for w, n in con) / ev, 4) if con and ev > 0 else None
    return total, ev, pct, media


def as_scored(items):
    return [G.Scored(Decimal(str(w)), Decimal(str(n)) if n is not None else None)
            for w, n in items]


CASES = [
    [(40.0, 7.5), (60.0, None)],          # partial evaluation
    [(40.0, 7.5), (60.0, 5.25)],          # full coverage
    [(30.0, 9.0), (30.0, 8.0), (40.0, 7.0)],
    [(100.0, 5.0)],                        # single component
    [(50.0, None), (50.0, None)],          # nothing scored
    [(33.33, 6.66), (33.33, 7.77), (33.34, 8.88)],  # awkward decimals
]


def test_equivalence_within_tolerance():
    for case in CASES:
        t, e, p, m = orig_aggregate(case)
        r = G.aggregate(as_scored(case))
        assert abs(float(r.peso_total) - t) < 1e-9
        assert abs(float(r.porcentaje_evaluado) - p) <= 0.005
        if m is None:
            assert r.media_ponderada is None
        else:
            assert abs(float(r.media_ponderada) - m) <= 0.00005


def test_typical_cases_exact():
    r = G.aggregate(as_scored([(40.0, 7.5), (60.0, None)]))
    assert (r.peso_total, r.peso_evaluado, r.porcentaje_evaluado, r.media_ponderada) == \
        (Decimal(100), Decimal(40), Decimal("40.00"), Decimal("7.5000"))
    r = G.aggregate(as_scored([(40.0, 7.5), (60.0, 5.25)]))
    assert r.media_ponderada == Decimal("6.1500")


def test_blocks_and_winner_rule():
    block = G.aggregate_block(Decimal(40), as_scored([(50.0, 8.0), (50.0, 6.0)]))
    assert block == G.Scored(Decimal(40), Decimal("7.0000"))
    a = G.aggregate(as_scored([(100.0, 6.15)]))
    b = G.aggregate(as_scored([(100.0, 7.0)]))
    picked = G.pick_winner([("continua", a), ("final", b)])
    assert [p.applied for p in picked] == [False, True]
    lonely = G.pick_winner([("unica", a)])
    assert lonely[0].applied is True
    none = G.pick_winner([("x", G.aggregate(as_scored([(100.0, None)]))),
                          ("y", G.aggregate(as_scored([(100.0, None)])))])
    assert [p.applied for p in none] == [False, False]


def test_final_verdict_states():
    full = G.aggregate(as_scored([(100.0, 4.9)]))
    v = G.final_verdict([("c", full)], None)
    assert (v.grade, v.evaluated, v.state) == (Decimal("4.9000"), True, "suspendida")
    part = G.aggregate(as_scored([(40.0, 9.0), (60.0, None)]))
    v = G.final_verdict([("c", part)], None)
    assert (v.grade, v.evaluated, v.state) == (None, False, "en_progreso")
    v = G.final_verdict([("c", part)], Decimal("5.0"))
    assert (v.evaluated, v.state) == (True, "aprobada")
    v = G.final_verdict([], None)
    assert v.state == "sin_evaluar"
