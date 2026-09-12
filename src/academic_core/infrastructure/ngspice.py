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

from academic_core.domain.engineering.simulation import (
    SimulationBackend, SimulationJob, SimulationResult,
)

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

    def __bool__(self) -> bool:
        return self.available and self.verified


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


class NgSpiceDiscovery:
    """Discovers and inspects ngspice runtime binaries independently of backend execution."""

    @staticmethod
    def parse_version(text: str) -> str:
        match = re.search(r"ngspice(?:[- ](?:version )?)(\d+(?:\.\d+)*)", text, re.I)
        return match.group(1) if match else "UNKNOWN"

    @classmethod
    def candidates(cls, configured: str = "") -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(path_str: str, method: str) -> None:
            if not path_str:
                return
            p = Path(path_str)
            if not p.is_file():
                return
            try:
                norm = str(p.resolve()).lower()
            except OSError:
                norm = str(p).lower()
            if norm in seen:
                return
            seen.add(norm)
            candidates.append((str(p), method))

        # 1. Explicitly configured executable (or directory)
        if configured:
            p = Path(configured)
            if p.is_file():
                # In Windows, if pointed to GUI ngspice.exe, prefer headless console binary if alongside
                if p.name.lower() == "ngspice.exe":
                    con_peer = p.with_name("ngspice_con.exe")
                    if con_peer.is_file():
                        add(str(con_peer), "configured-console")
                add(str(p), "configured")
            elif p.is_dir():
                add(str(p / "ngspice_con.exe"), "configured-dir-console")
                add(str(p / "ngspice.exe"), "configured-dir")
                add(str(p / "bin" / "ngspice_con.exe"), "configured-bin-console")
                add(str(p / "bin" / "ngspice.exe"), "configured-bin")
            else:
                candidates.append((configured, "configured"))
            return candidates

        # 2. Environment variables: ACORE_NGSPICE_PATH, NGSPICE_PATH
        for env_var in ("ACORE_NGSPICE_PATH", "NGSPICE_PATH"):
            val = os.environ.get(env_var, "").strip()
            if val:
                vp = Path(val)
                if vp.is_file():
                    if vp.name.lower() == "ngspice.exe":
                        add(str(vp.with_name("ngspice_con.exe")), f"env:{env_var}-console")
                    add(str(vp), f"env:{env_var}")
                elif vp.is_dir():
                    add(str(vp / "ngspice_con.exe"), f"env:{env_var}-console")
                    add(str(vp / "ngspice.exe"), f"env:{env_var}")
                    add(str(vp / "bin" / "ngspice_con.exe"), f"env:{env_var}-bin-console")
                    add(str(vp / "bin" / "ngspice.exe"), f"env:{env_var}-bin")

        # 3. Settings configuration (simulation.ngspice_path)
        try:
            from academic_core.config.settings import Settings
            cfg_path = Settings.load().simulation.ngspice_path
            if cfg_path and cfg_path != configured:
                cp = Path(cfg_path)
                if cp.is_file():
                    if cp.name.lower() == "ngspice.exe":
                        add(str(cp.with_name("ngspice_con.exe")), "settings-console")
                    add(str(cp), "settings")
                elif cp.is_dir():
                    add(str(cp / "ngspice_con.exe"), "settings-dir-console")
                    add(str(cp / "ngspice.exe"), "settings-dir")
                    add(str(cp / "bin" / "ngspice_con.exe"), "settings-bin-console")
                    add(str(cp / "bin" / "ngspice.exe"), "settings-bin")
        except Exception:
            pass

        # 4. PATH lookup: on Windows prefer ngspice_con.exe (headless console)
        con_path = shutil.which("ngspice_con") or shutil.which("ngspice_con.exe")
        if con_path:
            add(con_path, "PATH-console")
        std_path = shutil.which("ngspice") or shutil.which("ngspice.exe")
        if std_path:
            sp = Path(std_path)
            if sp.name.lower() == "ngspice.exe":
                add(str(sp.with_name("ngspice_con.exe")), "PATH-peer-console")
            add(std_path, "PATH")

        # 5. Standard Windows drives and install roots (e.g. C:\Spice64\bin)
        win_roots = ["C:\\", "D:\\"]
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            val = os.environ.get(env_name)
            if val:
                win_roots.append(val)

        for root_str in win_roots:
            root = Path(root_str)
            for folder in ("Spice64", "Spice", "ngspice"):
                add(str(root / folder / "bin" / "ngspice_con.exe"), "standard-install-console")
                add(str(root / folder / "bin" / "ngspice.exe"), "standard-install")
                add(str(root / folder / "ngspice_con.exe"), "standard-install-console")
                add(str(root / folder / "ngspice.exe"), "standard-install")

        # 6. User home directories (Documents, Downloads) where official archives are unpacked
        try:
            home = Path.home()
            for sub in ("Documents", "Downloads", "Desktop", ""):
                base = home / sub if sub else home
                if not base.exists():
                    continue
                add(str(base / "Spice64" / "bin" / "ngspice_con.exe"), "user-install-console")
                add(str(base / "Spice64" / "bin" / "ngspice.exe"), "user-install")
                try:
                    for match in base.glob("ngspice*/Spice64/bin/ngspice_con.exe"):
                        add(str(match), "user-archive-console")
                    for match in base.glob("ngspice*/Spice64/bin/ngspice.exe"):
                        add(str(match), "user-archive")
                    for match in base.glob("ngspice*/bin/ngspice_con.exe"):
                        add(str(match), "user-archive-console")
                    for match in base.glob("ngspice*/bin/ngspice.exe"):
                        add(str(match), "user-archive")
                except OSError:
                    pass
        except Exception:
            pass

        return candidates

    @classmethod
    def batch_probe(cls, path: Path, method: str, timeout_seconds: float = 15.0) -> RuntimeInfo:
        with tempfile.TemporaryDirectory(prefix="academic-core-ngspice-probe-") as tmp:
            work = Path(tmp)
            (work / "input.cir").write_text(HEALTH_NETLIST, encoding="ascii")
            try:
                probe = subprocess.run(
                    [str(path), "-b", "-o", "probe.log", "input.cir"],
                    cwd=str(work), capture_output=True, text=True,
                    timeout=min(timeout_seconds, 15.0), check=False)
                log_file = work / "probe.log"
                log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""
                combined = (probe.stdout or "") + "\n" + (probe.stderr or "") + "\n" + log_text
                version = cls.parse_version(combined)
                verified = probe.returncode == 0 and version != "UNKNOWN"
                return RuntimeInfo(
                    "ngspice", str(path), version, method, True,
                    verified, f"batch_probe_exit={probe.returncode}",
                    platform.platform(), _now())
            except (OSError, subprocess.TimeoutExpired) as exc:
                return RuntimeInfo("ngspice", str(path), "UNKNOWN", method, True,
                                   False, str(exc), platform.platform(), _now())

    @classmethod
    def detect(cls, configured: str = "", timeout_seconds: float = 30.0) -> RuntimeInfo:
        for candidate, method in cls.candidates(configured):
            path = Path(candidate)
            if not path.is_file():
                continue
            try:
                proc = subprocess.run(
                    [str(path), "-v"], capture_output=True,
                    text=True, timeout=min(timeout_seconds, 10.0), check=False)
                combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
                version = cls.parse_version(combined)
                verified = proc.returncode == 0 and version != "UNKNOWN"
                if verified:
                    return RuntimeInfo("ngspice", str(path), version, method, True,
                                       True, f"exit={proc.returncode}",
                                       platform.platform(), _now())
                return cls.batch_probe(path, method, timeout_seconds)
            except (OSError, subprocess.TimeoutExpired) as exc:
                # If -v times out (e.g. GUI binary waiting for interactive loop),
                # fallback to batch probe to verify batch execution capabilities.
                probe_res = cls.batch_probe(path, method, timeout_seconds)
                if probe_res.verified:
                    return probe_res
                return RuntimeInfo("ngspice", str(path), "UNKNOWN", method, True,
                                   False, str(exc), platform.platform(), _now())
        return RuntimeInfo("ngspice", "", "UNKNOWN", "not-found", False, False,
                           "ngspice executable not found", platform.platform(), _now())


class NgSpiceBackend(SimulationBackend):
    name = "ngspice"

    def __init__(self, executable: str = "", timeout_seconds: float = 30.0,
                 workspace_base: str | Path | None = None):
        self.configured_executable = executable
        self.timeout_seconds = float(timeout_seconds)
        self.workspace_base = Path(workspace_base) if workspace_base else None
        self._process: subprocess.Popen | None = None
        self._cancel_requested = threading.Event()
        self._runtime_info: RuntimeInfo | None = None

    # Static delegations for backwards compatibility
    _candidates = staticmethod(NgSpiceDiscovery.candidates)
    _version_from_output = staticmethod(NgSpiceDiscovery.parse_version)

    def detect(self) -> RuntimeInfo:
        info = NgSpiceDiscovery.detect(self.configured_executable, self.timeout_seconds)
        if info.verified:
            self._runtime_info = info
        return info

    def capabilities(self) -> tuple[str, ...]:
        return ("detect", "version", "validate_runtime", "prepare", "run",
                "cancel", "cleanup", "health-check")

    def version(self) -> str:
        return self.detect().version

    def validate_runtime(self) -> RuntimeInfo:
        if self._runtime_info and self._runtime_info.verified:
            return self._runtime_info
        info = self.detect()
        if not info.available:
            raise RuntimeErrorF7A(info.verification_details)
        if not info.verified:
            raise RuntimeErrorF7A(f"runtime not verified: {info.verification_details}")
        self._runtime_info = info
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
        command = (info.executable_path, "-b", "-o", "output.log", "input.cir")
        status = "FAILED"
        code: int | None = None
        stdout = stderr = ""
        try:
            self._process = subprocess.Popen(
                list(command), cwd=str(workspace), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, shell=False)
            if self._cancel_requested.is_set():
                _terminate(self._process)
            try:
                stdout, stderr = self._process.communicate(timeout=self.timeout_seconds)
                code = self._process.returncode
                log_path = workspace / "output.log"
                if log_path.is_file():
                    # Batch mode writes log details to the -o file; include in stdout capture
                    file_output = log_path.read_text(encoding="utf-8", errors="replace")
                    stdout = (stdout or "") + ("\n" if stdout else "") + file_output
                status = "CANCELLED" if self._cancel_requested.is_set() \
                    else ("COMPLETED" if code == 0 else "FAILED")
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or ""
                stderr = exc.stderr or ""
                _terminate(self._process)
                try:
                    stdout2, stderr2 = self._process.communicate(timeout=2.0)
                    stdout += stdout2 or ""
                    stderr += stderr2 or ""
                except Exception:
                    pass
                log_path = workspace / "output.log"
                if log_path.is_file():
                    file_output = log_path.read_text(encoding="utf-8", errors="replace")
                    stdout = (stdout or "") + ("\n" if stdout else "") + file_output
                code = self._process.returncode
                status = "CANCELLED" if self._cancel_requested.is_set() else "TIMEOUT"
        finally:
            self._process = None
            self._cancel_requested.clear()
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

    def simulate(self, netlist: str, analyses: tuple = ("op",), cas_store=None) -> SimulationResult:
        """Run scientific simulation (DC, Transient, AC, Noise, Sensitivity, Monte Carlo)."""
        from academic_core.domain.engineering.simulation import MonteCarloAnalysis, run_monte_carlo
        from academic_core.infrastructure.ngspice_parser import parse_ngspice_op

        for a in analyses:
            if isinstance(a, MonteCarloAnalysis):
                return run_monte_carlo(netlist, a, self, cas_store=cas_store)

        job = SimulationJob(netlist, analyses=analyses)
        deck = job.build_netlist()
        execution = self.run(deck)
        return parse_ngspice_op(execution, netlist=deck, cas_store=cas_store, analyses=analyses)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
            proc.wait(timeout=2)
        except OSError:
            pass
