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
    q, p, r = t.escala
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
        raise _no("el término general oscila y no sé acotar |aₙ|")
    trace.regla("serie.comparacion", v.criterio,
                why="comparación en el límite: misma convergencia que la serie de referencia")
    return v


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
    lim = LM.limite(mx.Call("abs", (razon,)), T.var, "oo")
    if lim.valor == "+∞":
        return Veredicto("diverge", "criterio del cociente: |aₙ₊₁/aₙ| → +∞")
    if lim.expr is None:
        raise _no(f"el cociente no tiene límite ({lim.texto()})")
    L = float(mx.valor_real(lim.expr, {}))
    if abs(L - 1) < 1e-14:
        raise _no("criterio del cociente con límite 1: no decide")
    return Veredicto("converge absolutamente" if L < 1 else "diverge",
                     f"criterio del cociente: |aₙ₊₁/aₙ| → {lim.texto()} "
                     f"{'< 1' if L < 1 else '> 1'}")


# ---------------------------------------------------------------------------
# power series
# ---------------------------------------------------------------------------


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


def suma(T: Termino, n0: int = 1, trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    if T.factoriales:
        raise _no("suma con factoriales: solo se estudia su convergencia")
    var = T.var
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
        if x is None or x.denominator != 1:
            raise _no("raíz no entera del denominador: no telescopa a un número racional")
        A = RZ._eval(num, x) / RZ._eval(dden, x)
        sumandos.append((A, -int(x)))          # A/(n + k)
    if sum(A for A, _ in sumandos) != 0:
        raise _no("ΣAᵢ ≠ 0: la serie no telescopa")
    trace.regla("suma.fracciones", "aₙ = " + " + ".join(f"({A})/(n + {k})" for A, k in sumandos),
                why="fracciones simples sobre las raíces del denominador")
    total = Fraction(0)
    for A, k in sumandos:
        m = n0 + k - 1
        if m < 0:
            raise _no("un término se anula el denominador dentro del rango de la suma")
        total -= A * sum((Fraction(1, j) for j in range(1, m + 1)), Fraction(0))
    trace.regla("suma.telescopica", f"Σ = −Σ Aᵢ·H(n₀ + kᵢ − 1) = {total}",
                why="los armónicos H(N + kᵢ) se cancelan al tender N a ∞ porque ΣAᵢ = 0")
    return _num(total)


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
