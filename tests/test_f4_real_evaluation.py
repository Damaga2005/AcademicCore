# SPDX-License-Identifier: MIT
"""F4.1 closure — Gestion vs AcademicCore evaluation on EVERY real subject
(F4.1_REAL_EVALUATION_REPORT content)."""
import pytest

from gestion_real_harness import SOURCES, certified


@pytest.mark.parametrize("source", SOURCES)
def test_evaluation_equivalence_every_subject(source):
    rep, _ = certified(source)
    ev = rep["evaluation"]
    assert ev["mismatches"] == 0
    assert ev["subjects"] == rep["inventory"]["tables"]["asignatura"]
    assert all(r["equal"] for r in ev["rows"])
    assert {r["core"]["state"] for r in ev["rows"]} <= {
        "aprobada", "suspendida", "en_progreso", "sin_evaluar"}
