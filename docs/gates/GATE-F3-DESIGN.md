# GATE-F3-DESIGN — F3-ext Auditoría + Diseño (F3.0)

> Fase: F3.0 SOLO auditoría + diseño. No modifica código. Implementación (F3.1) pendiente de coherencia.
> Regla: auditar TODO Conversor-HTML-A-MD, seleccionar solo lo reutilizable, sin romper arquitectura certificada.

---

## 1. Baseline real AcademicCore

- Repo: `https://github.com/Damaga2005/AcademicCore`
- Branch: `main`, limpio, `origin/main` sincronizado.
- HEAD verificado: `3642ca53deb0a04335d6766d90aecd34637abd75`
  `cert: certify E0.4 explainable engineering deep observability`
- Coincide con baseline esperado `3642ca5` del prompt. No se fuerza SHA antiguo.
- Estado roadmap: F0–F8-P5 CERTIFICADAS, D1/D2/D3 + F15 + F8-Q + E0–E0.4 CERTIFICADAS.
- F3 actual ya CERTIFICADO (`docs/gates/GATE-F3.md`, 2026-09-12, 123 passed): AST 19 kinds, HTML/MD parsers, sanitize, MathML→LaTeX 1:1, PDF native, Stirling opcional. F3-ext NO duplica; solo extiende gaps.

## 2. Baseline real Conversor-HTML-A-MD

- Repo: `https://github.com/Damaga2005/Conversor-HTML-A-MD`
- HEAD verificado (ls-remote + clone): `bad31042a8b5b4be970ea250cae1f9f36bff6fda`
  `docs: comprehensive update of README.md … 40-test suite`
- Coincide con baseline del prompt. Código fuente es autoridad (README orientativo).
- Inventario real: 612 archivos, 28 `.py` (11 raíz + 17 `tests/`):
  raíz: `conversor_html_notebooklm.py` (~7871 lín, pipeline HTML→MD + GUI Tk),
  `universal_converters.py` (1499 lín, 15 funciones, PDF/DOCX/IPYNB/XLSX/CSV/MD→HTML/Anki/fórmulas/problemas/glosario/batch),
  `engineering_tools_suite.py` (37 solvers), `upc_degree_engine.py` (~444 lín),
  `upc_gui_tab.py` (~689 lín), `build_master_upc_engine.py`, `download_and_parse_guides.py`,
  `generate_q1_q2/q3_q4/q5_q6/q7_q8.py`, `conversor_html_notebooklm.spec`, `requirements.txt`.
  tests: `test_formula_and_problem_extraction.py` (9/9 pasan), `test_universal_and_lab.py` (9 tests),
  `test_upc_curriculum.py`, `test_engineering_tools.py`, `test_resolver*.py` (harness ad-hoc, hacen skip),
  GUI smoke (`test_full/modern/modular/theme_gui.py`), utilidades (`problem_generator.py` GENERACIÓN, `deep_audit.py`, etc.).
- Sin Flask/SQLAlchemy en repo (grep 0). GUM = metrología ISO/IEC 98-3, no framework.

## 3. Arquitectura actual AcademicCore (reutilizar, no duplicar)

- `src/academic_core/documents/`: `ast.py` (frozen `Node(kind,attrs,children)` + `Metadata` + `Document(meta,history,children)`, `SCHEMA_VERSION=1`, 19 kinds, `validate()`, `to_dict/from_dict`, sin `digest()` propio), `html_parser.py` (`PARSER html-parser 3.0`, bs4→AST puro, callouts, figs, images→CAS, shield_math, mermaid→code_block), `markdown_parser.py` (`markdown-parser 3.0`, subset ATX/GFM/$), `render_html.py` (escaping, `javascript:` dropeado), `render_markdown.py` (determinista GFM), `conversor_{images,math,sanitize,tables}.py` (adaptado MIT: data-URI→CAS sin fetch remoto, `parse_mathml_to_latex` 1:1, `clean_soup_noise`, `table_grid` con spans estructurales, `encoding.py` BOM→meta→utf-8→cp1252), `validate.py` (`MAX_BLOCKS=20000`, `MAX_TEXT_CHARS=2M`, link/image/equation checks), `security.py` (`is_javascript_scheme` único, 11 variantes pineadas), `search.py`, `templates.py`.
- Aplicación: `DocumentService.build(resource,version,parser=auto)` persiste `ast_json sort_keys`, originales inmutados.
- F2 CAS: `FileBlobStore` (`^[0-9a-f]{64}$`, streaming 1MiB, `os.replace` atómico, re-hash). Imágenes `cas:<hex>`, remotas no fetcheadas.
- D1: puertos/adaptadores, dominio stdlib-only, prohibido Qt/Tk/Flask/filesystem/network/subprocess en dominio. D2: `AcademicCoreError(ValueError)` `AC-AREA-NNN`, `to_ui_error` único. D3: MIT, `bs4/lxml/pypdf`, PyMuPDF vetado (AGPL), PySide6 LGPL dinámico.
- E0.4: `execution-trace/1`, eventos ordenados, digest sha256 sin metadata, límites (`MAX_EVENTS 10000`, matrices>8×8 digest, `TRACE_TRUNCATED`, budget 4000ev/5MB), determinismo `PYTHONHASHSEED 0/11/2024/random`, overhead 3-11%.
- Tests: `test_ast/documents/html_docs/markdown_roundtrip/conversor_equiv/compat_f3` + `conversor_ref.py` (skip si ausente).

## 4. Inventario exhaustivo Conversor (resumen; detalle en auditorías F3.0)

- HTML→MD (`conversor_html_notebooklm.py`, 50 funcs + `UltraFaithfulMarkdownConverter` 12 métodos): selección `article/main/body`, `clean_soup_noise`, `escape` consciente `$`, `convert_pre` (lang), `is_code_table/extract_code_from_table`, `convert_blockquote`, `preprocess_callouts` (30 clases ES/CA/EN), `preprocess_course_components` (cards/defs/steps/boxes, 100% UPC), `preprocess_figures` + `extract_figs_from_scripts` (JS data-URI hack), `preprocess_footnotes` (`[^n]`), `rewrite_internal_links` (exacto + fuzzy FS), `preprocess_media` (YouTube/video/audio), `extract_metadata`, badges/YAML, `mark/kbd/sub/sup/del/ins/hr`, quiz `BANC/DATA/ITEMS`, SVG→LaTeX (comment/data-latex/aria/desc), `extract_base64_images`, `convert_html_table_to_gfm_2d` (matriz rowspan/colspan, `(cont.)`), `extract_and_shield_tables/diagrams` (mermaid/plantuml), pipeline 19 pasos, `parse_mathml_to_latex` + mapas, `clean_latex_formula` (+ duplicado en UC), `extract_and_shield_math` (9 fuentes), `generate_formula_sheet/glossary/flashcards/master/dashboard/cheatsheet`, `GUM_TEMPLATES`, `score_exam`, GUI Tk (~4000 lín, `ctypes WM_DROPFILES`), CLI `--preset notebooklm/obsidian/github`.
- Universales (`universal_converters.py`): `convert_pdf_to_markdown` (fitz, tablas, assets, headings por tamaño, sin test), `omml_to_latex` (15 constructos, mejor activo), `convert_docx_to_markdown` (ZIP/XML, heading off-by-one), `convert_ipynb_to_markdown` (nunca ejecuta, testeado), `convert_markdown_to_printable_html` (parser ingenuo, XSS, CDN sin SRI), `convert_markdown_to_anki` (regex Q→A + término→def, IDs fijos), `convert_excel_csv_to_markdown` (CSV stdlib, XLSX pandas valor-cacheado), `clean_latex_formula`, `extract_raw_formulas_from_file` (MD/HTML/DOCX/IPYNB/XLSX, PDF anunciado no implementado), `extract_formula_sheet_from_files`, `extract_problems_from_text/files` (ES/CA/EN, params `VAR=num unidad`, `\boxed{}`), `extract_spice_netlists_from_files`, `generate_technical_glossary_from_files`, `batch_convert_universal` (sin caché/cancel, errores tragados, orden FS no-determinista).
- Fórmulas/problemas: `OPERATOR_MAP/NAMED_FUNCS/GREEK/SUP/SUB`, `clean_math_text/wikipedia_latex`, `html_formula_node_to_latex`, `generate_formula_sheet_from_markdown` (respeta `\tag`), `extract_quiz_questions` (dominio), `problem_generator.py` = GENERACIÓN aleatoria (Wheatstone/INA/Pt100/ADC) → fuera F3.
- UPC/solvers: `UPCDegreeEngine` (CRUD curricular, quiz, exports, `exec`), 37 solvers puros stdlib (RF/analógica/digital/DSP/sensores; 2 emiten C/VHDL), `download_and_parse_guides.py` (regexes UPC `OBJETIVOS/Tema N/CALIFICACIÓN/BIBLIOGRAFÍA`, filtro `2309xx`), `build_master_upc_engine.py` (ETL), `generate_q*.py` (contenido + `exec`, anti-patrón), `upc_gui_tab.py`, `Laboratorio_Virtual_Sensores.html`, `data/` (source/generated), `dist_course_md/` (corpus ejemplo catalán, solo fixture opcional).

## 5. Matriz de reutilización (decisión)

| Capacidad | Archivo/función | Acción | Motivo |
|---|---|---|---|
| Tabla HTML→GFM matriz rowspan/colspan + shielding | `convert_html_table_to_gfm_2d`, `extract_and_shield_tables` | MIGRATE | Mejor pieza; adaptar `(cont.)` configurable/off, header `th/thead`, límites celdas |
| `escape` consciente `$`, `convert_pre`, mark/kbd/del/hr/sub/sup, code-en-tabla | `UltraFaithful.*` | MIGRATE | Anti-corrupción LaTeX; regex `$` endurecer (monetarios, `\$`, code spans) |
| MathML→LaTeX + mapas | `parse_mathml_to_latex`, `OPERATOR_MAP/NAMED/GREEK` | MIGRATE | Probado; añadir `mmultiscripts/cases/pmatrix`, `munder lim`, unificar `phi/varphi` |
| Shielding math 9 fuentes + restauración | `extract_and_shield_math`, restore en `convert_html_to_markdown` | MIGRATE | Tokens evitan corrupción `markdownify`; añadir `\(..\)/\[..\]`, tokens UUID, provenance xpath |
| SVG→LaTeX, diagrams mermaid/plantuml, footnotes, dl/task/details, figures estándar, metadata + `read_html_file_safely`, `.html→.md+#anchor` exacto, `slugify+TOC` (fix unicode), pipeline 19 pasos como spec | ídem | MIGRATE (TOC/slug ADAPT) | Estándar y probado conceptualmente; TOC incluir `#`, colisiones, NFKD; metadata escapar YAML |
| OMML→LaTeX + mapa | `omml_to_latex`, `OMML_NS/MAP` | MIGRATE | Cobertura F3 (frac/sup/sub/rad/delim/matriz/nary/lim/accentos); añadir `cases/borderBox`, `defusedxml`, límite profundidad |
| `clean_latex_formula` (unificar 2 copias) | `chn:281` + `uc:934` | ADAPT | Elegir variante UC (balance simétrico); parametrizar `decimal_comma`, `frac_agresivo`; idempotencia testeada |
| PDF→MD, DOCX→MD, IPYNB→MD, XLSX/CSV→MD, `extract_raw_formulas`, `extract_formula_sheet`, `extract_problems`, Anki regex Q→A/término→def, glosario | `universal_converters.*` | ADAPT | Núcleos válidos; endurecer ZIP/bombas/límites/caps base64, corregir heading shift, parametrizar branding UPC, desacoplar import MathML |
| MD→HTML imprimible, `markdown_to_simple_html`, batch orquestación | `convert_markdown_to_printable_html`, `batch_convert_universal` | REIMPLEMENT | Parser ingenuo/XSS/CDN sin SRI; batch sin caché/cancel/errores/orden determinista; conservar idea + CSS print |
| Regex/extraction patterns, presets como matriz features | varios | REFERENCE | Reusar lógica, no código |
| Quiz `BANC/DATA/ITEMS`, `preprocess_course_components`, guías UPC, `UPCDegreeEngine`, 37 solvers, `GUM_TEMPLATES`, GUI Tk/`ctypes`, `Laboratorio_Virtual_Sensores.html`, `generate_q*.py`+datos, `build_master`, SPICE netlists (salvo F8), tests UPC/GUI/resolver | varios | DEFER/REJECT | NO-GOALS §24; patrones ya cubiertos o dominio F4/F8 |
| `problem_generator.py generate_*` | `tests/problem_generator.py` | DEFER/REJECT (GENERACIÓN) | Síntesis aleatoria viola fidelidad; solo `check_answer` rescatable fuera F3 |

## 6. Capacidades descubiertas fuera de especificación

`extract_figs_from_scripts` (JS data-URI), taxonomía 30 clases callout + `details`, matriz tabla + `(cont.)` + align por style, `escape` quirúrgico LaTeX, footnotes `role=doc-endnotes`, diagrams fence, `dl/task/details/nav`, fuzzy `resolve_local_stem` (score `overlap*2+5`, stopwords CA), doble vía Anki `genanki→SQLite` (`$$→\[ \]`), `read_html_file_safely` (BOM→meta→utf-8→cp1252), post-regex sup/sub + `$$` canónico + dedup `[!]/---`, `formula_sheet` con numeración oficial, `WM_DROPFILES` Win32, previewer propio, `GUM_TEMPLATES/score_exam/search spotlight`.

## 7. Dependencias (D3)

Reutilizar solo con auditoría: `bs4` (MIT), `lxml` (BSD-3, pinnar; chn usa `html.parser` — migrar a lxml opcional), `markdownify` (pinnar versión), `pypdf` (existente), `fitz/PyMuPDF` vetado AGPL → PDF vía `pypdf` nativo o adapter opcional aislado (no en dominio); `pandas/tabulate/openpyxl` solo en adapter XLSX (límites + tipos), `genanki` opcional (IDs parametrizados), `defusedxml` nuevo para OMML/XML, `mathml2latex` fallback opcional. Nada de Tk/`ctypes`/Flask/SQLAlchemy/PyWebView. Licencia MIT `©2026 Damaga2005`, headers provenance same-author.

## 8. Seguridad documental

Docs son DATOS: nunca ejecutar JS/macros/notebooks/C/VHDL/SPICE/shell. Amenazas: Zip Slip (verificar tamaños/nº archivos, rechazar absolutos/symlinks), Zip Bomb/descompresión (caps bytes/páginas/celdas/base64), traversal (`..`, NUL, `^[0-9a-f]{64}$` en CAS), XXE/entidades (defusedxml, sin red), SVG malicioso (solo `data-latex` textual, sin render), iframe (`youtube→link`, resto bloqueado, esquemas `http/https/#`/relativo, bloquear `javascript:/data:text-html/vbscript:`), XSS MD→HTML/Anki (allowlist + escape), DOM gigante/nesting (MAX_HTML_BYTES, MAX_TABLE_CELLS, MAX_B64), ReDoS (`\$(.*?)\$`, quiz regex con timeouts/límites), remote sin SRI (prohibido fetch remoto; `remote-not-fetched`), `exec/eval/pickle/subprocess` prohibidos (grep CI). Tests: malformed XML, Slip/Bomb, symlink, traversal, SVG, iframe, scripts, inputs gigantes.

## 9. D1

Parsers como adapters detrás de puertos (`ResourceExtractor`-style); dominio `documents/ast.py` stdlib-only intacto; bs4/lxml/openpyxl/pandas solo en adapter; sin Qt/Tk/Flask; sin discovery dinámico; sin FS en dominio (inyectar `put_bytes/blob_exists`); UI→application únicamente.

## 10. D2

Nuevos errores bajo `AcademicCoreError` `AC-*-NNN`: invalid input, unsupported format, malformed document, security rejection, extraction/normalization/asset/rendering/provenance failure. `UNSUPPORTED` o error apropiado (nunca contenido vacío silencioso); warnings `(doc,warnings)` nunca `ok` con warnings ocultos; `to_ui_error` único; `except:pass` solo fallback con warning.

## 11. D3

Ver §7. No incorporar dependencia porque Conversor la usa. Cada una: licencia, copyright, necesidad, seguridad, mantenimiento, tamaño, alternativa.

## 12. AST canónico

Reutilizar `ast.py` 19 kinds, `Metadata`, `history`, `validate`, `from_dict` estricto, `schema_version=1` (sin bump). NO crear `F3Document/AcademicDocument/DocumentNode`. Extensión compatible solo si auditoría prueba gap (p.ej. `callout` como `quote` tipado ya existe vía `blockquote [!TYPE]`; `Problem/Question/Solution/Answer/Parameter/Unit` como nodos o como capa extracción — decidir en F3.1 tras prototipo, sin duplicar). Añadir `Document.digest()` canónico (`sort_keys`, `ensure_ascii`, `allow_nan=False`, decimales string, excluye timestamps) siguiendo `execution/codec.py`.

## 13. Importers

`HTML` (existente + piezas MIGRATE), `PDF` adapter (texto pypdf + tablas/imágenes si F3 lo exige, OCR declarado UNSUPPORTED), `DOCX/OMML` adapter (nuevo, `omml→equation`), `IPYNB` adapter (nunca ejecutar; code→`code_block`, `text/latex→equation`, png→CAS), `XLSX/CSV` adapter (hoja→`table`, fórmulas Excel como datos salvo contrato explícito, sin macros). Interfaces `parse_* (bytes|Path, provenance) → (Document, warnings)`.

## 14. Extractors (extracción ≠ generación)

`Formula`: `shield→parse_mathml/omml→clean→dedup canónica→(formula,source,locator)`; `Problem`: `extract_problems_from_text` (`statement/parameters/units/questions/solution/boxed/provenance`, ES/CA/EN) con params normalizados `{var,value:float,unit_SI}` y dedup hash. `term→definition`, `question→answer` solo como extracción heurística con tests precisión. Generación (`problem_generator.py`, SRS, `QuestionGenerator`) explícitamente fuera.

## 15. Renderers

`AST→Markdown` y `AST→HTML` existentes; `AST→LaTeX` nuevo (ecuaciones, tablas, figuras, callouts, footnotes). PDF vía `AST→HTML/LaTeX→PDF`, nunca PDF como modelo interno.

## 16. Assets/F2

`F3 → Asset abstraction → F2 CAS → content-addressed reference`. Data-URI→`put_bytes` con MIME real, hash/dedup, caps; remotas `remote-not-fetched`; `word/media`, ipynb png, PDF images igual vía. Sin CAS paralelo.

## 17. Provenance

Toda extracción rastreable: `source document/format/hash/location/fragment`, `extractor+version`, `normalization version`; cuando aplique `PDF page/párrafo/DOM path/DOCX XML path/worksheet/cell/notebook cell`. Determinista; timestamps runtime fuera de digests. Registry shielding y `extract_raw` deben retornar `(valor, source, locator)`.

## 18. Determinismo

`same input+options+implementation → same AST+canonical+digest`. Controlar dict/set/FS order (`sorted(rglob)`), locale/timezone/timestamps/random/hash seed/path normalization. Tests `PYTHONHASHSEED=0/11/2024/random`. `attrs` insertion-order → canónico `sort_keys`; IDs Anki/tokens deterministas o parametrizados.

## 19. Observabilidad (E0.4)

Eventos reales solo: `document_loaded/node_parsed/formula_detected/formula_normalized/problem_detected/asset_extracted/asset_referenced/warning/rejection/rendered`. Sin inventar fórmulas/problemas/assets/locs/pasos/errores. Respetar budget/límites E0.4 (`TRACE_TRUNCATED` explícito para docs gigantes, batch con caché/cancel/progreso).

## 20. Tests F3 (propios AcademicCore)

Document (headings/paragraphs/lists/tables/figures/links/callouts/footnotes/code), Math (MathML/TeX/OMML/frac/powers/roots/matrices/limits/malformed), Problems (ES/CA/EN, params/units/questions/solutions/answers), Formats (HTML/PDF/DOCX/IPYNB/XLSX/CSV), Security (lista §8), Determinism (multiseed), Provenance (toda extracción con fuente válida). No copiar tests ciegamente; adaptar intención.

## 21. Golden corpus

Pequeño y representativo, derivado de capacidades reales: HTML simple/complejo, MathML, HTML+MathML, DOCX+OMML, PDF, IPYNB, XLSX, CSV, fórmula compleja, problema completo, tablas complejas, footnotes, callout, image/base64, malformed, malicious. Digests pineados + matriz `conversor_equiv` extendida.

## 22. Performance

Medir antes/después: HTML pequeño/grande, fórmula/problem extraction, PDF, DOCX, batch, rendering. Documentar regresiones. Caps Maxwell: `MAX_HTML_BYTES/TABLE_CELLS/B64_BYTES/PDF_BYTES=100MB` existentes + nuevos `validate_office_bytes`, budget eventos/páginas.

## 23. Riesgos

XSS sin allowlist sistemática; DoS sin límites; fuzzy FS no-determinista; `slugify` incompatible GitHub; `(cont.)` contamina datos; `var` 1-letra FP; `2,2→2{,}2` y `1/(..)` destructivos; `phi/varphi` invertido; doble `clean_latex` divergente; `pandas/fitz` version-dependientes; 90% pipeline chn sin tests; fricción AGPL (fitz) vs MIT.

## 24. Non-goals

Generación preguntas, SRS, asignaturas/profesores/evaluación/calendario, 37+ solvers, GUM/Virtual Lab, calculadoras/grado UPC, Anki como dominio, GUI Tk, PyInstaller, Flask/SQLAlchemy/PyWebView. Primitiva genérica suelta sí; funcionalidad completa no.

## 25. Plan implementación (orden sugerido desde auditoría)

1. `Document.digest()` + canónico + tests multiseed (sin bump schema).
2. Provenance fina (`source/locator`, registry con xpath) + D2 errores.
3. Hardening (`validate_office_bytes`, defusedxml, caps, allowlist XSS, `sorted` batch + caché/cancel).
4. OMML adapter + `omml_to_latex` MIGRATE + tests.
5. HTML importer mejoras (tablas, footnotes, diagrams, metadata, links exactos) MIGRATE.
6. `clean_latex` unificado + `extract_raw_formulas` ADAPT (sin XLSX-math).
7. `extract_problems` MIGRATE/ADAPT + normalización SI.
8. DOCX/IPYNB/XLSX-CSV adapters + Asset/F2.
9. Markdown renderer + LaTeX renderer + trace E0.4.
10. Golden corpus + equivalencia + performance + certificación.

---

## GATE (respuestas §42)

- **¿Qué se reutiliza?** Tabla §5 MIGRATE (tablas, escape, MathML, shielding, SVG/diagrams, footnotes, OMML, metadata/encoding, links exactos).
- **¿Qué se reescribe?** MD→HTML, batch (caché/cancel/errores), fuzzy→off, `clean_latex` unificado, sheets con orden documento.
- **¿Qué se rechaza?** UPC curricular, 37 solvers, guías UPC, GUI Tk/`ctypes`, lab HTML, contenido `generate_q*`, quiz dominio, GUM dominio, SPICE/VHDL/C ejecución.
- **¿Qué se difiere?** `problem_generator` (F4+), corpus `dist_course_md` como fixtures, Anki serialización plena, PDF tablas/imágenes avanzadas si no hay gap probado.
- **¿Qué capacidad nueva se descubrió?** §6 (15 ítems, evidencia en auditorías).
- **¿Qué ya existe?** §3+§8 de auditoría AcademicCore (§3 aquí); no duplicar.
- **¿Qué contrato se añade?** `parse_*(bytes|Path,prov)→(Document,warnings)`, `extract_formulas/problems→(items con provenance)`, `render_latex(doc)→str`, errores `AC-*-NNN`, `digest()`.
- **¿Determinismo?** Canónico + multiseed + `sorted` + IDs deterministas + goldens con digest.
- **¿Seguridad?** Threat model §8 + tests + `defusedxml`/caps/allowlist + CI `eval/exec/pickle/subprocess` grep.
- **¿Provenance?** Contrato §17 + tests (toda extracción con fuente válida).
- **¿E0.4?** Eventos §19, budget + `TRACE_TRUNCATED`, sin pasos inventados.

> DETENCIÓN F3.0: no implementar hasta coherencia interna verificada. F3.1 solo tras aprobar este diseño.
