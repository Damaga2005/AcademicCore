# SPDX-License-Identifier: MIT
"""F16 central bodies (NEW): structured, validated, traceable.

A body is ``name + mass + radius + mu + provenance``. ``mu`` defaults to
the derived ``G*M`` (single formula in ``constants``); the Earth preset
pins the conventional mu. No silent defaults for user bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.orbital import constants as C


def _positive_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ControlError(ControlStatus.INVALID, label + " must be finite and > 0")
    return value


@dataclass(frozen=True)
class CentralBody:
    name: str
    mass_kg: Decimal
    radius_m: Decimal
    mu_m3_s2: Decimal
    provenance: str

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ControlError(ControlStatus.INVALID, "body name must be non-empty")
        _positive_decimal(self.mass_kg, "mass")
        _positive_decimal(self.radius_m, "radius")
        _positive_decimal(self.mu_m3_s2, "mu")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ControlError(ControlStatus.INVALID, "provenance must be non-empty")


def make_body(name: str, mass_kg: Decimal, radius_m: Decimal,
              provenance: str, mu_m3_s2: Decimal | None = None) -> CentralBody:
    """User body: mu defaults to derived G*M (documented, not silent)."""
    mass = _positive_decimal(mass_kg, "mass")
    radius = _positive_decimal(radius_m, "radius")
    mu = C.gravitational_parameter(mass) if mu_m3_s2 is None else _positive_decimal(mu_m3_s2, "mu")
    return CentralBody(str(name), mass, radius, mu, str(provenance))


EARTH = CentralBody(
    name="Earth",
    mass_kg=C.EARTH_MASS_KG,
    radius_m=C.EARTH_RADIUS_M,
    mu_m3_s2=C.EARTH_MU_M3_S2,
    provenance=C.EARTH_PROVENANCE,
)
