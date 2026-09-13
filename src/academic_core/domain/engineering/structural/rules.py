"""Deterministic topological recognition rules for electrical circuits (Phase 7-B8).

Implements rule-based structural classification with deterministic explainability.
No LLMs, no linguistic heuristics, no invented justifications.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from academic_core.domain.engineering.structural.elements import CircuitGraph
from academic_core.domain.engineering.structural.types import TopologyType


@dataclass(frozen=True)
class RecognitionMatch:
    """A matched topological pattern with deterministic explainability."""

    topology: TopologyType
    elements: tuple[str, ...]  # sorted component refs involved
    reason: str  # derived from real topology
    metadata: dict[str, Any] = field(default_factory=dict)


class RecognitionRule(ABC):
    """Abstract base class for extensible circuit pattern recognition rules."""

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Name of the recognition rule."""
        pass

    @abstractmethod
    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        """Evaluate rule against the circuit graph, returning matches."""
        pass


class SingleResistorRule(RecognitionRule):
    """Recognizes circuits with exactly one resistor."""

    @property
    def rule_name(self) -> str:
        return "SingleResistorRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        r_comps = [c for c in graph.components.values() if c.type.upper() == "R"]
        if len(r_comps) == 1:
            ref = r_comps[0].ref.upper()
            return [
                RecognitionMatch(
                    topology=TopologyType.SINGLE_RESISTOR,
                    elements=(ref,),
                    reason=f"Circuit contains exactly one resistor {ref}.",
                )
            ]
        return []


class SeriesResistorsRule(RecognitionRule):
    """Recognizes two or more resistors connected in series."""

    @property
    def rule_name(self) -> str:
        return "SeriesResistorsRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        chains = graph.get_resistor_series_chains()
        for r_chain, (t1, t2), inter_nodes in chains:
            if len(r_chain) >= 2:
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.SERIES_RESISTORS,
                        elements=tuple(sorted(r_chain)),
                        reason=(
                            f"Resistors {', '.join(sorted(r_chain))} form a series connection "
                            f"sharing intermediate node(s) {sorted(inter_nodes)} with degree 2."
                        ),
                    )
                )
        return matches


class ParallelResistorsRule(RecognitionRule):
    """Recognizes two or more resistors connected in parallel."""

    @property
    def rule_name(self) -> str:
        return "ParallelResistorsRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        groups = graph.get_parallel_groups()
        for g in groups:
            r_group = [c for c in g if graph.components[c].type == "R"]
            if len(r_group) >= 2:
                # Find nodes
                b = [b for b in graph.branches if b.ref == r_group[0]][0]
                n1, n2 = min(b.node1, b.node2), max(b.node1, b.node2)
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.PARALLEL_RESISTORS,
                        elements=tuple(sorted(r_group)),
                        reason=(
                            f"Resistors {', '.join(sorted(r_group))} are connected in parallel "
                            f"across nodes {n1} and {n2}."
                        ),
                    )
                )
        return matches


class VoltageDividerRule(RecognitionRule):
    """Recognizes a voltage divider structure.

    Pattern:
    - An independent voltage source V connected across node_hi and node_lo.
    - A series chain of >= 2 resistors connected between node_hi and node_lo.
    - At least one intermediate tap node exposed between the resistors.
    """

    @property
    def rule_name(self) -> str:
        return "VoltageDividerRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        v_sources = [c for c in graph.components.values() if c.type == "V"]
        chains = graph.get_resistor_series_chains()

        if not v_sources or not chains:
            return []

        for v in v_sources:
            vp, vm = str(v.pins.get("+", "")), str(v.pins.get("-", ""))
            v_pair = (min(vp, vm), max(vp, vm))

            for r_chain, (t1, t2), inter_nodes in chains:
                if len(r_chain) >= 2 and (t1, t2) == v_pair and inter_nodes:
                    elements = tuple(sorted([v.ref.upper()] + list(r_chain)))
                    matches.append(
                        RecognitionMatch(
                            topology=TopologyType.VOLTAGE_DIVIDER,
                            elements=elements,
                            reason=(
                                f"Resistors {', '.join(sorted(r_chain))} share a series path "
                                f"across voltage source {v.ref.upper()} terminals ({vp}, {vm}), "
                                f"with intermediate tap node(s) {sorted(inter_nodes)}."
                            ),
                            metadata={
                                "tap_nodes": sorted(inter_nodes),
                                "output_node": None,
                            },
                        )
                    )
        return matches


class CurrentDividerRule(RecognitionRule):
    """Recognizes a current divider structure.

    Pattern:
    - An independent current source I connected across nodes n1 and n2.
    - Two or more parallel resistor branches connected across n1 and n2.
    """

    @property
    def rule_name(self) -> str:
        return "CurrentDividerRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        i_sources = [c for c in graph.components.values() if c.type == "I"]
        if not i_sources:
            return []

        for i_src in i_sources:
            ip, im = str(i_src.pins.get("+", "")), str(i_src.pins.get("-", ""))
            i_pair = (min(ip, im), max(ip, im))

            # Find parallel resistors across this exact pair of nodes
            parallel_resistors = []
            for b in graph.branches:
                if b.type == "R":
                    b_pair = (min(b.node1, b.node2), max(b.node1, b.node2))
                    if b_pair == i_pair:
                        parallel_resistors.append(b.ref)

            if len(parallel_resistors) >= 2:
                elements = tuple(sorted([i_src.ref.upper()] + parallel_resistors))
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.CURRENT_DIVIDER,
                        elements=elements,
                        reason=(
                            f"Current source {i_src.ref.upper()} feeds parallel resistors "
                            f"{', '.join(sorted(parallel_resistors))} across nodes {i_pair[0]} and {i_pair[1]}."
                        ),
                    )
                )
        return matches


class ResistiveBridgeRule(RecognitionRule):
    """Recognizes 4 or 5 resistor bridge topologies (e.g. Wheatstone bridge)."""

    @property
    def rule_name(self) -> str:
        return "ResistiveBridgeRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        from itertools import combinations

        r_comps = [c for c in graph.components.values() if c.type == "R"]
        if len(r_comps) not in (4, 5):
            return []

        # Find 4 distinct nodes involved with these resistors
        r_nodes = set()
        for c in r_comps:
            for net in c.pins.values():
                r_nodes.add(str(net))

        if len(r_nodes) != 4:
            return []

        # An energized bridge requires an independent source across excitation terminals
        sources = [c for c in graph.components.values() if c.type in ("V", "I")]
        if not sources:
            return []

        nlist = sorted(r_nodes)
        edges = {tuple(sorted([b.node1, b.node2])) for b in graph.branches if b.type == "R"}

        # Check if there exists a partition into excitation pair (A, B) and detector pair (C, D)
        # such that the 4 bridge arms (A,C), (A,D), (B,C), (B,D) all exist
        for pair in combinations(nlist, 2):
            A, B = pair
            rem = [n for n in nlist if n not in pair]
            C, D = rem[0], rem[1]
            arms = {tuple(sorted([A, C])), tuple(sorted([A, D])), tuple(sorted([B, C])), tuple(sorted([B, D]))}
            if not arms.issubset(edges):
                continue

            # Check excitation source: must connect across (A, B) or (C, D).
            # Store the matched source explicitly (never rely on a residual
            # loop variable) so the 5th-resistor diagonal decision below uses
            # a well-defined, deterministic value. Sources are scanned in
            # sorted ref order so that, if multiple sources qualify, the
            # outcome does not depend on component insertion order.
            matched_source_pair: tuple[str, str] | None = None
            matched_source_ref: str | None = None
            for s in sorted(sources, key=lambda c: c.ref.upper()):
                sp, sm = str(s.pins.get("+", "")), str(s.pins.get("-", ""))
                candidate_pair = tuple(sorted([sp, sm]))
                if candidate_pair in (tuple(sorted([A, B])), tuple(sorted([C, D]))):
                    matched_source_pair = candidate_pair
                    matched_source_ref = s.ref.upper()
                    break

            if matched_source_pair is None:
                continue

            # If 5th resistor, it must connect across the other diagonal
            if len(r_comps) == 5:
                diag = (
                    tuple(sorted([C, D]))
                    if matched_source_pair == tuple(sorted([A, B]))
                    else tuple(sorted([A, B]))
                )
                if diag not in edges:
                    continue

            elements = tuple(sorted([c.ref for c in r_comps]))
            return [
                RecognitionMatch(
                    topology=TopologyType.RESISTIVE_BRIDGE,
                    elements=elements,
                    reason=(
                        f"Resistors {', '.join(elements)} form a 4-node Wheatstone bridge structure "
                        f"with excitation across ({A}, {B}) and sensing across ({C}, {D})."
                    ),
                    metadata={
                        "bridge_nodes": nlist,
                        "excitation_nodes": (A, B),
                        "detector_nodes": (C, D),
                        "matched_source_pair": matched_source_pair,
                        "matched_source_ref": matched_source_ref,
                    },
                )
            ]
        return []


class SeriesParallelReducibleRule(RecognitionRule):
    """Recognizes whether a multi-resistor network is reducible via series/parallel steps."""

    @property
    def rule_name(self) -> str:
        return "SeriesParallelReducibleRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        r_comps = [c for c in graph.components.values() if c.type == "R"]
        if len(r_comps) >= 2 and graph.is_connected and not graph.floating_nodes:
            if graph.is_resistor_network_reducible():
                elements = tuple(sorted([c.ref for c in r_comps]))
                # Check if it has both series and parallel
                has_series = bool(graph.get_series_pairs())
                has_parallel = bool(graph.get_parallel_groups())
                matches = [
                    RecognitionMatch(
                        topology=TopologyType.SERIES_PARALLEL_REDUCIBLE,
                        elements=elements,
                        reason=(
                            f"Resistor network ({', '.join(elements)}) can be iteratively reduced "
                            "to a single equivalent resistance via series and parallel steps."
                        ),
                    )
                ]
                if has_series and has_parallel:
                    matches.append(
                        RecognitionMatch(
                            topology=TopologyType.SERIES_PARALLEL_MIXED,
                            elements=elements,
                            reason="Network contains a combination of both series and parallel resistor connections.",
                        )
                    )
                return matches
            else:
                elements = tuple(sorted([c.ref for c in r_comps]))
                return [
                    RecognitionMatch(
                        topology=TopologyType.NON_REDUCIBLE_RESISTIVE,
                        elements=elements,
                        reason=(
                            f"Resistor network ({', '.join(elements)}) cannot be reduced by pure "
                            "series/parallel transformations (contains cross-bridge or mesh dependencies)."
                        ),
                    )
                ]
        return []


class IndependentSourcesRule(RecognitionRule):
    """Recognizes independent voltage and current sources."""

    @property
    def rule_name(self) -> str:
        return "IndependentSourcesRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        for comp in graph.components.values():
            if comp.type == "V":
                vp, vm = str(comp.pins.get("+", "")), str(comp.pins.get("-", ""))
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.INDEPENDENT_VOLTAGE_SOURCE,
                        elements=(comp.ref.upper(),),
                        reason=f"Independent voltage source {comp.ref.upper()} connected from {vp} to {vm}.",
                    )
                )
            elif comp.type == "I":
                ip, im = str(comp.pins.get("+", "")), str(comp.pins.get("-", ""))
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.INDEPENDENT_CURRENT_SOURCE,
                        elements=(comp.ref.upper(),),
                        reason=f"Independent current source {comp.ref.upper()} delivering current from {ip} to {im}.",
                    )
                )
        return sorted(matches, key=lambda m: m.elements)


class DynamicNetworkRule(RecognitionRule):
    """Recognizes RC, RL, RLC, and energy storage networks based on electrical loops."""

    @property
    def rule_name(self) -> str:
        return "DynamicNetworkRule"

    def evaluate(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        matches: list[RecognitionMatch] = []
        c_comps = [c for c in graph.components.values() if c.type == "C"]
        l_comps = [c for c in graph.components.values() if c.type == "L"]
        r_comps = [c for c in graph.components.values() if c.type == "R"]

        if not c_comps and not l_comps:
            return []

        storage_refs = tuple(sorted([c.ref for c in c_comps + l_comps]))
        matches.append(
            RecognitionMatch(
                topology=TopologyType.ENERGY_STORAGE,
                elements=storage_refs,
                reason=f"Circuit contains reactive energy storage elements ({', '.join(storage_refs)}).",
            )
        )

        # Disconnected or floating reactive elements should not be classified as clean RC/RL/RLC
        if not graph.is_connected or graph.floating_nodes or graph.has_invalid_voltage_short():
            return matches

        # Check if reactive elements have any floating pins
        for c in c_comps + l_comps:
            for net in c.pins.values():
                node_obj = graph.nodes.get(str(net))
                if node_obj is None or node_obj.degree <= 1:
                    return matches

        loops = graph.get_fundamental_loops()
        if not loops:
            return matches

        # 1. RC check
        if c_comps and not l_comps and r_comps:
            # Check for ideal voltage source direct clamp across any capacitor
            v_sources = [c for c in graph.components.values() if c.type == "V"]
            clamped = False
            for c in c_comps:
                c_pair = {str(c.pins["1"]), str(c.pins["2"])}
                for v in v_sources:
                    v_pair = {str(v.pins["+"]), str(v.pins["-"])}
                    if c_pair == v_pair:
                        clamped = True
                        break
                if clamped:
                    break

            if not clamped:
                # Every capacitor must participate in at least one closed loop containing a resistor
                all_c_in_loop = True
                active_refs: set[str] = set()
                for c in c_comps:
                    c_in_rc_loop = False
                    for loop in loops:
                        if c.ref in loop and any(graph.components[ref].type == "R" for ref in loop):
                            c_in_rc_loop = True
                            active_refs.update(loop)
                    if not c_in_rc_loop:
                        all_c_in_loop = False
                        break

                if all_c_in_loop and active_refs:
                    rc_elements = tuple(sorted([ref for ref in active_refs if graph.components[ref].type in ("R", "C")]))
                    matches.append(
                        RecognitionMatch(
                            topology=TopologyType.RC,
                            elements=rc_elements,
                            reason=(
                                f"First-order RC network formed by coherent closed loops containing "
                                f"capacitive storage ({', '.join(sorted(c.ref for c in c_comps))}) "
                                f"and resistive path ({', '.join(sorted(r.ref for r in r_comps))})."
                            ),
                        )
                    )

        # 2. RL check
        elif l_comps and not c_comps and r_comps:
            # An inductor directly clamped in parallel by an ideal current
            # source has its branch current fixed by the source, eliminating
            # the dynamic degree of freedom -- same reasoning as a capacitor
            # clamped by an ideal voltage source.
            i_sources = [c for c in graph.components.values() if c.type == "I"]
            l_clamped = False
            for l in l_comps:
                l_pair = {str(l.pins["1"]), str(l.pins["2"])}
                for i_src in i_sources:
                    i_pair = {str(i_src.pins["+"]), str(i_src.pins["-"])}
                    if l_pair == i_pair:
                        l_clamped = True
                        break
                if l_clamped:
                    break
            if l_clamped:
                return matches

            all_l_in_loop = True
            active_refs = set()
            for l in l_comps:
                l_in_rl_loop = False
                for loop in loops:
                    if l.ref in loop and any(graph.components[ref].type == "R" for ref in loop):
                        l_in_rl_loop = True
                        active_refs.update(loop)
                if not l_in_rl_loop:
                    all_l_in_loop = False
                    break

            if all_l_in_loop and active_refs:
                rl_elements = tuple(sorted([ref for ref in active_refs if graph.components[ref].type in ("R", "L")]))
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.RL,
                        elements=rl_elements,
                        reason=(
                            f"First-order RL network formed by coherent closed loops containing "
                            f"inductive storage ({', '.join(sorted(l.ref for l in l_comps))}) "
                            f"and resistive path ({', '.join(sorted(r.ref for r in r_comps))})."
                        ),
                    )
                )

        # 3. RLC check
        elif c_comps and l_comps and r_comps:
            # Check that L and C participate in shared or coupled dynamic loops with R
            rlc_shared = False
            for loop in loops:
                has_c = any(graph.components[ref].type == "C" for ref in loop)
                has_l = any(graph.components[ref].type == "L" for ref in loop)
                if has_c and has_l:
                    rlc_shared = True
                    break

            if not rlc_shared:
                for c in c_comps:
                    c_pair = (min(str(c.pins["1"]), str(c.pins["2"])), max(str(c.pins["1"]), str(c.pins["2"])))
                    for l in l_comps:
                        l_pair = (min(str(l.pins["1"]), str(l.pins["2"])), max(str(l.pins["1"]), str(l.pins["2"])))
                        if c_pair == l_pair:
                            rlc_shared = True
                            break

            if rlc_shared:
                all_refs = tuple(sorted([c.ref for c in c_comps + l_comps + r_comps]))
                matches.append(
                    RecognitionMatch(
                        topology=TopologyType.RLC,
                        elements=all_refs,
                        reason=(
                            f"Second-order RLC network comprising resistance ({', '.join(sorted(r.ref for r in r_comps))}), "
                            f"inductance ({', '.join(sorted(l.ref for l in l_comps))}), and "
                            f"capacitance ({', '.join(sorted(c.ref for c in c_comps))}) in coherent coupled loops."
                        ),
                    )
                )

        return sorted(matches, key=lambda m: (m.topology.value, m.elements))



class RuleRegistry:
    """Registry of deterministic recognition rules.

    Allows future extension (e.g. DiodeRecognitionRule, BJTRecognitionRule)
    without rewriting the analyzer engine.
    """

    def __init__(self, default_rules: bool = True):
        self._rules: list[RecognitionRule] = []
        if default_rules:
            self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(IndependentSourcesRule())
        self.register(SingleResistorRule())
        self.register(SeriesResistorsRule())
        self.register(ParallelResistorsRule())
        self.register(VoltageDividerRule())
        self.register(CurrentDividerRule())
        self.register(ResistiveBridgeRule())
        self.register(SeriesParallelReducibleRule())
        self.register(DynamicNetworkRule())

    def register(self, rule: RecognitionRule) -> None:
        self._rules.append(rule)

    @property
    def rules(self) -> tuple[RecognitionRule, ...]:
        return tuple(self._rules)

    def evaluate_all(self, graph: CircuitGraph) -> list[RecognitionMatch]:
        """Evaluate all registered rules in deterministic order."""
        matches: list[RecognitionMatch] = []
        for rule in self._rules:
            res = rule.evaluate(graph)
            matches.extend(res)
        return sorted(matches, key=lambda m: (m.topology.value, m.elements))
