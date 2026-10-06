# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): distributions with AREA — Dirac deltas, steps and trains of deltas.

A distribution here is an ordinary piecewise function plus a finite list of
impulses ``A·δ(t − t₀)``. That is exactly what Signals and Systems needs: the
derivative of a function with jumps (each jump becomes a delta whose area is the
jump), the sifting property, ``δ(a·t − b) = δ(t − b/a)/|a|``, convolution with a
delta (a shift), integrals that cross an impulse, and the Fourier transform of a
train of deltas.

Input text is a sum of terms; each term is a product of ordinary factors and at
most one ``delta(...)`` or ``u(...)``/``escalon(...)`` whose argument is linear in the
variable with rational coefficients (``3*delta(2*t-1)``, ``t*u(t-2)``,
``-u(1-t)``). Anything else — a delta inside another function, ``δ(t²−1)``, the
derivative of a delta — is refused with the reason, never approximated.

Second paths: the jumps and the impulse areas are recomputed by evaluating each
side of the breakpoint; the integral of the derivative is checked against the
increment of the function (fundamental theorem with the impulses counted).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

INF = None   # an open end of a piece


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# the object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tramo:
    desde: Fraction | None        # None = −∞
    hasta: Fraction | None        # None = +∞
    expr: mx.Expr

    def contiene(self, t: Fraction) -> bool:
        return (self.desde is None or self.desde < t) and (self.hasta is None or t < self.hasta)


@dataclass(frozen=True)
class Distribucion:
    var: str
    tramos: tuple[Tramo, ...] = ()               # disjoint, sorted, zero outside
    impulsos: tuple[tuple[Fraction, mx.Expr], ...] = ()   # (t₀, area), sorted

    def texto(self) -> str:
        partes = []
        for t in self.tramos:
            if _es_cero(t.expr):
                continue
            a = "−∞" if t.desde is None else str(t.desde)
            b = "+∞" if t.hasta is None else str(t.hasta)
            partes.append(f"{mx.text(t.expr)} en ({a}, {b})")
        for t0, area in self.impulsos:
            delta = f"δ({_desplazado(self.var, t0)})"
            v = mx.exact_value(area)
            if v == 1:
                partes.append(delta)
            elif v == -1:
                partes.append("−" + delta)
            else:
                partes.append(f"{_texto_area(area)}·{delta}")
        return " + ".join(partes).replace("+ −", "− ") if partes else "0"

    def ordinaria(self, t: Fraction) -> mx.Expr | None:
        for tramo in self.tramos:
            if tramo.contiene(t):
                return tramo.expr
        return None


def _desplazado(var: str, t0: Fraction) -> str:
    if t0 == 0:
        return var
    return f"{var} − {t0}" if t0 > 0 else f"{var} + {-t0}"


def _texto_area(area: mx.Expr) -> str:
    texto = mx.text(area)
    v = mx.exact_value(area)
    if v is not None and v.denominator == 1:
        return texto
    return texto if isinstance(area, (mx.Sym, mx.Const)) else f"({texto})"


def _es_cero(e: mx.Expr) -> bool:
    v = mx.exact_value(e)
    return v is not None and v == 0


def _limpio(e: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import calculators as K

    try:
        return K._presentable(e, Trace())
    except Exception:  # noqa: BLE001 - the raw form is still right
        return e


def _suma(a: mx.Expr, b: mx.Expr) -> mx.Expr:
    if _es_cero(a):
        return b
    if _es_cero(b):
        return a
    return _limpio(mx.Add(a, b))


# ---------------------------------------------------------------------------
# reading the text
# ---------------------------------------------------------------------------


_DISTRIBUCION = re.compile(r"(delta|δ|u|escalon|heaviside)\s*\(", re.IGNORECASE)


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
        elif nivel == 0 and ch in "+-" and previo == "" :
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


def _lineal(arg: str, var: str) -> tuple[Fraction, Fraction]:
    """``a·t + c`` → (a, c), rational, or refused."""
    from academic_core.domain.engineering.mathlab import poly as P

    e = mx.parse(arg)
    try:
        p = P.as_poly(e)
    except Exception:
        p = None
    if p is None or set(mx.variables(e)) - {var}:
        raise _no(f"el argumento «{arg}» tiene que ser lineal en {var} con coeficientes "
                  "racionales")
    a, c = Fraction(0), Fraction(0)
    for mono, coef in p.items():
        if mono == ():
            c = Fraction(coef)
        elif mono == ((var, 1),):
            a = Fraction(coef)
        else:
            raise _no(f"δ o u de «{arg}»: solo argumentos lineales (a·{var} − b); "
                      "δ(g(t)) con g no lineal no está implementado")
    if a == 0:
        raise _no(f"«{arg}» no depende de {var}")
    return a, c


def leer(texto: str, var: str = "t", trace: Trace | None = None) -> Distribucion:
    trace = trace if trace is not None else Trace()
    piezas: list[Tramo] = []
    impulsos: list[tuple[Fraction, mx.Expr]] = []
    for signo, termino in _terminos(texto.replace("**", "^")):
        encontrados = list(_DISTRIBUCION.finditer(termino))
        if len(encontrados) > 1:
            raise _no(f"«{termino}» multiplica dos distribuciones (δ·δ o δ·u no está "
                      "definido en general)")
        if not encontrados:
            f = mx.parse(termino)
            piezas.append(Tramo(None, None, f if signo > 0 else mx.Neg(f)))
            continue
        m = encontrados[0]
        nombre = m.group(1).lower()
        arg, fin = _argumento(termino, m.end())
        antes, despues = termino[:m.start()].rstrip(), termino[fin:].lstrip()
        if (antes.count("(") != antes.count(")") or (antes and not antes.endswith("*"))
                or (despues and not despues.startswith(("*", "/")))):
            raise _no(f"en «{termino}» la δ o la u tiene que ser un factor que multiplica; "
                      "dentro de otra función o dividiendo no es una distribución con área")
        resto = (termino[:m.start()] + "1" + termino[fin:]).strip()
        resto = re.sub(r"\*\s*1\s*$", "", re.sub(r"^\s*1\s*\*", "", resto)) or "1"
        coef = mx.parse(resto)
        if signo < 0:
            coef = mx.Neg(coef)
        a, c = _lineal(arg, var)
        t0 = -c / a
        if nombre in ("delta", "δ"):
            # δ(a·t + c) = δ(t − t₀)/|a| and then f(t)·δ(t − t₀) = f(t₀)·δ(t − t₀)
            valor = mx.substitute(coef, var, mx.num(t0))
            if mx.evaluate(valor) is None:
                raise _error("UNDEFINED", f"el coeficiente de δ no existe en {var} = {t0}")
            area = _limpio(mx.Div(valor, mx.num(abs(a))))
            if abs(a) != 1:
                trace.regla("delta.escala", f"δ({arg}) = δ({_desplazado(var, t0)})/{abs(a)}",
                            why="δ(a·t − b) = δ(t − b/a)/|a|: el área se reparte al comprimir")
            if mx.depends(coef, var):
                trace.regla("delta.criba", f"{mx.text(coef)}·δ({_desplazado(var, t0)}) = "
                                           f"{mx.text(valor)}·δ({_desplazado(var, t0)})",
                            why="propiedad de cribado: la delta solo ve el valor en t₀")
            impulsos.append((t0, area))
        else:
            # u(a·t + c) is 1 where a·t + c > 0: to the right of t₀ if a > 0
            piezas.append(Tramo(t0, None, coef) if a > 0 else Tramo(None, t0, coef))
    return _normalizar(var, piezas, impulsos)


def _normalizar(var: str, piezas, impulsos) -> Distribucion:
    cortes = sorted({x for p in piezas for x in (p.desde, p.hasta) if x is not None})
    bordes: list[Fraction | None] = [None] + cortes + [None]
    tramos = []
    for i in range(len(bordes) - 1):
        a, b = bordes[i], bordes[i + 1]
        if a is not None and b is not None:
            medio = (a + b) / 2
        elif a is None and b is None:
            medio = Fraction(0)
        elif a is None:
            medio = b - 1
        else:
            medio = a + 1
        total: mx.Expr = mx.num(0)
        for p in piezas:
            if p.contiene(medio):
                total = _suma(total, p.expr)
        tramos.append(Tramo(a, b, total))
    juntos: dict[Fraction, mx.Expr] = {}
    for t0, area in impulsos:
        juntos[t0] = _suma(juntos.get(t0, mx.num(0)), area)
    return Distribucion(var, _fusionar(tramos),
                        tuple((t0, a) for t0, a in sorted(juntos.items()) if not _es_cero(a)))


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------


def _lado(tramo: Tramo, var: str, t0: Fraction) -> mx.Expr:
    valor = mx.substitute(tramo.expr, var, mx.num(t0))
    if mx.evaluate(valor) is None:
        raise _no(f"la función no tiene límite finito en {var} = {t0}: el salto no es un "
                  "número y la derivada no es una delta con área")
    return valor


def derivada(D: Distribucion, trace: Trace | None = None) -> Distribucion:
    """Ordinary derivative on each piece + a delta of area «jump» at each break."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    trace = trace if trace is not None else Trace()
    if D.impulsos:
        raise _no("la derivada de una delta (δ′, el doblete) no está implementada")
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
            impulsos.append((t0, salto))
    return Distribucion(D.var, _fusionar(tramos), tuple(impulsos))


def integral(D: Distribucion, a: Fraction, b: Fraction, *, extremo: str | None = None,
             trace: Trace | None = None) -> mx.Expr:
    """∫ₐᵇ D. An impulse ON a limit is ambiguous (½ or 1 or 0 depending on the
    book); it is refused unless ``extremo`` declares the convention:
    «incluye», «excluye» or «mitad»."""
    trace = trace if trace is not None else Trace()
    if a > b:
        return mx.Neg(integral(D, b, a, extremo=extremo, trace=trace))
    total: mx.Expr = mx.num(0)
    for t in D.tramos:
        lo = a if t.desde is None else max(a, t.desde)
        hi = b if t.hasta is None else min(b, t.hasta)
        if lo >= hi or _es_cero(t.expr):
            continue
        valor = _integral_ordinaria(t.expr, D.var, lo, hi)
        trace.regla("distribucion.tramo", f"∫ de {lo} a {hi} de {mx.text(t.expr)} = "
                                          f"{mx.text(valor)}", why="parte ordinaria")
        total = _suma(total, valor)
    for t0, area in D.impulsos:
        if a < t0 < b:
            trace.regla("distribucion.area", f"δ en {t0} dentro de ({a}, {b}): suma su área "
                                             f"{mx.text(area)}",
                        why="∫ A·δ(t − t₀) dt = A si t₀ está dentro del intervalo")
            total = _suma(total, area)
        elif t0 in (a, b):
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


def _integral_ordinaria(f: mx.Expr, var: str, a: Fraction, b: Fraction) -> mx.Expr:
    import academic_core.domain.engineering.mathlab as ML

    if not mx.depends(f, var):
        return _limpio(mx.Mul(f, mx.num(b - a)))
    r = ML.calcular(ML.Peticion("integrar", {"integrando": f, "var": var,
                                             "desde": str(a), "hasta": str(b)}))
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
    """f * Σ Aₖ·δ(t − tₖ) = Σ Aₖ·f(t − tₖ) — the ordinary part of D must be 0."""
    trace = trace if trace is not None else Trace()
    if any(not _es_cero(t.expr) for t in D.tramos):
        raise _no("solo la convolución con un tren finito de deltas (sin parte ordinaria)")
    total: mx.Expr = mx.num(0)
    for t0, area in D.impulsos:
        desplazada = mx.substitute(f, D.var, mx.Sub(mx.Sym(D.var), mx.num(t0)))
        trace.regla("delta.convolucion", f"f * δ({_desplazado(D.var, t0)}) = "
                                         f"f({_desplazado(D.var, t0)})",
                    why="convolucionar con una delta desplaza la función a donde está la delta")
        total = _suma(total, mx.Mul(area, desplazada))
    return total


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
