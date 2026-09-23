# ADR-0024 — Legacy data migration protocol (F4.1)

Date: 2026-09-23 · Status: Accepted

## Decision
`GestionMigrationService`: read-only source (`mode=ro`, integrity_check,
Alembic allow-list) -> deterministic plan -> dry-run (zero writes) or
apply = snapshot (SQLite online backup, mandatory) -> CAS blobs -> ONE SQL
transaction -> derived FTS -> post-validation -> `migration_runs`.
Every source row ends in `legacy_map` (migrated) or `legacy_payloads`
(preserved verbatim with reason / deferred phase). Idempotent re-runs;
cancel leaves the target unchanged; report digest excludes timestamps,
run ids and paths. The original database and files are never modified.

## Consequence
"Fuera de F4.1 ≠ eliminar": F10/F11/F12/F14/F4.2 data (sessions, SRS
concepts, dismissals, annotations, favourites) is kept for its phase.
