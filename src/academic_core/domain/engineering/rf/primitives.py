"""F8-P3 RF primitives (NEW): frequency/period/wavelength, phasors,
impedance/admittance categories, complex power.

Conventions frozen by the design gate (`docs/gates/GATE-F8P3-DESIGN.md`
§6/§7/§9):

* Peak phasors under ``e^{+j*omega*t}`` are the default; RMS values are
  reached only through an explicit conversion (``peak/sqrt(2)``), never
  silently.
* ``omega`` (rad/s), the electrical length ``theta`` (rad) and the
  propagation-constant components (``alpha`` Np/m, ``beta`` rad/m) are
  documentary *labels* on a Decimal, never ``Quantity`` targets --
  ``units.parse_unit`` has no rad/deg/Np entry (repo precedent:
  ``MagnitudeResult``/``phase_unit`` elsewhere use plain labelled
  values, not ``Quantity``).
* Impedance/admittance follow the F8-D5 ``FINITE/INFINITE/UNDEFINED``
  vocabulary (own small enum here -- ``rf`` cannot import ``ac/``,
  which is upstream of ``control``/``math``/``units`` in the DAG, so
  the vocabulary is mirrored, not imported, per gate §9/§26).

No floating-point or third-party numeric library anywhere in this
package; all arithmetic
goes through ``DecimalComplex``/``Decimal`` under the certified
``math.*`` kernels.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    complex_from_polar,
    decimal_pi,
    make_context,
)
from academic_core.domain.engineering.units import (
    FREQUENCY,
    LENGTH,
    POWER,
    Quantity,
    Unit,
    parse_unit,
)

ENGINE_VERSION = "f8p3-rf/1"


def _require_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, f"{name} must be a Decimal")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


def frequency(f: Decimal) -> Quantity:
    """f > 0, Hz."""
    f = _require_decimal(f, "frequency")
    if f <= 0:
        raise ControlError(ControlStatus.INVALID, "frequency must be > 0")
    return Quantity(f, parse_unit("Hz"))


def angular_frequency(f: Decimal) -> Decimal:
    """omega = 2*pi*f, rad/s label (documentary, not a Quantity)."""
    freq = frequency(f)
    ctx = make_context()
    two_pi = ctx.multiply(Decimal(2), decimal_pi(ctx))
    return ctx.multiply(two_pi, freq.value)


def period(f: Decimal) -> Quantity:
    """T = 1/f, seconds."""
    freq = frequency(f)
    ctx = make_context()
    return Quantity(ctx.divide(Decimal(1), freq.value), parse_unit("s"))


def wavelength(v: Decimal, f: Decimal) -> Quantity:
    """lambda = v/f. v: phase velocity (m/s, explicit line parameter,
    never a hidden global constant); f: Hz."""
    v = _require_decimal(v, "phase velocity")
    if v <= 0:
        raise ControlError(ControlStatus.INVALID, "phase velocity must be > 0")
    freq = frequency(f)
    ctx = make_context()
    return Quantity(ctx.divide(v, freq.value), parse_unit("m"))


def phase_constant(v: Decimal, f: Decimal) -> Decimal:
    """beta = 2*pi/lambda, rad/m label."""
    lam = wavelength(v, f)
    ctx = make_context()
    two_pi = ctx.multiply(Decimal(2), decimal_pi(ctx))
    return ctx.divide(two_pi, lam.value)


class PhasorTag(str, Enum):
    PEAK = "peak"
    RMS = "rms"


@dataclass(frozen=True)
class Phasor:
    """A complex phasor under e^{+j*omega*t}. ``tag`` records whether the
    stored magnitude is peak (frozen default) or RMS (explicit
    conversion only)."""

    value: DecimalComplex
    tag: PhasorTag

    def __post_init__(self) -> None:
        if not isinstance(self.value, DecimalComplex):
            raise ControlError(ControlStatus.INVALID, "phasor value must be DecimalComplex")
        if not isinstance(self.tag, PhasorTag):
            raise ControlError(ControlStatus.INVALID, "phasor tag must be a PhasorTag")

    @staticmethod
    def from_polar(magnitude: Decimal, phase_rad: Decimal, tag: PhasorTag = PhasorTag.PEAK) -> "Phasor":
        magnitude = _require_decimal(magnitude, "phasor magnitude")
        if magnitude < 0:
            raise ControlError(ControlStatus.INVALID, "phasor magnitude must be >= 0")
        phase_rad = _require_decimal(phase_rad, "phasor phase")
        return Phasor(complex_from_polar(magnitude, phase_rad), tag)

    def to_rms(self) -> "Phasor":
        """Explicit peak -> RMS conversion (peak/sqrt(2)); magnitude domain
        only, never used inside an active solve (gate §6)."""
        if self.tag == PhasorTag.RMS:
            return self
        ctx = make_context()
        sqrt2 = ctx.sqrt(Decimal(2))
        return Phasor(
            DecimalComplex(ctx.divide(self.value.re, sqrt2), ctx.divide(self.value.im, sqrt2)),
            PhasorTag.RMS,
        )

    def to_peak(self) -> "Phasor":
        if self.tag == PhasorTag.PEAK:
            return self
        ctx = make_context()
        sqrt2 = ctx.sqrt(Decimal(2))
        return Phasor(
            DecimalComplex(ctx.multiply(self.value.re, sqrt2), ctx.multiply(self.value.im, sqrt2)),
            PhasorTag.PEAK,
        )


class ImpedanceCategory(Enum):
    """F8-D5 vocabulary mirrored (not imported -- rf never imports ac/).
    INFINITE is a behavioral open (value=None), never Decimal("Infinity")."""

    FINITE = "finite"
    INFINITE = "infinite"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class ImmittanceValue:
    """Impedance (Ω) or admittance (S) with an explicit category."""

    category: ImpedanceCategory
    value: DecimalComplex | None
    quantity: str  # "impedance" | "admittance"

    def __post_init__(self) -> None:
        if self.quantity not in ("impedance", "admittance"):
            raise ControlError(ControlStatus.INVALID, "quantity must be impedance|admittance")
        if self.category == ImpedanceCategory.FINITE and self.value is None:
            raise ControlError(ControlStatus.INVALID, "FINITE category needs a value")
        if self.category != ImpedanceCategory.FINITE and self.value is not None:
            raise ControlError(ControlStatus.INVALID, "non-FINITE category must carry value=None")

    def require_finite(self) -> DecimalComplex:
        if self.category != ImpedanceCategory.FINITE or self.value is None:
            raise ControlError(
                ControlStatus.UNSUPPORTED,
                f"no finite {self.quantity} (category {self.category.value})",
            )
        return self.value

    @property
    def unit_symbol(self) -> str:
        return "ohm" if self.quantity == "impedance" else "S"


def impedance_of(value: DecimalComplex) -> ImmittanceValue:
    if not isinstance(value, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "impedance value must be DecimalComplex")
    return ImmittanceValue(ImpedanceCategory.FINITE, value, "impedance")


def admittance_of(value: DecimalComplex) -> ImmittanceValue:
    if not isinstance(value, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "admittance value must be DecimalComplex")
    return ImmittanceValue(ImpedanceCategory.FINITE, value, "admittance")


def impedance_to_admittance(z: ImmittanceValue) -> ImmittanceValue:
    """1/Z with the F8-D5 zero-numerator/zero-denominator discipline
    (0/0 -> UNDEFINED, x/0 -> INFINITE, never Decimal('Infinity'))."""
    if z.quantity != "impedance":
        raise ControlError(ControlStatus.INVALID, "impedance_to_admittance needs an impedance")
    if z.category == ImpedanceCategory.UNDEFINED:
        return ImmittanceValue(ImpedanceCategory.UNDEFINED, None, "admittance")
    if z.category == ImpedanceCategory.INFINITE:
        return ImmittanceValue(ImpedanceCategory.FINITE, DecimalComplex.zero(), "admittance")
    assert z.value is not None
    if z.value.is_zero_exact():
        return ImmittanceValue(ImpedanceCategory.INFINITE, None, "admittance")
    return ImmittanceValue(ImpedanceCategory.FINITE, DecimalComplex.one() / z.value, "admittance")


def admittance_to_impedance(y: ImmittanceValue) -> ImmittanceValue:
    if y.quantity != "admittance":
        raise ControlError(ControlStatus.INVALID, "admittance_to_impedance needs an admittance")
    if y.category == ImpedanceCategory.UNDEFINED:
        return ImmittanceValue(ImpedanceCategory.UNDEFINED, None, "impedance")
    if y.category == ImpedanceCategory.INFINITE:
        return ImmittanceValue(ImpedanceCategory.FINITE, DecimalComplex.zero(), "impedance")
    assert y.value is not None
    if y.value.is_zero_exact():
        return ImmittanceValue(ImpedanceCategory.INFINITE, None, "impedance")
    return ImmittanceValue(ImpedanceCategory.FINITE, DecimalComplex.one() / y.value, "impedance")


@dataclass(frozen=True)
class ComplexPower:
    """S = P + jQ, frozen F8-D4 convention: S = (1/2) V * conj(I) for
    peak phasors (absorbed-uniform, P<0 delivers)."""

    s: DecimalComplex

    @property
    def p(self) -> Decimal:
        return self.s.re

    @property
    def q(self) -> Decimal:
        return self.s.im

    def apparent(self) -> Decimal:
        return self.s.modulus()

    def power_factor(self) -> Decimal | None:
        """pf = P/|S|; None iff |S| = 0 exact (F8-D4 rule, no epsilon)."""
        apparent = self.apparent()
        if apparent == 0:
            return None
        ctx = make_context()
        return ctx.divide(self.p, apparent)


def complex_power(v_peak: DecimalComplex, i_peak: DecimalComplex) -> ComplexPower:
    """S = (1/2) * V * conj(I), peak phasors under e^{+j*omega*t}."""
    if not isinstance(v_peak, DecimalComplex) or not isinstance(i_peak, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "complex_power needs DecimalComplex V and I")
    half = DecimalComplex(Decimal("0.5"), Decimal(0))
    return ComplexPower(half * v_peak * i_peak.conjugate())


def power_quantity(s: ComplexPower) -> Quantity:
    return Quantity(s.p, parse_unit("W"))
