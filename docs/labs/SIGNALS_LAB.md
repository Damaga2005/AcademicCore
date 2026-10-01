# Laboratorio de Señales y Sistemas — Especificación de diseño

Estado: **especificación con las decisiones D1 a D24 aprobadas (§32)**, revisada contra `MATH_LAB.md` v2 y `CIRCUITS_LAB.md`; sin implementación iniciada · Fecha: 2026-10-01 · Ruta de UI: `engineering/signals`
Ámbito: todo lo de señales que **no** es matemática pura de señales: lectura de espectros (también en sentido inverso), ventanas y resolución, muestreo y reconstrucción, modulación, sistemas LTI visualizados en tiempo y frecuencia, diseño y análisis de filtros FIR e IIR, filtro adaptado, análisis espectral, STFT, multirate, generador de señales, calculadoras, prácticas P0 a P11 de Señales y Sistemas, visores de Tratamiento de la Señal, ejercicios de examen reales como casos de prueba.
Fuentes: guías docentes de GREELEC (UPC) `230913 Señales y Sistemas (SST)` y `230918 Tratamiento de la Señal (TRS)` en `guias_upc/`; material del usuario de SST (Grupo 12) en OneDrive (exámenes 2020 a 2025, teoría, formularios, prácticas P0 a P11), **solo lectura**; el informe `math_catalog/extra_senales.md` (bloques SS-0 a SS-18 y TRS-1 a TRS-8) y los otros cuatro catálogos de `math_catalog/`; `MATH_LAB.md` (motor matemático) y `DIGITAL_DESIGN_LAB.md` (plantilla de estructura); el código real de `domain/engineering/dsp`, `comms`, `symbolic`, `math`, `lab` y `ui/waveform.py`, `ui/logic_analyzer.py`.
Decisión del usuario sobre el reparto (fijada): la **matemática pura de señales** (TF de secuencias, DFT teórica, series de Fourier, convolución por tramos, transformada z, correlación y densidad espectral deterministas, detección y estimación MAP, Neyman-Pearson, Cramér-Rao, Wiener, LMS) vive en `MATH_LAB.md`. **Este documento cubre todo lo demás de señales** y se apoya en el motor de aquel (§23).

---

## 0. Cómo leer este documento

| Sección | Contenido |
|---|---|
| 1 | Objetivo, requisitos del usuario (trazabilidad) y principios |
| 2 | **Punto de partida real**: qué existe en el repositorio, con rutas, y qué falta |
| 3 | Reparto con `MATH_LAB.md` y `CIRCUITS_LAB.md`; arquitectura por capas y mapa de módulos |
| 4 | **Convenciones del curso** (contrato de notación: `f` en Hz, `sinc` normalizada, `F = f/f_m`, `p_L[n]`, dB declarado) |
| 5 | Modelo de datos de señales, sistemas, espectros y figuras |
| 6 | Biblioteca de señales y **generador de señales** (SS-0) |
| 7 | **Sistemas LTI visualizados** en tiempo y frecuencia (SS-1 a SS-4, SS-11) |
| 8 | **Espectros**: DFT, lectura directa y **lectura inversa** (SS-12, SS-14), prioridad máxima |
| 9 | Ventanas y resolución espectral (SS-13) |
| 10 | Muestreo, aliasing y reconstrucción (SS-9) |
| 11 | Modulación y multiplexación: DSB, AM, SSB, FM, digital, FDM, TDM (SS-15) |
| 12 | **Filtros**: plantilla, FIR (ventanas, muestreo en frecuencia, Parks-McClellan), IIR (Butterworth, Chebyshev, elíptico), realización (SS-16, SS-17) |
| 13 | Filtro adaptado, correlador y decisión visual (SS-7 visual, SS-8) |
| 14 | Análisis espectral, STFT y espectrogramas |
| 15 | Multirate: diezmado, interpolación, remuestreo |
| 16 | Cuantización y conversión A/D, D/A (SS-18, parte pequeña) |
| 17 | **Tratamiento de la Señal**: visores y simulaciones sembradas (TRS-1 a TRS-8) |
| 18 | **Prácticas P0 a P11** de Señales y Sistemas |
| 19 | Gráficas y visores interactivos |
| 20 | Calculadoras (catálogo) |
| 21 | Ejercicios, plantilla, corrección y generador sembrado |
| 22 | **Casos de prueba de exámenes reales** (ES-01 a ES-40) |
| 23 | Interoperabilidad: motor de `MATH_LAB.md` §5, `CIRCUITS_LAB.md` y el resto de la app |
| 24 | Motor numérico: vía exacta y vía rápida, rendimiento |
| 25 | Verificación independiente y sellos |
| 26 | Explicación paso a paso |
| 27 | Audio, entrada y salida, formatos y persistencia |
| 28 | Accesibilidad, localización y seguridad |
| 29 | Plan de pruebas y criterios de aceptación |
| 30 | Fases de entrega (SG-0 a SG-17) |
| 31 | Riesgos y límites declarados |
| 32 | **Decisiones D1 a D24 (todas decididas)** |
| 33 | Lo que no se había pedido pero se incluye o se propone |
| A a H | Anexos: fórmulas de ventanas, referencia rápida de fórmulas, formato `signals-lab/1`, mapa de módulos, glosario ES/CA, equivalencias MATLAB/Python, valores dorados medidos, trazabilidad de ids |

Las claves `SS-n` y `TRS-n` remiten a los bloques de `math_catalog/extra_senales.md`; las frecuencias de examen (por ejemplo «≈ 14/29») son de ese informe (recuento manual sobre 29 pruebas, error ±2). **No se repiten aquí**, solo se usan para ordenar prioridades.

---

## 1. Objetivo, requisitos y principios

### 1.1 Objetivo

Que un estudiante de Señales y Sistemas (y, después, de Tratamiento de la Señal) pueda, en una sola página:

1. **Generar o cargar** una señal (analógica modelada o digital, sinusoide, pulso, tren, audio, ruido sembrado) y **verla** en tiempo, en frecuencia y, si procede, en tiempo-frecuencia.
2. **Leer un espectro** como en el examen: de los picos `|X[k]|` y de `N` deducir amplitud, frecuencia, longitud de la ventana y tipo de ventana (**problema inverso**, el último apartado de casi todos los finales), y comprobarlo reproduciendo el espectro con el modelo directo.
3. **Ver qué hace un sistema LTI** a una señal: respuesta impulsional, convolución animada, respuesta en frecuencia (módulo en dB, fase), polos y ceros, salida a sinusoides, eco y su inverso.
4. **Muestrear y reconstruir**: aliasing con tabla y gráfica, antialiasing, reconstrucción ideal y con D/A real (triángulo, retenedor de orden cero) y su filtro compensador.
5. **Modular y multiplexar**: producto por portadora, FDM, TDM, SSB, AM, FM, modulaciones digitales (reutilizando `comms/`), con comprobador de solapes en el eje `F` módulo 1.
6. **Diseñar filtros** desde una plantilla: FIR por ventanas, por muestreo en frecuencia y por Parks-McClellan; IIR por Butterworth, Chebyshev I y II y elíptico más bilineal; ver ceros y polos, medir la plantilla, comparar órdenes, filtrar audio.
7. **Hacer las prácticas P0 a P11** como entorno equivalente a MATLAB (estudio previo, experimentación y comprobación), sin necesidad de MATLAB.
8. **Practicar con ejercicios reales de examen** (parafraseados, con datos sembrados) con corrección determinista y solución modelo paso a paso.
9. En Tratamiento de la Señal: **visualizar** procesos, PSD estimada, detección con ROC, estimación, filtro de Wiener y filtro adaptativo (LMS), con simulación sembrada. La matemática la da `MATH_LAB.md`.

### 1.2 Requisitos explícitos del usuario (trazabilidad)

| Id | Requisito (textual o resumido) | Sección |
|---|---|---|
| R1 | Spec **muy detallado**, en español, solo especificación (no tocar código del repo ni OneDrive/guias_upc) | todo |
| R2 | Lectura de espectros `\|X[k]\|` **en sentido inverso**: de `k`, picos, `N` a `A`, `f`, `L` y ventana | 8, 9 |
| R3 | Ventanas y resolución | 9 |
| R4 | Muestreo y aliasing; reconstrucción | 10 |
| R5 | Modulación AM/FM/DSB/SSB/digital | 11 |
| R6 | Sistemas LTI en el dominio del tiempo y de la frecuencia, visualizados | 7 |
| R7 | Filtros: diseño FIR/IIR (ventanas, Parks-McClellan **solo si procede**, Butterworth/Chebyshev/…) | 12 |
| R8 | Filtro adaptado | 13 |
| R9 | Análisis espectral, STFT/espectrogramas | 14 |
| R10 | Diezmado e interpolación | 15 |
| R11 | Prácticas P0 a P11 de Señales y Sistemas | 18 |
| R12 | Tratamiento de la Señal (guía) | 17 |
| R13 | Gráficas y visores interactivos | 19 |
| R14 | Generador de señales | 6 |
| R15 | Calculadoras | 20 |
| R16 | Ejercicios reales de examen como casos de prueba; corrección | 21, 22 |
| R17 | Accesibilidad, rendimiento, pruebas, fases, riesgos y decisiones D1..D24 (todas decididas) | 28, 24, 29, 30, 31, 32 |
| R18 | Interoperar con el motor matemático (`MATH_LAB.md` §5) y con el laboratorio de circuitos (`CIRCUITS_LAB.md`, por referencia cruzada) | 23 |
| R19 | Respetar las convenciones del curso: `f` ordinaria en Hz, `sinc` normalizada, `F = f/f_m`, `p_L[n]`, dB declarado | 4 |
| R20 | Usar `extra_senales.md` (ids SS/TRS, frecuencias, convenciones, erratas) | 1.4, 4, 22 |
| R21 | Usar `DIGITAL_DESIGN_LAB.md` como plantilla de estructura, estilo, anexos y fases | este documento |

### 1.3 Principios de diseño

1. **Mismo contrato que el resto del proyecto.** La interfaz solo dibuja y pide; la lógica vive en dominio y aplicación, sin Qt (regla «zero solver code» en `ui/`, igual que `ui/waveform.py`, que recibe un `CaptureView` y no ve objetos de dominio).
2. **Exactitud donde se enseña, velocidad donde se mira.** Dos vías numéricas con un solo veredicto (§24): la **vía exacta** (`Decimal`, `dsp/` existente) produce las soluciones y los pasos de los ejercicios; la **vía rápida** (flotante) mueve los visores, el audio y el espectrograma. Cada resultado indica de qué vía viene y la vía rápida se contrasta contra la exacta en puntos sembrados.
3. **Todo resultado es explicable y verificable.** Traza de pasos (misma traza E0 que usa el laboratorio digital) y segundo camino independiente con sello (§25), con los mismos tres sellos de `MATH_LAB.md` §8.1 y §5.9 (`✔ Verificado`, `⚠ Solo numérico`, `✘ Discrepa`).
4. **Cada ejercicio declara sus convenciones**: dB de amplitud o de potencia, ventana simétrica o periódica, `N` frente a `L`, `f_m`, sentido de «100 veces inferior». Es una de las trampas más repetidas del examen (§4.4).
5. **La figura es dato.** Los enunciados traen gráficas que la aplicación no puede leer. El ejercicio ofrece **lecturas** como entradas (`k`, picos, tramos) y **genera** la gráfica a partir del modelo, como comprobación (SS-12, §8.8, §21.2).
6. **Determinismo.** Mismo ejercicio, misma semilla, mismos bytes y mismo *digest* (como `DspDocument.digest`). El ruido es siempre sembrado.
7. **Honestidad numérica.** Si un resultado es aproximado se marca y se da su error; si la plantilla no se alcanza, se dice y se muestra la violación; nunca se «ajusta» un filtro para que parezca válido.
8. **Español por defecto**, identificadores y enumeraciones en inglés, como el resto del repo. Glosario ES/CA en los ids de examen (D17), porque el material fuente está en catalán.
9. **El motor propio da los pasos; las librerías comprueban** (`MATH_LAB.md` §5.8 «Librerías de verificación» y su D1): NumPy, SciPy y SymPy, si están, actúan como oráculos independientes; si faltan, el laboratorio funciona y la comprobación queda marcada como «no contrastada con librería externa».
10. **Lo desconocido se dice.** No hay lectura de gráficas por visión en este laboratorio (decidido en D12); el alumno teclea las lecturas.

### 1.4 Prioridades heredadas de `extra_senales.md`

Las prioridades del informe (P1 a P4) se respetan en el orden de fases (§30). Resumen de lo que **cae en este documento**:

| Prio | Ids | Bloque | Dónde |
|---|---|---|---|
| P1 | SS-12 + SS-13 | DFT, enventanado y **lectura de espectros** | §8, §9 |
| P1 | SS-9 | Muestreo, aliasing, reconstrucción | §10 |
| P1 | SS-1, SS-2, SS-4 | Sistemas, convolución, respuesta en frecuencia (visuales) | §7 |
| P1 | SS-0 | Biblioteca de señales (base de todo) | §6 |
| P2 | SS-15 | Modulación y multiplexación | §11 |
| P2 | SS-11, SS-14 | Eco, reverberación, inverso; DFT circular frente a lineal | §7, §8 |
| P2 | SS-8 | Filtro adaptado | §13 |
| P3 | SS-16, SS-17 | Diseño FIR e IIR | §12 |
| P4 | SS-18 | Cuantización | §16 (pequeño) |
| P2/P3 | TRS-1 a TRS-8 | Visores de TRS | §17 |
| — | MAE | Programación MATLAB | fuera; solo tabla de equivalencias (Anexo F) |

Los bloques SS-3, SS-5, SS-6, SS-7 (matemática), SS-10 y TRS-3 a TRS-8 (matemática) **pertenecen a `MATH_LAB.md`** (bloque 15 «Señales y sistemas deterministas», §4.15, y bloque 16 «Detección y estimación», §4.16); aquí aparecen sus visores y verificaciones numéricas.

---

## 2. Punto de partida real

Verificado leyendo el código del repositorio (lecturas de módulos, no solo de nombres).

### 2.1 Qué existe hoy

**Motor de procesado discreto certificado (F8-P2)** — `src/academic_core/domain/engineering/dsp/`:

| Módulo | Aporta | Límites relevantes |
|---|---|---|
| `sequences.py` (234 líneas) | `Sequence` (secuencia causal uniforme `x[n]`, `n = 0..N−1`, con periodo `T` y unidades), `sample_signal` con recetas `sine`, `cosine`, `constant`, `step`, `impulse`, `geometric` | `MAX_SEQUENCE_N = 65 536`; solo **causal** (`n ≥ 0`): no hay eje `n` negativo (las prácticas usan `n = −9..9`, `p_11[n+5]`); sin ventanas, sin pulso `p_L`, sin diente, sin ruido |
| `dft.py` (264) | `dft` (definición, `Decimal`), `fft` radix-2 (DIT, exacta), `idft`, `ifft`, `dtft_at`, `circular_convolve`, `frequency_bins`, `nyquist_index`, `twiddle` con valores exactos en los ejes | `MAX_FFT_N = 4096`, `MAX_DIRECT_DFT_N = 512`; `N` no potencia de 2 en FFT es `INVALID` («apunta a la DFT directa», sin Bluestein); aritmética `Decimal`: **lenta** para espectrogramas |
| `sampling.py` (214) | `nyquist_verdict` (CLEAN / MARGINAL / ALIASED), `nyquist_rate` (2·f_max), `nyquist_frequency` (f_s/2), `alias_of` (plegado exacto a `[0, f_s/2]`), `reconstruct` (sinc ideal con atajo exacto en los nodos y cota de cola), `sample_times`, `to_sequence_uniform` | Reconstrucción de un solo instante por llamada; sin D/A real (ZOH, triángulo), sin antialiasing |
| `ztrans.py` (255) | `TransferFunctionZ` (`H(z)` con numerador y denominador ascendentes), `series_z`, `feedback_z`, `sensitivity_z`, `complementary_z`, `delay_coeffs`, `z_pair` | Orientada a control digital; `MAX_Z_ORDER` |
| `filters.py` (629) | `bilinear_design` (prototipo `TransferFunctionTF` de `control/` → `H(z)`, con prewarping), `bilinear_back`, `iir_stability` (polos, `|p| < 1`), `sos_decompose` (secciones de segundo orden), `cascade_evaluate`, `linear_phase_report` (simetría par/impar, Tipo I a IV), `fir_group_delay_at` | **No hay prototipos** Butterworth, Chebyshev ni elíptico (el prototipo lo pone quien llama); **no hay diseño FIR** (ni ventanas, ni muestreo en frecuencia, ni Remez) |
| `margins_d.py` (307) | Márgenes de estabilidad en tiempo discreto | Control, no señales |
| `report.py` (198) | `DspDocument` (esquema `SCHEMA`, `dumps`/`loads`, `compare`, `replay`, *digest*) | Serialización canónica a reutilizar |

**Comunicaciones digitales (F8-P4)** — `domain/engineering/comms/`: `pulse.py` (rectangular, `sinc_unit` normalizada con `sinc(0) = 1` exacto, coseno alzado y raíz de coseno alzado, `occupied_bandwidth`), `modulation.py` (`modulate` ASK/PSK/QAM por constelaciones, demoduladores, FSK con integral cruzada, `oversample`, `passband_value`, `bits_to_baseband`), `detection.py` (`matched_filter`, `correlator_decide`, `ml_decide`, `map_decide`, `energy_detect`), `channel.py` (AWGN, ganancia, rotación de fase, desplazamiento temporal con interpolación sinc), `metrics.py` (`q_function`, BER/SER, Shannon, conversiones dB), `simulation.py` (flujos pseudoaleatorios sembrados `uniform_stream`/`gaussian_stream` y Monte Carlo BPSK). Todo en `Decimal`, con topes (`MAX_SPS`, `MAX_SAMPLES`, `MAX_MC_BITS`).

**Motor simbólico y matemático** — `symbolic/` (`expr.py`, `derive.py`, `integrate.py`, `normal.py`, `solve.py`, `steps.py`, `numeric.py`): expresiones exactas de **una variable**, derivadas, primitivas, **registro de pasos**; `math/` (`decimal_complex.py` con `DecimalComplex`, `trig.py` con `decimal_sin/cos/atan2/pi`, `logarithm.py`, `rational.py`, `linsolve/`): `make_context()` es el contexto `Decimal` único.

**Circuitos y laboratorio virtual** — `ac/bode.py` (`log_frequencies`, `magnitude_db`, `unwrap_phases`, `crossing_brackets`, `threshold_bands`, `observed_extrema`, `analyze_bode`), `ac/response.py` (`TransferFunction`), `control/tf.py` y `control/poly.py` (polinomios, `TransferFunctionTF`), `lab/` (`Waveform` **lineal a tramos** sobre muestras comprometidas, `measure_*` de máximo, media, RMS, cruces, periodo y frecuencia, tiempos de subida, `measure_bandwidth`, `function_generator` con `sine`, `pulse`/`square`, `dc`; **triangular, ruido y arbitraria quedan fuera**: «no certified generator»).

**Interfaz** — `ui/waveform.py` (248 líneas): `layout_waveform` puro (geometría determinista sin Qt) + `WaveformWidget` (pinta); solo señales **digitales de dos niveles** (H/L), con etiquetas de texto, marcador de disparo y aviso `×n` cuando varias transiciones caen en una columna. `ui/logic_analyzer.py` (461): analizador lógico. `ui/routes.py` (rutas `engineering/circuits`, `analysis`, `lab`, `digital-logic`, `aerospace`), `ui/modules.py` (índice de módulos, que «agrupa laboratorios reales y nunca inventa capacidades»), `ui/virtual_lab.py`.

**Pruebas relacionadas** — `tests/test_f8p2_dsp.py` (695 líneas), `tests/test_f8p4_comms.py` (683), `tests/test_f8j_small_signal_ac.py`, `tests/test_f8q5_logic_analyzer.py`, `tests/test_f8q6_f15_logic_analyzer.py`, `tests/f8n_lab_common.py`.

**Dependencias** — `requirements.txt` solo pide `PySide6>=6.7`, `beautifulsoup4`, `lxml`, `pypdf`. NumPy 2.5.1 está instalado en el entorno de desarrollo pero **no figura** en los requisitos; SciPy y SymPy **no están** instalados. PySide6_Addons está instalado (incluye `QtMultimedia`).

### 2.2 Qué falta (lagunas verificadas)

| Laguna | Consecuencia |
|---|---|
| **No hay ventanas** (rectangular, triangular, Hann, Hamming, Blackman, Kaiser) ni `p_L[n]` ni «diente» | No se puede enventanar ni medir lóbulos. |
| **No hay espectro «amigable»** (módulo en dB, eje en `F`, `k` y Hz a la vez; lectura de picos) | Falta lo más característico del examen (SS-12). |
| **No hay modelo directo de espectro de sinusoide enventanada** (núcleo de Dirichlet, fuga, escalonamiento) | Sin él no hay ni verificación ni problema inverso. |
| FFT limitada a 4 096 puntos y en `Decimal` | Un espectrograma de 40 s de audio a 44,1 kHz (1 736 688 muestras, caso real de la P1) es inviable. Hace falta vía rápida. |
| Sin generador de ruido, triángulo, diente, chirp, ráfagas, audio | El «generador de señales» no existe (R14). |
| Sin diseño FIR: ventanas, muestreo en frecuencia, Parks-McClellan | P9 (apartados 30 a 34), P10 y P11 (apartado 12) no se pueden reproducir. |
| Sin prototipos Butterworth, Chebyshev I y II, elíptico (Cauer) ni órdenes mínimos | P11 no se puede reproducir. |
| Sin convolución con eje `n` explícito (`nc_conv(x, nxi, y, nyi)` de P2) ni regímenes | Falta la vista por tramos (SS-2, SS-3). |
| Sin respuesta en frecuencia analógica de un sistema definido por `h(t)` o por bloques | SS-4 sin visor. |
| Sin comprobador de solapes módulo 1 (FDM/TDM), sin filtro compensador D/A | SS-15 y SS-9 sin utilidad. |
| Sin STFT/espectrograma, sin periodograma/Welch, sin remuestreo ni diezmado | R9 y R10 sin base. |
| `lab/waveform.py` es lineal a tramos y solo a nivel de laboratorio de circuitos | No sirve como señal de procesado (conversión estructural, §23.3). |
| Sin graficador de señales: `stem`, espectro en dB, plano z, espectrograma, ejes `n`/`F`/`f` | `ui/waveform.py` solo dibuja niveles lógicos H/L. |
| Sin audio (E/S de WAV, reproducción) | P1, P6, P10, P11 usan `audioread` y `sound`. |
| Sin ruta de interfaz de señales | No hay `Route` ni entrada en `modules.py`. |

### 2.3 Lo que se reutiliza sin reescribir

`dsp/` entero (se **amplía** con un paquete nuevo al lado, no se reescribe; regla del repo «N-110: ningún `dsp → lab`»), `comms/pulse.py` y `comms/detection.py` (filtro adaptado, `sinc` normalizada), `comms/simulation.py` (generadores sembrados), `ac/bode.py` (detección de cortes, bandas, extremos, desenrollado de fase), `dsp/report.py` (formato canónico y *digest*), `execution/*` y `application/explain_service.py` (traza E0), el conversor único `to_ui_error` para errores, y el patrón `layout_*` puro + widget pintor de `ui/waveform.py`.

---

## 3. Reparto, arquitectura y mapa de módulos

### 3.1 Reparto entre laboratorios

| Tema | `MATH_LAB.md` | **Este laboratorio** | `CIRCUITS_LAB.md` |
|---|---|---|---|
| TF de secuencias (DTFT), `P_L(F)`, `\|1/(1−a e^{−j2πF})\|²` | cálculo exacto y pasos | **visor** del módulo, fase, periodicidad; comparación numérica | — |
| DFT teórica, `X[k] = X(F)\|_{F=k/N}`, propiedades | cálculo exacto | **lectura de espectros**, relleno de ceros, desincronización, circular frente a lineal visuales | — |
| Series de Fourier, TF de periódicas | coeficientes `c_k`, señal base, `X(f) = Σ c_k δ(f − kf₀)` | visor de líneas, suma parcial, salida de un LTI paso bajo | — |
| Convolución por tramos (analógica y digital) | integrales por tramos exactas, regímenes | **animación** reflejar y desplazar, `stem`, regímenes, comparación con DFT | — |
| Transformada z, ROC, `H(z)`, `h[n]` | exacto | **plano z** (polos, ceros, círculo unidad), respuesta en frecuencia, eco | — |
| Correlación y PSD deterministas | `r_x`, `S_x`, Wiener-Khinchin | **visor**, estimación numérica, retardo del pico, filtro adaptado | — |
| Detección MAP, Neyman-Pearson | exacto | **ROC**, histogramas, Monte Carlo sembrado | — |
| Estimación, Cramér-Rao, MVUE | exacto | varianza empírica frente a cota | — |
| Wiener, ecuaciones normales | exacto | identificación, ecualización, predicción visuales | — |
| LMS y NLMS | análisis de convergencia | **curva de aprendizaje**, superficie de error, simulación | — |
| **Muestreo, aliasing, reconstrucción** | (teorema en EDT) | **todo** | convertidores como circuito |
| **Modulación y multiplexación** | `Π`, deltas, desplazamiento en TF | **todo** (visor, comprobador de espectro) | etapas analógicas |
| **Ventanas, resolución, lectura inversa** | `W(F)` teórica | **todo** | — |
| **Diseño FIR** (ventanas, muestreo en frecuencia, Remez) | fórmulas cerradas de plantilla y `δ_p`, `δ_a` | **todo el diseño y medida** | — |
| **Diseño IIR** (Butterworth, Chebyshev, elíptico, bilineal) | orden mínimo Butterworth en forma cerrada (SS-17) | **todo el diseño**, SOS, comparación | **realización** del filtro **analógico** (Sallen-Key, etc.; §10.11) y su Bode |
| Respuesta en frecuencia analógica, Bode de `H(s)` | `H(f) = TF{h}` por definición | visor de `\|H(f)\|` de un sistema por `h(t)`/bloques | **Bode de circuitos** (`ac/`, `CIRCUITS_LAB.md` §8.9.1; BL-AC-7, CI-AC-36/37) |
| STFT, espectrograma, periodograma, Welch | PSD teórica | **todo** | — |
| Diezmado, interpolación, polifase | — | **todo** | — |
| Cuantización y A/D, D/A | `SQNR ≈ 6,02 b + 1,76 dB` (calculadora) | visor de cuantización | circuito ADC/DAC (§10.15) |
| Audio, generador, instrumentos virtuales | — | **todo** | generador de funciones del laboratorio virtual (`lab/stimulus.py`) |

Regla de frontera: **si un resultado es una fórmula cerrada con pasos, lo calcula `MATH_LAB`; si es una medida, un diseño numérico, una simulación o una gráfica interactiva, es de aquí.** Siempre se contrastan entre sí (§23). Las secciones de `MATH_LAB.md` (v2) y de `CIRCUITS_LAB.md` se citan **por nombre y número**, verificados el 2026-10-01 («§5.3 Verificación independiente»); si la numeración cambia, manda el nombre.

### 3.2 Arquitectura por capas

Respeta la arquitectura del proyecto (dominio puro → aplicación → UI; sin Qt fuera de `ui/`; ningún `dsp → signals`).

```
domain/engineering/signals/               NUEVO (al lado de dsp/, no lo sustituye)
  model.py          Signal, Axis, Window, Spectrum, FilterSpec, FilterDesign, Figure
  conv.py           convenciones (f/F/k, dB declarado, ventanas simétricas o periódicas)
  backend.py        adaptador numérico: NumPy opcional o Python puro (D2, §24.3)
  library.py        pulsos, trenes, p_L[n], diente, exponenciales, chirp, ruido sembrado
  generator.py      generador de señales (especificación → muestras)
  windows.py        rectangular, triangular, Hann, Hamming, Blackman, Kaiser, flat-top; W(F)
  spectrum.py       DFT/FFT rápida, relleno de ceros, módulo/fase/dB, picos
  spectral_model.py modelo directo: sinusoides enventanadas (Dirichlet), fuga, escalonamiento
  spectral_read.py  LECTURA INVERSA: de k, picos y N a A, f, L, ventana + ambigüedades
  resolution.py     resolución, separación mínima, bins por lóbulo
  lti.py            h[n]/h(t) → salida, respuesta en frecuencia, polos y ceros, eco e inverso
  conv_view.py      convolución con eje n/t explícito, regímenes, puntos de ruptura
  sampling.py       muestreo, aliasing, plegado, reconstrucción, D/A real, compensador
  modulation.py     DSB, AM, SSB, FM, FDM, TDM, comprobador de solapes módulo 1
  fir_design.py     ventanas, muestreo en frecuencia, Remez (Parks-McClellan)
  iir_design.py     Butterworth, Chebyshev I/II, elíptico, bilineal con prewarping, SOS
  template.py       plantilla (fp, fa, ap, aa), tolerancias δp δa, medida de cumplimiento
  matched.py        filtro adaptado, correlador, decisión con ruido sembrado
  stft.py           STFT, espectrograma, periodograma, Welch
  multirate.py      diezmado, interpolación, remuestreo racional, polifase
  quantize.py       cuantizador, SQNR
  process.py        procesos sembrados, PSD estimada, ROC, Wiener y LMS (visor)
  exact.py          puente a la vía exacta (dsp/ en Decimal)
  verify.py         segundos caminos y sellos
  errors.py         SignalsError y códigos
application/
  signals_lab.py        fachada del laboratorio (casos de uso)
  signals_exercises.py  catálogo de ejercicios, generador sembrado, corrector
  signals_practices.py  guiones de las prácticas P0 a P11
  signals_audio.py      E/S de WAV, reproducción (puerto), límites
  signals_explain.py    lecciones paso a paso (traza E0)
  signals_export.py     CSV, WAV, PNG/SVG, informe de práctica
infrastructure/
  audio.py              reproducción (QtMultimedia) y decodificación opcional de MP3
  oracles.py            NumPy / SciPy / SymPy opcionales como comprobadores
ui/
  signals_page.py       página `engineering/signals` y pestañas
  plot/                 NÚCLEO DE GRÁFICAS compartido (stem, línea, dB, plano z, espectrograma)
  signals_*_view.py     vistas por pestaña (§3.3)
```

Reglas de dependencia: `signals/` importa `dsp/`, `comms/pulse`, `comms/detection`, `comms/simulation`, `math/`, `symbolic/` y `ac/bode`; **nunca** importa `lab/` ni `ui/`; el puente a `lab.Waveform` es estructural y vive en `application/` (como ya dicta el docstring de `dsp/sequences.py`). `dsp/` no importa `signals/`.

**Nota de rutas.** Las rutas de este documento usan el árbol actual (`domain/engineering/`). `CIRCUITS_LAB.md` §3.8 renombra ese paquete a `domain/circuits/` (fase CI-R) y declara que `dsp/` **sale** hacia este laboratorio, mientras `comms/` se queda allí (su D7). `signals/` y `dsp/` permanecen **hermanos** estén donde estén; SG-0 coordina el destino físico con CI-R antes de crear ficheros (§30).

### 3.3 Pestañas de la página

`Señales` (generador y biblioteca) · `Sistemas` (LTI, convolución, polos y ceros, eco) · `Espectro` (DFT, ventanas, **lectura inversa**) · `Muestreo` · `Modulación` · `Filtros` (plantilla, FIR, IIR, comparación) · `Correlación` (adaptado, detección) · `Espectrograma` · `Multirate` · `Procesos` (TRS) · `Prácticas` · `Ejercicios` · `Calculadoras`. Una **barra de cadena** común muestra la señal activa, su origen (generador, fichero, ejercicio), `f_m`, longitud, y el estado de verificación.

### 3.4 Un modelo, varias vistas

La **señal** (`Signal`) es el objeto central; cualquier vista puede generar las otras:

```
Especificación (generador / ejercicio)  ⇄  muestras x[n]  ⇄  espectro X[k] / X(F)
        ⇅                                       ⇅                    ⇅
  expresión exacta (MATH_LAB)            sistema LTI h[n]       espectrograma / PSD
        ⇅                                       ⇅
     audio WAV                          polos y ceros H(z)  ⇄  plantilla y filtro
```

Cada flecha es una función del dominio con prueba de ida y vuelta y se valida por segundo camino (§25).

---

## 4. Convenciones del curso (contrato de notación)

Son las del formulario oficial de la asignatura (`extra_senales.md` §2). Si el laboratorio usara otras, las soluciones modelo no coincidirían con las del profesor. **Todas se muestran** en el panel «Convenciones» de cada pantalla y cada ejercicio declara las suyas.

### 4.1 Tabla de convenciones

| # | Convención | Definición exacta | Consecuencia en el laboratorio |
|---|---|---|---|
| C1 | Frecuencia ordinaria `f` en Hz | `X(f) = ∫ x(t) e^{−j2πft} dt`; `x(t) = ∫ X(f) e^{j2πft} df` | Los ejes analógicos son en Hz. La frecuencia angular `ω = 2πf` solo aparece en un conversor explícito. Nunca `ω` por defecto. |
| C2 | `sinc` **normalizada** | `sinc(x) = sin(πx)/(πx)`, `sinc(0) = 1` | Igual que `numpy.sinc` y `sinc` de MATLAB y que `comms.pulse.sinc_unit` (con `sinc(0) = 1` exacto). No existe la `sinc` sin normalizar. |
| C3 | Pulso y triángulo | `Π(t)` centrado de ancho 1; `Λ(t)` triángulo de ancho 2 (soporte `[−1, 1]`). `Π(t/T) ↔ T sinc(Tf)`; `Λ(t/T) ↔ T sinc²(Tf)` | El valor de `Π` en los saltos (`1/2` o `1`) no cambia ni la energía ni la TF; se declara y se dibuja con círculo abierto o cerrado. |
| C4 | Frecuencia digital normalizada | `F = f/f_m`. `X(F)` periódica de periodo 1. `F ∈ [−0,5; 0,5)` o `[0, 1)` seleccionable | Todos los espectros digitales muestran **dos periodos opcionales** (`[−1, 1]`), como en la P6. |
| C5 | DFT | `X[k] = X(F)\|_{F=k/N}`; `X[k] = Σ_{n=0}^{L−1} x[n] e^{−j2πkn/N}` (sin factor `1/N`); `k > N/2` equivale a la frecuencia `k − N`; `f_k = k f_m/N` | Igual que `fft` de MATLAB y NumPy. La inversa lleva `1/N`. El eje de `k`, de `F` y de Hz se ven **a la vez**. |
| C6 | Pulso causal | `p_L[n]` vale 1 para `n = 0..L−1`; se usa con desplazamientos, `p_L[n + M]` | Todas las secuencias de la biblioteca (§6) admiten **origen `n₀` arbitrario**, no solo causal (laguna de `Sequence`). |
| C7 | Diente | `(1 − n/L) p_L[n]` | Biblioteca §6, con la práctica P2. |
| C8 | Correlación | `r_xy(t) = x(t) * y*(−t)` (energía finita) o `lim (1/T)∫` (potencia finita); `S_x = TF{r_x}` | Retardo y atenuación de un canal por el pico de `r_yx` (§13). |
| C9 | dB | `G = 10 log₁₀(\|H\|²/H_ref) = 20 log₁₀(\|H\|/H_ref)`; **cada ejercicio declara si el dato es de amplitud o de potencia** | Control «dB de: amplitud / potencia» visible siempre; la frase «100 veces inferior» dispara el aviso de §4.4-T1. |
| C10 | Energía y potencia | `E = ∫\|x\|² = ∫\|X\|² df`; `P = (1/T)∫_T \|x\|² = Σ\|c_k\|²`; sinusoide `A²/2` | Lo calcula `MATH_LAB`; aquí se mide numéricamente y se contrasta (Parseval por dos caminos). |
| C11 | Sin calculadora | Las soluciones dejan `sinc(1/2) = 2/π`, `0,6366`, etc. | El modo de **cotas racionales** de `MATH_LAB.md` §8.2-A se ofrece para justificar valores como `sinc(1/2)`. |
| C12 | Unidades | Hz, kHz, MHz; s, ms, µs; internamente SI en `Decimal`/`float` | Conversión de unidades con el módulo `units.py` existente. |

### 4.2 Conversores canónicos

| De | A | Fórmula | Nota |
|---|---|---|---|
| `f` (Hz) | `F` | `F = f/f_m` | Valor plegado `F_plegada ∈ [0, 0,5]` aparte. |
| `F` | `k` | `k = N·F` | Si no es entero, el pico cae entre bins (§8.3). |
| `k` | `f` | `f = k·f_m/N` | Para `k > N/2`, `f = (k − N) f_m/N`. |
| `f` | `ω` | `ω = 2πf` | Solo en el conversor. |
| `F` | `Ω` (bilineal) | `Ω = tan(πF)` | Con prewarping (§12.6). |
| `Δk` entre ceros | `L` | `L = N/Δk` | Lectura inversa (§8.5). |
| `L` | resolución | `Δf_res = f_m/L` | No depende de `N` (relleno de ceros no resuelve más). |

### 4.3 Convenciones de presentación

- Las secuencias se dibujan con **`stem`** (como `stem(n, x)` de las prácticas); las señales analógicas con línea.
- El módulo de una DFT se dibuja por defecto con `stem(k, |X[k]|)` para `N` pequeña (como P9) y con línea (`plot`) para `N` grande o con relleno de ceros; el usuario alterna con una tecla y el cambio se explica (**un `plot` de una DFT de `N = 4096` es la envolvente de `X(F)`, no «más datos»**).
- Fase: se muestra **desenrollada** y envuelta; en un cero de `H(F)` la fase salta π y se anota (`P10`, `10.2.2`).
- Ejes con rotulado de unidades siempre (`n`, `F`, `f (Hz)`, `t (s)`, `k`, `dB`).
- Ejes `F` de `−0,5` a `0,5` o de `0` a `1`, y de `−1` a `1` para ver la periodicidad.

### 4.4 Trampas de enunciado que el laboratorio avisa

| Id | Trampa | Qué hace el laboratorio |
|---|---|---|
| T1 | «100 veces inferior»: ¿amplitud (`−40 dB`) o potencia (`−20 dB`)? El final de jun-2021 usa `−60 dB` sobre `\|H\|²` y el de 2022 usa la amplitud, ambos con `h(t) = e^{−t/10}u(t)` | Exige declarar el tipo; muestra la equivalencia en ambos sentidos; calculadora de dB (§20). |
| T2 | `N` frente a `L`: la DFT de `N` puntos de una señal de `L` muestras; `N ≥ L` o aparece aliasing temporal | Aviso rojo si `N < L` y muestra el solape (§8.7). |
| T3 | Pico `A·L/2`, no `A·L`: la sinusoide real se reparte en `±F₀` | La lectura inversa usa `A = 2\|X\|_pico / Σw` y lo explica (§8.5). |
| T4 | Espectro bilateral frente a unilateral (`A/2` frente a `A`) | Selector explícito; por defecto, bilateral del curso. |
| T5 | Ventana simétrica frente a periódica (`hann(L)` frente a `hann(L,'periodic')`) | Se declara; las fórmulas de pico y ceros cambian (§9.3, Anexo A). |
| T6 | Triángulo: `p_M * p_M / M` (longitud `2M−1`, vértice `1`) frente a `bartlett(L)` (extremos 0) frente a `triang(L)` | Biblioteca con las tres, etiquetadas (§9.2). |
| T7 | `fft` de MATLAB y NumPy sin factor `1/N`; Parseval con `1/N` | Constante visible en la fórmula de cada resultado. |
| T8 | `k > N/2` es frecuencia negativa; los picos de `F ∈ (0,5; 1)` están en `N − k` | La lectura inversa los empareja (§8.4). |
| T9 | Convolución circular de `N` puntos frente a lineal de `L₁ + L₂ − 1` | Visor de ambas, mínimo `N` (§8.7, SS-14). |
| T10 | `f_m` mínima: estricta `>` para sinusoides puras (delta en el borde) | `nyquist_verdict` existente (CLEAN / MARGINAL / ALIASED) y aviso (§10). |
| T11 | `log` neperiano frente a decimal en una «duración efectiva» | Calculadora de duración efectiva (`t = T ln 100 ≈ 46 s` para `e^{−t/10}`, ES-20). |

### 4.5 Erratas heredadas de las fuentes (el laboratorio no las reproduce)

Detectadas en `extra_senales.md` §2 y reforzadas con la lectura de las prácticas. El laboratorio **verifica por segundo camino** y, si discrepa de la solución oficial, **lo señala** y explica la diferencia (regla de `MATH_LAB.md` §15.2-1).

| Fuente | Errata | Lo que hace el laboratorio |
|---|---|---|
| Final 10-1-2020, ej. 2.2 | `R_p1p2 = Λ(t−2) + Λ(t+2)` en la opción 2 y `−Λ(t−2) + Λ(t+2)` en las 1 y 3: una de las tres tiene el signo mal; el valor en `t = 0` no la detecta | Caso de prueba **ES-35**: la correlación numérica distingue los tres signos. |
| 2.º parcial 23-5-2023, ej. 2.6a | El enunciado dice `N = 1000` y la figura es de `N = 1500` (la solución lo señala) | **ES-02**: el ejercicio permite fijar `N` de la figura y avisa si difiere del enunciado. |
| Final 13-1-2020, ej. 3 | El código MATLAB usa `f(i)` donde la variable es `fi(i)` y reutiliza `f` | Los guiones de §18 usan nombres sin colisión. |
| Informe propio de la P5 (a confirmar) | La TF del triángulo de base `T` se escribió `(T/2) sinc²(T f)`; con `Λ(2t/T) ↔ (T/2) sinc²(T f/2)`, el primer cero está en `f = 2/T` y no en `1/T` | **ES-31**: el visor de ventana mide el primer cero y lo contrasta con la fórmula; se marca como «a confirmar con el profesor» porque solo hay el informe del alumno. |

---

## 5. Modelo de datos

El modelo es de **dominio puro** (sin Qt), inmutable y serializable en formato canónico (como `DspDocument`).

### 5.1 `Signal`

| Campo | Contenido |
|---|---|
| `kind` | `ANALOG_MODEL` (señal analógica descrita por una especificación y evaluada en malla fina), `DIGITAL` (secuencia `x[n]` con `f_m`), `ANALOG_EXACT` (expresión simbólica por tramos del motor de `MATH_LAB`, §23) |
| `axis` | `Axis(origin, step, count, unit)`: para digital, `n₀`, `1`, `L`; para analógica, `t₀`, `Δt`, `count`. **Origen arbitrario** (corrige la laguna de `Sequence`) |
| `fm` | Frecuencia de muestreo en Hz o `None` si la señal es solo una secuencia sin tiempo físico |
| `values` | Tupla de reales o complejos (vía rápida) y, si se pide, copia exacta `Decimal` (vía exacta, §24) |
| `spec` | La **especificación** que la generó (receta, parámetros, semilla): permite regenerarla, verificarla y mostrar el enunciado |
| `unit` | Unidad de los valores (V, Pa, adimensional) |
| `provenance` | `generator`, `file` (con *digest* SHA-256 del contenido), `exercise` (id + semilla), `derived` (cadena de operaciones) |
| `flags` | `causal`, `real`, `periodic(N₀ o T₀)`, `energy_finite`, `power_finite`, `bandlimited(B)` (se infieren o se declaran) |

La causalidad, la realidad y la periodicidad se **infieren y se muestran**, no se suponen.

### 5.2 Otros objetos

| Objeto | Campos y responsabilidad |
|---|---|
| `Window` | `kind`, `L`, `symmetric: bool`, parámetros (`β` de Kaiser), `w[n]`, `sum_w`, `enbw`, `first_null`, `sidelobe_db`, `W(F)` exacta (núcleo de Dirichlet combinado) |
| `Spectrum` | `N`, `fm`, `k`, `F`, `f`, `X[k]` (complejo), `kind` (DFT / DTFT densa / periodograma), `window`, `scale` (`bilateral/unilateral`), `db_of` (`amplitude/power`) |
| `PeakReading` | `k`, `|X|` (con unidad), `incertidumbre` (±0,5 bin y de lectura), opcional `fase` |
| `SpectrumReading` | `N`, `fm` opcional, `peaks[]`, `nulls[]` (posiciones `k` de ceros de lóbulo), `sidelobe_ratio` (opcional), `window_hint` (opcional), `L_hint` (opcional) |
| `ReadingResult` | Hipótesis ordenadas: `(A, F₀, f, L, window)` con **intervalos**, ambigüedades listadas, `consistency` (error del modelo directo contra las lecturas) |
| `System` | `LTI` por `h[n]`/`h(t)`, por `H(z)`/`H(s)`, por ecuación en diferencias, por bloques (eco, ventana móvil, retardo, cascada), con `causal`, `stable` inferidos |
| `FilterSpec` | `kind` (LP, HP, BP, BS), `fm`, `fp`, `fa` (y pares), `αp`, `αa` (dB, **declarado de amplitud**), `δp`, `δa`, `H_ref` |
| `FilterDesign` | `family` (FIR-ventana, FIR-frecuencia, FIR-PM, IIR-Butter, IIR-Cheb1, IIR-Cheb2, IIR-Ellip), `order`, `b`, `a`, `sos`, `zeros`, `poles`, `check` (cumplimiento de plantilla con margen) |
| `Figure` | Figura de ejercicio **como datos**: `pieces[]` (tramos de una señal), `peaks[]`, `curve[]`, `annotations[]`; se dibuja y se compara por eventos con tolerancia (§21.2) |
| `Experiment` | Cadena de bloques de una práctica o ejercicio con parámetros y resultados |
| `SignalsDocument` | Esquema `signals-lab/1` (Anexo C), canónico, con *digest*; versión de motor `ENGINE_VERSION = "sg/1"` |

### 5.3 Ciclo de vida y tamaños

- Una `Signal` rápida admite hasta `2²⁴` muestras (D13); la exacta, hasta `MAX_SEQUENCE_N = 65 536` y FFT de 4 096 (límites actuales de `dsp/`).
- Cuando una operación se pide **con pasos** (ejercicio), si `L > 4096` el laboratorio **no ofrece solución exacta** y lo dice («demasiado grande para la vía exacta; resultado de la vía rápida»).
- Toda `Signal` derivada guarda la cadena de operaciones que la produjo, para reproducirla y para el informe (§27.5).

---

## 6. Biblioteca de señales y generador (SS-0)

Es la base de todos los demás bloques («el primer apartado de los ejercicios de periódicas siempre es *especifica una señal base*», `extra_senales.md` SS-0). La biblioteca vive en `signals/library.py`; el generador es la interfaz que la expone.

### 6.1 Biblioteca (catálogo)

| Familia | Señal | Definición (convenciones de §4) | Parámetros | Referencia teórica |
|---|---|---|---|---|
| Básicas analógicas | `δ(t)`, `u(t)`, `Π(t/T)`, `Λ(t/T)`, `sinc(t/T)`, `e^{−t/τ}u(t)`, `e^{−\|t\|/τ}`, gaussiana, `t·u(t)` | C1 a C3 | amplitud, `T`, `τ`, retardo | TF en `MATH_LAB` |
| Básicas digitales | `δ[n−n₀]`, `u[n]`, `p_L[n]`, **diente** `(1−n/L)p_L[n]`, `aⁿu[n]`, `a^{\|n\|}`, `cos(2πFn+φ)` | C6, C7 | `a`, `L`, `F`, `φ`, `n₀` | P2, P4 |
| Transformaciones del eje | desplazamiento, **escala** `x(t/a)`, **reflexión**, `x[n−n₀]`, `x[−n]`, `x[2n]` (diezmado), `x[n/2]` (expansión) | — | — | SS-0 |
| Combinaciones | suma ponderada de las anteriores; **descomposición de una figura en pulsos básicos** (`2Π−Π`, `Λ−Λ`, tren = pulso base `*` tren de deltas) | — | tramos | SS-0, SS-5 |
| Periódicas | sinusoide, cuadrada (ciclo de trabajo), triangular, diente de sierra, tren de pulsos, tren de deltas, rectificada de media onda | periodo `T₀` o `N₀` | periodo, ciclo, amplitud | SS-5, SS-6 |
| Multitono | suma de sinusoides con frecuencias, amplitudes y fases; **periodo = mcm** (analógica) o `N₀` mínimo con `F·N₀` entero | lista de componentes | — | SS-5, SS-12 |
| Ventanas | rectangular, triangular, Hann, Hamming, Blackman, Kaiser, flat-top (§9) | `L`, simétrica o periódica | `β` | SS-13 |
| Barrido | chirp lineal y logarítmico | `f₀`, `f₁`, duración | — | análisis tiempo-frecuencia |
| Aleatorias **sembradas** | ruido blanco gaussiano y uniforme, **AR(1)**, **AR(p)**, ruido coloreado | semilla, varianza, `a` | semilla | TRS-1, TRS-2 |
| Modeladas | **nota musical** (`f = 440·2^{(n−69)/12}`), **tecla DTMF** (dos tonos), voz sintética | tecla, duración | — | P5, examen de usuarios |
| Con eco | `x[n] + a x[n−L]`, `x[n] + a y[n−L]` (reverberación), inverso | `a`, `L` | — | SS-11 |
| Archivo | **WAV** (con `wave` de la biblioteca estándar), MP3 y otros opcionales (§27) | ruta | recorte, canal | P1, P6, P10, P11 |
| Ejercicio | señal definida por una `Figure` de examen | tramos | — | §21 |

Cada elemento de la biblioteca es una función de dominio **con su gemelo exacto** cuando existe (la sinusoide, `p_L[n]`, `aⁿu[n]` y el impulso están en `dsp.sample_signal`, que se reutiliza para la vía exacta; el resto, en `Decimal` bajo `make_context()`). La **expresión exacta por tramos** de las señales básicas (`Π`, `Λ`, `sinc`, `p_L[n]`, diente) y sus TF las ofrece `MATH_LAB.md` §4.15 («Biblioteca de señales») y §8.2-Q; esta biblioteca es su gemela numérica y se contrasta con ella (§23.1).

### 6.2 Reglas de la biblioteca

1. **Eje con origen arbitrario**: `p_11[n+5]` es la señal del ejercicio 1 de la P4; la biblioteca la produce con `n₀ = −5`.
2. **`Π` y `Λ` con bordes declarados** y exportables a la figura con círculos abiertos y cerrados.
3. **Verificación**: cada generador se comprueba contra su definición evaluada en una malla (`SS-0`: «evaluar la expresión en una malla y comparar con la figura»); dos descomposiciones alternativas de la misma figura (hay tres válidas en P1-2025) deben dar **la misma TF tras periodificar**.
4. **Energía y potencia** de cada señal se calculan al generarla y se muestran (clasificación energía finita / potencia finita / ninguna, SS-6).
5. **Sin aleatoriedad no sembrada**: toda señal aleatoria exige semilla visible; si el usuario no la da, se crea una y se muestra.

### 6.3 Generador de señales (instrumento)

El **generador** es un instrumento virtual, hermano del generador de funciones del laboratorio virtual (`lab/stimulus.py`, que solo da `sine`, `pulse/square` y `dc`). Se justifica uno nuevo porque aquel solo cubre circuitos analógicos y no tiene triangular, ruido, arbitraria ni multitono («no certified generator»). La relación se documenta: el generador de señales puede **exportar** su señal a un `StimulusSpec` del laboratorio virtual cuando es `sine`, `pulse` o `dc` (§23.3).

**Panel del generador**

| Control | Detalle |
|---|---|
| Forma | Selector de familia y señal (§6.1) |
| Parámetros | Amplitud, frecuencia `f` (Hz) **y** `F` (se muestran las dos), fase (rad o grados, declarado), componente continua, ciclo de trabajo, semilla |
| Muestreo | `f_m`, longitud `L` o duración, **origen `n₀`**, ancho de banda declarado `B` (para avisar de aliasing) |
| Suma y producto | Hasta 8 generadores combinados por suma y producto (modulación simple) |
| Ruido | Relación señal a ruido (dB, **declarado de potencia**) o varianza, con semilla |
| Aviso de aliasing | Si alguna componente supera `f_m/2` se muestra la **frecuencia aparente** (`alias_of`) y su `F` plegada (ES-05: `0,52 → 0,48`) |
| Vista previa | Tiempo, espectro y, si procede, espectrograma, con presupuesto de tiempo; sin bloquear la interfaz |
| Salida | A la cadena de bloques, a otra pestaña, a fichero (WAV, CSV), al altavoz, a la calculadora, al editor de ejercicios |

**Ejemplo de especificación textual** (el generador acepta y produce esta forma, útil para ejercicios y pruebas):

```
sine(A=4, f=2000 Hz, fm=8000 Hz, L=30)            # P9, apartado 1
dtmf(key="5", T=15 ms, fm=8000 Hz)                # P5, 5.3
sum( sine(A=3,f=800), sine(A=-5,f=4200) ), T=10 s, fm=16000  # P10, apartado 8
p_L(L=11, n0=-5)                                  # P4, ejercicio 1: p_11[n+5]
tooth(L=6, n0=5)                                  # P2: diente retardado 5 posiciones
noise(kind="gauss", var=1, seed=20260930)
```

### 6.4 Criterios de aceptación del generador

1. Cada señal de §6.1 se genera, se dibuja, se exporta y se regenera idéntica desde su especificación y semilla (mismo *digest*).
2. Un multitono analógico informa de su **periodo mcm** y de su potencia `ΣA²/2`.
3. Un tren de pulsos a `f_m` informa de si se cumple la condición de no solape (§11.6).
4. El aviso de aliasing salta siempre que la frecuencia supere `f_m/2` y da la frecuencia aparente correcta, en ambos sentidos.
5. La señal generada y su gemelo exacto coinciden en las muestras comparables (tolerancia declarada, §24.4).

---

## 7. Sistemas LTI visualizados en tiempo y frecuencia (SS-1 a SS-4, SS-11)

La demostración y el cálculo exacto (`h(t)`, integrales por tramos, `H(z)`) son de `MATH_LAB`; **aquí se ve y se mide**. Cada pantalla de esta sección tiene un botón «Pedir el cálculo exacto» que llama al motor de `MATH_LAB` (§23.1) y contrasta con la medición numérica.

### 7.1 Verificador de propiedades de sistemas (SS-1, ≈ 17/29)

Dado un sistema `y = T{x}` (integral, suma móvil, eco, `sign`, `√(x²)`, producto por `cos`, `y[n] = x[n] + 0,8 y[n−50]`, `α + βz(t)`), el verificador **refuta o no refuta** cada propiedad con señales de prueba sembradas.

| Propiedad | Prueba numérica | Qué muestra |
|---|---|---|
| Linealidad | `T{a x₁ + b x₂}` frente a `a T{x₁} + b T{x₂}` con coeficientes aleatorios sembrados | Las dos curvas superpuestas y la diferencia máxima; si falla, **el contraejemplo** como par de señales |
| Invariancia | `T{x(t−t₀)}` frente a `y(t−t₀)` con retardo sembrado | Idem; la modulación `x(t)cos(2πf₀t)` y `α + βz(t)` fallan (variantes de examen) |
| Causalidad | Dependencia del futuro: cambiar `x` para `t > t₁` y ver si `y(t ≤ t₁)` cambia; en LTI, `h = 0` para `t < 0` | Zona sombreada «futuro» y la salida que cambia |
| Estabilidad BIBO | En LTI, `∫\|h\|` (valores típicos: `e^{−t/T}u(t)` estable; `δ + aδ(t−T₀)` estable con `1 + \|a\|`); en general, entrada acotada sembrada con salida creciente | Valor de `∫\|h\|` o la salida que crece |
| Memoria | Dependencia de valores pasados | Texto |
| Sistema compuesto | Es LTI **solo si todos los bloques lo son**; un bloque no lineal (`sign`) lo rompe aunque lo siga un filtro | Diagrama de bloques con cada bloque coloreado por texto (L / no L) |

**Regla de honestidad:** la prueba numérica **solo refuta**. «No refutada tras 200 pruebas» **no es una demostración**; el sello es `Solo numérico` hasta que `MATH_LAB` aporte el paso algebraico (`MATH_LAB.md` §5.3 y §5.7: se enuncian y se comprueban las hipótesis). «Tiene respuesta impulsional» solo se afirma si el sistema es LTI.

### 7.2 Respuesta impulsional, salida y condiciones (SS-4)

| Elemento | Detalle |
|---|---|
| Entrada del sistema | `h(t)` o `h[n]` de la biblioteca (§6), de una fórmula, o **medida**: se alimenta una `δ` (en digital, `δ` de 501 muestras como pide P10/P11) y se registra la salida |
| Duración efectiva | `t_ef` tal que `\|h(t)\|max/\|h(t_ef)\| ≥ 100`; para `h = e^{−t/10}u(t)`, `t = 10 ln 100 ≈ 46 s` (ES-20), con el convenio de logaritmo y de amplitud o potencia declarado (T1, T11) |
| Salida a señales de prueba | Escalón, pulso, sinusoide, suma de sinusoides, señal del generador |
| Régimen transitorio y permanente | Se marca el instante en que la salida entra en banda `±ε` de la salida estacionaria |
| Energía y potencia de entrada y salida | Valores medidos y, si existe, el exacto de `MATH_LAB`; `E_y = E_x(1 + a²)` si los pulsos del eco no se solapan |

### 7.3 Convolución analógica visualizada (SS-2, ≈ 14/29)

**Vista**: tres paneles alineados en `t`: `x(λ)` y `h(t−λ)` (reflejada y desplazada, con `t` movido por un deslizador o animado), el **producto** con el área sombreada y la salida `y(t)` que se va dibujando.

| Elemento | Detalle |
|---|---|
| **Puntos de ruptura** | Sumas de extremos (borde izquierdo + borde izquierdo, etc.); se marcan en el eje `t` con una línea y su valor; el área cambia de fórmula en cada intervalo |
| Continuidad | Valor y derivada en las rupturas (comprobación de `SS-2`) |
| Descomposición en deltas | `p₁(t) = Π(t) * (δ(t−1) + δ(t+1))` para evitar el solape (se anima cada copia por separado y luego la suma) |
| Controles de verificación | `∫y = ∫x · ∫h`; duración `D_y = D_x + D_h`; comparación con la convolución numérica de malla fina y con la vía TF (producto en frecuencia) |
| Señales de la biblioteca | `Π`, `Λ`, `e^{−t/T}u(t)`, suma de deltas retardadas, ventana móvil |
| Dibujo | Línea para señales analógicas; las deltas con flecha y su área como etiqueta |

La solución modelo con pasos (integrales por tramos, ruptura, resultado) la genera `MATH_LAB`; este visor es la **gráfica enlazada** y la comprobación.

### 7.4 Convolución digital visualizada (SS-3, P2, ≈ 9/29)

| Elemento | Detalle |
|---|---|
| Función de la práctica | `nc_conv(x, nxi, y, nyi)`: devuelve `[z, n]` con el eje `n` correcto: `n = n_xi + n_yi : n_xf + n_yf`, longitud `L_x + L_y − 1` (P2, 2.2). Es **la** laguna de `Sequence` (causal solo): se resuelve con `Signal` de origen arbitrario (§5.1) |
| Tabla de solapes | Matriz fila-columna `x[k]·y[n−k]` con la diagonal de cada `n` resaltada |
| Regímenes | Para `aⁿu[n] * p_L[n]` (por ejemplo `2·0,9ⁿu[n]` con `p_50`, caso 4 de la P2): **tres tramos** (antes, transitorio con suma geométrica, régimen permanente); el visor los colorea y escribe el rango de `n` de cada uno |
| Suma móvil | Sistema de suma móvil de 11 términos |
| Casos de la práctica | Los cinco de la P2 (`5p_5[n] * δ[n−3]`, `5p_5[n−5] * 2δ[n+2]`-tipo, pulso por pulso, `p_50 * 2·0,9ⁿu[n]`, `p_50 * 2cos(2π·0,125 n)`), parametrizados por semilla (ES-10 y siguientes) |
| Verificaciones | `Σy = Σx·Σh`; igual que `conv` directa y que la DFT de `N ≥ L₁ + L₂ − 1` (§8.7) |

### 7.5 Respuesta en frecuencia y filtrado de sinusoides (SS-4, SS-10)

**Vista**: `|H(f)|` en lineal y dB, fase desenrollada y envuelta, retardo de grupo; `H(F)` periódica en `[−1, 1]`.

| Elemento | Detalle |
|---|---|
| Fuente de `H` | `TF{h}` numérica (malla densa o `dtft_at` exacta en puntos), `H(z)` evaluada sobre el círculo, o `H(s)` de un `TransferFunctionTF` |
| Marcas | Máximos y mínimos, ceros, frecuencia de **−3 dB** y de **−60 dB** (los umbrales del curso), ganancia en `f = 0`; usa `ac.bode.threshold_bands`, `crossing_brackets` y `observed_extrema` (ya existen) |
| Salida a sinusoides | Se elige `A + B cos(2πf₁t+φ₁) + C sin(2πf₂t)`; el visor dibuja entrada y salida: `\|H(f₀)\| cos(2πf₀t + φ + ∠H(f₀))` por componente y por superposición |
| Medición | Se simula `x * h` durante un tiempo largo y se **mide** amplitud y fase tras el transitorio, y se compara con la teoría |
| Propiedades | `H(0) = ∫h`; `\|H(f)\| ≤ ∫\|h\|`; si `h` es real, módulo par y fase impar (hermítica); en digital, `H(F) = H*(1−F)` |
| Ancho de banda efectivo | Para elegir `f_m` (SS-4, SS-9) |

Ejemplo dorado ES-20: `h(t) = e^{−t/10}u(t)` ⇒ `H(f) = 10/(1 + j20πf)`; `\|H(0)\| = 10` (20 dB), `\|H(0,2)\| = 0,7933` (−2,01 dB con `H_ref = 1`).

### 7.6 Plano z, polos y ceros (SS-11, P10, P11)

| Elemento | Detalle |
|---|---|
| Plano z | Círculo unidad, ceros (o), polos (×), multiplicidades, región de convergencia sombreada, ejes cuadrados (`axis('square')` de P10) |
| Recorrido de `H(F)` | Un punto sobre el círculo (`z = e^{j2πF}`) con los vectores a cada polo y cero: `\|H\| = K Π\|z−z_i\| / Π\|z−p_i\|`; al mover `F`, se ve por qué el módulo cae cerca de un cero y sube cerca de un polo |
| Estabilidad | `\|p\| < 1` por `dsp.iir_stability` (ya existe); margen al círculo; aviso si algún polo está a menos de `10⁻³` |
| FIR | Ceros de `H(z)`; **simetría cuadrantal** para fase lineal (`h[M−n] = ±h[n]`, `φ = −πMF`); informe `dsp.linear_phase_report` |
| Conversión | `H(z) ↔ H(F)` y a `h[n]` por los primeros términos de la recursión |

### 7.7 Eco, reverberación e inverso (SS-11, P7, ≈ 8/29)

| Sistema | `H(z)` | Geometría y comprobación |
|---|---|---|
| Eco FIR `y[n] = x[n] + a x[n−L]` | `1 + a z^{−L}` | `L` ceros en `\|z\| = \|a\|^{1/L}` y polo de multiplicidad `L` en 0; `\|a\| = 1/2`: **0,9330** con `L = 10` y **0,9659** con `L = 20`; `\|H(F)\|² = 1 + a² + 2a cos(2πLF)`, extremos en `F = m/L` y `(2m+1)/(2L)` |
| Reverberación IIR `y[n] = x[n] + a y[n−L]` | `1/(1 − a z^{−L})` | `L` polos con `\|p\| = \|a\|^{1/L}`; estable si `\|a\| < 1` (ES-12) |
| Eco analógico `h(t) = δ(t) + aδ(t−T)` | `1 + a e^{−j2πfT}` | `\|H(f)\| = \|1 + a e^{−j2πfT}\|`; máximos y mínimos periódicos en múltiplos de `1/T`; con `T = 1 ms`, `a = 1/2`: máximo 1,5 en `k` kHz y mínimo 0,5 en `(2k+1)/2` kHz (P7, ES-22) |
| Sistema inverso `z[n] = y[n] + b z[n−L]` | `H₁H₂ = 1` ⇒ `h₂ = Σ bᵏδ[n−kL]`, **`b = −a`**, `n₀ = L` | Si `\|a\| > 1`, el inverso causal sería inestable y el laboratorio lo avisa (ES-14) |
| Ecualizador de dos bandas | `A h₁ + B h₂` con media y diferencia de muestras | Respuesta de cada banda y combinación |

El inverso se **verifica** aplicando la cascada a una señal de prueba y comprobando `z = x` (SS-11), con error máximo mostrado. Con `T = ¼ s`-tipo y `f_m` dados, la P7 pide calcular `n = T f_m` y `b`: calculadora del eco digital (§20).

### 7.8 Bloques y cadenas

La cadena de bloques (§3.3) permite componer: fuente → eco → filtro → muestreador → DFT, con un **diagrama de bloques** de solo lectura y la señal de cada nodo disponible para cualquier visor. La cadena es **lineal con derivaciones** (no un editor libre de grafos; D14). Cada bloque declara si es LTI.

### 7.9 Criterios de aceptación

1. El verificador refuta `sign`, `α+βz(t)`, la modulación (invariancia) y el eco con `\|a\|>1` inverso (estabilidad) con contraejemplo mostrado, y no refuta eco, ventana móvil, retardo.
2. La animación de convolución marca todos los puntos de ruptura de `Π * Π`, `Π * Λ` y `Π * e^{−t/T}u(t)` y la salida coincide con el cálculo exacto de `MATH_LAB`.
3. `Σy = Σx·Σh` y `D_y = D_x + D_h` se muestran en toda convolución.
4. El visor de plano z reproduce los módulos `0,9330` y `0,9659` de §7.7 con 4 decimales.
5. La salida estacionaria medida coincide con `\|H(f₀)\|` y `∠H(f₀)` con error relativo menor que `10⁻⁶` en la vía exacta y `10⁻⁹` en la rápida (sin ruido).

---

## 8. Espectros: DFT, lectura directa e inversa (SS-12 y SS-14; prioridad máxima)

Es «el tipo de problema más característico de SST (último apartado de casi todos los finales)» y **no está en ningún catálogo** (`extra_senales.md` SS-12). Este apartado es el núcleo del laboratorio.

### 8.1 Modelo directo

Señal base: `x[n] = Σᵢ Aᵢ cos(2πFᵢn + φᵢ) · w[n]`, con `w[n]` ventana causal de `L` muestras (`p_L[n]` si es rectangular).

- Transformada: `X(F) = Σᵢ (Aᵢ/2)[e^{jφᵢ}W(F−Fᵢ) + e^{−jφᵢ}W(F+Fᵢ)]`.
- Rectangular: `W(F) = P_L(F) = sin(πLF)/sin(πF) · e^{−jπ(L−1)F}` (núcleo de Dirichlet): máximo `L` en `F = 0`, ceros en `k/L`.
- DFT de `N ≥ L` puntos: `X[k] = X(F)|_{F=k/N}`; frecuencias `f_k = k f_m/N`.
- **Pico**: `|X|_pico ≈ A·L/2` si `F₀` está lejos de `0` y de `0,5` y de otros lóbulos (T3). En general, `A = 2·|X|_pico / Σw[n]`.
- Si `F₀ = k₀/N` exacto y `L = N`: **un solo bin** (más su imagen `N − k₀`), de valor `AN/2`; si no, **fuga y escalonamiento**.

El modelo directo se implementa en `signals/spectral_model.py` con fórmula cerrada (sin FFT) y con FFT, y los dos se comparan (verificación §25).

### 8.2 Visor del espectro

| Elemento | Detalle |
|---|---|
| Ejes sincronizados | `k`, `F` y `f (Hz)` visibles a la vez; alterna `[0, 1)` frente a `[−0,5; 0,5)` |
| Estilo | `stem` para `N` pequeño; línea para `N` grande o relleno de ceros (con la explicación de T-4.3) |
| Capas | `\|X[k]\|` de la DFT elegida + **`\|X(F)\|` densa** (relleno de ceros, p. ej. 4 096 puntos como en P9-5) + **`\|W(F−F₀)\|` teórica** superpuesta, para ver cómo la DFT *muestrea* la envolvente |
| Lectura con cursor | Cursor sobre un pico: `k`, `F`, `f`, `\|X\|` (lineal y dB), y la **incertidumbre de lectura** (`±1/(2N)` en `F`) |
| Detección de picos | Máximos locales por encima de un umbral; **dos picos** por sinusoide (`k` y `N−k`) emparejados (T8); lóbulos laterales marcados en gris |
| Escala | Lineal, dB de amplitud (por defecto, `20 log₁₀(\|X\|/\|X\|max)`), dB de potencia, declarado (C9) |
| Fase | Módulo y fase de la DFT (P9-14), con la fase lineal de un retardo visible |

### 8.3 Fuga, escalonamiento y precisión de la medida (P9, apartados 1 a 6)

La práctica P9 pide medir la frecuencia y la amplitud de `x[n] = A cos(2πFx n)` con `A = 4`, `fx = 2000 Hz`, `f_m = 8 kHz` y `L = 30` muestras. Valores dorados del modelo (a re-medir por el motor, Anexo G):

| Caso | Datos | Resultado | Nota |
|---|---|---|---|
| a | `fx = 2000 Hz`, `L = N = 30` (`F₀ = 1/4`, `k₀ = 7,5`) | `\|X[7]\| = \|X[8]\| = 38,27`; `\|X[6]\| = \|X[9]\| = 12,94`; `\|X[5]\| = \|X[10]\| = 8,00`; frecuencia estimada `1 866,7 Hz` o `2 133,3 Hz`; amplitud estimada `2·38,27/30 = 2,55` | `AN/2 = 60` es el valor ideal: el pico cae a `38,27` (−3,9 dB, escalonamiento máximo `\|sinc(1/2)\| = 2/π`) |
| b | Idem con `N = 4 096` | Pico `60,0` en `k = 1 024` ⇒ `f = 2000 Hz`, `A = 4` | El relleno de ceros **interpola**, no resuelve más (resolución `f_m/L`) |
| c | `fx = 2147 Hz`, `N = 30` | Pico en `k = 8` con `\|X\| = 59,81`; `f = 2 133,3 Hz` (error `−13,7 Hz`); `A = 3,987` | `F₀ = 0,2684`, `k₀ = 8,05` casi en un bin |
| d | `fx = 2400 Hz`, `N = 30` | `F₀ = 0,3 = 9/30`: **un solo bin** `k = 9`, `\|X\| = 60`, `f = 2400 Hz`, `A = 4` exactos | Condición `N f_x/f_m` entero (P9, enventanado rectangular) |

**Errores mostrados** como en la tabla de la práctica (`valor teórico`, `medida con N = 30`, `error`, `medida con N = 4096`, `error`): la pantalla trae la **tabla de comparación** autogenerada. Se identifican tres fuentes: **escalonamiento** (el máximo de `X(F)` cae entre bins), **fuga** (lóbulos laterales) y **resolución** (lóbulo ancho).

**Refinamiento de la medida** (mejora sobre la práctica, desactivable): interpolación de pico por **cociente de bins adyacentes** invirtiendo el modelo directo (para la rectangular, `|X[k±1]|/|X[k]|` fija `δ = F₀N − k` por bisección), y parábola sobre el logaritmo del módulo para ventanas suaves; se muestra el error residual y se advierte de que es una **estimación**, no una lectura.

### 8.4 Lectura directa (predicción)

Dados `(A, f, φ)` de cada componente, `f_m`, `L`, `N` y la ventana, la pestaña **predice** la tabla de picos: `k` (o intervalo `[k, k+1]`), `\|X[k]\|`, `F`, `f`, y marca las imágenes `N − k` y los lóbulos laterales. Con `N`, `L` y `F₀`, informa de:

- Si `F₀N` es entero (un bin) o no (escalonamiento, pérdida máxima `20 log₁₀\|sinc(1/2)\|` = −3,92 dB para la rectangular).
- Si hay aliasing (`alias_of`): frecuencia aparente.
- Si dos componentes se solapan en el lóbulo principal (`\|F₁−F₂\| < 2/L` para la rectangular; `4/L` para triangular y Hann): interferencia.
- La diferencia con una **DFT con relleno de ceros**.

### 8.5 Lectura inversa (el problema característico del examen)

**Entradas** (`SpectrumReading`): `N`; `f_m` (si se conoce); los **picos** como pares `(k, valor)`; opcionalmente las posiciones `k` de los **ceros** de un lóbulo (`k_z`), el nivel del primer lóbulo lateral, y pistas (tipo de ventana, `L` aproximada). El alumno **teclea las lecturas** porque la aplicación no lee gráficas (D12); la gráfica generada sirve de comprobación.

**Salidas** (`ReadingResult`): hipótesis ordenadas `(A, F₀, f, L, ventana)` con **intervalos** y una lista de **ambigüedades**; el modelo directo reproduce los picos y se muestra el error.

**Procedimiento (cada paso con su «por qué»)**

| # | Paso | Fórmula | Ejemplo (los de examen llevan su id ES; el resto son ilustrativos) |
|---|---|---|---|
| 1 | **Plegado y emparejado**: los picos `k` y `N−k` son una misma sinusoide real; se toma `k ≤ N/2` | `F₀ = k/N`, `f = k f_m/N` (T8) | `k = 250`, `N = 1000`, `f_m = 16 MHz` ⇒ `F₀ = 0,25`, `f = 4 MHz` |
| 2 | **Intervalo de frecuencia** por la resolución de la lectura | `F₀ ∈ [(k−½)/N, (k+½)/N]`; afinado con cociente de bins (§8.3) si hay dos bins vecinos | `±1/(2N)` |
| 3 | **Longitud de la ventana por el primer cero** del lóbulo: `ΔF = 1/L` para la rectangular ⇒ `Δk = N/L` | `L = N/Δk` | `Δk = 18`, `N = 1000` ⇒ `L ≈ 55,6`; con el intervalo de lectura `Δk ∈ [17,5; 18,5]` ⇒ **`L ∈ [54,1; 57,1]`, es decir `{55, 56, 57}`**; el examen toma `L ≈ 55` |
| 3b | Si se da el **`m`-ésimo cero**: `L = m·N/Δk_m` | | quinto cero a `Δk = 500` con `N = 10 000` ⇒ `L = 5·10 000/500 = 100` (ES-02) |
| 3c | Ventana triangular `p_M*p_M/M`, `L = 2M−1`: primer cero en `Δk = N/M` | `M = N/Δk`, `L = 2M − 1` | |
| 3d | Hann: ceros en `±2/L` (primer cero del lóbulo principal), no en `±1/L` | `L = 2N/Δk` | Depende de T5 (simétrica o periódica) |
| 4 | **Amplitud** por el valor del pico | `A = 2\|X\|_pico / Σw[n]` (rectangular: `Σw = L`; triangular: `Σw = M`; Hann simétrica con ceros en los extremos: `Σw = (L−1)/2`; Hann periódica: `L/2`) | `\|X\|_pico = 20`, triangular `M = 10`: `A = 2·20/10 = 4` (P9-11 a 16) |
| 5 | **Ventana por la relación lóbulo principal/secundario** | `G_dB = 20 log₁₀(\|X\|_{pico}/\|X\|_{lat})`; se compara con la tabla del Anexo A (−13,3; −26,5; −31,5; −42,5; −58,1 dB) con tolerancia | `20 log₁₀(383/18,27) = 26,4 dB` ⇒ **triangular** (ES-03) |
| 6 | **Resolución y separación**: dos sinusoides se resuelven si sus lóbulos principales no se solapan | rectangular `\|F₁−F₂\| ≥ 2/L`; triangular y Hann `≥ 4/L` | `L = 40`, `f_m = 16 MHz` ⇒ `Δf_min = 2/40 · 16 MHz = 0,8 MHz` (ES-04) |
| 7 | **Aliasing**: si `F` aparente es `F_a`, la frecuencia real es `f = ±F_a f_m + i f_m` para `i` entero | lista de candidatas | `0,52 → 0,48` (ES-05) |
| 8 | **Desincronización**: la sinusoide dura menos de `L` muestras ⇒ pico más bajo y lóbulo más ancho | modelo con `L_activa < L` | |
| 9 | **Verificación por el modelo directo**: se sintetiza la señal con los parámetros hallados, se hace la FFT y se comparan picos y valores con las lecturas; el error máximo relativo es el criterio de consistencia | | sello |

**Ambigüedades que el laboratorio lista y no resuelve en silencio**

1. `L` por intervalo (`{55, 56, 57}`) y *«pico entre bins»* (frecuencia en un intervalo, no un número).
2. Ventana: a veces dos ventanas (Hann y triangular de igual ancho) son compatibles; se muestran ambas con su coherencia.
3. Si los datos no incluyen la ventana ni los ceros, **no hay solución única**: el laboratorio lo dice y pide el dato que falta.
4. Frecuencias fuera de `[0, f_m/2]`: aliasing posible (paso 7).
5. Con ruido, el pico sube con la media; se avisa.

**Explicación**: cada paso se escribe como en una solución de examen, con la fórmula, los valores sustituidos y el «por qué este método» (`MATH_LAB.md` §5.5b), p. ej. «se usa el primer cero y no el ancho a −3 dB porque la rectangular tiene un cero exacto en `1/L` y su lóbulo no es gaussiano».

### 8.6 Identificar usuario, nota o dígito (finales 2022 y 2024)

Variante de la lectura inversa donde el resultado es una **clase**: «¿qué usuario/nota/dígito es?»

| Aplicación | Tabla de referencia | Reglas |
|---|---|---|
| **Usuarios de una red** (final 2022, ej. 3; frecuencias asignadas en MHz con `f_m = 16 MHz`) | Frecuencias asignadas por el servidor (datos del ejercicio) | **Umbral** de decisión por usuario: punto medio entre el valor esperado del pico (`A·L/2`) y el nivel de fuga máximo de los otros usuarios; **separación mínima** para un tercer usuario sin solape de lóbulos (§8.5-6) |
| **Teclado telefónico** (P5, 5.3) | Filas 697, 770, 852, 941 Hz; columnas 1 209, 1 336, 1 477, 1 633 Hz (estándar DTMF) | Una tecla es **un tono de fila más uno de columna**. Con ventana de `T = 15 ms`, la rectangular tiene primer cero a `1/T = 66,7 Hz` (lóbulo principal completo `2/T = 133 Hz`) y el triángulo de base `T` a `2/T = 133 Hz` (lóbulo completo `4/T = 267 Hz`). El par fila-columna más próximo (941 y 1 209 Hz) está a **268 Hz**: pasa el criterio de no solape de lóbulos justo con el triángulo (267 Hz) y holgado con la rectangular. Compromiso resolución frente a fuga: el triángulo ensancha el lóbulo pero baja los laterales de −13 a −26 dB (cálculo del laboratorio, a contrastar con `tecla.wav`); el visor lo muestra |
| **Nota musical** | `f = 440·2^{(n−69)/12}` | Con `L` dada, advertencia de si la resolución `f_m/L` distingue semitonos adyacentes |

El resultado incluye **la decisión, el umbral razonado y la tasa de acierto con ruido sembrado** (Monte Carlo corto, vía rápida).

### 8.7 Propiedades de la DFT y circular frente a lineal (SS-14, P9 apartados 9 a 29)

| Propiedad | Visualización | Criterio |
|---|---|---|
| **Relleno de ceros** | `N = 32` frente a `N = 512` (P9-9, P9-10): módulo con `.` y `stem`; `IDFT` devuelve `x[n]` y ceros | Los primeros `L_x` valores coinciden con `x[n]` y el resto es 0 |
| **Convolución circular frente a lineal** | `p₆ * p₆` (longitud 11): `N = 16` coincide, `N = 15` coincide, **`N = 9` no** (aliasing temporal en las primeras muestras), **mínimo `N = 11 = L₁ + L₂ − 1`** (P9, apartados 22 a 24) | Tres paneles: lineal, circular de `N`, diferencia; se marca el solape |
| **Retardo circular** | `X[k]·e^{−j2πkn₀/N}` desplaza `x[n]` **circularmente**; con `n₀ = 10` y `N = 512` el vector coincide con `y₁[n]` retardado; con `n₀ = 500` la señal «envuelve» (apartados 19 y 20) | Animación del envolvente |
| **Modulación** `x[n]e^{j2πk₀n/N}` | Desplaza `X[k]` circularmente; `x[n](−1)ⁿ` desplaza `N/2` | Apartado 21 |
| **Hermiticidad** | `X[N−k] = X*[k]`, `X[0] = Σx[n]`, `X[N/2]` real | Completar los valores desconocidos de un `X[k]` incompleto (ejercicio SS-14) |
| **Parseval** | `Σ\|x\|² = (1/N) Σ\|X\|²` | Dos caminos |
| **Correlación por DFT** | `r_y` de 29 muestras exige `N ≥ 29`; `DFT{h[−n]}` | |
| **Filtrado por DFT** | `y = IDFT{DFT{x}·DFT{h}}`, `N ≥ L_x + L_h − 1` (P9, «Aplicació de filtrat amb DFT»); **igualdad en las muestras de `n` pero no «para cualquier `t`»** (comprobación del apartado del estudio previo) | Salida lineal `y_c`, salida muestreada `y(nT)` y salida por DFT |
| **`y[0] = (1/N) Σ Y[k]`** | Atajo del filtro adaptado (§13) | |

**Filtrado con `h(t) = e^{−t/10}u(t)` y `x(t)` pulso de 10 s** (apartado 24 a 29 de P9): se propone `f_m` por la **situación más restrictiva** (ancho de banda efectivo de `h` y de `x`), `L_x`, `L_h` (duración efectiva ≈ 46 s) y `N` apropiado; se compara `y_c = conv`, `y(nT)` exacto y el resultado por DFT, y se explican las **escalas de amplitud** (la convolución discreta suma, la continua integra: factor `T`).

### 8.8 Figura como dato: modelo de «lectura de gráfica»

Los enunciados traen una gráfica de `\|X[k]\|` que la aplicación no puede leer (riesgo 1 de `extra_senales.md` §6). El ejercicio tiene una **`Figure` de tipo espectro** con: `N`, eje `k`, lista de picos `(k, valor)`, lóbulos (`k_z`), nivel lateral. Dos usos:

1. **Generar la gráfica del enunciado** a partir del modelo directo con parámetros sembrados (el alumno ve «la figura del examen» y teclea sus lecturas).
2. **Comparar** la gráfica que el alumno construye con la esperada **por eventos** (picos y ceros dentro de tolerancia), no por píxeles (§21.2).

### 8.9 Criterios de aceptación

1. Para los cuatro casos de §8.3, el motor reproduce los valores a `10⁻⁹` relativo (vía rápida) y `10⁻²⁰` (vía exacta con `N ≤ 512`).
2. La lectura inversa de ES-01 a ES-04 devuelve los resultados del examen, con los intervalos de §8.5, y lista las ambigüedades.
3. La verificación por modelo directo de la lectura inversa reproduce los picos con error `< 10⁻⁶` o declara «no consistente».
4. Con `N < L` el visor avisa de aliasing temporal y muestra el solape.
5. `N` mínimo de la convolución circular y el solape de `N = 9` salen igual que en la práctica (P9-22 a 24).
6. Ningún resultado de la lectura inversa se presenta como único si hay ambigüedad.

---

## 9. Ventanas y resolución espectral (SS-13, ≈ 7/29)

### 9.1 Catálogo de ventanas

`W(F)` es la TF de la ventana causal de `L` muestras; todas las medidas (lóbulo, laterales, ENBW) se **miden con relleno de ceros** y se contrastan con la fórmula cerrada. Valores teóricos o de referencia de la literatura de ventanas; los medidos con un prototipo en NumPy para esta especificación (L = 64, relleno de ceros a 65 536) coinciden dentro de 0,1 dB (Anexo G).

| Ventana | Definición `w[n]`, `n = 0..L−1` | 1.er cero (`F·L`) | Ancho del lóbulo principal (cero a cero) | Lóbulo lateral máx. | `Σw` (ganancia coherente × `L`) | ENBW (bins) | Pérdida por escalonamiento máx. |
|---|---|---|---|---|---|---|---|
| Rectangular `p_L[n]` | `1` | 1 | `2/L` | −13,3 dB | `L` (1) | 1,00 | 3,92 dB |
| Triangular `p_M*p_M/M` (`L = 2M−1`) | `min(n+1, L−n)/M` | 2 (`1/M`) | `4/L` | −26,5 dB | `M` (≈ 0,5) | 1,33 | 1,82 dB |
| Hann | `½ − ½cos(2πn/(L−1))` (simétrica) o `/L` (periódica) | 2 | `4/L` | −31,5 dB | `(L−1)/2` o `L/2` (0,5) | 1,50 | 1,42 dB |
| Hamming | `0,54 − 0,46 cos(2πn/(L−1))` | 2 | `4/L` | −42,5 dB | `≈ 0,54 L` | 1,36 | 1,78 dB |
| Blackman | `0,42 − 0,5cos(2πn/(L−1)) + 0,08cos(4πn/(L−1))` | 3 | `6/L` | −58,1 dB | `≈ 0,42 L` | 1,73 | 1,10 dB |
| Kaiser `β` | `I₀(β√(1−(2n/(L−1)−1)²))/I₀(β)` | depende de `β` | creciente con `β` | decreciente con `β` (`β = 0` es la rectangular) | integral | creciente | decreciente |
| Flat-top | suma de 5 cosenos | muy ancho | ≈ 10 bins | muy bajo | — | alto | < 0,01 dB (medida de amplitud) |

Los valores del flat-top y la dependencia de `β` de la Kaiser se **miden** en SG-2 y se fijan como dorados; no se citan aquí números sin medirlos.

### 9.2 Convenciones de las ventanas (T5, T6)

| Convención | Opciones | Cómo se declara |
|---|---|---|
| Hann y Hamming | **simétrica** (`L−1` en el denominador; `hann(L)` de MATLAB) o **periódica** (`L`; mejor para análisis espectral con DFT) | Casilla «ventana periódica»; cambia `Σw`, el cero exacto y la fórmula de `W(F)` |
| Triangular | `p_M * p_M / M` (vértice 1, extremos `1/M`, longitud `2M−1`; la del curso), `bartlett(L)` (extremos 0), `triang(L)` | Tres entradas con su nombre; la usada en los exámenes es la primera (P9-11: `w = [1:10, 9:−1:1]/10`) |
| Centrada o causal | Centrada en `n = 0` (`n = −9..9`, fase cero) o causal (`n = 0..18`, con el retardo `e^{−j2πF·9}`) | Eje `n` con origen declarado (§5.1); P9 apartados 11 a 13 |
| Normalización | Sin normalizar, a ganancia coherente 1, a energía 1 | Para comparar picos |

### 9.3 Visor de ventanas

| Elemento | Detalle |
|---|---|
| Tiempo y frecuencia | `w[n]` con `stem`; `W(F)` en dB, de `0` a `1`, con relleno de ceros; superposición de hasta cuatro ventanas |
| Medidas automáticas | Primer cero, ancho del lóbulo (`k` y Hz), nivel del lateral máximo (dB), `Σw`, ENBW, pérdida por escalonamiento, pendiente de caída de laterales; **comparación con la fórmula cerrada** |
| Práctica P5 (5.2) | `w₁(t) = Π(t/T)` y `w₂(t) = Λ(2t/T)` con `T = 15 ms`: ventana, `W(f)`, `G_dB = 20 log₁₀(\|W\|/\|W\|max)` |
| Práctica P9 (17, 18) | Anchura de los lóbulos principales de la rectangular y la triangular (en muestras y en frecuencia) y la **relación de nivel lóbulo principal/secundario** (dB, con `20 log₁₀\|·\|`) |
| Medición con cursor | Dos cursores sobre `W(F)` dan `ΔF`, `Δk`, `ΔdB` |
| Explicación | «La rectangular tiene el lóbulo más estrecho (`2/L`) y los laterales más altos (−13 dB); la triangular lo ensancha al doble y baja los laterales a −26 dB» |

### 9.4 Compromiso resolución frente a fuga (demostrador)

Dos sinusoides: una fuerte (amplitud 1) y otra débil (amplitud `α`, ajustable de 1 a `10⁻³`), separadas `ΔF` ajustable; ventana elegible. Se ve (a) cuándo el lóbulo principal las **funde** y (b) cuándo los **laterales de la fuerte tapan** a la débil. El control «¿se distingue?» da el veredicto numérico: pico de la débil por encima del lateral de la fuerte en esa posición y separación mínima. Resultado típico: rectangular resuelve más cerca pero la débil de −40 dB queda tapada por los laterales de −13 dB; Hann/Hamming la dejan ver a costa de separación doble. El demostrador sale de la misma lógica que la separación mínima del ES-04.

### 9.5 Asistente «¿qué ventana uso?»

Según los datos del problema (¿dos tonos próximos?, ¿rango dinámico?, ¿medida de amplitud?, ¿longitud fija?) recomienda una ventana y explica el porqué (`MATH_LAB.md` §5.5b: toda elección de método se justifica): *separación pequeña ⇒ rectangular; rango dinámico alto ⇒ Hamming o Blackman; amplitud exacta con tono entre bins ⇒ flat-top*.

### 9.6 Criterios de aceptación

1. Para cada ventana del §9.1 (salvo Kaiser y flat-top, que se fijan al medir), el primer cero, el lateral y la `Σw` medidos coinciden con la tabla dentro de 0,15 dB y 1 % de `F·L`.
2. La P5 (5.2) y la P9 (17, 18) se completan con las medidas del visor.
3. La lectura inversa (§8.5) identifica una triangular a partir de `20 log₁₀(383/18,27) = 26,4 dB`.
4. El demostrador del §9.4 reproduce el compromiso para tres ventanas con valores medidos.

---

## 10. Muestreo, aliasing y reconstrucción (SS-9, ≈ 15/29)

La teoría («teorema de muestreo, muestreo ideal y real, conversores AD y DA») está en la guía (Tema 3) y el catálogo EDT solo la menciona (Teo. 82, 0 apariciones en examen de EDT): **bloque nuevo** de este laboratorio.

### 10.1 Muestreo ideal y réplicas

`x_m(t) = Σ x(nT)δ(t−nT)` ⇒ `X_m(f) = f_m Σₙ X(f − n f_m)` (convenio del curso; en digital, `X(F)` con `F = f/f_m`, periodo 1).

| Elemento | Detalle |
|---|---|
| Vista espectral | Espectro original (banda `B`, p. ej. un triángulo), **réplicas** en `n f_m`, zonas de solape rellenas con patrón y color; deslizador de `f_m` |
| Veredicto | `dsp.nyquist_verdict(f, f_m)`: `CLEAN` (`f < f_m/2`), `MARGINAL` (`f = f_m/2`, solo en nodos), `ALIASED` (`f > f_m/2`); `nyquist_rate = 2·f_max` (una **tasa**) frente a `nyquist_frequency = f_m/2` (una **frecuencia**) en etiquetas distintas |
| **Frecuencia mínima sin aliasing** | Para señales multicomponente y **tras modular o un sistema** (p. ej. `f_x + 10 Hz` en un trémolo: el ancho de banda máximo tras el sistema manda); el laboratorio calcula `f_m ≥ 2·B_max` con `B_max` mostrado paso a paso |
| Hipótesis | Banda limitada `B`; `f_m ≥ 2B`; **estricta `>`** para sinusoides puras (delta en el borde, T10) |
| Aviso | Si `f_m` es baja, la banda que se pliega y la frecuencia aparente |

### 10.2 Tabla y diagrama de aliasing

Tabla numérica: para cada componente `f`, `f_m`: `F = f/f_m`, **`F` plegada a `[0, 0,5]`**, `f` aparente (`alias_of`, redondeo `.5` hacia arriba, el criterio canónico del código existente), número de pliegues. Ejemplo canónico: `cos(2π·0,52n) = cos(2π·0,48n)` (ES-05). **Diagrama de plegado** (la «escalera» del acordeón): `f` en el eje horizontal, `f_aparente` en el vertical, con los puntos del problema marcados. Con audio, demostración **auditiva** (§27.3): un barrido que sube y «rebota» al pasar `f_m/2`.

La banda `[F − B/f_m, F + B/f_m]` debe quedar **sin solape módulo 1**: el comprobador es el mismo que el de FDM (§11.6).

### 10.3 Filtro antialiasing y plantilla

Especificaciones (SS-9): banda de paso hasta `f_p = B` y banda atenuada desde `f_a = f_m − B`, con tolerancias `α_p`, `α_a` (§12.2). La pantalla propone la plantilla **y deja diseñarla** en la pestaña Filtros. «El filtro ideal no es realizable (no causal)»: se muestra su `h(t) = 2B sinc(2Bt)` truncada y con retardo, y se recuerda que la plantilla da el margen para una versión realizable.

### 10.4 Reconstrucción ideal

`x̂(t) = Σ x[n] sinc((t − nT)/T)` con las garantías de `dsp.reconstruct`: atajo **exacto en los nodos** (`x(mT) = x[m]`, sin evaluar `sin(πk)`), truncado a `lobes` lóbulos con **cota de cola** (`tail ≤ X_max·N_excl/(π·d_min)`) mostrada. Vía rápida para malla fina (visor); vía exacta para el valor en un instante.

| Visor | Detalle |
|---|---|
| Suma de sincs | Cada `x[n] sinc` en un color tenue y la suma en negro; muestra cómo cada muestra «aporta» su lóbulo |
| Error | `\|x(t) − x̂(t)\|` frente al número de lóbulos; cota de cola; efecto de los bordes (truncado) |
| Exactitud en nodos | Marca verde en `t = nT` |
| Comparación | Con la señal original; con el interpolador lineal (`Λ`), cúbico y retenedor |

### 10.5 D/A real: retenedor, triángulo y compensador (final 2022, ej. 2)

El D/A real usa un pulso `p(t)`: `x̂(t) = Σ x[n] p(t − nT)` ⇒ `X̂(f) = P(f) Σₖ X(f − k f_m)` (la réplicas se multiplican por `P(f)`).

| Pulso | `P(f)` | Caída en el borde de banda `f = B` con `B = 0,4 f_m` | Nota |
|---|---|---|---|
| Retenedor de orden cero `Π(t/T)` | `T sinc(Tf) e^{−jπfT}` | `\|sinc(0,4)\| = 0,7568` ⇒ −2,42 dB | Retardo medio de `T/2` |
| Triángulo `Λ(t/T)` (retenedor de primer orden no causal / interpolación lineal) | `T sinc²(Tf)` | `sinc²(0,4) = 0,5728` ⇒ −4,84 dB | El enunciado del final 2022 lo usa con `T = 0,1 ms` (`f_m = 10 kHz`) y `B = 4 kHz` |

**Filtro de reconstrucción exacta**: `H(f) = Π(f/2B) / P(f)`; con el triángulo, `H(f) = Π(f/2B)/(T sinc²(Tf))`: **compensación de hasta +4,84 dB en `f = 4 kHz`**. Es no causal e inestable en su forma ideal: se discute la **realizabilidad** y se proponen las **especificaciones**: banda de paso hasta `B = 4 kHz` con la ganancia compensadora, banda atenuada desde `f_m − B = 6 kHz`, tolerancias elegidas por el alumno (ES-15). Valores dorados de ES-15: `f_a = f_m − B = 6 kHz`; compensación `+4,84 dB` (triángulo) o `+2,42 dB` (ZOH) en `4 kHz`.

### 10.6 Muestreo real (guía)

Muestreo con pulso de duración finita `τ`: **natural** (`x(t)Σp((t−nT)/τ)`: `X(f) = Σ c_k X(f − k f_m)`, `c_k = (τ/T) sinc(kτ/T)`) y **instantáneo con retención**. Se muestra el espectro, la **deformación en banda** (apertura) y el cambio frente al ideal; es una pantalla opcional de la guía y **no** aparece en los exámenes leídos.

### 10.7 Submuestreo de paso banda (extra)

Muestreo de señales de paso banda (frecuencia de muestreo mínima `2f_H/⌊f_H/B⌋`) y zonas permitidas: una pantalla propuesta (D19), fuera del curso de SST pero útil para modulación; no entra en el orden de fases salvo petición.

### 10.8 Criterios de aceptación

1. `alias_of` reproduce `0,52 → 0,48`, `f > f_m/2` y las frecuencias de P9 (`f = 2 kHz`, `f_m = 8 kHz`, `F = 1/4`).
2. La reconstrucción de una señal de banda limitada a `0,25 f_m` con 64 lóbulos tiene error máximo declarado y la cota de cola siempre mayor que el error observado.
3. El compensador de ES-15 sale `+4,84 dB` y `+2,42 dB`.
4. El comprobador de solapes sobre un espectro replicado concuerda con `nyquist_verdict`.
5. La tabla de aliasing es la misma para un conjunto de entradas por la vía exacta (`Decimal`) y por la rápida.

---

## 11. Modulación y multiplexación (SS-15, ≈ 11/29)

### 11.1 Principio

`y(t) = x(t) cos(2πf₀t)` ⇒ `Y(f) = ½[X(f − f₀) + X(f + f₀)]`: producto en tiempo = convolución con deltas en frecuencia (desplazamiento y escala `1/2`). En digital, `cos(2πFn)` con `F = 1/4` (traslación a `f_m/4`) o `F = 1/2` (`(−1)ⁿ`, traslación a `f_m/2`). El cálculo simbólico de la TF lo da `MATH_LAB`; aquí el **visor de espectro antes y después**, con ocupación mostrada.

### 11.2 Esquemas incluidos

| Esquema | Qué se ve | Parámetros | Notas |
|---|---|---|---|
| **DSB-SC** | Espectro desplazado a `±f₀`, ancho `2B` | `f₀`, `B` | Recuperación síncrona |
| **AM convencional** | Portadora + bandas laterales; envolvente | índice `m`, `A_c` | Potencia de portadora y laterales; eficiencia `m²/(2+m²)`; sobremodulación `m > 1` |
| **SSB** (USB y LSB) | Una sola banda lateral | filtro de banda o **transformada de Hilbert** (FIR de tipo III con ventana) | Compara anchura con DSB |
| **FM y PM** | Líneas de Bessel `J_n(β)` en `f_c ± n f_x`; ancho de Carson `2(Δf + f_x)` | `Δf`, `f_x`, `β` | Para `β = 1`: `J₀ = 0,7652`, `J₁ = 0,4401`, `J₂ = 0,1149`; demodulación por derivación y envolvente |
| **Digitales** | ASK, PSK, QAM, FSK por **constelaciones** de `comms/` (`modulate`, `oversample`, `passband_value`); espectro con pulso rectangular, coseno alzado o raíz de coseno alzado (`occupied_bandwidth`) | `M`, `R_s`, `α` | Reutiliza `comms/`; no se reimplementa |
| **Inversor de banda** | Modular + paso bajo | `f₀ = B` | Examen SS-15 |
| **TDM** | `y = x Σ p(t − nT)`; tramas de varios canales | `T`, `D`, `N` | §11.7 |
| **Digital `cos(2πFn)`** | Traslación en `F` con módulo 1 | `F` | Examen |

### 11.3 Demodulación y recuperación

| Método | Detalle |
|---|---|
| Síncrono | `y(t)·cos(2πf₀t) = x(t)/2 + (x(t)/2)cos(4πf₀t)` y paso bajo; **escala** para compensar la ganancia del filtro (en la solución del examen aparece un factor `2/B`, según el filtro usado) |
| Error de fase `φ` | Amplitud `cos φ` (desvanecimiento total en `φ = π/2`) |
| Error de frecuencia `Δf` | Batido `cos(2πΔf t)` |
| Detector de envolvente | AM con `m ≤ 1` |
| Hilbert | SSB: `x(t)cos − x̂(t) sin` |
| Verificación | Se compara la señal recuperada con la entrada: error cuadrático normalizado y retardo del filtro |

### 11.4 Banda limitada previa

Si `f_m` es demasiado alta o hay solape con el replicado, se limita la banda con un paso bajo ideal truncado `2B_x sinc(2B_x t)` (SS-15). El diseño usa `h[n] = 2B sinc(2Bn)` con `n = −M..M` y `L_h = 2M + 1` (P6) con la **ventana elegida** (§12.3).

### 11.5 FDM: multiplexación en frecuencia

Varias señales de banda `B_i` se trasladan a portadoras distintas y se suman. El planificador (**utilidad nueva**, SS-15) recibe las bandas y calcula:

- ocupación **bilateral** total (suma de anchos);
- las portadoras mínimas;
- la `f_m` mínima para que **ningún intervalo se solape módulo 1**.

Los valores del informe de referencia (`f_m ≥ 8B = 80 kHz` para tres señales de 10 kHz; `f_m ≥ 120 kHz`) dependen de **qué significa `B`** en cada enunciado (banda unilateral o bilateral, con o sin banda base): el comprobador usa la definición que declara el ejercicio y la muestra, y los casos ES-16 y ES-17 se cierran contra la solución oficial del examen cuando se cargue el enunciado.

### 11.6 Comprobador de solapes módulo 1

Entrada: lista de señales con su banda ocupada `[F_i^−, F_i^+]` (en `F`, módulo 1) o `(f_i, B_i)` y `f_m`. Salida: **mapa de ocupación** en `[0, 1)` con barras de color y etiqueta (no solo color: patrón por señal), lista de **solapes**, y la `f_m` mínima. Algoritmo: intervalos cerrados módulo 1 con operación de unión; casos de borde (`F = 0,5`, intervalos que cruzan `1`) con pruebas dedicadas. Es **el mismo componente** que usa el aviso de aliasing del generador (§6.3) y del muestreo (§10.2). Verificación por simulación: tonos sembrados + FFT + recuperación + comparación.

### 11.7 TDM

`y(t) = x(t) Σ p(t − nT)`: con `N` canales y `f_m ≥ 2B`: `T ≤ 1/(2B)` y duración de cada ranura `D ≤ T/N` (SS-15). Visor de tramas con códigos de color y etiquetas de canal, y la recuperación por muestreo y filtrado.

### 11.8 Práctica P6 en este bloque

`f_m = 16 kHz`, dos señales de audio (10 a 15 s cada una) con ancho de banda mínimo `B_Hz = 4 kHz`, una modulada con `F₁ = f₁/f_m`; ambas **limitadas en banda** con `h_M[n] = 2B sinc(2Bn)`; canal útil `F_max = 0,5`; `Y(F)` con dos bandas; demultiplexor con las mismas portadoras y filtros; espectros `|Z₁(F)|` y `|Z₂(F)|` en `F` y en Hz (§18, P6; ES-33).

### 11.9 Criterios de aceptación

1. El producto por `cos(2πf₀t)` desplaza y escala `1/2`; el visor coincide con la TF teórica de `MATH_LAB` con error `< 10⁻⁶`.
2. El comprobador de §11.6 detecta y localiza los solapes de ES-16 y ES-17 con los datos que declare el ejercicio y calcula `f_m` mínima.
3. La demodulación síncrona recupera la señal con error `< 10⁻³` (con paso bajo suficientemente largo) y el error de fase `cos φ` se observa.
4. Los espectros de FM tienen las líneas de Bessel `J_n(β)` (a 4 decimales) y Carson coincide con la medida del 98 % de la potencia.
5. Las modulaciones digitales usan `comms/` sin duplicarlo.

---

## 12. Filtros: plantilla, FIR, IIR y realización (SS-16, SS-17)

Los exámenes leídos piden diseño de filtros poco (≈ 3/29 FIR, ≈ 1/29 IIR) pero **la teoría y las prácticas P6, P9, P10 y P11 lo exigen** (`extra_senales.md` SS-16, SS-17). Las fórmulas cerradas de plantilla y el orden mínimo de Butterworth son de `MATH_LAB`; **el diseño numérico, la medida, la comparación y el filtrado son de aquí**.

### 12.1 Flujo de la pestaña Filtros

```
Plantilla (fp, fa, αp, αa, fm)  →  Familia  →  Diseño  →  Medida contra la plantilla  →  Realización  →  Filtrado de una señal
        ↑ calculadora de δp, δa           ↑ orden mínimo        ↑ ceros y polos         ↑ SOS, coste       ↑ audio, generador
```

### 12.2 Plantilla y tolerancias

| Dato | Definición | Observación |
|---|---|---|
| `f_m`, `f_p`, `f_a` | En Hz; `F_p = f_p/f_m`, `F_a = f_a/f_m`; **transición** `ΔF = F_a − F_p` | Valores de la P10: `f_m = 16 kHz`, `f_p = 3,6 kHz`, `f_a = 4 kHz` (`ΔF = 0,025`); de la P11: `f_p = 3,7 kHz`, `f_a = 4 kHz` (`ΔF = 0,01875`) |
| `α_p`, `α_a` | Atenuación máxima en paso y mínima en atenuada, en dB, **de amplitud** (declarado) | P10: 1 dB y 40 dB; P11: 1 dB y 60 dB |
| `δ_p`, `δ_a` | `δ_p = (10^{α_p/20} − 1)/(10^{α_p/20} + 1)`; `δ_a = (1 + δ_p)·10^{−α_a/20}` | `H_max = 1 + δ_p` y `α_p = 20 log₁₀((1+δ_p)/(1−δ_p))`, `α_a = 20 log₁₀((1+δ_p)/δ_a)` (apartado 4 de P10) |
| Valores P10 | `δ_p = 0,05750`, `δ_a = 0,010575` | `α_p = 1` dB, `α_a = 40` dB |
| Tipo | Paso bajo, alto, banda, rechazo de banda (los tres últimos como extensión, §12.10) | Las prácticas solo usan paso bajo |
| `H_ref` | Referencia de la ganancia (la guía multiplica `b` por `Href`) | Visible |

**Medida de cumplimiento (`check`)**: se evalúa `|H(F)|` en una malla densa (4 096 puntos como mínimo, y exacta con `dtft_at` en `F_p` y `F_a`), se busca el **error máximo en cada banda** (apartado 3a de P10) y se compara con `δ_p` y `δ_a`. El resultado es **«cumple»** con margen en dB, o **«no cumple»** con la violación localizada (frecuencia, valor, exceso); el gráfico superpone **líneas de tolerancia** horizontales en lineal y en dB (apartados 4b y 4c de P10).

### 12.3 FIR por ventanas (P6, P10, P9-32)

Respuesta ideal truncada: `h[n] = 2B sinc(2Bn)`, `n = −M..M`, `L = 2M+1` (`B = B_h/f_m`, `M = L₁ = L − 1` en la guía de P10). Causalizar con retardo `M` ⇒ fase lineal `φ(F) = −2πMF`. `H = H_d ⊛ W` (ancho de transición ≈ ancho del lóbulo de `W`).

| Concepto | Detalle |
|---|---|
| Fenómeno de Gibbs | Con ventana rectangular el pico del rizado (≈ 9 %, unos −21 dB en la atenuada pegada a la transición) **no baja al aumentar `L`**; solo se estrecha. Se muestra con una animación de `L` creciente |
| **Ejemplo de la P10 (L = 21, rectangular, `B = 0,25`)** | `H(0) = 1,0315`, `H(F_a) = 0,5` (−6,0 dB: la frecuencia de corte coincide con `f_a`); no cumple |
| **Datos medidos para la plantilla de P10** (corte en el centro de la transición, `F_c = 0,2375`; malla de 16 384 puntos; valores **de referencia**, se fijan al medir con el motor) | Rectangular: `L = 21` rizado en paso 3,44 dB / atenuada máx. −12,5 dB; `L = 41`: 1,18 / −20,9; `L = 101`: 0,99 / −24,5; `L = 201`: 0,50 / −29,6 (**nunca** cumple −40 dB). Hamming: `L = 121`: 0,10 / −40,3; `L = 131`: 0,04 / −49,7; `L = 141`: 0,03 / −55,0 (cumple a partir de ≈ 121). Kaiser `β = 3,34`: `L = 89`: 0,18 / −39,2; `L = 91`: 0,15 / −40,3 (cumple) |
| Estimadores de longitud | Kaiser (ventana): `L ≈ (A − 7,95)/(14,36·ΔF)` con `A = −20 log₁₀ δ_a`; para P10 `A ≈ 39,5 dB`, `L ≈ 88` (se mide 91). Fórmula de Kaiser/Herrmann para el equirrizado: `L ≈ (−20 log₁₀√(δ_pδ_a) − 13)/(14,6·ΔF)`; para P10 da **52,5** (ver §12.5) |
| `β` de Kaiser | `β = 0,5842(A−21)^{0,4} + 0,07886(A−21)` para `21 < A < 50`; `0,1102(A − 8,7)` para `A ≥ 50`; `0` si `A ≤ 21` (para P10: `β = 3,34`) |
| Elección de ventana | Asistente §9.5; la ventana fija la atenuación (Hamming ≈ −53 dB, Blackman ≈ −74 dB, rectangular ≈ −21 dB) y el **ancho de transición** fija `L` (`3,3/L` Hamming, `5,5/L` Blackman, `0,9/L` rectangular) |
| Fase lineal | Informe `dsp.linear_phase_report` (Tipo I a IV por simetría y paridad de `L`); retardo de grupo `M` constante (`dsp.fir_group_delay_at`) |
| Ceros | `roots(h)` (el apartado 2 de P10); **simetría cuadrantal** para fase lineal: dibujados sobre el plano z con el círculo unidad |

Se enseña **por qué** el diseño «`L = 21`» de la guía **no puede** cumplir la plantilla (la guía lo anuncia: «caldrà incrementar la longitud»): el asistente muestra la longitud mínima por ventana y por Parks-McClellan.

### 12.4 FIR por muestreo en frecuencia (P9, apartados 30 a 33)

Un FIR causal se obtiene muestreando la respuesta ideal con fase lineal y calculando la IDFT: `H[k] = e^{−jπk(N−1)/N}` para `0 ≤ k ≤ k_c`, cero en la banda de rechazo, y `H[N−k] = H*[k]` (hermítica para que `h[n]` sea real); `h[n] = IDFT_N{H[k]}`, `n = 0..N−1`. Con `N = 128` (apartado 30), `h[n]` y su respuesta con `N = 4 096` puntos (la guía escribe 4 098: posible errata; el laboratorio usa una potencia de 2 y lo indica) (apartado 31); comparación con el filtro por ventanas con `L = 126` (127 coeficientes, apartado 32), con 256 coeficientes (apartado 33) y con Parks-McClellan (apartado 34). **El visor muestra el rizado entre las muestras de frecuencia** (el filtro solo cumple la plantilla *en* los `N` puntos; entre ellos oscila), que es la lección del apartado 31 («¿te parece un buen filtro?»).

### 12.5 Parks-McClellan (equirrizado): **procede** (D5, decidido)

La petición del usuario decía «Parks-McClellan solo si procede»; la decisión D5 es que **procede** porque las prácticas lo exigen en cuatro apartados (P9-34, P10-5 y P10-6, P11-12: `hpm = firpm(Lh−1, 2·F0, M0, pond)` con `F0 = [0, fp, fa, fm/2]/fm`, `M0 = [1 1 0 0]`, `pond = [δ_a, δ_p]`) y es el único método que alcanza la plantilla con la longitud mínima. **Se implementa en una fase tardía** (SG-10) y **en dominio**, no se delega.

| Aspecto | Detalle |
|---|---|
| Algoritmo | Intercambio de Remez sobre una rejilla densa (16× el orden), interpolación baricéntrica de Lagrange, extremos alternos, convergencia por cambio relativo del error `< 10⁻⁶` o 40 iteraciones; casos de los cuatro tipos de fase lineal |
| Pesos | `W = [δ_a, δ_p]` (paso, atenuada) para que los rizados relativos sean `δ_p/δ_a` (convenio de `firpm`); se explica |
| Búsqueda de orden | Parte del estimador de Herrmann (`L ≈ 52,5`, es decir **53 o 54 coeficientes** en P10) y **aumenta el orden hasta cumplir** la plantilla (apartado 6 de P10: «¿qué longitud?»); valor de referencia pendiente de **medir** con el motor y de contrastar con `firpm` de MATLAB del usuario y con `scipy.signal.remez` si está instalado (§25) |
| Resultado | Rizado **uniforme** en cada banda (equirrizado), con una línea de tolerancia; comparación con ventana (misma longitud) |
| Límites | `L ≤ 1 024`, tiempo máximo con progreso y cancelación; fallo de convergencia se informa, nunca se oculta |

### 12.6 IIR: Butterworth, Chebyshev I y II, elíptico (P11, SS-17)

Pasos: prototipo analógico paso bajo normalizado → plantilla analógica por **bilineal con pre-distorsión** `Ω = tan(πF)` (con `fm` normalizada) → orden mínimo → polos y ceros → transformación bilineal `s = (1 − z⁻¹)/(1 + z⁻¹)` (`dsp.bilinear_design` con `prewarp`) → `H(z)`.

| Familia | Orden mínimo (fórmula) | Polos y ceros | Características |
|---|---|---|---|
| **Butterworth** | `N = ⌈ log[(10^{α_a/10} − 1)/(10^{α_p/10} − 1)] / (2 log(Ω_a/Ω_p)) ⌉` | Polos en el semicírculo izquierdo, equiespaciados; sin ceros finitos | Máximamente plano; el de mayor orden |
| **Chebyshev I** | `N = ⌈ arccosh(√((10^{α_a/10}−1)/(10^{α_p/10}−1))) / arccosh(Ω_a/Ω_p) ⌉` | Polos en una elipse | Rizado en la banda de paso, monótono en la atenuada |
| **Chebyshev II (inverso)** | Igual orden que I | Polos y **ceros** en el eje imaginario | Monótono en paso, rizado en la atenuada; se diseña a `f_a` |
| **Elíptico (Cauer)** | Ecuación del grado con integrales elípticas completas `K`: `N = ⌈ K(k)·K(√(1−k₁²)) / (K(√(1−k²))·K(k₁)) ⌉` con `k = Ω_p/Ω_a`, `k₁ = √((10^{α_p/10}−1)/(10^{α_a/10}−1))` | Polos y ceros con funciones elípticas de Jacobi | **Menor orden** para una plantilla dada |

**Resultados dorados para la plantilla de P11** (`f_m = 16 kHz`, `f_p = 3,7 kHz`, `f_a = 4 kHz`, `α_p = 1 dB`, `α_a = 60 dB`; `Ω_p = tan(π·0,23125) = 0,8886`, `Ω_a = 1`): **Butterworth `N = 65`** (64,22), **Chebyshev I y II `N = 17`** (16,70), **elíptico `N = 8`** (7,66). Se verifican con el motor y con `scipy.signal.buttord`/`cheb1ord`/`ellipord` si están. «Comproveu que el filtre de menor ordre és el darrer» (guía de P11): el visor lo muestra en una tabla.

**Estabilidad numérica (aviso de la propia guía de P11)**: con orden 65 y coeficientes `(b, a)` en doble precisión, la forma directa **puede dar polos fuera del círculo unidad por error de redondeo** («alguna de les aproximacions pot derivar en inestabilitat per problemes de precisió numèrica»). El laboratorio **lo demuestra** (polos calculados con `roots` desde `a`, módulo máximo, respuesta impulsional de 501 muestras que diverge) y propone **SOS** (`dsp.sos_decompose`: emparejamiento de polos conjugados con sus ceros más próximos; verificación `cascade_evaluate`) como solución, más el **asistente de relajación** (ampliar transición o reducir `α_a` y recalcular el orden) que menciona la guía (ES-30).

### 12.7 Comparación de familias y de FIR frente a IIR

Tabla autogenerada (con la misma plantilla): orden, número de multiplicaciones por muestra (modelo de coste determinista), polos/ceros, **retardo de grupo** (constante en FIR simétrico), duración de la respuesta impulsional (delta de 501 muestras, apartado 6 y 13), **tiempo de ejecución medido** (`tic`/`toc`: **no determinista**, se marca y no entra en el *digest*), fase lineal sí/no, estabilidad, rizado real en cada banda. Gráficas superpuestas de módulo, módulo en dB, fase, retardo de grupo y `h[n]`. Elección asistida: «para fase lineal, Parks-McClellan; para mínimo orden, elíptico; para respuesta plana, Butterworth».

### 12.8 Realización y cuantización

| Elemento | Detalle |
|---|---|
| Formas | Directa I y II, transpuesta, **cascada de SOS** (por defecto), paralelo; FIR simétrico (mitad de productos) |
| SOS | Emparejamiento y orden de secciones, ganancia por sección, **escalado** para evitar desbordamiento (norma L2), verificación frente a la forma directa |
| Coste | Productos y sumas por muestra; retardos de memoria |
| **Cuantización de coeficientes** (extra, D20) | `b` bits de coeficiente: ceros y polos se mueven; visor del error de respuesta y del movimiento de polos (los de orden alto se vuelven inestables antes) |
| Filtros propios de la práctica | `y = xx_filtreFIR(x, h)` (igual a `filter(h, 1, x)`) y `y = sv_iir_d2(x, b, a)` como **ejercicios de programación guiados**: el alumno escribe la ecuación en diferencias `y[n] = Σ b_i x[n−i] − Σ a_i y[n−i]` y el laboratorio compara con la implementación de referencia |

### 12.9 Filtrar señales (P10-8, P11-8 a 13)

Entrada: señal del generador (por ejemplo, `A₁ = 3` a 800 Hz y `A₂ = −5` a 4 200 Hz, `T = 10 s`) o archivo de audio. Procedimiento: igualar la `f_m` del diseño y la de la señal; salida con `conv`, con la función propia o con `filter`; se representan entrada y salida en **10 periodos de la componente de baja frecuencia**; el espectro muestra que la de 4 200 Hz queda atenuada ≥ `α_a`; se **escucha** el original y el filtrado (`sound([x, y], f_m)`: §27.3). La atenuación medida de cada tono se contrasta con `\|H(F)\|`.

### 12.10 Paso alto, paso banda y rechazo de banda (extensión)

FIR: inversión espectral (`δ[n−M] − h_LP[n]`) y diferencia de pasa-bajos; IIR: transformación de frecuencia analógica (LP→HP, LP→BP, LP→BS) antes de la bilineal. Mismas plantillas con dos bandas de paso o dos de atenuación. No se piden en los exámenes leídos: fase tardía.

### 12.11 Frontera con filtros analógicos y `CIRCUITS_LAB.md`

El laboratorio de circuitos electrónicos (`CIRCUITS_LAB.md`, §10.11 «Filtros activos», catálogo `BL-AN-13` y solver `CI-AN-FILT`) **realiza** filtros analógicos y calcula su Bode con `ac/`; este documento diseña el **prototipo** (por D8 es un único objeto y una única función de orden mínimo y polos, la defina quien se construya primero):

| Responsabilidad | Aquí | `CIRCUITS_LAB.md` |
|---|---|---|
| Plantilla en Hz y orden mínimo (Butterworth, Chebyshev I y II, elíptico) | Sí, función única (D8) | Consume; es el paso 1 de `CI-AN-FILT`. **Bessel** (retardo de grupo plano, solo analógico) lo define allí |
| **Prototipo** `H(s)` (polos, ceros, ganancia, `ω₀`, `Q` por sección) | Sí: objeto `AnalogFilterPrototype` (contrato en §23.4) | Consume |
| **Realización con componentes** (Sallen-Key, realimentación múltiple, LC) y valores `R`, `C` | No | Sí |
| **Bode de un circuito** y comparación con el prototipo | Visor de módulo y fase compartido (§19.6) | Sí (`ac/bode.py`, §8.9.1; BL-AC-7, CI-AC-36/37) |
| Filtro digital equivalente del analógico (bilineal) | Sí | Referencia cruzada |
| Calculadora de dB (`CI-RF-01`, §14.2) | Reutiliza | Origen |

### 12.12 Criterios de aceptación

1. Para la plantilla de P10, el laboratorio calcula `δ_p = 0,05750` y `δ_a = 0,010575`, **rechaza** la rectangular de `L = 21` con la violación localizada, y encuentra la longitud mínima por ventana (Hamming ≈ 121 a 131; Kaiser ≈ 91) y por Parks-McClellan (≈ 53 a 54, a medir).
2. Para la plantilla de P11, los órdenes salen `65`, `17`, `17`, `8` y los cuatro filtros **cumplen** la plantilla en SOS; la forma `(b, a)` de Butterworth de orden 65 produce el aviso de inestabilidad numérica.
3. Los polos de todos los IIR diseñados tienen `|p| < 1` en SOS y se dibujan con el círculo unidad.
4. El FIR de fase lineal tiene retardo de grupo constante igual a `M`.
5. Cada diseño se contrasta con SciPy (`firwin`, `remez`, `butter`, `cheby1`, `cheby2`, `ellip`) si está instalado, con discrepancia máxima en `|H|` menor que `10⁻⁹` (IIR en SOS) o `10⁻⁶` (Remez), y se marca «no contrastado» si no.
6. Un diseño que no alcanza la plantilla no se muestra como válido.

---

## 13. Filtro adaptado, correlador y decisión (SS-7 visual y SS-8, ≈ 5/29 y 12/29)

La matemática (`r_xy`, `S_xy`, `y(t) = s * p(−t) = r_sp(t)`) es de `MATH_LAB`; aquí, el **visor** y la simulación.

### 13.1 Filtro adaptado

| Elemento | Detalle |
|---|---|
| Esquema | Dos pulsos (**ortogonales** o no) `s₀(t)`, `s₁(t)`; filtro `h(t) = p(T − t)` (causal) o `p(−t)`; salida en `t₀`; **umbral** `A` y `−A` para decidir |
| Visor | Entrada con ruido sembrado, salida del filtro (con el **máximo en `t = 0` o `T`**: la energía si `s = p`, 0 si `s` es ortogonal), instante de muestreo marcado y umbral dibujado |
| Versión digital con DFT | `H[k]`, `N ≥ L_s + L_h − 1`, `y[0] = (1/N) Σ Y[k]` (ES-34) |
| **Cauchy-Schwarz** | Comparación con filtros alternativos aleatorios sembrados: el adaptado da la mayor `y(t₀)/σ` (relación señal a ruido de salida); SNR teórica `2E/N₀` |
| **Simulación** | Monte Carlo corto sembrado: tasa de acierto con ruido; compara con la teórica `Q(√(2E/N₀))`-tipo (de `MATH_LAB` y `comms/metrics.py`) |
| Reutilización | `comms.detection.matched_filter`, `correlator_decide`, `ml_decide` (existen) y `comms.pulse` |

### 13.2 Correlación visualizada y retardo de canal (final 2022, ej. 1.7; SS-7)

`r_x(t) = x(t) * x*(−t)` y `r_xy` por FFT con relleno (`N ≥ L₁ + L₂ − 1`). Propiedades mostradas: `r_x` par si `x` real, `r_x(0) = E` (o `P`), `|r_x(τ)| ≤ r_x(0)` (Schwarz), ortogonalidad si `r_xy(0) = 0`; para exponenciales complejas `A e^{j2πft}`, `B e^{j2πf't}`: `r_xy = A B* e^{j2πfτ}` si `f = f'`, 0 si no (nota del examen). **Estimación de retardo y atenuación de un canal por el pico de `r_yx`** (ES-36): el pico en `τ̂` y su altura dan el retardo y la ganancia (`r_yx = a·r_x(τ − T₀)`); se calcula con la resolución de muestreo y se refina por interpolación parabólica del pico, con el error declarado. **Errata de examen (ES-35):** `R_p1p2 = ±Λ(t−2) + Λ(t+2)`: el visor calcula la correlación numérica de los pulsos del enunciado y decide el signo correcto.

### 13.3 Criterios de aceptación

1. En ES-34, `y[0]` por DFT coincide con `Σ x[n]p[n]` y con la salida temporal en `t = 0` con error `< 10⁻⁹`.
2. El filtro adaptado supera al 100 % de 1 000 filtros aleatorios sembrados en SNR de salida.
3. La estimación de retardo de ES-36 devuelve el retardo con error menor que `T_s/2` y la ganancia con error menor que 1 %.
4. `r_x` cumple paridad, `r_x(0) = E` y Schwarz en las señales de la biblioteca.

---

## 14. Análisis espectral, STFT y espectrogramas

Guía de SST: «Análisis espectral y correlación». Guía de TRS: densidad espectral de potencia (T1). Esta pantalla es el **visor** de `X[k]` a lo largo del tiempo y de la PSD estimada.

### 14.1 Herramientas

| Herramienta | Definición | Parámetros |
|---|---|---|
| **Periodograma** | `\|X[k]\|²/(L f_m)` (o `/(L Σw²)` con ventana) | ventana, `N` |
| **Welch** | Promedio de periodogramas de segmentos solapados | longitud de segmento, solape (50 % por defecto), ventana |
| **STFT** | `X(m, k) = Σₙ x[n] w[n − mR] e^{−j2πkn/N}` | longitud `L`, salto `R` (`hop`), `N`, ventana |
| **Espectrograma** | `\|X(m, k)\|²` en dB re un máximo, con rango dinámico elegible | `L`, `R`, `N`, ventana, rango (60 dB por defecto) |
| Estimación paramétrica (extra, D21) | AR(`p`) por Yule-Walker y su PSD `σ²/\|A(F)\|²` | `p` |

**Compromiso tiempo-frecuencia:** `Δt ≈ L/f_m`, `Δf ≈ f_m/L` (resolución de la ventana usada, §9): **no se mejoran a la vez**; relleno de ceros solo interpola. Control «¿qué se ve?» con anchos de banda y duración.

### 14.2 Vista del espectrograma

| Elemento | Detalle |
|---|---|
| Imagen | Mapa de calor con **escala de color perceptual** y alternativa de **escala de grises** y de **alto contraste**; la leyenda rotulada en dB; no se depende solo del color |
| Ejes | `t (s)` y `f (Hz)` (o `F`), con zoom y desplazamiento |
| Cursor | Valor en dB, `t`, `f`; rebanada espectral en el instante del cursor (`\|X(m, ·)\|`) y rebanada temporal a la frecuencia del cursor |
| Anotaciones | Picos detectados con ruta (pista de frecuencia); marcas de teclas DTMF o notas |
| Enlazado | Con la forma de onda, el espectro de un instante y la ventana usada |

### 14.3 Casos de uso

| Señal | Qué enseña |
|---|---|
| **Chirp** lineal | Línea recta en el espectrograma; efecto de `L` en el grosor |
| **Secuencia DTMF** (`tecla.wav` de la P5, varias teclas) | Dos líneas por tecla; identificar la tecla con tabla (§8.6) |
| **Escala de notas** | Escalones de frecuencia; aliasing si `f_m` baja |
| **Audio `dm_serie`** (P1; `f_m = 44 100 Hz`, 1 736 688 muestras, 39,38 s) | Visor de gran tamaño (inviable en la vía exacta) |
| **Eco y reverberación** | Rastro repetido; `L` del eco |
| **FM** | Línea sinusoidal; ancho de Carson |
| **Mezcla P6** | Dos bandas en `F` (modulada y base) |

### 14.4 PSD estimada de procesos aleatorios (TRS-2, visor)

Realizaciones sembradas de un proceso (ruido blanco, AR(1), MA(q), sinusoide en ruido): periodograma de una realización (**no consistente**: la varianza no baja con `N`), **Welch** (varianza baja `∝ 1/K`), y la **PSD teórica** de `MATH_LAB` superpuesta, para ver el sesgo y la varianza. Potencia por tiempo `r[0]` y por frecuencia `∫₀¹ S dF` (Wiener-Khinchin discreto, dos caminos).

### 14.5 Rendimiento y límites

| Caso | Objetivo (con NumPy) | Sin NumPy |
|---|---|---|
| FFT de `2²⁰` puntos | < 0,5 s | **No** disponible (se limita a `2¹⁶` y se avisa) |
| STFT de 40 s a 44,1 kHz, `L = 1 024`, `R = 256` (≈ 6 800 tramas) | < 2 s | Se **reduce** (diezmado a 8 kHz, tope de tramas) con aviso y progreso, hilo aparte y cancelación |
| Dibujo del espectrograma (imagen `QImage` precalculada) | ≥ 30 fps al desplazar | Ídem |

La vía exacta (`dsp/`, `MAX_FFT_N = 4 096`) **no** se usa para el espectrograma (§24).

### 14.6 Criterios de aceptación

1. Un tono puro de amplitud `A` con ventana Hann muestra `A` tras la normalización de ganancia coherente (con el escalonamiento declarado).
2. El chirp lineal produce una línea recta de pendiente `(f₁ − f₀)/T` con error `< 1 bin`.
3. El periodograma de ruido blanco no baja de varianza con `N`; Welch con `K` segmentos sí (`∝ 1/K` con tolerancia del 20 %).
4. Los cuatro controles de color (perceptual, grises, alto contraste, rango) cambian la vista sin cambiar los datos.

---

## 15. Multirate: diezmado, interpolación y remuestreo

No aparece en los exámenes de SST leídos; sí en la práctica del procesado de audio (cambio de `f_m`) y en el uso real (44,1 kHz a 8 o 16 kHz). Se incluye como **bloque propio** con prioridad media.

### 15.1 Operaciones

| Operación | Definición | Espectro | Filtro necesario |
|---|---|---|---|
| **Diezmado por `M`** | `y[n] = x[Mn]` | `Y(F) = (1/M) Σ_{k=0}^{M−1} X((F − k)/M)`: réplicas que **se pliegan** | Paso bajo **antes**, corte `F_c = 1/(2M)` |
| **Expansión por `L`** | `y[n] = x[n/L]` si `L \| n`, 0 si no | `Y(F) = X(LF)`: `L − 1` **imágenes** en `[0, 1)` | Paso bajo **después**, corte `1/(2L)` y ganancia `L` |
| **Remuestreo racional `L/M`** | Expandir por `L`, filtrar, diezmar por `M` | Un solo filtro de corte `min(1/(2L), 1/(2M))` y ganancia `L` | Polifásico |
| `x[2n]`, `x[n/2]` del curso | Casos `M = 2` y `L = 2` de SS-0 | Ejemplos de examen | — |
| `x[n](−1)ⁿ` | Traslación a `F = 1/2` | Ya en §8.7 y §11 | — |

### 15.2 Visor

Espectro de entrada con réplicas, **espectro tras diezmar sin filtro** (con el solape coloreado y la frecuencia aparente) y **tras filtrar y diezmar**; análogo para la expansión (imágenes) y la interpolación. La pantalla enseña el **orden** correcto (filtro antes de diezmar, después de expandir). Se **escucha** (§27.3) el efecto del aliasing al diezmar sin filtrar.

### 15.3 Polifásico y coste

Descomposición polifásica del filtro (`L` o `M` ramas), con el **modelo de coste determinista** (productos por muestra de salida) frente a la forma directa; ejemplos de conversión: 44 100 → 48 000 Hz (`L/M = 160/147`), 44 100 → 16 000 Hz (`160/441`), 16 000 → 8 000 Hz (`1/2`). El filtro se diseña con la **plantilla** de §12 (Kaiser o Parks-McClellan) y se mide su cumplimiento.

### 15.4 Criterios de aceptación

1. Diezmar por 2 un tono de `0,3 F` produce `0,6 → 0,4` (aliasing) sin filtro y desaparece con el filtro previo.
2. El remuestreo `160/147` conserva la frecuencia de un tono con error `< 10⁻³` relativo y mantiene la ganancia.
3. La forma polifásica da la misma salida que la directa con diferencia máxima `< 10⁻¹²` (vía rápida) y menos productos.

---

## 16. Cuantización y conversión A/D, D/A (SS-18, parte pequeña)

La guía lo lista («Conversores AD i DA»), **no aparece en ningún examen ni práctica** (0/29) y `extra_senales.md` lo deja «fuera de alcance por ahora» salvo `SQNR ≈ 6,02 b + 1,76 dB`. Aquí entra **solo la parte visual y pequeña** (fase tardía SG-15, decisión D18).

| Elemento | Detalle |
|---|---|
| Cuantizador uniforme | `b` bits, rango `±V`, `Δ = 2V/2^b`, error de redondeo en `[−Δ/2, Δ/2]`, potencia `Δ²/12` |
| SQNR | `SQNR ≈ 6,02 b + 1,76 dB` para una sinusoide a plena escala; con amplitud menor, `−20 log₁₀(V/A)`; **medida** frente a la fórmula |
| Visor | Señal original, cuantizada, **error** y su histograma (uniforme), espectro del error (blanco o con armónicos si la señal es de baja amplitud) |
| Cadena A/D y D/A | Antialiasing → muestreo y retención → cuantización → codificación; D/A con retenedor y reconstrucción (§10.5) |
| Extras (D18) | *Dither*; ENOB; cuantización no uniforme (ley µ/A) solo como curva |

Criterio: el SQNR medido de una sinusoide a plena escala con `N ≥ 2¹⁶` muestras coincide con `6,02 b + 1,76` dentro de 0,3 dB para `b = 4..16`.

---

## 17. Tratamiento de la Señal: visores y simulaciones sembradas (TRS-1 a TRS-8)

### 17.1 Alcance y dependencias

- La **matemática** de TRS-1 a TRS-8 (autocorrelación, matriz de correlación, PSD, MAP y Neyman-Pearson, Cramér-Rao y MVUE, ML y MMSE, Wiener-Hopf, gradiente, LMS y NLMS) vive en `MATH_LAB.md` (decisión del usuario; bloque 16, §4.16, y calculadoras §8.2-R). **Este laboratorio aporta las escenas visuales y la simulación sembrada** y se alimenta de aquel: las curvas teóricas (ROC, cota, `J_min`, PSD) las calcula `MATH_LAB`; este laboratorio las dibuja y las contrasta con Monte Carlo (§23.1).
- **No hay material de TRS** en la carpeta de OneDrive (las carpetas de 3.º y 4.º están vacías): solo la guía (`230918`: T1 10 h, T2 12 h, T3 15 h, T4 11 h, T5 12 h; control 20 %, seguimiento del laboratorio 25 %, final 55 %; prácticas obligatorias y no reevaluables; 13 h de grupo pequeño). **No hay frecuencia de examen medida**: las prioridades son por horas. Si el usuario aporta exámenes de TRS, se revisan (riesgo 4 de `extra_senales.md` §6).
- Dependencia de fases: SG-14 depende de que `MATH_LAB` entregue los bloques TRS (§30).

### 17.2 Escenas

| Escena (TRS) | Qué se ve | Parámetros sembrados | Contraste con la teoría |
|---|---|---|---|
| **Procesos discretos** (TRS-1) | Realizaciones superpuestas, media de conjunto y temporal (**ergodicidad**), `r̂[k]` sesgada y no sesgada, **matriz de correlación** Toeplitz como mapa de calor y sus **autovalores** (todos `≥ 0`) | AR(1) `a`, MA(`q`), sinusoide en ruido blanco, semilla, nº de realizaciones | `r[k]` teórica, `r[−k] = r*[k]`, `r[0] ≥ \|r[k]\|` |
| **PSD y procesos filtrados** (TRS-2) | Periodograma, Welch, PSD teórica `σ²/\|1 − a e^{−j2πF}\|²`; `S_y = \|H\|² S_x` visual: ruido blanco → filtro → PSD (§14.4) | `a`, `σ²`, filtro, `K` | Potencia por tiempo y por frecuencia |
| **Detección** (TRS-3) | Dos densidades gaussianas (`H₀`, `H₁`), **umbral** móvil, áreas `P_FA` y `P_D` sombreadas, **ROC** con el punto de operación, **MAP** (a priori deslizante) frente a **Neyman-Pearson** (`P_FA` fijada), detección de señal conocida `T = sᵀx`, `d² = sᵀs/σ²`, ruido coloreado y **blanqueado**, **filtro adaptado** como caso particular (§13) | `σ`, `μ`, `P(H₀)`, `P_FA`, `L` muestras, semilla | `P_D = Q(Q⁻¹(P_FA) − d)`; tasas empíricas por Monte Carlo |
| **Estimación** (TRS-4, TRS-5) | Histograma del estimador sobre muchas simulaciones, sesgo, varianza, línea de la **cota de Cramér-Rao**, eficiencia; log-verosimilitud dibujada y su máximo (**ML**); **posterior** con a priori (**MAP**, **MMSE**); caso gaussiano conjunto con la recta de regresión | media de gaussiana, DC en ruido, amplitud de sinusoide, nº de datos | `Var ≥ 1/I(θ)` siempre; ortogonalidad `E[(θ − θ̂)x] = 0` |
| **Wiener** (TRS-6) | **Identificación** de sistema, **ecualización** de canal, **cancelación** de ruido, **predicción**, **interpolación**; **superficie de error** `J(w)` con dos coeficientes (curvas de nivel), `w₀`, `J_min`, ecuaciones `R w = p` con `R` y `p` mostradas | canal, SNR, orden | `J(w) ≥ J_min` para `w` perturbado; mínimos cuadrados con muchos datos converge a Wiener |
| **Gradiente** (TRS-7) | Trayectorias `w(k+1) = w(k) + μ(p − R w(k))` sobre las curvas de nivel; **modos** `v_i(k) = (1 − μλ_i)^k v_i(0)`, constantes de tiempo `τ_i`, **dispersión de autovalores** y velocidad | `μ`, `R` | `0 < μ < 2/λ_max`; divergencia observable fuera |
| **LMS y NLMS** (TRS-8) | **Curva de aprendizaje** `J(n)` promedio de 100 a 1 000 realizaciones, evolución de `E[w(n)]`, **desajuste** `M ≈ μ tr(R)/2`, comparación LMS frente a NLMS (`0 < μ̃ < 2`), compromiso rapidez/desajuste | `μ`, `R`, nº de realizaciones, semilla | `μ > 2/tr(R)`: divergencia; ecualización adaptativa de un canal con interferencia entre símbolos y cancelación de ruido en audio |

### 17.3 Reglas comunes

1. Toda escena **declara semilla, número de realizaciones y tiempo**; sin semilla no hay simulación.
2. **La teoría se muestra al lado** con su valor exacto (de `MATH_LAB`) y la discrepancia relativa; si la simulación se desvía más de lo esperable por el tamaño de muestra, se avisa («el intervalo de confianza del Monte Carlo no incluye la teoría»).
3. La simulación **nunca sustituye** a la solución con pasos; es el contraste del §5.3 de `MATH_LAB` («simulación sembrada como contraste»).
4. Cada escena tiene su **versión de ejercicio** (calcular `P_D`, `μ_max`, `J_min`…) con corrección por equivalencia en `MATH_LAB`.
5. El tiempo de cálculo de las escenas pesadas (1 000 realizaciones de LMS de 10 000 muestras) usa la vía rápida, hilo aparte y cancelación.

### 17.4 Criterios de aceptación

1. En la escena de detección, la ROC teórica y la empírica (10⁴ muestras) coinciden dentro del intervalo de confianza al 99 % en 20 puntos.
2. En estimación, ninguna simulación produce `Var < 1/I(θ)` por encima del intervalo estadístico para estimadores insesgados.
3. LMS: con `μ` dentro de la cota, `E[w(n)] → w₀`; fuera de la cota, la divergencia se observa en la curva.
4. La superficie de error con dos coeficientes tiene el mínimo en `w₀` con `J_min` igual al de `MATH_LAB`.

---

## 18. Prácticas P0 a P11 de Señales y Sistemas

Fuente: enunciados de la carpeta `Laboratorio/` del usuario (tardor 2025; en catalán), informes propios (P1, P4 a P7, P9 a P11) y la `Guía d'entrega de material`. La guía de la asignatura asigna 6 h de laboratorio por bloque (4 bloques) y el 10 % de la nota; las de TRS pesan el 25 %. Las prácticas se hacen en MATLAB (también se admite Python según la guía docente). **El laboratorio no ejecuta código del alumno** (D9): ofrece el mismo **flujo de trabajo** (estudio previo, experimentación, comprobación, informe) con bloques y calculadoras propios, y **genera el código equivalente en MATLAB y en Python** para que el alumno lo corra en su entorno (§Anexo F). No se copian los PDF al repositorio (regla D5 de `MATH_LAB.md`).

### 18.1 Modelo de práctica

| Campo | Contenido |
|---|---|
| Id y título | `P4`, «Transformada de Fourier para señales digitales» |
| Fuente | Enunciado local (ruta configurable) y su versión; **parafraseado** en el repositorio |
| Estudio previo | Preguntas teóricas con campos de respuesta (fórmulas, valores, dibujos cualitativos) corregidas por equivalencia (`MATH_LAB`) o por propiedad |
| Pasos de experimentación | Lista numerada **igual que la guía** (P9: 34 apartados) con: parámetros, bloques del laboratorio, valor esperado, gráfica y comentario guiado |
| Funciones propias | Las que pide la guía (`nc_conv`, `la_dm_DTFT`/`xx_trf`, `xx_filtreFIR`, `sv_iir_d2`…) como **ejercicio de programación guiado**: se explica la especificación y se compara con la implementación de referencia (sin ejecutar código del alumno) |
| Comprobación | Valores teóricos y medidos, errores mostrados en tabla |
| Informe | Plantilla de la guía: **título, autores, grupo, fecha, subtítulo por apartado, resultados con gráficos y breve comentario con los parámetros usados, conclusiones**; salida en PDF o Markdown (el alumno entrega PDF en Atenea) (§27.5) |
| Nomenclatura | Los nombres del código generado siguen `nc_fitxer.m` (inicial de nombre y apellido), con cabecera «qué hace, autor, fecha»; sin acentos ni diéresis (regla de la guía) |

### 18.2 Mapa de prácticas

| Práctica | Tema | Material disponible | Bloques de este laboratorio | Fase |
|---|---|---|---|---|
| **P0** | Introducción a MATLAB (instalación, `Command window`, scripts, funciones, matrices y operaciones) | `P0_IntroduccioMatlabT25.pdf` | Ejercicios de matrices con **verificador de dimensiones** (§18.3); tabla de equivalencias (Anexo F) | SG-1 |
| **P1** | Señal de audio: muestras, `f_m`, máximo, mínimo, media, energía, duración, gráficas | `P1_DM.pdf` (informe), `dm_serie.mp3` | §6 (archivo), §14 | SG-1 |
| **P2** | Generación de señales digitales y convolución | `P2_SenyalsDigitals_Convolucio.pdf`; funciones propias del alumno | §6, §7.4 | SG-3 |
| **P3** | *Sin material en la carpeta* (hueco de numeración) | — | Reservada; el contenido se fijará con el material (D22) | — |
| **P4** | Transformada de Fourier de señales digitales (función propia `xx_trf`) | `P4_Transformada…pdf`, `la_dm_DTFT.m` | §8, visor de DTFT; `MATH_LAB` (teórica) | SG-3 |
| **P5** | Propiedades de la TF: **enventanado**; detección de sinusoides; **teclado telefónico** | informe P5, `tecla.wav` | §9, §8.6 | SG-3 |
| **P6** | **Modulación, multiplexación y filtrado** (dos audios, `f_m = 16 kHz`) | informe P6, `audio_pr6_1.wav`, `la_dm_DTFT.m` | §11, §12.3 | SG-7 |
| **P7** | **Señales periódicas** (enunciado en imagen, ilegible por texto) y **simulacro de parcial** (eco; periódica con filtro de un armónico) | `P7_SenyalsPeriodics.pdf` (solo imagen), informe «Examen Parcial» | §7.7, `MATH_LAB` (series) | SG-5 |
| **P8** | *Sin material en la carpeta* (probable muestreo y periódicas; por confirmar) | — | Reservada; propuesta: §10 (D22) | — |
| **P9** | **DFT**: sinusoides, enventanado, propiedades y filtros (34 apartados) | `P9_DFT.pdf`, informe P9 | §8, §9, §12.4 | SG-3 (1 a 29), SG-8 (30 a 33), SG-10 (34) |
| **P10** | **Filtros FIR** | `P10_FiltresFIR.pdf`, informe, `sv_plantillaG.m`, `sv_plantillaH.m`, `P10.mlx` | §12.2 a §12.5 | SG-8 (apartados 5 y 6 en SG-10) |
| **P11** | **Filtros IIR** y filtrado del audio de inicio de curso | `P11_FiltresIIR.pdf`, informe | §12.6 a §12.9 | SG-9 (apartado 12 en SG-10) |

La carpeta incluye además `Guía.pdf` (entrega), `SST_ManualMATLAB.pdf` y `Taula funcions Matlab.pdf` (lista de funciones del curso; base del Anexo F).

### 18.3 P0 — Introducción a MATLAB

| Apartado (paráfrasis) | En el laboratorio |
|---|---|
| Instalación y entorno | Texto de ayuda y enlace; no se instala nada |
| `log10(((5·4+80)³))/3 = 2`; `ans`; `v2 = v1·π` | Calculadora científica con historial (`MATH_LAB` §8.2-I) |
| Scripts, secciones `%%`, cabecera, funciones | Plantilla de cabecera y estructura sugerida (cabecera, inicialización, procesamiento, representación) |
| Función `nc_quadratic_formula(a, b, c)` | Calculadora de ecuación de 2.º grado con pasos y comprobación `{3,6,6}` y `{1,5,4}` (`MATH_LAB`) |
| Vectores fila/columna, matrices, `A(n,m)` | Visor de matrices |
| Operaciones `+ − * / \ .* ./ .^ ^ ' .' conj` y lógicas | **Verificador de dimensiones**: dada una lista de expresiones (`r = a(1)/b(3)`, `r2 = a*b`, `r3 = a'.*b`, `r4 = a*a`, `r9 = C/a`…) y tamaños, dice si **se puede o no y por qué** (compatibilidad de dimensiones), que es lo que pide el ejercicio («Has pogut realitzar totes les operacions?») |

### 18.4 P1 — Señal de audio

Carga de un WAV (`audioread`): **número de muestras y `f_m`** (`length`, `size`), **máximo, mínimo, media**, **energía** `Σx²`, **duración** `L/f_m`, gráficas frente a la muestra y al tiempo, segmento de 4 s. Valores del informe del usuario (para el caso de prueba **privado y opcional** con ruta local, §22.2): `f_m = 44 100 Hz`, 1 736 688 muestras, máx. 0,94201, mín. −0,95193, media `−2,2445·10⁻⁵`, energía 30 447,1061, duración 39,3807 s. No se incluye el audio en el repositorio.

### 18.5 P2 — Generación de señales digitales y convolución

Seis funciones: `delta`, `escalón`, `pulso rectangular p_L`, `exponencial causal aⁿu[n]`, `exponencial simétrica a^{|n|}`, `dentL (1 − n/L)p_L[n]`; prueba con `n = −10:20`, `stem(n, sv_dent(n, 6))`, retardada 5 y adelantada 5. **Convolución propia** `[z, n] = nc_conv(x, nxi, y, nyi)` con el eje correcto, y cinco casos (delta retardada, pulsos, `p_50 * 2·0,9ⁿu[n]`, `p_50 * 2cos(2π·0,125n)`) representando `x`, `y` y `z`. El laboratorio ofrece los casos, la **verificación** `Σz = Σx·Σy`, la longitud y el eje, y los regímenes (§7.4). (El texto del enunciado extraído tiene los números parcialmente ilegibles; los parámetros exactos se confirman con el PDF.)

### 18.6 P4 — Transformada de Fourier de señales digitales

Función `X = xx_trf(x, n, F)` con `X(F) = Σ x[n] e^{−j2πFn}`: versión de una frecuencia, de un vector `F`, y con **parámetros por defecto** (`n = 0:L_x−1`, `F = −0,5:0,001:0,5`). Ejercicios:

| Ejercicio | Entrada | Lo que se verifica |
|---|---|---|
| 1 | `x[n] = p₁₁[n+5]` | `X(F) = sin(11πF)/sin(πF)` real (fase cero, señal centrada); periodo 1; máximo 11 en `F = 0`; ceros en `k/11` (ES-24) |
| 2 | `x[n] = aⁿu[n]`, `a = 0,8` y `a = −0,8` | `\|X(F)\|² = 1/(1 + a² − 2a cos 2πF)`; `a = 0,8`: máximo 5 en `F = 0`, mínimo 0,5556 en `F = 0,5`; `a = −0,8`: al revés (ES-25) |
| 3 | TF de las señales digitales básicas de las tablas | Visor con parámetros adecuados |

### 18.7 P5 — Enventanado y teclado telefónico

Teclado: `x_i(t) = x(t)w(t)` con `x(t) = ½cos(2πf_{f_i}t) + ½cos(2πf_{c_i}t)` y ventana de `T`; análisis de las ventanas `w₁ = Π(t/T)` y `w₂ = Λ(2t/T)` (`T = 15 ms`): ventana, `W(f)`, módulo en dB; identificación del dígito con `tecla.wav` (§8.6; ES-31, ES-32).

### 18.8 P6 — Modulación, multiplexación y filtrado

Sistema multiplexor: dos audios de 10 a 15 s, `f_m = 16 kHz`, una señal modulada con `F₁ = f₁/f_m`, ambas **limitadas** con `h_M[n] = 2B sinc(2Bn)`, `n = −M..M`, `L_h = 2M+1`, `B = B_Hz/f_m`, `B_Hz ≥ 4 kHz`; `Y(F)` en `F` y en Hz. Demultiplexor con el mismo esquema y espectros `|Z₁|`, `|Z₂|` (§11.8; ES-33).

### 18.9 P7 — Periódicas y simulacro de parcial

Ejercicio 1 (eco): relación entrada-salida, linealidad e invariancia; `h(t) = δ(t) + aδ(t−T₀)`, causalidad y estabilidad; salida a `x(t) = 2Π(t/T)` con `a = ½`; energía y potencia; `H(f)` con `T = 1 ms`; segundo sistema (realimentación), `b` y `T` del **inverso**; caso `a = −2`; versión digital con `n` y `b` (`h_d[n]` con deltas alternadas cada 100 muestras, `b = −a`, `n = 100`). Ejercicio 2 (periódica con `T = 5 ms`, `A = 2`): periodo y frecuencia fundamental, señal base y su energía, TF de la base, coeficientes de la serie, `X(f)` de la periódica (deltas), **armónicos nulos**, ancho de banda del filtro para dejar solo el fundamental, `h(t)`, salida y su potencia. Valor de referencia para una **onda cuadrada ±A con A = 2**: amplitud del fundamental `4A/π = 2,546` (coincide con el «≈ 2,55» del informe), armónicos pares nulos (ES-23). **Los errores que el alumno anota en sus comentarios** (olvidar `n₁` del inverso, mal desarrollo de `h(t)`, mala elección de la señal base) son **casos de «error común»** del ejercicio (§21.5).

### 18.10 P9 — DFT (34 apartados) y su reflejo en el laboratorio

| Apartados | Contenido | Dónde |
|---|---|---|
| Teoría | TF de una sinusoide analógica y digital; relación `F_x = f_x/f_m` | §4, §8 |
| 1 a 6 | `A = 4`, `f_x = 2 kHz`, `f_m = 8 kHz`, `L = 30`; DFT de 30 puntos con la función propia y con `fft`; `stem(k, abs(X))`; posición y valor del máximo; error de frecuencia y de amplitud; repetir con `N = 4 096`; `f_x = 2 147 Hz`; **tabla de comparación** | §8.3 (ES-06 a ES-08) |
| Enventanado rectangular y relleno de ceros (7 a 10) | `f_x = 2 400 Hz` (un bin: ES-09); `N = 1 024`; `N = 512` y la IDFT con ceros | §8.3, §8.7 |
| Enventanado triangular (11 a 18) | `x[n] = 4cos(2π·0,25 n)`, `n = −9..9`, `w = [1:10, 9:−1:1]/10`, `y₁[n] = y[n−9]`; DFT de 19 y de 512 puntos; **pico 20 en `k = 128` y `k = 384`** (ES-10); comparación con la rectangular: **anchura del lóbulo** y **relación principal/secundario en dB** | §9 |
| Retardo y modulación (19 a 21) | `z_n = IDFT{Y_dft·e^{−j2πkn₀/N}}`, `n₀ = 10` y `n₀ = 500` (envolvente circular); `Y_dft` por `e^{j2πk₀n/N}` | §8.7 |
| Convolución (22 a 24) | `p₆ * p₆`, `N = 16, 15, 9`; mínimo `N = 11` | §8.7 (ES-11) |
| Filtrado con DFT (25 a 29) | `h(t) = e^{−t/10}u(t)`, pulso de 10 s; `f_m`, `L_x`, `L_h`, `N`; `y_c = conv` frente a `y(nT)` frente a DFT; escalas | §8.7 |
| Diseño por muestreo en frecuencia (30 a 34) | `N = 128`, `h[n]` y su respuesta con `N = 4 096`, comparación con ventana `L = 126` y `L = 256`, y con Parks-McClellan | §12.4 y §12.5 |
| Origen | Ejercicio 2 del final de 10-1-2014 (QT), con cuatro apartados teóricos «para resolver tras la práctica» | Se añade como ejercicio (parafraseado) |

### 18.11 P10 y P11 — Filtros FIR e IIR

Mapeo de apartados de P10 y P11 en §12.3 a §12.9 con los datos de §12.2; las plantillas `sv_plantillaG.m` y `sv_plantillaH.m` del usuario sirven de **referencia de salida** (qué debe dibujarse), sin copiarse.

### 18.12 Ejecución de una práctica en la interfaz

La pestaña **Prácticas** muestra la lista, el avance por apartado (casillas), el **modo** `Estudio previo` (preguntas teóricas) y `Experimentación` (pasos con bloques), el **modo guiado** (da pistas) y el **modo examen** (sin ayudas), y el botón «Generar informe» (§27.5). Los datos son sembrados cuando no son del enunciado (cada alumno obtiene los suyos); las prácticas de pareja (`nc1_nc2_fitxer.m`) se admiten con dos autores.

### 18.13 Criterios de aceptación

1. P2, P4, P5, P9, P10 y P11 se pueden completar íntegramente con el laboratorio sin MATLAB, y el informe generado tiene el formato de la guía.
2. El código MATLAB y Python generado para cada paso reproduce el resultado del laboratorio (contrastado con NumPy y, cuando es posible, con una ejecución MATLAB aportada por el usuario).
3. El verificador de dimensiones de P0 responde correctamente a las doce expresiones del ejercicio con razón.
4. Los apartados de P9 con valores (§8.3, ES-10, ES-11) coinciden con los valores del informe del usuario.

---

## 19. Gráficas y visores interactivos

### 19.1 Reutilización y núcleo de gráficas

El patrón es el de `ui/waveform.py`: **una función pura `layout_*` que calcula geometría (sin Qt, determinista, comprobable con pruebas) + un widget que solo pinta**, con texto alternativo, etiqueta de cada traza y aviso cuando varios puntos caen en un píxel. El **núcleo de gráficas** (`ui/plot/`) es **propio sobre Qt y compartido** (D6, decidido) con el graficador de `MATH_LAB.md` §6 (que ya lista `stem`, convolución animada, espectro de líneas, módulo y fase en `[−1, 1]` y plano z para su bloque 15, y superficie de error, ROC y curva de aprendizaje para el 16) y con las gráficas de `CIRCUITS_LAB.md` §8.9 (Bode, polo-cero, espectro, formas de onda; formato `Trace`), que además generaliza `ui/waveform.py` (§3.8 de aquel). Lo define el primero que se construya y los demás lo extienden; SG-0 construye el mínimo y lo mide contra §19.5, y solo si no alcanza los objetivos se adopta una librería. Las capas de dibujo de señales (stem, dB, plano z, espectrograma) son **extensiones** del mismo núcleo.

### 19.2 Tipos de gráfica

| Tipo | Usos | Detalles |
|---|---|---|
| Línea `x(t)` | Señales analógicas, salida de filtros | Envolvente mín/máx cuando hay más puntos que píxeles |
| **`stem(n, x)`** | Secuencias, `h[n]`, DFT | Círculo en la punta; ejes `n`, `k`, `F` |
| Módulo y fase de `H` | Respuesta en frecuencia | Escala lineal o dB (declarado), fase envuelta o desenrollada; **líneas de tolerancia** de la plantilla |
| **Espectro `\|X[k]\|`** | Lectura directa e inversa | Picos marcados, cursor, ventana teórica superpuesta |
| **Plano z** | Polos y ceros | Círculo unidad, multiplicidad, región de convergencia, ejes cuadrados |
| Barras de ocupación módulo 1 | FDM, aliasing | Intervalos con patrón por señal |
| Réplicas del muestreo | Espectro de la señal muestreada | Solapes rellenos |
| Convolución animada | `x(λ)`, `h(t−λ)`, producto, `y(t)` | Puntos de ruptura marcados |
| Espectrograma | STFT | Mapa de calor con leyenda y alternativas de color |
| Histogramas, ROC, contornos | TRS | Áreas sombreadas, punto de operación |
| Constelaciones y diagramas de ojo | Modulación digital | De `comms/` |
| Superficies de error | Wiener y LMS | Contornos de `J(w)` con la trayectoria |

### 19.3 Interacción

Zoom y desplazamiento con ratón y **teclado** (flechas, `+`, `−`, `0`); **dos cursores** con lectura de diferencia (`Δt`, `Δf`, `ΔdB`) como en un osciloscopio y un analizador de espectro; marcadores con nombre; **animaciones** con reproducción, pausa y paso a paso (la convolución, el barrido de `f_m`, `F` sobre el círculo de `H(z)`); exportar a **PNG, SVG y CSV**; copiar valores bajo el cursor; **sincronización** de ejes entre vistas (tiempo, espectro y espectrograma).

### 19.4 Visores de instrumento

| Visor | Hermano de | Detalle |
|---|---|---|
| **Osciloscopio de señales** | Osciloscopio del laboratorio virtual | Disparo por nivel y flanco (`lab/measure`), medidas automáticas: máximo, mínimo, media, RMS, periodo y frecuencia (`lab/measure_*`) |
| **Analizador de espectro** | — | `\|X(f)\|`, ventana, promedio, marcadores de pico |
| **Medidor** | — | Energía, potencia, SNR, distorsión armónica total |
| **Altavoz** | — | Reproducción con límite de volumen (§27.3) |

### 19.5 Rendimiento de las gráficas

Objetivos: línea de `10⁶` puntos con envolvente a ≥ 30 fps; `stem` hasta `10⁴`; espectrograma como imagen precalculada; **`layout_*` puro por debajo de 50 ms** con `10⁴` elementos; geometría independiente de Qt y comprobable. Todo lo pesado en hilo aparte con cancelación.

### 19.6 Visor de Bode compartido

El visor de módulo en dB y fase se comparte con `CIRCUITS_LAB.md` §8.9.1 (gráfica «Bode», con `ac/bode.py` para los circuitos y las mediciones de §8.9.4): mismo componente, misma convención (`G = 20 log₁₀\|H\|`, frecuencias de corte y bandas con `threshold_bands` y `crossing_brackets`), mismos sellos. Los datos entran como `Trace` (`circuit-trace/1`, §8.9.2 de aquel) mediante un adaptador, de modo que se superponen prototipo, circuito simulado y medida.

### 19.7 Accesibilidad de las gráficas

Cada gráfica tiene **descripción textual** («espectro de 30 puntos; picos en `k = 7` y `k = 8` con valor 38,27; imagen en `k = 22` y `k = 23`») y **tabla** de valores navegable; el color nunca es el único canal (patrones y etiquetas); contraste suficiente; modo de alto contraste y de daltonismo; ver §28.

---

## 20. Calculadoras

Mismas reglas de `MATH_LAB.md` §8.1: entrada con vista previa, resultado exacto y aproximado con error, **pasos** (Resumen, Paso a paso, Detallado), **sello de verificación**, historial, copiar y enviar a otras calculadoras o laboratorios, y **uso por programa** sin interfaz. Las calculadoras son funciones del dominio con entrada y salida tipadas. **No se recorta ninguna aunque no salga en examen**, como pidió el usuario para el MATH_LAB.

| # | Calculadora | Qué hace (con pasos) | Fuente |
|---|---|---|---|
| C1 | **Frecuencias**: `f ↔ F ↔ ω ↔ k` | Conversión en ambos sentidos, plegado, frecuencia aparente, `k` y `N−k` | §4.2 |
| C2 | **Aliasing y Nyquist** | Veredicto, tasa y frecuencia de Nyquist, tabla multicomponente, `F` plegada | §10 |
| C3 | **Periodo** de sumas de sinusoides | Analógica: mcm de periodos; digital: `N₀` mínimo con `F·N₀` entero | SS-5 |
| C4 | **dB**: amplitud/potencia, razón ↔ dB, «veces inferior» | Aviso T1: pide el tipo y muestra las dos lecturas (`−40 dB` y `−20 dB`); suma de fuentes | `CI-RF-01` y §14.2 de `CIRCUITS_LAB.md` |
| C5 | **Resolución espectral** | Dados `L`, `N`, `f_m` y ventana: `Δf_res`, ancho del lóbulo, bins por lóbulo, **separación mínima** | §9 |
| C6 | **Lectura inversa de espectro** | El procedimiento de §8.5 con entradas `N`, picos, ceros; salida con intervalos y ambigüedades | §8.5 |
| C7 | **Amplitud de pico** de una sinusoide enventanada | `A·Σw/2` y escalonamiento máximo por ventana | §8.1 |
| C8 | **Tamaño de DFT** | `N ≥ L₁ + L₂ − 1`; solape para `N` menor; longitud de la convolución y de `r_y` | SS-14 |
| C9 | **Convolución discreta** con regímenes | Tabla de solapes; tramos; `Σy = Σx·Σh` | SS-3 |
| C10 | **Plantilla** `α_p`, `α_a` ↔ `δ_p`, `δ_a` | En ambos sentidos, con `H_max = 1 + δ_p` | §12.2 |
| C11 | **Orden mínimo** de filtro | Butterworth, Chebyshev I y II, elíptico, con `Ω = tan(πF)`; valores intermedios | §12.6 |
| C12 | **Longitud FIR estimada** | Kaiser (ventana) y Herrmann (equirrizado), con `β` de Kaiser | §12.3 |
| C13 | **Bilineal con pre-distorsión** | `Ω = tan(πF)`, frecuencia analógica de diseño, `dsp.bilinear_design` | §12.6 |
| C14 | **Eco y reverberación** | `H(z)`, módulo de los ceros o polos `\|a\|^{1/L}`, `\|H(F)\|²`, extremos, inverso `b = −a`, `n₀ = L` | §7.7 |
| C15 | **Filtro compensador del D/A** | `1/sinc` o `1/sinc²` en el borde de banda, especificación `f_p`, `f_a` | §10.5 |
| C16 | **Planificador FDM/TDM** | Ocupación bilateral, `f_m` mínima, solapes módulo 1; `T ≤ 1/(2B)`, `D ≤ T/N` | §11 |
| C17 | **Modulación** | Ancho de banda de AM, DSB, SSB; Carson; índice y potencia | §11 |
| C18 | **Cuantización** | `SQNR = 6,02 b + 1,76`, `Δ`, bits necesarios | §16 |
| C19 | **Diezmado e interpolación** | Frecuencia resultante, aliasing aparente, `L/M` y coste polifásico | §15 |
| C20 | **Retardo por correlación** | Retardo y atenuación desde el pico de `r_yx`; distancia si se da la velocidad | §13.2 |
| C21 | **Nota y tecla** | `f` de una nota (MIDI); pareja de tonos DTMF de una tecla | §8.6 |
| C22 | **Energía y potencia** | Por tiempo y por frecuencia (Parseval, dos caminos) con `MATH_LAB` | SS-6 |
| C23 | **Duración efectiva** de `h` | `t = T ln(1/ε)` con `ε` declarada en amplitud o potencia | ES-20 |
| C24 | **Equivalencia MATLAB / Python** | Tabla de funciones (Anexo F) y generación de código | §18 |
| C25 | **Ganancia en dB de un sistema** `H(f)` | Módulo, dB, fase, frecuencia de −3 dB, de −60 dB | SS-4 |

Todas pasan la **batería común** (§29): propiedades con semilla, ejemplos dorados y contraste con NumPy, SciPy o SymPy si están instalados.

---

## 21. Ejercicios, plantilla, corrección y generador sembrado

### 21.1 Plantilla única de ejercicio

La misma que usan el laboratorio digital (`DIGITAL_DESIGN_LAB.md` §22.8) y el de matemáticas (`MATH_LAB.md` §7), ampliada con los campos propios de señales:

| Campo | Contenido |
|---|---|
| Id y origen | `SG-LR-0007`; si viene de examen, la clave del catálogo (`SS-12`, año y tipo `F`, `P1`, `P2`) y el id de caso `ES-nn` |
| Enunciado | Texto generado a partir de parámetros sembrados, **parafraseado** (no copiado) |
| Datos | Parámetros, `f_m`, `N`, `L`, ventana, plantilla; y la **semilla** |
| **Convenciones declaradas** | dB de amplitud o potencia, ventana simétrica o periódica, espectro bilateral o unilateral, `H_ref` (§4.4) |
| Figura (dato) | `Figure` generada (picos, tramos, curva) con su gráfica; **lecturas** que el alumno teclea (§8.8) |
| Apartados encadenados | Resultados intermedios guardados y ofrecidos a los apartados siguientes (`MATH_LAB.md` §15.2-2) |
| Entregable | Valor con unidad, intervalo, lista de picos, clase (ventana, usuario), gráfica dibujada, filtro diseñado, cadena de bloques, expresión |
| Solución | Traza paso a paso (E0, §26), con apartados (a), (b), (c) como el enunciado |
| Gráfica esperada | Generada **de la traza**, no escrita a mano |
| Verificación | Segundo camino (§25) y sello |
| Errores comunes | Lista de respuestas erróneas típicas con su diagnóstico (§21.5) |
| Asignatura, tema, competencia | SST: CE10, CG3, CT5, CB2; TRS: CE21, CE22, CB5; tema de la guía |
| Frecuencia en examen | Del informe `extra_senales.md` (para ordenar prioridades) |

### 21.2 Tipos de respuesta y corrección

Determinista, **por equivalencia o por propiedad**, nunca por texto, y **el modelo nunca califica** (mismo principio del corrector certificado del proyecto).

| Tipo de respuesta | Criterio | Tolerancia |
|---|---|---|
| Número con unidad | Magnitud y dimensión correctas; valor relativo | `1 %` por defecto (configurable); exacto si es entero (`L`, `k`, orden) |
| Número exacto (`2/π`, `√2/2`) | Equivalencia con el motor de `MATH_LAB` (§7 de aquel) | exacta |
| **Intervalo** (p. ej. `L ∈ [54, 57]`) | La respuesta del alumno cae dentro **y** el intervalo contiene el valor verdadero | por contención |
| Lista de **picos** `(k, valor)` | Emparejamiento por `k` y valor | `±0` en `k` o `±1` si el enunciado lo declara; valor al 1 % |
| **Clase** (ventana, usuario, dígito, nota) | Igualdad | — |
| **Gráfica dibujada** (espectro, cronograma, `x(t)` por tramos) | **Comparación por eventos** (posición y valor de picos, ceros, cruces, rupturas), no por píxeles | Tolerancia configurable en cada eje |
| **Filtro diseñado** (`b`, `a`, o polos y ceros) | **Por propiedad**: ¿cumple la plantilla?, ¿orden mínimo?, ¿estable?, ¿fase lineal?; **no** se comparan coeficientes (la solución no es única) | La que fija la plantilla (`δ_p`, `δ_a`) |
| **Cadena de bloques** | Comparación por respuesta (misma salida para entradas de prueba sembradas) | `10⁻⁶` |
| **Expresión** | Equivalencia por simplificación o por puntos sembrados (`MATH_LAB` §7) | — |
| Demostración guiada | Lista de pasos con hipótesis comprobadas | — |

### 21.3 Pistas graduadas y modos

- **Pistas** en tres niveles: orientación («¿cuántos ceros tiene la ventana en el eje?»), fórmula, primer paso resuelto.
- **Modo estudio**: predice el siguiente paso (p. ej. el valor del pico) y corrige.
- **Modo examen**: sin ayudas, con tiempo y puntuación por apartado.
- **Modo asistido** de la lectura inversa: el alumno escoge el paso (primero `Δk`, luego `L`) y el laboratorio dice si es adecuado.

### 21.4 Generador sembrado por familia

Cada familia produce **enunciado, figura y solución** de forma reproducible a partir de una semilla y un nivel de dificultad. Restricciones de buena formación (por ejemplo, evitar que la lectura inversa sea ambigua salvo que el nivel lo pida).

| Familia (id) | Parámetros sorteados | Niveles | Restricciones |
|---|---|---|---|
| **Lectura inversa** (`SS-12`) | `L ∈ [20, 200]`, `N ∈ {512, 1000, 2048, 4096, 10 000}`, `A ∈ [0,5; 10]`, `F₀`, ventana (rect, tri, Hann), nº de tonos | 1: rectangular, un tono, bin exacto; 2: entre bins; 3: dos tonos; 4: ventana desconocida, aliasing y ruido sembrado | `N ≥ L`; ceros dentro del eje; ambigüedad de `L` solo en nivel ≥ 2 |
| **Ventana** (`SS-13`) | Relación lóbulo/lateral con ruido de lectura | 1 a 3 | Valores separados por más de 5 dB |
| **Aliasing** (`SS-9`) | `f`, `f_m`, banda; trémolo; D/A con ZOH o triángulo | 1 a 4 | `f_m` fuera de Nyquist por una cantidad no trivial |
| **FDM/TDM** (`SS-15`) | Nº de señales, `B`, definición de `B` | 1 a 3 | Definición de `B` explícita |
| **Convolución** (`SS-2`, `SS-3`) | Pulsos, exponenciales, retardos | 1 a 3 | Puntos de ruptura enteros |
| **Propiedades de sistemas** (`SS-1`) | Sistema de una lista de 30, parámetros | 1 a 3 | Respuesta conocida |
| **Eco e inverso** (`SS-11`) | `a`, `L`, `f_m` | 1 a 3 | `\|a\| ≠ 1` salvo nivel 4 |
| **Respuesta en frecuencia** (`SS-4`) | `h` y frecuencias; convención dB | 1 a 3 | T1 declarado |
| **Filtros** (`SS-16`, `SS-17`) | Plantilla `(f_p, f_a, α_p, α_a, f_m)` | 1: orden mínimo; 2: ventana adecuada; 3: familia IIR; 4: comparación | Orden razonable |
| **Detección, estimación, Wiener, LMS** (`TRS-3..8`) | Parámetros | 1 a 3 | Se corrigen con `MATH_LAB` |

### 21.5 Errores comunes (catálogo de diagnóstico)

Cada ejercicio detecta respuestas típicas **y explica** el error: (a) `A = |X|_pico/L` en lugar de `2|X|_pico/Σw` (olvidó la mitad por el par `±F₀`); (b) `L = N/Δk` con `Δk` en Hz en lugar de en bins; (c) mezclar dB de amplitud y de potencia; (d) tomar el cero de la ventana triangular como el de la rectangular; (e) olvidar `N − k` en el pico imagen; (f) confundir `f_m` mínima con frecuencia de Nyquist (`2B` frente a `f_m/2`); (g) en el inverso del eco, olvidar el **retardo `n₀ = L`**; (h) mala elección de la señal base de una periódica; (i) olvidar el retardo de grupo `M` de un FIR causalizado; (j) no incluir la **ganancia compensadora** en el filtro del D/A. Las (g) y (h) son errores que el alumno anota en su informe del simulacro de parcial (P7).

### 21.6 Enlace con el banco de preguntas y la maestría

Los ejercicios se integran en el banco de preguntas y en la maestría del proyecto (`application/exercise_service.py`, `mastery.py`, `correction.py`) como **nuevo tipo de pregunta «señales»**, con corrección determinista; resolver ejercicios con verificación actualiza el dominio, igual que en el laboratorio digital (`DIGITAL_DESIGN_LAB.md` §15.2 y §15.3).

### 21.7 Criterios de aceptación

1. Cada familia de §21.4 genera 100 ejercicios sembrados distintos con solución verificada por segundo camino y **sin ambigüedad** (salvo declarada).
2. La corrección acepta respuestas equivalentes (`L ∈ {55, 56}` si el enunciado da el intervalo; `0,5` por `1/2`; filtro con otros coeficientes que cumple la plantilla).
3. Para cada ejercicio, mismo semilla ⇒ mismo enunciado, figura, solución y *digest*.
4. El corrector **rechaza** un filtro que no cumple la plantilla y señala la violación.

---

## 22. Casos de prueba de exámenes reales

### 22.1 Reglas de uso

- Los exámenes son **material de la universidad** y no se copian al repositorio (regla D5 de `MATH_LAB.md`). Las pruebas del proyecto usan **problemas propios de la misma forma** (parafraseados, con datos nuevos), y los **valores** de esta tabla son resultados de **cálculo** (fórmula o prototipo), no texto de enunciado.
- Una **prueba opcional** apunta a la carpeta local del usuario (ruta configurable `SST_MATERIAL_DIR`) y se omite si no existe; sirve para contrastar el laboratorio con las soluciones oficiales.
- Hay que **leer la solución oficial** como referencia, pero **no** se compara texto; se verifica por segundo camino y se señalan las erratas (§4.5).
- Los valores marcados **(a confirmar)** dependen de un dato del enunciado que no se pudo leer en el texto extraído (OCR parcial) y se cierran con el PDF original.

### 22.2 Tabla de casos

`F` = final, `P1`/`P2` = primer/segundo parcial; fuente: `extra_senales.md` y las prácticas. «Valor» = resultado esperado del laboratorio (vía exacta y rápida).

| Id | Origen | Bloque | Datos (paráfrasis) | Valor esperado | Comprobación |
|---|---|---|---|---|---|
| **ES-01** | P2 y finales | SS-12 | Primer cero del lóbulo a `Δk = 18` bins; `N = 1 000`; rectangular | `L = N/Δk ≈ 55,6`; con la incertidumbre de lectura, **`L ∈ [54,1; 57,1]`**; el examen usa `L ≈ 55` | Modelo directo con `L = 55`: primer cero en `k ≈ 18,2` |
| **ES-02** | P2 2023 | SS-12 | Quinto cero a `Δk = 500`; `N = 10 000` | `L = 5·N/Δk = 100` exacto. Además: enunciado con `N = 1 000` y figura con `N = 1 500` (errata): aviso | Dos valores de `N` |
| **ES-03** | P2 2020-21 | SS-13 | Pico principal 383 y mayor lateral 18,27 | `20 log₁₀(383/18,27) = 26,4 dB` ⇒ **triangular** (−26,5) | Medida sobre `W(F)` |
| **ES-04** | F 2022 ej. 3 | SS-12 | `L = 40`, `f_m = 16 MHz`, tercer usuario | Separación mínima `2/L · f_m = 0,05 · 16 MHz = 0,8 MHz` | Solape de lóbulos medido |
| **ES-05** | Varios | SS-9, SS-12 | `cos(2π·0,52n)` | Idéntica a `cos(2π·0,48n)`: `F` aparente `0,48` | `alias_of`; DFT con pico en `k = 0,48N` |
| **ES-06** | P9 | SS-12 | `A = 4`, `f_x = 2 kHz`, `f_m = 8 kHz`, `L = N = 30` | `\|X[7]\| = \|X[8]\| = 38,267`; `\|X[6]\| = \|X[9]\| = 12,944`; `\|X[5]\| = \|X[10]\| = 8,000`; `f̂ = 1 866,7` o `2 133,3 Hz`; `Â = 2,551` | Fórmula de Dirichlet y FFT |
| **ES-07** | P9 | SS-12 | Idem con `N = 4 096` (relleno de ceros) | Pico `60,000` en `k = 1 024`; `f̂ = 2 000 Hz`; `Â = 4` | |
| **ES-08** | P9 | SS-12 | `f_x = 2 147 Hz`, `N = 30` | `k = 8`, `\|X\| = 59,81`, `f̂ = 2 133,3 Hz` (error −13,7 Hz), `Â = 3,987` | |
| **ES-09** | P9 | SS-12 | `f_x = 2 400 Hz`, `N = L = 30` (`F₀ = 0,3`) | Un solo bin `k = 9`, `\|X\| = 60`, `Â = 4`, resto nulo | `N f_x/f_m` entero |
| **ES-10** | P9 | SS-13 | `x[n] = 4cos(2π·0,25 n)`, `n = −9..9`, `w = [1:10, 9:−1:1]/10`, `N = 512` | `Σw = 10`; **pico 20 en `k = 128` y `k = 384`**; `A = 2·20/10 = 4` | Fórmula y FFT |
| **ES-11** | P9 | SS-14 | `p₆ * p₆`; DFT de `N` puntos del cuadrado | Convolución lineal `[1,2,3,4,5,6,5,4,3,2,1]`; `N = 16` y `15` coinciden; `N = 10` falla en `n = 0` (valor 2); `N = 9`: `[3,3,3,4,5,6,5,4,3]`; **mínimo `N = 11`** | Comparación con `conv` |
| **ES-12** | P1 2025, F 2023 Q2 | SS-11 | `y[n] = x[n] + a y[n−L]`, `a = ½`, `L = 10` y `20` | `L` polos en `\|p\| = ½^{1/L}`: **0,9330** y **0,9659**; estable | `roots` |
| **ES-13** | P1, F | SS-11 | `y[n] = x[n] + a x[n−L]` | `L` ceros en el mismo módulo; `\|H(F)\|² = 1 + a² + 2a cos(2πLF)` con máx. `(1+a)²` y mín. `(1−a)²` | Barrido en `F` |
| **ES-14** | P7, F | SS-11 | Inverso del eco: `z[n] = y[n] + b z[n−L]` | `b = −a`, `n₀ = L`; con `\|a\| > 1` el inverso causal es **inestable** | `z = x` numérico |
| **ES-15** | F 2022 ej. 2 | SS-9 | `B = 4 kHz`, `T = 0,1 ms` (`f_m = 10 kHz`), D/A con triángulo `Λ(t/T)` | `f_m ≥ 2B` cumple; plantilla: paso hasta `4 kHz`, atenuada desde **`f_m − B = 6 kHz`**; compensación **`+4,84 dB`** a `4 kHz` (ZOH: `+2,42 dB`) | `sinc(0,4) = 0,7568`, `sinc² = 0,5728` |
| **ES-16** | F 2023 Q1, F 2024 | SS-15 | Tres señales de `B = 10 kHz` en FDM | `f_m ≥ 8B = 80 kHz` en el enunciado de referencia **(a confirmar la definición de `B`)** | Comprobador módulo 1 |
| **ES-17** | F 2024 Q1 | SS-15 | Condición de portadora `B/f_m ≤ F ≤ 1/2 − 2B/f_m`; `f_m ≥ 120 kHz` en el caso de referencia | **(a confirmar)** | Comprobador módulo 1 |
| **ES-18** | Varios | SS-4 | «100 veces inferior» | Amplitud: **−40 dB**; potencia: **−20 dB**; el laboratorio exige declarar | Calculadora C4 |
| **ES-19** | F jun-2021 | SS-4 | `h(t) = e^{−t/10}u(t)`; `10 log\|H\|² = −60 dB` frente a `H(0)` | `H(f)/H(0) = 1/(1 + j20πf)`: `−3 dB` en `f = 1/(20π) = 0,01592 Hz`; **`−60 dB` en `f = √(10⁶−1)/(20π) = 15,915 Hz`** | `H` numérica |
| **ES-20** | F 2022 ej. 1 | SS-4, SS-1 | `h(t) = e^{−t/10}u(t)` | **Duración efectiva** (`h_max/h = 100`): `10 ln 100 = 46,05 s`; `H(f) = 10/(1 + j20πf)`; con `H_ref = 1`: **20 dB a 0 Hz y −2,01 dB a 0,2 Hz** (`\|H(0,2)\| = 0,7933`); con `H_ref = \|H\|max = 10`: 0 dB y −22,01 dB | Convención declarada |
| **ES-21** | F 2023 | SS-9 | Trémolo `x(t)·(1 + m cos(2π·10 t))` con `f_x` | Ancho de banda tras el sistema `f_x + 10 Hz` ⇒ `f_m > 2(f_x + 10)` **(parámetros a confirmar)** | |
| **ES-22** | P7 | SS-11 | Eco `δ(t) + ½δ(t − 1 ms)` | `\|H(f)\| = \|1 + ½e^{−j2πf·10⁻³}\|`: máximo 1,5 en múltiplos de 1 kHz, mínimo 0,5 en `(2k+1)·500 Hz` | Barrido |
| **ES-23** | P7 | SS-5 | Onda cuadrada ±`A`, `A = 2` | Fundamental `4A/π = 2,546`; armónicos pares nulos | Serie por `MATH_LAB`; FFT |
| **ES-24** | P4 | SS-10 | `x[n] = p₁₁[n + 5]` | `X(F) = sin(11πF)/sin(πF)` real; máx. 11 en `F = 0`; ceros en `k/11`; periodo 1 | Suma truncada y DFT densa |
| **ES-25** | P4 | SS-10 | `x[n] = aⁿu[n]`, `a = ±0,8` | `\|X\|² = 1/(1 + a² − 2a cos 2πF)`: `a = 0,8`: máx. 5 (`F = 0`), mín. 0,5556 (`F = ½`); `a = −0,8`: al revés | |
| **ES-26** | P2 | SS-3 | Cinco convoluciones de la práctica | Longitud `L₁ + L₂ − 1`; `Σz = Σx·Σy`; regímenes de `p₅₀ * 2·0,9ⁿu[n]` **(parámetros a confirmar)** | `conv` |
| **ES-27** | P10 | SS-16 | `f_m = 16 kHz`, `f_p = 3,6`, `f_a = 4`, `α_p = 1 dB`, `α_a = 40 dB` | `δ_p = 0,05750`, `δ_a = 0,010575`; `α_p = 20 log₁₀((1+δ_p)/(1−δ_p)) = 1 dB` | Fórmulas |
| **ES-28** | P10 | SS-16 | La misma plantilla, FIR por ventanas de corte `0,2375` | Rectangular **nunca** cumple (−29,6 dB con `L = 201`); Hamming cumple con `L ≈ 121 a 131`; Kaiser `β = 3,34` con `L ≈ 91`; Parks-McClellan estimado `≈ 53 a 54` (a medir) | `check` de plantilla |
| **ES-29** | P11 | SS-17 | `f_m = 16 kHz`, `f_p = 3,7`, `f_a = 4`, `α_p = 1`, `α_a = 60` | Órdenes **65** (Butterworth), **17** (Chebyshev I y II), **8** (elíptico) | Fórmulas y SciPy |
| **ES-30** | P11 | SS-17 | Butterworth de orden 65, forma `(b, a)` y SOS | Aviso de inestabilidad numérica en `(b, a)`; SOS estable; `\|p\|max < 1` | `roots`, `sosfilt` |
| **ES-31** | P5 | SS-13 | Ventanas `Π(t/T)` y `Λ(2t/T)`, `T = 15 ms` | Rectangular: `T sinc(Tf)`, cero en `66,7 Hz`; triángulo de base `T`: `(T/2)sinc²(Tf/2)`, cero en `133 Hz` (**errata candidata** del informe: `sinc²(Tf)`) | Medida del cero |
| **ES-32** | P5 | SS-12 | Tecla con `x(t) = ½cos(2πf_f t) + ½cos(2πf_c t)`, `T = 15 ms` | Dos picos en `(f_f, f_c)` ⇒ tecla; par más próximo 941 y 1 209 Hz (268 Hz) frente a lóbulo `4/T = 267 Hz` (triángulo) | `tecla.wav` (opcional) |
| **ES-33** | P6 | SS-15 | Dos audios, `f_m = 16 kHz`, `B_Hz = 4 kHz`, `h_M = 2B sinc(2Bn)` | `B = 0,25`; `Y(F)` con dos bandas dentro de `[−0,5; 0,5)`; recuperación del canal 2 con error cuadrático normalizado `< 10⁻²` | Simulación |
| **ES-34** | F 2020-2, F 2023 Q1 | SS-8 | Pulsos ortogonales de `L_s` muestras; filtro adaptado; `N` de la DFT | `N ≥ L_s + L_h − 1`; `y[0] = (1/N)ΣY[k] = Σ s[n]p[n]` (energía si `s = p`; 0 si ortogonal) | Salida temporal |
| **ES-35** | F 10-1-2020, ej. 2.2 | SS-7 | `R_{p₁p₂}` de dos pulsos | Una de las tres soluciones oficiales tiene el signo mal; la **correlación numérica** decide | Errata |
| **ES-36** | F 2022 ej. 1.7 | SS-7 | Correlación cruzada con un pico | Retardo `T₀ = τ̂` y ganancia `a = r_yx(τ̂)/r_x(0)` **(valores a confirmar)** | |
| **ES-37** | F 2022 ej. 3 | SS-12 | Dos usuarios con `L = 40` muestras y `f_m = 16 MHz` (frecuencias a confirmar) | Pico esperado `A·L/2`; umbral razonado; tercer usuario a ≥ 0,8 MHz | Monte Carlo |
| **ES-38** | P9-30 | SS-16 | Muestreo en frecuencia, `N = 128` | `h[n]` simétrica; `H` coincide en las muestras y **rizado entre ellas** | `N = 4 096` |
| **ES-39** | F 2023 Q1 | SS-15 | TDM de `N` canales de ancho `B` | `T ≤ 1/(2B)`, `D ≤ T/N` | Simulación |
| **ES-40** | P1 | Audio | `dm_serie.mp3`, `f_m = 44 100` | 1 736 688 muestras, máx. 0,94201, mín. −0,95193, media `−2,2445·10⁻⁵`, energía 30 447,1061, 39,3807 s | **Privado y opcional** |

### 22.3 Cobertura

Los 40 casos cubren **todos los bloques P1** de `extra_senales.md` (SS-0 a SS-5, SS-9, SS-10, SS-12, SS-13) y los P2 de este laboratorio (SS-8, SS-11, SS-14, SS-15, SS-16, SS-17), más las prácticas P2 a P11. Cada caso se programa como **prueba de dominio sin Qt** con su semilla (§29.2).

---

## 23. Interoperabilidad

### 23.1 Con el motor matemático (`MATH_LAB.md` v2: §5.9, §16, bloques 15 y 16)

El motor matemático es la **fuente de verdad simbólica**; este laboratorio es la **fuente de verdad numérica y gráfica**. Cada uno es el **segundo camino** del otro (principio 3 de `MATH_LAB.md` §1.2). El reparto es la tabla de `MATH_LAB.md` §16.1 «Tabla de referencias cruzadas».

| Capacidad de `MATH_LAB` (nombre y sección) | Qué pide este laboratorio | Qué devuelve a `MATH_LAB` |
|---|---|---|
| Expresiones y exactitud (§5.1): por tramos, racionales multivariable, áreas de delta | Convertir una `Signal` o `Figure` a **expresión por tramos** (`Σ A_i Π((t−t_i)/T_i)`) y viceversa | Evaluación en malla fina (`float`) para comparar con la expresión |
| Pasos (§5.2), «Por qué este método» (§5.5b), cambios de variable (§5.6), hipótesis (§5.7) | Cuando un apartado pide solución exacta, la **traza** del motor se muestra tal cual, con su «por qué» | — |
| Verificación independiente (§5.3) y librerías de verificación (§5.8) | Sello `✔ Verificado` / `⚠ Solo numérico` / `✘ Discrepa`; NumPy, SciPy y SymPy opcionales, con «no contrastada con librería externa» si faltan | **Contraste numérico**: `dtft_at`, DFT densa, convolución por malla o FFT, Monte Carlo sembrado, medida de espectro con error |
| Contrato con los demás laboratorios (§5.9) | Llamada tipada `calcular(...)`, traza serializable, sello, gráfica descrita como datos | **Plug-in de verificación** `verificar(resultado) → veredicto + discrepancia`: este laboratorio registra `dsp/dft.py` (el ejemplo de §5.9) y `signals/spectrum.py` |
| Convenciones declaradas (§5.11) | Las de §4 son las de §5.11 (frecuencia ordinaria, `F = f/f_m`, dB de amplitud o potencia, correlación); cada ejercicio las declara | La verificación con la convención contraria |
| Bloque 15 «Señales y sistemas deterministas» (§4.15; calculadoras §8.2-Q): biblioteca, convolución, periódicas, energía y potencia, correlación y PSD deterministas, DTFT, DFT, eco e inverso | El valor **exacto** y los pasos de cada una, por «uso por programa» (§8.1) | La figura enlazada y las medidas numéricas |
| Bloque 16 «Detección y estimación» (§4.16; calculadoras §8.2-R): TRS-3 a TRS-8 | Curvas teóricas (ROC, cota, `J_min`, PSD) | Monte Carlo sembrado con intervalo de confianza |
| Cotas racionales (§8.2-A) | `sinc(1/2) = 2/π` y desigualdades de ventana sin calculadora | — |
| Corrector por equivalencia (§7) y figuras como datos (§7, v2) | Respuestas de tipo expresión; la plantilla única | Las respuestas de tipo **medida** y de **figura** las corrige este laboratorio (§21.2) |

**Contrato de intercambio** (tipado, determinista, sin Qt): el `Resultado` de `MATH_LAB.md` §5.9 (aquí llamado `ExactResult`: valor exacto, traza, hipótesis, sello, convenciones) ↔ `NumericResult` (valor `Decimal` o `float`, intervalo de error, método, semilla, *digest*). Si ambos discrepan, el sello es `✘ Discrepa`, el caso se **guarda** y no se da por bueno ninguno hasta resolverlo. Si el plug-in de verificación falta, el sello baja a `⚠ Solo numérico`.

**Estado de lo que se pidió al otro documento** (ya recogido en `MATH_LAB.md` v2): (1) la biblioteca de señales por tramos de SS-0 (§4.15, primera fila); (2) la TF y la DTFT de esas señales con pasos (§4.15, DTFT); (3) áreas de delta (§5.1 y nota de §4.15); (4) un punto de entrada por programa para cada calculadora (§5.9 y §8.1).

**Temas que `MATH_LAB.md` §16.3 propone provisionalmente para este laboratorio** (su D12 sigue pendiente): propiedades de sistemas (§7.1), respuesta en frecuencia a sinusoides (§7.5), PSD de procesos discretos (§14.4 y §17, compartida con `MATH_LAB`) y cuantización (§16). Aquí se incluyen tal como propone ese informe; si el usuario los reasigna, solo cambian las filas correspondientes de §3.1.

### 23.2 Con el código existente

| Módulo | Uso | Regla |
|---|---|---|
| `dsp/` | Vía exacta: `fft`, `dft`, `dtft_at`, `circular_convolve`, `alias_of`, `nyquist_*`, `reconstruct`, `TransferFunctionZ`, `bilinear_design`, `sos_decompose`, `iir_stability`, `linear_phase_report`; `DspDocument` para el formato | **No se modifica**; se amplía con `signals/` |
| `comms/` | Modulaciones digitales, `matched_filter`, `correlator_decide`, pulsos `RC/RRC`, `sinc_unit`, BER, flujos sembrados | No se duplica |
| `ac/bode.py` | Cortes, bandas, extremos, desenrollado de fase, `log_frequencies` | El visor de Bode lo reutiliza |
| `control/tf.py`, `control/poly.py` | `TransferFunctionTF` como prototipo analógico para `bilinear_design` | Contrato en §23.4 |
| `symbolic/`, `math/` | Contexto `Decimal` (`make_context`), trigonometría, complejos, racionales | — |
| `application/explain_service.py`, `domain/execution/` | Traza E0 | §26 |

### 23.3 Con el laboratorio virtual (`lab/`)

Adaptadores **estructurales** en `application/` (nunca `dsp → lab`; ver el docstring de `dsp/sequences.py`):

- `waveform_to_signal(wave, f_m)`: de la `Waveform` lineal a tramos de una simulación (transitorio MNA o ngspice) a una `Signal` muestreada por **evaluación exacta del punto**, para llevar la salida de un circuito al espectro, al espectrograma o al filtro.
- `signal_to_stimulus(signal)`: solo si es `sine`, `pulse/square` o `dc` (únicos generadores certificados de `lab/stimulus.py`); si no, se avisa («esta señal no se puede inyectar como fuente certificada»).
- Barrido AC de un circuito ⇄ `H(f)` del visor de §7.5.

### 23.4 Con `CIRCUITS_LAB.md`

Ese documento ya está redactado; la numeración citada es la verificada el 2026-10-01 (§3.8 reorganización, §6 dibujo dinámico, §8 simulación y gráficas, §10 circuitos analógicos, §14 calculadoras). Lo que se espera y lo que se ofrece:

| Contrato | Descripción |
|---|---|
| **`AnalogFilterPrototype`** | Familia, orden, plantilla en Hz (`f_p`, `f_a`, `α_p`, `α_a`), polos y ceros en `s` (rad/s), ganancia, descomposición en secciones (`ω₀`, `Q`, tipo), `H_ref`. Por D8 lo define **el primero que se construya** (SG-9 aquí, o el solver `CI-AN-FILT` de §10.11 allí, que necesita lo mismo: especificaciones a orden y polos) y el otro lo **importa**; hay una sola función de orden mínimo, usada por la calculadora C11 y por la de filtros activos de §14.2 |
| **`AnalogFilterRealization`** | Topología (Sallen-Key, realimentación múltiple, biquad de estado), valores `R` y `C` (series E), sensibilidad (§10.11); vuelve aquí para comparar su Bode con el del prototipo |
| **Bode y gráficas** | Visor y convención compartidos (§19.6); `ac/bode.py`; formato `Trace` de §8.9.2 de aquel con adaptador |
| **dB y escalas** | Una única calculadora de dB (`CI-RF-01`, §14.2 de aquel); este laboratorio la **reutiliza** (C4). La **convención** de dB es de `MATH_LAB.md` §5.11 (`MATH_LAB.md` §16.1) |
| **Antialiasing y reconstrucción** | La plantilla `f_p = B`, `f_a = f_m − B` se define aquí; su realización con componentes, en §10.11 de aquel |
| **Mezcladores, detector de envolvente, VCO** | Circuitos allí (§10); espectros aquí |
| **ADC y DAC** | Arquitecturas, INL/DNL y ENOB allí (§10.15, `BL-AN-14`; `CI-AN-14` es Bode, no el ADC) y en `DIGITAL_DESIGN_LAB.md` §22.6; teoría de cuantización, SQNR medido y visor aquí (§16). La fórmula `6,02 b + 1,76 dB` es la misma en los dos textos |
| **Respuesta de circuito a señal** | `waveform_to_signal` (§23.3); la simulación es la de §8 de aquel (transitorio §8.5, AC §8.6, Fourier §8.8) |
| **Dibujo dinámico (§6 de aquel)** | Sus modos de pequeña señal (M2a, M2b, M2c) dibujan el circuito equivalente del que sale un `H(s)`; este laboratorio **no dibuja circuitos**, consume el `H(s)` resultante. El diagrama de bloques de solo lectura de §7.8 usa el núcleo de lienzo compartido (§3 de aquel y DL-3) si existe |
| **Reparto de paquetes (§3.8 de aquel)** | `dsp/` sale de circuitos hacia este laboratorio; `comms/` se queda allí (su D7, a revisar); el control discreto (`BL-CT-9`) y el ADC **consumen** `dsp/` por su interfaz pública; el renombrado a `domain/circuits/` (CI-R) afecta a las rutas (nota de §3.2) |

### 23.5 Con el laboratorio digital (`DIGITAL_DESIGN_LAB.md`)

Frontera con §22.6 de aquel («Sistemas de Hardware de Procesado»): el laboratorio digital **realiza en hardware** (coma fija `Qm.n`, estructuras, CORDIC, ADC/DAC, protocolos) y este **diseña y analiza en teoría de señales**. Solapes y reparto:

| Tema | Responsable | Nota |
|---|---|---|
| Diseño del filtro (plantilla, familia, orden, coeficientes en coma flotante) | **Este** | Objeto `FilterDesign` |
| Cuantización de coeficientes, estructuras en coma fija, desbordamiento, coste en puertas | **Digital (DL-20)** | Consume `FilterDesign`; aquí solo el visor mínimo de §12.8 (D20) |
| LMS: teoría y curva de convergencia | `MATH_LAB` (teoría) y **este** (escena §17) | Digital solo la realización hardware |
| Modulación digital (constelaciones) | `comms/` (existente) | Este laboratorio la usa para el espectro; Digital, para la forma de onda de bits |
| Cuantización y SQNR | **Este** (§16) | Digital: ruido de cuantización en hardware (referencia cruzada) |
| Visión general de la relación con el diseño digital | Ver `DIGITAL_DESIGN_LAB.md` §23 (mapa de frontera, dependencias y decisiones D17 a D19) | Rótulo visible «Diseño digital»; D12 aquí depende de DL-11 y D20 de DL-20 |

### 23.6 Con el resto de la aplicación

Banco de preguntas, maestría y corrección (§21.6); documentos (informes de práctica, §27.5); búsqueda; tutor socrático opcional (`F12`): puede **explicar** la traza, nunca calificar; ruta nueva `engineering/signals` en `ui/routes.py` y entrada en `ui/modules.py` (que solo lista capacidades reales); errores a través del conversor único `to_ui_error` y nuevos códigos en `docs/specs/ERROR-CODES.md`; el motor de **explicación** y de **repetición** de `domain/execution`.

---

## 24. Motor numérico: vía exacta y vía rápida

### 24.1 Por qué dos vías

El motor certificado `dsp/` trabaja en `Decimal` con topes deliberados: `MAX_FFT_N = 4 096`, `MAX_DIRECT_DFT_N = 512`, `MAX_SEQUENCE_N = 65 536`, y la FFT exige potencia de 2 (no hay Bluestein). Eso es **ideal para enseñar y verificar** (resultados exactos, sin ruido de redondeo, con nodos exactos) y **inviable para mirar**: el audio de la P1 tiene 1 736 688 muestras, un espectrograma de 40 s necesita unas 6 800 FFT de 1 024 puntos, y la práctica P9 pide `N = 4 096` y DFT de longitud 30 (no potencia de 2). La vía rápida no sustituye a la exacta: la **contrasta**.

### 24.2 Comparación

| Aspecto | **Vía exacta** | **Vía rápida** |
|---|---|---|
| Aritmética | `Decimal` bajo `make_context()`; `DecimalComplex`; trigonometría certificada | `float64` y `complex128` |
| Módulos | `dsp/` existente (`fft`, `dft`, `dtft_at`, `reconstruct`, `alias_of`), `comms/` | `signals/spectrum.py`, `stft.py`, `lti.py`, `fir_design.py`, `iir_design.py`, `multirate.py`, `process.py` |
| Límites | `N ≤ 4 096` (FFT), `≤ 512` (DFT directa), `≤ 65 536` muestras | `≤ 2²⁴` muestras (D13); FFT de longitud arbitraria |
| Uso | **Soluciones y pasos de ejercicios**, casos dorados, verificación | Visores, audio, espectrograma, simulaciones Monte Carlo, diseño de filtros, prácticas |
| Determinismo | Bit a bit en cualquier plataforma | Igual semilla ⇒ mismos números hasta `~10⁻¹³` relativo; el *digest* usa una **representación redondeada** (12 cifras significativas) |
| Sello | `Verificado` cuando coincide con un segundo camino independiente | `Verificado` solo si coincide con la exacta en puntos sembrados o con un oráculo; si no, `Solo numérico` |

### 24.3 Implementación de la vía rápida

- **NumPy es opcional** (D2, decidido; se añade a `requirements.txt` como **recomendado**, nunca obligatorio). Con NumPy: `numpy.fft`, `convolve`, ventanas vectorizadas, remuestreo. **Sin NumPy**: implementación en Python puro (`cmath`, listas o `array`) de una FFT radix-2 iterativa más Bluestein para `N` arbitrario, **límite blando `N ≤ 2¹⁶`** con aviso, hilo aparte y barra de progreso. El laboratorio **sigue funcionando** sin NumPy con funcionalidad reducida declarada en pantalla.
- El código del dominio **no importa NumPy directamente**: usa un pequeño **adaptador** (`signals/backend.py`) con una sola implementación activa por proceso y la misma API; las pruebas corren con las dos.
- Operaciones por bloques (`fft` por tramos del STFT) para acotar memoria.

### 24.4 Contraste entre vías (tolerancias)

| Operación | Criterio | Tolerancia |
|---|---|---|
| DFT/FFT (`N ≤ 4 096`) | `max\|X_rápida − X_exacta\| ≤ ε·max\|X_exacta\|` | `ε = 10⁻¹²` (error esperado `O(log₂N·u)`, `u = 1,1·10⁻¹⁶`) |
| `h[n]` de un FIR por ventanas | Igual | `10⁻¹²` |
| Respuesta en frecuencia en `F_p`, `F_a` | Valor exacto con `dtft_at` frente a la rejilla densa | `10⁻¹⁰` |
| Polos de IIR en SOS | `roots` flotante frente a `Decimal` con refinamiento | `10⁻⁹` |
| `N > 4 096` | Contraste en **puntos sembrados** (la exacta evalúa solo `dtft_at(k)`, `O(L)` por punto) | `10⁻¹⁰` |

### 24.5 Aleatoriedad sembrada

Ruido y procesos: `random.Random(semilla)` de la biblioteca estándar (reproducible entre plataformas para `random()`), con **Box-Muller** propio para la gaussiana (no se usa `gauss` de la biblioteca ni el generador de NumPy para evitar diferencias entre versiones). La vía exacta reutiliza `comms.simulation.uniform_stream` y `gaussian_stream` (ya existentes y deterministas en `Decimal`). La semilla es parte de la especificación de la señal (§5.1) y se muestra siempre.

### 24.6 Objetivos de rendimiento (medibles)

Líneas base que se **miden en SG-0** (el repositorio no tiene medida previa de `dsp/` en estos tamaños) y se fijan como objetivos con tolerancia; **no** se prometen números sin medir.

| Operación | Objetivo con NumPy | Sin NumPy |
|---|---|---|
| FFT de `2¹⁶` puntos | < 50 ms | < 3 s |
| FFT de `2²⁰` puntos | < 0,5 s | no disponible |
| Convolución de `10⁶` por `10³` muestras por FFT | < 1 s | no disponible |
| STFT 40 s a 44,1 kHz, `L = 1 024`, `R = 256` | < 2 s | con reducción (§14.5) |
| Lectura inversa (§8.5), cualquier entrada | < 50 ms | igual |
| Diseño FIR ventana, `L ≤ 2 001` | < 100 ms | < 1 s |
| Remez, `L ≤ 257` | < 1 s | < 20 s |
| Butterworth, Chebyshev, elíptico ≤ orden 65 en SOS | < 100 ms | < 1 s |
| Monte Carlo de LMS (1 000 realizaciones × 10 000 muestras) | < 5 s | con tope de realizaciones |
| Generación de 40 s de señal sintética | < 100 ms | < 2 s |
| DFT exacta `N = 512` (`Decimal`) | **a medir** | — |

Todo lo que pueda tardar se ejecuta en **segundo plano** con **cancelación** y **barra de progreso**, límite de recursos (tiempo, memoria, muestras) y mensaje claro al alcanzarlos.

### 24.7 Presupuestos

Tiempo máximo por tarea (30 s por defecto, configurable), memoria (`2²⁴` muestras `float64` ≈ 134 MB; para audio largo se usa `float32` o por bloques), longitud máxima por tipo (§5.3), nº máximo de realizaciones Monte Carlo (10⁴), nº de trazas por gráfica (16). Al superar el presupuesto, resultado `PARTIAL` o error seguro, nunca bloqueo de la interfaz.

---

## 25. Verificación independiente y sellos

Mismos tres sellos que `MATH_LAB.md` §8.1: **Verificado** (con el segundo camino entre paréntesis), **Solo numérico**, **Discrepa**. Si discrepa, el resultado **no se muestra como correcto**: se informa del fallo y se guarda el caso (`signals-case/1`: entrada, semilla, resultado propio, resultado del oráculo, versión del motor).

| Operación | Primer camino | Segundo camino independiente |
|---|---|---|
| Espectro de una sinusoide enventanada | FFT | Fórmula cerrada de Dirichlet (§8.1) y DFT directa `Decimal` si `N ≤ 512` |
| **Lectura inversa** | Procedimiento de §8.5 | **Modelo directo**: se sintetiza la señal con los parámetros hallados y se compara con las lecturas |
| Ventana: lóbulo, laterales, `Σw` | Medida con relleno de ceros | Fórmula cerrada (Anexo A) |
| Convolución | Directa | FFT con `N ≥ L₁ + L₂ − 1`; `Σy = Σx·Σh`; duración |
| Respuesta en frecuencia | Barrido denso | `dtft_at` exacta en puntos; `H(0) = Σh`; hermiticidad |
| Salida a sinusoide | Simulación y medida en régimen | `\|H(f₀)\|`, `∠H(f₀)` |
| Muestreo y aliasing | `alias_of` | DFT de la señal muestreada: pico en `k` esperado |
| Reconstrucción | Suma de sincs en malla | Atajo exacto en nodos de `dsp.reconstruct`; cota de cola |
| Modulación | Producto y FFT | TF teórica (`MATH_LAB`); `Parseval` |
| FDM: solapes | Comprobador de intervalos | Simulación con tonos sembrados + FFT |
| Diseño FIR/IIR | Algoritmo propio | `check` de plantilla en malla densa + oráculo SciPy (`firwin`, `remez`, `butter`, `cheby1`, `cheby2`, `ellip`) si está |
| Estabilidad | `roots(a)` | `iir_stability` de `dsp/` y `\|p\| < 1` en SOS; respuesta impulsional larga |
| Filtro adaptado | Salida | Cauchy-Schwarz (filtros aleatorios sembrados) y `y[0] = Σ s p` |
| Correlación | Directa o por FFT | `r(0) = E`, paridad, Schwarz |
| STFT | Trama a trama | Reconstrucción por solape y suma (identidad); una trama contra la DFT exacta |
| Cuantización | Medida | `6,02 b + 1,76 dB` |
| TRS (escenas) | Monte Carlo sembrado | Teoría de `MATH_LAB` con intervalo de confianza |

**Verificaciones cruzadas entre las dos vías (§24.4)** son parte del sello.

---

## 26. Explicación paso a paso

### 26.1 Fuente de verdad

Misma idea que `DIGITAL_DESIGN_LAB.md` §12: las explicaciones **salen de la traza de ejecución E0** del motor (`domain/execution/`, `application/explain_service.py`), **no de un modelo generativo**. Cada paso de una lección es un evento de la traza con su regla, entradas, salida y condición; la lección lo **renderiza** (`explain_render.py`) en lenguaje de clase.

### 26.2 Formato de cada paso

| Campo | Contenido |
|---|---|
| Regla | Nombre en castellano («primer cero de la ventana», «plegado de frecuencias») |
| Qué se hace | Expresión con valores sustituidos |
| **Por qué este método** | Motivo y por qué no otros (`MATH_LAB.md` §5.5b) |
| Condición o hipótesis | «Se asume `N ≥ L`», «sin aliasing: `f < f_m/2`» (§5.7 de aquel) |
| Resultado | Valor con unidad e intervalo de incertidumbre |
| Convenciones | dB, ventana, `N` frente a `L` |
| Resaltado | El elemento en la gráfica (pico, cero, lóbulo, región de solape, punto de ruptura) |

### 26.3 Niveles y modos

Tres niveles: **Resumen**, **Paso a paso** y **Detallado** (con justificación formal y comprobación de hipótesis). Navegación anterior, siguiente, reproducir; resaltado del trozo afectado en la figura. **Modo estudio** (predecir el siguiente paso) y **modo asistido** (el alumno propone el paso, el laboratorio le dice si sirve y por qué, con contraejemplo si no). Ejemplo de lectura inversa en tres líneas de resumen: *«Los picos en `k = 250` y `750` son una sola sinusoide (par `k`, `N − k`); `F₀ = 0,25`. El primer cero está a `Δk = 18`; `L = N/Δk ≈ 55`. El pico es 140 y `Σw = L`, luego `A = 2·140/55 = 5,1`.»* (valores ilustrativos).

### 26.4 Garantía de honestidad

La explicación nunca afirma lo que la traza no contiene; si el resultado es una estimación (interpolación de pico, Monte Carlo), la lección lo dice y da su error; si hay ambigüedad (`L ∈ {55, 56, 57}`), lo lista. El tutor socrático (`F12`), si se usa, **explica** la traza y **nunca califica**.

---

## 27. Audio, entrada y salida, formatos y persistencia

### 27.1 Entrada

| Formato | Soporte | Límites |
|---|---|---|
| **WAV PCM** (8, 16, 24, 32 bits) | Biblioteca estándar `wave` (sin dependencias nuevas) | Mono o estéreo (canal elegible o media); `f_m` entre 100 Hz y 384 kHz; ≤ 5 min (D13); cabecera validada (tamaño de datos coherente con el fichero) |
| WAV de coma flotante | **No** con `wave` (no lo admite): se avisa y se pide convertir; opcional con NumPy si el usuario lo pide | — |
| **MP3** y otros (los audios del curso: `dm_serie.mp3`) | Opcional por **QtMultimedia** (`QAudioDecoder`) o un decodificador externo opcional; si no está, mensaje claro «conviértelo a WAV» | Duración y tamaño acotados |
| CSV y texto numérico (`t,x` o `n,x`) | Lector propio con límites | ≤ 10⁷ filas |
| `.npy` | Con NumPy si está | Sin `pickle` |
| JSON `signals-lab/1` | Formato propio (Anexo C) | Profundidad y tamaño acotados |

Los valores se normalizan a `[−1, 1]` (PCM entero → `x/2^{b−1}`) y se conserva la referencia al **fichero y su SHA-256** (no el audio) para reproducir.

### 27.2 Salida

WAV de 16 bits (`wave`), CSV, PNG y SVG de gráficas, JSON del experimento, informe (§27.5), código MATLAB y Python equivalente (Anexo F).

### 27.3 Reproducción de audio

- **Puerto** `AudioOutput` en `application/` con una implementación en `infrastructure/audio.py` basada en **QtMultimedia** (`QAudioSink`); en pruebas, un puerto falso que registra lo que se «reproduciría». Si no hay dispositivo, el botón se desactiva con explicación.
- Semántica de `sound(x, f_m)`: recorte a `±1` con **aviso de saturación**; `sound([x, y], f_m)` reproduce original y filtrada en secuencia o en estéreo.
- **Seguridad auditiva**: **limitador de volumen** y atenuación por defecto, rampas de 10 ms de entrada y salida (sin clic), duración máxima de reproducción por defecto (30 s) y aviso antes de reproducir un barrido o una señal de gran amplitud.
- Usos: demostración de **aliasing** (barrido que rebota), **diezmado sin filtro**, `tecla.wav`, comparación de filtros IIR frente a FIR (P11-12), `dm_serie`.
- **Sonificación opcional** de gráficas para accesibilidad (§28.1).

### 27.4 Formato `signals-lab/1`

Esquema en el Anexo C: canónico (mismo contenido ⇒ mismos bytes ⇒ mismo *digest*), con `schema`, `engine_version`, `seed`, `signals[]` (especificación y, opcionalmente, muestras), `systems[]`, `filters[]`, `experiments[]`, `readings[]`, `results[]` con sello. Reutiliza `DspDocument` (`create`, `dumps`, `loads`, `compare`, `replay`) de `dsp/report.py` como base. El lector rechaza esquemas desconocidos con mensaje seguro.

### 27.5 Informe de práctica

Plantilla de la guía: **título, autores, grupo, fecha, subtítulo por apartado, resultados con gráficos y breve comentario con los parámetros utilizados, conclusiones**. Salida en **PDF** (Qt `QTextDocument` + `QPdfWriter`, sin dependencias nuevas) y **Markdown**; el comentario lo escribe el alumno (el laboratorio rellena los parámetros y las figuras, **no redacta conclusiones**). Incluye la tabla de **código generado** y las semillas. El nombre del fichero sigue la nomenclatura de la guía (`nc_…`).

### 27.6 Persistencia

Los experimentos se guardan **dentro de los proyectos de ingeniería existentes** (como circuitos y diseños digitales), con **versionado ligero** (historial con nota), **autoguardado y recuperación**, duplicar, renombrar y **comparar dos versiones** (diferencias en parámetros y resultados). La **repetición** (`replay`) recalcula un documento y compara el *digest*.

---

## 28. Accesibilidad, localización y seguridad

### 28.1 Accesibilidad

| Requisito | Cómo |
|---|---|
| **Solo teclado** | Todos los visores: foco con flechas (cursor), `+`/`−`/`0` (zoom), `Tab` entre trazas, `Intro` para fijar un marcador, atajos para reproducir y pausar animaciones |
| **Nombres accesibles** | Como `WaveformWidget` (`setAccessibleName`, `setAccessibleDescription`): «Espectro de módulo de la DFT de 30 puntos», con descripción de qué muestra |
| **Descripción textual y tabla** | Cada gráfica genera su resumen (picos, ceros, rangos) y una **tabla de valores navegable** (§19.7) |
| **Color no único** | Trazas con patrón y etiqueta; mapa del espectrograma con alternativa de grises y alto contraste |
| **Sonificación** (extra, D23) | Opción de convertir una curva (espectro, respuesta) en un tono de altura variable |
| **Reducción de movimiento** | Respeta el ajuste del sistema (`motion` ya existe); las animaciones se sustituyen por pasos manuales |
| **Tamaños** | Fuentes escalables; áreas de clic suficientes |
| **Texto real** | Pasos y resultados son texto seleccionable, no imagen |
| **Audio** | Nada depende solo del sonido; todo lo que se oye también se ve |

### 28.2 Localización

Toda la interfaz en **español**, con claves centralizadas y términos consistentes (*lóbulo principal, lóbulo lateral, ventana, muestreo, diezmado, respuesta impulsional, plano z, polos y ceros, plantilla, banda de paso, banda atenuada, retardo de grupo, relleno de ceros*). **Glosario ES/CA** en los ids de examen y en el panel de convenciones (por ejemplo *sinc*, *finestra*, *enfinestrament*, *mostratge*, *pols*, *filtre*), porque el material fuente está en catalán; D17 (decidido) fija español con glosario ES/CA; no se implementa interfaz catalana en este laboratorio, y si la aplicación la adopta globalmente (D12 de `DIGITAL_DESIGN_LAB.md`), las claves centralizadas la permiten sin tocar la lógica. Números con la configuración regional en la **presentación**, nunca en el guardado. Preparado para inglés sin tocar la lógica. Prueba automática que busca literales en inglés en las etiquetas.

### 28.3 Seguridad y privacidad

| Riesgo | Medida |
|---|---|
| **Ficheros de audio y datos hostiles** | Validación de cabecera (WAV), tope de tamaño y de duración, rechazo de formatos desconocidos con mensaje seguro (conversor único `to_ui_error`), **sin ejecutar** nada; sin `eval` ni `pickle` |
| Expresiones de usuario (generador, ejercicios) | Analizador propio con límites de longitud, profundidad y nodos; sin `eval` (misma regla que el laboratorio digital) |
| Denegación de servicio (FFT enorme, STFT gigante, Monte Carlo largo) | Presupuestos y cancelación (§24.7) |
| Exportación | Nombres saneados; nunca se sobrescribe sin confirmar |
| **Privacidad del audio** | El audio **nunca sale del equipo**; no se envía a servicios; el audio del curso (`dm_serie.mp3`, `tecla.wav`) **no se copia al repositorio**; el tutor no recibe el contenido del audio |
| Oráculos (SciPy, NumPy) | Se importan como bibliotecas locales; nada de red |
| Telemetría | Ninguna sobre el contenido de señales |
| Volumen | Limitador y avisos (§27.3) |
| Material del usuario | Solo lectura; la ruta configurable (`SST_MATERIAL_DIR`) se trata como dato |

---

## 29. Plan de pruebas y criterios de aceptación

### 29.1 Estrategia

Se sigue la convención del repositorio: pruebas por fase (`tests/test_sg0_….py`, nombrado análogo a `test_f8p2_dsp.py`), **de dominio sin Qt** siempre que sea posible; la parte de UI con `pytest-qt` en modo offscreen es lenta (la suite de UI actual tarda minutos), de modo que se escriben **pocas pruebas de UI dirigidas**. Las pruebas existentes (`test_f8p2_dsp.py`, `test_f8p4_comms.py`, `test_f8q5_logic_analyzer.py`) **no cambian de resultado**.

| Nivel | Qué se prueba |
|---|---|
| **Unitarias de dominio** | Biblioteca de señales, ventanas (fórmulas cerradas), espectro, modelo directo, lectura inversa, convención `f/F/k`, muestreo, modulación, comprobador módulo 1, diseño FIR/IIR, `check` de plantilla, Remez, multirate, cuantización |
| **Propiedades con semilla** | §29.2 |
| **Doradas** | Casos ES-01 a ES-40 y Anexo G, con valores fijados; cualquier cambio exige justificarlo |
| **Dos vías** | Rápida frente a exacta en `N ≤ 4 096` y en puntos sembrados (§24.4) |
| **Oráculos** | NumPy, SciPy, SymPy si están; si no, la prueba se **omite con motivo visible**, nunca pasa en silencio |
| **Sin NumPy** | Toda la suite de dominio corre con el adaptador de Python puro (con límites reducidos) |
| **Integración con `MATH_LAB`** | Contrato `ExactResult` ↔ `NumericResult` con casos de SS-10, SS-2, SS-5 |
| **Prácticas** | Cada práctica reproduce sus valores de referencia; el código MATLAB y Python generado se contrasta con NumPy |
| **UI** | Gestos del cursor y zoom, animación de la convolución, pestañas, resaltado de pasos, nombres accesibles, exportaciones |
| **Seguridad** | WAV truncado o con cabecera falsa, CSV gigante, JSON profundo, expresión enorme, FFT de `2³⁰`: error seguro sin colgarse ni consumir memoria sin límite |
| **Accesibilidad** | Todo el flujo principal con teclado; descripciones no vacías; contraste |
| **Rendimiento** | Pruebas de tiempo con tolerancia (marcadas para no fallar en máquinas lentas) |
| **Localización** | Búsqueda automática de literales en inglés |

### 29.2 Propiedades con semilla (lista cerrada)

1. `ifft(fft(x)) = x` y `fft` rápida `=` exacta para `N ≤ 4 096`.
2. Parseval: `Σ\|x\|² = (1/N) Σ\|X\|²`; hermiticidad de `X` si `x` es real.
3. Teorema de convolución: lineal `=` circular con `N ≥ L₁ + L₂ − 1`; aliasing temporal si `N` menor y el error cae exactamente en las primeras `L₁ + L₂ − 1 − N` muestras.
4. Periodicidad `X(F + 1) = X(F)` y `H(F) = H*(1 − F)` para `h` real.
5. `alias_of(f, f_m) = alias_of(f + k f_m, f_m)` y `alias_of ∈ [0, f_m/2]`.
6. Modelo directo de sinusoide enventanada: fórmula cerrada `=` FFT con `N ≥ L`.
7. **Ida y vuelta de la lectura inversa**: para parámetros sembrados `(A, F₀, L, ventana, N)`, la lectura inversa del espectro generado **contiene** los parámetros originales en sus intervalos y reproduce los picos con error `< 10⁻⁶`.
8. `Σw`, primer cero y lateral de cada ventana coinciden con su fórmula.
9. FIR simétrico ⇒ fase lineal y retardo de grupo `M`; ceros con simetría cuadrantal.
10. Filtro inverso del eco: la cascada con el eco es la identidad (hasta el retardo `n₀`).
11. Comprobador de solapes módulo 1 `=` simulación por fuerza bruta (tonos y FFT).
12. `check` de plantilla `=` barrido denso independiente.
13. Remez: la solución tiene al menos `r + 1` extremos alternos con igual magnitud de error (condición de equirrizado) dentro de `10⁻⁴`.
14. La bilineal conserva la estabilidad: polos analógicos en el semiplano izquierdo ⇒ `\|p\| < 1`.
15. SOS en cascada `=` forma directa en la respuesta (`10⁻⁹`) para órdenes ≤ 20 y estable donde la directa no lo es (orden 65).
16. Remuestreo `L/M` conserva un tono; la forma polifásica `=` la directa.
17. STFT con ventana que cumple COLA: la reconstrucción por solape y suma devuelve la señal.
18. SQNR medido `=` `6,02 b + 1,76` (`±0,3 dB`).
19. Correlación: `r_x` par, `r_x(0) = E`, `\|r_x(τ)\| ≤ r_x(0)`.
20. Procesos sembrados: misma semilla ⇒ mismas realizaciones; la media de conjunto converge a la teórica con `√N`.
21. Misma semilla, mismo ejercicio, mismos bytes y *digest* (determinismo).

### 29.3 Criterios de aceptación globales

1. **Cualquier ejercicio** del catálogo (§21.4) muestra **pasos, gráfica y sello de verificación** (con su convención declarada).
2. La **lectura inversa** (§8.5) resuelve ES-01 a ES-05 y ES-37 con intervalos y lista de ambigüedades, y su ida y vuelta (propiedad 7) pasa para 10⁴ casos sembrados.
3. Los cuatro casos de §8.3 (ES-06 a ES-09) y ES-10 reproducen los valores del informe de la P9.
4. Las prácticas **P2, P4, P5, P6, P9, P10, P11** se completan con el laboratorio y generan su informe con el formato de la guía.
5. Para la plantilla de P10 y P11 se obtienen los órdenes y longitudes de §12 y los filtros **cumplen** la plantilla con margen o se declara la violación.
6. Ninguna medida de la vía rápida se da por buena sin contraste con la exacta o con un oráculo (`Verificado`) o sin la marca `Solo numérico`.
7. Todo resultado es **determinista** y lleva **digest** reproducible (representación redondeada en la vía rápida).
8. Todo el flujo principal es operable **solo con teclado**; cada gráfica tiene descripción textual y tabla.
9. Toda la interfaz está en **español**; el glosario ES/CA está en los ids de examen.
10. Sin NumPy, el laboratorio **arranca y funciona** con funcionalidad reducida declarada.
11. El audio se **reproduce con limitador** y nunca sale del equipo.
12. Las pruebas existentes del proyecto **no cambian de resultado**; `dsp/` y `comms/` **no se modifican**.
13. Los datos de las erratas (§4.5) se detectan: ES-31 y ES-35 muestran la discrepancia con la solución oficial.
14. La suite de dominio nueva corre **sin Qt** y en menos de 60 s en una máquina de desarrollo estándar (objetivo; se mide en SG-0).

---

## 30. Fases de entrega

Cada fase es **entregable y demostrable por sí sola**, con pruebas y documentación, e **incluye las calculadoras de su bloque** (§20) completas y con pasos y verificación. Esfuerzo relativo (S ≈ días, M ≈ 1–2 semanas, L ≈ 3–5 semanas, XL > 5 semanas), orientativo.

| Fase | Contenido | Depende de | Esfuerzo |
|---|---|---|---|
| **SG-0** Cimientos | Paquete `signals/`, modelo de datos (§5), convenciones (§4), `Signal` con **origen arbitrario**, errores, **adaptador de backend** (`signals/backend.py`: NumPy opcional o Python puro, D2, §24.3; NumPy se añade a `requirements.txt` como recomendado), núcleo de gráficas mínimo (§19.1, D6: línea, `stem`, espectro, ejes `n/F/f/k`), **línea base de rendimiento** (§24.6), ruta `engineering/signals`, esqueleto de página, formato `signals-lab/1`. **Antes de crear ficheros se fija con CI-R de `CIRCUITS_LAB.md` dónde viven `dsp/` y `signals/`** (nota de §3.2) | CI-R (coordinación) | L |
| **SG-1** Biblioteca y generador | §6 completa, generador con aviso de aliasing, E/S de **WAV**, reproducción con limitador (§27.3), **P0** (verificador de dimensiones) y **P1** (audio); calculadoras C1, C3, C4, C21, C23; ES-40 (privado y opcional) | SG-0 | M |
| **SG-2** Espectros, ventanas y **lectura inversa** | §8 y §9: modelo directo, visor, lectura directa, **lectura inversa con intervalos y ambigüedades**, identificación de usuario, nota y dígito (§8.6), catálogo de ventanas medido (valores dorados), resolución; calculadoras C5, C6, C7; casos ES-01 a ES-10, ES-31, ES-32, ES-37 (ES-05 se cierra con la tabla de aliasing en SG-4). **Prioridad máxima** (SS-12 + SS-13, ≈ 14/29) | SG-0, SG-1 | L |
| **SG-3** DFT, DTFT y convolución digital | §8.7 (relleno de ceros, circular frente a lineal, retardo, modulación, hermiticidad), visor de DTFT, convolución digital con regímenes (§7.4); **P2, P4, P5** completas y **P9 apartados 1 a 29**; calculadoras C8, C9; ES-11, ES-24 a ES-26 | SG-2 | M |
| **SG-4** Muestreo y reconstrucción | §10: réplicas, aliasing, plegado, reconstrucción ideal, D/A real y compensador; calculadoras C2, C15; ES-05, ES-15, ES-21 | SG-2 | M |
| **SG-5** Sistemas LTI visualizados | §7 (salvo §7.4, en SG-3): verificador de propiedades, convolución analógica animada, respuesta en frecuencia y dB, plano z, eco e inverso; calculadoras C14, C25; ES-12 a ES-14, ES-18 a ES-20, ES-22, ES-23; simulacro **P7** (eco y periódica) | SG-1, SG-3; bloque 15 de `MATH_LAB` (§4.15) | L |
| **SG-6** Ejercicios y corrección v1 | Plantilla (§21.1), corrector (§21.2), pistas, modo estudio, **generador sembrado** de las familias de lectura inversa, ventana, aliasing, convolución, propiedades de sistemas, eco y respuesta en frecuencia; las demás familias de §21.4 se añaden en la fase de su bloque (FDM/TDM en SG-7, filtros en SG-8 y SG-9, TRS en SG-14); errores comunes; pruebas privadas de examen con ruta local; enlace con maestría | SG-2, SG-4, SG-5 | L |
| **SG-7** Modulación y multiplexación | §11: DSB, AM, SSB, FM, digitales (con `comms/`), FDM, TDM, **comprobador de solapes módulo 1**, demodulación; incluye el **núcleo mínimo `windowed_sinc`** de §12.3 (sinc truncada con ventana de §9, que SG-8 reutiliza) para la banda limitada de §11.4 y el Hilbert de SSB; **P6**; calculadoras C16, C17; ES-16, ES-17, ES-33, ES-39 | SG-4 | M |
| **SG-8** Filtros FIR | §12.1 a §12.5 (sin Remez): plantilla, tolerancias, ventanas, muestreo en frecuencia, ceros, comparación y filtrado de señales; **P10** (salvo apartados 5 y 6) y **P9 apartados 30 a 33**; calculadoras C10, C12; ES-27, ES-28, ES-38 | SG-3, SG-7 | M |
| **SG-9** Filtros IIR | §12.6 a §12.9: Butterworth, Chebyshev I y II, elíptico, bilineal con pre-distorsión, **`AnalogFilterPrototype`** (D8: se define aquí si `CI-AN-FILT` aún no lo ha hecho; si existe, se importa), **SOS**, aviso de inestabilidad numérica, comparación de familias, visor mínimo de coeficientes a `b` bits (D20); **P11** (salvo apartado 12); calculadoras C11, C13; ES-29, ES-30 | SG-8 | L |
| **SG-10** Parks-McClellan | Remez propio (§12.5, D5), búsqueda del orden mínimo; completa P9-34, P10-5, P10-6 y P11-12; extensión a paso alto, banda y rechazo de banda (§12.10) | SG-8, SG-9 | M |
| **SG-11** Filtro adaptado y correlación | §13; calculadora C20; ES-34 a ES-36 | SG-5 | M |
| **SG-12** STFT y espectrogramas | §14, PSD estimada de procesos (§14.4), estimación AR por Yule-Walker (D21); rendimiento con NumPy y reducción sin él | SG-2 | M |
| **SG-13** Multirate | §15; calculadora C19; el filtro del polifásico usa §12 (Kaiser; Parks-McClellan si SG-10 ya está) | SG-9 | S |
| **SG-14** Visores de TRS | §17 completo; calculadora C22 en colaboración con `MATH_LAB` | **bloque 16 de `MATH_LAB`** (§4.16), SG-11, SG-12 | L |
| **SG-15** Cuantización y A/D | §16 (D18); submuestreo de paso banda, tardío y opcional (§10.7, D19); calculadora C18 | SG-4 | S |
| **SG-16** Informes y equivalencias | Informes de práctica en PDF y Markdown (§27.5), **código MATLAB y Python equivalente** (Anexo F), modo examen, calculadora C24, exportaciones | SG-3, SG-7, SG-8, SG-9 | M |
| **SG-17** Pulido y certificación | Accesibilidad completa y sonificación (D23), rendimiento, seguridad (WAV hostiles), localización (ES y glosario ES/CA, D17), documentación de usuario, certificación | Todas | M |

**Orden recomendado:** SG-0 → SG-1 → **SG-2** → SG-3 → SG-4 → SG-5 → SG-6 → SG-7 → SG-8 → SG-9 → SG-11 → SG-12 → SG-10 → SG-13 → SG-16 → SG-14 → SG-15 → SG-17.
Razón: primero lo que **más rinde en examen** (lectura de espectros, muestreo, sistemas: los bloques P1 de `extra_senales.md`) y es **puramente de dominio**; los ejercicios en cuanto hay tres bloques que generar; modulación (P2); los filtros se retrasan porque pesan poco en el examen (≈ 3/29 y 1/29) aunque las prácticas P10 y P11 los exigen; Parks-McClellan tras los filtros IIR por ser el algoritmo más costoso; TRS cuando `MATH_LAB` entregue sus bloques. **Cada fase se cierra cuando resuelve sus casos ES con pasos, gráfica y verificación.**

---

## 31. Riesgos y límites declarados

### 31.1 Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Alcance enorme** (es un laboratorio de señales completo) | Alto | Fases entregables, orden por valor de examen, límites declarados |
| **Las figuras de los enunciados no se pueden leer** | Alto | La figura es **dato** con lecturas tecleadas (§8.8); gráfica generada como comprobación; reevaluación futura solo local (D12) |
| **`Decimal` es lento** y `dsp/` tiene topes (4 096) | Alto | Dos vías con contraste (§24); la exacta solo para soluciones |
| **NumPy no está en los requisitos** | Medio | Opcional con adaptador y Python puro como respaldo; funcionalidad reducida declarada (D2) |
| **Divergencia de convenciones** (dB, ventana, `N` frente a `L`) | Alto | Cada ejercicio las declara; avisos T1 a T11; calculadoras con selector |
| **Erratas en soluciones oficiales** | Medio | Verificación por segundo camino; casos ES-31 y ES-35; se señala la discrepancia |
| **Lectura inversa ambigua** | Medio | Intervalos y lista de ambigüedades; nunca se presenta un valor único si no lo es |
| **Coordinación con `MATH_LAB.md` v2 y `CIRCUITS_LAB.md`** (ya redactados; pueden renumerarse, y el renombrado CI-R mueve rutas) | Medio | Referencias por **nombre y número verificado** (2026-10-01); contratos de §23; D8 evita duplicar el prototipo; revisión de numeración antes de implementar |
| **Remez** no converge en casos extremos | Medio | Rejilla densa, límites, mensaje claro, oráculo SciPy; no se afirma lo que no converge |
| **IIR de alto orden en `(b, a)`** inestable | Medio | SOS por defecto y aviso didáctico (§12.6) |
| **Funciones elípticas** (Cauer) numéricamente delicadas | Medio | AGM y descenso de Landen; contraste con `ellipord`/`ellip` de SciPy si está |
| **Audio**: dispositivo de salida, QtMultimedia en Windows, MP3 | Medio | Puerto con respaldo; WAV siempre; MP3 opcional con mensaje; pruebas con puerto falso |
| **Datos del curso no están en el repositorio** (audios, enunciados) | Medio | Pruebas privadas con ruta local; los públicos son problemas propios |
| **TRS sin datos de examen** | Medio | Prioridad por horas de la guía; revisar si el usuario aporta exámenes |
| **Solapes** con `DIGITAL_DESIGN_LAB.md` §22.6 y `CIRCUITS_LAB.md` | Medio | Tabla de frontera (§23.4, §23.5); objetos compartidos (`FilterDesign`, `AnalogFilterPrototype`) |
| **Rendimiento del dibujo** de gráficas grandes | Medio | Envolvente mín/máx, imagen precalculada, `layout_*` puro medible, hilo aparte |
| **Pruebas de UI lentas** | Medio | Lógica en dominio testeable sin Qt; pocas pruebas de UI |
| **Determinismo en coma flotante** entre plataformas | Medio | *Digest* sobre representación redondeada; contraste con la vía exacta |
| **Derechos de autor** del material de la universidad | Medio | Nada se copia al repositorio; solo paráfrasis y valores calculados |

### 31.2 Límites declarados al usuario

- La lectura de una gráfica de examen **no es automática**: el alumno teclea las lecturas.
- La **lectura inversa** da hipótesis con intervalos, no certezas, cuando los datos son insuficientes.
- La vía rápida es **numérica**: «Verificado» significa contrastado con la exacta o con un oráculo, no demostrado.
- Un filtro que **no cumple** la plantilla se muestra como tal; el laboratorio no «arregla» los datos.
- Parks-McClellan y los filtros elípticos son numéricos y se **contrastan**, no se demuestran.
- No se ejecuta **código MATLAB ni Python** del alumno; se genera el equivalente.
- El audio solo se **reproduce** en el equipo y con volumen limitado.
- La **matemática exacta** (TF, series, transformada z, detección, estimación…) la hace `MATH_LAB`; este documento no la reimplementa.
- Para TRS no hay frecuencia de examen medida.
- P3 y P8 no tienen material; P7 solo parcialmente legible.

---

## 32. Decisiones D1 a D24 (todas decididas)

El usuario **aprobó todas las decisiones con la recomendación** que figuraba en la tabla; cada una está propagada a las secciones que se indican. Ninguna queda abierta.

| # | Decisión | Opciones | Estado y resolución | Se aplica en |
|---|---|---|---|---|
| D1 | Reparto matemática frente a laboratorio | `MATH_LAB` / este / mixto | ✅ **DECIDIDO por el usuario:** la matemática pura de señales va a `MATH_LAB.md`; aquí todo lo demás | §3.1, §23.1 |
| D2 | NumPy | Requisito / opcional con respaldo / no usar | ✅ **DECIDIDO: opcional con adaptador** (`signals/backend.py`) y respaldo en Python puro; se añade a `requirements.txt` como **recomendado**, no obligatorio (coherente con D1 de `MATH_LAB.md`) | §24.3, §29.1, SG-0 |
| D3 | SciPy y SymPy como oráculos | Sí / No | ✅ **DECIDIDO: sí, opcionales** y solo como comprobadoras (`signal.firwin/remez/butter/cheby1/cheby2/ellip/freqz/spectrogram/welch`; `sympy` para DTFT cerradas); si faltan, «no contrastada con librería externa» | §25, §12.12, §29.1 |
| D4 | Vía exacta y vía rápida | Dos vías con contraste / solo exacta / solo rápida | ✅ **DECIDIDO: dos vías con contraste**: la exacta explica, la rápida muestra | §24, §25 |
| D5 | **Parks-McClellan** | Sí / No / Delegar a SciPy | ✅ **DECIDIDO: procede, propio, en SG-10**, contrastado con `scipy.signal.remez` si está (lo piden P9-34, P10-5 y 6, P11-12) | §12.5, SG-10 |
| D6 | Núcleo de gráficas | Propio compartido / `pyqtgraph` / `matplotlib` | ✅ **DECIDIDO: propio** (`QPainter`, `QImage`, `layout_*` puro), **compartido** con `MATH_LAB` §6 y las gráficas de `CIRCUITS_LAB` §8.9; solo se adopta una librería si la medición de SG-0 no alcanza §19.5 | §19.1, §19.6, SG-0 |
| D7 | dB por defecto | Amplitud / potencia | ✅ **DECIDIDO: amplitud `20 log₁₀\|H\|`** con selector visible y declaración obligatoria en cada ejercicio (T1) | §4.1 C9, §4.4, C4 |
| D8 | Prototipo analógico `AnalogFilterPrototype` | Este / `CIRCUITS_LAB` / el primero que se construya | ✅ **DECIDIDO: el primero que se construya** lo define y el otro lo importa; una sola función de orden mínimo | §12.11, §23.4, SG-9 |
| D9 | ¿Ejecutar código MATLAB o Python del alumno? | Sí / No | ✅ **DECIDIDO: no** (seguridad y alcance): se genera el código equivalente (Anexo F) y se verifica contra NumPy | §18, §28.3, SG-16 |
| D10 | Uso de exámenes reales | En el repositorio / privado con ruta local | ✅ **DECIDIDO: privado con ruta local** (hereda D5 de `MATH_LAB.md`); paráfrasis y valores calculados en el repositorio | §22.1 |
| D11 | Realización por defecto de un IIR | Forma directa / SOS | ✅ **DECIDIDO: SOS**, con aviso didáctico de la forma directa | §12.6, §12.8 |
| D12 | Leer gráficas de examen por imagen | Sí (visión) / No | ✅ **DECIDIDO: no en las fases SG**; lecturas tecleadas. Reevaluar solo tras DL-11 del laboratorio digital (**dependencia: DL-11**; DL-11 entrega el pipeline `infrastructure/vision.py`) (OpenCV y Ollama locales), con revisión humana | §8.5, §8.8, §31.2 |
| D13 | Topes de tamaño | Valores | ✅ **DECIDIDO:** `2²⁴` muestras (≈ 6 min a 44,1 kHz), audio ≤ 5 min por defecto, `10⁴` realizaciones de Monte Carlo; configurables | §5.3, §24.2, §24.7, §27.1 |
| D14 | Cadena de bloques | Lineal con derivaciones / editor libre de grafos | ✅ **DECIDIDO: lineal con derivaciones**; el diagrama de solo lectura reutiliza el núcleo de lienzo compartido si ya existe | §7.8, §23.4 |
| D15 | Ventana por defecto | Simétrica / periódica | ✅ **DECIDIDO: simétrica** (`hann(L)` de MATLAB y del curso), casilla «periódica» y aviso (T5); la triangular del curso es `p_M*p_M/M` | §4.4 T5, T6, §9.2 |
| D16 | Reproducción de audio y MP3 | QtMultimedia / librería externa | ✅ **DECIDIDO: QtMultimedia** (ya instalado con PySide6_Addons); MP3 por `QAudioDecoder` opcional; WAV siempre | §27.1, §27.3 |
| D17 | Idioma | Solo ES / ES con glosario CA / interfaz CA | ✅ **DECIDIDO: ES con glosario ES/CA** en ids y convenciones; sin interfaz catalana en este laboratorio | §28.2, Anexo E |
| D18 | Cuantización y A/D (SS-18) | Fuera / pequeña | ✅ **DECIDIDO: pequeña y tardía (SG-15)**: visor y SQNR | §16, SG-15 |
| D19 | Submuestreo de paso banda | Sí / No | ✅ **DECIDIDO: sí, tardío y opcional** (en SG-15) | §10.7, SG-15 |
| D20 | Cuantización de coeficientes de filtros | Aquí / `DIGITAL_DESIGN_LAB` DL-20 | ✅ **DECIDIDO: en DL-20** de `DIGITAL_DESIGN_LAB.md` §22.10 (coma fija; esta fase depende de SG-9); aquí solo el visor mínimo de coeficientes a `b` bits (en SG-9) | §12.8, §23.5, SG-9 |
| D21 | Estimación espectral paramétrica (AR por Yule-Walker) | Sí / No | ✅ **DECIDIDO: sí, extra tardío en SG-12** | §14.1, SG-12 |
| D22 | **P3 y P8** (sin material) | Esperar / suponer | ✅ **DECIDIDO: reservadas**; se piden los enunciados al usuario, no se inventan | §18.2 |
| D23 | Sonificación de gráficas | Sí / No | ✅ **DECIDIDO: sí, pequeña, en SG-17** | §28.1, SG-17 |
| D24 | Orden de modulaciones | Todas a la vez / por frecuencia de examen | ✅ **DECIDIDO: por frecuencia de examen** (DSB, FDM, TDM y digital `cos(2πFn)` primero; AM, SSB y FM después, dentro de SG-7) | §11, SG-7 |

---

## 33. Lo que no se había pedido pero se incluye o se propone

1. **Intervalos de incertidumbre y lista de ambigüedades** en la lectura inversa, con verificación por modelo directo.
2. **Demostrador resolución frente a fuga** (§9.4) y **asistente de ventana** (§9.5).
3. **Verificador de dimensiones** de P0 y **tabla de comparación** de P9 autogenerada.
4. **Generación de código MATLAB y Python** equivalente para cada práctica (Anexo F), sin ejecutar código del alumno.
5. **Informe de práctica** con la plantilla de la guía (PDF y Markdown).
6. **Avisos de las trampas de examen** (T1 a T11) y detección de erratas (ES-31, ES-35).
7. **Planificador FDM/TDM** y **comprobador de solapes módulo 1** compartido por muestreo, generador y multiplexación.
8. **Filtros: asistente de relajación** de la plantilla cuando el orden es excesivo (la guía de P11 lo sugiere) y **demostración de la inestabilidad numérica** de la forma directa frente a SOS.
9. **Animaciones** de convolución, de `f_m` y de `F` sobre el círculo de `H(z)`.
10. **Demostración auditiva** de aliasing y de diezmado sin filtro.
11. **Estimador de duración efectiva** de una respuesta impulsional y comparación de familias con modelo de coste determinista.
12. **Multirate y polifásico**, con cálculo de conversión 44,1 a 48 kHz.
13. **STFT y espectrograma** con alto contraste, grises y descripción textual.
14. **Estimación AR por Yule-Walker** (D21) y **submuestreo de paso banda** (D19).
15. **Escenas de TRS** con contraste Monte Carlo frente a teoría exacta y banner de discrepancia.
16. **Corrección por propiedad** de filtros (plantilla, orden, estabilidad) y por **eventos** de gráficas dibujadas.
17. **Catálogo de errores comunes** con diagnóstico y enlace a la trampa.
18. **Integración con el laboratorio virtual**: llevar la salida de un circuito al espectro (`waveform_to_signal`) y viceversa.
19. **Sonificación** de gráficas y modo alto contraste.
20. **Prueba opcional** contra el material local del usuario, con ruta configurable.
21. **Modo examen** (tiempo y puntuación) y **modo asistido** de la lectura inversa.
22. **Reutilización y frontera explícita** con `comms/`, `ac/bode.py`, `DIGITAL_DESIGN_LAB.md` y `CIRCUITS_LAB.md`.

---

## Anexo A — Ventanas: fórmulas de `W(F)`

Notación: `P_L(F) = Σ_{n=0}^{L−1} e^{−j2πFn} = [sin(πLF)/sin(πF)] · e^{−jπ(L−1)F}` es la TF de `p_L[n]` (ventana rectangular causal). `D_L(F) = sin(πLF)/sin(πF)` es el núcleo de Dirichlet (real). Todas las ventanas de la familia coseno se escriben como combinación de `P_L` desplazados (la fase se arrastra con ellos, por eso se define con `P_L` y no con `D_L`).

| Ventana (causal, `n = 0..L−1`) | `w[n]` | `W(F)` exacta |
|---|---|---|
| Rectangular | `1` | `P_L(F)` |
| Triangular del curso `p_M * p_M / M`, `L = 2M−1` | `min(n+1, L−n)/M` | `P_M(F)²/M` |
| Hann **periódica** | `½ − ½cos(2πn/L)` | `½P_L(F) − ¼[P_L(F − 1/L) + P_L(F + 1/L)]` |
| Hamming **periódica** | `0,54 − 0,46cos(2πn/L)` | `0,54P_L(F) − 0,23[P_L(F − 1/L) + P_L(F + 1/L)]` |
| Blackman **periódica** | `0,42 − 0,5cos(2πn/L) + 0,08cos(4πn/L)` | `0,42P_L − 0,25[P_L(F ∓ 1/L)] + 0,04[P_L(F ∓ 2/L)]` (suma de los dos signos) |
| Variante **simétrica** (`L−1` en el denominador) | igual con `2πn/(L−1)` | Mismo desarrollo con desplazamientos `±1/(L−1)` y `P_L`; el primer cero exacto del lóbulo principal y `Σw` cambian ligeramente (T5) |

**Propiedades usadas por la lectura inversa**: `W(0) = Σw`; ceros de la rectangular en `k/L`; ceros de la triangular en `k/M`; la **Hann periódica** tiene ceros en `±2/L, ±3/L, …` (el cero de `±1/L` queda cancelado por los términos desplazados); ENBW `= LΣw²/(Σw)²` bins; pérdida por escalonamiento `= 20 log₁₀(\|W(½Δk)\|/W(0))`, con `Δk = 1/N` en `F`.

**Estimadores** de longitud de FIR por ventanas (transición `ΔF` en `F = f/f_m`): rectangular `0,9/ΔF`, Hann `3,1/ΔF`, Hamming `3,3/ΔF`, Blackman `5,5/ΔF`, Kaiser `(A − 7,95)/(14,36 ΔF)`; atenuación en la banda atenuada: rectangular ≈ 21 dB, Hann ≈ 44 dB, Hamming ≈ 53 dB, Blackman ≈ 74 dB.

## Anexo B — Referencia rápida de fórmulas de lectura y resolución

| Pregunta | Fórmula | Condición |
|---|---|---|
| Frecuencia de un pico en `k` | `f = k f_m/N`, `F = k/N`; `k > N/2 ⇒ f = (k−N) f_m/N` | `N`, `f_m` conocidos |
| Intervalo de `F₀` por lectura de bin | `[(k−½)/N, (k+½)/N]` | Sin refinar |
| Amplitud | `A = 2\|X\|_pico/Σw` | Pico lejos de `0` y `½` |
| Rectangular: `L` por el `m`-ésimo cero | `L = m N/Δk_m` | Un solo tono cerca |
| Triangular: `M` por el primer cero | `M = N/Δk`, `L = 2M − 1` | |
| Hann: `L` por el primer cero | `L = 2N/Δk` | Periódica; simétrica varía en ±1 |
| Ventana por razón principal/lateral | `20 log₁₀(P/S)`: 13,3 rect; 26,5 tri; 31,5 Hann; 42,5 Hamming; 58,1 Blackman | Tolerancia ±1 dB |
| Resolución (lóbulos principales sin solape) | `\|F₁ − F₂\| ≥ 2/L` rect; `4/L` tri, Hann, Hamming; `6/L` Blackman | Criterio de examen |
| Criterio de Rayleigh (cero del vecino) | `\|F₁ − F₂\| ≥ 1/L` rect | Criterio más permisivo |
| Escalonamiento máximo | `20 log₁₀\|sinc(½)\| = −3,92 dB` rect (`N = L`) | Pico a mitad de bin |
| Pico de `X(F)` rectangular | `A L/2` | Lejos de `0` y `½` |
| `N` mínimo de la convolución circular | `N ≥ L₁ + L₂ − 1` | |
| `f_m` mínima sin aliasing | `f_m ≥ 2 B_max` (estricta para sinusoides puras) | Tras modulación o sistema |
| Frecuencia aparente | `f_a = \|f − round(f/f_m) f_m\|` | `alias_of` |
| Tolerancias | `δ_p = (10^{α_p/20}−1)/(10^{α_p/20}+1)`, `δ_a = (1+δ_p)10^{−α_a/20}` | Amplitud |
| Orden Butterworth | `⌈log[(10^{α_a/10}−1)/(10^{α_p/10}−1)]/(2 log(Ω_a/Ω_p))⌉` | `Ω = tan(πF)` |
| Longitud Kaiser (FIR) | `(A − 7,95)/(14,36ΔF)` | `A = −20 log₁₀ δ_a` |
| Longitud equirrizado (Herrmann) | `(−20 log₁₀√(δ_pδ_a) − 13)/(14,6ΔF)` | Estimador |
| Compensación del D/A | ZOH `1/sinc(f/f_m)`; triángulo `1/sinc²(f/f_m)` | `T = 1/f_m` |
| SQNR | `6,02 b + 1,76 dB` | Sinusoide a plena escala |
| Eco: módulo de ceros/polos | `\|a\|^{1/L}` | `H = 1 ± a z^{−L}` |

## Anexo C — Formato `signals-lab/1`

Extensión de `dsp-report` (`DspDocument`): canónico (mismas claves ordenadas, mismos bytes, mismo *digest*), versión de motor `sg/1`.

```json
{
  "schema": "signals-lab/1",
  "engine_version": "sg/1",
  "meta": {"autor": "", "asignatura": "SST", "practica": "P9", "creado": "", "notas": ""},
  "seed": 20260930,
  "conventions": {"db_of": "amplitude", "window_symmetric": true, "spectrum": "bilateral"},
  "signals": {
    "x1": {"kind": "DIGITAL", "spec": "sine(A=4,f=2000,fm=8000,L=30)", "axis": {"origin": 0, "count": 30},
           "fm": "8000", "samples": null, "digest": "sha256:..."}
  },
  "systems": {"h1": {"kind": "FIR", "b": ["0.25", "0.5", "0.25"], "a": ["1"]}},
  "filters": {"f1": {"family": "FIR-WINDOW", "spec": {"fm": "16000", "fp": "3600", "fa": "4000", "ap_db": "1", "aa_db": "40"},
                      "window": "hamming", "L": 131, "check": {"status": "PASS", "margin_db": "9.7"}}},
  "readings": [{"N": 30, "peaks": [{"k": 7, "value": "38.267"}, {"k": 8, "value": "38.267"}], "nulls": []}],
  "experiments": [{"id": "P9-1", "chain": ["x1", "dft(N=30)"], "results": ["r1"]}],
  "results": {"r1": {"value": "...", "seal": "VERIFIED", "second_path": "dirichlet-closed-form", "path": "fast"}}
}
```

Reglas: identificadores validados por expresión regular; límites de tamaño y profundidad; **no** se guardan muestras de audio por defecto (solo la especificación o el *hash* del fichero); orden canónico al serializar; lector que rechaza esquemas desconocidos con mensaje seguro; los números de la vía rápida se redondean a 12 cifras significativas en el *digest*.

## Anexo D — Mapa de módulos y responsabilidades

| Módulo | Responsabilidad | Capa | Estado |
|---|---|---|---|
| `signals/model.py`, `conv.py` | Tipos y convenciones | dominio | nuevo |
| `signals/library.py`, `generator.py` | Biblioteca y generador | dominio | nuevo |
| `signals/windows.py`, `resolution.py` | Ventanas y resolución | dominio | nuevo |
| `signals/spectrum.py`, `spectral_model.py`, `spectral_read.py` | Espectro, modelo directo, lectura inversa | dominio | nuevo |
| `signals/lti.py`, `conv_view.py` | Sistemas, convolución con eje | dominio | nuevo |
| `signals/sampling.py` | Muestreo, aliasing, D/A real | dominio | nuevo (usa `dsp/sampling.py`) |
| `signals/modulation.py` | Modulación y multiplexación | dominio | nuevo (usa `comms/`) |
| `signals/fir_design.py`, `iir_design.py`, `template.py` | Diseño de filtros y plantilla | dominio | nuevo (usa `dsp/filters.py`) |
| `signals/matched.py`, `stft.py`, `multirate.py`, `quantize.py`, `process.py` | Adaptado, STFT, multirate, cuantización, TRS | dominio | nuevo |
| `signals/backend.py`, `exact.py`, `verify.py`, `errors.py` | Vías numéricas, verificación, errores | dominio | nuevo |
| `dsp/*`, `comms/*` | Motor exacto y comunicaciones | dominio | **existe, no se toca** |
| `application/signals_lab.py` | Fachada | aplicación | nuevo |
| `application/signals_exercises.py`, `signals_practices.py` | Ejercicios y prácticas | aplicación | nuevo |
| `application/signals_audio.py`, `signals_export.py`, `signals_explain.py` | Audio, exportación, lecciones | aplicación | nuevo |
| `infrastructure/audio.py`, `oracles.py` | Reproducción y oráculos opcionales | infraestructura | nuevo, opcional |
| `ui/signals_page.py`, `ui/plot/*`, `ui/signals_*_view.py` | Página, gráficas, pestañas | UI | nuevo |
| `ui/waveform.py` | Patrón `layout_*` + widget (solo H/L digital) | UI | existe; el patrón se reutiliza |
| `ui/routes.py`, `ui/modules.py` | Ruta `engineering/signals`, índice | UI | se amplían |

## Anexo E — Glosario (ES / CA)

**Aliasing / solapamiento (CA: *aliasing*, *solapament freqüencial*)**: replicación de componentes de frecuencia por encima de `f_m/2`. **Antialiasing**: filtro previo. **Banda de paso / atenuada (*banda de pas / atenuada*)**. **Convolución (*convolució*)**. **Diezmado (*decimació*)**. **Enventanado (*enfinestrament*)**. **Escalonamiento (*scalloping*)**: pérdida de amplitud por pico entre bins. **Filtro adaptado (*filtre adaptat*)**. **Fuga (*fuita espectral*)**. **Lóbulo principal / lateral (*lòbul principal / lateral*)**. **Muestreo (*mostratge*)**. **Plantilla (*plantilla d'especificacions*)**. **Relleno de ceros (*zero-padding*)**. **Resolución espectral**: capacidad de separar dos tonos; `f_m/L`. **Respuesta impulsional (*resposta impulsional*)**. **Retardo de grupo**: `−dφ/dω`. **SOS**: secciones de segundo orden en cascada. **STFT**: transformada de Fourier de tiempo corto. **Ventana (*finestra*)**. **TF / DTFT / DFT**: transformada de Fourier, de secuencias, discreta. **`p_L[n]`**: pulso causal de `L` muestras. **Tren (*tren de pols*)**. **Señal base**: el periodo que, repetido, da una periódica. **Diente (*dent*)**. **Pulso (*pols*)**. **Filtre FIR / IIR**: de respuesta impulsional finita o infinita.

## Anexo F — Equivalencias MATLAB, laboratorio y Python

Tabla de la «Taula funcions Matlab» del curso, ampliada. «Convención» marca las diferencias que cambian un resultado.

| MATLAB | En el laboratorio | NumPy / SciPy | Convención |
|---|---|---|---|
| `fft(x, N)`, `ifft` | DFT de `N` puntos; relleno de ceros si `N > L` | `numpy.fft.fft(x, N)` | Sin `1/N` en la directa; `N < L` **trunca** la señal (no hace aliasing temporal) |
| `conv(x, y)` | Convolución lineal; longitud `L₁ + L₂ − 1` | `numpy.convolve` | El eje `n` hay que construirlo (`nc_conv`) |
| `filter(b, a, x)` | Ecuación en diferencias; condiciones iniciales nulas | `scipy.signal.lfilter` | `a[0] = 1` |
| `freqz(b, a, N)` | Respuesta en frecuencia | `scipy.signal.freqz` | Devuelve `ω` en rad/muestra: `F = ω/2π` |
| `roots(h)` | Ceros (FIR) o polos | `numpy.roots` | Orden descendente de potencias de `z⁻¹` |
| `zplane` | Plano z | (`matplotlib`) | — |
| `stem`, `plot` | `stem`, línea | `matplotlib.pyplot` | — |
| `abs`, `angle`, `unwrap` | Módulo, fase, desenrollado | `numpy` | — |
| `sinc(x)` | `sinc` normalizada | `numpy.sinc` | `sin(πx)/(πx)` |
| `hann(L)`, `hamming(L)`, `blackman(L)` | Simétrica | `scipy.signal.windows.hann(L, sym=True)` | `'periodic'` ↔ `sym=False` |
| `bartlett(L)`, `triang(L)` | Triangular (extremos 0 y no 0) | `windows.bartlett`, `windows.triang` | La del curso es `p_M*p_M/M` |
| `kaiser(L, β)` | Kaiser | `windows.kaiser` | — |
| `fir1(M, Wn, win)` | FIR por ventanas | `scipy.signal.firwin(M+1, Wn, window=…)` | `Wn` normalizada a Nyquist `= 2·F_c` |
| `firpm(M, F, A, W)` | Parks-McClellan | `scipy.signal.remez(M+1, bands, desired, weight, fs)` | `M` es el **orden** (`L = M + 1`); pesos `[δ_a, δ_p]` |
| `butter`, `buttord` | Butterworth y orden | `scipy.signal.butter`, `buttord` | `Wn = 2F` (Nyquist = 1) |
| `cheby1`, `cheb1ord` | Chebyshev I | `scipy.signal.cheby1`, `cheb1ord` | Rizado `α_p` en dB |
| `cheby2`, `cheb2ord` | Chebyshev II | `scipy.signal.cheby2`, `cheb2ord` | La frecuencia es la de la banda atenuada |
| `ellip`, `ellipord` | Elíptico | `scipy.signal.ellip`, `ellipord` | `α_p` y `α_a` en dB |
| `bilinear` | Bilineal con pre-distorsión | `scipy.signal.bilinear` | `Ω = tan(πF)` frente a `2 f_m` |
| `tf2sos`, `sosfilt` | SOS | `scipy.signal.tf2sos`, `sosfilt` | Emparejamiento de polos y ceros |
| `xcorr(x, y)` | Correlación cruzada | `numpy.correlate`, `scipy.signal.correlate` | Normalización (`'biased'`, `'unbiased'`) y conjugación |
| `spectrogram`, `pwelch` | STFT y Welch | `scipy.signal.spectrogram`, `welch` | Escalas de densidad |
| `resample(x, p, q)` | Remuestreo `p/q` | `scipy.signal.resample_poly` | Filtro implícito |
| `decimate`, `interp`, `upsample`, `downsample` | Diezmado, interpolación | `scipy.signal.decimate` | Con o sin filtro |
| `hilbert` | Transformada de Hilbert (señal analítica) | `scipy.signal.hilbert` | — |
| `audioread`, `audiowrite`, `sound` | E/S de audio y reproducción | `wave`, `soundfile` | Normaliza a `[−1, 1]` |
| `length`, `size`, `max`, `min`, `mean`, `sum(x.^2)` | Medidas de P1 | `numpy` | Energía `Σx²` |
| `randn`, `rng` | Ruido sembrado | — (nuestro generador sembrado) | No reproduce el flujo de MATLAB |
| `tic`, `toc` | Tiempo medido (no determinista) | `time.perf_counter` | Fuera del *digest* |
| `fftshift` | Eje centrado | `numpy.fft.fftshift` | — |
| `polyfit` | Mínimos cuadrados | `numpy.polyfit` | — |

## Anexo G — Valores dorados medidos para esta especificación

Obtenidos con un prototipo en NumPy 2.5.1 para redactar este documento (no existe implementación). Son **valores de referencia a re-medir** con el motor en SG-2 y SG-8/SG-9 y a fijar como dorados con su tolerancia.

**G.1 Ventanas (L = 64, relleno de ceros a 65 536; simétricas de NumPy)**

| Ventana | Primer cero (`F·L`) | Lateral máx. (dB) |
|---|---|---|
| Rectangular | 1,00 | −13,25 |
| Triangular (`bartlett`) | 2,00 | −26,51 |
| Hann | 2,03 | −31,47 |
| Hamming | 2,07 | −42,45 |
| Blackman | 3,05 | −58,11 |

**G.2 Espectro de `A = 4`, `F₀ = 1/4`, `L = 30` (`N = L = 30`)**

| `k` | 5 | 6 | **7** | **8** | 9 | 10 |
|---|---|---|---|---|---|---|
| `\|X[k]\|` | 8,000 | 12,944 | **38,267** | **38,267** | 12,944 | 8,000 |

Con `N = 4 096`: pico `60,000` en `k = 1 024`. `f_x = 2 147 Hz`, `N = 30`: `k = 8`, `59,808`. `f_x = 2 400 Hz`, `N = 30`: `k = 9`, `60,000`. Triangular de 19 muestras (`w = [1:10, 9:−1:1]/10`, `Σw = 10`), `N = 512`: pico `20,000` en `k = 128` y `384`.

**G.3 Filtros (plantilla de P10: `f_m = 16 kHz`, `f_p = 3,6`, `f_a = 4`, `α_p = 1`, `α_a = 40`; corte `F_c = 0,2375`)**

| Diseño | `L` | Rizado en paso (dB, pico a pico) | Atenuación mínima en la atenuada (dB) |
|---|---|---|---|
| Rectangular | 21 | 3,44 | −12,5 |
| Rectangular | 41 | 1,18 | −20,9 |
| Rectangular | 101 | 0,99 | −24,5 |
| Rectangular | 201 | 0,50 | −29,6 |
| Hamming | 121 | 0,10 | −40,3 |
| Hamming | 131 | 0,04 | −49,7 |
| Hamming | 141 | 0,03 | −55,0 |
| Kaiser `β = 3,34` | 89 | 0,18 | −39,2 |
| Kaiser `β = 3,34` | 91 | 0,15 | −40,3 |

Estimadores: Kaiser de ventana `88`; Herrmann (equirrizado) `52,5`. `δ_p = 0,057501`, `δ_a = 0,010575`. **Pendiente de medir**: Parks-McClellan (no hay `scipy` en el entorno de redacción).

**G.4 Plantilla de P11 (`f_p = 3,7`, `f_a = 4`, `α_p = 1`, `α_a = 60`, `f_m = 16 kHz`)**: `Ω_p = 0,88862`, `Ω_a = 1`. Butterworth `64,22 → 65`; Chebyshev I y II `16,70 → 17`; elíptico `7,66 → 8`.

**G.5 Otros**: `0,5^{1/10} = 0,93303`, `0,5^{1/20} = 0,96593`; `sinc(0,4) = 0,75683`, `sinc²(0,4) = 0,57280` (`+4,84 dB`, ZOH `+2,42 dB`); `h = e^{−t/10}u(t)`: `10 ln 100 = 46,052 s`, `\|H(0,2)\| = 0,7933` (`−2,012 dB`), `−60 dB` en `15,915 Hz`; `p₆ * p₆ = [1,2,3,4,5,6,5,4,3,2,1]`; `N = 9`: `[3,3,3,4,5,6,5,4,3]`.

## Anexo H — Trazabilidad de los ids de `extra_senales.md`

| Id | Bloque | Dónde se cubre | Fase | Casos |
|---|---|---|---|---|
| SS-0 | Biblioteca de señales | §6 | SG-1 | ES-40 |
| SS-1 | Propiedades de sistemas | §7.1 | SG-5 | — |
| SS-2 | Convolución analógica | §7.3 (visor); cálculo en `MATH_LAB` | SG-5 | — |
| SS-3 | Convolución digital y regímenes | §7.4 (visor) | SG-3 | ES-26 |
| SS-4 | Respuesta en frecuencia y dB | §7.5 | SG-5 | ES-18 a ES-20, ES-22 |
| SS-5 | Periódicas | Visor en §7 y §18.9; cálculo en `MATH_LAB` | SG-5 | ES-23 |
| SS-6 | Energía y potencia | Medidas en §7.2; cálculo en `MATH_LAB` | SG-5 | — |
| SS-7 | Correlación y PSD | §13.2 (visor); cálculo en `MATH_LAB` | SG-11 | ES-35, ES-36 |
| SS-8 | Filtro adaptado | §13.1 | SG-11 | ES-34 |
| SS-9 | Muestreo | §10 | SG-4 | ES-05, ES-15, ES-21 |
| SS-10 | DTFT | Visor en §8, §18.6; cálculo en `MATH_LAB` | SG-3 | ES-24, ES-25 |
| SS-11 | Eco, reverberación, inverso | §7.7 | SG-5 | ES-12 a ES-14, ES-22 |
| SS-12 | DFT y lectura de espectros | §8 | SG-2 | ES-01, ES-02, ES-04 a ES-09, ES-32, ES-37 |
| SS-13 | Ventanas | §9 | SG-2 | ES-03, ES-10, ES-31 |
| SS-14 | Propiedades de la DFT | §8.7 | SG-3 | ES-11 |
| SS-15 | Modulación y multiplexación | §11 | SG-7 | ES-16, ES-17, ES-33, ES-39 |
| SS-16 | Diseño FIR | §12.2 a §12.5 | SG-8, SG-10 | ES-27, ES-28, ES-38 |
| SS-17 | Diseño IIR | §12.6 | SG-9 | ES-29, ES-30 |
| SS-18 | Cuantización | §16 | SG-15 | — |
| TRS-1, TRS-2 | Procesos y PSD | §14.4, §17 | SG-12, SG-14 | — |
| TRS-3 | Detección | §17 (visor); matemática en `MATH_LAB` | SG-14 | — |
| TRS-4, TRS-5 | Estimación | §17 | SG-14 | — |
| TRS-6 | Wiener | §17 | SG-14 | — |
| TRS-7, TRS-8 | Gradiente y LMS | §17 | SG-14 | — |
| MAE | MATLAB | Fuera; Anexo F | SG-16 | — |

---

*Fin del documento. Estado: decisiones D1 a D24 aprobadas por el usuario; **no se ha iniciado ninguna implementación** y no se ha modificado nada del repositorio ni de OneDrive o `guias_upc` (solo lectura). Pendiente fuera de este documento: enunciados de P3 y P8 (D22), exámenes de Tratamiento de la Señal si existen (prioridades de SG-14), la D12 de `MATH_LAB.md` (temas sin asignar) y el destino físico de `dsp/` tras CI-R. Para empezar: indicar «arranca SG-0».*

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


### Capacidades específicas adicionales — SignalsLab

- Los datos experimentales deben conservar frecuencia de muestreo, duración, número de muestras, cuantización y condiciones de adquisición.
- La incertidumbre y el ruido deben distinguirse de la discrepancia del modelo cuando sea posible.
- El catálogo de gráficas debe cubrir tiempo, frecuencia, espectro, PSD, correlación y comparaciones de señales.
- Las ejecuciones estocásticas deben admitir semillas y configuración reproducible.

## Catálogo maestro de cobertura

La cobertura de este laboratorio se audita también en `docs/labs/COVERAGE_CATALOG.md`. Ese catálogo fija el contrato común de familia temática, estados y criterio de completitud; documentar una capacidad no implica que esté implementada.
