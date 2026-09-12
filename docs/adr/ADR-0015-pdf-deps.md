# ADR-0015 — PDF dependencies: pypdf native, no PyMuPDF, Stirling external

Date: 2026-09-12 · Status: Accepted

## Context
Native PDF ops need a library (license, maintenance, Windows, security,
memory, size). Candidates: pypdf (BSD-3), PyMuPDF (AGPL-3.0-or-later).

## Decision
- Native backend = **pypdf** (BSD-3, pure Python, maintained): inspect,
  extract text/pages, merge, split, rotate. `render_page` honestly
  unsupported natively.
- **PyMuPDF rejected** despite being installed in dev: AGPL would encumber
  distribution; rasterization is not a gate requirement.
- Advanced ops (OCR/compress/future render) = external Stirling runtime via
  localhost API (ADR-0006, STIRLING-INTEGRATION.md). Domain depends only on
  `PDFBackend`.

## Consequence
Runtime deps gain `pypdf` (+ F3 `beautifulsoup4`, `lxml`). No AGPL code in
the tree. `render_page` stays `UnsupportedOperation` until a compatible
backend exists.
