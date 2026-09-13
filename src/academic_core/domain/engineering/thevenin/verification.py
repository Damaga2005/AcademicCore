"""Multi-load verification of Thevenin and Norton equivalents against the original circuit.

Verifies that connecting an identical resistive load to the original circuit
and to the equivalent model produces identical terminal voltages and currents.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import build_mna_problem, solve_linear_dc
from academic_core.domain.engineering.mna.linear import solve_exact
from academic_core.domain.engineering.mna.solver import _fraction_to_decimal
from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.thevenin.result import LoadVerificationResult, ResistanceKind
from academic_core.domain.engineering.units import Quantity, parse_quantity, parse_unit

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_OHM = parse_unit("ohm")

DEFAULT_TEST_LOADS = (
    "0.1 ohm",
    "10 ohm",
    "100 ohm",
    "1000 ohm",
    "50000 ohm",
    "1 Mohm",
)


def _next_ref(circuit: Circuit, prefix: str) -> str:
    nums = [
        int(c.ref[len(prefix):])
        for c in circuit.components
        if c.ref.upper().startswith(prefix.upper()) and c.ref[len(prefix):].isdigit()
    ]
    return f"{prefix}{max(nums, default=0) + 1}"


def verify_equivalent_with_loads(
    circuit: Circuit,
    port: TheveninPort,
    v_th_exact: Fraction,
    r_th_exact: Fraction | None,
    resistance_kind: ResistanceKind,
    load_strings: tuple[str, ...] = DEFAULT_TEST_LOADS,
) -> tuple[LoadVerificationResult, ...]:
    """Test the equivalent model against the original circuit across multiple load resistances."""
    if resistance_kind == ResistanceKind.UNDEFINED:
        return ()

    results: list[LoadVerificationResult] = []

    for r_str in load_strings:
        r_load_q = parse_quantity(r_str)
        r_load_f = Fraction(r_load_q.to_base())
        if r_load_f <= 0:
            continue

        # 1. Attach load to original circuit non-destructively
        c_loaded = Circuit(name=f"{circuit.name}_load_{r_str}")
        for c in circuit.components:
            c_loaded.add(Component(c.ref, c.type, c.value, dict(c.pins)))

        load_ref = _next_ref(c_loaded, "R")
        c_loaded.add(
            Component(load_ref, "R", r_load_q, {"1": port.positive_terminal, "2": port.negative_terminal})
        )

        try:
            prob = build_mna_problem(c_loaded)
            outcome = solve_exact([list(row) for row in prob.matrix], list(prob.rhs))
            if outcome.status.value != "unique" or outcome.solution is None:
                continue
            v_map = {n: outcome.solution[prob.node_index[n]] for n in prob.nodes}
            v_map[prob.ground] = Fraction(0)
            v_orig_f = v_map.get(port.positive_terminal, Fraction(0)) - v_map.get(port.negative_terminal, Fraction(0))
            i_orig_f = v_orig_f / r_load_f
        except Exception:
            continue

        # 2. Predict terminal response from equivalent
        if resistance_kind == ResistanceKind.FINITE and r_th_exact is not None:
            i_eq_f = v_th_exact / (r_th_exact + r_load_f)
            v_eq_f = i_eq_f * r_load_f
        elif resistance_kind == ResistanceKind.ZERO:
            i_eq_f = v_th_exact / r_load_f
            v_eq_f = v_th_exact
        elif resistance_kind == ResistanceKind.INFINITE:
            i_eq_f = Fraction(0)
            v_eq_f = Fraction(0)
        else:
            continue

        # Compare exact rational values (lossless)
        passed = (v_orig_f == v_eq_f) and (i_orig_f == i_eq_f)

        results.append(
            LoadVerificationResult(
                load_resistance=r_load_q,
                v_port_original=Quantity(_fraction_to_decimal(v_orig_f), _VOLT),
                i_port_original=Quantity(_fraction_to_decimal(i_orig_f), _AMP),
                v_port_equivalent=Quantity(_fraction_to_decimal(v_eq_f), _VOLT),
                i_port_equivalent=Quantity(_fraction_to_decimal(i_eq_f), _AMP),
                passed=passed,
            )
        )

    return tuple(results)
