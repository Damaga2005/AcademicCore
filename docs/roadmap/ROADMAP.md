# AcademicCore — Roadmap Maestro Completo, Arquitectura y Evolución Futura

> **Proyecto**: AcademicCore  
> **Documento**: Roadmap Maestro y Visión Funcional  
> **Estado**: En Desarrollo Activo (Fases F0 a F8-I **CERTIFICADAS**)  
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
 F8  Electrónica Avanzada (F8-A ... F8-I)      [CERTIFICADO]
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

---

## 6. Familia F8 — Electrónica Avanzada

La familia **F8** constituye el motor de simulación circuital y electrónica de AcademicCore:

### 6.1 Fases Certificadas (F8-A a F8-I)

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

### 6.2 Fases Futuras de la Familia F8

- **F8-J — Small-Signal AC**: Linealización de puntos de operación DC de dispositivos no lineales (diodos y transistores) para extraer parámetros de pequeña señal ($g_m, r_\pi, r_o$) y resolver respuesta en alterna.
- **F8-K — Semiconductores Adicionales**: Incorporación de modelos para MOSFET (Level 1 / Shichman-Hodges), JFET, diodos Zener, LEDs, Schottky y fotodiodos.
- **F8-L — Transient (Régimen Transitorio)**: Integración temporal de ecuaciones diferenciales algebraicas (DAE) mediante esquemas implícitos (Backward Euler, Trapezoidal, BDF) con paso de tiempo adaptativo.
- **F8-M — Análisis Avanzados**: Barridos DC (*DC Sweep*), barridos de parámetros (*Parameter Sweep*), análisis de sensibilidad ($\partial \text{salida} / \partial \text{parámetro}$), Monte Carlo y análisis de peor caso (*Worst Case*).
- **F8-N — Laboratorio Virtual**: Instrumentación virtual interactiva (fuente de alimentación DC, multímetro digital, osciloscopio de doble canal, generador de funciones, analizador lógico).
- **F8-O — Metrología e Incertidumbre**: Expresión de incertidumbre según la guía GUM (tipo A, tipo B, combinada y expandida), propagación analítica y Monte Carlo, cifras significativas y trazabilidad metrológica.

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
