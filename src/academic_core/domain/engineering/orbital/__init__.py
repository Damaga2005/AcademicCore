# SPDX-License-Identifier: MIT
"""F16 orbital mechanics: deterministic two-body content (NEW).

Pure Decimal two-body mechanics over SI units. Reuses the certified
``math`` package (50-digit context, sqrt/cbrt/trig/pi) and the ``units``
dimensions; owns no Knowledge rows and duplicates nothing from F8-P5
Satcom (link budgets take distance as input; this package computes
orbital motion).
"""

from academic_core.domain.engineering.orbital.bodies import EARTH, CentralBody, make_body
from academic_core.domain.engineering.orbital.constants import (
    EARTH_MASS_KG,
    EARTH_MU_M3_S2,
    EARTH_PROVENANCE,
    EARTH_RADIUS_M,
    G_NEWTON,
    G_PROVENANCE,
    gravitational_parameter,
    newton_g,
)
from academic_core.domain.engineering.orbital.elements import (
    FRAMES,
    SCHEMA as ELEMENTS_SCHEMA,
    ClassicalElements,
)
from academic_core.domain.engineering.orbital.kepler import (
    eccentric_from_mean_rad,
    eccentric_from_true_rad,
    mean_from_eccentric_rad,
    true_from_eccentric_rad,
)
from academic_core.domain.engineering.orbital.orbits import (
    altitude_from_radius_m,
    apoapsis_m,
    circular_period_s,
    circular_velocity_m_s,
    day_to_s,
    deg_to_rad,
    ellipse_from_apsides_m,
    escape_velocity_m_s,
    hour_to_s,
    kinetic_energy_j,
    km_to_m,
    m_to_km,
    minute_to_s,
    periapsis_m,
    period_from_radius_s,
    potential_energy_j,
    radius_from_altitude_m,
    radius_from_period_m,
    specific_energy_j_kg,
    total_energy_j,
    vis_viva_semimajor_m,
    vis_viva_velocity_m_s,
)

ENGINE_VERSION = "f16-orbital/1"

__all__ = [
    "ENGINE_VERSION",
    "EARTH", "CentralBody", "make_body",
    "G_NEWTON", "G_PROVENANCE", "EARTH_MASS_KG", "EARTH_RADIUS_M",
    "EARTH_MU_M3_S2", "EARTH_PROVENANCE", "newton_g", "gravitational_parameter",
    "radius_from_altitude_m", "altitude_from_radius_m",
    "circular_velocity_m_s", "circular_period_s", "period_from_radius_s",
    "radius_from_period_m", "vis_viva_velocity_m_s", "vis_viva_semimajor_m",
    "kinetic_energy_j", "potential_energy_j", "total_energy_j",
    "specific_energy_j_kg", "escape_velocity_m_s",
    "periapsis_m", "apoapsis_m", "ellipse_from_apsides_m",
    "eccentric_from_mean_rad", "mean_from_eccentric_rad",
    "true_from_eccentric_rad", "eccentric_from_true_rad",
    "ClassicalElements", "FRAMES", "ELEMENTS_SCHEMA",
    "km_to_m", "m_to_km", "day_to_s", "hour_to_s", "minute_to_s", "deg_to_rad",
]
