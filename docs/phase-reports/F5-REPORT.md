# F5-REPORT — Authoring Engine

Date: 2026-09-12 · Base: F4 `1a6f699` (145 passed, 2 skipped → 174 + 2 kept)

## Pre-work (before code)
`docs/F5_AUTHORING_AUDIT.md` (AST-19 sin cambios necesarios, gaps, reuse) +
`docs/F5_AUTHORING-DESIGN.md` (modelo, comandos, lifecycle, versionado,
validación, plantillas, copy/paste, búsqueda, UI, límites) + `F5-PLAN.md`.

## Built (no F3 rewrites; one model; Markdown never canonical)
- `domain/authoring.py`: path-addressed commands (Insert/Delete/Replace/Move/
  UpdateText/UpdateMetadata/SetAttribute) with apply/inverse, lifecycle graph
  DRAFT→REVIEW→PUBLISHED→ARCHIVED (+DRAFT→ARCHIVED, REVIEW→DRAFT),
  `AuthoringDocument` (undo/redo, cap 200, redo invalidation, versions
  untouched). Pure, no Qt/IO.
- `documents/validate.py` (structured issues, never silent), `templates.py`
  (5 AST-generating templates), `documents/search.py` (deterministic hits).
- `document` resource kind (AST JSON bytes, Authoring-only) + `update_title`.
- Migration `009_authoring` (`authored` lifecycle, `doc_links` 6 target kinds).
- `application/authoring.py`: templates/imports/open/save (noop-identical,
  parent chains, FTS reindex, title sync)/validate/links/lifecycle/autosave
  (capped, recover, cleanup)/copy-paste (AST verbatim, md/html explicit
  degrade, else reject)/search. `DocumentService.load_ast()` added.
- `ui/authoring.py` Authoring tab: browser/outline/block editors (markdown-
  mediated + dedicated equation/code/metadata)/save/undo/redo/validate/export/
  links/lifecycle/templates. Qt reflects service state; never canonical.
- Fidelity fixes found by round-trip battery (shared with F3, covered by
  F3+F5 tests): md parser keeps `cas:` targets; renderers keep bare-inline
  list items; html parser reads back `span.math-*`.

## Equivalence definition (round-trips)
Same block-kind sequence; inline text modulo whitespace; equation sources
exact; image refs exact; code content exact; link targets exact; list_item
normalized (bare text ≡ paragraph). Byte-identity NOT required; tables keep
header/row structure (spans structural).

## Debt
F3 markdown subset unchanged (footnotes/definitions out, documented);
`engines/resource.py` still superseded (F5+ cleanup); tree() N+1 unchanged.
