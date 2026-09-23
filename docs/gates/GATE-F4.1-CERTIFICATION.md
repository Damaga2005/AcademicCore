# GATE-F4.1-CERTIFICATION — cierre F4.1

Fecha: 2026-09-23 · Rama `claude/new-session-wn0twl`

## G. Decisión

```text
F4.1 NOT CERTIFIED
```

Bloqueos (y solo estos):

1. **Migración REAL no ejecutada.** La instalación real de Gestion-Academica
   (`academico.db`, `documentos/`) no es accesible desde el entorno de cierre:
   no está en el contenedor, ni en ningún repositorio (`.gitignore` de Gestion),
   ni en el Google Drive conectado (búsqueda: solo `Thumbs.db` de Windows).
   Según la auditoría F4.0 vive en el PC Windows del usuario (Syncthing).
   No se ha certificado con sustitutos (seed/fixtures), por regla.
   **Para cerrar:** ejecutar en esa máquina el arnés
   `python -m academic_core.application.gestion_certification` y
   `pytest tests/test_f4_real_*.py` con `ACORE_GESTION_REAL_DB/_DOCS`
   (runbook: `docs/migration/GESTION-F4.1-MIGRATION.md`). Si su veredicto es
   PASS en los 11 criterios y la suite queda como abajo, F4.1 se certifica.
2. **F3 golden `test_html_corpus` (`html_cp1252`) falla**, idéntico en baseline
   y final. Causa raíz demostrada: el golden depende de la versión de **libxml2**
   embebida en el wheel de lxml. Con libxml2 2.14.6 (este entorno, lxml 6.1.3 =
   versión del lock) el texto suelto antes de `<p>` queda en `<body>` y el parser
   lo recorta (`"Prix: 2,2 €"`); el digest esperado corresponde exactamente a
   `"Prix: 2,2 € "` (verificado por reconstrucción del digest), es decir, a una
   libxml2 que envuelve el texto en un `<p>` implícito. PREEXISTENTE, ajeno a
   F4.1; no se modifica F3 para ocultarlo. Resolverlo (normalizar espacios en el
   parser HTML o fijar libxml2) es trabajo de F3.

## A. Baseline

| | |
|---|---|
| Baseline | `31ad044` (worktree limpio) |
| HEAD implementación previa | `b162e13` |
| HEAD código final probado | `7cf1c66` (+ `eafa876` y este commit: solo docs) |
| Rama / árbol | `claude/new-session-wn0twl`, limpio y sincronizado con `origin` |

## B. Datos reales

| Elemento | Estado |
|---|---|
| hash BD fuente real | NO DISPONIBLE (ver G.1) |
| manifest de documentos reales | NO DISPONIBLE |
| conteos entrada/salida reales | NO DISPONIBLE — los genera el arnés (`inventory`, `no_loss`) |

Evidencia sustitutiva (NO certifica): BD de referencia generada por el propio
código de Gestion@187a614 → arnés completo PASS en los 11 criterios, SHA-256
fuente `c675d5ef…` idéntico antes/después; 54 asignaturas, 61 vínculos de
profesorado → 61 identidades (9 homónimos NO fusionados), 65 esquemas,
164 componentes, 81 recursos (50 Wuolah, 31 Studocu), 0 discrepancias de
evaluación.

## C. Migración (código)

dry-run sin escrituras · snapshot obligatorio · una transacción · validación
posterior · idempotente (2ª ejecución: 0 nuevas) · cancelable · digest
reproducible · fuente abierta en solo lectura. Cambios de cierre:
- **Profesores**: se fusionan solo con evidencia (mismo nombre + mismo e-mail
  no vacío); si no, identidad propia derivada del id estable de Gestion;
  nunca se reutiliza por nombre un profesor existente (`test_f4_professor_identity_collision`).
- `legacy_payloads.migration_version` (migración 013) junto a entidad, id,
  payload, motivo y fase destino (`deferred_to`).
- Backup: `restore_zip` verificado (antes solo crear/verificar).
- Arnés de certificación real + `test_f4_real_*` (6 ficheros).

## D. Tests (HEAD `7cf1c66`, `pytest -o addopts="" -q`, incluye `slow`)

| Suite | Resultado |
|---|---|
| Completa | **1 failed, 4407 passed, 144 skipped** (25:36) |
| F4.1 (`test_f4_*`) | 994 tests: todos pasan salvo 10 variantes `[real]` saltadas (sin datos reales) |
| F3/F3.1 | todo verde salvo `test_html_corpus` (G.2) |
| Seguridad (`test_f4_security`) | 65 passed |
| Determinismo | `PYTHONHASHSEED` 0/11/2024/random: mismo digest de informe y estado |

`pytest -q` con addopts por defecto usa la misma colección y configuración
(solo cambia la verbosidad); no se volvió a ejecutar por separado.

## E. Diferencias baseline → final (comparación test a test por JUnit)

| Clase | Tests |
|---|---|
| PREEXISTENTE | `test_f3_golden::test_html_corpus` (FAIL en ambos, mismo mensaje y digests) |
| REGRESIÓN | ninguna |
| NUEVO Y JUSTIFICADO | 994 tests F4.1 (10 skips `[real]`) |
| TEST ACTUALIZADO CORRECTAMENTE | `test_persistence` y `test_migration`: nº de migraciones 11 → 13 (012 y 013 aditivas, se dividen correctamente); ningún assert eliminado |
| Skips | 134 del baseline (ngspice/reportlab/Stirling ausentes) + 10 `[real]` |

## Matriz

| Criterio | Evidencia | Resultado |
|---|---|---|
| baseline | `31ad044` + suite JUnit | PASS |
| dominio | `test_f4_domain` | PASS |
| evaluación real | arnés `evaluation_real` | FAIL (no ejecutado sobre datos reales) |
| profesores | collision test | PASS |
| documentos | hashes reales | FAIL (no ejecutado) |
| grupos | mapping real | FAIL (no ejecutado) |
| recursos | conteos reales | FAIL (no ejecutado) |
| tareas | conteos/relaciones reales | FAIL (no ejecutado) |
| horarios | conteos/relaciones reales | FAIL (no ejecutado) |
| espacios | mapping real | FAIL (no ejecutado) |
| Home | consulta real | FAIL (no ejecutado) |
| Carrera | consulta real | FAIL (no ejecutado) |
| backup | verify + restore (tests + referencia) | PASS |
| idempotencia | segunda ejecución (tests + referencia) | PASS |
| determinismo | 4 hash seeds | PASS |
| seguridad | AST/tests | PASS |
| regresión | comparación baseline | PASS (0 regresiones; fallo F3 preexistente) |
| documentación | este gate, runbook, ADRs | PASS |

Los criterios «reales» pasan en la BD de referencia y en el sintético; se
marcan FAIL porque la regla exige los datos reales del usuario.

## F. Riesgos residuales

- Sin evidencia de e-mail, un mismo profesor en varias asignaturas aparece como
  varias identidades (seguro y reversible vía `legacy_map`; fusionar requiere
  una decisión humana posterior).
- Guías en Markdown: el parser F3 colapsa saltos de línea simples. Impacto real
  nulo en Gestion: su importador de guías solo aceptaba PDF
  (`test_analizar_rechaza_documento_no_pdf`), y el PDF conserva líneas.
- `test_html_corpus` hasta que F3 elimine la dependencia de libxml2.
