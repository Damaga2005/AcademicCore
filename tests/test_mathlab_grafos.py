# SPDX-License-Identifier: MIT
"""ML-12: árboles y grafos — contrastados con Floyd–Warshall y con fuerza bruta."""
from __future__ import annotations

import itertools
import math
import random
from fractions import Fraction as F

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import grafos as G


def _aleatorio(rng, n, m):
    nodos = [f"v{i}" for i in range(n)]
    aristas = []
    for i in range(1, n):                       # a spanning path keeps it connected
        aristas.append([nodos[i - 1], nodos[i], rng.randint(1, 9)])
    for _ in range(m):
        a, b = rng.sample(nodos, 2)
        aristas.append([a, b, rng.randint(1, 9)])
    return G.grafo(aristas)


def _floyd(g):
    d = {(a, b): (0 if a == b else math.inf) for a in g.nodos for b in g.nodos}
    for a, b, w in g.aristas:
        d[a, b] = min(d[a, b], w)
        d[b, a] = min(d[b, a], w)
    for k, i, j in itertools.product(g.nodos, repeat=3):
        d[i, j] = min(d[i, j], d[i, k] + d[k, j])
    return d


def test_dijkstra_contra_floyd_y_kruskal_contra_fuerza_bruta():
    rng = random.Random(4)
    for _ in range(40):
        g = _aleatorio(rng, rng.randint(2, 6), rng.randint(0, 6))
        fw = _floyd(g)
        c = G.dijkstra(g, g.nodos[0])
        assert all(c.distancia[n] == fw[g.nodos[0], n] for n in g.nodos)
        _, total = G.kruskal(g)
        mejor = math.inf
        for sub in itertools.combinations(g.aristas, len(g.nodos) - 1):
            if len(G.componentes(G.grafo([[a, b] for a, b, _ in sub], nodos=g.nodos))) == 1:
                mejor = min(mejor, sum(w for *_, w in sub))
        assert total == mejor


def test_hipotesis_comprobadas():
    with pytest.raises(Exception, match="HYPOTHESIS"):
        G.dijkstra(G.grafo([["a", "b", -1]]), "a")
    with pytest.raises(Exception, match="NEGATIVE_CYCLE"):
        G.bellman_ford(G.grafo([["a", "b", 1], ["b", "a", -2]], dirigido=True), "a")
    with pytest.raises(Exception, match="CYCLE"):
        G.topologico(G.grafo([["a", "b"], ["b", "c"], ["c", "a"]], dirigido=True))
    with pytest.raises(Exception, match="NOT_CONNECTED"):
        G.kruskal(G.grafo([["a", "b", 1]], nodos=["c"]))


@pytest.mark.parametrize("p,L", [
    ({"a": "1/2", "b": "1/4", "c": "1/8", "d": "1/8"}, F(7, 4)),
    ({"a": "0.4", "b": "0.2", "c": "0.2", "d": "0.1", "e": "0.1"}, F(11, 5)),
    ({"x": "1/3", "y": "1/3", "z": "1/3"}, F(5, 3)),
])
def test_huffman(p, L):
    h = G.huffman(p)
    assert h.longitud_media == L and h.kraft == 1
    codigos = list(h.codigos.values())
    assert not any(a != b and b.startswith(a) for a in codigos for b in codigos)   # prefix-free
    assert len(h.dibujo.nodos) == 2 * len(p) - 1


def test_calculadora():
    r = ML.calcular(ML.Peticion("grafo", {"calculo": "dijkstra", "origen": "A", "aristas": [
        ["A", "B", 4], ["A", "C", 2], ["C", "B", 1], ["B", "D", 5]]}))
    assert r.exacto == "B: 3 (A → C → B); C: 2 (A → C); D: 8 (A → C → B → D)"
    assert r.sello.verdict == "verificado" and len(r.traza.steps) >= 3
    r = ML.calcular(ML.Peticion("huffman", {"probabilidades": {"a": "1/2", "b": "1/2"}}))
    assert r.exacto.startswith("a: 0, b: 1; L = 1")
