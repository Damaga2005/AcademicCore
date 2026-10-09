# Laboratorio de Matemáticas — Especificación de diseño

Estado: **v2 con las decisiones D1 a D12 aprobadas por el usuario (§13); implementación en curso: ML-0, ML-1 y el motor trigonométrico (T-01 a T-24) completos; ML-12 y ML-2 completos; ML-3 (núcleo + espacios vectoriales), ML-5 (varias variables) ML-6 (integración múltiple) ML-7 (línea, superficie y teoremas), ML-13 (cálculo vectorial ampliado), ML-4 (series y métodos numéricos), ML-8 (EDO y transformadas), ML-9 (probabilidad y estadística), ML-14 (señales y sistemas deterministas), ML-15 (fasores y polarización), ML-16 (campos y ondas), ML-22 (física auxiliar) y ML-17 (discreta, códigos e información), ML-18 (detección y estimación), ML-19 (optimización y aprendizaje), ML-20 (Markov, MDP y refuerzo), ML-21 (matemáticas financieras), ML-10 (ejercicios, corrector y generador) y ML-11 (el pulido: accesibilidad, rendimiento, documentación y certificación) completos**; **las 24 fases de §10 están implementadas y certificadas** (`docs/gates/GATE-MATH-LAB-CERTIFICATION.md`: 80/80 operaciones, 0 fallos, 0 lentas, 0 no deterministas) · Fecha: 2026-10-09 (v1: 2026-09-30)
Ámbito: desde la aritmética básica hasta las integrales triples, de línea y de superficie, pasando por cálculo, álgebra lineal, ecuaciones diferenciales, transformadas y probabilidad. Cada tema con **ejercicios para resolver, gráficas y solución paso a paso**. **v2** añade la matemática de otras asignaturas del grado que no es de otro laboratorio: matemática discreta y cuerpos finitos, códigos y criptografía, teoría de la información, Markov y refuerzo, optimización y aprendizaje automático, finanzas, señales deterministas, detección y estimación, fasores y polarización, campos y ondas, y mecánica auxiliar (**bloques 8 a 19**). Lo que va a `SIGNALS_LAB.md` y a `CIRCUITS_LAB.md` está en la tabla «qué va dónde» (§16).
Fuentes: guías docentes de GREELEC (UPC) en `guias_upc/` — Cálculo (230903), Álgebra Lineal (230904), Cálculo Vectorial (230908), Ecuaciones Diferenciales y Transformadas (230909), Probabilidad y Procesos Estocásticos (230914), Señales y Sistemas (230913). **v2:** cuatro informes de lectura de solo lectura en `Descargas/labs/math_catalog/` (`extra_senales.md`, `extra_electromagnetismo.md`, `extra_circuitos_control.md`, `extra_algoritmia_ia_codigos.md`), integrados con el **reparto decidido por el usuario** (D6, §13) y sin tocar el repositorio ni `guias_upc`.

---

## 0. Cómo leer este documento

| Sección | Contenido |
|---|---|
| 1 | Objetivo y principios |
| 2 | Punto de partida real (qué hay ya en el repositorio) |
| 3 | Mapa de temas y asignaturas |
| 4 | Catálogo por niveles, del 0 al 7, y **bloques nuevos 8 a 19 (v2)** |
| 5 | El motor matemático (exactitud, pasos, verificación), **contrato con otros laboratorios (5.9), arquitectura (5.10) y convenciones declaradas (5.11)** |
| 6 | Gráficas |
| 7 | Ejercicios, corrección y generador |
| 8 | **Calculadoras (catálogo completo, todas con pasos)** |
| 9 | Interfaz |
| 10 | Fases de entrega |
| 11 | Pruebas y criterios de aceptación |
| 12 | Riesgos y límites |
| 13 | Decisiones (D1 a D12, todas ✅ DECIDIDO) |
| 14 | Lo que muestran los materiales reales (exámenes, problemas, apuntes) |
| 15 | Catálogo priorizado con datos de los exámenes: 15 tipos por asignatura y cambios de diseño; **15.6 a 15.8: segunda tanda (v2)** |
| 16 | **Qué va dónde**: MATH_LAB, SIGNALS_LAB, CIRCUITS_LAB y DIGITAL_DESIGN_LAB; resolución de D12 |
| 17 | **Fuera de alcance** (anotado) |

---

## 1. Objetivo y principios

### 1.1 Objetivo

Que un estudiante pueda resolver en una sola pantalla **cualquier ejercicio típico de matemáticas del grado**: escribirlo, obtener el resultado, **ver cada paso con la regla usada**, ver la **gráfica** que lo explica y **comprobar** que es correcto.

### 1.2 Principios

1. **Exactitud.** Se trabaja con fracciones, raíces y constantes (π, e) de forma exacta siempre que se pueda. El resultado aproximado se marca como aproximado y con su error.
2. **Cada paso se explica.** Qué regla se aplica, sobre qué trozo, y qué queda. Sin cajas negras. **Todo cambio de variable se muestra y se justifica** (§5.6) y **se comprueban las hipótesis de cada teorema** (§5.7).
3. **Nada se muestra sin comprobar.** Todo resultado se verifica por un **segundo camino independiente** (derivar la primitiva, sustituir en la ecuación, evaluar numéricamente, calcular la integral por el otro orden…).
4. **Honestidad.** Si el sistema no sabe resolver algo de forma exacta, lo dice y ofrece la versión numérica con el error acotado; nunca inventa.
5. **La interfaz solo dibuja y pide.** La matemática vive en dominio y aplicación, sin Qt (igual que el resto del proyecto).
6. **Librerías al servicio de la corrección.** El proyecto hoy solo usa PySide6; el usuario autoriza cualquier librería que ayude a que un resultado sea correcto (D1), siempre como comprobadora y nunca sustituyendo los pasos del motor propio (§5.8).
7. **Español**, con notación matemática clara y entrada de fórmulas cómoda.
8. **Convención declarada (v2).** Todo ejercicio que dependa de una convención (valor eficaz o de pico, signo de la exponencial compleja, dB de amplitud o de potencia, varianza con `n` o con `n−1`, umbral de Chauvenet del curso…) **la declara y la muestra**, y la verifica contra la convención contraria como segundo camino (§5.11).
9. **Motor compartido (v2).** El motor de pasos, el corrector y los verificadores se ofrecen por un **contrato estable** a los demás laboratorios (señales, circuitos, diseño digital). El laboratorio de matemáticas **no contiene modelos de ingeniería**: ofrece la capa matemática genérica y recibe de los otros labs sus plantillas de ejercicio (§5.9, §16). **`math` no importa `digital`**: la dependencia es `digital → math`, y `DIGITAL_DESIGN_LAB` se **registra como plug-in de verificación** de §4.8 (equivalencia lógica por tabla exhaustiva) y de §4.10 (LFSR frente a la división polinómica del CRC).

---

## 2. Punto de partida real

Ya existe en `domain/engineering/`:

| Módulo | Qué aporta | Límite |
|---|---|---|
| `symbolic/` | Expresiones exactas con fracciones, derivadas, integrales por sustitución y por partes, ecuaciones lineales, simplificación y **registro de pasos** | **Una sola variable** en derivación e integración |
| `math/` | Resolución de sistemas lineales, racionales, complejos con `Decimal`, trigonometría, logaritmos | Sin matrices generales, sin autovalores |
| `dsp/`, `control/`, `ac/` | Transformada z, DFT, funciones de transferencia, raíces de polinomios | Orientados a ingeniería, no a enseñar la matemática |
| `ui/waveform.py` | Dibujo de formas de onda con Qt | No es un graficador general |

**Falta todavía**: matrices generales y autovalores, límites, series, Taylor, ecuaciones diferenciales, Laplace y Fourier simbólicos, integrales múltiples y de línea o de superficie, probabilidad y estadística, graficador 2D y 3D y corrector de respuestas matemáticas. La derivación multivariable/gradiente, evaluación, igualdad, simplificación e integración iniciales ya tienen implementación en MathLab (§10 y `mathlab/calculators.py`).

**Falta además (v2)**, comprobado por nombres de módulo en el informe de circuitos y control (no leyendo código): fracciones racionales **multivariable** con símbolos (`R`, `C`, `K`, `x`) y simplificación a la forma `K·Π(s−z)/Π(s−p)`; aritmética modular y **cuerpos finitos**; simulador sembrado de **eventos**; ajuste por mínimos cuadrados general y **no lineal**; **Lambert W**; **problemas de contorno** en una dimensión; el **criterio de Chauvenet del curso**; y el **análisis dimensional** como comprobador universal.

**Lo que ya existe y se reutiliza como motor de verificación** (no se reescribe, no es de este laboratorio): `control/` (Routh, lugar de raíces, márgenes, espacio de estados), `ac/` (Bode, fasores, potencia, pequeña señal), `gum.py` y `metrology/`, `mna/`, `rf/lines.py` y `dsp/` (incluida la DFT). Pertenecen a los laboratorios de señales y de circuitos (§16); aquí solo se usan como **segundo camino** a través del contrato de §5.9.

---

## 3. Mapa de temas y asignaturas

| Bloque | Temas de las guías | Asignatura |
|---|---|---|
| **0 Aritmética y álgebra elemental** | Base para todo lo demás | (previo; «Introducción a las Matemáticas») |
| **1 Funciones y trigonometría** | Cálculo, temas 1 y 2 | Cálculo |
| **2 Cálculo de una variable** | Cálculo, temas 3 a 12 | Cálculo |
| **3 Álgebra lineal** | Álgebra Lineal, temas 1 a 6 | Álgebra Lineal |
| **4 Cálculo vectorial** | Varias variables, curvas y superficies, integración múltiple, integrales de línea y de superficie, Green, Stokes, Gauss; **ampliado (v2): operadores ∇ en cilíndricas y esféricas, laplaciano y cambio de componentes entre bases; cinemática intrínseca de curvas (D12)** | Cálculo Vectorial; Electromagnetismo; Física |
| **5 Ecuaciones diferenciales y transformadas** | EDO, Laplace, Fourier, transformada z, EDP introductoria; **v2: oscilador con factor Q y conducción de calor 1D (D12)** | Ecuaciones Diferenciales y Transformadas; Física |
| **6 Probabilidad y estadística** | Probabilidad, variables aleatorias, estadística, procesos estocásticos; **v2: BER con `Q`, ALOHA, Rayleigh y Rice, ARQ (D12)** | Probabilidad y Procesos Estocásticos; Telecomunicación espacial |
| **7 Métodos numéricos** | Cálculo, tema 12; apoyo de los demás; **v2: capa genérica para otros labs (ajuste no lineal, Lambert W, trascendentes con varias raíces, problemas de contorno 1D, EDO implícitas)** | Cálculo y otras |
| **8 Matemática discreta** (v2) | Lógica, conjuntos, inducción, recurrencias, sumatorios, complejidad; **tiempo real: utilización, Liu-Layland, RTA, hiperperiodo (D12)** | IMATEC; Algoritmia y Programación; Estructuras de Datos; Tiempo Real |
| **9 Aritmética modular y cuerpos finitos** (v2) | ℤₙ, GF(p), GF(2), GF(2ᵐ); el motor de Gauss acepta el **cuerpo como parámetro**; cifrado clásico | Álgebra Lineal (códigos y secreto); Algoritmia |
| **10 Códigos, secretos y clave pública** (v2) | Códigos lineales, Hamming, CRC, Shamir, esquemas lineales, RSA, Diffie-Hellman; **privacidad: k-anonimato, microagregación, privacidad diferencial (D12)** | Álgebra Lineal (códigos y secreto); Seguridad (nivel numérico) |
| **11 Teoría de la información** (v2) | Entropía, KL, Huffman, capacidad de canal | Aprendizaje Automático y Profundo; Códigos; IoT |
| **12 Markov, MDP y refuerzo** (v2) | Cadenas, Bellman, Q-learning, bandidos | Aprendizaje por Refuerzo (hueco de Probabilidad) |
| **13 Optimización y aprendizaje automático** (v2) | Descenso de gradiente, regresión, logística, métricas, k-medias, PCA, SVD, retropropagación a mano | Aprendizaje Automático y Profundo; Resolución de Problemas con IA |
| **14 Matemáticas financieras** (v2) | Interés, VAN/TIR, bonos, futuros, CRR, Black-Scholes, Monte Carlo, Markowitz | Ingeniería Financiera |
| **15 Señales y sistemas deterministas** (v2) | Convolución por tramos, series de Fourier por señal base, DTFT, DFT, z, correlación y densidad espectral deterministas | Señales y Sistemas |
| **16 Detección y estimación** (v2) | MAP, Neyman-Pearson y ROC, Cramér-Rao, Wiener, LMS y NLMS; **PSD teórica de procesos discretos (D12)** | Tratamiento de la Señal |
| **17 Fasores y polarización** (v2) | Régimen senoidal, onda plana, medios con pérdidas, Jones y retardadores; **Fresnel, Brewster, reflexión total y multicapa (D12)** | Electromagnetismo Aplicado y Fotónica |
| **18 Campos y ondas** (v2) | Electrostática por regiones, verificación de Maxwell, ecuación de onda por sustitución; **Coulomb y Biot-Savart por integración, Ampère, condensadores y dieléctricos, inducción y Poynting, antenas y enlace (D12)** | Electromagnetismo; Electromagnetismo Aplicado; Telecomunicación espacial |
| **19 Física auxiliar** (v2) | Equilibrio y oscilaciones desde U(x); termodinámica del gas ideal (**opcional**); **órbitas y Kepler, visibilidad esférica; Maxwell-Boltzmann, Planck y Stefan (opcional) (D12)** | Física; Telecomunicación espacial |

**Leyenda de respaldo (v2).** En los bloques 8 a 19, cada tipo de ejercicio lleva **E** si aparece en exámenes reales leídos (recuento «n/N» manual, ±1 o ±2) o **G** si solo está en la guía docente (frecuencia inferida del temario, **prioridad menor**: se construye después de los E, §15.6). Los bloques 0 a 7 conservan el respaldo de §15.

---

## 4. Catálogo por niveles

Para cada bloque: **qué resuelve**, **pasos que enseña**, **gráfica** y **verificación**.

### 4.0 Aritmética y álgebra elemental

| Tema | Ejercicios | Gráfica / ayuda |
|---|---|---|
| Operaciones básicas | Sumas, restas, productos y divisiones, con llevadas y división larga paso a paso | Columnas como en papel |
| Fracciones | Simplificar, operar, comparar, pasar a decimal y periódico | Recta numérica |
| Potencias, raíces, logaritmos | Propiedades, racionalizar, cambio de base | Tabla de propiedades |
| Porcentajes, proporciones, regla de tres | Variación, interés; **v2:** impuestos por **tramos marginales** (función a trozos), anualidades y rentas (enlaza con el bloque 14) | — |
| Divisibilidad | MCD, MCM, factorización en primos, criterios; **v2:** suma de divisores σ(n), números perfectos, criba de Eratóstenes y primalidad hasta √n con su coste contado, dígitos y letra del DNI (resto mod 23) (E débil: hojas de APR) | Árbol de factores |
| Bases de numeración | Conversión (enlaza con las calculadoras del laboratorio digital); **v2:** máscaras y AND/OR/XOR/desplazamiento, direccionamiento IPv4 y subredes (G); el complemento a 2, rango y desbordamiento **no se duplica aquí**: su implementación única es `DIGITAL_DESIGN_LAB.md` §10 (el punto flotante IEEE 754 profundo queda fuera, §17) | — |
| Polinomios | Suma, producto, división, Ruffini, factorización, identidades notables | Gráfica del polinomio |
| Ecuaciones e inecuaciones | Lineales, cuadráticas, con valor absoluto, racionales, irracionales, exponenciales y logarítmicas | Solución sobre la recta real |
| Sistemas de ecuaciones | Sustitución, igualación, reducción | Rectas que se cortan |
| Sucesiones y combinatoria básica | Progresiones, factoriales, combinaciones; **v2:** binomio de Newton, Pascal e identidades (más en el bloque 8) | Triángulo de Pascal |

### 4.1 Funciones y trigonometría

Dominio y recorrido, inyectiva/exhaustiva/biyectiva, función inversa, composición; polinómicas, racionales, potenciales, exponenciales, logarítmicas, trigonométricas e hiperbólicas; transformaciones (desplazar, escalar, reflejar); identidades trigonométricas y ecuaciones trigonométricas; resolución de triángulos. Gráfica de cada función con sus transformaciones y de la inversa como reflexión.

### 4.2 Cálculo de una variable

| Tema (guía) | Ejercicios | Gráfica |
|---|---|---|
| Números reales (T1) | Desigualdades, valor absoluto, intervalos, supremo e ínfimo | Recta real |
| Límites (T3) | Límites en un punto y en el infinito, laterales, **indeterminaciones** (∞/∞, ∞−∞, 1^∞, 0/0), regla de L'Hôpital | Función con la zona del límite |
| Continuidad (T4) | Tipos de discontinuidad, teoremas de Bolzano, Weierstrass y del valor medio | Puntos de discontinuidad marcados |
| Derivabilidad (T5) | Derivada por definición y por reglas (producto, cociente, cadena, inversa, implícita), recta tangente, Rolle | Función y tangente que se mueve |
| Taylor (T6) | Polinomios de Taylor y resto, aproximaciones, límites por Taylor | **Función frente a Taylor de grado n** |
| Estudio de funciones (T7) | Crecimiento, extremos, concavidad, inflexión, **asíntotas**, estudio completo con tabla de signos | Gráfica final con todos los elementos |
| Primitivas (T8) | Inmediatas, **por partes**, **cambio de variable**, racionales (fracciones simples), trigonométricas, irracionales | Función y primitiva |
| Integral de Riemann (T9) | Definida, teorema fundamental, áreas, volúmenes de revolución, longitud de arco | **Sumas de Riemann** (izquierda, derecha, punto medio) acercándose al área |
| Impropias (T10) | Primera y segunda especie, criterios de convergencia, función gamma | Área bajo la cola |
| Series (T11) | Criterios (comparación, razón, raíz, integral), alternadas, series de potencias, **radio de convergencia**, Taylor | Sumas parciales |
| Métodos numéricos (T12) | Bisección, Newton, punto fijo, trapecios, Simpson, interpolación | Iteraciones sobre la gráfica |

### 4.3 Álgebra lineal

| Tema | Ejercicios | Gráfica |
|---|---|---|
| Números complejos | Formas binómica, polar y exponencial, potencias y raíces, fórmula de Euler | **Plano complejo** |
| Matrices y sistemas | Operaciones, **Gauss y Gauss-Jordan paso a paso**, rango, inversa, determinantes (Laplace, Sarrus), Cramer, discusión de sistemas con parámetros | Sistemas 2×2 y 3×3 como rectas y planos |
| Espacios vectoriales | Independencia lineal, base, dimensión, coordenadas, cambio de base, subespacios | Vectores en 2D y 3D |
| Aplicaciones lineales | Matriz asociada, núcleo e imagen, cambios de base | Transformación de la cuadrícula |
| Espacio euclídeo | Producto escalar, norma, ortogonalidad, **Gram-Schmidt**, proyecciones, mínimos cuadrados | Proyección sobre un subespacio |
| Diagonalización | Autovalores y autovectores, polinomio característico, diagonalización, potencias de matrices | Autovectores sobre la transformación |
| **Álgebra lineal sobre un cuerpo cualquiera (v2)** | Gauss, rango, núcleo, inversa y determinante con el **cuerpo como parámetro** (ℚ, ℝ, ℂ, GF(p), GF(2)); detalle en el bloque 9. Las matrices unitarias, la SVD de 2×2 (elipse de polarización, bloque 17) y PCA (bloque 13) son aplicaciones de este tema | Tabla de operaciones; datos proyectados |

### 4.4 Cálculo vectorial

| Tema (guía) | Ejercicios | Gráfica |
|---|---|---|
| Espacio euclídeo n-dimensional | Distancia, bolas, abiertos y cerrados, interior y frontera | Conjuntos en 2D |
| Funciones de varias variables | Dominio, **conjuntos de nivel**, límites direccionales, continuidad | **Curvas de nivel** y superficie 3D |
| Derivación | Parciales, **gradiente**, derivada direccional, jacobiana, regla de la cadena, función implícita, cambios de coordenadas (polares, cilíndricas, esféricas) | Gradiente sobre las curvas de nivel; plano tangente |
| Extremos | Hessiana, criterio de Sylvester, **puntos críticos y de silla**, Taylor de grado 2 | Superficie con los puntos marcados |
| Extremos condicionados | **Multiplicadores de Lagrange**, extremos absolutos en recintos | Restricción tangente a la curva de nivel |
| Curvas y superficies | Parametrización regular, recta y plano tangente, longitud, área | Curva y superficie parametrizadas |
| **Integración múltiple** | **Integrales dobles y triples**: Fubini, **cambio del orden de integración**, **cambio de variable con jacobiano** (polares, cilíndricas, esféricas), áreas, volúmenes, masa y centro de masas | **Región de integración** dibujada y cortes por planos |
| **Integrales de línea** | De una función escalar y de un campo vectorial (**circulación**), independencia del camino, **campos conservativos** y cálculo del **potencial escalar** | Curva con el campo |
| **Integrales de superficie** | De función escalar y **flujo** de un campo vectorial, vector normal, orientación | Superficie con normales y campo |
| **Teoremas** | **Green, Stokes y Gauss (divergencia)**, rotacional, divergencia, campos solenoidales, potencial vectorial | Región, frontera y orientación |
| **Operadores ∇ en cilíndricas y esféricas (v2, E)** | Gradiente, divergencia, rotacional y laplaciano con los **factores de escala** `h_i` (el catálogo anterior solo trataba el cambio de coordenadas *de la integral*, no los operadores); `∇²V = −ρ/ε₀` (Poisson); `∇·(∇×F) = 0` como control. Respaldo: Electromagnetismo 9/9 y 5/5 parciales | Vectores base `r̂, θ̂, φ̂` locales sobre la región |
| **Cambio de componentes entre bases (v2, E)** | Matriz de rotación ortogonal `R(φ)` o `R(θ,φ)`; `E(2, π/4, 3) = E_r r̂` a cartesianas; `abs(E)` invariante, `RᵀR = I`, ida y vuelta | Campo en las dos bases |
| **Cinemática intrínseca de curvas (v2, E, D12)** | Para `r(t)`: tangente `T`, curvatura `κ = abs(r′×r″)/abs(r′)³`, `a_t = d(abs(v))/dt`, `a_n = κ·abs(v)²`, radio de curvatura; `a = a_t·T + a_n·N`. Respaldo: Física, ≈ 12/15 | Trayectoria con `T`, `N` y las dos componentes de `a` |

Para los teoremas, el sistema calcula **los dos lados** (p. ej. la circulación por la curva y la integral doble del rotacional) y **muestra que coinciden**; esa es la comprobación.

### 4.5 Ecuaciones diferenciales y transformadas

| Tema | Ejercicios | Gráfica |
|---|---|---|
| EDO de primer orden | Separables, lineales, exactas, Bernoulli, con problema de valor inicial | **Campo de direcciones** y solución |
| EDO lineales de orden superior | Coeficientes constantes, homogéneas y no homogéneas (coeficientes indeterminados, variación de constantes) | Soluciones |
| Sistemas lineales | Con valores propios (enlaza con 4.3) | **Plano de fases** |
| **Transformada de Laplace** | Definición, propiedades, tabla, **inversión por fracciones simples**, funciones por trozos, convolución, delta de Dirac, **resolver EDO** | Señal en el tiempo |
| **Series de Fourier** | Trigonométrica y exponencial, pares e impares, Parseval, convergencia; **v2:** método de la **señal base** (`c_k = (1/T₀)·X_b(k/T₀)`) y TF de periódicas como deltas (bloque 15, E 18/29) | **Sumas parciales** sobre la función |
| **Transformada de Fourier** | Definición, propiedades, transformadas básicas, Parseval, convolución; **v2:** convenio de frecuencia ordinaria `f` de Señales y Sistemas (§5.11) | Señal y espectro |
| **Transformada z** | Propiedades, región de convergencia, inversión, convolución de secuencias; **v2:** eco, reverberación e inverso con geometría de polos y ceros (bloque 15) | Secuencia y polos y ceros |
| Métodos numéricos para EDO | Euler, Runge-Kutta | Solución exacta frente a numérica |
| **Oscilador amortiguado y forzado con factor Q; conducción de calor 1D (v2, E, D12)** | `m·x″ + b·x′ + k·x = F(t)`: subamortiguado, crítico y sobreamortiguado, `Q = ω₀/(2γ)`, resonancia y ancho de banda (reutiliza las EDO lineales de orden n); calor `u_t = α·u_xx` con barras y condiciones de contorno (separación de variables introductoria, §4.5 EDP). Respaldo: Física | Respuesta frente a `ω` y evolución de `u(x,t)` |
| EDP introductoria | Separación de variables (ecuaciones del calor y de ondas, nivel introductorio) | Evolución en el tiempo |
| **Problemas de contorno 1D (v2, capa genérica, G)** | `y'' = y/L²` con condiciones en **dos extremos** (`cosh`/`sinh`), existencia y unicidad por el determinante de contorno, límites `w ≫ L` y `w ≪ L`; Poisson 1D por tramos con **empalme** de campo y potencial; diferencias finitas tridiagonales como contraste. Lo usan los laboratorios de circuitos y dispositivos (§16) | Solución, asíntotas y varias `L` a la vez |
| Ecuación de onda y Maxwell como **verificación por sustitución (v2)** | Ver bloque 18; aquí solo la regla: el campo candidato se sustituye en la EDP, nunca se «resuelve» por separación de variables en cilíndricas o esféricas (fuera, §17) | Trazas en el tiempo |

### 4.6 Probabilidad y estadística

| Tema | Ejercicios | Gráfica |
|---|---|---|
| Probabilidad básica | Combinatoria, espacios discretos y continuos, condicionada, independencia, **Bayes**, probabilidad total | **Árbol de probabilidad**, diagrama de Venn |
| Variables aleatorias | Discretas (Bernoulli, binomial, geométrica, Poisson) y continuas (uniforme, exponencial, gaussiana), esperanza, varianza, momentos, Chebyshov, funciones de una variable | Función de probabilidad o densidad y **distribución acumulada**; áreas sombreadas |
| Varias variables | Conjunta, marginales, condicionadas, **covarianza y correlación**, suma por convolución, estimación lineal | Densidad conjunta 2D y curvas de nivel |
| Estadística | Descriptiva (histogramas, boxplots, dispersión), **teorema central del límite**, estimadores (momentos, máxima verosimilitud), **intervalos de confianza** | Histogramas y ajuste |
| Procesos estocásticos | Media, autocorrelación, estacionariedad, proceso gaussiano y de Poisson; **v2:** cadenas de Markov y paseo aleatorio (bloque 12), la distribución de Laplace de la privacidad diferencial se trata en el bloque 10 (D12) | **Realizaciones** sembradas y autocorrelación |
| **Comunicaciones (v2, G, D12)** | **BER con `Q`** (`P_b = Q(√(2E_b/N₀))` y variantes), ALOHA puro y ranurado (`S = G·e^{−2G}`, `S = G·e^{−G}`), desvanecimiento **Rayleigh y Rice** (envolvente, probabilidad de fallo), **ARQ** (parada y espera, retroceso `N`, repetición selectiva: eficiencia). Shannon: bloque 11 | Curvas BER frente a `E_b/N₀` y `S(G)` |

### 4.7 Métodos numéricos

Raíces (bisección, Newton, secante, punto fijo), sistemas lineales (LU, iterativos), interpolación y mínimos cuadrados, integración (trapecios, Simpson, cuadratura), EDO (Euler, Runge-Kutta). Cada uno con **error y convergencia** mostrados en una gráfica.

**Capa genérica para otros laboratorios (v2).** Se añaden, como matemática pura y sin modelos de ingeniería (los ejemplos de dispositivos, sensores y circuitos viven en `CIRCUITS_LAB.md`, §16): **mínimos cuadrados lineales y no lineales** (Gauss-Newton con inicio razonable y diagnóstico de no convergencia, linealización por transformación `1/f`, `ln`, `log-log`, minimax frente a mínimos cuadrados); **ecuaciones trascendentes con *todas* las raíces** (barrido de signo + bisección + Newton, para Kepler, Wien o la dispersión de una lámina dieléctrica); **Lambert W real** (ramas 0 y −1) como forma cerrada de `x·eˣ = a`; **EDO implícitas** (Euler implícito, trapezoidal, estabilidad absoluta `abs(1−hλ)<1` y rigidez); y los **problemas de contorno 1D** de §4.5. **Funciones especiales** (Bessel `J_n`, `I₀`, integrales elípticas `K(k)`) solo como **biblioteca comprobadora** (mpmath o SciPy, con serie propia para `J₀` y `J₁`), sin teoría (G).

### Bloques nuevos 8 a 19 (v2)

Cada bloque lista el **tipo de ejercicio**, los **pasos con el porqué del método** (§5.5b), las **hipótesis que se comprueban** (§5.7), la **verificación por un segundo camino** (§5.3), la **gráfica** y el **respaldo** (leyenda en §3: **E** = exámenes reales, con recuento; **G** = solo guía, prioridad menor). Cada bloque se entrega con sus calculadoras (§8) y su generador sembrado. Lo que cada informe asignó a otro laboratorio **no** está aquí (§16).

### 4.8 Matemática discreta: lógica, conjuntos, inducción, recurrencias y complejidad

*Plug-in de verificación:* `DIGITAL_DESIGN_LAB` (`boolean/equiv.py`) se registra como segundo camino de la lógica proposicional; `math` no lo importa.

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| Lógica proposicional y cuantificadores: tablas de verdad, equivalencias, negar con ∀/∃, decidir una implicación | Formalizar → tabla de verdad o leyes (De Morgan, contrarrecíproco) con cada ley nombrada; negación símbolo a símbolo. La tabla sirve hasta unas 4 variables; con más, leyes | Dominio del cuantificador explícito; no confundir `p ⇒ q` con su recíproco | Enumeración de las 2ⁿ valoraciones frente a la derivación por leyes | Tabla de verdad | G (IMATEC, tema 1) |
| Conjuntos e inclusión-exclusión (2 a 4 conjuntos); conjunto potencia 2ⁿ | Definir por comprensión → operar → cardinal por fórmula | Finitud; no confundir ⊂ con ∈ | Enumeración explícita de los elementos | Venn sombreado | G |
| Demostración por inducción, contradicción y contrarrecíproco (sumatorios, √2 irracional, Bernoulli, divisibilidad) | Plantilla: caso base → hipótesis → paso → conclusión, cada paso etiquetado. **Honestidad:** verifica el cálculo, no el razonamiento libre; no es un demostrador automático | Base correcta y paso válido para todo `n ≥ n₀` (error típico: el paso usa `n−1` con `n₀ = 1`) | Comprobación numérica para `n = 1..N`; el paso no depende de un valor concreto | — | G |
| Binomio de Newton, Pascal e identidades (simetría, suma de filas, Vandermonde) | Término general `C(n,k)·aⁿ⁻ᵏ·bᵏ` → simplificar | `n` entero ≥ 0; binomio generalizado con `abs(x) < 1` | Evaluar en un punto (`a = b = 1` da 2ⁿ) | Triángulo de Pascal | E débil (Pascal recursivo, 1/13 APR) |
| Recurrencias: lineales (Fibonacci por ecuación característica), `T(n)=T(n−1)+c`, `T(n)=2T(n/2)+n`, teorema maestro | Recurrencia → caso base → resolver. El teorema maestro solo si tiene la forma `a·T(n/b)+f(n)`; si no, iteración o característica (se dice cuál y por qué) | Terminación (el argumento decrece al caso base); `T(1)` conocido | Iterar numéricamente frente a la fórmula cerrada; sustituir la solución en la recurrencia (paso de inducción) | Iteración frente a cerrada | G (recursión en 4 ficheros APR) |
| Ruina del jugador y paseo aleatorio como ecuación en diferencias con fronteras | `p_k = p·p_{k+1} + q·p_{k−1}`, `p₀ = 0`, `p_N = 1` → raíz característica → solución | Pasos independientes; barreras absorbentes | Para `p = 1/2`, `p_k = k/N`; simulación sembrada | Trayectorias y probabilidad frente a `k` | G (PPE, T9 §9.5) |
| Sumatorios y complejidad: contar ejecuciones del cuerpo, cerrar el sumatorio, término dominante, cota `f ≤ c·g` para `n ≥ n₀`; O(1) a O(2ⁿ); ordenación y búsqueda; mochila con 2ᴺ soluciones | Contar → sumatorio (progresión aritmética o geométrica) → dominante → justificar la cota | Modelo de coste explícito (comparaciones o asignaciones); peor, mejor y caso medio distinguidos | Contador instrumentado para varios `n` y `T(n)/g(n)` tiende a una constante; fórmula cerrada | Curvas de crecimiento en escala log | G (APR, PED) |
| Programación dinámica y voraz como solucionador exacto (mochila, cambio de monedas) | Fuerza bruta de 2ᴺ para `N` pequeño y PD como camino exacto; el voraz del cambio es óptimo solo con el sistema del euro y se avisa | Sistema de monedas declarado | PD frente a voraz y frente a fuerza bruta | Tabla de PD | G (proyecto 2023-24) |
| **Tiempo real (D12)**: utilización `U = ΣCᵢ/Tᵢ`, cota de **Liu-Layland** `n·(2^{1/n}−1)`, **tiempo de respuesta** (RTA) `Rᵢ = Cᵢ + Σⱼ⌈Rᵢ/Tⱼ⌉·Cⱼ` por punto fijo, hiperperiodo (mcm), EDF frente a prioridades fijas | Tareas con `(C, T, D)` → utilización → test suficiente (Liu-Layland) → si no concluye, RTA exacto (se explica por qué) | Tareas periódicas e independientes; `D ≤ T`; prioridades por tasa; fórmula de Liu-Layland **solo suficiente**, no necesaria | La iteración de RTA converge o supera `D`; simulación de eventos sembrada del cronograma sobre el hiperperiodo | Diagrama de Gantt | G (Tiempo Real; fórmula de Liu-Layland a verificar con el motor) |

### 4.9 Aritmética modular y cuerpos finitos

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| ℤₙ: tablas de suma y producto, **inversos por Euclides extendido**, congruencias `a·x ≡ b (mod n)`, teorema chino del resto, pequeño de Fermat, φ de Euler, orden y raíz primitiva, ¿es cuerpo? | Euclides con **todos los cocientes y la combinación** `a·s + b·n = 1`. Tabla completa solo si `n` es pequeño; Euclides si no | `gcd(a,n) = 1` para el inverso; para `a·x ≡ b` hace falta `gcd(a,n) divide a b` y entonces hay `gcd(a,n)` soluciones módulo `n`; `n` primo para cuerpo | Sustituir en la congruencia; `a·a⁻¹ mod n = 1`; contraste con la tabla de productos | Tabla de operaciones con diagonal y ceros marcados | G (Álgebra de códigos, tema 1) |
| Potencia modular por cuadrados sucesivos | Mostrar cada cuadrado y cada producto; reducir en cada paso | Exponente entero ≥ 0 | `pow` independiente; Fermat o Euler cuando aplica | — | G |
| **Cifrado clásico**: César `(x+k) mod 26` con `k` = suma de dígitos impares del DNI, afín `a·x+b`, Vigenère, Hill (matriz invertible mod 26) | Letra → 0..25 → operación → letra; descifrado con `−k` o `a⁻¹`; Hill: determinante coprimo con 26 | Alfabeto cerrado (sin ñ ni tildes); `gcd(a,26)=1`; `k ≥ 0`; en Python `%` ya es no negativo, en C hay que normalizar (**convención declarada**) | `descifrar(cifrar(x)) = x`; `k` y `k+26` dan lo mismo; `A·A⁻¹ = I (mod 26)` | Rueda de desplazamientos | **E** César 3/7 finales de APR (2018-19, 2020-21, 2022-23); afín, Vigenère y Hill G |
| Hash por módulo y paradoja del cumpleaños: `h(k) = k mod m`, factor de carga `α = n/m`, sondeo lineal frente a encadenamiento, `P(colisión) = 1 − Π(1 − i/m)` | Calcular `h(k)` → resolver colisiones → contar sondeos; coste medio de búsqueda con éxito ≈ `1 + α/2` (encadenamiento) | Hash uniforme; `m` primo conviene; `α < 1` en sondeo lineal | Simulación sembrada frente a la fórmula; Monte Carlo del cumpleaños | Histograma de ocupación | G (PED) |
| **Álgebra lineal sobre GF(p) y GF(2)**: independencia, base, dimensión, rango, núcleo, inversa, determinante, suma e intersección | Gauss-Jordan con **el cuerpo como parámetro** (`1+1=0` en GF(2), con XOR); pivotes → base → núcleo por variables libres | No hay división por 2 en GF(2); `−v = v`; un subespacio de dimensión `k` tiene `2ᵏ` elementos | Contar los `2ᵏ` elementos; `A·x = 0` para cada vector del núcleo; rango + nulidad = `n` | Elementos del subespacio (n pequeño) | G |
| Cuerpos **GF(2ᵐ)**: producto de polinomios módulo uno irreducible (p. ej. `x³+x+1`), tabla de potencias de α, inverso, `xⁿ−1` | Representar como polinomios de grado `< m` → multiplicar y reducir → tabla log/antilog | Polinomio módulo **irreducible** (si no, no es cuerpo); α primitivo para la tabla completa | `α^(2ᵐ−1) = 1`; `u·u⁻¹ = 1`; contar `2ᵐ` elementos | Tabla log/antilog | G, prioridad media |
| Polinomios sobre GF(p): división, irreducibilidad, interpolación de Lagrange mod p | Ruffini y división larga con coeficientes reducidos | `p` primo | Evaluar en todos los puntos del cuerpo | — | G |

### 4.10 Códigos lineales, compartición de secretos y clave pública

*Plug-in de verificación:* `DIGITAL_DESIGN_LAB` registra su LFSR (`calc/crc.py`) como segundo camino del CRC frente a la división polinómica de esta sección; `math` no importa `digital`.

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Código lineal**: `G ↔ H` en forma sistemática `[I\|P] ↔ [Pᵀ\|I]`, las `2ᵏ` palabras, codificar `u·G`, parámetros `[n,k,d]` | Llevar `G` a forma sistemática por Gauss (bloque 9) → `H` → comprobar `G·Hᵀ = 0` → enumerar | `G` de rango `k`; permutar columnas da un código equivalente | `G·Hᵀ = 0`; `H·c = 0` para cada palabra; número de palabras `2ᵏ` | Lista de palabras con peso | G |
| **Distancia mínima**, capacidad de detección `d−1` y corrección `⌊(d−1)/2⌋`, Singleton, Hamming (empaquetado), códigos perfectos | `d_min` = peso mínimo no nulo = mínimo de columnas de `H` linealmente dependientes. Si el código no es lineal, hay que mirar todos los pares (se avisa) | El código es **lineal**; errores independientes | `d_min` por pares frente a peso mínimo; columnas de `H` distintas y no nulas implican `d ≥ 3` | — | G |
| **Decodificación por síndrome**, líderes de clase, probabilidad de error en un canal binario simétrico | `s = H·r`; si `s` coincide con la columna `j` de `H`, invertir el bit `j` | A lo sumo `t = ⌊(d−1)/2⌋` errores; con más, **se avisa** de que la corrección es incorrecta | La palabra corregida pertenece al código y es la más cercana a `r` (por enumeración) | Esquema de palabras y bola de radio `t` | G |
| Hamming(7,4), **CRC** como división polinómica módulo 2, paridad bidimensional, checksum de Internet (complemento a 1 de 16 bits) | Añadir `r` ceros → dividir con XOR → resto = CRC → trama = mensaje + CRC | Generador con término independiente 1 y grado `r` | La trama completa da resto 0; forma matricial cíclica; **plug-in cruzado:** LFSR de `DIGITAL_DESIGN_LAB` frente a la división polinómica (mismo resto bit a bit) | División larga con XOR | G (IoT, Códigos) |
| **Compartición de secretos de Shamir** `(t, n)` sobre GF(p) | Polinomio de grado `t−1` con término libre = secreto → partes `f(i)` → reconstrucción `f(0) = Σ yᵢ·Πⱼ≠ᵢ (−xⱼ)/(xᵢ − xⱼ) (mod p)` | `p` primo, `p > n` y `p >` secreto; `xᵢ` distintos y no nulos; grado exacto `t−1` | **Dos subconjuntos distintos** de `t` partes dan el mismo secreto; con `t−1` partes cada valor es compatible (contar un polinomio por candidato) | Puntos del polinomio sobre GF(p) | G (trabajo final de la asignatura) |
| Esquema **lineal vectorial** sobre GF(2): conjuntos autorizados, estructura de acceso, monotonía, seguridad perfecta | Resolver `M·s = secreto` por Gauss sobre GF(2); mínimos autorizados | El vector del secreto está en el espacio de las columnas de los autorizados y fuera del de los no autorizados | Reconstrucción por dos conjuntos autorizados | Grafo de acceso | G |
| **RSA, firma y Diffie-Hellman** con primos pequeños | `p, q` → `φ=(p−1)(q−1)` → `e` → `d = e⁻¹ mod φ` (Euclides) → `c = mᵉ mod n` por cuadrados sucesivos; DH con generador `g` mod `p`; ataque por factorización de `n` pequeño | `p ≠ q` primos; `m < n`; `gcd(m,n)=1` para la ecuación de Euler (el caso general se explica por CRT) | `m^(e·d) ≡ m (mod n)`; `e·d ≡ 1 (mod φ)`; `pow` independiente | — | G. **Aviso fijo en pantalla:** material pedagógico, nunca para seguridad real |
| **Privacidad (D12)**: **k-anonimato** (clases de equivalencia, generalización), **microagregación**, **privacidad diferencial** con mecanismo de Laplace `Lap(Δf/ε)` y composición | Contar clases → generalizar → `k` alcanzado; DP: sensibilidad `Δf` → escala `b = Δf/ε` → ruido sembrado | `ε > 0`; sensibilidad bien calculada; datos discretos y registros independientes | k-anonimato: toda clase tiene `≥ k` registros; DP: razón de densidades `≤ e^ε` para entradas vecinas; error esperado `b`; simulación sembrada | Clases de equivalencia; densidad de Laplace | G. **Aviso fijo:** pedagógico, no garantiza privacidad real |

### 4.11 Teoría de la información

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| Entropía, conjunta, condicionada, **información mutua**, `D(p‖q)`, entropía cruzada `H(p,q) = H(p) + D(p‖q)` | Tabla de probabilidades → `log₂` → suma | Probabilidades normalizadas; `0·log 0 = 0`; `D` infinita si `q = 0` donde `p > 0` | `H = log₂ N` en el uniforme; `I ≥ 0`; regla de la cadena `H(X,Y) = H(X)+H(Y\|X)`; cambio de base | Barras y diagrama de Venn de entropías | G (transversal) |
| **Huffman, Shannon-Fano y Kraft**: árbol, longitud media `L̄`, eficiencia, ¿es prefijo? | Ordenar → fusionar los dos menores → asignar bits → `L̄` | Fuente sin memoria; los empates dan varios óptimos con la misma `L̄` | `H ≤ L̄ < H+1`; Kraft con igualdad; decodificar y recuperar el mensaje | Árbol de Huffman | G, prioridad media |
| **Capacidad de canal**: BSC `1−H₂(p)`, BEC `1−ε`, Shannon-Hartley `B·log₂(1+SNR)` | Pasar SNR de dB a lineal con la **convención declarada** (§5.11) → fórmula | Canal sin memoria; ruido gaussiano blanco aditivo | `C(0,5)=0`; tasa de un código `k/n ≤ C` | `C(p)` | G |
| Entropía de contraseñas y espacio de claves `2ᵏ`; cumpleaños sobre hashes `2^(n/2)` (la fórmula de colisión `1 − Π(1 − i/m)` vive en el bloque 9; aquí solo el coste en bits) | Contar → logaritmo → conversión a tiempo | Elección uniforme (las contraseñas humanas no lo son: se avisa de la sobrestimación) | `log₂` por dos caminos; simulación del cumpleaños | — | G |

### 4.12 Cadenas de Markov, MDP y refuerzo

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Cadena de Markov**: matriz `P` por filas, `π·Pⁿ`, distribución estacionaria `π·P = π` con `Σπ = 1`, clasificación de estados, tiempo de absorción `N = (I−Q)⁻¹` | Construir `P` → resolver el sistema → comprobar. Absorción por `(I−Q)⁻¹` si hay estados absorbentes | `P` estocástica por filas; irreducible y aperiódica para estacionaria única y convergencia | `Pⁿ` converge a filas iguales a `π`; autovector izquierdo de autovalor 1; simulación sembrada | **Grafo de estados** con probabilidades | G (hueco conocido de Probabilidad) |
| **MDP** `(S,A,P,R,γ)`: leer y definir; **evaluación de política** `v = (I−γP)⁻¹R`; **ecuación de optimalidad**; iteración de valor y de política | Una ecuación de Bellman por estado. Sistema lineal si hay política fija y `S` pequeño; iteración en otro caso (se justifica) | `γ < 1` o episodio finito (contracción, existencia y unicidad); modelo conocido | **Residuo de Bellman 0** al sustituir; iteración frente a solución directa; la mejora de política es monótona | Gridworld con política y valores | G (RL, tema 4) |
| **Monte Carlo, TD(0), SARSA y Q-learning** a mano sobre un episodio dado | Retornos hacia atrás → actualizar la tabla → política ε-greedy; `Q ← Q + α[r + γ·max Q(s′,·) − Q]` frente a SARSA (acción realmente tomada) | `α ∈ (0,1]`; visitas infinitas para converger; off-policy frente a on-policy | Con `α = 1/N`, MC es la media muestral; Q-learning converge a la solución óptima de Bellman; simulación sembrada | Tabla `Q` | G |
| **Bandidos**: estimación incremental `Qₙ₊₁ = Qₙ + (R−Qₙ)/n`, ε-greedy, UCB `Q + c·√(ln t/N)` | Tabla de `Q` y `N` por brazo → elegir → actualizar | Recompensas estacionarias (si no, `α` constante) | `Qₙ` es la media muestral; ley de los grandes números | Recompensa media frente al tiempo | G |
| Gradiente de política (REINFORCE) y actor-crítico | `∇log π = 1ₐ − π` (softmax) → multiplicar por `G − b` → ascender | El baseline no depende de la acción | Diferencias finitas de `J` en un MDP de un paso; media muestral | — | G, prioridad baja |

### 4.13 Optimización y aprendizaje automático

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Descenso de gradiente** (GD, SGD, mini-lotes, momento, Adam) a mano; elegir `η`; divergencia | `∇J` por la regla de la cadena → actualizar → parar con `norma(∇J) < tol`. En una cuadrática, `η < 2/L`; el mal condicionamiento ralentiza | `J` diferenciable; convexa y con gradiente `L`-Lipschitz con `η ≤ 1/L` para garantía; variables escaladas | **Gradiente por diferencias finitas centrales**; el óptimo coincide con las ecuaciones normales `∇J = 0` | **Trayectoria sobre curvas de nivel** y `J(θₖ)` | G (4 asignaturas) |
| **Regresión** múltiple, polinómica y regularizada: ecuaciones normales, `R²`, ridge `(XᵀX+λI)⁻¹Xᵀy`, lasso por soft-threshold, validación cruzada | Construir `X` (columna de unos) → resolver → residuos → `R² = 1 − SSR/SST`; ridge si hay multicolinealidad | `XᵀX` invertible; errores de media cero y varianza constante para los intervalos | `Xᵀe = 0`; contraste con GD y con SVD (pseudoinversa) | Ajuste, residuos y curva de validación | G |
| **Regresión logística y softmax**: `σ(z)`, log-loss, gradiente `Xᵀ(p−y)`, frontera, odds | `z → σ(z) →` pérdida → gradiente → un paso de GD | Clases no perfectamente separables (si lo son, `w → ∞` sin regularizar) | Diferencias finitas; `Σ softmax = 1`; Newton-IRLS | Frontera en el plano | G |
| **Métricas de clasificación**: confusión, exactitud, precisión, exhaustividad, F1, especificidad, ROC y AUC | Contar VP, FP, FN, VN → fórmulas | Positivo definido; con clases desbalanceadas la exactitud engaña (se avisa) | `VP+FP+FN+VN = N`; AUC por trapecios = probabilidad de ordenar bien un par (Mann-Whitney) | Matriz y curva ROC | G (la ROC se comparte con el bloque 16) |
| **k-medias** (Lloyd a mano), **EM** de mezcla gaussiana 1D, BIC, silueta | Iniciar → asignar → recalcular → repetir; EM: responsabilidades → parámetros → `log L` | `k` fijo; el resultado depende de la inicialización | SSE decrece; `log L` no decrece; varios arranques sembrados; silueta en `[−1,1]` | Clústeres y centroides | G |
| **Árboles de decisión y ensamblados**: entropía, Gini, ganancia de información, mejor división | Impureza del padre → de los hijos ponderados → ganancia → máximo | Umbrales ordenados o categorías; independencia de los clasificadores del ensamble (**rara vez cierta: se avisa**) | Ganancia `≥ 0`; entropía 0 en nodo puro y `log₂ k` en el uniforme | Árbol | G |
| **PCA y SVD**: centrar → covarianza → autovalores → varianza explicada → proyección; error de reconstrucción = suma de autovalores descartados | Diagonalización ortogonal (teorema espectral, bloque 3) o SVD de `X` centrada; el método se justifica por la simetría de la covarianza | Datos centrados; escala (PCA depende de ella); autovalores distintos para componentes únicos | `VᵀV = I`; `Σλ` = traza; PCA por SVD da los mismos ejes salvo el signo | Datos proyectados y ejes | G |
| **Redes neuronales a mano**: propagación (ReLU, sigmoide, tanh), pérdida MSE o entropía cruzada, **retropropagación** capa a capa (`δ`, `∂J/∂W = δ·aᵀ`), softmax + entropía cruzada (`p−y`), número de parámetros; convolución `O=⌊(W−K+2P)/S⌋+1`, Batch Norm, dropout `1/(1−p)`; **atención** `softmax(Q·Kᵀ/√d)·V`; RNN y LSTM en 2-3 pasos | Tabla de `z` y `a` hacia delante → `δ` de salida → `δ` hacia atrás → actualizar | Activaciones diferenciables (convención de ReLU en 0 declarada); dimensiones coherentes; pérdida adecuada a la tarea | **Gradiente numérico por diferencias centrales**; la pérdida baja tras un paso con `η` pequeño; filas de la atención suman 1; parámetros contados también como producto de dimensiones | Grafo de la red; mapa de calor de pesos | G |
| SVM de 3-4 puntos (KKT) | Identificar soporte → sistema de restricciones activas → `w, b` → margen `2/norma(w)` | Datos separables o parámetro `C`; kernel semidefinido positivo | KKT `αᵢ(yᵢ(wᵀxᵢ+b)−1)=0`; signo de `f(xᵢ) = yᵢ` | Margen y soportes | G, prioridad baja |

### 4.14 Matemáticas financieras

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Interés** simple y compuesto, capitalización continua `C₀·e^{rt}`, TAE, regla del 72 | Elegir la composición → fórmula → despejar la incógnita (tiempo con `ln`) | Tasa constante; **base de días** (act/365, 30/360) y nominal frente a efectiva declaradas | Capitalizar mes a mes frente a la fórmula; el límite `m → ∞` tiende a `e^{rt}`; descontar y capitalizar devuelve el inicial | Curvas de capital | G |
| **VAN, TIR, anualidades y amortización** | Línea temporal → factor de descuento → suma. La TIR por **bisección** (hay cambio de signo acotado) con la gráfica de `VAN(r)`; Newton solo si la derivada no se anula | Un solo cambio de signo ⇒ TIR única (**Descartes**); `r > −1` | `VAN(TIR) = 0` recalculado; intereses + capital = total pagado; segundo método de raíces | `VAN(r)` y tabla de amortización | G |
| **Bonos**: precio, duración de Macaulay y modificada, convexidad (la YTM no se resuelve: es implícita y sin cerrar) | Flujos → descontar → `P`; `∂P/∂y` derivando el sumatorio | Curva de tipos plana; sin impago; fechas regulares | `P` a la par cuando `y` = cupón; derivada numérica de `P(y)` frente a la duración; monotonía | `P(y)` | G |
| **Futuros** `F = S₀·e^{rT}` y arbitraje | Capitalizar el spot → comparar con el mercado → estrategia | Sin fricciones; tasa constante | Valor inicial del contrato 0; la cartera replicante da beneficio 0 | Diagrama de beneficio | G |
| **Opciones**: payoff, **árbol binomial CRR** (`u = e^{σ√Δt}`, `d = 1/u`, `q = (e^{rΔt}−d)/(u−d)`), americanas, paridad put-call | Árbol de precios → payoffs en las hojas → retroceder → comparar con el ejercicio inmediato | `0 < q < 1`, es decir `d < e^{rΔt} < u` (no arbitraje); mercado completo; sin dividendos | Paridad `C − P = S₀ − K·e^{−rT}`; réplica con `Δ` acciones y `B` bono; convergencia a Black-Scholes con `n` grande | **Árbol dibujado** | G |
| **Black-Scholes-Merton**, griegas, volatilidad implícita | `d₁ → d₂ → Φ` (normal acumulada del bloque 6). Implícita por Newton sobre la vega, que es siempre positiva y garantiza unicidad | Movimiento browniano geométrico; `σ` y `r` constantes; europea; sin dividendos | Paridad; límite del árbol; `Δ` por derivada numérica; `C` monótona en `σ` | Precio y griegas frente a `S` | G |
| **Monte Carlo** de derivados: `S_T = S₀·exp((r−σ²/2)T + σ√T·Z)`, error estándar, intervalo | Generar `Z ~ N(0,1)` con semilla → `S_T` → payoff → media descontada y error | `Z` independientes; semilla explícita; `N` grande | El precio MC cae en el intervalo del de Black-Scholes; error proporcional a `1/√N` | Histograma de payoffs | G |
| **Markowitz**: `μₚ = wᵀμ`, `σₚ² = wᵀΣw`, mínima varianza `Σ⁻¹1/(1ᵀΣ⁻¹1)`, frontera eficiente, Sharpe, VaR gaussiano | Lagrangiano con `wᵀ1 = 1` y `wᵀμ = m` → **sistema KKT lineal**. Si no se permiten cortos es programación cuadrática: **no se resuelve, se avisa** | `Σ` definida positiva (Sylvester); cortos permitidos | `wᵀ1 = 1`; `∇L = 0`; contraste con GD o con muestreo aleatorio de pesos (ninguno mejora la frontera) | Frontera eficiente | G |

### 4.15 Señales y sistemas deterministas

Convenios de Señales y Sistemas (§5.11): frecuencia ordinaria `f`, `X(f) = ∫x(t)·e^{−j2πft}dt`, `sinc(x) = sin(πx)/(πx)`, `Π` de ancho 1, `Λ` de ancho 2, frecuencia normalizada `F = f/f_m` con DFT `X[k] = X(F)` en `F = k/N`, `p_L[n]` causal de `L` muestras. La lectura de espectros, el muestreo, la modulación y el diseño de filtros **no** están aquí (§16). Recuentos sobre ≈ 29 pruebas leídas (±2).

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Biblioteca de señales** `δ, u, Π, Λ, sinc, p_L[n]`, «diente»; transformaciones del eje (desplazar, escalar, reflejar); descomponer una figura en pulsos | Leer la figura por tramos → `x(t) = ΣA_i·Π((t−t_i)/T_i)` → comprobar los extremos de cada tramo → energía | Convención de `Π` en los saltos (no afecta a `E` ni a la TF) | Evaluar en malla frente a los datos; las 3 descomposiciones válidas de P1-2025 dan la misma TF tras periodificar | Señal y sus pulsos | **E** transversal (base de todo) |
| **Convolución analógica por tramos** (`Π`, `Λ`, `e^{−t/T}u(t)`, deltas, ventana móvil) | Reflejar y desplazar `h(t−λ)`; **puntos de ruptura = sumas de extremos**; integrar por intervalo; continuidad en las rupturas. Descomposición en deltas si hay solape; TF si `h` es un producto sencillo (se justifica) | Soporte compacto o `h ∈ L¹`; asociatividad solo si existen las intermedias | `∫y = ∫x·∫h`; duración `D_x + D_h`; valor y derivada en las rupturas; malla fina o FFT con relleno; vía TF | **`h` reflejada deslizándose** y `y(t)` | **E 14/29** (P1 en 6 de 8) |
| **Convolución digital** (`aⁿu[n]`, `p_L[n]`, suma móvil) y **regímenes** | Tabla de solapes; longitud `L₁+L₂−1`; tres tramos (antes, transitorio, régimen) con sumas geométricas; vía z | `abs(a) < 1` para la suma infinita | `Σy = Σx·Σh`; `conv` numérica; DFT con `N ≥ L₁+L₂−1` | `stem` | **E 9/29** |
| **Periódicas**: periodo (mcm), señal base, `c_k`, `X(f) = Σ c_k·δ(f−k f₀)`, armónicos nulos por paridad (`1−(−1)^k`), `y = x*h` con paso bajo | `c_k = (1/T₀)·X_b(k/T₀)`; el desplazamiento aporta fase; **método de la señal base + TF** en vez de la integral de periodo cuando los pulsos son básicos (se dice por qué) | Periodicidad exacta; pulsos sin solape entre periodos; TF en sentido de distribución | Otra señal base da los mismos `c_k`; suma parcial frente a la figura; Parseval `P = Σabs(c_k)²` | Señal y **espectro de líneas** | **E 18/29** (8 de 10 segundos parciales) |
| **Energía, potencia y Parseval**: clasificar (energía finita, potencia finita, ninguna), `E`, `P`, sinusoide `A²/2`, salida de un sistema (eco, rectificador de media onda) | `E = ∫abs(x)² = ∫abs(X)²`; `P = (1/T)∫abs(x)² = Σabs(c_k)²`; suma de potencias solo entre componentes ortogonales | Componentes de frecuencias distintas para sumar potencias | **Tiempo y frecuencia** (dos caminos); `E_y = E_x(1+a²)` para `y = x + a·x(t−T)` sin solape | Señal y densidad | **E 12/29** |
| **Correlación y densidad espectral deterministas**: `r_x = x*x*(−t)`, `r_xy`, `S_x = abs(X)²`, `S_y = S_x·abs(H)²`, periódicas, exponenciales complejas, retardo y atenuación por el pico de `r_yx` | `r_xy = A·B*·e^{j2πfτ}` si `f=f′` y 0 si no; `r_yx = r_x*h`; Wiener-Khinchin | Tipo energía o potencia para elegir la definición; conjugación con señales complejas | `r = TF⁻¹{S}`; `r(0) = E` (o `P`) y `abs(r(τ)) ≤ r(0)` (Schwarz); paridad; `xcorr` por FFT | `r(τ)` y `S(f)` | **E 12/29** |
| **TF de secuencias (DTFT)**: `p_L[n]`, `aⁿu[n]`, `δ[n−n₀]`; `abs(H(F))²`; salida a `A + B·cos(2πFn)`; modulación `(−1)ⁿ` | `P_L(F) = sin(πLF)/sin(πF)·e^{−jπ(L−1)F}` (máximo `L` en `F=0`, ceros en `k/L`); `abs(1/(1−a·e^{−j2πF}))² = 1/(1+a²−2a·cos 2πF)`; periodicidad 1 | Secuencia absolutamente sumable (o distribuciones para sinusoides) | Suma truncada; DFT con relleno muy largo; transformada inversa; Parseval `Σabs(x)² = ∫₀¹abs(X)²dF`; hermiticidad | **Módulo y fase en `[−1,1]`** | **E 20/29** (el más repetido) |
| **DFT**: propiedades, relleno de ceros, **circular frente a lineal** (`N ≥ L₁+L₂−1`), aliasing temporal, retardo circular `e^{−j2πk n₀/N}`, simetría hermítica `X[N−k] = X*[k]`, `X[0] = Σx`, `y[0] = (1/N)·ΣY[k]`, correlación por DFT | Elegir `N` mínimo por la longitud de la convolución lineal; con `N` menor, las primeras muestras se solapan | `N ≥ L` en cada señal; señal real ⇒ simetría hermítica | `conv` directa; `Σabs(x)² = (1/N)·Σabs(X)²` | `x[n]` y `abs(X[k])` con `k > N/2` como frecuencia negativa | **E 8/29** |
| **Transformada z ampliada: eco, reverberación e inverso**: `H(z) = 1 + a·z^{−L}`, `1/(1−a·z^{−L})`, ecualizador, inverso `b = −a` | `1 + a·z^{−L}` tiene `L` ceros en `abs(z) = abs(a)^{1/L}` y un polo de orden `L` en 0; `abs(H(F))² = 1+a²+2a·cos(2πLF)`; inverso causal `h₂ = Σbᵏδ[n−kL]` | Causalidad del inverso; `abs(b) < 1`; si `abs(a) > 1` el inverso causal es inestable | La cascada devuelve `z = x`; recursión de los primeros términos; ceros con las raíces del polinomio | Plano z con polos y ceros, y `abs(H(F))` | **E 8/29** |

La **TF de periódicas como deltas** exige que el motor maneje **áreas de delta** (§5.1), no solo funciones.

### 4.16 Detección y estimación

Todo este bloque es **G**: Tratamiento de la Señal no tiene exámenes en la carpeta, solo guía (5 temas, 60 h de dedicación: T1 10 h, T2 12 h, T3 15 h, T4 11 h, T5 12 h) y bibliografía estándar. Si el usuario aporta exámenes, hay que revisar las prioridades.

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Matriz de correlación** `R = E[x·xᴴ]` (Toeplitz hermitiana) de AR(1), MA(q) o sinusoide en ruido blanco; semidefinida positiva | `r[−k] = r*[k]`, `r[0] ≥ abs(r[k])`; salida `r_y = r_x*h*h*[−n]`; **PSD teórica** `S(F) = Σ r[k]·e^{−j2πFk}` (AR(1): `σ²/abs(1−a·e^{−j2πF})²`) y `S_y = S_x·abs(H)²` (D12) | WSS; momentos de segundo orden finitos; ergodicidad si se estima de una realización | Muchas realizaciones sembradas y `R` empírica; autovalores `≥ 0`; potencia `r[0] = ∫₀¹ S dF` (tiempo y frecuencia). El periodograma, Welch y la ergodicidad visual son de SIGNALS_LAB §14.4 y §17 | Mapa de `R` | G |
| **Detección**: `H₀: x = w` frente a `H₁: x = s + w`; razón de verosimilitudes, **MAP** (`γ = P(H₀)/P(H₁)`), Bayes y **Neyman-Pearson** (fijar `P_FA` y maximizar `P_D`); señal conocida `T = sᵀx`, `d² = sᵀs/σ²`, `P_D = Q(Q⁻¹(P_FA) − d)` | Si hay a priori y costes: Bayes o MAP; si solo se fija `P_FA`: NP (se dice por qué). `L(x) = p(x\|H₁)/p(x\|H₀) ≷ γ` | Densidades conocidas; muestras independientes (si no, covarianza y blanqueado) | **Monte Carlo sembrado** (tasas empíricas); el punto está sobre la ROC; el filtro adaptado es un caso particular | **Curva ROC** y las dos densidades con el umbral | G (T2, 12 h) |
| **Estimación**: sesgo, varianza, **información de Fisher** `I(θ) = −E[∂²ln p/∂θ²]`, **cota de Cramér-Rao** `Var ≥ 1/I(θ)`, eficiencia, MVUE; media de una gaussiana, DC en ruido blanco, amplitud de una sinusoide; versión vectorial | Log-verosimilitud → derivadas → `I`; eficiente si `∂ln p/∂θ = I(θ)·(g(x)−θ)` | Condiciones de regularidad (soporte independiente de `θ`, derivadas bajo la esperanza); estimador insesgado | Varianza empírica sobre muchas simulaciones **siempre `≥` cota** | Varianza frente a cota | G (T3, 15 h) |
| **ML, MAP y MMSE**; gaussiano conjunto `θ̂ = m_θ + K_θx·K_x⁻¹(x−m_x)` con error `K_θ − K_θx·K_x⁻¹·K_xθ` | ML maximiza `ln p(x\|θ)`; MAP añade `ln p(θ)`; MMSE es la media a posteriori; en gaussiano MAP = MMSE | A priori propia; conjuntamente gaussianas | Ortogonalidad `E[(θ−θ̂)·xᵀ] = 0`; ECM por simulación | Verosimilitud y posterior | G |
| **Filtro de Wiener**: `R·w = p` (Wiener-Hopf), `J_min = σ_d² − pᴴw₀`; mínimos cuadrados `w = (XᵀX)⁻¹Xᵀy`; predicción por Yule-Walker | Principio de ortogonalidad `E[e·x*] = 0`; `R` y `p` desde correlaciones | `R` definida positiva; WSS; `X` de rango completo | Residuos ortogonales a las columnas de `X`; `J(w) ≥ J_min` para `w` perturbado; con muchos datos, mínimos cuadrados ≈ Wiener | **Superficie de error** y sus elipses | G (T4, 11 h) |
| **Descenso de gradiente sobre la superficie de error**: `w(k+1) = w(k) + μ(p − R·w(k))`, `0 < μ < 2/λ_max`, `τᵢ = −1/ln(1−μλᵢ)` | Diagonalizar `R = QΛQᴴ`; coordenadas del error `vᵢ(k) = (1−μλᵢ)ᵏ·vᵢ(0)`; dispersión `λ_max/λ_min` fija la velocidad | `R` definida positiva; `μ` constante | Simulación frente a la fórmula modal; gradiente de `J` por diferencias finitas | Trayectoria sobre las elipses | G (T5) |
| **LMS y NLMS**: `w(n+1) = w(n) + μ·e*(n)·x(n)`; convergencia en media `0 < μ < 2/λ_max`, práctica `0 < μ < 2/tr(R)`; desajuste `M ≈ μ·tr(R)/2`; NLMS `0 < μ̃ < 2` | Ecuación en diferencias de `E[w(n)]`; `μ` es un compromiso entre rapidez y desajuste | Independencia entre `x(n)` y `w(n)`; `R` estacionaria | 100 a 1000 realizaciones sembradas: `E[w(n)]` y `J(n)` frente a la teoría; con `μ` sobre la cota **se ve la divergencia** | **Curva de aprendizaje** | G (T5) |

### 4.17 Fasores y polarización

Respaldo **E** muy fuerte: Electromagnetismo Aplicado y Fotónica (EAFO) escribe todo el examen en notación fasorial (3 problemas de 10 apartados por final, 2020-2025, reevaluaciones y parciales). Lo circuital (impedancias, líneas, Smith) **no** está aquí (§16).

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Fasor ↔ tiempo**, suma de sinusoides de igual frecuencia, **problema inverso** («dados dos valores medidos con `8cos(2,4πt)+A·cos(2,4πt+φ₁)`, hallar `A` y `φ₁`» = módulo y argumento de una suma de fasores) | `x = Re[X·e^{jωt}]`; sumar fasores; volver al tiempo | Régimen senoidal permanente; lineal; **convención declarada** (coseno o seno, `e^{+jωt}` o `e^{−iωt}`, pico o eficaz) | Muestrear el dominio del tiempo y ajustar; resolver también con la convención contraria y comprobar que da el mismo resultado físico | **Diagrama fasorial** | **E** (~100 % de EAFO) |
| **Onda plana**: `k = nω/c`, `λ`, `v`, `η = η₀/n`, `H = (1/η)·k̂×E`, `⟨S⟩ = ½Re(E×H*) = abs(E)²/2η`, potencia captada `⟨S⟩·A` en un sensor circular o cuadrado (a veces desplazado) | De fasores a potencia media; área del sensor por integral | Onda plana uniforme; medio lineal, homogéneo e isótropo; incidencia perpendicular al sensor | Promediar `S(t)` numéricamente en un periodo; `∇×E = −jωμH`; dos expresiones de `⟨S⟩` | Campo y sensor | **E** |
| **Raíz compleja con rama principal** y **medios con pérdidas**: `ε̃ = ε′(1−j·tanδ)`, `ñ = √ε̃_r`, `α`, `β`, buen dieléctrico `α ≈ (β/2)·tanδ`, buen conductor `α ≈ β ≈ √(ωμσ/2) = 1/δ_p`, neper a dB (×8,686), espesor para atenuar `X` dB | Calcular **siempre el complejo exacto** y comparar con la aproximación. Se comprueba la **condición de aplicabilidad** (`σ/ωε ≪ 1` o `≫ 1`). Rama elegida con `Re ≥ 0` para propagación (se explica) | `σ/ωε` en el régimen que justifica la aproximación; desarrollo binomial de `√(1−jx)` válido | **Error relativo** de la aproximación frente al exacto (el enunciado pide «justificar que se puede usar…») | Atenuación frente a la profundidad | **E ~12/17** |
| **Polarización**: clasificar (lineal, circular izquierda o derecha, elíptica), relación axial, ángulo del eje `tan2ψ = 2·A_x·A_y·cosδ/(A_x² − A_y²)`, campos `E` y `H` de la misma onda | **Semiejes = valores singulares** de la matriz real `[Re E \| Im E]`; orientación = vector singular izquierdo (SVD de 2×2, bloque 3) | Onda plana transversal | AR por dos fórmulas (`tanχ` y razón de semiejes); muestrear `E(t)` y medir; esfera de Poincaré con `abs(S) = S₀` si está totalmente polarizada | **Elipse de polarización** y esfera de Poincaré | **E ~10/13** (el tipo más específico de EAFO) |
| **Cálculo de Jones**: retardadores `R(−φ)·diag(1, e^{−jδ})·R(φ)` (λ/4, λ/2, retardo arbitrario), **cascada**, polarizador (Malus `cos²θ`), **diseñar una cadena** que produzca un estado (AR = 3,73 con eje mayor a 45°: resolver `φ₁` y `φ₂`) | Producto de matrices 2×2 complejas; vector propio; ecuaciones trigonométricas para `φ`. Se explica por qué la cascada y no un solo retardador | Retardador sin pérdidas ⇒ matriz **unitaria**; ejes y retardo dados | Unitariedad: conserva `abs(E)²`; potencia final; muestreo de `E(t)` | Elipse antes y después de cada elemento | **E ~10/13** |
| **Desajuste de polarización** `PLF = abs(ê₁·ê₂*)²` | Producto escalar hermítico de vectores de Jones | Vectores normalizados | Malus como caso particular | — | G (Telecomunicación espacial) |
| **Fresnel, Brewster y reflexión total (D12)**: `r_s, r_p, t_s, t_p`, `tanθ_B = n₂/n₁`, `senθ_c = n₂/n₁`, onda **evanescente**, `R = abs(r)²` y `T` | Snell → `cosθ_t` (complejo si hay reflexión total, rama declarada) → coeficientes → potencias. Aviso: `T ≠ abs(t)²` salvo en el mismo medio (factor `n₂·cosθ_t/(n₁·cosθ_i)`) | Interfaz plana; medios no magnéticos; sin pérdidas (con pérdidas, `ñ` complejo y exacto frente a aproximado como en la fila de medios con pérdidas) | `R + T = 1`; `r_p(θ_B) = 0`; incidencia normal `r = (n₁−n₂)/(n₁+n₂)` | `R(θ)` y `T(θ)` con Brewster y ángulo crítico marcados | **E ~11/13** (EAFO) |
| **Película delgada y multicapa (Airy) (D12)**: matriz de transferencia 2×2 por capa con `δ = k₀·n·d·cosθ`, reflectancia, antirreflejante λ/4 (`n_f = √(n₁·n₂)`) | Producto de matrices 2×2 complejas de las capas → `r, t, R` | Capas planas; `n` dado a la longitud de onda; sin pérdidas (matrices unitarias en el caso ideal) | `R + T = 1`; `det = 1` por capa; una capa reproduce Fresnel; resonancias de Fabry-Perot | `R(λ)` o `R(d)` | **E** dentro de EAFO (≈ 11/13), prioridad media |

Quedan fuera, por ser de otro laboratorio: impedancias, potencia compleja de circuitos, líneas, Smith y guías (CIRCUITS_LAB). Fresnel y multicapa entran por D12 (filas siguientes); antenas y enlace van al bloque 18 y las órbitas al 19.

### 4.18 Campos y ondas: electrostática por regiones y verificación de Maxwell

Respaldo **E**: Electromagnetismo (9 exámenes revisados; el mismo problema de las **tres esferas aparece 5 veces**) y EAFO. Los operadores ∇ en curvilíneas viven en §4.4.

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Carga total con densidad no uniforme**: `λ = a·sen(θ/2)` en un arco, `ρ = a·r` en un cilindro anular, `ρ = a·r²`, `σ = a·x²` | Parametrizar el elemento (`dl = R·dθ`, `dS`, `dτ` con jacobiano) → integrar → resultado en función de `a` | Densidad acotada; elemento bien orientado | **Análisis dimensional de `a`**; límite de densidad uniforme; integración numérica | Elemento y densidad | **E 8/9** |
| **Gauss con simetría**: `Q_enc(r) = ∫ρ dτ`, `E(r)` por regiones, `V(r) = −∫E dr` con **empalme** de `V` y `V(∞) = 0`; cilindros coaxiales; esfera con `ρ = a·rⁿ` y conductor | Elegir la superficie gaussiana **justificando la simetría** (esférica, cilíndrica o plana); `∮E·dS = Q_enc/ε₀` por región; empalmar | Simetría razonada (no solo dicha); `L ≫ R` en el cilindro; **`V(∞)=0` solo si la distribución está acotada** (cilindro infinito: otra referencia, se avisa) | `∇·E = ρ/ε₀` en esféricas o cilíndricas; `E = −dV/dr`; energía por dos fórmulas (`½ΣQV` y `(ε₀/2)∫E²`) | **`E(r)` y `V(r)` por tramos** con la continuidad visible | **E 9/9** |
| **Conductores concéntricos y toma a tierra**: cargas inducidas (`−Q₁` en `R₂`, `Q₁+Q₂` en `R₃`), `V` en cada radio, **conectar a tierra** (`V=0` ⇒ nuevo reparto: sistema lineal 2×2), energía | Cargas inducidas por Gauss en el conductor; con tierra, plantear `V=0` y resolver el sistema | Equilibrio electrostático; conductores sin campo interior | Suma de cargas inducidas = carga neta; energía por dos caminos | Reparto de cargas por superficie | **E 9/9** |
| **`V` dado ⇒ `E`, `ρ`, flujo**: `V = x²+y²+4`, `V = α·x³+β·y²+2`; `E = −∇V`, `ρ = −ε₀∇²V`, flujo por las 6 caras de un cubo, carga = `ε₀·flujo` | Gradiente y laplaciano; flujo cara a cara **o** por Gauss (`∭∇·E dV`). Las dos vías son el propio control | `V` de clase C² | **Cara a cara frente a divergencia** | Cubo con las normales | **E 5/5 parciales** |
| **Maxwell diferencial**: comprobar que `(E,B)` cumplen las ecuaciones sin fuentes y **hallar `c = ω/k = 1/√(μ₀ε₀)`**; `E₀/B₀ = c`; **completar la tercera componente** con `∇·B = 0` (integrar `∂B_y/∂y = −∂B_x/∂x` con función de integración); `E = E₀·sen(πx/a)·cos(ωt−βz)·ŷ` ⇒ `H`, densidad de energía y potencia por tres planos | Derivar con la regla de la cadena en dos variables → sustituir → igualar. **La constante de integración es cero «en ausencia de campos estáticos»: hipótesis explícita** | Medio sin fuentes y sin campos estáticos | Sustituir las cuatro ecuaciones y `∇²E = μ₀ε₀·∂²E/∂t²`; `∇·(∇×F) = 0` como control de consistencia | Campo en dos instantes | **E** (2/4 finales y ~12 enunciados de capítulo) |
| **Ecuación de onda y perfiles arbitrarios**: `f(t − k̂·r/v)`, `sech²`, `e^{−(α·x−β·t)²}`; dirección (signo del argumento), `v = ω/abs(k)`, `α/β = 1/c`, energía por área `∫S dt` (`∫e^{−ax²} = √(π/a)`, `∫sech² = tanh`), **trazas en varios sensores** con retardos y atenuaciones | Reconocer el argumento `f(t − k̂·r/v)`; **verificar por sustitución**, no resolver la EDP (§17) | Medio homogéneo y sin dispersión; incidencia oblicua con `k̂` de varias componentes | Sustituir en la ecuación de onda por la regla de la cadena; energía por Simpson | **Trazas en cada sensor**, con el instante de pico | **E ~6/17** |
| **Coulomb, Biot-Savart y Ampère por integración (D12)**: `E` de hilo, anillo, disco y arco; `B` de espira y segmento; Ampère con simetría; **polígono de `N` lados → círculo** (límite) | Parametrizar la fuente → vector `r−r′` → integrar por componentes (la simetría anula unas) → resultado en el eje o en el punto | Distribución acotada; simetría razonada para Ampère; punto de campo fuera de la fuente | Límite `z ≫ R` = carga o dipolo puntual; Gauss o Ampère como 2.º camino; integración numérica; `N → ∞` reproduce el círculo | Campo sobre el eje y en 2D; polígono → círculo | **E** (Electromagnetismo; 9/9, 4/4, ~7/9 y 5/6 según el tema del grupo) |
| **Condensadores y dieléctricos (D12)**: `C = Q/V` plano, esférico y cilíndrico; dieléctrico por capas (serie y paralelo), `D = ε·E`, polarización y cargas ligadas, energía `½CV²`, fuerza | Gauss con `D` por regiones → `V` → `C`; capas: continuidad de `D` normal y de `E` tangencial | Equilibrio electrostático; bordes despreciados (`L ≫ d`) | `C` por dos caminos (`Q/V` y energía `2W/V²`); límite de capa fina; análisis dimensional | `E(r)` y `D(r)` por capas con saltos visibles | **E** (mismo grupo de recuentos) |
| **Inducción y Poynting (D12)**: Faraday `ε = −dΦ/dt` con signo de Lenz, inductancia mutua, `S = E×H`, balance de energía de Poynting | Flujo con la orientación elegida → derivada → signo por Lenz; Poynting: `∮S·dA = −d(energía)/dt − P_Joule` | Orientación de la superficie coherente con la del contorno (declarada); campos en régimen cuasiestático | Ley de Lenz como control de signo; energía por dos caminos; unidades (V = Wb/s) | Espira, flujo y fem frente al tiempo | **E** (mismo grupo de recuentos) |
| **Antenas y enlace (D12)**: directividad y ganancia, **Friis** `P_r = P_t·G_t·G_r·(λ/(4πR))²`, balance de enlace en dB, ruido de sistema `T_sys`, `G/T`, factor de array de `N` elementos | Lineal → dB con la **convención declarada** (§5.11) → sumar términos → margen de enlace | Campo lejano; adaptación y polarización (PLF, bloque 17) declaradas; ruido blanco | Balance en lineal frente a dB; array con `N = 1` reproduce el elemento; el lóbulo principal tiene ancho `≈ λ/(N·d)` | Diagrama de radiación polar y balance en cascada | G (Telecomunicación espacial; antenas E débil), prioridad baja |

### 4.19 Física auxiliar: mecánica 1D con potencial, órbitas y termodinámica (opcional)

| Tipo de ejercicio | Pasos y por qué ese método | Hipótesis que se comprueban | Verificación (2.º camino) | Gráfica | Resp. |
|---|---|---|---|---|---|
| **Equilibrio y pequeñas oscilaciones desde `U(x)`** (fórmula o gráfica): equilibrios, estabilidad, rango de `E` para oscilar, `v_max = √(2(E−U_min)/m)`, `ω = √(U″(x₀)/m)`, periodo `T = 2∫dx/√(2(E−U)/m)` (impropia en los puntos de retroceso); `U` periódica `U₀/2·(1−cos(2πx/a))` ⇒ `ω = (π/a)·√(U₀/m)` por Taylor | `U′ = 0`; `U″ > 0` estable; Taylor de grado 2. La cuadratura para el periodo exacto; la armónica para el aproximado (se compara) | Fuerza conservativa 1D; `E` conservada; `U″ ≠ 0` (si es 0, orden superior) | **Integrar `m·x″ = −U′(x)` numéricamente** y medir el periodo frente a la cuadratura | **`U(x)` con niveles de `E`** y retrato de fases | **E ~12/15** |
| **Termodinámica del gas ideal** (**opcional**): `W = −∫p dV` con `p(V)` lineal, parabólico o `pV = cte`; `ΔU = n·C_v·ΔT`; **`T` máxima del proceso** (derivar `pV/nR`); `ΔS = n·C_v·ln(T_f/T_i) + n·R·ln(V_f/V_i)`; `ΔS` del universo con foco a `T_H`; rendimiento de un ciclo `A→B→C→A` | Integral 1D de `p(V)`; optimización 1D; logaritmos. Solo la verificación física es nueva | Gas ideal; proceso cuasiestático; `γ = C_p/C_v` dado; foco ideal | `ΔU` del ciclo = 0 y `ΣQ = ΣW`; **`S` es función de estado** (dos caminos reversibles distintos); desigualdad de Clausius | **Diagramas `p–V` y `T–S`** | **E 15/15**, pero **opcional**: se activa a petición; si el laboratorio se limita a matemática pura, queda como aplicación de la integral 1D |
| **Órbitas y visibilidad (D12)**: ecuación de **Kepler** `M = E − e·senE` (trascendente, §4.7), velocidad circular, `T² ∝ a³`, energía orbital, visibilidad esférica `cosθ = R/(R+h)` | Kepler por barrido de signo + Newton (con `0 ≤ e < 1`); energía `−GMm/2a` | Órbita ligada; dos cuerpos; Tierra esférica | Sustituir en `M = E − e·senE`; `e = 0` da el círculo; periodo por `T = 2π√(a³/GM)` | Órbita y huella de visibilidad | G (Telecomunicación espacial), prioridad baja |
| **Maxwell-Boltzmann, Planck y Stefan (D12, opcional)**: `f(v)`, `v_p`, `v_med`, `v_rms`; ley de Planck y `∫x³/(eˣ−1)dx = π⁴/15` ⇒ Stefan-Boltzmann | Integral gaussiana o gamma → momentos; cambio de variable `x = hν/kT` justificado (§5.6) | Gas clásico; equilibrio térmico | `∫f = 1`; `v_rms² = 3kT/m`; integral numérica de Planck | `f(v)` y espectro con el máximo de Wien | E en Física (parte térmica), **opcional** con la termodinámica |

---

## Capacidad implementada — ML-12 (2026-10-06)

**Aritmética entera con trazas** (`mathlab/enteros.py`, operación `modular`): Euclides extendido con la tabla de cocientes y la identidad de Bézout; inverso modular (o la razón por la que no existe: el mcd); potencia por cuadrados sucesivos con cada cuadrado y cada producto; congruencias lineales `a·x ≡ b (mod n)` con sus `mcd(a, n)` soluciones; teorema chino del resto también con módulos no coprimos (o «incompatible»); φ de Euler, orden multiplicativo, raíz primitiva y si ℤₙ es cuerpo. Segundo camino de cada resultado: Bézout sustituido, `a·a⁻¹ mod n = 1`, `pow`, sustitución en la congruencia, recuento por fuerza bruta. ~10 000 casos contra fuerza bruta sin discrepancias.

**Fracciones racionales multivariable** (`mathlab/racional.py`, operación `racional`): mcd de polinomios en varias variables (contenido y parte primitiva recursivos, sucesión de pseudorrestos primitivos), forma normal en términos mínimos —`(s² − a²)/(s − a) = s + a`—, ganancia, ceros y polos en la variable elegida: grado 1 y 2 con coeficientes simbólicos (raíz exacta del discriminante cuando es un cuadrado de polinomio, `K/(s(s+a))` → polos `0` y `−a`), polos complejos conjugados, cúbicas y bicuadradas numéricas por el buscador de ecuaciones. **Discusión por casos** del discriminante con el factor positivo apartado: en `1/(LCs² + RCs + 1)` decide el signo de `C·R² − 4·L`. Comprobado contra `sympy.cancel` en 144 funciones aleatorias y contra `sympy.gcd` en 145 pares.

**Motor lineal con el cuerpo como parámetro** (`mathlab/lineal.py`, operación `lineal`): Gauss-Jordan con cada operación de fila escrita, rango, determinante, inversa, núcleo y sistemas por Rouché–Frobenius sobre ℚ, ℂ (exacto, como ℚ(i)), ℝ (coma flotante con pivoteo parcial y tolerancia declarada; el sello baja a «solo numérico» y avisa de que el rango es una decisión numérica), GF(p) (`p` primo comprobado; GF(4) se rechaza) y GF(2ᵐ) (polinomio módulo comprobado irreducible; por defecto los primitivos habituales, p. ej. `x³+x+1`). Segundo camino: Laplace para el determinante (n ≤ 6), `A·A⁻¹ = I`, `A·v = 0` y sustitución. Contrastado con SymPy sobre ℚ y con recuento exhaustivo del núcleo sobre GF(2), GF(3) y GF(5), sin discrepancias. Ejemplo: `[[2,1],[1,2]]` tiene det 3 en ℚ y es singular en GF(3). ℂ contrastado con SymPy; ℝ con el rango exacto de SymPy sobre las mismas matrices racionales; GF(2ᵐ) con los axiomas de cuerpo y el recuento del núcleo.

**Distribuciones con área** (`mathlab/distribuciones.py`, operación `distribucion`): sumas de términos con `delta(…)`, sus derivadas `delta'(…)`, `delta''(…)` (hasta orden 4), `u(…)`/`escalon(…)` y funciones ordinarias, con posiciones **exactas** también irracionales (`δ(t² − 2)` está en `±√2`); `δ⁽ᵏ⁾(a·t − b) = δ⁽ᵏ⁾(t − b/a)/(aᵏ·|a|)`, cribado `f(t)·δ(t − t₀) = f(t₀)·δ(t − t₀)` y su forma de Leibniz para `δ⁽ᵏ⁾`; `δ(g(t)) = Σ δ(t − tᵢ)/|g′(tᵢ)|` sobre las raíces reales simples de `g` (raíz múltiple: no definida, se dice); `u(g(t))` no lineal como intervalos donde `g > 0`; productos de escalones y `δ·u` (si la delta cae en el salto hay que declarar `u(0)`); la derivada de `δ⁽ᵏ⁾` es `δ⁽ᵏ⁺¹⁾`; derivada de una función con saltos (cada salto es una delta cuya área es el salto); integrales que cruzan deltas (una delta justo en un límite exige declarar si cuenta entera, nada o la mitad); convolución con un tren finito de deltas; transformada de un tren `Σ δ(t − kT)` con la convención `f` u `ω` (§5.11). Segundo camino: `∫ D′ = incremento de D` contando las deltas, y en los tests una gaussiana estrecha integrada numéricamente (`δ(g)` y `δ′`). Rechaza con motivo `δ·δ`, `δ⁽ᵏ⁾(g)` con `k ≥ 1` y `g` no lineal, `δ(g)` en raíz múltiple y una delta dentro de otra función o dividiendo.

**Análisis dimensional** (`mathlab/dimensional.py`, operación `dimensional`): dimensiones como unidades (`V`, `kg*m/s^2`, `µF`, `kPa`) o en base (`[M L^2 T^-2]`), exponentes racionales (`sqrt(l/g)` es un tiempo); comprueba la homogeneidad diciendo qué suma o qué argumento de `exp`/`ln`/`sin` la rompe, y halla la dimensión que ha de tener una constante (`F = G·m1·m2/r²` → `[G] = M⁻¹·L³·T⁻²`), comprobada por sustitución. Siempre avisa: la homogeneidad es necesaria, no suficiente. Los nombres de varias letras con dimensión declarada (`Vcc`, `m1`, `Lb`) se leen enteros: el analizador acepta ahora `nombres=` declarados, y sin declararlos `xy` sigue siendo `x·y`.

**Verificador de gradientes** (`mathlab/gradientes.py`, operación `comprobar_gradiente`): diferencias centrales con extrapolación de Richardson (error O(h⁴)) en puntos sembrados, para una fórmula o una función caja negra; detecta picos (ReLU, `|x|`) comparando las pendientes laterales con dos pasos, y los marca «no fiables» en lugar de dar una falsa discrepancia. Batería: 10 funciones, 0 falsos positivos, y un error del 0,1 % en una componente se detecta en todas.

**Simulador sembrado de eventos** (`mathlab/eventos.py`, operaciones `markov` y `cola_mm1`): generador SplitMix64 propio (sin `random` en el dominio; reproduce el valor de referencia), cadenas de Markov con π **exacta** (sistema sobre ℚ con el motor lineal, comprobada `π·P = π`) y `p(n)` exacta, y simulación como segundo camino juzgada con su propio error por medias por lotes (0 de 80 semillas fuera de 4σ); bucle de eventos discretos reutilizable; M/M/1 con teoría y simulación; Monte Carlo con error típico. Usa la `semilla` de la petición (§5.9).

**Árboles y grafos** (`mathlab/grafos.py`, operaciones `grafo` y `huffman`): BFS, DFS, componentes, Dijkstra (comprobado con Bellman–Ford; pesos negativos rechazados y ciclos negativos detectados), Kruskal (comprobado con Prim), orden topológico (Kahn; un ciclo se informa); Huffman con `L = Σ nodos internos`, Kraft = 1 y `H ≤ L < H + 1`, y el árbol como datos dibujables (nodos con coordenadas y aristas rotuladas). Contrastado con Floyd–Warshall y con fuerza bruta del árbol generador mínimo.

**Convenciones declaradas** (`mathlab/convenciones.py`, operación `convencion`): cada cálculo se hace con la convención declarada y con la contraria, y se reconcilian: dB de amplitud o potencia (la trampa «100 veces inferior»: −40 dB o −20 dB, con aviso si la convención declarada no corresponde a la magnitud), valor eficaz o de pico (la potencia coincide), `s` con `n` o `n−1` (relación exacta), resto euclídeo o de C, base de logaritmos (bit, nat, hartley), `f` u `ω`, interés nominal o efectivo, y Chauvenet fijo `D_max = 3` iterativo frente al clásico (avisa cuando no coinciden).

**Contrato y plug-ins (§5.9), revisado:** un plug-in declara a qué operaciones se aplica y puede responder «no aplica»; un plug-in que coincide ya no asciende un resultado solo numérico a verificado (antes, registrar cualquier verificador convertía todo en «verificado»), y uno roto queda como aviso. `contract.validar_forma(resultado)` es la prueba de contrato de los laboratorios consumidores (versión, sello, tipos de paso, convenciones, traza serializable), y se pasa a **todas** las operaciones registradas. Encontró un fallo: la traza serializada perdía espacios finales y se rompía con saltos de línea, `|` o `=` en un campo; ahora los valores se escapan (traza versión 1.1, compatible).

## Capacidad implementada — ML-2, funciones y cálculo de una variable (2026-10-06)

Cada operación da pasos con «por qué», hipótesis comprobadas y un segundo camino independiente; las baterías contra SymPy están en los tests.

| Tipo (§15.1, Cálculo) | Operación | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Límites e indeterminaciones (T3); límites por Taylor **con parámetro** (8) | `limite` (`parametro`) | Término principal en la escala `c·w^p·e^(qw)·(ln w)^r` con `x = a ± 1/w`; cancelaciones por series de Laurent truncadas con coeficientes exactos (`√(x² + x) − x`, `1/x − 1/sen x`, `1^∞`, `0⁰`); con parámetro, los coeficientes que dependen de él se anotan y sus ceros dan los casos; si decide un signo, por intervalos; un parámetro en el exponente, por barrido exacto con fronteras bisecadas | Evaluación acercándose al punto (Richardson); 61 casos y 222 aleatorios frente a SymPy sin un resultado distinto |
| Estudio completo (5), extremos absolutos (6), número de soluciones (4) | `estudio`, `extremos_absolutos`, `soluciones` | Dominio exacto (ceros de denominadores, argumentos de ln, radicandos), simetría, cortes, asíntotas (vertical, horizontal, oblicua), monotonía y curvatura por tabla de signos; Weierstrass con su hipótesis; Bolzano + monotonía estricta | Extremos frente a sus vecinos y a una malla de 2001 puntos; puntos críticos frente a `sympy.solve` |
| Ceros reales | (interno) `raices.py` | Raíces racionales, cuadráticas y bicuadradas exactas; el resto aislado por **Sturm** (número exacto, valor a precisión de máquina); `ln g = k`, `eᵍ = k`, `√g = k`, factores `eˣ` que no se anulan, `|·|` y `sign` por trozos, `sen`/`cos` de argumento lineal | 296 polinomios frente a `sympy.real_roots` |
| Impropias con parámetro (1) | `impropia` | Comparación en el límite (`e^(qw)`, `w^p`, Bertrand) en cada punto impropio; valor por Barrow con límites exactos; con parámetro, barrido exacto y fronteras localizadas | Cuadratura tanh-sinh (si la cola es lenta lo dice: «no concluyente») |
| Series numéricas (14), de potencias (2), suma de series (3) | `serie` | Condición necesaria, comparación con geométricas, `n^p` y Bertrand, Leibniz con el decrecimiento comprobado por `b′`, cociente con factoriales simplificados exactamente (`n!`, `(2n)!`); radio por el cociente y extremos estudiados; sumas geométricas y telescópicas exactas (armónicos) | Sumas parciales; convergencia frente a `Sum.is_convergent` |
| Taylor con resto de Lagrange (11) | `taylor` | Coeficientes exactos en potencias de `(x − a)`; `M = máx |f⁽ⁿ⁺¹⁾|` por Weierstrass; orden mínimo para un error | Error real ≤ cota |
| Primitivas: fracciones simples (9) y cambio de variable (10) | `primitiva`, `integrar` | Factorización sobre ℚ (lineales con multiplicidad, cuadráticos irreducibles), coeficientes por sistema lineal exacto; `√(cuadrática)` completando el cuadrado y con cambio trigonométrico o hiperbólico | Derivar la primitiva; descomposición frente a `sympy.apart` |
| Función definida por una integral (12) | `tfc` | `F′ = f(v)·v′ − f(u)·u′` | Derivada numérica de cuadraturas |
| Inversa y su derivada (15) | `inversa` | `x₀` exacto, inyectividad, `f′(x₀) ≠ 0` | Sustitución |
| Continuidad y derivabilidad con parámetros (7) | `a_trozos` | Ecuaciones en los parámetros resueltas exactamente | Salto y derivadas laterales numéricos |
| Hipótesis de Rolle, valor medio, Bolzano (13) | `teorema` | Cada hipótesis comprobada (y dónde falla) y `c` hallado | — |
| Desigualdades (T1) | `resolver_inequidad` | Tabla de signos exacta (además del caso periódico de T-13) | Puntos de prueba |
| Riemann, aplicaciones (T9) y métodos numéricos (T12) | `riemann`, `aplicacion_integral`, `metodo_numerico` | Sumas izquierda/derecha/punto medio/trapecio con rectángulos como datos; área entre curvas, volumen de revolución (discos o capas) y longitud de arco; bisección, Newton, punto fijo con contractividad comprobada, trapecios y Simpson con cota a priori, interpolación de Lagrange exacta | Barrow frente a Simpson |

**Huecos de ML-2 cerrados (2026-10-06, con segundo camino cada uno):** exponenciales
superlineales que se compensan (`e^(x²)·e^(−x²) = 1` por combinación exacta de exponentes;
`3ⁿ·n!/nⁿ` por el cociente reagrupado a `(1+1/n)^n → e`), escala `ln(ln x)`, criterio de
Dirichlet en impropias (`sin x/x`) y series (`sin n/n`), sumas de Taylor (`Σxⁿ/n = −ln(1−x)`,
`e^x`, `sin`, `cos`, `atan`, `atanh`, geométricas), Γ exacta (enteros, semienteros,
recurrencia; valor `∫₀^∞x^c·e^(−x) = Γ(c+1)`) y reducción de potencias de cuadrático
irreducible (Δ > 0), y barrido con parámetro ampliado a malla geométrica hasta ±10⁶.

**Lo que sigue sin hacerse (y se dice):** `ln(ln(ln))`, Dirichlet con oscilación no afín
(`sin(x²)/x`), series fuera de la tabla de Taylor, Γ fuera de enteros/semienteros en
exacto, cuadráticas repetidas con Δ ≤ 0, sondas de barrido no decididas, espectro 3×3 no
racional, autovectores de λ no racional y pseudoinversa sin rango columna completo.
**ML-5:** gradiente no lineal (críticos, Lagrange), Hessiana semidefinida o indefinida
en n > 2, Taylor-2 sin cota, recintos no rectangulares.

## Capacidad implementada — ML-9, probabilidad y estadística (2026-10-07)

Todo en Python puro (SciPy solo como oráculo en las pruebas). Cada operación da pasos con
«por qué», las convenciones que cambian el resultado (tasa o media, σ o σ², geométrica
desde 0 o desde 1, varianza con n o con n − 1, factor K lineal…) y **dos caminos**: la
función de distribución sale de su forma cerrada o de la función especial (gamma y beta
incompletas por Lentz, Φ⁻¹ de Acklam refinada con Halley, Q de Marcum) y se contrasta con
la **cuadratura tanh-sinh de la densidad**; las simulaciones sembradas usan el
**mecanismo constructivo** de cada ley (suma de Bernoulli, llegadas exponenciales,
Box-Muller, Marsaglia-Tsang), nunca la inversa de la F que comprueban. Si un segundo
camino discrepa, el resultado sale con el sello «discrepa», no como excepción.

| Tipo de examen (§15.1, Probabilidad) | Operación | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| 1 Probabilidad total y Bayes | `probabilidad` (`bayes`) | Partición comprobada, regla del producto por rama, total y posteriores exactas en ℚ; el árbol como datos | `P(B) + P(no B) = 1`, `Σ P(Aᵢ∣B) = 1` y simulación del árbol |
| 2 Binomial, geométrica, Poisson | `variable_aleatoria` | Probabilidades exactas (`406006699/625000000`, `1 − 5·e^(−2)`), sucesos «P(2 < X ≤ 5)» y condicionados «P(X > 3 ∣ X > 1)» | Suma término a término y simulación |
| 3 Aproximación normal | `aproximacion_normal` | Corrección de continuidad, condición `np ≥ 5` declarada | El valor exacto al lado, con el error |
| 4–5 Intervalos de confianza y tamaño de muestra | `intervalo_confianza` | z con σ conocida, t con σ estimada (elección justificada), χ² para la varianza, Wald (y Wilson de contraste) para proporciones, diferencias (agrupada o Welch), tamaño redondeado hacia arriba | Cuantil por cuadratura y **cobertura del método simulada** (3000 muestras) |
| 6 Exponencial, falta de memoria, Gamma | `variable_aleatoria`, `proceso` | `P(X > 8 ∣ X > 3) = e^(−1)`; Erlang con F exacta | Cuadratura y simulación |
| 7 Densidad con constante, Chebyshov | `variable_aleatoria` (`densidad`) | `∫f = 1` lineal en la constante (exacta), `f ≥ 0` comprobada, momentos y F por tramos | Cuadratura independiente |
| 8 Transformaciones, máximo, mínimo, convolución | `variable_aleatoria` | Ramas monótonas por los ceros de g′ (también sin cambio de signo, x³), inversa simbólica, `f_Y = Σ f_X(h)·∣h′∣`; `Fⁿ`, `1 − (1 − F)ⁿ`; tramos de z por las sumas de extremos | `∫f_Y = 1`, mediana contra la simulación de g(X); convolución numérica por tramos |
| 9 Vectores gaussianos | `vector_aleatorio` | `Aμ + b`, `AΣAᵀ`, condicionada `μ_a + Σ_abΣ_bb⁻¹(x_b − μ_b)` en ℚ; Σ semidefinida comprobada por menores principales | Elemento a elemento y ortogonalidad del error, exactas |
| 10 Esperanza condicional, estimación lineal | `vector_aleatorio` (`tabla`) | Marginales, Cov, ρ², independencia (contraejemplo «incorreladas no independientes»), recta óptima y `E[Y∣X]` | `E[e] = E[e·X] = 0` exactos |
| 11 Momentos y máxima verosimilitud | `estimador` | Fórmulas cerradas (Poisson, exponencial, Bernoulli, geométrica, binomial, normal, U(0, θ) con su máximo en el borde); densidad con parámetro, numérica y declarada | Sección áurea sobre log L |
| 12 Proceso de Poisson | `proceso` | Recuentos, incrementos independientes, condicionada binomial, llegadas Erlang, `λ·mín(t₁, t₂)` | Simulación de las llegadas |
| 13 Procesos con variables aleatorias | `proceso` (`va`) | `E[X(t)]` y `R(t₁, t₂)` exactas integrando sobre cada variable (uniforme, discreta, normal por momentos), producto a suma, reducción por periodo; estacionariedad decidida | Simulación sembrada de `R` |
| 14 Procesos de Bernoulli o ±1 | `proceso` (`paseo`) | Media, varianza, `R(n, m)`, paridad | **Enumeración de los 2ⁿ caminos** (n ≤ 16) |
| 15 Combinatoria, ocupación, inclusión-exclusión | `probabilidad` | Variaciones, combinaciones (con y sin repetición), multiconjuntos, bolas distinguibles o no, sobreyecciones, desarreglos | **Enumeración directa**; regiones de Venn ≥ 0 |
| Tablas (§15.2 punto 9) | `tabla_estadistica` | Normal, t, χ², F calculadas con el redondeo «de tabla» (1,960; 2,576; t₁₉ = 2,093…) | F por cuadratura en el cuantil |
| Descriptiva, contrastes, regresión | `estadistica`, `contraste`, `regresion` | Las dos varianzas, cuartiles tipo 7 declarados, atípicos por 1,5·RIC; z, t, χ² (varianza, bondad, independencia); mínimos cuadrados en ℚ | Identidad `Σ(x − x̄)² = Σx² − n·x̄²`; p-valor por cuadratura y región crítica coherente; `Xᵀe = 0` |
| Comunicaciones (D12, G) | `comunicaciones` | BER de BPSK/QPSK/BFSK/OOK/DPSK/FSK no coherente/BPSK con Rayleigh (y Eb/N0 para una BER objetivo), ALOHA puro y ranurado, fallo Rayleigh y Rice, ARQ (convención de Stallings) | Simulación de BPSK en AWGN, Q por cuadratura, promedio sobre el desvanecimiento, simulación de ALOHA y ARQ |
| Simulación | `montecarlo` | Con la semilla de la petición; sello «solo numérico» | Frente al exacto, 5 errores típicos |

**Batería:** 300 leyes y sucesos aleatorios contra `scipy.stats` (P(a < X ≤ b) y su forma
exacta, cuantil, media, varianza): 0 errores (120 quedan como test permanente).

**Lo que no se hace (y se dice):** la densidad con parámetro en el estimador es numérica
(sello «solo numérico»); las esperanzas sobre una normal solo para expresiones
polinómicas en esa variable; la media y la varianza de Rice no se dan en forma cerrada;
la fórmula de retroceso N con `N < 1 + 2a` es la aproximación de libro y se avisa.

**Revisión de fases anteriores (2026-10-07)** con un barrido de entradas sobre todas las
operaciones: `integrar` con `oo` leía «o·o» y devolvía un resultado vacío (ahora delega
en `impropia`); con parámetros (`∫₀¹ k·x(1 − x)`) afirmaba falsamente «no está acotado en
x ≈ 0» (ahora Barrow simbólico, `k/6`, contrastado con cuadratura en varios valores); una
integral divergente salía «verificada» sin valor; `impropia` no daba el valor de
`∫₀^∞ x³e^(−x/2)` (ahora usa también el integrador de ML-2); ML-8 lanzaba una excepción
cuando el segundo camino discrepaba en lugar del sello «discrepa»; extremos, centros o
puntos con letras, sumas de Riemann de funciones no acotadas, funciones con letras sin
valor en operaciones de una variable, gradiente o críticos de una constante, `1/0`
literal, `clientes ≤ 0` en M/M/1 y probabilidades con denominador 0 en Huffman reventaban
con TypeError, IndexError o ZeroDivisionError (ahora se rechazan diciendo qué falla); las
sumas de Riemann con una singularidad evitable (`sen x/x` en 0) toman el límite; `evaluar`
con valores en texto (`x = "1/2"`) devolvía un resultado vacío (ahora exacto, `1/4`), con
letras sin valor da la sustitución parcial comprobada y donde no está definida lo dice.
El contrato (§5.9) convierte en «dato mal escrito» solo los fallos de leer la petición
(clave ausente, `int("1/2")`, `None`); cualquier otro error interno sigue saliendo como
tal. Cuatro ficheros de pruebas importaban SymPy sin `importorskip`, y el CI (que no lo
instala) no podía ni recogerlos. Pruebas: `tests/test_mathlab_revision_fases.py`.

## Capacidad implementada — ML-14, señales y sistemas deterministas (2026-10-07)

Todo en Python puro (sin NumPy ni SciPy en el dominio; la DFT es la definición
directa en O(N²)). Cada cálculo de la operación `senales` da pasos con «por qué»,
las convenciones de §5.11 (`frecuencia = f`, `frecuencia_digital = F`) y **dos
caminos**: la fórmula cerrada frente a cuadratura fina, DFT con relleno o
recurrencia iterada. Si el segundo camino discrepa, sello «discrepa».

| Tipo (§4.15) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Biblioteca de señales | `biblioteca`, `eje` | Π/Λ/exp con integral, energía (A²T, 2A²T/3, A²T/2) y TF cerradas; eje afín con centro y ancho nuevos; aviso de solape con energía cruzada | Cuadratura fina; E escala como E/\|a\| |
| Convolución analógica | `convolucion`, `ventana` | Rupturas = sumas de extremos; lineal a trozos exacta en constantes; deltas que desplazan y escalan; ventana como Π normalizado | ∫y = ∫x·∫h; cuadratura fina + cola exponencial |
| Convolución digital | `conv_digital`, `regimen` | Exacta en ℚ, longitud L1+L2−1, tres tramos; régimen por suma geométrica (\|a\| < 1) | Σy = Σx·Σh; DFT con N ≥ L1+L2−1 |
| Periódicas | `periodica`, `periodo` | c_k = (1/T0)·X_b(k/T0); nulos por paridad; periodo por mcm | Otra base da los mismos c_k; Parseval contra (1/T0)∫\|x\|² |
| Energía y potencia | `energia`, `potencia_sinusoide`, `energia_eco` | E exacta por tramos; P = A²/2; E_y = E_x(1+a²) sin solape | Cuadratura fina |
| Correlación y densidad | `correlacion`, `densidad` | r del Π (triángulo) y de la exp; S = \|X\|²; retardo por el pico | r(0) = E; \|r(τ)\| ≤ r(0) |
| DTFT | `dtft` | P_L con máximo L y ceros en k/L; aⁿu[n] con \|H\|²; δ con fase | Parseval Σ\|x\|² = ∫₀¹\|X\|²; hermiticidad |
| DFT | `dft`, `dft_lineal` | Definición directa; X[0] = Σx; hermítica; Parseval; retardo como fase | Circular = lineal con N ≥ L1+L2−1 |
| Eco e inverso | `eco`, `inverso`, `cascada` | Ceros en \|z\| = \|a\|^{1/L}; \|H(F)\|²; h2 = Σb^k·δ[n−kL] con b = −a (\|b\| < 1) | La cascada devuelve x |

**Batería:** `tests/test_mathlab_ml14.py` (35 pruebas: doradas + las 7
propiedades de §11.3 para el bloque 15). La prueba de contrato
(`tests/test_mathlab_contrato_ml12.py`) incluye ya `senales`.

**Lo que no se hace (y se dice):** tramos no constantes (triangular con
exponencial y colas) salen con sello «solo numérico»; el inverso causal con
\|b\| ≥ 1 se rechaza por inestable; la TF de periódicas como deltas usa las
áreas de `distribuciones.py` (ML-12) sin duplicarlas.

## Capacidad implementada — ML-15, fasores y polarización (2026-10-07)

Respaldo E de EAFO. Operación `polarizacion` (§8.2 S) con los cinco grupos de
calculadoras, todo en Python puro (la SVD 2×2 es fórmula cerrada).
Convenciones de §5.11 declaradas en cada cálculo (`pico` o `V_ef`,
`e^{+jωt}` o `e^{−iωt}`, `f` o `ω`, dB de amplitud): el fasor frente al
tiempo se verifica con la convención contraria y da la misma onda física.

| Tipo (§4.17) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Fasor ↔ tiempo, inverso | `fasor`, `inverso`, `convenciones_fasor` | Suma rectangular (exacta si fases múltiplo de π/2); inverso como sistema 2×2 en (P, Q) desde dos muestras | Muestreo del tiempo; x(t) idéntica con e⁺ y con e⁻ |
| Onda plana | `onda_plana` | k = nω/c, η = η₀/n, H = k̂×E/η, ⟨S⟩ = |E|²/2η, P = ⟨S⟩·A (círculo/cuadrado; desplazamiento avisado) | ½Re(E×H*) y promedio temporal; k̂·E = 0 comprobado |
| Medios con pérdidas | `medios` | ε̃, ñ en rama Re ≥ 0, γ = α+jβ; aproximación por σ/ωε con condición y error relativo; d(X dB) con 8,686 | α, β por γ y por k₀·ñ |
| Polarización | `polarizacion` | SVD de [Re E \| Im E]; AR también por tanχ; ψ por tan2ψ y por vector singular; Stokes | Giro muestreado (mano); |s| = S₀ |
| Jones | `jones`, `diseno`, `plf` | Retardadores R(−φ)·diag(1,e^{−jδ})·R(φ), cascada, Malus; diseño λ/4+λ/2 en malla determinista; PLF hermítico | J†J = I (conserva |E|²); Malus como caso de PLF |
| Fresnel | `fresnel` | Snell, cosθ_t con Im ≥ 0, r/t/potencias con factor de medios; θ_B, θ_c | R + T = 1; r_p(θ_B) = 0; normal (n₁−n₂)/(n₁+n₂) |
| Multicapa | `multicapa`, `antirreflejante` | Matriz por capa (δ, η s/p), producto, Y = C/B; n_f = √(n₁n₂) | det = 1 por capa; R + T = 1; AR con R ≈ 0 |

**Batería:** `tests/test_mathlab_ml15.py` (32 pruebas: doradas + las 6
propiedades de §11.3 para el bloque 17). La prueba de contrato incluye ya
`polarizacion`. Mano declarada: dextrógira por la regla de la mano derecha
con el pulgar en la dirección de propagación (IEEE); con e^{+jωt}:
dextrógira ⟺ sinδ < 0.

**Lo que no se hace (y se dice):** fases no múltiplo de π/2 salen numéricas
(con rectangular exacto solo si lo son); AR = ∞ se informa como lineal; ψ no
definida en circular; inverso causal con |b| ≥ 1 y muestras separadas medio
periodo se rechazan; el diseño Jones falla honestamente si la malla no
alcanza el objetivo.

## Capacidad implementada — ML-16, campos y ondas (2026-10-07)

Respaldo E de Electromagnetismo (las tres esferas, 5 veces) y parciales.
Operación `campos` (§8.2 T) con los ocho grupos; reutiliza ML-13
(electrostática de la caja para V dado) y no duplica motores. Convención
declarada: `V(∞) = 0` solo para distribuciones acotadas (`potencial =
V_inf_0`); el cilindro infinito lleva su referencia en r₀ y lo avisa.

| Tipo (§4.18) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Carga total | `carga` | Arco (dl = R·dθ), cilindro (jacobiano r), esfera (capas 4πr²), placa separable; todo en función de `a` | Cuadratura; homogeneidad Q(2a) = 2Q(a); límites uniforme/macizo |
| Gauss | `gauss` | Esfera con empalme y V(∞) = 0; ρ = a·rⁿ con Q_enc; cilindro con ref. en r₀; plano a caballo | ∇·E = ρ/ε₀; E = −dV/dr; energía por ½ΣQV y (ε₀/2)∫E² |
| Conductores | `conductores` | Gauss en el metal (E = 0); V por superposición; tierra impone V = 0 | Inducidas suman la carga neta; V(R₃) = 0 con tierra |
| V dado | `v_dado` | ML-13: E = −∇V, ρ = −ε₀∇²V, caja por 6 caras | ∭ρ frente a ε₀∯E·dS |
| Maxwell | `maxwell`, `guia`, `completar` | c = ω/k = E₀/B₀; guía TE con β² = ω²/c² − (π/a)² (corte honesto); By por ∇·B = 0 | Helmholtz fasorial; cuadratura de P; función nula sin campos estáticos |
| Perfiles | `perfil` | f(t − k̂·r/v) gauss/sech² por sustitución; v, energía, trazas | Ecuación de onda numérica; Simpson del área |
| Coulomb/BS | `coulomb`, `biot_savart` | Anillo, disco, espira, hilo, polígono de N lados | Límites puntual/plano/dipolo; Ampère; N → ∞ a la espira |
| Condensadores | `condensador` | Plano, esférico, cilíndrico por Gauss con D; serie | Q²/2C frente a ½CV²; R₂ → ∞; serie ≤ mín |
| Inducción | `faraday`, `poynting` | Φ orientado → derivada → Lenz; S = E×H en el borde | Unidades V = Wb/s; ∮S·dA = dU/dt exacto |
| Antenas (G) | `friis`, `ruido`, `array` | Friis, G/T, AF = sen(Nψ/2)/sen(ψ/2) | Lineal frente a dB; N = 1 reproduce |

**Batería:** `tests/test_mathlab_ml16.py` (29 pruebas: doradas + las 8
propiedades de §11.3 para el bloque 18). La prueba de contrato incluye ya
`campos`.

**Lo que no se hace (y se dice):** modo en corte (β imaginaria) y Bj con
simetría no razonada se rechazan; perfiles solo gauss/sech²; mutua solo
solenoide-bobina (geometrías arbitrarias, fuera); antenas
solo Friis/ruido/array (G, al final como manda §10); campo fuera del eje y
fuerza sobre espiras en campo no uniforme, fuera (se dicen); el signo de Ex
del arco lo fija la figura (orientación declarada).

## Capacidad implementada — ML-22, física auxiliar (2026-10-07)

U(x) siempre (E ~12/15); gas ideal opcional activado (D10); órbitas G al
final de su fase; MB/Planck/Stefan opcional activado (D12). Operación
`fisica` (§8.2 U) con las cuatro calculadoras, en Python puro.

| Tipo (§4.19) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Equilibrio y oscilación | `equilibrio`, `oscilacion`, `retrato` | U′ = 0 por barrido + bisección, U″; ω = √(U″/m); T por sen²; RK4 | T por cuadratura = RK4; retrato integrado |
| Gas ideal (opc.) | `gas`, `ciclo` | W = −∫p dV; T por pV = nRT; T_max derivando; ΔS cerrada; ciclo poligonal | ∫dQ_rev/T; Clausius ΣQ + ΣW = 0; η = W/Q_in |
| Kepler/órbitas (G) | `kepler`, `orbita`, `visibilidad` | Bisección + Newton; v = √(GM/a); cosθ = R/(R+h) | Sustitución; e = 0 círculo; T²/a³ |
| MB/Planck/Stefan (opc.) | `maxwell_boltzmann`, `planck` | Momentos gaussianos; ∫x³/(eˣ−1) numérica | ∫f = 1, ⟨v²⟩; π⁴/15 con σ |

**Batería:** `tests/test_mathlab_ml22.py` (17 pruebas: doradas + las 3
propiedades de §11.3 para el bloque 19). La prueba de contrato incluye ya
`fisica`. W = trabajo sobre el gas (Q = ΔU − W, declarado).

**Lo que no se hace (y se dice):** U solo polinómica, cosenoidal, fuerza
polinómica, tabla (tramos rectos, aproximada) o expresión (derivadas
numéricas); 2D solo conservativo comprobado; sin mínimos no hay oscilación;
E que escapa no confina; E a la altura de una barrera interior da periodo
infinito y se niega (homoclínica); e ≥ 1 fuera (ligadas); mutua coaxial
cerrada fuera; cinemática con ligaduras, choques 1D, CM, inercias, rodadura,
conducción y Boltzmann de 2 niveles sí están (mecánica clásica de exámenes);
dinámica de sistemas, rotación general y fluidos, fuera; finanzas y ML no
tocan este bloque.

## Capacidad implementada — ML-17, discreta/códigos/información (2026-10-07)

E débil (César, Pascal) y G. Operaciones `discreta` (§8.2 J + tiempo real),
`codigos` (§8.2 K + L) e `informacion` (§8.2 M); ℤₙ/GF(p)/GF(2) lineales de
ML-12 reutilizados sin duplicar; Huffman de `grafos`; azar sembrado de
`eventos`; LFSR ajeno como plug-in futuro (no importado, §4.10).

| Tipo (§4.8–§4.11) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Lógica | `logica`, `equivalencia`, `cuantificador` | Tablas 2ⁿ (≤ 4 vars) + leyes nombradas; ¬∀ ≡ ∃¬ | Tablas frente a frente |
| Conjuntos/binomio | `conjuntos`, `potencia`, `binomio`, `vandermonde` | Enumeración; filas que suman 2ⁿ; suma directa | Inclusión-exclusión; evaluar en a = b = 1 |
| Recurrencias | `recurrencia`, `maestro`, `ruina` | Característica exacta + iteración; casos 1/2/3; p = 1/2 exacto | Iterar frente a cerrada; recurrencia punto a punto |
| Complejidad/PD | `sumatorio`, `mochila`, `cambio` | Cerradas exactas; PD con tabla | Suma directa; fuerza bruta 2ᴺ; voraz frente a PD |
| Tiempo real (D12) | `tiempo_real` | U → Liu-Layland → RTA por punto fijo | Cronograma entero sobre el hiperperiodo |
| Cifrado (E) | `cesar`, `afin`, `vigenere`, `hill` | Aritmética modular con hipótesis (gcd, alfabeto) | descifrar(cifrar(x)) = x; A·A⁻¹ = I |
| Tablas/hash | `tabla_zn`, `hash` | Tablas solo si n pequeño; P colisión | Euclides; Monte Carlo del cumpleaños |
| GF(2ᵐ)/GF(p) | `gf2m`, `poli_gfp` | Rabin; tabla log/antilog | α^(2ᵐ−1) = 1; u·u⁻¹ = 1 |
| Códigos | `codigo`, `sindrome`, `crc`, `paridad`, `checksum` | Sistemática por Gauss; resto 0; complemento a 1 | G·Hᵀ = 0; H·c = 0; par más cercano |
| Secretos/clave | `shamir_*`, `rsa`, `dh`, `k_anonimato`, `dp` | Lagrange en 0; Euclides; cuadrados sucesivos | Dos subconjuntos; m^(ed) ≡ m; razón ≤ e^ε |
| Información | `entropia`, `conjunta`, `divergencia`, `kraft`, `capacidad`, `huffman_check`, `clave` | Tablas y log₂; cadena e I ≥ 0 | Uniforme log₂N; C(0,5) = 0; H ≤ L̄ < H+1 |

**Batería:** `tests/test_mathlab_ml17.py` (19 pruebas: doradas + las 11
propiedades de §11.3 para los bloques 8–11). La prueba de contrato incluye
ya las tres operaciones.

**Lo que no se hace (y se dice):** tablas lógicas con > 4 variables (por
leyes); enumeraciones con n > 12/20 (se dice); maestro fuera de tabla;
RTA con periodos no enteros (solo RTA, sin cronograma); hiperperiodo > 2·10⁵
(sin cronograma); RSA/DH/Shamir/privacidad pedagógicos (aviso fijo);
esquema lineal vectorial GF(2) detallado, fuera (solo el marco Gauss).

## Capacidad implementada — ML-18, detección y estimación (2026-10-07)

Bloque 16 (G, sin exámenes: guía de Tratamiento de la Señal). Operación
`deteccion` (§8.2 R) con los seis grupos, en Python puro (Gauss en ℚ,
Jacobi simétrico, Cholesky, Box-Muller sembrado).

| Tipo (§4.16) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Correlación/PSD | `matriz_r`, `r_ar1`, `psd`, `psd_salida` | Toeplitz hermitiana; AR(1) exacto; Wiener-Khinchin | s.d.p. y \|r\| ≤ r(0); r[0] = ∫S dF |
| Detección | `detector`, `detector_map` | T = sᵀx; umbral NP o γ MAP/Bayes; ROC | Monte Carlo sembrado sobre la ROC |
| Fisher/CRB | `fisher` | Cerradas (gaussiana, Bernoulli, Poisson) | Media muestral = CRB (eficiente) |
| Gaussiano | `gauss_conjunto` | Condicionada con ECM | Ortogonalidad E[(θ−θ̂)xᵀ] = 0 |
| Wiener | `wiener`, `yule_walker` | Gauss exacta; Yule-Walker AR(1) | Residuos R·w − p = 0; J(w) ≥ J_min |
| Gradiente/LMS | `gradiente`, `lms`, `nlms` | Modos (1−μλ)ᵏ; E[w(n)] + Monte Carlo | Cota 2/λ_max; divergencia visible |

**Batería:** `tests/test_mathlab_ml18.py` (8 pruebas con las 6 propiedades
de §11.3 para el bloque 16). La prueba de contrato incluye `deteccion`.

**Lo que no se hace (y se dice):** R singular (sin Wiener único); μ fuera
de (0, 2/λ_max) diverge y se muestra; modelos fuera de los tres Fisher;
estimación no gaussiana ni no lineal.

## Capacidad implementada — ML-19, optimización y aprendizaje (2026-10-07)

Bloque 13 (G). Operación `aprende` (§8.2 O) con los siete grupos, en
Python puro salvo ℚ exacta donde el examen la usa; el verificador de
gradientes de ML-12 y el Gauss/Jacobi de ML-18, reutilizados.

| Tipo (§4.13) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Descenso | `gd` | GD/momento/Adam a mano en cuadráticas; η < 2/L | Óptimo por normales; diferencias centrales |
| Regresión | `regresion`, `lasso` | Normales exactas en ℚ; ridge; soft-threshold | Xᵀe = λw; R²; OLS frente a encogido |
| Logística/métricas | `logistica`, `metricas`, `roc` | Xᵀ(p−y); confusión; trapecios | Pérdida que baja; Mann-Whitney |
| Clústeres | `kmedias`, `em`, `arbol` | Lloyd; EM 1D; ganancia máxima | SSE/silueta; log L y BIC; ganancia ≥ 0 |
| PCA/SVD | `pca`, `svd` | Espectral de la covarianza; XᵀX | Σλ = traza; VᵀV = I; mismos ejes |
| Redes | `red`, `retroprop`, `atencion`, `rnn`, `lstm` | Tablas z/a; δ·aᵀ; softmax; puertas | Diferencias centrales; filas = 1 |
| SVM | `svm` | Margen 2/‖w‖ con KKT | mín y·f ≥ 1 |

**Batería:** `tests/test_mathlab_ml19.py` (8 pruebas con las 5 propiedades
de §11.3 para el bloque 13). La prueba de contrato incluye `aprende`.

**Lo que no se hace (y se dice):** XᵀX singular sin ridge; clases
desbalanceadas (la exactitud engaña, se avisa); k-medias/EM dependen de la
inicialización; w = 0 en SVM; datos no separables en logística sin
regularizar (w → ∞, se avisa).

## Capacidad implementada — ML-20, Markov/MDP/refuerzo (2026-10-07)

Bloque 12 (G). Operación `refuerzo` (§8.2 N) con los cinco grupos;
`markov`/`cola_mm1` de ML-12 reutilizados (π exacta, simulación sembrada).

| Tipo (§4.12) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Cadenas | `absorcion`, `clasifica` | N = (I−Q)⁻¹ exacta; clases + periodos por mcd | N·(I−Q) = I; partición y cierre por aristas de un paso; periodo = retorno mínimo multiplicando Pᵏ |
| MDP | `mdp_eval`, `mdp_optimo` | Sistema lineal; iteración hasta tol + voraz | Residuo de Bellman 0; iteración = directa |
| Tabulares | `episodio` | MC/TD/SARSA/Q sobre episodio dado | MC = media muestral exacta |
| Bandidos | `bandidos` | Incremental/ε-greedy/UCB con tablas Q/N | Qₙ = media muestral exacta |
| Gradiente | `reinforce` | Softmax con baseline en 1 paso | Diferencias finitas de J |

**Batería:** `tests/test_mathlab_ml20.py` (7 pruebas con las propiedades de
§11.3 para el bloque 12, incluida la gráfica de recompensa media de los
bandidos). La prueba de contrato incluye `refuerzo`.

**Lo que no se hace (y se dice):** I−Q singular (sin absorción segura);
γ ≥ 1 (sin contracción); α fuera de (0,1]; MDP continuo o con S grande
(solo tabular pequeño).

## Capacidad implementada — ML-21, matemáticas financieras (2026-10-07)

Bloque 14 (G). Operación `finanzas` (§8.2 P) con 15 cálculos. Convenciones
declaradas (§5.11): tasa **nominal** repartida en `m` capitalizaciones
(la periódica es `r/m`, la TAE es `(1+r/m)^m − 1`), Florida continua
`e^{rt}`; Markowitz **con cortos** (si no, es cuadrática y no se resuelve).
La base de días (act/365 o 30/360) **no** se implementa: el calendario no
está modelado y se dice, en vez de asumirlo.

| Tipo (§4.14) | Cálculo | Cómo se resuelve | Segundo camino |
|---|---|---|---|
| Interés | `interes`, `tiempo` | Simple, `(1+r/m)^{mt}`, continua | Periodo a periodo con el último fraccionado |
| Rentabilidad | `van`, `tir`, `anualidad` | Suma descontada; bisección en el cambio de signo; `A·r/(1−(1+r)^{−n})` | VAN(TIR) = 0; saldo 0 tras n cuotas |
| Fijo | `bono` | Suma descontada + ∂P/∂y | Duración modificada = −P′/P numérica |
| Derivados | `futuro`, `payoff`, `crr`, `black_scholes` | `S₀e^{rT}`; árbol con `q=(e^{rΔt}−d)/(u−d)`; BSM | `0 < q < 1`; CRR → BS con n grande; paridad put-call |
| Volatilidad | `vol_implicita`, `montecarlo` | Newton sobre la vega; `S_T` lognormal exacta sembrada | Vega > 0 ⇒ raíz única; MC dentro de 3σ̂ de BSM |
| Cartera | `markowitz`, `frontera`, `sharpe_var` | KKT lineal exacto en ℚ; barrido de `m` | `wᵀ1 = 1`, `wᵀμ = m`, `2Σw` ortogonal al espacio factible, σ² creciente y perturbación factible que sube el riesgo |
| (hipótesis) | Σ definida positiva | — | Sylvester: los `n` menores principales-leading > 0, en ℚ |

**Batería:** `tests/test_mathlab_ml21.py` (20 pruebas) más la fila
`finanzas` del contrato. Verifica CRR → Black-Scholes (n = 400, tolerancia
0.05), paridad put-call, duración contra derivada numérica, ortogonalidad
del gradiente KKT a la dirección factible con 3 activos, rechazo de Σ no
definida positiva y el error 1/√N del Monte Carlo. El contrato cubre los
15 cálculos.

**Lo que no se hace (y se dice):** Markowitz **sin shorts** (la frontera es
cuadrática: se avisa en la hipótesis, no se resuelve) y Σ **no definida
positiva** (`BAD_INPUT`, porque «mínima varianza» no sería un mínimo);
bono de precio 0 o sin flujos (`BAD_INPUT`: la duración no está definida);
TIR sin cambio de signo acotado (se lanza `UNSUPPORTED`, no se inventa ninguna);
CRR con `d < e^{rΔt} < u` (hay arbitraje → se rechaza); σ implícita sin
solución en [0,∞) (`UNSUPPORTED`); BS con dividendos, tasa variable o
anticipos (fuera del modelo estándar); Todo lo que exige un flujo perpetuo
o una base de días act/365 o 30/360 explícita: la convención se declara
pero **no** se implementa el calendario, así que se dice en vez de
aproximar.

## Capacidad implementada — ML-10, ejercicios y corrector (2026-10-07)

§7. Operación `ejercicio` (§8.2 S) con 5 cálculos y 7 temas. Reutiliza
`verify.check_equivalence` / `numeric_agreement` (el corrector de F9 y el
operador `igualdad` ya comparaban formas normales: aquí se usan, no se
repiten).

| Requisito de §7 | Cómo está resuelto |
|---|---|
| Plantilla única | `Ejercicio`: enunciado, datos, tipo de entrega, pistas, respaldo E/G, dificultad, gráfica y solución paso a paso |
| Tipos de entrega | `expresion`, `numero`, `matriz`, `vector`, `conjunto`, `grafica`, `demostracion` |
| **Corrección por equivalencia** | Formas normales exactas; si solo coinciden en las muestras, el sello queda en `solo_numerico` y se dice (§5.3) |
| Pistas graduadas y modo estudio | `pistas_hasta(n)`: de menos a más ayuda, y se pide solo las `n` primeras |
| **Generador sembrado** | Por tema, dificultad y semilla; determinista y con la solución incluida |
| **Respuestas no únicas** | `comprueba_propiedad("ortonormal", A)`: comprueba `Aᵀ·A = I`, no su forma |
| Nada por parecido | Una gráfica **no** se corrige por texto: se lanza `UNSUPPORTED` y se dice por qué |

**La solución la pide el motor, no la escribe el generador.** Cada
constructor llama a la calculadora real (`limite`, `differentiate`,
`integrar`, `lineal.determinante`, `resolver`, `algebra.gram_schmidt`,
`laplace`), de modo que enunciado y solución no pueden desincronizarse. El
generador **se autocomprueba** (`corrige(ex, ex.solucion)`) y **reintenta con
otros parámetros** si el ejercicio sale degenerado —un determinante 0, un
límite que no existe—, porque un ejercicio sin sentido no es un ejercicio.

**Batería:** `tests/test_mathlab_ml10.py` (19 pruebas) más la fila `ejercicio`
del contrato.

**Lo que no se hace (y se dice):** gráficos con figuras leídas del enunciado
(§7 lo pide y aquí se **niega**: la aplicación no lee la imagen, así que el
ejercicio ofrece las lecturas como datos — falta hacerlo en los temas con
figura); exercises de los bloques todavía no conectados al banco D6 de
preguntas ni a la maestría (el corrector es el mismo principio —determinista,
el modelo nunca califica— pero el enlace no está); y corrección por
equivalencia de **demostraciones**: se corrige la identidad a demostrar, no
el razonamiento.

## Capacidad implementada — ML-11, el pulido (2026-10-09)

Última fase de §10. `pulido.py` + operación `pulido` (5 cálculos). Las cuatro
cosas son **comprobaciones que se ejecutan**, no una lista de deseos: un
requisito que nadie puede ver fallar acaba mintiendo solo, que es lo que pasó
con los huecos declarados de este mismo documento.

| Frente | Cálculo | Qué comprueba de verdad |
|---|---|---|
| Accesibilidad (§6) | `accesibilidad` | Descripción textual obligatoria; serie con nombre; `len(xs) = len(ys)`; y que el modelo `Graph`/`Serie` **no tiene campo de color**, que es lo que hace imposible depender solo de él |
| Documentación (§8.1) | `describe` | El resultado **entero** como texto, con los tres niveles de detalle: valor, aproximación y error, pasos, sello, hipótesis, convenciones, avisos y gráfica descrita |
| Rendimiento (§5.4) | `rendimiento` | `time.perf_counter` contra un techo declarado (que se puede cruzar a propósito para verlo fallar) y **determinismo**: la misma entrada da el mismo resultado y sello |
| Certificación (§8.4) | `audita`, `certifica` | Recorre **todas** las operaciones registradas con una entrada canónica y comprueba los criterios de §8.4 uno a uno |

**Medido:** 80 operaciones comprobadas, **0 fallos, 0 fuera del techo, 0 no
deterministas**, 0 sin muestra.

**El criterio 3 se aplica donde §8.4 lo pide y no donde no.** La norma solo
exige el «por qué se eligió este método» a derivar, integrar, límites, series,
EDO y transformadas (12 aquí, todas cumplen). Aplicarlo a las 80 sería
inventarse un criterio más estricto, y **hacer fallar la certificación por algo
que la norma no pide sería una forma elegante de mentir**: las otras cinco
(`grafo`, `metodo_numerico`, `proceso`, `teorema`, `variable_aleatoria`) se
reportan como **mejora pendiente**, ni como buenas ni como malas.

**Lo que no se hace (y se dice):** la **interfaz** (§9, el visor Qt) es de otra
capa — aquí se certifica que la gráfica *descrita como dato* es accesible, que
el widget la pinte bien es del gate de UX; los criterios 4 y 9 de §8.4, que son
de juicio y de orden de entrega; el **rendimiento de la interfaz** (aquí se
mide el dominio); las figuras leídas del enunciado (§7, lo niega ML-10); y el
enlace al banco D6 y a la maestría (§7).

**Batería:** `tests/test_mathlab_ml11.py` (24 pruebas). Una de ellas ejecuta la
certificación entera dentro de la suite: si el motor se rompe, la batería lo
nota.

## 5. El motor matemático

### 5.1 Expresiones y exactitud

- Ampliación de `symbolic/` a **varias variables**, vectores, matrices, sumatorios, límites, integrales y derivadas como objetos de primera clase.
- Números **exactos**: enteros, fracciones, raíces, π, e, i. Aproximación con `Decimal` solo cuando se pide y con su error.
- Entrada de fórmulas por **texto** (`int(x^2*sin(x), x, 0, pi)`) con **vista previa** con notación matemática y mensajes de error en castellano que dicen dónde está el problema.
- **Dependencia crítica (v2): fracciones racionales multivariable.** `H(s)` con `R`, `C`, `K` simbólicos, forma normal `K·Π(s−z)/Π(s−p)`, polos y ceros con parámetros, discusión por casos de un parámetro y raíces de polinomios con coeficientes simbólicos. Es lo que más piden los demás laboratorios y **no puede quedar de una sola variable**; entra en la fase ML-12 (§10).
- **Cuerpo como parámetro (v2).** Los objetos de álgebra lineal (Gauss, rango, núcleo, inversa, determinante) se definen sobre un **cuerpo** elegido: ℚ, ℝ, ℂ, GF(p), GF(2), y a continuación GF(2ᵐ). Las hipótesis (`p` primo, polinomio irreducible) pasan a ser comprobaciones explícitas (§5.7).
- **Distribuciones (v2).** Deltas de Dirac, escalón y trenes de deltas con **área** (TF de periódicas, convolución con `δ`), además de funciones ordinarias.
- **Aritmética entera exacta con trazas (v2).** Euclides extendido y potenciación modular con la lista de pasos (cada cociente, cada cuadrado y cada producto), igual que ya se hace con fracciones.

### 5.2 Pasos

Cada operación produce una **traza**: regla aplicada (nombre en castellano), trozo afectado, expresión antes y después, y condiciones (p. ej. «se asume x ≠ 0»). Es el mismo formato de pasos que ya usan el álgebra y la derivación actuales, ampliado. Tres niveles de detalle: resumen, paso a paso y detallado.

### 5.3 Verificación independiente

| Operación | Comprobación |
|---|---|
| Derivada | Comparar con el límite del cociente incremental numérico |
| Primitiva | **Derivarla** y ver que da el integrando |
| Integral definida | Evaluación numérica con error acotado (Simpson adaptativo) |
| Integral múltiple | Calcularla **por otro orden** y por **cambio de variable**; o numéricamente |
| Teoremas de Green, Stokes y Gauss | Calcular **ambos lados** |
| Ecuación o sistema | **Sustituir** la solución |
| EDO | Sustituir en la ecuación y en las condiciones iniciales |
| Límite | Evaluación numérica por los dos lados |
| Matrices | Comprobar `A·A⁻¹ = I`, `A·v = λ·v`, etc. |
| Probabilidad | Suma a 1, simulación sembrada como contraste |
| **(v2)** Aritmética modular y cuerpos finitos | `descifrar(cifrar(x)) = x`; `a·a⁻¹ ≡ 1`; tabla completa para `n` pequeño; `α^(2ᵐ−1) = 1`; contar los `2ᵏ` elementos de un subespacio de GF(2) |
| **(v2)** Códigos, Shamir, RSA | `G·Hᵀ = 0`; `d_min` por pares frente al peso mínimo; **dos subconjuntos** de partes dan el mismo secreto; `m^(e·d) ≡ m` frente a `pow` independiente |
| **(v2)** Información y Markov | `H = log₂ N` en el uniforme; Kraft; `Pⁿ` converge a `π`; **residuo de Bellman 0**; `N·(I−Q) = I`; periodo = retorno mínimo; simulación sembrada de la cadena o del episodio |
| **(v2)** Optimización y redes | **Gradiente por diferencias finitas centrales** (verificador reutilizable en GD, logística, retropropagación y Markowitz); la pérdida baja tras un paso; `Xᵀe = 0` |
| **(v2)** Finanzas | Paridad put-call; `VAN(TIR) = 0`; saldo 0 tras n cuotas; duración `= −P′/P`; límite del árbol CRR a Black-Scholes; `0 < q < 1`; **Markowitz**: `2Σw` ortogonal a la dirección factible y Σ definida positiva por Sylvester; Monte Carlo dentro del intervalo exacto |
| **(v2)** Señales deterministas | `∫y = ∫x·∫h`; duración `D_x + D_h`; `Σy = Σx·Σh`; **tiempo y frecuencia** (Parseval); Wiener-Khinchin `r = TF⁻¹{S}`; circular frente a `conv` directa; la cascada de eco e inverso devuelve la entrada |
| **(v2)** Detección y estimación | Monte Carlo sembrado de `P_FA` y `P_D`; varianza empírica **`≥` cota de Cramér-Rao**; ortogonalidad `E[e·x*] = 0`; modos de LMS frente a la fórmula modal |
| **(v2)** Fasores y Jones | **Dominio del tiempo frente a fasor**; resolver con la convención contraria; **unitariedad** de Jones (conserva `abs(E)²`); exacto frente a aproximado (buen conductor, buen dieléctrico) con su error relativo |
| **(v2)** Campos y Maxwell | `∇·E = ρ/ε₀` por regiones; `E = −dV/dr`; flujo cara a cara frente a divergencia; **sustituir las cuatro ecuaciones de Maxwell** y la de onda; `∇·(∇×F) = 0`; energía `½ΣQV` frente a `(ε₀/2)∫E²` |
| **(v2)** Análisis dimensional | **Comprobador universal:** toda constante de un enunciado (la `a` de `ρ = a·r²`) y toda fórmula se comprueban por dimensiones; detecta unidades inconsistentes en soluciones oficiales (§11.4) |
| **(v2)** Trascendentes y simulación | Todas las raíces por **barrido de signo + bisección**; integración RK4 de `m·x″ = −U′(x)` para medir el periodo; Monte Carlo sembrado; simulación de eventos con semilla |

Si la comprobación falla, el resultado **no se muestra como correcto**: se informa del fallo y se guarda el caso.

### 5.4 Límites honestos

La integración simbólica exacta **no es decidible en general**. El sistema intenta un conjunto amplio de técnicas (sustitución, partes, fracciones simples, trigonométricas, tablas). Si ninguna vale: **«no sé darte una primitiva exacta»** y ofrece el valor numérico con error. Lo mismo para límites, EDO y sumas de series. Tope de tiempo y de tamaño con cancelación.

### 5.5 Rendimiento sin NumPy

Sin NumPy, los cálculos numéricos pesados (superficies 3D, integrales triples numéricas, simulaciones) van en **hilo aparte** con cancelación y barra de progreso, con topes claros. Si hiciera falta, NumPy se añade como dependencia **opcional** (D1).

---

### 5.5b Regla general: toda elección de método se justifica

**Requisito del usuario:** lo de «por qué se elige» **no es exclusivo de los cambios de variable: vale para cualquier procedimiento.** Cada vez que el sistema **elige** entre varios caminos posibles, el paso lleva un apartado **«Por qué este método»** con el motivo concreto y, cuando ayude, **por qué no los otros**. Ejemplos:

| Decisión | Qué se explica |
|---|---|
| Integrar por partes en vez de sustituir | Qué factor se toma como `u` y cuál como `dv`, y por qué (regla LIATE u otra) |
| Orden de integración en una integral doble o triple | Por qué dx antes que dy (límites más simples, integrando integrable en ese orden) |
| Sistema de coordenadas (cartesianas, polares, cilíndricas, esféricas) | Qué simetría de la región o del integrando lo aconseja |
| Teorema elegido (Green, Stokes, Gauss, cálculo directo) | Por qué es más corto y que sus hipótesis se cumplen |
| Método para un límite (L'Hôpital, Taylor, equivalentes) | Qué indeterminación aparece y por qué ese método la resuelve |
| Criterio de convergencia de una serie o integral | Por qué ese criterio aplica y los otros no concluyen |
| Método de una EDO (separables, lineal, Laplace…) | Cómo se reconoce el tipo de ecuación |
| Método de diagonalización, Gauss u otro en álgebra | Qué propiedad de la matriz lo permite |
| Clasificación de un punto crítico (Hessiana, Sylvester, estudio directo) | Por qué el criterio concluye o por qué hay que recurrir a otro |
| Parametrización de una curva o superficie | Por qué esa y no otra |
| **(v2)** Euclides extendido frente a la tabla de inversos | El tamaño de `n`; el inverso exige `gcd = 1` y se muestra la combinación `a·s + b·n = 1` |
| **(v2)** Código: forma sistemática frente a enumeración de las `2ᵏ` palabras | Si es lineal basta el peso mínimo; si no, todos los pares |
| **(v2)** Newton frente a bisección (TIR, volatilidad implícita, Wien) | Newton si la derivada no se anula y hay buen punto inicial (vega > 0); bisección si hay cambio de signo acotado; para la TIR se avisa de la regla de Descartes |
| **(v2)** Bellman: sistema lineal frente a iteración | Política fija y `S` pequeño ⇒ `(I−γP)⁻¹R`; si no, iteración de valor |
| **(v2)** Markowitz: KKT lineal frente a programación cuadrática | Sin restricción de signo en `w` ⇒ KKT; con «sin cortos» no se resuelve y se avisa |
| **(v2)** Convolución: por tramos, por deltas o por TF | Por tramos si hay pocos extremos; por deltas si hay solape de pulsos; por TF si la respuesta es exponencial o sinc |
| **(v2)** Periódica: señal base + TF o integral de periodo | La base si los pulsos son `Π` y `Λ` desplazados; la integral si es una función analítica |
| **(v2)** DFT: elección de `N` | `N ≥ L₁+L₂−1` para que la circular coincida con la lineal; con menos, aparece aliasing temporal |
| **(v2)** Detección: Bayes, MAP o Neyman-Pearson | Con a priori y costes, Bayes o MAP; si solo se fija `P_FA`, Neyman-Pearson |
| **(v2)** Descenso de gradiente: paso `η` | Cota `2/L` en una cuadrática; el condicionamiento decide si hace falta escalar |
| **(v2)** Gauss frente a cálculo directo en campos | Gauss si hay simetría esférica, cilíndrica o plana (**se razona cuál**); cálculo directo si no |
| **(v2)** Exacto frente a aproximado en medios con pérdidas | Siempre se calcula el exacto y se compara; la aproximación solo vale si se cumple su condición |
| **(v2)** Polarización: SVD de `[Re E \| Im E]` o fórmulas de `tan2ψ` | La SVD da semiejes y orientación a la vez; las fórmulas son el segundo camino |

Si varios caminos son válidos, el sistema **lo dice** y justifica el elegido. Si el camino elegido no concluye (p. ej. L'Hôpital que no converge), **lo dice y cambia de método explicando el cambio**. Es un criterio de aceptación de todas las fases (§11.2).

### 5.6 Cambios de variable y sustituciones: siempre explicados

**Requisito del usuario:** cada vez que se haga un cambio de variable, en una integral o en cualquier otro sitio, hay que **mostrarlo y explicar por qué**. Es obligatorio, no opcional. Cada cambio produce un bloque de pasos con esta estructura:

| Parte | Contenido |
|---|---|
| **Por qué** | El motivo en una frase: «aparece `x²+1` y su derivada `2x` como factor», «la región es un círculo, las polares la simplifican», «el integrando contiene `√(a²−x²)`, sirve `x = a·sen t`» |
| **El cambio** | Escrito completo: `u = g(x)`, o `(x, y) = (r·cos θ, r·sen θ)` |
| **Diferencial o jacobiano** | `du = g'(x)·dx` o `\|J\| = r`, con el determinante calculado paso a paso |
| **Límites o región nuevos** | Cada límite transformado, o la región dibujada antes y después; en varias variables, la **imagen de la región** |
| **Validez** | Comprobación de que el cambio es aplicable: derivable, **inyectivo** en la región, jacobiano distinto de 0 (se señalan los puntos donde falla, como el origen en polares) |
| **Integral nueva** | Escrita y resuelta |
| **Deshacer** | Vuelta a las variables originales si es indefinida, o valor directo si es definida |

El sistema también puede explicar **por qué no** se eligió otra sustitución, y en el modo asistido el alumno propone el cambio y el sistema le dice si sirve y por qué, con contraejemplo si no.

### 5.7 Hipótesis de los teoremas

Los exámenes reales piden *«raoneu tots els passos i, en particular, que es compleixen les hipòtesis dels teoremes emprats»*. Por eso, antes de aplicar un teorema (Green, Stokes, Gauss, Fubini, Weierstrass, Bolzano, Rolle, L'Hôpital, función implícita, criterios de convergencia…), el sistema **lista sus hipótesis y comprueba cada una** con el problema concreto: clase C¹ del campo, región acotada y con frontera regular a trozos, orientación coherente, continuidad en el cierre, etc. Si una hipótesis falla, **no aplica el teorema** y lo explica.

**Hipótesis de las técnicas nuevas (v2)**, que se listan y comprueban igual que las de los teoremas: `gcd(a,n) = 1` (inverso modular) y `p` primo o polinomio irreducible (cuerpo); código **lineal** (para `d_min` por peso mínimo); `p` primo mayor que `n` y que el secreto (Shamir); `p ≠ q`, `m < n` (RSA); `γ < 1` (Bellman); matriz estocástica irreducible y aperiódica (estacionaria única); `J` diferenciable y gradiente `L`-Lipschitz (descenso de gradiente); `Σ` definida positiva (Markowitz); un solo cambio de signo (TIR); `0 < q < 1` (CRR); soporte compacto o `h ∈ L¹` (convolución); `N ≥ L` en la DFT; secuencia sumable (DTFT); condiciones de regularidad de Fisher; `R` definida positiva (Wiener); régimen senoidal permanente y convención de signo (fasores); retardador sin pérdidas, matriz unitaria (Jones); simetría razonada y `V(∞) = 0` solo si la distribución está acotada (Gauss y potencial); ausencia de campos estáticos (constante de integración en Maxwell); `U″ ≠ 0` (oscilaciones).

### 5.8 Librerías de verificación

Decisión del usuario: se aceptan **todas las librerías que ayuden a que un resultado sea correcto**. Regla de reparto:

- El **motor propio** produce siempre la solución **paso a paso** (es lo que se enseña).
- Las librerías externas (SymPy, NumPy, SciPy, mpmath…) se usan como **comprobadores independientes**: si discrepan con el motor propio, el caso se marca como error, se guarda y no se da por bueno.
- Si una librería falta, el laboratorio sigue funcionando y la comprobación queda marcada como «no contrastada con librería externa».
- Un resultado solo dado por una librería, sin pasos, **no** se muestra como solución de un ejercicio; puede servir como pista del valor esperado.
- **(v2)** Los motores de los otros laboratorios (`control/`, `ac/`, `gum.py`, `rf/`, `dsp/`, `mna/`) cuentan como **comprobadores independientes** al mismo nivel que SymPy o NumPy, a través del protocolo de §5.9.

### 5.9 Contrato con los demás laboratorios (v2)

**Requisito del usuario:** SIGNALS_LAB y CIRCUITS_LAB (y el laboratorio digital) usan el motor de pasos del laboratorio de matemáticas; este **no** absorbe sus modelos. Para que eso funcione sin acoplarse, el motor ofrece una interfaz estable, sin Qt (§1.2, principio 5):

| Elemento | Contrato |
|---|---|
| **Llamada** | Función de dominio `calcular(operación, entrada tipada, convenciones, nivel de pasos, semilla, límites) → Resultado`. La misma que usa la interfaz (§8.3); ningún laboratorio llama a la pantalla |
| **Resultado** | Valor exacto y, si se pide, aproximado con error; **traza de pasos** (regla con identificador estable, trozo, antes y después, condiciones y «por qué este método»); **sello de verificación** (`✔`, `⚠ Solo numérico`, `✘ Discrepa`); **gráfica descrita** como datos (no imagen); **convenciones usadas**; **hipótesis comprobadas** con su veredicto |
| **Traza serializable** | Formato textual versionado (clave-valor), con tres niveles de detalle, que el otro laboratorio puede **incrustar** en su propia pantalla sin reescribir los pasos |
| **Plug-in de verificación** | Un laboratorio registra su motor como **segundo camino**: función `verificar(resultado) → veredicto + discrepancia`. Ejemplos: CIRCUITS_LAB registra `ac/bode.py` para comprobar un Bode; SIGNALS_LAB registra `dsp/dft.py`. Si el plug-in falta, el sello baja a `⚠ Solo numérico` |
| **Capa genérica que se ofrece** | Fracciones racionales **multivariable** y forma normal `K·Π(s−z)/Π(s−p)`; raíces con parámetros y desigualdades polinómicas en un parámetro; mínimos cuadrados lineales y **no lineales**; trascendentes con **todas** las raíces; **Lambert W**; **problemas de contorno 1D**; EDO implícitas; convolución por tramos; DFT y propiedades; complejos y matrices unitarias; Monte Carlo sembrado; **análisis dimensional** (§4.7 y §8.2 V) |
| **Qué recibe** | Plantillas de ejercicio y **datos de figuras** (tramos, picos, lecturas) de los otros laboratorios, con la misma plantilla única de §7; nunca modelos físicos |
| **Honestidad y límites** | El mismo mensaje «no sé darte una solución exacta» y los mismos topes de tiempo y cancelación (§5.4) |
| **Versionado** | El contrato lleva número de versión; un cambio incompatible lo incrementa y los laboratorios consumidores lo declaran |
| **Prueba de contrato** | Cada laboratorio consumidor tiene una prueba que invoca una calculadora y comprueba **la forma** de la traza y el sello (no el texto) |

### 5.10 Cambios de arquitectura de la segunda tanda (v2)

1. **Cuerpo como parámetro** del motor lineal (§5.1) y **polinomios sobre GF(p)** como extensión del bloque de polinomios.
2. **Racionales multivariable** (§5.1): la dependencia más repetida de los informes.
3. **Simulador sembrado de eventos** (Markov, MDP y Q-learning, ALOHA y colas si se aceptan, planificador, algoritmo genético): es el «segundo camino» natural ya previsto para Monte Carlo (§8.2 G), generalizado a eventos.
4. **Verificador numérico de gradientes** (diferencias centrales), reutilizable en descenso de gradiente, logística, retropropagación y Markowitz.
5. **Análisis dimensional** como comprobador de constantes y de fórmulas.
6. **Árboles y grafos dibujables** (Huffman, CRR, decisión, MDP, Markov, grafo de acceso): se generalizan los árboles de probabilidad (§6).
7. **Raíces trascendentes con todas las soluciones** (barrido de signo + bisección) y **Lambert W** (§4.7).
8. **Etiquetado de evidencia** por tipo de ejercicio (E o G, §3): al disponer de exámenes de las asignaturas hoy solo con guía, hay que reordenar prioridades.

### 5.11 Convenciones que cada ejercicio declara (v2)

**Requisito del usuario:** las soluciones oficiales y los exámenes **mezclan convenciones** y eso produce errores; por eso cada ejercicio trae un campo `convenciones` que se **imprime en el enunciado y en la solución** y se usa como segundo camino (resolver con la convención contraria y comprobar que el resultado físico coincide, o que difiere exactamente como se espera).

| Convención | Opciones | Dónde pesa |
|---|---|---|
| **Valor eficaz o de pico** | `V_ef` o amplitud; `P = V_ef²/(4·Re Z_g)` o `V_p²/(8·Re Z_g)` | Fasores y potencia: EAFO usa amplitud, otros textos `V_ef`; la potencia media lleva `½` o no |
| **Signo de la exponencial compleja** | `e^{+jωt}` (ingeniería, `j`) o `e^{−iωt}` (física, `i`); coseno o seno como referencia de fase | Signo de la fase, `ε̃ = ε′(1−j·tanδ)`, sentido de giro de la polarización |
| **dB de amplitud o de potencia** | `20·log₁₀` o `10·log₁₀`. **Trampa de enunciado:** «100 veces inferior» es −40 dB en amplitud o −20 dB en potencia (los finales jun-2021 y 2022 de Señales y Sistemas usan una cada uno con `h(t) = e^{−t/10}·u(t)`) | Respuesta en frecuencia, capacidad de canal, enlace |
| **Desviación típica muestral** | `s` con `n` o con `n−1`; `σ` o `σ²`; tasa o media | Estadística descriptiva, intervalos, estimadores |
| **Chauvenet del curso** | Umbral **fijo** `D_max = 3` aplicado de forma **iterativa** (se elimina la lectura más extrema y se recalcula) frente al Chauvenet clásico `N·P(abs(Z) > z) < 0,5`. El motor muestra cuál usa y compara los dos | Preprocesado de datos de medida (el uso concreto vive en CIRCUITS_LAB; la regla de convención es de este laboratorio) |
| **Frecuencia ordinaria o angular** | `X(f) = ∫x·e^{−j2πft}dt` (Señales y Sistemas, Ecuaciones Diferenciales) frente a `ω`; `sinc(x) = sin(πx)/(πx)`; `Π` ancho 1, `Λ` ancho 2 | Todo el bloque 15 |
| **Frecuencia digital normalizada** | `F = f/f_m` de periodo 1; en la DFT `k > N/2` equivale a frecuencia negativa `k − N` | DTFT y DFT |
| **Correlación y potencia** | `r_xy(t) = x(t)*y*(−t)` (energía finita) o `lim (1/T)∫` (potencia finita); `S_x = TF{r_x}` | Bloques 15 y 16 |
| **Resto en la división entera** | `%` no negativo (Python) o con signo (C) | Aritmética modular, cifrados |
| **Base de logaritmos** | `log₂`, `ln` o `log₁₀` (unidad: bit, nat, hartley) | Información, finanzas, dB |
| **Finanzas** | Tasa nominal o efectiva; base de días act/365 o 30/360; con o sin cortos | Bloque 14 |
| **Referencia del potencial** | `V(∞) = 0` solo para distribuciones acotadas; si no, otra referencia declarada | Electrostática |
| **Convención de ReLU en 0, orientación de Stokes, objetos distinguibles o no** | (ya en §15.2) | Redes, vectorial, probabilidad |

La **tolerancia «1 % ≙ 3σ» o uniforme** y el **origen de coordenadas en las líneas** son convenciones de CIRCUITS_LAB y quedan allí.

---

## 6. Gráficas

Un **graficador propio** con Qt (sin dependencias nuevas), reutilizando el dibujo de `ui/waveform.py`:

| Tipo | Usos |
|---|---|
| Funciones y=f(x), varias a la vez | Todo el cálculo de una variable |
| Paramétricas, polares e implícitas | Curvas |
| Sumas de Riemann, Taylor, series de Fourier | Animación del «acercamiento» con el grado o el número de términos |
| **Curvas de nivel** y mapas de calor | Funciones de dos variables |
| **Campos vectoriales 2D** (y de direcciones) | Gradiente, EDO, circulación |
| **Superficies 3D y curvas 3D** | Rotables con el ratón, con ejes, malla y sombreado; planos tangentes |
| **Regiones de integración 3D** | Recintos con cortes y las tres proyecciones |
| Histogramas y distribuciones | Probabilidad y estadística |
| Plano complejo y plano de fases | Complejos, autovalores, sistemas |
| **(v2)** Señales: `stem`, **convolución animada** (`h` reflejada que se desliza), espectro de líneas, `abs(X(F))` y fase en `[−1,1]`, plano z con polos y ceros | Bloque 15 |
| **(v2)** **Árboles y grafos**: Huffman, CRR, decisión, MDP y cadena de Markov (estados y probabilidades), grafo de acceso de Shamir, gridworld | Bloques 10 a 14 |
| **(v2)** Superficie de error con sus elipses y la trayectoria de GD o LMS; curva ROC y densidades con el umbral; curva de aprendizaje; frontera de decisión | Bloques 13 y 16 |
| **(v2)** Diagrama fasorial, **elipse de polarización** y esfera de Poincaré | Bloque 17 |
| **(v2)** Funciones **a trozos con empalme visible**: `E(r)` y `V(r)` por regiones; trazas de una onda en varios sensores con el instante de pico | Bloque 18 |
| **(v2)** Retrato de fases de `U(x)` con niveles de energía; diagramas `p–V` y `T–S` (opcional) | Bloque 19 |
| **(v2)** Tablas de operaciones de ℤₙ y GF(p) con diagonal y ceros marcados; tabla log/antilog de GF(2ᵐ) | Bloque 9 |

Interacción: **zoom, desplazamiento, cursor con valores, exportar** a imagen. Accesibilidad: descripción textual de cada gráfica y no depender solo del color.

Visor 3D (D2, decidido): prototipo propio con Qt (malla, sombreado, ordenación en profundidad, rotación, regiones y normales), medido; si no alcanza calidad y fluidez, se pasa a Qt Quick 3D.

---

## 7. Ejercicios, corrección y generador

- **Plantilla única** de ejercicio (la misma del laboratorio de diseño digital): enunciado, datos, tipo de entrega, solución paso a paso, gráfica esperada, verificación y enlace al tema y la asignatura.
- **Tipos de respuesta:** expresión, número exacto o aproximado, matriz o vector, intervalo o conjunto, gráfica, demostración guiada.
- **Corrección por equivalencia**, no por texto: dos expresiones se consideran iguales si su diferencia se simplifica a 0 o coincide numéricamente en muchos puntos sembrados. Se acepta `2x+2x` por `4x`, y `1/2` por `0,5`.
- **Pistas graduadas** y **modo estudio** (predice el siguiente paso).
- **Generador sembrado** por tema y dificultad, con solución incluida.
- Enlace con el **banco de preguntas y la maestría** ya existentes, con el mismo principio del corrector: determinista, y **el modelo nunca califica**.
- **(v2) Figuras como datos.** Los enunciados reales traen **gráficas** (periódicas, espectros `abs(X[k])`, pulsos, curvas de Bode) que la aplicación no puede leer. El ejercicio ofrece las lecturas (tramos, picos, `k`, valores, `N`) como **datos de entrada** y genera la gráfica como comprobación. Si el enunciado y la figura discrepan (`N = 1000` en el texto y `N = 1500` en la figura), el sistema **avisa** de la inconsistencia (§11.4).
- **(v2) Soluciones no únicas.** Algunas respuestas no son únicas (una base ortonormal, una señal base, un diseño por Ackermann o por coeficientes): la corrección compara **propiedad o respuesta** (autovalores, misma TF, misma curva), nunca la forma.
- **(v2) Convenciones.** El corrector recibe las convenciones del ejercicio (§5.11) y acepta la equivalente en la otra convención solo si se declaró.
- **(v2) Respaldo visible.** Cada ejercicio muestra su insignia **E** o **G** (§3), para que el alumno sepa si el tipo sale en exámenes reales.

---

## 8. Calculadoras

**Requisito del usuario:** se hacen **todas** las calculadoras posibles, **aunque no salgan en los exámenes**, porque el usuario las necesita para otras cosas. **Todas muestran el resultado paso a paso** (con el «por qué este método» de §5.5b, los cambios de variable de §5.6 y las hipótesis de §5.7) y **todas se verifican** por un segundo camino (§5.3). Lo que los exámenes no usan (§15.3) afecta solo al **orden** de construcción de los *ejercicios*; **no recorta ninguna calculadora**.

### 8.1 Reglas comunes a todas

| Regla | Detalle |
|---|---|
| Entrada | Texto con vista previa en notación matemática; acepta `x^2`, `sqrt(x)`, `sen`/`sin`, `e^x`, `pi`, `i`/`j`; errores en castellano que dicen dónde está el fallo |
| Salida | **Resultado exacto** (fracciones, raíces, π, e) y, si se pide, aproximado con el número de cifras elegido y su error |
| Pasos | Siempre disponibles con tres niveles: **Resumen**, **Paso a paso**, **Detallado** (con justificación formal) |
| Verificación | Sello visible: `✔ Verificado (derivando la primitiva)`, `⚠ Solo numérico`, `✘ Discrepa`; si discrepa, no se da por bueno |
| Honestidad | Si no se sabe resolver de forma exacta: «no sé darte una primitiva exacta», con valor numérico y error (§5.4) |
| Gráfica | Cada calculadora ofrece su gráfica asociada (función y derivada, área, región, campo…) |
| Historial | Todas las operaciones quedan guardadas y se pueden repetir, editar y comparar |
| Reutilización | **Copiar** el resultado o los pasos como texto, Markdown o LaTeX; **enviar** el resultado a otra calculadora, al editor de ejercicios o a **otros laboratorios** (p. ej. la función de transferencia de Laplace al laboratorio de control) |
| Uso por programa | Cada calculadora es una función del dominio con entrada y salida tipadas, invocable desde cualquier otra parte de la aplicación sin pasar por la interfaz (así el resto de laboratorios puede pedir «deriva esto con pasos») |
| Variables y constantes | Variables con nombre, asignación de valores, constantes definidas por el usuario y **memoria** de resultados anteriores |
| Límites | Tope de tiempo y tamaño con cancelación y progreso |
| **(v2)** Convenciones | Toda calculadora cuyo resultado dependa de una convención (§5.11) tiene un campo `convención`, la imprime y ofrece la verificación con la contraria |
| **(v2)** Contrato | Toda calculadora cumple el contrato de §5.9: devuelve resultado, traza serializable, sello y gráfica descrita, y acepta plug-ins de verificación de otros laboratorios |
| **(v2)** Respaldo | Cada tipo de ejercicio asociado a la calculadora lleva su insignia **E** o **G** (§3) |

### 8.2 Catálogo de calculadoras

#### A. Aritmética y álgebra elemental

| Calculadora | Pasos que muestra |
|---|---|
| Operaciones básicas | Suma, resta, producto y **división larga** con llevadas, como en papel |
| Fracciones | Simplificar, operar, comparar, pasar a decimal y a periódico |
| Potencias, raíces y logaritmos | Propiedades aplicadas una a una; racionalización; cambio de base |
| Porcentajes y proporciones | Regla de tres, variación porcentual, interés simple y compuesto |
| MCD, MCM y factorización en primos | Algoritmo de Euclides y árbol de factores |
| Bases de numeración | Conversión con pasos (enlaza con el laboratorio digital) |
| Polinomios | Suma, producto, **división, Ruffini, factorización**, raíces, identidades notables |
| Ecuaciones e inecuaciones | Lineales, cuadráticas, valor absoluto, racionales, irracionales, exponenciales, logarítmicas y trigonométricas, con comprobación |
| Sistemas de ecuaciones | Sustitución, igualación, reducción y Gauss, lineales y no lineales sencillos |
| Combinatoria | Factoriales, permutaciones, variaciones, combinaciones, con y sin repetición |
| Progresiones y sumatorios | Fórmula cerrada y demostración por pasos |
| Desigualdades y valor absoluto | Solución sobre la recta real |
| Cotas racionales | Justifica desigualdades como `2√2 < π` o `e < 3` sin calculadora |
| **(v2)** Binomio, Pascal y números combinatorios | Término general, coeficiente de `xᵏ`, identidades, con evaluación en un punto como comprobación |
| **(v2)** Divisibilidad ampliada | σ(n), números perfectos, criba de Eratóstenes, primalidad hasta √n con el número de operaciones contado, dígitos y letra del DNI |
| **(v2)** Impuestos por tramos y cambio de monedas | Función a trozos con tramos **marginales** (no confundir con tipo único); voraz frente a programación dinámica |
| **(v2)** Bases: máscaras y direccionamiento IPv4 (el complemento a 2 es de `DIGITAL_DESIGN_LAB.md` §10) | AND/OR/XOR/desplazamiento; red, difusión y número de hosts `2^(32−p)−2` |

#### B. Funciones y trigonometría

| Calculadora | Pasos que muestra |
|---|---|
| Dominio y recorrido | Condiciones que restringen el dominio, una a una |
| Composición, inversa y simetrías | Despeje de la inversa; paridad |
| Transformaciones de gráficas | Desplazar, escalar, reflejar, con dibujo |
| Identidades y ecuaciones trigonométricas | Identidad aplicada en cada paso; soluciones generales |
| Resolución de triángulos | Teoremas del seno y del coseno |
| Funciones hiperbólicas | Definiciones e identidades |

#### C. Cálculo de una variable

| Calculadora | Pasos que muestra |
|---|---|
| **Derivadas** | Cada regla (suma, producto, cociente, **cadena**, potencia, exponencial, logarítmica, trigonométricas, inversas e hiperbólicas), **derivación implícita**, **logarítmica**, por la **definición** (límite del cociente incremental), de orden n, de funciones paramétricas y polares, en un punto |
| **Recta tangente y normal** | Derivada en el punto y ecuación |
| **Límites** | Por sustitución, **indeterminaciones** (0/0, ∞/∞, ∞−∞, 1^∞, 0·∞, 0⁰, ∞⁰) con **L'Hôpital, Taylor o equivalentes** y el motivo de cada elección, laterales y en el infinito |
| Continuidad | Tipo de discontinuidad; continuidad con parámetros |
| **Estudio completo de una función** | Dominio, cortes, simetrías, asíntotas, crecimiento, extremos, concavidad, inflexión y **gráfica final** |
| Extremos absolutos en un intervalo | Lista de candidatos y por qué se aplica Weierstrass |
| **Polinomio de Taylor y resto** | Derivadas en el punto, resto de Lagrange con **cota del error**, gráfica función frente a Taylor |
| **Integrales indefinidas (primitivas)** | Inmediatas, **por partes** (qué `u` y por qué), **por cambio de variable** (§5.6), **fracciones simples**, trigonométricas, irracionales, sustituciones de Euler y trigonométricas |
| **Integrales definidas** | Teorema fundamental del cálculo, áreas, áreas entre curvas |
| **Integrales impropias** | De primera y segunda especie, criterios de convergencia, **con parámetro**, función gamma y beta |
| Sumas de Riemann | Izquierda, derecha, punto medio, con animación |
| Aplicaciones de la integral | Volúmenes de revolución, longitud de arco, área de revolución, valor medio, centro de masas |
| **Series numéricas** | Criterios (término general, razón, raíz, comparación, integral, Leibniz, absoluta) eligiendo y justificando; **suma** por geométrica, telescópica o Taylor |
| **Series de potencias** | **Radio e intervalo de convergencia**, extremos, derivación e integración término a término, desarrollo de funciones |
| Sucesiones | Límite, monotonía, cotas, recurrentes |
| Números reales | Supremo, ínfimo, máximo, mínimo |

#### D. Álgebra lineal y complejos

| Calculadora | Pasos que muestra |
|---|---|
| **Números complejos** | Formas binómica, polar y exponencial; operaciones, **potencias y raíces**, fórmula de Euler; en el **plano complejo** |
| **Matrices** | Suma, producto, transpuesta, traza, potencias, **inversa**, **determinante** (Laplace, Sarrus, por eliminación), **rango**, forma escalonada |
| **Sistemas lineales** | **Gauss y Gauss-Jordan**, Cramer, **discusión con parámetros por casos**, interpretación geométrica |
| Espacios vectoriales | Independencia, base, dimensión, coordenadas, **cambio de base**, suma e intersección de subespacios |
| Aplicaciones lineales | Matriz asociada, **núcleo e imagen**, inyectividad, composición |
| **Valores y vectores propios** | Polinomio característico, raíces (exactas o numéricas, sobre R y C), espacios propios, **diagonalización**, potencias y exponencial de una matriz |
| Espacio euclídeo | **Producto escalar con matriz de Gram cualquiera**, norma, ángulo, **Gram-Schmidt**, **proyección ortogonal**, distancia mínima |
| **Diagonalización ortogonal y teorema espectral** | Ortonormalización dentro de espacios propios múltiples |
| **Descomposición en valores singulares (SVD)** y **pseudoinversa** | Desde `AᵀA`, completar `U` |
| Mínimos cuadrados | Ajuste de recta, parábola y funciones, ecuaciones normales |
| Formas cuadráticas | Clasificación (Sylvester, autovalores), cónicas y cuádricas con dibujo |
| Vectores | Producto escalar, vectorial, mixto, ángulo, proyección, áreas y volúmenes |
| Otras descomposiciones | LU, QR, Cholesky, Jordan |
| **(v2)** **Gauss, rango, núcleo, inversa y determinante sobre un cuerpo** | La misma calculadora de matrices y sistemas con el parámetro **cuerpo** (ℚ, ℝ, ℂ, GF(p), GF(2)); en GF(2) con XOR; hipótesis del cuerpo comprobadas (§5.7) |
| **(v2)** **PCA** | Centrar, covarianza, autovalores, varianza explicada, reconstrucción; contraste con la SVD (calculadora O) |
| **(v2)** **Elipse de una matriz real 2×2 y matrices unitarias** | Semiejes y orientación por SVD; unitariedad `UᴴU = I` (usado en polarización, calculadora S) |

#### E. Cálculo vectorial y en varias variables

| Calculadora | Pasos que muestra |
|---|---|
| **Derivadas parciales** | Cada parcial, de orden superior, **teorema de Schwarz**, regla de la cadena en varias variables |
| **Gradiente, derivada direccional, jacobiana, Hessiana** | Cálculo y significado geométrico; **plano tangente** |
| **Diferenciabilidad** | Por definición en un punto (parciales, criterio de tangencia, polares y trayectorias) |
| Límites y continuidad en varias variables | Límites direccionales, por polares, por acotación |
| **Función implícita y función inversa** | Hipótesis (jacobiano no nulo), derivadas de la función implícita, sistemas |
| **Extremos** | **Puntos críticos**, clasificación con la Hessiana (Sylvester y autovalores), **puntos de silla**, extremos **condicionados con Lagrange**, extremos absolutos en un recinto (interior y frontera por piezas) |
| Curvas y superficies | **Parametrización**, regularidad por el rango del jacobiano, tangente y plano normal, longitud y área |
| **Integrales dobles** | Fubini, **cambio de orden**, **cambio a polares u otras coordenadas con jacobiano** (§5.6), región dibujada |
| **Integrales triples** | Orden, **cilíndricas y esféricas** con su jacobiano, volumen, masa, centro de masas, momentos de inercia |
| **Integrales de línea** | De función escalar y **circulación** de un campo, **independencia del camino**, **potencial escalar**, campos conservativos |
| **Integrales de superficie** | De función escalar y **flujo**, vector normal y orientación |
| **Divergencia y rotacional** | Cálculo e interpretación; potencial vectorial |
| **Teoremas de Green, Stokes y Gauss** | Hipótesis comprobadas, **los dos lados calculados** y comparados |
| Cambios de coordenadas | Polares, cilíndricas, esféricas y generales, con jacobiano |
| **(v2)** **Operadores ∇ en cilíndricas y esféricas** | Gradiente, divergencia, rotacional y laplaciano con factores de escala `h_i`; Poisson `∇²V = −ρ/ε₀`; `∇·(∇×F) = 0` como control |
| **(v2)** **Cambio de componentes entre bases** | Rotación de bases ortogonal; `abs(E)` invariante, `RᵀR = I`, ida y vuelta |
| **(v2, D12)** **Cinemática intrínseca** | `T`, `N`, `κ`, `a_t`, `a_n` y descomposición de `a` sobre la trayectoria |

#### F. Ecuaciones diferenciales y transformadas

| Calculadora | Pasos que muestra |
|---|---|
| **EDO de primer orden** | Reconoce el tipo (separable, lineal, exacta con factor integrante, homogénea, Bernoulli, sustituciones) y explica cómo; PVI; campo de direcciones |
| **EDO lineales de orden n** | Ecuación característica, coeficientes indeterminados (resonancia, raíces múltiples y complejas), variación de parámetros, reducción de orden, Wronskiano |
| **Sistemas de EDO** | Autovalores (real, complejo, defectivo), exponencial de matriz, **plano de fases** y estabilidad |
| **Transformada de Laplace** y su **inversa** | Definición, propiedades, tabla, fracciones simples, raíces múltiples y complejas, funciones a trozos, **escalón y delta**, convolución, **resolver EDO y PVI**, región de convergencia |
| **Series de Fourier** | Coeficientes, par e impar, desarrollo en senos o cosenos, **sumas parciales** dibujadas, Parseval y sumas numéricas |
| **Transformada de Fourier** y su inversa | Por definición y por propiedades, Parseval, convolución, gaussianas |
| **Transformada z** y su inversa | Propiedades, **región de convergencia**, ecuaciones en diferencias, `H(z)` y `h[n]`, convolución discreta |
| Métodos numéricos para EDO | Euler, Euler mejorado, Runge-Kutta, con error frente a la solución exacta |
| EDP introductoria | Separación de variables (calor, ondas, Laplace) |
| Espacios de Hilbert | Mejor aproximación, Gram-Schmidt con producto integral |
| **(v2)** **Problemas de contorno 1D** | `cosh`/`sinh` con condiciones en dos extremos, existencia y unicidad, asíntotas, Poisson 1D por tramos con empalme, contraste por diferencias finitas tridiagonales (§4.5) |
| **(v2, D12)** **Oscilador con Q y conducción de calor 1D** | Régimen de amortiguamiento, `Q`, resonancia; calor por separación de variables introductoria |

#### G. Probabilidad y estadística

| Calculadora | Pasos que muestra |
|---|---|
| Probabilidad básica | Espacio muestral, **probabilidad condicionada, total y Bayes** con árbol, independencia |
| **Distribuciones** | Bernoulli, binomial, geométrica, Poisson, hipergeométrica, uniforme, exponencial, gamma, normal, t de Student, chi-cuadrado, F, beta, Weibull…: densidad, **distribución acumulada**, **cuantiles**, media, varianza, con **área sombreada** |
| Aproximaciones | Normal a binomial y Poisson con corrección de continuidad; comparación con el valor exacto |
| Variables aleatorias | Esperanza, varianza, momentos, Chebyshev, función generatriz, **transformaciones** de variables (jacobiano, máximo, mínimo, suma por convolución) |
| Vectores aleatorios | Conjunta, marginales, condicionadas, covarianza, correlación, **vectores gaussianos**, regresión y estimación lineal |
| **Estadística descriptiva** | Media, mediana, moda, cuartiles, varianza (con n y con n−1, declarado), histogramas, boxplots, dispersión |
| **Estimación e intervalos de confianza** | Momentos, máxima verosimilitud (con la log-verosimilitud dibujada), intervalos para media, varianza, proporciones y diferencias, **tamaño de muestra**; elección t o z justificada |
| Contrastes de hipótesis | Test z, t, chi-cuadrado, p-valor (aunque no salgan en los exámenes) |
| Regresión y correlación | Recta de mínimos cuadrados, coeficientes, residuos |
| **Procesos estocásticos** | Media, autocorrelación, estacionariedad, **Poisson**, gaussianos, realizaciones sembradas |
| Simulación | Monte Carlo con semilla explícita para contrastar cualquier resultado |
| Tablas estadísticas | Normal, t, chi-cuadrado y F **calculadas**, con el valor «de tabla» redondeado y el exacto |
| **(v2, D12)** Comunicaciones | BER con `Q`, ALOHA, Rayleigh y Rice, eficiencia de ARQ con sus hipótesis |

#### H. Métodos numéricos

Raíces (bisección, Newton, secante, punto fijo), sistemas (LU, Jacobi, Gauss-Seidel), interpolación (Lagrange, Newton, splines), mínimos cuadrados, derivación e **integración numérica** (trapecios, Simpson, cuadratura), EDO numéricas. Todos con error, convergencia y gráfica de las iteraciones. **(v2)** Se añaden: mínimos cuadrados **no lineales** (Gauss-Newton) y linealización por transformación; trascendentes con **todas las raíces**; **Lambert W**; EDO **implícitas** con estabilidad absoluta; sumatorio con error (serie de `e` y de `sen x` por Taylor con `N` términos).

#### I. Utilidades generales

**Calculadora científica** con historial y memoria; **conversor de unidades** (con análisis dimensional, reutilizando `units.py`); **despeje** de una variable en una fórmula; **simplificación y factorización** de expresiones; **evaluación** con valores; **sumatorios y productorios**; **tablas de valores** y gráficas rápidas; conversión de bases; números grandes exactos; **(v2, D12)** **SQNR** `6,02·b + 1,76 dB` (la teoría y el visor de cuantización son de SIGNALS_LAB §16).

#### J. Matemática discreta (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Tablas de verdad y equivalencias | Ley aplicada en cada paso; negación de cuantificadores; enumeración de las 2ⁿ valoraciones como comprobación |
| Conjuntos e inclusión-exclusión | Cardinal por fórmula y por enumeración; Venn |
| Plantilla de inducción | Caso base, hipótesis, paso, conclusión; verificación numérica para `n = 1..N` (no demuestra: avisa) |
| Recurrencias y teorema maestro | Característica, iteración o teorema maestro con el motivo de la elección; iteración frente a cerrada |
| Complejidad y conteo de operaciones | Sumatorio del bucle, término dominante, cota con `n₀`, contador instrumentado |
| **(v2, D12)** Tiempo real | Utilización, Liu-Layland (suficiente, no necesaria), RTA por punto fijo, hiperperiodo, Gantt |

#### K. Aritmética modular y cuerpos finitos (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Euclides extendido y congruencias | Cocientes, combinación `a·s + b·n = 1`, inverso, `a·x ≡ b` con número de soluciones, CRT |
| Potencia modular, Fermat, φ de Euler, orden y raíz primitiva | Cada cuadrado y producto; teorema aplicado con su hipótesis |
| Tablas de ℤₙ y GF(p) | Suma y producto, inversos, ¿cuerpo? |
| **Gauss sobre GF(p) y GF(2)** | Calculadora D con el parámetro cuerpo |
| GF(2ᵐ) y polinomios sobre GF(p) | Reducción por el irreducible, tabla log/antilog, inverso, irreducibilidad |
| Cifrado clásico | César, afín, Vigenère, Hill; cifrar, descifrar, `k` y `k+26` |
| Hash y cumpleaños | `h(k) = k mod m`, sondeos, factor de carga, `1 − Π(1 − i/m)` |

#### L. Códigos, secretos y clave pública (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Código lineal | `G ↔ H`, palabras, `d_min`, capacidad, síndrome y corrección con aviso si hay más de `t` errores |
| CRC, paridad, checksum, Hamming(7,4) | División polinómica con XOR, trama completa y comprobación de resto 0 |
| Shamir `(t, n)` sobre GF(p) | Reparto, reconstrucción por Lagrange, dos subconjuntos y `t−1` partes |
| Esquema lineal vectorial GF(2) | Conjuntos autorizados, monotonía, reconstrucción |
| RSA, firma, Diffie-Hellman | `p, q, φ, e, d`, cuadrados sucesivos; aviso «solo pedagógico» |
| **(v2, D12)** Privacidad | k-anonimato, microagregación, mecanismo de Laplace; aviso «solo pedagógico» |

#### M. Teoría de la información (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Entropía, información mutua, `D(p‖q)`, entropía cruzada | Tabla, `log₂`, propiedades y regla de la cadena |
| Huffman y Kraft | Árbol paso a paso, `L̄`, eficiencia, decodificación |
| Capacidad de canal | BSC, BEC, Shannon-Hartley con SNR en dB declarado |
| Entropía de claves y cumpleaños | `log₂` por dos caminos |

#### N. Markov, MDP y refuerzo (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Cadena de Markov | `π·Pⁿ`, estacionaria, clasificación, absorción `(I−Q)⁻¹`, simulación sembrada |
| MDP y Bellman | Evaluación `(I−γP)⁻¹R`, iteración de valor y de política, política voraz, residuo |
| MC, TD, SARSA, Q-learning | Episodio dado a mano, tabla `Q`, off-policy frente a on-policy |
| Bandidos | ε-greedy, UCB, Q incremental, simulación |
| **Simulador sembrado de eventos** | Núcleo común para contrastar cualquier resultado del bloque (§5.10) |

#### O. Optimización y aprendizaje automático (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Descenso de gradiente y variantes | Iteraciones a mano, `η`, trayectoria sobre curvas de nivel, condición `η < 2/L` |
| Regresión múltiple, polinómica, ridge, lasso, logística y softmax | Ecuaciones normales, `R²`, soft-threshold, frontera, validación cruzada |
| Métricas de clasificación | Confusión, F1, ROC y AUC |
| k-medias, EM de mezcla gaussiana, BIC, silueta | Iteración a iteración con SSE o `log L` |
| Árboles de decisión | Entropía, Gini, ganancia |
| Redes neuronales a mano | Propagación, retropropagación con `δ`, conteo de parámetros, tamaños de convolución, atención |
| **Verificador de gradientes** | Diferencias centrales frente al gradiente analítico (reutilizable) |

#### N. Cadenas de Markov, MDP y refuerzo (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Cadenas absorbentes | `N = (I−Q)⁻¹` con los transitorios declarados |
| Clasificación de estados | Alcanzabilidad, clases, recurrentes/transitorios, periodo por mcd |
| Evaluación de política | `v = (I−γP)⁻¹R` exacto, una ecuación de Bellman por estado |
| Iteración de valor | Barrido hasta tolerancia y política voraz |
| Episodio a mano | MC, TD(0), SARSA y Q-learning sobre el mismo episodio |
| Bandidos | Incremental, ε-greedy y UCB con tablas `Q`/`N` |
| REINFORCE | Softmax con baseline y su gradiente |
| **Hecho** | Los 7 cálculos de `refuerzo` (ML-20); `markov` y `cola_mm1` de ML-12 se reutilizan |

#### P. Matemáticas financieras (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Interés, anualidades, amortización | Capitalización y descuento, tabla de amortización con saldo final 0 |
| VAN y TIR | Línea temporal, bisección, aviso de Descartes |
| Bonos | Precio, duración de Macaulay y modificada, convexidad (YTM no se resuelve) |
| Futuros y arbitraje | `F = S₀·e^{rT}` y la cartera replicante |
| Opciones | Payoff, árbol CRR, americana, paridad, Black-Scholes, griegas, volatilidad implícita, Monte Carlo |
| Markowitz | KKT, mínima varianza, **frontera eficiente por barrido de `m`**, Sharpe, VaR gaussiano |
| **Hecho** | Los 15 cálculos de `finanzas` (ML-21), con `frontera` incluida |

#### S. Ejercicios, corrector y generador (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Plantilla de ejercicio | Enunciado, datos, tipo de entrega, pistas, insignia E/G y dificultad |
| Generador sembrado | Un ejercicio por tema, dificultad y semilla, con su solución y sus pasos |
| Corrector por equivalencia | Formas normales, no texto; el sello baja si solo hay coincidencia numérica |
| Corrección por propiedad | Para lo que no tiene respuesta única (`Aᵀ·A = I`) |
| Pistas graduadas | De menos a más ayuda, y solo las `n` primeras |
| **Hecho** | Los 5 cálculos de `ejercicio` (ML-10) sobre 7 temas |

#### T. Pulido, accesibilidad y certificación (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Accesibilidad de un resultado | Que la gráfica se entiende sin verla; sin descripción o sin nombre de serie se rechaza |
| Volcado a texto | El resultado entero: valor, pasos, sello, hipótesis, convenciones y gráfica |
| Rendimiento y determinismo | Tiempo real contra el techo de §5.4, y que la misma entrada da lo mismo |
| Auditoría de §8.4 | Los nueve criterios, una operación cada vez |
| **Hecho** | Los 5 cálculos de `pulido` (ML-11), con gate propio |

#### Q. Señales y sistemas deterministas (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Biblioteca de señales | `δ, u, Π, Λ, sinc, p_L[n]`; transformaciones del eje |
| Convolución analógica por tramos y digital | Puntos de ruptura, integrales por intervalo, regímenes, comprobación `∫y = ∫x·∫h` |
| Periódicas por señal base | `c_k`, TF de deltas, potencia por Parseval, otra señal base |
| Energía, potencia, correlación y densidad espectral | Tiempo y frecuencia, Wiener-Khinchin |
| DTFT | `P_L(F)`, módulo y fase, salida a sinusoides, Parseval |
| DFT y circular frente a lineal | Elección de `N`, relleno, aliasing temporal, retardo, simetría hermítica |
| Eco, reverberación e inverso | `H(z)`, ceros en `abs(z) = abs(a)^{1/L}`, `abs(H(F))`, inverso causal y su estabilidad |

#### R. Detección y estimación (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Matriz de correlación y PSD teórica | Toeplitz, semidefinida positiva, salida de un sistema, `S(F)` y `S_y = S_x·abs(H)²` |
| Detección | LRT, MAP, Bayes, Neyman-Pearson, `P_FA` y `P_D`, ROC |
| Fisher y Cramér-Rao | Log-verosimilitud, `I(θ)`, cota, eficiencia |
| ML, MAP y MMSE | Estimador y error, ortogonalidad |
| Wiener y mínimos cuadrados | `R·w = p`, `J_min`, residuos ortogonales |
| Gradiente, LMS y NLMS | Modos `(1−μλᵢ)ᵏ`, cotas de `μ`, curva de aprendizaje sembrada |

#### S. Fasores y polarización (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Fasores | Fasor ↔ tiempo, suma de sinusoides, problema inverso, convención declarada y contraria |
| Onda plana y potencia media | `k, λ, v, η`, `⟨S⟩`, potencia captada, promedio temporal como comprobación |
| Medios con pérdidas | Exacto con rama de raíz, aproximado con su condición y error relativo, Np ↔ dB |
| Polarización y Jones | Clasificación, relación axial, elipse por SVD, retardadores, cascada, diseño por ecuaciones trigonométricas |
| **(v2, D12)** Fresnel y multicapa | `r_s, r_p`, Brewster, ángulo crítico y evanescente, matrices de transferencia, antirreflejante, `R + T = 1` |

#### T. Campos y ondas (v2)

| Calculadora | Pasos que muestra |
|---|---|
| Carga total | `dl, dS, dτ` con jacobiano, constante `a` con análisis dimensional |
| Gauss y potencial por regiones | `Q_enc(r)`, `E(r)`, `V(r)` con empalme, conductores y tierra, energía por dos fórmulas |
| `V` dado | `E = −∇V`, `ρ = −ε₀∇²V`, flujo cara a cara frente a Gauss |
| Maxwell y ecuación de onda | Sustitución de las cuatro ecuaciones, `c`, completar componentes, perfiles `f(t−x/v)`, energía por área, trazas en sensores |
| **(v2, D12)** Coulomb, Biot-Savart y Ampère | Integración por componentes, polígono → círculo, límites lejanos |
| **(v2, D12)** Condensadores y dieléctricos | `C` por regiones y capas, `D`, energía por dos caminos |
| **(v2, D12)** Inducción y Poynting | Faraday con Lenz, inductancia mutua, balance de Poynting |
| **(v2, D12)** Antenas y enlace | Directividad, Friis, balance en dB con convención declarada, `G/T`, factor de array |

#### U. Mecánica 1D y termodinámica (v2, esta última opcional)

| Calculadora | Pasos que muestra |
|---|---|
| Equilibrio y oscilaciones desde `U(x)` | Equilibrios, estabilidad, `ω`, confinamiento, periodo por cuadratura frente a integración numérica |
| Procesos de gas ideal (opcional) | `W, ΔU, Q, T_max, ΔS`, ciclos, función de estado por dos caminos |
| **(v2, D12)** Órbitas y visibilidad | Kepler por barrido y Newton, `T`, energía, visibilidad esférica |
| **(v2, D12)** Maxwell-Boltzmann, Planck y Stefan (opcional) | Momentos de `f(v)`, integral de Planck, ley de Stefan |

#### V. Capa genérica para otros laboratorios (v2)

Interfaz de §5.9; sin modelos de ingeniería.

| Calculadora | Pasos que muestra |
|---|---|
| **Fracciones racionales multivariable** | Simplificar, forma normal `K·Π(s−z)/Π(s−p)`, polos y ceros con parámetros, discusión por casos |
| Raíces con parámetros | Raíces simbólicas o numéricas; desigualdades polinómicas en un parámetro |
| Mínimos cuadrados lineales y no lineales | Gauss-Newton con diagnóstico, linealización por transformación, minimax |
| Trascendentes con todas las raíces; Lambert W | Barrido de signo, bisección, Newton; ramas 0 y −1 |
| Problemas de contorno 1D | `cosh`/`sinh`, empalmes, diferencias finitas |
| EDO implícitas | Euler implícito, trapezoidal, estabilidad absoluta |
| **Análisis dimensional** | Dimensiones de cada término y de cada constante |
| Funciones especiales (biblioteca comprobadora) | Bessel, `I₀`, `K(k)`; sin teoría |

### 8.3 Cómo se construyen

- Cada calculadora es una función del **dominio** (sin Qt) con entrada y salida tipadas, que devuelve **resultado + traza de pasos + sello de verificación + gráfica descrita**; la interfaz solo la muestra.
- Las calculadoras que comparten motor (derivar, integrar, transformar) se construyen **sobre el mismo núcleo de reglas**, de modo que un paso se escribe una vez y lo usan todas.
- **Se entregan con cada fase** del plan (§10): cada fase incluye las calculadoras de su bloque, completas y con pasos, sin esperar a los ejercicios.
- Todas pasan la **misma batería de pruebas**: propiedades con semilla (p. ej. `derivar(integrar(f)) ≡ f`), ejemplos dorados y, si están instaladas, contraste con SymPy, NumPy o SciPy (§5.8).

### 8.4 Criterios de aceptación de las calculadoras

1. Toda calculadora de este catálogo existe, tiene modo paso a paso y sello de verificación.
2. Ningún resultado se da por correcto sin segundo camino.
3. Los pasos de derivar, integrar, límites, series, ecuaciones diferenciales y transformadas nombran la regla y explican **por qué se eligió**.
4. Toda sustitución o cambio de variable muestra por qué, el cambio, el diferencial o jacobiano, los límites nuevos y la validez.
5. Los resultados se pueden **copiar, exportar y enviar** a otras calculadoras y a otros laboratorios, y se pueden pedir **por programa** sin la interfaz.
6. Cuando no hay solución exacta, se dice y se da el valor numérico con su error.
7. **(v2)** Toda calculadora cuyo resultado dependa de una convención la declara y verifica con la contraria (§5.11).
8. **(v2)** Toda calculadora cumple el contrato de §5.9 y puede pedirse desde SIGNALS_LAB, CIRCUITS_LAB o el laboratorio digital sin pasar por la interfaz.
9. **(v2)** Las calculadoras de los bloques con respaldo **E** (15, 17, 18, `U(x)` del 19 y la parte de César del 9) se entregan **antes** que las de respaldo **G**, pero **ninguna se recorta** (regla del usuario de §8).

---

## 9. Interfaz

Pestañas por bloque (0 a 7, y **8 a 19 en v2**, agrupadas en «Discreta y códigos», «Datos e IA», «Señales y detección», «Campos y física») más **Calculadoras** y **Ejercicios**. Cada ejercicio muestra su insignia de respaldo (**E** examen, **G** guía) y sus convenciones declaradas. Un **editor de fórmulas** con vista previa, **panel de pasos navegable** (anterior, siguiente, reproducir) que resalta el trozo afectado, y **gráfica enlazada** a cada resultado. Todo operable con teclado; español.

---

## 10. Fases de entrega

Orden pensado para que lo **de más uso** llegue antes y cada fase sea demostrable.

| Fase | Contenido | Esfuerzo |
|---|---|---|
| **ML-0** Cimientos | Expresiones con varias variables, entrada de texto con vista previa, traza de pasos, corrector por equivalencia, graficador 2D (la ampliación de v2, con racionales multivariable, cuerpo como parámetro y contrato, es **ML-12**) | L |
| **ML-1** Aritmética y álgebra elemental | Bloque 0 completo, con sus ejercicios y generador | M |
| **ML-2** Funciones y cálculo de una variable | Bloques 1 y 2: límites, derivadas, Taylor, estudio de funciones, primitivas, Riemann, impropias | XL |
| **ML-3** Álgebra lineal | Complejos, matrices, espacios, autovalores; gráficas 2D y 3D básicas. **Implementado (2026-10-06):** característico n×n (hasta 6×6, Faddeev-Leverrier), autovalores exactos con multiplicidad (racionales por Ruffini, ℚ(√r) y pares complejos exactos; factor irreducible de grado ≥ 3 → numérico declarado), autovectores por Gauss, diagonalización con A·P = P·D, Gram-Schmidt, Cramer, mínimos cuadrados y pseudoinversa de Moore-Penrose de cualquier rango (A = C·R, cuatro condiciones de Penrose); **espacios vectoriales** (suma/intersección con Grassmann, cambios de base por la canónica, núcleo/imagen/antiimágenes, proyección ortogonal, complemento y distancia, invariantes, independencia con un parámetro, valores singulares); calculadoras `algebra`, `gamma` y `espacios` | L |
| **ML-4** Series y métodos numéricos | Series, radio de convergencia, bisección, Newton, Simpson, EDO numéricas; **v2:** capa genérica (mínimos cuadrados no lineales, trascendentes con todas las raíces, Lambert W, EDO implícitas) **Implementado (2026-10-06):** radio e intervalo de convergencia de Σcₙ(x−c)^(kn) (cociente, raíz, extremos por los criterios de series y Raabe; radio comprobado con factoriales enteros y Richardson), secante, regula falsi (Illinois), todas las raíces en [a, b] (Sturm si es polinómica; barrido + Brent + raíces dobles por f′), Lambert W ramas 0 y −1 (Halley) y a·x·e^(bx) = c, LU exacta con pivoteo (PA = LU), Jacobi y Gauss-Seidel con ρ(B), Newton por diferencias divididas, ajuste polinómico exacto, linealizaciones, Gauss-Newton, recta minimax, EDO (Euler, Heun, RK4, Euler implícito, trapecio) con orden observado, estabilidad |R(hλ)| y rigidez; calculadora `numericos` | M |
| **ML-5** Varias variables | Gradiente, extremos, Lagrange; curvas de nivel y visor 3D. **Implementado (2026-10-06):** límites por caminos (no existencia probada; coincidencia = indicio declarado), derivada direccional, jacobiana, cadena con equivalencia exacta, implícita con identidad, Hessiana con Sylvester (silla en n > 2 por Descartes) y Taylor-2, puntos críticos y Lagrange **no lineales** por bases de Gröbner (`sistemas.py`: coordenadas exactas racionales o con √, numéricas si no; varias ligaduras; aviso de puntos singulares de la ligadura), Weierstrass en rectángulos y en regiones {g ≤ 0} acotadas; calculadora `multivar` | L |
| **ML-6** Integración múltiple | Dobles y triples, cambio de orden, jacobianos, regiones 3D. **Implementado (2026-10-06):** iteradas exactas con límites variables (Fubini, primitivas comprobadas derivando, Barrow simbólico) y segundo camino por cuadratura tanh-sinh anidada; polares, cilíndricas y esféricas con jacobiano y validez del cambio; cambio de orden de tipo I a franjas de tipo II con los dos órdenes comparados; masa y centro de masas; calculadora `multiple` | XL |
| **ML-7** Línea, superficie y teoremas | Integrales de línea y de superficie, conservativos, Green, Stokes y Gauss, con comprobación por los dos lados. **Implementado (2026-10-06):** circulación y ∫ f ds por curvas parametrizadas a trozos, rotacional y divergencia, potencial con rot F = 0 comprobado y ∇φ = F verificado (segundo camino φ(B) − φ(A)), flujo y ∬ f dS con normal r_u × r_v y orientación elegible, |r′| y |N| exactos cuando son cuadrados perfectos; Green, Stokes y Gauss calculan los dos lados y los comparan (una orientación equivocada sale como discrepancia, no se tapa); calculadora `vectorial` | XL |
| **ML-8** Ecuaciones diferenciales y transformadas | EDO, Laplace, Fourier, transformada z, plano de fases; **v2:** problemas de contorno 1D y Poisson 1D por tramos; **oscilador con Q y conducción de calor 1D (D12)** **Implementado (2026-10-06):** EDO de primer orden (lineal, separable, Bernoulli, exacta con μ(t)/μ(y)/μ mixto, homogénea, homogénea desplazada, argumento lineal, Riccati con solución particular, Clairaut, PVI; los demás tipos no lineales, numéricos), lineales de coeficientes constantes (característico exacto en ℚ/ℚ(√d)/ℂ, coeficientes indeterminados con resonancia, variación de parámetros; factores irreducibles de grado 3 y 4 exactos por Cardano/forma trigonométrica y Ferrari, también bicuadradas, con nombres r1, α1, β1 y su definición; solo grado ≥ 5 queda numérico con sello «solo numérico», por Abel-Ruffini), PVI por Laplace con tramos, escalones y deltas (comprobación exacta por tramos y salto de las deltas), Laplace directa/inversa con región de convergencia, sistemas x′ = Ax + f con e^{At} y plano de fases, oscilador (Q, regímenes, resonancia, ancho de banda), respuesta impulsional, convolución, Volterra e integro-diferenciales, Picard, Wronskiano, reducción de orden, Euler-Cauchy, series de Fourier (n simbólico, Parseval, evaluación) y transformada (frecuencia ordinaria), transformada z, inversa y ecuaciones en diferencias, contorno 1D (también paramétrico), Poisson por tramos con contraste por diferencias finitas y calor 1D (Dirichlet, Neumann, mixta; contorno dependiente de t y flujos no nulos por referencia + Duhamel, con modos resonantes aparte y coeficientes simplificados); transformada z con polos cuadráticos repetidos; **2026-10-07:** puntos críticos de f = φ(w) (curvas de nivel exactas, familias periódicas como sen(x²+y²) completas por paridad de k, extremos aislados exactos); calculadoras `edo`, `laplace`, `fourier`, `transformada_z`, `contorno` | XL |
| **ML-9** Probabilidad y estadística | Bloque 6 completo con gráficas y simulación sembrada; **v2:** BER con `Q`, ALOHA, Rayleigh y Rice, ARQ (D12) **Implementado (2026-10-07):** los 15 tipos de §15.1 y las 13 calculadoras del bloque G (§8.2): Bayes con árbol, combinatoria contrastada por enumeración, inclusión-exclusión con regiones de Venn; 16 leyes con F, cuantil y momentos (exactos con parámetros racionales: binomial, geométrica, Pascal, hipergeométrica, uniforme, beta entera en ℚ; Poisson, exponencial, Erlang, Weibull y Rayleigh con `exp` exacta) y tablas normal, t, χ² y F calculadas con su redondeo; densidades por tramos con constante, momentos, F, Chebyshov, transformaciones por ramas monótonas, máximo, mínimo y convolución exactos; tablas conjuntas, vectores gaussianos y estimación lineal óptima en ℚ; aproximación normal al lado del exacto; descriptiva, intervalos (t/z justificada, cobertura simulada), contrastes, regresión y estimadores; procesos de Poisson, paseo ±1 y procesos con variables (R(τ) exacta y estacionariedad); BER, ALOHA, Rayleigh/Rice y ARQ; calculadoras `probabilidad`, `variable_aleatoria`, `vector_aleatorio`, `aproximacion_normal`, `estadistica`, `intervalo_confianza`, `contraste`, `regresion`, `estimador`, `proceso`, `tabla_estadistica`, `comunicaciones`, `montecarlo` | L |
| **ML-10** Ejercicios y maestría | Banco por tema, generador, enlace con el corrector y la maestría. **Implementado (2026-10-07):** plantilla única (§7) con enunciado, datos, tipo de entrega, pistas graduadas, respaldo E/G y solución paso a paso; **corrector por equivalencia** (formas normales exactas de `verify`, nunca texto: `2x+2x` = `4x`, `1/2` = `0,5`, y si solo hay coincidencia numérica el sello baja a `solo_numerico`); respuestas **no únicas corregidas por propiedad** (`Aᵀ·A = I`); **generador sembrado** por tema y dificultad cuya solución la pide el motor, se autocomprueba y **reintenta si el ejercicio sale degenerado**; 7 temas y 5 cálculos de `ejercicio` | L |
| **ML-11** Pulido | Accesibilidad, rendimiento, documentación de usuario, certificación. **Implementado (2026-10-09):** `pulido.py` con las cuatro comprobaciones **ejecutables** — `audita_accesibilidad` (§6: descripción textual obligatoria, serie con nombre, `len(xs) = len(ys)`, y el modelo de gráficas **no tiene campo de color**), `describe` (el resultado entero como texto: valor, pasos, sello, hipótesis, convenciones y gráfica), `mide` (tiempo real contra un techo declarado, más **determinismo**: la misma entrada da el mismo resultado) y `audita`/`certifica` (recorre **las 80 operaciones registradas** y comprueba los criterios de §8.4 uno a uno); operación `pulido` con 5 cálculos; gate en `docs/gates/GATE-MATH-LAB-CERTIFICATION.md` | M |
| **ML-12** Cimientos ampliados (v2) | **Racionales multivariable** (dependencia crítica); **cuerpo como parámetro** del motor lineal y aritmética entera con trazas; distribuciones con área; **contrato con otros laboratorios** y plug-ins de verificación (§5.9); **convenciones declaradas** (§5.11); análisis dimensional; verificador de gradientes; simulador sembrado de eventos; árboles y grafos | L |
| **ML-13** Cálculo vectorial ampliado (v2, **E**) | Operadores ∇ en cilíndricas y esféricas, laplaciano y Poisson, cambio de componentes entre bases; los 6 tipos de `V` dado y flujo por cubo; **cinemática intrínseca de curvas (D12)** **Implementado (2026-10-06):** ∇, ∇·, ∇× y ∇² con factores de escala en cartesianas, cilíndricas y esféricas (segundo camino en cartesianas por diferencias de orden 4), controles ∇·(∇×F) = 0 y ∇×∇V = 0, Poisson ρ = −ε₀∇²V, cambio de componentes con RᵀR = I y módulo invariante, V dado ⇒ E, ρ y carga en una caja por ∭ρ y ∯E·dS, cinemática intrínseca (T, N, κ, a_t, a_n, radio); calculadora `operadores` | S-M |
| **ML-14** Señales y sistemas deterministas (v2, **E**) | Bloque 15: biblioteca de señales, convolución por tramos y digital, periódicas por señal base, energía y correlación, DTFT, DFT, z con eco e inverso. **Implementado (2026-10-07):** pulsos Π/Λ/exp con integral, energía y TF cerradas (E = A²T, 2A²T/3, A²T/2) y aviso de solape; eje afín con E/|a| comprobada; convolución por rupturas = sumas de extremos con ∫y = ∫x·∫h (lineal a trozos exacta en constantes; cola exponencial por cuadratura con sello numérico), deltas que desplazan y escalan, ventana móvil; digital exacta en ℚ (L1+L2−1, tres tramos, Σy y DFT con N suficiente) y régimen geométrico; periódicas c_k = (1/T0)·X_b(k/T0) con nulos por paridad, periodo por mcm y Parseval; energía/potencia (A²/2, E_x(1+a²) del eco), correlación con r(0) = E y |r| ≤ r(0), densidad S = |X|² y retardo por el pico; DTFT (P_L con máximo L y ceros en k/L, |H|² del de primer orden, fase del retardo; Parseval y hermiticidad), DFT (X[0], hermítica, Parseval, circular = lineal con N ≥ L1+L2−1, retardo como fase) y eco (ceros en |z| = |a|^{1/L}, |H(F)|², inverso causal con b = −a y cascada que devuelve la entrada); calculadora `senales` | L |
| **ML-15** Fasores y polarización (v2, **E**) | Bloque 17: fasores, onda plana, medios con pérdidas (exacto frente a aproximado), Jones con SVD; **Fresnel, Brewster, evanescente y multicapa (D12)**. **Implementado (2026-10-07):** suma de fasores con rectangular exacto si la fase es múltiplo de π/2, problema inverso por sistema 2×2 en (P, Q) con verificación por muestreo, x(t) idéntica con las dos convenciones; onda plana (k, λ, v, η, H por k̂×E, ⟨S⟩ por |E|²/2η y por ½Re(E×H*) y por promedio temporal, sensor con aviso de desplazamiento); medios con ñ en rama Re ≥ 0, α/β por γ y por k₀·ñ, aproximación elegida por σ/ωε con error relativo y espesor para X dB; polarización por SVD 2×2 con AR por tanχ, ψ por tan2ψ, mano por giro muestreado y Stokes; Jones (retardadores unitarios, Malus, cascada, diseño λ/4+λ/2 en malla determinista, PLF); Fresnel con R+T=1, r_p(θ_B)=0 e incidencia normal exacta; multicapa con det=1 por capa y antirreflejante λ/4 con R≈0; calculadora `polarizacion` | M-L |
| **ML-16** Campos y ondas (v2, **E**) | Bloque 18: carga total, Gauss por regiones, conductores y tierra, Maxwell por sustitución, ecuación de onda y trazas; **Coulomb, Biot-Savart, Ampère, condensadores, inducción y Poynting (D12, E)**; antenas y enlace (D12, G, al final de la fase); depende de ML-13 y ML-8. **Implementado (2026-10-07):** carga de arco/cilindro/esfera/placa con cuadratura y homogeneidad en `a`; Gauss esférico con empalme V(∞)=0 y energía por ½ΣQV y (ε₀/2)∫E², ρ=a·rⁿ con ∇·E comprobado, cilindro con referencia en r₀ (aviso V(∞)=0) y plano; concéntricos con inducidas exactas y tierra que drena (V=0); V dado por ML-13 con Gauss por dos lados; Maxwell plana (c por dos cocientes), guía TE con Helmholtz fasorial y potencia, completar By con ∇·B=0; perfiles gauss/sech² por sustitución con retardos y energía; anillo/disco/espira/hilo con límites puntual/plano/dipolo, polígono con N→∞ a la espira; condensadores con energía doble y serie; Faraday con Lenz, Poynting con balance exacto; Friis lineal/dB, G/T y array (N=1 reproduce); calculadora `campos` | L |
| **ML-17** Discreta, modular, códigos e información (v2, E débil y **G**) | Bloques 8 a 11: lógica, inducción, recurrencias, complejidad; ℤₙ y GF(p) con el cifrado clásico (**E** 3/7 de APR), códigos lineales, CRC, Shamir, RSA y DH; entropía y Huffman; **tiempo real y privacidad (D12, G, al final)**. Dentro de la fase, el cifrado clásico (**E**) y ℤₙ van primero. GF(2ᵐ) al final, prioridad media. **Implementado (2026-10-07):** tablas de verdad/equivalencias hasta 4 vars (si no, leyes), conjuntos por enumeración, binomio con filas 2ⁿ, recurrencias por característica con iteración, maestro casos 1/2/3, ruina con p=1/2 exacta, sumatorios cerrados, mochila PD = fuerza bruta, voraz frente a PD, tiempo real (U, Liu-Layland, RTA, hiperperiodo, cronograma); César/afín/Vigenère/Hill con ida y vuelta, tablas ℤₙ, hash con Monte Carlo, GF(2ᵐ) con Rabin y tabla log/antilog, polinomios sobre GF(p), [n,k,d] con G·Hᵀ=0, síndrome, Hamming(7,4), CRC con resto 0, paridad, checksum, Shamir con dos subconjuntos, RSA/DH con aviso pedagógico, k-anonimato, Laplace con b=Δf/ε; entropía/mutua/KL/cruzada con cadena, Kraft, BSC/BEC/Hartley, Huffman con H≤L̄<H+1, claves 2ᵏ; operaciones `discreta`, `codigos`, `informacion` | L |
| **ML-18** Detección y estimación (v2, **G**) | Bloque 16: MAP, Neyman-Pearson y ROC, Cramér-Rao, Wiener, gradiente, LMS y NLMS; **PSD teórica de procesos discretos (D12)**. **Implementado (2026-10-07):** Toeplitz hermitiana con s.d.p., AR(1), PSD con r[0] = ∫S, S_y = S_x|H|²; señal conocida con d², umbral NP, P_D y ROC con Monte Carlo; MAP/Bayes por γ; Fisher cerrada con CRB; gaussiano con ML = MAP = MMSE y ECM; Wiener con R·w = p y J_min; Yule-Walker; gradiente por modos con cota; LMS con curva sembrada (divergencia visible) y NLMS; operación `deteccion` | M |
| **ML-19** Optimización y aprendizaje automático (v2, **G**) | Bloque 13: GD, regresión, logística, métricas, k-medias, EM, árboles, PCA y SVD, redes a mano. **Implementado (2026-10-07):** GD/momento/Adam en cuadráticas con η < 2/L y óptimo por normales; regresión exacta en ℚ con Xᵀe = λw, ridge, lasso 1D y R²; logística con pérdida que baja; métricas, ROC/AUC por trapecios = Mann-Whitney; Lloyd con SSE y silueta, EM 1D con log L y BIC, árboles por ganancia; PCA con Σλ = traza y VᵀV = I, SVD 2×2; MLP con retropropagación verificada por diferencias, atención con filas 1, RNN/LSTM, SVM con KKT; operación `aprende` | M |
| **ML-20** Markov, MDP y refuerzo (v2, **G**) | Bloque 12 con el simulador de eventos. **Implementado (2026-10-07):** absorción N = (I−Q)⁻¹ exacta con N·(I−Q) = I, clasificación con periodos por mcd, MDP con v = (I−γP)⁻¹R y residuo 0, iteración de valor = solución directa, episodio a mano (MC = media muestral, TD/SARSA/Q), bandidos con Qₙ exacta, REINFORCE con gradiente numérico; operación `refuerzo` (lo de ML-12 no se duplica) | M |
| **ML-21** Matemáticas financieras (v2, **G**) | Bloque 14. **Implementado (2026-10-07):** interés simple/compuesto m/continuo con TAE y regla del 72, despeje con ln, VAN, TIR por bisección, anualidad de amortización, bono (Macaulay, modificada y convexidad), futuro, payoff, árbol CRR con q, Black-Scholes con griegas, σ implícita por Newton sobre la vega, Monte Carlo sembrado con error 1/√N, Markowitz por KKT lineal, **frontera eficiente** y Sharpe/VaR; operación `finanzas` (15 cálculos) | M-L |
| **ML-22** Física auxiliar (v2, **E** para `U(x)`; parte térmica **opcional**; órbitas **G**) | Bloque 19: `U(x)` siempre; termodinámica del gas ideal y Maxwell-Boltzmann, Planck y Stefan solo si se activan (D10, D12); **órbitas y visibilidad (D12, G)**. **Implementado (2026-10-07):** equilibrios por barrido+bisección con U″, ω exacta en cuadráticas, v_max, periodo por cuadratura sen² = RK4, retrato de fases; gas lineal/parabólico/isotermo con T_max, ΔS doble y ciclo con Clausius; Kepler por bisección+Newton (e=0 círculo), órbita circular, visibilidad; MB con norma y ⟨v²⟩, Planck π⁴/15 con σ; calculadora `fisica` | S |

**Cada fase incluye las calculadoras de su bloque (§8), con pasos y verificación completos.** S ≈ días, M ≈ 1–2 semanas, L ≈ 3–5, XL > 5. **Orden recomendado (v1):** ML-0 → ML-1 → ML-2 → ML-3 → ML-5 → ML-6 → ML-7 → ML-4 → ML-8 → ML-9 → ML-10 → ML-11.

**Orden recomendado (v2), con los bloques respaldados por exámenes (E) antes que los de solo guía (G):** ML-0 → **ML-12** → ML-1 → ML-2 → ML-3 → ML-5 → ML-6 → ML-7 → **ML-13** → ML-4 → ML-8 → ML-9 → **ML-14 → ML-15 → ML-16 → ML-22** (`U(x)`, **E**; el gas ideal es opcional) → **ML-17** → **ML-18 → ML-19 → ML-20 → ML-21** → ML-10 → ML-11. ML-10 (ejercicios y maestría) y ML-11 (pulido) se **repiten como cierre incremental** de cada tanda, no solo al final. ML-12 no se retrasa: sin racionales multivariable y sin el contrato no pueden empezar los otros laboratorios (§16).

---

## 11. Pruebas y criterios de aceptación

### 11.1 Estrategia

Pruebas de dominio **sin Qt**, por fase. Además de ejemplos dorados, **propiedades con semilla**: para expresiones aleatorias, `derivada(primitiva(f)) ≡ f`; `integral por un orden = integral por el otro`; `Green = integral de línea`; `A·A⁻¹ = I`; `parse(text(e)) = e`.

### 11.2 Criterios globales

1. Cualquier ejercicio del catálogo muestra **pasos, gráfica y sello de verificación**.
2. Ningún resultado se da por correcto **sin comprobación independiente**.
3. Las integrales dobles y triples se calculan **por dos órdenes o dos sistemas de coordenadas** y coinciden.
4. Green, Stokes y Gauss se comprueban **calculando ambos lados**.
5. Lo que no se sabe resolver exacto se dice, y se da el valor numérico con error.
6. La corrección acepta respuestas **equivalentes** en distinta forma.
7. Todo resultado es **determinista** y reproducible.
8. Toda la interfaz en **castellano** y operable con teclado.
9. Las pruebas existentes del proyecto **no cambian de resultado**.
10. **Toda elección de método** lleva su «Por qué este método» (§5.5b), y **todo cambio de variable** muestra el porqué, el cambio, el diferencial o jacobiano, los límites o región nuevos y la comprobación de validez (§5.6).
11. **Todo teorema** aplicado lista y comprueba sus hipótesis (§5.7).
12. Los **15 tipos prioritarios de cada asignatura** (§15.1) se resuelven con pasos, por qué, hipótesis, gráfica y verificación independiente; cada fase se cierra con sus tipos.
13. **(v2)** Los **tipos prioritarios de los bloques 8 a 19** (§15.6) se resuelven con pasos, por qué, hipótesis, gráfica y verificación independiente; los de respaldo **E** cierran antes que los **G**.
14. **(v2)** Todo ejercicio sensible a una **convención** (§5.11) la declara, la imprime y pasa la verificación con la contraria.
15. **(v2)** El motor cumple el **contrato de §5.9**: cada laboratorio consumidor pasa su prueba de contrato (forma de la traza y del sello) y puede registrar su plug-in de verificación.
16. **(v2)** **Ninguna solución oficial se da por buena por coincidir con ella:** las erratas de §11.4 se detectan por verificación cruzada y se señalan.
17. **(v2)** Las pruebas existentes del proyecto y las del laboratorio digital **no cambian de resultado** al introducir el cuerpo como parámetro y los racionales multivariable.

### 11.3 Pruebas de los bloques 8 a 19 (v2)

Pruebas de dominio **sin Qt**, con **propiedades sembradas** además de ejemplos dorados (en la misma línea de §11.1):

| Bloque | Propiedades y casos |
|---|---|
| 8 | RTA converge o supera `D`, `U` bajo la cota de Liu-Layland ⇒ planificable; `T(n)` iterada = fórmula cerrada; contador instrumentado: `T(n)/g(n)` tiende a una constante; tabla de verdad = derivación por leyes; inclusión-exclusión = enumeración |
| 9 | `descifrar(cifrar(x)) = x` y `k ≡ k+26`; `a·a⁻¹ ≡ 1`; para `n` pequeño, la tabla completa de productos coincide con Euclides; `α^(2ᵐ−1) = 1`; Gauss sobre GF(2): `A·x = 0` en todo el núcleo y `2ᵏ` elementos |
| 10 | `G·Hᵀ = 0`; `d_min` por pares = peso mínimo; el síndrome corrige un error y **avisa** con dos; CRC: la trama completa da resto 0; Shamir: **dos subconjuntos** de `t` partes dan el secreto y `t−1` no lo determinan; `m^(e·d) ≡ m (mod n)` frente a `pow`; k-anonimato: toda clase `≥ k`; DP: razón de densidades `≤ e^ε` |
| 11 | `H = log₂ N` en el uniforme; `I ≥ 0`; Kraft con igualdad en Huffman; `H ≤ L̄ < H+1`; `C_BSC(0,5) = 0` |
| 12 | `Pⁿ` converge a `π` con `π·P = π`; residuo de Bellman 0; iteración de valor = `(I−γP)⁻¹R`; Q-learning con visitas suficientes converge a la solución de Bellman; `Qₙ` = media muestral |
| 13 | Gradiente analítico = diferencias centrales en GD, logística, retropropagación y Markowitz; la pérdida baja tras un paso con `η` pequeño; `Xᵀe = 0`; PCA = SVD salvo signo; `Σλ` = traza |
| 14 | Paridad put-call; `VAN(TIR) = 0`; CRR con `n` grande tiende a Black-Scholes; `wᵀ1 = 1` y `∇L = 0`; el Monte Carlo cae en el intervalo exacto |
| 15 | `∫y = ∫x·∫h`; `Σy = Σx·Σh`; Parseval en tiempo y frecuencia; Wiener-Khinchin; circular = lineal con `N ≥ L₁+L₂−1`; la cascada eco + inverso devuelve la entrada; **tres señales base distintas** dan los mismos `c_k` |
| 16 | `P_FA` y `P_D` empíricas sobre la ROC; varianza empírica `≥` CRB; `E[e·x*] = 0`; modos de LMS frente a la fórmula; `μ` sobre la cota diverge; PSD teórica = TF de `r` y `r[0] = ∫S dF` |
| 17 | Fasor frente a tiempo con **las dos convenciones**; `abs(E)²` conservado por Jones (unitaria); AR por dos fórmulas; exacto frente a aproximado con su error relativo; Fresnel: `R + T = 1` y `r_p(θ_B) = 0`; multicapa: `det = 1` por capa |
| 18 | `∇·E = ρ/ε₀` por regiones; flujo por 6 caras = Gauss; Maxwell por sustitución; `∇·(∇×F) = 0`; energía por dos fórmulas; **análisis dimensional** de cada constante; Biot-Savart frente a Ampère y límite `z ≫ R`; Friis en lineal frente a dB |
| 19 | Periodo por RK4 = cuadratura de `U(x)`; Kepler: sustitución en `M = E − e·senE` y `e = 0` da el círculo; `ΔS` por dos caminos reversibles (opcional) |

Los **casos privados** (enunciados reales de los exámenes) siguen la regla de §14.1: no se copian al repositorio; las pruebas del proyecto usan problemas propios de la misma forma y una prueba opcional apunta a la carpeta local.

### 11.4 Erratas halladas, como casos de prueba de verificación cruzada (v2)

Los cuatro informes encuentran **errores o ambigüedades en soluciones oficiales y enunciados**. Cada uno se convierte en un caso de prueba: el sistema, verificando por un segundo camino, **debe señalar la discrepancia** en lugar de aceptar la solución publicada (§15.2, punto 1).

| Fuente | Qué se halló | Caso de prueba | Dueño |
|---|---|---|---|
| Señales y Sistemas, final 10-1-2020, ej. 2.2 | `R_p1p2 = Λ(t−2) + Λ(t+2)` en una opción y `−Λ(t−2) + Λ(t+2)` en otras dos: una de las tres tiene el signo mal; el valor en `t = 0` (que es 0) **no lo detecta** | Correlación de dos pulsos desplazados: evaluar en `t = ±2`, no solo en 0; el sistema debe señalar cuál signo es correcto | MATH_LAB (bloque 15) |
| Señales y Sistemas, 2.º parcial 23-5-2023, ej. 2.6a | El enunciado dice `N = 1000` y la figura es de `N = 1500` | Ejercicio con **dato de texto distinto del dato de la figura**: el sistema avisa de la inconsistencia (§7, figuras como datos) | MATH_LAB (bloque 15) |
| Señales y Sistemas, finales jun-2021 y 2022 | «100 veces inferior» se toma como −60 dB sobre `abs(H)²` en uno y como amplitud en otro, con `h(t) = e^{−t/10}·u(t)` | Mismo enunciado con las dos convenciones de dB: las frecuencias de −60 dB difieren; el ejercicio **exige declarar** la convención (§5.11) | MATH_LAB (convención) |
| Final 13-1-2020, ej. 3 | El código MATLAB usa `f(i)` donde la variable es `fi(i)` y reutiliza `f` | **No es caso matemático** (MATLAB está fuera de alcance, §17); solo se anota | — |
| Probabilidad (catálogo existente) | Tablas de la normal permutadas, signos, constantes, fechas | Ya recogido en §15.2 punto 1: tablas calculadas, no impresas | MATH_LAB |
| Dispositivos Electrónicos, Ejercicio 3 (unión PN) | La solución etiqueta «eV» una barrera que es `½·w·E_max` en voltios (unidades inconsistentes) | **Análisis dimensional** obligatorio: el sistema detecta la unidad errónea | CIRCUITS_LAB (usa el comprobador de MATH_LAB) |
| Sistemas de Medida 2020-21, P3 c | Cita `15,152 kHz` para `x = 0` mientras b) y el resto usan `13,793 kHz` | Verificación cruzada del valor frente al cálculo directo | CIRCUITS_LAB |
| Sistemas de Medida, actividad 1DE | `t95 = 4,8 s`, pero con retardo 1,21 s y 1,35 s el valor sería ≈ 6,2 a 6,3 s y el veredicto «cumple < 6 s» cambiaría. **No confirmado** (el texto extraído mezcla columnas) | Caso de **ajuste con retardo**: `t95 = retardo + τ·ln 20`; se marca «por confirmar» | CIRCUITS_LAB |
| PPE, Parcial Oct-2025, P1c | `P(N > 123) = 0,036` con `N ∼ Geom(0,0081)`: el valor correcto es `(1−p)^123 ≈ 0,368` (un cero de más) | Cola geométrica exacta frente a simulación; el motor da 0,3677 verificado | MATH_LAB (bloque 6) |
| PPE, Parcial Oct-2025, P1d | Escribe `P(Y ≥ 2)` pero resta `P(Y=0)+P(Y=1)+P(Y=2)`, i.e. calcula `P(Y > 2) ≈ 0,048` | Sucesos `≥` frente a `>` en Poisson: el motor los distingue | MATH_LAB (bloque 6) |
| PPE, Parcial Oct-2025, P2d | Pide error `< 0,1` pero calcula con `0,2` (`0,2·√n/3 = 1,96` → n ≥ 864,5; con 0,1 sería n ≥ 3459) | Tamaño de muestra con el error del enunciado, no con el del cálculo | MATH_LAB (bloque 6) |
| PPE, Parcial Oct-2025, P1a | Escribe `P(Bin(5;0,1) ≥ 3) = 0,0081` (solo el término k = 3); el total es 0,00856 | Suma de los tres términos k = 3, 4, 5 | MATH_LAB (bloque 6) |
| Física, Final 2025, P3 | Vuelta isoterma con `ΔS_e = −9,0 J/K`: el área exacta es `nRT·ln(1/2) ≈ −8,3 kJ` (los −9,0 salen del trapecio en la isoterma) | Isoterma exacta frente a trapecio; `ΔS_U = +1,4 J/K` se mantiene | MATH_LAB (bloque 19) |
| Electromagnetismo, Final 23-24, C5 | Escribe `c = 3,33×10⁻⁹` (eso es `1/c` en SI; `c = 1/√(μ₀ε₀) ≈ 3×10⁸ m/s`) | `ω/k = E₀/B₀ = c` por sustitución, con tolerancia de examen (1e−3) | MATH_LAB (bloque 18) |
| Álgebra, 2.º Parcial 2022 (ms.) | P2b: arrastre de signo en Gram-Schmidt; P3a: el resumen dice `β = 2` y el cálculo previo da `β = −2`; P3c: dice `α+β = 3` y es `α+β = −3`. Detectadas en lectura (el propio desarrollo las corrige) | Discusión por casos con parámetros y Gram-Schmidt con `G` no estándar | MATH_LAB (bloque 3, pendientes de fijar como test) |

Las de dueño CIRCUITS_LAB están además en su Anexo E (erratas conocidas como casos de prueba). Sumadas a las de §15.2, **ninguna solución oficial es oráculo**.

---

## 12. Riesgos y límites

| Riesgo | Mitigación |
|---|---|
| **Alcance enorme**: es un sistema de álgebra computacional | Fases entregables; orden por valor; límites honestos declarados |
| **Integración simbólica incompleta** | Conjunto amplio de técnicas, caída a numérico con error, verificación siempre |
| **Sin NumPy, lo numérico pesado es lento** | Hilo aparte, topes, dependencia opcional (D1) |
| **Visor 3D de calidad** | Prototipo propio con Qt medido; si no alcanza, Qt Quick 3D (D2, decidido); empezar por lo simple (malla y rotación) |
| **Entrada de fórmulas** difícil para el usuario | Vista previa, errores claros, atajos y plantillas |
| **Duplicar** lo que ya hay en `symbolic/`, `math/`, `dsp/` | Se amplía lo existente, no se reescribe |
| **(v2) Racionales multivariable**: sin ellos no hay `H(s)` con `R`, `C`, `K` simbólicos y los demás laboratorios no arrancan | Fase ML-12 antes que cualquier bloque nuevo; es la dependencia crítica del reparto (§5.1) |
| **(v2) Cuerpo como parámetro** puede romper álgebra lineal existente | Pruebas de regresión de ML-3 sin cambios; ℚ y ℝ como cuerpos por defecto; criterio 17 de §11.2 |
| **(v2) Frontera difusa entre laboratorios**: la misma fórmula (Bode, dB, Smith) aparece en tres specs | Tabla «qué va dónde» (§16); el contrato (§5.9) solo ofrece la capa genérica; D12 resuelta (§16.3) |
| **(v2) Evidencia desigual**: solo APR, PPE, SST, EAFO, Electromagnetismo, Física y AC/SM tienen exámenes; el resto solo guía | Insignia **E**/**G** (§3), los **G** son de prioridad menor y se reordenan cuando haya exámenes (§15.8) |
| **(v2) Figuras en los enunciados** (espectros, periódicas, curvas) que la app no puede leer | Figuras como datos (§7) con gráfica generada y aviso de inconsistencia |
| **(v2) Convenciones mezcladas** (eficaz/pico, `e^{±jωt}`, dB, `n`/`n−1`, Chauvenet) producen errores silenciosos | Campo `convenciones` obligatorio y verificación con la contraria (§5.11) |
| **(v2) Distribuciones** (áreas de delta en la TF de periódicas) no caben en un motor de funciones ordinarias | Distribuciones de primera clase con área (§5.1) |
| **(v2) Cripto y seguridad**: se podría confundir material pedagógico con real | Aviso fijo «solo pedagógico, nunca seguridad real» en RSA, Diffie-Hellman y Shamir |
| **(v2) Aprendizaje automático y finanzas con resultados no deterministas** | Semilla explícita y verificación por gradiente numérico, paridad put-call y simulación sembrada |

Límites declarados al usuario: no hay demostraciones formales generales (la inducción es una plantilla que verifica el cálculo, no el razonamiento); la integración y los límites simbólicos no son completos; las gráficas 3D son de aproximación; Markowitz sin cortos (programación cuadrática) no se resuelve; los **cripto** son pedagógicos.

---

## 13. Decisiones (todas resueltas)

| # | Decisión | Resolución |
|---|---|---|
| D1 | ¿Dependencias opcionales? | ✅ **DECIDIDO:** vale toda librería que ayude a que el resultado sea correcto (SymPy, NumPy, SciPy, mpmath…), como **comprobadora independiente**; los pasos los da siempre el motor propio (§5.8). |
| D2 | Visor 3D | ✅ **DECIDIDO (el usuario pidió «perfecto»):** se construye un prototipo del visor propio con Qt (malla, sombreado, ordenación en profundidad, rotación, regiones y normales) y se **mide**; si no alcanza calidad y fluidez suficientes, se pasa a Qt Quick 3D. La decisión final la toma la medición, no la preferencia. |
| D3 | Prioridad de fases | ✅ **DECIDIDO:** el orden de §10 (lo de más uso primero), con los bloques E antes que los G. |
| D4 | Alcance del nivel 0 | ✅ **DECIDIDO: completo** (aritmética, divisibilidad, combinatoria). |
| D5 | Materiales reales | ✅ **Aportados** (carpeta del usuario, §14). Pasada sistemática hecha (§15). Regla: **no se borra ni modifica nada** de esa carpeta. |
| D6 | **Reparto de los cuatro informes extra** | ✅ **DECIDIDO por el usuario (aplicado estrictamente):** **entran** en MATH_LAB como bloques nuevos 8 a 19 (aritmética modular y cuerpos finitos, códigos, CRC, Shamir, RSA, Diffie-Hellman, Markov y MDP, información, optimización y aprendizaje automático, finanzas, lógica y recurrencias, señales deterministas, detección y estimación, fasores y Jones, electrostática por regiones y Maxwell, operadores ∇, ecuación de onda por sustitución, `U(x)`, termodinámica opcional). **No entran**: lo de espectros, ventanas, muestreo, modulación, FIR, IIR y filtro adaptado va a `SIGNALS_LAB.md`; **todo lo circuital** (Bode, síntesis de `H(s)`, transitorios, GUM, circuitos a trozos, calibración de sensores, estabilidad, estado de circuitos, dB, líneas, Smith, adaptación, guías, conversión de potencia) va a `CIRCUITS_LAB.md`. Aquí solo la capa matemática genérica y el contrato (§5.9, §16). |
| D7 | Orden de construcción por evidencia | ✅ **DECIDIDO:** primero los bloques con respaldo **E** (15, 17, 18, César del 9, `U(x)`), después los **G**; **ninguna calculadora se recorta** (§8). Se reordena si llegan exámenes de las asignaturas con solo guía. |
| D8 | Cuerpo como parámetro del motor de Gauss | ✅ **DECIDIDO por el usuario:** el motor acepta el cuerpo (ℚ, ℝ, ℂ, GF(p), GF(2)); GF(2ᵐ) después (prioridad media). |
| D9 | Convenciones declaradas por ejercicio | ✅ **DECIDIDO por el usuario:** valor eficaz o pico, signo `e^{±jωt}`, dB de amplitud o potencia, `s` con `n` o `n−1`, y **Chauvenet del curso con `D_max` fijo** (§5.11). |
| D10 | Termodinámica del gas ideal | ✅ **DECIDIDO: opcional** (se activa a petición; el resto de la física auxiliar, `U(x)`, no es opcional). |
| D11 | Variable compleja general, Legendre, Laplace 2D/3D, CPM/PERT, GCN, GAN/VAE, IEEE 754 profundo, juegos de tablero, MATLAB | ✅ **DECIDIDO: fuera de alcance** (§17). |
| D12 | **Temas sin asignar por el usuario** (§16.3) | ✅ **DECIDIDO (aprobada la propuesta de cada informe):** entran en MATH_LAB Coulomb, Biot-Savart, Ampère, condensadores, inducción y Poynting (bloque 18), Fresnel y multicapa (17), antenas y enlace (18), órbitas (19), BER, ALOHA, Rayleigh y Rice (§4.6), privacidad (10), tiempo real (8), PSD teórica (16), cinemática intrínseca, oscilador con Q y calor (§4.4, §4.5), Maxwell-Boltzmann, Planck y Stefan (19, opcional). **Fuera:** propiedades de sistemas y cuantización (SIGNALS_LAB), robot, PID, Kalman, cristalografía y fiabilidad (§17). |

## 14. Lo que muestran los materiales reales

Fuente: carpeta de estudio del usuario (`Ingenieria Electronica de Telecomunicaciones/`), leída **solo para consulta; no se ha modificado, movido ni borrado nada** (regla fijada por el usuario: prohibido borrar). Contiene apuntes, colecciones de problemas y **exámenes finales y parciales resueltos** de Cálculo, Álgebra Lineal, Cálculo Vectorial, Ecuaciones Diferenciales y Transformadas y Probabilidad y Procesos Estocásticos, y prácticas de Señales y Sistemas (MATLAB). Están en **catalán** en su mayoría.

### 14.1 Cómo se usan

- Como **fuente de tipos de ejercicio** y como **casos de prueba privados** del laboratorio: el sistema debe ser capaz de resolver, con pasos y verificación, los problemas de esos exámenes.
- **No se copian al repositorio.** Los enunciados son material de la universidad; las pruebas del proyecto usan problemas propios de la misma forma, y una prueba opcional apunta a la carpeta local del usuario (ruta configurable) y se omite si no existe.
- Hay que **leer la solución oficial** de cada uno como referencia, pero la corrección no depende de comparar texto.

### 14.2 Temas que faltaban en el catálogo y que aparecen en los exámenes

| Asignatura | Tema añadido |
|---|---|
| Cálculo Vectorial | **Cónicas y cuádricas** (apuntes «Conics Quadrics»): clasificación y dibujo; **curva regular por el rango del jacobiano**, recta tangente, parametrización; curva como intersección de superficies; extremos absolutos en un recinto con frontera; flujo por Gauss sobre una región limitada por un cono; circulación por Stokes |
| Cálculo | Integrales impropias **con parámetro** («¿para qué valores de α converge?»); límites con parámetros; probar **existencia y unicidad de raíces** y acotarlas; Taylor de una función con término general; continuidad con parámetros |
| Álgebra Lineal | Subespacios **sobre C**, suma e intersección; endomorfismos nilpotentes y matriz en una base dada; **producto escalar con una matriz de Gram** cualquiera; diagonalización con parámetros; **diagonalización ortogonal**, **teorema espectral**, **descomposición en valores singulares (SVD)** |
| Ecuaciones Diferenciales y Transformadas | **Laplace con fracciones simples y raíces múltiples**; EDO lineales con coeficientes variables; **sistemas de EDO**; **espacios de Hilbert** y series de Fourier |
| Probabilidad y Procesos Estocásticos | **Proceso de Poisson**, estimación por momentos e **intervalos de confianza** con t de Student y otras distribuciones tabuladas; autocorrelación de un proceso; probabilidad condicionada de un proceso |
| Señales y Sistemas (prácticas en MATLAB) | Convolución, DFT y señales digitales; quedan para un laboratorio de señales, enlazando con `dsp/` |

Para las **tablas estadísticas** (normal, t de Student, chi-cuadrado, F) que los exámenes traen impresas, el laboratorio las **calcula** con precisión y las muestra con la zona sombreada, en lugar de depender de una tabla.

### 14.3 Formato de respuesta de los exámenes

Los exámenes piden: **razonar cada paso**, **comprobar hipótesis**, **justificar gráficamente o por parametrización**, y dar **la orientación elegida** (Stokes, flujo). El laboratorio replica esa forma de respuesta completa como **solución modelo**, con apartados (a), (b), (c)… iguales que en el enunciado.

### 14.4 Estado de la lectura

La pasada sistemática por tema **ya está hecha** por asignatura (cinco informes en `Descargas/labs/math_catalog/`); su resumen y los 15 tipos prioritarios por asignatura están en §15. Quedan fuera las prácticas de MATLAB de Señales y Sistemas (laboratorio de señales) y lo listado en §15.5.

### 14.5 Segunda tanda de lectura (v2)

Cuatro informes adicionales, **de solo lectura** (no se modificó nada en OneDrive ni en `guias_upc`; no se tocó el repositorio), en `Descargas/labs/math_catalog/`. Los enunciados están parafraseados y no se copian al repositorio (regla D5).

| Informe | Asignaturas leídas | Evidencia | Límite principal |
|---|---|---|---|
| `extra_senales.md` | Señales y Sistemas (≈ 29 pruebas: 11 finales y 18 parciales, 2018-2025), Tratamiento de la Señal, MATLAB | SST con exámenes; TRS y MATLAB **solo guía** | La solución del ej. 1 y parte del 3 del final 2023 Q1 sale como ruido de OCR; `Primer Control.pdf` y `Segundo Control.pdf` son imagen sin texto; frecuencias ±2 |
| `extra_electromagnetismo.md` | Física, Electromagnetismo, EAFO, ICAF/CIAF, Telecomunicación espacial | Exámenes de Física (34), Electromagnetismo (9), EAFO (~17) y 5 controles de CIAF; ICAF solo por un zip de otra asignatura; **Telecomunicación espacial solo guía** | Los exámenes «Resuelto» de Electromagnetismo son imágenes sin texto; el tema 6 de EAFO no tiene material; las frecuencias de Telecomunicación espacial son horas de temario |
| `extra_circuitos_control.md` | CCE, Análisis de Circuitos, Dispositivos, Sistemas de Medida, Circuitos Analógicos, Control, Energía, Materiales, Tecnología Electrónica, PSPICE | AC (17 exámenes) y SM (3 finales) con datos; CCE un solo examen; el resto solo guía | Soluciones manuscritas; casi todo **va a CIRCUITS_LAB** (§16); aquí solo se retiene la capa genérica |
| `extra_algoritmia_ia_codigos.md` | IMATEC, Algoritmia y Programación, Estructuras de Datos, códigos y secreto, Seguridad, Aprendizaje Automático y Profundo, Refuerzo, Financiera, Tiempo Real, IoT, Robots, Integración, PPE | **Conteo real solo en APR (13 exámenes) y PPE (16)**; todo lo demás solo guía | Frecuencias inferidas del temario; fórmulas estándar (Liu-Layland, CRR, Shamir…) a verificar con el motor propio |

Lo que la lectura confirmó que **no existe** en los catálogos anteriores: fasores, cuerpos finitos, Markov, información, finanzas, operadores ∇ en curvilíneas, DTFT y DFT como tema, correlación determinista y densidad espectral, detección y estimación.

## 15. Catálogo priorizado con datos de los exámenes reales

Fuente: cinco informes de lectura completa de la carpeta de estudio del usuario, en `Descargas/labs/math_catalog/` (`calculo.md`, `calculo_vectorial.md`, `algebra_lineal.md`, `ecuaciones_diferenciales.md`, `probabilidad_estadistica.md`). Cada informe tiene, por tema, tipos de ejercicio con frecuencia, razonamiento de elección de método, hipótesis, gráficas, verificación cruzada, dificultades y 45–55 ejemplos parafraseados. **Este apartado resume lo que cambia en el plan**; el detalle vive en esos ficheros. Las frecuencias son recuentos manuales (±1).

### 15.1 Los 15 tipos prioritarios por asignatura

**Cálculo Vectorial** (13 exámenes; 9 finales)

| # | Tipo | Frecuencia |
|---|---|---|
| 1 | Extremos absolutos en recinto compacto (Weierstrass, interior, frontera por piezas o Lagrange) | 8/13 |
| 2 | Puntos críticos y clasificación (Hessiana, Sylvester, caso degenerado) | 10/13 |
| 3 | Función implícita (existencia, `Df`, segunda derivada, sistemas) | 10/13 |
| 4 | Flujo con Gauss y tapa | 7/9 finales |
| 5 | Integral triple y volumen, con elección de coordenadas y jacobiano | 8/9 finales |
| 6 | Diferenciabilidad por definición en el origen | 7/13 |
| 7 | Función inversa (local, `DF⁻¹`, por qué no hay inversa global) | 7/13 |
| 8 | Circulación con Stokes (superficie, orientación, comprobación directa) | 5/9 finales |
| 9 | Curva regular definida implícitamente o por intersección (tangente, plano normal) | 8/13 |
| 10 | Parametrización de curvas y superficies; cerrada y regular | transversal |
| 11 | Campos conservativos y potencial | 2/9 finales |
| 12 | Continuidad en el origen (acotación, polares, trayectorias) | 5/13 |
| 13 | Cambio de orden de integración y región iterada | varios |
| 14 | Green con curva no cerrada y campos con singularidad | 1/9 |
| 15 | Topología de conjuntos y dibujo de cuádricas | transversal |

**Cálculo** (11 exámenes)

| # | Tipo | Frecuencia |
|---|---|---|
| 1 | Convergencia de integrales impropias (con parámetro) | 11/11 |
| 2 | Series de potencias: radio, extremos, dominio | 11/11 |
| 3 | Suma de una serie por Taylor, geométrica o telescópica | 6/11 |
| 4 | Existencia y número de soluciones: Bolzano, monotonía, Rolle | 9/11 |
| 5 | Estudio completo de una función con gráfica | 8–10/11 |
| 6 | Extremos absolutos en un intervalo | 5–6/11 |
| 7 | Continuidad y derivabilidad con parámetros | 6/11 |
| 8 | Límites por Taylor con parámetros | 7/11 |
| 9 | Primitiva racional por fracciones simples | 6/11 |
| 10 | Primitiva por cambio de variable (justificado) | 5/11 |
| 11 | Polinomio de Taylor y resto de Lagrange con cota | 9/11 |
| 12 | Función definida por una integral (TFC, regla de la cadena) | 7/11 |
| 13 | «Enunciar y comprobar hipótesis» de Rolle, Bolzano, Weierstrass…, con contraejemplo | transversal |
| 14 | Criterios de convergencia de series numéricas | 3/11 |
| 15 | Función inversa y su derivada | 3/11 |

**Álgebra Lineal** (finales 2018–2024; cada final repite el mismo patrón)

| # | Tipo |
|---|---|
| 1 | Diagonalización de una 3×3 con parámetros, sobre R y sobre C |
| 2 | Descomposición en valores singulares (SVD), con «A = MᵀM» |
| 3 | Diagonalización ortogonal de una simétrica (teorema espectral) |
| 4 | Producto escalar definido por una base ortonormal: matriz de Gram |
| 5 | Producto escalar con parámetro: ¿cuándo es definido positivo? (Sylvester) |
| 6 | Base ortogonal de un subespacio por Gram-Schmidt con el producto dado |
| 7 | Proyección ortogonal y distancia mínima |
| 8 | Matriz de un proyector o simetría, y sus propiedades |
| 9 | Subespacios: dimensión y base de F, G, F+G, F∩G (con parámetros, sobre R y C) |
| 10 | Descomposiciones `w = v_F + v_G` y unicidad |
| 11 | Aplicación lineal dada en una base no canónica; núcleo, imagen, con parámetros |
| 12 | Composición de aplicaciones y antiimágenes |
| 13 | Cambio de base, coordenadas, independencia con parámetro |
| 14 | Subespacios invariantes y vectores propios ligados a proyecciones |
| 15 | Mínimos cuadrados y pseudoinversa |

**Ecuaciones Diferenciales y Transformadas** (17 exámenes)

| # | Tipo | Frecuencia |
|---|---|---|
| 1 | PVI lineal por Laplace con segundo miembro a trozos, escalón o delta | 17/17 tienen Laplace |
| 2 | EDO lineal de primer orden con PVI | 6+ |
| 3 | EDO exacta con factor integrante `μ(x)` o `μ(y)` | 8/17 |
| 4 | Lineal de orden n a coeficientes constantes (indeterminados, resonancia, PVI) | 12/17 |
| 5 | Serie de Fourier y sumas numéricas por evaluación y Parseval | 12/17 |
| 6 | Transformada de Fourier por definición; Parseval | 8/17 |
| 7 | Transformada z: ecuación en diferencias, `H(z)`, `h[n]`, región de convergencia | 8–10/17 |
| 8 | Sistemas 2×2 `x' = Ax` (real, complejo, defectivo) | 5/17 |
| 9 | Respuesta impulsional `h(t)` y `x = h*f` | 8/17 |
| 10 | Ecuaciones integrales y integro-diferenciales de convolución | 5/17 |
| 11 | Laplace inversa de racionales y con `e^{-as}` | 6/17 |
| 12 | EDO homogéneas y sustituciones (Bernoulli, `z = y/x`…) con clasificación | 8/17 |
| 13 | Transformada de Fourier para integrales impropias | 6/17 |
| 14 | Convolución discreta por definición y por z; gaussianas | 5/17 |
| 15 | Reducción de orden, variación de parámetros, Picard, Wronskiano | 3/17 |

**Probabilidad y Estadística** (15 exámenes y cuestionarios)

| # | Tipo |
|---|---|
| 1 | Probabilidad total y Bayes |
| 2 | Binomial, geométrica y Poisson en canales, detectores y colas |
| 3 | Aproximación normal (De Moivre–Laplace, TCL) con corrección de continuidad |
| 4 | Intervalo de confianza para la media con t de Student |
| 5 | Intervalo de confianza para proporciones y diferencias; tamaño de muestra |
| 6 | Exponencial y falta de memoria; competición de exponenciales; Gamma |
| 7 | Densidad con constante por determinar; Chebyshev frente al valor exacto |
| 8 | Transformaciones de variables aleatorias (jacobiano, máximo, mínimo, convolución) |
| 9 | Vectores gaussianos y transformaciones lineales |
| 10 | Esperanza condicional, regresión y estimación lineal óptima |
| 11 | Estimadores por momentos y máxima verosimilitud |
| 12 | Proceso de Poisson |
| 13 | Procesos construidos con variables aleatorias: media, autocorrelación, estacionariedad |
| 14 | Procesos discretos de Bernoulli o ±1 |
| 15 | Independencia, combinatoria de ocupación, inclusión-exclusión |

### 15.2 Lo que cambia en el diseño

1. **Verificación numérica obligatoria, no comparación con la solución publicada.** Los cinco informes (y los cuatro de v2, §11.4) encuentran **erratas en las soluciones oficiales** (signos, constantes, tablas de la normal permutadas, fechas, unidades). El laboratorio nunca da por buena una solución por coincidir con la del examen; la verifica por otro camino (§5.3) y, si discrepa de la oficial, lo **señala** y explica la diferencia.
2. **Apartados encadenados.** Muchos problemas reutilizan el resultado de un apartado en el siguiente (la primitiva de (b) en (c)). El modelo de ejercicio guarda los **resultados intermedios** y los ofrece a los apartados posteriores.
3. **Parámetros y discusión por casos.** Es la mayor dificultad en Álgebra (diagonalizar con parámetros, raíces no racionales, R frente a C) y en Cálculo (límites y convergencia con parámetros). El motor debe **ramificar por casos** y presentarlos ordenados.
4. **Correcciones por propiedad, no por valor.** Las bases ortonormales no son únicas; se verifican por `A·v = λ·v`, por reconstrucción de la matriz, etc.
5. **Convenciones de parámetros** que generan errores: tasa o media, σ o σ², varianza muestral con n o con n−1, redondeo a tabla o valor exacto, objetos distinguibles o no. Cada ejercicio **declara su convención** y la muestra; en v2 el catálogo de convenciones es la tabla de §5.11.
6. **Sin calculadora en los exámenes.** Piden decidir signos y comparar (`2√2 < π`, `e < 3`). Se incluye un modo de **cotas racionales** que justifica esas desigualdades.
7. **Hipótesis y contraejemplos.** «Enunciad el teorema y comprobad las hipótesis» es un tipo de pregunta en sí (con contraejemplos como `x^{2/3}` para Rolle).
8. **Gráficas.** En cálculo vectorial son casi siempre necesarias (región, sólido con normales, curva con orientación). En Ecuaciones Diferenciales solo se piden pocas veces, pero la teoría y el resto de la app las necesitan.
9. **Tablas estadísticas** (normal, t, chi-cuadrado, F) **calculadas**, con los valores que usan las soluciones como casos de prueba (1,96; 2,57; t₁₉ = 2,093…).
10. **Notación y variantes.** Algunos textos usan `j` en vez de `i`, pedir «respuestas cualitativas» (existencia y unicidad), espacios de polinomios, matrices o sucesiones, y productos escalares por integral o por evaluación: el motor los admite.

### 15.3 Temas del catálogo que los exámenes no usan (prioridad baja)

En los 17 exámenes de Ecuaciones Diferenciales **no aparecen** EDP, métodos numéricos, campo de direcciones, plano de fases ni estabilidad; en Probabilidad, contrastes de hipótesis, ergodicidad, densidad espectral ni filtrado; en Cálculo, capítulo de métodos numéricos. Siguen en el catálogo (§4) y **tendrán su calculadora completa** (§8), por decisión del usuario; solo **pasan a las últimas fases sus ejercicios y generadores**.

### 15.4 Efecto en las fases

El orden de §10 se mantiene, con este añadido: cada fase se da por cerrada cuando resuelve **sus tipos prioritarios de §15.1** con pasos, por qué, hipótesis, gráfica y verificación. Dos tipos nuevos que faltaban en el plan: **SVD y pseudoinversa** (en ML-3) y **Laplace con segundo miembro por trozos, escalón y delta** (en ML-8, con la región de convergencia). **v2:** las fases ML-12 a ML-22 se cierran del mismo modo con los tipos de §15.6.

### 15.5 Limitaciones de la lectura

- Las soluciones oficiales de Álgebra 2018–2024 son manuscritas y escaneadas; solo se miraron a fondo tres finales y tres problemas de valores singulares, y el razonamiento de los demás años está en parte inferido (marcado así en el informe).
- Quedan sin texto extraíble los `apuntes definitivos.pdf` de Cálculo Vectorial y las fotos `IMG_0769` a `IMG_0774` de Probabilidad (corruptas). Falta OCR.
- Tres parciales de Cálculo Vectorial (abril y noviembre de 2018, abril de 2019) solo traen enunciado.
- En Cálculo Vectorial, los apuntes de 2022 solo se leyeron por índice y enunciados de teoremas; en Probabilidad, los temas 1 a 6 de la teoría por índice y palabras clave.
- Los recuentos de frecuencia son manuales; pueden variar en ±1.

### 15.6 Tipos prioritarios de los bloques nuevos (v2)

**E** (con recuento) primero y **G** después. Frecuencias manuales (±1 o ±2); las de **G** son peso de temario, **no de examen**.

**Respaldo E (se construyen primero)**

| # | Tipo | Bloque | Recuento |
|---|---|---|---|
| 1 | DTFT: núcleo de Dirichlet, módulo, salida a sinusoides | 15 | ≈ 20/29 (Señales y Sistemas) |
| 2 | Periódicas: señal base, `c_k`, TF de deltas | 15 | ≈ 18/29 |
| 3 | Convolución analógica por tramos | 15 | ≈ 14/29 |
| 4 | Energía, potencia, correlación y densidad espectral deterministas | 15 | ≈ 12/29 |
| 5 | Convolución digital y regímenes; DFT circular frente a lineal; eco, inverso y polos y ceros | 15 | ≈ 9/29, ≈ 8/29 y ≈ 8/29 |
| 6 | Fasores, onda plana y potencia media | 17 | ≈ 100 % de EAFO |
| 7 | Jones, retardadores y elipse de polarización | 17 | ≈ 10/13 |
| 8 | Medios con pérdidas: exacto frente a aproximado | 17 | ≈ 12/17 |
| 9 | Electrostática con simetría, `E` y `V` por regiones; conductores concéntricos y tierra | 18 | 9/9 de Electromagnetismo (las 3 esferas, 5 veces) |
| 10 | `V` dado ⇒ `E`, `ρ`, flujo por un cubo | 18 | 5/5 parciales |
| 11 | Carga total con densidad no uniforme | 18 | 8/9 |
| 12 | Maxwell diferencial: verificar y completar campos | 18 | 2/4 finales y ~12 enunciados |
| 13 | Ecuación de onda con perfil arbitrario y trazas | 18 | ≈ 6/17 |
| 14 | Equilibrio y oscilaciones desde `U(x)` | 19 | ≈ 12/15 |
| 15 | Cifrado César y aritmética modular | 9 | 3/7 finales de APR |
| 16 | Fresnel, Brewster, reflexión total y multicapa (D12) | 17 | ≈ 11/13 (EAFO) |
| 17 | Coulomb, Biot-Savart, Ampère, condensadores, inducción y Poynting (D12) | 18 | Electromagnetismo (9/9, 4/4, ~7/9, 5/6 por tema) |
| 18 | Cinemática intrínseca de curvas (D12) | 4.4 | ≈ 12/15 (Física) |
| (opc.) | Termodinámica del gas ideal; Maxwell-Boltzmann, Planck y Stefan (D12) | 19 | 15/15 (opcional) |

**Respaldo G (después), en el orden del informe de algoritmia y del de señales**

| # | Bloque | Por qué va en ese orden |
|---|---|---|
| 1 | 9 y 10: modular y GF, códigos lineales, compartición de secretos, RSA y DH | Temario alto; comparten GF y Gauss; es el **cambio de arquitectura** más claro |
| 2 | 13: descenso de gradiente, regresión, redes a mano, k-medias, PCA | Temario alto en cuatro asignaturas |
| 3 | 12: Markov, MDP, Bellman, Q-learning | Hueco conocido de Probabilidad |
| 4 | 14: finanzas | Bloque cerrado y muy calculable |
| 5 | 11: información | Hilo común barato |
| 6 | 16: detección (T2, 12 h), Wiener (T4, 11 h), Cramér-Rao (T3, 15 h), LMS y gradiente (T5, 12 h) | Sin exámenes; pesos de la guía de Tratamiento de la Señal |
| 7 | 8: lógica, inducción, recurrencias, complejidad | Nivel bajo y mucha reutilización |
| 8 | Ampliaciones de D12: PSD teórica (16), BER y ALOHA (§4.6), tiempo real (8), privacidad (10), antenas y enlace (18), órbitas (19) | Solo guía; se construyen al final de su fase |

### 15.7 Lo que cambia en el diseño por la segunda tanda (v2)

1. **Racionales multivariable, cuerpo como parámetro y contrato** entran en ML-12 antes que todo lo demás (§5.1, §5.9, §5.10).
2. **Convenciones declaradas** en cada ejercicio, con verificación contra la contraria (§5.11).
3. **Erratas como casos de prueba** de verificación cruzada y análisis dimensional (§11.4).
4. **Figuras como datos**, soluciones no únicas y corrección por propiedad (§7).
5. **Distribuciones** (áreas de delta) en el motor (§5.1).
6. **Operadores ∇ en curvilíneas** como ampliación de Cálculo Vectorial (§4.4): faltaban en los cinco catálogos.
7. **Etiquetado de evidencia E y G** por tipo de ejercicio (§3): al disponer de exámenes de Códigos, Aprendizaje, Refuerzo, Finanzas o Tratamiento de la Señal, hay que reordenar los G.
8. **Segundo camino con motores de otros laboratorios** (`ac/`, `control/`, `dsp/`, `gum.py`) mediante plug-ins, sin duplicarlos (§5.8, §5.9).

### 15.8 Limitaciones de la segunda lectura (v2)

- **Solo guía, sin ejercicios ni exámenes:** Tratamiento de la Señal, MATLAB, Telecomunicación espacial, Circuitos Analógicos, Control, Energía, Materiales, Tecnología Electrónica, PSPICE, IMATEC, códigos y secreto, Seguridad, Aprendizaje (automático, profundo y por refuerzo), Resolución de Problemas con IA, Ingeniería Financiera, Tiempo Real, IoT y Robots. Tipos y frecuencias **inferidos del temario**.
- Los apuntes de terceros de Señales y Sistemas (`Primer Control.pdf`, `Segundo Control.pdf`), los exámenes «Resuelto» de Electromagnetismo, parte de los de EAFO 2019-2021 y los PDF de EAFO 2024 y 2026 son **imágenes sin texto**; falta OCR.
- La ruta de ICAF contiene solo un zip de **Radiación y Propagación**: lo marcado como ICAF es **inferencia**. El tema 6 de EAFO no tiene material.
- Las soluciones de Análisis de Circuitos son manuscritas: los conteos salen de los enunciados impresos. Un solo examen de CCE.
- Fórmulas citadas de memoria de dominio (Ackermann, DCM, IPC-2221, Liu-Layland, CRR, FSPL, Shamir, Huffman) **se verifican con el motor propio**, no se dan por buenas por el informe.
- Los recuentos de frecuencia son manuales (±1 a ±2).

---

## 16. Qué va dónde (v2)

**Regla del usuario:** MATH_LAB es la **capa matemática**; SIGNALS_LAB y CIRCUITS_LAB son laboratorios de **aplicación** que reutilizan su motor (§5.9). `SIGNALS_LAB.md` (§3.1, reparto en tres columnas) y `CIRCUITS_LAB.md` (§3.3, capa matemática compartida) están escritos; esta tabla está **alineada con ellos**. La regla de frontera de SIGNALS_LAB §3.1 es la que manda: *si un resultado es una fórmula cerrada con pasos, lo calcula MATH_LAB; si es una medida, un diseño numérico, una simulación o una gráfica interactiva, es del laboratorio de aplicación*. Las secciones se citan por nombre y número; si un número cambia, el nombre manda.

### 16.1 Tabla de referencias cruzadas

| Tema | Dónde | Qué aporta MATH_LAB al otro laboratorio |
|---|---|---|
| Convolución por tramos, series de Fourier por señal base, DTFT, DFT (propiedades y circular), transformada z, eco e inverso, energía, correlación y densidad espectral deterministas | **MATH_LAB** (bloque 15); el visor es de SIGNALS_LAB (§7, §8) | Cálculo exacto y pasos; SIGNALS_LAB dibuja y contrasta numéricamente |
| **Propiedades de sistemas** (linealidad, invariancia, causalidad, estabilidad BIBO) y respuesta a sinusoides (D12) | **SIGNALS_LAB** (§7.1, SS-1) | Paso algebraico y hipótesis (§5.3, §5.7); la prueba numérica de SIGNALS_LAB solo refuta |
| Respuesta en frecuencia `H(f) = TF{h}` por definición | MATH_LAB (bloque 15); visor de `abs(H(f))` en SIGNALS_LAB (§7.5) | Cálculo exacto |
| **Lectura de espectros**, problema inverso `k ⇒ A, f, L`, desincronización y fuga | **SIGNALS_LAB** (§8) | DFT, DTFT y su verificación numérica |
| **Ventanas** y resolución espectral | **SIGNALS_LAB** (§9) | `W(F)` teórica |
| **Muestreo**, aliasing, reconstrucción, D/A con triángulo o ZOH | **SIGNALS_LAB** (§10) | DTFT, periodicidad en frecuencia (el teorema de muestreo lo da Ecuaciones Diferenciales y Transformadas) |
| **Modulación y multiplexación** (FDM, TDM, digital) | **SIGNALS_LAB** (§11) | Convolución con `δ`, DTFT |
| **Diseño de filtros FIR e IIR** (ventanas, Remez, plantilla, Butterworth, bilineal) | **SIGNALS_LAB** (§12) | Fórmulas cerradas de plantilla (`δ_p`, `δ_a`), orden mínimo de Butterworth, raíces, Gibbs, `abs(H(F))` |
| **Filtro adaptado** y decisión entre pulsos | **SIGNALS_LAB** (§13) | `r_xy`, Cauchy-Schwarz; el detector general es MATH_LAB (bloque 16) |
| **STFT, espectrograma, periodograma, Welch**; PSD estimada | **SIGNALS_LAB** (§14) | PSD **teórica** (bloque 16, D12) |
| **Diezmado, interpolación, polifase** | **SIGNALS_LAB** (§15) | — |
| **Cuantización** y A/D, D/A (D12) | **SIGNALS_LAB** (§16); circuito ADC/DAC en CIRCUITS_LAB | `SQNR = 6,02·b + 1,76 dB` como calculadora (§8.2 I) |
| Detección (MAP, NP, ROC), Cramér-Rao, Wiener, LMS y NLMS | **MATH_LAB** (bloque 16); escenas, Monte Carlo y curvas de aprendizaje en SIGNALS_LAB (§17) | Valor exacto y pasos por «uso por programa» |
| Fasores y polarización de Jones, onda plana, medios con pérdidas, **Fresnel y multicapa (D12)** | **MATH_LAB** (bloque 17) | Lo usa CIRCUITS_LAB para impedancias y potencia |
| Electrostática por regiones, verificación de Maxwell, onda por sustitución, operadores ∇, **Coulomb, Biot-Savart, Ampère, condensadores, inducción y Poynting, antenas y enlace (D12)** | **MATH_LAB** (bloque 18 y §4.4) | — |
| `U(x)`, termodinámica (opcional), **órbitas (D12)** | **MATH_LAB** (bloque 19) | — |
| **Bode** (asintótico y real), **síntesis de `H(s)`** desde una curva, tipo de filtro | **CIRCUITS_LAB** (§10, `ac/`) | **Racionales multivariable**, forma normal, raíces con parámetros |
| **Transitorios** con conmutación y eventos | **CIRCUITS_LAB** (§5.5 bloque B, §8.5) | EDO de 1.er orden, continuidad, `ln` de eventos; Laplace como técnica (EDT) |
| **GUM e incertidumbre**, peor caso, RSS, Monte Carlo, aberrantes, ruido y ENBW | **CIRCUITS_LAB** (§13.4.1) | Monte Carlo sembrado, `t` de Student (ya en `gum.py`); la **convención de Chauvenet** (§5.11) |
| **Circuitos a trozos**, punto de trabajo, pequeña señal, margen dinámico | **CIRCUITS_LAB** (BL-AC-13, §9) | Desigualdades por casos, cuadráticas con raíz válida, Lambert W |
| **Ajuste y calibración de sensores** (RTD, NTC, termopar, Steinhart-Hart) | **CIRCUITS_LAB** (§13.4.3 y §13.4.4) | **Mínimos cuadrados lineales y no lineales**, linealización por transformación |
| **Estabilidad** (Routh con parámetro, lugar de raíces, Nyquist, Jury), espacio de estados, Lyapunov, Ackermann | **CIRCUITS_LAB** (§13.3.4) | Raíces, autovalores, exponencial de matriz (§4.3), desigualdades polinómicas |
| **Calculadora de dB** y escalas logarítmicas | **CIRCUITS_LAB** (§14.2.2, Anexo C) | La **convención** de dB (§5.11); logaritmos |
| **Líneas de transmisión**, carta de Smith, adaptación, parámetros S y ABCD, **guías de onda y cavidades** | **CIRCUITS_LAB** (§11.3 a §11.5, §11.11) | Complejos, matrices unitarias, trascendentes con todas las raíces |
| **Lámina dieléctrica y fibra** (ecuación trascendente de dispersión) | CIRCUITS_LAB solo la **referencia** (§11.11 no la resuelve); el **solucionador** es MATH_LAB (§4.7, trascendentes con todas las raíces) | Barrido de signo + bisección + Newton |
| **Conversión de potencia** (buck, boost), THD y factor de potencia, magnéticos | **CIRCUITS_LAB** (§12) | Valor medio y eficaz, Fourier |
| Redes matriciales, Tellegen, Mason, sensibilidad | **CIRCUITS_LAB** (BL-AC-14, §10) | Subespacios fundamentales, sistemas lineales |
| **Problemas de contorno** y electrostática 1D de la unión PN (§9.2), Lambert W (BL-DEV-5), curva I-V fotovoltaica (§12) | **CIRCUITS_LAB** (aplicación) | **Solvers de MATH_LAB** (§4.5, §4.7) |
| **Fracciones racionales multivariable** | MATH_LAB (ML-12); CIRCUITS_LAB (§3.3, su D2) decide crear `ratfun` mínimo o esperar | Dependencia crítica (§5.1) |
| Aritmética binaria, lógica y bases de numeración (diseño digital) | **DIGITAL_DESIGN_LAB** (existente) | Bases (§4.0); complemento a 2 con banderas: implementación única en `DIGITAL_DESIGN_LAB.md` §10 |

### 16.2 Interfaz: cómo usan el motor los otros laboratorios

Según §5.9: llamada tipada → resultado con traza, sello y gráfica descrita; plug-ins de verificación; plantillas de ejercicio y figuras como datos; versión de contrato; prueba de contrato. Los tres sellos son los mismos que citan SIGNALS_LAB y CIRCUITS_LAB (§8.1). **Dependencia crítica:** racionales multivariable (§5.1); sin ellos, CIRCUITS_LAB no puede simplificar una `H(s)` con símbolos. Convenciones: la tabla de §5.11 y el Anexo C de CIRCUITS_LAB deben coincidir en las comunes (amplitud, fasor, dB).

### 16.3 Resolución de D12 (aprobada con la propuesta; antes «pendientes»)

El usuario aprobó la propuesta de cada informe. Donde la propuesta nombraba «MATH_LAB o X», se tomó MATH_LAB si SIGNALS_LAB no lo cubre ya.

| Tema | Decisión aplicada | Dónde queda |
|---|---|---|
| Propiedades de sistemas y respuesta en frecuencia a sinusoides | **Fuera** de MATH_LAB | SIGNALS_LAB §7.1; la biblioteca de señales básicas ya está en el bloque 15 |
| Densidad espectral de procesos discretos, PSD de AR(1) | **Dentro** (parte teórica) | Bloque 16 (§4.16, ML-18); el visor y la ergodicidad, SIGNALS_LAB §14.4 y §17 |
| Cuantización (SQNR) | **Fuera**, salvo la calculadora | SIGNALS_LAB §16; calculadora en §8.2 I |
| Coulomb, Biot-Savart, Ampère, polígono → círculo, condensadores y dieléctricos, inducción, Poynting | **Dentro** | Bloque 18 (§4.18, ML-16), E |
| Cinemática intrínseca, oscilador con Q, conducción de calor | **Dentro** | §4.4 (ML-13), §4.5 (ML-8), E |
| Maxwell-Boltzmann, Planck y Stefan | **Dentro**, opcional con la termodinámica | Bloque 19 (ML-22) |
| Fresnel, Brewster, evanescente, multicapa | **Dentro** | Bloque 17 (§4.17, ML-15), E |
| Antenas, balance de enlace, ruido de sistema | **Dentro**, G prioridad baja | Bloque 18 (ML-16, al final) |
| Mecánica orbital (Kepler), visibilidad esférica | **Dentro**, G prioridad baja | Bloque 19 (ML-22) |
| BER con `Q`, ALOHA, Rayleigh y Rice | **Dentro**, G | §4.6 Probabilidad (ML-9) |
| Privacidad: k-anonimato, microagregación, privacidad diferencial | **Dentro**, G | Bloque 10 (§4.10, ML-17) |
| Tiempo real (Liu-Layland, RTA, hiperperiodo) y ARQ | **Dentro**, G | Bloque 8 (§4.8) y §4.6 |
| Cinemática de robot diferencial, PID discreto, Kalman 1D | **Fuera** (el control discreto es de CIRCUITS_LAB, BL-CT-9) | §17 |
| Cristalografía (Miller, Bragg) y fiabilidad serie-paralelo | **Fuera** | §17 |

---

## 17. Fuera de alcance (anotado, v2)

Por decisión del usuario (D11) **no entran** en el laboratorio de matemáticas en esta versión:

- **Variable compleja general** (residuos, Laurent, integrales de contorno): 0 apariciones en los exámenes y guías leídos. Solo queda la aritmética de complejos con **ramas de la raíz** (bloque 17).
- **Funciones de Legendre**, multipolos y armónicos esféricos; **separación de variables en cilíndricas y esféricas** (Bessel y Legendre). Se mantiene solo la EDP introductoria de §4.5.
- **Laplace y Poisson en 2D y 3D** (en 1D por tramos sí, §4.5).
- **CPM, PERT y EVM** (gestión de proyectos).
- **Redes sobre grafos (GCN)** y **GAN/VAE** (el producto de matrices, la atención y la entropía cruzada sí están en el bloque 13).
- **IEEE 754 profundo** (punto flotante) y **complemento a 2 con desbordamiento** (este último es de `DIGITAL_DESIGN_LAB.md` §10).
- **Juegos de tablero y matrices como estructura de datos** (sudoku, buscaminas, dominó, sopa de letras): lógica de programación, no matemática.
- **MATLAB** como lenguaje, M-files, toolboxes y GUI. Solo una tabla de equivalencias (`roots`, `polyfit`, `conv`, `filter`, `fft`, `residue`, `xcorr`…) como campo «cómo se comprueba con tu herramienta» en la verificación (§5.3).
- **(D12)** Cinemática de robot diferencial, PID discreto y Kalman 1D (el control discreto es de CIRCUITS_LAB, BL-CT-9); cristalografía (Miller, Bragg) y fiabilidad serie-paralelo.
- Lo asignado a **SIGNALS_LAB** y **CIRCUITS_LAB** (§16.1), incluidas las propiedades de sistemas y la cuantización (D12).

---

*Fin del documento (v2, 2026-10-01). Decisiones D1 a D12 cerradas. La implementación ya está iniciada: ML-0 aporta las calculadoras base (`derivar`, `gradiente`, `simplificar`, `evaluar`, `igualdad`, `integrar`) y el motor trigonométrico exacto añade reglas iniciales de T-01, T-02, T-03 y T-05. Estas capacidades siguen siendo parciales respecto al alcance completo de sus familias. Las familias restantes permanecen explícitamente pendientes; no se consideran entregadas por mera documentación.*

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


## Capacidad transversal — conversión de unidades y análisis dimensional

El laboratorio incorpora un conversor de unidades reutilizable como herramienta matemática y como comprobador de problemas.

### Alcance
- Unidades SI y prefijos: longitud, masa, tiempo, área, volumen, velocidad, aceleración, fuerza, energía, potencia, presión, temperatura, frecuencia, carga, tensión y magnitudes habituales del grado.
- Ángulo: grados, radianes y revoluciones.
- Magnitudes derivadas mediante expresiones de unidades.
- Conversión entre unidades compatibles, con preservación de exactitud cuando sea posible.
- Conversión de intervalos y órdenes de magnitud sin límites artificiales de valor; el **rango de unidades soportado** sí queda acotado por el catálogo declarado por el motor.
- **Rango completo de prefijos SI:** desde `10⁻³⁰` hasta `10³⁰` (`quetta`/`Q` … `quecto`/`q`), incluyendo todos los prefijos oficiales intermedios. El motor debe aceptar, normalizar y convertir cualquiera de ellos cuando sea aplicable a la magnitud.
- Detección de unidades incompatibles antes de calcular.
- Análisis dimensional como verificación independiente de fórmulas y ejercicios.
- Trazabilidad: unidad de entrada, unidad canónica, factor aplicado, resultado y unidad de salida.

### Uso pedagógico
Las conversiones no son una calculadora aislada: pueden aparecer como paso de cualquier ejercicio, mostrar el procedimiento y comprobar dimensionalmente el resultado final.

### Regla de diseño
La implementación de unidades debe ser compartida por los laboratorios y no duplicarse en cada dominio. `MATH_LAB` define/consume la capacidad genérica; los demás laboratorios la reutilizan con sus unidades específicas.



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


### Motor transversal de unidades — requisitos completos

MathLab actúa como referencia del motor común de unidades. Además del rango completo de prefijos SI **10⁻³⁰ → 10³⁰**, debe contemplar:
- unidades simples y derivadas;
- unidades compuestas como `m/s²`, `N·m` y `kg·m/s²`;
- productos, cocientes y potencias de unidades;
- simplificación y normalización de unidades;
- conversión automática;
- análisis dimensional;
- detección de unidades incompatibles;
- temperatura como conversión afín;
- ángulos;
- magnitudes logarítmicas como dB mediante reglas específicas;
- selección y normalización automática de prefijos;
- trazabilidad `entrada → normalización → factor/regla → unidad canónica → resultado`.

Las unidades forman parte del valor tipado y no son texto decorativo. El motor debe poder distinguir, por ejemplo, una conversión válida de `25 mA → 0,025 A` de una magnitud incompatible o de un factor de prefijo incorrecto. El catálogo de unidades y las reglas especiales son extensibles sin duplicar el motor en cada laboratorio.


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


### Capacidades específicas adicionales — MathLab

- El motor debe poder representar formalmente el **dominio de validez** de un modelo o método (por ejemplo, restricciones de dominio, convergencia y condiciones de teoremas).
- La comparación de métodos debe permitir contrastar solución exacta, aproximación numérica y verificación independiente.
- Las unidades y el análisis dimensional deben participar en la validación antes de evaluar expresiones.
- El historial de intentos debe conservar la estructura de pasos matemáticos, no solo la respuesta final.


## Especificación completa — trigonometría para Ingeniería

La trigonometría de MathLab se considera un submotor simbólico completo. Cada familia debe disponer de reglas estructurales, control de dominio, trazabilidad, pruebas exactas y verificación independiente antes de marcarse como completada.

### T-01. Funciones y representación fundamental — COMPLETADA
- sin, cos, tan; cot, sec, csc.
- inversas asin/arcsin, acos/arccos, atan/arctan.
- grados, radianes y revoluciones.
- valores notables y reducción por cuadrantes.
- evaluación exacta y fallback numérico con precisión declarada.

### T-02. Relaciones fundamentales — COMPLETADA
- tan=sin/cos; cot=cos/sin; sec=1/cos; csc=1/sin.
- sin²+cos²=1.
- 1+tan²=sec².
- 1+cot²=csc².
- todas las formas despejadas equivalentes.

> **Última línea, por qué no es una regla de `simplify`.** Las seis escrituras de
> `tg = sen/cos` se reconocen — `sen/tg = cos`, `cos/sec = cos²`, `tg/sen = 1/cos`,
> `sec/cos = 1/cos²`, `sen·cot = cos`, `cos·cosec = cot` — pero en un objetivo
> aparte, `trig.razones(expr)`, no en la simplificación por defecto.
>
> La razón es el dominio. `sen(x)/tg(x)` y `cos(x)` coinciden donde las dos existen y
> se diferencian en todas partes: la primera no existe en `pi/2` y la sí. Los
> solucionadores leen el dominio de lo que devuelve `simplify`, así que fundirlas
> allía mueve el dominio: medido, puso 193 de 383 respuestas en el lado
> equivocado de una inecuación. La regla existe, dice en su paso dónde vale (§5.7) y
> no se cuela en el camino de nadie.

### T-03. Paridad, simetría y periodicidad — COMPLETADA
- paridad.
- periodicidades fundamentales.
- reducción de argumentos mediante períodos.
- simetrías de cuadrante.
- ángulos opuestos, suplementarios y complementarios.

### T-04. Suma y diferencia de ángulos — COMPLETADA
- sin(a±b), cos(a±b), tan(a±b).
- formas equivalentes e inversas.
- reconocimiento dentro de expresiones mayores.
- control de denominadores y dominio.

### T-05. Ángulo doble — COMPLETADA
- sin(2x), cos(2x), tan(2x).
- las tres formas principales de cos(2x).
- reconocimiento inverso.
- preservación de restricciones.

### T-06. Ángulo triple y múltiple — COMPLETADA
- sin(3x), cos(3x), tan(3x).
- fórmulas generales nx.
- expansión recursiva y reconocimiento inverso.
- polinomios de Chebyshev cuando sean útiles.

### T-07. Medio ángulo y sustitución universal — COMPLETADA
- sin²(x/2), cos²(x/2), tan²(x/2).
- signos y restricciones de intervalo.
- t=tan(x/2).
- racionalización de expresiones trigonométricas mediante la sustitución.

### T-08. Producto a suma — COMPLETADA
- sin(a)sin(b), cos(a)cos(b), sin(a)cos(b).
- todas las variantes de signos.
- uso en simplificación e integración.

### T-09. Suma a producto — COMPLETADA
- sin(a)+sin(b), sin(a)-sin(b).
- cos(a)+cos(b), cos(a)-cos(b).
- formas inversas de T-08.

### T-10. Reducción de potencias — COMPLETADA
- reducción de sin² y cos².
- potencias pares superiores.
- productos de potencias.
- selección de forma útil para integración.

### T-11. Composición y funciones inversas — COMPLETADA
- composiciones.
- sin(asin(x)), cos(acos(x)), tan(atan(x)).
- asin(sin(x)), acos(cos(x)), atan(tan(x)) con ramas y restricciones.
- discontinuidades y dominios.
- evitar identidades globales falsas.

### T-12. Ecuaciones trigonométricas — COMPLETADA (elementales, con fase, polinómicas y racionales, **productos** y **el cuadrado que elimina una función**: `sen(x)*cos(x) = 0` da cuatro familias —`0`, `π`, `±π/2`— y `sen(x)*cos(x)*tg(x) = 0` da dos, `0` y `π`. La etiqueta decía que el primero «no entra en los casos y se rechaza», y era falso: el rechazo era correcto, la razón no. Etiqueta revisada el 2026-10-04 contra el motor)
- ecuaciones elementales.
- ecuaciones transformadas por identidades.
- polinomios en sin/cos.
- ecuaciones racionales.
- soluciones generales y en intervalos.
- detección de soluciones espurias.
- verificación en la ecuación original.

### T-13. Inecuaciones y análisis de dominio — COMPLETADA (dominio de cualquier expresión: denominadores, polos de las funciones y lo que cada una pide de su argumento)
- desigualdades trigonométricas.
- intervalos de signo.
- ceros, singularidades y denominadores.
- restricciones de inversas.
- conjuntos solución periódicos.

### T-14. Trigonometría hiperbólica — COMPLETADA (identidades, suma/diferencia, dobles, inversas, conexión exponencial, **las seis derivadas y las seis integrales**. Las dos últimas —`sech` y `csch`— se cerraron el 2026-10-04, y la etiqueta decía «faltan las derivadas», que existían todas)
- sinh, cosh, tanh, coth, sech, csch.
- identidades.
- suma/diferencia.
- múltiplos.
- inversas.
- conexión exponencial.
- derivadas e integrales.

### T-15. Complejos y Euler — COMPLETADA
- e^(ix)=cos(x)+i sin(x).
- formas rectangular, polar, trigonométrica y exponencial.
- trigonometría compleja.
- identidades de Euler.
- De Moivre.
- raíces y argumentos.
- ramas.

### T-16. Fasores y aplicaciones de Ingeniería — COMPLETADA
- magnitud/fase.
- rectangular↔polar.
- operaciones con fasores.
- señal sinusoidal↔fasor.
- frecuencia angular, desfase y RMS cuando corresponda.
- contrato de interoperabilidad con CIRCUITS_LAB y SIGNALS_LAB.

### T-17. Derivación trigonométrica — COMPLETADA (la tabla de derivadas cubre circulares, recíprocas, inversas, hiperbólicas e hiperbólicas inversas, con su dominio)
- funciones circulares, inversas, hiperbólicas e inversas hiperbólicas.
- regla de la cadena.
- productos, cocientes y composiciones.
- órdenes superiores.
- verificación independiente.

### T-18. Integración trigonométrica — **COMPLETADA** (2026-10-04). Cierra sus tres límites declarados en un día, y ninguno de los tres era una función que faltara:

1. **El discriminante negativo.** Decía que a la capa `symbolic` le faltaba `arctg`. No faltaba la función: faltaba el **nombre**, y en tres sitios a la vez —la tabla de derivadas de T-17 llevaba `atan` desde hacía meses—. La gramática del parser y la del evaluador certificado son dos listas distintas escritas en dos sitios distintos, así que se cerraron a la vez y `ENGINE_VERSION` pasó de `engcalc/6.0` a `engcalc/6.1`. Al evaluador se le añadieron quince funciones, cada una escrita como la identidad que la define sobre `sen`, `cos`, `exp` y `ln`, sin una segunda serie en ningún sitio.
2. **La cuadrática irreducible al cuadrado.** `(u²+1)²` llegaba a `_factores` escrito como `u⁴ + 2u² + 1`, un cuartico sin raíz racional, y **el polinomio que llegaba nunca fue un cuartico**: era una cuadrática escrita dos veces y nadie miró a ver si lo era. Con la descomposición squarefree (Musser) cierran `∫du/(u²+1)²`, `∫(u+1)/(u²+1)²`, `∫du/(u²+1)³`, `∫du/(u²+1)⁴` y `∫sen²x/(1+cos x) dx`.
3. **El cuartico sin raíz racional.** `∫du/(u⁴+1)` se negaba porque el denominador no tiene raíz racional y `_factores` solo miraba raíces racionales. Un biquadrático sí se parte: `u⁴ + a u² + c = (u² + pu + q)(u² - pu + q)` con `q = √c` y `p² = 2q - a`. No hizo falta aritmética de cuerpos: `q` se exige racional, de modo que solo un coeficiente de la respuesta lleva radical —`β - α·p/2` se simplifica a `(A + C/q)/4`, que es racional—, y `√(p²)·t` es un producto, no un tipo nuevo. Cierran `∫du/(u⁴+1)`, `∫du/(u⁴+u²+1)`, `∫du/(u⁴-6u²+1)` y `∫dx/(cos x·cos 2x)`.

Verificadas **derivando** en 81 puntos por caso: error máximo 1,2·10⁻²⁶.

Lo que sigue negándose no es un límite sino **clases**, y cada una con su motivo escrito, porque un rechazo sin motivo no es una frontera: es una ignorancia con forma de límite. `√c` irracional (`1/(u⁴+2)`, que necesita dos radiales), denominador no mónico (`1/(3u⁴+2)`), potencia del biquadrático (`1/(u⁴+1)²`) y numerador impar sobre denominador par (`∫u/(u⁴+1) du`). Las cuatro están en listas que **fallan** el día que se cierren.

Etiqueta revisada cuatro veces el 2026-10-04. Las tres primeras contralistas dijeron cosas que ya eran falsas —que faltaban la reducción de potencias, que faltaban las partes para logaritmos, y que la etiqueta estaba «cerrada entera» siendo parcial— y se corrigieron contra el motor, no contra la memoria)

### T-19. Series y aproximaciones — **COMPLETADA** (2026-10-05). El límite que la mantenía en PARCIAL era uno solo: la cota de error cuando no hay cota sobre la derivada omitida. Cerrado, y al cerrarlo Resultó que **dos de las tres cotas que el motor declaraba no eran cotas** — no estaban flojas, estaban al revés, en el semiplano negativo y en el argumento grande, que es donde nadie miraba. 546 puntos comprobados el 2026-10-05 entre `maclaurin` y `taylor`, 0 fallos de acotado:

  **Lo que hay ahora.** Las siete series conocidas llevan cota, todas por el mismo mecanismo: la cola de la serie mayorizada término a término por una progresión geométrica construida con sus propios coeficientes. El primer término omitido se compara con `|x|^m/m!` y la razón entre términos sucesivos se acota por una constante por debajo de 1, así que la cola deja de ser una suma sin nombre y pasa a ser una serie geométrica con valor.

  | serie | razón de la mayorización | válida para |
  |---|---|---|
  | `sin`, `cos`, `sinh`, `cosh` | `\|x\|²/((m+1)(m+2))` | `\|x\| < √((m+1)(m+2))` |
  | `exp` | `\|x\|/(m+1)` | `\|x\| < m+1` |
  | `tan` | `\|x\|²/2` | `\|x\| < √2`, dentro del radio π/2 |
  | `ln` | `\|x\|` | `\|x\| < 1`, su radio de convergencia |

  donde `m` es la primera potencia que la truncación no escribe. Cada cota viaja con **su dominio y con el argumento que la sostiene**, leídos en `serie.hipotesis`: una cota sin dominio es un número, y un número sin dominio es una promesa que nadie puede comprobar.

  **Los dos fallos que encontró la verificación.** El motor declaraba el primer término omitido como cota de `sin`, `cos` y `ln`, y lo medido dice que sólo lo era en parte:
  - `sin` y `cos`: la estimación alternante exige que los términos **decrezcan**, y `x^9/9!` deja de decrecer pasado `x ≈ 8,5` (el cociente `(x^9/9!)/(x^7/7!)` es `x²/72`). Para un argumento grande la cota declarada era menor que el error real y se imprimía como cota superior.
  - `ln`: la serie de Mercator alterna **sólo para `x > 0`**. En `x < 0` todos los términos son negativos, la cola es monótona y el primer término omitido es cota **inferior**. En `x = -0,9` con cinco términos el motor declaraba `0,0886` para un error de `0,4725` — más de cinco veces corto, y en la dirección que hace que una cota parezca un resultado. La prueba anterior sólo muestreaba `x > 0`, que es donde no se rompe.

  **Lo que se niega, y por qué.** `taylor` de una **expresión que no reconoce** sigue sin declarar cota, y dice que no la declara. No es un resto de trabajo: el movimiento fácil —ver `exp` dentro de `x²·exp(x)` y reusar la cota de `exp`— está disponible y es falso. Medido: el error real de `taylor(x²·exp(x), 0, 4)` es **20 a 26 veces mayor** que la cota que ese movimiento adjuntaría, en todos los argumentos probados. El polinomio es exacto, no se declara ningún número, y la ausencia se explica en palabras. Tampoco se acota la forma `exp(x) + 1`: su cola no es la cola de `exp` más una constante, y mayorizar una no mayoriza la otra.

  `taylor` de una de las **siete funciones conocidas** ya no se niega — `taylor(exp(x), 0, 6)` llevaba `cota = None` mientras el módulo sabía acotar esa misma cola por `maclaurin`. La serie de `f` sobre `a` es la serie de `u ↦ f(a + u)` sobre el origen, así que la cota se construye en 0 y se sustituye `x → x − a`: para `taylor(ln(x), 1, 4)` la cota sale en `|x − 1|`, y está comprobada en esa variable.

  **`taylor` deja de ser la puerta más débil a la misma serie.** Cerrar la cota dejó
  a la vista algo peor: `taylor(tan(x), 0, 4)` moría con `EXPRESSION_LIMIT` mientras
  `maclaurin("tan", 4)` devolvía la serie sin despeinarse, y lo mismo con `ln`
  alrededor de 1. No era una limitación de orden sino de puerta — `tan' = 1/cos²` y
  `ln^(k) = (k-1)!/x^k`, y derivar cualquiera de las dos expande un producto de
  potencias que el registro de pasos no aguanta, mientras que escribir los números
  tangentes o los términos de Mercator no tiene ese problema. Ahora una función
  conocida se **escribe** en `taylor` en vez de derivarse, y los dos topes (3 y 4)
  suben al orden máximo declarado, 40. Donde ambas puertas podían calcularse
  coinciden exactamente: 48 combinaciones de polinomio, residuo y cota sobre seis
  funciones, 0 diferencias.

  Dos trampas que la delegación cruzó y que quedan vigiladas:

  - **`ln` en el origen.** `maclaurin("ln", n)` es la serie de `ln(1+x)` —una
    rareza deliberada de ese nombre, escrita en sus hipótesis—, pero
    `taylor(ln(x), 0, n)` promete el polinomio de Taylor de `ln` en 0, y ahí no
    existe. Delegando, `taylor` contestaba `x − x²/2 + x³/3 − …` a una pregunta sobre
    `ln`: la serie era correcta, de **otra** función. Antes se negaba con «`ln(0)` no
    es un número», y esa negativa era la respuesta correcta y tenía que sobrevivir al
    arreglo. Sigue negándose, y hay una alarma que lo comprueba.
  - **El radio de `tan` no es el de Mercator.** La hipótesis anunciaba «radio de
    convergencia 1» para las dos, cuando el de `tan` es π/2. Era falso en la
    dirección que prohíbe una serie que converge: entre 1 y 1,57 la serie de `tan`
    suma sin problema, y el módulo lo negaba.

- Taylor/Maclaurin.
- orden solicitado.
- término residual.
- estimación de error.
- convergencia.
- comparación exacta/aproximada.

### T-20. Estrategia de transformación — **COMPLETADA** (2026-10-05). Catorce objetivos declarados, cada uno con su `porque` y su `verifica`: ocho de **reescritura** con reglas —simplificar, expandir, producto_a_suma, suma_a_producto, potencias, sustitucion_universal, hiperbolicas, exponencial—, y seis de **transformación**, que no reescriben nada y devuelven otra clase de cosa: derivar, integrar, complejos, fasores y, desde hoy, **demostrar** (`verify.py`, forma normal exacta y luego simplificación acotada; la coincidencia numérica nunca demuestra) y **resolver** (`ecuaciones.py`, familias con periodo, verificadas sustituyendo en la ecuación original). La especificación nombraba «simplificar, demostrar, resolver, integrar, derivar, complejos, fasores» y el registro tenía cinco de las siete; las dos que faltaban ya existían como operaciones (`igualdad`, `resolver`) pero no como objetivos, y por eso el motor no podía enumerarlas. La calculadora las escribe en la trayectoria. El requisito de «búsqueda acotada, sin ciclos» tiene ahora prueba: cada objetivo de reescritura aplicado a su propia salida no la agranda. Etiqueta anterior: PARCIAL, con cinco objetivos de siete)
El motor debe seleccionar transformaciones según el objetivo: simplificar, demostrar, resolver, integrar, derivar, pasar a complejos o preparar señales/fasores. Debe evitar ciclos y explosión combinatoria mediante búsqueda acotada.

### T-21. Valores exactos y constantes — COMPLETADA
- ángulos notables.
- raíces exactas.
- múltiplos racionales de pi.
- equivalencias exactas.
- fallback numérico con precisión declarada.

### T-22. Verificación formal — COMPLETADA
Cada transformación debe conservar semántica en su dominio, registrar regla y restricciones, y poder verificarse por un camino independiente. La comprobación numérica nunca será la única prueba de una identidad.

### T-23. Gráficas y análisis — COMPLETADA
- período, amplitud, frecuencia y fase.
- ceros, extremos y asíntotas.
- discontinuidades.
- comparación de expresiones.
- aproximación y error.

### T-24. Criterio de completitud — **CUMPLIDO** (2026-10-06): las 23 familias tienen parser, reglas exactas, control de dominio, traza, pruebas, verificación independiente y **operación en la calculadora** (la última pieza: los ocho objetivos de reescritura se piden con `transformar`, que hasta entonces solo alcanzaba `simplificar`)
Una familia solo será COMPLETADA con parser/AST compatible, reglas exactas, control de dominio, trazabilidad, tests, verificación independiente, integración con calculators.py, documentación y CI verde.

Este catálogo es el alcance de implantación de trigonometría para Ingeniería de MathLab. Documentado no significa implementado.

## Capacidad implementada — motor trigonométrico exacto (2026-10-02)

`mathlab/trig.py` es un motor de reglas exacto, conectado a `simplificar`. Cada transformación pertenece a **un** objetivo y solo acepta reescrituras estrictamente más baratas o estrictamente más caras según cuál sea (§5.5b, T-20): esa medida es un orden bien fundado, así que cada objetivo termina y su resultado es un punto fijo por construcción. Mezclar las dos direcciones en un mismo bucle no puede terminar —`sin(2x)` se desarrolla a `2·sin(x)·cos(x)` y vuelve a colapsarse—.

Objetivos y familias:

| Objetivo | Función | Familias |
|---|---|---|
| reducir | `simplify` | paridad, signo fuera de potencia, reducción de argumento, valores notables, pitagoras, recíprocas, doble plegado, suma/diferencia inversa, unidad |
| desarrollar | `expand` | suma y diferencia, ángulo doble directo |
| producto a suma | `product_to_sum` | T-08 |
| suma a producto | `sum_to_product` | T-09 |
| potencias | `reduce_powers` | T-10 |

Lo que esto deja cubierto de la especificación: **T-02** completo (las seis formas de cada relación), **T-03** completo (paridad, periodicidad, opuestos, suplementarios, complementarios, en una tabla por cuadrante en lugar de una regla por signo), **T-04** en ambos sentidos, **T-05** en ambos sentidos y con las tres formas de `cos(2x)` ofrecidas en vez de elegidas, **T-06** (ángulo triple en ambos sentidos, múltiplos cerrados en una sola variable con los polinomios de Chebyshev, y `sin(nx)` en potencias de `sin(x)` solo cuando `n` es impar porque para `n` par no existe), **T-07** (los cuadrados del medio ángulo en ambos sentidos, con ida y vuelta exacta, y la sustitución universal `t = tan(x/2)` como objetivo aparte), **T-08**, **T-09**, **T-10** y la parte de **T-21** que el motor necesita (ángulos notables de 0° a 180° en pasos de 15°/30°/45°, con las seis funciones exactas y `None` donde la función no existe).

Dos decisiones que conviene que queden escritas, porque son cosas que el motor **no** hace:

- El medio ángulo sin elevar al cuadrado no se simplifica nunca. `√((1−cos x)/2) = sin(x/2)` vale en `[0, 2π]` y es falsa fuera, así que el motor se niega y `half_angle_forms` devuelve cada forma con su intervalo (§5.7).
- La sustitución `t = tan(x/2)` es un cambio de variable (§5.6), no una identidad, y por eso vive en su propio objetivo. Mezclarla con las identidades no era una cuestión de gusto: la sustitución *crea* `tan(x/2)` y la regla del medio ángulo *consume* `tan(x/2)²`, así que en un mismo bucle se alimentan y la expresión crece hasta reventar el límite de texto.

**T-14 (hiperbólica)** comparte motor con las circulares porque son las mismas fórmulas con un signo cambiado, y por eso viven en familias aparte para que la traza diga cuál ha actuado. Cubierto: `cosh²−sinh²=1`, `1−tanh²=sech²`, `cosh²−1=sinh²`, `coth²−1=csch²`, `1−coth²=−csch²`, los cocientes y recíprocas, la paridad de las seis, `sinh(asinh(x))=x` y sus dos hermanas, el valor en el origen, las sumas y diferencias, el ángulo doble en ambos sentidos y la conexión exponencial en objetivo aparte. Las seis derivadas y las seis integrales no viven aquí sino en T-17 y T-18, y **existen las doce**: lo que se leía como una ausencia era una referencia cruzada.

Dos identidades hiperbólcas **no** existen y el motor se niega a aplicarlas, con pruebas que lo fijan: `1+coth²(x)` y `sinh²(x)−1`. SeColaron en una primera versión y las rejectedó la comprobación numérica, no la lectura: `coth² = 1 + csch²` va en el otro sentido, y lo mismo con `cosh² = 1 + sinh²`.

**T-22** se sostiene así: cada reescritura registra su familia (`simplify_ex` la devuelve, y la calculadora la escribe en la traza), y las pruebas vuelven a comprobar cada identidad por un camino numérico independiente con puntos sembrados. Hay además un control negativo —`cos(x)` frente a `sin(x)` tiene que ser rechazado— porque sin él la comprobación pasaría igual si el verificador no comparase nada.

Dos cosas que conviene decir sin adornos:

- El inventario `identities()` se deriva de los registros de reglas, no se escribe a mano. Antes anunciaba `angulo_doble_coseno`, `angulo_doble_tangente` y `medio_angulo` sin que existiera regla alguna para ninguna de las tres; ahora una prueba falla si eso vuelve a pasar.
- `sec`, `csc` y `cot` no eran evaluables numéricamente, y el motor los produce. Una verificación que no puede evaluar lo que el motor emite no está comprobando nada, así que ahora son `1/cos`, `1/sin` y `1/tan`. El polo, eso sí, el camino numérico no lo ve: a `pi/2`, `cos` vale 6·10⁻¹⁷ y no cero, así que `sec(pi/2)` vuelve como un número enorme en lugar de como negativa. La negativa la da la tabla simbólica; el camino numérico solo puede dar la magnitud, y eso es lo que dice.

**T-11 (inversas y ramas)** tiene dos direcciones que no son simétricas, y esa asimetría es el contenido de la familia. `sin(arcsen(u)) = u` vale donde esté definida, así que el motor la reduce. `arcsen(sen x) = x` **no**, y el motor se niega a reescribirla: `ramas.ramas()` entrega cada rama con el intervalo donde sí vale, y `ramas.evidencia_global()` da un contraejemplo calculado —en `2·pi`, `arcsen(sen(2·pi))` vale 0 y no `2·pi`—. Los dominios de las inversas también son todos distintos: `[-1,1]` cerrado para `arcsen` y `arccos`, `(-1,1)` abierto para `arctanh` porque en los extremos no existe, y `[1,∞)` para `arccosh`. Por eso `dominio.Intervalo` lleva dos banderas de apertura.

**T-12 (ecuaciones)** resuelve `sen/cos/tan = c`, `a·sen+b·cos = c` por desplazamiento de fase, y polinomios en `sen`, `cos` o `tan` con raíces exactas. Cada familia se comprueba **sustituyendo miembros en la ecuación original**, que es lo único que caza una solución espuria y lo que exige T-12. Dos decisiones que hay que tener presentes: un valor irracional como `√2/2` da una solución **exacta** (`arcsen(√2/2)` es un número exacto aunque no sea múltiplo de `pi`), y cuando ningún caso encaja la respuesta es «no lo resuelve todavía», **nunca** «no hay soluciones». Esa distinción está fijada por pruebas, porque un solucionador que afirma que no hay soluciones sin haberlo demostrado es peor que uno que se niega.


**T-13 (inecuaciones)** convierte `f(x) > 0` en una carta de signos, y la carta solo vale si sus puntos críticos están todos. De ahí salen dos requisitos que no son opcionales. El primero: los **polos**, no solo los ceros. `tg(x) < 1` tiene dos intervalos, no uno, y solo el polo de `pi/2` parte el primero en dos; buscar solo los ceros devuelve un intervalo que contiene un punto donde la expresión no existe. Los polos de `tg` y `cotg` no tienen denominador en la expresión, así que se obtienen de los ceros de `cos` y `sen` en lugar de de una tabla inventada. El segundo: el **origen del periodo** es un punto como cualquier otro y se lee en la función. Dejarlo siempre abierto pierde una solución real — `cos(x)² > 1/2` se cumple en 0, y ahí es donde empieza la carta.

El signo dentro de cada hueco se decide **numéricamente**, y eso no es una aproximación del resultado sino una prueba: una función continua sin ceros ni polos dentro de un hueco no puede cambiar de signo en él. Si alguna vez cambiara, el motor **se niega** en lugar de elegir un lado, porque esa situación significa «me he dejado algo» y no «sé cuál mitad es». Y si los ceros no se pueden colocar en la rejilla de `pi` de forma exacta, la respuesta es «no lo sé»: `ceros()` devuelve `None`, que no es lo mismo que `[]`.

Dos cosas más quedaron fijadas por pruebas, y las dos son de la misma familia que el error que las causó. Una: `f^n = 0` está exactamente donde `f = 0` para **todo** `n` entero positivo; tratar la potencia par como un caso aparte hace que `sen(x)²` se quede sin ceros. Dos: el periodo que se informa es el **mínimo**, no un periodo válido. `dominio.periodo` daba 2`pi` para `sen(x)²`, cuyo periodo real es `pi`; no es un error en el conjunto —los puntos son los mismos— pero duplica cada intervalo y tapa la simetría que lo explica. `dominio.periodo_minimo` lo reduce a la mitad mientras siga cumpliéndose.

**T-20 (estrategia de resolución).** Faltaba el paso que hace resolubles las
ecuaciones con recíproca, y es uno solo: `N/D = 0` tiene los ceros de **N**, nunca
los de D, porque donde el denominador se anula hay un polo, y un polo no es
solución de nada. Con él, `sec(x) = 1`, `cosec(x) = 1` y `cotg(x) = 1` se
resuelven. La conversión recíproca → cociente va **antes** del bucle de reglas
y no dentro de él: una regla que agranda y otra que encoge no comparten punto fijo.

**Un agujero en la comprobación de espurias, encontrado al sellar T-24.** La
comprobación por sustitución —la única que caza una solución espuria y en la que se
apoya T-12— **nunca se ejecutaba**. Hacía `if not mx.variables(miembro): continue`,
y el miembro de una familia resuelta es justamente una constante, así que el
`continue` se saltaba el caso que hay que mirar: la función devolvía una lista
vacía para **toda** familia, incluidas las que no satisfacen la ecuación. Una
comprobación que no puede fallar no es una comprobación. Ahora sustituye de verdad, y
una familia con el paso equivocado se marca como espuria con su residuo.

**T-21 (fallback numérico declarado).** `verify.aproximacion()` devuelve el valor
**y lo que vale**: mide la sensibilidad de la expresión perturbando la entrada y
declara el error a partir de ahí, en vez de citar el tamaño del último dígito y
esperar. La diferencia se ve en un caso que el proyecto ya conocía: `sen(x)` en
`x = 1` sale con error 4·45·10⁻¹⁵, y en `x = 10⁶` sale con **2·08·10⁻⁴**.
La entrada y la salida son exactas y las dos se calculan en dobles; un error
declarado que allí se quedara en 10⁻¹⁵ sería peor que ninguno.

**T-24 (integración, sello y CI).** Las cuatro familias tienen ya operación en
`calculators.py` — `resolver`, `resolver_inequidad`, `ramas`, `aproximar` — y cada
resultado lleva su sello, trazados por un camino que no consulta el cálculo que
produjo la respuesta. Ecuaciones: se sustituye un miembro de cada familia en la
ecuación original. Inecuaciones: se muestrea el conjunto y se compara **en las dos
direcciones**. Ramas: el sello lleva el contraejemplo calculado, porque lo que
certifica las ramas es precisamente que la composición falla en algún sitio.
Aproximación: el sello es «solo numérico» con el error a la vista.

**T-23 (gráficas como hechos exactos).** `graficas.py` responde a la pregunta
del enunciado —periodo, amplitud, frecuencia, fase, ceros, extremos,
asíntotas, discontinuidades, comparación y aproximación— con hechos
comprobables, y la polilínea es un dato más, no la respuesta. La operación
`caracteristicas` lleva su propio camino de verificación: un muestreo denso de
la función contra cada hecho declarado, que es independiente de los solucionadores
que los produjeron. Cuando discrepan, el sello dice «discrepa» y la traza lo
registra.

Tres decisiones que hubo que tomar porque el enunciado no las dice:

- **La amplitud es la mitad del recorrido, no la mitad del máximo.** `3·sen(2x)`
  tiene amplitud 3 y un valor máximo de 3, así que dividir el máximo por dos da
  1.5 y sale mal en toda función no centrada en el cero. `sen(x) + 1` recorre de
  0 a 2 y su amplitud es 1.
- **Un senoide no necesita que se le estime la amplitud.** En la forma canónica
  `A·sen(Bx + C) + D` el coeficiente de la llamada *es* la amplitud: `5·sen(x + π/3)`
  vale 5, y muestrear el máximo devuelve 4.989, que es un hecho de la rejilla y no
  de la función. Solo se estima cuando no se reconoce la forma.
- **Una función sin máximo no tiene amplitud.** `1/tan(x)` no tiene una amplitud
  pequeña: no tiene ninguna, y un número ahí sería una altura muestreada que no
  significa nada.

**Lo que T-23 no hace, y por qué.** Solo se declaran asíntotas verticales: las
horizontales y oblicuas necesitan el límite en el infinito y no hay motor de
límites, y muestrear en un `x` grande no es un límite. `sen(x) + cos(x)` es un
senoide pero solo tras un desplazamiento de fase que habría que buscar, y se
declina en vez de contestarse a medias.

**Tres huecos que encontró el verificador de T-23 en módulos anteriores, y los
tres cerrados.** Ya no son huecos; quedan aquí porque el criterio con el que se
encontraron es el mismo que se usa para el resto.

- `periodo_minimo("sen(x)/x")` decía `2·π` y la función no es periódica. El
  periodo se pregunta ahora a la expresión **entra**: la periodicidad sobrevive a
  sumas, productos y cocientes, así que una parte no periódica —la `x` desnuda
  del denominador— zanja la respuesta, y `sen(x)/x`, `x + sen(x)`, `sen(x)·x`
  dan `None`.
- Los ceros de `5·sen(x + π/3)` daban `0`, que es donde se anula el seno sin
  desplazar. La causa era que `_afine` no veía la parte constante:
  `trig._factores` reparte productos y no sumas, así que `x + π/3` volvía como un
  factor único y todo desplazamiento salía «no afín».
- `sen(x)/x` declaraba `0` como cero, y `0/0` no es un cero sino un punto donde
  no está definido. Los ceros de un cociente son los de su numerador menos los
  puntos donde el denominador se anula.

**Una afirmación mía que era falsa.** T-23 decía que `1/tan(x)` es cotangente y
que por tanto `π/2` no es una discontinuidad suya. La cotangente lo es como
función, pero la **expresión** `1/tan(x)` no existe en `π/2`, porque `tan(π/2)`
no existe y el recíproco de nada es nada. El dominio del motor era correcto y la
afirmación era el error. Lo que falta no es la discontinuidad sino la nota de que
el hueco es **removible**, con límite 0.

**T-20 (los objetivos del motor, todos declarados).** `trig.OBJETIVOS` lleva los
doce en un solo registro, y hay dos clases que no son la misma cosa. Una
**reescritura** (`simplificar`, `expandir`, `producto_a_suma`, `suma_a_producto`,
`potencias`, `sustitucion_universal`, `hiperbolicas`, `exponencial`) dispara
reglas sobre subexpresiones y su respuesta es otra expresión, así que lleva un
registro de familias **no vacío**. Una **transformación** (`derivar`,
`integrar`, `complejos`, `fasores`) lleva una expresión a algo de otro tipo —una
derivada, una primitiva, un complejo, un fasor— y no tiene familias porque no
reescribe nada; lo que debe en su lugar es un `porque` escrito y un `verifica`
que nombre el segundo camino.

Los cuatro vivían en los módulos que los necesitan, así que el motor no podía
decir qué sabe hacer, y un objetivo que no se puede enumerar es uno que no se
puede prometer. Ahora cada uno declara su método y su módulo de procedencia,
`trig.inventario()` los expone, y la calculadora escribe el método declarado en
la trayectoria: una declaración que nadie lee es una declaración en un fichero.

**El hueco removible y el caso lineal, también cerrados.** `1/tan(x)` en `pi/2`
se decide por estructura —el recíproco se simplifica a `cotg`, cuyo dominio sí
incluye `pi/2`—, y un hueco que la simplificación no cancela se declara polo,
que es el lado seguro. Y `x = 0` se resuelve, que era lo más elemental que
faltaba; arreglarlo destapó que `0·pi` y `0` eran dos puntos distintos para el
motor, que la regla de fusión de intervalos estaba al revés y que un extremo
infinito no ganaba nunca en una fusión.

**COMPLETADAS:** T-01 a T-24, sin excepciones. **T-19 quedó COMPLETADA el 2026-10-05**,
que era la única que seguía PARCIAL y no por huecos del método sino por un límite
declarado: la cota de error cuando no hay cota sobre la derivada omitida. Al cerrarlo
resultó que la regla anterior —«el primer término omitido es la cota» para `sin`, `cos`
y `ln`, y ninguna cota para las otras cuatro— no era ni muy cierta ni muy honesta: dos
de esas tres cotas no acotaban en el semiplano negativo, y `ln` fallaba por un factor de
cinco en `x = -0,9`. Ahora las siete llevan cota mayorizada sobre su propia cola, cada
una con su dominio declarado, y la que no se puede derivar se niega diciéndolo.
Está vigilada por una alarma que falla el día que algo de esto se rompa, y la alarma
mide contra el error real en vez de comprobar que un número existe.

**T-18 quedó COMPLETADA el 2026-10-04**, cerrando sus tres límites declarados en un
solo día. Ninguno de los tres era una función que faltara, y esa es la parte que
conviene recordar: el discriminante negativo era un **nombre** que la tabla de
derivadas ya tenía desde T-17 y que la gramática no aceptaba; la cuadrática
irreducible al cuadrado era una cuadrática escrita dos veces que nadie miró a ver
si lo era; y el cuartico sin raíz racional era un biquadrático, que se parte sin
aritmética de cuerpos porque solo un coeficiente de la respuesta necesita un
radical. La etiqueta decía «T-18 cerrada entera» y era un exceso de confianza, no
un dato —tres días antes seguía siendo parcial de verdad, por tres motivos
distintos que la documentación mezclaba en uno solo.

**T-14, T-18 y T-19 cerradas**, cada una con lo que le quedaba.
`∫sen^n`, `∫cos^n` y `∫tg^n` por la fórmula de reducción, `∫ln^n` por partes
tabulares, y las primitivas propias de la familia —`cot`, `sec^2`, `cosec^2`, `cot^2`,
`coth`, `sech^2`, `sech`, `csch`— en tabla. El polinomio de Taylor de un monomio ya
coincide con el monomio, y las siete series conocidas llevan cota de error con su
dominio declarado.

**T-18: los tres huecos que quedaban están resueltos, y los tres
eran el mismo fallo de lectura: una regla que miraba una cosa y no la otra.

- **El producto de dos potencias.** `sen(x)^3·cos(x)^2` no entraba porque la
  reducción es de UNA potencia y el cambio de variable no ve el resto. Los tres
  casos clásicos lo convierten en una SUMA de potencias simples, que es lo único
  que ya había: exponente impar en `sen`, exponente impar en `cos`, y los dos
  pares con `sen^(2a)·cos^(2b) = 4^... ·(1-cos(2g))^a(1+cos(2g))^b`. Ningún término
  nuevo: o es `sen·cos^p` —que el cambio de variable siempre hizo— o es
  `cos(2g)^k`, que es la reducción con factor de cadena. Solo faltaba leer el
  integrando para encontrar las que ya existían.
- **`∫sec^n`, `∫cosec^n`, `∫cot^n` para n ≥ 3.** `f^n = f^(n-2)·f^2` y el
  cuadrado ya estaba en la tabla. Ojo con la cotangente: NO tiene la misma forma
  que las otras dos, y fingir que sí es lo que hacía que `∫sec^3` saliera
  `sec·tg - ln|sec+tg|` —piezas correctas, coeficientes equivocados—, que es peor
  que no responder porque parece terminado.
- **`e^x·sen(x)`, `e^x·cos(x)`, `senh(x)^2`, `cosh(x)^2`.** Entradas de tabla. La
  primera tiene forma cerrada y ningún cambio de variable la encuentra: `u = sen(x)`
  no aplica y las partes por dos veces vuelven a la integral de la que salieron.
  `senh^2` y `cosh^2` se diferencian en el SIGNO del término lineal, y comprobarlo
  derivando es lo que las distingue; leerlas no.

Dos errores de los encontrados al verificar, que ya no se ven porque están
arreglados:

- El denominador del caso par-par era `4^(a+b)` en vez de `2^(a+b)`, de modo que
  `∫sen^2·cos^2` salía cuatro veces pequeña. Correcta en la forma y con la
  constante equivocada.
- Al caso con exponente impar en `cos` le faltaba el `(-1)^j` del binomio, que es
  todo lo que separa las dos ramas: `∫sen^2·cos^3` daba una derivada
  `sen^2·cos(1 + sen^2)`, una expresión real y la primitiva equivocada.

**Un límite que no es un hueco.** `sen(x)^6·cos(x)^6` se integra bien —234
caracteres, dentro del presupuesto— y su derivada no cabe en los 480. O sea: el
motor devuelve una respuesta correcta que no puede comprobar. La prueba lo dice y
lo comprueba por diferencias finitas, porque ahí ya no queda la verificación
simbólica. Es justo lo que el presupuesto existe para hacer visible en vez de
esconder.

**Auditoría.** Un barrido del motor entero buscando respuestas FALSAS, no
capacidades faltantes, vive en `tests/test_mathlab_auditoria.py`: **485**
comprobaciones, cada una por un camino que no consulta el cálculo que la produjo.
La primera tanda encontró dos bugs que ninguna otra prueba veía:

- `x^(3/2)` volvía del otro árbol de expresiones como `√x`. El numerador del
  exponente se perdía, y la primitiva de `√x` salía `2·√x/3`, cuya derivada
  es `1/(3·√x)`. El primer arreglo puso el numerador encima de la raíz y dio
  `x^3·√x`, que es `x^(7/2)` y sale 35 veces demasiado grande. Las dos versiones
  **se imprimen como una potencia fraccionaria** y solo derivar lo delata.
- El bucle de Taylor leía el término de orden k con la derivada de orden k+1
  mientras el coeficiente salía como recíproco. Dos fallos que se cancelan, que es
  la razón por la que todo valor intermedio parecía plausible.

**Segunda tanda de la auditoría: T-13, T-11, T-15 y T-16.** Un barrido por las
familias que la anterior no cubría encontró **seis bugs de respuesta falsa** y un
bucle infinito. Ninguno era una capacidad que faltara: todos contestaban mal.

- **T-13, el más grave: `sen(x) >= 1` publicaba `∅`.** La carta recorre *huecos* y
  se queda con los que cumplen; una solución sin interior —el máximo es tangente,
  no un cambio de signo— no tiene ninguno que quedarse. Se cumple en `pi/2` y en
  `3pi/2`. Lo escondía el caso vecino: `sen(x) <= 1` salía bien, porque en él
  cumplen todos los huecos y no hay nada que buscar. También `sen(x) <= -1`,
  `cos(x) >= 1` y `cos(x) <= -1`.
- **T-13: `<=` y `<` publicaban el mismo conjunto** en `tg`, con `pi` dentro de
  `< 0`. El extremo del periodo se comparaba sin doblar contra un conjunto de ceros
  ya doblado, así que no se reconocía como cero y lo decidía el valor numérico:
  `tg(pi) = -1e-16` pasa cualquier `< 0`.
- **T-13: `0·pi` y `periodo·pi` se contestaban distinto** siendo el mismo punto, en
  las doce combinaciones de operador sobre seno, coseno y tangente. La respuesta
  declara que se repite cada `P·pi`; no puede separarlos.
- **T-11: las dos ramas de `acosh(cosh)` estaban cambiadas de sitio.** Publicaba `x`
  en `(-inf, 0]` y `-x` en `[0, inf)`; `acosh(cosh(x)) = |x|` dice lo contrario. Y
  la **nota** de cada fila describía el lado correcto, así que el motor se contradecía
  a sí mismo y las dos frases decían la misma cosa falsa.
- **T-15: `arg` mal en el segundo cuadrante.** Con parte real negativa hay dos
  cuadrantes y se doblan en direcciones opuestas: `arg(-3+4i)` salía en -4.069 en
  vez de +2.214, fuera del rango `(-pi, pi]` que el propio módulo declara.
- **T-15: `principal=False` no era una vuelta más**, que es lo que su nombre
  prometía: devolvía el `atan(y/x)` sin doblar, que con parte real negativa no es un
  argumento del número —el coseno sale con el signo equivocado—.
- **Un bucle infinito, preexistente.** `periodo_minimo` partía el candidato por la
  mitad con la condición `candidato / 2 > 0`, y un `Fraction` positivo partido por
  dos nunca llega a cero. `sen(x)^2 + cos(x)^2 - 1/2` es la constante 1/2 escrita
  más larga, repite tras cualquier desplazamiento, y **`sen(x)^2 + cos(x)^2 > 1/2`
  colgaba el motor** hasta que lo mataban. Ahora se niega con el motivo que ya daba
  `1 > 1/2`: no hay periodo mínimo, y un periodo sin mínimo no lo usa una carta.

Lo que salió limpio, y conviene decirlo porque es la mitad del resultado: T-16
entero, las otras cinco familias de ramas de T-11, y el periodo, la frecuencia, la
amplitud —la mitad del recorrido, medida en la prueba y no por el motor— y los
ceros de T-23, comprobados anulando la función.

Dos comprobaciones de la propia auditoría resultaron **ingenuas** y se corrigieron,
no el motor: un polo visto por punto flotante es un número grande, así que la
comprobación de inecuaciones tiene que contarlo como polo o marca como error una
respuesta correcta; y `test_argumento_no_principal_gana_una_vuelta_entera` afirmaba
que las dos vías dan lo mismo, sobre `3+4i` —primer cuadrante, donde la opción no
cambia nada—, así que pasaba con una implementación que ignorara la opción.

**Tercera tanda: dos escrituras de la misma pregunta, y dos respuestas.** El motor
tenía la respuesta y se negaba a darla. `sec(x)^2 > 4` se rechazaba mientras
`1/cos(x)^2 > 4` se resolvía; `sec(x) = 2` se resolvía y `sec(x)^2 = 4` no. Es la
misma enfermedad que T-14 cerró para las integrales, en los dos solucionadores que
esa tanda no tocó:

- **La potencia del recíproco iba fuera del cociente.** `(1/cos(u))^n` es el mismo
  número en una forma que nada de lo que viene después reconoce; `1/cos(u)^n` es
  como lo escribe el estudiante. Solo para entero positivo, que es donde la
  identidad es exacta. `cot(u)^n` tenía además su propia forma, el cociente
  `cos/sin`, y por eso `cot(x)^2 > 1` se rechazaba. **6 de 8 parejas** coinciden
  ahora; eran 2 de 8.
- **Dos ceros falsos**: `tg(x)·cos(x)` publicaba `pi/2` y `3pi/2`, y `tg` no existe
  ahí. El producto es cero donde lo sea un factor, pero solo donde el producto
  **existe** —y el filtro que tenía la rama del cociente faltaba en la del
  producto.
- **Un cero que faltaba, el mismo defecto por el otro lado.** `tg(x)·cos(x)` es
  `sen(x)`, de periodo `2·pi`, y `tg` se dobla en `pi` declarando un cero, así que
  `pi` no se generaba nunca. Cada factor aporta ahora sus ceros hasta el periodo
  del producto, con vueltas enteras de su propio periodo.
- **Un «no hay soluciones» falso**: `cot(x)^3 > 4` publicaba `∅` sobre una
  expresión llena de soluciones. Sus ceros necesitan `tg(x) = 4^(-1/3)`, que no
  es múltiplo racional de `pi`, y el solucionador devolvía una lista de familias
  vacía **sin registrar el rechazo**. La prueba independiente es el teorema del
  valor intermedio: una función continua sin polo ni cero no cambia de signo, y
  un cambio demuestra que el cero existe. `cos(x)^3 > 1` pasa la misma prueba, y
  ahí `∅` es la verdad.
- **El dominio se comía un `0/0`**: `1/sen(x)` declaraba existir en `pi` y en
  `2pi`, donde vale `1/0`. `0` y el final del periodo son el mismo punto, la regla
  que la carta de signos ya seguía. Tres expectativas de prueba clavaban el
  comportamiento equivocado, derivadas de la salida y no de lo que las
  expresiones son; corregidas con el razonamiento escrito.

13 expresiones de producto y cociente contrastadas punto a punto contra la
función: **0 discrepancias**, antes 2 ceros falsos y 1 que faltaba.

**Tercera tanda, segunda parte: el reciproco con potencia impar.** `sec(x)^3 > 8`
se negaba con el motivo correcto —su cero necesita `cos = 1/2`, exacto— mientras
`sec(x)^2 > 4` se resolvía, y la única diferencia era el grado. El teorema de la
raíz racional dice «divisor del constante **sobre** divisor del coeficiente
**principal**» y aquí se usaba solo el primero: para `-16·u^4 + 1` eso da ±1 y la
raíz es 1/2. Con el numerador del principal en el juego, `1/cos(u)^n = c` resuelve
para toda potencia entera.

**Y un no-hecho, probado y revertido, escrito para que no se intente otra vez.**
`sen(u)/tg(u)` es `cos(u)` y `cos(u)/sec(u)` es `cos(u)^2`, y reducirlos parece
obvio. El motivo para no hacerlo está en el **periodo**: `cos²` tiene periodo `pi`
y `cos/sec` tiene `2·pi`, porque `sec` no existe donde `cos` se anula. Reescribir
borra el dominio *y* el periodo, y el conjunto publicado pasa a ser el de otra
función —medido: `cos(x)/sec(x) > 1/2` quedaba mal en 193 de 383 puntos—. El
sitio correcto es la reescritura de identidades. Queda escrito en el código, con
el número.

18 inecuaciones del recíproco contrastadas punto a punto, 384 muestras cada una y
los polos saltados y declarados: **0 respuestas incorrectas**.

**COMPLETADAS:** T-01 a T-24.

**NOTA sobre T-13.** La especificación la marca COMPLETADA y su lista no pide
dominio multivariable —`dominio()` toma la variable como parámetro y sirve para
cualquiera—. Las fracciones racionales **multivariable** son ML-12, otra fase, y
no un hueco de esta.

**PENDIENTES:** ninguna de la especificación; lo que queda es lo que cada línea dice.

## Catálogo maestro de cobertura

La cobertura de este laboratorio se audita también en `docs/labs/COVERAGE_CATALOG.md`. Ese catálogo fija el contrato común de familia temática, estados y criterio de completitud; documentar una capacidad no implica que esté implementada.
