# AcademicCore — Roadmap Maestro Completo, Arquitectura y Evolución Futura

> **Proyecto**: AcademicCore  
> **Documento**: Roadmap Maestro y Visión Funcional  
> **Estado**: En Desarrollo Activo (Fases F0 a F8-P5 **CERTIFICADAS**)
> **Objetivo**: Plataforma académica técnica con conocimiento estructurado, evaluación, aprendizaje adaptativo, ingeniería/simulación e IA asistiva gobernada por guardrails deterministas.

---

## 1. Visión General

AcademicCore es una plataforma de aprendizaje técnico e ingeniería que combina en un único sistema unificado:

- **Gestión de asignaturas**: carreras, cursos, temas, sesiones y planificación académica.
- **Teoría y documentación**: procesamiento estructurado de apuntes, libros y especificaciones técnicas.
- **Fórmulas y conceptos**: extracción canónica, grafo de dependencias y relaciones de prerrequisitos.
- **Ejercicios y exámenes**: bancos de problemas estructurados, generación determinista y calificación rigurosa.
- **Corrección y seguimiento del dominio**: corrección exacta y probabilística, modelado de maestría (*mastery*).
- **Aprendizaje adaptativo**: rutas personalizadas de estudio según lagunas conceptuales y curvas de olvido.
- **Matemáticas de alta precisión**: álgebra exacta (`fractions.Fraction`), números complejos y aritmética `Decimal` arbitraria.
- **Análisis y simulación de circuitos**: motor MNA lineal y no lineal (DC, AC fasorial, modelos de pequeña señal, diodos y transistores).
- **Laboratorio virtual y metrología**: estimación de incertidumbre (GUM), propagación y calibración de instrumentos.
- **IA / Tutor asistivo**: asistencia explicativa y socrática desacoplada de la autoridad matemática y física.
- **Sincronización y persistencia**: arquitectura local-first con respaldo en la nube y trazabilidad de procedencia (*provenance*).
- **Interfaz de usuario**: aplicación de escritorio nativa, responsiva y ergonómica.

> [!IMPORTANT]
> **Principio de Soberanía Determinista**:  
> La aplicación debe poder funcionar en su totalidad sin depender obligatoriamente de un LLM. La IA es una capa superior de asistencia explicativa y pedagógica, **nunca la autoridad matemática o física del sistema**.

---

## 2. Principios Fundamentales del Producto

### 2.1 Exactitud
Cuando existe una respuesta matemática, física o numérica verificable, debe obtenerse mediante lógica algorítmica determinista, nunca mediante inferencia estadística de modelos de lenguaje.

### 2.2 Trazabilidad de Extremo a Extremo
Toda respuesta, calificación o resultado de simulación debe rastrearse mediante una cadena ininterrumpida de evidencias:
$$
\text{Fuente} \longrightarrow \text{Documento} \longrightarrow \text{Sección} \longrightarrow \text{Concepto / Fórmula} \longrightarrow \text{Ejercicio} \longrightarrow \text{Respuesta}
$$

### 2.3 Determinismo Estricto
$$
\text{Mismo input} + \text{Misma configuración} + \text{Misma versión} \Longrightarrow \text{Mismo resultado idéntico}
$$
Cero variabilidad no controlada, generadores pseudoaleatorios con semillas auditables y digests SHA-256 de topología y estado del solver.

### 2.4 IA Sustituible y Desacoplada
El sistema soporta indistintamente múltiples proveedores de IA (*Extractive*, *Ollama local*, *Google Gemini*, proveedores futuros) mediante interfaces de puertos y adaptadores sin alterar una sola línea del núcleo académico o físico.

### 2.5 Seguridad Permanente
Queda terminantemente prohibido que contenido académico, prompts de usuario o parámetros de simulación puedan traducirse en ejecución arbitraria de código (`eval`, `exec`, `compile`, `subprocess`, `os.system`, `shell=True`, deserializaciones inseguras).

### 2.6 Modularidad Extensible
La arquitectura permite incorporar nuevas disciplinas (Matemáticas, Electrónica, Física, Metrología, Programación, Automática, Control, Telecomunicaciones) sin necesidad de rediseñar ni reconstruir el núcleo.

---

## 3. Arquitectura Conceptual del Sistema

```
                         ┌─────────────────────────┐
                         │           UI            │
                         │    AcademicCore App     │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │    Application Layer    │
                         └────────────┬────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
  Academic Engine             Engineering Engine               AI Engine
         │                            │                            │
         ▼                            ▼                            ▼
  Knowledge Base                 Mathematics                   Providers
  Assessment                     MNA (DC & AC)                 Ollama (Local)
  Mastery                        Nonlinear (D & Q)             Gemini (Cloud)
  Adaptive Learning              Transient (Future)            Socratic Tutor
  Exams                          Virtual Lab / Metrology       Guardrails
         │                            │                            │
         └────────────────────────────┼────────────────────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │       Persistence       │
                         │      Local / Cloud      │
                         └─────────────────────────┘
```

---

## 4. Capas del Sistema

- **Knowledge Core**: Documentos, fuentes, secciones, fragmentos (*chunks*), conceptos, fórmulas, relaciones ontológicas, evidencias, metadatos y cadena de *provenance*.
- **Academic Core**: Carreras, asignaturas, temas, ejercicios, preguntas, exámenes, intentos, rúbricas, corrección algorítmica, estudiantes, estados de *mastery* y métricas de progreso.
- **Engineering Core**: Unidades SI y magnitudes físicas dimensionales, matrices de alta precisión, representación canónica de circuitos, MNA lineal (DC y AC), MNA no lineal con amortiguamiento Newton-Raphson, modelos de semiconductores, teoremas de red y comprobaciones de conservación (KCL, KVL, Tellegen).
- **Adaptive Engine**: Historial de intentos, vector de dominio, priorización de refuerzo, ajuste dinámico de dificultad, repetición espaciada (*spaced repetition*) y generación de itinerarios de aprendizaje.
- **AI Engine**: Abstracción de proveedores LLM, contexto estructurado, plantillas de prompting, guardrails de validación determinista, asistencia socrática y generación asistida de variantes.
- **Application / UI**: Paneles de control (*dashboard*), visor de cursos y documentos, editor de apuntes, resolución guiada de ejercicios, simulador de circuitos, laboratorio virtual y monitor de rendimiento.

---

## 5. Roadmap Global y Estado de Certificación

```
 F0  Auditoría y Arquitectura                  [CERTIFICADO]
  │
 F1  Núcleo de Dominio                         [CERTIFICADO]
  │
 F2  Recursos y Almacenamiento CAS             [CERTIFICADO]
  │
 F3  Documentos / PDF / AST                    [CERTIFICADO]
  │
 F4  Knowledge / Modelo Académico              [CERTIFICADO]
  │
 F5  Authoring Engine                          [CERTIFICADO]
  │
 F6  Matemáticas e Ingeniería Base             [CERTIFICADO]
  │
 F7  MNA Lineal y Simulación SPICE             [CERTIFICADO]
  │
 F8  Electrónica Avanzada (F8-A ... F8-M)      [CERTIFICADO]
  │
 F9  Assessment y Evaluación Formal            [EN PLANIFICACIÓN]
  │
 F10 Mastery y Modelado del Estudiante         [EN PLANIFICACIÓN]
  │
 F11 Aprendizaje Adaptativo                    [EN PLANIFICACIÓN]
  │
 F12 IA / Tutor Socrático con Guardrails       [EN PLANIFICACIÓN]
  │
 F13 OneDrive / Cloud Sync                     [EN PLANIFICACIÓN]
  │
 F14 Migración de Sistemes-de-Mesura           [EN PLANIFICACIÓN]
  │
 F15 Aplicación Final Integral                 [EN PLANIFICACIÓN]
```

### 5.1 Orden de implementación vigente (a partir de F8-J)

> Fuente: `ROADMAP_orden_implementacion.md` (2026-09-19). Este orden es
> estricto y único: sin fases en paralelo salvo decisión explícita.
> Nota de estado local (verificado en repo): F8-J está implementado
> (`GATE-F8J.md` CERTIFIED) y existe dominio F9/assessment (`GATE-F9A.md`,
> tests `test_f9*`); el orden de lo pendiente sigue siendo el de abajo.

```
F0   Auditoría y Arquitectura                          [CERTIFICADO]
F1   Núcleo de Dominio                                 [CERTIFICADO]
F2   Recursos y Almacenamiento CAS                      [CERTIFICADO]
F3   Documentos / PDF / AST                             [CERTIFICADO]
F4   Knowledge / Modelo Académico                       [CERTIFICADO]
F5   Authoring Engine                                   [CERTIFICADO]
F6   Matemáticas e Ingeniería Base                      [CERTIFICADO]
F7   MNA Lineal y Simulación SPICE                      [CERTIFICADO]
F8-A a F8-I   Electrónica Avanzada                      [CERTIFICADO]
 │
 │  ═══════════ A PARTIR DE AQUÍ: NUEVO ORDEN ═══════════
 │
F8-J   Small-Signal AC                                  [1º]
F8-K   Semiconductores Adicionales (MOSFET/JFET/Zener)  [2º]
F8-L   Transitorio (DAE, Backward Euler, Trapezoidal)   [3º]
F8-M   Análisis Avanzados (Sweep, Sensibilidad, MC)     [4º] CERTIFICADO
F8-N   Laboratorio Virtual                              [5º] CERTIFICADO
F8-O   Metrología e Incertidumbre (GUM)                 [6º] CERTIFICADO
F8-P1  Sistemas y Control                               [7º] CERTIFICADO
F8-P2  DSP                                              [8º] CERTIFICADO
F8-P3  RF y Líneas de Transmisión                       [9º] CERTIFICADO
F8-P4  Comunicaciones Digitales                         [10º] CERTIFICADO
F8-P5  Síntesis Satcom                                  [11º] CERTIFICADO
 │
 │  ═══════════ CIERRE DE F8. EMPIEZA CONSTRUCCIÓN DE APP ═══════════
 │
[D1]   Decisión: Arquitectura de módulos/plugins        [12º]
[D2]   Decisión: Estándar de logging/errores            [13º]
[D3]   Decisión: Licencia única del proyecto             [14º]
F15    Aplicación Final (app mínima funcional)          [15º]
F3-ext Integración conversor HTML→MD/LaTeX              [16º]
F4-ext Fusión gestión académica                         [17º]
F13-ext Sync entre 2 PCs personales                     [18º]
 │
 │  ═══════════ APP FUNCIONAL. CONSTRUCCIÓN SOBRE ELLA ═══════════
 │
[D4]   Pipeline CI/build (GitHub Actions)               [19º]
[D5]   Suite de tests                                   [20º]
[D6]   Esquema neutro de banco de preguntas             [21º]
[D7]   Ingesta estructurada al Knowledge Core (F4)      [22º]
F9     Assessment y Evaluación Formal                   [23º]
F10    Mastery y Modelado del Estudiante                [24º]
F11    Aprendizaje Adaptativo                           [25º]
F12    IA / Tutor Socrático con Guardrails               [26º]
F13    OneDrive / Cloud Sync (completo)                 [27º]
F14    Migración de Sistemes-de-Mesura                  [28º]
F16    Contenido Aeroespacial/Satélite (última fase)    [29º]
F8-Q  Motor Digital + Logic Analyzer                 [CERTIFICADA]
E0     Explainable Execution / Pedagogical Trace        [CERTIFICADA]
E0.1   Explainable Execution Expansion (pasos reales)  [CERTIFICADA]
E0.1-R+ Hardening + cierre de limitaciones           [CERTIFICADA]
E0.2   Explainable Engineering Expansion (analógico)  [CERTIFICADA]
 │
 │  ═══════════ CAPACIDAD PEDAGÓGICA TRANSVERSAL ═══════════
 │
> **E0 es obligatoria para todo resolver nuevo y para la migración progresiva de los resolvers existentes.**
> No es una feature exclusiva de UI ni una explicación generada retrospectivamente por IA: la explicación debe proceder de una traza estructurada de la ejecución determinista.

```

| # | Código | Nombre | Depende de | Nota |
|---|---|---|---|---|
| 1 | F8-J | Small-Signal AC | F8-H, F8-I | Linealización de diodo/BJT para pequeña señal |
| 2 | F8-K | Semiconductores Adicionales | F8-J | MOSFET Level 1, JFET, Zener, LED, Schottky, fotodiodo |
| 3 | F8-L | Transitorio | F8-K | DAE, Backward Euler, Trapezoidal, BDF, paso adaptativo |
| 4 | F8-M | Análisis Avanzados | F8-L | DC Sweep, Parameter Sweep, sensibilidad, Monte Carlo, Worst Case |
| 5 | F8-N | Laboratorio Virtual | F8-M | Fuente DC, multímetro, osciloscopio, generador, analizador lógico |
| 6 | F8-O | Metrología e Incertidumbre (GUM) | F8-N, F6 | Capa de metrología sobre GUM local F7-B7 (sin `eval`); propagación analítica + MC, cifras significativas, trazabilidad — **CERTIFICADO** |
| 7 | F8-P1 | Sistemas y Control | F8-D6 (Bode ya certificado) | Función de transferencia, Bode, lugar de raíces, PID, espacio de estados — **CERTIFICADO** |
| 8 | F8-P2 | DSP | F8-P1 | FFT/DFT, transformada Z, FIR/IIR, muestreo, aliasing — **CERTIFICADO** |
| 9 | F8-P3 | RF y Líneas de Transmisión | F8-D1/D2, F8-P2 | Carta de Smith, parámetros S, líneas de transmisión, matching — **CERTIFICADO** (antenas/link budget diferidos a F8-P5, roadmap:212) |
| 10 | F8-P4 | Comunicaciones Digitales | F8-P2, F8-P3 | Modulaciones, constelaciones, BER/SNR, Shannon — **CERTIFICADO** |
| 11 | F8-P5 | Síntesis Satcom | F8-P1..P4 | Módulo integrador: link budget + modulación + ruido + antenas — **CERTIFICADO** |
| 12 | D1 | Arquitectura de módulos/plugins | — | Manifiesto común antes de fusionar `GestionAcademicaGREELEC.exe`, el conversor y AcademicCore |
| 13 | D2 | Estándar de logging/errores | — | Sustituye el patrón `except Exception: pass` del conversor |
| 14 | D3 | Licencia única | — | El conversor ya usa MIT; fijar antes de fusionar más repos |
| 15 | F15 | Aplicación Final | D1, D2, D3, toda F8 | Qt/PySide6, dashboard, resolución de ejercicios, simulación |
| 15a | F8-Q | Motor Digital + Logic Analyzer | F15, F8-N | Motor digital event-driven (LOW/HIGH, tiempo Decimal, zero-delay), gates N-arias, stimuli, probes, `DigitalTrace`, serialización/replay `digital-trace/1`, Logic Analyzer (trigger RISING/FALLING/BOTH, pre/post-trigger) e integración F15 (pestaña Logic Analyzer + renderer de formas de onda) — **CERTIFICADA** (Q.1–Q.7, [`GATE-F8Q-FINAL.md`](../gates/GATE-F8Q-FINAL.md)) |
| 15b | E0 | Explainable Execution / Pedagogical Trace | F8-Q.7 (F8-Q certificada) | `ExecutionTrace` común (`execution-trace/1`, digest, replay, renderer de 7 preguntas) integrado con el resolver de ecuaciones y con F8-Q; botón «Explicar» en Ejercicios — **CERTIFICADA** ([`GATE-E0-FINAL.md`](../gates/GATE-E0-FINAL.md)); retrofit de otros resolvers (E0-A…E0-D) pendiente |
| 15c | E0.1 | Explainable Execution Expansion | E0 | Motor simbólico acotado con pasos reales (derivadas, integrales, ecuaciones lineales, simplificación), iteraciones reales de F8-N (Newton) y F8-P (bisección), presupuesto GUM paso a paso, causalidad F8-Q, `digital-circuit/1`, lecciones «Paso N / Tipo / Regla / …» en Ejercicios y Logic Analyzer — **CERTIFICADA** ([`GATE-E0.1-FINAL.md`](../gates/GATE-E0.1-FINAL.md)) |
| 15d | E0.1-R+ | Hardening + limitaciones justificadas | E0.1 | Equivalencia observer/no-observer (GUM, F8-N, F8-P), etiquetas SYMBOLIC/NUMERIC/NONE, causalidad F8-Q delta a delta sin tocar el paquete digital, GUM declarativo (callables UNSUPPORTED), auditoría Decimal de √/ν_eff (se conserva el motor certificado), límites F8-N configurables — **CERTIFICADA** ([`GATE-E0.1-R-FINAL.md`](../gates/GATE-E0.1-R-FINAL.md)) |
| 15e | E0.2 | Explainable Engineering Expansion (analógico) | E0.1-R+ | F8-H con Shockley real, Newton, Jacobiano, backtracking y KCL por nodo observados; MNA lineal con A, b y x exactos; barrido DC, AC, transitorio y TF a nivel de resultado con lo no observable declarado; «Explicar último» en el Laboratorio Virtual — **CERTIFICADA** ([`GATE-E0.2-FINAL.md`](../gates/GATE-E0.2-FINAL.md)) |
| 16 | F3-ext | Integración del conversor HTML→MD/LaTeX | F15 | Motor de `Conversor-HTML-A-MD` (ya desacoplado de Tkinter) |
| 17 | F4-ext | Fusión de gestión académica | F15, F3-ext | Migra `GestionAcademicaGREELEC.exe` al modelo F4 y al dashboard |
| 18 | F13-ext | Sync entre 2 PCs personales | F15 | Última edición gana + log (no CRDT) |
| 19 | D4 | Pipeline de CI/build | F15 | GitHub Actions, tests en cada commit |
| 20 | D5 | Suite de tests | D4 | Empieza por el motor de conversión HTML→MD |
| 21 | D6 | Esquema neutro de banco de preguntas | — | Generaliza `BANC`/`DATA.items`/`ITEMS` a JSON neutro por asignatura |
| 22 | D7 | Ingesta estructurada al Knowledge Core | D6, F4 | Definiciones/fórmulas/preguntas como entidades F4, no `.md` sueltos |
| 23 | F9 | Assessment y Evaluación Formal | D6, D7 | Tipos de pregunta, pipeline de corrección |
| 24 | F10 | Mastery y Modelado del Estudiante | F9 | Modelo bayesiano de dominio |
| 25 | F11 | Aprendizaje Adaptativo | F10 | Rutas personalizadas, `LLM = OFF` garantizado |
| 26 | F12 | IA / Tutor Socrático con Guardrails | F11 | LLM → JSON estructurado → Validador → Solver determinista |
| 27 | F13 | OneDrive / Cloud Sync (completo) | F13-ext | Versión completa más allá del sync entre 2 PCs |
| 28 | F14 | Migración de Sistemes-de-Mesura | F4-ext | Ingesta del repo `Damaga2005/Sistemes-de-Mesura` |
| 29 | F16 | Contenido Aeroespacial/Satélite | F8-P5 | Mecánica orbital básica; última fase, sin prisa |

**Regla de oro:** no empezar una fase con dependencias sin marcar como hecha. Orden estricto, sin paralelo salvo decisión explícita.

---

## 5.2 E0 — Explainable Execution / Pedagogical Trace

**Estado:** PLANIFICADA / TRANSVERSAL  
**Implementación:** después de completar y certificar F8-Q.7  
**Propósito:** convertir la ejecución real de los resolvers en una solución académica completamente trazable, reproducible y visualizable paso a paso.

### Objetivo obligatorio

AcademicCore no debe limitarse a producir:

entrada → resultado

cuando existe un procedimiento determinista que puede explicarse. Debe poder producir:

datos → procedimiento → pasos → transformaciones → estados intermedios → comprobaciones → resultado.

La explicación debe derivarse de la ejecución real del motor. **No se permite que una IA invente retrospectivamente una explicación que no esté respaldada por la traza del solver.**

### ExecutionTrace común

E0 deberá definir un contrato transversal para una traza estructurada que pueda representar, como mínimo:

- datos iniciales y condiciones;
- hipótesis y convenciones;
- pasos ordenados y deterministas;
- operaciones y transformaciones;
- fórmulas y sustituciones;
- valores intermedios y unidades;
- justificación académica del paso;
- estados estructurales intermedios;
- advertencias y condiciones de validez;
- verificaciones;
- resultado final.

La traza deberá ser **determinista, serializable, validable y reproducible**.

### Circuitos

Los resolvers de circuitos deberán poder representar el estado del circuito durante la solución. Si se simplifica una red, se sustituyen componentes, se elimina una rama o se crea un equivalente, deberá poder mostrarse:

1. circuito original;
2. operación/transformación aplicada;
3. circuito resultante;
4. cálculo asociado;
5. siguiente transformación.

El usuario deberá poder seguir visualmente la evolución del circuito como en una corrección de examen.

### Tablas de verdad y lógica

Las soluciones deberán poder mostrar entradas, señales intermedias, operaciones y salidas. No se limitarán a la tabla final si existen expresiones intermedias relevantes.

Las simplificaciones booleanas deberán poder mostrar las transformaciones y la ley/identidad aplicada en cada paso.

### Matemáticas e ingeniería

Los resolvers deberán poder exponer fórmulas, sustituciones, conversiones de unidades, resultados intermedios, redondeos y comprobaciones finales cuando sean académicamente relevantes.

En simulación deberán poder exponerse las condiciones iniciales, parámetros, eventos/estados relevantes y verificaciones sin confundir la traza pedagógica con la traza técnica interna del solver.

### Corrección de ejercicios

E0 deberá preparar el modo de corrección paso a paso. La corrección deberá poder distinguir, cuando el dominio lo permita, entre:

- paso correcto;
- paso incorrecto;
- paso incompleto;
- error algebraico;
- error de unidades;
- error conceptual;
- resultado correcto obtenido mediante procedimiento incorrecto;
- resultado final incorrecto.

Deberá poder localizarse el primer error verificable y explicar la corrección correspondiente.

### Arquitectura

La separación obligatoria será:

Domain/Application → ExecutionTrace → Renderer

La traza no dependerá de Qt ni de la UI. Los renderers podrán producir texto, fórmulas, tablas, diagramas de circuitos y gráficos.

### Determinismo y replay

Mismo input + misma configuración + misma versión deberá producir una traza equivalente y un digest estable. Los datos puramente runtime no deberán contaminar el digest pedagógico.

La traza deberá integrarse con los mecanismos de serialización y replay existentes, respetando D1 y D2.

### Regla para nuevos resolvers

**Desde la planificación de E0, todo resolver nuevo deberá diseñarse compatible con ExecutionTrace desde el principio.** No se permitirá implementar primero un resolver que solo devuelva el resultado y dejar la explicación para una fase indefinida posterior cuando el procedimiento sea determinista y explicable.

### Retrofit de resolvers existentes

Tras implementar E0 se auditarán los resolvers existentes y se clasificarán como:

- **E0-A — Compatible:** ya conservan información suficiente.
- **E0-B — Adaptable:** la información existe pero no está expuesta como traza.
- **E0-C — Requiere modificación:** se pierde información intermedia necesaria.
- **E0-D — Rediseño:** no existe un procedimiento reproducible suficientemente estructurado.

Los E0-C/E0-D deberán migrarse progresivamente según prioridad.

### Certificación E0

E0 no se certificará hasta demostrar un flujo completo:

Input → Resolver → ExecutionTrace → Serialización → Replay → Renderer → Solución → Verificación

con determinismo y tests. Como mínimo deberá existir un caso de referencia de matemáticas, uno de circuitos, uno de lógica/tabla de verdad y uno de corrección de una respuesta.

### Regla de calidad transversal

> **La explicación paso a paso es parte del contrato de calidad del resolver.**
>
> No es una decoración de UI, no es texto inventado por IA y no es opcional cuando existe un procedimiento determinista que pueda exponerse.

---
## 6. Familia F8 — Electrónica Avanzada

La familia **F8** constituye el motor de simulación circuital y electrónica de AcademicCore:

### 6.1 Fases Certificadas (F8-A a F8-P5)

| Fase | Denominación | Capacidades Principales | Estado | Gate |
|:---:|:---|:---|:---:|:---:|
| **F8-A** | Núcleo de Conocimiento Electrónico | Ontología de modelos de circuitos, rangos de validez, topología canónica. | **CERTIFICADO** | [`GATE-F8A.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8A.md) |
| **F8-B** | Solver MNA Lineal DC General | Análisis DC con números racionales exactos (`fractions.Fraction`) para elementos $R, V, I, E, G, H, F, O$. | **CERTIFICADO** | [`GATE-F8B.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8B.md) |
| **F8-C** | Reducciones Thévenin y Norton DC | Equivalentes de un puerto en continua mediante inyección de fuente de prueba y análisis de circuito pasivado. | **CERTIFICADO** | [`GATE-F8C.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8C.md) |
| **F8-D1**| Matemáticas Complejas de Alta Precisión | Aritmética compleja exacta y de alta precisión (`DecimalComplex`) con soporte trigonométrico puro. | **CERTIFICADO** | [`GATE-F8D1.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D1.md) |
| **F8-D2**| Solver Lineal Complejo | Eliminación gaussiana compleja con análisis de rango de Rouché-Capelli y umbrales de estabilidad. | **CERTIFICADO** | [`GATE-F8D2.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D2.md) |
| **F8-D3**| MNA AC Fasorial en Régimen Permanente | Análisis sinusoidal en frecuencia ($e^{+j\omega t}$) con fasores de pico para $R, L, C, V, I$. | **CERTIFICADO** | [`GATE-F8D3.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D3.md) |
| **F8-D4**| Potencia en Corriente Alterna | Potencia compleja $S = P + jQ$, potencia aparente, factor de potencia y balance de Tellegen en AC. | **CERTIFICADO** | [`GATE-F8D4.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D4.md) |
| **F8-D5**| Impedancia y Barrido Frecuencial AC | Cálculo de impedancia/admitancia de entrada y funciones de transferencia en frecuencia. | **CERTIFICADO** | [`GATE-F8D5.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D5.md) |
| **F8-D6**| Respuesta en Frecuencia y Diagramas de Bode | Magnitud en dB, fase desenrollada (*unwrap*), frecuencias de corte a $-3\text{ dB}$ y anchos de banda. | **CERTIFICADO** | [`GATE-F8D6.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D6.md) |
| **F8-D7**| Thévenin y Norton en Corriente Alterna | Impedancia equivalente compleja $Z_{th}$ y tensión en circuito abierto fasorial $V_{th}$. | **CERTIFICADO** | [`GATE-F8D7.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D7.md) |
| **F8-D8**| Resonancia y Factor de Calidad (Q) | Identificación rigurosa de frecuencias de resonancia por bracketing y cálculo de energía reactiva vs disipada. | **CERTIFICADO** | [`GATE-F8D8.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8D8.md) |
| **F8-E** | Fuentes Dependientes Lineales | Control por tensión (VCVS $E$, VCCS $G$) y por corriente (CCVS $H$, CCCS $F$) con detección de ciclos dirigidos. | **CERTIFICADO** | [`GATE-F8E.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8E.md) |
| **F8-F** | Amplificador Operacional Ideal (Nullor) | Modelo de amplificador operacional ideal ($V_+ = V_-$, $i_+ = i_- = 0$) con incógnita auxiliar de corriente de salida. | **CERTIFICADO** | [`GATE-F8F.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8F.md) |
| **F8-G** | Transformadores Ideales y Redes Dos Puertos| Modelo de transformador ideal (relación de espiras $n$, $V_1 = n V_2$, $I_2 = -n I_1$) y matrices $Z, Y, H, ABCD$. | **CERTIFICADO** | [`GATE-F8G.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8G.md) |
| **F8-H** | Diodo Shockley (Punto de Operación DC) | MNA no lineal con modelo de diodo Shockley, Jacobiano analítico, amortiguamiento Newton y validación ngspice. | **CERTIFICADO** | [`GATE-F8H.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8H.md) |
| **F8-I** | Transistor BJT (Modelo Ebers-Moll DC) | Punto de operación DC de transistores bipolares NPN y PNP bajo Ebers-Moll, Jacobiano $3\times 3$ acoplado analítico, circuitos canónicos B1–B15, escalabilidad $N=1..64$ y validación ngspice 47. | **CERTIFICADO** | [`GATE-F8I.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8I.md) |
| **F8-J** | Small-Signal AC | Linealización de puntos de operación DC de dispositivos no lineales (diodos y BJT), extracción de parámetros de pequeña señal ($g_m$, $r_\pi$, $r_o$) y resolución de respuesta en alterna. | **CERTIFICADO** | [`GATE-F8J.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8J.md) |
| **F8-K** | Semiconductores Adicionales | MOSFET Level 1 / Shichman-Hodges (`M`), JFET square-law (`J`), diodos Zener, LED, Schottky y fotodiodos (`D` + `kind`); MNA no lineal, Jacobiano analítico, contrato small-signal AC y validación ngspice 47. | **CERTIFICADO** | [`GATE-F8K.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8K.md) |
| **F8-L** | Transitorio (DAE en tiempo) | Capacitores e inductores con modelos companion, integradores implícitos Backward Euler / Trapezoidal / BDF2, paso adaptativo por LTE, rollback transaccional y Newton-DAE acoplado con validación ngspice 47. | **CERTIFICADO** | [`GATE-F8L.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8L.md) |
| **F8-M** | Análisis Avanzados | DC Sweep, Parameter Sweep (allowlist cerrado), Worst Case (esquinas $2^k$), sensibilidad DC implícita analítica, sensibilidad AC lineal y Monte Carlo nativo con semilla; warm-start con fallback trazable; validación por diferencias finitas y ngspice 47. | **CERTIFICADO** | [`GATE-F8M.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8M.md) |
| **F8-N** | Laboratorio Virtual | Orquestación reproducible de sesiones, experimentos, runs, probes, instrumentos ideales, measurements, stimuli, serialización canónica y replay sobre los engines certificados. | **CERTIFICADO** | [`GATE-F8N.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8N.md) |
| **F8-O** | Metrología e Incertidumbre (GUM) | Capa de metrología sobre motores certificados: Tipo A/B, propagación analítica (law of propagation con correlaciones), sensibilidades de circuito F8-M, Monte Carlo nativo con semilla, cifras significativas y trazabilidad con digests deterministas. | **CERTIFICADO** | [`GATE-F8O.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8O.md) |
| **F8-P1** | Sistemas y Control (SISO LTI) | Función de transferencia, márgenes de Bode por bisección, lugar de Evans, PID y Ziegler–Nichols, espacio de estados, respuestas temporales analíticas y serialización `f8p1-control/1`. | **CERTIFICADO** | [`GATE-F8P1.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8P1.md) |
| **F8-P2** | DSP (tiempo discreto) | FFT/DFT, Z unilateral causal, FIR/IIR, bilineal desde P1, muestreo/Nyquist/aliasing, márgenes discretos, serialización F8-P2. | **CERTIFICADO** | [GATE-F8P2.md](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8P2.md) |
| **F8-P3** | RF y Líneas de Transmisión | Primitivas RF, líneas de transmisión (RLGC/lossless), reflexión/VSWR/RL, redes dos-puertos Z/Y/ABCD, parámetros S (Kurokawa), cascada ABCD, Carta de Smith (matemática), matching de impedancias en forma cerrada (conjugado/λ4/stub/LC), márgenes RF (VSWR/RL/IL/ML/GT/K-μ), serialización `f8p3-rf/1`. | **CERTIFICADO** | [GATE-F8P3.md](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8P3.md) |
| **F8-P4** | Comunicaciones Digitales | Bits/símbolos/alfabetos, constelaciones Gray deterministas (BPSK/QPSK/M-PSK/M-QAM/ASK/OOK), FSK coherente, pulsos RC/RRC, canal AWGN, detección coherente, BER/SER/SNR/EbN0/EsN0, capacidad Shannon, simulación seeded, serialización `f8p4-comms/1`. | **CERTIFICADO** | [GATE-F8P4.md](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8P4.md) |
| **F8-P5** | Síntesis Satcom | Constantes SI exactas, EIRP, FSPL, Friis, antenas (ganancia/apertura), ruido kTB, G/T, C/N0, C/N, Eb/N0, margen de enlace, 1–2 legs, transponder lineal, síntesis inversa cerrada, integración P4, serialización `f8p5-satcom/1`. | **CERTIFICADO** | [GATE-F8P5.md](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8P5.md) |

### 6.2 Fases Futuras de la Familia F8

> [!NOTE]
> *Nota normativa:* F8-P4 y F8-P5 ya están certificadas y figuran en §6.1. La familia F8 queda cerrada; el siguiente paso son las decisiones D1/D2/D3, de acuerdo con el orden normativo de §5.1.

- **F8-O — Metrología e Incertidumbre**: **CERTIFICADA** ([`GATE-F8O.md`](file:///c:/Users/dmart/Documents/AcademicCore/docs/gates/GATE-F8O.md)). Expresión de incertidumbre según la guía GUM (tipo A, tipo B, combinada y expandida), propagación analítica y Monte Carlo, cifras significativas y trazabilidad metrológica.

---

## 7. Evolución Futura del Sistema (F9 a F15)

### F9 — Assessment & Evaluación
- **Tipos de preguntas**: Selección múltiple, verdadero/falso, respuesta numérica con unidades y tolerancias, fórmulas algebraicas, esquemas circuitales, diagnóstico de fallos y problemas abiertos.
- **Pipeline de corrección**: `Student Answer` $\to$ `Correction Service` (Exacto $\to$ Numérico $\to$ Simbólico $\to$ Solver de Ingeniería $\to$ IA supervisada). Prioridad absoluta al motor determinista.

### F10 — Mastery & Modelado del Estudiante
- Representación probabilística y bayesiana del dominio de cada estudiante desglosado por asignatura, tema, sección, concepto, fórmula y habilidad.

### F11 — Aprendizaje Adaptativo
- Selección dinámica de ejercicios en base a la política de priorización:
  $$
  P = 100 \cdot (0.5 \cdot need \cdot evW + 0.3 \cdot err + 0.2 \cdot rec)
  $$
- Funcionalidad garantizada con `LLM = OFF`.

### F12 — Asistencia Inteligente / Tutor Socrático
- Asistencia conversacional pedagógica: explicaciones contextuales, pistas progresivas y razonamiento guiado socrático antes de proporcionar soluciones directas.
- Arquitectura de guardrails obligatorios:
  $$
  \text{LLM Output} \longrightarrow \text{Structured JSON} \longrightarrow \text{Validator} \longrightarrow \text{Deterministic Solver} \longrightarrow \text{Verified Response}
  $$

### F13 — OneDrive & Sincronización en la Nube
- Arquitectura *offline-first* con sincronización bidireccional, detección de conflictos y versionado determinista.

### F14 — Migración de Sistemes-de-Mesura
- Ingesta, normalización y validación del corpus completo del repositorio `Damaga2005/Sistemes-de-Mesura` (teoría, fórmulas y problemas de instrumentación).

### F15 — Aplicación Final
- Entorno de escritorio unificado en Qt/PySide6 que integra dashboard, biblioteca de apuntes, resolución de ejercicios, simulación de circuitos, laboratorio virtual y tutoría adaptativa.

---

## 8. Principios de Certificación y Deuda Técnica

### Qué NO debe convertirse en deuda técnica:
1. **No convertir el sistema en un chatbot genérico.**
2. **No usar un LLM para calcular respuestas matemáticas o físicas.**
3. **No acoplar la interfaz gráfica con los motores de cálculo.**
4. **No mezclar la recuperación de conocimiento con la lógica de corrección.**
5. **No fragmentar la arquitectura creando un solver ad-hoc diferente para cada componente.**
6. **No permitir *magic defaults* silenciosos.**
7. **No ocultar errores ni relajar tolerancias artificialmente.**
8. **No sacrificar la reproducibilidad determinista por comodidad temporal.**

### Mandato de Certificación:
```
BUILD SMALL
VERIFY EVERYTHING
EXTEND THE CORE
KEEP THE SYSTEM DETERMINISTIC
USE AI WHERE IT ADDS VALUE
NEVER LET AI REPLACE VERIFIED KNOWLEDGE
```
