# SPDX-License-Identifier: MIT
"""ML-2 (T11): numerical series, power series and the sum of a series.

Convergence of Σ aₙ (n ≥ n₀)
---------------------------

1. **Necessary condition**: if aₙ ↛ 0 the series diverges (limit engine).
2. **Positive terms** (eventually): the principal term ``c·n^p·e^(qn)·(ln n)^r`` of
   aₙ decides by LIMIT COMPARISON with the geometric, p- and Bertrand series:
   q < 0 converges, q > 0 diverges, p < −1 converges, p > −1 diverges, and with
   p = −1 it converges iff r < −1.
3. **Alternating** ``(−1)ⁿ·bₙ``: absolute convergence first (2. on bₙ); otherwise
   **Leibniz**: bₙ → 0 and bₙ eventually decreasing, the latter checked by the sign
   of the principal term of b′(x) — conditional convergence.
4. **Factorials** (``n!``, ``factorial(2n)``): the **ratio test**, with
   ``(an+b+a)!/(an+b)! = Π (an+b+i)`` simplified EXACTLY before the limit.

Power series Σ cₙ·(x − x₀)^(k·n)
-------------------------------

Radius by the ratio limit ``R_y = lím |cₙ/cₙ₊₁|`` in y = (x − x₀)^k, then
R = R_y^(1/k); each endpoint is a numerical series studied with the rules above,
so the answer is the full interval of convergence with its ends classified.

Sums
----

- geometric: aₙ₊₁/aₙ = r constant (checked exactly): Σ = a_{n₀}/(1 − r) for |r| < 1;
- telescoping rational: aₙ = Σ Aᵢ/(n + kᵢ) with integer kᵢ and ΣAᵢ = 0 (partial
  fractions over the exact roots of the denominator): Σ = −Σ Aᵢ·H(n₀ + kᵢ − 1),
  H the harmonic numbers — an exact rational.

Second path: partial sums computed numerically (and, for a sum, compared with the
closed form with an error bound from the tail's principal term when available).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import limite as LM
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# reading a term with factorials
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Termino:
    expr: mx.Expr                       # with symbols F_k standing for factorial(arg_k)
    factoriales: tuple[mx.Expr, ...]    # arg_k
    var: str

    def valor(self, n: float) -> float | None:
        env = {self.var: n}
        for k, arg in enumerate(self.factoriales):
            a = mx.valor_real(arg, {self.var: n})
            if a is None or a < 0 or a > 170:
                return None
            env[f"F_{k}"] = math.gamma(a + 1)
        try:
            v = mx.valor_real(self.expr, env)
        except (OverflowError, ValueError, ZeroDivisionError):
            return None
        return None if v is None else float(v)


_FACT_POSTFIJO = re.compile(r"(\b[0-9A-Za-z_]+|\([^()]*\))!")


def leer(texto: str, var: str = "n") -> Termino:
    t = texto.replace("**", "^")
    while _FACT_POSTFIJO.search(t):
        t = _FACT_POSTFIJO.sub(lambda m: f"factorial({m.group(1)})", t)
    factoriales: list[mx.Expr] = []
    salida, i = "", 0
    while True:
        j = t.find("factorial(", i)
        if j < 0:
            salida += t[i:]
            break
        nivel, k = 1, j + len("factorial(")
        while k < len(t) and nivel:
            nivel += {"(": 1, ")": -1}.get(t[k], 0)
            k += 1
        arg = mx.parse(t[j + len("factorial("):k - 1])
        salida += t[i:j] + f"F_{len(factoriales)}"
        factoriales.append(arg)
        i = k
    return Termino(mx.parse(salida), tuple(factoriales), var)


def _sustituye_n(T: Termino, nuevo: mx.Expr) -> mx.Expr:
    return mx.substitute(T.expr, T.var, nuevo)


def cociente(T: Termino) -> mx.Expr:
    """aₙ₊₁/aₙ with every factorial ratio written as the exact product it is:
    (m + d)! = m!·(m + 1)···(m + d). In aₙ₊₁ each F_k becomes F_k·P_k; since F_k is
    a common multiplicative factor of both terms, it is then set to 1 in both — and
    that is CHECKED against the true ratio computed with Γ at a few n."""
    alterna = _factor_alterno(T.expr, T.var)
    if alterna is not None:
        # (−1)^(a(n+1)+m)/(−1)^(an+m) = (−1)^a, said before anything takes ln(−1)
        interno = cociente(Termino(alterna[1], T.factoriales, T.var))
        return mx.Neg(interno) if alterna[2] else interno
    n = mx.Sym(T.var)
    sig = _sustituye_n(T, mx.Add(n, mx.Num(Fraction(1))))
    actual = T.expr
    for k, arg in enumerate(T.factoriales):
        arg_sig = mx.substitute(arg, T.var, mx.Add(n, mx.Num(Fraction(1))))
        d = _constante_entera(mx.Sub(arg_sig, arg), T.var)
        if d is None or d < 0:
            raise _no(f"factorial({mx.text(arg)}): el argumento no avanza un entero fijo ≥ 0")
        producto: mx.Expr = mx.Num(Fraction(1))
        for i in range(1, d + 1):
            producto = mx.Mul(producto, mx.Add(arg, mx.Num(Fraction(i))))
        sig = mx.substitute(sig, f"F_{k}", producto)
        actual = mx.substitute(actual, f"F_{k}", mx.Num(Fraction(1)))
    razon = mx.Div(sig, actual)
    for prueba in (5, 8, 13):
        verdad_a, verdad_b = T.valor(prueba + 1), T.valor(prueba)
        nuestra = mx.valor_real(razon, {T.var: prueba})
        if verdad_a is not None and verdad_b and nuestra is not None:
            if abs(verdad_a / verdad_b - nuestra) > 1e-9 * max(1.0, abs(nuestra)):
                raise _no("los factoriales no aparecen solo como factores: el cociente no "
                          "se simplifica así")
    return razon


def _cociente_viejo(T: Termino) -> mx.Expr:
    n = mx.Sym(T.var)
    sig = _sustituye_n(T, mx.Add(n, mx.Num(Fraction(1))))
    razon: mx.Expr = mx.Div(sig, T.expr)
    for k, arg in enumerate(T.factoriales):
        arg_sig = mx.substitute(arg, T.var, mx.Add(n, mx.Num(Fraction(1))))
        salto = LM._limpio(mx.Sub(arg_sig, arg))
        d = mx.exact_value(salto)
        if d is None or d.denominator != 1:
            raise _no(f"factorial({mx.text(arg)}): el argumento no avanza un entero fijo")
        d = int(d)
        producto: mx.Expr = mx.Num(Fraction(1))
        for i in range(1, abs(d) + 1):
            producto = mx.Mul(producto, mx.Add(arg, mx.Num(Fraction(i))))
        razon = mx.substitute(razon, f"F_{k}", mx.Num(Fraction(1)))   # F_k(n+1)/F_k(n) …
        razon = mx.Mul(razon, producto if d > 0 else mx.Div(mx.Num(Fraction(1)), producto))
    # the substitution of F_k by 1 is only valid because each F_k appears as a
    # factor in numerator and denominator in the same position: check it
    return razon


def _constante_entera(e: mx.Expr, var: str) -> int | None:
    """e as a polynomial in var that is an integer constant (n + 1 − n → 1)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    p = RZ._polinomio_de(e, var)
    if p is None:
        return None
    p = RZ._recorta(p)
    if len(p) > 1:
        return None
    c = p[0] if p else Fraction(0)
    return int(c) if c.denominator == 1 else None


def _signos(e: mx.Expr, var: str, exps: list, signo: list) -> mx.Expr:
    """Take every (−1)^(…), (−c)^(…) and cos(π·(n + m)) out of a product."""
    if isinstance(e, mx.Neg):
        signo[0] = -signo[0]
        return _signos(e.arg, var, exps, signo)
    if isinstance(e, mx.Pow) and mx.depends(e.exponent, var) and not mx.depends(e.base, var):
        c = mx.valor_real(e.base, {})
        if c is not None and c < 0:
            exps.append(e.exponent)
            if c == -1:
                return mx.Num(Fraction(1))
            return mx.Pow(LM._limpio(mx.Neg(e.base)), e.exponent)
    if isinstance(e, mx.Call) and e.name == "cos":
        a1 = mx.valor_real(e.args[0], {var: 1.0})
        a2 = mx.valor_real(e.args[0], {var: 2.0})
        if a1 is not None and a2 is not None and abs((a2 - a1) - math.pi) < 1e-12:
            m = a1 / math.pi - 1
            if abs(m - round(m)) < 1e-12:
                exps.append(mx.Add(mx.Sym(var), mx.Num(Fraction(int(round(m))))) if round(m) >= 0
                            else mx.Sub(mx.Sym(var), mx.Num(Fraction(-int(round(m))))))
                return mx.Num(Fraction(1))
    if isinstance(e, mx.Mul):
        return mx.Mul(_signos(e.left, var, exps, signo), _signos(e.right, var, exps, signo))
    if isinstance(e, mx.Div):
        izq = _signos(e.left, var, exps, signo)
        antes = len(exps)
        der = _signos(e.right, var, exps, signo)
        # (−1)^k in a denominator is (−1)^k as well (its inverse equals itself)
        return mx.Div(izq, der)
    return e


def _factor_alterno(e: mx.Expr, var: str) -> tuple[int, mx.Expr, bool] | None:
    """aₙ = s·(−1)^(a·n + m)·bₙ with bₙ free of signs. Returns (sign of the constant
    part, bₙ, alternates?) — alternating iff the total exponent has odd a."""
    exps: list = []
    signo = [1]
    b = _signos(e, var, exps, signo)
    if not exps:
        return None
    from academic_core.domain.engineering.mathlab import raices as RZ

    total: mx.Expr = mx.Num(Fraction(0))
    for x in exps:
        total = mx.Add(total, x)
    p = RZ._polinomio_de(total, var)
    if p is None:
        return None
    p = RZ._recorta(p) + [Fraction(0)] * 2
    m, a = p[0], p[1]
    if any(c != 0 for c in p[2:]) or m.denominator != 1 or a.denominator != 1:
        return None
    s = signo[0] * (1 if int(m) % 2 == 0 else -1)
    return s, LM._limpio(b), int(a) % 2 == 1


# ---------------------------------------------------------------------------
# convergence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Veredicto:
    tipo: str          # «converge absolutamente», «converge condicionalmente», «diverge»
    criterio: str

    @property
    def converge(self) -> bool:
        return self.tipo.startswith("converge")

    def texto(self) -> str:
        return f"{self.tipo} ({self.criterio})"


def _w(e: mx.Expr, var: str) -> mx.Expr:
    return mx.substitute(e, var, mx.Sym(LM.W))


def _comparacion(b: mx.Expr, var: str) -> Veredicto | None:
    t = LM.principal(_w(b, var))
    if t is None:
        return Veredicto("converge absolutamente", "términos nulos desde un índice")
    if isinstance(t, LM.Acotada) or isinstance(t, LM._CeroAcotado):
        return None
    if t.valor_c < 0:
        t = LM.Termino(LM._limpio(mx.Neg(t.c)), t.p, t.q, t.r, t.sup)
    q, p, r = t.escala[:3]
    desc = f"aₙ ~ {LM._texto_termino(t, var, 'oo', 1)}"
    if q != 0:
        return Veredicto("converge absolutamente" if q < 0 else "diverge",
                         f"{desc}: comparación con una geométrica")
    if p != -1:
        return Veredicto("converge absolutamente" if p < -1 else "diverge",
                         f"{desc}: comparación en el límite con Σ n^({p}), "
                         f"{'p < −1' if p < -1 else 'p ≥ −1'}")
    return Veredicto("converge absolutamente" if r < -1 else "diverge",
                     f"{desc}: serie de Bertrand Σ 1/(n·ln(n)^{-r}), "
                     f"{'converge' if r < -1 else 'diverge'}")


def _mayorante(e: mx.Expr) -> mx.Expr | None:
    """Replace sin/cos factors of a product (numerator side) by 1: |aₙ| ≤ that."""
    if isinstance(e, mx.Call) and e.name in ("sin", "cos"):
        return mx.Num(Fraction(1))
    if isinstance(e, mx.Neg):
        return _mayorante(e.arg)
    if isinstance(e, mx.Mul):
        a, b = _mayorante(e.left), _mayorante(e.right)
        if a is None and b is None:
            return None
        return mx.Mul(a if a is not None else mx.Call("abs", (e.left,)),
                      b if b is not None else mx.Call("abs", (e.right,)))
    if isinstance(e, mx.Div):
        a = _mayorante(e.left)
        return None if a is None else mx.Div(a, mx.Call("abs", (e.right,)))
    return None


def convergencia(T: Termino, n0: int = 1, trace: Trace | None = None) -> Veredicto:
    trace = trace if trace is not None else Trace()
    var = T.var
    if T.factoriales:
        return _cociente(T, trace)
    a = T.expr
    alterna = _factor_alterno(a, var)
    if alterna is not None and not alterna[2]:
        # (−1)^(2n) and the like: a constant sign, not an alternating series
        a = alterna[1] if alterna[0] > 0 else mx.Neg(alterna[1])
        alterna = None
    # 1. necessary condition
    try:
        lim = LM.limite(a if alterna is None else alterna[1], var, "oo")
    except LM.NoSe:
        lim = None
    if lim is not None and lim.valor != "0":
        v = Veredicto("diverge", f"el término general no tiende a 0 (|aₙ| → {lim.texto()})")
        trace.regla("serie.necesaria", v.criterio, why="si Σ aₙ converge, aₙ → 0")
        return v
    trace.regla("serie.necesaria", "aₙ → 0: la condición necesaria se cumple (no basta)")
    if alterna is not None:
        signo, b, _ = alterna
        abs_v = _comparacion(b, var)
        if abs_v is not None and abs_v.converge:
            trace.regla("serie.absoluta", abs_v.criterio, why="la convergencia absoluta "
                                                              "implica la convergencia")
            return abs_v
        # Leibniz: b decreasing eventually: b′ < 0 for large x
        from academic_core.domain.engineering.mathlab import derive_mv as DM

        db = DM.differentiate(b, var)
        t = LM.principal(_w(db, var))
        if isinstance(t, LM.Termino) and not isinstance(t, LM._CeroAcotado) and t.valor_c < 0:
            no_abs = (f"; no absolutamente: {abs_v.criterio}" if abs_v else "")
            v = Veredicto("converge condicionalmente",
                          f"Leibniz: bₙ = {mx.text(b)} → 0 y decreciente desde un índice "
                          f"(b′ ~ {LM._texto_termino(t, var, 'oo', 1)} < 0){no_abs}")
            trace.regla("serie.leibniz", v.criterio)
            return v
        raise _no("serie alternada en la que no sé probar que bₙ decrece")
    v = _comparacion(a, var)
    if v is None:
        cota = _mayorante(a)
        if cota is not None:
            w = _comparacion(cota, var)
            if w is not None and w.converge:
                v = Veredicto("converge absolutamente",
                              f"|aₙ| ≤ {mx.text(LM._limpio(cota))} (|sen|, |cos| ≤ 1), y "
                              + w.criterio)
    if v is None:
        d = _dirichlet_serie(a, var)
        if d is not None:
            trace.regla("serie.dirichlet", d,
                        why="sumas parciales de sin/cos acotadas y el otro factor "
                            "tiende a 0 monótonamente: converge aunque no absolutamente")
            return Veredicto("converge condicionalmente", d)
        raise _no("el término general oscila y no sé acotar |aₙ|")
    trace.regla("serie.comparacion", v.criterio,
                why="comparación en el límite: misma convergencia que la serie de referencia")
    return v


def _dirichlet_serie(a: mx.Expr, var: str) -> str | None:
    """Dirichlet para Σ g(n)·h(n): g = sin/cos(au+b) con sumas parciales acotadas
    (|Σ| ≤ 1/|sin(a/2)|) y h → 0 monótona (h′ de signo constante).

    No cubre el caso uniformemente oscilante sin factor separable: entonces
    devuelve None y el rechazo sigue siendo honesto.
    """
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import raices as RZ

    nums, _dens = _factores_serie(a)
    hallado, resto = None, []
    for factor in nums:
        c = _seno_coseno_afin(factor, var)
        if c is not None and hallado is None:
            hallado = c
        else:
            resto.append(factor)
    dens = list(_dens)
    if hallado is None:
        return None
    nombre, aval, _b = hallado
    if abs(math.sin(aval / 2)) < 1e-12:
        return None
    cota = 1.0 / abs(math.sin(aval / 2))
    h = resto[0] if resto else mx.Num(Fraction(1))
    for x in resto[1:]:
        h = mx.Mul(h, x)
    for x in dens:
        h = mx.Div(h, mx.Call("abs", (x,)))
    try:
        lim = LM.limite(h, var, "oo")
    except Exception:  # noqa: BLE001
        return None
    if lim.valor != "0":
        return None
    try:
        dh = DM.differentiate(h, var)
    except Exception:  # noqa: BLE001
        return None
    t = LM.principal(mx.substitute(dh, var, mx.Sym(LM.W)))
    from academic_core.domain.engineering.mathlab.limite import Termino as _T

    if not (isinstance(t, _T) and t.valor_c < 0):
        return None
    return (f"{nombre} con sumas parciales acotadas (≤ {cota:.4g}) y "
            f"{mx.text(LM._limpio(h))} → 0 decreciente")


def _factores_serie(e: mx.Expr) -> tuple[list, list]:
    if isinstance(e, mx.Mul):
        a1, b1 = _factores_serie(e.left)
        a2, b2 = _factores_serie(e.right)
        return a1 + a2, b1 + b2
    if isinstance(e, mx.Div):
        a1, b1 = _factores_serie(e.left)
        a2, b2 = _factores_serie(e.right)
        return a1 + b2, b1 + a2
    if isinstance(e, mx.Neg):
        n, d = _factores_serie(e.arg)
        return n, d
    return [e], []


def _seno_coseno_afin(f: mx.Expr, var: str) -> tuple | None:
    from academic_core.domain.engineering.mathlab import raices as RZ

    if not (isinstance(f, mx.Call) and f.name in ("sin", "cos") and len(f.args) == 1):
        return None
    p = RZ._polinomio_de(f.args[0], var)
    if p is None:
        return None
    p = RZ._recorta(p) + [Fraction(0)] * 2
    if any(c != 0 for c in p[2:]):
        return None
    return (f.name, float(p[1]), float(p[0]))


def sin_factoriales(T: Termino) -> mx.Expr | None:
    """(n + c)! for several integer c share n!: (n+2)!/n! = (n+1)(n+2). If the common
    n! cancels (checked), the term has no factorial left and the comparison applies."""
    if not T.factoriales:
        return T.expr
    desplazamientos = []
    for arg in T.factoriales:
        c = _constante_entera(mx.Sub(arg, mx.Sym(T.var)), T.var)
        if c is None:
            return None
        desplazamientos.append(c)
    base = min(desplazamientos)
    e = T.expr
    for k, c in enumerate(desplazamientos):
        producto: mx.Expr = mx.Sym("B_0")
        for i in range(base + 1, c + 1):
            producto = mx.Mul(producto, mx.Add(mx.Sym(T.var), mx.Num(Fraction(i))))
        e = mx.substitute(e, f"F_{k}", producto)
    a = mx.valor_real(e, {T.var: 7, "B_0": 2.0})
    b = mx.valor_real(e, {T.var: 7, "B_0": 3.0})
    if a is None or b is None or abs(a - b) > 1e-12 * max(1.0, abs(a)):
        return None
    return LM._limpio(mx.substitute(e, "B_0", mx.Num(Fraction(1))))


def _cociente(T: Termino, trace: Trace) -> Veredicto:
    simple = sin_factoriales(T)
    if simple is not None and simple is not T.expr:
        trace.regla("serie.factoriales", f"aₙ = {mx.text(simple)}",
                    why="(n + c)! = n!·(n + 1)···(n + c): los factoriales se cancelan")
        return convergencia(Termino(simple, (), T.var), trace=trace)
    razon = cociente(T)
    trace.regla("serie.cociente", f"aₙ₊₁/aₙ = {mx.text(LM._limpio(razon))}",
                why="con factoriales, el criterio del cociente: (m+1)!/m! = m + 1 exacto")
    from academic_core.domain.engineering.mathlab import numericos as NU

    try:
        lim = LM.limite(mx.Call("abs", (razon,)), T.var, "oo")
    except LM.NoSe:
        razon = NU._normaliza_n(razon, T.var)
        trace.regla("serie.cociente_agrupado", f"aₙ₊₁/aₙ = {mx.text(razon)}",
                    why="potencias de exponente n agrupadas: (n/(n+1))ⁿ a la vista")
        lim = LM.limite(mx.Call("abs", (razon,)), T.var, "oo")
    if lim.valor == "+∞":
        return Veredicto("diverge", "criterio del cociente: |aₙ₊₁/aₙ| → +∞")
    if lim.expr is None:
        raise _no(f"el cociente no tiene límite ({lim.texto()})")
    L = float(mx.valor_real(lim.expr, {}))
    if abs(L - 1) < 1e-14:
        r = NU._raabe(T, T.var, False, trace)
        if r is not None:
            criterio = r[1].split("(", 1)[1].rsplit(")", 1)[0] if "(" in r[1] else r[1]
            return Veredicto("converge absolutamente" if r[0] else "diverge", criterio)
        raise _no("criterio del cociente con límite 1 y Raabe sin decidir")
    return Veredicto("converge absolutamente" if L < 1 else "diverge",
                     f"criterio del cociente: |aₙ₊₁/aₙ| → {lim.texto()} "
                     f"{'< 1' if L < 1 else '> 1'}")


# ---------------------------------------------------------------------------
# power series
# ---------------------------------------------------------------------------


def suma_potencias(T: Termino, x: str = "x", n0: int = 1,
                   trace: Trace | None = None) -> mx.Expr:
    """Σ_{n≥n0} aₙ(x) en forma cerrada reconociendo la serie de Taylor.

    Familias exactas (y = (x−x₀)^k con el signo de (−1)^n absorbido):
    geométrica (delegada a :func:`suma`), −ln(1−y) = Σ y^n/n,
    exp(y) = Σ y^n/n!, sin/cos por Σ (−1)^n B^{2n(+1)}/(2n(+1)!),
    atan/atanh por Σ ±B^{2n+1}/(2n+1).
    Con n0 > 1 se restan los primeros términos explícitos.
    Lo demás se rechaza con su motivo; el valor se comprueba con sumas
    parciales en un punto interior.
    """
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    n = T.var
    if T.factoriales and any(not _es_afin_factorial(a, n) for a in T.factoriales):
        raise _no("factorial de argumento no afín en n: no es una serie de Taylor")
    alterna = _factor_alterno(T.expr, n)
    base_expr = alterna[1] if alterna is not None else T.expr
    alt = alterna[2] if alterna is not None else False
    signo_const = alterna[0] if alterna is not None else 1
    # potencias con exponente en n y base en x
    potencias = _potencias_en_x(base_expr, x, n)
    if not potencias:
        raise _no(f"no es una serie de potencias en {x}: falta (x − x₀)^(k·n+m)")
    (B, E) = potencias[0]
    for (B2, E2) in potencias[1:]:
        if mx.text(LM._limpio(mx.Sub(E2, E))) != "0" or \
                mx.text(LM._limpio(mx.Div(B2, B))) not in ("1",):
            raise _no("varias potencias con distinto (x − x₀) o exponente: no es una "
                      "serie de Taylor de una sola función")
    pE = RZ._polinomio_de(E, n)
    if pE is None:
        raise _no(f"el exponente no es afín en {n}")
    pE = RZ._recorta(pE) + [Fraction(0)] * 2
    if any(c != 0 for c in pE[2:]) or pE[1] <= 0 or pE[1].denominator != 1:
        raise _no(f"el exponente tiene que ser k·{n} + m con k entero positivo")
    k, m = int(pE[1]), pE[0]
    # y^n·B^m fuera: y = ±B^k (signo de la alternancia absorbido)
    Bk = mx.Pow(B, mx.Num(Fraction(k))) if k != 1 else B
    Bm = mx.Pow(B, mx.Num(m)) if m != 0 else mx.Num(Fraction(1))
    y = LM._limpio(mx.Neg(Bk) if alt else Bk)
    # el resto se divide por la potencia SIN signo: base_expr ya no trae (−1)^n
    yn = mx.Pow(Bk, mx.Sym(n))
    resto = _resto_tras_potencias(base_expr, yn, Bm, m)
    familia = _familia_taylor(resto, T, n, k, m, alt)
    if familia is None:
        raise _no("el coeficiente en n no es 1, 1/n, 1/(2n+1), 1/n!, 1/(2n)! ni "
                  "1/(2n+1)!: no es una serie de Taylor de la tabla")
    nombre, generadora, desde, k_resto = familia
    # K es el signo constante por la constante del resto (2x^n/n → −2ln(1−x));
    # B^m ya está dentro de sin/cos/atan/atanh, y la geométrica lo lleva dentro
    K = LM._limpio(mx.Mul(mx.Num(Fraction(signo_const)), k_resto))
    cerrada = LM._limpio(generadora(y, B, Bm, K))
    if n0 != desde:
        ajuste = _cola_inicial(T, x, n, n0, desde)
        cerrada = LM._limpio(mx.Sub(cerrada, ajuste))
    trace.regla("suma.taylor", f"Σ = {mx.text(cerrada)} ({nombre})",
                why=f"el término es el de la serie de Taylor de {nombre} en y = {mx.text(y)}")
    _verifica_suma_potencias(T, x, n, n0, cerrada, y, trace)
    return cerrada


def _resto_tras_potencias(base_expr: mx.Expr, yn: mx.Expr, Bm: mx.Expr,
                          m: Fraction) -> mx.Expr:
    """base_expr/(yn·Bm) cancelando los factores idénticos exactos.

    Es la división que deja el coeficiente R(n): para x^n/n con y^n = x^n
    da 1/n, no (x^n/n)/x^n. Solo cancela factores con el mismo texto, así
    que nunca identifica lo que no es idéntico.
    """
    num, den = _num_den(_aplana(base_expr))
    yn_num, yn_den = _num_den(yn)
    extras_num = _como_factores(yn_den)
    extras_den = _como_factores(yn_num)
    if m != 0:
        bm_num, bm_den = _num_den(Bm)
        extras_num += _como_factores(bm_den)
        extras_den += _como_factores(bm_num)
    num, den = _cancela_listas(_como_factores(num) + extras_num,
                               _como_factores(den) + extras_den)
    return LM._limpio(mx.Div(num, den)) if mx.text(den) != "1" else LM._limpio(num)


def _como_factores(e: mx.Expr) -> list:
    if isinstance(e, mx.Mul):
        return _como_factores(e.left) + _como_factores(e.right)
    if mx.text(e) == "1":
        return []
    return [e]


def _colapsa_potencia(e: mx.Expr) -> mx.Expr:
    """(a^b)^c → a^(b·c): exacto para n entero (índice de la serie)."""
    if isinstance(e, mx.Pow) and isinstance(e.base, mx.Pow):
        return mx.Pow(e.base.base, _colapsa_potencia(mx.Mul(e.base.exponent, e.exponent)))
    if isinstance(e, mx.Mul):
        return mx.Mul(_colapsa_potencia(e.left), _colapsa_potencia(e.right))
    if isinstance(e, mx.Div):
        return mx.Div(_colapsa_potencia(e.left), _colapsa_potencia(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_colapsa_potencia(e.arg))
    return e


def _cancela_listas(lnum: list, lden: list) -> tuple[mx.Expr, mx.Expr]:
    """Cancela factores entre dos listas: idénticos por texto, y potencias de la
    misma base restando exponentes (Pow(Pow(a,b),c) colapsada antes)."""
    lnum = [_colapsa_potencia(f) for f in lnum]
    lden = [_colapsa_potencia(f) for f in lden]
    pot_num: dict[str, tuple] = {}
    resto_num = []
    for f in lnum:
        if isinstance(f, mx.Pow):
            clave = mx.text(f.base)
            base, exps = pot_num.get(clave, (f.base, []))
            pot_num[clave] = (base, exps + [(1, f.exponent)])
        else:
            resto_num.append(f)
    pot_den: dict[str, tuple] = {}
    resto_den = []
    for f in lden:
        if isinstance(f, mx.Pow):
            clave = mx.text(f.base)
            base, exps = pot_den.get(clave, (f.base, []))
            pot_den[clave] = (base, exps + [(1, f.exponent)])
        else:
            resto_den.append(f)
    for clave in list(pot_num):
        if clave not in pot_den:
            continue
        base, exps_n = pot_num.pop(clave)
        _, exps_d = pot_den.pop(clave)
        exp: mx.Expr = mx.Num(Fraction(0))
        for _, e in exps_n:
            exp = mx.Add(exp, e)
        for _, e in exps_d:
            exp = mx.Sub(exp, e)
        exp = LM._limpio(exp)
        if LM._identico_cero(exp):
            continue
        resto_num.append(mx.Pow(base, exp))
    for clave, (base, pares) in pot_den.items():
        for _, e in pares:
            resto_num.append(mx.Pow(base, LM._limpio(mx.Neg(e))))
    bolsa_den = list(resto_den)
    bolsa_num = []
    for f in resto_num:
        for g in list(bolsa_den):
            if mx.text(f) == mx.text(g) and not isinstance(f, mx.Pow):
                bolsa_den.remove(g)
                break
        else:
            bolsa_num.append(f)
    n2: mx.Expr = mx.Num(Fraction(1))
    for f in bolsa_num:
        n2 = _mul1(n2, f)
    d2: mx.Expr = mx.Num(Fraction(1))
    for f in bolsa_den:
        d2 = _mul1(d2, f)
    return n2, d2


def _cancela_bolsas(num: mx.Expr, den: mx.Expr, qnum: mx.Expr,
                    qden: mx.Expr) -> tuple[mx.Expr, mx.Expr]:
    """(num·qden)/(den·qnum) cancelando factores de idéntico texto uno a uno."""
    bolsa_num = _como_factores(num) + _como_factores(qden)
    bolsa_den = _como_factores(den) + _como_factores(qnum)
    bolsa_num = [_colapsa_potencia(f) for f in bolsa_num]
    bolsa_den = [_colapsa_potencia(f) for f in bolsa_den]
    for f in list(bolsa_num):
        for g in list(bolsa_den):
            if mx.text(f) == mx.text(g):
                bolsa_num.remove(f)
                bolsa_den.remove(g)
                break
    n2: mx.Expr = mx.Num(Fraction(1))
    for f in bolsa_num:
        n2 = _mul1(n2, f)
    d2: mx.Expr = mx.Num(Fraction(1))
    for f in bolsa_den:
        d2 = _mul1(d2, f)
    return n2, d2


def _mul1(a: mx.Expr, b: mx.Expr) -> mx.Expr:
    if mx.text(a) == "1":
        return b
    if mx.text(b) == "1":
        return a
    return mx.Mul(a, b)


def _aplana(e: mx.Expr) -> mx.Expr:
    if isinstance(e, mx.Div):
        a, b = _aplana(e.left), _aplana(e.right)
        na, da = _num_den(a)
        nb, db = _num_den(b)
        return mx.Div(_mul1(na, db), _mul1(da, nb))
    if isinstance(e, mx.Mul):
        return mx.Mul(_aplana(e.left), _aplana(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_aplana(e.arg))
    return e


def _num_den(e: mx.Expr) -> tuple[mx.Expr, mx.Expr]:
    if isinstance(e, mx.Div):
        return e.left, e.right
    return e, mx.Num(Fraction(1))


def _es_afin_factorial(a: mx.Expr, n: str) -> bool:
    from academic_core.domain.engineering.mathlab import raices as RZ

    p = RZ._polinomio_de(a, n)
    if p is None:
        return False
    return len(RZ._recorta(p)) <= 2


def _potencias_en_x(e: mx.Expr, x: str, n: str) -> list[tuple[mx.Expr, mx.Expr]]:
    """[(base, exponente)] con la base en x y el exponente en n."""
    if isinstance(e, mx.Pow) and mx.depends(e.base, x) and not mx.depends(e.base, n) \
            and mx.depends(e.exponent, n) and not mx.depends(e.exponent, x):
        return [(e.base, e.exponent)]
    if isinstance(e, (mx.Mul, mx.Div, mx.Add, mx.Sub)):
        return _potencias_en_x(e.left, x, n) + _potencias_en_x(e.right, x, n)
    if isinstance(e, mx.Neg):
        return _potencias_en_x(e.arg, x, n)
    if isinstance(e, mx.Call):
        salida: list = []
        for a in e.args:
            salida += _potencias_en_x(a, x, n)
        return salida
    return []


def _familia_taylor(resto: mx.Expr, T: Termino, n: str, k: int, m: Fraction,
                    alt: bool):
    """(nombre, generadora(y, B), primer_n) o None.

    El resto es K·R(n): constante en n por R(n) de la tabla. Los factoriales
    de T ya están como F_0; aquí R = 1/F_0 con el argumento comprobado.
    """
    from academic_core.domain.engineering.mathlab import raices as RZ

    resto = LM._limpio(resto)
    # sin factoriales: resto = K, K/n o K/(2n+1)
    if not T.factoriales:
        if not mx.depends(resto, n):
            return ("la serie geométrica",
                    lambda y, B, Bm, K: LM._limpio(mx.Div(mx.Mul(K, Bm),
                                        mx.Sub(mx.Num(Fraction(1)), y))), 0,
                    LM._limpio(resto))
        for a_cand, b_cand in ((Fraction(1), Fraction(0)), (Fraction(2), Fraction(1))):
            q = _igual_a_sobre(resto, n, a_cand, b_cand)
            if q is not None:
                if a_cand == 1 and k == 1 and m == 0 and not alt:
                    return ("−ln(1 − y)",
                            lambda y, B, Bm, K: LM._limpio(mx.Mul(
                                K, mx.Neg(mx.Call("ln", (mx.Sub(
                                    mx.Num(Fraction(1)), y),))))), 1, q)
                if a_cand == 1 and k == 1 and m == 0 and alt:
                    return ("−ln(1 + B) con y = −B",
                            lambda y, B, Bm, K: LM._limpio(mx.Mul(
                                K, mx.Neg(mx.Call("ln", (mx.Add(
                                    mx.Num(Fraction(1)), B),))))), 1, q)
                if a_cand == 2 and k == 2 and m == 1 and alt:
                    return ("atan",
                            lambda y, B, Bm, K: LM._limpio(mx.Mul(K, mx.Call("atan", (B,)))), 0,
                            q)
                if a_cand == 2 and k == 2 and m == 1 and not alt:
                    return ("atanh",
                            lambda y, B, Bm, K: LM._limpio(mx.Mul(
                                K, mx.Mul(mx.Num(Fraction(1, 2)), mx.Call(
                                    "ln", (mx.Div(mx.Add(mx.Num(Fraction(1)), B),
                                                   mx.Sub(mx.Num(Fraction(1)), B)),))))), 0,
                            q)
        return None
    # con un factorial: R = 1/F_0 con argumento afín comprobado
    if len(T.factoriales) != 1:
        return None
    arg = T.factoriales[0]
    p = RZ._polinomio_de(arg, n)
    if p is None:
        return None
    p = RZ._recorta(p) + [Fraction(0)] * 2
    if any(c != 0 for c in p[2:]):
        return None
    fa, fb = p[1], p[0]
    # resto = K/F_0 con K constante en n (K(x) vale)
    num = _constante_en_n(resto, n)
    if num is None:
        return None
    if fa == 1 and fb == 0 and k == 1 and m == 0:
        return ("exp", lambda y, B, Bm, K: LM._limpio(mx.Mul(K, mx.Call("exp", (y,)))), 0,
                num)
    if fa == 2 and fb == 0 and k == 2 and m == 0 and alt:
        return ("cos", lambda y, B, Bm, K: LM._limpio(mx.Mul(K, mx.Call("cos", (B,)))), 0,
                num)
    if fa == 2 and fb == 1 and k == 2 and m == 1 and alt:
        return ("sin", lambda y, B, Bm, K: LM._limpio(mx.Mul(K, mx.Call("sin", (B,)))), 0,
                num)
    return None


def _igual_a_sobre(resto: mx.Expr, n: str, a: Fraction, b: Fraction):
    """K si resto = K/(a·n + b) con K libre de n; None si no."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    num, den = _num_den(_aplana(resto))
    if mx.depends(num, n):
        return None
    p = RZ._polinomio_de(den, n)
    if p is None:
        return None
    pr = RZ._recorta(p)
    if len(pr) > 2:
        return None
    pr = pr + [Fraction(0)] * (2 - len(pr))
    if pr[1] != a or pr[0] != b:
        # denominador proporcional: (a·n+b) con factor constante
        if pr[1] == 0:
            return None
        coc = pr[1] / a
        if pr[0] / coc != b:
            return None
        num = LM._limpio(mx.Div(num, mx.Num(coc)))
    if mx.depends(num, n):
        return None
    return num


def _constante_en_n(resto: mx.Expr, n: str):
    """K(x) con resto = K/F_0 (F_0 el factorial); None si depende de n."""
    e = mx.substitute(resto, "F_0", mx.Sym("_f0"))
    # K = resto·F_0 evaluado en F_0 = 1 es K si K no depende de n
    cand = LM._limpio(mx.substitute(resto, "F_0", mx.Num(Fraction(1))))
    if mx.depends(cand, n):
        return None
    # y además resto·F_0 no depende de n
    prod = LM._limpio(mx.Mul(resto, mx.Sym("F_0")))
    prod = LM._limpio(mx.substitute(prod, "F_0", mx.Num(Fraction(1))))
    if mx.text(prod) != mx.text(cand):
        return None
    return cand


def _cola_inicial(T: Termino, x: str, n: str, n0: int, desde: int) -> mx.Expr:
    """Σ_{j=desde}^{n0−1} a_j(x) explícita (vacía si n0 ≤ desde)."""
    total = mx.Num(Fraction(0))
    for j in range(desde, n0):
        t = LM._limpio(mx.substitute(T.expr, n, mx.Num(Fraction(j))))
        for k, arg in enumerate(T.factoriales):
            v = LM._limpio(mx.substitute(arg, n, mx.Num(Fraction(j))))
            q = mx.exact_value(v)
            if q is None or q < 0 or q.denominator != 1 or int(q) > 170:
                raise _no(f"el término inicial n = {j} no es evaluable exactamente")
            t = mx.substitute(t, f"F_{k}", mx.Num(Fraction(math.factorial(int(q)))))
        total = LM._limpio(mx.Add(total, t))
    return total


def _verifica_suma_potencias(T: Termino, x: str, n: str, n0: int, cerrada: mx.Expr,
                             y: mx.Expr, trace: Trace) -> None:
    """Segundo camino: suma parcial frente a la forma cerrada en un punto interior."""
    punto = None
    for t in (0.5, 0.25, 0.1, -0.5):
        try:
            vy = mx.valor_real(y, {x: t})
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if vy is None or not math.isfinite(vy):
            continue
        if "ln" in mx.text(cerrada) or "atan" in mx.text(cerrada):
            if abs(vy) >= 1 - 1e-12:
                continue
        punto = {x: t}
        break
    if punto is None:
        trace.verificacion("suma_taylor.sin_punto", "forma cerrada no evaluable en el punto")
        return
    objetivo = mx.valor_real(cerrada, punto)
    parcial = 0.0
    for j in range(n0, n0 + 500):
        env = {**punto, n: float(j)}
        for k, arg in enumerate(T.factoriales):
            a = mx.valor_real(arg, {**punto, n: float(j)})
            if a is None or a < 0 or a > 170:
                parcial = None
                break
            env[f"F_{k}"] = math.gamma(a + 1)
        if parcial is None:
            break
        try:
            v = mx.valor_real(T.expr, env)
        except (OverflowError, ValueError, ZeroDivisionError):
            v = None
        if v is None:
            parcial = None
            break
        parcial += float(v)
        if abs(float(v)) < 1e-14 * max(1.0, abs(parcial)):
            break
    if objetivo is None or parcial is None:
        trace.verificacion("suma_taylor.sin_punto", "forma cerrada no evaluable en el punto")
        return
    if abs(parcial - float(objetivo)) > 1e-6 * max(1.0, abs(float(objetivo))):
        raise _no("la forma cerrada no coincide con la suma parcial en el punto")
    trace.verificacion("suma_taylor.parcial",
                       f"S_N ≈ {parcial:.10g} frente a {float(objetivo):.10g} en "
                       f"{x} = {list(punto.values())[0]}")


@dataclass(frozen=True)
class Potencias:
    centro: mx.Expr
    radio: mx.Expr | None              # None = ∞
    extremos: tuple[tuple[str, Veredicto], ...]
    k: int

    def texto(self, var: str = "x") -> str:
        if self.radio is None:
            return "R = ∞: converge en todo ℝ"
        if mx.exact_value(self.radio) == 0:
            return f"R = 0: solo converge en {var} = {mx.text(self.centro)}"
        partes = [f"R = {mx.text(self.radio)}"]
        izq = next((v for s, v in self.extremos if s == "izq"), None)
        der = next((v for s, v in self.extremos if s == "der"), None)
        a = LM._limpio(mx.Sub(self.centro, self.radio))
        b = LM._limpio(mx.Add(self.centro, self.radio))
        intervalo = (("[" if izq and izq.converge else "(") + f"{mx.text(a)}, {mx.text(b)}"
                     + ("]" if der and der.converge else ")"))
        partes.append(f"converge en {intervalo}")
        for lado, v in self.extremos:
            punto = a if lado == "izq" else b
            partes.append(f"en {var} = {mx.text(punto)}: {v.texto()}")
        return "; ".join(partes)


def _separa_potencia(T: Termino, x: str) -> tuple[mx.Expr, mx.Expr, int, Termino]:
    """term = cₙ·(x − x₀)^(k·n + m): returns (x₀, factor, k, cₙ·(x−x₀)^m as Termino)."""
    n = T.var

    def busca(e):
        if isinstance(e, mx.Pow) and mx.depends(e.base, x) and mx.depends(e.exponent, n):
            return e
        for h in ((e.left, e.right) if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)) else
                  (e.arg,) if isinstance(e, mx.Neg) else ()):
            r = busca(h)
            if r is not None:
                return r
        return None

    pot = busca(T.expr)
    if pot is None:
        raise _error("BAD_INPUT", f"no encuentro la potencia (x − x₀)^(k·{n}) en el término")
    from academic_core.domain.engineering.mathlab import raices as RZ

    base_p = RZ._polinomio_de(pot.base, x)
    if base_p is None or len(base_p) != 2 or base_p[1] != 1:
        raise _no("la base de la potencia tiene que ser x − x₀")
    x0 = -base_p[0]
    expo = RZ._polinomio_de(pot.exponent, n)
    if expo is None or len(expo) != 2 or expo[1].denominator != 1 or expo[1] <= 0:
        raise _no(f"el exponente tiene que ser k·{n} + m con k entero positivo")
    k, m = int(expo[1]), expo[0]
    resto = mx.substitute(T.expr, x, mx.Add(mx.Num(x0) if x0 >= 0 else mx.Neg(mx.Num(-x0)),
                                            mx.Sym("_y1")))
    coef = LM._limpio(mx.Div(mx.substitute(T.expr, x, mx.Add(_num(x0), mx.Num(Fraction(1)))),
                             mx.Num(Fraction(1))))
    # cₙ = term evaluated at x − x₀ = 1
    return _num(x0), pot, k, Termino(coef, T.factoriales, n)


def _num(q) -> mx.Expr:
    q = Fraction(q)
    return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))


def potencias(T: Termino, x: str = "x", trace: Trace | None = None) -> Potencias:
    trace = trace if trace is not None else Trace()
    x0, pot, k, C = _separa_potencia(T, x)
    razon = cociente(C)
    lim = LM.limite(mx.Call("abs", (mx.Div(mx.Num(Fraction(1)), razon),)), T.var, "oo")
    trace.regla("potencias.radio", f"R_y = lím |cₙ/cₙ₊₁| = {lim.texto()} (y = (x − x₀)^{k})",
                why="criterio del cociente aplicado a Σ cₙ·yⁿ")
    if lim.valor == "+∞":
        return Potencias(x0, None, (), k)
    if lim.expr is None:
        raise _no(f"el cociente de coeficientes no tiene límite ({lim.texto()})")
    Ry = lim.expr
    R = Ry if k == 1 else LM._limpio(mx.Pow(Ry, mx.Num(Fraction(1, k))))
    if mx.exact_value(R) == 0:
        return Potencias(x0, R, (), k)
    extremos = []
    for lado, s in (("izq", -1), ("der", 1)):
        punto = LM._limpio(mx.Add(x0, mx.Mul(_num(s), R)))
        termino = mx.substitute(T.expr, x, punto)
        try:
            v = convergencia(Termino(LM._limpio(termino), T.factoriales, T.var), trace=Trace())
        except UnsupportedError as exc:
            v = Veredicto("no decidido", str(exc).replace("UNSUPPORTED: ", ""))
        trace.regla("potencias.extremo", f"x = {mx.text(punto)}: {v.texto()}")
        extremos.append((lado, v))
    return Potencias(x0, R, tuple(extremos), k)


# ---------------------------------------------------------------------------
# sums
# ---------------------------------------------------------------------------


def _bernoulli(m: int) -> Fraction:
    """Bₘ por Akiyama–Tanigawa (B₁ = +1/2; solo se usan los pares)."""
    a = [Fraction(0)] * (m + 1)
    for k in range(m + 1):
        a[k] = Fraction(1, k + 1)
        for j in range(k, 0, -1):
            a[j - 1] = j * (a[j - 1] - a[j])
    return a[0]


def _zeta_par(p: int) -> mx.Expr:
    """ζ(p) para p par: (−1)^{p/2+1}·B_p·(2π)^p/(2·p!) = q·π^p, q racional."""
    q = (-1) ** (p // 2 + 1) * _bernoulli(p) * Fraction(2 ** p, 2 * math.factorial(p))
    return mx.Mul(mx.Num(q), mx.Pow(mx.Const("pi"), mx.Num(Fraction(p))))


def _catalogo(T: "Termino", n0: int, trace: Trace) -> mx.Expr | None:
    """Sumas clásicas exactas: Σ c/nᵖ (p par) = c·ζ(p); con (−1)ⁿ, η(p) = (1 − 2^{1−p})ζ(p)
    y η(1) = ln 2; Σ (−1)ⁿ·c/(2n+1) desde 0 = c·π/4. Se suman desde el índice natural
    (1, o 0 en la de Leibniz) y se restan exactamente los términos que sobran."""
    var = T.var
    a = T.expr
    alt = _factor_alterno(a, var)
    nucleo = alt[1] if alt is not None else a
    alterna = alt is not None and alt[2]
    n = mx.Sym(var)
    candidatos = []
    for pot in range(1, 13):
        c = LM._limpio(mx.Mul(nucleo, mx.Pow(n, mx.Num(Fraction(pot)))))
        if not mx.depends(c, var) and mx.exact_value(c) is not None:
            candidatos.append(("p", pot, mx.exact_value(c)))
            break
    c_leibniz = LM._limpio(mx.Mul(nucleo, mx.Add(mx.Mul(mx.Num(Fraction(2)), n), mx.Num(Fraction(1)))))
    if not mx.depends(c_leibniz, var) and mx.exact_value(c_leibniz) is not None and alterna:
        candidatos.append(("leibniz", 1, mx.exact_value(c_leibniz)))
    for tipo, pot, c in candidatos:
        inicio = 0 if tipo == "leibniz" else 1
        a_ini = mx.exact_value(LM._limpio(mx.substitute(a, var, mx.Num(Fraction(inicio)))))
        if a_ini is None or c == 0:
            continue
        # a_inicio = c/(inicio-esimo denominador)·ε con ε = ±1 el signo del primer término
        den_ini = Fraction(1) if tipo == "leibniz" else Fraction(1)
        eps = 1 if a_ini * den_ini / c > 0 else -1
        if tipo == "leibniz":
            base = mx.Mul(mx.Num(Fraction(1, 4)), mx.Const("pi"))
            nombre = "Σ (−1)ⁿ/(2n+1) = π/4 (Leibniz)"
        elif alterna:
            if pot == 1:
                base, nombre = mx.Call("ln", (mx.Num(Fraction(2)),)), "Σ (−1)ⁿ⁺¹/n = ln 2"
            elif pot % 2 == 0:
                base = mx.Mul(mx.Num(1 - Fraction(1, 2 ** (pot - 1))), _zeta_par(pot))
                nombre = f"η({pot}) = (1 − 2^{1 - pot})·ζ({pot})"
            else:
                continue
        else:
            if pot % 2 or pot < 2:
                continue
            base, nombre = _zeta_par(pot), f"ζ({pot}) por los números de Bernoulli"
        if n0 < inicio:
            continue
        total: mx.Expr = mx.Mul(mx.Num(Fraction(eps) * abs(c)), base)
        for j in range(inicio, n0):
            total = mx.Sub(total, LM._limpio(mx.substitute(a, var, mx.Num(Fraction(j)))))
        total = LM._limpio(total)
        trace.regla("suma.catalogo", f"{nombre}; desde n = {n0}: Σ = {mx.pretty(total)}",
                    why="suma clásica con valor cerrado conocido; los términos anteriores al "
                        "índice pedido se restan exactamente")
        return total
    return None


def suma(T: Termino, n0: int = 1, trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    if T.factoriales:
        raise _no("suma con factoriales: sin forma cerrada en este motor (se da la suma "
                  "numérica con su cota)")
    var = T.var
    cat = _catalogo(T, n0, trace)
    if cat is not None:
        return cat
    razon = LM._limpio(cociente(T))
    if mx.depends(razon, var):
        # 3/2ⁿ⁺¹ ÷ 3/2ⁿ does not fold by itself: a constant ratio is its limit, checked
        valores = [mx.valor_real(razon, {var: k}) for k in (n0 + 1, n0 + 2, n0 + 5, n0 + 9)]
        try:
            lim = LM.limite(razon, var, "oo")
        except Exception:  # noqa: BLE001
            lim = None
        if lim is not None and lim.expr is not None and all(
                v is not None and abs(v - mx.valor_real(lim.expr, {})) < 1e-12 for v in valores):
            razon = lim.expr
    if not mx.depends(razon, var):
        r = mx.valor_real(razon, {})
        if r is None or abs(r) >= 1:
            raise _error("DIVERGES", f"geométrica de razón {mx.text(razon)} con |r| ≥ 1: diverge")
        primero = LM._limpio(mx.substitute(T.expr, var, mx.Num(Fraction(n0))))
        s = LM._limpio(mx.Div(primero, mx.Sub(mx.Num(Fraction(1)), razon)))
        trace.regla("suma.geometrica", f"razón r = {mx.text(razon)}, primer término "
                                       f"{mx.text(primero)}: Σ = a/(1 − r) = {mx.text(s)}")
        return s
    return _telescopica(T.expr, var, n0, trace)


def _telescopica(a: mx.Expr, var: str, n0: int, trace: Trace) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    razon = P.as_ratio(a, var)
    if razon is None:
        raise _no("no es geométrica ni racional en n: no sé sumarla en forma cerrada")
    num = RZ._polinomio_de(P.to_expr(razon.numerator), var)
    den = RZ._polinomio_de(P.to_expr(razon.denominator), var)
    if num is None or den is None or len(num) >= len(den) - 1:
        raise _no("el término racional no decrece como 1/n² o más: no es telescópica sumable")
    raices = RZ.raices_polinomio(den).raices
    if len(raices) != len(den) - 1 or any(r.multiplicidad > 1 or not r.exacta for r in raices):
        raise _no("el denominador no se descompone en factores lineales racionales simples")
    dden = [c * k for k, c in enumerate(den)][1:]
    sumandos = []
    for r in raices:
        x = mx.exact_value(r.valor)
        if x is None:
            raise _no("raíz irracional del denominador: no telescopa a un número racional")
        A = RZ._eval(num, x) / RZ._eval(dden, x)
        sumandos.append((A, x))                 # A/(n − x)
    if sum(A for A, _ in sumandos) != 0:
        raise _no("ΣAᵢ ≠ 0: la serie no telescopa")
    # telescopa si las raíces difieren en enteros (x = c + mᵢ con c común); con la
    # digamma, Σₙ Σᵢ Aᵢ/(n − xᵢ) = −Σᵢ Aᵢ·ψ(n₀ − xᵢ) y las diferencias ψ(b + k) − ψ(b)
    # = Σ_{j<k} 1/(b + j) son racionales (antes solo se admitían raíces enteras)
    frac = {x - math.floor(x) for _, x in sumandos}
    if len(frac) != 1:
        raise _no("las raíces no difieren en enteros: no telescopa")
    if any(n0 - x <= 0 for _, x in sumandos):
        raise _no("un término anula el denominador dentro del rango de la suma")
    trace.regla("suma.fracciones", "aₙ = " + " + ".join(f"({A})/(n − ({x}))" for A, x in sumandos),
                why="fracciones simples sobre las raíces del denominador")
    b = min(n0 - x for _, x in sumandos)
    total = Fraction(0)
    for A, x in sumandos:
        k = int(n0 - x - b)
        total -= A * sum((1 / (b + j) for j in range(k)), Fraction(0))
    trace.regla("suma.telescopica", f"Σ = −Σ Aᵢ·[ψ(n₀ − xᵢ) − ψ(b)] = {total}",
                why="las colas se cancelan al tender N a ∞ porque ΣAᵢ = 0")
    return _num(total)


@dataclass(frozen=True)
class SumaNumerica:
    valor: float
    cota: float          # |S − S_N| ≤ cota
    N: int
    q: float             # |aₙ₊₁/aₙ| ≤ q < 1 desde N

    def texto(self) -> str:
        return (f"Σ ≈ {self.valor:.12g} (|error| ≤ {self.cota:.2g}: S_N con N = {self.N} "
                f"y la cola mayorada por la geométrica de razón {self.q:.3g})")


def suma_numerica(T: Termino, n0: int = 1, trace: Trace | None = None,
                  tol: float = 1e-12) -> SumaNumerica:
    """S_N más una cota de la cola: si |aₙ₊₁/aₙ| ≤ q < 1 para n ≥ N, entonces
    |Σ_{n>N} aₙ| ≤ |a_{N+1}|/(1 − q). El límite del cociente se calcula exacto
    (tiene que ser < 1); que el cociente no crezca desde N se comprueba en una
    ventana de 200 términos, no se demuestra: el resultado es solo numérico."""
    trace = trace if trace is not None else Trace()
    try:
        lim = LM.limite(cociente(T), T.var, "oo")
        L = abs(float(mx.valor_real(lim.expr, {}))) if lim.expr is not None else None
    except (UnsupportedError, ValidationError, TypeError, ValueError):
        L = None
    if L is None or not L < 1:
        raise _no("sin forma cerrada y sin cociente que tienda a un valor < 1: no hay "
                  "cota de la cola que dar")
    s, n = 0.0, n0
    terminos = []
    while n < n0 + 5000:
        v = T.valor(n)
        if v is None:
            break
        terminos.append(v)
        s += v
        if len(terminos) >= 2 and terminos[-2] != 0:
            q = abs(terminos[-1] / terminos[-2])
            # la ventana solo se mira cuando la cola ya parece pequeña
            ventana: list[float] = []
            if q < 1 and abs(v) * q / (1 - q) <= tol * max(1.0, abs(s)):
                # hasta 200 términos, o hasta donde se pueden evaluar (Γ desborda en 171!)
                for k in range(n, n + 201):
                    w = T.valor(k)
                    if w is None:
                        break
                    ventana.append(w)
            if len(ventana) > 20:
                razones = [abs(ventana[i + 1] / ventana[i]) if ventana[i] else 0.0
                           for i in range(len(ventana) - 1)]
                if all(r <= q * (1 + 1e-12) for r in razones):
                    cota = abs(ventana[1]) / (1 - q)
                    if cota <= tol * max(1.0, abs(s)):
                        trace.regla("suma.numerica",
                                    f"S_{n} ≈ {s:.15g}; |aₙ₊₁/aₙ| ≤ {q:.4g} desde n = {n} "
                                    f"(comprobado en {len(razones)} términos) "
                                    f"⇒ |cola| ≤ |a_{n + 1}|/(1 − q) ≤ {cota:.2g}",
                                    why="sin forma cerrada: la suma parcial más una cota "
                                        "de lo que falta, mayorado por una geométrica "
                                        f"(el cociente tiende a {L:.4g} < 1)")
                        return SumaNumerica(s, cota, n, q)
        n += 1
    raise _no("la cola no baja de la tolerancia en los términos que se pueden evaluar")


def suma_parcial(T: Termino, n0: int, N: int) -> float | None:
    """S_N; stops early once the terms are below rounding (a geometric series would
    overflow 2ⁿ long before N = 10⁵, after its terms stopped mattering)."""
    s, pequenos = 0.0, 0
    for n in range(n0, N + 1):
        v = T.valor(n)
        if v is None:
            return s if pequenos >= 20 else None
        s += v
        pequenos = pequenos + 1 if abs(v) < 1e-17 * max(1.0, abs(s)) else 0
        if pequenos >= 50:
            break
    return s
