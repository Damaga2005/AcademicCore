# ADR-0021 — Teaching guides and knowledge reuse F3/F3.1 (no new parser)

Date: 2026-09-23 · Status: Accepted

## Decision
`documents/syllabus.py` ports Gestion `guia_docente.py` as a pure,
bounded, text-only heuristic fed by the F3/F3.1 AST of an imported
resource (`DocumentService.load_ast`). The result is a proposal with
provenance (resource id, version, content hash, parser, extractor) and
`needs_review` flags; `KnowledgeService.apply_syllabus` refuses to write
without explicit confirmation. Subject knowledge reuses the F3.1
formula/problem/term extractors. GREELEC data never lives in code.

## Consequence
Golden equivalence with the real `guia_docente.py` (11 texts). Markdown
sources lose soft line breaks in the F3 parser; guides are normally PDFs
(line-preserving) — documented limitation.
