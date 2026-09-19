# GATE-F8K-DESIGN — Auditoría forense y diseño formal (sin implementación)

> **Fase**: F8-K — Semiconductores adicionales (MOSFET Level 1 / Shichman-Hodges, JFET, Zener, LED, Schottky, fotodiodo)
> **Tipo**: AUDITORÍA + DISEÑO. **No se implementa nada en esta fase.**
> **Rama normativa**: `main` · **HEAD auditado**: `43a67a7`
> **Veredicto**: **`F8-K DESIGN READY`** (con 2 condiciones pre-implementación, §16)

---

## 1. Header y estado del repositorio

| Campo | Valor observado |
|:---|:---|
| Rama | `main` (up to date con `origin/main`) |
| HEAD | `43a67a7 feat(assessment): harden adversarial persistence and session recovery (gate F9-D)` |
| `git status --short` | limpio (vacío) al inicio de la auditoría |
| `git diff --stat` / `git diff` | vacíos — **cero trabajo local no comprometido** |
| Historial (`git log -n 10 --oneline --decorate`) | `43a67a7` (HEAD→main, origin/main) · `0838192` README · `5249d28` F9 assessment · `661c8c2` **F8-J certified** · `fc5cdc5` F8-I · `f857565` F8-H · `7e85834` F8-G · `26762e5` F8-F findings · `567d2f7` F8-F · `8af0e52` pre-F8-F |
| Python / plataforma | `3.14.6 (MSC v.1944 64-bit AMD64)` · `Windows-11-10.0.26200-SP0` |
| Fases certificadas (evidencia en disco) | F0–F7, F8-A…F8-J (existen `GATE-F8H.md`, `GATE-F8I.md`, `GATE-F8J.md` + sus `-DESIGN.md`), F9-A…F9-D parcial |

**F8-I certificada**: sí (`GATE-F8I.md`, commit `fc5cdc5`). **F8-J certificada**: sí (`GATE-F8J.md`, commit `661c8c2`, tests `test_f8j_small_signal_ac.py` en disco). La tarea asigna F8-K como siguiente fase oficial — coherente con el historial Git.

### 1.1 Inconsistencia documental detectada (ROADMAP.md desactualizado) — FIND-DOC-01 (HIGH)

`docs/roadmap/ROADMAP.md` contradice el estado certificado real:

- Línea 5: encabezado declara fases `F0 a F8-I CERTIFICADAS` (omite F8-J, certificada en `661c8c2`).
- Línea 125: `F8 Electrónica Avanzada (F8-A ... F8-I) [CERTIFICADO]` (omite F8-J).
- Tabla §6.1: última fila certificada es **F8-I** (línea 167); no existe fila F8-J.
- §6.2 (línea 171): lista **F8-J como fase futura** ("F8-J — Small-Signal AC: Linealización…"), cuando `GATE-F8J.md` la cierra como `F8-J CERTIFIED AND CLOSED`.

No se corrige en esta fase (regla §19: reportar primero). **Condición pre-implementación nº 1**: actualizar ROADMAP.md (cabecera, línea 125, tabla §6.1 con fila F8-J certificada, §6.2 moviendo F8-J a certificadas y declarando F8-K como siguiente) antes de abrir la rama de implementación F8-K.

---

## 2. Baseline de regresión (medida en esta auditoría, sin modificar código)

| Suite | Colectados | Resultado | Duración | Notas |
|:---|:---:|:---|:---:|:---|
| `tests/test_f8h_nonlinear_dc.py` | 69 | **69 passed** | 222.11 s | 100 % verde |
| `tests/test_f8i_bjt.py` + `tests/test_f8i_nonlinear_bjt.py` | 33 + 41 = 74 | **74 passed** | 105.39 s | 100 % verde |
| `tests/test_f8j_small_signal_ac.py` | 29 | **28 passed, 1 failed** | ~278–383 s | El fallo es **solo umbral de tiempo** (ver FIND-PERF-01); todo el contenido matemático (`SOLVED`, KCL/KVL, ngspice, AST, no-float, determinismo) pasa |
| Suma relevante F8-H/I/J | 172 | 171 pass / 1 perf-fail | — | Sin regresión matemática |

Observaciones de baseline:

- El gate F8-J declara "23 tests"; el fichero colecta **29** (incluye `TestF8LCorrectiveRegression` con regresiones de cierre F8-L). Discrepancia solo documental (INFO-01).
- `git status` limpio + HEAD == `origin/main`: la baseline es reproducible contra el commit citado.

### FIND-PERF-01 (HIGH, no bloqueante del diseño — ver §16)

`TestASTSecurityAndInvariants::test_scalability_benchmark` falla en esta máquina por umbral normativo de tiempo, **no por matemática**:

```text
Performance timings: {1: 0.133s, 10: 3.60s, 32: 41.43s, 64: 230.89s}   (2.ª pasada: {1: 0.144s, 10: 4.14s, 32: 71.68s, 64: 300.56s})
assert timings[64] < 150.0  →  AssertionError (230.9 s / 300.6 s)
```

El solve en N=64 retorna `ACStatus.SOLVED` (la física converge); solo excede el límite de 150 s (certificado F8-J: 88.4 s en su máquina). Causa: dependencia de hardware, no regresión de código (árbol limpio, sin cambios desde la certificación). Conforme a §15 de la tarea, los tiempos deben tratarse como **diagnósticos**, y este caso lo demuestra empíricamente. **Condición pre-implementación nº 2**: disponer el umbral (re-calibrar por máquina, marcar como diagnóstico no-normativo, o eximir en CI lento) antes del cierre de la implementación F8-K; no se introducirá ningún umbral normativo nuevo para F8-K (§15, §10 del test plan).

---

## 3. Alcance exacto F8-K

### 3.1 IN (dentro de F8-K)

- **DC operating point** de los 6 dispositivos vía `solve_nonlinear_dc` (Newton amortiguado existente, sin cambios en la política Q1: RTOL=1E-9, ATOL=1E-12, STOL=1E-12, MAX_ITER=50, MAX_BACKTRACK=10).
- Residuales `F(x) = A0·x − b0 + ΣD_k(x)`, Jacobianos analíticos por dispositivo, stamps MNA deterministas.
- `NonlinearStatus` / `ACStatus` sin cambios (reuso; §9).
- Validación de parámetros (tipos `Quantity`, dimensiones, finitud, positividad — patrón `extract_*_params`, sin defaults mágicos).
- Contrato de linealización para F8-J (congelado en §9; sin implementar AC nuevo salvo el stamp incremental ya especificado).
- Determinismo bit-a-bit (orden por `ref`, digest SHA-256, `zero-vector` init), AST security, tripwire no-`float` en el núcleo.
- Tests unit/solver/cross-device/regresión/seguridad/determinismo (§12). Validación cruzada ngspice 47 donde aplique (MOSFET/JFET/Zener/LED/Schottky/fotodiodo son todos modelables en ngspice para oráculo externo).

### 3.2 OUT (excluido, con justificación)

| Exclusión | Justificación |
|:---|:---|
| Transient / DAE / capacitancias de unión (Cgs, Cgd, Cds, charge storage) | Pertenece a F8-L; F8-K es DC (+ linealización AC sin memoria). Introducir C internas rompería la separación DC/AC certificada en F8-J |
| Ruido, temperatura (self-heating, derating), BSIM/EKV, RF | Modelos SPICE completos fuera del roadmap F8-K ("Level 1", Shockley); sin parámetros térmicos en la arquitectura `Component.parameters` actual |
| Optoelectrónica dinámica (respuesta temporal, espectro) | El fotodiodo F8-K es DC: `Iph` constante parametrizada; sin modelos temporales definidos por el roadmap |
| Barridos DC/parámetros, Monte Carlo, sensibilidad | Pertenece a F8-M |
| `Rs` serie en LED (resistencia serie física) | `Vd_int = Vd − I·Rs` es **implícita** en I (requiere nodo interno auxiliar o Newton interno); se difiere como limitación honesta documentada, igual que Q3 de F8-H |
| Efectos de segundo orden MOSFET (DIBL, narrow-width, subthreshold slope) | Fuera de "Level 1 / Shichman-Hodges" |

---

## 4. Dependencias

Ninguna dependencia externa nueva. Dependencias internas (todas certificadas, todas en disco):

- `mna.problem.build_mna_problem` (stamps lineales, `allow_diodes/allow_bjts` como precedente del flag por familia).
- `mna.nonlinear._NewtonSystem` + `solve_nonlinear_dc` (residual/Jacobiano/backtracking/convergencia).
- `math.linsolve` (`ComplexLinearProblem.from_sequences`, `NumericMode.HIGH_PRECISION`) — única autoridad lineal.
- `math.trig.make_context` (precisión 50) y `Decimal` explícito.
- `circuit.COMPONENT_PINS` + `_REF_RE` (deben extenderse con letras nuevas).
- `ac.small_signal.solve_small_signal_ac` (contrato de linealización, `SUPPORTED_TYPES` propio).
- `thevenin` (`SUPPORTED_TYPES` lineal — debe **seguir rechazando** los 6 tipos nuevos).
- `units.Quantity` (dimensiones: V, A, S, 1/V, A/V² como tupla derivada, adimensional).

---

## 5. Arquitectura existente relevante (flujo real reconstruido)

### 5.1 Capas y ficheros

```text
circuit.py ──▶ problem.py ──▶ solver.py ──▶ AnalysisResult        (lineal F8-B…G)
     │              │                ▲
     │              │         nonlinear.py (Newton, F8-H/I) ──▶ NonlinearResult
     │              │              ▲ diode.py (Shockley) · bjt.py (Ebers-Moll)
     │              ▼
     └────▶ ac/small_signal.py ──▶ SmallSignalACResult            (F8-J)
                    ▲ math/linsolve (ComplexLinearProblem) · math/trig · DecimalComplex
```

### 5.2 Símbolos y contratos (con localización)

- `solve_linear_dc(circuit) -> AnalysisResult` — `mna/solver.py:198`. Solo tipos lineales.
- `build_mna_problem(circuit, *, allow_diodes=False, allow_bjts=False) -> MNAProblem` — `mna/problem.py:234`. Desconocidos → `UnsupportedElementError`; D sin flag → UNSUPPORTED (precedente exacto para los 6 tipos F8-K).
- `MNAProblem` (`mna/problem.py:217`): `nodes` ordenados (no-ref), `node_index`, `vsource_refs` ordenados, `vsource_index` (+legs `T:1/:2`), `matrix`/`rhs` en `Fraction` exactos. `size = nodos + aux`.
- Diodos/BJT **no añaden incógnitas**: su corriente entra solo en residual/Jacobiano (`nonlinear.py:284-378`: stamps `+g (A,A)/(K,K)`, `−g (A,K)/(K,A)`; BJT bloque 3×3 `bjt_jacobian` sumado en filas/columnas C/B/E).
- `solve_nonlinear_dc(circuit, *, max_iter=MAX_ITER) -> NonlinearResult` — `mna/nonlinear.py:393`. Convergencia por bloques KCL (A) + aux (V) con `_block_ok`; backtracking bisección estricta (`MAX_BACKTRACK+1` halvings); no-finitud → `DIVERGED`; `SINGULAR_JACOBIAN` vía linsolve; `INVALID`/`UNSUPPORTED` en banda.
- `NonlinearStatus` (`nonlinear.py:111`): CONVERGED / MAX_ITERATIONS / DIVERGED / SINGULAR_JACOBIAN / INVALID / UNSUPPORTED. Solo CONVERGED porta solución.
- `DiodeParams` + `extract_diode_params` (`mna/diode.py:46,55`): conjunto exacto `{Is, n, Vt}`, sin defaults; `shockley_current` / `shockley_conductance` / `companion` con contrato overflow→`Infinity` y chequeo `is_finite()` obligatorio en el llamante.
- `BJTParams` + `extract_bjt_params` (`mna/bjt.py:51,66`): `{polarity, Is, Bf, Br, Nf, Nr, Vt}` + `alphaF/alphaR` derivados; corrientes con signo por polaridad (`bjt_terminal_currents`, `bjt.py:182`); Jacobiano 3×3 idéntico en forma para NPN/PNP (`bjt_jacobian`, `bjt.py:255`); `bjt_companion` (`bjt.py:306`).
- `solve_small_signal_ac(circuit, frequency, *, dc_result=None) -> SmallSignalACResult` (`ac/small_signal.py:464`): `SUPPORTED_TYPES` propio (`small_signal.py:113`, incluye R/L/C/V/I/E/G/H/F/O/T/D/Q); DC equivalente (C→abierto, L→V 0V); `dc_result` incompatible → INVALID; D→`g_d` (`shockley_conductance`), Q→`bjt_jacobian` en el punto DC congelado; solve complejo HP único; `ACStatus` (`ac/solution.py:39`): SOLVED/SINGULAR/INCONSISTENT/NUMERICALLY_UNCERTAIN/INVALID/UNSUPPORTED/DIVERGED.
- `ComplexLinearProblem.from_sequences(A, b)` (`math/linsolve/problem.py:153`): acepta `Decimal`/`DecimalComplex` como first-class; `NumericMode.HIGH_PRECISION` en Newton y AC.
- `make_context()` = prec 50, `ROUND_HALF_EVEN`, nunca contexto global (`math/trig.py:33`).
- `COMPONENT_PINS` (`circuit.py:23`): R/C/L 2 pines; V/I/E/G/H/F 2; D (A,K); Q (C,B,E); O 3; T 4. `_REF_RE = ^([RCLVIDQEGHFOT])(\d+)$` (`circuit.py:38`) — **excluye M/J**: J19 construye el `M1` de prueba saltándose el validador vía `object.__new__` (test_f8j:751-756), prueba de que M es la letra prevista para MOSFET.
- `dependent.py:127-143`: H/F controlados por corriente de D o Q → `InvalidCircuitError`. **Los 6 tipos F8-K tampoco podrán ser `control_ref`** (sus corrientes son no lineales).
- `thevenin/port.py:15`: `SUPPORTED_TYPES = {R,V,I,E,G,H,F,O,T}` — reducciones lineales; D/Q ya excluidos; los 6 tipos nuevos quedan excluidos automáticamente si no se tocan (no tocar).
- Netlist `engcircuit/6.0`: `to_netlist`/`from_netlist` solo conectividad; `parameters` **no serializados** (limitación honesta F8-H Q3, clase AUDIT-002) — aplica igual a F8-K.
- `Component` es `frozen=True` superficial (dicts mutables; auditado: nadie muta post-construcción — `circuit.py:47-54`).

### 5.3 Precisión/seguridad/determinismo (verificado por grep + lectura)

- **Cero `float(`** en `mna/`, `ac/`, `math/` (los 4+23+1 hits son cadenas `"1.0"` de versiones y `Decimal("0.5")` — falsos positivos). `float` sí existe fuera del núcleo solver: `simulation.py` (capa presentación ngspice: `math.hypot/atan2/log10`, `rng.gauss`), `equations.py:272` (evaluador de ecuaciones de usuario Fase 6, fuera del path F8), `gum.py` (metrología). **F8-K debe vivir estrictamente en el path sin-`float`** (`mna/`, `ac/small_signal.py`, `math/`).
- **Cero ejecución dinámica** en `engineering/`: sin `eval/exec/compile/__import__/importlib/subprocess/socket`; `re.compile` es regex, no ejecución. Modelos F8-K puramente matemáticos.
- **Determinismo**: nodos/refs/ramas ordenados, init `zero-vector`, digests SHA-256 de estructura (`nonlinear.py:235`) y de solver; J20 (10 corridas, 1 digest) pasa en baseline.

---

## 6. Auditoría matemática y especificación por dispositivo

Notación: todas las magnitudes `Decimal` bajo `make_context()` (prec 50). `exp = ctx.exp`. Contrato overflow: cualquier `exp` que desborde → `Infinity` → llamante retorna `None` (Jacobiano) / residual `None` → `DIVERGED` (causa: evaluación). Parámetros siempre `Quantity` validados (finitos, > 0 salvo flags/zeros declarados), **sin defaults**.

### 6.1 MOSFET Level 1 / Shichman-Hodges (tipo `M`, 4 pines D/G/S/B)

**Letra**: `M` (convención SPICE; J19 ya la reserva como "unsupported"). **Pines**: `("D","G","S","B")` — bulk explícito (el uso discreto de 3 terminales ata B a S en la netlist; sin bulk no hay efecto cuerpo honesto). **Parámetros requeridos** (todos explícitos): `polarity ∈ {NMOS, PMOS}`, `Kp` (A/V², transconductancia), `Vto` (V, > 0 como magnitud), `Lambda` (1/V, ≥ 0; `Lambda = 0` desactiva modulación de canal honestamente), `Phi` (V, ≥ 0), `Gamma` (√V, ≥ 0; `Gamma = 0` desactiva cuerpo).

Ecuaciones (NMOS; PMOS = mismos escalares con `V_GS=−(V_G−V_S)` etc. por intercambio de signo, patrón BJT NPN/PNP):

```text
VGS = VG − VS,  VDS = VD − VS,  VSB = VS − VB
Vth = Vto + Gamma·(sqrt(max(Phi + VSB, 0)) − sqrt(Phi))     [Gamma=0 → Vth=Vto]
Vov = VGS − Vth                                            [sobremarcha]
cutoff:    Vov ≤ 0                       → ID = 0
triodo:    Vov > 0, 0 < VDS < Vov         → ID = Kp·(Vov·VDS − VDS²/2)·(1 + Lambda·VDS)
saturación:Vov > 0, VDS ≥ Vov            → ID = (Kp/2)·Vov²·(1 + Lambda·VDS)
```

Corrientes terminales (entrantes): `ID_d = +ID`, `ID_s = −ID`, `ID_g = 0`, `ID_b = 0` (aislante + unión cuerpo ideal en F8-K; corriente de cuerpo = 0 por alcance). KCL: `ID_d + ID_s = 0` idéntico.

Derivadas (Newton + linealización AC común `mos_jacobian_4x4`):

```text
cutoff:  todas cero.
triodo:  ∂ID/∂VGS = Kp·VDS·(1+Lambda·VDS);  ∂ID/∂VDS = Kp·(Vov − VDS)·(1+Lambda·VDS) + Kp·(Vov·VDS − VDS²/2)·Lambda
         ∂ID/∂Vth = −∂ID/∂VGS;  ∂Vth/∂VSB = Gamma/(2·sqrt(Phi+VSB))  [0 si Gamma=0 o Phi+VSB≤0]
saturación: gm = ∂ID/∂VGS = Kp·Vov·(1+Lambda·VDS); gds = ∂ID/∂VDS = (Kp/2)·Vov²·Lambda; gmb = gm·(∂Vth/∂VSB) con signo vía cadena
```

Stamp MNA (filas/cols D,G,S,B; G sin fila de corriente — puerta ideal no consume): `J[r][c] += s_r·s_c·g` con `s = (+1 D, 0 G, −1 S, 0 B)` para el canal, más columna cuerpo vía `∂ID/∂VB = −∂ID/∂VSB`. **Sin incógnitas nuevas** (igual que D/Q). Fronteras: en `VDS = Vov` ambas ramas coinciden en valor (`Kp·Vov²/2·(1+Lambda·Vov)`) pero la derivada `∂ID/∂VDS` salta (`Kp·Vov·Lambda·…` vs triodo→0 en el límite sin Lambda… con Lambda hay salto finito) — discontinuidad de Jacobiano aceptada y amortiguada por el backtracking de decremento estricto (mismo tratamiento que el codo diodo/BJT); documentar en tests de región.

Unidades: Kp A/V² (tupla derivada), Vto/Phi V, Lambda 1/V, Gamma √V (adimensional-mag √V como `Quantity` con dimensión de raíz de tensión — validar magnitud ≥ 0; dimensión exacta a definir en implementación contra `units.py`).

### 6.2 JFET (tipo `J`, 3 pines D/G/S)

**Letra**: `J` (SPICE). **Parámetros**: `polarity ∈ {NCHAN, PCHAN}` (aceptar alias NJF/PJF solo si se documentan; por defecto NCHAN/PCHAN), `Idss` (A > 0), `Vp` (V > 0 magnitud de pinch-off), `Lambda` (1/V ≥ 0).

```text
VGS, VDS como en §6.1 (NCHAN; PCHAN por signo).
cutoff:    VGS ≤ −Vp                                    → ID = 0
triodo:    VGS > −Vp, 0 < VDS < VGS + Vp                 → ID = Idss·[2·(1+VGS/Vp)·(VDS/Vp) − (VDS/Vp)²]·(1+Lambda·VDS)   [nota: Vp>0, VGS negativo en N]
saturación:VGS > −Vp, VDS ≥ VGS + Vp                    → ID = Idss·(1 + VGS/Vp)²·(1 + Lambda·VDS)
```

Corrientes entrantes `(+ID, 0, −ID)` en (D,G,S); Jacobiano 3×3 con la misma estructura de stamp que el BJT (`nonlinear.py:352-372` reutilizable en patrón). Derivadas analíticas por región (cocientes en `Vp`, potencias enteras — sin `exp`, luego **sin riesgo de overflow exponencial**; el único riesgo es `VDS` extremo × `Idss` → chequeo `is_finite` estándar).

### 6.3 Zener (tipo `D` + discriminador de modelo, 2 pines A/K)

**Decisión estructural**: Zener/LED/Schottky/fotodiodo **reusan la letra `D`** (convención SPICE: todos son diodos con `.model` distinto) con parámetro requerido adicional `kind ∈ {RECT, ZENER, LED, SCHOTTKY, PHOTO}`. Esto evita explosión de letras en `_REF_RE`/`COMPONENT_PINS`/`SUPPORTED_TYPES` y refleja la física (todos son uniones de 2 terminales con la misma topología de stamp). `extract_diode_params` actual exige conjunto exacto `{Is,n,Vt}` → la implementación añadirá `extract_diode_variant_params` por kind (cada kind, su conjunto exacto; RECT = comportamiento F8-H bit-a-bit).

Modelo Zener (ruptura inversa explícita, directa = Shockley):

```text
Vd = VA − VK
directa (Vd ≥ 0):  I = Is·(exp(Vd/(n·Vt)) − 1)              [idéntica F8-H]
inversa (Vd < 0):  I = −Is − Iz·(exp(−(Vd + Vz)/(nz·Vt)) − 1)
```

con `Vz` (V > 0, tensión Zener), `Iz` (A > 0, corriente de codo), `nz` (adim > 0). Continuidad: en `Vd = 0`, inversa da `−Is − Iz·(exp(−Vz/(nz·Vt)) − 1) ≈ −Is` (exp(−Vz/…)≈0 pues Vz ≫ nz·Vt) → continua en valor salvo `O(Iz·e^{−Vz/nzVt})` despreciable y **testeable**. Derivada: `g = Is/(n·Vt)·e^{Vd/nVt}` (directa); `g = Iz/(nz·Vt)·e^{−(Vd+Vz)/nzVt}` (inversa) — salto finito en `Vd=0` (de `Is/nVt` a `≈0+Iz/(nzVt)·e^{−Vz/nzVt}`), amortiguado por backtracking. Resistencia dinámica en ruptura = `1/g` emergente (no parámetro). Fuga = `Is` honesta. Sin clipping.

### 6.4 LED (tipo `D`, kind LED)

Shockley puro con dominio de parámetros validado para Vf típica (p. ej. test con `Vf ≈ 1.8–3.3 V` emergente de `Is ∈ [1E-20, 1E-12] A`, `n ∈ [1, 2]`); inversa = bloqueo (`−Is`). **Sin `Rs` en F8-K** (ecuación implícita; limitación honesta §3.2). Sin física óptica (sin lúmenes/espectro). Derivadas = `shockley_conductance` existente.

### 6.5 Schottky (tipo `D`, kind SCHOTTKY)

Shockley puro con `n ≈ 1` y `Is` grande (p. ej. `Is ∈ [1E-9, 1E-6] A` → Vf ≈ 0.2–0.4 V emergente); fuga inversa mayor = el mismo `Is` (honesto). Derivadas existentes. La diferencia con RECT es **dominio de validación + kind**, no ecuación.

### 6.6 Fotodiodo (tipo `D`, kind PHOTO)

```text
I = Is·(exp(Vd/(n·Vt)) − 1) − Iph,     Iph ≥ 0 (A, Quantity, requerida explícita; Iph = 0 = oscuridad)
```

Polaridad: fotocorriente sale del cátodo en convención A→K (signo menos explícito; tercer cuadrante bajo iluminación inversa — testeable contra ngspice con `Isource` equivalente). Oscuridad (`Iph=0`) = Shockley exacto (regresión directa F8-H). Derivada `g = shockley_conductance` (Iph constante no aporta). Sin dinámica óptica/temporal. AC: gd oscura + Iph congelada (abierto incremental).

### 6.7 Tabla de decisión (qué reusa qué)

| Dispositivo | Ecuación base | Reusa código | Nuevo |
|:---|:---|:---|:---|
| MOSFET | Shichman-Hodges §6.1 | patrón `extract_*`, `_NewtonSystem`, `resolve` por signo (BJT) | `mna/mosfet.py`, stamp 4×4, validación Kp/Vto/Lambda/Phi/Gamma |
| JFET | cuadrática §6.2 | mismo patrón | `mna/jfet.py`, stamp 3×3 |
| Zener | Shockley + rama ruptura §6.3 | `shockley_*` directa | rama inversa + `extract` por kind |
| LED/Schottky | Shockley puro | todo F8-H | solo kind + dominios de validación |
| Fotodiodo | Shockley − Iph | `shockley_*` | parámetro Iph + signo |

---

## 7. Integración MNA + Newton (diseño, sin código)

1. **Tipos y pines** (`circuit.py`): `COMPONENT_PINS += {"M": ("D","G","S","B"), "J": ("D","G","S")}`; `_REF_RE` → `^([RCLVIDQEGHFOTMJ]|D)(\d+)$` (añadir `MJ`; D ya está). `models.py`: factories `mosfet()/jfet()/diode_variant()` como placeholders (patrón `diode()/bjt()` actuales).
2. **Lineal** (`problem.py`): `SUPPORTED_TYPES` **inalterado**; `build_mna_problem(..., allow_mosfets=False, allow_jfets=False, allow_diode_variants=False)` — flags nuevos por familia (granularidad mejor que un único `allow_f8k`; permite mensajes UNSUPPORTED precisos). Sin flag → `UnsupportedElementError` (misma frase que D/Q).
3. **`_NewtonSystem`**: listas `mos_list`/`jfet_list` ordenadas por ref + índices D/G/S/B y D/G/S; mapas de params; `residual()` suma `(+ID@D, −ID@S, 0@G, 0@B)` y JFET análogo; `jacobian()` suma los bloques analíticos; no-finitud → `None` (mismo contrato). `_canonical_structure`/`_provenance`/`_summary` añaden `model: kind` + parámetros por ref (digests siguen siendo SHA-256 deterministas).
4. **Convergencia**: política Q1 intacta (cero cambios en RTOL/ATOL/STOL/iteraciones). El backtracking de decremento estricto ya imposibilita oscilación entre regiones MOSFET/JFET/Zener (misma garantía que F8-H §Q4).
5. **H/F**: `dependent.py` + `problem.resolve_control` + `nonlinear.nctrl` rechazan `control_ref` a M/J/D-kind con `InvalidCircuitError` (extensión de 2 líneas por sitio, mismo mensaje que D/Q).
6. **Thevenin/puerto**: sin cambios (rechazo automático).
7. **Compatibilidad atrás**: circuitos sin M/J/D-kind producen bit-a-bit los mismos `(A0,b0)`, residuales y digests (D-RECT ≡ D actual; tests F8-H/I/J lo blindan).

---

## 8. Integración F8-J (contrato de linealización — congelar en DC, stampar en AC)

`SUPPORTED_TYPES` de `small_signal.py:113` += `{"M", "J"}` (las variantes D-kind ya están cubiertas por `"D"`). Nuevos dataclasses `MOSFETSmallSignalParams {gm, gds, gmb, vgs0, vds0, region}` y `JFETSmallSignalParams {gm, gds, …}` (patrón `DiodeSmallSignalParams`/`BJTSmallSignalParams`).

| Dispositivo | Congelado de DC (en `v0`) | Stamp AC incremental |
|:---|:---|:---|
| MOSFET | región + `gm, gds, gmb` de §6.1 | bloque 4×4 (D,G,S,B) con `DecimalComplex(g,0)` |
| JFET | región + `gm, gds` | bloque 3×3 |
| Zener | `g` en `Vd0` (Directa o ruptura según signo) | conductancia A–K (mismo código que D) |
| LED/Schottky | `g_d` | idéntico a D (J10 como plantilla de test) |
| Fotodiodo | `g` oscura; `Iph` congelada | `g` A–K; `Iph` = abierto incremental (fuente DC ideal) |

L/C reactivos, fuentes AC (`ac_mag/ac_phase`) y nulor/transformador: sin cambios. `dc_result` precomputado con M/J debe validarse en `_validate_dc_result_compatibility` (acepta `NonlinearResult` con los nuevos `element_powers`; sin cambios de lógica, solo nuevos refs).

---

## 9. Precisión numérica y estabilidad (requisitos para la implementación)

- **Cero `float`**: todo `Decimal` + `ctx.{add,subtract,multiply,divide,exp,sqrt}`; potencias MOSFET/JFET solo enteras (`Vov²`, `(1+VGS/Vp)²`) vía multiply — prohibido `**` float y `math.pow`.
- **Divisiones**: `1/Vp`, `Is/(n·Vt)`, `Gamma/(2·sqrt)` — denominadores validados > 0 en extract; `sqrt(max(Phi+VSB,0))` blinda dominio.
- **Overflow**: `exp` solo en Shockley/Zener/MOS-sub… (MOS Level 1 y JFET **no usan exp**: ventaja de robustez — registrar en tests). Desborde → `Infinity` → `DIVERGED` (causa evaluación), nunca silencio.
- **Underflow**: `exp(−Vz/nzVt)` ≈ 0 honesto (Decimal lo representa; no es error).
- **Singularidades**: `Lambda = 0` → `gds = 0`/`ro = ∞` (honesto; puede dar Jacobiano singular en topologías sin camino DC — veredicto SINGULAR_JACOBIAN, no cuelgue). `Vov = 0` / `VGS = −Vp`: ramas coinciden en 0 (continuas). `Phi+VSB ≤ 0` → cuerpo como `Gamma = 0`.
- **Región-flapping**: mitigado por decremento estricto del residual + `a_min = 1/1024`; test obligatorio: barrido de `VDS` cruzando `Vov` converge monótonamente.
- **Mal condicionamiento**: `gds` minúscula (Lambda→0 en saturación) + `gm` grande conviven como en BJT (`gF ≫ gR`) — precedente certificado.

---

## 10. Seguridad y determinismo (requisitos)

- Prohibido en código F8-K: `eval/exec/compile/globals/locals/__import__/importlib/subprocess/os.system/shell/socket/red/ficheros`. Solo `Decimal`, `dataclass`, `Enum`, `hashlib`, `json` (igual que `diode.py`/`bjt.py`/`nonlinear.py`).
- Tests AST replican `test_ast_security_scan` + `test_no_float_in_engine` sobre cada fichero nuevo.
- Determinismo: orden `sorted(ref.upper())`, init cero, `json(sort_keys=True)` → SHA-256; test J20-style por familia (10 corridas, 1 digest).

---

## 11. API y modelo de datos (cambios necesarios, por archivo)

| Archivo | Cambio | Motivo / impacto |
|:---|:---|:---|
| `circuit.py` | `COMPONENT_PINS` + `_REF_RE` con `M`, `J` | Sin esto M/J no existen como componentes; impacto nulo en tipos actuales |
| `models.py` | `mosfet()`, `jfet()`, `diode_variant(kind, …)` placeholders | Paridad con `diode()/bjt()`; sin física |
| `mna/mosfet.py` (nuevo) | `MOSParams`, `extract_mosfet_params`, `mos_terminal_currents`, `mos_jacobian`, `mos_companion` | Paralelo exacto a `bjt.py` |
| `mna/jfet.py` (nuevo) | ídem JFET 3×3 | ídem |
| `mna/diode.py` | rama inversa Zener + `extract_diode_variant_params` + `Iph` | RECT bit-idéntico; kinds nuevos aislados |
| `mna/problem.py` | flags `allow_mosfets/jfets/diode_variants`; rechazo H/F→M/J/D | Granularidad de error; lineal intacto por defecto |
| `mna/nonlinear.py` | listas M/J, stamps, provenance/summary, `nctrl` rechaza M/J | Núcleo Newton; Q1 intacta |
| `mna/__init__.py` | re-exports nuevos | API pública |
| `mna/dependent.py` | rechazo control por M/J (+kinds) | Corrientes no lineales no controlan H/F |
| `ac/small_signal.py` | `SUPPORTED_TYPES`+M/J, dataclasses SS, stamps 4×4/3×3, Zener/LED/Schottky/foto vía `g` | Contrato §8 |
| `thevenin/*` | **sin cambios** | Rechazo automático verificado por test |
| Tests §12 | ficheros nuevos + actualización J19 | J19 (`M→UNSUPPORTED`) cambia de premise al existir M: debe reescribirse a letra aún-inexistente o a circuito con modelo inválido |

---

## 12. Test plan (implementación futura; aquí solo diseño)

- **Unit** (por dispositivo): params válidos/inválidos (dimensión, signo, finitud, kind exacto), `I=0` en corte, continuidad en fronteras (`VDS=Vov`, `VGS=−Vp`, `Vd=0` Zener/foto), derivadas vs diferencias centrales, `companion` ≡ paso Newton, signos N/P, `KCL ⇒ ΣI = 0` por dispositivo.
- **Solver**: 1-MOSFET/1-JFET + R + V (bias correcto vs ngspice), saturación/triodo/corte, Zener en ruptura directa e inversa, LED Vf, Schottky Vf baja, foto oscura/iluminada; no-convergencia (`max_iter=0/1` → MAX_ITERATIONS), Jacobiano singular (puentes V en conflicto), extremos (`VDS=50 V`, `VGS=−100 V` → DIVERGED honesto o convergencia amortiguada).
- **Cross-device**: M+Q, J+D, Zener+D level-shifter (plantilla B12), M+O, J+T, circuito universal R/V/I/E/G/H/F/O/T/D/Q/M/J/Zener/LED/Schottky/foto simultáneos (plantilla D15/B15).
- **Regresión**: `test_f8h_nonlinear_dc.py` (69), `test_f8i_bjt.py` (33), `test_f8i_nonlinear_bjt.py` (41), `test_f8j_small_signal_ac.py` (28+benchmark diagnóstico) y suite completa; J19 reescrito.
- **Security**: AST scan por fichero nuevo + `float`-literal scan (AST `Constant: float`) — mismos asserts que F8-J.
- **Determinismo**: 10 corridas/digest por familia + comparación `to_dict`.
- **Oráculo externo**: ngspice 47 (ruta certificada `C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe`) para M1/J1/Z1/L1/S1/P1 con tolerancia heredada `< 1E-4` (mag) / `< 0.05°` (fase AC).
- **Benchmark (diagnóstico, §15)**: escalado N=1..64 por familia; registrar tiempos, iteraciones Newton (objetivo: constante como BJT=7), memoria; **sin asserts normativos de segundos** (lección FIND-PERF-01).

---

## 13. Referencia matemática (cadena de verificación por dispositivo)

```text
Modelo → Ecuación (§6) → Variables (VGS/VDS/VSB/Vd + salidas ID/I) → Unidades (V, A, S, A/V², 1/V)
→ Regiones (predicados exactos) → Derivadas (§6) → Jacobiano (stamp MNA §7)
→ MNA F(x)=A0x−b0+D(x) → Newton amortiguado (Q1) → NonlinearResult + KCL/KVL/Tellegen
```

Cada flecha tiene test cuantitativo asignado en §12. Fórmulas vagas: cero (todas las ecuaciones están cerradas en §6).

---

## 14. Riesgos y open questions

| # | Riesgo / pregunta | Severidad | Mitigación en diseño |
|:---|:---|:---:|:---|
| R1 | Discontinuidad de derivada en `VDS=Vov` / `VGS=−Vp` / `Vd=0` (Zener) → más iteraciones o estancamiento | MEDIUM | Backtracking estricto existente + tests de cruce de región; sin suavizado oculto |
| R2 | `ro=∞` (Lambda=0) → Jacobiano singular en ciertas topologías | LOW | Veredicto honesto SINGULAR_JACOBIAN; test dedicado |
| R3 | `Iph` ¿`Quantity` (A) o incl. nivel lux? | LOW (OQ-1) | **Decidido**: `Quantity` en A, requerida explícita (sin modelo óptico) |
| R4 | Bulk MOSFET: ¿legar `B` flotante? | LOW | `B` debe conectarse (reachability lo exige); documentar amarre a S en tests |
| R5 | Alias `PCHAN/NJF/PJF` | INFO (OQ-2) | Solo `NCHAN/PCHAN` (+`NMOS/PMOS`); alias solo si se documentan en implementación |
| R6 | Sobrecarga de `D` con 5 kinds: ¿confunde regresión F8-H? | LOW | RECT ≡ F8-H bit-a-bit, blindado por los 69 tests intactos |
| R7 | Tiempo N=64 dependiente de máquina (FIND-PERF-01) | HIGH (proceso) | Benchmarks diagnósticos; ver §16 condición 2 |

---

## 15. Blocking findings (criterio §17 de la tarea)

| ID | Enunciado §17 | Estado |
|:---|:---|:---|
| Dependencia no resuelta | Ninguna (§4: todo interno y certificado) | ✅ no bloquea |
| Ambigüedad matemática | Ninguna (ecuaciones cerradas §6) | ✅ no bloquea |
| Incompatibilidad F8-H/I/J | Ninguna (extensión por patrón, §7–8; lineales intactos) | ✅ no bloquea |
| API insuficientemente definida | Definida por archivo/símbolo (§11) | ✅ no bloquea |
| Problema de precisión | Mismo contrato `Decimal`/overflow que F8-H/I; MOS/JFET sin `exp` (más robustos) | ✅ no bloquea |
| Ruptura de determinismo | Mismos mecanismos (orden, digest, init) | ✅ no bloquea |
| Regresión existente | **FIND-PERF-01**: solo umbral de tiempo hw-dependiente; 171/172 verde incl. toda la matemática | ⚠️ condiciona (ver §16), no bloquea el diseño |
| Requisito del roadmap contradictorio | **FIND-DOC-01**: roadmap desactualizado respecto a F8-J | ⚠️ condiciona (ver §16), no bloquea el diseño |
| Modelo físico insuficiente | Todos cerrados en §6 | ✅ no bloquea |

**Conclusión**: ningún criterio §17 se cumple en sentido matemático/arquitectónico. El diseño es completo y la implementación posterior puede ejecutarse de forma determinista y auditable exclusivamente desde este documento.

---

## 16. Definition of Done (para la futura fase de implementación; no ejecutar ahora)

1. ROADMAP.md corregido (condición 1) **antes** de abrir implementación.
2. Umbral perf F8-J dispuesto como diagnóstico (condición 2).
3. `mna/mosfet.py`, `mna/jfet.py`, extensión `diode.py`, flags `problem.py`, stamps `nonlinear.py`, contrato AC `small_signal.py` según §7–8/11.
4. Tests §12 verdes + regresión completa + ngspice `< 1E-4`.
5. AST/no-float/determinismo verdes. Benchmarks registrados sin umbrales normativos.
6. Gate `GATE-F8K.md` de certificación. Sin commits en esta fase de diseño.

---

## 17. Veredicto final

**`F8-K DESIGN READY`**

El alcance está cerrado (§3), la matemática de los 6 dispositivos está especificada con ecuaciones, regiones, derivadas y stamps (§6–8), la integración reusa la arquitectura certificada sin romper F8-H/I/J (§7, §11), y la baseline está medida (§2). Las dos condiciones pre-implementación (ROADMAP.md y umbral perf) son de proceso, no de diseño.

---

### Apéndice A — Archivos analizados (lectura directa)

`docs/roadmap/ROADMAP.md` · `docs/gates/GATE-F8H.md`, `GATE-F8I.md`, `GATE-F8J.md` · `src/academic_core/domain/engineering/circuit.py`, `models.py`, `simulation.py` (parcial, capa presentación), `equations.py:265-290`, `units.py` (parcial) · `mna/__init__.py`, `mna/problem.py` (íntegro), `mna/nonlinear.py` (íntegro), `mna/diode.py` (íntegro), `mna/bjt.py` (íntegro), `mna/solver.py` (vía grep), `mna/dependent.py` (vía grep) · `ac/small_signal.py` (íntegro), `ac/solution.py:30-109` · `math/trig.py` (íntegro), `math/decimal_complex.py` + `math/linsolve/problem.py:120-199` (vía grep/lectura) · `thevenin/port.py:15` · `tests/test_f8j_small_signal_ac.py:747-864` (J19/J20/benchmark/regresión F8-L) · `pyproject/requirements` (no requerido: runner estándar pytest) · historial Git (10 commits) + `git status/diff`.

### Apéndice B — Archivos modificados

`docs/gates/GATE-F8K-DESIGN.md` (este informe — único fichero creado; entregable §18 de la tarea). **Cero modificaciones** en código productivo, tests o documentación normativa existente.
