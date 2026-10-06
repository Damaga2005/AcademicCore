# SPDX-License-Identifier: MIT
"""ML-6: integración múltiple exacta con segundo camino numérico.

- ``iterada``: ∫…∫ f con límites que dependen de las variables exteriores
  (Fubini), de dentro hacia fuera: primitiva exacta en la variable interior
  (motor E0.1, o la sustitución trigonométrica de ML-2), comprobada derivando, y
  Barrow con límites simbólicos. Segundo camino independiente: cuadratura de
  Gauss-Legendre anidada sobre la misma región.
- ``coordenadas``: polares (r, t), cilíndricas (r, t, z) y esféricas
  (rho, phi, theta) con su jacobiano |J| = r, r, rho²·sen(phi) declarado y con
  la validez del cambio (inyectivo salvo en un conjunto de medida nula).
- ``cambio_orden``: región de tipo I {a ≤ x ≤ b, g₁(x) ≤ y ≤ g₂(x)} reescrita
  como unión de franjas de tipo II, con las inversas de g₁ y g₂; las dos
  integrales iteradas se calculan y tienen que coincidir.
- ``masa`` y ``centro_masas`` como integrales de la densidad.

Si alguna primitiva no sale exacta el resultado es numérico y se dice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

NOMBRES = frozenset({"rho", "phi", "theta"})
GL_PUNTOS = 24
MAX_DIM = 3


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def leer(texto) -> mx.Expr:
    if isinstance(texto, mx.Expr):
        return texto
    if isinstance(texto, (int, Fraction)):
        return mx.Num(Fraction(texto)) if texto >= 0 else mx.Neg(mx.Num(-Fraction(texto)))
    return mx.parse(str(texto), nombres=NOMBRES)


def _limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import trig as T

    e = _pitagoras(_logexp(e))
    try:
        e = LM._limpio(T.simplify(e))
    except Exception:  # noqa: BLE001 - se queda sin simplificar, sigue siendo exacta
        pass
    return _bonito(_canon(e))


def _neg_de(e: mx.Expr) -> mx.Expr | None:
    """u si e = −u (Neg, número negativo o producto con coeficiente negativo)."""
    if isinstance(e, mx.Neg):
        return e.arg
    if isinstance(e, mx.Num) and e.value < 0:
        return mx.Num(-e.value)
    if isinstance(e, mx.Mul):
        u = _neg_de(e.left)
        if u is not None:
            return u if mx.exact_value(u) == 1 else mx.Mul(u, e.right)
    if isinstance(e, mx.Div):
        u = _neg_de(e.left)
        if u is not None:
            return mx.Div(u, e.right)
    return None


def _bonito(e: mx.Expr) -> mx.Expr:
    """a + −b → a − b, a − −b → a + b, 1·u → u (solo presentación)."""
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        a, b = _bonito(e.left), _bonito(e.right)
        if isinstance(e, mx.Mul):
            if mx.exact_value(a) == 1 and not mx.variables(a) and isinstance(a, mx.Num):
                return b
            if mx.exact_value(b) == 1 and isinstance(b, mx.Num):
                return a
            return mx.Mul(a, b)
        if isinstance(e, mx.Div):
            return mx.Div(a, b)
        u = _neg_de(b)
        if u is not None:
            return mx.Sub(a, u) if isinstance(e, mx.Add) else mx.Add(a, u)
        return type(e)(a, b)
    if isinstance(e, mx.Neg):
        return mx.Neg(_bonito(e.arg))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_bonito(x) for x in e.args))
    if isinstance(e, mx.Pow):
        return mx.Pow(_bonito(e.base), e.exponent)
    return e


def _canon(e: mx.Expr) -> mx.Expr:
    """Forma normal polinómica sobre átomos (agrupa «a − −b», términos repetidos);
    se queda la más corta. Los nombres largos se protegen del re-parseo."""
    from academic_core.domain.engineering.mathlab import poly as P

    largos = sorted(v for v in mx.variables(e) if len(v) > 1)
    libres = [c for c in "ABCDFGHJKLMNOPQRSTUVW" if c not in mx.variables(e)]
    ida = dict(zip(largos, libres))
    f = e
    for v, c in ida.items():
        f = mx.substitute(f, v, mx.Sym(c))
    try:
        g = P.to_expr(P.as_poly(f))
    except Exception:  # noqa: BLE001
        return e
    for v, c in ida.items():
        g = mx.substitute(g, c, mx.Sym(v))
    return g if len(mx.text(g)) <= 1.25 * len(mx.text(e)) else e


def _logexp(e: mx.Expr) -> mx.Expr:
    """ln(e) = 1, ln(exp(u)) = u, exp(ln(u)) = u (u > 0 donde se usa), x − 0 = x."""
    if isinstance(e, mx.Call):
        args = tuple(_logexp(a) for a in e.args)
        if e.name == "ln" and args[0] == mx.Const("e"):
            return mx.Num(Fraction(1))
        if e.name == "ln" and isinstance(args[0], mx.Call) and args[0].name == "exp":
            return args[0].args[0]
        if e.name == "exp" and isinstance(args[0], mx.Call) and args[0].name == "ln":
            return args[0].args[0]
        return mx.Call(e.name, args)
    if isinstance(e, mx.Sub) and mx.exact_value(e.right) == 0:
        return _logexp(e.left)
    if isinstance(e, mx.Div) and mx.exact_value(e.right) == 1:
        return _logexp(e.left)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_logexp(e.left), _logexp(e.right))
    if isinstance(e, mx.Pow):
        return mx.Pow(_logexp(e.base), _logexp(e.exponent))
    if isinstance(e, mx.Neg):
        return mx.Neg(_logexp(e.arg))
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _logexp(e.radicand))
    return e


def _pitagoras(e: mx.Expr) -> mx.Expr:
    """Forma polinómica con cos²(u) = 1 − sen²(u), también dentro de las funciones.
    Solo se aplica si de verdad acorta (si no, se deja como estaba)."""
    from academic_core.domain.engineering.mathlab import poly as P

    if isinstance(e, mx.Call):
        e = mx.Call(e.name, tuple(_pitagoras(a) for a in e.args))
    elif isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        e = type(e)(_pitagoras(e.left), _pitagoras(e.right))
    elif isinstance(e, mx.Neg):
        e = mx.Neg(_pitagoras(e.arg))
    elif isinstance(e, mx.Pow):
        e = mx.Pow(_pitagoras(e.base), e.exponent)
    if not any(isinstance(n, mx.Call) and n.name in ("sin", "cos") for n in _nodos(e)):
        return e
    largos = sorted(v for v in mx.variables(e) if len(v) > 1)
    if largos:
        libres = [c for c in "ABCDFGHJKLMNOPQRSTUVW" if c not in mx.variables(e)]
        ida = dict(zip(largos, libres))
        f = e
        for v, c in ida.items():
            f = mx.substitute(f, v, mx.Sym(c))
        g = _pitagoras(f)
        for v, c in ida.items():
            g = mx.substitute(g, c, mx.Sym(v))
        return g if g is not f else e
    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return e
    cambio = True
    while cambio:
        cambio = False
        for m, c in list(p.items()):
            for v, k in m:
                if P.is_atom(v) and P.atom_text(v).startswith("cos(") and k >= 2:
                    seno = "@sin(" + P.atom_text(v)[4:]
                    resto = P.mono_div(m, ((v, 2),))
                    p = P.add(p, {m: c}, -1)
                    p = P.add(p, P.mul({resto: c}, P.add({(): Fraction(1)},
                                                         {((seno, 2),): Fraction(1)}, -1)))
                    cambio = True
                    break
            if cambio:
                break
    nuevo = P.to_expr(p)
    return nuevo if len(mx.text(nuevo)) < len(mx.text(e)) else e


def _nodos(e: mx.Expr):
    yield e
    for campo in ("left", "right", "arg", "base", "exponent", "radicand"):
        h = getattr(e, campo, None)
        if isinstance(h, mx.Expr):
            yield from _nodos(h)
    for a in getattr(e, "args", ()) or ():
        if isinstance(a, mx.Expr):
            yield from _nodos(a)


# ---------------------------------------------------------------------------
# primitiva en una variable (las demás son constantes)
# ---------------------------------------------------------------------------


def primitiva(f: mx.Expr, var: str, trace: Trace) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import primitivas as PR

    F = _e01(f, var)
    if F is None:
        # sumas: término a término sobre la forma expandida
        from academic_core.domain.engineering.mathlab import poly as P

        try:
            p = P.as_poly(f)
        except Exception:  # noqa: BLE001
            p = {}
        if len(p) > 1:
            partes = []
            for m, c in p.items():
                Fi = _e01(P.to_expr({m: c}), var)
                if Fi is None:
                    partes = None
                    break
                partes.append(Fi)
            if partes:
                F = partes[0]
                for Fi in partes[1:]:
                    F = mx.Add(F, Fi)
    if F is None:
        try:
            F = PR.sustitucion_trigonometrica(f, var, Trace())
        except Exception:  # noqa: BLE001
            F = None
    if F is None:
        raise _no(f"sin primitiva exacta de {mx.text(f)} en d{var}")
    try:
        bien = _deriva_bien(DM.differentiate(F, var), f, var)
    except Exception:  # noqa: BLE001 - el derivador no acepta algún nodo: diferencias
        bien = _deriva_bien_numerica(F, f, var)
    if not bien:
        raise _no(f"la primitiva de {mx.text(f)} en d{var} no se verifica derivando")
    F = _limpio(F)
    trace.regla("multiple.primitiva", f"∫ {mx.text(f)} d{var} = {mx.text(F)}",
                why="las demás variables son constantes en esta integración (Fubini)")
    return F


def _e01(f: mx.Expr, var: str) -> mx.Expr | None:
    from academic_core.domain.engineering.symbolic import integrate as I
    from academic_core.domain.engineering.symbolic import steps as S

    if var not in mx.variables(f):
        return mx.Mul(f, mx.Sym(var))
    # factores constantes (π, e, otras variables) fuera de la integral
    factores = list(_factores(f))
    const = [g for g in factores if var not in mx.variables(g)]
    if const and len(const) < len(factores):
        resto = [g for g in factores if var in mx.variables(g)]
        G = resto[0]
        for g in resto[1:]:
            G = mx.Mul(G, g)
        Fg = _e01(G, var)
        if Fg is None:
            return None
        for c in const:
            Fg = mx.Mul(c, Fg)
        return Fg
    if isinstance(f, mx.Neg):
        Fg = _e01(f.arg, var)
        return None if Fg is None else mx.Neg(Fg)
    try:
        _, G, _ = I.antiderivative(mx.to_symbolic(f), var, S.StepLog())
        return mx.from_symbolic(G)
    except Exception:  # noqa: BLE001
        return None


def _deriva_bien_numerica(F: mx.Expr, f: mx.Expr, var: str) -> bool:
    """F′ = f por diferencias centrales de orden 4 en varios puntos."""
    nombres = sorted(mx.variables(f) | mx.variables(F) | {var})
    validos = 0
    for k in range(16):
        env = {n: 0.11 + 0.093 * k + 0.031 * i for i, n in enumerate(nombres)}
        h = 1e-3
        try:
            vals = []
            for d in (-2, -1, 1, 2):
                vals.append(mx.valor_real(F, {**env, var: env[var] + d * h}))
            b = mx.valor_real(f, env)
        except (ValueError, OverflowError, ZeroDivisionError):
            continue
        if b is None or any(v is None for v in vals):
            continue
        d = (vals[0] - 8 * vals[1] + 8 * vals[2] - vals[3]) / (12 * h)
        if abs(d - b) > 1e-7 * max(1.0, abs(b)):
            return False
        validos += 1
    return validos >= 3


def _factores(e: mx.Expr):
    if isinstance(e, mx.Mul):
        yield from _factores(e.left)
        yield from _factores(e.right)
    else:
        yield e


def _deriva_bien(dF: mx.Expr, f: mx.Expr, var: str) -> bool:
    from academic_core.domain.engineering.mathlab import verify as V

    try:
        iguales, _, _ = V.check_equivalence(dF, f)
        if iguales:
            return True
    except Exception:  # noqa: BLE001
        pass
    nombres = sorted(mx.variables(f) | mx.variables(dF))
    validos = 0
    for k in range(16):
        env = {n: 0.11 + 0.093 * k + 0.031 * i for i, n in enumerate(nombres)}
        try:
            a, b = mx.valor_real(dF, env), mx.valor_real(f, env)
        except (ValueError, OverflowError, ZeroDivisionError):
            continue
        if a is None or b is None:
            continue                      # fuera del dominio de f: no cuenta
        if abs(a - b) > 1e-9 * max(1.0, abs(b)):
            return False
        validos += 1
    return validos >= 3


# ---------------------------------------------------------------------------
# integral iterada
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    exacto: mx.Expr | None
    numerico: float
    coincide: bool

    def texto(self) -> str:
        if self.exacto is None:
            return f"≈ {self.numerico:.12g}"
        return f"{mx.text(self.exacto)} ≈ {self.numerico:.12g}"


def _norm_limites(limites) -> list[tuple[str, mx.Expr, mx.Expr]]:
    out = []
    for item in limites:
        if len(item) != 3:
            raise _error("BAD_INPUT", "cada límite es [variable, desde, hasta]")
        out.append((str(item[0]), leer(item[1]), leer(item[2])))
    if not 1 <= len(out) <= MAX_DIM:
        raise _error("BAD_INPUT", f"entre 1 y {MAX_DIM} integrales")
    vistos = []
    for v, lo, hi in out:
        if v in vistos:
            raise _error("BAD_INPUT", f"{v} aparece dos veces")
        # un límite solo puede depender de variables más exteriores (Fubini)
        interiores = {w for w, _, _ in out[:out.index((v, lo, hi)) + 1]}
        malas = (mx.variables(lo) | mx.variables(hi)) & interiores
        if malas:
            raise _error("BAD_INPUT", f"los límites de {v} dependen de {', '.join(sorted(malas))}, "
                                      "que se integra antes: el orden no es válido")
        vistos.append(v)
    return out


def iterada(f, limites, trace: Trace | None = None) -> Resultado:
    """``limites`` de dentro hacia fuera: [[x, a(y,z), b(y,z)], [y, c(z), d(z)], [z, e, f]]."""
    trace = trace if trace is not None else Trace()
    f = leer(f)
    L = _norm_limites(limites)
    libres = mx.variables(f) - {v for v, _, _ in L}
    for _, lo, hi in L:
        libres |= (mx.variables(lo) | mx.variables(hi)) - {v for v, _, _ in L}
    if libres:
        raise _error("BAD_INPUT", f"variables sin integrar: {', '.join(sorted(libres))}")
    trace.metodo("multiple.fubini", "integral iterada de dentro hacia fuera",
                 why="Fubini: f continua en una región descrita por límites continuos")
    num = numerica(f, L)
    exacto: mx.Expr | None = f
    try:
        for v, lo, hi in L:
            F = primitiva(exacto, v, trace)
            arriba = _limpio(mx.substitute(F, v, hi))
            abajo = _limpio(mx.substitute(F, v, lo))
            exacto = _limpio(mx.Sub(arriba, abajo))
            trace.regla("multiple.barrow",
                        f"[{mx.text(F)}] de {v} = {mx.text(lo)} a {v} = {mx.text(hi)}: "
                        f"({mx.text(arriba)}) − ({mx.text(abajo)}) = {mx.text(exacto)}",
                        why="regla de Barrow: F(límite superior) − F(límite inferior)")
    except UnsupportedError as exc:
        exacto = _otro_orden(f, L, trace)
        if exacto is None:
            trace.aviso("multiple.sin_exacta", f"sin forma exacta: {exc}")
    if exacto is None:
        return Resultado(None, num, False)
    try:
        val = float(mx.valor_real(exacto, {}))
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        val = math.nan
    coincide = abs(val - num) <= 1e-7 * max(1.0, abs(num))
    if coincide:
        trace.verificacion("multiple.gauss", f"cuadratura tanh-sinh anidada da {num:.12g}: coincide",
                           why="segundo camino independiente de las primitivas")
    else:
        trace.aviso("multiple.discrepa", f"exacto {val:.12g} frente a numérico {num:.12g}: "
                    "¿discontinuidad o singularidad en la región? se da el numérico")
    return Resultado(exacto if coincide else None, num, coincide)


def _otro_orden(f: mx.Expr, L, trace: Trace) -> mx.Expr | None:
    """Con todos los límites constantes (rectángulo o caja) el orden es libre
    (Fubini): si uno no tiene primitiva exacta se prueban los demás."""
    import itertools

    if len(L) < 2 or any(mx.variables(lo) | mx.variables(hi) for _, lo, hi in L):
        return None
    for orden in itertools.permutations(L):
        if list(orden) == list(L):
            continue
        t = Trace()
        exacto = f
        try:
            for v, lo, hi in orden:
                F = primitiva(exacto, v, t)
                exacto = _limpio(mx.Sub(_limpio(mx.substitute(F, v, hi)),
                                        _limpio(mx.substitute(F, v, lo))))
        except UnsupportedError:
            continue
        trace.regla("multiple.otro_orden", "se cambia al orden " + " ".join(
            f"d{v}" for v, _, _ in orden) + ", donde sí hay primitivas exactas",
            why="límites constantes: Fubini permite integrar en cualquier orden")
        exacto = f
        for v, lo, hi in orden:                      # se repite con la traza buena
            F = primitiva(exacto, v, trace)
            arriba = _limpio(mx.substitute(F, v, hi))
            abajo = _limpio(mx.substitute(F, v, lo))
            exacto = _limpio(mx.Sub(arriba, abajo))
            trace.regla("multiple.barrow",
                        f"[{mx.text(F)}] de {v} = {mx.text(lo)} a {v} = {mx.text(hi)}: "
                        f"({mx.text(arriba)}) − ({mx.text(abajo)}) = {mx.text(exacto)}",
                        why="regla de Barrow: F(límite superior) − F(límite inferior)")
        return exacto
    return None


_FUNCIONES = {"sin": "math.sin", "cos": "math.cos", "tan": "math.tan", "exp": "math.exp",
              "ln": "math.log", "log": "math.log", "sqrt": "math.sqrt", "asin": "math.asin",
              "acos": "math.acos", "atan": "math.atan", "arcsin": "math.asin",
              "arccos": "math.acos", "arctan": "math.atan", "sinh": "math.sinh",
              "cosh": "math.cosh", "tanh": "math.tanh", "abs": "abs"}


def compilar(e: mx.Expr, nombres: list[str]):
    """Expr → función de Python (float); None si hay un nodo que no se traduce."""
    def py(n) -> str:
        if isinstance(n, mx.Num):
            return repr(float(n.value))
        if isinstance(n, mx.Sym):
            return f"v[{nombres.index(n.name)}]"
        if isinstance(n, mx.Const):
            return {"pi": "math.pi", "e": "math.e"}[n.name]
        if isinstance(n, mx.Add):
            return f"({py(n.left)}+{py(n.right)})"
        if isinstance(n, mx.Sub):
            return f"({py(n.left)}-{py(n.right)})"
        if isinstance(n, mx.Mul):
            return f"({py(n.left)}*{py(n.right)})"
        if isinstance(n, mx.Div):
            return f"({py(n.left)}/{py(n.right)})"
        if isinstance(n, mx.Pow):
            return f"_pot({py(n.base)},{py(n.exponent)})"
        if isinstance(n, mx.Neg):
            return f"(-{py(n.arg)})"
        if isinstance(n, mx.Root):
            return f"_raiz({py(n.radicand)},{int(n.degree)})"
        if isinstance(n, mx.Call) and n.name in _FUNCIONES and len(n.args) == 1:
            return f"{_FUNCIONES[n.name]}({py(n.args[0])})"
        raise KeyError(type(n).__name__)

    try:
        codigo = py(e)
    except (KeyError, ValueError, AttributeError):
        return None
    return eval(f"lambda v: {codigo}", {"math": math, "_pot": _pot, "_raiz": _raiz,  # noqa: S307
                                        "abs": abs})


def _pot(a: float, b: float) -> float:
    if a < 0 and float(b).is_integer():
        return a ** int(b)
    return a ** b


def _raiz(a: float, n: int) -> float:
    if a < 0 and n % 2:
        return -((-a) ** (1 / n))
    return a ** (1 / n)


def _tanh_sinh(h: float = 1 / 12, tmax: float = 3.2) -> list[tuple[float, float]]:
    """Nodos y pesos de tanh-sinh en (−1, 1): tolera singularidades integrables en
    los extremos (√(1 − x²), 1/√x…), que es lo que rompe a Gauss."""
    out = []
    k = -int(tmax / h)
    while k * h <= tmax:
        t = k * h
        u = math.pi / 2 * math.sinh(t)
        x = math.tanh(u)
        w = h * math.pi / 2 * math.cosh(t) / math.cosh(u) ** 2
        if abs(x) < 1 and w > 1e-300:
            out.append((x, w))
        k += 1
    return out


_NODOS = _tanh_sinh()


def numerica(f: mx.Expr, L) -> float:
    """Cuadratura tanh-sinh anidada: la variable exterior manda en los límites de las
    interiores; los extremos nunca se evalúan."""
    L = list(L)
    nombres = [v for v, _, _ in L]
    fc = compilar(f, nombres)
    lims = [(compilar(lo, nombres), compilar(hi, nombres)) for _, lo, hi in L]
    if fc is None or any(a is None or b is None for a, b in lims):
        raise _no("el integrando o un límite no se pueden evaluar numéricamente")
    v = [0.0] * len(L)

    def rec(k: int) -> float:
        if k < 0:
            return fc(v)
        a, b = lims[k][0](v), lims[k][1](v)
        m, h = (a + b) / 2, (b - a) / 2
        total = 0.0
        for x, w in _NODOS:
            v[k] = m + h * x
            total += w * rec(k - 1)
        return total * h
    try:
        r = rec(len(L) - 1)
    except (ValueError, OverflowError, ZeroDivisionError, TypeError):
        raise _no("la cuadratura numérica no se puede evaluar (singularidad)") from None
    if isinstance(r, complex) or not math.isfinite(r):
        raise _no("la cuadratura numérica no da un valor real finito")
    return r


# ---------------------------------------------------------------------------
# cambios de coordenadas
# ---------------------------------------------------------------------------

_CAMBIOS = {
    "polares": ({"x": "r*cos(t)", "y": "r*sin(t)"}, "r", ("r", "t")),
    "cilindricas": ({"x": "r*cos(t)", "y": "r*sin(t)", "z": "z"}, "r", ("r", "t", "z")),
    "esfericas": ({"x": "rho*sin(phi)*cos(theta)", "y": "rho*sin(phi)*sin(theta)",
                   "z": "rho*cos(phi)"}, "rho^2*sin(phi)", ("rho", "phi", "theta")),
}


def en_coordenadas(f, sistema: str, limites, trace: Trace | None = None) -> Resultado:
    """f en cartesianas; los límites ya en el sistema nuevo."""
    trace = trace if trace is not None else Trace()
    if sistema not in _CAMBIOS:
        raise _error("BAD_INPUT", f"coordenadas: {', '.join(_CAMBIOS)}")
    cambio, jac, nuevas = _CAMBIOS[sistema]
    f = leer(f)
    g = f
    for v, e in cambio.items():
        g = mx.substitute(g, v, leer(e))
    g = _limpio(mx.Mul(g, leer(jac)))
    usadas = {str(item[0]) for item in limites}
    if not usadas <= set(nuevas):
        raise _error("BAD_INPUT", f"en {sistema} las variables son {', '.join(nuevas)}")
    trace.regla("multiple.cambio", ", ".join(f"{v} = {e}" for v, e in cambio.items()) +
                f"; |J| = {jac}", why=f"{sistema}: la simetría de la región lo aconseja; el "
                "jacobiano es el factor de escala del elemento de volumen")
    donde = {"polares": "el origen (r = 0)", "cilindricas": "el eje z (r = 0)",
             "esfericas": "el eje z (rho = 0 o sen phi = 0)"}[sistema]
    trace.hipotesis("multiple.cambio_valido", "cambio inyectivo y J ≠ 0 salvo medida nula",
                    f"solo falla en {donde}, de medida nula: no cambia la integral")
    trace.regla("multiple.integrando", f"f·|J| = {mx.text(g)}")
    return iterada(g, limites, trace)


# ---------------------------------------------------------------------------
# cambio del orden de integración (dobles)
# ---------------------------------------------------------------------------


def _invierte(g: mx.Expr, x: str, Y: mx.Expr) -> list[mx.Expr]:
    """Candidatas a x = g⁻¹(Y) para las formas de examen: c·h(x) + d con h lineal,
    potencia, raíz, exp o ln. Se devuelven todas las ramas; elige el llamador."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    pol = RZ._polinomio_de(g, x)
    cand: list[mx.Expr] = []
    if pol is not None and len(RZ._recorta(pol)) in (2, 3):
        p = RZ._recorta(pol)
        if len(p) == 2:
            cand.append(mx.Div(mx.Sub(Y, leer(p[0])), leer(p[1])))
        else:
            c, b, a = p
            k0 = b * b - 4 * a * c
            disc = mx.Mul(leer(4 * a), Y) if k0 == 0 else mx.Add(leer(k0), mx.Mul(leer(4 * a), Y))
            for s in (1, -1):
                raiz = mx.Root(2, disc)
                r2 = raiz if s > 0 else mx.Neg(raiz)
                cand.append(mx.Div(r2 if b == 0 else mx.Add(leer(-b), r2), leer(2 * a)))
        return cand
    # forma c·h(x) + d: se aísla numéricamente c y d con dos evaluaciones de h
    for h, inv in (("sqrt", lambda u: mx.Pow(u, leer(2))), ("exp", lambda u: mx.Call("ln", (u,))),
                   ("ln", lambda u: mx.Call("exp", (u,)))):
        hx = mx.Call(h, (mx.Sym(x),)) if h != "sqrt" else mx.Root(2, mx.Sym(x))
        lin = _lineal_en(g, hx, x)
        if lin is not None:
            c, d = lin
            u = Y if d == 0 else mx.Sub(Y, leer(d))
            cand.append(inv(u if c == 1 else mx.Div(u, leer(c))))
    return cand


def _lineal_en(g: mx.Expr, h: mx.Expr, x: str):
    """g = c·h + d con c, d racionales (se comprueba en varios puntos)."""
    pts = [0.37, 0.81, 1.3, 2.2]
    try:
        vals = [(float(mx.valor_real(h, {x: t})), float(mx.valor_real(g, {x: t}))) for t in pts]
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None
    (h0, g0), (h1, g1) = vals[0], vals[1]
    if abs(h1 - h0) < 1e-12:
        return None
    c = Fraction(g1 - g0) / Fraction(h1 - h0)
    c = c.limit_denominator(1000)
    d = Fraction(g0 - float(c) * h0).limit_denominator(1000)
    if c == 0 or any(abs(float(c) * hv + float(d) - gv) > 1e-9 for hv, gv in vals):
        return None
    return c, d


@dataclass(frozen=True)
class Franja:
    y_lo: mx.Expr
    y_hi: mx.Expr
    x_lo: mx.Expr
    x_hi: mx.Expr

    def texto(self, x: str, y: str) -> str:
        return (f"{mx.text(self.y_lo)} ≤ {y} ≤ {mx.text(self.y_hi)}, "
                f"{mx.text(self.x_lo)} ≤ {x} ≤ {mx.text(self.x_hi)}")


def cambio_orden(f, x: str, a, b, y: str, g1, g2,
                 trace: Trace | None = None) -> tuple[list[Franja], Resultado, Resultado]:
    """{a ≤ x ≤ b, g₁(x) ≤ y ≤ g₂(x)} → franjas {c ≤ y ≤ d, h₁(y) ≤ x ≤ h₂(y)}."""
    trace = trace if trace is not None else Trace()
    f, a, b, g1, g2 = leer(f), leer(a), leer(b), leer(g1), leer(g2)
    fa, fb = float(mx.valor_real(a, {})), float(mx.valor_real(b, {}))
    if not fa < fb:
        raise _error("BAD_INPUT", "hace falta a < b")
    Y = mx.Sym(y)

    def ev(g, t):
        return float(mx.valor_real(g, {x: t}))
    muestras = [fa + (fb - fa) * k / 400 for k in range(401)]
    for g in (g1, g2):
        d = [ev(g, t2) - ev(g, t1) for t1, t2 in zip(muestras, muestras[1:])]
        if any(u > 1e-12 for u in d) and any(u < -1e-12 for u in d):
            raise _no(f"{mx.text(g)} no es monótona en [{mx.text(a)}, {mx.text(b)}]: parte "
                      "la región antes de cambiar el orden")
    if any(ev(g1, t) > ev(g2, t) + 1e-12 for t in muestras):
        raise _error("BAD_INPUT", "g₁ ≤ g₂ no se cumple en todo el intervalo")
    # cortes en y: valores de g₁ y g₂ en los extremos
    cortes_e = []
    for g in (g1, g2):
        for t in (a, b):
            e = _limpio(mx.substitute(g, x, t))
            cortes_e.append((float(mx.valor_real(e, {})), e))
    cortes_e.sort(key=lambda c: c[0])
    cortes: list[tuple[float, mx.Expr]] = []
    for v, e in cortes_e:
        if not cortes or abs(v - cortes[-1][0]) > 1e-12:
            cortes.append((v, e))
    inversas = {id(g): [c for c in _invierte(g, x, Y)] for g in (g1, g2)}
    franjas: list[Franja] = []
    for (c, ce), (d, de) in zip(cortes, cortes[1:]):
        ym = (c + d) / 2
        dentro = [t for t in muestras if ev(g1, t) - 1e-12 <= ym <= ev(g2, t) + 1e-12]
        if not dentro:
            continue
        xl, xr = min(dentro), max(dentro)
        lo = _borde(xl, fa, fb, a, b, ym, inversas, (g1, g2), x, y)
        hi = _borde(xr, fa, fb, a, b, ym, inversas, (g1, g2), x, y)
        franjas.append(Franja(ce, de, _limpio(lo), _limpio(hi)))
    if not franjas:
        raise _error("BAD_INPUT", "la región es vacía")
    trace.regla("multiple.orden", "región en el otro orden: " + " ∪ ".join(
        "{" + fr.texto(x, y) + "}" for fr in franjas),
        why="se cortan las franjas horizontales donde cambia la curva que hace de borde; "
            "cada borde es la inversa de g₁ o g₂ (o una recta vertical x = a, x = b)")
    original = iterada(f, [[y, g1, g2], [x, a, b]], trace)
    partes = [iterada(f, [[x, fr.x_lo, fr.x_hi], [y, fr.y_lo, fr.y_hi]], Trace())
              for fr in franjas]
    num = sum(p.numerico for p in partes)
    exactos = [p.exacto for p in partes]
    total = None
    if all(e is not None for e in exactos):
        total = exactos[0]
        for e in exactos[1:]:
            total = mx.Add(total, e)
        total = _limpio(total)
    nuevo = Resultado(total, num, all(p.coincide for p in partes))
    if abs(original.numerico - nuevo.numerico) > 1e-7 * max(1.0, abs(num)):
        raise _error("INTERNAL", "los dos órdenes no coinciden: región mal reescrita")
    trace.verificacion("multiple.dos_ordenes", f"los dos órdenes dan {num:.12g}",
                       why="Fubini: el valor no depende del orden de integración")
    return franjas, original, nuevo


def _borde(xb: float, fa: float, fb: float, a, b, ym: float, inversas, gs, x, y):
    if abs(xb - fa) < 1e-9 * max(1.0, abs(fa)) + (fb - fa) / 400:
        if abs(xb - fa) < (fb - fa) / 800:
            return a
    if abs(xb - fb) < (fb - fa) / 800:
        return b
    for g in gs:
        for inv in inversas[id(g)]:
            try:
                v = float(mx.valor_real(inv, {y: ym}))
            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                continue
            if abs(v - xb) <= (fb - fa) / 200 + 1e-9:
                return inv
    raise _no(f"no sé invertir el borde que pasa por {x} ≈ {xb:.4g}")


# ---------------------------------------------------------------------------
# aplicaciones
# ---------------------------------------------------------------------------


def masa(densidad, limites, sistema: str = "cartesianas",
         trace: Trace | None = None) -> Resultado:
    trace = trace if trace is not None else Trace()
    trace.regla("multiple.masa", "M = ∫ densidad dV")
    if sistema == "cartesianas":
        return iterada(densidad, limites, trace)
    return en_coordenadas(densidad, sistema, limites, trace)


def centro_masas(densidad, limites, sistema: str = "cartesianas",
                 trace: Trace | None = None) -> tuple[Resultado, list[Resultado]]:
    """(M, [x̄, ȳ, (z̄)]) con x̄ = ∫x·ρ dV / M."""
    trace = trace if trace is not None else Trace()
    dim = len(limites)
    coords = ["x", "y", "z"][:dim]
    M = masa(densidad, limites, sistema, trace)
    if abs(M.numerico) < 1e-300:
        raise _error("BAD_INPUT", "masa nula: no hay centro de masas")
    out = []
    for c in coords:
        mom = masa(mx.Mul(leer(c), leer(densidad)), limites, sistema, Trace())
        ex = None
        if mom.exacto is not None and M.exacto is not None:
            ex = _limpio(mx.Div(mom.exacto, M.exacto))
        out.append(Resultado(ex, mom.numerico / M.numerico, mom.coincide and M.coincide))
        trace.regla("multiple.centro", f"{c}̄ = ∫{c}·ρ / M = " +
                    (mx.text(ex) if ex is not None else f"≈ {out[-1].numerico:.10g}"))
    return M, out
