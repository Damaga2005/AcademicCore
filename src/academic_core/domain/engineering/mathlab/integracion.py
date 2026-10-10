# SPDX-License-Identifier: MIT
"""Primitivas más allá del motor E0.1: partes, cambio de variable y funciones
especiales, cada resultado comprobado derivando.

Orden de estrategias (la primera que da una primitiva verificada gana):

1. E0.1 y sus ayudas (constantes fuera, término a término, linealización de
   potencias trigonométricas, sustitución trigonométrica): :func:`multiple.primitiva`;
2. **partes** con LIATE (u = logaritmo, inversa trigonométrica, algebraica,
   trigonométrica, exponencial), recursiva, también **cíclica** (eˣ·cos x): si la
   integral reaparece multiplicada por c, I = (lo obtenido)/(1 − c);
3. **cambio de variable** u = g(x) con g tomada de la propia expresión (argumentos
   de funciones, radicandos, exponentes, denominadores): si f/g′ se escribe solo
   con u (o invirtiendo g), ∫ f dx = ∫ H(u) du;
4. **funciones especiales** cuando no hay primitiva elemental: e^(±a x²) → erf/erfi,
   sen(ax)/x → Si, cos(ax)/x → Ci, e^(ax)/x → Ei, sen(ax²) y cos(ax²) → Fresnel,
   1/ln x → Ei(ln x); el coeficiente se ajusta y se comprueba derivando.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
from collections.abc import Iterator
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

MAX_PROFUNDIDAD = 4
MAX_SEGUNDOS = 8.0

# El plazo de CPU vive en un ContextVar, no en una global: cada pestaña de la
# interfaz calcula en su propio hilo y un ContextVar es por hilo, así que dos
# cálculos simultáneos ya no se pisan ni se amplian el plazo el uno al otro.
_PLAZO: contextvars.ContextVar[float] = contextvars.ContextVar("mathlab_plazo", default=0.0)


def _fijar_plazo(momento: float) -> None:
    _PLAZO.set(momento)


def _agotado() -> bool:
    return time.monotonic() > _PLAZO.get()


@contextlib.contextmanager
def _plazo_acortado(minimo: float = 0.5) -> Iterator[None]:
    """Da a un subcálculo como mucho la mitad del plazo que queda (nunca menos de `minimo`)."""
    anterior = _PLAZO.get()
    ahora = time.monotonic()
    _PLAZO.set(min(anterior, ahora + max(minimo, (anterior - ahora) / 2)))
    try:
        yield
    finally:
        _PLAZO.set(anterior)


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _limpio(e):
    from academic_core.domain.engineering.mathlab import multiple as MI

    return MI._limpio(e)


def _d(e, v):
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    try:
        return _limpio(DM.differentiate(e, v))
    except Exception:  # noqa: BLE001
        return _limpio(DM.derivada_directa(e, v))


def comprueba(F: mx.Expr, f: mx.Expr, var: str) -> bool:
    """F′ = f: exacta si se puede; si no, en 12 puntos con tolerancia relativa 1e-9."""
    from academic_core.domain.engineering.mathlab import verify as V

    try:
        dF = _d(F, var)
    except Exception:  # noqa: BLE001
        return False
    try:
        iguales, _, _ = V.check_equivalence(dF, f)
        if iguales:
            return True
    except Exception:  # noqa: BLE001
        pass
    nombres = sorted(mx.variables(f) | mx.variables(dF) | {var})
    buenos = 0
    for k in range(24):
        signo = -1 if k % 3 == 2 else 1
        env = {n: signo * (0.13 + 0.117 * k + 0.029 * i) for i, n in enumerate(nombres)}
        try:
            a, b = mx.valor_real(dF, env), mx.valor_real(f, env)
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
        if a is None or b is None:
            continue
        if abs(a - b) > 1e-9 * max(1.0, abs(b)):
            return False
        buenos += 1
    return buenos >= 6


def _sec_lineal(e: mx.Expr, var: str):
    """(c, nombre, u) si e = c·sec(u) o c·csc(u) con u = a·x + b."""
    from academic_core.domain.engineering.mathlab import cuasipolinomios as Q

    c: mx.Expr = mx.Num(1)
    n = e
    if isinstance(n, mx.Neg):
        c, n = mx.Num(-1), n.arg
    if isinstance(n, mx.Mul) and not mx.depends(n.left, var):
        c, n = mx.Mul(c, n.left), n.right
    if isinstance(n, mx.Mul) and not mx.depends(n.right, var):
        c, n = mx.Mul(c, n.right), n.left
    if isinstance(n, mx.Div) and not mx.depends(n.left, var) and isinstance(n.right, mx.Call) \
            and n.right.name in ("cos", "sin"):
        c = mx.Mul(c, n.left)
        n = mx.Call("sec" if n.right.name == "cos" else "csc", n.right.args)
    if isinstance(n, mx.Call) and n.name in ("sec", "csc"):
        lin = Q._lineal(n.args[0], var)
        if lin is not None and not Q.es_cero(lin[0]):
            return c, n.name, n.args[0], lin[0]
    return None


def _tabla_sec(f: mx.Expr, var: str, profundidad: int):
    """∫ de sumas con términos c·sec(ax + b), c·csc(ax + b) (el resto, por primitiva)."""
    terminos = []

    def aplana(n, signo):
        if isinstance(n, mx.Add):
            aplana(n.left, signo)
            aplana(n.right, signo)
        elif isinstance(n, mx.Sub):
            aplana(n.left, signo)
            aplana(n.right, -signo)
        elif isinstance(n, mx.Neg):
            aplana(n.arg, -signo)
        else:
            terminos.append(n if signo > 0 else mx.Neg(n))
    aplana(f, 1)
    if not any(_sec_lineal(t, var) for t in terminos):
        return None
    total = None
    for t in terminos:
        sl = _sec_lineal(t, var)
        if sl is None:
            try:
                F = primitiva(t, var, Trace(), profundidad + 1)
            except UnsupportedError:
                return None
        else:
            c, nombre, u, a = sl
            if nombre == "sec":
                arg = mx.Add(mx.Call("sec", (u,)), mx.Call("tan", (u,)))
                F = mx.Mul(mx.Div(c, a), mx.Call("ln", (mx.Call("abs", (arg,)),)))
            else:
                arg = mx.Add(mx.Call("csc", (u,)), mx.Call("cot", (u,)))
                F = mx.Neg(mx.Mul(mx.Div(c, a), mx.Call("ln", (mx.Call("abs", (arg,)),))))
        total = F if total is None else mx.Add(total, F)
    return _limpio(total)


def primitiva(f: mx.Expr, var: str, trace: Trace | None = None, profundidad: int = 0
              ) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    if profundidad == 0:
        _fijar_plazo(time.monotonic() + MAX_SEGUNDOS)
    elif _agotado():
        raise _no("tiempo agotado buscando la primitiva")
    if profundidad > MAX_PROFUNDIDAD:
        raise _no("demasiadas integraciones anidadas")
    f = _limpio(f)
    from academic_core.domain.engineering.mathlab import multiple as MI

    tabla = _tabla_sec(f, var, profundidad)
    if tabla is not None and comprueba(tabla, f, var):
        trace.regla("integral.tabla_sec", f"∫ {mx.text(f)} d{var} = {mx.text(tabla)}",
                    why="tabla: ∫sec u = ln|sec u + tan u|, ∫csc u = −ln|csc u + cot u| "
                        "(u lineal), comprobada derivando")
        return tabla
    try:
        return MI.primitiva(f, var, trace)
    except UnsupportedError:
        pass

    for nombre, estrategia in (("especial", _especial), ("cambio", _cambio),
                               ("trigonometrica", _trigonometrica), ("partes", _partes)):
        t = Trace()
        # 'cambio' es la más cara: se le acorta el plazo para que no se lo coma todo
        acotado = _plazo_acortado() if nombre == "cambio" else contextlib.nullcontext()
        with acotado:
            try:
                F = estrategia(f, var, t, profundidad)
            except (UnsupportedError, ValidationError, ZeroDivisionError, ValueError):
                F = None
        if F is not None:
            F = _limpio(F)
            if comprueba(F, f, var):
                for paso in t:
                    trace.steps.append(paso)
                trace.regla("integral.comprobada", f"∫ {mx.text(f)} d{var} = {mx.text(F)}",
                            why="comprobada derivando: F′ = f")
                return F
    raise _no(f"sin primitiva de {mx.text(f)} en d{var}")


# ---------------------------------------------------------------------------
# partes
# ---------------------------------------------------------------------------


def _factores(e):
    from academic_core.domain.engineering.mathlab import limite as LM

    return LM._factores(e)


def _liate(f: mx.Expr, var: str) -> int:
    """0 log, 1 inversa trig, 2 algebraica, 3 trig, 4 exponencial."""
    if isinstance(f, mx.Call):
        if f.name in ("ln", "log", "log10"):
            return 0
        if f.name in ("asin", "acos", "atan", "asinh", "acosh", "atanh"):
            return 1
        if f.name in ("sin", "cos", "tan", "sec", "csc", "cot", "sinh", "cosh"):
            return 3
        if f.name == "exp":
            return 4
    if isinstance(f, mx.Pow):
        if isinstance(f.base, mx.Call) and f.base.name in ("ln", "log"):
            return 0
        if isinstance(f.base, mx.Call) and f.base.name in ("asin", "acos", "atan"):
            return 1
        if var in mx.variables(f.exponent):
            return 4
        if isinstance(f.base, mx.Call) and f.base.name in ("sin", "cos"):
            return 3
    return 2


def _partes(f: mx.Expr, var: str, trace: Trace, prof: int) -> mx.Expr | None:
    nums, dens = _factores(f)
    if dens and any(var in mx.variables(d) for d in dens):
        # cocientes: u = todo salvo un factor exponencial/trig integrable
        pass
    from academic_core.domain.engineering.mathlab import limite as LM

    opciones = []
    for i in sorted(range(len(nums)), key=lambda i: _liate(nums[i], var)):
        u = nums[i]
        if var not in mx.variables(u):
            continue
        resto = [g for j, g in enumerate(nums) if j != i]
        opciones.append((u, LM._reconstruye(resto, dens)))
        # xᵏ = x^(k−1)·x: el x que sobra va con dv (x²·e^(−x²), x³·e^(x²))
        k = mx.exact_integer(u.exponent) if isinstance(u, mx.Pow) and \
            u.base == mx.Sym(var) else None
        if k is not None and k >= 2:
            u2 = mx.Sym(var) if k == 2 else mx.Pow(mx.Sym(var), mx.Num(Fraction(k - 1)))
            opciones.append((u2, LM._reconstruye(resto + [mx.Sym(var)], dens)))

    for u, dv in opciones:
        if _agotado():
            return None
        if dv == f:
            continue
        try:
            v = _primitiva_simple(dv, var, prof)
        except UnsupportedError:
            continue
        du = _d(u, var)
        nuevo = _limpio(mx.Mul(v, du))
        trace.regla("integral.partes", f"u = {mx.text(u)}, dv = {mx.text(dv)} d{var}: "
                    f"du = {mx.text(du)} d{var}, v = {mx.text(v)}",
                    why="LIATE: u es el factor que más se simplifica al derivar")
        # ¿cíclica? ∫ v du = c·∫ f
        c = _proporcion(nuevo, f, var)
        if c is not None and c != 1:
            I = _limpio(mx.Div(mx.Mul(u, v), mx.Num(1 + c)))
            trace.regla("integral.ciclica", f"∫ v du = {c}·I ⇒ I = u·v/(1 + {c})",
                        why="la integral reaparece: se despeja")
            return I
        with _plazo_acortado():
            try:
                resto_int = primitiva(nuevo, var, Trace(), prof + 1)
            except UnsupportedError:
                # segunda vuelta de partes para la cíclica (eˣ·sen x)
                r = _partes_ciclica(u, v, nuevo, f, var, trace, prof)
                if r is not None:
                    return r
                continue
        return mx.Sub(mx.Mul(u, v), resto_int)
    return None


def _partes_ciclica(u, v, nuevo, f, var, trace, prof):
    """∫ f = u v − ∫ nuevo; si nuevo = u₂·dv₂ con ∫ nuevo = u₂v₂ − c·∫ f."""
    from academic_core.domain.engineering.mathlab import limite as LM

    nums, dens = _factores(nuevo)
    for i in sorted(range(len(nums)), key=lambda k: _liate(nums[k], var)):
        u2 = nums[i]
        if var not in mx.variables(u2):
            continue
        dv2 = LM._reconstruye([g for j, g in enumerate(nums) if j != i], dens)
        try:
            v2 = _primitiva_simple(dv2, var, prof)
        except UnsupportedError:
            continue
        resto = _limpio(mx.Mul(v2, _d(u2, var)))
        c = _proporcion(resto, f, var)
        if c is not None:
            # I = u v − (u₂ v₂ − c I) ⇒ I (1 − c) = u v − u₂ v₂
            if c == 1:
                continue
            trace.regla("integral.ciclica", f"tras dos veces partes la integral reaparece "
                        f"con factor {c}: I·(1 − {c}) = u·v − u₂·v₂",
                        why="integral cíclica: se despeja I")
            return mx.Div(mx.Sub(mx.Mul(u, v), mx.Mul(u2, v2)), mx.Num(1 - c))
    return None


def _proporcion(a: mx.Expr, b: mx.Expr, var: str) -> Fraction | None:
    """c racional con a = c·b (comprobado en varios puntos)."""
    ratios = []
    for k in range(5):
        x = 0.31 + 0.27 * k
        try:
            va, vb = mx.valor_real(a, {var: x}), mx.valor_real(b, {var: x})
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
        if va is None or vb is None or abs(vb) < 1e-12:
            return None
        ratios.append(va / vb)
    c = Fraction(ratios[0]).limit_denominator(1000)
    if all(abs(r - float(c)) < 1e-10 * max(1.0, abs(r)) for r in ratios):
        return c
    return None


def _primitiva_simple(e, var, prof):
    """La primitiva de dv: solo el motor directo (sin partes), para no ciclar."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        return MI.primitiva(e, var, Trace())
    except UnsupportedError:
        if prof >= MAX_PROFUNDIDAD - 1:
            raise
        return _cambio(e, var, Trace(), prof + 1) or _falla()


def _falla():
    raise _no("sin primitiva")


# ---------------------------------------------------------------------------
# cambio de variable
# ---------------------------------------------------------------------------


def _subexpresiones(e: mx.Expr, var: str):
    vistos = set()

    def rec(n):
        cands = []
        if isinstance(n, mx.Call):
            cands.extend(n.args)
        if isinstance(n, mx.Root):
            cands.append(n.radicand)
            cands.append(n)
        if isinstance(n, mx.Pow):
            if var in mx.variables(n.exponent):
                cands.append(n.exponent)
                cands.append(n)
            else:
                cands.append(n.base)
                k = mx.exact_integer(n.exponent)
                if n.base == mx.Sym(var) and k is not None and k >= 2:
                    for m in range(2, k + 1):
                        if k % m == 0:
                            cands.append(mx.Pow(mx.Sym(var), mx.Num(Fraction(m))))
        if isinstance(n, mx.Div):
            cands.append(n.right)
            if var in mx.variables(n.right):
                cands.append(mx.Div(mx.Num(Fraction(1)), mx.Sym(var)))    # u = 1/x
        if isinstance(n, mx.Call) and n.name in ("exp", "ln", "sin", "cos", "tan", "atan",
                                                 "asin"):
            cands.append(n)
        for c in cands:
            if var in mx.variables(c):
                t = mx.text(c)
                if t not in vistos and t != var:
                    vistos.add(t)
                    yield c
        for h in ("left", "right", "arg", "base", "exponent", "radicand"):
            c = getattr(n, h, None)
            if isinstance(c, mx.Expr):
                yield from rec(c)
        for a in getattr(n, "args", ()) or ():
            if isinstance(a, mx.Expr):
                yield from rec(a)
    yield from rec(e)


def _inversa(g: mx.Expr, var: str, U: mx.Expr) -> list[mx.Expr]:
    """Candidatas a x = g⁻¹(u): las de multiple._invierte y, para g = ᵏ√p(x) con p
    de grado ≤ 2, las de p(x) = uᵏ; para exp/ln de algo lineal, log/exp de u."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import raices as RZ

    out = list(MI._invierte(g, var, U))
    if isinstance(g, mx.Root):
        out.extend(MI._invierte(g.radicand, var, mx.Pow(U, mx.Num(Fraction(g.degree)))))
    if isinstance(g, mx.Call) and g.name in ("exp", "ln"):
        p = RZ._polinomio_de(g.args[0], var)
        if p is not None and len(RZ._recorta(p)) == 2:
            b, a = RZ._recorta(p)
            interior = mx.Call("ln", (U,)) if g.name == "exp" else mx.Call("exp", (U,))
            out.append(mx.Div(mx.Sub(interior, MI.leer(b)), MI.leer(a)))
    if isinstance(g, mx.Pow) and g.base == mx.Const("e"):
        out.extend(_inversa(mx.Call("exp", (g.exponent,)), var, U))
    return out


def _cambio(f: mx.Expr, var: str, trace: Trace, prof: int) -> mx.Expr | None:
    """Primero se preparan todos los cambios que dejan una integral solo en u; se
    prueban de la más corta a la más larga, cada uno con su parte del tiempo."""
    libres = [c for c in "uwvtsz" if c not in mx.variables(f) and c != var]
    if not libres:
        return None
    U = libres[0]
    Us = mx.Sym(U)
    opciones = []
    for g in _subexpresiones(f, var):
        dg = _d(g, var)
        if mx.exact_value(dg) == 0 and not mx.variables(dg):
            continue
        h = _limpio(mx.Div(f, dg))
        H = _reemplaza(h, g, Us)
        if var in mx.variables(H):
            ok = False
            for inv in _inversa(g, var, Us):
                cand = _limpio(_raices_positivas(mx.substitute(H, var, inv), U))
                if var not in mx.variables(cand) and _coincide_en_u(cand, h, g, var, U):
                    H, ok = cand, True
                    break
            if not ok:
                continue
        H = _limpio(H)
        if var in mx.variables(H) or mx.text(H) == mx.text(_limpio(mx.substitute(f, var, Us))):
            continue
        opciones.append((len(mx.text(H)), g, dg, H))
    opciones.sort(key=lambda o: o[0])
    for _, g, dg, H in opciones:
        with _plazo_acortado():
            try:
                FU = primitiva(H, U, Trace(), prof + 1)
            except UnsupportedError:
                continue
        F = _limpio(_raices_positivas(mx.substitute(FU, U, g), var))
        if not comprueba(F, f, var):
            continue
        trace.regla("integral.cambio", f"u = {mx.text(g)}, du = {mx.text(dg)} d{var}: "
                    f"∫ {mx.text(H)} du = {mx.text(FU)}",
                    why="la expresión es H(g(x))·g′(x): se integra en u y se deshace")
        return F
    return None


def _raices_positivas(e: mx.Expr, U: str) -> mx.Expr:
    """√(N/D) = √N/u^k cuando D = c·u^(2k) (se toma u > 0, como en el cambio
    recíproco; la primitiva final se comprueba derivando)."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import poly as P

    if isinstance(e, mx.Root) and e.degree == 2:
        r = _raices_positivas(e.radicand, U)
        try:
            N, D = MI._nd(MI._canon(r))
        except Exception:  # noqa: BLE001
            return mx.Root(2, r)
        if len(D) == 1:
            (m, c), = D.items()
            k = P.mono_exp(m, U)
            if c > 0 and k % 2 == 0 and all(v == U for v, _ in m):
                den = mx.Root(2, mx.Num(c))
                if k:
                    den = mx.Mul(den, mx.Pow(mx.Sym(U), mx.Num(Fraction(k // 2))))
                return mx.Div(mx.Root(2, P.to_expr(N)), den)
        return mx.Root(2, r)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_raices_positivas(e.left, U), _raices_positivas(e.right, U))
    if isinstance(e, mx.Neg):
        return mx.Neg(_raices_positivas(e.arg, U))
    if isinstance(e, mx.Pow):
        return mx.Pow(_raices_positivas(e.base, U), e.exponent)
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_raices_positivas(a, U) for a in e.args))
    return e


def _coincide_en_u(cand, h, g, var, U) -> bool:
    """H(g(x)) = h(x) en los puntos del dominio (los demás se saltan)."""
    buenos = 0
    for k in range(16):
        # solo x > 0: el cambio puede suponer u > 0; la comprobación final de la
        # primitiva (con x de los dos signos) es la que decide
        x = 0.37 + 0.29 * k + (1.5 if k > 7 else 0)
        try:
            gu = mx.valor_real(g, {var: x})
            b = mx.valor_real(h, {var: x})
            a = mx.valor_real(cand, {U: gu}) if gu is not None else None
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            continue
        if a is None or b is None:
            continue
        if abs(a - b) > 1e-9 * max(1.0, abs(b)):
            return False
        buenos += 1
    return buenos >= 3


def _reemplaza(e: mx.Expr, g: mx.Expr, U: mx.Expr) -> mx.Expr:
    tg = mx.text(_limpio(g))

    def rec(n):
        if mx.text(n) == tg or mx.text(_limpio(n)) == tg:
            return U
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(n)(rec(n.left), rec(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(rec(n.arg))
        if isinstance(n, mx.Pow):
            return mx.Pow(rec(n.base), rec(n.exponent))
        if isinstance(n, mx.Root):
            return mx.Root(n.degree, rec(n.radicand))
        if isinstance(n, mx.Call):
            return mx.Call(n.name, tuple(rec(a) for a in n.args))
        return n
    return rec(e)


# ---------------------------------------------------------------------------
# sustitución trigonométrica general
# ---------------------------------------------------------------------------


def _trigonometrica(f: mx.Expr, var: str, trace: Trace, prof: int) -> mx.Expr | None:
    """√(a − b·x²) → x = √(a/b)·sen t; √(a + b·x²) → x = √(a/b)·tan t;
    √(b·x² − a) → x = √(a/b)·sec t (a, b > 0). Se integra en t (potencias
    trigonométricas) y se deshace con t = arcsen(…), arctan(…), arcsec(…)."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import raices as RZ

    radicales = [n for n in _todos(f) if isinstance(n, mx.Root) and n.degree == 2
                 and var in mx.variables(n.radicand)]
    if not radicales:
        return None
    p = RZ._polinomio_de(radicales[0].radicand, var)
    if p is None:
        return None
    p = RZ._recorta(p) + [Fraction(0)] * 3
    c, b1, a2 = p[0], p[1], p[2]
    if b1 != 0 or a2 == 0 or c == 0 or len(RZ._recorta(p)) > 3:
        return None
    t = "t" if "t" not in mx.variables(f) else "s"
    T = mx.Sym(t)
    k = MI._limpio(mx.Root(2, mx.Num(abs(c / a2))))
    if a2 < 0 < c:
        x_de_t, dx, inversa = mx.Mul(k, mx.Call("sin", (T,))), mx.Mul(k, mx.Call("cos", (T,))), \
            mx.Call("asin", (mx.Div(mx.Sym(var), k),))
        regla = "sen"
    elif a2 > 0 and c > 0:
        # primero senh (formas limpias: √(k² + x²) = k·cosh t); si no sale, tan
        x_de_t, dx = mx.Mul(k, mx.Call("sinh", (T,))), mx.Mul(k, mx.Call("cosh", (T,)))
        inversa = mx.Call("asinh", (mx.Div(mx.Sym(var), k),))
        regla = "senh"
        g = _limpio(_raices_hip(MI._limpio(mx.Mul(mx.substitute(f, var, x_de_t), dx)), t))
        if var not in mx.variables(g):
            try:
                G = primitiva(_limpio(MI._angulo_doble_h(g) if hasattr(MI, "_angulo_doble_h") else g),
                              t, Trace(), prof + 1)
                F = _limpio(mx.substitute(_doble_h(G), t, inversa))
                trace.regla("integral.trig", f"x = {mx.text(x_de_t)} (senh), dx = {mx.text(dx)} dt: "
                            f"∫ {mx.text(g)} dt = {mx.text(G)}; t = {mx.text(inversa)}",
                            why="√(k² + x²) = k·cosh t por cosh² − senh² = 1")
                return F
            except UnsupportedError:
                pass
        x_de_t, dx = mx.Mul(k, mx.Call("tan", (T,))), mx.Div(k, mx.Pow(mx.Call("cos", (T,)), mx.Num(2)))
        inversa = mx.Call("atan", (mx.Div(mx.Sym(var), k),))
        regla = "tan"
    else:
        x_de_t = mx.Div(k, mx.Call("cos", (T,)))
        dx = mx.Div(mx.Mul(k, mx.Call("sin", (T,))), mx.Pow(mx.Call("cos", (T,)), mx.Num(2)))
        inversa = mx.Call("acos", (mx.Div(k, mx.Sym(var)),))
        regla = "sec"
    g = mx.Mul(mx.substitute(f, var, x_de_t), dx)
    g = _limpio(_raices_trig(MI._limpio(g), t))
    if var in mx.variables(g):
        return None
    try:
        G = primitiva(g, t, Trace(), prof + 1)
    except UnsupportedError:
        return None
    F = _limpio(mx.substitute(MI._angulo_doble(G), t, inversa))
    trace.regla("integral.trig", f"x = {mx.text(x_de_t)} ({regla}), dx = {mx.text(dx)} dt: "
                f"∫ {mx.text(g)} dt = {mx.text(G)}; t = {mx.text(inversa)}",
                why="la raíz se vuelve un coseno (o secante) con Pitágoras")
    return F


def _raices_trig(e: mx.Expr, t: str) -> mx.Expr:
    """√(k²·cos²t) = k·cos t (t en el intervalo principal del cambio, donde cos t ≥ 0)
    y lo mismo con 1/cos²t."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import poly as P

    if isinstance(e, mx.Root) and e.degree == 2:
        for r in (_sen_a_cos(MI._canon(e.radicand)), MI._pitagoras(MI._canon(e.radicand)),
                  _tan_a_sec(MI._canon(e.radicand))):
            hecho = _raiz_de_monomio(r, MI, P)
            if hecho is not None:
                return hecho
        return e
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_raices_trig(e.left, t), _raices_trig(e.right, t))
    if isinstance(e, mx.Neg):
        return mx.Neg(_raices_trig(e.arg, t))
    if isinstance(e, mx.Pow):
        return mx.Pow(_raices_trig(e.base, t), e.exponent)
    return e


def _raices_hip(e: mx.Expr, t: str) -> mx.Expr:
    """√(k²·(1 + senh²t)) = k·cosh t (cosh > 0)."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import poly as P

    if isinstance(e, mx.Root) and e.degree == 2:
        try:
            p = P.as_poly(MI._canon(e.radicand))
        except Exception:  # noqa: BLE001
            return e
        senh = f"@sinh({t})"
        cosh = mx.Call("cosh", (mx.Sym(t),))
        # p = c·(1 + senh²) con c > 0
        c = p.get((), Fraction(0))
        if c > 0 and p.get(((senh, 2),), Fraction(0)) == c and len(p) == 2:
            import math
            rn, rd = math.isqrt(c.numerator), math.isqrt(c.denominator)
            k = MI.leer(Fraction(rn, rd)) if rn * rn == c.numerator and rd * rd == c.denominator \
                else mx.Root(2, MI.leer(c))
            return mx.Mul(k, cosh)
        return e
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_raices_hip(e.left, t), _raices_hip(e.right, t))
    if isinstance(e, mx.Neg):
        return mx.Neg(_raices_hip(e.arg, t))
    if isinstance(e, mx.Pow):
        return mx.Pow(_raices_hip(e.base, t), e.exponent)
    return e


def _doble_h(e: mx.Expr) -> mx.Expr:
    """senh(2u) = 2 senh u cosh u, cosh(2u) = 1 + 2 senh²u (para deshacer t = arcsenh)."""
    if isinstance(e, mx.Call) and e.name in ("sinh", "cosh") and len(e.args) == 1:
        a = e.args[0]
        if isinstance(a, mx.Mul) and mx.exact_value(a.left) is not None and not mx.variables(a.left) \
                and mx.exact_value(a.left) in (2, 4):
            u = a.right if mx.exact_value(a.left) == 2 else mx.Mul(mx.Num(Fraction(2)), a.right)
            u = _doble_h(u) if mx.exact_value(a.left) == 4 else u
            sh, ch = mx.Call("sinh", (u,)), mx.Call("cosh", (u,))
            if mx.exact_value(a.left) == 4:
                inner = _doble_h(mx.Call("sinh", (mx.Mul(mx.Num(Fraction(2)), a.right),)))
                innerc = _doble_h(mx.Call("cosh", (mx.Mul(mx.Num(Fraction(2)), a.right),)))
                sh, ch = inner, innerc
            if e.name == "sinh":
                return mx.Mul(mx.Num(Fraction(2)), mx.Mul(sh, ch))
            return mx.Add(mx.Num(Fraction(1)), mx.Mul(mx.Num(Fraction(2)), mx.Pow(sh, mx.Num(2))))
        return mx.Call(e.name, (_doble_h(a),))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_doble_h(e.left), _doble_h(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_doble_h(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_doble_h(e.base), e.exponent)
    return e


def _sen_a_cos(e: mx.Expr) -> mx.Expr:
    """sen²u = 1 − cos²u (el sentido contrario al de multiple._pitagoras)."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return e
    cambio = True
    while cambio:
        cambio = False
        for m, c in list(p.items()):
            for v, k in m:
                if P.is_atom(v) and P.es_llamada(v, "sin") and k >= 2:
                    cos_ = "@cos(" + P.atom_text(v)[4:]
                    resto = P.mono_div(m, ((v, 2),))
                    p = P.add(p, {m: c}, -1)
                    p = P.add(p, P.mul({resto: c}, P.add({(): Fraction(1)},
                                                         {((cos_, 2),): Fraction(1)}, -1)))
                    cambio = True
                    break
            if cambio:
                break
    return P.to_expr(p)


def _tan_a_sec(e: mx.Expr) -> mx.Expr:
    """1 + tan²u = 1/cos²u: con tan escrita como sen/cos y Pitágoras en el numerador."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import verify as V

    q = MI._racional(MI._canon(V._a_seno_coseno(e)))
    if isinstance(q, mx.Div):
        return mx.Div(MI._pitagoras(MI._canon(q.left)), q.right)
    return e


def _raiz_de_monomio(r, MI, P):
    try:
        N, D = MI._nd(MI._canon(r))
    except Exception:  # noqa: BLE001
        return None
    if True:
        def raiz_monomio(p):
            if len(p) != 1:
                return None
            (m, c), = p.items()
            if c <= 0 or any(k % 2 for _, k in m):
                return None
            num = c.numerator
            den = c.denominator
            import math
            rn, rd = math.isqrt(num), math.isqrt(den)
            coef = MI.leer(Fraction(rn, rd)) if rn * rn == num and rd * rd == den else \
                mx.Root(2, MI.leer(c))
            out = coef
            for v, k in m:
                out = mx.Mul(out, mx.Pow(mx.parse(P.atom_text(v)) if P.is_atom(v) else mx.Sym(v),
                                         mx.Num(Fraction(k // 2))))
            return out
        rn_, rd_ = raiz_monomio(N), raiz_monomio(D)
        if rn_ is not None and rd_ is not None:
            return mx.Div(rn_, rd_)
        return None


# ---------------------------------------------------------------------------
# funciones especiales
# ---------------------------------------------------------------------------


def _especial(f: mx.Expr, var: str, trace: Trace, prof: int) -> mx.Expr | None:
    """F = c·S(αx) con S especial; c y α se ajustan y F′ = f se comprueba."""
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    x = mx.Sym(var)
    cands = []

    def lin_coef(arg, grado):
        p = RZ._polinomio_de(arg, var)
        if p is None:
            return None
        p = RZ._recorta(p) + [Fraction(0)] * 3
        if any(c != 0 for i, c in enumerate(p) if i != grado):
            return None
        return p[grado]
    for n in _todos(f):
        if isinstance(n, mx.Call) and n.name == "exp":
            a = lin_coef(n.args[0], 2)
            if a is not None and a != 0:
                k = mx.Root(2, mx.Num(abs(a)))
                nombre = "erf" if a < 0 else "erfi"
                cands.append(mx.Call(nombre, (mx.Mul(k, x),)))
            b = lin_coef(n.args[0], 1)
            if b is not None and b != 0:
                cands.append(mx.Call("Ei", (mx.Mul(mx.Num(b), x),)))
        if isinstance(n, mx.Pow) and n.base == mx.Const("e"):
            a = lin_coef(n.exponent, 2)
            if a is not None and a != 0:
                k = mx.Root(2, mx.Num(abs(a)))
                cands.append(mx.Call("erf" if a < 0 else "erfi", (mx.Mul(k, x),)))
            b = lin_coef(n.exponent, 1)
            if b is not None and b != 0:
                cands.append(mx.Call("Ei", (mx.Mul(mx.Num(b), x),)))
        if isinstance(n, mx.Call) and n.name in ("sin", "cos"):
            b = lin_coef(n.args[0], 1)
            if b is not None and b != 0:
                cands.append(mx.Call("Si" if n.name == "sin" else "Ci", (mx.Mul(mx.Num(b), x),)))
            a = lin_coef(n.args[0], 2)
            if a is not None and a != 0:
                k = mx.Root(2, mx.Num(abs(a)))
                nombre = "FresnelS" if n.name == "sin" else "FresnelC"
                cands.append(mx.Call(nombre, (mx.Mul(k, x),)))
        if isinstance(n, mx.Call) and n.name == "ln" and n.args[0] == x:
            cands.append(mx.Call("Ei", (mx.Call("ln", (x,)),)))
    for S in cands:
        dS = _d(S, var)
        c = _proporcion(f, dS, var)
        if c is None:
            # coeficiente irracional (√π…): se toma del cociente simbólico
            q = _limpio(mx.Div(f, dS))
            if var in mx.variables(q):
                continue
            F = _limpio(mx.Mul(q, S))
        else:
            F = _limpio(mx.Mul(mx.Num(c), S))
        if comprueba(F, f, var):
            trace.regla("integral.especial", f"∫ {mx.text(f)} d{var} = {mx.text(F)}",
                        why="no tiene primitiva elemental: se expresa con la función "
                            "especial cuya derivada es el integrando")
            return F
    _ = P
    return None


def _todos(e):
    yield e
    for h in ("left", "right", "arg", "base", "exponent", "radicand"):
        c = getattr(e, h, None)
        if isinstance(c, mx.Expr):
            yield from _todos(c)
    for a in getattr(e, "args", ()) or ():
        if isinstance(a, mx.Expr):
            yield from _todos(a)
