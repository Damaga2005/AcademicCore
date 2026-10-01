# Laboratorio de Diseño Digital — Especificación de diseño

Estado: **aprobada en lo esencial (decididas D1, D2, D3, D4, D8, D9, D11, D12, D13, D14, D16, D17, D18 y D19; pendientes D5 y D6 con recomendación, y D7, D10 y D15; ver §20.3, §22.12 y §22.13)**, sin implementación iniciada · Fecha: 2026-09-30 · Revisión: hardware objetivo y visión local con Ollama · Ruta de UI: `engineering/digital-logic` (id estable, ver §23.6) · **Ampliado el 2026-09-30 con la §22 (conceptos de las guías docentes; sin HDL, decisión D11)** · **Alineado el 2026-10-01 con `MATH_LAB.md` v2, `SIGNALS_LAB.md` y `CIRCUITS_LAB.md` (nueva §23 «Relación con otros laboratorios»; las decisiones D1 a D16 no cambian)**
Ámbito: convertir la página «Lógica digital» en un laboratorio completo de diseño digital: dibujar, simular, comprobar, explicar paso a paso, reducir con álgebra de Boole, calcular, importar por imagen y exportar.

---

## 0. Cómo leer este documento

| Sección | Contenido |
|---|---|
| 1 | Objetivo, requisitos del usuario y principios |
| 2 | Punto de partida real (qué existe hoy en el repositorio y qué no) |
| 3 | Arquitectura y reparto por capas |
| 4 | **Motor de álgebra de Boole con demostración paso a paso** (el núcleo pedido) |
| 5 | Tabla de verdad, formas canónicas y simplificación (Karnaugh, Quine-McCluskey, Petrick) |
| 6 | Editor visual de circuitos |
| 7 | Simulación, temporización y análisis (riesgos, glitches, camino crítico) |
| 8 | Lógica secuencial (biestables, FSM, contadores, registros) |
| 9 | Biblioteca de componentes (MSI, aritmética, memorias) |
| 10 | Calculadoras y herramientas numéricas |
| 11 | Comprobación y verificación de resultados (oráculos independientes) |
| 12 | Explicación paso a paso (integración con la traza de ejecución E0) |
| 13 | Importar desde imagen (OpenCV + Ollama, todo local; perfiles de hardware) |
| 14 | Importación y exportación (BLIF, PLA, CSV, VCD, imagen, PDF; **sin HDL**) |
| 15 | Persistencia, proyectos y conexión con Ejercicios |
| 16 | Accesibilidad, localización y rendimiento |
| 17 | Seguridad y privacidad |
| 18 | Plan de pruebas y criterios de aceptación |
| 19 | Fases de entrega |
| 20 | Riesgos, límites conocidos y decisiones abiertas |
| 21 | Cosas que no se habían pedido pero se incluyen |
| **22** | **Ampliación: conceptos de las guías docentes (asíncronos, CMOS, temporización, ASM, memorias, CPU educativa, procesado digital, códigos). Sin HDL.** |
| A–D | Anexos: catálogo de leyes, formato de ficheros, mapa de módulos, glosario |
| **23** | **Relación con otros laboratorios** (`MATH_LAB`, `SIGNALS_LAB`, `CIRCUITS_LAB`, futuro aeroespacial): fronteras, dependencias, rutas y paquetes tras CI-R |

---

## 1. Objetivo y requisitos

### 1.1 Objetivo

Que un estudiante pueda, en una sola pantalla, hacer **todo el ciclo de un ejercicio de electrónica digital**:

1. Partir de un enunciado (función, tabla, esquema en papel o foto).
2. Obtener la **tabla de la verdad**.
3. Obtener la **función lógica** en forma canónica (minitérminos/maxitérminos).
4. **Reducirla** con álgebra de Boole, viendo **cada paso** con la ley aplicada, hasta la función reducida.
5. Confirmar la reducción con Karnaugh y Quine-McCluskey.
6. **Dibujar el circuito** con N puertas, simularlo y ver sus formas de onda.
7. **Comprobar** que el circuito dibujado equivale a la función esperada.
8. Ver **paso a paso** por qué cada salida toma cada valor.
9. Usar calculadoras (bases, complemento a 2, Gray, BCD, coma flotante, CRC, Hamming…).
10. Guardar, exportar y reutilizar el diseño.

### 1.2 Requisitos explícitos del usuario (trazabilidad)

| Id | Requisito (textual o resumido) | Sección |
|---|---|---|
| R1 | Dibujar cualquier circuito con N puertas | 6 |
| R2 | Simularlo | 7 |
| R3 | Comprobar resultados | 11 |
| R4 | Ver paso a paso los resultados | 12 |
| R5 | Subir una imagen del circuito y reconocerla (OCR) | 13 |
| R6 | Tabla de la verdad | 5 |
| R7 | Pasos hasta la función lógica reducida tras álgebra de Boole | 4 |
| R8 | Calculadoras y todo lo relacionado | 10 |
| R9 | Lo más avanzado que exista sobre el tema | 7, 8, 9, 11, 14 |
| R10 | Mencionar lo que el usuario no haya pensado | 21 |

### 1.3 Principios de diseño

1. **Determinismo y exactitud.** Todo resultado es una función pura de la entrada. Sin reloj de pared, sin aleatoriedad no sembrada. Mismo diseño → mismo resultado → mismo *digest*.
2. **Nada se inventa en la interfaz.** La UI dibuja y envía órdenes; la lógica vive en dominio y aplicación (misma regla que el resto del proyecto: «zero solver code» en `ui/`).
3. **Todo resultado es explicable y verificable.** Cada transformación produce una traza (qué ley, qué antes, qué después) y se valida con un método independiente.
4. **Dos implementaciones, un solo veredicto.** Cualquier simplificación o equivalencia se comprueba exhaustivamente por tabla de verdad (o con SAT/BDD si hay muchas variables) antes de mostrarse como «correcta».
5. **La IA propone, el motor decide.** El reconocimiento de imagen nunca simula sin revisión humana; las explicaciones vienen de la traza del motor, no de un modelo generativo.
6. **Español por defecto**, con los identificadores internos y valores de enumeración en inglés (convención ya establecida: `SUCCESS`, `EQUIVALENT`, etc.).
7. **Sin dependencias pesadas si la biblioteca estándar basta.** Cada dependencia nueva se justifica y es opcional cuando se pueda.

---

## 2. Punto de partida real

### 2.1 Qué existe hoy

Motor digital certificado F8-Q (`src/academic_core/domain/engineering/digital/` más `domain/engineering/digital_circuit.py`, 300 líneas; las rutas «engineering» cambian con la fase CI-R de `CIRCUITS_LAB.md`, ver §23.5):

| Módulo | Aporta |
|---|---|
| `core.py` | `DigitalCircuit`, `DigitalNet`, `DigitalEvent`, `EventQueue`, `DigitalSimulator`. Lógica de **dos estados** (BAJO/ALTO), dirigida por eventos, tiempo en `Decimal`, **retardo cero**, orden canónico, tope de 1 024 nodos y 1 000 000 de eventos, detección de bucles de retardo cero. |
| `components.py` | `GateKind` (NOT, AND, OR, XOR, NAND, NOR, XNOR), `DigitalComponent` de N entradas, `GateEvaluator`. |
| `stimuli.py` | `ToggleStimulus`, `PatternStimulus`. |
| `trace.py`, `replay.py`, `serialization.py` | Traza `digital-trace/1`, repetición y comparación por digest. |
| `analyzer.py` | `LogicAnalyzer`: captura con ventana y disparo (flanco ascendente, descendente, ambos; pre y post disparo). |

Aplicación: `application/digital_service.py` (servicio, demos, vistas), `application/explain_service.py` (explicación desde traza de ejecución E0), y —**añadido en esta sesión**— `application/digital_design.py` (diseño editable `digital-design/1`).
UI: `ui/logic_analyzer.py` (analizador), `ui/waveform.py` (formas de onda), y —**añadido**— `ui/digital_editor.py` (lienzo con entradas, 7 puertas y cables).

### 2.2 Qué falta (lagunas verificadas)

| Laguna | Consecuencia |
|---|---|
| Solo 2 estados y retardo cero | No hay alta impedancia, no hay desconocido `X`, no hay glitches por retardo real, no hay biestables. |
| Sin componentes secuenciales | No se puede hacer un contador ni una máquina de estados. |
| Sin álgebra de Boole simbólica | No hay expresiones, ni tabla de verdad, ni simplificación. |
| Sin comprobación de equivalencia | «Verificar repetición» solo demuestra reproducibilidad, no corrección. |
| Editor sin deshacer, zoom, selección múltiple, copiar/pegar, subcircuitos | Incómodo por encima de ~15 elementos. Límite actual: 64 elementos, 8 entradas por puerta. |
| Diseños solo en memoria + JSON manual | Se pierden al cerrar si no se guardan. |
| Sin importar imagen, sin exportar | — |
| Sin calculadoras digitales | — |
| Sin conexión con Ejercicios | — |

---

## 3. Arquitectura

Se respeta la arquitectura por capas del proyecto (dominio puro → aplicación → UI; sin Qt fuera de `ui/`).

```
domain/engineering/digital/          (motor certificado + ampliaciones)
  boolean/                           NUEVO  álgebra de Boole simbólica
    expr.py            AST inmutable de expresiones + normalización
    parse.py           lector de expresiones (varias notaciones)
    laws.py            catálogo de leyes con patrón, condición y nombre
    rewrite.py         motor de reescritura con traza de pasos
    simplify.py        estrategias de reducción (guiada por leyes)
    truth.py           tabla de verdad, minitérminos, maxitérminos
    canonical.py       SOP/POS canónicas, numeración Σm / ΠM
    kmap.py            mapas de Karnaugh (2–6 variables) y agrupaciones
    qm.py              Quine-McCluskey + Petrick (multisalida)
    espresso.py        heurística tipo Espresso para muchas variables
    bdd.py             diagramas de decisión binarios (ROBDD)
    equiv.py           equivalencia: tabla, BDD y SAT
    sat.py             pequeño CDCL / DPLL para equivalencia grande
    hazards.py         riesgos estáticos y dinámicos (análisis lógico)
    synth.py           síntesis: expresión/tabla → circuito de puertas
    techmap.py         mapeo a solo-NAND, solo-NOR, AOI, MUX, ROM
  seq/                                NUEVO  lógica secuencial
    latch.py, flipflop.py, register.py, counter.py, shift.py
    fsm.py             máquinas de estados (Moore/Mealy), minimización
    timing.py          setup/hold, metaestabilidad (modelo), frecuencia máx.
  calc/                               NUEVO  calculadoras
    radix.py, twos.py, gray.py, bcd.py, ieee754.py, fixedpoint.py
    parity.py, hamming.py, crc.py, arith.py (sumadores, restas, Booth)
  core.py / components.py / ...       EXISTE, NO SE TOCA (certificado F8-Q)
  digital2/                           NUEVO  motor ampliado al lado (4 valores + retardos), ver §7.1 y Anexo C

application/
  digital_design.py                   EXISTE   diseño editable (se amplía)
  digital_service.py                  EXISTE   captura / demos
  digital_lab.py                      NUEVO    fachada del laboratorio
  digital_import.py                   NUEVO    imagen / BLIF / PLA / CSV
  digital_export.py                   NUEVO    BLIF / PLA / CSV / VCD / SVG / PDF
  digital_explain.py                  NUEVO    lecciones paso a paso

ui/
  digital_editor.py                   EXISTE   lienzo (se amplía)
  digital_lab_page.py                 NUEVO    pestañas del laboratorio
  digital_boolean_view.py             NUEVO    álgebra + pasos
  digital_truth_view.py               NUEVO    tabla de verdad, Karnaugh
  digital_calc_view.py                NUEVO    calculadoras
  digital_fsm_view.py                 NUEVO    diagrama de estados
```

**Rutas del árbol.** Los nombres `domain/engineering/digital/...` de este documento son los del árbol **actual**. `CIRCUITS_LAB.md` §3.7 y §3.8 renombra `domain/engineering` a `domain/circuits` (fase CI-R) y declara que `digital/` **sale** hacia este laboratorio. Destino físico de todo el código digital (antiguo y nuevo) y orden de los movimientos: §23.5. Hasta entonces, nada de este documento depende de la ruta física.

### 3.1 Pestañas de la página

`Circuito` (editor + simulación + formas de onda) · `Álgebra` (expresión, leyes, pasos) · `Tabla y Karnaugh` · `Secuencial` (FSM, biestables) · `Calculadoras` · `Importar / Exportar` · `Comprobar`. Una **barra de estado común** muestra el circuito activo y su estado de validación.

### 3.2 Un modelo, varias vistas

El **diseño** (`DigitalDesign`) y la **expresión** (`BoolExpr`) son dos vistas del mismo objeto lógico. Regla: cualquier vista puede generar las otras.

```
Expresión  ⇄  Tabla de verdad  ⇄  Circuito (puertas)  ⇄  BLIF / PLA
   ⇅                ⇅                    ⇅
Minitérminos     Karnaugh            Formas de onda
```

Cada flecha es una función del dominio con test de ida y vuelta (round-trip), y se valida por equivalencia (§11).

---

## 4. Motor de álgebra de Boole con demostración paso a paso

Este es el requisito central (R7). Se diseña como un **motor de reescritura con traza**, no como un simplificador caja negra: cada paso registra la ley aplicada, el subtérmino afectado y la expresión resultante.

### 4.1 Representación

`BoolExpr` es un árbol inmutable y *hashable*:

- Átomos: `Var(nombre)`, `Const(0|1)`.
- Operadores: `Not`, `And(n-aria)`, `Or(n-aria)`, `Xor(n-aria)`, `Xnor`, `Nand`, `Nor`, `Implies`, `Iff`.
- Los `And/Or/Xor` son **n-arios y aplanados**; los operandos se ordenan canónicamente (orden total sobre variables y estructuras) para que dos expresiones equivalentes por asociatividad/conmutatividad tengan **la misma forma normal sintáctica**. Esto hace fiable la comparación y el *hash*.
- Se conserva la **notación de origen** del usuario para mostrarla igual (p. ej. `A'`, `¬A`, `!A`, `~A`, `Ā`).

### 4.2 Notaciones de entrada

El lector acepta, mezcladas:

| Concepto | Ejemplos aceptados |
|---|---|
| NOT | `A'`, `!A`, `~A`, `¬A`, `NOT A`, `Ā` (con barra combinada) |
| AND | `A·B`, `A*B`, `A&B`, `AB` (yuxtaposición), `A AND B`, `A∧B` |
| OR | `A+B`, `A\|B`, `A OR B`, `A∨B` |
| XOR | `A⊕B`, `A^B`, `A XOR B` |
| Constantes | `0`, `1`, `V/F`, `H/L` |
| Paréntesis | `()`, `[]` |
| Suma de minitérminos | `Σm(1,3,5,7)`, `F(A,B,C)=Σ(1,3,7)` |
| Producto de maxitérminos | `ΠM(0,2,4)` |
| Con «don't care» | `Σm(1,3)+d(5,7)` |

La precedencia sigue el estándar: NOT > AND > XOR > OR, y se muestra siempre **parentizada explícitamente** en los pasos para evitar ambigüedad. Errores de sintaxis devuelven posición y mensaje en español («falta cerrar el paréntesis abierto en la posición 7»), nunca una excepción cruda.

### 4.3 Catálogo de leyes (resumen; detalle en el Anexo A)

Cada ley tiene: **id**, **nombre en español**, **patrón**, **plantilla de reemplazo**, **condiciones** y **dirección** (expandir/reducir/neutra).

| Familia | Leyes |
|---|---|
| Identidad | `A+0=A`, `A·1=A` |
| Nulo / dominación | `A+1=1`, `A·0=0` |
| Idempotencia | `A+A=A`, `A·A=A` |
| Complemento | `A+A'=1`, `A·A'=0` |
| Involución | `(A')'=A` |
| Conmutativa / Asociativa | `A+B=B+A`, `(A+B)+C=A+(B+C)` (y con AND) |
| Distributiva | `A(B+C)=AB+AC`, `A+BC=(A+B)(A+C)` |
| Absorción | `A+AB=A`, `A(A+B)=A` |
| Absorción generalizada / Adyacencia | `A+A'B=A+B`, `A(A'+B)=AB`, `AB+AB'=A`, `(A+B)(A+B')=A` |
| De Morgan | `(AB)'=A'+B'`, `(A+B)'=A'B'` (n-aria) |
| Consenso | `AB+A'C+BC=AB+A'C`, y su dual |
| Shannon | expansión `F=A·F(1)+A'·F(0)` |
| Xor | `A⊕B=AB'+A'B`, `A⊕0=A`, `A⊕1=A'`, `A⊕A=0`, `A⊕A'=1` |
| Implicación / equivalencia | `A→B=A'+B`, `A↔B=(A⊕B)'` |
| Nand/Nor universales | `A'=(A·A)'`, `AB=((AB)')'`… |
| Dualidad | El dual de toda ley válida es válido (se verifica en pruebas). |

### 4.4 Algoritmo de reducción guiada

El motor no aplica leyes al azar: usa una **estrategia por fases**, para que la explicación sea didáctica y el resultado repetible.

1. **Normalización inicial.** Eliminar `→`, `↔`, `⊕` (si el usuario elige «solo AND/OR/NOT») y aplicar De Morgan hasta que los NOT estén sobre variables.
2. **Aplanado.** Aplicar asociatividad; reordenar canónicamente.
3. **Expansión a suma de productos** (distributiva) solo si el objetivo lo requiere (SOP) — o a producto de sumas (POS).
4. **Reducción.** Repetir hasta punto fijo, con prioridad:
   1. idempotencia, complemento, nulo, identidad;
   2. absorción;
   3. adyacencia (`AB+AB'=A`);
   4. absorción generalizada (`A+A'B=A+B`);
   5. consenso (para eliminar términos redundantes);
   6. factor común (distributiva inversa) si reduce el coste.
5. **Comprobación de mínimo.** Se compara el resultado con la mínima forma obtenida por Quine-McCluskey/Petrick (§5.4). Si el álgebra se queda en una forma **no mínima** (mínimo local), el motor lo dice explícitamente y propone los pasos adicionales (p. ej. añadir un término de consenso y luego absorber), en lugar de afirmar que es mínima.
6. **Verificación.** La expresión final se comprueba equivalente a la original por tabla/BDD/SAT. Si no lo fuera, **se descarta la traza y se informa como error interno** (nunca se muestra una demostración falsa).

Modos de estrategia seleccionables por el alumno: **SOP mínima**, **POS mínima**, **solo NAND**, **solo NOR**, **mínimo número de literales**, **mínimo número de puertas**, **mínimo de entradas por puerta** (límite de fan-in, p. ej. 2 o 3), **libre** (deja elegir la ley manualmente).

### 4.5 Modo asistido («aplica tú la ley»)

Además del modo automático, un **modo manual guiado**: el alumno selecciona un subtérmino y el sistema le muestra **qué leyes son aplicables ahí**; el alumno elige y el sistema **comprueba que el paso es válido** (equivalencia local + global). Si el alumno se equivoca, el sistema indica **por qué** ese paso no es válido (contraejemplo con valores concretos: «con A=1, B=0 la expresión de antes vale 1 y la de después 0»). Esto sirve para estudiar y para corregir ejercicios (§15.3).

### 4.6 Formato de cada paso

```
Paso 3 de 7                         [Ley: Absorción  A + A·B = A]
Antes:   F = A·B' + A·B'·C + A'·B
                └───────┘
                subtérmino afectado: A·B' + A·B'·C  (A := A·B')
Después: F = A·B' + A'·B
Justificación: (A·B') + (A·B')·C = A·B' por absorción con A := A·B', B := C
Comprobación: equivalente ✔ (8/8 combinaciones)
Literales: 8 → 6 · Puertas: 6 → 4
```

Se muestran: expresión completa antes/después, **resaltado del subtérmino**, la **sustitución de metavariables** (`A := A·B'`), coste antes/después y el sello de comprobación. La lista de pasos es navegable (anterior/siguiente/reproducir/saltar a ley) y exportable.

### 4.7 Ejemplo completo (lo que debe producir)

Entrada: `F(A,B,C) = A'BC + AB'C + ABC' + ABC`

| # | Expresión | Ley |
|---|---|---|
| 0 | `A'BC + AB'C + ABC' + ABC` | Original |
| 1 | `A'BC + AB'C + ABC' + ABC + ABC` | Idempotencia (duplicar `ABC`) |
| 2 | `(A'BC + ABC) + (AB'C + ABC) + ABC'` | Reagrupar (asociativa/conmutativa) |
| 3 | `BC(A' + A) + AC(B' + B) + ABC'` | Distributiva (factor común) |
| 4 | `BC·1 + AC·1 + ABC'` | Complemento |
| 5 | `BC + AC + ABC'` | Identidad |
| 6 | `BC + A(C + BC')` | Distributiva (factor común de A) |
| 7 | `BC + A(C + B)` | Absorción generalizada `C + BC' = C + B` |
| 8 | `BC + AC + AB` | Distributiva |
| — | **Forma mínima: `AB + AC + BC`** | Coincide con Quine-McCluskey y con Karnaugh |

Este ejemplo es una **prueba de aceptación** (§18): el motor debe reproducir una secuencia válida y llegar a la misma forma mínima.

### 4.8 Expresiones con «don't care»

Las condiciones «no importa» (`d`) se conservan y se usan **solo donde reducen**: la traza indica qué `d` se han **tomado como 1** y cuáles como 0, y advierte que la reducción es válida **solo** para las combinaciones especificadas.

### 4.9 Multisalida

Para varias funciones a la vez (`F1, F2, F3` con las mismas variables) el motor:

- Simplifica cada una y además busca **términos producto compartidos** (Quine-McCluskey multisalida) para reducir el número total de puertas.
- Muestra el coste con y sin compartición.

### 4.10 Límites y garantías

| Aspecto | Garantía |
|---|---|
| Variables | Álgebra y Karnaugh: hasta 6 variables (Karnaugh); tabla de verdad exhaustiva: hasta 20 variables (1 048 576 filas, con tope y aviso); más allá, BDD/SAT para equivalencia y Espresso para reducción heurística (sin garantía de mínimo, se declara). |
| Tiempo | Tope de pasos (p. ej. 500) y de tamaño; si se supera, se detiene con un mensaje claro y se devuelve lo obtenido hasta ese punto, marcado como **parcial**. |
| Optimalidad | «Mínima» solo se afirma cuando Quine-McCluskey + Petrick la certifica; si no, se dice «reducida» y se indica si hay un mínimo mejor conocido. |
| Determinismo | Mismo input → misma traza (orden de leyes fijo y desempates canónicos). |

---

## 5. Tabla de verdad, formas canónicas y simplificación

### 5.1 Tabla de verdad

- Se genera desde: una **expresión**, un **circuito dibujado**, una **lista de minitérminos/maxitérminos**, o una **descripción**.
- Orden de filas por defecto: binario natural con la variable de mayor peso a la izquierda (`000, 001, …`). Alternativas: **código Gray** (para Karnaugh).
- Columnas: entradas, cada **salida**, y opcionalmente **columnas intermedias** (valor de cada subexpresión o de cada nodo del circuito), para ver de dónde sale cada resultado.
- Soporta **salidas múltiples**, **valores `X` (indiferentes)** y **tabla incompleta** (algunas combinaciones no especificadas).
- Acciones: resaltar filas que valen 1 (o 0), **exportar** a CSV/Markdown/LaTeX/imagen, **editar la salida** haciendo clic (para crear una función a partir de una tabla).
- **Numeración de filas** (decimal) y notación `Σm(...)`/`ΠM(...)` mostrada a la vez.

### 5.2 Formas canónicas

- **SOP canónica** (suma de minitérminos) y **POS canónica** (producto de maxitérminos), con la identidad `mᵢ = Mᵢ'` mostrada.
- Paso a paso «tabla → función»: se listan las filas con salida 1, se escribe cada minitérmino (`A'BC`, …) y se suman.
- **Expansión** de una expresión no canónica a canónica (añadir variables faltantes con `(X + X')`), con pasos.
- Conversión entre `Σm` y `ΠM` (complementar el conjunto de índices).

### 5.3 Mapas de Karnaugh

- 2, 3, 4, 5 y 6 variables (5 y 6 como mapas apilados/con espejo, con aviso de cómo leer las adyacencias).
- **Agrupaciones** de tamaño potencia de 2, incluidas las **cíclicas** (bordes que se tocan), con colores por grupo.
- Indicación de **implicantes primos**, **primos esenciales** y **redundantes**.
- Manejo de `X`: el grupo puede englobar `X` cuando reduce; se marcan cuáles se usaron.
- **Modo SOP y modo POS** (agrupar 1s o 0s).
- Interacción: el alumno **dibuja sus propios grupos** y el sistema los valida y le dice si son maximales, si se solapan innecesariamente o si falta cubrir algún 1.
- Paso a paso: «Grupo 1: celdas 3, 7, 11, 15 → `C·D`» con la eliminación de variables explicada («A y B cambian dentro del grupo, se eliminan»).
- Salida múltiple: mapas paralelos con marcado de términos compartidos.

### 5.4 Quine-McCluskey y método de Petrick

- **Tabulación** por número de unos, combinación de pares que difieren en un bit, marcado de implicantes primos.
- **Tabla de cobertura** (implicantes vs. minitérminos), detección de **esenciales**, **reducción por dominancia** de filas y columnas, y **Petrick** para resolver los ciclos.
- **Todas las soluciones mínimas** cuando hay empates (se muestran y se elige por criterio de coste).
- Coste configurable: literales, puertas, entradas, **coste ponderado** (p. ej. 1 por puerta + 1 por entrada) y coste con **NOT gratis o no** (según se dispongan las variables complementadas).
- Multisalida (implicantes compartidos) y `X`.
- Cada tabla se **muestra paso a paso** como en un libro de texto.

### 5.5 Espresso y grandes funciones

Para más de ~10 variables, un minimizador heurístico (`EXPAND–IRREDUNDANT–REDUCE`) con resultado **verificado por equivalencia** aunque no garantice mínimo. Se declara siempre «reducida, no certificada como mínima».

### 5.6 Síntesis y mapeo tecnológico

- De expresión/tabla a **circuito de puertas** (dos niveles AND-OR, OR-AND).
- **Mapeo a solo NAND** y **solo NOR** con la transformación mostrada paso a paso (doble negación + De Morgan).
- Mapeo a **AOI/OAI**, a **multiplexores** (Shannon), a **ROM/LUT** (tabla → memoria), a **decodificador + OR**.
- **Factorización multinivel** (extracción de subexpresiones comunes, división algebraica) con comparación de coste entre dos niveles y multinivel.
- Restricción de **fan-in** máximo: descomposición de puertas anchas en árboles.
- Informe: nº de puertas por tipo, nº de literales, profundidad lógica (niveles), fan-out máximo.

---

## 6. Editor visual de circuitos

### 6.1 Estado y objetivos

El editor actual (colocar entradas y 7 puertas, cablear, mover, borrar, editar estímulo y pines, guardar/abrir JSON) se **amplía** hasta uso serio de circuitos grandes.

**Núcleo de lienzo compartido.** `CIRCUITS_LAB.md` §7 pide un editor con las mismas capacidades genéricas (deshacer, zoom, selección, rejilla, buses, etiquetas de red, jerarquía, DRC en vivo, símbolos ANSI/IEC) y `SIGNALS_LAB.md` §7.8 un lienzo de solo lectura. Lo genérico (viewport, selección, pila de comandos, enrutado ortogonal, culling e índice espacial, minimapa, motor de reglas DRC) vive en un **núcleo neutral de UI** que no conoce puertas ni resistencias; este laboratorio y el de circuitos son **clientes**. Lo define el primero que se construya y el otro lo importa (misma regla que `SIGNALS_LAB.md` D8), con prueba de contrato común. Detalle en §23.4.

### 6.2 Capacidades a añadir

| Área | Capacidad |
|---|---|
| Elementos | Salidas explícitas (LED, display de 7 segmentos, sonda), constantes 0/1, **buses** (entrada/salida de varios bits), **etiquetas de red**, texto y notas, **entradas interactivas** (interruptor, pulsador) para «jugar» con el circuito en vivo. |
| Edición | **Deshacer/rehacer ilimitado** (pila de comandos), copiar/cortar/pegar, **selección múltiple** (rectángulo, Mayús+clic), **alinear y distribuir**, girar/voltear, ajustar a rejilla, mover con teclado. |
| Cableado | Cables **ortogonales con enrutado automático**, uniones (puntos de conexión) visibles, **buses con división y unión** (`A[3:0]`), **etiquetas de red** que conectan sin cable, resaltado de toda la red al pasar el ratón, arrastrar un cable existente para reconectar. |
| Vista | **Zoom y desplazamiento** (rueda, gesto, barra espaciadora+arrastre), **encajar a la ventana**, **mini-mapa**, rejilla opcional, tema claro/oscuro. |
| Jerarquía | **Subcircuitos** (crear un bloque a partir de una selección, con pines de entrada/salida), **biblioteca de bloques** reutilizables, instancias con parámetros (anchura del bus), **entrar y salir** de un bloque. |
| Símbolos | Estilos **ANSI/IEEE (forma)** e **IEC 60617 (rectángulo con `&`, `≥1`, `=1`)**, alternables; burbujas de inversión; entradas invertidas en la puerta. |
| Ayudas | Autocompletado de puertas (escribe `nand` y aparece), **comprobación de reglas** en vivo (§6.4), **vista en árbol/lista** del circuito, buscar elemento por nombre. |
| Salida | Exportar a **PNG/SVG/PDF** (§14), imprimir, copiar al portapapeles como imagen. |
| Ejemplos | Galería de circuitos de libro (semisumador, sumador completo, multiplexor, decodificador, comparador, ALU de 4 bits, flip-flop, contador…) que se cargan y se **modifican**. |

### 6.3 Escala

- Objetivo: **≥ 5 000 elementos** con desplazamiento fluido (dibujo por *culling* de lo visible, índice espacial para clics, *repaint* por regiones).
- El tope del motor sigue en 1 024 nodos por diseño plano, **pero** se sube configurable y, con jerarquía, se **aplana** solo para simular (con el límite y su error explicados).
- Simulación en **hilo aparte** con cancelación, como en el resto de laboratorios (`ServiceWorker`).

### 6.4 Comprobación de reglas de diseño (DRC)

Avisos en vivo, con posición en el lienzo, gravedad y arreglo sugerido:

| Regla | Gravedad |
|---|---|
| Pin de entrada sin conectar | Error |
| Salida de puerta sin uso | Aviso |
| Dos salidas conectadas a la misma red (**cortocircuito**) | Error |
| **Bucle combinacional** (realimentación sin elemento de memoria) | Aviso/Error (según modo) |
| Entrada sin fuente/estímulo | Aviso |
| Fan-out excesivo (> N) | Aviso |
| Nombre duplicado o no válido | Error |
| Bus con anchuras incompatibles | Error |
| Puerta de N entradas con entradas repetidas (`AND(A,A,B)`) | Info (simplificable) |
| Lógica redundante detectable (`A·A'`, constante) | Info con botón «simplificar» |

### 6.5 Interacción y teclado

Todas las herramientas con **atajos** (por ejemplo `V` mover, `W` cable, `I` entrada, `A/O/N/X` puertas, `Del` borrar, `Ctrl+Z/Y`, `Ctrl+C/V/X`, `Ctrl+A`, `F` encajar, `+/-` zoom, flechas para mover, `Esc` cancelar). Operable **solo con teclado** (§16).

---

## 7. Simulación, temporización y análisis

### 7.1 Ampliación del motor (decisión de diseño importante)

El motor certificado es de **2 estados y retardo cero**. Para lo «más avanzado» hay que ampliarlo **sin romper la certificación existente**:

| Modo de simulación | Estados | Retardos | Uso |
|---|---|---|---|
| **Ideal (actual)** | `0`, `1` | 0 | Tablas de verdad, lógica combinacional, ejercicios básicos. **Se mantiene idéntico** (mismos digests). |
| **Con retardo** | `0`, `1` | Retardo de propagación por puerta (fijo, o mínimo/típico/máximo) y **retardo inercial vs. de transporte** | Glitches, riesgos, camino crítico. |
| **Multivaluado (IEEE 1164 reducido)** | `0`, `1`, `X` (desconocido), `Z` (alta impedancia), `U` (sin inicializar) | Opcional | Buses con tres estados, inicialización de biestables, contención, detección de indeterminación. |

Se implementa como un **motor nuevo y opcional** al lado del certificado (mismo patrón de trazas y digests, otro *schema*: `digital-trace/2`), de modo que **las pruebas F8-Q existentes siguen pasando sin tocarlas**. La certificación del motor nuevo se hace **contra el motor ideal**: con retardo 0 y sin `X/Z`, debe dar **el mismo resultado** que el certificado (prueba de equivalencia sistemática).

### 7.2 Estímulos y bancos de prueba

- Estímulos actuales (alternante, patrón) **más**: **reloj** (periodo, ciclo de trabajo, fase, jitter opcional determinista), **contador binario** de entradas (recorre todas las combinaciones), **secuencia aleatoria sembrada** (semilla explícita, reproducible), **rampa**, **pulso único**, **vectores desde tabla** (importar CSV), **estímulo exhaustivo** automático para N ≤ 16 entradas.
- **Banco de pruebas (testbench)**: lista de vectores de entrada con **salidas esperadas** por instante; el sistema ejecuta y marca `✔`/`✘` por vector, con el primer fallo señalado sobre la forma de onda.
- **Aserciones** temporales simples: «Y debe valer 1 siempre que A=1 y B=1», «Q no cambia si CLK=0», «entre flancos de CLK, D estable ≥ tsetup».

### 7.3 Simulación interactiva

- Modo **en vivo**: el alumno pulsa interruptores y ve el estado de cada red (colores por valor: `0`, `1`, `X`, `Z`) directamente en el esquema; opcionalmente con animación de propagación.
- **Paso a paso de simulación**: siguiente evento, siguiente instante, hasta el siguiente cambio de una red, hasta el flanco, **retroceso** (la traza es determinista, así que retroceder es reponer hasta el evento anterior), puntos de parada («parar cuando Y cambie»).
- **Tabla de estado de todas las redes** en cada instante.

### 7.4 Formas de onda y analizador lógico

Ya existe analizador con disparo y ventana. Se amplía con:

- Estados `X/Z` con estilo propio, **buses** mostrados como valor hexadecimal en un solo carril (con expansión a bits).
- **Cursores** (medir tiempos y diferencias), **marcadores**, zoom/desplazamiento horizontal, **búsqueda de eventos** («siguiente flanco de Y»), **medidas** (periodo, frecuencia, ciclo de trabajo, retardo entre dos señales, anchura de pulso).
- **Comparación de dos ejecuciones** (antes/después de una modificación, o circuito ideal vs. con retardos), con las diferencias resaltadas.
- Exportar a **imagen**, **CSV**, **VCD** (formato estándar de ondas, abrible en GTKWave).
- **Propiedad de `ui/waveform.py`.** Es el visor de carriles **lógicos** y sigue siendo de este laboratorio. Las señales analógicas (`WaveformPlot` de `CIRCUITS_LAB.md` §8.8) y las gráficas de señales (`stem`, dB, plano z) se dibujan en el **núcleo de gráficas compartido** (`ui/plot/`, `SIGNALS_LAB.md` §3.2); cursores, zoom y medidas genéricos se reutilizan de allí y no se reimplementan aquí (§23.4).

### 7.5 Análisis de temporización

- **Camino crítico** estático: retardo máximo de entrada a salida, mostrado sobre el esquema.
- **Riesgos (hazards)**: detección **estática 1/0** y **dinámica** por análisis lógico y por simulación con retardos; sugerencia de **término de consenso** para eliminarlos (enlace con §4.3 consenso).
- **Glitches** visibles en la forma de onda con marca.
- Para circuitos secuenciales: **frecuencia máxima**, **tiempos de preparación/mantenimiento** (setup/hold), **violaciones** señaladas, **skew de reloj**; modelo de **metaestabilidad** (informativo).
- **Consumo dinámico estimado** (nº de conmutaciones × capacidad configurable) como métrica didáctica.

### 7.6 Comprobación de propiedades

Bucles de oscilación (anillo de inversores), estados no alcanzables, **puntos muertos** en máquinas de estados, **entradas que nunca influyen** (observabilidad), **redes constantes** (controlabilidad) — informes de **testabilidad** (cobertura de fallos «stuck-at» con generación de vectores de prueba, ATPG sencillo tipo D-algoritmo o por SAT).

---

## 8. Lógica secuencial

Sin esto no se cubre la mitad del temario.

### 8.1 Elementos de memoria

Latch SR (NOR y NAND), **latch D**, **flip-flops** D, T, JK, SR, con **entradas asíncronas** (preset/clear), sensibles a **flanco ascendente o descendente**, y **maestro-esclavo** construido desde puertas (para ver el funcionamiento interno). **Tablas características y de excitación** mostradas y usadas por la síntesis.

### 8.2 Bloques secuenciales

Registros (paralelo, con habilitación, con carga), **registros de desplazamiento** (SISO/SIPO/PISO/PIPO, universal), **contadores** (asíncrono/síncrono, ascendente/descendente/módulo N, BCD, Johnson, anillo), **divisores de frecuencia**, **LFSR** (con polinomio elegido, para pseudoaleatorios y CRC), **memorias** (ROM, RAM síncrona/asíncrona, FIFO simple), **detector de flancos**, **antirrebote**.

### 8.3 Máquinas de estados finitos (FSM)

- **Editor de diagramas de estados** (nodos = estados, arcos con condición/salida), modos **Moore** y **Mealy**.
- **Tabla de transición de estados** y **tabla de salidas** generadas automáticamente y **editables**.
- **Minimización de estados** (tabla de implicación / particiones) con explicación paso a paso.
- **Asignación de estados**: binaria, Gray, *one-hot*, con criterios de coste.
- **Síntesis**: elegir tipo de biestable (D/T/JK/SR), calcular las **ecuaciones de excitación** (con Karnaugh y álgebra, reutilizando §4–5) y **generar el circuito** dibujado.
- **Simulación de la FSM** en el propio diagrama (estado activo resaltado) y en el circuito sintetizado, con **comprobación de equivalencia** entre ambos.
- **Detección de problemas**: estados inalcanzables, no determinismo, transiciones incompletas, estados sin salida, **estados ilegales** en la asignación binaria y su tratamiento de recuperación.
- **Plantillas**: detector de secuencia (con y sin solapamiento), semáforo, control de ascensor, máquina expendedora, protocolo simple.

### 8.4 Análisis secuencial

Diagramas de **temporización** (cronogramas) generados automáticamente para una secuencia de entradas, comprobación **setup/hold** y **dominio de reloj único** (aviso si se detectan varios relojes: cruce de dominios).

---

## 9. Biblioteca de componentes

### 9.1 Básicos

Puertas NOT, AND, OR, XOR, NAND, NOR, XNOR (ya), **buffer**, **buffer de tres estados** (con `Z`), **puertas de N entradas**, **entradas invertidas**, **Schmitt** (didáctico).

### 9.2 Combinacionales MSI

Multiplexores (2:1, 4:1, 8:1, … parametrizable), demultiplexores, **decodificadores** (2→4, 3→8, con habilitación; BCD→7 segmentos), **codificadores** y **de prioridad**, **comparadores** de magnitud, **generadores y detectores de paridad**, **conversores de código** (binario↔Gray, BCD↔binario, exceso 3), **barrel shifter**.

### 9.3 Aritméticos

Semisumador, **sumador completo**, sumador **ripple-carry**, **carry-lookahead** (con explicación de generar/propagar), **carry-select**, restador, **sumador/restador** con complemento a 2 y bandera de **desbordamiento**, **multiplicador** (matriz y **Booth**), **divisor** (restaurador), **ALU** de N bits con banderas (cero, negativo, acarreo, desbordamiento) y selección de operación.

### 9.4 Memoria y programables

ROM/LUT (relleno desde tabla de verdad), **PLA** y **PAL** (matriz AND-OR mostrada gráficamente y programada desde la función), RAM, registro de archivos. **Ejemplo FPGA-lite**: LUT de 4 entradas + biestable como «celda lógica».

### 9.5 Salida/visualización

LED, barra de LEDs, **display de 7 segmentos** (con decodificador), display hexadecimal, sonda con valor decimal/hex/binario, **matriz de LEDs** simple.

### 9.6 Definición y ampliación

Cada componente se describe **declarativamente** (nombre, pines, anchura, función o subcircuito interno, símbolo, ayuda). Añadir uno nuevo no exige tocar el motor. Los componentes «de libro» se construyen **a partir de puertas** (verificados por tabla) y se pueden **abrir** para ver su interior.

---

## 10. Calculadoras y herramientas numéricas

Todas: entrada con validación estricta, resultado con **pasos** (cómo se llega), **exactitud** (enteros/`Decimal`/`Fraction`, nunca `float` salvo IEEE 754 explícito), copiar/exportar, y **verificación** por método alternativo.

| Calculadora | Detalle |
|---|---|
| **Conversor de bases** | 2/8/10/16 y **base arbitraria 2–36**, con partes **fraccionarias**, división sucesiva y multiplicación sucesiva **mostradas paso a paso**; agrupación en 3/4 bits. |
| **Aritmética en cualquier base** | Suma, resta, multiplicación y división con acarreos mostrados. |
| **Representación de enteros** | Signo-magnitud, **complemento a 1**, **complemento a 2**, **exceso K**; rango, conversión ida y vuelta, **extensión de signo**, y detección de **desbordamiento** en operaciones con explicación. |
| **Suma/resta en C2** | Con acarreos bit a bit, banderas C/V/N/Z y regla del desbordamiento. |
| **Multiplicación** | Suma-desplazamiento y **algoritmo de Booth** (radix-2 y radix-4) paso a paso; división restauradora / no restauradora. |
| **Código Gray** | Binario↔Gray, con la regla XOR de bits adyacentes mostrada; Gray reflejado y n-bit. |
| **BCD** | BCD natural/Aiken/exceso 3/2-de-5, suma BCD con **corrección +6** paso a paso. |
| **Coma fija** | Formato Qm.n, saturación/redondeo/truncado, errores de cuantización. |
| **IEEE 754** | half/single/double (y **bfloat16**): descomposición en signo/exponente/mantisa, casos especiales (∞, NaN, subnormales), conversión decimal↔binario **exacta con `Fraction`**, suma/multiplicación paso a paso con **redondeo** (modos) y **error relativo**. |
| **Paridad** | Par/impar, generación y comprobación, **paridad bidimensional**. |
| **Códigos detectores/correctores** | **Hamming(7,4)** y extendido (SECDED): codificar, introducir un error, **calcular el síndrome** y corregir, con las ecuaciones de paridad; **distancia de Hamming**; **CRC** (polinomio elegido, división módulo 2 paso a paso, comprobación); **checksum**. |
| **Códigos de línea** | NRZ, RZ, Manchester, Manchester diferencial, AMI (visualizados como formas de onda). |
| **Códigos ASCII/Unicode** | Texto ↔ binario/hex/decimal, con tabla y bytes UTF-8. |
| **Tamaños y rangos** | Rango de N bits con/sin signo, nº de bits necesarios para un valor, capacidad de memoria. |
| **Lógica proposicional** | Evaluador de fórmulas (validez, tautología, contradicción, satisfacibilidad), tabla de verdad de una **fórmula proposicional** (misma máquina que el álgebra de Boole, con notación lógica). |
| **Cálculo de costes y retardos** | Número de puertas/literales/transistores CMOS estimados; **retardo** de un camino con tiempos por puerta configurables. |
| **Temporización de reloj** | Frecuencia ↔ periodo, ciclo de trabajo, **frecuencia máxima** dado un camino crítico + setup/hold, **anchura de bus** vs. ancho de banda. |
| **Dimensionado** | Nº de biestables para N estados, nº de líneas de dirección para una memoria, tamaño de contador para un módulo. |
| **Convertidor de expresión** | SOP↔POS, `Σm`↔`ΠM`, NAND/NOR, con pasos. |

**Reparto con `MATH_LAB.md`.** Esta tabla no se recorta, pero la implementación se reparte para no escribir dos veces la misma matemática (detalle y regla de dependencia en §23.3): la conversión entre bases y la aritmética por columnas son de `MATH_LAB` §4.0; la **lógica proposicional** (misma máquina que el álgebra de §4) comparte `BoolExpr` y no incluye cuantificadores (`MATH_LAB` §4.8); **CRC, Hamming y paridad** se calculan con el álgebra sobre GF(2) de `MATH_LAB` §4.9 y §4.10, y aquí aportan la **vista de hardware** (LFSR, árboles XOR, cronograma) que además sirve de segundo camino; la fórmula `SQNR = 6,02·b + 1,76 dB` es la calculadora de `MATH_LAB` §8.2 I. Son propias de este laboratorio: complemento a 1, a 2 y exceso con banderas, Gray, BCD, Booth, división, coma fija, IEEE 754, ASCII/UTF-8, códigos de línea, costes, retardos y temporización.

Cada calculadora se implementa en `domain/engineering/digital/calc/` (ruta actual; ver §23.5) como funciones puras y se expone en una pestaña común con **historial** de operaciones y opción de **enviar el resultado al circuito o al álgebra** (p. ej. un número → patrón de estímulo).

---

## 11. Comprobación y verificación de resultados

### 11.1 Tipos de comprobación

| Comprobación | Pregunta que responde | Método |
|---|---|---|
| **Reproducibilidad** (ya existe) | ¿Sale lo mismo si lo repito? | Repetición de traza y digest |
| **Equivalencia circuito ↔ expresión** | ¿El circuito dibujado hace la función esperada? | Tabla exhaustiva; BDD/SAT si son muchas variables |
| **Equivalencia circuito ↔ circuito** | ¿Mi versión reducida hace lo mismo que la original? | Miter (XOR de salidas) + SAT/BDD |
| **Corrección frente a especificación** | ¿Cumple mi tabla/enunciado? | Comparación con tabla dada, con contraejemplos |
| **Aserciones y banco de pruebas** | ¿Cumple estas propiedades en el tiempo? | Simulación con vectores |
| **Comprobación de la reducción** | ¿La expresión reducida equivale a la original? | Tabla/BDD (obligatoria antes de mostrar una demostración) |
| **Mínimo** | ¿Es realmente mínima? | Quine-McCluskey + Petrick |
| **Propiedades estructurales** | Bucles, redundancias, constantes | Análisis del grafo |

### 11.2 Contraejemplos

Cuando algo no coincide, el sistema entrega un **contraejemplo mínimo** (asignación de entradas concreta), lo **carga en el circuito** y muestra **dónde divergen** ambos lados, resaltando en el esquema la primera red que difiere.

### 11.3 Oráculos independientes (como `ngspice` en analógico)

El proyecto ya usa `ngspice` como **oráculo externo opcional** para el laboratorio analógico. Igual aquí:

- **Oráculo interno independiente**: una segunda implementación de la evaluación (evaluación de la expresión por recursión frente a simulación por eventos) y cruce sistemático en las pruebas.
- **Oráculo externo opcional**: **ABC/Espresso** para minimización y equivalencia sobre BLIF/PLA. *(Icarus y Yosys descartados: el proyecto no usa HDL, ver §22.1.)* Detección automática del binario (misma lógica de descubrimiento que `infrastructure/ngspice.py`), con la interfaz funcionando igual si no están instalados (el botón queda desactivado con explicación).
- El resultado del oráculo se muestra junto al del motor con veredicto **«coinciden» / «difieren»**; en caso de diferencia se marca en **ERROR** y se guarda el caso.

### 11.4 Sellos de verificación

Cada resultado importante lleva un sello visible: `✔ Verificado (tabla 16/16)`, `✔ Equivalente (BDD)`, `⚠ Reducida, no certificada como mínima`, `✘ Difiere en la combinación 0110`. Mismo lenguaje visual que la «tarjeta de conservación» del laboratorio analógico.

**Correspondencia con los tres sellos del proyecto** (`MATH_LAB.md` §5.9 y §8.1, citados por `SIGNALS_LAB.md` y `CIRCUITS_LAB.md`): `✔ Verificado` y `✔ Equivalente` son `✔ Verificado` con su método entre paréntesis; `✘ Difiere` es `✘ Discrepa`; `⚠ Reducida, no certificada como mínima` es un **calificativo** de un `✔ Verificado` (la equivalencia está comprobada; lo no certificado es el mínimo), no un cuarto sello. `⚠ Solo numérico` no se usa aquí porque la verificación digital es exacta. Las trazas se emiten como trazas E0 y, donde otro laboratorio las incruste, con el formato serializable de `MATH_LAB.md` §5.9.

---

## 12. Explicación paso a paso

### 12.1 Fuente de verdad

La explicación **se genera desde la traza del motor**, no desde texto libre. Se integra con el sistema de trazas de ejecución existente (`domain/execution/digital.py`, `application/explain_service.py`, esquema E0), añadiendo operaciones nuevas.

Operaciones explicables:

| Operación | Contenido de la explicación |
|---|---|
| `digital.boolean-simplify` | Cada ley aplicada (§4.6) |
| `digital.truth-table` | Cómo se evalúa cada fila; qué subexpresión vale qué |
| `digital.canonical` | De la tabla a `Σm` y a la función |
| `digital.kmap` | Cada grupo y la variable que se elimina |
| `digital.quine-mccluskey` | Tabulación, primos, cobertura, Petrick |
| `digital.simulate` (existente, ampliada) | Por qué cambió cada red en cada instante |
| `digital.fsm-synthesis` | Del diagrama a las ecuaciones |
| `digital.calc.*` | Cada calculadora, paso a paso |

### 12.2 Niveles de detalle

Tres niveles seleccionables: **Resumen** (qué y por qué en una línea), **Paso a paso** (cada ley/evento) y **Detallado** (con la justificación formal y las sustituciones de metavariables). Un interruptor **«Muéstrame por qué»** en cualquier resultado abre la explicación de ese resultado concreto.

### 12.3 Explicación sobre el esquema

Al seleccionar una transición o un paso, el esquema **resalta el camino causal**: qué entradas cambiaron, qué puertas evaluaron y por qué la salida tomó ese valor («NAND: entradas 1,1 → salida 0»). En álgebra, el subtérmino afectado se resalta en la expresión y, si hay circuito asociado, en el propio circuito.

### 12.4 Modos didácticos

- **Reproducir** la demostración (animada, con velocidad ajustable).
- **Oculta el resultado** (modo estudio): el alumno predice el siguiente paso/valor y el sistema lo corrige.
- **Exportar la demostración** a Markdown/LaTeX/PDF para entregar.

### 12.5 Garantía de honestidad

El texto explicativo se compone con **plantillas** rellenadas con datos de la traza; **no hay modelo generativo** en el camino de una explicación. Si en el futuro se usa un LLM para redactar mejor (como ya hace el tutor), pasará por el mismo validador («validado y comprobado con el corrector certificado; el modelo nunca califica»).

---

## 13. Importar desde imagen (visión / OCR)

### 13.1 Qué se quiere

El usuario **sube una imagen** (captura, foto de cuaderno, PDF de un ejercicio, dibujo) y el sistema **reconstruye el circuito** en el editor, o bien **extrae una tabla de verdad o una expresión**.

### 13.2 Por qué «OCR» no basta

OCR reconoce **texto**. Un esquema tiene **símbolos y cables**. Hace falta un pipeline de **reconocimiento de diagramas**:

```
Imagen → preprocesado → segmentación (símbolos / cables / texto)
       → clasificación de símbolos (tipo de puerta y orientación)
       → OCR de etiquetas (nombres de señales)
       → grafo de conectividad (qué pin conecta con qué pin)
       → DigitalDesign (borrador) → REVISIÓN HUMANA → editor
```

### 13.3 Estrategias, de más a menos fiable

| Opción | Cómo | Ventajas | Inconvenientes |
|---|---|---|---|
| **A. Modelo de visión (LLM multimodal)** | Se envía la imagen y se pide el `digital-design/1` (JSON con esquema estricto). | Mejor con fotos y dibujos a mano; entiende contexto. | Requiere red y clave de API; **envía la imagen a un servicio externo**; puede equivocarse. |
| **B. Visión clásica + detector entrenado** | OpenCV (binarizado, contornos, Hough para líneas) + detector de símbolos (p. ej. YOLO/ONNX) + Tesseract para etiquetas. | Local y privado. | Hay que **entrenar y mantener** el detector; frágil con dibujos sucios. |
| **C. Híbrido** | Detección local de cables y símbolos, y el modelo de visión solo para dudas, o Tesseract para etiquetas. | Equilibrio. | Complejidad. |
| **D. Solo texto** | OCR de **expresiones** y **tablas** (fórmulas impresas, tablas de verdad) → álgebra/tabla. | Sencillo y muy útil. | No cubre esquemas. |
| **E. Circuito dibujado por el propio sistema** | Reconocimiento de imágenes exportadas por esta misma app (marcas embebidas). | 100 % fiable. | Solo para round-trip. |

**Decisión adoptada (D1):** **todo el reconocimiento es local**. No se envían imágenes a servicios externos; la opción A queda **descartada**. Se construye el camino **C híbrido local**: **OpenCV** para la parte geométrica (limpieza, enderezado, cables, recorte de símbolos) y **Ollama con un modelo de visión** para clasificar símbolos y etiquetas. Orden de entrega: **D (expresiones y tablas)** primero, después esquemas con el pipeline híbrido, siempre con revisión humana obligatoria (§13.4).

#### 13.3.1 Pipeline híbrido local (OpenCV + Ollama)

1. **OpenCV** (preprocesado): escala de grises, binarizado adaptativo, enderezado por perspectiva, eliminación de ruido y de rejilla de fondo.
2. **OpenCV** (geometría): detección de segmentos de cable (Hough / esqueletización), uniones y esquinas; agrupación de componentes conexos para **aislar cada símbolo** en un recorte.
3. **Ollama (visión)**, una llamada **por recorte** y no por esquema completo: «¿qué puerta lógica es esto y cuántas entradas tiene?» con salida en JSON de esquema estricto. Es más fiable y más barato con modelos pequeños.
4. **Ollama / Tesseract** para las etiquetas de señales (A, B, S, «AND»…), también por recorte.
5. **Conectividad determinista** (sin modelo): los cables detectados por OpenCV se asocian a los pines geométricamente. El modelo **no decide conexiones**.
6. **Validación**: reglas de diseño (§6.4) y coherencia; lo dudoso se marca en ámbar.
7. **Revisión humana** en el editor antes de simular.

#### 13.3.2 Perfiles de hardware (equipos del usuario)

| Equipo | VRAM | RAM | Perfil |
|---|---|---|---|
| Sobremesa con **RTX 2060** | 6 GB (verificar con `nvidia-smi`) | 16 GB | **Ligero**: modelos de visión de hasta ~4B parámetros cuantizados a 4 bits, con holgura. Modelos de ~7–8B solo si caben sin desbordar a CPU. |
| Portátil con **RTX 4060** | 8 GB | 16 GB | **Estándar**: modelos de ~7–8B cuantizados a 4 bits con comodidad. |

Reglas de diseño derivadas:
- **Se diseña para el equipo más justo (6 GB).** Lo que funcione en la 2060 funciona en la 4060.
- El **modelo de visión se elige por equipo** en ajustes (`ollama_vision_model`), con perfiles «ligero» y «estándar»; el proyecto compartido no lo fija.
- Estimación orientativa de memoria: ~0,6 GB por cada 1 000 millones de parámetros a 4 bits, más margen para la imagen. Si el modelo no cabe en VRAM, Ollama reparte capas en CPU y va **mucho más lento**; la app **avisa del tiempo estimado**.
- **Imágenes reescaladas** antes de enviarse; **una sola llamada a la vez**, con cancelación y progreso; **respaldo en CPU** si la GPU no está disponible.
- **No se fija ningún modelo concreto en el diseño.** Se prueban 2–3 candidatos pequeños (familias con visión disponibles en Ollama) contra el **conjunto de evaluación** (§13.5) y se elige el que mida mejor. La oferta de modelos cambia deprisa; la medición decide.
- La integración actual con Ollama (`engines/ai.py`, `infrastructure/llm.py`, host `http://127.0.0.1:11434`, modelo autodetectado) **solo envía texto**: habrá que ampliarla para enviar imágenes (campo `images` de la API de Ollama).
- **Estado en el momento de redactar:** Ollama **no está instalado** en el equipo de trabajo. Instalarlo y descargar modelos requiere acción expresa del usuario.

#### 13.3.3 Pipeline compartido

`CIRCUITS_LAB.md` §7.1 importará esquemas analógicos por imagen con **este mismo pipeline** (OpenCV + modelo local), y `SIGNALS_LAB.md` D12 reevaluará leer gráficas de examen por imagen **tras DL-11**. Por eso la parte genérica (preprocesado, segmentación, cliente de Ollama con el campo `images`, perfiles de hardware, cancelación y progreso, revisión humana) se construye en `infrastructure/vision.py` y `application/` sin conocer puertas; el clasificador de símbolos y las reglas de revisión de cada laboratorio son clientes. El ajuste `ollama_vision_model` es único para la aplicación (§23.4).

### 13.4 Flujo de usuario

1. **Subir** imagen / PDF / pegar del portapapeles / arrastrar.
2. **Recorte** y **enderezado** (perspectiva), ajuste de contraste.
3. El sistema muestra el **borrador** superpuesto a la imagen: cada símbolo detectado con su etiqueta, cada cable en color, y **nivel de confianza por elemento**.
4. El alumno **corrige** (cambiar tipo de puerta, reconectar un cable, renombrar) directamente sobre la superposición.
5. **Comprobaciones automáticas** (DRC §6.4 + coherencia): pines huérfanos, cables ambiguos, etiquetas duplicadas; se listan como pendientes.
6. **Confirmar** → se carga en el editor. **No se simula nada hasta confirmar.**
7. Opcional: **comparar con la expresión/tabla del enunciado** si se proporciona, para detectar errores de lectura (si no coinciden, se sugiere dónde mirar).

### 13.5 Reglas de calidad

- Nunca se presenta el resultado como definitivo: se etiqueta **«Reconocido automáticamente — revisa»**.
- Cada elemento lleva **confianza**; por debajo de un umbral se marca en ámbar y se pide confirmación.
- Se guarda la **imagen original** junto al diseño (con permiso) para poder revisar.
- **Conjunto de evaluación** propio (§18): imágenes de circuitos con su verdad conocida, con **métrica de exactitud** por tipo de puerta y por conexión; el reconocimiento no se da por «funcional» hasta superar un umbral acordado.

### 13.6 Otras entradas por imagen

- **Tabla de verdad** desde foto → tabla editable.
- **Expresión booleana** manuscrita o impresa (incluido con barras encima para la negación) → `BoolExpr`.
- **Mapa de Karnaugh** desde foto → celdas y agrupaciones reconocidas.
- **Diagrama de estados** desde foto (mejor esfuerzo).
- **Cronograma/forma de onda** desde foto → estímulos o esperados de un banco de pruebas.

### 13.7 Ejecución y dependencias

- Todo el reconocimiento va en **hilo aparte** con barra de progreso y **cancelación**.
- Dependencias **opcionales** (`opencv-python-headless`, Ollama con un modelo de visión y, para etiquetas, `pytesseract`+binario Tesseract, y `onnxruntime` si se entrena un detector propio); si no están, la función explica qué instalar y el resto del laboratorio sigue funcionando.
- **Sin ninguna dependencia de servicios externos** (decisión D1): el reconocimiento es 100 % local.

---

## 14. Importación y exportación

### 14.1 Formatos

| Formato | Importar | Exportar | Notas |
|---|---|---|---|
| `digital-design/1` (JSON propio) | ✔ | ✔ | Ya existe. Ampliado (buses, jerarquía, símbolos, notas). |
| `digital-trace/1` | ✔ | ✔ | Ya existe. |
| **BLIF** | ✔ | ✔ | Estándar de minimizadores (ABC/SIS). |
| **Tabla de verdad CSV** | ✔ | ✔ | — |
| **PLA (Espresso)** | ✔ | ✔ | — |
| **VCD** (formas de onda) | ○ | ✔ | Abrible en GTKWave. |
| **PNG / SVG / PDF** (esquema) | — | ✔ | Vectorial preferido. |
| **Markdown / LaTeX / PDF** (demostración, tabla, Karnaugh, informe) | — | ✔ | Para entregar prácticas. |
| **Imagen → diseño** | ✔ | — | §13. |
| **Logisim Evolution (`.circ`)** | ○ | ○ | Ampliación deseable por su popularidad docente. |

Leyenda: ✔ incluido · ○ fase posterior.

### 14.2 Sin HDL

**Decisión D11:** no se importa ni exporta VHDL/Verilog ni se simula HDL; el alumno usa Quartus fuera de la aplicación. Round-trip probado solo con los formatos que quedan: `diseño → BLIF → importar → diseño'` con `diseño ≡ diseño'`.

### 14.3 Informes

Generador de **informe de práctica** (una página o varias) con: enunciado, tabla de verdad, función canónica, **pasos del álgebra**, Karnaugh, circuito (imagen), formas de onda, resultados de comprobación y sellos. Plantillas en español, exportables a **PDF/DOCX/Markdown** (reutilizando el generador de documentos existente en `documents/`).

---

## 15. Persistencia, proyectos y Ejercicios

### 15.1 Proyectos

- Los diseños digitales se guardan **dentro de los proyectos de ingeniería** ya existentes (como los circuitos analógicos), con **versionado ligero** (historial de guardados con nota) y **recuperación** tras cierre inesperado (autoguardado).
- Un proyecto puede contener: diseños, expresiones, bancos de pruebas, FSMs, informes y calculadoras guardadas.
- **Duplicar, renombrar, mover, comparar dos versiones** (diferencia visual entre dos diseños).

### 15.2 Conexión con Aprender / Practicar

- Enlace con **asignaturas** y **temas** (el diseño se asocia a una asignatura).
- Los ejercicios de lógica digital del banco de preguntas se pueden **abrir en el laboratorio** con el enunciado y el objetivo cargados (p. ej. «reduce esta función»).
- **Correlación con dominio/maestría**: resolver ejercicios con verificación actualiza el dominio, siguiendo el mismo mecanismo del corrector certificado.

### 15.3 Corrección automática de ejercicios

Nuevo tipo de pregunta **«circuito digital»** en el banco: el alumno entrega un circuito o una expresión; el corrector **compara por equivalencia** con la solución y con restricciones (máximo de puertas, solo NAND, fan-in ≤ 3, sin bucles) y devuelve **veredicto + contraejemplo + pistas** (usando el modo asistido §4.5). Como el resto del corrector: determinista, con la misma política de «el modelo nunca califica».

### 15.4 Generador de ejercicios

Generación **sembrada y reproducible** de ejercicios con solución conocida (reducir una función aleatoria de N variables, diseñar un contador módulo M, etc.), con **dificultad** ajustable y la solución paso a paso incluida.

---

## 16. Accesibilidad, localización y rendimiento

### 16.1 Accesibilidad

- El lienzo es operable **solo con teclado** (§6.5) y tiene **nombres accesibles** y **descripción textual** del circuito (lista de elementos y conexiones) para lectores de pantalla («Puerta AND `and1`: entrada 0 desde `A`, entrada 1 desde `B`; salida a `or1` pin 0»).
- **Colores** con contraste suficiente y **no solo color**: los valores `0/1/X/Z` también se distinguen por **forma/patrón/etiqueta**; modo **alto contraste** y **daltonismo**.
- Tamaños de fuente **escalables**; respeta la reducción de movimiento del sistema (ya existe `motion`).
- Las tablas de verdad y los pasos son **texto real navegable**, no solo imagen.

### 16.2 Localización

- Toda la UI en español (con las claves en un único sitio), términos consistentes: *puerta, biestable, flanco, minitérmino, implicante primo, retardo de propagación…*.
- Números y separadores según configuración regional en la presentación (nunca en el guardado).
- Preparado para **añadir inglés** sin tocar la lógica (cadenas centralizadas).

### 16.3 Rendimiento (objetivos medibles)

| Operación | Objetivo |
|---|---|
| Tabla de verdad de 16 variables | < 1 s |
| Quine-McCluskey de 8 variables | < 1 s; 10 variables < 10 s (con progreso y cancelación) |
| Simulación de 100 000 eventos | < 2 s |
| Dibujo del lienzo con 5 000 elementos | ≥ 30 fps al desplazar |
| Reconocimiento de imagen (local) | < 10 s en portátil medio; con barra de progreso |
| Carga de un diseño de 5 000 elementos | < 1 s |

Todo lo que pueda tardar se ejecuta en **segundo plano** con **cancelación** y **límite de recursos** (tiempo, memoria, eventos), con mensajes claros al alcanzarlos.

---

## 17. Seguridad y privacidad

- **Entrada no fiable**: todo texto (expresiones, JSON, BLIF, PLA, CSV) se **valida con límites** (longitud, profundidad, nº de nodos) antes de procesarse; el lector de expresiones es un analizador propio, **nunca `eval`**.
- **Ficheros**: tope de tamaño (ya hay `MAX_TRACE_FILE_BYTES` como patrón), rechazo de esquemas desconocidos con mensaje seguro (sin *tracebacks* ni rutas: se reutiliza el conversor único `to_ui_error`).
- **Exportación**: nombres de fichero saneados; nunca se sobrescribe sin confirmar.
- **Imágenes**: el reconocimiento es **solo local** (decisión D1). Las imágenes no salen del equipo. Ollama se usa únicamente en `127.0.0.1`; si el usuario configura otro host, la app **avisa** de que las imágenes viajarían por la red. No se guardan claves de servicios de visión porque no se usan.
- **Oráculos externos** (abc/espresso): se ejecutan con lista blanca de argumentos, **sin shell**, con tiempo máximo y en directorio temporal aislado; el fichero generado se trata como dato, no como orden.
- **Sin telemetría** del contenido de los diseños.
- Los diseños de un alumno no se comparten sin acción explícita.

---

## 18. Plan de pruebas y criterios de aceptación

### 18.1 Estrategia

Se sigue la convención del repositorio: pruebas por fase (`tests/test_dl*_…py`), sin dependencias pesadas en las unitarias, y **pruebas de UI** con `pytest-qt` en modo offscreen (lentas: ~6 minutos la parte de UI actual, por lo que las nuevas pruebas de dominio deben poder ejecutarse **sin Qt**).

| Nivel | Qué se prueba |
|---|---|
| **Unitarias de dominio** | Cada ley del catálogo (patrón, condición, equivalencia), lector de expresiones (válidas e inválidas), tabla de verdad, canónicas, Karnaugh, QM/Petrick, BDD, SAT, calculadoras. |
| **Propiedades (aleatorias con semilla)** | Para expresiones aleatorias: `simplify(e) ≡ e`; `parse(print(e)) = e`; `canónica(tabla(e)) ≡ e`; toda traza verifica paso a paso; dualidad de leyes; QM da un mínimo ≤ que el álgebra. |
| **Contra oráculos** | Mínimos de QM frente a ABC/Espresso si están; **oráculo interno** siempre. |
| **Doradas (golden)** | Ejemplos de libro con demostración completa, incluido el de §4.7 y el semisumador, sumador completo, decodificador, mux; el resultado (forma final, nº de literales, nº de pasos) se fija. |
| **Motor de simulación** | Modo ideal nuevo ≡ motor certificado (mismos digests); retardo cero + sin `X/Z` reproduce el certificado; casos de glitch y de bucle. |
| **Secuencial** | Tablas de excitación, contadores (secuencia completa), FSM (detector de secuencias), minimización con resultado conocido, equivalencia FSM↔circuito. |
| **Round-trip** | Expresión↔tabla↔circuito↔BLIF, todos verificados por equivalencia. |
| **Reconocimiento de imagen** | Conjunto de evaluación propio; métrica de exactitud; **prueba de no regresión** con umbral. |
| **UI** | Gestos del editor (colocar, cablear, deshacer/rehacer, copiar/pegar, selección múltiple, zoom), pestañas, resaltado de pasos, accesibilidad (nombres accesibles), exportaciones. |
| **Seguridad** | Entradas hostiles (expresiones enormes, JSON profundo, imágenes corruptas, BLIF malicioso) → error seguro, sin colgarse ni consumir memoria sin límite. |
| **Rendimiento** | Pruebas de tiempo con tolerancia (marcadas para no fallar en máquinas lentas). |

### 18.2 Criterios de aceptación globales

1. Cualquier expresión de hasta 6 variables se reduce con **pasos verificados**, y el resultado **coincide con QM/Karnaugh** (o se declara explícitamente que el álgebra no alcanza el mínimo y se muestra cómo seguir).
2. Ninguna demostración se muestra sin **haber sido comprobada** como equivalente.
3. Un circuito de **N puertas** (N hasta el límite configurado) se puede dibujar, simular, comprobar frente a una expresión y explicar.
4. La tabla de verdad se genera desde expresión **y** desde circuito, y ambas **coinciden**.
5. El flujo **enunciado → tabla → canónica → reducción algebraica → circuito → simulación → verificación** se completa en la UI sin salir de la página.
6. Todos los resultados son **deterministas** y llevan **digest** reproducible.
7. Las calculadoras dan **resultados exactos** y **verificados por método alterno**.
8. **Ninguna** prueba F8-Q existente cambia de resultado. La garantía de «motor certificado intacto» se comprueba con el **manifiesto de hashes SHA-256** de `CIRCUITS_LAB.md` CI-R.2 (que sustituye a las comparaciones `git diff 0cf3554` y funciona donde esté el paquete), no con rutas físicas.
9. El reconocimiento de imagen **nunca simula sin confirmación humana** y publica su **exactitud medida**.
10. **Accesibilidad**: todo el flujo principal se completa **solo con teclado**.
11. Toda la interfaz está en **español**, sin cadenas a medio traducir (prueba automática que busca literales en inglés en las etiquetas visibles).
12. La suite completa pasa (con el caso conocido de fin de línea Windows del fichero dorado E0 resuelto por normalización en la comparación; el arreglo es **único** y también figura en `CIRCUITS_LAB.md` §21 punto 16: lo hace la primera fase que toque ese dorado, DL-0 o CI-0, y la otra no lo repite).

---

## 19. Fases de entrega

Cada fase es **entregable y demostrable por sí sola**, con pruebas y documentación. Las estimaciones son orientativas y de esfuerzo relativo (S ≈ días, M ≈ 1–2 semanas, L ≈ 3–5 semanas, XL > 5 semanas).

| Fase | Contenido | Depende de | Esfuerzo |
|---|---|---|---|
| **DL-0** Cimientos | Estructura de módulos, `BoolExpr`, lector de expresiones con errores en español, tabla de verdad, minitérminos/maxitérminos, canónicas, DRC básico. | — | M |
| **DL-1** Álgebra con pasos | Catálogo de leyes, motor de reescritura con traza, estrategias, verificación de cada paso, modo asistido, vista de pasos en UI. **Cubre R6 y R7.** | DL-0 | L |
| **DL-2** Karnaugh, QM y síntesis | Mapas 2–6 variables, Quine-McCluskey + Petrick, multisalida, `X`, síntesis a puertas, NAND/NOR, comparación con álgebra. | DL-1 | L |
| **DL-3** Editor avanzado | Deshacer/rehacer, zoom, selección múltiple, copiar/pegar, buses, etiquetas, salidas, símbolos ANSI/IEC, DRC en vivo, galería. **Cubre R1.** | DL-0 | L |
| **DL-4** Comprobación | Equivalencia circuito↔expresión/circuito↔circuito (tabla + BDD + SAT), contraejemplos, banco de pruebas, aserciones, sellos. **Cubre R3.** | DL-0 | M |
| **DL-5** Motor ampliado | Modo con retardos, valores `X/Z/U`, buffers de tres estados, `digital-trace/2`, equivalencia con el motor certificado, glitches y riesgos. **Cubre R2 avanzado.** | DL-0 | XL |
| **DL-6** Calculadoras | Todas las de §10 con pasos y verificación cruzada; pestaña y historial. **Cubre R8.** | DL-0 | L |
| **DL-7** Paso a paso general | Integración con trazas E0, resaltado causal sobre el esquema, simulación con retroceso, modo estudio. **Cubre R4.** | DL-1, DL-5 | L |
| **DL-8** Secuencial | Latches, flip-flops, registros, contadores, LFSR, memorias, FSM (editor, tabla, minimización, síntesis, equivalencia). | DL-2, DL-5 | XL |
| **DL-9** Biblioteca MSI y aritmética | Mux, decodificadores, comparadores, sumadores (ripple, lookahead), ALU, PLA/PAL, 7 segmentos; subcircuitos. | DL-3, DL-8 | L |
| **DL-10** Importar/exportar | BLIF, CSV, PLA, VCD, PNG/SVG/PDF, informes; oráculos externos opcionales. | DL-4 | L |
| **DL-11** Imagen → circuito | Expresiones/tablas por OCR (D), después esquemas con el pipeline híbrido local (C, decisión D1; la opción A está descartada) y revisión obligatoria; conjunto de evaluación; pipeline genérico compartido (§13.3.3). **Cubre R5.** | DL-3, DL-10 | XL |
| **DL-12** Ejercicios y persistencia | Proyectos, versionado, autoguardado, tipo de pregunta «circuito digital», corrector por equivalencia, generador sembrado, enlace con maestría. | DL-4, DL-1 | L |
| **DL-13** Pulido y certificación | Accesibilidad completa, rendimiento, seguridad, localización, documentación de usuario, certificación final. | Todas | M |

**Dependencias externas** (fases de otros laboratorios; detalle en §23.7): DL-0 sitúa su código nuevo según §23.5 y no empieza a mover ficheros antes de CI-R.0; DL-1 y DL-6 usan el motor de pasos y el contrato de `MATH_LAB.md` §5.9 (**ML-12**); DL-3 y CI-4 comparten el núcleo de lienzo (§6.1, §23.4); DL-6 delega GF(2), CRC y Hamming en **ML-17**; DL-11 aporta el pipeline que usará `CIRCUITS_LAB.md` §7.1.

**Orden recomendado:** DL-0 → DL-1 → DL-2 → DL-4 → DL-3 → DL-7 → DL-6 → DL-5 → DL-8 → DL-9 → DL-10 → DL-12 → DL-11 → DL-13.
Razón: primero lo que **entrega valor inmediato al alumno y es puramente de dominio** (álgebra, tabla, Karnaugh, verificación); después el editor y el paso a paso; el motor ampliado y lo secuencial más tarde por ser lo más costoso; la visión al final porque depende de que el editor y los formatos sean estables.

---

## 20. Riesgos, límites y decisiones abiertas

### 20.1 Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **El reconocimiento de esquemas a mano es difícil** y nunca será perfecto | Alto | Revisión humana obligatoria, confianza por elemento, métrica publicada, empezar por expresiones/tablas. |
| **Ampliar el motor** puede romper la certificación F8-Q | Alto | Motor nuevo al lado; prueba de equivalencia con el certificado; sin tocar el existente. |
| **Explosión combinatoria** en QM/Petrick y tablas | Medio | Topes, cancelación, Espresso/BDD/SAT, mensajes claros y resultado «parcial». |
| **Álgebra guiada que no llega al mínimo** | Medio | Comparar siempre con QM; explicar cómo continuar; no afirmar «mínima» sin certificación. |
| **Alcance enorme** | Alto | Fases entregables; orden por valor; cada fase con criterios propios. |
| **Rendimiento del lienzo** con muchos elementos | Medio | *Culling*, índice espacial, pruebas de rendimiento. |
| **Dependencias externas** (OpenCV, Tesseract, ABC…) | Medio | Todas opcionales con degradación clara. |
| **Privacidad** al enviar imágenes | Alto | Resuelto por la decisión D1: reconocimiento solo local, sin servicios externos ni claves; aviso si el usuario configura un host de Ollama distinto de `127.0.0.1` (§17). |
| **Mantenimiento de la UI en español** | Bajo | Cadenas centralizadas y prueba automática de literales en inglés. |
| **Pruebas de UI lentas** (la suite completa tarda >6 min) | Medio | Lógica en dominio testeable sin Qt; pruebas de UI mínimas y dirigidas. |

### 20.2 Límites conocidos (declarados al usuario)

- «Mínima» solo se afirma con certificación (QM+Petrick); en funciones grandes se dirá «reducida».
- Karnaugh hasta **6 variables** (más allá no es legible).
- El simulador **no modela** analógico (corrientes, umbrales, ruido): es lógico/temporal. **No hay cosimulación mixta** analógico-digital en este documento ni en `CIRCUITS_LAB.md` en sus versiones actuales; lo que existe es un puente por datos (§23.2).
- El reconocimiento de imagen **no** es fiable al 100 %; es un asistente.
- La metaestabilidad se ofrece como **modelo informativo**, no como simulación física.

### 20.3 Decisiones que necesito de ti

| # | Decisión | Opciones | Mi recomendación |
|---|---|---|---|
| D1 | ¿Se acepta enviar imágenes a un servicio externo de visión? | Sí / No (solo local) / Configurable | ✅ **DECIDIDO: solo local.** Visión clásica con OpenCV + Ollama con modelo de visión (§13.3.1). Sin servicios externos. |
| D2 | ¿Dependencias opcionales de visión local (OpenCV, Tesseract, ONNX)? | Instalarlas / No | ✅ Implícito por D1: **OpenCV** y **Ollama** opcionales; Tesseract/ONNX según resultados de la evaluación. |
| D3 | ¿Herramientas externas de verificación? | ABC/Espresso si están / No | ✅ **DECIDIDO:** solo ABC/Espresso opcionales; **Icarus y Yosys descartados** (D11). |
| D4 | Límite de diseño plano | 1 024 nodos (actual) / ampliar | ✅ **DECIDIDO: ampliar** en el motor nuevo (objetivo inicial 65 536; el motor certificado no cambia). |
| D5 | ¿Qué símbolos por defecto? | ANSI / IEC | **ANSI** por defecto, IEC alternable |
| D6 | ¿Importar **Logisim** (`.circ`) en la primera versión? | Sí / Después | **Después** (DL-10+) |
| D7 | Umbral de exactitud del reconocimiento para dar la función por «entregada» | p. ej. 90 % de puertas y 85 % de conexiones sobre el conjunto de evaluación | Fijar el conjunto de evaluación primero |
| D8 | Prioridad de fases | Orden de §19 / otro | ✅ **DECIDIDO:** empezar por **DL-0, DL-1, DL-2 y DL-4** (tabla de verdad, reducción paso a paso, Karnaugh/QM y verificación, sin tocar el motor certificado). |
| D9 | Perfiles de hardware para la visión | Ligero (6 GB VRAM) / Estándar (8 GB) | ✅ **Definidos** en §13.3.2; se diseña para el equipo más justo (RTX 2060, 6 GB). |
| D10 | Modelo de visión concreto | — | **Pendiente**: se decide midiendo 2–3 candidatos con el conjunto de evaluación cuando Ollama esté instalado. |

---

## 21. Lo que no se había pedido pero se incluye (o se propone)

1. **Modo estudio** (predice y corrige) y **modo asistido** (aplica tú la ley).
2. **Contraejemplos** cuando algo no coincide, cargados en el esquema.
3. **Comprobación de equivalencia entre dos circuitos** (para saber si tu reducción es correcta).
4. **Detección de riesgos (hazards) y glitches** con corrección por consenso.
5. **Camino crítico** y análisis de **setup/hold**.
6. **Cobertura de fallos «stuck-at» y generación de vectores de prueba** (ATPG).
7. **Máquinas de estados** completas: editor, minimización, síntesis y equivalencia.
8. **Biestables, contadores, registros, LFSR, memorias, PLA/PAL, ALU.**
9. **Valores `X/Z/U`** y buses de tres estados.
10. **Subcircuitos y biblioteca reutilizable**, buses y etiquetas de red.
11. **Exportar a BLIF/PLA/CSV/VCD** y **banco de pruebas** en formato propio; oráculo opcional ABC/Espresso. *(HDL descartado, D11.)*
12. **Informe de práctica** en PDF/DOCX/Markdown.
13. **Nuevo tipo de pregunta «circuito digital»** con corrección automática por equivalencia y **generador de ejercicios** sembrado.
14. **Proyectos con versionado, autoguardado y recuperación.**
15. **Accesibilidad completa** (solo teclado, descripción textual del circuito, alto contraste).
16. **Símbolos ANSI/IEC alternables.**
17. **Códigos de línea, Hamming, CRC, IEEE 754, coma fija, BCD, Gray.**
18. **Mismos huecos en el editor analógico** (deshacer/rehacer, zoom, paso a paso): conviene compartir el núcleo del lienzo entre ambos laboratorios en lugar de duplicarlo (ya recogido en `CIRCUITS_LAB.md` §21 punto 15; ver §6.1 y §23.4).
19. **Guía de usuario y tutorial interactivo** dentro de la propia página.
20. **Conjunto de evaluación y métricas públicas** para el reconocimiento de imagen.
21. **Comparación visual de dos versiones** de un diseño.
22. **Estimación de coste CMOS** (transistores) y **consumo dinámico** como métricas didácticas.
23. **Nota importante sobre tests actuales:** hay que **normalizar los saltos de línea** en la comparación del fichero dorado E0 (falla en Windows por `\r\n`) — corrección trivial pero pendiente.

---

## Anexo A — Catálogo de leyes (formato)

Cada ley se define como dato, no como código disperso:

```
id:        absorcion_or
nombre:    Absorción
patron:    A + A·B
reemplazo: A
metavars:  A, B (cualquier subexpresión)
tipo:      reduce
dual:      absorcion_and
prueba:    verificada por tabla de verdad al cargar el catálogo
```

Al arrancar, **el catálogo se autovalida**: cada ley se comprueba por tabla de verdad y cada dual se comprueba dual. Añadir una ley nueva sin ser válida hace fallar el arranque de las pruebas.

## Anexo B — Formato `digital-design/2` (propuesto)

Extensión de `digital-design/1` (existente) compatible hacia atrás (el lector 2 lee 1):

```json
{
  "schema": "digital-design/2",
  "name": "sumador-completo",
  "meta": {"autor": "", "asignatura": "", "creado": "", "notas": ""},
  "symbols": "ANSI",
  "elements": {
    "A":  {"type": "INPUT", "x": 2, "y": 2, "width": 1, "stim": {"mode": "pattern", "states": "0101", "step": "1"}},
    "g1": {"type": "XOR", "x": 12, "y": 2, "n": 2, "delay": {"min": "0", "typ": "0", "max": "0"}},
    "S":  {"type": "OUTPUT", "x": 30, "y": 4, "label": "Suma"}
  },
  "wires": [["A", "g1", 0], ["B", "g1", 1], ["g1", "S", 0]],
  "buses": [],
  "subcircuits": {},
  "tests": {"vectors": [], "assertions": []},
  "origin": {"kind": "manual|image|blif", "image_ref": null, "confidence": null}
}
```

Reglas: identificadores validados por expresión regular, límites de tamaño, orden canónico al serializar (mismo diseño → mismos bytes → mismo digest).

## Anexo C — Mapa de módulos y responsabilidades

| Módulo | Responsabilidad | Capa | Estado |
|---|---|---|---|
| `boolean/expr.py` | AST y normalización | dominio | nuevo |
| `boolean/parse.py` | Lector de expresiones | dominio | nuevo |
| `boolean/laws.py` | Catálogo de leyes | dominio | nuevo |
| `boolean/rewrite.py` | Reescritura con traza | dominio | nuevo |
| `boolean/simplify.py` | Estrategias de reducción | dominio | nuevo |
| `boolean/truth.py`, `canonical.py` | Tabla, minitérminos | dominio | nuevo |
| `boolean/kmap.py`, `qm.py`, `espresso.py` | Minimización | dominio | nuevo |
| `boolean/bdd.py`, `sat.py`, `equiv.py` | Equivalencia | dominio | nuevo |
| `boolean/hazards.py` | Riesgos | dominio | nuevo |
| `boolean/synth.py`, `techmap.py` | Síntesis y mapeo | dominio | nuevo |
| `seq/*` | Secuencial y FSM | dominio | nuevo |
| `calc/*` | Calculadoras | dominio | nuevo |
| `digital/core.py` etc. | Motor certificado | dominio | **existe, no se toca** |
| `digital2/*` | Motor ampliado (retardos, `X/Z`) | dominio | nuevo, al lado |
| `application/digital_design.py` | Diseño editable | aplicación | existe, se amplía |
| `application/digital_lab.py` | Fachada del laboratorio | aplicación | nuevo |
| `application/digital_import.py`, `digital_export.py` | E/S de formatos | aplicación | nuevo |
| `application/digital_explain.py` | Lecciones | aplicación | nuevo |
| `infrastructure/abc.py`, `vision.py` | Oráculo opcional y visión | infraestructura | nuevo, opcional |
| `ui/digital_editor.py` | Lienzo | UI | existe, se amplía |
| `ui/digital_*_view.py` | Pestañas | UI | nuevo |
| `domain/engineering/digital_circuit.py` | Puente `digital-circuit/1` del motor certificado | dominio | **existe, no se toca** (sale con `digital/`, §23.5) |
| `infrastructure/vision.py` | Pipeline de imagen **compartido** (§13.3.3) | infraestructura | nuevo, opcional |
| núcleo de lienzo y de gráficas (`ui/canvas/`, `ui/plot/`) | Compartidos con circuitos y señales (§23.4) | UI | nuevo, neutral |

Todas las rutas de esta tabla usan el árbol actual; el destino tras CI-R está en §23.5.

## Anexo D — Glosario

**Minitérmino (mᵢ):** producto de todas las variables (directas o negadas) que vale 1 solo en la fila *i*. **Maxitérmino (Mᵢ):** suma de todas las variables que vale 0 solo en la fila *i*. **Implicante primo:** término producto que implica la función y no se puede reducir más. **Primo esencial:** implicante primo que es el único que cubre algún minitérmino. **Petrick:** método para elegir la cobertura mínima de implicantes. **Riesgo (hazard):** posibilidad de un pico transitorio en la salida por retardos desiguales. **BDD:** diagrama de decisión binario, representación canónica de una función. **SAT:** problema de satisfacibilidad booleana. **Miter:** circuito que compara dos circuitos con XOR de salidas. **ATPG:** generación automática de vectores de prueba. **FSM:** máquina de estados finitos (Moore: salida depende del estado; Mealy: del estado y la entrada). **DRC:** comprobación de reglas de diseño. **Setup/hold:** tiempos de preparación y mantenimiento de un biestable respecto al flanco de reloj. **VCD:** formato estándar de volcado de formas de onda. **LUT/PLA/PAL:** tabla de consulta / matriz lógica programable.

---

## 22. Ampliación: conceptos de diseño digital de las guías docentes

Origen: guías docentes de GREELEC (UPC) descargadas en `guias_upc/` — Diseño Digital (230911), Sistemas Digitales Configurables (230921), Sistemas de Hardware de Procesado de la Información (230931), Sistemas Embebidos (230916), Diseño Microelectrónico (230930) y el seminario de Códigos Lineales (230300). Esta sección **añade** contenido; no sustituye a las anteriores. Prioridad: **Diseño Digital primero**; el resto, después. El foco es la **parte teórica con gráficas y ejercicios de resolver**.

### 22.1 Exclusiones y decisión D11

- **Fuera de alcance:** VHDL, Verilog, cualquier HDL, simulación de HDL, flujo FPGA/CPLD (síntesis, restricciones, informes de recursos) y exportación a Quartus. El alumno ya dispone de Quartus para eso.
- Se conservan los conceptos que las guías enseñan **alrededor** del HDL, tratados de forma visual y con el motor propio: máquinas algorítmicas, segmentación, test, consumo, lógica programable (LUT, PLA/PAL).

### 22.2 Mapa asignatura → laboratorio

| Asignatura (cuatrimestre) | Conceptos que entran | Sección |
|---|---|---|
| **Diseño Digital (3.º)** | Asíncronos, análisis secuencial, MSI, contadores, CMOS eléctrico, temporización, ASM, memorias | 22.3 |
| **Sistemas Digitales Configurables (5.º)** | Segmentación, máquinas concurrentes, microprogramación, consumo, test, relojes, LUT | 22.4 |
| **Sistemas Embebidos (4.º)** | CPU educativa, memoria y caché, decodificación, temporización de memoria, E/S e interrupciones | 22.5 |
| **Sist. de Hardware de Procesado (7.º)** | Formatos numéricos, FIR/IIR, CORDIC, ADC/DAC, protocolos, modulación, LMS | 22.6 |
| **Diseño Microelectrónico (7.º)** | Puertas CMOS a nivel de transistor, retardo y potencia (solo la parte digital) | 22.3-E |
| **Álgebra Lineal, Códigos y Secretos (3.º, seminario)** | Códigos lineales, compartición de secretos | 22.7 |

### 22.3 Diseño Digital: lo que falta

Cada ejercicio sigue la plantilla de §22.8: enunciado generado, **gráfica esperada**, solución paso a paso, verificación independiente y sello de §11.4.

#### A. Sistemas asíncronos

Tabla de flujo primitiva, reducción de estados, **estados estables/inestables**, **carreras críticas y no críticas**, asignación de estados libre de carreras (líneas de transición), **riesgos esenciales**, ecuaciones de excitación y realización con puertas o con latches SR. Gráficas: diagrama de transiciones sobre el cubo de estados, cronograma de una carrera con dos resultados distintos según los retardos. Verificación: simulación con retardos (§7.1) en ambos órdenes de retardo.

#### B. Análisis de circuitos secuenciales (circuito → diagrama)

Dado un circuito dibujado: ecuaciones de entrada de los biestables → tabla de transición → tabla de estados → **diagrama de estados** → identificación Moore/Mealy → cronograma para una secuencia de entrada. Es la dirección **contraria** a la síntesis de §8.3; comparte el mismo modelo de FSM y se comprueba por equivalencia con la FSM extraída.

#### C. Diseño con módulos MSI (ejercicios guiados)

Implementar una función dada con: **multiplexor** (expansión de Shannon, variables «de control» elegibles), **decodificador + OR/NAND**, **sumadores** y **comparadores** en cascada, **ROM/LUT**. Extensión de módulos (mux 16:1 con 4:1, decodificador 4→16 con dos 3→8). El sistema muestra el coste y compara alternativas.

#### D. Contadores y registros con biestables

Diseño con D/T/JK a partir de la **tabla de excitación**: módulo N, secuencias arbitrarias, BCD, Johnson, anillo; carga y borrado síncronos o asíncronos; **estados ilegales** y **autoarranque**; división de frecuencia con cronograma. Gráfica: diagrama de estados con estados ilegales resaltados y cronograma de las salidas.

#### E. Nivel eléctrico CMOS

| Contenido (guía, tema 4) | Gráfica / ejercicio |
|---|---|
| Inversor CMOS | **Curva de transferencia (VTC)**, umbral de conmutación, ganancia |
| Niveles y márgenes | V_IL, V_IH, V_OL, V_OH, **márgenes de ruido** NM_H y NM_L, comparación entre familias |
| Puertas CMOS | **Redes pull-up/pull-down duales** derivadas de la función; recuento de transistores; puertas complejas (AOI/OAI) |
| Retardo | t_pHL, t_pLH, t_p; efecto del fan-out y de la capacidad de carga |
| Potencia | Dinámica `α·C·V²·f`, estática (fugas) y de cortocircuito; curva potencia frente a frecuencia |
| Salidas especiales | Colector/drenador abierto y **dimensionado de la resistencia de pull-up**; tres estados; alta impedancia |
| Espúreos | Picos transitorios por conmutación simultánea (ground bounce, didáctico) |

Datos de las familias (TTL, CMOS 5 V, LVCMOS 3,3 V) como **tabla editable**, marcados «valores típicos didácticos; verificar en la hoja del fabricante». Cálculo exacto con `Decimal`. La simulación a nivel de conmutador de la red de transistores se comparte con el laboratorio analógico (`mna/mosfet.py`, que seguirá en el paquete de circuitos tras CI-R); aquí solo se **usan** sus resultados por interfaz pública. Reparto: la **tabla de familias lógicas** (V_IL, V_IH, V_OL, V_OH, I_OL, I_OH, t_p, C_in), los márgenes de ruido, la potencia `α·C·V²·f`, el dimensionado de pull-up y los ejercicios con gráfica son **de este laboratorio**; el MOSFET como circuito (punto de trabajo, inversor con carga, conmutación) es de `CIRCUITS_LAB.md` §9. La tabla de familias es el **puente** con el simulador analógico (§23.2). El «Schmitt» de §9.1 es un búfer lógico con histéresis, distinto del Schmitt con op-amp de `CIRCUITS_LAB.md` §10.

#### F. Temporización

Cronogramas con parámetros (t_cq, t_su, t_h, t_pd mín/máx, skew): **frecuencia máxima** `1/(t_cq + t_lógica + t_su + t_skew)`, **holgura** de setup y de hold por camino, violaciones señaladas en el cronograma; **reset síncrono frente a asíncrono** (recuperación/eliminación); **sincronizador de dos etapas**; reloj con habilitación frente a reloj «gated». Ejercicio inverso: dado el periodo, ¿cuánta lógica cabe?

#### G. Máquinas algorítmicas (ASM)

**Carta ASM** (caja de estado, decisión, salidas condicionales) editable; conversión carta ↔ diagrama de estados; separación **unidad de datos / unidad de control**; diseño del camino de datos (registros, ALU, multiplexores, señales de control); ejemplos de libro: multiplicador por sumas y desplazamientos, divisor, contador de unos, control de semáforo. Verificación: simulación de la carta frente al circuito sintetizado.

#### H. Catálogo de circuitos integrados 74xx (descartado, D14)

Componentes «con nombre de chip» para reproducir las prácticas reales: patillaje, tabla de función y ejemplo de uso. **DESCARTADO (D14):** el laboratorio de la asignatura usa Quartus II y no se ha encontrado ninguna lista de chips. Se conservan los MSI genéricos de §9.2. Si se reabriera, esta era la lista provisional (a validar contra hojas del fabricante): 7400, 7402, 7404, 7408, 7432, 7486, 7447 (BCD→7 seg.), 74138, 74139, 74151, 74153, 74157, 7483, 7485, 7474, 7476, 74161/74163, 74175, 74194, 74244/74245 (buses). Cada uno se **construye a partir de puertas** y se verifica por tabla contra la función publicada.

#### I. Memorias y decodificación

ROM/PROM, SRAM, DRAM (conceptos); **expansión** en ancho y en profundidad; **mapa de direcciones** con decodificación total y parcial (solapamientos y huecos dibujados); ejercicio: dado un mapa, diseñar el decodificador. Temporización de lectura/escritura genérica (ver 22.5).

#### J. Lógica programable (solo conceptos)

PLA, PAL, CPLD y FPGA como **estructuras**: matriz AND-OR, macroceldas, **LUT de k entradas + biestable** como célula lógica. Ejercicios: programar una PLA/PAL desde una función; **mapear una función a LUT de 4 entradas** (contando LUT y niveles); comparar con puertas. Sin flujo de síntesis ni HDL.

### 22.4 Sistemas Digitales Configurables (solo el concepto)

| Concepto | Ejercicio o gráfica |
|---|---|
| **Segmentación (pipelining)** | Dividir un camino combinacional en etapas; **diagrama espacio-tiempo**, latencia, rendimiento, frecuencia máxima antes/después; riesgos y burbujas |
| **Máquinas de estados concurrentes** | Dos FSM que se comunican (petición/acuse); cronograma conjunto; detección de interbloqueo |
| **Sistemas microprogramados** | Memoria de control: formato de microinstrucción, secuenciador, ejecución paso a paso |
| **Reducción de consumo** | Clock gating, aislamiento de operandos, reducción de actividad: estimación de conmutaciones con y sin técnica |
| **Estructuras de test** | **Scan chain**, **BIST** con LFSR y firma MISR, boundary scan (JTAG, conceptual); cobertura de fallos (enlaza con ATPG de §7.6) |
| **Relojes** | Divisores, dominios de reloj y cruce entre dominios (conceptual, con cronograma) |
| **IP cores** | Bloques reutilizables con interfaz declarada (subcircuitos de §6.2) |

### 22.5 Sistemas Embebidos: arquitectura de computadores

Se plantea un **procesador educativo** dentro de la aplicación, construido con los bloques de §9 para que se pueda abrir y ver por dentro.

| Concepto | Contenido |
|---|---|
| **CPU educativa** | Camino de datos (registros, ALU, bus) y control **cableado o microprogramado**; ISA mínima (unas 16 instrucciones) con **ensamblador y desensamblador**; ejecución **ciclo a ciclo** con el registro de instrucción, PC y banderas visibles |
| **Arquitecturas** | Von Neumann frente a Harvard; **endianness** (visualización de bytes); pila y subrutinas |
| **Jerarquía de memoria** | **Caché**: correspondencia directa, asociativa y por conjuntos; aciertos y fallos sobre una traza de direcciones; gráfica de **tasa de aciertos** frente a tamaño y asociatividad; tiempo medio de acceso; **memoria virtual** (tabla de páginas, TLB, fallo de página) |
| **Decodificación** | Mapa de memoria y de E/S con decodificación de direcciones (ver 22.3-I) |
| **Temporización de memoria** | Cronogramas de **lectura y escritura** de SRAM y ROM con tiempos de acceso, setup y hold; comprobación de si una CPU dada puede con una memoria dada; introducción a DRAM (refresco, RAS/CAS) |
| **Buses y compatibilidad eléctrica** | Colector abierto en buses sin arbitraje, niveles entre familias, carga máxima |
| **Entrada/salida** | Registros de periférico; **sondeo frente a interrupciones**; vector, prioridad, enmascaramiento, **latencia** y cambio de contexto en cronograma; temporizadores; conversores conectados a la CPU |

Este bloque es grande (esfuerzo XL) y se planifica después del de Diseño Digital.

### 22.6 Sistemas de Hardware de Procesado: conceptos con gráficas

Se **reutilizan** los módulos ya existentes para la matemática: `dsp/` (que **sale** hacia `SIGNALS_LAB.md`, CI-R) y su objeto `FilterDesign` (`SIGNALS_LAB.md` §23.5), `comms/` (que se queda en circuitos, su D7) y `mna/`; todos por su interfaz pública. Aquí se añade la **realización digital** y sus efectos. Reparto fijado en `SIGNALS_LAB.md` §23.5 y en §23.3 de este documento: el **diseño** del filtro y la **teoría** (LMS, cuantización, SQNR) son de otros laboratorios; este añade solo la realización en hardware.

| Concepto | Ejercicio o gráfica |
|---|---|
| **Formatos numéricos y precisión finita** | Coma fija Qm.n, saturación y redondeo; **ruido de cuantización en hardware**; SNR ≈ 6,02·N + 1,76 dB (la calculadora es la de `MATH_LAB.md` §8.2 I y la teoría, `SIGNALS_LAB.md` §16); gráfica del error frente al número de bits |
| **Filtros digitales FIR e IIR** | Estructuras (directa, transpuesta, cascada) a partir de un `FilterDesign` de `SIGNALS_LAB.md`; respuesta en frecuencia **ideal frente a cuantizada**; efecto de cuantizar los coeficientes sobre polos y ceros; desbordamiento; coste en puertas (esta fila es la «DL-20» que `SIGNALS_LAB.md` D20 asigna aquí) |
| **CORDIC** | Modo rotación y modo vectorial; iteraciones paso a paso; gráfica del **error frente al nº de iteraciones**; ganancia constante |
| **Convertidores (lado digital)** | Lógica digital de ADC y DAC: codificador de prioridad del flash, **registro SAR y su FSM**, decimador del sigma-delta, códigos de salida (binario, offset, complemento a 2), cronograma de la conversión e interfaz con la CPU (§22.5). Las arquitecturas eléctricas, INL/DNL, ENOB y el circuito son de `CIRCUITS_LAB.md` §10.15 (BL-AN-14); la teoría de cuantización y el SQNR medido, de `SIGNALS_LAB.md` §16 |
| **Segmentación** | Como en 22.4, aplicada a un filtro o a CORDIC |
| **Interfaces y protocolos** | **UART, SPI, I2C**: cronograma de una trama, generador y decodificador; errores de paridad y de trama; velocidad de transmisión |
| **Modulación digital** | Generación de la **secuencia de bits y símbolos** (mapeador, formador de pulso en coma fija) y su cronograma; las constelaciones y el espectro vienen de `comms/` y de `SIGNALS_LAB.md` §11 |
| **Filtro adaptativo** | **Realización hardware** de LMS y NLMS (MAC, coma fija, desbordamiento, segmentación); la teoría y la **curva de convergencia** son de `MATH_LAB.md` bloque 16 y `SIGNALS_LAB.md` §17 |

### 22.7 Códigos lineales y compartición de secretos

**Reasignado (alineación 2026-10-01).** La matemática de este apartado, es decir, códigos lineales binarios (matriz generadora y de comprobación de paridad, forma sistemática, síndrome y decodificación con *standard array*, distancia mínima y capacidad de corrección, cotas de Hamming y Singleton) y **compartición de secretos** de tipo Shamir sobre `GF(p)` con su gráfica de puntos, **ya está en `MATH_LAB.md`** (§4.9 y §4.10, bloques 9 y 10, fase ML-17, y la asignatura «Álgebra Lineal, Códigos y Secretos» de su §3), con aritmética exacta y segundo camino. No se reimplementa aquí. Lo que aporta este laboratorio es la **realización en hardware**: codificador y decodificador de Hamming como circuito de puertas (árboles XOR, corrección por decodificador del síndrome), **CRC serie con LFSR** y su cronograma, generador y comprobador de paridad. Esa realización se verifica contra el resultado de `MATH_LAB` (segundo camino cruzado: división polinómica frente a LFSR). Hamming y CRC como calculadoras siguen en §10 con esta misma división.

### 22.8 Plantilla común de «ejercicio con gráfica»

Todo ejercicio de este apartado (y del resto de laboratorios: `MATH_LAB.md` §7, `SIGNALS_LAB.md` §21.1 y `CIRCUITS_LAB.md` §15 la adoptan) usa la misma estructura, para que el corrector, el generador sembrado (§15.4) y la maestría funcionen igual:

| Campo | Contenido |
|---|---|
| Enunciado | Texto generado a partir de parámetros sembrados |
| Datos | Parámetros y restricciones (límite de puertas, familia lógica, frecuencia…) |
| Entregable | Qué debe entregar el alumno: circuito, expresión, tabla, valor numérico, **gráfica dibujada** |
| Solución | Traza paso a paso (E0) |
| Gráfica esperada | Cronograma, VTC, diagrama de estados, curva… con la solución superpuesta a la del alumno |
| Verificación | Método independiente (§11) y sello |
| Asignatura / tema / competencia | Enlace a CE14, CE15, CE25 y al tema de la guía |

Una **gráfica dibujada** por el alumno (por ejemplo un cronograma) se corrige por **comparación de eventos** (instantes y valores), con tolerancia configurable, no por píxeles.

### 22.9 Ejercicios tipo por tema de Diseño Digital

| Tema de la guía | Tipos de ejercicio | Gráfica |
|---|---|---|
| 1. Introducción | Sistemas de numeración y códigos, álgebra de Boole, niveles y alta impedancia | Tabla de verdad, niveles lógicos |
| 2. Combinacional | SoP/PoS, módulos MSI, sumadores, comparadores | Karnaugh, esquema |
| 3. Secuencial | Latches y biestables, análisis y síntesis de FSM, registros y contadores, asíncronos, temporización, ASM | Diagrama de estados, cronograma, carta ASM |
| 4. CMOS | VTC, márgenes de ruido, retardos, consumo, lógica programable, memorias | VTC, potencia frente a f, mapa de memoria |

### 22.10 Fases nuevas

Orden pensado para que **Diseño Digital vaya primero** y encaje después de DL-8/DL-9 de §19.

| Fase | Contenido | Depende de | Esfuerzo |
|---|---|---|---|
| **DL-14** Secuencial avanzado | Asíncronos (A), análisis de circuitos secuenciales (B), ejercicios MSI (C), contadores (D) | DL-8, DL-9 | L |
| **DL-15** Eléctrico y temporización | CMOS (E), temporización (F), familias lógicas y colector abierto | DL-5; consume `mna/mosfet.py` por interfaz pública (sin depender de una fase CI concreta: si falta, VTC con el modelo analítico propio) | L |
| **DL-16** ASM y camino de datos | Cartas ASM (G), microprogramación, máquinas concurrentes (22.4) | DL-8 | L |
| **DL-17** Memorias y lógica programable | Memorias y decodificación (I), lógica programable (J) | DL-9 | M |
| **DL-18** Plantilla de ejercicios | 22.8 y 22.9, generador sembrado por tema, enlace con competencias, cadenas solo en español (D12: sin interfaz catalana) | DL-12 | M |
| **DL-19** Test, consumo y segmentación | Scan, BIST/LFSR, clock gating, pipelining, relojes | DL-14 | M |
| **DL-20** Procesado digital | Formatos, realización de FIR/IIR, CORDIC, lado digital de ADC/DAC, protocolos, realización de LMS (22.6) | DL-6, **SG-9** de `SIGNALS_LAB.md` (objeto `FilterDesign` e IIR; su D20 fija esta fase como dueña de la cuantización de coeficientes) | L |
| **DL-21** Arquitectura de computadores | CPU educativa, ensamblador, caché, memoria virtual, E/S e interrupciones (22.5) | DL-17 | XL |
| **DL-22** Códigos (realización hardware) | 22.7 reasignado: Hamming, CRC con LFSR y paridad como circuitos y cronogramas; la matemática es de `MATH_LAB` | DL-6, DL-8 (LFSR), **ML-17** | S-M |
| **DL-23** Placa DE2 virtual | 22.13 y 22.14: placa con SW/KEY/LED/HEX y teclado, ejercicios del estudio previo de las Prácticas 0 a 3, cronogramas estilo Quartus, tablero de ajedrez, ejemplos dorados | DL-3, DL-7 | M |

**Orden recomendado para lo nuevo:** **DL-23 (placa DE2, en cuanto estén DL-3 y DL-7)** → DL-14 → DL-15 → DL-16 → DL-17 → DL-18 → DL-19 → DL-20 → DL-22 → DL-21.

### 22.11 Criterios de aceptación adicionales

1. Un circuito secuencial dibujado da su **diagrama de estados** correcto, y la FSM extraída es **equivalente** al circuito.
2. Un circuito asíncrono con carrera crítica se **detecta** y se muestra el cronograma que falla.
3. La **VTC**, los márgenes de ruido y el consumo salen de los datos de la familia y coinciden con el cálculo manual de los ejemplos dorados.
4. Un cronograma con violación de setup o hold la **señala** y da la holgura exacta.
5. Una **carta ASM** y el circuito sintetizado producen el **mismo cronograma**.
6. Un CRC calculado con el LFSR del circuito **coincide** con la división polinómica de `MATH_LAB`, y un Hamming(7,4) dibujado corrige un error y avisa con dos.
7. La CPU educativa ejecuta un programa de ejemplo y su traza **coincide** con un intérprete independiente del mismo ISA.
8. Toda gráfica esperada de un ejercicio se genera de la traza, no de datos escritos a mano.
9. Ninguna función de esta sección usa ni genera HDL.

### 22.12 Riesgos y decisiones abiertas nuevas

| Riesgo | Mitigación |
|---|---|
| **Datos de familias lógicas** erróneos o desactualizados | Marcar como didácticos y usar tabla editable |
| **La CPU educativa crece sin límite** | ISA mínima fijada de antemano y aparte como fase XL |
| **Duplicar matemática** ya presente en `MATH_LAB`, `SIGNALS_LAB` (`dsp/`), `comms/` y `mna/` | Reutilizar sus módulos por interfaz pública; aquí solo se añade la realización digital (§23.3) |
| **Corregir gráficas dibujadas a mano** | Comparación por eventos con tolerancia, no por imagen |

| # | Decisión | Estado |
|---|---|---|
| D11 | Sin VHDL/Verilog/HDL ni flujo FPGA | ✅ **DECIDIDO** (22.1) |
| D12 | ¿Interfaz también en catalán (las guías de Diseño Digital están en catalán)? | ✅ **DECIDIDO (2026-10-01): no.** La aplicación no tendrá interfaz en catalán; las guías en catalán se leen como fuente, la UI y las cadenas de ejercicios van en español. |
| D13 | ISA de la CPU educativa | ✅ **DECIDIDO: propia y simple** (2026-09-30). Se podrá revisar más adelante (p. ej. un subconjunto de RISC-V) si hiciera falta. |
| D14 | Catálogo de chips 74xx | ✅ **CERRADO (2026-09-30): se descarta.** Búsqueda en Studocu y en la web de la ETSETB sin ninguna lista de chips, y la guía 230911 y la Práctica 0 confirman que el laboratorio usa **Quartus II y la placa DE2 (Cyclone II EP2C35F672C6)**, no chips sueltos (ver §22.13). Se mantienen los módulos MSI genéricos de §9.2. Reabrir solo si el profesorado confirma prácticas con chips reales. |
| D15 | Datos de las familias lógicas: valores típicos didácticos o los de las hojas del laboratorio | Pendiente |

### 22.13 Práctica de laboratorio en placa DE2 (versión virtual, sin HDL)

Fuente: guía de la Práctica 0 de Diseño Digital (v5.01, grupo 14). El laboratorio real usa **Quartus II Web Edition 9.1 sp2** y la placa **Terasic DE2** con FPGA **Cyclone II EP2C35F672C6**. La aplicación **no** sustituye a Quartus ni genera VHDL (D11); ofrece el mismo **ciclo de trabajo** para estudiar antes y comprobar después.

#### A. Placa DE2 virtual

Una vista de la placa con los recursos que usan las prácticas, conectados a los **nombres de pin** del laboratorio (`SW[17..0]`, `KEY[3..0]`, `LEDR[17..0]`, `LEDG[8..0]`, `HEX0`…`HEX7` de 7 bits, reloj):

| Recurso | Uso en la aplicación |
|---|---|
| Microinterruptores `SW` | Entradas del circuito; se pueden pulsar en vivo (§7.3) |
| Pulsadores `KEY`, reloj de la placa | Entradas de tipo pulsador y de reloj |
| LED rojos y verdes | Salidas de un bit |
| Displays de 7 segmentos `HEX0`…`HEX7` | Salida con el dibujo real de los segmentos; nivel activo configurable |

Los nombres exactos, los pines de la FPGA y los niveles activos se toman del **manual de la DE2** y de su tabla de pines, ya disponibles (datos en §22.14-A); no se inventan. La tabla de asignación se puede **importar de ese CSV**.

#### B. Ejercicios del «estudio previo» (los que pide la guía antes de ir al laboratorio)

| Pregunta tipo de la guía | Qué hace la aplicación |
|---|---|
| Tabla de la verdad y logigrama con AND, OR y NOT de un multiplexor 2:1 | Tabla, esquema y comprobación de equivalencia |
| Pasar de 1 bit a un bus de 4 bits; ¿cuántas filas tendría la tabla? | Cálculo (2^9 = 512 filas) y expansión a bus |
| Dibujar un cronograma para al menos cuatro combinaciones | El alumno dibuja; se corrige por eventos (§22.8) |
| ¿En qué posición deben estar los interruptores para un valor dado? | Placa virtual con la asignación de pines |
| Tabla de la verdad de un convertidor BCD → 7 segmentos; ¿activo alto o bajo?; ¿qué combinación muestra la «S»? | Tabla editable, display dibujado y corrección |
| Esquema completo indicando la anchura de cada bus | Editor con buses y comprobación de anchuras (§6.4) |

#### C. Cronogramas al estilo de Quartus

Editor de formas de onda para entradas con: **tiempo final** y **rejilla** configurables (p. ej. 800 ns y 20 ns), entradas de tipo **reloj con periodo** (la guía usa 200, 400 y 800 ns para hacer una simulación **exhaustiva** con tres entradas), valor arbitrario por tramo, **agrupar señales en bus** y mostrarlas en **binario, hexadecimal o decimal**. La simulación con retardos (§7.1) reproduce el **modo «Timing»** de forma didáctica; los retardos de la Cyclone II real **no** se modelan, y así se declara.

#### D. Diseño jerárquico como en la guía

Esquemático con **símbolos propios** (crear símbolo de un diseño, editar su dibujo, p. ej. el trapecio del multiplexor), **buses** `x[3..0]` y líneas de nodo con nombre (§6.2). Ejemplo dorado: la Práctica 0, un multiplexor 2:1 de 4 bits más tres convertidores BCD→7 segmentos, con `SW[17..14]`, `SW[13..10]`, `SW[0]`, `HEX6`, `HEX4` y `HEX0`; su resultado debe coincidir con la simulación global de la guía.

#### E. Lo que sigue fuera

Compilación, ajuste a la FPGA, análisis de tiempos reales, grabar la placa y VHDL siguen siendo cosa de Quartus y de la placa física.

#### F. Decisión y criterio de aceptación

| # | Decisión | Estado |
|---|---|---|
| D16 | ¿Incluir la placa DE2 virtual y el editor de cronogramas estilo Quartus? | ✅ **DECIDIDO: sí** (2026-09-30). Fase DL-23; los nombres de pin y niveles activos vienen del manual y la tabla de pines de la DE2 (ya aportados, §22.14-A). |

Criterio: la Práctica 0 completa (estudio previo y simulación global) se puede resolver en la aplicación y sus resultados coinciden con los de la guía.

### 22.14 Prácticas 1, 2 y 3 y datos reales de la placa DE2

Fuentes: guías `DD_Prac1_v4_2`, `DD_Prac2_v3_33`, `DD_Prac3_v3_9`, y `DE2_UserManual.pdf` y `DE2_Pin_Table.pdf` de los datasheets del laboratorio. Las prácticas están en catalán. **Importante:** casi todo el «estudio previo» de estas prácticas pide **escribir VHDL**; eso queda fuera (D11). La aplicación cubre el resto: cronogramas, tablas de verdad, logigramas, diagramas de estados y **comprobar el comportamiento**.

#### A. Datos reales de la placa (ya disponibles, ya no son «pendientes»)

Del manual de la DE2, que sustituyen a los valores supuestos de §22.13-A:

| Recurso | Dato del manual |
|---|---|
| FPGA | Cyclone II 2C35 (EP2C35F672C6) |
| Interruptores | 18. **Abajo = 0, arriba = 1** |
| Pulsadores | 4. En reposo valen 1 y dan **un pulso a 0** al pulsar (activo bajo) |
| LED | 18 rojos y 9 verdes |
| Displays de 7 segmentos | 8 (`HEX0`…`HEX7`), segmentos indexados de 0 a 6, el punto **no está conectado**. **Activos a nivel bajo** (0 enciende, 1 apaga) |
| Relojes | Osciladores de 50 MHz y 27 MHz |
| Otros | LCD de caracteres (controlador ST7066U), SRAM 512 KB, SDRAM 8 MB, Flash, PS/2, RS-232, VGA, audio; no se usan en las prácticas 0 a 3 |

La **tabla de pines** (`DE2_Pin_Table.pdf`, p. ej. `SW[0]` → `PIN_N25`) se usa como **fuente de la asignación de nombres** de la placa virtual. El LCD y las memorias quedan como ampliación opcional de la placa virtual.

#### B. Práctica 1 — validador de movimientos de ajedrez (combinacional)

Sistema `Nucli_P1`: entradas `Xi, Yi, Xf, Yf` (3 bits cada una, 0 a 7) y `fitxa` (0 = alfil, 1 = torre); salida `MOK` = movimiento correcto (y 0 si origen = destino). Son **13 entradas, 8 192 combinaciones**: la guía insiste en no hacer la tabla completa y **descomponer en bloques** (`DELTA` para la diferencia absoluta, `DCSR` para la decisión).

| Ejercicio de la guía | En la aplicación |
|---|---|
| EP1: cronograma de 8 movimientos con condiciones (4 por pieza, 2 correctos y 2 incorrectos por pieza) | Generador con esas restricciones y corrección por eventos |
| Dibujar los 8 movimientos en tableros | **Tablero de ajedrez interactivo** que muestra la jugada y la pieza |
| EP2: cronograma de `DELTA` (con restricciones sobre los valores repetidos) | Cronograma con verificación |
| EP4: cronograma de `DCSR` con `DX`, `DY`, `A_OK`, `T_OK`, `MOK` | Idem |
| EP5 y EP6: tabla de verdad **bidimensional** de 6 variables (`V_A`, `V_T`) | Tabla 2D editable (como un mapa de Karnaugh de 6 variables) |
| Comprobar en placa los 8 movimientos | Placa virtual (22.13) |

Descripciones VHDL (EP3, EP7): **fuera**. La aplicación sí puede comprobar que el bloque **dibujado** (puertas) da el mismo `MOK` que una **especificación de referencia** (tablero con las reglas del ajedrez) en las 8 192 combinaciones.

#### C. Práctica 2 — calculadora con teclado (secuencial)

Multiplica dos cifras decimales: `*` borra y espera datos, los dígitos se guardan (se ven los dos últimos), `#` ejecuta y muestra el resultado en dos displays; cuatro LED verdes indican «se pueden introducir datos» y cuatro rojos lo contrario. Bloques: `keytest` (lee el teclado y da un pulso de un ciclo, `nkey`), `keygroup`, `regs`, `AperB` (multiplicador binario más convertidor binario → BCD), `sel`, `control` (máquina de estados), `f_div` (50 MHz / 2^16 ≈ 763 Hz), `hex_disps`, `leds`.

| Ejercicio de la guía | En la aplicación |
|---|---|
| Tabla de verdad de `keygroup` | Tabla editable y comprobación |
| Convertidor binario → BCD | Tabla, circuito y calculadora (§10) con verificación |
| `sel` con el **mínimo de puertas estándar** (logigrama) | Síntesis mínima (DL-2) y comparación con el dibujo del alumno |
| Cronograma de `regs` y de `control` | Cronograma con eventos corregibles |
| **Diagrama de estados** de `control` (salidas y cambios de estado) | Editor de FSM (§8.3) con simulación |
| Ampliaciones: elegir operando A o B, signo en complemento a 2, más operaciones | Ejercicios de ampliación con el mismo modelo |

Modelo de teclado: un **teclado hexadecimal** con pulso de un ciclo por pulsación. *(Cómo está conectado físicamente a la placa no consta en los documentos leídos; se confirma con el laboratorio.)*

#### D. Práctica 3 — juego de adivinar un número (secuencial síncrono)

Se genera un número aleatorio de dos dígitos, el jugador prueba números y se indica **menor / acertado / mayor** con los 8 LED verdes (cuatro de la izquierda, cuatro del centro o cuatro de la derecha). `#` reinicia. Bloques nuevos: **contador BCD de dos cifras** (habilitación síncrona, reset asíncrono), **comparador**, y `control`, una **máquina de Mealy**.

| Ejercicio de la guía | En la aplicación |
|---|---|
| Cronograma y **diagrama de estados** (Mealy) de `control` | Editor de FSM con Mealy y cronograma |
| Contador BCD con habilitación y reset asíncrono | Bloque de §8.2 con cronograma |
| Comparador | Tabla y circuito comprobados |
| Ampliaciones (3 cifras, «trampa» con contraseña, contador de jugadas, temporizador) | Ejercicios opcionales |

El número aleatorio se modela con un **contador libre o LFSR sembrado** (determinista, §1.3): mismo arranque, misma partida.

#### E. Conjunto de ejercicios nuevo a implementar

1. Tablero de ajedrez interactivo con reglas de alfil y torre.
2. Tabla de verdad 2D de 6 variables.
3. Simulador de la placa con teclado hexadecimal, 7 segmentos activos a nivel bajo, LED y pulsadores activos a nivel bajo.
4. `f_div`: divisor de frecuencia con cálculo de la frecuencia de salida y cronograma.
5. Ejemplos dorados: los sistemas `Nucli_P1`, calculadora `calc` y juego `jocDE2`, con sus cronogramas de la guía como casos de prueba.

#### F. Criterios de aceptación

1. Para `Nucli_P1`, el circuito de puertas dibujado por el alumno coincide con la especificación de ajedrez en las 8 192 combinaciones, o se da un contraejemplo.
2. Una jugada concreta (p. ej. alfil de (2,3) a (4,6)) da `MOK = 0` y se ve sobre el tablero.
3. La calculadora da `5 × 3 = 15` con la secuencia `*`, `5`, `3`, `#`, y los displays muestran lo que pide la guía.
4. El juego indica menor, acertado o mayor con el patrón de LED de la guía.
5. Nada de esta sección genera ni valida VHDL.

---

## 23. Relación con otros laboratorios

Alineación del 2026-10-01 con `MATH_LAB.md` v2, `SIGNALS_LAB.md`, `CIRCUITS_LAB.md` y el futuro laboratorio aeroespacial. **No cambia ninguna decisión D1 a D16** (D17 a D19 se añaden y quedan decididas el 2026-10-01; D12 se cierra como «sin catalán») ni renumera secciones: todas las citas de otros documentos a §4.5, §11.3, §12, §13, §15.2, §15.3, §22.6 y §22.8, y a DL-3, DL-11 y DL-20, siguen siendo válidas. Convenciones de lectura: «`Dn`» sin prefijo es de este documento (D12 aquí es el catalán, decidido que no; `MATH_LAB` D12 y `SIGNALS_LAB` D12 son otras decisiones); las fases son `DL-n`; los ejercicios de este laboratorio usarán ids estables `DD-<área>-<nn>`, nunca reutilizados, como `CI-` y `ES-` en los otros.

### 23.1 Regla general y mapa de frontera

Regla de `MATH_LAB.md` §16 y `SIGNALS_LAB.md` §3.1: lo que es **fórmula cerrada con pasos** lo calcula `MATH_LAB`; lo que es **medida, diseño numérico, simulación o gráfica interactiva** es del laboratorio de aplicación. Aquí, la aplicación es **todo lo que es lógica discreta (0, 1, X, Z) y su temporización**.

| Tema | Dueño | Qué hace este laboratorio |
|---|---|---|
| Álgebra de Boole, tabla de verdad, Karnaugh, QM, BDD/SAT, síntesis, `BoolExpr` | **Digital** | Todo (§4, §5). Se registra como segundo camino de la lógica proposicional de `MATH_LAB` §4.8 |
| Lógica proposicional con cuantificadores, conjuntos, inducción | `MATH_LAB` §4.8 | Nada |
| Conversión de bases 2–36, aritmética por columnas, máscaras, IPv4 | `MATH_LAB` §4.0 | Presenta en bits y agrupa en 3/4; no reimplementa |
| Complemento a 1/2, exceso K, banderas C/V/N/Z, Gray, BCD, Booth, coma fija, **IEEE 754**, ASCII, códigos de línea | **Digital** (§10) | Todo. `MATH_LAB` §17 deja el IEEE 754 fuera |
| GF(2), GF(2ᵐ), códigos lineales, CRC, Hamming, paridad 2D, checksum, Shamir | `MATH_LAB` §4.9, §4.10 (ML-17) | Solo la **realización hardware** y el segundo camino cruzado (§22.7) |
| Simulación lógica, formas de onda lógicas, analizador lógico, riesgos, camino crítico, setup/hold | **Digital** (§7) | Todo |
| Familias lógicas, VTC, márgenes de ruido, potencia, colector abierto | **Digital** (§22.3 E) | Tabla de familias y ejercicios; el MOSFET como circuito es de `CIRCUITS_LAB` §9 |
| Simulación de circuitos analógicos, MNA, SPICE, instrumentos | `CIRCUITS_LAB` | Nada; el analizador lógico se ofrece como instrumento por datos (§23.2) |
| ADC/DAC: circuito, INL/DNL, ENOB | `CIRCUITS_LAB` §10.15 | Solo el lado digital (SAR, codificador, códigos, cronograma) |
| Cuantización: teoría, SQNR medido, visor | `SIGNALS_LAB` §16; fórmula en `MATH_LAB` §8.2 I | Ruido de cuantización en hardware y desbordamiento |
| Diseño de filtros FIR/IIR, LMS teórico, constelaciones y espectros | `SIGNALS_LAB`, `MATH_LAB`, `comms/` | Realización en coma fija, coste en puertas (DL-20) |
| Fiabilidad (λ, MTBF, serie y paralelo, Arrhenius) | `CIRCUITS_LAB` §12.11 (`CI-PW-25`); `MATH_LAB` la deja fuera | Solo MTBF de **metaestabilidad** del sincronizador y cobertura de fallos (§7.5, §7.6) |
| Aeroespacial / satcom | Futuro laboratorio | **No afecta**: no hay dependencia en ningún sentido. Si el aeroespacial usa codificación de canal, la toma de `MATH_LAB` y, si hace falta hardware, de la realización de §22.7 |

### 23.2 Lógica digital y circuitos analógicos: frontera y puente

1. **Lógica digital no entra en el editor de circuitos.** Las puertas, biestables, buses lógicos y FSM se dibujan y simulan **aquí**, con el motor de §7. El editor de `CIRCUITS_LAB` §7 no coloca puertas lógicas como elementos de simulación digital.
2. **«Digital-interfaz» de `CIRCUITS_LAB` §7.3** (comparador con histéresis, ADC/DAC ideal, conversión de nivel) son **bloques comportamentales analógicos**. Pueden usar la tabla de familias lógicas de §22.3 E (V_IL, V_IH, V_OL, V_OH) para fijar sus umbrales; esa tabla es el contrato de **datos** entre los dos laboratorios.
3. **No hay cosimulación mixta** (analógico y lógico en un mismo reloj de simulación) en ninguno de los dos documentos. Se declara como límite (§20.2). Lo que sí se ofrece, por datos y sin acoplar motores: (a) una traza analógica del laboratorio virtual se **digitaliza** con los umbrales de una familia y se muestra en el analizador lógico (puente en `application/`, como ya prevé `CIRCUITS_LAB` §8.10); (b) una forma de onda lógica de este laboratorio se exporta como **estímulo** de un `StimulusSpec` del laboratorio virtual.
4. **`ui/logic_analyzer.py`** es de este laboratorio y `CIRCUITS_LAB` lo enlaza como instrumento. **`ui/waveform.py`** sigue siendo el visor de carriles lógicos (§7.4); lo analógico va en `WaveformPlot` y en el núcleo de gráficas compartido. La frase de `CIRCUITS_LAB` §3.8 que dice que `waveform.py` «se generaliza» debe leerse como «se reutiliza su patrón» (ver lista de cambios en otros documentos).
5. **Propiedad de los ejercicios de frontera:** inversor CMOS (VTC, márgenes, retardo, potencia) y colector abierto con pull-up, aquí; punto de trabajo del MOSFET, MOS como interruptor y comparadores con op-amp, en circuitos.

### 23.3 Reparto de implementación con `MATH_LAB` y regla de dependencia

- **Dirección de dependencia:** `digital → math` (motor de pasos y contrato de `MATH_LAB.md` §5.9, trazas E0, verificadores). **`math` nunca importa `digital`.** Por eso este laboratorio **registra** su motor (`boolean/equiv.py`, tabla exhaustiva) como **plug-in de verificación** de la lógica proposicional de `MATH_LAB` §4.8, y registra el LFSR como segundo camino del CRC de §4.10; no al revés.
- **`BoolExpr` no sustituye** a las expresiones simbólicas de `MATH_LAB` §5.1 (una variable real, racionales multivariable): es un AST propio de álgebra de Boole, con su catálogo de leyes (Anexo A). No hay que unificar los dos árboles; sí el formato de traza y los sellos (§11.4).
- **Bases y aritmética binaria:** el conversor y la aritmética por columnas se piden a `MATH_LAB` §4.0 por su punto de entrada de §5.9; `calc/radix.py` queda como presentación en bits. `calc/twos.py`, `gray.py`, `bcd.py`, `arith.py`, `ieee754.py`, `fixedpoint.py` son propias. `calc/parity.py` es el generador de paridad como función de bits; `calc/hamming.py` y `calc/crc.py` delegan en `MATH_LAB` y añaden la vista de hardware.
- **`MATH_LAB` §4.0 y §16.1** listan complemento a 2, rango y desbordamiento tanto en su bloque 0 como bajo «DIGITAL_DESIGN_LAB (existente)»: la implementación única de complemento a 2 con banderas es la de aquí; `MATH_LAB` conserva conversión de bases, máscaras e IPv4 (cambio pedido en §23.8).

### 23.4 Componentes compartidos de UI e infraestructura

| Componente | Quién lo define | Clientes | Regla |
|---|---|---|---|
| **Núcleo de lienzo** (`ui/canvas/`: viewport, selección, pila de comandos, enrutado ortogonal, índice espacial, minimapa, símbolos ANSI/IEC, motor de reglas DRC) | El primero que se construya entre DL-3 y CI-4; el otro lo importa | `digital_editor`, editor de esquemas, diagrama de bloques de `SIGNALS_LAB` §7.8 | Neutral: sin puertas ni resistencias. Prueba de contrato común. Las reglas DRC (§6.4) y ERC (`CIRCUITS_LAB` §7.8) son datos sobre el mismo motor |
| **Núcleo de gráficas** (`ui/plot/`) | `SIGNALS_LAB` §3.2 | `waveform.py` (cursores, zoom, medidas), `WaveformPlot`, visores de señales | `waveform.py` conserva su dibujo lógico |
| **Pipeline de imagen** (`infrastructure/vision.py`, cliente de Ollama con `images`, `ollama_vision_model`) | Este laboratorio (DL-11) | `CIRCUITS_LAB` §7.1; `SIGNALS_LAB` D12 tras DL-11 | Un único ajuste por equipo; revisión humana obligatoria |
| **Ejecución segura de binarios externos** (descubrimiento, lista blanca, sin shell, directorio temporal) | El primero que lo necesite (`ngspice` o `abc`/`espresso`) | `infrastructure/ngspice.py`, `infrastructure/abc.py` | Un solo auxiliar, misma política que §17 |
| **Plantilla única de ejercicio** (§22.8) y registro de tipos de pregunta | `MATH_LAB` §7 / este | «circuito digital», «señales», tipos de circuitos | Un registro; cada laboratorio añade su tipo, el corrector y la maestría no cambian |
| **Fin de línea del dorado E0** | Primera fase que lo toque | DL-0, CI-0 | Un único arreglo |

### 23.5 Paquetes, rutas y renombrado (CI-R)

- **Qué sale y a dónde.** Según `CIRCUITS_LAB.md` §3.8, salen a este laboratorio `domain/engineering/digital/`, `digital_circuit.py`, `application/digital_service.py`, `application/digital_design.py`, `ui/digital_editor.py`, `ui/logic_analyzer.py` y la ruta `engineering/digital-logic`. `domain/execution/digital.py` **se queda** en `domain/execution` (paquete transversal de explicación).
- **Destino ✅ DECIDIDO (D17):** `domain/digital/` como paquete hermano de `domain/circuits/` y `domain/signals/`, con subpaquetes `boolean/`, `seq/`, `calc/`, `digital2/` y, para el código certificado, `certified/` (o conservar el nombre `digital/` interno). Los nombres `domain/engineering/digital/boolean/...` de §3 y del Anexo C se leen ya como `domain/digital/boolean/...`. El motor certificado se mueve aparte, en un paso posterior a CI-R.
- **Orden (compatible con la regla de oro de `CIRCUITS_LAB` §3.7.3: «tests en verde antes y después»).** (1) CI-R.0 a CI-R.2 sin tocar nada digital, con el manifiesto de hashes del motor certificado. (2) **DL-0 puede empezar sin esperar a CI-R** creando solo código **nuevo** en `domain/digital/` (fuera de `engineering`), de modo que CI-R no tiene que mover nada suyo. (3) El codemod de CI-R.4 actualiza los `import` del motor certificado. (4) El **movimiento físico** de `digital/` a `domain/digital/` es un paso aparte, posterior a CI-R, con el manifiesto comprobado antes y después. Mientras, el código nuevo importa el certificado por su ruta de entonces.
- **Pruebas.** Las pruebas `test_dl*` usan el auxiliar `tests/_paths.py` de CI-R.2, nunca rutas físicas. Los tres tests que hoy comparan `git diff 0cf3554 -- .../digital` pasan al manifiesto.
- **Lo que no se renombra** (`CIRCUITS_LAB.md` §3.7.2): etiquetas `digital-circuit/1`, `digital-design/1` y `digital-trace/1`, ids de ruta, tablas SQLite, ficheros `test_f8q*` y prefijos de errores. Los nuevos códigos de error van a `docs/specs/ERROR-CODES.md` con el prefijo de área vigente.

### 23.6 Ruta de UI y rótulo visible

Hoy el área `engineering` se rotula «Circuitos electrónicos» (`ui/routes.py`, `ui/main_window.py`) y contiene `engineering/digital-logic` («Lógica digital»). Se mantiene el **id estable** `engineering/digital-logic` (contrato de navegación, `CIRCUITS_LAB` §3.7.2). ✅ **DECIDIDO (D18):** el **rótulo visible** pasa a ser «Diseño digital» (el área `engineering` conserva «Circuitos electrónicos»), sin cambiar el id `engineering/digital-logic`; la página puede ofrecerse también desde un grupo común de laboratorios junto a Matemáticas, Señales y Circuitos. `CIRCUITS_LAB` ya prevé que las rutas antiguas sigan siendo atajos hacia las nuevas (D3).

### 23.7 Dependencias entre fases

| Fase de este documento | Depende además de | Motivo |
|---|---|---|
| DL-0 | CI-R.2 (solo si toca el motor certificado o sus pruebas) | Manifiesto de hashes y `tests/_paths.py` |
| DL-1, DL-7 | **ML-12** de `MATH_LAB` | Motor de pasos, contrato §5.9, sellos |
| DL-3 | CI-4 (coordinación) | Núcleo de lienzo compartido (§23.4) |
| DL-6 | ML-12 y **ML-17** | Bases, GF(2), CRC y Hamming delegados |
| DL-15 | — (usa `mna/mosfet.py` ya existente) | VTC con interfaz pública |
| DL-20 | **SG-9** de `SIGNALS_LAB` | `FilterDesign` e IIR |
| DL-22 | DL-8, ML-17 | LFSR y matemática de códigos |
| DL-11 | — | Entrega el pipeline que usarán CI-4 (imagen de esquemas) y `SIGNALS_LAB` D12 |

### 23.8 Puntos que los otros documentos deben recoger

Este documento ya asume: `MATH_LAB` §4.0 y §16.1 sin complemento a 2 duplicado; `CIRCUITS_LAB` §3.8 con `waveform.py` reutilizado y no «generalizado», y con el núcleo de lienzo definido en su §3; la cita de ADC en `SIGNALS_LAB` §23.4 como §10.15 / BL-AN-14; y que los tres citen esta §23. Hasta que se actualicen, en caso de duda manda el reparto de §23.1.

### 23.9 Decisiones nuevas propuestas (no sustituyen a D1 a D16)

| # | Decisión | Propuesta | Estado |
|---|---|---|---|
| D17 | Destino físico del paquete digital y orden respecto a CI-R | `domain/digital/` nuevo desde DL-0; movimiento del certificado en paso aparte tras CI-R (§23.5) | ✅ **DECIDIDO** |
| D18 | Rótulo visible y área de la página «Lógica digital» | «Diseño digital», id estable `engineering/digital-logic` (§23.6) | ✅ **DECIDIDO** |
| D19 | Quién construye primero el núcleo de lienzo | **`CIRCUITS_LAB` CI-4 lo define primero; este laboratorio (DL-3) lo importa** (§23.4) | ✅ **DECIDIDO** |

---

*Fin del documento. Estado: decididas D1, D2, D3, D4, D8, D9, D11, D12, D13, D14, D16, D17, D18 y D19; **no se ha iniciado ninguna implementación**. Siguiente paso: indicar «arranca DL-0», que empieza por la tabla de verdad y la reducción algebraica paso a paso (DL-0 y DL-1). Nuevas fases DL-14 a DL-23 en §22.10. Pendiente del usuario: decidir D5, D6 (con recomendación), D7 y D15, instalar Ollama y pegar la salida de `nvidia-smi` y `ollama list` para cerrar D10.*

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


### Capacidades transversales adicionales — contrato académico

Todos los laboratorios deben integrarse con las siguientes capacidades comunes, sin duplicar su infraestructura por dominio:

#### Incertidumbre y error
- incertidumbre absoluta y relativa;
- propagación de incertidumbre a través de expresiones y cadenas de cálculo;
- separación entre error sistemático y aleatorio cuando proceda;
- sensibilidad respecto a parámetros;
- intervalos y tolerancias cuando sean aplicables;
- Monte Carlo reproducible cuando el problema lo requiera;
- comparación entre incertidumbre experimental, tolerancia y discrepancia teórica.

#### Validación de entradas
Antes de resolver, validar unidades, dimensiones, dominios matemáticos, rangos físicos, parámetros incompatibles, condiciones iniciales e hipótesis contradictorias. Los errores de entrada deben identificarse antes de presentar un resultado como válido.

#### Experimentos reproducibles y datos
Una práctica puede conservar configuración, versión del motor, parámetros, semilla aleatoria, datos de entrada, datos crudos, procesamiento, resultados, incertidumbre y conclusión. Debe ser posible reproducir una ejecución cuando el modelo lo permita.

#### Gráficas académicas
Las gráficas forman parte del resultado estructurado y conservan datos, ejes, unidades, escalas, procedencia y método de generación. El catálogo común debe permitir reutilizar representaciones entre laboratorios sin imponer una interfaz concreta.

#### Intentos, pistas y aprendizaje
Un ejercicio puede conservar múltiples intentos del estudiante. El sistema debe registrar el primer error detectado, correcciones y ayudas utilizadas. Las pistas pueden progresar desde una indicación conceptual hasta el siguiente paso y la solución completa, sin sustituir el razonamiento del estudiante.

#### Comparación de métodos
Cuando existan varios métodos válidos, el resultado puede comparar método analítico, simbólico, numérico, aproximado o simulado, mostrando diferencias, precisión, coste y condiciones de validez.

#### Instrumentación y medición
Los laboratorios que trabajen con medidas deben poder consumir una capa común de instrumentos virtuales y datos de medición. El instrumento, su configuración y la incertidumbre asociada forman parte de la procedencia del dato.

#### Informe reproducible
Una práctica completa debe poder transformarse posteriormente en un informe con enunciado, datos, hipótesis, procedimiento, cálculos, gráficas, mediciones, errores, incertidumbre, corrección y conclusión. La generación documental concreta queda fuera del diseño visual de este documento.


### Capacidades específicas adicionales — Digital Design Lab

- Los intentos deben poder conservar circuito, estímulos, tabla de verdad, trazas y resultado del corrector.
- La validación debe detectar anchuras incompatibles, señales sin fuente, conflictos de conducción, estados inválidos y condiciones de temporización fuera de especificación cuando el modelo las soporte.
- La comparación de métodos debe permitir contrastar tabla de verdad, minimización, simulación y HDL cuando estén disponibles.

## Catálogo maestro de cobertura

La cobertura de este laboratorio se audita también en `docs/labs/COVERAGE_CATALOG.md`. Ese catálogo fija el contrato común de familia temática, estados y criterio de completitud; documentar una capacidad no implica que esté implementada.
