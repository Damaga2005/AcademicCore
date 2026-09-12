# Migration matrix (Phase 0 audit → Academic Core destination)

Status today: Academic Core is greenfield — everything is AUSENTE.
States: MIGRATE | REWRITE | ADAPT | REFERENCE | REJECT | INVESTIGATE.

## A. Conversor-HTML-A-MD → Academic Core

| Fuente | Funcionalidad | Destino | Estado | Acción |
|---|---|---|---|---|
| `UltraFaithfulMarkdownConverter` | Núcleo HTML→MD fiel | `engines/resource` + adapters | AUSENTE | MIGRATE — aislar 1 clase |
| `preprocess_*/sanitize/shields` | Limpieza DOM | adapters html | AUSENTE | MIGRATE |
| `parse_mathml_to_latex/to_mathjax` | MathML→LaTeX | document AST equations | AUSENTE | MIGRATE (+ declarar `markdownify` faltante) |
| `convert_html_table_to_gfm_2d` | Tablas→GFM | document AST tables | AUSENTE | MIGRATE |
| `extract_base64_images` + SHA dedup | Imágenes→assets/CAS | storage CAS | AUSENTE | MIGRATE |
| `process_all_course_temas/course_worker` | Batch 10 temas | ResourceEngine pipeline | AUSENTE | ADAPT — desacoplar Tk/threading |
| Visor Tk + highlight/zoom | Visor desktop | — | AUSENTE | REJECT (Qt lo sustituye; `search_course_content` como REFERENCE) |
| `export_viewer_to_html_pdf` | Export HTML/PDF | pdf engine | AUSENTE | ADAPT |
| `generate_printable_exam_pdf` | Cuadernillo A4 UPC | pdf engine | AUSENTE | MIGRATE |
| Flashcards/Anki (`genanki` + fallback sqlite) | `.apkg/.tsv` 550 tarjetas | study/flashcards | AUSENTE | MIGRATE |
| `open_exam_simulator_modal/score_exam` + `problem_generator.py` | Examen + baremo + generador | exam engine | AUSENTE | REWRITE — separar motor de modal Tk |
| `dist_course_md/*.md` | Contenidos SdM | `content/corpus` (datos) | AUSENTE | REFERENCE — curar, no migrar código |
| `setup_gum_calculator_tab` + 6 plantillas | Calculadora GUM | measurement engine | AUSENTE | MIGRATE |
| `run_monte_carlo_gum` | Monte Carlo Supl.1 | measurement engine | AUSENTE | MIGRATE |
| `setup_filters_tab/draw_bode_plot` | Sallen-Key + Bode | circuits/filters + Qt Bode | AUSENTE | REWRITE (math sí, Canvas no) |
| Pt100 CVD/NTC/CJC/Wheatstone+INA | Sensores | circuits/sensors | AUSENTE | MIGRATE |
| `setup_rlc_presets_tab` + 13 presets | Banco RLC | circuits/rlc | AUSENTE | ADAPT |
| Netlists `.cir` | Export SPICE | engineering backends | AUSENTE | REFERENCE — validar vs ngspice |
| Lab HTML MNA Thévenin/Norton | Solver 7 nodos | simulation engine | AUSENTE | REWRITE con tests |
| Lab 16 módulos WebGL/CAD + Keysight/Rigol/Tektronix + FFT | Lab virtual | virtual-lab | AUSENTE | ADAPT como artefacto versionado |
| Carta Smith + GREELEC PEE/CAF/SC | RF/potencia | — | AUSENTE | INVESTIGATE — fuera alcance SdM |
| GUI Tk + DnD ctypes + `.spec` | App desktop | Qt (`app.py` done) | PARCIAL | REJECT Tk; `.spec` como REFERENCE |
| `tests/*.py` ad-hoc (12, sin framework) | QA | `tests/` pytest | PARCIAL | REWRITE — checks CI |
| `.apkg` + PNG en git | Artefactos | CI artifacts/LFS | AUSENTE | REJECT versionarlos |

Riesgos: `markdownify` no declarado (instalación fresca rota); monolito
Tk-acoplado; FFT/MNA solo en JS sin tests; binarios en git + mojibake;
drift README v8.0 vs HTML v7.0.

## B. Gestion-Academica → Academic Core (28 filas, verbo completo en informe de auditoría)

MIGRATE/ADAPT: años/cuatrimestres (generalizar, no hardcodear 4/8), asignaturas
+ validación siglas + catálogo optativas, profesores, componentes/esquemas/
bloques/nota-final (grading), subida docs (reutilizar `utils.py` magic-bytes),
categorías+grupos (deprecar `Apartado` legacy), visor pdf.js (vendorizar o
sustituir), marcadores, anotaciones, indexado+buscador Ctrl+K (NFKD +
`pagina_texto`), recursos externos (scrapers a `adapters/`), tareas, horarios
(expandir fechas como lib pura), conflictos, ICS, timeline Gantt, repaso
espaciado, hitos, espacios-estudio + modo-examen, racha (desacoplar winotify),
notas globales vs por asignatura, notificaciones, dashboard (quitar links UPC),
backup (límites `BACKUP_MAX_*`), auth lock (endurecer: hoy sin Flask-Login y
`SECRET_KEY` efímera), guías docentes (aislar en `adapters/upc`, descartable).

Riesgos: dominio GREELEC/UPC hardcodeado; 672 docs + DB 27 MB fuera de git;
DB local en migración vieja; SQLite monousuario + 200 MB upload; scrapers
frágiles; pdf.js vendorizado pesado; winotify/pywebview solo-Windows.

## C. Sistemes-de-Mesura → Academic Core (NO migrar aún; contrato para Fase 12)

Portar (Fase 12): corpus 91 ficheros con hashes, esquema KB 10 tablas,
registro 2896 fórmulas + gate `coverage==1.0`, 377 conceptos, chunks/tablas/
visuals con `source_hash+section+doc`, FTS5 BM25 + TF-IDF stdlib + RRF,
`FormulaRetriever`, abstención + EvidencePack, banco V/F 500, examiner
verificado, exam grading Decimal, correction por rúbrica, calculator AST +
`formula_check`, adaptive/mastery event-sourcing + spacing, `LLMProvider`/
`EmbeddingProvider`, contrato API ~35 rutas (reimplementar, no copiar UI),
tests 1092 + `check` sha256 + CI.
Curar antes: variables 7.08%, **units 0%**, conditions 0%, 34 fórmulas
bloqueadas en examiner (`coverage=0.9883`), ruido/mojibake, gold desactualizado.
Dependencias runtime: ninguna (stdlib); `GEMINI_API_KEY` opcional con fallback
extractivo. Sin Ollama/vector-DB hoy — Ollama llega en Fase 10.
