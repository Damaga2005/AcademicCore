# SPDX-License-Identifier: MIT
"""ML-3: álgebra lineal exacta sobre ℚ — autovalores, Gram-Schmidt y mínimos cuadrados.

Lo que ya estaba (lineal.py, cuerpo como parámetro; complejos.py) no se toca:
aquí van las piezas que faltaban de MATH_LAB §4.3/§15.1 con pasos y segundo
camino propios:

- autovalores exactos hasta 6×6 con multiplicidad: característico por
  Faddeev-Leverrier, raíces racionales por Ruffini y el factor cuadrático que
  quede en ℚ(√r) o como par complejo conjugado exacto; un factor irreducible de
  grado ≥ 3 se rechaza y el calculador da los valores numéricos (NUMERIC_ONLY);
- autovectores como núcleo de (A−λI) con el motor lineal, solo para λ racional;
- diagonalización A = PDP⁻¹ comprobada por A·P = P·D;
- Gram-Schmidt clásico exacto con comprobación de ortogonalidad dos a dos;
- Cramer pedagógico (cada xᵢ = det(Aᵢ)/det(A), verificado por sustitución);
- mínimos cuadrados por ecuaciones normales y pseudoinversa de Moore-Penrose
  de cualquier rango (factorización A = C·R), con las cuatro condiciones de
  Penrose comprobadas.

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


MAX_N = 6


def polinomio_caracteristico(A, trace: Trace | None = None) -> list[Fraction]:
    """Coeficientes [c0..cn] del mónico det(λI − A), exactos (Faddeev-Leverrier)."""
    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    n = _cuadrada(A)
    if n > MAX_N:
        raise _no(f"característico de {n}×{n}: hasta {MAX_N}×{MAX_N}")
    coefs = _leverrier(A)
    trace.regla("algebra.caracteristico", f"p(λ) = {_texto_poli(coefs)}",
                why="Faddeev-Leverrier exacto: Mₖ = A·Mₖ₋₁ + cₙ₋ₖ₊₁·I, cₙ₋ₖ = −tr(A·Mₖ)/k")
    if coefs[0] != (-1) ** n * _det_frac(A):
        raise _error("INTERNAL", "p(0) ≠ (−1)ⁿ·det(A)")
    return coefs


def _leverrier(A) -> list[Fraction]:
    n = len(A)
    c = [Fraction(0)] * (n + 1)
    c[n] = Fraction(1)
    Mk = [[Fraction(0)] * n for _ in range(n)]
    for k in range(1, n + 1):
        AM = [[sum(A[i][t] * Mk[t][j] for t in range(n)) for j in range(n)] for i in range(n)]
        Mk = [[AM[i][j] + (c[n - k + 1] if i == j else 0) for j in range(n)] for i in range(n)]
        AMk = [[sum(A[i][t] * Mk[t][j] for t in range(n)) for j in range(n)] for i in range(n)]
        c[n - k] = -sum(AMk[i][i] for i in range(n)) / k
    return c


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
    valor: object  # Fraction, mx.Expr real o (re, im) complejo
    multiplicidad: int

    def texto(self) -> str:
        base = texto_autovalor(self.valor)
        return base if self.multiplicidad == 1 else f"{base} (mult. {self.multiplicidad})"


def texto_autovalor(v) -> str:
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    def t(x):
        return str(x) if isinstance(x, Fraction) else mx.text(x)
    if isinstance(v, tuple):
        re, im = v
        neg = (im < 0) if isinstance(im, Fraction) else isinstance(im, mx.Neg)
        mag = (-im if isinstance(im, Fraction) else im.arg) if neg else im
        mag_t = "" if mag == 1 else t(mag) + "·"
        pre = "" if re == 0 else f"{t(re)} "
        return f"{pre}{'−' if neg else ('+' if pre else '')}{' ' if pre else ''}{mag_t}i"
    return t(v)


def _quitar_racionales(p: list[Fraction]) -> tuple[list[Fraction], list[Fraction]]:
    """Raíces racionales con multiplicidad (regla de Ruffini) y el cociente restante."""
    import math

    from academic_core.domain.engineering.mathlab import raices as RZ

    raices: list[Fraction] = []
    while p[0] == 0 and len(p) > 1:
        p = p[1:]
        raices.append(Fraction(0))
    if len(p) > 1:
        comun = math.lcm(*[c.denominator for c in p])
        enteros = [int(c * comun) for c in p]
        candidatos = sorted({Fraction(s * a, b) for a in RZ._divisores(enteros[0])
                             for b in RZ._divisores(enteros[-1]) for s in (1, -1)})
        for r in candidatos:
            while len(p) > 1 and RZ._eval(p, r) == 0:
                p, _ = RZ._divmod(p, [-r, Fraction(1)])
                raices.append(r)
    return raices, p


def _cuadratica_exacta(q: list[Fraction]) -> list:
    """Las dos raíces exactas de c + b·λ + a·λ² sin raíces racionales."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    c, b, a = q
    disc = b * b - 4 * a * c
    re = -b / (2 * a)
    k, libre = RZ._raiz_simplificada(abs(disc))
    rk = k / (2 * a)
    if disc > 0:
        return sorted([RZ._mas_raiz(re, rk, libre), RZ._mas_raiz(re, -rk, libre)],
                      key=lambda e: _float(e))
    im = RZ._mas_raiz(Fraction(0), abs(rk), libre)
    if libre == 1:
        im = abs(rk)
    from academic_core.domain.engineering.mathlab import mvexpr as mx
    return [(re, im), (re, -im if isinstance(im, Fraction) else mx.Neg(im))]


def _float(v) -> float:
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    return float(v) if isinstance(v, Fraction) else float(mx.valor_real(v, {}))


def autovalores(A, trace: Trace | None = None) -> list:
    """Espectro exacto, con multiplicidad (cada λ repetido tantas veces como su
    multiplicidad algebraica): racionales (Fraction), reales en ℚ(√r) (mx.Expr) y
    complejos como (re, im) con im ≠ 0. Si queda un factor irreducible de grado ≥ 3
    no hay forma exacta sencilla: UNSUPPORTED (ver ``autovalores_numericos``)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    _cuadrada(A)
    coefs = polinomio_caracteristico(A, trace)
    racionales, resto = _quitar_racionales(list(coefs))
    if racionales:
        trace.regla("algebra.ruffini", "raíces racionales: " + ", ".join(
            str(v) for v in racionales), why="regla de las raíces racionales y Ruffini exacto")
    vals: list = sorted(racionales)
    if len(resto) > 1:
        # parte libre de cuadrados: cada factor irreducible repetido se trata una vez
        g = RZ._mcd(resto, RZ._deriv(resto)) if len(resto) > 2 else [Fraction(1)]
        libre = RZ._divmod(resto, g)[0] if len(g) > 1 else resto
        libre = [x / libre[-1] for x in libre]
        mult = (len(resto) - 1) // (len(libre) - 1)
        if len(libre) != 3:
            raise _no(f"factor irreducible de grado {len(libre) - 1} sin raíces racionales: "
                      "sin forma exacta; usa los autovalores numéricos")
        pares = _cuadratica_exacta(libre)
        trace.regla("algebra.cuadratica", f"{_texto_poli(libre)} = 0 → λ = " + ", ".join(
            texto_autovalor(v) for v in pares) + (f" (mult. {mult})" if mult > 1 else ""),
            why="discriminante " + ("> 0: reales en ℚ(√r)" if not isinstance(pares[0], tuple)
                                    else "< 0: par complejo conjugado exacto"))
        for v in pares:
            vals.extend([v] * mult)
    trace.regla("algebra.autovalores", "λ = " + ", ".join(texto_autovalor(v) for v in vals))
    _verifica_autovalores(A, coefs, vals, trace)
    return vals


def autovalores_numericos(A) -> list[complex]:
    """Todas las raíces de p(λ) en coma flotante (Durand-Kerner), para el caso sin
    forma exacta; el llamador sella NUMERIC_ONLY."""
    coefs = [float(c) for c in polinomio_caracteristico(A)]
    n = len(coefs) - 1
    z = [complex(0.4, 0.9) ** k for k in range(n)]

    def p(x):
        t = 0j
        for c in reversed(coefs):
            t = t * x + c
        return t
    for _ in range(2000):
        nuevo = []
        for i, zi in enumerate(z):
            den = 1 + 0j
            for j, zj in enumerate(z):
                if i != j:
                    den *= zi - zj
            nuevo.append(zi - p(zi) / den if den != 0 else zi + 1e-9)
        if max(abs(a - b) for a, b in zip(nuevo, z)) < 1e-15:
            z = nuevo
            break
        z = nuevo
    z = [complex(round(w.real, 12), round(w.imag, 12)) for w in z]
    return sorted(z, key=lambda w: (w.real, w.imag))


def _verifica_autovalores(A, coefs, vals, trace) -> None:
    """Segundo camino: Σλ = traza(A) y Πλ = det(A) (exacto si todos son racionales,
    en coma flotante compleja si no) y cada λ racional anula p(λ)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    n = len(A)
    if len(vals) != n:
        raise _error("INTERNAL", f"{len(vals)} autovalores para una {n}×{n}")
    for v in vals:
        if isinstance(v, Fraction) and RZ._eval(coefs, v) != 0:
            raise _error("INTERNAL", f"λ = {v} no anula el característico")
    traza_a = sum(A[i][i] for i in range(n))
    det_a = _det_frac(A)
    if all(isinstance(v, Fraction) for v in vals):
        prod = Fraction(1)
        for v in vals:
            prod *= v
        if sum(vals) != traza_a or prod != det_a:
            raise _error("INTERNAL", "Σλ ≠ traza o Πλ ≠ det")
    else:
        zs = [complex(_float(v[0]), _float(v[1])) if isinstance(v, tuple) else complex(_float(v))
              for v in vals]
        prod = 1 + 0j
        for z in zs:
            prod *= z
        escala = max(1.0, max(abs(z) for z in zs)) ** n
        if abs(sum(zs) - float(traza_a)) > 1e-9 * escala or \
                abs(prod - float(det_a)) > 1e-9 * escala:
            raise _error("INTERNAL", "Σλ ≠ traza o Πλ ≠ det")
        for z in zs:
            pz = 0j
            for c in reversed(coefs):
                pz = pz * z + float(c)
            if abs(pz) > 1e-8 * escala:
                raise _error("INTERNAL", "un λ no anula el característico")
    trace.verificacion("algebra.traza_det", "Σλ = traza, Πλ = det y p(λ) = 0 para cada λ")


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
    """Moore-Penrose exacta para cualquier rango: con A = C·R (C las columnas
    pivote de A, R las filas no nulas de su escalonada reducida, ambas de rango
    completo) es A⁺ = Rᵀ(RRᵀ)⁻¹(CᵀC)⁻¹Cᵀ. Con rango columna completo se reduce a
    (AᵀA)⁻¹Aᵀ. Se comprueban las cuatro condiciones de Penrose."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A = _a_frac(A)
    if not A or not A[0] or any(len(f) != len(A[0]) for f in A):
        raise _error("BAD_INPUT", "matriz rectangular no vacía")
    m, n = len(A), len(A[0])
    K = L.cuerpo("Q")
    esc = L.escalonar([[K.de(x) for x in fila] for fila in A], K)
    r = esc.rango
    if r == 0:
        trace.regla("algebra.pseudoinversa", "A = 0 ⇒ A⁺ = 0 (n×m)")
        return [[Fraction(0)] * m for _ in range(n)]
    C = [[A[i][c] for c in esc.pivotes] for i in range(m)]
    R = [[Fraction(x) for x in esc.matriz[k]] for k in range(r)]

    def prod(X, Y):
        return [[sum(X[i][k] * Y[k][j] for k in range(len(Y))) for j in range(len(Y[0]))]
                for i in range(len(X))]

    def t(X):
        return [list(c) for c in zip(*X)]

    def inv(X):
        return [[Fraction(v) for v in f] for f in
                L.inversa([[K.de(x) for x in f] for f in X], K)]
    P = prod(prod(t(R), inv(prod(R, t(R)))), prod(inv(prod(t(C), C)), t(C)))
    trace.regla("algebra.pseudoinversa", f"rango {r}: A = C·R, A⁺ = Rᵀ(RRᵀ)⁻¹(CᵀC)⁻¹Cᵀ",
                why="factorización de rango completo: CᵀC y RRᵀ son invertibles (r×r)")
    _verifica_moore_penrose(A, P, trace)
    return P


def _verifica_moore_penrose(A, P, trace) -> None:
    def prod(X, Y):
        return [[sum(X[i][k] * Y[k][j] for k in range(len(Y))) for j in range(len(Y[0]))]
                for i in range(len(X))]

    def t(X):
        return [list(c) for c in zip(*X)]
    AP, PA = prod(A, P), prod(P, A)
    if prod(AP, A) != A or prod(PA, P) != P or AP != t(AP) or PA != t(PA):
        raise _error("INTERNAL", "no cumple las cuatro condiciones de Penrose")
    trace.verificacion("algebra.penrose", "AA⁺A = A, A⁺AA⁺ = A⁺, (AA⁺)ᵀ = AA⁺, (A⁺A)ᵀ = A⁺A")
