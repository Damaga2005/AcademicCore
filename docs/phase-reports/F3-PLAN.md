# F3-PLAN — Document Engine + PDF Engine (+ Conversor reuse, + Stirling)

Date: 2026-09-12 · Base: F2 `d645c16` (81 tests green, tree clean, sources intact)

## Pre-flight (done)
`pytest` 81 passed · tree clean · Conversor HEAD `e5b8d60` intact ·
CONVERSOR-F3-AUDIT.md written · Stirling official research done
(v2.14.3, 2026-08-06; open-core MIT+proprietary; no Java/Docker locally →
bootstrap REAL test will be SIMULATED, honestly).

## F3-A — Document Engine
New package `src/academic_core/documents/`:
- `ast.py`: frozen dataclass nodes (Heading/Paragraph/Text/Emphasis/Strong/
  Link/List/ListItem/Quote/CodeBlock/InlineCode/Table/TableRow/TableCell/
  Image/Equation/ThematicBreak/Section + Metadata), SCHEMA_VERSION=1,
  `validate()`, deterministic JSON (de)serialization. Deps: stdlib only.
- `conversor_math.py` (ADAPT): OPERATOR_MAP/NAMED/GREEK/SUP/SUB maps +
  `parse_mathml_to_latex` + `clean_latex_formula` (flag-gated) +
  `html_formula_node_to_latex` + shield pipeline → Equation nodes
  (source preserved, format latex|mathml, display inline/block).
- `conversor_tables.py` (ADAPT): 2D grid + code-table detect → Table nodes
  with rowspan/colspan (no `(cont.)` text hack).
- `conversor_images.py` (ADAPT): base64/FIGS extraction → CAS put-callable.
- `conversor_sanitize.py` (ADAPT): `clean_soup_noise`.
- `conversor_metadata.py` (ADAPT): `extract_metadata`.
- `encoding.py` (REUSE_DIRECT): `read_html_file_safely`.
- `html_parser.py` (ADAPT): preprocessors + shields → AST (bs4/lxml only in
  this layer; AST stays pure).
- `markdown_parser.py` (REWRITE): subset MD→AST (Conversor has no MD parser).
- `render_markdown.py` / `render_html.py` (REWRITE): AST→MD/HTML, escaped,
  deterministic. Round-trip: AST-normalized compare.
- `documents.py` (application): build/store Document derivations
  (resource+version+parser+timestamp+history), migration `007_documents.sql`.
- Deps added to requirements: beautifulsoup4, lxml, pypdf (runtime).
  markdownify/genanki/tk NOT added. mathml2latex stays lazy-optional.

## F3-B — PDF Engine
New package `src/academic_core/pdf/`:
- `engine.py`: `PDFEngine` + `NativePDFBackend` (pypdf BSD: inspect/metadata/
  extract_text/pages/split/merge/rotate; `render_page` = UnsupportedOperation,
  honest) + `StirlingPDFBackend` (API client, localhost:8080, X-API-KEY,
  capability detection via OpenAPI, timeouts, temp-jail, output validation →
  CAS as new ResourceVersion). Domain sees only the engine interface.
- `stirling.py`: research constants (VERSION v2.14.3, source, assets),
  `StirlingRuntime` (detect/install-bootstrap/version/health/start/stop/
  restart/cleanup) with states NOT_INSTALLED…STOPPED; no-Java here →
  bootstrap SIMULATED; works-without-Stirling guaranteed.
- PDF→AST: native text per page → Paragraph/Heading blocks + provenance
  (backend, version, pages, warnings, status).
- Tests: mock HTTP server (real localhost HTTP, stdlib) for READY/ERROR/
  TIMEOUT/INVALID_OUTPUT/NON_ZERO_EXIT/restart/cleanup; `@pytest.mark.external`
  real tests skipped without runtime; cert states honest (IMPLEMENTED/
  SIMULATED, never VERIFIED for unexecuted paths).

## Out of scope (§47)
RAG/embeddings/vectores, Ollama/modelos, OneDrive, adaptive, SdM migration,
SPICE/KiCad, GUM/MC, installer, F4.
