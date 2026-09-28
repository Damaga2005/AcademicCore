# SPDX-License-Identifier: MIT
"""F16 classical orbital elements (NEW): documented conventions, digest.

Conventions (documented, fixed):

- ``a``: semimajor axis, m, > 0.
- ``e``: eccentricity, 0 <= e < 1 (bound ellipse).
- ``i``: inclination, rad, 0 <= i <= pi.
- ``omega`` (Omega): right ascension of the ascending node, rad, [0, 2pi).
- ``argp`` (omega): argument of periapsis, rad, [0, 2pi).
- ``nu``: true anomaly, rad, [0, 2pi).
- ``frame``: reference frame tag, closed set ``ECI`` (inertial,
  Earth-centred, J2000 axes) | ``ORBITAL`` (perifocal plane coordinates).
  No frame transformations are implemented (out of scope by contract);
  the tag only prevents silent mixing.

Digest ``f16-elements/1`` over the canonical Decimal spellings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus

SCHEMA = "f16-elements/1"
FRAMES = ("ECI", "ORBITAL")


def _req_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, label + " must be finite")
    return value


def _req_angle(value: object, label: str, lo: Decimal, hi: Decimal,
               lo_ok: bool, hi_ok: bool) -> Decimal:
    v = _req_decimal(value, label)
    bad_lo = v < lo if lo_ok else v <= lo
    bad_hi = v > hi if hi_ok else v >= hi
    if bad_lo or bad_hi:
        raise ControlError(ControlStatus.INVALID, label + " out of range")
    return v


@dataclass(frozen=True)
class ClassicalElements:
    a_m: Decimal
    e: Decimal
    i_rad: Decimal
    omega_rad: Decimal
    argp_rad: Decimal
    nu_rad: Decimal
    frame: str = "ECI"

    def __post_init__(self):
        from academic_core.domain.engineering.math import decimal_pi
        pi = decimal_pi()
        two_pi = pi * 2
        if isinstance(self.a_m, bool) or not isinstance(self.a_m, Decimal) \
                or not self.a_m.is_finite() or self.a_m <= 0:
            raise ControlError(ControlStatus.INVALID, "a must be Decimal > 0")
        if isinstance(self.e, bool) or not isinstance(self.e, Decimal) \
                or not self.e.is_finite() or self.e < 0 or self.e >= 1:
            raise ControlError(ControlStatus.INVALID, "e must satisfy 0 <= e < 1")
        _req_angle(self.i_rad, "inclination", Decimal(0), pi, True, True)
        for label, v in (("omega", self.omega_rad), ("argp", self.argp_rad),
                         ("nu", self.nu_rad)):
            _req_angle(v, label, Decimal(0), two_pi, True, False)
        if self.frame not in FRAMES:
            raise ControlError(ControlStatus.INVALID,
                               f"frame must be one of {list(FRAMES)}")

    def to_dict(self) -> dict:
        return {"a_m": str(self.a_m), "argp_rad": str(self.argp_rad), "e": str(self.e),
                "frame": self.frame, "i_rad": str(self.i_rad),
                "nu_rad": str(self.nu_rad), "omega_rad": str(self.omega_rad),
                "schema": SCHEMA}

    def digest(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
