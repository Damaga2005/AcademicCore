# SPDX-License-Identifier: MIT
"""ML-8 (§4.5): transformada z unilateral, inversa y ecuaciones en diferencias.

Directa (x[n] causal, n ≥ 0): cada término c·nᵏ·ρⁿ·{1, cos βn, sen βn} sale de

    Z{ρⁿ} = z/(z − ρ),
    Z{ρⁿcos βn} = z(z − ρcos β)/(z² − 2ρz·cos β + ρ²),
    Z{ρⁿsen βn} = zρ·sen β/(z² − 2ρz·cos β + ρ²),
    Z{nᵏ·x[n]} = (−z·d/dz)ᵏ X(z),

más δ[n − k] → z^{−k} y x[n]·u[n − k] → z^{−k}·Z{x[n + k]}. Región: |z| > máx ρ.

Inversa (secuencia causal, |z| > el polo de mayor módulo): fracciones simples de
X(z)/z sobre ℚ y la tabla: z/(z − p)ᵏ ↔ C(n, k−1)·p^{n−k+1}; pares complejos
ρ^{±iθ} ↔ ρⁿcos θn, ρⁿsen θn; z^{1−k} ↔ δ[n − k + 1].

Ecuaciones en diferencias Σ aₖ·y[n − k] = Σ bₖ·x[n − k] con y[−1], y[−2]… dados:
Z{y[n − k]} = z^{−k}Y + Σⱼ y[−j]·z^{j−k}; H(z) = B(z)/A(z) y h[n] = Z⁻¹{H}.

Comprobación: la inversa se compara con la división larga de X(z) en potencias de
z⁻¹ (x[0], x[1]… exactos); la solución de la ecuación, con la recurrencia iterada.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import laplace as LP
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

limpio = Q.limpio
Z = "z"


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _bonito(e):
    from academic_core.domain.engineering.mathlab import fourier as FO

    return FO._bonito(e)


def prepara(texto: str) -> str:
    texto = texto.replace("δ", "delta").replace("**", "^")
    texto = re.sub(r"(?<![A-Za-z_])(u|H)\s*[\[(]", "heaviside(", texto)
    texto = re.sub(r"delta\s*\[", "delta(", texto)
    texto = re.sub(r"\[", "(", texto).replace("]", ")")
    return mx.normaliza_entrada(texto)


def _negativas(e: mx.Expr, n: str) -> mx.Expr:
    """(−a)ⁿ → aⁿ·cos(πn): base negativa como oscilación."""
    if isinstance(e, mx.Pow) and mx.depends(e.exponent, n) and not mx.depends(e.base, n):
        b = mx.valor_real(e.base, {})
        if b is not None and b < 0:
            pos = limpio(mx.Neg(e.base))
            return mx.Mul(mx.Pow(pos, e.exponent),
                          mx.Call("cos", (limpio(mx.Mul(mx.Const("pi"), e.exponent)),)))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_negativas(e.left, n), _negativas(e.right, n))
    if isinstance(e, mx.Neg):
        return mx.Neg(_negativas(e.arg, n))
    if isinstance(e, mx.Pow):
        return mx.Pow(_negativas(e.base, n), e.exponent)
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_negativas(a, n) for a in e.args))
    return e


def _rho_de(alfa: mx.Expr) -> mx.Expr:
    """e^α, con e^{ln a} = a."""
    if isinstance(alfa, mx.Call) and alfa.name == "ln":
        return alfa.args[0]
    return _bonito(mx.Call("exp", (alfa,)))


def z_termino(x: Q.Termino) -> mx.Expr:
    """Z{c·nᵏ·e^{αn}·f(βn)} como expresión racional en z."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    z = mx.Sym(Z)
    rho = _rho_de(x.alfa)
    if x.tipo == "1":
        X = mx.Div(z, mx.Sub(z, rho))
    else:
        cb = limpio(mx.Call("cos", (x.beta,)))
        sb = limpio(mx.Call("sin", (x.beta,)))
        den = mx.Add(mx.Sub(mx.Pow(z, mx.Num(2)), mx.Mul(mx.Mul(mx.Num(2), rho), mx.Mul(z, cb))),
                     mx.Pow(rho, mx.Num(2)))
        if x.tipo == "cos":
            X = mx.Div(mx.Mul(z, mx.Sub(z, mx.Mul(rho, cb))), den)
        else:
            X = mx.Div(mx.Mul(mx.Mul(z, rho), sb), den)
    for _ in range(x.n):
        X = mx.Neg(mx.Mul(z, DM.differentiate(X, Z)))
    return _bonito(mx.Mul(x.coef, X))


@dataclass
class DirectaZ:
    X: mx.Expr
    radio: float | None
    radio_txt: str

    def texto(self) -> str:
        return f"X(z) = {racional_txt(self.X)}; región de convergencia: {self.radio_txt}"


def _terminos(e: mx.Expr) -> list[mx.Expr]:
    out = []

    def aplana(nd, signo):
        if isinstance(nd, mx.Add):
            aplana(nd.left, signo)
            aplana(nd.right, signo)
        elif isinstance(nd, mx.Sub):
            aplana(nd.left, signo)
            aplana(nd.right, -signo)
        elif isinstance(nd, mx.Neg):
            aplana(nd.arg, -signo)
        else:
            out.append(nd if signo > 0 else mx.Neg(nd))
    aplana(e, 1)
    return out


def _factores(e: mx.Expr) -> tuple[list, list, list, int]:
    """(deltas, escalones, resto, signo) de un término producto."""
    deltas, escalones, resto = [], [], []
    signo = 1

    def recorre(nd):
        nonlocal signo
        if isinstance(nd, mx.Mul):
            recorre(nd.left)
            recorre(nd.right)
        elif isinstance(nd, mx.Neg):
            signo = -signo
            recorre(nd.arg)
        elif isinstance(nd, mx.Call) and nd.name == "delta":
            deltas.append(nd.args[0])
        elif isinstance(nd, mx.Call) and nd.name == "heaviside":
            escalones.append(nd.args[0])
        else:
            resto.append(nd)
    if isinstance(e, mx.Div):
        recorre(e.left)
        resto.append(mx.Div(mx.Num(Fraction(1)), e.right))
    else:
        recorre(e)
    return deltas, escalones, resto, signo


def _desfase(arg: mx.Expr, n: str) -> int:
    lin = Q._lineal(arg, n)
    if lin is None or mx.exact_value(lin[0]) != 1:
        raise _no(f"«{mx.text(arg)}»: solo desplazamientos n − k")
    k = mx.exact_value(limpio(mx.Neg(lin[1])))
    if k is None or Fraction(k).denominator != 1:
        raise _no(f"«{mx.text(arg)}»: el desplazamiento tiene que ser entero")
    return int(k)


def transformada(texto: str, n: str = "n", trace: Trace | None = None) -> DirectaZ:
    trace = trace if trace is not None else Trace()
    e = LP._expande(mx.parse(prepara(texto)))
    z = mx.Sym(Z)
    total = None
    radio = None
    for term in _terminos(e):
        deltas, escalones, resto, signo = _factores(term)
        g = mx.Num(Fraction(signo))
        for r in resto:
            g = mx.Mul(g, r)
        g = _negativas(limpio(g), n)
        if deltas:
            if len(deltas) > 1:
                raise _no("producto de dos deltas")
            k = _desfase(deltas[0], n)
            if k < 0:
                continue                     # fuera de n ≥ 0 (unilateral)
            c = limpio(mx.substitute(g, n, mx.Num(Fraction(k))))
            for a in escalones:
                if (mx.valor_real(mx.substitute(a, n, mx.Num(Fraction(k))), {}) or 0) < 0:
                    c = mx.Num(Fraction(0))
            X = _bonito(mx.Mul(c, mx.Pow(z, mx.Num(Fraction(-k)))))
            trace.regla("z.delta", f"δ[{n} − {k}] → z^(−{k})", why="definición")
        else:
            k = max([_desfase(a, n) for a in escalones] + [0])
            ts = Q.leer(mx.substitute(g, n, mx.Sym("t")), "t")
            if k:
                ts = Q.desplaza(ts, mx.Num(Fraction(k)))
            X = None
            for x in ts:
                Xi = z_termino(x)
                X = Xi if X is None else mx.Add(X, Xi)
                rv = mx.valor_real(_rho_de(x.alfa), {})
                if rv is not None and (radio is None or abs(rv) > radio):
                    radio = abs(rv)
            if X is None:
                continue
            if k:
                X = mx.Mul(mx.Pow(z, mx.Num(Fraction(-k))), X)
                trace.regla("z.retardo", f"x[{n}]·u[{n} − {k}] → z^(−{k})·Z{{x[{n} + {k}]}}",
                            why="desplazamiento en el tiempo")
        total = X if total is None else mx.Add(total, X)
    X = _bonito(total) if total is not None else mx.Num(Fraction(0))
    txt = "todo z ≠ 0" if radio is None else f"|z| > {_txt_num(radio)}"
    r = DirectaZ(X, radio, txt)
    trace.regla("z.directa", r.texto(), why="tabla: Z{ρⁿ} = z/(z − ρ), Z{ρⁿcos βn}, "
                "Z{ρⁿsen βn} y Z{nᵏx[n]} = (−z·d/dz)ᵏX(z)")
    _verifica_directa(e, n, r, trace)
    return r


def racional_txt(X: mx.Expr, var: str = Z) -> str:
    """N(z)/D(z) en potencias decrecientes con coeficientes enteros si se puede."""
    try:
        num, den = LP._num_den(mx.substitute(X, var, mx.Sym("s")), "s")
    except Exception:  # noqa: BLE001
        return mx.text(X)
    fr = LP.Fraccion(mx.Num(Fraction(0)), num, den)
    d = LP.Directa([fr], None, "", None)
    try:
        partes = d.agrupada_texto()
    except Exception:  # noqa: BLE001
        return mx.text(X)
    if not partes:
        return "0"
    return partes[0][1].replace("s", var)


def _txt_num(v: float) -> str:
    q = Fraction(v).limit_denominator(1000)
    return str(q) if abs(float(q) - v) < 1e-12 else f"{v:.10g}"


def _valor_x(e: mx.Expr, n: str, k: int) -> float:
    """x[k] evaluando escalones y deltas discretos."""
    def ev(nd):
        if isinstance(nd, mx.Call) and nd.name == "delta":
            v = mx.valor_real(mx.substitute(nd.args[0], n, mx.Num(Fraction(k))), {})
            return mx.Num(Fraction(1 if v is not None and abs(v) < 1e-12 else 0))
        if isinstance(nd, mx.Call) and nd.name == "heaviside":
            v = mx.valor_real(mx.substitute(nd.args[0], n, mx.Num(Fraction(k))), {})
            return mx.Num(Fraction(1 if v is not None and v >= 0 else 0))
        if isinstance(nd, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(nd)(ev(nd.left), ev(nd.right))
        if isinstance(nd, mx.Neg):
            return mx.Neg(ev(nd.arg))
        if isinstance(nd, mx.Pow):
            return mx.Pow(ev(nd.base), ev(nd.exponent))
        if isinstance(nd, mx.Call):
            return mx.Call(nd.name, tuple(ev(a) for a in nd.args))
        return nd
    v = mx.valor_real(ev(e), {n: k})
    return float(v) if v is not None else float("nan")


def _verifica_directa(e, n, r: DirectaZ, trace) -> None:
    """Σ x[k]·z^{−k} hasta converger, en dos z reales de la región."""
    base = 1.0 if r.radio is None else r.radio
    peor = 0.0
    for zv in (base * 1.7 + 0.5, base * 3.1 + 1.0):
        suma = 0.0
        cota = base / zv
        for k in range(0, 2000):
            xk = _valor_x(e, n, k)
            term = xk * zv ** (-k)
            suma += term
            if k > 30 and (k + 1) ** 4 * cota ** k < 1e-18:
                break           # la cola está acotada por C·k⁴·(ρ/|z|)^k
        ex = mx.valor_real(r.X, {Z: zv})
        if ex is None:
            raise _error("DISCREPANT", "X(z) no evaluable")
        peor = max(peor, abs(ex - suma) / max(1.0, abs(ex)))
    if peor > 1e-9:
        raise _error("DISCREPANT", f"X(z) frente a Σx[n]z^(−n): desviación {peor:.3g}")
    trace.verificacion("z.serie", f"X(z) frente a la serie Σ x[n]·z^(−n) sumada en dos z "
                       f"de la región (desviación {peor:.2g})", why="la definición")


# ---------------------------------------------------------------------------
# inversa
# ---------------------------------------------------------------------------


def _binomial_n(k: int, n: str) -> mx.Expr:
    """C(n, k) como polinomio en n."""
    e: mx.Expr = mx.Num(Fraction(1))
    for j in range(k):
        e = mx.Mul(e, mx.Sub(mx.Sym(n), mx.Num(Fraction(j))))
    return limpio(mx.Div(e, mx.Num(Fraction(math.factorial(k)))))


@dataclass
class InversaZ:
    x: mx.Expr
    deltas: list           # [(k, c)]
    polos: str

    def texto(self, n: str = "n") -> str:
        partes = []
        if not Q.es_cero(self.x):
            partes.append(f"({mx.text(self.x)})·u[{n}]")
        for k, c in self.deltas:
            d = f"δ[{n}]" if k == 0 else f"δ[{n} − {k}]"
            partes.append(d if mx.exact_value(c) == 1 else f"{mx.text(c)}·{d}")
        return f"x[{n}] = " + (" + ".join(partes) if partes else "0") + f" (causal; {self.polos})"

    def valor(self, k: int, n: str = "n") -> float:
        v = 0.0
        if k >= 0 and not Q.es_cero(self.x):
            w = mx.valor_real(self.x, {n: k})
            v += float(w) if w is not None else float("nan")
        for j, c in self.deltas:
            if j == k:
                v += float(mx.valor_real(c, {}))
        return v


def inversa(X: mx.Expr | str, n: str = "n", trace: Trace | None = None) -> InversaZ:
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    if isinstance(X, str):
        X = mx.parse(mx.normaliza_entrada(X))
    num, den = LP._num_den(mx.substitute(X, Z, mx.Sym("s")), "s")
    # X(z)/z: el denominador se multiplica por z
    den_z = AL._p_mul(list(den), [Fraction(0), Fraction(1)])
    entera, simples = LP.simples(num, den_z)
    if any(not Q.es_cero(c) for c in entera):
        raise _error("INTERNAL", "X(z)/z con parte entera: no debería pasar")
    N = mx.Sym(n)
    x_total: mx.Expr = mx.Num(Fraction(0))
    deltas: dict[int, mx.Expr] = {}
    polos = []
    for f in simples:
        if len(f.q) == 2:
            p = -f.q[0]
            A = f.A[0]
            if p == 0:
                # A/z^k · z = A·z^{1−k} ↔ A·δ[n − (k − 1)]
                deltas[f.k - 1] = limpio(mx.Add(deltas.get(f.k - 1, mx.Num(Fraction(0))), A))
                continue
            polos.append(str(p))
            term = mx.Mul(A, mx.Mul(_binomial_n(f.k - 1, n),
                                    mx.Pow(Q.num(p), limpio(mx.Sub(N, mx.Num(Fraction(f.k - 1)))))))
            x_total = mx.Add(x_total, term)
        else:
            if f.k > 1:
                raise _no("polos complejos o irracionales repetidos: fuera de la tabla")
            c0, b = f.q[0], f.q[1]
            disc = b * b - 4 * c0
            B = f.A[1] if len(f.A) > 1 else mx.Num(Fraction(0))
            C = f.A[0]
            if disc < 0:
                rho = limpio(mx.Root(2, Q.num(c0)))
                cos_t = limpio(mx.Div(Q.num(-b / 2), rho))
                theta = _angulo(cos_t)
                sin_t = limpio(mx.Call("sin", (theta,)))
                polos.append(f"{mx.text(rho)}·e^(±i·{mx.text(theta)})")
                # (B z + C)·z/q = B·z(z − ρcos θ) + (C + Bρcos θ)·z
                D = limpio(mx.Add(C, mx.Mul(B, mx.Mul(rho, cos_t))))
                rn = mx.Pow(rho, N)
                term = mx.Mul(rn, mx.Add(mx.Mul(B, mx.Call("cos", (mx.Mul(theta, N),))),
                                         mx.Mul(mx.Div(D, mx.Mul(rho, sin_t)),
                                                mx.Call("sin", (mx.Mul(theta, N),)))))
                x_total = mx.Add(x_total, term)
            else:
                # raíces reales irracionales p₁, p₂: residuos (B·pᵢ + C)/(pᵢ − pⱼ)
                r = limpio(mx.Root(2, Q.num(disc)))
                p1 = limpio(mx.Div(mx.Add(Q.num(-b), r), mx.Num(2)))
                p2 = limpio(mx.Div(mx.Sub(Q.num(-b), r), mx.Num(2)))
                polos.append(f"{mx.text(p1)}, {mx.text(p2)}")
                for pi_, pj in ((p1, p2), (p2, p1)):
                    res = _bonito(mx.Div(mx.Add(mx.Mul(B, pi_), C), mx.Sub(pi_, pj)))
                    x_total = mx.Add(x_total, mx.Mul(res, mx.Pow(pi_, N)))
    x = _bonito(x_total)
    r = InversaZ(x, sorted(deltas.items()), "polos: " + (", ".join(polos) or "solo en 0"))
    trace.regla("z.inversa", r.texto(n), why="fracciones simples de X(z)/z y la tabla "
                "z/(z − p)ᵏ ↔ C(n, k−1)·p^(n−k+1), pares complejos ↔ ρⁿcos θn, ρⁿsen θn")
    _verifica_inversa(num, den, r, n, trace)
    return r


def _angulo(c: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        notable = MI._angulo_notable("acos", c)
    except Exception:  # noqa: BLE001
        notable = None
    return notable if notable is not None else mx.Call("acos", (c,))


def _verifica_inversa(num, den, r: InversaZ, n, trace) -> None:
    """División larga de num(z)/den(z) en potencias de z⁻¹."""
    numf = [float(mx.valor_real(c, {})) for c in num]
    denf = [float(c) for c in den]
    grado = len(denf) - 1
    # x[k] = coeficiente de z^{−k}: numf como serie en z⁻¹
    N_ = list(reversed(numf)) + [0.0] * 40
    D_ = list(reversed(denf))
    desplaz = grado - (len(numf) - 1)
    coefs = []
    resto = N_[:]
    for k in range(30):
        c = resto[k] / D_[0] if k < len(resto) else 0.0
        coefs.append(c)
        for j in range(1, len(D_)):
            if k + j < len(resto):
                resto[k + j] -= c * D_[j]
    peor = 0.0
    for k in range(25):
        idx = k - desplaz
        esperado = coefs[idx] if 0 <= idx < len(coefs) else 0.0
        obtenido = r.valor(k, n)
        peor = max(peor, abs(esperado - obtenido) / max(1.0, abs(esperado)))
    if peor > 1e-8:
        raise _error("DISCREPANT", f"x[n] frente a la división larga: desviación {peor:.3g}")
    trace.verificacion("z.division", f"x[0]…x[24] coinciden con la división larga de X(z) "
                       f"(desviación {peor:.2g})", why="X(z) = Σ x[n]·z^(−n)")


# ---------------------------------------------------------------------------
# ecuaciones en diferencias
# ---------------------------------------------------------------------------


@dataclass
class Diferencias:
    H: mx.Expr
    h: InversaZ
    y: InversaZ | None

    def texto(self, n: str = "n") -> str:
        t = f"H(z) = {racional_txt(self.H)}; h: {self.h.texto(n).replace('x[', 'h[', 1)}"
        if self.y is not None:
            t += f"; y: {self.y.texto(n).replace('x[', 'y[', 1)}"
        return t


def diferencias(ecuacion: str, x: str | None = None, iniciales: dict | None = None,
                n: str = "n", trace: Trace | None = None) -> Diferencias:
    """«y[n] - 5/6*y[n-1] + 1/6*y[n-2] = x[n] + x[n-1]»; iniciales = {-1: y[−1], …}."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    iniciales = {int(k): mx.parse(str(v)) for k, v in (iniciales or {}).items()}
    lhs, rhs = ecuacion.split("=", 1) if "=" in ecuacion else (ecuacion, "0")

    def coefs_de(texto, nombre):
        texto = texto.replace(" ", "")
        out: dict[int, mx.Expr] = {}
        resto = texto
        for m in re.finditer(nombre + r"\[" + n + r"(?:([+-])(\d+))?\]", texto):
            k = int(m.group(2)) if m.group(2) else 0
            if m.group(1) == "+":
                raise _no("solo retardos y[n − k] (k ≥ 0)")
            simb = f"{nombre.upper()}{k}__"
            resto = resto.replace(m.group(0), simb)
        e = mx.parse(mx.normaliza_entrada(resto)) if resto else mx.Num(Fraction(0))
        from academic_core.domain.engineering.mathlab import derive_mv as DM
        for v in sorted(mx.variables(e)):
            if v.startswith(nombre.upper()) and v.endswith("__"):
                k = int(v[1:-2])
                out[k] = limpio(DM.differentiate(e, v))
        libre = e
        for v in mx.variables(e):
            if v.startswith(nombre.upper()) and v.endswith("__"):
                libre = mx.substitute(libre, v, mx.Num(Fraction(0)))
        return out, limpio(libre)

    a, libre_l = coefs_de(lhs, "y")
    b, libre_r = coefs_de(rhs, "x")
    if not a:
        raise _error("BAD_INPUT", "la ecuación no tiene términos y[n − k]")
    K = max(list(a) + list(b) + [0])
    aq = [Fraction(mx.exact_value(a.get(k, mx.Num(0))) or 0) for k in range(K + 1)]
    bq = [Fraction(mx.exact_value(b.get(k, mx.Num(0))) or 0) for k in range(K + 1)]
    # A(z)·z^K y B(z)·z^K como polinomios en z (grado bajo a alto)
    Az = [aq[K - j] for j in range(K + 1)]
    Bz = [bq[K - j] for j in range(K + 1)]
    z = mx.Sym(Z)
    H = _bonito(mx.Div(LP._q_a_expr(Bz, Z), LP._q_a_expr(Az, Z)))
    trace.regla("z.H", f"H(z) = B(z)/A(z) = {mx.text(H)}",
                why="Z{y[n − k]} = z^(−k)·Y(z) con condiciones nulas")
    h = inversa(H, n, trace) if any(Bz) else InversaZ(mx.Num(0), [], "")
    y = None
    if x is not None or iniciales:
        # Y(z) = [B(z)·X(z) + I(z)]/A(z); I(z) = −Σₖ aₖ·Σⱼ₌₁ᵏ y[−j]·z^{j−k}
        I = mx.Num(Fraction(0))
        for k in range(1, K + 1):
            for j in range(1, k + 1):
                if j in (-q for q in iniciales):
                    pass
                yj = iniciales.get(-j, mx.Num(Fraction(0)))
                I = mx.Sub(I, mx.Mul(mx.Mul(Q.num(aq[k]), yj),
                                     mx.Pow(z, mx.Num(Fraction(j - k)))))
        Xz = transformada(x, n, Trace()).X if x is not None else mx.Num(Fraction(0))
        Bpol = LP._q_a_expr(Bz, Z)
        Apol = LP._q_a_expr(Az, Z)
        Y = _bonito(mx.Div(mx.Add(mx.Mul(mx.Div(Bpol, mx.Pow(z, mx.Num(K))), Xz), I),
                           mx.Div(Apol, mx.Pow(z, mx.Num(K)))))
        trace.regla("z.Y", f"Y(z) = [B·X + I]/A = {mx.text(Y)}",
                    why="Z{y[n − k]} = z^(−k)Y(z) + Σ y[−j]·z^(j−k) (unilateral)")
        y = inversa(Y, n, trace)
        _verifica_recurrencia(aq, bq, x, iniciales, y, n, trace)
    _ = AL
    return Diferencias(H, h, y)


def _verifica_recurrencia(aq, bq, x, iniciales, y: InversaZ, n, trace) -> None:
    K = len(aq) - 1
    xe = LP._expande(mx.parse(prepara(x))) if x is not None else None

    def xv(k):
        if xe is None or k < 0:
            return 0.0
        return _valor_x(xe, n, k)
    ys: dict[int, float] = {-j: float(mx.valor_real(v, {})) for j, v in
                            ((-k, v) for k, v in iniciales.items())}
    ys = {k: float(mx.valor_real(v, {})) for k, v in iniciales.items()}
    peor = 0.0
    for k in range(0, 25):
        acc = sum(bq[j] * xv(k - j) for j in range(K + 1))
        acc -= sum(aq[j] * ys.get(k - j, 0.0) for j in range(1, K + 1))
        ys[k] = acc / aq[0]
        peor = max(peor, abs(ys[k] - y.valor(k, n)) / max(1.0, abs(ys[k])))
    if peor > 1e-8:
        raise _error("DISCREPANT", f"y[n] frente a la recurrencia: desviación {peor:.3g}")
    trace.verificacion("z.recurrencia", f"y[0]…y[24] coinciden con la recurrencia iterada "
                       f"(desviación {peor:.2g})", why="la ecuación misma, paso a paso")
