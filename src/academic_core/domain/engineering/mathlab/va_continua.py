# SPDX-License-Identifier: MIT
"""ML-9 (§4.6, tipos 7 y 8 de §15.1): variables continuas dadas por su densidad.

Una densidad se da **por tramos** ``[(expresión, a, b), …]`` (extremos racionales o
``±oo``), con una constante por determinar si hace falta (``k·x²`` en [0, 1]).

- **Constante**: ``∫f = 1`` es lineal en la constante; se integra en exacto con el
  motor de ML-2 (primitiva comprobada derivando) y se despeja.
- **Momentos, F y probabilidades**: integrales exactas; F por tramos con el
  extremo superior simbólico.
- **Chebyshov**: la cota ``1/k²`` frente a la probabilidad exacta.
- **Transformaciones** ``Y = g(X)``: el soporte de X se parte por los ceros de g′
  en tramos monótonos; en cada uno se invierte g **simbólicamente** (se pela la
  expresión: sumas, productos, potencias, exp, ln) y
  ``f_Y(y) = Σ f_X(h(y))·|h′(y)|``.
- **Máximo y mínimo** de n independientes: ``F^n`` y ``1 − (1 − F)^n``.
- **Suma por convolución**: ``f_Z(z) = ∫ f_X(x)·f_Y(z − x) dx`` con los tramos de z
  por las sumas de los extremos.

Segundo camino de todo: cuadratura numérica independiente (tanh-sinh) y, para
las transformaciones y la suma, la simulación sembrada de X (por inversión
numérica de su F, que no usa el resultado que se comprueba).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import probabilidad as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


INF = None  # un extremo infinito se guarda como None


def _extremo(v) -> Fraction | None:
    t = str(v).strip().replace("−", "-").replace(" ", "")
    if t in ("oo", "+oo", "inf", "+inf", "∞", "+∞", "-oo", "-inf", "-∞"):
        return None
    return P.fraccion(v, "un extremo")


def _signo_inf(v) -> int:
    t = str(v).strip().replace("−", "-").replace(" ", "")
    return -1 if t.startswith("-") and t.lstrip("-") in ("oo", "inf", "∞") else 1


@dataclass(frozen=True)
class Tramo:
    expr: mx.Expr
    a: Fraction | None     # None = −∞
    b: Fraction | None     # None = +∞

    def contiene(self, x: float) -> bool:
        return (self.a is None or x >= self.a) and (self.b is None or x <= self.b)


def _txt_ext(v: Fraction | None, signo: int) -> str:
    if v is None:
        return "oo" if signo > 0 else "-oo"
    return str(v)


# ---------------------------------------------------------------------------
# exponenciales juntas y simplificación
# ---------------------------------------------------------------------------


def combina_exp(e: mx.Expr) -> mx.Expr:
    """``exp(a)·exp(b)·c`` → ``c·exp(a + b)`` con el exponente en forma normal; el
    integrador de ML-2 no junta exponenciales, y una convolución las multiplica."""
    from academic_core.domain.engineering.mathlab import poly as PO

    factores: list[mx.Expr] = []
    exponentes: list[mx.Expr] = []

    def recorre(x: mx.Expr, signo: list[int]):
        if isinstance(x, mx.Mul):
            recorre(x.left, signo)
            recorre(x.right, signo)
        elif isinstance(x, mx.Neg):
            signo[0] = -signo[0]
            recorre(x.arg, signo)
        elif isinstance(x, mx.Call) and x.name == "exp":
            exponentes.append(x.args[0])
        elif isinstance(x, mx.Pow) and x.base == mx.E:
            exponentes.append(x.exponent)
        else:
            factores.append(combina_exp(x) if isinstance(x, (mx.Add, mx.Sub, mx.Div)) else x)

    if isinstance(e, (mx.Add, mx.Sub)):
        return type(e)(combina_exp(e.left), combina_exp(e.right))
    if isinstance(e, mx.Div):
        return mx.Div(combina_exp(e.left), e.right)
    signo = [1]
    recorre(e, signo)
    if len(exponentes) < 2:
        return e
    arg = exponentes[0]
    for x in exponentes[1:]:
        arg = mx.Add(arg, x)
    try:
        arg = PO.to_expr(PO.as_poly(arg))
    except Exception:  # noqa: BLE001
        pass
    r: mx.Expr = mx.Call("exp", (arg,))
    for f in factores:
        r = mx.Mul(f, r)
    return mx.Neg(r) if signo[0] < 0 else r


def _exp_ln(e: mx.Expr) -> mx.Expr:
    """``exp(c·ln u) → u^c`` y ``ln(exp u) → u`` (lo que deja la inversa de exp)."""
    if isinstance(e, mx.Call):
        args = tuple(_exp_ln(a) for a in e.args)
        if e.name == "exp" and len(args) == 1:
            a = args[0]
            c, u = None, None
            if isinstance(a, mx.Call) and a.name == "ln":
                c, u = mx.ONE, a.args[0]
            elif isinstance(a, mx.Mul) and isinstance(a.right, mx.Call) and a.right.name == "ln" \
                    and not mx.variables(a.left):
                c, u = a.left, a.right.args[0]
            elif isinstance(a, mx.Neg) and isinstance(a.arg, mx.Call) and a.arg.name == "ln":
                c, u = mx.num(Fraction(-1)), a.arg.args[0]
            if u is None:
                c, u = _coef_ln(a)
            if u is not None:
                return mx.Pow(u, c) if c != mx.ONE else u
        if e.name == "ln" and len(args) == 1 and isinstance(args[0], mx.Call) \
                and args[0].name == "exp":
            return args[0].args[0]
        return mx.Call(e.name, args)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_exp_ln(e.left), _exp_ln(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_exp_ln(e.arg))
    if isinstance(e, mx.Pow):
        base, exp_ = _exp_ln(e.base), _exp_ln(e.exponent)
        m = mx.exact_value(exp_)
        if isinstance(base, mx.Neg) and m is not None and Fraction(m).denominator == 1 \
                and Fraction(m).numerator % 2 == 0:
            base = base.arg
        if isinstance(base, mx.Root) and m is not None and Fraction(m) % base.degree == 0:
            k = Fraction(m) / base.degree
            return base.radicand if k == 1 else mx.Pow(base.radicand, mx.num(k))
        return mx.Pow(base, exp_)
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _exp_ln(e.radicand))
    return e


def _coef_ln(a: mx.Expr):
    """``a = c·ln(u)`` con c constante → ``(c, u)``; si no, ``(None, None)``."""
    from academic_core.domain.engineering.mathlab import poly as PO

    lns = [n for n in _nodos(a) if isinstance(n, mx.Call) and n.name == "ln"]
    for n in lns:
        marca = mx.Sym("ʟ")
        b = _reemplaza(a, n, marca)
        if mx.depends(b, "ʟ") and not (mx.variables(b) - {"ʟ"}):
            try:
                pol = PO.as_poly(b)
                c = mx.exact_value(PO.to_expr(pol).__class__ and mx.substitute(b, "ʟ", mx.ONE))
                if c is not None and mx.exact_value(mx.substitute(b, "ʟ", mx.ZERO)) == 0 and \
                        mx.exact_value(mx.substitute(b, "ʟ", mx.num(Fraction(2)))) == 2 * c:
                    return mx.num(Fraction(c)), n.args[0]
            except Exception:  # noqa: BLE001
                continue
    return None, None


def _nodos(e: mx.Expr):
    yield e
    for campo in ("left", "right", "arg", "base", "exponent", "radicand"):
        h = getattr(e, campo, None)
        if isinstance(h, mx.Expr):
            yield from _nodos(h)
    for h in getattr(e, "args", ()) or ():
        if isinstance(h, mx.Expr):
            yield from _nodos(h)


def _reemplaza(e: mx.Expr, viejo: mx.Expr, nuevo: mx.Expr) -> mx.Expr:
    if e == viejo:
        return nuevo
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_reemplaza(e.left, viejo, nuevo), _reemplaza(e.right, viejo, nuevo))
    if isinstance(e, mx.Neg):
        return mx.Neg(_reemplaza(e.arg, viejo, nuevo))
    if isinstance(e, mx.Pow):
        return mx.Pow(_reemplaza(e.base, viejo, nuevo), _reemplaza(e.exponent, viejo, nuevo))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_reemplaza(a, viejo, nuevo) for a in e.args))
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _reemplaza(e.radicand, viejo, nuevo))
    return e


def _arg_normal(a: mx.Expr) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import poly as PO

    try:
        return PO.to_expr(PO.as_poly(a))
    except Exception:  # noqa: BLE001
        return a


def _reduce_periodo(e: mx.Expr) -> mx.Expr:
    """``sin(2kπ + u) → sin u``, ``cos((2k+1)π + u) → −cos u``, argumentos en forma normal."""
    if isinstance(e, mx.Call):
        args = tuple(_reduce_periodo(a) for a in e.args)
        nombre = "sin" if e.name == "sen" else e.name
        if nombre in ("sin", "cos") and len(args) == 1:
            a = _arg_normal(args[0])
            vars_ = mx.variables(a)
            c = a
            for v in vars_:
                c = mx.substitute(c, v, mx.ZERO)
            cv = mx.valor_real(c, {})
            if cv is not None and cv != 0:
                k = Fraction(cv / math.pi).limit_denominator(64)
                if abs(float(k) * math.pi - cv) < 1e-12 and k.denominator == 1:
                    resto = _arg_normal(mx.Sub(a, mx.Mul(mx.num(k), mx.PI)))
                    r = mx.Call(nombre, (resto,))
                    if k.numerator % 2:
                        r = mx.Neg(r)
                    return r
            return mx.Call(nombre, (a,))
        return mx.Call(e.name, args)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_reduce_periodo(e.left), _reduce_periodo(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_reduce_periodo(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_reduce_periodo(e.base), e.exponent)
    return e


def _monomios(e: mx.Expr):
    """Suma de monomios ``{(π^k, (átomo, potencia)…): coef}``; None si no cabe."""
    if isinstance(e, mx.Num):
        return {(0, ()): Fraction(e.value)}
    if e == mx.PI:
        return {(1, ()): Fraction(1)}
    if isinstance(e, mx.Neg):
        m = _monomios(e.arg)
        return None if m is None else {k: -v for k, v in m.items()}
    if isinstance(e, (mx.Add, mx.Sub)):
        a, b = _monomios(e.left), _monomios(e.right)
        if a is None or b is None:
            return None
        r = dict(a)
        for k, v in b.items():
            r[k] = r.get(k, Fraction(0)) + (v if isinstance(e, mx.Add) else -v)
        return {k: v for k, v in r.items() if v != 0}
    if isinstance(e, mx.Mul):
        a, b = _monomios(e.left), _monomios(e.right)
        if a is None or b is None:
            return None
        r: dict = {}
        for (pa, fa), va in a.items():
            for (pb, fb), vb in b.items():
                fs: dict = {}
                for t, n in fa + fb:
                    fs[t] = fs.get(t, 0) + n
                k = (pa + pb, tuple(sorted((t, n) for t, n in fs.items() if n)))
                r[k] = r.get(k, Fraction(0)) + va * vb
        return {k: v for k, v in r.items() if v != 0}
    if isinstance(e, mx.Div):
        a, b = _monomios(e.left), _monomios(e.right)
        if a is None or b is None or len(b) != 1:
            return None
        (pb, fb), vb = next(iter(b.items()))
        inv = {(-pb, tuple((t, -n) for t, n in fb)): 1 / vb}
        return _monomios_mul(a, inv)
    if isinstance(e, mx.Pow):
        n = mx.exact_value(e.exponent)
        if n is not None and Fraction(n).denominator == 1 and -8 <= n <= 8:
            base = _monomios(e.base)
            if base is not None and len(base) == 1:
                (pb, fb), vb = next(iter(base.items()))
                n = int(n)
                return {(pb * n, tuple((t, m * n) for t, m in fb)): vb ** n}
            return {(0, ((mx.text(e.base), int(n)),)): Fraction(1)} if not isinstance(
                e.base, (mx.Num,)) else None
    _ATOMOS[mx.text(e)] = e
    return {(0, ((mx.text(e), 1),)): Fraction(1)}


_ATOMOS: dict[str, mx.Expr] = {}


def _monomios_mul(a, b):
    r: dict = {}
    for (pa, fa), va in a.items():
        for (pb, fb), vb in b.items():
            fs: dict = {}
            for t, n in fa + fb:
                fs[t] = fs.get(t, 0) + n
            k = (pa + pb, tuple(sorted((t, n) for t, n in fs.items() if n)))
            r[k] = r.get(k, Fraction(0)) + va * vb
    return {k: v for k, v in r.items() if v != 0}


def _de_monomios(m: dict) -> mx.Expr:
    if not m:
        return mx.ZERO
    terminos = []
    for (pk, fs), c in sorted(m.items(), key=lambda kv: (len(kv[0][1]), str(kv[0]))):
        num: list[mx.Expr] = []
        den: list[mx.Expr] = []
        for t, n in fs:
            atomo = _ATOMOS.get(t) or mx.parse(t)
            (num if n > 0 else den).append(atomo if abs(n) == 1 else mx.Pow(atomo, mx.num(Fraction(abs(n)))))
        if pk:
            (num if pk > 0 else den).append(mx.PI if abs(pk) == 1 else mx.Pow(mx.PI, mx.num(Fraction(abs(pk)))))
        signo = c < 0
        c = abs(c)
        cuerpo: mx.Expr | None = None
        for f in num:
            cuerpo = f if cuerpo is None else mx.Mul(cuerpo, f)
        if c.numerator != 1 or cuerpo is None:
            cn = mx.num(Fraction(c.numerator))
            cuerpo = cn if cuerpo is None else mx.Mul(cn, cuerpo)
        divisor: mx.Expr | None = mx.num(Fraction(c.denominator)) if c.denominator != 1 else None
        for f in den:
            divisor = f if divisor is None else mx.Mul(divisor, f)
        t = cuerpo if divisor is None else mx.Div(cuerpo, divisor)
        terminos.append((signo, t))
    r: mx.Expr | None = None
    for signo, t in terminos:
        if r is None:
            r = mx.Neg(t) if signo else t
        else:
            r = mx.Sub(r, t) if signo else mx.Add(r, t)
    return r


def normaliza(e: mx.Expr) -> mx.Expr:
    """Reducción periódica de sen/cos y suma de monomios (π y átomos con potencias)."""
    try:
        e = _reduce_periodo(e)
        m = _monomios(e)
    except Exception:  # noqa: BLE001
        return e
    return e if m is None else _de_monomios(m)


def simplifica(e: mx.Expr) -> mx.Expr:
    e = _exp_ln(e)
    try:
        from academic_core.domain.engineering.mathlab import calculators as K

        e = K.pliega_constante(e)
    except Exception:  # noqa: BLE001
        pass
    n = normaliza(e)
    if n is not e and len(mx.text(n)) <= len(mx.text(e)):
        e = n
    r = P.simplifica(e)
    try:
        from academic_core.domain.engineering.mathlab import poly as PO

        n = PO.to_expr(PO.as_poly(r))
        if len(mx.text(n)) <= len(mx.text(r)):
            return n
    except Exception:  # noqa: BLE001
        pass
    return r


# ---------------------------------------------------------------------------
# integración exacta con su comprobación
# ---------------------------------------------------------------------------


def integra(f: mx.Expr, var: str, a, b) -> mx.Expr:
    """``∫ₐᵇ f`` exacto (extremos racionales, ±oo o expresiones en otra variable).
    Lanza ``UnsupportedError`` si el motor no da forma exacta."""
    from academic_core.domain.engineering.mathlab import contract as C

    f = combina_exp(f)
    if mx.exact_value(f) == 0:
        return mx.ZERO
    peticion = C.Peticion("integrar", {"integrando": f, "var": var, "desde": a, "hasta": b})
    r = C.calcular(peticion)
    if r.exacto_expr is not None and r.sello.verdict == "verificado":
        return simplifica(r.exacto_expr)
    if r.operacion == "impropia" or (isinstance(r.exacto, str) and "vale" in r.exacto):
        if r.aproximado is not None and r.sello.verdict == "verificado":
            texto = str(r.exacto).split("vale", 1)[1].strip()
            return simplifica(mx.parse(texto.replace("·", "*").replace("π", "pi")
                                       .replace("√", "sqrt")))
    raise _no(f"no sé dar ∫ {mx.text(f)} d{var} en forma exacta")


def _num_integral(fun, a: float | None, b: float | None) -> float:
    if a is None and b is None:
        return P.integral_a_infinito(fun, 0.0) + P.integral_a_infinito(lambda t: fun(-t), 0.0)
    if b is None:
        return P.integral_a_infinito(fun, a)
    if a is None:
        return P.integral_a_infinito(lambda t: fun(-t), -b)
    return P.tanh_sinh(fun, a, b)


def _f_num(expr: mx.Expr, var: str):
    def f(x: float) -> float:
        try:
            v = mx.valor_real(expr, {var: x})
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
        return 0.0 if v is None or not math.isfinite(v) else float(v)
    return f


# ---------------------------------------------------------------------------
# densidad por tramos
# ---------------------------------------------------------------------------


@dataclass
class Densidad:
    tramos: list[Tramo]
    var: str
    constante: str | None = None
    valor_constante: mx.Expr | None = None

    def f(self, x: float) -> float:
        for t in self.tramos:
            if t.contiene(x):
                return _f_num(t.expr, self.var)(x)
        return 0.0

    def soporte(self) -> tuple[float, float]:
        a = min((-math.inf if t.a is None else float(t.a)) for t in self.tramos)
        b = max((math.inf if t.b is None else float(t.b)) for t in self.tramos)
        return a, b

    def integral_exacta(self, peso: mx.Expr | None = None) -> mx.Expr:
        total: mx.Expr = mx.ZERO
        for t in self.tramos:
            g = t.expr if peso is None else mx.Mul(peso, t.expr)
            total = mx.Add(total, integra(g, self.var, _txt_ext(t.a, -1), _txt_ext(t.b, 1)))
        return simplifica(total)

    def integral_numerica(self, peso=None) -> float:
        total = 0.0
        for t in self.tramos:
            g = _f_num(t.expr, self.var)
            fun = g if peso is None else (lambda x, g=g: peso(x) * g(x))
            total += _num_integral(fun, None if t.a is None else float(t.a),
                                   None if t.b is None else float(t.b))
        return total


def lee_densidad(tramos, var: str = "x", constante: str | None = None,
                 trace: Trace | None = None) -> Densidad:
    """``[["k*x^2", "0", "1"], ["k*(2-x)", "1", "2"]]``; la constante se despeja
    de ``∫f = 1`` si se nombra (o si hay una única letra libre)."""
    trace = trace if trace is not None else Trace()
    lista = []
    libres: set[str] = set()
    for tr in tramos:
        if len(tr) != 3:
            raise _error("BAD_INPUT", "cada tramo es [expresión, desde, hasta]")
        e = mx.parse(str(tr[0])) if not isinstance(tr[0], mx.Expr) else tr[0]
        a, b = _extremo(tr[1]), _extremo(tr[2])
        if a is not None and b is not None and b <= a:
            raise _error("BAD_INPUT", f"tramo vacío [{a}, {b}]")
        lista.append(Tramo(e, a, b))
        libres |= mx.variables(e) - {var}
    lista.sort(key=lambda t: -math.inf if t.a is None else float(t.a))
    for t1, t2 in zip(lista, lista[1:]):
        if t1.b is None or (t2.a is not None and t2.a < t1.b):
            raise _error("BAD_INPUT", "los tramos se solapan")
    if constante is None and len(libres) == 1:
        constante = next(iter(libres))
    elif libres - ({constante} if constante else set()):
        raise _error("BAD_INPUT", f"letras sin valor en la densidad: {', '.join(sorted(libres))}")
    d = Densidad(lista, var, constante)
    if constante:
        d = _despeja_constante(d, trace)
    _comprueba_densidad(d, trace)
    return d


def _con(d: Densidad, valor: mx.Expr) -> Densidad:
    tr = [Tramo(simplifica(mx.substitute(t.expr, d.constante, valor)), t.a, t.b)
          for t in d.tramos]
    return Densidad(tr, d.var, d.constante, valor)


def _despeja_constante(d: Densidad, trace: Trace) -> Densidad:
    k = d.constante
    t0 = _con(d, mx.ZERO).integral_exacta()
    t1 = _con(d, mx.ONE).integral_exacta()
    trace.regla("densidad.normaliza", f"∫ f = {mx.text(simplifica(mx.Add(t0, mx.Mul(mx.Sym(k), mx.Sub(t1, t0)))))} "
                                      f"(lineal en {k})",
                why="una densidad integra 1 en todo su soporte: es la ecuación que fija la "
                    "constante")
    pend = simplifica(mx.Sub(t1, t0))
    if mx.exact_value(pend) == 0:
        raise _error("BAD_INPUT", f"la integral no depende de {k}: no se puede despejar")
    valor = simplifica(mx.Div(mx.Sub(mx.ONE, t0), pend))
    # linealidad comprobada en un tercer punto
    t2 = _con(d, mx.num(Fraction(2))).integral_exacta()
    esperado = mx.valor_real(mx.Add(t0, mx.Mul(mx.num(Fraction(2)), pend)), {})
    if abs(float(mx.valor_real(t2, {})) - float(esperado)) > 1e-9:
        raise _no(f"∫f no es lineal en {k}: no sé despejarla")
    trace.regla("densidad.constante", f"{k} = {mx.text(valor)}",
                why=f"de ∫f = 1 despejando {k}")
    dk = _con(d, valor)
    vk = mx.valor_real(valor, {})
    for t in dk.tramos:
        fx = _f_num(t.expr, d.var)
        a = -50.0 if t.a is None else float(t.a)
        b = 50.0 if t.b is None else float(t.b)
        for i in range(1, 40):
            if fx(a + (b - a) * i / 40) < -1e-12:
                raise _error("BAD_INPUT", f"con {k} = {mx.text(valor)} ≈ {vk:.6g} la función "
                                          "toma valores negativos: no es una densidad")
    trace.hipotesis("densidad.no_negativa", f"f ≥ 0 en el soporte con {k} = {mx.text(valor)}",
                    "se cumple")
    return dk


def _comprueba_densidad(d: Densidad, trace: Trace) -> None:
    total = d.integral_numerica()
    if abs(total - 1) > 1e-7:
        raise _error("BAD_INPUT" if d.constante is None else "DISCREPANT",
                     f"∫f = {total:.10g} ≠ 1: no es una densidad"
                     + ("" if d.constante else " (¿falta una constante por determinar?)"))
    trace.verificacion("densidad.integral_uno", f"cuadratura tanh-sinh independiente: ∫f = "
                                                f"{total:.12g}")


# ---------------------------------------------------------------------------
# momentos, F, probabilidades, Chebyshov
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Momentos:
    media: mx.Expr
    m2: mx.Expr
    varianza: mx.Expr


def momentos(d: Densidad, trace: Trace) -> Momentos:
    x = mx.Sym(d.var)
    m1 = d.integral_exacta(x)
    m2 = d.integral_exacta(mx.Pow(x, mx.num(Fraction(2))))
    var = simplifica(mx.Sub(m2, mx.Pow(m1, mx.num(Fraction(2)))))
    trace.regla("va.momentos", f"E[X] = ∫x·f = {mx.text(m1)}; E[X²] = {mx.text(m2)}; "
                               f"Var X = E[X²] − E[X]² = {mx.text(var)}",
                why="definición de esperanza de una variable continua")
    n1 = d.integral_numerica(lambda t: t)
    n2 = d.integral_numerica(lambda t: t * t)
    for nombre, ex, nu in (("E[X]", m1, n1), ("E[X²]", m2, n2)):
        v = mx.valor_real(ex, {})
        if v is None or abs(v - nu) > 1e-7 * max(1, abs(nu)):
            raise _error("DISCREPANT", f"{nombre} exacta {v} frente a cuadratura {nu}")
    trace.verificacion("va.momentos_cuadratura", f"E[X] ≈ {n1:.10g} y E[X²] ≈ {n2:.10g} "
                                                 "por cuadratura (coinciden)")
    return Momentos(m1, m2, var)


def F_por_tramos(d: Densidad, trace: Trace) -> list[tuple[Fraction | None, Fraction | None, mx.Expr]]:
    """``F(x)`` en cada tramo: ``F(aᵢ) + ∫_{aᵢ}^x f``."""
    piezas = []
    acumulado: mx.Expr = mx.ZERO
    a0 = d.tramos[0].a
    if a0 is not None:
        piezas.append((None, a0, mx.ZERO))
    t_var = "t" if d.var != "t" else "u"
    for t in d.tramos:
        g = mx.substitute(t.expr, d.var, mx.Sym(t_var))
        dentro = integra(g, t_var, _txt_ext(t.a, -1), d.var)
        Fi = simplifica(mx.Add(acumulado, dentro))
        piezas.append((t.a, t.b, Fi))
        if t.b is not None:
            acumulado = simplifica(mx.Add(acumulado, integra(t.expr, d.var, _txt_ext(t.a, -1),
                                                             str(t.b))))
    if d.tramos[-1].b is not None:
        piezas.append((d.tramos[-1].b, None, mx.ONE))
    trace.regla("va.F", "; ".join(f"F({d.var}) = {mx.text(F)} en "
                                  f"[{'−∞' if a is None else a}, {'+∞' if b is None else b}]"
                                  for a, b, F in piezas),
                why="F(x) = ∫_{−∞}^x f; en cada tramo, lo acumulado más la integral desde su "
                    "comienzo")
    for a, b, F in piezas:
        if a is not None and b is not None:
            xm = (float(a) + float(b)) / 2
            exacto = mx.valor_real(F, {d.var: xm})
            num = F_num(d, xm)
            if exacto is None or abs(exacto - num) > 1e-7:
                raise _error("DISCREPANT", f"F({xm}) exacta {exacto} frente a cuadratura {num}")
    trace.verificacion("va.F_cuadratura", "F en el punto medio de cada tramo frente a la "
                                          "cuadratura de f (coinciden)")
    return piezas


def F_num(d: Densidad, x: float) -> float:
    """F(x) por cuadratura tramo a tramo (los picos de f entre tramos no la estropean)."""
    total = 0.0
    for t in d.tramos:
        a = None if t.a is None else float(t.a)
        b = x if t.b is None else min(float(t.b), x)
        if a is not None and b <= a:
            continue
        total += _num_integral(_f_num(t.expr, d.var), a, b)
    return total


def probabilidad(d: Densidad, I: P.Intervalo, trace: Trace) -> tuple[mx.Expr | None, float]:
    total: mx.Expr = mx.ZERO
    num = 0.0
    exacta = True
    for t in d.tramos:
        lo = t.a if I.lo is None else (I.lo if t.a is None else max(t.a, I.lo))
        hi = t.b if I.hi is None else (I.hi if t.b is None else min(t.b, I.hi))
        if lo is not None and hi is not None and hi <= lo:
            continue
        try:
            total = mx.Add(total, integra(t.expr, d.var, _txt_ext(lo, -1), _txt_ext(hi, 1)))
        except UnsupportedError:
            exacta = False
        num += _num_integral(_f_num(t.expr, d.var), None if lo is None else float(lo),
                             None if hi is None else float(hi))
    valor = simplifica(total) if exacta else None
    if valor is not None:
        v = mx.valor_real(valor, {})
        if v is None or abs(v - num) > 1e-8:
            raise _error("DISCREPANT", f"P exacta {v} frente a cuadratura {num}")
        trace.verificacion("va.prob_cuadratura", f"cuadratura: {num:.12g} (coincide)")
    return valor, num


def chebyshov(d: Densidad, m: Momentos, k: Fraction, trace: Trace) -> dict:
    mu = float(mx.valor_real(m.media, {}))
    sigma = math.sqrt(float(mx.valor_real(m.varianza, {})))
    lo, hi = mu - float(k) * sigma, mu + float(k) * sigma
    fuera = 1 - _num_integral(d.f, lo, hi) if sigma > 0 else 0.0
    cota = float(1 / (k * k))
    trace.regla("va.chebyshov", f"P(|X − μ| ≥ {k}σ) ≤ 1/{k}² = {1 / (k * k)}; exacta ≈ {fuera:.6g}",
                why="Chebyshov solo usa media y varianza: vale para cualquier ley, por eso "
                    "suele quedar lejos del valor exacto")
    if fuera > cota + 1e-9:
        raise _error("DISCREPANT", "la probabilidad exacta supera la cota de Chebyshov")
    trace.verificacion("va.chebyshov_cota", "la probabilidad exacta respeta la cota")
    return {"cota": 1 / (k * k), "exacta": fuera, "intervalo": (lo, hi)}


# ---------------------------------------------------------------------------
# simulación de X por su F numérica (contraste de transformaciones y sumas)
# ---------------------------------------------------------------------------


def muestreador(d: Densidad, puntos: int = 4000):
    """Inversión numérica de F sobre una malla (independiente de los resultados que
    se comprueban: solo usa f)."""
    a, b = d.soporte()
    if not math.isfinite(a) or not math.isfinite(b):
        # recorta a una cola despreciable
        lo = a if math.isfinite(a) else -1.0
        hi = b if math.isfinite(b) else 1.0
        while not math.isfinite(a) and _num_integral(d.f, None, lo) > 1e-10:
            lo *= 2
        while not math.isfinite(b) and _num_integral(d.f, hi, None) > 1e-10:
            hi *= 2
        a, b = lo, hi
    xs = [a + (b - a) * i / puntos for i in range(puntos + 1)]
    Fs = [0.0]
    for x0, x1 in zip(xs, xs[1:]):
        Fs.append(Fs[-1] + P.tanh_sinh(d.f, x0, x1, nivel=4))
    tot = Fs[-1]
    Fs = [v / tot for v in Fs]

    def muestra(g) -> float:
        u = g.uniforme()
        lo, hi = 0, puntos
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if Fs[mid] <= u:
                lo = mid
            else:
                hi = mid
        dF = Fs[hi] - Fs[lo]
        frac = (u - Fs[lo]) / dF if dF > 0 else 0.5
        return xs[lo] + frac * (xs[hi] - xs[lo])
    return muestra


# ---------------------------------------------------------------------------
# Y = g(X): inversión simbólica por tramos monótonos
# ---------------------------------------------------------------------------


def invierte(g: mx.Expr, var: str, y: str = "y") -> list[mx.Expr]:
    """Las ramas ``h(y)`` con ``g(h(y)) = y`` pelando ``g``. Lanza si no sabe."""
    objetivo: list[mx.Expr] = [mx.Sym(y)]
    expr = g
    for _ in range(40):
        if expr == mx.Sym(var):
            return objetivo
        dep_l = lambda e: mx.depends(e, var)  # noqa: E731
        if isinstance(expr, mx.Neg):
            objetivo = [mx.Neg(o) for o in objetivo]
            expr = expr.arg
        elif isinstance(expr, mx.Add):
            if dep_l(expr.left) and not dep_l(expr.right):
                objetivo = [mx.Sub(o, expr.right) for o in objetivo]
                expr = expr.left
            elif dep_l(expr.right) and not dep_l(expr.left):
                objetivo = [mx.Sub(o, expr.left) for o in objetivo]
                expr = expr.right
            else:
                break
        elif isinstance(expr, mx.Sub):
            if dep_l(expr.left) and not dep_l(expr.right):
                objetivo = [mx.Add(o, expr.right) for o in objetivo]
                expr = expr.left
            elif dep_l(expr.right) and not dep_l(expr.left):
                objetivo = [mx.Sub(expr.left, o) for o in objetivo]
                expr = expr.right
            else:
                break
        elif isinstance(expr, mx.Mul):
            if dep_l(expr.left) and not dep_l(expr.right):
                objetivo = [mx.Div(o, expr.right) for o in objetivo]
                expr = expr.left
            elif dep_l(expr.right) and not dep_l(expr.left):
                objetivo = [mx.Div(o, expr.left) for o in objetivo]
                expr = expr.right
            else:
                break
        elif isinstance(expr, mx.Div):
            if dep_l(expr.left) and not dep_l(expr.right):
                objetivo = [mx.Mul(o, expr.right) for o in objetivo]
                expr = expr.left
            elif dep_l(expr.right) and not dep_l(expr.left):
                objetivo = [mx.Div(expr.left, o) for o in objetivo]
                expr = expr.right
            else:
                break
        elif isinstance(expr, mx.Pow) and not mx.depends(expr.exponent, var):
            n = mx.exact_value(expr.exponent)
            if expr.base == mx.E:
                break
            if n is None or n == 0:
                break
            n = Fraction(n)
            inv = mx.num(1 / n)
            nuevas = []
            for o in objetivo:
                if n.denominator == 1 and n > 1:
                    r = mx.Root(int(n), o)       # raíz real (impar: también de negativos)
                elif n == -1:
                    r = mx.Div(mx.ONE, o)
                else:
                    r = mx.Pow(o, inv)
                nuevas.append(r)
                if n.numerator % 2 == 0:
                    nuevas.append(mx.Neg(r))
            objetivo = nuevas
            expr = expr.base
        elif isinstance(expr, mx.Pow) and expr.base == mx.E:
            objetivo = [mx.Call("ln", (o,)) for o in objetivo]
            expr = expr.exponent
        elif isinstance(expr, mx.Root):
            objetivo = [mx.Pow(o, mx.num(Fraction(expr.degree))) for o in objetivo]
            expr = expr.radicand
        elif isinstance(expr, mx.Call) and len(expr.args) == 1:
            inversa = {"exp": "ln", "ln": "exp", "sqrt": None}.get(expr.name)
            if expr.name == "sqrt":
                objetivo = [mx.Pow(o, mx.num(Fraction(2))) for o in objetivo]
            elif inversa:
                objetivo = [mx.Call(inversa, (o,)) for o in objetivo]
            else:
                break
            expr = expr.args[0]
        else:
            break
    raise _no(f"no sé invertir y = {mx.text(g)} en forma cerrada")


@dataclass(frozen=True)
class Transformada:
    g: mx.Expr
    tramos: tuple[tuple[float, float, mx.Expr], ...]   # (y0, y1, f_Y en ese intervalo)

    def f(self, y: float) -> float:
        for a, b, e in self.tramos:
            if a <= y <= b:
                v = mx.valor_real(e, {"y": y})
                return 0.0 if v is None else float(v)
        return 0.0


def transforma(d: Densidad, g: mx.Expr, trace: Trace, semilla: int = 20261007) -> Transformada:
    from academic_core.domain.engineering.mathlab import derive_mv as D

    var = d.var
    dg = D.differentiate(g, var)
    ramas = invierte(g, var)
    trace.metodo("transformacion.inversa", "ramas de la inversa: " + ", ".join(
        f"{var} = {mx.text(simplifica(h))}" for h in ramas),
                 why="se despeja x en y = g(x) deshaciendo cada operación en orden inverso; "
                     "una potencia par da dos ramas (±)")
    gx = _f_num(g, var)
    dgx = _f_num(dg, var)
    # puntos de corte: extremos de los tramos y ceros de g′
    cortes: set[float] = set()
    for t in d.tramos:
        a = -1e6 if t.a is None else float(t.a)
        b = 1e6 if t.b is None else float(t.b)
        cortes |= {a, b}
        n = 400
        prev = dgx(a + (b - a) * 0.5 / n)
        for i in range(1, n):
            x = a + (b - a) * (i + 0.5) / n
            v = dgx(x)
            if prev * v < 0:
                lo, hi = x - (b - a) / n, x
                for _ in range(80):
                    m = (lo + hi) / 2
                    if dgx(lo) * dgx(m) <= 0:
                        hi = m
                    else:
                        lo = m
                cortes.add((lo + hi) / 2)
            prev = v
        # ceros de g′ sin cambio de signo (x³ en 0): mínimos locales de |g′| que valen 0
        malla = [a + (b - a) * (i + 0.5) / n for i in range(n)]
        absd = [abs(dgx(x)) for x in malla]
        for i in range(1, n - 1):
            if absd[i] <= absd[i - 1] and absd[i] <= absd[i + 1]:
                lo, hi = malla[i - 1], malla[i + 1]
                for _ in range(100):
                    m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
                    if abs(dgx(m1)) < abs(dgx(m2)):
                        hi = m2
                    else:
                        lo = m1
                xc = (lo + hi) / 2
                vecinos = max(absd[i - 1], absd[i + 1])
                if abs(dgx(xc)) < 1e-9 and vecinos > 1e-6:
                    q = Fraction(xc).limit_denominator(1000)
                    cortes.add(float(q) if abs(float(q) - xc) < 1e-6 else xc)
    cortes_l = sorted(cortes)
    contribuciones: list[tuple[float, float, mx.Expr, mx.Expr]] = []  # (y0, y1, h, f_X tramo)
    for x0, x1 in zip(cortes_l, cortes_l[1:]):
        xm = (x0 + 1.0 if x1 >= 1e6 and x0 > -1e6 else x1 - 1.0 if x0 <= -1e6 < x1 < 1e6
              else (x0 + x1) / 2)
        tramo = next((t for t in d.tramos if t.contiene(xm)), None)
        if tramo is None:
            continue
        ya, yb = sorted((_limite_g(g, var, x0, "+"), _limite_g(g, var, x1, "-")))
        ym = gx(xm)
        h = None
        for r in ramas:
            v = mx.valor_real(r, {"y": ym})
            if v is not None and abs(v - xm) < 1e-7 * max(1, abs(xm)):
                h = r
                break
        if h is None:
            raise _no("ninguna rama de la inversa cae en un tramo monótono")
        contribuciones.append((ya, yb, h, tramo.expr))
    ys = sorted({c[0] for c in contribuciones} | {c[1] for c in contribuciones})
    tramos_y = []
    for y0, y1 in zip(ys, ys[1:]):
        ym = _rep(y0, y1)
        suma: mx.Expr = mx.ZERO
        for a, b, h, fx in contribuciones:
            if a <= ym <= b:
                dh = D.differentiate(h, "y")
                valor_dh = mx.valor_real(dh, {"y": ym})
                jac = dh if valor_dh is not None and valor_dh >= 0 else mx.Neg(dh)
                suma = mx.Add(suma, mx.Mul(mx.substitute(fx, var, h), jac))
        tramos_y.append((y0, y1, simplifica(suma)))
    trace.regla("transformacion.densidad", "; ".join(
        f"f_Y(y) = {mx.text(e)} en [{_fy(a)}, {_fy(b)}]" for a, b, e in tramos_y),
                why="f_Y(y) = Σ f_X(h(y))·|h′(y)| sobre las ramas monótonas (jacobiano de la "
                    "inversa)")
    T = Transformada(g, tuple(tramos_y))
    # segundo camino: ∫ f_Y = 1 y P(Y ≤ y0) por simulación sembrada de X
    tot = sum(_num_integral(T.f, a if math.isfinite(a) else None,
                            b if math.isfinite(b) else None) for a, b, _ in tramos_y)
    if abs(tot - 1) > 2e-5:   # singularidades integrables (y^(−2/3)) en un extremo
        raise _error("DISCREPANT", f"∫ f_Y = {tot:.10g} ≠ 1")
    muestra = muestreador(d)
    ymed = _cuantil_num(T, 0.5, tramos_y)
    sim = P.simula(lambda gen: 1.0 if gx(muestra(gen)) <= ymed else 0.0, 20000, semilla)
    if not sim.dentro(0.5, 5):
        raise _error("DISCREPANT", f"P(g(X) ≤ mediana) simulada {sim.texto()} ≠ 0,5")
    trace.verificacion("transformacion.comprobacion",
                       f"∫ f_Y = {tot:.10g} y la mediana de f_Y ({ymed:.6g}) deja "
                       f"{sim.texto()} de las muestras simuladas de g(X)")
    return T


def _limite_g(g: mx.Expr, var: str, x: float, lado: str) -> float:
    """g en un extremo de un tramo monótono, por límite exacto (±∞ incluidos)."""
    from academic_core.domain.engineering.mathlab import limite as LM

    if abs(x) >= 1e6:
        punto = "oo" if x > 0 else "-oo"
        lado = ""
    else:
        q = Fraction(x).limit_denominator(10 ** 6)
        punto = str(q) if abs(float(q) - x) < 1e-12 else repr(x)
    try:
        lim = LM.limite(g, var, punto, lado)
        if lim.valor in ("inf", "oo", "+oo", "∞", "+∞"):
            return math.inf
        if lim.valor in ("-inf", "-oo", "-∞", "−∞"):
            return -math.inf
        if lim.expr is not None:
            v = mx.valor_real(lim.expr, {})
            if v is not None and math.isfinite(v):
                return _redondea(float(v))
    except Exception:  # noqa: BLE001
        pass
    paso = 1e-9 * max(1.0, abs(x))
    v = _f_num(g, var)(x + paso if lado == "+" else x - paso) if abs(x) < 1e6 else \
        _f_num(g, var)(x)
    return _redondea(v)


def _rep(a: float, b: float) -> float:
    """Un punto interior representativo de (a, b), también si un extremo es infinito."""
    if math.isfinite(a) and math.isfinite(b):
        return a + 0.37 * (b - a)
    if math.isfinite(a):
        return a + 1.0
    if math.isfinite(b):
        return b - 1.0
    return 0.0


def _fy(v: float) -> str:
    return "−∞" if v == -math.inf else "+∞" if v == math.inf else f"{v:.6g}"


def _redondea(v: float) -> float:
    if abs(v) > 1e5:
        return math.inf if v > 0 else -math.inf
    q = Fraction(v).limit_denominator(1000)
    return float(q) if abs(float(q) - v) < 1e-9 else v


def _cuantil_num(T: Transformada, p: float, tramos) -> float:
    a = tramos[0][0] if math.isfinite(tramos[0][0]) else -1.0
    b = tramos[-1][1] if math.isfinite(tramos[-1][1]) else 1.0

    def F(y):
        total = 0.0
        for y0, y1, _ in tramos:
            if y <= y0:
                break
            total += _num_integral(T.f, y0 if math.isfinite(y0) else None, min(y1, y))
        return total
    return P._biseccion(F, p, a, b)


# ---------------------------------------------------------------------------
# máximo y mínimo de n independientes, suma por convolución
# ---------------------------------------------------------------------------


def maximo_minimo(d: Densidad, n: int, trace: Trace) -> dict:
    piezas = F_por_tramos(d, Trace())
    maxi, mini = [], []
    for a, b, F in piezas:
        Fm = simplifica(mx.Pow(F, mx.num(Fraction(n))))
        Fn = simplifica(mx.Sub(mx.ONE, mx.Pow(mx.Sub(mx.ONE, F), mx.num(Fraction(n)))))
        maxi.append((a, b, Fm))
        mini.append((a, b, Fn))
    trace.regla("orden.maximo", f"F_max(x) = F(x)^{n}",
                why="el máximo es ≤ x si y solo si las n son ≤ x (independientes)")
    trace.regla("orden.minimo", f"F_min(x) = 1 − (1 − F(x))^{n}",
                why="el mínimo es > x si y solo si las n son > x")
    # segundo camino: simulación
    muestra = muestreador(d)
    a, b = d.soporte()
    for a_, b_, F in maxi:
        if a_ is not None and b_ is not None:
            xm = (float(a_) + float(b_)) / 2
            objetivo = float(mx.valor_real(F, {d.var: xm}))
            sim = P.simula(lambda g: 1.0 if max(muestra(g) for _ in range(n)) <= xm else 0.0,
                           8000)
            if not sim.dentro(objetivo):
                raise _error("DISCREPANT", f"F_max({xm}) = {objetivo} frente a {sim.texto()}")
            trace.verificacion("orden.simulacion", f"F_max({xm:.4g}) = {objetivo:.6g} y la "
                                                   f"simulación da {sim.texto()}")
            break
    return {"max": maxi, "min": mini}


def convolucion(d1: Densidad, d2: Densidad, trace: Trace, z: str = "z") -> list:
    """``f_Z(z) = ∫ f_X(x)·f_Y(z − x) dx``; tramos de z por las sumas de extremos."""
    v = d1.var
    puntos = set()
    for t1 in d1.tramos:
        for t2 in d2.tramos:
            for p in (t1.a, t1.b):
                for q in (t2.a, t2.b):
                    if p is not None and q is not None:
                        puntos.add(p + q)
    ext_inf = any(t.a is None for t in d1.tramos + d2.tramos)
    ext_sup = any(t.b is None for t in d1.tramos + d2.tramos)
    zs = sorted(puntos)
    if not zs:
        raise _no("convolución sin extremos finitos")
    intervalos = []
    if ext_inf:
        intervalos.append((None, zs[0]))
    intervalos += list(zip(zs, zs[1:]))
    if ext_sup:
        intervalos.append((zs[-1], None))
    resultado = []
    for z0, z1 in intervalos:
        zm = (float(z0) - 1.0 if z1 is not None and z0 is None else
              float(z1) + 1.0 if z0 is None else
              float(z0) + 1.0 if z1 is None else (float(z0) + float(z1)) / 2)
        if z0 is None:
            zm = float(z1) - 1.0
        total: mx.Expr = mx.ZERO
        hay = False
        for t1 in d1.tramos:
            for t2 in d2.tramos:
                # x ∈ [t1.a, t1.b] ∩ [z − t2.b, z − t2.a]
                cand_lo = [(t1.a, None)] + [(None, t2.b)]
                lo = _mayor(t1.a, t2.b, zm, z)
                hi = _menor(t1.b, t2.a, zm, z)
                lo_v = -math.inf if lo is None else float(mx.valor_real(lo, {z: zm}))
                hi_v = math.inf if hi is None else float(mx.valor_real(hi, {z: zm}))
                if hi_v <= lo_v:
                    continue
                del cand_lo
                g = mx.Mul(t1.expr, mx.substitute(t2.expr, d2.var, mx.Sub(mx.Sym(z), mx.Sym(v))))
                total = mx.Add(total, integra(g, v, "-oo" if lo is None else lo,
                                              "oo" if hi is None else hi))
                hay = True
        if hay:
            resultado.append((z0, z1, simplifica(total)))
    trace.regla("convolucion.tramos", "; ".join(
        f"f_Z(z) = {mx.text(e)} en [{'−∞' if a is None else a}, {'+∞' if b is None else b}]"
        for a, b, e in resultado),
                why="f_Z(z) = ∫ f_X(x)·f_Y(z − x) dx; los límites de x cambian cuando z cruza "
                    "una suma de extremos")
    # segundo camino: convolución numérica en el punto medio de cada tramo
    for a, b, e in resultado:
        zm = ((float(a) + float(b)) / 2 if a is not None and b is not None else
              (float(b) - 0.5 if a is None else float(a) + 0.5))
        exacto = float(mx.valor_real(e, {z: zm}) or 0.0)
        num = 0.0
        for t1 in d1.tramos:
            f1 = _f_num(t1.expr, v)
            for t2 in d2.tramos:
                f2 = _f_num(t2.expr, d2.var)
                lo = max(-math.inf if t1.a is None else float(t1.a),
                         -math.inf if t2.b is None else zm - float(t2.b))
                hi = min(math.inf if t1.b is None else float(t1.b),
                         math.inf if t2.a is None else zm - float(t2.a))
                if hi > lo:
                    num += _num_integral(lambda x, f1=f1, f2=f2: f1(x) * f2(zm - x),
                                         None if lo == -math.inf else lo,
                                         None if hi == math.inf else hi)
        if abs(exacto - num) > 1e-6 * max(1, abs(num)):
            raise _error("DISCREPANT", f"f_Z({zm}) exacta {exacto} frente a cuadratura {num}")
    trace.verificacion("convolucion.cuadratura", "f_Z en el punto medio de cada tramo frente "
                                                 "a la integral numérica (coinciden)")
    return resultado


def _mayor(a1: Fraction | None, b2: Fraction | None, zm: float, z: str) -> mx.Expr | None:
    """max(a1, z − b2) evaluado en zm (None = −∞)."""
    opciones = []
    if a1 is not None:
        opciones.append((float(a1), mx.num(a1)))
    if b2 is not None:
        opciones.append((zm - float(b2), simplifica(mx.Sub(mx.Sym(z), mx.num(b2)))))
    if not opciones:
        return None
    return max(opciones, key=lambda o: o[0])[1]


def _menor(b1: Fraction | None, a2: Fraction | None, zm: float, z: str) -> mx.Expr | None:
    opciones = []
    if b1 is not None:
        opciones.append((float(b1), mx.num(b1)))
    if a2 is not None:
        opciones.append((zm - float(a2), simplifica(mx.Sub(mx.Sym(z), mx.num(a2)))))
    if not opciones:
        return None
    return min(opciones, key=lambda o: o[0])[1]
