# Comportamientos migrados vs divergencias (§28 — sin parches silenciosos)

Origen verificado: `Gestion-Academica/models.py`, `routes/horarios.py`,
`routes/conflictos.py` (solo lectura; sin commits en fuentes).

## A. Grading — DIVERGENCIA deliberada (ADR-0011)
Original: `float` + `round(x, 2/4)` de Python (banker's / half-even).
Academic Core: `Decimal` + `ROUND_HALF_UP` (redondeo académico estándar).
Cota de desviación: ≤0.005 en porcentaje, ≤0.00005 en media; `test_grading.py`
replica la semántica original en float y exige acuerdo dentro de la cota +
exactitud en casos típicos. Resto idéntico: media solo sobre puntuados, regla
`maximo`, `final` override, evaluada solo al 100% del peso (comparación en
crudo, no sobre el porcentaje redondeado), corte 5.0.

## B. Bloques — SIMPLIFICACIÓN temporal documentada
Original: el bloque pesa su propio `%` del esquema y agrega a sus miembros.
F1: el bloque pesa la suma de sus miembros (el `%` de bloque llega con la UI
de grading de Fase 4). Esquemas sin bloques son bit a bit equivalentes.

## C. Horarios — EXTENSIÓN genérica
`dia_semana` 1..7 (original 1..5, cuadrícula Lun–Vie). Expansión, regla de
anclaje quincenal, `is_session_day` O(1) y solape `[inicio,fin)` idénticos;
`test_schedule.py` los fija, incluido el ancla (inicio en miércoles → patrón
desde el primer martes posterior).

## D. Conflictos — paridad total
Warn-never-block, tareas puntuales + sesiones de series, clave de
desduplicado por (tipo,id,fecha): misma semántica, implementación pura
(`domain/conflicts.py`), sin Flask.

## E. Tareas/espacios — paridad + desacoplo
Tipos, prioridades, subset que autocrea espacio, secciones fijas e intervalos
de repaso `{no_visto:0, flojo:3, dominado:18}` portados; winotify/Qt fuera del
dominio (notificaciones = registros; el delivery es infraestructura/UI).

## F. No migrado en F1 (pendiente explícito)
UI Flask (nunca se migrará), scrapers Wuolah/Studocu y guías docentes
(`adapters/upc` en Fase 11 si procede), `Apartado` legacy (deprecado),
pdf.js vendorizado (Fase 3), backup con límites anti-zip-bomb (Fase 4+,
interfaz `BackupService` ya definida), auth web (no aplica; `AppLock` local).
