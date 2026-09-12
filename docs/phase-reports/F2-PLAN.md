# F2-PLAN — Resource Engine

Date: 2026-09-12 · Status: plan · Gate target: `docs/gates/GATE-F2.md`

## 1. Arquitectura actual relevante (F1, commit `1e08109`, 41 tests green)
- `domain/`: entities puras (`ResourceReference` = puntero académico subject→
  recurso), `identity.py` (16 kinds, `resource:<s>:r:NNNNN`), grading/schedule
  puros. Sin Qt/SQLAlchemy/filesystem (testado).
- `infrastructure/`: `Database` + migraciones 001–004 + repos explícitos.
- `application/`: Academic/Grading/Schedule services, `SimpleSearchService`
  (substring), `BackupService`, `AppLock`.
- `storage/store.py` (F0): CAS básico put/get sin integrity-check, sin
  atomic-write, sin streaming, sin delete/exists. Se reutiliza el layout
  `<cas>/<hh>/<hh>/<sha>` pero NO la clase para el path F2.
- `engines/resource.py` (F0): interfaz `ResourceEngine`/`ResourceAdapter`
  acoplada a `Store` concreto. Se conserva intacta (no rewrite, no borrado);
  F2 construye el path ports+adapters y la declara superseded en F2-REPORT.

## 2. Componentes a reutilizar
`ResourceReference`, `identity` (+`IdAllocator`, counters), `Database`,
método migrate-by-file, `norm()` de search, `Settings` (+ nuevo
`ingest.max_bytes`), `Store` layout CAS, tests F0/F1 (regresión obligatoria).

## 3. Nuevos componentes (F2, sin F3)
- `domain/ports.py`: ABCs `BlobStore`, `ResourceRecords`, `ResourceIndexer`,
  `ResourceExtractor`, `ResourceAdapter` (inversión de dependencia; solo
  abc/typing/dataclasses — domain sigue sin filesystem/SQLite/FTS5/Qt).
- `domain/resources.py`: `Resource` (id estable + kind + current_version),
  `ResourceVersion` (n, content_hash, bytes, provenance, extraction_status),
  `ResourceProvenance` (origin/file|url|generated|manual|migration, adapter…),
  `ExtractedContent` (text|binary|metadata|warnings). `ResourceReference`
  NO se toca.
- `infrastructure/cas.py`: `FileBlobStore` SHA-256, streaming chunked,
  atomic `os.replace`, integrity-check en lectura, `exists/delete`, validación
  de hash, sin path traversal (rutas derivadas solo del hex).
- `infrastructure/migrations/005_resources.sql` (resources, versions,
  provenance embebida) + `006_fts.sql` (tabla FTS5 + triggers o rebuild
  manual; decisión: rebuild manual explícito, más auditable que triggers).
- `infrastructure/resources.py`: `SqliteResourceRecords` + `FtsResourceIndexer`
  (índice derivado, `rebuild()` drip-feed por lotes, filtros kind/subject).
- `resources/adapters.py` (nuevo paquete `src/academic_core/resources/`):
  `LocalFileAdapter`, `MarkdownAdapter`, `HtmlAdapter` (stdlib html.parser,
  sin JS), `PdfAdapter` (boundary: metadata + texto si pypdf disponible, si
  no `extraction_status=deferred`; Stirling explícitamente NO).
- `application/ingest.py`: `IngestionService` con pipeline
  detect→adapter→read→hash→dedupe→store→records→extract→index, idempotente,
  transaccional (rollback ante fallo), límites de tamaño, rechazo de URLs y
  traversal. ZIP = unsupported documentado (boundary pendiente, con test).
- UI: pestaña Resources en `MainWindow` (list/import/inspect/search/reindex),
  slots finos a servicios.
- ADR-0013 (Resource vs Reference vs Version), ADR-0014 (FTS5 derivado).

## 4. Límites de F2 (NO hacer)
Stirling, Ollama/modelos, OneDrive, RAG/embeddings/vectores, Knowledge Engine,
Document AST completo, KB Sistemes, SPICE/KiCad, GUM/Monte Carlo, installer,
web/cloud-sync, ZIP extraction. Boundaries solo como interfaces+tests.

## 5. Riesgos
- PDFs sin texto (escaneados) → status `deferred`, no fallo silencioso.
- FTS5 acoplado a SQLite: reconstrucción debe probarse (drop→rebuild→igual).
- pypdf opcional: adapter debe degradar sin romper imports (import lazy).
- Memoria: streaming real en hash+copy; extractor con tope de texto indexable.
- Conteo de tests: F2 añade ~40; suite total debe seguir <10 s.

## 6. Estrategia de tests
Nuevos: `test_cas.py`, `test_resource_identity.py`, `test_provenance.py`,
`test_ingest.py`, `test_extract.py`, `test_fts.py`, `test_resource_security.py`;
extender `test_architecture.py` (domain sin sqlite3/os/FTS5/Qt) y `test_ui.py`
(pestaña Resources). Gate: 100% suite (F0+F1+F2) + checklist §23.
