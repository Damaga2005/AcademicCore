# ADR-0003 — Storage: SQLite + Filesystem + CAS + Incremental Indexes

Date: 2026-09-12 · Status: Accepted

## Decision
- **SQLite**: metadata, relations, config, state, references, history
  (single-user; WAL mode; forward-only migrations).
- **Filesystem + Content-Addressed Storage (sha256)**: PDFs, images, video,
  datasets, LaTeX, netlists, results. Blobs NEVER in SQLite (tested).
- **Indexes**: FTS5 lexical (BM25) + local TF-IDF semantic + RRF hybrid —
  ported from Sistemes-de-Mesura; no external vector DB in v1.
- RAM discipline: lazy loading, streaming, background workers, incremental
  indexing, batch processing (machine has 16 GB; disk is cheap).

## Consequences
- `Store` implements CAS layout `<cas>/<hh>/<hh>/<sha256>` + `entities` table.
- Corpus files keep CRLF + manifest hashes (`.gitattributes` precedent).
- Backup = SQLite dump + CAS snapshot (Gestion-Academica `backup.py` limits ported).
