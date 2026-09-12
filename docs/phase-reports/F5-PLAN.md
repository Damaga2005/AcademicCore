# F5-PLAN — Authoring Engine

Date: 2026-09-12 · Base: F4 `1a6f699` (145 passed, 2 skipped; tree clean)

## Pre-work (done)
`docs/F5_AUTHORING_AUDIT.md` (estado + gaps + decisión: sin nodos nuevos) +
`docs/F5_AUTHORING-DESIGN.md` (modelo, comandos, lifecycle, versionado,
validación, plantillas, copy/paste, búsqueda, UI). Sin reescrituras F3.

## Build order
1. `domain/authoring.py`: paths, 7 comandos puros (apply/inverse), lifecycle
   graph, `AuthoringDocument` (undo/redo, tope 200), `ValidationIssue`.
2. `documents/validate.py`: `validate_document` (estructura, metadata,
   enlaces, imágenes/CAS, ecuaciones, tablas, headings, oversize).
3. `documents/templates.py`: 5 plantillas → AST.
4. `documents/search.py`: `search_document` determinista.
5. `RESOURCE_KINDS += "document"` (+registry note: sin adapter de ingesta;
   solo Authoring crea este kind) + `update_title` en records.
6. Migración `009_authoring.sql` (`authored`, `doc_links`).
7. `application/authoring.py`: open/save/versionar/autosave/copy-paste/links/
   validación + `DocumentService.load_ast()`.
8. `ui/authoring.py`: pestaña Authoring (browser/outline/block-editor/
   metadata/acciones). `app.py`/`main_window.py`: solo wiring.
9. Tests: authoring (model+commands+undo/lifecycle), validation, templates,
   versioning, roundtrip-F5 (MD+HTML con definición de equivalencia),
   academic-links, security-F5, compat-F3 (golden v1), perf-F5, UI authoring.
10. Docs: F5-REPORT, GATE-F5, README/CHANGELOG, arch tests.

## Out
RAG/embeddings/AI/Ollama/OneDrive/SPICE/GUM/exam-gen/corrección/installer/
plugins. Footnotes/definitions MD fuera de alcance.
