# SPDX-License-Identifier: MIT
"""ML-7: integrales de línea y de superficie; Green, Stokes y Gauss por los dos lados.

Curvas y superficies se dan parametrizadas (como en los exámenes):

- curva: ``{"r": ["cos(t)", "sin(t)", "t"], "t": "t", "a": 0, "b": "2*pi"}``; una
  curva a trozos es una lista de esas piezas, recorridas en orden;
- superficie: ``{"r": [...], "u": "u", "v": "v", "limites": [[u, a, b], [v, c, d]],
  "orientacion": 1 | -1}`` con normal r_u × r_v (o la opuesta con −1).

Cada integral se reduce a una iterada de :mod:`multiple` (exacta cuando hay
primitiva, con segundo camino numérico). Los teoremas calculan **los dos lados**
y los comparan: si no coinciden, se dice (orientación, hipótesis o datos).
Las hipótesis (C¹, región simplemente conexa, orientación coherente) se
comprueban donde se puede y se declaran donde no.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.engineering.mathlab import multiple as MI
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

COORDS = ("x", "y", "z")


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _d(e: mx.Expr, v: str) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return MI._limpio(DM.differentiate(e, v))


def _vec(F) -> list[mx.Expr]:
    if not isinstance(F, (list, tuple)) or len(F) not in (2, 3):
        raise _error("BAD_INPUT", "un campo o una parametrización es una lista de 2 o 3 "
                                  "componentes")
    return [MI.leer(c) for c in F]


def _txt(v) -> str:
    return "(" + ", ".join(mx.text(c) for c in v) + ")"


def _sustituye(e: mx.Expr, r: list[mx.Expr]) -> mx.Expr:
    """e(x, y, z) con (x, y, z) = r(t) (simultánea, por nombres temporales)."""
    tmp = {c: f"__{c}" for c in COORDS[:len(r)]}
    for c, t in tmp.items():
        e = mx.substitute(e, c, mx.Sym(t))
    for (c, t), rc in zip(tmp.items(), r):
        e = mx.substitute(e, t, rc)
    return e


def _suma(xs: list[mx.Expr]) -> mx.Expr:
    total = xs[0]
    for x in xs[1:]:
        total = mx.Add(total, x)
    return total


def _producto_escalar(a, b) -> mx.Expr:
    return _suma([mx.Mul(x, y) for x, y in zip(a, b)])


def _vectorial(a, b) -> list[mx.Expr]:
    return [mx.Sub(mx.Mul(a[1], b[2]), mx.Mul(a[2], b[1])),
            mx.Sub(mx.Mul(a[2], b[0]), mx.Mul(a[0], b[2])),
            mx.Sub(mx.Mul(a[0], b[1]), mx.Mul(a[1], b[0]))]


def _norma(v: list[mx.Expr], limites) -> mx.Expr:
    """|v| exacta: si la suma de cuadrados es un monomio cuadrado perfecto
    (sen²u, 2u², 4…) se saca de la raíz con el signo que tiene en la región."""
    from fractions import Fraction

    from academic_core.domain.engineering.mathlab import poly as P

    R = MI._limpio(_suma([mx.Pow(c, mx.Num(2)) for c in v]))
    raiz = mx.Root(2, R)
    largos = sorted(n for n in mx.variables(R) if len(n) > 1)
    libres = [c for c in "ABCDFGHJKLMNOPQRSTUVW" if c not in mx.variables(R)]
    ida = dict(zip(largos, libres))
    Rr = R
    for n, c in ida.items():
        Rr = mx.substitute(Rr, n, mx.Sym(c))
    try:
        p = P.as_poly(Rr)
    except Exception:  # noqa: BLE001
        return MI._limpio(raiz)
    resto = None
    if len(p) != 1:
        # factor monomio cuadrado común: √(u²·(4u² + 1)) = |u|·√(4u² + 1)
        nombres = {n for m in p for n, _ in m}
        comun = []
        for n in sorted(nombres):
            e = min(P.mono_exp(m, n) for m in p)
            if e >= 2:
                comun.append((n, e - e % 2))
        if not comun:
            return MI._limpio(raiz)
        cm = tuple(comun)
        resto = {P.mono_div(m, cm): cc for m, cc in p.items()}
        resto_e = P.to_expr(resto)
        for n, cc in ida.items():
            resto_e = mx.substitute(resto_e, cc, mx.Sym(n))
        p = {cm: Fraction(1)}
    (mono, c), = p.items()
    if c <= 0 or any(e % 2 for _, e in mono):
        return MI._limpio(raiz)
    rc = MI.leer(1)
    num, den = c.numerator, c.denominator
    import math
    rn, rd = math.isqrt(num), math.isqrt(den)
    k = (MI.leer(Fraction(rn, rd)) if rn * rn == num and rd * rd == den
         else mx.Root(2, MI.leer(c)))
    g = P.to_expr({tuple((n, e // 2) for n, e in mono): Fraction(1)}) if mono else rc
    for n, cc in ida.items():
        g = mx.substitute(g, cc, mx.Sym(n))
    signos = _signos(g, limites)
    if signos == {1} or signos == {1, 0}:
        out = mx.Mul(k, g)
    elif signos <= {-1, 0}:
        out = mx.Neg(mx.Mul(k, g))
    else:
        out = mx.Mul(k, mx.Call("abs", (g,)))
    if resto is not None:
        out = mx.Mul(out, mx.Root(2, resto_e))
    return MI._limpio(out)


def _signos(g: mx.Expr, limites) -> set[int]:
    """Signo de g en una rejilla de la región (límites constantes o dependientes)."""
    L = [(str(v), MI.leer(a), MI.leer(b)) for v, a, b in limites]
    out: set[int] = set()

    def rec(k: int, env: dict):
        if k < 0:
            val = mx.valor_real(g, env)
            if val is not None:
                out.add(0 if abs(val) < 1e-12 else (1 if val > 0 else -1))
            return
        v, a, b = L[k]
        fa, fb = float(mx.valor_real(a, env)), float(mx.valor_real(b, env))
        for i in range(1, 24):
            rec(k - 1, {**env, v: fa + (fb - fa) * i / 24})
    rec(len(L) - 1, {})
    return out


@dataclass(frozen=True)
class Valor:
    exacto: mx.Expr | None
    numerico: float

    def texto(self) -> str:
        return MI.Resultado(self.exacto, self.numerico, True).texto()


def _suma_valores(vals: list[MI.Resultado]) -> Valor:
    num = sum(v.numerico for v in vals)
    if all(v.exacto is not None for v in vals):
        return Valor(MI._limpio(_suma([v.exacto for v in vals])), num)
    return Valor(None, num)


# ---------------------------------------------------------------------------
# operadores
# ---------------------------------------------------------------------------


def rotacional(F, trace: Trace | None = None) -> list[mx.Expr]:
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    if len(F) == 2:
        r = [MI._limpio(mx.Sub(_d(F[1], "x"), _d(F[0], "y")))]
        trace.regla("vect.rot2", f"∂Q/∂x − ∂P/∂y = {mx.text(r[0])}",
                    why="rotacional escalar en el plano (lo que integra Green)")
        return r
    P, Q, R = F
    r = [MI._limpio(mx.Sub(_d(R, "y"), _d(Q, "z"))), MI._limpio(mx.Sub(_d(P, "z"), _d(R, "x"))),
         MI._limpio(mx.Sub(_d(Q, "x"), _d(P, "y")))]
    trace.regla("vect.rot", f"∇ × F = (R_y − Q_z, P_z − R_x, Q_x − P_y) = {_txt(r)}")
    return r


def divergencia(F, trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    d = MI._limpio(_suma([_d(c, v) for c, v in zip(F, COORDS)]))
    trace.regla("vect.div", f"∇ · F = {mx.text(d)}")
    return d


def _es_cero(e: mx.Expr) -> bool:
    from academic_core.domain.engineering.mathlab import verify as V

    try:
        iguales, _, _ = V.check_equivalence(e, mx.Num(0))
        if iguales:
            return True
    except Exception:  # noqa: BLE001
        pass
    nombres = sorted(mx.variables(e))
    vistos = 0
    for k in range(12):
        env = {n: 0.37 + 0.211 * k - 0.13 * i for i, n in enumerate(nombres)}
        v = mx.valor_real(e, env)
        if v is None:
            continue
        if abs(v) > 1e-9:
            return False
        vistos += 1
    return vistos >= 4


# ---------------------------------------------------------------------------
# campos conservativos
# ---------------------------------------------------------------------------


def potencial(F, trace: Trace | None = None) -> mx.Expr:
    """φ con ∇φ = F: rotacional nulo comprobado y φ por integración sucesiva."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    n = len(F)
    rot = rotacional(F, trace)
    if not all(_es_cero(c) for c in rot):
        trace.regla("vect.no_conservativo", "∇ × F ≠ 0: F no es conservativo",
                    why="un gradiente tiene rotacional nulo (Schwarz)")
        raise _error("NOT_CONSERVATIVE", f"∇ × F = {_txt(rot)} ≠ 0: F no es un gradiente")
    trace.hipotesis("vect.dominio", "dominio simplemente conexo",
                    "rot F = 0 solo garantiza potencial global si el dominio no tiene "
                    "agujeros; si F tiene singularidades (p. ej. en el eje), el potencial "
                    "vale en cada región simplemente conexa")
    vs = COORDS[:n]
    phi = MI.primitiva(F[0], vs[0], trace)
    for k in range(1, n):
        resto = MI._limpio(mx.Sub(F[k], _d(phi, vs[k])))
        if any(v in mx.variables(resto) for v in vs[:k]):
            raise _error("INTERNAL", "el resto depende de variables ya integradas")
        trace.regla("vect.potencial_paso", f"∂φ/∂{vs[k]} = F_{vs[k]} ⇒ g′({vs[k]}) = {mx.text(resto)}",
                    why="lo que falta de la componente solo puede depender de las variables "
                        "que quedan")
        if not _es_cero(resto):
            phi = MI._limpio(mx.Add(phi, MI.primitiva(resto, vs[k], trace)))
    for c, v in zip(F, vs):
        if not _es_cero(MI._limpio(mx.Sub(_d(phi, v), c))):
            raise _error("INTERNAL", f"∂φ/∂{v} ≠ F_{v}")
    trace.verificacion("vect.grad_phi", f"∇φ = F comprobado con φ = {mx.text(phi)}")
    return phi


# ---------------------------------------------------------------------------
# integrales de línea
# ---------------------------------------------------------------------------


def _piezas(curva) -> list[dict]:
    piezas = curva if isinstance(curva, list) else [curva]
    out = []
    for p in piezas:
        if not isinstance(p, dict) or "r" not in p:
            raise _error("BAD_INPUT", "cada pieza de curva es {'r': [...], 't', 'a', 'b'}")
        out.append({"r": _vec(p["r"]), "t": str(p.get("t", "t")),
                    "a": MI.leer(p.get("a", 0)), "b": MI.leer(p.get("b", 1))})
    return out


def circulacion(F, curva, trace: Trace | None = None) -> Valor:
    """∫_C F·dr = Σ ∫ F(r(t))·r′(t) dt."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    vals = []
    for k, p in enumerate(_piezas(curva)):
        r, t = p["r"], p["t"]
        if len(r) != len(F):
            raise _error("BAD_INPUT", "el campo y la curva tienen dimensiones distintas")
        dr = [_d(c, t) for c in r]
        integrando = MI._limpio(_producto_escalar([_sustituye(c, r) for c in F], dr))
        trace.regla("vect.linea", f"pieza {k + 1}: r({t}) = {_txt(r)}, r′ = {_txt(dr)}, "
                    f"F(r)·r′ = {mx.text(integrando)}",
                    why="∫ F·dr = ∫ F(r(t))·r′(t) dt sobre el parámetro")
        vals.append(MI.iterada(integrando, [[t, p["a"], p["b"]]], trace))
    v = _suma_valores(vals)
    trace.regla("vect.circulacion", f"∫ F·dr = {v.texto()}")
    return v


def linea_escalar(f, curva, trace: Trace | None = None) -> Valor:
    """∫_C f ds = Σ ∫ f(r(t))·|r′(t)| dt."""
    trace = trace if trace is not None else Trace()
    f = MI.leer(f)
    vals = []
    for k, p in enumerate(_piezas(curva)):
        r, t = p["r"], p["t"]
        dr = [_d(c, t) for c in r]
        norma = _norma(dr, [[t, p["a"], p["b"]]])
        integrando = MI._limpio(mx.Mul(_sustituye(f, r), norma))
        trace.regla("vect.ds", f"pieza {k + 1}: |r′({t})| = {mx.text(norma)}, "
                    f"f(r)·|r′| = {mx.text(integrando)}", why="ds = |r′(t)| dt")
        vals.append(MI.iterada(integrando, [[t, p["a"], p["b"]]], trace))
    return _suma_valores(vals)


def circulacion_por_potencial(F, curva, trace: Trace | None = None) -> Valor:
    """Segundo camino para un campo conservativo: φ(final) − φ(inicio)."""
    trace = trace if trace is not None else Trace()
    phi = potencial(F, trace)
    piezas = _piezas(curva)
    ini = [MI._limpio(mx.substitute(c, piezas[0]["t"], piezas[0]["a"])) for c in piezas[0]["r"]]
    fin = [MI._limpio(mx.substitute(c, piezas[-1]["t"], piezas[-1]["b"])) for c in piezas[-1]["r"]]
    a = MI._limpio(_sustituye(phi, ini))
    b = MI._limpio(_sustituye(phi, fin))
    val = MI._limpio(mx.Sub(b, a))
    trace.regla("vect.barrow_linea", f"φ{_txt(fin)} − φ{_txt(ini)} = {mx.text(val)}",
                why="teorema fundamental de las integrales de línea")
    return Valor(val, float(mx.valor_real(val, {})))


# ---------------------------------------------------------------------------
# integrales de superficie
# ---------------------------------------------------------------------------


def _superficie(S) -> dict:
    if not isinstance(S, dict) or "r" not in S or "limites" not in S:
        raise _error("BAD_INPUT", "superficie: {'r': [x, y, z], 'u', 'v', 'limites', "
                                  "'orientacion'}")
    r = _vec(S["r"])
    if len(r) != 3:
        raise _error("BAD_INPUT", "una superficie vive en ℝ³: tres componentes")
    lim = S["limites"]
    u = str(S.get("u", lim[0][0]))
    v = str(S.get("v", lim[1][0]))
    o = int(S.get("orientacion", 1))
    if o not in (1, -1):
        raise _error("BAD_INPUT", "orientacion = 1 o −1")
    return {"r": r, "u": u, "v": v, "limites": lim, "o": o}


def _normal(S: dict, trace: Trace) -> list[mx.Expr]:
    ru = [_d(c, S["u"]) for c in S["r"]]
    rv = [_d(c, S["v"]) for c in S["r"]]
    N = [MI._limpio(c if S["o"] > 0 else mx.Neg(c)) for c in _vectorial(ru, rv)]
    trace.regla("vect.normal", f"r_{S['u']} = {_txt(ru)}, r_{S['v']} = {_txt(rv)}, "
                f"N = {'' if S['o'] > 0 else '−'}r_{S['u']} × r_{S['v']} = {_txt(N)}",
                why="vector normal de la parametrización (con la orientación pedida)")
    return N


def flujo(F, S, trace: Trace | None = None) -> Valor:
    """∬_S F·dS = ∬ F(r(u,v))·N du dv."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    piezas = S if isinstance(S, list) else [S]
    vals = []
    for k, Sk in enumerate(piezas):
        Sk = _superficie(Sk)
        N = _normal(Sk, trace)
        integrando = MI._limpio(_producto_escalar([_sustituye(c, Sk["r"]) for c in F], N))
        trace.regla("vect.flujo", f"superficie {k + 1}: F(r)·N = {mx.text(integrando)}",
                    why="dS = N du dv con N = r_u × r_v")
        vals.append(MI.iterada(integrando, Sk["limites"], trace))
    v = _suma_valores(vals)
    trace.regla("vect.flujo_total", f"∬ F·dS = {v.texto()}")
    return v


def superficie_escalar(f, S, trace: Trace | None = None) -> Valor:
    """∬_S f dS = ∬ f(r)·|N| du dv (área con f = 1)."""
    trace = trace if trace is not None else Trace()
    f = MI.leer(f)
    piezas = S if isinstance(S, list) else [S]
    vals = []
    for Sk in piezas:
        Sk = _superficie(Sk)
        N = _normal(Sk, trace)
        norma = _norma(N, Sk["limites"])
        integrando = MI._limpio(mx.Mul(_sustituye(f, Sk["r"]), norma))
        trace.regla("vect.dS", f"|N| = {mx.text(norma)}, f·|N| = {mx.text(integrando)}",
                    why="dS = |r_u × r_v| du dv")
        vals.append(MI.iterada(integrando, Sk["limites"], trace))
    return _suma_valores(vals)


# ---------------------------------------------------------------------------
# teoremas: los dos lados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Teorema:
    nombre: str
    lado_a: tuple[str, Valor]
    lado_b: tuple[str, Valor] | None
    coinciden: bool | None

    def texto(self) -> str:
        t = f"{self.lado_a[0]} = {self.lado_a[1].texto()}"
        if self.lado_b is not None:
            t += f"; {self.lado_b[0]} = {self.lado_b[1].texto()}"
            t += "; coinciden" if self.coinciden else "; NO coinciden"
        return t


def _compara(nombre, a, b, trace) -> Teorema:
    if b is None:
        return Teorema(nombre, a, None, None)
    ok = abs(a[1].numerico - b[1].numerico) <= 1e-7 * max(1.0, abs(a[1].numerico))
    if ok:
        trace.verificacion(f"vect.{nombre.lower()}", f"{a[0]} = {b[0]}: los dos lados coinciden",
                           why=f"{nombre} comprobado calculando las dos integrales")
    else:
        trace.aviso(f"vect.{nombre.lower()}_discrepa",
                    f"{a[0]} ≈ {a[1].numerico:.10g} pero {b[0]} ≈ {b[1].numerico:.10g}: revisa "
                    "orientación, que la frontera sea completa o las hipótesis (C¹, "
                    "singularidades dentro de la región)")
    return Teorema(nombre, a, b, ok)


def _singularidades(F, trace) -> None:
    """Aviso si alguna componente tiene denominador (posible singularidad dentro)."""
    for c in F:
        if any(isinstance(n, mx.Div) and mx.variables(n.right) for n in MI._nodos(c)):
            trace.hipotesis("vect.c1", "F de clase C¹ en toda la región",
                            f"{mx.text(c)} tiene denominador: comprueba que no se anula "
                            "dentro (si se anula, el teorema no aplica tal cual)")
            return
    trace.hipotesis("vect.c1", "F de clase C¹", "componentes polinómicas o elementales sin "
                    "denominador: C¹ en todo el espacio")


def green(F, region, sistema: str = "cartesianas", borde=None,
          trace: Trace | None = None) -> Teorema:
    """∮_C P dx + Q dy = ∬_D (Q_x − P_y) dA (C con orientación positiva)."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    if len(F) != 2:
        raise _error("BAD_INPUT", "Green es en el plano: F = [P, Q]")
    _singularidades(F, trace)
    trace.hipotesis("vect.green", "D acotada con frontera C¹ a trozos recorrida en sentido "
                    "positivo (la región a la izquierda)", "la da el enunciado")
    rot = rotacional(F, trace)[0]
    dobles = (MI.iterada(rot, region, trace) if sistema == "cartesianas"
              else MI.en_coordenadas(rot, sistema, region, trace))
    a = ("∬ (Q_x − P_y) dA", Valor(dobles.exacto, dobles.numerico))
    b = ("∮ F·dr", circulacion(F, borde, trace)) if borde else None
    return _compara("Green", a, b, trace)


def stokes(F, S, borde=None, trace: Trace | None = None) -> Teorema:
    """∬_S (∇×F)·dS = ∮_∂S F·dr (borde orientado con la normal: regla de la mano derecha)."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    if len(F) != 3:
        raise _error("BAD_INPUT", "Stokes es en ℝ³: F = [P, Q, R]")
    _singularidades(F, trace)
    trace.hipotesis("vect.stokes", "S orientable, borde orientado según la normal (mano "
                    "derecha)", "la normal es r_u × r_v por la orientación dada")
    rot = rotacional(F, trace)
    a = ("∬ (∇×F)·dS", flujo(rot, S, trace))
    b = ("∮ F·dr", circulacion(F, borde, trace)) if borde else None
    return _compara("Stokes", a, b, trace)


def gauss(F, region, sistema: str = "cartesianas", superficies=None,
          trace: Trace | None = None) -> Teorema:
    """∭_V ∇·F dV = ∯_∂V F·dS (normal exterior)."""
    trace = trace if trace is not None else Trace()
    F = _vec(F)
    if len(F) != 3:
        raise _error("BAD_INPUT", "Gauss es en ℝ³: F = [P, Q, R]")
    _singularidades(F, trace)
    trace.hipotesis("vect.gauss", "V acotado, frontera cerrada a trozos con normal exterior",
                    "cada tapa de la frontera tiene que ir con la normal hacia fuera")
    d = divergencia(F, trace)
    triple = (MI.iterada(d, region, trace) if sistema == "cartesianas"
              else MI.en_coordenadas(d, sistema, region, trace))
    a = ("∭ ∇·F dV", Valor(triple.exacto, triple.numerico))
    b = ("∯ F·dS", flujo(F, superficies, trace)) if superficies else None
    return _compara("Gauss", a, b, trace)
