# F5_AUTHORING-DESIGN — modelo de autoría

## AuthoringDocument (`domain/authoring.py`, puro, sin Qt)
`AuthoringDocument(doc: Document, revision, dirty, undo_stack, redo_stack)`.
Edición = comandos deterministas sobre **paths** (tupla de índices desde la
raíz): `InsertNode(path, node)`, `DeleteNode(path)`, `ReplaceNode(path, node)`,
`MoveNode(src, dst)`, `UpdateText(path, text)`, `UpdateMetadata(meta)`,
`SetAttribute(path, key, value)`. Cada comando: `apply(doc)->doc` +
`inverse()`; validable antes de aplicar; historial con tope 200; `redo` se
invalida en cada comando nuevo. Undo/redo tocan SOLO working state, jamás
versiones persistidas.

## Lifecycle
`DRAFT → REVIEW → PUBLISHED → ARCHIVED`, más `DRAFT→ARCHIVED` y
`REVIEW→DRAFT`. Transiciones fuera de este grafo = error. El estado vive en
`authored.lifecycle` (no en el AST), con timestamp.

## Versionado (`application/authoring.py`)
`save()` serializa AST canónico → CAS → `append_version` (parent chain,
adapter `authoring/5.0`, hash, timestamp) → actualiza título →
indexa texto extraído en FTS → registra derivation. Blobs existentes
intocables. `save()` con bytes idénticos = no-op documentado (sin versión
artificial). Autosave: fichero temporal `<data>/autosave/<rid>.json` con tope
1 MiB + `recover()` + `cleanup()`; nunca contamina versiones.

## Validación
`validate_document(doc, blob_exists)` → `[ValidationIssue(path, code, msg)]`:
estructura, metadata, enlaces (http(s)/relativo; `javascript:`=error),
imágenes (blob `cas:<hex>` existente), ecuaciones (source no vacío,
llaves balanceadas), tablas (vía `validate()`), headings (saltos >1 =
warning), oversize. Sin sanitización silenciosa: todo se reporta.

## Plantillas (generan AST, nunca Markdown hardcodeado)
`templates.py`: lecture-notes, lab-report, assignment, project-report,
exam-notes. Cada una = función que devuelve `Document` estructurado con
secciones y placeholders.

## Copy/paste estructural
`serialize_nodes()` / `paste_nodes(mime, data)`: acepta
`application/x-academic-ast` (JSON) y degrada explícitamente desde
markdown/html (reparseo + warnings) u otros mimes (rechazo con motivo).
Jamás pérdida silenciosa.

## Búsqueda in-document
`search_document(doc, query)` → `[(path, kind, excerpt)]` determinista sobre
texto + headings + metadata.title. Sin semántica (fase posterior).

## Integración académica
`doc_links(resource_id, target_kind, target_id)` para subject/topic/
assignment/project/lab/exam + validación de existencia del target.
Documento válido sin jerarquía (links opcionales).

## UI (`ui/authoring.py`)
Pestaña Authoring: browser (authored + recursos md/html), outline (árbol de
bloques), editor de bloque (texto/ecuación/código/celda/metadata según kind),
acciones guardar/nueva-versión/undo/redo/validar/exportar MD+HTML, links
académicos, plantillas. Representación Qt explícita y testeable; el AST en
memoria del servicio es la única fuente (la UI lo refleja, no lo duplica).

## Límites F5
Sin RAG/embeddings/AI/KB, sin OneDrive/sync, sin SPICE/GUM, sin generación o
corrección de exámenes, sin instalador/plugins. Footnotes/definitions del
Markdown fora d'abast (subset F3 documentado).
