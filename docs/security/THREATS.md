# Security baseline (Phase 0 — inputs are hostile)

- Subprocess: no `shell=True`, arg lists, timeouts, temp-dir jails; allow-list
  binaries (ngspice, pdflatex, Stirling sidecar).
- ZIP: anti zip-slip (canonical path check), anti zip-bomb (size/count caps —
  port Gestion `BACKUP_MAX_*`), no executable extraction.
- Path traversal: CAS paths derived from hex hash only; uploads validated by
  magic bytes + extension allow-list (port `utils.py`).
- HTML/URLs: sanitize on ingest (BS4 allow-list), no remote fetch without opt-in.
- LaTeX: `--no-shell-escape` equivalent, compilation in sandbox temp dir.
- SPICE: netlists generated from canonical Circuit only; backend stdout parsed,
  never eval'd.
- Secrets: env / OS store only; never in SQLite payloads or git.
- Threat model + per-engine hardening land with each phase; this file is the gate.
