"""F8-N Virtual Laboratory — stimuli (typed configuration of existing waves).

``StimulusSpec`` is translated into the existing ``parameters["wave"]``
dict / ``value`` / AC phase parameters of a V or I source in the run
copy; the certified ``_wave_value`` implementation is the only waveform
generator. No waveform code of its own.
"""
from decimal import Decimal

from academic_core.domain.engineering.circuit import Component
from academic_core.domain.engineering.units import Quantity

from .model import (
    INVALID_STIMULUS,
    LabConfigError,
    StimulusKind,
    StimulusSpec,
    lab_context,
)

_ZERO = Decimal(0)


def _need_quantity(name, val, exemplar=None):
    if val is None:
        raise LabConfigError(INVALID_STIMULUS, f"function_generator: {name} is required")
    if not isinstance(val, Quantity):
        raise LabConfigError(INVALID_STIMULUS, f"function_generator: {name} must be a Quantity")
    if exemplar is not None and val.dimension != exemplar.dimension:
        raise LabConfigError(INVALID_STIMULUS,
                             f"function_generator: {name} dimension mismatch")
    return val


def _opt_decimal(name, val, default):
    if val is None:
        return default
    if isinstance(val, bool) or not isinstance(val, Decimal) or not val.is_finite():
        raise LabConfigError(INVALID_STIMULUS, f"function_generator: {name} must be finite Decimal")
    return val


def function_generator(source_ref, waveform, *, amplitude=None, offset=None,
                       frequency=None, phase_lag=None, duty=None,
                       delay=None, rise=None, fall=None):
    """Pure factory: user-level waveform description -> StimulusSpec.

    * ``sine``: ``va = amplitude``, ``vo = offset``, ``freq = frequency``,
      ``td = delay + phase_lag_deg / (360 * frequency)`` (only lag >= 0
      representable since ``td >= 0``; a phase lead is a config error).
      "Delay" is a time *shift*, not a hold.
    * ``pulse``/``square``: ``v1 = offset``, ``v2 = offset + amplitude``,
      ``period = 1 / frequency``, ``td = delay``, ``tr = rise``,
      ``tf = fall``, ``width = duty * period - (tr + tf) / 2`` where duty
      in (0, 1) is defined at the 50 % amplitude crossings;
      ``width < 0`` is a config error.
    * ``dc``: ``value = offset``.
    Triangle / noise / arbitrary waves: out of scope (no certified
    generator).
    """
    if not isinstance(source_ref, str) or not source_ref:
        raise LabConfigError(INVALID_STIMULUS, "source_ref must be a non-empty string")
    wave = str(waveform).strip().lower()
    if wave == "sine":
        amplitude = _need_quantity("amplitude", amplitude)
        offset = _need_quantity("offset", offset, amplitude)
        if frequency is None:
            raise LabConfigError(INVALID_STIMULUS, "function_generator: frequency is required")
        if isinstance(frequency, bool) or not isinstance(frequency, Decimal) \
                or not frequency.is_finite() or not frequency > 0:
            raise LabConfigError(INVALID_STIMULUS, "function_generator: frequency must be > 0")
        lag = _opt_decimal("phase_lag", phase_lag, _ZERO)
        if lag < 0:
            raise LabConfigError(INVALID_STIMULUS,
                                 "function_generator: phase lead not representable "
                                 "(certified sine has td >= 0 and no phase parameter)")
        dly = _opt_decimal("delay", delay, _ZERO)
        if dly < 0:
            raise LabConfigError(INVALID_STIMULUS, "function_generator: delay must be >= 0")
        with lab_context():
            td = dly + lag / (Decimal(360) * frequency)
        return StimulusSpec(source_ref, StimulusKind.SINE.value,
                            vo=offset, va=amplitude, freq=frequency, td=td)
    if wave in ("pulse", "square"):
        amplitude = _need_quantity("amplitude", amplitude)
        offset = _need_quantity("offset", offset, amplitude)
        if frequency is None:
            raise LabConfigError(INVALID_STIMULUS, "function_generator: frequency is required")
        if isinstance(frequency, bool) or not isinstance(frequency, Decimal) \
                or not frequency.is_finite() or not frequency > 0:
            raise LabConfigError(INVALID_STIMULUS, "function_generator: frequency must be > 0")
        if wave == "square":
            if duty is not None and duty != Decimal("0.5"):
                raise LabConfigError(INVALID_STIMULUS,
                                     "function_generator: square fixes duty at 0.5")
            duty_val = Decimal("0.5")
        else:
            if duty is None:
                raise LabConfigError(INVALID_STIMULUS,
                                     "function_generator: pulse needs duty in (0, 1)")
            if isinstance(duty, bool) or not isinstance(duty, Decimal):
                raise LabConfigError(INVALID_STIMULUS, "function_generator: duty must be Decimal")
            duty_val = duty
        with lab_context():
            if not _ZERO < duty_val < Decimal(1):
                raise LabConfigError(INVALID_STIMULUS,
                                     "function_generator: duty must be in (0, 1)")
            dly = _opt_decimal("delay", delay, _ZERO)
            tr = _opt_decimal("rise", rise, _ZERO)
            tf = _opt_decimal("fall", fall, _ZERO)
            if dly < 0 or tr < 0 or tf < 0:
                raise LabConfigError(INVALID_STIMULUS,
                                     "function_generator: delay/rise/fall must be >= 0")
            period = Decimal(1) / frequency
            width = duty_val * period - (tr + tf) / Decimal(2)
            if width < 0:
                raise LabConfigError(INVALID_STIMULUS,
                                     "function_generator: duty too small for rise+fall "
                                     "(width < 0)")
            v2 = offset + amplitude
        return StimulusSpec(source_ref, StimulusKind.PULSE.value,
                            v1=offset, v2=v2, td=dly, tr=tr, tf=tf,
                            width=width, period=period)
    if wave == "dc":
        offset = _need_quantity("offset", offset)
        for name, val in (("amplitude", amplitude), ("frequency", frequency),
                          ("phase_lag", phase_lag), ("duty", duty),
                          ("delay", delay), ("rise", rise), ("fall", fall)):
            if val is not None:
                raise LabConfigError(INVALID_STIMULUS,
                                     f"function_generator: dc takes only offset (got {name})")
        return StimulusSpec(source_ref, StimulusKind.DC.value, value=offset)
    raise LabConfigError(INVALID_STIMULUS,
                         f"function_generator: unknown waveform {waveform!r} "
                         "(sine | pulse | square | dc)")


def stimulus_wave_dict(stim):
    """Certified ``parameters["wave"]`` dict for a time-domain stimulus."""
    kind = StimulusKind(stim.kind)
    if kind == StimulusKind.STEP:
        return {"type": "step", "v1": stim.v1, "v2": stim.v2, "t0": stim.t0}
    if kind == StimulusKind.PULSE:
        return {"type": "pulse", "v1": stim.v1, "v2": stim.v2, "td": stim.td,
                "tr": stim.tr, "tf": stim.tf, "width": stim.width,
                "period": stim.period}
    if kind == StimulusKind.SINE:
        return {"type": "sine", "vo": stim.vo, "va": stim.va,
                "freq": stim.freq, "td": stim.td}
    raise LabConfigError(INVALID_STIMULUS, f"no wave dict for {stim.kind}")


def apply_stimuli(circuit, stimuli):
    """Return a new circuit with stimuli applied (never mutates input).

    DC replaces ``Component.value``; STEP/PULSE/SINE set
    ``parameters["wave"]``; AC sets ``ac_mag``/``ac_phase``/``phase_unit``.
    Stimulus Quantities are normalized to base display units (same rule
    as the execution snapshot). Raises ``LabConfigError`` when a source
    is missing or not V/I.
    """
    from .serialize import base_quantity
    comps = list(circuit.components)
    by_ref = {c.ref.upper(): i for i, c in enumerate(comps)}
    for stim in stimuli:
        key = stim.source_ref.upper()
        if key not in by_ref:
            raise LabConfigError(INVALID_STIMULUS,
                                 f"stimulus source {stim.source_ref!r} not in circuit")
        comp = comps[by_ref[key]]
        if comp.type.upper() not in ("V", "I"):
            raise LabConfigError(INVALID_STIMULUS,
                                 f"stimulus on non-V/I source {comp.ref!r}")
        kind = StimulusKind(stim.kind)
        params = dict(comp.parameters or {})
        value = comp.value
        if kind == StimulusKind.DC:
            value = base_quantity(stim.value)
            params.pop("wave", None)
        elif kind in (StimulusKind.STEP, StimulusKind.PULSE, StimulusKind.SINE):
            wave = stimulus_wave_dict(stim)
            for lkey in ("v1", "v2", "vo", "va"):
                if lkey in wave:
                    wave[lkey] = base_quantity(wave[lkey])
            params["wave"] = wave
        elif kind == StimulusKind.AC:
            params["ac_mag"] = base_quantity(stim.magnitude)
            params["ac_phase"] = stim.phase
            params["phase_unit"] = stim.phase_unit
        comps[by_ref[key]] = Component(comp.ref, comp.type, value,
                                       dict(comp.pins), params, dict(comp.metadata))
    from academic_core.domain.engineering.circuit import Circuit
    out = Circuit(name=circuit.name)
    for comp in comps:
        out.add(comp)
    return out
