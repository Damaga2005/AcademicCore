"""F8-P2 ideal sampling: Nyquist verdict, alias map, reconstruction (NEW).

Ideal uniform model only: x[n] = x_c(nT), fs = 1/T. The Nyquist
verdict distinguishes rate (2·fmax) from frequency (fs/2) explicitly.
The alias map is exact integer/rational arithmetic with a canonical
folded range [0, fs/2] (half-up boundary rule, documented). Ideal sinc
reconstruction carries the node-exactness identity x(mT) = x[m] through
a symbolic node shortcut — never through approximating sin(πk)
numerically. Truncated lobes report an explicit tail bound (self-checked
in tests); the ≤1e-6 tolerance lives only here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.dsp.sequences import Sequence, to_sample_value
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_RECON_LOBES = 5000


def _as_freq(value: object, label: str, allow_zero: bool = True) -> Decimal:
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal/int/str")
    if not out.is_finite():
        raise ControlError(ControlStatus.INVALID, label + " must be finite")
    if out < 0 or (not allow_zero and out <= 0):
        raise ControlError(ControlStatus.INVALID, label + " range violated")
    return out


def nyquist_verdict(signal_freq: object, rate_hz: object) -> str:
    """CLEAN (f < fs/2), MARGINAL (f = fs/2, node-only), ALIASED (f > fs/2)."""
    freq = _as_freq(signal_freq, "signal frequency")
    rate = _as_freq(rate_hz, "sample rate", allow_zero=False)
    ctx = make_context()
    half = ctx.divide(rate, Decimal(2))
    if freq < half:
        return "CLEAN"
    if freq == half:
        return "MARGINAL"
    return "ALIASED"


def nyquist_rate(signal_freq: object) -> Decimal:
    """Nyquist rate = 2·fmax (a rate, not a frequency — see verdict)."""
    freq = _as_freq(signal_freq, "signal frequency")
    return make_context().multiply(Decimal(2), freq)


def nyquist_frequency(rate_hz: object) -> Decimal:
    """Nyquist frequency = fs/2 (a frequency, not a rate)."""
    rate = _as_freq(rate_hz, "sample rate", allow_zero=False)
    return make_context().divide(rate, Decimal(2))


def alias_of(signal_freq: object, rate_hz: object) -> Decimal:
    """Folded alias f_a = |f − round(f/fs)·fs| in [0, fs/2].

    Exact Decimal arithmetic; .5 boundaries round half-up (canonical).
    """
    freq = _as_freq(signal_freq, "signal frequency")
    rate = _as_freq(rate_hz, "sample rate", allow_zero=False)
    ctx = make_context()
    quotient = ctx.divide(freq, rate)
    folds = int(quotient.to_integral_value(rounding=ROUND_HALF_UP))
    folded = ctx.subtract(freq, ctx.multiply(Decimal(folds), rate))
    return folded.copy_abs()


def _sinc(unit_offset: Decimal, ctx) -> Decimal:
    if unit_offset == 0:
        return ctx.plus(Decimal(1))
    arg = ctx.multiply(decimal_pi(ctx), unit_offset)
    return ctx.divide(decimal_sin(arg, ctx), arg)


@dataclass(frozen=True)
class ReconstructReport:
    value: str
    node_exact: bool
    truncated: bool
    lobes_used: int
    tail_bound: str
    detail: str = ""


def reconstruct(sequence: Sequence, time_s: object, lobes: int = 64) -> ReconstructReport:
    """Ideal sinc reconstruction x(t) = Σ x[n]·sinc((t−nT)/T).

    Node shortcut: when t − n·T == 0 exactly for some n, x[n] returns
    verbatim (symbolic, exact — the sin(πk) numerics never run).
    Otherwise the centred lobe window sums min(N, window) terms and
    records truncation + an explicit tail bound
    (tail ≤ Xmax·N_excl/(π·d_min), documented crude-but-valid).
    """
    if not isinstance(sequence, Sequence):
        raise ControlError(ControlStatus.INVALID, "reconstruct needs a Sequence")
    if isinstance(time_s, bool):
        raise ControlError(ControlStatus.INVALID, "time rejects bool")
    if isinstance(time_s, Decimal):
        moment = time_s
    elif isinstance(time_s, int):
        moment = Decimal(time_s)
    else:
        raise ControlError(ControlStatus.INVALID, "time must be Decimal/int")
    if not moment.is_finite() or moment < 0:
        raise ControlError(ControlStatus.INVALID, "time t >= 0 required")
    if isinstance(lobes, bool) or not isinstance(lobes, int) or lobes < 1:
        raise ControlError(ControlStatus.INVALID, "lobe budget >= 1 required")
    if lobes > MAX_RECON_LOBES:
        raise ControlError(ControlStatus.INVALID, "lobe budget exceeded")
    ctx = make_context()
    period = sequence.period
    count = sequence.length
    # Reconstruction is real-valued: complex sequences are UNSUPPORTED
    # before any shortcut (a complex node value has no real image).
    for item in sequence.values:
        if isinstance(item, DecimalComplex):
            raise ControlError(
                ControlStatus.UNSUPPORTED, "reconstruction is real-valued")
    # Node shortcut: exact Decimal equality, no trig runs.
    for n in range(count):
        if ctx.subtract(moment, ctx.multiply(period, Decimal(n))) == 0:
            val = sequence.values[n]
            out = val.re if isinstance(val, DecimalComplex) else val
            return ReconstructReport(
                value=str(ctx.plus(out)), node_exact=True, truncated=False,
                lobes_used=0, tail_bound="0", detail="node identity")
    # Centred window over real-valued sequences.
    centre = ctx.divide(moment, period)
    lo = max(0, int((centre - lobes).to_integral_value(rounding=ROUND_HALF_UP)))
    hi = min(count - 1, int((centre + lobes).to_integral_value(rounding=ROUND_HALF_UP)))
    acc = Decimal(0)
    peak = Decimal(0)
    for n in range(lo, hi + 1):
        unit = ctx.divide(ctx.subtract(moment, ctx.multiply(period, Decimal(n))), period)
        term = ctx.multiply(sequence.values[n], _sinc(unit, ctx))
        acc = ctx.add(acc, term)
        mag = sequence.values[n].copy_abs()
        if mag > peak:
            peak = mag
    excluded = count - (hi - lo + 1)
    truncated = excluded > 0
    if truncated:
        edge = Decimal(lobes if lobes >= 1 else 1)
        bound = ctx.divide(
            ctx.multiply(peak, Decimal(excluded)), ctx.multiply(decimal_pi(ctx), edge))
    else:
        bound = Decimal(0)
    return ReconstructReport(
        value=str(ctx.plus(acc)), node_exact=False, truncated=truncated,
        lobes_used=hi - lo + 1, tail_bound=str(bound),
        detail="truncated sinc sum" if truncated else "full sinc sum")


def sample_times(period: Decimal, count: int) -> tuple:
    """Exact node times n·T (the node-shortcut construction)."""
    if isinstance(period, bool) or not isinstance(period, Decimal):
        raise ControlError(ControlStatus.INVALID, "period must be Decimal")
    if not period.is_finite() or period <= 0:
        raise ControlError(ControlStatus.INVALID, "period T > 0 required")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ControlError(ControlStatus.INVALID, "count N >= 1 required")
    ctx = make_context()
    return tuple(ctx.multiply(period, Decimal(n)) for n in range(count))


def to_sequence_uniform(times_values: object, period: object,
                        values_unit: object = "1") -> Sequence:
    """Structural Waveform→Sequence bridge (exact point evaluation).

    Takes plain (times, values) tuples — never a lab object (N-110) —
    and validates uniformity within exact Decimal equality.
    """
    if (not isinstance(times_values, (tuple, list)) or len(times_values) != 2):
        raise ControlError(ControlStatus.INVALID, "bridge needs (times, values)")
    times, vals = times_values
    if not isinstance(times, (tuple, list)) or not isinstance(vals, (tuple, list)):
        raise ControlError(ControlStatus.INVALID, "bridge needs (times, values)")
    if len(times) != len(vals) or len(times) == 0:
        raise ControlError(ControlStatus.INVALID, "bridge needs aligned non-empty data")
    t_step = period if isinstance(period, Decimal) else None
    if t_step is None:
        raise ControlError(ControlStatus.INVALID, "bridge period must be Decimal")
    if not t_step.is_finite() or t_step <= 0:
        raise ControlError(ControlStatus.INVALID, "period T > 0 required")
    ctx = make_context()
    for index in range(len(times)):
        expect = ctx.multiply(t_step, Decimal(index))
        got = times[index] if isinstance(times[index], Decimal) else None
        if got is None or got != expect:
            raise ControlError(ControlStatus.INVALID, "bridge data not uniform on T")
    return Sequence.create(
        tuple(to_sample_value(v) for v in vals), t_step, values_unit)
