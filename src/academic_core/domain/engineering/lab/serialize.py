"""F8-N Virtual Laboratory — canonical serialization (schema ``f8n-lab/1``).

Canonical JSON: UTF-8, sorted keys, compact separators, ASCII, no
NaN/Infinity. Every Decimal is the string ``str(d.normalize())`` (exact,
round-trippable); Quantity is base-unit value + dimension; missing is
JSON null with an explicit status next to it.

Never: pickle, eval, marshal, YAML object tags, class-name-based
reconstruction. Loading builds objects only through allowlisted typed
constructors. Compatibility: ``schema`` must equal ``f8n-lab/1``
exactly; no forward/backward promise (see replay).
"""
import dataclasses
import hashlib
import json
from decimal import Decimal
from enum import Enum
from fractions import Fraction

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.units import Quantity

from .model import (
    MAX_SERIALIZED_BYTES,
    SCHEMA,
    AnalysisKind,
    AnalysisSpec,
    Annotation,
    AnnotationRecord,
    BodeData,
    BodePointData,
    ComplexScalar,
    CurrentProbe,
    ExperimentDefinition,
    ExperimentRecord,
    InstrumentKind,
    InstrumentReading,
    InstrumentSpec,
    LabConfigError,
    LaboratorySession,
    LoadStatus,
    MeasurementResult,
    MeasurementSpec,
    ParameterProbe,
    Run,
    Scalar,
    ScopeChannel,
    ScopeChannelData,
    ScopeData,
    StimulusSpec,
    SweepData,
    TriggerSpec,
    VoltageProbe,
    Waveform,
)

INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
SERIALIZATION_TOO_LARGE = "SERIALIZATION_TOO_LARGE"

_ZERO = Decimal(0)


def _fail(message):
    raise LabConfigError(INVALID_SERIALIZATION, message)


# ---------------------------------------------------------------------------
# Canonical value encoding
# ---------------------------------------------------------------------------

def decimal_string(d):
    """Exact canonical decimal string (round-trips through Decimal(str)).

    DEVIATION D-R1 (documented in GATE-F8N): the design gate asks for
    ``str(d.normalize())``. ``normalize()`` is exact but NOT
    representation-preserving (``Decimal(900)`` -> ``"9E+2"``), and the
    certified engines hash ``str()`` of Decimals into their digests
    (F8-M plan/config digests). A save/load round trip would then flip
    engine digests and break normative same-version replay
    (``EQUIVALENT``). Plain ``str(d)`` is exactly round-trippable
    (``Decimal(str(d)) == d`` bit-for-bit, same representation) and
    keeps every digest stable; no float or precision is involved.
    """
    if isinstance(d, bool) or not isinstance(d, Decimal) or not d.is_finite():
        _fail(f"non-finite/non-Decimal value {d!r}")
    return str(d)


def canonical(obj):
    """Map any lab/engine value to a canonical JSON-safe structure.

    Dicts are key-sorted (arrays keep semantic order, documented where
    order is significant). Floats are rejected loudly (Decimal only).
    Rationals (Fraction / RationalComplex) are stored as exact
    numerator/denominator pairs, never float.
    """
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        _fail("float value in canonical payload")
    if isinstance(obj, Decimal):
        return decimal_string(obj)
    if isinstance(obj, DecimalComplex):
        return {"im": decimal_string(obj.im), "re": decimal_string(obj.re)}
    if isinstance(obj, Fraction):
        return {"den": obj.denominator, "num": obj.numerator}
    if isinstance(obj, RationalComplex):
        return {"im": canonical(obj.im), "re": canonical(obj.re)}
    if isinstance(obj, Quantity):
        return {"d": list(obj.dimension), "v": decimal_string(obj.to_base())}
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj):
        # NOTE: attribute access via the instance __dict__ (frozen
        # dataclasses are never slotted in this codebase); bare
        # getattr() is forbidden by the lab security policy (N-091).
        # dataclasses.astuple() is NOT usable here: it would recurse
        # into nested dataclasses (Quantity, DecimalComplex) and break
        # their canonical forms.
        values = obj.__dict__
        out = {}
        for f in dataclasses.fields(obj):
            out[f.name] = canonical(values[f.name])
        return out
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[_canonical_key(k)] = canonical(v)
        return out
    if isinstance(obj, (tuple, list)):
        return [canonical(v) for v in obj]
    _fail(f"unserializable type {type(obj).__name__}")


def _canonical_key(key):
    from academic_core.domain.engineering.mna.analysis import ParamAddress
    if isinstance(key, ParamAddress):
        return key.key
    if isinstance(key, str):
        return key
    _fail(f"non-string mapping key {key!r}")


def dumps_canonical(obj):
    """Canonical JSON text (the only persistence form)."""
    return json.dumps(canonical(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def digest(domain_tag, obj):
    """``sha256(domain_tag || 0x00 || canonical_json_bytes)`` hex."""
    payload = dumps_canonical(obj).encode("utf-8")
    h = hashlib.sha256()
    h.update(domain_tag.encode("utf-8"))
    h.update(b"\x00")
    h.update(payload)
    return h.hexdigest()


#: Provenance metadata keys that are volatile by engine design (wall
#: clock) and must never enter a digest or a stored document. Found by
#: audit: F8-J embeds ``provenance.timestamp`` in its DC operating
#: point; every certified engine digest already excludes it.
VOLATILE_KEYS = frozenset({"timestamp", "datetime"})


def scrub_volatile(node):
    """Drop volatile provenance metadata (recursive, deterministic)."""
    if isinstance(node, dict):
        return {k: scrub_volatile(v) for k, v in node.items()
                if str(k).lower() not in VOLATILE_KEYS}
    if isinstance(node, list):
        return [scrub_volatile(v) for v in node]
    return node


def stable_result_payload(result):
    """JSON-safe, digest-stable form of a live certified result."""
    return scrub_volatile(canonical(result))


# ---------------------------------------------------------------------------
# Closed per-type circuit parameter schema
# ---------------------------------------------------------------------------

_D_QUANTITY_FIELDS = {
    "D": {"Is", "n", "Vt", "Vz", "nz", "Iz", "Iph"},
    "Q": {"Is", "Bf", "Br", "Nf", "Nr", "Vt"},
    "M": {"Kp", "Vto", "Lambda", "Phi", "Gamma"},
    "J": {"Idss", "Vp", "Lambda"},
}
_DIODE_SETS = {
    None: {"Is", "n", "Vt"},
    "RECT": {"Is", "n", "Vt"},
    "LED": {"Is", "n", "Vt"},
    "SCHOTTKY": {"Is", "n", "Vt"},
    "ZENER": {"Is", "n", "Vt", "Vz", "nz", "Iz"},
    "PHOTO": {"Is", "n", "Vt", "Iph"},
}
_POLARITY = {"Q": ("NPN", "PNP"), "M": ("NMOS", "PMOS"), "J": ("NCHAN", "PCHAN")}
_VI_KEYS = {"wave", "ac_mag", "ac", "ac_phase", "phase", "phase_unit"}
_WAVE_KEYS = {
    "dc": frozenset(),
    "step": frozenset({"v1", "v2", "t0"}),
    "pulse": frozenset({"v1", "v2", "td", "tr", "tf", "width", "period"}),
    "sine": frozenset({"vo", "va", "freq", "td"}),
}


def _canonical_wave(ref, raw):
    if not isinstance(raw, dict):
        _fail(f"{ref}: 'wave' must be a dict")
    wtype = raw.get("type")
    if not isinstance(wtype, str) or wtype.lower() not in _WAVE_KEYS:
        _fail(f"{ref}: bad wave type {wtype!r}")
    wtype = wtype.lower()
    if set(raw) != _WAVE_KEYS[wtype] | {"type"}:
        _fail(f"{ref}: wave {wtype!r} needs exactly keys "
              f"{sorted(_WAVE_KEYS[wtype] | {'type'})}")
    out = {"type": wtype}
    for key, val in raw.items():
        if key == "type":
            continue
        if key in ("v1", "v2", "vo", "va"):
            if not isinstance(val, Quantity):
                _fail(f"{ref}: wave {key!r} must be a Quantity")
            out[key] = canonical(val)
        else:
            if isinstance(val, bool) or not isinstance(val, Decimal) \
                    or not val.is_finite():
                _fail(f"{ref}: wave time {key!r} must be finite Decimal")
            out[key] = decimal_string(val)
    return out


def canonical_parameters(comp):
    """Closed-schema canonical parameters (unknown keys rejected)."""
    t = comp.type.upper()
    params = dict(comp.parameters or {})
    ref = comp.ref
    if t in ("R", "C", "L", "T", "O"):
        if params:
            _fail(f"{ref}: type {t} takes no parameters, got {sorted(params)}")
        return {}
    if t in ("V", "I"):
        unknown = set(params) - _VI_KEYS
        if unknown:
            _fail(f"{ref}: unknown V/I parameters {sorted(unknown)}")
        out = {}
        for key in sorted(params):
            val = params[key]
            if key == "wave":
                out[key] = _canonical_wave(ref, val)
            elif key == "phase_unit":
                if not isinstance(val, str) or val.strip().lower() not in ("deg", "rad"):
                    _fail(f"{ref}: bad phase_unit {val!r}")
                out[key] = val
            elif key == "ac":
                if isinstance(val, bool):
                    out[key] = val
                elif isinstance(val, (Quantity, Decimal, int)) and not isinstance(val, bool):
                    out[key] = canonical(val)
                elif isinstance(val, str):
                    out[key] = val
                else:
                    _fail(f"{ref}: bad 'ac' parameter {val!r}")
            elif key == "ac_mag":
                if isinstance(val, bool) or not isinstance(val, (Quantity, Decimal, int, str)):
                    _fail(f"{ref}: bad ac_mag {val!r}")
                out[key] = canonical(val)
            elif key in ("ac_phase", "phase"):
                if isinstance(val, bool) or not isinstance(val, (Decimal, int, str)):
                    _fail(f"{ref}: bad {key} {val!r}")
                out[key] = canonical(val)
        return out
    if t == "D":
        kind = params.get("kind")
        if kind is not None and (not isinstance(kind, str)
                                 or kind.upper() not in _DIODE_SETS):
            _fail(f"{ref}: bad diode kind {kind!r}")
        want = _DIODE_SETS[kind.upper() if isinstance(kind, str) else None]
        if kind is not None:
            want = want | {"kind"}
        if set(params) != want:
            _fail(f"{ref}: diode needs exactly parameters {sorted(want)}, "
                  f"got {sorted(params)}")
        out = {}
        for key in sorted(params):
            if key == "kind":
                out[key] = params[key]
            else:
                if not isinstance(params[key], Quantity):
                    _fail(f"{ref}: diode parameter {key!r} must be a Quantity")
                out[key] = canonical(params[key])
        return out
    if t in ("Q", "M", "J"):
        want = _D_QUANTITY_FIELDS[t] | {"polarity"}
        if set(params) != want:
            _fail(f"{ref}: type {t} needs exactly parameters {sorted(want)}, "
                  f"got {sorted(params)}")
        out = {}
        for key in sorted(params):
            if key == "polarity":
                if not isinstance(params[key], str) \
                        or params[key].upper() not in _POLARITY[t]:
                    _fail(f"{ref}: bad polarity {params[key]!r}")
                out[key] = params[key]
            else:
                if not isinstance(params[key], Quantity):
                    _fail(f"{ref}: parameter {key!r} must be a Quantity")
                out[key] = canonical(params[key])
        return out
    if t in ("E", "G"):
        if set(params) != {"cp", "cn"} or \
                not all(isinstance(params[k], str) for k in ("cp", "cn")):
            _fail(f"{ref}: type {t} needs string cp/cn, got {sorted(params)}")
        return {"cn": params["cn"], "cp": params["cp"]}
    if t in ("H", "F"):
        if set(params) != {"control_ref"} or not isinstance(params["control_ref"], str):
            _fail(f"{ref}: type {t} needs string control_ref")
        return {"control_ref": params["control_ref"]}
    _fail(f"{ref}: unknown component type {t!r}")


def canonical_circuit(circuit):
    """Canonical typed circuit snapshot (components sorted by ref)."""
    comps = []
    for comp in sorted(circuit.components, key=lambda c: c.ref.upper()):
        value = canonical(comp.value) if comp.value is not None else None
        pins = sorted(((str(k), str(v)) for k, v in comp.pins.items()))
        comps.append({"ref": comp.ref, "type": comp.type.upper(),
                      "value": value, "pins": pins,
                      "parameters": canonical_parameters(comp)})
    return {"name": circuit.name, "components": comps,
            "nets": sorted(set(str(n) for n in circuit.nets))}


# ---------------------------------------------------------------------------
# Canonical analysis / experiment forms + digests
# ---------------------------------------------------------------------------

def canonical_analysis(spec):
    kind = spec.kind
    out = {"kind": kind}
    payload = (spec.sweep or spec.param_sweep or spec.corners or spec.sens
               or spec.sens_ac or spec.mc or spec.transient)
    if payload is not None:
        if kind == AnalysisKind.MONTE_CARLO.value:
            out["config"] = canonical(_strip_mc_seed(payload))
        else:
            out["config"] = canonical(payload)
    if spec.frequency is not None:
        out["frequency"] = canonical(spec.frequency)
    if spec.frequencies:
        out["frequencies"] = canonical(tuple(spec.frequencies))
        out["input_source"] = spec.input_source
        out["output_p"] = spec.output_p
        out["output_n"] = spec.output_n
        if spec.db_threshold is not None:
            out["db_threshold"] = decimal_string(spec.db_threshold)
    return out


def _strip_mc_seed(config):
    """MC config canonical form without seed (seed lives in the definition)."""
    return dataclasses.replace(config, seed=None)


def canonical_probe(probe):
    return {"type": type(probe).__name__, "spec": canonical(probe)}


def experiment_canonical(defn, circuit):
    """Digested subset of an experiment (labels/notes excluded)."""
    return {
        "analysis": canonical_analysis(defn.analysis),
        "circuit": canonical_circuit(circuit),
        "instruments": [[k, canonical(v)] for k, v in defn.instruments],
        "measurements": [[k, canonical(v)] for k, v in defn.measurements],
        "overrides": [[addr.key, decimal_string(val)] for addr, val in defn.overrides],
        "probes": [[k, canonical_probe(v)] for k, v in defn.probes],
        "seed": defn.seed,
        "stimuli": [canonical(s) for s in defn.stimuli],
    }


def experiment_digest(defn, circuit):
    return digest("f8n/experiment/1", experiment_canonical(defn, circuit))


def experiment_id(defn, circuit):
    return "exp-" + experiment_digest(defn, circuit)[:16]


def experiment_core_canonical(defn, circuit):
    """Digested numerical inputs of an experiment (instrument views excluded).

    Scope/meter/viewer configs are pure presentation views: changing any
    scope field changes the reading, never the run (test N-030). The run
    digest therefore covers this core form, while the experiment identity
    (``experiment_digest``) covers the full configuration.
    """
    full = experiment_canonical(defn, circuit)
    return {k: v for k, v in full.items() if k != "instruments"}


def experiment_core_digest(defn, circuit):
    return digest("f8n/experiment-core/1", experiment_core_canonical(defn, circuit))


def run_canonical_payload(status, engine_status, result_payload, measurements):
    # Measurement encoding is the document form (_measurement_doc), so the
    # digest recomputed at load over stored documents matches exactly.
    return {
        "engine_status": engine_status,
        "measurements": [_measurement_doc(m) for m in measurements],
        "result": canonical(result_payload),
        "status": status,
    }


def run_digest(experiment_core_digest_str, status, engine_status,
               result_payload, measurements):
    return digest("f8n/run/1", {
        "experiment_core": experiment_core_digest_str,
        "run": run_canonical_payload(status, engine_status, result_payload,
                                     measurements),
    })


# ---------------------------------------------------------------------------
# CSV export (deterministic, unit-aware; produced as str, no file I/O)
# ---------------------------------------------------------------------------

def _csv_field(text):
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def waveform_csv(name, wave):
    lines = [f"t[s],{_csv_field(str(name))}[{_csv_field(wave.unit_label)}]"]
    for t, v in zip(wave.times, wave.values):
        lines.append(f"{decimal_string(t)},{decimal_string(v)}")
    return "\n".join(lines) + "\n"


def table_csv(table):
    lines = ["key,value,unit,status,reason"]
    for row in table.rows:
        if row.value is None:
            val, unit = "", ""
        else:
            val = decimal_string(row.value.value)
            unit = row.value.unit_label
        lines.append(",".join(_csv_field(e) for e in
                              (row.key, val, unit, row.status, row.reason)))
    return "\n".join(lines) + "\n"


def sweep_csv(name, sweep):
    lines = [f"axis[{_csv_field(sweep.axis_label)}],"
             f"{_csv_field(str(name))}[{_csv_field(sweep.unit_label)}],status"]
    for ax, val, st in zip(sweep.axis, sweep.values, sweep.statuses):
        ax_s = decimal_string(ax) if isinstance(ax, Decimal) else str(ax)
        if val is None:
            val_s = ""
        elif isinstance(val, Decimal):
            val_s = decimal_string(val)
        else:
            val_s = str(val)
        lines.append(",".join(_csv_field(e) for e in (ax_s, val_s, str(st))))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Session / run documents
# ---------------------------------------------------------------------------

def _scalar_doc(scalar):
    if scalar is None:
        return None
    if isinstance(scalar, Scalar):
        return {"d": list(scalar.dimension), "source": scalar.source,
                "unit": scalar.unit_label, "v": decimal_string(scalar.value)}
    if isinstance(scalar, ComplexScalar):
        return {"d": list(scalar.dimension),
                "frequency_hz": decimal_string(scalar.frequency_hz),
                "source": scalar.source, "unit": scalar.unit_label,
                "value": canonical(scalar.value)}
    _fail(f"bad scalar payload {type(scalar).__name__}")


def _reading_doc(reading):
    data = reading.data
    if data is None:
        payload = None
    elif isinstance(data, (Scalar, ComplexScalar)):
        payload = {"type": "scalar", "value": _scalar_doc(data)}
    elif isinstance(data, Waveform):
        payload = {"type": "waveform",
                   "times": [decimal_string(t) for t in data.times],
                   "values": [decimal_string(v) for v in data.values],
                   "d": list(data.dimension), "unit": data.unit_label,
                   "source": data.source}
    elif isinstance(data, ScopeData):
        chans = []
        for ch in data.channels:
            chans.append({"probe": ch.probe_key,
                          "times": [decimal_string(t) for t in ch.times],
                          "raw": [decimal_string(v) for v in ch.raw],
                          "coupled": [decimal_string(v) for v in ch.coupled],
                          "y_div": [decimal_string(v) for v in ch.y_div],
                          "clipped": list(ch.clipped),
                          "unit": ch.unit_label})
        payload = {"type": "scope", "channels": chans,
                   "window": [decimal_string(data.window[0]),
                              decimal_string(data.window[1])],
                   "trigger_time": decimal_string(data.trigger_time)
                   if data.trigger_time is not None else None,
                   "vertical_divisions": data.vertical_divisions}
    elif isinstance(data, BodeData):
        payload = {"type": "bode",
                   "points": [{"f_hz": decimal_string(p.frequency_hz),
                               "db": decimal_string(p.db) if p.db is not None else None,
                               "wrapped_rad": decimal_string(p.wrapped_rad)
                               if p.wrapped_rad is not None else None,
                               "unwrapped_rad": decimal_string(p.unwrapped_rad)
                               if p.unwrapped_rad is not None else None,
                               "status": p.status} for p in data.points],
                   "bandwidth_lo_hz": decimal_string(data.bandwidth_lo_hz)
                   if data.bandwidth_lo_hz is not None else None,
                   "bandwidth_hi_hz": decimal_string(data.bandwidth_hi_hz)
                   if data.bandwidth_hi_hz is not None else None,
                   "bandwidth_threshold_db": decimal_string(data.bandwidth_threshold_db)
                   if data.bandwidth_threshold_db is not None else None,
                   "source": data.source}
    elif isinstance(data, SweepData):
        axis = []
        for a in data.axis:
            axis.append(decimal_string(a) if isinstance(a, Decimal) else str(a))
        values = []
        for v in data.values:
            if v is None:
                values.append(None)
            elif isinstance(v, Decimal):
                values.append(decimal_string(v))
            else:
                values.append(str(v))
        payload = {"type": "sweep",
                   "axis": axis, "values": values,
                   "statuses": list(data.statuses),
                   "axis_label": data.axis_label, "unit": data.unit_label,
                   "source": data.source,
                   "extra": [[k, str(v)] for k, v in data.extra]}
    else:
        _fail(f"bad reading payload {type(data).__name__}")
    return {"key": reading.key, "kind": reading.kind, "status": reading.status,
            "reason": reading.reason, "data": payload}


def _measurement_doc(m):
    return {"key": m.key, "status": m.status, "reason": m.reason,
            "value": _scalar_doc(m.value)}


def _annotation_doc(record):
    return {"run_id": record.run_id, "index": record.index,
            "text": record.annotation.text,
            "refs": [[k, _scalar_doc(v)] for k, v in record.annotation.refs]}


def experiment_document(defn, circuit):
    digest_str = experiment_digest(defn, circuit)
    return {
        "experiment_digest": digest_str,
        "experiment_id": "exp-" + digest_str[:16],
        "label": defn.label,
        "definition": {
            "analysis": canonical_analysis(defn.analysis),
            "instruments": [[k, canonical(v)] for k, v in defn.instruments],
            "label": defn.label,
            "measurements": [[k, canonical(v)] for k, v in defn.measurements],
            "overrides": [[addr.key, decimal_string(val)]
                          for addr, val in defn.overrides],
            "probes": [[k, canonical_probe(v)] for k, v in defn.probes],
            "seed": defn.seed,
            "stimuli": [canonical(s) for s in defn.stimuli],
        },
    }


def run_document(run, result_payload):
    return {
        "analysis_kind": run.analysis_kind,
        "diagnostics": list(run.diagnostics),
        "engine_status": run.engine_status,
        "experiment_digest": run.experiment_digest,
        "experiment_id": run.experiment_id,
        "measurements": [_measurement_doc(m) for m in run.measurements],
        "provenance": canonical(run.provenance),
        "readings": [_reading_doc(r) for r in run.readings],
        "result": canonical(result_payload),
        "result_digest": run.result_digest,
        "run_id": run.run_id,
        "seed": run.seed,
        "session_id": run.session_id,
        "status": run.status,
    }


def to_document(session, result_payloads):
    """Canonical session document (the session *is* its own snapshot value).

    ``result_payloads`` maps ``run_id`` -> engine ``to_dict()`` payload.
    Raises ``LabConfigError(SERIALIZATION_TOO_LARGE)`` past the budget.
    """
    exp_docs = [experiment_document(defn, session.circuit)
                for defn in session.experiments]
    records = []
    for record in session.records:
        runs = []
        for run in record.runs:
            if run.run_id not in result_payloads:
                raise LabConfigError(INVALID_SERIALIZATION,
                                     f"missing result payload for {run.run_id}")
            runs.append(run_document(run, result_payloads[run.run_id]))
        records.append({"experiment_id": record.experiment_id, "runs": runs,
                        "annotations": [_annotation_doc(a)
                                        for a in record.annotations]})
    doc = {"schema": SCHEMA, "session_id": session.session_id,
           "circuit": canonical_circuit(session.circuit),
           "experiments": exp_docs,
           "records": records,
           "metadata": [[k, v] for k, v in session.metadata],
           "state": session.state}
    if len(dumps_canonical(doc).encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise LabConfigError(SERIALIZATION_TOO_LARGE,
                             "session document exceeds 64 MiB")
    return doc


def dumps_session(session, result_payloads):
    return dumps_canonical(to_document(session, result_payloads))


# ---------------------------------------------------------------------------
# Loading (allowlisted constructors only)
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class LoadResult:
    status: str
    session: object = None
    detail: str = ""


_BASE_UNITS = ("V", "A", "ohm", "S", "F", "H", "s", "Hz", "W", "C", "J",
               "N", "T", "Wb", "K", "mol", "cd", "1")


def _unit_for_dim(dim):
    """Base unit for a dimension tuple (display units never preserved)."""
    from academic_core.domain.engineering.units import Unit, parse_unit
    for symbol in _BASE_UNITS:
        try:
            unit = parse_unit(symbol)
        except Exception:
            continue
        if list(unit.dimension) == dim:
            return unit
    # Dimensions with no parseable base symbol (device-model registry):
    # construct exact base units (factor 1; stored values are base).
    from academic_core.domain.engineering.mna.analysis import KP_DIM, LAMBDA_DIM
    extra = {tuple(KP_DIM): ("A/V2", "A"), tuple(LAMBDA_DIM): ("1/V", "V")}
    if tuple(dim) in extra:
        symbol, base = extra[tuple(dim)]
        return Unit(symbol, base, "", tuple(dim), Decimal(1))
    return None


def base_quantity(quantity):
    """Display-canonical form of a Quantity (base value, base unit).

    Engine digests are display-unit sensitive while lab serialization
    keeps base units only; the execution snapshot is therefore
    normalized so save/load round trips stay bit-identical.
    """
    from academic_core.domain.engineering.units import Quantity as _Q
    unit = _unit_for_dim(list(quantity.dimension))
    if unit is None:
        _fail(f"dimension {list(quantity.dimension)!r} has no base unit")
    return _Q(quantity.to_base(), unit)


def normalize_circuit(circuit):
    """Display-canonical circuit copy (values/params/waves in base units).

    Numbers are untouched (base values); only display units are
    normalized. Never mutates the input.
    """
    from academic_core.domain.engineering.circuit import Circuit, Component
    from academic_core.domain.engineering.units import Quantity as _Q
    out = Circuit(name=circuit.name)
    for comp in circuit.components:
        value = base_quantity(comp.value) if comp.value is not None else None
        params = {}
        for key, val in (comp.parameters or {}).items():
            if key == "wave" and isinstance(val, dict):
                wave = dict(val)
                for lkey in ("v1", "v2", "vo", "va"):
                    if lkey in wave and isinstance(wave[lkey], _Q):
                        wave[lkey] = base_quantity(wave[lkey])
                params[key] = wave
            elif isinstance(val, _Q):
                params[key] = base_quantity(val)
            else:
                params[key] = val
        out.add(Component(comp.ref, comp.type, value, dict(comp.pins),
                          params, dict(comp.metadata)))
    return out


def _quantity_from_doc(node):
    from academic_core.domain.engineering.units import Quantity as _Q
    if not isinstance(node, dict) or set(node) != {"d", "v"}:
        _fail(f"bad Quantity node {node!r}")
    dim = node["d"]
    if not isinstance(dim, list) or len(dim) != 7 \
            or not all(isinstance(e, int) and not isinstance(e, bool) for e in dim):
        _fail(f"bad dimension {dim!r}")
    try:
        value = Decimal(str(node["v"]))
    except Exception:
        _fail(f"bad decimal {node['v']!r}")
    if not value.is_finite():
        _fail("non-finite Quantity")
    unit = _unit_for_dim(dim)
    if unit is None:
        _fail(f"dimension {dim!r} has no base unit")
    return _Q(value, unit)


def _decimal_from_doc(node):
    if isinstance(node, bool):
        _fail(f"bad decimal {node!r}")
    try:
        d = Decimal(str(node)) if not isinstance(node, Decimal) else node
    except Exception:
        _fail(f"bad decimal {node!r}")
    if not d.is_finite():
        _fail(f"non-finite decimal {node!r}")
    return d


def _circuit_from_doc(node):
    from academic_core.domain.engineering.circuit import Circuit, Component
    if not isinstance(node, dict) or set(node) != {"components", "name", "nets"}:
        _fail("bad circuit node")
    circuit = Circuit(str(node["name"]))
    for entry in node["components"]:
        if not isinstance(entry, dict) \
                or set(entry) != {"parameters", "pins", "ref", "type", "value"}:
            _fail("bad component node")
        value = _quantity_from_doc(entry["value"]) if entry["value"] is not None else None
        pins = {str(k): str(v) for k, v in entry["pins"]}
        params = _parameters_from_doc(str(entry["ref"]), str(entry["type"]),
                                      entry["parameters"])
        circuit.add(Component(str(entry["ref"]), str(entry["type"]), value, pins,
                              params, {}))
    return circuit


def _parameters_from_doc(ref, type_letter, node):
    if not isinstance(node, dict):
        _fail(f"{ref}: bad parameters node")
    t = type_letter.upper()
    if t in ("R", "C", "L", "T", "O"):
        if node:
            _fail(f"{ref}: type {t} takes no parameters")
        return {}
    if t in ("V", "I"):
        out = {}
        for key, val in node.items():
            if key == "wave":
                out[key] = _wave_from_doc(ref, val)
            elif key == "phase_unit":
                out[key] = str(val)
            elif key == "ac":
                out[key] = val if isinstance(val, bool) else _scalarish(val)
            elif key in ("ac_mag", "ac_phase", "phase"):
                out[key] = _scalarish(val)
            else:
                _fail(f"{ref}: unknown V/I parameter {key!r}")
        from academic_core.domain.engineering.circuit import Component
        pins = {"+": "x", "-": "y"}
        canonical_parameters(Component(ref, t, None, pins, out, {}))
        return out
    if t in ("D", "Q", "M", "J"):
        out = {}
        for key, val in node.items():
            if key in ("kind", "polarity"):
                out[key] = str(val)
            else:
                out[key] = _quantity_from_doc(val)
        return out
    if t in ("E", "G", "H", "F"):
        return {str(k): str(v) for k, v in node.items()}
    _fail(f"{ref}: unknown component type {t!r}")


def _scalarish(node):
    if isinstance(node, bool):
        _fail("bad scalar node")
    if isinstance(node, int):
        return node
    if isinstance(node, str):
        try:
            return Decimal(node)
        except Exception:
            return node
    if isinstance(node, dict) and set(node) == {"d", "v"}:
        return _quantity_from_doc(node)
    _fail(f"bad scalar node {node!r}")


def _wave_from_doc(ref, node):
    if not isinstance(node, dict) or "type" not in node:
        _fail(f"{ref}: bad wave node")
    wtype = node["type"]
    if wtype not in _WAVE_KEYS:
        _fail(f"{ref}: bad wave type {wtype!r}")
    out = {"type": wtype}
    for key, val in node.items():
        if key == "type":
            continue
        if key in ("v1", "v2", "vo", "va"):
            out[key] = _quantity_from_doc(val)
        else:
            out[key] = _decimal_from_doc(val)
    if set(out) != _WAVE_KEYS[wtype] | {"type"}:
        _fail(f"{ref}: wave {wtype!r} has wrong keys")
    return out


def _addr_from_key(key):
    from academic_core.domain.engineering.mna.analysis import ParamAddress
    if not isinstance(key, str) or "." not in key:
        _fail(f"bad parameter key {key!r}")
    ref, _, fld = key.partition(".")
    return ParamAddress(ref, fld)


def _grid_from_doc(node):
    from academic_core.domain.engineering.mna.analysis import GridSpec
    kind = node.get("kind")
    if kind == "linear":
        return GridSpec.linear(_decimal_from_doc(node["start"]),
                               _decimal_from_doc(node["stop"]),
                               _decimal_from_doc(node["step"]))
    if kind == "log":
        return GridSpec.log(_decimal_from_doc(node["start"]),
                            _decimal_from_doc(node["stop"]), int(node["n"]))
    if kind == "list":
        return GridSpec.from_list(tuple(_decimal_from_doc(v) for v in node["values"]))
    _fail(f"bad grid {node!r}")


def _dist_from_doc(node):
    from academic_core.domain.engineering.mna.analysis import NormalDist, UniformDist
    if not isinstance(node, dict):
        _fail(f"bad distribution {node!r}")
    if set(node) == {"low", "high"}:
        return UniformDist(_decimal_from_doc(node["low"]),
                           _decimal_from_doc(node["high"]))
    if set(node) == {"mean", "std", "min", "max"}:
        return NormalDist(_decimal_from_doc(node["mean"]),
                          _decimal_from_doc(node["std"]),
                          _decimal_from_doc(node["min"]),
                          _decimal_from_doc(node["max"]))
    if len(node) == 1:
        (name, payload), = list(node.items())
        if name == "UniformDist":
            return UniformDist(_decimal_from_doc(payload["low"]),
                               _decimal_from_doc(payload["high"]))
        if name == "NormalDist":
            return NormalDist(_decimal_from_doc(payload["mean"]),
                              _decimal_from_doc(payload["std"]),
                              _decimal_from_doc(payload["min"]),
                              _decimal_from_doc(payload["max"]))
    _fail(f"bad distribution {node!r}")


def _observable_from_doc(node):
    from academic_core.domain.engineering.mna.analysis import ObservableSpec
    return ObservableSpec(str(node["kind"]), str(node["locator"]))


def _target_addr(node):
    if isinstance(node, dict):
        return _addr_from_key(str(node["ref"]) + "." + str(node["field"]))
    return _addr_from_key(str(node))


def _addr_list(nodes):
    out = []
    for a in nodes:
        if isinstance(a, str):
            out.append(_addr_from_key(a))
        else:
            out.append(_addr_from_key(str(a["ref"]) + "." + str(a["field"])))
    return tuple(out)


def _analysis_from_doc(node):
    from academic_core.domain.engineering.mna.analysis import (
        MCConfig,
        ParamSweepConfig,
        SweepConfig,
        WorstCaseConfig,
    )
    from academic_core.domain.engineering.mna.sensitivity import (
        ACSensitivityConfig,
        SensitivityConfig,
    )
    from academic_core.domain.engineering.mna.transient import TransientConfig
    kind = node.get("kind")
    if kind == AnalysisKind.DC_SWEEP.value:
        cfg = node["config"]
        return AnalysisSpec(kind, sweep=SweepConfig(
            _target_addr(cfg["target"]), _grid_from_doc(cfg["grid"]),
            tuple(_observable_from_doc(o) for o in cfg["observables"]),
            bool(cfg.get("warm_start", False))))
    if kind == AnalysisKind.PARAM_SWEEP.value:
        cfg = node["config"]
        target = cfg.get("target")
        grid = cfg.get("grid")
        points = tuple(
            tuple((_addr_from_key(k), _decimal_from_doc(v)) for k, v in sorted(p.items()))
            for p in cfg.get("points", []))
        corners = tuple(tuple(e) for e in cfg.get("corners", []))
        return AnalysisSpec(kind, param_sweep=ParamSweepConfig(
            str(cfg["mode"]), _addr_from_key(target) if target else None,
            _grid_from_doc(grid) if grid else None, points, corners,
            tuple(_observable_from_doc(o) for o in cfg["observables"]),
            bool(cfg.get("warm_start", False))))
    if kind == AnalysisKind.CORNERS.value:
        cfg = node["config"]
        params = tuple((_target_addr(e[0]), _decimal_from_doc(e[1]),
                        _decimal_from_doc(e[2])) for e in cfg["parameters"])
        return AnalysisSpec(kind, corners=WorstCaseConfig(
            params, tuple(_observable_from_doc(o) for o in cfg["observables"]),
            bool(cfg.get("warm_start", False))))
    if kind == AnalysisKind.SENS_DC.value:
        cfg = node["config"]
        return AnalysisSpec(kind, sens=SensitivityConfig(
            _addr_list(cfg["parameters"]),
            tuple(_observable_from_doc(o) for o in cfg["observables"]),
            bool(cfg.get("normalized", False))))
    if kind == AnalysisKind.SENS_AC.value:
        cfg = node["config"]
        freq = cfg["frequency"]
        freq_q = _quantity_from_doc(freq) if isinstance(freq, dict) else str(freq)
        return AnalysisSpec(kind, sens_ac=ACSensitivityConfig(
            freq_q, _addr_list(cfg["parameters"]),
            tuple(_observable_from_doc(o) for o in cfg["observables"])))
    if kind == AnalysisKind.MONTE_CARLO.value:
        cfg = node["config"]
        dists = tuple((_target_addr(e[0]), _dist_from_doc(e[1]))
                      for e in cfg["distributions"])
        return AnalysisSpec(kind, mc=MCConfig(
            int(cfg["iterations"]), dists, None,
            tuple(_observable_from_doc(o) for o in cfg["observables"]),
            str(cfg.get("base", "dc-op"))))
    if kind == AnalysisKind.OP.value:
        return AnalysisSpec(kind)
    if kind == AnalysisKind.AC_POINT.value:
        return AnalysisSpec(kind, frequency=_quantity_from_doc(node["frequency"]))
    if kind == AnalysisKind.AC_SWEEP.value:
        freqs = tuple(_quantity_from_doc(f) for f in node["frequencies"])
        dbt = node.get("db_threshold")
        return AnalysisSpec(kind, frequencies=freqs,
                            input_source=str(node["input_source"]),
                            output_p=str(node["output_p"]),
                            output_n=str(node.get("output_n", "0")),
                            db_threshold=_decimal_from_doc(dbt)
                            if dbt is not None else None)
    if kind == AnalysisKind.TRANSIENT.value:
        cfg = node["config"]
        return AnalysisSpec(kind, transient=TransientConfig(
            str(cfg["method"]), _decimal_from_doc(cfg["tstop"]),
            _decimal_from_doc(cfg["h_init"]), _decimal_from_doc(cfg["h_min"]),
            _decimal_from_doc(cfg["h_max"]), _decimal_from_doc(cfg["reltol"]),
            _decimal_from_doc(cfg["abstol"]), bool(cfg.get("adaptive", True))))
    _fail(f"bad analysis {kind!r}")


def _probe_from_doc(node):
    _key, body = node[0], node[1]
    ptype, spec = body["type"], body["spec"]
    if ptype == "VoltageProbe":
        return VoltageProbe(str(spec["p"]), str(spec.get("n", "0")))
    if ptype == "CurrentProbe":
        return CurrentProbe(str(spec["branch"]))
    if ptype == "ParameterProbe":
        return ParameterProbe(str(spec["ref"]), str(spec["field"]))
    _fail(f"unknown probe type {ptype!r}")


def _stimulus_from_doc(node):
    kw = {}
    for key in ("value", "v1", "v2", "vo", "va", "magnitude"):
        if node.get(key) is not None:
            kw[key] = _quantity_from_doc(node[key])
    for key in ("t0", "td", "tr", "tf", "width", "period", "freq", "phase"):
        if node.get(key) is not None:
            kw[key] = _decimal_from_doc(node[key])
    if node.get("phase_unit") is not None:
        kw["phase_unit"] = str(node["phase_unit"])
    return StimulusSpec(str(node["source_ref"]), str(node["kind"]), **kw)


def _scope_channel_from_doc(node):
    return ScopeChannel(str(node["probe_key"]),
                        _decimal_from_doc(node.get("volts_per_div", "1")),
                        _decimal_from_doc(node.get("offset", "0")),
                        str(node.get("coupling", "DC")))


def _trigger_from_doc(node):
    return TriggerSpec(str(node["source_probe_key"]),
                       _decimal_from_doc(node.get("level", "0")),
                       str(node.get("slope", "rising")),
                       _decimal_from_doc(node.get("pre", "0")),
                       _decimal_from_doc(node.get("post", "0")),
                       _decimal_from_doc(node.get("hysteresis", "0")))


def _instrument_from_doc(node):
    kind = str(node["kind"])
    if kind in (InstrumentKind.VOLTMETER.value, InstrumentKind.AMMETER.value,
                InstrumentKind.SWEEP_VIEWER.value):
        at = node.get("at")
        return InstrumentSpec(kind, probe=str(node["probe"]),
                              at=_decimal_from_doc(at) if at is not None else None)
    if kind == InstrumentKind.OSCILLOSCOPE.value:
        window = node.get("window")
        trig = node.get("trigger")
        return InstrumentSpec(
            kind,
            channels=tuple(_scope_channel_from_doc(c) for c in node.get("channels", [])),
            window=(_decimal_from_doc(window[0]), _decimal_from_doc(window[1]))
            if window is not None else None,
            trigger=_trigger_from_doc(trig) if trig is not None else None,
            sample_count=int(node.get("sample_count", 1001)))
    if kind == InstrumentKind.FREQUENCY_RESPONSE.value:
        return InstrumentSpec(kind)
    _fail(f"unknown instrument {kind!r}")


def _measurement_from_doc(node):
    kw = {"kind": str(node["kind"]), "probe": str(node["probe"])}
    window = node.get("window")
    if window is not None:
        kw["window"] = (_decimal_from_doc(window[0]), _decimal_from_doc(window[1]))
    for key in ("level", "low_frac", "high_frac", "v_low", "v_high",
                "v_initial", "v_final", "tol", "abs_band", "db_threshold",
                "hysteresis"):
        if node.get(key) is not None:
            kw[key] = _decimal_from_doc(node[key])
    if node.get("slope") is not None:
        kw["slope"] = str(node["slope"])
    if node.get("basis") is not None:
        kw["basis"] = str(node["basis"])
    if node.get("auto_levels") is not None:
        kw["auto_levels"] = bool(node["auto_levels"])
    return MeasurementSpec(**kw)


def _scalar_from_doc(node):
    if node is None:
        return None
    if not isinstance(node, dict):
        _fail("bad scalar node")
    dim = tuple(node["d"]) if isinstance(node.get("d"), list) else None
    if dim is None or len(dim) != 7:
        _fail("bad scalar dimension")
    if set(node) == {"d", "source", "unit", "v"}:
        return Scalar(_decimal_from_doc(node["v"]), dim, str(node["unit"]),
                      str(node.get("source", "")))
    if set(node) == {"d", "frequency_hz", "source", "unit", "value"}:
        raw = node["value"]
        z = DecimalComplex(_decimal_from_doc(raw["re"]), _decimal_from_doc(raw["im"]))
        return ComplexScalar(z, dim, str(node["unit"]),
                             _decimal_from_doc(node["frequency_hz"]),
                             str(node.get("source", "")))
    _fail("bad scalar node")


def _reading_from_doc(node):
    payload = node.get("data")
    data = None
    if payload is not None:
        ptype = payload.get("type")
        if ptype == "scalar":
            data = _scalar_from_doc(payload["value"])
        elif ptype == "waveform":
            data = Waveform(tuple(_decimal_from_doc(t) for t in payload["times"]),
                            tuple(_decimal_from_doc(v) for v in payload["values"]),
                            tuple(payload["d"]), str(payload.get("unit", "")),
                            str(payload.get("source", "")))
        elif ptype == "scope":
            chans = []
            for ch in payload["channels"]:
                chans.append(ScopeChannelData(
                    str(ch["probe"]),
                    tuple(_decimal_from_doc(t) for t in ch["times"]),
                    tuple(_decimal_from_doc(v) for v in ch["raw"]),
                    tuple(_decimal_from_doc(v) for v in ch["coupled"]),
                    tuple(_decimal_from_doc(v) for v in ch["y_div"]),
                    tuple(bool(c) for c in ch["clipped"]), str(ch.get("unit", ""))))
            window = (_decimal_from_doc(payload["window"][0]),
                      _decimal_from_doc(payload["window"][1]))
            trig = payload.get("trigger_time")
            data = ScopeData(tuple(chans), window,
                             _decimal_from_doc(trig) if trig is not None else None,
                             int(payload.get("vertical_divisions", 8)))
        elif ptype == "bode":
            pts = []
            for p in payload["points"]:
                pts.append(BodePointData(
                    _decimal_from_doc(p["f_hz"]),
                    _decimal_from_doc(p["db"]) if p["db"] is not None else None,
                    _decimal_from_doc(p["wrapped_rad"])
                    if p["wrapped_rad"] is not None else None,
                    _decimal_from_doc(p["unwrapped_rad"])
                    if p["unwrapped_rad"] is not None else None,
                    str(p.get("status", ""))))
            lo = payload.get("bandwidth_lo_hz")
            hi = payload.get("bandwidth_hi_hz")
            th = payload.get("bandwidth_threshold_db")
            data = BodeData(tuple(pts),
                            _decimal_from_doc(lo) if lo is not None else None,
                            _decimal_from_doc(hi) if hi is not None else None,
                            _decimal_from_doc(th) if th is not None else None,
                            str(payload.get("source", "")))
        elif ptype == "sweep":
            axis = [(_decimal_from_doc(a) if _is_decimal_str(a) else str(a))
                    for a in payload["axis"]]
            values = []
            for v in payload["values"]:
                if v is None:
                    values.append(None)
                elif _is_decimal_str(v):
                    values.append(_decimal_from_doc(v))
                else:
                    values.append(str(v))
            data = SweepData(tuple(axis), tuple(values), tuple(payload["statuses"]),
                             str(payload.get("axis_label", "")),
                             str(payload.get("unit", "")),
                             str(payload.get("source", "")),
                             tuple((str(k), str(v)) for k, v in payload.get("extra", [])))
        else:
            _fail(f"unknown reading payload {ptype!r}")
    return InstrumentReading(str(node["key"]), str(node["kind"]), str(node["status"]),
                             str(node.get("reason", "")), data)


def _is_decimal_str(text):
    if not isinstance(text, str) or not text:
        return False
    try:
        d = Decimal(text)
    except Exception:
        return False
    return d.is_finite()


def _definition_from_doc(node):
    entry = node["definition"]
    seed = entry.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        _fail("bad seed")
    return ExperimentDefinition(
        label=str(entry.get("label", "")),
        analysis=_analysis_from_doc(entry["analysis"]),
        overrides=tuple((_addr_from_key(k), _decimal_from_doc(v))
                        for k, v in entry.get("overrides", [])),
        stimuli=tuple(_stimulus_from_doc(s) for s in entry.get("stimuli", [])),
        probes=tuple((str(pair[0]), _probe_from_doc(pair))
                     for pair in entry.get("probes", [])),
        instruments=tuple((str(pair[0]), _instrument_from_doc(pair[1]))
                          for pair in entry.get("instruments", [])),
        measurements=tuple((str(pair[0]), _measurement_from_doc(pair[1]))
                           for pair in entry.get("measurements", [])),
        seed=seed)


def _run_from_doc(node):
    from .model import MeasurementStatus
    measurements = []
    for m in node.get("measurements", []):
        status = str(m["status"])
        try:
            MeasurementStatus(status)
        except ValueError:
            _fail(f"unknown measurement status {status!r}")
        measurements.append(MeasurementResult(str(node["run_id"]), str(m["key"]),
                                              _scalar_from_doc(m["value"]),
                                              status, str(m.get("reason", ""))))
    readings = [_reading_from_doc(r) for r in node.get("readings", [])]
    return Run(str(node["run_id"]), str(node["experiment_id"]),
               str(node.get("session_id", "")), str(node["experiment_digest"]),
               str(node["analysis_kind"]),
               node.get("seed"), str(node["status"]),
               node.get("engine_status"), None, tuple(measurements),
               tuple(readings), tuple(str(d) for d in node.get("diagnostics", [])),
               dict(node.get("provenance", {})), str(node["result_digest"]))


def from_document(doc):
    """Rebuild a session from a canonical document (tamper-checked).

    Load recomputes experiment ids/digests and rejects a document whose
    stored digests disagree (tamper/corruption = INVALID_SERIALIZATION).
    Engine results are NOT reconstructed (``Run.result`` is None); replay
    re-executes deterministically.
    """
    try:
        if not isinstance(doc, dict):
            return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                              "document must be a mapping")
        if doc.get("schema") != SCHEMA:
            return LoadResult(LoadStatus.SCHEMA_MISMATCH.value, None,
                              f"schema must be {SCHEMA}, got {doc.get('schema')!r}")
        circuit = _circuit_from_doc(doc["circuit"])
        experiments = []
        for entry in doc.get("experiments", []):
            defn = _definition_from_doc(entry)
            digest_str = experiment_digest(defn, circuit)
            if digest_str != entry.get("experiment_digest") or \
                    "exp-" + digest_str[:16] != entry.get("experiment_id"):
                return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                                  "experiment digest mismatch (tampered or corrupt)")
            experiments.append(defn)
        by_id = {}
        for defn in experiments:
            by_id[experiment_id(defn, circuit)] = defn
        records = []
        for entry in doc.get("records", []):
            exp_id = str(entry.get("experiment_id", ""))
            if exp_id not in by_id:
                return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                                  f"record for unknown experiment {exp_id!r}")
            runs = []
            for rnode in entry.get("runs", []):
                run = _run_from_doc(rnode)
                if run.experiment_id != exp_id:
                    return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                                      "run/experiment mismatch")
                expect_n = sum(1 for r in runs
                               if r.experiment_id == exp_id) + 1
                if run.run_id != f"{exp_id}#{expect_n}":
                    return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                                      f"run id sequence broken at {run.run_id!r}")
                core = experiment_core_digest(by_id[exp_id], circuit)
                recomputed = run_digest(core, run.status,
                                        run.engine_status, rnode.get("result"),
                                        run.measurements)
                if recomputed != run.result_digest:
                    return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                                      f"run digest mismatch at {run.run_id!r}")
                runs.append(run)
            annotations = []
            for anode in entry.get("annotations", []):
                refs = tuple((str(k), _scalar_from_doc(v)) for k, v in anode.get("refs", []))
                annotation = Annotation(str(anode.get("text", "")), refs)
                annotations.append(AnnotationRecord(str(anode.get("run_id", "")),
                                                    int(anode.get("index", 0)), annotation))
            records.append(ExperimentRecord(exp_id, tuple(runs), tuple(annotations)))
        session = LaboratorySession(
            str(doc.get("session_id", "")), circuit, tuple(experiments),
            tuple(records), tuple((str(k), str(v)) for k, v in doc.get("metadata", [])),
            str(doc.get("state", "OPEN")), str(doc.get("schema", SCHEMA)))
        return LoadResult(LoadStatus.OK.value, session, "")
    except LabConfigError as exc:
        if exc.code in (SCHEMA_MISMATCH,):
            return LoadResult(LoadStatus.SCHEMA_MISMATCH.value, None, exc.message)
        return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None, exc.message)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None, str(exc))


def loads_document(text):
    """Parse canonical JSON text with the size guard applied before parsing."""
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        return LoadResult(LoadStatus.SERIALIZATION_TOO_LARGE.value, None,
                          "document exceeds 64 MiB")
    try:
        doc = json.loads(text)
    except Exception as exc:
        return LoadResult(LoadStatus.INVALID_SERIALIZATION.value, None,
                          f"not JSON: {exc}")
    return from_document(doc)
