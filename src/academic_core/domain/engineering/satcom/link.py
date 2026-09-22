"""F8-P5 link leg model (NEW).

One directed leg Tx → Rx with explicit reference planes:

    P0 Tx PA output (Ptx) → P1 Tx antenna output (EIRP)
    → P2 free space + misc losses → P3 Rx antenna output
    → P4 LNA input (post-Rx-feed; Tsys referenced here)

EIRP = Ptx·Gtx/Ltx. Pr(LNA input) = EIRP − FSPL − Lmisc − Lrx + Grx.
C/N0 = EIRP − FSPL − Lmisc + G/T − k, G/T = Grx − Lrx − 10log10(Tsys).
dB bookkeeping runs through the DbValue label algebra; linear cross-
checks use REUSEd P3/P4 kernels. Feed mismatch loss from a Gamma reuses
rf.margins (no second engine).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.metrics import to_db10, to_db20
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_pi,
    make_context,
)
from academic_core.domain.engineering.rf.margins import mismatch_loss_db
from academic_core.domain.engineering.satcom.antennas import Antenna, MAX_ANTENNAS_PER_LEG
from academic_core.domain.engineering.satcom.constants import (
    check_magnitude,
    wavelength_m,
)
from academic_core.domain.engineering.satcom.losses import LossEntry, total_loss_db
from academic_core.domain.engineering.satcom.metrics import (
    DbValue,
    db_add,
    db_sub,
    k_dbw_per_k_hz,
)
from academic_core.domain.engineering.satcom.noise import friis_temperature
from academic_core.domain.engineering.satcom.noise import g_over_t_dbk as _noise_g_over_t

DIRECTIONS = ("uplink", "downlink")
MAX_LOSS_ENTRIES = 16


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _positive_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise _fail(ControlStatus.INVALID, label + " must be Decimal/int/str")
    return check_magnitude(out, label)


def _loss_db(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise _fail(ControlStatus.INVALID, label + " must be Decimal/int/str")
    if not out.is_finite() or out < 0:
        raise _fail(ControlStatus.INVALID, label + " must be finite dB >= 0")
    return out


@dataclass(frozen=True)
class LinkLeg:
    """One directed link leg (immutable; validation-only post-init)."""

    direction: str
    ptx_w: Decimal
    tx_antenna: Antenna
    ltx_db: Decimal
    freq_hz: Decimal
    distance_m: Decimal
    losses: tuple = ()
    rx_antenna: Antenna | None = None
    lrx_db: Decimal = Decimal(0)
    tsys_k: Decimal | None = None
    friis_stages: tuple = ()
    tant_k: Decimal | None = None
    bandwidth_hz: Decimal = Decimal(1)
    rb_bps: Decimal = Decimal(1)
    scheme: str = "bpsk"

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise _fail(ControlStatus.INVALID, "leg direction must be uplink/downlink")
        for label, val in (("Ptx", self.ptx_w), ("frequency", self.freq_hz),
                           ("distance", self.distance_m), ("bandwidth", self.bandwidth_hz),
                           ("bit rate", self.rb_bps)):
            _positive_decimal(val, label)
        for label, val in (("Ltx", self.ltx_db), ("Lrx", self.lrx_db)):
            _loss_db(val, label)
        if not isinstance(self.tx_antenna, Antenna):
            raise _fail(ControlStatus.INVALID, "leg needs a Tx Antenna")
        if self.rx_antenna is not None and not isinstance(self.rx_antenna, Antenna):
            raise _fail(ControlStatus.INVALID, "Rx antenna must be Antenna/None")
        antennas = 1 + (1 if self.rx_antenna is not None else 0)
        if antennas > MAX_ANTENNAS_PER_LEG:
            raise _fail(ControlStatus.INVALID, "at most 2 antennas per leg")
        if not isinstance(self.losses, (tuple, list)):
            raise _fail(ControlStatus.INVALID, "losses must be a tuple/list")
        if len(self.losses) > MAX_LOSS_ENTRIES:
            raise _fail(ControlStatus.INVALID, "loss budget exceeded (16 max)")
        for entry in self.losses:
            if not isinstance(entry, LossEntry):
                raise _fail(ControlStatus.INVALID, "losses must be LossEntry")
        if (self.tsys_k is None) == (len(self.friis_stages) == 0):
            raise _fail(ControlStatus.INVALID, "leg needs Tsys XOR Friis stages")
        if self.tsys_k is not None:
            if isinstance(self.tsys_k, bool) or not isinstance(self.tsys_k, Decimal):
                raise _fail(ControlStatus.INVALID, "Tsys must be Decimal K")
            if not self.tsys_k.is_finite() or self.tsys_k <= 0:
                raise _fail(ControlStatus.INVALID, "Tsys must be finite K > 0")
        if self.tant_k is not None:
            if isinstance(self.tant_k, bool) or not isinstance(self.tant_k, Decimal):
                raise _fail(ControlStatus.INVALID, "Tant must be Decimal K")
            if not self.tant_k.is_finite() or self.tant_k <= 0:
                raise _fail(ControlStatus.INVALID, "Tant must be finite K > 0")
        if not isinstance(self.scheme, str) or not self.scheme.strip():
            raise _fail(ControlStatus.INVALID, "leg scheme tag cannot be empty")


def leg_wavelength_m(leg: LinkLeg) -> Decimal:
    """lambda = c/f for the leg carrier."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "leg_wavelength needs a LinkLeg")
    return wavelength_m(leg.freq_hz)


def system_temperature_k(leg: LinkLeg) -> Decimal:
    """Effective Tsys at LNA input: Tsys|(Friis Te) + Tant when given."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "system_temperature needs a LinkLeg")
    ctx = make_context()
    if len(leg.friis_stages) > 0:
        base = friis_temperature(leg.friis_stages)
    else:
        assert leg.tsys_k is not None
        base = leg.tsys_k
    if leg.tant_k is not None:
        return ctx.add(base, leg.tant_k)
    return base


def eirp_dbw(leg: LinkLeg) -> DbValue:
    """EIRP = Ptx + Gtx − Ltx (dBW) at plane P1."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "eirp needs a LinkLeg")
    wave = leg_wavelength_m(leg)
    gain = leg.tx_antenna.gain_dbi_value(wave)
    result = db_add(DbValue(to_db10(leg.ptx_w), "dBW"), DbValue(gain, "dBi"))
    return db_sub(result, DbValue(leg.ltx_db, "dB"))


def fspl_db(leg: LinkLeg) -> DbValue:
    """FSPL = 20·log10(4πd/λ) (dB) via REUSEd to_db20."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "fspl needs a LinkLeg")
    wave = leg_wavelength_m(leg)
    ctx = make_context()
    ratio = ctx.divide(ctx.multiply(ctx.multiply(Decimal(4), decimal_pi(ctx)),
                                   leg.distance_m), wave)
    return DbValue(to_db20(ratio), "dB")


def fspl_linear(leg: LinkLeg) -> Decimal:
    """FSPL = (4πd/λ)² linear (identity partner of fspl_db)."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "fspl_linear needs a LinkLeg")
    wave = leg_wavelength_m(leg)
    ctx = make_context()
    ratio = ctx.divide(ctx.multiply(ctx.multiply(Decimal(4), decimal_pi(ctx)),
                                   leg.distance_m), wave)
    return ctx.multiply(ratio, ratio)


def misc_losses_db(leg: LinkLeg) -> DbValue:
    """Sum of the explicit loss ledger (dB)."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "misc_losses needs a LinkLeg")
    return DbValue(total_loss_db(leg.losses), "dB")


def receive_gain_dbi(leg: LinkLeg) -> Decimal:
    """Resolved Rx antenna gain (dBi); leg without Rx antenna → INVALID."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "receive_gain needs a LinkLeg")
    if leg.rx_antenna is None:
        raise _fail(ControlStatus.INVALID, "leg has no Rx antenna")
    return leg.rx_antenna.gain_dbi_value(leg_wavelength_m(leg))


def g_over_t_dbk(leg: LinkLeg) -> DbValue:
    """G/T = Grx − Lrx − 10log10(Tsys) (dB/K) at plane P4."""
    gain = receive_gain_dbi(leg)
    temp = system_temperature_k(leg)
    return DbValue(_noise_g_over_t(gain, temp), "dB/K")


def received_power_dbw(leg: LinkLeg) -> DbValue:
    """Pr = EIRP − FSPL − Lmisc − Lrx + Grx (dBW) at plane P4."""
    power = eirp_dbw(leg)
    power = db_sub(power, fspl_db(leg))
    power = db_sub(power, misc_losses_db(leg))
    power = db_sub(power, DbValue(leg.lrx_db, "dB"))
    return db_add(power, DbValue(receive_gain_dbi(leg), "dBi"))


def cn0_dbhz(leg: LinkLeg) -> DbValue:
    """C/N0 = EIRP − FSPL − Lmisc + G/T − k (dBHz)."""
    result = db_sub(eirp_dbw(leg), fspl_db(leg))
    result = db_sub(result, misc_losses_db(leg))
    ctx = make_context()
    with_gt = ctx.add(result.value, g_over_t_dbk(leg).value)
    return DbValue(ctx.subtract(with_gt, k_dbw_per_k_hz()), "dBHz")


def cn_db(leg: LinkLeg) -> DbValue:
    """C/N = C/N0 − 10log10(B) (dB), single-B declaration.

    Bandwidth normalization strips the Hz: dBHz → dB (documented
    plane semantics; the DbValue algebra guards the power/gain chain).
    """
    carrier = cn0_dbhz(leg)
    ctx = make_context()
    value = ctx.subtract(carrier.value, to_db10(leg.bandwidth_hz))
    return DbValue(value, "dB")


def ebno_db(leg: LinkLeg) -> DbValue:
    """Eb/N0 = C/N0 − 10log10(Rb) (dB).

    Rate normalization strips the Hz: dBHz → dB (documented).
    """
    carrier = cn0_dbhz(leg)
    ctx = make_context()
    value = ctx.subtract(carrier.value, to_db10(leg.rb_bps))
    return DbValue(value, "dB")


def feed_mismatch_loss_db(gamma: DecimalComplex) -> Decimal:
    """Feed mismatch loss from Gamma via REUSEd rf.margins (dB ≥ 0).

    P3-reuse evidence: no second mismatch engine. |Gamma| ≥ 1 or
    matched pin → P3 typed states propagate (UNSUPPORTED→ControlError).
    """
    if not isinstance(gamma, DecimalComplex):
        raise _fail(ControlStatus.INVALID, "Gamma must be DecimalComplex")
    margin = mismatch_loss_db(gamma)
    return margin.require_finite()
