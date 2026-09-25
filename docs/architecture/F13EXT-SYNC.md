# F13-ext — Sincronización determinista entre 2 PCs

> **Fase:** F13-ext · **Protocolo:** `f13ext-sync/1` · **Estrategia:** last-write-wins + log · **No CRDT**

## 1. Arquitectura

```text
Real tables (preferences, saved_searches, quick_notes)
  ↓ adapters (application/sync.py)
SyncRecord {resource_id, kind, payload, version_ms, version_device, digest, deleted}
  ↓ domain/sync.py (pure: export/compare/classify/LWW/apply/verify)
Snapshot JSON {protocol, device_id, exported_at_ms, records[]}
  ↓ infrastructure/sync_transport.py (FileTransport, sin cloud)
Otro PC: import_snapshot (valida) -> sync -> apply -> verify -> sync_log
  ↓ infrastructure/sync_store.py (sync_state + sync_log, migración 015)
```

- Fuente de verdad local: cada PC funciona sin el otro; sync es capa, no sustitución.
- Sin segunda BD académica: `sync_state` solo guarda versiones/digests, nunca duplica entidades.

## 2. Datos sincronizables (v1)

| Entidad | resource_id | payload | versión | digest |
|---|---|---|---|---|
| preference | `pref:<f42.key>` (6 claves) | `{"value": ...}` (Decimal→str) | `(ms, device)` vía sync_state | canónico kind+rid+payload+deleted |
| saved_search | `saved:<kind>:<ref>` | `{"title","created"}` | id. | id. |
| quick_note | `note:<slug>` | `{"text","created"}` | id. | id. |

Fuera de alcance (documentado): subjects/assessments/documents/CAS blobs/circuits/engineering, notificaciones computadas, recents (ruido LRU), auth/multiusuario. Motivo: necesitan versionado propio primero; F13 los ampliará.

## 3. Last-write-wins

Comparación `(version_ms, version_device)`: mayor `ms` gana; empate → mayor `device_id` lexicográfico gana. Precisión ms. Relojes desincronizados: determinista pero sin garantía causal (límite conocido; F13 podrá añadir HLC). Igualdad total → `unchanged`. Mismo digest con versiones distintas → `same` (converge a versión mayor, sin conflicto).

## 4. Identidad de dispositivo

`sync.device_id` en `app_settings`: 32 hex minúsculas (`secrets.token_hex(16)`). Nunca hostname/MAC/IP/rutas. Validación regex; si falta o es inválida se regenera. Si se clona la BD, regenerar (documentado en gate).

## 5. Versionado

Por recurso: `(version_ms:int>=0, version_device:32hex)`. `sync_state` conserva `(version, digest)`; si el digest actual coincide se reutiliza versión (sin bump espurio); si cambia se asigna `(now_ms, device_id)`. Determinista dado mismo estado+config.

## 6. Tombstones

`delete_record()` → `payload={}`, `deleted=True`, nueva versión, digest propio. Se propaga por LWW como un update. Retención: se conservan; purga solo manual futura (no auto-GC en v1).

## 7. Protocolo

`EXPORT -> CANONICAL -> COMPARE -> CLASSIFY(unchanged/local-only/remote-only/same/conflict) -> LWW -> APPLY -> VERIFY -> SYNC LOG`. `VERIFY` re-ejecuta `sync(out, remote)` y exige convergencia.

## 8. Transporte

`FileTransport.save/load`: JSON canónico `sort_keys`, límites (8 MB snapshot, 256 KB payload, 10k records), validación de esquema/digests/device, rechazo con `AC-SYN-001` sin tocar estado válido. Desacoplado del motor; OneDrive/cloud queda para F13.

## 9. Seguridad

Validación de estructura/tipos/versiones/hashes antes de aplicar. Sin `eval/exec/compile/subprocess/os.system/shell=True/pickle`: verificado por AST en tests. SQL parametrizado (`?`). Secretos nunca en log (D2 redact).

## 10. Canonicalización y hashes

`canonical_digest = sha256(json({deleted,kind,payload,resource_id}, sort_keys, separators))`. Excluye versión/tiempos/runtime → mismo cambio == mismo digest en ambos PCs.

## 11. Log

`sync_log(event_id, device_id, resource_id, kind, operation, local_version, remote_version, winner, conflict, result, timestamp_ms, digest_before, digest_after, protocol_version)`. `event_id = sha256(protocol|rid|lv|rv|op|winner|digest_after)[:16]` (determinista). `timestamp_ms` inyectado (tests fijos). Append-only, `INSERT OR IGNORE`.

## 12. Límites y F13

V1 resuelve 2 PCs personales con fichero. No CRDT, no merges semánticos, no cloud obligatorio. F13 añadirá OneDrive/cloud/offline-first sobre este motor (`Sync Engine, Versioning, Conflict Resolution, Sync Log, Transport Adapter`).
