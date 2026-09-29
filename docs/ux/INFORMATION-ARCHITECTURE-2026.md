# Information Architecture 2026 — AcademicCore

Estado: **diseño, sin implementación** (Prompt 2). Entrada: `docs/ux/UX-AUDIT-2026.md`.
Decisión previa confirmada por el usuario: **F9–F12 (sesiones, mastery, plan adaptativo, tutor) se exponen por la fachada `application`** en el paso de Learn/Practice/Tutor (Prompt 8), sin tocar cálculos ni contratos.

---

## 1. Cambio de modelo mental

```
Antes:   VIEW → VIEW → VIEW            (13 pestañas planas + menú Go duplicado)
Después: WORKSPACE → CONTEXT → TASK → TOOLS → RESULT
```

| Nivel | Pregunta que responde | Ejemplo |
|---|---|---|
| **Workspace** | ¿En qué área estoy? | Engineering |
| **Context** | ¿Sobre qué trabajo? | Asignatura *Circuitos I* · módulo *Digital Logic* |
| **Task** | ¿Qué quiero hacer? | Capturar una traza con disparo |
| **Tools** | ¿Con qué? | Canales, trigger, ventana |
| **Result** | ¿Qué obtuve? | Forma de onda, tabla de transiciones, digest |

Principios que gobiernan las decisiones (prueba del tronco: tapando el contenido, el usuario sigue sabiendo **dónde está, dónde puede ir y qué es aplicable**):

1. Una sola navegación primaria, persistente, de 5 elementos.
2. El **contexto** (asignatura activa) es estado global visible, no una barra lateral permanente.
3. Ninguna acción aparece donde no es aplicable (adiós a los 7 botones globales).
4. Nada se elimina: las 13 vistas siguen existiendo, con nueva ubicación.
5. **Sin enlaces muertos:** una sección que aún no tiene backend expuesto no aparece en la navegación (regla de honestidad de `PRODUCT.md`).
6. Claridad sobre consistencia; sustracción por defecto.

---

## 2. Estructura de primer nivel

```
AcademicCore
├── Home            Dónde estoy, qué puedo continuar, qué viene
├── Learn           Asignaturas, actividades, notas, planificación, biblioteca, documentos, (mastery, tutor*)
├── Practice        Ejercicios, matemáticas paso a paso, (sesiones/exámenes*, plan adaptativo*)
├── Engineering     Circuits · Analysis · Lab · Digital Logic · Aerospace
└── Settings        Apariencia, datos, importar/exportar, acerca de
                    (* = requiere exponer F9–F12 por la fachada; ver §9)
```

Orden y semántica: de lo general (Home) a lo específico; Settings siempre al final y anclado abajo.

---

## 3. Mapa de las 13 vistas actuales (sin perder funcionalidad)

| # | Vista actual (pestaña) | Nuevo destino | Ruta | Cambio de rol |
|---|---|---|---|---|
| 0 | Dashboard | **Home** | `home` | Entrada real al producto |
| 1 | Overview | Learn › Subject › **Summary** | `learn/subject/summary` | Pasa de volcado de texto a ficha de asignatura |
| 2 | Activities | Learn › Subject › **Activities** | `learn/subject/activities` | Tabla agrupada por tipo y estado |
| 3 | Grades | Learn › Subject › **Grades** | `learn/subject/grades` | Cifras con unidad/estado; veredicto y gradebook |
| 4 | Planning | Learn › Subject › **Planning** | `learn/subject/planning` | Próximas y vencidas; también alimenta Home |
| 5 | Resources | Learn › **Library** | `learn/library` | Búsqueda + detalle + procedencia |
| 6 | Authoring | Learn › **Documents** | `learn/documents` | Editor de bloques con ciclo de vida |
| 7 | Engineering | Engineering › **Circuits** (+ punto de entrada de módulos) | `engineering/circuits` | Proyectos, circuitos, netlist, cálculos |
| 8 | Exercises | Practice › **Exercises** | `practice/exercises` | Problema, entradas, trabajo, resultado |
| 9 | Simulation | Engineering › **Analysis** | `engineering/analysis` | Ejecución de OP/AC/TRAN/DC |
| 10 | Virtual Lab | Engineering › **Lab** | `engineering/lab` | Sesiones, instrumentos, replay |
| 11 | Logic Analyzer | Engineering › **Digital Logic** | `engineering/digital-logic` | Captura, forma de onda, transiciones |
| 12 | Settings | **Settings** | `settings` | Apariencia, datos, acerca de |
| — | `OrbitPanel` (dentro de Engineering) | Engineering › **Aerospace** | `engineering/aerospace` | Deja de ser un bloque embebido bajo el netlist |
| — | 7 botones globales (Add topic… Export/Import JSON) | Ver §5.3 | — | Se reubican por contexto |
| — | Sidebar del árbol académico | **Selector de contexto** (§4) + panel de contexto en Learn | — | Ya no ocupa 300 px en todas las pestañas |
| — | `SearchDialog` (Ctrl+K) | **Command palette** global (§7) | — | Contenido + navegación + comandos |
| — | `ModulesDialog` | Engineering › índice de módulos | `engineering` | Corrige H-03 (Aerospace apuntaba a Simulation) |
| — | Dock "Session log" | **Actividad** (panel lateral opcional, §4.4) | — | Deja de ser texto estático |

Secciones nuevas (reservadas, visibles solo cuando exista backend en la fachada):

| Sección | Área | Ruta | Fuente |
|---|---|---|---|
| Mastery | Learn | `learn/mastery` | F10 |
| Tutor (panel contextual) | Learn/Practice | `panel:tutor` | F12 |
| Sessions / Exams | Practice | `practice/sessions` | F9 |
| Adaptive plan | Practice | `practice/plan` | F11 |

---

## 4. Estructura del shell

### 4.1 Anatomía

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ▣ AcademicCore   Learn › Circuitos I › Grades       [⌘ Buscar… Ctrl+K]  ◐ ● │  ← Top bar
├────────┬───────────────────────────────────────────────────┬───────────────┤
│  Home  │  Summary  Activities  Grades  Planning  Mastery*  │               │  ← Nav contextual
│ ▸Learn │───────────────────────────────────────────────────│  Panel        │
│ Practice│                                                   │  lateral      │
│ Engin. │             ÁREA DE CONTENIDO (workspace)          │  (Tutor* /    │
│        │       Context → Task → Tools → Result             │  Inspector /  │
│        │                                                   │  Actividad)   │
│Settings│                                                   │               │
├────────┴───────────────────────────────────────────────────┴───────────────┤
│ ● Ready · offline · v0.x · datos: …\AcademicCore\data                        │  ← Estado global
└────────────────────────────────────────────────────────────────────────────┘
```

| Zona | Contenido | Regla |
|---|---|---|
| **Navegación primaria** (izquierda, 5 ítems) | Home, Learn, Practice, Engineering; Settings anclado abajo | Siempre visible; resalta el área actual; colapsable a iconos; nunca cambia según la vista |
| **Top bar** | Migas de pan · selector de contexto · búsqueda/comandos · tema · estado offline | Las migas solo si profundidad ≥ 3 (§6) |
| **Navegación contextual** (bajo el top bar) | Secciones del área actual (segmentado/pestañas ligeras) | Máx. 6 ítems; cambia con el área |
| **Contenido** | Workspace activo | Sin navegación propia; usa Context→Task→Tools→Result |
| **Panel lateral** (derecha, opcional) | Tutor, Inspector, Actividad | Se abre a demanda, recuerda su estado; `Esc` lo cierra |
| **Estado global** | Estado real del motor/backends, offline, ruta de datos | Solo información verificable |

### 4.2 Contexto global

- **Contexto activo = asignatura** (`subject stable_id`) — hoy vive como selección del árbol.
- Se muestra como *chip* en el top bar (`Circuitos I ▾`); un clic abre un **selector en popover** con el árbol Universidad→Grado→Año→Periodo→Asignatura (misma fuente `queries.tree()`), con búsqueda.
- En **Learn** el árbol se muestra además como **panel de contexto** izquierdo (navegación de datos, no de producto). En Practice/Engineering el contexto es opcional y solo se usa para vincular resultados a la asignatura.
- Sin asignatura activa, las secciones que la requieren muestran un estado vacío con acción: «Elige una asignatura».
- Persistencia: la asignatura activa se restaura al abrir.

### 4.3 Navegación por nivel

| Nivel | Qué es | Dónde | Ejemplos |
|---|---|---|---|
| Primaria | Áreas | Rail izquierdo | Home · Learn · Practice · Engineering · Settings |
| Secundaria | Secciones del área | Barra bajo top bar | Learn: Subject, Library, Documents · Engineering: Circuits, Analysis, Lab, Digital Logic, Aerospace |
| Terciaria (contextual) | Modos/pasos dentro de un workspace | Dentro del contenido | Subject: Summary/Activities/Grades/Planning · Lab: Setup/Run/Results |
| Global | Cruza áreas | Ctrl+K | Ir a…, buscar contenido, ejecutar comando |

### 4.4 Panel lateral (derecha)

| Panel | Contenido | Disponible |
|---|---|---|
| Inspector | Detalle del elemento seleccionado (procedencia, digest, ids) — donde hoy se muestran ids crudos | Siempre |
| Actividad | Ejecuciones y eventos reales de la sesión (sustituye al "Session log" estático) | Siempre |
| Tutor | Ayuda socrática ligada al problema actual (F12) | Solo con F12 expuesto |

---

## 5. Definición por área: Workspace → Context → Task → Tools → Result

### 5.1 Home

| Capa | Contenido | Fuente real |
|---|---|---|
| Context | Saludo por hora real + asignatura activa | reloj + selección |
| Task (acción primaria) | **Continuar** lo último (último ejercicio/lab/documento/asignatura) | `search_history` + registros recientes; si no hay → «Empezar» |
| Tools | Accesos a las 4 áreas con conteos reales | `exercises.library_keys()`, `digital.demos()`, `records.all_ids()` |
| Result | Próximas entregas/exámenes y vencidas | `queries.upcoming_deadlines/overdue_deadlines` |

Acción primaria: **Continuar**. Secundarias: abrir área, Ctrl+K. Estados: primer uso (sin datos → guía honesta), con datos, error parcial (una fuente falla sin romper el resto: se conserva `_safe`).

### 5.2 Learn

Secciones: `Subject` (Summary · Activities · Grades · Planning) · `Library` · `Documents` · `Mastery`*.

| Capa | Subject | Library | Documents |
|---|---|---|---|
| Context | Asignatura activa (panel de árbol) | Asignatura opcional como filtro | Documento abierto |
| Task | Ver/registrar avance | Buscar, importar, indexar | Editar bloques, guardar versión |
| Tools | Menú **Nuevo ▾** (topic/assignment/task/exam), Registrar nota | Importar, Reindexar, Construir documento | Aplicar bloque, Validar, Enlazar, Ciclo de vida, Deshacer/Rehacer |
| Result | Tablas y cifras con estado; veredicto de notas | Detalle con procedencia y digest | Estado (rev, versión, limpio/sucio), exportar MD/HTML |

Acción primaria por sección: Subject → *Nuevo*; Library → *Importar*; Documents → *Guardar (nueva versión)*.

### 5.3 Reubicación de las acciones globales

| Acción actual | Nuevo lugar |
|---|---|
| Add topic / assignment / task / exam | `Nuevo ▾` en Learn › Subject (habilitado solo con asignatura activa) |
| Record grade | Acción primaria contextual de Learn › Subject › Grades |
| Add… / Delete (árbol) | Menú contextual del selector de contexto (clic derecho / `⋯`) |
| Export JSON / Import JSON | Settings › Datos |
| Import file / Reindex / Build document | Learn › Library |

### 5.4 Practice

Secciones: `Exercises` · `Sessions`* · `Plan`*.

| Capa | Exercises |
|---|---|
| Context | Ejercicio de la biblioteca (o asignatura/tema vinculado) |
| Task | Resolver; pedir explicación paso a paso; matemáticas (derivar, integrar, resolver, simplificar) |
| Tools | Entradas estructuradas (variable, valor, unidad), Solve, Explicar, Paso a paso |
| Result | Resultado + digest + traza pedagógica; estado real |

Acción primaria: **Resolver**. Matemáticas pasa a modo (segmentado) dentro de Exercises, no a una fila de 7 botones.
**Tutor** (F12) es un panel lateral del problema en curso, no una vista: la cadena determinista se mantiene
`LLM proposal → validation → policy → F9 correct_answer → verification → VerifiedResponse`, y el panel solo muestra el `VerifiedResponse` con su estado *verified / unverified / rejected*. Si el proveedor es `NullProvider` (LLM=OFF), el panel dice «Tutor desactivado» y no ofrece entrada de chat.

### 5.5 Engineering

Índice del área (`engineering`) = **selector de módulos**: Electronics · Digital Logic · Aerospace (mismo `module_index`, ahora navegable con destino correcto).

| Sección | Vista actual | Context | Task | Tools | Result |
|---|---|---|---|---|---|
| Circuits | EngineeringPanel | Proyecto → circuito | Definir topología/cálculo | Añadir componente, Calcular, estado de backends | Netlist, avisos de topología, cálculos con digest |
| Analysis | SimulationPanel | Circuito de escenario real | Elegir análisis (OP/TRAN/AC/DC) | Parámetros del análisis | Medidas con valor+estado+digest; visualización |
| Lab | VirtualLabPanel | Sesión (`f8n-lab/1`) | Experimento: estímulos, sondas | Instrumentos, Run, Replay, Explicar | Lecturas de instrumentos, replay equivalente/no |
| Digital Logic | LogicAnalyzerPanel | Circuito digital demo | Captura con disparo | Canales, trigger, ventana | Forma de onda, tabla de transiciones, explicación |
| Aerospace | OrbitPanel | Cuerpo central (Earth) | Órbita circular | Altitud | v, T, v_esc; vista de órbita |

Modelo de cada workspace de ingeniería (para el Prompt 6/7): `Context → Inputs → Tools → Visualization → Instruments → Results → History/Replay`, con zonas separadas: parámetros | herramientas | visualización | resultados | historial.

### 5.6 Settings

Secciones: `Appearance` · `Data` (carpeta, importar/exportar JSON) · `About` (versión, licencia, esquemas, estado de backends). Sin jerga de gate/fase (se elimina «GREELEC…» de la UI de usuario; permanece en documentación).

---

## 6. Rutas, migas y navegación hacia atrás

### 6.1 Esquema de rutas

`area[/section[/item]]` — cadena estable, única fuente de verdad de la navegación.

| Ruta | Destino (widget) |
|---|---|
| `home` | Dashboard |
| `learn/subject/{summary\|activities\|grades\|planning}` | Overview / Activities / Grades / Planning |
| `learn/library` | Resources |
| `learn/documents` | Authoring |
| `practice/exercises` | Exercises |
| `engineering` | Índice de módulos |
| `engineering/circuits` · `/analysis` · `/lab` · `/digital-logic` · `/aerospace` | Engineering · Simulation · Virtual Lab · Logic Analyzer · OrbitPanel |
| `settings/{appearance\|data\|about}` | Settings |

**Compatibilidad:** las claves actuales de `navigate_to` (`home, overview, engineering, exercises, simulation, lab, logic, resources, settings`) siguen aceptadas y se traducen a rutas; los atributos de widget y el orden de las 13 páginas no cambian (ver §10).

### 6.2 Migas de pan

Solo cuando aportan orientación (profundidad ≥ 3 o contexto de datos):

- `Learn › Circuitos I › Grades` ✔
- `Engineering › Digital Logic › Captura #3` ✔
- `Home`, `Settings`, `Practice › Exercises` ✘ (la navegación primaria+contextual ya lo dice)

Cada tramo es clicable. El último tramo es texto.

### 6.3 Atrás / adelante

- Pila de historial de rutas (con contexto y selección) — **Alt+←** / **Alt+→**, botón atrás del ratón.
- `Esc` cierra, por orden: diálogo → popover → panel lateral. No navega hacia atrás.
- Atrás desde la raíz de un área no hace nada (no sale del producto).
- Deep-link interno: cualquier resultado de Ctrl+K abre su ruta exacta (p. ej. una asignatura → `learn/subject/summary` con ese contexto).

---

## 7. Command / search (Ctrl+K)

Tres grupos en una sola paleta, con lista navegable por teclado (↑/↓, Enter, Esc):

| Grupo | Contenido | Fuente |
|---|---|---|
| Ir a | Áreas y secciones («Ir a Digital Logic») | tabla de rutas |
| Contenido | Asignaturas, tareas, notas, documentos | `UnifiedSearchService` (sin segundo motor) |
| Comandos | «Nueva tarea», «Importar recurso», «Cambiar tema», «Abrir carpeta de datos» | acciones registradas por vista |

Reglas: un resultado sin destino navegable **no se muestra** (corrige H-06); Enter abre el resultado *seleccionado*, no siempre el primero; estado vacío con sugerencia; recientes al abrir sin texto.

Atajos globales: `Ctrl+K` paleta · `Ctrl+1…5` áreas · `Alt+←/→` historial · `Ctrl+,` Settings · `F6` cicla regiones (nav → contenido → panel) · `Esc` cierra capa superior.

---

## 8. Estados

### 8.1 Estados de workspace (contenido)

| Estado | Cuándo | Presentación |
|---|---|---|
| Vacío (sin contexto) | Falta asignatura/proyecto | Mensaje + acción primaria («Elegir asignatura») |
| Vacío (sin datos) | Existe contexto sin registros | Mensaje honesto + acción de crear |
| Cargando | Consulta en curso | Indicador de progreso ligado a la tarea |
| Listo | Datos disponibles | Contenido |
| Error parcial | Una fuente falla | La sección afectada explica el fallo; el resto sigue |
| Error | Fallo de operación | Mensaje UI-safe (problema + acción) vía conversor único D2 |

### 8.2 Estados de ejecución (labs, análisis, ejercicios)

Extensión del enum `UiState` (hoy 5 estados) a los que pide el brief, **solo con causa real**:

| Estado | Causa real | ¿Existe hoy? |
|---|---|---|
| Ready | Configuración válida, sin ejecución | sí (IDLE) |
| Running | `ServiceWorker` en curso | sí |
| Computing | Fase de cálculo del motor tras la validación | mapeable (explain/detalle) |
| Success / Warning | Resultado / `NOT_TRIGGERED`, `unverified` | sí |
| Error | Excepción convertida a `UiError` | sí |
| Offline | Backend opcional no disponible (`backend_status_lines`, Stirling) | dato real, hoy en texto |
| Paused | **No existe capacidad de pausa** en los motores | **no se muestra** hasta que exista |

La pill no lleva texto libre: estado + un detalle corto secundario.

---

## 9. Relaciones entre módulos

```
                    ┌─────────────── Ctrl+K (búsqueda/ir a/comandos) ───────────────┐
                    │                                                               │
   Learn ── Subject ─┬─ Library ──(procedencia, digest)──► Documents (enlaces academic-link)
     │  (contexto)   │                                          ▲
     │               └─ Planning ──► Home (próximas/vencidas)    │ enlaza subject/topic/lab
     ▼                                                          │
  Practice ── Exercises ──(Explain)──┐                          │
     │   └── Sessions*/Plan* ◄── F9/F10/F11 ──► Mastery* (Learn)│
     │                                                          │
     └── Tutor* (panel) ──(VerifiedResponse via F9)──► Exercises/Sessions
                                                                │
  Engineering ── Circuits ─► Analysis ─► Lab ──(Explain/Replay)─┘  (resultados enlazables a Documents)
              ├─ Digital Logic (traza digital-trace/1)
              └─ Aerospace (F16)
```

Relaciones normativas:

1. **Contexto → todo:** la asignatura activa etiqueta ejercicios, sesiones y documentos.
2. **Engineering → Learn:** un resultado o run se puede enlazar a un documento (los `academic-link` kinds ya existen: subject/topic/assignment/project/lab/exam).
3. **Practice ↔ Learn:** los ejercicios se vinculan a temas; el progreso (F10) se lee desde Learn › Mastery.
4. **Tutor:** solo como capa sobre un problema concreto; nunca autoridad — muestra el `VerifiedResponse`, no una respuesta libre.
5. **Explain (E0–E0.3):** desde Exercises y Lab con la misma presentación de «traza → pasos».
6. **Home** solo consume; no posee datos.

### Exposición de F9–F12 (dependencia del Prompt 8)

Decisión tomada: se exponen por la fachada. Alcance de esa tarea (no del rediseño visual): añadir a `AcademicApp` los servicios de sesión (F9), mastery (F10), plan (F11) y tutor (F12) con vistas de solo lectura/valores planos, sin modificar dominio ni motores. Hasta entonces esas secciones **no aparecen** en la navegación.

---

## 10. Restricciones de implementación heredadas (para el Prompt 4)

| Restricción | Consecuencia en el diseño |
|---|---|
| Tests fijan `tabs.count() == 13`, `tabText(0) == "Dashboard"`, `tabText(count-2) == "Logic Analyzer"` y nombres de atributos | El shell **envuelve** el `QTabWidget` existente como pila de páginas (barra de pestañas oculta); el nuevo enrutador conmuta `setCurrentWidget`. Cero cambios en widgets internos para el 100 % de las páginas actuales |
| La UI solo consume `application` + `domain` | El enrutador y el shell viven en `ui/`; sin imports de infraestructura |
| `navigate_to` público (claves antiguas) | Se mantiene como fachada del nuevo enrutador |
| Secciones nuevas sin backend | Registradas con «capacidad disponible?»; ocultas si no |
| Sub-secciones de Subject (Summary/Activities/Grades/Planning) | Hoy son 4 pestañas del mismo `QTabWidget`; se mapean como rutas sobre esas mismas páginas y se re-presentan sin cambiar su contenido hasta el rediseño de Learn |

## 11. Persistencia de navegación

Se guarda en `QSettings`: última ruta, asignatura activa, estado del rail (expandido/colapsado), panel lateral (abierto y cuál), geometría de ventana. Restauración segura: ruta desconocida o sección no disponible → `home`.

## 12. Criterios de aceptación de la IA (para verificar en Prompt 4 y 12)

1. Desde cualquier pantalla se identifica área, sección y contexto sin leer el contenido (prueba del tronco).
2. Las 13 vistas siguen alcanzables por menú, paleta y ruta.
3. Ninguna acción visible falla por falta de contexto (se deshabilita con explicación o no se muestra).
4. Ningún enlace lleva a una vista distinta de la anunciada (H-03).
5. Toda la navegación es operable solo con teclado; `Esc` y `Alt+←` se comportan según §6.3.
6. Sin secciones que dependan de backend no expuesto.
7. Reabrir la app restaura ruta y contexto.

## 13. Decisiones registradas y preguntas abiertas

| Decisión | Motivo |
|---|---|
| Asignatura como contexto global, no sidebar fija | Libera ancho en Engineering/Practice y elimina acciones inaplicables |
| Aerospace como sección propia | Estaba escondida bajo el netlist y mal enrutada |
| Matemáticas dentro de Exercises (modo) | Evita 7 botones planos en una fila |
| Tutor como panel, no vista | Debe sentirse integrado al flujo, no un chatbot |
| Historial propio (Alt+←) | La pila de pestañas de Qt no tiene «atrás» |
| **Abierta:** ¿el rail primario muestra texto siempre o solo iconos al colapsar? | Se resolverá en el Design System (P3) según tamaño tipográfico |
| **Abierta:** ¿Documents dentro de Learn o área propia? | Se mantiene en Learn (5 áreas fijadas por el brief); revisar tras uso real |
| **Abierta:** ubicación exacta de Import/Export JSON (Settings › Data vs. menú de contexto) | Por defecto Settings › Data |

---

## 14. Estado de implementación (Prompt 4)

Implementado: rail primario (5 áreas, colapsable, persistente), top bar (migas, chip de contexto, búsqueda), barra de secciones por área, ruteador `ui/routes.py` con historial (`Alt+←/→`), `Ctrl+1…5`, `Ctrl+,`, paleta Ctrl+K con grupo «Go to», menú `New ▾` en Learn, Import/Export JSON en Settings, persistencia de ruta/asignatura/geometría/rail.

Desviaciones deliberadas respecto al diseño:

| Diseño | Implementado | Motivo |
|---|---|---|
| El área `Engineering` abre un índice de módulos | Abre la última sección visitada (por defecto *Circuits*); el índice sigue en `Go ▸ Engineering: Modules…` | El índice como página es trabajo del Prompt 6 |
| Panel lateral Inspector/Actividad | El dock «Session log» queda oculto por defecto (`View ▸ Session log`) | Sin contenido real que mostrar aún |
| Estado global en barra inferior | Se mantiene la barra de estado existente | Los estados de ejecución reales llegan con los Prompts 6–7 |
| Selector de contexto en popover | Chip en la top bar que abre Learn con el árbol como panel de contexto | El popover con búsqueda queda para Learn (Prompt 8) |
| `Go` menu con Documents/Aerospace | Se mantienen los 10 ítems actuales (test fijado); ambas rutas se alcanzan por la barra de secciones y por Ctrl+K | Evitar cambiar un contrato de test sin necesidad |

### 14.1 Home (Prompt 5)

Home usa solo datos reales: *Continue* = la actividad más reciente y resoluble entre las asignaturas abiertas (historial certificado `search_history`, tipo `asignatura`) y las secciones visitadas (registro propio de UI en `state_store`, porque el dominio solo admite los tipos de `SEARCH_KINDS`); *Coming up* = `queries.overdue/upcoming_deadlines`; *Tools* = conteos de los servicios. Restaurar la ruta al arrancar no cuenta como actividad. Sin actividad real, Home ofrece el siguiente paso honesto («Add a subject» / «Open Learn»). La nota «GREELEC» sale de Home y permanece en Settings.

### 14.2 Engineering y laboratorios (Prompts 6 y 7)

`engineering/circuits` y `engineering/aerospace` son dos workspaces dentro de la misma página fijada (`EngineeringPanel.set_workspace`), de modo que el número de páginas sigue siendo 13. `engineering/analysis` (Simulation), `engineering/lab` (Virtual Lab) y `engineering/digital-logic` comparten el esqueleto de laboratorio (DESIGN-SYSTEM §11). Corregido en el camino: `SimulationPanel` llamaba a `self.decimal` (inexistente), por lo que el análisis transitorio con su parámetro por defecto siempre fallaba.
