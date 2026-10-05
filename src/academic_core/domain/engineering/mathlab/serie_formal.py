# SPDX-License-Identifier: MIT
"""T-19: Taylor coefficients by arithmetic on truncated series, not by derivatives.

Why this module exists
----------------------

``series.taylor`` used to obtain the coefficient of order ``k`` by differentiating
``k`` times and evaluating at the centre. That is the definition, and as an
algorithm it fails in two ways that have nothing to do with the mathematics:

* **the derivatives grow.** ``1/(1-x)`` differentiated five times is a quotient
  of products of quotients; nothing folds ``0·(1-x)`` on the way, and the step
  log hit its 2000-character field at order 5. ``sqrt(x)`` about 1 died at order 3.
* **a coefficient had to be a rational number.** ``exp(x)`` about 2 was refused
  with «no tiene desarrollo de Taylor en ese centro», which is false: its
  coefficients are ``e²/k!``. ``e²`` simply was not a number the old route could hold.

Here every subexpression becomes the list of its first coefficients in
``u = x - a``, and the operations act on those lists: a sum adds them, a product
is the Cauchy product, a quotient is long division of series, and a function of
a series is composed from its own known series about the value at the centre
(``exp(c + w) = exp(c)·exp(w)``, ``sin(c + w) = sin(c)cos(w) + cos(c)sin(w)``…).
The coefficients are exact polynomials over rationals in constant atoms such as
``exp(2)`` or ``sin(1)``, so ``sin(1)cos(1) - cos(1)sin(1)`` is exactly 0 and not a
float that looks small.

What it refuses, and why it is right to
---------------------------------------

The refusals are the points where the function has no Taylor expansion at all:
a pole at the centre (``1/x`` at 0), ``ln`` at a point where its argument is 0 or
negative, a non-integer power of something that vanishes there (``sqrt(x)`` at 0),
``tan`` where ``cos`` vanishes. Each one says which. Anything this module does not
know how to compose raises :class:`NoFormal`, and the caller falls back to the
derivative route instead of guessing.
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.errors import UnsupportedError

#: how many extra terms a quotient may need to cancel a common zero at the centre,
#: as in ``sin(x)/x`` at 0 (one) or ``(1 - cos x)/x^2`` (two)
HOLGURA = 6

_CERO = P.const(Fraction(0))
_MEDIO = mx.Num(Fraction(-1, 2))
_UNO = P.const(Fraction(1))


#: the value at 0 of every function whose series is composed here and is defined
#: there; the simplifier folds the circular ones but not, for instance, ``sech(0)``
_EN_CERO = {"sin": Fraction(0), "cos": Fraction(1), "tan": Fraction(0),
            "sec": Fraction(1), "sinh": Fraction(0), "cosh": Fraction(1),
            "tanh": Fraction(0), "sech": Fraction(1), "exp": Fraction(1)}


def _pi_por(q: Fraction) -> mx.Expr:
    return mx.Mul(mx.Num(q), mx.PI) if q != 1 else mx.PI


#: exact values the inverse functions take at rational points, so that the constant
#: term of asin about 0 reads 0 and not asin(0)
_INVERSAS_NOTABLES = {
    ("asin", Fraction(0)): mx.ZERO, ("atan", Fraction(0)): mx.ZERO,
    ("asinh", Fraction(0)): mx.ZERO, ("atanh", Fraction(0)): mx.ZERO,
    ("asin", Fraction(1, 2)): _pi_por(Fraction(1, 6)),
    ("asin", Fraction(-1, 2)): _pi_por(Fraction(-1, 6)),
    ("acos", Fraction(0)): _pi_por(Fraction(1, 2)),
    ("acos", Fraction(1, 2)): _pi_por(Fraction(1, 3)),
    ("acos", Fraction(-1, 2)): _pi_por(Fraction(2, 3)),
    ("atan", Fraction(1)): _pi_por(Fraction(1, 4)),
    ("atan", Fraction(-1)): _pi_por(Fraction(-1, 4)),
}


class NoFormal(Exception):
    """A construct this module cannot compose; the caller uses another route."""


def _rechazo(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# constants: polynomials over Q in constant atoms
# ---------------------------------------------------------------------------


def _const(e: mx.Expr) -> P.Polynomial:
    """A constant expression folded into the coefficient ring, or ``NoFormal``.

    It goes through the trigonometric simplifier first, so ``sin(pi)`` arrives as
    ``0`` and ``cos(pi/3)`` as ``1/2`` instead of as atoms nobody can compare to zero.
    """
    from academic_core.domain.engineering.mathlab import trig as T

    if (isinstance(e, mx.Call) and len(e.args) == 1 and e.name in _EN_CERO
            and mx.exact_value(e.args[0]) == 0):
        return P.const(_EN_CERO[e.name])
    try:
        return P.as_poly(T.simplify(e))
    except Exception:  # noqa: BLE001 - anything the ring cannot hold
        try:
            return P.as_poly(e)
        except Exception as exc:  # noqa: BLE001
            raise NoFormal(f"constante no representable: {mx.text(e)}") from exc


def _expr(c: P.Polynomial) -> mx.Expr:
    return P.to_expr(c)


def _racional(c: P.Polynomial) -> Fraction | None:
    """The value of ``c`` when it is a plain rational, else ``None``."""
    if P.is_zero(c):
        return Fraction(0)
    if len(c) == 1:
        (monomio, valor), = c.items()
        if monomio == ():
            return Fraction(valor)
    return None


def _valor(c: P.Polynomial) -> float | None:
    """A numerical value for a constant, only to decide a sign or a domain."""
    return mx.valor_real(_expr(c), {})


def _raiz_entera(n: int, k: int) -> int | None:
    """The exact ``k``-th root of ``n >= 0``, or ``None``."""
    r = round(n ** (1.0 / k))
    for candidato in (r - 1, r, r + 1):
        if candidato >= 0 and candidato ** k == n:
            return candidato
    return None


def _potencia_constante(c: P.Polynomial, r: Fraction) -> P.Polynomial:
    """``c^r`` exactly: a rational when ``c`` is a perfect power, an atom otherwise.

    ``sqrt(1)`` is 1 and ``8^(1/3)`` is 2; leaving them as ``sqrt(1)`` or
    ``raiz(8, 3)`` is exact and unreadable, and every coefficient carries the factor.
    """
    q = _racional(c)
    if q is not None and q > 0:
        p, k = r.numerator, r.denominator
        num, den = _raiz_entera(q.numerator, k), _raiz_entera(q.denominator, k)
        if num is not None and den is not None:
            return P.const(Fraction(num, den) ** p)
        # (a/b)^(p/k) = (a/b)^t · (a^e·b^(k-e))^(1/k) / b, with p = t·k + e, 0 < e < k:
        # a rational times the k-th root of an integer, with the k-th powers taken out
        e = p % k
        t = (p - e) // k
        a, b = q.numerator, q.denominator
        coeficiente = q ** t / b
        radicando = a ** e * b ** (k - e)
        fuera, dentro = _extraer_potencias(radicando, k)
        coeficiente *= fuera
        if dentro == 1:
            return P.const(coeficiente)
        return P.scale(_const(mx.Root(k, mx.Num(Fraction(dentro)))), coeficiente)
    return _const(mx.Pow(_expr(c), mx.Num(r)))


def _extraer_potencias(n: int, k: int) -> tuple[int, int]:
    """``n = fuera^k · dentro`` with ``dentro`` free of k-th powers (small factors)."""
    fuera, dentro, d = 1, n, 2
    while d ** k <= dentro and d < 10 ** 4:
        while dentro % d ** k == 0:
            dentro //= d ** k
            fuera *= d
        d += 1
    return fuera, dentro


def _inverso_constante(c: P.Polynomial) -> P.Polynomial:
    """``1/c``: exact when ``c`` is rational, an atom ``1/(…)`` otherwise."""
    q = _racional(c)
    if q is not None:
        if q == 0:
            raise ZeroDivisionError
        return P.const(1 / q)
    return _const(mx.Div(mx.ONE, _expr(c)))


# ---------------------------------------------------------------------------
# series arithmetic. A series is a list of coefficients, index = power of u.
# ---------------------------------------------------------------------------


def _suma(a, b, signo=1):
    return [P.add(x, y, signo) for x, y in zip(a, b)]


def _escala(a, c: P.Polynomial):
    return [P.mul(x, c) for x in a]


def _producto(a, b, n):
    salida = [_CERO] * n
    for i, x in enumerate(a[:n]):
        if P.is_zero(x):
            continue
        for j in range(n - i):
            if not P.is_zero(b[j]):
                salida[i + j] = P.add(salida[i + j], P.mul(x, b[j]))
    return salida


def _inversa(b, n):
    """``1/b`` for a series whose constant term is not zero."""
    inv0 = _inverso_constante(b[0])
    salida = [inv0] + [_CERO] * (n - 1)
    for k in range(1, n):
        acumulado = _CERO
        for j in range(1, k + 1):
            if not P.is_zero(b[j]):
                acumulado = P.add(acumulado, P.mul(b[j], salida[k - j]))
        salida[k] = P.scale(P.mul(acumulado, inv0), Fraction(-1))
    return salida


def _valuacion(a) -> int | None:
    for i, x in enumerate(a):
        if not P.is_zero(x):
            return i
    return None


def _derivada(a):
    """Formal derivative with respect to ``u``; one term shorter."""
    return [P.scale(a[k], Fraction(k)) for k in range(1, len(a))]


def _integral(a, constante, n):
    """Formal antiderivative with the given constant term, ``n`` terms long."""
    salida = [constante] + [_CERO] * (n - 1)
    for k in range(1, n):
        if k - 1 < len(a):
            salida[k] = P.scale(a[k - 1], Fraction(1, k))
    return salida


def _componer(coeficientes: list[Fraction], w, n):
    """``Σ coeficientes[k]·w^k`` for a series ``w`` with zero constant term (Horner)."""
    salida = [_CERO] * n
    for c in reversed(coeficientes[:n]):
        salida = _producto(salida, w, n)
        salida[0] = P.add(salida[0], P.const(c))
    return salida


def _factorial(k: int) -> int:
    f = 1
    for i in range(2, k + 1):
        f *= i
    return f


def _exp_coef(n):
    return [Fraction(1, _factorial(k)) for k in range(n)]


def _sin_coef(n):
    return [Fraction((-1) ** ((k - 1) // 2), _factorial(k)) if k % 2 else Fraction(0)
            for k in range(n)]


def _cos_coef(n):
    return [Fraction((-1) ** (k // 2), _factorial(k)) if k % 2 == 0 else Fraction(0)
            for k in range(n)]


def _sinh_coef(n):
    return [Fraction(1, _factorial(k)) if k % 2 else Fraction(0) for k in range(n)]


def _cosh_coef(n):
    return [Fraction(1, _factorial(k)) if k % 2 == 0 else Fraction(0) for k in range(n)]


def _binomial_coef(r: Fraction, n):
    """``binom(r, k)`` for ``k < n``: the series of ``(1 + w)^r``."""
    salida, actual = [], Fraction(1)
    for k in range(n):
        salida.append(actual)
        actual = actual * (r - k) / (k + 1)
    return salida


def _ln1_coef(n):
    """``ln(1 + w)``."""
    return [Fraction(0)] + [Fraction((-1) ** (k + 1), k) for k in range(1, n)]


# ---------------------------------------------------------------------------
# the translation
# ---------------------------------------------------------------------------


def coeficientes(expresion: mx.Expr, var: str, centro: mx.Expr, n: int) -> list:
    """The first ``n`` Taylor coefficients of ``expresion`` about ``centro``.

    Each coefficient is an exact constant expression. Raises ``NoFormal`` for a
    construct this module does not compose, and ``UnsupportedError`` where the
    expansion does not exist.
    """
    serie = _serie(expresion, var, _const(centro), centro, n)
    return [_limpio(c) for c in serie[:n]]


def _limpio(c: P.Polynomial) -> mx.Expr:
    """The coefficient as the reader should see it: ``sqrt(1)`` is 1, ``-1/6*1`` is -1/6.

    The trigonometric simplifier folds the radicals and the notable values; the ring
    normal form is applied again afterwards so that what comes back is canonical.
    """
    from academic_core.domain.engineering.mathlab import trig as T

    q = _racional(c)
    if q is not None:
        # ``poly.to_expr`` writes a bare constant as ``c*1``
        return mx.Num(q) if q >= 0 else mx.Neg(mx.Num(-q))
    try:
        return T.simplify(_expr(c))
    except Exception:  # noqa: BLE001 - the exact ring form is still correct
        return _expr(c)


def _serie(e: mx.Expr, var: str, a: P.Polynomial, centro: mx.Expr, n: int):
    if var not in mx.variables(e):
        return [_const(e)] + [_CERO] * (n - 1)
    if isinstance(e, mx.Sym):
        return ([a, _UNO] + [_CERO] * n)[:n]
    if isinstance(e, mx.Neg):
        return _escala(_serie(e.arg, var, a, centro, n), P.const(Fraction(-1)))
    if isinstance(e, mx.Add):
        return _suma(_serie(e.left, var, a, centro, n), _serie(e.right, var, a, centro, n))
    if isinstance(e, mx.Sub):
        return _suma(_serie(e.left, var, a, centro, n),
                     _serie(e.right, var, a, centro, n), -1)
    if isinstance(e, mx.Mul):
        return _producto(_serie(e.left, var, a, centro, n),
                         _serie(e.right, var, a, centro, n), n)
    if isinstance(e, mx.Div):
        return _cociente(e.left, e.right, var, a, centro, n)
    if isinstance(e, mx.Pow):
        return _potencia(e.base, e.exponent, var, a, centro, n)
    if isinstance(e, mx.Root):
        return _potencia_racional(e.radicand, Fraction(1, e.degree), var, a, centro, n,
                                  texto=mx.text(e))
    if isinstance(e, mx.Call):
        return _funcion(e, var, a, centro, n)
    raise NoFormal(f"nodo no compuesto: {type(e).__name__}")


def _cociente(num, den, var, a, centro, n):
    largo = n + HOLGURA
    b = _serie(den, var, a, centro, largo)
    vb = _valuacion(b)
    if vb is None or vb >= HOLGURA:
        raise _rechazo(
            f"el denominador {mx.text(den)} se anula en {mx.text(centro)} con todas "
            "sus derivadas a la vista: no hay desarrollo de Taylor en ese centro")
    if vb == 0:
        return _producto(_serie(num, var, a, centro, n), _inversa(b, n), n)
    c = _serie(num, var, a, centro, largo)
    vc = _valuacion(c)
    if vc is not None and vc < vb:
        raise _rechazo(
            f"{mx.text(den)} se anula en {mx.text(centro)} y {mx.text(num)} no lo "
            "compensa: la función tiene un polo ahí, su valor no es un número y no "
            "hay desarrollo de Taylor en ese centro")
    if vc is None:
        return [_CERO] * n
    # a common zero of order vb cancels, as in sin(x)/x at 0: shift both
    return _producto(c[vb:vb + n], _inversa(b[vb:vb + n], n), n)


def _potencia(base, exponente, var, a, centro, n):
    if var in mx.variables(exponente):
        # b^g = exp(g·ln b), which is exactly what the definition means
        return _serie(mx.Call("exp", (mx.Mul(exponente, mx.Call("ln", (base,))),)),
                      var, a, centro, n)
    r = mx.exact_value(exponente)
    if r is None:
        # a symbolic constant exponent: same identity, with a constant factor
        return _serie(mx.Call("exp", (mx.Mul(exponente, mx.Call("ln", (base,))),)),
                      var, a, centro, n)
    r = Fraction(r)
    if r.denominator == 1 and r >= 0:
        s = _serie(base, var, a, centro, n)
        salida = [_UNO] + [_CERO] * (n - 1)
        for _ in range(int(r)):
            salida = _producto(salida, s, n)
        return salida
    if r.denominator == 1:
        return _cociente(mx.ONE, mx.Pow(base, mx.Num(-r)), var, a, centro, n)
    return _potencia_racional(base, r, var, a, centro, n, texto=mx.text(mx.Pow(base, exponente)))


def _potencia_racional(base, r: Fraction, var, a, centro, n, *, texto: str):
    s = _serie(base, var, a, centro, n)
    s0 = s[0]
    q = _racional(s0)
    if q == 0:
        raise _rechazo(
            f"{texto}: la base se anula en {mx.text(centro)} y el exponente {r} no es "
            "entero, así que alguna derivada no es un número ahí y no hay desarrollo de "
            "Taylor en ese centro")
    valor = float(q) if q is not None else _valor(s0)
    if valor is None:
        raise NoFormal(f"no se sabe el signo de {mx.text(_expr(s0))}")
    if valor < 0 and r.denominator % 2 == 0:
        raise _rechazo(
            f"{texto}: la base vale {mx.text(_expr(s0))} < 0 en {mx.text(centro)} y una "
            "raíz de índice par de un negativo no es real")
    # (s0·(1 + w))^r = s0^r · (1 + w)^r with w = (s - s0)/s0
    potencia = _potencia_constante(s0, r)
    w = _escala([_CERO] + s[1:], _inverso_constante(s0))
    return _escala(_componer(_binomial_coef(r, n), w, n), potencia)


def _argumento(e: mx.Call, var, a, centro, n):
    s = _serie(e.args[0], var, a, centro, n)
    return s, s[0], [_CERO] + s[1:]


def _funcion(e: mx.Call, var, a, centro, n):
    nombre = e.name
    if nombre == "log" and len(e.args) == 2:
        # logb(b, x) = ln(x)/ln(b)
        return _serie(mx.Div(mx.Call("ln", (e.args[1],)), mx.Call("ln", (e.args[0],))),
                      var, a, centro, n)
    if len(e.args) != 1:
        raise NoFormal(f"{nombre} con {len(e.args)} argumentos")
    arg = e.args[0]
    if nombre == "log10":
        return _serie(mx.Div(mx.Call("ln", (arg,)), mx.Call("ln", (mx.Num(Fraction(10)),))),
                      var, a, centro, n)
    s, s0, w = _argumento(e, var, a, centro, n)
    c0 = _expr(s0)

    def at(f):
        q = _racional(s0)
        if q is not None and (f, q) in _INVERSAS_NOTABLES:
            return _const(_INVERSAS_NOTABLES[(f, q)])
        return _const(mx.Call(f, (c0,)))

    if nombre == "exp":
        return _escala(_componer(_exp_coef(n), w, n), _const(mx.Call("exp", (c0,))))
    if nombre in ("sin", "cos"):
        seno, coseno = _componer(_sin_coef(n), w, n), _componer(_cos_coef(n), w, n)
        if nombre == "sin":
            return _suma(_escala(coseno, at("sin")), _escala(seno, at("cos")))
        return _suma(_escala(coseno, at("cos")), _escala(seno, at("sin")), -1)
    if nombre in ("sinh", "cosh"):
        sh, ch = _componer(_sinh_coef(n), w, n), _componer(_cosh_coef(n), w, n)
        if nombre == "sinh":
            return _suma(_escala(ch, at("sinh")), _escala(sh, at("cosh")))
        return _suma(_escala(ch, at("cosh")), _escala(sh, at("sinh")))
    if nombre in ("sec", "csc", "cot", "sech", "csch", "coth"):
        return _reciproca(nombre, arg, s0, c0, w, centro, n)
    if nombre in ("tan", "tanh"):
        base = "cos" if nombre == "tan" else "cosh"
        if P.is_zero(_const(mx.Call(base, (c0,)))):
            raise _rechazo(
                f"tan({mx.text(arg)}) tiene un polo en {mx.text(centro)}: el coseno se "
                "anula ahí, su valor no es un número y no hay desarrollo de Taylor")
        # tan(c + w) = (t + tan w)/(1 - t·tan w); tanh with + in the denominator
        impar = _sin_coef(n) if nombre == "tan" else _sinh_coef(n)
        par = _cos_coef(n) if nombre == "tan" else _cosh_coef(n)
        tangente = _producto([P.const(c) for c in impar],
                             _inversa([P.const(c) for c in par], n), n)
        tw = _componer([_racional(c) for c in tangente], w, n)
        t = at(nombre)
        numerador = _suma(tw, [t] + [_CERO] * (n - 1))
        signo = Fraction(-1) if nombre == "tan" else Fraction(1)
        denominador = _suma([_UNO] + [_CERO] * (n - 1), _escala(tw, P.scale(t, signo)))
        return _producto(numerador, _inversa(denominador, n), n)
    if nombre == "ln":
        q = _racional(s0)
        if q == 0:
            raise _rechazo(
                f"ln({mx.text(arg)}) en {mx.text(centro)}: el argumento vale 0 y ln(0) "
                "no es un número, así que no hay desarrollo de Taylor en ese centro")
        valor = float(q) if q is not None else _valor(s0)
        if valor is None:
            raise NoFormal(f"no se sabe el signo de {mx.text(c0)}")
        if valor < 0:
            raise _rechazo(
                f"ln({mx.text(arg)}) en {mx.text(centro)}: el argumento vale "
                f"{mx.text(c0)} < 0 y el logaritmo de un negativo no es real")
        u = _escala(w, _inverso_constante(s0))
        return _suma(_componer(_ln1_coef(n), u, n),
                     [_const(mx.Call("ln", (c0,)))] + [_CERO] * (n - 1))
    # inverse functions: f(s) = f(s0) + ∫ f'(s)·s' du, with f' algebraic
    derivadas = {
        "atan": lambda z: mx.Div(mx.ONE, mx.Add(mx.ONE, mx.Pow(z, mx.Num(2)))),
        "atanh": lambda z: mx.Div(mx.ONE, mx.Sub(mx.ONE, mx.Pow(z, mx.Num(2)))),
        # written as a power -1/2 and not as 1/sqrt(...): the binomial series then
        # carries ONE constant atom, instead of sqrt(c) and 1/sqrt(c) as two atoms
        # the ring cannot cancel against each other
        "asin": lambda z: mx.Pow(mx.Sub(mx.ONE, mx.Pow(z, mx.Num(2))), _MEDIO),
        "acos": lambda z: mx.Neg(mx.Pow(mx.Sub(mx.ONE, mx.Pow(z, mx.Num(2))), _MEDIO)),
        "asinh": lambda z: mx.Pow(mx.Add(mx.Pow(z, mx.Num(2)), mx.ONE), _MEDIO),
        "acosh": lambda z: mx.Pow(mx.Sub(mx.Pow(z, mx.Num(2)), mx.ONE), _MEDIO),
    }
    if nombre in derivadas:
        valor = _valor(s0)
        if valor is None:
            raise NoFormal(f"no se sabe dónde cae {mx.text(c0)}")
        fuera = {"asin": abs(valor) >= 1, "acos": abs(valor) >= 1,
                 "atanh": abs(valor) >= 1, "acosh": valor <= 1}.get(nombre, False)
        if fuera:
            raise _rechazo(
                f"{nombre}({mx.text(arg)}) en {mx.text(centro)}: el argumento vale "
                f"{mx.text(c0)}, en el borde o fuera del dominio donde {nombre} es "
                "derivable, así que no hay desarrollo de Taylor en ese centro")
        # f'(s(u)) as a series in u, composed through the same machinery
        fprima = _serie(derivadas[nombre](mx.Sym("_s")), "_s", s0, c0, n)
        fprima_de_s = _componer_desplazada(fprima, w, n)
        integrando = _producto(fprima_de_s, _derivada(s) + [_CERO], n)
        return _integral(integrando, at(nombre), n)
    if nombre == "abs":
        valor = _valor(s0)
        if valor is None or valor == 0:
            raise _rechazo(
                f"abs({mx.text(arg)}) en {mx.text(centro)}: el argumento vale 0 y el "
                "valor absoluto no es derivable donde su argumento cambia de signo")
        return s if valor > 0 else _escala(s, P.const(Fraction(-1)))
    raise NoFormal(f"función sin serie compuesta: {nombre}")


def _reciproca(nombre, arg, s0, c0, w, centro, n):
    """sec, csc, cot and their hyperbolic ones, about ``c0`` through ``w = s - c0``.

    Written with addition formulas whose denominator has constant term 1, so the
    series division never has to invert a symbolic constant. Inverting ``sin(1)``
    would put an atom ``1/sin(1)`` next to ``sin(1)`` that the ring cannot cancel,
    and every coefficient would carry ``csc(1)^2·sin(1)`` where ``csc(1)`` belongs.

    * ``sec(c+w) = sec c / (cos w − tan c·sin w)``
    * ``csc(c+w) = csc c / (cos w + cot c·sin w)``
    * ``cot(c+w) = (cot c − tan w)/(1 + cot c·tan w)``

    and the hyperbolic ones with the signs of ``cosh(c+w) = cosh c cosh w + sinh c sinh w``.
    """
    hiperbolica = nombre in ("sech", "csch", "coth")
    seno = "sinh" if hiperbolica else "sin"
    coseno = "cosh" if hiperbolica else "cos"
    nulo = {"sec": coseno, "sech": coseno, "csc": seno, "csch": seno,
            "cot": seno, "coth": seno}[nombre]
    if P.is_zero(_const(mx.Call(nulo, (c0,)))):
        raise _rechazo(
            f"{nombre}({mx.text(arg)}) tiene un polo en {mx.text(centro)}: {nulo} se "
            "anula ahí, su valor no es un número y no hay desarrollo de Taylor")
    impar = _componer(_sinh_coef(n) if hiperbolica else _sin_coef(n), w, n)
    par = _componer(_cosh_coef(n) if hiperbolica else _cos_coef(n), w, n)

    def k(f):
        return _const(mx.Call(f, (c0,)))

    if nombre in ("sec", "sech"):
        signo = Fraction(1) if hiperbolica else Fraction(-1)
        t = k("tanh" if hiperbolica else "tan")
        den = _suma(par, _escala(impar, P.scale(t, signo)))
        return _escala(_inversa(den, n), k(nombre))
    if nombre in ("csc", "csch"):
        t = k("coth" if hiperbolica else "cot")
        den = _suma(par, _escala(impar, t))
        return _escala(_inversa(den, n), k(nombre))
    # cot / coth
    tangente = _producto(impar, _inversa(par, n), n)
    cotc = k(nombre)
    if hiperbolica:
        # coth(c+w) = (coth c + tanh w)/(1 + coth c·tanh w)
        numerador = _suma([cotc] + [_CERO] * (n - 1), tangente)
    else:
        numerador = _suma([cotc] + [_CERO] * (n - 1), tangente, -1)
    denominador = _suma([_UNO] + [_CERO] * (n - 1), _escala(tangente, cotc))
    return _producto(numerador, _inversa(denominador, n), n)


def _componer_desplazada(f, w, n):
    """``Σ f[k]·w^k`` with constant (non-rational) coefficients ``f[k]``."""
    salida = [_CERO] * n
    for c in reversed(f[:n]):
        salida = _producto(salida, w, n)
        salida[0] = P.add(salida[0], c)
    return salida
