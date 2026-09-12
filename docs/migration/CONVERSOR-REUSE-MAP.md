# CONVERSOR-REUSE-MAP — origin → destination → type → deps → tests → reason

License: MIT © 2026 Damaga2005 (same author; reuse permitted). Every adapted
module carries a `Provenance:` header (file, lines, license, author, date).
No Tk/markdownify/genanki code enters Academic Core. No architecture copied.

| Original (`conversor_html_notebooklm.py`) | Destino Academic Core | Tipo | Dependencias | Tests | Motivo |
|---|---|---|---|---|---|
| `OPERATOR_MAP` L41–91, `NAMED_MATH_FUNCS` L93–98 | `documents/conversor_math.py` (maps) | ADAPT | ninguna | `test_equations.py` (símbolos) | Datos curados de alta fidelidad |
| `parse_mathml_to_latex` L104–229 | `documents/conversor_math.py` | ADAPT | bs4 | equivalencia vs original (fixtures MathML) | Núcleo matemático; aislar de Tk |
| `clean_latex_formula` L265–314 (+`clean_wikipedia_latex`) | `documents/conversor_math.py` (`polish`, flag-gated) | ADAPT | re | source intacto + polish opcional | Reescritura opinada → derivada, nunca canónica |
| `html_formula_node_to_latex` L316–357 (+SUP/SUB/GREEK L231–254) | `documents/conversor_math.py` | ADAPT | bs4 | var/sub/sup/frac fixtures | Fórmulas HTML enriquecidas |
| `extract_and_shield_math` L373–613 (9 fuentes + lazy mathml2latex) | `documents/conversor_math.py` (`shield_math`) + `html_parser.py` | ADAPT | bs4, mathml2latex lazy | MathJax/KaTeX/MathML/SVG/img-alt/var | Estrategia shield-then-convert → Equation |
| `clean_soup_noise` L620–638 | `documents/conversor_sanitize.py` | ADAPT | bs4 | script/style/hidden/cookie eliminados | Sanitización estructural real |
| `extract_base64_images` L640–662 | `documents/conversor_images.py` | ADAPT | base64 | data-URI → CAS, ext detection | Destino CAS en vez de assets/ |
| `extract_figs_from_scripts` L359–371 | `documents/conversor_images.py` | ADAPT | bs4, re | FIGS dict → src | Sin ejecutar JS (regex sobre texto) |
| `extract_and_shield_diagrams` L664–684 | `html_parser.py` (mermaid/plantuml → CodeBlock) | ADAPT | bs4 | fences preservados | Semántica portable |
| `preprocess_callouts_*` L686–736 | `html_parser.py` (→ Quote) | ADAPT | bs4 | `[!NOTE]` multilingüe | Semántica portable |
| figures/captions, def-lists, task-lists, details/summary, footnotes, media L738–1138 | `html_parser.py` | ADAPT selectivo | bs4 | Image+caption, dl, task items | Solo semántica portable |
| navigation/course-components L738–1138 (parte) | — | DO_NOT_MIGRATE | — | — | Ruido específico del curso |
| `extract_metadata` L1139–1168 | `documents/conversor_metadata.py` | ADAPT | bs4 | og/meta/title/author/date | → Document Metadata |
| `is_code_table` L1175–1184 + `extract_code_from_table` L1186–1202 | `documents/conversor_tables.py` | ADAPT | bs4, re | Prism/gutter → CodeBlock+lang | Distinción código-vs-datos |
| `convert_html_table_to_gfm_2d` L1204–1293 | `documents/conversor_tables.py` (`table_grid`) | ADAPT | bs4 | rowspan/colspan/align fixtures | Motor 2D; salida a nodos Table |
| `read_html_file_safely` L1691–1718 | `documents/encoding.py` | REUSE_DIRECT | stdlib | BOM/meta/cp1252 vectors | Función pura |
| `rewrite_internal_links` L1002–1074 | `html_parser.py` (relative Link targets) | ADAPT | bs4 | — | Enlaces internos preservados |
| `UltraFaithfulMarkdownConverter` L1311+ | — | DO_NOT_MIGRATE (+REFERENCE idea shield) | markdownify (no añadida) | — | Renderers AST la sustituyen |
| `sanitize_html` Anki L2368, quiz/Anki/GUI/batch, tests ad-hoc | — | DO_NOT_MIGRATE | tk/genanki | — | Fuera de F3 / otras fases |
