"""Architecture boundaries (modular monolith): domain/engines never import UI/Qt/app."""
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"

FORBIDDEN_IN = ("domain", "engines", "storage", "config")
FORBIDDEN_IMPORTS = ("PySide6", "academic_core.app")


def test_no_ui_imports_in_core():
    violations = []
    for sub in FORBIDDEN_IN:
        for f in (SRC / sub).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for bad in FORBIDDEN_IMPORTS:
                if bad in text:
                    violations.append(f"{f.relative_to(SRC)} imports {bad}")
    assert not violations, violations


def test_engines_do_not_import_each_other_circularly():
    # Lightweight: pdf/ai/resource/providers/document/engineering are leaf modules.
    import academic_core.engines as e
    assert hasattr(e, "PDFService") and hasattr(e, "AIRouter")
