# SPDX-License-Identifier: MIT
"""ML-2 (T10): la función Gamma exacta donde es exacta.

Γ(n) = (n−1)! para enteros n ≥ 1; Γ(k+1/2) = (2k)!·√π/(4^k·k!) para
k ≥ 0; el resto de z < 0 no entero se lleva por Γ(z+1) = z·Γ(z) hasta una
base exacta. Los polos (enteros ≤ 0) son un error, no un valor; lo que no es
entero ni semientero se rechaza con su motivo en exacto (la calculadora
ofrece el valor numérico con su sello).
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


def gamma(z: mx.Expr, trace: Trace | None = None) -> mx.Expr:
    """Γ(z) exacta para z entera o semientera; polos y resto, con su motivo."""
    trace = trace if trace is not None else Trace()
    q = mx.exact_value(z)
    if q is None:
        raise _no(f"Γ({mx.text(z)}): el argumento no es un número exacto")
    q = Fraction(q)
    if q.denominator not in (1, 2):
        raise _no(f"Γ({q}): solo enteros y semienteros tienen forma cerrada exacta")
    if q <= 0 and q == int(q):
        raise _error("POLE", f"Γ({q}): polo en un entero ≤ 0")
    # subir por recurrencia hasta una base exacta ≥ 1/2
    w = q
    divisores: list[Fraction] = []
    while not (w > 0 and (w.denominator == 1 or w.denominator == 2)):
        if w <= 0 and w == int(w):
            raise _error("POLE", f"Γ({q}): polo en el camino ({w})")
        divisores.append(w)
        w += 1
        if len(divisores) > 64:
            raise _no(f"Γ({q}): recurrencia demasiado larga")
    base = _gamma_base(w)
    for d in divisores:
        base = mx.Div(base, _num(d))
    from academic_core.domain.engineering.mathlab import limite as LM

    resultado = LM._limpio(base)
    trace.regla("gamma.recurrencia" if divisores else "gamma.directa",
                f"Γ({q}) = {mx.text(resultado)}",
                why="Γ(n+1) = n! en enteros; Γ(k+1/2) = (2k)!·√π/(4^k·k!); "
                    "Γ(z+1) = z·Γ(z) para bajar el resto")
    return resultado


def _gamma_base(q: Fraction) -> mx.Expr:
    if q.denominator == 1 and q >= 1:
        n = int(q) - 1
        total = 1
        for j in range(2, n + 1):
            total *= j
        return mx.Num(Fraction(total))
    if q.denominator == 2 and q > 0:
        k = int((q - Fraction(1, 2)))
        num, den = 1, 1
        for j in range(2, 2 * k + 1):
            num *= j
        for j in range(2, k + 1):
            den *= j
        den *= 4 ** k
        coef = Fraction(num, den)
        return mx.Mul(_num(coef), mx.Root(2, mx.Const("pi")))
    raise _no(f"Γ({q}): base sin forma cerrada")


def valor_numerico(z: mx.Expr) -> float:
    """Γ(x) numérica para x real positiva no entera (math.gamma como comprobadora)."""
    import math

    v = mx.valor_real(z, {})
    if v is None:
        raise _no("Γ numérica solo para argumento real evaluable")
    if v <= 0:
        raise _error("POLE", "Γ numérica solo para argumento real positivo")
    return math.gamma(float(v))
