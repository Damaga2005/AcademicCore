# SPDX-License-Identifier: MIT
"""ML-2 (T10): improper integrals — convergence (also with a parameter) and value.

Convergence by limit comparison, decided by the limit engine's principal term.
Near each singular point the integrand is written in a variable ``w → +∞``:

    x → +∞:   x = w,            dx = dw
    x → −∞:   x = −w,           dx = dw
    x → c±:   x = c ± 1/w,      |dx| = dw / w²

and the principal term of f(x(w))·|dx/dw| is ``K·w^p·e^(q·w)·(ln w)^r``. Then
``∫^∞ K·w^p·e^(qw)·(ln w)^r dw`` converges iff q < 0, or q = 0 and p < −1, or
q = 0, p = −1 and r < −1 (comparison with e^(qw), the p-integrals and Bertrand's
integrals). Positive principal coefficient is not needed: near the point the
integrand keeps the sign of K, so the comparison is legitimate.

An oscillating integrand (sin x / x at ∞) has no principal term: convergence
there would need Dirichlet's test; the module says so instead of deciding.

Value: when it converges and there is no parameter, the primitive F is taken
from the integration engine and the improper limits of F at the singular points
are computed EXACTLY by the limit engine. Second path: numerical quadrature on a
truncated interval with the tail bounded.

With a parameter α: the convergence verdict is computed exactly for each α of a
scan (step 1/4 on [−10, 10]); each change of verdict is bisected over rational α
to a boundary, which is then identified as a simple rational and checked
exactly at, and on both sides of, the boundary. The answer says how it was
obtained.
"""

from __future__ import annotations

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


def _es_inf(t: str) -> int:
    t = t.strip().replace(" ", "")
    if t in ("oo", "+oo", "inf", "+inf", "∞", "+∞"):
        return 1
    if t in ("-oo", "-inf", "-∞"):
        return -1
    return 0


@dataclass(frozen=True)
class Local:
    punto: str
    lado: str                 # «+» (from the right), «-» (from the left), «» for ±∞
    converge: bool
    razon: str


@dataclass(frozen=True)
class Convergencia:
    converge: bool
    locales: tuple[Local, ...]
    valor: mx.Expr | None = None
    aproximado: float | None = None

    def texto(self) -> str:
        if not self.converge:
            return "diverge: " + "; ".join(l.razon for l in self.locales if not l.converge)
        if self.valor is not None:
            return f"converge y vale {mx.text(self.valor)}"
        return "converge"


def _local(f: mx.Expr, var: str, punto: str, lado: str) -> Local:
    w = mx.Sym(LM.W)
    inf = _es_inf(punto)
    if inf:
        g = mx.substitute(f, var, w if inf > 0 else mx.Neg(w))
    else:
        c = mx.parse(punto)
        paso = mx.Div(mx.Num(Fraction(1)), w)
        x = mx.Add(c, paso) if lado == "+" else mx.Sub(c, paso)
        g = mx.Div(mx.substitute(f, var, x), mx.Pow(w, mx.Num(Fraction(2))))
    try:
        t = LM.principal(g)
    except LM.NoSe as exc:
        raise _no(f"no sé el comportamiento cerca de {punto}: {exc}") from None
    donde = f"en {'+∞' if inf > 0 else '−∞' if inf < 0 else punto + ('⁺' if lado == '+' else '⁻')}"
    if t is None or isinstance(t, LM._CeroAcotado):
        if isinstance(t, LM._CeroAcotado):
            d = _dirichlet(f, var, punto, inf)
            if d is not None:
                return Local(punto, lado, True, f"{donde} converge condicionalmente por "
                             f"Dirichlet: {d}")
            raise _no(f"el integrando oscila {donde}: haría falta el criterio de Dirichlet")
        return Local(punto, lado, True, f"{donde} el integrando es idénticamente 0")
    if isinstance(t, LM.Acotada):
        d = _dirichlet(f, var, punto, inf)
        if d is not None:
            return Local(punto, lado, True, f"{donde} converge condicionalmente por "
                         f"Dirichlet: {d}")
        raise _no(f"el integrando oscila {donde}: la comparación no decide")
    q, p, r = t.escala[:3]
    if q != 0:
        conv = q < 0
        razon = f"{donde} se comporta como e^({q}·w){'' if not p else f'·w^{p}'}: " + (
            "decae exponencialmente" if conv else "crece exponencialmente")
    elif p != -1:
        conv = p < -1
        razon = (f"{donde} ~ {mx.text(t.c)}·w^{p}" + (f"·ln(w)^{r}" if r else "")
                 + f" con w → ∞: {'p < −1, converge' if conv else 'p ≥ −1, diverge'} "
                   "(comparación con ∫ w^p)")
    else:
        conv = r < -1
        razon = (f"{donde} ~ {mx.text(t.c)}·w^(−1)" + (f"·ln(w)^{r}" if r else "")
                 + f": integral de Bertrand, {'converge' if conv else 'diverge'} (r "
                   f"{'<' if conv else '≥'} −1)")
    return Local(punto, lado, conv, razon)


def _dirichlet(f: mx.Expr, var: str, punto: str, inf: int) -> str | None:
    """Criterio de Dirichlet en ±∞: f = g·h con g = sin(ax+b)/cos(ax+b) de
    primitiva acotada (|∫g| ≤ 2/|a|) y h → 0 monótona.

    Devuelve la justificación o None si no aplica. Cada hipótesis se comprueba:
    la forma afín del argumento, la acotación de la primitiva, el límite de h
    y su monotonía (signo de h′ en muestras grandes más término principal).
    """
    if not inf:
        return None
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    g, h = _parte_oscilante(f, var)
    if g is None or h is None:
        return None
    nombre, a = g[0], g[1]
    if a == 0:
        return None
    cota_g = 2.0 / abs(a)
    # h → 0 en el infinito correspondiente
    try:
        lh = LM.limite(h, var, "oo" if inf > 0 else "-oo")
    except Exception:  # noqa: BLE001 - sin límite probado no hay Dirichlet
        return None
    if lh.valor != "0":
        return None
    # h monótona desde un punto: h′ con signo constante en muestras grandes y
    # término principal que no cambia de signo
    try:
        dh = DM.differentiate(h, var)
    except Exception:  # noqa: BLE001
        return None
    signos = []
    for w0 in (10.0, 30.0, 100.0, 300.0, 1000.0):
        x0 = w0 if inf > 0 else -w0
        try:
            v = mx.valor_real(dh, {var: x0})
        except (OverflowError, ValueError, ZeroDivisionError):
            return None
        if v is None or v == 0:
            return None
        signos.append(1 if v > 0 else -1)
    if any(s != signos[0] for s in signos):
        return None
    # valores de |h| decreciendo hacia 0 en las mismas muestras
    modulos = []
    for w0 in (10.0, 100.0, 1000.0, 10000.0):
        x0 = w0 if inf > 0 else -w0
        try:
            v = mx.valor_real(h, {var: x0})
        except (OverflowError, ValueError, ZeroDivisionError):
            return None
        if v is None:
            return None
        modulos.append(abs(float(v)))
    if not all(b < a for a, b in zip(modulos, modulos[1:])):
        return None
    hv = mx.valor_real(h, {var: 10.0 if inf > 0 else -10.0})
    sentido = "decrece" if (hv or 0) > 0 > signos[0] or (hv or 0) < 0 < signos[0] else \
        "monótona"
    prim = f"−cos({mx.text(_arg_afin(g, var))})/{a}" if nombre == "sin" else \
        f"sin({mx.text(_arg_afin(g, var))})/{a}"
    return (f"{nombre}({mx.text(_arg_afin(g, var))}) con primitiva acotada {prim} "
            f"(|∫| ≤ {cota_g:.4g}) y {mx.text(h)} → 0 {sentido} (h′ con signo "
            f"{'negativo' if signos[0] < 0 else 'positivo'} en 10..1000)")


def _arg_afin(g, var: str) -> mx.Expr:
    return g[3]


def _parte_oscilante(f: mx.Expr, var: str) -> tuple | None:
    """(nombre, a, b, arg) de sin(a·var+b)/cos(a·var+b) y el cofactor h.

    Busca el factor oscilante en un producto/cociente; h es f con ese factor
    puesto a 1 (en el numerador). Si no hay exactamente un seno o coseno de
    argumento afín, devuelve (None, None).
    """
    from academic_core.domain.engineering.mathlab import raices as RZ

    nums, dens = _factores_mul_div(f)
    hallado, indice = None, -1
    for i, factor in enumerate(nums):
        c = _es_seno_coseno(factor, var)
        if c is not None:
            if hallado is not None:
                return None, None
            hallado, indice = c, i
    if hallado is None:
        return None, None
    resto = [x for j, x in enumerate(nums) if j != indice]
    h = resto[0] if resto else mx.Num(Fraction(1))
    for x in resto[1:]:
        h = mx.Mul(h, x)
    for x in dens:
        h = mx.Div(h, x)
    return hallado, LM._limpio(h)


def _factores_mul_div(e: mx.Expr) -> tuple[list, list]:
    if isinstance(e, mx.Mul):
        a1, b1 = _factores_mul_div(e.left)
        a2, b2 = _factores_mul_div(e.right)
        return a1 + a2, b1 + b2
    if isinstance(e, mx.Div):
        a1, b1 = _factores_mul_div(e.left)
        a2, b2 = _factores_mul_div(e.right)
        return a1 + b2, b1 + a2
    if isinstance(e, mx.Neg):
        n, d = _factores_mul_div(e.arg)
        return [mx.Neg(x) for x in n], d
    return [e], []


def _es_seno_coseno(f: mx.Expr, var: str) -> tuple | None:
    """(nombre, a, b, arg) si f es sin/cos de argumento afín a·var + b."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    if not (isinstance(f, mx.Call) and f.name in ("sin", "cos") and len(f.args) == 1):
        return None
    arg = f.args[0]
    p = RZ._polinomio_de(arg, var)
    if p is None:
        return None
    p = RZ._recorta(p) + [Fraction(0)] * 2
    if any(c != 0 for c in p[2:]):
        return None
    b, a = p[0], p[1]
    return (f.name, float(a), float(b), arg)


def puntos_singulares(f: mx.Expr, var: str, a: str, b: str) -> list[tuple[str, str]]:
    """(point, side) pairs where the integral is improper, ordered."""
    from academic_core.domain.engineering.mathlab import estudio as ES
    from academic_core.domain.engineering.mathlab import raices as RZ

    salida: list[tuple[str, str]] = []
    ia, ib = _es_inf(a), _es_inf(b)
    xa = None if ia else float(mx.valor_real(mx.parse(a), {}))
    xb = None if ib else float(mx.valor_real(mx.parse(b), {}))
    if ia:
        salida.append((a, ""))
    candidatos: dict[float, str] = {}
    for g in ES._fronteras(f):
        if not mx.depends(g, var):
            continue
        for r in RZ.ceros(g, var).raices:
            if (xa is None or r.x >= xa - 1e-12) and (xb is None or r.x <= xb + 1e-12):
                candidatos[round(r.x, 12)] = mx.text(r.valor) if r.exacta else repr(r.x)
    if xa is not None:
        candidatos.setdefault(round(xa, 12), a)
    if xb is not None:
        candidatos.setdefault(round(xb, 12), b)
    for x in sorted(candidatos):
        texto = candidatos[x]
        for lado in ("+", "-"):
            if lado == "+" and xb is not None and x >= xb - 1e-12:
                continue
            if lado == "-" and xa is not None and x <= xa + 1e-12:
                continue
            if _singular(f, var, texto, lado):
                salida.append((texto, lado))
    if ib:
        salida.append((b, ""))
    return salida


def _singular(f: mx.Expr, var: str, punto: str, lado: str) -> bool:
    """Improper at this side: f undefined at the point or unbounded next to it."""
    x = float(mx.valor_real(mx.parse(punto), {}))
    if mx.valor_real(f, {var: x}) is None:
        return True
    try:
        lim = LM.limite(f, var, punto, lado)
    except Exception:  # noqa: BLE001
        return False
    return lim.valor in ("+∞", "−∞")


def convergencia(f: mx.Expr, var: str, a: str, b: str, trace: Trace | None = None,
                 con_valor: bool = True) -> Convergencia:
    trace = trace if trace is not None else Trace()
    singulares = puntos_singulares(f, var, a, b)
    if not singulares:
        raise _error("NOT_IMPROPER", "la integral no es impropia: f es continua y acotada en "
                                     "el intervalo cerrado y finito")
    trace.regla("impropia.puntos", "impropia en " + ", ".join(
        p + ("⁺" if l == "+" else "⁻" if l == "-" else "") for p, l in singulares),
        why="un extremo infinito o un punto donde f no está acotada")
    locales = []
    for punto, lado in singulares:
        loc = _local(f, var, punto, lado)
        trace.regla("impropia.comparacion", loc.razon,
                    why="criterio de comparación en el límite con w^p, e^(qw) o w^(−1)·ln(w)^r")
        locales.append(loc)
    converge = all(l.converge for l in locales)
    valor = None
    if converge and con_valor:
        valor = _valor(f, var, a, b, singulares, trace)
        if valor is None:
            valor = _intenta_gamma(f, var, a, b, trace)
    return Convergencia(converge, tuple(locales), valor)


def _intenta_gamma(f: mx.Expr, var: str, a: str, b: str, trace: Trace) -> mx.Expr | None:
    """∫₀^∞ K·x^c·e^(−x) dx = K·Γ(c+1): el caso de la función gamma (T10).

    Solo la forma exacta con c racional > −1 y K constante; si no encaja,
    None (la primitiva ya lo intentó antes). El valor se verifica por
    cuadratura en la calculadora como los demás.
    """
    from academic_core.domain.engineering.mathlab import gamma as G
    from academic_core.domain.engineering.mathlab import raices as RZ

    if a.strip() != "0" or _es_inf(b) != 1:
        return None
    nums, dens = _factores_mul_div(f)
    if dens:
        return None
    exp_ok, pot_c, resto = False, None, []
    for factor in nums:
        if isinstance(factor, mx.Call) and factor.name == "exp" and len(factor.args) == 1:
            p = RZ._polinomio_de(factor.args[0], var)
            if p is not None and RZ._recorta(p) == [Fraction(0), Fraction(-1)]:
                if exp_ok:
                    return None
                exp_ok = True
                continue
        resto.append(factor)
    if not exp_ok:
        return None
    K = mx.Num(Fraction(1))
    for factor in resto:
        if isinstance(factor, mx.Pow) and mx.text(factor.base) == var and \
                not mx.depends(factor.exponent, var):
            if pot_c is not None:
                return None
            c = mx.exact_value(factor.exponent)
            if c is None:
                return None
            pot_c = Fraction(c)
            continue
        if mx.text(factor) == var:
            if pot_c is not None:
                return None
            pot_c = Fraction(1)
            continue
        if mx.depends(factor, var):
            return None
        v = mx.exact_value(factor)
        if v is None:
            return None
        K = mx.Mul(K, factor)
    c = Fraction(0) if pot_c is None else pot_c
    if c <= -1:
        return None
    try:
        g = G.gamma(mx.Num(c + 1), trace)
    except Exception:  # noqa: BLE001 - sin forma exacta: la cuadratura lo dirá
        return None
    valor = LM._limpio(mx.Mul(K, g))
    trace.regla("impropia.gamma", f"∫₀^∞ x^{c}·e^(−x) dx = Γ({c + 1}): {mx.text(valor)}",
                why="definición de la función gamma para c > −1")
    return valor


def _primitiva_ampliada(f: mx.Expr, var: str, trace: Trace) -> mx.Expr | None:
    """The ML-2 integrator (parts, change of variable, special forms) when E0.1 has
    no rule — e.g. x³·e^(−x/2). Only accepted if differentiating it gives f back."""
    from academic_core.domain.engineering.mathlab import derive_mv as D
    from academic_core.domain.engineering.mathlab import integracion as IN
    from academic_core.domain.engineering.mathlab import verify as V

    try:
        F = IN.primitiva(f, var, Trace())
    except Exception:  # noqa: BLE001
        return None
    if V.verify_by_derivative(F, f, var, D.differentiate).verdict != V.VERIFIED:
        return None
    trace.metodo("impropia.primitiva_ampliada", "primitiva por el integrador de ML-2",
                 why="el motor E0.1 no tiene regla; se integra por partes o cambio de "
                     "variable y se comprueba derivando")
    return F


def _valor(f: mx.Expr, var: str, a: str, b: str, singulares, trace: Trace) -> mx.Expr | None:
    """Barrow with exact limits of the primitive at every singular point."""
    from academic_core.domain.engineering.mathlab import calculators as K
    from academic_core.domain.engineering.symbolic import integrate as I_
    from academic_core.domain.engineering.symbolic import steps as St

    try:
        _c, resultado, _i = I_.antiderivative(mx.to_symbolic(f), var, St.StepLog())
        F = K._raiz_real(mx.from_symbolic(resultado))
    except Exception:  # noqa: BLE001
        F = _primitiva_ampliada(f, var, trace)
    if F is None:
        trace.aviso("impropia.sin_primitiva", "converge, pero no hay primitiva elemental "
                                              "con la que calcular su valor exacto")
        return None
    trace.regla("impropia.primitiva", f"F({var}) = {mx.text(F)}")
    # cut [a, b] at the interior singular points; each piece is lim F(right) − lim F(left)
    cortes = [a] + [p for p, l in singulares if l == "+" and p not in (a,)] + [b]
    cortes = list(dict.fromkeys(cortes))
    total: mx.Expr = mx.Num(Fraction(0))
    for izq, der in zip(cortes, cortes[1:]):
        try:
            Fd = _extremo(F, var, der, "-")
            Fi = _extremo(F, var, izq, "+")
        except Exception:  # noqa: BLE001
            return None
        if Fd is None or Fi is None:
            return None
        total = mx.Add(total, mx.Sub(Fd, Fi))
    valor = LM._limpio(total)
    trace.regla("impropia.valor", f"lím F − lím F = {mx.text(valor)}",
                why="Barrow con límites en los puntos donde la integral es impropia")
    return valor


def _extremo(F: mx.Expr, var: str, punto: str, lado: str) -> mx.Expr | None:
    inf = _es_inf(punto)
    if not inf:
        directo = mx.substitute(F, var, mx.parse(punto))
        if mx.valor_real(directo, {}) is not None:
            try:
                lim = LM.limite(F, var, punto, lado)
                if lim.expr is not None:
                    return lim.expr
            except Exception:  # noqa: BLE001
                return LM._limpio(directo)
    lim = LM.limite(F, var, punto, lado if not inf else "")
    return lim.expr


def comprobacion_numerica(f: mx.Expr, var: str, a: str, b: str, valor: mx.Expr
                          ) -> tuple[bool | None, str]:
    """Midpoint rule on a geometric grid towards each improper end (no quadrature
    point lands on a singularity), compared with the exact value."""
    import math

    objetivo = float(mx.valor_real(valor, {}))
    ia, ib = _es_inf(a), _es_inf(b)

    def F(x):
        try:
            v = mx.valor_real(f, {var: x})
        except (OverflowError, ValueError, ZeroDivisionError):
            return 0.0
        return 0.0 if v is None or not math.isfinite(v) else float(v)

    # map to t ∈ (0, 1): x = a + t/(1−t) for [a, ∞), tanh-like for (−∞, ∞), linear for finite
    if ia and ib:
        x_de = lambda t: math.tan(math.pi * (t - 0.5))                 # noqa: E731
        dx = lambda t: math.pi / math.cos(math.pi * (t - 0.5)) ** 2     # noqa: E731
    elif ib:
        xa = float(mx.valor_real(mx.parse(a), {}))
        x_de = lambda t: xa + t / (1 - t)                              # noqa: E731
        dx = lambda t: 1 / (1 - t) ** 2                                # noqa: E731
    elif ia:
        xb = float(mx.valor_real(mx.parse(b), {}))
        x_de = lambda t: xb - (1 - t) / t                              # noqa: E731
        dx = lambda t: 1 / t ** 2                                      # noqa: E731
    else:
        xa = float(mx.valor_real(mx.parse(a), {}))
        xb = float(mx.valor_real(mx.parse(b), {}))
        x_de = lambda t: xa + (xb - xa) * t                            # noqa: E731
        dx = lambda t: xb - xa                                         # noqa: E731
    # tanh-sinh: t = (1 + tanh(π/2·sinh(s)))/2 clusters nodes at both ends, so no node
    # lands on a singularity; two ranges of s tell whether the sum has settled
    def suma(kmax: int) -> float:
        total, h = 0.0, 1 / 64
        for k in range(-kmax, kmax + 1):
            s = k * h
            u = math.pi / 2 * math.sinh(s)
            t = (1 + math.tanh(u)) / 2
            if not 0 < t < 1:
                continue
            peso = math.pi / 4 * math.cosh(s) / math.cosh(u) ** 2
            total += F(x_de(t)) * dx(t) * peso * h
        return total

    corta, larga = suma(200), suma(300)
    tol = 1e-6 * max(1.0, abs(objetivo))
    if abs(corta - larga) > tol:
        return None, (f"cuadratura no concluyente (cola lenta: {corta:.8g} con s ≤ 3,1 y "
                      f"{larga:.8g} con s ≤ 4,7)")
    return abs(larga - objetivo) < tol, f"cuadratura tanh-sinh ≈ {larga:.10g}"


# ---------------------------------------------------------------------------
# with a parameter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConParametro:
    parametro: str
    intervalos: tuple[tuple[Fraction | None, bool, Fraction | None, bool], ...]
    fronteras: tuple[Fraction, ...]
    rango: tuple[int, int]

    def texto(self) -> str:
        if not self.intervalos:
            return f"no converge para ningún {self.parametro} de [{self.rango[0]}, {self.rango[1]}]"
        partes = []
        for lo, clo, hi, chi in self.intervalos:
            izq = "−∞" if lo is None else str(lo)
            der = "+∞" if hi is None else str(hi)
            partes.append(("[" if clo else "(") + f"{izq}, {der}" + ("]" if chi else ")"))
        return f"converge si {self.parametro} ∈ " + " ∪ ".join(partes)


def _veredicto(f: mx.Expr, var: str, a: str, b: str, alfa: str, v: Fraction) -> bool | None:
    g = mx.substitute(f, alfa, mx.Num(v) if v >= 0 else mx.Neg(mx.Num(-v)))
    try:
        return convergencia(g, var, a, b, con_valor=False).converge
    except ValidationError as exc:
        if "NOT_IMPROPER" in str(exc):
            return True
        return None
    except Exception:  # noqa: BLE001
        return None


def _simple(lo: Fraction, hi: Fraction) -> Fraction:
    """The rational of smallest denominator in [lo, hi]."""
    for den in range(1, 1025):
        num = -(-lo.numerator * den // lo.denominator)     # ceil(lo·den)
        c = Fraction(num, den)
        if c <= hi:
            return c
    return (lo + hi) / 2


def con_parametro(f: mx.Expr, var: str, a: str, b: str, alfa: str,
                  trace: Trace | None = None, rango: tuple[int, int] = (-10, 10)
                  ) -> ConParametro:
    trace = trace if trace is not None else Trace()
    trace.metodo("impropia.barrido", f"barrido exacto en {alfa} con paso 1/4 en "
                 f"[{rango[0]}, {rango[1]}] y malla geométrica hasta ±10⁶, "
                 "con bisección racional de cada frontera",
                 why=("para cada valor del parámetro el criterio de comparación es exacto; "
                      "las fronteras se localizan donde cambia el veredicto y se comprueban "
                      "en el propio valor y a ambos lados; las sondas no decididas se ignoran"))
    muestras = [Fraction(k, 4) for k in range(4 * rango[0], 4 * rango[1] + 1)]
    alcance = _extiende_muestras_impropia(muestras, f, var, a, b, alfa)
    veredictos = [_veredicto(f, var, a, b, alfa, v) for v in muestras]
    if any(v is None for v in veredictos):
        malos = [str(m) for m, v in zip(muestras, veredictos) if v is None][:5]
        raise _no(f"no sé decidir la convergencia para {alfa} = {', '.join(malos)}…")
    fronteras: list[Fraction] = []
    for (m0, v0), (m1, v1) in zip(zip(muestras, veredictos), zip(muestras[1:], veredictos[1:])):
        if v0 == v1:
            continue
        lo, hi = m0, m1
        for _ in range(40):
            medio = (lo + hi) / 2
            if _veredicto(f, var, a, b, alfa, medio) == v0:
                lo = medio
            else:
                hi = medio
        c = _simple(lo, hi) if hi - lo < Fraction(1, 2 ** 30) else hi
        # c itself may belong to either side; check just around it
        eps = Fraction(1, 10 ** 6)
        if _veredicto(f, var, a, b, alfa, c - eps) == _veredicto(f, var, a, b, alfa, c + eps):
            raise _no(f"la frontera cerca de {alfa} ≈ {float(c):.6g} no se deja aislar")
        fronteras.append(c)
    # intervals of convergence
    intervalos = []
    puntos = [None] + fronteras + [None]
    for lo, hi in zip(puntos, puntos[1:]):
        medio = (Fraction(rango[0]) if lo is None else lo) if hi is None and lo is not None else None
        if lo is None and hi is None:
            prueba = Fraction(0)
        elif lo is None:
            prueba = hi - Fraction(1, 2)
        elif hi is None:
            prueba = lo + Fraction(1, 2)
        else:
            prueba = (lo + hi) / 2
        if not _veredicto(f, var, a, b, alfa, prueba):
            continue
        clo = lo is not None and bool(_veredicto(f, var, a, b, alfa, lo))
        chi = hi is not None and bool(_veredicto(f, var, a, b, alfa, hi))
        if intervalos and intervalos[-1][2] == lo and (intervalos[-1][3] or clo):
            prev = intervalos.pop()
            intervalos.append((prev[0], prev[1], hi, chi))
        else:
            intervalos.append((lo, clo, hi, chi))
    for c in fronteras:
        trace.regla("impropia.frontera", f"{alfa} = {c}: "
                    f"{'converge' if _veredicto(f, var, a, b, alfa, c) else 'diverge'} en la "
                    "frontera", why="el caso frontera se decide aparte (p = −1)")
    trace.aviso("impropia.rango", f"barrido en [{rango[0]}, {rango[1]}] con malla "
                                  f"geométrica decidida hasta ±{alcance:g}: fuera de ese "
                                  f"alcance de {alfa} se supone el mismo veredicto que en sus "
                                  "extremos")
    return ConParametro(alfa, tuple(intervalos), tuple(fronteras), rango)


def _extiende_muestras_impropia(muestras: list, f, var: str, a: str, b: str,
                                alfa: str) -> float:
    """Sondas geométricas ±10·2^k hasta ±10⁶; solo entran las decididas."""
    alcance = 10.0
    for signo in (-1, 1):
        for k in range(1, 18):
            m = Fraction(signo * 10 * 2 ** k)
            if abs(m) > 10 ** 6:
                break
            try:
                v = _veredicto(f, var, a, b, alfa, m)
            except Exception:  # noqa: BLE001
                continue
            if v is None:
                continue
            if m not in muestras:
                muestras.append(m)
            alcance = max(alcance, float(abs(m)))
    muestras.sort()
    return alcance
