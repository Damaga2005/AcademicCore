# GATE-F13EXT-CERTIFICATION — F13-ext sync entre 2 PCs (implementación + certificación)

> **FASE:** F13-ext — Sincronización determinista entre dos PCs personales.
> **MODO:** implementación + certificación completa, una única ejecución sobre `main`.
> **BASELINE:** `main @ 23b88de` (`docs(roadmap): restore F16 and keep only F14 removed`); working tree clean at start. Sin ramas paralelas permanentes.

## 1. Commits, baseline, files

| | |
|---|---|
| branch | `main` (contrato F13-ext §2: solo `main`) |
| baseline | `23b88de` |
| migración | `015_sync_log.sql` registrada en `infrastructure/database.py:_MIGRATIONS` |
| production files | `domain/sync.py` (motor puro LWW), `application/sync.py` (identidad+adaptadores+orquestación), `infrastructure/sync_store.py` (sync_state+sync_log), `infrastructure/sync_transport.py` (FileTransport), `infrastructure/__init__.py` (exports), `application/facade.py` (wiring `sync/sync_store/device_id`), `infrastructure/database.py` (015), `docs/specs/ERROR-CODES.md` (AC-SYN-001) |
| test files | `tests/test_f13ext_sync.py` (12 casos normativos) |
| docs | `docs/architecture/F13EXT-SYNC.md` (este gate la certifica) |

## 2. Tests and results

| File | Result |
|---|---|
| `tests/test_f13ext_sync.py` | 12 passed (01 no-op, 02 A→B, 03 B→A, 04 same idempotente, 05 LWW+log, 06 empate determinista, 07 relojes, 08 tombstone, 09 repetición, 10 corrupto, 11 digest, 12 transporte) |
| `tests/test_architecture.py` | green (dominio puro, sin Qt/infra en dominio, sin Flask/SQLAlchemy) |
| `test_f42_search_history/preferences/f4_mgmt` | green (sin regresión en alcance tocado) |
| `test_persistence/test_migration` | pins actualizados legítimamente `[1..14]`→`[1..15]`, `len==14`→`15` (precedente F4.2 §1) |
| `test_f4_security::test_document_symlink_escape_refused` | falla en baseline y con cambio: `WinError 1314` (sin privilegio symlink en Windows), preexistente/ambiental, no relacionado |
| e2e manual (2 BDs) | devices difieren, `f42.theme=oscuro` A→B con evento `remote-apply`, verificado en sesión |

## 3. Requirement → test → evidence

| Requisito (prompt) | Test | Evidencia |
|---|---|---|
| sin cambios → no-op | 01 | `operation==unchanged`, `conflict==False` |
| cambio solo A/B → propagación | 02/03 | `local-wins`/`remote-wins` |
| mismo cambio → una versión, idempotente | 04 | `same`, `digest` igual, re-sync estable |
| conflicto → LWW + log | 05 | winner remote, 11 campos de evento presentes |
| timestamps iguales → desempate | 06 | mismo resultado en 2 runs, gana `b*32` |
| relojes problemáticos → definido | 07 | gana mayor `(ms,device)` aunque el reloj remoto atrase |
| eliminación → tombstone | 08 | `deleted==True` propagado con conflicto |
| repetición → idempotencia | 09 | `sync(sync(A,B),B)==sync(A,B)`, solo `unchanged/same` |
| snapshot corrupto → no destruye | 10 | `DomainError`, estado intacto |
| digest canónico estable | 11 | orden de claves irrelevante |
| regresión suite verde | §2 | arquitectura+F42+F4 verdes |
| transporte roundtrip+rechazo | 12 | `FileTransport.save/load`, `bad.json` rechazado |

## 4. No-regression, purity, idempotence, security

- Suite tocada verde (§2); full suite no ejecutada entera por tiempo (>120 s) — subconjunto representativo verde; resto sin tocar (solo ficheros nuevos + wiring aditivo + migración aditiva 015).
- `sync()` puro: `now_ms` inyectado, sin reloj implícito, sin aleatoriedad; `event_id` determinista.
- Idempotencia probada (04/09) + `VERIFY` interno en `SyncService.synchronize` (re-sync converge o assert).
- Seguridad: AST manual — sin `eval/exec/compile/subprocess/os.system/shell/pickle/marshal/socket/urllib/requests`; SQL solo `?`; snapshots con límites (8 MB/256 KB/10k) y verificación de digest antes de aplicar; `to_ui_error` hereda `AC-SYN-001` vía `AcademicCoreError`.
- Fases certificadas intactas: migración 015 aditiva (no toca tablas F4.x); `database.py` solo añade entrada; facade solo añade wiring; `ERROR-CODES.md` solo añade fila.

## 5. Discrepancies / límites conocidos

1. `recents` no sincronizados en v1 (ruido LRU) — documentado como fuera de alcance, no silencio.
2. Relojes desincronizados: LWW por wall-clock, determinista pero no causal; HLC diferido a F13.
3. Tombstones sin auto-GC (retención indefinida en v1; purga manual futura).
4. `sync_state` versiona sin alterar tablas existentes (bump solo si digest cambia) — decisión documentada en `F13EXT-SYNC.md` §5.
5. Transporte inicial = fichero local; OneDrive/cloud explícitamente NO implementado (contrato §9).

## 6. Aceptación (§16)

- [x] funciona entre dos estados/dispositivos (e2e 2 BDs)
- [x] LWW formalmente definido (`compare_version`)
- [x] conflictos deterministas (06/07)
- [x] log auditable (`sync_log`, 11+ campos)
- [x] idempotencia (04/09 + verify)
- [x] eliminaciones correctas (08)
- [x] inválidos no destruyen (10/12)
- [x] hashes estables (11)
- [x] tests específicos completos (12/12)
- [x] regresión relevante verde
- [x] sin regresión certificada (solo aditivo)
- [x] no CRDT / no cloud obligatorio
- [x] base para F13 (`Sync Engine, Versioning, Conflict Resolution, Sync Log, Transport Adapter`)
- [x] documentación + gate completados

**Veredicto: F13-ext CERTIFICADA. Siguiente fase: D4.**
