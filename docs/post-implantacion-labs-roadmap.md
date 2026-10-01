# Post-Implantación Labs Roadmap

## Propósito

Este documento recoge el trabajo previsto **después de completar la implantación de los Labs de AcademicCore**.

No forma parte de las fases actuales de implantación de los Labs. Define el trabajo transversal de maduración del producto, endurecimiento del núcleo y, finalmente, la infraestructura documental de máxima fidelidad.

> **Exclusión explícita:** el diseño y evolución específica de la **Labs App** queda fuera de este documento. Esa parte está controlada por el propietario del proyecto.

---

# BLOQUE A — Product Hardening & Core Maturity

## 1. Flujo académico extremo a extremo

Consolidar las piezas existentes en un flujo coherente:

`documento → ingestión → conocimiento → conceptos → ejercicios → evaluación → corrección → mastery → práctica adaptativa`

### Objetivos

- Evitar módulos aislados que funcionen correctamente pero no estén integrados.
- Mantener trazabilidad desde el documento original hasta el resultado académico.
- Poder explicar de dónde procede cada concepto, pregunta, corrección y recomendación.
- Mantener la procedencia incluso después de transformaciones o actualizaciones.
- Verificar el flujo completo con pruebas end-to-end.

### Criterio de cierre

Un usuario debe poder recorrer el flujo académico completo sin depender de procesos manuales ocultos ni perder contexto entre módulos.

---

## 2. Document Core

Antes de implementar la conversión documental final, consolidar el núcleo documental actual como representación canónica.

### Debe soportar explícitamente

- documentos;
- secciones;
- párrafos;
- listas;
- tablas;
- imágenes;
- enlaces;
- código;
- fórmulas;
- problemas;
- ejercicios;
- soluciones;
- metadatos;
- procedencia;
- advertencias de extracción;
- referencias cruzadas.

### Principios

- El AST no pertenece a ningún Lab.
- Los Labs consumen el Document Core.
- El Document Core no depende de un Lab concreto.
- La información no debe degradarse innecesariamente durante transformaciones.
- La matemática mantiene LaTeX como representación canónica.

---

## 3. Búsqueda académica

Evolucionar la búsqueda desde búsqueda textual hacia una búsqueda realmente académica.

### Debe poder localizar

- documentos;
- conceptos;
- definiciones;
- fórmulas;
- problemas;
- ejercicios;
- temas;
- asignaturas;
- recursos relacionados;
- contenido equivalente o similar.

### Cada resultado debería poder mostrar

- origen;
- documento;
- sección/página cuando exista;
- fragmento relevante;
- tipo de contenido;
- procedencia;
- confianza cuando la extracción o reconstrucción no sea exacta.

### Objetivo

La búsqueda debe responder no solo a “dónde aparece esta palabra”, sino a “dónde está la información académica que necesito”.

---

## 4. Knowledge Core

Reforzar la trazabilidad y evolución del conocimiento.

### Mejoras

- versionado de conocimiento;
- procedencia por fragmento;
- relación concepto ↔ fuente;
- detección de contenido actualizado;
- invalidación/reprocesado controlado;
- resolución de duplicados;
- relaciones entre conceptos;
- referencias cruzadas;
- historial de transformaciones;
- diagnóstico de conocimiento incompleto.

### Principio

Ningún conocimiento académico debe perder su fuente original sin una razón explícita.

---

## 5. Question Bank

Ampliar la profundidad del banco de preguntas.

### Mejoras

- más tipos de problemas;
- problemas paramétricos;
- variantes equivalentes;
- dependencia de prerrequisitos;
- dificultad justificable;
- metadatos académicos;
- procedencia;
- solución estructurada;
- pasos esperados;
- respuestas equivalentes;
- validación matemática;
- detección de preguntas defectuosas.

El banco debe poder distinguir entre una respuesta diferente y una respuesta matemáticamente equivalente.

---

## 6. Corrección matemática

Reforzar la corrección más allá de correcto/incorrecto.

### Debe distinguir, cuando sea posible

- resultado correcto;
- procedimiento correcto;
- error aritmético;
- error de signo;
- error de unidades;
- fórmula incorrecta;
- sustitución incorrecta;
- redondeo;
- dominio inválido;
- método alternativo válido;
- respuesta equivalente;
- error conceptual.

### Principio

La corrección debe identificar **qué falló**, no únicamente si falló.

---

## 7. Assessment

Mejorar la evaluación sobre la infraestructura ya existente.

### Mejoras

- mayor variedad de tipos de evaluación;
- variantes de problemas;
- selección basada en prerrequisitos;
- análisis de errores;
- trazabilidad de preguntas;
- análisis por concepto;
- detección de preguntas ambiguas o defectuosas;
- reutilización controlada de ejercicios;
- generación de informes más útiles.

---

## 8. Mastery

Refinar el modelo de dominio académico.

### Mejoras

- evidencia necesaria para considerar dominado un concepto;
- separación entre acierto aislado y dominio sostenido;
- dependencia entre conceptos;
- degradación del dominio con el tiempo cuando corresponda;
- evidencia de distintos tipos de ejercicio;
- explicación de por qué el sistema considera un concepto dominado o pendiente.

No declarar mastery con evidencia insuficiente.

---

## 9. Adaptive Learning

Mejorar las decisiones de práctica adaptativa.

### Debe poder considerar

- mastery;
- errores recientes;
- dificultad;
- prerrequisitos;
- tiempo desde la última práctica;
- tipos de error;
- rendimiento histórico;
- variedad de ejercicios;
- objetivos académicos.

Las recomendaciones deben ser explicables y reproducibles.

---

## 10. Socratic Tutor y frontera LLM

Mantener al LLM como componente auxiliar y nunca como autoridad matemática.

### Mejoras

- contexto académico más preciso;
- uso de fuentes/procedencia;
- verificación determinista;
- detección de afirmaciones no verificadas;
- mejores explicaciones de errores;
- recuperación ante respuestas ambiguas;
- separación estricta entre propuesta del LLM y resultado verificado.

### Regla

`LLM → propuesta estructurada → validación → solver determinista → respuesta verificada`

El LLM no debe convertirse en una dependencia obligatoria del núcleo académico.

---

## 11. Cloud Sync

Reforzar la experiencia alrededor del sistema offline-first ya existente.

### Mejoras

- visualización clara del estado;
- resolución de conflictos;
- recuperación de errores;
- reintentos;
- historial de sincronización;
- diagnósticos;
- recuperación después de interrupciones;
- validación de integridad;
- pruebas de escenarios prolongados offline/online.

La sincronización nunca debe destruir datos locales por un fallo remoto.

---

# BLOQUE B — Product / UX

## 12. UX de producto

No rediseñar la Labs App aquí.

Sí mejorar la experiencia transversal de AcademicCore:

- navegación global;
- descubrimiento de funciones;
- estados vacíos;
- errores recuperables;
- progreso de operaciones largas;
- mensajes de diagnóstico;
- consistencia visual;
- accesibilidad;
- preferencias;
- historial;
- acciones recientes;
- feedback de operaciones.

El objetivo es que el producto explique claramente qué está haciendo y qué ha ocurrido.

---

## 13. Diagnóstico y observabilidad

Crear una capa transversal de diagnóstico comprensible.

Debe permitir identificar:

- errores de ingestión;
- documentos parcialmente procesados;
- fallos de conversión;
- errores de sincronización;
- errores de motores;
- problemas de persistencia;
- operaciones lentas;
- recursos no verificables.

Los diagnósticos técnicos deben poder convertirse en mensajes útiles para el usuario.

---

## 14. Configuración

Mejorar la configuración sin convertirla en una interfaz excesivamente compleja.

Separar claramente:

- preferencias de usuario;
- rutas;
- fuentes documentales;
- sincronización;
- rendimiento;
- privacidad;
- comportamiento académico;
- opciones avanzadas.

---

# BLOQUE C — Windows, rendimiento, seguridad y fiabilidad

## 15. Windows / Desktop Hardening

Verificar el producto real, no solamente el código.

### Debe probarse

- instalación limpia;
- actualización;
- desinstalación;
- recuperación;
- Start Menu;
- rutas con espacios;
- rutas Unicode;
- permisos;
- OneDrive;
- múltiples monitores;
- DPI;
- 125/150/200 %;
- suspensión/reanudación;
- documentos grandes;
- bibliotecas grandes;
- operaciones largas;
- errores recuperables;
- limpieza de datos temporales.

---

## 16. Rendimiento y escalabilidad

El objetivo no es únicamente que las pruebas pasen, sino que AcademicCore siga siendo utilizable al crecer.

### Escenarios

- bibliotecas grandes;
- muchos documentos;
- documentos grandes;
- ingestión masiva;
- búsquedas repetidas;
- sincronización;
- generación de ejercicios;
- evaluaciones extensas;
- múltiples operaciones simultáneas.

Medir:

- latencia;
- memoria;
- CPU;
- tamaño de base de datos;
- tiempos de ingestión;
- tiempos de búsqueda;
- operaciones p95/p99 cuando sea relevante.

---

## 17. Seguridad

Continuar endureciendo especialmente las superficies de entrada.

### Revisar

- HTML;
- Markdown;
- DOCX;
- PDF;
- imágenes;
- enlaces;
- contenido externo;
- archivos malformados;
- rutas;
- nombres de archivo;
- contenido potencialmente ejecutable;
- XSS;
- traversal;
- descompresión peligrosa;
- recursos remotos.

Principio:

> Un documento académico importado nunca debe convertirse automáticamente en código ejecutable o contenido confiable.

---

## 18. Persistencia y migraciones

Mantener la base de datos evolucionable sin pérdida de información.

### Mejoras

- migraciones atómicas;
- compatibilidad entre versiones;
- recuperación ante interrupción;
- backups cuando proceda;
- validación de integridad;
- detección de esquemas incompatibles;
- migraciones reversibles cuando sea razonable.

---

## 19. Accesibilidad

Completar la validación real de accesibilidad.

### Revisar

- navegación por teclado;
- foco;
- contraste;
- escalado;
- lector de pantalla;
- mensajes de error;
- estados de progreso;
- componentes complejos;
- fórmulas y contenido matemático.

No considerar una característica accesible únicamente porque “funciona” visualmente.

---

# BLOQUE D — Calidad y verificación

## 20. Testing funcional end-to-end

Mantener los tests unitarios existentes, pero aumentar la cobertura de flujos completos.

### Flujos prioritarios

- documento → conocimiento;
- conocimiento → ejercicio;
- ejercicio → evaluación;
- evaluación → corrección;
- corrección → mastery;
- mastery → práctica adaptativa;
- sincronización;
- recuperación ante errores;
- importación/exportación.

---

## 21. Golden fixtures

Crear una colección estable de documentos y problemas de referencia.

Debe incluir:

- documentos académicos;
- fórmulas;
- tablas;
- imágenes;
- problemas;
- soluciones;
- documentos largos;
- documentos malformados;
- casos multiformato.

Las fixtures deberán utilizarse para detectar regresiones semánticas y visuales.

---

## 22. Contract testing

Mantener contratos explícitos entre:

- Document Core;
- Knowledge Core;
- Question Bank;
- Assessment;
- Correction;
- Mastery;
- Adaptive Learning;
- Tutor;
- Sync;
- UI.

Una modificación interna no debería romper silenciosamente otro módulo.

---

## 23. Documentación viva

Mantener sincronizados:

- README;
- arquitectura;
- roadmap;
- contratos;
- especificaciones;
- códigos de error;
- documentación de producto;
- documentación de Labs.

Toda afirmación de funcionalidad debe corresponder con una capacidad realmente implementada y verificable.

---

# BLOQUE E — Conversión documental de máxima fidelidad

Este bloque conserva la decisión tomada previamente y se ejecutará después del endurecimiento principal.

## 24. Objetivo

Construir una capa documental transversal capaz de convertir entre los principales formatos académicos sin destruir información relevante.

La prioridad será la **fidelidad semántica y estructural**, y posteriormente la fidelidad visual allí donde sea técnicamente posible.

## 25. Formatos objetivo

- HTML ↔ Markdown
- HTML ↔ DOCX
- HTML ↔ PDF
- Markdown ↔ DOCX
- Markdown ↔ PDF
- DOCX ↔ HTML
- DOCX ↔ Markdown
- DOCX ↔ PDF
- PDF → HTML
- PDF → Markdown
- PDF → DOCX

Cuando proceda, también se contemplará la interacción con LaTeX como formato matemático y de composición.

## 26. Elementos que deben conservarse

- Fórmulas matemáticas.
- Fórmulas en **LaTeX** como representación matemática canónica.
- Problemas y ejercicios.
- Enunciados, apartados y soluciones.
- Tablas y estructura de celdas.
- Imágenes y referencias.
- Listas y jerarquía documental.
- Código.
- Enlaces.
- Notas y metadatos relevantes.
- Estructura de títulos y secciones.
- Cuando sea posible, estilos, saltos de página, cabeceras, pies y otra información de maquetación.

## 27. Arquitectura

La conversión deberá apoyarse en un **Document Core / AST documental canónico**.

Principio:

> Ningún conversor debe traducir directamente de un formato a otro si hacerlo implica perder información que pueda conservarse en la representación canónica.

Flujo:

`Formato origen → Document AST → Formato destino`

Para matemáticas:

`MathML / OMML / fórmula enriquecida → LaTeX canónico → AST → formato destino`

Cuando el documento de origen ya contenga LaTeX válido, se conservará preferentemente el source LaTeX original.

## 28. Fidelidad semántica frente a visual

Se distinguirán:

1. **Fidelidad semántica:** contenido y estructura equivalentes.
2. **Fidelidad visual:** apariencia, tipografía, posicionamiento y paginación equivalentes.

No se afirmará que una conversión es “100 % fiel” únicamente porque el archivo de destino se abra correctamente.

## 29. PDF

PDF será tratado como el caso más complejo.

La conversión deberá considerar, cuando estén disponibles:

- texto y posición;
- bloques y jerarquía;
- fórmulas;
- tablas;
- imágenes;
- vectores;
- fuentes;
- saltos y paginación;
- documentos escaneados;
- confianza y procedencia.

Los elementos que no puedan reconstruirse con suficiente confianza deberán quedar identificados y no desaparecer silenciosamente.

## 30. Informe de fidelidad y pérdida

Cada conversión importante deberá poder producir un informe con:

- elementos preservados;
- transformados;
- reconstruidos;
- con pérdida;
- no verificables;
- nivel de confianza.

Principio:

> Si algo no puede conservarse, AcademicCore debe decirlo explícitamente.

## 31. Round-trip

Pruebas de ida y vuelta:

- HTML → Markdown → HTML
- DOCX → AST → DOCX
- DOCX → Markdown → DOCX
- HTML → PDF → extracción → AST
- Markdown → PDF → extracción/validación
- documentos con fórmulas → conversión → comprobación del LaTeX

Usar *golden fixtures* con fórmulas, ejercicios, tablas, imágenes, listas, código y estructuras complejas.

---

# Orden de ejecución post-Labs

1. **Flujo académico extremo a extremo**
2. **Document Core**
3. **Knowledge Core y trazabilidad**
4. **Búsqueda académica**
5. **Question Bank + corrección matemática**
6. **Assessment + Mastery + Adaptive Learning**
7. **Tutor y frontera LLM**
8. **Cloud Sync**
9. **UX transversal**
10. **Diagnóstico y observabilidad**
11. **Windows/Desktop Hardening**
12. **Rendimiento y escalabilidad**
13. **Seguridad**
14. **Persistencia y migraciones**
15. **Accesibilidad**
16. **Testing E2E + golden fixtures + contratos**
17. **Documentación viva**
18. **Conversión documental de máxima fidelidad**

> El orden es orientativo: algunas tareas podrán ejecutarse en paralelo, pero la conversión documental de máxima fidelidad queda deliberadamente al final.

---

# Criterio global de finalización

AcademicCore no se considerará completamente maduro por el mero hecho de tener todos los Labs implementados.

El objetivo final será:

**Labs completos + núcleo académico integrado + producto robusto + Windows fiable + seguridad + rendimiento + trazabilidad + testing E2E + documentación coherente + conversión documental de máxima fidelidad.**

---

## Exclusiones

Este roadmap **no incluye el diseño específico de la Labs App** ni decisiones de producto internas de esa aplicación.

---

## Estado

**Planificado — Post-Implantación Labs**

Este documento no implica que estas funcionalidades estén implementadas actualmente. Define el trabajo posterior necesario para llevar AcademicCore desde una base funcional y con Labs completos hasta un producto académico maduro y robusto.
