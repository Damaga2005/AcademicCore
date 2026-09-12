"""F7-A unit tests: no ngspice required, no fake is runtime evidence."""
from pathlib import Path

import pytest

from academic_core.infrastructure.ngspice import (
    HEALTH_NETLIST, NgSpiceBackend, RuntimeInfo,
)


def test_missing_runtime_is_structured(tmp_path):
    b = NgSpiceBackend(str(tmp_path / "missing-ngspice.exe"), timeout_seconds=1)
    info = b.detect()
    assert (info.available, info.verified, info.detection_method) == (False, False, "not-found")
    with pytest.raises(RuntimeError):
        b.validate_runtime()


def test_prepare_workspace_isolated_and_cleanup(tmp_path):
    b = NgSpiceBackend(workspace_base=tmp_path)
    ws = b.prepare(HEALTH_NETLIST, "unit")
    assert ws.parent == tmp_path and (ws / "input.cir").read_text(encoding="ascii") == HEALTH_NETLIST
    b.cleanup(ws)
    assert not ws.exists()


def test_netlist_validation_and_nul():
    b = NgSpiceBackend()
    assert b.validate("") == ["empty netlist"]
    assert b.validate("* ok\n.end") == []
    with pytest.raises(ValueError):
        b.prepare("bad\x00netlist")


def test_runtime_version_parsing():
    assert NgSpiceBackend._version_from_output("ngspice-47\n").startswith("47")
    assert NgSpiceBackend._version_from_output("ngspice version 46.2") == "46.2"
    assert NgSpiceBackend._version_from_output("nothing") == "UNKNOWN"


class FakeProcess:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.killed = False

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def terminate(self):
        self.killed = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode


def test_run_capture_success_with_patched_process(monkeypatch, tmp_path):
    b = NgSpiceBackend(str(tmp_path / "ngspice.exe"), workspace_base=tmp_path)
    # Unit-only: discovery and process are patched. This is NOT real ngspice evidence.
    exe = tmp_path / "ngspice.exe"
    exe.write_text("unit placeholder", encoding="ascii")
    monkeypatch.setattr(b, "validate_runtime", lambda: RuntimeInfo(
        "ngspice", str(exe), "47", "unit", True, True, "patched",
        "Windows", "now"))
    proc = FakeProcess()
    monkeypatch.setattr("academic_core.infrastructure.ngspice.subprocess.Popen",
                        lambda *a, **k: proc)
    result = b.run(HEALTH_NETLIST)
    assert result.status == "COMPLETED"
    assert result.exit_code == 0 and result.stdout == "ok"
    assert not Path(result.workspace).exists()
    assert result.input_hash


def test_run_failure_is_not_success(monkeypatch, tmp_path):
    b = NgSpiceBackend(str(tmp_path / "ngspice.exe"), workspace_base=tmp_path)
    exe = tmp_path / "ngspice.exe"
    exe.write_text("unit placeholder", encoding="ascii")
    monkeypatch.setattr(b, "validate_runtime", lambda: RuntimeInfo(
        "ngspice", str(exe), "47", "unit", True, True, "patched",
        "Windows", "now"))
    monkeypatch.setattr("academic_core.infrastructure.ngspice.subprocess.Popen",
                        lambda *a, **k: FakeProcess(1, "", "bad netlist"))
    result = b.run("* invalid\n.end")
    assert result.status == "FAILED" and result.exit_code == 1
    assert result.stderr == "bad netlist"


def test_timeout_status_and_termination(monkeypatch, tmp_path):
    import subprocess

    class Slow(FakeProcess):
        def poll(self):
            return None if not self.killed else 1

        def communicate(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("ngspice", timeout, output="partial")
            return "", ""

    b = NgSpiceBackend(str(tmp_path / "ngspice.exe"), workspace_base=tmp_path)
    exe = tmp_path / "ngspice.exe"
    exe.write_text("unit placeholder", encoding="ascii")
    monkeypatch.setattr(b, "validate_runtime", lambda: RuntimeInfo(
        "ngspice", str(exe), "47", "unit", True, True, "patched",
        "Windows", "now"))
    proc = Slow()
    monkeypatch.setattr("academic_core.infrastructure.ngspice.subprocess.Popen",
                        lambda *a, **k: proc)
    result = b.run(HEALTH_NETLIST)
    assert result.status == "TIMEOUT" and proc.killed


def test_cancel_before_run_is_safe(tmp_path):
    assert NgSpiceBackend(workspace_base=tmp_path).cancel() is False


@pytest.mark.external
@pytest.mark.integration
def test_external_ngspice_integration_is_separate():
    b = NgSpiceBackend()
    info = b.detect()
    if not info.available:
        pytest.skip("ngspice not installed: real integration unavailable")
    result = b.health_check()
    assert result.status == "COMPLETED"
