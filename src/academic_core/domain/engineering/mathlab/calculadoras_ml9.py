# SPDX-License-Identifier: MIT
"""ML-9: las calculadoras de probabilidad y estadística (§8.2 G), registradas en el
contrato §5.9.

Cada una devuelve pasos, hipótesis, convenciones declaradas, una gráfica como datos
y un sello. Si el segundo camino del dominio no coincide (``DISCREPANT``), el
resultado **no se lanza como error**: se devuelve con el sello «discrepa» y el
motivo, para que el consumidor no pueda presentarlo como correcto (§5.3).

Operaciones: ``probabilidad``, ``variable_aleatoria``, ``vector_aleatorio``,
``aproximacion_normal``, ``estadistica``, ``intervalo_confianza``, ``contraste``,
``regresion``, ``estimador``, ``proceso``, ``tabla_estadistica``,
``comunicaciones`` y ``montecarlo``.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import probabilidad as P
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.calculators import _finalizar, con_discrepancia
from academic_core.domain.engineering.mathlab.trace import Trace


def _dict(peticion: C.Peticion, que: str) -> dict:
    e = peticion.entrada
    if not isinstance(e, dict):
        raise C.error("BAD_INPUT", f"se espera un diccionario para «{que}»")
    return e


def _ok(peticion, trace, exacto, metodo, detalle="", aproximado=None, grafica=None, avisos=()):
    return _finalizar(peticion, trace, exacto, aproximado=aproximado,
                      sello=V.Seal(V.VERIFIED, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


def _numerico(peticion, trace, exacto, metodo, detalle="", aproximado=None, grafica=None,
              avisos=()):
    return _finalizar(peticion, trace, exacto, aproximado=aproximado,
                      sello=V.Seal(V.NUMERIC_ONLY, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


def _serie(nombre, f, a, b, n=240) -> C.Serie:
    xs, ys, cortes = [], [], []
    for i in range(n + 1):
        x = a + (b - a) * i / n
        try:
            y = f(x)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            y = None
        if y is None or not math.isfinite(y) or abs(y) > 1e12:
            if xs and (not cortes or cortes[-1] != len(xs)):
                cortes.append(len(xs))
            continue
        xs.append(x)
        ys.append(float(y))
    return C.Serie(nombre, tuple(xs), tuple(ys), tuple(cortes))


def _grafica(series, xl, yl, desc):
    series = tuple(s for s in series if s.ys)
    return C.Graph(series=series, x_label=xl, y_label=yl, description=desc) if series else None


def _ventana(d: P.Distribucion) -> tuple[float, float]:
    lo, hi = d.soporte
    a = lo if math.isfinite(lo) else d.cuantil(0.0005)
    b = hi if math.isfinite(hi) else d.cuantil(0.9995)
    if d.discreta:
        b = min(b, a + 80)
    return a, b


# ---------------------------------------------------------------------------
# probabilidad básica
# ---------------------------------------------------------------------------


@_con_discrepancia
def _probabilidad(peticion: C.Peticion) -> C.Resultado:
    """``{"calculo": "bayes", "previas": {...}, "verosimilitudes": {...}, "evidencia": "D"}``,
    ``{"calculo": "combinatoria", "tipo": "combinaciones", "n": 5, "k": 2}`` o
    ``{"calculo": "inclusion_exclusion", "datos": {"A": ..., "AB": ...}}``."""
    from academic_core.domain.engineering.mathlab import prob_basica as B

    e = _dict(peticion, "probabilidad")
    calculo = str(e.get("calculo", "bayes"))
    trace = Trace()
    if calculo == "bayes":
        r = B.bayes(e["previas"], e["verosimilitudes"], str(e.get("evidencia", "B")), trace,
                    peticion.semilla)
        arbol = r.arbol()
        trace.regla("bayes.arbol", "árbol: " + "; ".join(
            f"{n['padre']} → {n['etiqueta']} ({n['p']})" for n in arbol if n["padre"]))
        exacto = {"P(" + r.evidencia + ")": str(r.total),
                  **{f"P({h} | {r.evidencia})": str(q) for h, q in zip(r.hipotesis, r.posteriores)}}
        return _ok(peticion, trace, exacto, "probabilidad total exacta, complementario y "
                   "simulación sembrada del árbol", r.texto(), aproximado=float(r.total))
    if calculo == "combinatoria":
        k = e.get("k")
        r = B.combinatoria(str(e["tipo"]), int(e["n"]), None if k is None else int(k), trace,
                           grupos=e.get("grupos"))
        metodo = "fórmula y enumeración directa" if r.enumerado is not None else "fórmula"
        sello = V.VERIFIED if r.enumerado is not None else V.NUMERIC_ONLY
        return _finalizar(peticion, trace, str(r.valor), sello=V.Seal(sello, metodo, r.formula),
                          avisos=() if r.enumerado is not None else
                          ("sin segundo camino: espacio demasiado grande para enumerar",))
    if calculo == "inclusion_exclusion":
        r = B.inclusion_exclusion(e["datos"], trace)
        exacto = {"P(unión)": str(r["union"]), "P(ninguno)": str(r["ninguno"]),
                  **{f"solo {k}": str(v) for k, v in r["regiones"].items()}}
        for k, (si, prod) in r["independencia"].items():
            trace.regla("ie.independencia", f"{'∩'.join(k)}: P = {e['datos'][k]} "
                                            f"{'=' if si else '≠'} producto {prod}")
        return _ok(peticion, trace, exacto, "regiones de Venn exactas", str(r["union"]))
    raise C.error("BAD_INPUT", f"cálculo desconocido «{calculo}»")


# ---------------------------------------------------------------------------
# variable aleatoria: leyes con nombre y densidades por tramos
# ---------------------------------------------------------------------------


@_con_discrepancia
def _variable_aleatoria(peticion: C.Peticion) -> C.Resultado:
    """``{"dist": "binomial", "parametros": {"n": 10, "p": "0.3"}, "suceso": "P(X<=3)"}``
    (también ``"cuantil": 0.95`` o solo los momentos) o ``{"densidad": [["k*x^2", "0",
    "1"]], "calculo": "momentos"|"F"|"probabilidad"|"chebyshov"|"transformacion"|
    "maximo"|"convolucion", ...}``."""
    e = _dict(peticion, "variable_aleatoria")
    if "densidad" in e:
        return _densidad(peticion, e)
    trace = Trace()
    _dist = str(e["dist"])
    trace.metodo("variable_aleatoria.ley",
                 f"se construye la {_dist} y se calcula sobre su función de "
                 "distribución",
                 why="todo lo que se pide (sucesos, cuantiles, momentos) sale "
                     "de la ley: la probabilidad es un área bajo f o una suma "
                     "de la tabla, y el cuantil es donde esa área acumulada "
                     "llega al nivel pedido; fijar la ley primero es lo que "
                     "permite además contrastarla por simulación")
    d = P.distribucion(_dist, dict(e.get("parametros", {})), trace)
    trace.regla("dist.ley", f"X ~ {d.titulo()}: {d.formula}")
    mu, var = d.media_f(), d.varianza_f()
    num = P.momentos_numericos(d)
    if mu is not None and var is not None:
        if abs(float(mu) - num[0]) > 1e-6 * max(1, abs(num[0])) or \
                abs(float(var) - num[1]) > 1e-6 * max(1, abs(num[1])):
            raise C.error("DISCREPANT", f"momentos {mu}, {var} frente a {num}")
        trace.regla("dist.momentos", f"E[X] = {_t(mu)}, Var X = {_t(var)}")
        trace.verificacion("dist.momentos_num", f"sumando/integrando la "
                                                f"{'probabilidad' if d.discreta else 'densidad'}"
                                                f": E[X] ≈ {num[0]:.10g}, Var X ≈ {num[1]:.10g}")
    a, b = _ventana(d)
    exacto: dict = {"ley": d.titulo()}
    if mu is not None:
        exacto["E[X]"] = _t(mu)
    if var is not None:
        exacto["Var X"] = _t(var)
    aproximado = None
    sombra = None
    if e.get("suceso"):
        A, Bc = P.lee_suceso(str(e["suceso"]))
        I = A if Bc is None else A.interseca(Bc)
        valor, ex = P.probabilidad_intervalo(d, I)
        if Bc is not None:
            vb, eb = P.probabilidad_intervalo(d, Bc)
            if vb == 0:
                raise C.error("BAD_INPUT", "se condiciona a un suceso de probabilidad 0")
            valor = valor / vb
            ex = _cociente(ex, eb)
            trace.regla("dist.condicionada", f"P({A.texto()} | {Bc.texto()}) = "
                                             f"P({I.texto()})/P({Bc.texto()})",
                        why="definición de probabilidad condicionada")
        trace.regla("dist.suceso", f"P({I.texto()}) = {d.formula_F or d.formula}"
                    + (f" = {P.texto_exacto(ex)}" if ex is not None else "") + f" ≈ {valor:.10g}")
        _segundo_camino_suceso(d, I, Bc, valor, trace, peticion.semilla)
        texto = P.texto_exacto(ex) if ex is not None and len(P.texto_exacto(ex)) < 90 else None
        if texto is None and d.tabla and Bc is None and _forma_tabla(d, I):
            texto = f"{_forma_tabla(d, I)} ≈ {valor:.10g}"
        exacto[e["suceso"]] = texto or f"{valor:.10g}"
        aproximado = valor
        if not d.discreta:
            lo_s = a if I.lo is None else max(a, float(I.lo))
            hi_s = b if I.hi is None else min(b, float(I.hi))
            sombra = _serie("área sombreada", d.densidad, lo_s, hi_s, 120)
    if e.get("cuantil") is not None:
        p = P.fraccion(e["cuantil"], "p")
        q = d.cuantil(float(p))
        exacto[f"x_{p}"] = f"{q:.10g}"
        if d.discreta:
            qe = d.cuantil_exacto(p)
            if qe is not None and qe != q:
                raise C.error("DISCREPANT", f"cuantil {q} frente al exacto {qe}")
            trace.regla("dist.cuantil", f"el menor k con F(k) ≥ {p} es {int(q)}")
        else:
            Fq = P.F_por_cuadratura(d, q)
            if abs(Fq - float(p)) > 1e-7:
                raise C.error("DISCREPANT", f"F(cuantil) = {Fq}")
            trace.regla("dist.cuantil", f"F(x) = {p} ⇒ x = {q:.10g}"
                        + (f" (tabla: {P.redondeo_tabla(q, 3)})" if d.tabla else ""))
            trace.verificacion("dist.cuantil_cuadratura", f"F({q:.8g}) = {Fq:.10f} por "
                                                          "cuadratura de la densidad")
        aproximado = q if aproximado is None else aproximado
    series = [_serie("P(X = k)" if d.discreta else "f(x)", d.densidad, a, b,
                     int(b - a) if d.discreta else 240),
              _serie("F(x)", d.F, a, b, 240)]
    if sombra is not None:
        series.append(sombra)
    grafica = _grafica(series, "x", "f, F", f"{'probabilidad' if d.discreta else 'densidad'} y "
                       f"distribución acumulada de {d.titulo()}"
                       + ("; el área sombreada es la probabilidad pedida" if sombra else ""))
    return _ok(peticion, trace, exacto, "F cerrada frente a la cuadratura de la densidad (o la "
               "suma término a término) y simulación sembrada constructiva", d.titulo(),
               aproximado=aproximado, grafica=grafica)


def _t(v) -> str:
    if isinstance(v, Fraction):
        return str(v)
    if isinstance(v, float):
        return f"{v:.10g}"
    return P.texto_exacto(v) if isinstance(v, mx.Expr) else str(v)


def _cociente(a, b):
    if isinstance(a, Fraction) and isinstance(b, Fraction) and b:
        return a / b
    if a is None or b is None:
        return None
    ea = mx.num(a) if isinstance(a, Fraction) else a
    eb = mx.num(b) if isinstance(b, Fraction) else b
    from academic_core.domain.engineering.mathlab import va_continua as VC

    if isinstance(eb, mx.Call) and eb.name == "exp":
        # e^a/e^b = e^(a − b): la falta de memoria de la exponencial queda a la vista
        return VC.simplifica(VC.combina_exp(mx.Mul(ea, mx.Call("exp", (mx.Neg(eb.args[0]),)))))
    return VC.simplifica(mx.Div(ea, eb))


def _forma_tabla(d: P.Distribucion, I: P.Intervalo) -> str:
    if d.nombre != "normal":
        return ""
    mu, s = float(d.parametros["μ"]), math.sqrt(float(d.parametros["σ²"]))
    partes = []
    if I.hi is not None:
        partes.append(f"Φ({(float(I.hi) - mu) / s:.6g})")
    else:
        partes.append("1")
    if I.lo is not None:
        partes.append(f"Φ({(float(I.lo) - mu) / s:.6g})")
    return " − ".join(partes)


def _segundo_camino_suceso(d, I, B, valor, trace, semilla):
    if d.discreta:
        lo = int(max(d.soporte[0], -1e9))
        total = 0.0
        k = lo
        en_b = 0.0
        while k <= d.soporte[1] and k < lo + 400000:
            p = d.densidad(k)
            if P.en_intervalo(I, k):
                total += p
            if B is not None and P.en_intervalo(B, k):
                en_b += p
            if k > lo + 50 and p < 1e-18 and k > (float(d.media_f() or 0) + 50):
                break
            k += 1
        directo = total / en_b if B is not None else total
        if abs(directo - valor) > 1e-9:
            raise C.error("DISCREPANT", f"suma término a término {directo} frente a {valor}")
        trace.verificacion("dist.suma", f"sumando P(X = k) término a término: {directo:.12g}")
    else:
        a = None if I.lo is None else float(I.lo)
        b = None if I.hi is None else float(I.hi)
        Fb = 1.0 if b is None else P.F_por_cuadratura(d, b)
        Fa = 0.0 if a is None else P.F_por_cuadratura(d, a)
        directo = Fb - Fa
        if B is not None:
            Bb = 1.0 if B.hi is None else P.F_por_cuadratura(d, float(B.hi))
            Ba = 0.0 if B.lo is None else P.F_por_cuadratura(d, float(B.lo))
            directo /= (Bb - Ba)
        if abs(directo - valor) > 1e-7:
            raise C.error("DISCREPANT", f"cuadratura {directo} frente a {valor}")
        trace.verificacion("dist.cuadratura", f"cuadratura tanh-sinh de la densidad: "
                                              f"{directo:.12g}")

    def ind(g):
        if B is None:
            return 1.0 if P.en_intervalo(I, d.muestra(g)) else 0.0
        for _ in range(100000):
            x = d.muestra(g)
            if P.en_intervalo(B, x):
                return 1.0 if P.en_intervalo(I, x) else 0.0
        raise C.error("BAD_INPUT", "el suceso condicionante casi nunca ocurre al simular")
    muestras = d.muestras_asequibles(20000)
    if B is not None:
        pb = P.probabilidad_intervalo(d, B)[0]
        if pb < 0.05:
            muestras = int(muestras * pb * 20)
    if muestras < 1000:
        trace.aviso("dist.sin_simulacion", "la simulación sería demasiado larga con estos "
                                           "parámetros: solo el segundo camino determinista")
        return
    sim = P.simula(ind, muestras, semilla)
    if not sim.dentro(valor, 5):
        raise C.error("DISCREPANT", f"simulación {sim.texto()} frente a {valor}")
    trace.verificacion("dist.simulacion", f"simulación sembrada (mecanismo constructivo de la "
                                          f"ley): {sim.texto()}")


def _densidad(peticion: C.Peticion, e: dict) -> C.Resultado:
    from academic_core.domain.engineering.mathlab import va_continua as VC

    trace = Trace()
    var = str(e.get("var", "x"))
    _calc = str(e.get("calculo", "momentos"))
    trace.metodo("variable_aleatoria.densidad",
                 f"se lee la densidad por {var} tramos y se calcula «{_calc}» "
                 "integrando sobre ella",
                 why="con la densidad a mano, cualquier probabilidad es un "
                     "área y cualquier momento un integral contra xⁿ: por eso "
                     "todas las preguntas salen del mismo sitio, y por eso "
                     "los tramos se integran de forma exacta cuando el "
                     "polinomio lo permite")
    d = VC.lee_densidad(e["densidad"], var, e.get("constante"), trace)
    calculo = _calc
    exacto: dict = {}
    if d.constante:
        exacto[d.constante] = mx.text(d.valor_constante)
    a, b = d.soporte()
    va = a if math.isfinite(a) else -6.0
    vb = b if math.isfinite(b) else va + 8.0
    series = [_serie(f"f({var})", d.f, va - 0.5, vb + 0.5)]
    aproximado = None
    if calculo in ("momentos", "chebyshov"):
        m = VC.momentos(d, trace)
        exacto.update({"E[X]": mx.text(m.media), "E[X²]": mx.text(m.m2),
                       "Var X": mx.text(m.varianza)})
        aproximado = float(mx.valor_real(m.media, {}))
        if calculo == "chebyshov":
            k = P.fraccion(e.get("k", 2), "k")
            c = VC.chebyshov(d, m, k, trace)
            exacto["cota de Chebyshov"] = str(c["cota"])
            exacto["P(|X − μ| ≥ kσ)"] = f"{c['exacta']:.10g}"
    elif calculo == "F":
        piezas = VC.F_por_tramos(d, trace)
        exacto["F"] = "; ".join(f"{mx.text(F)} en [{'−∞' if lo is None else lo}, "
                                f"{'+∞' if hi is None else hi}]" for lo, hi, F in piezas)
        series.append(_serie(f"F({var})", lambda x: VC.F_num(d, x), va - 0.5, vb + 0.5, 120))
    elif calculo == "probabilidad":
        A, Bc = P.lee_suceso(str(e["suceso"]))
        I = A if Bc is None else A.interseca(Bc)
        valor, num = VC.probabilidad(d, I, trace)
        if Bc is not None:
            vb_, nb = VC.probabilidad(d, Bc, trace)
            valor = None if valor is None or vb_ is None else VC.simplifica(mx.Div(valor, vb_))
            num = num / nb
        exacto[str(e["suceso"])] = mx.text(valor) if valor is not None else f"{num:.10g}"
        aproximado = num
    elif calculo == "transformacion":
        g = mx.parse(str(e["g"]))
        T = VC.transforma(d, g, trace, peticion.semilla)
        exacto["f_Y"] = "; ".join(f"{mx.text(f)} en [{VC._fy(lo)}, {VC._fy(hi)}]"
                                  for lo, hi, f in T.tramos)
        ya = T.tramos[0][0] if math.isfinite(T.tramos[0][0]) else -6.0
        yb = T.tramos[-1][1] if math.isfinite(T.tramos[-1][1]) else ya + 8.0
        series = [_serie("f_Y(y)", T.f, ya, yb)]
    elif calculo in ("maximo", "minimo"):
        n = int(e.get("n", 2))
        r = VC.maximo_minimo(d, n, trace)
        clave = "max" if calculo == "maximo" else "min"
        exacto[f"F_{clave}"] = "; ".join(f"{mx.text(F)} en [{'−∞' if lo is None else lo}, "
                                         f"{'+∞' if hi is None else hi}]" for lo, hi, F in r[clave])
    elif calculo == "convolucion":
        d2 = VC.lee_densidad(e["densidad2"], str(e.get("var2", var)), e.get("constante2"), trace)
        r = VC.convolucion(d, d2, trace)
        exacto["f_Z"] = "; ".join(f"{mx.text(f)} en [{'−∞' if lo is None else lo}, "
                                  f"{'+∞' if hi is None else hi}]" for lo, hi, f in r)

        def fz(zv):
            for lo, hi, f in r:
                if (lo is None or zv >= lo) and (hi is None or zv <= hi):
                    v = mx.valor_real(f, {"z": zv})
                    return 0.0 if v is None else float(v)
            return 0.0
        lo0 = r[0][0] if r[0][0] is not None else -6
        hi0 = r[-1][1] if r[-1][1] is not None else float(lo0) + 8
        series = [_serie("f_Z(z)", fz, float(lo0) - 0.5, float(hi0) + 0.5)]
    else:
        raise C.error("BAD_INPUT", f"cálculo desconocido «{calculo}»")
    grafica = _grafica(series, var, "densidad", "la densidad (y lo que se pide) por tramos")
    return _ok(peticion, trace, exacto, "integración exacta (primitiva comprobada derivando) y "
               "cuadratura independiente", "", aproximado=aproximado, grafica=grafica)


# ---------------------------------------------------------------------------
# vectores aleatorios
# ---------------------------------------------------------------------------


@_con_discrepancia
def _vector_aleatorio(peticion: C.Peticion) -> C.Resultado:
    """``{"calculo": "tabla", "x": [...], "y": [...], "p": [[...]]}``,
    ``{"calculo": "gauss_lineal", "mu": [...], "cov": [[...]], "A": [[...]], "b": [...]}``
    o ``{"calculo": "gauss_condicional", "mu": ..., "cov": ..., "observadas": {"3": 2}}``."""
    from academic_core.domain.engineering.mathlab import prob_basica as B

    e = _dict(peticion, "vector_aleatorio")
    calculo = str(e.get("calculo", "tabla"))
    trace = Trace()
    if calculo == "tabla":
        c = B.tabla_conjunta(e["x"], e["y"], e["p"], trace)
        exacto = {"p_X": [str(v) for v in c.px], "p_Y": [str(v) for v in c.py],
                  "E[X]": str(c.EX), "E[Y]": str(c.EY), "Var X": str(c.VX), "Var Y": str(c.VY),
                  "Cov": str(c.cov), "ρ²": str(c.rho2), "ρ": f"{c.rho():.10g}",
                  "independientes": "sí" if c.independientes else "no",
                  "E[Y|X]": [str(v) for v in c.condicionada]}
        if c.recta:
            exacto["Ŷ"] = f"{c.recta[0]} + {c.recta[1]}·X"
        return _ok(peticion, trace, exacto, "covarianza por dos fórmulas y ortogonalidad del "
                   "error, exactas", "")
    if calculo == "gauss_lineal":
        r = B.gaussiano_lineal(e["mu"], e["cov"], e["A"], e.get("b"), trace)
        exacto = {"μ_Y": [str(v) for v in r["media"]],
                  "Σ_Y": [[str(v) for v in f] for f in r["cov"]]}
        grafica = None
        if len(r["media"]) == 2:
            f = B.densidad_gaussiana_2d(r["media"], r["cov"])
            s1 = math.sqrt(float(r["cov"][0][0]))
            m1, m2 = float(r["media"][0]), float(r["media"][1])
            grafica = _grafica([_serie(f"f(y₁, {m2:g})", lambda y: f(y, m2), m1 - 3 * s1,
                                       m1 + 3 * s1)], "y₁", "densidad",
                               "corte de la densidad conjunta de Y por y₂ = μ₂")
        return _ok(peticion, trace, exacto, "AΣAᵀ por elementos (exacto)", "", grafica=grafica)
    if calculo == "gauss_condicional":
        r = B.gaussiano_condicional(e["mu"], e["cov"], {str(k): v for k, v in e["observadas"].items()},
                                    trace)
        exacto = {"índices": r["indices"], "media": [str(v) for v in r["media"]],
                  "cov": [[str(v) for v in f] for f in r["cov"]]}
        return _ok(peticion, trace, exacto, "ortogonalidad del error (exacta)", "")
    raise C.error("BAD_INPUT", f"cálculo desconocido «{calculo}»")


@_con_discrepancia
def _aproximacion_normal(peticion: C.Peticion) -> C.Resultado:
    """``{"dist": "binomial", "parametros": {"n": 100, "p": "0.3"}, "suceso": "P(X<=35)"}``
    o ``{"tcl": {"n": 50, "media": 2, "varianza": 4}, "suceso": "P(X<=110)"}``."""
    from academic_core.domain.engineering.mathlab import procesos as PR

    e = _dict(peticion, "aproximacion_normal")
    trace = Trace()
    if "tcl" in e:
        t = e["tcl"]
        r = PR.tcl_suma(int(t["n"]), t["media"], t["varianza"], str(e["suceso"]), trace)
        trace.aviso("tcl.sin_exacta", "sin la ley de cada sumando no hay valor exacto con el que "
                                      "comparar: el resultado es una aproximación")
        return _numerico(peticion, trace, None, "teorema central del límite",
                         f"S ≈ N({r['media']:.6g}, {r['varianza']:.6g})", aproximado=r["p"],
                         avisos=("aproximación por el TCL",))
    r = PR.aproximacion_normal(str(e["dist"]), dict(e.get("parametros", {})), str(e["suceso"]),
                               trace)
    exacto = {"exacta": r.exacta_txt if r.exacta_txt and len(r.exacta_txt) < 90
              else f"{r.exacta:.10g}",
              "normal (con corrección)": f"{r.aproximada:.10g}",
              "normal (sin corrección)": f"{r.sin_correccion:.10g}",
              "error de la aproximación": f"{abs(r.aproximada - r.exacta):.3g}"}
    return _ok(peticion, trace, exacto, "valor exacto al lado de la aproximación", r.texto(),
               aproximado=r.aproximada)


# ---------------------------------------------------------------------------
# estadística
# ---------------------------------------------------------------------------


@_con_discrepancia
def _estadistica(peticion: C.Peticion) -> C.Resultado:
    """``{"datos": [2, 4, 4, 5, ...]}`` (o el texto con los datos)."""
    from academic_core.domain.engineering.mathlab import estadistica as E

    e = peticion.entrada
    datos = e.get("datos") if isinstance(e, dict) else e
    if not isinstance(datos, (list, tuple)):
        raise C.error("BAD_INPUT",
                      f"«estadistica» necesita una lista de datos; se "
                      f"recibió {type(datos).__name__}")
    trace = Trace()
    trace.metodo("estadistica.descriptiva",
                 "mediana y cuartiles por posición, y dispersión con el "
                 "divisor que se declara",
                 why="la media y la mediana no dicen lo mismo cuando hay "
                     "valores extremos: por eso se calculan las dos. Y la "
                     "varianza aparece con divisor n y con n − 1 porque dan "
                     "valores distintos, y cada una es la correcta según el "
                     "uso que se vaya a hacer")
    d = E.descriptiva(datos, trace)
    exacto = {"n": d.n, "media": str(d.media), "mediana": str(d.mediana),
              "moda": [str(m) for m in d.modas], "Q1": str(d.q1), "Q3": str(d.q3),
              "varianza (n)": str(d.var_n),
              "cuasivarianza (n − 1)": None if d.var_n1 is None else str(d.var_n1),
              "atípicos": [str(a) for a in d.atipicos]}
    xs, ys = [], []
    for lo, hi, c in d.histograma:
        xs += [lo, lo, hi, hi]
        ys += [0, c, c, 0]
    caja = C.Serie("caja", (float(d.bigotes[0]), float(d.q1), float(d.mediana), float(d.q3),
                            float(d.bigotes[1])), (0.5, 0.5, 0.5, 0.5, 0.5))
    grafica = C.Graph(series=(C.Serie("histograma", tuple(xs), tuple(ys)), caja), x_label="x",
                      y_label="frecuencia",
                      description=f"histograma ({len(d.histograma)} clases, Sturges) y diagrama "
                                  f"de caja: bigotes {d.bigotes[0]}–{d.bigotes[1]}, caja "
                                  f"{d.q1}–{d.q3}, mediana {d.mediana}")
    return _ok(peticion, trace, exacto, "Σ(x − x̄)² = Σx² − n·x̄² y recuento de la mediana "
               "(exactos)", d.texto(), grafica=grafica)


@_con_discrepancia
def _intervalo_confianza(peticion: C.Peticion) -> C.Resultado:
    """``{"parametro": "media", "n": 20, "media": "10.2", "s": "1.5", "nivel": "0.95"}`` y
    variantes (``sigma``, ``datos``, varianza, proporcion, dif_medias, dif_proporciones,
    tamano_media, tamano_proporcion)."""
    from academic_core.domain.engineering.mathlab import estadistica as E

    e = _dict(peticion, "intervalo_confianza")
    trace = Trace()
    I = E.intervalo(e, trace, peticion.semilla)
    exacto: dict = {"intervalo": [f"{I.lo:.10g}", f"{I.hi:.10g}"] if I.lo != I.hi else I.exacto,
                    "estimación": f"{I.estimacion:.10g}"}
    for k, v in I.cuantiles.items():
        exacto[k] = f"{v:.10g}" if isinstance(v, float) else str(v)
    exacto.update({k: (list(v) if isinstance(v, tuple) else v) for k, v in I.extra.items()})
    if I.cobertura is not None:
        trace.verificacion("ic.cobertura", f"cobertura del método en {I.cobertura.muestras} "
                                           f"muestras simuladas: {I.cobertura.texto()} (nominal "
                                           f"{float(I.nivel):g})")
    grafica = None
    if I.lo != I.hi:
        grafica = _grafica([C.Serie("intervalo", (I.lo, I.estimacion, I.hi), (0.0, 0.0, 0.0))],
                           "valor", "", f"{I.texto()}; el punto central es la estimación")
    metodo = "cuantil comprobado por cuadratura" + (" y cobertura simulada del método"
                                                    if I.cobertura is not None else "")
    return _ok(peticion, trace, exacto, metodo, I.texto(), grafica=grafica)


@_con_discrepancia
def _contraste(peticion: C.Peticion) -> C.Resultado:
    """``{"tipo": "media", "n": 25, "media": 52, "s": 5, "mu0": 50, "alternativa": "mayor"}``;
    tipos: media, proporcion, varianza, bondad, independencia."""
    from academic_core.domain.engineering.mathlab import estadistica as E

    e = _dict(peticion, "contraste")
    trace = Trace()
    c = E.contraste(e, trace)
    exacto = {"hipótesis": c.nombre, "estadístico": f"{c.estadistico:.10g}", "ley": c.ley,
              "p-valor": f"{c.p_valor:.10g}", "región crítica": [f"{v:.6g}" for v in c.critico],
              "decisión": "se rechaza H₀" if c.rechaza else "no se rechaza H₀"}
    exacto.update(c.detalle)
    return _ok(peticion, trace, exacto, "p-valor por la función especial y por cuadratura; "
               "región crítica coherente", c.texto(), aproximado=c.p_valor,
               avisos=("los contrastes no aparecen en los exámenes leídos (§15.3)",))


@_con_discrepancia
def _regresion(peticion: C.Peticion) -> C.Resultado:
    """``{"x": [...], "y": [...]}``."""
    from academic_core.domain.engineering.mathlab import estadistica as E

    e = _dict(peticion, "regresion")
    trace = Trace()
    r = E.regresion(e["x"], e["y"], trace)
    xs = [float(P.fraccion(v)) for v in e["x"]]
    ys = [float(P.fraccion(v)) for v in e["y"]]
    a, b = float(r.a), float(r.b)
    grafica = C.Graph(series=(C.Serie("datos", tuple(xs), tuple(ys)),
                              _serie("recta", lambda x: a + b * x, min(xs), max(xs), 2)),
                      x_label="x", y_label="y", description=f"nube de puntos y {r.texto()}")
    exacto = {"a": str(r.a), "b": str(r.b), "r²": str(r.r2), "r": f"{r.r():.10g}",
              "residuos": [str(v) for v in r.residuos]}
    return _ok(peticion, trace, exacto, "Xᵀe = 0 y Σe² = Syy(1 − r²) exactos", r.texto(),
               grafica=grafica)


@_con_discrepancia
def _estimador(peticion: C.Peticion) -> C.Resultado:
    """``{"familia": "poisson", "datos": [2, 3, 1]}`` o ``{"familia": "densidad", "datos":
    [...], "f": "t*x^(t-1)", "parametro": "t", "desde": 0, "hasta": 1, "rango": [0.1, 20]}``."""
    from academic_core.domain.engineering.mathlab import estadistica as E

    e = _dict(peticion, "estimador")
    trace = Trace()
    r = E.estimadores(str(e["familia"]), e["datos"], trace, e)
    exacto = {**{f"momentos {k}": _t(v) for k, v in r.momentos.items()},
              **{f"MV {k}": _t(v) for k, v in r.mv.items()}}
    lo, hi = r.rango
    grafica = _grafica([_serie("log L", r.logL, lo, hi)], next(iter(r.mv)), "log L",
                       "log-verosimilitud; su máximo es el estimador MV")
    if r.numerico:
        return _numerico(peticion, trace, exacto, "sección áurea sobre log L y bisección de la "
                         "ecuación de momentos", "", grafica=grafica,
                         aproximado=float(next(iter(r.mv.values()))))
    return _ok(peticion, trace, exacto, "fórmula cerrada y máximo numérico de log L "
               "(sección áurea)", "", grafica=grafica)


# ---------------------------------------------------------------------------
# procesos, tablas, comunicaciones, simulación
# ---------------------------------------------------------------------------


@_con_discrepancia
def _proceso(peticion: C.Peticion) -> C.Resultado:
    """``{"tipo": "poisson", "lambda": 2, "consulta": "conteo", "t": 3, "k": 4}``,
    ``{"tipo": "paseo", "p": "1/2", "n": 6, "k": 2}`` o ``{"tipo": "va", "X": "A*cos(w*t+x)",
    "variables": {"x": {"tipo": "uniforme", "a": 0, "b": "2*pi"}, ...}}``."""
    from academic_core.domain.engineering.mathlab import procesos as PR

    e = _dict(peticion, "proceso")
    trace = Trace()
    tipo = str(e.get("tipo", "poisson"))
    if tipo == "poisson":
        trace.metodo("proceso.poisson",
                     "conteo de llegadas por la fórmula de Poisson, "
                     "contrastado con una simulación sembrada",
                     why="un proceso de Poisson cuenta eventos en un "
                         "intervalo y su ley depende solo de la longitud del "
                         "intervalo (propiedad de incremento independiente); "
                         "por eso la fórmula da la exacta y la simulación "
                         "solo sirve de segundo camino")
        r = PR.poisson_proceso(e, trace, peticion.semilla)
        if r["simulacion"] is None:
            return _numerico(peticion, trace, {"valor": r["exacto"]}, "fórmula exacta sin "
                             "simulación (demasiadas llegadas)", "", aproximado=r["valor"])
        return _ok(peticion, trace, {"valor": r["exacto"]}, "fórmula exacta y simulación "
                   "sembrada de las llegadas", r["simulacion"].texto(), aproximado=r["valor"])
    if tipo in ("paseo", "bernoulli", "pm1"):
        trace.metodo("proceso.paseo",
                     "distribución del valor tras n pasos, por enumeración de "
                     "caminos cuando caben",
                     why="con p y 1−p el valor tras n pasos es la suma de n "
                         "saltos, y enumerar los caminos da la ley exacta; "
                         "cuando 2ⁿ es demasiado grande se cambia a las "
                         "fórmulas y se **dice**, porque el coste crece de "
                         "forma exponencial")
        e2 = dict(e)
        e2["tipo"] = "bernoulli" if tipo == "bernoulli" or e.get("modelo") == "bernoulli" else "pm1"
        r = PR.paseo(e2, trace)
        exacto = {k: str(v) for k, v in r.items()}
        enumerado = any(s.rule == "paseo.enumeracion" for s in trace)
        if enumerado:
            return _ok(peticion, trace, exacto, "enumeración exacta de los caminos", "")
        return _numerico(peticion, trace, exacto, "fórmulas (sin enumeración, n > 16)", "")
    if tipo == "va":
        trace.metodo("proceso.va",
                     "media, autocorrelación y estacionariedad de un proceso "
                     "definido por X(t, ω)",
                     why="con las variables aleatorias de ω se integra sobre "
                         "la ley de cada una, y R(τ) sale de⟨X(t)·X(t+τ)⟩: "
                         "la estacionariedad se decide comparando R(τ) con "
                         "R(0), no suponiéndola")
        r = PR.proceso_va(str(e["X"]), e["variables"], str(e.get("var", "t")), trace,
                          peticion.semilla)
        exacto = {"E[X(t)]": mx.text(r.media), "R(t1, t2)": mx.text(r.R),
                  "estacionario (sentido amplio)": "sí" if r.estacionario else "no",
                  "motivo": r.motivo}
        grafica = None
        if r.R_tau is not None:
            exacto["R(τ)"] = mx.text(r.R_tau)
            exacto["potencia R(0)"] = mx.text(r.potencia)
            libres = sorted(mx.variables(r.R_tau) - {"τ"})
            env = {n: 1.0 for n in libres}
            grafica = _grafica([_serie("R(τ)", lambda tau: float(mx.valor_real(
                r.R_tau, {**env, "τ": tau}) or 0.0), -6.0, 6.0)], "τ", "R",
                "autocorrelación" + (f" (con {', '.join(libres)} = 1)" if libres else ""))
        return _ok(peticion, trace, exacto, "esperanzas exactas y simulación sembrada de "
                   "R(t1, t2)", "", grafica=grafica)
    raise C.error("BAD_INPUT", f"proceso «{tipo}» (poisson, paseo o va)")


@_con_discrepancia
def _tabla_estadistica(peticion: C.Peticion) -> C.Resultado:
    """``{"ley": "t", "gl": 19, "p": "0.975"}`` (cuantil) o ``{"ley": "normal", "x": 1.96}``
    (F); leyes normal, t, chi2, f (``d1``, ``d2``)."""
    e = _dict(peticion, "tabla_estadistica")
    trace = Trace()
    ley = str(e.get("ley", "normal"))
    trace.metodo("tabla.cuantil",
                 f"el cuantil se busca invirtiendo la {ley} con los "
                 "parámetros declarados",
                 why="una tabla de cuantiles es la F de esa ley evaluada en "
                     "un punto, y consultarla es invertir F. El cuantil de t "
                     "y el de normal se parecen pero solo coinciden con "
                     "muchos grados de libertad: por eso los gl son parte del "
                     "enunciado y no un detalle")
    params = {k: v for k, v in e.items() if k in ("gl", "nu", "k", "d1", "d2")}
    if ley in ("t", "student") and "gl" in params:
        params = {"nu": params["gl"]}
    if ley in ("chi2",) and "gl" in params:
        params = {"k": params["gl"]}
    d = P.distribucion(ley, params, trace)
    if e.get("p") is not None:
        p = float(P.fraccion(e["p"], "p"))
        q = d.cuantil(p)
        Fq = P.F_por_cuadratura(d, q)
        if abs(Fq - p) > 1e-7:
            raise C.error("DISCREPANT", f"F({q}) = {Fq} ≠ {p}")
        trace.regla("tabla.cuantil", f"{d.titulo()}: F(x) = {p} ⇒ x = {q:.10g}; "
                                     f"en tabla {P.redondeo_tabla(q, 3)}",
                    why=f"F por {d.especial or 'su forma cerrada'}; se resuelve F(x) = p")
        trace.verificacion("tabla.cuadratura", f"F({q:.10g}) = {Fq:.12f} integrando la densidad")
        return _ok(peticion, trace, {"cuantil": f"{q:.10g}", "tabla": P.redondeo_tabla(q, 3)},
                   "cuantil por la función especial, comprobado por cuadratura", d.titulo(),
                   aproximado=q)
    x = float(P.fraccion(e["x"], "x"))
    F = d.F(x)
    Fq = P.F_por_cuadratura(d, x)
    if abs(F - Fq) > 1e-8:
        raise C.error("DISCREPANT", f"F({x}) = {F} frente a cuadratura {Fq}")
    trace.regla("tabla.F", f"{d.titulo()}: F({x:g}) = {F:.10g}; en tabla {P.redondeo_tabla(F, 4)}")
    trace.verificacion("tabla.cuadratura", f"cuadratura de la densidad: {Fq:.12f}")
    return _ok(peticion, trace, {"F": f"{F:.10g}", "tabla": P.redondeo_tabla(F, 4),
                                 "1 − F": f"{1 - F:.10g}"},
               "función especial frente a cuadratura", d.titulo(), aproximado=F)


@_con_discrepancia
def _comunicaciones(peticion: C.Peticion) -> C.Resultado:
    """``{"calculo": "ber", "modulacion": "bpsk", "EbN0_dB": 6}`` (o ``"objetivo": 1e-5``),
    ``{"calculo": "aloha", "G": 0.5, "ranurado": false}``,
    ``{"calculo": "desvanecimiento", "modelo": "rayleigh", "snr_media_db": 20,
    "umbral_db": 10}`` o ``{"calculo": "arq", "protocolo": "retroceso_n", "P": 0.1,
    "a": 2, "N": 7}``."""
    from academic_core.domain.engineering.mathlab import procesos as PR

    e = _dict(peticion, "comunicaciones")
    trace = Trace()
    calculo = str(e.get("calculo", "ber"))
    if calculo == "ber":
        obj = e.get("objetivo")
        r = PR.ber(str(e.get("modulacion", "bpsk")),
                   None if e.get("EbN0_dB") is None else float(P.fraccion(e["EbN0_dB"])),
                   None if obj is None else float(obj), trace, peticion.semilla)
        f = PR.BER_MODULACIONES[str(e.get("modulacion", "bpsk")).lower()][1]
        grafica = _grafica([_serie("P_b", lambda db: math.log10(max(f(PR.db_a_lineal(db)), 1e-300)),
                                   0.0, 16.0, 160)], "Eb/N0 (dB)", "log₁₀ P_b",
                           f"curva BER de {e.get('modulacion', 'bpsk')} frente a Eb/N0")
        return _ok(peticion, trace, {"P_b": f"{r['P_b']:.6g}", "Eb/N0 (dB)": f"{r['EbN0_dB']:.6g}",
                                     "fórmula": r["formula"]},
                   "fórmula con Q y simulación o cuadratura", "", aproximado=r["P_b"],
                   grafica=grafica)
    if calculo == "aloha":
        ranurado = bool(e.get("ranurado", False))
        G = float(P.fraccion(e.get("G", 0.5), "G"))
        r = PR.aloha(G, ranurado, trace, peticion.semilla)
        fun = (lambda g: g * math.exp(-g)) if ranurado else (lambda g: g * math.exp(-2 * g))
        grafica = _grafica([_serie("S(G)", fun, 0.0, 4.0)], "G", "S",
                           f"caudal de ALOHA {'ranurado' if ranurado else 'puro'}")
        return _ok(peticion, trace, {"S": f"{r['S']:.10g}", "S máx": "1/e" if ranurado else "1/(2e)",
                                     "G óptima": f"{r['Gopt']:g}"},
                   "fórmula y simulación sembrada", "", aproximado=r["S"], grafica=grafica)
    if calculo == "desvanecimiento":
        r = PR.desvanecimiento(e, trace)
        return _ok(peticion, trace, {"P(fallo)": f"{r['P_fallo']:.10g}"},
                   "forma cerrada (o Q de Marcum) frente a cuadratura", "",
                   aproximado=r["P_fallo"])
    if calculo == "arq":
        r = PR.arq(e, trace, peticion.semilla)
        return _ok(peticion, trace, {"U": f"{r['U']:.10g}", "fórmula": r["formula"],
                                     "a": f"{r['a']:.6g}"},
                   "fórmula y simulación sembrada del mismo modelo", "", aproximado=r["U"])
    raise C.error("BAD_INPUT", f"cálculo desconocido «{calculo}»")


@_con_discrepancia
def _montecarlo(peticion: C.Peticion) -> C.Resultado:
    """``{"dist": "exponencial", "parametros": {"lambda": 2}, "suceso": "P(X>1)",
    "muestras": 50000}``: simulación sembrada (semilla de la petición) frente al valor
    exacto, para contrastar cualquier resultado (§8.2 G, «Simulación»)."""
    e = _dict(peticion, "montecarlo")
    trace = Trace()
    d = P.distribucion(str(e["dist"]), dict(e.get("parametros", {})), trace)
    A, B = P.lee_suceso(str(e["suceso"]))
    n = int(e.get("muestras", 20000))
    if not 100 <= n <= 2_000_000:
        raise C.error("BAD_INPUT", "entre 100 y 2·10⁶ muestras")
    if n * d.coste > 4e7:
        raise C.error("BAD_INPUT", f"{n} muestras de {d.titulo()} son demasiado trabajo "
                                   f"(máximo {int(4e7 / d.coste)})")
    I = A if B is None else A.interseca(B)

    def ind(g):
        while True:
            x = d.muestra(g)
            if B is None or P.en_intervalo(B, x):
                return 1.0 if P.en_intervalo(I, x) else 0.0
    sim = P.simula(ind, n, peticion.semilla)
    v, _ = P.probabilidad_intervalo(d, I)
    if B is not None:
        v /= P.probabilidad_intervalo(d, B)[0]
    trace.metodo("mc.simulacion", f"{n} muestras de {d.titulo()} con semilla {peticion.semilla}",
                 why="cada muestra se genera con el mecanismo de la ley (no invirtiendo F), así "
                     "que contrasta la fórmula de forma independiente")
    dentro = sim.dentro(v, 5)
    trace.verificacion("mc.contraste", f"estimación {sim.texto()}; exacto {v:.10g}: "
                                       f"{'dentro' if dentro else 'FUERA'} de 5 errores típicos")
    sello = V.Seal(V.NUMERIC_ONLY if dentro else V.DISCREPANT, "Monte Carlo sembrado",
                   f"{sim.texto()} frente a {v:.10g}")
    return _finalizar(peticion, trace, {"estimación": f"{sim.valor:.6g}",
                                        "error típico": f"{sim.error_tipico:.2g}",
                                        "exacto": f"{v:.10g}"}, aproximado=sim.valor,
                      error=sim.error_tipico, sello=sello)


C.registrar("probabilidad", _probabilidad)
C.registrar("variable_aleatoria", _variable_aleatoria)
C.registrar("vector_aleatorio", _vector_aleatorio)
C.registrar("aproximacion_normal", _aproximacion_normal)
C.registrar("estadistica", _estadistica)
C.registrar("intervalo_confianza", _intervalo_confianza)
C.registrar("contraste", _contraste)
C.registrar("regresion", _regresion)
C.registrar("estimador", _estimador)
C.registrar("proceso", _proceso)
C.registrar("tabla_estadistica", _tabla_estadistica)
C.registrar("comunicaciones", _comunicaciones)
C.registrar("montecarlo", _montecarlo)
