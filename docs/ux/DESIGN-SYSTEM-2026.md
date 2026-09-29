# Design System 2026 — AcademicCore

Estado: **especificación, sin implementación** (Prompt 3). Entradas: `UX-AUDIT-2026.md`, `INFORMATION-ARCHITECTURE-2026.md`.
Sustituye a `DESIGN.md` («Apple workbench») cuando se implemente el Prompt 4; hasta entonces `DESIGN.md` describe el código actual.

## 0. Carácter

> **Estación de trabajo de ingeniería, calmada y precisa.** Un instrumento: legible de un vistazo, denso donde el trabajo lo pide, sin ornamento.

| Debe sentirse | No debe sentirse |
|---|---|
| Windows 11 moderno (Fluent en proporciones y foco) | Windows 95, demo de Qt, formulario empresarial |
| Preciso, calmado, contemporáneo | SaaS genérico, clon de ChatGPT, clon de macOS, glassmorphism |
| Software académico profesional | Juguete o «dashboard de marketing» |

**Rasgos distintivos** (lo que lo hace propio y no genérico):
1. **Neutros cálidos** (`#F7F7F5`, no gris azulado) con **un único acento cian profundo** — tono de osciloscopio/instrumento, no azul Apple ni púrpura SaaS.
2. **Cifras como protagonistas:** valores y unidades en cifras tabulares, con más peso visual que las etiquetas.
3. **Jerarquía por espacio, tono y tipografía antes que por bordes.** Los bordes son la excepción (campos de entrada y foco).
4. **Honestidad visual:** cada estado del sistema tiene causa real (ver IA §8).

**Nota sobre el dato externo.** Se consultó la base de `ui-ux-pro-max` (`--design-system`, densidad 7 / movimiento 2 / varianza 3). Su recomendación de estilo/tipografía es de web (landing, GSAP, Google Fonts) y **no se adopta**; solo sirvió para confirmar la familia cian/teal como tono «ops/instrumento» y las reglas de foco visible y contraste. La paleta final se verificó calculando la razón de contraste WCAG de cada par (§3.4).

---

## 1. Realidades de Qt que condicionan el sistema

El diseño se especifica para lo que **PySide6/QSS puede cumplir**; lo que no, tiene un mecanismo explícito.

| Capacidad deseada | QSS | Mecanismo acordado |
|---|---|---|
| Colores, radios, padding, bordes, fuentes | ✔ | Hoja de estilo generada desde tokens |
| Sombras suaves | ✘ (`box-shadow` no existe) | `QGraphicsDropShadowEffect` **solo** en popovers/paleta (widgets sin marco); diálogos usan la sombra nativa de la ventana. En el resto, elevación **tonal** |
| Anillo de foco con separación (offset) | ✘ | Proxy de estilo/`FocusRing` pintado a medida; mínimo: borde de 2 px en acento |
| Transiciones CSS | ✘ | `QPropertyAnimation` con tokens de duración/curva |
| Iconos vectoriales teñibles | parcial | SVG con `QSvgRenderer`/`QIcon`, coloreado por token |
| Tabular figures / features OpenType | ✘ en QSS | `QFont.setFeature("tnum", 1)` (Qt ≥ 6.7) en widgets numéricos |
| Fuentes en px con DPI | ✔ (px lógicos) | Todo en **px lógicos**; Qt 6 escala por `devicePixelRatio` (125/150/200 %) |
| Tema claro/oscuro | ✔ | Dos instancias de `Tokens`; QSS regenerado en vivo |

Regla: **nada de `*{ font-size }` global** (bloquea la escala); el tamaño lo fija el rol (`objectName`/propiedad `role`) o `QFont` desde tokens.

---

## 2. Tokens de fundamentos

### 2.1 Tipografía

**Familia de interfaz:** `"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", sans-serif` (sistema Windows 11 → identidad nativa, sin empaquetar fuentes).
**Familia de pantalla (Display/Title):** `"Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI"`.
**Monoespaciada (solo texto de máquina: netlists, digests, código):** `"Cascadia Mono", Consolas, monospace`.
Decisión: **no empaquetar fuente** en esta fase (evita ampliar `THIRD_PARTY_NOTICES` y el instalador). Si se quisiera una identidad propia más adelante, la tarea es aislada.

| Rol | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|
| **Display** | 40 / 48 px | 600 | Título de Home y estados vacíos de página |
| **Title** | 28 / 36 px | 600 | Título de sección/workspace |
| **Section** | 20 / 28 px | 600 | Encabezado de grupo/panel |
| **Body** | 14 / 22 px | 400 | Texto, controles, tablas, listas (por defecto) |
| **Body-large** | 16 / 24 px | 400 | Lectura prolongada (Documents, explicaciones) |
| **Secondary** | 13 / 18 px | 400 | Etiquetas de campo, metadatos |
| **Caption** | 12 / 16 px | 400 | Notas, unidades secundarias, pies de procedencia |
| **Numeric** | = Body/Section | 500–600 + `tnum` | Valores medidos y resultados |

Reglas: máximo **dos pesos por pantalla** (400 y 600); nada bajo 12 px; el peso 500 solo en cifras. Mono nunca como «disfraz técnico» de prosa.
Equivalencia pt→px (Qt a 96 dpi lógicos): 9 pt = 12 px; el cuerpo anterior de 9 pt pasa a 14 px (+17 %).

### 2.2 Espaciado

Escala única: **`4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 80`** (`space-1 … space-9`). Prohibidos los valores fuera de escala.

| Uso | Token |
|---|---|
| Separación icono–texto | 8 |
| Padding interno de control | 8 vertical / 12 horizontal (denso) · 12 / 16 (estándar) |
| Entre campos de un formulario | 16 |
| Padding de card/panel | 16 (compacto) · 24 (estándar) |
| Entre secciones de una página | 32 |
| Margen de página | 32 (≥1280 px) · 24 (<1280 px) |
| Aire editorial (Home, estados vacíos) | 48–80 |

Densidad: dos modos declarados — **Standard** (por defecto) y **Compact** (tablas/instrumentos: alto de fila 28 px y padding −4).

### 2.3 Forma y elevación

Radios: `r-sm 4` (badges, checkboxes) · `r-md 8` (controles, campos) · `r-lg 12` (cards, paneles, popovers) · `r-xl 16` (diálogos) · `r-full` (pills).
Grosores: hairline 1 px; foco 2 px.

**Materialidad** — `Background → Surface → Elevated → Popover → Dialog`:

| Capa | Función | Cómo se separa (prioridad) |
|---|---|---|
| **Background** | Lienzo de la app | Tono base |
| **Surface** | Cards, paneles, tablas | 1º tono (más claro/oscuro que el fondo), 2º espacio; sin borde |
| **Elevated** | Controles y regiones que se apoyan sobre una superficie (campos, pistas de segmentados, cabeceras de tabla, hover) | Tono; el campo lleva borde de control (§2.5) |
| **Popover** | Menús, combos abiertos, tooltips, paleta Ctrl+K | Tono + sombra suave (`QGraphicsDropShadowEffect`, 0/8/24 px, 12–18 %) |
| **Dialog** | Modales | Tono + sombra nativa de ventana + velo sobre la app (opacidad 32 %) |
| **Disabled** | Controles no disponibles | Tono apagado + texto atenuado (exento de contraste) |

En **modo claro** Surface = blanco puro sobre Background cálido: el contraste tonal es sutil (1.05:1), por eso **el espacio y la sombra de popovers hacen el trabajo** y las cards pueden llevar un hairline `#E6E6E3` *solo* si la densidad lo exige. En **modo oscuro** la elevación es **más claridad** (`#111 → #1A1A1A → #202020 → #262626 → #2B2B2B`).

> Interpretación del brief: el brief lista `#F7F7F5 / #FFFFFF / #F2F2F0` para el claro. Se respeta: Background = `#F7F7F5`, Surface = `#FFFFFF`, y `#F2F2F0` se usa como **capa Elevated de controles** (campos, pistas de segmentados, cabeceras), que en claro es un «pozo» tonal sobre la superficie. Popover y Dialog son `#FFFFFF` (+ sombra).

### 2.4 Movimiento

| Token | Duración | Uso |
|---|---|---|
| `motion-instant` | 0 ms | Reduce-motion; cambios de valor |
| `motion-fast` | 100 ms | Hover, pressed, foco, tooltip |
| `motion-base` | 140 ms | Cambio de estado, aparición/desaparición de popover, pill |
| `motion-slow` | 180 ms | Panel lateral, cambio de sección, diálogo |

Curvas: entrada `OutCubic`, salida `InCubic` (**salida ≈ 70 % de la entrada**). Prohibido: rebotes, zoom > 2 %, animación permanente, parpadeo. Único elemento con animación continua permitida: el indicador de progreso *indeterminado* mientras existe una ejecución real.
**Reduce motion:** si Windows tiene desactivados los efectos de animación (`SPI_GETCLIENTAREAANIMATION`), todas las duraciones pasan a `motion-instant`.
Movimiento permitido solo si comunica estado o relación espacial (ver §6).

### 2.5 Iconografía

Conjunto único de **iconos lineales de 1.5 px** en rejilla 16 px (20 px en navegación). Fuente propuesta: *Fluent System Icons* (MIT) empaquetados como SVG; se añade a `THIRD_PARTY_NOTICES.md` al implementar. Color por token (`icon-default`, `icon-accent`, `icon-disabled`); nunca emoji. Todo botón solo-icono lleva `accessibleName` y tooltip.

---

## 3. Color

### 3.1 Un solo acento

**Cian profundo (instrumento).** Un único acento por modo; el resto es neutro. Se gasta en: selección/ítem activo, acción primaria, foco, progreso, enlace. Nunca en decoración.

### 3.2 Tema claro

| Token | Valor | Notas |
|---|---|---|
| `bg` | `#F7F7F5` | Background |
| `surface` | `#FFFFFF` | Surface / Popover / Dialog |
| `elevated` | `#F2F2F0` | Capa Elevated (controles, cabeceras) |
| `disabled` | `#ECECE9` | Fondo deshabilitado |
| `text` | `#111111` | Texto principal |
| `text-secondary` | `#6B6B6B` | Secundario y placeholders |
| `text-disabled` | `#A3A3A0` | Solo deshabilitado |
| `divider` | `#E6E6E3` | Separadores decorativos |
| `border-control` | `#949490` | Contorno de campos (no texto ≥ 3:1) |
| `accent` | `#0A6A7C` | Acento (relleno primario, foco, selección) |
| `accent-text` | `#0A6A7C` | Texto/enlace en acento |
| `accent-on` | `#FFFFFF` | Texto sobre relleno acento |
| `accent-soft` | `#E1F1F4` | Fondo de selección |
| `hover` | `rgba(17,17,17,0.05)` | Overlay hover |
| `pressed` | `rgba(17,17,17,0.09)` | Overlay pressed |
| `scrim` | `rgba(17,17,17,0.32)` | Velo de diálogo |

### 3.3 Tema oscuro

| Token | Valor | Notas |
|---|---|---|
| `bg` | `#111111` | Background |
| `surface` | `#1A1A1A` | Surface |
| `elevated` | `#202020` | Elevated |
| `popover` | `#262626` | Popover |
| `dialog` | `#2B2B2B` | Dialog |
| `disabled` | `#1E1E1E` | Fondo deshabilitado |
| `text` | `#F5F5F5` | Principal |
| `text-secondary` | `#A0A0A0` | Secundario |
| `text-disabled` | `#5A5A5A` | Deshabilitado |
| `divider` | `#2E2E2E` | Separadores |
| `border-control` | `#6A6A6A` | Contorno de campos |
| `accent` | `#4CC9E0` | Acento |
| `accent-on` | `#0A1A1F` | Texto sobre relleno acento |
| `accent-soft` | `rgba(76,201,224,0.16)` | Selección |
| `hover` / `pressed` | `rgba(245,245,245,0.06)` / `0.10` | Overlays |
| `scrim` | `rgba(0,0,0,0.55)` | Velo |

### 3.4 Semántica (cuarentena de estado)

Color de estado **solo** en badges, validación y cifras; nunca decorativo ni como única señal (siempre icono/texto).

| Estado | Claro: texto / fondo | Oscuro: texto / fondo |
|---|---|---|
| Success | `#166534` / `#E6F4EA` | `#6FD08C` / `#17301F` |
| Warning | `#8A5300` / `#FFF1D6` | `#F2B84B` / `#3A2A0B` |
| Error | `#B42318` / `#FDE8E6` | `#FF8A80` / `#3D1917` |
| Info / Running | `#0B6478` / `#E3F3F7` | `#5CCFE6` / `#0F2E36` |
| Idle / Ready | `#5C5C5A` / `#ECECE9` | `#A0A0A0` / `#262626` |

### 3.5 Contraste verificado (calculado, WCAG 2.x)

| Par | Ratio | Umbral |
|---|---|---|
| `text` #111 sobre bg / surface / elevated | 17.6 / 18.9 / 16.9 | 4.5 ✔ |
| `text-secondary` #6B6B6B sobre bg / surface / elevated | 4.97 / 5.33 / 4.75 | 4.5 ✔ |
| `accent` #0A6A7C sobre surface / bg | 6.24 / 5.82 | 4.5 ✔ |
| Blanco sobre `accent` (botón primario) | 6.24 | 4.5 ✔ |
| `border-control` #949490 sobre surface | 3.04 | 3.0 (no texto) ✔ |
| Semántica claro (texto sobre su fondo) | 5.6–6.3 | 4.5 ✔ |
| Oscuro: `text` sobre bg…dialog | 17.3 → 13.0 | 4.5 ✔ |
| Oscuro: `text-secondary` #A0A0A0 sobre bg / surface / elevated / popover / dialog | 7.2 / 6.7 / 6.2 / 5.8 / 5.4 | 4.5 ✔ |
| Oscuro: `accent` #4CC9E0 sobre bg / surface / elevated | 9.7 / 8.9 / 8.3 | 4.5 ✔ |
| Oscuro: `accent-on` #0A1A1F sobre `accent` | 9.1 | 4.5 ✔ |
| Oscuro: `border-control` #6A6A6A sobre surface | 3.2 | 3.0 ✔ |
| Oscuro: semántica (texto sobre su fondo) | 5.8–7.9 | 4.5 ✔ |
| Foco (acento) sobre bg claro / oscuro | 5.2 / 10.4 | 3.0 ✔ |

`text-disabled` y separadores decorativos (1.17:1 claro) están exentos por norma; **no** se usan para información.

### 3.6 Color de datos (visualización)

Serie categórica de 6 tonos, todos ≥ 5:1 sobre su superficie; **nunca el color como único canal** (etiqueta directa, patrón de trazo o marca).

| # | Claro | Oscuro |
|---|---|---|
| 1 | `#0A6A7C` | `#4CC9E0` |
| 2 | `#B45309` | `#F2A03D` |
| 3 | `#6D4AAE` | `#B79CF0` |
| 4 | `#B4234A` | `#F27A9A` |
| 5 | `#2F7D32` | `#6FD08C` |
| 6 | `#52616B` | `#9FB0BA` |

Ejes y rejilla: `divider`/`text-secondary`. Disparo (trigger) = línea discontinua en acento + etiqueta de texto. Los colores del orbital y de la forma de onda dejan de estar fijos en código (V-05) y salen de estos tokens.

---

## 4. Componentes

Notación: alto · padding · radio · estados. Todos los estados existen en ambos temas: **default, hover, pressed, focus, disabled** (+ selected/error donde aplica).

### 4.1 Botones

| Variante | Aspecto | Uso |
|---|---|---|
| **Primary** | Relleno `accent`, texto `accent-on`, peso 600 | 1 por vista/diálogo (Regla de una sola voz) |
| **Secondary** | Fondo `elevated`, texto `text` | Acciones alternativas |
| **Subtle (ghost)** | Sin fondo, texto `accent-text`; hover `hover` | Acciones de baja jerarquía, en tablas y cards |
| **Destructive** | Texto/relleno `error`; requiere confirmación contextual | Borrar |

Alto 36 px (Standard) / 28 px (Compact); padding 8×16; radio `r-md`; icono opcional a la izquierda (8 px de separación). Hover −8 % luminosidad/overlay `hover`; pressed overlay `pressed`; disabled tono `disabled` + `text-disabled`. Transición `motion-fast`.

### 4.2 Icon buttons
32×32 px (24 en Compact), icono 16; radio `r-md`; fondo transparente → overlay en hover; `accessibleName` y tooltip obligatorios; objetivo táctil/ratón ≥ 32 px.

### 4.3 Navegación (IA §4)

| Elemento | Especificación |
|---|---|
| **Rail primario** | Ancho 64 px (colapsado) / 216 px (expandido); ítem 44 px alto; icono 20 + etiqueta 14/600; fondo `surface`; **seleccionado = fondo `accent-soft` + icono/texto `accent`** (sin barra lateral decorativa); Settings anclado abajo |
| **Nav contextual** (secciones del área) | Control segmentado/pestañas ligeras bajo la top bar, 40 px; seleccionado = texto `text` 600 + fondo `accent-soft`; hasta 6 ítems |
| **Top bar** | 56 px; migas · chip de contexto · botón de búsqueda (campo simulado de 280 px con `Ctrl K`) · tema · estado offline |
| **Breadcrumbs** | Secondary 13 px; separador `›` en `text-secondary`; último tramo `text`; tramos anteriores enlaces subtle |

### 4.4 Cards y paneles
- **Card:** `surface`, radio `r-lg`, padding 24 (16 compacto), **sin borde por defecto**; título Section 20, cuerpo Body. Clicable: hover overlay + cursor de mano + foco visible.
- **Panel:** región funcional del workspace (parámetros, herramientas, visualización, resultados); título Section, separación entre paneles 16–24. Los paneles se distinguen por **espacio y tono**, no por marcos; máximo un nivel de anidamiento.
- **Panel lateral:** 360 px, `surface`, borde izquierdo `divider`; anima `motion-slow`.

### 4.5 Tabs y segmented controls
- **Segmented:** pista `elevated` radio `r-md`, padding 2; segmento activo `surface` + texto `text` 600 (claro) / `accent-soft` (oscuro); alto 32; ≤ 5 segmentos.
- **Tabs de contenido:** texto Secondary→Body 600 al activarse, indicador de 2 px `accent` inferior; para vistas hermanas dentro de un workspace.

### 4.6 Campos (inputs)
Alto 36, padding 8×12, radio `r-md`, fondo `elevated`, **borde `border-control` 1 px** (única excepción al «sin bordes» por accesibilidad, 3:1). Etiqueta Secondary 13 **visible sobre el campo** (nunca solo placeholder); texto de ayuda Caption bajo el campo; error: borde `error` + mensaje bajo el campo (no solo en diálogo); foco: borde 2 px `accent`. Unidades como sufijo en el propio campo (`5  V`), cifras `tnum`. Áreas de texto: mínimo 3 líneas, redimensionables.
**Combos y selectores:** misma caja; popover de lista 40 px por opción; scroll a partir de 8 opciones; buscables a partir de 12.

### 4.7 Tablas
Cabecera `elevated`, texto Secondary 13/600; filas 36 px (Standard) / 28 px (Compact); zebra **no**; separador `divider` solo entre grupos; selección `accent-soft`; hover `hover`; cifras alineadas a la derecha con `tnum`; columna de estado con badge; encabezado fijo; foco de celda visible; ordenación con icono. Vacía: estado vacío de tabla (§4.11).

### 4.8 Badges y estado
- **Badge/Pill de estado:** radio `r-full`, alto 24, padding 4×10, Caption 12/600, **icono de 12 px + texto** (color nunca solo), colores de §3.4.
- **Estados de ejecución** (Ready, Running, Computing, Success, Warning, Error, Offline; *Paused* solo si el motor lo soporta): texto corto fijo; el detalle largo va en una línea secundaria, no dentro de la pill.
- **Indicador de estado global** (barra de estado): punto de 8 px + texto Caption.

### 4.9 Diálogos
Estructura obligatoria: **Título** (Section 20) · **Contexto** (Secondary, una línea: qué y sobre qué) · **Contenido mínimo** · **Acciones**.
Ancho 400 (confirmación) / 480 (formulario) / 640 (contenido rico); padding 24; radio `r-xl`; velo `scrim`; aparición `motion-slow`.
Acciones alineadas a la derecha; **primaria a la izquierda del grupo** (convención de Windows: afirmativa primero), secundaria a continuación; una sola primaria; destructiva con texto explícito (*Eliminar asignatura*), nunca «OK/Yes».
Comportamiento: foco inicial en el primer campo o en la acción segura; `Esc` cancela; `Enter` activa la primaria salvo en áreas de texto; **el botón por defecto de un diálogo destructivo es Cancelar**; errores en línea junto al campo. No se usan `QMessageBox` genéricos cuando un diálogo contextual aporte más.

### 4.10 Tooltips
Popover pequeño: `popover`, radio `r-md`, Caption 12, padding 6×10, máx. 280 px, retardo 500 ms, `motion-fast`. **Nunca** único portador de información esencial (sintaxis, unidades → van en helper text).

### 4.11 Estados vacío, error, carga
| Estado | Estructura |
|---|---|
| **Vacío** | Icono 32 (`text-secondary`) · Título Section · una línea de explicación honesta · **una** acción primaria; espacio 48+ |
| **Error** | Icono de error · problema en una frase · acción de recuperación · detalle técnico colapsable (código `UiError`); solo mensajes UI-safe |
| **Cargando** | Esqueleto o progreso ligado a la tarea real; indeterminado solo si no hay porcentaje; sin *spinners* decorativos |
| **Offline** | Badge + explicación de qué se degrada (backend opcional no disponible) |

### 4.12 Progreso
Lineal de 4 px, pista `elevated`, relleno `accent`, radio `r-full`; determinado cuando el motor informa avance; indeterminado (animación 1.2 s) solo durante una ejecución real; texto de estado asociado.

### 4.13 Command / search (Ctrl+K)
Popover centrado 640 px, `popover`, radio `r-lg`, sombra suave. Campo grande (Body-large 16) sin borde; grupos con cabecera Caption; filas 40 px con icono + título + ruta secundaria; selección `accent-soft`; recientes al abrir; atajos visibles a la derecha; `↑/↓` navega, `Enter` abre el **seleccionado**, `Esc` cierra; estado vacío con sugerencias.

### 4.14 Paneles laterales
Tutor / Inspector / Actividad (IA §4.4): 360 px, cabecera con título + cerrar, contenido desplazable, `Esc` cierra; el panel Tutor muestra el estado *verified / unverified / rejected* como badge y nunca contenido no verificado como respuesta.

### 4.15 Otros
- **Checkbox/radio/switch:** 18 px, radio `r-sm`, marcado en `accent`.
- **Scrollbars:** 8 px, aparecen al pasar el ratón (auto-ocultas), sin flechas, pulgar `text-secondary` al 50 %.
- **Menús:** `popover`, filas 32 px, radio `r-md`, atajo a la derecha en Caption.
- **Separadores:** `divider` 1 px o espacio; preferir espacio.

---

## 5. Patrones de composición

| Patrón | Regla |
|---|---|
| **Página** | Margen 32; título Title 28 + línea de contexto Secondary; contenido en columna máx. 1200 px salvo workspaces |
| **Workspace de ingeniería** | 3 zonas: parámetros (izq., 320) · visualización (centro, flexible) · resultados (der./abajo); herramientas en barra superior; historial/replay en panel lateral |
| **Formulario** | Etiqueta arriba, una columna, 16 entre campos, acciones al pie; validación en línea |
| **Home** | Composición editorial: una acción primaria (*Continuar*), datos reales, **sin cuadrícula de cards** |
| **Resultado de ejecución** | Cabecera con estado + digest; cifras con unidad como elemento principal; visualización; detalle técnico colapsado |

---

## 6. Movimiento funcional (catálogo)

| Situación | Efecto | Token |
|---|---|---|
| Hover / pressed / foco | Cambio de overlay | fast |
| Aparición / desaparición de popover, tooltip, paleta | Fade + desplazamiento vertical 4 px | base |
| Cambio de sección | Fade cruzado del contenido (sin deslizar el rail) | slow |
| Panel lateral | Deslizamiento horizontal + fade | slow |
| Diálogo | Fade + escala 0.98→1 (solo si el diálogo es ventana sin relayout; si no, solo fade) | slow |
| Cambio de estado (pill) | Cross-fade de color/etiqueta | base |
| Ejecución | Progreso real; aparición del resultado con fade | base |
Todo con `reduce-motion` → `instant`.

---

## 7. Accesibilidad (requisitos del sistema)

1. **Foco visible siempre**: anillo de 2 px `accent` (3:1 mínimo) en todo control, ítem de lista, pestaña y celda. Prohibido `outline: 0` sin sustituto (corrige S-02).
2. Objetivo mínimo de puntero 32×32 px.
3. Orden de tabulación = orden visual; `F6` cicla regiones.
4. Toda información transmitida por color lleva texto o icono.
5. Todos los controles solo-icono y paneles llevan `accessibleName`/`accessibleDescription`.
6. Contraste según §3.5 verificable por script en CI de diseño (tabla de pares como test).
7. Respeta *reduce motion* y el modo oscuro/claro del sistema.

## 8. Implementación (contrato para el Prompt 4)

- **Extender, no reemplazar, `theme.py`:** `Tokens` gana campos de tipografía, espaciado, radio, elevación y movimiento; se mantiene `apply_status_style` y el mecanismo de regenerar QSS.
- Mapeo de tokens actuales → nuevos: `ground→bg`, `card→surface`, `field→elevated`, `sidebar→bg` (el rail usa `surface`), `hairline→divider`, `ink→text`, `secondary→text-secondary`, `accent_soft→accent-soft`, `*_bg/_ink` → semántica §3.4, `tertiary→text-disabled`.
- Componentes reutilizables nuevos (en `ui/`): `StatusPill`, `Section/Panel`, `ResultView`, `EmptyState`, `Notice`/`ContextDialog`, `CommandPalette`, `NavRail`, `Segmented`, `FocusRing`, `run_task()`.
- Se elimina `* { font-size }`; los roles se asignan por propiedad `role` (`display|title|section|body|secondary|caption|numeric`).
- Colores de datos y de `OrbitView`/`WaveformWidget` leen `current_tokens()`.
- Tests: contraste de pares (§3.5) y ausencia de hex fuera de `theme.py`.
- `DESIGN.md` se reescribe como puntero a este documento al terminar el Prompt 4.

## 9. Decisiones y puntos abiertos

| Decisión | Motivo |
|---|---|
| Acento cian profundo | Identidad de instrumento; lejos del azul Apple y del púrpura SaaS; contraste holgado |
| Segoe UI Variable, sin empaquetar fuentes | Nativo Win11, cero licencias nuevas |
| Bordes solo en campos y foco | Accesibilidad (3:1) sin volver al look de rejilla |
| Sombra solo en popovers/paleta | Único sitio donde Qt la da bien y aporta jerarquía real |
| Primaria a la izquierda en diálogos | Convención de Windows |
| **Abierta:** Fluent System Icons vs Lucide (ISC) | Decidir al implementar; ambos permisivos |
| **Abierta:** modo *Compact* global o por vista | Por defecto por vista (tablas/instrumentos) |
| **Abierta:** escala de texto del sistema de Windows (Settings › Accessibility) | Qt no la lee; evaluar en el Prompt 11 |

---

## 10. Kit de workspace (Prompt 6)

Implementado en `ui/workspace.py` y usado por Circuits, Aerospace y Digital Logic.

| Componente | Uso | Notas |
|---|---|---|
| `Panel` | Zona titulada de un workspace (Setup, Waveform, Results…) | Superficie `card`, radio 12, sin borde; título 14/600 (rol *PanelTitle*, entre Body y Section); `actions` aloja controles propios de la zona |
| `Metric` | Un valor medido con su unidad | Etiqueta 12, cifra 24/600 con `tnum`, unidad 13; nombre accesible «Etiqueta: valor unidad»; `—` cuando no hay valor |
| `KeyValueList` | Hechos alineados (contexto, topología) | Clave secundaria 13, valor seleccionable |
| `EmptyState` | Estado vacío con siguiente paso | Título Section + una línea |

Modelo de zonas por workspace: **Context** (qué objeto) → **Inputs** → **Tools** (barra superior) → **Visualization** → **Results/Instruments** → **History/Replay**. Los paneles se separan por espacio y tono; los divisores redimensionables (`QSplitter`) solo aparecen donde el usuario reparte espacio entre zonas (Digital Logic).

Casillas (`QCheckBox`/`QListWidget::indicator`): 14 px, borde `border-control`, marcadas en `accent` (relleno; el trazo de check llegará con el conjunto de iconos).
