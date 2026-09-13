"""Structured result types for F8-C Thevenin & Norton analysis.

Contains immutable dataclasses representing the Thevenin equivalent,
Norton equivalent, one-port equivalents, and load verification records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from fractions import Fraction

from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.units import Quantity


class EquivalentStatus(Enum):
    SOLVED = "solved"
    VERIFIED = "verified"
    INVALID_PORT = "invalid_port"
    UNSUPPORTED = "unsupported"
    SINGULAR = "singular"
    INCONSISTENT = "inconsistent"
    OPEN_CIRCUIT = "open_circuit"
    SHORT_CIRCUIT = "short_circuit"
    UNDEFINED = "undefined"


class ResistanceKind(Enum):
    FINITE = "finite"
    ZERO = "zero"
    INFINITE = "infinite"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class LoadVerificationResult:
    """Outcome of loading the original vs equivalent one-port with a test resistor."""

    load_resistance: Quantity
    v_port_original: Quantity
    i_port_original: Quantity
    v_port_equivalent: Quantity
    i_port_equivalent: Quantity
    passed: bool


@dataclass(frozen=True)
class TheveninResult:
    """Thevenin equivalent model for a two-terminal port: Vth in series with Rth."""

    status: EquivalentStatus
    port: TheveninPort
    v_th: Quantity | None = None
    r_th: Quantity | None = None
    resistance_kind: ResistanceKind = ResistanceKind.UNDEFINED
    polarity: str = ""
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    load_verifications: tuple[LoadVerificationResult, ...] = ()
    _v_th_exact: Fraction | None = None
    _r_th_exact: Fraction | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "port": {"positive": self.port.positive_terminal, "negative": self.port.negative_terminal},
            "v_th": self.v_th.format() if self.v_th is not None else None,
            "r_th": self.r_th.format() if self.r_th is not None else (
                "infinity" if self.resistance_kind == ResistanceKind.INFINITE else None
            ),
            "resistance_kind": self.resistance_kind.value,
            "polarity": self.polarity,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
            "load_verifications": [
                {
                    "load": lv.load_resistance.format(),
                    "v_original": lv.v_port_original.format(),
                    "i_original": lv.i_port_original.format(),
                    "v_thevenin": lv.v_port_equivalent.format(),
                    "i_thevenin": lv.i_port_equivalent.format(),
                    "passed": lv.passed,
                }
                for lv in self.load_verifications
            ],
        }


@dataclass(frozen=True)
class NortonResult:
    """Norton equivalent model for a two-terminal port: In in parallel with Rn."""

    status: EquivalentStatus
    port: TheveninPort
    i_n: Quantity | None = None
    r_n: Quantity | None = None
    resistance_kind: ResistanceKind = ResistanceKind.UNDEFINED
    polarity: str = ""
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    _i_n_exact: Fraction | None = None
    _r_n_exact: Fraction | None = None
    load_verifications: tuple[LoadVerificationResult, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "port": {"positive": self.port.positive_terminal, "negative": self.port.negative_terminal},
            "i_n": self.i_n.format() if self.i_n is not None else None,
            "r_n": self.r_n.format() if self.r_n is not None else (
                "infinity" if self.resistance_kind == ResistanceKind.INFINITE else None
            ),
            "resistance_kind": self.resistance_kind.value,
            "polarity": self.polarity,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
            "load_verifications": [
                {
                    "load": lv.load_resistance.format(),
                    "v_original": lv.v_port_original.format(),
                    "i_original": lv.i_port_original.format(),
                    "v_norton": lv.v_port_equivalent.format(),
                    "i_norton": lv.i_port_equivalent.format(),
                    "passed": lv.passed,
                }
                for lv in self.load_verifications
            ],
        }


@dataclass(frozen=True)
class OnePortEquivalent:
    """Unified two-terminal one-port representation combining Thevenin and Norton models."""

    status: EquivalentStatus
    port: TheveninPort
    thevenin: TheveninResult
    norton: NortonResult
    is_equivalent: bool
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "port": {"positive": self.port.positive_terminal, "negative": self.port.negative_terminal},
            "thevenin": self.thevenin.to_dict(),
            "norton": self.norton.to_dict(),
            "is_equivalent": self.is_equivalent,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
        }
