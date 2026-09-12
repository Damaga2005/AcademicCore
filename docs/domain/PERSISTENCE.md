# Persistence model (Phase 1)

- Engine: stdlib `sqlite3` only (ADR-0012). No ORM anywhere in the repo.
- `Database` applies forward-only migrations `001_academic → 002_grading →
  `003_planning → 004_study`, tracked in `schema_version`; re-open is a no-op.
- Stable IDs are TEXT PRIMARY KEYs; Decimal money-like values (weights,
  scores, finals) travel as TEXT to stay exact; dates as ISO strings.
- Large blobs NEVER in SQLite (gated by Phase 0 CAS test); JSON lists
  (resources/files/milestones/links/refs) stored as TEXT arrays.
- Repositories map rows ↔ domain dataclasses explicitly; domain never sees
  a row object. `test_persistence.py` proves create → close → reopen →
  identical recovery, including id counters.
