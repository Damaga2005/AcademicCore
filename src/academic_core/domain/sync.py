# SPDX-License-Identifier: MIT
"""F13-ext sync engine (domain, pure): LWW + log, sin CRDT.

Capa sobre la persistencia existente. Opera sobre ``SyncRecord`` planos;
los adaptadores convierten entidades reales a registros. Sin Qt, sin SQL,
sin red, sin reloj implícito (``now_ms`` siempre inyectado).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from academic_core.domain.entities import DomainError

PROTOCOL_VERSION = "f13ext-sync/1"

_DEVICE_RE = re.compile(r"^[0-9a-f]{32}$")
_RID_RE = re.compile(r"^[A-Za-z0-9_.:/#-]{1,256}$")
KINDS = ("preference", "saved_search", "quick_note")

MAX_PAYLOAD_BYTES = 256 * 1024


def _err(msg: str) -> DomainError:
    return DomainError(msg, code="AC-SYN-001")


def validate_device_id(device_id: str) -> str:
    if not isinstance(device_id, str) or not _DEVICE_RE.match(device_id):
        raise _err(f"bad device_id: {device_id!r}")
    return device_id


def validate_kind(kind: str) -> str:
    if kind not in KINDS:
        raise _err(f"bad kind: {kind!r}")
    return kind


def validate_resource_id(resource_id: str) -> str:
    if not isinstance(resource_id, str) or not _RID_RE.match(resource_id):
        raise _err(f"bad resource_id: {resource_id!r}")
    return resource_id


def _check_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise _err("payload must be a dict")
    try:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as e:
        raise _err(f"payload not JSON-canonical: {e}") from e
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise _err("payload too large")
    return payload


def canonical_digest(kind: str, resource_id: str, payload: dict, deleted: bool) -> str:
    """Digest sobre la representación canónica.

    Incluye ``kind + resource_id + payload ordenado + deleted``.
    Excluye versión/dispositivo/tiempos: el mismo cambio aplicado en dos
    PCs tiene el mismo digest (detección de ``same change``).
    """
    validate_kind(kind)
    validate_resource_id(resource_id)
    _check_payload(payload)
    form = {"deleted": bool(deleted), "kind": kind, "payload": payload,
            "resource_id": resource_id}
    raw = json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SyncRecord:
    resource_id: str
    kind: str
    payload: dict
    version_ms: int
    version_device: str
    origin_device: str
    updated_ms: int
    digest: str
    deleted: bool = False

    def version_tuple(self) -> tuple:
        return (int(self.version_ms), str(self.version_device))


@dataclass(frozen=True)
class SyncEvent:
    event_id: str
    device_id: str
    resource_id: str
    operation: str
    local_version: str
    remote_version: str
    winner: str
    conflict: bool
    result: str
    timestamp_ms: int
    digest_before: str
    digest_after: str
    protocol_version: str = PROTOCOL_VERSION


def make_record(resource_id: str, kind: str, payload: dict, version_ms: int,
                version_device: str, origin_device: str = "",
                deleted: bool = False) -> SyncRecord:
    validate_resource_id(resource_id)
    validate_kind(kind)
    validate_device_id(version_device)
    origin = origin_device or version_device
    validate_device_id(origin)
    if not isinstance(version_ms, int) or version_ms < 0:
        raise _err(f"bad version_ms: {version_ms!r}")
    _check_payload(payload)
    digest = canonical_digest(kind, resource_id, payload, deleted)
    return SyncRecord(resource_id, kind, dict(payload), version_ms, version_device,
                      origin, version_ms, digest, bool(deleted))


def delete_record(resource_id: str, kind: str, ms: int, device_id: str) -> SyncRecord:
    """Tombstone: payload vacío, ``deleted=True``, versión nueva."""
    return make_record(resource_id, kind, {}, ms, device_id, device_id, deleted=True)


def _vstr(rec) -> str:
    if rec is None:
        return "-"
    return f"{rec.version_ms}:{rec.version_device}"


def compare_version(a_ms: int, a_dev: str, b_ms: int, b_dev: str) -> int:
    """1 si A gana, -1 si B gana, 0 si empate total.

    Precisión ms; igualdad -> desempate lexicográfico por device_id
    (determinista). Relojes desincronizados: sigue siendo determinista
    (gana el mayor par), sin garantía causal (límite documentado).
    """
    if a_ms != b_ms:
        return 1 if a_ms > b_ms else -1
    if a_dev != b_dev:
        return 1 if a_dev > b_dev else -1
    return 0


def _event_id(protocol: str, rid: str, lv: str, rv: str, op: str,
              winner: str, digest_after: str) -> str:
    raw = "|".join((protocol, rid, lv, rv, op, winner, digest_after))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _check_state(state, name: str) -> dict:
    if not isinstance(state, dict):
        raise _err(f"{name} state must be a dict")
    for k, v in state.items():
        if not isinstance(v, SyncRecord):
            raise _err(f"corrupt record: {k!r}")
        if v.resource_id != k:
            raise _err(f"record key mismatch: {k!r}")
    return state


def sync(local: dict, remote: dict, device_id: str, now_ms: int) -> tuple:
    """Un paso de sincronización: ``sync(S, R) = (S', log)``.

    Idempotente: ``sync(S', R) == S'`` sin cambios nuevos.
    """
    validate_device_id(device_id)
    if not isinstance(now_ms, int) or now_ms < 0:
        raise _err(f"bad now_ms: {now_ms!r}")
    local = _check_state(local, "local")
    remote = _check_state(remote, "remote")

    out: dict[str, SyncRecord] = {}
    log: list[SyncEvent] = []
    for rid in sorted(set(local) | set(remote)):
        a = local.get(rid)
        b = remote.get(rid)
        lv, rv = _vstr(a), _vstr(b)
        before = a.digest if a is not None else ""
        if a is not None and b is None:
            out[rid] = a
            op, winner, conflict, result = "local-keep", "local", False, "kept-local"
            after = a.digest
        elif a is None and b is not None:
            out[rid] = b
            op, winner, conflict, result = "remote-apply", "remote", False, "applied-remote"
            after = b.digest
            before = ""
        elif a.digest == b.digest and a.version_tuple() == b.version_tuple():
            out[rid] = a
            op, winner, conflict, result = "unchanged", "none", False, "no-op"
            after = a.digest
        elif a.digest == b.digest:
            # Mismo cambio, versiones distintas -> converger a la mayor.
            best = a if compare_version(a.version_ms, a.version_device,
                                        b.version_ms, b.version_device) >= 0 else b
            out[rid] = best
            op, winner = "same", "local" if best is a else "remote"
            conflict, result, after = False, "merged-same", best.digest
        else:
            cmp = compare_version(a.version_ms, a.version_device,
                                  b.version_ms, b.version_device)
            if cmp >= 0:
                out[rid] = a
                op, winner, result = "local-wins", "local", "kept-local"
                after = a.digest
            else:
                out[rid] = b
                op, winner, result = "remote-wins", "remote", "applied-remote"
                after = b.digest
            conflict = True
        log.append(SyncEvent(
            event_id=_event_id(PROTOCOL_VERSION, rid, lv, rv, op, winner, after),
            device_id=device_id, resource_id=rid, operation=op,
            local_version=lv, remote_version=rv, winner=winner,
            conflict=conflict, result=result, timestamp_ms=now_ms,
            digest_before=before, digest_after=after,
            protocol_version=PROTOCOL_VERSION))
    return out, log


def export_snapshot(state: dict, device_id: str, now_ms: int) -> dict:
    validate_device_id(device_id)
    _check_state(state, "local")
    recs = []
    for rid in sorted(state):
        r = state[rid]
        recs.append({"deleted": r.deleted, "digest": r.digest, "kind": r.kind,
                     "origin_device": r.origin_device, "payload": r.payload,
                     "resource_id": r.resource_id, "updated_ms": r.updated_ms,
                     "version_device": r.version_device, "version_ms": r.version_ms})
    return {"device_id": device_id, "exported_at_ms": now_ms,
            "protocol": PROTOCOL_VERSION, "records": recs}


def import_snapshot(data: dict) -> tuple:
    """Valida un snapshot y devuelve ``(device_id, state)``.

    Rechaza snapshots corruptos sin tocar el estado válido.
    """
    if not isinstance(data, dict):
        raise _err("snapshot must be a dict")
    if data.get("protocol") != PROTOCOL_VERSION:
        raise _err(f"unknown snapshot protocol: {data.get('protocol')!r}")
    validate_device_id(data.get("device_id", ""))
    recs = data.get("records")
    if not isinstance(recs, list) or len(recs) > 10000:
        raise _err("bad snapshot records")
    state: dict[str, SyncRecord] = {}
    for e in recs:
        if not isinstance(e, dict):
            raise _err("bad snapshot entry")
        try:
            kind = validate_kind(e["kind"])
            rid = validate_resource_id(e["resource_id"])
            payload = e["payload"]
            vms = e["version_ms"]
            vdev = validate_device_id(e["version_device"])
            origin = validate_device_id(e.get("origin_device", vdev))
            ums = e.get("updated_ms", vms)
            deleted = bool(e.get("deleted", False))
        except KeyError as ex:
            raise _err(f"snapshot entry missing {ex}") from ex
        if not isinstance(vms, int) or not isinstance(ums, int) or vms < 0 or ums < 0:
            raise _err("bad snapshot version")
        _check_payload(payload)
        if canonical_digest(kind, rid, payload, deleted) != e.get("digest"):
            raise _err(f"snapshot digest mismatch: {rid!r}")
        if rid in state:
            raise _err(f"duplicate snapshot record: {rid!r}")
        state[rid] = SyncRecord(rid, kind, dict(payload), vms, vdev, origin,
                                ums, str(e["digest"]), deleted)
    return str(data["device_id"]), state
