"""F8-P4 coherent detection (NEW).

Separated stages: received signal -> decision statistic -> decision rule
-> detected symbol. Coherent threshold/correlator/matched-filter/
minimum-distance ML with uniform priors (ML = MAP documented); MAP only
with declared priors. Non-coherent energy detection is LIMITED to OOK/FSK.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.constellation import Constellation
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.math.logarithm import decimal_log10


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _check_received(received: object, limit: int = 65536) -> tuple:
    if not isinstance(received, (tuple, list)) or len(received) == 0:
        raise _fail(ControlStatus.INVALID, "received samples must be non-empty")
    if len(received) > limit:
        raise _fail(ControlStatus.INVALID, "detection budget exceeded")
    for y in received:
        if not isinstance(y, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "received samples must be DecimalComplex")
        if not y.re.is_finite() or not y.im.is_finite():
            raise _fail(ControlStatus.INVALID, "received samples must be finite")
    return tuple(received)


def threshold_decide(values: object, thresholds: object) -> tuple:
    """1-D region decision: region index per value over sorted thresholds."""
    if not isinstance(values, (tuple, list)) or len(values) == 0:
        raise _fail(ControlStatus.INVALID, "decision values must be non-empty")
    if not isinstance(thresholds, (tuple, list)) or len(thresholds) == 0:
        raise _fail(ControlStatus.INVALID, "thresholds must be non-empty")
    for thr in thresholds:
        if isinstance(thr, bool) or not isinstance(thr, Decimal):
            raise _fail(ControlStatus.INVALID, "thresholds must be Decimal")
        if not thr.is_finite():
            raise _fail(ControlStatus.INVALID, "thresholds must be finite")
    ordered = sorted(thresholds)
    if list(thresholds) != ordered:
        raise _fail(ControlStatus.INVALID, "thresholds must be sorted ascending")
    out: list = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, Decimal):
            raise _fail(ControlStatus.INVALID, "decision values must be Decimal")
        if not v.is_finite():
            raise _fail(ControlStatus.INVALID, "decision values must be finite")
        region = 0
        for thr in ordered:
            if v >= thr:
                region += 1
            else:
                break
        out.append(region)
    return tuple(out)


def matched_filter(waveform: object) -> tuple:
    """Discrete matched filter h[n] = conj(s[L-1-n]) (ML identity)."""
    if not isinstance(waveform, (tuple, list)) or len(waveform) == 0:
        raise _fail(ControlStatus.INVALID, "waveform must be non-empty")
    if len(waveform) > 65536:
        raise _fail(ControlStatus.INVALID, "detection budget exceeded")
    for s in waveform:
        if not isinstance(s, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "waveform must be DecimalComplex")
        if not s.re.is_finite() or not s.im.is_finite():
            raise _fail(ControlStatus.INVALID, "waveform must be finite")
    length = len(waveform)
    return tuple(waveform[length - 1 - n].conjugate() for n in range(length))


def inner_product(first: tuple, second: tuple) -> DecimalComplex:
    """<a, b> = sum conj(a[n])*b[n] under the working context."""
    if len(first) != len(second) or len(first) == 0:
        raise _fail(ControlStatus.INVALID, "correlator inputs must align non-empty")
    ctx = make_context()
    acc_re = Decimal(0)
    acc_im = Decimal(0)
    for a, b in zip(first, second):
        if not isinstance(a, DecimalComplex) or not isinstance(b, DecimalComplex):
            raise _fail(ControlStatus.INVALID, "correlator inputs must be DecimalComplex")
        prod = a.conjugate() * b
        acc_re = ctx.add(acc_re, prod.re)
        acc_im = ctx.add(acc_im, prod.im)
    return DecimalComplex(acc_re, acc_im)


def correlator_decide(received: object, candidates: object) -> tuple:
    """ML correlator: argmax Re{<y, s_i>} (equal-energy candidates)."""
    clean = _check_received(received)
    if not isinstance(candidates, (tuple, list)) or len(candidates) < 2:
        raise _fail(ControlStatus.INVALID, "correlator needs >= 2 candidates")
    width = len(candidates[0])
    for cand in candidates:
        if not isinstance(cand, (tuple, list)) or len(cand) != width or width == 0:
            raise _fail(ControlStatus.INVALID, "candidates must align non-empty")
    out: list = []
    for y in clean:
        if not isinstance(y, tuple):
            sample = (y,)
        else:
            sample = y
        if len(sample) != width:
            raise _fail(ControlStatus.INVALID, "received width must match candidates")
        best = 0
        best_stat: Decimal | None = None
        for idx, cand in enumerate(candidates):
            stat = inner_product(sample, tuple(cand)).re
            if best_stat is None or stat > best_stat:
                best_stat = stat
                best = idx
        out.append(best)
    return tuple(out)


def ml_decide(received: object, constellation: Constellation) -> tuple:
    """Minimum-distance ML over the constellation (ties -> lowest id)."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "ml_decide needs a Constellation")
    clean = _check_received(received)
    out: list = []
    for y in clean:
        best = 0
        best_dist: Decimal | None = None
        for point in constellation.points:
            dist = (y - point.coordinate).squared_modulus()
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = point.sid
        out.append(best)
    return tuple(out)


@dataclass(frozen=True)
class MapPriors:
    """Declared (non-uniform) symbol priors for MAP detection."""

    probabilities: tuple

    def __post_init__(self) -> None:
        if not isinstance(self.probabilities, tuple) or len(self.probabilities) < 2:
            raise _fail(ControlStatus.INVALID, "priors need >= 2 entries")
        ctx0 = make_context()
        total = Decimal(0)
        for p in self.probabilities:
            if isinstance(p, bool) or not isinstance(p, Decimal):
                raise _fail(ControlStatus.INVALID, "priors must be Decimal")
            if not p.is_finite() or p <= 0:
                raise _fail(ControlStatus.INVALID, "priors must be finite > 0")
            total = ctx0.add(total, p)
        if total <= 0:
            raise _fail(ControlStatus.INVALID, "priors must sum positive")


def map_decide(received: object, constellation: Constellation,
               priors: MapPriors, noise_variance: Decimal) -> tuple:
    """MAP with declared priors (ML iff priors uniform — never mixed silently)."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "map_decide needs a Constellation")
    if not isinstance(priors, MapPriors):
        raise _fail(ControlStatus.INVALID, "map_decide needs declared MapPriors")
    if len(priors.probabilities) != constellation.order:
        raise _fail(ControlStatus.INVALID, "priors must cover the alphabet")
    if isinstance(noise_variance, bool) or not isinstance(noise_variance, Decimal):
        raise _fail(ControlStatus.INVALID, "noise variance must be Decimal")
    if not noise_variance.is_finite() or noise_variance <= 0:
        raise _fail(ControlStatus.INVALID, "noise variance > 0 required")
    clean = _check_received(received)
    ctx = make_context()
    out: list = []
    for y in clean:
        best = 0
        best_metric: Decimal | None = None
        for point, prior in zip(constellation.points, priors.probabilities):
            dist = (y - point.coordinate).squared_modulus()
            metric = ctx.subtract(ctx.divide(dist, noise_variance),
                                  ctx.multiply(Decimal(2), _ln_decimal(prior, ctx)))
            if best_metric is None or metric < best_metric:
                best_metric = metric
                best = point.sid
        out.append(best)
    return tuple(out)


def _ln_decimal(value: Decimal, ctx) -> Decimal:
    """ln via certified log10 (ln x = log10(x)/log10(e)) — internal use."""
    log10e = decimal_log10(decimal_exp(Decimal(1), ctx), ctx)
    return ctx.divide(decimal_log10(value, ctx), log10e)


def energy_detect(received_energy: object, threshold_energy: object) -> tuple:
    """LIMITED non-coherent energy detector (OOK/FSK only)."""
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
