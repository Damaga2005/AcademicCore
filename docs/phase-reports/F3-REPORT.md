# F3-REPORT — Document Engine + PDF Engine (+ Conversor reuse, + Stirling)

Date: 2026-09-12 · Base: F2 `d645c16` (81 tests, all kept green → 123 total)

## F3-A — audit + reuse (priority: reuse > fidelity > … > UI)
- `CONVERSOR-F3-AUDIT.md`: 20 componentes con veredicto (fuente intacta,
  HEAD `e5b8d60`, MIT misma autoría). `CONVERSOR-REUSE-MAP.md`: tabla
  origen→destino→tipo→deps→tests→motivo.
- REUSED_DIRECT: `encoding.py` (BOM/meta/cp1252, labels idénticos).
- ADAPTED (misma semántica, arquitectura nueva): `conversor_math.py`
  (MathML 1:1 incl. annotation-priority + msup fix verificado por tests;
  `polish()` es `clean_latex_formula` reducido y FLAG-GATED — el source
  canónico nunca se reescribe), `conversor_tables.py` (grid 2D; spans
  estructurales en vez de `(cont.)`), `conversor_images.py` (base64/FIGS→CAS),
  `conversor_sanitize.py` (noise + event-handlers/js: URLs = superset),
  metadata, callouts/figures/def-lists/task-lists/details, code-tables,
  internal links, diagrams→CodeBlock.
- REWRITTEN: markdown subset parser, AST→MD/HTML renderers (markdownify
  pipeline sustituido, no duplicado).
- REJECTED: Tk GUI, genanki/quiz, batch curso, tests ad-hoc, Anki-sanitize,
  nav/course-component preprocessors.
- Tests de equivalencia importan el módulo ORIGINAL y comparan 1:1
  (mathml 14 casos, polish subset + divergencia intencional pineada, tablas
  con resolución de spans, imágenes byte-identical, sanitize superset,
  encoding vectors, metadata).
- AST: 19 kinds, frozen, SCHEMA_VERSION=1, validate(), JSON determinista;
  `ast.py` verificado stdlib-only por test. Parsers: html (bs4 solo en esa
  capa), md subset. Round-trip md→AST→md→AST estable (comparación normalizada).
  Document derivations en `007_documents` keyed (resource,version,parser) con
  history chain; originales intactos.

## F3-B — PDF + Stirling
- `PDFEngine` + `NativePDFBackend` (pypdf BSD): inspect/metadata/pages/
  extract/merge/split/rotate + validación de outputs; `render_page` =
  `UnsupportedOperation` honesto; PDF→AST por páginas con warnings de escaneo.
- PyMuPDF rechazado (AGPL) en ADR-0015 aunque instalado en dev.
- Stirling: investigación oficial (v2.14.3 2026-08-06, open-core MIT+propietario
  → jamás vendored; API `/api/v1`, X-API-KEY, Swagger; assets jar/msi).
  `StirlingRuntime` (detect/version/health/start/stop/restart, localhost-only,
  timeouts, cleanup) + `StirlingPDFBackend` (merge/split/rotate/extract,
  capability detection vía OpenAPI, output validation → CAS).
- Certificación honesta: cliente VERIFIED vs fake HTTP real; bootstrap/ops
  reales SIMULATED (sin Java/Docker) en `@pytest.mark.external`; nada marcado
  VERIFIED sin ejecución.

## UI / perf / seguridad
- Resources tab: import/list/inspect/search/reindex + build document +
  export MD/HTML + estado Stirling. Perf medido (bounds generosos, suite ~28 s).
- Seguridad: js/event-handlers/malformed/escaping pineados; PDF corrupt/
  empty/oversize/traversal/overwrite-timeout/process-failure/invalid-output/
  cleanup/injection pineados; subprocess sin shell, temp aislado.

## Deuda
- `engines/resource.py` (F0) sigue superseded (cleanup F5+). PDF text de
  escaneados = deferred. Endpoint map Stirling sujeto a confirmación live
  (auto-detección lo absorbe). reportlab ausente → 2 skips honestos.
