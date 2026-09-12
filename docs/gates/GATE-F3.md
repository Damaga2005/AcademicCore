# GATE F3 — Document + PDF Engine: ✅ PASS (2026-09-12)

Suite: **123 passed, 2 skipped** (81 F0/F1/F2 + 42 F3; skips = reportlab
ausente, path honesto). Fuentes originales intactas (Conversor `e5b8d60`).

## Conversor
- [x] Auditado (20 componentes) · reutilizables identificados · alta calidad
  reutilizada/adaptada (math/tables/images/sanitize/metadata/encoding)
- [x] Nada duplicado innecesariamente (markdownify/Tk/genanki fuera)
- [x] Procedencia (headers + REUSE-MAP) · licencia MIT revisada
- [x] Tests de equivalencia vs módulo original · repo intacto

## Document AST
- [x] 19 kinds · independiente Qt (test stdlib-only) · metadata · headings/
  paragraphs/lists/tables/images/links/code/equations · schema v1 ·
  serialización determinista · validación (rechaza corruptos)

## Parsers / Renderers
- [x] Markdown→AST · HTML→AST · sanitización (superset) · MathML→LaTeX
  preservado (1:1) · round-trip semántico estable
- [x] AST→Markdown · AST→HTML · escaping seguro

## Provenance
- [x] Resource + ResourceVersion + parser + versión + timestamp + history chain

## PDF
- [x] Engine + native backend + extraction/metadata/pages + PDF→AST +
  original preservado (derivaciones, nunca overwrite)

## Stirling
- [x] Repo oficial investigado · licencia/distribución documentadas ·
  v2.14.3 fijada · runtime manager · bootstrap · health · API adapter ·
  capabilities · op real (vs mock HTTP) · output validation · start/stop/
  restart/timeout/cleanup/localhost · funciona sin Stirling (native default)

## Security / Regression
- [x] traversal · malicious HTML · malformed/oversized PDF · overwrite ·
  injection · temp cleanup — todos pineados
- [x] F0 PASS · F1 PASS · F2 PASS · F3 PASS

Estados: IMPLEMENTED donde hay código, VERIFIED donde hay ejecución real,
SIMULATED solo bootstrap live. **Fase 4 NO iniciada.**
