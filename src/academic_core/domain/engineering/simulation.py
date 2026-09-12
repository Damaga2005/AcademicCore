"""Simulation boundary (Phase 6 & 7): models, interfaces, results, and signals.

F7-A provides execution infrastructure (NgSpiceBackend).
F7-B1 introduces scientific simulation models:
- Signal (node voltages, branch currents, units, axes, Decimal + float samples)
- SimulationResult (scientific result with signals, provenance, raw references)
- SimulationJob (builds analysis decks from netlists/circuits)
F7-B2 adds DC Sweep analysis:
- DCSweepAnalysis (source, start, stop, step, validation)
- Multi-point Signal support (samples sequence, sweep_axis, points_count)
F7-B3 adds Transient analysis:
- TransientAnalysis (tstep, tstop, tstart, tmax, uic, validation)
- Time axis Signal support (time_axis, sample_at, multi-point time series)
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

_SPICE_SUFFIXES: dict[str, Decimal] = {
    "t": Decimal("1e12"),
    "g": Decimal("1e9"),
    "meg": Decimal("1e6"),
    "k": Decimal("1e3"),
    "m": Decimal("1e-3"),
    "u": Decimal("1e-6"),
    "n": Decimal("1e-9"),
    "p": Decimal("1e-12"),
    "f": Decimal("1e-15"),
}


def parse_spice_number(text: str | int | float | Decimal) -> Decimal:
    """Parse a numerical value or SPICE-syntax string with optional engineering suffixes to Decimal.

    Supports:
    - Standard Decimal/float/int representations
    - SPICE engineering suffixes: 't', 'g', 'meg', 'k', 'm', 'u', 'n', 'p', 'f'
    """
    if isinstance(text, Decimal):
        return text
    if isinstance(text, (int, float)):
        return Decimal(str(text))
    s = str(text).strip().lower()
    if not s:
        raise ValueError("empty number string")

    if s.endswith("meg"):
        val_str = s[:-3]
        try:
            return Decimal(val_str) * _SPICE_SUFFIXES["meg"]
        except Exception as exc:
            raise ValueError(f"invalid numerical string: {text!r}") from exc

    for suffix, multiplier in _SPICE_SUFFIXES.items():
        if suffix != "meg" and s.endswith(suffix):
            val_str = s[:-len(suffix)]
            try:
                return Decimal(val_str) * multiplier
            except Exception:
                pass

    try:
        return Decimal(s)
    except Exception as exc:
        raise ValueError(f"invalid numerical string: {text!r}") from exc


@dataclass(frozen=True)
class TransientAnalysis:
    """Specification for a Transient (.tran) analysis.

    Simulates circuit behavior over time from tstart (default 0) to tstop with step tstep.
    Optional tmax (maximum internal timestep) and uic (use initial conditions).
    """
    tstep: Decimal | str | float | int
    tstop: Decimal | str | float | int
    tstart: Decimal | str | float | int = Decimal(0)
    tmax: Decimal | str | float | int | None = None
    uic: bool = False

    def __post_init__(self):
        try:
            tstep_d = parse_spice_number(self.tstep)
            tstop_d = parse_spice_number(self.tstop)
            tstart_d = parse_spice_number(self.tstart)
            tmax_d = parse_spice_number(self.tmax) if self.tmax is not None else None
        except Exception as exc:
            raise ValueError(f"invalid numerical parameter for transient analysis: {exc}")

        object.__setattr__(self, "tstep", tstep_d)
        object.__setattr__(self, "tstop", tstop_d)
        object.__setattr__(self, "tstart", tstart_d)
        object.__setattr__(self, "tmax", tmax_d)
        object.__setattr__(self, "uic", bool(self.uic))

        if tstep_d <= 0:
            raise ValueError(f"transient step must be positive, got {tstep_d}")
        if tstop_d <= 0:
            raise ValueError(f"transient stop must be positive, got {tstop_d}")
        if tstart_d < 0:
            raise ValueError(f"transient start must be non-negative, got {tstart_d}")
        if tstop_d <= tstart_d:
            raise ValueError(f"transient stop ({tstop_d}) must be greater than start ({tstart_d})")
        if tmax_d is not None and tmax_d <= 0:
            raise ValueError(f"transient tmax must be positive, got {tmax_d}")

    def to_spice_card(self) -> str:
        """Generate SPICE .tran directive line."""
        uic_suffix = " uic" if self.uic else ""
        if self.tmax is not None:
            return f".tran {self.tstep} {self.tstop} {self.tstart} {self.tmax}{uic_suffix}"
        if self.tstart != 0:
            return f".tran {self.tstep} {self.tstop} {self.tstart}{uic_suffix}"
        return f".tran {self.tstep} {self.tstop}{uic_suffix}"

    @classmethod
    def from_string(cls, text: str) -> TransientAnalysis:
        """Parse from a line like '.tran 10u 5m' or 'tran 1e-5 0.005 0 1e-5 uic'."""
        cleaned = text.strip()
        if cleaned.lower().startswith(".tran"):
            cleaned = cleaned[5:].strip()
        elif cleaned.lower().startswith("tran"):
            cleaned = cleaned[4:].strip()
        parts = cleaned.split()
        if len(parts) < 2:
            raise ValueError(f"malformed transient directive: {text!r} (expected at least tstep and tstop)")

        uic = False
        if parts[-1].lower() == "uic":
            uic = True
            parts = parts[:-1]

        tstep = parse_spice_number(parts[0])
        tstop = parse_spice_number(parts[1])
        tstart = Decimal(0)
        tmax = None

        if len(parts) >= 3:
            tstart = parse_spice_number(parts[2])
        if len(parts) >= 4:
            tmax = parse_spice_number(parts[3])

        return cls(tstep=tstep, tstop=tstop, tstart=tstart, tmax=tmax, uic=uic)


@dataclass(frozen=True)
class DCSweepAnalysis:
    """Specification for a DC Sweep (.dc) analysis.

    Sweeps an independent voltage or current source over [start, stop] with step size step.
    Enforces parameter validation: non-empty source, non-zero step, sign consistency.
    """
    source: str
    start: Decimal
    stop: Decimal
    step: Decimal

    def __post_init__(self):
        if not self.source or not str(self.source).strip():
            raise ValueError("DC sweep source must not be empty")
        try:
            start_d = Decimal(str(self.start))
            stop_d = Decimal(str(self.stop))
            step_d = Decimal(str(self.step))
        except Exception as exc:
            raise ValueError(f"invalid numerical parameter for DC sweep: {exc}")

        object.__setattr__(self, "source", str(self.source).strip().upper())
        object.__setattr__(self, "start", start_d)
        object.__setattr__(self, "stop", stop_d)
        object.__setattr__(self, "step", step_d)

        if step_d == 0:
            raise ValueError("DC sweep step cannot be 0")
        if start_d < stop_d and step_d < 0:
            raise ValueError(f"increasing range ({start_d} to {stop_d}) requires positive step, got {step_d}")
        if start_d > stop_d and step_d > 0:
            raise ValueError(f"decreasing range ({start_d} to {stop_d}) requires negative step, got {step_d}")

    @property
    def expected_points(self) -> int:
        """Expected number of points in the sweep (inclusive)."""
        diff = self.stop - self.start
        return int(diff // self.step) + 1

    def to_spice_card(self) -> str:
        """Generate SPICE .dc directive line."""
        return f".dc {self.source} {self.start} {self.stop} {self.step}"

    @classmethod
    def from_string(cls, text: str) -> DCSweepAnalysis:
        """Parse from a line like '.dc V1 0 10 1' or 'dc V1 0 10 1'."""
        cleaned = text.strip()
        if cleaned.lower().startswith(".dc"):
            cleaned = cleaned[3:].strip()
        elif cleaned.lower().startswith("dc"):
            cleaned = cleaned[2:].strip()
        parts = cleaned.split()
        if len(parts) < 4:
            raise ValueError(f"malformed DC sweep directive: {text!r} (expected 4 tokens: source start stop step)")
        source = parts[0]
        start = Decimal(parts[1])
        stop = Decimal(parts[2])
        step = Decimal(parts[3])
        return cls(source=source, start=start, stop=stop, step=step)


@dataclass(frozen=True)
class Signal:
    """Scientific representation of a simulated electrical variable.

    Maintains separation between domain Decimal precision and solver IEEE 754 float precision.
    Supports single-point (.op) and multi-point (.dc sweep) sequences.
    """
    name: str  # e.g. "v(out)", "i(v1)", "v-sweep"
    unit: str  # e.g. "V", "A"
    axis: str  # "voltage", "current", "sweep"
    samples: tuple[Decimal, ...] = ()
    raw_samples: tuple[float, ...] = ()

    @property
    def value(self) -> Decimal | None:
        """Single-point scalar value (for DC operating point analyses or first point)."""
        return self.samples[0] if self.samples else None

    @property
    def raw_value(self) -> float | None:
        """Raw IEEE 754 float representation directly from solver (first point)."""
        return self.raw_samples[0] if self.raw_samples else None

    @property
    def is_multi_point(self) -> bool:
        return len(self.samples) > 1

    def __len__(self) -> int:
        return len(self.samples)


@dataclass(frozen=True)
class SimulationResult:
    """Scientific result of a circuit simulation.

    Preserves backward compatibility with Phase 6 while providing scientific signals,
    execution metadata, error reporting, and CAS raw artifact references.
    """
    backend: str
    netlist_digest: str
    analyses: tuple  # e.g. ("op",) or (DCSweepAnalysis(...),)
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

    @property
    def sweep_axis(self) -> Signal | None:
        """The primary sweep variable/axis Signal if present in the simulation."""
        for sig in self.signals.values():
            if sig.axis == "sweep":
                return sig
        for key in ("v-sweep", "i-sweep", "sweep"):
            if key in self.signals:
                return self.signals[key]
        return None

    @property
    def time_axis(self) -> Signal | None:
        """The primary time variable/axis Signal if present in the simulation."""
        for sig in self.signals.values():
            if sig.axis == "time":
                return sig
        if "time" in self.signals:
            return self.signals["time"]
        return None

    @property
    def points_count(self) -> int:
        """Number of points in the simulation result."""
        axis = self.time_axis or self.sweep_axis
        if axis and axis.samples:
            return len(axis.samples)
        for sig in self.signals.values():
            if sig.samples:
                return len(sig.samples)
        return 0

    def sample_at(self, signal_name: str, target: Decimal | float | str) -> Decimal | None:
        """Sample a signal value at or nearest to a specified time or sweep value."""
        sig = self.get_signal(signal_name)
        axis = self.time_axis or self.sweep_axis
        if not sig or not sig.samples or not axis or not axis.samples:
            return None
        target_d = parse_spice_number(target)
        best_idx = 0
        min_diff = abs(axis.samples[0] - target_d)
        for i, val in enumerate(axis.samples[1:], start=1):
            diff = abs(val - target_d)
            if diff < min_diff:
                min_diff = diff
                best_idx = i
        if best_idx < len(sig.samples):
            return sig.samples[best_idx]
        return None

    def voltage(self, node: str) -> Decimal | None:
        """Convenience accessor for node voltage scalar value (first/operating point)."""
        node_clean = node.strip().lower()
        if node_clean.startswith("v(") and node_clean.endswith(")"):
            name = node_clean
        else:
            name = f"v({node_clean})"
        sig = self.get_signal(name)
        return sig.value if sig else None

    def voltage_samples(self, node: str) -> tuple[Decimal, ...] | None:
        """Full sequence of node voltage samples across all sweep points."""
        node_clean = node.strip().lower()
        if node_clean.startswith("v(") and node_clean.endswith(")"):
            name = node_clean
        else:
            name = f"v({node_clean})"
        sig = self.get_signal(name)
        return sig.samples if sig else None

    def current(self, source: str) -> Decimal | None:
        """Convenience accessor for source branch current scalar value (first/operating point)."""
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
        sig2 = self.get_signal(f"{src_clean}#branch")
        return sig2.value if sig2 else None

    def current_samples(self, source: str) -> tuple[Decimal, ...] | None:
        """Full sequence of source branch current samples across all sweep points."""
        src_clean = source.strip().lower()
        if src_clean.startswith("i(") and src_clean.endswith(")"):
            name = src_clean
        elif src_clean.endswith("#branch"):
            name = f"i({src_clean[:-7]})"
        else:
            name = f"i({src_clean})"
        sig = self.get_signal(name)
        if sig:
            return sig.samples
        sig2 = self.get_signal(f"{src_clean}#branch")
        return sig2.samples if sig2 else None


@dataclass(frozen=True)
class SimulationJob:
    """Simulation job connecting a Circuit and/or netlist to an execution request."""
    netlist: str
    analyses: tuple[Any, ...] = ("op",)
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
        has_dc_sweep = False
        has_tran = False

        for a in self.analyses:
            if isinstance(a, DCSweepAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_dc_sweep = True
            elif isinstance(a, TransientAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_tran = True
            elif isinstance(a, str):
                an = a.strip()
                an_lower = an.lower()
                if an_lower == "op":
                    analysis_commands.append(".op")
                elif an_lower.startswith("dc ") or an_lower.startswith(".dc "):
                    # Validate via DCSweepAnalysis
                    sweep = DCSweepAnalysis.from_string(an)
                    analysis_commands.append(sweep.to_spice_card())
                    has_dc_sweep = True
                elif an_lower.startswith("tran ") or an_lower.startswith(".tran "):
                    # Validate via TransientAnalysis
                    tran = TransientAnalysis.from_string(an)
                    analysis_commands.append(tran.to_spice_card())
                    has_tran = True
                elif not an.startswith("."):
                    analysis_commands.append(f".{an}")
                else:
                    analysis_commands.append(an)

        existing = {l.strip().lower() for l in lines}
        to_add = [cmd for cmd in analysis_commands if cmd.lower() not in existing]

        # For DC sweep in batch mode, ngspice requires a .print dc card
        if has_dc_sweep:
            has_print_dc = any(l.strip().lower().startswith(".print dc") or l.strip().lower().startswith("print dc") for l in lines)
            if not has_print_dc:
                print_card = self._build_print_dc_card(lines)
                if print_card and print_card.lower() not in existing:
                    to_add.append(print_card)

        # For Transient in batch mode, ngspice requires a .print tran card
        if has_tran:
            has_print_tran = any(l.strip().lower().startswith(".print tran") or l.strip().lower().startswith("print tran") for l in lines)
            if not has_print_tran:
                print_card = self._build_print_tran_card(lines)
                if print_card and print_card.lower() not in existing:
                    to_add.append(print_card)

        if end_idx is not None:
            new_lines = lines[:end_idx] + to_add + lines[end_idx:]
        else:
            new_lines = lines + to_add + [".end"]

        return "\n".join(new_lines) + "\n"

    @staticmethod
    def _build_print_dc_card(lines: list[str]) -> str:
        """Inspect netlist to automatically construct a .print dc card with all circuit nets and sources."""
        nets: set[str] = set()
        sources: set[str] = set()
        for line in lines:
            l = line.strip()
            if not l or l.startswith("*") or l.startswith("."):
                continue
            parts = l.split()
            if not parts:
                continue
            ref = parts[0].upper()
            if ref.startswith("V") or ref.startswith("I"):
                sources.add(ref.lower())
                if len(parts) >= 3:
                    for n in parts[1:3]:
                        if n.lower() not in ("0", "gnd", "ground"):
                            nets.add(n.lower())
            elif len(parts) >= 3:
                for n in parts[1:3]:
                    if n.lower() not in ("0", "gnd", "ground"):
                        nets.add(n.lower())

        tokens = [f"v({n})" for n in sorted(nets)] + [f"i({s})" for s in sorted(sources)]
        if tokens:
            return f".print dc {' '.join(tokens)}"
        return ".print dc"

    @staticmethod
    def _build_print_tran_card(lines: list[str]) -> str:
        """Inspect netlist to automatically construct a .print tran card with all circuit nets and sources."""
        nets: set[str] = set()
        sources: set[str] = set()
        for line in lines:
            l = line.strip()
            if not l or l.startswith("*") or l.startswith("."):
                continue
            parts = l.split()
            if not parts:
                continue
            ref = parts[0].upper()
            if ref.startswith("V") or ref.startswith("I"):
                sources.add(ref.lower())
                if len(parts) >= 3:
                    for n in parts[1:3]:
                        if n.lower() not in ("0", "gnd", "ground"):
                            nets.add(n.lower())
            elif len(parts) >= 3:
                for n in parts[1:3]:
                    if n.lower() not in ("0", "gnd", "ground"):
                        nets.add(n.lower())

        tokens = [f"v({n})" for n in sorted(nets)] + [f"i({s})" for s in sorted(sources)]
        if tokens:
            return f".print tran {' '.join(tokens)}"
        return ".print tran"


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
            if isinstance(v, (list, tuple)):
                dec_tuple = tuple(Decimal(str(x)) for x in v)
                flt_tuple = tuple(float(x) for x in v)
            else:
                try:
                    dec_tuple = (Decimal(str(v)),)
                    flt_tuple = (float(v),)
                except Exception:
                    dec_tuple = (Decimal(0),)
                    flt_tuple = (0.0,)
            signals[k_lower] = Signal(k_lower, unit, axis, dec_tuple, flt_tuple)
        return SimulationResult(self.name, digest, tuple(analyses),
                                dict(self.payload), mocked=True, signals=signals)
