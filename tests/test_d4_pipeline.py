# SPDX-License-Identifier: MIT
"""D4: el pipeline CI es reproducible, sin bypasses y detecta fallos.

Solo stdlib. Sin red. Sin tocar el árbol del repo (tmp_path + cwd aislado).
El subprocess se usa SOLO aquí como harness (argv exacto, sin shell),
igual que el harness de certificación F4.1/F4.2.
"""

import py_compile
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _run_pytest(where: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
         "--rootdir", str(where), "-q", *args, str(where)],
        capture_output=True, text=True, cwd=where, shell=False, timeout=120)


def test_workflow_exists_and_triggers_on_main():
    assert WORKFLOW.is_file()
    text = _text()
    assert "pull_request" in text and "push" in text
    assert re.search(r"branches:\s*\[main\]", text)


def test_runners_are_pinned_not_floating():
    code = "\n".join(ln for ln in _text().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#"))
    assert "ubuntu-24.04" in code and "windows-2025" in code
    assert "ubuntu-latest" not in code and "windows-latest" not in code


def test_no_silent_bypasses_in_workflow():
    code = "\n".join(ln for ln in _text().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#"))
    for bypass in ("|| true", "continue-on-error", "exit 0", "--deselect",
                   "if: always()", "-m \"not slow\""):
        assert bypass not in code, f"bypass prohibido: {bypass}"
    assert "fail-fast: true" in code


def test_install_is_reproducible_and_pinned():
    lock = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    rows = [ln.strip() for ln in lock.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    assert rows, "lock vacío"
    assert all("==" in r for r in rows), "toda fila del lock debe pinear =="
    names = {re.split(r"[=<>!;\s]", r, maxsplit=1)[0].lower() for r in rows}
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in req.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-r")):
            want = re.split(r"[=<>!;\s]", line, maxsplit=1)[0].lower()
            assert want in names, f"{want} sin pin en lock"
    assert "requirements-lock.txt" in _text(), "CI debe instalar desde el lock"
    with (ROOT / "pyproject.toml").open("rb") as fh:
        py = tomllib.load(fh)
    assert py["project"]["name"] == "academic-core"
    assert py["project"]["requires-python"] == ">=3.11,<3.15"
    assert py["project"]["scripts"]["academic-core"] == "academic_core.app:main"
    assert py["build-system"]["build-backend"] == "setuptools.build_meta"


def test_pytest_executes_and_reports(tmp_path):
    case = tmp_path / "test_ok.py"
    case.write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    proc = _run_pytest(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout


def test_failing_tests_fail_the_pipeline(tmp_path):
    case = tmp_path / "test_bad.py"
    case.write_text("def test_bad():\n    assert False, 'boom'\n", encoding="utf-8")
    proc = _run_pytest(tmp_path)
    assert proc.returncode != 0
    assert "1 failed" in proc.stdout


def test_static_check_compiles_all_sources(tmp_path):
    out = tmp_path / "bytecode"
    out.mkdir()
    for src in sorted((ROOT / "src").rglob("*.py")):
        assert py_compile.compile(str(src), cfile=str(
            out / (src.stem + ".pyc")), doraise=True)
    assert "compileall" in _text()
    assert "python -m build" in _text(), "CI debe verificar el build"


def test_env_exceptions_are_explicit_and_minimal():
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "collect_ignore" not in src
    assert src.count("add_marker") == 2, "solo 2 excepciones ambientales"
    for node in ("test_f3_golden.py::TestGolden::test_html_corpus",
                 "test_f4_security.py::test_document_symlink_escape_refused"):
        assert node in src, f"excepción sin node id exacto: {node}"
    assert "xfail" in src and "strict=True" in src and "skip" in src
    assert "linux" in src and "symlink" in src


def test_checkouts_are_lf_deterministic():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in attrs, "golden byte-comparados exigen checkout LF"


def test_no_unwanted_artifacts_in_worktree():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("*.db", ".pytest_cache/", "build/", "dist/", "__pycache__/"):
        assert entry in ignore, f".gitignore debe cubrir {entry}"
    assert not (ROOT / "dist").exists(), "dist/ no debe existir en el árbol"
    assert not (ROOT / "build").exists(), "build/ no debe existir en el árbol"
