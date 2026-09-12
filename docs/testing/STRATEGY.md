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
- External: `@pytest.mark.external` needs live runtimes (Stirling/Java);
  `pytest -m "not external"` is the default gate; external never blocks it.
- Equivalence: `tests/conversor_ref.py` loads the read-only Conversor module
  (CONVERSOR_PATH or default checkout) and compares 1:1; skips when absent.
- Perf: `tests/test_perf.py` prints timings with generous bounds (no tuning).
