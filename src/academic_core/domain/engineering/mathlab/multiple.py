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
    if len(mx.text(e)) <= 260:
        # la simplificación trigonométrica general explora muchas reescrituras: en
        # expresiones grandes (pasos intermedios) se omite; la forma normal de abajo
        # sigue siendo exacta
        try:
            e = LM._limpio(T.simplify(e))
        except Exception:  # noqa: BLE001 - se queda sin simplificar, sigue siendo exacta
            pass
    e = _canon(_canon_profundo(_raiz_cte(_logexp(e))))
    e2 = _canon(_raiz_cte(e))          # (√u)⁴ aparece a menudo solo tras la forma normal
    if mx.text(e2) != mx.text(e):
        e = e2
    for cand in (_racional(e), _racional(_angulo_doble(e))):
        if cand is not None and len(mx.text(cand)) <= len(mx.text(e)):
            e = cand
    return _bonito(e)


def _angulo_notable(nombre: str, a: mx.Expr) -> mx.Expr | None:
    """arcsen/arccos/arctan de un valor notable = q·π (q con denominador ≤ 12),
    aceptado solo si la función directa de q·π devuelve exactamente a."""
    from academic_core.domain.engineering.mathlab import trig as T

    v = mx.valor_real(a, {})
    if v is None:
        return None
    try:
        ang = {"asin": math.asin, "acos": math.acos, "atan": math.atan}[nombre](float(v))
    except ValueError:
        return None
    q = Fraction(ang / math.pi).limit_denominator(12)
    if abs(float(q) * math.pi - ang) > 1e-12:
        return None
    cand = mx.Mul(leer(q), mx.Const("pi")) if q != 0 else mx.Num(Fraction(0))
    directa = {"asin": "sin", "acos": "cos", "atan": "tan"}[nombre]
    try:
        dif = T.simplify(mx.Sub(mx.Call(directa, (cand,)), a))
    except Exception:  # noqa: BLE001
        return None
    if mx.exact_value(dif) == 0 and not mx.variables(dif):
        return cand
    try:
        from academic_core.domain.engineering.mathlab import verify as V

        if V.check_equivalence(T.simplify(mx.Call(directa, (cand,))), T.simplify(a))[0]:
            return cand
    except Exception:  # noqa: BLE001
        pass
    return None


def _log_racional(a: mx.Expr, b: mx.Expr) -> Fraction | None:
    """log_b(a) racional exacto cuando a y b son racionales positivos con a = b^k:
    a^den = b^num en enteros (sin coma flotante)."""
    av, bv = mx.exact_value(a), mx.exact_value(b)
    if av is None or bv is None or mx.variables(a) or mx.variables(b):
        return None
    av, bv = Fraction(av), Fraction(bv)
    if av <= 0 or bv <= 0 or bv == 1:
        return None
    if av == 1:
        return Fraction(0)
    try:
        k = Fraction(math.log(av) / math.log(bv)).limit_denominator(24)
    except (ValueError, ZeroDivisionError):
        return None
    if k.numerator == 0 or abs(k.numerator) > 64:
        return None
    izq = av ** k.denominator
    der = bv ** k.numerator
    return k if izq == der else None


def _raiz_cte(e: mx.Expr) -> mx.Expr:
    """√(c·u) con c cuadrado perfecto racional → √c·√u (√(4y) = 2√y)."""
    if isinstance(e, mx.Root) and e.degree % 2 == 1:
        q = mx.exact_value(e.radicand)
        if q is not None and q < 0:          # ∛(−2) = −∛2
            return mx.Neg(mx.Root(e.degree, leer(-Fraction(q))))
    if isinstance(e, mx.Root) and e.degree == 2:
        r = _raiz_cte(e.radicand)
        # contenido cuadrado de un polinomio: √(16 − 4y) = 2·√(4 − y)
        try:
            from academic_core.domain.engineering.mathlab import poly as P

            p = P.as_poly(r)
            if len(p) > 1 and not P.atoms_of(p) and all(len(n) == 1 for m in p for n, _ in m):
                # contenido racional c = g/l (mcd de numeradores / mcm de denominadores);
                # se saca la mayor parte cuadrada: √(c·q) = √c·√q
                g, l = 0, 1
                for c in p.values():
                    g = math.gcd(g, abs(c.numerator))
                    l = l * c.denominator // math.gcd(l, c.denominator)
                kn = 1
                for q in range(int(math.isqrt(g)), 1, -1):
                    if g % (q * q) == 0:
                        kn = q
                        break
                kd = 1
                for q in range(int(math.isqrt(l)), 1, -1):
                    if l % (q * q) == 0:
                        kd = q
                        break
                if l != 1 and kd * kd != l:
                    kd = 1          # solo si el denominador es cuadrado entero
                k = Fraction(kn, kd)
                if k != 1:
                    return mx.Mul(leer(k), mx.Root(2, _bonito(P.to_expr(P.scale(p, 1 / (k * k))))))
        except Exception:  # noqa: BLE001
            pass
        if isinstance(r, mx.Mul):
            c = mx.exact_value(r.left)
            if c is not None and c > 0 and not mx.variables(r.left):
                c = Fraction(c)
                rn, rd = math.isqrt(c.numerator), math.isqrt(c.denominator)
                if rn * rn == c.numerator and rd * rd == c.denominator:
                    return mx.Mul(leer(Fraction(rn, rd)), mx.Root(2, r.right))
        return mx.Root(2, r)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_raiz_cte(e.left), _raiz_cte(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_raiz_cte(e.arg))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_raiz_cte(a) for a in e.args))
    if isinstance(e, mx.Pow):
        k = mx.exact_integer(e.exponent)
        if isinstance(e.base, mx.Root) and k is not None and k >= e.base.degree:
            q, resto = divmod(k, e.base.degree)
            r = _raiz_cte(e.base.radicand)
            entero = r if q == 1 else mx.Pow(r, mx.Num(Fraction(q)))
            if resto == 0:
                return entero
            raiz = mx.Root(e.base.degree, r)
            return mx.Mul(entero, raiz if resto == 1 else mx.Pow(raiz, mx.Num(Fraction(resto))))
        return mx.Pow(_raiz_cte(e.base), e.exponent)
    return e


def _angulo_doble(e: mx.Expr) -> mx.Expr:
    """sen(2u) = 2·sen u·cos u y cos(2u) = 1 − 2·sen²u (para que se cancelen con
    los factores sen u, cos u de un denominador)."""
    if isinstance(e, mx.Call) and e.name in ("sin", "cos") and len(e.args) == 1:
        a = e.args[0]
        if isinstance(a, mx.Mul) and mx.exact_value(a.left) == 2 and not mx.variables(a.left):
            u = _angulo_doble(a.right)
            if e.name == "sin":
                return mx.Mul(mx.Num(Fraction(2)), mx.Mul(mx.Call("sin", (u,)),
                                                          mx.Call("cos", (u,))))
            return mx.Sub(mx.Num(Fraction(1)), mx.Mul(mx.Num(Fraction(2)),
                                                      mx.Pow(mx.Call("sin", (u,)), mx.Num(2))))
        return mx.Call(e.name, (_angulo_doble(a),))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_angulo_doble(e.left), _angulo_doble(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_angulo_doble(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_angulo_doble(e.base), e.exponent)
    return e


def _racional(e: mx.Expr) -> mx.Expr | None:
    """e como N/D (polinomios sobre átomos: sen θ, eˣ… cuentan como variables) con el
    factor monomio común cancelado y, si D divide a N, el cociente exacto. None si no
    se puede (forma demasiado grande o algo no racional)."""
    from academic_core.domain.engineering.mathlab import poly as P

    largos = sorted(v for v in mx.variables(e) if len(v) > 1)
    libres = [c for c in "ABCDFGHJKLMNOPQRSTUVW" if c not in mx.variables(e)]
    ida = dict(zip(largos, libres))
    f = e
    for v, c in ida.items():
        f = mx.substitute(f, v, mx.Sym(c))
    try:
        N, D = _nd(f)
        if not D:
            return None
        if not N:
            return mx.Num(Fraction(0))
        N, D = _cancela(N, D)
        if D[max(D, key=lambda m: (P.mono_degree(m), m))] < 0:
            N, D = P.scale(N, -1), P.scale(D, -1)
        num = P.to_expr(N)
        if len(D) == 1 and () in D:
            out = P.to_expr(P.scale(N, 1 / D[()]))
        else:
            out = mx.Div(num, P.to_expr(D))
    except Exception:  # noqa: BLE001 - tamaño, atomos raros: se deja como estaba
        return None
    for v, c in ida.items():
        out = mx.substitute(out, c, mx.Sym(v))
    return out


def _nd(e: mx.Expr):
    from academic_core.domain.engineering.mathlab import poly as P

    uno = {(): Fraction(1)}
    if isinstance(e, (mx.Add, mx.Sub)):
        n1, d1 = _nd(e.left)
        n2, d2 = _nd(e.right)
        if d1 == d2:
            return P.add(n1, n2, 1 if isinstance(e, mx.Add) else -1), d1
        return (P.add(P.mul(n1, d2), P.mul(n2, d1), 1 if isinstance(e, mx.Add) else -1),
                P.mul(d1, d2))
    if isinstance(e, mx.Mul):
        n1, d1 = _nd(e.left)
        n2, d2 = _nd(e.right)
        return P.mul(n1, n2), P.mul(d1, d2)
    if isinstance(e, mx.Div):
        n1, d1 = _nd(e.left)
        n2, d2 = _nd(e.right)
        return P.mul(n1, d2), P.mul(d1, n2)
    if isinstance(e, mx.Neg):
        n, d = _nd(e.arg)
        return P.scale(n, -1), d
    if isinstance(e, mx.Pow):
        k = mx.exact_integer(e.exponent)
        if k is not None and abs(k) <= 12:
            n, d = _nd(e.base)
            pn, pd = uno, uno
            for _ in range(abs(k)):
                pn, pd = P.mul(pn, n), P.mul(pd, d)
            return (pn, pd) if k >= 0 else (pd, pn)
    return P.as_poly(e), uno


def _sin_abs_pares(p):
    """|u|^(2k) = u^(2k) y (√u)^k = u^(k//2)·(√u)^(k mod 2) dentro de un polinomio
    sobre átomos."""
    from academic_core.domain.engineering.mathlab import poly as P

    out = {}
    for m, c in p.items():
        term = {(): c}
        resto = []
        for v, k in m:
            texto = P.atom_text(v) if P.is_atom(v) else ""
            if P.es_llamada(texto, "sqrt") and k >= 2:
                u = P.as_poly(mx.parse(texto[5:-1]))
                for _ in range(k // 2):
                    term = P.mul(term, u)
                if k % 2:
                    resto.append((v, 1))
                continue
            if P.is_atom(v) and P.atom_text(v).startswith("abs(") and k >= 2:
                u = P.as_poly(mx.parse(P.atom_text(v)[4:-1]))
                for _ in range(k // 2):
                    term = P.mul(term, P.mul(u, u))
                if k % 2:
                    resto.append((v, 1))
            else:
                resto.append((v, k))
        term = P.mul(term, {tuple(sorted(resto)): Fraction(1)})
        out = P.add(out, term)
    return out


def _cancela(N, D):
    from academic_core.domain.engineering.mathlab import poly as P

    N, D = _sin_abs_pares(N), _sin_abs_pares(D)

    # factor monomio común
    nombres = {v for m in list(N) + list(D) for v, _ in m}
    comun = []
    for v in sorted(nombres):
        k = min(P.mono_exp(m, v) for m in list(N) + list(D))
        if k > 0:
            comun.append((v, k))
    if comun:
        c = tuple(comun)
        N = {P.mono_div(m, c): x for m, x in N.items()}
        D = {P.mono_div(m, c): x for m, x in D.items()}
    # D divide a N
    q = _division_exacta(N, D)
    if q is not None:
        return q, {(): Fraction(1)}
    # N divide a D (resultado 1/q)
    q = _division_exacta(D, N)
    if q is not None:
        return {(): Fraction(1)}, q
    # coeficiente principal de D a 1
    lc = D[max(D)]
    return P.scale(N, 1 / lc), P.scale(D, 1 / lc)


def _division_exacta(N, D):
    from academic_core.domain.engineering.mathlab import poly as P

    if len(D) == 1 and () in D:
        return P.scale(N, 1 / D[()])
    nombres = sorted({v for m in list(N) + list(D) for v, _ in m})

    def clave(m):
        return tuple(P.mono_exp(m, v) for v in nombres)
    q = {}
    r = dict(N)
    ld = max(D, key=clave)
    pasos = 0
    while r:
        pasos += 1
        if pasos > 200:
            return None
        lr = max(r, key=clave)
        t = P.mono_div(lr, ld)
        if t is None:
            return None
        c = r[lr] / D[ld]
        q[t] = q.get(t, Fraction(0)) + c
        r = P.add(r, P.mul({t: c}, D), -1)
    return q


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
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _bonito(e.radicand))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_bonito(x) for x in e.args))
    if isinstance(e, mx.Pow):
        return mx.Pow(_bonito(e.base), e.exponent)
    return e


def _canon_profundo(e: mx.Expr) -> mx.Expr:
    """Forma normal también dentro de raíces y funciones (√(4 − x²) y √(−x² + 4)
    pasan a ser el mismo átomo)."""
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, _forma_fija(_canon_profundo(e.radicand)))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_forma_fija(_canon_profundo(a)) for a in e.args))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_canon_profundo(e.left), _canon_profundo(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_canon_profundo(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_canon_profundo(e.base), _canon_profundo(e.exponent))
    return e


def _forma_fija(e: mx.Expr) -> mx.Expr:
    """Forma normal polinómica SIEMPRE (no la más corta): dos escrituras del mismo
    radicando dan el mismo texto y por tanto el mismo átomo."""
    from academic_core.domain.engineering.mathlab import poly as P

    largos = sorted(v for v in mx.variables(e) if len(v) > 1)
    libres = [c for c in "ABCDFGHJKLMNOPQRSTUVW" if c not in mx.variables(e)]
    ida = dict(zip(largos, libres))
    f = e
    for v, c in ida.items():
        f = mx.substitute(f, v, mx.Sym(c))
    try:
        g = _bonito(P.to_expr(P.as_poly(f)))
    except Exception:  # noqa: BLE001
        return e
    for v, c in ida.items():
        g = mx.substitute(g, c, mx.Sym(v))
    return g


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
    if isinstance(e, mx.Call) and e.name in ("csc", "sec", "cot") and len(e.args) == 1:
        u = _logexp(e.args[0])
        if e.name == "cot":
            return mx.Div(mx.Call("cos", (u,)), mx.Call("sin", (u,)))
        return mx.Div(mx.Num(Fraction(1)), mx.Call("sin" if e.name == "csc" else "cos", (u,)))
    if isinstance(e, mx.Call) and e.name == "log" and len(e.args) == 2:
        b, a = _logexp(e.args[0]), _logexp(e.args[1])
        k = _log_racional(a, b)
        if k is not None:
            return leer(k)
        return mx.Div(mx.Call("ln", (a,)), mx.Call("ln", (b,)))
    if isinstance(e, mx.Div) and isinstance(e.left, mx.Call) and isinstance(e.right, mx.Call) \
            and e.left.name == "ln" and e.right.name == "ln":
        k = _log_racional(_logexp(e.left.args[0]), _logexp(e.right.args[0]))
        if k is not None:
            return leer(k)
    if isinstance(e, mx.Call):
        args = tuple(_logexp(a) for a in e.args)
        if len(args) == 1 and isinstance(args[0], mx.Call) and len(args[0].args) == 1:
            z = args[0].args[0]
            uno = mx.Num(Fraction(1))
            dos = mx.Num(Fraction(2))
            comp = {
                ("sin", "asin"): lambda: z, ("cos", "acos"): lambda: z, ("tan", "atan"): lambda: z,
                ("cos", "asin"): lambda: mx.Root(2, mx.Sub(uno, mx.Pow(z, dos))),
                ("sin", "acos"): lambda: mx.Root(2, mx.Sub(uno, mx.Pow(z, dos))),
                ("tan", "asin"): lambda: mx.Div(z, mx.Root(2, mx.Sub(uno, mx.Pow(z, dos)))),
                ("sin", "atan"): lambda: mx.Div(z, mx.Root(2, mx.Add(uno, mx.Pow(z, dos)))),
                ("cos", "atan"): lambda: mx.Div(uno, mx.Root(2, mx.Add(uno, mx.Pow(z, dos)))),
                ("sec", "atan"): lambda: mx.Root(2, mx.Add(uno, mx.Pow(z, dos))),
                ("sinh", "asinh"): lambda: z, ("cosh", "acosh"): lambda: z,
                ("cosh", "asinh"): lambda: mx.Root(2, mx.Add(uno, mx.Pow(z, dos))),
                ("exp", "ln"): lambda: z,
            }.get((e.name, args[0].name))
            if comp is not None:
                return _logexp(comp())
        if e.name in ("asin", "acos", "atan") and not mx.variables(args[0]) and len(args) == 1:
            k = _angulo_notable(e.name, args[0])
            if k is not None:
                return k
        if e.name == "exp" and isinstance(args[0], mx.Call) and args[0].name in ("W", "Wm1"):
            u = args[0].args[0]                       # W·e^W = u ⇒ e^W = u/W
            return mx.Div(u, args[0])
        if e.name == "abs" and isinstance(args[0], mx.Call) and args[0].name == "exp":
            return args[0]                                  # eᵘ > 0
        if e.name == "abs" and isinstance(args[0], mx.Root) and args[0].degree % 2 == 0:
            return args[0]                                  # raíz par ≥ 0
        if e.name in ("erf", "erfi", "Si", "FresnelS", "FresnelC", "W", "sin", "tan", "asin",
                      "atan", "sinh", "tanh") and mx.exact_value(args[0]) == 0 \
                and not mx.variables(args[0]):
            return mx.Num(Fraction(0))
        if e.name == "ln" and args[0] == mx.Const("e"):
            return mx.Num(Fraction(1))
        if e.name == "ln" and isinstance(args[0], mx.Call) and args[0].name == "exp":
            return args[0].args[0]
        if e.name == "exp" and isinstance(args[0], mx.Call) and args[0].name == "ln":
            return args[0].args[0]
        if e.name == "exp":
            a0 = args[0]
            neg = isinstance(a0, mx.Neg)
            a1 = a0.arg if neg else a0
            if isinstance(a1, mx.Mul) and isinstance(a1.right, mx.Call) and a1.right.name == "ln" \
                    and mx.exact_value(a1.left) is not None and not mx.variables(a1.left):
                k = Fraction(mx.exact_value(a1.left)) * (-1 if neg else 1)
                return mx.Pow(a1.right.args[0], leer(k))
            if neg and isinstance(a1, mx.Call) and a1.name == "ln":
                return mx.Div(mx.Num(Fraction(1)), a1.args[0])
        return mx.Call(e.name, args)
    if isinstance(e, mx.Sub) and mx.exact_value(e.right) == 0:
        return _logexp(e.left)
    if isinstance(e, mx.Div) and mx.exact_value(e.right) == 1:
        return _logexp(e.left)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_logexp(e.left), _logexp(e.right))
    if isinstance(e, mx.Pow):
        if e.base == mx.Const("e"):
            return _logexp(mx.Call("exp", (e.exponent,)))
        if mx.exact_value(e.exponent) == 1 and not mx.variables(e.exponent):
            return _logexp(e.base)                       # u¹ = u
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
    elif isinstance(e, mx.Root):
        e = mx.Root(e.degree, _pitagoras(e.radicand))
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
                if P.is_atom(v) and P.es_llamada(v, "cos") and k >= 2:
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
        lin = _linealiza_trig(f)
        for _ in range(3):                       # cos²(2x) aparece en la segunda vuelta
            if lin is f:
                break
            F = _por_terminos(lin, var)
            if F is not None:
                break
            otra = _linealiza_trig(_canon(lin))
            if mx.text(otra) == mx.text(lin):
                break
            lin = otra
        if F is not None:
            trace.regla("multiple.linealiza", f"{mx.text(f)} = {mx.text(_limpio(lin))}",
                        why="potencias de sen y cos (y senh, cosh) a ángulo doble: "
                            "sen²u = (1 − cos 2u)/2, cos²u = (1 + cos 2u)/2, "
                            "sen u·cos u = sen 2u/2")
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


def _linealiza_trig(e: mx.Expr) -> mx.Expr:
    """Reescribe sen²u, cos²u y sen u·cos u (también dentro de potencias pares
    mayores) con el ángulo doble; devuelve el mismo objeto si no hay nada que hacer."""
    def dos(u):
        return mx.Mul(mx.Num(Fraction(2)), u)

    def lin(n):
        if isinstance(n, mx.Pow) and isinstance(n.base, mx.Call) and \
                n.base.name in ("sinh", "cosh"):
            k = mx.exact_integer(n.exponent)
            if k is not None and k >= 2:
                u = n.base.args[0]
                ch2 = mx.Call("cosh", (dos(u),))
                cuadrado = mx.Div(mx.Sub(ch2, mx.Num(Fraction(1))) if n.base.name == "sinh"
                                  else mx.Add(ch2, mx.Num(Fraction(1))), mx.Num(Fraction(2)))
                resto = (mx.Num(Fraction(1)) if k == 2 else
                         lin(mx.Pow(n.base, mx.Num(Fraction(k - 2)))))
                return mx.Mul(cuadrado, resto)
        if isinstance(n, mx.Pow) and isinstance(n.base, mx.Call) and n.base.name in ("sin", "cos"):
            k = mx.exact_integer(n.exponent)
            if k is not None and k >= 2:
                u = n.base.args[0]
                signo = mx.Sub if n.base.name == "sin" else mx.Add
                cuadrado = mx.Div(signo(mx.Num(Fraction(1)), mx.Call("cos", (dos(u),))),
                                  mx.Num(Fraction(2)))
                resto = (mx.Num(Fraction(1)) if k == 2 else
                         lin(mx.Pow(n.base, mx.Num(Fraction(k - 2)))))
                return mx.Mul(cuadrado, resto)
        if isinstance(n, mx.Mul):
            a, b = n.left, n.right
            if (isinstance(a, mx.Call) and isinstance(b, mx.Call) and {a.name, b.name} ==
                    {"sin", "cos"} and a.args == b.args):
                return mx.Div(mx.Call("sin", (dos(a.args[0]),)), mx.Num(Fraction(2)))
            if (isinstance(a, mx.Call) and isinstance(b, mx.Call) and {a.name, b.name} ==
                    {"sinh", "cosh"} and a.args == b.args):
                return mx.Div(mx.Call("sinh", (dos(a.args[0]),)), mx.Num(Fraction(2)))
            return mx.Mul(lin(a), lin(b))
        if isinstance(n, (mx.Add, mx.Sub, mx.Div)):
            return type(n)(lin(n.left), lin(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(lin(n.arg))
        return n
    out = lin(e)
    return e if mx.text(out) == mx.text(e) else out


def _por_terminos(e: mx.Expr, var: str) -> mx.Expr | None:
    """Primitiva término a término de la forma expandida."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        p = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return None
    partes = []
    for m, c in p.items():
        Fi = _e01(P.to_expr({m: c}), var)
        if Fi is None:
            return None
        partes.append(Fi)
    if not partes:
        return mx.Num(Fraction(0))
    F = partes[0]
    for Fi in partes[1:]:
        F = mx.Add(F, Fi)
    return F


def _e01(f: mx.Expr, var: str) -> mx.Expr | None:
    from academic_core.domain.engineering.symbolic import integrate as I
    from academic_core.domain.engineering.symbolic import steps as S

    if var not in mx.variables(f):
        return mx.Mul(f, mx.Sym(var))
    # factores constantes (π, e, otras variables), arriba o abajo, fuera
    from academic_core.domain.engineering.mathlab import limite as LM

    nums, dens = LM._factores(f)
    cn = [g for g in nums if var not in mx.variables(g) and mx.exact_value(g) != 1]
    cd = [g for g in dens if var not in mx.variables(g) and mx.exact_value(g) != 1]
    nums = [g for g in nums if not (var not in mx.variables(g) and mx.exact_value(g) == 1)]
    if (cn or cd) and (len(cn) < len(nums) or len(cd) < len(dens)):
        rn = [g for g in nums if var in mx.variables(g)]
        rd = [g for g in dens if var in mx.variables(g)]
        G = LM._reconstruye(rn, rd)
        Fg = _e01(G, var)
        if Fg is None:
            return None
        return mx.Mul(LM._reconstruye(cn, cd), Fg)
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

    def __post_init__(self) -> None:
        # con valor exacto (ya contrastado con la cuadratura) el decimal sale de él:
        # la cuadratura cerca de una singularidad integrable pierde cifras
        if self.exacto is not None:
            v = mx.valor_real(self.exacto, {})
            if v is not None and math.isfinite(float(v)):
                object.__setattr__(self, "numerico", float(v))

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
    from academic_core.domain.engineering.mathlab import integracion as IN

    if len(L) == 1:
        trozos = _trocea_abs(f, L[0][0], L[0][1], L[0][2], trace)
        if trozos is not None:
            partes = [iterada(g, [[L[0][0], a, b]], trace) for g, a, b in trozos]
            num_t = sum(p.numerico for p in partes)
            if all(p.exacto is not None for p in partes):
                tot = partes[0].exacto
                for p in partes[1:]:
                    tot = mx.Add(tot, p.exacto)
                return Resultado(_limpio(tot), num_t, True)
            return Resultado(None, num_t, False)
    try:
        for v, lo, hi in L:
            F = IN.primitiva(exacto, v, trace)
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
    if not coincide:
        # p. ej. una primitiva con 1/v que Barrow no puede evaluar en v = 0: con
        # límites constantes se prueba el otro orden
        otro = _otro_orden(f, L, trace)
        if otro is not None:
            try:
                vo = float(mx.valor_real(otro, {}))
            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                vo = math.nan
            if abs(vo - num) <= 1e-7 * max(1.0, abs(num)):
                exacto, val, coincide = otro, vo, True
    if coincide:
        trace.verificacion("multiple.gauss", f"cuadratura tanh-sinh anidada da {num:.12g}: coincide",
                           why="segundo camino independiente de las primitivas")
    else:
        trace.aviso("multiple.discrepa", f"exacto {val:.12g} frente a numérico {num:.12g}: "
                    "¿discontinuidad o singularidad en la región? se da el numérico")
    return Resultado(exacto if coincide else None, num, coincide)


def _trocea_abs(f: mx.Expr, var: str, lo: mx.Expr, hi: mx.Expr, trace: Trace):
    """|u(x)| en el integrando: se parte [a, b] en los ceros de u y en cada trozo
    |u| = ±u. None si no hay valor absoluto o sus ceros no salen exactos."""
    from academic_core.domain.engineering.mathlab import raices as RZ

    abss = [n for n in _nodos(f) if isinstance(n, mx.Call) and n.name == "abs"
            and var in mx.variables(n.args[0])]
    if not abss:
        return None
    try:
        a, b = float(mx.valor_real(lo, {})), float(mx.valor_real(hi, {}))
    except (TypeError, ValueError):
        return None
    cortes = []
    for n in abss:
        try:
            c = RZ.ceros(n.args[0], var, (min(a, b), max(a, b)))
        except Exception:  # noqa: BLE001
            return None
        for r in c.raices:
            if min(a, b) < r.x < max(a, b):
                if not r.exacta:
                    return None
                cortes.append((r.x, r.valor))
    puntos = [(a, lo)] + sorted({round(x, 12): (x, e) for x, e in cortes}.values()) + [(b, hi)]
    trozos = []
    for (x0, e0), (x1, e1) in zip(puntos, puntos[1:]):
        medio = (x0 + x1) / 2

        def quita(n):
            if isinstance(n, mx.Call) and n.name == "abs" and var in mx.variables(n.args[0]):
                arg = quita(n.args[0])
                v = mx.valor_real(arg, {var: medio})
                return arg if v is None or v >= 0 else mx.Neg(arg)
            if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
                return type(n)(quita(n.left), quita(n.right))
            if isinstance(n, mx.Neg):
                return mx.Neg(quita(n.arg))
            if isinstance(n, mx.Pow):
                return mx.Pow(quita(n.base), quita(n.exponent))
            if isinstance(n, mx.Root):
                return mx.Root(n.degree, quita(n.radicand))
            if isinstance(n, mx.Call):
                return mx.Call(n.name, tuple(quita(x) for x in n.args))
            return n
        trozos.append((_limpio(quita(f)), e0, e1))
    trace.regla("multiple.trozos_abs", "se parte en " + ", ".join(mx.text(e) for _, e in cortes) +
                ": " + "; ".join(f"[{mx.text(a_)}, {mx.text(b_)}]: {mx.text(g)}"
                                 for g, a_, b_ in trozos),
                why="|u| = u donde u ≥ 0 y −u donde u < 0")
    return trozos


def _otro_orden(f: mx.Expr, L, trace: Trace) -> mx.Expr | None:
    """Con todos los límites constantes (rectángulo o caja) el orden es libre
    (Fubini): si uno no tiene primitiva exacta se prueban los demás."""
    import itertools

    from academic_core.domain.engineering.mathlab import integracion as IN

    if len(L) < 2 or any(mx.variables(lo) | mx.variables(hi) for _, lo, hi in L):
        return None
    for orden in itertools.permutations(L):
        if list(orden) == list(L):
            continue
        t = Trace()
        exacto = f
        try:
            for v, lo, hi in orden:
                F = IN.primitiva(exacto, v, t)
                exacto = _limpio(mx.Sub(_limpio(mx.substitute(F, v, hi)),
                                        _limpio(mx.substitute(F, v, lo))))
        except UnsupportedError:
            continue
        trace.regla("multiple.otro_orden", "se cambia al orden " + " ".join(
            f"d{v}" for v, _, _ in orden) + ", donde sí hay primitivas exactas",
            why="límites constantes: Fubini permite integrar en cualquier orden")
        exacto = f
        for v, lo, hi in orden:                      # se repite con la traza buena
            F = IN.primitiva(exacto, v, trace)
            arriba = _limpio(mx.substitute(F, v, hi))
            abajo = _limpio(mx.substitute(F, v, lo))
            exacto = _limpio(mx.Sub(arriba, abajo))
            trace.regla("multiple.barrow",
                        f"[{mx.text(F)}] de {v} = {mx.text(lo)} a {v} = {mx.text(hi)}: "
                        f"({mx.text(arriba)}) − ({mx.text(abajo)}) = {mx.text(exacto)}",
                        why="regla de Barrow: F(límite superior) − F(límite inferior)")
        return exacto
    return None


_FUNCIONES = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
              "ln": math.log, "log": math.log, "sqrt": math.sqrt, "asin": math.asin,
              "acos": math.acos, "atan": math.atan, "arcsin": math.asin,
              "arccos": math.acos, "arctan": math.atan, "sinh": math.sinh,
              "cosh": math.cosh, "tanh": math.tanh, "abs": abs}


def compilar(e: mx.Expr, nombres: list[str]):
    """Expr → función de Python (float); None si hay un nodo que no se traduce.

    Se compila a clausuras anidadas, no a texto con ``eval`` (prohibido por la
    prueba de seguridad F15-017; antes fallaba el CI)."""
    def c(n):
        if isinstance(n, mx.Num):
            k = float(n.value)
            return lambda v: k
        if isinstance(n, mx.Sym):
            i = nombres.index(n.name)
            return lambda v: v[i]
        if isinstance(n, mx.Const):
            k = {"pi": math.pi, "e": math.e}[n.name]
            return lambda v: k
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            a, b = c(n.left), c(n.right)
            if isinstance(n, mx.Add):
                return lambda v: a(v) + b(v)
            if isinstance(n, mx.Sub):
                return lambda v: a(v) - b(v)
            if isinstance(n, mx.Mul):
                return lambda v: a(v) * b(v)
            return lambda v: a(v) / b(v)
        if isinstance(n, mx.Pow):
            a, b = c(n.base), c(n.exponent)
            return lambda v: _pot(a(v), b(v))
        if isinstance(n, mx.Neg):
            a = c(n.arg)
            return lambda v: -a(v)
        if isinstance(n, mx.Root):
            a, g = c(n.radicand), int(n.degree)
            return lambda v: _raiz(a(v), g)
        if isinstance(n, mx.Call) and n.name in _FUNCIONES and len(n.args) == 1:
            f, a = _FUNCIONES[n.name], c(n.args[0])
            return lambda v: f(a(v))
        raise KeyError(type(n).__name__)

    try:
        return c(e)
    except (KeyError, ValueError, AttributeError):
        return None


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
            if v[k] == a or v[k] == b:
                continue        # el nodo se redondea al extremo: no se evalúa nunca
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

    cand: list[mx.Expr] = []
    if isinstance(g, mx.Div) and g.right == mx.Sym(x) and mx.exact_value(g.left) is not None \
            and not mx.variables(g.left):
        cand.append(mx.Div(g.left, Y))                     # u = c/x ⇒ x = c/u
    pol = RZ._polinomio_de(g, x)
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
    # sen y cos: todas las ramas de la inversa en unas cuantas vueltas
    for h, ramas in (("sin", ((1, "asin", 0), (-1, "asin", 1))),
                     ("cos", ((1, "acos", 0), (-1, "acos", 0)))):
        lin = _lineal_en(g, mx.Call(h, (mx.Sym(x),)), x)
        if lin is None:
            continue
        c, d = lin
        u = Y if d == 0 else mx.Sub(Y, leer(d))
        u = u if c == 1 else mx.Div(u, leer(c))
        for signo, inv, pi_extra in ramas:
            base = mx.Call(inv, (u,))
            base = base if signo > 0 else mx.Neg(base)
            for k in range(-3, 4):
                desplaz = 2 * k + pi_extra          # múltiplo de π que se suma
                cand.append(base if desplaz == 0 else
                            mx.Add(mx.Mul(leer(desplaz), mx.Const("pi")), base))
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
    cortes_x = _cortes_monotonia((g1, g2), x, a, b, fa, fb)
    if cortes_x:
        trace.regla("multiple.partir", f"g₁ o g₂ cambian de monotonía en {x} = " +
                    ", ".join(mx.text(c) for c in cortes_x) + ": se parte la región ahí",
                    why="en cada trozo las curvas son monótonas y tienen inversa")
        puntos = [a] + cortes_x + [b]
        todas, origs, nuevos = [], [], []
        for lo, hi in zip(puntos, puntos[1:]):
            fr, o, nv = cambio_orden(f, x, lo, hi, y, g1, g2, trace)
            todas.extend(fr)
            origs.append(o)
            nuevos.append(nv)
        def junta(rs):
            num = sum(r.numerico for r in rs)
            if all(r.exacto is not None for r in rs):
                tot = rs[0].exacto
                for r in rs[1:]:
                    tot = mx.Add(tot, r.exacto)
                return Resultado(_limpio(tot), num, all(r.coincide for r in rs))
            return Resultado(None, num, False)
        return todas, junta(origs), junta(nuevos)
    for g in (g1, g2):
        d = [ev(g, t2) - ev(g, t1) for t1, t2 in zip(muestras, muestras[1:])]
        if any(u > 1e-12 for u in d) and any(u < -1e-12 for u in d):
            raise _no(f"{mx.text(g)} no es monótona en [{mx.text(a)}, {mx.text(b)}] y sus "
                      "extremos no se localizan exactos")
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


def _cortes_monotonia(gs, x, a, b, fa, fb) -> list[mx.Expr]:
    """Ceros de g′ estrictamente dentro de (a, b) donde g cambia de sentido (exactos)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import raices as RZ

    cortes: list[tuple[float, mx.Expr]] = []
    for g in gs:
        if x not in mx.variables(g):
            continue
        dg = _limpio(DM.differentiate(g, x))
        if x not in mx.variables(dg):
            continue
        try:
            ceros = RZ.ceros(dg, x, (fa, fb))
        except Exception:  # noqa: BLE001
            continue
        for r in ceros.raices:
            if fa + 1e-9 < r.x < fb - 1e-9 and r.exacta:
                izq = float(mx.valor_real(dg, {x: r.x - 1e-6}))
                der = float(mx.valor_real(dg, {x: r.x + 1e-6}))
                if izq * der < 0 and all(abs(r.x - c) > 1e-9 for c, _ in cortes):
                    cortes.append((r.x, r.valor))
    return [e for _, e in sorted(cortes, key=lambda c: c[0])]


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
