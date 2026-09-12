"""Engineering persistence: projects/circuits/calculations save/reopen/migrate."""
from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.units import parse_quantity as Q
from academic_core.infrastructure import IntegrityError
import pytest


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _divider():
    c = Circuit("divisor")
    c.add(Component("V1", "V", Q("5 V"), {"+": "IN", "-": "0"}))
    c.add(Component("R1", "R", Q("10 kohm"), {"1": "IN", "2": "OUT"}))
    c.add(Component("R2", "R", Q("10 kohm"), {"1": "OUT", "2": "0"}))
    return c


def test_project_circuit_roundtrip_and_reopen(tmp_path):
    core = _app(tmp_path)
    core.engineering.create_project("lab1")
    assert core.engineering.save_circuit("lab1", _divider()) == []
    assert core.engineering.netlist("lab1", "divisor").startswith("* divisor")
    core2 = _app(tmp_path)
    back = core2.engineering.repo.load_circuit("lab1", "divisor")
    assert back.to_netlist() == _divider().to_netlist()
    assert [p.name for p in core2.engineering.repo.list_projects()] == ["lab1"]


def test_calculation_persisted_and_reproducible(tmp_path):
    core = _app(tmp_path)
    core.engineering.create_project("lab1")
    r = core.engineering.calculate({"V": "5 V", "R": "1 kohm"}, "I = V / R",
                                    project="lab1", name="I")
    rows = core.engineering.repo.calculations_of("lab1")
    assert len(rows) == 1 and rows[0]["digest"] == r.digest
    assert rows[0]["value"] == "0.005" and rows[0]["unit"] == "A"
    assert core.engineering.repo.get_calculation(r.digest)["equation"] == "I = V / R"


def test_project_delete_guarded(tmp_path):
    core = _app(tmp_path)
    core.engineering.create_project("lab1")
    core.engineering.save_circuit("lab1", _divider())
    with pytest.raises(IntegrityError):
        core.engineering.repo.delete_project("lab1")
    core.engineering.repo.delete_circuit("lab1", "divisor")
    core.engineering.repo.delete_project("lab1")
    assert core.engineering.repo.list_projects() == []


def test_duplicate_project_rejected(tmp_path):
    core = _app(tmp_path)
    core.engineering.create_project("lab1")
    with pytest.raises(ValueError):
        core.engineering.create_project("lab1")


def test_migration_010_present(tmp_path):
    import sqlite3
    core = _app(tmp_path)
    vers = [r[0] for r in sqlite3.connect(core.db.path).execute(
        "SELECT version FROM schema_version ORDER BY version")]
    assert 10 in vers
