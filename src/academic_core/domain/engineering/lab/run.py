"""F8-N Virtual Laboratory — run dispatch (orchestration only).

Each run is exactly one call (or the documented composition) of a
certified entry point. The lab never re-implements Newton, MNA,
transient, AC, sweep, sensitivity or Monte Carlo. Instruments and
measurements are pure functions of the run result; they cannot trigger
solves.
"""
import dataclasses
from decimal import Decimal

from academic_core.domain.engineering.ac.bode import analyze_bode
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    frequency_response,
    voltage_between,
)
from academic_core.domain.engineering.ac.small_signal import solve_small_signal_ac
from academic_core.domain.engineering.mna.analysis import (
    dc_equivalent,
    circuit_digest,
    solve_dc_sweep,
    solve_param_sweep,
    solve_point,
    solve_worst_case,
    substitute,
    run_monte_carlo_native,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.nonlinear import (
    ATOL as Q1_ATOL,
    MAX_BACKTRACK as Q1_MAX_BACKTRACK,
    MAX_ITER as Q1_MAX_ITER,
    RTOL as Q1_RTOL,
    STOL as Q1_STOL,
)
from academic_core.domain.engineering.mna.sensitivity import (
    solve_ac_sensitivity,
    solve_dc_sensitivity,
)
from academic_core.domain.engineering.mna.transient import solve_transient
from academic_core.domain.engineering.units import UnitError

from . import instruments as _inst
from . import measure as _measure
from .model import (
    CURRENT,
    DIMENSIONLESS,
    VOLTAGE,
    AnalysisKind,
    ComplexScalar,
    CurrentProbe,
    InstrumentKind,
    InstrumentStatus,
    LabConfigError,
    MeasurementKind,
    MeasurementResult,
    MeasurementStatus,
    ParameterProbe,
    Run,
    RunStatus,
    Scalar,
    StimulusKind,
    VoltageProbe,
    WAVE_IGNORING_ANALYSES,
    deepcopy_circuit,
    lab_context,
)
from .serialize import experiment_core_digest, experiment_digest, run_digest
from .stimulus import apply_stimuli

_ZERO = Decimal(0)

ENGINE_VERSIONS = {
    "f8h-nonlinear": "f8h-nonlinear/1.0",
    "f8l-transient": "f8l-transient/1.0",
    "f8m-analysis": "f8m-analysis/1.0",
    "f8j-small-signal-ac": "f8j-small-signal-ac/1.0",
    "f8d-ac-response": "f8d-ac-response/1.0",
    "f8d-ac-bode": "f8d-ac-bode/1.0",
}

_CONFIG_ERRORS = (InvalidCircuitError, MissingReferenceError,
                  FloatingCircuitError, CircularControlError,
                  DimensionalityError, UnitError)


@dataclasses.dataclass(frozen=True)
class ACSweepResult:
    """Wrapped AC sweep pair (both certified objects, unchanged)."""

    sweep: object
    bode: object

    def to_dict(self):
        return {"sweep": self.sweep.to_dict(), "bode": self.bode.to_dict()}


def map_engine_status(engine_status_value):
    """Certified verdict -> RunStatus (engine_status kept verbatim)."""
    s = str(engine_status_value)
    if s in ("converged", "completed", "solved"):
        return RunStatus.COMPLETED.value
    if s in ("completed_with_point_failures", "completed_with_failures"):
        return RunStatus.COMPLETED_WITH_FAILURES.value
    if s == "invalid":
        return RunStatus.INVALID_CIRCUIT.value
    if s == "unsupported":
        return RunStatus.UNSUPPORTED.value
    return RunStatus.SOLVER_FAILURE.value


def working_circuit(session_circuit, definition):
    """The transactional execution snapshot of one experiment (pure).

    Clone -> normalize display units -> apply overrides/stimuli. Shared by
    :func:`execute_run` and by E0.3 explanations, which re-observe a run on
    exactly the circuit it executed. Raises the same errors as the run.
    """
    from .serialize import normalize_circuit
    working = normalize_circuit(deepcopy_circuit(session_circuit))
    if definition.overrides:
        working = substitute(working, {addr: val for addr, val in
                                       definition.overrides})
    if definition.stimuli:
        working = apply_stimuli(working, definition.stimuli)
    return working


def execute_run(session_circuit, definition, experiment_id, run_index,
                session_id):
    """Build the immutable execution snapshot and run one analysis.

    Returns ``(Run, result_payload)`` where payload is the engine
    ``to_dict()`` for serialization. Failed runs are appended as failed
    runs (status set, definition intact); unexpected exceptions
    propagate loudly (never masked as solver failures).
    """
    exp_digest = experiment_digest(definition, session_circuit)
    core_digest = experiment_core_digest(definition, session_circuit)
    run_id = f"{experiment_id}#{run_index}"
    diagnostics = []
    analysis = definition.analysis
    kind = analysis.kind

    # Transactional snapshot: clone -> normalize display units -> apply
    # overrides/stimuli -> execute. Normalization is required because
    # engine digests are display-unit sensitive while lab documents keep
    # base units only (round trips must stay bit-identical).
    try:
        working = working_circuit(session_circuit, definition)
    except LabConfigError as exc:
        return _failed_run(run_id, experiment_id, session_id, exp_digest,
                           core_digest, kind, definition.seed, RunStatus.INVALID_CONFIGURATION.value,
                           None, None, (f"snapshot failed: {exc.message}",),
                           definition, session_circuit)
    except _CONFIG_ERRORS as exc:
        return _failed_run(run_id, experiment_id, session_id, exp_digest,
                           core_digest, kind, definition.seed, RunStatus.INVALID_CIRCUIT.value,
                           "invalid", None, (f"snapshot failed: {exc}",),
                           definition, session_circuit)

    wave_stimuli = [s for s in definition.stimuli
                    if StimulusKind(s.kind) in (StimulusKind.STEP, StimulusKind.PULSE,
                                                StimulusKind.SINE)]
    if wave_stimuli and kind in {a.value for a in WAVE_IGNORING_ANALYSES}:
        diagnostics.append("stimulus_ignored_by_analysis: time-domain waves use "
                           "the DC value only on " + kind)

    try:
        dispatched = _dispatch(kind, analysis, working, definition)
    except UnsupportedElementError as exc:
        return _failed_run(run_id, experiment_id, session_id, exp_digest,
                           core_digest, kind, definition.seed, RunStatus.UNSUPPORTED.value,
                           "unsupported", None, (str(exc),) + tuple(diagnostics),
                           definition, working)
    except _CONFIG_ERRORS as exc:
        code = RunStatus.INVALID_CIRCUIT.value
        return _failed_run(run_id, experiment_id, session_id, exp_digest,
                           core_digest, kind, definition.seed, code, "invalid",
                           None, (str(exc),) + tuple(diagnostics),
                           definition, working)
    result, engine_result, engine_status, newton_state = dispatched
    from .serialize import stable_result_payload
    if engine_result is None:
        payload = {}
    elif isinstance(engine_result, dict):
        payload = engine_result
    else:
        payload = stable_result_payload(engine_result)
    status = map_engine_status(engine_status) if engine_status is not None else \
        RunStatus.UNSUPPORTED.value

    if status in (RunStatus.INVALID_CIRCUIT.value, RunStatus.UNSUPPORTED.value,
                  RunStatus.SOLVER_FAILURE.value) or result is None:
        return _failed_run(run_id, experiment_id, session_id, exp_digest,
                           core_digest, kind, definition.seed, status, engine_status, result,
                           tuple(diagnostics), definition, working,
                           payload=payload)

    readings = _compute_readings(run_id, definition, kind, analysis, working,
                                 result, newton_state)
    measurements = _compute_measurements(run_id, definition, kind, working,
                                         result, readings)
    provenance = _provenance(definition, exp_digest, kind, analysis, working,
                             result, engine_status, payload)
    result_digest_str = run_digest(core_digest, status, engine_status, payload,
                                   measurements)
    # Provenance carries the digest as a record (the digest itself covers
    # experiment + status + result + measurements, never provenance).
    provenance["result_digest"] = result_digest_str
    run = Run(run_id, experiment_id, session_id, exp_digest, kind,
              definition.seed, status, engine_status, result,
              tuple(measurements), tuple(readings), tuple(diagnostics),
              provenance, result_digest_str)
    return run, payload


def _failed_run(run_id, experiment_id, session_id, exp_digest, core_digest,
                kind, seed, status, engine_status, result, diagnostics,
                definition, working, payload=None):
    measurements = _compute_measurements(run_id, definition, kind, working,
                                         None, ())
    provenance = _provenance(definition, exp_digest, kind, definition.analysis,
                             working, result, engine_status, payload or {})
    result_digest_str = run_digest(core_digest, status, engine_status,
                                   payload or {}, measurements)
    provenance["result_digest"] = result_digest_str
    run = Run(run_id, experiment_id, session_id, exp_digest, kind, seed,
              status, engine_status, result, tuple(measurements), (),
              tuple(diagnostics), provenance, result_digest_str)
    return run, payload or {}


def _dispatch(kind, analysis, working, definition):
    """One certified engine call. Returns
    ``(result, payload, engine_status, newton_state)``.

    The payload is the live certified result object (exact numerics);
    serialization canonicalizes it directly. Engine ``to_dict()``
    presentation formatting is ambient-context sensitive and is never
    part of any digest (test N-090).
    """
    if kind == AnalysisKind.OP.value:
        result, state = solve_point(working)
        return result, result, result.status.value, state
    if kind == AnalysisKind.DC_SWEEP.value:
        result = solve_dc_sweep(working, analysis.sweep)
        return result, result, result.status.value, None
    if kind == AnalysisKind.PARAM_SWEEP.value:
        result = solve_param_sweep(working, analysis.param_sweep)
        return result, result, result.status.value, None
    if kind == AnalysisKind.CORNERS.value:
        result = solve_worst_case(working, analysis.corners)
        return result, result, result.status.value, None
    if kind == AnalysisKind.SENS_DC.value:
        result = solve_dc_sensitivity(working, analysis.sens)
        return result, result, result.status.value, None
    if kind == AnalysisKind.SENS_AC.value:
        result = solve_ac_sensitivity(working, analysis.sens_ac)
        return result, result, result.status.value, None
    if kind == AnalysisKind.MONTE_CARLO.value:
        config = dataclasses.replace(analysis.mc, seed=definition.seed)
        result = run_monte_carlo_native(working, config)
        return result, result, result.status.value, None
    if kind == AnalysisKind.AC_POINT.value:
        result = solve_small_signal_ac(working, analysis.frequency)
        return result, result, result.status.value, None
    if kind == AnalysisKind.AC_SWEEP.value:
        return _dispatch_ac_sweep(analysis, working)
    if kind == AnalysisKind.TRANSIENT.value:
        result = solve_transient(working, analysis.transient)
        return result, result, result.status.value, None
    raise LabConfigError("INVALID_ANALYSIS", f"unknown analysis {kind!r}")


def _dispatch_ac_sweep(analysis, working):
    from .model import NONLINEAR_TYPES
    present = {c.type.upper() for c in working.components}
    if present & NONLINEAR_TYPES:
        # No nonlinear AC sweep engine (audit finding 7): honest
        # UNSUPPORTED without solving.
        return None, {"unsupported": "nonlinear circuit has no AC sweep engine"}, \
            "unsupported", None
    comps = {c.ref.upper(): c for c in working.components}
    src = comps.get(analysis.input_source.upper())
    if src is None or src.type.upper() not in ("V", "I"):
        raise InvalidCircuitError(
            f"AC sweep input source {analysis.input_source!r} must be a V/I source")
    pins = src.pins
    plus = pins.get("+", pins.get("1", ""))
    minus = pins.get("-", pins.get("2", ""))
    definition = ResponseDefinition(
        "transfer", (voltage_between(plus, minus),
                     voltage_between(analysis.output_p, analysis.output_n),
                     src.ref))
    sweep = frequency_response(working, definition, list(analysis.frequencies))
    bode = analyze_bode(sweep, analysis.db_threshold)
    wrapped = ACSweepResult(sweep, bode)
    status = sweep.status if isinstance(sweep.status, str) else sweep.status.value
    return wrapped, wrapped.to_dict(), status, None


# ---------------------------------------------------------------------------
# Readings + measurements (pure views)
# ---------------------------------------------------------------------------

def _probe_lookup(definition):
    return {k: v for k, v in definition.probes}


def _probe_kind(probe):
    if isinstance(probe, VoltageProbe):
        return "V"
    if isinstance(probe, CurrentProbe):
        return "I"
    if isinstance(probe, ParameterProbe):
        return "P"
    return "?"


def _compute_readings(run_id, definition, kind, analysis, working, result,
                      newton_state):
    probes = _probe_lookup(definition)
    readings = []
    for key, spec in definition.instruments:
        probe = probes.get(spec.probe) if spec.probe else None
        kind_tag = spec.kind
        if kind_tag in (InstrumentKind.VOLTMETER.value, InstrumentKind.AMMETER.value):
            readings.append(_read_meter(key, spec, probe, kind, analysis, working,
                                        result, newton_state))
        elif kind_tag == InstrumentKind.OSCILLOSCOPE.value:
            readings.append(_read_scope(key, spec, definition, working, result))
        elif kind_tag == InstrumentKind.FREQUENCY_RESPONSE.value:
            readings.append(_read_fr(key, analysis, result))
        elif kind_tag == InstrumentKind.SWEEP_VIEWER.value:
            readings.append(_read_sweep_viewer(key, spec, probe, kind, analysis,
                                               working, result))
    return readings


def _read_meter(key, spec, probe, kind, analysis, working, result,
                newton_state):
    is_volt = spec.kind == InstrumentKind.VOLTMETER.value
    if probe is None:
        return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                              "unknown probe key")
    if is_volt and not isinstance(probe, VoltageProbe):
        return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                              "voltmeter needs a VoltageProbe")
    if not is_volt and not isinstance(probe, CurrentProbe):
        return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                              "ammeter needs a CurrentProbe")
    source = f"{key}:{spec.probe}"
    if kind == AnalysisKind.OP.value:
        if is_volt:
            val, reason = _inst.voltage_op(probe, _inst.op_voltage_map(result))
            if val is None:
                return _inst._reading(key, spec.kind, InstrumentStatus.NO_DATA.value,
                                      reason)
            return _inst.evaluate_meter(key, spec, val, VOLTAGE, "V", source)
        bmap = _inst.op_branch_map(result)
        val, reason = _inst.current_op(probe, working, result, bmap, newton_state)
        if val is None:
            code = InstrumentStatus.UNSUPPORTED.value \
                if "not offered" in reason or "unavailable" in reason \
                else InstrumentStatus.NO_DATA.value
            return _inst._reading(key, spec.kind, code, reason)
        return _inst.evaluate_meter(key, spec, val, CURRENT, "A", source)
    if kind == AnalysisKind.DC_SWEEP.value:
        from .serialize import canonical_analysis
        config = canonical_analysis(analysis)["config"]
        target = config["target"]
        target_key = target if isinstance(target, str) else \
            target["ref"] + "." + target["field"]
        axis = []
        values = []
        statuses = []
        for p in result.points:
            status = _inst._status_str(p.status)
            params = dict(p.parameters)
            axis.append(params.get(target_key))
            statuses.append(f"{p.index}:{status}")
            if status != "converged":
                values.append(None)
                continue
            if is_volt:
                val, _ = _inst.voltage_point(probe, p)
            else:
                val, _ = _inst.current_point(probe, working, working, p)
            values.append(val)
        from .model import SweepTrace
        data = SweepTrace(tuple(axis), tuple(values), target_key,
                          VOLTAGE if is_volt else CURRENT,
                          "V" if is_volt else "A", source, tuple(statuses))
        return _inst._reading(key, spec.kind, InstrumentStatus.OK.value, "", data)
    if kind == AnalysisKind.AC_POINT.value:
        freq_hz = analysis.frequency.to_base()
        if is_volt:
            phasor, reason = _inst.voltage_phasor(probe, result)
            dim, label = VOLTAGE, "V"
        else:
            phasor, reason = _inst.current_phasor(probe, result)
            dim, label = CURRENT, "A"
        if phasor is None:
            return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                                  reason)
        data = ComplexScalar(phasor, dim, label, freq_hz, source)
        return _inst._reading(key, spec.kind, InstrumentStatus.OK.value, "", data)
    if kind == AnalysisKind.TRANSIENT.value:
        if is_volt:
            wave, reason = _inst.voltage_waveform(probe, working, result, source)
            dim, label = VOLTAGE, "V"
        else:
            wave, reason = _inst.current_waveform(probe, working, result, source)
            dim, label = CURRENT, "A"
        if wave is None:
            return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                                  reason)
        t_bounds = (result.times[0], result.times[-1])
        return _inst.evaluate_transient_meter(key, spec, wave, spec.at,
                                              t_bounds, dim, label, source)
    return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                          "meter not applicable to " + kind)


def _read_scope(key, spec, definition, working, result):
    probes = _probe_lookup(definition)
    channel_waves = {}
    for ch in spec.channels:
        probe = probes.get(ch.probe_key)
        if probe is None:
            channel_waves[ch.probe_key] = None
            continue
        if isinstance(probe, VoltageProbe):
            wave, _ = _inst.voltage_waveform(probe, working, result,
                                             f"{key}:{ch.probe_key}")
            channel_waves[ch.probe_key] = wave
        elif isinstance(probe, CurrentProbe):
            wave, reason = _inst.current_waveform(probe, working, result,
                                                  f"{key}:{ch.probe_key}")
            channel_waves[ch.probe_key] = wave if wave is not None else (None, reason)
        else:
            channel_waves[ch.probe_key] = (None, "scope needs V/I probes")
    t_bounds = (result.times[0], result.times[-1])
    return _inst.evaluate_scope(key, spec, channel_waves, t_bounds)


def _read_fr(key, analysis, result):
    return _inst.evaluate_fr_viewer(key, result.sweep, result.bode,
                                    analysis.db_threshold, key)


def _read_sweep_viewer(key, spec, probe, kind, analysis, working, result):
    if probe is None:
        return _inst._reading(key, spec.kind, InstrumentStatus.UNSUPPORTED.value,
                              "unknown probe key")
    config = {"DC_SWEEP": analysis.sweep, "PARAM_SWEEP": analysis.param_sweep,
              "CORNERS": analysis.corners, "MONTE_CARLO": analysis.mc,
              "SENS_DC": analysis.sens, "SENS_AC": analysis.sens_ac}.get(kind)
    return _inst.evaluate_sweep_viewer(key, probe, _probe_kind(probe), kind,
                                       result, config, working, working,
                                       f"{key}:{spec.probe}")


# ---------------------------------------------------------------------------
# Measurements (pure functions of run state; never feed back)
# ---------------------------------------------------------------------------

def _compute_measurements(run_id, definition, kind, working, result, readings):
    probes = _probe_lookup(definition)
    BodeDataLocal = None
    if kind == AnalysisKind.AC_SWEEP.value and result is not None:
        fr = _inst.evaluate_fr_viewer("__bw__", result.sweep, result.bode,
                                      definition.analysis.db_threshold, "")
        BodeDataLocal = fr.data
    out = []
    for key, mspec in definition.measurements:
        probe = probes.get(mspec.probe)
        if probe is None:
            out.append(MeasurementResult(run_id, key, None,
                                         MeasurementStatus.NO_DATA.value,
                                         "unknown probe key"))
            continue
        out.append(_compute_one(run_id, key, mspec, probe, kind, working,
                                result, BodeDataLocal))
    return out


def _compute_one(run_id, key, mspec, probe, kind, working, result, bode_data):
    mkind = mspec.kind
    source = f"{key}:{mspec.probe}"
    if result is None:
        return MeasurementResult(run_id, key, None,
                                 MeasurementStatus.NO_DATA.value,
                                 "run has no usable payload")
    if mkind in {m.value for m in (MeasurementKind.MAX, MeasurementKind.MIN,
                                   MeasurementKind.PP, MeasurementKind.MEAN,
                                   MeasurementKind.RMS, MeasurementKind.CROSSINGS,
                                   MeasurementKind.PERIOD, MeasurementKind.FREQUENCY,
                                   MeasurementKind.RISE_TIME, MeasurementKind.FALL_TIME,
                                   MeasurementKind.OVERSHOOT, MeasurementKind.SETTLING_TIME)}:
        wave, reason = _measure_waveform(probe, working, result, source)
        if wave is None:
            return MeasurementResult(run_id, key, None,
                                     MeasurementStatus.NO_DATA.value, reason)
        window = tuple(mspec.window) if mspec.window is not None else None
        if mkind in (MeasurementKind.MAX.value, MeasurementKind.MIN.value,
                     MeasurementKind.PP.value):
            return _measure.measure_max_min_pp(run_id, key, wave, mkind,
                                               window, source)
        if mkind == MeasurementKind.MEAN.value:
            return _measure.measure_mean(run_id, key, wave, window, source)
        if mkind == MeasurementKind.RMS.value:
            return _measure.measure_rms(run_id, key, wave, window, source)
        if mkind == MeasurementKind.CROSSINGS.value:
            return _measure.measure_crossings(run_id, key, wave, mspec.level,
                                              mspec.slope or "rising",
                                              mspec.hysteresis, window, source)
        if mkind in (MeasurementKind.PERIOD.value, MeasurementKind.FREQUENCY.value):
            return _measure.measure_period_frequency(run_id, key, wave, mkind,
                                                     mspec.level,
                                                     mspec.hysteresis, window,
                                                     source)
        if mkind in (MeasurementKind.RISE_TIME.value, MeasurementKind.FALL_TIME.value):
            return _measure.measure_rise_fall(run_id, key, wave, mkind,
                                              mspec.low_frac, mspec.high_frac,
                                              mspec.v_low, mspec.v_high,
                                              mspec.auto_levels, window, source)
        if mkind == MeasurementKind.OVERSHOOT.value:
            return _measure.measure_overshoot(run_id, key, wave, mspec.v_initial,
                                              mspec.v_final, window, source)
        if mkind == MeasurementKind.SETTLING_TIME.value:
            return _measure.measure_settling(run_id, key, wave, mspec.v_final,
                                             mspec.tol, mspec.abs_band,
                                             mspec.v_initial, window, source)
    if mkind in (MeasurementKind.AC_GAIN.value, MeasurementKind.AC_GAIN_DB.value,
                 MeasurementKind.AC_PHASE.value, MeasurementKind.AC_AMPLITUDE.value):
        return _compute_ac_measure(run_id, key, mspec, probe, working, result,
                                   source)
    if mkind == MeasurementKind.BANDWIDTH.value:
        return _measure.measure_bandwidth(run_id, key, bode_data, source)
    if mkind == MeasurementKind.DC_VALUE.value:
        if isinstance(probe, VoltageProbe):
            val, reason = _inst.voltage_op(probe, _inst.op_voltage_map(result))
            if val is None:
                return MeasurementResult(run_id, key, None,
                                         MeasurementStatus.NO_DATA.value, reason)
            return _measure.measure_dc_value(run_id, key,
                                             Scalar(val, VOLTAGE, "V", source))
        if isinstance(probe, CurrentProbe):
            bmap = _inst.op_branch_map(result)
            val, reason = _inst.current_op(probe, working, result, bmap, None)
            if val is None:
                return MeasurementResult(run_id, key, None,
                                         MeasurementStatus.NO_DATA.value, reason)
            return _measure.measure_dc_value(run_id, key,
                                             Scalar(val, CURRENT, "A", source))
        if isinstance(probe, ParameterProbe):
            try:
                scalar = _inst.evaluate_parameter_probe(working, probe, source)
            except Exception as exc:
                return MeasurementResult(run_id, key, None,
                                         MeasurementStatus.NO_DATA.value, str(exc))
            return _measure.measure_dc_value(run_id, key, scalar)
    return MeasurementResult(run_id, key, None,
                             MeasurementStatus.INVALID_MEASUREMENT.value,
                             f"measurement {mkind!r} not applicable here")


def _measure_waveform(probe, working, result, source):
    if isinstance(probe, VoltageProbe):
        return _inst.voltage_waveform(probe, working, result, source)
    if isinstance(probe, CurrentProbe):
        return _inst.current_waveform(probe, working, result, source)
    return None, "waveform measurements need a V/I probe"


def _compute_ac_measure(run_id, key, mspec, probe, working, result, source):
    mkind = mspec.kind
    if isinstance(probe, VoltageProbe):
        phasor, reason = _inst.voltage_phasor(probe, result)
        dim, label = VOLTAGE, "V"
    elif isinstance(probe, CurrentProbe):
        phasor, reason = _inst.current_phasor(probe, result)
        dim, label = CURRENT, "A"
    else:
        return MeasurementResult(run_id, key, None,
                                 MeasurementStatus.NO_DATA.value,
                                 "AC measurements need a V/I probe")
    if phasor is None:
        return MeasurementResult(run_id, key, None,
                                 MeasurementStatus.NO_DATA.value, reason)
    if mkind == MeasurementKind.AC_AMPLITUDE.value:
        return _measure.measure_ac_amplitude(run_id, key, phasor, mspec.basis,
                                             dim, label, source)
    if mkind in (MeasurementKind.AC_GAIN.value, MeasurementKind.AC_GAIN_DB.value,
                 MeasurementKind.AC_PHASE.value):
        found = _inst.ac_excitation_phasor(working)
        if found is None:
            return MeasurementResult(run_id, key, None,
                                     MeasurementStatus.UNDEFINED.value,
                                     "needs exactly one AC excitation source")
        _, src_phasor = found
        with lab_context():
            zero = src_phasor.re == 0 and src_phasor.im == 0
        if zero:
            return MeasurementResult(run_id, key, None,
                                     MeasurementStatus.UNDEFINED.value,
                                     "zero input (F8-D5 semantics)")
        with lab_context():
            h = phasor / src_phasor
        return _measure.measure_ac(run_id, key, mkind, h, _ZERO, source)
    return MeasurementResult(run_id, key, None,
                             MeasurementStatus.INVALID_MEASUREMENT.value,
                             f"unknown AC measurement {mkind!r}")


# ---------------------------------------------------------------------------
# Provenance (all deterministic; no timestamps/ids/addresses)
# ---------------------------------------------------------------------------

def _provenance(definition, exp_digest, kind, analysis, working, result,
                engine_status, payload):
    from .serialize import canonical_analysis
    prov = {
        "schema": "f8n-lab/1",
        "lab_version": "f8n-lab/1",
        "engine_versions": dict(ENGINE_VERSIONS),
        "experiment_digest": exp_digest,
        "circuit_digest": circuit_digest(working),
        "analysis": {"kind": kind, "config": canonical_analysis(analysis)},
        "parameters": [[addr.key, str(val)] for addr, val in definition.overrides],
        "stimuli": [canonical_stimulus_doc(s) for s in definition.stimuli],
        "probes": [[k, _inst_type(v)] for k, v in definition.probes],
        "instruments": [[k, v.kind] for k, v in definition.instruments],
        "measurement_specs": [[k, v.kind] for k, v in definition.measurements],
        "seed": definition.seed,
        "tolerances": {
            "Q1_RTOL": str(Q1_RTOL), "Q1_ATOL": str(Q1_ATOL),
            "Q1_STOL": str(Q1_STOL), "Q1_MAX_ITER": str(Q1_MAX_ITER),
            "Q1_MAX_BACKTRACK": str(Q1_MAX_BACKTRACK),
            "transient": _transient_tolerances(analysis),
        },
        "engine_result_digests": _engine_digests(payload),
        "engine_status": engine_status,
        "warm_start": _warm_start_info(payload),
        "dc_mapping": "C removed; L -> 0 V short; waves/IC ignored (DC value)",
        "result_digest": "",
    }
    return prov


def canonical_stimulus_doc(stim):
    from .serialize import canonical
    return canonical(stim)


def _inst_type(probe):
    return type(probe).__name__


def _transient_tolerances(analysis):
    cfg = analysis.transient
    if cfg is None:
        return None
    return {"reltol": str(cfg.reltol), "abstol": str(cfg.abstol),
            "h_min": str(cfg.h_min), "h_max": str(cfg.h_max),
            "method": cfg.method, "adaptive": bool(cfg.adaptive)}


def _engine_digests(payload):
    out = {}
    if isinstance(payload, dict):
        if payload.get("digest") is not None:
            out["digest"] = str(payload["digest"])
        prov = payload.get("provenance")
        if isinstance(prov, dict):
            for k, v in prov.items():
                if "digest" in str(k) and isinstance(v, str):
                    out[str(k)] = v
    return out


def _warm_start_info(payload):
    out = {}
    if isinstance(payload, dict):
        prov = payload.get("provenance")
        if isinstance(prov, dict):
            for k in ("n_warm_start_used", "n_fallback", "n_converged",
                      "n_failed", "iterations", "init_mode"):
                if k in prov and isinstance(prov[k], (str, int, bool)):
                    out[k] = prov[k]
    return out
