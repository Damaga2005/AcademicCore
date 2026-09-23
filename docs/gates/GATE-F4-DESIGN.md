# GATE-F4-DESIGN — F4.0 Auditoría forense completa

> Fase F4.0: SOLO auditoría + diseño. No implementé código, tests ni configuración.
> Único archivo creado/alterado: este gate.
> Baselines: AcademicCore `34629a5` (local, +7 sobre `origin/main 3642ca5`); Gestion-Academica `187a614` (`master`).

---

## 1. Executive Summary

AcademicCore está certificado en F0–F3.1, F8/F8-Q, F15, E0–E0.4 y F9-A..D (gates existen; ROADMAP aún marca F9 en planificación). Sus fortalezas: dominio puro, CAS/integridad, AST documental canónico, errores D2, trace E0.4, golden corpus.

Gestion-Academica (`Flask + Flask-SQLAlchemy + SQLite + PyWebView`, master `187a614`) es un sistema de gestión maduro: 54 asignaturas, ~7400 páginas indexadas, 61 profesores, 65 esquemas de evaluación, documentos anotables, horarios/tareas/espacios de estudio, autenticación + CSRF + backups. Su debilidad arquitectónica: **dominio acoplado a `db.Model` y lógica de negocio repartida entre `models.py` y `routes/*`**, sin puertos, sin casos de uso, DTOs ni dominio testeable sin Flask.

F4.0 concluye: **el modelo académico canónico ya existe en AcademicCore** (`domain/academic.py`, `grading.py`, `schedule.py`, `conflicts.py`, `results.py`, `identity.py`); lo que falta es la **capa de gestión operativa y de conocimiento** (ciclos, documentos-linked, evaluación, SRS, progreso). F4 debe **adaptar/extraer** de Gestion-Academica, nunca copiar su ActiveRecord.

---

## 2. Baseline exacto

| Repositorio | Path físico | Rama | HEAD | Estado |
|---|---|---|---|---|
| AcademicCore | `C:\Users\dmart\Documents\AcademicCore` | `main` | `34629a5a5f27da4dae7cfabcca8cd22c0a7c70dc` | limpio, ahead 7 |
| Gestion-Academica | `C:\Users\dmart\AppData\Local\Temp\opencode\Gestion-Academica` (clon) | `master` | `187a614cd0ad14f10103f675246750c02beec7ba` | limpio |
| Conversor (solo referencia) | `...\Temp\opencode\Conversor-HTML-A-MD` | — | `bad31042` | inalterado |

## 3. Estado Git

```
$ git status --short          → (vacío)
$ git branch --show-current   → main
$ git log --oneline -15       → 34629a5 test(f3): certify f3-ext
                              82c07c8 test(f3): add golden corpus
                              1dbabb3 feat(f3): deepen HTML importer and add latex renderer
                              8ec0163 feat(f3): add document format adapters
                              c866db2 feat(f3): unify formula normalization and add problem extraction
                              475f735 feat(f3): harden office/xml import boundaries and adapt OMML extraction
                              66f578c feat(f3): add canonical document digest
                              3642ca5 (origin/main) cert: certify E0.4 …
$ git rev-parse HEAD          → 34629a5…
$ git rev-parse origin/main   → 3642ca5…
$ git diff / --cached         → vacío
```

---

## 4. AcademicCore inventory (282 `.py` en `src/`, 116 tests, 146 `.md` en docs)

| Paquete | Responsabilidad | Fases | Gate | Tests | Riesgos/deuda |
|---|---|---|---|---|---|
| `academic_core/{app,errors,logging_config}.py` | Fachada, taxonomía D2, logging estructurado | D2 | GATE-D2 | test_architecture, test_config | códigos AC-* descentralizados (§14) |
| `domain/` raíz | `entities`, `academic` (7 niveles), `identity` (16 kinds, `IdAllocator`), `grading` (Decimal HALF_UP), `schedule`, `conflicts`, `results` (gradebook genérico), `status`, `ports`, `resources` (Resource/Version/Provenance), `authoring` (7+undo) | F1, F4, F5 | GATE-F1/F4/F5 | test_identity, test_ids, test_domain, test_grading, test_schedule, test_results, test_provenance | `domain/authoring.py:13` importa `documents.ast` (domain→documents) |
| `domain/assessment/` | scoring Decimal, máquina de estados sesión | F9-B | GATE-F9A | test_f9b_domain_assessment | `except: pass` en `application/assessment.py:332` |
| `domain/engineering/` | MNA (B–M), AC/D1–D8, small-signal, thevenin, math exacta, structural, digital, lab, metrology, control, DSP, RF, comms, satcom, symbolic | F6–F8, F8-Q, F8-N/O/P1..P5 | múltiples | ~90 test files | ninguno estructural (puro, sin float en física) |
| `domain/execution/` | `execution-trace/1`, equation/newton/analog/control/symbolic/engineering_deep, replay | E0–E0.4 | GATE-E0* | test_e0*, test_e01r_* | ninguno (límites/digest verificados) |
| `documents/` | F3 base + F3.1 (15 módulos nuevos: `limits`, `latex_norm`, `omml`, `office_security`, `formulas`, `problems`, `terms`, `render_latex`, `toc`, `links`, `batch`, `docx_adapter`, `ipynb_adapter`, `tabular_adapter`, `trace`) | F3, F3.1 | GATE-F3, GATE-F3-DESIGN, GATE-F3-CERTIFICATION | test_ast/documents/html_docs/markdown_roundtrip/conversor_equiv/compat_f3/pdf, test_f3_ext (40), test_f3_golden | sin `defusedxml` (ET con guardas DOCTYPE/ENTITY), `documents/security.py` sin SPDX |
| `application/` | `facade`, `services`, `academic_io`, `ingest`, `documents`, `authoring`, `engineering`, `simulation_service`, `lab_service`, `exercise_service`, `digital_service`, `assessment`, `explain_service/render`, `queries`, `search`, `backup`, `security` | F5, F9, E0.1 | GATE-F5/F15 | test_application, test_authoring*, test_f9c_* | `except Exception` (contexto, no silencioso) |
| `infrastructure/` | `database` (SQLite WAL/FK/busy_timeout + 11 migraciones), `cas`, `resources`, `repositories`, `authoring`, `engineering`, `assessment`, `ngspice`+parser, `migrations/*.sql` | F0–F2, F7, F9-D | GATE-F2 | test_persistence, test_cas, test_ingest, test_reproducibility | ninguno bloqueante |
| `storage/`, `resources/`, `engines/`, `pdf/` | store CAS, adapters (file/md/html/pdf; ZIP rechazado), PDFEngine pypdf + Stirling v2.14.3, AI providers | F0, F2, F3, F5 | GATE-F0/F2/F3 | test_pdf, test_stirling, test_resource_security | Stirling `REVIEW REQUIRED` (Apache-2.0 vs MIT-open-core) |
| `ui/` | `main_window`, `dashboard`, `exercises`, `simulation`, `virtual_lab`, `logic_analyzer`, `waveform`, `engineering`, `authoring`, `dialogs`, `state`, `workers`, `errors` | F15 | GATE-F15 | test_f15_*, test_ui* | UI→domain directo (deuda AI-001/AI-002, re-enrutado en F15) |

Tests: 116 ficheros. Fixtures: `tests/fixtures/{digital_trace,execution_trace,logic_analyzer}`. Config: `pyproject.toml` (deps PySide6, extras dev/pdf/html/anki, pytest markers), `requirements.txt`, `requirements-lock.txt`, `requirements-dev.txt`, `sbom.json` (CycloneDX 1.5), `THIRD_PARTY_NOTICES.md`. `scripts/` y CI (`.github/`) **no existen**. `LICENSE` MIT.

Docs: 82 gates, 16 ADR, `roadmap/ROADMAP.md`, `specs/ERROR-CODES.md`, `security/THREATS.md`, `testing/STRATEGY.md`, `domain/{MODEL,ID-POLICY,PERSISTENCE,RELATIONS}.md`, `architecture/{MODULES,OVERVIEW,NGSPICE-WINDOWS,STIRLING-INTEGRATION}.md`, `migration/{MATRIX, MIGRATION-REPORT-F1, CONVERSOR-{F3-AUDIT,REUSE-MAP}, GESTION-ACADEMICA-F4-{AUDIT,REUSE-MAP}, CONFLICTS.md, ENGINEERING-*}`, `phase-reports/F2–F7B8`.

## 5. AcademicCore architecture

```text
UI (PySide6)  →  Application (services/facade)  →  Domain + Ports (stdlib puro)  →  Infrastructure/Adapters (SQLite, CAS, ngspice, PDF)
```

- `tests/test_architecture.py:21–104`: `test_domain_is_pure` (domain sin PySide6/sqlalchemy/application/infrastructure/app), `test_application_and_infrastructure_have_no_ui`, `test_ui_consumes_only_application_and_domain`, `test_domain_knows_no_backends` (AST: sin os/pathlib/sqlite3/urllib/socket/PySide6/ftplib/http), `test_ast_is_stdlib_only`.
- `GATE-D1-DESIGN.md` (§9, §12, D1-008) endurece: UI→application only; AI-001/AI-002 registran el desvío actual de `ui/simulation.py:73,88,103,118` y `ui/virtual_lab.py:142,143,156,212,228,268` (UI→domain) como deuda a corregir en F15.
- Sin imports dinámicos: único `importlib` real = `infrastructure/database.py:15` (`from importlib import resources`).
- `subprocess` solo en `infrastructure/ngspice.py:15,216,240,341–343` y `pdf/stirling.py:13,109–111` (ambos `shell=False`, timeouts, allow-list de binarios).
- DSP/RF/comms/satcom con tests de dirección N-110 (`test_architecture.py:134–389`).

## 6. AcademicCore certification status

| Fase | Estado | Evidencia |
|---|---|---|
| F0, F1, F2, F3 | CERTIFICADO | GATE-F0 (MATRIX), F1, F2, F3 |
| F3.1 (F3-ext) | CERTIFICADO (local, no pusheado) | GATE-F3-DESIGN + GATE-F3-CERTIFICATION; commits `66f578c..34629a5` |
| F4 | CERTIFICADO | GATE-F4.md, F4-REPORT |
| F5, F6 | CERTIFICADO | GATE-F5, F6 |
| F7-A..F7-B8 | CERTIFICADO | GATE-F7A..B8 |
| F8-A..F8-P5 | CERTIFICADO | GATE-F8A..P5 (37+ gates) |
| F8-Q (.1–.7) | CERTIFICADO | GATE-F8Q-*, incl. GATE-F8Q-FINAL |
| D1 | DISEÑO APROBADO (2e8017f) | GATE-D1-DESIGN.md; test suite como gate vivo |
| D2 | CERTIFICADO (5670ffd, b94c6a9) | GATE-D2-DESIGN.md |
| D3 | CERTIFICADO (91343ba, 6bdb0a9) | GATE-D3-DESIGN.md, LICENSE, SBOM, NOTICE |
| F15 | CERTIFICADO (c88dd9f, c1dea25, d23ca7f) | GATE-F15.md |
| E0, E0.1, E0.1-R+, E0.2, E0.3, E0.4 | CERTIFICADO | GATE-E0*, commits 7fc04b7..3642ca5 |
| F9-A..F9-D | IMPLEMENTADO + gates (43a67a7) | GATE-F9A/C/D; ROADMAP.md aún «EN PLANIFICACIÓN» (desfase doc) |
| F9-E/F, F10–F14, F16 | EN PLANIFICACIÓN | solo ROADMAP.md, sin código |

## 7. AcademicCore file-level findings (resumen con evidencia)

| Hallazgo | Evidencia | Acción F4 |
|---|---|---|
| `except: pass` catalogados | `application/assessment.py:332–334`, `documents/conversor_math.py:255–256,261–262`, `documents/encoding.py:25–26`, `infrastructure/assessment.py:147–148,153–154`, `infrastructure/ngspice.py:156–157,205–206,364–365`, `infrastructure/ngspice_parser.py:101,282,368,463,492,592,632,726,751,768`, `pdf/stirling.py:84,95,112,197` | cat. + warning/trace, no F4-imp |
| Códigos AC-* sintéticos sin clase | `errors.py:122` (AC-SER-002), `:139` (AC-SEC-001), `:142` (AC-APP-001), `domain/engineering/digital/core.py:49` (AC-DOM-001) | registro central + test unicidad (ADR cand.) |
| `documents/security.py` sin SPDX | archivo 1–9 | añadir header (commit trivial, fuera de F4.0) |
| Stirling license sin resolver | `pdf/stirling.py` (Apache-2.0 vs MIT-open-core) | D3 REQUIRES VERIFICATION |
| `domain/authoring.py:13` importa `documents.ast` | domain→documents (fuera de lista prohibida de test) | F4: mantener o extraer contrato `DocumentRef` |
| Packaging version desfasado | `pyproject.toml:10` version 0.1.0 vs CHANGELOG 0.18.0 | ADR/versioning (no F4) |
| tests usan `__import__` en runtime de test | `tests/test_conversor_equiv.py:75` | higiene (no F4) |
| `lxml` wheels embeben libxml2 (versión ?) | D3 | REQUIRES VERIFICATION |
| No CI / no `scripts/` | `.github/` ausente | LATER_PHASE (D4/D5) |

## 8. Gestion-Academica inventory (~110 `.py`, 20 HTML, 26 JS, 17 CSS, 33 tests, 23 migraciones)

Raíz: `app.py` (factory + 32 blueprints + auto-migrate/seed), `models.py` (1616 L, 20+ entidades ActiveRecord), `config.py` (65 L, `SECRET_KEY` efímera, `MAX_CONTENT_LENGTH 200MB`, cookie flags), `utils.py` (144 L, `ruta_absoluta` anti-traversal, magic-bytes exe), `seed.py` (314 L, GREELEC 4 años/8 cuatrimestres), `changelog.py`, `guia_docente.py` (350 L, heurística PDF→profesorado/esquemas, sin escritura directa), `import_apuntes.py` (340 L, OneDrive→app, dry-run/apply), `informe_siglas.py`, `cargar_guias_docentes.py` (320 L, 15 asigs), `cargar_guias_docentes_2.py` (546 L, 38 asigs), `cargar_studocu.py` (102 L, 31 URLs), `cargar_wuolah.py` (132 L, ~50 slugs), `fix_ciaf.py` (78 L, mover docs), `limpiar_zips_codigo.py` (36 L), `reorganizar_apr_ped.py` (221 L, zip proyectos), `generar_icono.py` (Pillow), `escritorio.py` (253 L, PyWebView + backup diario + winotify), `escritorio.spec` (PyInstaller), `build.ps1`, `requirements.txt`/`requirements-dev.txt` (Flask≥3, Flask-SQLAlchemy≥3.1, Flask-Migrate≥4, python-dotenv, pywebview≥6, pythonnet, pypdf≥5, winotify; sin pins), `.env.example` (GREELEC_LOCK_KEY, FLASK_SECRET_KEY, HOST/PORT/DEBUG), `README.md`, `FUNCIONALIDADES.md` (54 asigs, 61 prof, 65 esquemas/168 comp, 676 docs/185 grupos/~7400 págs, 81 ext, 9 clases/15 tareas/7 espacios), `design-system-preview.html`, `layout-preview.html`, `icono_preview.png`, `icono.ico`.

## 9. Gestion-Academica file-by-file audit (resumen exhaustivo por carpeta)

| Ruta | Tipo/Len | Responsabilidad y clases/funciones | Persistencia/UI/Negocio | Seguridad | Estado |
|---|---|---|---|---|---|
| `app.py` ~153 L | Python/Flask | factory `create_app`, 32 blueprints, auto-migrate/seed, `/`, `/api`; `migrate`, `_bootstrap_datos_iniciales_si_vacio` | orquesta SQLite + SSR | sin eval/exec/pickle/subprocess; env host/port/debug | CORE/INFRA |
| `models.py` ~1616 L | Python/SQLAlchemy | dominio+ORM: `Anio,Cuatrimestre,Asignatura,resolver_asignatura,ComponenteEvaluacion,BloqueEvaluacion,EsquemaEvaluacion,esquemas_con_ganador,calcular_resultado_componentes,calcular_estado_notas,Apartado,GrupoDocumento,Documento,Marcador,AnotacionPdf,TareaEvento,EspacioEstudio,EspacioEstudioDocumento,ObjetivoEspacio,HorarioClase,fechas_sesiones_horario,intervalos_solapan,fecha_es_sesion_de_horario,ConfiguracionApp,Hito,Concepto,PaginaTexto,AvisoDescartado,DiaActividad,SesionEstudio,registrar_actividad*,calcular_racha*,RecursoExterno,Profesor,BusquedaFavorito/Reciente,NotaRapida` | `db.Model` directo, FK/cascade, `@validates` (email/URL/siglas), `to_dict()`  | mixed domain+data | REUSE de cálculos; REIMPLEMENT de persistencia |
| `config.py` 65 L | CONFIG | `RESOURCE_DIR/DATA_DIR` (frozen `sys._MEIPASS`), `MIGRATIONS_DIR`, `load_dotenv`, `Config` (`SQLALCHEMY_DATABASE_URI=sqlite:///DATA_DIR/academico.db`, `MAX_CONTENT_LENGTH 200MB`, `SECRET_KEY`, `SESSION_COOKIE_*`, `BACKUP_*`, `DOCUMENTO_*`) | FS+SQLite | SECRET_KEY efímera; cookie secure desactivado (HTTP-LAN) | ADAPT |
| `utils.py` 144 L | APP/ADAPTER | `slugify,carpeta_*,ruta_absoluta,validar_archivo_subido,validar_cantidad,nombre_archivo_disponible,crear_apartados_por_defecto,borrar_carpeta_asignatura` | `ruta_absoluta()` realpath+prefijo, `secure_filename`, allowlist ext, `MAX_BYTES`, magic bytes MZ/ELF/Mach-O | FS `DOCUMENTOS_DIR/{id_slug}/{categoria}/{id_grupo}` | ADAPT (patrón de upload) |
| `seed.py` 314 L | SCRIPT/DATA | GREELEC 4 años/8 cuatrimestres, get-or-create idempotente, `--reset` destructivo | `obtener_o_crear_anio/cuatrimestre,crear_asignatura,obligatorias,catalogo_optativas,poblar_datos_iniciales,seed` | escribe BD+FS | ADAPT (idempotencia), REJECT (`--reset drop_all`) |
| `guia_docente.py` 350 L | DOMAIN/APP | heurística PDF→`{profesores,esquemas}` con `pendiente_revision` | `extraer_texto,analizar_profesorado,analizar_evaluacion,analizar_guia_docente,_resolver_formula,_parsear_terminos,_componentes_planos` | solo lectura PDF, sin red | REUSE/ADAPT al pipeline de importers de F3 |
| `import_apuntes.py` 340 L | SCRIPT/ADAPTER | OneDrive→app con `--dry-run/--apply --only-zips` | `clasificar_categoria,construir_items,imprimir_informe,ejecutar_importacion,main` | FS+BD, `secure_filename`, `hash()` tmp | OUT_OF_SCOPE (rutas OneDrive), REFERENCE |
| `informe_siglas.py` 44 L | SCRIPT | lista asignaturas sin siglas | `informe_siglas_faltantes` | read-only | OUT_OF_SCOPE |
| `cargar_guias_docentes.py/_2.py` 320+546 L | DATA/SCRIPT | 15+38 asigs, `DATOS{}` → `Profesor/Esquema/Componente` (borra-recrea) | `ejecutar,main` | escritura destructiva sin backup | DATA/seed → OUT_OF_SCOPE (contenido GREELEC) |
| `cargar_studocu.py` 102 L | SCRIPT/ADAPTER | `CONFIRMADOS{id:url}` 31 → `RecursoExterno(nombre=Studocu)` | `ejecutar,main` | upsert | DATA → OUT_OF_SCOPE (contenido) |
| `cargar_wuolah.py` 132 L | SCRIPT/ADAPTER | ~50 slugs → URLs Wuolah | `ejecutar,main` | upsert | DATA → OUT_OF_SCOPE |
| `fix_ciaf.py` 78 L | SCRIPT | mover Parcial CIAF (asig 27→34) + limpiar grupo | `ejecutar` | FS+BD, `shutil.move/rmtree(ignore_errors)` | OUT_OF_SCOPE |
| `limpiar_zips_codigo.py` 36 L | SCRIPT | borrar `Codigo_*.zip` | `limpiar` | FS+BD | OUT_OF_SCOPE |
| `reorganizar_apr_ped.py` 221 L | SCRIPT | zipear proyectos APR/PRD, mover grupos | `zipear_proyecto,ejecutar,mover_grupo_a_otros,borrar_grupo_y_documentos` | reescritura masiva sin snapshot | OUT_OF_SCOPE |
| `generar_icono.py` 75 L | GENERATOR/BUILD | `dibujar_icono` 1024px multi-res | `dibujar_icono,main` | Pillow | KEEP_SEPARATE (icono) |
| `escritorio.py` 253 L | ADAPTER/BUILD | PyWebView 1280x850 `/vista/dashboard`, backup diario 10, toasts winotify | `_filtrar_menu_contextual,_habilitar_copiar_y_atajos,_avisar_notificaciones_urgentes,_avisar_racha_record,_backup_automatico,_iniciar_servidor,_esperar_servidor,main` | Flask daemon + WebView2 | ADAPT (solo launcher) |
| `escritorio.spec`/`build.ps1` | BUILD | PyInstaller bundle | — | console=False oculta tracebacks | LATER_PHASE (D4) |
| `requirements*.txt`, `.env.example` | CONFIG | deps sin pins; plantilla env | — | — | REIMPLEMENT (pins) |
| `README.md`/`FUNCIONALIDADES.md` | DOC | arquitectura mermaid, spec funcional 20 secciones | — | `LICENSE` referenciado pero ausente | REUSE (spec), ADAPT (licencia) |
| `design-system-preview.html`, `layout-preview.html`, `icono*.png/ico` | ASSET | previews, icono | — | — | KEEP_SEPARATE |
| `routes/anios.py,cuatrimestres.py` | APPLICATION/PORT | CRUD puro | `listar,obtener,crear,actualizar,borrar_*` | db directo | REIMPLEMENT (casos de uso) |
| `routes/asignaturas.py` 17 KB | APPLICATION | `listar,media_curso,media_por_cuatrimestre,objetivo_media,obtener/crear/actualizar/cambiar_estado/borrar,catalogo/elegir/quitar_optativa` + `_verificar_siglas,cambiar_estado_asignatura,_set_prerrequisitos,_media_ponderada` | db directo + `borrar_carpeta_asignatura` | — | REUSE cálculos, REIMPLEMENT orchestration |
| `routes/componentes.py`,`bloques.py`,`esquemas.py` | APPLICATION | CRUD componentes/bloques/esquemas + duplicar | `crear_componente_en_bloque,mover_bloque,duplicar` | db directo | REUSE (modelo), REIMPLEMENT (servicio) |
| `routes/apartados.py`,`grupos_documento.py` | APPLICATION | CRUD legacy + categorías/subgrupos + mover/borrar FS | `mover,crear,actualizar` | db+FS | ADAPT (F2 CAS) |
| `routes/documentos.py` 11.7 KB | APPLICATION | `listar,subir,obtener,servir,archivo,actualizar,renombrar,etiquetas,listar_por_asig,recientes,progreso,quitar-continuar,borrar` + `_indexar_texto_pdf,_renombrar,_borrar_fisico,_mover_fisico` | upload transaccional (rollback+limpia), `pypdf` índice, progreso/racha | allowlist + rollback | ADAPT (→F3 + F2) |
| `routes/marcadores.py`,`anotaciones.py` | APPLICATION | marcador PDF + rects JSON 0..1 (6 colores) | `CRUD`,`_normalizar_rects,_validar_color` | db | REUSE (PDF annotations), DEFER si F3 PDF no soporta |
| `routes/tareas.py` 9.7 KB | APPLICATION | `listar,obtener,crear,actualizar,posponer,borrar,calendario_mensual` + `_parse_fecha/hora/bool,_resolver_asig/doc,_autocrear_espacio` | repetición semanal ×52 | parseo validado | REUSE (domain.schedule), REIMPLEMENT (service) |
| `routes/espacios_estudio.py` 7.7 KB | APPLICATION | CRUD espacio+refs+objetivos, leído/destacado, progreso/días | `CRUD` | db | REUSE (concepts SRS) |
| `routes/horarios.py` 7.4 KB | APPLICATION | CRUD serie recurrente + expansión | `fechas_sesiones_horario` | db | REUSE (`domain.schedule`) |
| `routes/ics.py`/`importar_ics.py` | ADAPTER | export/import ICS, heurística nombre curso→asignatura, dedup título+fecha, hora peninsular | `export,import,preview` | db+ICS | REIMPLEMENT (adapter) + REUSE (schedule) |
| `routes/conflictos.py` | DOMAIN/APP | `detectar_conflictos(fecha,hora_ini/fin,excluir*)` + `comprobar` | `intervalos_solapan,fecha_es_sesion_de_horario` | db | REUSE (`domain.conflicts`) |
| `routes/linea_tiempo.py` | UI/APP | Gantt cuatrimestre | `linea_tiempo` | db queries | REUSE (queries) |
| `routes/estudio.py`/`racha.py` | APPLICATION | temporizador `SesionEstudio(1..600 min)`, resumen, racha | `registrar_actividad,calcular_racha` | db | REUSE (F4 mastery) |
| `routes/conceptos.py` | APPLICATION | CRUD + `subir/bajar/repaso_hoy` SRS 0/3/18 días | `reclasificar` | db | REUSE (SRS, F4) |
| `routes/hitos.py` | APPLICATION | CRUD hitos | `CRUD` | db | REUSE (goals) |
| `routes/notificaciones.py` 6.7 KB | APPLICATION | `calcular_notificaciones,obtener,descartar` + `_ultima_actividad,_autocompletar_examenes_pasados` | atrasadas/inminentes/abandonadas, niveles rojo | db | REUSE (LATER_PHASE) |
| `routes/notas_rapidas.py` | APPLICATION | CRUD bloc global | `CRUD` | db | REUSE (notes) |
| `routes/busqueda.py` 9.8 KB | APPLICATION | `buscar,favoritos,recientes` + `_contiene/_pagina_coincide/_fragmento` | NFKD, fragmentos ±60ch | db | REUSE (FTS `storage/store.py`) |
| `routes/configuracion.py` | APPLICATION | get/put `ConfiguracionApp` (tema/avisos/widgets) | `obtener_configuracion` | db | REUSE (settings) |
| `routes/backup.py` 14 KB | INFRASTRUCTURE | `listar,descargar_automaticos,exportar,importar,exportar_expediente_csv` + `_ruta_db,_volcar/construir/escribir_zip,_validar_zip_seguro,_validar_sqlite` | ZIP-slip/bomb (5GB, 200k, ratio 100, 2GB/miembro) + SQLite validation | db+FS | REUSE (backup) / ADAPT (f2) |
| `routes/cambio_externo.py` | INFRASTRUCTURE | huella BD + `registrar_deteccion_cambio_externo(after_request)` | mtime+tamaño/counts | db | LATER_PHASE (sync) |
| `routes/recursos_externos.py`,`profesores.py` | APPLICATION | CRUD recursos (Wuolah/Studocu) y profesores | `CRUD` | db | REUSE (resources) |
| `routes/guia_docente.py` 6.3 KB | APPLICATION/UI | `POST /documentos/<id>/analizar-guia-docente` + `POST /asignaturas/<id>/importar-guia-docente` | confirmación humana antes de escribir | db | REUSE (ADAPT a F4.1) |
| `routes/auth.py` 9.8 KB | INFRA/UI | gate `before_request`, CSRF global, `/unlock`,`/lock`, rate-limit, `Authorization: Bearer/X-GREELEC-KEY`, `hmac.compare_digest`, `secrets.token_urlsafe` | sesión Flask | auth | ADAPT (single-user local-first) |
| `routes/vistas.py` 4 KB | UI | `GET /vista/*` (dashboard, asignatura, calendario, horario, linea-tiempo, repaso, espacios-estudio, modo-examen, ajustes, changelog) + `_detectar_ip_local,_info_base_datos` | queries directas en vista | db | REUSE (UI F15) |
| `routes/errors.py` 628 B | INFRA | `ApiError(mensaje,status)`, `register_error_handlers` (`ApiError→400,ValueError→400,404→JSON`) | — | — | ADAPT (→D2) |
| `templates/` 16 Jinja2 | UI | `index,dashboard,asignatura,calendario,horario,linea_tiempo,repaso,espacios_estudio,espacio_estudio_detalle,modo_examen,ajustes,changelog,unlock` + partials `_buscador_global,_notas_rapidas,_notificaciones_bell` | SSR + `csrf_token,lock_activo,tema_actual` | escapado Jinja; auditar el filtro `safe` | OUT_OF_SCOPE (PySide6 F15) |
| `static/css/` 17 + `static/js/` 23 + `static/vendor/pdfjs/**` + `static/vendor/lucide/sprite.svg` | UI/ASSET | design-system Apple Dark/claro, print, fetch JSON + `X-CSRFToken`, visor PDF embebido, iconos | sin framework | auditar CSP/SRI en pdfjs | OUT_OF_SCOPE (UI) / REUSE tokens |
| `tests/` 33 ficheros (~150 KB) | TEST | auth, backup, backup_automatico, bloques, busqueda, conceptos, documentos_seguridad (magic-bytes/traversal/ext), espacios, estado, estado_notas, estudio_y_repeticion, exportar_expediente, guia_docente, hitos, importar_ics, js_sintaxis, linea_tiempo, migracion, nota_minima, notificaciones, notificaciones_nativas, notas_rapidas, objetivo_y_recordatorio, organizacion_documentos, racha, seed, siglas_horario, ajustes_bd, anotaciones_pdf, asignaturas_borrado, backup, cambio_externo, empaquetado | pytest | — | KEEP as intent (ADAPT a F4.1) |
| `migrations/` 23 Alembic | MIGRATION | `c73474549a28 baseline` + 22 (`fase11 metadatos`, `fase10 nombre profesor`, `espacios_estudio`, `org jerárquica docs`, `contenido_normalizado`, `búsqueda global/favoritos/recientes`, `sesion_estudio`, `dia_actividad`, `nota en sesión`, `nota_rapida`, `aviso_descartado`, `anotaciones_pdf`, `profesor múltiple`, `bloques nota jerárquica`, `orden componentes`, `esquemas alternativos`, `nota_minima`, `objetivo_media`, `nombre_original auditoría`, `índices`, `calendario+horario`, `tarea_evento.documento_id`) | Alembic + SQLite `render_as_batch=True` | dry-run+snapshot en migración | MIGRATE (fusionar con F2) |

## 10. Gestion-Academica architecture

```text
Browser/pywebview (templates/*.html + static/css+js + pdf.js)
  → vistas.py (SSR, queries directas) + 32 Blueprints JSON (routes/*)
    → models.py (ActiveRecord: entidades+validates+to_dict+cálculos) + utils.py + guia_docente.py
      → Persistence: Flask-SQLAlchemy SQLite DATA_DIR/academico.db + Alembic auto-upgrade
        + FS DOCUMENTOS_DIR/{id_slug}/{categoria}/{id_grupo}/ + backups/*.zip
      → External: OneDrive, Wuolah/Studocu URLs, Atenea .ics, winotify, WebView2, .env
```

- Lógica de negocio en **dos sitios**: `models.py` (`calcular_resultado_componentes, esquemas_con_ganador, calcular_estado_notas, fechas_sesiones_horario, calcular_racha*, reclasificar`) y `routes/*` (`media_curso, objetivo_media, detectar_conflictos, calcular_notificaciones, autocrear EspacioEstudio, importar ICS/guía`).
- Persistencia: solo SQLAlchemy; sin repositorios/DAOs; `db.session` manipulado directamente en cada ruta y script; `to_dict()` mezcla serialización API con dominio.
- Acoplamiento: `routes→models→db` directo; `vistas→models` queries en capa UI; `utils↔routes.documentos` circularidad contenida (`apartados→documentos._borrar/_mover`); scripts importan `app.create_app`+modelos+FS.
- Contradice D1 (dominio no puro), D2 (errores `ApiError` paralelo, sin `AC-*`), D3 (deps sin pins, `LICENSE` ausente).

## 11. Security audit (ambos repos)

| Hallazgo | Archivo:línea | Riesgo | Recomendación |
|---|---|---|---|
| Auth abierta por defecto | Gestion `config.py:Config` (sin `GREELEC_LOCK_KEY` → no login), `routes/auth.py:gate` | MEDIO: LAN HTTP sin auth | F4: single-user local-first con lock-key explícito + aviso; no portar a multiusuario |
| `SESSION_COOKIE_SECURE=False` + SECRET_KEY efímera | `config.py` | MEDIO-BAJO | ADAPT: fijar key persistente, cookie secure solo HTTPS |
| Rate-limit en memoria | `routes/auth.py:_intentos_fallidos` | BAJO (un proceso) | ADAPT: rate-limit persistente o LATER_PHASE |
| XXE mitigado (ET + guardas) | `documents/{docx_adapter:73,omml:56,tabular_adapter:72}.py` | BAJO | mantener; `defusedxml` opcional |
| SSRF `urlopen` | `engines/ai.py:47–61`, `pdf/stirling.py:82,91,181,194` | MEDIO-BAJO | allow-list host/localhost |
| `subprocess` `shell=False` | `infrastructure/ngspice.py:216,240,341`, `pdf/stirling.py:109` | BAJO | mantener |
| `javascript:/data:/vbscript:` | `documents/{links:23,security:16,conversor_sanitize:38,validate:70}.py` | BAJO (3 capas) | mantener |
| SVG scripts | `documents/conversor_math.py:296–313` | BAJO (solo data-latex/aria) | mantener |
| Zip Slip/Bomb | `documents/office_security.py:27–62`, `routes/backup.py:_validar_zip_seguro` | BAJO (guards) | mantener |
| formula-injection CSV→Excel | `documents/tabular_adapter.py:52` | BAJO-UNKNOWN | prefijar `'` a `=+-@` al exportar |
| `__import__` en test | `tests/test_conversor_equiv.py:75` | NINGUNO | higiene |
| Destructive scripts | Gestion `seed.py(--reset),fix_ciaf,limpiar,reorganizar,cargar_*` | MEDIO | OUT_OF_SCOPE; ADAPT solo `--dry-run`+backup |
| `LICENSE` referenciado pero ausente | Gestion `README.md` | MEDIO (D3) | REIMPLEMENT: LICENSE MIT + NOTICE |

**No hallados**: `eval/exec/compile/pickle/marshal/os.system/shell=True` en runtime; SQL solo ORM + `LIKE/ilike` parametrizado; JS/macro/notebook execution; C/VHDL/SPICE execution.

## 12. D1 audit

- **CONFORME** (domain puro, infra confinada, sin imports dinámicos, sin ciclos demostrados).
- **Deuda** UI→domain directo: `ui/simulation.py:73,88,103,118`, `ui/virtual_lab.py:142,143,156,212,228,268`; permitida por test actual, prohibida por D1-008 → re-enrutado F15.
- `domain/authoring.py:13` importa `documents.ast` (permitido por test; decisión F4).
- **Gestion-Academica: CONTRADICE** (dominio = `db.Model`; UI consulta modelos; lógica en routes).

## 13. D2 audit

- `errors.py:18–68` raíz `AcademicCoreError(AC-APP-000)` + 8 subclases; `UiError` frozen `:80–86`; `to_ui_error:101–154`; `ui_error_for_code:157–168`.
- Logging `logging_config.py:1–101`: stdlib, domain prohibido, `event_code/component/operation/correlation_id`, redacción secretos/home.
- `except Exception` pervasivo **con contexto** (`application/academic_io.py:84,114; ingest.py:123,165,200; resources/adapters.py:140,182; documents/batch.py:60; ui/*`).
- `except: pass` reales: §7 (MEDIO) — catalogar/justificar.
- `print()` 0 en `src/`; `getattr/setattr` defensivos (no despacho).
- **Gestion**: `ApiError` paralelo sin `AC-*`; `register_error_handlers` mapea `ValueError→400` (no tipado); REIMPLEMENT vía `to_ui_error`.

## 14. D3 audit

- AcademicCore: LICENSE MIT; headers SPDX presentes (excepción `documents/security.py`); `pyproject.toml:18–29` (PySide6≥6.7 runtime; extras dev/pdf/html/anki); `requirements-lock.txt:4–12` pinnea; `sbom.json` CycloneDX 1.5; `THIRD_PARTY_NOTICES.md:17–30` con `pip show`/metadata.
- Compat: bs4 MIT, lxml BSD-3 (libxml2 embebida: versión ?), pypdf BSD-3, markdownify/mathml2latex/genanki/pytest MIT, PySide6 LGPL-3 dinámico compatible MIT.
- **UNKNOWN**: Stirling (Apache-2.0 vs MIT-open-core), libxml2 en wheels lxml; GREELEC license.
- **Gestion**: `requirements.txt` sin pins; `LICENSE` ausente.

## 15. Determinism audit

| Área | Clasificación | Evidencia |
|---|---|---|
| Document digest | DETERMINISTIC | `documents/ast.py:219–250` (sort_keys, sin history/timestamps) |
| execution-trace/1 | DETERMINISTIC | `domain/execution/codec.py:26–43,177–195` + tests `PYTHONHASHSEED` multiproceso |
| FS/batch | DETERMINISTIC | `documents/batch.py:37,45` `sorted(files)`; `application/authoring.py:249` |
| Sets/dicts | CONDITIONALLY | sets en `database.py:103`; metadata ordenada `codec.py:320` |
| random/seeds | CONDITIONALLY | `domain/assessment/models.py:90–98` (`random.Random(seed)`; `None`=no det.) |
| Timestamps/UUID | NON_DETERMINISTIC (excluidos de digest) | `logging_config.py:39` `uuid4`; `application/*` `datetime.now(utc)` |
| Locale/TZ | DETERMINISTIC | UTC explícito, ISO-8601 |
| Gestion: notas/estado | CONDITIONALLY | `calcular_estado_notas` sin random; `seed.py` orden determinista; `seed --reset` destructive |
| Gestion: `datetime.now` | NON_DETERMINISTIC | `models.py` timestamps, `created_at/updated_at` |
| Gestion: `import_apuntes.py:hash()` | NON_DETERMINISTIC (tmp) | solo tmp, no serializado |

## 16. Serialization audit

| Formato | Schema | Versionado | Seguridad | Digest/Migración |
|---|---|---|---|---|
| AST JSON | `SCHEMA_VERSION=1` | `from_dict` estricto, rechaza kind/version desconocidos | `allow_nan=False`, sin pickle/eval | `Document.digest()` SHA-256 semántico |
| execution-trace/1 | `schema/version=1`, claves cerradas | `VersionMismatchError` | 8MiB/depth 7/2M items, sin floats/NaN | `trace_digest` sin metadata; replay mismatch |
| digital-trace/1 | `digital-trace/1` | strict round-trip | límites de dígitos | `circuit_digest` |
| SQLite | `SCHEMA_VERSION` tabla | migraciones forward-only transaccionales | WAL/FK/busy_timeout, parametrizado | CAS `sha256[0:2]/[2:4]/sha`; backup sidecar SHA-256 |
| CSV/XLSX | sin schema (tabla) | degradación con warnings | `safe_open_zip`, topes | images→CAS via `put` |
| XML/OOXML/OMML | sin schema | — | ENTITY/DOCTYPE rechazados, depth 64/200k | `history` con counts |
| ICS | RFC 5545 (export) | — | heurística import (horario peninsular) | dedup título+fecha |
| HTML/Markdown/LaTeX | AST es fuente | renderer derivado | 3 capas XSS | — |
| Gestion backup ZIP | sin schema | — | slip/bomb 5GB/200k/ratio100/2GB | `_validar_sqlite` (header check) |

## 17. Testing audit

- `pytest -q` (2026-09-23, 10 min timeout): 11 failed, resto passed. Las fallas son **preexistentes por CRLF** (`test_e0_execution_trace.py::test_e0_g01_golden_voltage_divider`, `test_f8q4_digital_trace_serialization.py::test_q4_g01_golden_fixture[6]`, `test_f8q5_logic_analyzer.py::test_q5_g01_golden_captures[4]`), verificadas byte a byte en un worktree limpio de `3642ca5` sin F3.1 → **regresión F4.0/F3.1 = 0**. Duración ~10 min (timeout), excluir `slow` para CI.
- F3 relevante: **95 passed, 2 skipped** (reportlab ausente).
- F3.1: 44/44 (`test_f3_ext` 40 + `test_f3_golden` 4).
- Gestion-Academica: 33 test files (~150 KB, ~600 test items); no ejecuté (F4.0 solo audit; no CI there; no `requirements-dev` pins).
- Distinción: `preexisting` (CRLF goldens), `environmental` (reportlab, pypdf absent), `regression` = **0**.

## 18. F3/F3.1 reconciliation

| Capacidad | F3 base | F3.1 | Estado |
|---|---|---|---|
| AST | 19 kinds, v1, stdlib | digest + canonical |Extiende, no duplica |
| HTML/MD | bs4→AST, sanitize | callouts/footnotes/task/details/links exactos/TOC | ADAPT |
| PDF | pypdf text/pages | — | LATER_PHASE (tables/images/OCR) |
| DOCX/OMML/IPYNB/XLSX/CSV | — | adapters nuevos | IMPLEMENTED |
| MathML/shielding/OMML | 1:1 + shielding 9 fuentes | `latex_norm` único, `omml` +cases/borderBox | ADAPT |
| Formulas/problems/terms | — | extractors con provenance | IMPLEMENTED |
| Batch/trace/LaTeX/TOC/links | — | nuevos | IMPLEMENTED |
| F3-ext vs Conversor | — | no duplica AST/CAS/errores/trace | PASS |

## 19. Conversor reconciliation

Fuera de AcademicCore: fuzzy resolver (OUT_OF_SCOPE), figs-from-scripts JS (UNSUPPORTED), quiz BANC/DATA/ITEMS (LATER_PHASE), 37 solvers/UPC engine/GUI Tk/lab HTML (OUT_OF_SCOPE), MD→HTML CDN (LATER_PHASE), Anki pleno (LATER_PHASE), PDF tables/images (LATER_PHASE), OCR (UNSUPPORTED), SPICE netlists (OUT_OF_SCOPE). `problem_generator` (DEFER/OUT_OF_SCOPE). `UltraFaithfulMarkdownConverter` (OUT_OF_SCOPE, solo shield idea).

## 20. AcademicCore ↔ Gestion comparison

| Gestion | AcademicCore equiv. | Coincidencia | Duplicación | Complementariedad | Conflicto | Acción | Fase |
|---|---|---|---|---|---|---|---|
| `Anio/Cuatrimestre` | `domain/academic.py` (7 niveles) | media | model overlap | curriculum depth | ActiveRecord vs dataclass | REIMPLEMENT en F4.1 | F4.1 |
| `Asignatura` (ECTS, siglas, estado, optativas) | `domain/academic.py` (Course/Section) | alta | model overlap | state machine (`superada/cursando/pendiente`) | — | ADAPT (`cambiar_estado_asignatura`) | F4.1 |
| `Componente/Bloque/Esquema` | `domain/grading.py` + `results.py` | media | — | bloques jerárquicos, esquemas alternativos, `nota_minima` | — | REIMPLEMENT | F4.1 |
| `calcular_resultado_componentes`, `esquemas_con_ganador` | `domain/grading.py` (Decimal HALF_UP) | media | — | fórmula de ponderación + ganador | Decimal vs float | REUSE concept, REIMPLEMENT | F4.1 |
| `calcular_estado_notas` | `domain/status.py` | alta | — | reglas AP/sobreviven | — | ADAPT | F4.1 |
| `Documento/GrupoDocumento/Apartado` | `documents/` (AST+CAS) + `domain/resources.py` | baja | FS/BD duplicado | F3 parsers (HTML/DOCX/PDF/IPYNB/XLSX) | DB+FS vs CAS | REIMPLEMENT sobre F2 CAS | F4.1 |
| `PaginaTexto` (pypdf index) | `documents/search.py` + FTS storage | media | index duplicado | FTS + excerpts | — | REIMPLEMENT | F4.1 |
| `Marcador/AnotacionPdf` | — | ninguna | — | PDF annotations | F3 PDF text-only | LATER_PHASE | F14 |
| `TareaEvento/HorarioClase` | `domain/schedule.py` + `conflicts.py` | alta | — | series recurrentes, ICS, conflictos | ActiveRecord | ADAPT | F4.1 |
| `EspacioEstudio/DiaActividad/SesionEstudio/racha` | `domain/results.py` (gradebook) | media | — | progreso/racha | — | REIMPLEMENT (F10) | F10 |
| `Concepto` SRS 0/3/18 | `domain/status.py` | baja | — | SRS | — | LATER_PHASE (F11) | F11 |
| `Hito` | `domain/results.py` (milestones) | media | — | objetivos | — | ADAPT | F4.1 |
| `NotaRapida` | `domain/authoring.py` | media | — | bloques | — | REIMPLEMENT | F4.1 |
| `Profesor` | — | ninguna | — | contexto | — | LATER_PHASE | F4.1 |
| `RecursoExterno` (Wuolah/Studocu) | `domain/resources.py` | media | — | provenance | — | ADAPT | F4.1 |
| `busqueda/favoritos/recientes` | `storage/store.py` FTS + `application/search.py` | media | — | FTS + excerpts | — | REUSE | F4.1 |
| `notificaciones` (atrasadas/inminentes) | — | ninguna | — | lógica | — | LATER_PHASE | F12 |
| `backup` ZIP + SQLite validation | `application/backup.py` + F2 | media | — | transaccional | — | REUSE | F4.1 |
| `guia_docente` heurística | F3.1 `problems/terms/formulas` | baja | — | extracción heurística + provenance | — | REUSE (F3.1) | F4.1 |
| `seed GREELEC` | — | ninguna | — | datos | — | OUT_OF_SCOPE (contenido) | — |
| `cargar_*/fix_ciaf/limpiar/reorganizar` | — | ninguna | — | ETL contenido | — | OUT_OF_SCOPE (contenido/data-migration) | — |
| `auth` (lock+CSRF+rate-limit) | `application/security.py` | media | — | single-user local-first | Flask session vs Qt | ADAPT (LATER_PHASE multiuser) | F4.1 |
| `ics export/import` | `domain/schedule.py` | media | serialización ICS | — | — | REIMPLEMENT (adapter) | F4.1 |
| `apuntes/documentos UI` | `ui/dashboard.py`, `ui/exercises.py` | baja | — | PySide6 canónico | Flask/Jinja vs Qt | REIMPLEMENT (F15) | F15 |
| `resultados/notas/export CSV` | `domain/results.py` + `application/queries.py` | media | — | ADR-0016 gradebook genérico | `to_dict()` ActiveRecord | REUSE | F4.1 |
| `seed/catálogo Optativas` | `domain/academic.py` (prerrequisitos) | baja | — | curriculum | — | OUT_OF_SCOPE (contenido) | — |
| `generación de preguntas` | **NO EXISTE** en ambos (Gestion solo extrae/importa) | — | — | — | — | OUT_OF_SCOPE (F9+/F12) | F12 |
| `IA/LLM` | `engines/ai.py` (Ollama/Gemini) | — | — | providers | — | KEEP_SEPARATE (F12) | F12 |
| `matemáticas/unidades/ingeniería` | `domain/engineering/*` completo | — | — | F6–F8 completo | — | KEEP_SEPARATE | F8 |
| `persistencia` | `infrastructure/database.py` + `storage/store.py` (SQLite+FTS+CAS) | alta | DTO/DAO duplicado | WAL, migraciones, FTS | — | REUSE | F4.1 |
| `serialización` | `documents/ast`, `domain/resources`, codecs estrictos | alta | JSON/ICS duplicados | más estrictos | — | REUSE | F4.1 |

## 21. Duplicate analysis

| Duplicidad | Canon | Decisión |
|---|---|---|
| Modelos `Anio/Cuatrimestre/Asignatura` | `CANONICAL_ACADEMICCORE` (`domain/academic.py`) | `MERGE_REQUIRED` → REIMPLEMENT en domain dataclasses |
| Persistencia `db.session` directo (Gestion) | `CANONICAL_ACADEMICCORE` (`infrastructure/database.py` + repositorios) | `MERGE_REQUIRED` → repositorios/ports |
| Errores `ApiError` | `CANONICAL_ACADEMICCORE` (`errors.py` + `to_ui_error`) | `MERGE_REQUIRED` → adapter Flask D2 |
| Cálculo notas (`modelos` vs `grading.py`) | `CANONICAL_ACADEMICCORE` (Decimal) | `MERGE_REQUIRED` |
| Documentos (FS+BD vs AST+CAS) | `CANONICAL_ACADEMICCORE` (F3+F2) | `MERGE_REQUIRED` |
| Búsqueda/paginación | `CANONICAL_ACADEMICCORE` (FTS) | `REUSE` |
| Horarios/conflictos | `CANONICAL_ACADEMICCORE` (`domain/schedule.py`/`conflicts.py`) | `REUSE` |
| SESIÓN/racha | `CANONICAL_ACADEMICCORE` (F10) | `LATER_PHASE` |
| UI Jinja/JS vs PySide6 | `CANONICAL_ACADEMICCORE` (F15) | `KEEP_SEPARATE` |
| Migraciones Alembic vs SQL | `CANONICAL_ACADEMICCORE` (`infrastructure/migrations/*.sql`) | `MERGE_REQUIRED` (mapeo one-way, sin doble escritura) |
| Ingesta OneDrive/Wuolah/Studocu | `CANONICAL_GESTION` | `REFERENCE` (contenido) |
| Metadata docente UPC/GREELEC | `CANONICAL_GESTION` | `OUT_OF_SCOPE` (contenido) |

## 22. Missing capabilities (Gestion → AcademicCore)

| ID | Funcionalidad | Origen | Deps | Valor | Riesgo | Destino | Fase | Estrategia |
|---|---|---|---|---|---|---|---|---|
| M-01 | Ciclo académico (`Anio/Cuatrimestre`) | `models.py`, `routes/anios.py,cuatrimestres.py` | Flask-SQLAlchemy | alto | bajo | `domain/academic.py` extend | F4.1 | ADAPT |
| M-02 | Gestión de asignaturas (siglas, ECTS, estado, optativas, prerrequisitos) | `models.Asignatura`, `routes/asignaturas.py` | — | alto | medio (ActiveRecord) | `domain/academic.py` + `application` | F4.1 | REIMPLEMENT |
| M-03 | Evaluación: componentes/bloques/esquemas/nota mínima/ganador | `models.py` (`Componente,Bloque,Esquema`), `routes/{componentes,bloques,esquemas}.py` | — | alto | medio | `domain/grading.py`/`results.py` extend | F4.1 | REIMPLEMENT |
| M-04 | Documentos por asignatura (categoría/grupo/etiquetas) | `models.{Apartado,GrupoDocumento,Documento}`, `routes/{apartados,grupos_documento,documentos}.py` | FS+BD | alto | alto (doble storage) | F3 AST + F2 CAS + `domain/resources` | F4.1 | REIMPLEMENT |
| M-05 | Lectura/progreso de documentos (`progreso`,`quitar-continuar`) | `routes/documentos.py` | — | medio | bajo | `application/documents.py` | F4.1 | ADAPT |
| M-06 | Tareas/eventos/calendario/posponer | `models.TareaEvento`, `routes/tareas.py,calendario` | — | alto | bajo | `domain/schedule.py` + `application` | F4.1 | REIMPLEMENT |
| M-07 | Horarios recurrentes/sesiones | `models.HorarioClase`, `routes/horarios.py,linea_tiempo.py` | — | alto | bajo | `domain/schedule.py` | F4.1 | ADAPT |
| M-08 | Detección de conflictos | `routes/conflictos.py` | — | alto | bajo | `domain/conflicts.py` | F4.1 | REUSE |
| M-09 | Import/export ICS | `routes/{ics,importar_ics}.py` | — | medio | medio (heurística) | adapter ICS | F4.1 | REIMPLEMENT |
| M-10 | Objetivos/hitos | `models.Hito`, `routes/hitos.py` | — | medio | bajo | `domain/results.py` | F4.1 | ADAPT |
| M-11 | Rápidas notas | `models.NotaRapida`, `routes/notas_rapidas.py` | — | medio | bajo | `domain/authoring.py` | F4.1 | REIMPLEMENT |
| M-12 | Profesores + guía docente → esquemas | `models.Profesor`, `guia_docente.py`, `routes/{profesores,guia_docente}.py` | pypdf | medio | medio (heurística) | `application/knowledge` (F4.1) | F4.1 | REUSE (heurística) + confirmación humana |
| M-13 | Recursos externos (Wuolah/Studocu) | `models.RecursoExterno`, `routes/recursos_externos.py` | — | bajo | bajo | `domain/resources.py` | F4.1 | ADAPT |
| M-14 | Búsqueda global + favoritos/recientes | `routes/busqueda.py` | — | medio | bajo | FTS `storage/store.py` | F4.1 | REUSE |
| M-15 | Notificaciones (atrasadas/inminentes) | `routes/notificaciones.py` | — | medio | bajo | `application/notify` | F4.2 | LATER_PHASE |
| M-16 | Espacio de estudio + racha + temporizador | `models.{EspacioEstudio,DiaActividad,SesionEstudio}`, `routes/{espacios_estudio,estudio,racha}.py` | — | alto | medio | `domain/study` | F10 | REIMPLEMENT (LATER_PHASE) |
| M-17 | SRS conceptos (0/3/18) | `models.Concepto`, `routes/conceptos.py` | — | medio | bajo | `domain/srs` | F11 | LATER_PHASE |
| M-18 | Auth lock + CSRF + rate-limit | `routes/auth.py`, `config.py` | Flask session | medio | medio (HTTP LAN) | `application/security.py` | F4.1 | ADAPT |
| M-19 | Backup/exportar-importar + expediente CSV | `routes/backup.py` | zip+sqlite | alto | medio | `application/backup.py` | F4.1 | REUSE |
| M-20 | Detección cambio externo (Syncthing) | `routes/cambio_externo.py` | mtime+counts | medio | bajo | F13 | F13 | LATER_PHASE |
| M-21 | Anotaciones/marcadores PDF | `models.{Marcador,AnotacionPdf}`, `routes/{marcadores,anotaciones}.py` | — | medio | medio | `pdf/` | F14 | LATER_PHASE |
| M-22 | Changelog in-app | `changelog.py` | — | bajo | bajo | F15 | F15 | ADAPT |

Inverso (AcademicCore → Gestion): motores de ingeniería (F8), unidades/álgebra exacta, execution trace (E0), AST documental, CAS/integridad, FTS, backups atómicos, evaluación formal (F9), PDF/Stirling, explicabilidad, no-IA-por-defecto. Ninguno debe “portarse” a Gestion; Gestion los referencia vía future merge.

## 23. Migration matrix

| ID | Origen | Funcionalidad | Destino | Acción | Fase | Riesgo | Dependencias |
|---|---|---|---|---|---|---|---|
| X-01 | Gestion `models.Asignatura` | Asignatura (código/siglas/ECTS/estado) | `domain/academic.py` | REIMPLEMENT | F4.1 | medio | identity/graduation |
| X-02 | Gestion `models.Anio/Cuatrimestre` | Ciclo | `domain/academic.py` | REIMPLEMENT | F4.1 | bajo | persistence |
| X-03 | Gestion modelos | Componentes/bloques/esquemas | `domain/grading.py`/`results.py` | REIMPLEMENT | F4.1 | medio | Decimal |
| X-04 | Gestion `calcular_resultado_componentes` | Ponderación + ganador | `domain/grading.py` | ADAPT | F4.1 | bajo | results |
| X-05 | Gestion `calcular_estado_notas` | Estado notas | `domain/status.py` | ADAPT | F4.1 | bajo | grading |
| X-06 | Gestion `Documento/GrupoDocumento` | Docs por asignatura | `documents/*` + `domain/resources` | REIMPLEMENT | F4.1 | alto | F2 CAS + F3 |
| X-07 | Gestion `PaginaTexto` | Índice PDF | `application/search.py` + FTS | REIMPLEMENT | F4.1 | medio | pypdf |
| X-08 | Gestion `TareaEvento` | Tareas | `domain/schedule.py` | REIMPLEMENT | F4.1 | medio | identity |
| X-09 | Gestion `HorarioClase` | Horarios | `domain/schedule.py` | REIMPLEMENT | F4.1 | bajo | conflicts |
| X-10 | Gestion `detectar_conflictos` | Conflictos | `domain/conflicts.py` | REUSE | F4.1 | bajo | schedule |
| X-11 | Gestion ICS | ICS adapter | `infrastructure/ics.py` | REIMPLEMENT | F4.1 | medio | schedule |
| X-12 | Gestion `Hito` | Hitos | `domain/results.py` | ADAPT | F4.1 | bajo | results |
| X-13 | Gestion `NotaRapida` | Notas rápidas | `domain/authoring.py` | REIMPLEMENT | F4.1 | bajo | authoring |
| X-14 | Gestion `Profesor` | Profesorado | `domain/academic.py` (Faculty) | ADAPT | F4.1 | bajo | persistence |
| X-15 | Gestion `guia_docente.py` | Guía docente → datos | `application/knowledge.py` | REUSE | F4.1 | medio | F3.1 provenance |
| X-16 | Gestion `RecursoExterno` | Recursos | `domain/resources.py` | ADAPT | F4.1 | bajo | F2 |
| X-17 | Gestion `busqueda.py` | Búsqueda | FTS + `application/search.py` | REUSE | F4.1 | bajo | storage |
| X-18 | Gestion `backup.py` | Backup | `application/backup.py` | REUSE | F4.1 | bajo | storage |
| X-19 | Gestion `auth.py` | Auth | `application/security.py` | ADAPT | F4.1 | medio | D2 |
| X-20 | Gestion `notificaciones.py` | Notificaciones | `application/notify.py` | DEFER | F4.2 | bajo | schedule |
| X-21 | Gestion `espacios_estudio/racha/estudio` | Estudio/racha | `domain/study` | LATER_PHASE | F10 | medio | F4 |
| X-22 | Gestion `Concepto.repaso_hoy` | SRS | `domain/srs` | LATER_PHASE | F11 | bajo | F4 |
| X-23 | Gestion `marcadores/anotaciones` | PDF annotations | `pdf/annotations` | LATER_PHASE | F14 | medio | F3 PDF |
| X-24 | Gestion `seed.py` | Seed GREELEC | data/ | OUT_OF_SCOPE | — | bajo | — |
| X-25 | Gestion `cargar_*/fix_*/limpiar_*` | ETL | scripts | OUT_OF_SCOPE | — | bajo | — |
| X-26 | Gestion `templates/static` | UI | `ui/` | OUT_OF_SCOPE | F15 | — | Qt |
| X-27 | Gestion `escritorio.py`/`.spec` | Launcher | `app.py` + PyInstaller | LATER_PHASE | D4 | bajo | — |
| X-28 | Conversor quiz BANC | Preguntas | D6/D7/F9 | LATER_PHASE | F9 | medio | F4 |

## 24. F4 scope

Objetivo: **gestión académica operativa y conocimiento** sobre el dominio canónico existente.

- Alcance F4.1: (a) gestión de ciclos/asignaturas/estado; (b) evaluación (componentes, bloques, esquemas, nota mínima, resultado); (c) documentos por asignatura (sobre F3 AST + F2 CAS); (d) tareas/horarios/conflictos/ICS; (e) hitos/objetivos; (f) profesores/recursos; (g) búsqueda; (h) backup; (i) guía docente como **extracción con provenance**.
- F4.2 (opcional): notificaciones, notas rápidas, configuración de widgets, favoritos/recientes.
- F4.3 (posterior): ingestores de contenido externo (Wuolah/Studocu) solo como `RecursoExterno` con URL, sin fetch remoto.

Non-goals: UI PySide6 (F15), solvers (F8), GUM (F8-O), SRS/mastery (F10/F11), evaluación formal de intentos (F9), IA/Tutor (F12), sync cloud (F13), generación de preguntas (F12/D6), modelos GPT, HPC.

## 25. F4 architecture

```text
UI (F15 PySide6)
  → Application services (mgmt, evaluation, documents, schedule, knowledge)
    → Domain (academic, grading, schedule, conflicts, results, resources) + Ports
      → Infrastructure (SQLite repos, CAS, FTS, ICS, PDF, UI-free)
```

Componentes propuestos (sin implementar):

| Módulo | Responsabilidad | Fase |
|---|---|---|
| `domain/academic.py` (extend) | `AcademicYear/Term/Course/Faculty/Enrollment/Status` | F4.1 |
| `domain/grading.py` (extend) | `AssessmentComponent/Block/Scheme/MinGrade` | F4.1 |
| `domain/knowledge.py` | `Concept/Definition/Formula/Problem` re-export desde F3.1 | F4.1 |
| `application/mgmt.py` | CRUD casos de uso de asignaturas/años | F4.1 |
| `application/evaluation.py` | Componentes/esquemas/resultados | F4.1 |
| `application/documents.py` (extend) | Link `Resource`↔`Course` (provenance) | F4.1 |
| `application/schedule.py` | Tareas/horarios/conflictos/ICS | F4.1 |
| `application/knowledge.py` | Guía docente → extracción | F4.1 |
| `infrastructure/repositories/academic.py` | Repos SQLite parametrizados | F4.1 |
| `infrastructure/repositories/evaluation.py` | Repos componentes/bloques | F4.1 |
| `infrastructure/repositories/schedule.py` | Repos tareas/horarios | F4.1 |

## 26. Later phases (no-pérdida)

- F9: assessment formal (`routes/notas_rapidas`? no: F9 ya existe), D6 banco de preguntas.
- F10: `EspacioEstudio`/racha/temporizador → mastery.
- F11: `Concepto` SRS 0/3/18 → spaced repetition.
- F12: notificaciones, tutor IA, generation (NO en F4).
- F13: `cambio_externo` (Syncthing), cloud.
- F14: `Marcador`/`AnotacionPdf` (PDF annotations).
- F15: PySide6 dashboard, `modo_examen`, chuleta, Ajustes; `templates/static` (Jinja/JS) OUT_OF_SCOPE.
- D4/D5: CI/build, test suite (scripts in `requirements-dev`).
- D6/D7: banco de preguntas neutro, ingesta estructurada al Knowledge Core (F3.1 problems/terms ya dan provenance).

## 27. Risks

| RISK-ID | Descripción | Origen | Impacto | Prob | Sev | Mitigación | Fase |
|---|---|---|---|---|---|---|---|
| R-01 | Dominio acoplado a ORM → no portable | Gestion `models.py` | alto | alta | crítica | Extraer dataclasses a domain; repos en infra | F4.1 |
| R-02 | Doble storage (FS+BD vs CAS) → divergencia | Gestion docs | alto | alta | crítica | CAS único; documents como Resource | F4.1 |
| R-03 | Pérdida de datos en migración Alembic→SQL | 23 migraciones | alto | media | alta | Snapshot + validación + dry-run | F4.1 |
| R-04 | Errores `ApiError` paralelos | Gestion | medio | alta | media | Mapeo a D2; test unicidad AC-* | F4.1 |
| R-05 | Licencias sin pins (Gestion) | `requirements.txt` | medio | media | media | Lock file + SBOM | F4.1 |
| R-06 | Auth abierta por defecto | `config.py` | medio | media | media | Lock-key + rate-limit persistente | F4.1 |
| R-07 | Determinismo (timestamps/seed) | `models.py` | medio | media | media | ISO UTC + digest sin timestamps | F4.1 |
| R-08 | Stirling license sin resolver | `pdf/stirling.py` | medio | baja | media | Verificar Apache-2.0 vs MIT | D3 |
| R-09 | `except: pass` silenciosos | §13 | medio | alta | media | Catalogar; emitir warning/log | F4.1 |
| R-10 | Códigos AC-* colisión | §14 | medio | media | media | Registro central + test unicidad | F4.1 |
| R-11 | UI Jinja→PySide6 doble mantenimiento | F15 | medio | alta | media | Mantener Jinja como `REFERENCE`; Qt canónico | F15 |
| R-12 | Performance SQLite con >7k docs | `routes/documentos.py` | medio | media | media | FTS + índices + paginación | F4.1 |
| R-13 | ICS heurísticas incorrectas | `importar_ics.py` | bajo | media | baja | `pendiente_revision` + provenance | F4.1 |
| R-14 | ReDoS en regex evaluadores | `problems.py:14–28` | bajo | baja | baja | Acotar + timeout | F4.1 |
| R-15 | CSV formula-injection | `tabular_adapter.py:52` | bajo | baja | baja | Prefijo `'` | F4.1 |

## 28. ADR candidates

- **ADR-0017** Modelo académico canónico (dataclasses domain vs ActiveRecord).
- **ADR-0018** Repositorios/Ports para persistencia (SQLite abstracto).
- **ADR-0019** Documentos: `Resource`+CAS+AST (sin columnas dedicadas).
- **ADR-0020** Evaluación: scheme/block/component + Decimal.
- **ADR-0021** Knowledge: reuse F3.1 extractors (no re-parse).
- **ADR-0022** ICS adapter determinista + `pendiente_revision`.
- **ADR-0023** Auth single-user local-first (lock-key).
- **ADR-0024** Migración de datos: dry-run + snapshot + validación.
- **ADR-0025** UI: PySide6 (no Jinja) en F15.

## 29. Performance

- AcademicCore: F3-ext 1.9 ms HTML small / 203.6 ms HTML 200-sections / 25.1 ms MathML 50eq / 4.2 ms DOCX 200-para / 2.6 ms MD render / 4.9 ms LaTeX render (snapshot 2026-09-23).
- F4 objetivo: CRUD academic <10 ms, búsqueda <200 ms p95, migración 7k docs con progreso y cancelación.

## 30. Licensing

- AcademicCore MIT (uniforme). Stirling REQUIRES VERIFICATION (R-08). lxml/libxml2 UNKNOWN minor. GREELEC/Gestion UNKNOWN (LICENSE ausente).
- F4: reutilizar Algorithms de Gestion bajo **confirmación de licencia**; si no verificable, REIMPLEMENT desde spec.

## 31. Security (F4-specific)

- F4.1 no añade `eval/exec/pickle/subprocess/network` a domain.
- ICS/upload/ZIP con límites explícitos; backup import con `_validar_zip_seguro` equivalente F2.
- CSRF/lock solo si UI web (Flask `REFERENCE`); PySide6 F15 usa `UiError` + sandbox.

## 32. Test baseline

- F3: 95 passed, 2 skipped.
- Full AcademicCore: 11 preexistentes CRLF (byte-idénticas en `3642ca5`), resto passed; regresión = 0.
- Gestion: 33 test files, no ejecutados (auditoría; entorno sin pins).
- F4.1 requiere: `test_f4_domain.py`, `test_f4_mgmt.py`, `test_f4_evaluation.py`, `test_f4_documents.py`, `test_f4_schedule.py`, `test_f4_knowledge.py`, `test_f4_migration_dryrun.py`, golden/migración data.

## 33. Open questions

1. ¿El contenido GREELEC (54 asigs, 7400 págs) entra como **datos de referencia** o queda fuera? (actualmente OUT_OF_SCOPE).
2. ¿Migrar los 23 Alembic a `infrastructure/migrations/*.sql` o mantener Alembic como adapter? (recomendado: SQL canónico, Alembic solo lectura/import una vez).
3. ¿Autenticación real (multiusuario) o lock-key local? (recomendado: local-first lock).
4. ¿Migrar 676 documentos reales al CAS ahora o en F13 sync? (recomendado: F4.1 import con progreso + dry-run).
5. ¿F4.1 incluye `Profesor` como entidad o solo metadata? (recomendado: entidad mínima).
6. Stirling license verification pendiente.

## 34. F4.1 milestones

1. **M1** — Domain académico dataclasses (`AcademicYear/Term/Course/Faculty/Status`) + `identity` estable; sin ORM.
2. **M2** — Evaluación: `Component/Block/Scheme/MinGrade/WeightedResult` (Decimal) + tests equivalencia Gestion.
3. **M3** — Repositorios SQLite (`infrastructure/repositories/{academic,evaluation}.py`) + migración one-way + dry-run.
4. **M4** — Documentos: link `Resource`↔`Course`, CAS, progreso, FTS.
5. **M5** — Schedule: `Task/ClassSession/Conflict` + ICS adapter.
6. **M6** — Knowledge: `Concept/Definition/Formula/Problem` re-export F3.1; extracción de guía docente.
7. **M7** — Hitos/objetivos/notas rápidas + búsqueda + backup.
8. **M8** — Auth/seguridad D2 (lock-key, AC-* codes, warnings) + hardening.
9. **M9** — Golden data migration + full regression + GATE-F4-CERTIFICATION.

## 35. Acceptance criteria (F4.1)

- Domain F4 sin `db`/Flask/SQLAlchemy (test AST).
- Notas Decimal exactas; equivalencia con `calcular_resultado_componentes` (golden).
- Documentos en CAS (`cas:<sha256>`), 0 bytes en BD salvo índice.
- Tareas/horarios sin conflictos sobre golden ICS.
- Errores solo D2 (`AC-*`), 0 `ApiError` en dominio.
- Determinismo: same input → same digest, `PYTHONHASHSEED` 0/11/2024/random.
- Migración dry-run idempotente; 0 pérdidas (conteo de entrada=salida).
- 0 regresiones; F3/F3.1 gates siguen verdes.
- UI (F15) consume solo application/ports.

## 36. Performance (ver §29)

## 37. Security (ver §31)

## 38. Final gate decision

```text
F4 DESIGN READY
```

Justificación: ambos repos auditados (282+110 `.py`, archivo por archivo en §9), arquitectura reconstruida, 22 capacidades faltantes inventariadas (§22), 28 migraciones clasificadas (§23), duplicidades resueltas (§21), F3/Conversor reconciliados (§18-19), D1/D2/D3/seguridad/determinismo/serialización/tests auditados (§11-17), F4 definido con milestones + acceptance (§24-25, §34-35).

Riesgos residuales (no bloqueantes para diseño): R-01/R-02 (requieren M1/M4 en F4.1), R-08 (Stirling), R-03 (migración), decisiones §33.

**NO implementé F4.1.** Único cambio deliberado: este gate.
Nota de reproducibilidad: `.claude/settings.local.json` apareció como untracked externo durante la sesión (configuración del harness `impeccable`, ajeno a F4.0); no fue creado ni editado por esta auditoría.

## 39. Informe final

```text
========================================
ACADEMICCORE + GESTION-ACADEMICA AUDIT
========================================

AcademicCore HEAD:   34629a5 (main; +7 sobre origin/main 3642ca5)
Gestion-Academica HEAD: 187a614 (master)

AcademicCore files audited: 282 src/*.py + 116 tests + 146 docs (+config/packaging)
Gestion-Academica files audited: 110 .py + 20 HTML + 26 JS + 17 CSS + 33 tests + 23 migrations

AcademicCore tests: 11 failed preexistentes (CRLF golden; regresión 0), resto passed
Gestion-Academica tests: 33 files inventariados (no ejecutados: fase audit-only)

Architecture findings: D1 conforme salvo UI→domain debt; Gestion ActiveRecord contradice D1
Security findings: 0 eval/exec/pickle/shell=True; 2 SSRF urlsopen; 1 XLSX formula-injection pendiente; auth LAN abierta
D1 findings: 2 (UI→domain, domain→documents)
D2 findings: ~20 `except: pass`; códigos AC-* sin registro central; ApiError paralelo (Gestion)
D3 findings: Stirling UNKNOWN; lxml/libxml2 UNKNOWN; Gestion LICENSE ausente; pins ausentes
Determinism findings: timestamps/UUID NON_DET (excluidos de digest); sets CONDITIONAL; batch/trace DETERMINISTIC

Missing capabilities: 22 (M-01..M-22)
Duplications: 11 (modelos, persistencia, errores, docs, búsqueda, horario, UI, migraciones)
Migration candidates: 28 (X-01..X-28)
F4 candidates: M1..M9 (academic, evaluación, docs, schedule, knowledge, hitos, seguridad)
Later-phase candidates: F10 (racha), F11 (SRS), F12 (notif/IA), F13 (sync), F14 (PDF annot), F15 (Qt)

Critical risks: R-01 ActiveRecord→domain, R-02 doble storage, R-03 migración Alembic→SQL

Gate:
F4 DESIGN READY
========================================
```
