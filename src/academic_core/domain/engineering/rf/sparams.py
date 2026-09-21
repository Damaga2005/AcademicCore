"""F8-P3 S-parameters (NEW): Kurokawa power waves, S<->ABCD, T
(scattering-transfer) as a derived view.

Convention: one unified Kurokawa formula for real and complex
reference impedance (gate §14):

    a_i = (V_i + Zref*I_i) / (2*sqrt(Re(Zref)))
    b_i = (V_i - conj(Zref)*I_i) / (2*sqrt(Re(Zref)))

``Re(Zref) > 0`` required, else INVALID (evanescent/complex-plane
references OUT). No alternative convention is substituted.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, decimal_sqrt, make_context
from academic_core.domain.engineering.rf.networks import TwoPort

ENGINE_VERSION = "f8p3-rf/1"

DEFAULT_REFERENCE = DecimalComplex(Decimal(50), Decimal(0))


def _check_reference(zref: DecimalComplex) -> None:
    if not isinstance(zref, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "reference impedance must be DecimalComplex")
    if not zref.re.is_finite() or not zref.im.is_finite():
        raise ControlError(ControlStatus.INVALID, "reference impedance must be finite")
    if zref.re <= 0:
        raise ControlError(ControlStatus.INVALID, "reference impedance needs Re(Zref) > 0")


def power_waves(v: DecimalComplex, i: DecimalComplex, zref: DecimalComplex, ctx=None) -> tuple:
    """(a, b) Kurokawa power waves at one port."""
    c = ctx or make_context()
    _check_reference(zref)
    two_sqrt_re = c.multiply(Decimal(2), decimal_sqrt(zref.re, c))
    a = (v + zref * i) / DecimalComplex(two_sqrt_re, Decimal(0))
    b = (v - zref.conjugate() * i) / DecimalComplex(two_sqrt_re, Decimal(0))
    return a, b


@dataclass(frozen=True)
class SParameters:
    """S = [[S11, S12], [S21, S22]] with an explicit reference
    impedance carried on the object (default 50 ohm exact Decimal)."""

    s11: DecimalComplex
    s12: DecimalComplex
    s21: DecimalComplex
    s22: DecimalComplex
    reference: DecimalComplex = DEFAULT_REFERENCE

    def __post_init__(self) -> None:
        _check_reference(self.reference)
        for name, val in (("s11", self.s11), ("s12", self.s12), ("s21", self.s21), ("s22", self.s22)):
            if not isinstance(val, DecimalComplex) or not val.re.is_finite() or not val.im.is_finite():
                raise ControlError(ControlStatus.INVALID, f"{name} must be finite DecimalComplex")

    def matrix_vector(self, a1: DecimalComplex, a2: DecimalComplex, ctx=None) -> tuple:
        """b = S*a."""
        b1 = self.s11 * a1 + self.s12 * a2
        b2 = self.s21 * a1 + self.s22 * a2
        return b1, b2

    def is_reciprocal(self) -> bool:
        """S12 == S21 exact."""
        return self.s12 == self.s21

    def is_symmetric(self) -> bool:
        return self.s11 == self.s22

    def is_matched(self, tolerance: Decimal) -> bool:
        return self.s11.is_zero(tolerance) and self.s22.is_zero(tolerance)

    def unitarity_residual(self, ctx=None) -> Decimal:
        """||S^dagger S - I|| (Frobenius-style, sum of squared-modulus
        entries) -- exactly 0 for a lossless network within the
        certified tolerance (gate §8: <=1e-40)."""
        c = ctx or make_context()
        sh11 = self.s11.conjugate()
        sh12 = self.s21.conjugate()
        sh21 = self.s12.conjugate()
        sh22 = self.s22.conjugate()
        p11 = sh11 * self.s11 + sh12 * self.s21
        p12 = sh11 * self.s12 + sh12 * self.s22
        p21 = sh21 * self.s11 + sh22 * self.s21
        p22 = sh21 * self.s12 + sh22 * self.s22
        d11 = p11 - DecimalComplex.one()
        d22 = p22 - DecimalComplex.one()
        total = c.add(
            c.add(d11.squared_modulus(), p12.squared_modulus()),
            c.add(p21.squared_modulus(), d22.squared_modulus()),
        )
        return c.sqrt(total)


def identity_passthrough(reference: DecimalComplex = DEFAULT_REFERENCE) -> SParameters:
    """S = [[0,1],[1,0]] exact -- ideal matched through connection."""
    zero = DecimalComplex.zero()
    one = DecimalComplex.one()
    return SParameters(zero, one, one, zero, reference)


def s_to_abcd(s: SParameters, ctx=None) -> TwoPort:
    """S -> ABCD requires S21 != 0 (SINGULAR otherwise -- unilateral/
    isolated network, gate §15). Standard formulas at a real or
    complex reference Zref, generalised via the Kurokawa convention:
    at equal ports referenced to the same Zref the classical real-Z0
    conversion formulas hold verbatim (Zref cancels in ratios)."""
    if s.s21.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "S -> ABCD singular (S21 == 0)")
    c = ctx or make_context()
    z0 = s.reference
    one = DecimalComplex.one()
    det_s = s.s11 * s.s22 - s.s12 * s.s21
    a = ((one + s.s11) * (one - s.s22) + s.s12 * s.s21) / (DecimalComplex(Decimal(2), Decimal(0)) * s.s21)
    b = z0 * (((one + s.s11) * (one + s.s22) - s.s12 * s.s21) / (DecimalComplex(Decimal(2), Decimal(0)) * s.s21))
    cc = (((one - s.s11) * (one - s.s22) - s.s12 * s.s21) / (DecimalComplex(Decimal(2), Decimal(0)) * s.s21)) / z0
    d = ((one - s.s11) * (one + s.s22) + s.s12 * s.s21) / (DecimalComplex(Decimal(2), Decimal(0)) * s.s21)
    return TwoPort("abcd", a, b, cc, d)


def abcd_to_s(m: TwoPort, reference: DecimalComplex = DEFAULT_REFERENCE, ctx=None) -> SParameters:
    """ABCD -> S requires (A + B/Z0 + C*Z0 + D) != 0 (SINGULAR
    otherwise, gate §15)."""
    _check_reference(reference)
    if m.kind != "abcd":
        raise ControlError(ControlStatus.INVALID, "abcd_to_s needs an abcd two-port")
    z0 = reference
    denom = m.a11 + m.a12 / z0 + m.a21 * z0 + m.a22
    if denom.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "ABCD -> S singular (zero denominator)")
    det = m.determinant()
    two = DecimalComplex(Decimal(2), Decimal(0))
    s11 = (m.a11 + m.a12 / z0 - m.a21 * z0 - m.a22) / denom
    s12 = two * det / denom
    s21 = two / denom
    s22 = (-m.a11 + m.a12 / z0 - m.a21 * z0 + m.a22) / denom
    return SParameters(s11, s12, s21, s22, z0)


@dataclass(frozen=True)
class TMatrix:
    """Scattering-transfer (T) matrix, a derived view of S for chain
    reasoning only (gate §5/§15: never a separate engine, never used
    for cascading -- ABCD carries the cascade contract per §16)."""

    t11: DecimalComplex
    t12: DecimalComplex
    t21: DecimalComplex
    t22: DecimalComplex


def s_to_t(s: SParameters) -> TMatrix:
    """T11=-det(S)/S21, T12=S11/S21, T21=-S22/S21, T22=1/S21."""
    if s.s21.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "S -> T singular (S21 == 0)")
    det = s.s11 * s.s22 - s.s12 * s.s21
    return TMatrix(-det / s.s21, s.s11 / s.s21, -s.s22 / s.s21, DecimalComplex.one() / s.s21)


def t_to_s(t: TMatrix, reference: DecimalComplex = DEFAULT_REFERENCE) -> SParameters:
    """Inverse of ``s_to_t``: S11=T12/T22, S12=(T11*T22-T12*T21)/T22,
    S21=1/T22, S22=-T21/T22."""
    if t.t22.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "T -> S singular (T22 == 0)")
    det = t.t11 * t.t22 - t.t12 * t.t21
    return SParameters(
        t.t12 / t.t22, det / t.t22, DecimalComplex.one() / t.t22, -t.t21 / t.t22, reference
    )
