# F13 — OneDrive / Cloud Sync completo (offline-first)

> **Fase:** F13 · **Base:** F13-ext certificada (`f13ext-sync/1`) · **Estrategia:** LWW + log, sin CRDT, sin segundo motor

## 1. Relación F13-ext / F13

```text
F13 = F13-ext + cloud/offline coordination
```

- Motor reutilizado sin cambios: `domain/sync.py` (EXPORT → CANONICAL →
  COMPARE → CLASSIFY → LWW → APPLY → VERIFY → SYNC LOG).
- F13-ext aporta: protocolo `f13ext-sync/1`, identidad de dispositivo,
  versión `(version_ms, version_device)`, digest canónico, tombstones,
  idempotencia, `sync_state`, `sync_log`, verificación por convergencia,
  límites y `FileTransport`.
- F13 añade **solo**: transporte cloud desacoplado + coordinación
  offline-first + estado runtime por recurso. Ninguna responsabilidad del
  motor se duplica.

## 2. Arquitectura

```text
                    CloudSyncService (application/cloud_sync.py)
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
              SyncService      CloudTransport     SyncLogRepository
              (F13-ext)        (infraestructura)  (+ sync_status)
                    │                │                │
                    │     ┌──────────┴──────────┐     │
                    │     │                     │     │
                    │  MemoryCloud        OneDriveFolder   │
                    │  (tests)            (carpeta local)  │
                    │                     │     │
                    └─────────────────────┼─────┘
                                          │
                                     Local DB
```

El dominio no conoce OneDrive, Graph, HTTP, tokens, credenciales ni rutas
cloud. La integración cloud vive en `infrastructure/cloud_transport.py`.

Se mantiene:

```text
FileTransport         ← F13-ext existente (2 PCs por fichero)
MemoryCloudTransport  ← F13, fake/in-memory para contrato (tests)
OneDriveFolderTransport ← F13, carpeta local de OneDrive (sin red)
```

## 3. Transporte cloud

Contrato (`CloudTransport.read/write`):

- `read() → dict | None`: snapshot remoto validado o `None` si ausente
  (primer push). Valida esquema, protocolo, dispositivo, digests y límites
  antes de devolver; rechaza con `AC-SYN-001` sin tocar estado válido.
- `write(snapshot, expected_remote_digest=None)`: valida, comprueba tamaño
  (8 MB snapshot, 256 KB payload vía F13-ext, 10k records) y escribe de
  forma atómica (carpeta: tmp + replace). `expected_remote_digest` permite
  detectar escritura concurrente (`AC-SYN-004`).
- Errores tipados (sin secretos en mensajes):
  `AC-SYN-002` offline/no disponible, `AC-SYN-003` auth/permiso,
  `AC-SYN-004` conflicto de escritura, `AC-SYN-001` validación.

Sin dependencias nuevas: solo `pathlib` + `json` + reutilización de
`S.import_snapshot` y límites F13-ext. Cero `requests/urllib/socket/http`.

## 4. Offline-first

```text
CAMBIO LOCAL → persistencia local → sync pendiente → ¿cloud disponible?
  SÍ → sincroniza (LWW) → synced/conflict
  NO → pendiente/offline → reintento idempotente
```

- Sin conexión los cambios locales permanecen y la app académica funciona.
- Nada se marca como sincronizado sin confirmación de escritura.
- Reintentar es idempotente (`sync(S',R)=S'`, verificado por F13-ext).
- Nunca: `error cloud → rollback destructivo local`.

## 5. Estado de sincronización

Tabla aditiva `sync_status(resource_id, status, updated_ms, detail)` +
`cloud_sync_meta(last_sync_ms)` (migración 021). Valores:
`synced | pending | offline | conflict | error`.

- `conflict`: LWW resolvió un conflicto (queda en `sync_log` con ganador).
- Runtime separado: `sync_status` nunca entra en `canonical_digest`.
- `pending/offline`: push diferido, reintentable.

## 6. Versionado y conflictos

Reutiliza `compare_version` F13-ext: mayor `ms` gana; empate → mayor
`device_id` lexicográfico; igualdad total → `unchanged`; mismo digest con
versiones distintas → `same` (converge a versión mayor).

Cada conflicto registra en `sync_log`: recurso, versión local/remota,
digest antes/después, decisión (`local-wins/remote-wins/same`), ganador,
resultado y evento determinista (`event_id` hash). Sin merges semánticos.

## 7. Integridad

Pipeline ante datos remotos:

```text
READ → SIZE LIMIT → SCHEMA → PROTOCOL → DEVICE → DIGEST → SYNC ENGINE →
APPLY (solo ganadores remotos) → VERIFY (convergencia) → WRITE (si cambió) →
SYNC LOG + STATUS
```

Si algo falla, el estado local válido queda intacto (`synchronize` valida
antes de aplicar; el coordinador marca `error` sin escribir).

Probado: JSON inválido, snapshot corrupto, digest incorrecto, protocolo
incompatible, payload excesivo, escritura interrumpida (tmp + replace),
offline, auth denegado, reintento tras error.

## 8. Seguridad

- Sin `eval/exec/compile/subprocess/os.system/shell=True/pickle` (AST en
  `test_d5_contracts.py`, extendido a F13).
- SQL parametrizado (`?`); snapshots con límites y verificación de digest.
- Secretos: nunca en snapshots, `sync_log`, `sync_status` ni excepciones
  (test `no_secrets`, redacción D2 en logs).
- El LLM de F12 no participa en sincronización.
- Credenciales reales (OAuth/Graph) fuera del gate determinista: la
  integración real exige credenciales del usuario y queda documentada como
  limitación (no se finge E2E contra OneDrive).

## 9. Datos

Alcance inicial = F13-ext: `preference` (`pref:<f42.key>`, 6 claves),
`saved_search` (`saved:<kind>:<ref>`), `quick_note` (`note:<slug>`), con
tombstones. Excluidos: caches, recents/LRU, secretos, credenciales,
documentos/assessments/engineering (necesitan versionado propio; F13 no es
"sincronizar todo").

## 10. Persistencia

Migración `021_cloud_sync.sql` aditiva, incremental y rerunnable
(`IF NOT EXISTS`): `sync_status` + `cloud_sync_meta`. No toca tablas
certificadas. Pins actualizados legítimamente: `test_migration` 20→21,
`test_persistence` +21.

## 11. Límites reales

1. Reloj wall-clock (LWW determinista, sin garantía causal; HLC futuro).
2. Tombstones sin auto-GC (retención; purga manual futura).
3. Sin E2E real contra OneDrive/Graph en este gate (sin credenciales; el
   adapter real queda separado y sin certificar).
4. Carpeta OneDrive = sincronización del SO; conflictos de escritura
   concurrente se detectan vía `expected_remote_digest`, no se fusionan.
5. CI real pendiente de push (ver gate); evidencia local incluida.
