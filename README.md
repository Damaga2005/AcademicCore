# Academic Core

**Academic Engineering Environment / Academic OS for Windows — Fase 0 foundation.**

Modular monolith · PySide6/Qt native · SQLite + CAS + FTS5/TF-IDF ·
Evidence-gated AI (Ollama runtime) · PDF via isolated Stirling adapter.

## Quickstart (Windows)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -m "not migration"      # fast loop
pytest                         # full incl. migration contract
python -m academic_core        # minimal native window (Qt)
python -m academic_core --config=config.json
```

Headless smoke: `$env:QT_QPA_PLATFORM="offscreen"; python -m academic_core`.

## Tree

```
src/academic_core/  app.py(Qt validación)  config/  domain/  storage/
                    engines/  infrastructure/  application/
tests/ (145: + results, queries, integrity, academic-io, ui-academic,
        academic-perf)
docs/{architecture,adr×16,migration(+GESTION-F4-*),domain,security,testing,
     roadmap,gates,phase-reports,F4_ACADEMIC_MANAGEMENT.md}
```

## Fase 4 (actual)
Academic Management: árbol navegable, CRUD + borrado seguro, gradebook
genérico (escalas/pesos/parciales) junto al motor F1, queries planning,
import/export JSON, UI workspace. Gate: `docs/gates/GATE-F4.md`.

## Fase 3 (actual)
Document Engine (AST canónico, parsers HTML/MD con reuse del Conversor,
renderers, provenance) + PDF Engine (native pypdf + Stirling opcional
v2.14.3). Gate: `docs/gates/GATE-F3.md`. Licencias: Conversor MIT misma
autoría; pypdf BSD; Stirling open-core externo (no vendored).

## Fase 2 (actual)
Resource Engine: CAS SHA-256 + adapters (file/md/html/pdf) + pipeline
idempotente + versiones + provenance + FTS5 derivado + tab Resources.
Gate: `docs/gates/GATE-F2.md`. Plan: `docs/phase-reports/F2-PLAN.md`.

## Fase 1 (actual)
Modelo canónico + IDs estables + SQLite sin ORM + grading Decimal equivalente
+ horarios/conflictos + servicios + UI validación. Gate: `docs/gates/GATE-F1.md`.

## Fase 0 answers (short)
1-4. Inventories + MATRIX.md (MIGRATE/REWRITE/ADAPT/REFERENCE/REJECT/INVESTIGATE).
5-6. `docs/architecture/` + 10 ADRs. 7. `domain/` dataclasses. 8. SQLite+CAS.
9. `PDFService` + disabled `StirlingAdapter`. 10. Ollama backend + `AIRouter`.
11. `ResourceProvider` (OneDrive opt-in). 12. Canonical `Circuit` + external
backends. 13-14. Provenance on every entity; `source_latex` immutable + 100%
retrieval gate. 15. Boundary test. 16. Single model, stable IDs. 17. Status
labels. 18. Lazy/streaming/index-incrementalexternals. 19. Installer Phase 13.
20. MATRIX + ROADMAP phase order.

Sources are READ-ONLY references; no commits made to them. Migration happens
selectively per MATRIX with origin/license/decision recorded.
