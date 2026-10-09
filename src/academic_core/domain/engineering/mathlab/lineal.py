# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): the linear engine over a field chosen as a parameter.

Fields: ℚ (exact), ℂ as ℚ(i) (exact), ℝ (floating point with partial pivoting and a
declared tolerance), GF(p) and GF(2ᵐ).

Gauss, rank, kernel, inverse and determinant are the same algorithm over any field;
what changes is the arithmetic, and with it the answers: ``[[2, 1], [1, 2]]`` is
invertible over ℚ and singular over GF(3). The field is
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

    def igual(self, a, b) -> bool:
        return self.es_cero(self.resta(a, b))

    def preparar(self, M) -> None:
        """Called before eliminating; ℝ uses it to fix its tolerance."""

    def elegir_pivote(self, M, desde: int, c: int):
        return next((i for i in range(desde, len(M)) if not self.es_cero(M[i][c])), None)

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

    def preparar(self, M) -> None:
        """Pasa las entradas al cuerpo **antes** de eliminar.

        Sin esto, dar la matriz con enteros (lo natural) dejaba enteros en la
        matriz, ``inv`` devolvía un float y Gauss calculaba en coma flotante:
        el determinante salía con error de redondeo y su propio control contra
        Laplace lo detectaba y se negaba a certificarlo. ``de()`` convierte y
        además rechaza los decimales, que en ℚ no son exactos — que es lo que
        corresponde decir en vez de calcular en coma flotante y llamarlo ℚ.
        """
        for fila in M:
            for j, x in enumerate(fila):
                if not isinstance(x, Fraction):
                    fila[j] = self.de(x)

    def suma(self, a, b):
        return a + b

    def resta(self, a, b):
        return a - b

    def mul(self, a, b):
        return a * b

    def inv(self, a):
        # ``1/a`` con ``a`` entero devuelve un float y el camino de Gauss
        # pasaría a coma flotante en silencio; forzando Fraction la división
        # es exacta siempre (2026-10-07, lo encontró el generador de
        # ejercicios de ML-10 al pedir un determinante con enteros).
        return Fraction(1) / Fraction(a)


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


class Reales(Cuerpo):
    """ℝ in floating point: the only inexact field, and it says so.

    Pivoting picks the largest entry of the column (partial pivoting) and a value is
    taken as zero below ``tolerancia``, which scales with the matrix. Rank over ℝ in
    floating point is a numerical decision, not a theorem, so every result over ℝ
    carries that warning.
    """

    nombre = "ℝ"
    exacto = False

    def __init__(self):
        self.tolerancia = 1e-12

    def de(self, valor):
        if isinstance(valor, str):
            from academic_core.domain.engineering.mathlab import mvexpr as mx

            v = mx.valor_real(mx.parse(valor), {})
            if v is None:
                raise _error("BAD_ENTRY", f"«{valor}» no es un número real")
            return float(v)
        if isinstance(valor, complex):
            raise _error("BAD_ENTRY", f"{valor} no es real")
        return float(valor)

    def suma(self, a, b):
        return a + b

    def resta(self, a, b):
        return a - b

    def mul(self, a, b):
        return a * b

    def inv(self, a):
        return 1.0 / a

    def es_cero(self, a) -> bool:
        return abs(a) <= self.tolerancia

    def igual(self, a, b) -> bool:
        return abs(a - b) <= self.tolerancia * max(1.0, abs(a), abs(b)) * 1e3

    def preparar(self, M) -> None:
        escala = max((abs(x) for f in M for x in f), default=1.0) or 1.0
        self.tolerancia = max(len(M), len(M[0])) * escala * 2.0 ** -45

    def elegir_pivote(self, M, desde: int, c: int):
        fila = max(range(desde, len(M)), key=lambda i: abs(M[i][c]), default=None)
        if fila is None or self.es_cero(M[fila][c]):
            return None
        return fila

    def texto(self, a) -> str:
        return f"{a:.10g}"


class Complejos(Cuerpo):
    """ℂ restricted to ℚ(i): a + b·i with a, b rational, exact."""

    nombre = "ℂ"

    def de(self, valor):
        if isinstance(valor, tuple):
            return (Fraction(valor[0]), Fraction(valor[1]))
        if isinstance(valor, complex):
            raise _error("BAD_ENTRY", "un complejo en coma flotante no es exacto: escribe "
                                      "«a + b*i» con a y b fracciones")
        if isinstance(valor, str):
            from academic_core.domain.engineering.mathlab import mvexpr as mx

            return _complejo_exacto(mx.parse(valor.replace("j", "i")), valor)
        return (Racionales().de(valor), Fraction(0))

    def suma(self, a, b):
        return (a[0] + b[0], a[1] + b[1])

    def resta(self, a, b):
        return (a[0] - b[0], a[1] - b[1])

    def mul(self, a, b):
        return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])

    def inv(self, a):
        n = a[0] * a[0] + a[1] * a[1]
        return (a[0] / n, -a[1] / n)

    def texto(self, a) -> str:
        re_, im_ = a
        if im_ == 0:
            return str(re_)
        modulo = abs(im_)
        imag = ("" if modulo == 1 else str(modulo) if modulo.denominator == 1
                else f"({modulo})") + "i"
        if re_ == 0:
            return ("-" if im_ < 0 else "") + imag
        return f"{re_} {'-' if im_ < 0 else '+'} {imag}"


def _complejo_exacto(e, valor: str):
    """``a + b·i`` from a polynomial in ``i`` with rational coefficients."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(e)
    except Exception:
        p = None
    if p is None:
        raise _error("BAD_ENTRY", f"«{valor}» no es un complejo exacto a + b·i")
    re_, im_ = Fraction(0), Fraction(0)
    for mono, c in p.items():
        exponentes = dict(mono)
        if set(exponentes) - {"@i"}:
            raise _error("BAD_ENTRY", f"«{valor}» no es un complejo exacto a + b·i")
        grado = exponentes.get("@i", 0)
        signo = (1, 1, -1, -1)[grado % 4]      # i^k cycles 1, i, -1, -i
        if grado % 2 == 0:
            re_ += signo * Fraction(c)
        else:
            im_ += signo * Fraction(c)
    return (re_, im_)


#: conventional primitive polynomials (bit k = coefficient of x^k); the code checks
#: irreducibility anyway, so a wrong entry here would be refused, not used
POLINOMIOS_GF2M = {2: 0b111, 3: 0b1011, 4: 0b10011, 5: 0b100101, 6: 0b1000011,
                   7: 0b10000011, 8: 0b100011101}


def _texto_poli2(p: int, var: str = "x") -> str:
    if p == 0:
        return "0"
    sup = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    partes = []
    for k in range(p.bit_length() - 1, -1, -1):
        if p >> k & 1:
            partes.append("1" if k == 0 else var if k == 1 else var + str(k).translate(sup))
    return " + ".join(partes)


def _mod_poli2(a: int, m: int) -> int:
    grado = m.bit_length() - 1
    while a.bit_length() - 1 >= grado:
        a ^= m << (a.bit_length() - 1 - grado)
    return a


def irreducible_gf2(m: int) -> bool:
    """A polynomial over GF(2) is irreducible iff no polynomial of degree 1..deg/2
    divides it — checked by trial division."""
    grado = m.bit_length() - 1
    if grado < 1:
        return False
    for d in range(2, 1 << (grado // 2 + 1)):
        if _mod_poli2(m, d) == 0:
            return False
    return True


class GF2m(Cuerpo):
    """GF(2ᵐ) = GF(2)[α]/(m(α)), elements as bit patterns; m(x) CHECKED irreducible."""

    def __init__(self, m: int, modulo: int | None = None):
        if not 1 <= m <= 16:
            raise _error("BAD_FIELD", "GF(2ᵐ) con 1 ≤ m ≤ 16")
        if modulo is None:
            if m == 1:
                modulo = 0b10
            elif m not in POLINOMIOS_GF2M:
                raise _error("BAD_FIELD", f"para GF(2^{m}) indica el polinomio irreducible")
            else:
                modulo = POLINOMIOS_GF2M[m]
        if modulo.bit_length() - 1 != m:
            raise _error("BAD_FIELD", f"el polinomio {_texto_poli2(modulo)} no es de grado {m}")
        if not irreducible_gf2(modulo):
            raise _error("NOT_A_FIELD", f"{_texto_poli2(modulo)} no es irreducible sobre GF(2): "
                                        f"GF(2)[x]/({_texto_poli2(modulo)}) tiene divisores de cero")
        self.m, self.modulo = m, modulo
        self.nombre = f"GF(2^{m}) con {_texto_poli2(modulo)}"

    def de(self, valor):
        if isinstance(valor, str):
            return _mod_poli2(_poli2_de_texto(valor), self.modulo)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
            raise _error("BAD_ENTRY", "en GF(2ᵐ) un elemento es un entero ≥ 0 (sus bits son "
                                      "los coeficientes) o un polinomio en «a»")
        if valor >> self.m:
            raise _error("BAD_ENTRY", f"{valor} tiene más de {self.m} bits")
        return valor

    def suma(self, a, b):
        return a ^ b

    resta = suma

    def mul(self, a, b):
        r = 0
        while b:
            if b & 1:
                r ^= a
            b >>= 1
            a <<= 1
            if a >> self.m:
                a ^= self.modulo
        return r

    def inv(self, a):
        if a == 0:
            raise ZeroDivisionError
        r, e = 1, (1 << self.m) - 2
        while e:
            if e & 1:
                r = self.mul(r, a)
            a, e = self.mul(a, a), e >> 1
        return r

    def texto(self, a) -> str:
        return _texto_poli2(a, "α")


def _poli2_de_texto(texto: str) -> int:
    resultado = 0
    for termino in texto.replace(" ", "").replace("α", "a").split("+"):
        if termino in ("0", ""):
            continue
        if termino == "1":
            k = 0
        elif termino in ("a", "x"):
            k = 1
        elif termino[:2] in ("a^", "x^") and termino[2:].isdigit():
            k = int(termino[2:])
        else:
            raise _error("BAD_ENTRY", f"«{texto}» no es un polinomio en a sobre GF(2)")
        resultado ^= 1 << k
    return resultado


def cuerpo(nombre: str | None) -> Cuerpo:
    """«Q» (default), «R», «C», «GF(p)» / «Z_p», «GF(2^m)» or «GF(2^m, x^3+x+1)»."""
    texto = (nombre or "Q").strip().upper().replace(" ", "")
    if texto in ("Q", "ℚ", "RACIONALES"):
        return Racionales()
    if texto in ("R", "ℝ", "REALES"):
        return Reales()
    if texto in ("C", "ℂ", "COMPLEJOS"):
        return Complejos()
    if texto.startswith("GF(2^"):
        interior = texto[5:].rstrip(")")
        grado, _, poli = interior.partition(",")
        try:
            m = int(grado)
        except ValueError:
            raise _error("BAD_FIELD", f"cuerpo desconocido «{nombre}»") from None
        return GF2m(m, _poli2_de_texto(poli.lower()) if poli else None)
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
    K.preparar(M)
    filas, total = len(M), len(M[0])
    columnas = total if columnas is None else columnas
    pivotes: list[int] = []
    factor = K.uno()
    r = 0
    for c in range(columnas):
        fila = K.elegir_pivote(M, r, c)
        if fila is None:
            continue
        if fila != r:
            M[r], M[fila] = M[fila], M[r]
            factor = K.resta(K.cero(), factor)
            trace.regla("gauss.intercambio", f"F{r + 1} ↔ F{fila + 1}",
                        after=texto_matriz(M, K),
                        why=f"la columna {c + 1} necesita un pivote no nulo en la fila {r + 1}")
        pivote = M[r][c]
        if not K.igual(pivote, K.uno()):
            inverso = K.inv(pivote)
            M[r] = [K.mul(inverso, x) for x in M[r]]
            factor = K.mul(factor, pivote)
            trace.regla("gauss.escala", f"F{r + 1} ← ({K.texto(inverso)})·F{r + 1}",
                        after=texto_matriz(M, K), why="pivote igual a 1")
        for i in range(filas):
            if i != r and not K.es_cero(M[i][c]):
                k = M[i][c]
                M[i] = [K.resta(x, K.mul(k, y)) for x, y in zip(M[i], M[r])]
                M[i][c] = K.cero()
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
        if not K.igual(laplace, det):
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
    if not all(K.igual(x, y) for f, g in zip(producto(A, inv, K), identidad)
               for x, y in zip(f, g)):
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
    if not all(K.igual(_dot(f, particular, K), y) for f, y in zip(A, b)):
        raise _error("INTERNAL", "la solución particular no cumple A·x = b")
    trace.verificacion("sistema.sustitucion", "A·x = b con la solución particular")
    tipo = "compatible determinado" if not base else "compatible indeterminado"
    return Sistema(tipo, E.rango, rango_ampliada, particular, base)
