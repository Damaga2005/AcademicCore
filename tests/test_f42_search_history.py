# SPDX-License-Identifier: MIT
"""F4.2 favourites/recents: CRUD, idempotence, limits, ordering, validation."""
import os

import pytest

from academic_core.application import AcademicApp
from academic_core.application.search_history import SearchHistoryService
from academic_core.config import Settings
from academic_core.domain import planning as PL
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure import SearchHistoryRepository


def _svc(tmp_path, tag="data"):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return SearchHistoryService(SearchHistoryRepository(core.db))


def test_add_is_favourite_remove(tmp_path):
    svc = _svc(tmp_path)
    assert svc.add_favourite("asignatura", "subject:x", "Álgebra",
                             created="2026-09-01T10:00:00") is True
    assert svc.is_favourite("asignatura", "subject:x") is True
    assert svc.is_favourite("asignatura", "subject:y") is False
    assert svc.remove_favourite("asignatura", "subject:x") is True
    assert svc.is_favourite("asignatura", "subject:x") is False


def test_add_duplicate_is_noop_and_remove_missing_is_idempotent(tmp_path):
    svc = _svc(tmp_path)
    assert svc.add_favourite("tarea", "task:1", "Parcial",
                             created="2026-09-01T10:00:00") is True
    assert svc.add_favourite("tarea", "task:1", "Parcial otro título",
                             created="2026-09-02T10:00:00") is False
    assert svc.list_favourites()[0].title == "Parcial"
    assert svc.remove_favourite("tarea", "task:nope") is False


def test_favourites_ordering_is_deterministic(tmp_path):
    svc = _svc(tmp_path)
    svc.add_favourite("tarea", "task:b", "B", created="2026-09-02T10:00:00")
    svc.add_favourite("asignatura", "subject:a", "A", created="2026-09-02T10:00:00")
    svc.add_favourite("nota_al_vuelo", "note:1", "N", created="2026-09-01T10:00:00")
    got = [(f.kind, f.ref) for f in svc.list_favourites()]
    assert got == [("asignatura", "subject:a"), ("tarea", "task:b"),
                   ("nota_al_vuelo", "note:1")]


@pytest.mark.parametrize("kind,ref,title", [
    ("no_existe", "x", "T"), ("asignatura", "", "T"), ("asignatura", "x", ""),
    ("asignatura", "  ", "T"),
])
def test_favourite_validation(tmp_path, kind, ref, title):
    svc = _svc(tmp_path)
    with pytest.raises(AcademicManagementError) as e:
        svc.add_favourite(kind, ref, title)
    assert e.value.code == "AC-ACD-004"


def test_recents_insert_update_upsert_and_label_url(tmp_path):
    svc = _svc(tmp_path)
    svc.record_recent("documento", "resource:1", "tema1.pdf", "/vista/d/1",
                      accessed="2026-09-01T10:00:00")
    svc.record_recent("documento", "resource:1", "tema1 v2", "/vista/d/1b",
                      accessed="2026-09-02T10:00:00")
    got = svc.list_recents()
    assert len(got) == 1  # upsert: single row
    assert (got[0].label, got[0].url, got[0].accessed) == (
        "tema1 v2", "/vista/d/1b", "2026-09-02T10:00:00")


def test_recents_limit_trim_and_ordering(tmp_path):
    svc = _svc(tmp_path)
    for i in range(17):
        svc.record_recent("tarea", f"task:{i:02d}", f"T{i}", f"/u/{i}",
                          accessed=f"2026-09-{i + 1:02d}T10:00:00")
    got = svc.list_recents()
    assert len(got) == PL.RECENT_SEARCH_LIMIT == 15
    assert got[0].ref == "task:16" and got[-1].ref == "task:02"
    assert [r.accessed for r in got] == sorted(
        (r.accessed for r in got), reverse=True)


def test_recents_deterministic_and_duplicate_validation(tmp_path):
    svc = _svc(tmp_path)
    for _ in range(2):
        svc.record_recent("hito", "milestone:1", "B2", "/vista/h",
                          accessed="2026-09-03T10:00:00")
    assert len(svc.list_recents()) == 1
    with pytest.raises(AcademicManagementError):
        svc.record_recent("hito", "milestone:1", "", "/vista/h")
    with pytest.raises(AcademicManagementError):
        svc.record_recent("hito", "milestone:1", "B2", "")
    with pytest.raises(AcademicManagementError):
        svc.record_recent("inventado", "x", "L", "/u")


def test_domain_entities_reject_bad_values():
    with pytest.raises(DomainError):
        PL.SavedSearch("asignatura", "", "T")
    with pytest.raises(DomainError):
        PL.RecentSearch("asignatura", "r", "L", "")
