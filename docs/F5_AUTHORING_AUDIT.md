# F5_AUTHORING_AUDIT — estado previo (base F4 `1a6f699`, 145 passed + 2 skipped)

## AST v1 (`documents/ast.py`, 19 kinds, SCHEMA_VERSION=1)
document/section/heading/paragraph/text/emphasis/strong/link/list/list_item/
quote/code_block/inline_code/table/table_row/table_cell/image/equation/
thematic_break. Frozen dataclasses, `validate()` estructural, JSON
determinista, `from_dict` rechaza kinds/versiones/desconocidos. Testado
(`test_ast.py`). **Decisión: sin nodos nuevos en F5** — edición, plantillas,
búsqueda y validación operan sobre estos 19; sin bump de schema, compat F3
trivial.

## Edición existente: NINGUNA
No hay editor model, ni comandos, ni undo/redo, ni lifecycle, ni validación
de servicio (solo `validate()` estructural), ni plantillas, ni búsqueda
in-document, ni autosave, ni copy/paste estructural. La UI F4 edita
entidades académicas, nunca nodos AST.

## Parsers/renderers (reutilizar sin cambios)
`markdown_parser` (subset), `html_parser` (bs4 + shields Conversor),
`render_markdown`/`render_html` (deterministas, escaping). Round-trip MD
estable testado. **No reescribir.** F5 añade batería round-trip explícita
(+HTML→AST→HTML→AST, hoy ausente) y definición documentada de equivalencia.

## Persistence/CAS/versiones
`FileBlobStore` (streaming, integrity), `resource_versions` (append-only +
parent chain), `documents` derivations keyed (resource,version,parser).
**Gap F5**: (1) authored AST no tiene kind propio — se añade `document`
(kind nº 6, bytes = AST JSON canónico); (2) sin tabla de lifecycle/links
académicos — migración `009_authoring` (`authored`, `doc_links`); (3) FTS no
indexa AST — el servicio extrae texto plano del AST al guardar.

## Integración Subject/Topic
`ResourceReference` enlaza subject→resource; documents derivan de resources.
**Gap F5**: sin enlaces document→{topic,assignment,project,lab,exam} ni
lifecycle visible. Se resuelve con `doc_links` + `authored.lifecycle`.

## Limitaciones encontradas
- `DocumentService.build` devuelve summary (no AST) → F5 expone `load_ast()`.
- `ResourceRecords` no tiene `update_title` → F5 lo añade (título del AST).
- Markdown subset no soporta definiciones/footnotes → fuera de F5 (documentar).
- `QTextDocument` no se usará como modelo (acoplamiento prohibido): editor
  estructurado outline+block-editors, con acción avanzada "Edit as Markdown"
  con reparseo explícito + reporte.
