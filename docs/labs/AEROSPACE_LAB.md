# Laboratorio Aeroespacial y de Telecomunicación Espacial — Especificación de diseño

Documento de **especificación**: no describe código escrito, describe lo que se va a construir y en qué orden. Se redacta **solo con lectura** del repositorio `C:\Users\dmart\Documents\AcademicCore`, de `guias_upc\` y de los documentos hermanos de `C:\Users\dmart\Downloads\labs\`. No se ha tocado el repositorio, ni OneDrive, ni `guias_upc\`.

Fecha de verificación del código y de las guías: **2026-10-01**. Todo número de líneas, de tests o de funciones citado aquí se ha contado ese día sobre el árbol de trabajo (con cambios sin confirmar; ver §2.1).

Fuentes: guía docente `guias_upc\cuatrimestre_7\telecomunicacion-espacial.pdf` (230257 TELESP, 6 ECTS, optativa); `guias_upc\cuatrimestre_5\sistemas-de-control.pdf`, `guias_upc\cuatrimestre_5\sistemas-de-medida.pdf` y `guias_upc\cuatrimestre_7\sensores-actuadores-y-microcontroladores-en-robots-moviles.pdf` solo por lo espacial o de navegación; informe `math_catalog\extra_electromagnetismo.md` (sección 6, Telecomunicación espacial); `MATH_LAB.md` (bloques 18 y 19, decisión D12); `CIRCUITS_LAB.md` (§3.3.1, §3.7, §3.8, §11, fase CI-R); `SIGNALS_LAB.md` (§3.1, D8); y el código real de `domain\engineering\{orbital,satcom,structural,comms,rf}`, `ui\aerospace.py`, `ui\routes.py`, `ui\engineering.py`, `ui\main_window.py`, `ui\modules.py`, `ui\dashboard.py`, `application\engineering.py`, `application\explain_service.py`, `domain\execution\orbital.py` y los tests relacionados.

---

## Índice general

| Parte | Secciones | Contenido |
|---|---|---|
| 1 | §0–§2 | Cómo leer, objetivo y requisitos, punto de partida real (inventario honesto, lagunas y deuda) |
| 2 | §3–§5 | Arquitectura, ubicación en la navegación, mapa guía→bloques, convenciones declaradas |
| 3 | §6 | Mecánica orbital: Kepler, elementos, Hohmann, perturbaciones, huella en tierra, visibilidad |
| 4 | §7–§9 | Enlace y balance, antenas y propagación, modulación y codificación a nivel de enlace |
| 5 | §10–§12 | Calculadoras, gráficas, diagramas de bloques de enlace |
| 6 | §13–§16 | Ejercicios, generador, corrección y trazas, verificación por segundo camino, datos |
| 7 | §17–§19 | Interfaz detallada, accesibilidad, pruebas |
| 8 | §20–§24 | Migración de UI y paquete (fase AE-R), fases, riesgos, decisiones D1..D18, aceptación |
| Anexos | A–D | Valores de referencia verificados, fórmulas, glosario, trazabilidad |

Atajos: bloques `BL-AE-*` en §4.2 · tipos de ejercicio `AE-*` en §13 · migración `AE-R` en §20 · fases `AE-0`…`AE-9` en §21 · **decisiones D1..D18 con recomendación en §23** · frontera con otros laboratorios en §3.3.

---

# PARTE 1 — Cómo leer, objetivo y punto de partida

## 0. Cómo leer este documento

### 0.1 Marcas de estado

Se usan las mismas marcas que `CIRCUITS_LAB.md` §0.2, para que los tres documentos se puedan cruzar:

| Marca | Significado |
|---|---|
| **[EXISTE]** | Ya está en el repositorio, con tests; el spec lo reutiliza sin reescribir |
| **[PARCIAL]** | Existe una parte; el spec dice cuál y qué falta |
| **[NUEVO]** | No existe; se construye en este laboratorio |
| **[MUEVE]** | Existe y cambia de sitio (paquete, ruta o pestaña) sin cambiar de comportamiento |
| **[FRONTERA]** | Pertenece a otro laboratorio (`MATH_LAB`, `CIRCUITS_LAB`, `SIGNALS_LAB`); aquí solo se consume o se enlaza |

### 0.2 Respaldo por examen

**Esta asignatura no tiene ningún examen ni apunte en el repositorio ni en OneDrive.** El informe `extra_electromagnetismo.md` (cabecera, fila de Telecomunicación Espacial) lo dice expresamente: «No hay ningún material en OneDrive» y «Todo lo de esta asignatura es **deducido del temario, no de exámenes**; la frecuencia indicada es peso en horas del temario, no frecuencia de examen».

Consecuencia directa y honesta para este documento:

- **Ningún bloque, tipo de ejercicio ni calculadora de este laboratorio está respaldado por examen.** La marca **`[SOLO GUÍA]`** significa «deducido del temario de la guía docente (peso en horas) y de la bibliografía declarada (Maral y Bousquet, Gordon y Morgan, Ha)».
- La prioridad de todo el laboratorio es por eso **baja** frente a Circuitos, Señales o Matemáticas, que sí tienen exámenes. La prioridad **relativa dentro** del laboratorio se reparte por el **peso en horas** de la guía (§4.1), que es el único dato objetivo.
- Donde una fórmula o un valor numérico proviene de **tablas externas** (coeficientes de lluvia de la UIT-R, atenuación por gases, temperaturas de ruido de cielo) el laboratorio **no inventa datos**: se piden al usuario como entrada, con una tabla opcional marcada «orientativa, no normativa» (§8.4).
- Un tipo de ejercicio cuyo enunciado exacto no se puede comprobar contra ningún examen se marca **`[ESTILO DEDUCIDO]`**: sigue el estilo de los problemas de balance de enlace de la bibliografía, no un enunciado real del curso. El corrector no puede asumir un formato de respuesta único (por eso acepta equivalencias de unidades, §15.3).
- Los **valores de aula** (3 grados de elevación mínima, 0,6 de eficiencia, 290 K de referencia) se tratan como **convenciones declaradas** que el estudiante puede cambiar (§5), no como verdades.

### 0.3 Identificadores estables

Tres niveles que no se mezclan, en paralelo con `CIRCUITS_LAB.md` §0.3 y `SIGNALS_LAB.md`:

- **`BL-AE-<n>`**: bloque temático del índice maestro (§4.2).
- **`AE-<área>-<nn>`**: tipo de ejercicio del catálogo (§13), con dos cifras. Las áreas son `OR` (órbitas), `GT` (huella y visibilidad), `EN` (enlace y balance), `AN` (antenas y propagación), `RU` (ruido), `PH` (capa física y acceso). Un identificador **nunca se reutiliza ni se renumera**; un tipo retirado queda marcado `retirado`.
- **`AE-R`, `AE-0`…`AE-9`** (sin área, solo cifra o letra): **fases** de construcción (§20, §21).
- **`D1`…`D18`**: decisiones (§23).
- **`L1`…**: lagunas verificadas (§2.8). **`H1`…**: hallazgos de deuda (§2.9). **`R-…`**: riesgos (§22).

### 0.4 Convenciones de este texto

- Las rutas usan el árbol **actual**: `domain\engineering\…`. Tras la fase `CI-R` de `CIRCUITS_LAB.md` §3.7.3 ese árbol se llama `domain\circuits\…`; el nuevo paquete de este laboratorio, `domain\aerospace\`, **no depende del nombre** de su vecino (§3.2, D3). Cuando importa, se escribe `<núcleo>` para «`domain\engineering` antes de CI-R, `domain\circuits` después».
- Las fórmulas van en texto plano con `·` y `^`; `√`, `π`, `μ`, `Ω`, `ω`, `ν` se escriben como símbolos. Ángulos en radianes salvo que se diga «grados».
- Unidades SI en el motor; unidades de uso común (km, GHz, dBW, grados) solo en la **capa de presentación** (§5.1).
- «Esencial» = sin ello el laboratorio no cumple su objetivo. «Deseable» = mejora la utilidad. «Opcional» = solo si sobra tiempo, y siempre marcado `[SOLO GUÍA]`.

### 0.5 Qué NO es este documento

- No es un tratado de ingeniería aeroespacial: la asignatura es **Telecomunicación Espacial** (comunicaciones por satélite), no dinámica de vuelo, estructuras aeroespaciales ni propulsión. Esas disciplinas **no están en ninguna guía** del grado y quedan fuera (§1.4).
- No es el spec del motor matemático: Kepler como ecuación trascendente genérica, trigonometría esférica pura y Bessel como biblioteca son de `MATH_LAB` (§3.3).
- No es el spec de circuitos RF: adaptación, líneas, parámetros S, figura de ruido y cascada de Friis **de circuito** son de `CIRCUITS_LAB` §11 (`BL-RF-12`). Aquí se **consume** `friis_temperature` por su interfaz.
- No es el spec de procesado de señal: modulaciones y espectros como señal son de `SIGNALS_LAB`; aquí solo su **consecuencia en el enlace** (§9).
- No incluye código; los ejemplos de fórmula son los contratos que el código debe cumplir.

---

## 1. Objetivo y requisitos

### 1.1 Objetivo

Construir, dentro de AcademicCore, un **laboratorio aeroespacial** propio —con su área en la navegación, su paquete de dominio y su catálogo de ejercicios— que permita a un estudiante de Telecomunicación Espacial:

1. **Calcular y entender una órbita**: elementos clásicos, ecuación de Kepler, posición y velocidad en cualquier instante, transferencias de Hohmann, periodo, energía, perturbaciones básicas (achatamiento J2, arrastre en LEO como aviso), tipos de órbita útiles (LEO, MEO, GEO, HEO tipo Molniya, sol-síncrona).
2. **Relacionar la órbita con una estación**: huella en tierra, ángulo de elevación y acimut, distancia oblicua, ventanas de visibilidad, duración de un paso, Doppler.
3. **Construir y verificar un balance de enlace**: PIRE, pérdidas en espacio libre, ganancia de antena, temperatura de ruido de sistema, G/T, C/N₀, E_b/N₀, margen, atenuación por lluvia y gases, enlace ascendente, descendente y transpondedor transparente («bent pipe»), espacio profundo.
4. **Conectar el enlace con la capa física**: tasa máxima alcanzable, BER teórica, Shannon, eficiencia espectral, ganancia de codificación, bajo las mismas convenciones que el resto de la app.
5. **Dibujar el sistema**: diagramas de bloques de la cadena de enlace (transmisor, antena, canal, antena, LNA, receptor) y de la carga útil (transpondedor), generados desde el mismo modelo que calcula (§12).
6. **Practicar con corrección explicada**: ejercicios paramétricos, generador con semilla, corrección paso a paso con la traza E0 y verificación por **segundo camino independiente** (§15).

El laboratorio no sustituye al libro ni a las tablas de la UIT: **hace visibles y comprobables** los cálculos.

### 1.2 Requisitos explícitos del usuario (trazabilidad)

| Id | Requisito (del encargo) | Dónde se cumple |
|---|---|---|
| U1 | Spec en español, **solo especificación**; no tocar repo, OneDrive ni `guias_upc` (lectura) | Cabecera; todo el documento |
| U2 | Contexto: `engineering` ya se llama visiblemente «Circuitos electrónicos»; `orbital/`, `satcom/` y `structural-aero` salen; `structural` de circuitos **se queda** (reconocimiento de topologías) | §3.1, §3.3, H4 |
| U3 | Decidir y detallar la **nueva ubicación en la navegación**: área propia «Aeroespacial», **sin renombrar ids de ruta existentes salvo con alias** | §3.5, §17.1, §20.3, D1, D2 |
| U4 | **Fase de migración de UI y paquete**: `domain\engineering\orbital|satcom` → paquete propio, **tests en verde antes y después, como CI-R** | §20 (fase AE-R), D3, D4 |
| U5 | Inventario honesto del código real: qué existe y qué falta | §2 |
| U6 | Mapa guía→bloques, y qué es respaldado por examen (solo guía: baja prioridad) | §0.2, §4 |
| U7 | Contenido: mecánica orbital, enlace y balance, antenas/propagación, modulación/codificación a nivel de enlace (frontera con `SIGNALS_LAB`), calculadoras, gráficas, diagramas de bloques, ejercicios/generador/corrección con trazas y verificación por segundo camino, convenciones declaradas, accesibilidad, pruebas, fases, riesgos | §6–§19, §21, §22 |
| U8 | Frontera: lo puramente matemático en `MATH_LAB`; balances circuitales y RF en `CIRCUITS_LAB` §11 | §3.3 |
| U9 | Decisiones D1..Dn **todas con recomendación**, aprobables en bloque | §23 |
| U10 | Objetivo de longitud (1000+ líneas) y respuesta final de 10 líneas | Este fichero; mensaje final |

### 1.3 Principios de diseño

Heredados del repositorio (los verifican tests existentes) y de los otros laboratorios:

1. **Un solo motor, muchas vistas.** Un `LinkLeg`, una `ClassicalElements`: la calculadora, el diagrama, la gráfica y el corrector leen el **mismo objeto**; nada se recalcula en la interfaz (patrón ya verificado: `test_product_aerospace.py`, «every number from the F16 domain engine»).
2. **Exactitud primero.** Todo en `Decimal` con el contexto único `make_context()` (50 dígitos); `float` solo para **pintar** (coordenadas de píxel). Es la regla ya cumplida por `orbital` y `satcom`.
3. **Determinismo.** Misma entrada, misma salida y mismo *digest* (`test_determinism_same_digest`); la simulación Monte Carlo usa semilla explícita.
4. **Dominio puro.** Sin Qt, sin SQLite, sin red, sin ficheros, impuesto por `tests\test_architecture.py` (`test_satcom_layer_direction` y el escáner de llamadas peligrosas de `test_f16_orbital.py`).
5. **Convención declarada, nunca implícita.** Cada resultado dice en qué convenciones se calculó (§5): radio terrestre, día sidéreo o solar, dBi o dBd, T₀ = 290 K, sentido del margen.
6. **Verificación por segundo camino** como parte del resultado, no como extra (§15.5).
7. **Honestidad del alcance.** Lo que viene de tablas se pide como dato; lo que se desconoce se marca (§0.2). El laboratorio **nunca** presenta como medida lo que es un modelo ideal de dos cuerpos.
8. **Errores en castellano**, con el estado del motor conservado (`ControlStatus`), sin trazas de Python hacia el usuario.
9. **Sin renombrar ids persistentes.** Etiquetas de esquema (`f8p5-satcom/1`, `f16-orbital/1`), operación `physics.orbital` y claves de Knowledge **no cambian** (§20.2).
10. **Ligero y pocas dependencias.** Nada de librerías astrodinámicas externas (poliastro, SGP4) en el camino exacto; solo como **comprobador opcional** de pruebas (§19.6).

### 1.4 Alcance: qué entra y qué no

**Entra** (todo `[SOLO GUÍA]`, §0.2):

| Tema (guía) | Entra como |
|---|---|
| 2. Entorno espacial: principios orbitales, tipos de órbitas, órbitas útiles, lanzamiento y puesta en órbita | Bloques `BL-AE-1` a `BL-AE-6` |
| 3. Carga útil: transpondedor, amplificador no lineal, subsistema de antenas | `BL-AE-12`, `BL-AE-13` (modelo básico: back-off, intermodulación, ganancia de apertura) |
| 4. Canal satélite: espacio libre, efectos atmosféricos, interferencias, multicamino (canal LMSC), ruido | `BL-AE-8`, `BL-AE-9`, `BL-AE-10` |
| 5. Cálculo del enlace: pérdidas, ruido, G/T, balance, espacio profundo | `BL-AE-7` a `BL-AE-11` |
| 6. Capa física: modulaciones y codificación de canal vistas desde el satélite | `BL-AE-14` (frontera con SIGNALS_LAB) |
| 7. Acceso múltiple: FDMA/TDMA/CDMA, acceso aleatorio | `BL-AE-15` (cálculo, no simulación de red) |
| 8. Redes y servicios (DVB-S2, VSAT, Inmarsat, IP por satélite) | **Tabla de referencia** de parámetros típicos (§9.6); sin motor |

**No entra** (decisión explícita, para que nadie lo busque):

- **Dinámica de vuelo, actitud, estabilidad, control de actitud** (rueda de reacción, momentos): no hay guía que lo pida. El control de la app (`control/`) es de circuitos y de la asignatura Sistemas de Control (§4.3), no de aeronáutica.
- **Estructuras aeroespaciales** (cargas de lanzamiento, vibraciones, pandeo): «structural-aero» no existe en el código ni en ninguna guía (H4); el nombre del encargo se refería a `structural\` de circuitos, que **se queda**.
- **Propulsión más allá de la ecuación del cohete** de Tsiolkovsky y el balance de Δv de maniobras; sin motores, empuje, especie de propelente.
- **Propagación numérica de alta fidelidad** (SGP4/TLE, perturbaciones de Sol y Luna, presión de radiación, mapa de gravedad): se ofrece un modelo **educativo** (J2 secular, arrastre exponencial como aviso, §6.8) y se documenta su límite; SGP4 queda como opcional marcado y no entra en el camino exacto.
- **Mecánica de tres cuerpos** (puntos de Lagrange, CR3BP): ni la guía ni `extra_electromagnetismo.md` lo piden; se menciona como futuro en §22 (R-ALC).
- **Planificación de misiones interplanetarias** (conjunta de cónicas parcheadas, asistencias gravitatorias): solo el enlace de **espacio profundo** (§7.8) y distancia Tierra-Marte como dato; la trayectoria no.
- **Navegación por satélite (GNSS)**: el guion de la guía de robots móviles menciona sensores, no GPS; solo se enlaza `BL-AE-16` (opcional) con **pseudodistancias** como aplicación de la geometría de visibilidad, sin receptor ni efemérides (§4.3).
- **Redes y protocolos** (IP por satélite, TCP sobre GEO): solo la **latencia de propagación** como cálculo (§7.9).
- **Teoría de códigos avanzada** (Viterbi, LDPC, BCH): el informe la declara fuera de alcance; solo ganancia de codificación como número de tabla.

### 1.5 Definición de «completo»

El laboratorio está **completo** cuando, para cada bloque `BL-AE-n` esencial de §4.2:

1. existe su cálculo exacto en el dominio con pruebas;
2. existe su traza paso a paso (E0) con **verificación por segundo camino** (§15.5);
3. existe al menos una calculadora (§10) y una gráfica o diagrama (§11–§12) donde la figura aporta;
4. existe al menos un tipo de ejercicio con generador y corrector (§13–§15);
5. aparece en la interfaz bajo «Aeroespacial» con teclado y lector de pantalla (§17–§18);
6. ninguna prueba de la suite existente cambia de resultado (§19, §20).

La cobertura es **del temario de la guía**, no de exámenes (no los hay): el criterio es «cada subapartado numerado 2.x, 4.x, 5.x, 6.x, 7.x de la guía tiene bloque», no «cada tipo de examen tiene ejercicio».

### 1.6 Perfiles de usuario y flujos principales

| Perfil | Quiere | Flujo |
|---|---|---|
| Estudiante que prepara un problema largo de balance de enlace (el más probable del examen, §0.2) | Hacer el balance con sus datos y ver dónde falla el margen | «Enlace» → plantilla de enlace GEO o LEO → editar PIRE/G/T/pérdidas → ver el balance en cascada y el margen → «Explicar» |
| Estudiante que revisa órbitas | Ver una órbita, su periodo, la huella y los pasos sobre su ciudad | «Órbitas» → elementos (o altitud/apogeo) → 2D/3D, huella → «Visibilidad» sobre una estación |
| Estudiante en autoevaluación | Practicar tipos con enunciados nuevos y que lo corrijan | «Ejercicios» → tipo `AE-EN-03` → semilla → respuesta → corrección con traza |
| Docente/curador del banco | Fijar convenciones del curso y ejemplos reutilizables | Ajustes del laboratorio → «Convenciones» (§5) → guardar plantilla |
| Alumno de otra asignatura (Circuitos, Señales) | Reutilizar una parte, p. ej. ruido de cascada o BER | Desde el enlace a `friis_temperature` y `ber_*` (sin duplicar; §3.3) |

---

## 2. Punto de partida real

Inventario **honesto** (cuenta de líneas y de funciones comprobada el 2026-10-01 con `wc`/`grep`; aquí «existe» significa «tiene código y pruebas», no «está en pantalla»).

### 2.1 Panorama general

- El repositorio tiene **cambios sin confirmar en 109 ficheros** de la rama `main` (`git status --short`, 2026-10-01). Los paquetes `orbital` y `satcom` **no figuran** entre los modificados (lo inventariado de ellos es el estado confirmado); de los tests aeroespaciales solo `tests\test_f8p5_satcom.py` aparece modificado (a comprobar en AE-R.0: probable cambio mecánico). `ui\aerospace.py`, `ui\routes.py`, `ui\modules.py`, `ui\dashboard.py` y `ui\main_window.py` **sí** tienen cambios locales sin confirmar (la fase de UX 2026): el inventario de UI es del árbol de trabajo, no de `HEAD`. La fase `AE-R.0` debe partir de un commit limpio (§20).
- Último trabajo en `HEAD`: rediseño UX 2026 (`3cf2f8f docs: README, CHANGELOG, DESIGN and TEST-SUITE for the UX 2026 redesign`). El área «Circuitos electrónicos» (`engineering`) ya está renombrada visiblemente.
- **Lo aeroespacial vive hoy en tres sitios distintos y sin servicio de aplicación**: el dominio (`domain\engineering\orbital` y `satcom`), la traza de explicación (`domain\execution\orbital.py`, `application\explain_service.py`) y **una sola página de interfaz** (`ui\aerospace.py`, 379 líneas, solo órbita circular o elíptica de la Tierra). **`satcom` no tiene ningún consumidor fuera de sus tests** (verificado: `grep satcom src --include=*.py` solo da `explain_*`, `rf\__init__.py` y `units.py` como menciones, ninguna es una importación funcional de la UI).

### 2.2 `domain\engineering\orbital` (648 líneas, 16 tests) **[PARCIAL]**

| Módulo | Líneas | Qué contiene |
|---|---|---|
| `bodies.py` | 59 | `CentralBody` (dataclass inmutable con nombre, masa, radio, μ, procedencia) y `make_body`; preset `EARTH` |
| `constants.py` | 50 | `G_NEWTON = 6,67430E-11` (CODATA 2018), `EARTH_MASS_KG = 5,97237E24`, `EARTH_RADIUS_M = 6371000` (**radio medio IUGG**), `EARTH_MU_M3_S2 = 398600,4418 km³/s²` (IERS), `gravitational_parameter`, con procedencia en texto |
| `elements.py` | 87 | `ClassicalElements` (a, e, i, Ω, ω, ν o M, marco, esquema `ELEMENTS_SCHEMA`) validada y con *digest* |
| `kepler.py` | 116 | `mean_from_eccentric_rad`, `eccentric_from_mean_rad` (Newton con tope de iteraciones y error `ControlError` en no convergencia), `true_from_eccentric_rad`, `eccentric_from_true_rad` |
| `orbits.py` | 261 | radio↔altitud, `circular_velocity_m_s`, `circular_period_s`, `period_from_radius_s`, `radius_from_period_m`, `vis_viva_velocity_m_s`, `vis_viva_semimajor_m`, energías cinética, potencial, total y específica, `escape_velocity_m_s`, `periapsis_m`, `apoapsis_m`, `ellipse_from_apsides_m`, conversiones km, día, hora, minuto, grado |
| `__init__.py` | 75 | superficie pública y `ENGINE_VERSION = "f16-orbital/1"` |

Tests: `tests\test_f16_orbital.py` (244 líneas, **16** `def test_`): preset de la Tierra con procedencia, validación del cuerpo, ISS (velocidad y periodo conocidos), altitud GEO a partir del día sidéreo, ida y vuelta radio/altitud, inversa periodo/radio, vis-viva frente al caso circular y elíptico, coherencia de energías y escape, apsides y dominio de `e`, ida y vuelta de Kepler y no convergencia, elementos clásicos con *digest*, unidades extendidas (masa, fuerza, ángulo), determinismo, traza de ejecución con *replay*, **escáner de llamadas e importaciones peligrosas**.

**Qué falta en orbital (verificado, ver L1..L12):** no hay propagación en el tiempo (posición y velocidad en función de `t` desde el periapsis), no hay conversión elementos→vector de estado (r, v) ni su inversa, no hay Hohmann ni cambio de plano, no hay J2, no hay huella en tierra, no hay visibilidad, no hay otros cuerpos aparte de la Tierra (solo `make_body` genérico), no hay duración de eclipse ni sol-síncrona.

### 2.3 `domain\engineering\satcom` (1 572 líneas, 44 tests) **[EXISTE, mucho más completo que la UI]**

| Módulo | Líneas | Qué contiene |
|---|---|---|
| `constants.py` | 60 | `SPEED_OF_LIGHT_M_S` (exacta), `BOLTZMANN_J_K` (exacta SI 2019), `wavelength_m`, `check_magnitude` con `MAX_MAGNITUDE` |
| `metrics.py` | 195 | `DbValue` (valor + etiqueta absoluta dBW/dBm/dBi/dBHz/dB/K…), `db_add`/`db_sub` con **comprobación de etiquetas** (no se suma dBW con dBW), `to_dbw`, `to_dbm`, `from_dbw`, `from_dbm`, `dbm_to_dbw`, `dbw_to_dbm`, `k_dbw_per_k_hz` (−228,6), `required_cn_db` (Shannon), `dbd_label_to_dbi` |
| `antennas.py` | 161 | `Antenna` (ganancia dBi o diámetro y eficiencia), `circular_area_m2`, `gain_linear_from_aperture`, `aperture_from_gain_linear`, `beamwidth_approx_deg`, `dbd_to_dbi` (+2,15 dB), `dbi_to_dbd`, `gain_kind_result` |
| `losses.py` | 84 | `LossEntry` con tipos permitidos (`ALLOWED_LOSS_KINDS`), tope `MAX_LOSSES = 16`, `total_loss_db` |
| `noise.py` | 111 | `noise_psd_w_hz`, `noise_power_w`, `friis_temperature` (tope `MAX_FRIIS_STAGES`), `g_over_t_dbk` |
| `link.py` | 274 | `LinkLeg` (enlace dirigido ascendente o descendente: P_tx, antenas, pérdidas, frecuencia, distancia, T_sys **o** etapas de Friis, ancho de banda, tasa, esquema), `eirp_dbw`, `fspl_db`, `fspl_linear`, `misc_losses_db`, `receive_gain_dbi`, `received_power_dbw`, `cn0_dbhz`, `cn_db`, `ebno_db`, `g_over_t_dbk`, `system_temperature_k`, `feed_mismatch_loss_db` (desde Γ) |
| `synthesis.py` | 320 | `forward_budget` → `BudgetResult`, `link_margin_db`, `bent_pipe_cn0_dbhz` (transpondedor transparente: suma de inversas), `required_eirp_dbw`, `max_rb_bps`, `max_rb_shannon_bps`, `required_ebno_from_ber` (bisección con tope `MAX_BISECT_ITER`), `min_ptx_w`, `ber_kind_for_scheme`; `Transponder`, `EXACT_BER_SCHEMES` |
| `report.py` | 191 | `SatcomDocument` (esquema `SCHEMA`), `dumps`, `loads` (rechazan lo malformado), `compare`, `replay` (reproducción exacta) |
| `__init__.py` | 176 | superficie pública y `ENGINE_VERSION = "f8p5-satcom/1"` |

Tests: `tests\test_f8p5_satcom.py` (652 líneas, **44** tests) + el test de capas `test_satcom_layer_direction` en `tests\test_architecture.py` (líneas 322 en adelante).

**Dependencias reales de `satcom` hacia el resto del árbol de ingeniería** (contadas con `grep` sobre las importaciones; es el dato que decide la migración, §3.2 y §20.4):

| Destino | Usos | Lo que se importa |
|---|---|---|
| `engineering.math` | 7 + 1 (`math.logarithm`) | `make_context`, `decimal_pi`, `decimal_sqrt`, `decimal_ln10`, `decimal_log10`, `decimal_exp` |
| `engineering.control.errors` | 8 | `ControlError`, `ControlStatus` (**tipo de error compartido**: el motor aeroespacial no tiene error propio) |
| `engineering.comms.metrics` | 5 | `to_db10`, `to_db20`, `from_db10`, `q_function`/BER/Shannon (`MetricResult`) |
| `engineering.rf.margins` | 1 | `mismatch_loss_db` |
| `engineering.metrology.o5` | 1 | (propagación de incertidumbre, opcional) |
| `engineering.control.response` | 1 | (resultado tipado) |

`orbital` importa solo `math` (9 usos) y `control.errors` (5): **su desacoplamiento es trivial**; `satcom` además cuelga de `comms.metrics` y `rf.margins`.

**Qué falta en satcom (verificado, ver L13..L26):** no hay lluvia (UIT-R P.838/P.618) ni gases (P.676), no hay ruido de cielo, no hay `T_A` por antena, no hay Doppler, no hay multicamino (Rice/Rayleigh/Loo), no hay intermodulación ni *back-off* de un TWTA, no hay acceso múltiple (ALOHA, TDMA, CDMA), no hay *roll-off* ni ancho de banda de símbolo, no hay ganancia de codificación, no hay interferencias (C/I), no hay plantillas guardadas, y **no hay ninguna interfaz**.

### 2.4 Traza de explicación E0 **[EXISTE, solo para órbitas]**

- `domain\execution\orbital.py` (operación `physics.orbital`): `explain_orbital(kind, *args)` registra entradas, normalización, pasos con fórmula y sustitución, resultado y **CHECK independiente** (p. ej. `v²·r = μ` para la circular). Tiene `replay_orbital`.
- `application\explain_service.py`: `orbital_trace(kind, *args)` y `explain_orbital(...)` devuelven `ExplanationView`; el *replay* se resuelve por la operación (`orbital_trace.OPERATIONS`). Está en el servicio **transversal** de explicación, no en un servicio aeroespacial.
- **No existe traza E0 para `satcom`**: hay `report.replay` (reproduce un documento) pero ninguna `explain_satcom`. Es una laguna importante: el balance de enlace es el contenido de mayor peso y no se explica paso a paso hoy (L13).

### 2.5 Interfaz actual **[PARCIAL]**

- `ui\aerospace.py` (379 líneas): `OrbitView` (pintor 2D `paintEvent` con perigeo y apogeo) y `OrbitPanel` (campos «Altitud» y «Apogeo» en km, preajustes, tarjetas de métricas `r`, `v`, `T`, `vesc`, histórico de ejecuciones con «replay», estado `EN ESPERA/ÉXITO/ERROR`). Solo la **Tierra**, solo **dos cuerpos** circular o elíptico por altitudes de perigeo y apogeo. Las cuentas están en `solve` y `solve_ellipse` (métodos estáticos, **dentro de la clase de UI**, aunque llaman a funciones certificadas: es la única lógica de aplicación que vive en la UI, H3).
- Navegación (`ui\routes.py`): la ruta `engineering/aerospace` («Aeroespacial») es **hermana de «Circuitos», «Análisis», «Laboratorio», «Lógica digital»** dentro del área `engineering` («Circuitos electrónicos»). La clave heredada `aerospace` resuelve a `engineering/aerospace`.
- `ui\engineering.py` (`EngineeringPanel`): contiene un `QStackedWidget` con dos espacios, `circuits_workspace` y `orbit_panel` (importado de `ui.aerospace`), y `set_workspace(name)` que elige entre `circuits` y `aerospace`. **Lo aeroespacial está acoplado a la página de circuitos** (L27).
- `ui\main_window.py`: el mapa de páginas asigna `"aerospace": self.engineering_panel`; `_show_route` llama a `engineering_panel.set_workspace(route.target)` si el destino es `circuits` o `aerospace`, y enfoca `engineering_panel.orbit_panel.altitude_km` al llegar.
- `ui\modules.py` (`module_index`): entrada «Aeroespacial» con `EARTH.name` como única entrada; importa `domain.engineering.orbital.bodies.EARTH`.
- `ui\dashboard.py`: tarjeta `("aerospace", "Aeroespacial", "Órbitas terrestres")`.
- **No hay** vista de enlace, huella, 3D, ni diagrama; **no hay** servicio de aplicación aeroespacial: `AcademicApp` (facade) no expone nada de orbital ni de satcom.

### 2.6 Tests que tocan lo aeroespacial (inventario para la migración)

| Fichero | Qué verifica | Dependencia que habrá que tocar en AE-R |
|---|---|---|
| `test_f16_orbital.py` (16) | Motor orbital | Importa `academic_core.domain.engineering.orbital…`; **y** lee rutas físicas (`pathlib`) en el escáner de llamadas peligrosas |
| `test_f8p5_satcom.py` (44) | Motor satcom | Importa `…engineering.satcom…`, además de `rf`, `comms`, `control` |
| `test_architecture.py` | Capas | `test_satcom_layer_direction` lee `domain\engineering\satcom` por ruta física; reglas sobre `rf.margins`, `ac`, `mna`, `dsp`, `lab` |
| `test_product_aerospace.py` (3) | `OrbitPanel` usa el motor | Importa `ui.aerospace.OrbitPanel` y `…engineering.orbital` |
| `test_labs_functional.py` | `OrbitPanel` (líneas 148–170) | Importa `ui.aerospace.OrbitPanel` |
| `test_ux_engineering.py` | Cuatro pruebas «aerospace_…» (líneas 47–101) y navegación (línea 225) | `OrbitPanel`; `navigate_to("engineering/aerospace")` |
| `test_ux_routes.py` | `resolve("aerospace")`, conjunto de objetivos (línea 20), `test_aerospace_is_its_own_route_not_simulation` | Cadenas de id de ruta |
| `test_ux_shell.py` | Módulo «aerospace» aterriza en la órbita; `win._route.id == "engineering/aerospace"` (línea 69); selección `("route", "engineering/aerospace")` (línea 161) | **Cadenas de id de ruta: único cambio intencional de tests** (§20.3) |
| `test_ux_certification.py` | `navigate_to("engineering/aerospace")` calcula una órbita real (línea 92) | Id de ruta |
| `test_product_dashboard.py` | Tarjetas incluyen `aerospace` (línea 175–186) | Clave de tarjeta (no cambia) |
| `test_product_labs.py` | Conjunto de ids de módulos `{"digital-logic","electronics","aerospace"}` (línea 23) | Id de módulo (no cambia) |
| `test_e04_explainable_engineering_deep.py` | Trazas profundas (incluye lo orbital) | Importaciones y operación `physics.orbital` |

Resultado: la fase AE-R **solo cambia cadenas** en cuatro ficheros de tests de UI (ids de ruta) y **importaciones** en seis ficheros de dominio, y lo hace **después** de haber hecho los tests agnósticos (AE-R.2), como en CI-R.2.

### 2.7 Qué cubre hoy cada tema de la guía (capacidad real antes de este spec)

| Tema de la guía (horas) | Hoy en el código | Estado |
|---|---|---|
| 1. Introducción (9 h 08 m) | — | Sin código; solo teoría (no necesita motor) |
| 2. Entorno espacial (41 h 25 m, **27 %**) | `orbital`: velocidad circular, periodo, vis-viva, energías, escape, apsides, Kepler E↔M↔ν. UI: circular y elíptica 2D | **[PARCIAL]**: falta propagar en el tiempo, Hohmann, J2, huella, visibilidad, tipos de órbita guiados, lanzamiento y puesta en órbita (cohete) |
| 3. Carga útil (18 h 16 m) | `satcom.synthesis.Transponder` (struct) y `bent_pipe_cn0_dbhz` | **[PARCIAL]**: sin AM/AM, AM/PM, *back-off*, intermodulación |
| 4. Canal satélite (16 h 08 m) | `fspl_db`, `misc_losses_db`, `noise_*` | **[PARCIAL]**: sin lluvia, gases, ionosfera, multicamino ni interferencias |
| 5. Cálculo del enlace (16 h 08 m) | `forward_budget`, `cn0`, `ebno`, `link_margin_db`, `required_eirp_dbw`, `min_ptx_w`, `max_rb_*` | **[EXISTE] en dominio; sin UI, sin traza E0, sin espacio profundo parametrizado** |
| 6. Capa física (10 h 46 m) | `comms.metrics` (BER, Q, Shannon) y `satcom.synthesis.required_ebno_from_ber` | **[EXISTE] en dominio** (frontera §9) |
| 7. Acceso múltiple (10 h 46 m) | — | **[NUEVO]** |
| 8. Redes y servicios (27 h 23 m) | — | Solo tabla de referencia (§9.6) |

### 2.8 Lagunas verificadas (L1..L30)

| Id | Laguna | Bloque que la cierra |
|---|---|---|
| L1 | No hay posición y velocidad en función del tiempo: no existe «propagar» (M₀ + n·Δt → E → ν → (r, v)) | `BL-AE-2` |
| L2 | No hay conversión elementos clásicos ↔ vector de estado (r, v) en el marco inercial | `BL-AE-2` |
| L3 | No hay transferencias: Hohmann, bielíptica, cambio de plano, Δv total | `BL-AE-4` |
| L4 | No hay perturbaciones: regresión nodal y precesión del perigeo por J2, sol-síncrona, Molniya (inclinación crítica), arrastre | `BL-AE-5` |
| L5 | No hay huella en tierra (latitud/longitud geodésica de la traza, rotación terrestre) | `BL-AE-6` |
| L6 | No hay elevación, acimut, distancia oblicua desde una estación ni ventanas de visibilidad | `BL-AE-6` |
| L7 | No hay Doppler orbital (velocidad radial de un paso) | `BL-AE-6` |
| L8 | No hay eclipses (sombra cilíndrica) ni fracción iluminada | `BL-AE-5` (opcional) |
| L9 | No hay tipos de órbita guiados con parámetros característicos (LEO, MEO, GEO, HEO, sol-síncrona, Molniya, tundra) | `BL-AE-3` |
| L10 | No hay ecuación del cohete ni balance de Δv de lanzamiento (tema 2.5 de la guía) | `BL-AE-4` |
| L11 | Solo existe la Tierra como preset (`make_body` genérico sin catálogo de Luna, Marte, Sol, Júpiter) | `BL-AE-1` |
| L12 | `ClassicalElements` no tiene la ley de Kepler del tiempo (`t_p`) ni la validación de tipo cónico (hiperbólica) | `BL-AE-2` |
| L13 | **No hay traza E0 de `satcom`** (el balance de enlace no se explica paso a paso) | §15.2 |
| L14 | No hay atenuación por lluvia (UIT-R P.838 `γ = k·R^α`, P.618 longitud efectiva) | `BL-AE-9` |
| L15 | No hay gases atmosféricos ni nubes (valores de tabla, entrada del usuario) | `BL-AE-9` |
| L16 | No hay temperatura de ruido de cielo por lluvia `T = T_m·(1−10^(−A/10))`, ni ruido del suelo/spillover, ni `T_A` de antena | `BL-AE-10` |
| L17 | No hay degradación C/N en lluvia ni disponibilidad estadística (porcentaje de tiempo) | `BL-AE-9` (opcional) |
| L18 | No hay interferencias: C/I, C/(N+I), enlace descendente con interferencia de satélite adyacente | `BL-AE-11` |
| L19 | No hay pérdida de apuntamiento ni por polarización (PLF) en el balance (solo `LossEntry` genérica) | `BL-AE-8` |
| L20 | No hay canal con multicamino (Rayleigh, Rice, Loo/LMSC) ni margen de desvanecimiento | `BL-AE-10b` |
| L21 | No hay *back-off* de amplificador no lineal (IBO/OBO), AM/AM, AM/PM, intermodulación (2f₁−f₂), P₁dB, IIP₃ | `BL-AE-12` |
| L22 | No hay plan de frecuencias de transpondedor ni ancho de banda de canal con *roll-off* | `BL-AE-12` |
| L23 | No hay acceso múltiple: FDMA/TDMA/CDMA, eficiencia de trama, ALOHA puro y ranurado | `BL-AE-15` |
| L24 | No hay ganancia de codificación ni tasa de código en el balance (`E_b/N₀` requerido con código) | `BL-AE-14` |
| L25 | No hay presupuesto de espacio profundo parametrizado (distancias 10⁸–10¹⁰ km, ganancia de DSN) | `BL-AE-11` |
| L26 | No hay latencia de propagación ni retardo de ida y vuelta | `BL-AE-11` |
| L27 | **La página aeroespacial cuelga de `EngineeringPanel`**: cambiar de módulo recrea el apilado de circuitos | §17.1, AE-R.5 |
| L28 | No hay servicio de aplicación aeroespacial: la lógica `solve`/`solve_ellipse` vive en la UI | §3.4 |
| L29 | No hay dibujo de diagramas de bloques de enlace ni de carga útil | §12 |
| L30 | No hay catálogo de ejercicios aeroespaciales en Knowledge ni en `ExerciseService` | §13, §16 |

### 2.9 Hallazgos de deuda y riesgos del código (H1..H10)

| Id | Hallazgo | Consecuencia |
|---|---|---|
| H1 | **Radio terrestre ambiguo**: `EARTH_RADIUS_M = 6371000` (medio IUGG) pero la altitud GEO clásica (35 786 km) usa el radio **ecuatorial** 6378,137 km. Con el radio medio, `a_GEO − R` da **35 793 km** | La convención debe ser **declarada y seleccionable** (§5, C1); un test GEO no puede esperar 35 786 con el preset actual |
| H2 | **Día sidéreo frente a solar**: la GEO exige el sidéreo (86 164,0905 s); con el solar (86 400 s) sale 42 241 km. El motor no distingue, cada llamada recibe `period_s` | Convención C2 declarada; constante nombrada en el paquete |
| H3 | **Lógica de cálculo dentro de la UI**: `OrbitPanel.solve` y `solve_ellipse` | Pasan a un servicio de aplicación (§3.4); la UI solo pinta |
| H4 | **«structural-aero» no existe**. El brief lo agrupa con orbital y satcom, pero `domain\engineering\structural` (6 ficheros, 1 988 líneas) es el reconocimiento de topologías de **circuitos** y lo consumen `domain\electronics\recognition.py` y `applicability.py` | **Se queda en circuitos** (coincide con `CIRCUITS_LAB.md` H9 y D6); no se mueve nada de él |
| H5 | `satcom` depende de `control.errors.ControlError` como error de dominio **común** | Se reutiliza el tipo tal cual (alias en el paquete nuevo); no se crea un error paralelo (D5) |
| H6 | `satcom` depende de `comms.metrics` y `rf.margins` | Tras la migración el flujo es **aeroespacial → circuitos**, nunca al revés; regla de capas nueva (§3.2) |
| H7 | `test_satcom_layer_direction` y `test_f16_orbital` leen **rutas físicas** | Se parametrizan con un helper de rutas (paso AE-R.2) |
| H8 | `ModulesDialog` y `module_index` importan `…engineering.orbital.bodies` | Cambia la importación al nuevo paquete; el id `aerospace` no cambia |
| H9 | `ui\aerospace.py` es un **módulo**; se quiere un **paquete** `ui\aerospace\` con varias páginas | `from academic_core.ui.aerospace import OrbitPanel` **debe seguir funcionando** (reexportación, AE-R.5); los tests de UI importan esa ruta |
| H10 | Las reglas de dirección de capas están por **nombre de segmento** (`"engineering" in segs`) | El codemod de CI-R y el de AE-R **tocan el mismo fichero** `test_architecture.py`; orden y coordinación en §20.5 |

---

## Bloque transversal — experiencia académica completa

Todos los ejercicios y experimentos de este laboratorio deben poder recorrer el contrato común:

`Enunciado → Datos → Hipótesis → Modelo → Elección del método → Cálculo/Simulación → Verificación independiente → Resultado → Interpretación → Gráfica/Diagrama → Conclusión`

### Modo problema
- El estudiante puede introducir o recibir un enunciado, datos y condiciones.
- Las hipótesis y convenciones relevantes quedan visibles y forman parte del resultado.
- Cada paso significativo queda trazado y puede ser revisado.
- El resultado usa el contrato común `Resultado`, con exactitud/aproximación, error cuando proceda, trazabilidad, avisos y sello de verificación.
- Si no existe una segunda vía de comprobación suficiente, el sistema no presenta el resultado como plenamente verificado.

### Modo experimento
`Hipótesis → Configuración → Simulación/Cálculo → Medición → Resultado → Comparación → Error → Explicación`

Debe permitir comparar, cuando tenga sentido, teoría frente a cálculo numérico, simulación o medición, dejando explícita la causa de las discrepancias.

### Interoperabilidad
El laboratorio expone y consume resultados mediante contratos estables, sin importar directamente la UI de otros laboratorios:
- `MATH_LAB → todos`: álgebra, cálculo, unidades, métodos numéricos y verificación.
- `DIGITAL_DESIGN_LAB → CIRCUITS_LAB`: lógica digital y HDL.
- `CIRCUITS_LAB → SIGNALS_LAB`: circuitos como sistemas físicos.
- `SIGNALS_LAB → CIRCUITS_LAB / AEROSPACE_LAB`: señales, modulación, ruido y métricas.
- `SIGNALS_LAB → AEROSPACE_LAB`: capa física y comunicaciones.
- `AEROSPACE_LAB` integra los resultados anteriores para problemas de sistema.

La interfaz concreta de la futura **Labs App** queda fuera de este documento: aquí se define el comportamiento del laboratorio y sus contratos, no su diseño visual.



### Capacidad transversal — Corrector académico

El laboratorio debe integrarse con un **Corrector Académico común**. La corrección no se limita a comparar el resultado final: debe localizar, cuando sea posible, el **primer punto incorrecto** del procedimiento y clasificar el tipo de error.

Debe poder distinguir al menos:
- resultado correcto;
- unidad incorrecta;
- procedimiento incorrecto;
- error algebraico;
- error numérico;
- error de redondeo;
- error conceptual;
- hipótesis o convención incorrecta;
- dato mal interpretado;
- método inadecuado;
- paso omitido;
- signo incorrecto;
- incompatibilidad dimensional.

El corrector debe explicar la causa del error y su propagación hacia los pasos posteriores cuando pueda determinarla. Cada laboratorio aporta sus reglas de dominio, pero la clasificación, trazabilidad y contrato de corrección son comunes.
