# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): distributions with AREA — Dirac deltas, their derivatives, and steps.

A distribution here is an ordinary piecewise function plus a finite list of
impulses ``A·δ⁽ᵏ⁾(t − t₀)`` (k = 0 is the delta, k = 1 the doublet δ′, …). That is
what Signals and Systems needs: the derivative of a function with jumps (each jump
becomes a delta whose area is the jump), the derivative of a delta, the sifting
property and its Leibniz form for δ⁽ᵏ⁾, ``δ⁽ᵏ⁾(a·t − b) = δ⁽ᵏ⁾(t − b/a)/(aᵏ·|a|)``,
``δ(g(t)) = Σ δ(t − tᵢ)/|g′(tᵢ)|`` over the simple real roots of g, steps of a
non-linear argument (``u(t² − 1)``), products of steps and ``δ·u``, convolution with
deltas, integrals that cross impulses, and the Fourier transform of a train.

Positions are EXACT: rational or algebraic (``δ(t² − 2)`` sits at ``±√2``), kept as
expressions and ordered by their value.

Input text is a sum of terms; each term is a product of ordinary factors, any
number of ``u(...)``/``escalon(...)`` and at most one ``delta(...)``, ``delta'(...)``,
``delta''(...)``… Refused, with the reason: two deltas in one product, a delta inside
another function or in a denominator, ``δ(g)`` at a multiple root of g (not defined),
``δ⁽ᵏ⁾(g)`` with k ≥ 1 and g non-linear, a step evaluated exactly at its jump under a
delta (``δ(t)·u(t)``) unless the convention ``u(0)`` is declared.

Second paths: the jumps and the impulse areas are recomputed by evaluating each
side of the breakpoint; the integral of the derivative is checked against the
increment of the function (fundamental theorem with the impulses counted).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: two exact positions closer than this are the same point
PROXIMIDAD = 1e-12
#: highest derivative of δ accepted
MAX_ORDEN = 4


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# exact positions
# ---------------------------------------------------------------------------


class Punto:
    """An exact real position (``1/2``, ``sqrt(2)``), ordered by its value."""

    __slots__ = ("expr", "x", "aproximado")

    def __init__(self, valor, aproximado: bool = False):
        self.aproximado = aproximado
        if isinstance(valor, Punto):
            self.expr, self.x, self.aproximado = valor.expr, valor.x, valor.aproximado
            return
        expr = valor if isinstance(valor, mx.Expr) else mx.num(Fraction(valor))
        x = mx.valor_real(expr, {})
        if x is None:
            raise _error("BAD_INPUT", f"«{mx.text(expr)}» no es un número real")
        exacto = mx.exact_value(expr)
        self.expr = mx.num(exacto) if exacto is not None else expr
        self.x = float(x)

    @property
    def racional(self) -> Fraction | None:
        return None if self.aproximado else mx.exact_value(self.expr)

    def mas(self, d: Fraction) -> "Punto":
        if self.aproximado:
            return Punto(mx.Num(Fraction(self.x) + d), aproximado=True)
        q = self.racional
        return Punto(q + d) if q is not None else Punto(mx.Add(self.expr, mx.num(d)))

    def __eq__(self, otro) -> bool:
        if not isinstance(otro, Punto):
            try:
                otro = Punto(otro)
            except Exception:  # noqa: BLE001
                return NotImplemented
        return abs(self.x - otro.x) <= PROXIMIDAD * max(1.0, abs(self.x))

    def __hash__(self) -> int:
        return hash(round(self.x, 9))

    def __lt__(self, otro) -> bool:
        return self != otro and self.x < Punto(otro).x

    def __le__(self, otro) -> bool:
        return self == otro or self.x < Punto(otro).x

    def __gt__(self, otro) -> bool:
        return self != otro and self.x > Punto(otro).x

    def __ge__(self, otro) -> bool:
        return self == otro or self.x > Punto(otro).x

    def __str__(self) -> str:
        return f"≈{self.x:.12g}" if self.aproximado else mx.text(self.expr)

    __repr__ = __str__


# ---------------------------------------------------------------------------
# the object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tramo:
    desde: Punto | None        # None = −∞
    hasta: Punto | None        # None = +∞
    expr: mx.Expr

    def contiene(self, x: float) -> bool:
        return (self.desde is None or self.desde.x < x) and (self.hasta is None or x < self.hasta.x)


@dataclass(frozen=True)
class Impulso:
    posicion: Punto
    area: mx.Expr
    orden: int = 0          # 0: δ, 1: δ′, …


_PRIMAS = {0: "", 1: "′", 2: "″", 3: "‴"}


def _primas(k: int) -> str:
    return _PRIMAS.get(k, f"⁽{k}⁾")


@dataclass(frozen=True)
class Distribucion:
    var: str
    tramos: tuple[Tramo, ...] = ()               # disjoint, sorted, zero outside
    impulsos: tuple[Impulso, ...] = ()           # sorted by (position, order)

    def texto(self) -> str:
        partes = []
        for t in self.tramos:
            if _es_cero(t.expr):
                continue
            a = "−∞" if t.desde is None else str(t.desde)
            b = "+∞" if t.hasta is None else str(t.hasta)
            partes.append(f"{mx.text(t.expr)} en ({a}, {b})")
        for imp in self.impulsos:
            delta = f"δ{_primas(imp.orden)}({_desplazado(self.var, imp.posicion)})"
            if imp.posicion.aproximado:
                a = mx.valor_real(imp.area, {})
                partes.append(f"≈{a:.10g}·{delta}")
                continue
            v = mx.exact_value(imp.area)
            if v == 1:
                partes.append(delta)
            elif v == -1:
                partes.append("−" + delta)
            else:
                partes.append(f"{_texto_area(imp.area)}·{delta}")
        return " + ".join(partes).replace("+ −", "− ") if partes else "0"

    @property
    def aproximada(self) -> bool:
        """Some position is only known numerically (a root isolated by Sturm)."""
        return any(i.posicion.aproximado for i in self.impulsos) or any(
            p is not None and p.aproximado for t in self.tramos for p in (t.desde, t.hasta))

    def ordinaria(self, t) -> mx.Expr | None:
        x = Punto(t).x
        for tramo in self.tramos:
            if tramo.contiene(x):
                return tramo.expr
        return None


def _desplazado(var: str, t0: Punto) -> str:
    q = t0.racional
    if q is not None:
        if q == 0:
            return var
        return f"{var} − {q}" if q > 0 else f"{var} + {-q}"
    texto = str(t0)
    if t0.aproximado:
        return f"{var} − ({texto})"
    if texto.startswith("-"):
        return f"{var} + {texto[1:]}"
    return f"{var} − {texto}"


def _texto_area(area: mx.Expr) -> str:
    texto = mx.text(area)
    v = mx.exact_value(area)
    if v is not None and v.denominator == 1:
        return texto
    return texto if isinstance(area, (mx.Sym, mx.Const)) else f"({texto})"


def _es_cero(e: mx.Expr) -> bool:
    v = mx.exact_value(e)
    if v is not None:
        return v == 0
    if mx.variables(e):
        return False
    z = mx.evaluate(e)
    return z is not None and abs(z) < 1e-14


def _limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import limite as LM

    return LM._limpio(e)


def _suma(a: mx.Expr, b: mx.Expr) -> mx.Expr:
    if _es_cero(a):
        return b
    if _es_cero(b):
        return a
    return _limpio(mx.Add(a, b))


def _en(e: mx.Expr, var: str, t0: Punto) -> mx.Expr:
    return _limpio(mx.substitute(e, var, t0.expr))


# ---------------------------------------------------------------------------
# reading the text
# ---------------------------------------------------------------------------


_DISTRIBUCION = re.compile(r"(delta|δ|u|escalon|heaviside)\s*('*)\s*\(", re.IGNORECASE)

# El escalón se escribe u(...) dentro de expr, pero mx.parse no conoce u como
# función (u es una variable muda legítima en los cambios de variable). Esta
# reescritura se aplica solo donde el sentido es inequívoco: la f de una
# convolución con impulsos, donde f es una señal y no lleva variables mudas.
_ESCALON_U = re.compile(r"(?<![A-Za-z_0-9])[uU]\s*\(")


def normaliza_escalon(texto: str) -> str:
    """u(...) / U(...) -> escalon(...), el resto del texto sin tocar."""
    return _ESCALON_U.sub("escalon(", texto)


def _terminos(texto: str) -> list[tuple[int, str]]:
    """Split at top-level + and − (keeping the sign)."""
    salida, nivel, actual, signo = [], 0, "", 1
    previo = ""
    for ch in texto:
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
        if nivel == 0 and ch in "+-" and previo not in ("", "*", "/", "^", "(", "e", "E"):
            if actual.strip():
                salida.append((signo, actual))
            signo, actual = (1 if ch == "+" else -1), ""
        elif nivel == 0 and ch in "+-" and previo == "":
            signo = 1 if ch == "+" else -1
        else:
            actual += ch
        if not ch.isspace():
            previo = ch
    if actual.strip():
        salida.append((signo, actual))
    return salida


def _argumento(texto: str, inicio: int) -> tuple[str, int]:
    nivel = 1
    i = inicio
    while i < len(texto) and nivel:
        if texto[i] == "(":
            nivel += 1
        elif texto[i] == ")":
            nivel -= 1
        i += 1
    if nivel:
        raise _error("PARSE_ERROR", "paréntesis sin cerrar")
    return texto[inicio:i - 1], i


def _polinomio(arg: str, var: str):
    from academic_core.domain.engineering.mathlab import poly as P

    e = mx.parse(arg)
    if set(mx.variables(e)) - {var}:
        raise _no(f"el argumento «{arg}» solo puede depender de {var}")
    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        p = None
    if p is None or any(set(dict(m)) - {var} for m in p):
        raise _no(f"el argumento «{arg}» tiene que ser un polinomio en {var} con "
                  "coeficientes racionales")
    return e, p


def _lineal_exacto(arg: str, var: str) -> tuple[Fraction, mx.Expr] | None:
    """arg = a·t + c con a racional ≠ 0 y c constante exacta cualquiera (t − π)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import limite as LM

    try:
        e = mx.parse(arg)
        if set(mx.variables(e)) - {var}:
            return None
        a = LM._limpio(DM.differentiate(e, var))
        c = LM._limpio(mx.substitute(e, var, mx.num(Fraction(0))))
    except Exception:  # noqa: BLE001
        return None
    av = mx.exact_value(a)
    if av is None or av == 0 or mx.variables(c) or mx.valor_real(c, {}) is None:
        return None
    return Fraction(av), c


def _lineal(p, var: str) -> tuple[Fraction, Fraction] | None:
    a, c = Fraction(0), Fraction(0)
    for mono, coef in p.items():
        if mono == ():
            c = Fraction(coef)
        elif mono == ((var, 1),):
            a = Fraction(coef)
        else:
            return None
    return (a, c) if a != 0 else None


def _raices_reales(p, var: str, arg: str) -> list[tuple[Punto, int]]:
    """ALL real roots with multiplicity: exact when possible; otherwise isolated by
    Sturm's theorem (the count is exact) and given as approximate positions."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    coefs = RZ._polinomio_de(mx.parse(arg), var)
    if coefs is None:
        raise _no(f"«{arg}» no es un polinomio con coeficientes racionales")
    salida = []
    for r in RZ.raices_polinomio(coefs).raices:
        punto = Punto(r.valor) if r.exacta else Punto(mx.Num(Fraction(r.x)), aproximado=True)
        salida.append((punto, r.multiplicidad))
    return sorted(salida, key=lambda rm: rm[0].x)


def _positivo(e: mx.Expr, var: str, arg: str) -> list[tuple[Punto | None, Punto | None]]:
    """The open intervals where the polynomial is > 0 — sign tested between roots."""
    general = _lineal_exacto(arg, var)
    if general is not None:
        a, c = general
        t0 = Punto(_limpio(mx.Div(mx.Neg(c), mx.num(a))))
        return [(t0, None)] if a > 0 else [(None, t0)]
    _, p = _polinomio(arg, var)
    raices = [r for r, _ in _raices_reales(p, var, arg)]
    if not mx.variables(e):
        v = mx.valor_real(e, {})
        return [(None, None)] if v is not None and v > 0 else []
    bordes: list[Punto | None] = [None] + raices + [None]
    salida = []
    for a, b in zip(bordes, bordes[1:]):
        if a is None and b is None:
            x = 0.0
        elif a is None:
            x = b.x - 1
        elif b is None:
            x = a.x + 1
        else:
            x = (a.x + b.x) / 2
        v = mx.valor_real(e, {var: x})
        if v is not None and v > 0:
            if salida and salida[-1][1] is not None and a is not None and salida[-1][1] == a:
                # a root of even multiplicity: the sign does not change, but u(0) there
                # is a single point, irrelevant for an ordinary function
                salida[-1] = (salida[-1][0], b)
            else:
                salida.append((a, b))
    return salida


def _interseca(A, B):
    salida = []
    for a0, a1 in A:
        for b0, b1 in B:
            lo = a0 if b0 is None else b0 if a0 is None else max(a0, b0, key=lambda p: p.x)
            hi = a1 if b1 is None else b1 if a1 is None else min(a1, b1, key=lambda p: p.x)
            if lo is None or hi is None or lo < hi:
                salida.append((lo, hi))
    return salida


def _escalon_en(arg: str, var: str, t0: Punto, u0: Fraction | None) -> Fraction:
    e = mx.parse(arg) if _lineal_exacto(arg, var) is not None else _polinomio(arg, var)[0]
    v = mx.valor_real(e, {var: t0.x})
    g_exacto = mx.exact_value(mx.substitute(e, var, t0.expr))
    if g_exacto == 0 or (g_exacto is None and v is not None and abs(v) < 1e-12):
        if u0 is None:
            raise _error("AMBIGUOUS", f"la delta en {var} = {t0} cae justo en el salto de "
                                      f"u({arg}): declara u(0) (0, 1/2 o 1)")
        return u0
    return Fraction(1) if v > 0 else Fraction(0)


def _derivadas(coef: mx.Expr, var: str, k: int) -> list[mx.Expr]:
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    salida = [coef]
    for _ in range(k):
        salida.append(_limpio(DM.differentiate(salida[-1], var)))
    return salida


def _cribar(coef: mx.Expr, var: str, t0: Punto, k: int, escala: mx.Expr,
            trace: Trace) -> list[Impulso]:
    """f(t)·δ⁽ᵏ⁾(t − t₀) = Σⱼ (−1)ʲ·C(k, j)·f⁽ʲ⁾(t₀)·δ⁽ᵏ⁻ʲ⁾(t − t₀) (Leibniz)."""
    if not mx.depends(coef, var):
        return [Impulso(t0, _limpio(mx.Mul(coef, escala)), k)]
    derivadas = _derivadas(coef, var, k)
    salida = []
    for j in range(k + 1):
        valor = mx.substitute(derivadas[j], var, t0.expr)
        if mx.evaluate(valor) is None:
            raise _error("UNDEFINED", f"el coeficiente de δ (o su derivada {j}ª) no existe "
                                      f"en {var} = {t0}")
        area = _limpio(mx.Mul(mx.num((-1) ** j * math.comb(k, j)), mx.Mul(valor, escala)))
        if not _es_cero(area):
            salida.append(Impulso(t0, area, k - j))
    ley = ("f(t)·δ(t − t₀) = f(t₀)·δ(t − t₀)" if k == 0 else
           "f·δ⁽ᵏ⁾(t − t₀) = Σ (−1)ʲ C(k,j) f⁽ʲ⁾(t₀) δ⁽ᵏ⁻ʲ⁾(t − t₀)")
    trace.regla("delta.criba", f"{mx.text(coef)}·δ{_primas(k)}({_desplazado(var, t0)}) → "
                               + " + ".join(f"({mx.text(i.area)})·δ{_primas(i.orden)}"
                                            for i in salida),
                why=f"propiedad de cribado: {ley}")
    return salida


def _delta_de_g(e: mx.Expr, var: str, arg: str, k: int, trace: Trace) -> list[Impulso]:
    """δ⁽ᵏ⁾(g(t)) for g with simple real roots.

    δ(g) = Σ δ(t − tᵢ)/|g′(tᵢ)|, and since d/dt δ⁽ʲ⁾(g) = g′·δ⁽ʲ⁺¹⁾(g),
    δ⁽ʲ⁺¹⁾(g) = (1/g′)·d/dt δ⁽ʲ⁾(g): each step differentiates the impulses and
    multiplies by 1/g′ (smooth at simple roots) with the Leibniz sifting rule.
    """
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    dg = _limpio(DM.differentiate(e, var))
    base: list[Impulso] = []
    for r, mult in _raices_reales(None, var, arg):
        if mult > 1:
            raise _error("UNDEFINED", f"δ({arg}): {r} es raíz múltiple de g y allí "
                                      "δ(g) no está definida (g′ = 0)")
        pendiente = _limpio(mx.substitute(dg, var, r.expr))
        valor = mx.valor_real(pendiente, {})
        # |g′(tᵢ)| exactly: the sign is known from the value, so no abs() is left
        modulo = pendiente if valor > 0 else _limpio(mx.Neg(pendiente))
        base.append(Impulso(r, _limpio(mx.Div(mx.num(1), modulo)), 0))
    trace.regla("delta.composicion",
                f"δ({arg}) = " + (" + ".join(f"δ({_desplazado(var, i.posicion)})·"
                                            f"{mx.text(i.area)}" for i in base) or "0"),
                why="δ(g(t)) = Σ δ(t − tᵢ)/|g′(tᵢ)| sobre las raíces reales simples de g")
    inversa = _limpio(mx.Div(mx.num(1), dg))
    for j in range(k):
        siguiente: list[Impulso] = []
        for imp in base:
            siguiente.extend(_cribar(inversa, var, imp.posicion, imp.orden + 1, imp.area, trace))
        base = siguiente
        trace.regla("delta.composicion_derivada",
                    f"δ{_primas(j + 1)}({arg}) = (1/g′)·d/dt δ{_primas(j)}({arg})",
                    why="d/dt δ⁽ʲ⁾(g(t)) = g′(t)·δ⁽ʲ⁺¹⁾(g(t)) (regla de la cadena)")
    return base


def leer(texto: str, var: str = "t", trace: Trace | None = None,
         u0: Fraction | None = None) -> Distribucion:
    """``u0`` is the declared value of the step at its jump, needed only when a
    delta sits exactly there (δ(t)·u(t))."""
    trace = trace if trace is not None else Trace()
    piezas: list[Tramo] = []
    impulsos: list[Impulso] = []
    for signo, termino in _terminos(texto.replace("**", "^")):
        encontrados = list(_DISTRIBUCION.finditer(termino))
        deltas = [m for m in encontrados if m.group(1).lower() in ("delta", "δ")]
        if len(deltas) > 1:
            raise _no(f"«{termino}» multiplica dos deltas: δ·δ no está definido")
        escalones, delta = [], None
        resto, cursor = "", 0
        for m in encontrados:
            if m.start() < cursor:
                raise _no(f"en «{termino}» hay una δ o una u dentro de otra")
            arg, fin = _argumento(termino, m.end())
            antes = termino[cursor:m.start()]
            nivel_previo = termino[:m.start()].count("(") - termino[:m.start()].count(")")
            izquierda = termino[:m.start()].rstrip()
            derecha = termino[fin:].lstrip()
            if (nivel_previo or (izquierda and not izquierda.endswith("*"))
                    or (derecha and not derecha.startswith(("*", "/")))):
                raise _no(f"en «{termino}» la δ o la u tiene que ser un factor que multiplica; "
                          "dentro de otra función o dividiendo no es una distribución")
            primas = len(m.group(2))
            nombre = m.group(1).lower()
            if nombre not in ("delta", "δ") and primas:
                raise _no("u′ es δ: escríbelo como delta")
            if nombre in ("delta", "δ"):
                delta = (arg, primas)
            else:
                escalones.append(arg)
            resto += antes + "1"
            cursor = fin
        resto += termino[cursor:]
        resto = re.sub(r"(?<![\w.])1\s*\*\s*", "", resto).strip()
        resto = re.sub(r"\*\s*1(?![\w.^])", "", resto).strip() or "1"
        if resto.startswith(("*", "/")):
            resto = "1" + resto
        coef = mx.parse(resto)
        if signo < 0:
            coef = mx.Neg(coef)
        if delta is None:
            zonas = [(None, None)]
            for arg in escalones:
                e = (mx.parse(arg) if _lineal_exacto(arg, var) is not None
                     else _polinomio(arg, var)[0])
                zonas = _interseca(zonas, _positivo(e, var, arg))
            piezas.extend(Tramo(a, b, coef) for a, b in zonas)
            continue
        arg, k = delta
        if k > MAX_ORDEN:
            raise _no(f"δ de orden {k} > {MAX_ORDEN}")
        general = _lineal_exacto(arg, var)
        if general is not None:
            a, c = general
            lineal = (a, c)
            t0 = Punto(_limpio(mx.Div(mx.Neg(c), mx.num(a))))
        else:
            e, p = _polinomio(arg, var)
            lineal = _lineal(p, var)
            if lineal is not None:
                a, c = lineal
                t0 = Punto(-c / a)
        if lineal is not None:
            base = [Impulso(t0, mx.num(Fraction(1) / (a ** k * abs(a))), k)]
            if a != 1:
                trace.regla("delta.escala",
                            f"δ{_primas(k)}({arg}) = δ{_primas(k)}({_desplazado(var, t0)})"
                            f"·{Fraction(1) / (a ** k * abs(a))}",
                            why="δ⁽ᵏ⁾(a·t − b) = δ⁽ᵏ⁾(t − b/a)/(aᵏ·|a|): el área se reparte al "
                                "comprimir y cada derivada saca un factor a")
        else:
            base = _delta_de_g(e, var, arg, k, trace)
        for imp in base:
            factor = Fraction(1)
            for arg_u in escalones:
                factor *= _escalon_en(arg_u, var, imp.posicion, u0)
            if escalones:
                trace.regla("delta.escalon", f"los escalones valen {factor} en "
                                             f"{var} = {imp.posicion}",
                            why="la delta solo ve el valor de los demás factores en su punto")
            if factor == 0:
                continue
            impulsos.extend(_cribar(coef, var, imp.posicion, imp.orden,
                                    _limpio(mx.Mul(mx.num(factor), imp.area)), trace))
    return _normalizar(var, piezas, impulsos)


def _normalizar(var: str, piezas, impulsos) -> Distribucion:
    cortes = sorted({x for p in piezas for x in (p.desde, p.hasta) if x is not None},
                    key=lambda p: p.x)
    bordes: list[Punto | None] = [None] + cortes + [None]
    tramos = []
    for i in range(len(bordes) - 1):
        a, b = bordes[i], bordes[i + 1]
        if a is not None and b is not None:
            medio = (a.x + b.x) / 2
        elif a is None and b is None:
            medio = 0.0
        elif a is None:
            medio = b.x - 1
        else:
            medio = a.x + 1
        total: mx.Expr = mx.num(0)
        for p in piezas:
            if p.contiene(medio):
                total = _suma(total, p.expr)
        tramos.append(Tramo(a, b, total))
    juntos: dict[tuple[Punto, int], mx.Expr] = {}
    for imp in impulsos:
        clave = (imp.posicion, imp.orden)
        juntos[clave] = _suma(juntos.get(clave, mx.num(0)), imp.area)
    lista = sorted(((p, k, a) for (p, k), a in juntos.items() if not _es_cero(a)),
                   key=lambda pka: (pka[0].x, -pka[1]))
    return Distribucion(var, _fusionar(tramos), tuple(Impulso(p, a, k) for p, k, a in lista))


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------


def _lado(tramo: Tramo, var: str, t0: Punto) -> mx.Expr:
    valor = mx.substitute(tramo.expr, var, t0.expr)
    if mx.evaluate(valor) is None:
        raise _no(f"la función no tiene límite finito en {var} = {t0}: el salto no es un "
                  "número y la derivada no es una delta con área")
    return valor


def derivada(D: Distribucion, trace: Trace | None = None) -> Distribucion:
    """Ordinary derivative on each piece, a delta of area «jump» at each break, and
    each δ⁽ᵏ⁾ becomes δ⁽ᵏ⁺¹⁾."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    trace = trace if trace is not None else Trace()
    tramos = tuple(Tramo(t.desde, t.hasta, _limpio(DM.differentiate(t.expr, D.var)))
                   for t in D.tramos)
    impulsos = []
    for izq, der in zip(D.tramos, D.tramos[1:]):
        t0 = izq.hasta
        salto = _limpio(mx.Sub(_lado(der, D.var, t0), _lado(izq, D.var, t0)))
        trace.regla("distribucion.salto",
                    f"salto en {D.var} = {t0}: f({t0}⁺) − f({t0}⁻) = {mx.text(salto)}",
                    why="la derivada de un salto de altura h es h·δ: el área de la delta "
                        "es el salto")
        if not _es_cero(salto):
            impulsos.append(Impulso(t0, salto, 0))
    for imp in D.impulsos:
        if imp.orden + 1 > MAX_ORDEN:
            raise _no(f"δ de orden {imp.orden + 1} > {MAX_ORDEN}")
        impulsos.append(Impulso(imp.posicion, imp.area, imp.orden + 1))
        trace.regla("delta.deriva", f"(δ{_primas(imp.orden)})′ = δ{_primas(imp.orden + 1)} en "
                                    f"{D.var} = {imp.posicion}",
                    why="la derivada distribucional de δ⁽ᵏ⁾ es δ⁽ᵏ⁺¹⁾")
    return _normalizar(D.var, [t for t in tramos], impulsos) if D.impulsos else \
        Distribucion(D.var, _fusionar(tramos), tuple(impulsos))


def integral(D: Distribucion, a, b, *, extremo: str | None = None,
             trace: Trace | None = None) -> mx.Expr:
    """∫ₐᵇ D. An impulse ON a limit is ambiguous (½ or 1 or 0 depending on the
    book); a delta there is refused unless ``extremo`` declares the convention:
    «incluye», «excluye» or «mitad». δ⁽ᵏ⁾ with k ≥ 1 integrates to 0 strictly inside,
    and on a limit no convention makes it meaningful: refused."""
    trace = trace if trace is not None else Trace()
    a, b = Punto(a), Punto(b)
    if a > b:
        return _limpio(mx.Neg(integral(D, b, a, extremo=extremo, trace=trace)))
    total: mx.Expr = mx.num(0)
    for t in D.tramos:
        lo = a if t.desde is None or t.desde < a else t.desde
        hi = b if t.hasta is None or t.hasta > b else t.hasta
        if lo >= hi or _es_cero(t.expr):
            continue
        valor = _integral_ordinaria(t.expr, D.var, lo, hi)
        trace.regla("distribucion.tramo", f"∫ de {lo} a {hi} de {mx.text(t.expr)} = "
                                          f"{mx.text(valor)}", why="parte ordinaria")
        total = _suma(total, valor)
    for imp in D.impulsos:
        t0, area = imp.posicion, imp.area
        dentro = a < t0 < b
        en_limite = t0 == a or t0 == b
        if imp.orden:
            if en_limite:
                raise _error("AMBIGUOUS", f"hay una δ{_primas(imp.orden)} justo en el límite "
                                          f"{t0}: su integral no está definida allí")
            if dentro:
                trace.regla("distribucion.doblete", f"∫ δ{_primas(imp.orden)} = 0 en {t0}",
                            why="∫ δ⁽ᵏ⁾ = δ⁽ᵏ⁻¹⁾ evaluada en los límites, que es 0 fuera de t₀")
            continue
        if dentro:
            trace.regla("distribucion.area", f"δ en {t0} dentro de ({a}, {b}): suma su área "
                                             f"{mx.text(area)}",
                        why="∫ A·δ(t − t₀) dt = A si t₀ está dentro del intervalo")
            total = _suma(total, area)
        elif en_limite:
            if extremo is None:
                raise _error("AMBIGUOUS", f"hay una delta justo en el límite {t0}: declara si "
                                          "se incluye, se excluye o cuenta la mitad "
                                          "(extremo = incluye | excluye | mitad)")
            factor = {"incluye": Fraction(1), "excluye": Fraction(0),
                      "mitad": Fraction(1, 2)}.get(extremo)
            if factor is None:
                raise _error("BAD_INPUT", f"extremo «{extremo}» desconocido")
            trace.convencion("distribucion.extremo",
                             f"delta en el límite {t0}: «{extremo}» (factor {factor})")
            total = _suma(total, _limpio(mx.Mul(mx.num(factor), area)))
    return total


def _integral_ordinaria(f: mx.Expr, var: str, a: Punto, b: Punto) -> mx.Expr:
    import academic_core.domain.engineering.mathlab as ML

    if not mx.depends(f, var):
        return _limpio(mx.Mul(f, mx.Sub(b.expr, a.expr)))
    r = ML.calcular(ML.Peticion("integrar", {"integrando": f, "var": var,
                                             "desde": mx.text(a.expr),
                                             "hasta": mx.text(b.expr)}))
    valor = r.exacto_expr if isinstance(r.exacto_expr, mx.Expr) else None
    if valor is None and isinstance(r.exacto, (int, Fraction)):
        valor = mx.num(r.exacto)
    if valor is None and isinstance(r.exacto, str):
        valor = mx.parse(r.exacto)
    if valor is None:
        raise _no(f"no sé integrar exactamente {mx.text(f)} entre {a} y {b}")
    if r.sello.verdict == "discrepa":
        raise _error("INTERNAL", "la integral de un tramo no pasa su verificación")
    return valor


def convolucion_con_impulsos(f: mx.Expr, D: Distribucion,
                             trace: Trace | None = None) -> mx.Expr:
    """f * Σ Aₖ·δ⁽ⁿ⁾(t − tₖ) = Σ Aₖ·f⁽ⁿ⁾(t − tₖ) — the ordinary part of D must be 0."""
    trace = trace if trace is not None else Trace()
    if any(not _es_cero(t.expr) for t in D.tramos):
        raise _no("solo la convolución con deltas y sus derivadas (sin parte ordinaria)")
    total: mx.Expr = mx.num(0)
    for imp in D.impulsos:
        g = _derivadas(f, D.var, imp.orden)[-1]
        desplazada = mx.substitute(g, D.var, mx.Sub(mx.Sym(D.var), imp.posicion.expr))
        trace.regla("delta.convolucion",
                    f"f * δ{_primas(imp.orden)}({_desplazado(D.var, imp.posicion)}) = "
                    f"f{_primas(imp.orden)}({_desplazado(D.var, imp.posicion)})",
                    why="convolucionar con δ⁽ⁿ⁾ desplaza la derivada n-ésima a donde está la delta")
        termino = desplazada if mx.exact_value(imp.area) == 1 else mx.Mul(imp.area, desplazada)
        total = _suma(total, termino)
    return _limpio(total)


def _coef(c: Fraction) -> str:
    if c == 1:
        return ""
    return f"{c}·" if c.denominator == 1 else f"({c})·"


def _fusionar(tramos) -> tuple[Tramo, ...]:
    """Adjacent pieces with the same formula are one piece."""
    salida: list[Tramo] = []
    for t in tramos:
        if salida and mx.text(salida[-1].expr) == mx.text(t.expr):
            salida[-1] = Tramo(salida[-1].desde, t.hasta, t.expr)
        else:
            salida.append(t)
    return tuple(salida)


@dataclass(frozen=True)
class Tren:
    """Σₖ A·δ(t − k·T): its Fourier transform is another train."""

    periodo: Fraction
    area: Fraction = Fraction(1)
    convencion: str = "f"     # §5.11: ordinary frequency f or angular ω
    pasos: Trace = field(default_factory=Trace)

    def transformada(self) -> str:
        T, A = self.periodo, self.area
        if T <= 0:
            raise _error("BAD_INPUT", "el periodo tiene que ser positivo")
        self.pasos.convencion("frecuencia", f"frecuencia = {self.convencion}")
        k = f"k/{T}" if T.denominator == 1 else f"k·{1 / T}"
        if self.convencion == "f":
            altura = A / T
            texto = f"{_coef(altura)}Σₖ δ(f − {k})"
            why = "X(f) = ∫x·e^{−j2πft}dt: la serie de Fourier de un tren tiene todos los cₖ = A/T"
        else:
            # ω = 2πf and δ(f − k/T) = 2π·δ(ω − 2πk/T)
            altura = 2 * A / T
            texto = f"{_coef(altura)}π·Σₖ δ(ω − 2π·{k})".replace("1π", "π") if altura == 1 \
                else f"{_coef(altura)}π·Σₖ δ(ω − 2π·{k})"
            why = "con ω, δ(f − f₀) = 2π·δ(ω − ω₀): aparece el 2π en el área"
        self.pasos.regla("tren.fourier", texto, why=why)
        return texto
