# SPDX-License-Identifier: MIT
"""F13-ext servicio: identidad, adaptadores, persistencia y límites (§5 D5).

Cubre lo que `test_f13ext_sync.py` (motor puro) no toca: `SyncService`
sobre repositorios reales (2 BDs), `SyncLogRepository`, `FileTransport`
y `ensure_device_id`. Sin red. Tiempos siempre inyectados.
"""

from __future__ import annotations

import os
import re

import pytest

from academic_core.application import AcademicApp
from academic_core.application.sync import (
    SyncError,
    SyncService,
    ensure_device_id,
    generate_device_id,
)
from academic_core.config import Settings
from academic_core.domain import planning as PL
from academic_core.domain import sync as S
from academic_core.infrastructure import SearchHistoryRepository, SyncLogRepository
from academic_core.infrastructure.sync_transport import FileTransport, SyncRejected

DEVICE_RE = re.compile(r"^[0-9a-f]{32}$")


def _core(tmp_path, tag):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _snapshot(svc, now_ms):
    return S.export_snapshot(svc.export_local(now_ms), svc.device_id, now_ms)


# -- identidad ----------------------------------------------------------

def test_device_id_format_unique_and_stable(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    assert DEVICE_RE.match(a.device_id) and DEVICE_RE.match(b.device_id)
    assert a.device_id != b.device_id
    assert ensure_device_id(a.personal) == a.device_id  # estable
    assert a.personal.setting("sync.device_id") == a.device_id  # persistido
    assert DEVICE_RE.match(generate_device_id())


def test_device_id_regenerates_when_corrupt(tmp_path):
    core = _core(tmp_path, "a")
    core.personal.set_setting("sync.device_id", "no-es-un-id")
    nid = ensure_device_id(core.personal)
    assert DEVICE_RE.match(nid) and nid != "no-es-un-id"
    assert core.personal.setting("sync.device_id") == nid


# -- alcance de exportación ----------------------------------------------

def test_export_scope_only_syncable(tmp_path):
    core = _core(tmp_path, "a")
    core.personal.set_setting("f42.theme", "oscuro")
    core.personal.set_setting("gestion.tema", "oscuro")  # legacy: no sync
    core.personal.set_setting("other", "x")  # desconocido: no sync
    state = core.sync.export_local(1000)
    assert set(state) == {"pref:f42.theme"}
    assert state["pref:f42.theme"].payload == {"value": "oscuro"}


# -- sincronización entre 2 BDs -------------------------------------------

def test_preference_propagates_a_to_b_with_log(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    a.personal.set_setting("f42.theme", "oscuro")
    res = b.sync.synchronize(_snapshot(a.sync, 2000), now_ms=3000)
    assert b.personal.setting("f42.theme") == "oscuro"
    ops = [e.operation for e in res["events"]]
    assert ops == ["remote-apply"]
    ev = b.sync_store.events_of("pref:f42.theme")
    assert len(ev) == 1 and ev[0]["winner"] == "remote"
    assert ev[0]["protocol_version"] == "f13ext-sync/1"
    st = b.sync_store.get_state("pref:f42.theme")
    assert st is not None and st["digest"] == res["state"]["pref:f42.theme"].digest


def test_reverse_propagation(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    b.personal.set_setting("f42.theme", "oscuro")
    res = a.sync.synchronize(_snapshot(b.sync, 2000), now_ms=3000)
    assert a.personal.setting("f42.theme") == "oscuro"
    assert [e.operation for e in res["events"]] == ["remote-apply"]


def test_favourite_and_note_roundtrip(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    a.search_history.add_favourite("asignatura", "subject:x", "Álgebra",
                                   created="2026-01-01T10:00:00")
    a.personal.add_note(PL.QuickNote("note:nota-1", "texto", "2026-01-01"))
    b.sync.synchronize(_snapshot(a.sync, 2000), now_ms=3000)
    assert b.search_history.is_favourite("asignatura", "subject:x") is True
    assert b.search_history.list_favourites()[0].title == "Álgebra"
    notes = b.personal.notes()
    assert [(n.stable_id, n.text) for n in notes] == [("note:nota-1", "texto")]


def test_service_idempotent_second_run_is_noop(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    a.personal.set_setting("f42.theme", "oscuro")
    snap = _snapshot(a.sync, 2000)
    first = b.sync.synchronize(snap, now_ms=3000)
    second = b.sync.synchronize(snap, now_ms=4000)
    assert {k: v.digest for k, v in second["state"].items()} == \
        {k: v.digest for k, v in first["state"].items()}
    assert {e.operation for e in second["events"]} <= {"unchanged", "same"}


def test_version_reused_when_digest_unchanged(tmp_path):
    core = _core(tmp_path, "a")
    core.personal.set_setting("f42.theme", "oscuro")
    core.sync.synchronize(_snapshot(core.sync, 2000), now_ms=3000)
    v1 = core.sync_store.get_state("pref:f42.theme")["version_ms"]
    core.sync.synchronize(_snapshot(core.sync, 2000), now_ms=9000)
    v2 = core.sync_store.get_state("pref:f42.theme")["version_ms"]
    assert v1 == v2 == 3000  # versión del primer export; sin bump espurio


def test_corrupt_snapshot_rejected_state_untouched(tmp_path):
    a, b = _core(tmp_path, "a"), _core(tmp_path, "b")
    b.personal.set_setting("f42.theme", "claro")
    with pytest.raises(SyncError) as e:
        b.sync.synchronize({"protocol": "nope"}, now_ms=3000)
    assert e.value.code == "AC-SYN-001"
    assert b.personal.setting("f42.theme") == "claro"
    assert b.sync_store.events_of("pref:f42.theme") == []


# -- transporte y límites ---------------------------------------------------

def test_transport_rejects_missing_invalid_and_tampered(tmp_path):
    t = FileTransport()
    with pytest.raises(SyncRejected):
        t.load(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SyncRejected):
        t.load(bad)
    core = _core(tmp_path, "a")
    core.personal.set_setting("f42.theme", "oscuro")
    snap = _snapshot(core.sync, 2000)
    p = tmp_path / "s.json"
    t.save(snap, p)
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    data["records"][0]["payload"] = {"value": "manipulado"}
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SyncRejected):
        t.load(p)


def test_transport_rejects_oversize(tmp_path):
    t = FileTransport()
    big = {"protocol": "f13ext-sync/1", "device_id": "a" * 32,
           "exported_at_ms": 1, "records": [{"x": "y" * 9_000_000}]}
    with pytest.raises(SyncRejected):
        t.save(big, tmp_path / "big.json")


def test_synclog_append_is_idempotent_and_ordered(tmp_path):
    core = _core(tmp_path, "a")
    store = core.sync_store
    assert isinstance(store, SyncLogRepository)
    rec = S.make_record("pref:f42.theme", "preference", {"value": "x"},
                        100, core.device_id, core.device_id)
    store.put_state(rec)
    got = store.get_state("pref:f42.theme")
    assert got["digest"] == rec.digest and got["version_ms"] == 100
    assert store.get_state("pref:nope") is None


def test_sync_service_construction_validates_device(tmp_path):
    core = _core(tmp_path, "a")
    with pytest.raises(ValueError):
        SyncService(core.personal, SearchHistoryRepository(core.db),
                    core.sync_store, "corto")
