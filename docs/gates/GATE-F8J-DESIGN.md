# F8-J Design Audit — Small-Signal AC Analysis of Nonlinear Circuits

> **Phase**: F8-J Phase 0 (Audit and Technical Design only).
> **Production code modified**: NO.
> **Existing tests modified**: NO.
> **Git commit / push / pull / reset / clean**: NO.
> **Working directory**: `.stfolder/` untouched.
> **Status**: Design Complete & Mathematically Closed.

---

## 1. Objetivo & Visión General

La fase **F8-J** constituye el siguiente hito normativo en la evolución del motor de análisis de circuitos de **AcademicCore**: la formulación, diseño e implementación del **Análisis AC de Pequeña Señal (Small-Signal AC Analysis)** para circuitos analógicos no lineales que contienen semiconductores (diodos de unión Shockley y transistores bipolares de unión BJT bajo el modelo de transporte de Ebers-Moll, NPN y PNP), integrados armoniosamente con la totalidad de los componentes pasivos y activos certificados en fases anteriores:
$$\{R, L, C, V, I, E, G, H, F, O, T, D, Q\}$$

El objetivo primario de F8-J es conectar matemáticamente:
1. El **punto de operación no lineal en corriente continua (DC Operating Point)** resuelto y certificado en F8-H y F8-I (`solve_nonlinear_dc`), con
2. El **núcleo de análisis fasorial complejo en frecuencia** establecido en F8-D1, F8-D2 y F8-D3 (`DecimalComplex`, `ComplexLinearProblem`, `NumericMode.HIGH_PRECISION`, `ACOperatingPoint`, `NodePhasor`).

El principio fundacional de F8-J es la **linealización formal por series de Taylor de primer orden** de las características constitutivas de los dispositivos semiconductores alrededor del punto de polarización DC estático $\mathbf{x}_0$, desacoplando de manera estricta y transparente la resolución no lineal iterativa (Newton-Raphson amortiguado) de la resolución fasorial en régimen permanente sinusoidal (sistema lineal complejo $\mathbf{A}_{ac}(j\omega)\mathbf{x}_{ac} = \mathbf{b}_{ac}$).

---

## 2. Scope & Out of Scope

### 2.1 En Alcance (In Scope)
- **Punto de operación DC obligatorio**: Resolución preliminar del estado estático del circuito mediante `solve_nonlinear_dc(circuit)`.
- **Extracción de parámetros incrementales**:
  - Diodo Shockley ($D$): conductancia dinámica $g_d = \left.\frac{dI_D}{dV_D}\right|_{V_{D0}}$.
  - Transistor BJT ($Q$, NPN y PNP): matriz jacobiana analítica exacta $3\times 3$ de corrientes terminales respecto a tensiones terminales $\mathbf{J}_{BJT}(V_{C0}, V_{B0}, V_{E0})$ reutilizando `academic_core.domain.engineering.mna.bjt.bjt_jacobian`.
- **Estampado MNA complejo de componentes pasivos y fuentes en AC**:
  - Resistores: $Y_R = 1/R$.
  - Capacitores: $Y_C = j\omega C$, con $\omega = 2\pi f$, $f > 0$.
  - Inductores: $Y_L = \frac{1}{j\omega L} = -\frac{j}{\omega L}$ para $f > 0$.
  - Fuentes independientes:
    - Fuentes puras de polarización DC: anuladas en AC (fuente de tensión DC $\to$ cortocircuito incremental $\tilde{v}_s = 0$; fuente de corriente DC $\to$ circuito abierto incremental $\tilde{i}_s = 0$).
    - Fuentes de pequeña señal AC: inyección fasorial $\tilde{V}_{ac} = V_{peak} e^{j\phi}$ o $\tilde{I}_{ac} = I_{peak} e^{j\phi}$.
  - Fuentes dependientes lineales ($E, G, H, F$): idéntica contribución incremental que en F8-E/D3.
  - Amplificador operacional ideal ($O$): modelo nullor fasorial ($v_+ - v_- = 0$, corriente de salida $i_o$ auxiliar).
  - Transformador ideal ($T$): relación de transformación fasorial $v_2 = n v_1$, $i_1 + n i_2 = 0$.
- **Frecuencia única (Single Frequency)**: Especificación canónica $f > 0$ vía `Quantity` con dimensión `FREQUENCY` (Hz) y $\omega = 2\pi f$ (rad/s) vía `ACOperatingPoint`.
- **Resolución numérica de alta precisión**: Empleo exclusivo de `DecimalComplex` y `math.linsolve` (`NumericMode.HIGH_PRECISION`), garantizando cero `float` y cero `numpy`.
- **Observables físicos y procedencia**: Vector de fasores nodales $\tilde{V}_n$, fasores de corriente de rama $\tilde{I}_b$, tensiones de rama $\tilde{V}_b$, parámetros de pequeña señal reportados ($g_d$, $g_m, r_\pi, r_o, g_F, g_R$), balance de corrientes KCL complejo en todos los nodos y procedencia canónica con resumen criptográfico SHA-256 encadenado al digest del punto DC.
- **Validación cruzada**: Comparación rigurosa contra simulación `.AC` de ngspice 47.

### 2.2 Fuera de Alcance (Out of Scope)
- **Régimen transitorio en el dominio del tiempo**: Integración temporal de ecuaciones diferenciales ordinarias ($d/dt \neq 0$, Backward Euler, Trapezoidal).
- **Efectos reactivos internos de semiconductores**: Sin capacitancias de unión de deplexión ($C_{jd}$, $C_{je}$, $C_{jc}$) ni capacitancias de difusión ($\tau_F, \tau_R$) por defecto, a menos que se especifiquen explícitamente como componentes $C$ externos en el circuito.
- **Efectos parásitos de segundo orden**: Sin efecto Early ($V_A = \infty$), sin resistencias de contacto de base/colector/emisor ($r_b, r_c, r_e = 0$).
- **Dispositivos no certificados**: Prohibido MOSFET, JFET, IGBT, tiristores, túnel, diodos Zener en ruptura inversa.
- **Análisis de distorsión y gran señal**: Sin armónicos, sin intermodulación, sin balance armónico.
- **Ruido eléctrico**: Sin ruido térmico Johnson-Nyquist, sin ruido de granalla (shot noise), sin ruido $1/f$ (flicker).
- **Parámetros S de radiofrecuencia**: Sin líneas de transmisión distribuidas, matrices de dispersión o puertos adaptados a $50\,\Omega$.
- **Barridos estocásticos y térmicos**: Sin simulación Monte Carlo ni barridos de temperatura.

---

## 3. Arquitectura de Small-Signal AC

### 3.1 Flujo Operativo y Pipeline
El análisis de pequeña señal en F8-J se estructura en un pipeline unidireccional y desacoplado de 5 etapas:

```
                  Canonical Circuit & Frequency f
                                 │
                                 ▼
                     [Etapa 1: DC Operating Point]
                       solve_nonlinear_dc(circuit)
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
      NonlinearStatus != CONVERGED         NonlinearStatus == CONVERGED
      (DIVERGED, SINGULAR, etc.)                    x0 = [V0, Iaux0]
              │                                     │
              ▼                                     ▼
        Abort with AC Status               [Etapa 2: Linearization]
     (propagate in-band error)              Shockley: gd = dI/dV|x0
                                            BJT: J_BJT(x0) = [dI_term/dV_term]
                                                    │
                                                    ▼
                                    [Etapa 3: Small-Signal Complex MNA]
                                       Build ACOperatingPoint(f)
                                       AC sources active, DC sources zeroed
                                       Stamp R, L, C, D(gd), Q(J_BJT), E, G, H, F, O, T
                                       A_ac(jω) * x_ac = b_ac
                                                    │
                                                    ▼
                                    [Etapa 4: Complex Linear Solve]
                                       math.linsolve(HIGH_PRECISION)
                                       Rouché-Capelli & Backward Error Check
                                                    │
                                                    ▼
                                    [Etapa 5: Physical Observables]
                                       Reconstruct node phasors V_n
                                       Reconstruct branch currents I_b
                                       Complex KCL verification
                                       Provenance & SHA-256 Digest
```

### 3.2 Desacoplamiento Estricto AC vs DC
1. **La solución AC no itera**: El sistema AC es estrictamente **lineal** en el dominio fasorial. Se ensambla y resuelve exactamente una vez por cada frecuencia evaluada.
2. **Inmutabilidad del punto estático**: El punto de polarización $\mathbf{x}_0$ es un vector estático congelado. Ninguna magnitud de excitación de pequeña señal altera $\mathbf{x}_0$.
3. **Pureza de fuentes**:
   - Una fuente independiente en DC impone $V_{DC}$ o $I_{DC}$.
   - En el modelo incremental de pequeña señal, su perturbación es $\tilde{v}_s$ o $\tilde{i}_s$. Si la fuente es exclusivamente de polarización (sin atributo AC), su variación de pequeña señal es idénticamente nula ($\tilde{v}_s = 0$ cortocircuito, $\tilde{i}_s = 0$ circuito abierto).

---

## 4. Modelo Matemático Formal

### 4.1 Desarrollo en Series de Taylor
Sea un circuito con vector de potenciales de nudo y variables auxiliares $\mathbf{x}(t) \in \mathbb{R}^N$, gobernado por el sistema algebraico-diferencial no lineal:
$$\mathbf{f}(\mathbf{x}(t)) + \frac{d}{dt}\mathbf{q}(\mathbf{x}(t)) = \mathbf{u}(t)$$

Separando el estado en una componente estática de polarización $\mathbf{x}_0$ y una pequeña perturbación dinámica $\Delta\mathbf{x}(t)$:
$$\mathbf{x}(t) = \mathbf{x}_0 + \Delta\mathbf{x}(t), \quad \mathbf{u}(t) = \mathbf{u}_0 + \Delta\mathbf{u}(t)$$
con $\|\Delta\mathbf{x}(t)\| \ll \|\mathbf{x}_0\|$.

En el punto de operación DC, las derivadas temporales son nulas y el sistema satisface la ecuación de equilibrio estático:
$$\mathbf{f}(\mathbf{x}_0) = \mathbf{u}_0$$
resuelta por `solve_nonlinear_dc(circuit)`.

Efectuando la aproximación de Taylor de primer orden para la perturbación:
$$\mathbf{f}(\mathbf{x}_0 + \Delta\mathbf{x}(t)) \approx \mathbf{f}(\mathbf{x}_0) + \left.\frac{\partial\mathbf{f}}{\partial\mathbf{x}}\right|_{\mathbf{x}_0} \Delta\mathbf{x}(t)$$
$$\mathbf{q}(\mathbf{x}_0 + \Delta\mathbf{x}(t)) \approx \mathbf{q}(\mathbf{x}_0) + \left.\frac{\partial\mathbf{q}}{\partial\mathbf{x}}\right|_{\mathbf{x}_0} \Delta\mathbf{x}(t)$$

Sustituyendo y restando el equilibrio $\mathbf{f}(\mathbf{x}_0) = \mathbf{u}_0$, obtenemos el sistema lineal diferencial de pequeña señal:
$$\mathbf{G}(\mathbf{x}_0) \Delta\mathbf{x}(t) + \mathbf{C}(\mathbf{x}_0) \frac{d}{dt}\Delta\mathbf{x}(t) = \Delta\mathbf{u}(t)$$
donde:
- $\mathbf{G}(\mathbf{x}_0) = \left.\frac{\partial\mathbf{f}}{\partial\mathbf{x}}\right|_{\mathbf{x}_0} \in \mathbb{R}^{N \times N}$ es la matriz de conductancias incrementales MNA en el punto $\mathbf{x}_0$.
- $\mathbf{C}(\mathbf{x}_0) = \left.\frac{\partial\mathbf{q}}{\partial\mathbf{x}}\right|_{\mathbf{x}_0} \in \mathbb{R}^{N \times N}$ es la matriz de elementos dinámicos lineales ($L, C$).

### 4.2 Transformación Fasorial en el Dominio de la Frecuencia
Bajo una excitación armónica sinusoidal permanente a frecuencia angular $\omega = 2\pi f > 0$, con la convención canónica de AcademicCore $e^{+j\omega t}$:
$$\Delta\mathbf{x}(t) = \text{Re}\left\{ \tilde{\mathbf{X}} e^{j\omega t} \right\}, \quad \Delta\mathbf{u}(t) = \text{Re}\left\{ \tilde{\mathbf{U}} e^{j\omega t} \right\}$$
donde $\tilde{\mathbf{X}} \in \mathbb{C}^N$ y $\tilde{\mathbf{U}} \in \mathbb{C}^N$ son fasores complejos con amplitudes de valor pico.

Dado que $\frac{d}{dt} \to j\omega$, el sistema diferencial se transforma de forma exacta en el sistema algebraico complejo MNA:
$$\mathbf{A}_{ac}(j\omega) \tilde{\mathbf{X}} = \mathbf{b}_{ac}$$
con:
$$\mathbf{A}_{ac}(j\omega) = \mathbf{G}(\mathbf{x}_0) + j\omega \mathbf{C}(\mathbf{x}_0) \in \mathbb{C}^{N \times N}, \quad \mathbf{b}_{ac} = \tilde{\mathbf{U}} \in \mathbb{C}^N$$

---

## 5. Resistores ($R$)

- **Modelo DC**: Ley de Ohm $I = \frac{V_1 - V_2}{R}$.
- **Modelo Incremental**: $i_{ac} = \frac{v_1 - v_2}{R} = Y_R (v_1 - v_2)$.
- **Admitancia Compleja**:
  $$Y_R = \frac{1}{R} + j 0 \in \mathbb{C}$$
- **Dependencia en Frecuencia**: Ninguna ($\frac{dY_R}{d\omega} = 0$).
- **Unidades**: Resistencia $R$ en $\Omega$ (`Quantity(RESISTANCE)`), Admitancia $Y_R$ en $\text{S}$ (Siemens).
- **Estampado MNA**:
  Para nodos $p_1, p_2 \neq 0$:
  $$A[p_1, p_1] \mathrel{+}= Y_R, \quad A[p_2, p_2] \mathrel{+}= Y_R$$
  $$A[p_1, p_2] \mathrel{-}= Y_R, \quad A[p_2, p_1] \mathrel{-}= Y_R$$
  (Si $p_1=0$ o $p_2=0$, la fila/columna de tierra se omite, cumpliendo la invariante MNA de F8-B/D3).

---

## 6. Capacitores ($C$)

- **Modelo DC**: Circuito abierto ($I_C = 0$). No participa en la matriz conductiva estática de F8-H/I.
- **Modelo Incremental**: $i_c(t) = C \frac{dv_c(t)}{dt} \implies \tilde{I}_c = j\omega C \tilde{V}_c$.
- **Admitancia Compleja**:
  $$Y_C = 0 + j \omega C \in \mathbb{C}, \quad \omega = 2\pi f$$
- **Dominio de Frecuencia**:
  - Requiere estrictamente $f > 0$.
  - Si $f \le 0$ o no es finita: se rechaza con `ACFrequencyError` / `ACStatus.INVALID`.
  - Transición a DC ($f = 0$): No se interpola silenciosamente; $f=0$ es el dominio estático de `solve_nonlinear_dc`.
- **Unidades**: Capacitancia $C$ en $\text{F}$ (`Quantity(CAPACITANCE)`), Admitancia $Y_C$ en $\text{S}$ (imaginaria pura positiva).
- **Estampado MNA**:
  Para terminales $p_1, p_2 \neq 0$:
  $$A[p_1, p_1] \mathrel{+}= Y_C, \quad A[p_2, p_2] \mathrel{+}= Y_C$$
  $$A[p_1, p_2] \mathrel{-}= Y_C, \quad A[p_2, p_1] \mathrel{-}= Y_C$$

---

## 7. Inductores ($L$)

- **Modelo DC**: Cortocircuito ($V_L = 0$). En F8-B/H MNA, genera una rama auxiliar de tensión con $V=0$.
- **Modelo Incremental AC**: $v_L(t) = L \frac{di_L(t)}{dt} \implies \tilde{V}_L = j\omega L \tilde{I}_L$.
- **Admitancia Compleja Directa**:
  Para todo $\omega = 2\pi f > 0$, la reactancia inductiva $X_L = \omega L > 0$ es no nula y finita. Por tanto, la admitancia incremental del inductor existe y está bien definida:
  $$Y_L = \frac{1}{j\omega L} = -j \frac{1}{\omega L} = 0 - j \frac{1}{\omega L} \in \mathbb{C}$$
- **Compatibilidad Arquitectónica**:
  En `ac/problem.py` (líneas 428–430), AcademicCore ya implementa inductores como admitancias de rama $Y_L = -j/(\omega L)$ sin añadir incógnitas auxiliares. F8-J adopta esta misma convención canónica para evitar introducir columnas innecesarias en la formulación de pequeña señal cuando $f > 0$.
- **Unidades**: Inductancia $L$ en $\text{H}$ (`Quantity(INDUCTANCE)`), Admitancia $Y_L$ en $\text{S}$ (imaginaria pura negativa).
- **Estampado MNA**:
  $$A[p_1, p_1] \mathrel{+}= Y_L, \quad A[p_2, p_2] \mathrel{+}= Y_L$$
  $$A[p_1, p_2] \mathrel{-}= Y_L, \quad A[p_2, p_1] \mathrel{-}= Y_L$$

---

## 8. Fuentes Independientes y Dependientes

### 8.1 Fuentes Independientes ($V$, $I$)
En un circuito de pequeña señal, cada fuente independiente posee potencialmente dos atributos: su polarización estática y su excitación dinámica.

#### Reglas Normativas de Excitación:
1. **Atributos de Parámetros**:
   - `parameters["ac_mag"]`: Magnitud pico de pequeña señal (Quantity o Decimal).
   - `parameters["ac_phase"]` o `parameters["phase"]`: Ángulo de fase (por defecto $0^\circ$, soporte para `"deg"` y `"rad"` vía `phase_unit`).
   - `parameters["ac"]`: Flag booleano opcional. Si `ac=True` y no hay `ac_mag`, se toma `value` como magnitud AC.
2. **Fuentes de polarización pura (DC Bias)**:
   Si una fuente no posee especificación AC (`ac_mag=0`, o sin atributos AC):
   - **Fuente de Tensión DC**: En AC se comporta como cortocircuito incremental ($\tilde{V}_{ac} = 0$). Ocupa una fila/columna auxiliar en MNA con restricción $V(+) - V(-) = 0$ y término independiente $b_k = 0$.
   - **Fuente de Corriente DC**: En AC se comporta como circuito abierto incremental ($\tilde{I}_{ac} = 0$). No inyecta corriente al vector de términos independientes $\mathbf{b}_{ac}$ ($b = 0$).
3. **Fuentes con Excitación AC**:
   - **Fuente de Tensión AC**: Fasor $\tilde{V}_s = V_{peak} (\cos\phi + j\sin\phi)$. Ocupa fila auxiliar $k$ con restricción $V(+) - V(-) = \tilde{V}_s$, inyectando $\tilde{V}_s$ en $b_k$.
   - **Fuente de Corriente AC**: Fasor $\tilde{I}_s = I_{peak} (\cos\phi + j\sin\phi)$. Inyecta $+\tilde{I}_s$ en el nodo positivo y $-\tilde{I}_s$ en el nodo negativo del RHS $\mathbf{b}_{ac}$.

### 8.2 Fuentes Dependientes ($E, G, H, F$)
Las fuentes dependientes ya son intrínsecamente lineales:
- **$E$ (VCVS)**: $V(+) - V(-) - \mu (V_{cp} - V_{cn}) = 0$. Fila auxiliar idéntica a F8-D3.
- **$G$ (VCCS)**: Inyección incremental $J = g_m (V_{cp} - V_{cn})$ en terminales de salida.
- **$H$ (CCVS)**: $V(+) - V(-) - r \cdot I_{ctrl} = 0$. Resuelve la forma lineal de control.
- **$F$ (CCCS)**: Inyección incremental $J = \beta \cdot I_{ctrl}$.
- **Restricción estricta heredada**: Las fuentes controladas por corriente ($H, F$) no pueden sensar terminales internos no-auxiliares de semiconductores ($D$ o $Q$), tal como quedó certificado en F8-I (`UnsupportedElementError`).

### 8.3 Amplificador Operacional Ideal ($O$) y Transformador Ideal ($T$)
- **Op-Amp ($O$)**: Restricción fasorial de entrada virtual $V(+) - V(-) = 0$, corriente de salida $I_o$ en columna auxiliar.
- **Transformador ($T$)**: Restricciones de acoplamiento fasorial $V_3 - V_4 - n (V_1 - V_2) = 0$ y $I_1 + n I_2 = 0$.

---

## 9. Diodo Shockley ($D$)

### 9.1 Modelo Constitutivo y Punto de Polarización
En el punto de operación estático $\mathbf{x}_0$, el diodo con parámetros $(I_S, n, V_T)$ presenta una caída de tensión estática $V_{D0} = V_{A0} - V_{K0}$ y una corriente de polarización estática:
$$I_{D0} = I_S \left( \exp\left(\frac{V_{D0}}{n V_T}\right) - 1 \right)$$

### 9.2 Conductancia Dinámica Incremental
Efectuando la derivada analítica exacta en $V_{D0}$:
$$g_d = \left.\frac{dI_D}{dV_D}\right|_{V_{D0}} = \frac{I_S}{n V_T} \exp\left(\frac{V_{D0}}{n V_T}\right)$$
calculada mediante la función certificada `shockley_conductance(Vd, params, ctx)` de `academic_core.domain.engineering.mna.diode`.

### 9.3 Modelo de Pequeña Señal
La relación corriente-tensión fasorial del diodo es:
$$\tilde{I}_d = g_d \tilde{V}_d = g_d (\tilde{V}_a - \tilde{V}_k)$$
- **Admitancia Compleja**: $Y_D = g_d + j 0$ (admitancia puramente real).
- **Capacitancia de Unión**: **Cero por defecto** (conforme al mandato normativo §9: sin capacitancias espurias no parametrizadas).
- **Estampado MNA**:
  Exactamente idéntico al de un resistor con conductancia $g_d$ entre ánodo ($A$) y cátodo ($K$):
  $$A[A, A] \mathrel{+}= g_d, \quad A[K, K] \mathrel{+}= g_d$$
  $$A[A, K] \mathrel{-}= g_d, \quad A[K, A] \mathrel{-}= g_d$$

---

## 10. Transistor BJT Ebers-Moll ($Q$)

### 10.1 Reutilización del Jacobiano Analítico Certificado de F8-I
En F8-I se certificó la formulación matemática de transporte de Ebers-Moll para transistores NPN y PNP con conservación idéntica de corriente $I_C + I_B + I_E \equiv 0$.

El modelo de pequeña señal del BJT se define unívocamente como la linealización de primer orden de sus corrientes terminales entrantes $(I_C, I_B, I_E)$ en función de sus potenciales de nodo $(V_C, V_B, V_E)$:
$$\begin{bmatrix} \tilde{I}_c \\ \tilde{I}_b \\ \tilde{I}_e \end{bmatrix} = \mathbf{J}_{BJT}(V_{C0}, V_{B0}, V_{E0}) \begin{bmatrix} \tilde{V}_c \\ \tilde{V}_b \\ \tilde{V}_e \end{bmatrix}$$

**Regla de Oro**: F8-J **NO vuelve a implementar ni redefinir las derivadas analíticas**. Reutiliza directamente la función:
```python
bjt_jacobian(vc, vb, ve, bjt_params, ctx)
```
de `academic_core.domain.engineering.mna.bjt`.

### 10.2 Estructura del Jacobiano de Conductancias $3 \times 3$
Para ambos tipos de polaridad (NPN y PNP), el Jacobiano viene parametrizado por las conductancias dinámicas de unión $(g_F, g_R)$:
$$\mathbf{J}_{BJT} = \begin{bmatrix}
J_{00} & J_{01} & J_{02} \\
J_{10} & J_{11} & J_{12} \\
J_{20} & J_{21} & J_{22}
\end{bmatrix} = \begin{bmatrix}
\frac{g_R}{\alpha_R} & g_F - \frac{g_R}{\alpha_R} & -g_F \\
-\frac{g_R}{\beta_R} & \frac{g_F}{\beta_F} + \frac{g_R}{\beta_R} & -\frac{g_F}{\beta_F} \\
-g_R & -\frac{g_F}{\alpha_F} + g_R & \frac{g_F}{\alpha_F}
\end{bmatrix}$$
donde las filas corresponden a las corrientes terminales entrantes $(\tilde{I}_c, \tilde{I}_b, \tilde{I}_e)$ y las columnas a los potenciales $(\tilde{V}_c, \tilde{V}_b, \tilde{V}_e)$.

#### Propiedades Algebraicas Invariantes:
1. **Conservación de Corriente Terminal (Suma de Filas Nula)**:
   $$\sum_{i=0}^2 J_{ik} = 0 \quad \forall k \in \{0, 1, 2\} \implies \tilde{I}_c + \tilde{I}_b + \tilde{I}_e \equiv 0$$
2. **Invarianza ante Referencia de Potencial (Suma de Columnas Nula)**:
   $$\sum_{k=0}^2 J_{ik} = 0 \quad \forall i \in \{0, 1, 2\}$$
   (Un desplazamiento uniforme de potencial $\tilde{V}_c = \tilde{V}_b = \tilde{V}_e = \Delta V$ induce corriente terminal nula).

### 10.3 Conexión con los Parámetros Híbridos Clásicos ($g_m, r_\pi, r_o$)
En la región activa directa ($V_{BE} > 0, V_{BC} \le 0$), donde $g_R \approx 0$:
- Transconductancia: $g_m = \left.\frac{\partial I_C}{\partial V_{BE}}\right|_{V_{CE}} \approx g_F = \frac{I_{C0}}{V_T}$.
- Resistencia dinámica base-emisor: $r_\pi = \left(\left.\frac{\partial I_B}{\partial V_{BE}}\right|_{V_{CE}}\right)^{-1} \approx \frac{\beta_F}{g_F} = \frac{\beta_F}{g_m}$.
- Resistencia de salida: $r_o = \infty$ (sin efecto Early en el modelo canónico Ebers-Moll).

### 10.4 Estampado MNA Complejo del BJT
Sean $c, b, e$ los índices de nodo no-tierra asignados a los pines `"C"`, `"B"`, `"E"` del BJT $Q$.
Definiendo el mapeo de pines a índices locales: $\text{pin\_map} = \{C: 0, B: 1, E: 2\}$:
Para cada par de pines $p, q \in \{C, B, E\}$ con índices de nodo $i = \text{node\_index}(p)$ y $j = \text{node\_index}(q)$:
- Si $i \neq \text{ground}$ y $j \neq \text{ground}$:
  $$A[i, j] \mathrel{+}= \text{DecimalComplex}(J_{\text{pin\_map}[p], \text{pin\_map}[q]}, \text{Decimal}(0))$$

Este estampado es 100% natural, directo, determinista y preserva bit a bit la compatibilidad con el solver lineal complejo `math.linsolve`.

---

## 11. Definición del Papel de la Frecuencia

### 11.1 Decisión de Arquitectura: Frecuencia Única (Single Frequency) Prioritaria
- **Fase Inicial (F8-J)**: Se establece como requisito prioritario y estricto el análisis a **Frecuencia Única (Single Frequency)**:
  ```python
  solve_small_signal_ac(circuit: Circuit, frequency: Quantity | str) -> SmallSignalACResult
  ```
- **Justificación**:
  1. Permite validar exhaustivamente el modelo matemático incremental, el acoplamiento no lineal DC $\to$ AC, y los 20 casos de prueba canónicos sin introducir complejidad superflua.
  2. Garantiza un marco de benchmarking y certificación limpio y desacoplado.

### 11.2 Extensión Futura a Barrido de Frecuencias (Frequency Sweep)
La arquitectura queda deliberadamente diseñada para soportar barridos lineales y logarítmicos (`solve_small_signal_ac_sweep`) en una extensión inmediata sin rediseño:
- El punto de polarización DC $\mathbf{x}_0$ y los parámetros de pequeña señal ($g_d, \mathbf{J}_{BJT}$) se calculan **una sola vez**.
- La matriz de admitancia $\mathbf{A}_{ac}(j\omega)$ se re-estampa y resuelve para cada frecuencia $\omega_k$ del barrido reutilizando el punto estático congelado.

---

## 12. AC vs DC: Separación Estricta de Funciones

| Característica | DC Operating Point (`solve_nonlinear_dc`) | Small-Signal AC (`solve_small_signal_ac`) |
| :--- | :--- | :--- |
| **Dominio Matemático** | $\mathbb{R}^N$ (números reales, `Decimal`) | $\mathbb{C}^N$ (`DecimalComplex`, alta precisión) |
| **Naturaleza del Sistema** | No lineal acoplado: $\mathbf{F}(\mathbf{x}) = \mathbf{0}$ | Lineal fasorial: $\mathbf{A}_{ac}(j\omega)\tilde{\mathbf{X}} = \mathbf{b}_{ac}$ |
| **Método de Resolución** | Newton-Raphson amortiguado con bisección | Eliminación gaussiana / Rouché-Capelli (`linsolve`) |
| **Número de Iteraciones** | $1 \le k \le 50$ (iterativo) | Exactamente 1 paso de resolución lineal |
| **Capacitores** | Circuito abierto ($I_C = 0$) | Admitancia compleja $Y_C = j\omega C$ |
| **Inductores** | Cortocircuito ($V_L = 0$) | Admitancia compleja $Y_L = -j/(\omega L)$ |
| **Diodos** | Exponencial completa $I_D(V_D)$ | Conductancia dinámica $g_d = \left.\frac{dI_D}{dV_D}\right|_{V_{D0}}$ |
| **BJTs** | Ebers-Moll acoplado no lineal | Jacobiano de conductancias $\mathbf{J}_{BJT}(\mathbf{x}_0)$ |
| **Fuentes DC** | Excitación activa ($V_s, I_s$) | Anuladas ($\tilde{v}_s = 0$ corto, $\tilde{i}_s = 0$ abierto) |
| **Fuentes AC** | Ignoradas o no aplicables | Excitación fasorial activa $\tilde{V}_s, \tilde{I}_s$ |

---

## 13. Observables y Domain Objects Tipados

AcademicCore prohíbe el uso de diccionarios improvisados para el resultado normativo. Se define la estructura tipada `SmallSignalACResult`:

```python
@dataclass(frozen=True)
class DiodeSmallSignalParams:
    ref: str
    anode: str
    cathode: str
    v_d0: Decimal        # Tensión DC de polarización (V)
    i_d0: Decimal        # Corriente DC de polarización (A)
    g_d: Decimal         # Conductancia dinámica incremental (S)
    r_d: Decimal         # Resistencia dinámica incremental 1/gd (Ω)

@dataclass(frozen=True)
class BJTSmallSignalParams:
    ref: str
    collector: str
    base: str
    emitter: str
    polarity: str        # "NPN" | "PNP"
    v_c0: Decimal        # Tensión DC colector (V)
    v_b0: Decimal        # Tensión DC base (V)
    v_e0: Decimal        # Tensión DC emisor (V)
    v_be0: Decimal       # Vbe DC (V)
    v_ce0: Decimal       # Vce DC (V)
    i_c0: Decimal        # Corriente DC colector (A)
    i_b0: Decimal        # Corriente DC base (A)
    i_e0: Decimal        # Corriente DC emisor (A)
    g_m: Decimal         # Transconductancia gm (S)
    r_pi: Decimal        # Resistencia dinámica de entrada r_pi (Ω)
    g_F: Decimal         # Conductancia de unión directa (S)
    g_R: Decimal         # Conductancia de unión inversa (S)
    jacobian: tuple[tuple[Decimal, Decimal, Decimal], ...]

@dataclass(frozen=True)
class SmallSignalACResult:
    status: ACStatus
    operating_point: ACOperatingPoint | None
    dc_operating_point: NonlinearResult | None
    node_voltages: tuple[NodePhasor, ...]
    branch_currents: tuple[BranchCurrent, ...]
    branch_voltages: tuple[BranchVoltage, ...]
    diode_parameters: tuple[DiodeSmallSignalParams, ...]
    bjt_parameters: tuple[BJTSmallSignalParams, ...]
    kcl_max_residual: Decimal | None
    kvl_max_residual: Decimal | None
    solver_result: object | None
    numeric_mode: NumericMode
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str
```

---

## 14. Unidades y Convención de Fase

### 14.1 Tabla Canónica de Unidades
| Magnitud | Símbolo | Unidad SI | Dimensión `units.py` | Tipo Python |
| :--- | :--- | :--- | :--- | :--- |
| Frecuencia cíclica | $f$ | $\text{Hz}$ | `FREQUENCY` | `Quantity(Decimal, Unit)` |
| Frecuencia angular | $\omega$ | $\text{rad/s}$ | Adimensional doc | `Decimal` ($2\pi f$) |
| Resistencia | $R$ | $\Omega$ | `RESISTANCE` | `Quantity` |
| Conductancia | $G, g_d, g_m$ | $\text{S}$ (Siemens) | `ADMITTANCE` | `Quantity` / `Decimal` |
| Capacitancia | $C$ | $\text{F}$ | `CAPACITANCE` | `Quantity` |
| Inductancia | $L$ | $\text{H}$ | `INDUCTANCE` | `Quantity` |
| Tensión fasorial | $\tilde{V}$ | $\text{V}$ (volt pico) | `VOLTAGE` | `DecimalComplex` |
| Corriente fasorial | $\tilde{I}$ | $\text{A}$ (ampere pico) | `CURRENT` | `DecimalComplex` |

### 14.2 Convención de Fase
- **Dominio Interno**: Cartesianas $(\text{Re}, \text{Im})$ sobre `DecimalComplex`.
- **Ángulo Fasorial**: $\angle \tilde{Z} = \text{atan2}(\text{Im}, \text{Re}) \in (-\pi, \pi]$ radianes.
- **Visualización y Reporte**: Grados sexagesimales ($[-180^\circ, 180^\circ]$ o $[0^\circ, 360^\circ)$ normalizado).

---

## 15. Aritmética Compleja de Alta Precisión

- **Infraestructura Base**: Reutilización estricta de `DecimalComplex` (`academic_core.domain.engineering.math.decimal_complex`).
- **Resolución Lineal**: `ComplexLinearProblem` resuelto en `NumericMode.HIGH_PRECISION` vía `academic_core.domain.engineering.math.linsolve`.
- **Prohibición de Float y Numpy**: No se permite la conversión a `complex` primitivo de Python en ningún punto de la resolución, asegurando ausencia de redondeos flotantes estándar y garantizando determinismo de plataforma.

---

## 16. Precisión, Tolerancias y Residuales

- **Contexto de Precisión de Trabajo**: 50 dígitos decimales de precisión (`make_context()` con precision $\ge 50$).
- **Tolerancia del Solver Lineal (Backward Error)**:
  $$\text{BE\_TOL} = 10^{-30}$$
- **Tolerancias de Convergencia del Punto DC**:
  $$R_{\text{TOL}} = 10^{-9}, \quad A_{\text{TOL}} = 10^{-12}, \quad S_{\text{TOL}} = 10^{-12}$$
- **Criterio de Aceptación KCL Complejo**:
  Para cada nodo $n$, la suma de corrientes fasoriales entrantes/salientes satisface:
  $$|\sum \tilde{I}_b(n)| \le A_{\text{TOL}} + R_{\text{TOL}} \max(1, \max |\tilde{I}|)$$

---

## 17. Validación Externa con ngspice 47

### 17.1 Protocolo de Simulación Comparada
Para cada circuito canónico que involucre semiconductores:
1. Generación de netlist canónico `.cir` con parámetros exactos.
2. Directiva de análisis:
   ```spice
   .op
   .ac lin 1 <freq> <freq>
   ```
3. Ejecución directa mediante subprocess controlado contra el binario verificado `ngspice_con.exe` (v47).
4. Parseo del archivo de salida o `.raw` para extraer la magnitud y fase de tensiones de nodo.

### 17.2 Métricas y Umbrales Normativos
- **Error Relativo de Magnitud**:
  $$\epsilon_{\text{mag}} = \frac{\left| |\tilde{V}_{\text{core}}| - |\tilde{V}_{\text{ngspice}}| \right|}{\max(1\,\text{V}, |\tilde{V}_{\text{ngspice}}|)} < 10^{-4}$$
- **Error Absoluto de Fase**:
  $$\epsilon_{\text{phase}} = \left| \angle\tilde{V}_{\text{core}} - \angle\tilde{V}_{\text{ngspice}} \right| < 0.05^\circ \quad (\approx 8.7 \times 10^{-4}\,\text{rad})$$

---

## 18. Test Matrix Canónica (J1 a J20)

| ID | Nombre del Test | Descripción del Circuito y Topología | Criterio de Éxito |
| :--- | :--- | :--- | :--- |
| **J1** | Single resistor AC | Fuente AC $V_s$ sobre $R_1$. | $\tilde{V} = V_s$, $\tilde{I} = V_s / R_1$, fase $0^\circ$. |
| **J2** | RC Low-Pass filter | Filtro pasabajos $R-C$ a $f = f_c = \frac{1}{2\pi RC}$. | $|\tilde{V}_{out}| = \frac{V_s}{\sqrt{2}}$, $\angle \tilde{V}_{out} = -45^\circ$. |
| **J3** | RC High-Pass filter | Filtro pasaaltos $C-R$ a $f = f_c$. | $|\tilde{V}_{out}| = \frac{V_s}{\sqrt{2}}$, $\angle \tilde{V}_{out} = +45^\circ$. |
| **J4** | RL Circuit | Divisor $R-L$ a frecuencia de corte. | Magnitud y fase reactiva inductiva exacta. |
| **J5** | RLC Resonant Bandpass | Circuito $R-L-C$ serie a frecuencia de resonancia $f_0 = \frac{1}{2\pi\sqrt{LC}}$. | Impedancia puramente resistiva, fase $0^\circ$, corriente máxima. |
| **J6** | Voltage Divider AC | Divisor de tensión con múltiples impedancias complejas. | Relación fasorial de tensiones exacta. |
| **J7** | Current Source AC | Fuente de corriente AC excitando red $R \parallel C$. | Tensión fasorial nodal coincidente con ley de Ohm fasorial. |
| **J8** | Dependent Source AC | Circuito con VCVS ($E$) y VCCS ($G$) en régimen sinusoidal. | Solución matricial MNA exacta con acoplamiento lineal. |
| **J9** | Shockley Diode Small-Signal | Diodo polarizado en DC ($V_{DC}, R_{bias}$) con señal AC acoplada. | $g_d = \frac{I_S}{n V_T} e^{\frac{V_{D0}}{n V_T}}$, división AC sobre $r_d = 1/g_d$. |
| **J10** | NPN Common Emitter | Amplificador emisor común con resistencia de colector y desacoplo. | Ganancia de tensión $A_v \approx -g_m R_C$, inversión de fase $180^\circ$. |
| **J11** | PNP Common Emitter | Amplificador emisor común con transistor PNP polarizado. | Ganancia y punto de pequeña señal coincidentes con ngspice. |
| **J12** | Emitter Follower | Colector común (seguidor de emisor) con BJT NPN. | Ganancia de tensión $A_v \approx 1$, fase $\approx 0^\circ$, impedancia de salida baja. |
| **J13** | BJT + Diode Circuit | Etapa de polarización compensada por diodo + amplificador BJT. | Ambos semiconductores linealizados en sus respectivos puntos Q. |
| **J14** | BJT + Dependent Source | Amplificador BJT acoplado a etapa buffer con fuente dependiente $E$. | MNA conjunta con elementos lineales y no lineales linealizados. |
| **J15** | BJT + Ideal Op-Amp | Etapa activa mixta con BJT y amplificador operacional $O$. | Nullor y modelo BJT resueltos simultáneamente en AC. |
| **J16** | Transformer AC | Circuito acoplado inductivamente con transformador ideal $T$. | Relación de espiras $n$ reflejada en tensiones y corrientes fasoriales. |
| **J17** | Multi-node Mixed Circuit | Red amplia con $\{R, L, C, D, Q, V, I\}$ de $\ge 10$ nodos. | KCL complejo $\le 10^{-12}$, concordancia ngspice $< 10^{-4}$. |
| **J18** | Invalid Frequency | Frecuencia $f \le 0$, compleja, no finita o no dimensional. | Error tipado en-banda `ACFrequencyError` / `ACStatus.INVALID`. |
| **J19** | Unsupported Element | Circuito conteniendo elemento no soportado (ej. MOSFET $M$). | Rechazo tipado `UnsupportedElementError` / `ACStatus.UNSUPPORTED`. |
| **J20** | Determinism & Provenance | Ejecución repetida (10 iteraciones) del circuito J10. | Digest SHA-256 bit-a-bit idéntico en el 100% de corridas. |

---

## 19. Invariantes y Leyes de Conservación

1. **Ley de Corrientes de Kirchhoff Compleja (KCL Fasorial)**:
   En cada nodo $k$ del circuito (incluyendo el nodo de tierra de referencia):
   $$\sum_{b \text{ incidentes}} \tilde{I}_b = 0$$
2. **Ley de Tensiones de Kirchhoff Compleja (KVL Fasorial)**:
   A lo largo de cualquier malla fundamental del grafo del circuito:
   $$\sum_{b \in \text{malla}} \tilde{V}_b = 0$$
3. **Invarianza de Referencia Nodal**:
   El desplazamiento del potencial de referencia deja inalteradas todas las corrientes fasoriales de rama y todas las diferencias de potencial de rama.
4. **Determinismo Numérico Absoluto**:
   Para idéntica topología y parámetros, el resultado fasorial y el digest SHA-256 son reproducibles al 100%.
5. **Pureza Decimal**:
   Prohibición de `float` y `numpy` en todas las clases de dominio y motores de cálculo.

---

## 20. Regresión de Fases Anteriores

El diseño técnico de F8-J garantiza explícitamente:
- **Suite F8-H (DC no lineal diodo)**: 69/69 tests inalterados y pasando al 100%.
- **Suite F8-I (DC no lineal BJT)**: 74/74 tests inalterados y pasando al 100%.
- **Suite F8-D1 (Aritmética compleja Decimal)**: 50/50 tests inalterados y pasando al 100%.
- **Suite F8-D2 (Solver complejo de alta precisión)**: 67/67 tests inalterados y pasando al 100%.
- **Cero rotura de interfaces existentes**: `solve_nonlinear_dc` y `solve_ac` preservan intactas sus firmas y contratos.

---

## 21. Seguridad y Restricciones AST

Al igual que en F8-H y F8-I, todo el código desarrollado para F8-J debe superar la auditoría AST de seguridad estricta:
- Cero llamadas a `eval()`, `exec()`, `compile()`.
- Cero uso de `__import__()` o importación dinámica.
- Cero llamadas a `subprocess`, `os.system`, `socket` en el código de producción (`domain/engineering/`).
- Cero presencia de literales o coerciones a `float` en la lógica física o numérica.

---

## 22. Provenance y Digest Canónico SHA-256

El diccionario de procedencia (`provenance`) de F8-J incluirá:
```python
provenance = {
    "engine": "f8j-small-signal-ac/1.0",
    "circuit_structure": canonical_circuit_dict,
    "frequency": operating_point.to_dict(),
    "dc_operating_point_digest": dc_result.provenance.get("digest"),
    "linear_solver": {
        "mode": "HIGH_PRECISION",
        "working_precision": 50,
        "backend": "academic_core.domain.engineering.math.linsolve",
    },
    "tolerances": {
        "atol": str(ATOL),
        "rtol": str(RTOL),
    },
    "status": status.value,
}
```
El **digest canónico** será el hash SHA-256 del string JSON serializado con claves ordenadas (`sort_keys=True`) de esta estructura. Nunca contendrá timestamps, UUIDs aleatorios ni punteros de memoria.

---

## 23. Benchmarking de Rendimiento y Escalamiento

Se define el plan de benchmarking sintético preliminar para medir el tiempo de ensamblado y resolución AC frente al tamaño del circuito ($N$ nodos):
- Topologías en escalera (ladder networks) con transistores BJT y diodos:
  - $N = 1$ etapa (3 nodos)
  - $N = 10$ etapas (12 nodos)
  - $N = 32$ etapas (34 nodos)
  - $N = 64$ etapas (66 nodos)
  - $N = 128$ etapas (130 nodos)
- **Criterio de Medición**: Medir primero en la Fase 1 antes de imponer thresholds artificiales; verificar que el coste de resolución AC lineal represente una fracción pequeña ($\le 20\%$) del tiempo total (ya que el paso DC requiere $k$ iteraciones de Newton, mientras que el paso AC requiere exactamente 1 resolución lineal).

---

## 24. Criterios de Certificación para GATE-F8J

Para que la futura puerta **GATE-F8J** sea declarada superada y cerrada:
1. **100% de tests J1 a J20 pasando**: La suite completa de tests de pequeña señal debe pasar con 0 errores y 0 omisiones.
2. **Regresión completa intacta**: F8-A hasta F8-I (incluyendo F8-D1, F8-D2, F8-H, F8-I) al 100% verde.
3. **Validación cruzada ngspice 47 superada**: Error relativo de magnitud $< 10^{-4}$ y error de fase $< 0.05^\circ$ en amplificadores BJT y redes con diodos.
4. **Auditoría AST limpia**: Cero `float`, cero funciones dinámicas o inseguras.
5. **Determinismo verificado**: Mismo digest SHA-256 verificado en múltiples ejecuciones.

---

## 25. Riesgos y Decisiones Arquitectónicas

1. **Riesgo**: Discrepancia entre la convención de fase de ngspice y AcademicCore.
   - *Decisión*: Se congela la convención fasorial $e^{+j\omega t}$ con amplitudes pico y fase en grados en $(-\pi, \pi]$ normalizada a $[-180^\circ, 180^\circ]$ para comparación unívoca.
2. **Riesgo**: Fuentes de tensión de polarización DC que generen singularidad si se cortocircuitan ingenuamente.
   - *Decisión*: Las fuentes de tensión DC se tratan formalmente como ramas MNA auxiliares de tensión con $V_{ac} = 0$, preservando el rango completo de la matriz MNA sin alterar la topología del grafo.
3. **Riesgo**: Re-evaluación no lineal accidental durante el cálculo AC.
   - *Decisión*: El cálculo AC recibe el punto $\mathbf{x}_0$ resuelto de forma inmutable; la matriz de pequeña señal se ensambla directamente como un `ComplexLinearProblem` lineal.

---

## 26. Cambios Previstos y Lista de Archivos para la Implementación Posterior

Para la Fase 1 de Implementación (a ejecutar únicamente tras la aprobación formal de este diseño):

### 26.1 Archivos de Producción a Crear / Modificar
1. **[NUEVO] `src/academic_core/domain/engineering/ac/small_signal.py`**:
   - Orquestador principal: `solve_small_signal_ac(circuit, frequency)`.
   - Extracción de parámetros de pequeña señal para diodos (`DiodeSmallSignalParams`) y BJTs (`BJTSmallSignalParams`).
   - Ensamblador MNA de pequeña señal `build_small_signal_problem(...)`.
2. **[MODIFICAR] `src/academic_core/domain/engineering/ac/__init__.py`**:
   - Exportación de `solve_small_signal_ac` y domain objects de pequeña señal.
3. **[MODIFICAR] `src/academic_core/domain/engineering/ac/problem.py`**:
   - Admisión de `allow_nonlinear_linearized=True` o soporte de elementos $D$ y $Q$ cuando se suministran sus parámetros incrementales.

### 26.2 Archivos de Test a Crear
1. **[NUEVO] `tests/test_f8j_small_signal_ac.py`**:
   - Implementación exhaustiva de los casos J1 a J20.
   - Cross-validation automatizada con ngspice 47.
   - Auditoría AST y pruebas de determinismo.
