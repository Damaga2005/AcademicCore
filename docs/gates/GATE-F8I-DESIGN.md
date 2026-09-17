# F8-I Design Audit — Nonlinear Circuits (DC Operating Point with BJT / Ebers-Moll Model)

> **Phase**: Audit and Design only. No implementation code written, no certified code modified, no migrations executed, no solver created, no implementation tests created, no push, no pull, no reset, no clean, `.stfolder/` untouched. Verdict at §27.

---

## 1. Executive Summary

Phase **F8-I** represents the next conceptual and mathematical leap in AcademicCore's electronics engineering domain: the extension of the nonlinear DC operating-point analysis from two-terminal scalar semiconductors (Shockley diode, certified in F8-H) to **three-terminal active semiconductor devices** through the **Bipolar Junction Transistor (BJT) under the classic Ebers-Moll model (NPN and PNP)**.

Following the certification of F8-A through F8-H (69/69 F8-H tests passing, 0 skip, 0 fail; commit `f857565`), this design audit systematically evaluates the existing architecture across `src/academic_core/domain/engineering/`. The audit finds that AcademicCore's existing infrastructure:
1. Already declares `Q` with pins `("C", "B", "E")` in `COMPONENT_PINS` (`circuit.py`) and matches `Q\d+` in reference regex since Phase 6.
2. Reuses the linear MNA unknown vector layout bit-for-bit without adding auxiliary current variables (the BJT terminal currents enter nodal KCL rows directly).
3. Reuses the high-precision linear solver (`math.linsolve`) with `DecimalComplex` (zero imaginary part) under explicit 50-to-80 digit contexts.
4. Reuses the damped Newton-Raphson iteration architecture with geometric bisection backtracking established in F8-H `nonlinear.py`.
5. Requires no architectural redesign or secondary solver.

Scope is strictly delimited: **DC operating point of BJT networks under the Ebers-Moll model (NPN and PNP), mixing with all prior certified components $\{R, L, C, V, I, E, G, H, F, O, T, D\}$; no AC small-signal, no transient ODE integration, no MOSFET/JFET, no temperature sweeps, no charge storage or junction capacitances**.

**Verdict**: **`F8-I DESIGN READY`** (§27).

---

## 2. Estado Git

- **Branch**: `main`
- **Head Commit**: `f857565` (*feat(engineering): certify F8-H nonlinear DC operating point with Shockley diode and ngspice-47 validation*)
- **Status**: Ahead of `origin/main` by 2 commits (`7e85834` F8-G, `f857565` F8-H).
- **Working Tree**: Clean with respect to tracked files. Untracked files present: `.stfolder/`, `docs/gates/GATE-F8D*.md`, `full_result.log`.
- **Integrity**: Zero files outside `docs/gates/GATE-F8I-DESIGN.md` modified during this phase.

---

## 3. Arquitectura Actual Relevante

AcademicCore proporciona una arquitectura modular y determinista en `src/academic_core/domain/engineering/`:

1. **Modelo Canónico de Circuito (`circuit.py`)**:
   - `Component(ref, type, value, pins, parameters, metadata)` representa componentes inmutables a nivel de atributos.
   - `COMPONENT_PINS["Q"] = ("C", "B", "E")`: colector, base y emisor son nets explícitos en `pins: dict[str, str]`.
   - `models.bjt()` en `models.py` existe como placeholder con metadatos.
   - En `mna/problem.py`, `SUPPORTED_TYPES = frozenset({"R", "V", "I", "E", "G", "H", "F", "O", "T"})` rechaza formalmente `Q` como no soportado hasta la habilitación explícita por flag.

2. **Unidades y Magnitudes Físicas (`units.py`)**:
   - `Quantity(Decimal, Unit)` garantiza evaluación exacta sin números en coma flotante (`float`).
   - Dimensiones estándar: `CURRENT` (A), `VOLTAGE` (V), `DIMENSIONLESS` (adimensional).
   - Barrera estricta: parámetros no finitos, negativos o de dimensión incorrecta lanzan `InvalidCircuitError`.

3. **Núcleo Lineal MNA DC (`mna/problem.py`, `mna/solver.py`)**:
   - Vector de incógnitas canónico: tensiones de nudo no-tierra $\mathbf{v}$ ordenadas alfabéticamente, seguidas de corrientes auxiliares $\mathbf{i}_{aux}$ de ramas de tensión $\{V, E, H, O, T\}$.
   - Sin fila/columna de tierra. La referencia $V_0 = 0$ es invariante.
   - Solucionador exacto sobre `fractions.Fraction` (`solve_exact`) para circuitos lineales.

4. **Álgebra Lineal de Alta Precisión (`math/linsolve/`)**:
   - Autoridad única: `ComplexLinearProblem.from_sequences` + `solve(problem, mode)`.
   - Análisis de rango de Rouché-Capelli, pivoteo con umbrales rigurosos, detección de error hacia atrás (`BE_TOL = 1E-30`).
   - Soporte nativo para `NumericMode.HIGH_PRECISION` con `DecimalComplex`.

5. **Motor No Lineal DC (`mna/nonlinear.py`, `mna/diode.py`)**:
   - Subred lineal $(A_0, b_0)$ extraída mediante `build_mna_problem(circuit, allow_diodes=True)`.
   - Residual acoplado: $F(x) = A_0 x - b_0 + D(x) = 0$.
   - Jacobiano analítico: $J(x) = A_0 + \sum J_{elem}(x)$.
   - Paso de Newton: $J(x_k) \Delta x = -F(x_k)$ resuelto por `math.linsolve`.
   - Búsqueda lineal amortiguada con bisección geométrica ($\alpha \in \{1, 1/2, \dots, 2^{-10}\}$).
   - Criterio de convergencia por bloques de magnitud física (KCL $\le 10^{-12}$ A, restricciones $\le 10^{-9}$ V).

---

## 4. Objetivo Exacto de F8-I

### 4.1 Evaluación Comparativa de Candidatas

Siguiendo el mandato de auditoría, se evaluaron formalmente cuatro candidatas:

1. **Candidata 1: Punto de Operación DC con BJT bajo Modelo Ebers-Moll (NPN y PNP)**:
   - *Continuidad matemática*: Transición natural de 1D escalar (diodo de 2 terminales) a 2D vectorial acoplado (transistor de 3 terminales).
   - *Reutilización*: Reutiliza al 100% la infraestructura de Newton amortiguado, `math.linsolve` y MNA de F8-H.
   - *Valor académico*: El transistor bipolar es el dispositivo semiconductor activo fundamental en la formación en ingeniería electrónica.
   - *Generalidad*: Funciona en emisor común, base común, colector común, pares diferenciales, espejos de corriente, Darlingtons.
   - *Verificabilidad*: Comprobación analítica exacta y validación cruzada con `.OP` de ngspice 47.
   - *Ausencia de rediseño*: `Q` ya está declarado en `circuit.py`. No altera el vector de incógnitas MNA.

2. **Candidata 2: Análisis AC de Pequeña Señal de Circuitos No Lineales**:
   - Conecta F8-D y F8-H linealizando el diodo en el punto Q. Sin embargo, sin BJT, se limita a circuitos con diodos (detectores/limitadores), careciendo de valor para amplificadores de transistores.

3. **Candidata 3: Análisis Transitorio en el Dominio del Tiempo (Integración ODE)**:
   - Requiere esquemas de integración (Backward Euler/Trapezoidal), estimación de paso temporal y estados reactivos dinámicos en $L$ y $C$. Salto discontinuo de complejidad excesiva.

4. **Candidata 4: Barrido Paramétrico DC (DC Sweep)**:
   - Es un bucle exterior sobre el solver DC existente, no una extensión arquitectónica o componente físico nuevo.

### 4.2 Selección Justificada
Se selecciona de forma unánime y rigurosa la **Candidata 1: Punto de Operación DC con Transistores BJT bajo el Modelo Ebers-Moll (NPN y PNP)** como el objetivo normativo de F8-I.

---

## 5. Definición Formal del Dominio

- **Fenómeno Físico**: Transporte e inyección de portadores minoritarios en uniones p-n semiconductoras bipolares acopladas.
- **Régimen de Análisis**: DC Operating Point (Régimen Permanente de Corriente Continua, $\omega = 0$, $d/dt = 0$).
- **Variables**: Potenciales de nodo $V_C, V_B, V_E \in \mathbb{R}$ (voltios). Tensiones de unión $V_{BE}, V_{BC}$ (NPN) o $V_{EB}, V_{CB}$ (PNP). Corrientes terminales entrantes $I_C, I_B, I_E \in \mathbb{R}$ (amperios).
- **Incógnitas**: El BJT no añade incógnitas auxiliares. Las incógnitas son estrictamente los potenciales de nudo no-tierra y las corrientes auxiliares de ramas de tensión lineales.
- **Restricciones y Contorno**: Referencia fija de tierra en $V_0 = 0$. Invarianza total ante desplazamiento de potencial.
- **Unidades**: Parámetros estrictamente encapsulados en `Quantity`: corriente en `A`, tensión en `V`, factores en `DIMENSIONLESS`.
- **Convenciones**: Signo pasivo (corrientes entrantes al dispositivo positivas, $I_C + I_B + I_E \equiv 0$).
- **Estados Válidos**: Corte, Activa Directa, Activa Inversa, Saturación.
- **Estados Inválidos**: Terminales en cortocircuito directo entre sí cuando impongan degeneración inadmisible sin resistencia, o parámetros no positivos / no finitos.
- **Singularidades y Degeneraciones**: Base flotante o circuito sin camino DC a tierra; diagnosticados por análisis de rango como `SINGULAR_JACOBIAN`.
- **Clasificación**:
  - **SUPPORTED**: BJT NPN y PNP bajo Ebers-Moll acoplado con $\{R, V, I, E, G, H, F, O, T, D\}$ en cualquier topología; múltiples BJT hasta $N=64$.
  - **LIMITED**: Parámetros no serializados en texto `.cir` (limitación AUDIT-002); sin efecto Early ($V_A = \infty$).
  - **UNSUPPORTED**: MOSFETs, JFETs, régimen transitorio $d/dt \neq 0$, fuentes $H/F$ sensando patillas de BJT.

---

## 6. Modelo Físico y Matemático Completo

### 6.1 Ecuaciones de Ebers-Moll (Formulación de Transporte)

#### 6.1.1 Transistor NPN
Tensiones de control:
$$V_{BE} = V_B - V_E, \quad V_{BC} = V_B - V_C$$

Corrientes de diodo de inyección:
$$I_F = I_S \left( \exp\left( \frac{V_{BE}}{n_F V_t} \right) - 1 \right)$$
$$I_R = I_S \left( \exp\left( \frac{V_{BC}}{n_R V_t} \right) - 1 \right)$$

Corrientes entrantes a los terminales:
$$I_C = I_F - \left(1 + \frac{1}{\beta_R}\right) I_R = I_F - \frac{I_R}{\alpha_R}$$
$$I_B = \frac{I_F}{\beta_F} + \frac{I_R}{\beta_R}$$
$$I_E = -\left(1 + \frac{1}{\beta_F}\right) I_F + I_R = -\frac{I_F}{\alpha_F} + I_R$$
con:
$$\alpha_F = \frac{\beta_F}{\beta_F + 1}, \quad \alpha_R = \frac{\beta_R}{\beta_R + 1}$$
Conservación exacta de carga en el componente:
$$I_C + I_B + I_E \equiv 0 \quad \forall (V_{BE}, V_{BC})$$

#### 6.1.2 Transistor PNP
Tensiones de control:
$$V_{EB} = V_E - V_B = -V_{BE}, \quad V_{CB} = V_C - V_B = -V_{BC}$$

Corrientes de diodo de inyección:
$$I_F = I_S \left( \exp\left( \frac{V_{EB}}{n_F V_t} \right) - 1 \right)$$
$$I_R = I_S \left( \exp\left( \frac{V_{CB}}{n_R V_t} \right) - 1 \right)$$

Corrientes entrantes a los terminales:
$$I_C = -I_F + \frac{I_R}{\alpha_R}$$
$$I_B = -\frac{I_F}{\beta_F} - \frac{I_R}{\beta_R}$$
$$I_E = \frac{I_F}{\alpha_F} - I_R$$
Se cumple idénticamente: $I_C + I_B + I_E \equiv 0$.

### 6.2 Conductancias Analíticas y Matriz Jacobiana de $3 \times 3$

Conductancias dinámicas de unión (en siemens, S):
$$g_F = \frac{\partial I_F}{\partial V_{BE}} = \frac{I_S}{n_F V_t} \exp\left( \frac{V_{BE}}{n_F V_t} \right)$$
$$g_R = \frac{\partial I_R}{\partial V_{BC}} = \frac{I_S}{n_R V_t} \exp\left( \frac{V_{BC}}{n_R V_t} \right)$$

Para NPN, el bloque Jacobiano $J_{BJT}$ de derivadas respecto a $(V_C, V_B, V_E)$ es:
$$J_{BJT} = \begin{pmatrix}
+\frac{g_R}{\alpha_R} & g_F - \frac{g_R}{\alpha_R} & -g_F \\
-\frac{g_R}{\beta_R} & \frac{g_F}{\beta_F} + \frac{g_R}{\beta_R} & -\frac{g_F}{\beta_F} \\
-g_R & -\frac{g_F}{\alpha_F} + g_R & +\frac{g_F}{\alpha_F}
\end{pmatrix}$$

Propiedades algebraicas verificadas:
- Cada fila suma exactamente 0: $\sum_j J_{ij} = 0$ (independencia del potencial absoluto).
- Cada columna suma exactamente 0: $\sum_i J_{ij} = 0$ (conservación estricta de KCL en el paso diferencial).

---

## 7. Solver Strategy

1. **Reutilización Estricta de MNA**:
   - `build_mna_problem(circuit, allow_diodes=True, allow_bjts=True)` construye la matriz lineal $(A_0, b_0)$ con todos los elementos no semiconductores.
   - El vector de incógnitas no crece con los BJTs.
2. **Residual No Lineal Acoplado**:
   $$F(x) = A_0 x - b_0 + D(x) + Q(x)$$
   donde $Q(x)$ suma $I_C, I_B, I_E$ a las filas KCL de los nodos correspondientes.
3. **Jacobiano Global**:
   $$J(x) = A_0 + \sum J_d(x) + \sum J_q(x)$$
   estampando el bloque $3 \times 3$ de cada BJT.
4. **Paso de Newton-Raphson con Bisección**:
   - $J(x_k) \Delta x = -F(x_k)$ resuelto mediante `math.linsolve` en modo `HIGH_PRECISION`.
   - Factor de amortiguamiento $\alpha \in \{1, 1/2, \dots, 2^{-10}\}$ con criterio de descenso estricto de norma residual $\|F(x_{k+1})\| < \|F(x_k)\|$.

---

## 8. Numerical Strategy

- **Aritmética Decimal de 50 a 80 Dígitos**:
  - Evaluación matemática bajo `decimal.Decimal` con `trig.make_context(prec=80)`.
  - Cero contaminación por `float`.
- **Protección Frente a Desbordamiento**:
  - Atrapamiento de `decimal.Overflow` e `InvalidOperation` retornando `Decimal('Infinity')`.
  - Transición controlada a `NonlinearStatus.DIVERGED` con causa `EVALUATION_OVERFLOW` si la exponencial desborda.
- **Tolerancias de Convergencia**:
  - Residuo KCL: $\|F_{KCL}\|_\infty \le 10^{-12}\text{ A} + 10^{-9} \max(1, \|x\|_\infty)$.
  - Restricción auxiliar: $\|F_{aux}\|_\infty \le 10^{-9}\text{ V} + 10^{-9} \max(1, \|x\|_\infty)$.
  - Paso de actualización: $\|\alpha \Delta x\|_\infty \le 10^{-12} (1 + \|x\|_\infty)$.

---

## 9. Estados y Errores Formales

- **`CONVERGED`**: Convergencia matemática y física alcanzada dentro del límite de iteraciones.
- **`MAX_ITERATIONS`**: Se alcanzaron 50 iteraciones sin cumplir las tolerancias de residual.
- **`DIVERGED`**: Residual diverge a $\ge 10^{20}$, estancamiento de bisección o desbordamiento numérico.
- **`SINGULAR_JACOBIAN`**: Rango deficiente en $J(x)$ por nodo flotante o falta de camino a tierra.
- **`INVALID`**: Parámetros de componente no físicos, no positivos o no dimensionados.
- **`UNSUPPORTED`**: Elementos fuera de alcance ($L/C$ en DC puro, semiconductores no modelados).

---

## 10. Interacción con Componentes Existentes (F8-A..F8-H)

- **$R, V, I$**: Soportado 100%. Polarización básica y cargas.
- **$E, G$**: Soportado 100%. Control por tensión o transconductancia.
- **$H, F$**: Soportado en ramas lineales. **Loudly INVALID** si sensa patillas de BJT.
- **$O$**: Soportado 100%. Reguladores y amplificadores operacionales ideales con transistor.
- **$T$**: Soportado 100%. Acoplamiento de etapas con transformador ideal.
- **$D$**: Soportado 100%. Redes mixtas diodo-transistor acopladas en el mismo bucle Newton.
- **Múltiples BJTs**: Soportado 100%. Pares diferenciales, espejos de corriente, Darlingtons hasta $N=64$.
- **$L, C$**: **UNSUPPORTED en DC**. Sigue el contrato formal de F8-B/F8-H.

---

## 11. Generality Strategy

- Topologías arbitrarias: serie, paralelo, puente, escalera, malla, estrella, multigrafo, nodos de alto grado, circuitos conectados y flotantes.
- Escalamiento probado formalmente en $N = 1, 2, 4, 8, 16, 32, 64$ transistores.
- Prohibición de optimizaciones que dependan de estructuras canónicas particulares.

---

## 12. Oráculo Externo (ngspice 47)

- Validación frente a binario ngspice 47 (`ngspice_con.exe`).
- Generación de deck canónico con modelo `.model QMOD NPN (IS=... BF=... BR=... NF=... NR=...)` y directiva `.op`.
- Tolerancia máxima admisible: error relativo $< 10^{-4}$ (100 ppm) en tensiones de nodo y corrientes de rama.
- Autoridad primaria: deducción analítica y leyes de conservación (KCL/KVL/Tellegen).

---

## 13. Política de Unidades y Parámetros

Parámetros requeridos en `Component.parameters` como instancias `Quantity`:
- `"polarity"`: `"NPN"` o `"PNP"` (cadena).
- `"Is"`: Corriente de transporte de saturación (`CURRENT`, $> 0$, A).
- `"Bf"`: Ganancia directa de corriente (`DIMENSIONLESS`, $> 0$).
- `"Br"`: Ganancia inversa de corriente (`DIMENSIONLESS`, $> 0$).
- `"Nf"`: Factor de idealidad base-emisor (`DIMENSIONLESS`, $> 0$).
- `"Nr"`: Factor de idealidad base-colector (`DIMENSIONLESS`, $> 0$).
- `"Vt"`: Tensión térmica (`VOLTAGE`, $> 0$, V).

Sin valores mágicos por defecto. Validación estricta con `extract_bjt_params`.

---

## 14. Netlist, AST y Serialización

- Formato canónico `engcircuit/6.0`: `Q<ref> <node_C> <node_B> <node_E>`.
- Preserva determinismo de ordenación y roundtrip estructural.
- Parámetros avanzados no serializados en texto plano `.cir` (limitación documentada AUDIT-002).

---

## 15. Thevenin, Norton y Two-Port

- Circuitos que contengan componentes no lineales BJT producen formalmente `UNSUPPORTED` al solicitar reducción Thévenin/Norton lineal.
- Prohibido asumir linealidad donde no existe o emitir resistencias inventadas.

---

## 16. Potencia y Conservación de Energía

- Potencia del BJT: $P_{BJT} = V_{CE} I_C + V_{BE} I_B \ge 0$ en régimen activo disipativo.
- Teorema de Tellegen verificado rigurosamente en cada solve convergente: $\sum_b P_b \equiv 0$ con tolerancia $\le 10^{-12}\text{ W}$.

---

## 17. Seguridad del Dominio

- Dominio libre de subprocess, shell, eval, exec, compile, globals, locals, sockets o mutación externa.
- Verificación automática en test mediante escaneo de AST de Python.

---

## 18. Inmutabilidad y Proveniencia

- Objetos `Circuit` y `Component` inmutables durante el análisis.
- Provenance determinista con digest SHA-256 canónico libre de marcas temporales en la entrada del hash.

---

## 19. Rendimiento y Tripwires

- Benchmarks proyectados: $N=1 < 60\text{ ms}$, $N=16 < 1.5\text{ s}$, $N=32 < 5.0\text{ s}$, $N=64 < 20.0\text{ s}$.
- Tripwire absoluto: $\le 60\text{ s}$ para cualquier prueba de $N \le 64$.

---

## 20. Plan de Pruebas (`tests/test_f8i_nonlinear_bjt.py`)

Suite integral de $\ge 70$ pruebas:
- Física Ebers-Moll y derivadas analíticas vs. numéricas.
- Circuitos canónicos B1 a B15 (polarización fija, autopolarización, seguidor emisor, base común, PNP, espejo de corriente, par diferencial, Darlington, inversores, interacción con Op-Amp, Transformador, Diodo y fuentes dependientes).
- Escalamiento $N=1..64$.
- Modos de fallo deliberados (base flotante, singularidad, divergencia, parámetros no físicos).
- Validación cruzada con ngspice 47.
- Conservación KCL, KVL y Tellegen.
- Seguridad AST y determinismo de procedencia.

---

## 21. Plan de Regresión

- Cero regresiones demostrable: 100% de tests F8-A a F8-H en PASS (69/69 de F8-H conservados).
- `allow_bjts: bool = False` por defecto en MNA para blindar el contrato lineal previo.

---

## 22. Análisis de Riesgos

Se gestionan activamente 5 riesgos mayores (R1: convergencia en conmutación brusca; R2: desbordamiento exponencial; R3: Jacobiano singular por base abierta; R4: discrepancia de polaridades con ngspice; R5: lazos de control de fuentes dependientes). Todos con mitigación probada y ninguno bloqueante.

---

## 23. Decisiones Abiertas Resueltas (Q1–Q5)

- **Q1**: Formulación de Transporte SPICE ($I_S, \beta_F, \beta_R$) seleccionada por coherencia termodinámica y estándar industrial.
- **Q2**: Extensión modular de `nonlinear.py` con física en `mna/bjt.py`, evitando duplicación de solvers.
- **Q3**: Elementos $L/C$ en DC rechazados como `UNSUPPORTED` preservando el contrato formal F8-B/F8-H.
- **Q4**: Soporte conjunto de polaridades NPN y PNP desde F8-I.
- **Q5**: Preservación del formato `engcircuit/6.0` con parámetros como limitación de persistencia declarada.

---

## 24. Out of Scope

Excluidos formalmente: MOSFETs, JFETs, efecto Early, efectos capacitivos/dinámicos, régimen transitorio $d/dt \neq 0$, pequeña señal AC fasorial (objeto de F8-J).

---

## 25. Archivos Autorizados para la Futura Implementación

- **Nuevos**: `src/academic_core/domain/engineering/mna/bjt.py`, `tests/test_f8i_nonlinear_bjt.py`, `docs/gates/GATE-F8I.md`.
- **Modificaciones mínimas**: `src/academic_core/domain/engineering/mna/{problem,nonlinear,dependent,__init__}.py`.
- **Prohibido modificar**: Código previo de F8-A a F8-H fuera de `mna/`, `circuit.py`, `structural/`, o tests existentes.

---

## 26. Restricciones de Implementación

Aritmética estricta `Decimal`, determinismo alfabético en matrices y nodos, verificación obligatoria con ngspice 47 ($< 10^{-4}$), cero duplicación de solvers.

---

## 27. Veredicto Final

El diseño técnico y de auditoría para la fase F8-I satisface rigurosamente todas las condiciones matemáticas, físicas, arquitectónicas y normativas requeridas.

VEREDICTO FINAL:
**`F8-I DESIGN READY`**
