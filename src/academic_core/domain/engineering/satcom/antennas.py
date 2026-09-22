"""F8-P5 ideal-aperture antennas (NEW).

Closed identities only: Ae = G*lambda^2/(4*pi), G = eta*4*pi*A/lambda^2
(circular A = pi*D^2/4). Gain input (dBi) XOR aperture-derived
(diameter + efficiency) — never both silently. dBd converts with the
fixed +2.15 dB dipole reference. Beamwidth ~70*lambda/D is a labelled
APPROXIMATION (MetricResult kind), never an exact pattern claim.
No EM solver, no patterns, no tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.metrics import (
    APPROXIMATION,
    EXACT,
    MetricResult,
    to_db10,
)
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import decimal_pi, decimal_sqrt, make_context
from academic_core.domain.engineering.satcom.constants import check_magnitude

DBD_TO_DBI_OFFSET = Decimal("2.15")
MAX_ANTENNAS_PER_LEG = 2


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _positive(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise _fail(ControlStatus.INVALID, label + " must be Decimal/int/str")
    return check_magnitude(out, label)


def dbd_to_dbi(gain_dbd: Decimal) -> Decimal:
    """dBi = dBd + 2.15 (fixed half-wave-dipole reference)."""
    if isinstance(gain_dbd, bool) or not isinstance(gain_dbd, Decimal):
        raise _fail(ControlStatus.INVALID, "dBd gain must be Decimal")
    if not gain_dbd.is_finite():
        raise _fail(ControlStatus.INVALID, "dBd gain must be finite")
    return make_context().add(gain_dbd, DBD_TO_DBI_OFFSET)


def dbi_to_dbd(gain_dbi: Decimal) -> Decimal:
    """dBd = dBi - 2.15 (fixed half-wave-dipole reference)."""
    if isinstance(gain_dbi, bool) or not isinstance(gain_dbi, Decimal):
        raise _fail(ControlStatus.INVALID, "dBi gain must be Decimal")
    if not gain_dbi.is_finite():
        raise _fail(ControlStatus.INVALID, "dBi gain must be finite")
    return make_context().subtract(gain_dbi, DBD_TO_DBI_OFFSET)


def circular_area_m2(diameter_m: Decimal) -> Decimal:
    """A = pi*D^2/4 (m^2), D > 0."""
    diam = _positive(diameter_m, "dish diameter")
    ctx = make_context()
    return ctx.divide(ctx.multiply(decimal_pi(ctx), ctx.multiply(diam, diam)), Decimal(4))


def gain_linear_from_aperture(area_m2: Decimal, wavelength_m: Decimal,
                              efficiency: Decimal) -> Decimal:
    """G = eta*4*pi*A/lambda^2 (linear), 0 < eta <= 1."""
    area = _positive(area_m2, "aperture area")
    wave = _positive(wavelength_m, "wavelength")
    if isinstance(efficiency, bool) or not isinstance(efficiency, Decimal):
        raise _fail(ControlStatus.INVALID, "efficiency must be Decimal")
    if not efficiency.is_finite() or efficiency <= 0 or efficiency > 1:
        raise _fail(ControlStatus.INVALID, "efficiency in (0, 1] required")
    ctx = make_context()
    numer = ctx.multiply(ctx.multiply(ctx.multiply(Decimal(4), decimal_pi(ctx)), area),
                         efficiency)
    return ctx.divide(numer, ctx.multiply(wave, wave))


def aperture_from_gain_linear(gain_linear: Decimal, wavelength_m: Decimal) -> Decimal:
    """Ae = G*lambda^2/(4*pi) (m^2), inverse identity of the above."""
    gain = _positive(gain_linear, "linear gain")
    wave = _positive(wavelength_m, "wavelength")
    ctx = make_context()
    return ctx.divide(ctx.multiply(gain, ctx.multiply(wave, wave)),
                      ctx.multiply(Decimal(4), decimal_pi(ctx)))


def beamwidth_approx_deg(diameter_m: Decimal, wavelength_m: Decimal) -> MetricResult:
    """APPROXIMATION theta_3dB ~= 70*lambda/D (degrees, circular aperture)."""
    diam = _positive(diameter_m, "dish diameter")
    wave = _positive(wavelength_m, "wavelength")
    ctx = make_context()
    value = ctx.divide(ctx.multiply(Decimal(70), wave), diam)
    return MetricResult(value=value, kind=APPROXIMATION)


def gain_kind_result(value_db: Decimal) -> MetricResult:
    """Wrap an exact gain figure with its EXACT kind tag."""
    if isinstance(value_db, bool) or not isinstance(value_db, Decimal):
        raise _fail(ControlStatus.INVALID, "gain must be Decimal dB")
    if not value_db.is_finite():
        raise _fail(ControlStatus.INVALID, "gain must be finite")
    return MetricResult(value=value_db, kind=EXACT)


@dataclass(frozen=True)
class Antenna:
    """One antenna: gain_dbi XOR (diameter_m + efficiency); never both."""

    gain_dbi: Decimal | None = None
    diameter_m: Decimal | None = None
    efficiency: Decimal | None = None
    gain_kind: str = "dBi"

    def __post_init__(self) -> None:
        has_gain = self.gain_dbi is not None
        has_dish = self.diameter_m is not None or self.efficiency is not None
        if has_gain and has_dish:
            raise _fail(ControlStatus.INVALID, "antenna: gain XOR aperture, not both")
        if not has_gain and not has_dish:
            raise _fail(ControlStatus.INVALID, "antenna needs gain or aperture")
        if self.gain_kind not in ("dBi", "dBd"):
            raise _fail(ControlStatus.INVALID, "antenna gain_kind must be dBi/dBd")
        if has_gain:
            if isinstance(self.gain_dbi, bool) or not isinstance(self.gain_dbi, Decimal):
                raise _fail(ControlStatus.INVALID, "antenna gain must be Decimal")
            if not self.gain_dbi.is_finite():
                raise _fail(ControlStatus.INVALID, "antenna gain must be finite")
        else:
            if self.diameter_m is None or self.efficiency is None:
                raise _fail(ControlStatus.INVALID, "aperture needs diameter + efficiency")
            _positive(self.diameter_m, "dish diameter")
            if isinstance(self.efficiency, bool) or not isinstance(self.efficiency, Decimal):
                raise _fail(ControlStatus.INVALID, "efficiency must be Decimal")
            if (not self.efficiency.is_finite() or self.efficiency <= 0
                    or self.efficiency > 1):
                raise _fail(ControlStatus.INVALID, "efficiency in (0, 1] required")

    def gain_dbi_value(self, wavelength_m: Decimal) -> Decimal:
        """Resolve to dBi (linear-domain exact conversion for aperture form)."""
        if self.gain_dbi is not None:
            if self.gain_kind == "dBi":
                return self.gain_dbi
            return dbd_to_dbi(self.gain_dbi)
        wave = _positive(wavelength_m, "wavelength")
        area = circular_area_m2(self.diameter_m)
        assert self.efficiency is not None
        glin = gain_linear_from_aperture(area, wave, self.efficiency)
        return to_db10(glin)
