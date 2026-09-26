# SPDX-License-Identifier: MIT
"""D5 contratos de suite: seguridad AST sobre ficheros F13-ext/D4 y markers.

F13EXT-SYNC.md §9 afirma verificación AST; las listas F41/F42 no cubren
los ficheros F13-ext/D4. Este fichero cierra ese hueco sin tocar tests
certificados. También fija: markers usados ⊆ registrados, y que los
tests de presupuesto temporal llevan marca `perf` explícita.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"

# Ficheros F13-ext + D4 con contrato "sin ejecución dinámica" (lista
# explícita; añadir aquí cualquier fichero nuevo con el mismo contrato).
SYNC_D4 = [SRC / p for p in (
    "domain/sync.py",
    "application/sync.py",
    "infrastructure/sync_store.py",
    "infrastructure/sync_transport.py",
    "application/facade.py",
    "infrastructure/__init__.py",
    "infrastructure/database.py",
)]
SYNC_D4_TESTS = [ROOT / "tests" / p for p in (
    "conftest.py",
    "test_d4_pipeline.py",
    "test_f13ext_sync.py",
    "test_f13ext_service.py",
    "test_d5_contracts.py",
)]

BUILTIN_MARKS = {"parametrize", "skip", "skipif", "xfail", "usefixtures",
                 "filterwarnings"}
PERF_FILES = ["tests/test_perf.py", "tests/test_academic_perf.py",
              "tests/test_perf_f5.py"]


def _tree(p: Path) -> ast.AST:
    return ast.parse(p.read_text(encoding="utf-8"), str(p))


def _registered_marks() -> set[str]:
    marks = set()
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*"([a-z]+):', line)
        if m:
            marks.add(m.group(1))
    return marks


def test_sync_d4_files_exist():
    assert all(p.is_file() for p in SYNC_D4 + SYNC_D4_TESTS)


def test_sync_d4_no_dangerous_calls():
    bad = []
    for path in SYNC_D4 + [p for p in SYNC_D4_TESTS if p.suffix == ".py"]:
        for n in ast.walk(_tree(path)):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in (
                        "eval", "exec", "compile", "__import__"):
                    bad.append(f"{path.name}:{n.lineno}:{f.id}")
                for kw in n.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                        bad.append(f"{path.name}:{n.lineno}:shell=True")
    assert bad == []


def test_sync_d4_no_unsafe_or_network_imports():
    forbidden = {"pickle", "marshal", "shelve", "subprocess", "socket",
                 "urllib", "http", "requests", "flask", "sqlalchemy",
                 "PySide6", "ctypes", "os", "threading"}
    # os/threading: prohibidos aquí (el motor sync es puro; el transporte
    # usa pathlib, no os). `os` sí aparece en tests ajenos: no es este test.
    bad = []
    for path in [SRC / "domain/sync.py", SRC / "application/sync.py",
                 SRC / "infrastructure/sync_store.py",
                 SRC / "infrastructure/sync_transport.py"]:
        for n in ast.walk(_tree(path)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else (
                [n.module or ""] if isinstance(n, ast.ImportFrom) else [])
            for m in mods:
                if m.split(".")[0] in forbidden:
                    bad.append(f"{path.name}:{m}")
    assert bad == []


def test_domain_sync_is_pure():
    """domain/sync.py: stdlib + domain/entities; nada de app/infra/Qt."""
    mods: set[str] = set()
    for n in ast.walk(_tree(SRC / "domain/sync.py")):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "datetime", "decimal", "enum",
                    "hashlib", "json", "re", "typing", "academic_core"}, mods


def test_all_used_marks_are_registered():
    used: set[str] = set()
    for p in (ROOT / "tests").glob("test_*.py"):
        for m in re.finditer(r"pytest\.mark\.([A-Za-z_]\w*)",
                             p.read_text(encoding="utf-8")):
            if m.group(1) not in BUILTIN_MARKS:
                used.add(m.group(1))
    assert used <= _registered_marks(), used - _registered_marks()
    assert "perf" in _registered_marks(), "marker perf sin registrar"


def test_perf_tests_carry_perf_marker():
    for rel in PERF_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "pytestmark = pytest.mark.perf" in text, rel


def test_arch_and_repro_markers_are_used():
    assert "pytestmark = pytest.mark.arch" in (
        ROOT / "tests/test_architecture.py").read_text(encoding="utf-8")
    assert "pytestmark = pytest.mark.repro" in (
        ROOT / "tests/test_reproducibility.py").read_text(encoding="utf-8")
