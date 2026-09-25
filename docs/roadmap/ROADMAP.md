# AcademicCore — Roadmap Maestro + Plan de Implementación

> **Proyecto**: AcademicCore  
> **Documento**: Roadmap Maestro + Plan de Implementación  
> **Estado**: En Desarrollo Activo — orden de implementación consolidado y actualizado
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

## 5. Roadmap Global + Plan de Implementación

Esta sección es la **fuente normativa del orden de trabajo** de AcademicCore. No representa únicamente la historia del proyecto: define el orden recomendado para continuar la implementación, minimizando bloqueos, duplicaciones y trabajo que después tendría que rehacerse.

### 5.1 Estado global

Las fases ya certificadas o cerradas se conservan como historial y como base técnica. Las fases pendientes se ejecutan en el orden indicado en §5.2.

> [!IMPORTANT]
> **Regla de orden:** no iniciar una fase pendiente mientras una dependencia directa marcada en el plan no esté cerrada, salvo decisión explícita documentada.
>
> **Regla de integridad:** ninguna fase futura puede modificar bajo ningún concepto el comportamiento certificado de fases anteriores sin una fase de cambio explícitamente aprobada, con tests de regresión y nueva certificación.
>
> **F14 — Sistemes-de-Mesura queda eliminada del roadmap.**
>
> **F16 — Contenido Aeroespacial/Satélite se conserva como fase final del roadmap.**
>
> Las subdivisiones históricas **PRE-F0.x** se conservan como referencia del proyecto, pero sus nombres exactos no están formalizados actualmente en este repositorio.

### 5.2 Orden normativo de implementación

```
PRE-F0.x  Fundaciones históricas                         [HISTÓRICO]
   │
F0        Auditoría y Arquitectura                       [CERTIFICADO]
   │
F1        Núcleo de Dominio                              [CERTIFICADO]
   │
F2        Recursos y Almacenamiento CAS                  [CERTIFICADO]
   │
F3        Documentos / PDF / AST                         [CERTIFICADO]
   │
F3.1      Extensión de ingestión                         [CERTIFICADO]
   │
F4        Knowledge / Modelo Académico                   [CERTIFICADO]
   │
F4.1      Migración y consolidación                      [CERTIFICADO]
   │
F4.2      Historial / Personalización / Notificaciones  [CERTIFICADO]
   │
F5        Authoring Engine                               [CERTIFICADO]
   │
F6        Matemáticas e Ingeniería Base                  [CERTIFICADO]
   │
F7        MNA Lineal y Simulación SPICE                  [CERTIFICADO]
   │
F8-A → F8-P5  Electrónica Avanzada                       [CERTIFICADO]
   │
F8-Q      Motor Digital + Logic Analyzer                 [CERTIFICADO]
   │
E0 → E0.4 Explainable Execution / Engineering           [CERTIFICADO]
   │
D1        Arquitectura de módulos/plugins                [CERTIFICADO]
   │
D2        Logging / errores                              [CERTIFICADO]
   │
D3        Licencia única                                 [CERTIFICADO]
   │
F15       Aplicación Final / app mínima funcional        [CERTIFICADO]
   │
F3-ext    Integración conversor HTML→MD/LaTeX            [CERTIFICADO]
   │
F4-ext    Fusión de gestión académica                    [CERTIFICADO]
   │
══════════════════ ESTADO ACTUAL ══════════════════════════
   │
F13-ext   Sync entre 2 PCs personales                    [CERTIFICADA]
   │
D4        Pipeline CI/build                              [CERTIFICADA]
   │
D5        Suite global de tests                          [SIGUIENTE]
   │
D6        Esquema neutro de banco de preguntas           [PENDIENTE]
   │
D7        Ingesta estructurada → Knowledge Core          [PENDIENTE]
   │
F9        Assessment y Evaluación Formal                 [PENDIENTE]
   │
F10       Mastery y Modelado del Estudiante              [PENDIENTE]
   │
F11       Aprendizaje Adaptativo                         [PENDIENTE]
   │
F12       IA / Tutor Socrático con Guardrails            [PENDIENTE]
   │
F13       OneDrive / Cloud Sync completo                 [PENDIENTE]
   │
F16       Contenido Aeroespacial / Satélite              [PENDIENTE — ÚLTIMA FASE]
```

### 5.3 Plan de implementación por fase

| Orden | Fase | Objetivo de implementación | Dependencias principales | Estado |
|---:|---|---|---|:---:|
| 1 | F13-ext | Sincronización determinista entre 2 PCs personales; última edición gana + log, sin CRDT | F15 | **CERTIFICADA** |
| 2 | D4 | Pipeline CI/build y ejecución automática de tests en cada cambio | F15 | **CERTIFICADA** |
| 3 | D5 | Consolidar suite global de tests y cobertura de regresión, empezando por el conversor HTML→MD | D4 | **SIGUIENTE** |
| 4 | D6 | Definir esquema neutro y versionado para bancos de preguntas, independiente de una asignatura concreta | — | Pendiente |
| 5 | D7 | Transformar definiciones, fórmulas y preguntas estructuradas en entidades del Knowledge Core/F4 | D6, F4 | Pendiente |
| 6 | F9 | Assessment formal: tipos de pregunta, intentos, corrección determinista y pipeline de evaluación | D6, D7 | Pendiente |
| 7 | F10 | Modelado de mastery y dominio del estudiante a partir de evidencia real de F9 | F9 | Pendiente |
| 8 | F11 | Selección adaptativa de ejercicios y rutas personalizadas, funcional con LLM=OFF | F10 | Pendiente |
| 9 | F12 | Tutor socrático desacoplado: LLM → JSON estructurado → validación → autoridad determinista | F11 | Pendiente |
| 10 | F13 | Sincronización cloud/OneDrive completa, conflictos, versionado y operación offline-first | F13-ext | Pendiente |
| 11 | F16 | Contenido Aeroespacial/Satélite; mecánica orbital básica como fase final de contenido | F13 | Pendiente |

### 5.4 Dependencias críticas

La cadena pedagógica deberá mantenerse explícitamente:

```
D6
 ↓
D7
 ↓
F9
 ↓
F10
 ↓
F11
 ↓
F12
```

Y la cadena de sincronización:

```
F15
 ↓
F13-ext
 ↓
F13
```

La razón del orden es evitar implementar una capa sobre contratos todavía inestables. En particular:

- **D6** define qué representa una pregunta.
- **D7** define cómo entra ese conocimiento estructurado en el Knowledge Core.
- **F9** convierte esa estructura en evaluación y evidencia.
- **F10** convierte la evidencia de evaluación en estado de dominio.
- **F11** utiliza el dominio para decidir qué estudiar después.
- **F12** utiliza todo lo anterior como contexto pedagógico, pero nunca sustituye la autoridad determinista.
- **F13-ext** resuelve primero el caso pequeño de sincronización entre dos PCs antes de ampliar el problema a cloud/OneDrive con F13.

### 5.5 Criterio para avanzar

Una fase se considera cerrada únicamente cuando:

1. su implementación está terminada;
2. sus tests específicos están verdes;
3. las regresiones relevantes están verdes;
4. sus contratos de dependencia están documentados;
5. existe gate/certificación cuando corresponda;
6. no quedan cambios silenciosos sobre fases certificadas;
7. el estado del roadmap se actualiza al cierre.

**No se considera una fase completada simplemente porque exista código funcional.**

### 5.6 Fases eliminadas

#### F14 — Sistemes-de-Mesura
**ELIMINADA.** No forma parte del plan de implementación futuro.



### 5.7 Regla de oro

> **Construir en orden, verificar cada dependencia, preservar lo certificado y no introducir complejidad antes de que exista una necesidad contractual clara.**

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

## 7. Evolución Futura del Sistema

### F9 — Assessment & Evaluación
- **Tipos de preguntas**: Selección múltiple, verdadero/falso, respuesta numérica con unidades y tolerancias, fórmulas algebraicas, esquemas circuitales, diagnóstico de fallos y problemas abiertos.
- **Pipeline de corrección**: Student Answer → Correction Service (Exacto → Numérico → Simbólico → Solver de Ingeniería → IA supervisada). Prioridad absoluta al motor determinista.

### F10 — Mastery & Modelado del Estudiante
- Representación probabilística y bayesiana del dominio de cada estudiante desglosado por asignatura, tema, sección, concepto, fórmula y habilidad.

### F11 — Aprendizaje Adaptativo
- Selección dinámica de ejercicios en base a evidencia de dominio, errores y recencia.
- Funcionalidad garantizada con LLM = OFF.

### F12 — Asistencia Inteligente / Tutor Socrático
- Asistencia conversacional pedagógica: explicaciones contextuales, pistas progresivas y razonamiento guiado socrático antes de proporcionar soluciones directas.
- Arquitectura de guardrails obligatorios:
  LLM Output → Structured JSON → Validator → Deterministic Solver → Verified Response

### F13 — OneDrive & Sincronización en la Nube
- Evolución de F13-ext hacia sincronización cloud/OneDrive completa.
- Arquitectura offline-first, sincronización bidireccional, detección de conflictos y versionado determinista.

### F15 — Aplicación Final
- **Estado: CERTIFICADA / IMPLEMENTADA.**
- Entorno de escritorio unificado en Qt/PySide6 que sirve como base de integración de las fases posteriores.

> **F14 — Sistemes-de-Mesura queda eliminada. F16 — Contenido Aeroespacial/Satélite permanece como última fase futura y no debe adelantarse ni eliminarse sin una decisión explícita y documentada.**

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
