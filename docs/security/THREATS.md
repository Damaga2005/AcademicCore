# Security baseline (Phase 0 — inputs are hostile; F2 ingestion hardened)

- Subprocess: no `shell=True`, arg lists, timeouts, temp-dir jails; allow-list
  binaries (ngspice, pdflatex, Stirling sidecar).
- ZIP: anti zip-slip (canonical path check), anti zip-bomb (size/count caps —
  port Gestion `BACKUP_MAX_*`), no executable extraction.
  F2 STATUS: ingestion REFUSES archives (`.zip/.7z/.rar` → UnsupportedType,
  tested, zero rows written) — extraction deferred to a later phase.
- Path traversal: CAS paths derived from hex hash only; uploads validated by
  magic bytes + extension allow-list (port `utils.py`).
  F2 STATUS: `FileBlobStore` paths derive only from validated sha256 hex;
  `..`/NUL inputs refused (`SecurityError`, tested); URLs never fetched
  (explicit-adapter boundary, tested).
- HTML/URLs: sanitize on ingest (BS4 allow-list), no remote fetch without opt-in.
  F2 STATUS: stdlib `html.parser` only — scripts/styles never collected,
  JS never executed, no network (tested).
- LaTeX: `--no-shell-escape` equivalent, compilation in sandbox temp dir.
- SPICE: netlists generated from canonical Circuit only; backend stdout parsed,
  never eval'd.
- Secrets: env / OS store only; never in SQLite payloads or git.
- F2 ingestion: size cap `ingest.max_bytes` (default 100 MiB, streaming
  enforced); corrupt PDFs degrade to `failed` status, never crash ingest;
  failed imports roll back canonical records (tested); CAS blobs immutable
  (overwrite impossible by construction); FTS input compiled to quoted
  AND-terms (no operator injection).
- Threat model + per-engine hardening land with each phase; this file is the gate.
