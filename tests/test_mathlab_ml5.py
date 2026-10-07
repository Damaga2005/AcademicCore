# SPDX-License-Identifier: MIT
"""ML-5 (varias variables): límites direccionales, derivada direccional,
jacobiana, cadena, implícita, Hessiana/Sylvester, Taylor-2, Lagrange y
extremos en recintos. Todo exacto con segundo camino; lo no exacto, con motivo.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx


def test_limites_direccionales_no_existe():
    from academic_core.domain.engineering.mathlab import varias as MV

    r = MV.limites_direccionales(mx.parse("x*y/(x^2+y^2)"), ["x", "y"],
                                 {"x": "0", "y": "0"})
    assert r.existe is False
    assert "y = x" in r.texto() and "y = 0" in r.texto()


def test_limites_direccionales_indicio():
    from academic_core.domain.engineering.mathlab import varias as MV

    r = MV.limites_direccionales(mx.parse("x^2+y^2"), ["x", "y"],
                                 {"x": "0", "y": "0"})
    # la cota en polares |f| ≤ r² prueba la existencia (ya no es solo un indicio)
    assert r.existe is True and "polares" in r.texto()
    # sin cota ni composición sigue siendo un indicio, nunca una prueba
    r2 = MV.limites_direccionales(mx.parse("x^2*y^2/(x^2*y^2+(x-y)^2)"), ["x", "y"],
                                  {"x": "0", "y": "0"})
    assert r2.existe is not True


def test_derivada_direccional():
    from academic_core.domain.engineering.mathlab import varias as MV

    v = MV.derivada_direccional(mx.parse("x^2+y^2"), ["x", "y"],
                                {"x": 1, "y": 1}, [1, 0])
    assert v == Fraction(2)


def test_jacobiana():
    from academic_core.domain.engineering.mathlab import varias as MV

    J = MV.jacobiana([mx.parse("x^2+y"), mx.parse("x*y")], ["x", "y"])
    assert mx.text(J[0][0]) == "2*x" and mx.text(J[1][1]) == "x"


def test_cadena():
    from academic_core.domain.engineering.mathlab import varias as MV

    d = MV.cadena(mx.parse("x^2*y"), {"x": mx.parse("t^2"), "y": mx.parse("t")}, "t")
    assert mx.text(d) == "5*t^4"


def test_implicita():
    from academic_core.domain.engineering.mathlab import varias as MV

    d = MV.implicita(mx.parse("x^2+y^2-1"), "x", "y")
    assert "x" in mx.text(d) and "y" in mx.text(d)


def test_hessiana_minimo_y_silla():
    from academic_core.domain.engineering.mathlab import varias as MV

    H, c = MV.hessiana(mx.parse("x^2+y^2"), ["x", "y"])
    assert c == "mínimo" and H[0][0] == mx.Num(Fraction(2))
    _, c2 = MV.hessiana(mx.parse("x^2-y^2"), ["x", "y"])
    assert c2 == "punto de silla"
    # H no constante: sin punto no decide; con punto sí
    with pytest.raises(Exception, match="no decide|depende del punto"):
        MV.hessiana(mx.parse("x^3+y^3"), ["x", "y"])
    _, c3 = MV.hessiana(mx.parse("x^3+y^3"), ["x", "y"], {"x": 1, "y": 1})
    assert c3 == "mínimo"


def test_puntos_criticos():
    from academic_core.domain.engineering.mathlab import varias as MV

    pts = MV.puntos_criticos(mx.parse("x^2+x*y+y^2"), ["x", "y"])
    assert len(pts) == 1 and pts[0][0] == (Fraction(0), Fraction(0))
    assert pts[0][1] == "mínimo"


def test_taylor2():
    from academic_core.domain.engineering.mathlab import varias as MV

    p = MV.taylor2(mx.parse("exp(x+y)"), ["x", "y"],
                   {"x": mx.Num(Fraction(0)), "y": mx.Num(Fraction(0))})
    assert p is not None


def test_lagrange():
    from academic_core.domain.engineering.mathlab import varias as MV

    pts = MV.lagrange(mx.parse("x^2+y^2"), mx.parse("x+y-1"), ["x", "y"])
    assert (Fraction(1, 2), Fraction(1, 2)) in [p for p, _ in pts]


def test_extremos_recinto():
    from academic_core.domain.engineering.mathlab import varias as MV

    r = MV.extremos_recinto(mx.parse("x^2+y^2"), ["x", "y"],
                            ("rectangulo", "-1", "1", "-1", "1"))
    assert r.minimo[1] == Fraction(0) and r.maximo[1] == Fraction(2)


def test_rechazos_honestos():
    from academic_core.domain.engineering.mathlab import varias as MV

    # silla de mono: (0, 0) es el único crítico; la Hessiana nula no decide y la
    # comparación de f en un entorno (valores mayores y menores) la da como silla
    pts = MV.puntos_criticos(mx.parse("x^3-3*x*y^2"), ["x", "y"])
    assert len(pts) == 1 and pts[0][0] == (Fraction(0), Fraction(0))
    assert pts[0][1].startswith("punto de silla")
    with pytest.raises(Exception, match="no están aisladas"):
        MV.puntos_criticos(mx.parse("(x-y)^2"), ["x", "y"])
    # el conjunto crítico no aislado se describe entero
    _, curvas = MV.conjunto_critico(mx.parse("(x-y)^2"), ["x", "y"])
    assert mx.text(curvas[0].ecuacion) == "x - y" and curvas[0].clase.startswith("mínimos")
    with pytest.raises(Exception, match="[Dd]iscriminante|no decide|semidefinida"):
        MV.hessiana(mx.parse("x^4+y^4"), ["x", "y"])


def test_calculadora_multivar():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("multivar", {"calculo": "limites", "expr": "x*y/(x^2+y^2)",
                                             "vars": ["x", "y"],
                                             "punto": {"x": "0", "y": "0"}}))
    assert r.sello.verdict == "verificado" and "no existe" in r.exacto
    r = ML.calcular(ML.Peticion("multivar", {"calculo": "lagrange", "expr": "x^2+y^2",
                                             "ligadura": "x+y-1", "vars": ["x", "y"]}))
    assert r.sello.verdict == "verificado" and "1/2" in r.exacto
    r = ML.calcular(ML.Peticion("multivar", {"calculo": "extremos", "expr": "x^2+y^2",
                                             "vars": ["x", "y"],
                                             "recinto": ["rectangulo", "-1", "1",
                                                         "-1", "1"]}))
    assert r.sello.verdict == "verificado"
    casos = [
        {"calculo": "direccional", "expr": "x^2+y^2", "vars": ["x", "y"],
         "punto": {"x": 1, "y": 1}, "direccion": [1, 0]},
        {"calculo": "jacobiana", "fs": ["x^2+y", "x*y"], "vars": ["x", "y"]},
        {"calculo": "cadena", "expr": "x^2*y", "sust": {"x": "t^2", "y": "t"}, "t": "t"},
        {"calculo": "implicita", "expr": "x^2+y^2-1", "x": "x", "y": "y"},
        {"calculo": "hessiana", "expr": "x^2+y^2", "vars": ["x", "y"]},
        {"calculo": "hessiana", "expr": "x^3+y^3", "vars": ["x", "y"],
         "punto": {"x": "1", "y": "1"}},
        {"calculo": "criticos", "expr": "x^2+x*y+y^2", "vars": ["x", "y"]},
        {"calculo": "taylor2", "expr": "exp(x+y)", "vars": ["x", "y"],
         "centro": {"x": "0", "y": "0"}},
    ]
    for entrada in casos:
        r = ML.calcular(ML.Peticion("multivar", entrada))
        assert r.sello.verdict == "verificado", (entrada["calculo"], r.exacto)


def test_errores_de_entrada_honestos():
    import academic_core.domain.engineering.mathlab as ML

    with pytest.raises(Exception, match="punto"):
        ML.calcular(ML.Peticion("multivar", {"calculo": "limites", "expr": "x"}))
    with pytest.raises(Exception, match="fs"):
        ML.calcular(ML.Peticion("multivar", {"calculo": "jacobiana", "vars": ["x"]}))
    with pytest.raises(Exception, match="centro"):
        ML.calcular(ML.Peticion("multivar", {"calculo": "taylor2", "expr": "x",
                                             "vars": ["x"], "centro": {}}))
    with pytest.raises(Exception, match="desconocido"):
        ML.calcular(ML.Peticion("multivar", {"calculo": "volar"}))


def test_bordes_robustos():
    from academic_core.domain.engineering.mathlab import varias as MV

    # sin puntos críticos: lista vacía, no error
    assert MV.puntos_criticos(mx.parse("x+y^2"), ["x", "y"]) == []
    # lagrange incompatible lineal: sin candidatos (1 = 0 en la 1.ª ecuación)
    assert MV.lagrange(mx.parse("x"), mx.parse("y"), ["x", "y"]) == []
    # recinto mal formado o vacío: motivo, no traceback suelto
    with pytest.raises(Exception, match="rectángulo|recinto"):
        MV.extremos_recinto(mx.parse("x"), ["x", "y"], ("disco", "0", "0", "1"))
    with pytest.raises(Exception, match="a < b"):
        MV.extremos_recinto(mx.parse("x"), ["x", "y"],
                            ("rectangulo", "1", "-1", "-1", "1"))
    # dirección nula o de dimensión errónea
    with pytest.raises(Exception, match="nulo"):
        MV.derivada_direccional(mx.parse("x"), ["x"], {"x": 0}, [0])
    with pytest.raises(Exception, match="tantas componentes"):
        MV.derivada_direccional(mx.parse("x+y"), ["x", "y"], {"x": 0, "y": 0}, [1])
    # dirección no unitaria se normaliza igual
    assert MV.derivada_direccional(mx.parse("x^2+y^2"), ["x", "y"],
                                  {"x": 1, "y": 1}, [2, 0]) == Fraction(2)
    # hessiana 3x3 definida
    _, c = MV.hessiana(mx.parse("x^2+y^2+z^2"), ["x", "y", "z"])
    assert c == "mínimo"


# ---------------------------------------------------------------------------
# no lineales (bases de Gröbner) y autovalores corregidos
# ---------------------------------------------------------------------------


def test_criticos_no_lineales():
    from academic_core.domain.engineering.mathlab import varias as MV

    pts = dict(MV.puntos_criticos(mx.parse("x^3-3*x+y^2"), ["x", "y"]))
    assert pts == {(Fraction(-1), Fraction(0)): "punto de silla",
                   (Fraction(1), Fraction(0)): "mínimo"}
    pts = MV.puntos_criticos(mx.parse("x*y*exp(-x^2-y^2)"), ["x", "y"])
    clases = sorted((round(MV._float(p[0]), 6), round(MV._float(p[1]), 6), c)
                    for p, c in pts)
    r = round(2 ** -0.5, 6)
    assert clases == [(-r, -r, "máximo"), (-r, r, "mínimo"), (0.0, 0.0, "punto de silla"),
                      (r, -r, "mínimo"), (r, r, "máximo")]
    # 3 variables con silla decidida por Descartes (Hessiana diag(2, −2, 2))
    pts = MV.puntos_criticos(mx.parse("x^2-y^2+z^2"), ["x", "y", "z"])
    assert pts == [((Fraction(0),) * 3, "punto de silla")]
    # coordenada sin forma exacta: numérica, no inventada
    pts = MV.puntos_criticos(mx.parse("x^4/4-2*x+y^2"), ["x", "y"])
    assert len(pts) == 1 and isinstance(pts[0][0][0], float)
    assert abs(pts[0][0][0] - 2 ** (1 / 3)) < 1e-9 and pts[0][1] == "mínimo"


def test_lagrange_no_lineal():
    from academic_core.domain.engineering.mathlab import varias as MV

    pts = MV.lagrange(mx.parse("x+y"), mx.parse("x^2+y^2-1"), ["x", "y"])
    valores = sorted(MV._float(v) for _, v in pts)
    assert [round(v, 9) for v in valores] == [round(-2 ** 0.5, 9), round(2 ** 0.5, 9)]
    pts = MV.lagrange(mx.parse("x*y*z"), mx.parse("x^2+y^2+z^2-3"), ["x", "y", "z"])
    assert len(pts) == 14
    assert max(MV._float(v) for _, v in pts) == 1 and min(MV._float(v) for _, v in pts) == -1
    # dos ligaduras: plano ∩ cilindro
    pts = MV.lagrange(mx.parse("z"), [mx.parse("x+y+z-1"), mx.parse("x^2+y^2-1")],
                      ["x", "y", "z"])
    assert sorted(round(MV._float(v), 9) for _, v in pts) == [
        round(1 - 2 ** 0.5, 9), round(1 + 2 ** 0.5, 9)]


def test_lagrange_aviso_ligadura_singular():
    from academic_core.domain.engineering.mathlab import varias as MV
    from academic_core.domain.engineering.mathlab.trace import Trace

    t = Trace()
    MV.lagrange(mx.parse("x"), mx.parse("y^2-x^3"), ["x", "y"], t)   # cúspide en (0,0)
    assert "mv.lagrange_singular" in t.to_text()   # (0, 0): el mínimo que Lagrange no ve


def test_autovalores_corregidos():
    from academic_core.domain.engineering.mathlab import algebra as AL

    F = Fraction
    assert [AL.texto_autovalor(v) for v in AL.autovalores([[2, -1], [3, 0]])] == [
        "1 + sqrt(2)·i", "1 − sqrt(2)·i"]
    assert AL.autovalores([[0, -1, 0], [1, 0, 0], [0, 0, 2]]) == [F(2), (F(0), F(1)),
                                                                  (F(0), F(-1))]
    assert AL.autovalores([[1, 1], [0, 1]]) == [F(1), F(1)]
    with pytest.raises(Exception, match="no diagonaliza"):
        AL.diagonalizar([[1, 1], [0, 1]])
    P, D = AL.diagonalizar([[2, 1, 1], [1, 2, 1], [1, 1, 2]])
    assert sorted(D) == [F(1), F(1), F(4)]
    # 4×4 por bloques y raíces cúbicas irreducibles: numéricas, nunca incompletas
    assert len(AL.autovalores([[1, 0, 0, 0], [0, 2, 0, 0], [0, 0, 0, -1], [0, 0, 1, 0]])) == 4
    with pytest.raises(Exception, match="sin forma exacta"):
        AL.autovalores([[0, 1, 0], [0, 0, 1], [2, 0, 0]])
    z = AL.autovalores_numericos([[0, 1, 0], [0, 0, 1], [2, 0, 0]])
    assert len(z) == 3 and all(abs(w ** 3 - 2) < 1e-9 for w in z)


def test_extremos_en_region():
    from academic_core.domain.engineering.mathlab import varias as MV

    r = MV.extremos_recinto(mx.parse("x^2+y^2-x"), ["x", "y"], ("region", "x^2+y^2-1"))
    assert r.minimo[1] == Fraction(-1, 4) and r.maximo[1] == Fraction(2)
    r = MV.extremos_recinto(mx.parse("x*y"), ["x", "y"], ("region", "x^2+4*y^2-8"))
    assert (r.minimo[1], r.maximo[1]) == (Fraction(-2), Fraction(2))
    with pytest.raises(Exception, match="no es acotado"):
        MV.extremos_recinto(mx.parse("x"), ["x", "y"], ("region", "y^2-x^3"))


def test_pseudoinversa_rango_deficiente():
    from academic_core.domain.engineering.mathlab import algebra as AL

    F = Fraction
    assert AL.pseudoinversa([[1, 1], [1, 1]]) == [[F(1, 4), F(1, 4)], [F(1, 4), F(1, 4)]]
    assert AL.pseudoinversa([[0, 0]]) == [[F(0)], [F(0)]]


def test_recinto_con_curva_de_criticos_y_lado_constante():
    from academic_core.domain.engineering.mathlab import varias as MV

    # x²y: los críticos son la recta x = 0 (valor 0); extremos en el borde
    r = MV.extremos_recinto(mx.parse("x^2*y"), ["x", "y"], ("rectangulo", "-1", "1", "-1", "1"))
    assert (r.minimo[1], r.maximo[1]) == (Fraction(-1), Fraction(1))
    # −2x − 2xy es constante (= 0) en el lado y = −1
    r = MV.extremos_recinto(mx.parse("-2*x-2*x*y"), ["x", "y"],
                            ("rectangulo", "-1", "1", "-1", "1"))
    assert (r.minimo[1], r.maximo[1]) == (Fraction(-4), Fraction(4))
    # f constante en la frontera del disco
    r = MV.extremos_recinto(mx.parse("x^2+y^2"), ["x", "y"], ("region", "x^2+y^2-2"))
    assert (r.minimo[1], r.maximo[1]) == (Fraction(0), Fraction(2))


def test_pasos_visibles():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("multivar", {"calculo": "criticos", "expr": "x^3-3*x+y^2"}))
    t = r.como_texto()
    assert "∂f/∂x = 3*x^2 - 3 = 0" in t and "x^2 - 1 = 0" in t
    assert "H en (1, 0) = [6, 0; 0, 2]; Δ1 = 6, Δ2 = 12" in t
    r = ML.calcular(ML.Peticion("multivar", {"calculo": "lagrange", "expr": "x+y",
                                             "ligadura": "x^2+y^2-1"}))
    assert "mayor valor sqrt(2)" in r.como_texto()
    with pytest.raises(Exception, match="x = 0"):
        MV_ = __import__("academic_core.domain.engineering.mathlab.varias", fromlist=["x"])
        MV_.puntos_criticos(mx.parse("x^2*y"), ["x", "y"])
