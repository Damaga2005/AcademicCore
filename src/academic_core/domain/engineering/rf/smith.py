"""F8-P3 Smith mathematics (NEW): math only, no graphics (gate §17).

One engine (the Mobius map + inversion) shared by z-plane, y-plane and
matching (gate §17/§18: "one engine, two views" -- matching reads the
same closed forms through Gamma).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_sin,
    make_context,
)

ENGINE_VERSION = "f8p3-rf/1"


def _check_finite(z: DecimalComplex, name: str) -> DecimalComplex:
    if not isinstance(z, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, f"{name} must be DecimalComplex")
    if not z.re.is_finite() or not z.im.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return z


def normalize(z: DecimalComplex, z0: DecimalComplex) -> DecimalComplex:
    """z_normalized = Z/Z0."""
    _check_finite(z, "Z")
    _check_finite(z0, "Z0")
    if z0.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "normalize singular: Z0 == 0")
    return z / z0


def denormalize(z_norm: DecimalComplex, z0: DecimalComplex) -> DecimalComplex:
    """Z = z_normalized * Z0."""
    _check_finite(z_norm, "z_normalized")
    _check_finite(z0, "Z0")
    return z_norm * z0


def z_to_gamma(z_norm: DecimalComplex) -> DecimalComplex:
    """Gamma = (z-1)/(z+1); z -> infinity handled by the caller as the
    ``open`` load kind (never a numeric huge value here)."""
    _check_finite(z_norm, "z_normalized")
    one = DecimalComplex.one()
    denom = z_norm + one
    if denom.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "z -> Gamma singular (z == -1)")
    return (z_norm - one) / denom


def gamma_to_z(gamma: DecimalComplex) -> DecimalComplex:
    """z = (1+Gamma)/(1-Gamma); Gamma = 1 -> SINGULAR (open, represented
    by the caller as a behavioral infinity, not this function)."""
    _check_finite(gamma, "Gamma")
    one = DecimalComplex.one()
    denom = one - gamma
    if denom.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Gamma -> z singular (Gamma == 1)")
    return (one + gamma) / denom


def z_to_gamma_full(z: DecimalComplex, z0: DecimalComplex) -> DecimalComplex:
    """Gamma directly from unnormalized Z (Z -> z -> Gamma, same map)."""
    return z_to_gamma(normalize(z, z0))


def gamma_to_z_full(gamma: DecimalComplex, z0: DecimalComplex) -> DecimalComplex:
    return denormalize(gamma_to_z(gamma), z0)


def y_to_gamma(y_norm: DecimalComplex) -> DecimalComplex:
    """Gamma_y via the SAME Mobius map applied to the normalized
    admittance y = Y/Y0 = 1/z (shared helper, one engine)."""
    one = DecimalComplex.one()
    if y_norm.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "y -> Gamma singular (y == 0, i.e. z -> infinity)")
    z_norm = one / y_norm
    return z_to_gamma(z_norm)


def gamma_to_y(gamma: DecimalComplex) -> DecimalComplex:
    """y = 1/z = 1/gamma_to_z(Gamma)."""
    z_norm = gamma_to_z(gamma)
    if z_norm.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Gamma -> y singular (z == 0)")
    return DecimalComplex.one() / z_norm


@dataclass(frozen=True)
class RCircle:
    """Constant-resistance circle |Gamma - r/(r+1)| = 1/(r+1)."""

    r: Decimal
    center: DecimalComplex
    radius: Decimal


def resistance_circle(r: Decimal, ctx=None) -> RCircle:
    c = ctx or make_context()
    if r < 0:
        raise ControlError(ControlStatus.INVALID, "resistance circle needs r >= 0")
    denom = c.add(r, Decimal(1))
    if denom == 0:
        raise ControlError(ControlStatus.SINGULAR, "resistance circle singular (r == -1)")
    center = DecimalComplex(c.divide(r, denom), Decimal(0))
    radius = c.divide(Decimal(1), denom)
    return RCircle(r, center, radius)


def on_resistance_circle(gamma: DecimalComplex, circle: RCircle, tolerance: Decimal, ctx=None) -> bool:
    c = ctx or make_context()
    dist = (gamma - circle.center).modulus()
    return c.subtract(dist, circle.radius).copy_abs() <= tolerance


@dataclass(frozen=True)
class XCircle:
    """Constant-reactance circle |Gamma - (1+j/x)| = 1/|x|."""

    x: Decimal
    center: DecimalComplex
    radius: Decimal


def reactance_circle(x: Decimal, ctx=None) -> XCircle:
    c = ctx or make_context()
    if x == 0:
        raise ControlError(ControlStatus.SINGULAR, "reactance circle singular (x == 0)")
    center = DecimalComplex(Decimal(1), c.divide(Decimal(1), x))
    radius = c.divide(Decimal(1), x.copy_abs())
    return XCircle(x, center, radius)


def on_reactance_circle(gamma: DecimalComplex, circle: XCircle, tolerance: Decimal, ctx=None) -> bool:
    c = ctx or make_context()
    dist = (gamma - circle.center).modulus()
    return c.subtract(dist, circle.radius).copy_abs() <= tolerance


def rotate_along_line(gamma_load: DecimalComplex, gamma: DecimalComplex, length: Decimal, ctx=None) -> DecimalComplex:
    """Gamma(l) = Gamma_L * e^{-2*gamma*l} (line movement, gate §17).
    Lossless (gamma purely imaginary) is a pure rotation by angle
    -2*beta*l -- reuses the same complex-exponential helper, no
    separate rotation-only implementation."""
    c = ctx or make_context()
    _check_finite(gamma_load, "Gamma_L")
    exponent = DecimalComplex(c.multiply(Decimal(-2), c.multiply(gamma.re, length)), c.multiply(Decimal(-2), c.multiply(gamma.im, length)))
    ea = decimal_exp(exponent.re, c)
    factor = DecimalComplex(c.multiply(ea, decimal_cos(exponent.im, c)), c.multiply(ea, decimal_sin(exponent.im, c)))
    return gamma_load * factor
