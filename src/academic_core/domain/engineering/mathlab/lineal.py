# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): the linear engine over a field chosen as a parameter — ℚ or GF(p).

Gauss, rank, kernel, inverse and determinant are the same algorithm over any field;
what changes is the arithmetic, and with it the answers: ``[[1, 1], [1, 1]]`` has
rank 1 everywhere, but ``[[1, 1], [1, 2]]`` is invertible over ℚ and not over GF(1)…
and ``[[2, 1], [1, 2]]`` is invertible over ℚ and singular over GF(3). The field is
therefore an argument, and its hypothesis (``p`` prime) is CHECKED, not assumed
(§5.7): ℤ₄ is not a field, and Gauss over it would divide by 2.

Every row operation is written in the trace the way it is written on paper
(``F2 ← F2 − 3·F1``), and every result is checked by a second path: ``A·A⁻¹ = I``,
``A·v = 0`` for each kernel vector, ``A·x = b`` for a solution, and the determinant
by Laplace expansion for small matrices.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: Laplace's expansion is n! — the second path for the determinant stops here
MAX_LAPLACE = 6
MAX_DIMENSION = 12


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


# ---------------------------------------------------------------------------
# fields
# ---------------------------------------------------------------------------


class Cuerpo:
    nombre = "?"

    def de(self, valor) -> object:
        raise NotImplementedError

    def cero(self):
        return self.de(0)

    def uno(self):
        return self.de(1)

    def suma(self, a, b):
        raise NotImplementedError

    def resta(self, a, b):
        raise NotImplementedError

    def mul(self, a, b):
        raise NotImplementedError

    def inv(self, a):
        raise NotImplementedError

    def es_cero(self, a) -> bool:
        return a == self.cero()

    def texto(self, a) -> str:
        return str(a)


class Racionales(Cuerpo):
    nombre = "ℚ"

    def de(self, valor):
        if isinstance(valor, str):
            from academic_core.domain.engineering.mathlab import mvexpr as mx

            exacto = mx.exact_value(mx.parse(valor))
            if exacto is None:
                raise _error("BAD_ENTRY", f"«{valor}» no es un número racional exacto")
            return Fraction(exacto)
        if isinstance(valor, float):
            raise _error("BAD_ENTRY", "un decimal en coma flotante no es exacto: "
                                      "escríbelo como fracción")
        return Fraction(valor)

    def suma(self, a, b):
        return a + b

    def resta(self, a, b):
        return a - b

    def mul(self, a, b):
        return a * b

    def inv(self, a):
        return 1 / a


class Primo(Cuerpo):
    """GF(p) = ℤ_p, p prime — checked at construction."""

    def __init__(self, p: int):
        from academic_core.domain.engineering.mathlab import enteros as Z

        if not Z.es_cuerpo(p):
            raise _error("NOT_A_FIELD",
                         f"ℤ_{p} no es un cuerpo: {p} no es primo, y Gauss dividiría por un "
                         "divisor de cero")
        self.p = p
        self.nombre = f"GF({p})"

    def de(self, valor):
        q = Racionales().de(valor)
        if q.denominator % self.p == 0:
            raise _error("BAD_ENTRY", f"{q} no existe en GF({self.p}): su denominador es "
                                      f"múltiplo de {self.p}")
        return q.numerator * pow(q.denominator, -1, self.p) % self.p

    def suma(self, a, b):
        return (a + b) % self.p

    def resta(self, a, b):
        return (a - b) % self.p

    def mul(self, a, b):
        return (a * b) % self.p

    def inv(self, a):
        return pow(a, -1, self.p)


def cuerpo(nombre: str | None) -> Cuerpo:
    """«Q» (default) or «GF(p)» / «Z_p» / «p»."""
    texto = (nombre or "Q").strip().upper().replace(" ", "")
    if texto in ("Q", "ℚ", "R", "ℝ", "RACIONALES"):
        return Racionales()
    for prefijo in ("GF(", "Z_", "Z", "F"):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):].rstrip(")")
            break
    try:
        return Primo(int(texto))
    except ValueError:
        raise _error("BAD_FIELD", f"cuerpo desconocido «{nombre}»; usa Q o GF(p)") from None


# ---------------------------------------------------------------------------
# matrices
# ---------------------------------------------------------------------------


Matriz = list[list]


def matriz(filas, K: Cuerpo) -> Matriz:
    if not filas or not all(isinstance(f, (list, tuple)) for f in filas):
        raise _error("BAD_INPUT", "una matriz es una lista de filas")
    ancho = len(filas[0])
    if ancho == 0 or any(len(f) != ancho for f in filas):
        raise _error("BAD_INPUT", "todas las filas tienen que tener la misma longitud")
    if len(filas) > MAX_DIMENSION or ancho > MAX_DIMENSION + 1:
        raise _error("EXPRESSION_LIMIT", f"dimensión mayor que {MAX_DIMENSION}")
    return [[K.de(x) for x in f] for f in filas]


def texto_matriz(A: Matriz, K: Cuerpo) -> str:
    return "[" + "; ".join(", ".join(K.texto(x) for x in f) for f in A) + "]"


def producto(A: Matriz, B: Matriz, K: Cuerpo) -> Matriz:
    return [[_dot([A[i][k] for k in range(len(B))], [B[k][j] for k in range(len(B))], K)
             for j in range(len(B[0]))] for i in range(len(A))]


def _dot(u, v, K: Cuerpo):
    total = K.cero()
    for a, b in zip(u, v):
        total = K.suma(total, K.mul(a, b))
    return total


@dataclass(frozen=True)
class Escalonada:
    matriz: Matriz
    pivotes: tuple[int, ...]
    #: product of the factors the determinant picks up (swaps and scalings)
    factor: object
    rango: int


def escalonar(A: Matriz, K: Cuerpo, trace: Trace | None = None,
              columnas: int | None = None) -> Escalonada:
    """Reduced row echelon form by Gauss–Jordan, every row operation written.

    ``columnas`` limits the pivot search (for an augmented matrix the last
    column is not a variable).
    """
    trace = trace if trace is not None else Trace()
    M = [list(f) for f in A]
    filas, total = len(M), len(M[0])
    columnas = total if columnas is None else columnas
    pivotes: list[int] = []
    factor = K.uno()
    r = 0
    for c in range(columnas):
        fila = next((i for i in range(r, filas) if not K.es_cero(M[i][c])), None)
        if fila is None:
            continue
        if fila != r:
            M[r], M[fila] = M[fila], M[r]
            factor = K.resta(K.cero(), factor)
            trace.regla("gauss.intercambio", f"F{r + 1} ↔ F{fila + 1}",
                        after=texto_matriz(M, K),
                        why=f"la columna {c + 1} necesita un pivote no nulo en la fila {r + 1}")
        pivote = M[r][c]
        if pivote != K.uno():
            inverso = K.inv(pivote)
            M[r] = [K.mul(inverso, x) for x in M[r]]
            factor = K.mul(factor, pivote)
            trace.regla("gauss.escala", f"F{r + 1} ← ({K.texto(inverso)})·F{r + 1}",
                        after=texto_matriz(M, K), why="pivote igual a 1")
        for i in range(filas):
            if i != r and not K.es_cero(M[i][c]):
                k = M[i][c]
                M[i] = [K.resta(x, K.mul(k, y)) for x, y in zip(M[i], M[r])]
                trace.regla("gauss.eliminar", f"F{i + 1} ← F{i + 1} − ({K.texto(k)})·F{r + 1}",
                            after=texto_matriz(M, K),
                            why=f"se anula la entrada ({i + 1}, {c + 1}) con el pivote")
        pivotes.append(c)
        r += 1
        if r == filas:
            break
    return Escalonada(M, tuple(pivotes), factor, len(pivotes))


def rango(A: Matriz, K: Cuerpo, trace: Trace | None = None) -> int:
    return escalonar(A, K, trace).rango


def determinante(A: Matriz, K: Cuerpo, trace: Trace | None = None):
    trace = trace if trace is not None else Trace()
    n = len(A)
    if any(len(f) != n for f in A):
        raise _error("NOT_SQUARE", "el determinante solo existe para matrices cuadradas")
    E = escalonar(A, K, trace)
    det = K.cero() if E.rango < n else E.factor
    trace.regla("det.gauss", f"det = {K.texto(det)}",
                why=("cada intercambio cambia el signo y cada fila escalada saca su "
                     "factor; si el rango no es completo, es 0"))
    if n <= MAX_LAPLACE:
        laplace = _laplace(A, K)
        if laplace != det:
            raise _error("INTERNAL", "el determinante por Gauss no coincide con Laplace")
        trace.verificacion("det.laplace", "coincide con el desarrollo de Laplace",
                           after=K.texto(laplace))
    return det


def _laplace(A: Matriz, K: Cuerpo):
    if len(A) == 1:
        return A[0][0]
    total = K.cero()
    for j, a in enumerate(A[0]):
        if K.es_cero(a):
            continue
        menor = [f[:j] + f[j + 1:] for f in A[1:]]
        termino = K.mul(a, _laplace(menor, K))
        total = K.suma(total, termino) if j % 2 == 0 else K.resta(total, termino)
    return total


def inversa(A: Matriz, K: Cuerpo, trace: Trace | None = None) -> Matriz:
    trace = trace if trace is not None else Trace()
    n = len(A)
    if any(len(f) != n for f in A):
        raise _error("NOT_SQUARE", "solo una matriz cuadrada puede tener inversa")
    ampliada = [list(f) + [K.uno() if i == j else K.cero() for j in range(n)]
                for i, f in enumerate(A)]
    trace.metodo("inversa.gauss_jordan", "Gauss–Jordan sobre [A | I]",
                 why="las operaciones que llevan A a I llevan I a A⁻¹")
    E = escalonar(ampliada, K, trace, columnas=n)
    if E.rango < n:
        raise _error("SINGULAR", f"la matriz tiene rango {E.rango} < {n} en {K.nombre}: "
                                 "no es invertible")
    inv = [f[n:] for f in E.matriz]
    identidad = [[K.uno() if i == j else K.cero() for j in range(n)] for i in range(n)]
    if producto(A, inv, K) != identidad:
        raise _error("INTERNAL", "A·A⁻¹ no es la identidad")
    trace.verificacion("inversa.producto", "A·A⁻¹ = I", after=texto_matriz(inv, K))
    return inv


def nucleo(A: Matriz, K: Cuerpo, trace: Trace | None = None) -> list[list]:
    """A basis of ``{v : A·v = 0}``, one vector per free variable."""
    trace = trace if trace is not None else Trace()
    E = escalonar(A, K, trace)
    n = len(A[0])
    libres = [j for j in range(n) if j not in E.pivotes]
    base = []
    for libre in libres:
        v = [K.cero()] * n
        v[libre] = K.uno()
        for fila, c in enumerate(E.pivotes):
            v[c] = K.resta(K.cero(), E.matriz[fila][libre])
        base.append(v)
    for v in base:
        if any(not K.es_cero(_dot(f, v, K)) for f in A):
            raise _error("INTERNAL", "un vector del núcleo no se anula")
    trace.verificacion("nucleo.comprobacion",
                       f"dim núcleo = {len(base)} = {n} − rango {E.rango}, y A·v = 0 para cada v")
    return base


@dataclass(frozen=True)
class Sistema:
    tipo: str                      # «compatible determinado» / «… indeterminado» / «incompatible»
    rango_a: int
    rango_ampliada: int
    particular: list | None
    nucleo: list[list]

    def texto(self, K: Cuerpo) -> str:
        if self.particular is None:
            return f"incompatible (rango A = {self.rango_a} < rango [A|b] = {self.rango_ampliada})"
        x = "(" + ", ".join(K.texto(v) for v in self.particular) + ")"
        if not self.nucleo:
            return f"compatible determinado: x = {x}"
        libres = " + ".join(f"λ{i + 1}·(" + ", ".join(K.texto(v) for v in u) + ")"
                            for i, u in enumerate(self.nucleo))
        return f"compatible indeterminado ({len(self.nucleo)} parámetros): x = {x} + {libres}"


def resolver_sistema(A: Matriz, b: list, K: Cuerpo, trace: Trace | None = None) -> Sistema:
    """``A·x = b`` classified by Rouché–Frobenius, with the general solution."""
    trace = trace if trace is not None else Trace()
    if len(b) != len(A):
        raise _error("BAD_INPUT", "b tiene que tener tantas componentes como filas A")
    n = len(A[0])
    ampliada = [list(f) + [y] for f, y in zip(A, b)]
    E = escalonar(ampliada, K, trace, columnas=n)
    rango_ampliada = escalonar(ampliada, K).rango
    trace.hipotesis("rouche", f"rango A = {E.rango}, rango [A|b] = {rango_ampliada}, "
                              f"incógnitas = {n}", "Rouché–Frobenius")
    if rango_ampliada > E.rango:
        return Sistema("incompatible", E.rango, rango_ampliada, None, [])
    particular = [K.cero()] * n
    for fila, c in enumerate(E.pivotes):
        particular[c] = E.matriz[fila][n]
    base = nucleo(A, K, trace)
    if any(_dot(f, particular, K) != y for f, y in zip(A, b)):
        raise _error("INTERNAL", "la solución particular no cumple A·x = b")
    trace.verificacion("sistema.sustitucion", "A·x = b con la solución particular")
    tipo = "compatible determinado" if not base else "compatible indeterminado"
    return Sistema(tipo, E.rango, rango_ampliada, particular, base)
