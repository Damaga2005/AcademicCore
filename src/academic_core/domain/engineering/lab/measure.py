"""F8-N Virtual Laboratory — measurement functions.

Every measurement is a declared pure function of run state with an exact
mathematical definition (design gate, Measurement Functions table).
Undefined results are ``None`` with a reason, never 0.
"""
from decimal import Decimal

from .model import (
    DIMENSIONLESS,
    FREQUENCY,
    TIME,
    MeasurementKind,
    MeasurementResult,
    MeasurementStatus,
    Scalar,
    Slope,
    lab_context,
)
from .waveform import (
    band_exit_times,
    crossings,
    wave_mean,
    wave_min_max,
    wave_rms,
)

_ZERO = Decimal(0)
_OK = MeasurementStatus.OK.value
_UNDEF = MeasurementStatus.UNDEFINED.value
_INVALID = MeasurementStatus.INVALID_MEASUREMENT.value
_NO_DATA = MeasurementStatus.NO_DATA.value


def _scalar(value, dimension, unit_label, source):
    return Scalar(value, dimension, unit_label, source)


def _result(run_id, key, value, status, reason=""):
    return MeasurementResult(run_id, key, value, status, reason)


def _window_of(wave, window):
    if window is None:
        return wave.times[0], wave.times[-1]
    return window[0], window[1]


def measure_max_min_pp(run_id, key, wave, kind, window=None, source=""):
    """max / min / pp over ``window`` (default whole run)."""
    try:
        a, b = _window_of(wave, window)
        lo, hi = wave_min_max(wave, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    with lab_context():
        if kind == MeasurementKind.MAX.value:
            val = hi
        elif kind == MeasurementKind.MIN.value:
            val = lo
        else:
            val = hi - lo
    return _result(run_id, key, _scalar(val, wave.dimension, wave.unit_label, source), _OK)


def measure_mean(run_id, key, wave, window=None, source=""):
    try:
        a, b = _window_of(wave, window)
        val = wave_mean(wave, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    return _result(run_id, key, _scalar(val, wave.dimension, wave.unit_label, source), _OK)


def measure_rms(run_id, key, wave, window=None, source=""):
    try:
        a, b = _window_of(wave, window)
        val = wave_rms(wave, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    return _result(run_id, key, _scalar(val, wave.dimension, wave.unit_label, source), _OK)


def measure_crossings(run_id, key, wave, level, slope="rising",
                      hysteresis=None, window=None, source=""):
    """Crossing list; no crossings is OK with count 0 (empty payload)."""
    if level is None:
        return _result(run_id, key, None, _INVALID, "crossings needs a level")
    try:
        Slope(slope)
    except ValueError:
        return _result(run_id, key, None, _INVALID, f"unknown slope {slope!r}")
    try:
        a, b = _window_of(wave, window)
        found = crossings(wave, level, slope, hysteresis, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    # Count result: dimensionless scalar carrying the count.
    return _result(run_id, key,
                   _scalar(Decimal(len(found)), DIMENSIONLESS, "1", source),
                   _OK, f"{len(found)} crossings")


def _default_level(wave, a, b):
    lo, hi = wave_min_max(wave, a, b)
    with lab_context():
        return (hi + lo) / Decimal(2)


def measure_period_frequency(run_id, key, wave, kind, level=None,
                             hysteresis=None, window=None, source=""):
    """period = (t_K - t_1)/(K-1) over rising crossings; frequency = 1/period.

    ``K < 2`` is UNDEFINED (never 0 Hz)."""
    try:
        a, b = _window_of(wave, window)
        if level is None:
            level = _default_level(wave, a, b)
        found = crossings(wave, level, "rising", hysteresis, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    if len(found) < 2:
        return _result(run_id, key, None, _UNDEF, "fewer than two rising crossings")
    with lab_context():
        period = (found[-1] - found[0]) / Decimal(len(found) - 1)
        if kind == MeasurementKind.PERIOD.value:
            return _result(run_id, key, _scalar(period, TIME, "s", source), _OK)
        return _result(run_id, key, _scalar(Decimal(1) / period, FREQUENCY, "Hz", source), _OK)


def _edge_levels(v_low, v_high, auto_levels, wave, a, b):
    if auto_levels:
        if v_low is not None or v_high is not None:
            return None, None, "auto_levels conflicts with explicit v_low/v_high"
        try:
            lo, hi = wave_min_max(wave, a, b)
        except ValueError as exc:
            return None, None, str(exc)
        return lo, hi, ""
    if v_low is None or v_high is None:
        return None, None, "rise/fall needs v_low and v_high (or auto_levels)"
    return v_low, v_high, ""


def measure_rise_fall(run_id, key, wave, kind, low_frac, high_frac,
                      v_low=None, v_high=None, auto_levels=False,
                      window=None, source=""):
    """rise = t_hi - t_lo with first rising crossings of the fractional
    levels (mirror image with falling crossings for fall_time)."""
    rising = kind == MeasurementKind.RISE_TIME.value
    if low_frac is None or high_frac is None:
        return _result(run_id, key, None, _INVALID,
                       "rise/fall needs low_frac and high_frac (no hidden default)")
    with lab_context():
        ok_frac = _ZERO < low_frac < high_frac < Decimal(1)
    if not ok_frac:
        return _result(run_id, key, None, _INVALID, "need 0 < low_frac < high_frac < 1")
    try:
        a, b = _window_of(wave, window)
        lo_v, hi_v, err = _edge_levels(v_low, v_high, auto_levels, wave, a, b)
        if err:
            return _result(run_id, key, None, _INVALID, err)
        with lab_context():
            delta = hi_v - lo_v
            if not delta > 0:
                return _result(run_id, key, None, _INVALID,
                               "rise/fall needs v_high > v_low")
            if rising:
                l_lo = lo_v + low_frac * delta
                l_hi = lo_v + high_frac * delta
            else:
                l_lo = hi_v - low_frac * delta
                l_hi = hi_v - high_frac * delta
            slope = "rising" if rising else "falling"
            first = crossings(wave, l_lo, slope, None, a, b)
            if not first:
                return _result(run_id, key, None, _UNDEF, "low edge not found")
            t_lo = first[0]
            if not t_lo < b:
                return _result(run_id, key, None, _UNDEF, "high edge not found")
            second = crossings(wave, l_hi, slope, None, t_lo, b)
            # crossings() with a == t_lo: first segment at t_lo re-crosses
            # only if the signal returns to the level; the t_lo crossing
            # itself belongs to the earlier segment (attribution rule), so
            # it is not double counted.
            if not second:
                return _result(run_id, key, None, _UNDEF, "high edge not found")
            val = second[0] - t_lo
        recorded = f"auto[{lo_v},{hi_v}]" if auto_levels else ""
        return _result(run_id, key, _scalar(val, TIME, "s", source), _OK, recorded)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))


def measure_overshoot(run_id, key, wave, v_initial=None, v_final=None,
                      window=None, source=""):
    """(max - v_final)/(v_final - v_initial) rising (mirrored falling);
    clipped at 0 from below (no overshoot = 0, a true zero)."""
    try:
        a, b = _window_of(wave, window)
        lo, hi = wave_min_max(wave, a, b)
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    from .waveform import interpolate
    vi = interpolate(wave, a) if v_initial is None else v_initial
    vf = interpolate(wave, b) if v_final is None else v_final
    with lab_context():
        swing = vf - vi
        if swing == 0:
            return _result(run_id, key, None, _UNDEF, "zero swing")
        if swing > 0:
            ratio = (hi - vf) / swing
        else:
            ratio = (vf - lo) / (vi - vf)
        if ratio < 0:
            ratio = _ZERO
    recorded = ""
    if v_initial is None or v_final is None:
        recorded = f"defaults v_initial={vi} v_final={vf}"
    return _result(run_id, key, _scalar(ratio, DIMENSIONLESS, "%", source), _OK, recorded)


def measure_settling(run_id, key, wave, v_final=None, tol=None,
                     abs_band=None, v_initial=None, window=None, source=""):
    """Earliest ``t_s`` with ``|x - v_final| <= band`` for all ``t`` in
    ``[t_s, b]``; result ``t_s - a``. In band on all of W gives ``a``
    (result 0); out of band at ``b`` is UNDEFINED."""
    from .waveform import interpolate
    if (tol is None) == (abs_band is None):
        return _result(run_id, key, None, _INVALID,
                       "settling needs exactly one of tol / abs_band")
    try:
        a, b = _window_of(wave, window)
        vf = interpolate(wave, b) if v_final is None else v_final
        with lab_context():
            if tol is not None:
                if not tol > 0:
                    return _result(run_id, key, None, _INVALID, "tol must be > 0")
                vi = interpolate(wave, a) if v_initial is None else v_initial
                band = tol * abs(vf - vi)
            else:
                if not abs_band > 0:
                    return _result(run_id, key, None, _INVALID, "abs_band must be > 0")
                band = abs_band
        exits = band_exit_times(wave, vf, band, a, b)
        with lab_context():
            if abs(interpolate(wave, b) - vf) > band:
                return _result(run_id, key, None, _UNDEF,
                               "not settled inside window")
            if not exits:
                val = _ZERO
            else:
                val = max(exits) - a
    except ValueError as exc:
        return _result(run_id, key, None, _INVALID, str(exc))
    recorded = ""
    if v_final is None:
        recorded = f"default v_final={vf}"
    return _result(run_id, key, _scalar(val, TIME, "s", source), _OK, recorded)


def measure_ac(run_id, key, kind, phasor, frequency_hz, source=""):
    """ac_gain / ac_gain_db / ac_phase on a peak phasor
    ``H`` (``e^{+jwt}`` engine convention). Uses the certified F8-J/F8-D6
    helpers; ``H = 0`` is UNDEFINED."""
    from academic_core.domain.engineering.ac.bode import magnitude_db
    from academic_core.domain.engineering.ac.phasors import magnitude, phase
    from .model import lab_context as _lc
    if phasor is None:
        return _result(run_id, key, None, _NO_DATA, "no phasor payload")
    with _lc():
        mag = magnitude(phasor)
        if mag == 0:
            return _result(run_id, key, None, _UNDEF, "H = 0")
        if kind == MeasurementKind.AC_GAIN.value:
            return _result(run_id, key, _scalar(mag, DIMENSIONLESS, "1", source), _OK)
        if kind == MeasurementKind.AC_GAIN_DB.value:
            mres = magnitude_db(mag)
            if mres.value is None:
                return _result(run_id, key, None, _UNDEF, "zero magnitude")
            return _result(run_id, key,
                           _scalar(mres.value, DIMENSIONLESS, "dB", source), _OK)
        if kind == MeasurementKind.AC_PHASE.value:
            return _result(run_id, key,
                           _scalar(phase(phasor), DIMENSIONLESS, "rad", source), _OK)
    return _result(run_id, key, None, _INVALID, f"not an AC phasor measurement: {kind}")


def measure_ac_amplitude(run_id, key, phasor, basis, dimension, unit_label, source=""):
    """Peak (``|X|``) or RMS (``peak/sqrt(2)``); ``basis`` required."""
    from academic_core.domain.engineering.ac.phasors import magnitude, rms_from_peak
    from .model import lab_context as _lc
    if basis is None:
        return _result(run_id, key, None, _INVALID, "ac_amplitude needs basis='peak'|'rms'")
    if basis not in ("peak", "rms"):
        return _result(run_id, key, None, _INVALID, "basis must be 'peak' or 'rms'")
    if phasor is None:
        return _result(run_id, key, None, _NO_DATA, "no phasor payload")
    with _lc():
        mag = magnitude(phasor)
        val = mag if basis == "peak" else rms_from_peak(mag)
    return _result(run_id, key, _scalar(val, dimension, unit_label, source), _OK)


def measure_bandwidth(run_id, key, bode_data, source=""):
    """Certified Bode interval only (never a single interpolated number);
    unestablished is UNDEFINED."""
    if bode_data is None or bode_data.bandwidth_lo_hz is None \
            or bode_data.bandwidth_hi_hz is None:
        return _result(run_id, key, None, _UNDEF, "bandwidth not established")
    with lab_context():
        val = bode_data.bandwidth_hi_hz - bode_data.bandwidth_lo_hz
    return _result(run_id, key, _scalar(val, FREQUENCY, "Hz", source), _OK,
                   f"interval [{bode_data.bandwidth_lo_hz},{bode_data.bandwidth_hi_hz}]")


def measure_dc_value(run_id, key, scalar):
    if scalar is None:
        return _result(run_id, key, None, _NO_DATA, "no DC payload")
    return _result(run_id, key, scalar, _OK)
