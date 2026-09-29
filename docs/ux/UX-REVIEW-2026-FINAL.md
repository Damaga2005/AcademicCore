# AcademicCore — Auditoría visual final (Prompt 12)

Fecha: 2026-09-29 · Rama `main` sobre `c6bf954` · Alcance: las 17 rutas de la aplicación tras los Prompts 1–11.

> Esto es una auditoría, no una certificación. No cambia código. La certificación (suite completa, separación de fallos) es el Prompt 13.

## 1. Método y límites

**Qué se hizo**
- Se renderizó la ventana real (Windows, Segoe UI, 1250×780, movimiento reducido para que la captura no pille el fundido) en **tres condiciones**: datos de ejemplo en claro, datos de ejemplo en oscuro, y base vacía en claro. 17 rutas × 3 = 51 capturas; se revisaron a ojo las de claro con datos y muestras de oscuro y vacío.
- Métricas automáticas por ruta: scroll horizontal, widgets enfocables, controles sin nombre accesible, botones de menos de 28 px, etiquetas o botones recortados (`sizeHint` mayor que el ancho real).
- Contraste WCAG calculado sobre los tokens del tema (ambas paletas).
- Redimensionado y DPI: mediciones del Prompt 11 (100/125/150/200 %).

**Qué NO se hizo (no se afirma nada sobre esto)**
- Recorrido completo con teclado ni lector de pantalla; solo recuento de widgets enfocables y nombres accesibles.
- Modo de contraste alto de Windows, ni estados hover/pressed capturados.
- Pruebas con personas usuarias.
- Estado *running* y diálogos de error capturados por pantalla (los diálogos se revisaron en el Prompt 9).
- Los datos de ejemplo son mínimos: una asignatura vacía, un banco de 4 preguntas y un intento. Con una asignatura con actividades, notas y fechas las pantallas de Learn se verán distintas, pero la **forma** (texto plano) es la del código, no depende de los datos.

## 2. Veredicto

El rediseño es **desigual**. Lo que se rehízo (carril y barra superior, Home, Ingeniería, laboratorios, Practice, diálogos, movimiento, comportamiento en Windows) se percibe como producto y es coherente en claro y oscuro. Lo que **no se tocó** sigue siendo la interfaz anterior y desentona:

| Se percibe como producto | Sigue siendo herramienta antigua |
|---|---|
| Shell, Home, Circuits, Analysis, Lab, Digital Logic, Aerospace, Sessions, Plan, Mastery, diálogos | Learn › Summary / Activities / Grades / Planning, Learn › Documents, Learn › Library, Settings |

Cuatro hallazgos de gravedad alta (F-01 a F-04) están todos en ese segundo grupo. Los Prompts 5–11 no los cubrían, así que no son regresiones, son trabajo no hecho.

## 3. Puntuación por pantalla

✔ correcto · ~ mejorable · ✘ débil. "Mov." (movimiento) es uniforme: fundido de página y de pastilla de estado en todas. "Nav." es uniforme: carril, migas y secciones. Contraste de texto cumple 4,5:1 en todas (ver F-17 para lo que no cumple).

| Pantalla | Jer. | Comp. | Esp. | Tipo | Cns. | Den. | Est. | Fdb. | A11y | Tec. | Rsz. | Prod. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Home | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Learn › Summary | ✘ | ✘ | ~ | ~ | ✘ | ~ | ✘ | ~ | ✔ | ✘ | ✔ | ✘ |
| Learn › Activities | ✘ | ✘ | ~ | ~ | ✘ | ~ | ✘ | ~ | ✔ | ✘ | ✔ | ✘ |
| Learn › Grades | ✘ | ✘ | ~ | ~ | ✘ | ~ | ✘ | ~ | ✔ | ✘ | ✔ | ✘ |
| Learn › Planning | ✘ | ✘ | ~ | ~ | ✘ | ~ | ✘ | ~ | ✔ | ✘ | ✔ | ✘ |
| Learn › Mastery | ✔ | ~ | ✔ | ✔ | ~ | ✔ | ~ | ✔ | ✔ | ~ | ✔ | ~ |
| Learn › Library | ✘ | ✘ | ~ | ~ | ✘ | ✘ | ✘ | ~ | ✘ | ~ | ✔ | ✘ |
| Learn › Documents | ✘ | ✘ | ~ | ~ | ✘ | ✘ | ✘ | ~ | ✘ | ~ | ✘ | ✘ |
| Practice › Exercises | ✔ | ~ | ✔ | ✔ | ~ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Practice › Sessions | ✔ | ~ | ~ | ✔ | ✔ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Practice › Plan | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ~ |
| Engineering › Circuits | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Engineering › Analysis | ✔ | ~ | ~ | ✔ | ✔ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Engineering › Lab | ✔ | ✔ | ~ | ✔ | ~ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Engineering › Digital Logic | ✔ | ~ | ~ | ✔ | ~ | ~ | ~ | ✔ | ✔ | ✔ | ✔ | ~ |
| Engineering › Aerospace | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ~ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Settings | ✘ | ✘ | ~ | ~ | ✘ | ✔ | ✔ | ✔ | ✘ | ~ | ✔ | ✘ |

Criterio de "Tec." (teclado): ✘ = la página no contiene ningún widget enfocable (medido: 0 en las cuatro de Learn por asignatura); ~ = enfocable pero con controles sin nombre o sin recorrido verificado; ✔ = enfocable y nombrado. **No es un recorrido real de teclado.**
Criterio de "A11y": ✘ = hay controles sin nombre accesible (medido: Library 3, Documents 4, Settings 1).

## 4. Hallazgos

Cada uno lleva pantalla, problema, evidencia, impacto y corrección concreta. Gravedad: **A** alta, **M** media, **B** baja.

### Gravedad alta

**F-01 · A · Learn › Summary, Activities, Grades, Planning**
- *Problema:* muestran volcados de texto plano en una caja de solo lectura, con identificadores internos y códigos de estado.
- *Evidencia:* Summary dice `subject: subject:c1` y `topics: 0 | refs: 0`; Activities `== assignments (0) ==`; Grades `grade=None evaluated=False state=sin_evaluar`; Planning `upcoming:` y `overdue:` vacíos. Código en `main_window.py` (líneas ~811–842: `setPlainText`). Las cuatro páginas tienen **0 widgets enfocables**.
- *Impacto:* es la primera pantalla que ve quien abre una asignatura, y parece una salida de depuración. Rompe la coherencia con Home y Practice.
- *Corrección:* reconstruir con el kit de workspace (`Panel`, `Metric`, `KeyValueList`, tabla) usando los mismos datos del servicio; estados vacíos con texto humano ("Sin actividades: crea la primera"); traducir códigos (`sin_evaluar` → "Sin evaluar"); la barra "New / Record grade" solo donde tenga sentido, no en Summary.

**F-02 · A · Learn › Documents**
- *Problema:* la página necesita 1164 px de ancho; a 1250 px de ventana desborda y aparece scroll horizontal.
- *Evidencia:* medido `hscroll=True`, `minimumSizeHint=1164`; en la captura los botones aparecen cortados ("Apply bloc", "Save (new vers", "Ex") y el editor de bloques queda fuera de vista. Es la única de las 17 rutas con desborde.
- *Impacto:* funciones inaccesibles sin desplazar; a 125–200 % de escala empeora.
- *Corrección:* dividir en tres columnas con `QSplitter` y anchos mínimos razonables; por debajo de ~1100 px apilar el editor bajo el esquema; nombrar los 4 controles sin nombre.

**F-03 · A · Settings**
- *Problema:* bloque de texto plano con jerga interna y controles estirados a todo el ancho.
- *Evidencia:* `lab schema: f8n-lab/1`, `GREELEC: no integration (UNKNOWN / REQUIRES INPUT)`, `storage: C:\...\Temp\...`; el desplegable "Appearance" y el botón "Open data folder" ocupan todo el ancho; sin paneles ni agrupación; hueco vacío el 60 % inferior.
- *Impacto:* la pantalla de ajustes es donde se percibe el cuidado de un producto; aquí parece configuración de desarrollo.
- *Corrección:* tres paneles (Appearance, Data, About) con `KeyValueList`; controles de ancho natural; mover "GREELEC" y "lab schema" a un pliegue "Diagnostics"; nombrar el desplegable.

**F-04 · A · Learn › Library**
- *Problema:* muestra el estado de un servicio interno y deja áreas sin explicación.
- *Evidencia:* `Stirling: NOT_INSTALLED (http://127.0.0.1:8080) · native PDF ready` (`main_window.py` ~865); la lista de resultados y la vista previa son cajas grandes vacías sin título ni estado vacío; 3 controles sin nombre (`QLineEdit`, `QListWidget`, `QTextEdit`).
- *Impacto:* la persona usuaria ve una URL local y un estado técnico que no puede accionar; no sabe qué hace cada área.
- *Corrección:* sustituir por "PDF: motor integrado"; el diagnóstico de Stirling a Settings › Diagnostics; `EmptyState` en resultados y vista previa; nombres accesibles.

### Gravedad media

**F-05 · M · Practice › Sessions — estado vacío recortado.** El texto "Choose the questions on the left and start an attempt" queda cortado ("start an attempt" apenas visible) en claro y oscuro; los enunciados de la lista se truncan sin puntos suspensivos ni tooltip y aparece un resto de barra de scroll horizontal. *Corrección:* altura mínima del panel Question para que quepa el `EmptyState`; `setTextElideMode(ElideRight)` + tooltip con el texto completo; `ScrollBarAlwaysOff` horizontal.

**F-06 · M · Español mezclado con inglés.** 13 literales en 3 ficheros: `Explicar`, `Paso a paso`, `Derivar`, `Integrar`, `Resolver ecuación`, `Simplificar`, `Matemáticas` (exercises.py); `Explicar`, `Explicar último`, `Explicar en detalle` (virtual_lab.py); `Selecciona una transición para ver por qué cambió.` (logic_analyzer.py), conviviendo con `Solve`, `Problem`, `Your inputs`. *Impacto:* percepción de producto inacabado. *Corrección:* decidir el idioma de la interfaz (el resto está en inglés) y unificar; si se quiere bilingüe, es un trabajo de i18n aparte y no un cambio de etiquetas.

**F-07 · M · Árbol académico — selección partida.** La fila seleccionada se pinta en dos tonos (zona de la rama y zona del texto) en claro y oscuro. *Corrección:* mismo color para `QTreeWidget::branch:selected` y `::item:selected`.

**F-08 · M · Tablas con cabeceras recortadas y barras de scroll residuales.** Circuits › Results ("U…" en lugar de "Unit"), Digital Logic › Transitions ("ne…" en lugar de "net"/"note"), y un tramo de barra horizontal en ambas. *Corrección:* `stretchLastSection`, anchos por columna, y política horizontal `AsNeeded` con anchos suficientes.

**F-09 · M · Paneles vacíos sin estado vacío.** Circuits (Projects y Circuits), Analysis › Results, Lab › Results, Aerospace › Orbit view, Plan › "Mastery used". Aparecen como cajas blancas sin explicación. *Corrección:* un `EmptyState` de una línea en cada uno, o `placeholder` descriptivo.

**F-10 · M · Learn › Mastery.** Las columnas "Concept / Mastery / Observations" no rellenan la tabla (contenido pegado a la izquierda, gran hueco); el indicador "Subject mastery" muestra "—" y "choose a subject" en dos tipografías; el dominio es un porcentaje en texto, sin barra. *Corrección:* columnas `Stretch`, números alineados a la derecha, delegado con barra de progreso, texto único "Elige una asignatura".

**F-11 · M · Desplegables y spinboxes.** El borde derecho del desplegable aparece cortado (doble borde) y las flechas del spinbox de Plan › Exercises se dibujan como barras vacías. *Corrección:* estilizar `::drop-down`, `::up-button`, `::down-button` con flechas dibujadas (ya existe `make_icon` en el shell).

**F-12 · M · Casillas (checkbox).** Marcadas se ven como un cuadrado relleno sin marca de verificación (limitación ya declarada en el Prompt 5). El estado depende solo del color. *Corrección:* dibujar la marca con `::indicator:checked` e imagen.

**F-13 · M · Ritmo vertical desigual.** Analysis, Lab y Sessions dejan una franja de ~40 px vacía entre la barra de herramientas y los paneles; Circuits, Exercises y Plan no. *Corrección:* mismo `spacing` en el esqueleto de laboratorio; quitar la altura reservada del aviso cuando no hay mensaje.

**F-14 · M · Digital Logic — barra de estado distinta.** Muestra una banda gris completa con "IDLE" en lugar de la pastilla de estado del resto de laboratorios, y su barra de herramientas reparte seis controles en una línea. *Corrección:* usar la pastilla en la barra; agrupar acciones secundarias.

**F-15 · M · Exercises › Mathematics.** Los cuatro botones (`Derivar`, `Integrar`, `Resolver ecuación`, `Simplificar`) quedan apretados en el borde inferior del panel, con etiquetas en dos líneas. *Corrección:* rejilla de columnas iguales con altura mínima y margen inferior.

### Gravedad baja

**F-16 · B · Aerospace.** Los presets de altitud ("420 · 20 200 · 35 786") no llevan etiqueta ni unidad; "Orbit view" está vacía antes de calcular. *Corrección:* etiquetas "LEO / MEO / GEO" con tooltip en km; texto guía en la vista.

**F-17 · B · Contraste (calculado, WCAG 2.x).**

| Par | Claro | Oscuro | Umbral |
|---|---|---|---|
| Texto principal sobre fondo/tarjeta | 17,6 / 18,9 | 17,3 / 16,0 | 4,5 ✔ |
| Texto secundario sobre fondo/tarjeta/campo | 4,97 / 5,33 / 4,75 | 7,2 / 6,7 / 6,2 | 4,5 ✔ |
| Texto secundario sobre *hover* | **4,38** | 5,34 | 4,5 ✘ claro |
| Acento como texto sobre fondo | 5,82 | 9,66 | 4,5 ✔ |
| Borde de control sobre tarjeta | 3,04 | 3,22 | 3,0 ✔ (justo) |
| Pastillas de estado (4) | 5,6–6,3 | 6,8–7,9 | 4,5 ✔ |
| **Asa de la barra de scroll** (`tertiary`) sobre fondo | **2,36** | **2,74** | 3,0 ✘ |
| Texto deshabilitado (`tertiary`) | 2,1–2,5 | 2,4–2,7 | exento (WCAG 1.4.3) |

*Corrección:* asa de scroll con `border_control`; oscurecer un paso `secondary` en el tema claro o cambiar el fondo de *hover*.
Nota: los botones no llevan borde y su relleno frente a la tarjeta es 1,07–1,12:1; se identifican por la etiqueta, lo cual es aceptable pero no cumple 1.4.11 si se exigiera fondo distinguible.

**F-18 · B · Nombres accesibles.** 8 controles sin nombre: Library (3), Documents (4), Settings (1). Los de las demás rutas están todos nombrados. *Corrección:* `setAccessibleName` en cada uno.

**F-19 · B · Foco inicial.** En Aerospace el campo "Altitude" recibe foco al entrar (anillo visible); en el resto de páginas el foco queda en el carril. Es coherente con "entrar en la herramienta", pero conviene documentarlo como decisión. *Corrección:* ninguna obligatoria; decidir si es política general.

## 5. Lo que está bien (con evidencia)

- **Home** (vacía y con datos): jerarquía clara, una acción primaria por estado, "Tools" con datos reales.
- **Tema claro/oscuro**: en las 17 capturas en claro y en las de oscuro revisadas (Home, Sessions) no hay texto ilegible ni zonas sin tema. El resto de capturas en oscuro se generaron pero no se revisaron una a una.
- **Redimensionado y DPI**: sin scroll horizontal en 4 escalas × 5 páginas (Prompt 11), salvo Documents (F-02) que no estaba en esa muestra.
- **Estados**: los cinco estados aplican pastilla coherente; durante `RUNNING` se bloquean las acciones que iniciarían otra ejecución.
- **Diálogos**: título, contexto, acción primaria/secundaria, Escape, foco inicial (Prompt 9).
- **Movimiento**: 100–180 ms, un disparo, sin bucles, colapsa con "reducir animaciones" (Prompt 10).
- **Aerospace y Lab**: mejores ejemplos de esqueleto de laboratorio.

## 6. Prioridad recomendada

1. **Antes de certificar (Prompt 13):** F-01, F-02, F-03, F-04. Son las cuatro pantallas que aún parecen la interfaz anterior; F-02 además es un desborde funcional.
2. **Mismo lote, coste bajo:** F-05, F-07, F-08, F-09, F-18 (recortes y estados vacíos; tocan QSS y un par de líneas por panel).
3. **Decisión de producto necesaria:** F-06 (idioma) y F-12 (marca de casilla).
4. **Después:** F-10, F-11, F-13 a F-17.

Si no se corrigen, deben figurar como **limitaciones conocidas** en `GATE-UX-2026-CERTIFICATION.md`; no se pueden omitir.

## 7. Correcciones aplicadas (tras la auditoría)

Se corrigieron los hallazgos y se **volvió a medir** con el mismo script (17 rutas × claro/oscuro con datos) y a revisar las capturas.

| Hallazgo | Estado | Qué se hizo |
|---|---|---|
| F-01 Learn (Summary/Activities/Grades/Planning) | Corregido | Nuevo `ui/subject_views.py` con `Panel`, `Metric`, `KeyValueList` y estados vacíos; nombre de asignatura en vez de `subject:c1`; códigos traducidos (`sin_evaluar` → "Not evaluated"); cada vista es enfocable con teclado; la barra "New / Record grade" ya no aparece en Summary. `toPlainText()` se mantiene para copiar y para los tests. |
| F-02 Documents | Corregido | `QSplitter` de tres paneles con anchos mínimos bajos y rejillas de botones; mínimo de la página **1164 → 754 px**; ya no hay scroll horizontal a 1250 px. |
| F-03 Settings | Corregido | Paneles Appearance, Data, About y Diagnostics; controles de ancho natural; columna de 720 px. La limitación GREELEC sigue visible (la fija un test) en Diagnostics. |
| F-04 Library | Corregido | Ya no muestra la URL ni `NOT_INSTALLED`: "PDF export: built-in engine"; el estado de Stirling pasó a Settings › Diagnostics; paneles Resources/Details con estado vacío. |
| F-05 Sessions | Corregido | `EmptyState` reserva la altura de su texto; enunciados con puntos suspensivos y tooltip; sin barra horizontal. |
| F-06 Idioma mezclado | **No corregido** | Las etiquetas en español (`Explicar`, `Paso a paso`, `Derivar`…) abren explicaciones cuyo contenido es español y está fijado por tests de los motores certificados E0–E3. Traducir solo las etiquetas dejaría botón en inglés y resultado en español. Es una decisión de producto (idioma de la interfaz o i18n completo); no se tomó. |
| F-07 Selección del árbol | Corregido | Token `selection` (opaco); la rama y la fila usan el mismo color. Antes el fondo translúcido se sumaba dos veces en oscuro. |
| F-08 Tablas | Corregido | Columnas que se reparten el ancho y sin barra horizontal (Circuits › Results, Mastery). Digital Logic › Transitions mantiene scroll horizontal (7 columnas) pero ya no recorta cabeceras. |
| F-09 Paneles vacíos | Corregido | `HintList` y textos guía en Projects, Circuits, Documents, "Mastery used", Results del laboratorio y vista de órbita. |
| F-10 Mastery | Corregido | Columna de dominio con barra (delegado), columnas repartidas, cabeceras alineadas. |
| F-11 Desplegables y spinboxes | Corregido | Flechas dibujadas desde los tokens (PNG con `@2x`) y sub-controles estilizados. |
| F-12 Casillas | Corregido | Marca de verificación dibujada; el estado ya no depende solo del color. |
| F-13 Ritmo vertical | Corregido | `Notice` sin altura cuando está vacío (compartido por labs y Practice). |
| F-14 Digital Logic estado | Corregido | Pastilla de estado en lugar de banda a todo el ancho. |
| F-15 Exercises › Mathematics | Corregido | Botones con altura mínima. |
| F-16 Aerospace | Corregido | Presets "LEO 420 / MEO 20 200 / GEO 35 786" en rejilla; texto guía en la vista de órbita. |
| F-17 Contraste | Corregido parcial | Asa de scroll pasa a `secondary` (≥ 3:1 en ambos temas) y el *hover* claro sube a 4,5:1. Sigue igual: los botones sin borde se distinguen por su etiqueta (relleno 1,07–1,12:1). |
| F-18 Nombres accesibles | Corregido | 0 controles sin nombre en las 17 rutas (antes 8). |
| F-19 Foco inicial | Sin cambio | Es una decisión de diseño (entrar en la herramienta), no un defecto. |

**Verificación posterior:** scroll horizontal en 0 de 17 rutas (antes 1), controles sin nombre 0 (antes 8), etiquetas o botones recortados 0 (antes 4). 12 tests nuevos en `tests/test_ux_polish.py`; se actualizaron 4 aserciones que fijaban el volcado de texto plano (`subject:fis`, `aprobada`, `complete=True`, `practice: …`) y una etiqueta de preset.

**Límites de esta segunda pasada:** no se repitió el recorrido con teclado ni lector de pantalla, y las capturas en oscuro se revisaron por muestreo, igual que en la primera.

