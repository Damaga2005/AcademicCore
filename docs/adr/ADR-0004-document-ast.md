# ADR-0004 — Canonical Document AST (Markdown is NOT the internal model)

Date: 2026-09-12 · Status: Accepted

## Decision
Internal model: `Document(meta, blocks[])` with block kinds
`section|paragraph|equation|figure|table|code|link|reference`.
All importers (HTML/PDF/DOCX/LaTeX/Markdown) convert TO it; all exporters
(Markdown/HTML/LaTeX/PDF) convert FROM it.

## Rationale
Conversor audit: the `UltraFaithfulMarkdownConverter` is valuable but Markdown-
as-model loses equation/table/figure semantics needed by formulas, labs and
authoring. Sistemes audit: chunks/sections/tables/visuals already want a typed
AST with provenance. AST preserves math fidelity + provenance across conversions.

## Consequences
- `engines/document_ast.py` is the v0 AST; converters land in Phase 2-3.
- Every equation block keeps original LaTeX + provenance (see ADR-0010 + Formulas).
