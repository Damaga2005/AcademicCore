# SPDX-License-Identifier: MIT
"""ML-9: probabilidad y estadística (§4.6, §8.2 G y los 15 tipos de §15.1).

SciPy solo como oráculo (nunca en el código del laboratorio); las pruebas que no
lo necesitan corren sin él. Los valores «de tabla» de §15.2 punto 9 (1,96; 2,576;
t₁₉ = 2,093…) son casos de prueba propios.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import estadistica as E
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import prob_basica as B
from academic_core.domain.engineering.mathlab import probabilidad as P
from academic_core.domain.engineering.mathlab import procesos as PR
from academic_core.domain.engineering.mathlab import va_continua as VC
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace


def pedir(op, entrada):
    r = ML.calcular(ML.Peticion(op, entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# tablas (§15.2 punto 9): calculadas, con los valores de las soluciones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ley,gl,p,tabla", [
    ("normal", {}, "0.975", "1,960"), ("normal", {}, "0.995", "2,576"),
    ("normal", {}, "0.95", "1,645"), ("t", {"gl": 19}, "0.975", "2,093"),
    ("t", {"gl": 9}, "0.975", "2,262"), ("chi2", {"gl": 9}, "0.05", "3,325"),
    ("chi2", {"gl": 9}, "0.95", "16,919"), ("f", {"d1": 4, "d2": 9}, "0.95", "3,633"),
])
def test_tablas_calculadas_con_su_redondeo(ley, gl, p, tabla):
    r = pedir("tabla_estadistica", {"ley": ley, "p": p, **gl})
    assert r.exacto["tabla"] == tabla
    assert r.sello.verdict == V.VERIFIED


def test_funciones_especiales_frente_a_scipy():
    st = pytest.importorskip("scipy.stats")
    for p in (1e-10, 0.001, 0.3, 0.5, 0.975, 1 - 1e-9):
        assert abs(P.Phi_inv(p) - st.norm.ppf(p)) < 1e-9 * max(1, abs(st.norm.ppf(p)))
    for nu in (1, 2, 5, 19, 30, 120):
        assert abs(P.distribucion("t", {"nu": nu}).cuantil(0.975) - st.t.ppf(0.975, nu)) < 1e-9
        assert abs(P.distribucion("t", {"nu": nu}).F(-1.3) - st.t.cdf(-1.3, nu)) < 1e-12
    for k in (1, 2, 7, 50):
        d = P.distribucion("chi2", {"k": k})
        assert abs(d.F(3.7) - st.chi2.cdf(3.7, k)) < 1e-12
        assert abs(d.cuantil(0.05) - st.chi2.ppf(0.05, k)) < 1e-8
    assert abs(P.distribucion("f", {"d1": 3, "d2": 11}).F(2.2) - st.f.cdf(2.2, 3, 11)) < 1e-12
    assert abs(P.distribucion("beta", {"a": "2.5", "b": "0.7"}).F(0.3)
               - st.beta.cdf(0.3, 2.5, 0.7)) < 1e-12
    assert abs(P.distribucion("gamma", {"k": "2.5", "lambda": "1.3"}).F(2)
               - st.gamma.cdf(2, 2.5, scale=1 / 1.3)) < 1e-12
    assert abs(P.distribucion("rice", {"nu": "1.5", "sigma": "0.8"}).F(1.2)
               - st.rice.cdf(1.2, 1.5 / 0.8, scale=0.8)) < 1e-12
    assert abs(P.marcum_q1(2.0, 1.5) - st.ncx2.sf(1.5 ** 2, 2, 2.0 ** 2)) < 1e-12


@pytest.mark.parametrize("nombre,params,x", [
    ("normal", {"mu": 1, "sigma": 2}, 2.3), ("t", {"nu": 4}, -1.1), ("chi2", {"k": 1}, 0.5),
    ("gamma", {"k": "2.5", "lambda": "1.3"}, 2.0), ("beta", {"a": 2, "b": 5}, 0.3),
    ("f", {"d1": 4, "d2": 9}, 1.7), ("weibull", {"k": "1.5", "lambda": 2}, 1.1),
    ("rayleigh", {"sigma": 1}, 1.0), ("rice", {"K": 3}, 0.8), ("laplace", {"b": 2}, -0.7),
])
def test_F_cerrada_frente_a_la_cuadratura_de_la_densidad(nombre, params, x):
    d = P.distribucion(nombre, params)
    assert abs(d.F(x) - P.F_por_cuadratura(d, x)) < 1e-7


# ---------------------------------------------------------------------------
# tipos 1, 2, 6 y 15: Bayes, discretas, exponencial, combinatoria
# ---------------------------------------------------------------------------


def test_bayes_exacto_con_arbol_y_simulacion():
    r = pedir("probabilidad", {"calculo": "bayes", "evidencia": "D",
                               "previas": {"A1": "0.5", "A2": "0.3", "A3": "0.2"},
                               "verosimilitudes": {"A1": "0.02", "A2": "0.03", "A3": "0.05"}})
    assert r.exacto["P(D)"] == "29/1000"
    assert r.exacto["P(A3 | D)"] == "10/29"
    assert r.sello.verdict == V.VERIFIED
    assert "árbol" in r.traza.to_text()


def test_bayes_rechaza_lo_que_no_es_una_particion():
    with pytest.raises(Exception, match="partición"):
        B.bayes({"A": "0.5", "B": "0.3"}, {"A": "0.1", "B": "0.2"})


@pytest.mark.parametrize("tipo,n,k,valor", [
    ("variaciones", 5, 3, 60), ("variaciones_rep", 3, 4, 81), ("combinaciones", 7, 3, 35),
    ("combinaciones_rep", 4, 3, 20), ("ocupacion_indistinguibles", 3, 4, 15),
    ("sobreyecciones", 3, 5, 150), ("desarreglos", 6, None, 265),
])
def test_combinatoria_frente_a_la_enumeracion(tipo, n, k, valor):
    c = B.combinatoria(tipo, n, k)
    assert c.valor == valor and c.enumerado == valor


def test_inclusion_exclusion_y_regiones_de_venn():
    r = B.inclusion_exclusion({"A": "1/2", "B": "2/5", "C": "3/10", "AB": "1/5", "AC": "1/10",
                               "BC": "1/10", "ABC": "1/20"})
    assert r["union"] == Fraction(17, 20)
    assert sum(r["regiones"].values()) == r["union"]
    assert r["independencia"]["AB"][0] and not r["independencia"]["AC"][0]
    with pytest.raises(Exception, match="incoherentes"):
        B.inclusion_exclusion({"A": "1/2", "B": "1/2", "AB": "3/5"})


@pytest.mark.parametrize("dist,params,suceso,exacto", [
    ("binomial", {"n": 10, "p": "0.3"}, "P(X<=3)", "406006699/625000000"),
    ("poisson", {"lambda": 2}, "P(X>=3)", "1 - 5*exp(-2)"),
    ("poisson", {"lambda": "1/2", "t": 4}, "P(1<X<=4)", "4*exp(-2)"),
    ("geometrica", {"p": "1/6"}, "P(X>3 | X>1)", "25/36"),
    ("hipergeometrica", {"N": 20, "K": 7, "n": 5}, "P(X=2)", "1001/2584"),
    ("exponencial", {"media": 5}, "P(X>8 | X>3)", "exp(-1)"),
    ("gamma", {"k": 3, "lambda": 2}, "P(X<=1)", "1 - 5*exp(-2)"),
    ("beta", {"a": 2, "b": 3}, "P(X<=1/2)", "11/16"),
])
def test_sucesos_exactos_de_las_leyes(dist, params, suceso, exacto):
    r = pedir("variable_aleatoria", {"dist": dist, "parametros": params, "suceso": suceso})
    obtenido = r.exacto[suceso]
    assert abs(float(mx.valor_real(mx.parse(obtenido), {}))
               - float(mx.valor_real(mx.parse(exacto), {}))) < 1e-14
    assert r.sello.verdict == V.VERIFIED
    assert "simulación" in r.traza.to_text()


def test_falta_de_memoria_de_la_geometrica_y_la_exponencial():
    g = pedir("variable_aleatoria", {"dist": "geometrica", "parametros": {"p": "1/6"},
                                     "suceso": "P(X>5 | X>3)"})
    g2 = pedir("variable_aleatoria", {"dist": "geometrica", "parametros": {"p": "1/6"},
                                      "suceso": "P(X>2)"})
    assert g.exacto["P(X>5 | X>3)"] == g2.exacto["P(X>2)"] == "25/36"


def test_convenciones_declaradas_cambian_el_resultado():
    t = Trace()
    a = P.distribucion("exponencial", {"media": 2}, t)
    b = P.distribucion("exponencial", {"lambda": 2})
    assert a.parametros["λ"] == Fraction(1, 2) and b.parametros["λ"] == 2
    assert "MEDIA" in t.to_text()
    n1 = P.distribucion("normal", {"mu": 0, "sigma": 4})
    n2 = P.distribucion("normal", {"mu": 0, "var": 4})
    assert n1.parametros["σ²"] == 16 and n2.parametros["σ²"] == 4
    g0 = P.distribucion("geometrica", {"p": "1/2", "desde": 0})
    assert g0.media_f() == 1 and P.distribucion("geometrica", {"p": "1/2"}).media_f() == 2


def test_cuantil_discreto_exacto_y_continuo_por_cuadratura():
    r = pedir("variable_aleatoria", {"dist": "binomial", "parametros": {"n": 10, "p": "0.3"},
                                     "cuantil": "0.9"})
    assert r.exacto["x_9/10"] == "5"
    r = pedir("variable_aleatoria", {"dist": "normal", "parametros": {"mu": 10, "sigma": 2},
                                     "cuantil": "0.975"})
    assert abs(float(r.exacto["x_39/40"]) - (10 + 2 * 1.959963984540054)) < 1e-9


# ---------------------------------------------------------------------------
# tipo 3: aproximación normal con corrección de continuidad
# ---------------------------------------------------------------------------


def test_de_moivre_laplace_al_lado_del_exacto():
    r = PR.aproximacion_normal("binomial", {"n": 100, "p": "0.3"}, "P(25<=X<=35)")
    assert abs(r.exacta - 0.7703512122767611) < 1e-12
    assert abs(r.aproximada - r.exacta) < 1e-3 < abs(r.sin_correccion - r.exacta)


# ---------------------------------------------------------------------------
# tipos 7 y 8: densidad con constante, Chebyshov, transformaciones
# ---------------------------------------------------------------------------


def test_densidad_con_constante_momentos_y_F():
    t = Trace()
    d = VC.lee_densidad([["k*x^2", "0", "1"], ["k*(2-x)", "1", "2"]], trace=t)
    assert mx.exact_value(d.valor_constante) == Fraction(6, 5)
    m = VC.momentos(d, t)
    assert mx.exact_value(m.media) == Fraction(11, 10)
    assert mx.exact_value(m.varianza) == Fraction(13, 100)
    F = VC.F_por_tramos(d, t)
    assert mx.valor_real(F[2][2], {"x": 1.5}) == pytest.approx(0.85)


def test_densidad_exponencial_con_constante_hasta_infinito():
    r = pedir("variable_aleatoria", {"densidad": [["c*exp(-2*x)", "0", "oo"]],
                                     "calculo": "momentos"})
    assert r.exacto["c"] == "2" and r.exacto["E[X]"] == "1/2" and r.exacto["Var X"] == "1/4"


def test_densidad_que_toma_valores_negativos_se_rechaza():
    with pytest.raises(Exception, match="negativos"):
        VC.lee_densidad([["k*(x-1/2)", "0", "2"]])


def test_chebyshov_frente_al_valor_exacto():
    r = pedir("variable_aleatoria", {"densidad": [["k*x^2", "0", "1"], ["k*(2-x)", "1", "2"]],
                                     "calculo": "chebyshov", "k": 2})
    assert r.exacto["cota de Chebyshov"] == "1/4"
    assert float(r.exacto["P(|X − μ| ≥ kσ)"]) < 0.25


@pytest.mark.parametrize("densidad,g,y,esperado", [
    ([["1/3", "-1", "2"]], "x^2", 0.5, 1 / 3 / math.sqrt(0.5)),      # dos ramas en (0, 1)
    ([["1/3", "-1", "2"]], "x^2", 2.0, 1 / 6 / math.sqrt(2.0)),      # una rama en (1, 4)
    ([["2*exp(-2*x)", "0", "oo"]], "exp(-x)", 0.4, 2 * 0.4),         # f_Y = 2y
    ([["exp(-x^2/2)/sqrt(2*pi)", "-oo", "oo"]], "x^2", 1.3,          # χ²₁
     math.exp(-1.3 / 2) / math.sqrt(2 * math.pi * 1.3)),
    ([["1/2", "-1", "1"]], "x^3", -0.2, 1 / 6 * 0.2 ** (-2 / 3)),
    ([["1", "0", "1"]], "-ln(x)", 1.7, math.exp(-1.7)),
])
def test_transformaciones_por_ramas_monotonas(densidad, g, y, esperado):
    T = VC.transforma(VC.lee_densidad(densidad), mx.parse(g), Trace())
    assert T.f(y) == pytest.approx(esperado, rel=1e-9)


def test_suma_por_convolucion_y_maximo():
    r = VC.convolucion(VC.lee_densidad([["1", "0", "1"]]), VC.lee_densidad([["1", "0", "1"]]),
                       Trace())
    assert [mx.text(e) for _, _, e in r] == ["z", "-z + 2"]
    r = VC.convolucion(VC.lee_densidad([["2*exp(-2*x)", "0", "oo"]]),
                       VC.lee_densidad([["3*exp(-3*x)", "0", "oo"]]), Trace())
    assert mx.valor_real(r[0][2], {"z": 0.7}) == pytest.approx(6 * (math.exp(-1.4) - math.exp(-2.1)))
    m = VC.maximo_minimo(VC.lee_densidad([["1", "0", "1"]]), 3, Trace())
    assert mx.text(m["max"][1][2]) == "x^3"


# ---------------------------------------------------------------------------
# tipos 9 y 10: vectores
# ---------------------------------------------------------------------------


def test_tabla_conjunta_incorreladas_no_independientes():
    c = B.tabla_conjunta([-1, 0, 1], [0, 1], [["1/6", "0"], ["0", "2/3"], ["1/6", "0"]])
    assert c.cov == 0 and not c.independientes


def test_estimacion_lineal_optima_y_esperanza_condicional():
    c = B.tabla_conjunta([-1, 0, 1], [0, 1], [["1/6", "1/6"], ["1/3", "0"], ["0", "1/3"]])
    assert c.recta == (Fraction(1, 2), Fraction(1, 4))
    assert c.condicionada == (Fraction(1, 2), Fraction(0), Fraction(1))


def test_vector_gaussiano_lineal_y_condicional():
    r = B.gaussiano_lineal([1, 2], [[4, 2], [2, 3]], [[1, 1], [1, -1]], [0, 1])
    assert r["cov"] == [[11, 1], [1, 3]] and r["media"] == [3, 0]
    c = B.gaussiano_condicional([0, 0, 1], [[4, 2, 1], [2, 3, 0], [1, 0, 2]], {"3": "2"})
    assert c["media"] == [Fraction(1, 2), 0]
    assert c["cov"] == [[Fraction(7, 2), 2], [2, 3]]
    with pytest.raises(Exception, match="semidefinida"):
        B.gaussiano_lineal([0, 0], [[1, 2], [2, 1]], [[1, 0], [0, 1]])


# ---------------------------------------------------------------------------
# tipos 4, 5 y 11: estadística
# ---------------------------------------------------------------------------


def test_descriptiva_exacta_con_las_dos_varianzas():
    d = E.descriptiva([2, 4, 4, 4, 5, 5, 7, 9])
    assert d.media == 5 and d.var_n == 4 and d.var_n1 == Fraction(32, 7)
    assert d.mediana == Fraction(9, 2)


def test_intervalo_t_de_student_y_su_eleccion_justificada():
    r = pedir("intervalo_confianza", {"parametro": "media", "n": 20, "media": "10.2", "s": "1.5"})
    lo, hi = (float(v) for v in r.exacto["intervalo"])
    assert lo == pytest.approx(9.49797839037012, abs=1e-9)
    assert hi == pytest.approx(10.902021609629879, abs=1e-9)
    assert r.exacto["tabla"]["t"] == "2,093"
    texto = r.traza.to_text()
    assert "σ desconocida" in texto and "cobertura" in texto


def test_intervalo_z_con_sigma_conocida_y_tamano_de_muestra():
    I = E.intervalo({"parametro": "media", "n": 16, "media": 5, "sigma": 2, "nivel": "0.99"})
    assert I.hi - 5 == pytest.approx(2.5758293035489 * 2 / 4, abs=1e-9)
    assert E.intervalo({"parametro": "tamano_proporcion", "error": "0.03"}).estimacion == 1068
    assert E.intervalo({"parametro": "tamano_media", "error": "0.5", "sigma": 3}).estimacion == 139


def test_intervalos_de_varianza_proporcion_y_diferencias_frente_a_scipy():
    st = pytest.importorskip("scipy.stats")
    I = E.intervalo({"parametro": "varianza", "n": 10, "media": 0, "s2": 4})
    assert I.lo == pytest.approx(9 * 4 / st.chi2.ppf(0.975, 9), rel=1e-10)
    assert I.hi == pytest.approx(9 * 4 / st.chi2.ppf(0.025, 9), rel=1e-10)
    I = E.intervalo({"parametro": "proporcion", "n": 200, "exitos": 46})
    assert I.lo == pytest.approx(0.23 - st.norm.ppf(0.975) * math.sqrt(0.23 * 0.77 / 200))
    I = E.intervalo({"parametro": "dif_medias", "grupo1": {"n": 12, "media": 20, "s": 3},
                     "grupo2": {"n": 15, "media": 18, "s": 4}})
    sp2 = (11 * 9 + 14 * 16) / 25
    assert I.hi - 2 == pytest.approx(st.t.ppf(0.975, 25) * math.sqrt(sp2 * (1 / 12 + 1 / 15)))


def test_contrastes_frente_a_scipy():
    st = pytest.importorskip("scipy.stats")
    c = E.contraste({"tipo": "media", "n": 25, "media": 52, "s": 5, "mu0": 50,
                     "alternativa": "mayor"})
    assert c.p_valor == pytest.approx(st.t.sf(2, 24), rel=1e-10) and c.rechaza
    c = E.contraste({"tipo": "independencia", "tabla": [[20, 30], [30, 20]]})
    chi, p, *_ = st.chi2_contingency([[20, 30], [30, 20]], correction=False)
    assert c.estadistico == pytest.approx(chi) and c.p_valor == pytest.approx(p)
    c = E.contraste({"tipo": "bondad", "observadas": [18, 22, 20, 25, 15, 20]})
    assert c.p_valor == pytest.approx(st.chisquare([18, 22, 20, 25, 15, 20]).pvalue)


def test_regresion_exacta_con_residuos_ortogonales():
    r = E.regresion([1, 2, 3, 4, 5], [2, 4, 5, 4, 5])
    assert (r.a, r.b, r.r2) == (Fraction(11, 5), Fraction(3, 5), Fraction(3, 5))
    assert sum(r.residuos) == 0


@pytest.mark.parametrize("familia,datos,clave,mom,mv", [
    ("poisson", [2, 3, 1, 4, 0, 2], "λ", Fraction(2), Fraction(2)),
    ("exponencial", ["0.5", "1.2", "0.3", "2.1"], "λ", Fraction(40, 41), Fraction(40, 41)),
    ("uniforme", ["0.2", "1.7", "0.9", "1.1"], "θ", Fraction(39, 20), Fraction(17, 10)),
    ("normal", [1, 2, 3, 4, 6], "σ²", Fraction(74, 25), Fraction(74, 25)),
])
def test_estimadores_momentos_y_maxima_verosimilitud(familia, datos, clave, mom, mv):
    e = E.estimadores(familia, datos)
    assert e.momentos[clave] == mom and e.mv[clave] == mv


def test_estimador_de_una_densidad_con_parametro():
    xs = [0.3, 0.8, 0.6, 0.9, 0.7]
    e = E.estimadores("densidad", xs, params={"f": "t*x^(t-1)", "parametro": "t", "desde": 0,
                                              "hasta": 1, "rango": ["0.1", "20"]})
    assert e.mv["t"] == pytest.approx(-5 / sum(math.log(x) for x in xs), rel=1e-6)
    m = sum(xs) / 5
    assert e.momentos["t"] == pytest.approx(m / (1 - m), rel=1e-6)


# ---------------------------------------------------------------------------
# tipos 12, 13 y 14: procesos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("consulta,datos,valor", [
    ("conteo", {"t": 2, "k": 3}, 4.5 * math.exp(-3)),
    ("dos_tiempos", {"t1": 1, "t2": 3, "a": 1, "b": 4}, 6.75 * math.exp(-4.5)),
    ("condicionada", {"s": 1, "t": 4, "a": 1, "b": 3}, 27 / 64),
    ("llegada", {"k": 3, "t": 2}, 1 - 8.5 * math.exp(-3)),
])
def test_proceso_de_poisson(consulta, datos, valor):
    r = PR.poisson_proceso({"lambda": "1.5", "consulta": consulta, **datos})
    assert r["valor"] == pytest.approx(valor, rel=1e-12)


def test_paseo_pm1_contra_la_enumeracion_de_caminos():
    t = Trace()
    r = PR.paseo({"tipo": "pm1", "p": "2/3", "n": 6, "m": 4, "k": 2}, t)
    assert r["media"] == 2 and r["varianza"] == Fraction(16, 3) and r["P"] == Fraction(80, 243)
    assert "enumeración exacta" in t.to_text()
    assert PR.paseo({"tipo": "pm1", "p": "1/2", "n": 5, "k": 2})["P"] == 0   # paridad


@pytest.mark.parametrize("X,variables,media,R_tau,estacionario", [
    ("cos(w*t+x)", {"x": {"tipo": "uniforme", "a": "0", "b": "2*pi"}}, "0", "cos(w*τ)/2", True),
    ("A*cos(2*t+x)", {"A": {"tipo": "discreta", "valores": [1, -1], "p": ["1/2", "1/2"]},
                      "x": {"tipo": "uniforme", "a": "0", "b": "2*pi"}}, "0", "cos(2*τ)/2", True),
    ("A*cos(t)+B*sin(t)", {"A": {"tipo": "normal", "var": 2}, "B": {"tipo": "normal", "var": 2}},
     "0", "2*cos(τ)", True),
    ("cos(w*t+x)", {"x": {"tipo": "uniforme", "a": "0", "b": "pi"}}, "-2*sin(t*w)/pi", None, False),
])
def test_procesos_construidos_con_variables(X, variables, media, R_tau, estacionario):
    r = PR.proceso_va(X, variables)
    assert mx.text(r.media) == media
    assert r.estacionario is estacionario
    if R_tau:
        assert mx.text(r.R_tau) == R_tau


# ---------------------------------------------------------------------------
# comunicaciones (D12)
# ---------------------------------------------------------------------------


def test_ber_aloha_desvanecimiento_y_arq():
    assert PR.ber("bpsk", 6)["P_b"] == pytest.approx(0.5 * math.erfc(math.sqrt(10 ** 0.6)))
    assert PR.ber("bpsk", objetivo=1e-5)["EbN0_dB"] == pytest.approx(9.5879, abs=1e-3)
    assert PR.ber("bpsk_rayleigh", 10)["P_b"] == pytest.approx(0.5 * (1 - math.sqrt(10 / 11)))
    assert PR.aloha(0.5, False)["S"] == pytest.approx(1 / (2 * math.e))
    assert PR.aloha(1, True)["S"] == pytest.approx(1 / math.e)
    assert PR.desvanecimiento({"modelo": "rayleigh", "snr_media_db": 20, "umbral_db": 10}
                              )["P_fallo"] == pytest.approx(1 - math.exp(-0.1))
    assert PR.arq({"protocolo": "parada_espera", "P": "0.1", "a": 2})["U"] == pytest.approx(0.18)
    assert PR.arq({"protocolo": "retroceso_n", "P": "0.1", "a": 2, "N": 7})["U"] == \
        pytest.approx(0.9 / 1.4)
    assert PR.arq({"protocolo": "repeticion_selectiva", "P": "0.1", "a": 2, "N": 2})["U"] == \
        pytest.approx(2 * 0.9 / 5)


# ---------------------------------------------------------------------------
# contrato: un segundo camino que discrepa da el sello, no una excepción
# ---------------------------------------------------------------------------


def test_un_segundo_camino_que_discrepa_da_el_sello_discrepa(monkeypatch):
    def roto(*_a, **_k):
        raise C.error("DISCREPANT", "plantado")
    monkeypatch.setattr(B, "bayes", roto)
    r = ML.calcular(ML.Peticion("probabilidad", {"calculo": "bayes", "previas": {},
                                                 "verosimilitudes": {}}))
    assert r.sello.verdict == V.DISCREPANT and "plantado" in r.sello.detail
    assert C.validar_forma(r) == []


def test_montecarlo_con_la_semilla_de_la_peticion_es_reproducible():
    e = {"dist": "exponencial", "parametros": {"lambda": 2}, "suceso": "P(X>1)", "muestras": 5000}
    a = ML.calcular(ML.Peticion("montecarlo", e, semilla=7))
    b = ML.calcular(ML.Peticion("montecarlo", e, semilla=7))
    c = ML.calcular(ML.Peticion("montecarlo", e, semilla=8))
    assert a.aproximado == b.aproximado != c.aproximado
    assert a.sello.verdict == V.NUMERIC_ONLY


def test_bateria_aleatoria_de_leyes_frente_a_scipy():
    """120 leyes y sucesos sembrados: P(a < X ≤ b) (también su forma exacta), cuantil,
    media y varianza frente a scipy.stats. 0 errores tolerados."""
    import random

    st = pytest.importorskip("scipy.stats")
    rng = random.Random(9)
    for _ in range(120):
        kind = rng.choice(["binomial", "poisson", "geometrica", "hipergeometrica", "normal", "t",
                           "chi2", "f", "gamma", "beta", "weibull", "exponencial", "rayleigh"])
        if kind == "binomial":
            n, p = rng.randint(1, 60), Fraction(rng.randint(1, 19), 20)
            d, o = P.distribucion(kind, {"n": n, "p": p}), st.binom(n, float(p))
        elif kind == "poisson":
            lam = Fraction(rng.randint(1, 60), 4)
            d, o = P.distribucion(kind, {"lambda": lam}), st.poisson(float(lam))
        elif kind == "geometrica":
            p = Fraction(rng.randint(1, 19), 20)
            d, o = P.distribucion(kind, {"p": p}), st.geom(float(p))
        elif kind == "hipergeometrica":
            N = rng.randint(2, 40)
            K, m = rng.randint(0, N), rng.randint(1, N)
            d, o = P.distribucion(kind, {"N": N, "K": K, "n": m}), st.hypergeom(N, K, m)
        elif kind == "normal":
            mu, s = rng.randint(-5, 5), Fraction(rng.randint(1, 30), 10)
            d, o = P.distribucion(kind, {"mu": mu, "sigma": s}), st.norm(mu, float(s))
        elif kind in ("t", "chi2"):
            v = rng.randint(1, 40)
            d = P.distribucion(kind, {"nu": v} if kind == "t" else {"k": v})
            o = st.t(v) if kind == "t" else st.chi2(v)
        elif kind == "f":
            a, b = rng.randint(1, 20), rng.randint(1, 30)
            d, o = P.distribucion(kind, {"d1": a, "d2": b}), st.f(a, b)
        elif kind == "gamma":
            k, lam = Fraction(rng.randint(1, 40), 4), Fraction(rng.randint(1, 20), 5)
            d, o = P.distribucion(kind, {"k": k, "lambda": lam}), st.gamma(float(k), scale=1 / float(lam))
        elif kind == "beta":
            a, b = Fraction(rng.randint(1, 30), 5), Fraction(rng.randint(1, 30), 5)
            d, o = P.distribucion(kind, {"a": a, "b": b}), st.beta(float(a), float(b))
        elif kind == "weibull":
            k, lam = Fraction(rng.randint(3, 30), 5), Fraction(rng.randint(1, 20), 5)
            d, o = P.distribucion(kind, {"k": k, "lambda": lam}), st.weibull_min(float(k), scale=float(lam))
        elif kind == "exponencial":
            lam = Fraction(rng.randint(1, 20), 5)
            d, o = P.distribucion(kind, {"lambda": lam}), st.expon(scale=1 / float(lam))
        else:
            s = Fraction(rng.randint(1, 20), 5)
            d, o = P.distribucion(kind, {"sigma": s}), st.rayleigh(scale=float(s))
        lo, hi = sorted(o.ppf(rng.uniform(0.01, 0.99)) for _ in range(2))
        if d.discreta:
            lo, hi = math.floor(lo), math.floor(hi)
        lo, hi = Fraction(lo).limit_denominator(100), Fraction(hi).limit_denominator(100)
        v, ex = P.probabilidad_intervalo(d, P.Intervalo(lo, False, hi, True))
        ref = o.cdf(float(hi)) - o.cdf(float(lo))
        assert abs(v - ref) < 1e-9, (d.titulo(), lo, hi)
        if ex is not None:
            assert abs(P.valor_de(ex) - ref) < 1e-9, (d.titulo(), P.texto_exacto(ex))
        p = rng.uniform(0.02, 0.98)
        q = d.cuantil(p)
        if d.discreta:
            assert q == o.ppf(p), (d.titulo(), p)
        else:
            assert abs(q - o.ppf(p)) < 1e-7 * max(1, abs(q)), (d.titulo(), p)
        mu, var = d.media_f(), d.varianza_f()
        if mu is not None:          # t con ν = 1, F con d2 ≤ 2: no existe
            assert abs(float(mu) - o.mean()) < 1e-8 * max(1, abs(o.mean()))
        if var is not None:
            assert abs(float(var) - o.var()) < 1e-7 * max(1, o.var())


def test_geometrica_p_pequena_no_cuelga():
    """Cola geométrica con p pequeña (PPE): la densidad float no cuelga."""
    import time
    t0 = time.time()
    r = pedir("variable_aleatoria", {"dist": "geometrica",
                                     "parametros": {"p": "0.0081"},
                                     "suceso": "P(X>123)"})
    assert time.time() - t0 < 60
    assert r.sello.verdict == V.VERIFIED
    assert "0.3677" in str(r.exacto)


def test_poisson_mayor_vs_mayor_igual():
    """P(Y ≥ 2) ≠ P(Y > 2): el motor los distingue (errata PPE)."""
    import math
    a = pedir("variable_aleatoria", {"dist": "poisson",
                                     "parametros": {"lambda": "0.81"},
                                     "suceso": "P(X>=2)"})
    b = pedir("variable_aleatoria", {"dist": "poisson",
                                     "parametros": {"lambda": "0.81"},
                                     "suceso": "P(X>2)"})
    assert str(a.exacto) != str(b.exacto)
    assert abs(1 - 2.13805 * math.exp(-0.81) - 0.0489) < 1e-3
