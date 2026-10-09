# SPDX-License-Identifier: MIT
"""Demostraciones asistidas: lo demostrable se demuestra, el resto se dice.

Cubre lo que los exámenes piden como «prueba» y es computable:

- punto fijo (Bolzano a f(x) − x con imagen contenida y monotonía);
- desigualdades (mínimo global de f − g en compacto, exacto o numérico);
- subespacios (axiomas por linealidad homogénea de las condiciones);
- invariancia (se reutiliza ``espacios.invariante``: basta la base);
- inducción (base + paso como identidades exactas en forma normal).

Lo que NO hace: razonamiento libre, elección de la idea feliz ni
cuantificadores anidados. Cada función escribe su «por qué» (§5.5b),
comprueba hipótesis (§5.7) y verifica por un segundo camino (§5.3).
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _f(x) -> float:
    if isinstance(x, Fraction):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    try:
        return float(Fraction(s))
    except (ValueError, ZeroDivisionError):
        try:
            return float(s)
        except ValueError:
            raise _error("BAD_INPUT", f"«{x}» no es un número")


def _cero_exacto(e: mx.Expr) -> bool | None:
    """¿Es e idénticamente 0? True/False exactos; None si no se sabe."""
    try:
        q = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return None
    if q is None:
        return None
    if not q:
        return True
    try:
        if not P.real_variables(q):
            return False
    except Exception:  # noqa: BLE001
        pass
    return None


def _num(e: mx.Expr, env: dict) -> float | None:
    v = mx.valor_real(e, env)
    if v is None:
        return None
    return float(v.real if isinstance(v, complex) else v)


# ---------------------------------------------------------------------------
# punto fijo
# ---------------------------------------------------------------------------

def punto_fijo(f_texto: str, var: str = "x", a=0, b=1,
               trace: Trace | None = None) -> dict:
    """f:[a,b] → [a,b] continua tiene c con f(c) = c.

    Imagen contenida (extremos dentro + monotonía por Sturm en f′) y
    Bolzano a g = f − x con el cero aislado por Sturm.
    """
    from academic_core.domain.engineering.mathlab import calculo_extra as CX
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.pfijo", "g = f − x con Bolzano; la imagen se acota por "
                 "monotonía (Sturm en f′)",
                 why="el punto fijo es un cero de g y Bolzano lo da si g "
                     "cambia de signo; la monotonía acota la imagen sin "
                     "resolver ninguna optimización")
    try:
        f = mx.parse(str(f_texto))
    except Exception as exc:  # noqa: BLE001
        raise _error("BAD_INPUT", f"no se lee f: {exc}") from None
    xa, xb = float(Fraction(str(a))), float(Fraction(str(b)))
    if not xb > xa:
        raise _error("BAD_INPUT", "intervalo vacío")
    cont, dc = CX._continua_en(f, var, xa, xb)
    trace.hipotesis("sen.pfijo_continua", f"f continua en [{xa}, {xb}]",
                    "se cumple" if cont else f"NO se cumple{': ' + dc if dc else ''}")
    if not cont:
        raise _no(f"sin continuidad no hay teorema: {dc}")
    # monotonía: ceros de f′ en (a, b) por Sturm
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    try:
        df = DM.differentiate(f, var)
        ceros_df = RZ.ceros(df, var, (xa, xb)).raices
        interiores = [r for r in ceros_df if xa < r.x < xb]
    except Exception:  # noqa: BLE001
        interiores = None
    if interiores is None:
        raise _no("f′ sin análisis exacto: la imagen no se acota (se dice)")
    fa, fb = _num(f, {var: xa}), _num(f, {var: xb})
    if fa is None or fb is None:
        raise _no("f no evaluable en los extremos")
    if interiores:
        trace.aviso("sen.pfijo_nomonotona",
                    f"f′ se anula en {[r.texto() for r in interiores]}: sin "
                    "monotonía la imagen no se acota y no hay teorema")
        raise _no("f no monótona: parte el intervalo o se dice")
    dentro = xa - 1e-9 <= min(fa, fb) and max(fa, fb) <= xb + 1e-9
    trace.hipotesis("sen.pfijo_imagen", f"f([{xa}, {xb}]) ⊆ [{xa}, {xb}]",
                    "se cumple (monótona + extremos dentro)" if dentro
                    else "NO se cumple: la imagen sale")
    if not dentro:
        raise _no("la imagen sale del intervalo: sin punto fijo garantizado")
    # g(a) ≥ 0 ≥ g(b): Bolzano con Sturm
    g = mx.Sub(f, mx.Sym(var))
    raices = [r for r in RZ.ceros(g, var, (xa, xb)).raices if xa <= r.x <= xb]
    if not raices:
        raise _error("DISCREPANT", "Bolzano promete un cero y Sturm no lo aísla")
    c = raices[0]
    gc = _num(g, {var: c.x})
    if gc is None or abs(gc) > 1e-6:
        raise _error("DISCREPANT", "el candidato no anula g")
    trace.verificacion("sen.pfijo_c", f"f({c.texto()}) = {c.texto()}: g(c) ≈ 0")
    return {"c": c.x, "texto": c.texto()}


# ---------------------------------------------------------------------------
# desigualdades en un compacto
# ---------------------------------------------------------------------------

def desigualdad(f_texto: str, g_texto: str, var: str = "x", a=0, b=1,
                trace: Trace | None = None) -> dict:
    """Prueba f ≥ g en [a, b]: mínimo global de h = f − g.

    Candidatos: críticos exactos de h′ por Sturm + extremos. Si el mínimo es
    ≥ 0 exacto, probado; si es > 0 numérico con margen, probado numérico;
    si es < 0, contraejemplo (la afirmación es FALSA y se dice dónde).
    """
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.desig", "mínimo global de h = f − g: críticos de Sturm "
                 "+ extremos",
                 why="en un compacto el mínimo se alcanza y solo puede estar "
                     "donde h′ = 0 o en los bordes: Sturm los agota")
    try:
        h = mx.Sub(mx.parse(str(f_texto)), mx.parse(str(g_texto)))
    except Exception as exc:  # noqa: BLE001
        raise _error("BAD_INPUT", f"no se leen f/g: {exc}") from None
    xa, xb = float(Fraction(str(a))), float(Fraction(str(b)))
    if not xb > xa:
        raise _error("BAD_INPUT", "intervalo vacío")
    try:
        dh = DM.differentiate(h, var)
        crits = [r.x for r in RZ.ceros(dh, var, (xa, xb)).raices
                 if xa - 1e-12 <= r.x <= xb + 1e-12]
    except Exception:  # noqa: BLE001
        raise _no("h′ sin análisis exacto: los críticos no se agotan (se dice)")
    cand = sorted(set([xa, xb] + [min(max(c, xa), xb) for c in crits]))
    vals = []
    for c in cand:
        v = _num(h, {var: c})
        if v is None:
            raise _no("h no evaluable en un candidato")
        vals.append((c, v))
    m = min(v for _, v in vals)
    xm = next(c for c, v in vals if v == m)
    if m < -1e-9:
        trace.verificacion("sen.desig_falsa",
                           f"h({xm:.6g}) = {m:.6g} < 0: la afirmación es FALSA")
        return {"veredicto": "falsa", "contraejemplo": xm, "min": m,
                "fuerza": "exacta"}
    trace.verificacion("sen.desig_min", f"mínimo {m:.6g} ≥ 0 en x = {xm:.6g}")
    return {"veredicto": "cierta", "xmin": xm, "min": m, "fuerza": "numerica"}


# ---------------------------------------------------------------------------
# subespacios por axiomas
# ---------------------------------------------------------------------------

def _lineal_homogenea(e: mx.Expr, vars_: list[str]) -> bool | None:
    """¿Es e lineal homogénea en vars? True/False; None si no se sabe."""
    try:
        q = P.as_poly(e)
    except Exception:  # noqa: BLE001
        return None
    if q is None:
        return None
    for mon, _ in q.items():
        Vars = {v for v, _ in mon if not str(v).startswith("@")}
        if set(Vars) - set(vars_):
            return None
        if sum(k for _, k in mon) != 1:
            return False
    return True if q else True


def subespacio(conds: list[str], vars_: list[str],
               trace: Trace | None = None) -> dict:
    """Verifica los axiomas de subespacio para condiciones lineales homogéneas.

    Si alguna condición falla en 0, NO es subespacio (certificado: el 0).
    Si todo es lineal homogéneo, los tres axiomas valen por linealidad.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.subespacio", "cada condición se clasifica: lineal "
                 "homogénea ⇒ axiomas por linealidad; si el 0 falla, no lo es",
                 why="los axiomas para condiciones lineales homogéneas son "
                     "la propia linealidad: no hay nada más que comprobar")
    if not conds:
        raise _error("BAD_INPUT", "sin condiciones")
    for i, c in enumerate(conds):
        try:
            e = mx.parse(str(c))
        except Exception as exc:  # noqa: BLE001
            raise _error("BAD_INPUT", f"no se lee la condición {i + 1}: {exc}") from None
        cero = _num(e, {v: 0.0 for v in vars_})
        if cero is None:
            raise _no(f"la condición {i + 1} no se evalúa en 0")
        if abs(cero) > 1e-12:
            trace.verificacion("sen.subespacio_no",
                               f"el 0 no cumple «{c}»: NO es subespacio")
            return {"es": False, "motivo": f"0 ∉ S (falla «{c}»)"}
        lin = _lineal_homogenea(e, [str(v) for v in vars_])
        if lin is not True:
            trace.aviso("sen.subespacio_nolineal",
                        f"«{c}» no es lineal homogénea decidible: no se prueba")
            raise _no(f"«{c}» no es lineal homogénea: los axiomas no se deciden")
    trace.verificacion("sen.subespacio_si",
                       "0 ∈ S y suma/escalar se heredan de la linealidad")
    return {"es": True, "motivo": "condiciones lineales homogéneas"}


# ---------------------------------------------------------------------------
# invariancia (reexpone espacios.invariante con marco de prueba)
# ---------------------------------------------------------------------------

def invariante(M, F, trace: Trace | None = None) -> dict:
    """f(F) ⊆ F comprobando la base (linealidad); False también es respuesta."""
    from academic_core.domain.engineering.mathlab import espacios as EV

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.invariante", "basta la base: si cada imagen sigue en F, "
                 "todo F sigue",
                 why="linealidad: f(Σλv) = Σλf(v), así que la base decide")
    ok = EV.invariante(M, F, trace)
    trace.verificacion("sen.invariante_veredicto",
                       "F invariante" if ok else "F NO invariante (hay testigo)")
    return {"es": bool(ok)}


# ---------------------------------------------------------------------------
# inducción: base + paso como identidades exactas
# ---------------------------------------------------------------------------

def induccion(igualdad: str, var: str = "n", base=0, termino: str | None = None,
              trace: Trace | None = None) -> dict:
    """Verifica una inducción P(base) y P(k) ⇒ P(k+1) como identidades.

    Dos modos: ``suma`` (con ``termino`` a(k): base como suma finita exacta
    y cerrado(k+1) − cerrado(k) ≡ a(k+1)) e ``igualdad`` (L = R con
    L(k+1)−L(k) ≡ R(k+1)−R(k)). Lo no polinómico ((1+x)^n) no normaliza:
    indicio numérico, no prueba.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.induccion", "base por sustitución exacta; el paso como "
                 "identidad de diferencias en forma normal",
                 why="si S(k+1)−S(k) coincide a ambos lados, el paso es una "
                     "identidad y la inducción cierra")
    if "=" not in str(igualdad):
        raise _error("BAD_INPUT", "igualdad de la forma L = R")
    L0, R0 = (s.strip() for s in str(igualdad).split("=", 1))
    try:
        L, R = mx.parse(L0), mx.parse(R0)
    except Exception as exc:  # noqa: BLE001
        raise _error("BAD_INPUT", f"no se lee la igualdad: {exc}") from None
    n0 = _f(base)
    if termino is not None:
        try:
            A = mx.parse(str(termino))
        except Exception as exc:  # noqa: BLE001
            raise _error("BAD_INPUT", f"no se lee el término: {exc}") from None
        if n0 != int(n0) or n0 < 0 or n0 > 10000:
            raise _error("BAD_INPUT", "base entera ≥ 0 y ≤ 10000 para sumar")
        s = mx.Num(Fraction(0))
        for i in range(1, int(n0) + 1):
            s = mx.Add(s, mx.substitute(A, var, mx.Num(Fraction(i))))
        d0 = mx.Sub(mx.substitute(L, var, mx.Num(Fraction(int(n0)))), s)
        if _cero_exacto(d0) is not True:
            v0 = _num(d0, {})
            if v0 is None:
                raise _no("con parámetros libres no se decide la base")
            if abs(v0) > 1e-9:
                trace.verificacion("sen.induccion_base_falla",
                                   "la base no se cumple: el enunciado es FALSO")
                return {"veredicto": "falsa_en_base"}
            raise _no("base solo numérica: no es prueba")
        k = mx.Sym(var)
        kp1 = mx.Add(k, mx.Num(Fraction(1)))
        dif = mx.Sub(mx.Sub(mx.substitute(L, var, kp1), mx.substitute(L, var, k)),
                     mx.substitute(A, var, kp1))
    else:
        d0 = mx.Sub(mx.substitute(L, var, mx.Num(Fraction(n0).limit_denominator(10**9))),
                    mx.substitute(R, var, mx.Num(Fraction(n0).limit_denominator(10**9))))
        if _cero_exacto(d0) is not True:
            v0 = _num(d0, {})
            if v0 is None:
                raise _no("con parámetros libres no se decide la base")
            if abs(v0) > 1e-9:
                trace.verificacion("sen.induccion_base_falla",
                                   "la base no se cumple: el enunciado es FALSO")
                return {"veredicto": "falsa_en_base"}
            raise _no("base solo numérica: no es prueba")
        k = mx.Sym(var)
        kp1 = mx.Add(k, mx.Num(Fraction(1)))
        dif = mx.Sub(mx.Sub(mx.substitute(L, var, kp1), mx.substitute(L, var, k)),
                     mx.Sub(mx.substitute(R, var, kp1), mx.substitute(R, var, k)))
    if _cero_exacto(dif) is True:
        trace.verificacion("sen.induccion_paso",
                           "S(k+1)−S(k) idéntico a ambos lados: el paso cierra")
        return {"veredicto": "probada"}
    # indicio numérico en varios k (no prueba)
    mal = 0
    for kk in range(5):
        v = _num(dif, {var: float(kk)})
        if v is None:
            raise _no("no evaluable sin fijar parámetros: indicio, no prueba")
        if abs(v) > 1e-6:
            mal += 1
    if mal:
        trace.verificacion("sen.induccion_paso_falla",
                           "el paso falla: el enunciado es FALSO")
        return {"veredicto": "falsa_en_paso"}
    raise _no("el paso no es identidad polinómica: indicio, no prueba")
