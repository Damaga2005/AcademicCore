# UX Audit 2026 — AcademicCore

Estado: **auditoría sin cambios de código** (Prompt 1 de `PROMPTS_ACADEMICCORE_UX_2026.md`).
Base: `main` @ `d5650c5`, árbol limpio. Ningún archivo de código, test ni rama fue tocado.

## 0. Método y límites

- Evidencia: lectura completa de los 19 módulos de `src/academic_core/ui/` (3 951 líneas), `app.py`, `DESIGN.md`, `PRODUCT.md`, tests que fijan la UI y greps de verificación. Las referencias `archivo:línea` apuntan a `HEAD`.
- **No se ha ejecutado la app ni se han hecho capturas.** Lo que depende de renderizado real (DPI 125/150/200 %, contraste efectivo, jitter de resize, foco visible) figura como *riesgo por inspección de código*, no como hecho medido. Se verificará en los Prompts 11–13.
- Convención de severidad: **A** = rompe la promesa de producto o la honestidad de la UI; **M** = degrada claramente la percepción; **B** = pulido.

---

## 1. Inventario

### 1.1 Ventana y navegación (`main_window.py`, 682 líneas)

| Elemento | Realidad actual |
|---|---|
| Ventana | `AcademicMainWindow`, 1250×780, sin `minimumSize`. Título: `Academic Core — F4 Academic Management (vX)` |
| Menús | `View ▸ Appearance` y `Go` (5 grupos + "Engineering: Modules…"). No hay `File`, `Help` |
| Sidebar | Árbol académico (Universidad→Grado→Año→Periodo→Asignatura) de 300 px fijos + botones `Add…` / `Delete`. **Visible en todas las pestañas**, sea o no relevante |
| Fila de acciones | 7 botones globales (`Add topic`, `Add assignment`, `Add task`, `Add exam`, `Record grade`, `Export JSON`, `Import JSON`) sobre las pestañas, **siempre visibles**, actúan sobre la asignatura del árbol |
| Contenido | `QTabWidget` con **13 pestañas** planas |
| Dock | `Session log` fijo a la derecha: solo un texto estático (versión, ruta de BD), no es un log |
| Barra de estado | Texto estático `v · offline · ruta` |
| Atajo | `Ctrl+K` → `SearchDialog` (modal) |

### 1.2 Las 13 vistas reales (orden actual de pestañas)

| # | Pestaña | Archivo | Tipo de superficie |
|---|---|---|---|
| 0 | Dashboard | `dashboard.py` | Rejilla 2×3 de cards con botón "Open" |
| 1 | Overview | `main_window.py` | `QTextEdit` solo lectura, volcado de texto |
| 2 | Activities | `main_window.py` | `QTextEdit` solo lectura, volcado de texto |
| 3 | Grades | `main_window.py` | `QTextEdit` solo lectura, volcado de texto |
| 4 | Planning | `main_window.py` | `QTextEdit` solo lectura, volcado de texto |
| 5 | Resources | `main_window.py` | Búsqueda + 5 botones + lista + `QTextEdit` |
| 6 | Authoring | `authoring.py` | 3 columnas fijas (260/300/resto) + ~12 botones |
| 7 | Engineering | `engineering.py` + `aerospace.py` | 3 columnas fijas (240/260/resto) + `OrbitPanel` embebido |
| 8 | Exercises | `exercises.py` | Formulario + 7 botones + `QTextEdit` |
| 9 | Simulation | `simulation.py` | 5 `QGroupBox` apilados |
| 10 | Virtual Lab | `virtual_lab.py` | 3 `QGroupBox` apilados |
| 11 | Logic Analyzer | `logic_analyzer.py` + `waveform.py` | Pila vertical: formulario, canales, botones, forma de onda, tabla, explicación |
| 12 | Settings | `main_window.py` | `QFormLayout` (apariencia, carpeta de datos) + texto |

### 1.3 Diálogos y feedback

| Componente | Archivo | Notas |
|---|---|---|
| `prompt_form` | `dialogs.py` | Único formulario genérico (text/int/date/combo). OK/Cancel |
| `confirm` | `dialogs.py` | `QMessageBox.question` genérico, título "Confirm" |
| `show_ui_error` / `show_value` | `errors.py` | Conversor único D2 → `QMessageBox` warning/info/critical |
| `SearchDialog` (Ctrl+K) | `search.py` | Modal, 520 px |
| `ModulesDialog` | `modules.py` | Lista simple, 460 px |
| `FirstRunDialog` + splash | `startup.py` | Una pantalla; splash pintado a mano con hex fijos |
| `QMessageBox` directos | main_window 20, authoring 13, engineering 9 | 42 usos que **no** pasan por `show_ui_error` |

### 1.4 Sistema visual actual (`theme.py`, 276 líneas + `DESIGN.md`)

- Fusion + un único QSS generado desde `Tokens` (22 colores; light/dark; `system|light|dark` persistido en `QSettings`).
- Mundo declarado: **"Apple workbench"** — acento `#007AFF`, neutros `#F5F5F7/#F2F2F6/#1D1D1F`, fuente `Segoe UI → SF Pro → Helvetica`.
- Tipografía en **pt**: 15 / 11 / 10 / 9 / 8.5 pt (≈ 20 / 15 / 13 / 12 / 11 px). Regla global `* { font-size: 9pt }`.
- Radios 7/8/10/12 px; sin sombras (regla declarada); pill de estado por `[role="pill"][state=…]`.
- Motion: `motion.pop_in` = fade de opacidad 0.85→1 en 150 ms, aplicado a **3** diálogos.
- Estados: enum `UiState` = `IDLE / RUNNING / SUCCESS / WARNING / ERROR`.

### 1.5 Rutas / navegación real

Ruta única: `navigate_to(key)` → `_navigate(key)` → `tabs.setCurrentWidget/Index`. Claves: `home, overview, engineering, exercises, simulation, lab, logic, resources, settings`. Entradas: Dashboard (botones "Open"), menú `Go`, `ModulesDialog`. **No existe** historial, "atrás", breadcrumbs, ni estado de navegación persistido.

---

## 2. Problemas (con evidencia e impacto)

### 2.A — Qué transmite "toolkit clásico" y por qué

| ID | Sev | Problema | Evidencia | Impacto |
|---|---|---|---|---|
| U-01 | A | **La navegación es una tira de 13 pestañas** más un menú `Go` que la duplica. Es `VIEW → VIEW → VIEW`, no `WORKSPACE → CONTEXT → TASK` | `main_window.py:58-110`; `DESIGN.md` reconoce "Thirteen tabs scroll natively with arrow buttons — a pinned product fact" | La app se lee como una colección de paneles; las pestañas del extremo quedan ocultas tras flechas |
| U-02 | A | **Las vistas académicas son volcados de texto plano**: `subject: {stable_id}`, `scheme(0-10): grade=… state=…`, `• título [estado] stable_id` | `main_window.py:558-585` (4 pestañas, `QTextEdit(readOnly=True)`) | Es la marca más fuerte de "herramienta de depuración". Muestra ids internos al alumno. Sin tabla, sin gráfico, sin jerarquía |
| U-03 | A | **Sidebar y fila de 7 acciones siempre visibles**, aunque estés en Logic Analyzer o Simulation, donde no significan nada. Las acciones fallan con un `QMessageBox` "Select a subject in the tree first" | `main_window.py:141-156`, `443-447` | Contexto y herramientas mezclados: el usuario no sabe dónde está ni qué se aplica a qué |
| U-04 | A | **Presentación de resultados = `QTextEdit` de texto** en Exercises, Simulation, Virtual Lab, Engineering, Resources. Instrumentos (scope, Bode, sweep) se reducen a `"3ch 100pts window=…"` | `virtual_lab.py:308-320`, `simulation.py:152-160` | Un resultado de ejecución se ve igual que un formulario. El laboratorio no tiene visualización (salvo Logic Analyzer) |
| U-05 | M | **Diálogos genéricos**: `prompt_form` sin contexto, sin validación inline, botones "OK/Cancel"; `confirm` con título "Confirm" y el id crudo (`Delete subject SUBJ-…?`) sin botón por defecto seguro | `dialogs.py:11-69`; `grep defaultButton` = 0 | Percepción de formulario de 2005; riesgo de borrado accidental |
| U-06 | M | **42 `QMessageBox` directos** (`type(e).__name__: e`) coexisten con el conversor D2; el propio `errors.py` promete que "raw `str(exc)` never reaches the user" | 23 coincidencias de `type(e).__name__`/`str(e)` en `ui/`; `authoring.py`, `engineering.py`, `main_window.py` | Tres patrones de error distintos; se filtran nombres de excepción; incumple el contrato declarado |
| U-07 | M | **Mezcla de idiomas** en la misma pantalla: `Explicar`, `Paso a paso`, `Matemáticas`, `Derivar`, `Explicar último` junto a `Solve`, `Add + Run`, `Replay last` | `exercises.py:65-101`, `virtual_lab.py:97-111` | Incoherencia visible; sin capa i18n |
| U-08 | M | **Jerga interna en UI de usuario**: "F8-N sessions", "F8-Q digital capture… digital-trace/1", "FTS5", "GREELEC: no integration (UNKNOWN / REQUIRES INPUT)" (en Dashboard **y** Settings); el título de ventana dice "F4 Academic Management" | `dashboard.py:71-83,114-119`, `main_window.py:32,71,271` | Códigos de fase/gate filtrados al producto |
| U-09 | M | **Etiquetas de sección sin estilo**: `QLabel("Projects")`, `("Circuits")`, `("Documents")`, `("Outline")` no tienen `objectName`, no reciben ninguna jerarquía del tema | `engineering.py:28,44,60`, `authoring.py:33,49,60` | Cabeceras indistinguibles del cuerpo |
| U-10 | M | **Anchos fijos en píxeles** sin splitters ni scroll: 300 + (260+300) en Authoring, 300 + (240+260) en Engineering, más el dock derecho | `authoring.py:44,55`, `engineering.py:39,55`, `main_window.py:55`; **cero** `QSplitter`/`QScrollArea`/`QStackedWidget` en `ui/` | En ventanas pequeñas o con escalado alto el editor queda aplastado; los paneles largos (Logic Analyzer, Simulation) no tienen scroll |

### 2.B — Honestidad de la UI (regla "no simular")

| ID | Sev | Problema | Evidencia | Impacto |
|---|---|---|---|---|
| H-01 | A | **`Scenario` en Simulation es un control decorativo**: solo tiene el ítem `demo: voltage divider`, su tooltip promete "or a saved project circuit", y `_execute` **nunca lo lee**: elige el circuito según el `Analysis` | `simulation.py:42-45` vs `86-150` | Un control que aparenta elegir y no elige. Contradice el principio de PRODUCT.md |
| H-02 | M | **Dos grupos con el mismo título "Inputs"** separados por "Execution" (`Experiment · Inputs · Execution · Inputs · Results`) | `simulation.py:46,53,62,68` | Composición incoherente; el usuario ve dos veces "Inputs" |
| H-03 | A | **"Aerospace" navega a la pestaña equivocada**: `ModulesDialog` mapea `aerospace → simulation`, pero el orbital vive dentro de la pestaña *Engineering* (`OrbitPanel`) | `modules.py:24-27,57-58` vs `engineering.py:73-75` | Botón que lleva a un sitio sin orbitales. Digital Logic y Aerospace no existen como espacios propios |
| H-04 | M | **Dashboard: "Good morning." y "Continue where you left off." están fijos** (no dependen de hora ni de estado); no hay nada que continuar. "Resources / sessions — Available when the Resources tab has content" está siempre habilitado | `dashboard.py:50-53,79-80` | Frase de cortesía que no corresponde a datos reales |
| H-05 | M | **"Recent" solo lista el historial de búsqueda** (`search_history`), no trabajo real; no se enlazan ni las próximas entregas/exámenes aunque `queries.upcoming_deadlines` existe | `dashboard.py:150-157`, `main_window.py:580-585` | Home no responde a "qué he hecho / qué puedo continuar" |
| H-06 | M | **Búsqueda: Enter abre siempre el primer resultado**, la lista no es navegable con teclado hacia otro; solo los hits de tipo *subject* navegan, el resto no hace nada sin aviso | `search.py:32-33,53-59`, `main_window.py:319-325` | Paleta que aparenta poder elegir y no puede; feedback nulo si no hay destino |
| H-07 | M | **Virtual Lab: combinación circuito/análisis incompatible se rechaza con error** en vez de deshabilitar/filtrar opciones | `virtual_lab.py:176-182` | Error evitable; estado previsible no comunicado |

### 2.C — Estados, teclado, foco, accesibilidad, resize

| ID | Sev | Problema | Evidencia | Impacto |
|---|---|---|---|---|
| S-01 | M | Estados con **texto libre** en la pill (`"IDLE — session open"`, `"ERROR code: mensaje largo"`) y solo 5 estados; faltan `Computing`, `Paused`, `Offline` que pide el Prompt 7 | `state.py`; `logic_analyzer.py:382` | Pill que desborda; el modelo de estados no cubre el brief |
| S-02 | A | **Foco de teclado dudoso**: `outline: 0` en árbol y listas elimina el indicador nativo; `QPushButton` y `QTabBar::tab` no tienen regla `:focus` (solo campos de texto recolorean borde) | `theme.py:189-190`, `211-217` | *Riesgo por inspección*: navegación con Tab sin foco visible (WCAG 2.4.7). A confirmar con captura |
| S-03 | M | **Teclado mínimo**: un solo atajo global (`Ctrl+K`); mnemónicos `&` solo en Exercises y Logic Analyzer; sin atajos de navegación entre áreas | `grep QShortcut` = 1 | Sin navegación experta |
| S-04 | M | **Accesibilidad desigual**: 15 `setAccessibleName`, casi todos en Logic Analyzer; el resto de paneles no expone nombres | `grep setAccessibleName` | Lectores de pantalla: paneles sin nombre |
| S-05 | M | **La información esencial vive en tooltips** (p. ej. "Units required, e.g. V=5 V", sintaxis `VAR=value; VAR2=value2`) | `exercises.py:55,82,90-92` | Sintaxis oculta; el input es un `QTextEdit` de formato libre con `;` |
| S-06 | M | **Estado de UI no persistido**: solo `appearance` y `firstrun/seen` en `QSettings`. No se guarda geometría, última pestaña, selección | `grep saveGeometry/restoreGeometry` = 0 | Cada arranque vuelve a Dashboard/tamaño fijo |
| S-07 | M | **Empty states repetidos y sin acción**: "Select a subject in the tree" ×4 pestañas; "No project"; "(no block)" | `main_window.py:553`, `engineering.py:184` | Estado vacío sin guía ni acción siguiente |
| S-08 | B | **Sin `minimumSize`** en ventana; **sin plan DPI**: constantes de la forma de onda en píxeles (`LEFT=150`, `LANE_HEIGHT=44`), fuentes en pt | `waveform.py:41-46`, `main_window.py:33` | *Riesgo* a 125/150/200 %: por verificar en Prompt 11 |

### 2.D — Sistema visual y motion

| ID | Sev | Problema | Evidencia | Impacto |
|---|---|---|---|---|
| V-01 | A | **El lenguaje visual actual contradice el brief**: el tema es un clon de paleta Apple (`#007AFF`, `#F5F5F7`, fallback "SF Pro") y `DESIGN.md` lo declara "Apple workbench"; el Prompt 3 pide explícitamente *no clon de macOS* y una base `#F7F7F5 / #111111` | `theme.py:1-8,54-106`; `DESIGN.md:93-99` | Requiere rehacer tokens y reescribir `DESIGN.md` |
| V-02 | A | **Escala tipográfica muy por debajo del brief**: display 15 pt (≈20 px) vs 36–44; título 11 pt vs 26–32; cuerpo 9 pt (12 px) vs 14–16; caption 8.5 pt (≈11 px) | `theme.py:160-168` | Densidad de "utilidad de escritorio"; sin jerarquía editorial |
| V-03 | M | **Regla `* { font-size: 9pt }`** pisa cualquier tamaño heredado y complica escalar la tipografía | `theme.py:160` | Bloquea una escala tipográfica real |
| V-04 | M | **Sin tokens de espaciado/radio/motion**: márgenes 2/6/12/16/24/28 y radios 7/8/10/12 sueltos; los tokens solo cubren color | `theme.py:26-51`; `dashboard.py:36-37,88-89` | Imposible garantizar la escala 4/8/12/16/24/32/48/64/80 |
| V-05 | M | **Colores hardcodeados fuera del tema**: `OrbitView` (`#007AFF/#6E6E73/#FF9F0A`), splash y ojo de la app (`#1D1D1F…`) | `aerospace.py:57-64`, `startup.py:67-88` | La órbita ignora el modo oscuro y cualquier cambio de paleta |
| V-06 | M | **La materialidad está reducida a 4 tonos + hairline** (sidebar/ground/card/field). No hay Popover/Dialog/Disabled como superficies, ni elevación | `theme.py:29-33`, `DESIGN.md` "Flat-By-Construction" | El brief pide `Background → Surface → Elevated → Popover/Dialog` |
| V-07 | M | **Sin iconografía** en ningún control (59 `QPushButton`, todos texto) | `grep QIcon` (solo el icono de ventana) | Navegación puramente textual; jerarquía de acciones débil (7–12 botones iguales en fila) |
| V-08 | M | **Motion casi inexistente**: solo el fade de 3 diálogos (0.85→1.0, apenas perceptible); `prompt_form`, `QMessageBox`, cambio de pestaña y cambios de estado no animan; sin modo *reduce motion* | `motion.py`; `grep pop_in` = 3 usos | Sensación de app estática; el motion no comunica relación espacial |
| V-09 | B | **Splash** con barra de progreso ficticia de 120 px fija (no refleja carga) | `startup.py:83-84` | Elemento decorativo que aparenta progreso |

### 2.E — Componentes duplicados

| Duplicación | Dónde | Consolidar en |
|---|---|---|
| Fila de estado (`QLabel` pill + `_set_state`) copiada 4 veces | `exercises.py:225`, `simulation.py:167`, `virtual_lab.py:418`, `logic_analyzer.py:384` | `StatusPill` compartido |
| Helper `_section(title)` con `QGroupBox` copiado 2 veces | `simulation.py:34`, `virtual_lab.py:49` | `Section` / `Panel` |
| Patrón "lista + fila de botones" en 3 sitios | `main_window.py:39-55`, `engineering.py:27-56`, `authoring.py:32-56` | `ListPanel` |
| Boilerplate `ServiceWorker` + `finished/failed` ×8 | exercises, simulation, virtual_lab, logic_analyzer | `run_task()` helper |
| Tres estilos de error (`show_ui_error`, `QMessageBox.warning(type(e))`, `show_value`) | toda la UI | Un único `Notice`/diálogo contextual |
| Salida de resultado `QTextEdit#Output` ×6 | todos los paneles | `ResultView` con tabla/valor/unidad |

---

## 3. Oportunidades

1. **Shell de producto**: 5 áreas (Home, Learn, Practice, Engineering, Settings) con navegación primaria lateral y contexto (asignatura) como estado global, no como sidebar fija. El menú `Go` ya contiene esa agrupación (`_build_go_menu`) → es el borrador real de la IA.
2. **Home con datos reales**: hay fuentes existentes sin usar — `queries.upcoming_deadlines/overdue_deadlines`, `app.records`, `search_history`, `app.exercises.library_keys()`, `app.digital.demos()`.
3. **Resultados como resultados**: `Measurement` (valor+unidad+estado) y `ScopeData/BodeData/SweepData` ya llegan al panel; hoy se descartan a texto. Dibujar es presentación pura (como ya hace `waveform.layout_waveform`, función pura testeable).
4. **Estados reales**: `Ready/Running/Computing/Success/Paused/Error/Offline` mapeables a lo que ya emite `ServiceWorker` y a `NOT_TRIGGERED`/`EQUIVALENT` del replay. No hace falta simular nada.
5. **Extender `Tokens`** (no reemplazar el mecanismo): añadir tipografía, espaciado, radio, duración; regenerar el QSS.
6. **Tutor**: `application/tutor.py` (F12) existe pero no está integrado (ver §5).

## 4. Elementos a conservar

- **Patrón de ejecución**: `ServiceWorker` (QThreadPool → señales), widgets nunca tocados desde el hilo (`workers.py`).
- **`UiState` + pill dinámica** (mecanismo), **`UiError` + conversor único D2** (contrato), **Ctrl+K**, **First-run**, **modo claro/oscuro/sistema**.
- **Logic Analyzer**: `layout_waveform` puro y testeable, etiquetas `H/L`, nombres accesibles, mensajes honestos (`NOT_TRIGGERED`, "traza cargada sin circuito: no se puede explicar sin inventarla"). Es el mejor ejemplo del estándar buscado.
- **Ética "sin funciones ficticias"** del Dashboard y de `PRODUCT.md` (aplicar también a H-01, H-04).
- **Frontera de arquitectura**: la UI solo consume application+domain; sin infra/SQLite/CAS (test `test_ui_consumes_only_application_and_domain`).
- **Contratos fijados por tests** (ver §6).

## 5. Elementos a rediseñar

Navegación y shell (U-01, U-03) · Home (H-04, H-05) · vistas académicas (U-02) · resultados y visualización (U-04) · Engineering: separar Digital Logic / Electronics / Aerospace (H-03) · Simulation/Virtual Lab (H-01, H-02, H-07) · diálogos y errores (U-05, U-06) · búsqueda/paleta (H-06) · tokens, tipografía, materialidad e iconografía (V-01…V-07) · motion (V-08) · foco/teclado/accesibilidad (S-02…S-04) · persistencia de estado de UI (S-06).

**Hallazgo estructural — Learn/Practice/Tutor:** no existe ninguna UI para F9 (sesiones), F10 (mastery), F11 (plan adaptativo) ni F12 (tutor). `grep -i tutor src/academic_core/ui` = 0 coincidencias y `facade.py` no expone tutor/sesiones/mastery. "Learn/Practice" hoy se reduce a Overview/Resources y Exercises. El Prompt 8 no es un rediseño sino **exponer por la fachada** (application, no core matemático) lo que ya está certificado; conviene decidirlo explícitamente antes de ese paso.

## 6. Dependencias y riesgos

| Riesgo | Detalle | Mitigación |
|---|---|---|
| **Tests fijan la estructura actual** | `tabs.count() == 13` en `test_ui.py:18`, `test_ui_authoring.py:23`, `test_ui_engineering.py:17`; `tabText(0) == "Dashboard"` (`test_f15_app.py:78`); `tabText(count-2) == "Logic Analyzer"`; atributos de widgets (`win.tabs`, `btn_*`, `status`, `output`…) | Mantener el `QTabWidget` de 13 páginas como **contenedor real** (oculto o detrás de un `QStackedWidget`) y construir el shell encima, como ya hizo `navigate_to`; o actualizar los tests conscientemente en un commit aparte y documentado |
| Frontera de arquitectura | `test_ui_consumes_only_application_and_domain` prohíbe infraestructura en `ui/` | No introducir imports nuevos de `infrastructure` |
| Deuda existente de límites | `simulation.py` y `virtual_lab.py` construyen specs de `domain.engineering.lab.model`/`mna` dentro del widget, contradiciendo su docstring ("no solver internals in widgets") | No empeorar; idealmente mover la construcción a `SimulationService`/`LabService` (application) en el paso de laboratorios |
| Motores certificados | F0–F16, cálculos, persistencia | Prohibido tocar; el rediseño consume las mismas APIs |
| Exposición de F9–F12 | Requiere ampliar la fachada | Decisión previa al Prompt 8 |
| Ejecución real no verificada | DPI, foco visible, contraste, resize | Capturas y pruebas manuales en Prompts 11–13 |
| `DESIGN.md` ya "canónico" | Documenta el mundo Apple y reglas ("no shadows", "no kickers") que el brief invalida parcialmente | Reemplazarlo por `DESIGN-SYSTEM-2026.md` (Prompt 3) y dejar `DESIGN.md` como puntero |

## 7. Resumen ejecutivo

La base técnica es sólida (workers, estados, errores, tokens, frontera de capas) pero la **experiencia** es la de un panel de pruebas: 13 pestañas planas, vistas de volcado de texto, resultados sin visualización, diálogos genéricos, tipografía de 9 pt y una paleta que imita a Apple. Además hay cuatro incumplimientos de honestidad concretos (H-01 Scenario decorativo, H-03 Aerospace mal enrutado, H-04 saludo fijo, H-06 búsqueda que solo abre el primer resultado). El Logic Analyzer es el patrón a seguir. El mayor bloqueo estructural es que **F9–F12 no tienen superficie de UI**.

Prioridad sugerida para los siguientes prompts: IA (P2) → tokens de escala/espaciado/materialidad (P3) → shell sobre el `QTabWidget` existente (P4) → resto.

---
`UX AUDIT COMPLETE — NO CODE CHANGED`
