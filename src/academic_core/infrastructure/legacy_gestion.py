# SPDX-License-Identifier: MIT
"""Read-only adapter for a Gestion-Academica SQLite database (F4.1).

This is the ONLY place that knows Gestion's physical schema. It never
writes to the legacy database (opened with ``mode=ro``), never imports
Flask/SQLAlchemy, and returns plain rows. Also resolves legacy document
paths under an explicit root without ever escaping it.

Supported schema: the Alembic chain of Gestion-Academica@187a614
(``c73474549a28`` ... head ``e5a7c9b1d3f4``). Older revisions are read with
missing columns/tables reported, never guessed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from academic_core.errors import MigrationError, AcademicCoreError

SOURCE_SYSTEM = "gestion-academica"
ALEMBIC_CHAIN = (
    "c73474549a28", "4328d69e2e5e", "41e04bad8c03", "a3ed4ca22390", "fbc3c60c71ff",
    "4543c92b56f8", "f962d2bd0be5", "d7b267f6cfa5", "b1c2d3e4f5a6", "c2d3e4f5a6b7",
    "00cd0e536834", "6db5013308bc", "c842b67f9507", "e1f2a3b4c5d6", "5cd17294d4a8",
    "cf88a4da32ad", "ee15612bb3a3", "7572e1b913a6", "a1c3e5f7b9d2", "b2d4f6a8c0e1",
    "c3e5a7b9d1f2", "d4f6b8c0e2a3", "e5a7c9b1d3f4",
)
HEAD = ALEMBIC_CHAIN[-1]
# Every data table of the head schema, in dependency order.
TABLES = (
    "anio", "cuatrimestre", "asignatura", "asignatura_prerrequisito", "profesor",
    "esquema_evaluacion", "bloque_evaluacion", "componente_evaluacion", "recurso_externo",
    "apartado", "grupo_documento", "documento", "pagina_texto", "marcador", "anotacion_pdf",
    "tarea_evento", "espacio_estudio", "espacio_estudio_documento", "objetivo_espacio",
    "horario_clase", "hito", "nota_rapida", "concepto", "sesion_estudio", "dia_actividad",
    "configuracion_app", "aviso_descartado", "busqueda_favorito", "busqueda_reciente",
)
REQUIRED = ("anio", "cuatrimestre", "asignatura")
MAX_SOURCE_BYTES = 4 * 1024 ** 3


class UnsafePathError(AcademicCoreError):
    code = "AC-SEC-002"
    category = "security"


MAX_INDEX_FILES = 200_000


def build_filename_index(root: str | Path, max_files: int = MAX_INDEX_FILES
                         ) -> dict[str, list[str]]:
    """Map filename -> sorted list of relative POSIX paths under ``root``.

    Deterministic (sorted walk), read-only, never follows symlinks that
    escape the root. Bounded: raises UnsafePathError past ``max_files``.
    Used ONLY as an identity fallback when the historic ``ruta_local``
    no longer matches the user's physical layout (F4.1 closure §3)."""
    base = Path(os.path.realpath(root))
    if not base.is_dir():
        raise FileNotFoundError(str(root))
    index: dict[str, list[str]] = {}
    n = 0
    entries = sorted(base.rglob("*"))
    for p in entries:
        if not p.is_file() or p.is_symlink():
            continue
        n += 1
        if n > max_files:
            raise UnsafePathError("documents tree exceeds index budget")
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            continue
        index.setdefault(p.name, []).append(rel)
    for v in index.values():
        v.sort()
    return index


def resolve_document_by_identity(root: str | Path, filename: str, size: int | None,
                                 max_bytes: int,
                                 index: dict[str, list[str]] | None = None) -> Path:
    """Resolve a legacy document by identity (filename + size), not by path.

    Returns the unique candidate re-validated through :func:`resolve_document`
    (same traversal/symlink/size guards). Raises FileNotFoundError when there
    is no candidate or more than one (ambiguous: never guess)."""
    if not filename or "\x00" in filename or "/" in filename or "\\" in filename:
        raise UnsafePathError("identity filename refused")
    idx = build_filename_index(root) if index is None else index
    candidates = idx.get(filename, [])
    if size is not None:
        sized = []
        for rel in candidates:
            try:
                target = resolve_document(root, rel, max_bytes)
            except (UnsafePathError, FileNotFoundError):
                continue
            if target.stat().st_size == size:
                sized.append(rel)
        candidates = sized
    if len(candidates) != 1:
        raise FileNotFoundError(f"{filename}: {len(candidates)} identity candidates")
    return resolve_document(root, candidates[0], max_bytes)


@dataclass
class LegacySnapshot:
    revision: str
    tables: dict[str, list[dict]]
    missing_tables: tuple[str, ...] = ()
    orphans: list[str] = field(default_factory=list)

    def count(self, table: str) -> int:
        return len(self.tables.get(table, ()))

    def digest(self) -> str:
        payload = json.dumps({"revision": self.revision, "tables": self.tables},
                             sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                             default=_json_default)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_default(v):
    if isinstance(v, (bytes, bytearray)):
        return {"hex": bytes(v).hex()}
    raise TypeError(type(v).__name__)


def _pk_order(cx: sqlite3.Connection, table: str) -> str:
    cols = cx.execute(f'PRAGMA table_info("{table}")').fetchall()
    pks = [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]]
    return ", ".join(f'"{c}"' for c in pks) if pks else "rowid"


class LegacyGestionSource:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        p = self.path
        if not p.is_file():
            raise MigrationError(f"legacy database not found: {p.name}", code="AC-MIG-002")
        size = p.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise MigrationError("legacy database too large", code="AC-MIG-002")
        with p.open("rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                raise MigrationError("not a SQLite database", code="AC-MIG-002")
        # Read-only URI: the legacy file is never modified (no WAL checkpoint,
        # no journal); query_only as a second belt.
        cx = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA query_only=ON")
        return cx

    def open_and_validate(self) -> tuple[str, list[str]]:
        """Return (alembic revision, warnings) or raise AC-MIG-002/003."""
        cx = self._connect()
        try:
            try:
                check = cx.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError as e:
                raise MigrationError(f"legacy database unreadable: {e}", code="AC-MIG-002") from e
            if check != "ok":
                raise MigrationError("legacy database failed integrity_check", code="AC-MIG-002")
            names = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "alembic_version" not in names:
                raise MigrationError("no alembic_version: not a Gestion database",
                                     code="AC-MIG-003")
            rev = cx.execute("SELECT version_num FROM alembic_version").fetchone()
            rev = rev[0] if rev else ""
            if rev not in ALEMBIC_CHAIN:
                raise MigrationError(f"unsupported Gestion schema revision {rev!r}",
                                     code="AC-MIG-003")
            missing = [t for t in REQUIRED if t not in names]
            if missing:
                raise MigrationError(f"required tables missing: {missing}", code="AC-MIG-003")
            warnings = [f"table {t} absent (older revision {rev}): read as empty"
                        for t in TABLES if t not in names]
            fk = cx.execute("PRAGMA foreign_key_check").fetchall()
            warnings += [f"source foreign-key violation: {r[0]} rowid {r[1]} -> {r[2]}"
                         for r in fk]
            return rev, warnings
        finally:
            cx.close()

    def read(self) -> LegacySnapshot:
        rev, _ = self.open_and_validate()
        cx = self._connect()
        try:
            names = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            tables: dict[str, list[dict]] = {}
            for t in TABLES:
                if t not in names:
                    tables[t] = []
                    continue
                rows = cx.execute(f'SELECT * FROM "{t}" ORDER BY {_pk_order(cx, t)}').fetchall()
                tables[t] = [dict(r) for r in rows]
            return LegacySnapshot(rev, tables, tuple(t for t in TABLES if t not in names))
        finally:
            cx.close()


# --------------------------------------------------------------- documents

def resolve_document(root: str | Path, relative: str, max_bytes: int) -> Path:
    """Resolve ``relative`` (Gestion ``ruta_local``) strictly inside ``root``.

    Refuses absolute paths, NUL bytes, drive letters, ``..`` segments and
    anything whose real path (symlinks resolved) leaves the root. Returns
    the path of an existing regular file within ``max_bytes``; raises
    UnsafePathError (AC-SEC-002) or FileNotFoundError."""
    if not relative or "\x00" in relative:
        raise UnsafePathError("empty or NUL path refused")
    rel = relative.replace("\\", "/")
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise UnsafePathError("absolute path refused")
    if any(part == ".." for part in rel.split("/")):
        raise UnsafePathError("parent traversal refused")
    base = Path(os.path.realpath(root))
    target = Path(os.path.realpath(base / rel))
    if target != base and base not in target.parents:
        raise UnsafePathError("path escapes the documents root")
    if not target.is_file():
        raise FileNotFoundError(rel)
    if target.stat().st_size > max_bytes:
        raise UnsafePathError("document exceeds size limit")
    return target
