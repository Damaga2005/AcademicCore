# GATE-F4.2-DESIGN — Auditoría y diseño F4.2 (solo diseño, sin implementación)

Fecha: 2026-09-24 · Rama `f4.1-closure` · HEAD `ac2581f` (F4.1 CERTIFIED, baseline intacto)
Estado inicial verificado: `git status` limpio salvo `.claude/` externo; no se toca `main`; no push.

## 1. Matriz de evidencia F4.2

| Fuente | Ubicación | Evidencia de F4.2 | Tipo | Confianza |
|---|---|---|---|---|
| código migración | `src/academic_core/application/gestion_migration.py:917-919` | `busqueda_favorito/reciente` → `legacy_payloads`, motivo `"search favourites/recents are F4.2"`, `deferred="F4.2"` | explícita | alta |
| código migración | `gestion_migration.py:914-916` | `aviso_descartado` → `deferred="F12"` ("notification dismissals are F12") | explícita | alta |
| test | `tests/test_f4_migration_dryrun.py:251` | `deferred[favorito]==deferred[reciente]=="F4.2"` pineado | explícita | alta |
| docs migración | `docs/migration/GESTION-F4.1-MIGRATION.md:69-73` | tabla "Kept verbatim": F4.2 `busqueda_favorito,busqueda_reciente` | explícita | alta |
| docs delta | `docs/migration/GESTION-F4.1-DELTA-MAP.md:74` | `BusquedaFavorito/Reciente` → `legacy_payloads (F4.2)` | explícita | alta |
| ADR | `docs/adr/ADR-0024-legacy-migration-protocol.md:15-17` | "F4.2 data (…, favourites) is kept for its phase" | explícita | alta |
| gate F4 | `docs/gates/GATE-F4-DESIGN.md:354,388,403` | M-15 notificaciones → `application/notify` LATER_PHASE; X-20 `notificaciones` DEFER F4.2; "F4.2 (opcional): notificaciones, notas rápidas, configuración de widgets, favoritos/recientes" | explícita | alta |
| gate F4.1 | `docs/gates/GATE-F4.1-DESIGN.md:54-56` | "Fuera de F4.1 (conservado): … F4.2 favoritos/recientes/notificaciones" (y F12 notificaciones/IA) | explícita | alta |
| commits | `eba67b8` (grep F4.2) | M3–M7; el mensaje/cuerpo alude al diferido F4.2 | explícita | media |
| roadmap | `docs/roadmap/ROADMAP.md` | sin mención a F4.2 | explícita (ausencia) | alta |
| código existente | `domain/entities.py:551`, `infrastructure/repositories.py:699-708`, `migrations/004_study.sql:17` | `Notification` + `notify/pending_notifications` huérfanos (0 llamadas fuera de su definición) | explícita | alta |
| código existente | `application/search.py:73-91` (`UnifiedSearchService`), `infrastructure/resources.py:128-173` (FTS5), `academic_store.py:251` (`search_context`) | búsqueda unificada + FTS + contexto, sin historial/favoritos | explícita | alta |
| código existente | `academic_store.py:479-488` (`PersonalRepository.set/get_setting`), `academic_mgmt.py:31-33,565,575`, claves `gestion.tema`, `gestion.dias_*`, `gestion.widgets_*`, `grades.target_average` | ajustes persistidos, sin servicio de validación ni consumidor de widgets/tema | explícita | alta |
| código existente | `application/calendar.py:58-201`, `application/queries.py:90-109`, `application/academic_mgmt.py:263-309` (`agenda/home/upcoming/week`) | fuentes para notificaciones (tareas, series, conflictos, home) | explícita | alta |
| Gestion real | `routes/notificaciones.py:14-141`, `routes/busqueda.py:45-242`, `routes/configuracion.py:9-46`, `models.py` (AvisoDescartado 1371, ConfiguracionApp 1227, BusquedaFavorito 1537, BusquedaReciente 1564, NotaRapida 1593) | semántica de referencia: 3 reglas + autocompletar + descarte diario; 12 grupos + NFKD + favoritos/recientes; widgets; notas | explícita | alta |
| spec futuro | — | flujos UX exactos, catálogo de widgets exigible, multiusuario | — | DESCONOCIDO |

## 2. Clasificación de requisitos

**EXPLÍCITO** — F4.2 = capa de asistencia operativa: (a) favoritos/recientes de búsqueda persistidos desde `legacy_payloads`; (b) notificaciones computadas (`application/notify`); (c) preferencias/ajustes validados (tema, umbrales, widgets, objetivo de media); (d) notas rápidas ya existen (`QuickNote`, F4.1 M7) → su item "notas rápidas" se da por satisfecho en dominio, pendiente solo de UI (F15).

**DERIVADO** — (1) Sin auto-escritura en lectura: Gestion autocompleta exámenes en cada `GET`; F4.2 computa estado "ocurrido" sin mutar (idempotencia §11). (2) Sin descarte persistente en F4.2: `AvisoDescartado` es F12; el filtrado de descartes es de sesión/llamante. (3) Notificaciones computadas, no almacenadas (salvo avisos explícitos de usuario vía `notify()` existente). (4) `today` inyectado como parámetro (precedente `career.home(today)`). (5) Migración 014 aditiva para `saved_searches`/`recent_searches` + consumo de payloads F4.2.

**INFERIDO** — (a) El catálogo exacto de widgets lo define F15; F4.2 solo valida orden/ocultos como listas de tokens. (b) Límite de recientes = 15 y de grupos = 25 heredados de Gestion salvo decisión F15.

**DESCONOCIDO** — UX/flujos, multiusuario/auth, fetch remoto de recursos, entrega (push/winotify: F12).

**Conflicto resuelto por diseño (no por invención):** GATE-F4.1-DESIGN asigna "notificaciones/IA" a F12 mientras GATE-F4-DESIGN asigna `application/notify` a F4.2. Regla adoptada: F4.2 = notificaciones **deterministas computadas de datos locales** (atrasada/inminente/sin-empezar/inactiva); F12 = entrega, descartes persistentes (`AvisoDescartado`), IA y push. Sin solape.

## 3. Objetivo

Dar al usuario, sobre datos ya migrados, asistencia operativa diaria —búsquedas recordadas, avisos computados, preferencias persistidas— sin nueva ingesta, sin IA, sin UI (F15) y sin mutar F4.1.

## 4. Alcance

IN SCOPE: `SavedSearch`/`RecentSearch` (CRUD + trim + consumo de payloads F4.2); `NotificationService.compute()` con 4 reglas; `PreferencesService` (tema, `dias_aviso_examen`, `dias_asignatura_abandonada`, `widgets_orden/ocultos`, `grades.target_average`); reutilización de `Notification`, `notify/pending_notifications`, FTS, `UnifiedSearchService`, `agenda/home/upcoming`, `QuickNote`.
OUT OF SCOPE: UI Qt/Jinja (F15), entrega push/winotify (F12), descartes persistentes (F12), SRS (F11), sesiones/rachas (F10), anotaciones PDF (F14), sync (F13), generación de preguntas/IA (F12), fetch remoto, multiusuario, nueva ingesta de Gestion.

## 5. Requisitos funcionales

1. Favoritos: añadir idempotente (existente→200 lógico), listar por `fecha_creacion desc`, borrar; tipos del catálogo `TIPOS_ENTIDAD_BUSQUEDA` Gestion.
2. Recientes: upsert (borrar+reinsertar como más reciente), `etiqueta_mostrada`+`url` obligatorios, listar 15, recorte automático.
3. Notificaciones `compute(today, config)`: tarea atrasada (`dias<0`, rojo); tarea inminente (`dias<=recordatorio||dias_aviso_examen`, rojo si <3 si no naranja); espacio sin empezar (≤3 días, con material, 0% leído; rojo si <2); asignatura inactiva (`dias>dias_asignatura_abandonada`, gris; sin base→omitir). Orden rojo>naranja>gris. Exámenes pasados se informan como ocurridos, nunca se autocompletan.
4. Preferencias: get/put validados (`tema∈{claro,oscuro}`, días ≥1, media 0–10 o null, widgets como listas de tokens).
5. Migración 014 consume los payloads `busqueda_favorito/reciente` a las tablas nuevas (dry-run + idempotencia).

## 6. Requisitos no funcionales

D2 (`AC-ACD-*` nuevos + `to_ui_error`, sin `ApiError` nuevo); determinismo (cómputo puro, `today` inyectado, `ORDER BY` en listados, sin `hash()` persistente); idempotencia (re-ejecuciones y segundas migraciones sin duplicados); seguridad (§9); regresión §17 intacta.

## 7. Modelo de dominio

Reutilizar sin cambios: `Notification(title,body,due,read)`, `QuickNote`, `Milestone`, `StudyConcept`, `Task`, `Series`. Nuevo (dominio puro, stdlib): `SavedSearch(kind,ref,title)` + `RecentSearch(kind,ref,label,url,accessed)` — sin FK reales (como Gestion `TIPOS_ENTIDAD_BUSQUEDA`), invariantes: tipo del catálogo, `ref`/`label`/`url` no vacíos, `accessed` fecha. Lifecycle: crear/listar/borrar (favoritos), upsert/trim (recientes). Cardinalidades: N favoritos y ≤15 recientes por instalación (single-user). `Preferences` como value object validado, persistido en `app_settings`.

## 8. Arquitectura

```text
UI (F15, futuro)
  ↓
application: notify.py (NotificationService) + search.py (extend: favourites/recents) + personal.py nuevo (PreferencesService)
  ↓
domain / ports: entities.Notification, planning.QuickNote, nuevos saved_search/recent_search, preferences; puertos SearchHistoryPort, NotificationPort
  ↓
infrastructure: repositories existentes (notifications, app_settings) + 014 (saved_searches, recent_searches); adapters: ninguno nuevo
```

Sin ciclos (application→domain/ports; infra→ports), sin DB desde UI, sin lógica en routes/templates (no existen en AcademicCore), sin discovery dinámico, sin estado global mutable.

## 9. Interfaces

`NotificationService.compute(today, config) -> list[NotificationView(kind,level,title,message,url,entity)]`; `notify(n)/pending()` (existentes); `SearchHistory: add_favourite/is_favourite/list_favourites/remove_favourite/record_recent/list_recents`; `PreferencesService.get/update`. Errores D2, resultados tipados (no excepciones de control salvo D2).

## 10. Persistencia

Migración **014** aditiva: `saved_searches(kind,ref,title,created)` + unique(kind,ref); `recent_searches(kind,ref,label,url,accessed)` + índice temporal; consumo de `legacy_payloads` F4.2 en el migrador (fase F4.2, dry-run primero). Rollback: 014 `down` = DROP de las dos tablas (datos re-derivables desde payloads). Compatibilidad: resto del esquema intacto; `notifications` y `app_settings` reutilizados sin cambios.

## 11. Seguridad

Sin `eval/exec/pickle/subprocess/network`; URLs solo rutas internas (`/vista/...` futuras, nunca fetch); NFKD/snippet reuse (sin ReDoS: patrones acotados existentes); `recordatorio`/umbrales validados como enteros ≥0; sqlite parametrizado; sin secretos; `notify()` nunca incluye rutas locales absolutas en mensajes.

## 12. Determinismo

`compute()` puro: mismos (datos, today, config) → misma lista, mismo orden (nivel, fecha, id). Listados con `ORDER BY`. Digest de informe de migración de payloads excluye timestamps (precedente ADR-0024). Tests multiseed 0/11/2024/random.

## 13. Idempotencia

Favoritos: add existente = no-op. Recientes: upsert + trim → estado final único. Migración 014: `legacy_map`/`already_migrated`; rerun = 0 cambios. `compute()` sin escrituras (sin autocompletar).

## 14. Compatibilidad y regresión

Intactos: D1/D2/D3, F2, F3/F3.1, F4.0/F4.1 (migración y gates sin tocar; `/3` y payloads F4.2 se consumen, no se reescriben), F8-Q, E0/E0.4, F15. `notifications`/`app_settings` existentes se usan, no se remodelan.

## 15. Estrategia de tests

| Requisito | Test | Evidencia | Esperado |
|---|---|---|---|
| favoritos CRUD+idempotencia | `test_f42_search_history.py` | fixture sintética | add 2× = 1 fila; delete idempotente |
| recientes upsert+trim | id. | 16 inserts | 15 filas, la más reciente primera |
| consumo payloads F4.2 | `test_f42_migration.py` | fixture legacy | 2 filas migradas, rerun 0 |
| 4 reglas notify | `test_f42_notify.py` | tareas/espacios/asignaturas atrás/límite/futuro | niveles y mensajes exactos; sin escrituras |
| exámenes pasados no mutan | id. | examen ayer no completado | estado "ocurrido", BD intacta (hash) |
| preferencias validación | `test_f42_preferences.py` | valores límite | rechazos D2, `None` borra objetivo |
| determinismo | id. + multiseed | seeds 0/11/2024/random | mismo resultado |
| seguridad | `test_f42_security.py` | AST (sin eval/exec/pickle/subprocess/network; SQL parametrizado) | verde |
| regresión | suite | gate §17 | 0 regresiones |

## 16. Rollback

Código: revert del commit F4.2 (014 `down` revierte tablas; payloads F4.2 intactos → re-ejecutables). Datos: payloads nunca se borran; `notify()` solo añade filas `notifications` (borrables por id).

## 17. Criterios de aceptación y gate

Aceptación: las 4 reglas con niveles exactos; favoritos/recientes según §5; preferencias validadas; 014 consume los 2 payloads (1 favorito + 1 reciente reales) con rerun 0; determinismo multiseed; seguridad AST verde; 0 regresiones; sin tocar F4.1/Gestion real. Gate futuro: `GATE-F4.2-CERTIFICATION.md` con matriz requisito→test→evidencia.

## 18. Riesgos (por impacto)

1. Divergencia UX futura (F15) sobre niveles/mensajes — mitigación: niveles y textos en dominio con tests pineados.
2. `widgets_orden` sin catálogo exigible — mitigación: tokens libres validados sintácticamente; catálogo en F15.
3. Recientes con URLs externas heredadas — mitigación: se almacenan, nunca se fetchean.
4. Límite 15/25 heredado arbitrario — mitigación: constantes con nombre y tests.
5. Solape F12 (descartes/entrega) — mitigación: regla §2, `AvisoDescartado` intacto.

## 19. Bloqueos

Los siguientes puntos quedan **cerrados por especificación antes de implementación**. No cambian el alcance de F4.2 ni F4.1; convierten decisiones implícitas en contratos ejecutables.

### 19.1 Resolución de referencias legacy — BLOQUEO CERRADO

busqueda_favorito.entidad_id y busqueda_reciente.entidad_id de Gestion son IDs físicos de la base legacy y **no son IDs reutilizables directamente** en AcademicCore.

Regla normativa:
1. El consumo F4.2 DEBE resolver referencias legacy mediante legacy_map/la identidad estable producida por F4.1.
2. F4.2 NO DEBE inventar, slugificar, reinterpretar ni reutilizar numéricamente un entidad_id legacy como stable_id.
3. Si una referencia no tiene mapping determinista a un objeto AcademicCore, el payload se conserva íntegramente en legacy_payloads y **no se crea** un SavedSearch/RecentSearch adivinando el destino.
4. El migrador debe distinguir entre referencia resuelta (se materializa el registro F4.2) y referencia no resoluble (payload preservado + warning/deferred evidence, sin pérdida).
5. La resolución debe ser idempotente y no modificar el origen Gestion.

Esto es obligatorio para el caso real del fixture: tipo_entidad=asignatura, entidad_id=2 y tipo_entidad=documento, entidad_id=1.

### 19.2 Actividad canónica de asignatura — BLOQUEO CERRADO

La regla dias > dias_asignatura_abandonada requiere una fuente de actividad determinista. F4.2 NO puede inventar un campo inexistente en Subject.

Contrato:
- La actividad se calcula únicamente desde fuentes AcademicCore ya existentes que puedan asociarse inequívocamente a una asignatura.
- Como mínimo se consideran las fuentes de actividad que ya tienen subject_id y fecha/hora persistidas; activity_days por sí solo NO se tratará como actividad específica de asignatura cuando no exista asociación.
- La implementación debe exponer una función de aplicación/domain de solo lectura, por ejemplo last_subject_activity(subject_id), que devuelva la última actividad canónica o None.
- Si no existe actividad específica resoluble para una asignatura, la regla inactiva se **omite**, tal como exige §5.
- El cálculo usa today inyectado; nunca datetime.now() oculto dentro de compute().

La fuente exacta debe quedar documentada en los tests con casos por cada tipo de actividad utilizado; no se permite introducir una fuente nueva o una escritura lateral para fabricar actividad.

### 19.3 Frontera Notification / NotificationView — BLOQUEO CERRADO

F4.2 NO remodela la tabla notifications ni convierte las notificaciones persistidas existentes en el almacenamiento de los avisos computados.

Separación obligatoria:

Notification / notify() / pending_notifications()
    = mecanismo persistido existente

NotificationView
    = resultado efímero y determinista de NotificationService.compute()

compute():
- no escribe notifications;
- no marca tareas/exámenes como completados;
- no crea descartes;
- no altera app_settings;
- no altera legacy_payloads;
- solo lee datos y devuelve NotificationView[].

AvisoDescartado sigue siendo F12 y queda fuera de F4.2.

### 19.4 Preferencias: namespace y serialización — BLOQUEO CERRADO

F4.2 reutiliza exclusivamente app_settings y PersonalRepository.set_setting/setting.

Namespace canónico:

f42.theme
f42.exam_reminder_days
f42.abandoned_subject_days
f42.widgets_order
f42.widgets_hidden
f42.target_average

Reglas:
- theme ∈ {claro, oscuro}.
- exam_reminder_days y abandoned_subject_days son enteros ≥ 1.
- target_average es Decimal/valor textual validado en rango [0,10], o None para eliminarlo.
- widgets_order y widgets_hidden se almacenan como JSON UTF-8 canónico de listas de strings.
- No se usa CSV como representación persistida F4.2.
- Al leer valores legacy gestion.widgets_*, el servicio puede normalizarlos a la representación F4.2; no modifica los valores legacy durante una lectura.
- La serialización debe ser estable para que dos estados semánticamente iguales produzcan el mismo texto persistido.

### 19.5 Queries limitadas de UI — BLOQUEO CERRADO

Las queries de UI existentes como upcoming_deadlines(..., limit=20) y overdue_deadlines(..., limit=50) NO son una fuente completa para NotificationService.compute().

F4.2 debe usar una fuente completa o una query específica sin límite de presentación. Los límites de UI no pueden hacer desaparecer silenciosamente avisos computables.

### 19.6 Fecha canónica de StudySpace — BLOQUEO CERRADO

Para la regla espacio sin empezar ≤3 días, el origen temporal canónico es el objeto académico que originó el espacio, preferentemente su exam_task_id cuando exista.

La implementación debe:
1. resolver el StudySpace;
2. resolver su tarea/examen asociado;
3. calcular días respecto a la fecha canónica de ese objeto;
4. comprobar material existente y progreso 0%;
5. omitir la regla si falta información suficiente, sin inventar fechas.

No se usará created del StudySpace como sustituto silencioso de la fecha del evento académico.

### 19.7 Desempates deterministas

Todos los listados F4.2 deben tener orden explícito.
- favoritos: created DESC, kind ASC, ref ASC;
- recientes: accessed DESC, kind ASC, ref ASC;
- avisos: level priority DESC, due ASC, stable/entity id ASC.

Nunca se dependerá del orden accidental de SQLite.

## 20. Cambios realizados

Actualización de docs/gates/GATE-F4.2-DESIGN.md para cerrar los cuatro puntos de especificación detectados en la auditoría de implementación:
1. resolución segura de referencias legacy;
2. definición canónica de actividad por asignatura;
3. separación estricta entre notificaciones persistidas y avisos computados;
4. namespace y serialización de preferencias.

Además se han cerrado explícitamente los riesgos derivados de límites de queries de UI, fecha canónica de StudySpace y desempates deterministas.

**Estado:** F4.2 DESIGN READY → IMPLEMENTATION READY (con contratos cerrados).

No se implementa código F4.2 en este commit. F4.1 permanece intacto.
