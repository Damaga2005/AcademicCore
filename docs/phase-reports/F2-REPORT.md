# F2-REPORT — Resource Engine

Date: 2026-09-12 · Base: F1 `1e08109` (41 tests, all kept green)

## What was built
- `domain/ports.py`: `BlobStore`, `ResourceExtractor`, `ResourceIndexer`,
  `ResourceRecords` ABCs (domain defines ports; ast-pinned backend-free).
- `domain/resources.py`: `Resource` / `ResourceVersion` / `ResourceProvenance`
  (origins file|url|generated|manual|migration); `ResourceReference` untouched.
- `resources/adapters.py`: local-file, markdown, HTML (stdlib parser, scripts
  never collected/executed), PDF (pypdf best-effort, `deferred` without it,
  `failed` on corrupt — never a crash, never silent-empty). ZIP refused
  explicitly (deferred boundary, tested).
- `infrastructure/cas.py`: SHA-256, 1 MiB streaming, atomic `os.replace`,
  read-time integrity check (`CorruptBlob`), `exists/delete`, hex-only paths,
  size-capped `put_file` with tmp cleanup.
- Migrations `005_resources` + `006_fts` (small, rerunnable); records with
  `unit_of_work` rollback; FTS indexer with safe query compiler + subject
  filter via `resource_refs`.
- `application/ingest.py`: detect→adapter→read→hash→dedupe→store→records→
  extract→index; idempotent dupes; same-source-changed-bytes → new version;
  explicit `resource_id` versioning; URL ingestion refused; traversal/NUL/
  oversize guarded; `reindex()` from canonical store.
- UI: Resources tab (list/import/inspect/search/reindex), thin slots.
- Config: `ingest.max_bytes` (default 100 MiB), `ingest.cas_dir` override.

## Boundaries / debt
- `engines/resource.py` (F0) kept intact but SUPERSEDED by the ports path;
  removal is a F5+ cleanup, not F2 scope.
- ZIP extraction, Stirling, Ollama, OneDrive, RAG/vectors, Document AST,
  Knowledge/SdM migration: explicitly out (interfaces only where needed).
- PDF without pypdf → `deferred` (visible, not silent). Block `%` of scheme
  (F1 debt) untouched. FTS rank-tie order not pinned (set-equality pinned).

## Conversor-HTML-A-MD relation
Reference only: extension→kind mapping and metadata ideas (title extraction,
asset hashing) informed F2 adapters; NO code copied, NO Tk architecture
ported. Full HTML/table/MathML fidelity belongs to F3 Document Engine.

## Tests
40 new (cas 8, extract 7, ingest 7, identity 3, provenance 3, fts 3,
security 7, arch +1). Suite: **81 passed** in ~24 s.
