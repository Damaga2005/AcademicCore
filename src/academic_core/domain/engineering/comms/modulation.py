"""F8-P4 modulation and demodulation (NEW).

Baseband complex modulation over frozen constellations plus coherent FSK
tone sets and the documentary passband mapping:

    s_pb(t) = I(t)*cos(2*pi*fc*t) - Q(t)*sin(2*pi*fc*t), phi0 = 0.

FSK: tones fi = fc + i*df with orthogonal spacing df = 1/(2*Ts)
(coherent, zero initial phase per symbol). samples/symbol is an integer
1..64; total samples <= 65536.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.bits import (
    MAX_SYMBOLS,
    map_bits,
    validate_bits,
    validate_symbols,
)
from academic_core.domain.engineering.comms.constellation import (
    Constellation,
    ook_constellation,
)
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    complex_from_polar,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_SPS = 64
MAX_SAMPLES = 65536
MAX_FSK_M = 64


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def modulate(constellation: Constellation, symbols: object) -> tuple:
    """Symbols to baseband complex samples (unit average energy)."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "modulate needs a Constellation")
    clean = validate_symbols(symbols, constellation.order)
    return tuple(constellation.coordinate_of(s) for s in clean)


def demodulate_ml(received: object, constellation: Constellation) -> tuple:
    """Minimum-distance ML decision (uniform priors; ties -> lowest id)."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "demodulate_ml needs a Constellation")
    if not isinstance(received, (tuple, list)) or len(received) == 0:
        raise _fail(ControlStatus.INVALID, "received samples must be non-empty")
    if len(received) > MAX_SYMBOLS:
        raise _fail(ControlStatus.INVALID, "symbol budget exceeded")
    for y in received:
        if not isinstance(y, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "received samples must be DecimalComplex")
        if not y.re.is_finite() or not y.im.is_finite():
            raise _fail(ControlStatus.INVALID, "received samples must be finite")
    out: list = []
    for y in received:
        best = 0
        best_dist: Decimal | None = None
        for point in constellation.points:
            dist = (y - point.coordinate).squared_modulus()
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = point.sid
        out.append(best)
    return tuple(out)


def bpsk_demodulate(received: object) -> tuple:
    """Coherent BPSK: decide 0 iff Re(y) >= 0."""
    if not isinstance(received, (tuple, list)) or len(received) == 0:
        raise _fail(ControlStatus.INVALID, "received samples must be non-empty")
    out: list = []
    for y in received:
        if not isinstance(y, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "received samples must be DecimalComplex")
        if not y.re.is_finite() or not y.im.is_finite():
            raise _fail(ControlStatus.INVALID, "received samples must be finite")
        out.append(0 if y.re >= 0 else 1)
    return tuple(out)


def qpsk_demodulate(received: object) -> tuple:
    """Coherent QPSK quadrant decision matching the frozen Gray map."""
    if not isinstance(received, (tuple, list)) or len(received) == 0:
        raise _fail(ControlStatus.INVALID, "received samples must be non-empty")
    out: list = []
    for y in received:
        if not isinstance(y, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "received samples must be DecimalComplex")
        if not y.re.is_finite() or not y.im.is_finite():
            raise _fail(ControlStatus.INVALID, "received samples must be finite")
        east = y.re >= 0
        north = y.im >= 0
        if east and north:
            out.append(0)
        elif (not east) and north:
            out.append(1)
        elif (not east) and (not north):
            out.append(2)
        else:
            out.append(3)
    return tuple(out)


def ask_thresholds(constellation: Constellation) -> tuple:
    """Equidistant ML thresholds over the sorted real ASK levels."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "ask_thresholds needs a Constellation")
    for p in constellation.points:
        if p.coordinate.im != 0:
            raise _fail(ControlStatus.INVALID, "ASK constellation must be real-valued")
    levels = sorted(p.coordinate.re for p in constellation.points)
    ctx = make_context()
    return tuple(ctx.divide(ctx.add(a, b), Decimal(2)) for a, b in zip(levels, levels[1:]))


def ask_demodulate(received: object, constellation: Constellation) -> tuple:
    """Coherent ASK: real-part threshold decision (ML, equidistant)."""
    if not isinstance(received, (tuple, list)) or len(received) == 0:
        raise _fail(ControlStatus.INVALID, "received samples must be non-empty")
    thresholds = ask_thresholds(constellation)
    ordered = sorted(constellation.points, key=lambda p: p.coordinate.re)
    sids = [p.sid for p in ordered]
    out: list = []
    for y in received:
        if not isinstance(y, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "received samples must be DecimalComplex")
        if not y.re.is_finite() or not y.im.is_finite():
            raise _fail(ControlStatus.INVALID, "received samples must be finite")
        region = 0
        for thr in thresholds:
            if y.re >= thr:
                region += 1
            else:
                break
        out.append(sids[region])
    return tuple(out)


def ook_coherent_threshold() -> Decimal:
    """OOK coherent threshold sqrt(2)/2 in normalized units (EXACT rule)."""
    constellation = ook_constellation()
    levels = sorted(p.coordinate.re for p in constellation.points)
    ctx = make_context()
    return ctx.divide(ctx.add(levels[0], levels[1]), Decimal(2))


def ook_demodulate_noncoherent(received_energy: object, threshold_energy: object) -> tuple:
    """LIMITED non-coherent OOK/FSK energy detector: |y|^2 vs threshold."""
    if not isinstance(received_energy, (tuple, list)) or len(received_energy) == 0:
        raise _fail(ControlStatus.INVALID, "received energies must be non-empty")
    if isinstance(threshold_energy, bool) or not isinstance(threshold_energy, Decimal):
        raise _fail(ControlStatus.INVALID, "energy threshold must be Decimal")
    if not threshold_energy.is_finite() or threshold_energy < 0:
        raise _fail(ControlStatus.INVALID, "energy threshold must be finite >= 0")
    out: list = []
    for e in received_energy:
        if isinstance(e, bool) or not isinstance(e, Decimal):
            raise _fail(ControlStatus.INVALID, "received energies must be Decimal")
        if not e.is_finite() or e < 0:
            raise _fail(ControlStatus.INVALID, "received energies must be finite >= 0")
        out.append(1 if e >= threshold_energy else 0)
    return tuple(out)


def _as_positive(value: object, label: str) -> Decimal:
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
    if not out.is_finite() or out <= 0:
        raise _fail(ControlStatus.INVALID, label + " > 0 required")
    return out


@dataclass(frozen=True)
class FskScheme:
    """Coherent FSK tone set (validation-only post-init)."""

    order: int
    carrier_hz: Decimal
    symbol_period_s: Decimal
    spacing_hz: Decimal
    tone_freqs_hz: tuple

    def __post_init__(self) -> None:
        if self.order not in tuple(2 ** k for k in range(1, 7)):
            raise _fail(ControlStatus.INVALID, "FSK order M = 2^k <= 64 required")
        for field in (self.carrier_hz, self.symbol_period_s, self.spacing_hz):
            if isinstance(field, bool) or not isinstance(field, Decimal):
                raise _fail(ControlStatus.INVALID, "FSK parameters must be Decimal")
            if not field.is_finite() or field <= 0:
                raise _fail(ControlStatus.INVALID, "FSK parameters must be finite > 0")
        if len(self.tone_freqs_hz) != self.order:
            raise _fail(ControlStatus.INVALID, "FSK tone table must have M entries")


def fsk_scheme(order: int, carrier_hz: object, symbol_period_s: object) -> FskScheme:
    """Tone set fi = fc + i*df with orthogonal df = 1/(2*Ts)."""
    if isinstance(order, bool) or not isinstance(order, int):
        raise _fail(ControlStatus.INVALID, "FSK order M must be int")
    if order not in tuple(2 ** k for k in range(1, 7)):
        raise _fail(ControlStatus.INVALID, "FSK order M = 2^k <= 64 required")
    if order > MAX_FSK_M:
        raise _fail(ControlStatus.INVALID, "FSK order M <= 64 required")
    fc = _as_positive(carrier_hz, "carrier frequency")
    ts = _as_positive(symbol_period_s, "symbol period")
    ctx = make_context()
    spacing = ctx.divide(Decimal(1), ctx.multiply(Decimal(2), ts))
    tones = tuple(ctx.add(fc, ctx.multiply(spacing, Decimal(i))) for i in range(order))
    product = ctx.multiply(spacing, ts)
    if product != Decimal("0.5"):
        raise _fail(ControlStatus.INCONSISTENT, "FSK orthogonality product df*Ts != 1/2")
    return FskScheme(order=order, carrier_hz=fc, symbol_period_s=ts,
                     spacing_hz=spacing, tone_freqs_hz=tones)


def fsk_tone_of(symbol: int, scheme: FskScheme) -> Decimal:
    """Tone frequency of one FSK symbol (tone index == symbol)."""
    if not isinstance(scheme, FskScheme):
        raise _fail(ControlStatus.INVALID, "fsk_tone_of needs an FskScheme")
    if isinstance(symbol, bool) or not isinstance(symbol, int):
        raise _fail(ControlStatus.INVALID, "FSK symbol must be int")
    if symbol < 0 or symbol >= scheme.order:
        raise _fail(ControlStatus.INVALID, "FSK symbol out of range")
    return scheme.tone_freqs_hz[symbol]


def fsk_cross_integral(freq_a: Decimal, freq_b: Decimal, period_s: Decimal) -> Decimal:
    """Closed-form real-tone cross-correlation over [0, Ts].

    integral cos(2*pi*fa*t)*cos(2*pi*fb*t) dt
      = sin(2*pi*(fa-fb)*Ts)/(4*pi*(fa-fb))
      + sin(2*pi*(fa+fb)*Ts)/(4*pi*(fa+fb)).
    Zero for fa == fb is the tone energy (unsupported here: SINGULAR).
    """
    for value, label in ((freq_a, "tone A"), (freq_b, "tone B"), (period_s, "period")):
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal")
        if not value.is_finite() or value <= 0:
            raise _fail(ControlStatus.INVALID, label + " must be finite > 0")
    ctx = make_context()
    if freq_a == freq_b:
        raise _fail(ControlStatus.SINGULAR, "cross integral needs distinct tones")
    pi = decimal_pi(ctx)
    two_pi = ctx.multiply(Decimal(2), pi)
    diff = ctx.subtract(freq_a, freq_b)
    total = ctx.add(freq_a, freq_b)
    term_d = ctx.divide(decimal_sin(ctx.multiply(ctx.multiply(two_pi, diff), period_s), ctx),
                        ctx.multiply(ctx.multiply(Decimal(4), pi), diff))
    term_s = ctx.divide(decimal_sin(ctx.multiply(ctx.multiply(two_pi, total), period_s), ctx),
                        ctx.multiply(ctx.multiply(Decimal(4), pi), total))
    return ctx.add(term_d, term_s)


def check_samples_per_symbol(sps: object, total: int) -> int:
    """Integer sps in [1, 64] with total samples <= 65536."""
    if isinstance(sps, bool) or not isinstance(sps, int):
        raise _fail(ControlStatus.INVALID, "samples/symbol must be int")
    if sps < 1 or sps > MAX_SPS:
        raise _fail(ControlStatus.INVALID, "samples/symbol in [1, 64] required")
    if total > MAX_SAMPLES:
        raise _fail(ControlStatus.INVALID, "sample budget exceeded")
    return sps


def oversample(symbols_complex: tuple, sps: int) -> tuple:
    """Rectangular hold of baseband symbols to sps samples each."""
    if not isinstance(symbols_complex, (tuple, list)) or len(symbols_complex) == 0:
        raise _fail(ControlStatus.INVALID, "symbols must be non-empty")
    check_samples_per_symbol(sps, len(symbols_complex) * sps)
    out: list = []
    for z in symbols_complex:
        if not isinstance(z, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "symbols must be DecimalComplex")
        out.extend([z] * sps)
    return tuple(out)


def passband_value(sample_i: Decimal, sample_q: Decimal, carrier_hz: Decimal,
                   time_s: Decimal) -> Decimal:
    """Documentary passband sample: I*cos(wc*t) - Q*sin(wc*t), phi0 = 0."""
    for value, label in ((sample_i, "I"), (sample_q, "Q")):
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise _fail(ControlStatus.INVALID, label + " must be Decimal")
        if not value.is_finite():
            raise _fail(ControlStatus.INVALID, label + " must be finite")
    fc = _as_positive(carrier_hz, "carrier frequency")
    if isinstance(time_s, bool) or not isinstance(time_s, Decimal):
        raise _fail(ControlStatus.INVALID, "time must be Decimal")
    if not time_s.is_finite() or time_s < 0:
        raise _fail(ControlStatus.INVALID, "time must be finite >= 0")
    ctx = make_context()
    angle = ctx.multiply(ctx.multiply(ctx.multiply(Decimal(2), decimal_pi(ctx)), fc), time_s)
    return ctx.subtract(ctx.multiply(sample_i, decimal_cos(angle, ctx)),
                        ctx.multiply(sample_q, decimal_sin(angle, ctx)))


def rotate_phase(symbols: tuple, angle_rad: Decimal) -> tuple:
    """Apply e^{j*angle} to baseband symbols (certified polar helper)."""
    if not isinstance(symbols, (tuple, list)) or len(symbols) == 0:
        raise _fail(ControlStatus.INVALID, "symbols must be non-empty")
    if isinstance(angle_rad, bool) or not isinstance(angle_rad, Decimal):
        raise _fail(ControlStatus.INVALID, "angle must be Decimal radians")
    if not angle_rad.is_finite():
        raise _fail(ControlStatus.INVALID, "angle must be finite")
    phasor = complex_from_polar(Decimal(1), angle_rad)
    out: list = []
    for z in symbols:
        if not isinstance(z, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "symbols must be DecimalComplex")
        out.append(z * phasor)
    return tuple(out)


def bits_to_baseband(bits: object, constellation: Constellation) -> tuple:
    """Bits -> symbols (MSB-first) -> baseband complex samples."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "bits_to_baseband needs a Constellation")
    clean = validate_bits(bits)
    symbols = map_bits(clean, constellation.bits_per_symbol)
    validate_symbols(symbols, constellation.order)
    return modulate(constellation, symbols)
