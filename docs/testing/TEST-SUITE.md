# Suite global de tests (D5)

> Documento canónico de la suite. Infraestructura CI: `docs/testing/CI.md`
> (D4). Estrategia histórica resumida en `docs/testing/STRATEGY.md`.

## 1. Suite estándar

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest -m "not external" -q
```

Es exactamente lo que ejecuta el job `test` de CI en las 4 celdas
(windows/ubuntu × py 3.12/3.13). Incluye TODO salvo `external`: unit,
integration con probe, persistencia, migraciones, arquitectura, perf,
`slow`, UI offscreen y goldens.

## 2. Comandos por necesidad

| Necesidad | Comando |
|---|---|
| Suite estándar (= CI) | `pytest -m "not external" -q` |
| Bucle rápido (sin migración/pesados) | `pytest -m "not external and not migration and not perf and not slow" -q` |
| Solo contratos de arquitectura | `pytest -m arch -q` |
| Solo reproducibilidad | `pytest -m repro -q` |
| Solo migraciones | `pytest -m migration -q` |
| Runtimes vivos (ngspice/Stirling/Java) | `pytest -m external -q` (requiere runtimes; nunca bloquea) |
| Presupuesto temporal | `pytest -m perf -q` (umbrales NUNCA relajados para verdear) |
| Un área | `pytest tests/test_f8b_mna_solver.py -q` |

`pytest` a secas ejecuta también `external` (falla/skip sin runtimes);
por eso la forma canónica siempre lleva `-m "not external"`.

## 3. Markers

Registrados en `pyproject.toml` (`test_d5_contracts.py` fija que todo
marker usado existe y que `perf`/`arch`/`repro` se usan de verdad):

| Marker | Significado | En gate |
|---|---|---|
| `arch` | fronteras de arquitectura (`test_architecture.py`) | sí |
| `migration` | gates de migración/cobertura | sí |
| `repro` | reproducibilidad netlist/CAS | sí |
| `external` | necesita runtime VIVO (ngspice, Stirling, Java); nunca bloquea | NO |
| `integration` | necesita runtime INSTALADO; con sonda `skipif`/skip si falta | sí (skips visibles) |
| `slow` | stress de aritmética exacta (minutos por diseño; NO excluido del gate) | sí |
| `perf` | presupuesto temporal (sensible al runner; umbrales intactos) | sí |

`integration` sin `external` (f8b/f8c) = validación cruzada con ngspice
cuando está instalado, skip explícito cuando no. No es bypass: la sonda
es la clasificación (§9 D5).

## 4. Fixtures y patrones

- `tmp_path` siempre para DBs/ficheros; jamás contaminar el árbol
  (`test_no_unwanted_artifacts_in_worktree` lo fija).
- `ACORE_DATA_DIR` + `AcademicApp(Settings.load())` para repositorios
  reales (patrón F4.2, reutilizado en F13-ext servicio).
- Tiempos inyectados (`now_ms`, `created=`, `dtstamp=`); `time.time()` solo
  como default con override en tests.
- Aleatoriedad con `random.Random(seed)` explícita y parametrizada.
- UI Qt solo offscreen (`QT_QPA_PLATFORM=offscreen`, fijado en CI).

## 5. Determinismo

- Seeds fijos; nada de `random` global, hora, locale, red, rutas
  absolutas ni orden de filesystem en aserciones.
- Hash-seed: cada proceso CI arranca con seed aleatorio; 4 celdas verdes
  = evidencia de independencia. Verificación local multiseed del subset
  rápido en el gate D5.
- Digests SHA-256 sobre serialización canónica (`sort_keys`); goldens
  byte a byte con checkout LF (`.gitattributes eol=lf`).

## 6. Limitaciones ambientales (únicas, explícitas)

Tabla en `tests/conftest.py` (fijada por `test_d4_pipeline.py`):

1. `test_html_corpus` en linux → `xfail(strict=True)`: el golden
   `html_cp1252` depende del wheel lxml (manylinux ≠ Windows).
2. `test_document_symlink_escape_refused` → `skip` solo si el SO niega
   symlinks (sonda real de capacidad).

Más `integration`/`external` con sonda (ngspice, Stirling, Java).
Nada más se salta, silencia o excluye.

## 7. Matriz de cobertura (baseline pre-D5: 138 ficheros, 4598 tests)

Área → ficheros → tests → tipo → suite → CI (`not external` salvo ind.):

| Área | Ficheros | Tests | Tipo | CI |
|---|---|---:|:---:|:---:|
| Dominio F1 (identidad, cantidades, resultados, config, app) | 9 | 49 | unit | sí |
| Grading/equivalencia Gestion | 2 | 820 | golden paramétrico | sí |
| Persistencia/migraciones | 6 | 49 | integration | sí |
| Recursos F2 (CAS, FTS, ingesta, storage, provenance) | 11 | 63 | integration | sí |
| Conversor F3/F3-ext (AST, HTML, math, tablas, PDF/DOCX/IPYNB, goldens) | 9 | 84 | unit+golden | sí |
| Académico F4/F4.1/F4.2 (dominio, knowledge, gestión, calendario/ICS, seguridad) | 16 | 170 | unit+integration | sí |
| Authoring F5 | 5 | 27 | unit+integration | sí |
| Engineering F6/F7 (unidades, MNA, transitorio, control, GUM) | 14 | 333 | unit+ngspice-probe | sí |
| Electrónica F8 (solver, AC, no-lineal, RF, digital, lab, metrología) | 41 | 2444 | unit+golden+probe | sí |
| Assessment F9 | 3 | 71 | unit+integration | sí |
| Explicable E0–E0.4 (trazas, replay, certificación) | 7 | 364 | unit+golden | sí |
| App F15/UI (facade, dashboard, Qt offscreen) | 7 | 77 | integration/UI | sí |
| Sync F13-ext (motor 12 + servicio D5) | 2 | 24 | unit+integration | sí |
| Suite D4/D5 (arquitectura, pipeline, contratos) | 3 | 30 | contrato | sí |
| Perf (presupuesto temporal) | 3 | 5 | perf | sí |
| External/misc (Stirling, reproducibilidad) | 2 | 7 | external+repro | parcial |

Conversor §4 D5: headings/párrafos/listas (`TestHTML`, `test_headings_paragraphs_lists`),
enlaces/imágenes (`test_links_exact_and_dangerous`, `test_images_become_cas_references`,
`test_data_uri_and_remote`), tablas (`test_table_grid_equivalence`, `TestTabular`,
`test_rowspan_colspan_semantic`, `test_empty_cells_and_corrupt_table`),
fórmulas (`TestMath`, `test_mathml_*`, `test_omml_*`), código (`code_block` mermaid,
`test_code_table_detected`), Unicode/entidades (`test_encoding_vectors`,
`test_mathml_simple_complex_unicode`, escapes), malformado
(`test_malformed_html_never_drops_text`, `test_malformed_and_security`),
límites (`test_huge_*`, `test_csv_large_truncated`, `test_zip_bomb_guards`,
`test_cells_no_execution`), determinismo (`test_digest_*`, goldens,
`test_batch_deterministic_errors`), seguridad (`TestAssetsSecurity`,
`test_no_scripts_or_handlers_survive`, `javascript:*`).

## 8. Decisiones D5 (auditoría)

- **Sin eliminaciones**: cada fichero cubre capa/contrato distinto
  (p.ej. `test_schedule` = dominio Series vs `test_f4_schedule` =
  servicio calendario+ICS; `test_results` = escalas vs `test_grading` =
  equivalencia Gestion). Eliminar perdería cobertura.
- **Sin tests redundantes nuevos**: solo huecos reales → +12 servicio
  F13-ext (§5 D5: identidad, adaptadores, persistencia, aplicación
  remota, límites `AC-SYN-001`) y +8 contratos D5 (AST F13-ext/D4,
  pureza dominio sync, markers, perf).
- **Markers añadidos** (`arch`, `repro`, `perf` + registro `perf`):
  metadato aditivo, cero cambio de comportamiento, CI intacto
  (sigue ejecutando lo mismo).
- **Perf**: clasificado, NO excluido del gate, umbrales intactos.
  El flake `test_perf_academic_scale` (D4 run #4, runner lento) queda
  documentado, no enmascarado.
- **Código certificado tocado**: nada. Solo tests + `pyproject`
  (registro de marker) + docs.
