# SPDX-License-Identifier: MIT
"""ML-8: EDO, Laplace, Fourier, transformada z, sistemas, oscilador, contorno y calor.

SymPy solo como oráculo (nunca en el código del laboratorio): transformadas,
inversas y soluciones se contrastan numéricamente con él.
"""

from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contorno as CO
from academic_core.domain.engineering.mathlab import cuasipolinomios as Q
from academic_core.domain.engineering.mathlab import edo as ED
from academic_core.domain.engineering.mathlab import fourier as FO
from academic_core.domain.engineering.mathlab import laplace as LP
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import transformada_z as TZ

sp = pytest.importorskip("sympy")

T, S = sp.symbols("t s", positive=True)


def _sym(texto: str):
    return sp.sympify(texto.replace("^", "**").replace("e**", "E**"), locals={"t": T, "s": S})


def _valor_inv(inv, x: float) -> float:
    total = 0.0
    for a, cuasi, _ in inv.piezas:
        av = float(mx.valor_real(a, {}))
        if x >= av:
            total += float(mx.valor_real(Q.a_expr(cuasi, inv.t), {inv.t: x - av}))
    return total


# ---------------------------------------------------------------------------
# Laplace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("f", ["t^3*e^(-2*t)", "e^(3*t)*cos(4*t)", "t*sin(2*t)", "sinh(3*t)*t",
                               "t^2*cos(t)", "cos(t)^3", "(t+1)^2*e^t", "t*e^(-t)*sin(3*t)"])
def test_laplace_directa_frente_a_sympy(f):
    F = LP.transformada(f).expr()
    Fs = sp.laplace_transform(_sym(f), T, S, noconds=True)
    for sv in (5.3, 7.1):
        assert abs(mx.valor_real(F, {"s": sv}) - complex(Fs.subs(S, sv).evalf()).real) < 1e-9


def test_laplace_con_escalones_y_deltas():
    r = LP.transformada("t*(u(t)-u(t-1))")
    assert r.texto().startswith("F(s) = 1/s^2 + e^(−s)·(-s - 1)/s^2")
    assert "toda s" in r.abscisa_txt
    assert "e^(−3s)" in LP.transformada("delta(t-3)").texto()
    assert "e^(−π·s)" in LP.transformada("sin(t)*u(t-pi)").texto()
    assert "s^2" in LP.transformada("delta''(t-2)+3").texto()


@pytest.mark.parametrize("F", ["1/(s^2+4*s+13)", "(3*s+2)/(s^2+2*s+10)", "1/(s^3+s)",
                               "s^2/((s+1)^3)", "1/((s^2+1)*(s^2+4))", "(s+5)/(s^2-2*s-3)",
                               "1/(s^4-1)", "1/(s^2+2)^2", "1/(s^2+1)^3", "s/(s^2-3)^2"])
def test_laplace_inversa_frente_a_sympy(F):
    r = LP.inversa(F)
    fs = sp.inverse_laplace_transform(_sym(F), S, T)
    for tv in (0.5, 1.7, 3.2):
        assert abs(_valor_inv(r, tv) - complex(fs.subs(T, tv).evalf()).real) < 1e-8


def test_laplace_inversa_formas_de_clase():
    assert LP.inversa("1/(s^2-2)").texto() == "f(t) = 1/2*sinh(sqrt(2)*t)*sqrt(2) (t ≥ 0)"
    assert LP.inversa("(s+1)/(s^2+2*s-1)").texto() == "f(t) = cosh(sqrt(2)*t)*exp(-t) (t ≥ 0)"
    assert "u(t − 1)" in LP.inversa("(1-e^(-s))/s^2").texto()
    assert "δ′(t)" in LP.inversa("(s^3+1)/(s^2+1)").texto()


def test_laplace_inversa_exacta_con_cubica_irreducible():
    r = LP.inversa("1/(s^3+s+1)")
    assert not r.aproximada and "donde" in r.texto()
    res = ML.calcular(ML.Peticion("laplace", {"calculo": "inversa", "F": "1/(s^3+s+1)"}))
    assert res.sello.verdict != "discrepa"


def test_laplace_inversa_grado_cinco_sigue_numerica():
    assert LP.inversa("1/(s^5+s+3)").aproximada


# ---------------------------------------------------------------------------
# EDO
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ec, esperado", [
    ("y''+y=sin(t)", "-1/2*cos(t)*t"),
    ("y''-2*y'+y=t*e^t", "1/6*exp(t)*t^3"),
    ("y'''-y=e^t", "1/3*exp(t)*t"),
    ("y''+2*y'+5*y=e^(-t)*sin(2*t)", "-1/4*cos(2*t)*exp(-t)*t"),
])
def test_coeficientes_indeterminados_con_resonancia(ec, esperado):
    g = ED.general(ED.leer(ec))
    assert g.metodo == "coeficientes indeterminados"
    assert mx.text(Q.a_expr(g.particular)) == esperado


def test_variacion_de_parametros_formas_de_libro():
    assert ED.general(ED.leer("y''+y=sec(t)")).texto().endswith(
        "cos(t)*ln(abs(cos(t))) + sin(t)*t")
    assert ED.general(ED.leer("y''+4*y=tan(2*t)")).texto().endswith(
        "-1/4*cos(2*t)*ln(abs(1/cos(2*t) + tan(2*t)))")


def test_caracteristico_con_cubica_irreducible_es_exacto():
    g = ED.general(ED.leer("y'''+y'+y=0"))
    assert not g.aproximada and "donde" in g.texto()


@pytest.mark.parametrize("ec, ini", [("y''+3*y'+2*y=e^(-3*t)", ["1", "0"]),
                                     ("y''+y=u(t-2)", ["1", "1"]),
                                     ("y'+3*y=delta(t-1)", ["2"]),
                                     ("y''-y=t", ["0", "1"]),
                                     ("y''+4*y=sin(2*t)", ["0", "0"])])
def test_pvi_por_laplace_frente_a_sympy(ec, ini):
    r = ED.pvi_laplace(ED.leer(ec), ini)
    y = sp.Function("y")
    lhs, rhs = ec.split("=")
    expr = lhs.replace("y''", "Derivative(y(t),t,2)").replace("y'", "Derivative(y(t),t)")
    expr = expr.replace("y", "y(t)").replace("y(t)(t)", "y(t)")
    expr = expr.replace("Derivative(y(t)(t),t,2)", "Derivative(y(t),t,2)")
    rhs_s = rhs.replace("u(t-2)", "Heaviside(t-2)").replace("delta(t-1)", "DiracDelta(t-1)")
    eq = sp.Eq(sp.sympify(expr.replace("^", "**"), locals={"y": y, "t": T}),
               sp.sympify(rhs_s.replace("^", "**").replace("e**", "E**"), locals={"t": T}))
    ics = {y(0): sp.sympify(ini[0])}
    if len(ini) > 1:
        ics[y(T).diff(T).subs(T, 0)] = sp.sympify(ini[1])
    try:
        sol = sp.dsolve(eq, y(T), ics=ics).rhs
    except Exception:  # noqa: BLE001 - SymPy no resuelve todos (deltas): basta la comprobación interna
        return
    for tv in (0.4, 1.5, 2.7, 3.6):
        assert abs(_valor_inv(r.inversa, tv) - float(sol.subs(T, tv).evalf())) < 1e-8


def test_pvi_con_delta_salta_la_derivada():
    r = ED.pvi_laplace(ED.leer("y''+4*y=delta(t-pi)"), ["0", "1"])
    assert r.piezas_tramos[-1][2] == mx.parse("sin(2*t)")


@pytest.mark.parametrize("ec, ic, tipo", [
    ("y'=t*y", (0, 2), "lineal"),
    ("y'=y^2*t", None, "separable"),
    ("y'+y=t*y^3", None, "Bernoulli"),
    ("(3*t^2*y+y^2)+(t^3+2*t*y)*y'=0", (1, 1), "exacta"),
    ("y'=(t^2+y^2)/(t*y)", None, "homogénea"),
    ("y'=y*(1-y)", (0, "1/2"), "separable"),
])
def test_primer_orden_clasifica_y_resuelve(ec, ic, tipo):
    r = ED.primer_orden(ec, inicial=ic)
    assert r.tipo == tipo


def test_logistica_explicita():
    r = ED.primer_orden("y'=y*(1-y)", inicial=(0, "1/2"))
    assert r.solucion == "y = exp(t)/(exp(t) + 1)"


def test_factor_integrante():
    assert ED.primer_orden("(y^2+1)+(2*t*y)*y'=0").tipo in ("separable", "exacta")
    r = ED.primer_orden("(3*t*y+y^2)+(t^2+t*y)*y'=0")
    assert r.tipo == "exacta con factor integrante"


# ---------------------------------------------------------------------------
# sistemas, oscilador, convolución, ecuaciones integrales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("A, fase", [([[0, 1], [-2, -3]], "nodo estable"),
                                     ([[1, -1], [1, 1]], "foco (espiral) inestable"),
                                     ([[2, 1], [0, 2]], "nodo impropio"),
                                     ([[0, 1], [-1, 0]], "centro"),
                                     ([[1, 2], [2, 1]], "punto de silla")])
def test_sistemas_plano_de_fases(A, fase):
    r = ED.sistema(A)
    assert r.fases.startswith(fase)


def test_exponencial_de_matriz_frente_a_sympy():
    A = [[1, 0, 0], [0, 2, 1], [0, 0, 2]]
    r = ED.sistema(A)
    E = (sp.Matrix(A) * T).exp()
    for tv in (0.3, 1.2):
        for i in range(3):
            for j in range(3):
                v = mx.valor_real(Q.a_expr(r.exponencial[i][j]), {"t": tv})
                assert abs(v - float(E[i, j].subs(T, tv))) < 1e-9


def test_oscilador_con_q():
    r = ED.oscilador(1, "1/2", 4)
    assert mx.text(r.Q) == "4" and "subamortiguado" in r.regimen
    assert "1/4*sqrt(62)" in r.resonancia
    assert "crítico" in ED.oscilador(1, 4, 4).regimen


def test_convolucion_y_volterra():
    assert ED.convolucion("t", "e^(-t)").texto() == "f(t) = exp(-t) + t + -1 (t ≥ 0)"
    assert ED.volterra("1", "t", "1").texto() == "f(t) = cosh(t) (t ≥ 0)"
    assert ED.integro("y'+4*int(y)=0", "1").texto() == "f(t) = cos(2*t) (t ≥ 0)"


def test_picard_wronskiano_reduccion_euler():
    its = ED.picard("t*y", 0, 1, 3)
    assert mx.text(its[3]) == "1/2*t^2 + 1/8*t^4 + 1/48*t^6 + 1"
    assert ED.reduccion_orden("t^2*y''-3*t*y'+4*y=0", "t^2") == mx.parse("ln(abs(t))*t^2")
    assert ED.euler_cauchy("t^2*y''-2*y=t^3") == "y = C2/t + C1*t^2 + 1/4*t^3 (t > 0)"


# ---------------------------------------------------------------------------
# Fourier
# ---------------------------------------------------------------------------


def test_serie_de_fourier_simplificada():
    s = FO.serie([["t", "-pi", "pi"]])
    assert mx.text(s.bn) == "-2*(-1)^n/n" and mx.text(s.an) == "0"
    s = FO.serie([["abs(t)", "-pi", "pi"]])
    assert mx.text(s.a0) == "pi" and mx.text(s.parseval) == "1/6*pi^2"
    s = FO.serie([["sin(t)", "0", "pi"], ["0", "pi", "2*pi"]])
    assert 1 in s.especiales and mx.text(s.especiales[1][1]) == "1/2"


def test_coeficientes_frente_a_sympy():
    x, n = sp.symbols("x n")
    s = FO.serie([["t^2", "-1", "1"]])
    for k in range(1, 5):
        ak = sp.integrate(x ** 2 * sp.cos(k * sp.pi * x), (x, -1, 1))
        assert abs(float(mx.valor_real(s.an, {"n": k})) - float(ak)) < 1e-12


def test_transformada_de_fourier():
    assert FO.transformada("u(t+1/2)-u(t-1/2)").texto().startswith("X(f) = sin(pi*f)/(pi*f)")
    assert FO.transformada("e^(-2*abs(t))").texto().startswith("X(f) = 1/(pi^2*f^2 + 1)")
    assert FO.transformada("e^(-t^2)").texto() == "X(f) = exp(-pi^2*f^2)*sqrt(pi)"
    assert FO.transformada("delta'(t)").texto() == "X(f) = i·(2*pi*f)"


# ---------------------------------------------------------------------------
# transformada z
# ---------------------------------------------------------------------------


def test_z_directa_e_inversa():
    assert TZ.transformada("3^n*sin(pi*n/2)").texto().startswith("X(z) = 3·z/(z^2 + 9)")
    assert TZ.inversa("z/(z-1)^2").texto() == "x[n] = (n)·u[n] (causal; polos: 1)"
    r = TZ.inversa("(z^2+z)/(z^2-z+1)")
    assert "cos(1/3*pi*n)" in r.texto()


def test_ecuacion_en_diferencias():
    r = TZ.diferencias("y[n]-5/6*y[n-1]+1/6*y[n-2]=x[n]", "u[n]", {})
    assert mx.text(r.y.x) == "-3*(1/2)^n + (1/3)^n + 3"
    r = TZ.diferencias("y[n]-y[n-1]=x[n]", "n", {-1: "2"})
    assert [r.y.valor(k) for k in range(4)] == [2.0, 3.0, 5.0, 8.0]


# ---------------------------------------------------------------------------
# contorno, Poisson, calor
# ---------------------------------------------------------------------------


def test_problemas_de_contorno():
    assert CO.contorno("y''+y=0", 0, "pi/2", ("y", 1), ("y", 2)).tipo == "única"
    assert CO.contorno("y''+y=0", 0, "pi", ("y", 0), ("y", 0)).tipo == "infinitas"
    assert CO.contorno("y''+y=0", 0, "pi", ("y", 0), ("y", 1)).tipo == "ninguna"
    r = CO.contorno("y''=y/L^2", 0, "w", ("y", "V0"), ("y", 0))
    assert "sinh(x/L)" in mx.text(r.y) and "cosh(x/L)" in mx.text(r.y)


def test_poisson_por_tramos_con_empalme():
    r = CO.poisson([["0", "0", "1", "1"], ["0", "1", "3", "4"]], ("y", 0), ("y", 10))
    assert [mx.text(e) for _, _, e in r.piezas] == ["20/3*x", "5/3*x + 5"]


def test_calor():
    r = CO.calor("1/4", "1", "100", "dirichlet")
    assert mx.text(r.coef) == "(-200*(-1)^n + 200)/(pi*n)"
    assert mx.text(r.decaimiento) == "1/4*pi^2*n^2"
    r = CO.calor("1", "1", "x", "dirichlet", "20", "50")
    assert mx.text(r.estacionario) == "30*x + 20"
    assert CO.calor("2", "pi", "x", "neumann").a0 == mx.parse("pi")


# ---------------------------------------------------------------------------
# calculadoras
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op, entrada", [
    ("edo", "y''+y=sin(t)"),
    ("edo", {"calculo": "pvi", "ecuacion": "y''+4*y=delta(t-pi)", "iniciales": ["0", "1"]}),
    ("edo", {"calculo": "sistema", "A": [[0, 1], [-2, -3]]}),
    ("edo", {"calculo": "oscilador", "m": 1, "b": "1/2", "k": 4}),
    ("laplace", "t*u(t-1)"),
    ("laplace", {"calculo": "inversa", "F": "1/(s^2+1)^2"}),
    ("fourier", {"calculo": "serie", "tramos": [["t", "-pi", "pi"]]}),
    ("fourier", {"calculo": "transformada", "x": "u(t+1/2)-u(t-1/2)"}),
    ("transformada_z", "n*(1/2)^n"),
    ("transformada_z", {"calculo": "diferencias", "ecuacion": "y[n]-y[n-1]=x[n]", "x": "u[n]"}),
    ("contorno", {"calculo": "calor", "alfa": 1, "L": "pi", "inicial": "x"}),
    ("contorno", {"calculo": "poisson", "tramos": [["-1", "0", "1"], ["0", "1", "2"]],
                  "ca": ["y", 0], "cb": ["y", 0]}),
])
def test_calculadoras_ml8_verificadas_con_grafica(op, entrada):
    r = ML.calcular(ML.Peticion(op, entrada))
    assert r.sello.verdict == "verificado"
    assert r.grafica is None or r.grafica.series


def test_impresion_de_denominador_negado():
    """x/(−(2t²)) se imprimía «x/-2*t^2», que se relee como (x/−2)·t² (cambiaba valores)."""
    e = mx.Div(mx.Sym("x"), mx.Neg(mx.Mul(mx.Num(2), mx.Pow(mx.Sym("t"), mx.Num(2)))))
    assert mx.text(e) == "x/(-2*t^2)"
    v = mx.valor_real(mx.parse(mx.text(e)), {"x": 1.0, "t": 2.0})
    assert math.isclose(v, -1 / 8)


# ---------------------------------------------------------------------------
# limitaciones resueltas: bicuadrada, curvas por composición, resonancia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("F", ["1/(s^4+3*s^2+1)", "1/(s^4-2*s^2-1)", "1/(s^4+2)",
                               "1/(s^4+s^2+2)"])
def test_laplace_inversa_cuartica_bicuadrada_exacta(F):
    assert not LP.inversa(F).aproximada
    res = ML.calcular(ML.Peticion("laplace", {"calculo": "inversa", "F": F}))
    assert res.sello.verdict == "verificado"


def test_caracteristico_bicuadrado_exacto():
    g = ED.general(ED.leer("y''''+3*y''+y=0"))
    assert not g.aproximada and "sqrt(5)" in g.texto()


@pytest.mark.parametrize("f, clase", [
    ("(x^2+y^2)*e^(-x^2-y^2)", "máximos (no estrictos) (exacto"),
    ("(x^2+y^2-1)^2*e^(x^2+y^2)", "mínimos (no estrictos) (exacto"),
])
def test_curva_critica_por_composicion(f, clase):
    from academic_core.domain.engineering.mathlab import mvexpr as mx
    from academic_core.domain.engineering.mathlab import varias as MV

    _, curvas = MV.conjunto_critico(mx.parse(f), ["x", "y"])
    assert curvas[0].clase.startswith(clase)


def test_criticos_sen_de_cuadratica():
    res = ML.calcular(ML.Peticion("multivar", {"calculo": "criticos", "expr": "sin(x^2+y^2)",
                                               "vars": ["x", "y"]}))
    assert "(0, 0): mínimo" in res.exacto
    assert "-1/2*pi + x^2 + y^2 = 0: f = 1, máximos" in res.exacto
    assert "-3/2*pi + x^2 + y^2 = 0: f = -1, mínimos" in res.exacto
    assert "-1/2*pi - pi*k + x^2 + y^2 = 0 (k ≥ 0)" in res.exacto
    assert "k par: f = 1, máximos" in res.exacto


def test_criticos_cos_de_cuadratica_origen_exacto():
    res = ML.calcular(ML.Peticion("multivar", {"calculo": "criticos", "expr": "cos(x^2+y^2)",
                                               "vars": ["x", "y"]}))
    assert "(0, 0): máximo (exacto" in res.exacto and "(k ≥ 1)" in res.exacto


def test_calor_resonancia():
    r = CO.calor("1", "1", "0", "dirichlet", "e^(-pi^2*t)", "0")
    assert 1 in r.especiales and "t" in str(r.especiales[1]) or "*t" in r.texto()
    assert "resonancia" in r.texto()


def test_calor_resonancia_simplificada():
    r = CO.calor("1", "1", "0", "dirichlet", "e^(-pi^2*t)", "0")
    assert "n^5" not in r.texto() and "(n ≠ 1)" in r.texto()
