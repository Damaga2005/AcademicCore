# Testing strategy

- `tests/test_*.py` unit (identity, config) — fast, no Qt.
- Integration (storage CAS/SQLite) — tmp dirs, real files.
- Architecture (`test_architecture.py`) — import boundaries, fails build on violation.
- Migration (`test_migration.py`, marker `migration`) — formula coverage contract;
  full 2896-gate runs in Phase 12.
- Reproducibility (`test_reproducibility.py`, marker `repro`) — netlists, hashes.
- Future: `pytest-qt` UI smoke (offscreen), engine benchmark suites with fixed
  seeds, gold files + sha256 manifests.
- Run: `pytest -m "not migration"` for fast loop; full suite in CI + Windows job.
