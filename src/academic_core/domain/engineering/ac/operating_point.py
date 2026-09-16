"""Single-frequency operating point authority (F8-D3).

:class:`ACOperatingPoint` is the ONE place the operating frequency comes
from. Individual sources never carry their own frequency: if a
component's ``parameters`` dict contains frequency metadata, it must
match the operating point exactly or assembly is rejected — never
silently ignored.

Conventions frozen here:

* time dependence ``e^(+jwt)`` globally;
* amplitudes are PEAK (never RMS inside the solver);
* source phase metadata: ``parameters["phase"]`` with optional
  ``parameters["phase_unit"]`` in ``{"deg", "rad"}`` (default ``deg``,
  default phase 0);
* radian is dimensionless: no new SI dimension is introduced; Hz and
  rad/s are distinguished as quantity-vs-plain-Decimal (see below);
* ``f > 0`` with ``w = 2*pi*f`` computed as an explicitly approximate
  ``Decimal`` (transcendental — never a ``Fraction``).

Frequency ``f`` is a ``Quantity`` with the FREQUENCY dimension (Hz and
SI-prefixed forms via F6 parsing). Angular frequency ``w`` is a plain
``Decimal`` in rad/s: since radian is dimensionless, rad/s is
dimensionally identical to Hz, so a distinct ``Quantity`` dimension
would be dishonest; the unit is carried as documentation
(``angular_unit = "rad/s"``), not as physics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.ac.errors import ACFrequencyError
from academic_core.domain.engineering.units import FREQUENCY, Quantity, parse_quantity

TIME_CONVENTION = "e^(+jwt)"
AMPLITUDE_CONVENTION = "peak"
PHASE_CONVENTION = "degrees by default (rad with explicit phase_unit); phasor angle = atan2(Im, Re) in (-pi, pi]"


@dataclass(frozen=True)
class ACOperatingPoint:
    frequency: Quantity  # Hz, base value > 0
    omega: Decimal  # rad/s, explicitly approximate Decimal (2*pi*f)
    frequency_unit: str  # display symbol of the frequency quantity
    angular_unit: str  # always "rad/s" (documentary, not a dimension)
    time_convention: str  # always e^(+jwt)
    amplitude_convention: str  # always peak
    phase_convention: str
    reference_node: str  # actual ground net name as found in the circuit

    @classmethod
    def from_frequency(cls, freq: Quantity | str, reference_node: str) -> "ACOperatingPoint":
        from academic_core.domain.engineering.math.trig import decimal_pi, make_context

        q = parse_quantity(freq) if isinstance(freq, str) else freq
        if not isinstance(q, Quantity):
            raise ACFrequencyError(f"operating frequency must be a Quantity, got {type(q).__name__}")
        if q.dimension != FREQUENCY:
            raise ACFrequencyError(
                f"operating frequency must have the frequency dimension, "
                f"got {q.format()}"
            )
        f_hz = q.to_base()
        if f_hz <= 0:
            if f_hz == 0:
                raise ACFrequencyError(
                    "f = 0 is outside the AC phasor domain (steady-state AC "
                    "formulas divide by f; a formal DC reduction L->short / "
                    "C->open belongs to a future orchestrator, not to D3)"
                )
            raise ACFrequencyError(
                f"f < 0 ({q.format()}) is outside this product's declared "
                f"domain (f > 0). This is a product boundary, not a "
                f"mathematical claim: negative frequencies are meaningful "
                f"in Fourier theory."
            )
        ctx = make_context()
        omega = ctx.multiply(ctx.multiply(Decimal(2), decimal_pi()), f_hz)
        if not reference_node or not str(reference_node).strip():
            raise ACFrequencyError("reference node must be a non-empty net name")
        return cls(
            frequency=q,
            omega=omega,
            frequency_unit=q.unit.display,
            angular_unit="rad/s",
            time_convention=TIME_CONVENTION,
            amplitude_convention=AMPLITUDE_CONVENTION,
            phase_convention=PHASE_CONVENTION,
            reference_node=reference_node,
        )

    def to_dict(self) -> dict:
        return {
            "frequency": self.frequency.format(),
            "frequency_base_hz": str(self.frequency.to_base()),
            "angular_frequency_rad_per_s": str(self.omega),
            "frequency_unit": self.frequency_unit,
            "angular_unit": self.angular_unit,
            "time_convention": self.time_convention,
            "amplitude_convention": self.amplitude_convention,
            "phase_convention": self.phase_convention,
            "reference_node": self.reference_node,
        }
