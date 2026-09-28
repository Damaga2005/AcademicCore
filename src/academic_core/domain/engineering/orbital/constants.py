# SPDX-License-Identifier: MIT
"""F16 physical constants with provenance (NEW, no second engine).

Exact SI defining constants are exact; measured constants carry their
reference provenance (value + source, never invented):

- ``G``: Newtonian constant of gravitation, CODATA 2018
  (6.67430e-11 m^3 kg^-1 s^-2, relative uncertainty 2.2e-5).
- Earth mass/radius: IAU / IERS conventional reference values.
- ``mu`` (standard gravitational parameter) is DERIVED as ``G*M``
  (single formula, single place), except the Earth preset which pins the
  conventional ``mu_Earth = 398600.4418 km^3/s^2`` for pedagogy.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus

# G = 6.67430e-11 m^3 kg^-1 s^-2 (CODATA 2018, exact decimal spelling).
G_NEWTON = Decimal("6.67430E-11")
G_PROVENANCE = "CODATA 2018: 6.67430e-11 m^3 kg^-1 s^-2"

# Earth: mean radius 6371.0 km (IUGG), mass 5.97237e24 kg (IAU 2015
# nominal GM-based), mu 398600.4418 km^3/s^2 (IERS Conventions).
EARTH_MASS_KG = Decimal("5.97237E24")
EARTH_RADIUS_M = Decimal("6371000")
EARTH_MU_M3_S2 = Decimal("398600441800000")  # 398600.4418 km^3/s^2
EARTH_PROVENANCE = ("IAU 2015 / IERS Conventions / IUGG mean radius: "
                    "M=5.97237e24 kg, R=6371.0 km, mu=398600.4418 km^3/s^2")


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def newton_g() -> Decimal:
    """G = 6.67430e-11 m^3 kg^-1 s^-2 (CODATA 2018)."""
    return G_NEWTON


def gravitational_parameter(mass_kg: Decimal) -> Decimal:
    """mu = G*M (m^3/s^2). The only place mu is derived from mass."""
    if isinstance(mass_kg, bool) or not isinstance(mass_kg, Decimal):
        raise _fail(ControlStatus.INVALID, "mass must be Decimal")
    if not mass_kg.is_finite() or mass_kg <= 0:
        raise _fail(ControlStatus.INVALID, "mass must be finite and > 0")
    from academic_core.domain.engineering.math import make_context
    return make_context().multiply(G_NEWTON, mass_kg)
