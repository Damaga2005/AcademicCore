# GATE-F3-CERTIFICATION — F3-ext Implementación (F3.1)

> Autoridad de diseño: `docs/gates/GATE-F3-DESIGN.md` (F3.0, aprobado).
> Baselines: AcademicCore `3642ca5`, Conversor-HTML-A-MD `bad31042`.

## 1. Baseline inicial

- `main` limpio en `3642ca53deb0a04335d6766d90aecd34637abd75`
  (`cert: certify E0.4 explainable engineering deep observability`).
- Sin reset ni force-push. 6 commits de implementación + este gate.

## 2. Commits

```text
66f578c feat(f3): add canonical document digest
475f735 feat(f3): harden office/xml import boundaries and adapt OMML extraction
c866db2 feat(f3): unify formula normalization and add problem extraction
8ec0163 feat(f3): add document format adapters
1dbabb3 feat(f3): deepen HTML importer and add latex renderer
82c07c8 test(f3): add golden corpus
<este>  test(f3): certify f3-ext
```

## 3. Archivos

Nuevos (16): `documents/{limits,latex_norm,omml,office_security,formulas,
problems,terms,render_latex,toc,links,batch,docx_adapter,ipynb_adapter,
tabular_adapter,trace}.py`, `tests/{test_f3_ext,test_f3_golden}.py`.
Modificados (4): `documents/{ast,html_parser,__init__}.py`,
`tests/test_architecture.py` (allowlist stdlib `hashlib/json`),
`docs/migration/CONVERSOR-REUSE-MAP.md` (§F3.1). Ningún otro módulo tocado.

## 4–8. Clasificación final

- MIGRATED: OMML→LaTeX (+cases/borderBox), IPYNB adapter, tablas
  rowspan/colspan como spans estructurales, shielding math 9 fuentes,
  footnotes `[^n]`, mermaid/plantuml, metadata+encoding robusto.
- ADAPTED: `clean_latex_formula` canónica única (variante UC, flags
  `decimal_comma`/`frac_aggressive`, idempotente), fórmula/problema/
  término/Q→A extractors con provenance, DOCX (off-by-one corregido),
  CSV/XLSX, callouts normalizados (NOTE/TIP/WARNING/CAUTION/IMPORTANT/
  EXAMPLE/QUESTION), links exactos `.html→.md#anchor`, TOC/slugs NFKD.
- REIMPLEMENTED: batch (sorted/errores/caché/cancel), MD→HTML
  imprimible (no copiado: XSS/CDN sin SRI rechazados), XLSX sin pandas.
- REJECTED: fuzzy FS resolver, `extract_figs_from_scripts` (exige JS del
  curso), `problem_generator`, 37 solvers, UPCEngine, guías UPC, GUI Tk,
  lab HTML, `generate_q*`, SPICE/VHDL/C como artefactos F3.
- DEFERRED: OCR (UNSUPPORTED honesto), PDF tablas/imágenes avanzadas
  (sin gap probado vs pypdf nativo), Anki pleno (solo exporter futuro).

## 9. Nuevos hallazgos (F3.1, ninguno oculto)

- `a` a nivel de bloque perdía el enlace (descenso genérico): rama
  explícita con `_inline_node` (`html_parser.py:255`).
- `SOLUTION_SPLIT` consumía la línea (`Solución: \boxed{2}` → solución
  vacía): captura el resto de línea como solución.
- Catalán `Solució` (sin `n`) no casaba: alternativa añadida.
- XLSX: ruta `xl/worksheets/` perdida al resolver rels: corregida.
- `put` devuelve hex (`cas:` lo antepone `extract_images`): contrato fijado.
- `TraceEvent RESULT` exige `result`: `record_import` siempre emite uno.
- Shorthand `4k7`: raw preservado, nunca float espurio.
- Ninguna capacidad Conversor adicional fuera de la matriz F3.0.

## 10. APIs

```text
Document.digest() -> str  (canonical_json + sha256, sin timestamps/history)
parse_docx/parse_ipynb/parse_csv/parse_xlsx/parse_tabular(data, ...) -> (Document, warnings)
extract_from_markdown / extract_from_document / deduplicate / formula_sheet
extract_problems_from_text / extract_problems_from_document
extract_terms / extract_qa
render_latex.render(doc) -> str
toc.slugify/toc_entries/render_toc · links.rewrite_target/rewrite_soup_links
batch.convert_batch(files, convert, progress/cancel/cache) -> BatchResult
trace.record_import(...) -> ExecutionTrace  (document.import)
omml.omml_to_latex / parse_omml_fragment · latex_norm.clean_latex_formula
```

## 11. AST

Canónico, `schema_version=1` sin bump, sin kinds nuevos (callouts=
`quote+[!TYPE]`, footnotes=`link(#fn)+quote`, task=`[x]` textual).
`test_architecture.py::test_ast_is_stdlib_only` verde (stdlib+hashlib/json).

## 12. Provenance

Toda extracción (`ExtractedFormula/Problem/Term/QA`) exige
`source+locator` (DOM path, `ast/i/j`, celda, `md:n`, página). Tests:
cada ítem extraído porta fuente válida.

## 13. Digest

`sort_keys/separators(, :)/ensure_ascii/allow_nan=False`; excluye
`created_at/modified_at/history`. Tests: estabilidad, cambio timestamp
→ mismo digest, diferencia semántica → distinto, orden attrs invariante.
Multiseed `0/11/random` verde. 10 digests dorados pineados.

## 14. Assets/F2

Data-URI→`put_bytes` (MIME real, caps), `word/media`, png IPYNB igual
vía; remotas `remote-not-fetched` (título fallback, sin fetch). Sin CAS
paralelo. Dedup por hash de contenido.

## 15. Security

Límites `documents/limits.py` (HTML 10MiB, tablas 10k celdas, B64 5MiB,
ZIP 1000 miembros/50MiB, XML depth 64/200k nodos, asset 20MiB).
ENTITY/DOCTYPE rechazados, traversal/symlink/bombas pineados,
`javascript:/data:/vbscript:` nunca reescritos y neutralizados en 3
capas, `eval/exec/compile/pickle/subprocess/network` ausentes
(auditoría grep: solo `re.compile` + `urllib.parse`). Sin macros,
sin ejecución de notebooks/JS.

## 16–18. D1/D2/D3

- D1: adapters tras la capa documents; `ast.py` stdlib-only; bs4/lxml/
  ET-zip solo en adapters; sin Qt/Tk/Flask/FS/red en dominio.
- D2: `AC-ADP-21x/22x/23x/24x/25x`, `AC-VAL-22x/23x/24x/25x`,
  `AC-UNS-250`; `UNSUPPORTED`/warning explícito, nunca `except:pass`
  silencioso; `to_ui_error` único intacto.
- D3: cero dependencias nuevas (stdlib + bs4/lxml/pypdf existentes;
  sin fitz/AGPL, sin pandas, sin genanki). MIT intacto.

## 19. E0.4

`documents/trace.py` usa el `TraceRecorder` certificado
(`document.import`): solo hechos reales, contenido acotado (conteos),
`TRACE_TRUNCATED` explícito por budget, un RESULT con resultado.
Sin infraestructura paralela.

## 20–21. Tests + golden corpus

- F3 relevante: **95 passed, 2 skipped** (reportlab ausente, path
  honesto) en 12.04 s: `test_f3_ext` (40), `test_f3_golden` (4),
  ast/documents/html/markdown/equiv/compat/pdf/architecture/
  provenance/reproducibility.
- `test_f3_ext.py`: matriz §48 completa (AST, HTML, math, problemas
  ES/CA/EN, PDF, DOCX, IPYNB, XLSX/CSV, assets, seguridad, batch,
  trace, renderers, TOC).
- `test_f3_golden.py`: 8 HTML + 2 DOCX con digest+bloques pineados,
  neutralización maliciosa, colisiones slug (`tema,tema-1,cafe`).

## 22. Performance (snapshot, sin regresión exigible pre/post)

```text
html_small 1.9 ms · html_large_200sec 203.6 ms · mathml_50eq 25.1 ms
formula_extract 2.8 ms · problem_extract_20 0.5 ms · docx_200para 4.2 ms
render_markdown 2.6 ms · render_latex 4.9 ms
```

## 23. Limitations (honestas)

PDF=tablas/imágenes/OCR UNSUPPORTED; XLSX lector mínimo (sin estilos/
fusión avanzada); fuzzy links OFF; `extract_figs_from_scripts`
UNSUPPORTED; heurísticas problema/término marcadas `heuristic=True`
(falsos positivos posibles); `==mark==` no-GFM.

## 24. Reproducibility

Suite completa en este entorno: 11 failed preexistentes CRLF
(`test_e0_execution_trace`, `test_f8q4`, `test_f8q5`), conjunto
byte-idéntico en worktree baseline `3642ca5` sin cambios F3.1
(verificado 2026-09-23) → **cero regresiones F3.1**. Resto del suite
passed. F3/GATE-F3.md no degradado (95 passed arriba).

## 25. Verdict

```text
F3.1 COMPLETE / CERTIFIED
```
