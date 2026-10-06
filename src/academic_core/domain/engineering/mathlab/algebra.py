# SPDX-License-Identifier: MIT
"""ML-3: álgebra lineal exacta sobre ℚ — autovalores, Gram-Schmidt y mínimos cuadrados.

Lo que ya estaba (lineal.py, cuerpo como parámetro; complejos.py) no se toca:
aquí van las piezas que faltaban de MATH_LAB §4.3/§15.1 con pasos y segundo
camino propios:

- autovalores 2×2 exactos (los complejos conjugados como par a±bi) y 3×3 con
  espectro racional (característico cúbico por raíces racionales exactas);
- autovectores como núcleo de (A−λI) con el motor lineal, solo para λ racional;
- diagonalización A = PDP⁻¹ comprobada por A·P = P·D;
- Gram-Schmidt clásico exacto con comprobación de ortogonalidad dos a dos;
- Cramer pedagógico (cada xᵢ = det(Aᵢ)/det(A), verificado por sustitución);
- mínimos cuadrados por ecuaciones normales y pseudoinversa (AᵀA)⁻¹Aᵀ cuando
  A tiene rango columna completo; si no, rechazo con su motivo.

Todo en Fraction exactos; la traza lleva cada paso con su «por qué».
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _a_frac(M) -> list[list[Fraction]]:
    return [[Fraction(x) for x in fila] for fila in M]


def _cuadrada(A) -> int:
    n = len(A)
    if n == 0 or any(len(f) != n for f in A):
        raise _error("NOT_SQUARE", "se necesita una matriz cuadrada")
    return n


def polinomio_caracteristico(A, trace: Trace | None = None) -> list[Fraction]:
    """Coeficientes [c0..cn] de det(A − λI), exactos (Leverrier-Faddeeva)."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    n = _cuadrada(A)
    if n > 3:
        raise _no(f"característico de {n}×{n}: solo 2×2 y 3×3 exactos")
    K = L.cuerpo("Q")
    coefs = _leverrier(A, K)
    trace.regla("algebra.caracteristico", f"p(λ) = {_texto_poli(coefs)}",
                why="2×2: λ² − tr·λ + det; 3×3: λ³ − tr·λ² + ½(tr² − tr(A²))·λ − det")
    return coefs


def _leverrier(A, K) -> list[Fraction]:
    """Característico mónico por fórmulas directas (2×2 y 3×3), exactas."""
    n = len(A)
    if n == 2:
        tr = A[0][0] + A[1][1]
        det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
        return [det, -tr, Fraction(1)]
    # λ³ − tr·λ² + ½(tr² − tr(A²))·λ − det
    tr = sum(A[i][i] for i in range(3))
    A2 = [[sum(A[i][k] * A[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    tr2 = sum(A2[i][i] for i in range(3))
    det = (A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1])
           - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0])
           + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]))
    return [-det, (tr * tr - tr2) / 2, -tr, Fraction(1)]


def _texto_poli(coefs: list[Fraction]) -> str:
    partes = []
    for k in range(len(coefs) - 1, -1, -1):
        c = coefs[k]
        if c == 0:
            continue
        if k == 0:
            partes.append(f"{c}")
        elif k == 1:
            partes.append(f"{c}·λ" if c not in (1, -1) else ("λ" if c == 1 else "−λ"))
        else:
            partes.append(f"{c}·λ^{k}" if c not in (1, -1)
                          else (f"λ^{k}" if c == 1 else f"−λ^{k}"))
    return " + ".join(partes).replace("+ −", "− ")


@dataclass(frozen=True)
class Autovalor:
    valor: Fraction | tuple[Fraction, Fraction]  # real o (re, im)
    multiplicidad: int

    def texto(self) -> str:
        base = str(self.valor) if isinstance(self.valor, Fraction) else \
            f"{self.valor[0]} ± {abs(self.valor[1])}i"
        return base if self.multiplicidad == 1 else f"{base} (mult. {self.multiplicidad})"


def autovalores(A, trace: Trace | None = None) -> list:
    """Espectro exacto 2×2 siempre (reales en ℚ(√r) si hace falta, complejos como
    par conjugado); 3×3 si es racional; si no, con su motivo."""
    from academic_core.domain.engineering.mathlab import mvexpr as mx
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    n = _cuadrada(A)
    coefs = polinomio_caracteristico(A, trace)
    if n == 2:
        a, b, c = coefs[2], coefs[1], coefs[0]
        disc = b * b - 4 * a * c
        k, libre = RZ._raiz_simplificada(abs(disc))
        if disc >= 0 and libre == 1:
            vals = [(-b + k) / (2 * a), (-b - k) / (2 * a)]
            vals = sorted(vals)
            trace.regla("algebra.autovalores", f"λ = {vals[0]}, {vals[1]} (Δ = {disc} ≥ 0)",
                        why="cuadrática exacta sobre ℚ")
            _verifica_autovalores(A, coefs, vals, trace)
            return vals
        if disc >= 0:
            # reales irracionales a ± b·√r: exactos en ℚ(√r), no complejos
            re, rk = -b / (2 * a), k / (2 * a)
            vals = [RZ._mas_raiz(re, rk, libre), RZ._mas_raiz(re, -rk, libre)]
            trace.regla("algebra.autovalores",
                        f"λ = {mx.text(vals[0])}, {mx.text(vals[1])} (Δ = {disc} > 0 "
                        "no cuadrado)",
                        why="raíces reales exactas en ℚ(√r)")
            _verifica_autovalores_flotante(coefs, vals, trace)
            return vals
        # par complejo conjugado exacto
        re = -b / (2 * a)
        im = k / (2 * a)
        trace.regla("algebra.autovalores", f"λ = {re} ± {im}·√{libre}·i (Δ = {disc} < 0)",
                    why="discriminante negativo: conjugados exactos, no aproximados")
        return [(re, im), (re, -im)]
    # n == 3: raíces racionales exactas del cúbico
    r = RZ.raices_polinomio(coefs)
    exactas = [mx_valor(v) for v in r.raices if v.exacta]
    if len(exactas) != 3 or any(m != 1 for m in [v.multiplicidad for v in r.raices]):
        if len(exactas) != sum(v.multiplicidad for v in r.raices if v.exacta):
            raise _no("cúbico con raíz irracional o compleja: el espectro 3×3 solo es "
                      "exacto con raíces racionales")
    vals = sorted(exactas)
    trace.regla("algebra.autovalores", f"λ = {', '.join(str(v) for v in vals)}",
                why="raíces racionales exactas del característico cúbico")
    _verifica_autovalores(A, coefs, vals, trace)
    return vals


def mx_valor(r) -> Fraction:
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    v = mx.exact_value(r.valor)
    if v is None:
        raise _no("raíz no racional del característico")
    return Fraction(v)


def _verifica_autovalores(A, coefs, vals, trace) -> None:
    """Segundo camino: cada λ anula p(λ), y traza = Σλ, det = Πλ."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    for v in vals:
        if not isinstance(v, Fraction):
            continue
        if RZ._eval(coefs, v) != 0:
            raise _error("INTERNAL", f"λ = {v} no anula el característico")
    reales = [v for v in vals if isinstance(v, Fraction)]
    if reales and len(reales) == len(A):
        traza_a = sum(A[i][i] for i in range(len(A)))
        if sum(reales) != traza_a:
            raise _error("INTERNAL", "Σλ ≠ traza(A)")
        det_a = _det_frac(A)
        prod = Fraction(1)
        for v in reales:
            prod *= v
        if prod != det_a:
            raise _error("INTERNAL", "Πλ ≠ det(A)")
    trace.verificacion("algebra.traza_det", "cada λ anula p(λ); Σλ = traza, Πλ = det")


def _verifica_autovalores_flotante(coefs, vals, trace) -> None:
    """Segundo camino para λ en ℚ(√r): p(λ) ≈ 0 en coma flotante (10⁻⁹)."""
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    for v in vals:
        total = 0.0
        pot = 1.0
        xv = float(mx.valor_real(v, {}))
        for c in coefs:
            total += float(c) * pot
            pot *= xv
        if abs(total) > 1e-9 * max(1.0, abs(xv) ** len(coefs)):
            raise _error("INTERNAL", f"λ = {mx.text(v)} no anula el característico")
    trace.verificacion("algebra.caracteristico_num",
                       "p(λ) ≈ 0 en coma flotante para cada λ irracional")


def _det_frac(A) -> Fraction:
    from academic_core.domain.engineering.mathlab import lineal as L

    K = L.cuerpo("Q")
    M = [[K.de(x) for x in fila] for fila in A]
    return L.determinante(M, K)


def autovectores(A, lam, trace: Trace | None = None) -> list[list[Fraction]]:
    """Base del núcleo de (A − λI) con el motor lineal; λ tiene que ser racional."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    n = _cuadrada(A)
    try:
        lam = Fraction(lam)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise _error("BAD_INPUT", f"λ = {lam}: tiene que ser racional exacto") from exc
    M = [[L.cuerpo("Q").de(A[i][j] - (lam if i == j else 0)) for j in range(n)]
         for i in range(n)]
    K = L.cuerpo("Q")
    base = L.nucleo([list(f) for f in M], K, trace)
    if not base:
        raise _error("DEFECTIVE", f"λ = {lam} no tiene autovector (¿multiplicidad mal?)")
    trace.regla("algebra.autovectores", f"dim ker(A − {lam}I) = {len(base)}",
                why="autovector = núcleo de (A − λI) por Gauss exacto")
    for v in base:
        Av = [sum(A[i][j] * v[j] for j in range(n)) for i in range(n)]
        if any(Av[i] != lam * v[i] for i in range(n)):
            raise _error("INTERNAL", "A·v ≠ λ·v")
    trace.verificacion("algebra.av_sub", "A·v = λ·v para cada vector de la base")
    return [[Fraction(x) for x in v] for v in base]


def diagonalizar(A, trace: Trace | None = None) -> tuple:
    """(P, D): A·P = P·D comprobado; si no hay base de autovectores, con su motivo."""
    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    n = _cuadrada(A)
    vals = autovalores(A, trace)
    if any(not isinstance(v, Fraction) for v in vals):
        raise _no("espectro no racional (complejo o irracional): los autovectores "
                  "exactos viven sobre ℚ y aquí no existen")
    if len(set(vals)) != n and any(vals.count(v) > 1 for v in set(vals)):
        mults = {v: vals.count(v) for v in set(vals)}
        total = 0
        vecs: dict = {}
        for v, m in mults.items():
            vecs[v] = autovectores(A, v, trace)
            total += len(vecs[v])
            if len(vecs[v]) < m:
                raise _error("DEFECTIVE", f"λ = {v}: mult. geométrica {len(vecs[v])} < "
                             f"algebraica {m}: no diagonaliza")
        if total != n:
            raise _error("DEFECTIVE", "faltan autovectores: no diagonaliza")
    else:
        vecs = {v: autovectores(A, v, trace) for v in vals}
    P_cols, D = [], []
    for v in vals:
        P_cols.append(vecs[v].pop(0))
        D.append(v)
    P = [[P_cols[j][i] for j in range(n)] for i in range(n)]
    AP = [[sum(A[i][k] * P[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
    PD = [[P[i][j] * D[j] for j in range(n)] for i in range(n)]
    if AP != PD:
        raise _error("INTERNAL", "A·P ≠ P·D")
    trace.regla("algebra.diagonalizar", f"D = diag({', '.join(str(v) for v in D)})",
                why="P por columnas de autovectores; A·P = P·D término a término")
    trace.verificacion("algebra.diag_sub", "A·P = P·D comprobado")
    return P, D


def gram_schmidt(vects, trace: Trace | None = None) -> list[list[Fraction]]:
    """Base ortogonal exacta (sin normalizar); dependencia, con su motivo."""
    trace = trace if trace is not None else Trace()
    V = _a_frac(vects)
    if any(len(v) != len(V[0]) for v in V):
        raise _error("BAD_INPUT", "todos los vectores con la misma dimensión")
    orto: list[list[Fraction]] = []
    for i, v in enumerate(V):
        u = list(v)
        for w in orto:
            num = sum(a * b for a, b in zip(v, w))
            den = sum(a * a for a in w)
            if den == 0:
                raise _error("BAD_INPUT", "vector nulo en la entrada")
            u = [a - num * b / den for a, b in zip(u, w)]
        if all(c == 0 for c in u):
            raise _error("DEPENDENT", f"v_{i + 1} es combinación de los anteriores: "
                         "la familia es ligada")
        orto.append(u)
        trace.regla("algebra.gram_schmidt", f"u_{i + 1} = v_{i + 1} − Σ proy",
                    why="se resta la proyección sobre cada u anterior")
    for i in range(len(orto)):
        for j in range(i + 1, len(orto)):
            if sum(a * b for a, b in zip(orto[i], orto[j])) != 0:
                raise _error("INTERNAL", "la base no es ortogonal")
    trace.verificacion("algebra.ortogonalidad", "uᵢ·uⱼ = 0 para i ≠ j, exacto")
    return orto


def cramer(A, b, trace: Trace | None = None) -> list[Fraction]:
    """xᵢ = det(Aᵢ)/det(A) con cada determinante por Gauss+Laplace; det = 0, motivo."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    b = [Fraction(x) for x in b]
    n = _cuadrada(A)
    if len(b) != n:
        raise _error("BAD_INPUT", "b con tantas componentes como filas A")
    K = L.cuerpo("Q")
    det = L.determinante([[K.de(x) for x in fila] for fila in A], K, trace)
    if det == 0:
        raise _error("SINGULAR", "det(A) = 0: Cramer no vale (sistema no determinado)")
    sol = []
    for j in range(n):
        Aj = [list(fila) for fila in A]
        for i in range(n):
            Aj[i][j] = b[i]
        dj = L.determinante([[K.de(x) for x in fila] for fila in Aj], K)
        sol.append(dj / det)
        trace.regla("algebra.cramer", f"x_{j + 1} = det(A_{j + 1})/det(A) = {sol[-1]}",
                    why="se sustituye la columna j por b y se divide por det(A) ≠ 0")
    for i in range(n):
        if sum(A[i][j] * sol[j] for j in range(n)) != b[i]:
            raise _error("INTERNAL", "Cramer no cumple A·x = b")
    trace.verificacion("algebra.cramer_sub", "A·x = b sustituido")
    return sol


def minimos_cuadrados(A, b, trace: Trace | None = None) -> tuple[list[Fraction], Fraction]:
    """x̂ = (AᵀA)⁻¹Aᵀb por ecuaciones normales; residuo ‖r‖² exacto."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    b = [Fraction(x) for x in b]
    m, n = len(A), len(A[0])
    AtA = [[sum(A[k][i] * A[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    Atb = [sum(A[k][i] * b[k] for k in range(m)) for i in range(n)]
    K = L.cuerpo("Q")
    try:
        inv = L.inversa([[K.de(x) for x in fila] for fila in AtA], K, trace)
    except Exception as exc:
        raise _error("RANK", f"AᵀA singular: columnas ligadas ({exc})") from None
    x = [sum(inv[i][j] * Atb[j] for j in range(n)) for i in range(n)]
    x = [Fraction(v) for v in x]
    r2 = sum((sum(A[i][j] * x[j] for j in range(n)) - b[i]) ** 2 for i in range(m))
    trace.regla("algebra.minimos", f"x̂ = (AᵀA)⁻¹Aᵀb = {x}, ‖r‖² = {r2}",
                why="ecuaciones normales: el residuo es ortogonal a cada columna")
    for i in range(n):
        if sum(AtA[i][j] * x[j] for j in range(n)) != Atb[i]:
            raise _error("INTERNAL", "no cumple AᵀAx̂ = Aᵀb")
    trace.verificacion("algebra.mmcc_sub", "AᵀAx̂ = Aᵀb sustituido")
    return x, r2


def pseudoinversa(A, trace: Trace | None = None) -> list[list[Fraction]]:
    """A⁺ = (AᵀA)⁻¹Aᵀ con rango columna completo; si no, con su motivo."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    m, n = len(A), len(A[0])
    AtA = [[sum(A[k][i] * A[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    K = L.cuerpo("Q")
    try:
        inv = L.inversa([[K.de(x) for x in fila] for fila in AtA], K, trace)
    except Exception as exc:
        raise _error("RANK", f"sin rango columna completo no hay (AᵀA)⁻¹ ({exc})") from None
    P = [[sum(inv[i][k] * A[j][k] for k in range(n)) for j in range(m)] for i in range(n)]
    P = [[Fraction(v) for v in fila] for fila in P]
    trace.regla("algebra.pseudoinversa", "A⁺ = (AᵀA)⁻¹Aᵀ",
                why="rango columna completo: AᵀA invertible exacta")
    _verifica_moore_penrose(A, P, trace)
    return P


def _verifica_moore_penrose(A, P, trace) -> None:
    def prod(X, Y):
        return [[sum(X[i][k] * Y[k][j] for k in range(len(Y))) for j in range(len(Y[0]))]
                for i in range(len(X))]

    if prod(A, prod(P, A)) != A or prod(P, prod(A, P)) != P:
        raise _error("INTERNAL", "no cumple A·A⁺·A = A y A⁺·A·A⁺ = A⁺")
    trace.verificacion("algebra.mp12", "A·A⁺·A = A y A⁺·A·A⁺ = A⁺")
