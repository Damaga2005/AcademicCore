"""F8-D3 orchestration: Circuit + frequency -> AC phasor solution.

``solve_ac(circuit, frequency, mode=AUTO)`` is the convenience API: it
catches the expected, classifiable validation failures and reports them
in-band (INVALID / UNSUPPORTED, mirroring F8-B), while the mathematical
classification of well-formed systems is inherited 1:1 from the F8-D2
solver — D3 never overrides it with heuristics, only enriches the
diagnostics with physical hypotheses (floating subnetworks, parallel
ideal sources, resonant degeneracy).

``build_ac_problem`` is the lower-level audit API and raises typed
errors eagerly.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from academic_core.domain.engineering.ac.errors import (
    ACFrequencyError,
    ACModeError,
    ACPhaseError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.ac.problem import (
    ACMNAProblem,
    build_ac_problem,
)
from academic_core.domain.engineering.ac.solution import (
    ACSolution,
    ACStatus,
    NodePhasor,
    kcl_residual,
    kvl_residual,
    reconstruct,
)
from academic_core.domain.engineering.ac.topology import reference_net
from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve import (
    ComplexLinearProblem,
    NumericMode,
    SolveStatus,
    solve,
)
from academic_core.domain.engineering.mna.errors import CircularControlError
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.units import Quantity

ENGINE_VERSION = "f8d-ac-mna/1.0"

_D2_TO_AC = {
    SolveStatus.SOLVED: ACStatus.SOLVED,
    SolveStatus.SINGULAR: ACStatus.SINGULAR,
    SolveStatus.INCONSISTENT: ACStatus.INCONSISTENT,
    SolveStatus.NUMERICALLY_UNCERTAIN: ACStatus.NUMERICALLY_UNCERTAIN,
}

_PHYSICAL_HINTS = {
    ACStatus.SINGULAR: (
        "mathematically rank-deficient but consistent (D2 verdict, kept). "
        "Physical hypotheses (not overrides): parallel ideal voltage "
        "sources with equal phasors, series LC branch shorting a source "
        "at resonance, or a floating subnetwork that passed reachability "
        "only through an ideal source constraint."
    ),
    ACStatus.INCONSISTENT: (
        "mathematically contradictory constraints (D2 verdict, kept). "
        "Physical hypotheses (not overrides): incompatible ideal voltage "
        "sources on one node pair, or an ideal source across a "
        "zero-impedance series LC branch at resonance with Vs != 0."
    ),
    ACStatus.NUMERICALLY_UNCERTAIN: (
        "D2 could not certify the classification at working precision "
        "(verdict kept). Reconstructed branches and residuals below are "
        "the best available evidence, not a certified solution."
    ),
}

_INVALID_ERRORS = (
    InvalidCircuitError,
    MissingReferenceError,
    FloatingCircuitError,
    DimensionalityError,
    ACFrequencyError,
    ACPhaseError,
    ACModeError,
    CircularControlError,
)


def _canonical_circuit(circuit: Circuit) -> dict:
    return {
        "engine": ENGINE_VERSION,
        "circuit_name": circuit.name,
        "components": sorted(
            (
                {
                    "ref": c.ref.upper(),
                    "type": c.type.upper(),
                    "value_base": str(c.value.to_base()) if c.value is not None else None,
                    "pins": dict(sorted(c.pins.items())),
                    "parameters": {k: str(v) for k, v in sorted(c.parameters.items())},
                }
                for c in circuit.components
            ),
            key=lambda d: d["ref"],
        ),
    }


def _digest(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()


def solve_ac_problem(
    problem: ACMNAProblem,
    mode: NumericMode = NumericMode.AUTO,
) -> ACSolution:
    """Solve a pre-built :class:`ACMNAProblem` via the F8-D2 solver."""
    op = problem.operating_point
    lin_problem = ComplexLinearProblem.from_sequences(
        [list(row) for row in problem.matrix], list(problem.rhs)
    )
    lin = solve(lin_problem, mode)
    status = _D2_TO_AC[lin.status]
    diagnostics: list[str] = [
        f"engine={ENGINE_VERSION}",
        f"numeric_mode={lin.numeric_mode.value}",
        f"frequency={op.frequency.format()}",
        f"omega_rad_per_s={op.omega}",
        f"reference={problem.ground}",
        f"n_nodes={len(problem.nodes)}",
        f"n_vsources={len(problem.vsource_refs)}",
        f"solver_digest={lin.digest}",
    ]
    hint = _PHYSICAL_HINTS.get(status)
    if hint is not None:
        diagnostics.append(hint)

    zero_r = RationalComplex.zero()
    zero_d = DecimalComplex.zero()
    node_map: dict = {problem.ground: (zero_r if problem.kind == "rational" else zero_d)}
    branch_currents: tuple = ()
    branch_voltages: tuple = ()
    node_voltages: tuple = ()
    kcl_max: Decimal | None = None
    kvl_max: Decimal | None = None
    n_cycles = 0
    if lin.solution is not None:
        for n in problem.nodes:
            node_map[n] = lin.solution[problem.node_index[n]]
        node_voltages = tuple(
            NodePhasor(n, node_map[n]) for n in sorted(node_map)
        )
        branch_currents, branch_voltages = reconstruct(
            problem.branches, node_map, lin.solution, problem.vsource_index
        )
        kcl_max, _per_net = kcl_residual(
            problem.branches, branch_currents, problem.circuit.nets
        )
        kvl_max, n_cycles = kvl_residual(problem.branches, branch_voltages)
        e_count = len(problem.branches)
        v_count = len(problem.circuit.nets)
        diagnostics.append(
            f"kcl_max={kcl_max} kvl_max={kvl_max} cycles={n_cycles} "
            f"(expected E-V+1={e_count - v_count + 1})"
        )

    topology_digest = _digest(_canonical_circuit(problem.circuit))
    digest = _digest({
        "topology": topology_digest,
        "solver_digest": lin.digest,
        "status": status.value,
        "mode": lin.numeric_mode.value,
        "frequency_base_hz": str(op.frequency.to_base()),
    })
    provenance = {
        "engine": "f8d-ac-mna",
        "version": "1.0",
        "numeric_mode": lin.numeric_mode.value,
        "working_precision": lin.working_precision,
        "frequency": op.frequency.format(),
        "frequency_base_hz": str(op.frequency.to_base()),
        "angular_frequency_rad_per_s": str(op.omega),
        "phase_convention": op.phase_convention,
        "amplitude_convention": op.amplitude_convention,
        "reference_node": problem.ground,
        "component_refs": sorted(c.ref.upper() for c in problem.circuit.components),
        "topology_digest": topology_digest,
        "solver_digest": lin.digest,
        "status": status.value,
    }
    opamps = sorted(
        ({"ref": c.ref, "in_p": c.pins["+"], "in_n": c.pins["-"],
          "out": c.pins["o"]}
         for c in problem.circuit.components if c.type.upper() == "O"),
        key=lambda d: d["ref"],
    )
    if opamps:
        # F8-F provenance (conditional: circuits without O byte-identical).
        # The ideal op-amp is pins-only (no value/parameters); full
        # identity is these three nets.
        provenance["ideal_opamps"] = opamps
    xfmrs = sorted(
        ({"ref": c.ref, "p1": c.pins["1"], "p2": c.pins["2"],
          "s1": c.pins["3"], "s2": c.pins["4"],
          "n": str(c.value.to_base())}
         for c in problem.circuit.components if c.type.upper() == "T"),
        key=lambda d: d["ref"],
    )
    if xfmrs:
        # F8-G provenance (conditional: circuits without T byte-identical).
        # Identity is four nets plus the turns ratio from the digest.
        provenance["ideal_transformers"] = xfmrs
    return ACSolution(
        status=status,
        operating_point=op,
        node_voltages=node_voltages,
        branch_currents=branch_currents,
        branch_voltages=branch_voltages,
        residual=lin.residual,
        kcl_max_residual=kcl_max,
        kvl_max_residual=kvl_max,
        kvl_cycles=n_cycles,
        solver_result=lin,
        numeric_mode=lin.numeric_mode,
        working_precision=lin.working_precision,
        provenance=provenance,
        diagnostics=tuple(diagnostics),
        digest=digest,
    )


def _invalid_solution(
    status: ACStatus, diagnostics: tuple[str, ...], freq_text: str
) -> ACSolution:
    digest = _digest({"status": status.value, "diagnostics": list(diagnostics),
                      "frequency": freq_text})
    return ACSolution(
        status=status,
        operating_point=None,
        node_voltages=(),
        branch_currents=(),
        branch_voltages=(),
        residual=None,
        kcl_max_residual=None,
        kvl_max_residual=None,
        kvl_cycles=0,
        solver_result=None,
        numeric_mode=None,
        working_precision=None,
        provenance={"engine": "f8d-ac-mna", "version": "1.0", "status": status.value},
        diagnostics=diagnostics,
        digest=digest,
    )


def solve_ac(
    circuit: Circuit,
    frequency: Quantity | str,
    mode: NumericMode = NumericMode.AUTO,
) -> ACSolution:
    """Solve a canonical circuit in sinusoidal steady state at ``frequency``.

    Validation failures are reported in-band (INVALID / UNSUPPORTED);
    mathematical states are inherited from F8-D2. Never raises for a
    merely out-of-domain or ill-posed circuit.
    """
    try:
        ground = reference_net(circuit.nets)
    except MissingReferenceError as exc:
        return _invalid_solution(ACStatus.INVALID, (str(exc),), str(frequency))
    try:
        op = ACOperatingPoint.from_frequency(frequency, ground)
    except (ACFrequencyError, ValueError) as exc:
        return _invalid_solution(ACStatus.INVALID, (str(exc),), str(frequency))
    try:
        problem = build_ac_problem(circuit, op, mode)
    except UnsupportedElementError as exc:
        return _invalid_solution(ACStatus.UNSUPPORTED, (str(exc),), str(frequency))
    except _INVALID_ERRORS as exc:
        return _invalid_solution(ACStatus.INVALID, (str(exc),), str(frequency))
    return solve_ac_problem(problem, mode)
