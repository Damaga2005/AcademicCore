"""Typed errors for the F8-D3 General AC MNA engine.

Failure modes shared with the DC world reuse the F8-B hierarchy
unchanged (same rules, same exception types — the engine never invents
a second ground rule or a second dimensionality rule):

* ``MissingReferenceError`` — no (or ambiguous) 0/GND net;
* ``FloatingCircuitError`` — nets unreachable from ground;
* ``InvalidCircuitError`` — malformed circuit or out-of-range parameter;
* ``UnsupportedElementError`` — types outside the ideal R/L/C/V/I domain;
* ``DimensionalityError`` — value with the wrong physical dimension.

Mathematical states (SOLVED / SINGULAR / INCONSISTENT /
NUMERICALLY_UNCERTAIN / INVALID / UNSUPPORTED) travel in-band on
``ACSolution``; only genuinely invalid input raises. AC-specific input
failures are below.
"""

from __future__ import annotations

from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)

__all__ = [
    "CircularControlError",
    "DimensionalityError",
    "FloatingCircuitError",
    "InvalidCircuitError",
    "MissingReferenceError",
    "UnsupportedElementError",
    "ACFrequencyError",
    "ACPhaseError",
    "ACModeError",
]


class ACFrequencyError(ValueError):
    """Raised for operating frequencies outside the AC phasor domain.

    ``f = 0`` is rejected (steady-state AC formulas divide by ``f``; a
    formal DC reduction L→short / C→open belongs to a future
    orchestrator, not to D3), as is ``f < 0`` (product boundary — not a
    mathematical claim: negative frequencies are meaningful in Fourier
    theory but out of this product's declared domain).
    """


class ACPhaseError(ValueError):
    """Raised for source phase metadata that is missing-malformed: unknown
    unit, unparseable value, NaN-like content, or float input (rejected
    at the exactness boundary like everywhere else in F8-D)."""


class ACModeError(ValueError):
    """Raised when EXACT mode is requested but the problem cannot be
    represented exactly (any L/C with f > 0 brings in π; any
    non-axis-aligned or radian-unit phase brings in irrationals).

    Mirrors the D2 rule that EXACT on decimal data is refused: solving
    rounded data and calling it exact would fake exactness.
    """
