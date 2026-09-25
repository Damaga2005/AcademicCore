# SPDX-License-Identifier: MIT
"""F13-ext transport adapter: archivo local para 2 PCs (sin cloud).

El motor no conoce proveedores; este adaptador guarda/carga snapshots
JSON canónicos con validación estricta (esquema, tamaños, hashes).
Nada se ejecuta; toda entrada se valida antes de aplicarse.
"""

from __future__ import annotations

import json
from pathlib import Path

from academic_core.domain import sync as S
from academic_core.errors import AcademicCoreError

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


class SyncRejected(AcademicCoreError):
    code = "AC-SYN-001"
    category = "sync"


class FileTransport:
    """Snapshot <-> archivo. Desacoplado del motor."""

    def save(self, snapshot: dict, path) -> str:
        if not isinstance(snapshot, dict):
            raise SyncRejected("snapshot must be a dict")
        raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise SyncRejected("snapshot too large")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        return str(p)

    def load(self, path) -> dict:
        p = Path(path)
        try:
            raw = p.read_bytes()
        except OSError as e:
            raise SyncRejected(f"cannot read snapshot: {e}") from e
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise SyncRejected("snapshot too large")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise SyncRejected("snapshot is not valid JSON") from e
        try:
            S.import_snapshot(data)
        except ValueError as e:
            raise SyncRejected(str(e)) from e
        return data
