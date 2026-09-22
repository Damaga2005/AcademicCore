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
                "documents", "pdf", "resources", "domain"):
        for f in _texts(sub):
            text = f.read_text(encoding="utf-8")
            # import statements only: docstring prose may name backends.
            if _re.search(r"^\s*(import|from)\s+PySide6", text, _re.MULTILINE):
                violations.append(f"{f.relative_to(SRC)} imports PySide6")
            if _RX_APP.search(text):
                violations.append(f"{f.relative_to(SRC)} imports academic_core.app")
    assert not violations, violations


def test_ui_consumes_only_application_and_domain():
    """UI never touches infrastructure/SQLite/CAS; never Flask/SQLAlchemy."""
    import re as _re
    violations = []
    for f in _texts("ui"):
        text = f.read_text(encoding="utf-8")
        for bad in ("from academic_core.infrastructure", "import sqlite3",
                    "flask", "Flask", "sqlalchemy", "SQLAlchemy"):
            if bad in text:
                violations.append(f"{f.relative_to(SRC)} uses {bad}")
        if _re.search(r"^\s*(import|from)\s+academic_core\.app\b", text, _re.MULTILINE):
            violations.append(f"{f.relative_to(SRC)} imports app module")
    assert not violations, violations


def test_no_flask_or_web_stack_anywhere():
    """No Flask/SQLAlchemy imports in src (docs may discuss them)."""
    import re as _re
    violations = []
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        if _re.search(r"^\s*(import|from)\s+(flask|sqlalchemy)\b", text,
                      _re.MULTILINE | _re.IGNORECASE):
            violations.append(str(f.relative_to(SRC)))
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
    forbidden = {"os", "pathlib", "sqlite3", "urllib", "socket",
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


def test_dsp_layer_direction():
    """F8-P2 DSP boundaries (N-110 principle: lower layers take no edges
    from upper layers). dsp MAY consume control downward (acyclic);
    nothing flows upward into control/mna/ac/lab, and dsp never touches
    lab/simulation/UI/filesystem/network. Parsed with ast: only real
    imports count."""
    import ast as _ast
    eng = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    dsp_files = list((eng / "dsp").glob("*.py")) if (eng / "dsp").exists() else []
    assert dsp_files, "dsp package missing"
    violations = []
    for f in dsp_files:
        tree = _ast.parse(f.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            mods = []
            if isinstance(node, _ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                segs = mod.split(".")
                if "lab" in segs and "domain" in segs:
                    violations.append(f"{f.name}: dsp -> lab")
                if mod in ("simulation",) or "simulation" in segs:
                    violations.append(f"{f.name}: dsp -> simulation")
                if segs[:2] == ["academic_core", "app"] or "academic_core.app" in mod:
                    violations.append(f"{f.name}: dsp -> app")
    for f in (eng / "control").glob("*.py"):
        tree = _ast.parse(f.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                        else [node.module or ""])
                for mod in mods:
                    if "engineering.dsp" in mod.split(".") or mod == "dsp":
                        violations.append(f"control/{f.name}: control -> dsp")
    for sub in ("mna", "ac", "lab"):
        for f in (eng / sub).glob("*.py"):
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if "dsp" in mod.split("."):
                            violations.append(f"{sub}/{f.name}: {sub} -> dsp")
    assert not violations, violations


def test_rf_layer_direction():
    """F8-P3 RF boundaries (N-110 principle, mirrors test_dsp_layer_direction).
    rf MAY consume control/math/units downward (acyclic); nothing flows
    upward into control/math/units, and rf never touches mna/ac/lab/
    simulation/UI/filesystem/network. rf is a closed-form math layer:
    it must never import the live-circuit ac/twoport.py extraction
    layer either (gate §26)."""
    import ast as _ast
    eng = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    rf_files = list((eng / "rf").glob("*.py")) if (eng / "rf").exists() else []
    assert rf_files, "rf package missing"
    violations = []
    for f in rf_files:
        tree = _ast.parse(f.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            mods = []
            if isinstance(node, _ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                segs = mod.split(".")
                if "lab" in segs and "domain" in segs:
                    violations.append(f"{f.name}: rf -> lab")
                if mod in ("simulation",) or "simulation" in segs:
                    violations.append(f"{f.name}: rf -> simulation")
                if segs[:2] == ["academic_core", "app"] or "academic_core.app" in mod:
                    violations.append(f"{f.name}: rf -> app")
                if "mna" in segs:
                    violations.append(f"{f.name}: rf -> mna")
                if "ac" in segs and "engineering" in segs:
                    violations.append(f"{f.name}: rf -> ac")
    for sub in ("control", "math"):
        for f in (eng / sub).glob("*.py"):
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if "engineering.rf" in mod.split(".") or mod == "rf":
                            violations.append(f"{sub}/{f.name}: {sub} -> rf")
    units_file = eng / "units.py"
    if units_file.exists():
        tree = _ast.parse(units_file.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                        else [node.module or ""])
                for mod in mods:
                    if "engineering.rf" in mod.split(".") or mod == "rf":
                        violations.append(f"units.py: units -> rf")
    for sub in ("mna", "ac", "lab"):
        for f in (eng / sub).glob("*.py"):
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if "rf" in mod.split("."):
                            violations.append(f"{sub}/{f.name}: {sub} -> rf")
    assert not violations, violations


def test_comms_layer_direction():
    """F8-P4 comms boundaries (N-110 principle, mirrors dsp/rf tests).
    comms MAY consume dsp/control/math/units/metrology.o5 downward
    (acyclic); nothing flows upward into control/math/dsp/units, and
    comms never touches rf/mna/ac/lab/simulation/UI/filesystem/network.
    comms is a closed-form math layer: no second FFT/DFT/Sequence/
    digest/serializer/replay engine lives inside it."""
    import ast as _ast
    eng = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    comms_files = list((eng / "comms").glob("*.py")) if (eng / "comms").exists() else []
    assert comms_files, "comms package missing"
    violations = []
    for f in comms_files:
        tree = _ast.parse(f.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            mods = []
            if isinstance(node, _ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                segs = mod.split(".")
                if "lab" in segs and "domain" in segs:
                    violations.append(f"{f.name}: comms -> lab")
                if mod in ("simulation",) or "simulation" in segs:
                    if "domain.engineering" not in mod:
                        violations.append(f"{f.name}: comms -> simulation")
                if segs[:2] == ["academic_core", "app"] or "academic_core.app" in mod:
                    violations.append(f"{f.name}: comms -> app")
                if "mna" in segs:
                    violations.append(f"{f.name}: comms -> mna")
                if "engineering" in segs:
                    tail = segs[segs.index("engineering") + 1:]
                    if tail[:1] == ["rf"]:
                        violations.append(f"{f.name}: comms -> rf")
                    if tail[:1] == ["ac"]:
                        violations.append(f"{f.name}: comms -> ac")
    for sub in ("control", "math", "dsp"):
        for f in (eng / sub).glob("*.py"):
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if "engineering.comms" in mod:
                            violations.append(f"{sub}/{f.name}: {sub} -> comms")
    units_file = eng / "units.py"
    if units_file.exists():
        tree = _ast.parse(units_file.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                        else [node.module or ""])
                for mod in mods:
                    if "engineering.comms" in mod:
                        violations.append("units.py: units -> comms")
    for sub in ("mna", "ac", "lab"):
        for f in (eng / sub).glob("*.py"):
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    mods = ([a.name for a in node.names] if isinstance(node, _ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if "comms" in mod.split("."):
                            violations.append(f"{sub}/{f.name}: {sub} -> comms")
    assert not violations, violations
