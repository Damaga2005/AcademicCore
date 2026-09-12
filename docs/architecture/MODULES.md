# Modules & Boundaries

| Module | Path | Depends on | Must NOT import |
|---|---|---|---|
| domain | `domain/` | stdlib | PySide6, app, engines |
| config | `config/` | stdlib | PySide6, app |
| storage | `storage/` | stdlib (sqlite3) | PySide6, app |
| engines/resource | `engines/resource.py` | storage, domain | PySide6, app |
| documents/ast | `documents/ast.py` | stdlib only | everything (Qt, SQLite, bs4, parsers) |
| documents/parsers | `documents/*parser*, conversor_*` | ast, bs4/lxml | Qt, Tk, markdownify |
| documents/renderers | `documents/render_*` | ast | Qt, raw HTML injection |
| application/documents | `application/documents.py` | blobs, records, db | Qt |
| pdf/engine | `pdf/engine.py` | documents.ast, pypdf | Qt, Stirling, AGPL libs |
| pdf/stirling | `pdf/stirling.py` | engine (interface) | Domain, non-localhost |
| domain/authoring | `domain/authoring.py` | documents.ast (value objects) | Qt, I/O, versions |
| documents/validate+templates+search | `documents/*.py` | ast | Qt, network |
| application/authoring | `application/authoring.py` | blobs, records, indexer, stores | Qt |
| ui/authoring | `ui/authoring.py` | application facade, domain | infrastructure, sqlite3 |

Note: domain→documents.ast is a value-object dependency (stdlib-only nodes),
not a layer inversion; parsers/backends stay outside domain.
| engines/document | `engines/document_ast.py` | domain | PySide6, app |
| engines/pdf | `engines/pdf.py` | — (interface) | Stirling impl details |
| engines/ai | `engines/ai.py` | stdlib urllib | whole KB, app |
| engines/providers | `engines/providers.py` | pathlib | tokens in code |
| engines/engineering | `engines/engineering.py` | domain | SPICE binaries directly |
| ui/app | `app.py` | config, PySide6 | engines internals beyond interfaces |

Split points (future, no rewrite needed): SPICE/LaTeX/Stirling/Ollama already
external processes; index builder → background QThread → optional service.
