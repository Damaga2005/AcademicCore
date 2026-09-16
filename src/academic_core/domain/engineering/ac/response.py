"""Transfer functions and frequency response for F8-D5 (network vs operating).

One shared architecture for four transfer kinds::

    Hv = Vout / Vin    (VOLTAGE_GAIN, dimensionless)
    Hi = Iout / Iin    (CURRENT_GAIN, dimensionless)
    Zt = Vout / Iin    (TRANSIMPEDANCE, ohm)
    Yt = Iout / Vin    (TRANSADMITTANCE, siemens)

Endpoints are unambiguous: voltage endpoints are ``(node_a, node_b)``
pairs (``V(A,B)``); current endpoints are branch refs in D3 orientation
(pin1->pin2 R/L/C, +->- V/I). A zero input gives UNDEFINED (defined
False, value None) — limit analysis is out of scope.

Two bases, never confused:

* ``network-transfer``: all independent sources except the nominated
  input are deactivated (V -> 0 V short, I -> removed) on a FRESH
  derived circuit, the input keeps its excitation, the derived system
  is solved, and output/input is measured. A network property.
* ``operating-point-ratio``: output/input read off one existing live
  solution. An observation, not a property.

Magnitude/phase come from the D1 authority; cartesian values are
preserved (never magnitude+phase only). No filters, no Bode, no unwrap,
no poles/zeros — the H tables produced here are their future input.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from academic_core.domain.engineering.ac.impedance import (
    OHM_SYMBOL,
    SIEMENS_SYMBOL,
    ImpedanceError,
    deactivate_sources,
)
from academic_core.domain.engineering.ac.phasors import magnitude, phase, to_polar
from academic_core.domain.engineering.ac.solution import ACStatus

BASIS_NETWORK_TRANSFER = "network-transfer"
BASIS_OPERATING_POINT_RATIO = "operating-point-ratio"


class TransferKind(Enum):
    VOLTAGE_GAIN = "voltage_gain"
    CURRENT_GAIN = "current_gain"
    TRANSIMPEDANCE = "transimpedance"
    TRANSADMITTANCE = "transadmittance"


_KIND_UNIT = {
    TransferKind.VOLTAGE_GAIN: "1",
    TransferKind.CURRENT_GAIN: "1",
    TransferKind.TRANSIMPEDANCE: OHM_SYMBOL,
    TransferKind.TRANSADMITTANCE: SIEMENS_SYMBOL,
}


@dataclass(frozen=True)
class Endpoint:
    """One transfer endpoint: voltage V(A,B) or branch current.

    ``kind`` is "voltage" (nodes a/b used) or "current" (branch ref
    used, D3 orientation). Exactly the data needed — no bare strings.
    """

    kind: str  # voltage | current
    node_a: str = ""
    node_b: str = ""
    branch: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("voltage", "current"):
            raise ImpedanceError(f"endpoint kind must be voltage|current, got {self.kind!r}")
        if self.kind == "voltage" and (not self.node_a or not self.node_b):
            raise ImpedanceError("voltage endpoint needs node_a and node_b")
        if self.kind == "current" and not self.branch:
            raise ImpedanceError("current endpoint needs a branch ref")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "A": self.node_a, "B": self.node_b,
                "branch": self.branch}


def voltage_between(node_a: str, node_b: str) -> Endpoint:
    return Endpoint("voltage", node_a=node_a, node_b=node_b)


def current_through(branch_ref: str) -> Endpoint:
    return Endpoint("current", branch=branch_ref)


@dataclass(frozen=True)
class TransferFunction:
    kind: TransferKind
    input: Endpoint
    output: Endpoint
    value: object | None  # phasor or None when undefined
    defined: bool
    basis: str  # network-transfer | operating-point-ratio
    unit: str
    input_source: str  # nominated input source ref ("" for operating ratios)
    diagnostic: str

    def require_defined(self):
        if not self.defined or self.value is None:
            raise ImpedanceError(
                f"{self.kind.value} undefined ({self.diagnostic})"
            )
        return self.value

    def magnitude(self) -> Decimal:
        return magnitude(self.require_defined())

    def phase(self) -> Decimal:
        return phase(self.require_defined())

    def polar(self) -> tuple[Decimal, Decimal]:
        return to_polar(self.require_defined())

    def to_dict(self) -> dict:
        from academic_core.domain.engineering.ac.phasors import fmt_cartesian

        return {
            "kind": self.kind.value,
            "input": self.input.to_dict(),
            "output": self.output.to_dict(),
            "value": None if self.value is None else fmt_cartesian(self.value),
            "defined": self.defined,
            "basis": self.basis,
            "unit": self.unit,
            "input_source": self.input_source,
            "diagnostic": self.diagnostic,
        }


def _kind_for(input_ep: Endpoint, output_ep: Endpoint) -> TransferKind:
    if input_ep.kind == "voltage" and output_ep.kind == "voltage":
        return TransferKind.VOLTAGE_GAIN
    if input_ep.kind == "current" and output_ep.kind == "current":
        return TransferKind.CURRENT_GAIN
    if input_ep.kind == "current" and output_ep.kind == "voltage":
        return TransferKind.TRANSIMPEDANCE
    return TransferKind.TRANSADMITTANCE


def _read_endpoint(solution, ep: Endpoint):
    if ep.kind == "voltage":
        va = solution.voltage_of(ep.node_a)
        vb = solution.voltage_of(ep.node_b)
        if va is None or vb is None:
            raise ImpedanceError(
                f"endpoint nodes ({ep.node_a}, {ep.node_b}) not in solution"
            )
        return va - vb
    cur = solution.current_of(ep.branch)
    if cur is None:
        raise ImpedanceError(f"endpoint branch {ep.branch!r} not in solution")
    return cur


def _divide_or_undefined(num, den, kind: TransferKind, basis: str,
                         input_source: str, input_ep: Endpoint,
                         output_ep: Endpoint) -> TransferFunction:
    unit = _KIND_UNIT[kind]
    tag = f"{kind.value}({output_ep.to_dict()} / {input_ep.to_dict()})"
    if den.is_zero_exact():
        return TransferFunction(
            kind, input_ep, output_ep, None, False, basis, unit,
            input_source,
            f"{tag}: zero input admits no transfer (limit analysis out of scope)",
        )
    return TransferFunction(
        kind, input_ep, output_ep, num / den, True, basis, unit,
        input_source, f"{tag}: {basis}",
    )


def analyze_transfer(solution, input_ep: Endpoint,
                     output_ep: Endpoint) -> TransferFunction:
    """Operating-point ratio from one live solution (labeled, not property)."""
    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"transfer analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    kind = _kind_for(input_ep, output_ep)
    num = _read_endpoint(solution, output_ep)
    den = _read_endpoint(solution, input_ep)
    return _divide_or_undefined(num, den, kind, BASIS_OPERATING_POINT_RATIO,
                                "", input_ep, output_ep)


def network_transfer(problem, solution, input_source: str, input_ep: Endpoint,
                     output_ep: Endpoint) -> TransferFunction:
    """True network transfer: all other independents deactivated.

    Builds a FRESH derived circuit (original untouched): every
    independent source except ``input_source`` is deactivated (V -> 0 V
    short, I -> removed), the input keeps its excitation, the derived
    system is solved through the F8-D3 engine, and output/input is read
    there. A non-SOLVED derived solve yields an explicitly labeled
    undefined transfer carrying the solver status.
    """
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.circuit import Circuit

    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"transfer analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    names = {c.ref.upper() for c in problem.circuit.components}
    if input_source.upper() not in names:
        raise ImpedanceError(f"input source {input_source!r} not in circuit")
    kept = next(c for c in problem.circuit.components
                if c.ref.upper() == input_source.upper())
    if kept.type.upper() not in ("V", "I"):
        raise ImpedanceError(
            f"transfer input must be an independent V/I source, got "
            f"{kept.type!r}"
        )
    derived = deactivate_sources(problem.circuit, keep=input_source)
    fresh = Circuit(f"{problem.circuit.name}+tin-{input_source.upper()}")
    for c in derived:
        fresh.add(c)
    res = solve_ac(fresh, problem.operating_point.frequency)
    kind = _kind_for(input_ep, output_ep)
    tag_in = " (deactivation: all independents except " \
        f"{input_source.upper()} set to 0V-short/removed)"
    if res.status != ACStatus.SOLVED:
        return TransferFunction(
            kind, input_ep, output_ep, None, False, BASIS_NETWORK_TRANSFER,
            _KIND_UNIT[kind], input_source.upper(),
            f"derived transfer solve: {res.status.value}{tag_in}",
        )
    num = _read_endpoint(res, output_ep)
    den = _read_endpoint(res, input_ep)
    tf = _divide_or_undefined(num, den, kind, BASIS_NETWORK_TRANSFER,
                              input_source.upper(), input_ep, output_ep)
    if not tf.defined:
        return TransferFunction(
            tf.kind, tf.input, tf.output, None, False, tf.basis, tf.unit,
            tf.input_source, tf.diagnostic + tag_in,
        )
    return TransferFunction(
        tf.kind, tf.input, tf.output, tf.value, True, tf.basis, tf.unit,
        tf.input_source, tf.diagnostic + tag_in,
    )


SWEEP_COMPLETED = "completed"
SWEEP_COMPLETED_WITH_POINT_FAILURES = "completed_with_point_failures"


@dataclass(frozen=True)
class ResponseDefinition:
    """What one frequency point computes (sweep driver input).

    ``kind`` selects branch impedance/admittance (``target`` = branch
    ref), port impedance/admittance (``target`` = ``PortDefinition``),
    or a transfer (``target`` = ``(input_endpoint, output_endpoint,
    input_source|"")`` tuple; empty source means operating-point ratio).
    """

    kind: str
    target: object

    def __post_init__(self) -> None:
        valid = ("branch-impedance", "branch-admittance", "port-impedance",
                 "port-admittance", "transfer")
        if self.kind not in valid:
            raise ImpedanceError(
                f"sweep quantity kind must be one of {valid}, got {self.kind!r}"
            )

    def to_dict(self) -> dict:
        from academic_core.domain.engineering.ac.impedance import PortDefinition
        t = self.target
        if isinstance(t, PortDefinition):
            td: object = t.to_dict()
        elif isinstance(t, tuple):
            td = [{"kind": e.kind, "A": e.node_a, "B": e.node_b,
                   "branch": e.branch} for e in t[:2]] + [t[2] if len(t) > 2 else ""]
        else:
            td = str(t)
        return {"kind": self.kind, "target": td}


@dataclass(frozen=True)
class SweepPoint:
    frequency: object  # Quantity (Hz)
    status: object  # ACStatus of the underlying D3 solve
    value: object | None  # ImpedanceValue | TransferFunction | None
    diagnostic: str
    digest: str | None

    def to_dict(self) -> dict:
        return {
            "frequency": str(self.frequency.to_base()),
            "status": self.status.value,
            "value": None if self.value is None else self.value.to_dict(),
            "diagnostic": self.diagnostic,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class SweepResult:
    status: str  # completed | completed_with_point_failures
    points: tuple[SweepPoint, ...]
    definition: ResponseDefinition
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "points": [p.to_dict() for p in self.points],
            "definition": self.definition.to_dict(),
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def linear_frequencies(start, stop, n: int) -> list:
    """Deterministic linear grid of n Hz quantities in [start, stop].

    Explicit working-context arithmetic (never ambient rounding) for the
    step; n == 1 yields [start] and requires start == stop.
    """
    from academic_core.domain.engineering.ac.operating_point import (
        ACOperatingPoint as _OP,
    )
    from academic_core.domain.engineering.math.trig import make_context
    from academic_core.domain.engineering.units import (
        FREQUENCY,
        Quantity,
        parse_quantity,
    )
    assert _OP is not None

    def _hz(v) -> Quantity:
        q = parse_quantity(v) if isinstance(v, str) else v
        if not isinstance(q, Quantity) or q.dimension != FREQUENCY:
            raise ImpedanceError(f"sweep frequency must be Hz, got {v!r}")
        if q.to_base() <= 0:
            raise ImpedanceError(f"sweep frequency must be f > 0, got {v!r}")
        return q

    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ImpedanceError(f"sweep count must be a positive int, got {n!r}")
    a, b = _hz(start), _hz(stop)
    ctx = make_context()
    fa, fb = a.to_base(), b.to_base()
    if n == 1:
        if fa != fb:
            raise ImpedanceError("single-point sweep requires start == stop")
        return [a]
    if fb < fa:
        raise ImpedanceError("linear sweep requires start <= stop")
    step = ctx.divide(ctx.subtract(fb, fa), Decimal(n - 1))
    from academic_core.domain.engineering.units import parse_unit

    hz = parse_unit("Hz")
    return [Quantity(ctx.add(fa, ctx.multiply(step, Decimal(i))), hz)
            for i in range(n)]


def _normalize_frequencies(frequencies) -> list:
    from academic_core.domain.engineering.units import (
        FREQUENCY,
        Quantity,
        parse_quantity,
    )

    out = []
    for f in frequencies:
        q = parse_quantity(f) if isinstance(f, str) else f
        if not isinstance(q, Quantity) or q.dimension != FREQUENCY:
            raise ImpedanceError(f"sweep frequency must be Hz, got {f!r}")
        if q.to_base() <= 0:
            raise ImpedanceError(f"sweep frequency must be f > 0, got {f!r}")
        out.append(q)
    if not out:
        raise ImpedanceError("sweep frequency list must not be empty")
    return out


def frequency_response(circuit, definition: ResponseDefinition,
                       frequencies) -> SweepResult:
    """Deterministic sweep: each frequency is an independent analysis.

    Per point: fresh operating point -> D3 solve -> D5 quantity. No MNA
    reuse across frequencies (A depends on omega), no caching. A failed
    point is recorded (status + diagnostic, value None) and never aborts
    the sweep: all-SOLVED yields ``completed``, else
    ``completed_with_point_failures``. Order, values and digest are
    fully determined by (circuit, definition, frequency list).
    """
    import hashlib
    import json

    from academic_core.domain.engineering.ac.impedance import (
        PortDefinition,
        measure_port,
    )
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.solution import ACStatus
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.math.linsolve.problem import NumericMode

    if not isinstance(definition, ResponseDefinition):
        raise ImpedanceError(
            f"definition must be a ResponseDefinition, got {type(definition).__name__}"
        )
    freqs = _normalize_frequencies(frequencies)
    ground = reference_net(circuit.nets)
    points: list[SweepPoint] = []
    failures = 0
    for freq in freqs:
        op = None
        try:
            from academic_core.domain.engineering.ac.operating_point import (
                ACOperatingPoint,
            )
            op = ACOperatingPoint.from_frequency(freq, ground)
            problem = build_ac_problem(circuit, op, NumericMode.AUTO)
            sol = solve_ac(circuit, freq, NumericMode.AUTO)
        except Exception as exc:  # validation failures become point data
            points.append(SweepPoint(freq, _status_of(exc), None, str(exc), None))
            failures += 1
            continue
        if sol.status != ACStatus.SOLVED:
            points.append(SweepPoint(
                freq, sol.status, None,
                f"point solve: {sol.status.value}; "
                f"{'; '.join(sol.diagnostics[:2])}", None))
            failures += 1
            continue
        try:
            value = _evaluate_definition(definition, problem, sol)
        except ImpedanceError as exc:
            points.append(SweepPoint(freq, sol.status, None, str(exc), None))
            failures += 1
            continue
        pdigest = hashlib.sha256(json.dumps(
            {"f": str(freq.to_base()), "value": value.to_dict()},
            sort_keys=True, default=str).encode()).hexdigest()
        points.append(SweepPoint(freq, sol.status, value,
                                 f"solved at {freq.format()}", pdigest))
    status = (SWEEP_COMPLETED if failures == 0
              else SWEEP_COMPLETED_WITH_POINT_FAILURES)
    digest = hashlib.sha256(json.dumps({
        "engine": "f8d-ac-response/1.0",
        "definition": definition.to_dict(),
        "circuit": sorted(c.ref.upper() for c in circuit.components),
        "points": [p.to_dict() for p in points],
    }, sort_keys=True, default=str).encode()).hexdigest()
    provenance = {
        "engine": "f8d-ac-response/1.0",
        "version": "1.0",
        "definition": definition.to_dict(),
        "frequencies_hz": [str(f.to_base()) for f in freqs],
        "n_points": len(points),
        "n_failures": failures,
        "temporal_convention": "e^(+jwt)",
        "amplitude_convention": "peak",
        "per_point_status": [p.status.value for p in points],
    }
    diagnostics = (f"sweep {status}: {len(points) - failures}/{len(points)} "
                   f"solved",)
    return SweepResult(status, tuple(points), definition, provenance,
                       diagnostics, digest)


def _status_of(exc: Exception):
    from academic_core.domain.engineering.ac.solution import ACStatus

    name = type(exc).__name__
    if "Unsupported" in name:
        return ACStatus.UNSUPPORTED
    return ACStatus.INVALID


def _evaluate_definition(definition: ResponseDefinition, problem, solution):
    from academic_core.domain.engineering.ac.impedance import (
        PortDefinition,
        branch_admittance,
        branch_impedance,
        measure_port,
    )

    kind, target = definition.kind, definition.target
    if kind == "branch-impedance":
        return branch_impedance(problem, solution, str(target))
    if kind == "branch-admittance":
        return branch_admittance(problem, solution, str(target))
    if kind in ("port-impedance", "port-admittance"):
        if not isinstance(target, PortDefinition):
            raise ImpedanceError("port sweep needs a PortDefinition target")
        quantity = "impedance" if kind == "port-impedance" else "admittance"
        return measure_port(problem, solution, target, quantity=quantity)
    # transfer: target = (input_endpoint, output_endpoint, input_source|"").
    input_ep, output_ep, source = target[0], target[1], target[2] if len(target) > 2 else ""
    if source:
        return network_transfer(problem, solution, source, input_ep, output_ep)
    return analyze_transfer(solution, input_ep, output_ep)
