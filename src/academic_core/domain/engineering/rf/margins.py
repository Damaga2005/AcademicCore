"""F8-P3 RF margins (NEW): VSWR, Return Loss, Insertion Loss, Mismatch
Loss, Transducer Gain (GT), Rollett K/mu stability.

Every formula matches gate §6/§19; domains are explicit, singular
edges return typed statuses (never ``Infinity``/``NaN``). dB values
are dimensionless display labels (never ``Quantity`` targets, gate
§7) computed via the certified ``decimal_log10`` -- no second log
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, decimal_log10, make_context

ENGINE_VERSION = "f8p3-rf/1"


def _require_complex(value, name: str) -> DecimalComplex:
    if not isinstance(value, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, f"{name} must be DecimalComplex")
    if not value.re.is_finite() or not value.im.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


@dataclass(frozen=True)
class ScalarMargin:
    status: str  # "FINITE" | "UNSUPPORTED"
    value: Decimal | None
    reason: str = ""

    def require_finite(self) -> Decimal:
        if self.status != "FINITE" or self.value is None:
            raise ControlError(ControlStatus.UNSUPPORTED, self.reason or "margin undefined")
        return self.value


def vswr(gamma: DecimalComplex, ctx=None) -> ScalarMargin:
    """VSWR = (1+|Gamma|)/(1-|Gamma|) for |Gamma| < 1.
    |Gamma| = 1 -> UNSUPPORTED (infinite VSWR, never Infinity stored).
    |Gamma| > 1 -> UNSUPPORTED (active load, VSWR undefined)."""
    c = ctx or make_context()
    _require_complex(gamma, "Gamma")
    mag = gamma.modulus()
    if mag == 1:
        return ScalarMargin("UNSUPPORTED", None, "infinite VSWR at |Gamma| = 1")
    if mag > 1:
        return ScalarMargin("UNSUPPORTED", None, "VSWR undefined for active load (|Gamma| > 1)")
    return ScalarMargin("FINITE", c.divide(c.add(Decimal(1), mag), c.subtract(Decimal(1), mag)))


def return_loss_db(gamma: DecimalComplex, ctx=None) -> ScalarMargin:
    """RL = -20*log10(|Gamma|), |Gamma| > 0 finite (sign preserved:
    negative RL = return gain, documented). |Gamma| = 0 -> UNSUPPORTED
    (infinite RL, never Infinity stored)."""
    c = ctx or make_context()
    _require_complex(gamma, "Gamma")
    mag = gamma.modulus()
    if mag == 0:
        return ScalarMargin("UNSUPPORTED", None, "infinite return loss at Gamma = 0")
    log_mag = decimal_log10(mag, c)
    return ScalarMargin("FINITE", c.minus(c.multiply(Decimal(20), log_mag)))


def insertion_loss_db(s21: DecimalComplex, ctx=None) -> ScalarMargin:
    """IL = -20*log10(|S21|), same domain rule as RL."""
    c = ctx or make_context()
    _require_complex(s21, "S21")
    mag = s21.modulus()
    if mag == 0:
        return ScalarMargin("UNSUPPORTED", None, "infinite insertion loss at S21 = 0")
    log_mag = decimal_log10(mag, c)
    return ScalarMargin("FINITE", c.minus(c.multiply(Decimal(20), log_mag)))


def mismatch_loss_db(gamma: DecimalComplex, ctx=None) -> ScalarMargin:
    """ML = -10*log10(1 - |Gamma|^2), |Gamma| < 1 (mismatch loss >= 0).
    |Gamma| >= 1 -> UNSUPPORTED."""
    c = ctx or make_context()
    _require_complex(gamma, "Gamma")
    mag = gamma.modulus()
    if mag >= 1:
        return ScalarMargin("UNSUPPORTED", None, "mismatch loss undefined for |Gamma| >= 1")
    one_minus = c.subtract(Decimal(1), c.multiply(mag, mag))
    log_val = decimal_log10(one_minus, c)
    return ScalarMargin("FINITE", c.minus(c.multiply(Decimal(10), log_val)))


@dataclass(frozen=True)
class SParametersLike:
    """Minimal 2x2 S-parameter view consumed by margins (avoids an
    import cycle with ``rf.sparams``; both operate on the same plain
    DecimalComplex fields)."""

    s11: DecimalComplex
    s12: DecimalComplex
    s21: DecimalComplex
    s22: DecimalComplex


def input_reflection_loaded(s: SParametersLike, gamma_load: DecimalComplex, ctx=None) -> DecimalComplex:
    """Gamma_in = S11 + S12*S21*Gamma_L / (1 - S22*Gamma_L)."""
    c = ctx or make_context()
    denom = DecimalComplex.one() - s.s22 * gamma_load
    if denom.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Gamma_in singular (1 - S22*GammaL == 0)")
    return s.s11 + (s.s12 * s.s21 * gamma_load) / denom


def transducer_gain(
    s: SParametersLike, gamma_source: DecimalComplex, gamma_load: DecimalComplex, ctx=None
) -> ScalarMargin:
    """GT = |S21|^2*(1-|Gs|^2)*(1-|GL|^2) / (|1-Gs*Gin|^2*|1-S22*GL|^2),
    Gin the loaded input reflection (gate §6). Available/max-stable/
    unilateral gains are OUT (future, gate §30)."""
    c = ctx or make_context()
    denom22 = DecimalComplex.one() - s.s22 * gamma_load
    if denom22.is_zero_exact():
        return ScalarMargin("UNSUPPORTED", None, "GT singular (1 - S22*GammaL == 0)")
    gamma_in = input_reflection_loaded(s, gamma_load, c)
    denom_gs = DecimalComplex.one() - gamma_source * gamma_in
    if denom_gs.is_zero_exact():
        return ScalarMargin("UNSUPPORTED", None, "GT singular (1 - Gs*Gin == 0)")
    num = c.multiply(
        c.multiply(s.s21.squared_modulus(), c.subtract(Decimal(1), gamma_source.squared_modulus())),
        c.subtract(Decimal(1), gamma_load.squared_modulus()),
    )
    den = c.multiply(denom_gs.squared_modulus(), denom22.squared_modulus())
    if den == 0:
        return ScalarMargin("UNSUPPORTED", None, "GT singular (zero denominator)")
    return ScalarMargin("FINITE", c.divide(num, den))


@dataclass(frozen=True)
class StabilityFactors:
    delta: DecimalComplex
    k: Decimal
    mu: Decimal


def rollett_stability(s: SParametersLike, ctx=None) -> StabilityFactors:
    """Rollett K and mu stability factors (standard closed forms):

        Delta = S11*S22 - S12*S21
        K = (1 - |S11|^2 - |S22|^2 + |Delta|^2) / (2*|S12*S21|)
        mu = (1 - |S11|^2) / (|S22 - Delta*conj(S11)| + |S12*S21|)

    K > 1 and mu > 1 both indicate unconditional stability (mu is the
    single-parameter test, gate §19 P3-I020 bounds only GT for passive
    networks; K/mu are additional diagnostics)."""
    c = ctx or make_context()
    delta = s.s11 * s.s22 - s.s12 * s.s21
    s12s21_mag = (s.s12 * s.s21).modulus()
    if s12s21_mag == 0:
        raise ControlError(ControlStatus.SINGULAR, "K singular: S12*S21 == 0")
    numerator = c.add(
        c.subtract(
            c.subtract(Decimal(1), s.s11.squared_modulus()),
            s.s22.squared_modulus(),
        ),
        delta.squared_modulus(),
    )
    k = c.divide(numerator, c.multiply(Decimal(2), s12s21_mag))
    mu_denom = c.add((s.s22 - delta * s.s11.conjugate()).modulus(), s12s21_mag)
    if mu_denom == 0:
        raise ControlError(ControlStatus.SINGULAR, "mu singular: zero denominator")
    mu = c.divide(c.subtract(Decimal(1), s.s11.squared_modulus()), mu_denom)
    return StabilityFactors(delta=delta, k=k, mu=mu)
