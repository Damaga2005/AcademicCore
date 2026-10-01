# Post-Implantación Labs Roadmap

## Propósito

Este documento recoge el trabajo previsto **después de completar la implantación de los Labs de AcademicCore**.

No forma parte de las fases actuales de implantación de los Labs. Su objetivo es preservar desde ahora las decisiones de arquitectura y las funcionalidades transversales que se abordarán al final del ciclo principal.

---

## 1. Conversión documental de máxima fidelidad

### Objetivo

Construir una capa documental transversal capaz de convertir entre los principales formatos académicos sin destruir información relevante.

La prioridad será la **fidelidad semántica y estructural**, y posteriormente la fidelidad visual allí donde sea técnicamente posible.

### Formatos objetivo

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

### Elementos que deben conservarse

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

### Arquitectura prevista

La conversión deberá apoyarse en un **Document Core / AST documental canónico**.

Principio central:

> Ningún conversor debe traducir directamente de un formato a otro si hacerlo implica perder información que pueda conservarse en la representación canónica.

Flujo conceptual:

Formato origen → Document AST → Formato destino

Para matemáticas:

MathML / OMML / fórmula enriquecida → LaTeX canónico → AST → formato destino

Cuando el documento de origen ya contenga LaTeX válido, se conservará preferentemente el **source LaTeX original**, evitando reconstruirlo innecesariamente.

### Fidelidad semántica frente a fidelidad visual

Se distinguirán explícitamente dos objetivos:

1. **Fidelidad semántica**
   - El contenido, estructura, fórmulas, problemas, tablas e imágenes siguen representando la misma información.
2. **Fidelidad visual**
   - El documento resultante mantiene apariencia, tipografía, posicionamiento, paginación y maquetación.

No se afirmará que una conversión es “100 % fiel” únicamente porque el archivo de destino se abra correctamente.

### PDF

PDF será tratado como el caso más complejo.

La conversión PDF → formato editable deberá considerar, cuando estén disponibles:

- texto y posición;
- bloques y jerarquía;
- fórmulas;
- tablas;
- imágenes;
- vectores;
- fuentes;
- saltos y paginación;
- documentos escaneados;
- información de confianza/procedencia.

Los elementos que no puedan reconstruirse con suficiente confianza deberán quedar identificados en un informe de fidelidad, en lugar de desaparecer silenciosamente.

---

## 2. Informe de fidelidad y pérdida

Cada conversión importante deberá poder producir un informe que indique:

- elementos preservados;
- elementos transformados;
- elementos reconstruidos;
- elementos con pérdida;
- elementos no verificables;
- nivel de confianza cuando la reconstrucción no sea exacta.

Principio:

> Si algo no puede conservarse, AcademicCore debe decirlo explícitamente.

---

## 3. Round-trip y pruebas de regresión

La capa de conversión tendrá pruebas específicas de ida y vuelta.

Ejemplos:

- HTML → Markdown → HTML
- DOCX → AST → DOCX
- DOCX → Markdown → DOCX
- HTML → PDF → extracción → AST
- Markdown → PDF → extracción/validación
- documentos con fórmulas → conversión → comprobación del LaTeX

Las pruebas deberán usar documentos reales de referencia (*golden fixtures*) que contengan:

- fórmulas;
- ejercicios;
- tablas;
- imágenes;
- listas;
- bloques de código;
- estructuras anidadas;
- casos límite de formato.

---

## 4. Integración con AcademicCore

La capa documental final deberá servir como infraestructura transversal para:

- MathLab.
- Labs de ingeniería.
- Banco de ejercicios.
- Apuntes y materiales académicos.
- Documentos importados.
- Generación de informes.
- Tutor y recursos educativos.
- Exportación de resultados.
- Intercambio de materiales entre formatos.

La implementación deberá respetar la arquitectura existente:

- el contenido matemático mantiene su representación canónica en LaTeX;
- el Document Core es independiente de un Lab concreto;
- los Labs consumen la infraestructura documental, pero no deben acoplarla a un dominio específico.

---

## 5. Criterio de finalización

Este bloque solo podrá considerarse cerrado cuando:

- exista el Document Core canónico;
- estén implementadas las conversiones objetivo que sean técnicamente viables;
- las fórmulas se conserven de forma verificable;
- los problemas y ejercicios mantengan su estructura;
- tablas e imágenes tengan tratamiento explícito;
- exista informe de fidelidad/pérdida;
- existan pruebas de round-trip;
- existan fixtures de regresión;
- las pérdidas inevitables estén documentadas;
- no se hagan afirmaciones de fidelidad superior a la demostrada por las pruebas.

---

## Estado

**Planificado — Post-Implantación Labs**

Este documento **no implica que esta funcionalidad esté implementada actualmente**. Define el trabajo que se abordará una vez finalizada la implantación principal de los Labs.