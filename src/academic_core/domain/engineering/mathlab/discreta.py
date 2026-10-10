# SPDX-License-Identifier: MIT
"""ML-17, bloque 8 (G): lógica, conjuntos, binomio, recurrencias, complejidad,
programación dinámica/voraz y tiempo real.

Todo determinista y sin dependencias: las tablas son enumeración exhaustiva,
las fórmulas cerradas se comprueban iterando y la simulación usa el
Generador sembrado de ``eventos``. Cada función escribe su «por qué» (§5.5b)
y verifica por un segundo camino (§5.3).
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        raise _error("BAD_INPUT", f"«{x}» no es un número racional")


def _f(x) -> float:
    return float(_Q(x))


# ---------------------------------------------------------------------------
# lógica proposicional: tablas y leyes
# ---------------------------------------------------------------------------

class _Lex:
    def __init__(self, s: str):
        self.toks, i = [], 0
        while i < len(s):
            c = s[i]
            if c.isspace():
                i += 1
            elif c in "()":
                self.toks.append(c)
                i += 1
            elif s.startswith("->", i) or s.startswith("=>", i):
                self.toks.append("->")
                i += 2
            elif s.startswith("<->", i) or s.startswith("<=>", i):
                self.toks.append("<->")
                i += 3
            elif c in "¬~!":
                self.toks.append("no")
                i += 1
            elif c in "∧&":
                self.toks.append("y")
                i += 1
            elif c in "∨|":
                self.toks.append("o")
                i += 1
            elif c.isalpha() or c == "_":
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                w = s[i:j].lower()
                self.toks.append({"and": "y", "or": "o", "not": "no"}.get(w, s[i:j]))
                i = j
            else:
                raise _error("BAD_INPUT", f"carácter «{c}» en la fórmula")
        self.pos = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def next(self):
        t = self.peek()
        self.pos += 1
        return t


def _parse_logica(s: str):
    """Fórmula → ('var', nombre) | ('no', f) | ('y'/'o'/'->'/'<->', a, b)."""
    lx = _Lex(s)

    def equiv():
        a = impl()
        while lx.peek() == "<->":
            lx.next()
            a = ("<->", a, impl())
        return a

    def impl():
        a = disy()
        while lx.peek() == "->":
            lx.next()
            a = ("->", a, impl())
        return a

    def disy():
        a = conj()
        while lx.peek() == "o":
            lx.next()
            a = ("o", a, conj())
        return a

    def conj():
        a = neg()
        while lx.peek() == "y":
            lx.next()
            a = ("y", a, neg())
        return a

    def neg():
        if lx.peek() == "no":
            lx.next()
            return ("no", neg())
        if lx.peek() == "(":
            lx.next()
            a = equiv()
            if lx.next() != ")":
                raise _error("BAD_INPUT", "falta «)»")
            return a
        t = lx.next()
        if not isinstance(t, str) or t in ("y", "o", "no", "->", "<->", ")", None):
            raise _error("BAD_INPUT", "se esperaba una variable")
        return ("var", t)

    r = equiv()
    if lx.peek() is not None:
        raise _error("BAD_INPUT", f"sobra «{lx.peek()}» en la fórmula")
    return r


def _vars_logica(f) -> list[str]:
    if f[0] == "var":
        return [f[1]]
    if f[0] == "no":
        return _vars_logica(f[1])
    out = []
    for g in f[1:]:
        for v in _vars_logica(g):
            if v not in out:
                out.append(v)
    return out


def _eval_logica(f, env: dict) -> bool:
    if f[0] == "var":
        return env[f[1]]
    if f[0] == "no":
        return not _eval_logica(f[1], env)
    a, b = _eval_logica(f[1], env), _eval_logica(f[2], env)
    if f[0] == "y":
        return a and b
    if f[0] == "o":
        return a or b
    if f[0] == "->":
        return (not a) or b
    return a == b  # <->


def tabla_verdad(formula: str, trace: Trace | None = None) -> dict:
    """Tabla completa de 2ⁿ valoraciones (hasta 4 variables, si no leyes)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.logica_tabla", "enumerar las 2ⁿ valoraciones",
                 why="con ≤ 4 variables la tabla es el método directo y "
                     "exhaustivo (§4.8)")
    f = _parse_logica(formula)
    vs = _vars_logica(f)
    if len(vs) > 8:
        raise _no("más de 8 variables (256 filas): por leyes, no por tabla (se dice)")
    filas = []
    for k in range(2 ** len(vs)):
        env = {v: bool((k >> i) & 1) for i, v in enumerate(vs)}
        filas.append((env, _eval_logica(f, env)))
    trace.verificacion("sen.logica_exhaustiva",
                       f"{len(filas)} valoraciones: "
                       f"{'tautología' if all(v for _, v in filas) else 'contingencia' if any(v for _, v in filas) else 'contradicción'}")
    return {"vars": vs, "filas": filas}


def equivalencia(f_texto: str, g_texto: str, trace: Trace | None = None) -> dict:
    """¿Son equivalentes? Tablas frente a frente + leyes nombradas."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.logica_equiv", "misma tabla + ley que la explica",
                 why="coincidir en las 2ⁿ filas ES la equivalencia; la ley "
                     "nombrada (De Morgan, contrarrecíproco, definición de ⇒) "
                     "dice por qué")
    f, g = _parse_logica(f_texto), _parse_logica(g_texto)
    vs = sorted(set(_vars_logica(f)) | set(_vars_logica(g)))
    if len(vs) > 12:
        raise _no("más de 12 variables: por leyes")
    contra = None
    for k in range(2 ** len(vs)):
        env = {v: bool((k >> i) & 1) for i, v in enumerate(vs)}
        if _eval_logica(f, env) != _eval_logica(g, env):
            contra = env
            break
    ok = contra is None
    trace.verificacion("sen.logica_tablas",
                       f"las {2 ** len(vs)} valoraciones coinciden" if ok else
                       "difieren en " + ", ".join(f"{v} = {'V' if x else 'F'}"
                                                  for v, x in contra.items()))
    return {"equivalentes": ok, "contraejemplo": contra}


def negar_cuantificador(cuant: str, var: str, matriz: str,
                        trace: Trace | None = None) -> dict:
    """¬∀x·P ≡ ∃x·¬P (y dual): negación símbolo a símbolo."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.logica_cuant", "¬∀ es ∃¬ y ¬∃ es ∀¬, símbolo a símbolo",
                 why="dualidad de cuantificadores: la negación cruza el "
                     "cuantificador cambiándolo (§4.8)")
    if cuant not in ("forall", "exists"):
        raise _error("BAD_INPUT", "cuantificador forall o exists")
    dual = "exists" if cuant == "forall" else "forall"
    simbolo = "∃" if dual == "exists" else "∀"
    out = f"{simbolo}{var} ¬({matriz})"
    trace.hipotesis("sen.logica_dominio", "dominio del cuantificador explícito",
                    "cumple (lo da la entrada)")
    trace.verificacion("sen.logica_dual", out)
    return {"negacion": out}


# ---------------------------------------------------------------------------
# conjuntos
# ---------------------------------------------------------------------------

def _conj(d: dict) -> frozenset:
    if isinstance(d, dict) and "elementos" in d:
        return frozenset(d["elementos"])
    if isinstance(d, (list, tuple, set)):
        return frozenset(d)
    raise _error("BAD_INPUT", "conjunto como lista de elementos")


def operacion_conjuntos(a, b, op: str, trace: Trace | None = None) -> dict:
    """Unión, intersección, diferencia y cardinal por fórmula y por lista."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conjuntos", "operar por comprensión y contar por fórmula",
                 why="la cardinalidad por inclusión-exclusión frente a la "
                     "enumeración es el segundo camino (§4.8)")
    A, B = _conj(a), _conj(b)
    if op == "union":
        r, esperado, ley = A | B, len(A) + len(B) - len(A & B), "|A| + |B| − |A ∩ B|"
    elif op == "interseccion":
        r, esperado, ley = A & B, len(A) + len(B) - len(A | B), "|A| + |B| − |A ∪ B|"
    elif op == "diferencia":
        r, esperado, ley = A - B, len(A) - len(A & B), "|A| − |A ∩ B|"
    else:
        raise _error("BAD_INPUT", "operación union, interseccion o diferencia")
    # segundo camino: el cardinal por la fórmula de inclusión-exclusión
    if len(r) != esperado:
        raise _error("DISCREPANT", f"|resultado| = {len(r)} ≠ {ley} = {esperado}")
    trace.verificacion("sen.conjuntos_cardinal", f"|resultado| = {ley} = {esperado}")
    return {"elementos": sorted(r), "cardinal": len(r)}


def potencia_n(n: int, trace: Trace | None = None) -> dict:
    """Conjunto potencia: 2ⁿ subconjuntos; se enumeran hasta n = 12 (4096)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.potencia", "cada elemento está o no está: 2 opciones por elemento",
                 why="la biyección subconjunto ↔ número binario de n cifras da 2ⁿ")
    n = int(_Q(n))
    if n < 0:
        raise _error("BAD_INPUT", "n ≥ 0")
    if n > 12:
        trace.aviso("sen.potencia_grande", f"n = {n}: se da el cardinal sin enumerar "
                                           f"los {2 ** n} subconjuntos")
        trace.verificacion("sen.potencia_cardinal",
                           f"|P| = 2^{n} = Σ C({n},k) = {sum(math.comb(n, i) for i in range(n + 1))}")
        return {"subconjuntos": None, "cardinal": 2 ** n}
    els = list(range(n))
    subs = [[e for j, e in enumerate(els) if (k >> j) & 1] for k in range(2 ** n)]
    # segundo camino: contar por tamaños, Σ C(n,k), y que no haya repetidos
    if len({tuple(x) for x in subs}) != 2 ** n or \
            sum(math.comb(n, i) for i in range(n + 1)) != 2 ** n:
        raise _error("DISCREPANT", "la enumeración no da 2ⁿ subconjuntos distintos")
    trace.verificacion("sen.potencia_cardinal", f"|P| = 2^{n} = Σ C({n},k) = {2 ** n}")
    return {"subconjuntos": subs, "cardinal": 2 ** n}


# ---------------------------------------------------------------------------
# binomio
# ---------------------------------------------------------------------------

def _comb(n: int, k: int) -> int:
    n, k = int(n), int(k)
    if not (0 <= k <= n):
        return 0
    return math.comb(n, k)


def binomio_termino(n, k, trace: Trace | None = None) -> dict:
    """Término C(n,k) con simetría y comprobación por filas que suman 2ⁿ."""
    trace = trace if trace is not None else Trace()
    trace.metodo("senbinomio", "C(n,k) exacto con simetría C(n,k) = C(n,n−k)",
                 why="el coeficiente es entero exacto: la simetría lo comprueba")
    n, k = int(_Q(n)), int(_Q(k))
    if not (n >= 0 and 0 <= k <= n):
        raise _error("BAD_INPUT", "0 ≤ k ≤ n con n entero")
    c = _comb(n, k)
    if c != _comb(n, n - k):
        raise _error("DISCREPANT", "simetría rota")
    if sum(_comb(n, j) for j in range(n + 1)) != 2 ** n:
        raise _error("DISCREPANT", "la fila no suma 2ⁿ")
    trace.verificacion("sen.binomio_fila", f"fila {n} suma 2^{n}")
    return {"C": c}


def vandermonde(r, s, n, trace: Trace | None = None) -> dict:
    """Σ_k C(r,k)·C(s,n−k) = C(r+s,n) (identidad comprobada sumando)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.vandermonde", "sumar el producto de coeficientes",
                 why="Vandermonde es una identidad contable: la suma directa "
                     "la comprueba")
    r, s, n = int(_Q(r)), int(_Q(s)), int(_Q(n))
    tot = sum(_comb(r, k) * _comb(s, n - k) for k in range(n + 1))
    if tot != _comb(r + s, n):
        raise _error("DISCREPANT", "Vandermonde no cierra")
    trace.verificacion("sen.vandermonde_suma", f"Σ = C({r + s},{n}) = {tot}")
    return {"suma": tot}


# ---------------------------------------------------------------------------
# recurrencias
# ---------------------------------------------------------------------------

def recurrencia_lineal(a, b, c, f0, f1, n, trace: Trace | None = None) -> dict:
    """f_n = a·f_{n−1} + b·f_{n−2} + c, con f_0, f_1: forma cerrada + iteración.

    Forma cerrada por la ecuación característica r² = a·r + b más una solución
    particular de la constante c; la iteración es el segundo camino. Con raíces
    racionales la comprobación es exacta; si no, numérica.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.rec_caracteristica",
                 "característica r² − a·r − b = 0 → solución general + particular "
                 "de la constante → α, β por f₀ y f₁",
                 why="una recurrencia lineal de coeficientes constantes se resuelve "
                     "como una EDO lineal: homogénea por raíces, particular por "
                     "tanteo (§4.12)")
    a, b, c = _Q(a), _Q(b), _Q(c)
    f0, f1 = _Q(f0), _Q(f1)
    n = int(_Q(n))
    if n < 0:
        raise _error("BAD_INPUT", "n ≥ 0")
    if b == 0:
        raise _error("BAD_INPUT", "b = 0: es de primer orden, no de segundo")
    it = [f0, f1]
    for _ in range(max(0, n - 1)):
        it.append(a * it[-1] + b * it[-2] + c)
    # solución particular de la constante c (resonancia si r = 1 es raíz)
    if 1 - a - b != 0:
        cp, fp = c / (1 - a - b), ""
        part = lambda k: cp                                    # noqa: E731
    elif a + 2 * b != 0:
        cp, fp = c / (a + 2 * b), "n"
        part = lambda k: cp * k                                # noqa: E731
    else:
        cp, fp = c / 2, "n²"
        part = lambda k: cp * k * k                            # noqa: E731
    D = a * a + 4 * b
    raiz = _raiz_racional(D)
    exacta = raiz is not None
    if exacta:
        r1, r2 = (a + raiz) / 2, (a - raiz) / 2
    else:
        import cmath
        rr = cmath.sqrt(complex(float(D)))
        r1, r2 = (float(a) + rr) / 2, (float(a) - rr) / 2
    g0, g1 = f0 - part(0), f1 - part(1)
    if D == 0:                                  # raíz doble: (α + β·n)·rⁿ
        al = g0
        be = g1 / r1 - al
        hom = lambda k: (al + be * k) * r1 ** k            # noqa: E731
        pot = "" if r1 == 1 else f"({_fq(r1)})ⁿ"
        terminos = [(al, pot), (be, ("n·" + pot) if pot else "n")]
    else:
        be = (g1 - g0 * r1) / (r2 - r1)
        al = g0 - be
        hom = lambda k: al * r1 ** k + be * r2 ** k        # noqa: E731
        if exacta:
            terminos = [(al, "" if r1 == 1 else f"({_fq(r1)})ⁿ"),
                        (be, "" if r2 == 1 else f"({_fq(r2)})ⁿ")]
        else:
            terminos = []
    if exacta:
        cerrada = _suma_texto(terminos + [(cp, fp)])
    else:
        rad = f"√{_fq(D)}" if D > 0 else f"i·√{_fq(-D)}"
        cerrada = (f"α·r₁ⁿ + β·r₂ⁿ" + (f" + {_fq(cp)}" + (f"·{fp}" if fp else "") if cp else "")
                   + f", con r₁,₂ = ({_fq(a)} ± {rad})/2, α ≈ {_c(al)}, "
                     f"β ≈ {_c(be)}").replace("+ -", "− ")
    trace.regla("sen.rec_cerrada", f"f_n = {cerrada}",
                why="α y β salen de imponer f₀ y f₁ a la solución general")
    # segundo camino: la iteración, término a término
    for k in range(min(n, 60) + 1):
        v = hom(k) + part(k)
        if exacta:
            if v != it[k]:
                raise _error("DISCREPANT", f"forma cerrada ≠ iteración en n = {k}")
        elif abs(complex(v) - float(it[k])) > 1e-6 * max(1.0, abs(float(it[k]))):
            raise _error("DISCREPANT", f"forma cerrada ≠ iteración en n = {k}")
    trace.verificacion("sen.rec_iteracion",
                       f"f_{n} = {it[n]}: la forma cerrada coincide con la iteración "
                       f"en n = 0…{min(n, 60)}")
    vals = (r1, r2) if exacta else None
    return {"f_n": it[n], "raices": vals, "cerrada": cerrada}


def _raiz_racional(q):
    """√q si es racional (q ≥ 0 con numerador y denominador cuadrados); si no, None."""
    if q < 0:
        return None
    rn, rd = math.isqrt(q.numerator), math.isqrt(q.denominator)
    if rn * rn == q.numerator and rd * rd == q.denominator:
        return Fraction(rn, rd)
    return None


def _c(v) -> str:
    v = complex(v)
    return f"{v.real:.6g}" if abs(v.imag) < 1e-12 * max(1.0, abs(v)) else f"{v:.6g}"


def _suma_texto(terminos) -> str:
    """Σ coef·factor sin ceros, sin «1·», sin «+ −» y sin «(1)ⁿ»."""
    partes = []
    for coef, factor in terminos:
        coef = Fraction(coef)
        if coef == 0:
            continue
        mag = _fq(abs(coef))
        cuerpo = mag if not factor else factor if mag == "1" else f"{mag}·{factor}"
        signo = ("−" if coef < 0 else "") if not partes else (" − " if coef < 0 else " + ")
        partes.append(signo + cuerpo)
    return "".join(partes) or "0"


def _fq(q) -> str:
    q = Fraction(q)
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def teorema_maestro(a, b, f_desc: str, trace: Trace | None = None) -> dict:
    """a·T(n/b) + f(n) con f = Θ(n^k·log^j n): teorema maestro extendido.

    ``f_desc``: «1», «n», «n2», «n3», «nlogn» o la forma general «n^k», «n^k*log(n)»,
    «n^k*log(n)^j». La cota se comprueba desarrollando la recurrencia de verdad.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.maestro", "comparar f(n) = n^k·log^j n con n^(log_b a)",
                 why="el árbol de recursión reparte el trabajo entre las hojas "
                     "(n^(log_b a)) y la raíz (f): gana el mayor (§4.12)")
    a, b = int(_Q(a)), int(_Q(b))
    if not (a >= 1 and b > 1):
        raise _error("BAD_INPUT", "a ≥ 1, b > 1")
    forma = _forma_f(f_desc)
    if forma is None:
        trace.aviso("sen.maestro_forma",
                    "f(n) no es de la forma n^k·log^j n: el teorema no aplica")
        raise _no(f"f(n) = {f_desc} no es n^k·log^j n: iteración o característica")
    k, j = forma
    e = math.log(a) / math.log(b)
    trace.regla("sen.maestro_exponente", f"log_{b}({a}) = {e:.6g}; f = n^{_fq(k)}"
                + (f"·log^{j}(n)" if j else ""),
                why="el exponente crítico decide el caso")
    def texto(p, q):
        base = "1" if p == 0 else "n" if p == 1 else f"n^{p:.4g}"
        lg = "" if q == 0 else "·log n" if q == 1 else             "·log" + str(q).translate(str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")) + "n"
        return f"Θ({base}{lg})" if base != "1" or not lg else f"Θ({lg[1:]})"
    if float(k) < e - 1e-12:
        caso, cota = f"caso 1: {texto(e, 0)}", (e, 0)
    elif abs(float(k) - e) <= 1e-12:
        caso, cota = f"caso 2: {texto(e, j + 1)}", (e, j + 1)
    else:
        caso, cota = f"caso 3: {texto(float(k), j)} (regularidad: a/b^k < 1, se cumple)", \
            (float(k), j)
    # segundo camino: desarrollar T(bᵐ) = a·T(bᵐ⁻¹) + f(bᵐ) y ver que T/cota se
    # estabiliza (acotada y sin derivar) — los tres casos lo exigen
    def f(m):
        return b ** (k * m) * (m * math.log(b)) ** j if m else 1.0
    # cuántos niveles caben sin desbordar el float: b^(exponente·M) < 1e250
    M = max(12, min(60, int(250 / (max(float(k), e, 0.5) * math.log10(b)))))
    T, razones = 1.0, {}
    for m in range(1, M + 1):
        T = a * T + f(m)
        g = b ** (cota[0] * m) * (m * math.log(b)) ** cota[1]
        razones[m] = T / g
    r1, r2 = razones[2 * M // 3], razones[M]
    if not (r2 > 0 and 0.5 < r2 / r1 < 2):
        raise _error("DISCREPANT", f"T(n)/cota no se estabiliza: {r1:.4g} → {r2:.4g}")
    trace.verificacion("sen.maestro_desarrollo",
                       f"desarrollando la recurrencia, T(n)/cota = {r1:.4g} → {r2:.4g} "
                       f"(n = {b}^{2 * M // 3} → {b}^{M}): acotada")
    return {"caso": caso}


def _forma_f(f_desc: str):
    """(k, j) con f = n^k·log^j n, o None si no tiene esa forma."""
    import re
    t = str(f_desc).replace(" ", "").replace("·", "*").lower()
    atajos = {"1": "n^0", "n": "n^1", "nlogn": "n^1*log(n)", "n2": "n^2", "n3": "n^3",
              "n^2logn": "n^2*log(n)", "logn": "n^0*log(n)"}
    t = atajos.get(t, t)
    t = re.sub(r"^n(?=\*|$)", "n^1", t)
    m = re.fullmatch(r"n\^([0-9]+(?:/[0-9]+|\.[0-9]+)?)(?:\*?log\(?n\)?(?:\^([0-9]+))?)?", t)
    if m is None:
        return None
    k = Fraction(m.group(1))
    j = 0 if "log" not in t else int(m.group(2) or 1)
    return k, j


def ruina(p, N, trace: Trace | None = None) -> dict:
    """Ruina del jugador: p_k exacta; con p = 1/2, p_k = k/N."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.ruina", "ecuación en diferencias con fronteras p₀ = 0, "
                 "p_N = 1 por la raíz característica",
                 why="pasos independientes con barreras absorbentes: la "
                     "característica la cierra (§4.8)")
    p = _Q(p)
    N = int(_Q(N))
    if not (0 < p < 1 and N >= 1):
        raise _error("BAD_INPUT", "0 < p < 1, N ≥ 1")
    trace.hipotesis("sen.ruina_barreas", "barreras absorbentes en 0 y N", "cumple")
    if p == Fraction(1, 2):
        ps = [Fraction(k, N) for k in range(N + 1)]
        trace.verificacion("sen.ruina_simétrica", "p_k = k/N")
    else:
        q = 1 - p
        r = q / p
        ps = [(1 - r ** k) / (1 - r ** N) for k in range(N + 1)]
    # segundo camino: la recurrencia con los valores
    for k in range(1, N):
        if abs(float(ps[k]) - (float(p) * float(ps[k + 1]) + float(1 - p) * float(ps[k - 1]))) > 1e-9:
            raise _error("DISCREPANT", "no cumple la recurrencia")
    trace.verificacion("sen.ruina_recurre", "p_k = p·p_{k+1} + q·p_{k−1} en todo k")
    return {"p_k": ps}


# ---------------------------------------------------------------------------
# sumatorios y complejidad
# ---------------------------------------------------------------------------

def cerrar_sumatorio(tipo: str, n, trace: Trace | None = None, **kw) -> dict:
    """Cerradas exactas + dominante. Aritmética y cuadrados de 1 a n;
    geométrica de 0 a n (n+1 términos)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.sumatorio", "fórmula cerrada exacta según la progresión",
                 why="contar lleva al sumatorio y cerrarlo da el dominante "
                     "para la cota (§4.8)")
    n = int(_Q(n))
    if n < 0:
        raise _error("BAD_INPUT", "n ≥ 0")
    if tipo == "aritmetica":
        a1, d = _Q(kw.get("a1", 1)), _Q(kw.get("d", 1))
        tot = Fraction(n) * (2 * a1 + (n - 1) * d) / 2
        num = sum(a1 + (k - 1) * d for k in range(1, n + 1))
        dom = "Θ(n²)" if d != 0 else "Θ(n)"
    elif tipo == "geometrica":
        r = _Q(kw.get("r", 2))
        if r == 1:
            tot = Fraction(n + 1)
        else:
            tot = (r ** (n + 1) - 1) / (r - 1)
        num = sum(r ** k for k in range(n + 1))
        dom = f"Θ({r}ⁿ)" if r != 1 else "Θ(n)"
    elif tipo == "cuadrados":
        tot = Fraction(n) * (n + 1) * (2 * n + 1) / 6
        num = sum(Fraction(k * k) for k in range(1, n + 1))
        dom = "Θ(n³)"
    else:
        raise _error("BAD_INPUT", "suma aritmetica, geometrica o cuadrados")
    if num != tot:
        raise _error("DISCREPANT", "la cerrada no suma lo mismo")
    trace.verificacion("sen.sumatorio_suma", f"Σ = {tot} por suma directa")
    return {"suma": tot, "dominante": dom}


# ---------------------------------------------------------------------------
# mochila y cambio (PD exacta frente a voraz y fuerza bruta)
# ---------------------------------------------------------------------------

def mochila(pesos: list, valores: list, cap: int,
            trace: Trace | None = None) -> dict:
    """Mochila 0/1 por PD con tabla; fuerza bruta de 2ᴺ como segundo camino."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mochila", "tabla PD por objetos y capacidad; 2ᴺ por "
                 "fuerza bruta comprueba",
                 why="N pequeño: la fuerza bruta es el oráculo exacto de la PD")
    ws = [int(_Q(w)) for w in pesos]
    vs = [_Q(v) for v in valores]
    cap = int(_Q(cap))
    if not (ws and len(ws) == len(vs) and cap >= 0):
        raise _error("BAD_INPUT", "listas no vacías de igual longitud y cap ≥ 0")
    N = len(ws)
    if N > 20:
        raise _no("N > 20: sin fuerza bruta de 2ᴺ (se dice)")
    dp = [[Fraction(0)] * (cap + 1) for _ in range(N + 1)]
    for i in range(1, N + 1):
        for c in range(cap + 1):
            dp[i][c] = dp[i - 1][c]
            if ws[i - 1] <= c:
                dp[i][c] = max(dp[i][c], dp[i - 1][c - ws[i - 1]] + vs[i - 1])
    mejor = max(sum(vs[i] for i in range(N) if (k >> i) & 1)
                if sum(ws[i] for i in range(N) if (k >> i) & 1) <= cap
                else Fraction(-1) for k in range(2 ** N))
    if dp[N][cap] != mejor:
        raise _error("DISCREPANT", "PD y fuerza bruta difieren")
    trace.verificacion("sen.mochila_fb", f"óptimo {dp[N][cap]} por los dos caminos")
    return {"optimo": dp[N][cap]}


def cambio_monedas(cantidad: int, sistema: list,
                   trace: Trace | None = None) -> dict:
    """Voraz frente a PD: óptimo solo con el sistema del euro (se avisa)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cambio", "voraz (la mayor primero) frente a PD exacta",
                 why="el voraz solo es óptimo con sistemas canónicos como el "
                     "euro: la PD decide (§4.8)")
    C = int(_Q(cantidad))
    S = sorted((int(_Q(m)) for m in sistema), reverse=True)
    if not (C >= 0 and S and S[-1] == 1):
        raise _error("BAD_INPUT", "cantidad ≥ 0 y sistema con moneda 1")
    vor, resto = [], C
    for m in S:
        while resto >= m:
            vor.append(m)
            resto -= m
    INF = 10 ** 18
    dp = [0] + [INF] * C
    for c in range(1, C + 1):
        dp[c] = min(dp[c - m] + 1 for m in S if m <= c)
    trace.hipotesis("sen.cambio_sistema", "sistema declarado: "
                    + ", ".join(str(m) for m in sorted(S)),
                    "óptimo solo si es canónico (euro: sí)")
    # segundo camino: la voraz suma la cantidad y la PD nunca usa más monedas
    if sum(vor) != C or dp[C] > len(vor):
        raise _error("DISCREPANT", "la voraz no suma la cantidad o la PD empeora")
    if dp[C] < len(vor):
        trace.aviso("sen.cambio_no_canonico",
                    f"sistema no canónico: la voraz usa {len(vor)} monedas y el óptimo {dp[C]}")
    trace.verificacion("sen.cambio_pd",
                       f"voraz {len(vor)} monedas; PD {dp[C]} monedas")
    return {"voraz": vor, "optimo_pd": dp[C]}


# ---------------------------------------------------------------------------
# tiempo real (D12, G)
# ---------------------------------------------------------------------------

def _mcm(a: int, b: int) -> int:
    return abs(a * b) // math.gcd(a, b)


def tiempo_real(tareas: list, trace: Trace | None = None) -> dict:
    """U, Liu-Layland (suficiente), RTA por punto fijo e hiperperiodo.

    Tareas [{"C", "T", "D"}] periódicas e independientes, D ≤ T,
    prioridades por tasa (periodo corto = prioritario).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.tiemporeal", "utilización → Liu-Layland (suficiente) → "
                 "si no concluye, RTA exacto por punto fijo",
                 why="Liu-Layland es barato pero no necesario: el RTA decide "
                     "lo que la cota no (§4.8, D12)")
    ts = [{"C": _f(t["C"]), "T": _f(t["T"]), "D": _f(t.get("D", t["T"]))}
          for t in tareas]
    for t in ts:
        if not (t["C"] > 0 and t["T"] > 0 and t["D"] <= t["T"]):
            raise _error("BAD_INPUT", "C, T > 0 y D ≤ T en cada tarea")
    trace.hipotesis("sen.tr_modelo",
                    "periódicas, independientes, D ≤ T, prioridades por tasa",
                    "cumple (la entrada lo declara)")
    n = len(ts)
    U = sum(t["C"] / t["T"] for t in ts)
    cota = n * (2 ** (1 / n) - 1)
    ll = U <= cota
    hp = 1
    for t in ts:
        hp = _mcm(hp, int(t["T"]))
    orden = sorted(range(n), key=lambda i: ts[i]["T"])
    # RTA por punto fijo (solo tareas de mayor prioridad interfieren)
    rtas = {}
    for i in orden:
        R = ts[i]["C"]
        while True:
            Rn = ts[i]["C"] + sum(
                math.ceil(R / ts[j]["T"]) * ts[j]["C"]
                for j in orden if ts[j]["T"] < ts[i]["T"]
                or (ts[j]["T"] == ts[i]["T"] and j < i))
            if Rn <= R:
                break
            R = Rn
            if R > ts[i]["D"] + max(t["C"] for t in ts):
                break
        rtas[i] = Rn
    planificable = all(rtas[i] <= ts[i]["D"] for i in orden)
    # segundo camino: cronograma sobre el hiperperiodo (periodos enteros)
    if hp > 200000:
        trace.aviso("sen.tr_simulacion",
                    f"hiperperiodo {hp}: sin cronograma, solo RTA")
    elif all(float(t.get("C", 0)).is_integer() and float(t.get("T", 0)).is_integer()
             and float(t.get("D", t.get("T", 0))).is_integer() for t in tareas):
        Ci = [int(t["C"]) for t in tareas]
        Ti = [int(t["T"]) for t in tareas]
        Di = [int(t.get("D", t["T"])) for t in tareas]
        rem = [0] * n
        ddl = [0] * n
        miss = False
        for tick in range(hp):
            for i in orden:
                if tick % Ti[i] == 0:
                    if rem[i] > 0:
                        miss = True  # llegó el periodo con trabajo pendiente
                    rem[i] += Ci[i]
                    ddl[i] = tick + Di[i]
            for i in orden:
                if rem[i] > 0:
                    rem[i] -= 1
                    break
            for i in range(n):
                if rem[i] > 0 and tick + 1 > ddl[i]:
                    miss = True
        if miss == planificable:
            raise _error("DISCREPANT", "RTA y cronograma no coinciden")
        trace.verificacion("sen.tr_cronograma",
                           "el cronograma cumple los mismos plazos que el RTA")
    else:
        trace.aviso("sen.tr_simulacion",
                    "periodos no enteros: sin cronograma entero, solo RTA")
    trace.verificacion("sen.tr_rta",
                       f"U = {U:.4g} (cota {cota:.4g}); RTA = "
                       + ", ".join(f"{rtas[i]:.4g}" for i in orden)
                       + f"; hiperperiodo {hp}")
    return {"U": U, "cota_ll": cota, "liu_layland": ll, "rta": rtas,
            "hiperperiodo": hp, "planificable": planificable}
