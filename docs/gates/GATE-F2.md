# GATE F2 — Resource Engine: ✅ PASS (2026-09-12)

Suite: **81 passed** (41 F0/F1 regression + 40 F2). Sources untouched.

## A. Arquitectura
- [x] Resource Engine separado del Domain (ports en `domain/`, impl en
  `infrastructure/`+`resources/`+`application/ingest.py`)
- [x] Domain sin Qt / sin sqlite3 / sin FTS5 (`test_domain_knows_no_backends`, ast)
- [x] Adapters desacoplados (`adapter_for`, registry, `supports`)

## B. CAS
- [x] SHA-256 (`ba7816…` vector) · round-trip · dedup un blob · reopen
- [x] Integridad (`CorruptBlob`) · atomic (`os.replace`, tmp limpio en fallo)
- [x] Seguridad (hex-only, sin traversal) · streaming con tope (`TooLarge`)

## C. Resource identity
- [x] Estable across reindex+reopen · independiente de path y de FTS
- [x] Versiones con identidad propia bajo el mismo id estable

## D. Provenance
- [x] Origen/hash/adapter/timestamp/metadata/file+manual+generated/migration
- [x] Persistida y reabierta; cadena de parents en versiones

## E. Ingestion
- [x] Pipeline definido · import funcional · idempotencia (dupe, 1 versión)
- [x] Rollback ante fallo (zip refused → 0 filas; oversize → 0 filas)

## F. Versioning
- [x] Idéntico no crea versión · cambiado no destruye (v1 intacta, v2 nueva)

## G. FTS5
- [x] Index/search/filters(kind+subject)/rebuild determinista (set-equality)
- [x] Query compiler seguro (guiones entrecomillados, sin operadores inyectados)

## H. Security
- [x] Traversal · NUL · overwrite imposible · corrupt PDF · ZIP refused ·
  límites de tamaño · URLs rechazadas · fichero inexistente

## I. UI
- [x] Resources tab: import/list/inspect/search/reindex + offscreen smoke
  (`test_ui.py`, 5 tabs)

## J. Regression
- [x] F0 PASS · F1 PASS · F2 PASS (81/81 en una sola run)

Deuda registrada: F2-REPORT §Boundaries. **Fase 3 NO iniciada.**
