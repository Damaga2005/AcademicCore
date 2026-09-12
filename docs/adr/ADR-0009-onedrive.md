# ADR-0009 — OneDrive as provider (never a core dependency)

Date: 2026-09-12 · Status: Accepted

## Decision
`ResourceProvider` interface with `LocalFilesystemProvider`, `OneDriveProvider`
(disabled by default), `GitHubProvider`. OneDrive = read-only ingest in Phase 11;
no destructive sync until provenance + conflict policy + backups are proven.

## Rationale
Materials live in OneDrive today, but core must work fully offline on local FS.
Provider boundary keeps auth/sync fragility out of domain and preserves stable
IDs across re-ingest.

## Consequences
- Sync keeps IDs/provenance/state; conflicts resolve by content hash + manual review.
- Secrets (tokens) live in OS credential store / env, never in SQLite payloads.
