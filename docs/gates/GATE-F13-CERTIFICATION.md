# GATE-F13-CERTIFICATION — F13 OneDrive / Cloud Sync (implementación)

> **FASE:** F13 — OneDrive / Cloud Sync completo (offline-first).
> **MODO:** implementación + tests + regresión + seguridad (CI real pendiente).
> **BASELINE:** `main @ e8d8754` (`docs(f12): certificar con run 36336990034 verde`);
> working tree clean al inicio. Sin ramas permanentes.
> **VEREDICTO: NO CERTIFICADA — pendiente CI real (§12). No usar como
> evidencia de certificación.**

## 1. Baseline, HEAD, commits, archivos

| | |
|---|---|
| baseline | `e8d8754` |
| HEAD (implementación) | pendiente de commit (ver §13) |
| migración | `021_cloud_sync.sql` registrada en `infrastructure/database.py:_MIGRATIONS` |
| producción | `infrastructure/cloud_transport.py` (Memory + OneDriveFolder, sin red), `application/cloud_sync.py` (CloudSyncService sobre F13-ext), `infrastructure/sync_store.py` (+sync_status/meta, aditivo), `infrastructure/__init__.py` (exports), `application/facade.py` (wiring cloud_sync), `infrastructure/database.py` (021), `docs/specs/ERROR-CODES.md` (AC-SYN-002/003/004) |
| tests | `tests/test_f13_cloud_sync.py` (9 contractuales F13) |
| docs | `docs/architecture/F13-CLOUD-SYNC.md` (este gate la describe) |

Contrato conservado: `domain/sync.py` intacto (cero cambios al motor LWW).

## 2. Contrato

`F13 = F13-ext + cloud/offline coordination`. Pipeline certificado
F13-ext reutilizado vía `SyncService.synchronize` (incluye VERIFY interno).
Transporte cloud desacoplado (`read/write`), offline-first, estados
`synced/pending/offline/conflict/error` en tabla aditiva (fuera de digests).

## 3. Tests específicos (9/9 verdes local)

| Test | Cubre (prompt §14) |
|---|---|
| first_push_when_remote_absent | transporte: ausencia → push; estado synced |
| offline_keeps_local_and_marks_pending | offline-first: cambio sobrevive, pendiente, reintento idempotente |
| bidirectional_remote_wins | versionado: solo remoto cambia; convergencia |
| conflict_is_deterministic_and_logged | versionado/conflictos: LWW + 8 campos de log |
| corrupt_remote_does_not_destroy_local | integridad: corrupto → error, local intacto |
| tombstone_propagates | tombstones: sin resurrección corrupta, idempotencia |
| no_secrets_in_snapshot_or_log | seguridad: sin tokens/secretos |
| onedrive_folder_roundtrip_and_missing | transporte carpeta: ausencia, round-trip, idempotencia |
| auth_and_oversize_are_errors | transporte: auth denegado, límites |

TDD: test creado primero, RED 9/9 `ModuleNotFoundError` verificado, luego
GREEN mínimo, REFACTOR (limpieza de imports).

## 4. Regresión (verde local)

- `test_f13ext_sync` + `test_f13ext_service` + `test_f13_cloud_sync` +
  `test_d5_contracts` + `test_architecture` + `test_migration` +
  `test_persistence`: verde.
- `test_f4_security` (códigos únicos/documentados) + `test_d4_pipeline` +
  `test_f15_app` + `test_application` + `test_config`: verde (1 skip
  ambiental symlink si el SO lo niega).
- Suite completa `not external` no ejecutada entera por tiempo; subconjunto
  representativo verde; cambios solo aditivos (2 ficheros nuevos + métodos
  nuevos + migración aditiva + wiring + pins legítimos 20→21).

## 5. Seguridad

- AST (`test_d5_contracts`, extendido a F13): sin `eval/exec/compile/
  __import__/shell=True`, sin `pickle/marshal/shelve/subprocess/socket/
  urllib/http/requests/flask/sqlalchemy/PySide6/ctypes/os/threading` en los
  6 ficheros sync.
- SQL solo `?`; límites 8 MB/256 KB/10k + digest antes de aplicar.
- Secretos nunca en snapshots/logs/status (test específico + D2 redact).
- `to_ui_error` hereda `AC-SYN-002/003/004` vía `AcademicCoreError`.

## 6. Migraciones

`021_cloud_sync.sql` aditiva (`CREATE TABLE IF NOT EXISTS sync_status`,
`cloud_sync_meta`), rerunnable según patrón, compatible con BDs existentes.
Pins legítimos: `test_migration 20→21`, `test_persistence +21` (precedente
F4.2/D5).

## 7. E2E real

- 2 BDs + `MemoryCloudTransport` / carpeta OneDrive local: verde en tests.
- E2E real contra OneDrive/Graph con credenciales: **NO existe** (sin
  credenciales en desarrollo; no se finge). Limitación declarada, no
  certificación.

## 8. Limitaciones

Ver `F13-CLOUD-SYNC.md` §11 (reloj wall-clock, tombstones sin GC, sin E2E
Graph real, carpeta = cliente SO, CI pendiente).

## 9. CI real

**Pendiente.** No se declara certificación sin evidencia CI real (regla 17
del prompt). Tras push a `main`, ejecutar el workflow canónico
(`pytest -m "not external"`, 4 celdas + package) sin bypasses y registrar
aquí el run verde antes de marcar F13 CERTIFICADA y F16 SIGUIENTE.

## 10. Criterios de aceptación (§21 del prompt)

- [x] cloud transport según contrato real (carpeta + fake separado)
- [x] F13-ext reutilizado sin segundo motor (`domain/sync.py` intacto)
- [x] offline-first funcional (pending/offline + reintento idempotente)
- [x] cambios locales sobreviven sin conexión
- [x] sincronización bidireccional (LWW ambos sentidos)
- [x] versionado determinista (mismo input+estado+config+protocolo = misma decisión)
- [x] conflictos deterministas y auditables (sync_log)
- [x] tombstones (propagación F13-ext; sin resurrección)
- [x] idempotencia (re-sync estable)
- [x] snapshots validados antes de aplicar
- [x] corrupción no destruye estado válido
- [x] errores cloud controlados (offline/auth/conflict/límites)
- [x] secretos protegidos
- [x] sin ejecución arbitraria / deserialización insegura
- [x] migraciones correctas (021 aditiva + pins)
- [x] tests F13 verdes (9/9 local)
- [x] regresiones relevantes verdes (local)
- [x] documentación completa (F13-CLOUD-SYNC + ERROR-CODES)
- [ ] gate completo con CI real (**pendiente**)
- [ ] CI real verde (**pendiente de push**)
- [ ] roadmap actualizado (**pendiente de CI**: F13 sigue SIGUIENTE)
- [x] F16 permanece como única fase pendiente tras F13

## 11. Veredicto

**F13 IMPLEMENTADA, NO CERTIFICADA.** Siguiente paso: push + CI real verde
+ actualizar este gate con el run + marcar `F13 CERTIFICADA, F16 SIGUIENTE`
en ROADMAP/CHANGELOG. F16 fuera de alcance (no implementada aquí).
