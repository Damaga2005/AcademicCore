"""Simulation boundary (Phase 6): interface ONLY. Simulation = NOT IMPLEMENTED.

F7 will provide real backends behind this interface. F6 ships NullBackend
(unavailable) and MockBackend (prefixed results, tests/demos). No external
no ngspice, no binaries — importing this module must never execute anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationResult:
    backend: str
    netlist_digest: str
    analyses: tuple  # e.g. ("op",)
    data: dict  # backend-defined payload
    mocked: bool = False


class SimulationBackend(ABC):
    name: str = ""

    @abstractmethod
    def detect(self) -> bool:
        """True when the backend could run here (binaries, runtime, license)."""

    @abstractmethod
    def validate(self, netlist: str) -> list[str]:
        """Backend-side input checks. Returns issues (empty = accepted)."""

    @abstractmethod
    def simulate(self, netlist: str, analyses: tuple = ("op",)) -> SimulationResult:
        """Run analyses. F6 backends never execute external processes."""


class NullSimulationBackend(SimulationBackend):
    name = "null"

    def detect(self) -> bool:
        return False

    def validate(self, netlist: str) -> list[str]:
        return ["no simulation backend installed (F7)"]

    def simulate(self, netlist: str, analyses: tuple = ("op",)) -> SimulationResult:
        raise RuntimeError("simulation is NOT IMPLEMENTED in F6 (see F7)")


class MockSimulationBackend(SimulationBackend):
    """Prefixed results for tests and UI demos. Clearly marked mocked."""

    name = "mock"

    def __init__(self, payload: dict | None = None):
        self.payload = dict(payload or {"V(NET2)": "5.0"})

    def detect(self) -> bool:
        return True

    def validate(self, netlist: str) -> list[str]:
        return [] if netlist.strip() else ["empty netlist"]

    def simulate(self, netlist: str, analyses: tuple = ("op",)) -> SimulationResult:
        import hashlib
        digest = hashlib.sha256(netlist.encode()).hexdigest()
        return SimulationResult(self.name, digest, tuple(analyses),
                                dict(self.payload), mocked=True)
