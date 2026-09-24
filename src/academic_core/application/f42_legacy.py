# SPDX-License-Identifier: MIT
"""F4.2 legacy consumption: `legacy_payloads` deferred to F4.2 -> history.

Resolution (`resolve_legacy_reference`) is pure and side-effect free; storage
lives in `SearchHistoryService`. Legacy numeric ids are NEVER reused, cast,
slugified or matched numerically: only `legacy_map` (or the stable identity
F4.1 produced) resolves a reference. Unresolvable rows keep their payload
verbatim plus an evidence warning; Gestion is never written.
"""

from __future__ import annotations

from academic_core.domain.entities import DomainError
from academic_core.infrastructure.legacy_gestion import SOURCE_SYSTEM

# legacy kind -> legacy table whose `legacy_map` entry holds the stable ref.
_REFERENCE_TABLES = {
    "asignatura": "asignatura",
    "profesor": "profesor",
    "documento": "documento",
    "tarea": "tarea_evento",
    "examen": "tarea_evento",
    "evento": "tarea_evento",
    "hito": "hito",
    "concepto": "concepto",
    "nota_al_vuelo": "nota_rapida",
}
# Kinds with no resolvable entity: the payload is kept, never invented.
_UNRESOLVED_KINDS = ("pagina_pdf", "etiqueta")


def resolve_legacy_reference(kind: str, legacy_id, mapped: dict) -> tuple[str, str]:
    """Pure resolution: (kind, legacy id) -> ("RESOLVED", stable ref) or
    ("UNRESOLVED", reason). `mapped` is `legacy.all_mapped(SOURCE_SYSTEM)`."""
    if kind in _UNRESOLVED_KINDS:
        return "UNRESOLVED", f"kind {kind!r} has no stable entity"
    table = _REFERENCE_TABLES.get(kind)
    if table is None:
        return "UNRESOLVED", f"unknown kind {kind!r}"
    ref = mapped.get((table, str(legacy_id)))
    if not ref:
        return "UNRESOLVED", f"no legacy_map entry for {table}#{legacy_id}"
    return "RESOLVED", ref


def _label(kind: str, legacy_id, titles: dict, table: str, ref: str) -> str:
    get = titles.get(table)
    if get is not None:
        try:
            title = get(ref)
        except Exception:
            title = ""
        if title:
            return title
    return f"{kind} #{legacy_id}"


def consume_f42_payloads(legacy, history, titles: dict | None = None) -> dict:
    """Migrate `busqueda_favorito/reciente` payloads deferred to F4.2.

    Idempotent: favourites are no-ops when present, recents upsert;
    payloads are never deleted. A second run changes nothing.
    """
    titles = titles or {}
    mapped = legacy.all_mapped(SOURCE_SYSTEM)
    report: dict = {"migrated": 0, "unresolved": [], "warnings": []}
    for table in ("busqueda_favorito", "busqueda_reciente"):
        for row in legacy.payloads(SOURCE_SYSTEM, table):
            payload = row.get("payload") or {}
            kind = payload.get("tipo_entidad", "")
            legacy_id = payload.get("entidad_id", "")
            status, ref = resolve_legacy_reference(kind, legacy_id, mapped)
            if status != "RESOLVED":
                report["unresolved"].append(
                    {"table": table, "source_id": row.get("source_id"),
                     "reason": ref})
                report["warnings"].append(
                    f"{table}#{row.get('source_id')}: reference not resolvable"
                    f" ({ref}); payload preserved")
                continue
            try:
                if table == "busqueda_favorito":
                    added = history.add_favourite(
                        kind, ref,
                        _label(kind, legacy_id, titles,
                               _REFERENCE_TABLES[kind], ref),
                        created=str(payload.get("fecha_creacion") or ""))
                else:
                    added = history.record_recent(
                        kind, ref, str(payload.get("etiqueta_mostrada") or ""),
                        str(payload.get("url") or ""),
                        accessed=str(payload.get("fecha_acceso") or ""))
            except DomainError as e:
                report["unresolved"].append(
                    {"table": table, "source_id": row.get("source_id"),
                     "reason": f"invalid legacy values: {e}"})
                report["warnings"].append(
                    f"{table}#{row.get('source_id')}: invalid legacy values"
                    f" ({e}); payload preserved")
                continue
            report["migrated"] += 1 if added else 0
    return report
