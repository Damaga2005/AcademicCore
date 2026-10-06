# SPDX-License-Identifier: MIT
"""ML-2 (T4, T5, T7): estudio completo, extremos absolutos y número de soluciones."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import estudio as E
from academic_core.domain.engineering.mathlab import mvexpr as mx

sp = pytest.importorskip("sympy")

FUNCIONES = ["x^3-3*x", "(x^2+1)/(x-1)", "x*exp(-x)", "ln(x)/x", "sqrt(4-x^2)", "1/(x^2-4)",
             "x^2*exp(x)", "ln(x^2-1)", "x^4-2*x^2", "x/(x^2+1)", "exp(-x^2)", "x*ln(x)"]


@pytest.mark.parametrize("f", FUNCIONES)
def test_extremos_relativos_contra_sympy(f):
    x = sp.Symbol("x", real=True)
    sf = sp.sympify(f.replace("^", "**").replace("ln", "log"), locals={"x": x})
    d = sp.diff(sf, x)
    criticos = []
    for c in sp.solve(sp.Eq(d, 0), x):
        if not c.is_real or not sf.subs(x, c).is_real:
            continue           # outside the domain (ln(x² − 1) at 0)
        v = float(c)
        h = 1e-5
        izq, der = float(d.subs(x, v - h)), float(d.subs(x, v + h))
        if izq * der < 0:
            criticos.append(v)
    est = E.estudiar(mx.parse(f), "x")
    ours = sorted(p.x.x for p in est.extremos)
    assert len(ours) == len(criticos), (f, ours, criticos)
    assert all(abs(a - b) < 1e-9 for a, b in zip(ours, sorted(criticos)))


@pytest.mark.parametrize("f,esperado", [
    ("x^3-3*x", ["crece en: (−∞, -1) ∪ (1, +∞)", "máximo relativo en (-1, 2)",
                 "inflexión en (0, 0)", "impar"]),
    ("(x^2+1)/(x-1)", ["oblicua y = x + 1 en +∞", "vertical x = 1",
                       "mínimo relativo en (1 + sqrt(2), 2*sqrt(2) + 2)"]),
    ("x*exp(-x)", ["máximo relativo en (1, exp(-1))", "inflexión en (2, 2*exp(-2))",
                   "horizontal y = 0 en +∞"]),
    ("ln(x)/x", ["dominio: (0, +∞)", "máximo relativo en (exp(1), 1/exp(1))",
                 "vertical x = 0 (por la derecha → −∞)"]),
    ("sqrt(4-x^2)", ["dominio: [-2, 2]", "par"]),
    ("ln(x^2-1)", ["dominio: (−∞, -1) ∪ (1, +∞)", "par", "eje X en (-sqrt(2), 0)"]),
])
def test_estudio_completo(f, esperado):
    texto = E.estudiar(mx.parse(f), "x").texto()
    for trozo in esperado:
        assert trozo in texto, (trozo, texto)


@pytest.mark.parametrize("f,a,b", [("x^3-3*x", "-2", "3"), ("abs(x-1)+x^2", "-1", "2"),
                                   ("x*exp(-x)", "0", "4"), ("sin(x)+cos(x)", "0", "pi"),
                                   ("x^4-2*x^2", "-2", "1/2")])
def test_extremos_absolutos_contra_malla_fina(f, a, b):
    r = ML.calcular(ML.Peticion("extremos_absolutos", {"expr": f, "a": a, "b": b}))
    assert r.sello.verdict == "verificado"
    fe = mx.parse(f)
    xa, xb = mx.valor_real(mx.parse(a), {}), mx.valor_real(mx.parse(b), {})
    malla = [mx.valor_real(fe, {"x": xa + (xb - xa) * k / 20000}) for k in range(20001)]
    res = E.extremos_absolutos(fe, "x", mx.parse(a), mx.parse(b))
    assert abs(max(malla) - mx.valor_real(res.maximo[0], {})) < 1e-6
    assert abs(min(malla) - mx.valor_real(res.minimo[0], {})) < 1e-6


def test_weierstrass_comprueba_su_hipotesis():
    with pytest.raises(Exception, match="HYPOTHESIS"):
        E.extremos_absolutos(mx.parse("1/x"), "x", mx.parse("-1"), mx.parse("1"))


@pytest.mark.parametrize("f,a,b,n", [("x^3+x-1", None, None, 1), ("exp(x)-3*x", "0", "2", 2),
                                     ("x^3-3*x+1", None, None, 3), ("ln(x)+x", None, None, 1),
                                     ("x^2+1", None, None, 0)])
def test_numero_de_soluciones(f, a, b, n):
    r = E.numero_de_soluciones(mx.parse(f), "x", a and mx.parse(a), b and mx.parse(b))
    assert r.numero == n and r.justificacion
