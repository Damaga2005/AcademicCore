# ADR-0019 — Documents live in the subject context, bytes live in CAS

Date: 2026-09-23 · Status: Accepted

## Context
Gestion stores files on disk (`DOCUMENTOS_DIR/...`) plus DB rows; F2 already
provides CAS + versions + provenance and F3/F3.1 the AST and FTS.

## Decision
A document is an F2 `Resource`; the academic relation is
`course_documents(subject_id, resource_id, category, group_id, tags,
legacy)` + `document_groups`. Categories = Gestion's four plus the F4.1
tabs (guía docente, apuntes, problemas). Same bytes -> same resource
(dedup), possibly linked to several subjects; moving a document changes
the relation, never the bytes. Reading progress, extracted pages
(`document_pages`) and study-space selections reference the resource.
External resources (Wuolah/Studocu/...) are URL-only records; they are
never fetched (no SSRF surface).

## Consequence
One documentary universe (no FS+DB duplicate). Files refused by F2 adapters
(zip...) are stored as opaque bytes with `extraction_status=deferred`.
