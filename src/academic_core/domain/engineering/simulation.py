"""Simulation boundary (Phase 6 & 7): models, interfaces, results, and signals.

F7-A provides execution infrastructure (NgSpiceBackend).
F7-B1 introduces scientific simulation models:
- Signal (node voltages, branch currents, units, axes, Decimal + float samples)
- SimulationResult (scientific result with signals, provenance, raw references)
- SimulationJob (builds analysis decks from netlists/circuits)
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Signal:
    """Scientific representation of a simulated electrical variable.

    Maintains separation between domain Decimal precision and solver IEEE 754 float precision.
    """
    name: str  # e.g. "v(out)", "i(v1)"
    unit: str  # e.g. "V", "A"
    axis: str  # "voltage", "current"
    samples: tuple[Decimal, ...] = ()
    raw_samples: tuple[float, ...] = ()

    @property
    def value(self) -> Decimal | None:
        """Single-point scalar value (for DC operating point analyses)."""
        return self.samples[0] if self.samples else None

    @property
    def raw_value(self) -> float | None:
        """Raw IEEE 754 float representation directly from solver."""
        return self.raw_samples[0] if self.raw_samples else None


@dataclass(frozen=True)
class SimulationResult:
    """Scientific result of a circuit simulation.

    Preserves backward compatibility with Phase 6 while providing scientific signals,
    execution metadata, error reporting, and CAS raw artifact references.
    """
    backend: str
    netlist_digest: str
    analyses: tuple  # e.g. ("op",)
    data: dict  # legacy/compat backend-defined payload e.g. {"V(NET2)": "5.0"}
    mocked: bool = False
    signals: dict[str, Signal] = field(default_factory=dict)
    status: str = "COMPLETED"  # COMPLETED | FAILED | TIMEOUT | CANCELLED
    exit_code: int | None = 0
    duration_seconds: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    raw_artifact_hash: str = ""
    raw_stdout: str = ""
    raw_stderr: str = ""
    provenance: dict = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    def get_signal(self, name: str) -> Signal | None:
        """Case-insensitive lookup for signals by name e.g. 'v(out)' or 'V(OUT)'."""
        target = name.strip().lower()
        for k, v in self.signals.items():
            if k.lower() == target:
                return v
        return None

    def voltage(self, node: str) -> Decimal | None:
        """Convenience accessor for node voltages, e.g. voltage('out') or voltage('v(out)')."""
        node_clean = node.strip().lower()
        if node_clean.startswith("v(") and node_clean.endswith(")"):
            name = node_clean
        else:
            name = f"v({node_clean})"
        sig = self.get_signal(name)
        return sig.value if sig else None

    def current(self, source: str) -> Decimal | None:
        """Convenience accessor for source branch currents, e.g. current('v1') or current('i(v1)')."""
        src_clean = source.strip().lower()
        if src_clean.startswith("i(") and src_clean.endswith(")"):
            name = src_clean
        elif src_clean.endswith("#branch"):
            name = f"i({src_clean[:-7]})"
        else:
            name = f"i({src_clean})"
        sig = self.get_signal(name)
        if sig:
            return sig.value
        # Fallback to source#branch name directly
        sig2 = self.get_signal(f"{src_clean}#branch")
        return sig2.value if sig2 else None


@dataclass(frozen=True)
class SimulationJob:
    """Simulation job connecting a Circuit and/or netlist to an execution request."""
    netlist: str
    analyses: tuple[str, ...] = ("op",)
    circuit: Any = None

    def build_netlist(self) -> str:
        """Inject requested analyses into netlist before .end."""
        lines = self.netlist.strip().splitlines()
        end_idx = None
        for i, l in enumerate(lines):
            if l.strip().lower() == ".end":
                end_idx = i
                break

        analysis_commands = []
        for a in self.analyses:
            an = a.strip().lower()
            if an == "op":
                analysis_commands.append(".op")
            elif not an.startswith("."):
                analysis_commands.append(f".{an}")
            else:
                analysis_commands.append(an)

        existing = {l.strip().lower() for l in lines}
        to_add = [cmd for cmd in analysis_commands if cmd.lower() not in existing]

        if end_idx is not None:
            new_lines = lines[:end_idx] + to_add + lines[end_idx:]
        else:
            new_lines = lines + to_add + [".end"]

        return "\n".join(new_lines) + "\n"


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
        """Run analyses and return scientific SimulationResult."""


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
        digest = hashlib.sha256(netlist.encode()).hexdigest()
        signals = {}
        for k, v in self.payload.items():
            k_lower = k.lower()
            unit = "V" if k_lower.startswith("v") else ("A" if k_lower.startswith("i") else "")
            axis = "voltage" if unit == "V" else ("current" if unit == "A" else "other")
            try:
                dec = Decimal(str(v))
                flt = float(v)
            except Exception:
                dec = Decimal(0)
                flt = 0.0
            signals[k_lower] = Signal(k_lower, unit, axis, (dec,), (flt,))
        return SimulationResult(self.name, digest, tuple(analyses),
                                dict(self.payload), mocked=True, signals=signals)
