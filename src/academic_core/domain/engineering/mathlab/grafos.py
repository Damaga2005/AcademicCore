# SPDX-License-Identifier: MIT
"""ML-12 (§5.10.6): trees and graphs, solved step by step and drawable as data.

Graph algorithms of the course, each with its table of steps and a second path:

- BFS / DFS (order of visit; ties by the order the edges were given);
- Dijkstra (table of tentative distances) — checked by Bellman–Ford, which also
  catches what Dijkstra cannot handle: a negative weight is refused, not ignored;
- Kruskal (edges in order, union–find) — checked by Prim: both must give the
  same total weight;
- topological order (Kahn) — checked edge by edge; a cycle is reported with its
  vertices;
- connected components;
- Huffman codes — average length checked by an independent formula (the sum of
  the weights of the internal nodes), Kraft's sum = 1 and H ≤ L < H + 1.

Trees come out as :class:`Dibujo`: nodes with coordinates and labelled edges,
data that any lab draws its own way (§5.9: never an image).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

MAX_NODOS = 200


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


@dataclass(frozen=True)
class Grafo:
    nodos: tuple[str, ...]
    aristas: tuple[tuple[str, str, Fraction], ...]
    dirigido: bool = False

    def vecinos(self, u: str) -> list[tuple[str, Fraction]]:
        salida = [(b, w) for a, b, w in self.aristas if a == u]
        if not self.dirigido:
            salida += [(a, w) for a, b, w in self.aristas if b == u]
        return salida


def grafo(aristas, dirigido: bool = False, nodos=()) -> Grafo:
    leidas = []
    vistos: list[str] = [str(n) for n in nodos]
    for arista in aristas:
        if len(arista) not in (2, 3):
            raise _error("BAD_INPUT", "una arista es [origen, destino] o [origen, destino, peso]")
        a, b = str(arista[0]), str(arista[1])
        w = Fraction(str(arista[2])) if len(arista) == 3 else Fraction(1)
        leidas.append((a, b, w))
        for n in (a, b):
            if n not in vistos:
                vistos.append(n)
    if len(vistos) > MAX_NODOS:
        raise _error("EXPRESSION_LIMIT", f"más de {MAX_NODOS} nodos")
    return Grafo(tuple(vistos), tuple(leidas), dirigido)


def _existe(G: Grafo, n: str) -> None:
    if n not in G.nodos:
        raise _error("BAD_INPUT", f"el nodo «{n}» no está en el grafo")


# ---------------------------------------------------------------------------
# traversals
# ---------------------------------------------------------------------------


def bfs(G: Grafo, origen: str, trace: Trace | None = None) -> list[str]:
    trace = trace if trace is not None else Trace()
    _existe(G, origen)
    orden, cola, vistos = [], [origen], {origen}
    while cola:
        u = cola.pop(0)
        orden.append(u)
        nuevos = [v for v, _ in G.vecinos(u) if v not in vistos]
        for v in nuevos:
            vistos.add(v)
            cola.append(v)
        trace.regla("bfs.visita", f"visita {u}; a la cola: {', '.join(nuevos) or '—'}",
                    after=f"cola = [{', '.join(cola)}]")
    return orden


def dfs(G: Grafo, origen: str, trace: Trace | None = None) -> list[str]:
    trace = trace if trace is not None else Trace()
    _existe(G, origen)
    orden: list[str] = []

    def visitar(u: str) -> None:
        orden.append(u)
        trace.regla("dfs.visita", f"visita {u}", after=" → ".join(orden))
        for v, _ in G.vecinos(u):
            if v not in orden:
                visitar(v)

    visitar(origen)
    return orden


def componentes(G: Grafo) -> list[list[str]]:
    no_dirigido = Grafo(G.nodos, G.aristas, False)
    pendientes, salida = list(G.nodos), []
    while pendientes:
        comp = bfs(no_dirigido, pendientes[0])
        salida.append(comp)
        pendientes = [n for n in pendientes if n not in comp]
    return salida


# ---------------------------------------------------------------------------
# shortest paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Caminos:
    origen: str
    distancia: dict[str, Fraction | None]
    previo: dict[str, str | None]

    def camino(self, destino: str) -> list[str]:
        if self.distancia.get(destino) is None:
            return []
        c = [destino]
        while self.previo[c[-1]] is not None:
            c.append(self.previo[c[-1]])
        return c[::-1]

    def texto(self) -> str:
        partes = []
        for n, d in self.distancia.items():
            if n == self.origen:
                continue
            partes.append(f"{n}: ∞" if d is None else f"{n}: {d} ({' → '.join(self.camino(n))})")
        return "; ".join(partes)


def dijkstra(G: Grafo, origen: str, trace: Trace | None = None) -> Caminos:
    trace = trace if trace is not None else Trace()
    _existe(G, origen)
    negativas = [(a, b, w) for a, b, w in G.aristas if w < 0]
    if negativas:
        a, b, w = negativas[0]
        raise _error("HYPOTHESIS", f"Dijkstra exige pesos ≥ 0 y la arista {a}–{b} pesa {w}: "
                                   "usa Bellman–Ford")
    trace.hipotesis("dijkstra.pesos", "todos los pesos son ≥ 0", "se cumple")
    dist: dict[str, Fraction | None] = {n: None for n in G.nodos}
    previo: dict[str, str | None] = {n: None for n in G.nodos}
    dist[origen] = Fraction(0)
    orden = {n: i for i, n in enumerate(G.nodos)}
    monticulo = [(Fraction(0), orden[origen], origen)]
    cerrados: set[str] = set()
    while monticulo:
        d, _, u = heapq.heappop(monticulo)
        if u in cerrados:
            continue
        cerrados.add(u)
        mejoras = []
        for v, w in G.vecinos(u):
            if v in cerrados:
                continue
            if dist[v] is None or d + w < dist[v]:
                dist[v], previo[v] = d + w, u
                heapq.heappush(monticulo, (d + w, orden[v], v))
                mejoras.append(f"{v} = {d + w}")
        trace.regla("dijkstra.cierra", f"se cierra {u} (d = {d}); mejora: "
                                       f"{', '.join(mejoras) or '—'}",
                    after="  ".join(f"{n}:{'∞' if x is None else x}" for n, x in dist.items()))
    resultado = Caminos(origen, dist, previo)
    if bellman_ford(G, origen).distancia != dist:
        raise _error("INTERNAL", "Dijkstra y Bellman–Ford no coinciden")
    trace.verificacion("dijkstra.bellman_ford", "Bellman–Ford da las mismas distancias")
    return resultado


def bellman_ford(G: Grafo, origen: str) -> Caminos:
    _existe(G, origen)
    dist: dict[str, Fraction | None] = {n: None for n in G.nodos}
    previo: dict[str, str | None] = {n: None for n in G.nodos}
    dist[origen] = Fraction(0)
    arcos = list(G.aristas) + ([] if G.dirigido else [(b, a, w) for a, b, w in G.aristas])
    for _ in range(len(G.nodos) - 1):
        cambio = False
        for a, b, w in arcos:
            if dist[a] is not None and (dist[b] is None or dist[a] + w < dist[b]):
                dist[b], previo[b], cambio = dist[a] + w, a, True
        if not cambio:
            break
    for a, b, w in arcos:
        if dist[a] is not None and (dist[b] is None or dist[a] + w < dist[b]):
            raise _error("NEGATIVE_CYCLE", "hay un ciclo de peso negativo alcanzable: "
                                           "no existe camino mínimo")
    return Caminos(origen, dist, previo)


# ---------------------------------------------------------------------------
# spanning trees and order
# ---------------------------------------------------------------------------


def kruskal(G: Grafo, trace: Trace | None = None) -> tuple[list[tuple[str, str, Fraction]], Fraction]:
    trace = trace if trace is not None else Trace()
    if G.dirigido:
        raise _error("HYPOTHESIS", "el árbol generador mínimo es de grafos no dirigidos")
    padre = {n: n for n in G.nodos}

    def raiz(n: str) -> str:
        while padre[n] != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n

    elegidas, total = [], Fraction(0)
    for a, b, w in sorted(G.aristas, key=lambda e: e[2]):    # stable: ties keep input order
        ra, rb = raiz(a), raiz(b)
        if ra == rb:
            trace.regla("kruskal.descarta", f"{a}–{b} ({w}) cerraría un ciclo")
            continue
        padre[ra] = rb
        elegidas.append((a, b, w))
        total += w
        trace.regla("kruskal.elige", f"{a}–{b} ({w})", after=f"peso acumulado {total}")
    if len(elegidas) != len(G.nodos) - 1:
        raise _error("NOT_CONNECTED", "el grafo no es conexo: no hay árbol generador")
    if prim(G) != total:
        raise _error("INTERNAL", "Kruskal y Prim no dan el mismo peso")
    trace.verificacion("kruskal.prim", f"Prim da el mismo peso total {total}")
    return elegidas, total


def prim(G: Grafo) -> Fraction:
    inicio = G.nodos[0]
    dentro, total = {inicio}, Fraction(0)
    monticulo = [(w, i, v) for i, (v, w) in enumerate(G.vecinos(inicio))]
    heapq.heapify(monticulo)
    contador = len(monticulo)
    while monticulo and len(dentro) < len(G.nodos):
        w, _, v = heapq.heappop(monticulo)
        if v in dentro:
            continue
        dentro.add(v)
        total += w
        for x, wx in G.vecinos(v):
            if x not in dentro:
                contador += 1
                heapq.heappush(monticulo, (wx, contador, x))
    return total


def topologico(G: Grafo, trace: Trace | None = None) -> list[str]:
    trace = trace if trace is not None else Trace()
    if not G.dirigido:
        raise _error("HYPOTHESIS", "el orden topológico es de grafos dirigidos")
    entrada = {n: 0 for n in G.nodos}
    for _, b, _ in G.aristas:
        entrada[b] += 1
    libres = [n for n in G.nodos if entrada[n] == 0]
    orden = []
    while libres:
        u = libres.pop(0)
        orden.append(u)
        for v, _ in G.vecinos(u):
            entrada[v] -= 1
            if entrada[v] == 0:
                libres.append(v)
        trace.regla("kahn.saca", f"{u} (sin predecesores pendientes)", after=" → ".join(orden))
    if len(orden) < len(G.nodos):
        ciclo = [n for n in G.nodos if n not in orden]
        raise _error("CYCLE", f"hay un ciclo: quedan sin ordenar {', '.join(ciclo)} (el ciclo "
                              "está entre ellos); no hay orden topológico")
    posicion = {n: i for i, n in enumerate(orden)}
    if any(posicion[a] >= posicion[b] for a, b, _ in G.aristas):
        raise _error("INTERNAL", "una arista apunta hacia atrás")
    trace.verificacion("kahn.aristas", "cada arista va de un nodo anterior a uno posterior")
    return orden


# ---------------------------------------------------------------------------
# Huffman, and trees as drawable data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Nodo:
    id: str
    etiqueta: str
    x: float
    y: float


@dataclass(frozen=True)
class Dibujo:
    nodos: tuple[Nodo, ...]
    aristas: tuple[tuple[str, str, str], ...]      # (from, to, label)
    descripcion: str


@dataclass(frozen=True)
class Huffman:
    codigos: dict[str, str]
    longitud_media: Fraction
    entropia: float
    kraft: Fraction
    dibujo: Dibujo

    def texto(self) -> str:
        cods = ", ".join(f"{s}: {c}" for s, c in self.codigos.items())
        return (f"{cods}; L = {self.longitud_media} bits/símbolo, H = {self.entropia:.6g} "
                f"bits; eficiencia H/L = {self.entropia / float(self.longitud_media):.4g}")


def huffman(probabilidades: dict[str, object], trace: Trace | None = None) -> Huffman:
    trace = trace if trace is not None else Trace()
    try:
        p = {str(s): Fraction(str(v)) for s, v in probabilidades.items()}
    except ZeroDivisionError:
        raise _error("BAD_INPUT", "una probabilidad tiene denominador 0") from None
    if len(p) < 2:
        raise _error("BAD_INPUT", "Huffman necesita al menos dos símbolos")
    if any(v <= 0 for v in p.values()):
        raise _error("BAD_INPUT", "las probabilidades tienen que ser positivas")
    if sum(p.values()) != 1:
        raise _error("BAD_INPUT", f"las probabilidades suman {sum(p.values())}, no 1")
    # (weight, tie-break, id); a tree node is (id, left, right)
    monticulo = [(w, i, s) for i, (s, w) in enumerate(p.items())]
    heapq.heapify(monticulo)
    hijos: dict[str, tuple[str, str]] = {}
    pesos = dict(p)
    contador, internos = len(monticulo), Fraction(0)
    while len(monticulo) > 1:
        w1, _, a = heapq.heappop(monticulo)
        w2, _, b = heapq.heappop(monticulo)
        contador += 1
        nuevo = f"n{contador}"
        hijos[nuevo] = (a, b)
        pesos[nuevo] = w1 + w2
        internos += w1 + w2
        trace.regla("huffman.une", f"se unen {a} ({w1}) y {b} ({w2}) → {w1 + w2}",
                    why="siempre los dos de menor probabilidad")
        heapq.heappush(monticulo, (w1 + w2, contador, nuevo))
    raiz = monticulo[0][2]
    codigos: dict[str, str] = {}

    def asignar(n: str, prefijo: str) -> None:
        if n in hijos:
            asignar(hijos[n][0], prefijo + "0")
            asignar(hijos[n][1], prefijo + "1")
        else:
            codigos[n] = prefijo
    asignar(raiz, "")
    codigos = {s: codigos[s] for s in p}
    L = sum(p[s] * len(c) for s, c in codigos.items())
    H = -sum(float(v) * math.log2(float(v)) for v in p.values())
    kraft = sum(Fraction(1, 2 ** len(c)) for c in codigos.values())
    if L != internos:
        raise _error("INTERNAL", "la longitud media no coincide con la suma de nodos internos")
    trace.verificacion("huffman.internos", f"L = Σ pesos de los nodos internos = {internos}")
    if kraft != 1:
        raise _error("INTERNAL", "un código de Huffman cumple Kraft con igualdad")
    trace.verificacion("huffman.kraft", "Σ 2^(−ℓᵢ) = 1")
    if not (H - 1e-12 <= float(L) < H + 1):
        raise _error("INTERNAL", "no se cumple H ≤ L < H + 1")
    trace.verificacion("huffman.cota", f"H = {H:.6g} ≤ L = {L} < H + 1")
    etiquetas = {n: f"{s} ({p[s]})" for s, n in ((s, s) for s in p)}
    etiquetas.update({n: str(pesos[n]) for n in hijos})
    dibujo = dibujar_arbol(raiz, hijos, etiquetas, ("0", "1"),
                           f"árbol de Huffman de {len(p)} símbolos")
    return Huffman(codigos, L, H, kraft, dibujo)


def dibujar_arbol(raiz: str, hijos: dict[str, tuple[str, ...]], etiquetas: dict[str, str],
                  rotulos: tuple[str, ...] = (), descripcion: str = "") -> Dibujo:
    """Leaves at consecutive x, each parent centred over its children, depth = −y."""
    nodos: list[Nodo] = []
    aristas: list[tuple[str, str, str]] = []
    hoja = [0]

    def colocar(n: str, profundidad: int) -> float:
        h = hijos.get(n, ())
        if not h:
            x = float(hoja[0])
            hoja[0] += 1
        else:
            xs = [colocar(c, profundidad + 1) for c in h]
            x = sum(xs) / len(xs)
            for i, c in enumerate(h):
                aristas.append((n, c, rotulos[i] if i < len(rotulos) else ""))
        nodos.append(Nodo(n, etiquetas.get(n, n), x, -float(profundidad)))
        return x

    colocar(raiz, 0)
    return Dibujo(tuple(nodos), tuple(aristas), descripcion)
