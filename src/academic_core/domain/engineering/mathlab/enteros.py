# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): exact integer arithmetic with traces — ℤₙ the way it is examined.

Every operation writes the steps a student writes: each quotient of Euclid and the
back-substitution that yields ``a·s + b·t = d``; each square and each product of
modular exponentiation; the ``d`` solutions of a linear congruence; the combined
modulus of the Chinese remainder theorem. And every result is checked by a path
that shares nothing with the one that produced it (§5.3): ``a·a⁻¹ mod n = 1``,
Python's own ``pow``, substitution into the congruence, brute force when ``n`` is
small.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: brute-force checks only below this modulus
MAX_FUERZA_BRUTA = 10_000
#: exponents and moduli are bounded so a trace stays readable (§5.5)
MAX_BITS = 4096


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _sin_regla(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


def _entero(valor: object, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        try:
            texto = str(valor).strip()
            valor = int(texto)
        except (TypeError, ValueError):
            raise _error("BAD_INPUT", f"{nombre} tiene que ser un entero, y llegó «{valor}»") from None
    if abs(valor).bit_length() > MAX_BITS:
        raise _error("EXPRESSION_LIMIT", f"{nombre} tiene más de {MAX_BITS} bits")
    return valor


def _modulo(n: object) -> int:
    n = _entero(n, "el módulo")
    if n < 1:
        raise _error("BAD_INPUT", f"el módulo tiene que ser positivo, y es {n}")
    return n


# ---------------------------------------------------------------------------
# Euclid, extended
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bezout:
    """``a·s + b·t = d`` with ``d = mcd(a, b)``, and the table that produced it."""

    a: int
    b: int
    d: int
    s: int
    t: int
    #: (cociente, resto, s, t) per row, as the table is written on paper
    filas: tuple[tuple[int, int, int, int], ...]

    def texto(self) -> str:
        return f"mcd({self.a}, {self.b}) = {self.d} = {self.a}·({self.s}) + {self.b}·({self.t})"


def euclides_extendido(a: object, b: object, trace: Trace | None = None) -> Bezout:
    """Extended Euclid with every quotient and the running coefficients."""
    trace = trace if trace is not None else Trace()
    a, b = _entero(a, "a"), _entero(b, "b")
    if a == 0 and b == 0:
        raise _error("BAD_INPUT", "mcd(0, 0) no está definido")
    trace.metodo(
        "euclides.metodo", "algoritmo de Euclides extendido",
        why=("cada división sustituye (r₀, r₁) por (r₁, r₀ mod r₁) sin cambiar el mcd, "
             "y llevando a la vez los coeficientes s y t de cada resto se obtiene, al "
             "final, la identidad de Bézout a·s + b·t = mcd"),
        alternatives=(("factorizar los dos números",
                       "da el mcd pero no la combinación, que es lo que hace falta para "
                       "el inverso modular"),),
        before=f"mcd({a}, {b})")
    r0, r1 = abs(a), abs(b)
    s0, s1, t0, t1 = 1, 0, 0, 1
    filas = [(0, r0, s0, t0), (0, r1, s1, t1)]
    while r1:
        q = r0 // r1
        dividendo, divisor = r0, r1
        r0, r1 = r1, r0 - q * r1
        s0, s1 = s1, s0 - q * s1
        t0, t1 = t1, t0 - q * t1
        filas.append((q, r1, s1, t1))
        trace.regla("euclides.paso", f"{dividendo} = {q}·{divisor} + {r1}",
                    before=f"{dividendo} y {divisor}",
                    after=f"resto {r1}, s = {s1}, t = {t1}",
                    why="r = r₀ − q·r₁, y los coeficientes siguen la misma recurrencia")
    d = r0
    s = s0 * (1 if a >= 0 else -1)
    t = t0 * (1 if b >= 0 else -1)
    if a * s + b * t != d:
        raise _error("INTERNAL", "la identidad de Bézout no se cumple")
    trace.verificacion("euclides.bezout", "se comprueba la identidad de Bézout",
                       before=f"{a}·({s}) + {b}·({t})", after=str(d),
                       why="sustituir los coeficientes y obtener el mcd es la prueba")
    return Bezout(a, b, d, s, t, tuple(filas))


def inverso_modular(a: object, n: object, trace: Trace | None = None) -> int:
    """``a⁻¹ mod n`` from Bézout, or a refusal saying why it does not exist."""
    trace = trace if trace is not None else Trace()
    a, n = _entero(a, "a"), _modulo(n)
    if n == 1:
        raise _error("NO_INVERSE", "en ℤ₁ todo es 0 y no hay inversos")
    bezout = euclides_extendido(a % n, n, trace)
    if bezout.d != 1:
        raise _error("NO_INVERSE",
                     f"mcd({a}, {n}) = {bezout.d} ≠ 1: {a} no tiene inverso módulo {n} "
                     f"(sería un divisor de cero en ℤ_{n})")
    inverso = bezout.s % n
    trace.regla("inverso.de_bezout", f"{a}⁻¹ ≡ {inverso} (mod {n})",
                before=f"{a % n}·({bezout.s}) + {n}·({bezout.t}) = 1",
                after=str(inverso),
                why="reduciendo Bézout módulo n, el término n·t desaparece y queda a·s ≡ 1")
    if (a * inverso) % n != 1:
        raise _error("INTERNAL", "el inverso no lo es")
    trace.verificacion("inverso.comprobacion", "a·a⁻¹ mod n = 1",
                       before=f"{a}·{inverso} mod {n}", after="1")
    return inverso


# ---------------------------------------------------------------------------
# modular exponentiation
# ---------------------------------------------------------------------------


def potencia_modular(a: object, e: object, n: object, trace: Trace | None = None) -> int:
    """``a^e mod n`` by successive squares, reducing at every step."""
    trace = trace if trace is not None else Trace()
    a, e, n = _entero(a, "la base"), _entero(e, "el exponente"), _modulo(n)
    if e < 0:
        base = inverso_modular(a, n, trace)
        trace.regla("potencia.exponente_negativo", f"a^({e}) = (a⁻¹)^{-e}",
                    before=f"{a}^{e}", after=f"{base}^{-e}",
                    why="un exponente negativo es una potencia del inverso")
        a, e = base, -e
    binario = bin(e)[2:]
    trace.metodo("potencia.metodo", "exponenciación por cuadrados sucesivos",
                 why=(f"el exponente {e} en binario es {binario}: se elevan al cuadrado "
                      f"{len(binario) - 1} veces y se multiplican los cuadrados cuyo bit "
                      "es 1, reduciendo módulo n en cada paso para que nada crezca"),
                 before=f"{a}^{e} mod {n}")
    resultado, cuadrado = 1 % n, a % n
    for i, bit in enumerate(reversed(binario)):
        if bit == "1":
            antes = resultado
            resultado = (resultado * cuadrado) % n
            trace.regla("potencia.producto", f"bit {i} = 1: se multiplica a^(2^{i})",
                        before=f"{antes}·{cuadrado} mod {n}", after=str(resultado))
        if i < len(binario) - 1:
            anterior = cuadrado
            cuadrado = (cuadrado * cuadrado) % n
            trace.regla("potencia.cuadrado", f"a^(2^{i + 1}) = ({anterior})² mod {n}",
                        before=f"{anterior}²", after=str(cuadrado))
    if resultado != pow(a, e, n):
        raise _error("INTERNAL", "la potencia modular no coincide con pow")
    trace.verificacion("potencia.pow", "coincide con pow(a, e, n) calculado aparte",
                       after=str(resultado))
    return resultado


# ---------------------------------------------------------------------------
# linear congruences and the Chinese remainder theorem
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Congruencia:
    """All the solutions of ``a·x ≡ b (mod n)``: ``x ≡ x0 (mod m)``, listed mod n."""

    soluciones: tuple[int, ...]
    modulo: int
    x0: int | None
    paso: int | None

    def texto(self) -> str:
        if not self.soluciones:
            return "no tiene solución"
        return (f"x ≡ {self.x0} (mod {self.paso}); módulo {self.modulo}: "
                + ", ".join(map(str, self.soluciones)))


def congruencia_lineal(a: object, b: object, n: object,
                       trace: Trace | None = None) -> Congruencia:
    """``a·x ≡ b (mod n)``: solvable iff ``d = mcd(a, n)`` divides ``b``; then ``d`` solutions."""
    trace = trace if trace is not None else Trace()
    a, b, n = _entero(a, "a"), _entero(b, "b"), _modulo(n)
    d = euclides_extendido(a % n, n, trace).d
    trace.hipotesis("congruencia.condicion", f"mcd({a}, {n}) = {d} divide a {b}",
                    "se cumple" if b % d == 0 else "NO se cumple")
    if b % d:
        return Congruencia((), n, None, None)
    a2, b2, n2 = (a // d) % (n // d), (b // d) % (n // d), n // d
    x0 = (b2 * inverso_modular(a2, n2, trace)) % n2 if n2 > 1 else 0
    soluciones = tuple(sorted((x0 + k * n2) % n for k in range(d)))
    trace.regla("congruencia.soluciones",
                f"se divide entre {d}: {a2}·x ≡ {b2} (mod {n2}), x ≡ {x0}",
                after=", ".join(map(str, soluciones)),
                why=f"hay exactamente mcd = {d} soluciones módulo {n}, separadas {n2}")
    for x in soluciones:
        if (a * x - b) % n:
            raise _error("INTERNAL", "una solución no cumple la congruencia")
    trace.verificacion("congruencia.sustitucion", "cada solución cumple a·x ≡ b (mod n)")
    return Congruencia(soluciones, n, x0, n2)


@dataclass(frozen=True)
class Chino:
    """``x ≡ r (mod m)`` combining the system, or ``None`` when incompatible."""

    resto: int | None
    modulo: int | None

    def texto(self) -> str:
        return ("el sistema es incompatible" if self.resto is None
                else f"x ≡ {self.resto} (mod {self.modulo})")


def teorema_chino(restos, modulos, trace: Trace | None = None) -> Chino:
    """The Chinese remainder theorem, also for moduli that are NOT coprime.

    Pairs are merged one at a time: ``x ≡ r₁ (mod m₁)`` and ``x ≡ r₂ (mod m₂)`` are
    compatible iff ``mcd(m₁, m₂)`` divides ``r₂ − r₁``, and then combine modulo the
    lcm. Coprime moduli are the special case the textbook formula covers.
    """
    trace = trace if trace is not None else Trace()
    restos = [_entero(r, "un resto") for r in restos]
    modulos = [_modulo(m) for m in modulos]
    if len(restos) != len(modulos) or not restos:
        raise _error("BAD_INPUT", "hacen falta tantos restos como módulos, y al menos uno")
    r, m = restos[0] % modulos[0], modulos[0]
    for r2, m2 in zip(restos[1:], modulos[1:]):
        d = gcd(m, m2)
        if (r2 - r) % d:
            trace.aviso("chino.incompatible",
                        f"x ≡ {r} (mod {m}) y x ≡ {r2} (mod {m2}) son incompatibles: "
                        f"mcd = {d} no divide a {r2 - r}")
            return Chino(None, None)
        # m·k ≡ r2 - r (mod m2): k from the congruence, then x = r + m·k
        k = congruencia_lineal(m, r2 - r, m2, trace).x0
        nuevo_m = m // d * m2
        nuevo_r = (r + m * k) % nuevo_m
        trace.regla("chino.combinar", f"x ≡ {nuevo_r} (mod {nuevo_m})",
                    before=f"x ≡ {r} (mod {m}), x ≡ {r2} (mod {m2})",
                    after=f"x ≡ {nuevo_r} (mod {nuevo_m})",
                    why=f"x = {r} + {m}·k con {m}·k ≡ {r2 - r} (mod {m2}); el nuevo "
                        f"módulo es el mcm, {nuevo_m}")
        r, m = nuevo_r, nuevo_m
    for ri, mi in zip(restos, modulos):
        if (r - ri) % mi:
            raise _error("INTERNAL", "la solución del sistema no cumple una ecuación")
    trace.verificacion("chino.sustitucion", "la solución cumple todas las congruencias")
    return Chino(r, m)


# ---------------------------------------------------------------------------
# the structure of ℤₙ
# ---------------------------------------------------------------------------


def factorizacion(n: int) -> dict[int, int]:
    salida: dict[int, int] = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            salida[d] = salida.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        salida[n] = salida.get(n, 0) + 1
    return salida


def phi(n: object, trace: Trace | None = None) -> int:
    """Euler's totient from the factorisation: ``n·Π(1 − 1/p)``."""
    trace = trace if trace is not None else Trace()
    n = _modulo(n)
    resultado = n
    for p in factorizacion(n):
        resultado = resultado // p * (p - 1)
    trace.regla("phi.formula", f"φ({n}) = {resultado}",
                before=" · ".join(f"{p}^{e}" for p, e in factorizacion(n).items()) or "1",
                after=str(resultado), why="φ(n) = n·Π(1 − 1/p) sobre los primos de n")
    if n <= MAX_FUERZA_BRUTA and resultado != sum(1 for k in range(1, n + 1) if gcd(k, n) == 1):
        raise _error("INTERNAL", "φ no coincide con el recuento")
    return resultado


def orden(a: object, n: object, trace: Trace | None = None) -> int:
    """The multiplicative order of ``a`` mod ``n``: the least k with a^k ≡ 1. A divisor of φ(n)."""
    trace = trace if trace is not None else Trace()
    a, n = _entero(a, "a"), _modulo(n)
    if gcd(a, n) != 1:
        raise _error("NO_INVERSE", f"{a} no es invertible módulo {n}: no tiene orden")
    f = phi(n, trace)
    divisores = sorted(k for k in range(1, int(f ** 0.5) + 1) if f % k == 0)
    divisores = sorted(set(divisores + [f // k for k in divisores]))
    for k in divisores:
        if pow(a, k, n) == 1:
            trace.regla("orden.divisor", f"ord({a}) = {k}",
                        why=f"el orden divide a φ({n}) = {f}; es el menor divisor k con a^k ≡ 1")
            return k
    raise _error("INTERNAL", "ningún divisor de φ da 1")


def raiz_primitiva(n: object, trace: Trace | None = None) -> int | None:
    """The least primitive root mod ``n``, or ``None`` when ℤₙ* is not cyclic."""
    trace = trace if trace is not None else Trace()
    n = _modulo(n)
    f = phi(n, trace)
    primos = list(factorizacion(f))
    for g in range(1, n):
        if gcd(g, n) == 1 and all(pow(g, f // p, n) != 1 for p in primos):
            trace.regla("raiz_primitiva", f"{g} es raíz primitiva módulo {n}",
                        why=f"g^(φ/p) ≠ 1 para cada primo p de φ = {f}, así que ord(g) = φ")
            return g
    trace.aviso("raiz_primitiva.no_existe",
                f"ℤ_{n}* no es cíclico: solo hay raíces primitivas para 1, 2, 4, pᵏ y 2pᵏ")
    return None


def es_cuerpo(n: object, trace: Trace | None = None) -> bool:
    """ℤₙ is a field iff n is prime: then every non-zero element has an inverse."""
    trace = trace if trace is not None else Trace()
    n = _modulo(n)
    primo = n > 1 and factorizacion(n) == {n: 1}
    trace.hipotesis("cuerpo.primo", f"{n} es primo", "sí" if primo else "no")
    return primo
