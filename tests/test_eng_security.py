"""Engineering security: malicious expressions, injection, traversal, malformed."""
import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain.engineering import simulation as S
from academic_core.domain.engineering.circuit import Circuit, CircuitError
from academic_core.domain.engineering.equations import EquationError
from academic_core.domain.engineering.units import UnitError


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_expression_attacks_rejected(tmp_path):
    core = _app(tmp_path)
    attacks = [
        "__import__('os').system('id')", "open('/etc/passwd').read()",
        "V.__class__.__base__", "eval('1+1')", "V; import os",
        "V `id`", "V @ R", "lambda: 1",
    ]
    for evil in attacks:
        with pytest.raises((EquationError, UnitError)):
            core.engineering.calculate({"V": "5 V", "R": "1 kohm"}, f"X = {evil}")


def test_netlist_injection_rejected(tmp_path):
    core = _app(tmp_path)
    core.engineering.create_project("p")
    with pytest.raises(CircuitError):
        Circuit.from_netlist("R1 IN OUT 10kohm\nR1 OUT 0 1kohm\n.end")
    with pytest.raises(CircuitError):
        Circuit.from_netlist("BAD LINE WITHOUT ENOUGH\n.end")
    with pytest.raises(CircuitError):
        Circuit.from_netlist("R1 IN OUT 10kohm extra-token junk junk\n.end")


def test_simulation_never_executes():
    null = S.NullSimulationBackend()
    assert null.detect() is False
    assert null.validate("* x\n.end") == ["no simulation backend installed (F7)"]
    with pytest.raises(RuntimeError):
        null.simulate("* x\n.end")
    mock = S.MockSimulationBackend()
    assert mock.detect() is True
    res = mock.simulate("* x\n.end", ("op",))
    assert res.mocked is True and res.data == {"V(NET2)": "5.0"}
    import inspect
    import academic_core.domain.engineering.simulation as mod
    src = inspect.getsource(mod)
    assert "subprocess" not in src and "Popen" not in src and "os.system" not in src


def test_no_eval_exec_subprocess_in_engineering():
    import inspect
    import academic_core.domain.engineering.equations as eq
    import academic_core.domain.engineering.calc as calc
    import academic_core.domain.engineering.circuit as ckt
    import academic_core.domain.engineering.units as units
    for mod in (eq, calc, ckt, units):
        src = inspect.getsource(mod)
        assert "eval(" not in src, mod
        assert "exec(" not in src, mod
        assert "subprocess" not in src, mod
        assert "shell=True" not in src, mod


def test_numeric_overflow_controlled(tmp_path):
    core = _app(tmp_path)
    with pytest.raises(Exception):
        core.engineering.calculate({"V": "5 V", "R": "0 ohm"}, "I = V / R")
    with pytest.raises(Exception):
        core.engineering.calculate({"V": "5 XX"}, "I = V / R")
