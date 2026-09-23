# SPDX-License-Identifier: MIT
"""F3 → E0.4 observability bridge (F3.1 §39): real facts only, no parallel infra.

Uses the certified `TraceRecorder`/`ExecutionTrace`. Emits only events that
really happened; content is bounded (counts, never full blobs). Callers stop
adding detail past `max_detail` and record an explicit `TRACE_TRUNCATED`
warning instead of silently dropping.
"""

from __future__ import annotations

from academic_core.domain.execution.model import EventKind, TraceRecorder, TraceValue

OPERATION = "document.import"


def record_import(*, source: str = "", parser: str = "", blocks: int = 0,
                  formulas: int = 0, problems: int = 0, assets: int = 0,
                  warnings: tuple | list = (), rendered: str = "",
                  max_detail: int = 64) -> object:
    """Build an `ExecutionTrace` for a document import (all counts are real)."""
    rec = TraceRecorder(OPERATION)
    rec.input("source", TraceValue.of_text(source or "unknown"), "Documento cargado")
    rec.metadata("parser", (parser or "unknown")[:64])
    n = 0

    def add(kind, title, **kw):
        nonlocal n
        if n >= max_detail:
            return None
        n += 1
        return rec.event(kind, title, **kw)

    if blocks:
        add(EventKind.STEP, f"Nodos analizados: {blocks}")
    if formulas:
        add(EventKind.STEP, f"Fórmulas detectadas: {formulas}")
    if problems:
        add(EventKind.STEP, f"Problemas detectados: {problems}")
    if assets:
        add(EventKind.STEP, f"Assets extraídos: {assets}")
    truncated = (blocks + formulas + problems + assets) > max_detail
    for w in list(warnings)[:16]:
        add(EventKind.WARNING, f"Aviso: {str(w)[:200]}")
    if truncated:
        rec.event(EventKind.WARNING, "TRACE_TRUNCATED: detalle acotado por budget")
    if rendered:
        rec.event(EventKind.RESULT, f"Renderizado: {rendered}",
                  result=TraceValue.of_text(rendered[:64]))
    else:
        rec.event(EventKind.RESULT, "Importación registrada",
                  result=TraceValue.of_text(
                      f"blocks={blocks} formulas={formulas} "
                      f"problems={problems} assets={assets}"))
    return rec.finish()
