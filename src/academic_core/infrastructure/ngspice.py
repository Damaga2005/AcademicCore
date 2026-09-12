"""Controlled ngspice runtime integration (F7-A).

This module is deliberately infrastructure-only. It executes one external
binary with structured arguments in a private temporary workspace. It does
not parse scientific results; that is F7-B.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from academic_core.domain.engineering.simulation import SimulationBackend

NGSPICE_VERSION = "47"
HEALTH_NETLIST = """* AcademicCore F7-A health check
V1 in 0 1
R1 in 0 1k
.op
.control
op
quit
.endc
.end
"""


class RuntimeErrorF7A(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeInfo:
    backend: str
    executable_path: str
    version: str
    detection_method: str
    available: bool
    verified: bool
    verification_details: str
    platform: str
    timestamp: str


@dataclass(frozen=True)
class SimulationExecution:
    status: str  # QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED/TIMEOUT
    backend_id: str
    backend_version: str
    executable_path: str
    started_at: str
    finished_at: str
    duration_seconds: float
    exit_code: int | None
    stdout: str
    stderr: str
    workspace: str
    command_metadata: tuple
    timeout_seconds: float
    cancelled: bool = False
    input_hash: str = ""


class NgSpiceBackend(SimulationBackend):
    name = "ngspice"

    def __init__(self, executable: str = "", timeout_seconds: float = 30.0,
                 workspace_base: str | Path | None = None):
        self.configured_executable = executable
        self.timeout_seconds = float(timeout_seconds)
        self.workspace_base = Path(workspace_base) if workspace_base else None
        self._process: subprocess.Popen | None = None
        self._cancel_requested = threading.Event()

    def _candidates(self) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        if self.configured_executable:
            candidates.append((self.configured_executable, "configured"))
        path = shutil.which("ngspice") or shutil.which("ngspice.exe")
        if path:
            candidates.append((path, "PATH"))
        for root in (os.environ.get("ProgramFiles", ""),
                     os.environ.get("ProgramFiles(x86)", "")):
            if root:
                candidates.append((str(Path(root) / "ngspice" / "bin" / "ngspice.exe"),
                                   "known-install"))
        return candidates

    @staticmethod
    def _version_from_output(text: str) -> str:
        match = re.search(r"ngspice(?:[- ](?:version )?)(\d+(?:\.\d+)*)", text, re.I)
        return match.group(1) if match else "UNKNOWN"

    def detect(self) -> RuntimeInfo:
        for candidate, method in self._candidates():
            path = Path(candidate)
            if not path.is_file():
                continue
            try:
                proc = subprocess.run([str(path), "-v"], capture_output=True,
                                      text=True, timeout=min(self.timeout_seconds, 10),
                                      check=False)
                combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                version = self._version_from_output(combined)
                verified = proc.returncode == 0 and version != "UNKNOWN"
                return RuntimeInfo(self.name, str(path), version, method, True,
                                   verified, f"exit={proc.returncode}",
                                   platform.platform(), _now())
            except (OSError, subprocess.TimeoutExpired) as exc:
                return RuntimeInfo(self.name, str(path), "UNKNOWN", method, True,
                                   False, str(exc), platform.platform(), _now())
        return RuntimeInfo(self.name, "", "UNKNOWN", "not-found", False, False,
                           "ngspice executable not found", platform.platform(), _now())

    def capabilities(self) -> tuple[str, ...]:
        return ("detect", "version", "validate_runtime", "prepare", "run",
                "cancel", "cleanup", "health-check")

    def version(self) -> str:
        return self.detect().version

    def validate_runtime(self) -> RuntimeInfo:
        info = self.detect()
        if not info.available:
            raise RuntimeErrorF7A(info.verification_details)
        if not info.verified:
            raise RuntimeErrorF7A(f"runtime not verified: {info.verification_details}")
        return info

    def prepare(self, netlist: str, prefix: str = "run") -> Path:
        if "\x00" in netlist:
            raise ValueError("NUL in netlist")
        root = self.workspace_base
        workspace = Path(tempfile.mkdtemp(prefix=f"academic-core-{prefix}-", dir=root))
        (workspace / "input.cir").write_text(netlist, encoding="ascii", errors="strict")
        return workspace

    def validate(self, netlist: str) -> list[str]:
        return ["empty netlist"] if not netlist.strip() else []

    def cancel(self) -> bool:
        self._cancel_requested.set()
        proc = self._process
        if proc and proc.poll() is None:
            _terminate(proc)
            return True
        return False

    def cleanup(self, workspace: str | Path) -> None:
        path = Path(workspace)
        if path.exists() and path.is_dir():
            shutil.rmtree(path, ignore_errors=False)

    def run(self, netlist: str, keep_workspace: bool = False) -> SimulationExecution:
        issues = self.validate(netlist)
        if issues:
            raise ValueError("; ".join(issues))
        info = self.validate_runtime()
        workspace = self.prepare(netlist, "simulation")
        input_hash = hashlib.sha256(netlist.encode("ascii")).hexdigest()
        started = _now()
        began = time.monotonic()
        self._cancel_requested.clear()
        command = (info.executable_path, "-b", "-o", "output.log", "input.cir")
        status = "FAILED"
        code: int | None = None
        stdout = stderr = ""
        try:
            self._process = subprocess.Popen(
                list(command), cwd=str(workspace), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, shell=False)
            try:
                stdout, stderr = self._process.communicate(timeout=self.timeout_seconds)
                code = self._process.returncode
                status = "CANCELLED" if self._cancel_requested.is_set() \
                    else ("COMPLETED" if code == 0 else "FAILED")
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or ""
                stderr = exc.stderr or ""
                _terminate(self._process)
                stdout2, stderr2 = self._process.communicate()
                stdout += stdout2 or ""
                stderr += stderr2 or ""
                code = self._process.returncode
                status = "TIMEOUT"
        finally:
            self._process = None
            finished = _now()
            duration = time.monotonic() - began
            if not keep_workspace:
                self.cleanup(workspace)
        return SimulationExecution(status, self.name, info.version,
                                    info.executable_path, started, finished,
                                    duration, code, stdout, stderr,
                                    str(workspace), command[1:], self.timeout_seconds,
                                    status == "CANCELLED", input_hash)

    def health_check(self, keep_workspace: bool = False) -> SimulationExecution:
        return self.run(HEALTH_NETLIST, keep_workspace=keep_workspace)

    def simulate(self, netlist: str, analyses: tuple = ("health",)) -> SimulationExecution:
        """F7-A compatibility entry point; scientific parsing is F7-B."""
        return self.run(netlist)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
