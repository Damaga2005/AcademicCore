"""F8-N Virtual Laboratory — session operations (all pure, value semantics).

Every operation returns a **new** session; failures return the
*unchanged* session plus a typed status. Nothing is half-applied. A
failed run is appended as a failed run (definition intact). No
session-level mutable state exists, so one session cannot contaminate
another.
"""
from . import instruments as _inst
from .model import (
    BUDGET_EXCEEDED,
    DUPLICATE,
    INVALID_ANALYSIS,
    INVALID_CIRCUIT,
    INVALID_CONFIGURATION,
    INVALID_MEASUREMENT_SPEC,
    INVALID_PROBE,
    INVALID_SEED,
    INVALID_STIMULUS,
    MAX_EXPERIMENTS_PER_SESSION,
    MAX_RUNS_PER_SESSION,
    SESSION_CLOSED,
    UNKNOWN_EXPERIMENT,
    UNKNOWN_RUN,
    AnalysisKind,
    AnalysisSpec,
    Annotation,
    AnnotationRecord,
    CurrentProbe,
    ExperimentDefinition,
    ExperimentRecord,
    InstrumentKind,
    InstrumentSpec,
    LabConfigError,
    LaboratorySession,
    MeasurementKind,
    MeasurementSpec,
    ParameterProbe,
    StimulusKind,
    ValidationReport,
    VoltageProbe,
    deepcopy_circuit,
)
from .serialize import experiment_digest, experiment_id

_KEEP = object()


def _require_open(session):
    if session.state != "OPEN":
        raise LabConfigError(SESSION_CLOSED, "session is CLOSED")


def create_session(session_id, circuit, metadata=()):
    """Validate the id, deep-copy the circuit, open a session."""
    from academic_core.domain.engineering.circuit import Circuit
    if not isinstance(circuit, Circuit):
        raise LabConfigError(INVALID_CIRCUIT, "circuit must be a Circuit")
    return LaboratorySession(session_id, deepcopy_circuit(circuit), (),
                             (), tuple(metadata), "OPEN")


def validate_definition(session, definition):
    """Full static validation of a definition (no solve).

    Returns a list of ``(code, message)``. Covers: override addresses
    (closed registry + domain via certified ``resolve_param`` +
    ``substitute`` dry-run), stimulus sources (V/I, known), probe
    sources, instrument applicability + references, measurement
    applicability + references + kind-specific params, sweep-config /
    probe observable coverage, AC_SWEEP input/output refs, budgets.
    """
    from academic_core.domain.engineering.mna.analysis import (
        InvalidCircuitError,
        resolve_param,
        substitute,
        validate_observable,
    )
    from academic_core.domain.engineering.mna.analysis import ObservableSpec
    errors = []
    circuit = session.circuit
    kind = definition.analysis.kind
    comps = _inst.components_by_ref(circuit)
    nets = set(circuit.nets)

    # Overrides: closed registry + domain, via the certified path, on a
    # throwaway copy (dry-run; the session circuit is never touched).
    try:
        substitute(deepcopy_circuit(circuit),
                   {addr: val for addr, val in definition.overrides})
    except InvalidCircuitError as exc:
        errors.append((INVALID_CONFIGURATION, f"override rejected: {exc}"))
    for addr, _ in definition.overrides:
        try:
            resolve_param(circuit, addr)
        except InvalidCircuitError as exc:
            errors.append((INVALID_CONFIGURATION, f"override address: {exc}"))

    # Stimuli: known V/I sources (uniqueness enforced by construction).
    for stim in definition.stimuli:
        comp = comps.get(stim.source_ref.upper())
        if comp is None:
            errors.append((INVALID_STIMULUS,
                           f"stimulus source {stim.source_ref!r} not in circuit"))
        elif comp.type.upper() not in ("V", "I"):
            errors.append((INVALID_STIMULUS,
                           f"stimulus on non-V/I source {comp.ref!r}"))

    # Probes: existence + registry.
    probes = {k: v for k, v in definition.probes}
    for key, probe in definition.probes:
        for code, msg in _inst.check_probe_source(probe, circuit):
            errors.append((code, f"probe {key!r}: {msg}"))

    # Instruments: applicability, references, sweep coverage.
    for key, spec in definition.instruments:
        if not _inst.instrument_applicable(kind, spec.kind):
            errors.append((INVALID_CONFIGURATION,
                           f"instrument {key!r} ({spec.kind}) not applicable "
                           f"to {kind}"))
            continue
        if spec.kind in (InstrumentKind.VOLTMETER.value, InstrumentKind.AMMETER.value):
            if spec.probe not in probes:
                errors.append((INVALID_PROBE,
                               f"instrument {key!r} references unknown probe "
                               f"{spec.probe!r}"))
            elif spec.kind == InstrumentKind.VOLTMETER.value and \
                    not isinstance(probes[spec.probe], VoltageProbe):
                errors.append((INVALID_PROBE,
                               f"voltmeter {key!r} needs a VoltageProbe"))
            elif spec.kind == InstrumentKind.AMMETER.value and \
                    not isinstance(probes[spec.probe], CurrentProbe):
                errors.append((INVALID_PROBE,
                               f"ammeter {key!r} needs a CurrentProbe"))
            if spec.at is not None and kind != AnalysisKind.TRANSIENT.value:
                errors.append((INVALID_CONFIGURATION,
                               f"instrument {key!r}: 'at' is transient-only"))
        elif spec.kind == InstrumentKind.OSCILLOSCOPE.value:
            for ch in spec.channels:
                if ch.probe_key not in probes:
                    errors.append((INVALID_PROBE,
                                   f"scope {key!r} references unknown probe "
                                   f"{ch.probe_key!r}"))
                elif not isinstance(probes[ch.probe_key],
                                    (VoltageProbe, CurrentProbe)):
                    errors.append((INVALID_PROBE,
                                   f"scope {key!r} channel needs a V/I probe"))
            if spec.trigger is not None and \
                    spec.trigger.source_probe_key not in probes:
                errors.append((INVALID_PROBE,
                               f"scope {key!r} trigger references unknown probe"))
        elif spec.kind == InstrumentKind.SWEEP_VIEWER.value:
            if spec.probe not in probes:
                errors.append((INVALID_PROBE,
                               f"sweep viewer {key!r} references unknown probe "
                               f"{spec.probe!r}"))

    # Measurements: applicability, references, kind-specific params.
    for key, mspec in definition.measurements:
        if not _inst.measurement_applicable(kind, mspec.kind):
            errors.append((INVALID_CONFIGURATION,
                           f"measurement {key!r} ({mspec.kind}) not applicable "
                           f"to {kind}"))
            continue
        if mspec.probe not in probes:
            errors.append((INVALID_PROBE,
                           f"measurement {key!r} references unknown probe "
                           f"{mspec.probe!r}"))
            continue
        for code, msg in _measurement_params_ok(mspec):
            errors.append((code, f"measurement {key!r}: {msg}"))

    # Sweep-config / probe observable coverage (F8-M analyses).
    if kind in (AnalysisKind.DC_SWEEP.value, AnalysisKind.PARAM_SWEEP.value,
                AnalysisKind.CORNERS.value, AnalysisKind.MONTE_CARLO.value,
                AnalysisKind.SENS_DC.value, AnalysisKind.SENS_AC.value):
        config = _sweep_config_of(definition.analysis)
        provided = {o.key for o in _config_observables(config)}
        for key, probe in definition.probes:
            if isinstance(probe, ParameterProbe):
                continue
            try:
                required = _inst.required_observable_keys(probe, circuit)
            except LabConfigError as exc:
                errors.append((exc.code, f"probe {key!r}: {exc.message}"))
                continue
            if required is None:
                continue
            missing = required - provided
            if missing:
                errors.append((INVALID_CONFIGURATION,
                               f"probe {key!r} needs observables {sorted(missing)} "
                               f"absent from the {kind} config"))
        for obs in _config_observables(config):
            try:
                validate_observable(obs, circuit)
            except InvalidCircuitError as exc:
                errors.append((INVALID_CONFIGURATION, f"observable: {exc}"))

    # AC_SWEEP refs.
    if kind == AnalysisKind.AC_SWEEP.value:
        spec = definition.analysis
        src = comps.get(spec.input_source.upper())
        if src is None or src.type.upper() not in ("V", "I"):
            errors.append((INVALID_CONFIGURATION,
                           f"AC sweep input source {spec.input_source!r} "
                           f"must be a V/I source"))
        for net in (spec.output_p, spec.output_n):
            if net not in nets:
                errors.append((INVALID_CONFIGURATION,
                               f"AC sweep output net {net!r} unknown"))
        # NOTE (N-062): a nonlinear circuit is NOT rejected here; the run
        # dispatches to an honest UNSUPPORTED (no nonlinear AC sweep
        # engine exists). Static validation only covers refs.

    # Budgets.
    if len(session.experiments) >= MAX_EXPERIMENTS_PER_SESSION:
        errors.append((BUDGET_EXCEEDED, "too many experiments in session"))
    return errors


def _measurement_params_ok(mspec):
    kind = mspec.kind
    if kind in (MeasurementKind.RISE_TIME.value, MeasurementKind.FALL_TIME.value):
        if mspec.low_frac is None or mspec.high_frac is None:
            return [(INVALID_MEASUREMENT_SPEC,
                     "rise/fall needs low_frac and high_frac (no hidden default)")]
        if not 0 < mspec.low_frac < mspec.high_frac < 1:
            return [(INVALID_MEASUREMENT_SPEC, "need 0 < low < high < 1")]
        if not mspec.auto_levels and (mspec.v_low is None or mspec.v_high is None):
            return [(INVALID_MEASUREMENT_SPEC,
                     "rise/fall needs v_low/v_high or auto_levels")]
        if mspec.auto_levels and (mspec.v_low is not None or mspec.v_high is not None):
            return [(INVALID_MEASUREMENT_SPEC,
                     "auto_levels conflicts with explicit levels")]
    if kind == MeasurementKind.SETTLING_TIME.value:
        if (mspec.tol is None) == (mspec.abs_band is None):
            return [(INVALID_MEASUREMENT_SPEC,
                     "settling needs exactly one of tol / abs_band")]
        if mspec.tol is not None and not mspec.tol > 0:
            return [(INVALID_MEASUREMENT_SPEC, "tol must be > 0")]
        if mspec.abs_band is not None and not mspec.abs_band > 0:
            return [(INVALID_MEASUREMENT_SPEC, "abs_band must be > 0")]
    if kind == MeasurementKind.AC_AMPLITUDE.value and mspec.basis is None:
        return [(INVALID_MEASUREMENT_SPEC, "ac_amplitude needs basis='peak'|'rms'")]
    if kind == MeasurementKind.CROSSINGS.value and mspec.level is None:
        return [(INVALID_MEASUREMENT_SPEC, "crossings needs a level")]
    if mspec.window is not None and not mspec.window[0] < mspec.window[1]:
        return [(INVALID_MEASUREMENT_SPEC, "window needs a < b")]
    return []


def _sweep_config_of(analysis):
    return {"DC_SWEEP": analysis.sweep, "PARAM_SWEEP": analysis.param_sweep,
            "CORNERS": analysis.corners, "MONTE_CARLO": analysis.mc,
            "SENS_DC": analysis.sens, "SENS_AC": analysis.sens_ac}[analysis.kind]


def _config_observables(config):
    return tuple(config.observables or ())


def add_experiment(session, definition):
    """Full static validation (no solve); duplicates by digest idempotent."""
    _require_open(session)
    errors = validate_definition(session, definition)
    if errors:
        return session, ValidationReport.invalid(errors)
    new_id = experiment_id(definition, session.circuit)
    for existing in session.experiments:
        if experiment_id(existing, session.circuit) == new_id:
            return session, ValidationReport.valid()
    new_session = LaboratorySession(
        session.session_id, session.circuit,
        session.experiments + (definition,), session.records,
        session.metadata, session.state, session.schema)
    return new_session, ValidationReport.valid()


def run_experiment(session, experiment_id_str):
    """Execute one experiment; append the Run (failed runs too)."""
    from .run import execute_run
    _require_open(session)
    definition = None
    for existing in session.experiments:
        if experiment_id(existing, session.circuit) == experiment_id_str:
            definition = existing
            break
    if definition is None:
        raise LabConfigError(UNKNOWN_EXPERIMENT,
                             f"unknown experiment {experiment_id_str!r}")
    total_runs = sum(len(r.runs) for r in session.records)
    if total_runs >= MAX_RUNS_PER_SESSION:
        raise LabConfigError(BUDGET_EXCEEDED, "too many runs in session")
    prior = 0
    record_index = None
    for i, record in enumerate(session.records):
        if record.experiment_id == experiment_id_str:
            prior = len(record.runs)
            record_index = i
    run, _payload = execute_run(session.circuit, definition, experiment_id_str,
                                prior + 1, session.session_id)
    if record_index is None:
        record = ExperimentRecord(experiment_id_str, (run,), ())
        records = session.records + (record,)
    else:
        old = session.records[record_index]
        record = ExperimentRecord(old.experiment_id, old.runs + (run,),
                                  old.annotations)
        records = session.records[:record_index] + (record,) + \
            session.records[record_index + 1:]
    new_session = LaboratorySession(
        session.session_id, session.circuit, session.experiments, records,
        session.metadata, session.state, session.schema)
    return new_session, run


def annotate(session, run_id, annotation):
    """Append-only annotation (never digested)."""
    _require_open(session)
    if not isinstance(annotation, Annotation):
        raise LabConfigError(INVALID_CONFIGURATION, "annotation must be Annotation")
    for i, record in enumerate(session.records):
        ids = [r.run_id for r in record.runs]
        if run_id in ids:
            entry = AnnotationRecord(run_id, len(record.annotations), annotation)
            new_record = ExperimentRecord(record.experiment_id, record.runs,
                                          record.annotations + (entry,))
            records = session.records[:i] + (new_record,) + session.records[i + 1:]
            return LaboratorySession(session.session_id, session.circuit,
                                     session.experiments, records,
                                     session.metadata, session.state,
                                     session.schema)
    raise LabConfigError(UNKNOWN_RUN, f"unknown run {run_id!r}")


def reset(session):
    """Drop runs/annotations; keep circuit and definitions."""
    _require_open(session)
    records = tuple(ExperimentRecord(r.experiment_id, (), ()) for r in session.records)
    # Keep records only for experiments that still exist (all do); empty ones
    # carry no information, so drop them for a canonical reset state.
    records = tuple(r for r in records if r.runs or r.annotations)
    return LaboratorySession(session.session_id, session.circuit,
                             session.experiments, records, session.metadata,
                             session.state, session.schema)


def clone_session(session, new_session_id):
    """Same content, new id; recorded in metadata (not digested)."""
    _require_open(session)
    metadata = tuple(sorted(session.metadata + (("cloned_from", session.session_id),)))
    return LaboratorySession(new_session_id, deepcopy_circuit(session.circuit),
                             session.experiments, session.records, metadata,
                             session.state, session.schema)


def branch_experiment(session, experiment_id_str, *, label=None, overrides=_KEEP,
                      stimuli=_KEEP, probes=_KEEP, instruments=_KEEP,
                      measurements=_KEEP, seed=_KEEP):
    """New definition = old + explicit edit set; the original is untouched.

    Records ``derived_from`` in metadata (not digested).
    """
    _require_open(session)
    definition = None
    for existing in session.experiments:
        if experiment_id(existing, session.circuit) == experiment_id_str:
            definition = existing
            break
    if definition is None:
        raise LabConfigError(UNKNOWN_EXPERIMENT,
                             f"unknown experiment {experiment_id_str!r}")
    new_def = ExperimentDefinition(
        label=definition.label if label is None else label,
        analysis=definition.analysis,
        overrides=definition.overrides if overrides is _KEEP else overrides,
        stimuli=definition.stimuli if stimuli is _KEEP else stimuli,
        probes=definition.probes if probes is _KEEP else probes,
        instruments=definition.instruments if instruments is _KEEP else instruments,
        measurements=definition.measurements if measurements is _KEEP else measurements,
        seed=definition.seed if seed is _KEEP else seed)
    new_session, report = add_experiment(session, new_def)
    if not report.ok:
        return session, None, report
    new_id = experiment_id(new_def, session.circuit)
    metadata = tuple(sorted(session.metadata + (("derived_from", experiment_id_str),)))
    # add_experiment already built the session; attach derivation metadata.
    final = LaboratorySession(new_session.session_id, new_session.circuit,
                              new_session.experiments, new_session.records,
                              metadata, new_session.state, new_session.schema)
    return final, new_id, report


def close_session(session):
    _require_open(session)
    return LaboratorySession(session.session_id, session.circuit,
                             session.experiments, session.records,
                             session.metadata, "CLOSED", session.schema)


def to_document(session, result_payloads):
    """Snapshot value (works on closed sessions too)."""
    from .serialize import to_document as _to_document
    return _to_document(session, result_payloads)
