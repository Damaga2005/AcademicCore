"""Core algorithms for F8-C Thevenin & Norton analysis.

Reuses the certified F8-B Modified Nodal Analysis (MNA) solver directly:
  * Open-circuit analysis: evaluate Vth = Va - Vb on original circuit.
  * Deactivated test-source analysis: deactivate independent sources (V->0V,
    I->open) and apply test source to determine Rth across arbitrary topologies.
  * Short-circuit analysis: insert ideal 0V short across the port on the active
    circuit to determine Isc = In independently via MNA.
  * Multi-load verification: verify equivalent terminal behavior against original.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import (
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    SolveStatus,
    UnsupportedElementError,
    build_mna_problem,
    solve_linear_dc,
)
from academic_core.domain.engineering.mna.linear import LinearSolveStatus, solve_exact
from academic_core.domain.engineering.mna.solver import _fraction_to_decimal
from academic_core.domain.engineering.thevenin.errors import InvalidPortError, UnsupportedCircuitError
from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.thevenin.result import (
    EquivalentStatus,
    NortonResult,
    OnePortEquivalent,
    ResistanceKind,
    TheveninResult,
)
from academic_core.domain.engineering.thevenin.verification import (
    _copy_component,
    verify_equivalent_with_loads,
)
from academic_core.domain.engineering.units import Quantity, parse_quantity, parse_unit

SOLVER_ENGINE = "f8c-thevenin-norton"
SOLVER_VERSION = "1.0"

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_OHM = parse_unit("ohm")


def _next_ref(circuit: Circuit, prefix: str) -> str:
    nums = [
        int(c.ref[len(prefix):])
        for c in circuit.components
        if c.ref.upper().startswith(prefix.upper()) and c.ref[len(prefix):].isdigit()
    ]
    return f"{prefix}{max(nums, default=0) + 1}"


def _solve_exact(
    circuit: Circuit,
) -> tuple[SolveStatus, dict[str, Fraction] | None, dict[str, Fraction] | None, tuple[str, ...]]:
    """Solve MNA over exact rationals without intermediate decimal rounding."""
    try:
        problem = build_mna_problem(circuit)
    except UnsupportedElementError as exc:
        return SolveStatus.UNSUPPORTED, None, None, (str(exc),)
    except (InvalidCircuitError, MissingReferenceError, FloatingCircuitError, DimensionalityError) as exc:
        return SolveStatus.INVALID, None, None, (str(exc),)

    outcome = solve_exact([list(row) for row in problem.matrix], list(problem.rhs))
    if outcome.status == LinearSolveStatus.SINGULAR:
        return SolveStatus.SINGULAR, None, None, ("MNA matrix is rank-deficient",)
    if outcome.status == LinearSolveStatus.INCONSISTENT:
        return SolveStatus.INCONSISTENT, None, None, ("MNA matrix is inconsistent",)

    assert outcome.solution is not None
    v_map = {n: outcome.solution[problem.node_index[n]] for n in problem.nodes}
    v_map[problem.ground] = Fraction(0)
    i_v_map = {ref: outcome.solution[problem.vsource_index[ref]] for ref in problem.vsource_refs}
    return SolveStatus.SOLVED, v_map, i_v_map, ()


def _deactivate_sources(circuit: Circuit) -> Circuit:
    """Create a deactivated copy of `circuit`:
    - Independent voltage sources (V) replaced by 0 V ideal voltage sources (short circuit).
    - Independent current sources (I) removed (open circuit).
    - Resistors (R) preserved untouched.
    - Dependent sources (E/G/H/F) KEPT active with full control data:
      Thevenin/Norton on active networks requires the test-source
      method with dependents present; deactivating them would answer
      a different (passive) network.
    - Ideal op-amps (O) KEPT active (same rule: the nullor constraint
      is part of the network being measured).
    - Ideal transformers (T) KEPT active (same rule: the turns-ratio
      constraints are part of the network being measured).
    - Any other type passes through untouched; the downstream exact
      solve classifies it honestly (UNSUPPORTED/INVALID).
    """
    dead = Circuit(name=f"{circuit.name}_deactivated")
    for c in circuit.components:
        t = c.type.upper()
        if t == "R":
            dead.add(_copy_component(c))
        elif t == "V":
            dead.add(Component(c.ref, "V", parse_quantity("0 V"), dict(c.pins)))
        elif t == "I":
            # Current source open-circuited
            pass
        else:
            dead.add(_copy_component(c))
    return dead


def _prune_disconnected_from_port_and_gnd(circuit: Circuit, port: TheveninPort, ground: str) -> Circuit:
    """If opening current sources left isolated subgraphs that do not touch ground
    or either port terminal, prune them so reachability to ground is maintained."""
    parent: dict[str, str] = {net: net for net in circuit.nets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for c in circuit.components:
        pins = list(c.pins.values())
        for other in pins[1:]:
            union(pins[0], other)

    relevant_roots = {find(ground), find(port.positive_terminal), find(port.negative_terminal)}
    pruned = Circuit(name=circuit.name)
    for c in circuit.components:
        pins = list(c.pins.values())
        if any(find(p) in relevant_roots for p in pins):
            pruned.add(_copy_component(c))
    return pruned


def _make_provenance(
    circuit: Circuit,
    port: TheveninPort,
    analysis_type: str,
    method: str,
    result_summary: dict,
    status_str: str,
) -> dict:
    canonical_dict = {
        "engine": SOLVER_ENGINE,
        "version": SOLVER_VERSION,
        "analysis": analysis_type,
        "port": f"{port.positive_terminal}->{port.negative_terminal}",
        "circuit_name": circuit.name,
        "input_components": sorted(c.ref for c in circuit.components),
        "method": method,
        "source_deactivation_method": "V -> 0V short circuit, I -> open circuit",
        "test_source_configuration": "Vtest = 1V (+ on A, - on B); fallback Itest = 1A",
        "formulation": "MNA open-circuit + deactivated test-source analysis",
        "result": result_summary,
        "verification_status": status_str,
    }
    digest = hashlib.sha256(json.dumps(canonical_dict, sort_keys=True, default=str).encode()).hexdigest()
    return {
        "engine": SOLVER_ENGINE,
        "version": SOLVER_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
        "analysis": analysis_type,
        "port": f"{port.positive_terminal}->{port.negative_terminal}",
        "circuit_name": circuit.name,
        "method": method,
        "source_deactivation_method": canonical_dict["source_deactivation_method"],
        "test_source_configuration": canonical_dict["test_source_configuration"],
        "formulation": canonical_dict["formulation"],
        "result": result_summary,
        "verification_status": status_str,
    }


def analyze_thevenin(circuit: Circuit, port: TheveninPort) -> TheveninResult:
    """Compute the Thevenin equivalent (Vth, Rth) for the given port.

    Never modifies the input `circuit` destructively. Uses F8-B MNA exclusively.
    """
    try:
        port.validate_against(circuit)
    except InvalidPortError as exc:
        return TheveninResult(
            status=EquivalentStatus.INVALID_PORT,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=(str(exc),),
        )
    except UnsupportedCircuitError as exc:
        return TheveninResult(
            status=EquivalentStatus.UNSUPPORTED,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=(str(exc),),
        )

    # 1. Open-circuit voltage Vth = Va - Vb using exact MNA
    status_oc, v_map_oc, _, diag_oc = _solve_exact(circuit)
    if status_oc == SolveStatus.SINGULAR:
        return TheveninResult(
            status=EquivalentStatus.SINGULAR,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=("open-circuit system is rank-deficient/singular",),
        )
    if status_oc == SolveStatus.INCONSISTENT:
        return TheveninResult(
            status=EquivalentStatus.INCONSISTENT,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=("open-circuit system is contradictory/inconsistent",),
        )
    if status_oc in (SolveStatus.INVALID, SolveStatus.UNSUPPORTED):
        return TheveninResult(
            status=EquivalentStatus.INVALID_PORT if status_oc == SolveStatus.INVALID else EquivalentStatus.UNSUPPORTED,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=diag_oc,
        )

    assert v_map_oc is not None
    v_a = v_map_oc.get(port.positive_terminal, Fraction(0))
    v_b = v_map_oc.get(port.negative_terminal, Fraction(0))
    v_th_exact = v_a - v_b

    # 2. Deactivated network for Rth
    dead_raw = _deactivate_sources(circuit)
    ref_net = next(net for net in circuit.nets if net.strip().upper() in ("0", "GND"))
    dead = _prune_disconnected_from_port_and_gnd(dead_raw, port, ref_net)

    # Apply Vtest = 1 V across port (positive on A, negative on B)
    v_test_ref = _next_ref(dead, "V")
    c_vtest = Circuit(name=f"{dead.name}_vtest")
    for comp in dead.components:
        c_vtest.add(_copy_component(comp))
    c_vtest.add(
        Component(v_test_ref, "V", parse_quantity("1 V"), {"+": port.positive_terminal, "-": port.negative_terminal})
    )

    status_vtest, v_map_vtest, i_v_map_vtest, diag_vtest = _solve_exact(c_vtest)

    r_th_exact: Fraction | None = None
    res_kind = ResistanceKind.UNDEFINED
    status = EquivalentStatus.SOLVED

    if status_vtest == SolveStatus.SOLVED:
        assert i_v_map_vtest is not None
        # Branch current of Vtest flows + -> - through source. Current delivered into port A is -I_v
        i_v_f = i_v_map_vtest[v_test_ref]
        i_delivered_f = -i_v_f
        if i_delivered_f == 0:
            res_kind = ResistanceKind.INFINITE
            status = EquivalentStatus.OPEN_CIRCUIT
            r_th_exact = None
        else:
            res_kind = ResistanceKind.FINITE
            r_th_exact = Fraction(1) / i_delivered_f
    elif status_vtest == SolveStatus.INCONSISTENT:
        # 1V test source clashed with 0V short path across port -> test if Rth == 0 with Itest = 1 A
        i_test_ref = _next_ref(dead, "I")
        c_itest = Circuit(name=f"{dead.name}_itest")
        for comp in dead.components:
            c_itest.add(_copy_component(comp))
        c_itest.add(
            Component(i_test_ref, "I", parse_quantity("1 A"), {"+": port.positive_terminal, "-": port.negative_terminal})
        )
        status_itest, v_map_itest, _, diag_itest = _solve_exact(c_itest)
        if status_itest == SolveStatus.SOLVED:
            assert v_map_itest is not None
            v_drop_f = v_map_itest.get(port.positive_terminal, Fraction(0)) - v_map_itest.get(port.negative_terminal, Fraction(0))
            if v_drop_f == 0:
                res_kind = ResistanceKind.ZERO
                status = EquivalentStatus.SOLVED
                r_th_exact = Fraction(0)
            else:
                res_kind = ResistanceKind.FINITE
                r_th_exact = v_drop_f  # (v_drop / 1 A)
        else:
            return TheveninResult(
                status=EquivalentStatus.INCONSISTENT,
                port=port,
                polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
                diagnostics=("deactivated system is inconsistent",),
            )
    elif status_vtest == SolveStatus.SINGULAR:
        return TheveninResult(
            status=EquivalentStatus.SINGULAR,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=("deactivated system is singular",),
        )
    else:
        return TheveninResult(
            status=EquivalentStatus.UNDEFINED,
            port=port,
            polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
            diagnostics=diag_vtest,
        )

    # Multi-load verification
    verifications = verify_equivalent_with_loads(circuit, port, v_th_exact, r_th_exact, res_kind)
    if verifications and all(v.passed for v in verifications):
        status = EquivalentStatus.VERIFIED

    v_th_q = Quantity(_fraction_to_decimal(v_th_exact), _VOLT)
    r_th_q = Quantity(_fraction_to_decimal(r_th_exact), _OHM) if r_th_exact is not None else None

    result_summary = {
        "v_th": v_th_q.format(),
        "r_th": r_th_q.format() if r_th_q is not None else (
            "infinity" if res_kind == ResistanceKind.INFINITE else None
        ),
        "resistance_kind": res_kind.value,
        "polarity": f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
    }

    provenance = _make_provenance(
        circuit, port, "thevenin", "MNA open-circuit + deactivated test-source analysis", result_summary, status.value
    )

    return TheveninResult(
        status=status,
        port=port,
        v_th=v_th_q,
        r_th=r_th_q,
        resistance_kind=res_kind,
        polarity=f"+ on {port.positive_terminal}, - on {port.negative_terminal}",
        provenance=provenance,
        load_verifications=verifications,
        _v_th_exact=v_th_exact,
        _r_th_exact=r_th_exact,
    )


def analyze_norton(circuit: Circuit, port: TheveninPort) -> NortonResult:
    """Compute the Norton equivalent (In, Rn) for the given port.

    In = short-circuit current Isc from A to B. Validated independently against
    Vth / Rth where both are finite and non-zero.
    """
    thev = analyze_thevenin(circuit, port)
    if thev.status in (
        EquivalentStatus.INVALID_PORT,
        EquivalentStatus.UNSUPPORTED,
        EquivalentStatus.SINGULAR,
        EquivalentStatus.INCONSISTENT,
        EquivalentStatus.UNDEFINED,
    ):
        return NortonResult(
            status=thev.status,
            port=port,
            polarity=f"{port.positive_terminal} -> {port.negative_terminal}",
            diagnostics=thev.diagnostics,
        )

    # 1. Independent short-circuit analysis on active circuit
    c_sc = Circuit(name=f"{circuit.name}_sc")
    for c in circuit.components:
        c_sc.add(_copy_component(c))
    v_sc_ref = _next_ref(c_sc, "V")
    c_sc.add(
        Component(v_sc_ref, "V", parse_quantity("0 V"), {"+": port.positive_terminal, "-": port.negative_terminal})
    )

    status_sc, v_map_sc, i_v_map_sc, diag_sc = _solve_exact(c_sc)

    i_n_exact: Fraction | None = None
    status = EquivalentStatus.SOLVED

    if thev.resistance_kind == ResistanceKind.ZERO:
        # Norton equivalent cannot represent an ideal voltage source as a finite current source
        msg = (
            "Norton equivalent is not representable as a finite ordinary current source "
            "for zero Thevenin resistance (ideal voltage source)"
        )
        return NortonResult(
            status=EquivalentStatus.UNDEFINED,
            port=port,
            r_n=thev.r_th,
            resistance_kind=ResistanceKind.ZERO,
            polarity=f"{port.positive_terminal} -> {port.negative_terminal}",
            diagnostics=(msg,),
            _r_n_exact=thev._r_th_exact,
        )

    if status_sc == SolveStatus.SOLVED:
        assert i_v_map_sc is not None
        # Branch current of V_sc flows from + (A) to - (B) through the short
        i_sc_f = i_v_map_sc[v_sc_ref]
        i_n_exact = i_sc_f

        # Cross-validation: In == Vth / Rth when Rth is finite
        if thev.resistance_kind == ResistanceKind.FINITE and thev._r_th_exact is not None and thev._v_th_exact is not None:
            expected_in = thev._v_th_exact / thev._r_th_exact
            if i_n_exact != expected_in:
                raise ValueError(
                    f"internal defect: short-circuit current {i_n_exact} != Vth/Rth ({expected_in})"
                )
    elif thev.resistance_kind == ResistanceKind.INFINITE:
        i_n_exact = Fraction(0)
    else:
        status = EquivalentStatus.UNDEFINED

    i_n_q = Quantity(_fraction_to_decimal(i_n_exact), _AMP) if i_n_exact is not None else None

    if thev.status == EquivalentStatus.VERIFIED:
        status = EquivalentStatus.VERIFIED

    result_summary = {
        "i_n": i_n_q.format() if i_n_q is not None else None,
        "r_n": thev.r_th.format() if thev.r_th is not None else (
            "infinity" if thev.resistance_kind == ResistanceKind.INFINITE else None
        ),
        "resistance_kind": thev.resistance_kind.value,
        "polarity": f"{port.positive_terminal} -> {port.negative_terminal}",
    }

    provenance = _make_provenance(
        circuit, port, "norton", "MNA short-circuit analysis + Ohm's law cross-check", result_summary, status.value
    )

    return NortonResult(
        status=status,
        port=port,
        i_n=i_n_q,
        r_n=thev.r_th,
        resistance_kind=thev.resistance_kind,
        polarity=f"{port.positive_terminal} -> {port.negative_terminal}",
        provenance=provenance,
        load_verifications=thev.load_verifications,
        _i_n_exact=i_n_exact,
        _r_n_exact=thev._r_th_exact,
    )


def analyze_one_port(circuit: Circuit, port: TheveninPort) -> OnePortEquivalent:
    """Unified two-terminal one-port analysis returning both Thevenin and Norton equivalents."""
    thev = analyze_thevenin(circuit, port)
    nort = analyze_norton(circuit, port)

    is_equiv = False
    if (
        thev.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED)
        and nort.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED)
    ):
        if (
            thev.resistance_kind == ResistanceKind.FINITE
            and thev._v_th_exact is not None
            and thev._r_th_exact is not None
            and nort._i_n_exact is not None
        ):
            is_equiv = (thev._v_th_exact == nort._i_n_exact * thev._r_th_exact)

    overall_status = thev.status
    summary = {
        "thevenin_status": thev.status.value,
        "norton_status": nort.status.value,
        "is_equivalent": is_equiv,
    }
    prov = _make_provenance(circuit, port, "oneport", "unified one-port analysis", summary, overall_status.value)

    return OnePortEquivalent(
        status=overall_status,
        port=port,
        thevenin=thev,
        norton=nort,
        is_equivalent=is_equiv,
        provenance=prov,
    )

