# SPDX-License-Identifier: MIT
"""F13-ext application service: identidad, adaptadores y orquestación.

- Identidad estable por instalación (UUID hex, nunca hostname/MAC/IP).
- Adaptadores: preferences (f42.*), saved_searches, quick_notes.
- SyncService: export -> sync(domain) -> apply -> verify -> log.
Sin Qt. Sin subprocess. Sin red.
"""

from __future__ import annotations

import secrets
import time

from academic_core.domain import planning as PL
from academic_core.domain import sync as S
from academic_core.errors import AcademicCoreError

DEVICE_KEY = "sync.device_id"
SYNCABLE_PREFS = ("f42.theme", "f42.exam_reminder_days",
                  "f42.abandoned_subject_days", "f42.widgets_order",
                  "f42.widgets_hidden", "f42.target_average")


class SyncError(AcademicCoreError):
    code = "AC-SYN-001"
    category = "sync"


def generate_device_id() -> str:
    return secrets.token_hex(16)


def ensure_device_id(personal) -> str:
    """Lee ``sync.device_id`` o lo genera y persiste (estable por instalación)."""
    raw = personal.setting(DEVICE_KEY)
    if raw:
        try:
            return S.validate_device_id(raw.strip())
        except ValueError:
            pass
    nid = generate_device_id()
    personal.set_setting(DEVICE_KEY, nid)
    return nid


def _pref_payload(value) -> dict:
    from decimal import Decimal
    if isinstance(value, Decimal):
        return {"value": str(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {"value": value}
    if isinstance(value, list):
        return {"value": [str(v) for v in value]}
    return {"value": str(value)}  # pragma: no cover


def _pref_value(payload: dict):
    return payload.get("value")


class SyncService:
    """Orquesta la sincronización sobre repositorios reales."""

    def __init__(self, personal, history, sync_store, device_id: str):
        self.personal = personal
        self.history = history
        self.store = sync_store
        self.device_id = S.validate_device_id(device_id)

    # -- export ---------------------------------------------------------
    def export_local(self, now_ms: int) -> dict:
        state: dict[str, S.SyncRecord] = {}
        # preferences
        try:
            settings = self.personal.settings()
        except AttributeError:  # pragma: no cover - dict-like fake in tests
            settings = dict(self.personal)
        for key in SYNCABLE_PREFS:
            if key not in settings:
                continue
            rid = f"pref:{key}"
            payload = _pref_payload(settings[key])
            state[rid] = self._versioned(rid, "preference", payload, now_ms)
        # favourites
        for fav in self.history.favourites():
            rid = f"saved:{fav.kind}:{fav.ref}"
            payload = {"created": fav.created, "title": fav.title}
            state[rid] = self._versioned(rid, "saved_search", payload, now_ms)
        # quick notes
        notes = self.personal.notes() if hasattr(self.personal, "notes") else []
        for n in notes:
            payload = {"created": n.created, "text": n.text}
            state[n.stable_id] = self._versioned(n.stable_id, "quick_note", payload, now_ms)
        return state

    def _versioned(self, rid: str, kind: str, payload: dict, now_ms: int) -> S.SyncRecord:
        digest = S.canonical_digest(kind, rid, payload, False)
        prev = self.store.get_state(rid) if self.store is not None else None
        if prev is not None and prev.get("digest") == digest:
            return S.SyncRecord(rid, kind, dict(payload), int(prev["version_ms"]),
                                str(prev["version_device"]), self.device_id,
                                int(prev.get("updated_ms", prev["version_ms"])),
                                digest, False)
        return S.make_record(rid, kind, payload, int(now_ms), self.device_id,
                             self.device_id)

    # -- apply ----------------------------------------------------------
    def synchronize(self, remote_snapshot: dict, now_ms: int | None = None) -> dict:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        try:
            _, remote = S.import_snapshot(remote_snapshot)
        except ValueError as e:
            raise SyncError(str(e)) from e
        local = self.export_local(now)
        out, events = S.sync(local, remote, self.device_id, now_ms=now)
        self._apply_winners(out, events)
        # verify: re-export must converge (idempotence)
        verify, _ = S.sync(out, remote, self.device_id, now_ms=now)
        assert all(verify[k].digest == out[k].digest for k in out), "verify failed"
        for e in events:
            kind = out[e.resource_id].kind if e.resource_id in out else ""
            self.store.append(e, kind)
            if e.resource_id in out:
                self.store.put_state(out[e.resource_id])
        return {"state": out, "events": events,
                "snapshot": S.export_snapshot(out, self.device_id, now)}

    def _apply_winners(self, out: dict, events: list) -> None:
        by_id = {e.resource_id: e for e in events}
        for rid, rec in out.items():
            e = by_id[rid]
            if e.operation in ("local-keep", "local-wins", "unchanged", "same"):
                continue  # nada que escribir: el local ya manda o converge
            # remote manda -> escribir en tablas reales
            if rec.kind == "preference":
                key = rid.split("pref:", 1)[1]
                if rec.deleted:
                    self._delete_setting(key)
                else:
                    self.personal.set_setting(key, self._serialize_pref(key, rec.payload))
            elif rec.kind == "saved_search":
                if rec.deleted:
                    _, kind, ref = rid.split(":", 2)
                    self.history.remove_favourite(kind, ref)
                else:
                    # D5 fix: history es el REPOSITORIO (add_favourite toma
                    # SavedSearch, no (kind, ref, title) del servicio).
                    # El TypeError anterior rompía toda aplicación remota
                    # de favoritos. Se preserva `created` remoto.
                    _, kind, ref = rid.split(":", 2)
                    self.history.add_favourite(PL.SavedSearch(
                        kind, ref, str(rec.payload.get("title", "")),
                        str(rec.payload.get("created", ""))))
            elif rec.kind == "quick_note":
                if rec.deleted:
                    if hasattr(self.personal, "delete_note"):
                        self.personal.delete_note(rid)
                else:
                    self.personal.add_note(PL.QuickNote(rid, str(rec.payload.get("text", "")),
                                                       str(rec.payload.get("created", ""))))

    def _delete_setting(self, key: str) -> None:
        try:
            from academic_core.infrastructure.database import Database  # noqa: F401
        except ImportError:  # pragma: no cover
            pass
        if hasattr(self.personal, "db"):
            cx = self.personal.db.connect()
            cx.execute("DELETE FROM app_settings WHERE key=?", (key,))
            cx.commit()
            cx.close()

    @staticmethod
    def _serialize_pref(key: str, payload: dict) -> str:
        import json
        v = _pref_value(payload)
        if isinstance(v, list):
            return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        return "" if v is None else str(v)
