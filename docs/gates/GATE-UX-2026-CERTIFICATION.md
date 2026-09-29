# GATE UX 2026 — Certificación

Fecha: 2026-09-29 · Rama: `main` · Base previa al rediseño: `d5650c5` · Cierre del rediseño: ver §9 (commit del gate).

## Veredicto

**UX 2026: CERTIFICADO CON LIMITACIONES DOCUMENTADAS.**

- Suite completa: **4962 tests recogidos, 0 fallos de código** (5 fallos iniciales por paquete ausente en el entorno, ver §5). Más 8 tests del recorrido de certificación de este gate.
- El core certificado no se ha tocado (§3). Hay dos matices que se declaran, no se ocultan: un arreglo de dos líneas en la capa de aplicación F10 y una capa de aplicación nueva (`practice.py`).
- **No** se certifica lo que no se pudo ejecutar aquí: instalador, monitor físico a 125/150/200 %, lector de pantalla (§7).

Nada de lo anterior se afirma sin la evidencia de §6.

## 1. Qué se implementó (13 prompts, 15 commits sobre `d5650c5`)

| Prompt | Entrega | Commit |
|---|---|---|
| 1 Auditoría | `docs/ux/UX-AUDIT-2026.md` | `5f4650e` |
| 2 IA | `docs/ux/INFORMATION-ARCHITECTURE-2026.md` | `ff34b15` |
| 3 Sistema de diseño | tokens, `DESIGN-SYSTEM-2026.md` | `2098c42` |
| 4 Shell | carril, barra superior, secciones, rutas, paleta Ctrl+K | `c4b62c9` |
| 5 Home | Home editorial con actividad real | `921be68` |
| 6 Ingeniería | Circuits, Aerospace, Digital Logic sobre el kit de workspace | `7b01cd1` |
| 7 Laboratorios | esqueleto unificado, gráficas, resultados estructurados | `e1896e6` |
| 8 Learn/Practice/Tutor | página Practice (sesiones, plan, dominio), tutor integrado | `70d6cb4` (+ `fc521b1`, `c6d1fad`) |
| 9 Diálogos | `DialogFrame`, `show_message` único, sin `QMessageBox` fuera de `dialogs.py` | `7de01eb` |
| 10 Movimiento y estados | fundidos de 100–180 ms, bloqueo durante `RUNNING`, respeta "reducir animaciones" | `e14da44` |
| 11 Windows | tamaño ante pantallas pequeñas, carril que se pliega, instancia única, icono como recurso, F11 | `c6bf954` |
| 12 Auditoría visual | `docs/ux/UX-REVIEW-2026-FINAL.md` y sus correcciones | `b3a9d8b`, `798bdea` |
| 13 Este gate | recorrido de certificación + este documento | ver §9 |

Cambio total frente a la base: 56 ficheros, +8270 / −833 líneas (21 ficheros de tests: +2160 / −54).

## 2. Restricciones del encargo y cumplimiento

| Restricción | Estado | Evidencia |
|---|---|---|
| Mantener PySide6, EXE e instalador | Cumple | `packaging/windows/` sin cambios de estructura; solo se añadió el icono como recurso al `.spec` |
| Sin arquitectura paralela ni reescritura del core | Cumple | El rediseño vive en `src/academic_core/ui/`; el `QTabWidget` se conserva como pila de páginas |
| Sin port web | Cumple | — |
| No modificar core, F0–F16, cálculos, contratos, backend, persistencia certificada | **Cumple con dos matices (§3)** | `git diff d5650c5 HEAD -- src/academic_core/domain src/academic_core/engines src/academic_core/infrastructure` está vacío |
| `main` como fuente canónica | Cumple | `main` es la única rama (local y remota); sin ramas nuevas |
| No declarar certificación sin evidencia | Cumple | §6 y §7 |

## 3. Cambios fuera de `ui/` (declarados)

Se hicieron con la aprobación expresa de la persona responsable ("si a la decisión" al exponer F9–F12; "arregla" al fallo de F10). No tocan dominio, motores ni infraestructura.

| Fichero | Cambio | Por qué |
|---|---|---|
| `application/facade.py` | +22 líneas: cablea F9–F12 (`qbank`, `bank_ingest`, `correction`, `mastery`, `adaptive`, `tutor`, `practice`) | Exponer por la fachada lo que ya estaba certificado |
| `application/practice.py` | nuevo, 320 líneas | Orquesta F9→F10→F11→F12 y devuelve valores planos. No añade calificación, dominio, plan ni tutoría propios. La interfaz nunca recibe la respuesta correcta |
| `application/mastery.py` | 2 líneas: `if correct is None: continue` | `apply_evidence` lanzaba `DomainError("observation must carry positive mass")` con respuestas `needs_review`, contra su propio comentario ("None → needs_review → no_update"). El arreglo hace lo que el comentario documenta |

La cadena de autoridad determinista `propuesta LLM → validación → política → F9 correct_answer → verificación → VerifiedResponse` no se modificó. Con el modelo apagado (`NullProvider`, valor por defecto) el tutor responde con guía estática verificada (`LLM_UNAVAILABLE`).

## 4. Qué se verificó

### 4.1 Funcionalidad (recorrido `tests/test_ux_certification.py`, sin mocks del core)

| Área | Comprobación | Resultado |
|---|---|---|
| Módulos y navegación | Las 17 rutas abren su página sin error | ✔ |
| Ejercicios | `ohm-i` resuelve y da resultado; entrada inválida muestra error sin texto crudo de excepción | ✔ |
| Laboratorios | Virtual Lab: nueva sesión, ejecución y *replay* exacto; Digital Logic captura | ✔ |
| Ingeniería | Aerospace calcula una órbita GEO real (35 786 km) | ✔ |
| Tutor | Banco de ejemplo, intento, dominio actualizado, pista verificada con el modelo apagado | ✔ |
| Settings | Cambio claro/oscuro se aplica a los tokens | ✔ |
| Persistencia | Cerrar y reabrir conserva ruta y asignatura; la asignatura está en disco | ✔ |

### 4.2 Experiencia

| Aspecto | Verificación | Dónde |
|---|---|---|
| Navegación | Rutas, historial Alt+←/→, Ctrl+1–4, migas, secciones | `test_ux_routes`, `test_ux_shell` |
| Estados | Cinco estados con pastilla coherente; bloqueo durante `RUNNING` | `test_ux_motion` |
| Teclado | Diálogos: Escape, Enter, foco inicial; F11; vistas de Learn enfocables | `test_ux_dialogs`, `test_ux_windows`, `test_ux_polish` |
| Foco | Foco inicial explícito en cada diálogo; destructivos empiezan en Cancelar | `test_ux_dialogs` |
| Redimensionado y DPI | Sin scroll horizontal en 5 páginas × 4 escalas (100/125/150/200 %, por factor de escala de Qt); 0 de 17 rutas con desborde a 1250 px | Prompts 11 y 12 |
| Temas | Claro y oscuro: 17 rutas renderizadas en ambos; contraste de texto ≥ 4,5:1 calculado sobre los tokens | Prompt 12, `test_ux_polish` |
| Diálogos | Un único camino (`show_message`); sin `QMessageBox` fuera de `dialogs.py` | `test_ux_dialogs` |
| Errores | Solo campos seguros de `UiError` (D2); sin `{type(e).__name__}: {e}` | `test_ux_dialogs`, recorrido |
| Estados vacíos | Home, Learn, Library, Documents, Circuits, laboratorios, Aerospace, Plan | `test_ux_polish` y capturas |

## 5. Resultados de la suite (separados honestamente)

Suite completa lanzada en dos mitades (UI y resto), 4962 tests:

| Mitad | Resultado |
|---|---|
| UI (`test_ui*`, `test_f15_*`, `test_f8q6_f15_*`, `test_product_*`, `test_ux_*`, `test_practice_service`, `test_e01–e03*`) | **508 passed**, 0 fallos (22 min 17 s) |
| Resto | 4435 passed, **5 failed**, 14 skipped (39 min 21 s) |

Clasificación de todo lo que no fue verde:

| Categoría | Caso | Causa | Estado final |
|---|---|---|---|
| Nuevo (mío, corregido antes de commitear) | `test_pop_uses_bounded_easing` | Un test nuevo fijaba `ACORE_REDUCE_MOTION=1` a nivel de módulo y contaminaba la sesión | Corregido: la variable se fija por fixture. Pasa |
| Ambiental | 4 × `tests/test_pdf.py` y `test_f4_knowledge.py::test_teaching_guide_pdf_to_subject_with_provenance` | `pypdf` (declarado en `requirements-lock.txt`: 6.14.2) no estaba instalado | Instalado `pypdf==6.14.2`; los 5 pasan |
| Ambiental | 12 de los 14 *skipped* | Marcas `skipif` por `pypdf` ausente (p. ej. `test_f3_ext.py:291`). Inferido: al instalar `pypdf`, la re-ejecución de los 32 ficheros con marcas de omisión deja solo 2 omitidos y ningún fallo | Se ejecutan y pasan |
| Ambiental (previo a esta fase) | `test_conversor_equiv` | `markdownify` no instalado | Instalado `markdownify==1.2.3`; pasa |
| Ambiental (previo) | 5 *golden* (`test_e0_g01_…`, 4 × `test_q5_g01_…`) | Fixtures con CRLF de un checkout anterior; `.gitattributes` exige LF | Reextraídos con `git checkout`; pasan |
| Omitido, sin causa de código | 2 × `test_pdf.py:35` | `reportlab` ausente (no está en los requisitos) | Sigue *skipped* |
| Preexistente / no relacionado | Rama local `pr-1` y `stash@{0}` ("temp", 18-sep, `domain/engineering/units.py`) | Anteriores al rediseño | Retirados después a petición: la rama estaba integrada en `main` y el contenido del stash (unidad `S`/`ADMITTANCE`) ya está en `main` |

**Fallos nuevos atribuibles al rediseño tras corregir: 0. Fallos de código preexistentes: 0. No se ocultó ningún fallo.**

Nota de método: las 5 dependencias y los *golden* se arreglaron en el entorno, no en el repositorio, así que otra máquina sin `pip install -r requirements-lock.txt` verá los mismos fallos ambientales. Tras instalar `pypdf`/`markdownify` solo se re-ejecutaron los ficheros afectados y los 32 ficheros con posibles *skips*, no las dos mitades completas otra vez; el resultado combinado es la suma de ambas ejecuciones.

## 6. Evidencia

- **Tests nuevos del rediseño: 136** en 10 ficheros — `test_practice_service` 21, `test_ux_certification` 8, `test_ux_dialogs` 9, `test_ux_engineering` 27, `test_ux_motion` 7, `test_ux_polish` 10, `test_ux_practice` 24, `test_ux_routes` 9, `test_ux_shell` 13, `test_ux_windows` 8.
- **Documentos:** `UX-AUDIT-2026`, `INFORMATION-ARCHITECTURE-2026` (§14.x por prompt), `DESIGN-SYSTEM-2026`, `UX-REVIEW-2026-FINAL` (19 hallazgos, estado de cada uno en su §7).
- **Mediciones:** 17 rutas × {claro, oscuro, vacío} renderizadas; scroll horizontal 1 → 0 rutas; controles sin nombre accesible 8 → 0; etiquetas recortadas 4 → 0; contraste WCAG calculado sobre tokens.
- **Capturas:** se generaron durante el trabajo y no se guardan en el repositorio (carpeta temporal de la sesión).

Reproducción:

```bash
pip install -r requirements-lock.txt
QT_QPA_PLATFORM=offscreen python -m pytest tests -p no:cacheprovider
```

(la suite completa tarda ~40 min en esta máquina; la mitad de UI, ~22 min).

## 7. Limitaciones conocidas (no ocultas)

1. **Instalador sin ejecutar.** No se construyó ni se probó el EXE ni el Setup en esta fase (requiere PyInstaller, NSIS y administrador). Start Menu, desinstalación y máquina limpia siguen como *NOT VERIFIED* en `packaging/windows/README.md`. Solo hay un test estático (Start Menu registrado, clave de desinstalación, el desinstalador no borra los datos).
2. **DPI real.** 125/150/200 % se midió con el factor de escala de Qt sobre un monitor al 100 %, no en monitores físicos; el DPI mixto entre monitores no se probó.
3. **Accesibilidad.** No hay recorrido de teclado de extremo a extremo ni prueba con lector de pantalla ni modo de contraste alto de Windows. Solo se midieron nombres accesibles, widgets enfocables y contraste de tokens.
4. **Idioma de la interfaz (F-06).** Las etiquetas `Explicar`, `Paso a paso`, `Derivar`… están en español y abren explicaciones cuyo contenido es español fijado por los motores certificados E0–E3; el resto de la interfaz está en inglés. Es una decisión de producto pendiente.
5. **Contraste de botones sin borde.** Se distinguen por su etiqueta; su relleno frente a la tarjeta es 1,07–1,12:1.
6. **Intentos de práctica a medias.** Se pierden al cerrar la aplicación; lo corregido queda guardado. Sin banco propio, Practice se estrena con el banco de ejemplo (`Load sample`) o importando un JSON D6.
7. **Digital Logic › Transitions** mantiene scroll horizontal (7 columnas).
8. **Movimiento.** Se verificó que se dispara, dura 100–180 ms y se retira; no se midió cómo se percibe el fundido en pantalla.
9. **Ejecución como EXE empaquetado.** Las rutas de recursos (icono) siguen `runtime.resource_path`, pero no se ha ejecutado el bundle congelado.
10. **Menú Go** conserva 10 entradas porque los tests las fijan.
11. **Publicación.** Los commits se subieron uno a uno a `origin/main` y `main` es la única rama, local y remota. Se borraron las ramas `pr-1`, `f4.1-closure` y las cuatro `claude/*` (todas ya integradas en `main`; el único commit de `f4.1-closure`, un cambio de `.gitignore`, se conservó con `cherry-pick`).
12. La limitación de producto **GREELEC** (sin integración) se conserva y sigue visible en Settings › Diagnostics.

## 8. Criterios de aceptación

| Criterio | Cumple |
|---|---|
| Core y contratos intactos (domain/engines/infrastructure sin diff) | ✔ |
| Suite completa sin fallos de código | ✔ (tras los arreglos de entorno de §5) |
| Funcionalidad de módulos, navegación, laboratorios, ejercicios, tutor, ingeniería, settings y persistencia | ✔ (recorrido de §4.1) |
| UX: navegación, estados, teclado, foco, resize, DPI, temas, diálogos, errores, estados vacíos | ✔ con las reservas de §7 |
| Instalador ejecutado y verificado | ✘ No verificado |
| Accesibilidad con lector de pantalla | ✘ No verificada |

## 9. Cierre

El commit que añade este documento y `tests/test_ux_certification.py` cierra el Prompt 13. La verificación final antes de commitear fue el recorrido de certificación completo (8 tests) más `test_ux_polish` y `test_ux_motion`.
