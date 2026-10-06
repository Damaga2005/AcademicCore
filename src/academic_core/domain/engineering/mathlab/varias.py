# SPDX-License-Identifier: MIT
"""ML-5: cálculo en varias variables exacto donde es exacto.

Límites por caminos (la no existencia por dos caminos distintos ES una prueba;
la coincidencia en N caminos es un indicio, y se dice), derivada direccional,
jacobiana, regla de la cadena con equivalencia exacta, función implícita con
la identidad Fx + Fy·y′ = 0, Hessiana con Sylvester (y Descartes sobre el característico para la
silla en n > 2), puntos críticos y Lagrange también no lineales (bases de
Gröbner en :mod:`sistemas`), Taylor de grado 2 sin cota inventada y extremos
en rectángulos por Weierstrass (interior + 4 lados 1V + esquinas).

Cada resultado lleva traza con «por qué» y un segundo camino independiente;
lo que no sale exacto se rechaza con su motivo (§5.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _num(q) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import limite as LM

    return LM._num(q)


def _a_num(valor) -> mx.Expr:
    """int/Fraction/str/expr → expresión exacta."""
    from academic_core.domain.engineering.mathlab import limite as LM

    if isinstance(valor, mx.Expr):
        return valor
    if isinstance(valor, Fraction):
        return LM._num(valor)
    if isinstance(valor, int):
        return LM._num(Fraction(valor))
    return mx.parse(str(valor))


def _a_frac(valor, que: str) -> Fraction:
    """int/Fraction/float/str numérico/expr exacta → Fraction; si no, BAD_INPUT."""
    if isinstance(valor, Fraction):
        return valor
    if isinstance(valor, int):
        return Fraction(valor)
    if isinstance(valor, float):
        return Fraction(valor)
    if isinstance(valor, str):
        try:
            return Fraction(valor)
        except (ValueError, ZeroDivisionError) as exc:
            raise _error("BAD_INPUT", f"«{valor}» no es un número para {que}") from None
    if isinstance(valor, mx.Expr):
        v = mx.exact_value(valor)
        if v is None:
            raise _error("BAD_INPUT", f"«{mx.text(valor)}» no es un número exacto para {que}")
        return Fraction(v)
    raise _error("BAD_INPUT", f"«{valor}» no es un número para {que}")


def _eval_exacta(e: mx.Expr, punto: dict[str, mx.Expr]):
    """Sustituir y plegar a número exacto; None si no es exacto."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import trig as T

    v = e
    for nombre, val in punto.items():
        v = mx.substitute(v, nombre, _a_num(val))
    v = LM._limpio(T.simplify(v))
    return mx.exact_value(v)


# ---------------------------------------------------------------------------
# linealidad en varias variables (para gradientes y Lagrange lineales)
# ---------------------------------------------------------------------------


def _d(f: mx.Expr, v: str, trace: Trace | None = None) -> mx.Expr:
    """Parcial plegada a forma presentable (2·x, no 2·x¹+0)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import limite as LM

    from academic_core.domain.engineering.mathlab import multiple as MI

    return MI._bonito(LM._limpio(DM.differentiate(f, v, trace)))


def _es_cero_racional(e: mx.Expr) -> bool:
    """0 idéntico como función racional en alguna variable libre."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        if P.is_zero(P.as_poly(e)):
            return True
    except Exception:  # noqa: BLE001 - no es polinómica: se intenta racional
        pass
    for var in sorted(mx.variables(e)):
        try:
            razon = P.as_ratio(e, var)
        except Exception:  # noqa: BLE001
            razon = None
        if razon is not None and P.is_zero(razon.numerator):
            return True
    return False


def _prelin(e: mx.Expr) -> mx.Expr:
    """Div(a, c) con c constante exacta → a·(1/c), para que el polinomio lo vea."""
    if isinstance(e, mx.Div):
        c = mx.exact_value(e.right)
        if c is not None and c != 0 and not mx.variables(e.right):
            return mx.Mul(_prelin(e.left), mx.Num(Fraction(1) / Fraction(c)))
        return mx.Div(_prelin(e.left), _prelin(e.right))
    if isinstance(e, mx.Mul):
        return mx.Mul(_prelin(e.left), _prelin(e.right))
    if isinstance(e, (mx.Add, mx.Sub)):
        return type(e)(_prelin(e.left), _prelin(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_prelin(e.arg))
    return e


def _lin(e: mx.Expr, incognitas: set[str]) -> tuple[dict[str, Fraction], Fraction] | None:
    """e = Σ cᵢ·uᵢ + c₀ por forma normal de polinomio; None si no es lineal exacta."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(_prelin(e))
    except Exception:  # noqa: BLE001 - no polinómica: no lineal
        return None
    out: dict[str, Fraction] = {}
    const = Fraction(0)
    for mono, c in p.items():
        d = dict(mono)
        try:
            coef = Fraction(c)
        except (TypeError, ValueError, ArithmeticError):
            return None
        if set(d) - incognitas:
            return None
        grado = sum(d.values())
        if grado == 0:
            const += coef
        elif grado == 1:
            u = next(k for k, v in d.items() if v)
            if d[u] != 1:
                return None
            out[u] = out.get(u, Fraction(0)) + coef
        else:
            return None
    return out, const


# ---------------------------------------------------------------------------
# límites direccionales
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Direccionales:
    existe: bool | None  # False probado; None = indicio a favor; True nunca por caminos
    caminos: tuple[tuple[str, str], ...]

    def texto(self) -> str:
        if self.existe is False:
            vals = "; ".join(f"{c}: {v}" for c, v in self.caminos)
            return f"no existe: {vals}"
        if not self.caminos:
            return ("ningún camino decidido: no se concluye nada "
                    "(todas las sustituciones quedaron sin límite exacto)")
        comun = self.caminos[0][1]
        return (f"límite {comun} en todos los caminos probados "
                f"({len(self.caminos)}): indicio, no prueba de existencia; "
                "un camino no probado podría dar otro valor (§5.4)")


_CAMINOS = [("y = 0", "recta"), ("x = 0", "recta"),
            ("y = x", "recta"), ("y = -x", "recta"),
            ("y = 2*x", "recta"), ("y = x/2", "recta"),
            ("y = x^2", "parábola"), ("y = -x^2", "parábola")]


def limites_direccionales(f: mx.Expr, vars: list[str], punto: dict,
                          trace: Trace | None = None) -> Direccionales:
    """Límite por rectas y parábolas con el motor 1V exacto."""
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    if len(vars) != 2:
        raise _no("caminos solo en dos variables")
    x, y = vars
    ux, uy = f"u_{x}", f"u_{y}"
    F = mx.substitute(mx.substitute(f, x, mx.Add(mx.Sym(ux), _a_num(punto[x]))),
                      y, mx.Add(mx.Sym(uy), _a_num(punto[y])))
    trace.metodo("mv.limites_caminos", "rectas y parábolas por el punto, con el motor 1V",
                 why="si dos caminos dan distinto valor, el límite no existe (probado); "
                     "si coinciden, es solo un indicio")
    resultados: list[tuple[str, str]] = []
    for nombre, _ in _CAMINOS:
        expr = _camino(F, ux, uy, nombre)
        var = ux if mx.depends(expr, ux) else uy
        try:
            r = LM.limite(expr, var, "0")
        except Exception as exc:  # noqa: BLE001 - camino no decidido: no cuenta
            trace.regla("mv.camino", f"{nombre}: no decidido ({str(exc)[:60]})")
            continue
        veredictos = [LM.comprobacion_numerica(expr, var, "0", s, r) for s in (1, -1)]
        detalle = "; ".join(d for _, d in veredictos)
        trace.regla("mv.camino", f"{nombre}: {r.texto()} ({detalle})")
        if not all(ok for ok, _ in veredictos) and r.expr is not None:
            trace.aviso("mv.camino_num", f"{nombre}: el segundo camino no confirma")
            continue
        resultados.append((nombre, r.texto()))
    valores: dict[str, list] = {}
    for c, v in resultados:
        valores.setdefault(v, []).append(c)
    if len(valores) > 1:
        return Direccionales(False, tuple(resultados))
    return Direccionales(None, tuple(resultados))


def _camino(F: mx.Expr, ux: str, uy: str, nombre: str) -> mx.Expr:
    X, Y = mx.Sym(ux), mx.Sym(uy)
    if nombre == "y = 0":
        return mx.substitute(F, uy, mx.Num(Fraction(0)))
    if nombre == "x = 0":
        return mx.substitute(F, ux, mx.Num(Fraction(0)))
    rectas = {"y = x": Fraction(1), "y = -x": Fraction(-1), "y = 2*x": Fraction(2),
              "y = x/2": Fraction(1, 2)}
    if nombre in rectas:
        m = rectas[nombre]
        return mx.substitute(F, uy, mx.Mul(_num(m), X))
    if nombre == "y = x^2":
        return mx.substitute(F, uy, mx.Pow(X, mx.Num(Fraction(2))))
    if nombre == "y = -x^2":
        return mx.substitute(F, uy, mx.Neg(mx.Pow(X, mx.Num(Fraction(2)))))
    raise _error("BAD_INPUT", f"camino desconocido «{nombre}»")


# ---------------------------------------------------------------------------
# derivada direccional, jacobiana, cadena, implícita
# ---------------------------------------------------------------------------


def derivada_direccional(f: mx.Expr, vars: list[str], punto: dict, direccion: list,
                         trace: Trace | None = None):
    """∇f(p)·û con û unitario exacto; comprobada por diferencias finitas."""
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    grad = [_d(f, v, trace) for v in vars]
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    pesos = [_a_frac(d, "la dirección") for d in direccion]
    if len(pesos) != len(vars):
        raise _error("BAD_INPUT", "la dirección tiene que tener tantas componentes "
                                  f"como variables ({len(vars)})")
    n2 = sum(d * d for d in pesos)
    if n2 <= 0:
        raise _error("BAD_INPUT", "la dirección no puede ser el vector nulo")
    import math as _math

    # componentes del unitario exactas: d_i/√n2, con √n2 exacta si es cuadrado
    num_ok = _math.isqrt(n2.numerator) ** 2 == n2.numerator
    den_ok = _math.isqrt(n2.denominator) ** 2 == n2.denominator
    if num_ok and den_ok:
        inv_norma: mx.Expr = _num(Fraction(1, Fraction(
            _math.isqrt(n2.numerator), _math.isqrt(n2.denominator))))
    else:
        inv_norma = mx.Div(mx.Num(Fraction(1)), mx.Root(2, _num(n2)))
    total: mx.Expr = mx.Num(Fraction(0))
    penv = {v: punto[v] for v in vars}
    for g, v, d in zip(grad, vars, pesos):
        gv = _eval_exacta(g, penv)
        if gv is None:
            raise _no(f"∂f/∂{v} no es exacta en el punto")
        total = mx.Add(total, mx.Mul(_num(Fraction(gv) * d), inv_norma))
    total = LM._limpio(total)
    trace.regla("mv.direccional", f"D_u f = ∇f·û = {mx.text(total)}",
                why="derivada direccional: producto escalar con el unitario")
    _verifica_direccional(f, vars, punto, pesos, total, trace)
    v = mx.exact_value(total)
    return Fraction(v) if v is not None else total


def _verifica_direccional(f, vars, punto, pesos, total, trace) -> None:
    n2 = math.sqrt(sum(float(d) ** 2 for d in pesos))
    u = [float(d) / n2 for d in pesos]
    p = {}
    for v in vars:
        w = mx.valor_real(_a_num(punto[v]), {})
        if w is None:
            trace.verificacion("mv.direccional_num", "punto no evaluable numéricamente")
            return
        p[v] = float(w)
    h = 1e-6
    try:
        a = mx.valor_real(f, {v: p[v] + h * u[i] for i, v in enumerate(vars)})
        b = mx.valor_real(f, {v: p[v] - h * u[i] for i, v in enumerate(vars)})
        e = mx.valor_real(total, {})
    except (OverflowError, ValueError, ZeroDivisionError):
        a = b = e = None
    if None in (a, b, e):
        trace.verificacion("mv.direccional_num", "no evaluable numéricamente")
        return
    d = (a - b) / (2 * h)
    if abs(d - e) > 1e-4 * max(1.0, abs(e)):
        raise _error("DISCREPANT", f"diferencias finitas {d:.6g} ≠ {e:.6g}")
    trace.verificacion("mv.direccional_num", f"diferencias centradas ≈ {d:.10g}")


def jacobiana(fs: list[mx.Expr], vars: list[str],
              trace: Trace | None = None) -> list[list[mx.Expr]]:
    """Matriz de parciales con cada entrada derivada con pasos."""

    trace = trace if trace is not None else Trace()
    if not fs:
        raise _error("BAD_INPUT", "se necesita al menos una función")
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    J = [[_d(f, v, trace) for v in vars] for f in fs]
    trace.regla("mv.jacobiana", f"matriz {len(fs)}×{len(vars)} de derivadas parciales",
                why="cada fila es el gradiente de una componente")
    _verifica_jacobiana(fs, vars, J, trace)
    return J


def _verifica_jacobiana(fs, vars, J, trace) -> None:
    from academic_core.domain.engineering.mathlab import verify as V

    puntos = V.sampled_points(sorted(set(vars)), count=6)
    malos = 0
    for p in puntos:
        h = 1e-6
        for i, f in enumerate(fs):
            for j, v in enumerate(vars):
                try:
                    a = mx.valor_real(J[i][j], p)
                    f1 = mx.valor_real(f, {**p, v: p[v] + h})
                    f0 = mx.valor_real(f, {**p, v: p[v] - h})
                except (OverflowError, ValueError, ZeroDivisionError):
                    continue
                if None in (a, f1, f0):
                    continue
                if abs(a - (f1 - f0) / (2 * h)) > 1e-4 * max(1.0, abs(a)):
                    malos += 1
    if malos:
        raise _error("DISCREPANT", f"{malos} parciales no coinciden por diferencias")
    trace.verificacion("mv.jacobiana_num", "parciales frente a diferencias centradas")


def cadena(f: mx.Expr, sustituciones: dict[str, mx.Expr], t: str,
            trace: Trace | None = None) -> mx.Expr:
    """d/dt f(x(t)) = Σ ∂f/∂xᵢ·dxᵢ/dt, verificada contra derivar lo sustituido."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import verify as V

    trace = trace if trace is not None else Trace()
    total: mx.Expr = mx.Num(Fraction(0))
    for var, xt in sustituciones.items():
        parcial = _d(f, var, trace)
        en_curva = parcial
        for w, xw in sustituciones.items():
            en_curva = mx.substitute(en_curva, w, xw)
        dx = _d(xt, t)
        total = mx.Add(total, mx.Mul(en_curva, dx))
        trace.regla("mv.cadena_termino", f"∂f/∂{var}|curva·d{var}/dt",
                    why="cada variable intermedia aporta su eslabón evaluado en la curva")
    compuesta = f
    for var, xt in sustituciones.items():
        compuesta = mx.substitute(compuesta, var, xt)
    directa = _d(compuesta, t)
    total = LM._limpio(total)
    iguales, _, _ = V.check_equivalence(total, directa)
    if not iguales:
        raise _error("INTERNAL", "la cadena no coincide con derivar lo sustituido")
    trace.verificacion("mv.cadena_equiv", "cadena = derivada de la compuesta (exacto)")
    return total


def implicita(F: mx.Expr, x: str, y: str, trace: Trace | None = None) -> mx.Expr:
    """y′ = −Fx/Fy con Fy ≠ 0 comprobado; identidad Fx + Fy·y′ = 0 exacta."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import verify as V

    trace = trace if trace is not None else Trace()
    Fx, Fy = _d(F, x, trace), _d(F, y, trace)
    if LM._identico_cero(Fy):
        raise _error("HYPOTHESIS", "Fy es idénticamente 0: no hay función implícita")
    trace.hipotesis("implicita.fy", "Fy ≠ 0 en el punto",
                    "se cumple si el punto no anula Fy (se comprueba al evaluar)")
    yp = LM._limpio(mx.Div(mx.Neg(Fx), Fy))
    trace.regla("mv.implicita", f"y′ = −Fx/Fy = {mx.text(yp)}",
                why="derivar F(x, y(x)) = 0 y despejar y′")
    resto = LM._limpio(mx.Add(Fx, mx.Mul(Fy, yp)))
    if not _es_cero_racional(resto):
        raise _error("INTERNAL", "Fx + Fy·y′ no se anula idénticamente")
    trace.verificacion("mv.implicita_id", "Fx + Fy·y′ = 0 idéntico")
    return yp


# ---------------------------------------------------------------------------
# Hessiana, Sylvester, puntos críticos, Taylor-2
# ---------------------------------------------------------------------------


def hessiana(f: mx.Expr, vars: list[str], punto: dict | None = None,
             trace: Trace | None = None) -> tuple[list[list[mx.Expr]], str]:
    """Hessiana exacta y clase por Sylvester (2×2 completa; n > 2 solo definida)."""

    trace = trace if trace is not None else Trace()
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    H = [[_d(_d(f, a), b) for b in vars] for a in vars]
    trace.regla("mv.hessiana", "matriz de segundas derivadas (Schwarz: simétrica)",
                why="el orden de derivación no importa con parciales continuas")
    from academic_core.domain.engineering.mathlab import verify as V

    for i in range(len(vars)):
        for j in range(i + 1, len(vars)):
            iguales, _, _ = V.check_equivalence(H[i][j], H[j][i])
            if not iguales:
                raise _error("INTERNAL", "Hessiana no simétrica (Schwarz falla)")
    trace.verificacion("mv.hessiana_sim", "Hxy = Hyx exacta (Schwarz)")
    if punto is None and any(mx.exact_value(h) is None for fila in H for h in fila):
        raise _no("la Hessiana depende del punto: el criterio de segundo orden no "
                  "decide sin evaluar en el punto crítico")
    M = [[_eval_exacta(h, punto or {}) if punto else mx.exact_value(h) for h in fila]
         for fila in H]
    if any(v is None for fila in M for v in fila):
        raise _no("la Hessiana no es exacta en el punto")
    M = [[Fraction(v) for v in fila] for fila in M]
    donde = (" en (" + ", ".join(str(punto[v]) for v in vars) + ")") if punto else ""
    menores = _menores(M)
    trace.regla("mv.hessiana_valor",
                f"H{donde} = [" + "; ".join(", ".join(str(x) for x in fila) for fila in M) + "]; "
                + ", ".join(f"Δ{k + 1} = {d}" for k, d in enumerate(menores)),
                why="menores principales de la esquina superior izquierda")
    try:
        clase = _sylvester(M)
    except UnsupportedError:
        trace.regla("mv.sylvester", "el criterio de segundo orden no decide",
                    why="algún menor es nulo y no hay autovalores de signos opuestos")
        raise
    trace.regla("mv.sylvester", f"menores principales → {clase}",
                why={"mínimo": "todos los Δk > 0: definida positiva",
                     "máximo": "Δk alternan empezando por Δ1 < 0: definida negativa"}.get(
                    clase, "hay autovalores de los dos signos: indefinida"))
    return H, clase


def _menores(M: list[list[Fraction]]) -> list[Fraction]:
    from academic_core.domain.engineering.mathlab import lineal as L

    K = L.cuerpo("Q")
    return [Fraction(L.determinante([[K.de(M[i][j]) for j in range(k)] for i in range(k)], K))
            for k in range(1, len(M) + 1)]


def _sylvester(M: list[list[Fraction]]) -> str:
    from academic_core.domain.engineering.mathlab import lineal as L

    n = len(M)
    K = L.cuerpo("Q")
    menores = []
    for k in range(1, n + 1):
        menores.append(L.determinante([[K.de(M[i][j]) for j in range(k)] for i in range(k)], K))
    if all(d > 0 for d in menores):
        return "mínimo"
    if all(((-1) ** (k + 1)) * menores[k] > 0 for k in range(n)):
        return "máximo"
    if n == 2 and menores[1] < 0:
        return "punto de silla"
    if n == 2 and menores[1] == 0:
        raise _no("menor principal nulo (semidefinida): el criterio de segundo orden "
                  "no decide")
    if n == 2:
        raise _no("Hessiana indefinida no silla en 2×2: caso imposible (error interno)")
    # n > 2: H simétrica tiene todos sus autovalores reales, así que la regla de
    # Descartes sobre det(λI − H) cuenta exactamente los positivos y los negativos
    pos, neg = _signos_autovalores(M)
    if pos and neg:
        return "punto de silla"
    raise _no("Hessiana semidefinida (autovalor nulo): el criterio de segundo orden "
              "no decide")


def _signos_autovalores(M: list[list[Fraction]]) -> tuple[int, int]:
    from academic_core.domain.engineering.mathlab import algebra as AL

    c = AL.polinomio_caracteristico(M)
    while c and c[0] == 0:
        c = c[1:]

    def cambios(seq):
        s = [x for x in seq if x != 0]
        return sum(1 for a, b in zip(s, s[1:]) if (a > 0) != (b > 0))
    pos = cambios(c)
    neg = cambios([x * (-1) ** k for k, x in enumerate(c)])
    return pos, neg


def _coord(z):
    """Valor de :mod:`sistemas` → Fraction si es racional, expresión si es exacto
    irracional, float si solo se conoce numérico."""
    q = z.fraccion
    if q is not None:
        return q
    return z.expr if z.exacto else z.x


def texto_coord(c) -> str:
    if isinstance(c, Fraction):
        return str(c)
    if isinstance(c, float):
        return f"≈ {c:.10g}"
    return mx.text(c)


def _float(c) -> float:
    if isinstance(c, (Fraction, float, int)):
        return float(c)
    return float(mx.valor_real(c, {}))


def _clasifica(f: mx.Expr, vars: list[str], punto: tuple, trace: Trace) -> str:
    if all(isinstance(c, Fraction) for c in punto):
        try:
            return hessiana(f, vars, dict(zip(vars, punto)), trace)[1]
        except UnsupportedError:
            return "sin clasificar (segundo orden no decide)"
    # coordenadas irracionales o numéricas: la Hessiana se evalúa en coma flotante
    env = {v: _float(c) for v, c in zip(vars, punto)}
    H = [[float(mx.valor_real(_d(_d(f, a), b), env)) for b in vars] for a in vars]
    n = len(vars)
    escala = max(1.0, max(abs(h) for fila in H for h in fila))
    menores = [_det_float([fila[:k] for fila in H[:k]]) for k in range(1, n + 1)]
    tol = 1e-9 * escala ** n
    trace.regla("mv.hessiana_valor",
                "H en (" + ", ".join(texto_coord(c) for c in punto) + ") ≈ [" + "; ".join(
                    ", ".join(f"{x:.6g}" for x in fila) for fila in H) + "]; " + ", ".join(
                    f"Δ{k + 1} ≈ {d:.6g}" for k, d in enumerate(menores)),
                why="coordenadas con raíces: la Hessiana se evalúa en coma flotante")
    if abs(menores[-1]) <= tol:
        return "sin clasificar (Hessiana casi singular en coma flotante)"
    if any(abs(d) <= tol for d in menores):
        clase = "punto de silla"     # no singular y no definida ⇒ indefinida
    elif all(d > 0 for d in menores):
        clase = "mínimo"
    elif all(((-1) ** (k + 1)) * menores[k] > 0 for k in range(n)):
        clase = "máximo"
    else:
        clase = "punto de silla"
    trace.regla("mv.sylvester_num", f"Hessiana evaluada en coma flotante → {clase}",
                why="punto con coordenadas irracionales: signo de menores con margen")
    return clase


def _det_float(M: list[list[float]]) -> float:
    M = [list(f) for f in M]
    n, det = len(M), 1.0
    for k in range(n):
        piv = max(range(k, n), key=lambda i: abs(M[i][k]))
        if M[piv][k] == 0:
            return 0.0
        if piv != k:
            M[k], M[piv] = M[piv], M[k]
            det = -det
        det *= M[k][k]
        for i in range(k + 1, n):
            r = M[i][k] / M[k][k]
            for j in range(k, n):
                M[i][j] -= r * M[k][j]
    return det


def puntos_criticos(f: mx.Expr, vars: list[str],
                    trace: Trace | None = None) -> list[tuple[tuple, str]]:
    """Todos los puntos críticos aislados (∇f = 0, también no lineal) y su clase
    por la Hessiana; coordenadas exactas (racionales o con √) o numéricas."""
    from academic_core.domain.engineering.mathlab import sistemas as S

    trace = trace if trace is not None else Trace()
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    grad = [_d(f, v, trace) for v in vars]
    trace.regla("mv.sistema", "∇f = 0: " + "; ".join(
        f"∂f/∂{v} = {mx.text(g)} = 0" for v, g in zip(vars, grad)),
        why="un extremo interior de una función diferenciable anula el gradiente")
    trace.metodo("mv.criticos", "el sistema se resuelve por bases de Gröbner",
                 why="eliminación exacta: no se pierde ninguna solución ni se inventa")
    sols = S.resolver(grad, list(vars), trace)
    if not sols:
        trace.regla("mv.criticos", "∇f = 0 no tiene solución real: sin puntos críticos")
        return []
    out = []
    for s in sols:
        punto = tuple(_coord(s[v]) for v in vars)
        clase = _clasifica(f, vars, punto, trace)
        trace.regla("mv.criticos", f"({', '.join(texto_coord(c) for c in punto)}): {clase}")
        out.append((punto, clase))
    return out


def taylor2(f: mx.Expr, vars: list[str], centro: dict[str, mx.Expr],
            trace: Trace | None = None) -> mx.Expr:
    """P₂ = f(a) + ∇f·h + ½hᵀHh exacto; sin cota inventada (se dice)."""
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    faltan = [v for v in vars if v not in centro]
    if faltan:
        raise _error("BAD_INPUT", f"falta el centro de {', '.join(faltan)}")
    a = {v: centro[v] for v in vars}
    f0 = _eval_exacta(f, a)
    if f0 is None:
        raise _no("f no es exacta en el centro")
    h = {v: LM._limpio(mx.Sub(mx.Sym(v), _a_num(a[v]))) for v in vars}
    P: mx.Expr = _num(Fraction(f0))
    for v in vars:
        g = _eval_exacta(_d(f, v), a)
        if g is None:
            raise _no(f"∂f/∂{v} no es exacta en el centro")
        P = mx.Add(P, mx.Mul(_num(Fraction(g)), h[v]))
    for i, vi in enumerate(vars):
        for j, vj in enumerate(vars):
            hij = _eval_exacta(_d(_d(f, vi), vj), a)
            if hij is None:
                raise _no("la Hessiana no es exacta en el centro")
            # ½hᵀHh sumando sobre todos los pares (la simetría ya cuenta 2)
            P = mx.Add(P, mx.Mul(_num(Fraction(hij) / 2), mx.Mul(h[vi], h[vj])))
    P = LM._limpio(P)
    trace.regla("mv.taylor2", f"P₂ = {mx.text(P)}",
                why="Taylor de grado 2: constante, lineal con el gradiente y "
                    "cuadrática con la Hessiana")
    trace.hipotesis("mv.taylor2_cota", "sin cota de error declarada",
                    "haría falta acotar las terceras derivadas en un disco (§5.4)")
    _verifica_taylor2(f, vars, a, P, trace)
    return P


def _verifica_taylor2(f, vars, a, P, trace) -> None:
    base = {}
    for v in vars:
        w = mx.valor_real(_a_num(a[v]), {})
        base[v] = float(w) + 0.1 if w is not None else 0.1
    cerca = base
    try:
        real = mx.valor_real(f, cerca)
        aprox = mx.valor_real(P, cerca)
    except (OverflowError, ValueError, ZeroDivisionError):
        real = aprox = None
    if None in (real, aprox):
        trace.verificacion("mv.taylor2_num", "no evaluable cerca del centro")
        return
    trace.verificacion("mv.taylor2_num",
                       f"|f − P₂| = {abs(real - aprox):.3g} a distancia 0,1 del centro")


# ---------------------------------------------------------------------------
# Lagrange y extremos en recintos
# ---------------------------------------------------------------------------


def lagrange(f: mx.Expr, g, vars: list[str],
             trace: Trace | None = None) -> list[tuple[tuple, object]]:
    """∇f = Σλᵢ∇gᵢ, gᵢ = 0 (una o varias ligaduras); todos los candidatos aislados
    con el valor de f en cada uno (exacto si las coordenadas lo son)."""
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import sistemas as S

    trace = trace if trace is not None else Trace()
    if not vars:
        raise _error("BAD_INPUT", "se necesita al menos una variable")
    gs = list(g) if isinstance(g, (list, tuple)) else [g]
    if not gs or len(gs) >= len(vars):
        raise _error("BAD_INPUT", "hacen falta entre 1 y n − 1 ligaduras")
    lams = []
    for k in range(len(gs)):
        nombre = "lam" + ("" if len(gs) == 1 else str(k + 1))
        while nombre in vars:
            nombre += "_"
        lams.append(nombre)
    ecuaciones = []
    for v in vars:
        e = _d(f, v, trace)
        for lam, gi in zip(lams, gs):
            e = mx.Sub(e, mx.Mul(mx.Sym(lam), _d(gi, v)))
        ecuaciones.append(MI._bonito(MI._canon(LM._limpio(e))))
    ecuaciones.extend(gs)
    trace.regla("mv.sistema", "L = f − " + " − ".join(f"{l}·({mx.text(gi)})"
                                                     for l, gi in zip(lams, gs)) +
                "; ∇L = 0: " + "; ".join(f"{mx.text(e)} = 0" for e in ecuaciones),
                why="en un extremo condicionado regular ∇f es combinación de los ∇gᵢ")
    trace.metodo("mv.lagrange", "∇f = Σλᵢ∇gᵢ más las ligaduras, por bases de Gröbner",
                 why="los extremos condicionados regulares anulan el gradiente del "
                     "lagrangiano")
    try:
        sols = S.resolver(ecuaciones, list(vars) + lams, trace)
    except UnsupportedError as exc:
        c = _constante_en_ligadura(f, gs, vars)
        if c is None:
            raise
        trace.regla("mv.lagrange_constante", f"f vale {texto_coord(c)} en toda la ligadura",
                    why="los candidatos no están aislados porque f es constante sobre la "
                        "ligadura: todo punto es a la vez máximo y mínimo condicionado")
        raise _no(f"f es constante (= {texto_coord(c)}) sobre la ligadura: todos sus "
                  "puntos son extremos, no hay candidatos aislados") from exc
    _avisa_singulares(gs, vars, trace)
    out = []
    for s in sols:
        punto = tuple(_coord(s[v]) for v in vars)
        valor = _valor_f(f, vars, punto)
        trace.regla("mv.lagrange", f"({', '.join(texto_coord(c) for c in punto)}): "
                                   f"f = {texto_coord(valor)}")
        out.append((punto, valor))
    if not out:
        trace.regla("mv.lagrange", "sistema sin solución real: sin candidatos")
        return out
    vmax = max(out, key=lambda c: _float(c[1]))
    vmin = min(out, key=lambda c: _float(c[1]))
    acotada = len(vars) in (2, 3) and len(gs) == 1 and _es_acotada(gs[0], vars)
    trace.regla("mv.lagrange_resumen",
                f"mayor valor {texto_coord(vmax[1])} en ({', '.join(texto_coord(c) for c in vmax[0])}); "
                f"menor {texto_coord(vmin[1])} en ({', '.join(texto_coord(c) for c in vmin[0])})",
                why=("la ligadura es compacta (Weierstrass): son el máximo y el mínimo absolutos"
                     " (más los puntos singulares avisados, si los hay)") if acotada else
                    "comparación de candidatos; sin compacidad comprobada no se afirma que "
                    "sean extremos absolutos")
    return out


def _es_acotada(g, vars) -> bool:
    try:
        _acotada(g, vars, Trace())
        return True
    except (UnsupportedError, ValidationError):
        return False


def _constante_en_ligadura(f, gs, vars):
    """Valor de f si es el mismo en muchos puntos de la ligadura (una ligadura
    polinómica en 2 o 3 variables: se fijan todas menos la primera en una rejilla y
    se resuelve en ella)."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    if len(gs) != 1 or len(vars) not in (2, 3):
        return None
    x, resto = vars[0], vars[1:]
    valores = []
    rejilla = [Fraction(k, 7) for k in range(-20, 21)]
    combos = ([(a,) for a in rejilla] if len(resto) == 1 else
              [(a, b) for a in rejilla[::3] for b in rejilla[::3]])
    for combo in combos:
        h = gs[0]
        for v, c in zip(resto, combo):
            h = mx.substitute(h, v, _num(c))
        coefs = RZ._polinomio_de(h, x)
        if coefs is None or len(RZ._recorta(coefs)) < 2:
            continue
        for r in RZ.raices_polinomio(coefs).raices:
            v = mx.valor_real(f, {x: r.x, **{u: float(c) for u, c in zip(resto, combo)}})
            if v is not None:
                valores.append(float(v))
    if len(valores) < 4 or max(valores) - min(valores) > 1e-9 * max(1.0, abs(valores[0])):
        return None
    q = Fraction(valores[0]).limit_denominator(10 ** 6)
    return q if abs(float(q) - valores[0]) < 1e-12 else valores[0]


def _valor_f(f: mx.Expr, vars: list[str], punto: tuple):
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import trig as T

    if all(isinstance(c, Fraction) for c in punto):
        v = _eval_exacta(f, dict(zip(vars, punto)))
        if v is not None:
            return Fraction(v)
    if all(not isinstance(c, float) for c in punto):
        e = f
        for v, c in zip(vars, punto):
            e = mx.substitute(e, v, _a_num(c))
        e = LM._limpio(T.simplify(e))
        q = mx.exact_value(e)
        return Fraction(q) if q is not None else e
    return float(mx.valor_real(f, {v: _float(c) for v, c in zip(vars, punto)}))


def _avisa_singulares(gs, vars, trace) -> None:
    """Lagrange exige ∇g ≠ 0 (o rango completo) en la ligadura: se comprueba si hay
    puntos de la ligadura donde falla, que serían candidatos extra."""
    from academic_core.domain.engineering.mathlab import sistemas as S

    if len(gs) != 1:
        trace.hipotesis("mv.lagrange_regular", "rango completo de la jacobiana de las "
                        "ligaduras", "no comprobado con varias ligaduras")
        return
    try:
        sing = S.resolver([gs[0]] + [_d(gs[0], v) for v in vars], list(vars), Trace())
    except UnsupportedError:
        sing = None
    if sing:
        trace.aviso("mv.lagrange_singular", "la ligadura tiene puntos con ∇g = 0: " + "; ".join(
            "(" + ", ".join(texto_coord(_coord(s[v])) for v in vars) + ")" for s in sing) +
            " — son candidatos que Lagrange no ve; evalúa f en ellos")
    else:
        trace.verificacion("mv.lagrange_regular", "∇g ≠ 0 en toda la ligadura"
                           if sing == [] else "regularidad de la ligadura no decidida")


@dataclass(frozen=True)
class Recinto:
    minimo: tuple[str, object]
    maximo: tuple[str, object]

    def texto(self) -> str:
        return (f"mínimo {texto_coord(self.minimo[1])} en {self.minimo[0]}; "
                f"máximo {texto_coord(self.maximo[1])} en {self.maximo[0]}")


def extremos_recinto(f: mx.Expr, vars: list[str], recinto: tuple,
                      trace: Trace | None = None) -> Recinto:
    """Weierstrass en un rectángulo: interior (críticos) + 4 lados 1V + esquinas."""
    from academic_core.domain.engineering.mathlab import estudio as ES
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    if isinstance(recinto, (tuple, list)) and len(recinto) == 2 and recinto[0] == "region":
        return _extremos_region(f, vars, recinto[1], trace)
    if (not isinstance(recinto, (tuple, list)) or len(recinto) != 5
            or recinto[0] != "rectangulo"):
        raise _no("recintos: ['rectangulo', a, b, c, d] o ['region', g] con g ≤ 0 "
                  "compacto (disco, elipse…)")
    if len(vars) != 2:
        raise _no(f"el rectángulo es 2D: llegaron {len(vars)} variables")
    _, sa, sb, sc, sd = recinto
    for nombre, lo, hi in (("x", sa, sb), ("y", sc, sd)):
        try:
            flo, fhi = float(mx.valor_real(mx.parse(str(lo)), {})), float(
                mx.valor_real(mx.parse(str(hi)), {}))
        except (OverflowError, ValueError, ZeroDivisionError):
            flo = fhi = None
        if flo is None or fhi is None or not flo < fhi:
            raise _error("BAD_INPUT", f"el intervalo de {nombre} tiene que cumplir a < b "
                                      f"con extremos numéricos (llegó {lo}, {hi})")
    x, y = vars
    trace.hipotesis("weierstrass_mv", "f continua en el rectángulo cerrado",
                    "se comprueba lado a lado (cada lado 1V exige su tramo) y en el "
                    "interior f es diferenciable donde existe el gradiente")
    candidatos: list[tuple[str, Fraction | mx.Expr, float]] = []
    caja = [(float(mx.valor_real(mx.parse(str(sa)), {})), float(mx.valor_real(mx.parse(str(sb)), {}))),
            (float(mx.valor_real(mx.parse(str(sc)), {})), float(mx.valor_real(mx.parse(str(sd)), {})))]

    def dentro_rect(p):
        return _dentro(p[0], sa, sb) and _dentro(p[1], sc, sd)
    candidatos.extend(_criticos_interiores(f, vars, dentro_rect, caja, trace))
    lados = [(x, sa, sb, sc), (x, sa, sb, sd)]
    for var, ia, ib, val in lados:
        g = mx.substitute(f, y, mx.parse(str(val)))
        edge = _extremos_lado(g, var, ia, ib, trace)
        for t, vy in edge.candidatos:
            vf = float(mx.valor_real(vy, {}))
            desc = f"lado {y} = {val}, {var} = {t}"
            q = mx.exact_value(vy)
            candidatos.append((desc, Fraction(q) if q is not None else vy, vf))
    lados_v = [(y, sc, sd, sa), (y, sc, sd, sb)]
    for var, ia, ib, val in lados_v:
        g = mx.substitute(f, x, mx.parse(str(val)))
        edge = _extremos_lado(g, var, ia, ib, trace)
        for t, vy in edge.candidatos:
            vf = float(mx.valor_real(vy, {}))
            desc = f"lado {x} = {val}, {var} = {t}"
            q = mx.exact_value(vy)
            candidatos.append((desc, Fraction(q) if q is not None else vy, vf))
    esquinas_exactas = 0
    for cx in (sa, sb):
        for cy in (sc, sd):
            v = _eval_exacta(f, {x: mx.parse(str(cx)), y: mx.parse(str(cy))})
            if v is not None:
                esquinas_exactas += 1
                candidatos.append((f"esquina ({cx}, {cy})", Fraction(v), float(Fraction(v))))
    if not candidatos:
        raise _no("f no es exacta en ninguna esquina del rectángulo: con parámetros "
                  "u otra no exactitud no hay candidatos que comparar")
    if esquinas_exactas < 4:
        trace.aviso("mv.recinto_esquinas", "alguna esquina no es exacta y no entra "
                                           "en la comparación")
    minimo = min(candidatos, key=lambda c: c[2])
    maximo = max(candidatos, key=lambda c: c[2])
    trace.regla("mv.weierstrass", f"mínimo {minimo[1]} en {minimo[0]}; "
                                  f"máximo {maximo[1]} en {maximo[0]}",
                why="cerrado y acotado: el extremo está entre los candidatos")
    return Recinto((minimo[0], minimo[1]), (maximo[0], maximo[1]))


def _extremos_region(f: mx.Expr, vars: list[str], g, trace: Trace) -> Recinto:
    """Weierstrass en {g ≤ 0}: críticos con g < 0, Lagrange en g = 0 y los puntos
    singulares de la frontera (∇g = 0), que Lagrange no ve."""
    from academic_core.domain.engineering.mathlab import sistemas as S

    g = g if isinstance(g, mx.Expr) else mx.parse(str(g))
    _acotada(g, vars, trace)
    candidatos: list[tuple[str, object, float]] = []

    def entra(desc, punto):
        v = _valor_f(f, vars, punto)
        candidatos.append((f"{desc} ({', '.join(texto_coord(c) for c in punto)})", v,
                           _float(v)))
    caja = _caja_region(g, vars)

    def dentro_reg(p):
        return float(mx.valor_real(g, {v: _float(c) for v, c in zip(vars, p)})) < -1e-12
    candidatos.extend(_criticos_interiores(f, vars, dentro_reg, caja, trace))
    try:
        for punto, _ in lagrange(f, g, vars, trace):
            entra("frontera", punto)
    except UnsupportedError as exc:
        c = _constante_en_ligadura(f, [g], vars)
        if c is not None:
            candidatos.append(("toda la frontera (f constante en ella)", c, _float(c)))
        else:
            from academic_core.domain.engineering.mathlab import limite as LM

            lam = "lam"
            ecs = [LM._limpio(mx.Sub(_d(f, v), mx.Mul(mx.Sym(lam), _d(g, v)))) for v in vars]
            vals = _valores_no_aislados(ecs + [g], list(vars) + [lam], f, vars,
                                        lambda p: True, caja, trace)
            if not vals:
                raise exc
            candidatos.extend((d.replace("punto crítico", "frontera"), v, _float(v))
                              for d, v in vals)
    try:
        sing = S.resolver([g] + [_d(g, v) for v in vars], list(vars), Trace())
    except UnsupportedError:
        sing = []
    for s in sing:
        entra("frontera singular", tuple(_coord(s[v]) for v in vars))
    if not candidatos:
        raise _no("sin candidatos: ¿el recinto {g ≤ 0} es vacío?")
    minimo = min(candidatos, key=lambda c: c[2])
    maximo = max(candidatos, key=lambda c: c[2])
    trace.regla("mv.weierstrass", f"mínimo {texto_coord(minimo[1])} en {minimo[0]}; "
                                  f"máximo {texto_coord(maximo[1])} en {maximo[0]}",
                why="compacto y f continua: los extremos están entre los candidatos "
                    "(interior + Lagrange en la frontera + puntos singulares)")
    return Recinto((minimo[0], minimo[1]), (maximo[0], maximo[1]))


def _direcciones(n: int) -> list[tuple[float, ...]]:
    """Direcciones unitarias bien repartidas en ℝ² (720) o ℝ³ (espiral de Fibonacci)."""
    if n == 2:
        return [(math.cos(2 * math.pi * k / 720), math.sin(2 * math.pi * k / 720))
                for k in range(720)]
    out = []
    m = 2000
    for k in range(m):
        zc = 1 - 2 * (k + 0.5) / m
        r = math.sqrt(1 - zc * zc)
        th = math.pi * (3 - math.sqrt(5)) * k
        out.append((r * math.cos(th), r * math.sin(th), zc))
    return out


def _acotada(g: mx.Expr, vars: list[str], trace: Trace) -> None:
    """{g ≤ 0} acotado: la parte de mayor grado de g (polinómica) es > 0 en todas las
    direcciones (y de grado par)."""
    from academic_core.domain.engineering.mathlab import poly as Pm

    try:
        p = Pm.as_poly(g)
    except Exception:  # noqa: BLE001
        p = None
    if p is None or Pm.atoms_of(p) or len(vars) not in (2, 3):
        raise _no("['region', g] necesita g polinómica en 2 o 3 variables")
    d = max(Pm.mono_degree(m) for m in p)
    top = {m: c for m, c in p.items() if Pm.mono_degree(m) == d}
    malos = 0
    for u in _direcciones(len(vars)):
        val = sum(float(c) * math.prod(u[i] ** Pm.mono_exp(m, v) for i, v in enumerate(vars))
                  for m, c in top.items())
        if val <= 1e-9:
            malos += 1
    if d % 2 or malos:
        raise _no("{g ≤ 0} no es acotado (la parte de mayor grado de g no es definida "
                  "positiva): Weierstrass no aplica")
    trace.hipotesis("weierstrass_mv", "{g ≤ 0} compacto",
                    "cerrado (g continua) y acotado (parte de mayor grado de g > 0 en "
                    "toda dirección)")


def _extremos_lado(g, var, ia, ib, trace):
    """Extremos de f en un lado; si f es constante en él, sus dos extremos."""
    from academic_core.domain.engineering.mathlab import estudio as ES

    a, b = mx.parse(str(ia)), mx.parse(str(ib))
    if var not in mx.variables(g) or _es_cero_racional(_d(g, var)):
        v = _valor_f(g, [var], (_a_frac(a, "lado"),)) if mx.exact_value(a) is not None else g
        trace.regla("mv.lado_constante", f"f es constante en este lado: {texto_coord(v)}")

        @dataclass(frozen=True)
        class _Lado:
            candidatos: tuple

        return _Lado(((mx.text(a), _a_num(v) if isinstance(v, Fraction) else v),))
    return ES.extremos_absolutos(g, var, a, b, trace)


def _caja_region(g: mx.Expr, vars: list[str]) -> list[tuple[float, float]]:
    """Caja que contiene {g ≤ 0} (acotado): en cada dirección, el radio más lejano con
    g ≤ 0 (barrido logarítmico y bisección)."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    n = len(vars)
    gc = MI.compilar(g, list(vars))
    if gc is None:
        return [(-10.0, 10.0)] * n

    def val(p):
        try:
            return gc(list(p))
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
    puntos = [tuple(0.0 for _ in range(n))]
    dirs = _direcciones(n)[:: (4 if n == 2 else 5)]
    for u in dirs:
        radios = [0.01 * 1.15 ** j for j in range(80)]
        dentro = [r for r in radios if (v := val([r * c for c in u])) is not None and v <= 0]
        if not dentro:
            continue
        lo, hi = max(dentro), max(dentro) * 1.15
        for _ in range(40):
            m = (lo + hi) / 2
            v = val([m * c for c in u])
            if v is not None and v <= 0:
                lo = m
            else:
                hi = m
        puntos.append(tuple(lo * c for c in u))
    return [(min(p[k] for p in puntos) - 1e-6, max(p[k] for p in puntos) + 1e-6)
            for k in range(n)]


def _criticos_interiores(f, vars, dentro, caja, trace) -> list[tuple[str, object, float]]:
    """Candidatos interiores: puntos críticos aislados dentro, o, si forman curvas,
    los valores críticos (finitos) que se alcanzan dentro."""
    out = []
    try:
        pts = puntos_criticos(f, vars, trace)
    except UnsupportedError as exc:
        if "no están aisladas" not in str(exc):
            raise
        trace.aviso("mv.criticos_curva", "los puntos críticos forman curvas: f es constante "
                    "en cada una, así que bastan sus valores")
        grad = [_d(f, v) for v in vars]
        for desc, v in _valores_no_aislados(grad, list(vars), f, vars, dentro, caja, trace):
            out.append((desc, v, _float(v)))
        return out
    for punto, _clase in pts:
        if dentro(punto):
            v = _valor_f(f, vars, punto)
            out.append((f"interior ({', '.join(texto_coord(c) for c in punto)})", v, _float(v)))
    return out


def _valores_no_aislados(ecs, incognitas, f, vars, dentro, caja, trace) -> list[tuple[str, object]]:
    """Candidatos de un conjunto crítico no aislado (curvas más, quizá, puntos
    sueltos). Eliminando todo menos w en (ecs, f − w) queda un polinomio cuyas raíces
    son TODOS los valores críticos (Sard). Para cada factor racional m de ese
    polinomio se resuelve (ecs, m(f) = 0): si sus puntos están aislados se toman los
    que caen dentro; si forman una curva (f es constante en ella) se corta con
    x = c, y = c… para ver si pasa por dentro."""
    from academic_core.domain.engineering.mathlab import poly as Pm
    from academic_core.domain.engineering.mathlab import sistemas as S

    w = "w__"
    polis = [S.a_polinomio(e, incognitas, Trace()) for e in ecs]
    polis.append(S.a_polinomio(mx.Sub(f, mx.Sym(w)), incognitas + [w], Trace()))
    orden = list(incognitas) + [w]
    G = S.grobner([S._a_exp(p, orden) for p in polis if p])
    solo_w = [g for g in G if all(e == 0 for e in S._lider(g)[:-1])]
    if not solo_w:
        raise _no("conjunto crítico con infinitos valores: no se puede comparar")
    gw = solo_w[0]
    uni = [Fraction(0)] * (S._lider(gw)[-1] + 1)
    for e, c in gw.items():
        uni[e[-1]] = c
    grupos = S.factores(uni)
    trace.regla("mv.valores_criticos", "valores críticos posibles: " + ", ".join(
        mx.text(z.expr) if z.exacto else f"≈ {z.x:.10g}" for _, vs in grupos for z in vs),
        why="eliminando las variables de (sistema, f = w) queda un polinomio en w")
    out = []
    fp = Pm.as_poly(f)
    for m, valores in grupos:
        # m(f) como expresión con coeficientes racionales
        mf: Pm.Polynomial = {}
        pot: Pm.Polynomial = {(): Fraction(1)}
        for c in m:
            mf = Pm.add(mf, Pm.scale(pot, c))
            pot = Pm.mul(pot, fp)
        base = list(ecs) + [Pm.to_expr(mf)]
        puntos = []
        try:
            for s_ in S.resolver(base, list(incognitas), Trace()):
                puntos.append(tuple(_coord(s_[u]) for u in vars))
        except UnsupportedError:
            for k, v in enumerate(vars):
                lo, hi = caja[k]
                for i in range(41):
                    c = Fraction(lo + (hi - lo) * i / 40).limit_denominator(1000)
                    try:
                        sols = S.resolver(base + [mx.Sub(mx.Sym(v), _num(c))],
                                          list(incognitas), Trace())
                    except UnsupportedError:
                        continue
                    puntos.extend(tuple(_coord(s_[u]) for u in vars) for s_ in sols)
        for z in valores:
            for p in puntos:
                if dentro(p) and abs(_float(_valor_f(f, vars, p)) - z.x) <= 1e-9 * max(1.0, abs(z.x)):
                    valor = z.fraccion if z.fraccion is not None else (z.expr if z.exacto else z.x)
                    out.append((f"punto crítico ({', '.join(texto_coord(c) for c in p)})", valor))
                    break
    return out


def _dentro(v, a, b) -> bool:
    fa = mx.valor_real(mx.parse(str(a)), {})
    fb = mx.valor_real(mx.parse(str(b)), {})
    if fa is None or fb is None:
        return False
    return fa < _float(v) < fb
