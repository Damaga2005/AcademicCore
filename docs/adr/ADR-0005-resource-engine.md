# ADR-0005 — Resource Engine pipeline

Date: 2026-09-12 · Status: Accepted

## Decision
Pipeline: `SOURCE → INGEST → EXTRACT → NORMALIZE → STRUCTURE → IDENTIFY →
LINK → INDEX → ACADEMIC RESOURCE`, with per-format `ResourceAdapter`s.
Scope v1: pdf, html, md, latex, docx, pptx, image, csv, json, zip, dataset.

## Rationale
Unifies Conversor batch ingestion (`process_all_course_temas`), Gestion
document upload validation, and Sistemes KB build under one ID/provenance
regime. Adapters isolate fragile code (scrapers, DOCX/PPTX parsers).

## Consequences
- `engines/resource.py` defines interfaces; adapters land Phase 2.
- Every resource gets stable ID + CAS hash + provenance at INGEST.
