# SPDX-License-Identifier: MIT
"""ML-2: the remaining types of the one-variable course, each with its hypotheses.

- **TFC** (T9): F(x) = ∫_{u(x)}^{v(x)} f(t) dt ⇒ F′(x) = f(v(x))·v′(x) − f(u(x))·u′(x),
  with f's continuity on the range checked; second path: a numerical derivative
  of F (by quadrature) at a point.
- **Inverse function** (T5): (f⁻¹)′(y₀) = 1/f′(x₀) where f(x₀) = y₀, with x₀ found
  exactly when possible, its uniqueness justified by monotony, and f′(x₀) ≠ 0 checked.
- **Piecewise function with parameters** (T4/T5): continuity and differentiability
  at the junction as equations in the parameters, solved exactly (linear → the
  ℚ-linear engine; one parameter → exact roots).
- **Theorems with hypotheses** (T4/T5): Rolle, mean value, Bolzano — each
  hypothesis checked and, when one fails, said with the point where it fails; the
  conclusion's c found.
- **Riemann sums** (T9): left, right, midpoint, trapezoid; the exact integral beside
  them and the rectangles as drawable data.
- **Numerical methods** (T12): bisection, Newton, fixed point (contraction checked),
  composite trapezoid and Simpson with the a-priori error bound (M from Weierstrass),
  Lagrange interpolation (exact rational).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import limite as LM
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _d(e: mx.Expr, var: str) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return LM._limpio(DM.differentiate(e, var))


def _v(e: mx.Expr, env: dict | None = None) -> float | None:
    try:
        r = mx.valor_real(e, env or {})
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    return None if r is None else float(r)


def _simpson(g, a: float, b: float, n: int = 2000) -> float:
    if n % 2:
        n += 1
    h = (b - a) / n
    s = g(a) + g(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * g(a + i * h)
    return s * h / 3


# ---------------------------------------------------------------------------
# TFC
# ---------------------------------------------------------------------------


def tfc(f: mx.Expr, t: str, u: mx.Expr, v: mx.Expr, x: str,
        trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    fv = mx.substitute(f, t, v)
    fu = mx.substitute(f, t, u)
    dv, du = _d(v, x), _d(u, x)
    resultado = LM._limpio(mx.Sub(mx.Mul(fv, dv), mx.Mul(fu, du)))
    trace.hipotesis("tfc.continua", f"f({t}) = {mx.text(f)} continua entre los límites",
                    "se comprueba en el punto de control")
    trace.regla("tfc.regla", f"F′({x}) = f({mx.text(v)})·({mx.text(dv)}) − "
                             f"f({mx.text(u)})·({mx.text(du)}) = {mx.text(resultado)}",
                why="teorema fundamental del cálculo con la regla de la cadena en cada límite")
    return resultado


def tfc_comprobacion(f, t, u, v, x, derivada, x0: float) -> tuple[bool, str]:
    def F(xx):
        a, b = _v(u, {x: xx}), _v(v, {x: xx})
        return _simpson(lambda s: _v(f, {t: s}) or 0.0, a, b)

    h = 1e-4
    numerica = (F(x0 + h) - F(x0 - h)) / (2 * h)
    exacta = _v(derivada, {x: x0})
    ok = exacta is not None and abs(numerica - exacta) < 1e-5 * max(1.0, abs(exacta))
    return ok, f"F′({x0:g}) por diferencias de cuadraturas ≈ {numerica:.8g}"


# ---------------------------------------------------------------------------
# inverse function
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Inversa:
    x0: mx.Expr
    y0: mx.Expr
    derivada: mx.Expr
    justificacion: tuple[str, ...]

    def texto(self) -> str:
        return (f"f({mx.text(self.x0)}) = {mx.text(self.y0)}, así que "
                f"(f⁻¹)′({mx.text(self.y0)}) = 1/f′({mx.text(self.x0)}) = {mx.text(self.derivada)}")


def derivada_inversa(f: mx.Expr, var: str, y0: mx.Expr, trace: Trace | None = None) -> Inversa:
    from academic_core.domain.engineering.mathlab import estudio as ES
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    soluciones = RZ.ceros(mx.Sub(f, y0), var)
    if not soluciones.raices:
        raise _error("NOT_IN_RANGE", f"{mx.text(y0)} no es imagen de ningún punto: f⁻¹ no está "
                                     "definida ahí")
    if len(soluciones.raices) > 1:
        raise _error("NOT_INJECTIVE", f"f no es inyectiva: f(x) = {mx.text(y0)} en "
                                      + ", ".join(r.texto() for r in soluciones.raices))
    r = soluciones.raices[0]
    x0 = r.valor if r.exacta else mx.Num(Fraction(r.x))
    est = ES.estudiar(f, var, Trace())
    justificacion = []
    if not est.decrece or not est.crece:
        justificacion.append("f es estrictamente monótona en cada tramo de su dominio "
                             f"({'creciente' if est.crece else 'decreciente'}): inyectiva")
    else:
        justificacion.append(f"f(x) = {mx.text(y0)} tiene una única solución, x₀ = {r.texto()}; "
                             "f⁻¹ se toma localmente (f no es monótona en todo su dominio)")
    d = _d(f, var)
    dx0 = LM._limpio(mx.substitute(d, var, x0))
    if abs(_v(dx0) or 0) < 1e-14:
        raise _error("HYPOTHESIS", f"f′({mx.text(x0)}) = 0: f⁻¹ no es derivable en {mx.text(y0)} "
                                   "(tangente vertical)")
    justificacion.append(f"f′({mx.text(x0)}) = {mx.text(dx0)} ≠ 0")
    for j in justificacion:
        trace.hipotesis("inversa", j, "se cumple")
    resultado = LM._limpio(mx.Div(mx.Num(Fraction(1)), dx0))
    trace.regla("inversa.derivada", f"(f⁻¹)′({mx.text(y0)}) = 1/f′(x₀) = {mx.text(resultado)}",
                why="derivando f(f⁻¹(y)) = y con la regla de la cadena")
    return Inversa(x0, y0, resultado, tuple(justificacion))


# ---------------------------------------------------------------------------
# piecewise with parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ATrozos:
    condiciones: tuple[str, ...]
    soluciones: tuple[dict, ...]
    texto_solucion: str

    def texto(self) -> str:
        return "; ".join(self.condiciones) + " ⇒ " + self.texto_solucion


def a_trozos(izq: mx.Expr, der: mx.Expr, var: str, c: mx.Expr, parametros: list[str],
             derivable: bool, trace: Trace | None = None) -> ATrozos:
    """f = izq for x < c, der for x ≥ c. Continuity: izq(c⁻) = der(c); differentiability:
    izq′(c⁻) = der′(c⁺) (the one-sided derivatives, as limits of the derivatives, which
    is legitimate when f is continuous at c and the pieces are differentiable)."""
    trace = trace if trace is not None else Trace()
    ecuaciones = [LM._limpio(mx.Sub(mx.substitute(izq, var, c), mx.substitute(der, var, c)))]
    condiciones = [f"continuidad en {mx.text(c)}: {mx.text(ecuaciones[0])} = 0"]
    if derivable:
        e2 = LM._limpio(mx.Sub(mx.substitute(_d(izq, var), var, c),
                               mx.substitute(_d(der, var), var, c)))
        ecuaciones.append(e2)
        condiciones.append(f"derivadas laterales iguales: {mx.text(e2)} = 0")
    for cond in condiciones:
        trace.regla("trozos.condicion", cond,
                    why="f continua en c ⇔ límites laterales = f(c); derivable ⇔ además "
                        "derivadas laterales iguales")
    soluciones = _resuelve(ecuaciones, parametros, trace)
    if not soluciones:
        texto = "ningún valor de los parámetros lo cumple"
    else:
        texto = " o ".join("{" + ", ".join(f"{k} = {mx.text(v)}" for k, v in s.items()) + "}"
                           for s in soluciones)
    return ATrozos(tuple(condiciones), tuple(soluciones), texto)


def _resuelve(ecuaciones: list[mx.Expr], parametros: list[str], trace: Trace) -> list[dict]:
    from academic_core.domain.engineering.mathlab import lineal as L
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    ecuaciones = [e for e in ecuaciones if not (mx.exact_value(e) == 0)]
    # linear in all parameters?
    filas, b = [], []
    lineal = True
    for e in ecuaciones:
        try:
            p = P.as_poly(e)
        except Exception:  # noqa: BLE001
            lineal = False
            break
        fila = [Fraction(0)] * len(parametros)
        const = Fraction(0)
        for mono, coef in p.items():
            d = dict(mono)
            if not d:
                const = Fraction(coef)
            elif len(d) == 1 and list(d.values())[0] == 1 and list(d)[0] in parametros:
                fila[parametros.index(list(d)[0])] = Fraction(coef)
            else:
                lineal = False
        if not lineal:
            break
        filas.append(fila)
        b.append(-const)
    if lineal and filas:
        Q = L.cuerpo("Q")
        sistema = L.resolver_sistema(filas, b, Q, trace)
        if sistema.particular is None:
            return []
        if sistema.nucleo:
            raise UnsupportedError("UNSUPPORTED: infinitas soluciones: " + sistema.texto(Q))
        return [{p: (mx.Num(v) if v >= 0 else mx.Neg(mx.Num(-v)))
                 for p, v in zip(parametros, sistema.particular)}]
    if len(parametros) == 1:
        a = parametros[0]
        candidatos = None
        for e in ecuaciones:
            r = RZ.ceros(e, a)
            vals = {round(z.x, 10): z for z in r.raices}
            candidatos = vals if candidatos is None else {k: v for k, v in candidatos.items()
                                                          if k in vals}
        return [{a: z.valor if z.exacta else mx.Num(Fraction(z.x))}
                for z in (candidatos or {}).values()]
    raise UnsupportedError("UNSUPPORTED: sistema no lineal en varios parámetros")


# ---------------------------------------------------------------------------
# theorems
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Teorema:
    nombre: str
    hipotesis: tuple[tuple[str, bool, str], ...]
    conclusion: str

    @property
    def aplica(self) -> bool:
        return all(ok for _, ok, _ in self.hipotesis)

    def texto(self) -> str:
        h = "; ".join(f"{n}: {'sí' if ok else 'NO'}{(' — ' + d) if d else ''}"
                      for n, ok, d in self.hipotesis)
        return f"{self.nombre}: {h}. " + (self.conclusion if self.aplica else
                                           "No se puede aplicar.")


def _continua_en(f, var, a: float, b: float, cerrado: bool = True) -> tuple[bool, str]:
    from academic_core.domain.engineering.mathlab import estudio as ES

    dom = ES.dominio(f, var)
    for t in dom.tramos:
        ok_a = t.a is None or t.a.x < a or (t.cerrado_a and abs(t.a.x - a) < 1e-12) or (
            not cerrado and abs(t.a.x - a) < 1e-12)
        ok_b = t.b is None or t.b.x > b or (t.cerrado_b and abs(t.b.x - b) < 1e-12) or (
            not cerrado and abs(t.b.x - b) < 1e-12)
        if ok_a and ok_b:
            return True, ""
    malos = list(dict.fromkeys([ES._texto_punto(t.a) for t in dom.tramos if t.a] +
                               [ES._texto_punto(t.b) for t in dom.tramos if t.b]))
    return False, "f no está definida (o salta) en el intervalo" + (
        f": borde del dominio en {', '.join(malos)}" if malos else "")


def _derivable_en(f, var, a: float, b: float) -> tuple[bool, str]:
    from academic_core.domain.engineering.mathlab import estudio as ES
    from academic_core.domain.engineering.mathlab import raices as RZ

    d = _d(f, var)
    for g in ES._fronteras(d) + [x for x in _abs_args(f)]:
        if not mx.depends(g, var):
            continue
        for r in RZ.ceros(g, var, (a, b)).raices:
            if a < r.x < b:
                izq = _v(d, {var: r.x - 1e-7})
                der = _v(d, {var: r.x + 1e-7})
                if izq is None or der is None or abs(izq - der) > 1e-4 * max(1, abs(izq)):
                    return False, f"f no es derivable en {var} = {r.texto()}"
    return True, ""


def _abs_args(e: mx.Expr) -> list[mx.Expr]:
    from academic_core.domain.engineering.mathlab import raices as RZ

    return RZ._troceables(e, "x") if mx.variables(e) else []


def rolle(f, var, a: mx.Expr, b: mx.Expr, trace: Trace | None = None, valor_medio: bool = False
          ) -> Teorema:
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    xa, xb = _v(a), _v(b)
    cont, dc = _continua_en(f, var, xa, xb)
    der, dd = _derivable_en(f, var, xa, xb)
    fa, fb = LM._limpio(mx.substitute(f, var, a)), LM._limpio(mx.substitute(f, var, b))
    hipotesis = [(f"f continua en [{mx.text(a)}, {mx.text(b)}]", cont, dc),
                 (f"f derivable en ({mx.text(a)}, {mx.text(b)})", der, dd)]
    if valor_medio:
        pendiente = LM._limpio(mx.Div(mx.Sub(fb, fa), mx.Sub(b, a)))
        objetivo = mx.Sub(_d(f, var), pendiente)
        nombre = "Teorema del valor medio (Lagrange)"
        enunciado = f"existe c con f′(c) = (f(b) − f(a))/(b − a) = {mx.text(pendiente)}"
    else:
        iguales = cont and abs((_v(fa) or 0) - (_v(fb) or 0)) < 1e-12
        hipotesis.append((f"f({mx.text(a)}) = f({mx.text(b)})", iguales,
                          f"f(a) = {mx.text(fa)}, f(b) = {mx.text(fb)}"))
        objetivo = _d(f, var)
        nombre = "Teorema de Rolle"
        enunciado = "existe c con f′(c) = 0"
    for n, ok, dd2 in hipotesis:
        trace.hipotesis(f"{nombre}.{n}", n + (f" ({dd2})" if dd2 else ""),
                        "se cumple" if ok else "NO se cumple")
    conclusion = ""
    if all(ok for _, ok, _ in hipotesis):
        cs = [r for r in RZ.ceros(objetivo, var, (xa, xb)).raices if xa < r.x < xb]
        conclusion = enunciado + ": c = " + (", ".join(r.texto() for r in cs) or "—")
    return Teorema(nombre, tuple(hipotesis), conclusion)


def bolzano(f, var, a: mx.Expr, b: mx.Expr, trace: Trace | None = None) -> Teorema:
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    xa, xb = _v(a), _v(b)
    cont, dc = _continua_en(f, var, xa, xb)
    fa, fb = _v(f, {var: xa}), _v(f, {var: xb})
    signo = fa is not None and fb is not None and fa * fb < 0
    hipotesis = ((f"f continua en [{mx.text(a)}, {mx.text(b)}]", cont, dc),
                 ("f(a)·f(b) < 0", bool(signo), f"f(a) ≈ {fa:.6g}, f(b) ≈ {fb:.6g}"
                  if fa is not None and fb is not None else ""))
    conclusion = ""
    if cont and signo:
        cs = [r for r in RZ.ceros(f, var, (xa, xb)).raices if xa < r.x < xb]
        conclusion = "existe c en (a, b) con f(c) = 0: c = " + ", ".join(r.texto() for r in cs)
    return Teorema("Teorema de Bolzano", hipotesis, conclusion)


# ---------------------------------------------------------------------------
# Riemann and numerical methods
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Riemann:
    n: int
    sumas: dict
    exacta: mx.Expr | None
    rectangulos: tuple[tuple[float, float, float], ...]   # (x_left, x_right, height) midpoint

    def texto(self) -> str:
        partes = [f"{k}: {v:.10g}" for k, v in self.sumas.items()]
        if self.exacta is not None:
            partes.append(f"integral exacta {mx.text(self.exacta)} ≈ "
                          f"{float(mx.valor_real(self.exacta, {})):.10g}")
        return f"n = {self.n}; " + "; ".join(partes)


def riemann(f, var, a: mx.Expr, b: mx.Expr, n: int) -> Riemann:
    import academic_core.domain.engineering.mathlab as ML

    if not 1 <= n <= 100000:
        raise _error("BAD_INPUT", "n entre 1 y 100000")
    xa, xb = _v(a), _v(b)
    h = (xb - xa) / n
    val = lambda x: _v(f, {var: x})        # noqa: E731
    izq = sum(val(xa + i * h) for i in range(n)) * h
    der = sum(val(xa + (i + 1) * h) for i in range(n)) * h
    medio = sum(val(xa + (i + 0.5) * h) for i in range(n)) * h
    trap = (izq + der) / 2
    rect = tuple((xa + i * h, xa + (i + 1) * h, val(xa + (i + 0.5) * h)) for i in range(min(n, 200)))
    exacta = None
    try:
        r = ML.calcular(ML.Peticion("integrar", {"integrando": f, "var": var,
                                                 "desde": mx.text(a), "hasta": mx.text(b)}))
        if r.sello.verdict == "verificado" and isinstance(r.exacto_expr, mx.Expr):
            exacta = r.exacto_expr
    except Exception:  # noqa: BLE001
        pass
    return Riemann(n, {"izquierda": izq, "derecha": der, "punto medio": medio, "trapecio": trap},
                   exacta, rect)


@dataclass(frozen=True)
class Iteraciones:
    metodo: str
    filas: tuple[tuple, ...]
    resultado: float
    cota: float | None
    nota: str = ""

    def texto(self) -> str:
        base = f"{self.metodo}: ≈ {self.resultado:.12g}"
        if self.cota is not None:
            base += f" (error ≤ {self.cota:.3g})"
        return base + (f"; {self.nota}" if self.nota else "")


def biseccion(f, var, a: float, b: float, tol: float = 1e-8, max_it: int = 200) -> Iteraciones:
    fa, fb = _v(f, {var: a}), _v(f, {var: b})
    if fa is None or fb is None or fa * fb > 0:
        raise _error("HYPOTHESIS", "Bolzano: hace falta f(a)·f(b) < 0")
    filas = []
    for k in range(max_it):
        m = (a + b) / 2
        fm = _v(f, {var: m})
        filas.append((k + 1, a, b, m, fm))
        if fm == 0 or (b - a) / 2 < tol:
            break
        if (fm < 0) == (fa < 0):
            a, fa = m, fm
        else:
            b = m
    n_teorico = math.ceil(math.log2((filas[0][2] - filas[0][1]) / tol)) if tol > 0 else None
    return Iteraciones("bisección", tuple(filas), filas[-1][3], (b - a) / 2,
                       f"{len(filas)} iteraciones (cota a priori: n ≥ log₂((b − a)/tol) = "
                       f"{n_teorico})")


def newton(f, var, x0: float, tol: float = 1e-12, max_it: int = 50) -> Iteraciones:
    d = _d(f, var)
    x, filas = x0, []
    for k in range(max_it):
        fx, dx = _v(f, {var: x}), _v(d, {var: x})
        if fx is None or dx is None or dx == 0:
            raise _error("DIVERGES", f"Newton se detiene en x = {x:g}: f′(x) = 0 o fuera del dominio")
        nuevo = x - fx / dx
        filas.append((k + 1, x, fx, dx, nuevo))
        if abs(nuevo - x) < tol * max(1.0, abs(nuevo)):
            x = nuevo
            break
        x = nuevo
    else:
        raise _error("DIVERGES", f"Newton no converge en {max_it} iteraciones desde {x0:g}")
    return Iteraciones("Newton", tuple(filas), x, None,
                       f"{len(filas)} iteraciones; último paso |xₙ₊₁ − xₙ| = "
                       f"{abs(filas[-1][4] - filas[-1][1]):.2g} (estimación del error, no cota: "
                       "convergencia cuadrática cerca de una raíz simple)")


def punto_fijo(g, var, x0: float, a: float, b: float, tol: float = 1e-10,
               max_it: int = 500) -> Iteraciones:
    """Contraction on [a, b] checked: g([a, b]) ⊂ [a, b] and L = max |g′| < 1."""
    from academic_core.domain.engineering.mathlab import estudio as ES

    r = ES.extremos_absolutos(g, var, mx.Num(Fraction(a)), mx.Num(Fraction(b)))
    gmin, gmax = _v(r.minimo[0]), _v(r.maximo[0])
    if gmin < a - 1e-12 or gmax > b + 1e-12:
        raise _error("HYPOTHESIS", f"g([a, b]) = [{gmin:.6g}, {gmax:.6g}] no está contenido en "
                                   f"[{a:g}, {b:g}]")
    dg = _d(g, var)
    rd = ES.extremos_absolutos(dg, var, mx.Num(Fraction(a)), mx.Num(Fraction(b)))
    L = max(abs(_v(rd.maximo[0])), abs(_v(rd.minimo[0])))
    if L >= 1:
        raise _error("HYPOTHESIS", f"max |g′| = {L:.6g} ≥ 1 en [{a:g}, {b:g}]: no es contractiva")
    x, filas = x0, []
    for k in range(max_it):
        nuevo = _v(g, {var: x})
        filas.append((k + 1, x, nuevo))
        if abs(nuevo - x) < tol:
            x = nuevo
            break
        x = nuevo
    cota = L / (1 - L) * abs(filas[-1][2] - filas[-1][1])
    return Iteraciones("punto fijo", tuple(filas), x, cota,
                       f"contractiva con L = {L:.4g} < 1: error ≤ L/(1 − L)·|xₙ − xₙ₋₁|")


def cuadratura(f, var, a: mx.Expr, b: mx.Expr, n: int, metodo: str) -> Iteraciones:
    from academic_core.domain.engineering.mathlab import estudio as ES

    xa, xb = _v(a), _v(b)
    if metodo == "simpson" and n % 2:
        raise _error("BAD_INPUT", "Simpson necesita n par")
    h = (xb - xa) / n
    ys = [_v(f, {var: xa + i * h}) for i in range(n + 1)]
    if any(y is None for y in ys):
        raise _error("HYPOTHESIS", "f no está definida en algún nodo")
    if metodo == "trapecios":
        valor = h * (ys[0] / 2 + sum(ys[1:-1]) + ys[-1] / 2)
        orden, k, fac = 2, 2, 12
    else:
        valor = h / 3 * (ys[0] + ys[-1] + 4 * sum(ys[1:-1:2]) + 2 * sum(ys[2:-1:2]))
        orden, k, fac = 4, 4, 180
    deriv = f
    for _ in range(k):
        deriv = _d(deriv, var)
    try:
        r = ES.extremos_absolutos(deriv, var, a, b)
        M = max(abs(_v(r.maximo[0])), abs(_v(r.minimo[0])))
        cota = (xb - xa) * h ** orden * M / fac
        nota = f"cota a priori (b − a)·h^{orden}·M/{fac} con M = máx |f^({k})| = {M:.6g}"
    except Exception:  # noqa: BLE001
        cota, nota = None, "sin cota: no se pudo acotar la derivada"
    return Iteraciones(metodo, tuple((i, xa + i * h, y) for i, y in enumerate(ys)), valor, cota, nota)


def lagrange(puntos: list[tuple]) -> mx.Expr:
    """The interpolating polynomial through (xᵢ, yᵢ), exactly over ℚ."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    xs = [Fraction(str(x)) for x, _ in puntos]
    ys = [Fraction(str(y)) for _, y in puntos]
    if len(set(xs)) != len(xs):
        raise _error("BAD_INPUT", "abscisas repetidas")
    coefs = [Fraction(0)] * len(xs)
    for i, (xi, yi) in enumerate(zip(xs, ys)):
        base = [Fraction(1)]
        den = Fraction(1)
        for j, xj in enumerate(xs):
            if j == i:
                continue
            base = [Fraction(0)] + base
            for k in range(len(base) - 1):
                base[k] -= xj * base[k + 1]
            den *= xi - xj
        for k, c in enumerate(base):
            coefs[k] += yi * c / den
    total: mx.Expr | None = None
    x = mx.Sym("x")
    for k in range(len(coefs) - 1, -1, -1):
        c = coefs[k]
        if c == 0:
            continue
        pot = mx.Num(Fraction(1)) if k == 0 else (x if k == 1 else mx.Pow(x, mx.Num(Fraction(k))))
        t = mx.Num(abs(c)) if k == 0 else (pot if abs(c) == 1 else mx.Mul(mx.Num(abs(c)), pot))
        if total is None:
            total = t if c > 0 else mx.Neg(t)
        else:
            total = mx.Add(total, t) if c > 0 else mx.Sub(total, t)
    del RZ
    return total if total is not None else mx.Num(Fraction(0))


# ---------------------------------------------------------------------------
# applications of the definite integral (T9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Aplicacion:
    tipo: str
    planteamiento: str
    exacto: mx.Expr | None
    aproximado: float

    def texto(self) -> str:
        valor = (f"{mx.text(self.exacto)} ≈ {self.aproximado:.10g}" if self.exacto is not None
                 else f"≈ {self.aproximado:.10g} (sin primitiva elemental)")
        return f"{self.tipo}: {self.planteamiento} = {valor}"


def _definida(f: mx.Expr, var: str, a: mx.Expr, b: mx.Expr) -> tuple[mx.Expr | None, float]:
    import academic_core.domain.engineering.mathlab as ML

    xa, xb = _v(a), _v(b)

    def seguro(x: float) -> float:
        # at a removable point (x/(2√x) at 0) step a hair inside the interval
        v = _v(f, {var: x})
        if v is None:
            paso = 1e-10 * max(1.0, abs(x))
            v = _v(f, {var: x + paso if x <= (xa + xb) / 2 else x - paso})
        return v or 0.0

    numerico = _simpson(seguro, xa, xb, 4000)
    try:
        r = ML.calcular(ML.Peticion("integrar", {"integrando": f, "var": var,
                                                 "desde": mx.text(a), "hasta": mx.text(b)}))
        if isinstance(r.exacto_expr, mx.Expr) and r.sello.verdict != "discrepa":
            return r.exacto_expr, numerico
    except Exception:  # noqa: BLE001
        pass
    # √(quadratic): the trigonometric/hyperbolic substitution, then Barrow
    from academic_core.domain.engineering.mathlab import primitivas as PR

    try:
        F = PR.sustitucion_trigonometrica(f, var)
        valor = LM._limpio(mx.Sub(mx.substitute(F, var, b), mx.substitute(F, var, a)))
        if _v(valor) is not None:
            return valor, numerico
    except Exception:  # noqa: BLE001
        pass
    return None, numerico


def area_entre(f: mx.Expr, g: mx.Expr, var: str, a: mx.Expr, b: mx.Expr,
               trace: Trace | None = None) -> Aplicacion:
    """∫ₐᵇ |f − g|: cut at the crossings, each piece with its sign."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    h = LM._limpio(mx.Sub(f, g))
    xa, xb = _v(a), _v(b)
    cortes = [r for r in RZ.ceros(h, var, (xa, xb)).raices if xa < r.x < xb]
    bordes = [a] + [r.valor if r.exacta else mx.Num(Fraction(r.x)) for r in cortes] + [b]
    total: mx.Expr = mx.Num(Fraction(0))
    exacto, aprox, partes = True, 0.0, []
    for lo, hi in zip(bordes, bordes[1:]):
        medio = (_v(lo) + _v(hi)) / 2
        signo = 1 if (_v(h, {var: medio}) or 0) >= 0 else -1
        pieza = h if signo > 0 else LM._limpio(mx.Neg(h))
        partes.append(f"∫_{mx.text(lo)}^{mx.text(hi)} ({mx.text(pieza)})")
        e, n = _definida(pieza, var, lo, hi)
        aprox += n
        if e is None:
            exacto = False
        else:
            total = mx.Add(total, e)
    trace.regla("area.cortes", "cortes de las curvas en " + (", ".join(r.texto() for r in cortes)
                                                            or "ninguno dentro del intervalo"),
                why="el área es ∫|f − g|: en cada tramo entre cortes el signo de f − g es fijo")
    return Aplicacion("área", " + ".join(partes), LM._limpio(total) if exacto else None, aprox)


def volumen_revolucion(f: mx.Expr, var: str, a: mx.Expr, b: mx.Expr, eje: str = "x",
                       trace: Trace | None = None) -> Aplicacion:
    trace = trace if trace is not None else Trace()
    if eje == "x":
        integrando = LM._limpio(mx.Mul(mx.Const("pi"), mx.Pow(f, mx.Num(Fraction(2)))))
        plan = f"π·∫_{mx.text(a)}^{mx.text(b)} ({mx.text(f)})² d{var} (discos)"
    else:
        if (_v(a) or 0) < 0:
            raise _error("BAD_INPUT", "por capas alrededor del eje Y hace falta a ≥ 0")
        integrando = LM._limpio(mx.Mul(mx.Mul(mx.Num(Fraction(2)), mx.Const("pi")),
                                       mx.Mul(mx.Sym(var), f)))
        plan = f"2π·∫_{mx.text(a)}^{mx.text(b)} {var}·({mx.text(f)}) d{var} (capas cilíndricas)"
    trace.regla("volumen.formula", plan, why="discos de radio f(x) o capas de radio x y altura f(x)")
    e, n = _definida(integrando, var, a, b)
    return Aplicacion("volumen", plan, e, n)


def longitud_arco(f: mx.Expr, var: str, a: mx.Expr, b: mx.Expr,
                  trace: Trace | None = None) -> Aplicacion:
    trace = trace if trace is not None else Trace()
    d = _d(f, var)
    integrando = LM._limpio(mx.Root(2, mx.Add(mx.Num(Fraction(1)), mx.Pow(d, mx.Num(Fraction(2))))))
    plan = f"∫_{mx.text(a)}^{mx.text(b)} √(1 + ({mx.text(d)})²) d{var}"
    trace.regla("arco.formula", plan, why="L = ∫ √(1 + f′²): longitud de la poligonal en el límite")
    e, n = _definida(integrando, var, a, b)
    return Aplicacion("longitud de arco", plan, e, n)
