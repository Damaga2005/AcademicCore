"""F8-N Virtual Laboratory — core model (entities, enums, budgets, errors).

Orchestration layer over the certified engines (F8-H/I/J/K/L/M, F8-D5/D6).
Adds no solver, no device model, no waveform generator: every run is one
call of a certified entry point; instruments and measurements are pure
functions of run results.

Decimal only. No float, no I/O, no global state, no clock/uuid/random.
All Decimal arithmetic must run inside :func:`lab_context`.
"""
import copy
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from enum import Enum

from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    CAPACITANCE,
    CURRENT,
    DIMENSIONLESS,
    FREQUENCY,
    INDUCTANCE,
    POWER,
    RESISTANCE,
    TIME,
    VOLTAGE,
)

# ---------------------------------------------------------------------------
# Identity / versioning
# ---------------------------------------------------------------------------

#: Canonical schema tag for every F8-N document.
SCHEMA = "f8n-lab/1"
#: Laboratory layer version stamp (recorded in provenance, gated on replay).
LAB_VERSION = "f8n-lab/1"

# ---------------------------------------------------------------------------
# Deterministic Decimal context
# ---------------------------------------------------------------------------


@contextmanager
def lab_context():
    """Run Decimal arithmetic under an explicit, fresh lab context.

    The context never depends on the ambient (thread-local) decimal
    context, so caller ``decimal.setcontext`` / locale changes cannot
    alter lab results (test N-090). Engines manage their own contexts
    and are always called *outside* this block.
    """
    with localcontext(make_context()) as ctx:
        yield ctx


# ---------------------------------------------------------------------------
# Resource budgets (engineering bounds, fixed constants)
# ---------------------------------------------------------------------------

#: Scope payload bound (presentation artefact, never the solver).
MAX_DISPLAY_SAMPLES = 10000
#: Conventional instrument size.
MAX_SCOPE_CHANNELS = 4
#: Bounds keeping ``to_document`` size predictable.
MAX_EXPERIMENTS_PER_SESSION = 256
#: Runs retain full results in memory (a transient run can hold 1e5
#: samples x nodes).
MAX_RUNS_PER_SESSION = 1024
#: Linear cost, bounded table size.
MAX_MEASUREMENTS_PER_EXPERIMENT = 64
MAX_PROBES_PER_EXPERIMENT = 64
#: Load parses the whole document in memory.
MAX_SERIALIZED_BYTES = 64 * 1024 * 1024

#: Session-id charset (caller-supplied; the lab never generates ids).
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
#: Display label bound (labels are never digested).
MAX_LABEL_LEN = 128
#: Annotation text bound (annotations are never digested).
MAX_NOTE_LEN = 4096

# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

INVALID_PROBE = "INVALID_PROBE"
INVALID_MEASUREMENT_SPEC = "INVALID_MEASUREMENT_SPEC"
INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
INVALID_STIMULUS = "INVALID_STIMULUS"
INVALID_CIRCUIT = "INVALID_CIRCUIT"
INVALID_SEED = "INVALID_SEED"
INVALID_ANALYSIS = "INVALID_ANALYSIS"
INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
SESSION_CLOSED = "SESSION_CLOSED"
DUPLICATE = "DUPLICATE"
UNKNOWN_EXPERIMENT = "UNKNOWN_EXPERIMENT"
UNKNOWN_RUN = "UNKNOWN_RUN"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
VERSION_MISMATCH = "VERSION_MISMATCH"
SERIALIZATION_TOO_LARGE = "SERIALIZATION_TOO_LARGE"


class LabConfigError(ValueError):
    """Typed lab configuration failure (constructors / closed session)."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Enumerations (closed vocabularies; every user selector is allowlisted)
# ---------------------------------------------------------------------------


class AnalysisKind(str, Enum):
    OP = "OP"
    DC_SWEEP = "DC_SWEEP"
    PARAM_SWEEP = "PARAM_SWEEP"
    CORNERS = "CORNERS"
    SENS_DC = "SENS_DC"
    SENS_AC = "SENS_AC"
    MONTE_CARLO = "MONTE_CARLO"
    AC_POINT = "AC_POINT"
    AC_SWEEP = "AC_SWEEP"
    TRANSIENT = "TRANSIENT"


class StimulusKind(str, Enum):
    DC = "DC"
    STEP = "STEP"
    PULSE = "PULSE"
    SINE = "SINE"
    AC = "AC"


class MeasurementKind(str, Enum):
    MAX = "max"
    MIN = "min"
    PP = "pp"
    MEAN = "mean"
    RMS = "rms"
    CROSSINGS = "crossings"
    PERIOD = "period"
    FREQUENCY = "frequency"
    RISE_TIME = "rise_time"
    FALL_TIME = "fall_time"
    OVERSHOOT = "overshoot_ratio"
    SETTLING_TIME = "settling_time"
    AC_GAIN = "ac_gain"
    AC_GAIN_DB = "ac_gain_db"
    AC_PHASE = "ac_phase"
    AC_AMPLITUDE = "ac_amplitude"
    BANDWIDTH = "bandwidth"
    DC_VALUE = "dc_value"


class InstrumentKind(str, Enum):
    VOLTMETER = "voltmeter"
    AMMETER = "ammeter"
    OSCILLOSCOPE = "oscilloscope"
    FREQUENCY_RESPONSE = "frequency_response_viewer"
    SWEEP_VIEWER = "sweep_viewer"


class Coupling(str, Enum):
    DC = "DC"
    AC = "AC"


class Slope(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    EITHER = "either"


class RunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    INVALID_CIRCUIT = "INVALID_CIRCUIT"
    UNSUPPORTED = "UNSUPPORTED"
    SOLVER_FAILURE = "SOLVER_FAILURE"


class MeasurementStatus(str, Enum):
    OK = "OK"
    UNDEFINED = "UNDEFINED"
    INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
    NO_DATA = "NO_DATA"


class InstrumentStatus(str, Enum):
    OK = "OK"
    UNSUPPORTED = "UNSUPPORTED"
    NO_TRIGGER = "NO_TRIGGER"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    NO_DATA = "NO_DATA"


class ReplayStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    RESULT_DIFFERS = "RESULT_DIFFERS"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    INVALID_SERIALIZATION = "INVALID_SERIALIZATION"


class LoadStatus(str, Enum):
    OK = "OK"
    INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    SERIALIZATION_TOO_LARGE = "SERIALIZATION_TOO_LARGE"


# Measurement kinds valid per signal domain.
WAVEFORM_MEASUREMENTS = frozenset({
    MeasurementKind.MAX, MeasurementKind.MIN, MeasurementKind.PP,
    MeasurementKind.MEAN, MeasurementKind.RMS, MeasurementKind.CROSSINGS,
    MeasurementKind.PERIOD, MeasurementKind.FREQUENCY,
    MeasurementKind.RISE_TIME, MeasurementKind.FALL_TIME,
    MeasurementKind.OVERSHOOT, MeasurementKind.SETTLING_TIME,
})
AC_MEASUREMENTS = frozenset({
    MeasurementKind.AC_GAIN, MeasurementKind.AC_GAIN_DB,
    MeasurementKind.AC_PHASE, MeasurementKind.AC_AMPLITUDE,
    MeasurementKind.BANDWIDTH,
})
DC_MEASUREMENTS = frozenset({MeasurementKind.DC_VALUE})

#: Analyses whose engine ignores time-domain waves (DC value only).
WAVE_IGNORING_ANALYSES = frozenset({
    AnalysisKind.OP, AnalysisKind.DC_SWEEP, AnalysisKind.PARAM_SWEEP,
    AnalysisKind.CORNERS, AnalysisKind.SENS_DC, AnalysisKind.SENS_AC,
    AnalysisKind.MONTE_CARLO,
})

#: Analyses producing committed transient samples.
TRANSIENT_ANALYSES = frozenset({AnalysisKind.TRANSIENT})
#: Analyses producing phasors.
AC_POINT_ANALYSES = frozenset({AnalysisKind.AC_POINT})
#: Analyses producing frequency sweeps.
AC_SWEEP_ANALYSES = frozenset({AnalysisKind.AC_SWEEP})
#: F8-M sweep-like analyses (per-point tables).
SWEEP_ANALYSES = frozenset({
    AnalysisKind.DC_SWEEP, AnalysisKind.PARAM_SWEEP, AnalysisKind.CORNERS,
    AnalysisKind.MONTE_CARLO, AnalysisKind.SENS_DC, AnalysisKind.SENS_AC,
})
#: DC-side analyses (nonlinear operating points / F8-M DC machinery).
DC_SIDE_ANALYSES = frozenset({
    AnalysisKind.OP, AnalysisKind.DC_SWEEP, AnalysisKind.PARAM_SWEEP,
    AnalysisKind.CORNERS, AnalysisKind.SENS_DC, AnalysisKind.MONTE_CARLO,
})

#: Component types that make a circuit nonlinear (no F8-D5 AC sweep engine).
NONLINEAR_TYPES = frozenset({"D", "Q", "M", "J"})

DIM_LABELS = {
    VOLTAGE: "V",
    CURRENT: "A",
    RESISTANCE: "ohm",
    ADMITTANCE: "S",
    CAPACITANCE: "F",
    INDUCTANCE: "H",
    POWER: "W",
    TIME: "s",
    FREQUENCY: "Hz",
    DIMENSIONLESS: "1",
}


def _req_str(name, value, bound=None):
    if not isinstance(value, str) or not value:
        raise LabConfigError(INVALID_PROBE, f"{name} must be a non-empty string")
    if bound is not None and len(value) > bound:
        raise LabConfigError(INVALID_PROBE, f"{name} exceeds {bound} characters")
    return value


# ---------------------------------------------------------------------------
# Data types (all Decimal; complex = certified DecimalComplex)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scalar:
    """Dimensional scalar readout (exact Decimal, dimension tuple + label)."""

    value: Decimal
    dimension: tuple
    unit_label: str
    source: str = ""

    def __post_init__(self):
        if isinstance(self.value, bool) or not isinstance(self.value, Decimal):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Scalar value must be Decimal")
        if not isinstance(self.dimension, tuple) or len(self.dimension) != 7:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Scalar dimension must be a 7-tuple")
        if not all(isinstance(e, int) for e in self.dimension):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Scalar dimension exponents must be ints")


@dataclass(frozen=True)
class ComplexScalar:
    """Peak phasor readout (``e^{+jwt}`` engine convention)."""

    value: object  # DecimalComplex (typed loosely to avoid import weight here)
    dimension: tuple
    unit_label: str
    frequency_hz: Decimal = Decimal(0)
    source: str = ""

    def __post_init__(self):
        from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
        if not isinstance(self.value, DecimalComplex):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "ComplexScalar value must be DecimalComplex")


@dataclass(frozen=True)
class Waveform:
    """Committed samples joined by straight segments (piecewise linear)."""

    times: tuple
    values: tuple
    dimension: tuple
    unit_label: str = ""
    source: str = ""
    interpolation: str = "piecewise-linear"

    def __post_init__(self):
        if len(self.times) != len(self.values):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform times/values length mismatch")
        if len(self.times) == 0:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform needs at least one sample")
        for t in self.times:
            if isinstance(t, bool) or not isinstance(t, Decimal):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform times must be Decimal")
        for v in self.values:
            if isinstance(v, bool) or not isinstance(v, Decimal):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform values must be Decimal")
        for a, b in zip(self.times, self.times[1:]):
            if b <= a:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform times must be strictly increasing")
        if self.interpolation != "piecewise-linear":
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "Waveform interpolation is always piecewise-linear")


@dataclass(frozen=True)
class ComplexResponse:
    """Per-frequency phasor list (failed points are None, never 0)."""

    frequencies: tuple
    values: tuple
    dimension: tuple
    unit_label: str = ""
    source: str = ""
    statuses: tuple = ()

    def __post_init__(self):
        if len(self.frequencies) != len(self.values):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "ComplexResponse length mismatch")


@dataclass(frozen=True)
class SweepTrace:
    """Per-point sweep table (failed points are None, never 0)."""

    axis: tuple
    values: tuple
    axis_label: str = ""
    dimension: tuple = DIMENSIONLESS
    unit_label: str = ""
    source: str = ""
    statuses: tuple = ()

    def __post_init__(self):
        if len(self.axis) != len(self.values):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "SweepTrace length mismatch")


@dataclass(frozen=True)
class MeasurementRow:
    key: str
    value: object  # Scalar | None
    status: str
    reason: str = ""


@dataclass(frozen=True)
class MeasurementTable:
    rows: tuple
    run_id: str = ""
    experiment_digest: str = ""


# ---------------------------------------------------------------------------
# Probes (immutable specs; evaluation lives in instruments.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoltageProbe:
    p: str
    n: str = "0"

    def __post_init__(self):
        _req_str("VoltageProbe.p", self.p)
        _req_str("VoltageProbe.n", self.n)
        if self.p == self.n:
            raise LabConfigError(INVALID_PROBE, "VoltageProbe needs two distinct nets")


@dataclass(frozen=True)
class CurrentProbe:
    branch: str

    def __post_init__(self):
        _req_str("CurrentProbe.branch", self.branch)


@dataclass(frozen=True)
class ParameterProbe:
    ref: str
    field: str

    def __post_init__(self):
        _req_str("ParameterProbe.ref", self.ref)
        _req_str("ParameterProbe.field", self.field)

    @property
    def address(self):
        from academic_core.domain.engineering.mna.analysis import ParamAddress
        return ParamAddress(self.ref, self.field)


# ---------------------------------------------------------------------------
# Stimulus specification (typed configuration -> existing wave dicts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StimulusSpec:
    """Typed stimulus translated into the certified ``parameters["wave"]``
    dict / ``value`` / AC phase parameters of a V/I source in the run copy.
    The certified ``_wave_value`` implementation is the only waveform
    generator."""

    source_ref: str
    kind: str  # StimulusKind value
    value: object = None  # Quantity | None (DC)
    v1: object = None  # Quantity | None (STEP/PULSE levels)
    v2: object = None
    vo: object = None  # Quantity | None (SINE offset/amplitude)
    va: object = None
    t0: object = None  # Decimal | None (STEP edge; seconds)
    td: object = None  # Decimal | None (PULSE/SINE delay/shift)
    tr: object = None  # Decimal | None (PULSE rise)
    tf: object = None  # Decimal | None (PULSE fall)
    width: object = None  # Decimal | None (PULSE width)
    period: object = None  # Decimal | None (PULSE period, 0 = one-shot)
    freq: object = None  # Decimal | None (SINE Hz)
    magnitude: object = None  # Quantity | None (AC peak)
    phase: object = None  # Decimal | None (AC phase angle)
    phase_unit: object = None  # str | None ("deg" | "rad")

    def __post_init__(self):
        from academic_core.domain.engineering.units import Quantity
        _req_str("StimulusSpec.source_ref", self.source_ref)
        try:
            kind = StimulusKind(self.kind)
        except ValueError:
            raise LabConfigError(INVALID_STIMULUS, f"unknown stimulus kind {self.kind!r}")

        def _qty(name, val, dim=None):
            if val is None:
                return None
            if not isinstance(val, Quantity):
                raise LabConfigError(INVALID_STIMULUS, f"{name} must be a Quantity")
            if dim is not None and val.dimension != dim:
                raise LabConfigError(INVALID_STIMULUS, f"{name} has wrong dimension")
            if not val.to_base().is_finite():
                raise LabConfigError(INVALID_STIMULUS, f"{name} is non-finite")
            return val

        def _time(name, val, allow_zero=True, positive=False):
            if val is None:
                return None
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise LabConfigError(INVALID_STIMULUS, f"{name} must be a Decimal (seconds)")
            if not val.is_finite():
                raise LabConfigError(INVALID_STIMULUS, f"{name} is non-finite")
            if positive and not val > 0:
                raise LabConfigError(INVALID_STIMULUS, f"{name} must be > 0")
            if not allow_zero and val == 0 and positive:
                raise LabConfigError(INVALID_STIMULUS, f"{name} must be > 0")
            if val < 0:
                raise LabConfigError(INVALID_STIMULUS, f"{name} must be >= 0")
            return val

        # Per-kind closed validation: exactly the documented fields.
        if kind == StimulusKind.DC:
            _qty("value", self.value)
            extra = (self.v1, self.v2, self.vo, self.va, self.t0, self.td,
                     self.tr, self.tf, self.width, self.period, self.freq,
                     self.magnitude, self.phase, self.phase_unit)
            if self.value is None or any(e is not None for e in extra):
                raise LabConfigError(INVALID_STIMULUS, "DC stimulus needs exactly 'value'")
        elif kind == StimulusKind.STEP:
            _qty("v1", self.v1)
            _qty("v2", self.v2)
            _time("t0", self.t0)
            if self.v1 is None or self.v2 is None or self.t0 is None:
                raise LabConfigError(INVALID_STIMULUS, "STEP stimulus needs v1, v2, t0")
            if self.v1.dimension != self.v2.dimension:
                raise LabConfigError(INVALID_STIMULUS, "STEP v1/v2 dimension mismatch")
            rest = (self.value, self.vo, self.va, self.td, self.tr, self.tf,
                    self.width, self.period, self.freq, self.magnitude,
                    self.phase, self.phase_unit)
            if any(e is not None for e in rest):
                raise LabConfigError(INVALID_STIMULUS, "STEP stimulus takes only v1, v2, t0")
        elif kind == StimulusKind.PULSE:
            _qty("v1", self.v1)
            _qty("v2", self.v2)
            _time("td", self.td)
            _time("tr", self.tr)
            _time("tf", self.tf)
            _time("width", self.width)
            _time("period", self.period)
            if self.v1 is None or self.v2 is None or self.td is None \
                    or self.tr is None or self.tf is None \
                    or self.width is None or self.period is None:
                raise LabConfigError(INVALID_STIMULUS,
                                     "PULSE stimulus needs v1, v2, td, tr, tf, width, period")
            if self.v1.dimension != self.v2.dimension:
                raise LabConfigError(INVALID_STIMULUS, "PULSE v1/v2 dimension mismatch")
            rest = (self.value, self.vo, self.va, self.t0, self.freq,
                    self.magnitude, self.phase, self.phase_unit)
            if any(e is not None for e in rest):
                raise LabConfigError(INVALID_STIMULUS, "PULSE stimulus takes only its pulse fields")
        elif kind == StimulusKind.SINE:
            _qty("vo", self.vo)
            _qty("va", self.va)
            _time("td", self.td)
            _time("freq", self.freq, positive=True)
            if self.vo is None or self.va is None or self.freq is None or self.td is None:
                raise LabConfigError(INVALID_STIMULUS, "SINE stimulus needs vo, va, freq, td")
            if self.vo.dimension != self.va.dimension:
                raise LabConfigError(INVALID_STIMULUS, "SINE vo/va dimension mismatch")
            rest = (self.value, self.v1, self.v2, self.t0, self.tr, self.tf,
                    self.width, self.period, self.magnitude, self.phase, self.phase_unit)
            if any(e is not None for e in rest):
                raise LabConfigError(INVALID_STIMULUS, "SINE stimulus takes only vo, va, freq, td")
        elif kind == StimulusKind.AC:
            _qty("magnitude", self.magnitude)
            if self.magnitude is None or self.phase is None or self.phase_unit is None:
                raise LabConfigError(INVALID_STIMULUS,
                                     "AC stimulus needs magnitude, phase, phase_unit")
            if isinstance(self.phase, bool) or not isinstance(self.phase, Decimal):
                raise LabConfigError(INVALID_STIMULUS, "AC phase must be a Decimal")
            if not self.phase.is_finite():
                raise LabConfigError(INVALID_STIMULUS, "AC phase is non-finite")
            if str(self.phase_unit).strip().lower() not in ("deg", "rad"):
                raise LabConfigError(INVALID_STIMULUS, "AC phase_unit must be 'deg' or 'rad'")
            rest = (self.value, self.v1, self.v2, self.vo, self.va, self.t0,
                    self.td, self.tr, self.tf, self.width, self.period, self.freq)
            if any(e is not None for e in rest):
                raise LabConfigError(INVALID_STIMULUS,
                                     "AC stimulus takes only magnitude, phase, phase_unit")


# ---------------------------------------------------------------------------
# Instrument + measurement specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeChannel:
    probe_key: str
    volts_per_div: Decimal = Decimal("1")
    offset: Decimal = Decimal("0")
    coupling: str = "DC"

    def __post_init__(self):
        _req_str("ScopeChannel.probe_key", self.probe_key)
        try:
            Coupling(self.coupling)
        except ValueError:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                 f"unknown coupling {self.coupling!r}")
        for name, val in (("volts_per_div", self.volts_per_div),
                            ("offset", self.offset)):
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} must be Decimal")
            if not val.is_finite():
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} is non-finite")
        if self.volts_per_div <= 0:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "volts_per_div must be > 0")


@dataclass(frozen=True)
class TriggerSpec:
    source_probe_key: str
    level: Decimal = Decimal("0")
    slope: str = "rising"
    pre: Decimal = Decimal("0")
    post: Decimal = Decimal("0")
    hysteresis: Decimal = Decimal("0")

    def __post_init__(self):
        _req_str("TriggerSpec.source_probe_key", self.source_probe_key)
        try:
            Slope(self.slope)
        except ValueError:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"unknown slope {self.slope!r}")
        for name, val in (("level", self.level), ("pre", self.pre),
                            ("post", self.post), ("hysteresis", self.hysteresis)):
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} must be Decimal")
            if not val.is_finite():
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} is non-finite")
        for name, val in (("pre", self.pre), ("post", self.post),
                          ("hysteresis", self.hysteresis)):
            if val < 0:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} must be >= 0")


@dataclass(frozen=True)
class InstrumentSpec:
    """Ideal instrument configuration (pure view; never solves)."""

    kind: str  # InstrumentKind value
    probe: object = None  # str | None (meter single probe / sweep viewer probe)
    channels: tuple = ()  # tuple[ScopeChannel] (oscilloscope)
    window: object = None  # tuple[Decimal, Decimal] | None (scope explicit window)
    trigger: object = None  # TriggerSpec | None (scope)
    sample_count: int = 1001
    at: object = None  # Decimal | None (meter transient reading time; None = final)

    def __post_init__(self):
        try:
            kind = InstrumentKind(self.kind)
        except ValueError:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"unknown instrument {self.kind!r}")
        if kind in (InstrumentKind.VOLTMETER, InstrumentKind.AMMETER,
                    InstrumentKind.SWEEP_VIEWER):
            if not isinstance(self.probe, str) or not self.probe:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     f"{self.kind} needs a probe key")
            if self.channels or self.window is not None or self.trigger is not None:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     f"{self.kind} takes only a probe key")
            if kind == InstrumentKind.SWEEP_VIEWER and self.at is not None:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "sweep viewer takes no 'at'")
            if self.at is not None and (
                    isinstance(self.at, bool) or not isinstance(self.at, Decimal)
                    or not self.at.is_finite()):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "'at' must be a finite Decimal (seconds)")
        elif kind == InstrumentKind.OSCILLOSCOPE:
            if self.probe is not None:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "oscilloscope takes channels, not a single probe")
            if not (1 <= len(self.channels) <= MAX_SCOPE_CHANNELS):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     f"oscilloscope needs 1..{MAX_SCOPE_CHANNELS} channels")
            if not all(isinstance(ch, ScopeChannel) for ch in self.channels):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "oscilloscope channels must be ScopeChannel")
            if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "sample_count must be int")
            if self.sample_count < 2:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "sample_count must be >= 2")
            if self.sample_count > MAX_DISPLAY_SAMPLES:
                raise LabConfigError(BUDGET_EXCEEDED,
                                     f"sample_count {self.sample_count} exceeds {MAX_DISPLAY_SAMPLES}")
            if self.window is not None:
                if not isinstance(self.window, tuple) or len(self.window) != 2:
                    raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                         "scope window must be (t_start, t_end)")
                a, b = self.window
                for v in (a, b):
                    if isinstance(v, bool) or not isinstance(v, Decimal) or not v.is_finite():
                        raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                             "scope window bounds must be finite Decimal")
                if not a < b:
                    raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                         "scope window needs t_start < t_end")
            if self.trigger is not None and not isinstance(self.trigger, TriggerSpec):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "trigger must be TriggerSpec")
            if self.trigger is None and self.window is None:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "oscilloscope needs a trigger or an explicit window")
        elif kind == InstrumentKind.FREQUENCY_RESPONSE:
            if self.probe is not None or self.channels or self.window is not None \
                    or self.trigger is not None or self.at is not None:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                     "frequency-response viewer takes no probe/channel config")


@dataclass(frozen=True)
class MeasurementSpec:
    """Declared measurement (pure function of a run result)."""

    kind: str  # MeasurementKind value
    probe: str = ""
    window: object = None  # tuple[Decimal, Decimal] | None
    level: object = None  # Decimal | None (crossings)
    slope: object = None  # str | None
    hysteresis: object = None  # Decimal | None
    low_frac: object = None  # Decimal | None (rise/fall)
    high_frac: object = None
    v_low: object = None  # Decimal | None (rise/fall levels)
    v_high: object = None
    auto_levels: bool = False
    v_initial: object = None  # Decimal | None (overshoot/settling refs)
    v_final: object = None
    tol: object = None  # Decimal | None (settling relative tolerance)
    abs_band: object = None  # Decimal | None (settling absolute band)
    basis: object = None  # str | None ("peak" | "rms")
    db_threshold: object = None  # Decimal | None (bandwidth override)

    def __post_init__(self):
        try:
            MeasurementKind(self.kind)
        except ValueError:
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"unknown measurement {self.kind!r}")
        _req_str("MeasurementSpec.probe", self.probe)
        if not isinstance(self.auto_levels, bool):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "auto_levels must be bool")
        if self.window is not None:
            if not isinstance(self.window, tuple) or len(self.window) != 2:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, "window must be (a, b)")
            a, b = self.window
            for v in (a, b):
                if isinstance(v, bool) or not isinstance(v, Decimal) or not v.is_finite():
                    raise LabConfigError(INVALID_MEASUREMENT_SPEC,
                                         "window bounds must be finite Decimal")
        if self.slope is not None:
            try:
                Slope(self.slope)
            except ValueError:
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"unknown slope {self.slope!r}")
        for name, val in (("level", self.level), ("hysteresis", self.hysteresis),
                            ("low_frac", self.low_frac), ("high_frac", self.high_frac),
                            ("v_low", self.v_low), ("v_high", self.v_high),
                            ("v_initial", self.v_initial), ("v_final", self.v_final),
                            ("tol", self.tol), ("abs_band", self.abs_band),
                            ("db_threshold", self.db_threshold)):
            if val is not None and (isinstance(val, bool) or not isinstance(val, Decimal)
                                    or not val.is_finite()):
                raise LabConfigError(INVALID_MEASUREMENT_SPEC, f"{name} must be finite Decimal")
        if self.basis is not None and self.basis not in ("peak", "rms"):
            raise LabConfigError(INVALID_MEASUREMENT_SPEC, "basis must be 'peak' or 'rms'")


# ---------------------------------------------------------------------------
# Analysis specification (each wraps the certified config object)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisSpec:
    kind: str  # AnalysisKind value
    sweep: object = None  # SweepConfig (DC_SWEEP)
    param_sweep: object = None  # ParamSweepConfig (PARAM_SWEEP)
    corners: object = None  # WorstCaseConfig (CORNERS)
    sens: object = None  # SensitivityConfig (SENS_DC)
    sens_ac: object = None  # ACSensitivityConfig (SENS_AC)
    mc: object = None  # MCConfig with seed=None (MONTE_CARLO)
    frequency: object = None  # Quantity (AC_POINT, Hz)
    frequencies: tuple = ()  # tuple[Quantity] (AC_SWEEP)
    input_source: str = ""  # AC_SWEEP input source ref
    output_p: str = ""  # AC_SWEEP output nets (voltage_between)
    output_n: str = "0"
    db_threshold: object = None  # Decimal | None (AC_SWEEP)
    transient: object = None  # TransientConfig (TRANSIENT)

    def __post_init__(self):
        from academic_core.domain.engineering.units import Quantity
        try:
            kind = AnalysisKind(self.kind)
        except ValueError:
            raise LabConfigError(INVALID_ANALYSIS, f"unknown analysis {self.kind!r}")
        payload = {
            AnalysisKind.DC_SWEEP: self.sweep,
            AnalysisKind.PARAM_SWEEP: self.param_sweep,
            AnalysisKind.CORNERS: self.corners,
            AnalysisKind.SENS_DC: self.sens,
            AnalysisKind.SENS_AC: self.sens_ac,
            AnalysisKind.MONTE_CARLO: self.mc,
        }
        if kind in payload:
            if payload[kind] is None:
                raise LabConfigError(INVALID_ANALYSIS, f"{self.kind} needs its certified config")
            others = [self.sweep, self.param_sweep, self.corners, self.sens,
                      self.sens_ac, self.mc, self.transient]
            if any(o is not None for o in others if o is not payload[kind]):
                raise LabConfigError(INVALID_ANALYSIS, f"{self.kind} takes only its own config")
            if self.frequency is not None or self.frequencies or self.input_source \
                    or self.db_threshold is not None:
                raise LabConfigError(INVALID_ANALYSIS, f"{self.kind} takes only its own config")
            if kind == AnalysisKind.MONTE_CARLO and self.mc.seed is not None:
                raise LabConfigError(INVALID_SEED,
                                     "MONTE_CARLO config seed must be None (seed comes from the definition)")
            return
        if kind == AnalysisKind.OP:
            if any(o is not None for o in (self.sweep, self.param_sweep, self.corners,
                                           self.sens, self.sens_ac, self.mc, self.transient)):
                raise LabConfigError(INVALID_ANALYSIS, "OP takes no config")
            if self.frequency is not None or self.frequencies or self.input_source \
                    or self.db_threshold is not None:
                raise LabConfigError(INVALID_ANALYSIS, "OP takes no config")
            return
        if kind == AnalysisKind.AC_POINT:
            if self.frequency is None or not isinstance(self.frequency, Quantity):
                raise LabConfigError(INVALID_ANALYSIS, "AC_POINT needs a frequency Quantity")
            if self.frequency.dimension != FREQUENCY:
                raise LabConfigError(INVALID_ANALYSIS, "AC_POINT frequency has wrong dimension")
            if not self.frequency.to_base().is_finite() or not self.frequency.to_base() > 0:
                raise LabConfigError(INVALID_ANALYSIS, "AC_POINT frequency must be finite > 0")
            return
        if kind == AnalysisKind.AC_SWEEP:
            if not self.frequencies or not all(isinstance(f, Quantity) for f in self.frequencies):
                raise LabConfigError(INVALID_ANALYSIS, "AC_SWEEP needs a non-empty frequency tuple")
            for f in self.frequencies:
                if f.dimension != FREQUENCY or not f.to_base().is_finite() \
                        or not f.to_base() > 0:
                    raise LabConfigError(INVALID_ANALYSIS,
                                         "AC_SWEEP frequencies must be finite > 0 Hz")
            _req_str("AC_SWEEP.input_source", self.input_source)
            _req_str("AC_SWEEP.output_p", self.output_p)
            _req_str("AC_SWEEP.output_n", self.output_n)
            if self.db_threshold is not None and (
                    isinstance(self.db_threshold, bool)
                    or not isinstance(self.db_threshold, Decimal)):
                raise LabConfigError(INVALID_ANALYSIS, "db_threshold must be Decimal")
            return
        if kind == AnalysisKind.TRANSIENT:
            if self.transient is None:
                raise LabConfigError(INVALID_ANALYSIS, "TRANSIENT needs a TransientConfig")
            return


# ---------------------------------------------------------------------------
# Experiment definition (immutable, content-addressed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentDefinition:
    label: str = ""
    analysis: AnalysisSpec = None
    overrides: tuple = ()  # tuple[(ParamAddress, Decimal)] sorted by key
    stimuli: tuple = ()  # tuple[StimulusSpec] sorted by source_ref
    probes: tuple = ()  # tuple[(key, Probe)] sorted by key
    instruments: tuple = ()  # tuple[(key, InstrumentSpec)] sorted by key
    measurements: tuple = ()  # tuple[(key, MeasurementSpec)] sorted by key
    seed: object = None  # int | None

    def __post_init__(self):
        from decimal import Decimal as _D
        from academic_core.domain.engineering.mna.analysis import ParamAddress
        from academic_core.domain.engineering.units import Quantity
        if not isinstance(self.label, str):
            raise LabConfigError(INVALID_PROBE, "label must be str")
        if len(self.label) > MAX_LABEL_LEN:
            raise LabConfigError(INVALID_PROBE, "label exceeds 128 characters")
        if not isinstance(self.analysis, AnalysisSpec):
            raise LabConfigError(INVALID_ANALYSIS, "definition needs an AnalysisSpec")
        # Seed contract: required for Monte Carlo, forbidden otherwise.
        is_mc = self.analysis.kind == AnalysisKind.MONTE_CARLO.value
        if is_mc:
            if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
                raise LabConfigError(INVALID_SEED,
                                     "MONTE_CARLO needs an int seed >= 0 (no silent unused seed)")
        elif self.seed is not None:
            raise LabConfigError(INVALID_SEED,
                                 "seed is forbidden on deterministic analyses")
        # Overrides: (ParamAddress, Decimal|Quantity) -> stored base Decimal, sorted.
        norm_over = []
        for item in self.overrides:
            if not isinstance(item, tuple) or len(item) != 2:
                raise LabConfigError(INVALID_PROBE, "override must be (ParamAddress, value)")
            addr, val = item
            if not isinstance(addr, ParamAddress):
                raise LabConfigError(INVALID_PROBE, "override address must be a ParamAddress")
            if isinstance(val, Quantity):
                val = val.to_base()
            if isinstance(val, bool) or not isinstance(val, _D) or not val.is_finite():
                raise LabConfigError(INVALID_PROBE, "override value must be finite Decimal")
            norm_over.append((addr, val))
        norm_over.sort(key=lambda kv: kv[0].key)
        object.__setattr__(self, "overrides", tuple(norm_over))
        # Stimuli: at most one per source, sorted.
        if not all(isinstance(s, StimulusSpec) for s in self.stimuli):
            raise LabConfigError(INVALID_STIMULUS, "stimuli must be StimulusSpec")
        refs = [s.source_ref.upper() for s in self.stimuli]
        if len(set(refs)) != len(refs):
            raise LabConfigError(DUPLICATE, "at most one stimulus per source")
        object.__setattr__(self, "stimuli",
                           tuple(sorted(self.stimuli, key=lambda s: s.source_ref.upper())))
        # Probes / instruments / measurements: unique keys, sorted.
        for name, items, types in (
                ("probes", self.probes, (VoltageProbe, CurrentProbe, ParameterProbe)),
                ("instruments", self.instruments, (InstrumentSpec,)),
                ("measurements", self.measurements, (MeasurementSpec,))):
            norm = []
            for item in items:
                if not isinstance(item, tuple) or len(item) != 2:
                    raise LabConfigError(INVALID_PROBE, f"{name} entries must be (key, spec)")
                key, spec = item
                _req_str(f"{name} key", key, 64)
                if not isinstance(spec, types):
                    raise LabConfigError(INVALID_PROBE, f"{name}[{key!r}] has wrong spec type")
                norm.append((key, spec))
            keys = [k for k, _ in norm]
            if len(set(keys)) != len(keys):
                raise LabConfigError(DUPLICATE, f"duplicate {name} keys")
            object.__setattr__(self, name, tuple(sorted(norm, key=lambda kv: kv[0])))
        if len(self.probes) > MAX_PROBES_PER_EXPERIMENT:
            raise LabConfigError(BUDGET_EXCEEDED, "too many probes")
        if len(self.measurements) > MAX_MEASUREMENTS_PER_EXPERIMENT:
            raise LabConfigError(BUDGET_EXCEEDED, "too many measurements")


# ---------------------------------------------------------------------------
# Run / records / session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementResult:
    run_id: str
    key: str
    value: object  # Scalar | None (None with a status, never 0 for missing)
    status: str  # MeasurementStatus value
    reason: str = ""


@dataclass(frozen=True)
class InstrumentReading:
    key: str
    kind: str  # InstrumentKind value
    status: str  # InstrumentStatus value
    reason: str = ""
    data: object = None  # Scalar | ComplexScalar | Waveform | ScopeData | BodeData | SweepData


@dataclass(frozen=True)
class ScopeChannelData:
    probe_key: str
    times: tuple
    raw: tuple
    coupled: tuple
    y_div: tuple
    clipped: tuple
    unit_label: str = ""


@dataclass(frozen=True)
class ScopeData:
    channels: tuple  # tuple[ScopeChannelData]
    window: tuple  # (t_start, t_end)
    trigger_time: object = None  # Decimal | None
    vertical_divisions: int = 8


@dataclass(frozen=True)
class BodePointData:
    frequency_hz: Decimal
    db: object  # Decimal | None
    wrapped_rad: object  # Decimal | None
    unwrapped_rad: object  # Decimal | None
    status: str = ""


@dataclass(frozen=True)
class BodeData:
    points: tuple  # tuple[BodePointData]
    bandwidth_lo_hz: object = None  # Decimal | None (certified interval)
    bandwidth_hi_hz: object = None
    bandwidth_threshold_db: object = None
    source: str = ""


@dataclass(frozen=True)
class SweepData:
    axis: tuple
    values: tuple  # Decimal | None per point (None = failed, never 0)
    statuses: tuple = ()
    axis_label: str = ""
    unit_label: str = ""
    source: str = ""
    extra: tuple = ()  # tuple[(key, value-str)] sorted (statistics, honesty text...)


@dataclass(frozen=True)
class Run:
    run_id: str
    experiment_id: str
    session_id: str  # identity, never digested
    experiment_digest: str
    analysis_kind: str
    seed: object  # int | None
    status: str  # RunStatus value
    engine_status: object = None  # verbatim engine status string | None
    result: object = None  # certified engine result, wrapped unchanged
    measurements: tuple = ()
    readings: tuple = ()
    diagnostics: tuple = ()
    provenance: object = None  # dict (frozen at construction)
    result_digest: str = ""

    def __post_init__(self):
        object.__setattr__(self, "measurements", tuple(self.measurements))
        object.__setattr__(self, "readings", tuple(self.readings))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.provenance is None:
            object.__setattr__(self, "provenance", {})
        else:
            object.__setattr__(self, "provenance", dict(self.provenance))


@dataclass(frozen=True)
class Annotation:
    text: str
    refs: tuple = ()  # tuple[(key, Scalar)] reference values (never digested)

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise LabConfigError(INVALID_PROBE, "annotation text must be str")
        if len(self.text) > MAX_NOTE_LEN:
            raise LabConfigError(INVALID_PROBE, "annotation text exceeds 4096 characters")
        for item in self.refs:
            if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str) \
                    or not isinstance(item[1], Scalar):
                raise LabConfigError(INVALID_PROBE, "annotation refs must be (key, Scalar)")


@dataclass(frozen=True)
class AnnotationRecord:
    run_id: str
    index: int
    annotation: Annotation


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    runs: tuple = ()
    annotations: tuple = ()  # tuple[AnnotationRecord]


@dataclass(frozen=True)
class LaboratorySession:
    session_id: str
    circuit: object  # Circuit (deep copy at creation, never mutated after)
    experiments: tuple = ()
    records: tuple = ()
    metadata: tuple = ()  # tuple[(str, str)] sorted
    state: str = "OPEN"
    schema: str = SCHEMA

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not SESSION_ID_RE.fullmatch(self.session_id):
            raise LabConfigError(INVALID_CIRCUIT,
                                 "session_id must match ^[A-Za-z0-9_.-]{1,64}$")
        if self.state not in ("OPEN", "CLOSED"):
            raise LabConfigError(INVALID_CIRCUIT, "session state must be OPEN or CLOSED")
        if self.schema != SCHEMA:
            raise LabConfigError(SCHEMA_MISMATCH, f"schema must be {SCHEMA}")
        object.__setattr__(self, "experiments", tuple(self.experiments))
        object.__setattr__(self, "records", tuple(self.records))
        md = []
        for item in self.metadata:
            if not isinstance(item, tuple) or len(item) != 2 \
                    or not all(isinstance(e, str) for e in item):
                raise LabConfigError(INVALID_CIRCUIT, "metadata must be (str, str) pairs")
            md.append(item)
        md.sort()
        object.__setattr__(self, "metadata", tuple(md))


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: tuple = ()  # tuple[(code, message)]

    @staticmethod
    def valid():
        return ValidationReport(True, ())

    @staticmethod
    def invalid(errors):
        return ValidationReport(False, tuple(errors))


@dataclass(frozen=True)
class ReplayResult:
    run_id: str
    status: str  # ReplayStatus value
    comparable: bool = True
    expected_digest: str = ""
    actual_digest: str = ""
    first_difference: str = ""
    detail: str = ""


def deepcopy_circuit(circuit):
    """Deep copy a caller circuit (pins/parameters/metadata dicts included)."""
    return copy.deepcopy(circuit)
