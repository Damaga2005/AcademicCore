# ADR-0006 — PDF Engine via Stirling-PDF adapter (isolated, opt-in)

Date: 2026-09-12 · Status: Accepted (with pending runtime decision)

## Decision
Domain depends only on `PDFService` (`merge/split/compress/ocr/...`).
Stirling-PDF is consumed through `StirlingAdapter` against an **isolated
runtime** (separate process/container or local service URL), disabled by default.

## Investigation (pending before Phase 3)
- License: Stirling-PDF is Apache-2.0 (verify pinned release).
- Distribution: do NOT bundle blindly — prefer sidecar service or documented
  bring-your-own-runtime; record RAM (~512 MB–1 GB Java) vs 16 GB budget.
- Windows integration, updates, process isolation, temp-file/file-overwrite
  safety, network exposure (bind 127.0.0.1 only).

## Consequences
- No Stirling imports in domain. `stirling_enabled=false` default in config.
- Phase 3 benchmarks merge/split/OCR before enabling by default.
