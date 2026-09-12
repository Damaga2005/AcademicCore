# ID Policy (Phase 1 — stable identity)

## Grammar
Root: `university:<slug>` `degree:<slug>` `year:<label>` `term:<slug>`
`professor:<slug>` `tag:<slug>` — slug = `[a-z0-9]+(-[a-z0-9]+)*`.
Scoped: `subject:<s>` `topic:<s>:tNN` `concept:<s>:c:NNNNN`
`formula:<s>:f:NNNNNN` `resource:<s>:r:NNNNN` `lab:<s>:lab:NNNNN`
`assignment:<s>:a:NNNNN` `project:<s>:p:NNNNN` `exam:<s>:e:NNNNN`
`task:<s>:task:NNNNN`. Implemented in `domain/identity.py` (`validate`,
`make`, `slugify`, `IdAllocator`).

## Rules
1. Assigned ONCE at creation/INGEST; stored as SQLite PRIMARY KEY.
2. NEVER derived from SQL rowids, autoincrements, filesystem paths, or URLs.
3. Reindex / conversion / migration / sync preserve IDs byte-for-byte
   (tested: `test_ids.py`, persistence round-trip `test_persistence.py`).
4. Deterministic when a natural key exists (subject/professor/term slugs via
   `slugify`, NFKD accent-stripped); otherwise sequential from persisted
   per-kind counters (`id_counters` table, `IdAllocator`).
5. Content hash (sha256/CAS) is SEPARATE: hash verifies bytes, ID verifies
   lineage. Two ingests of identical bytes share a hash but keep distinct IDs.
6. Recurring schedule series are value objects (identified by subject +
   weekday + time + range), not ID entities — no stable-id kind by design.

## Persistence of counters
`AcademicRepository.load_counters/save_counters`; services allocate then
persist, so IDs never repeat across restarts (covered by round-trip test).
