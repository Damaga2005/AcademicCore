# SPDX-License-Identifier: MIT
"""F13 cloud transports: desacoplados del motor F13-ext.

- ``CloudTransport``: protocolo minimo (read/write) que el dominio nunca ve.
- ``MemoryCloudTransport``: fake/in-memory para probar el contrato sin red.
- ``OneDriveFolderTransport``: carpeta local de OneDrive (sync por fichero,
  sin Graph/HTTP/tokens). La integracion Graph real con credenciales queda
  fuera del gate determinista (ver F13-CLOUD-SYNC.md Limitaciones).

Sin ``os/socket/urllib/http/requests/pickle/subprocess``: solo pathlib+json.
Validacion y limites reutilizados de F13-ext (sin duplicar el motor).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from academic_core.domain import sync as S
from academic_core.errors import AcademicCoreError
from academic_core.infrastructure.sync_transport import (
    MAX_SNAPSHOT_BYTES,
    SyncRejected,
)


class CloudError(AcademicCoreError):
    code = "AC-SYN-002"
    category = "sync"


class CloudOffline(CloudError):
    code = "AC-SYN-002"
    category = "sync"


class CloudAuthError(CloudError):
    code = "AC-SYN-003"
    category = "sync"


class CloudConflict(CloudError):
    code = "AC-SYN-004"
    category = "sync"


def _check_size(snapshot: dict) -> bytes:
    try:
        raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise SyncRejected(f"snapshot not JSON-canonical: {e}") from e
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise SyncRejected("snapshot too large")
    return raw


def _validate(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        raise SyncRejected("snapshot must be a dict")
    _check_size(snapshot)
    try:
        S.import_snapshot(snapshot)
    except ValueError as e:
        raise SyncRejected(str(e)) from e
    return snapshot


def _clone(snapshot: dict) -> dict:
    return json.loads(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")))


class CloudTransport:
    """Protocolo minimo cloud: read/write de snapshots validados."""

    def read(self) -> dict | None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def write(self, snapshot: dict, expected_remote_digest: str | None = None) -> dict:
        raise NotImplementedError


class MemoryCloudTransport(CloudTransport):
    """Fake in-memory para tests. Separa claramente el contrato de la
    integracion real (nunca fingir E2E contra OneDrive)."""

    def __init__(self, *, offline: bool = False, auth_fail: bool = False):
        self.offline = bool(offline)
        self.auth_fail = bool(auth_fail)
        self._raw: dict | None = None

    def read(self) -> dict | None:
        if self.offline:
            raise CloudOffline("cloud unavailable (offline)")
        if self.auth_fail:
            raise CloudAuthError("cloud auth refused")
        if self._raw is None:
            return None
        try:
            data = _clone(self._raw)
        except (TypeError, ValueError) as e:
            raise SyncRejected(f"cloud snapshot corrupt: {e}") from e
        return _validate(data)

    def write(self, snapshot: dict, expected_remote_digest: str | None = None) -> dict:
        if self.offline:
            raise CloudOffline("cloud unavailable (offline)")
        if self.auth_fail:
            raise CloudAuthError("cloud auth refused")
        _validate(snapshot)
        if expected_remote_digest is not None and self._raw is not None:
            cur = hashlib.sha256(json.dumps(
                self._raw, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            if cur != expected_remote_digest:
                raise CloudConflict("remote changed since read")
        self._raw = _clone(snapshot)
        return {"stored": True, "records": len(snapshot.get("records", []))}


class OneDriveFolderTransport(CloudTransport):
    """Carpeta local de OneDrive (fichero ``academic-sync.json``).

    Sin tokens ni red: la sincronizacion con la nube la hace el cliente de
    OneDrive del SO. Escritura atomica (tmp + replace) para no dejar
    snapshots a medias ante caidas.
    """

    FILENAME = "academic-sync.json"

    def __init__(self, folder) -> None:
        p = Path(folder)
        if not str(p) or str(p).strip() == "":
            raise SyncRejected("onedrive folder is empty")
        self.folder = p

    def _path(self) -> Path:
        return self.folder / self.FILENAME

    def read(self) -> dict | None:
        p = self._path()
        try:
            raw = p.read_bytes()
        except OSError as e:
            # Ausencia = primer push, no error. Solo ENOENT-like.
            if not p.exists():
                return None
            raise CloudOffline(f"cannot read cloud snapshot: {e}") from e
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise SyncRejected("snapshot too large")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise SyncRejected("cloud snapshot is not valid JSON") from e
        return _validate(data)

    def write(self, snapshot: dict, expected_remote_digest: str | None = None) -> dict:
        _validate(snapshot)
        if expected_remote_digest is not None:
            cur = self.read()
            if cur is not None:
                cur_digest = hashlib.sha256(json.dumps(
                    cur, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
                if cur_digest != expected_remote_digest:
                    raise CloudConflict("remote changed since read")
        raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (self.FILENAME + ".tmp")
        try:
            tmp.write_bytes(raw)
            tmp.replace(self._path())
        except OSError as e:
            raise CloudOffline(f"cannot write cloud snapshot: {e}") from e
        return {"stored": True, "records": len(snapshot.get("records", []))}
