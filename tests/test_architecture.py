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
    violations = []
    for sub in ("application", "infrastructure", "storage", "config", "engines"):
        for f in _texts(sub):
            text = f.read_text(encoding="utf-8")
            if "PySide6" in text:
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


def test_engines_do_not_import_each_other_circularly():
    import academic_core.engines as e
    assert hasattr(e, "PDFService") and hasattr(e, "AIRouter")
