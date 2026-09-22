"""F8-P5 physical constants + wavelength (NEW).

Exact SI constants with provenance (grep-proved absent from the repo):
c = 299792458 m/s exact, k = 1.380649e-23 J/K exact. Wavelength
lambda = c/f. No second constants engine exists; Prompt 2 reuses these.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import make_context

SPEED_OF_LIGHT_M_S = Decimal(299792458)
BOLTZMANN_J_K = Decimal("1.380649E-23")

MAX_MAGNITUDE = Decimal("1E+30")


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def speed_of_light() -> Decimal:
    """c = 299792458 m/s exact (SI defining constant)."""
    return SPEED_OF_LIGHT_M_S


def boltzmann_k() -> Decimal:
    """k = 1.380649e-23 J/K exact (SI defining constant)."""
    return BOLTZMANN_J_K


def check_magnitude(value: Decimal, label: str) -> Decimal:
    """Finite Decimal within (0, 1e30]; violations rejected, never clipped."""
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise _fail(ControlStatus.INVALID, label + " must be Decimal")
    if not value.is_finite() or value <= 0 or value > MAX_MAGNITUDE:
        raise _fail(ControlStatus.INVALID, label + " must be finite in (0, 1e30]")
    return value


def wavelength_m(freq_hz: object) -> Decimal:
    """lambda = c/f (m), f > 0 finite Hz."""
    if isinstance(freq_hz, bool):
        raise _fail(ControlStatus.INVALID, "frequency rejects bool")
    if isinstance(freq_hz, Decimal):
        freq = freq_hz
    elif isinstance(freq_hz, int):
        freq = Decimal(freq_hz)
    elif isinstance(freq_hz, str):
        try:
            freq = Decimal(freq_hz.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad frequency string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "frequency must be Decimal/int/str")
    check_magnitude(freq, "frequency")
    return make_context().divide(SPEED_OF_LIGHT_M_S, freq)
