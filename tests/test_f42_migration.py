# SPDX-License-Identifier: MIT
"""F4.2 legacy consumption: favourites/recents payloads -> history."""
import hashlib
import os
import sqlite3

import gestion_legacy_fixture as G
from academic_core.application import AcademicApp
from academic_core.application.f42_legacy import (
    consume_f42_payloads, resolve_legacy_reference,
)
from academic_core.application.search_history import SearchHistoryService
from academic_core.config import Settings
from academic_core.infrastructure import LegacyRepository, SearchHistoryRepository


def _app(tmp_path, tag="data"):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _migrated(tmp_path):
    db, root = G.build(tmp_path / "legacy")
    core = _app(tmp_path)
    from academic_core.application.gestion_migration import MigrationOptions
    rep = core.migration.apply(
        db, MigrationOptions(documents_dir=str(root),
                             degree_total_credits="240",
                             final_project_names=("Trabajo de Fin de Grado",)),
        snapshot_dir=tmp_path / "snap")
    assert rep.lossless
    return core, db, root


def _titles(core):
    return {
        "asignatura": lambda sid: core.academic.get_subject(sid).name,
        "documento": lambda rid: next(
            d.filename for d in core.material.documents("subject:dd")
            if d.resource_id == rid),
    }


def test_fixture_favourite_and_recent_migrate(tmp_path):
    core, _, _ = _migrated(tmp_path)
    history = SearchHistoryService(SearchHistoryRepository(core.db))
    rep = consume_f42_payloads(core.migration.legacy, history, _titles(core))
    assert rep == {"migrated": 2, "unresolved": [], "warnings": []}
    favs = history.list_favourites()
    assert [(f.kind, f.ref, f.title) for f in favs] == [
        ("asignatura", "subject:dd", "Diseño Digital")]
    recs = history.list_recents()
    assert [(r.kind, r.ref, r.label, r.url) for r in recs] == [
        ("documento", recs[0].ref, "tema1.pdf", "/vista/documentos/1")]
    assert recs[0].ref.startswith("resource:")


def test_mapping_correct_unmapped_preserved_rerun_clean(tmp_path):
    core, _, _ = _migrated(tmp_path)
    history = SearchHistoryService(SearchHistoryRepository(core.db))
    mapped = core.migration.legacy.all_mapped("gestion-academica")
    assert resolve_legacy_reference("asignatura", 2, mapped)[0] == "RESOLVED"
    assert resolve_legacy_reference("asignatura", 999, mapped)[0] == "UNRESOLVED"
    assert resolve_legacy_reference("etiqueta", 1, mapped)[0] == "UNRESOLVED"
    assert resolve_legacy_reference("inventado", 1, mapped)[0] == "UNRESOLVED"
    # unmapped legacy row keeps its payload verbatim
    core.migration.legacy.keep("gestion-academica", "busqueda_favorito", 77,
                               {"tipo_entidad": "asignatura", "entidad_id": 999},
                               deferred_to="F4.2", reason="t",
                               migration_version="gestion-migration/3")
    rep = consume_f42_payloads(core.migration.legacy, history)
    assert rep["migrated"] == 2
    assert [u["source_id"] for u in rep["unresolved"]] == ["77"]
    kept = {p["source_id"]: p for p in core.migration.legacy.payloads(
        "gestion-academica", "busqueda_favorito")}
    assert kept["77"]["payload"]["entidad_id"] == 999  # payload preserved
    again = consume_f42_payloads(core.migration.legacy, history)
    assert again == {"migrated": 0, "unresolved": again["unresolved"],
                     "warnings": again["warnings"]}
    assert len(again["unresolved"]) == 1  # same single unresolved row


def test_gestion_source_untouched(tmp_path):
    core, db, _ = _migrated(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    history = SearchHistoryService(SearchHistoryRepository(core.db))
    consume_f42_payloads(core.migration.legacy, history)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert isinstance(core.migration.legacy, LegacyRepository)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM busqueda_favorito"
                                       ).fetchone()[0] == 1


def test_rollback_drops_only_f42_objects_and_data_rederives(tmp_path):
    """Documented 014 rollback: DROP the two F4.2 tables (payloads intact),
    F4.1 data untouched, re-running consume restores the rows."""
    core, _, _ = _migrated(tmp_path)
    history = SearchHistoryService(SearchHistoryRepository(core.db))
    titles = {"asignatura": lambda sid: core.academic.get_subject(sid).name}
    assert consume_f42_payloads(core.migration.legacy, history, titles)["migrated"] == 2
    cx = sqlite3.connect(core.db.path)
    before_f41 = cx.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    cx.execute("DROP TABLE saved_searches")
    cx.execute("DROP TABLE recent_searches")
    cx.execute("DELETE FROM schema_version WHERE version=14")
    cx.commit()
    assert cx.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == before_f41
    assert cx.execute("SELECT COUNT(*) FROM legacy_payloads WHERE deferred_to='F4.2'"
                      ).fetchone()[0] == 2  # payloads intact: re-derivable
    cx.close()
    import academic_core.infrastructure.database as dbmod
    dbmod.Database(core.db.path).connect().close()  # 014 re-applies
    rep = consume_f42_payloads(core.migration.legacy, history, titles)
    assert rep["migrated"] == 2 and rep["unresolved"] == []
    assert len(history.list_favourites()) == 1
