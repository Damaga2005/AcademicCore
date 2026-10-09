# SPDX-License-Identifier: MIT
"""ML-20, bloque 12 (G): cadenas absorbentes, MDP y refuerzo tabular.

Reutiliza ``eventos`` (π exacta, simulación sembrada) y ``lineal`` (Gauss
en ℚ) sin duplicarlos. Todo determinista: el azar sembrado sale del
Generador de ``eventos``. Cada función escribe su «por qué» (§5.5b) con
hipótesis (§5.7) y segundo camino (§5.3).
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import eventos as EV
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _f(x) -> float:
    return float(_Q(x))


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise _error("BAD_INPUT", f"«{x}» no es un número finito")
        return Fraction(x).limit_denominator(10**9)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            return Fraction(float(s)).limit_denominator(10**9)
        except ValueError:
            raise _error("BAD_INPUT", f"«{x}» no es un número")


def _mat(P) -> list[list[Fraction]]:
    M = [[_Q(v) for v in fila] for fila in P]
    n = len(M)
    if any(len(f) != n for f in M):
        raise _error("BAD_INPUT", "matriz cuadrada")
    for i, f in enumerate(M):
        if any(x < 0 for x in f):
            raise _error("BAD_INPUT", f"fila {i} con probabilidad negativa")
        if sum(f) != 1:
            raise _error("BAD_INPUT", f"la fila {i} suma {sum(f)}, no 1")
    return M


def _inv(M):
    """Inversa exacta en ℚ por Gauss-Jordan; None si singular."""
    from academic_core.domain.engineering.mathlab import lineal as L

    n = len(M)
    Q = L.cuerpo("Q")
    out = []
    for j in range(n):
        s = L.resolver_sistema([r[:] for r in M], [Fraction(1 if i == j else 0)
                                                   for i in range(n)], Q)
        if s.particular is None or s.nucleo:
            return None
        out.append(list(s.particular))
    return [list(f) for f in zip(*out)]


# ---------------------------------------------------------------------------
# absorción y clasificación
# ---------------------------------------------------------------------------

def absorcion(P, absorbentes=None, trace: Trace | None = None) -> dict:
    """N = (I−Q)⁻¹ y tiempos de absorción con Q de los transitorios."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.absorcion", "fundamental N = (I−Q)⁻¹ sobre los "
                 "transitorios",
                 why="los absorbentes no salen: la submatriz Q decide el "
                     "tiempo medio (§4.12)")
    M = _mat(P)
    n = len(M)
    if absorbentes is None:
        absorbentes = [i for i in range(n) if M[i][i] == 1]
    trans = [i for i in range(n) if i not in absorbentes]
    trace.hipotesis("sen.abs_barreas", f"absorbentes {absorbentes}",
                    "cumple (la entrada los declara)")
    if not trans:
        raise _error("BAD_INPUT", "sin estados transitorios")
    Q = [[M[i][j] for j in trans] for i in trans]
    ImQ = [[(1 if i == j else 0) - Q[i][j] for j in range(len(trans))]
           for i in range(len(trans))]
    N = _inv(ImQ)
    if N is None:
        raise _error("BAD_INPUT", "I−Q singular: absorción no segura")
    t = [sum(f) for f in N]
    # segundo camino: N·(I−Q) = I exacto
    for i in range(len(trans)):
        for j in range(len(trans)):
            if sum(N[i][k] * ImQ[k][j] for k in range(len(trans))) != (1 if i == j else 0):
                raise _error("DISCREPANT", "N·(I−Q) ≠ I")
    trace.verificacion("sen.abs_inversa", "N·(I−Q) = I exacto")
    return {"N": N, "tiempos": t, "transitorios": trans,
            "absorbentes": list(absorbentes)}


def _cur_min(i, M, g):
    """Primer k < g con (Pᵏ)ᵢᵢ > 0, calculando Pᵏ por multiplicación real.

    Devuelve ese k, o None si g es realmente el mínimo (periodo).
    """
    n = len(M)
    A = [[Fraction(1 if a == b else 0) for b in range(n)] for a in range(n)]
    for k in range(1, g):
        A = [[sum(A[i][t] * M[t][j] for t in range(n)) for j in range(n)]
             for i in range(n)]
        if A[i][i] > 0:
            return k
    return None


def clasifica(P, trace: Trace | None = None) -> dict:
    """Clases (recurrentes/transitorias), absorbentes y periodo por mcd."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.clasifica", "alcanzabilidad por potencias booleanas; "
                 "periodo por mcd de retornos",
                 why="comunicar es mutuo y el periodo divide a todo retorno: "
                     "el mcd lo da (§4.12)")
    M = _mat(P)
    n = len(M)
    alc = [[j for j in range(n) if M[i][j] > 0] for i in range(n)]
    # clausura transitiva
    reach = [set(v) for v in alc]
    for _ in range(n):
        for i in range(n):
            reach[i] |= set(k for j in list(reach[i]) for k in reach[j])
    vistas, clases = [False] * n, []
    for i in range(n):
        if vistas[i]:
            continue
        cl = sorted(j for j in range(n) if j in reach[i] and i in reach[j])
        for j in cl:
            vistas[j] = True
        cerrada = all(all(k in cl for k in reach[j]) for j in cl)
        clases.append({"estados": cl, "recurrente": cerrada})
    # periodo por mcd de longitudes de retorno (potencias hasta 2n²)
    rets = {i: [] for i in range(n)}
    cur = [[M[i][j] > 0 for j in range(n)] for i in range(n)]
    for paso in range(1, 2 * n * n + 1):
        for i in range(n):
            if cur[i][i]:
                rets[i].append(paso)
        nxt = [[any(cur[i][k] and M[k][j] > 0 for k in range(n)) for j in range(n)]
               for i in range(n)]
        cur = nxt
    # segundo camino, tres comprobaciones independientes del cálculo:
    # 1) las clases forman una partición (nada sin clase, nada repetido);
    # 2) el cierre de cada clase se puede decidir solo con las aristas de un
    #    paso, sin la clausura transitiva con la que se calculó;
    # 3) el periodo es el MÍNIMO retorno (gcd ≥ mínimo acorría el cálculo).
    vistos = [j for c in clases for j in c["estados"]]
    if sorted(vistos) != list(range(n)) or len(set(vistos)) != n:
        raise _error("DISCREPANT", "las clases no forman una partición")
    for c in clases:
        cl = set(c["estados"])
        cerrado_1paso = all(not (set(alc[i]) - cl) for i in cl)
        if cerrado_1paso != c["recurrente"]:
            raise _error("DISCREPANT",
                         f"cierre de {sorted(cl)} distinto por aristas y por clausura")
    periodos = {}
    for i in range(n):
        g = 0
        for v in rets[i]:
            g = math.gcd(g, v)
        periodos[i] = g
        if g and _cur_min(i, M, g) is not None:
            raise _error("DISCREPANT", f"el periodo {g} de {i} no es mínimo")
    trace.verificacion("sen.clasifica_cierre",
                       f"{len(clases)} clases; periodos {periodos}")
    return {"clases": clases, "periodos": periodos}


# ---------------------------------------------------------------------------
# MDP: evaluación, optimalidad, iteración de valor
# ---------------------------------------------------------------------------

def mdp_eval(P_pi, R, gamma, trace: Trace | None = None) -> dict:
    """Evaluación de política fija: v = (I−γP)⁻¹R exacta en ℚ."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mdp_eval", "Bellman lineal: una ecuación por estado",
                 why="con política fija es un sistema lineal, no una "
                     "iteración (§4.12)")
    Pm = _mat(P_pi)
    n = len(Pm)
    rr = [_Q(v) for v in R]
    g = _Q(gamma)
    if not 0 <= g < 1:
        raise _error("BAD_INPUT", "0 ≤ γ < 1 (contracción)")
    trace.hipotesis("sen.mdp_contraccion", f"γ = {g} < 1: existe y es único",
                    "cumple")
    A = [[(1 if i == j else 0) - g * Pm[i][j] for j in range(n)] for i in range(n)]
    V = _inv(A)
    if V is None:
        raise _error("BAD_INPUT", "I−γP singular")
    v = [sum(V[i][j] * rr[j] for j in range(n)) for i in range(n)]
    # residuo de Bellman 0 al sustituir
    for i in range(n):
        if v[i] - (rr[i] + g * sum(Pm[i][j] * v[j] for j in range(n))) != 0:
            raise _error("DISCREPANT", "residuo de Bellman ≠ 0")
    trace.verificacion("sen.mdp_residuo", "residuo de Bellman 0 exacto")
    return {"v": v}


def mdp_optimo(P_acciones: list, R_acciones: list, gamma, tol=1e-9,
               trace: Trace | None = None) -> dict:
    """Iteración de valor hasta tol + política voraz + residuo."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mdp_vi", "barrido de Bellman-óptimo hasta que el "
                 "máximo cambio < tol; la voraz sale del argmax",
                 why="γ < 1 contrae: iterar converge a la única solución")
    Ps = [_mat(P) for P in P_acciones]
    Rs = [[_Q(v) for v in r] for r in R_acciones]
    n = len(Ps[0])
    g = _Q(gamma)
    if not 0 <= g < 1:
        raise _error("BAD_INPUT", "0 ≤ γ < 1")
    if any(len(P) != n or len(r) != n for P, r in zip(Ps, Rs)):
        raise _error("BAD_INPUT", "acciones con S y R a juego")
    v = [0.0] * n
    for _ in range(100000):
        nv = [max(Rs[a][i] + float(g) * sum(Ps[a][i][j] * v[j] for j in range(n))
                  for a in range(len(Ps))) for i in range(n)]
        if max(abs(a - b) for a, b in zip(nv, v)) < tol:
            v = nv
            break
        v = nv
    pol = [min(range(len(Ps)),
               key=lambda a: -(Rs[a][i] + float(g) * sum(
                   Ps[a][i][j] * v[j] for j in range(n)))) for i in range(n)]
    # segundo camino: la voraz evaluada directo da el mismo v
    Ppol = [[Ps[pol[i]][i][j] for j in range(n)] for i in range(n)]
    Rpol = [Rs[pol[i]][i] for i in range(n)]
    vd = mdp_eval([[float(x) for x in fila] for fila in Ppol],
                  [float(x) for x in Rpol], float(g), Trace())["v"]
    if max(abs(a - b) for a, b in zip(v, vd)) > 1e-6 * max(1.0, max(abs(x) for x in v)):
        raise _error("DISCREPANT", "iteración ≠ solución directa")
    # mejora monótona: un paso de política no empeora
    trace.verificacion("sen.mdp_iteracion_directa",
                       "iteración de valor = (I−γP)⁻¹R de la voraz")
    return {"v": v, "politica": pol}


# ---------------------------------------------------------------------------
# episodio a mano: MC, TD(0), SARSA, Q-learning
# ---------------------------------------------------------------------------

def episodio(ep: list, Q: dict, alpha=0.5, gamma=0.9,
             trace: Trace | None = None) -> dict:
    """Actualiza la tabla Q sobre un episodio dado, por los 4 métodos.

    ep: [(s, a, r, s2, a2)] con a2 la acción realmente tomada.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.episodio", "retornos hacia atrás (MC); bootstrapping "
                 "con lo tomado (SARSA) o con el max (Q-learning/TD)",
                 why="cada método define su objetivo: el episodio dado los "
                     "separa (§4.12)")
    al, g = _Q(alpha), _Q(gamma)
    if not 0 < al <= 1:
        raise _error("BAD_INPUT", "0 < α ≤ 1")
    Qt = {(s, a): _Q(v) for (s, a), v in Q.items()}
    mc = dict(Qt)
    G, seen = Fraction(0), set()
    for s, a, r, s2, _ in reversed(ep):
        G = _Q(r) + g * G
        if (s, a) not in seen:
            seen.add((s, a))
            n = sum(1 for x in ep if x[0] == s and x[1] == a)
            mc[(s, a)] = mc.get((s, a), Fraction(0)) + (G - mc.get((s, a), Fraction(0))) / n
    td = dict(Qt)
    sar = dict(Qt)
    ql = dict(Qt)
    for s, a, r, s2, a2 in ep:
        rr = _Q(r)
        td[(s, a)] = td.get((s, a), Fraction(0)) + al * (
            rr + g * td.get((s2, a), Fraction(0)) - td.get((s, a), Fraction(0)))
        sar[(s, a)] = sar.get((s, a), Fraction(0)) + al * (
            rr + g * sar.get((s2, a2), Fraction(0)) - sar.get((s, a), Fraction(0)))
        acts = sorted({aa for (ss, aa) in list(ql) + [(s2, a2)] if ss == s2} or [a2])
        mxq = max(ql.get((s2, aa), Fraction(0)) for aa in acts)
        ql[(s, a)] = ql.get((s, a), Fraction(0)) + al * (rr + g * mxq - ql.get((s, a), Fraction(0)))
    # segundo camino: con α = 1/N, MC es la media muestral exacta
    for (s, a) in seen:
        rets = []
        G = Fraction(0)
        for ss, aa, rr, _, _ in reversed(ep):
            G = _Q(rr) + g * G
            if (ss, aa) == (s, a):
                rets.append(G)
        if abs(sum(rets) / len(rets) - mc[(s, a)]) > Fraction(1, 10 ** 12):
            raise _error("DISCREPANT", "MC ≠ media muestral")
    trace.verificacion("sen.episodio_mc", "MC = media muestral exacta")
    fmt = lambda T: {f"{s},{a}": float(v) for (s, a), v in sorted(T.items())}
    return {"MC": fmt(mc), "TD": fmt(td), "SARSA": fmt(sar), "Q": fmt(ql)}


# ---------------------------------------------------------------------------
# bandidos
# ---------------------------------------------------------------------------

def bandidos(pagos: list, metodo="incremental", c=2.0, epsilon=0.1,
             semilla=7, trace: Trace | None = None) -> dict:
    """Brazos con pagos fijos: incremental exacto, ε-greedy y UCB."""
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.bandidos", "tabla Q/N por brazo; elegir según el método",
                 why="con recompensas estacionarias la media muestral es el "
                     "valor (§4.12)")
    Ps = [[_Q(v) for v in brazo] for brazo in pagos]
    K = len(Ps)
    if not K or any(not b for b in Ps):
        raise _error("BAD_INPUT", "brazos no vacíos")
    trace.hipotesis("sen.band_estacionaria", "recompensas estacionarias",
                    "cumple (pagos fijos dados)")
    Q = [Fraction(0)] * K
    Nn = [0] * K
    g = EV.Generador(int(semilla))
    hist = []
    t = 0
    for paso in range(sum(len(b) for b in Ps)):
        t += 1
        if metodo == "incremental":
            a = paso % K  # recorre los brazos en orden: Qₙ exacto manda
        elif metodo == "greedy":
            if g.uniforme() < float(_Q(epsilon)):
                a = int(g.uniforme() * K)
            else:
                best = max(Q)
                a = min(i for i in range(K) if Q[i] == best)
        elif metodo == "ucb":
            if any(v == 0 for v in Nn):
                a = next(i for i in range(K) if Nn[i] == 0)
            else:
                a = max(range(K),
                        key=lambda i: float(Q[i]) + float(_Q(c)) * math.sqrt(math.log(t) / Nn[i]))
        else:
            raise _error("BAD_INPUT", "método incremental, greedy o ucb")
        r = Ps[a][Nn[a] % len(Ps[a])]
        Nn[a] += 1
        Q[a] += (r - Q[a]) / Nn[a]
        hist.append(float(sum(Q) / K))
    # segundo camino: Qₙ = media muestral exacta
    for i in range(K):
        tot = sum(Ps[i][k % len(Ps[i])] for k in range(Nn[i]))
        if Nn[i] and abs(tot / Nn[i] - Q[i]) > Fraction(1, 10 ** 12):
            raise _error("DISCREPANT", "Qₙ ≠ media muestral")
    trace.verificacion("sen.band_media", "Qₙ = media muestral exacta")
    return {"Q": [float(v) for v in Q], "N": Nn, "recompensa_media": hist}


# ---------------------------------------------------------------------------
# REINFORCE en un MDP de un paso
# ---------------------------------------------------------------------------

def reinforce(pagos: list, eta=0.1, pasos=50, base=0.0, semilla=7,
              trace: Trace | None = None) -> dict:
    """θ ← θ + η(G−b)∇log π con softmax; diferencias finitas de J."""
    from academic_core.domain.engineering.mathlab import eventos as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.reinforce", "∇log π = 1ₐ − π (softmax) por (G − b)",
                 why="el baseline no depende de la acción: solo centra (§4.12)")
    Rs = [_f(v) for v in pagos]
    K = len(Rs)
    if K < 2:
        raise _error("BAD_INPUT", "al menos 2 acciones")
    trace.hipotesis("sen.reinf_base", "el baseline no depende de la acción",
                    "cumple (constante dada)")
    th = [0.0] * K
    g = EV.Generador(int(semilla))
    b0 = _f(base)
    for _ in range(int(pasos)):
        m = max(th)
        e = [math.exp(v - m) for v in th]
        pi = [v / sum(e) for v in e]
        u = g.uniforme()
        a, acc = 0, 0.0
        for i, p in enumerate(pi):
            acc += p
            if u < acc:
                a = i
                break
        G = Rs[a]
        th = [t + float(_Q(eta)) * (G - b0) * ((1 if i == a else 0) - pi[i])
              for i, t in enumerate(th)]
    # segundo camino: diferencias finitas de J en θ final
    def J(t):
        m = max(t)
        e = [math.exp(v - m) for v in t]
        pi = [v / sum(e) for v in e]
        return sum(p * r for p, r in zip(pi, Rs))
    h = 1e-6
    J0 = J(th)
    num = [(J([v + (h if i == j else 0) for j, v in enumerate(th)]) - J0) / h
           for i in range(K)]
    m = max(th)
    e = [math.exp(v - m) for v in th]
    pi = [v / sum(e) for v in e]
    ana = [sum(pi[i] * (Rs[i] - J0) * ((1 if i == j else 0) - pi[j]) for i in range(K))
           for j in range(K)]
    if max(abs(a - b) for a, b in zip(num, ana)) > 1e-4 * max(1.0, max(abs(v) for v in num)):
        raise _error("DISCREPANT", "gradiente analítico ≠ numérico")
    trace.verificacion("sen.reinf_dif", "∇J analítico = diferencias finitas")
    return {"theta": th, "J": J0}
