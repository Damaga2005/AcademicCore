# SPDX-License-Identifier: MIT
"""ML-9 (§4.6): probabilidad básica, vectores aleatorios discretos y gaussianos.

Todo con ``Fraction`` (§5.1): un árbol de Bayes con datos racionales da la
posterior exacta. Los segundos caminos (§5.3):

- **Bayes y probabilidad total**: la tabla conjunta ``P(Aᵢ ∩ B)`` reconstruida
  por otra vía (complementarios) y ``Σ P(Aᵢ | B) = 1``; simulación sembrada del
  árbol como contraste.
- **Combinatoria**: la fórmula cerrada frente a la **enumeración** directa cuando
  el espacio es pequeño (≤ 2·10⁵ casos).
- **Inclusión-exclusión**: frente a la enumeración de las regiones de Venn cuando
  los datos son de conjuntos con intersecciones dadas.
- **Tabla conjunta**: marginales que suman 1, ``Cov = E[XY] − E[X]E[Y]`` frente a
  ``E[(X−μX)(Y−μY)]`` calculado sin la fórmula abreviada.
- **Vector gaussiano**: ``Y = AX + b`` con ``μ_Y = Aμ + b`` y ``Σ_Y = AΣAᵀ``
  (exacto sobre ℚ); la condicionada y la estimación lineal óptima con la
  ortogonalidad del error ``E[e·X] = 0`` comprobada exactamente.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import probabilidad as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _f(v, que="la probabilidad") -> Fraction:
    return P.fraccion(v, que)


# ---------------------------------------------------------------------------
# probabilidad total y Bayes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bayes:
    hipotesis: tuple[str, ...]
    previas: tuple[Fraction, ...]
    verosimilitudes: tuple[Fraction, ...]
    conjuntas: tuple[Fraction, ...]
    total: Fraction
    posteriores: tuple[Fraction, ...]
    evidencia: str

    def texto(self) -> str:
        lineas = [f"P({self.evidencia}) = {self.total} ≈ {float(self.total):.6g}"]
        for h, q in zip(self.hipotesis, self.posteriores):
            lineas.append(f"P({h} | {self.evidencia}) = {q} ≈ {float(q):.6g}")
        return "; ".join(lineas)

    def arbol(self) -> list[dict]:
        """El árbol como datos dibujables (§6): raíz → Aᵢ → B / no B."""
        nodos = [{"id": "Ω", "padre": None, "etiqueta": "Ω", "p": "1"}]
        for h, pa, pb in zip(self.hipotesis, self.previas, self.verosimilitudes):
            nodos.append({"id": h, "padre": "Ω", "etiqueta": h, "p": str(pa)})
            nodos.append({"id": f"{h}∩{self.evidencia}", "padre": h,
                          "etiqueta": self.evidencia, "p": str(pb)})
            nodos.append({"id": f"{h}∩no {self.evidencia}", "padre": h,
                          "etiqueta": f"no {self.evidencia}", "p": str(1 - pb)})
        return nodos


def bayes(previas: dict, verosimilitudes: dict, evidencia: str = "B",
          trace: Trace | None = None, semilla: int = 20261007) -> Bayes:
    """``previas = {"A1": "0.5", ...}``, ``verosimilitudes = {"A1": "0.02", ...}``
    (``P(B | Aᵢ)``). Las hipótesis tienen que ser una partición: se comprueba."""
    trace = trace if trace is not None else Trace()
    if set(previas) != set(verosimilitudes):
        raise _error("BAD_INPUT", "cada hipótesis necesita su P(Aᵢ) y su P(B | Aᵢ)")
    nombres = tuple(previas)
    pa = tuple(_f(previas[h], f"P({h})") for h in nombres)
    pb = tuple(_f(verosimilitudes[h], f"P({evidencia} | {h})") for h in nombres)
    for q, h in zip(pa + pb, nombres + nombres):
        if not 0 <= q <= 1:
            raise _error("BAD_INPUT", f"{q} no es una probabilidad ({h})")
    suma = sum(pa, Fraction(0))
    trace.hipotesis("bayes.particion", f"Σ P(Aᵢ) = {suma}: las hipótesis forman una "
                                       "partición (disjuntas y cubren Ω)",
                    "se cumple" if suma == 1 else "NO se cumple")
    if suma != 1:
        raise _error("BAD_INPUT", f"Σ P(Aᵢ) = {suma} ≠ 1: las hipótesis no son una partición "
                                  "(¿falta el complementario?)")
    conj = tuple(a * b for a, b in zip(pa, pb))
    for h, a, b, c in zip(nombres, pa, pb, conj):
        trace.regla("bayes.conjunta", f"P({h} ∩ {evidencia}) = P({h})·P({evidencia} | {h}) "
                                      f"= {a}·{b} = {c}",
                    why="regla del producto: cada rama del árbol multiplica sus probabilidades")
    total = sum(conj, Fraction(0))
    trace.metodo("bayes.total", f"P({evidencia}) = Σ P(Aᵢ)·P({evidencia} | Aᵢ) = {total}",
                 why="teorema de la probabilidad total: las Aᵢ son una partición, así que B "
                     "se reparte entre ellas sin solaparse")
    if total == 0:
        raise _error("BAD_INPUT", f"P({evidencia}) = 0: no se puede condicionar a un suceso "
                                  "de probabilidad nula")
    post = tuple(c / total for c in conj)
    for h, c, q in zip(nombres, conj, post):
        trace.regla("bayes.posterior", f"P({h} | {evidencia}) = P({h} ∩ {evidencia})/P("
                                       f"{evidencia}) = {c}/{total} = {q}",
                    why="teorema de Bayes: la probabilidad condicionada es la fracción de B "
                        "que corresponde a cada hipótesis")
    # segundo camino: por el complementario y la normalización
    no_b = sum((a * (1 - b) for a, b in zip(pa, pb)), Fraction(0))
    if total + no_b != 1 or sum(post, Fraction(0)) != 1:
        raise _error("DISCREPANT", "P(B) + P(no B) ≠ 1 o las posteriores no suman 1")
    trace.verificacion("bayes.complementario",
                       f"P({evidencia}) + P(no {evidencia}) = {total} + {no_b} = 1 y "
                       f"Σ P(Aᵢ | {evidencia}) = 1 (exacto)")
    sim = P.simula(lambda g: _rama(g, pa, pb), 20000, semilla)
    if not sim.dentro(float(total)):
        raise _error("DISCREPANT", f"simulación del árbol {sim.texto()} lejos de P(B) = {total}")
    trace.verificacion("bayes.simulacion", f"simulación sembrada del árbol: P({evidencia}) ≈ "
                                           f"{sim.texto()}")
    return Bayes(nombres, pa, pb, conj, total, post, evidencia)


def _rama(g, pa, pb) -> float:
    i = g.eleccion([float(a) for a in pa])
    return 1.0 if g.uniforme() < float(pb[i]) else 0.0


# ---------------------------------------------------------------------------
# combinatoria (con convenciones: orden, repetición, distinguibles)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conteo:
    tipo: str
    formula: str
    valor: int
    enumerado: int | None


def combinatoria(tipo: str, n: int, k: int | None = None, trace: Trace | None = None,
                 grupos: list[int] | None = None) -> Conteo:
    """``tipo`` ∈ variaciones, variaciones_rep, permutaciones, permutaciones_rep,
    combinaciones, combinaciones_rep, ocupacion_distinguibles (k bolas distintas en n
    urnas), ocupacion_indistinguibles, sobreyecciones (todas las urnas ocupadas),
    desarreglos."""
    trace = trace if trace is not None else Trace()
    if n < 0 or (k is not None and k < 0):
        raise _error("BAD_INPUT", "n y k tienen que ser ≥ 0")
    t = tipo.strip().lower()
    perm = math.perm
    if t == "variaciones":
        valor, formula = perm(n, k), f"V({n},{k}) = {n}!/({n}−{k})!"
        enum = _enumera(lambda: itertools.permutations(range(n), k), n, k)
        conv = "importa el orden, sin repetición"
    elif t == "variaciones_rep":
        valor, formula = n ** k, f"VR({n},{k}) = {n}^{k}"
        enum = _enumera(lambda: itertools.product(range(n), repeat=k), n, k)
        conv = "importa el orden, con repetición"
    elif t == "permutaciones":
        valor, formula = math.factorial(n), f"P({n}) = {n}!"
        enum = _enumera(lambda: itertools.permutations(range(n)), n, n)
        conv = "se ordenan los n elementos"
    elif t == "permutaciones_rep":
        g = grupos or []
        if sum(g) != n:
            raise _error("BAD_INPUT", f"los grupos suman {sum(g)} y no n = {n}")
        valor = math.factorial(n)
        for m in g:
            valor //= math.factorial(m)
        formula = f"{n}!/(" + "·".join(f"{m}!" for m in g) + ")"
        multiconjunto = [i for i, m in enumerate(g) for _ in range(m)]
        enum = (len(set(itertools.permutations(multiconjunto)))
                if math.factorial(n) <= 200000 else None)
        conv = "permutaciones de un multiconjunto (elementos repetidos indistinguibles)"
    elif t == "combinaciones":
        valor, formula = math.comb(n, k), f"C({n},{k}) = {n}!/({k}!·({n}−{k})!)"
        enum = _enumera(lambda: itertools.combinations(range(n), k), n, k)
        conv = "no importa el orden, sin repetición"
    elif t == "combinaciones_rep":
        valor, formula = math.comb(n + k - 1, k), f"CR({n},{k}) = C({n}+{k}−1, {k})"
        enum = _enumera(lambda: itertools.combinations_with_replacement(range(n), k), n, k)
        conv = "no importa el orden, con repetición"
    elif t == "ocupacion_distinguibles":
        valor, formula = n ** k, f"{n}^{k} (cada una de las {k} bolas elige urna)"
        enum = _enumera(lambda: itertools.product(range(n), repeat=k), n, k)
        conv = f"{k} bolas DISTINGUIBLES en {n} urnas"
    elif t == "ocupacion_indistinguibles":
        valor, formula = math.comb(n + k - 1, k), f"C({n}+{k}−1, {k}) (barras y estrellas)"
        enum = _enumera(lambda: itertools.combinations_with_replacement(range(n), k), n, k)
        conv = f"{k} bolas INDISTINGUIBLES en {n} urnas"
    elif t == "sobreyecciones":
        valor = sum((-1) ** j * math.comb(n, j) * (n - j) ** k for j in range(n + 1))
        formula = f"Σ_j (−1)^j·C({n},j)·({n}−j)^{k} (inclusión-exclusión)"
        enum = (sum(1 for c in itertools.product(range(n), repeat=k) if len(set(c)) == n)
                if n ** k <= 200000 else None)
        conv = f"{k} bolas distinguibles en {n} urnas, ninguna vacía"
    elif t == "desarreglos":
        valor = sum((-1) ** j * math.factorial(n) // math.factorial(j) for j in range(n + 1))
        formula = f"!{n} = {n}!·Σ_j (−1)^j/j!"
        enum = (sum(1 for p in itertools.permutations(range(n)) if all(p[i] != i for i in range(n)))
                if math.factorial(n) <= 200000 else None)
        conv = "permutaciones sin ningún punto fijo"
    else:
        raise _error("BAD_INPUT", f"tipo de recuento «{tipo}» no reconocido")
    trace.convencion("combinatoria.modelo", conv)
    trace.regla("combinatoria.formula", f"{formula} = {valor}",
                why="se elige la fórmula por las dos preguntas del modelo: ¿importa el orden? "
                    "¿se puede repetir?")
    if enum is not None:
        if enum != valor:
            raise _error("DISCREPANT", f"la enumeración da {enum} y la fórmula {valor}")
        trace.verificacion("combinatoria.enumeracion", f"enumeración directa: {enum} casos")
    else:
        trace.aviso("combinatoria.sin_enumeracion", "espacio demasiado grande para "
                                                    "enumerarlo: solo la fórmula")
    return Conteo(t, formula, valor, enum)


def _enumera(gen, n, k) -> int | None:
    if k is None:
        return None
    try:
        tam = max(n, 1) ** max(k, 1)
    except OverflowError:
        return None
    if tam > 200000 and math.comb(n + k, k) > 200000:
        return None
    contador = 0
    for _ in gen():
        contador += 1
        if contador > 400000:
            return None
    return contador


# ---------------------------------------------------------------------------
# inclusión-exclusión y Venn
# ---------------------------------------------------------------------------


def inclusion_exclusion(datos: dict, trace: Trace | None = None) -> dict:
    """``{"A": "0.5", "B": "0.4", "C": "0.3", "AB": "0.2", "AC": "0.1", "BC": "0.1",
    "ABC": "0.05"}`` → P(A ∪ B ∪ C), las regiones de Venn y la independencia."""
    trace = trace if trace is not None else Trace()
    simples = sorted(c for c in datos if len(c) == 1)
    if not 1 <= len(simples) <= 4:
        raise _error("BAD_INPUT", "entre 1 y 4 sucesos de una letra")
    p = {}
    for r in range(1, len(simples) + 1):
        for comb in itertools.combinations(simples, r):
            clave = "".join(comb)
            if clave not in datos:
                raise _error("BAD_INPUT", f"falta P({'∩'.join(comb)})")
            p[clave] = _f(datos[clave], f"P({clave})")
    union = Fraction(0)
    for r in range(1, len(simples) + 1):
        s = sum((p["".join(c)] for c in itertools.combinations(simples, r)), Fraction(0))
        union += (-1) ** (r + 1) * s
        trace.regla("ie.termino", f"{'+' if r % 2 else '−'} Σ intersecciones de {r} = {s}")
    trace.metodo("ie.union", f"P({' ∪ '.join(simples)}) = {union}",
                 why="inclusión-exclusión: se suman los sucesos, se restan las intersecciones "
                     "dobles que se contaron dos veces, se suman las triples…")
    # segundo camino: regiones de Venn por Möbius (cada región exclusiva ≥ 0)
    regiones = {}
    for r in range(len(simples), 0, -1):
        for comb in itertools.combinations(simples, r):
            clave = "".join(comb)
            exclusiva = p[clave] - sum((regiones[o] for o in regiones
                                        if set(clave) < set(o)), Fraction(0))
            regiones[clave] = exclusiva
    for k, v in regiones.items():
        if v < 0:
            raise _error("BAD_INPUT", f"los datos son incoherentes: la región solo-{k} tendría "
                                      f"probabilidad {v} < 0")
    suma_reg = sum(regiones.values(), Fraction(0))
    if suma_reg != union or union > 1:
        raise _error("DISCREPANT", f"las regiones suman {suma_reg} y la unión da {union}")
    trace.verificacion("ie.venn", f"las {len(regiones)} regiones de Venn (todas ≥ 0) suman "
                                  f"{suma_reg}, igual que la unión")
    indep = {}
    for r in range(2, len(simples) + 1):
        for comb in itertools.combinations(simples, r):
            prod = Fraction(1)
            for c in comb:
                prod *= p[c]
            indep["".join(comb)] = (p["".join(comb)] == prod, prod)
    return {"union": union, "ninguno": 1 - union, "regiones": regiones, "independencia": indep}


# ---------------------------------------------------------------------------
# vector discreto (tabla conjunta)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conjunta:
    xs: tuple[Fraction, ...]
    ys: tuple[Fraction, ...]
    p: tuple[tuple[Fraction, ...], ...]
    px: tuple[Fraction, ...]
    py: tuple[Fraction, ...]
    EX: Fraction
    EY: Fraction
    VX: Fraction
    VY: Fraction
    EXY: Fraction
    cov: Fraction
    rho2: Fraction            # ρ² exacto (ρ puede ser irracional)
    independientes: bool
    recta: tuple[Fraction, Fraction] | None   # Ŷ = a + b·X (estimación lineal óptima)
    condicionada: tuple[Fraction, ...]        # E[Y | X = xᵢ]

    def rho(self) -> float:
        if self.VX == 0 or self.VY == 0:
            return math.nan
        return float(self.cov) / math.sqrt(float(self.VX * self.VY))


def tabla_conjunta(xs, ys, p, trace: Trace | None = None) -> Conjunta:
    """``p[i][j] = P(X = xs[i], Y = ys[j])``."""
    trace = trace if trace is not None else Trace()
    X = tuple(_f(v, "x") for v in xs)
    Y = tuple(_f(v, "y") for v in ys)
    if len(p) != len(X) or any(len(fila) != len(Y) for fila in p):
        raise _error("BAD_INPUT", "la tabla tiene que ser len(xs) × len(ys)")
    T = tuple(tuple(_f(v) for v in fila) for fila in p)
    if any(v < 0 for fila in T for v in fila):
        raise _error("BAD_INPUT", "una probabilidad negativa")
    total = sum((v for fila in T for v in fila), Fraction(0))
    trace.hipotesis("conjunta.normalizada", f"Σ p(x, y) = {total}", "se cumple" if total == 1
                    else "NO se cumple")
    if total != 1:
        raise _error("BAD_INPUT", f"la tabla suma {total} y no 1")
    px = tuple(sum(fila, Fraction(0)) for fila in T)
    py = tuple(sum((T[i][j] for i in range(len(X))), Fraction(0)) for j in range(len(Y)))
    trace.regla("conjunta.marginales", f"p_X = ({', '.join(map(str, px))}); "
                                       f"p_Y = ({', '.join(map(str, py))})",
                why="la marginal suma la conjunta sobre la otra variable")
    EX = sum((x * q for x, q in zip(X, px)), Fraction(0))
    EY = sum((y * q for y, q in zip(Y, py)), Fraction(0))
    VX = sum((x * x * q for x, q in zip(X, px)), Fraction(0)) - EX * EX
    VY = sum((y * y * q for y, q in zip(Y, py)), Fraction(0)) - EY * EY
    EXY = sum((X[i] * Y[j] * T[i][j] for i in range(len(X)) for j in range(len(Y))), Fraction(0))
    cov = EXY - EX * EY
    trace.regla("conjunta.momentos", f"E[X] = {EX}, E[Y] = {EY}, Var X = {VX}, Var Y = {VY}, "
                                     f"E[XY] = {EXY}, Cov = E[XY] − E[X]E[Y] = {cov}")
    cov2 = sum(((X[i] - EX) * (Y[j] - EY) * T[i][j] for i in range(len(X))
                for j in range(len(Y))), Fraction(0))
    if cov2 != cov:
        raise _error("DISCREPANT", f"Cov por definición {cov2} ≠ {cov}")
    trace.verificacion("conjunta.cov_definicion", "E[(X − μX)(Y − μY)] da la misma covarianza "
                                                  "(exacto)")
    indep = all(T[i][j] == px[i] * py[j] for i in range(len(X)) for j in range(len(Y)))
    if indep:
        trace.regla("conjunta.independencia", "p(x, y) = p_X(x)·p_Y(y) en TODAS las casillas: "
                                              "independientes")
    else:
        i, j = next((i, j) for i in range(len(X)) for j in range(len(Y))
                    if T[i][j] != px[i] * py[j])
        trace.regla("conjunta.independencia",
                    f"no independientes: p({X[i]}, {Y[j]}) = {T[i][j]} ≠ {px[i]}·{py[j]} = "
                    f"{px[i] * py[j]}" + (" (aunque Cov = 0: incorreladas no implica "
                                          "independientes)" if cov == 0 else ""))
    rho2 = cov * cov / (VX * VY) if VX and VY else Fraction(0)
    recta = None
    if VX:
        b = cov / VX
        a = EY - b * EX
        recta = (a, b)
        trace.metodo("conjunta.estimacion_lineal", f"Ŷ = a + b·X con b = Cov/Var X = {b}, "
                                                   f"a = E[Y] − b·E[X] = {a}",
                     why="minimiza E[(Y − a − bX)²]: derivando en a y b sale el error "
                         "ortogonal a 1 y a X")
        e_err = sum(((Y[j] - a - b * X[i]) * T[i][j] for i in range(len(X))
                     for j in range(len(Y))), Fraction(0))
        ex_err = sum(((Y[j] - a - b * X[i]) * X[i] * T[i][j] for i in range(len(X))
                      for j in range(len(Y))), Fraction(0))
        if e_err != 0 or ex_err != 0:
            raise _error("DISCREPANT", "el error de la recta no es ortogonal")
        trace.verificacion("conjunta.ortogonalidad", "E[e] = 0 y E[e·X] = 0 exactos")
    cond = tuple((sum((Y[j] * T[i][j] for j in range(len(Y))), Fraction(0)) / px[i])
                 if px[i] else Fraction(0) for i in range(len(X)))
    trace.regla("conjunta.esperanza_condicional",
                "E[Y | X = x] = " + ", ".join(f"{c} (x = {x})" for x, c in zip(X, cond)),
                why="es el mejor estimador (no necesariamente lineal) de Y a partir de X")
    return Conjunta(X, Y, T, px, py, EX, EY, VX, VY, EXY, cov, rho2, indep, recta, cond)


# ---------------------------------------------------------------------------
# vector gaussiano
# ---------------------------------------------------------------------------


def _mat(M) -> list[list[Fraction]]:
    return [[_f(v, "un elemento") for v in fila] for fila in M]


def _mul(A, B):
    return [[sum((A[i][k] * B[k][j] for k in range(len(B))), Fraction(0))
             for j in range(len(B[0]))] for i in range(len(A))]


def _t(A):
    return [list(c) for c in zip(*A)]


def _inv(A):
    n = len(A)
    M = [list(f) + [Fraction(int(i == j)) for j in range(n)] for i, f in enumerate(A)]
    for c in range(n):
        piv = next((r for r in range(c, n) if M[r][c] != 0), None)
        if piv is None:
            raise _error("SINGULAR", "la matriz de covarianza no es invertible")
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [fila[n:] for fila in M]


def _det(A) -> Fraction:
    n = len(A)
    M = [list(f) for f in A]
    det = Fraction(1)
    for c in range(n):
        piv = next((r for r in range(c, n) if M[r][c] != 0), None)
        if piv is None:
            return Fraction(0)
        if piv != c:
            M[c], M[piv] = M[piv], M[c]
            det = -det
        det *= M[c][c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return det


def semidefinida_positiva(S) -> bool:
    """Todos los menores principales (no solo los directores) ≥ 0: criterio exacto."""
    n = len(S)
    for r in range(1, n + 1):
        for idx in itertools.combinations(range(n), r):
            if _det([[S[i][j] for j in idx] for i in idx]) < 0:
                return False
    return True


def gaussiano_lineal(mu, S, A, b=None, trace: Trace | None = None) -> dict:
    """``Y = A·X + b`` con ``X ~ N(μ, Σ)``: ``μ_Y = Aμ + b``, ``Σ_Y = AΣAᵀ``."""
    trace = trace if trace is not None else Trace()
    mu = [_f(v, "μ") for v in mu]
    S = _mat(S)
    A = _mat(A)
    n = len(mu)
    if len(S) != n or any(len(f) != n for f in S) or any(len(f) != n for f in A):
        raise _error("BAD_INPUT", "dimensiones incompatibles")
    if any(S[i][j] != S[j][i] for i in range(n) for j in range(n)):
        raise _error("BAD_INPUT", "Σ no es simétrica")
    if not semidefinida_positiva(S):
        raise _error("BAD_INPUT", "Σ no es semidefinida positiva: no es una covarianza")
    trace.hipotesis("gauss.covarianza", "Σ simétrica y semidefinida positiva (menores "
                                        "principales ≥ 0)", "se cumple")
    bb = [_f(v, "b") for v in (b or [0] * len(A))]
    muY = [sum((A[i][k] * mu[k] for k in range(n)), Fraction(0)) + bb[i] for i in range(len(A))]
    SY = _mul(_mul(A, S), _t(A))
    trace.regla("gauss.lineal", f"μ_Y = Aμ + b = {[str(v) for v in muY]}; Σ_Y = AΣAᵀ = "
                                f"{[[str(v) for v in f] for f in SY]}",
                why="una transformación lineal de un vector gaussiano es gaussiana; la media "
                    "y la covarianza se transforman así por linealidad de la esperanza")
    # segundo camino: Cov(Yi, Yj) = Σ_k Σ_l a_ik a_jl σ_kl elemento a elemento
    for i in range(len(A)):
        for j in range(len(A)):
            c = sum((A[i][k] * A[j][l] * S[k][l] for k in range(n) for l in range(n)), Fraction(0))
            if c != SY[i][j]:
                raise _error("DISCREPANT", "AΣAᵀ por elementos no coincide")
    trace.verificacion("gauss.elementos", "Cov(Yᵢ, Yⱼ) = Σₖₗ aᵢₖ·aⱼₗ·σₖₗ elemento a elemento "
                                          "(exacto)")
    indep = [(i, j) for i in range(len(A)) for j in range(i + 1, len(A)) if SY[i][j] == 0]
    return {"media": muY, "cov": SY, "incorreladas": indep}


def gaussiano_condicional(mu, S, observadas: dict, trace: Trace | None = None) -> dict:
    """``X_a | X_b = x_b``: ``μ = μ_a + Σ_ab Σ_bb⁻¹ (x_b − μ_b)``,
    ``Σ = Σ_aa − Σ_ab Σ_bb⁻¹ Σ_ba`` (índices desde 1)."""
    trace = trace if trace is not None else Trace()
    mu = [_f(v, "μ") for v in mu]
    S = _mat(S)
    n = len(mu)
    b = sorted(int(k) - 1 for k in observadas)
    if any(not 0 <= i < n for i in b):
        raise _error("BAD_INPUT", "índice observado fuera de rango")
    a = [i for i in range(n) if i not in b]
    xb = [_f(observadas[str(i + 1)] if str(i + 1) in observadas else observadas[i + 1], "x")
          for i in b]
    Sab = [[S[i][j] for j in b] for i in a]
    Sbb = [[S[i][j] for j in b] for i in b]
    Saa = [[S[i][j] for j in a] for i in a]
    K = _mul(Sab, _inv(Sbb))
    media = [mu[a[r]] + sum((K[r][c] * (xb[c] - mu[b[c]]) for c in range(len(b))), Fraction(0))
             for r in range(len(a))]
    cov = [[Saa[r][s] - sum((K[r][c] * Sab[s][c] for c in range(len(b))), Fraction(0))
            for s in range(len(a))] for r in range(len(a))]
    trace.regla("gauss.condicional", f"μ_(a|b) = μ_a + Σ_ab·Σ_bb⁻¹·(x_b − μ_b) = "
                                     f"{[str(v) for v in media]}; Σ_(a|b) = Σ_aa − Σ_ab·Σ_bb⁻¹·Σ_ba "
                                     f"= {[[str(v) for v in f] for f in cov]}",
                why="la condicionada de un vector gaussiano es gaussiana; Σ_ab·Σ_bb⁻¹ es la "
                    "matriz de la estimación lineal óptima, que aquí es además la óptima")
    # segundo camino: el error X_a − E[X_a | X_b] es incorrelado con X_b
    for r in range(len(a)):
        for c in range(len(b)):
            v = Sab[r][c] - sum((K[r][k] * Sbb[k][c] for k in range(len(b))), Fraction(0))
            if v != 0:
                raise _error("DISCREPANT", "el error no es ortogonal a las observaciones")
    trace.verificacion("gauss.ortogonalidad", "Cov(X_a − K·X_b, X_b) = Σ_ab − K·Σ_bb = 0 "
                                              "(exacto)")
    return {"indices": [i + 1 for i in a], "media": media, "cov": cov, "K": K}


def densidad_gaussiana_2d(mu, S):
    """La densidad conjunta de un vector gaussiano 2D, para las curvas de nivel."""
    s11, s12, s22 = float(S[0][0]), float(S[0][1]), float(S[1][1])
    det = s11 * s22 - s12 * s12
    m1, m2 = float(mu[0]), float(mu[1])

    def f(x, y):
        dx, dy = x - m1, y - m2
        q = (s22 * dx * dx - 2 * s12 * dx * dy + s11 * dy * dy) / det
        return math.exp(-q / 2) / (2 * math.pi * math.sqrt(det))
    return f
