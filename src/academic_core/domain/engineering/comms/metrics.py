"""F8-P4 metrics: Q/erfc, BER/SER, SNR/EbN0/EsN0, Shannon (NEW).

EXACT: BPSK/QPSK/BFSK/OOK BER, Shannon capacity, all conversions.
APPROXIMATION (labelled, never exact): M-PSK / square M-QAM / M-ASK SER.
SIMULATION results never originate here (see simulation.py).

Q(x) for x >= 1 uses the Laplace/Mills continued fraction evaluated by
modified Lentz under Decimal-80; for 0 <= x < 1 the erf Maclaurin series
is used. All transcendental kernels (exp/sqrt/pi/log10) are certified.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.bits import log2_int
from academic_core.domain.engineering.comms.constellation import (
    MASK_MAX_M,
    MPSK_ORDERS,
    MQAM_ORDERS,
)
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import (
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context,
)
from academic_core.domain.engineering.math.logarithm import (
    decimal_ln10,
    decimal_log10,
)

EXACT = "EXACT"
APPROXIMATION = "APPROXIMATION"
SIMULATION = "SIMULATION"

_CF_MAX_TERMS = 10000
_SERIES_MAX_TERMS = 10000


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _as_nonnegative(value: object, label: str) -> Decimal:
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
        raise _fail(ControlStatus.INVALID, label + " must be finite >= 0")
    return out


@dataclass(frozen=True)
class MetricResult:
    """A metric value with its machine-checked KIND (EXACT/APPROX/SIM)."""

    value: Decimal
    kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise _fail(ControlStatus.INVALID, "metric value must be Decimal")
        if not self.value.is_finite():
            raise _fail(ControlStatus.INVALID, "metric value must be finite")
        if self.kind not in (EXACT, APPROXIMATION, SIMULATION):
            raise _fail(ControlStatus.INVALID, "metric kind must be EXACT/APPROXIMATION/SIMULATION")


def _erfcx_cf(x: Decimal, ctx) -> Decimal:
    """erfcx(x) = e^{x^2}*erfc(x) via the Laplace continued fraction.

    erfcx(x) = (1/sqrt(pi))/G(x),
    G(x) = x + (1/2)/(x + 1/(x + (3/2)/(x + ...))),
    i.e. b0 = x, bj = x, aj = j/2, evaluated by modified Lentz.
    Callers keep x >= 1/sqrt(2) so convergence is rapid.
    """
    tiny = Decimal("1e-300")
    eps = Decimal("1e-75")
    fwd = ctx.plus(x)
    cee = ctx.plus(x)
    dee = Decimal(0)
    result = ctx.plus(x)
    for step in range(1, _CF_MAX_TERMS + 1):
        coef = ctx.divide(Decimal(step), Decimal(2))
        dee = ctx.add(x, ctx.multiply(coef, dee))
        if dee == 0:
            dee = tiny
        dee = ctx.divide(Decimal(1), dee)
        cee = ctx.add(x, ctx.divide(coef, cee))
        if cee == 0:
            cee = tiny
        factor = ctx.multiply(cee, dee)
        result = ctx.multiply(result, factor)
        if (factor - Decimal(1)).copy_abs() < eps:
            break
    else:
        raise _fail(ControlStatus.NUMERIC_ERROR, "erfcx fraction failed to converge")
    root_pi = decimal_sqrt(decimal_pi(ctx), ctx)
    return ctx.divide(ctx.divide(Decimal(1), root_pi), result)


def _erf_taylor(x: Decimal, ctx) -> Decimal:
    """erf(x) Maclaurin series, valid for |x| <= 1 (guarded)."""
    if x.copy_abs() > 1:
        raise _fail(ControlStatus.INVALID, "erf Taylor path needs |x| <= 1")
    eps = Decimal("1e-75")
    xsq = ctx.multiply(x, x)
    total = ctx.plus(x)
    term = ctx.plus(x)
    for n in range(1, _SERIES_MAX_TERMS + 1):
        ratio = ctx.divide(ctx.multiply(ctx.minus(xsq), Decimal(2 * n - 1)),
                           ctx.multiply(Decimal(n), Decimal(2 * n + 1)))
        term = ctx.multiply(term, ratio)
        total = ctx.add(total, term)
        if term.copy_abs() < eps:
            break
    else:
        raise _fail(ControlStatus.NUMERIC_ERROR, "erf series failed to converge")
    two_over_root_pi = ctx.divide(Decimal(2), decimal_sqrt(decimal_pi(ctx), ctx))
    return ctx.multiply(two_over_root_pi, total)


def _ctx80():
    return make_context(30)


def q_function(arg: object) -> Decimal:
    """Q(x) = P(N(0,1) > x) for finite Decimal x (any sign).

    x > 40 underflows to 0 (documented: true Q(40) < 1e-350, far below
    any working precision — returning 0 is honest, never silent).
    """
    if isinstance(arg, bool) or not isinstance(arg, Decimal):
        raise _fail(ControlStatus.INVALID, "Q argument must be Decimal")
    if not arg.is_finite():
        raise _fail(ControlStatus.INVALID, "Q argument must be finite")
    ctx = _ctx80()
    if arg < 0:
        return ctx.subtract(Decimal(1), q_function(ctx.minus(arg)))
    if arg > 40:
        return Decimal(0)
    if arg >= 1:
        root2 = decimal_sqrt(Decimal(2), ctx)
        scaled = ctx.divide(ctx.plus(arg), root2)
        erfcx = _erfcx_cf(scaled, ctx)
        expo = ctx.minus(ctx.multiply(scaled, scaled))
        return ctx.divide(ctx.multiply(erfcx, decimal_exp(expo, ctx)), Decimal(2))
    root2 = decimal_sqrt(Decimal(2), ctx)
    scaled = ctx.divide(arg, root2)
    erf_val = _erf_taylor(scaled, ctx)
    return ctx.multiply(ctx.subtract(Decimal(1), erf_val), Decimal("0.5"))


def decimal_erfc(arg: object) -> Decimal:
    """erfc(x) for finite Decimal x (any sign); x > 40 underflows to 0."""
    if isinstance(arg, bool) or not isinstance(arg, Decimal):
        raise _fail(ControlStatus.INVALID, "erfc argument must be Decimal")
    if not arg.is_finite():
        raise _fail(ControlStatus.INVALID, "erfc argument must be finite")
    ctx = _ctx80()
    if arg < 0:
        return ctx.subtract(Decimal(2), decimal_erfc(ctx.minus(arg)))
    if arg > 40:
        return Decimal(0)
    if arg >= 1:
        erfcx = _erfcx_cf(ctx.plus(arg), ctx)
        expo = ctx.minus(ctx.multiply(arg, arg))
        return ctx.multiply(erfcx, decimal_exp(expo, ctx))
    erf_val = _erf_taylor(ctx.plus(arg), ctx)
    return ctx.subtract(Decimal(1), erf_val)


def _check_ratio(value: object, label: str) -> Decimal:
    out = _as_nonnegative(value, label)
    return out


def ber_bpsk(eb_n0: object) -> MetricResult:
    """EXACT coherent BPSK: BER = Q(sqrt(2*Eb/N0))."""
    ratio = _check_ratio(eb_n0, "Eb/N0")
    ctx = make_context()
    arg = decimal_sqrt(ctx.multiply(Decimal(2), ratio), ctx)
    return MetricResult(value=q_function(arg), kind=EXACT)


def ber_qpsk(eb_n0: object) -> MetricResult:
    """EXACT coherent QPSK (Gray): BER = Q(sqrt(2*Eb/N0))."""
    ratio = _check_ratio(eb_n0, "Eb/N0")
    ctx = make_context()
    arg = decimal_sqrt(ctx.multiply(Decimal(2), ratio), ctx)
    return MetricResult(value=q_function(arg), kind=EXACT)


def ber_bfsk(eb_n0: object) -> MetricResult:
    """EXACT coherent BFSK: BER = Q(sqrt(Eb/N0))."""
    ratio = _check_ratio(eb_n0, "Eb/N0")
    ctx = make_context()
    arg = decimal_sqrt(ctx.plus(ratio), ctx)
    return MetricResult(value=q_function(arg), kind=EXACT)


def ber_ook(eb_n0: object) -> MetricResult:
    """EXACT coherent OOK: BER = Q(sqrt(Eb/N0))."""
    ratio = _check_ratio(eb_n0, "Eb/N0")
    ctx = make_context()
    arg = decimal_sqrt(ctx.plus(ratio), ctx)
    return MetricResult(value=q_function(arg), kind=EXACT)


def ser_qpsk_approx(es_n0: object) -> MetricResult:
    """APPROXIMATION QPSK SER ~= 2*Q(sqrt(2*Eb/N0)) with Es = 2*Eb."""
    ratio = _check_ratio(es_n0, "Es/N0")
    ctx = make_context()
    arg = decimal_sqrt(ctx.plus(ratio), ctx)
    val = ctx.multiply(Decimal(2), q_function(arg))
    return MetricResult(value=val, kind=APPROXIMATION)


def ser_mpsk_approx(order: int, es_n0: object) -> MetricResult:
    """APPROXIMATION M-PSK SER ~= 2*Q(sqrt(2*Es/N0)*sin(pi/M))."""
    if order not in MPSK_ORDERS:
        raise _fail(ControlStatus.INVALID, "M-PSK SER needs order 8/16/32/64")
    ratio = _check_ratio(es_n0, "Es/N0")
    ctx = make_context()
    angle = ctx.divide(decimal_pi(ctx), Decimal(order))
    arg = ctx.multiply(decimal_sqrt(ctx.multiply(Decimal(2), ratio), ctx),
                       decimal_sin(angle, ctx))
    val = ctx.multiply(Decimal(2), q_function(arg))
    return MetricResult(value=val, kind=APPROXIMATION)


def ser_mqam_approx(order: int, es_n0: object) -> MetricResult:
    """APPROXIMATION square M-QAM SER ~= 4*(1-1/sqrt(M))*Q(sqrt(3*Es/((M-1)*N0)))."""
    if order not in MQAM_ORDERS or order == 4:
        raise _fail(ControlStatus.INVALID, "M-QAM SER needs order 16/64/256")
    ratio = _check_ratio(es_n0, "Es/N0")
    ctx = make_context()
    root_m = decimal_sqrt(Decimal(order), ctx)
    pref = ctx.multiply(Decimal(4), ctx.subtract(Decimal(1),
                                                 ctx.divide(Decimal(1), root_m)))
    inner = ctx.divide(ctx.multiply(Decimal(3), ratio), Decimal(order - 1))
    val = ctx.multiply(pref, q_function(decimal_sqrt(inner, ctx)))
    return MetricResult(value=val, kind=APPROXIMATION)


def ser_mask_approx(order: int, es_n0: object) -> MetricResult:
    """APPROXIMATION M-ASK SER ~= 2*(M-1)/M*Q(sqrt(6*Es/((M^2-1)*N0)))."""
    log2_int(order)
    if order > MASK_MAX_M:
        raise _fail(ControlStatus.INVALID, "M-ASK SER needs order <= 64")
    ratio = _check_ratio(es_n0, "Es/N0")
    ctx = make_context()
    pref = ctx.divide(ctx.multiply(Decimal(2), Decimal(order - 1)), Decimal(order))
    inner = ctx.divide(ctx.multiply(Decimal(6), ratio),
                       Decimal(order * order - 1))
    val = ctx.multiply(pref, q_function(decimal_sqrt(inner, ctx)))
    return MetricResult(value=val, kind=APPROXIMATION)


def es_n0_from_eb_n0(eb_n0: object, bits_per_symbol: int) -> Decimal:
    """Es/N0 = k*Eb/N0 (exact, k >= 1)."""
    ratio = _check_ratio(eb_n0, "Eb/N0")
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    return make_context().multiply(ratio, Decimal(bits_per_symbol))


def eb_n0_from_es_n0(es_n0: object, bits_per_symbol: int) -> Decimal:
    """Eb/N0 = Es/N0/k (exact, k >= 1)."""
    ratio = _check_ratio(es_n0, "Es/N0")
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    return make_context().divide(ratio, Decimal(bits_per_symbol))


def snr_from_es_n0(es_n0: object, symbol_rate_hz: object,
                   bandwidth_hz: object) -> Decimal:
    """SNR = Es/N0*Rs/B (exact; Nyquist B = Rs gives SNR = Es/N0)."""
    ratio = _check_ratio(es_n0, "Es/N0")
    for value, label in ((symbol_rate_hz, "symbol rate"), (bandwidth_hz, "bandwidth")):
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal")
        if not value.is_finite() or value <= 0:
            raise _fail(ControlStatus.INVALID, label + " must be finite > 0")
    ctx = make_context()
    return ctx.multiply(ratio, ctx.divide(symbol_rate_hz, bandwidth_hz))


def to_db10(ratio: object) -> Decimal:
    """10*log10(x) power-ratio label in dB (x > 0)."""
    if isinstance(ratio, bool) or not isinstance(ratio, Decimal):
        raise _fail(ControlStatus.INVALID, "ratio must be Decimal")
    if not ratio.is_finite() or ratio <= 0:
        raise _fail(ControlStatus.INVALID, "ratio > 0 required")
    ctx = make_context()
    return ctx.multiply(Decimal(10), decimal_log10(ratio, ctx))


def to_db20(amplitude: object) -> Decimal:
    """20*log10(x) amplitude-ratio label in dB (x > 0)."""
    if isinstance(amplitude, bool) or not isinstance(amplitude, Decimal):
        raise _fail(ControlStatus.INVALID, "amplitude must be Decimal")
    if not amplitude.is_finite() or amplitude <= 0:
        raise _fail(ControlStatus.INVALID, "amplitude > 0 required")
    ctx = make_context()
    return ctx.multiply(Decimal(20), decimal_log10(amplitude, ctx))


def from_db10(db_value: object) -> Decimal:
    """10^{dB/10} via certified exp/ln10 (exact kernels)."""
    if isinstance(db_value, bool) or not isinstance(db_value, Decimal):
        raise _fail(ControlStatus.INVALID, "dB value must be Decimal")
    if not db_value.is_finite():
        raise _fail(ControlStatus.INVALID, "dB value must be finite")
    ctx = make_context()
    scaled = ctx.divide(db_value, Decimal(10))
    return decimal_exp(ctx.multiply(scaled, decimal_ln10(ctx)), ctx)


def shannon_capacity(bandwidth_hz: object, snr_linear: object) -> MetricResult:
    """EXACT Hartley-Shannon C = B*log2(1+SNR), B >= 0, SNR >= 0."""
    for value, label in ((bandwidth_hz, "bandwidth"), (snr_linear, "SNR")):
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal")
        if not value.is_finite() or value < 0:
            raise _fail(ControlStatus.INVALID, label + " must be finite >= 0")
    ctx = make_context()
    if bandwidth_hz == 0 or snr_linear == 0:
        return MetricResult(value=Decimal(0), kind=EXACT)
    log2_1p = ctx.divide(decimal_log10(ctx.add(Decimal(1), snr_linear), ctx),
                         decimal_log10(Decimal(2), ctx))
    return MetricResult(value=ctx.multiply(bandwidth_hz, log2_1p), kind=EXACT)


def spectral_efficiency(snr_linear: object) -> MetricResult:
    """EXACT C/B = log2(1+SNR)."""
    ratio = _check_ratio(snr_linear, "SNR")
    ctx = make_context()
    if ratio == 0:
        return MetricResult(value=Decimal(0), kind=EXACT)
    val = ctx.divide(decimal_log10(ctx.add(Decimal(1), ratio), ctx),
                     decimal_log10(Decimal(2), ctx))
    return MetricResult(value=val, kind=EXACT)


def shannon_limit_eb_n0() -> MetricResult:
    """EXACT Shannon limit Eb/N0 -> ln 2 = log10(2)*ln10 (-1.59 dB)."""
    ctx = make_context()
    ln2 = ctx.multiply(decimal_log10(Decimal(2), ctx), decimal_ln10(ctx))
    return MetricResult(value=ln2, kind=EXACT)
