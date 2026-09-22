"""F8-P5 budget synthesis + closed inverses (NEW).

Forward: full auditable budget per leg (every intermediate kept).
Bent-pipe end-to-end via reciprocal 1/(C/N0) combination (transparent
linear transponder as gain+bandwidth block). Closed inverses: required
EIRP, modem/Shannon max Rb, required Eb/N0 by bisection on EXACT P4
curves only, min Ptx by bounded bisection on the strictly increasing
margin(Ptx) line. No generic optimizer; infeasible targets are
UNSUPPORTED, never clipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.metrics import (
    APPROXIMATION,
    EXACT,
    MetricResult,
    ber_bfsk,
    ber_bpsk,
    ber_ook,
    ber_qpsk,
    from_db10,
    shannon_capacity,
    to_db10,
)
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import make_context
from academic_core.domain.engineering.satcom.constants import MAX_MAGNITUDE, check_magnitude
from academic_core.domain.engineering.satcom.link import (
    LinkLeg,
    cn0_dbhz,
    cn_db,
    ebno_db,
    eirp_dbw,
    fspl_db,
    g_over_t_dbk,
    misc_losses_db,
    receive_gain_dbi,
    received_power_dbw,
)
from academic_core.domain.engineering.satcom.metrics import k_dbw_per_k_hz
from academic_core.domain.engineering.satcom.losses import LossEntry
from academic_core.domain.engineering.satcom.metrics import DbValue, db_sub

MAX_LEGS = 2
MAX_BISECT_ITER = 200
MAX_PTX_W = Decimal("1E+6")

EXACT_BER_SCHEMES = ("bpsk", "qpsk", "bfsk", "ook")


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _exact_ber(scheme: str, eb_n0_linear: Decimal) -> MetricResult:
    if scheme == "bpsk":
        return ber_bpsk(eb_n0_linear)
    if scheme == "qpsk":
        return ber_qpsk(eb_n0_linear)
    if scheme == "bfsk":
        return ber_bfsk(eb_n0_linear)
    if scheme == "ook":
        return ber_ook(eb_n0_linear)
    raise _fail(ControlStatus.UNSUPPORTED,
                "BER inversion needs an EXACT P4 curve (bpsk/qpsk/bfsk/ook)")


@dataclass(frozen=True)
class BudgetResult:
    """Auditable forward budget (every intermediate kept)."""

    direction: str
    eirp_dbw: Decimal
    fspl_db: Decimal
    misc_db: Decimal
    lrx_db: Decimal
    grx_dbi: Decimal
    received_dbw: Decimal
    g_over_t_dbk: Decimal
    cn0_dbhz: Decimal
    cn_db: Decimal
    ebno_db: Decimal

    def __post_init__(self) -> None:
        fields = (("eirp_dbw", self.eirp_dbw), ("fspl_db", self.fspl_db),
                  ("misc_db", self.misc_db), ("received_dbw", self.received_dbw),
                  ("g_over_t_dbk", self.g_over_t_dbk), ("cn0_dbhz", self.cn0_dbhz),
                  ("cn_db", self.cn_db), ("ebno_db", self.ebno_db))
        for name, val in fields:
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise _fail(ControlStatus.INVALID, "budget field " + name + " must be Decimal")
            if not val.is_finite():
                raise _fail(ControlStatus.INVALID, "budget field " + name + " must be finite")
        if self.direction not in ("uplink", "downlink"):
            raise _fail(ControlStatus.INVALID, "budget direction must be uplink/downlink")


@dataclass(frozen=True)
class Transponder:
    """Transparent linear transponder block (gain + bandwidth only)."""

    gain_db: Decimal
    bandwidth_hz: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.gain_db, bool) or not isinstance(self.gain_db, Decimal):
            raise _fail(ControlStatus.INVALID, "transponder gain must be Decimal dB")
        if not self.gain_db.is_finite():
            raise _fail(ControlStatus.INVALID, "transponder gain must be finite")
        if isinstance(self.bandwidth_hz, bool) or not isinstance(self.bandwidth_hz, Decimal):
            raise _fail(ControlStatus.INVALID, "transponder bandwidth must be Decimal Hz")
        check_magnitude(self.bandwidth_hz, "transponder bandwidth")


def forward_budget(leg: LinkLeg) -> BudgetResult:
    """Full forward evaluation Tx -> receiver (deterministic)."""
    if not isinstance(leg, LinkLeg):
        raise _fail(ControlStatus.INVALID, "forward_budget needs a LinkLeg")
    return BudgetResult(
        direction=leg.direction,
        eirp_dbw=eirp_dbw(leg).value,
        fspl_db=fspl_db(leg).value,
        misc_db=misc_losses_db(leg).value,
        lrx_db=leg.lrx_db,
        grx_dbi=receive_gain_dbi(leg),
        received_dbw=received_power_dbw(leg).value,
        g_over_t_dbk=g_over_t_dbk(leg).value,
        cn0_dbhz=cn0_dbhz(leg).value,
        cn_db=cn_db(leg).value,
        ebno_db=ebno_db(leg).value,
    )


def link_margin_db(available_ebno_db: Decimal, required_ebno_db: Decimal) -> Decimal:
    """margin = available − required (dB); not availability."""
    for val, label in ((available_ebno_db, "available"), (required_ebno_db, "required")):
        if isinstance(val, bool) or not isinstance(val, Decimal):
            raise _fail(ControlStatus.INVALID, label + " Eb/N0 must be Decimal dB")
        if not val.is_finite():
            raise _fail(ControlStatus.INVALID, label + " Eb/N0 must be finite")
    return make_context().subtract(available_ebno_db, required_ebno_db)


def bent_pipe_cn0_dbhz(up_cn0_dbhz: Decimal, down_cn0_dbhz: Decimal,
                       xpdr_gain_db: Decimal = Decimal(0)) -> Decimal:
    """Transparent end-to-end 1/(C/N0)tot = Σ 1/(C/N0)i (dBHz).

    The transponder contributes linear gain only (no regeneration, no
    saturation); its gain cancels in the reciprocal sum and is carried
    for traceability (rejected if non-finite).
    """
    for val, label in ((up_cn0_dbhz, "uplink C/N0"), (down_cn0_dbhz, "downlink C/N0"),
                       (xpdr_gain_db, "transponder gain")):
        if isinstance(val, bool) or not isinstance(val, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal dB")
        if not val.is_finite():
            raise _fail(ControlStatus.INVALID, label + " must be finite")
    ctx = make_context()
    up_lin = from_db10(up_cn0_dbhz)
    down_lin = from_db10(down_cn0_dbhz)
    total = ctx.divide(Decimal(1), ctx.add(ctx.divide(Decimal(1), up_lin),
                                          ctx.divide(Decimal(1), down_lin)))
    return to_db10(total)


def required_eirp_dbw(target_ebno_db: Decimal, path_db: Decimal, g_over_t: Decimal,
                      rb_bps: Decimal) -> Decimal:
    """Closed-form required EIRP = Eb/N0 + L + k − G/T + 10log10(Rb) (dBW)."""
    for val, label in ((target_ebno_db, "target Eb/N0"), (path_db, "path loss"),
                       (g_over_t, "G/T")):
        if isinstance(val, bool) or not isinstance(val, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal dB")
        if not val.is_finite():
            raise _fail(ControlStatus.INVALID, label + " must be finite")
    if isinstance(rb_bps, bool) or not isinstance(rb_bps, Decimal):
        raise _fail(ControlStatus.INVALID, "bit rate must be Decimal")
    check_magnitude(rb_bps, "bit rate")
    ctx = make_context()
    out = ctx.add(target_ebno_db, path_db)
    out = ctx.subtract(out, g_over_t)
    out = ctx.add(out, k_dbw_per_k_hz())
    return ctx.add(out, to_db10(rb_bps))


def max_rb_bps(cn0_dbhz: Decimal, required_ebno_db: Decimal) -> Decimal:
    """Closed-form modem max Rb = (C/N0)lin/(Eb/N0)req,lin (bit/s)."""
    for val, label in ((cn0_dbhz, "C/N0"), (required_ebno_db, "required Eb/N0")):
        if isinstance(val, bool) or not isinstance(val, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal dB")
        if not val.is_finite():
            raise _fail(ControlStatus.INVALID, label + " must be finite")
    ctx = make_context()
    divisor = from_db10(required_ebno_db)
    if divisor <= 0:
        raise _fail(ControlStatus.NUMERIC_ERROR, "Eb/N0 requirement non-positive")
    return ctx.divide(from_db10(cn0_dbhz), divisor)


def max_rb_shannon_bps(bandwidth_hz: Decimal, cn_db: Decimal) -> Decimal:
    """Shannon max Rb = C from REUSEd P4 capacity (bit/s)."""
    if isinstance(bandwidth_hz, bool) or not isinstance(bandwidth_hz, Decimal):
        raise _fail(ControlStatus.INVALID, "bandwidth must be Decimal Hz")
    check_magnitude(bandwidth_hz, "bandwidth")
    if isinstance(cn_db, bool) or not isinstance(cn_db, Decimal):
        raise _fail(ControlStatus.INVALID, "C/N must be Decimal dB")
    if not cn_db.is_finite():
        raise _fail(ControlStatus.INVALID, "C/N must be finite")
    return shannon_capacity(bandwidth_hz, from_db10(cn_db)).value


def required_ebno_from_ber(scheme: str, target_ber: Decimal) -> Decimal:
    """Required Eb/N0 (linear ratio) for target BER — EXACT curves only.

    Bisection on the strictly decreasing P4 curve; monotonicity proved
    by endpoint check (BER(lo) > BER(hi)); ≤ 200 iterations; infeasible
    targets (≥ 0.5) → UNSUPPORTED.
    """
    if not isinstance(scheme, str) or scheme.strip() not in EXACT_BER_SCHEMES:
        raise _fail(ControlStatus.UNSUPPORTED,
                    "BER inversion needs an EXACT P4 curve (bpsk/qpsk/bfsk/ook)")
    if isinstance(target_ber, bool) or not isinstance(target_ber, Decimal):
        raise _fail(ControlStatus.INVALID, "target BER must be Decimal")
    if not target_ber.is_finite() or target_ber <= 0 or target_ber >= 1:
        raise _fail(ControlStatus.INVALID, "target BER must be in (0, 1)")
    if target_ber >= Decimal("0.5"):
        raise _fail(ControlStatus.UNSUPPORTED, "target BER >= 0.5 unreachable")
    ctx = make_context()
    lo = Decimal("1E-12")
    hi = Decimal(1)
    while _exact_ber(scheme.strip(), hi).value > target_ber:
        hi = ctx.multiply(hi, Decimal(10))
        if hi > Decimal("1E+30"):
            raise _fail(ControlStatus.UNSUPPORTED, "target BER unreachable in budget")
    if not _exact_ber(scheme.strip(), lo).value > target_ber:
        raise _fail(ControlStatus.INCONSISTENT, "BER curve monotonicity check failed")
    for _ in range(MAX_BISECT_ITER):
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        if _exact_ber(scheme.strip(), mid).value > target_ber:
            lo = mid
        else:
            hi = mid
        width = ctx.subtract(hi, lo)
        scale = hi.copy_abs()
        if scale < 1:
            scale = Decimal(1)
        if ctx.divide(width, scale) <= Decimal("1E-12"):
            break
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def _replace_ptx(leg: LinkLeg, ptx_w: Decimal) -> LinkLeg:
    return LinkLeg(direction=leg.direction, ptx_w=ptx_w, tx_antenna=leg.tx_antenna,
                   ltx_db=leg.ltx_db, freq_hz=leg.freq_hz, distance_m=leg.distance_m,
                   losses=leg.losses, rx_antenna=leg.rx_antenna, lrx_db=leg.lrx_db,
                   tsys_k=leg.tsys_k, friis_stages=leg.friis_stages,
                   tant_k=leg.tant_k, bandwidth_hz=leg.bandwidth_hz,
                   rb_bps=leg.rb_bps, scheme=leg.scheme)


def min_ptx_w(target_margin_db: Decimal, required_ebno_db: Decimal,
              template: LinkLeg) -> Decimal:
    """Min Ptx (W) for target margin by bisection on margin(Ptx).

    margin is strictly increasing with slope 1 dB/dB in Ptx_dBW;
    brackets required (margin(lo) < target ≤ margin(hi) attainable);
    ≤ 200 iterations; Ptx capped at MAX_PTX_W.
    """
    if isinstance(target_margin_db, bool) or not isinstance(target_margin_db, Decimal):
        raise _fail(ControlStatus.INVALID, "target margin must be Decimal dB")
    if not target_margin_db.is_finite():
        raise _fail(ControlStatus.INVALID, "target margin must be finite")
    if isinstance(required_ebno_db, bool) or not isinstance(required_ebno_db, Decimal):
        raise _fail(ControlStatus.INVALID, "required Eb/N0 must be Decimal dB")
    if not required_ebno_db.is_finite():
        raise _fail(ControlStatus.INVALID, "required Eb/N0 must be finite")
    if not isinstance(template, LinkLeg):
        raise _fail(ControlStatus.INVALID, "min_ptx needs a LinkLeg template")
    ctx = make_context()
    tiny = Decimal("1E-12")

    def margin_at(ptx: Decimal) -> Decimal:
        avail = forward_budget(_replace_ptx(template, ptx)).ebno_db
        return link_margin_db(avail, required_ebno_db)

    lo = tiny
    if margin_at(lo) >= target_margin_db:
        return lo
    hi = Decimal(1)
    while margin_at(hi) < target_margin_db:
        hi = ctx.multiply(hi, Decimal(10))
        if hi > MAX_PTX_W:
            raise _fail(ControlStatus.UNSUPPORTED, "target margin unreachable ≤ 1e6 W")
    if not margin_at(hi) >= target_margin_db:
        raise _fail(ControlStatus.INCONSISTENT, "margin monotonicity check failed")
    for _ in range(MAX_BISECT_ITER):
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        if margin_at(mid) < target_margin_db:
            lo = mid
        else:
            hi = mid
        if ctx.divide(ctx.subtract(hi, lo), hi) <= Decimal("1E-12"):
            break
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def ber_kind_for_scheme(scheme: str) -> str:
    """Machine-checked EXACT/APPROXIMATION kind of a scheme tag."""
    if not isinstance(scheme, str):
        raise _fail(ControlStatus.INVALID, "scheme tag must be a string")
    key = scheme.strip()
    if key in EXACT_BER_SCHEMES:
        return EXACT
    if key in ("mpsk8", "mpsk16", "mpsk32", "mpsk64", "mqam16", "mqam64",
               "mqam256", "mask", "qpsk-ser"):
        return APPROXIMATION
    raise _fail(ControlStatus.UNSUPPORTED, "unknown scheme tag " + key)
