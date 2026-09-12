# CONVERSOR-HTML-A-MD — F3 audit (read-only, HEAD `e5b8d60`)

Source: `conversor_html_notebooklm.py` (6.946 líneas) + `tests/` (12 scripts
ad-hoc, sin pytest) + `requirements.txt` + `LICENSE` (MIT, Damaga2005 —
misma autoría que Academic Core: reutilización permitida con atribución).
Working tree de la fuente verificado limpio; ningún commit realizado en ella.

## Inventario relevante para F3 (función → líneas → veredicto)

| Componente | Origen | Deps | Veredicto | Motivo |
|---|---|---|---|---|
| `OPERATOR_MAP` (~50 símbolos) + `NAMED_MATH_FUNCS` | L41–102 | ninguna | **ADAPT** | Mapa curado de alta fidelidad; copiar datos, no lógica Tk |
| `parse_mathml_to_latex` recursivo (mi/mn/mo/mfrac/msup/msub/msubsup/munder/mover/munderover/mfenced/menclose/mtable/mspace + `annotation` TeX prioritaria) | L104–229 | bs4 | **ADAPT** | Núcleo matemático; aislar de Tk, conservar ramas |
| `UNICODE_SUP/SUB_MAP`, `GREEK_MAP` | L231–254 | ninguna | **ADAPT** | Datos curados |
| `clean_wikipedia_latex`, `clean_latex_formula` (√, fracciones, derivadas, entidades, `%`, `2,2→2{,}2`, funciones, `_{\text{}}`, balanceo llaves) | L256–314 | re | **ADAPT** | Normalización valiosa pero OPINADA: portar con flag, conservar `source_latex` intacto (F1 formula policy) |
| `html_formula_node_to_latex` (span.f/var/sub/sup/ov/frac-values) | L316–357 | bs4 | **ADAPT** | Fórmulas HTML enriquecidas |
| `extract_and_shield_math` (9 fuentes: MathJax-script, KaTeX, MathML, .eq-containers, SVG-TeX, img-alt-LaTeX, ov-spans, frac-spans, var+sub/sup; fallback lazy `mathml2latex`) | L373–613 | bs4, mathml2latex(lazy) | **ADAPT** | Estrategia shield-then-convert; adaptar tokens a Equation AST |
| `clean_soup_noise` (comments, script/style/noscript, aria-hidden, display:none, cookies) | L620–638 | bs4 | **ADAPT** | Sanitización estructural real |
| `extract_base64_images` (data-URI → assets/, ext-smart) | L640–662 | base64 | **ADAPT** | Cambiar destino a CAS (inyectar put-callable) |
| `extract_figs_from_scripts` (FIGS/data-URI en JS → img[data-fig]) | L359–371 | bs4, re | **ADAPT** | Útil; sin ejecutar JS (solo regex sobre texto) |
| `extract_and_shield_diagrams` (mermaid/plantuml → fenced) | L664–684 | bs4 | **ADAPT** | → CodeBlock AST con language |
| `preprocess_callouts_and_admonitions` (→ `> [!NOTE]` multilingüe ca/es/en) | L686–736 | bs4 | **ADAPT** | → Quote AST |
| `preprocess_figures_and_captions`, `preprocess_definition_lists`, `preprocess_task_lists`, `preprocess_details_summary`, `preprocess_footnotes`, `preprocess_media_elements`, `preprocess_navigation_bars`, `preprocess_course_components` | L738–1138 | bs4 | **SELECTIVO**: figures/def-lists/task-lists/details/footnotes → **ADAPT**; navigation/course-components → **DO_NOT_MIGRATE** (ruido de curso, no semántica) | Solo semántica portable |
| `extract_metadata` (og:title/meta/title, author, date, description, canonical) | L1139–1168 | bs4 | **ADAPT** | → Document Metadata |
| `is_code_table` + `extract_code_from_table` (Prism/Rouge/gutter → fenced+lang) | L1175–1202 | bs4, re | **ADAPT** | Distinción código-vs-datos |
| `convert_html_table_to_gfm_2d` (matriz 2D, rowspan/colspan exactos, align, `<br>`, `\|`, celdas `(cont.)`) | L1204–1293 | bs4 | **ADAPT** | Motor de tablas; adaptar salida a nodos Table (spans preservados) |
| `extract_and_shield_tables` (tokenización previa) | L1295–1304 | — | **REFERENCE** | Idea útil; AST no necesita tokens |
| `read_html_file_safely` (BOM/meta/cp1252/utf-8-replace) | L1691–1718 | stdlib | **REUSE_DIRECT** | Función pura, sin cambios salvo tipos |
| `rewrite_internal_links` + `resolve_local_stem` | L1002–1074 | bs4 | **ADAPT** | → Link targets relativos |
| `UltraFaithfulMarkdownConverter.escape/convert_pre` (+ token-shield) | L1311–~1400 | markdownify | **DO_NOT_MIGRATE** | Pipeline markdownify sustituido por renderers AST; idea shield como REFERENCE |
| `sanitize_html` Anki (L2368, regex allow-list de tags de flashcard) | L2367–2368 | re | **DO_NOT_MIGRATE** | Alcance Anki, no sanitización general |
| Quiz/Anki/genanki-SQLite, GUI Tk (6 tabs), batch curso, tests ad-hoc | varios | tk, genanki | **DO_NOT_MIGRATE** | Fuera de F3 / otras fases |
| `to_mathjax` (L2586, anidada en modal examen) | modal Tk | — | **DO_NOT_MIGRATE** | Extraer solo si F9 lo pide |

## Dependencias del material reutilizable
Solo `beautifulsoup4` (+`lxml` como parser) y `mathml2latex` opcional-lazy.
`markdownify`, `genanki`, `tkinter`, `pyinstaller` NO entran en Academic Core.

## Riesgos detectados en el origen (no heredar)
- `clean_latex_formula` reescribe (derivadas, `2,2`, funciones): en Academic
  Core el `source` original se conserva siempre; la limpieza es derivada.
- `(cont.)` en celdas con rowspan: convención documentada, se preserva como
  `rowspan/colspan` estructurales en el AST en vez de texto.
- `mojibake` visible en el repo (`�`): F3 lee con la misma cascada de
  encodings y registra `encoding` en provenance.
