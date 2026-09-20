"""F8-N Virtual Laboratory — Waveform (committed samples, PL signal model).

Signal model: committed samples ``(t_i, x_i)``, ``i = 0..N-1``, joined by
straight segments (piecewise linear). All integrals are *exact* for that
model. Window ends inside a segment use the interpolated value (exact
under PL). Everything is Decimal under :func:`lab_context`; undefined
results are ``None`` with a reason, never 0.
"""
from decimal import Decimal

from .model import Waveform, lab_context

_ZERO = Decimal(0)


def make_waveform(times, values, dimension, unit_label="", source=""):
    """Build a Waveform from committed engine samples (exact copy, no
    resampling). Accepts any sequence of Decimal."""
    return Waveform(tuple(times), tuple(values), dimension,
                    unit_label=unit_label, source=source)


def window_breakpoints(wave, a, b):
    """Breakpoints of the PL signal restricted to ``[a, b]``.

    Returns ``(ts, xs)`` with ``ts[0] == a``, ``ts[-1] == b`` (window
    ends interpolated exactly under PL). Needs ``t_0 <= a < b <= t_{N-1}``.
    Raises ``ValueError`` with a reason string when the window is invalid.
    """
    times = wave.times
    values = wave.values
    if not a < b:
        raise ValueError("window needs a < b")
    if a < times[0] or b > times[-1]:
        raise ValueError("window outside simulated span")
    with lab_context():
        ts = [a]
        xs = [_interp_raw(times, values, a)]
        for t, x in zip(times, values):
            if a < t < b:
                ts.append(t)
                xs.append(x)
        ts.append(b)
        xs.append(_interp_raw(times, values, b))
    return tuple(ts), tuple(xs)


def _interp_raw(times, values, t):
    """Raw PL interpolation (caller holds the lab context)."""
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = times[lo], times[hi]
    x0, x1 = values[lo], values[hi]
    if t1 == t0:
        return x0
    frac = (t - t0) / (t1 - t0)
    return x0 + (x1 - x0) * frac


def interpolate(wave, t):
    """PL interpolation at ``t``; exact hits return the committed value."""
    with lab_context():
        return _interp_raw(wave.times, wave.values, t)


def segment_integral(xs_ts):
    """Exact integral pieces of a PL signal over breakpoints.

    Returns ``(area, area_sq)`` = ``(integral x dt, integral x^2 dt)``
    with ``integral x^2 dt = sum h_j (x_j^2 + x_j x_{j+1} + x_{j+1}^2)/3``.
    """
    ts, xs = xs_ts
    area = _ZERO
    area_sq = _ZERO
    with lab_context():
        for j in range(len(ts) - 1):
            h = ts[j + 1] - ts[j]
            x0, x1 = xs[j], xs[j + 1]
            area += h * (x0 + x1) / Decimal(2)
            area_sq += h * (x0 * x0 + x0 * x1 + x1 * x1) / Decimal(3)
    return area, area_sq


def wave_mean(wave, a, b):
    """Exact PL mean over ``[a, b]``: ``(1/(b-a)) integral x dt``."""
    ts, xs = window_breakpoints(wave, a, b)
    area, _ = segment_integral((ts, xs))
    with lab_context():
        return area / (b - a)


def wave_rms(wave, a, b):
    """Exact PL RMS over ``[a, b]``: ``sqrt((1/(b-a)) integral x^2 dt)``."""
    ts, xs = window_breakpoints(wave, a, b)
    _, area_sq = segment_integral((ts, xs))
    with lab_context():
        return (area_sq / (b - a)).sqrt()


def wave_min_max(wave, a, b):
    """``(min, max)`` over ``[a, b]`` (extremes of a PL signal occur at
    breakpoints, window ends included)."""
    _, xs = window_breakpoints(wave, a, b)
    return min(xs), max(xs)


def _cross_in_segment(x0, x1, level, slope):
    """Whether the open-directed segment crosses ``level`` per the trigger
    attribution rule (no double counting of exact hits)."""
    if slope in ("rising", "either") and x0 < level <= x1:
        return True
    if slope in ("falling", "either") and x0 > level >= x1:
        return True
    return False


def _cross_time(t0, t1, x0, x1, level):
    """Exact rational-Decimal crossing time inside one segment."""
    with lab_context():
        return t0 + (level - x0) * (t1 - t0) / (x1 - x0)


def crossings(wave, level, slope="rising", hysteresis=None, a=None, b=None):
    """Crossing times of ``level`` in ``[a, b]`` (default the whole run).

    Rising: ``x_i < L <= x_{i+1}``; falling: ``x_i > L >= x_{i+1}``; a
    sample exactly equal to ``L`` belongs to the segment that *ends* at
    ``L`` (no double counting). Hysteresis ``h`` arms the next accepted
    crossing only after the signal has been ``< L - h`` (rising) or
    ``> L + h`` (falling) since the previous accepted crossing.
    """
    times = wave.times
    values = wave.values
    lo = times[0] if a is None else a
    hi = times[-1] if b is None else b
    if not lo < hi:
        raise ValueError("window needs a < b")
    if lo < times[0] or hi > times[-1]:
        raise ValueError("window outside simulated span")
    h = _ZERO if hysteresis is None else hysteresis
    found = []
    armed_rising = True
    armed_falling = True
    with lab_context():
        for i in range(len(times) - 1):
            t0, t1 = times[i], times[i + 1]
            if t1 <= lo or t0 >= hi:
                # Still track arming outside the window for determinism
                # of hysteresis state? No: arming restarts at the window
                # start (documented, deterministic).
                continue
            x0, x1 = values[i], values[i + 1]
            if h > 0:
                if x0 < level - h or x1 < level - h:
                    armed_rising = True
                if x0 > level + h or x1 > level + h:
                    armed_falling = True
            if _cross_in_segment(x0, x1, level, slope):
                if slope in ("rising", "either") and x0 < level <= x1:
                    if h > 0 and not armed_rising:
                        continue
                    tc = _cross_time(t0, t1, x0, x1, level)
                    if lo <= tc <= hi:
                        found.append(tc)
                        armed_rising = False
                if slope in ("falling", "either") and x0 > level >= x1:
                    if h > 0 and not armed_falling:
                        continue
                    # For "either" on a segment crossing both ways is
                    # impossible (monotone segment); recompute once.
                    tc = _cross_time(t0, t1, x0, x1, level)
                    if lo <= tc <= hi and not (slope == "either" and found
                                               and found[-1] == tc):
                        found.append(tc)
                        armed_falling = False
    return tuple(found)


def band_exit_times(wave, v_final, band, a, b):
    """Last times the PL signal touches the band boundary in ``[a, b]``.

    Returns the sorted tuple of boundary-crossing times (linear
    interpolation, exact under PL). Empty means the signal never touches
    the boundary (always strictly inside or always outside). The
    settling time is the last such time (an *entry* counts: the signal
    that starts outside and enters at ``t_e`` settles at ``t_e``).
    """
    ts, xs = window_breakpoints(wave, a, b)
    touches = []
    with lab_context():
        upper = v_final + band
        lower = v_final - band
        for j in range(len(ts) - 1):
            t0, t1 = ts[j], ts[j + 1]
            x0, x1 = xs[j], xs[j + 1]
            in0 = lower <= x0 <= upper
            in1 = lower <= x1 <= upper
            if in0 == in1:
                continue
            if x0 == x1:  # unreachable (in0 != in1 needs x0 != x1)
                continue
            if (x0 > upper) != (x1 > upper):
                edge = upper
            elif (x0 < lower) != (x1 < lower):
                edge = lower
            else:  # endpoint exactly on the edge: the touch is at t0
                touches.append(t0)
                continue
            touches.append(t0 + (edge - x0) * (t1 - t0) / (x1 - x0))
    return tuple(touches)
