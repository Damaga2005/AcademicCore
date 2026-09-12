# GATE F1 — Domain & Academic Foundation: ✅ PASS (2026-09-12)

Full suite: **41 passed** (14 Phase 0 regression + 27 Phase 1), offscreen UI
included. Commit: Fase 1 (this push). Sources untouched (read-only audit).

| Gate | Evidencia | Resultado |
|---|---|---|
| Domain invariantes 100% | `test_domain.py` 4/4 (jerarquía, Term genérico, invariantes, subset examen) | ✅ |
| Identity estable/persistente | `test_ids.py` 5/5 + counters en round-trip (`test_persistence.py`) | ✅ |
| Persistence cerrar→abrir→recuperar | `test_persistence.py` 2/2 idéntico + migraciones 1-4 reejecutables | ✅ |
| Grading equivalencia | `test_grading.py` 4/4 (6 casos vs semántica original + exactos + bloques/winner + veredictos) | ✅ |
| Schedule normal + edge | `test_schedule.py` 5/5 (semanal, ancla quincenal, paridad O(1), coherencia, solape) | ✅ |
| Migration sin UI-only | MIGRATION-REPORT-F1: toda fila ✅/🟡 con entidad+servicio+repo+test | ✅ |
| Architecture | `test_architecture.py` 4/4: domain sin Qt/SQLAlchemy/app; app/infra sin Qt; 0 sqlalchemy en src | ✅ |
| UI arranca (Windows/offscreen) | `test_ui.py` qtbot offscreen: título, 4 tabs, demo hierarchy | ✅ |
| Regression | 14/14 tests Fase 0 verdes en la misma run | ✅ |

Divergencias conocidas y documentadas (no bloquean): ADR-0011 (Decimal),
CONFLICTS §B (peso de bloque), §C (1..7), §F (diferidos a F2/F4/F11).
Riesgos abiertos: `%` de bloque en UI F4; FTS5 en F2; límites backup en F4+;
modelos IA/simulación fuera de alcance según §27 (solo boundaries).

**Fase 1 cerrada. Fase 2 (Resource Engine) requiere autorización explícita.**
