# SPDX-License-Identifier: MIT
"""ML-2 (T6): Taylor polynomial with Lagrange's remainder BOUNDED, as the exam asks.

    f(x) = Pₙ(x) + Rₙ(x),    Rₙ(x) = f⁽ⁿ⁺¹⁾(ξ)/(n+1)!·(x − a)ⁿ⁺¹,  ξ between a and x

so |Rₙ(x)| ≤ M·|x − a|ⁿ⁺¹/(n+1)! with M = max |f⁽ⁿ⁺¹⁾| on the closed interval
between a and x. M is not guessed: it is the absolute maximum of |f⁽ⁿ⁺¹⁾| found by
:func:`estudio.extremos_absolutos` (Weierstrass, hypothesis checked).

Two questions:

- ``aproximar``: P_n(x₀) and the bound on the error at x₀ (or on a whole interval);
- ``orden_minimo``: the smallest n whose bound is below a tolerance ε.

Coefficients are exact (:mod:`serie_formal`), the polynomial is written in powers
of (x − a). Second path: the true error |f(x₀) − Pₙ(x₀)| must not exceed the bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import limite as LM
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import ValidationError

MAX_ORDEN = 30


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def polinomio(f: mx.Expr, var: str, a: mx.Expr, n: int) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import serie_formal as SF

    coefs = SF.coeficientes(f, var, a, n + 1)
    h = mx.Sym(var) if mx.exact_value(a) == 0 else mx.Sub(mx.Sym(var), a)
    total: mx.Expr | None = None
    for k, c in enumerate(coefs):
        c = LM._limpio(c)
        if mx.exact_value(c) == 0:
            continue
        v = mx.valor_real(c, {})
        negativo = v is not None and v < 0 and total is not None
        if negativo:
            c = LM._limpio(mx.Neg(c))
        potencia = h if k == 1 else mx.Pow(h, mx.Num(Fraction(k)))
        termino = c if k == 0 else (potencia if mx.exact_value(c) == 1 else mx.Mul(c, potencia))
        total = termino if total is None else (mx.Sub(total, termino) if negativo
                                               else mx.Add(total, termino))
    return total if total is not None else mx.Num(Fraction(0))


def _derivada(f: mx.Expr, var: str, k: int) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    g = f
    for _ in range(k):
        g = LM._limpio(DM.differentiate(g, var))
    return g


@dataclass(frozen=True)
class Aproximacion:
    n: int
    P: mx.Expr
    valor: mx.Expr | None          # Pₙ(x₀)
    M: mx.Expr
    cota: mx.Expr
    donde: str

    def texto(self, var: str = "x") -> str:
        partes = [f"P_{self.n}({var}) = {mx.text(self.P)}"]
        if self.valor is not None:
            partes.append(f"P_{self.n}({self.donde}) = {mx.text(self.valor)} ≈ "
                          f"{float(mx.valor_real(self.valor, {})):.12g}")
        partes.append(f"|R_{self.n}| ≤ M·|{var} − a|^{self.n + 1}/{self.n + 1}! con "
                      f"M = máx |f^({self.n + 1})| = {mx.text(self.M)}: "
                      f"|R_{self.n}| ≤ {mx.text(self.cota)} ≈ {float(mx.valor_real(self.cota, {})):.6g}")
        return "; ".join(partes)


def _maximo_abs(g: mx.Expr, var: str, lo: mx.Expr, hi: mx.Expr, trace: Trace) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import estudio as ES

    r = ES.extremos_absolutos(g, var, lo, hi, trace)
    vmax = mx.valor_real(r.maximo[0], {})
    vmin = mx.valor_real(r.minimo[0], {})
    return r.maximo[0] if abs(vmax) >= abs(vmin) else LM._limpio(mx.Neg(r.minimo[0]))


def aproximar(f: mx.Expr, var: str, a: mx.Expr, n: int, x0: mx.Expr | None = None,
              intervalo: tuple[mx.Expr, mx.Expr] | None = None,
              trace: Trace | None = None) -> Aproximacion:
    trace = trace if trace is not None else Trace()
    if not 0 <= n <= MAX_ORDEN:
        raise _error("BAD_INPUT", f"orden entre 0 y {MAX_ORDEN}")
    P = polinomio(f, var, a, n)
    trace.regla("taylor.polinomio", f"P_{n}({var}) = {mx.text(P)}",
                why="coeficientes f⁽ᵏ⁾(a)/k! exactos")
    if x0 is not None:
        lo, hi = sorted((a, x0), key=lambda e: mx.valor_real(e, {}))
        donde = mx.text(x0)
    elif intervalo is not None:
        lo, hi = intervalo
        donde = f"[{mx.text(lo)}, {mx.text(hi)}]"
    else:
        raise _error("BAD_INPUT", "da el punto x₀ o el intervalo donde acotar el resto")
    d = _derivada(f, var, n + 1)
    trace.regla("taylor.derivada", f"f^({n + 1})({var}) = {mx.text(d)}")
    if mx.valor_real(lo, {}) == mx.valor_real(hi, {}):
        M = LM._limpio(mx.Call("abs", (mx.substitute(d, var, lo),)))
    else:
        M = _maximo_abs(d, var, lo, hi, trace)
        M = LM._limpio(mx.Call("abs", (M,)))
    trace.regla("taylor.M", f"M = máx |f^({n + 1})| en [{mx.text(lo)}, {mx.text(hi)}] = {mx.text(M)}",
                why="ξ está entre a y x, así que |f⁽ⁿ⁺¹⁾(ξ)| ≤ M (Weierstrass da el máximo)")
    if x0 is not None:
        distancia = LM._limpio(mx.Call("abs", (mx.Sub(x0, a),)))
    else:
        distancia = LM._limpio(mx.Call("abs", (mx.Sub(max((lo, hi), key=lambda e: abs(
            mx.valor_real(mx.Sub(e, a), {}))), a),)))
    cota = LM._limpio(mx.Div(mx.Mul(M, mx.Pow(distancia, mx.Num(Fraction(n + 1)))),
                             mx.Num(Fraction(math.factorial(n + 1)))))
    valor = LM._limpio(mx.substitute(P, var, x0)) if x0 is not None else None
    return Aproximacion(n, P, valor, M, cota, donde)


def orden_minimo(f: mx.Expr, var: str, a: mx.Expr, x0: mx.Expr, eps: float,
                 trace: Trace | None = None) -> Aproximacion:
    trace = trace if trace is not None else Trace()
    for n in range(0, MAX_ORDEN + 1):
        r = aproximar(f, var, a, n, x0=x0, trace=Trace())
        c = float(mx.valor_real(r.cota, {}))
        trace.regla("taylor.prueba", f"n = {n}: cota {c:.4g}" + (" < ε" if c < eps else " ≥ ε"))
        if c < eps:
            return r
    raise _error("NOT_FOUND", f"ningún orden ≤ {MAX_ORDEN} da una cota menor que {eps:g}")


def error_real(f: mx.Expr, var: str, r: Aproximacion, x0: mx.Expr) -> float:
    return abs(float(mx.valor_real(f, {var: float(mx.valor_real(x0, {}))}))
               - float(mx.valor_real(r.valor, {})))
