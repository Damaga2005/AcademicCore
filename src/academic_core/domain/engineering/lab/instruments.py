"""F8-N Virtual Laboratory — probes and ideal virtual instruments.

All instruments are ideal, pure views: ``read(run_result, config)``.
They never alter a circuit, never solve, never depend on wall clock.
Declared idealisations (normative): infinite bandwidth, no loading, no
noise, no gain/offset error, exact Decimal readout.

An invalid probe produces an honest status. A missing magnitude is
``None`` with a reason, never 0.
"""
from decimal import Decimal
from enum import Enum as _Enum

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.units import Quantity

from .model import (
    CURRENT,
    DIMENSIONLESS,
    FREQUENCY,
    TIME,
    VOLTAGE,
    AnalysisKind,
    BodeData,
    BodePointData,
    ComplexScalar,
    Coupling,
    CurrentProbe,
    InstrumentKind,
    InstrumentReading,
    InstrumentSpec,
    InstrumentStatus,
    LabConfigError,
    MeasurementKind,
    ParameterProbe,
    Scalar,
    ScopeChannelData,
    ScopeData,
    Slope,
    StimulusKind,
    SweepData,
    VoltageProbe,
    Waveform,
    lab_context,
)
from .waveform import interpolate, make_waveform, wave_mean, window_breakpoints

_ZERO = Decimal(0)
_OK = InstrumentStatus.OK.value
_UNSUP = InstrumentStatus.UNSUPPORTED.value
_NO_TRIG = InstrumentStatus.NO_TRIGGER.value
_OOR = InstrumentStatus.OUT_OF_RANGE.value
_NO_DATA = InstrumentStatus.NO_DATA.value

INVALID_PROBE = "INVALID_PROBE"

GROUND_NETS = frozenset({"0", "GND"})


def is_ground(net):
    return isinstance(net, str) and net.strip().upper() in GROUND_NETS


def components_by_ref(circuit):
    return {c.ref.upper(): c for c in circuit.components}


def dc_short_ref(circuit, l_ref):
    """Map an inductor to its DC-equivalent short source ref.

    Mirrors the certified ``dc_equivalent`` algorithm (``L_k`` in circuit
    order -> ``V{base+k}``, ``base`` = max V number, at least 9000) so the
    lab can read the short current without re-implementing the solver.
    The mapping is recorded in provenance (``dc_mapping`` note).
    """
    comps = list(circuit.components)
    nums = []
    order = []
    for c in comps:
        t = c.type.upper()
        if t == "V":
            digits = "".join(ch for ch in c.ref if ch.isdigit())
            nums.append(int(digits) if digits else 0)
        if t == "L":
            order.append(c.ref.upper())
    base = max(nums + [9000])
    try:
        k = order.index(l_ref.upper()) + 1
    except ValueError:
        raise LabConfigError(INVALID_PROBE, f"unknown inductor {l_ref!r}")
    return f"V{base + k}"


def classify_current_branch(circuit, branch):
    """Classify a current-probe branch against the circuit.

    Returns one of: R, V, I, E, G, H, F, O, TLEG, C, L, D, QLEG, MLEG,
    JLEG. Raises ``LabConfigError(INVALID_PROBE)`` for unknown refs,
    missing legs and legs on the wrong type.
    """
    if not isinstance(branch, str) or not branch:
        raise LabConfigError(INVALID_PROBE, "branch must be a non-empty string")
    comps = components_by_ref(circuit)
    if ":" in branch:
        ref, leg = branch.split(":", 1)
        comp = comps.get(ref.strip().upper())
        if comp is None:
            raise LabConfigError(INVALID_PROBE, f"unknown branch {branch!r}")
        t = comp.type.upper()
        leg = leg.strip()
        if t == "T" and leg in ("1", "2"):
            return "TLEG"
        if t == "Q" and leg.upper() in ("C", "B", "E"):
            return "QLEG"
        if t == "M" and leg.upper() in ("D", "G", "S", "B"):
            return "MLEG"
        if t == "J" and leg.upper() in ("D", "G", "S"):
            return "JLEG"
        if t == "D" and leg.upper() in ("A", "K"):
            return "D"
        raise LabConfigError(INVALID_PROBE,
                             f"branch {branch!r} is not a probed leg of {comp.ref!r}")
    comp = comps.get(branch.strip().upper())
    if comp is None:
        raise LabConfigError(INVALID_PROBE, f"unknown branch {branch!r}")
    t = comp.type.upper()
    if t in ("R", "V", "I", "E", "G", "H", "F", "O", "C", "L", "D"):
        return t
    raise LabConfigError(INVALID_PROBE,
                         f"branch {branch!r} needs a terminal leg (e.g. {comp.ref}:C)")


def check_probe_source(probe, circuit):
    """Existence validation of a probe against a circuit.

    Returns a list of ``(code, message)`` (empty = valid). Nets, branch
    refs/legs and parameter addresses are checked; engine-domain rules
    (registry fields) use the certified ``resolve_param``.
    """
    nets = set(circuit.nets)
    if isinstance(probe, VoltageProbe):
        errs = []
        for name, net in (("p", probe.p), ("n", probe.n)):
            if net not in nets:
                errs.append((INVALID_PROBE, f"unknown net {net!r}"))
        return errs
    if isinstance(probe, CurrentProbe):
        try:
            classify_current_branch(circuit, probe.branch)
        except LabConfigError as exc:
            return [(exc.code, exc.message)]
        return []
    if isinstance(probe, ParameterProbe):
        from academic_core.domain.engineering.mna.analysis import (
            InvalidCircuitError,
            resolve_param,
        )
        try:
            resolve_param(circuit, probe.address)
        except InvalidCircuitError as exc:
            return [(INVALID_PROBE, str(exc))]
        except LabConfigError as exc:
            return [(exc.code, exc.message)]
        return []
    return [(INVALID_PROBE, f"unknown probe type {type(probe).__name__}")]


def required_observable_keys(probe, circuit):
    """Observable keys an F8-M config must provide for this probe.

    Returns ``None`` when the probe is derivable without an engine
    observable (I source value, open C, DC-shorted L). Raises
    ``LabConfigError`` for probes no F8-M observable can serve (device
    legs are served via ``device_current``; whole Q/M/J refs are invalid).
    """
    if isinstance(probe, VoltageProbe):
        keys = set()
        if not is_ground(probe.p):
            keys.add(f"node_voltage:{probe.p}")
        if not is_ground(probe.n):
            keys.add(f"node_voltage:{probe.n}")
        return keys
    if isinstance(probe, CurrentProbe):
        kind = classify_current_branch(circuit, probe.branch)
        if kind == "R":
            ref = probe.branch.split(":")[0].strip()
            return {f"resistor_current:{ref}"}
        if kind in ("V", "E", "H", "F", "O"):
            return {f"aux_current:{probe.branch.strip()}"}
        if kind == "TLEG":
            return {f"aux_current:{probe.branch.strip()}"}
        if kind in ("D", "QLEG", "MLEG", "JLEG"):
            return {f"device_current:{probe.branch.strip()}"}
        if kind in ("I", "C", "L"):
            return None
    if isinstance(probe, ParameterProbe):
        return set()
    raise LabConfigError(INVALID_PROBE, "cannot derive observables for probe")


# ---------------------------------------------------------------------------
# Applicability tables (static validation)
# ---------------------------------------------------------------------------

_METER_ANALYSES = frozenset({
    AnalysisKind.OP.value, AnalysisKind.DC_SWEEP.value,
    AnalysisKind.AC_POINT.value, AnalysisKind.TRANSIENT.value,
})
_SWEEP_VIEWER_ANALYSES = frozenset({
    AnalysisKind.DC_SWEEP.value, AnalysisKind.PARAM_SWEEP.value,
    AnalysisKind.CORNERS.value, AnalysisKind.MONTE_CARLO.value,
    AnalysisKind.SENS_DC.value, AnalysisKind.SENS_AC.value,
})


def instrument_applicable(analysis_kind, instrument_kind):
    if instrument_kind in (InstrumentKind.VOLTMETER.value, InstrumentKind.AMMETER.value):
        return analysis_kind in _METER_ANALYSES
    if instrument_kind == InstrumentKind.OSCILLOSCOPE.value:
        return analysis_kind == AnalysisKind.TRANSIENT.value
    if instrument_kind == InstrumentKind.FREQUENCY_RESPONSE.value:
        return analysis_kind == AnalysisKind.AC_SWEEP.value
    if instrument_kind == InstrumentKind.SWEEP_VIEWER.value:
        return analysis_kind in _SWEEP_VIEWER_ANALYSES
    return False


def measurement_applicable(analysis_kind, measurement_kind):
    from .model import AC_MEASUREMENTS, DC_MEASUREMENTS, WAVEFORM_MEASUREMENTS
    if measurement_kind in {m.value for m in WAVEFORM_MEASUREMENTS}:
        return analysis_kind == AnalysisKind.TRANSIENT.value
    if measurement_kind in (MeasurementKind.AC_GAIN.value,
                            MeasurementKind.AC_GAIN_DB.value,
                            MeasurementKind.AC_PHASE.value,
                            MeasurementKind.AC_AMPLITUDE.value):
        return analysis_kind == AnalysisKind.AC_POINT.value
    if measurement_kind == MeasurementKind.BANDWIDTH.value:
        return analysis_kind == AnalysisKind.AC_SWEEP.value
    if measurement_kind == MeasurementKind.DC_VALUE.value:
        return analysis_kind == AnalysisKind.OP.value
    return False


# ---------------------------------------------------------------------------
# Engine-result accessors (read-only typed adapters, no re-solve)
# ---------------------------------------------------------------------------

def op_voltage_map(result):
    return {nv.node: nv.voltage.to_base() for nv in result.node_voltages}


def op_branch_map(result):
    return {b.ref.upper(): b.current.to_base() for b in result.branch_currents}


def _upper_map(mapping):
    return {str(k).upper(): v for k, v in mapping.items()}


def transient_series(result):
    """``(times, {NET: values}, {REF: inductor values})`` with
    upper-cased lookup maps (exact committed copy, no resampling)."""
    times = tuple(result.times)
    nodes = _upper_map(result.node_trajectories)
    inds = _upper_map(result.inductor_currents)
    return times, nodes, inds


def evaluate_parameter_probe(circuit, probe, source=""):
    from academic_core.domain.engineering.mna.analysis import resolve_param
    resolved = resolve_param(circuit, probe.address)
    return Scalar(resolved.nominal, tuple(resolved.dimension),
                  _dim_label(resolved.dimension), source)


def _dim_label(dimension):
    from .model import DIM_LABELS
    return DIM_LABELS.get(tuple(dimension), "1")


def voltage_op(probe, vmap):
    """``V(p, n) = V_p - V_n`` (project convention, ground = 0)."""
    with lab_context():
        vp = vmap.get(probe.p, _ZERO if is_ground(probe.p) else None)
        vn = vmap.get(probe.n, _ZERO if is_ground(probe.n) else None)
    if vp is None or vn is None:
        return None, "net absent from operating point"
    with lab_context():
        return vp - vn, ""


def current_op(probe, circuit, result, bmap, newton_state):
    """Branch current with project sign conventions, verbatim.

    Order: engine branch record; open C (exactly 0 A); DC-shorted L via
    the mapped short aux; device legs via certified ``observable_value``.
    Anything else is UNSUPPORTED, never 0.
    """
    from academic_core.domain.engineering.mna.analysis import (
        ObservableSpec,
        observable_value,
    )
    key = probe.branch.strip().upper()
    if key in bmap:
        return bmap[key], ""
    kind = classify_current_branch(circuit, probe.branch)
    if kind == "C":
        return _ZERO, "open in DC (exactly 0 A)"
    if kind == "L":
        short = dc_short_ref(circuit, probe.branch).upper()
        if short in bmap:
            return bmap[short], f"DC short {short}"
        return None, f"DC short {short} absent from result"
    if kind in ("D", "QLEG", "MLEG", "JLEG"):
        if newton_state is None:
            return None, "no solver state for device current"
        try:
            with lab_context():
                val = observable_value(ObservableSpec("device_current", probe.branch.strip()),
                                       newton_state)
        except Exception as exc:
            return None, f"device current unavailable: {exc}"
        return val, ""
    return None, f"branch {probe.branch!r} not offered by this operating point"


def _point_params(point):
    try:
        return dict(point.parameters)
    except Exception:
        return {}


def _status_str(status):
    if isinstance(status, _Enum):
        return status.value
    return str(status)


def _point_success(point):
    """Per-point success across SweepPoint (Enum) and MCIteration (str)."""
    return _status_str(point.status) in ("converged", "ok")


def _point_status_str(point):
    return _status_str(point.status)


def _point_observables(point):
    try:
        return point.observables or {}
    except AttributeError:
        return {}


def _point_nodes(point):
    try:
        return point.node_voltages or {}
    except AttributeError:
        return {}


def _point_result(point):
    try:
        return point.result
    except AttributeError:
        return None


def _point_diagnostic(point):
    try:
        return point.diagnostic or ""
    except AttributeError:
        return ""


def voltage_point(probe, point):
    observables = _point_observables(point)
    nodes = _point_nodes(point)
    with lab_context():
        if is_ground(probe.p):
            vp = _ZERO
        elif f"node_voltage:{probe.p}" in observables:
            vp = observables[f"node_voltage:{probe.p}"]
        elif probe.p in nodes:
            vp = nodes[probe.p]
        else:
            return None, f"net {probe.p!r} absent from sweep point"
        if is_ground(probe.n):
            vn = _ZERO
        elif f"node_voltage:{probe.n}" in observables:
            vn = observables[f"node_voltage:{probe.n}"]
        elif probe.n in nodes:
            vn = nodes[probe.n]
        else:
            return None, f"net {probe.n!r} absent from sweep point"
        return vp - vn, ""


def current_point(probe, circuit, run_circuit, point):
    """Per-point branch current for F8-M sweep-likes."""
    from academic_core.domain.engineering.mna.analysis import ObservableSpec
    observables = _point_observables(point)
    kind = classify_current_branch(circuit, probe.branch)
    branch = probe.branch.strip()
    if kind == "R":
        key = f"resistor_current:{branch.split(':')[0]}"
        if key in observables:
            return observables[key], ""
        return None, f"observable {key} not in sweep config"
    if kind in ("V", "E", "H", "F", "O", "TLEG"):
        key = f"aux_current:{branch}"
        if key in observables:
            return observables[key], ""
        return None, f"observable {key} not in sweep config"
    if kind in ("D", "QLEG", "MLEG", "JLEG"):
        key = f"device_current:{branch}"
        if key in observables:
            return observables[key], ""
        return None, f"observable {key} not in sweep config"
    if kind == "C":
        return _ZERO, "open in DC (exactly 0 A)"
    if kind == "L":
        result = _point_result(point)
        if result is None:
            return None, "sweep point has no result payload"
        bmap = op_branch_map(result)
        short = dc_short_ref(circuit, branch).upper()
        if short in bmap:
            return bmap[short], f"DC short {short}"
        return None, f"DC short {short} absent from sweep point"
    if kind == "I":
        comp = components_by_ref(run_circuit).get(branch.upper())
        if comp is None or comp.value is None:
            return None, f"source {branch!r} has no DC value"
        params = _point_params(point)
        with lab_context():
            swept = None
            for pkey, pval in params.items():
                if str(pkey).upper() == f"{branch.upper()}.VALUE":
                    swept = pval
                    break
            base = swept if swept is not None else comp.value.to_base()
            return -base, "reported -Is (F8-B rule)"
    return None, f"branch {branch!r} not offered by this sweep"


def voltage_waveform(probe, circuit, result, source=""):
    """Voltage waveform from committed transient samples (exact copy)."""
    times, nodes, _ = transient_series(result)
    with lab_context():
        if is_ground(probe.p):
            xp = [_ZERO] * len(times)
        elif probe.p.upper() in nodes:
            xp = list(nodes[probe.p.upper()])
        else:
            return None, f"net {probe.p!r} absent from transient result"
        if is_ground(probe.n):
            xn = [_ZERO] * len(times)
        elif probe.n.upper() in nodes:
            xn = list(nodes[probe.n.upper()])
        else:
            return None, f"net {probe.n!r} absent from transient result"
        values = tuple(a - b for a, b in zip(xp, xn))
    return make_waveform(times, values, VOLTAGE, "V", source), ""


def current_waveform(probe, circuit, result, source=""):
    """Transient branch current: resistor derived ``(V1-V2)/R``,
    inductor direct; anything else UNSUPPORTED (F8-L exposes no more)."""
    kind = classify_current_branch(circuit, probe.branch)
    branch = probe.branch.strip()
    times, nodes, inds = transient_series(result)
    if kind == "R":
        comp = components_by_ref(circuit).get(branch.split(":")[0].upper())
        if comp is None or comp.value is None:
            return None, f"resistor {branch!r} has no value"
        nets = comp.pins
        with lab_context():
            r = comp.value.to_base()
            if r == 0:
                return None, f"resistor {branch!r} has zero value"
            n1, n2 = nets.get("1"), nets.get("2")
            x1 = [_ZERO] * len(times) if is_ground(n1) else nodes.get(str(n1).upper())
            x2 = [_ZERO] * len(times) if is_ground(n2) else nodes.get(str(n2).upper())
            if x1 is None or x2 is None:
                return None, "resistor nets absent from transient result"
            values = tuple((a - b) / r for a, b in zip(x1, x2))
        return make_waveform(times, values, CURRENT, "A", source), ""
    if kind == "L":
        series = inds.get(branch.upper())
        if series is None:
            return None, f"inductor {branch!r} absent from transient result"
        return make_waveform(times, tuple(series), CURRENT, "A", source), ""
    return None, f"transient current of {branch!r} not exposed by F8-L"


def phasor_sub(a, b):
    with lab_context():
        return a - b


def voltage_phasor(probe, result):
    vp = result.voltage_of(probe.p) if not is_ground(probe.p) else DecimalComplex(_ZERO, _ZERO)
    vn = result.voltage_of(probe.n) if not is_ground(probe.n) else DecimalComplex(_ZERO, _ZERO)
    if vp is None or vn is None:
        missing = probe.p if vp is None else probe.n
        return None, f"net {missing!r} absent from AC result"
    return phasor_sub(vp, vn), ""


def current_phasor(probe, result):
    val = result.current_of(probe.branch.strip())
    if val is None:
        return None, f"branch {probe.branch!r} not offered by this AC analysis"
    return val, ""


def ac_excitation_phasor(circuit):
    """Unique nonzero AC excitation phasor ``(ref, phasor)`` or ``None``.

    Follows the certified extraction rules (``ac_mag`` / ``ac`` /
    ``phase`` / ``ac_phase`` / ``phase_unit``); delay/wave ignored (AC
    analysis uses the phasor only). ``None`` when zero or ambiguous.
    """
    from academic_core.domain.engineering.math.trig import (
        decimal_cos,
        decimal_pi,
        decimal_sin,
        make_context,
    )
    from academic_core.domain.engineering.units import parse_quantity
    found = []
    ctx = make_context()
    with lab_context():
        for comp in circuit.components:
            if comp.type.upper() not in ("V", "I"):
                continue
            params = dict(comp.parameters or {})
            mag = None
            if "ac_mag" in params:
                raw = params["ac_mag"]
                if isinstance(raw, Quantity):
                    mag = raw.to_base()
                elif isinstance(raw, str):
                    try:
                        mag = parse_quantity(raw).to_base()
                    except Exception:
                        continue
                elif isinstance(raw, (int, Decimal)) and not isinstance(raw, bool):
                    mag = Decimal(raw)
                else:
                    continue
                ph_raw = params.get("ac_phase", params.get("phase", 0))
                unit = str(params.get("phase_unit", "deg")).strip().lower()
            elif params.get("ac") is True:
                mag = comp.value.to_base() if comp.value is not None else _ZERO
                ph_raw = params.get("ac_phase", params.get("phase", 0))
                unit = str(params.get("phase_unit", "deg")).strip().lower()
            elif "ac" in params and not isinstance(params["ac"], bool):
                raw = params["ac"]
                if isinstance(raw, Quantity):
                    mag = raw.to_base()
                elif isinstance(raw, (int, Decimal)) and not isinstance(raw, bool):
                    mag = Decimal(raw)
                else:
                    continue
                ph_raw = params.get("ac_phase", params.get("phase", 0))
                unit = str(params.get("phase_unit", "deg")).strip().lower()
            elif "phase" in params and "ac_mag" not in params:
                ph_raw = params["phase"]
                unit = str(params.get("phase_unit", "deg")).strip().lower()
                mag = comp.value.to_base() if comp.value is not None else _ZERO
            else:
                continue
            if mag is None or mag == 0:
                continue
            if isinstance(ph_raw, bool):
                continue
            try:
                ph = Decimal(ph_raw) if not isinstance(ph_raw, Decimal) else ph_raw
            except Exception:
                continue
            if unit not in ("deg", "rad"):
                continue
            angle = ph * decimal_pi(ctx) / Decimal(180) if unit == "deg" else ph
            echo = DecimalComplex(mag * decimal_cos(angle, ctx),
                                  mag * decimal_sin(angle, ctx))
            found.append((comp.ref, echo))
    if len(found) != 1:
        return None
    return found[0]


# ---------------------------------------------------------------------------
# Instrument evaluation (pure views over a run payload)
# ---------------------------------------------------------------------------

def _reading(key, kind, status, reason="", data=None):
    return InstrumentReading(key, kind, status, reason, data)


def evaluate_meter(key, spec, signal, dimension, unit_label, source=""):
    """Scalar meter reading from an already-evaluated signal."""
    if signal is None:
        return _reading(key, spec.kind, _NO_DATA, "no usable payload")
    if isinstance(signal, tuple):
        val, reason = signal
        if val is None:
            return _reading(key, spec.kind, _UNSUP, reason)
        signal = val
    if isinstance(signal, DecimalComplex):
        data = ComplexScalar(signal, dimension, unit_label,
                             frequency_hz=Decimal(0), source=source)
        return _reading(key, spec.kind, _OK, "", data)
    if isinstance(signal, Decimal):
        return _reading(key, spec.kind, _OK, "",
                        Scalar(signal, dimension, unit_label, source))
    if isinstance(signal, Scalar):
        return _reading(key, spec.kind, _OK, "", signal)
    return _reading(key, spec.kind, _UNSUP, "unsupported meter signal")


def evaluate_transient_meter(key, spec, wave, at, t_bounds, dimension,
                             unit_label, source=""):
    """Meter on a transient waveform at ``at`` (None = final), PL exact."""
    if wave is None:
        return _reading(key, spec.kind, _NO_DATA, "no waveform payload")
    if isinstance(wave, tuple):
        wave, reason = wave
        if wave is None:
            return _reading(key, spec.kind, _UNSUP, reason)
    t0, tstop = t_bounds
    t = wave.times[-1] if at is None else at
    with lab_context():
        if not t0 <= t <= tstop:
            return _reading(key, spec.kind, _OOR,
                            f"reading time {t} outside [{t0},{tstop}] (no extrapolation)")
        val = interpolate(wave, t)
    return _reading(key, spec.kind, _OK, "",
                    Scalar(val, dimension, unit_label, source))


def evaluate_scope(key, spec, channel_waves, t_bounds, source=""):
    """Oscilloscope: display grid over committed samples (PL exact).

    ``channel_waves`` maps probe key -> Waveform (or ``(None, reason)``).
    Measurements are never taken on the display grid (they use committed
    samples with explicit windows); scope config changes therefore never
    alter numerical results.
    """
    t0, tstop = t_bounds
    with lab_context():
        if spec.trigger is not None:
            trig = spec.trigger
            trig_wave = channel_waves.get(trig.source_probe_key)
            if trig_wave is None:
                return _reading(key, spec.kind, _UNSUP,
                                f"trigger probe {trig.source_probe_key!r} unknown")
            if isinstance(trig_wave, tuple):
                _, reason = trig_wave
                return _reading(key, spec.kind, _UNSUP,
                                f"trigger channel unavailable: {reason}")
            # Detection on the raw signal (for AC coupling the display is
            # re-centred over the resulting window; documented).
            from .waveform import crossings as _cross
            cands = [tc for tc in _cross(trig_wave, trig.level, trig.slope,
                                         trig.hysteresis if trig.hysteresis != 0 else None,
                                         trig_wave.times[0], trig_wave.times[-1])
                     if tc >= t0 + trig.pre]
            if not cands:
                return _reading(key, spec.kind, _NO_TRIG,
                                "no trigger crossing (normal mode: no free-run fallback)")
            tc = cands[0]
            a, b = tc - trig.pre, tc + trig.post
            if not (t0 <= a and b <= tstop):
                return _reading(key, spec.kind, _OOR,
                                "trigger window outside simulated span")
            trigger_time = tc
        else:
            a, b = spec.window
            if not (t0 <= a and b <= tstop):
                return _reading(key, spec.kind, _OOR,
                                "scope window outside simulated span (no extrapolation)")
            trigger_time = None
        n = spec.sample_count
        delta = (b - a) / Decimal(n - 1)
        grid = tuple(a + delta * Decimal(k) for k in range(n - 1)) + (b,)
    chans = []
    for ch in spec.channels:
        wave = channel_waves.get(ch.probe_key)
        if wave is None:
            return _reading(key, spec.kind, _UNSUP,
                            f"scope probe {ch.probe_key!r} unknown")
        if isinstance(wave, tuple):
            _, reason = wave
            return _reading(key, spec.kind, _UNSUP,
                            f"scope channel {ch.probe_key!r} unavailable: {reason}")
        with lab_context():
            raw = tuple(interpolate(wave, t) for t in grid)
            if ch.coupling == Coupling.AC.value:
                mean = wave_mean(wave, a, b)
                coupled = tuple(v - mean for v in raw)
            else:
                coupled = raw
            ydiv = tuple((v + ch.offset) / ch.volts_per_div for v in coupled)
            clipped = tuple(abs(y) > Decimal(4) for y in ydiv)
        chans.append(ScopeChannelData(ch.probe_key, grid, raw, coupled, ydiv,
                                      clipped, wave.unit_label))
    return _reading(key, spec.kind, _OK, "",
                    ScopeData(tuple(chans), (a, b), trigger_time, 8))


def evaluate_fr_viewer(key, sweep_result, bode_result, db_threshold, source=""):
    """Frequency-response viewer over the certified Bode analysis."""
    points = []
    for bp in bode_result.points:
        try:
            freq = bp.frequency.to_base()
        except AttributeError:
            freq = bp.frequency
        db = bp.db.value if bp.db is not None else None
        points.append(BodePointData(freq, db, bp.wrapped, bp.unwrapped,
                                    _status_str(bp.status)))
    lo = hi = None
    for band in bode_result.bands:
        if band.defined and band.bandwidth_lo is not None and band.bandwidth_hi is not None:
            lo, hi = band.bandwidth_lo, band.bandwidth_hi
            break
    data = BodeData(tuple(points), lo, hi, db_threshold, source)
    failed = sum(1 for bp in bode_result.points
                 if _status_str(bp.status) != "solved")
    reason = f"{failed} failed points" if failed else ""
    return _reading(key, InstrumentKind.FREQUENCY_RESPONSE.value, _OK, reason, data)


def _result_points(result):
    try:
        return list(result.points)
    except AttributeError:
        pass
    try:
        return list(result.corners)
    except AttributeError:
        pass
    try:
        return list(result.iterations)
    except AttributeError:
        pass
    return []


def _sweep_axis_points(result, config):
    """``(axis_values, axis_label)`` for F8-M sweep-likes."""
    target_key = None
    try:
        target = config.target
    except AttributeError:
        target = None
    if target is not None:
        try:
            target_key = target.key
        except AttributeError:
            target_key = str(target)
    pts = _result_points(result)
    if target_key is not None:
        axis = tuple(_point_params(p).get(target_key) for p in pts)
        if all(isinstance(v, Decimal) for v in axis):
            return axis, target_key
    return tuple(Decimal(p.index) for p in pts), "point"


def evaluate_sweep_viewer(key, probe, probe_kind, analysis_kind, result, config,
                          circuit, run_circuit, source=""):
    """Sweep viewer: direct table over F8-M results (no recomputation).

    Failed points are ``None`` with a status, never 0. Corners keep the
    corner-extremum honesty text verbatim; Monte Carlo keeps plan digest,
    failures and statistics.
    """
    from academic_core.domain.engineering.mna.analysis import CORNER_HONESTY
    statuses = []
    values = []
    extra = []
    if analysis_kind in (AnalysisKind.SENS_DC.value, AnalysisKind.SENS_AC.value):
        return _sensitivity_view(key, probe, probe_kind, analysis_kind, result,
                                 circuit, source)
    pts = _result_points(result)
    if analysis_kind == AnalysisKind.CORNERS.value:
        axis = tuple(Decimal(p.index) for p in pts)
        axis_label = "corner"
    else:
        axis, axis_label = _sweep_axis_points(result, config)
    for p in pts:
        status = _point_status_str(p)
        statuses.append(f"{p.index}:{status}" + (f" {p.diagnostic}" if p.diagnostic else ""))
        if not _point_success(p):
            values.append(None)
            continue
        val, _ = _point_probe_value(probe, probe_kind, circuit, run_circuit, p)
        values.append(val)
    unit_label, dimension = _probe_units(probe, probe_kind, circuit)
    if analysis_kind == AnalysisKind.CORNERS.value:
        extra.append(("scope", result.scope))
        for obs_key, ext in (result.extrema or {}).items():
            for side in ("min", "max"):
                entry = (ext or {}).get(side)
                if entry is not None:
                    extra.append((f"extremum:{obs_key}:{side}", str(entry.get("value"))))
                    extra.append((f"extremum:{obs_key}:{side}:arg",
                                  str(entry.get("arg_corner", ""))))
    if analysis_kind == AnalysisKind.MONTE_CARLO.value:
        extra.append(("plan_digest", str(result.plan_digest)))
        extra.append(("failures", str(result.failure_count)))
        for obs_key, stats in (result.statistics or {}).items():
            for skey in ("n", "mean", "variance", "std", "min", "max"):
                if skey in stats:
                    extra.append((f"statistics:{obs_key}:{skey}", str(stats[skey])))
            for pkey, pval in (stats.get("percentiles", {}) or {}).items():
                extra.append((f"statistics:{obs_key}:{pkey}", str(pval)))
    data = SweepData(axis, tuple(values), tuple(statuses), axis_label,
                     unit_label, source, tuple(sorted(extra)))
    failed = sum(1 for v in values if v is None)
    reason = f"{failed} failed points" if failed else ""
    return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _OK, reason, data)


def _point_probe_value(probe, probe_kind, circuit, run_circuit, point):
    """Scalar value of a probe at one F8-M sweep point (or (None, reason))."""
    if probe_kind == "V":
        return voltage_point(probe, point)
    if probe_kind == "I":
        return current_point(probe, circuit, run_circuit, point)
    if probe_kind == "P":
        params = _point_params(point)
        for pkey, pval in params.items():
            if str(pkey).upper() == probe.address.key.upper():
                return pval, "swept axis value"
        try:
            scalar = evaluate_parameter_probe(run_circuit, probe)
        except Exception as exc:
            return None, str(exc)
        return scalar.value, "nominal parameter value"
    return None, "unknown probe kind"


def _probe_units(probe, probe_kind, circuit):
    if probe_kind == "V":
        return "V", VOLTAGE
    if probe_kind == "I":
        return "A", CURRENT
    if probe_kind == "P":
        from academic_core.domain.engineering.mna.analysis import resolve_param
        try:
            resolved = resolve_param(circuit, probe.address)
            return _dim_label(tuple(resolved.dimension)), tuple(resolved.dimension)
        except Exception:
            return "1", DIMENSIONLESS
    return "1", DIMENSIONLESS


def _sensitivity_view(key, probe, probe_kind, analysis_kind, result, circuit, source=""):
    """Sensitivity viewer: table of dO/dp with dimension tuples.

    DC: derivatives are linear, so differential voltage probes subtract
    exactly. AC: magnitude/phase/dB derivatives do not subtract, so only
    single-observable probes are served (differential is UNSUPPORTED).
    """
    observables = result.observables or {}
    if probe_kind == "P":
        return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _UNSUP,
                        "sweep viewer needs a signal probe for sensitivity")
    keys = required_observable_keys(probe, circuit)
    if keys is None or not keys <= set(observables):
        return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _UNSUP,
                        "probe observables absent from sensitivity result")
    if analysis_kind == AnalysisKind.SENS_AC.value and len(keys) != 1:
        return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _UNSUP,
                        "differential probes unsupported for AC sensitivity")
    if probe_kind == "I":
        return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _UNSUP,
                        "current probes unsupported for sensitivity viewer")
    (obs_key,) = sorted(keys) if len(keys) == 1 else (None,)
    params = []
    values = []
    statuses = []
    extra = []
    with lab_context():
        if analysis_kind == AnalysisKind.SENS_DC.value:
            if len(keys) == 1:
                entry = observables[obs_key]
                sens = entry.get("sensitivities", {})
                extra.append(("nominal", str(entry.get("value"))))
                for param in sorted(sens):
                    params.append(param)
                    values.append(sens[param].get("derivative"))
                    statuses.append("completed")
                    extra.append((f"dimension:{param}", str(list(sens[param].get("dimension", [])))))
                    extra.append((f"normalized:{param}", str(sens[param].get("normalized"))))
            else:
                ka, kb = sorted(keys)
                ea, eb = observables[ka], observables[kb]
                sa, sb = ea.get("sensitivities", {}), eb.get("sensitivities", {})
                for param in sorted(set(sa) & set(sb)):
                    params.append(param)
                    values.append(sa[param].get("derivative") - sb[param].get("derivative"))
                    statuses.append("completed")
            unit_label, _dim = _probe_units(probe, probe_kind, circuit)
            axis_label = "parameter"
        else:
            entry = observables[obs_key]
            sens = entry.get("sensitivities", {})
            extra.append(("magnitude", str(entry.get("magnitude"))))
            for param in sorted(sens):
                params.append(param)
                values.append(sens[param].get("d_magnitude"))
                statuses.append("completed")
                extra.append((f"d_phase_rad:{param}", str(sens[param].get("d_phase_rad"))))
                extra.append((f"d_db:{param}", str(sens[param].get("d_db"))))
            unit_label, _dim = _probe_units(probe, probe_kind, circuit)
            axis_label = "parameter"
    data = SweepData(tuple(params), tuple(values), tuple(statuses), axis_label,
                     unit_label, source, tuple(sorted(extra)))
    return _reading(key, InstrumentKind.SWEEP_VIEWER.value, _OK, "", data)
