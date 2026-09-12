"""Phase 1 boundaries: Domain <- nothing; App/Infrastructure <- never Qt.

Domain: stdlib + dataclasses only (no PySide6, no sqlalchemy, no app).
Application/Infrastructure: no PySide6 (UI imports them, never the reverse).
Whole src: no sqlalchemy at all (ADR-0012, stdlib sqlite3 decision).
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"

# NOTE: plain substring "academic_core.app" would false-positive on
# "academic_core.application" — match the app module exactly.
_RX_APP = re.compile(r"academic_core\.app(?!lication)")


def _texts(sub: str):
    return list((SRC / sub).rglob("*.py"))


def test_domain_is_pure():
    violations = []
    for f in _texts("domain"):
        text = f.read_text(encoding="utf-8")
        for bad in ("PySide6", "sqlalchemy", "academic_core.application",
                    "academic_core.infrastructure"):
            if bad in text:
                violations.append(f"{f.relative_to(SRC)} imports {bad}")
        if _RX_APP.search(text):
            violations.append(f"{f.relative_to(SRC)} imports academic_core.app")
    assert not violations, violations


def test_application_and_infrastructure_have_no_ui():
    import re as _re
    violations = []
    for sub in ("application", "infrastructure", "storage", "config", "engines",
                "documents", "pdf", "resources"):
        for f in _texts(sub):
            text = f.read_text(encoding="utf-8")
            # import statements only: docstring prose may name backends.
            if _re.search(r"^\s*(import|from)\s+PySide6", text, _re.MULTILINE):
                violations.append(f"{f.relative_to(SRC)} imports PySide6")
            if _RX_APP.search(text):
                violations.append(f"{f.relative_to(SRC)} imports academic_core.app")
    assert not violations, violations


def test_no_sqlalchemy_anywhere():
    violations = []
    for f in SRC.rglob("*.py"):
        if "sqlalchemy" in f.read_text(encoding="utf-8"):
            violations.append(str(f.relative_to(SRC)))
    assert not violations, violations


def test_domain_knows_no_backends():
    """Domain != Qt, sqlite3, FTS5, filesystem, network.

    Parsed with ast: only real imports count (docstring prose mentioning a
    backend by name is documentation, not a dependency).
    """
    import ast
    forbidden = {"os", "pathlib", "sqlite3", "urllib", "socket", "hashlib",
                 "PySide6", "ftplib", "http"}
    violations = []
    for f in _texts("domain"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in forbidden:
                        violations.append(f"{f.relative_to(SRC)} imports {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in forbidden:
                    violations.append(f"{f.relative_to(SRC)} imports from {node.module}")
    assert not violations, violations


def test_engines_do_not_import_each_other_circularly():
    import academic_core.engines as e
    assert hasattr(e, "PDFService") and hasattr(e, "AIRouter")


def test_ast_is_stdlib_only():
    """Document AST: no Qt, no backends — parse imports with ast."""
    import ast as _ast
    f = SRC / "documents" / "ast.py"
    tree = _ast.parse(f.read_text(encoding="utf-8"))
    mods = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"dataclasses", "__future__"}, mods


def test_pdf_backend_never_in_domain():
    import ast as _ast
    for f in _texts("domain"):
        tree = _ast.parse(f.read_text(encoding="utf-8"))
        src = _ast.dump(tree)
        assert "Stirling" not in src and "subprocess" not in src and "PyMuPDF" not in src, f
