# SPDX-License-Identifier: MIT
"""ML-12 (§5.1): rational functions of several variables — ``H(s)`` with symbols.

The critical dependency of the other laboratories: a transfer function with ``R``,
``C``, ``K`` symbolic, written ``K·Π(s − z)/Π(s − p)``, its poles and zeros with
parameters, and the discussion by cases of a parameter. ``poly.as_ratio`` cancels
only in one variable and leaves ``(s² − a²)/(s − a)`` as it is; what was missing is
the GREATEST COMMON DIVISOR of polynomials in several variables, without which no
rational function can be put in lowest terms.

The gcd is the classical recursive one: a polynomial in ``x₁ … xₙ`` is seen as a
polynomial in ``x₁`` with coefficients in ``ℚ[x₂ … xₙ]``; content and primitive part
are taken recursively, and the primitive pseudo-remainder sequence gives the gcd of
the primitive parts. Every cancellation is checked by multiplying back, and the
normal form against the original at seeded points (§5.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError

Poly = P.Polynomial


def _sin_regla(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the univariate view of a multivariate polynomial
# ---------------------------------------------------------------------------


def variables(p: Poly) -> set[str]:
    return {nombre for m in p for nombre, _ in m}


def grado(p: Poly, v: str) -> int:
    return max((P.mono_exp(m, v) for m in p), default=-1) if p else -1


def coeficientes(p: Poly, v: str) -> dict[int, Poly]:
    """``p = Σ c_k·v^k`` → ``{k: c_k}``, each ``c_k`` free of ``v``."""
    salida: dict[int, Poly] = {}
    for m, c in p.items():
        k = P.mono_exp(m, v)
        resto = tuple((n, e) for n, e in m if n != v)
        salida.setdefault(k, {})[resto] = c
    return salida


def _potencia_de(v: str, k: int) -> Poly:
    return {((v, k),) if k else (): Fraction(1)}


def principal(p: Poly, v: str) -> Poly:
    """The leading coefficient in ``v``."""
    return coeficientes(p, v).get(grado(p, v), {}) if p else {}


def _resta(a: Poly, b: Poly) -> Poly:
    return P.add(a, b, -1)


# ---------------------------------------------------------------------------
# exact division, pseudo-remainder, gcd
# ---------------------------------------------------------------------------


def division_exacta(a: Poly, b: Poly, orden: list[str]) -> Poly | None:
    """``a / b`` when it is a polynomial, else ``None``; recursive in ``orden``."""
    if not b:
        raise ZeroDivisionError
    if not a:
        return {}
    presentes = [v for v in orden if v in variables(a) | variables(b)]
    if not presentes:
        return P.const(a.get((), Fraction(0)) / b[()])
    v, resto_orden = presentes[0], presentes[1:]
    cociente: Poly = {}
    r = dict(a)
    db = grado(b, v)
    lcb = principal(b, v)
    for _ in range(4 * (grado(a, v) + 2)):
        if not r or grado(r, v) < db:
            break
        t = division_exacta(principal(r, v), lcb, resto_orden)
        if t is None:
            return None
        termino = P.mul(t, _potencia_de(v, grado(r, v) - db))
        cociente = P.add(cociente, termino)
        r = _resta(r, P.mul(termino, b))
    return cociente if not r else None


def _pseudo_resto(a: Poly, b: Poly, v: str) -> Poly:
    db, lcb = grado(b, v), principal(b, v)
    r = dict(a)
    vueltas = grado(a, v) - db + 1
    while r and grado(r, v) >= db:
        termino = P.mul(principal(r, v), _potencia_de(v, grado(r, v) - db))
        r = _resta(P.mul(lcb, r), P.mul(termino, b))
        vueltas -= 1
    for _ in range(max(vueltas, 0)):
        r = P.mul(lcb, r)
    return r


def _normaliza(p: Poly, orden: list[str]) -> Poly:
    """Scaled so its leading term (lex by ``orden``) has coefficient 1."""
    if not p:
        return p

    def clave(m):
        return tuple(P.mono_exp(m, v) for v in orden)

    lider = max(p, key=clave)
    return P.scale(p, 1 / p[lider])


def contenido(p: Poly, v: str, orden: list[str]) -> Poly:
    g: Poly = {}
    for c in coeficientes(p, v).values():
        g = mcd(g, c, orden)
        if g == P.const(1):
            break
    return g


def mcd(a: Poly, b: Poly, orden: list[str] | None = None) -> Poly:
    """Greatest common divisor in ℚ[x₁ … xₙ], normalised (leading coefficient 1)."""
    if orden is None:
        orden = sorted(variables(a) | variables(b))
    if not a:
        return _normaliza(b, orden)
    if not b:
        return _normaliza(a, orden)
    presentes = [v for v in orden if v in variables(a) | variables(b)]
    if not presentes:
        return P.const(1)
    v, resto_orden = presentes[0], presentes[1:]
    ca, cb = contenido(a, v, resto_orden), contenido(b, v, resto_orden)
    c = mcd(ca, cb, resto_orden)
    pa = division_exacta(a, ca, presentes) if ca else a
    pb = division_exacta(b, cb, presentes) if cb else b
    if grado(pa, v) < grado(pb, v):
        pa, pb = pb, pa
    while pb and grado(pb, v) > 0:
        r = _pseudo_resto(pa, pb, v)
        if not r:
            break
        pa = pb
        cr = contenido(r, v, resto_orden)
        pb = division_exacta(r, cr, presentes) if cr else r
    if pb and grado(pb, v) <= 0:
        g = P.const(1)
    else:
        g = pa if not pb else pb
        cg = contenido(g, v, resto_orden)
        g = division_exacta(g, cg, presentes) if cg else g
    return _normaliza(P.mul(g, c), presentes)


# ---------------------------------------------------------------------------
# the rational function
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Raiz:
    valor: mx.Expr
    multiplicidad: int
    #: «real», «compleja», or a condition on the parameters («si Δ > 0 …»)
    naturaleza: str


@dataclass(frozen=True)
class FormaNormal:
    variable: str
    numerador: Poly
    denominador: Poly
    cancelado: Poly
    ganancia: mx.Expr
    ceros: tuple[Raiz, ...]
    polos: tuple[Raiz, ...]
    discusion: tuple[str, ...]
    completo: bool

    def expresion(self) -> mx.Expr:
        n, d = _expr(self.numerador), _expr(self.denominador)
        return n if self.denominador == P.const(1) else mx.Div(n, d)

    def factorizada(self) -> str:
        return _signos(self._factorizada())

    def _factorizada(self) -> str:
        v = self.variable

        def factor(r: Raiz) -> str:
            q = mx.exact_value(r.valor)
            texto = mx.pretty(r.valor)
            simple = not any(op in texto[1:] for op in (" + ", " - ", " − "))
            if q is not None:
                base = v if q == 0 else (f"({v} + {-q})" if q < 0 else f"({v} − {q})")
            elif texto.startswith("-") and simple:
                base = f"({v} + {texto[1:]})"
            elif simple:
                base = f"({v} − {texto})"
            else:
                base = f"({v} − ({texto}))"
            return base + (f"^{r.multiplicidad}" if r.multiplicidad > 1 else "")

        if not self.completo:
            return mx.text(self.expresion())
        arriba = "·".join(factor(r) for r in self.ceros)
        abajo = "·".join(factor(r) for r in self.polos)
        k = "" if mx.exact_value(self.ganancia) == 1 else mx.pretty(self.ganancia)
        if "/" in k or " " in k:
            k = f"({k})"
        cuerpo = arriba or "1"
        if abajo:
            cuerpo = f"{cuerpo}/({abajo})" if "·" in abajo else f"{cuerpo}/{abajo}"
        return f"{k}·{cuerpo}" if k else cuerpo


def _signos(texto: str) -> str:
    """«a + -b» reads «a − b»."""
    # «−» tipográfico en este módulo; pretty() ya escribe «a - b» en vez de «a + -b»
    return texto.replace("+ -", "− ").replace("- -", "+ ").replace(" - ", " − ")


def _expr(p: Poly) -> mx.Expr:
    """``poly.to_expr`` without its ``c*1`` for constant terms."""
    return _sin_unos(P.to_expr(p)) if p else mx.ZERO


def _sin_unos(e: mx.Expr) -> mx.Expr:
    if isinstance(e, mx.Mul):
        a, b = _sin_unos(e.left), _sin_unos(e.right)
        if mx.exact_value(b) == 1:
            return a
        if mx.exact_value(a) == 1:
            return b
        return mx.Mul(a, b)
    if isinstance(e, (mx.Add, mx.Sub, mx.Div)):
        return type(e)(_sin_unos(e.left), _sin_unos(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_unos(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sin_unos(e.base), e.exponent)
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _sin_unos(e.radicand))
    return e


def raiz_cuadrada_exacta(p: Poly, orden: list[str]) -> Poly | None:
    """``q`` with ``q² = p`` exactly, by the long-division square root, or ``None``."""
    if not p:
        return {}

    def clave(m):
        return tuple(P.mono_exp(m, v) for v in orden)

    lider = max(p, key=clave)
    c = p[lider]
    if c < 0 or any(e % 2 for _, e in lider):
        return None
    num, den = c.numerator, c.denominator
    rn, rd = int(round(num ** 0.5)), int(round(den ** 0.5))
    if rn * rn != num or rd * rd != den:
        return None
    q: Poly = {tuple((n, e // 2) for n, e in lider): Fraction(rn, rd)}
    resto = _resta(p, P.mul(q, q))
    q_lider = max(q, key=clave)
    for _ in range(64):
        if not resto:
            return q
        m = max(resto, key=clave)
        cociente = P.mono_div(m, q_lider)
        if cociente is None:
            return None
        t = {cociente: resto[m] / (2 * q[q_lider])}
        resto = _resta(resto, P.add(P.mul(P.scale(q, 2), t), P.mul(t, t)))
        q = P.add(q, t)
    return None


def _a_poly_racional(expr: mx.Expr, var: str) -> tuple[Poly, Poly]:
    razon = P.as_ratio(expr, var)
    if razon is None:
        raise _sin_regla(f"«{mx.text(expr)}» no es una función racional")
    for parte in (razon.numerator, razon.denominator):
        if any(P.is_atom(n) for m in parte for n, _ in m):
            raise _sin_regla(f"«{mx.text(expr)}» contiene funciones que no son polinomios: "
                             "no es una función racional")
    return razon.numerator, razon.denominator


def _raices(p: Poly, var: str) -> tuple[tuple[Raiz, ...], tuple[str, ...], bool]:
    """Roots in ``var``: degree 1 and 2 with symbolic coefficients, more if numeric."""
    from academic_core.domain.engineering.mathlab import ecuaciones as E

    n = grado(p, var)
    if n <= 0:
        return (), (), True
    c = coeficientes(p, var)
    # repeated factors: a root of p and p' is multiple
    derivada = {}
    for k, ck in c.items():
        if k:
            derivada = P.add(derivada, P.mul(P.scale(ck, k), _potencia_de(var, k - 1)))
    repetido = mcd(p, derivada, [var] + sorted(variables(p) - {var}))
    if grado(repetido, var) > 0:
        simple = division_exacta(p, repetido, [var] + sorted(variables(p) - {var}))
        a, ga, _ = _raices(simple, var)
        b, gb, cb = _raices(repetido, var)
        juntas: dict[str, Raiz] = {}
        for r in (*a, *b):
            clave = mx.text(r.valor)
            previa = juntas.get(clave)
            juntas[clave] = Raiz(r.valor, (previa.multiplicidad if previa else 0) + 1,
                                 r.naturaleza)
        return tuple(juntas.values()), ga + gb, cb
    def ex(q: Poly) -> mx.Expr:
        return _expr(q)
    if not c.get(0):
        # var^k divides p: 0 is a root, and the rest has a non-zero constant term
        k = min(c)
        resto = {tuple((nm, e - (k if nm == var else 0)) for nm, e in m
                       if not (nm == var and e == k)): cf for m, cf in p.items()}
        resto = {tuple(sorted(m)): cf for m, cf in resto.items()}
        otras, dis, completo = _raices(resto, var)
        return (Raiz(mx.ZERO, k, "real"), *otras), dis, completo
    if n == 1:
        valor = _plegar(mx.Div(mx.Neg(ex(c.get(0, {}))), ex(c[1])))
        return (Raiz(valor, 1, "real"),), (), True
    numericos = not variables(p) - {var}
    if numericos and n == 2:
        a2, a1, a0 = (c.get(k, {}).get((), Fraction(0)) for k in (2, 1, 0))
        delta_num = a1 * a1 - 4 * a2 * a0
        if delta_num < 0:
            # complex conjugate pair: the poles of 1/(s² + 4) are ±2i, and «no real
            # roots» is no answer for a transfer function
            from academic_core.domain.engineering.mathlab import ecuaciones as E_
            re_ = -a1 / (2 * a2)
            # sqrt(-Δ)/(2·|a|): _raiz_cuadratica returns sqrt(disc)/2 for c2 = 1, c1 = 0
            im_ = E_._raiz_cuadratica(Fraction(1), Fraction(0), -delta_num / (a2 * a2), 1)
            parte_i = mx.Mul(im_, mx.Const("i"))
            raices = []
            for signo in (1, -1):
                imag = parte_i if signo > 0 else mx.Neg(parte_i)
                raices.append(Raiz(imag if re_ == 0 else mx.Add(mx.Num(re_), imag), 1,
                                   "compleja conjugada"))
            return tuple(raices), (f"Δ = {delta_num} < 0: dos raíces complejas conjugadas",), True
    if numericos:
        u = mx.Sym("u")
        polinomio = {(((u.name, k),) if k else ()): ck.get((), Fraction(0))
                     for k, ck in c.items() if ck}
        raices, motivo = E._raices_reales(polinomio, u)
        if motivo:
            return tuple(Raiz(r, 1, "real") for r in raices), (motivo,), False
        reales = tuple(Raiz(r, 1, "real") for r in raices)
        return reales, (), len(reales) == n or n == 2
    if n == 2:
        a2, a1, a0 = ex(c.get(2, {})), ex(c.get(1, {})), ex(c.get(0, {}))
        delta_poly = _resta(P.mul(c.get(1, {}), c.get(1, {})),
                            P.scale(P.mul(c.get(2, {}), c.get(0, {})), 4))
        delta = ex(delta_poly)
        orden = sorted(variables(delta_poly))
        exacta = raiz_cuadrada_exacta(delta_poly, orden)
        raiz = ex(exacta) if exacta is not None else mx.Root(2, delta)
        mas = _plegar(mx.Div(mx.Add(mx.Neg(a1), raiz), mx.Mul(mx.Num(Fraction(2)), a2)))
        menos = _plegar(mx.Div(mx.Sub(mx.Neg(a1), raiz), mx.Mul(mx.Num(Fraction(2)), a2)))
        signo = _signo_con_parametros_positivos(delta_poly)
        texto = mx.text(delta)
        decide, fuera = _parte_que_decide(delta_poly)
        if exacta is not None:
            # each root is a quotient of polynomials: (-b ± r)/(2a), in lowest terms
            raices = []
            for signo in (1, -1):
                arriba = P.add(P.scale(c.get(1, {}), -1), P.scale(exacta, signo))
                abajo = P.scale(c.get(2, {}), 2)
                orden_r = sorted(variables(arriba) | variables(abajo)) or [var]
                g = mcd(arriba, abajo, orden_r) if arriba else P.const(1)
                arriba = division_exacta(arriba, g, orden_r) if arriba else arriba
                abajo = division_exacta(abajo, g, orden_r)
                # over ℚ the gcd has no numeric part: -2b/2 is cancelled by making
                # the denominator's leading coefficient 1
                lider = abajo[max(abajo, key=lambda m: tuple(P.mono_exp(m, x) for x in orden_r))]
                arriba, abajo = P.scale(arriba, 1 / lider), P.scale(abajo, 1 / lider)
                raices.append(ex(arriba) if abajo == P.const(1) else mx.Div(ex(arriba), ex(abajo)))
            mas, menos = raices
            return ((Raiz(mas, 1, "real"), Raiz(menos, 1, "real")),
                    (f"Δ = ({mx.text(ex(exacta))})² es un cuadrado: las dos raíces son "
                     "reales (iguales donde se anula)",), True)
        if signo == 1:
            naturaleza = "real (Δ > 0 para parámetros positivos)"
        elif signo == -1:
            naturaleza = "compleja conjugada (Δ < 0 para parámetros positivos)"
        else:
            naturaleza = "depende del signo de Δ"
        condicion = mx.pretty(ex(decide))
        if fuera:
            prefijo = (f"Δ = {mx.pretty(delta)} = {mx.pretty(ex(fuera))}·({condicion}); con "
                       f"{mx.pretty(ex(fuera))} > 0 decide el signo de {condicion}")
        else:
            prefijo = f"Δ = {mx.pretty(delta)}"
        discusion = (f"{prefijo}: {condicion} > 0, dos polos reales distintos; "
                     f"{condicion} = 0, uno doble; {condicion} < 0, dos complejos conjugados",)
        return (Raiz(mas, 1, naturaleza), Raiz(menos, 1, naturaleza)), discusion, True
    return (), (f"grado {n} en {var} con coeficientes simbólicos: no se factoriza aquí",), False


def _parte_que_decide(p: Poly) -> tuple[Poly, Poly]:
    """``p = fuera·decide`` with ``fuera`` a positive monomial factor (even powers or
    positive parameters): ``-4CL + C²R² = C·(CR² - 4L)``. Returns (decide, fuera)."""
    comunes = None
    for m in p:
        exps = dict(m)
        comunes = exps if comunes is None else {n: min(e, exps.get(n, 0))
                                                for n, e in comunes.items()}
    comunes = {n: e for n, e in (comunes or {}).items() if e}
    numerico = Fraction(0)
    from math import gcd
    for cf in p.values():
        numerico = Fraction(gcd(numerico.numerator, abs(cf.numerator)),
                            1) if numerico else abs(cf)
    mono = tuple(sorted(comunes.items()))
    fuera = {mono: Fraction(abs(numerico.numerator) or 1)} if (mono or numerico not in (0, 1)) else {}
    if not fuera:
        return p, {}
    decide = division_exacta(p, fuera, sorted(variables(p)))
    return (decide, fuera) if decide is not None else (p, {})


def _signo_con_parametros_positivos(p: Poly) -> int:
    """+1 / −1 when every coefficient has that sign (so the sign is fixed for
    positive parameters), 0 otherwise."""
    signos = {1 if c > 0 else -1 for c in p.values()}
    return signos.pop() if len(signos) == 1 else 0


def _plegar(e: mx.Expr) -> mx.Expr:
    try:
        razon = P.as_ratio(e, sorted(mx.variables(e))[0]) if mx.variables(e) else None
        if razon is not None and not any(P.is_atom(n) for m in razon.numerator
                                         for n, _ in m):
            g = mcd(razon.numerator, razon.denominator)
            orden = sorted(variables(razon.numerator) | variables(razon.denominator))
            n = division_exacta(razon.numerator, g, orden) if g else razon.numerator
            d = division_exacta(razon.denominator, g, orden) if g else razon.denominator
            if n is not None and d is not None:
                return P.to_expr(n) if d == P.const(1) else mx.Div(P.to_expr(n), P.to_expr(d))
        return P.to_expr(P.as_poly(e))
    except Exception:  # noqa: BLE001 - a radical: keep the exact form
        return e


def forma_normal(expr: mx.Expr, var: str, trace: Trace | None = None) -> FormaNormal:
    """``H(var)`` in lowest terms, with its gain, zeros and poles."""
    trace = trace if trace is not None else Trace()
    numerador, denominador = _a_poly_racional(expr, var)
    orden = [var] + sorted((variables(numerador) | variables(denominador)) - {var})
    g = mcd(numerador, denominador, orden)
    if g != P.const(1):
        numerador = division_exacta(numerador, g, orden)
        denominador = division_exacta(denominador, g, orden)
        trace.regla("racional.cancelar", f"se cancela el factor común {mx.text(P.to_expr(g))}",
                    before=mx.text(expr),
                    after=mx.text(mx.Div(P.to_expr(numerador), P.to_expr(denominador))),
                    why=("el mcd de numerador y denominador, calculado en todas las "
                         "variables, divide a los dos exactamente"),
                    conditions=(f"{mx.text(P.to_expr(g))} ≠ 0",))
    # the denominator's leading coefficient in var goes to the gain
    lider_n, lider_d = principal(numerador, var), principal(denominador, var)
    ganancia = _sin_unos(_plegar(mx.Div(_expr(lider_n), _expr(lider_d))))
    ceros, dis_n, completo_n = _raices(numerador, var)
    polos, dis_d, completo_d = _raices(denominador, var)
    forma = FormaNormal(var, numerador, denominador, g, ganancia, ceros, polos,
                        tuple(_signos(d) for d in dis_n + dis_d), completo_n and completo_d)
    trace.regla("racional.forma_normal", "forma K·Π(s − z)/Π(s − p)",
                after=forma.factorizada(),
                why=("K es el cociente de los coeficientes principales; los ceros y polos "
                     "son las raíces de numerador y denominador ya sin factores comunes"))
    for texto in forma.discusion:
        trace.hipotesis("racional.discusion", texto, "por casos")
    _verifica(expr, forma, var)
    trace.verificacion("racional.puntos", "la forma normal coincide con la original en "
                       "puntos sembrados de todas las variables, y cada cero y polo anula "
                       "su polinomio")
    return forma


def _verifica(expr: mx.Expr, forma: FormaNormal, var: str) -> None:
    from academic_core.domain.engineering.mathlab import verify as V

    nombres = sorted(mx.variables(expr) | {var})
    # the domain's own seeded sampler: no random generator in the domain layer
    puntos = V.sampled_points(nombres, count=12)
    for punto in puntos[:6]:
        a = mx.valor_real(expr, punto)
        b = mx.valor_real(forma.expresion(), punto)
        if a is not None and b is not None and abs(a - b) > 1e-8 * max(1.0, abs(a)):
            raise _sin_regla("la forma normal no coincide con la original (error interno)")
    for raices, poly in ((forma.ceros, forma.numerador), (forma.polos, forma.denominador)):
        for i, r in enumerate(raices):
            punto = {n: abs(v) + 0.3 for n, v in puntos[6 + i % 6].items() if n != var}
            valor = mx.evaluate(r.valor, punto)
            if valor is None:
                continue
            residuo = mx.evaluate(P.to_expr(poly), {**punto, var: valor})
            if residuo is not None and abs(residuo) > 1e-7 * max(1.0, abs(valor) ** grado(poly, var)):
                raise _sin_regla("una raíz no anula su polinomio (error interno)")
