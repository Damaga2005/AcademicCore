"""F8-P4 AWGN channel and static impairments (NEW).

AWGN with the closed PSD convention: one-sided N0 (W/Hz); complex noise
n ~ CN(0, N0) (N0/2 per I/Q branch); real noise n ~ N(0, N0/2).
apply_awgn adds caller-supplied noise (deterministic given the stream,
P4-I014). Static impairments (gain, phase rotation, frequency offset,
fractional timing shift) are analytic frozen transforms without state;
tracking loops are UNSUPPORTED (design gate section 27).
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    complex_from_polar,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_CHANNEL_SYMBOLS = 65536
MAX_TIMING_LOBES = 5000


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def validate_n0(value: object) -> Decimal:
    """One-sided noise PSD N0 > 0, finite (W/Hz label)."""
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "N0 rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad N0 string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "N0 must be Decimal/int/str")
    if not out.is_finite() or out <= 0:
        raise _fail(ControlStatus.INVALID, "N0 > 0 required")
    return out


def noise_variance_real(n0: Decimal) -> Decimal:
    """Real-branch variance N0/2 (two-sided PSD per dimension)."""
    psd = validate_n0(n0)
    return make_context().divide(psd, Decimal(2))


def noise_variance_complex(n0: Decimal) -> Decimal:
    """Complex-sample variance N0 (N0/2 per I/Q branch)."""
    return validate_n0(n0)


def two_sided_psd(n0_one_sided: Decimal) -> Decimal:
    """Two-sided PSD N0/2 per real dimension (documented separation)."""
    return noise_variance_real(n0_one_sided)


def _check_symbols(symbols: object) -> tuple:
    if not isinstance(symbols, (tuple, list)) or len(symbols) == 0:
        raise _fail(ControlStatus.INVALID, "symbols must be non-empty")
    if len(symbols) > MAX_CHANNEL_SYMBOLS:
        raise _fail(ControlStatus.INVALID, "channel symbol budget exceeded")
    for z in symbols:
        if not isinstance(z, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "symbols must be DecimalComplex")
        if not z.re.is_finite() or not z.im.is_finite():
            raise _fail(ControlStatus.INVALID, "symbols must be finite")
    return tuple(symbols)


def apply_awgn(symbols: object, noise: object) -> tuple:
    """y = x + n elementwise (noise supplied by the caller)."""
    clean = _check_symbols(symbols)
    if not isinstance(noise, (tuple, list)) or len(noise) != len(clean):
        raise _fail(ControlStatus.INVALID, "noise must align with symbols")
    out: list = []
    for symbol, sample in zip(clean, noise):
        if not isinstance(sample, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "noise must be DecimalComplex")
        if not sample.re.is_finite() or not sample.im.is_finite():
            raise _fail(ControlStatus.INVALID, "noise must be finite")
        out.append(symbol + sample)
    return tuple(out)


def apply_gain(symbols: object, gain: object) -> tuple:
    """LIMITED static attenuation/amplification y = a*x, a > 0 real."""
    clean = _check_symbols(symbols)
    if isinstance(gain, bool) or not isinstance(gain, Decimal):
        raise _fail(ControlStatus.INVALID, "gain must be Decimal")
    if not gain.is_finite() or gain <= 0:
        raise _fail(ControlStatus.INVALID, "gain a > 0 required")
    ctx = make_context()
    out: list = []
    for z in clean:
        out.append(DecimalComplex(ctx.multiply(z.re, gain),
                                  ctx.multiply(z.im, gain)))
    return tuple(out)


def apply_phase_rotation(symbols: object, angle_rad: object) -> tuple:
    """LIMITED static rotation y = x*e^{j*phi} (certified polar helper)."""
    clean = _check_symbols(symbols)
    if isinstance(angle_rad, bool) or not isinstance(angle_rad, Decimal):
        raise _fail(ControlStatus.INVALID, "angle must be Decimal radians")
    if not angle_rad.is_finite():
        raise _fail(ControlStatus.INVALID, "angle must be finite")
    phasor = complex_from_polar(Decimal(1), angle_rad)
    return tuple(z * phasor for z in clean)


def apply_frequency_offset(symbols: object, offset_hz: object,
                           sample_period_s: object) -> tuple:
    """LIMITED static offset y_n = x_n*e^{j*2*pi*df*n*T} (no tracking)."""
    clean = _check_symbols(symbols)
    if isinstance(offset_hz, bool) or not isinstance(offset_hz, Decimal):
        raise _fail(ControlStatus.INVALID, "frequency offset must be Decimal")
    if not offset_hz.is_finite():
        raise _fail(ControlStatus.INVALID, "frequency offset must be finite")
    if isinstance(sample_period_s, bool) or not isinstance(sample_period_s, Decimal):
        raise _fail(ControlStatus.INVALID, "sample period must be Decimal")
    if not sample_period_s.is_finite() or sample_period_s <= 0:
        raise _fail(ControlStatus.INVALID, "sample period T > 0 required")
    ctx = make_context()
    two_pi = ctx.multiply(Decimal(2), decimal_pi(ctx))
    out: list = []
    for n, z in enumerate(clean):
        angle = ctx.multiply(ctx.multiply(two_pi, offset_hz),
                             ctx.multiply(sample_period_s, Decimal(n)))
        out.append(z * complex_from_polar(Decimal(1), angle))
    return tuple(out)


def _sinc_local(offset: Decimal, ctx) -> Decimal:
    if offset == 0:
        return ctx.plus(Decimal(1))
    arg = ctx.multiply(decimal_pi(ctx), offset)
    return ctx.divide(decimal_sin(arg, ctx), arg)


def timing_shift(samples: object, shift_s: object, sample_period_s: object,
                 lobes: int = 64) -> tuple:
    """LIMITED fractional timing shift by truncated sinc interpolation.

    Complex-capable; lobe budget in [1, 5000]; shift in [0, Ts).
    """
    if not isinstance(samples, (tuple, list)) or len(samples) == 0:
        raise _fail(ControlStatus.INVALID, "samples must be non-empty")
    if len(samples) > MAX_CHANNEL_SYMBOLS:
        raise _fail(ControlStatus.INVALID, "channel symbol budget exceeded")
    if isinstance(shift_s, bool) or not isinstance(shift_s, Decimal):
        raise _fail(ControlStatus.INVALID, "timing shift must be Decimal")
    if isinstance(sample_period_s, bool) or not isinstance(sample_period_s, Decimal):
        raise _fail(ControlStatus.INVALID, "sample period must be Decimal")
    if not sample_period_s.is_finite() or sample_period_s <= 0:
        raise _fail(ControlStatus.INVALID, "sample period T > 0 required")
    if not shift_s.is_finite() or shift_s < 0 or shift_s >= sample_period_s:
        raise _fail(ControlStatus.INVALID, "timing shift tau in [0, Ts) required")
    if isinstance(lobes, bool) or not isinstance(lobes, int):
        raise _fail(ControlStatus.INVALID, "lobe budget must be int")
    if lobes < 1 or lobes > MAX_TIMING_LOBES:
        raise _fail(ControlStatus.INVALID, "lobe budget in [1, 5000] required")
    ctx = make_context()
    vals: list = []
    for s in samples:
        if not isinstance(s, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "samples must be DecimalComplex")
        if not s.re.is_finite() or not s.im.is_finite():
            raise _fail(ControlStatus.INVALID, "samples must be finite")
        vals.append(s)
    count = len(vals)
    unit_shift = ctx.divide(shift_s, sample_period_s)
    half = lobes
    out: list = []
    for m in range(count):
        lo = max(0, m - half)
        hi = min(count - 1, m + half)
        acc_re = Decimal(0)
        acc_im = Decimal(0)
        for n in range(lo, hi + 1):
            unit = ctx.subtract(ctx.subtract(Decimal(m), Decimal(n)), unit_shift)
            weight = _sinc_local(unit, ctx)
            acc_re = ctx.add(acc_re, ctx.multiply(vals[n].re, weight))
            acc_im = ctx.add(acc_im, ctx.multiply(vals[n].im, weight))
        out.append(DecimalComplex(acc_re, acc_im))
    return tuple(out)
