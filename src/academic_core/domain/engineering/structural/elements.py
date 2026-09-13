"""Circuit graph representation and structural element extraction (Phase 7-B8).

Provides deterministic extraction of nodes, branches, series/parallel groups,
loop bases (for KVL), node cutsets (for KCL), and reduction analysis.
Pure domain logic: no external dependencies, no I/O, fully deterministic.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Sequence

from academic_core.domain.engineering.circuit import Circuit, Component


@dataclass(frozen=True)
class StructuralNode:
    """A net / node in the circuit graph with canonical structural properties."""

    name: str
    connected_pins: tuple[tuple[str, str], ...]  # sorted ((ref, pin), ...)
    is_reference: bool
    is_floating: bool

    @property
    def degree(self) -> int:
        return len(self.connected_pins)

    @property
    def connected_components(self) -> tuple[str, ...]:
        return tuple(sorted({ref for ref, _ in self.connected_pins}))


@dataclass(frozen=True)
class StructuralBranch:
    """An electrical branch connecting two nodes."""

    id: str  # canonical ID, e.g. "R1(1-2)"
    ref: str
    type: str
    node1: str
    node2: str

    @property
    def nodes(self) -> tuple[str, str]:
        return (self.node1, self.node2)

    @property
    def is_self_loop(self) -> bool:
        return self.node1 == self.node2


class CircuitGraph:
    """Deterministic graph representation of a canonical Circuit."""

    def __init__(self, circuit: Circuit):
        self.circuit_name: str = circuit.name
        self.components: dict[str, Component] = {
            c.ref.upper(): c for c in sorted(circuit.components, key=lambda c: c.ref.upper())
        }
        self.raw_nets: set[str] = set(circuit.nets)

        # Build nodes map
        node_pins: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for comp in self.components.values():
            for pin, net in comp.pins.items():
                net_str = str(net).strip()
                node_pins[net_str].append((comp.ref.upper(), str(pin)))

        self.nodes: dict[str, StructuralNode] = {}
        for net_name in sorted(node_pins.keys()):
            pins_sorted = tuple(sorted(node_pins[net_name], key=lambda x: (x[0], x[1])))
            is_ref = net_name.upper() in ("0", "GND")
            is_flt = len(pins_sorted) <= 1
            self.nodes[net_name] = StructuralNode(
                name=net_name,
                connected_pins=pins_sorted,
                is_reference=is_ref,
                is_floating=is_flt,
            )

        # Build branches for 2-terminal components
        self.branches: list[StructuralBranch] = []
        for comp in self.components.values():
            pins = comp.pins
            if comp.type.upper() in ("R", "C", "L"):
                n1, n2 = str(pins.get("1", "")), str(pins.get("2", ""))
                bid = f"{comp.ref.upper()}({min(n1, n2)}-{max(n1, n2)})"
                self.branches.append(StructuralBranch(bid, comp.ref.upper(), comp.type.upper(), n1, n2))
            elif comp.type.upper() in ("V", "I"):
                np, nm = str(pins.get("+", "")), str(pins.get("-", ""))
                bid = f"{comp.ref.upper()}({np}->{nm})"
                self.branches.append(StructuralBranch(bid, comp.ref.upper(), comp.type.upper(), np, nm))
            else:
                # 3-terminal or others (e.g. Q, D)
                pin_list = sorted(pins.items())
                bid = f"{comp.ref.upper()}(" + ",".join(f"{p}:{n}" for p, n in pin_list) + ")"
                n1 = pin_list[0][1] if len(pin_list) > 0 else ""
                n2 = pin_list[1][1] if len(pin_list) > 1 else n1
                self.branches.append(StructuralBranch(bid, comp.ref.upper(), comp.type.upper(), n1, n2))

        self.branches.sort(key=lambda b: b.id)

    # -- Reference node & Ground -----------------------------------------------
    @property
    def reference_node(self) -> str | None:
        """Find canonical reference / GND node if present."""
        for n in self.nodes.values():
            if n.is_reference:
                return n.name
        return None

    # -- Connectivity & Disconnected Subgraphs ---------------------------------
    def get_connected_components(self) -> list[set[str]]:
        """Return connected components of nodes using deterministic BFS."""
        visited: set[str] = set()
        adj: dict[str, set[str]] = defaultdict(set)
        for b in self.branches:
            if b.node1 and b.node2:
                adj[b.node1].add(b.node2)
                adj[b.node2].add(b.node1)

        components: list[set[str]] = []
        for n in sorted(self.nodes.keys()):
            if n not in visited:
                comp_nodes: set[str] = set()
                queue = deque([n])
                visited.add(n)
                while queue:
                    curr = queue.popleft()
                    comp_nodes.add(curr)
                    for neighbor in sorted(adj[curr]):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(comp_nodes)
        return components

    @property
    def is_connected(self) -> bool:
        """A non-empty circuit is connected if all nodes belong to a single subgraph."""
        if not self.nodes:
            return True
        return len(self.get_connected_components()) <= 1

    @property
    def floating_nodes(self) -> list[str]:
        """Nodes that have degree <= 1 (floating pins)."""
        return sorted([n.name for n in self.nodes.values() if n.is_floating])

    # -- Short circuit & loop anomalies ----------------------------------------
    def has_invalid_voltage_short(self) -> bool:
        """Check for direct short circuit across an ideal voltage source."""
        for b in self.branches:
            if b.type == "V" and b.is_self_loop:
                return True
        # Check parallel V sources with opposite polarity or parallel with wire
        return False

    # -- Series & Parallel Components -----------------------------------------
    def get_parallel_groups(self) -> list[tuple[str, ...]]:
        """Find groups of 2-terminal components connected in parallel.

        Two or more components are in parallel if they connect the exact same pair of nodes.
        """
        pair_map: dict[tuple[str, str], list[str]] = defaultdict(list)
        for b in self.branches:
            if b.type in ("R", "C", "L", "V", "I"):
                key = (min(b.node1, b.node2), max(b.node1, b.node2))
                pair_map[key].append(b.ref)

        groups: list[tuple[str, ...]] = []
        for key in sorted(pair_map.keys()):
            refs = sorted(pair_map[key])
            if len(refs) >= 2:
                groups.append(tuple(refs))
        return sorted(groups)

    def get_series_pairs(self) -> list[tuple[str, str]]:
        """Find pairs of 2-terminal components connected in series.

        Two components are in series if they share a node of degree 2 that connects
        strictly those two components and nothing else.
        """
        pairs: list[tuple[str, str]] = []
        for node_name, node in self.nodes.items():
            if node.degree == 2:
                comps = node.connected_components
                if len(comps) == 2:
                    c1, c2 = min(comps[0], comps[1]), max(comps[0], comps[1])
                    pairs.append((c1, c2))
        return sorted(list(set(pairs)))

    def get_series_chains(self) -> list[tuple[str, ...]]:
        """Find maximal paths of series-connected 2-terminal components."""
        res_chains = self.get_resistor_series_chains()
        chains = [r[0] for r in res_chains]
        return sorted(chains)

    def get_resistor_series_chains(
        self,
    ) -> list[tuple[tuple[str, ...], tuple[str, str], tuple[str, ...]]]:
        """Find maximal chains of series-connected resistors.

        Returns list of tuples:
        (resistors_tuple, (terminal_start, terminal_end), intermediate_nodes_tuple)
        """
        # Internal series nodes have degree 2 in the circuit and connect strictly 2 resistors
        internal_nodes: dict[str, tuple[str, str]] = {}
        for name, node in self.nodes.items():
            if node.degree == 2:
                comps = node.connected_components
                if len(comps) == 2:
                    c1, c2 = comps[0], comps[1]
                    if self.components[c1].type == "R" and self.components[c2].type == "R":
                        internal_nodes[name] = (min(c1, c2), max(c1, c2))

        if not internal_nodes:
            return []

        adj: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for n, (r1, r2) in internal_nodes.items():
            adj[r1].add((r2, n))
            adj[r2].add((r1, n))

        chains: list[tuple[tuple[str, ...], tuple[str, str], tuple[str, ...]]] = []
        visited: set[str] = set()

        endpoints = [r for r, neighbors in adj.items() if len(neighbors) == 1]
        start_nodes = sorted(endpoints) if endpoints else sorted(adj.keys())

        for start in start_nodes:
            if start not in visited:
                chain = [start]
                inter_nodes: list[str] = []
                visited.add(start)
                curr = start
                while True:
                    next_steps = [(r, n) for r, n in sorted(adj[curr]) if r not in visited]
                    if len(next_steps) == 1:
                        nxt_r, mid_n = next_steps[0]
                        chain.append(nxt_r)
                        inter_nodes.append(mid_n)
                        visited.add(nxt_r)
                        curr = nxt_r
                    else:
                        break
                if len(chain) >= 2:
                    first_comp = self.components[chain[0]]
                    last_comp = self.components[chain[-1]]
                    first_nets = {str(first_comp.pins["1"]), str(first_comp.pins["2"])} - set(inter_nodes)
                    last_nets = {str(last_comp.pins["1"]), str(last_comp.pins["2"])} - set(inter_nodes)
                    t1 = sorted(first_nets)[0] if first_nets else ""
                    t2 = sorted(last_nets)[0] if last_nets else ""
                    terminals = (min(t1, t2), max(t1, t2))
                    chains.append((tuple(chain), terminals, tuple(sorted(inter_nodes))))
        return sorted(chains, key=lambda c: c[0])


    # -- KCL & KVL Foundations ------------------------------------------------
    def get_kcl_nodes(self) -> list[str]:
        """Essential / non-datum nodes for applying Kirchhoff's Current Law.

        Returns all non-reference nodes with degree >= 2, sorted canonically.
        If no reference node exists, returns all nodes with degree >= 2.
        """
        ref = self.reference_node
        kcl_nodes: list[str] = []
        for name, node in self.nodes.items():
            if ref is not None and name == ref:
                continue
            if node.degree >= 2:
                kcl_nodes.append(name)
        return sorted(kcl_nodes)

    def get_fundamental_loops(self) -> list[list[str]]:
        """Extract a deterministic fundamental cycle basis (loops) for KVL.

        Uses a deterministic spanning FOREST over the branch graph (one tree per
        connected component) to find fundamental cycles corresponding to chords
        (co-tree edges). This generalizes correctly to disconnected circuits:
        for a graph with E branches, V nodes and C connected components, the
        cycle rank (number of fundamental loops) is mu = E - V + C, since a
        spanning forest has exactly (V - C) tree edges.
        """
        if not self.branches:
            return []

        # Graph of node -> list of (neighbor, comp_ref)
        adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for b in self.branches:
            if b.node1 and b.node2 and not b.is_self_loop:
                adj[b.node1].append((b.node2, b.ref))
                adj[b.node2].append((b.node1, b.ref))

        # Build a spanning forest via deterministic BFS: start from the
        # reference node's component first (if any), then any remaining
        # unvisited nodes in canonical sorted order -- one BFS tree per
        # connected component.
        tree_edges: set[tuple[str, str, str]] = set()  # (min(u,v), max(u,v), ref)
        parent: dict[str, tuple[str, str]] = {}  # node -> (parent_node, ref)
        visited: set[str] = set()

        ordered_starts: list[str] = []
        ref_node = self.reference_node
        if ref_node is not None:
            ordered_starts.append(ref_node)
        ordered_starts.extend(n for n in sorted(self.nodes.keys()) if n != ref_node)

        for start_node in ordered_starts:
            if start_node in visited:
                continue
            visited.add(start_node)
            queue = deque([start_node])
            while queue:
                u = queue.popleft()
                for v, ref in sorted(adj[u], key=lambda x: (x[0], x[1])):
                    if v not in visited:
                        visited.add(v)
                        edge_key = (min(u, v), max(u, v), ref)
                        tree_edges.add(edge_key)
                        parent[v] = (u, ref)
                        queue.append(v)

        # Chords are branches not in the spanning tree
        loops: list[list[str]] = []
        seen_chords: set[tuple[str, str, str]] = set()

        for b in self.branches:
            if b.is_self_loop:
                continue
            chord_key = (min(b.node1, b.node2), max(b.node1, b.node2), b.ref)
            if chord_key not in tree_edges and chord_key not in seen_chords:
                seen_chords.add(chord_key)
                # Find tree path between b.node1 and b.node2
                # Trace back to LCA
                path1 = []
                curr = b.node1
                while curr in parent:
                    p, r = parent[curr]
                    path1.append((curr, r))
                    curr = p
                path1.append((curr, None))

                path2 = []
                curr = b.node2
                while curr in parent:
                    p, r = parent[curr]
                    path2.append((curr, r))
                    curr = p
                path2.append((curr, None))

                # Find LCA
                ancestors1 = {node: i for i, (node, _) in enumerate(path1)}
                lca = None
                lca_idx2 = 0
                for j, (node, _) in enumerate(path2):
                    if node in ancestors1:
                        lca = node
                        lca_idx2 = j
                        break

                loop_refs = [b.ref]
                if lca is not None:
                    lca_idx1 = ancestors1[lca]
                    for _, r in path1[:lca_idx1]:
                        if r:
                            loop_refs.append(r)
                    for _, r in path2[:lca_idx2]:
                        if r:
                            loop_refs.append(r)

                loops.append(sorted(set(loop_refs)))

        loops.sort(key=lambda l: (len(l), l))
        return loops

    # -- Reducible Resistor Network Checker ------------------------------------
    def is_resistor_network_reducible(self) -> bool:
        """Check if the resistor subnetwork is completely reducible via series/parallel steps.

        Applies iterative reduction on the resistor multigraph:
        1. Parallel merge: merge multiple resistors between same pair of nodes.
        2. Series merge: eliminate internal degree-2 nodes connecting strictly two resistors.
        Boundary nodes (connecting to sources or external terminals) are never eliminated.
        Terminates when no further reduction is possible.
        If the remaining graph has <= 1 resistor or <= 2 nodes, it is series-parallel reducible.
        """
        # Collect only resistor branches
        res_branches: list[tuple[str, str, str]] = []  # (u, v, ref)
        for b in self.branches:
            if b.type == "R":
                res_branches.append((min(b.node1, b.node2), max(b.node1, b.node2), b.ref))

        if not res_branches:
            return False
        if len(res_branches) <= 2:
            return True

        # Boundary nodes connect to non-resistor components (e.g. V, I)
        boundary_nodes: set[str] = set()
        for b in self.branches:
            if b.type != "R":
                boundary_nodes.add(b.node1)
                boundary_nodes.add(b.node2)

        # Mutable multigraph of edges
        edges = list(res_branches)

        changed = True
        while changed:
            changed = False
            # 1. Parallel reduction
            pair_count: dict[tuple[str, str], list[str]] = defaultdict(list)
            for u, v, ref in edges:
                if u != v:
                    pair_count[(min(u, v), max(u, v))].append(ref)

            new_edges = []
            for (u, v), refs in pair_count.items():
                if len(refs) > 1:
                    changed = True
                    # Merge into a single equivalent edge
                    new_edges.append((u, v, f"({'+'.join(sorted(refs))})"))
                else:
                    new_edges.append((u, v, refs[0]))
            edges = new_edges

            # 2. Series reduction: find internal nodes with degree 2 in this resistor graph
            node_deg: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
            for u, v, ref in edges:
                node_deg[u].append((u, v, ref))
                node_deg[v].append((u, v, ref))

            # Find an internal degree-2 node (NOT a boundary terminal!)
            elim_node = None
            for n, inc_edges in sorted(node_deg.items()):
                if n in boundary_nodes:
                    continue
                if len(inc_edges) == 2:
                    e1, e2 = inc_edges[0], inc_edges[1]
                    u1 = e1[0] if e1[1] == n else e1[1]
                    u2 = e2[0] if e2[1] == n else e2[1]
                    if u1 != u2:
                        elim_node = (n, e1, e2, u1, u2)
                        break

            if elim_node is not None:
                n, e1, e2, u1, u2 = elim_node
                edges.remove(e1)
                edges.remove(e2)
                merged_ref = f"({e1[2]}+{e2[2]})"
                edges.append((min(u1, u2), max(u1, u2), merged_ref))
                changed = True

        return len(edges) <= 1

