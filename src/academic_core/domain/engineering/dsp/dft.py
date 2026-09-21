"""F8-P2 DFT/IDFT + radix-2 FFT/IFFT (NEW).

Definitional core: exact finite sums
    X[k] = Σ_{n=0}^{N-1} x[n]·W_N^{kn},
    x[n] = (1/N)·Σ_{k=0}^{N-1} X[k]·W_N^{−kn},
with W_N = e^{−j2π/N} from certified Decimal trig (never binary float,
never a trig literal). Axis twiddles (multiples of π/2) resolve to
their mathematically exact values — a documented exactness rule, not
rounding. FFT is an exact DIT reordering of the same sum (bit-reversal
+ butterflies, deterministic loop order); non-power-of-2 input is
INVALID pointing at DFT-direct, never a silent Bluestein.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.dsp.sequences import Sequence, to_sample_value
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_FFT_N = 4096
MAX_DIRECT_DFT_N = 512


def _as_samples(values: object) -> tuple:
    if isinstance(values, Sequence):
        raw = values.values
    elif isinstance(values, (tuple, list)):
        raw = tuple(values)
    else:
        raise ControlError(ControlStatus.INVALID, "spectral input must be Sequence/tuple/list")
    if len(raw) == 0:
        raise ControlError(ControlStatus.INVALID, "empty spectrum input")
    return tuple(to_sample_value(v) for v in raw)


def _promote(value: Decimal | DecimalComplex) -> DecimalComplex:
    if isinstance(value, DecimalComplex):
        return value
    return DecimalComplex(value, Decimal(0))


def _is_power_of_two(n: int) -> bool:
    return n >= 1 and (n & (n - 1)) == 0


def twiddle(index: int, size: int, inverse: bool = False) -> DecimalComplex:
    """W_size^index = e^{∓j2π·index/size} (− for DFT, + for IDFT).

    Axis-exact rule: when the angle is an exact multiple of π/2 (i.e.
    ``(4·m) mod size == 0`` with ``m = index mod size``), the
    mathematically exact axis value is returned instead of a trig
    evaluation. All other angles go through certified decimal_cos/sin.
    """
    if not isinstance(size, int) or size < 1:
        raise ControlError(ControlStatus.INVALID, "twiddle size N >= 1 required")
    if not isinstance(index, int):
        raise ControlError(ControlStatus.INVALID, "twiddle index must be int")
    m = index % size
    ctx = make_context()
    if (4 * m) % size == 0:
        quadrant = (4 * m) // size % 4
        if not inverse:
            table = (
                DecimalComplex(Decimal(1), Decimal(0)),
                DecimalComplex(Decimal(0), Decimal(-1)),
                DecimalComplex(Decimal(-1), Decimal(0)),
                DecimalComplex(Decimal(0), Decimal(1)),
            )
        else:
            table = (
                DecimalComplex(Decimal(1), Decimal(0)),
                DecimalComplex(Decimal(0), Decimal(1)),
                DecimalComplex(Decimal(-1), Decimal(0)),
                DecimalComplex(Decimal(0), Decimal(-1)),
            )
        return table[quadrant]
    two_pi = ctx.multiply(decimal_pi(ctx), Decimal(2))
    angle = ctx.divide(ctx.multiply(two_pi, Decimal(m)), Decimal(size))
    cos_v = decimal_cos(angle, ctx)
    sin_v = decimal_sin(angle, ctx)
    if inverse:
        return DecimalComplex(cos_v, sin_v)
    return DecimalComplex(cos_v, ctx.minus(sin_v))


def _power_table(size: int, inverse: bool = False) -> tuple:
    """W_size^m for m = 0..size−1 (O(N) trig evals, indexed mod N)."""
    return tuple(twiddle(m, size, inverse) for m in range(size))


def dft(values: object) -> tuple:
    """Direct DFT sum (reference implementation — never removed)."""
    raw = _as_samples(values)
    size = len(raw)
    if size > MAX_DIRECT_DFT_N:
        raise ControlError(ControlStatus.INVALID, "DFT-direct budget exceeded")
    table = _power_table(size, False)
    out: list = []
    for k in range(size):
        acc = DecimalComplex(Decimal(0), Decimal(0))
        for n in range(size):
            acc = acc + _promote(raw[n]) * table[(k * n) % size]
        out.append(acc)
    return tuple(out)


def idft(values: object) -> tuple:
    """Direct IDFT sum with the exact 1/N factor."""
    raw = _as_samples(values)
    size = len(raw)
    if size > MAX_DIRECT_DFT_N:
        raise ControlError(ControlStatus.INVALID, "IDFT-direct budget exceeded")
    ctx = make_context()
    scale = ctx.divide(Decimal(1), Decimal(size))
    table = _power_table(size, True)
    out: list = []
    for n in range(size):
        acc = DecimalComplex(Decimal(0), Decimal(0))
        for k in range(size):
            acc = acc + _promote(raw[k]) * table[(k * n) % size]
        out.append(acc * DecimalComplex(scale, Decimal(0)))
    return tuple(out)


def _bit_reversed(data: list) -> list:
    size = len(data)
    bits = size.bit_length() - 1
    out: list = [DecimalComplex(Decimal(0), Decimal(0))] * size
    for i in range(size):
        rev = 0
        word = i
        for _ in range(bits):
            rev = (rev << 1) | (word & 1)
            word >>= 1
        out[rev] = data[i]
    return out


def _check_fft_size(size: int) -> None:
    if not _is_power_of_two(size):
        raise ControlError(
            ControlStatus.INVALID,
            "FFT needs N = 2^m; use DFT-direct for other sizes",
        )
    if size > MAX_FFT_N:
        raise ControlError(ControlStatus.INVALID, "FFT budget exceeded")


def fft(values: object) -> tuple:
    """Iterative radix-2 DIT FFT (deterministic bit-reversal + stages)."""
    raw = _as_samples(values)
    size = len(raw)
    _check_fft_size(size)
    data = _bit_reversed([_promote(v) for v in raw])
    length = 2
    while length <= size:
        half = length // 2
        for start in range(0, size, length):
            for j in range(half):
                factor = twiddle(j, length, False)
                left = data[start + j]
                right = data[start + j + half] * factor
                data[start + j] = left + right
                data[start + j + half] = left - right
        length *= 2
    return tuple(data)


def ifft(values: object) -> tuple:
    """Iterative radix-2 IFFT (conjugate twiddles + exact 1/N)."""
    raw = _as_samples(values)
    size = len(raw)
    _check_fft_size(size)
    ctx = make_context()
    scale = DecimalComplex(ctx.divide(Decimal(1), Decimal(size)), Decimal(0))
    data = _bit_reversed([_promote(v) for v in raw])
    length = 2
    while length <= size:
        half = length // 2
        for start in range(0, size, length):
            for j in range(half):
                factor = twiddle(j, length, True)
                left = data[start + j]
                right = data[start + j + half] * factor
                data[start + j] = left + right
                data[start + j + half] = left - right
        length *= 2
    return tuple(entry * scale for entry in data)


def dtft_at(values: object, theta: Decimal) -> DecimalComplex:
    """Direct DTFT sum Σ x[n]·e^{−jnθ} at one digital frequency."""
    if isinstance(theta, bool) or not isinstance(theta, Decimal):
        raise ControlError(ControlStatus.INVALID, "dtft angle must be Decimal")
    if not theta.is_finite():
        raise ControlError(ControlStatus.INVALID, "dtft angle must be finite")
    raw = _as_samples(values)
    ctx = make_context()
    acc = DecimalComplex(Decimal(0), Decimal(0))
    for n, item in enumerate(raw):
        angle = ctx.multiply(theta, Decimal(n))
        basis = DecimalComplex(decimal_cos(angle, ctx), ctx.minus(decimal_sin(angle, ctx)))
        acc = acc + _promote(item) * basis
    return acc


def circular_convolve(first: object, second: object) -> tuple:
    """Direct circular convolution (common length N required)."""
    a_raw = _as_samples(first)
    b_raw = _as_samples(second)
    if len(a_raw) != len(b_raw):
        raise ControlError(ControlStatus.INVALID, "circular convolution needs equal lengths")
    size = len(a_raw)
    a_c = [_promote(v) for v in a_raw]
    b_c = [_promote(v) for v in b_raw]
    out: list = []
    for n in range(size):
        acc = DecimalComplex(Decimal(0), Decimal(0))
        for m in range(size):
            acc = acc + a_c[m] * b_c[(n - m) % size]
        out.append(acc)
    return tuple(out)


def frequency_bins(rate_hz: Decimal, size: int) -> tuple:
    """Exact bin frequencies f_k = k·fs/N (Decimal, caller owns units)."""
    if isinstance(rate_hz, bool) or not isinstance(rate_hz, Decimal):
        raise ControlError(ControlStatus.INVALID, "bin rate must be Decimal")
    if not rate_hz.is_finite() or rate_hz <= 0:
        raise ControlError(ControlStatus.INVALID, "bin rate fs > 0 required")
    if not isinstance(size, int) or size < 1:
        raise ControlError(ControlStatus.INVALID, "bin count N >= 1 required")
    ctx = make_context()
    return tuple(ctx.divide(ctx.multiply(Decimal(k), rate_hz), Decimal(size)) for k in range(size))


def nyquist_index(size: int) -> int | None:
    """Bin k = N/2 for even N; None when no integer Nyquist bin exists."""
    if not isinstance(size, int) or size < 1:
        raise ControlError(ControlStatus.INVALID, "bin count N >= 1 required")
    if size % 2 == 1:
        return None
    return size // 2
