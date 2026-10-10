# SPDX-License-Identifier: MIT
"""ML-17, bloque 11 (G): entropía, información mutua, divergencia KL,
entropía cruzada, Huffman/Kraft (vía ``grafos``), capacidad de canal y
coste en bits de claves y cumpleaños.

Todo exacto en ℚ donde la entrada lo es (log₂ por cambio de base frente a
suma directa) o numérico declarado. Sin dependencias.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        raise _error("BAD_INPUT", f"«{x}» no es un número racional")


def _norm(probs: list, nombre="distribución") -> list[Fraction]:
    ps = [_Q(p) for p in probs]
    if any(p < 0 for p in ps):
        raise _error("BAD_INPUT", f"{nombre} con probabilidad negativa")
    if sum(ps) != 1:
        raise _error("BAD_INPUT", f"{nombre} no normalizada (suma {sum(ps)})")
    return ps


def _h2(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def entropia(probs: list, trace: Trace | None = None) -> dict:
    """H = −Σ p·log₂p (0·log0 = 0); uniforme da log₂N."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.entropia", "tabla → log₂ → suma con 0·log0 = 0",
                 why="definición directa sobre la tabla")
    ps = _norm(probs)
    H = sum(-float(p) * math.log2(float(p)) for p in ps if p > 0)
    N = len(ps)
    if all(p == ps[0] for p in ps) and abs(H - math.log2(N)) > 1e-9:
        raise _error("DISCREPANT", "el uniforme no da log₂N")
    trace.verificacion("sen.entropia_uniforme", f"H = {H:.6g} bits")
    return {"H": H}


def conjunta(tabla: list[list], trace: Trace | None = None) -> dict:
    """H(X,Y), H(X|Y), H(Y|X), I(X;Y) y regla de la cadena."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conjunta", "conjunta → marginales → condicionadas → mutua",
                 why="todas salen de la tabla conjunta por marginalización")
    P = [[_Q(v) for v in fila] for fila in tabla]
    tot = sum(sum(f) for f in P)
    if tot != 1:
        raise _error("BAD_INPUT", f"tabla no normalizada (suma {tot})")
    px = [sum(f) for f in P]
    py = [sum(P[i][j] for i in range(len(P))) for j in range(len(P[0]))]

    def H(ps):
        return sum(-float(p) * math.log2(float(p)) for p in ps if p > 0)

    Hxy = H([v for f in P for v in f])
    Hx, Hy = H(px), H(py)
    # H(X|Y) = Σ_y p(y)·H(X|Y=y)
    Hxy_y = 0.0
    for j in range(len(py)):
        if py[j] > 0:
            Hxy_y += float(py[j]) * H([P[i][j] / py[j] for i in range(len(P))])
    I = Hx + Hy - Hxy
    if abs((Hx + Hxy_y) - Hxy) > 1e-9 * max(1.0, Hxy):
        raise _error("DISCREPANT", "H(X,Y) ≠ H(Y) + H(X|Y)")
    if I < -1e-9:
        raise _error("DISCREPANT", "I < 0")
    trace.verificacion("sen.conjunta_cadena",
                       f"H(X,Y) = {Hxy:.6g}; I = {max(I, 0.0):.6g} ≥ 0")
    return {"Hxy": Hxy, "Hx": Hx, "Hy": Hy, "Hx_dado_y": Hxy_y, "I": max(I, 0.0)}


def divergencia(p: list, q: list, trace: Trace | None = None) -> dict:
    """D(p‖q) = Σ p·log₂(p/q); infinita si q = 0 donde p > 0."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.divergencia", "suma término a término con 0·log0 = 0",
                 why="definición; el soporte de q manda")
    ps = _norm(p, "p")
    qs = [_Q(v) for v in q]
    if any(v < 0 for v in qs) or sum(qs) != 1:
        raise _error("BAD_INPUT", "q no normalizada")
    if len(ps) != len(qs):
        raise _error("BAD_INPUT", "p y q de distinta longitud")
    D = 0.0
    for a, b in zip(ps, qs):
        if a > 0:
            if b == 0:
                trace.verificacion("sen.divergencia_inf",
                                   "q = 0 donde p > 0: D = +∞")
                return {"D": math.inf, "H_cruz": math.inf}
            D += float(a) * math.log2(float(a) / float(b))
    H = sum(-float(a) * math.log2(float(a)) for a in ps if a > 0)
    if D < -1e-9:
        raise _error("DISCREPANT", "D < 0")
    trace.verificacion("sen.divergencia_cruzada",
                       f"H(p,q) = H(p) + D = {H + D:.6g}")
    return {"D": D, "H_cruz": H + D}


def kraft(longitudes: list[int], trace: Trace | None = None) -> dict:
    """Σ 2^{−lᵢ} ≤ 1 (igualdad en Huffman completo); H ≤ L̄ < H+1 se ve fuera."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.kraft", "sumar las potencias diádicas",
                 why="Kraft decide si unas longitudes pueden ser prefijo")
    ls = [int(_Q(v)) for v in longitudes]
    if any(v <= 0 for v in ls):
        raise _error("BAD_INPUT", "longitudes ≥ 1")
    if not ls:
        raise _error("BAD_INPUT", "faltan las longitudes")
    K = sum(Fraction(1, 2 ** v) for v in ls)
    # segundo camino: si K ≤ 1 se construye el código canónico y se comprueba que
    # es prefijo; si K > 1 la construcción tiene que fallar
    palabras, c, prev = [], 0, None
    for l in sorted(ls):
        if prev is not None:
            c = (c + 1) << (l - prev)
        prev = l
        palabras.append(format(c, f"0{l}b") if c < 2 ** l else None)
    construible = None not in palabras and not any(
        q.startswith(p) for i, p in enumerate(palabras) for j, q in enumerate(palabras) if i != j)
    if construible != (K <= 1):
        raise _error("DISCREPANT", "Kraft y la construcción canónica no coinciden")
    trace.verificacion("sen.kraft_suma",
                       f"K = {float(K):.6g} {'= 1 (completo)' if K == 1 else '≤ 1' if K < 1 else '> 1 (no prefijo)'}")
    return {"K": K, "prefijo_posible": K <= 1}


def capacidad(tipo: str, param, trace: Trace | None = None) -> dict:
    """BSC: 1−H₂(p); BEC: 1−ε; Shannon-Hartley: B·log₂(1+SNR)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.capacidad", "fórmula del canal con la convención de SNR",
                 why="cada canal tiene su capacidad cerrada")
    if tipo == "BSC":
        p = float(_Q(param))
        if not 0 <= p <= 1:
            raise _error("BAD_INPUT", "0 ≤ p ≤ 1")
        C = 1 - _h2(p)
        if abs(p - 0.5) < 1e-15 and abs(C) > 1e-12:
            raise _error("DISCREPANT", "C_BSC(0,5) ≠ 0")
    elif tipo == "BEC":
        e = float(_Q(param))
        if not 0 <= e <= 1:
            raise _error("BAD_INPUT", "0 ≤ ε ≤ 1")
        C = 1 - e
    elif tipo == "hartley":
        B, snr_db = float(_Q(param[0])), float(_Q(param[1]))
        snr = 10 ** (snr_db / 10)
        C = B * math.log2(1 + snr)
        trace.hipotesis("sen.capacidad_snr",
                        f"SNR {snr_db} dB → lineal {snr:.6g} (convención dB declarada)",
                        "cumple")
    else:
        raise _error("BAD_INPUT", "canal BSC, BEC o hartley")
    trace.verificacion("sen.capacidad_valor", f"C = {C:.6g}")
    return {"C": C}


def coste_clave(bits: int, intentos_por_s: float = 1e9,
                trace: Trace | None = None) -> dict:
    """Espacio 2ᵏ y tiempo medio 2^{k−1}/tasa; cumpleaños 2^{n/2}."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.clave", "contar → log₂ → tiempo con tasa declarada",
                 why="el coste es exponencial en bits: se mide en log₂")
    k = int(_Q(bits))
    tasa = float(_Q(intentos_por_s))
    if not (k >= 0 and tasa > 0):
        raise _error("BAD_INPUT", "bits ≥ 0 y tasa > 0")
    trace.hipotesis("sen.clave_uniforme", "elección uniforme (las humanas no "
                    "lo son: sobrestima)",
                    "aviso registrado")
    t = 2 ** (k - 1) / tasa if k else 0.0
    trace.verificacion("sen.clave_log2", f"espacio 2^{k}; cumpleaños 2^{k // 2}")
    return {"espacio": 2 ** k, "tiempo_medio_s": t, "cumpleanos_bits": k // 2}
