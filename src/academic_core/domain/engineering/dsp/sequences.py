"""F8-P2 uniform sequences + ideal sampling model I/O (NEW).

A Sequence is a causal uniform record ``x[n]``, ``n = 0..N-1``, with an
explicit sampling period ``T > 0`` (seconds). Values are real
(`Decimal`) or `DecimalComplex` (finite components). Insertion order is
significant and preserved by canonical serialization.

This is a different object from the F8-N lab `Waveform`
(continuous-time piecewise-linear over committed ``(t_i, x_i)``): no
uniform sampler exists in the repo, and N-110 forbids any `dsp -> lab`
edge, so Waveform-to-Sequence conversion stays structural (exact
point evaluation, implemented by callers — never an import).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Sequence as _TypingSequence

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.units import TIME, Unit, parse_unit

MAX_SEQUENCE_N = 65536


def to_sample_value(value: object) -> Decimal | DecimalComplex:
    """Normalise one sample (exact for int/Fraction-real inputs)."""
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, "sample rejects bool")
    if isinstance(value, DecimalComplex):
        if not value.re.is_finite() or not value.im.is_finite():
            raise ControlError(ControlStatus.INVALID, "sample must be finite")
        return value
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, Fraction):
        ctx = make_context()
        out = ctx.divide(Decimal(value.numerator), Decimal(value.denominator))
    else:
        raise ControlError(
            ControlStatus.INVALID,
            "sample must be Decimal/int/Fraction/DecimalComplex, got "
            + type(value).__name__,
        )
    if not out.is_finite():
        raise ControlError(ControlStatus.INVALID, "sample must be finite")
    return out


def _as_unit(value: object, label: str) -> Unit:
    if isinstance(value, Unit):
        return value
    if isinstance(value, str):
        try:
            return parse_unit(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, label + " bad unit string") from exc
    raise ControlError(ControlStatus.INVALID, label + " must be Unit/str")


def _as_period(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, "period rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, "bad period string") from exc
    else:
        raise ControlError(ControlStatus.INVALID, "period must be Decimal/int/str")
    if not out.is_finite() or out <= 0:
        raise ControlError(ControlStatus.INVALID, "period T > 0 required")
    return out


@dataclass(frozen=True)
class Sequence:
    """Causal uniform sequence (validation-only post-init)."""

    values: tuple
    period: Decimal
    values_unit: Unit
    period_unit: Unit

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or len(self.values) == 0:
            raise ControlError(ControlStatus.INVALID, "sequence needs a non-empty tuple")
        if len(self.values) > MAX_SEQUENCE_N:
            raise ControlError(ControlStatus.INVALID, "sequence budget exceeded")
        for item in self.values:
            if isinstance(item, bool) or not isinstance(item, (Decimal, DecimalComplex)):
                raise ControlError(ControlStatus.INVALID, "samples must be Decimal/DecimalComplex")
            if isinstance(item, Decimal):
                if not item.is_finite():
                    raise ControlError(ControlStatus.INVALID, "samples must be finite")
            else:
                if not item.re.is_finite() or not item.im.is_finite():
                    raise ControlError(ControlStatus.INVALID, "samples must be finite")
        if isinstance(self.period, bool) or not isinstance(self.period, Decimal):
            raise ControlError(ControlStatus.INVALID, "period must be Decimal")
        if not self.period.is_finite() or self.period <= 0:
            raise ControlError(ControlStatus.INVALID, "period T > 0 required")
        if not isinstance(self.values_unit, Unit) or not isinstance(self.period_unit, Unit):
            raise ControlError(ControlStatus.INVALID, "sequence units must be Unit")
        if self.period_unit.dimension != TIME:
            raise ControlError(ControlStatus.INVALID, "period unit must be time")

    @property
    def length(self) -> int:
        return len(self.values)

    @property
    def sample_rate(self) -> Decimal:
        """fs = 1/T, exact Decimal division under the working context."""
        return make_context().divide(Decimal(1), self.period)

    def to_dict(self) -> dict:
        out: list = []
        for v in self.values:
            if isinstance(v, DecimalComplex):
                out.append({"re": str(v.re), "im": str(v.im)})
            else:
                out.append(str(v))
        return {
            "length": self.length,
            "period_s": str(self.period),
            "values": out,
        }

    @staticmethod
    def create(values: _TypingSequence[object], period: object,
               values_unit: object = "1", period_unit: object = "s") -> "Sequence":
        if not isinstance(values, (tuple, list)) or len(values) == 0:
            raise ControlError(ControlStatus.INVALID, "sequence needs non-empty values")
        if len(values) > MAX_SEQUENCE_N:
            raise ControlError(ControlStatus.INVALID, "sequence budget exceeded")
        return Sequence(
            values=tuple(to_sample_value(v) for v in values),
            period=_as_period(period),
            values_unit=_as_unit(values_unit, "values unit"),
            period_unit=_as_unit(period_unit, "period unit"),
        )


def sample_signal(kind: str, params: dict, period: object, count: int,
                  values_unit: object = "1") -> Sequence:
    """Ideal uniform sampler over closed-form analytic recipes (data only).

    kinds: sine{freq_hz, amplitude, phase_rad}, cosine{...},
    constant{value}, step{value}, impulse{index}, geometric{a}.
    All frequencies in Hz (Decimal), phases in radians (Decimal labels).
    """
    if not isinstance(kind, str):
        raise ControlError(ControlStatus.INVALID, "sampler kind must be a string")
    if not isinstance(params, dict):
        raise ControlError(ControlStatus.INVALID, "sampler params must be a dict")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ControlError(ControlStatus.INVALID, "sample count N >= 1 required")
    if count > MAX_SEQUENCE_N:
        raise ControlError(ControlStatus.INVALID, "sequence budget exceeded")
    t_step = _as_period(period)
    ctx = make_context()
    key = kind.strip().lower()

    def req(name: str) -> Decimal:
        raw = params.get(name)
        if isinstance(raw, bool):
            raise ControlError(ControlStatus.INVALID, "sampler param rejects bool")
        if isinstance(raw, Decimal):
            out = raw
        elif isinstance(raw, int):
            out = Decimal(raw)
        elif isinstance(raw, str):
            try:
                out = Decimal(raw.strip())
            except Exception as exc:
                raise ControlError(ControlStatus.INVALID, "bad sampler param") from exc
        else:
            raise ControlError(ControlStatus.INVALID, "sampler param must be numeric")
        if not out.is_finite():
            raise ControlError(ControlStatus.INVALID, "sampler param must be finite")
        return out

    if key in ("sine", "cosine"):
        freq = req("freq_hz")
        ampl = req("amplitude")
        phase = req("phase_rad") if "phase_rad" in params else Decimal(0)
        if freq < 0:
            raise ControlError(ControlStatus.INVALID, "sampler frequency >= 0 required")
        out: list = []
        for n in range(count):
            angle = ctx.multiply(ctx.multiply(ctx.multiply(Decimal(2), decimal_pi(ctx)), freq),
                                 ctx.multiply(t_step, Decimal(n)))
            angle = ctx.add(angle, phase)
            trig = decimal_sin(angle, ctx) if key == "sine" else decimal_cos(angle, ctx)
            out.append(ctx.multiply(ampl, trig))
        return Sequence.create(out, t_step, values_unit)
    if key == "constant":
        cval = req("value")
        return Sequence.create([cval] * count, t_step, values_unit)
    if key == "step":
        cval = req("value")
        return Sequence.create([cval] * count, t_step, values_unit)
    if key == "impulse":
        raw = params.get("index", 0)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0 or raw >= count:
            raise ControlError(ControlStatus.INVALID, "impulse index in [0, N) required")
        out = [Decimal(0)] * count
        out[raw] = Decimal(1)
        return Sequence.create(out, t_step, values_unit)
    if key == "geometric":
        base = req("a")
        out = []
        acc = Decimal(1)
        for _ in range(count):
            out.append(ctx.plus(acc))
            acc = ctx.multiply(acc, base)
        return Sequence.create(out, t_step, values_unit)
    raise ControlError(ControlStatus.UNSUPPORTED, "unknown sampler recipe " + kind.strip())
