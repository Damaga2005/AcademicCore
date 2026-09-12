# ADR-0010 — Stable IDs + formula fidelity

Date: 2026-09-12 · Status: Accepted

## Decision
- ID grammar (see `domain/identity.py`): `subject:<slug>`,
  `topic:<slug>:tNN`, `concept:<slug>:c:NNNNN`, `formula:<slug>:f:NNNNNN`,
  `resource:<slug>:r:NNNNN`, `lab:<slug>:lab:NNNNN`, `assignment:<slug>:a:NNNNN`.
- IDs assigned once at INGEST/creation, stored in SQLite, preserved across
  conversion/reindex/migration/sync. Content hash (sha256) is separate.
- Formulas are first-class: `{id, latex, source_latex, variables, units, topic,
  concepts, provenance, version}`. **Never rewrite `source_latex`**; derived
  normalizations version explicitly. Migration gate: 100% formula retrieval
  coverage (2896/2896 benchmark shape from Sistemes-de-Mesura) must hold.

## Rationale
Sistemes audit: 2896 formulas at 100% retrieval BUT units 0% / variables 7% —
so "100%" must be defined as retrieval-with-provenance, with curation tracked
separately. Without stable IDs the Phase 12 migration cannot be verified.

## Consequences
- `tests/test_migration.py` pins the contract; Phase 12 runs the full gate.
- Curation backlog (units/variables/conditions) is explicit roadmap work.
