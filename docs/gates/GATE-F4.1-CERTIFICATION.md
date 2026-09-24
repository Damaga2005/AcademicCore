# GATE-F4.1-CERTIFICATION — cierre F4.1

Fecha: 2026-09-24 · Rama `f4.1-closure`

## G. Decisión

```text
F4.1 CERTIFIED
```

## A. Baseline

| | |
|---|---|
| Baseline | `31ad044` (worktree limpio) |
| HEAD implementación previa | `49ad266` (harness real + runbook + política de profesores) |
| HEAD código final probado | este commit (cierre real: identidad + relaciones + gate) |
| Rama / árbol | `f4.1-closure`, limpio salvo `.claude/` untracked externo |

## B. Datos reales

| Elemento | Estado |
|---|---|
| hash BD fuente real | `280CB63D…AE567A` (28 438 528 bytes), idéntico antes/después de TODA la sesión |
| manifest de documentos reales | `F4.1-source-document-manifest.csv` (672 filas): reverificado 672/672 OK el 2026-09-24 |
| manifest físico del arnés | 672 ficheros, 1 303 240 023 bytes, digest `9833b849…` idéntico antes/después |
| inventario real | 4 años, 8 cuatrimestres, 54 asignaturas, 61 profesores, 65 esquemas, 168 componentes, 2 bloques, 162 apartados, 672 documentos, 7407 páginas, 185 grupos, 229 relaciones espacio-documento, 7 espacios, 81 recursos, 13 tareas, 9 horarios, 1 prerrequisito — total 9134 filas, 18/18 integridad OK |
| dry-run real | lossless, 0 errores de bloqueo, evaluación 54/54 sin diferencias, digest `267fbc86…` reproducible entre procesos |
| apply real | lossless, 0 errores, 0 fallos de validación, digest `76ee3824…`, snapshot SHA-256 `b0a89892…` |
| rerun real | 0 migrados, digest `7c34a3f0…`, 0 fallos |

Evidencia previa (NO certifica sola): BD de referencia generada por el propio
código de Gestion@187a614 → arnés completo PASS en los 11 criterios.

## C. Migración (código)

dry-run sin escrituras · snapshot obligatorio · una transacción · validación
posterior · idempotente (2ª ejecución: 0 nuevas) · cancelable · digest
reproducible · fuente abierta en solo lectura. Cambios de cierre:
- **Profesores**: se fusionan solo con evidencia (mismo nombre + mismo e-mail
  no vacío); si no, identidad propia derivada del id estable de Gestion;
  nunca se reutiliza por nombre un profesor existente (`test_f4_professor_identity_collision`).
  En datos reales: 61 filas → 61 identidades, 0 fusiones, 7 homónimos separados.
- **Identidad documental (cierre real)**: `ruta_local` es provenance; la
  identidad es nombre+tamaño+SHA-256+evidencia relacional
  (`resolve_document_by_identity`, migrador `gestion-migration/3`). Las 41
  discrepancias `teoria`↔`otros` se resuelven sin tocar la fuente; la
  evidencia por documento vive en `report.identity_resolutions`
  (digest `6571dd7a…`).
- **Relaciones duplicadas**: mismo (espacio, recurso) repetido se preserva
  explícitamente (`duplicate relation to shared resource`, con target) en vez
  de REPLACE silencioso; 2 filas reales así clasificadas, 0 pérdidas.
- `legacy_payloads.migration_version` (migración 013) junto a entidad, id,
  payload, motivo y fase destino (`deferred_to`).
- Backup: `restore_zip` verificado (antes solo crear/verificar).
- Arnés de certificación real + `test_f4_real_*` (6 ficheros).

## D. Tests (HEAD este commit, `pytest -o addopts="" -q`, incluye `slow`)

| Suite | Resultado |
|---|---|
| Completa | **12 failed, 4530 passed, 12 skipped, 2 errors** (1:00:46) |
| F4.1 (`test_f4_*`) | todo verde, incluidos 3 tests nuevos de identidad/relaciones; 21/21 `test_f4_real_*` con datos reales |
| F3/F3.1 | todo verde salvo `test_html_corpus` (preexistente libxml2, §G anterior) |
| Seguridad (`test_f4_security`) | 64 passed; `test_document_symlink_escape_refused` falla SOLO en Windows sin privilegio de symlink (WinError 1314 en `os.symlink` del propio test, antes de tocar código; ambiental) |
| Determinismo | `PYTHONHASHSEED` 0/11/2024/random: mismo digest de informe y estado; dry digest `267fbc86…` idéntico entre procesos |
| Errores pytest-qt | 2 en teardown (`ValueError: environment variable > 32767 chars`, límite de Windows; ambientales) |

`pytest -q` con addopts por defecto usa la misma colección y configuración
(solo cambia la verbosidad); no se volvió a ejecutar por separado.

## E. Diferencias baseline → final (comparación test a test)

| Clase | Tests |
|---|---|
| PREEXISTENTE | 11 CRLF (`test_e0_g01`, `test_q4_g01`×6, `test_q5_g01`×4) + `test_html_corpus[html_cp1252]` (libxml2): FAIL idéntico en `31ad044` y final |
| AMBIENTAL (no atribuible a F4.1) | `test_document_symlink_escape_refused` (WinError 1314 en `os.symlink` del test) + 2 errores teardown pytest-qt (límite 32767 chars de Windows) |
| REGRESIÓN | ninguna |
| NUEVO Y JUSTIFICADO | migrador `gestion-migration/3`, `identity_resolutions`, `_doc_resource`, 3 tests nuevos; 21/21 `test_f4_real_*` con datos reales |
| Skips | 12 (Stirling/ngspice/reportlab ausentes, `[real]` sin env) |

## Matriz

| Criterio | Evidencia | Resultado |
|---|---|---|
| baseline | `31ad044` + suite completa | PASS |
| dominio | `test_f4_domain` | PASS |
| evaluación real | arnés `evaluation_real`: 54/54, 0 diferencias | PASS |
| profesores | 61 filas → 61 identidades, 7 homónimos separados, 0 fusiones | PASS |
| documentos | 662 verificados SHA-256==CAS, 0 mismatches, 10 duplicados preservados | PASS |
| grupos | 185/185 migrados, relaciones verificadas | PASS |
| recursos | 81/81 (50 Wuolah, 31 Studocu) | PASS |
| tareas | 13/13 + conflictos verificados | PASS |
| horarios | 9/9 series verificadas | PASS |
| espacios | 7/7 + 229/229 relaciones (2 duplicadas clasificadas, 0 pérdidas) | PASS |
| Home | solo `cursando` en cuatrimestre actual | PASS |
| Carrera | buckets == estados fuente (54/54) | PASS |
| backup | 661 blobs, verify == restore, sujetos idénticos | PASS |
| idempotencia | segunda ejecución: 0 migrados, 0 fallos | PASS |
| determinismo | 4 hash seeds iguales | PASS |
| seguridad | AST/tests, 64 passed | PASS |
| regresión | 0 regresiones (11 CRLF + 1 libxml2 preexistentes; resto ambiental) | PASS |
| documentación | este gate, runbook, ADRs | PASS |

41 discrepancias de ruta: todas `mismo documento migrado` por identidad
(nombre+tamaño+SHA-256+asignatura/grupo), evidencia `6571dd7a…`, fuente intacta.

## F. Riesgos residuales

- Sin evidencia de e-mail, un mismo profesor en varias asignaturas aparece como
  varias identidades (seguro y reversible vía `legacy_map`; fusionar requiere
  una decisión humana posterior).
- Guías en Markdown: el parser F3 colapsa saltos de línea simples. Impacto real
  nulo en Gestion: su importador de guías solo aceptaba PDF
  (`test_analizar_rechaza_documento_no_pdf`), y el PDF conserva líneas.
- `test_html_corpus` hasta que F3 elimine la dependencia de libxml2.
