# ADR-0013 — Resource vs ResourceReference vs ResourceVersion

Date: 2026-09-12 · Status: Accepted

## Context
F1 introduced `ResourceReference` (academic link subject→resource) without a
managed-content counterpart. F2 needs canonical bytes + history without
conflating academic linkage, content identity, and version lineage.

## Decision
Three distinct concepts, three owners:
- `ResourceReference` (F1, unchanged): academic link; points AT a Resource.
- `Resource` (`domain/resources.py`): managed content, stable id
  `resource:<scope>:r:NNNNN` (scope = first linked subject, else `general`),
  allocated once via persisted counters. Id never changes.
- `ResourceVersion` (append-only rows): one per distinct content_hash.
  Same bytes → deduplicated, no new version. Changed bytes on the same
  logical source → new version; history preserved, never silently destroyed.
- `ResourceProvenance`: origin/file|url|generated|manual|migration, source
  path (metadata, may go stale), hash, timestamps, adapter id+version,
  extraction status, parent version link.

Content hash participates in DEDUPLICATION only — never in identity.

## Consequence
Reindex/reimport/move preserve ids (tested). Block-level `%` style future
extensions (Document AST v3, Knowledge v4+) build on versions, not on paths.
