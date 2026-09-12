# Modules & Boundaries

| Module | Path | Depends on | Must NOT import |
|---|---|---|---|
| domain | `domain/` | stdlib | PySide6, app, engines |
| config | `config/` | stdlib | PySide6, app |
| storage | `storage/` | stdlib (sqlite3) | PySide6, app |
| engines/resource | `engines/resource.py` | storage, domain | PySide6, app |
| engines/document | `engines/document_ast.py` | domain | PySide6, app |
| engines/pdf | `engines/pdf.py` | — (interface) | Stirling impl details |
| engines/ai | `engines/ai.py` | stdlib urllib | whole KB, app |
| engines/providers | `engines/providers.py` | pathlib | tokens in code |
| engines/engineering | `engines/engineering.py` | domain | SPICE binaries directly |
| ui/app | `app.py` | config, PySide6 | engines internals beyond interfaces |

Split points (future, no rewrite needed): SPICE/LaTeX/Stirling/Ollama already
external processes; index builder → background QThread → optional service.
