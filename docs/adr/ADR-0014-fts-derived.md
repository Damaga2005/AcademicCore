# ADR-0014 — FTS5 as a derived, rebuildable index (never canonical)

Date: 2026-09-12 · Status: Accepted

## Context
Text search is needed in F2, but the brief forbids the index becoming the
source of truth (ids/hashes/provenance must survive drop+rebuild).

## Decision
Plain FTS5 content table `resources_fts(stable_id, kind, title, body)`,
populated ONLY from canonical records+blobs via `IngestionService.reindex()`.
No triggers (explicit rebuilds are auditable). User query text is tokenized
into quoted AND-terms so hyphens/quotes can never become FTS operators.
Kind/subject filters apply post-match (subject via `resource_refs`).

## Consequence
`DELETE FROM resources_fts` + `reindex()` yields the same functional result
set (tested, order-insensitive: rank ties may reorder rowids). Backup covers
SQLite+CAS; FTS regenerates. TF-IDF/embeddings stay in later phases.
