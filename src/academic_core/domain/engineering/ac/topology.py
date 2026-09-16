"""Topology helpers for the F8-D3 AC engine (ground, reachability, cycles).

Rules are identical to F8-B (same ground convention, same reachability
criterion) but implemented here with edge identity, which the AC
branch-oriented KVL verification needs and F8-B's node-only chord
helper does not provide:

* ground: the single net whose stripped uppercase name is ``0``/``GND``;
* reachability: every net must reach ground through component branches
  (union-find over 2-pin edges);
* cycle basis: fundamental cycles over the branch multigraph with
  (branch_index, traversal_sign) steps, so parallel edges between the
  same node pair stay distinct.

Input is read-only: only ``.nets`` / ``.components`` / ``.pins`` are
inspected, never mutated.
"""

from __future__ import annotations

from academic_core.domain.engineering.ac.errors import (
    FloatingCircuitError,
    MissingReferenceError,
)


def reference_net(nets) -> str:
    """Return the single reference net (F8-B rule, AC reuse)."""
    candidates = sorted({net for net in nets if net.strip().upper() in ("0", "GND")})
    if not candidates:
        raise MissingReferenceError(
            "circuit has no reference node "
            "(expected a net named '0' or 'GND', case-insensitive)"
        )
    if len(candidates) > 1:
        raise MissingReferenceError(
            f"ambiguous/incompatible reference nodes: {candidates!r} "
            "(only one '0'/'GND' net is allowed)"
        )
    return candidates[0]


def check_connected(nets, components, ground: str) -> None:
    """Raise FloatingCircuitError if any net cannot reach ground."""
    parent: dict[str, str] = {net: net for net in nets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in components:
        pin_nets = list(c.pins.values())
        for other in pin_nets[1:]:
            ra, rb = find(pin_nets[0]), find(other)
            if ra != rb:
                parent[ra] = rb
    ground_root = find(ground)
    unreachable = sorted(net for net in nets if find(net) != ground_root)
    if unreachable:
        raise FloatingCircuitError(
            f"node(s) with no path to the reference node {ground!r}: "
            f"{unreachable!r}"
        )


def cycle_basis(edges: list[tuple[str, str]]) -> list[list[tuple[int, int]]]:
    """Fundamental cycle basis over a branch multigraph with edge identity.

    ``edges`` maps branch_index -> (node_a, node_b); every branch is its
    own edge even when several share one node pair. Returns one cycle per
    chord as a list of ``(branch_index, sign)`` steps, where ``sign`` is
    +1 when the cycle traverses the branch a→b and -1 for b→a. For a
    connected graph the count equals E - V + 1.
    """
    adjacency: dict[str, list[tuple[str, int]]] = {}
    for eid, (a, b) in enumerate(edges):
        adjacency.setdefault(a, []).append((b, eid))
        adjacency.setdefault(b, []).append((a, eid))
    roots = list(adjacency)
    if not roots:
        return []
    parent: dict[str, str | None] = {}
    parent_edge: dict[str, int] = {}
    tree_edges: set[int] = set()
    for root in adjacency:
        if root in parent:
            continue
        parent[root] = None
        order = [root]
        pos = 0
        while pos < len(order):
            cur = order[pos]
            pos += 1
            for nxt, eid in adjacency[cur]:
                if nxt not in parent:
                    parent[nxt] = cur
                    parent_edge[nxt] = eid
                    tree_edges.add(eid)
                    order.append(nxt)

    def oriented(eid: int, frm: str, to: str) -> int:
        a, b = edges[eid]
        if frm == a and to == b:
            return +1
        if frm == b and to == a:
            return -1
        raise AssertionError(f"edge {eid} does not join {frm!r} to {to!r}")

    def ancestors(node: str) -> list[str]:
        chain = [node]
        while parent[chain[-1]] is not None:
            chain.append(parent[chain[-1]])  # type: ignore[arg-type]
        return chain

    cycles = []
    for eid, (a, b) in enumerate(edges):
        if eid in tree_edges or a == b:
            # Self-loops are skipped: their drop is v - v == 0 identically.
            continue
        anc_a = ancestors(a)
        set_a = set(anc_a)
        node = b
        while node not in set_a:
            node = parent[node]  # type: ignore[assignment]
        lca = node
        steps: list[tuple[int, int]] = []
        node = a
        while node != lca:
            nxt = parent[node]
            assert nxt is not None
            steps.append((parent_edge[node], oriented(parent_edge[node], node, nxt)))
            node = nxt
        down: list[str] = []
        node = b
        while node != lca:
            down.append(node)
            nxt = parent[node]
            assert nxt is not None
            node = nxt
        down.append(lca)
        down.reverse()
        for u, v in zip(down, down[1:]):
            steps.append((parent_edge[v], oriented(parent_edge[v], u, v)))
        steps.append((eid, oriented(eid, b, a)))  # close b -> a through the chord
        cycles.append(steps)
    return cycles
    return cycles
