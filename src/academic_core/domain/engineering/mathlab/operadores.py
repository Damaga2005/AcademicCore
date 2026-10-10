# SPDX-License-Identifier: MIT
"""ML-13: cálculo vectorial ampliado (Electromagnetismo y Física).

- Operadores ∇ en coordenadas ortogonales con sus factores de escala hᵢ:

      cartesianas (x, y, z):           h = (1, 1, 1)
      cilíndricas (r, phi, z):         h = (1, r, 1)
      esféricas   (r, theta, phi):     h = (1, r, r·sen θ)   (θ polar, φ azimutal)

  gradiente (1/hᵢ)∂V/∂uᵢ, divergencia (1/H)Σ∂(Fᵢ·H/hᵢ)/∂uᵢ, rotacional con el
  determinante de escala y laplaciano (1/H)Σ∂/∂uᵢ(H/hᵢ²·∂V/∂uᵢ), H = h₁h₂h₃.
  Segundo camino: lo mismo en cartesianas y comparado en puntos, pasando las
  componentes por la matriz de cambio de base.
- Controles ∇·(∇×F) = 0 y ∇×(∇V) = 0.
- Poisson: ρ = −ε₀·∇²V.
- Cambio de componentes entre bases con la matriz ortogonal R (RᵀR = I, ida y
  vuelta y módulo invariante comprobados).
- V dado ⇒ E = −∇V, ρ = −ε₀∇²V y la carga en una caja por los dos lados de
  Gauss: ε₀·∯E·dS (seis caras) = ∭ρ dV.
- Cinemática intrínseca de r(t): v, a, T, N, κ, radio de curvatura,
  a_t = d|v|/dt y a_n = κ|v|², con a_t² + a_n² = |a|² comprobado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from academic_core.domain.engineering.mathlab import multiple as MI
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

SISTEMAS = {
    "cartesianas": (("x", "y", "z"), ("1", "1", "1")),
    "cilindricas": (("r", "phi", "z"), ("1", "r", "1")),
    "esfericas": (("r", "theta", "phi"), ("1", "r", "r*sin(theta)")),
}
#: (x, y, z) en función de las coordenadas de cada sistema
A_CARTESIANAS = {
    "cartesianas": ("x", "y", "z"),
    "cilindricas": ("r*cos(phi)", "r*sin(phi)", "z"),
    "esfericas": ("r*sin(theta)*cos(phi)", "r*sin(theta)*sin(phi)", "r*cos(theta)"),
}
#: filas = vectores unitarios del sistema expresados en la base cartesiana
BASE = {
    "cartesianas": (("1", "0", "0"), ("0", "1", "0"), ("0", "0", "1")),
    "cilindricas": (("cos(phi)", "sin(phi)", "0"), ("-sin(phi)", "cos(phi)", "0"),
                    ("0", "0", "1")),
    "esfericas": (("sin(theta)*cos(phi)", "sin(theta)*sin(phi)", "cos(theta)"),
                  ("cos(theta)*cos(phi)", "cos(theta)*sin(phi)", "-sin(theta)"),
                  ("-sin(phi)", "cos(phi)", "0")),
}
NOMBRES = frozenset({"theta", "phi", "rho", "eps0"})

# Cómo lo escribe el alumno → el nombre interno de cada sistema. Se usa el mismo
# criterio que multiple._ALIAS para que los dos módulos hablen de una sola manera:
# θ/phi valen igual y ρ es el radio. Aquí el nombre interno del radio es r (en
# multiple es rho) y el ángulo acimutal de las cilíndricas es phi (en multiple es
# t, porque allí t es el parámetro, no el ángulo), así que se acepta cualquiera de
# las dos grafías y se normaliza a la de este módulo.
_ALIAS = {
    "cilindricas": {"θ": "phi", "theta": "phi", "φ": "phi"},
    "esfericas": {"θ": "theta", "φ": "phi", "ρ": "r", "rho": "r"},
}


def _con_alias(texto: str, sistema: str | None) -> str:
    if sistema is None or not isinstance(texto, str):
        return texto
    import re

    for a, b in _ALIAS.get(sistema, {}).items():
        texto = re.sub(rf"(?<![A-Za-z_]){a}(?![A-Za-z_0-9])", b, texto)
    return texto


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def leer(e, sistema: str | None = None) -> mx.Expr:
    if isinstance(e, mx.Expr):
        return e
    if isinstance(e, (int,)):
        return MI.leer(e)
    return mx.parse(_con_alias(str(e), sistema), nombres=NOMBRES)


def _sistema(nombre: str):
    if nombre not in SISTEMAS:
        raise _error("BAD_INPUT", f"sistema: {', '.join(SISTEMAS)}")
    u, h = SISTEMAS[nombre]
    return list(u), [leer(x) for x in h]


def _d(e: mx.Expr, v: str) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return MI._limpio(DM.differentiate(e, v))


def _txt(v) -> str:
    return "(" + ", ".join(mx.text(c) for c in v) + ")"


def _vec(F, n: int = 3, sistema: str | None = None) -> list[mx.Expr]:
    if not isinstance(F, (list, tuple)) or len(F) != n:
        raise _error("BAD_INPUT", f"un campo es una lista de {n} componentes")
    return [leer(c, sistema) for c in F]


# ---------------------------------------------------------------------------
# operadores con factores de escala
# ---------------------------------------------------------------------------


def gradiente(V, sistema: str = "cartesianas", trace: Trace | None = None) -> list[mx.Expr]:
    trace = trace if trace is not None else Trace()
    u, h = _sistema(sistema)
    V = leer(V, sistema)
    g = [MI._limpio(mx.Div(_d(V, ui), hi)) for ui, hi in zip(u, h)]
    trace.regla("op.grad", f"∇V = (1/hᵢ)·∂V/∂uᵢ en {sistema} = {_txt(g)}",
                why=f"factores de escala h = ({', '.join(mx.text(x) for x in h)})")
    _comprueba(None, g, sistema, "vector", trace, "∇V", escalar=V, op="grad")
    return g


def divergencia(F, sistema: str = "cartesianas", trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    u, h = _sistema(sistema)
    F = _vec(F, sistema=sistema)
    H = mx.Mul(mx.Mul(h[0], h[1]), h[2])
    terminos = []
    for i in range(3):
        otros = mx.Div(H, h[i])
        terminos.append(_d(MI._limpio(mx.Mul(F[i], otros)), u[i]))
    d = MI._limpio(mx.Div(_suma(terminos), H))
    trace.regla("op.div", f"∇·F = (1/h₁h₂h₃)·Σ ∂(Fᵢ·h₁h₂h₃/hᵢ)/∂uᵢ = {mx.text(d)}",
                why=f"en {sistema} el elemento de volumen es {mx.text(MI._limpio(H))}·du₁du₂du₃")
    _comprueba(None, d, sistema, "escalar", trace, "∇·F", campo=F, op="div")
    return d


def rotacional(F, sistema: str = "cartesianas", trace: Trace | None = None) -> list[mx.Expr]:
    trace = trace if trace is not None else Trace()
    u, h = _sistema(sistema)
    F = _vec(F, sistema=sistema)
    H = MI._limpio(mx.Mul(mx.Mul(h[0], h[1]), h[2]))
    hf = [MI._limpio(mx.Mul(h[i], F[i])) for i in range(3)]
    comp = []
    for i, j, k in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        num = mx.Sub(_d(hf[k], u[j]), _d(hf[j], u[k]))
        comp.append(MI._limpio(mx.Div(mx.Mul(h[i], num), H)))
    trace.regla("op.rot", f"∇×F = (1/h₁h₂h₃)·det[hᵢêᵢ; ∂/∂uᵢ; hᵢFᵢ] = {_txt(comp)}",
                why=f"rotacional con factores de escala en {sistema}")
    _comprueba(None, comp, sistema, "vector", trace, "∇×F", campo=F, op="rot")
    return comp


def laplaciano(V, sistema: str = "cartesianas", trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    u, h = _sistema(sistema)
    V = leer(V, sistema)
    H = mx.Mul(mx.Mul(h[0], h[1]), h[2])
    terminos = []
    for i in range(3):
        coef = MI._limpio(mx.Div(H, mx.Pow(h[i], mx.Num(2))))
        terminos.append(_d(MI._limpio(mx.Mul(coef, _d(V, u[i]))), u[i]))
    L = MI._limpio(mx.Div(_suma(terminos), H))
    trace.regla("op.laplaciano", f"∇²V = (1/H)·Σ ∂/∂uᵢ(H/hᵢ²·∂V/∂uᵢ) = {mx.text(L)}",
                why=f"laplaciano con factores de escala en {sistema} (H = h₁h₂h₃)")
    _comprueba(None, L, sistema, "escalar", trace, "∇²V", escalar=V, op="lap")
    return L


def _suma(xs):
    t = xs[0]
    for x in xs[1:]:
        t = mx.Add(t, x)
    return t


# ---------------------------------------------------------------------------
# segundo camino: cartesianas
# ---------------------------------------------------------------------------


def _puntos(sistema: str) -> list[dict[str, float]]:
    u, _ = _sistema(sistema)
    pts = []
    for k in range(6):
        vals = [0.7 + 0.31 * k, 0.4 + 0.17 * k, 0.3 + 0.23 * k]
        pts.append(dict(zip(u, vals)))
    return pts


def _cart_de_punto(sistema: str, p: dict) -> dict:
    xyz = [float(mx.valor_real(leer(e), p)) for e in A_CARTESIANAS[sistema]]
    return dict(zip(("x", "y", "z"), xyz))


def _base_en(sistema: str, p: dict) -> list[list[float]]:
    return [[float(mx.valor_real(leer(c), p)) for c in fila] for fila in BASE[sistema]]


def _comprueba(_, res, sistema, tipo, trace, nombre, campo=None, op=None, escalar=None):
    """Compara con el cálculo en cartesianas: el campo/función se pasa a cartesianas
    punto a punto con diferencias finitas centradas (camino independiente)."""
    if sistema == "cartesianas":
        trace.verificacion(f"op.{nombre}", f"{nombre} en cartesianas: derivadas exactas")
        return
    u, _ = _sistema(sistema)
    for e in ([escalar] if escalar is not None else []) + list(campo or []):
        sobran = mx.variables(e) - set(u)
        if sobran:
            # antes: INTERNAL «el segundo camino no se pudo evaluar»
            raise _error("BAD_INPUT", f"en {sistema} las coordenadas son {', '.join(u)}; "
                                      f"sobra {', '.join(sorted(sobran))}")
    fallos = 0
    comprobados = 0
    for p in _puntos(sistema):
        try:
            esperado = _numerico(sistema, p, op or ("grad" if tipo == "vector" else "lap"),
                                 campo, escalar, res)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            continue
        if esperado is None:
            continue
        obtenido = ([float(mx.valor_real(c, p)) for c in res] if isinstance(res, list)
                    else float(mx.valor_real(res, p)))
        a = obtenido if isinstance(obtenido, list) else [obtenido]
        b = esperado if isinstance(esperado, list) else [esperado]
        comprobados += 1
        if any(abs(x - y) > 1e-5 * max(1.0, abs(y)) for x, y in zip(a, b)):
            fallos += 1
    if comprobados < 3:
        raise _error("INTERNAL", f"{nombre}: el segundo camino no se pudo evaluar")
    if fallos:
        raise _error("INTERNAL", f"{nombre} no coincide con el cálculo en cartesianas")
    trace.verificacion(f"op.{nombre}_cart", f"{nombre} coincide con el cálculo en "
                       "cartesianas en 6 puntos (componentes pasadas por la matriz de base)",
                       why="camino independiente de los factores de escala")


def _numerico(sistema, p, op, campo, escalar, res):
    """Valor del operador en p calculado en cartesianas con diferencias finitas."""
    u, _ = _sistema(sistema)
    xyz = _cart_de_punto(sistema, p)
    inv = _inversa(sistema)

    def coords(c):                         # cartesianas → coordenadas del sistema
        return inv(c)

    def F_cart(c):
        q = coords(c)
        comps = [float(mx.valor_real(f, q)) for f in campo]
        B = _base_en(sistema, q)
        return [sum(comps[i] * B[i][j] for i in range(3)) for j in range(3)]

    def V_cart(c):
        return float(mx.valor_real(escalar if escalar is not None else res, coords(c)))
    hh = 1e-4
    base = [xyz["x"], xyz["y"], xyz["z"]]

    def dif(fn, j):                       # diferencia centrada de orden 4
        vals = []
        for k in (-2, -1, 1, 2):
            q = list(base)
            q[j] += k * hh
            vals.append(fn(q))
        return (vals[0] - 8 * vals[1] + 8 * vals[2] - vals[3]) / (12 * hh)
    if op == "grad":
        g = [dif(V_cart, j) for j in range(3)]
        B = _base_en(sistema, p)
        return [sum(B[i][j] * g[j] for j in range(3)) for i in range(3)]
    if op == "div":
        return sum(dif(lambda c, j=j: F_cart(c)[j], j) for j in range(3))
    if op == "rot":
        J = [[dif(lambda c, i=i: F_cart(c)[i], j) for j in range(3)] for i in range(3)]
        rc = [J[2][1] - J[1][2], J[0][2] - J[2][0], J[1][0] - J[0][1]]
        B = _base_en(sistema, p)
        return [sum(B[i][j] * rc[j] for j in range(3)) for i in range(3)]
    if op == "lap":
        h2 = 2e-3
        tot = 0.0
        for j in range(3):
            vals = []
            for k in (-2, -1, 0, 1, 2):
                q = list(base)
                q[j] += k * h2
                vals.append(V_cart(q))
            tot += (-vals[0] + 16 * vals[1] - 30 * vals[2] + 16 * vals[3] - vals[4]) / (12 * h2 ** 2)
        return tot if escalar is not None else None
    return None


def _inversa(sistema: str):
    def f(c):
        x, y, z = c
        if sistema == "cilindricas":
            return {"r": math.hypot(x, y), "phi": math.atan2(y, x), "z": z}
        if sistema == "esfericas":
            r = math.sqrt(x * x + y * y + z * z)
            return {"r": r, "theta": math.acos(z / r), "phi": math.atan2(y, x)}
        return {"x": x, "y": y, "z": z}
    return f


# ---------------------------------------------------------------------------
# controles, Poisson y cambio de base
# ---------------------------------------------------------------------------


def controles(F, V=None, sistema: str = "cartesianas", trace: Trace | None = None) -> None:
    """∇·(∇×F) = 0 y ∇×(∇V) = 0 (identidades que todo cálculo correcto cumple)."""
    trace = trace if trace is not None else Trace()
    d = divergencia(rotacional(F, sistema, Trace()), sistema, Trace())
    if not _es_cero(d):
        raise _error("INTERNAL", f"∇·(∇×F) = {mx.text(d)} ≠ 0")
    trace.verificacion("op.div_rot", "∇·(∇×F) = 0")
    if V is not None:
        r = rotacional(gradiente(V, sistema, Trace()), sistema, Trace())
        if not all(_es_cero(c) for c in r):
            raise _error("INTERNAL", "∇×(∇V) ≠ 0")
        trace.verificacion("op.rot_grad", "∇×(∇V) = 0")


def _es_cero(e: mx.Expr) -> bool:
    nombres = sorted(mx.variables(e))
    vistos = 0
    for k in range(10):
        env = {n: 0.61 + 0.27 * k + 0.13 * i for i, n in enumerate(nombres)}
        v = mx.valor_real(e, env)
        if v is None:
            continue
        if abs(v) > 1e-9:
            return False
        vistos += 1
    return vistos >= 3


def poisson(V, sistema: str = "cartesianas", trace: Trace | None = None) -> mx.Expr:
    """ρ = −ε₀·∇²V (el resultado lleva el símbolo eps0)."""
    trace = trace if trace is not None else Trace()
    L = laplaciano(V, sistema, trace)
    rho = MI._limpio(mx.Neg(mx.Mul(mx.Sym("eps0"), L)))
    trace.regla("op.poisson", f"∇²V = −ρ/ε₀ ⇒ ρ = −ε₀·∇²V = {mx.text(rho)}",
                why="ecuación de Poisson (Gauss diferencial con E = −∇V)")
    return rho


def cambio_base(F, de: str, a: str, punto: dict | None = None,
                trace: Trace | None = None) -> list[mx.Expr]:
    """Componentes de F (dadas en la base de ``de``) en la base de ``a``; con
    ``punto`` (en las coordenadas de ``de``) se evalúan ahí."""
    trace = trace if trace is not None else Trace()
    F = _vec(F, sistema=de)
    _sistema(de)
    _sistema(a)
    # a cartesianas: F_cart = Bᵀ·F
    B = [[leer(c) for c in fila] for fila in BASE[de]]
    cart = [MI._limpio(_suma([mx.Mul(F[i], B[i][j]) for i in range(3)])) for j in range(3)]
    if a == "cartesianas":
        out = cart
    else:
        # de cartesianas a ``a``: F_a = B_a·F_cart, con B_a escrita en las coordenadas
        # de ``de`` (se pasa por x, y, z)
        Ba = [[leer(c) for c in fila] for fila in BASE[a]]
        xyz = [leer(e) for e in A_CARTESIANAS[de]]
        if de != "cartesianas" and a != de:
            raise _no("pasa primero a cartesianas: cambio directo entre dos sistemas "
                      "curvilíneos distintos no implementado")
        out = [_suma([mx.Mul(Ba[i][j], cart[j]) for j in range(3)]) for i in range(3)]
        # las componentes cartesianas se escriben en las coordenadas nuevas
        nuevas = [leer(e) for e in A_CARTESIANAS[a]]
        out = [MI._limpio(_sustituye_xyz(c, nuevas)) for c in out]
        _ = xyz
    trace.regla("op.cambio_base", f"R = matriz con los unitarios de {de} en filas; "
                f"F_{a} = {_txt(out)}", why="la base es ortonormal: R⁻¹ = Rᵀ")
    _comprueba_base(de, trace)
    if punto is not None:
        env = {k: leer(v, de) for k, v in punto.items()}
        out = [MI._limpio(_sustituye(c, env)) for c in out]
        modulo_antes = math.sqrt(sum(float(mx.valor_real(_sustituye(c, env), {})) ** 2
                                     for c in F))
        modulo = math.sqrt(sum(float(mx.valor_real(c, {})) ** 2 for c in out))
        if abs(modulo - modulo_antes) > 1e-9 * max(1.0, modulo):
            raise _error("INTERNAL", "el módulo no se conserva")
        trace.verificacion("op.modulo", f"|F| = {modulo:.10g} en las dos bases")
    return out


def _sustituye_xyz(e: mx.Expr, nuevas: list[mx.Expr]) -> mx.Expr:
    tmp = {"x": "__x", "y": "__y", "z": "__z"}
    for c, t in tmp.items():
        e = mx.substitute(e, c, mx.Sym(t))
    for (c, t), v in zip(tmp.items(), nuevas):
        e = mx.substitute(e, t, v)
    return e


def _sustituye(e: mx.Expr, env: dict) -> mx.Expr:
    for k, v in env.items():
        e = mx.substitute(e, k, v)
    return e


def _comprueba_base(sistema: str, trace: Trace) -> None:
    for p in _puntos(sistema)[:3]:
        B = _base_en(sistema, p)
        for i in range(3):
            for j in range(3):
                dot = sum(B[i][k] * B[j][k] for k in range(3))
                if abs(dot - (1 if i == j else 0)) > 1e-12:
                    raise _error("INTERNAL", "la base no es ortonormal")
    trace.verificacion("op.ortogonal", "RᵀR = I (base ortonormal) comprobado")


# ---------------------------------------------------------------------------
# V dado ⇒ E, ρ y carga en una caja por los dos lados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Electrostatica:
    E: list[mx.Expr]
    rho: mx.Expr
    carga_volumen: object | None
    carga_flujo: object | None

    def texto(self) -> str:
        t = f"E = {_txt(self.E)}; ρ = {mx.text(self.rho)}"
        if self.carga_volumen is not None:
            t += f"; Q = ∭ρ dV = {self.carga_volumen.texto()}"
        if self.carga_flujo is not None:
            t += f"; ε₀∯E·dS = {self.carga_flujo.texto()}"
        return t


def caras_caja(x0, x1, y0, y1, z0, z1) -> list[dict]:
    """Las seis caras de una caja con la normal exterior."""
    def L(a, b, c, d):
        return [["u", a, b], ["v", c, d]]
    return [
        {"r": [str(x0), "u", "v"], "limites": L(y0, y1, z0, z1), "orientacion": -1},
        {"r": [str(x1), "u", "v"], "limites": L(y0, y1, z0, z1)},
        {"r": ["v", str(y0), "u"], "limites": L(z0, z1, x0, x1), "orientacion": -1},
        {"r": ["v", str(y1), "u"], "limites": L(z0, z1, x0, x1)},
        {"r": ["u", "v", str(z0)], "limites": L(x0, x1, y0, y1), "orientacion": -1},
        {"r": ["u", "v", str(z1)], "limites": L(x0, x1, y0, y1)},
    ]


def electrostatica(V, sistema: str = "cartesianas", caja=None,
                   trace: Trace | None = None) -> Electrostatica:
    """E = −∇V, ρ = −ε₀∇²V; con ``caja`` = [x0, x1, y0, y1, z0, z1] (V en
    cartesianas) la carga encerrada por ∭ρ dV y por ε₀∯E·dS sobre las seis caras."""
    from academic_core.domain.engineering.mathlab import vectorial as VE

    trace = trace if trace is not None else Trace()
    grad = gradiente(V, sistema, trace)
    E = [MI._limpio(mx.Neg(c)) for c in grad]
    trace.regla("op.E", f"E = −∇V = {_txt(E)}", why="campo electrostático conservativo")
    rho = poisson(V, sistema, trace)
    qv = qf = None
    if caja is not None:
        if sistema != "cartesianas":
            raise _no("la caja se da en cartesianas: escribe V en x, y, z")
        x0, x1, y0, y1, z0, z1 = caja
        # se integra ρ/ε₀ y se multiplica por eps0 al final (eps0 es un símbolo)
        rho_e = MI._limpio(mx.Neg(laplaciano(V, sistema, Trace())))
        qv = MI.iterada(rho_e, [["x", x0, x1], ["y", y0, y1], ["z", z0, z1]], trace)
        qf = VE.flujo([mx.text(c) for c in E], caras_caja(x0, x1, y0, y1, z0, z1), trace)
        if abs(qv.numerico - qf.numerico) > 1e-7 * max(1.0, abs(qv.numerico)):
            raise _error("INTERNAL", "∭ρ dV y ε₀∯E·dS no coinciden")
        trace.verificacion("op.gauss_caja", "∭(ρ/ε₀) dV = ∯E·dS: Gauss por los dos lados "
                           "(la carga es ε₀ por ese valor)")
    return Electrostatica(E, rho, qv, qf)


# ---------------------------------------------------------------------------
# cinemática intrínseca
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Intrinseca:
    v: list[mx.Expr]
    a: list[mx.Expr]
    rapidez: mx.Expr
    T: list[mx.Expr]
    a_t: mx.Expr
    a_n: mx.Expr
    kappa: mx.Expr
    radio: mx.Expr | None
    N: list[mx.Expr] | None

    def texto(self) -> str:
        t = (f"v = {_txt(self.v)}, |v| = {mx.text(self.rapidez)}, a = {_txt(self.a)}; "
             f"T = {_txt(self.T)}; a_t = {mx.text(self.a_t)}, a_n = {mx.text(self.a_n)}; "
             f"κ = {mx.text(self.kappa)}")
        if self.radio is not None:
            t += f", ρ = 1/κ = {mx.text(self.radio)}"
        if self.N is not None:
            t += f"; N = {_txt(self.N)}"
        return t


def _norma(v: list[mx.Expr]) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import vectorial as VE

    return VE._norma(v, [["t", 0.1, 3.0]]) if all(not mx.variables(c) - {"t"} for c in v) \
        else MI._limpio(mx.Root(2, _suma([mx.Pow(c, mx.Num(2)) for c in v])))


def intrinseca(r, t: str = "t", t0=None, trace: Trace | None = None) -> Intrinseca:
    """Para r(t) en ℝ² o ℝ³; con ``t0`` todo se evalúa en ese instante."""
    trace = trace if trace is not None else Trace()
    if not isinstance(r, (list, tuple)) or len(r) not in (2, 3):
        raise _error("BAD_INPUT", "r(t) con 2 o 3 componentes")
    r = [leer(c) for c in r]
    if len(r) == 2:
        r = r + [mx.Num(0)]
    v = [_d(c, t) for c in r]
    a = [_d(c, t) for c in v]
    trace.regla("cin.va", f"v = r′ = {_txt(v)}, a = r″ = {_txt(a)}")
    if t0 is not None:
        t0e = leer(t0)
        v = [MI._limpio(mx.substitute(c, t, t0e)) for c in v]
        a = [MI._limpio(mx.substitute(c, t, t0e)) for c in a]
        trace.regla("cin.instante", f"en {t} = {mx.text(t0e)}: v = {_txt(v)}, a = {_txt(a)}")
    rapidez = _norma(v)
    if t0 is not None and abs(float(mx.valor_real(rapidez, {}))) < 1e-14:
        raise _error("SINGULAR", "v = 0 en ese instante: no hay tangente (punto no regular)")
    T = [MI._limpio(mx.Div(c, rapidez)) for c in v]
    va = MI._limpio(_suma([mx.Mul(x, y) for x, y in zip(v, a)]))
    a_t = MI._limpio(mx.Div(va, rapidez))
    cruz = [mx.Sub(mx.Mul(v[1], a[2]), mx.Mul(v[2], a[1])),
            mx.Sub(mx.Mul(v[2], a[0]), mx.Mul(v[0], a[2])),
            mx.Sub(mx.Mul(v[0], a[1]), mx.Mul(v[1], a[0]))]
    cruz = [MI._limpio(c) for c in cruz]
    ncruz = _norma(cruz)
    a_n = MI._limpio(mx.Div(ncruz, rapidez))
    kappa = MI._limpio(mx.Div(ncruz, mx.Pow(rapidez, mx.Num(3))))
    trace.regla("cin.tangente", f"T = v/|v| = {_txt(T)}", why="|v| = " + mx.text(rapidez))
    trace.regla("cin.at", f"a_t = d|v|/dt = (v·a)/|v| = {mx.text(a_t)}",
                why="componente de a en la dirección de T")
    trace.regla("cin.an", f"a_n = |v × a|/|v| = {mx.text(a_n)}; κ = |r′ × r″|/|r′|³ = "
                f"{mx.text(kappa)}", why="a_n = κ·|v|²")
    radio = None
    N = None
    if t0 is not None:
        k = float(mx.valor_real(kappa, {}))
        if abs(k) > 1e-14:
            radio = MI._limpio(mx.Div(mx.Num(1), kappa))
            N = [MI._limpio(mx.Div(mx.Sub(a[i], mx.Mul(a_t, T[i])), a_n)) for i in range(3)]
            trace.regla("cin.normal", f"N = (a − a_t·T)/a_n = {_txt(N)}; radio de curvatura "
                        f"1/κ = {mx.text(radio)}")
        else:
            trace.regla("cin.recta", "κ = 0: movimiento rectilíneo en ese instante, sin N")
        at, an = float(mx.valor_real(a_t, {})), float(mx.valor_real(a_n, {}))
        am = math.sqrt(sum(float(mx.valor_real(c, {})) ** 2 for c in a))
        if abs(at * at + an * an - am * am) > 1e-9 * max(1.0, am * am):
            raise _error("INTERNAL", "a_t² + a_n² ≠ |a|²")
        trace.verificacion("cin.pitagoras", f"a_t² + a_n² = |a|² = {am * am:.10g}",
                           why="a = a_t·T + a_n·N con T ⟂ N")
    else:
        _comprueba_intrinseca(v, a, a_t, a_n, t, trace)
    return Intrinseca(v, a, rapidez, T, a_t, a_n, kappa, radio, N)


def _comprueba_intrinseca(v, a, a_t, a_n, t, trace) -> None:
    for k in range(5):
        env = {t: 0.3 + 0.41 * k}
        try:
            at, an = float(mx.valor_real(a_t, env)), float(mx.valor_real(a_n, env))
            am2 = sum(float(mx.valor_real(c, env)) ** 2 for c in a)
        except (TypeError, ValueError):
            continue
        if abs(at * at + an * an - am2) > 1e-8 * max(1.0, am2):
            raise _error("INTERNAL", "a_t² + a_n² ≠ |a|²")
    trace.verificacion("cin.pitagoras", "a_t² + a_n² = |a|² en 5 instantes")
