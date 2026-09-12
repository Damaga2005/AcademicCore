# Changelog

## 0.5.0 — Fase 4 Academic Management (2026-09-12)
- Gestion audit + reuse map (concept-only, no code copied).
- Generic gradebook (scales/weights/optional/partial, Decimal) beside F1
  engine (ADR-0016); results service; planning queries; JSON import/export;
  safe deletes + prerequisites; migration 008 (additive).
- Facade (`AcademicApp`) + `ui/` workspace (tree, 5 tabs, dialogs).
- Gate F4: 145 passed, 2 skipped (123 F0–F3 + 22 F4).

## 0.4.0 — Fase 3 Document + PDF Engine (2026-09-12)
- Conversor audit (20 comps) + selective reuse (math 1:1, tables, images,
  sanitize, metadata, encoding) with equivalence tests vs original module.
- Canonical AST (19 kinds, v1, validated, deterministic JSON) + HTML/MD
  parsers + MD/HTML renderers + doc derivations (007) + provenance chain.
- PDF engine (pypdf native: inspect/merge/split/rotate/extract/PDF→AST) +
  Stirling v2.14.3 research, runtime manager, API backend (mock-verified,
  live SIMULATED). ADR-0015. Gate F3: 123 passed, 2 skipped.

## 0.3.0 — Fase 2 Resource Engine (2026-09-12)
- Ports (`BlobStore/Extractor/Indexer/Records`) + `Resource/Version/Provenance`.
- CAS: streaming SHA-256, atomic, integrity-checked, traversal-safe.
- Adapters file/md/html/pdf (+ZIP refused); pipeline idempotente + versiones.
- FTS5 derivado con rebuild + filtros; tab Resources; `ingest.max_bytes`.
- ADR-0013/0014; gate F2: 81 passed (41 F0/F1 + 40 F2).

## 0.2.0 — Fase 1 Domain & Academic Foundation (2026-09-12)
- Domain: 20 entidades (University→Subject→Topic/Assignment/Exam/Project/Lab/
  Task/Deadline/Grade/Tag/Bookmark/Annotation/StudySpace/Session/Notification),
  Term genérico, invariantes con DomainError.
- Identity: 16 kinds, slugify NFKD, IdAllocator + counters persistidos.
- Grading Decimal HALF_UP + equivalencia (ADR-0011); schedule/conflictos puros.
- Persistence: sqlite3 stdlib, 4 migraciones, repos explícitos (ADR-0012).
- Application: Academic/Grading/Schedule services + Search/Backup/AppLock.
- UI Qt validación (selectores, subjects CRUD, 4 tabs) + gate F1: 41 passed.

## 0.1.0 — Fase 0 foundation (2026-09-12)
- Audits: Conversor (monolito 6.051 lín + lab 16 módulos), Gestion (Flask,
  28 tablas, 152 rutas, 672 docs), Sistemes (91 fuentes, 2896 fórmulas,
  1092 tests) — full detail in `docs/migration/`.
- Architecture: modular monolith, 10 ADRs, domain v0, stable IDs, storage
  SQLite+CAS, engines interfaces (resource/document/pdf/ai/providers/
  engineering), Qt skeleton executable, config system, 6 test files.
- Gates: fast suite + migration contract + reproducibility + boundary test.
