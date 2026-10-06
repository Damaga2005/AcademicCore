# SPDX-License-Identifier: MIT
"""ML-4: series de potencias y métodos numéricos con error y convergencia a la vista.

Completa lo que ya estaba (bisección, Newton, punto fijo, trapecios, Simpson e
interpolación de Lagrange en :mod:`calculo_extra`; convergencia de series numéricas
en :mod:`series_numericas`):

- radio e intervalo de convergencia de Σ cₙ(x − c)^(k·n), con los extremos
  estudiados por los criterios de series numéricas;
- secante y regula falsi; **todas** las raíces en [a, b] (exactas por Sturm si f es
  polinómica; si no, barrido adaptativo + bisección + Newton, también las raíces
  dobles en las que f no cambia de signo);
- Lambert W real (ramas 0 y −1) y a·x·e^(b·x) = c;
- LU con pivoteo parcial exacta (PA = LU comprobado), Jacobi y Gauss-Seidel con el
  radio espectral de la matriz de iteración como criterio;
- interpolación de Newton por diferencias divididas (igual a la de Lagrange);
- ajustes: polinómico exacto, linealizaciones (exponencial, potencial, 1/f),
  Gauss-Newton con diagnóstico y recta minimax discreta;
- EDO y′ = f(t, y): Euler, Heun, RK4, Euler implícito y trapecio, orden observado
  por Richardson, estabilidad absoluta |R(hλ)| < 1 y aviso de rigidez.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def leer(e) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import multiple as MI

    return MI.leer(e)


def _d(e: mx.Expr, v: str) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import multiple as MI

    return MI._limpio(DM.differentiate(e, v))


def _f(e: mx.Expr, env: dict) -> float | None:
    v = mx.valor_real(e, env)
    return None if v is None else float(v)


# ---------------------------------------------------------------------------
# radio e intervalo de convergencia
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Convergencia:
    radio: str                 # «oo», «0» o la expresión exacta
    intervalo: str
    extremos: tuple[str, ...] = ()

    def texto(self) -> str:
        t = f"R = {self.radio}; converge en {self.intervalo}"
        if self.extremos:
            t += " (" + "; ".join(self.extremos) + ")"
        return t


def radio_convergencia(coef: str, x: str = "x", centro="0", k: int = 1, n: str = "n",
                       trace: Trace | None = None) -> Convergencia:
    """Σ cₙ·(x − c)^(k·n): R por el criterio del cociente sobre cₙ (o de la raíz),
    y luego cada extremo como serie numérica."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import series_numericas as SN

    trace = trace if trace is not None else Trace()
    if k < 1:
        raise _error("BAD_INPUT", "k ≥ 1")
    T = SN.leer(coef, n)
    c = leer(centro)
    try:
        q = SN.cociente(T)
        try:
            L = LM.limite(mx.Call("abs", (q,)), n, "oo")
        except (LM.NoSe, ValidationError, UnsupportedError):
            q = _normaliza_n(q, n)
            trace.regla("serie.cociente_normalizado", f"|cₙ₊₁/cₙ| = |{mx.text(q)}|",
                        why="potencias de exponente n agrupadas")
            L = LM.limite(mx.Call("abs", (q,)), n, "oo")
        metodo = "cociente: L = lím |cₙ₊₁/cₙ|"
    except (LM.NoSe, ValidationError, UnsupportedError):
        if T.factoriales:
            raise _no("ni el cociente ni la raíz deciden el radio")
        L = LM.limite(mx.Call("exp", (mx.Div(mx.Call("ln", (mx.Call("abs", (T.expr,)),)),
                                             mx.Sym(n)),)), n, "oo")
        metodo = "raíz: L = lím |cₙ|^(1/n)"
    trace.regla("serie.radio_L", f"{metodo} = {L.texto()}",
                why="Σ cₙ yⁿ converge si L·|y| < 1 y diverge si L·|y| > 1")
    valor = str(L.valor)
    if "∞" in valor or "oo" in valor or L.expr is None:
        Ry = mx.Num(Fraction(0))
    elif mx.exact_value(L.expr) == 0:
        trace.regla("serie.radio", "L = 0 ⇒ R = ∞: converge en toda la recta")
        return Convergencia("oo", "(−∞, +∞)")
    else:
        Ry = MI._limpio(mx.Div(mx.Num(Fraction(1)), L.expr))
    if mx.exact_value(Ry) == 0:
        trace.regla("serie.radio", "L = ∞ ⇒ R = 0: solo converge en el centro")
        return Convergencia("0", f"{{{mx.text(c)}}}")
    R = Ry if k == 1 else MI._limpio(mx.Root(k, Ry))
    trace.regla("serie.radio", f"R = {'1/L' if k == 1 else f'(1/L)^(1/{k})'} = {mx.text(R)}",
                why=f"y = (x − c)^{k}" if k > 1 else "R = 1/L")
    _comprueba_radio(T, n, Ry, trace)
    lo = MI._limpio(mx.Sub(c, R))
    hi = MI._limpio(mx.Add(c, R))
    extremos = []
    cerrado = []
    for nombre, signo in (("izquierdo", -1), ("derecho", 1)):
        # (x − c)^(kn) en x = c ± R vale (±1)^(kn)·Ryⁿ
        cuerpo = _normaliza_n(mx.Mul(T.expr, mx.Pow(Ry, mx.Sym(n))), n)
        if not (signo > 0 or k % 2 == 0):
            cuerpo = mx.Mul(mx.Pow(mx.Neg(mx.Num(Fraction(1))), mx.Sym(n)), cuerpo)
        termino = SN.Termino(cuerpo, T.factoriales, n)
        alterna = not (signo > 0 or k % 2 == 0)
        donde = f"x = {mx.text(lo if signo < 0 else hi)}"
        try:
            v = SN.convergencia(termino, trace=Trace())
            extremos.append(f"{donde}: {v.texto()}")
            cerrado.append(v.converge)
        except (UnsupportedError, ValidationError) as exc:
            abs_term = SN.Termino(_normaliza_n(mx.Mul(T.expr, mx.Pow(Ry, mx.Sym(n))), n),
                                  T.factoriales, n)
            r = _raabe(abs_term, n, alterna, trace)
            if r is None:
                extremos.append(f"{donde}: sin decidir ({exc})")
                cerrado.append(None)
            else:
                extremos.append(f"{donde}: {r[1]}")
                cerrado.append(r[0])
        trace.regla("serie.extremo", extremos[-1],
                    why="en el borde el cociente vale 1 y no decide: se estudia la serie "
                        "numérica que queda")
    izq = "[" if cerrado[0] else "("
    der = "]" if cerrado[1] else ")"
    intervalo = f"{izq}{mx.text(lo)}, {mx.text(hi)}{der}"
    if None in cerrado:
        intervalo += " (algún extremo sin decidir)"
    return Convergencia(mx.text(R), intervalo, tuple(extremos))


def _normaliza_n(e: mx.Expr, n: str) -> mx.Expr:
    """Potencias en n a la vista: b^(n + k) = bⁿ·b^k, factores repetidos arriba y
    abajo se cancelan y Πaᵢⁿ/Πbⱼⁿ = (Πaᵢ/Πbⱼ)ⁿ. Así (n + 1)^(n + 1)/((n + 1)·nⁿ)
    queda ((n + 1)/n)ⁿ y 2ⁿ·(1/2)ⁿ queda 1."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import multiple as MI

    nums, dens = LM._factores(e)

    def parte(fs):
        base_n, otros = [], []
        for f in fs:
            if isinstance(f, mx.Pow) and n in mx.variables(f.exponent):
                k = MI._limpio(mx.Sub(f.exponent, mx.Sym(n)))
                kv = mx.exact_value(k)
                if kv is not None and not mx.variables(k):
                    base_n.append(f.base)
                    if kv != 0:
                        otros.append(mx.Pow(f.base, k))
                    continue
            otros.append(f)
        return base_n, otros
    bn, on = parte(nums)
    bd, od = parte(dens)
    # cancelación textual
    textos_d = [mx.text(MI._limpio(f)) for f in od]
    quedan_n = []
    for f in on:
        t = mx.text(MI._limpio(f))
        if t in textos_d:
            i = textos_d.index(t)
            textos_d[i] = None
            od[i] = None
        else:
            quedan_n.append(f)
    od = [f for f in od if f is not None]
    total = LM._reconstruye(quedan_n, od)
    if bn or bd:
        base = MI._limpio(LM._reconstruye(bn, bd))
        if mx.exact_value(base) != 1 or mx.variables(base):
            total = mx.Mul(total, mx.Pow(base, mx.Sym(n)))
    return MI._limpio(total)


def _raabe(T, n: str, alterna: bool, trace: Trace):
    """Criterio de Raabe para Σ aₙ (aₙ > 0) con aₙ₊₁/aₙ → 1: L = lím n(1 − aₙ₊₁/aₙ).
    L > 1 converge, L < 1 diverge; con signos alternos y L > 0, aₙ decrece a 0
    (aₙ ≈ C·n^(−L)) y Leibniz da la convergencia condicional."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import series_numericas as SN

    try:
        q = _normaliza_n(SN.cociente(T), n)
        L = LM.limite(mx.Mul(mx.Sym(n), mx.Sub(mx.Num(Fraction(1)), q)), n, "oo")
    except (LM.NoSe, ValidationError, UnsupportedError):
        return None
    if L.expr is None:
        return None
    Lv = _f(L.expr, {})
    if Lv is None:
        return None
    Lt = mx.text(MI._limpio(L.expr))
    q_ = Fraction(Lv).limit_denominator(1000)
    if abs(float(q_) - Lv) < 1e-12:
        Lt = str(q_)
    trace.regla("serie.raabe", f"Raabe: lím n(1 − aₙ₊₁/aₙ) = {Lt}",
                why="el cociente tiende a 1 y no decide; Raabe compara con Σ n^(−L)")
    if Lv > 1:
        return True, f"converge absolutamente (Raabe: L = {Lt} > 1)"
    if Lv < 1:
        if alterna and Lv > 0:
            return True, (f"converge condicionalmente (Raabe: L = {Lt} < 1, no "
                          "absolutamente; L > 0 ⇒ |aₙ| decrece a 0: Leibniz)")
        if alterna:
            return False, f"diverge (Raabe: L = {Lt} ≤ 0: |aₙ| no tiende a 0)"
        return False, f"diverge (Raabe: L = {Lt} < 1)"
    return None


def _log_coef(T, n: str, m: int) -> float:
    """ln|cₘ| con cada factorial sustituido por su valor entero exacto (independiente
    del criterio del cociente y de la simplificación)."""
    v = mx.substitute(T.expr, n, mx.Num(Fraction(m)))
    for i, a in enumerate(T.factoriales):
        am = mx.exact_value(mx.substitute(a, n, mx.Num(Fraction(m))))
        if am is None or Fraction(am).denominator != 1 or am < 0:
            raise ValueError
        v = mx.substitute(v, f"F_{i}", mx.Num(Fraction(math.factorial(int(am)))))
    base = _f(v, {})
    if base is None or base == 0 or not math.isfinite(base):
        raise ValueError
    return math.log(abs(base))


def _comprueba_radio(T, n: str, Ry: mx.Expr, trace: Trace) -> None:
    """|cₘ/cₘ₊₁| en m y 2m y extrapolación de Richardson (el cociente se acerca a R
    como R·(1 + c/m + …))."""
    def ratio(m):
        return math.exp(_log_coef(T, n, m) - _log_coef(T, n, m + 1))
    est = None
    for m in (60, 40, 25, 12):
        try:
            r1, r2 = ratio(m), ratio(2 * m)
            est = 2 * r2 - r1
            break
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
    if est is None:
        trace.aviso("serie.radio_num", "sin comprobación numérica del radio (desborda)")
        return
    R = float(mx.valor_real(Ry, {}))
    if abs(est - R) > 0.02 * max(1.0, R):
        raise _error("INTERNAL", f"|cₙ/cₙ₊₁| extrapolado ≈ {est:.6g}, lejos de R = {R:.6g}")
    trace.verificacion("serie.radio_num", f"|cₙ/cₙ₊₁| en n = {m} y {2 * m}, extrapolado: "
                       f"{est:.6g} (R = {R:.6g})",
                       why="cociente con los factoriales como enteros exactos, sin pasar "
                           "por la simplificación ni por el límite")


# ---------------------------------------------------------------------------
# raíces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tabla:
    metodo: str
    cabecera: tuple[str, ...]
    filas: tuple[tuple, ...]
    resultado: object
    nota: str = ""

    def texto(self) -> str:
        r = self.resultado
        rt = (f"{r:.12g}" if isinstance(r, float) else
              ", ".join(f"{v:.12g}" for v in r) if isinstance(r, (list, tuple)) else str(r))
        return f"{self.metodo}: {rt}" + (f"; {self.nota}" if self.nota else "")


def secante(f, var: str, x0: float, x1: float, tol: float = 1e-12, max_it: int = 100) -> Tabla:
    f = leer(f)
    filas = []
    f0, f1 = _f(f, {var: x0}), _f(f, {var: x1})
    for k in range(max_it):
        if f0 is None or f1 is None:
            raise _error("DOMAIN", "f no se evalúa en un iterado")
        if f1 == f0:
            raise _error("DIVERGES", "f(xₙ) = f(xₙ₋₁): la secante es horizontal")
        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
        filas.append((k + 1, x0, x1, f1, x2))
        if abs(x2 - x1) < tol * max(1.0, abs(x2)):
            return Tabla("secante", ("k", "xₙ₋₁", "xₙ", "f(xₙ)", "xₙ₊₁"), tuple(filas), x2,
                         f"{k + 1} iteraciones; orden de convergencia ≈ 1,618 (raíz simple)")
        x0, f0, x1, f1 = x1, f1, x2, _f(f, {var: x2})
    raise _error("DIVERGES", f"la secante no converge en {max_it} iteraciones")


def regula_falsi(f, var: str, a: float, b: float, tol: float = 1e-12,
                 max_it: int = 500) -> Tabla:
    f = leer(f)
    fa, fb = _f(f, {var: a}), _f(f, {var: b})
    if fa is None or fb is None or fa * fb > 0:
        raise _error("HYPOTHESIS", "Bolzano: hace falta f(a)·f(b) < 0")
    filas = []
    c_ant = None
    lado = 0
    for k in range(max_it):
        c = (a * fb - b * fa) / (fb - fa)
        fc = _f(f, {var: c})
        filas.append((k + 1, a, b, c, fc))
        if fc == 0 or (c_ant is not None and abs(c - c_ant) < tol * max(1.0, abs(c))):
            return Tabla("regula falsi (Illinois)", ("k", "a", "b", "c", "f(c)"),
                         tuple(filas), c, f"{k + 1} iteraciones; Illinois evita que un "
                         "extremo se quede fijo")
        if fc * fb < 0:
            a, fa = b, fb
            if lado == -1:
                pass
            lado = -1
        else:
            fa /= 2                     # Illinois
            lado = 1
        b, fb = c, fc
        c_ant = c
    raise _error("DIVERGES", "regula falsi no converge")


@dataclass(frozen=True)
class Raices:
    raices: tuple[tuple[object, float, int], ...]   # (exacta o None, valor, multiplicidad)
    metodo: str
    nota: str

    def texto(self) -> str:
        if not self.raices:
            return f"ninguna raíz en el intervalo ({self.metodo})"
        partes = []
        for ex, v, m in self.raices:
            t = mx.text(ex) if ex is not None else f"≈ {v:.12g}"
            partes.append(t + (f" (multiplicidad {m})" if m > 1 else ""))
        return ", ".join(partes) + f" ({self.metodo}; {self.nota})"


def todas_las_raices(f, var: str, a, b, trace: Trace | None = None) -> Raices:
    """Todas las raíces reales de f en [a, b]."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    f = leer(f)
    fa_, fb_ = float(mx.valor_real(leer(a), {})), float(mx.valor_real(leer(b), {}))
    if not fa_ < fb_:
        raise _error("BAD_INPUT", "hace falta a < b")
    pol = RZ._polinomio_de(f, var)
    if pol is not None and len(RZ._recorta(pol)) > 1:
        ceros = RZ.raices_polinomio(pol)
        out = tuple((r.valor if r.exacta else None, r.x, r.multiplicidad)
                    for r in ceros.raices if fa_ - 1e-12 <= r.x <= fb_ + 1e-12)
        trace.regla("raices.sturm", f"f polinómica: {len(out)} raíces en el intervalo",
                    why="cadena de Sturm: cuenta exacta de raíces reales, nada se escapa")
        return Raices(out, "Sturm (exacto)", "todas, certificadas")
    fc = _compila(f, var)
    dfc = _compila(_d(f, var), var)
    raices: list[float] = []
    N = 4000
    xs = [fa_ + (fb_ - fa_) * i / N for i in range(N + 1)]
    ys = [_seguro(fc, x) for x in xs]
    escala = max([abs(y) for y in ys if y is not None] + [1.0])
    tol_f = 1e-10 * escala
    for i in range(N):
        x0, x1, y0, y1 = xs[i], xs[i + 1], ys[i], ys[i + 1]
        if y0 is None or y1 is None:
            continue
        if y0 == 0:
            raices.append(x0)
            continue
        if y0 * y1 < 0:
            r = _brent(fc, x0, x1, y0, y1)
            yr = _seguro(fc, r)
            if yr is not None and abs(yr) <= 1e-6 * escala:          # descarta polos
                raices.append(r)
        elif dfc is not None:
            # raíz doble: |f| mínimo sin cambio de signo; se mira f′ en la celda y
            # en sus vecinas (el mínimo puede caer en un nodo)
            d0, d1 = _seguro(dfc, x0), _seguro(dfc, x1)
            if d0 is not None and d1 is not None and d0 * d1 < 0:
                c = _brent(dfc, x0, x1, d0, d1)
                yc = _seguro(fc, c)
                if yc is not None and abs(yc) <= tol_f:
                    raices.append(c)
    if ys[-1] == 0:
        raices.append(xs[-1])
    raices = sorted(set(round(r, 13) for r in raices))
    limpias: list[float] = []
    for r in raices:
        if not limpias or abs(r - limpias[-1]) > 1e-9 * max(1.0, abs(r)):
            limpias.append(r)
    out = []
    for r in limpias:
        m = _multiplicidad_num(f, var, r)
        out.append((_exacta(f, var, r), r, m))
    trace.regla("raices.barrido", f"{N} subintervalos: cambios de signo → Brent; mínimos de "
                "|f| con f′ = 0 → raíces dobles", why="Bolzano en cada celda y, donde f no "
                "cambia de signo, una raíz de f′ con f ≈ 0")
    trace.verificacion("raices.residuo", "|f(r)| ≈ 0 en cada raíz: " + ", ".join(
        f"{(_seguro(fc, r) if _seguro(fc, r) is not None else float('nan')):.1e}"
        for _, r, _ in out))
    return Raices(tuple(out), "barrido + Brent",
                  f"celdas de ancho {(fb_ - fa_) / N:.2g}: dos raíces más juntas que eso se "
                  "separan solo si f′ cambia de signo entre ellas")


def _compila(e: mx.Expr, var: str):
    from academic_core.domain.engineering.mathlab import multiple as MI

    c = MI.compilar(e, [var])
    if c is None:
        return lambda x: _f(e, {var: x})
    return lambda x: c([x])


def _seguro(fn, x):
    try:
        v = fn(x)
        if isinstance(v, complex) or v is None or not math.isfinite(v):
            return None
        return v
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None


def _brent(fn, a, b, fa, fb, tol=1e-15):
    """Bisección con interpolación inversa (robusta y rápida)."""
    for _ in range(200):
        m = (a + b) / 2
        c = b - fb * (b - a) / (fb - fa) if fb != fa else m
        if not (min(a, b) < c < max(a, b)):
            c = m
        fc = _seguro(fn, c)
        if fc is None:
            c, fc = m, _seguro(fn, m)
            if fc is None:
                return m
        if fc == 0 or abs(b - a) < tol * max(1.0, abs(c)):
            return c
        if fa * fc < 0:
            b, fb = c, fc
        else:
            a, fa = c, fc
        if abs(b - a) > 0.5 * abs(b - a) and _ % 3 == 2:
            mm = (a + b) / 2
            fm = _seguro(fn, mm)
            if fm is not None:
                if fa * fm < 0:
                    b, fb = mm, fm
                else:
                    a, fa = mm, fm
    return (a + b) / 2


def _multiplicidad_num(f, var, r) -> int:
    m, g = 1, _d(f, var)
    while m < 6:
        v = _f(g, {var: r})
        sig = _f(_d(g, var), {var: r})
        if v is None or abs(v) > 1e-6 * max(1.0, abs(sig) if sig is not None else 1.0):
            return m
        m += 1
        g = _d(g, var)
    return m


def _exacta(f, var, r):
    """Forma exacta si r es racional sencillo o múltiplo racional de π y f se anula
    exactamente ahí (comprobado simbólicamente)."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    cands = []
    q = Fraction(r).limit_denominator(1000)
    if abs(float(q) - r) < 1e-11:
        cands.append(MI.leer(q))
    qp = Fraction(r / math.pi).limit_denominator(48)
    if abs(float(qp) * math.pi - r) < 1e-11 and qp != 0:
        cands.append(MI._limpio(mx.Mul(MI.leer(qp), mx.Const("pi"))))
    for c in cands:
        v = MI._limpio(mx.substitute(f, var, c))
        if mx.exact_value(v) == 0:
            return c
    return None


# ---------------------------------------------------------------------------
# Lambert W
# ---------------------------------------------------------------------------


def lambert_w(a, rama: int = 0, trace: Trace | None = None) -> tuple[object, float]:
    """W_rama(a): la solución w de w·e^w = a (rama 0: w ≥ −1; rama −1: w ≤ −1)."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    trace = trace if trace is not None else Trace()
    ae = leer(a)
    av = float(mx.valor_real(ae, {}))
    lim = -1 / math.e
    if av < lim - 1e-15:
        raise _error("DOMAIN", f"W solo es real para a ≥ −1/e ≈ {lim:.6g}")
    if rama == -1 and not (lim - 1e-15 <= av < 0):
        raise _error("DOMAIN", "la rama −1 existe solo para −1/e ≤ a < 0")
    if rama not in (0, -1):
        raise _error("BAD_INPUT", "rama 0 o −1")
    if abs(av - lim) < 1e-15:
        w = -1.0
    else:
        w = (math.log1p(av) if av > -0.3 else -0.5) if rama == 0 else \
            (math.log(-av) - math.log(-math.log(-av)) if av < -0.25 else -2.0)
        if rama == -1 and av < -0.3:
            w = -1 - math.sqrt(2 * (1 + math.e * av))
        for _ in range(100):                      # Halley
            ew = math.exp(w)
            fw = w * ew - av
            dw = ew * (w + 1)
            if dw == 0:
                break
            nuevo = w - fw / (dw - (w + 2) * fw / (2 * w + 2)) if w != -1 else w
            if abs(nuevo - w) < 1e-16 * max(1.0, abs(w)):
                w = nuevo
                break
            w = nuevo
    if abs(w * math.exp(w) - av) > 1e-12 * max(1.0, abs(av)):
        raise _error("INTERNAL", "w·e^w ≠ a")
    # forma exacta: a = k·e^k con k racional sencillo
    exacto = None
    q = Fraction(w).limit_denominator(100)
    if abs(float(q) - w) < 1e-12:
        cand = MI._limpio(mx.Mul(MI.leer(q), mx.Call("exp", (MI.leer(q),))))
        diff = MI._limpio(mx.Sub(cand, ae))
        dv = _f(diff, {})
        if mx.exact_value(diff) == 0 or (dv is not None and abs(dv) < 1e-15):
            exacto = MI.leer(q)
    trace.regla("lambert.w", f"W_{rama}({mx.text(ae)}) = " +
                (mx.text(exacto) if exacto is not None else f"≈ {w:.15g}"),
                why="Halley sobre w·e^w − a = 0 (convergencia cúbica)")
    trace.verificacion("lambert.comprobacion", f"w·e^w = {w * math.exp(w):.15g} ≈ a")
    return exacto, w


def resolver_x_exp(a, b, c, trace: Trace | None = None) -> list[tuple[object, float]]:
    """a·x·e^(b·x) = c ⇒ x = W(b·c/a)/b (las ramas que existan)."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    trace = trace if trace is not None else Trace()
    ae, be, ce = leer(a), leer(b), leer(c)
    if float(mx.valor_real(ae, {})) == 0 or float(mx.valor_real(be, {})) == 0:
        raise _error("BAD_INPUT", "a y b no nulos")
    arg = MI._limpio(mx.Div(mx.Mul(be, ce), ae))
    trace.regla("lambert.forma", f"a·x·e^(bx) = c ⇔ (bx)·e^(bx) = bc/a = {mx.text(arg)} "
                "⇔ x = W(bc/a)/b")
    out = []
    av = float(mx.valor_real(arg, {}))
    ramas = [0] + ([-1] if -1 / math.e <= av < 0 else [])
    if av < -1 / math.e:
        trace.regla("lambert.sin", "bc/a < −1/e: no hay solución real")
        return []
    for r in ramas:
        ex, w = lambert_w(arg, r, trace)
        x = w / float(mx.valor_real(be, {}))
        xe = MI._limpio(mx.Div(ex, be)) if ex is not None else None
        out.append((xe, x))
    return out


# ---------------------------------------------------------------------------
# sistemas lineales
# ---------------------------------------------------------------------------


def _fr(M):
    return [[Fraction(str(x)) for x in fila] for fila in M]


def lu(A, b=None, trace: Trace | None = None):
    """PA = LU (Doolittle con pivoteo parcial) exacta; con b resuelve Ly = Pb, Ux = y."""
    trace = trace if trace is not None else Trace()
    A = _fr(A)
    n = len(A)
    if any(len(f) != n for f in A):
        raise _error("NOT_SQUARE", "matriz cuadrada")
    U = [list(f) for f in A]
    L = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    perm = list(range(n))
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(U[i][k]))
        if U[p][k] == 0:
            raise _error("SINGULAR", f"columna {k + 1} sin pivote: A singular")
        if p != k:
            U[k], U[p] = U[p], U[k]
            perm[k], perm[p] = perm[p], perm[k]
            for j in range(k):
                L[k][j], L[p][j] = L[p][j], L[k][j]
            trace.regla("lu.pivote", f"F{k + 1} ↔ F{p + 1}", why="pivoteo parcial: el mayor "
                        "en valor absoluto (estabilidad)")
        for i in range(k + 1, n):
            m = U[i][k] / U[k][k]
            L[i][k] = m
            U[i] = [U[i][j] - m * U[k][j] for j in range(n)]
            trace.regla("lu.eliminar", f"l_{i + 1}{k + 1} = {m}; F{i + 1} ← F{i + 1} − {m}·F{k + 1}")
    PA = [A[perm[i]] for i in range(n)]
    LU_ = [[sum(L[i][k] * U[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
    if LU_ != PA:
        raise _error("INTERNAL", "PA ≠ LU")
    trace.verificacion("lu.comprobacion", "PA = LU comprobado exactamente")
    x = None
    if b is not None:
        bb = [Fraction(str(v)) for v in b]
        pb = [bb[perm[i]] for i in range(n)]
        y = []
        for i in range(n):
            y.append(pb[i] - sum(L[i][j] * y[j] for j in range(i)))
        x = [Fraction(0)] * n
        for i in reversed(range(n)):
            x[i] = (y[i] - sum(U[i][j] * x[j] for j in range(i + 1, n))) / U[i][i]
        trace.regla("lu.sustitucion", f"Ly = Pb ⇒ y = ({', '.join(map(str, y))}); "
                    f"Ux = y ⇒ x = ({', '.join(map(str, x))})")
        if any(sum(A[i][j] * x[j] for j in range(n)) != bb[i] for i in range(n)):
            raise _error("INTERNAL", "Ax ≠ b")
        trace.verificacion("lu.ax_b", "Ax = b sustituido")
    return L, U, perm, x


def iterativo(A, b, metodo: str = "jacobi", x0=None, tol: float = 1e-10,
              max_it: int = 1000, trace: Trace | None = None) -> Tabla:
    """Jacobi o Gauss-Seidel con el radio espectral de la matriz de iteración."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    Af = [[float(Fraction(str(v))) for v in f] for f in A]
    bf = [float(Fraction(str(v))) for v in b]
    n = len(Af)
    if any(Af[i][i] == 0 for i in range(n)):
        raise _error("HYPOTHESIS", "un elemento diagonal es 0: reordena las ecuaciones")
    dominante = all(abs(Af[i][i]) > sum(abs(Af[i][j]) for j in range(n) if j != i)
                    for i in range(n))
    # matriz de iteración exacta
    Aq = _fr(A)
    if metodo == "jacobi":
        Bm = [[Fraction(0) if i == j else -Aq[i][j] / Aq[i][i] for j in range(n)]
              for i in range(n)]
    elif metodo == "gauss_seidel":
        # B = −(D + L)⁻¹U
        from academic_core.domain.engineering.mathlab import lineal as LI

        K = LI.cuerpo("Q")
        DL = [[Aq[i][j] if j <= i else Fraction(0) for j in range(n)] for i in range(n)]
        U = [[Aq[i][j] if j > i else Fraction(0) for j in range(n)] for i in range(n)]
        inv = LI.inversa([[K.de(v) for v in f] for f in DL], K)
        Bm = [[-sum(Fraction(inv[i][k]) * U[k][j] for k in range(n)) for j in range(n)]
              for i in range(n)]
    else:
        raise _error("BAD_INPUT", "metodo = jacobi | gauss_seidel")
    rho = max(abs(z) for z in AL.autovalores_numericos(Bm))
    trace.regla("iter.radio", f"radio espectral de la matriz de iteración ρ(B) = {rho:.6g}",
                why="el método converge para todo x₀ si y solo si ρ(B) < 1")
    if dominante:
        trace.regla("iter.dominante", "A es diagonalmente dominante por filas: converge")
    if rho >= 1:
        raise _error("DIVERGES", f"ρ(B) = {rho:.6g} ≥ 1: {metodo} no converge (en general)")
    x = [0.0] * n if x0 is None else [float(v) for v in x0]
    filas = []
    for k in range(max_it):
        nuevo = list(x)
        for i in range(n):
            fuente = nuevo if metodo == "gauss_seidel" else x
            s = sum(Af[i][j] * fuente[j] for j in range(n) if j != i)
            nuevo[i] = (bf[i] - s) / Af[i][i]
        dif = max(abs(a - c) for a, c in zip(nuevo, x))
        filas.append((k + 1, *nuevo, dif))
        x = nuevo
        if dif < tol:
            break
    else:
        raise _error("DIVERGES", "no converge en el máximo de iteraciones")
    res = max(abs(sum(Af[i][j] * x[j] for j in range(n)) - bf[i]) for i in range(n))
    trace.verificacion("iter.residuo", f"‖Ax − b‖∞ = {res:.2e}")
    return Tabla({"jacobi": "Jacobi", "gauss_seidel": "Gauss-Seidel"}[metodo],
                 ("k", *[f"x{i + 1}" for i in range(n)], "‖Δx‖∞"), tuple(filas), x,
                 f"{len(filas)} iteraciones; ρ(B) = {rho:.4g}")


# ---------------------------------------------------------------------------
# interpolación y ajustes
# ---------------------------------------------------------------------------


def newton_divididas(puntos, x: str = "x", trace: Trace | None = None) -> mx.Expr:
    """Polinomio de Newton por diferencias divididas (exacto); igual al de Lagrange."""
    from academic_core.domain.engineering.mathlab import calculo_extra as CX
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import verify as V

    trace = trace if trace is not None else Trace()
    xs = [Fraction(str(p[0])) for p in puntos]
    ys = [Fraction(str(p[1])) for p in puntos]
    if len(set(xs)) != len(xs):
        raise _error("BAD_INPUT", "abscisas repetidas")
    tabla = [list(ys)]
    for k in range(1, len(xs)):
        prev = tabla[-1]
        tabla.append([(prev[i + 1] - prev[i]) / (xs[i + k] - xs[i]) for i in range(len(prev) - 1)])
        trace.regla("newton.dd", f"orden {k}: " + ", ".join(map(str, tabla[-1])))
    coefs = [col[0] for col in tabla]
    P = MI.leer(coefs[0])
    prod: mx.Expr = mx.Num(Fraction(1))
    for k in range(1, len(xs)):
        prod = mx.Mul(prod, mx.Sub(mx.Sym(x), MI.leer(xs[k - 1])))
        P = mx.Add(P, mx.Mul(MI.leer(coefs[k]), prod))
    P = MI._limpio(P)
    trace.regla("newton.polinomio", f"P(x) = {mx.text(P)}",
                why="P = f[x₀] + f[x₀,x₁](x − x₀) + …")
    L = CX.lagrange([(a, b) for a, b in zip(xs, ys)])
    iguales, _, _ = V.check_equivalence(P, L)
    if not iguales:
        raise _error("INTERNAL", "Newton y Lagrange no coinciden")
    trace.verificacion("newton.lagrange", "coincide con el polinomio de Lagrange (unicidad)")
    return P


@dataclass(frozen=True)
class Ajuste:
    modelo: str
    parametros: tuple
    ecm: float
    nota: str = ""
    medida: str = "suma de cuadrados de residuos"

    def texto(self) -> str:
        ps = ", ".join(p if isinstance(p, str) else (str(p) if isinstance(p, Fraction)
                                                     else f"{p:.10g}") for p in self.parametros)
        return f"{self.modelo}: ({ps}); {self.medida} = {self.ecm:.6g}" + \
            (f"; {self.nota}" if self.nota else "")


def ajuste_polinomico(puntos, grado: int, trace: Trace | None = None) -> Ajuste:
    """Mínimos cuadrados exactos por ecuaciones normales (VᵀV)c = Vᵀy."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    xs = [Fraction(str(p[0])) for p in puntos]
    ys = [Fraction(str(p[1])) for p in puntos]
    if len(xs) <= grado:
        raise _error("BAD_INPUT", "hacen falta más puntos que el grado")
    Vm = [[x ** k for k in range(grado + 1)] for x in xs]
    c, r2 = AL.minimos_cuadrados(Vm, ys, trace)
    poly = " + ".join(f"({v})·x^{k}" for k, v in enumerate(c))
    trace.regla("ajuste.polinomio", f"p(x) = {poly}")
    return Ajuste(f"polinomio de grado {grado} (c₀, c₁, …)", tuple(c), float(r2))


def ajuste_linealizado(puntos, modelo: str, trace: Trace | None = None) -> Ajuste:
    """exponencial y = a·e^(bx) (ln y), potencial y = a·x^b (log-log), inversa
    y = 1/(a + b·x) (1/y): recta por mínimos cuadrados en las variables transformadas."""
    trace = trace if trace is not None else Trace()
    xs = [float(Fraction(str(p[0]))) for p in puntos]
    ys = [float(Fraction(str(p[1]))) for p in puntos]
    if modelo == "exponencial":
        if any(y <= 0 for y in ys):
            raise _error("DOMAIN", "ln y exige y > 0")
        X, Y = xs, [math.log(y) for y in ys]
    elif modelo == "potencial":
        if any(y <= 0 for y in ys) or any(x <= 0 for x in xs):
            raise _error("DOMAIN", "log-log exige x > 0 e y > 0")
        X, Y = [math.log(x) for x in xs], [math.log(y) for y in ys]
    elif modelo == "inversa":
        if any(y == 0 for y in ys):
            raise _error("DOMAIN", "1/y exige y ≠ 0")
        X, Y = xs, [1 / y for y in ys]
    else:
        raise _error("BAD_INPUT", "modelo = exponencial | potencial | inversa")
    n = len(X)
    sx, sy = sum(X), sum(Y)
    sxx, sxy = sum(x * x for x in X), sum(x * y for x, y in zip(X, Y))
    den = n * sxx - sx * sx
    if den == 0:
        raise _error("BAD_INPUT", "todas las abscisas transformadas iguales")
    pend = (n * sxy - sx * sy) / den
    corte = (sy - pend * sx) / n
    if modelo == "exponencial":
        a, b = math.exp(corte), pend
        pred = [a * math.exp(b * x) for x in xs]
        forma = "y = a·e^(bx)"
    elif modelo == "potencial":
        a, b = math.exp(corte), pend
        pred = [a * x ** b for x in xs]
        forma = "y = a·x^b"
    else:
        a, b = corte, pend
        pred = [1 / (a + b * x) for x in xs]
        forma = "y = 1/(a + b·x)"
    ssr = sum((p - y) ** 2 for p, y in zip(pred, ys))
    trace.regla("ajuste.linealizado", f"{forma}: recta en las variables transformadas → "
                f"a = {a:.10g}, b = {b:.10g}",
                why="la transformación convierte el modelo en una recta; ojo: minimiza el "
                    "error transformado, no el original (Gauss-Newton lo afina)")
    return Ajuste(forma, (a, b), ssr, "residuos en las variables originales")


def gauss_newton(modelo, parametros: list[str], puntos, inicial: list[float],
                 x: str = "x", max_it: int = 100, trace: Trace | None = None) -> Ajuste:
    """Mínimos cuadrados no lineales: Jᵀ J Δ = −Jᵀ r con paso amortiguado si el
    residuo no baja; se diagnostica la no convergencia."""
    trace = trace if trace is not None else Trace()
    m = leer(modelo)
    dms = [_d(m, p) for p in parametros]
    xs = [float(Fraction(str(q[0]))) for q in puntos]
    ys = [float(Fraction(str(q[1]))) for q in puntos]
    theta = [float(v) for v in inicial]

    def resid(th):
        env = dict(zip(parametros, th))
        out = []
        for xi, yi in zip(xs, ys):
            v = _f(m, {**env, x: xi})
            if v is None:
                return None
            out.append(v - yi)
        return out
    r = resid(theta)
    if r is None:
        raise _error("DOMAIN", "el modelo no se evalúa con los parámetros iniciales")
    ssr = sum(v * v for v in r)
    filas = []
    for it in range(max_it):
        env = dict(zip(parametros, theta))
        J = [[_f(dm, {**env, x: xi}) for dm in dms] for xi in xs]
        if any(v is None for f_ in J for v in f_):
            raise _error("DOMAIN", "la jacobiana no se evalúa")
        k = len(parametros)
        JtJ = [[sum(J[i][a] * J[i][b] for i in range(len(xs))) for b in range(k)] for a in range(k)]
        Jtr = [sum(J[i][a] * r[i] for i in range(len(xs))) for a in range(k)]
        delta = _resuelve_float(JtJ, [-v for v in Jtr])
        if delta is None:
            raise _error("SINGULAR", "JᵀJ singular: parámetros no identificables con estos datos")
        paso = 1.0
        while paso > 1e-8:
            nuevo = [t + paso * d for t, d in zip(theta, delta)]
            rn = resid(nuevo)
            if rn is not None and sum(v * v for v in rn) <= ssr:
                break
            paso /= 2
        else:
            trace.aviso("gn.estancado", "ningún paso reduce el residuo: mínimo local o "
                        "inicio lejano")
            break
        theta, r = nuevo, rn
        nuevo_ssr = sum(v * v for v in r)
        filas.append((it + 1, *theta, nuevo_ssr, paso))
        trace.regla("gn.iteracion", f"it {it + 1}: θ = ({', '.join(f'{t:.8g}' for t in theta)}), "
                    f"SSR = {nuevo_ssr:.6g}, paso {paso:g}")
        if abs(ssr - nuevo_ssr) <= 1e-14 * max(1.0, ssr) and max(abs(d) for d in delta) * paso < 1e-12:
            ssr = nuevo_ssr
            break
        ssr = nuevo_ssr
    else:
        raise _error("DIVERGES", "Gauss-Newton no converge: prueba otro valor inicial "
                                 "(p. ej. el de la linealización)")
    grad = max(abs(sum(J[i][a] * r[i] for i in range(len(xs)))) for a in range(len(parametros)))
    trace.verificacion("gn.gradiente", f"‖Jᵀr‖∞ = {grad:.2e} ≈ 0 en el óptimo")
    return Ajuste(f"{mx.text(m)} con ({', '.join(parametros)})", tuple(theta), ssr,
                  f"{len(filas)} iteraciones")


def _resuelve_float(A, b):
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(M[i][k]))
        if abs(M[p][k]) < 1e-300:
            return None
        M[k], M[p] = M[p], M[k]
        for i in range(k + 1, n):
            f = M[i][k] / M[k][k]
            for j in range(k, n + 1):
                M[i][j] -= f * M[k][j]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def minimax_recta(puntos, trace: Trace | None = None) -> Ajuste:
    """Recta y = a + b·x que minimiza el error máximo (discreto): se alcanza con
    tres puntos que equioscilan (Chebyshev); se prueban todas las ternas, exacto."""
    trace = trace if trace is not None else Trace()
    P = [(Fraction(str(p[0])), Fraction(str(p[1]))) for p in puntos]
    if len(P) < 3:
        raise _error("BAD_INPUT", "al menos tres puntos")
    mejor = None
    for (x1, y1), (x2, y2), (x3, y3) in itertools.combinations(sorted(P), 3):
        if x1 == x3:
            continue
        # y_i − (a + b x_i) = ±h alternando: y1 − a − b x1 = h, y2 − a − b x2 = −h,
        # y3 − a − b x3 = h
        b = (y3 - y1) / (x3 - x1)
        h = ((y1 - b * x1) - (y2 - b * x2)) / 2
        a = y1 - b * x1 - h
        err = max(abs(y - a - b * x) for x, y in P)
        if mejor is None or err < mejor[2]:
            mejor = (a, b, err)
    a, b, err = mejor
    trace.regla("minimax", f"y = {a} + {b}·x con error máximo {err}",
                why="teorema de equioscilación: el error máximo se alcanza con signos "
                    "alternos en tres puntos")
    return Ajuste("minimax y = a + b·x", (a, b), float(err), f"E = {err} exacto",
                  "error máximo")


# ---------------------------------------------------------------------------
# EDO numéricas
# ---------------------------------------------------------------------------


@dataclass
class EDO:
    metodo: str
    t: list[float]
    y: list[float]
    errores: list[float] | None = None
    orden_observado: float | None = None
    estabilidad: str = ""
    notas: list[str] = field(default_factory=list)

    def texto(self) -> str:
        t = f"{self.metodo}: y({self.t[-1]:.6g}) ≈ {self.y[-1]:.12g}"
        if self.errores:
            t += f"; error final {self.errores[-1]:.3g}"
        if self.orden_observado is not None:
            t += f"; orden observado ≈ {self.orden_observado:.2f}"
        if self.estabilidad:
            t += f"; {self.estabilidad}"
        return t


ORDENES = {"euler": 1, "heun": 2, "rk4": 4, "euler_implicito": 1, "trapecio": 2}


def _paso(metodo, f, dfy, t, y, h):
    if metodo == "euler":
        return y + h * f(t, y)
    if metodo == "heun":
        k1 = f(t, y)
        return y + h / 2 * (k1 + f(t + h, y + h * k1))
    if metodo == "rk4":
        k1 = f(t, y)
        k2 = f(t + h / 2, y + h / 2 * k1)
        k3 = f(t + h / 2, y + h / 2 * k2)
        k4 = f(t + h, y + h * k3)
        return y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    # implícitos: Newton sobre g(z) = 0
    z = y + h * f(t, y)
    for _ in range(50):
        if metodo == "euler_implicito":
            g = z - y - h * f(t + h, z)
            dg = 1 - h * dfy(t + h, z)
        else:
            g = z - y - h / 2 * (f(t, y) + f(t + h, z))
            dg = 1 - h / 2 * dfy(t + h, z)
        if dg == 0:
            raise _error("SINGULAR", "Newton del paso implícito con derivada nula")
        dz = g / dg
        z -= dz
        if abs(dz) < 1e-14 * max(1.0, abs(z)):
            break
    return z


def edo(f, t0, y0, h, n: int, metodo: str = "rk4", exacta=None, t: str = "t",
        y: str = "y", trace: Trace | None = None) -> EDO:
    trace = trace if trace is not None else Trace()
    if metodo not in ORDENES:
        raise _error("BAD_INPUT", f"metodo = {', '.join(ORDENES)}")
    fe = leer(f)
    dfe = _d(fe, y)
    from academic_core.domain.engineering.mathlab import multiple as MI

    fc = MI.compilar(fe, [t, y])
    dc = MI.compilar(dfe, [t, y])
    if fc is None or dc is None:
        raise _no("f(t, y) con funciones no compilables")

    def F(tt, yy):
        return fc([tt, yy])

    def DF(tt, yy):
        return dc([tt, yy])
    t0f, y0f, hf = float(Fraction(str(t0))), float(Fraction(str(y0))), float(Fraction(str(h)))

    def integra(hh, pasos):
        ts, ys = [t0f], [y0f]
        for _ in range(pasos):
            ys.append(_paso(metodo, F, DF, ts[-1], ys[-1], hh))
            ts.append(ts[-1] + hh)
            if not math.isfinite(ys[-1]):
                break
        return ts, ys
    try:
        ts, ys = integra(hf, n)
    except OverflowError:
        raise _error("DIVERGES", "la solución numérica explota (inestabilidad)") from None
    res = EDO(metodo, ts, ys)
    trace.regla("edo.metodo", f"{metodo} con h = {hf:g}, {n} pasos (orden teórico "
                f"{ORDENES[metodo]})", why={"euler": "yₙ₊₁ = yₙ + h·f(tₙ, yₙ)",
                                            "heun": "predictor Euler + corrector trapecio",
                                            "rk4": "cuatro pendientes ponderadas 1:2:2:1",
                                            "euler_implicito": "yₙ₊₁ = yₙ + h·f(tₙ₊₁, yₙ₊₁), "
                                            "Newton en cada paso",
                                            "trapecio": "media de las pendientes en tₙ y "
                                            "tₙ₊₁ (implícito)"}[metodo])
    for k in range(0, min(len(ts), 41)):
        trace.regla("edo.paso", f"t = {ts[k]:.6g}: y ≈ {ys[k]:.12g}")
    if exacta is not None:
        ex = leer(exacta)
        errs = [abs(yy - float(mx.valor_real(ex, {t: tt}))) for tt, yy in zip(ts, ys)]
        res.errores = errs
        trace.regla("edo.error", f"error global en t = {ts[-1]:.6g}: {errs[-1]:.3g}",
                    why="comparado con la solución exacta dada")
    # orden observado (Richardson): h, h/2, h/4
    try:
        _, y1 = integra(hf, n)
        _, y2 = integra(hf / 2, 2 * n)
        _, y4 = integra(hf / 4, 4 * n)
        a, b = abs(y1[-1] - y2[-1]), abs(y2[-1] - y4[-1])
        p = math.log2(a / b) if a > 0 and b > 0 else None
        redondeo = 1e-10 * max(1.0, abs(y4[-1]))
        if b < redondeo:
            p = None
            res.notas.append("las diferencias entre h, h/2 y h/4 están al nivel del "
                             "redondeo: el orden no se puede medir así (el método ya es "
                             "exacto a precisión de máquina)")
            trace.regla("edo.orden", res.notas[-1])
        if p is not None and 0.5 <= p <= 8 and all(map(math.isfinite, (y1[-1], y2[-1], y4[-1]))):
            res.orden_observado = p
            trace.regla("edo.orden", f"orden observado log₂(|y_h − y_h/2| / |y_h/2 − y_h/4|) "
                        f"≈ {res.orden_observado:.2f}", why="Richardson: con orden p el "
                        "error se divide por 2^p al dividir h por 2")
    except (OverflowError, ValueError, ValidationError):
        pass
    # estabilidad absoluta si ∂f/∂y es constante (problema lineal y′ = λy + g(t))
    lam = mx.exact_value(dfe) if not mx.variables(dfe) else None
    if lam is not None:
        z = hf * float(lam)
        R = {"euler": 1 + z, "heun": 1 + z + z * z / 2,
             "rk4": 1 + z + z * z / 2 + z ** 3 / 6 + z ** 4 / 24,
             "euler_implicito": 1 / (1 - z) if z != 1 else math.inf,
             "trapecio": (1 + z / 2) / (1 - z / 2) if z != 2 else math.inf}[metodo]
        estable = abs(R) < 1 if float(lam) < 0 else None
        res.estabilidad = (f"hλ = {z:.4g}, |R(hλ)| = {abs(R):.4g}" +
                           ("" if estable is None else (" < 1: estable" if estable else
                                                        " ≥ 1: INESTABLE (reduce h o usa "
                                                        "un método implícito)")))
        trace.regla("edo.estabilidad", res.estabilidad,
                    why="estabilidad absoluta sobre y′ = λy: el método multiplica por R(hλ)")
        if float(lam) < 0 and abs(float(lam)) * (ts[-1] - ts[0]) > 50:
            res.notas.append("problema rígido (|λ|·T grande): los explícitos exigen h muy "
                             "pequeño; los implícitos son incondicionalmente estables")
            trace.aviso("edo.rigido", res.notas[-1])
    return res
