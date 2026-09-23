# SPDX-License-Identifier: MIT
"""F4.1 M8 — security, D2 and architecture gates for every F4.1 file."""
import ast
import os
import re
import sqlite3
from pathlib import Path

import pytest

import gestion_legacy_fixture as G
from academic_core.errors import F41_ERROR_CODES

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
F41_FILES = [SRC / p for p in (
    "domain/career.py", "domain/evaluation.py", "domain/course_material.py",
    "domain/planning.py", "application/academic_mgmt.py", "application/calendar.py",
    "application/knowledge.py", "application/gestion_migration.py",
    "application/gestion_oracle.py", "application/ids.py", "infrastructure/academic_store.py",
    "infrastructure/ics.py", "infrastructure/legacy_gestion.py", "documents/syllabus.py",
    "infrastructure/migrations/012_academic_f41.sql")]
PY = [p for p in F41_FILES if p.suffix == ".py"]
F41_DOMAIN = [p for p in PY if p.parent.name == "domain"]


def _tree(p: Path) -> ast.AST:
    return ast.parse(p.read_text(encoding="utf-8"), str(p))


def test_all_f41_files_exist():
    assert all(p.is_file() for p in F41_FILES)


@pytest.mark.parametrize("path", PY, ids=lambda p: p.name)
def test_no_dangerous_calls(path):
    bad = []
    for n in ast.walk(_tree(path)):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in ("eval", "exec", "compile", "__import__"):
                bad.append(f"{f.id}@{n.lineno}")  # builtins (re.compile is fine)
            if isinstance(f, ast.Attribute) and f.attr in ("system", "popen", "import_module",
                                                           "spawnl", "execv"):
                bad.append(f"{f.attr}@{n.lineno}")
            for kw in n.keywords:
                if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                    bad.append(f"shell=True@{n.lineno}")
    assert bad == []


@pytest.mark.parametrize("path", PY, ids=lambda p: p.name)
def test_no_unsafe_or_network_imports(path):
    forbidden = {"pickle", "marshal", "shelve", "subprocess", "socket", "urllib", "http",
                 "requests", "ftplib", "smtplib", "flask", "sqlalchemy", "PySide6", "ctypes"}
    for n in ast.walk(_tree(path)):
        mods = [a.name for a in n.names] if isinstance(n, ast.Import) else (
            [n.module or ""] if isinstance(n, ast.ImportFrom) else [])
        for m in mods:
            assert m.split(".")[0] not in forbidden, f"{path.name}: {m}"


@pytest.mark.parametrize("path", F41_DOMAIN, ids=lambda p: p.name)
def test_f41_domain_is_pure(path):
    allowed_stdlib = {"__future__", "dataclasses", "datetime", "decimal", "enum", "re",
                      "typing"}
    for n in ast.walk(_tree(path)):
        if isinstance(n, ast.ImportFrom):
            m = n.module or ""
            assert m.split(".")[0] in allowed_stdlib or m.startswith(
                ("academic_core.domain", "academic_core.errors")), f"{path.name}: {m}"
        elif isinstance(n, ast.Import):
            for a in n.names:
                assert a.name.split(".")[0] in allowed_stdlib, f"{path.name}: {a.name}"


@pytest.mark.parametrize("path", PY, ids=lambda p: p.name)
def test_no_new_silent_except_pass(path):
    for n in ast.walk(_tree(path)):
        if isinstance(n, ast.ExceptHandler):
            assert not (len(n.body) == 1 and isinstance(n.body[0], ast.Pass)), (
                f"{path.name}:{n.lineno} silent except/pass")


def test_sql_is_parameterized_in_f41_repositories():
    """f-strings in execute() may only interpolate '?' placeholder lists."""
    for p in (SRC / "infrastructure/academic_store.py",
              SRC / "application/gestion_migration.py"):
        for n in ast.walk(_tree(p)):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("execute", "executemany") and n.args
                    and isinstance(n.args[0], ast.JoinedStr)):
                names = {v.value.id for v in n.args[0].values
                         if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name)}
                assert names <= {"marks"}, f"{p.name}:{n.lineno} interpolates {names}"


def test_legacy_reader_only_interpolates_allowlisted_identifiers():
    """SQL identifiers in the legacy reader come from the constant TABLES
    tuple (``t``) or from PRAGMA output via ``_pk_order``; never user text."""
    seen = 0
    for n in ast.walk(_tree(SRC / "infrastructure/legacy_gestion.py")):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "execute" and n.args and isinstance(n.args[0], ast.JoinedStr)):
            for v in n.args[0].values:
                if isinstance(v, ast.FormattedValue):
                    seen += 1
                    node = v.value
                    name = (node.id if isinstance(node, ast.Name) else
                            node.func.id if isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Name) else "")
                    assert name in {"t", "table", "_pk_order"}, ast.dump(node)
    assert seen >= 2


def test_error_codes_unique_and_documented():
    doc = (ROOT / "docs" / "specs" / "ERROR-CODES.md").read_text(encoding="utf-8")
    table = re.findall(r"^\| (AC-[A-Z]{2,3}-\d{3}) \|", doc, re.M)
    assert len(table) == len(set(table)), "duplicate code rows in ERROR-CODES.md"
    for code in F41_ERROR_CODES:
        assert code in table, f"{code} not documented"
    used = set()
    for p in PY + [SRC / "application/backup.py"]:
        used |= set(re.findall(r'"(AC-[A-Z]{2,3}-\d{3})"', p.read_text(encoding="utf-8")))
    assert used <= set(table), used - set(table)


def test_d2_errors_are_single_root():
    from academic_core.application.backup import ArchiveRejected
    from academic_core.errors import (AcademicCoreError, AcademicManagementError,
                                      MigrationError, to_ui_error)
    from academic_core.infrastructure.ics import IcsError
    from academic_core.infrastructure.legacy_gestion import UnsafePathError
    for cls in (AcademicManagementError, MigrationError, IcsError, UnsafePathError,
                ArchiveRejected):
        assert issubclass(cls, AcademicCoreError)
        ui = to_ui_error(cls("secret /home/user/x.db", code=cls.code))
        assert ui.error_code == cls.code and "/home/user" not in ui.safe_message


def test_legacy_source_connection_is_read_only(tmp_path):
    from academic_core.infrastructure.legacy_gestion import LegacyGestionSource
    db, _ = G.build(tmp_path / "l", docs=False)
    cx = LegacyGestionSource(db)._connect()
    with pytest.raises(sqlite3.OperationalError):
        cx.execute("DELETE FROM asignatura")
    cx.close()


@pytest.mark.parametrize("rel", ["../x", "/etc/passwd", "C:/Windows/x", "a/../../b",
                                 "a\\..\\..\\b", "x\x00y", ""])
def test_document_path_traversal_refused(tmp_path, rel):
    from academic_core.infrastructure.legacy_gestion import UnsafePathError, resolve_document
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(UnsafePathError) as e:
        resolve_document(root, rel, 10)
    assert e.value.code == "AC-SEC-002"


def test_document_symlink_escape_refused(tmp_path):
    from academic_core.infrastructure.legacy_gestion import UnsafePathError, resolve_document
    root = tmp_path / "root"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("s")
    os.symlink(secret, root / "link.txt")
    with pytest.raises(UnsafePathError):
        resolve_document(root, "link.txt", 10)
    (root / "big.bin").write_bytes(b"x" * 11)
    with pytest.raises(UnsafePathError):
        resolve_document(root, "big.bin", 10)


def test_transcript_csv_neutralises_formulas(tmp_path):
    from academic_core.application import AcademicApp
    from academic_core.application.academic_mgmt import csv_safe
    from academic_core.config import Settings
    from academic_core.domain import entities as E
    assert [csv_safe(v) for v in ("=1+1", "+SUM(A1)", "-2+3", "@cmd", "\tx", "ok", -2)] == [
        "'=1+1", "'+SUM(A1)", "'-2+3", "'@cmd", "'\tx", "ok", "-2"]
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "d")
    core = AcademicApp(Settings.load())
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y", "Y", "degree:g"))
    ac.add_term(E.Term("term:t", "=HYPERLINK(\"http://x\")", "cuatrimestre", 1, "year:y"))
    ac.add_subject(E.Subject("subject:x", "", "=cmd|' /C calc'!A0", "X", term_id="term:t",
                             final_grade="7"))
    csv_text = core.career.transcript_csv()
    row = csv_text.splitlines()[1]
    assert "'=cmd" in row and "'=HYPERLINK" in row and ",7," not in row
    assert row.endswith(",aprobada,7")
