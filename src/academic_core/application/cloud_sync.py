# SPDX-License-Identifier: MIT
"""F13 cloud coordination: offline-first sobre el motor F13-ext.

``CloudSyncService`` reutiliza ``SyncService.synchronize`` (EXPORT ->
CANONICAL -> COMPARE -> CLASSIFY -> LWW -> APPLY -> VERIFY -> SYNC LOG)
y anade coordinacion cloud/offline:

- lee el snapshot remoto via ``CloudTransport`` (None = primer push);
- nunca aplica datos remotos sin validar (el transporte ya valido con
  ``import_snapshot``; ``synchronize`` vuelve a validar);
- un fallo cloud jamas destruye el estado local valido;
- nada se marca como sincronizado sin confirmacion de escritura;
- estados por recurso: synced/pending/offline/conflict/error (tabla
  ``sync_status``, aditiva; nunca contamina digests).

Sin OneDrive/Graph/HTTP/tokens en el dominio ni aqui: solo el adapter de
infraestructura conoce la carpeta cloud.
"""

from __future__ import annotations

import time

from academic_core.domain import sync as S
from academic_core.infrastructure.cloud_transport import (
    CloudAuthError,
    CloudError,
    CloudOffline,
)
from academic_core.infrastructure.sync_transport import SyncRejected

SYNC_STATUSES = ("synced", "pending", "offline", "conflict", "error")


class CloudSyncService:
    """Coordina SyncService (F13-ext) + transporte cloud."""

    def __init__(self, sync_service, store, transport, device_id: str):
        self.sync_service = sync_service
        self.store = store
        self.transport = transport
        self.device_id = S.validate_device_id(device_id)

    # -- API ----------------------------------------------------------
    def sync_now(self, now_ms: int | None = None) -> dict:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        local = self.sync_service.export_local(now)
        try:
            remote_snapshot = self.transport.read()
        except CloudOffline:
            self._mark_all(local, "offline", now, "cloud unavailable")
            return {"outcome": "offline", "events": [], "state": local,
                    "status": "offline"}
        except (CloudAuthError, CloudError, SyncRejected, ValueError) as e:
            self._mark_all(local, "error", now, _safe_detail(e))
            return {"outcome": "error", "events": [], "state": local,
                    "status": "error"}
        if remote_snapshot is None:
            return self._first_push(local, now)
        return self._join(local, remote_snapshot, now)

    def status_of(self, resource_id: str) -> dict | None:
        return self.store.get_status(resource_id)

    def all_statuses(self) -> list[dict]:
        return self.store.all_statuses()

    def pending(self) -> list[dict]:
        return [s for s in self.all_statuses() if s["status"] in ("pending", "offline")]

    # -- internos -----------------------------------------------------
    def _first_push(self, local: dict, now: int) -> dict:
        snapshot = S.export_snapshot(local, self.device_id, now)
        try:
            self.transport.write(snapshot)
        except CloudOffline:
            self._mark_all(local, "offline", now, "cloud unavailable")
            return {"outcome": "offline", "events": [], "state": local,
                    "status": "offline"}
        except (CloudAuthError, CloudError, SyncRejected, ValueError) as e:
            self._mark_all(local, "error", now, _safe_detail(e))
            return {"outcome": "error", "events": [], "state": local,
                    "status": "error"}
        for rec in local.values():
            self.store.put_state(rec)
            self.store.set_status(rec.resource_id, "synced", now, "first-push")
        if not local:
            self.store.set_meta("last_sync_ms", str(now))
        else:
            self.store.set_meta("last_sync_ms", str(now))
        return {"outcome": "synced", "events": [], "state": local, "status": "synced"}

    def _join(self, local: dict, remote_snapshot: dict, now: int) -> dict:
        try:
            result = self.sync_service.synchronize(remote_snapshot, now_ms=now)
        except (SyncRejected, CloudError, ValueError) as e:
            # Snapshot remoto invalido: estado local intacto (synchronize no
            # aplica antes de validar). No se marca nada como sincronizado.
            self._mark_all(local, "error", now, _safe_detail(e))
            return {"outcome": "error", "events": [], "state": local,
                    "status": "error"}
        except CloudOffline:
            self._mark_all(local, "offline", now, "cloud unavailable")
            return {"outcome": "offline", "events": [], "state": local,
                    "status": "offline"}
        state = result["state"]
        events = result["events"]
        merged_snapshot = result["snapshot"]
        conflict = any(getattr(e, "conflict", False) for e in events)
        try:
            if merged_snapshot != remote_snapshot:
                self.transport.write(merged_snapshot)
        except CloudOffline:
            self._mark_from_events(state, events, "pending", now, "push deferred")
            return {"outcome": "pending", "events": events, "state": state,
                    "status": "pending"}
        except (CloudAuthError, CloudError, SyncRejected, ValueError) as e:
            # Aplicado en local, push fallido: no rollback destructivo.
            self._mark_from_events(state, events, "error", now, _safe_detail(e))
            return {"outcome": "error", "events": events, "state": state,
                    "status": "error"}
        status = "conflict" if conflict else "synced"
        self._mark_from_events(state, events, status, now,
                               "lww-resolved" if conflict else "converged")
        self.store.set_meta("last_sync_ms", str(now))
        return {"outcome": status, "events": events, "state": state, "status": status}

    def _mark_all(self, local: dict, status: str, now: int, detail: str) -> None:
        for rid in sorted(local):
            self.store.set_status(rid, status, now, detail)

    def _mark_from_events(self, state: dict, events: list, status: str,
                          now: int, detail: str) -> None:
        by_id = {e.resource_id: e for e in events}
        for rid in sorted(state):
            e = by_id.get(rid)
            if e is not None and getattr(e, "conflict", False) and status == "synced":
                self.store.set_status(rid, "conflict", now, "lww-resolved")
            else:
                self.store.set_status(rid, status, now, detail)
        # Recursos que solo existian en remoto y perdieron (no deberia pasar
        # con LWW, pero se cubre por completitud): ya estan en state.


def _safe_detail(exc: BaseException) -> str:
    code = str(getattr(exc, "code", "") or getattr(type(exc), "code", "") or "")
    if code:
        return code
    msg = str(exc)[:80]
    # Nunca filtrar secretos: solo codigos y mensajes cortos ya validados.
    for bad in ("token", "secret", "password", "bearer", "api_key"):
        if bad in msg.lower():
            return "rejected"
    return msg or "rejected"
