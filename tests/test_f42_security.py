# SPDX-License-Identifier: MIT
"""F4.2 security/AST gates: no eval/exec/pickle/subprocess/network, SQL safe."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
F42 = [SRC / p for p in (
    "domain/planning.py",
    "application/search_history.py",
    "application/notify.py",
    "application/personal.py",
    "application/f42_legacy.py",
    "infrastructure/academic_store.py",
    "infrastructure/migrations/014_f42_search_history.sql",
)]
PY = [p for p in F42 if p.suffix == ".py"]


def _tree(p: Path) -> ast.AST:
    return ast.parse(p.read_text(encoding="utf-8"), str(p))


def test_all_f42_files_exist():
    assert all(p.is_file() for p in F42)


def test_no_dangerous_calls():
    bad = []
    for path in PY:
        for n in ast.walk(_tree(path)):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in (
                        "eval", "exec", "compile", "__import__"):
                    bad.append(f"{path.name}:{f.id}@{n.lineno}")
                if isinstance(f, ast.Attribute) and f.attr in (
                        "system", "popen", "import_module", "spawnl", "execv"):
                    bad.append(f"{path.name}:{f.attr}@{n.lineno}")
                for kw in n.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                        bad.append(f"{path.name}:shell=True@{n.lineno}")
    assert bad == []


def test_no_unsafe_or_network_imports():
    forbidden = {"pickle", "marshal", "shelve", "subprocess", "socket", "urllib",
                 "http", "requests", "ftplib", "smtplib", "flask", "sqlalchemy",
                 "PySide6", "ctypes"}
    for path in PY:
        for n in ast.walk(_tree(path)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else (
                [n.module or ""] if isinstance(n, ast.ImportFrom) else [])
            for m in mods:
                assert m.split(".")[0] not in forbidden, f"{path.name}: {m}"


def test_no_silent_except_pass():
    for path in PY:
        for n in ast.walk(_tree(path)):
            if isinstance(n, ast.ExceptHandler):
                assert not (len(n.body) == 1 and isinstance(n.body[0], ast.Pass)), (
                    f"{path.name}:{n.lineno} silent except/pass")


def test_sql_is_parameterized():
    for path in (SRC / "infrastructure/academic_store.py",):
        for n in ast.walk(_tree(path)):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("execute", "executemany") and n.args
                    and isinstance(n.args[0], ast.JoinedStr)):
                names = {v.value.id for v in n.args[0].values
                         if isinstance(v, ast.FormattedValue)
                         and isinstance(v.value, ast.Name)}
                # `marks` is only ever a run of "?" placeholders (precedent).
                assert names <= {"marks"}, f"{path.name}:{n.lineno} interpolates {names}"
