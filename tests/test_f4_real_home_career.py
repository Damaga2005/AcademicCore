# SPDX-License-Identifier: MIT
"""F4.1 closure — Home shows only the present; Carrera covers every subject
once; subject detail works for each status."""
import pytest

from gestion_real_harness import SOURCES, certified


@pytest.mark.parametrize("source", SOURCES)
def test_home_and_career(source):
    rep, _ = certified(source)
    car = rep["career"]
    b, st = car["career_buckets"], car["source_states"]
    assert b["current"] + b["in_progress_elsewhere"] == st["cursando"]
    assert (b["approved"], b["failed"], b["not_taken"], b["not_chosen"]) == (
        st["superada"], st["no_superada"], st["pendiente"], st["no_elegida"])
    assert len(car["home"]["current_subjects"]) == b["current"]
    assert len(car["home"]["current_subjects"]) <= rep["inventory"]["tables"]["asignatura"]


@pytest.mark.parametrize("source", SOURCES)
def test_subject_detail_per_status(source):
    rep, _ = certified(source)
    details = rep["career"]["details"]
    present = {k for k, v in details.items() if v}
    if source == "synthetic":
        assert present == {"CURSANDO", "APROBADA", "SUSPENDIDA", "NO_CURSANDO"}
    for d in details.values():
        if d:
            assert d["subject"].startswith("subject:")
