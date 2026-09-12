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
F7-B4 adds AC small-signal analysis:
- ACAnalysis (sweep_type DEC/OCT/LIN, points, fstart, fstop, validation)
- ComplexSignal (real, imag, magnitude, phase, dB, complex IEEE 754 float)
- Frequency axis Signal support (frequency_axis, sample_complex_at)
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

_SPICE_SUFFIXES: dict[str, Decimal] = {
    "t": Decimal("1000000000000"),
    "g": Decimal("1000000000"),
    "meg": Decimal("1000000"),
    "k": Decimal("1000"),
    "m": Decimal("0.001"),
    "u": Decimal("0.000001"),
    "n": Decimal("0.000000001"),
    "p": Decimal("0.000000000001"),
    "f": Decimal("0.000000000000001"),
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
class ACAnalysis:
    """Specification for an AC small-signal (.ac) analysis.

    Sweeps frequency with sweep_type: 'DEC' (decade), 'OCT' (octave), or 'LIN' (linear).
    Points: points per decade/octave, or total points for linear.
    Frequencies: fstart (start frequency in Hz) and fstop (stop frequency in Hz).
    """
    sweep_type: str  # "DEC" | "OCT" | "LIN"
    points: int
    fstart: Decimal | str | float | int
    fstop: Decimal | str | float | int

    def __post_init__(self):
        if not self.sweep_type or not str(self.sweep_type).strip():
            raise ValueError("AC sweep type must not be empty")
        st = str(self.sweep_type).strip().upper()
        if st not in ("DEC", "OCT", "LIN"):
            raise ValueError(f"invalid AC sweep type: {st!r} (expected 'DEC', 'OCT', or 'LIN')")

        try:
            pts = int(self.points)
        except Exception as exc:
            raise ValueError(f"invalid points parameter for AC analysis: {exc}")
        if pts <= 0:
            raise ValueError(f"AC points must be positive, got {pts}")

        try:
            fstart_d = parse_spice_number(self.fstart)
            fstop_d = parse_spice_number(self.fstop)
        except Exception as exc:
            raise ValueError(f"invalid frequency parameter for AC analysis: {exc}")

        if fstart_d <= 0:
            raise ValueError(f"AC start frequency must be positive, got {fstart_d}")
        if fstop_d <= fstart_d:
            raise ValueError(f"AC stop frequency ({fstop_d}) must be greater than start frequency ({fstart_d})")

        object.__setattr__(self, "sweep_type", st)
        object.__setattr__(self, "points", pts)
        object.__setattr__(self, "fstart", fstart_d)
        object.__setattr__(self, "fstop", fstop_d)

    def to_spice_card(self) -> str:
        """Generate SPICE .ac directive line."""
        def _fmt(d: Decimal) -> str:
            if d == d.to_integral():
                return str(int(d))
            s = f"{d:f}"
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s

        return f".ac {self.sweep_type.lower()} {self.points} {_fmt(self.fstart)} {_fmt(self.fstop)}"

    @classmethod
    def from_string(cls, text: str) -> ACAnalysis:
        """Parse from a line like '.ac dec 10 1 100k' or 'ac lin 50 100 10k'."""
        cleaned = text.strip()
        if cleaned.lower().startswith(".ac"):
            cleaned = cleaned[3:].strip()
        elif cleaned.lower().startswith("ac"):
            cleaned = cleaned[2:].strip()
        parts = cleaned.split()
        if len(parts) < 4:
            raise ValueError(f"malformed AC directive: {text!r} (expected 4 tokens: sweep_type points fstart fstop)")
        sweep_type = parts[0]
        points = int(parts[1])
        fstart = parse_spice_number(parts[2])
        fstop = parse_spice_number(parts[3])
        return cls(sweep_type=sweep_type, points=points, fstart=fstart, fstop=fstop)


@dataclass(frozen=True)
class NoiseAnalysis:
    """Specification for a Noise (.noise) small-signal analysis.

    Evaluates output noise and input-referred noise over a frequency sweep.
    Generates SPICE card: .noise <output_variable> <input_source> <sweep_type> <points> <fstart> <fstop>
    """
    output_variable: str  # e.g. "v(out)" or "V(OUT)"
    input_source: str     # e.g. "V1"
    sweep_type: str       # "DEC" | "OCT" | "LIN"
    points: int
    fstart: Decimal | str | float | int
    fstop: Decimal | str | float | int

    def __post_init__(self):
        if not self.output_variable or not str(self.output_variable).strip():
            raise ValueError("noise output variable must not be empty")
        if not self.input_source or not str(self.input_source).strip():
            raise ValueError("noise input source must not be empty")
        if not self.sweep_type or not str(self.sweep_type).strip():
            raise ValueError("noise sweep type must not be empty")
        st = str(self.sweep_type).strip().upper()
        if st not in ("DEC", "OCT", "LIN"):
            raise ValueError(f"invalid noise sweep type: {st!r} (expected 'DEC', 'OCT', or 'LIN')")

        try:
            pts = int(self.points)
        except Exception as exc:
            raise ValueError(f"invalid points parameter for noise analysis: {exc}")
        if pts <= 0:
            raise ValueError(f"noise points must be positive, got {pts}")

        try:
            fstart_d = parse_spice_number(self.fstart)
            fstop_d = parse_spice_number(self.fstop)
        except Exception as exc:
            raise ValueError(f"invalid frequency parameter for noise analysis: {exc}")

        if fstart_d <= 0:
            raise ValueError(f"noise start frequency must be positive, got {fstart_d}")
        if fstop_d <= fstart_d:
            raise ValueError(f"noise stop frequency ({fstop_d}) must be greater than start frequency ({fstart_d})")

        out_var = str(self.output_variable).strip()
        in_src = str(self.input_source).strip().upper()

        object.__setattr__(self, "output_variable", out_var)
        object.__setattr__(self, "input_source", in_src)
        object.__setattr__(self, "sweep_type", st)
        object.__setattr__(self, "points", pts)
        object.__setattr__(self, "fstart", fstart_d)
        object.__setattr__(self, "fstop", fstop_d)

    def to_spice_card(self) -> str:
        """Generate SPICE .noise directive line."""
        def _fmt(d: Decimal) -> str:
            if d == d.to_integral():
                return str(int(d))
            s = f"{d:f}"
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s

        return f".noise {self.output_variable} {self.input_source} {self.sweep_type.lower()} {self.points} {_fmt(self.fstart)} {_fmt(self.fstop)}"

    @classmethod
    def from_string(cls, text: str) -> NoiseAnalysis:
        """Parse from a line like '.noise v(out) V1 dec 10 1 100k' or 'noise v(out) v1 lin 50 100 10k'."""
        cleaned = text.strip()
        if cleaned.lower().startswith(".noise"):
            cleaned = cleaned[6:].strip()
        elif cleaned.lower().startswith("noise"):
            cleaned = cleaned[5:].strip()
        parts = cleaned.split()
        if len(parts) < 6:
            raise ValueError(f"malformed noise directive: {text!r} (expected 6 tokens: out_var in_source sweep_type points fstart fstop)")
        out_var = parts[0]
        in_src = parts[1]
        sweep_type = parts[2]
        points = int(parts[3])
        fstart = parse_spice_number(parts[4])
        fstop = parse_spice_number(parts[5])
        return cls(output_variable=out_var, input_source=in_src, sweep_type=sweep_type, points=points, fstart=fstart, fstop=fstop)


@dataclass(frozen=True)
class SensitivityAnalysis:
    """Specification for a Sensitivity (.sens) analysis.

    Evaluates DC or AC small-signal sensitivities of output_variable with respect to circuit components.
    Generates SPICE card:
      DC: .sens <output_variable>
      AC: .sens <output_variable> ac <sweep_type> <points> <fstart> <fstop>
    """
    output_variable: str  # e.g. "v(out)"
    analysis_type: str = "DC"  # "DC" | "AC"
    sweep_type: str = "DEC"    # "DEC" | "OCT" | "LIN" (when analysis_type is AC)
    points: int = 10           # (when analysis_type is AC)
    fstart: Decimal | str | float | int = Decimal(1)       # (when analysis_type is AC)
    fstop: Decimal | str | float | int = Decimal(100000)   # (when analysis_type is AC)
    parameters: tuple[str, ...] = ()  # Optional subset of parameters/components to print/evaluate

    def __post_init__(self):
        if not self.output_variable or not str(self.output_variable).strip():
            raise ValueError("sensitivity output variable must not be empty")
        an_type = str(self.analysis_type).strip().upper()
        if an_type not in ("DC", "AC"):
            raise ValueError(f"invalid sensitivity analysis type: {an_type!r} (expected 'DC' or 'AC')")

        st = str(self.sweep_type).strip().upper()
        if an_type == "AC":
            if st not in ("DEC", "OCT", "LIN"):
                raise ValueError(f"invalid AC sensitivity sweep type: {st!r} (expected 'DEC', 'OCT', or 'LIN')")
            try:
                pts = int(self.points)
            except Exception as exc:
                raise ValueError(f"invalid points parameter for AC sensitivity: {exc}")
            if pts <= 0:
                raise ValueError(f"sensitivity points must be positive, got {pts}")

            try:
                fstart_d = parse_spice_number(self.fstart)
                fstop_d = parse_spice_number(self.fstop)
            except Exception as exc:
                raise ValueError(f"invalid frequency parameter for AC sensitivity: {exc}")

            if fstart_d <= 0:
                raise ValueError(f"sensitivity start frequency must be positive, got {fstart_d}")
            if fstop_d <= fstart_d:
                raise ValueError(f"sensitivity stop frequency ({fstop_d}) must be greater than start frequency ({fstart_d})")
        else:
            pts = int(self.points) if self.points else 1
            fstart_d = Decimal(1)
            fstop_d = Decimal(100000)

        out_var = str(self.output_variable).strip()
        params = tuple(str(p).strip().lower() for p in self.parameters if str(p).strip())

        object.__setattr__(self, "output_variable", out_var)
        object.__setattr__(self, "analysis_type", an_type)
        object.__setattr__(self, "sweep_type", st)
        object.__setattr__(self, "points", pts)
        object.__setattr__(self, "fstart", fstart_d)
        object.__setattr__(self, "fstop", fstop_d)
        object.__setattr__(self, "parameters", params)

    def to_spice_card(self) -> str:
        """Generate SPICE .sens directive line."""
        if self.analysis_type == "DC":
            return f".sens {self.output_variable}"

        def _fmt(d: Decimal) -> str:
            if d == d.to_integral():
                return str(int(d))
            s = f"{d:f}"
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s

        return f".sens {self.output_variable} ac {self.sweep_type.lower()} {self.points} {_fmt(self.fstart)} {_fmt(self.fstop)}"

    @classmethod
    def from_string(cls, text: str) -> SensitivityAnalysis:
        """Parse from lines like '.sens v(out)', 'sens v(out)', or '.sens v(out) ac dec 10 1 100k'."""
        cleaned = text.strip()
        if cleaned.lower().startswith(".sens"):
            cleaned = cleaned[5:].strip()
        elif cleaned.lower().startswith("sens"):
            cleaned = cleaned[4:].strip()
        parts = cleaned.split()
        if not parts:
            raise ValueError(f"malformed sens directive: {text!r} (expected at least output variable)")
        out_var = parts[0]
        if len(parts) == 1:
            return cls(output_variable=out_var, analysis_type="DC")
        if len(parts) >= 2 and parts[1].lower() == "ac":
            if len(parts) < 6:
                raise ValueError(f"malformed AC sens directive: {text!r} (expected 6 tokens: out_var ac sweep_type points fstart fstop)")
            sweep_type = parts[2]
            points = int(parts[3])
            fstart = parse_spice_number(parts[4])
            fstop = parse_spice_number(parts[5])
            return cls(output_variable=out_var, analysis_type="AC", sweep_type=sweep_type, points=points, fstart=fstart, fstop=fstop)
        return cls(output_variable=out_var, analysis_type="DC")


class ParameterDistribution(ABC):
    """Abstract base class for circuit component parameter distributions."""

    @abstractmethod
    def sample(self, rng: random.Random) -> Decimal:
        """Sample a concrete parameter value as Decimal using the provided RNG instance."""

    @abstractmethod
    def validate(self) -> list[str]:
        """Validate distribution configuration. Returns empty list if valid, issues otherwise."""


@dataclass(frozen=True)
class UniformDistribution(ParameterDistribution):
    """Uniform continuous distribution for component parameters.

    Can be specified either via:
    1. nominal and tolerance_pct (e.g. nominal=1000, tolerance_pct=5 -> [950, 1050])
    2. explicit low and high bounds (e.g. low=950, high=1050, nominal=1000)
    """
    nominal: Decimal
    tolerance_pct: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None

    def __post_init__(self):
        nom_d = Decimal(str(self.nominal))
        tol_d = Decimal(str(self.tolerance_pct)) if self.tolerance_pct is not None else None
        low_d = Decimal(str(self.low)) if self.low is not None else None
        high_d = Decimal(str(self.high)) if self.high is not None else None

        if tol_d is not None:
            if tol_d < 0:
                raise ValueError(f"tolerance_pct must be non-negative, got {tol_d}")
            frac = tol_d / Decimal("100")
            if low_d is None:
                low_d = nom_d * (Decimal("1") - frac)
            if high_d is None:
                high_d = nom_d * (Decimal("1") + frac)
        else:
            if low_d is None:
                low_d = nom_d
            if high_d is None:
                high_d = nom_d

        if low_d > high_d:
            raise ValueError(f"distribution low ({low_d}) cannot exceed high ({high_d})")

        object.__setattr__(self, "nominal", nom_d)
        object.__setattr__(self, "tolerance_pct", tol_d)
        object.__setattr__(self, "low", low_d)
        object.__setattr__(self, "high", high_d)

    def validate(self) -> list[str]:
        issues = []
        if self.low is not None and self.high is not None and self.low > self.high:
            issues.append(f"low ({self.low}) > high ({self.high})")
        if self.tolerance_pct is not None and self.tolerance_pct < 0:
            issues.append(f"tolerance_pct ({self.tolerance_pct}) < 0")
        return issues

    def sample(self, rng: random.Random) -> Decimal:
        if self.low == self.high:
            return self.nominal
        u = Decimal(str(rng.random()))
        return self.low + (self.high - self.low) * u


@dataclass(frozen=True)
class NormalDistribution(ParameterDistribution):
    """Gaussian / Normal distribution for component parameters.

    Can be specified either via:
    1. nominal and std_dev
    2. nominal and tolerance_pct with sigma_coverage (std_dev = (nominal * tolerance_pct / 100) / sigma_coverage)
    Default sigma_coverage is 3.0 (meaning +-tolerance_pct covers 3*sigma or 99.73%).
    Optionally clamped between min_val and max_val.
    """
    nominal: Decimal
    std_dev: Decimal | None = None
    tolerance_pct: Decimal | None = None
    sigma_coverage: Decimal = Decimal("3.0")
    min_val: Decimal | None = None
    max_val: Decimal | None = None

    def __post_init__(self):
        nom_d = Decimal(str(self.nominal))
        cov_d = Decimal(str(self.sigma_coverage)) if self.sigma_coverage is not None else Decimal("3.0")
        if cov_d <= 0:
            raise ValueError(f"sigma_coverage must be strictly positive, got {cov_d}")

        sd_d = Decimal(str(self.std_dev)) if self.std_dev is not None else None
        tol_d = Decimal(str(self.tolerance_pct)) if self.tolerance_pct is not None else None
        min_d = Decimal(str(self.min_val)) if self.min_val is not None else None
        max_d = Decimal(str(self.max_val)) if self.max_val is not None else None

        if sd_d is not None:
            if sd_d < 0:
                raise ValueError(f"std_dev must be non-negative, got {sd_d}")
        elif tol_d is not None:
            if tol_d < 0:
                raise ValueError(f"tolerance_pct must be non-negative, got {tol_d}")
            tol_val = nom_d * (tol_d / Decimal("100"))
            sd_d = abs(tol_val) / cov_d
        else:
            sd_d = Decimal("0")

        if min_d is not None and max_d is not None and min_d > max_d:
            raise ValueError(f"min_val ({min_d}) cannot exceed max_val ({max_d})")

        object.__setattr__(self, "nominal", nom_d)
        object.__setattr__(self, "std_dev", sd_d)
        object.__setattr__(self, "tolerance_pct", tol_d)
        object.__setattr__(self, "sigma_coverage", cov_d)
        object.__setattr__(self, "min_val", min_d)
        object.__setattr__(self, "max_val", max_d)

    def validate(self) -> list[str]:
        issues = []
        if self.std_dev is not None and self.std_dev < 0:
            issues.append(f"std_dev ({self.std_dev}) < 0")
        if self.sigma_coverage <= 0:
            issues.append(f"sigma_coverage ({self.sigma_coverage}) <= 0")
        if self.min_val is not None and self.max_val is not None and self.min_val > self.max_val:
            issues.append(f"min_val ({self.min_val}) > max_val ({self.max_val})")
        return issues

    def sample(self, rng: random.Random) -> Decimal:
        if self.std_dev == 0:
            return self.nominal
        val_flt = rng.gauss(float(self.nominal), float(self.std_dev))
        val_d = Decimal(str(round(val_flt, 9)))
        if self.min_val is not None and val_d < self.min_val:
            val_d = self.min_val
        if self.max_val is not None and val_d > self.max_val:
            val_d = self.max_val
        return val_d


@dataclass(frozen=True)
class MonteCarloAnalysis:
    """Specification for Monte Carlo analysis and statistical parameter propagation."""
    iterations: int
    parameters: dict[str, ParameterDistribution]
    output_variables: tuple[str, ...] = ("v(out)",)
    base_analysis: Any = "op"  # "op" | ACAnalysis(...) | TransientAnalysis(...) | DCSweepAnalysis(...) | str
    seed: int | None = None
    continue_on_error: bool = True
    metric_extractors: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        try:
            n = int(self.iterations)
        except Exception as exc:
            raise ValueError(f"invalid iterations: {exc}")
        if n <= 0:
            raise ValueError(f"Monte Carlo iterations must be positive, got {n}")

        if not self.parameters:
            raise ValueError("Monte Carlo parameters mapping cannot be empty")

        for k, dist in self.parameters.items():
            if not isinstance(dist, ParameterDistribution):
                raise TypeError(f"parameter {k!r} distribution must inherit from ParameterDistribution, got {type(dist)}")
            issues = dist.validate()
            if issues:
                raise ValueError(f"invalid distribution for parameter {k!r}: {'; '.join(issues)}")

        if not self.output_variables:
            raise ValueError("Monte Carlo output_variables cannot be empty")

        out_vars = tuple(str(v).strip() for v in self.output_variables if str(v).strip())
        if not out_vars:
            raise ValueError("Monte Carlo output_variables cannot be empty")

        s = int(self.seed) if self.seed is not None else None

        object.__setattr__(self, "iterations", n)
        object.__setattr__(self, "output_variables", out_vars)
        object.__setattr__(self, "seed", s)


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
class ComplexSignal:
    """Scientific representation of an AC complex simulated electrical variable.

    Maintains separation between solver IEEE 754 float precision (complex) and
    high-precision domain Decimal representations for real/imag components,
    magnitude, phase (radians and degrees), and magnitude in decibels.
    """
    name: str  # e.g. "v(out)", "i(v1)"
    unit: str  # e.g. "V", "A"
    axis: str  # "voltage", "current"
    real_samples: tuple[Decimal, ...] = ()
    imag_samples: tuple[Decimal, ...] = ()
    raw_complex_samples: tuple[complex, ...] = ()

    @property
    def magnitude_samples(self) -> tuple[Decimal, ...]:
        """Magnitude |H| = sqrt(Re^2 + Im^2) for all frequency points."""
        res = []
        for r, i in zip(self.real_samples, self.imag_samples):
            mag = math.hypot(float(r), float(i))
            res.append(Decimal(str(mag)))
        return tuple(res)

    @property
    def phase_rad_samples(self) -> tuple[Decimal, ...]:
        """Phase in radians: atan2(Im, Re) in (-pi, pi] for all frequency points."""
        res = []
        for r, i in zip(self.real_samples, self.imag_samples):
            rad = math.atan2(float(i), float(r))
            res.append(Decimal(str(rad)))
        return tuple(res)

    @property
    def phase_deg_samples(self) -> tuple[Decimal, ...]:
        """Phase in degrees: degrees(atan2(Im, Re)) in (-180, 180] for all frequency points."""
        res = []
        for r, i in zip(self.real_samples, self.imag_samples):
            deg = math.degrees(math.atan2(float(i), float(r)))
            res.append(Decimal(str(deg)))
        return tuple(res)

    @property
    def db_samples(self) -> tuple[Decimal, ...]:
        """Magnitude in decibels: 20 * log10(|H|) for all frequency points.

        If |H| == 0, returns Decimal('-Infinity').
        """
        res = []
        for r, i in zip(self.real_samples, self.imag_samples):
            mag = math.hypot(float(r), float(i))
            if mag <= 0:
                res.append(Decimal("-Infinity"))
            else:
                db = 20.0 * math.log10(mag)
                res.append(Decimal(str(db)))
        return tuple(res)

    @property
    def value(self) -> complex | None:
        """First complex sample directly from solver."""
        return self.raw_complex_samples[0] if self.raw_complex_samples else None

    @property
    def real_value(self) -> Decimal | None:
        """Real part of the first point."""
        return self.real_samples[0] if self.real_samples else None

    @property
    def imag_value(self) -> Decimal | None:
        """Imaginary part of the first point."""
        return self.imag_samples[0] if self.imag_samples else None

    @property
    def magnitude_value(self) -> Decimal | None:
        """Magnitude of the first point."""
        return self.magnitude_samples[0] if self.magnitude_samples else None

    @property
    def phase_deg_value(self) -> Decimal | None:
        """Phase in degrees of the first point."""
        return self.phase_deg_samples[0] if self.phase_deg_samples else None

    @property
    def db_value(self) -> Decimal | None:
        """Magnitude in dB of the first point."""
        return self.db_samples[0] if self.db_samples else None

    @property
    def is_multi_point(self) -> bool:
        return len(self.raw_complex_samples) > 1

    def __len__(self) -> int:
        return len(self.raw_complex_samples)


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
    complex_signals: dict[str, ComplexSignal] = field(default_factory=dict)
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

    def get_complex_signal(self, name: str) -> ComplexSignal | None:
        """Case-insensitive lookup for complex signals by name e.g. 'v(out)' or 'V(OUT)'."""
        target = name.strip().lower()
        for k, v in self.complex_signals.items():
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
    def frequency_axis(self) -> Signal | None:
        """The primary frequency variable/axis Signal if present in the simulation."""
        for sig in self.signals.values():
            if sig.axis == "frequency":
                return sig
        if "frequency" in self.signals:
            return self.signals["frequency"]
        return None

    @property
    def points_count(self) -> int:
        """Number of points in the simulation result."""
        axis = self.frequency_axis or self.time_axis or self.sweep_axis
        if axis and axis.samples:
            return len(axis.samples)
        for csig in self.complex_signals.values():
            if csig.raw_complex_samples:
                return len(csig.raw_complex_samples)
        for sig in self.signals.values():
            if sig.samples:
                return len(sig.samples)
        return 0

    def sample_at(self, signal_name: str, target: Decimal | float | str) -> Decimal | None:
        """Sample a real signal value at or nearest to a specified time, sweep, or frequency value."""
        sig = self.get_signal(signal_name)
        axis = self.frequency_axis or self.time_axis or self.sweep_axis
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

    def sample_complex_at(self, signal_name: str, target_freq: Decimal | float | str) -> complex | None:
        """Sample a complex signal value at or nearest to a specified frequency."""
        sig = self.get_complex_signal(signal_name)
        f_axis = self.frequency_axis
        if not sig or not sig.raw_complex_samples or not f_axis or not f_axis.samples:
            return None
        target_d = parse_spice_number(target_freq)
        best_idx = 0
        min_diff = abs(f_axis.samples[0] - target_d)
        for i, val in enumerate(f_axis.samples[1:], start=1):
            diff = abs(val - target_d)
            if diff < min_diff:
                min_diff = diff
                best_idx = i
        if best_idx < len(sig.raw_complex_samples):
            return sig.raw_complex_samples[best_idx]
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

    def voltage_complex(self, node: str) -> complex | None:
        """Convenience accessor for node voltage complex scalar value (first point)."""
        node_clean = node.strip().lower()
        name = node_clean if (node_clean.startswith("v(") and node_clean.endswith(")")) else f"v({node_clean})"
        sig = self.get_complex_signal(name)
        return sig.value if sig else None

    def voltage_complex_samples(self, node: str) -> tuple[complex, ...] | None:
        """Full sequence of node voltage complex samples across all frequency points."""
        node_clean = node.strip().lower()
        name = node_clean if (node_clean.startswith("v(") and node_clean.endswith(")")) else f"v({node_clean})"
        sig = self.get_complex_signal(name)
        return sig.raw_complex_samples if sig else None

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

    def current_complex(self, source: str) -> complex | None:
        """Convenience accessor for source branch current complex scalar value (first point)."""
        src_clean = source.strip().lower()
        if src_clean.startswith("i(") and src_clean.endswith(")"):
            name = src_clean
        elif src_clean.endswith("#branch"):
            name = f"i({src_clean[:-7]})"
        else:
            name = f"i({src_clean})"
        sig = self.get_complex_signal(name)
        if sig:
            return sig.value
        sig2 = self.get_complex_signal(f"{src_clean}#branch")
        return sig2.value if sig2 else None

    def current_complex_samples(self, source: str) -> tuple[complex, ...] | None:
        """Full sequence of source branch current complex samples across all frequency points."""
        src_clean = source.strip().lower()
        if src_clean.startswith("i(") and src_clean.endswith(")"):
            name = src_clean
        elif src_clean.endswith("#branch"):
            name = f"i({src_clean[:-7]})"
        else:
            name = f"i({src_clean})"
        sig = self.get_complex_signal(name)
        if sig:
            return sig.raw_complex_samples
        sig2 = self.get_complex_signal(f"{src_clean}#branch")
        return sig2.raw_complex_samples if sig2 else None

    def magnitude(self, signal_name: str) -> tuple[Decimal, ...] | None:
        """Return sequence of magnitude samples |H| for given complex signal name."""
        sig = self.get_complex_signal(signal_name)
        return sig.magnitude_samples if sig else None

    def phase_deg(self, signal_name: str) -> tuple[Decimal, ...] | None:
        """Return sequence of phase in degrees (-180, 180] for given complex signal name."""
        sig = self.get_complex_signal(signal_name)
        return sig.phase_deg_samples if sig else None

    def phase_rad(self, signal_name: str) -> tuple[Decimal, ...] | None:
        """Return sequence of phase in radians (-pi, pi] for given complex signal name."""
        sig = self.get_complex_signal(signal_name)
        return sig.phase_rad_samples if sig else None

    def db(self, signal_name: str) -> tuple[Decimal, ...] | None:
        """Return sequence of magnitude in decibels (20*log10(|H|)) for given complex signal name."""
        sig = self.get_complex_signal(signal_name)
        return sig.db_samples if sig else None

    @property
    def onoise_spectrum(self) -> Signal | None:
        """Output noise spectral density Signal (V/sqrt(Hz) or A/sqrt(Hz)) if present."""
        return self.get_signal("onoise_spectrum")

    @property
    def inoise_spectrum(self) -> Signal | None:
        """Input-referred noise spectral density Signal (V/sqrt(Hz) or A/sqrt(Hz)) if present."""
        return self.get_signal("inoise_spectrum")

    @property
    def onoise_total(self) -> Decimal | None:
        """Integrated output noise (V_RMS or A_RMS) if present."""
        val = self.data.get("onoise_total")
        return Decimal(val) if val is not None else None

    @property
    def inoise_total(self) -> Decimal | None:
        """Integrated input-referred noise (V_RMS or A_RMS) if present."""
        val = self.data.get("inoise_total")
        return Decimal(val) if val is not None else None

    def sample_onoise_at(self, target_frequency: Decimal | str | float | int) -> Decimal | None:
        """Sample output noise spectral density at or nearest to specified frequency."""
        return self.sample_at("onoise_spectrum", target_frequency)

    def sample_inoise_at(self, target_frequency: Decimal | str | float | int) -> Decimal | None:
        """Sample input-referred noise spectral density at or nearest to specified frequency."""
        return self.sample_at("inoise_spectrum", target_frequency)

    @property
    def sensitivities(self) -> dict[str, Decimal | ComplexSignal]:
        """Component sensitivities dictionary if present."""
        return {}

    def get_sensitivity(self, param_name: str) -> Decimal | ComplexSignal | None:
        """Accessor for component sensitivity if present."""
        return None

    def get_normalized_sensitivity(self, param_name: str) -> Decimal | ComplexSignal | None:
        """Accessor for normalized component sensitivity if present."""
        return None


@dataclass(frozen=True)
class NoiseResult(SimulationResult):
    """Specialized simulation result for Noise (.noise) analysis.

    Provides noise spectral density curves (onoise_spectrum, inoise_spectrum)
    and integrated noise totals (onoise_total, inoise_total).
    """
    onoise_total_val: Decimal | None = None
    inoise_total_val: Decimal | None = None

    @property
    def onoise_total(self) -> Decimal | None:
        if self.onoise_total_val is not None:
            return self.onoise_total_val
        val = self.data.get("onoise_total")
        return Decimal(val) if val is not None else None

    @property
    def inoise_total(self) -> Decimal | None:
        if self.inoise_total_val is not None:
            return self.inoise_total_val
        val = self.data.get("inoise_total")
        return Decimal(val) if val is not None else None


@dataclass(frozen=True)
class SensitivityResult(SimulationResult):
    """Specialized simulation result for Sensitivity (.sens) analysis.

    Contains component sensitivities (d(Output)/d(Parameter)) and normalized sensitivities.
    For DC: sensitivities are scalar Decimals (e.g. V/Ohm, V/V, etc.).
    For AC: sensitivities are ComplexSignals across the frequency sweep.
    """
    sensitivities_map: dict[str, Decimal | ComplexSignal] = field(default_factory=dict)
    normalized_sensitivities: dict[str, Decimal | ComplexSignal] = field(default_factory=dict)
    output_variable: str = ""

    @property
    def sensitivities(self) -> dict[str, Decimal | ComplexSignal]:
        return self.sensitivities_map

    def get_sensitivity(self, param_name: str) -> Decimal | ComplexSignal | None:
        target = param_name.strip().lower()
        for k, v in self.sensitivities_map.items():
            if k.lower() == target:
                return v
        return None

    def get_normalized_sensitivity(self, param_name: str) -> Decimal | ComplexSignal | None:
        target = param_name.strip().lower()
        for k, v in self.normalized_sensitivities.items():
            if k.lower() == target:
                return v
        return None

    def compute_normalized_sensitivities(
        self,
        nominal_params: dict[str, Decimal | float | int],
        nominal_output: Any = None,
    ) -> dict[str, Decimal | ComplexSignal]:
        """Compute normalized sensitivities S_p = (p / Output) * (d Output / d p)."""
        norm_map: dict[str, Decimal | ComplexSignal] = {}
        for p_name, p_val in nominal_params.items():
            sens = self.get_sensitivity(p_name)
            if sens is None:
                continue
            p_dec = Decimal(str(p_val))
            if isinstance(sens, Decimal):
                if nominal_output is not None and not isinstance(nominal_output, (Signal, ComplexSignal)):
                    out_dec = Decimal(str(nominal_output))
                    if out_dec != 0:
                        norm_map[p_name.lower()] = (p_dec / out_dec) * sens
            elif isinstance(sens, ComplexSignal):
                # Frequency-dependent AC normalized sensitivity: S_p(jw) = (p / H(jw)) * (dH(jw) / dp)
                p_flt = float(p_dec)
                if isinstance(nominal_output, ComplexSignal) and len(nominal_output) == len(sens):
                    s_samples = []
                    re_samples = []
                    im_samples = []
                    for h_val, dh_val in zip(nominal_output.raw_complex_samples, sens.raw_complex_samples):
                        if h_val != 0:
                            s_val = (p_flt / h_val) * dh_val
                        else:
                            s_val = 0j
                        s_samples.append(s_val)
                        re_samples.append(Decimal(str(s_val.real)))
                        im_samples.append(Decimal(str(s_val.imag)))
                    norm_map[p_name.lower()] = ComplexSignal(
                        f"s_{p_name.lower()}", "normalized", "sensitivity",
                        tuple(re_samples), tuple(im_samples), tuple(s_samples)
                    )
        return norm_map


@dataclass(frozen=True)
class VariableStatistics:
    """Rigorous sample statistical aggregation for an output variable across Monte Carlo iterations.

    Note: These metrics are standard descriptive sample statistics:
    - Standard deviation uses Bessel's correction (N - 1 denominator) for N > 1.
    - Standard deviation for N = 1 is defined as 0.
    - Percentiles use standard rank linear interpolation.
    - This is NOT a GUM metrological uncertainty budget.
    """
    variable: str
    count: int
    mean: Decimal
    median: Decimal
    min_val: Decimal
    max_val: Decimal
    std_dev: Decimal
    variance: Decimal
    coeff_of_variation: Decimal
    percentiles: dict[int, Decimal]  # keys: 1, 5, 25, 50, 75, 95, 99


@dataclass(frozen=True)
class MonteCarloIteration:
    """Detailed record of a single concrete Monte Carlo trial."""
    index: int
    parameters: dict[str, Decimal]
    sub_seed: int
    netlist: str
    simulation_result: SimulationResult | None
    output_values: dict[str, Decimal]
    status: str = "COMPLETED"  # COMPLETED | FAILED
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class MonteCarloResult(SimulationResult):
    """Complete aggregated result of a Monte Carlo run."""
    iterations_requested: int = 0
    iterations_completed: int = 0
    iterations_failed: int = 0
    seed: int = 0
    analysis: MonteCarloAnalysis | None = None
    iterations: tuple[MonteCarloIteration, ...] = ()
    statistics: dict[str, VariableStatistics] = field(default_factory=dict)


def compute_statistics(values: list[Decimal], variable_name: str = "") -> VariableStatistics:
    """Compute sample statistics over a non-empty sequence of Decimals."""
    n = len(values)
    if n == 0:
        raise ValueError("cannot compute statistics on empty values sequence")

    if n == 1:
        val = values[0]
        p_dict = {p: val for p in (1, 5, 25, 50, 75, 95, 99)}
        return VariableStatistics(
            variable=variable_name,
            count=1,
            mean=val,
            median=val,
            min_val=val,
            max_val=val,
            std_dev=Decimal("0"),
            variance=Decimal("0"),
            coeff_of_variation=Decimal("0"),
            percentiles=p_dict,
        )

    mean_val = sum(values) / Decimal(n)
    var_val = sum((x - mean_val) ** 2 for x in values) / Decimal(n - 1)
    std_val = Decimal(str(math.sqrt(float(var_val))))
    cv_val = (std_val / abs(mean_val)) if mean_val != 0 else Decimal("0")

    sorted_vals = sorted(values)
    min_v = sorted_vals[0]
    max_v = sorted_vals[-1]

    # Median
    if n % 2 == 1:
        med_v = sorted_vals[n // 2]
    else:
        med_v = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / Decimal("2")

    # Percentiles using linear interpolation
    p_dict = {}
    for p in (1, 5, 25, 50, 75, 95, 99):
        rank = (n - 1) * (p / 100.0)
        idx = int(math.floor(rank))
        frac = rank - idx
        if idx >= n - 1:
            p_val = sorted_vals[-1]
        else:
            p_val = sorted_vals[idx] + Decimal(str(frac)) * (sorted_vals[idx + 1] - sorted_vals[idx])
        p_dict[p] = p_val

    return VariableStatistics(
        variable=variable_name,
        count=n,
        mean=mean_val,
        median=med_v,
        min_val=min_v,
        max_val=max_v,
        std_dev=std_val,
        variance=var_val,
        coeff_of_variation=cv_val,
        percentiles=p_dict,
    )


def substitute_netlist_parameters(netlist: str, params: dict[str, Decimal]) -> str:
    """Substitute concrete parameter values into SPICE netlist without altering directives.

    Supports:
    - Two-terminal passive elements (R, L, C)
    - Independent voltage and current sources (V, I) including DC token preservation
    - .param declarations (.param NAME = VALUE)
    """
    norm_params = {k.strip().upper(): v for k, v in params.items()}
    lines = netlist.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            out.append(line)
            continue

        # .param cards
        if stripped.lower().startswith(".param"):
            m = re.match(r"^(\.param\s+)([a-zA-Z0-9_]+)(\s*=\s*)([^\s]+)(.*)$", stripped, re.I)
            if m:
                pname = m.group(2).upper()
                if pname in norm_params:
                    val = norm_params[pname]
                    v_str = (
                        f"{float(val):.8e}"
                        if (abs(val) < Decimal("1e-4") or abs(val) >= Decimal("1e7"))
                        else (f"{val:f}".rstrip("0").rstrip(".") if "." in f"{val:f}" else f"{val:f}")
                    )
                    out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{v_str}{m.group(5)}")
                    continue
            out.append(line)
            continue

        # Ignore other dot-directives (.op, .ac, .tran, .include, etc.)
        if stripped.startswith("."):
            out.append(line)
            continue

        parts = stripped.split()
        if not parts:
            out.append(line)
            continue

        ref = parts[0].upper()
        if ref in norm_params:
            val = norm_params[ref]
            v_str = (
                f"{float(val):.8e}"
                if (abs(val) < Decimal("1e-4") or abs(val) >= Decimal("1e7"))
                else (f"{val:f}".rstrip("0").rstrip(".") if "." in f"{val:f}" else f"{val:f}")
            )
            if ref.startswith(("V", "I")):
                # Search for 'dc' token
                dc_idx = -1
                for idx, t in enumerate(parts[3:], start=3):
                    if t.lower() == "dc":
                        dc_idx = idx
                        break
                if dc_idx != -1 and dc_idx + 1 < len(parts):
                    parts[dc_idx + 1] = v_str
                elif len(parts) >= 4:
                    parts[3] = v_str
            elif len(parts) >= 4:
                parts[3] = v_str
            out.append(" ".join(parts))
        else:
            out.append(line)

    return "\n".join(out)


def _extract_output_variable(
    var_name: str,
    result: SimulationResult,
    parameters: dict[str, Decimal],
    metric_extractors: dict[str, Any] | None = None,
) -> Decimal:
    """Extract a scalar numerical result as Decimal for an output variable from a simulation trial."""
    if metric_extractors and var_name in metric_extractors:
        fn = metric_extractors[var_name]
        ret = fn(result, parameters)
        return Decimal(str(ret))

    v_clean = var_name.strip()
    v_lower = v_clean.lower()

    # 1. Automatic cutoff frequency extraction for AC analysis: 'fc', 'cutoff', 'f_cutoff'
    if v_lower in ("fc", "cutoff", "f_cutoff"):
        csig = result.get_complex_signal("v(out)")
        if not csig and result.complex_signals:
            csig = next(iter(result.complex_signals.values()))
        f_axis = result.frequency_axis
        if csig and f_axis and csig.raw_complex_samples and len(f_axis.samples) > 1:
            freqs = [float(f) for f in f_axis.samples]
            mags = [abs(c) for c in csig.raw_complex_samples]
            passband_mag = mags[0]
            target_mag = passband_mag / math.sqrt(2.0)
            for i in range(len(mags) - 1):
                if (mags[i] >= target_mag >= mags[i + 1]) or (mags[i] <= target_mag <= mags[i + 1]):
                    f1, f2 = freqs[i], freqs[i + 1]
                    m1, m2 = mags[i], mags[i + 1]
                    if m2 != m1:
                        fc = f1 + (target_mag - m1) / (m2 - m1) * (f2 - f1)
                    else:
                        fc = f1
                    return Decimal(str(round(fc, 4)))

    # 2. Automatic resonance frequency extraction for AC analysis: 'f0', 'resonance', 'f_resonance'
    if v_lower in ("f0", "resonance", "f_resonance"):
        target_sig = result.get_complex_signal("i(v1)") or result.get_complex_signal("v(out)")
        if not target_sig and result.complex_signals:
            target_sig = next(iter(result.complex_signals.values()))
        f_axis = result.frequency_axis
        if target_sig and f_axis and target_sig.raw_complex_samples and len(f_axis.samples) > 1:
            freqs = [float(f) for f in f_axis.samples]
            mags = [abs(c) for c in target_sig.raw_complex_samples]
            max_idx = max(range(len(mags)), key=lambda i: mags[i])
            if 0 < max_idx < len(mags) - 1:
                y1, y2, y3 = mags[max_idx - 1], mags[max_idx], mags[max_idx + 1]
                f1, f2, f3 = freqs[max_idx - 1], freqs[max_idx], freqs[max_idx + 1]
                denom = y1 - 2 * y2 + y3
                if denom != 0:
                    delta = 0.5 * (y1 - y3) / denom
                    df = (f3 - f1) / 2.0
                    peak_f = f2 + delta * df
                    return Decimal(str(round(peak_f, 4)))
            return Decimal(str(round(freqs[max_idx], 4)))

    # 3. Automatic maximum current extraction: 'max_current', 'i_max'
    if v_lower in ("max_current", "i_max"):
        target_sig = result.get_complex_signal("i(v1)") or next(iter(result.complex_signals.values()), None)
        if target_sig and target_sig.raw_complex_samples:
            max_i = max(abs(c) for c in target_sig.raw_complex_samples)
            return Decimal(str(round(max_i, 6)))

    # 4. Standard node voltage scalar lookup
    v_val = result.voltage(v_clean)
    if v_val is not None:
        return v_val

    # 5. Real Signal lookup
    sig = result.get_signal(v_clean)
    if sig and sig.value is not None:
        return sig.value

    # 6. Complex Signal lookup (magnitude)
    csig = result.get_complex_signal(v_clean)
    if csig and csig.magnitude_value is not None:
        return csig.magnitude_value

    # 7. Fallback to data dictionary
    if v_clean in result.data:
        try:
            return Decimal(str(result.data[v_clean]))
        except Exception:
            pass
    if v_lower in result.data:
        try:
            return Decimal(str(result.data[v_lower]))
        except Exception:
            pass

    raise ValueError(f"unable to extract output variable {var_name!r} from simulation result")


def run_monte_carlo(
    netlist: str,
    analysis: MonteCarloAnalysis,
    backend: Any,
    cas_store: Any = None,
) -> MonteCarloResult:
    """Execute Monte Carlo parameter propagation across repeated independent simulations."""
    master_seed = analysis.seed if analysis.seed is not None else random.randint(0, 2**31 - 1)
    rng = random.Random(master_seed)

    # 1. Pre-generate concrete parameter samples deterministically
    sorted_param_names = sorted(analysis.parameters.keys())
    planned_iterations: list[tuple[int, int, dict[str, Decimal], str]] = []
    for i in range(analysis.iterations):
        sub_seed = rng.randint(0, 2**31 - 1)
        iter_rng = random.Random(sub_seed)
        iter_params = {k: analysis.parameters[k].sample(iter_rng) for k in sorted_param_names}
        iter_netlist = substitute_netlist_parameters(netlist, iter_params)
        planned_iterations.append((i, sub_seed, iter_params, iter_netlist))

    if isinstance(analysis.base_analysis, (list, tuple)):
        base_analyses = tuple(analysis.base_analysis)
    else:
        base_analyses = (analysis.base_analysis,)

    completed_iterations: list[MonteCarloIteration] = []
    values_by_var: dict[str, list[Decimal]] = {var: [] for var in analysis.output_variables}
    iterations_completed = 0
    iterations_failed = 0
    cancelled = False

    # 2. Sequential execution
    for idx, sub_seed, iter_params, iter_netlist in planned_iterations:
        if getattr(backend, "_cancel_requested", None) and backend._cancel_requested.is_set():
            cancelled = True
            break

        try:
            try:
                sim_res = backend.simulate(iter_netlist, base_analyses, cas_store=cas_store)
            except TypeError:
                sim_res = backend.simulate(iter_netlist, base_analyses)

            if getattr(sim_res, "status", "") == "CANCELLED":
                cancelled = True
                break

            if getattr(sim_res, "status", "") != "COMPLETED":
                err_msg = "; ".join(getattr(sim_res, "errors", ())) or f"simulation status: {getattr(sim_res, 'status', 'UNKNOWN')}"
                raise RuntimeError(f"Iteration simulation failed: {err_msg}")

            out_values: dict[str, Decimal] = {}
            for v_name in analysis.output_variables:
                val = _extract_output_variable(v_name, sim_res, iter_params, analysis.metric_extractors)
                out_values[v_name] = val
                values_by_var[v_name].append(val)

            completed_iterations.append(
                MonteCarloIteration(
                    index=idx,
                    parameters=iter_params,
                    sub_seed=sub_seed,
                    netlist=iter_netlist,
                    simulation_result=sim_res,
                    output_values=out_values,
                    status="COMPLETED",
                    errors=(),
                )
            )
            iterations_completed += 1
        except Exception as exc:
            iterations_failed += 1
            completed_iterations.append(
                MonteCarloIteration(
                    index=idx,
                    parameters=iter_params,
                    sub_seed=sub_seed,
                    netlist=iter_netlist,
                    simulation_result=None,
                    output_values={},
                    status="FAILED",
                    errors=(str(exc),),
                )
            )
            if not analysis.continue_on_error:
                break

    # 3. Status determination
    if cancelled or (getattr(backend, "_cancel_requested", None) and backend._cancel_requested.is_set()):
        final_status = "CANCELLED"
    elif iterations_failed > 0 and not analysis.continue_on_error:
        final_status = "FAILED"
    elif iterations_completed == analysis.iterations:
        final_status = "COMPLETED"
    elif iterations_completed > 0:
        final_status = "PARTIAL"
    else:
        final_status = "FAILED"

    # 4. Statistical aggregation
    stats: dict[str, VariableStatistics] = {}
    signals: dict[str, Signal] = {}
    for var, vals in values_by_var.items():
        if vals:
            st = compute_statistics(vals, var)
            stats[var] = st
            dec_samples = tuple(vals)
            flt_samples = tuple(float(x) for x in vals)
            unit = "V" if var.lower().startswith("v") else ("A" if var.lower().startswith("i") else ("Hz" if var.lower() in ("fc", "f0", "cutoff", "resonance") else ""))
            axis = "distribution"
            signals[var] = Signal(var, unit, axis, dec_samples, flt_samples)

    data: dict[str, str] = {var: str(s.mean) for var, s in stats.items()}
    data["iterations_requested"] = str(analysis.iterations)
    data["iterations_completed"] = str(iterations_completed)
    data["iterations_failed"] = str(iterations_failed)
    data["seed"] = str(master_seed)

    raw_summary = {
        "analysis_type": "monte_carlo",
        "iterations_requested": analysis.iterations,
        "iterations_completed": iterations_completed,
        "iterations_failed": iterations_failed,
        "seed": master_seed,
        "backend": getattr(backend, "name", "unknown"),
        "status": final_status,
        "parameters": {k: str(v) for k, v in analysis.parameters.items()},
        "output_variables": list(analysis.output_variables),
        "statistics": {k: {
            "count": v.count,
            "mean": str(v.mean),
            "median": str(v.median),
            "std_dev": str(v.std_dev),
            "variance": str(v.variance),
            "min": str(v.min_val),
            "max": str(v.max_val),
            "coeff_of_variation": str(v.coeff_of_variation),
            "percentiles": {str(pk): str(pv) for pk, pv in v.percentiles.items()}
        } for k, v in stats.items()}
    }
    raw_bytes = json.dumps(raw_summary, indent=2).encode("utf-8")
    raw_hash = ""
    if cas_store is not None:
        try:
            raw_hash = cas_store.put_bytes(raw_bytes)
        except Exception:
            raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    else:
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

    netlist_digest = hashlib.sha256(netlist.encode("ascii", errors="replace")).hexdigest()

    errors_list = []
    for it in completed_iterations:
        if it.errors:
            errors_list.extend(it.errors)

    return MonteCarloResult(
        backend=getattr(backend, "name", "unknown"),
        netlist_digest=netlist_digest,
        analyses=(analysis,),
        data=data,
        mocked=(getattr(backend, "name", "") == "mock"),
        signals=signals,
        complex_signals={},
        status=final_status,
        exit_code=0 if final_status in ("COMPLETED", "PARTIAL") else 1,
        duration_seconds=0.0,
        raw_artifact_hash=raw_hash,
        provenance=raw_summary,
        errors=tuple(errors_list),
        iterations_requested=analysis.iterations,
        iterations_completed=iterations_completed,
        iterations_failed=iterations_failed,
        seed=master_seed,
        analysis=analysis,
        iterations=tuple(completed_iterations),
        statistics=stats,
    )


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
        has_ac = False
        has_noise = False
        has_sens = False
        sens_params: tuple[str, ...] = ()
        noise_in_src: str | None = None
        sens_is_ac = False

        for a in self.analyses:
            if isinstance(a, DCSweepAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_dc_sweep = True
            elif isinstance(a, TransientAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_tran = True
            elif isinstance(a, ACAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_ac = True
            elif isinstance(a, NoiseAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_noise = True
                noise_in_src = a.input_source
            elif isinstance(a, SensitivityAnalysis):
                analysis_commands.append(a.to_spice_card())
                has_sens = True
                if a.analysis_type == "AC":
                    sens_is_ac = True
                if a.parameters:
                    sens_params = a.parameters
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
                elif an_lower.startswith("ac ") or an_lower.startswith(".ac "):
                    # Validate via ACAnalysis
                    ac = ACAnalysis.from_string(an)
                    analysis_commands.append(ac.to_spice_card())
                    has_ac = True
                elif an_lower.startswith("noise ") or an_lower.startswith(".noise "):
                    # Validate via NoiseAnalysis
                    noise = NoiseAnalysis.from_string(an)
                    analysis_commands.append(noise.to_spice_card())
                    has_noise = True
                    noise_in_src = noise.input_source
                elif an_lower.startswith("sens ") or an_lower.startswith(".sens "):
                    # Validate via SensitivityAnalysis
                    sens = SensitivityAnalysis.from_string(an)
                    analysis_commands.append(sens.to_spice_card())
                    has_sens = True
                    if sens.analysis_type == "AC":
                        sens_is_ac = True
                    if sens.parameters:
                        sens_params = sens.parameters
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

        # For AC / Noise / AC-Sens in batch mode, ensure AC source excitation is present
        if has_ac or has_noise or (has_sens and sens_is_ac):
            has_ac_source = False
            first_v_idx = None
            target_src_idx = None
            for idx, line in enumerate(lines):
                l_strip = line.strip()
                if not l_strip or l_strip.startswith("*") or l_strip.startswith("."):
                    continue
                parts = l_strip.split()
                if not parts:
                    continue
                ref = parts[0].upper()
                if ref.startswith("V") or ref.startswith("I"):
                    if any(tok.lower() == "ac" for tok in parts):
                        has_ac_source = True
                        break
                    if noise_in_src and ref == noise_in_src.upper():
                        target_src_idx = idx
                    if first_v_idx is None and ref.startswith("V"):
                        first_v_idx = idx
            if not has_ac_source:
                chosen_idx = target_src_idx if target_src_idx is not None else first_v_idx
                if chosen_idx is not None:
                    lines[chosen_idx] = f"{lines[chosen_idx].rstrip()} ac 1"

            if has_ac:
                has_print_ac = any(l.strip().lower().startswith(".print ac") or l.strip().lower().startswith("print ac") for l in lines)
                if not has_print_ac:
                    print_card = self._build_print_ac_card(lines)
                    if print_card and print_card.lower() not in existing:
                        to_add.append(print_card)

        # For Noise in batch mode, ngspice requires a .print noise card
        if has_noise:
            has_print_noise = any(l.strip().lower().startswith(".print noise") or l.strip().lower().startswith("print noise") for l in lines)
            if not has_print_noise:
                to_add.append(".print noise all")

        # For Sensitivity in batch mode, ngspice requires a .print sens card
        if has_sens:
            has_print_sens = any(l.strip().lower().startswith(".print sens") or l.strip().lower().startswith("print sens") for l in lines)
            if not has_print_sens:
                if sens_params:
                    to_add.append(f".print sens {' '.join(sens_params)}")
                else:
                    to_add.append(".print sens all")

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

    @staticmethod
    def _build_print_ac_card(lines: list[str]) -> str:
        """Inspect netlist to automatically construct a .print ac card with all circuit nets and sources."""
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
            return f".print ac {' '.join(tokens)}"
        return ".print ac"


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
        for a in analyses:
            if isinstance(a, MonteCarloAnalysis):
                return run_monte_carlo(netlist, a, self)
        digest = hashlib.sha256(netlist.encode()).hexdigest()
        signals = {}
        complex_signals = {}
        for k, v in self.payload.items():
            k_lower = k.lower()
            unit = "V" if k_lower.startswith("v") else ("A" if k_lower.startswith("i") else "")
            axis = "voltage" if unit == "V" else ("current" if unit == "A" else "other")
            if isinstance(v, (list, tuple)) and v and isinstance(v[0], complex):
                raw_c = tuple(complex(x) for x in v)
                re_d = tuple(Decimal(str(x.real)) for x in raw_c)
                im_d = tuple(Decimal(str(x.imag)) for x in raw_c)
                complex_signals[k_lower] = ComplexSignal(k_lower, unit, axis, re_d, im_d, raw_c)
            elif isinstance(v, complex):
                raw_c = (complex(v),)
                re_d = (Decimal(str(v.real)),)
                im_d = (Decimal(str(v.imag)),)
                complex_signals[k_lower] = ComplexSignal(k_lower, unit, axis, re_d, im_d, raw_c)
            elif isinstance(v, (list, tuple)):
                dec_tuple = tuple(Decimal(str(x)) for x in v)
                flt_tuple = tuple(float(x) for x in v)
                signals[k_lower] = Signal(k_lower, unit, axis, dec_tuple, flt_tuple)
            else:
                try:
                    dec_tuple = (Decimal(str(v)),)
                    flt_tuple = (float(v),)
                except Exception:
                    dec_tuple = (Decimal(0),)
                    flt_tuple = (0.0,)
                signals[k_lower] = Signal(k_lower, unit, axis, dec_tuple, flt_tuple)
        if any(isinstance(a, NoiseAnalysis) or (isinstance(a, str) and a.strip().lower().startswith("noise")) for a in analyses) or "onoise_total" in self.payload:
            on_tot = Decimal(str(self.payload["onoise_total"])) if "onoise_total" in self.payload else None
            in_tot = Decimal(str(self.payload["inoise_total"])) if "inoise_total" in self.payload else None
            return NoiseResult(self.name, digest, tuple(analyses),
                               dict(self.payload), mocked=True, signals=signals,
                               complex_signals=complex_signals,
                               onoise_total_val=on_tot, inoise_total_val=in_tot)
        if any(isinstance(a, SensitivityAnalysis) or (isinstance(a, str) and a.strip().lower().startswith("sens")) for a in analyses) or "sensitivities" in self.payload:
            sens_map = dict(self.payload.get("sensitivities", {}))
            return SensitivityResult(self.name, digest, tuple(analyses),
                                     dict(self.payload), mocked=True, signals=signals,
                                     complex_signals=complex_signals,
                                     sensitivities_map=sens_map)
        return SimulationResult(self.name, digest, tuple(analyses),
                                dict(self.payload), mocked=True, signals=signals,
                                complex_signals=complex_signals)
