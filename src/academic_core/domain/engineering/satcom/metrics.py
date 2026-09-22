"""F8-P5 dB-label algebra + conversions (NEW).

DbValue carries an explicit label; only dimensionally valid
combinations evaluate (absolute ± relative → absolute; absolute −
same-absolute → dB; dB ± dB → dB). Everything else — dBi+dBi,
dBW+dBm, dB+dBW-order abuse aside — raises INVALID. Linear kernels
are REUSEd from comms.metrics (no second log/exp); dBd converts via
antennas (single +2.15 reference).

Labels: dB (relative), dBW (ref 1 W), dBm (ref 1 mW), dBi
(isotropic), dBd (dipole), dB/K (G/T), dBHz (C/N0 et al.), dBK
(temperature).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.metrics import from_db10, to_db10
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import make_context
from academic_core.domain.engineering.math.logarithm import decimal_ln10, decimal_log10
from academic_core.domain.engineering.satcom.antennas import dbd_to_dbi, dbi_to_dbd
from academic_core.domain.engineering.satcom.constants import boltzmann_k, check_magnitude

ABSOLUTE_LABELS = ("dBW", "dBm", "dBi", "dBd", "dB/K", "dBHz", "dBK")
POWER_LABELS = ("dBW", "dBm", "dBHz")
GAIN_LABELS = ("dBi", "dBd")
ALL_LABELS = ("dB",) + ABSOLUTE_LABELS


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


@dataclass(frozen=True)
class DbValue:
    """A dB-domain magnitude with an explicit label (immutable)."""

    value: Decimal
    label: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, Decimal):
            raise _fail(ControlStatus.INVALID, "dB value must be Decimal")
        if not self.value.is_finite():
            raise _fail(ControlStatus.INVALID, "dB value must be finite")
        if self.label not in ALL_LABELS:
            raise _fail(ControlStatus.INVALID, "unknown dB label " + str(self.label))


def db_add(first: DbValue, second: DbValue) -> DbValue:
    """Label-checked addition.

    dB±dB→dB; power±dB→power; gain±dB→gain; power+gain→power (either
    order); dB/K±dB→dB/K; dBK±dB→dBK. Everything else (power+power,
    gain+gain, mixed absolutes) → INVALID.
    """
    if not isinstance(first, DbValue) or not isinstance(second, DbValue):
        raise _fail(ControlStatus.INVALID, "db_add needs DbValues")
    ctx = make_context()
    lab_a, lab_b = first.label, second.label
    if lab_a == "dB" and lab_b == "dB":
        return DbValue(ctx.add(first.value, second.value), "dB")
    if lab_a in POWER_LABELS and lab_b == "dB":
        return DbValue(ctx.add(first.value, second.value), lab_a)
    if lab_a == "dB" and lab_b in POWER_LABELS:
        return DbValue(ctx.add(first.value, second.value), lab_b)
    if lab_a in GAIN_LABELS and lab_b == "dB":
        return DbValue(ctx.add(first.value, second.value), lab_a)
    if lab_a == "dB" and lab_b in GAIN_LABELS:
        return DbValue(ctx.add(first.value, second.value), lab_b)
    if lab_a in POWER_LABELS and lab_b in GAIN_LABELS:
        return DbValue(ctx.add(first.value, second.value), lab_a)
    if lab_a in GAIN_LABELS and lab_b in POWER_LABELS:
        return DbValue(ctx.add(first.value, second.value), lab_b)
    if lab_a in ("dB/K", "dBK") and lab_b == "dB":
        return DbValue(ctx.add(first.value, second.value), lab_a)
    if lab_a == "dB" and lab_b in ("dB/K", "dBK"):
        return DbValue(ctx.add(first.value, second.value), lab_b)
    raise _fail(ControlStatus.INVALID,
                "incompatible dB addition: " + lab_a + " + " + lab_b)


def db_sub(first: DbValue, second: DbValue) -> DbValue:
    """Label-checked subtraction.

    x−dB→x; power−power(same)→dB; gain−gain(same)→dB; power−gain→power;
    dB/K−dB→dB/K; dB/K−dB/K→dB; dBK−dBK→dB. Else INVALID.
    """
    if not isinstance(first, DbValue) or not isinstance(second, DbValue):
        raise _fail(ControlStatus.INVALID, "db_sub needs DbValues")
    ctx = make_context()
    lab_a, lab_b = first.label, second.label
    if lab_b == "dB" and lab_a in ALL_LABELS:
        return DbValue(ctx.subtract(first.value, second.value), lab_a)
    if lab_a in POWER_LABELS and lab_b == lab_a:
        return DbValue(ctx.subtract(first.value, second.value), "dB")
    if lab_a in GAIN_LABELS and lab_b == lab_a:
        return DbValue(ctx.subtract(first.value, second.value), "dB")
    if lab_a in POWER_LABELS and lab_b in GAIN_LABELS:
        return DbValue(ctx.subtract(first.value, second.value), lab_a)
    if lab_a in ("dB/K", "dBK") and lab_b == lab_a:
        return DbValue(ctx.subtract(first.value, second.value), "dB")
    raise _fail(ControlStatus.INVALID,
                "incompatible dB subtraction: " + lab_a + " - " + lab_b)


def to_dbw(power_w: Decimal) -> DbValue:
    """10·log10(P/1W) → dBW (REUSEd kernel)."""
    if isinstance(power_w, bool) or not isinstance(power_w, Decimal):
        raise _fail(ControlStatus.INVALID, "power must be Decimal watts")
    check_magnitude(power_w, "power")
    return DbValue(to_db10(power_w), "dBW")


def to_dbm(power_w: Decimal) -> DbValue:
    """10·log10(P/1mW) → dBm (REUSEd kernel)."""
    if isinstance(power_w, bool) or not isinstance(power_w, Decimal):
        raise _fail(ControlStatus.INVALID, "power must be Decimal watts")
    check_magnitude(power_w, "power")
    ctx = make_context()
    return DbValue(ctx.add(to_db10(power_w), Decimal(30)), "dBm")


def from_dbw(value_dbw: Decimal) -> Decimal:
    """Linear watts from dBW (REUSEd kernel)."""
    if isinstance(value_dbw, bool) or not isinstance(value_dbw, Decimal):
        raise _fail(ControlStatus.INVALID, "dBW value must be Decimal")
    if not value_dbw.is_finite():
        raise _fail(ControlStatus.INVALID, "dBW value must be finite")
    return from_db10(value_dbw)


def from_dbm(value_dbm: Decimal) -> Decimal:
    """Linear watts from dBm (REUSEd kernel)."""
    if isinstance(value_dbm, bool) or not isinstance(value_dbm, Decimal):
        raise _fail(ControlStatus.INVALID, "dBm value must be Decimal")
    if not value_dbm.is_finite():
        raise _fail(ControlStatus.INVALID, "dBm value must be finite")
    return from_db10(make_context().subtract(value_dbm, Decimal(30)))


def dbm_to_dbw(value_dbm: Decimal) -> Decimal:
    """dBW = dBm − 30 (exact reference shift)."""
    if isinstance(value_dbm, bool) or not isinstance(value_dbm, Decimal):
        raise _fail(ControlStatus.INVALID, "dBm value must be Decimal")
    if not value_dbm.is_finite():
        raise _fail(ControlStatus.INVALID, "dBm value must be finite")
    return make_context().subtract(value_dbm, Decimal(30))


def dbw_to_dbm(value_dbw: Decimal) -> Decimal:
    """dBm = dBW + 30 (exact reference shift)."""
    if isinstance(value_dbw, bool) or not isinstance(value_dbw, Decimal):
        raise _fail(ControlStatus.INVALID, "dBW value must be Decimal")
    if not value_dbw.is_finite():
        raise _fail(ControlStatus.INVALID, "dBW value must be finite")
    return make_context().add(value_dbw, Decimal(30))


def k_dbw_per_k_hz() -> Decimal:
    """10·log10(k) = −228.599… dB(W/K/Hz) (REUSEd kernel)."""
    return to_db10(boltzmann_k())


def required_cn_db(spectral_efficiency: Decimal) -> Decimal:
    """Shannon-required C/N = 10·log10(2^eta − 1) (dB), eta > 0.

    Direct form is Decimal-stable (no float expm1 needed at prec-50);
    eta → 0 gives large-negative dB honestly; eta ≤ 0 → INVALID.
    """
    if isinstance(spectral_efficiency, bool) or not isinstance(spectral_efficiency, Decimal):
        raise _fail(ControlStatus.INVALID, "spectral efficiency must be Decimal")
    if not spectral_efficiency.is_finite() or spectral_efficiency <= 0:
        raise _fail(ControlStatus.INVALID, "spectral efficiency eta > 0 required")
    ctx = make_context()
    ln2 = ctx.multiply(decimal_ln10(ctx), decimal_log10(Decimal(2), ctx))
    pow2 = decimal_exp(ctx.multiply(spectral_efficiency, ln2), ctx)
    excess = ctx.subtract(pow2, Decimal(1))
    if excess <= 0:
        raise _fail(ControlStatus.NUMERIC_ERROR, "Shannon C/N argument non-positive")
    return ctx.multiply(Decimal(10), decimal_log10(excess, ctx))


def dbd_label_to_dbi(value_dbd: Decimal) -> DbValue:
    """dBd → dBi labelled conversion (single reference, antennas module)."""
    return DbValue(dbd_to_dbi(value_dbd), "dBi")


def dbi_label_to_dbd(value_dbi: Decimal) -> DbValue:
    """dBi → dBd labelled conversion (single reference, antennas module)."""
    return DbValue(dbi_to_dbd(value_dbi), "dBd")
