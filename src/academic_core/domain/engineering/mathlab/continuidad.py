# SPDX-License-Identifier: MIT
"""What Barrow's rule needs before it may be applied, checked instead of assumed.

``∫_a^b f = F(b) - F(a)`` holds when ``f`` is continuous on ``[a, b]`` **and** ``F`` is
an antiderivative of ``f`` on the whole interval, which in particular means
continuous on it. Both conditions used to be taken for granted, and both failed
on exam-level inputs (found 2026-10-05, auditing against SymPy):

* **a pole of the integrand between the probe points.** The old check evaluated
  ``f`` at 17 equally spaced points. ``1/(x - 1/10)`` on ``[0, 1]`` and ``tan(x)`` on
  ``[0, 2]`` have their pole off that grid, so Barrow returned a finite number —
  ``2.197`` and ``0.877`` — for integrals that diverge.
* **a jump of the antiderivative.** The universal substitution produces terms
  like ``atan(tan(x/2))``, a correct antiderivative on each interval between odd
  multiples of ``π`` and discontinuous at them. ``∫_0^{2π} sin(x)·sin(x)`` came out
  ``0`` instead of ``π``, and ``∫_0^{2π} dx/(2 + cos x)`` ``0`` instead of ``2π/√3``.

The fix is structural. The *dangerous* subexpressions are read off the tree —
every denominator, every base of a negative or fractional power, every argument
of ``ln``, every ``cos`` hidden in a ``tan`` — and their zeros on the interval are
located; a zero is a singularity of ``f`` (refuse: the integral is improper) or a
removable point, and a zero of a danger of ``F`` is a candidate jump, whose size
is measured and subtracted. A final check against an adaptive quadrature that
shares nothing with the symbolic path decides whether the value may be shown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from academic_core.domain.engineering.mathlab import mvexpr as mx

#: grid used to bracket the zeros of a dangerous subexpression
MALLA = 4000


def _valor(e: mx.Expr, var: str, x: float) -> float | None:
    try:
        v = mx.evaluate(e, {var: x})
    except Exception:  # noqa: BLE001 - a point where it does not evaluate
        return None
    if v is None or not math.isfinite(v.real) or abs(v.imag) > 1e-9 * max(1.0, abs(v.real)):
        return None
    return v.real


def peligros(e: mx.Expr, var: str) -> list[mx.Expr]:
    """The subexpressions whose zeros can make ``e`` undefined or discontinuous."""
    salida: list[mx.Expr] = []

    def visita(n: mx.Expr) -> None:
        if var not in mx.variables(n):
            return
        if isinstance(n, mx.Div):
            salida.append(n.right)
        elif isinstance(n, mx.Pow):
            k = mx.exact_value(n.exponent)
            if k is None or k < 0 or getattr(k, "denominator", 1) != 1:
                salida.append(n.base)
        elif isinstance(n, mx.Root):
            salida.append(n.radicand)
        elif isinstance(n, mx.Call) and n.args:
            u = n.args[-1]
            if n.name in ("tan", "sec"):
                salida.append(mx.Call("cos", (u,)))
            elif n.name in ("cot", "csc"):
                salida.append(mx.Call("sin", (u,)))
            elif n.name in ("coth", "csch"):
                salida.append(mx.Call("sinh", (u,)))
            elif n.name in ("ln", "log", "log10"):
                salida.append(u)
            elif n.name in ("asin", "acos", "atanh"):
                salida.append(mx.Sub(mx.ONE, mx.Pow(u, mx.Num(2))))
            elif n.name == "acosh":
                salida.append(mx.Sub(u, mx.ONE))
            elif n.name in ("floor", "ceil", "sign"):
                # a jump wherever the argument crosses an integer (or 0 for sign)
                salida.append(u if n.name == "sign" else mx.Call("sin", (mx.Mul(mx.PI, u),)))
        for hijo in _hijos(n):
            visita(hijo)

    visita(e)
    return salida


def _hijos(n: mx.Expr):
    for nombre in ("left", "right", "base", "exponent", "arg", "radicand"):
        h = getattr(n, nombre, None)
        if isinstance(h, mx.Expr):
            yield h
    if isinstance(n, mx.Call):
        yield from n.args


def ceros(g: mx.Expr, var: str, a: float, b: float) -> list[float]:
    """The zeros of ``g`` on ``[a, b]``, from a fine grid, refined.

    A zero is found where ``g`` changes sign, where it stops being evaluable (the
    edge of a domain), or where ``|g|`` has a local minimum that refines to 0 — the
    last one catches double roots such as ``(x - 1)^2``, which do not change sign.
    """
    if b <= a:
        return []
    h = (b - a) / MALLA
    xs = [a + i * h for i in range(MALLA + 1)]
    ys = [_valor(g, var, x) for x in xs]
    escala = max((abs(y) for y in ys if y is not None), default=1.0) or 1.0
    encontrados: list[float] = []
    for i in range(MALLA):
        y0, y1 = ys[i], ys[i + 1]
        if y0 is None or y1 is None:
            if (y0 is None) != (y1 is None):
                encontrados.append(_borde(g, var, xs[i], xs[i + 1], y0 is None))
            elif y0 is None:
                encontrados.append(xs[i])
            continue
        if y0 == 0:
            encontrados.append(xs[i])
        elif y0 * y1 < 0:
            encontrados.append(_biseccion(g, var, xs[i], xs[i + 1]))
    if ys[-1] == 0:
        encontrados.append(b)
    for i in range(1, MALLA):
        y_1, y0, y1 = ys[i - 1], ys[i], ys[i + 1]
        if None in (y_1, y0, y1):
            continue
        if abs(y0) <= abs(y_1) and abs(y0) <= abs(y1) and y_1 * y1 > 0:
            x, v = _minimo(g, var, xs[i - 1], xs[i + 1])
            if v is not None and abs(v) <= 1e-9 * escala:
                encontrados.append(x)
    return _unicos(sorted(encontrados), h)


def _biseccion(g, var, lo, hi):
    flo = _valor(g, var, lo)
    for _ in range(80):
        mid = (lo + hi) / 2
        fm = _valor(g, var, mid)
        if fm is None or fm == 0:
            return mid
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def _borde(g, var, lo, hi, izquierda_indefinida):
    for _ in range(80):
        mid = (lo + hi) / 2
        indefinido = _valor(g, var, mid) is None
        if indefinido == izquierda_indefinida:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _minimo(g, var, lo, hi):
    """Golden-section search of ``|g|`` on ``[lo, hi]``."""
    r = (math.sqrt(5) - 1) / 2
    c, d = hi - r * (hi - lo), lo + r * (hi - lo)
    for _ in range(100):
        fc, fd = _valor(g, var, c), _valor(g, var, d)
        if fc is None or fd is None:
            break
        if abs(fc) < abs(fd):
            hi, d = d, c
            c = hi - r * (hi - lo)
        else:
            lo, c = c, d
            d = lo + r * (hi - lo)
    x = (lo + hi) / 2
    return x, _valor(g, var, x)


def _unicos(xs: list[float], h: float) -> list[float]:
    salida: list[float] = []
    for x in xs:
        if not salida or abs(x - salida[-1]) > 2 * h:
            salida.append(x)
    return salida


# ---------------------------------------------------------------------------
# the integrand: singular, removable, or fine
# ---------------------------------------------------------------------------


def es_singular(f: mx.Expr, var: str, c: float) -> bool:
    """Whether ``f`` is unbounded (or undefined on a side) near ``c``.

    A removable point such as ``sin(x)/x`` at 0 keeps ``|f|`` bounded as the
    distance shrinks; a pole makes it grow without bound.
    """
    valores = []
    for d in (1e-3, 1e-5, 1e-7):
        lados = [_valor(f, var, c - d), _valor(f, var, c + d)]
        if any(v is None for v in lados):
            return True
        valores.append(max(abs(v) for v in lados))
    return valores[2] > 50 * max(1.0, valores[0])


def puntos_singulares(f: mx.Expr, var: str, a: float, b: float) -> list[float]:
    """Points of ``[a, b]`` where the integrand is unbounded or undefined."""
    candidatos = sorted({round(c, 12) for g in peligros(f, var)
                         for c in ceros(g, var, a, b)})
    malos = [c for c in candidatos if es_singular(f, var, c)]
    # a region where f does not evaluate at all (ln of a negative, for instance)
    paso = (b - a) / 400 if b > a else 0
    for i in range(401):
        x = a + i * paso
        if _valor(f, var, x) is None and not any(abs(x - m) < 1e-6 for m in malos):
            if not any(abs(x - c) < 1e-9 for c in candidatos) or es_singular(f, var, x):
                malos.append(x)
                break
    return sorted(malos)


# ---------------------------------------------------------------------------
# the antiderivative: its jumps
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Salto:
    punto: float
    tamano: float


def saltos(F: mx.Expr, f: mx.Expr, var: str, a: float, b: float) -> list[Salto]:
    """Jumps of ``F`` inside ``(a, b)``: ``lim F(c+) - lim F(c-)``, measured.

    ``F(c+ε) - F(c-ε) = J + 2ε·f(c) + O(ε³)`` when ``F' = f`` on both sides, so the
    jump is that difference minus ``2ε·f(c)``. Two values of ``ε`` are compared: a
    real jump does not depend on ``ε``, a continuous point gives 0 in both.
    """
    salida: list[Salto] = []
    candidatos = sorted({round(c, 12) for g in peligros(F, var)
                         for c in ceros(g, var, a, b)})
    for c in candidatos:
        if not (a < c < b):
            continue
        fc = _valor(f, var, c)
        estimaciones = []
        for eps in (1e-5, 1e-6):
            mas, menos = _valor(F, var, c + eps), _valor(F, var, c - eps)
            if mas is None or menos is None:
                break
            estimaciones.append(mas - menos - 2 * eps * (fc or 0.0))
        if len(estimaciones) == 2 and abs(estimaciones[1]) > 1e-7:
            salida.append(Salto(c, estimaciones[1]))
    return salida


# ---------------------------------------------------------------------------
# the independent second path
# ---------------------------------------------------------------------------


_NODOS_K = (0.991455371120813, 0.949107912342759, 0.864864423359769,
            0.741531185599394, 0.586087235467691, 0.405845151377397,
            0.207784955007898, 0.0)
_PESOS_K = (0.022935322010529, 0.063092092629979, 0.104790010322250,
            0.140653259715525, 0.169004726639267, 0.190350578064785,
            0.204432940075298, 0.209482141084728)
_PESOS_G = (0.0, 0.129484966168870, 0.0, 0.279705391489277, 0.0,
            0.381830050505119, 0.0, 0.417959183673469)


def _gk15(f, a, b):
    centro, radio = (a + b) / 2, (b - a) / 2
    k = g = 0.0
    for x, wk, wg in zip(_NODOS_K, _PESOS_K, _PESOS_G):
        puntos = (centro,) if x == 0.0 else (centro - radio * x, centro + radio * x)
        for p in puntos:
            v = f(p)
            if v is None:
                raise ValueError
            k += wk * v
            g += wg * v
    return k * radio, abs(k - g) * radio


def cuadratura(f: mx.Expr, var: str, a: float, b: float,
               tolerancia: float = 1e-11) -> tuple[float, float] | None:
    """Adaptive Gauss–Kronrod (7-15): ``(value, error estimate)`` or ``None``.

    Shares nothing with the symbolic path — no antiderivative, no simplification —
    which is what makes it a second path in the sense of §5.3.
    """
    def evalua(x):
        return _valor(f, var, x)

    pila = [(a, b)]
    total = error = 0.0
    evaluaciones = 0
    while pila:
        lo, hi = pila.pop()
        try:
            valor, err = _gk15(evalua, lo, hi)
        except ValueError:
            return None
        evaluaciones += 15
        if evaluaciones > 200_000:
            return None
        if err <= max(tolerancia * abs(valor), 1e-14) or hi - lo < 1e-9 * max(1.0, abs(b - a)):
            total += valor
            error += err
        else:
            mid = (lo + hi) / 2
            pila.extend([(lo, mid), (mid, hi)])
    return total, error
