# SPDX-License-Identifier: MIT
"""ML-8 (§4.5): ecuaciones diferenciales ordinarias exactas.

Lineales de coeficientes constantes ``aₙy⁽ⁿ⁾ + … + a₀y = f(t)``:

* homogénea: raíces del polinomio característico en ℚ, ℚ(√d) o complejas
  conjugadas, con su multiplicidad (``tʲe^{rt}``, ``e^{pt}cos ωt``, ``e^{pt}sen ωt``);
* particular por **coeficientes indeterminados** cuando f es un cuasipolinomio: la
  forma de prueba ``tˢ·(polinomio)·e^{αt}(cos, sen)`` con s la multiplicidad de
  α + iβ como raíz (resonancia) y los coeficientes obtenidos exactos (se calculan
  con L⁻¹{F/p} quitando los modos homogéneos, que es la misma solución);
* particular por **variación de parámetros** (Wronskiano y Cramer) si no lo es;
* **PVI por Laplace** con segundo miembro a trozos, escalones y deltas.

Comprobación: la solución se sustituye en la ecuación **exactamente** en cada
tramo entre saltos (álgebra de cuasipolinomios: Σaₖy⁽ᵏ⁾ − f = 0 término a término),
las condiciones iniciales se evalúan exactas y, en cada delta, se comprueba el salto
de y⁽ⁿ⁻¹⁾ = área/aₙ.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import laplace as LP
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

limpio = Q.limpio
MAX_ORDEN = 8


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


# ---------------------------------------------------------------------------
# lectura de la ecuación
# ---------------------------------------------------------------------------


@dataclass
class Ecuacion:
    """Σ aₖ(t)·y⁽ᵏ⁾ = f(t) (lineal) o, si no lo es, la expresión E(t, y, y′…) = 0."""

    t: str
    y: str
    orden: int
    coefs: list               # aₖ como expresiones (pueden depender de t)
    f: mx.Expr                # segundo miembro (texto original para Laplace)
    f_texto: str
    lineal: bool
    E: mx.Expr                # LHS − RHS con y⁽ᵏ⁾ → símbolos Yk__

    def constantes(self) -> bool:
        return self.lineal and all(not mx.depends(a, self.t) for a in self.coefs)

    def texto_lhs(self) -> str:
        partes = []
        for k in range(self.orden, -1, -1):
            a = self.coefs[k]
            if Q.es_cero(a):
                continue
            d = self.y + "'" * k
            v = mx.exact_value(a)
            if v == 1 and not mx.variables(a):
                partes.append(d)
            else:
                partes.append(f"{mx.text(a)}·{d}")
        return " + ".join(partes).replace("+ -", "- ")


def _simbolo(k: int) -> str:
    return f"Y{k}__"


def leer(texto: str, t: str = "t", y: str = "y") -> Ecuacion:
    """«y'' + 3y' + 2y = u(t-1)»: derivadas con primas, y(t) o y."""
    if "=" not in texto:
        texto = texto + " = 0"
    lhs, rhs = texto.split("=", 1)
    rhs_original = rhs.strip()

    def sustituye(s: str) -> str:
        s = s.replace("**", "^").replace("’", "'").replace("′", "'").replace("″", "''")
        s = re.sub(rf"\b{y}\s*\(\s*{t}\s*\)", y, s)
        for k in range(MAX_ORDEN, 0, -1):
            primas = "'" * k
            s = re.sub(r"\b" + y + primas + r"(?!')", _simbolo(k), s)
        s = re.sub(rf"\b{y}\b(?!')", _simbolo(0), s)
        return s

    L = sustituye(lhs)
    R = sustituye(rhs)
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    try:
        El = mx.parse(LP.prepara(L, t))
        Er = mx.parse(LP.prepara(R, t))
    except Exception as exc:  # noqa: BLE001
        raise _error("BAD_INPUT", f"no se puede leer la ecuación: {exc}") from None
    E = mx.Sub(El, Er)
    usados = [k for k in range(MAX_ORDEN + 1) if _simbolo(k) in mx.variables(E)]
    if not usados or max(usados) == 0:
        raise _error("BAD_INPUT", f"la ecuación no contiene derivadas de {y}")
    n = max(usados)
    coefs = []
    lineal = True
    for k in range(n + 1):
        try:
            a = limpio(DM.differentiate(E, _simbolo(k))) if _simbolo(k) in mx.variables(E) \
                else mx.Num(Fraction(0))
        except Exception:  # noqa: BLE001
            a = None
        if a is None or any(_simbolo(j) in mx.variables(a) for j in range(n + 1)):
            lineal = False
            a = mx.Num(Fraction(0))
        coefs.append(a)
    f = mx.Num(Fraction(0))
    if lineal:
        resto = E
        for k in range(n + 1):
            resto = mx.substitute(resto, _simbolo(k), mx.Num(Fraction(0)))
        f = limpio(Q.pliega(mx.Neg(resto)))
        # comprobación de linealidad: E = Σ aₖYk − f exactamente
        recon = mx.Num(Fraction(0))
        for k, a in enumerate(coefs):
            recon = mx.Add(recon, mx.Mul(a, mx.Sym(_simbolo(k))))
        from academic_core.domain.engineering.mathlab import verify as V

        try:
            dif = mx.Sub(mx.Sub(recon, f), E)
            ok = all(abs(v) < 1e-9 for v in (_eval_num(dif, t, n, z) for z in (0.3, 1.7, 2.9)))
        except Exception:  # noqa: BLE001
            ok = False
        lineal = ok
        _ = V
    f_texto = rhs_original if lineal and not mx.depends(El, t) or True else ""
    # el segundo miembro para Laplace: f como texto (con u y δ)
    f_texto = mx.text(f) if lineal else ""
    return Ecuacion(t, y, n, coefs, f, f_texto, lineal, E)


def _sin_deltas(e):
    """δ(·) → una constante cualquiera, para poder evaluar la comprobación de linealidad."""
    if isinstance(e, mx.Call) and e.name == "delta":
        return mx.Num(Fraction(37, 100))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sin_deltas(e.left), _sin_deltas(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_deltas(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sin_deltas(e.base), _sin_deltas(e.exponent))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_sin_deltas(a) for a in e.args))
    return e


def _eval_num(e, t, n, z):
    e = _sin_deltas(e)
    env = {v: 1.3 + 0.17 * i for i, v in enumerate(sorted(mx.variables(e)))}
    env[t] = z
    for k in range(n + 1):
        env[_simbolo(k)] = 0.7 + 0.31 * k
    v = mx.valor_real(e, env)
    if v is None:
        raise ValueError
    return v


# ---------------------------------------------------------------------------
# polinomio característico y homogénea
# ---------------------------------------------------------------------------


def _coefs_q(ec: Ecuacion) -> list[Fraction]:
    out = []
    for a in ec.coefs:
        v = mx.exact_value(a)
        if v is None or mx.variables(a):
            raise _no(f"coeficiente {mx.text(a)} no racional: el polinomio característico "
                      "necesita coeficientes racionales para sus raíces exactas")
        out.append(Fraction(v))
    return out


@dataclass
class Modo:
    """tʲ·e^{αt}·f(βt) de la base de soluciones de la homogénea."""

    termino: Q.Termino
    texto_raiz: str


def _texto_poli(p: list[Fraction], var: str = "λ") -> str:
    from academic_core.domain.engineering.mathlab import algebra as AL

    return AL._texto_poli(p).replace("λ", var)


def base_homogenea(p: list[Fraction], trace: Trace) -> tuple[list[Q.Termino], list[str]]:
    """Modos de p(D)y = 0 y la descripción de cada raíz."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    cero = mx.Num(Fraction(0))
    uno = mx.Num(Fraction(1))
    modos: list[Q.Termino] = []
    raices: list[str] = []
    for q, m in AL.factores_irreducibles(p):
        if len(q) == 2:
            r = -q[0]
            raices.append(f"λ = {r}" + (f" (doble)" if m == 2 else f" (multiplicidad {m})"
                                        if m > 2 else ""))
            modos.extend(Q.Termino(uno, j, Q.num(r), "1", cero) for j in range(m))
        elif len(q) == 3:
            c0, b = q[0], q[1]
            pr = -b / 2
            w2 = c0 - b * b / 4
            w = limpio(mx.Root(2, Q.num(abs(w2))))
            if w2 > 0:
                raices.append(f"λ = {pr} ± {mx.text(w)}·i" + (f" (multiplicidad {m})" if m > 1
                                                               else ""))
                for j in range(m):
                    modos.append(Q.Termino(uno, j, Q.num(pr), "cos", w))
                    modos.append(Q.Termino(uno, j, Q.num(pr), "sin", w))
            else:
                raices.append(f"λ = {pr} ± {mx.text(w)}" + (f" (multiplicidad {m})" if m > 1
                                                             else ""))
                for j in range(m):
                    modos.append(Q.Termino(uno, j, limpio(mx.Add(Q.num(pr), w)), "1", cero))
                    modos.append(Q.Termino(uno, j, limpio(mx.Sub(Q.num(pr), w)), "1", cero))
        else:
            raise _no(f"el polinomio característico tiene el factor irreducible "
                      f"{_texto_poli(q)} de grado ≥ 3: sus raíces no tienen forma exacta "
                      "sencilla (usa los métodos numéricos)")
    trace.regla("edo.caracteristico", f"p(λ) = {_texto_poli(p)} = 0: " + "; ".join(raices),
                why="y = e^(λt) es solución si y solo si p(λ) = 0; una raíz de multiplicidad "
                    "m da tʲe^(λt), j < m; un par complejo p ± iω da e^(pt)cos ωt y e^(pt)sen ωt")
    return modos, raices


def _modo_texto(x: Q.Termino, t: str) -> str:
    return mx.text(Q.a_expr([Q.Termino(mx.Num(Fraction(1)), x.n, x.alfa, x.tipo, x.beta)], t))


# ---------------------------------------------------------------------------
# solución general (coeficientes constantes)
# ---------------------------------------------------------------------------


@dataclass
class General:
    homogenea: list           # modos
    particular: object        # Q.Cuasi o mx.Expr
    metodo: str
    prueba: str = ""
    t: str = "t"
    aproximada: bool = False

    def texto(self) -> str:
        t = self._texto()
        if self.aproximada:
            t = LP.decimales(t) + " (raíces del característico numéricas)"
        return t

    def _texto(self) -> str:
        yh = " + ".join(f"C{i + 1}·{_modo_texto(m, self.t)}" for i, m in enumerate(self.homogenea))
        if isinstance(self.particular, list):
            yp = mx.text(Q.a_expr(self.particular, self.t)) if self.particular else "0"
        else:
            yp = mx.text(self.particular)
        if yp == "0":
            return f"y = {yh}"
        return f"y = {yh} + {yp}"


def _residuo(coefs: list[Fraction], y: Q.Cuasi) -> Q.Cuasi:
    total: Q.Cuasi = []
    d = list(y)
    for k, a in enumerate(coefs):
        if a:
            total = Q.suma(total, Q.escala(d, Q.num(a)))
        d = Q.deriva(d)
    return total


def _es_modo(x: Q.Termino, modos: list[Q.Termino]) -> bool:
    for m in modos:
        if m.n == x.n and Q.es_cero(limpio(mx.Sub(m.alfa, x.alfa))) and \
                (m.tipo == "1") == (x.tipo == "1") and (
                    x.tipo == "1" or Q.es_cero(limpio(mx.Sub(m.beta, x.beta)))):
            return True
    return False


def general(ec: Ecuacion, trace: Trace | None = None) -> General:
    """Solución general de una lineal de coeficientes constantes."""
    trace = trace if trace is not None else Trace()
    if not ec.constantes():
        raise _no("la solución general por el característico necesita coeficientes constantes")
    p = _coefs_q(ec)
    try:
        modos, _ = base_homogenea(p, trace)
    except UnsupportedError as exc:
        if "grado ≥ 3" not in str(exc):
            raise
        return _general_numerica(ec, p, trace)
    if Q.es_cero(ec.f):
        trace.regla("edo.homogenea", "segundo miembro nulo: y = yₕ")
        return General(modos, [], "homogénea", t=ec.t)
    try:
        fq = Q.leer(ec.f, ec.t)
    except UnsupportedError:
        fq = None
    if fq is not None:
        yp = particular_indeterminados(p, fq, modos, ec.t, trace)
        res = Q.normaliza(Q.suma(_residuo(p, yp), Q.escala(fq, mx.Num(Fraction(-1)))))
        if res:
            raise _error("DISCREPANT", "la particular no verifica la ecuación")
        trace.verificacion("edo.particular", "Σ aₖ·y_p⁽ᵏ⁾ = f exactamente (álgebra de "
                           "cuasipolinomios)", why="sustitución en la ecuación")
        return General(modos, yp, "coeficientes indeterminados", t=ec.t)
    yp = variacion_parametros(ec, modos, trace)
    return General(modos, yp, "variación de parámetros", t=ec.t)


def _general_numerica(ec: Ecuacion, p: list[Fraction], trace: Trace) -> General:
    """Característico con un factor irreducible de grado ≥ 3: raíces numéricas
    (Durand-Kerner) y la particular por residuos numéricos de F/p."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    cero = mx.Num(Fraction(0))
    uno = mx.Num(Fraction(1))
    raices = AL._raices_complejas([c / p[-1] for c in p])
    modos: list[Q.Termino] = []
    vistos: list[complex] = []
    for r in sorted(raices, key=lambda z: (round(z.real, 9), -z.imag)):
        if any(abs(r - v) < 1e-7 or abs(r.conjugate() - v) < 1e-7 for v in vistos):
            continue
        m = sum(1 for z in raices if abs(z - r) < 1e-6)
        vistos.append(r)
        if abs(r.imag) < 1e-12:
            modos.extend(Q.Termino(uno, j, mx.Num(Fraction(r.real)), "1", cero) for j in range(m))
        else:
            b = mx.Num(Fraction(abs(r.imag)))
            for j in range(m):
                modos.append(Q.Termino(uno, j, mx.Num(Fraction(r.real)), "cos", b))
                modos.append(Q.Termino(uno, j, mx.Num(Fraction(r.real)), "sin", b))
    trace.aviso("edo.caracteristico_numerico", f"p(λ) = {_texto_poli(p)} tiene un factor "
                "irreducible de grado ≥ 3: raíces numéricas " + ", ".join(
                    f"{z.real:.10g}" + (f" ± {abs(z.imag):.10g}i" if abs(z.imag) > 1e-12 else "")
                    for z in vistos))
    if Q.es_cero(ec.f):
        return General(modos, [], "homogénea (raíces numéricas)", t=ec.t, aproximada=True)
    fq = Q.leer(ec.f, ec.t)
    total: Q.Cuasi = []
    for x in fq:
        fr = LP.transformada_termino(x)
        den = AL._p_mul(list(fr.den), list(p))
        total = Q.suma(total, LP.inversa_numerica(fr.num, den))

    def es_modo(x):
        for m in modos:
            if m.n == x.n and abs(float(mx.valor_real(m.alfa, {})) -
                                  float(mx.valor_real(x.alfa, {}))) < 1e-7 and \
                    (m.tipo == "1") == (x.tipo == "1") and (
                        x.tipo == "1" or abs(float(mx.valor_real(m.beta, {})) -
                                             float(mx.valor_real(x.beta, {}))) < 1e-7):
                return True
        return False
    yp = Q.normaliza([x for x in total if not es_modo(x)])
    # comprobación numérica: Σaₖy_p⁽ᵏ⁾ − f en puntos
    res = Q.suma(_residuo(p, yp), Q.escala(fq, mx.Num(Fraction(-1))))
    for tv in (0.3, 1.1, 2.2):
        v = mx.valor_real(Q.a_expr(res, ec.t), {ec.t: tv}) if res else 0.0
        if v is not None and abs(v) > 1e-7:
            raise _error("DISCREPANT", "la particular numérica no verifica la ecuación")
    trace.verificacion("edo.particular_num", "Σaₖ·y_p⁽ᵏ⁾ − f ≈ 0 en 3 puntos (coeficientes "
                       "numéricos)", why="sustitución")
    return General(modos, yp, "residuos numéricos", t=ec.t, aproximada=True)


def particular_indeterminados(p: list[Fraction], fq: Q.Cuasi, modos: list[Q.Termino], t: str,
                              trace: Trace) -> Q.Cuasi:
    """y_p con la forma de prueba tˢ·Pₘ(t)·e^{αt}·(cos, sen): L⁻¹{F/p} sin los modos
    homogéneos (es la única particular de esa forma)."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    # forma de prueba, por grupo (α, β) del segundo miembro
    grupos: dict[tuple, int] = {}
    for x in fq:
        clave = (mx.text(x.alfa), mx.text(x.beta) if x.tipo != "1" else "0")
        grupos[clave] = max(grupos.get(clave, 0), x.n)
    formas = []
    for (al, be), m in grupos.items():
        alfa = mx.parse(al)
        beta = mx.parse(be)
        s = sum(1 for x in modos if x.n == 0 and Q.es_cero(limpio(mx.Sub(x.alfa, alfa))) and
                (x.tipo == "1" if be == "0" else x.tipo == "cos" and
                 Q.es_cero(limpio(mx.Sub(x.beta, beta)))))
        mult = sum(1 for x in modos if Q.es_cero(limpio(mx.Sub(x.alfa, alfa))) and
                   (x.tipo == "1" if be == "0" else x.tipo == "cos" and
                    Q.es_cero(limpio(mx.Sub(x.beta, beta)))))
        poli = " + ".join(f"A{k}·t^{k}" if k > 1 else ("A1·t" if k == 1 else "A0")
                          for k in range(m + 1))
        trig = "" if be == "0" else f"·(cos({be}·t), sen({be}·t))"
        ex = "" if al == "0" else f"·e^({al}·t)"
        pre = "" if mult == 0 else f"t^{mult}·" if mult > 1 else "t·"
        formas.append(f"{pre}({poli}){ex}{trig}" + (
            f" — resonancia: {al}{' ± ' + be + 'i' if be != '0' else ''} es raíz de "
            f"multiplicidad {mult}" if mult else ""))
        _ = s
    trace.regla("edo.forma_prueba", "y_p = " + "; ".join(formas),
                why="coeficientes indeterminados: misma forma que f, multiplicada por tˢ con s la "
                    "multiplicidad de α ± iβ como raíz del característico")
    # coeficientes: L⁻¹{F(s)/p(s)} con condiciones nulas, sin los modos homogéneos
    total: Q.Cuasi = []
    for x in fq:
        fr = LP.transformada_termino(x)
        if not isinstance(fr.den[0], Fraction):
            raise _no("exponente o frecuencia no racional en el segundo miembro: la forma de "
                      "prueba no tiene raíces exactas en ℚ[s]")
        den = AL._p_mul(list(fr.den), list(p))
        _, simples = LP.simples(fr.num, den)
        for f in simples:
            total = Q.suma(total, LP.inversa_simple(f))
    yp = [x for x in total if not _es_modo(x, modos)]
    yp = Q.normaliza(yp)
    trace.regla("edo.coeficientes", f"y_p = {mx.text(Q.a_expr(yp, t))}",
                why="los coeficientes A₀, A₁… se obtienen exactos (sistema lineal equivalente: "
                    "fracciones simples de F(s)/p(s) quitando los modos de la homogénea)")
    return yp


def variacion_parametros(ec: Ecuacion, modos: list[Q.Termino], trace: Trace) -> mx.Expr:
    """y_p = Σ yᵢ·∫Wᵢ·f/(aₙ·W) (Cramer sobre el sistema del Wronskiano)."""
    from academic_core.domain.engineering.mathlab import integracion as IN
    from academic_core.domain.engineering.mathlab import multiple as MI

    n = ec.orden
    if len(modos) != n:
        raise _error("INTERNAL", "la base de la homogénea no tiene n funciones")
    if all(isinstance(m, Q.Termino) for m in modos):
        ys = [[m] for m in modos]
        filas = []
        for i in range(n):
            filas.append([Q.a_expr(y, ec.t) for y in ys])
            ys = [Q.deriva(y) for y in ys]
        base_expr = [Q.a_expr([m], ec.t) for m in modos]
    else:
        base_expr = list(modos)
        filas = []
        actual = base_expr
        for i in range(n):
            filas.append(actual)
            actual = [_d(f, ec.t) for f in actual]
    W = MI._limpio(_det(filas))
    trace.regla("edo.wronskiano", f"W = {mx.text(W)}",
                why="Wronskiano de la base: no se anula, así que el sistema de Cramer es único")
    an = ec.coefs[n]
    total = None
    for i in range(n):
        Wi_filas = [list(f) for f in filas]
        for r in range(n):
            Wi_filas[r][i] = mx.Num(Fraction(1 if r == n - 1 else 0))
        Wi = MI._limpio(_det(Wi_filas))
        bruto = mx.Div(mx.Mul(Wi, ec.f), mx.Mul(an, W))
        integrando = _simplifica_trig(bruto)
        candidatos = [integrando]
        try:
            sc = _cancela_producto(_a_seno_coseno(MI._limpio(bruto)))
            candidatos.append(_pitagoras_partido(sc))
        except Exception:  # noqa: BLE001
            pass
        primitivas = []
        ultimo = None
        for cand in candidatos:
            try:
                primitivas.append((MI._limpio(IN.primitiva(cand, ec.t)), cand))
            except Exception as exc:  # noqa: BLE001
                ultimo = exc
        if not primitivas:
            raise _no(f"variación de parámetros: sin primitiva exacta de "
                      f"{mx.text(integrando)} ({ultimo})")
        ci, integrando = min(primitivas, key=lambda p_: len(mx.text(p_[0])))
        trace.regla("edo.variacion", f"C{i + 1}′ = {mx.text(integrando)} ⇒ C{i + 1} = "
                    f"{mx.text(ci)}", why="Cramer: Cᵢ′ = Wᵢ·f/(aₙ·W)")
        term = mx.Mul(ci, base_expr[i])
        total = term if total is None else mx.Add(total, term)
    yp = _sin_modos(MI._limpio(total), modos, ec.t)
    _verifica_simbolica(ec, yp, trace)
    return yp


def _sin_modos(yp: mx.Expr, modos: list, t: str) -> mx.Expr:
    """Quita de y_p los sumandos c·(modo de la homogénea): ya están en C₁y₁ + C₂y₂."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    sumandos = []

    def aplana(e, signo):
        if isinstance(e, mx.Add):
            aplana(e.left, signo)
            aplana(e.right, signo)
        elif isinstance(e, mx.Sub):
            aplana(e.left, signo)
            aplana(e.right, -signo)
        elif isinstance(e, mx.Neg):
            aplana(e.arg, -signo)
        else:
            sumandos.append(e if signo > 0 else mx.Neg(e))
    aplana(yp, 1)
    fs = [Q.a_expr([m], t) if isinstance(m, Q.Termino) else m for m in modos]
    quedan = []
    for s_ in sumandos:
        absorbido = False
        for f in fs:
            try:
                ratio = MI._limpio(mx.Div(s_, f))
            except Exception:  # noqa: BLE001
                continue
            if not mx.depends(ratio, t):
                absorbido = True
                break
        if not absorbido:
            quedan.append(s_)
    if not quedan:
        return mx.Num(Fraction(0))
    r = quedan[0]
    for q in quedan[1:]:
        r = mx.Add(r, q)
    return MI._limpio(r)


def _a_seno_coseno(e):
    """tan, sec, csc, cot → cocientes de sen y cos (para poder cancelar)."""
    if isinstance(e, mx.Call) and len(e.args) == 1:
        a = _a_seno_coseno(e.args[0])
        s_, c_ = mx.Call("sin", (a,)), mx.Call("cos", (a,))
        uno = mx.Num(Fraction(1))
        tabla = {"tan": mx.Div(s_, c_), "sec": mx.Div(uno, c_), "csc": mx.Div(uno, s_),
                 "cot": mx.Div(c_, s_)}
        return tabla.get(e.name, mx.Call(e.name, (a,)))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_a_seno_coseno(e.left), _a_seno_coseno(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_seno_coseno(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_a_seno_coseno(e.base), e.exponent)
    return e


def _cancela_producto(e):
    """Producto/cociente de factores: los factores iguales arriba y abajo se cancelan."""
    coef = Fraction(1)
    exps: dict[str, list] = {}

    def recoge(n, k):
        nonlocal coef
        if isinstance(n, mx.Mul):
            recoge(n.left, k)
            recoge(n.right, k)
        elif isinstance(n, mx.Div):
            recoge(n.left, k)
            recoge(n.right, -k)
        elif isinstance(n, mx.Neg):
            coef = -coef
            recoge(n.arg, k)
        elif isinstance(n, mx.Pow) and mx.exact_value(n.exponent) is not None and \
                not mx.variables(n.exponent):
            recoge(n.base, k * Fraction(mx.exact_value(n.exponent)))
        elif mx.exact_value(n) is not None and not mx.variables(n):
            coef *= Fraction(mx.exact_value(n)) ** int(k) if Fraction(k).denominator == 1 else 1
            if Fraction(k).denominator != 1:
                exps.setdefault(mx.text(n), [n, Fraction(0)])[1] += k
        else:
            exps.setdefault(mx.text(n), [n, Fraction(0)])[1] += k
    recoge(e, Fraction(1))
    num: mx.Expr = Q.num(coef)
    den: mx.Expr = mx.Num(Fraction(1))
    for base, k in exps.values():
        if k > 0:
            num = mx.Mul(num, base if k == 1 else mx.Pow(base, Q.num(k)))
        elif k < 0:
            den = mx.Mul(den, base if k == -1 else mx.Pow(base, Q.num(-k)))
    return limpio(Q.pliega(mx.Div(num, den)))


def _pitagoras_partido(e):
    """sen²u/cos u → 1/cos u − cos u (y cos²u/sen u igual): integrandos de tabla."""
    def cambia(n):
        if isinstance(n, mx.Pow) and isinstance(n.base, mx.Call) and n.base.name == "sin" and \
                mx.exact_value(n.exponent) == 2:
            c = mx.Call("cos", n.base.args)
            return mx.Sub(mx.Num(Fraction(1)), mx.Pow(c, mx.Num(2)))
        if isinstance(n, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(n)(cambia(n.left), cambia(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(cambia(n.arg))
        return n
    partes = []

    def aplana(n, signo):
        if isinstance(n, mx.Add):
            aplana(n.left, signo)
            aplana(n.right, signo)
        elif isinstance(n, mx.Sub):
            aplana(n.left, signo)
            aplana(n.right, -signo)
        elif isinstance(n, mx.Neg):
            aplana(n.arg, -signo)
        else:
            partes.append(n if signo > 0 else mx.Neg(n))
    def reparte(n):
        """a·(b ± c)/d → a·b/d ± a·c/d (también con denominador variable)."""
        n = LP._expande(n)
        if isinstance(n, mx.Div):
            num = reparte(n.left)
            if isinstance(num, (mx.Add, mx.Sub)):
                return type(num)(reparte(mx.Div(num.left, n.right)),
                                 reparte(mx.Div(num.right, n.right)))
            if isinstance(num, mx.Neg):
                return mx.Neg(reparte(mx.Div(num.arg, n.right)))
            return mx.Div(num, n.right)
        if isinstance(n, (mx.Add, mx.Sub)):
            return type(n)(reparte(n.left), reparte(n.right))
        if isinstance(n, mx.Neg):
            return mx.Neg(reparte(n.arg))
        return n
    aplana(reparte(cambia(e)), 1)
    if not partes:
        return e
    total = None
    for p_ in partes:
        q = _cancela_producto(p_)
        total = q if total is None else mx.Add(total, q)
    return _a_sec(limpio(total))


def _a_sec(e):
    """1/cos u → sec u, 1/sen u → csc u (las primitivas de tabla)."""
    if isinstance(e, mx.Div) and isinstance(e.right, mx.Call) and e.right.name in ("cos", "sin"):
        nombre = "sec" if e.right.name == "cos" else "csc"
        return mx.Mul(_a_sec(e.left), mx.Call(nombre, e.right.args))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul)):
        return type(e)(_a_sec(e.left), _a_sec(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_sec(e.arg))
    return e


def _simplifica_trig(e):
    from academic_core.domain.engineering.mathlab import fourier as FO
    from academic_core.domain.engineering.mathlab import multiple as MI

    base = MI._limpio(e)
    candidatas = [base]
    try:
        sc = _a_seno_coseno(base)
        candidatas.append(_cancela_producto(sc))
        candidatas.append(FO.cancela(sc))
        candidatas.append(_pitagoras_partido(_cancela_producto(sc)))
    except Exception:  # noqa: BLE001
        pass
    from academic_core.domain.engineering.mathlab import verify as V

    buenas = [c for c in candidatas if c is base or V.numeric_agreement(c, base)[0]]
    return min(buenas, key=lambda c: len(mx.text(c)))


def _verifica_diferencias(ec: Ecuacion, y: mx.Expr, trace: Trace) -> None:
    """Σ aₖ·y⁽ᵏ⁾ − f en puntos con derivadas por diferencias centrales (h = 10⁻³)."""
    h = 1e-3
    probados = malos = 0
    for tv in (0.31, 0.47, 0.62):
        def yv(x):
            v = mx.valor_real(y, {ec.t: x})
            if v is None:
                raise ValueError
            return v
        try:
            ders = [yv(tv)]
            for k in range(1, ec.orden + 1):
                # k-ésima diferencia central
                tot = 0.0
                for j in range(k + 1):
                    tot += (-1) ** j * math.comb(k, j) * yv(tv + (k / 2 - j) * h)
                ders.append(tot / h ** k)
            lhs = sum(float(mx.valor_real(a, {ec.t: tv})) * d for a, d in zip(ec.coefs, ders))
            rhs = float(mx.valor_real(ec.f, {ec.t: tv}))
        except (ValueError, TypeError):
            continue
        probados += 1
        if abs(lhs - rhs) > 1e-4 * max(1.0, abs(rhs), abs(lhs)):
            malos += 1
    if malos or probados < 2:
        raise _error("DISCREPANT", "la solución no verifica la ecuación (diferencias finitas)")
    trace.verificacion("edo.diferencias", f"la ecuación se cumple en {probados} puntos con "
                       "derivadas por diferencias centrales", why="comprobación numérica: las "
                       "derivadas simbólicas crecían demasiado")


def _det(M):
    n = len(M)
    if n == 1:
        return M[0][0]
    if n == 2:
        return mx.Sub(mx.Mul(M[0][0], M[1][1]), mx.Mul(M[0][1], M[1][0]))
    total = None
    for j in range(n):
        menor = [fila[:j] + fila[j + 1:] for fila in M[1:]]
        term = mx.Mul(M[0][j], _det(menor))
        if j % 2:
            term = mx.Neg(term)
        total = term if total is None else mx.Add(total, term)
    return total


def _verifica_simbolica(ec: Ecuacion, y: mx.Expr, trace: Trace) -> None:
    """Σ aₖ·y⁽ᵏ⁾ − f ≡ 0 (equivalencia exacta, o en puntos si no se puede)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import verify as V

    d = y
    total = None
    try:
        for k, a in enumerate(ec.coefs):
            term = mx.Mul(a, d)
            total = term if total is None else mx.Add(total, term)
            if k < ec.orden:
                d = DM.differentiate(d, ec.t)
        ok = _eq0(mx.Sub(total, ec.f))
    except Exception:  # noqa: BLE001 - las derivadas crecen demasiado: diferencias finitas
        _verifica_diferencias(ec, y, trace)
        return
    if not ok:
        # exponentes irracionales (t^(√2 − 1)) que la equivalencia exacta no cierra:
        # el residuo en cinco puntos del dominio, relativo al tamaño de los términos
        malos = probados = 0
        for tv in (0.37, 0.81, 1.3, 2.2, 2.9):
            env = {ec.t: tv}
            for v in mx.variables(total) - {ec.t}:
                env[v] = 1.1
            r1, r2 = mx.valor_real(total, env), mx.valor_real(ec.f, env)
            if r1 is None or r2 is None:
                continue
            probados += 1
            if abs(r1 - r2) > 1e-9 * max(1.0, abs(r2), abs(r1)):
                malos += 1
        if malos or probados < 3:
            raise _error("DISCREPANT", "la solución no verifica la ecuación")
        trace.verificacion("edo.sustitucion_puntos", "la solución sustituida da el segundo "
                           f"miembro en {probados} puntos (la equivalencia simbólica no cierra "
                           "con exponentes irracionales)", why="definición de solución")
        return
    _ = V
    trace.verificacion("edo.sustitucion", "la solución sustituida da el segundo miembro "
                       "(equivalencia exacta)", why="definición de solución")


# ---------------------------------------------------------------------------
# PVI por Laplace
# ---------------------------------------------------------------------------


@dataclass
class PVI:
    inversa: object           # LP.Inversa
    t: str
    piezas_tramos: list       # [(desde, hasta, expr)] solución por tramos
    Y: str                    # Y(s) en texto

    def texto(self) -> str:
        cuerpo = self.inversa.texto().replace("f(t) =", "y(t) =")
        if len(self.piezas_tramos) > 1:
            trozos = "; ".join(f"{mx.text(e)} si {a} ≤ t < {b}"
                               for a, b, e in self.piezas_tramos)
            cuerpo += f"; a trozos: {trozos}"
        return cuerpo


def pvi_laplace(ec: Ecuacion, iniciales: list, trace: Trace | None = None) -> PVI:
    """y(0), y′(0), …, y⁽ⁿ⁻¹⁾(0) dados; L{y⁽ᵏ⁾} = sᵏY − Σ s^{k−1−j}y⁽ʲ⁾(0)."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    if not ec.constantes():
        raise _no("el PVI por Laplace necesita coeficientes constantes")
    p = _coefs_q(ec)
    n = ec.orden
    if len(iniciales) != n:
        raise _error("BAD_INPUT", f"hacen falta {n} condiciones iniciales y(0)…y^({n - 1})(0)")
    y0 = [limpio(c if isinstance(c, mx.Expr) else mx.parse(str(c))) for c in iniciales]
    # I(s) = Σₖ aₖ Σ_{j<k} s^{k−1−j}·y⁽ʲ⁾(0)
    I = [mx.Num(Fraction(0))] * max(1, n)
    for k in range(1, n + 1):
        for j in range(k):
            pot = k - 1 - j
            I[pot] = limpio(mx.Add(I[pot], mx.Mul(Q.num(p[k]), y0[j])))
    trace.regla("edo.laplace", f"L: ({_texto_poli(p, 's')})·Y(s) − [{LP._poli_txt(I)}] = F(s)",
                why="L{y⁽ᵏ⁾} = sᵏY(s) − s^(k−1)y(0) − … − y⁽ᵏ⁻¹⁾(0)")
    fracs: list[LP.Fraccion] = []
    if not Q.es_cero(ec.f):
        F = LP.transformada(ec.f_texto, ec.t, trace)
        for fr in F.fracciones:
            if not isinstance(fr.den[0], Fraction):
                raise _no("segundo miembro con exponentes o frecuencias no racionales")
            fracs.append(LP.Fraccion(fr.retardo, fr.num, AL._p_mul(list(fr.den), p)))
        senal = F.señal
    else:
        senal = None
    if any(not Q.es_cero(c) for c in I):
        fracs.append(LP.Fraccion(mx.Num(Fraction(0)), I, list(p)))
    trace.regla("edo.Y", "Y(s) = [F(s) + I(s)]/p(s)",
                why="se despeja la transformada de la solución")
    inv = inversa_fracciones(fracs, ec.t, trace)
    tramos = _por_tramos(inv, ec.t)
    r = PVI(inv, ec.t, tramos, "")
    _verifica_pvi(ec, p, y0, inv, senal, trace)
    trace.regla("edo.solucion", r.texto())
    return r


def inversa_fracciones(fracs: list, t: str, trace: Trace):
    grupos: dict[str, list] = {}
    aproximada = False
    for fr in fracs:
        grupos.setdefault(mx.text(fr.retardo), [fr.retardo, [], []])
        g = grupos[mx.text(fr.retardo)]
        try:
            entera, simples = LP.simples(fr.num, fr.den)
        except UnsupportedError as exc:
            if "grado ≥ 3" not in str(exc) or len(fr.num) >= len(fr.den):
                raise
            g[1] = Q.suma(g[1], LP.inversa_numerica(fr.num, fr.den))
            aproximada = True
            continue
        for f in simples:
            g[1] = Q.suma(g[1], LP.inversa_simple(f))
        for k, c in enumerate(entera):
            if not Q.es_cero(c):
                g[2].append((k, c))
    piezas = sorted(((a, Q.normaliza(c), imp) for a, c, imp in grupos.values()),
                    key=lambda g: float(mx.valor_real(g[0], {})))
    inv = LP.Inversa(piezas, t, aproximada=aproximada)
    if aproximada:
        trace.aviso("edo.numerica", "un factor irreducible de grado ≥ 3: residuos en raíces "
                    "numéricas (coeficientes decimales)")
    trace.regla("edo.inversa", inv.texto().replace("f(t)", "y(t)"),
                why="fracciones simples de cada término e^(−as)·R(s) y la tabla inversa")
    return inv


def _por_tramos(inv, t: str) -> list:
    cortes = sorted({float(mx.valor_real(a, {})) for a, _, _ in inv.piezas} | {0.0})
    textos = {float(mx.valor_real(a, {})): a for a, _, _ in inv.piezas}
    out = []
    for i, c in enumerate(cortes):
        activo: Q.Cuasi = []
        for a, cuasi, _ in inv.piezas:
            av = float(mx.valor_real(a, {}))
            if av <= c + 1e-12:
                activo = Q.suma(activo, Q.desplaza(cuasi, limpio(mx.Neg(a))) if av else cuasi)
        hasta = "+∞" if i + 1 == len(cortes) else mx.text(textos.get(cortes[i + 1],
                                                                     mx.Num(Fraction(0))))
        desde = mx.text(textos.get(c, mx.Num(Fraction(0))))
        out.append((desde, hasta, Q.a_expr(activo, t)))
    return out


def _verifica_pvi(ec, p, y0, inv, senal, trace) -> None:
    """Exacto en cada tramo: Σaₖy⁽ᵏ⁾ = f; condiciones iniciales; saltos en las deltas."""
    cortes = sorted({float(mx.valor_real(a, {})) for a, _, _ in inv.piezas} | {0.0} |
                    ({pnt.x for tr in senal.tramos for pnt in (tr.desde, tr.hasta)
                      if pnt is not None and pnt.x > 0} if senal is not None else set()) |
                    ({i.posicion.x for i in senal.impulsos if i.posicion.x > 0}
                     if senal is not None else set()))

    def activo_en(x: float) -> Q.Cuasi:
        y: Q.Cuasi = []
        for a, cuasi, _ in inv.piezas:
            av = float(mx.valor_real(a, {}))
            if av <= x:
                y = Q.suma(y, Q.desplaza(cuasi, limpio(mx.Neg(a))) if av else cuasi)
        return y

    for i, c in enumerate(cortes):
        medio = c + 0.5 if i + 1 == len(cortes) else (c + cortes[i + 1]) / 2
        y = activo_en(medio)
        lhs = _residuo(p, y)
        f_tramo: Q.Cuasi = []
        if senal is not None:
            for tr in senal.tramos:
                if tr.contiene(medio):
                    f_tramo = Q.suma(f_tramo, Q.leer(tr.expr, ec.t))
        dif = Q.normaliza(Q.suma(lhs, Q.escala(f_tramo, mx.Num(Fraction(-1)))))
        if dif and inv.aproximada:
            vals = [mx.valor_real(Q.a_expr(dif, ec.t), {ec.t: medio + d}) for d in (0, 0.1, 0.2)]
            if all(v is not None and abs(v) < 1e-7 for v in vals):
                dif = []
        if dif:
            raise _error("DISCREPANT", f"la solución no verifica la ecuación en el tramo que "
                         f"empieza en {c:g}")
    # condiciones iniciales (en 0⁺, salvo deltas en 0, que saltan y⁽ⁿ⁻¹⁾)
    y = activo_en(0.0)
    d = y
    salto0 = Fraction(0)
    if senal is not None:
        for imp in senal.impulsos:
            if abs(imp.posicion.x) < 1e-12 and imp.orden == 0:
                salto0 = Fraction(mx.exact_value(imp.area) or 0)
    for j, c in enumerate(y0):
        v = limpio(mx.substitute(Q.a_expr(d, ec.t), ec.t, mx.Num(Fraction(0))))
        esperado = c
        if j == ec.orden - 1 and salto0:
            esperado = limpio(mx.Add(c, Q.num(salto0 / p[-1])))
        dif0 = limpio(mx.Sub(v, esperado))
        if not Q.es_cero(dif0) and not (inv.aproximada and abs(mx.valor_real(dif0, {}) or 1) < 1e-8):
            raise _error("DISCREPANT", f"y^({j})(0) = {mx.text(v)} ≠ {mx.text(esperado)}")
        d = Q.deriva(d)
    trace.verificacion("edo.pvi", f"en cada uno de los {len(cortes)} tramos Σaₖy⁽ᵏ⁾ = f "
                       "exactamente y las condiciones iniciales se cumplen",
                       why="sustitución exacta tramo a tramo (los escalones y las deltas solo "
                           "cambian de tramo)")
    # saltos en las deltas: y⁽ⁿ⁻¹⁾(t₀⁺) − y⁽ⁿ⁻¹⁾(t₀⁻) = A/aₙ
    if senal is not None:
        for imp in senal.impulsos:
            x0 = imp.posicion.x
            if x0 <= 0 or imp.orden:
                continue
            antes, despues = activo_en(x0 - 1e-9), activo_en(x0 + 1e-9)
            for _ in range(ec.orden - 1):
                antes, despues = Q.deriva(antes), Q.deriva(despues)
            va = mx.valor_real(Q.a_expr(antes, ec.t), {ec.t: x0})
            vd = mx.valor_real(Q.a_expr(despues, ec.t), {ec.t: x0})
            esperado = float(mx.valor_real(imp.area, {})) / float(p[-1])
            if va is None or vd is None or abs((vd - va) - esperado) > 1e-9:
                raise _error("DISCREPANT", f"el salto en t = {imp.posicion} no es el de la delta")
        if any(imp.posicion.x > 0 for imp in senal.impulsos):
            trace.verificacion("edo.saltos", "en cada delta A·δ(t − t₀), y⁽ⁿ⁻¹⁾ salta A/aₙ",
                               why="integrar la ecuación a través de t₀")


# ---------------------------------------------------------------------------
# primer orden: lineal, separable, Bernoulli, exacta (con factor integrante), homogénea
# ---------------------------------------------------------------------------


@dataclass
class PrimerOrden:
    tipo: str
    solucion: str            # explícita «y = …» o implícita «Φ(t, y) = C»
    explicita: mx.Expr | None
    implicita: mx.Expr | None
    pasos: list = field(default_factory=list)


def _eq0(e: mx.Expr) -> bool:
    """e ≡ 0 (equivalencia exacta; las variables se igualan sumando las mismas a los
    dos lados, porque el comprobador exige el mismo conjunto de variables)."""
    from academic_core.domain.engineering.mathlab import multiple as MI
    from academic_core.domain.engineering.mathlab import verify as V

    try:
        z = MI._limpio(e)
        if mx.exact_value(z) == 0 and not mx.variables(z):
            return True
        vs = sorted(mx.variables(e))
        if not vs:
            v = mx.valor_real(e, {})
            return v is not None and abs(v) < 1e-13 and mx.exact_value(limpio(e)) == 0
        testigo: mx.Expr = mx.Sym(vs[0])
        for v in vs[1:]:
            testigo = mx.Add(testigo, mx.Sym(v))
        return bool(V.check_equivalence(mx.Add(limpio(e), testigo), testigo)[0])
    except Exception:  # noqa: BLE001
        return False


def _d(e, v):
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    return limpio(DM.differentiate(e, v))


def _prim(e, v):
    from academic_core.domain.engineering.mathlab import integracion as IN
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        return MI._limpio(IN.primitiva(MI._limpio(e), v))
    except Exception as exc:  # noqa: BLE001
        raise _no(f"sin primitiva exacta de {mx.text(e)} en d{v} ({exc})") from None


def _sin_abs(e):
    """ln|t| → ln t dentro de un factor integrante: μ solo importa salvo constante, y en
    cada intervalo donde t no se anula |t| = ±t."""
    if isinstance(e, mx.Call) and e.name == "abs":
        return _sin_abs(e.args[0])
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sin_abs(e.left), _sin_abs(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sin_abs(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sin_abs(e.base), _sin_abs(e.exponent))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_sin_abs(a) for a in e.args))
    return e


def _exp_bonito(e):
    """a/e^u → a·e^(−u); (e^u)^k → e^(k·u); e^(ln u) → u."""
    if isinstance(e, mx.Div):
        a, b = _exp_bonito(e.left), _exp_bonito(e.right)
        if isinstance(b, mx.Call) and b.name == "exp":
            return _exp_bonito(mx.Mul(a, mx.Call("exp", (limpio(mx.Neg(b.args[0])),))))
        return mx.Div(a, b)
    if isinstance(e, mx.Pow):
        b = _exp_bonito(e.base)
        if isinstance(b, mx.Call) and b.name == "exp" and not mx.variables(e.exponent):
            return mx.Call("exp", (limpio(mx.Mul(e.exponent, b.args[0])),))
        return mx.Pow(b, _exp_bonito(e.exponent))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul)):
        return type(e)(_exp_bonito(e.left), _exp_bonito(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_exp_bonito(e.arg))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_exp_bonito(a) for a in e.args))
    return e


def _junta_exp(e):
    """e^a·e^b → e^(a+b) dentro de cada producto."""
    if isinstance(e, mx.Mul):
        fs = []

        def recoge(n):
            if isinstance(n, mx.Mul):
                recoge(n.left)
                recoge(n.right)
            else:
                fs.append(_junta_exp(n))
        recoge(e)
        exps = [f.args[0] for f in fs if isinstance(f, mx.Call) and f.name == "exp"]
        otros = [f for f in fs if not (isinstance(f, mx.Call) and f.name == "exp")]
        if len(exps) > 1:
            arg = exps[0]
            for a in exps[1:]:
                arg = mx.Add(arg, a)
            arg = limpio(arg)
            otros.append(mx.Call("exp", (arg,)) if not Q.es_cero(arg) else mx.Num(Fraction(1)))
        else:
            otros.extend(mx.Call("exp", (a,)) for a in exps)
        r = otros[0]
        for f in otros[1:]:
            r = mx.Mul(r, f)
        return r
    if isinstance(e, (mx.Add, mx.Sub, mx.Div)):
        return type(e)(_junta_exp(e.left), _junta_exp(e.right))
    if isinstance(e, mx.Neg):
        return mx.Neg(_junta_exp(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_junta_exp(e.base), e.exponent)
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_junta_exp(a) for a in e.args))
    return e


def _bonito(e):
    from academic_core.domain.engineering.mathlab import multiple as MI

    try:
        r = MI._limpio(e)
    except Exception:  # noqa: BLE001
        return limpio(e)
    candidatas = [r]
    for f in (lambda x: _exp_bonito(x), lambda x: _junta_exp(LP._expande(_exp_bonito(x)))):
        try:
            candidatas.append(MI._limpio(f(r)))
        except Exception:  # noqa: BLE001
            pass
    return min(candidatas, key=lambda c: len(mx.text(c)))


def primer_orden(texto: str, t: str = "t", y: str = "y", inicial: tuple | None = None,
                 trace: Trace | None = None) -> PrimerOrden:
    """Clasifica y resuelve M(t, y) + N(t, y)·y′ = 0; ``inicial`` = (t₀, y₀)."""
    trace = trace if trace is not None else Trace()
    ec = leer(texto, t, y)
    if ec.orden != 1:
        raise _error("BAD_INPUT", "no es de primer orden")
    Y0, Y1 = _simbolo(0), _simbolo(1)
    N = _d(ec.E, Y1)
    if Y1 in mx.variables(N):
        raise _no("la ecuación no es lineal en y′ (no se puede escribir y′ = F(t, y))")
    M = limpio(mx.substitute(ec.E, Y1, mx.Num(Fraction(0))))
    Ys = mx.Sym(y)
    M = limpio(mx.substitute(M, Y0, Ys))
    N = limpio(mx.substitute(N, Y0, Ys))
    F = _bonito(mx.Neg(mx.Div(M, N)))
    trace.regla("edo1.forma", f"y′ = F({t}, {y}) = {mx.text(F)}; M = {mx.text(M)}, "
                f"N = {mx.text(N)}", why="M + N·y′ = 0")
    for metodo in (_lineal1, _separable, _bernoulli, _exacta, _homogenea):
        r = metodo(F, M, N, t, y, trace)
        if r is not None:
            break
    else:
        raise _no("no es separable, lineal, de Bernoulli, exacta (ni con factor integrante "
                  "μ(t) o μ(y)) ni homogénea")
    if inicial is not None:
        r = _con_inicial(r, t, y, inicial, trace)
    _verifica1(r, F, t, y, trace)
    return r


def _lineal1(F, M, N, t, y, trace):
    dF = _d(F, y)
    if mx.depends(_bonito(dF), y) and not _eq0(_d(dF, y)):
        return None
    if mx.depends(_bonito(dF), y):
        return None
    P = _bonito(mx.Neg(dF))
    q = _bonito(mx.substitute(F, y, mx.Num(Fraction(0))))
    if not mx.depends(q, t) and not mx.depends(P, t) and False:
        return None
    if Q.es_cero(P) if not mx.variables(P) else False:
        sol = _bonito(mx.Add(_prim(q, t), mx.Sym("C")))
        trace.regla("edo1.integral", f"y′ = {mx.text(q)} ⇒ y = {mx.text(sol)}")
        return PrimerOrden("integración directa", f"y = {mx.text(sol)}", sol, None)
    mu = _sin_abs(_bonito(mx.Call("exp", (_sin_abs(_prim(P, t)),))))
    trace.regla("edo1.lineal", f"y′ + ({mx.text(P)})·y = {mx.text(q)}: μ = e^(∫P) = {mx.text(mu)}",
                why="lineal de primer orden: (μ·y)′ = μ·q con el factor integrante μ")
    integral = _prim(mx.Mul(mu, q), t) if not Q.es_cero(q) else mx.Num(Fraction(0))
    sol = _bonito(mx.Div(mx.Add(integral, mx.Sym("C")), mu))
    trace.regla("edo1.solucion", f"y = (∫μq dt + C)/μ = {mx.text(sol)}")
    return PrimerOrden("lineal", f"y = {mx.text(sol)}", sol, None)


def _separable(F, M, N, t, y, trace):
    from academic_core.domain.engineering.mathlab import multiple as MI

    if Q.es_cero(F) if not mx.variables(F) else False:
        return None
    try:
        # F = g(t)·h(y) ⇔ F·F_ty − F_t·F_y ≡ 0 (∂²ln|F|/∂t∂y = 0 sin logaritmos)
        cruzada = mx.Sub(mx.Mul(F, _d(_d(F, t), y)), mx.Mul(_d(F, t), _d(F, y)))
    except Exception:  # noqa: BLE001
        return None
    if not _eq0(cruzada):
        return None
    # F = g(t)·h(y): h(y) = F(t₀, y), g(t) = F/h
    for t0 in (Fraction(0), Fraction(1), Fraction(2), Fraction(1, 2)):
        try:
            h = _bonito(mx.substitute(F, t, Q.num(t0)))
        except Exception:  # noqa: BLE001
            continue
        if Q.es_cero(h) if not mx.variables(h) else False:
            continue
        if any(mx.valor_real(h, {y: z}) is None for z in (0.37, 1.3)):
            continue        # F(t₀, y) no está definida (t₀ = 0 en 1/t)
        try:
            g = _bonito(mx.Div(F, h))
            dg = _d(g, y)
        except Exception:  # noqa: BLE001
            continue
        if not mx.depends(MI._limpio(g), y) or _eq0(dg):
            g = _bonito(mx.substitute(g, y, mx.Num(Fraction(1, 3)))) if mx.depends(g, y) else g
            break
    else:
        return None
    trace.regla("edo1.separable", f"y′ = ({mx.text(g)})·({mx.text(h)})",
                why="∂²(ln|F|)/∂t∂y = 0: F separa en g(t)·h(y)")
    H = _prim(mx.Div(mx.Num(Fraction(1)), h), y)
    G = _prim(g, t)
    trace.regla("edo1.integra", f"∫dy/h(y) = ∫g(t)dt: {mx.text(H)} = {mx.text(G)} + C",
                why="separando variables (h(y) ≠ 0; los ceros de h son soluciones constantes)")
    explicita = _despeja(H, G, y)
    ceros = _ceros_h(h, y)
    pasos = [f"soluciones constantes: y = {', '.join(ceros)}"] if ceros else []
    if pasos:
        trace.regla("edo1.equilibrios", pasos[0], why="h(y) = 0 anula y′")
    if explicita is not None:
        return PrimerOrden("separable", f"y = {mx.text(explicita)}", explicita, None, pasos)
    imp = _bonito(mx.Sub(H, G))
    return PrimerOrden("separable", f"{mx.text(imp)} = C", None, imp, pasos)


def _nodos(e):
    yield e
    for h in ("left", "right", "arg", "base", "exponent", "radicand"):
        c = getattr(e, h, None)
        if isinstance(c, mx.Expr):
            yield from _nodos(c)
    for a in getattr(e, "args", ()) or ():
        if isinstance(a, mx.Expr):
            yield from _nodos(a)


def _exp_de_logs(H):
    """e^H con H = Σ cᵢ·ln uᵢ + resto: Π uᵢ^cᵢ·e^resto."""
    if isinstance(H, mx.Add):
        return mx.Mul(_exp_de_logs(H.left), _exp_de_logs(H.right))
    if isinstance(H, mx.Sub):
        return mx.Div(_exp_de_logs(H.left), _exp_de_logs(H.right))
    if isinstance(H, mx.Neg):
        return mx.Div(mx.Num(Fraction(1)), _exp_de_logs(H.arg))
    if isinstance(H, mx.Call) and H.name == "ln":
        return H.args[0]
    if isinstance(H, mx.Mul) and not mx.variables(H.left) and isinstance(H.right, mx.Call) \
            and H.right.name == "ln":
        return mx.Pow(H.right.args[0], H.left)
    return mx.Call("exp", (H,))


def _ceros_h(h, y) -> list[str]:
    from academic_core.domain.engineering.mathlab import raices as RZ

    try:
        c = RZ.ceros(h, y)
    except Exception:  # noqa: BLE001
        return []
    return [mx.text(r.valor) for r in c.raices if r.exacta][:6]


def _despeja(H: mx.Expr, G: mx.Expr, y: str) -> mx.Expr | None:
    """H(y) = G(t) + C → y explícita en los casos de clase (ln|y|, 1/y, yⁿ, lineal)."""
    C = mx.Sym("C")
    K = mx.Sym("K")
    Hs = limpio(H)
    # ln|y| (o ln y) + c₀ = G + C  →  y = K·e^G
    if isinstance(Hs, mx.Call) and Hs.name == "ln":
        arg = Hs.args[0]
        if isinstance(arg, mx.Call) and arg.name == "abs":
            arg = arg.args[0]
        lin = Q._lineal(arg, y)
        if lin is not None and not Q.es_cero(lin[0]):
            m, c = lin
            return _bonito(mx.Div(mx.Sub(mx.Mul(K, mx.Call("exp", (G,))), c), m))
    lin = Q._lineal(Hs, y)
    if lin is not None and not Q.es_cero(lin[0]):
        m, c = lin
        return _bonito(mx.Div(mx.Sub(mx.Add(G, C), c), m))
    # a·y^k + b = G + C
    try:
        from academic_core.domain.engineering.mathlab import poly as P

        p = P.as_poly(Hs)
        if len(p) == 1:
            (mono, coef), = p.items()
            if len(mono) == 1 and mono[0][0] == y:
                k = mono[0][1]
                if k == -1:
                    return _bonito(mx.Div(mx.Num(coef), mx.Add(G, C)))
    except Exception:  # noqa: BLE001
        pass
    # suma de logaritmos: e^H = (a·y + b)/(c·y + d) = K·e^G  →  y despejada
    if any(isinstance(n, mx.Call) and n.name == "ln" for n in _nodos(Hs)):
        from academic_core.domain.engineering.mathlab import multiple as MI
        from academic_core.domain.engineering.mathlab import poly as P

        try:
            R = MI._racional(MI._limpio(_exp_de_logs(_sin_abs(Hs))))
            num, den = (R.left, R.right) if isinstance(R, mx.Div) else (R, mx.Num(Fraction(1)))
            ln_ = Q._lineal(num, y)
            ld = Q._lineal(den, y)
        except Exception:  # noqa: BLE001
            ln_ = ld = None
        if ln_ is not None and ld is not None and not (mx.variables(R) - {y}):
            (a, b), (c, d) = ln_, ld
            E_ = mx.Mul(K, mx.Call("exp", (G,)))
            sol = _bonito(mx.Div(mx.Sub(mx.Mul(E_, d), b), mx.Sub(a, mx.Mul(E_, c))))
            if mx.depends(sol, y):
                return None
            return sol
        _ = P
    if isinstance(Hs, (mx.Div, mx.Neg, mx.Mul)):
        # −1/y = G + C
        inv = _bonito(mx.Div(mx.Num(Fraction(1)), Hs))
        lin = Q._lineal(inv, y)
        if lin is not None and not Q.es_cero(lin[0]):
            m, c = lin
            return _bonito(mx.Div(mx.Sub(mx.Div(mx.Num(Fraction(1)), mx.Add(G, C)), c), m))
    return None


def _bernoulli(F, M, N, t, y, trace):
    from academic_core.domain.engineering.mathlab import multiple as MI

    exps = set()
    for n in MI._nodos(F):
        if isinstance(n, mx.Pow) and n.base == mx.Sym(y):
            k = mx.exact_value(n.exponent)
            if k is not None and k not in (0, 1):
                exps.add(Fraction(k))
        if isinstance(n, mx.Root) and n.radicand == mx.Sym(y):
            exps.add(Fraction(1, n.degree))
    for n_ in sorted(exps):
        # F = A(t)·y + B(t)·yⁿ: A y B de F(t,1) = A + B, F(t,2) = 2A + 2ⁿB
        f1 = mx.substitute(F, y, mx.Num(Fraction(1)))
        f2 = mx.substitute(F, y, mx.Num(Fraction(2)))
        dosn = mx.Pow(mx.Num(Fraction(2)), Q.num(n_))
        B = _bonito(mx.Div(mx.Sub(f2, mx.Mul(mx.Num(2), f1)), mx.Sub(dosn, mx.Num(2))))
        A = _bonito(mx.Sub(f1, B))
        recon = mx.Add(mx.Mul(A, mx.Sym(y)), mx.Mul(B, mx.Pow(mx.Sym(y), Q.num(n_))))
        if mx.depends(A, y) or mx.depends(B, y) or not _eq0(mx.Sub(recon, F)):
            continue
        uno_n = 1 - n_
        trace.regla("edo1.bernoulli", f"y′ = ({mx.text(A)})·y + ({mx.text(B)})·y^{n_}: "
                    f"v = y^{uno_n}", why="Bernoulli: v = y^(1−n) la convierte en lineal "
                    f"v′ = (1−n)·A·v + (1−n)·B")
        P = _bonito(mx.Mul(Q.num(-uno_n), A))
        q = _bonito(mx.Mul(Q.num(uno_n), B))
        mu = _sin_abs(_bonito(mx.Call("exp", (_sin_abs(_prim(P, t)),))))
        v = _bonito(mx.Div(mx.Add(_prim(mx.Mul(mu, q), t), mx.Sym("C")), mu))
        trace.regla("edo1.bernoulli_v", f"v = {mx.text(v)}")
        sol = _bonito(mx.Pow(v, Q.num(Fraction(1) / uno_n)))
        extra = ["y = 0 también es solución"] if n_ > 0 else []
        return PrimerOrden("Bernoulli", f"y = {mx.text(sol)}", sol, None, extra)
    return None


def _exacta(F, M, N, t, y, trace):
    My, Nt = _d(M, y), _d(N, t)
    mu = None
    if not _eq0(mx.Sub(My, Nt)):
        r1 = _bonito(mx.Div(mx.Sub(My, Nt), N))
        r2 = _bonito(mx.Div(mx.Sub(Nt, My), M))
        if not mx.depends(r1, y) or _eq0(_d(r1, y)):
            r1 = _bonito(mx.substitute(r1, y, mx.Num(Fraction(1, 3)))) if mx.depends(r1, y) else r1
            mu = _sin_abs(_bonito(mx.Call("exp", (_sin_abs(_prim(r1, t)),))))
            trace.regla("edo1.mu", f"(M_y − N_t)/N = {mx.text(r1)} solo depende de {t}: "
                        f"μ({t}) = {mx.text(mu)}", why="factor integrante μ(t)")
        elif not mx.depends(r2, t) or _eq0(_d(r2, t)):
            r2 = _bonito(mx.substitute(r2, t, mx.Num(Fraction(1, 3)))) if mx.depends(r2, t) else r2
            mu = _sin_abs(_bonito(mx.Call("exp", (_sin_abs(_prim(r2, y)),))))
            trace.regla("edo1.mu", f"(N_t − M_y)/M = {mx.text(r2)} solo depende de {y}: "
                        f"μ({y}) = {mx.text(mu)}", why="factor integrante μ(y)")
        else:
            return None
        M, N = _bonito(mx.Mul(mu, M)), _bonito(mx.Mul(mu, N))
        if not _eq0(mx.Sub(_d(M, y), _d(N, t))):
            return None
    trace.regla("edo1.exacta", f"M_y = N_t = {mx.text(_bonito(_d(M, y)))}",
                why="la forma M dt + N dy es exacta: es dΦ")
    phi_t = _prim(M, t)
    resto = _bonito(mx.Sub(N, _d(phi_t, y)))
    if mx.depends(resto, t) and not _eq0(_d(resto, t)):
        return None
    if mx.depends(resto, t):
        resto = _bonito(mx.substitute(resto, t, mx.Num(Fraction(1, 3))))
    phi = _bonito(mx.Add(phi_t, _prim(resto, y) if not Q.es_cero(resto) else mx.Num(0)))
    trace.regla("edo1.potencial", f"Φ = ∫M dt + h({y}) = {mx.text(phi)}",
                why="h′(y) = N − ∂/∂y∫M dt")
    tipo = "exacta" if mu is None else "exacta con factor integrante"
    return PrimerOrden(tipo, f"{mx.text(phi)} = C", None, phi)


def _homogenea(F, M, N, t, y, trace):
    lam = mx.Sym("lam__")
    escalada = mx.substitute(mx.substitute(F, t, mx.Mul(lam, mx.Sym(t))), y,
                             mx.Mul(lam, mx.Sym(y)))
    if not _eq0(mx.Sub(escalada, F)):
        return None
    v = mx.Sym("v")
    G = _bonito(mx.substitute(mx.substitute(F, y, v), t, mx.Num(Fraction(1))))
    trace.regla("edo1.homogenea", f"F(λt, λy) = F(t, y): y = t·v, t·v′ = {mx.text(G)} − v",
                why="homogénea de grado 0: el cambio y = t·v separa variables")
    den = _bonito(mx.Sub(G, v))
    if Q.es_cero(den) if not mx.variables(den) else False:
        return None
    H = _prim(mx.Div(mx.Num(Fraction(1)), den), "v")
    imp = _bonito(mx.Sub(mx.substitute(H, "v", mx.Div(mx.Sym(y), mx.Sym(t))),
                         mx.Call("ln", (mx.Call("abs", (mx.Sym(t),)),))))
    return PrimerOrden("homogénea", f"{mx.text(imp)} = C", None, imp)


def _con_inicial(r: PrimerOrden, t, y, inicial, trace) -> PrimerOrden:
    t0, y0 = (mx.parse(str(inicial[0])), mx.parse(str(inicial[1])))
    if r.explicita is not None:
        e = r.explicita
        cte = "C" if "C" in mx.variables(e) else "K" if "K" in mx.variables(e) else None
        if cte is None:
            return r
        from academic_core.domain.engineering.mathlab import ecuacion_general as EG

        ecu = _bonito(mx.Sub(mx.substitute(e, t, t0), y0))
        try:
            sols = EG.resolver(ecu, cte).soluciones
        except Exception as exc:  # noqa: BLE001
            raise _no(f"no se despeja {cte} de la condición inicial ({exc})") from None
        sols = [s_ for s_ in sols if s_.exacta is not None]
        if not sols:
            raise _no(f"la condición inicial no fija {cte}")
        valor = sols[0].exacta
        sol = _bonito(mx.substitute(e, cte, valor))
        trace.regla("edo1.pvi", f"{y}({mx.text(t0)}) = {mx.text(y0)} ⇒ {cte} = {mx.text(valor)}")
        return PrimerOrden(r.tipo, f"y = {mx.text(sol)}", sol, None, r.pasos)
    phi0 = _bonito(mx.substitute(mx.substitute(r.implicita, t, t0), y, y0))
    trace.regla("edo1.pvi", f"Φ({mx.text(t0)}, {mx.text(y0)}) = {mx.text(phi0)} = C")
    return PrimerOrden(r.tipo, f"{mx.text(r.implicita)} = {mx.text(phi0)}", None,
                       r.implicita, r.pasos)


def _verifica1(r: PrimerOrden, F, t, y, trace) -> None:
    if r.explicita is not None:
        sol = r.explicita
        res = mx.Sub(_d(sol, t), mx.substitute(F, y, sol))
        if not _eq0(res):
            _verifica_puntos(res, t, sol)
        trace.verificacion("edo1.sustitucion", "y′ − F(t, y) = 0 con la solución sustituida",
                           why="definición de solución")
        return
    phi = r.implicita
    res = mx.Add(_d(phi, t), mx.Mul(_d(phi, y), F))
    if not _eq0(res):
        _verifica_puntos(res, t, None, y)
    trace.verificacion("edo1.implicita", "dΦ/dt = Φ_t + Φ_y·F = 0: Φ es constante sobre las "
                       "soluciones", why="derivada de la solución implícita")


def _verifica_puntos(res, t, sol, y=None) -> None:
    """Último recurso: el residuo se anula en puntos (constantes C, K = valores)."""
    env_base = {"C": 0.7, "K": 1.3}
    malos = 0
    probados = 0
    for tv in (0.35, 0.8, 1.6):
        for yv in ((0.5, 1.2) if y else (None,)):
            env = dict(env_base)
            env[t] = tv
            if y:
                env[y] = yv
            v = mx.valor_real(res, env)
            if v is None:
                continue
            probados += 1
            if abs(v) > 1e-8:
                malos += 1
    if malos or not probados:
        raise _error("DISCREPANT", "la solución no verifica la ecuación")


# ---------------------------------------------------------------------------
# sistemas lineales x′ = A·x + f(t): e^{At} = L⁻¹{(sI − A)⁻¹} y plano de fases
# ---------------------------------------------------------------------------


@dataclass
class SistemaEDO:
    n: int
    exponencial: list            # Φ(t) = e^{At}: matriz de cuasipolinomios
    solucion: list | None        # x(t) por componentes (texto) si hay condiciones
    autovalores: str
    fases: str                   # clasificación (2×2)
    t: str = "t"

    def texto(self) -> str:
        filas = "; ".join(", ".join(mx.text(Q.a_expr(c, self.t)) for c in fila)
                          for fila in self.exponencial)
        t = f"e^(At) = [{filas}]"
        if self.solucion is not None:
            t += "; x(t) = (" + ", ".join(self.solucion) + ")"
        t += f"; {self.autovalores}"
        if self.fases:
            t += f"; {self.fases}"
        return t


def _leverrier(A: list[list[Fraction]]):
    """p(s) = det(sI − A) y B₀…B_{n−1} con (sI − A)⁻¹ = Σ Bₖ s^{n−1−k}/p(s)."""
    n = len(A)
    I = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    B = [I]
    c = [Fraction(1)]
    M = I
    for k in range(1, n + 1):
        AM = [[sum(A[i][r] * M[r][j] for r in range(n)) for j in range(n)] for i in range(n)]
        ck = -sum(AM[i][i] for i in range(n)) / k
        c.append(ck)
        M = [[AM[i][j] + (ck if i == j else 0) for j in range(n)] for i in range(n)]
        if k < n:
            B.append(M)
    # p(s) = s^n + c₁s^{n−1} + … + cₙ  (coeficientes de grado bajo a alto)
    p = list(reversed(c))
    return p, B


def clasifica_fases(A: list[list[Fraction]]) -> str:
    """Plano de fases de x′ = A·x (2×2) por traza y determinante."""
    (a, b), (c, d) = A
    tr, det = a + d, a * d - b * c
    disc = tr * tr - 4 * det
    if det < 0:
        return "punto de silla (inestable): autovalores reales de signos opuestos"
    if det == 0:
        return ("todos los puntos son de equilibrio (A = 0)" if a == b == c == d == 0 else
                "recta de puntos de equilibrio (det A = 0): degenerado")
    estab = "estable" if tr < 0 else "inestable" if tr > 0 else ""
    if disc > 0:
        return f"nodo {estab} (autovalores reales distintos del mismo signo)"
    if disc == 0:
        if b == 0 and c == 0:
            return f"nodo estrella {estab} (A = λI: todas las direcciones son propias)"
        return f"nodo impropio (degenerado) {estab}: autovalor doble con un solo autovector"
    giro = "antihorario" if c > 0 else "horario"
    if tr == 0:
        return f"centro (estable, no asintóticamente): órbitas cerradas, giro {giro}"
    return f"foco (espiral) {estab}, giro {giro}"


def sistema(A, x0=None, f=None, t: str = "t", trace: Trace | None = None) -> SistemaEDO:
    """x′ = A·x + f(t) con A racional n×n; x0 (opcional) = x(0); f = lista de textos."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    A = [[Fraction(mx.exact_value(mx.parse(str(v))) if isinstance(v, str) else v)
          for v in fila] for fila in A]
    n = len(A)
    if n < 1 or any(len(fila) != n for fila in A) or n > 5:
        raise _error("BAD_INPUT", "A tiene que ser cuadrada (hasta 5×5)")
    p, B = _leverrier(A)
    trace.regla("sistema.caracteristico", f"det(sI − A) = {_texto_poli(p, 's')}",
                why="Faddeev-LeVerrier: (sI − A)⁻¹ = Σ Bₖ·s^(n−1−k)/det(sI − A), exacto")
    try:
        desc = AL.descomponer(A, Trace())
        auto = desc.texto()
    except Exception as exc:  # noqa: BLE001
        auto = f"autovalores: {exc}"
    Phi = []
    for i in range(n):
        fila = []
        for j in range(n):
            num = [Fraction(0)] * n
            for k in range(n):
                num[n - 1 - k] = B[k][i][j]
            _, simples = LP.simples([Q.num(c) for c in num], p)
            g: Q.Cuasi = []
            for s_ in simples:
                g = Q.suma(g, LP.inversa_simple(s_))
            fila.append(g)
        Phi.append(fila)
    # comprobación exacta: Φ′ = A·Φ y Φ(0) = I
    for i in range(n):
        for j in range(n):
            lado = Q.deriva(Phi[i][j])
            otro: Q.Cuasi = []
            for r in range(n):
                if A[i][r]:
                    otro = Q.suma(otro, Q.escala(Phi[r][j], Q.num(A[i][r])))
            if Q.normaliza(Q.suma(lado, Q.escala(otro, mx.Num(-1)))):
                raise _error("DISCREPANT", "Φ′ ≠ A·Φ")
            v0 = limpio(mx.substitute(Q.a_expr(Phi[i][j], t), t, mx.Num(Fraction(0))))
            if not Q.es_cero(limpio(mx.Sub(v0, mx.Num(Fraction(int(i == j)))))):
                raise _error("DISCREPANT", "Φ(0) ≠ I")
    trace.verificacion("sistema.exponencial", "Φ′ = A·Φ y Φ(0) = I comprobados exactamente",
                       why="e^(At) es la única matriz fundamental con Φ(0) = I")
    trace.regla("sistema.eAt", "e^(At) = L⁻¹{(sI − A)⁻¹} por fracciones simples de cada entrada",
                why="L{e^(At)} = (sI − A)⁻¹")
    solucion = None
    if x0 is not None or f is not None:
        x0v = [mx.parse(str(v)) for v in (x0 or ["0"] * n)]
        fracs_por_comp = [[] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                num = [Fraction(0)] * n
                for k in range(n):
                    num[n - 1 - k] = B[k][i][j]
                if not Q.es_cero(x0v[j]):
                    fracs_por_comp[i].append(LP.Fraccion(
                        mx.Num(Fraction(0)), [limpio(mx.Mul(Q.num(c), x0v[j])) for c in num], p))
                if f is not None and str(f[j]).strip() not in ("0", ""):
                    Fj = LP.transformada(str(f[j]), t, Trace())
                    for fr in Fj.fracciones:
                        if not isinstance(fr.den[0], Fraction):
                            raise _no("término forzante con exponentes no racionales")
                        fracs_por_comp[i].append(LP.Fraccion(
                            fr.retardo, LP._p_mul(fr.num, [Q.num(c) for c in num]),
                            AL._p_mul(list(fr.den), p)))
        solucion = []
        for i in range(n):
            if not fracs_por_comp[i]:
                solucion.append("0")
                continue
            inv = inversa_fracciones(fracs_por_comp[i], t, Trace())
            solucion.append(inv.texto().replace("f(t) = ", "").replace(" (t ≥ 0)", ""))
        trace.regla("sistema.solucion", "x(t) = L⁻¹{(sI − A)⁻¹·(x(0) + F(s))} = (" +
                    ", ".join(solucion) + ")", why="transformando x′ = Ax + f")
    fases = clasifica_fases(A) if n == 2 else ""
    if fases:
        trace.regla("sistema.fases", fases,
                    why="traza, determinante y discriminante de A clasifican el origen")
    return SistemaEDO(n, Phi, solucion, auto, fases, t)


# ---------------------------------------------------------------------------
# oscilador amortiguado y forzado (factor Q)
# ---------------------------------------------------------------------------


@dataclass
class Oscilador:
    w0: mx.Expr
    gamma: mx.Expr
    Q: mx.Expr | None
    regimen: str
    wd: mx.Expr | None
    resonancia: str
    respuesta: str

    def texto(self) -> str:
        partes = [f"ω₀ = {mx.text(self.w0)}", f"γ = b/(2m) = {mx.text(self.gamma)}",
                  "Q = ∞ (sin amortiguamiento)" if self.Q is None else
                  f"Q = ω₀/(2γ) = {mx.text(self.Q)}", self.regimen]
        if self.wd is not None:
            partes.append(f"ω_d = √(ω₀² − γ²) = {mx.text(self.wd)}")
        partes.append(self.resonancia)
        if self.respuesta:
            partes.append(self.respuesta)
        return "; ".join(partes)


def oscilador(m, b, k, F: str | None = None, x0=None, v0=None, t: str = "t",
              trace: Trace | None = None) -> Oscilador:
    """m·x″ + b·x′ + k·x = F(t) (m, k > 0, b ≥ 0)."""
    from academic_core.domain.engineering.mathlab import multiple as MI

    trace = trace if trace is not None else Trace()
    m, b, k = (mx.parse(mx.normaliza_entrada(str(v))) for v in (m, b, k))
    w02 = MI._limpio(mx.Div(k, m))
    w0 = MI._limpio(mx.Root(2, w02))
    gamma = MI._limpio(mx.Div(b, mx.Mul(mx.Num(2), m)))
    gv, wv = mx.valor_real(gamma, {}), mx.valor_real(w0, {})
    if gv is None or wv is None or wv <= 0 or gv < 0:
        raise _error("BAD_INPUT", "hace falta m, k > 0 y b ≥ 0 numéricos")
    Qf = None if Q.es_cero(gamma) else MI._limpio(mx.Div(w0, mx.Mul(mx.Num(2), gamma)))
    disc = MI._limpio(mx.Sub(mx.Pow(gamma, mx.Num(2)), w02))
    dv = mx.valor_real(disc, {})
    wd = None
    if Q.es_cero(gamma):
        regimen = "sin amortiguamiento: oscilación armónica x = A·cos(ω₀t) + B·sen(ω₀t)"
        wd = w0
    elif abs(dv) < 1e-14 and Q.es_cero(disc):
        regimen = "amortiguamiento crítico (γ = ω₀, Q = 1/2): x = (A + Bt)·e^(−γt)"
    elif dv > 0:
        r = MI._limpio(mx.Root(2, disc))
        regimen = (f"sobreamortiguado (γ > ω₀, Q < 1/2): x = A·e^(({mx.text(MI._limpio(mx.Sub(r, gamma)))})t)"
                   f" + B·e^(({mx.text(MI._limpio(mx.Neg(mx.Add(r, gamma))))})t)")
    else:
        wd = MI._limpio(mx.Root(2, mx.Neg(disc)))
        regimen = (f"subamortiguado (γ < ω₀, Q > 1/2): x = e^(−γt)·(A·cos(ω_d·t) + "
                   "B·sen(ω_d·t))")
    trace.regla("oscilador.parametros", f"x″ + 2γx′ + ω₀²x = F/m con ω₀ = √(k/m) = {mx.text(w0)}, "
                f"γ = {mx.text(gamma)}" + ("" if Qf is None else f", Q = {mx.text(Qf)}"),
                why="la forma normal del oscilador; el régimen lo decide γ frente a ω₀")
    trace.regla("oscilador.regimen", regimen, why="raíces −γ ± √(γ² − ω₀²) del característico")
    # resonancia en amplitud con F = F₀·cos(ωt): A(ω) = (F₀/m)/√((ω₀² − ω²)² + (2γω)²)
    if Qf is None:
        reson = "resonancia: amplitud ilimitada en ω = ω₀ (sin amortiguamiento)"
    else:
        wr2 = MI._limpio(mx.Sub(w02, mx.Mul(mx.Num(2), mx.Pow(gamma, mx.Num(2)))))
        wr2v = mx.valor_real(wr2, {})
        ancho = MI._limpio(mx.Mul(mx.Num(2), gamma))
        if wr2v is not None and wr2v > 0:
            wr = MI._limpio(mx.Root(2, wr2))
            amax = MI._limpio(mx.Div(mx.Num(1), mx.Mul(mx.Mul(mx.Num(2), mx.Mul(m, gamma)), wd)))
            reson = (f"con F = F₀cos(ωt): A(ω) = (F₀/m)/√((ω₀² − ω²)² + (2γω)²); máximo en "
                     f"ω_r = √(ω₀² − 2γ²) = {mx.text(wr)} con A_max = F₀·{mx.text(amax)}; "
                     f"ancho de banda (potencia mitad) Δω = 2γ = ω₀/Q = {mx.text(ancho)}")
            _verifica_resonancia(float(mx.valor_real(w0, {})), float(gv), float(mx.valor_real(wr, {})),
                                 float(mx.valor_real(amax, {})), float(mx.valor_real(m, {})), trace)
        else:
            reson = ("con F = F₀cos(ωt): A(ω) decrece desde ω = 0 (Q ≤ 1/√2: no hay pico de "
                     f"resonancia); ancho de banda Δω = 2γ = {mx.text(ancho)}")
    trace.regla("oscilador.resonancia", reson,
                why="dA/dω = 0 ⇔ ω² = ω₀² − 2γ²; la potencia absorbida cae a la mitad en "
                    "ω₀ ± γ (exacto para la potencia), luego Δω = 2γ")
    respuesta = ""
    if F is not None or x0 is not None:
        texto = f"{mx.text(m)}*x''+{mx.text(b)}*x'+{mx.text(k)}*x={F or '0'}"
        ec = leer(texto, t, "x")
        ini = [x0 if x0 is not None else "0", v0 if v0 is not None else "0"]
        sol = pvi_laplace(ec, ini, trace)
        respuesta = sol.texto().replace("y(t)", "x(t)")
    return Oscilador(w0, gamma, Qf, regimen, wd, reson, respuesta)


def _verifica_resonancia(w0, g, wr, amax, m, trace) -> None:
    def A(w):
        return (1 / m) / math.sqrt((w0 ** 2 - w ** 2) ** 2 + (2 * g * w) ** 2)
    h = 1e-5 * max(1.0, wr)
    if not (A(wr) >= A(wr - h) and A(wr) >= A(wr + h)) or abs(A(wr) - amax) > 1e-9 * amax:
        raise _error("DISCREPANT", "la frecuencia de resonancia no da el máximo de A(ω)")
    trace.verificacion("oscilador.resonancia", f"A(ω_r) = {A(wr):.10g} es máximo local y "
                       "coincide con A_max", why="evaluación directa de A(ω) a ambos lados")


# ---------------------------------------------------------------------------
# respuesta impulsional, convolución, ecuaciones integrales e integro-diferenciales
# ---------------------------------------------------------------------------


def respuesta_impulsional(ecuacion: str, t: str = "t", trace: Trace | None = None):
    """h(t) = L⁻¹{1/p(s)} (condiciones nulas, entrada δ)."""
    trace = trace if trace is not None else Trace()
    ec = leer(ecuacion.split("=")[0] + "= 0", t)
    p = _coefs_q(ec)
    inv = inversa_fracciones([LP.Fraccion(mx.Num(Fraction(0)), [mx.Num(Fraction(1))], p)], t, trace)
    trace.regla("edo.h", f"H(s) = 1/({_texto_poli(p, 's')}), " + inv.texto().replace("f(t)", "h(t)"),
                why="respuesta a δ con condiciones nulas: Y = 1·H(s)")
    return inv


def convolucion(f: str, g: str, t: str = "t", trace: Trace | None = None):
    """(f * g)(t) = ∫₀ᵗ f(τ)g(t − τ)dτ = L⁻¹{F·G}."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    F = LP.transformada(f, t, Trace())
    G = LP.transformada(g, t, Trace())
    fracs = []
    for a in F.fracciones:
        for b in G.fracciones:
            if not isinstance(a.den[0], Fraction) or not isinstance(b.den[0], Fraction):
                raise _no("exponentes o frecuencias no racionales")
            fracs.append(LP.Fraccion(limpio(mx.Add(a.retardo, b.retardo)),
                                     LP._p_mul(a.num, b.num), AL._p_mul(list(a.den), list(b.den))))
    trace.regla("conv.laplace", "L{f * g} = F(s)·G(s)", why="teorema de convolución")
    inv = inversa_fracciones(fracs, t, trace)
    _verifica_convolucion(F.señal, G.señal, inv, trace)
    return inv


def _valor_inv(inv, x: float) -> float:
    total = 0.0
    for a, cuasi, _ in inv.piezas:
        av = float(mx.valor_real(a, {}))
        if x >= av:
            v = mx.valor_real(Q.a_expr(cuasi, inv.t), {inv.t: x - av})
            total += float(v) if v is not None else 0.0
    return total


def _verifica_convolucion(Df, Dg, inv, trace) -> None:
    if Df.impulsos or Dg.impulsos:
        trace.verificacion("conv.ida_vuelta", "comprobada por la transformada (hay deltas)")
        return
    peor = 0.0
    bf = [p.x for tr in Df.tramos for p in (tr.desde, tr.hasta) if p is not None]
    bg = [p.x for tr in Dg.tramos for p in (tr.desde, tr.hasta) if p is not None]
    for x in (0.7, 1.9, 3.3):
        cortes = sorted({0.0, x} | {c for c in bf if 0 < c < x} | {x - c for c in bg if 0 < x - c < x})
        num = sum(LP._cuadratura(lambda tau: LP.valor_senal(Df, tau) * LP.valor_senal(Dg, x - tau),
                                 a, b) for a, b in zip(cortes, cortes[1:]))
        peor = max(peor, abs(num - _valor_inv(inv, x)))
    if peor > 1e-7:
        raise _error("DISCREPANT", f"convolución frente a cuadratura: {peor:.3g}")
    trace.verificacion("conv.cuadratura", f"∫₀ᵗf(τ)g(t−τ)dτ por cuadratura en 3 instantes "
                       f"(desviación {peor:.2g})", why="la definición")


def volterra(f: str, k: str, lam="1", t: str = "t", trace: Trace | None = None):
    """y(t) = f(t) + λ∫₀ᵗ k(t − τ)y(τ)dτ ⇒ Y = F/(1 − λK)."""
    trace = trace if trace is not None else Trace()
    F = LP.transformada(f, t, Trace())
    K = LP.transformada(k, t, Trace())
    if any(not Q.es_cero(fr.retardo) for fr in K.fracciones):
        raise _no("núcleo con retardos")
    lam_e = mx.parse(mx.normaliza_entrada(str(lam)))
    Ke = K.expr()
    Y = mx.Div(F.expr(), mx.Sub(mx.Num(Fraction(1)), mx.Mul(lam_e, Ke)))
    trace.regla("volterra.laplace", f"Y(s) = F(s)/(1 − λK(s)) con K(s) = {mx.text(Ke)}",
                why="la integral es una convolución: L{k * y} = K·Y")
    inv = LP.inversa(LP._racional(Y) if not any(not Q.es_cero(fr.retardo) for fr in F.fracciones)
                     else Y, "s", t, trace)
    # comprobación: la ecuación integral en puntos
    peor = 0.0
    for x in (0.6, 1.4, 2.5):
        integ = LP._cuadratura(lambda tau: float(mx.valor_real(mx.parse(mx.normaliza_entrada(k)),
                                                                {t: x - tau})) *
                               _valor_inv_lp(inv, tau), 0.0, x)
        lhs = _valor_inv_lp(inv, x)
        rhs = LP.valor_senal(F.señal, x) + float(mx.valor_real(lam_e, {})) * integ
        peor = max(peor, abs(lhs - rhs))
    if peor > 1e-7:
        raise _error("DISCREPANT", f"la solución no cumple la ecuación integral ({peor:.3g})")
    trace.verificacion("volterra.puntos", f"y − f − λ∫k(t−τ)y(τ)dτ ≈ 0 en 3 instantes "
                       f"(desviación {peor:.2g})", why="sustitución con cuadratura")
    return inv


def _valor_inv_lp(inv, x: float) -> float:
    total = 0.0
    for a, cuasi, _ in inv.piezas:
        av = float(mx.valor_real(a, {}))
        if x >= av:
            v = mx.valor_real(Q.a_expr(cuasi, inv.t), {inv.t: x - av})
            total += float(v) if v is not None else 0.0
    return total


def integro(texto: str, y0="0", t: str = "t", trace: Trace | None = None):
    """Σ aₖy⁽ᵏ⁾ + c·∫₀ᵗy = f(t) con y(0), y′(0)… (la integral se escribe int(y)).

    (p(s) + c/s)·Y = F(s) + I(s)  ⇒  Y = s·(F + I)/(s·p(s) + c)."""
    import re as _re

    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    texto2 = _re.sub(r"(int|∫)\s*\(\s*y\s*\)", "Iy__", texto)
    lhs, rhs = texto2.split("=", 1) if "=" in texto2 else (texto2, "0")
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    sin_int = lhs.replace("Iy__", "0")
    ec = leer(sin_int + "=" + rhs, t)
    E = None
    c: mx.Expr = mx.Num(Fraction(0))
    if "Iy__" in lhs:
        completa = leer(lhs + " + 0*y = " + rhs, t)
        if "Iy__" in mx.variables(completa.E):
            c = limpio(DM.differentiate(completa.E, "Iy__"))
    cq = Fraction(mx.exact_value(c) or 0)
    p = _coefs_q(ec)
    n = ec.orden
    ini = y0 if isinstance(y0, (list, tuple)) else [y0] + ["0"] * (n - 1)
    y0s = [limpio(mx.parse(str(v))) for v in ini]
    # I(s) = Σₖ aₖ Σ_{j<k} s^{k−1−j}·y⁽ʲ⁾(0)
    I = [mx.Num(Fraction(0))] * max(1, n)
    for k in range(1, n + 1):
        for jj in range(k):
            I[k - 1 - jj] = limpio(mx.Add(I[k - 1 - jj], mx.Mul(Q.num(p[k]), y0s[jj])))
    den = [cq] + list(p)                      # s·p(s) + c
    fracs = []
    if any(not Q.es_cero(x) for x in I):
        fracs.append(LP.Fraccion(mx.Num(Fraction(0)), [mx.Num(0)] + I, den))
    senal = None
    if not Q.es_cero(ec.f):
        F = LP.transformada(ec.f_texto, t, Trace())
        senal = F.señal
        for fr in F.fracciones:
            fracs.append(LP.Fraccion(fr.retardo, [mx.Num(0)] + list(fr.num),
                                     AL._p_mul(list(fr.den), den)))
    trace.regla("integro.laplace", f"({_texto_poli(p, 's')} + {cq}/s)·Y = F(s) + I(s)",
                why="L{∫₀ᵗy} = Y(s)/s y L{y⁽ᵏ⁾} = sᵏY − …")
    inv = inversa_fracciones(fracs, t, trace)
    # comprobación en puntos: derivadas exactas por tramos e integral por cuadratura
    peor = 0.0
    for x in (0.45, 1.3, 2.6):
        derivs = [0.0] * (n + 1)
        for a, cuasi, _ in inv.piezas:
            av = float(mx.valor_real(a, {}))
            if x < av:
                continue
            d = cuasi
            for k in range(n + 1):
                derivs[k] += float(mx.valor_real(Q.a_expr(d, t), {t: x - av}) or 0.0)
                d = Q.deriva(d)
        cortes = sorted({0.0, x} | {float(mx.valor_real(a, {})) for a, _, _ in inv.piezas
                                    if 0 < float(mx.valor_real(a, {})) < x})
        integral = sum(LP._cuadratura(lambda u: _valor_inv(inv, u), a_, b_)
                       for a_, b_ in zip(cortes, cortes[1:]))
        lhs_v = sum(float(pk) * dk for pk, dk in zip(p, derivs)) + float(cq) * integral
        rhs_v = LP.valor_senal(senal, x) if senal is not None else 0.0
        peor = max(peor, abs(lhs_v - rhs_v))
    if peor > 1e-6:
        raise _error("DISCREPANT", f"la solución no cumple la ecuación integro-diferencial "
                     f"({peor:.3g})")
    trace.verificacion("integro.puntos", f"Σaₖy⁽ᵏ⁾ + c∫y − f ≈ 0 en 3 instantes (desviación "
                       f"{peor:.2g})", why="sustitución con la integral por cuadratura")
    _ = E
    return inv


# ---------------------------------------------------------------------------
# Picard, Wronskiano, reducción de orden, Euler-Cauchy
# ---------------------------------------------------------------------------


def picard(F: str, t0="0", y0="1", iteraciones: int = 3, t: str = "t", y: str = "y",
           trace: Trace | None = None) -> list:
    """φ₀ = y₀, φₖ₊₁(t) = y₀ + ∫_{t₀}^t F(s, φₖ(s)) ds."""
    trace = trace if trace is not None else Trace()
    Fe = mx.parse(mx.normaliza_entrada(F))
    t0e, y0e = mx.parse(str(t0)), mx.parse(str(y0))
    phi = y0e
    salida = [phi]
    for k in range(iteraciones):
        integrando = _bonito(mx.substitute(Fe, y, phi))
        P = _prim(integrando, t)
        phi = _bonito(mx.Add(y0e, mx.Sub(P, mx.substitute(P, t, t0e))))
        # comprobación: φ′ = F(t, φ anterior)
        if not _eq0(mx.Sub(_d(phi, t), integrando)):
            raise _error("DISCREPANT", "la iteración no deriva al integrando")
        salida.append(phi)
        trace.regla("picard.iteracion", f"φ{k + 1}({t}) = {mx.text(phi)}",
                    why="φₖ₊₁ = y₀ + ∫F(s, φₖ(s))ds; comprobada derivando")
    return salida


def wronskiano(funciones: list[str], t: str = "t", trace: Trace | None = None) -> mx.Expr:
    trace = trace if trace is not None else Trace()
    fs = [mx.parse(mx.normaliza_entrada(f)) for f in funciones]
    filas = []
    actual = fs
    for _ in range(len(fs)):
        filas.append(actual)
        actual = [_d(f, t) for f in actual]
    W = _bonito(_det(filas))
    trace.regla("wronskiano", f"W = {mx.text(W)}" + (
        " ≢ 0: las funciones son linealmente independientes" if not _eq0(W) else
        " ≡ 0 (no basta para concluir dependencia si no son soluciones de una misma EDO)"),
        why="determinante de las funciones y sus derivadas")
    return W


def reduccion_orden(ecuacion: str, y1: str, t: str = "t", trace: Trace | None = None) -> mx.Expr:
    """y″ + p(t)y′ + q(t)y = 0 con y₁ conocida: y₂ = y₁·∫e^{−∫p}/y₁² dt."""
    trace = trace if trace is not None else Trace()
    ec = leer(ecuacion, t)
    if ec.orden != 2:
        raise _error("BAD_INPUT", "la reducción de orden es para orden 2")
    a2 = ec.coefs[2]
    p = _bonito(mx.Div(ec.coefs[1], a2))
    y1e = mx.parse(mx.normaliza_entrada(y1))
    if not _eq0(mx.Add(mx.Add(mx.Mul(ec.coefs[2], _d(_d(y1e, t), t)),
                              mx.Mul(ec.coefs[1], _d(y1e, t))), mx.Mul(ec.coefs[0], y1e))):
        raise _error("BAD_INPUT", f"{y1} no es solución de la homogénea")
    mu = _sin_abs(_bonito(mx.Call("exp", (mx.Neg(_sin_abs(_prim(p, t))),))))
    v = _prim(mx.Div(mu, mx.Pow(y1e, mx.Num(2))), t)
    y2 = _bonito(mx.Mul(y1e, v))
    trace.regla("reduccion.orden", f"y₂ = y₁∫e^(−∫p)/y₁² dt = {mx.text(y2)}",
                why="y = v·y₁ reduce la ecuación a primer orden en v′")
    homog = Ecuacion(t, "y", 2, ec.coefs, mx.Num(Fraction(0)), "", True, ec.E)
    _verifica_simbolica(homog, y2, trace)
    return y2


def euler_cauchy(ecuacion: str, t: str = "t", trace: Trace | None = None) -> str:
    """a·t²y″ + b·t·y′ + c·y = 0: y = tʳ con a·r(r − 1) + b·r + c = 0."""
    trace = trace if trace is not None else Trace()
    ec = leer(ecuacion, t)
    if ec.orden != 2:
        raise _no("Euler-Cauchy de orden 2")
    T = mx.Sym(t)
    a = _bonito(mx.Div(ec.coefs[2], mx.Pow(T, mx.Num(2))))
    b = _bonito(mx.Div(ec.coefs[1], T))
    c = ec.coefs[0]
    if any(mx.depends(x, t) for x in (a, b, c)):
        raise _no("no es de Euler-Cauchy (coeficientes a·t², b·t, c)")
    aq, bq, cq = (Fraction(mx.exact_value(x)) for x in (a, b, c))
    # a r² + (b − a) r + c = 0
    A, B, C = aq, bq - aq, cq
    disc = B * B - 4 * A * C
    r0 = Q.num(-B / (2 * A))
    lnT = mx.Call("ln", (T,))
    if disc > 0:
        raiz = _bonito(mx.Root(2, Q.num(disc)))
        r1 = _bonito(mx.Div(mx.Add(Q.num(-B), raiz), Q.num(2 * A)))
        r2 = _bonito(mx.Div(mx.Sub(Q.num(-B), raiz), Q.num(2 * A)))
        base = [_bonito(mx.Pow(T, r1)), _bonito(mx.Pow(T, r2))]
    elif disc == 0:
        base = [_bonito(mx.Pow(T, r0)), _bonito(mx.Mul(mx.Pow(T, r0), lnT))]
    else:
        beta = _bonito(mx.Div(mx.Root(2, Q.num(-disc)), Q.num(2 * A)))
        tr = mx.Pow(T, r0)
        base = [_bonito(mx.Mul(tr, mx.Call("cos", (mx.Mul(beta, lnT),)))),
                _bonito(mx.Mul(tr, mx.Call("sin", (mx.Mul(beta, lnT),))))]
    sol_e = _bonito(mx.Add(mx.Mul(mx.Sym("C1"), base[0]), mx.Mul(mx.Sym("C2"), base[1])))
    sol = f"y = {mx.text(sol_e)} ({t} > 0)"
    trace.regla("euler_cauchy", f"y = {t}^r: {aq}·r(r − 1) + {bq}·r + {cq} = 0 ⇒ {sol}",
                why="t = e^x la convierte en coeficientes constantes")
    homog = Ecuacion(t, "y", 2, ec.coefs, mx.Num(Fraction(0)), "", True, ec.E)
    for f in base:
        _verifica_simbolica(homog, f, trace)
    if not Q.es_cero(ec.f):
        yp = variacion_parametros(ec, base, trace)
        sol = f"y = {mx.text(sol_e)} + {mx.text(yp)} ({t} > 0)"
        trace.regla("euler_cauchy.particular", f"y_p = {mx.text(yp)} por variación de parámetros",
                    why="con la base tʳ de la homogénea")
    return sol
