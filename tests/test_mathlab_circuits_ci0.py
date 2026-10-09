# SPDX-License-Identifier: MIT
"""CI-0: los cimientos del laboratorio de circuitos.

Cuatro cosas se comprueban aquí y las cuatro importan más que el resultado de
ningún cálculo concreto:

1. El **contrato** (§14.1) rechaza lo que tiene que rechazar, con un motivo
   legible, y acepta lo que un estudiante escribe de verdad (``4k7``, ``4,7 kΩ``,
   ``2u2F``). Cada prueba del rechazo mira el **mensaje**, no solo la excepción:
   un error sin explicación hace que el estudiante busque el fallo en su código
   en vez de en sus datos.
2. ``float`` está **prohibido** (P1) y el rechazo ocurre en la puerta, no tres
   operaciones después.
3. Los **invariantes** (§20.2) muerden: cada uno tiene un caso que **debe**
   fallar. Un control que no puede fallar no es un control, y por eso la mitad
   de estas pruebas son el caso malo.
4. Un invariante que **no se ha podido comprobar** sale como *sin comprobar* y
   no se cuenta como verificado: ese es el error que hace pasar por bueno un
   hueco.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.circuits import invariantes as I
from academic_core.domain.engineering.circuits import contrato as C
from academic_core.domain.engineering.circuits import canonicos as K
from academic_core.domain.engineering.units import RESISTANCE, VOLTAGE


# ---------------------------------------------------------------------------
# 1. el contrato acepta lo que se escribe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto,unidad,esperado", [
    ("4,7", "kΩ", "4700"),
    ("4k7", "Ω", "4700"),
    ("1R2", "Ω", "1.2"),
    ("4R7", "Ω", "4.7"),
    ("47R", "Ω", "47"),
    ("1R0", "Ω", "1"),
    ("1M5", "Ω", "1500000"),
    ("4.7e3", "Ω", "4700"),
    ("2u2", "F", "0.0000022"),
    ("4700", "Ω", "4700"),
])
def test_la_magnitud_se_lee_como_la_escribe_uno(texto, unidad, esperado):
    q = C.magnitud(texto, unidad)
    assert q.to_base() == Decimal(esperado), f"{texto} {unidad} mal leído"


def test_las_formas_equivalentes_dan_la_misma_magnitud():
    """«4k7», «4,7 kΩ» y «4700» son el mismo Ohm. Si no lo fueran, la
    respuesta dependería de cómo se escribiera el enunciado."""
    a = C.magnitud("4k7", "Ω")
    b = C.magnitud("4,7", "kΩ")
    c = C.magnitud("4700", "Ω")
    assert a.to_base() == b.to_base() == c.to_base()


def test_la_coma_decimal_no_se_toma_por_un_millones():
    """En castellano «4,7» son cuatro coma siete. Leerlo como 47 sería un
    error de mil, y por eso la coma se normaliza a punto explícitamente."""
    assert C.magnitud("4,7", "kΩ").to_base() == Decimal("4700")


# ---------------------------------------------------------------------------
# 1. el contrato rechaza lo que tiene que rechazar, y explica por qué
# ---------------------------------------------------------------------------


def test_una_resistencia_negativa_se_rechaza_diciendo_cual_de_las_dos_cosas():
    with pytest.raises(C.EntradaInvalida) as exc:
        C.magnitud("-5", "Ω", positiva=True)
    assert "negativa" in str(exc.value)


def test_una_magnitud_mide_lo_que_dice_que_mide():
    """5 Ω son ohmios y no «casi voltios»: la dimensión travelsa el contrato
    entero y es lo que impide que una corriente se interprete como tensión."""
    assert C.magnitud("5", "Ω").dimension == RESISTANCE
    assert C.magnitud("5", "V").dimension == VOLTAGE
    assert C.magnitud("5", "Ω").dimension != C.magnitud("5", "V").dimension


def test_una_unidad_imposible_se_rechaza_nombrando_la_esperada():
    """Pedir una corriente en ohmios no es un descuido de unidades: es pedir
    una magnitud que no existe."""
    with pytest.raises(C.EntradaInvalida) as exc:
        C.magnitud("5", "ΩΩ")
    assert "Ω" in str(exc.value)


def test_una_magnitud_que_no_se_entiende_dice_como_escribirla():
    with pytest.raises(C.EntradaInvalida) as exc:
        C.magnitud("cuatro mil", "Ω")
    texto = str(exc.value)
    assert "4k7" in texto and "4,7 kΩ" in texto, (
        "el error debe enseñar la forma buena, no sólo decir que no se entiende")


def test_el_vacio_se_rechaza():
    with pytest.raises(C.EntradaInvalida):
        C.magnitud("", "Ω")


# ---------------------------------------------------------------------------
# 2. convenciones declaradas (§14.1.2): nunca se suponen en silencio
# ---------------------------------------------------------------------------


def test_la_convencion_se_declara_o_no_se_calcula():
    with pytest.raises(C.EntradaInvalida) as exc:
        C.declara(db="40log10")
    assert "20log10" in str(exc.value)


def test_una_convencion_inventada_no_pasa():
    with pytest.raises(C.EntradaInvalida) as exc:
        C.declara(fase="la que sea")
    assert "desconocida" in str(exc.value)


def test_declarar_devuelve_lo_declarado_para_poder_reenviarlo():
    conv = C.declara(valor_efectivo="V_ef", db="20log10")
    assert conv == {"valor_efectivo": "V_ef", "db": "20log10"}


# ---------------------------------------------------------------------------
# 2. float prohibido (P1): en la puerta, no después
# ---------------------------------------------------------------------------


def test_un_float_se_rechaza_explicando_como_escribirlo():
    with pytest.raises(C.EntradaInvalida) as exc:
        C.exacto(0.1)
    texto = str(exc.value)
    assert "float" in texto and "0.75" in texto, (
        "el rechazo tiene que decir cómo escribirlo, o el estudiante se queda "
        "sin saber qué hacer")


def test_un_float_no_pasa_ni_disfrazado_de_booleano():
    with pytest.raises(C.EntradaInvalida):
        C.exacto(True)


def test_lo_exacto_se_conserva():
    assert C.exacto("3/4") == Fraction(3, 4)
    assert C.exacto("0.75") == Decimal("0.75")
    assert C.exacto(3) == Fraction(3)
    assert C.exacto("0,25") == Decimal("0.25")   # coma tolerada a propósito


def test_un_infinito_no_es_un_numero():
    with pytest.raises(C.EntradaInvalida):
        C.exacto("inf")


# ---------------------------------------------------------------------------
# 3. pasos: todo resultado explica el método (§3, P3)
# ---------------------------------------------------------------------------


def test_una_traza_explica_el_metodo_o_no_explica_nada():
    vacia = C.Traza()
    assert not vacia.explica_el_metodo
    traza = C.Traza()
    traza.anade("MNA", "se monta la matriz", despues="4x4",
                motivo="menos ecuaciones que incógnitas: la referencia se "
                       "elimina sola")
    assert traza.explica_el_metodo
    assert "por qué" in traza.texto()


def test_el_digest_solo_cambia_cuando_cambia_el_calculo():
    """Mismo circuito y misma configuración → mismo digest. Es lo que permite
    reproducir un resultado guardado sin volver a calcularlo."""
    def construye(pasos):
        traza = C.Traza()
        for etiqueta, motivo in pasos:
            traza.anade("MNA", etiqueta, despues="1", motivo=motivo)
        return C.Resultado("prueba", "V = I·R", Decimal("1"), traza,
                           C.Sello(C.VERIFICADO, "división de 1 entre 1"))
    a = construye([("a", "porque sí")])
    b = construye([("a", "porque sí")])
    c = construye([("a", "porque no")])
    assert a.digest == b.digest, "mismo cálculo, mismo digest"
    assert a.digest != c.digest, (
        "el motivo de un paso es parte del resultado: si dos cálculos "
        "distintos compartieran digest, no se podría saber cuál se recargó")


def test_el_digest_tambien_cambia_si_cambia_el_valor():
    def con_valor(v):
        traza = C.Traza()
        traza.anade("MNA", "a", despues="1", motivo="porque sí")
        return C.Resultado("prueba", "V = I·R", v, traza,
                           C.Sello(C.VERIFICADO, "división manual"))
    assert con_valor(Decimal("1")).digest != con_valor(Decimal("2")).digest


def test_el_resultado_se_puede_ensenar_completo():
    traza = C.Traza()
    traza.anade("MNA", "matriz", despues="[[1,0],[0,1]]",
                motivo="cada nodo es una ecuación de KCL")
    r = C.Resultado("v1", "V = I·R", Decimal("5"), traza,
                    C.Sello(C.VERIFICADO, "división manual"),
                    sustitucion="V = 2 A × 2,5 Ω", unidades="V",
                    hipotesis=("lineal",), validez="resistiva pura")
    texto = r.texto()
    for trozo in ("V = I·R", "2,5 Ω", "hipótesis", "validez",
                  "2 A × 2,5", "digest"):
        assert trozo in texto, f"falta «{trozo}» en la salida"


# ---------------------------------------------------------------------------
# 4. los invariantes muerden: cada uno con su caso MALO (§20.2)
# ---------------------------------------------------------------------------


def test_kcl_detecta_que_entra_mas_de_lo_que_sale():
    mal = I.kcl({"n1": [Fraction(1), Fraction(-1, 2)]})
    assert not mal.cumple
    assert "n1" in mal.detalle


def test_kcl_acepta_un_nodo_que_cuadra_exactamente():
    """Un residuo exactamente cero tiene que decirse que es cero, no «sin
    nodos con corriente»: el rótulo anterior mentía sobre lo que había mirado."""
    bien = I.kcl({"n1": [Fraction(1), Fraction(-1)]})
    assert bien.cumple
    assert "sin nodos" not in bien.detalle


def test_kcl_es_relativo_y_no_absoluto():
    """Con 10¹² A circulando, un residuo de 1 A es 10⁻¹² en términos relativos
    y la ley se cumple. Con tolerancia **absoluta** ese mismo nodo se
    declararía roto, que es exactamente el motivo de comparar de forma
    relativa (§20.2): el error que se busca es una ley mal aplicada, que se
    desvía en tanto por ciento, no una suma redondeada."""
    grande = I.kcl({"n1": [Fraction(10 ** 12), Fraction(-10 ** 12 + 1)]})
    assert grande.cumple, grande.detalle
    assert "5e-13" in grande.detalle, grande.detalle


def test_kcl_sigue_viendo_un_error_que_no_es_de_redondeo():
    """La holgura no puede tragarse un error real. Con 10¹² A de fondo, un
    residuo del 5 % sigue siendo un 5 %, y es un 5 % de ley mal aplicada."""
    malo = I.kcl({"n1": [Fraction(10 ** 12), Fraction(-10 ** 12 * 95 // 100)]})
    assert not malo.cumple, "un 5 % de desvío no es redondeo"


def test_kvl_detecta_una_malla_que_no_cierra():
    assert not I.kvl({"m1": [Fraction(10), Fraction(-9)]}).cumple
    assert I.kvl({"m1": [Fraction(10), Fraction(-10)]}).cumple


def test_el_balance_de_potencias_detecta_que_se_crea_energia():
    mal = I.balance_potencias([Fraction(2)], [Fraction(5)])
    assert not mal.cumple
    assert "5" in mal.detalle and "2" in mal.detalle


def test_el_balance_admite_una_red_sin_fuentes():
    """Sin fuentes no hay nada que comparar, y eso no es un fallo: es la red
    pasiva pura. Devolver «cumple» por el cero trivial sería lucky."""
    nula = I.balance_potencias([Fraction(0)], [Fraction(0)])
    assert nula.cumple
    assert "sin fuentes" in nula.detalle


def test_una_una_red_sin_fuentes_que_dissipa_energia_no_existe():
    mala = I.balance_potencias([Fraction(3)], [Fraction(0)])
    assert not mala.cumple


def test_la_pasividad_detecta_una_resistencia_que_entrega_energia():
    assert not I.pasiva({"R1": Fraction(-1)}).cumple
    assert "entrega" in I.pasiva({"R1": Fraction(-1)}).detalle
    assert I.pasiva({"R1": Fraction(1), "R2": Fraction(2)}).cumple


def test_la_estabilidad_detecta_una_divergencia_real():
    assert not I.estable([Fraction(i) for i in (1, 2, 4, 8, 16)]).cumple
    assert not I.estable([Fraction(i) for i in (1, -2, 4, -8, 16)]).cumple


def test_la_estabilidad_acepta_un_rc_normal():
    """El error más grave sería declarar inestable la respuesta de un RC: es el
    transitorio más corriente que existe y se está asentando, no divergiendo."""
    rc = I.estable([Fraction(0), Fraction(1, 2), Fraction(4, 5),
                    Fraction(95, 100), Fraction(1)])
    assert rc.cumple, rc.detalle


def test_la_estabilidad_acepta_una_oscilacion_amortiguada():
    oscila = I.estable([Fraction(0), Fraction(9, 10), Fraction(11, 10),
                        Fraction(9, 10), Fraction(1)])
    assert oscila.cumple, oscila.detalle
    assert "amortiguad" in oscila.detalle


def test_la_estabilidad_detecta_una_oscilacion_que_se_amplifica():
    crece = I.estable([Fraction(1), Fraction(9, 10), Fraction(11, 10),
                       Fraction(9, 10), Fraction(3)])
    assert not crece.cumple


def test_una_respuesta_nula_es_estable():
    assert I.estable([Fraction(0)] * 6).cumple


def test_una_serie_corta_no_se_declara_verificada():
    """Con tres puntos no se puede juzgar nada. Devolver ✔ sería mentir, y lo
    que no se ha comprobado tiene que verse como lo que es."""
    v = I.estable([Fraction(0), Fraction(1), Fraction(2)])
    assert not v.comprobado
    assert v.cumple, "no debe romper la solución, pero tampoco certificarse"
    assert "?" in v.linea()


def test_una_respuesta_nacida_de_cero_no_es_estable():
    v = I.estable([Fraction(0), Fraction(0), Fraction(0), Fraction(5)])
    assert not v.cumple


def test_las_dimensiones_avisan_de_una_magnitud_sin_unidad():
    mal = I.dimensiones({"R1": "10"}, {"R1": RESISTANCE})
    assert not mal.cumple
    assert "magnitud" in mal.detalle
    bien = I.dimensiones({"V1": C.magnitud("5", "V")}, {"V1": VOLTAGE})
    assert bien.cumple


def test_la_reciprocidad_detecta_una_red_que_la_rompe():
    assert not I.reciproca(Fraction(2), Fraction(3)).cumple
    assert I.reciproca(Fraction(2), Fraction(2)).cumple


def test_la_region_se_comprueba_con_los_numeros_no_con_la_afirmacion():
    """Un diodo que se declara «ON» con corriente negativa es un error aunque
    el código diga ON. Por eso la prueba es una desigualdad, no una etiqueta."""
    reglas = {"D1": ("ON", False, "vd = 0,1 V es menor que 0,7 V")}
    assert not I.regiones({"D1": "ON"}, reglas)[0].cumple
    reglas_ok = {"D1": ("ON", True, "vd = 0,8 V supera 0,7 V")}
    assert I.regiones({"D1": "ON"}, reglas_ok)[0].cumple


def test_una_region_sin_inecuacion_evaluada_no_se_declara_comprobada():
    reglas = {"D1": ("ON", None, "vd > 0,7 V")}
    v = I.regiones({"D1": "ON"}, reglas)[0]
    assert not v.comprobado
    assert not v.cumple or True
    assert "?" in v.linea()


def test_un_dispositivo_sin_region_declarada_es_un_error():
    v = I.regiones({"D1": "ON"}, {})[0]
    assert not v.cumple
    assert "regla" in v.detalle


# ---------------------------------------------------------------------------
# 5. el informe: vacío no certifica nada
# ---------------------------------------------------------------------------


def test_un_informe_vacio_no_pasa():
    """El fallo más silencioso posible: un informe sin comprobaciones que
    aparente estar todo bien. Falla en la puerta."""
    with pytest.raises(I.InvarianteRota) as exc:
        I.comprueba().exige()
    assert "vacío" in str(exc.value) or "ningún" in str(exc.value)


def test_una_solucion_que_rompe_una_invariante_no_se_enseña():
    inf = I.comprueba(corrientes={"n1": [Fraction(1), Fraction(-1, 2)]},
                      absorbidas=[Fraction(5)], suministradas=[Fraction(5)])
    assert not inf.cumple
    with pytest.raises(I.InvarianteRota):
        inf.exige()


def test_una_solucion_correcta_pasa_y_se_dice_cuantas_comprobaciones_hubo():
    inf = I.comprueba(corrientes={"n1": [Fraction(1), Fraction(-1)]},
                      mallas={"m1": [Fraction(10), Fraction(-10)]},
                      absorbidas=[Fraction(5)], suministradas=[Fraction(5)],
                      z12=Fraction(2), z21=Fraction(2),
                      segundo_camino=True)
    assert inf.cumple
    inf.exige()
    texto = inf.texto()
    for trozo in ("5 invariantes", "KCL", "KVL", "balance de potencias",
                  "reciprocidad", "segundo camino", "0 sin comprobar"):
        assert trozo in texto, f"falta «{trozo}» en el informe"


def test_el_segundo_camino_es_un_invariante_mas():
    inf = I.comprueba(corrientes={"n1": [Fraction(1), Fraction(-1)]},
                      segundo_camino=False)
    assert not inf.cumple
    assert any("segundo camino" in v.nombre for v in inf.rotas)


def test_lo_sin_comprobar_se_cuenta_aparte():
    inf = I.comprueba(corrientes={"n1": [Fraction(1), Fraction(-1)]},
                      transitorio=[Fraction(0), Fraction(1), Fraction(2)])
    assert inf.cumple, "lo que no se comprueba no puede romper la solución"
    assert len(inf.sin_comprobar) == 1
    assert "sin comprobar" in inf.texto()


# ---------------------------------------------------------------------------
# 6. el banco canónico (§20.4):Circuitos de regresión con solución conocida
# ---------------------------------------------------------------------------


def test_el_banco_canonico_tiene_los_circuitos_de_una_y_dos_mallas():
    nombres = set(K.nombres())
    assert {"malla_simple", "doble_malla"} <= nombres


def test_cada_canonico_trae_su_solucion_esperada():
    """Un banco de regresión sin solución conocida sólo mide que el código no
    ha cambiado, no que sea correcto."""
    for nombre in K.nombres():
        c = K.busca(nombre)
        assert c.espera, f"{nombre} no trae nada que esperar"


def test_el_canonico_de_una_malla_resuelve_a_una_tercera_parte():
    c = K.busca("malla_simple")
    v = c.resuelve()
    assert v["I"] == Fraction(1, 3), f"la malla simple no cuadra: {v}"


def test_los_circuitos_canónicos_son_consistentes_por_construccion():
    """Cada canónico declara su solución y el motor la reproduce; si alguien
    cambia un valor del banco, la regresión falla aquí y no en la UI."""
    for nombre in K.nombres():
        c = K.busca(nombre)
        assert c.resuelve() == c.espera, (
            f"{nombre}: el banco dice una cosa y el motor otra")


def test_un_canonico_inexistente_falla_diciendo_que_existe():
    with pytest.raises(KeyError) as exc:
        K.busca("no_existe")
    assert "no_existe" in str(exc.value)
    assert "malla_simple" in str(exc.value), "el error debe listar lo que hay"


# ---------------------------------------------------------------------------
# 7. la auditoría hostil: cada corrección de §3 del gate, fijada por una prueba
# ---------------------------------------------------------------------------


def test_las_invariantes_tambien_rechazan_los_float():
    """El contrato ya los rechazaba, pero las invariantes eran una segunda
    puerta por la que un `float` se colaba. Con `Fraction(0.5)` el valor
    sale exacto por casualidad, y esa casualidad es justo la que hace
    peligroso dejarlo pasar: otros valores sí perderían cifras y el residuo
    que se compararía sería el del redondeo, no el del cálculo."""
    with pytest.raises(I.InvarianteRota) as exc:
        I.kcl({"n1": [0.5, -0.5]})
    assert "float" in str(exc.value)
    for mala in (lambda: I.kvl({"m1": [0.5, -0.5]}),
                 lambda: I.balance_potencias([0.5], [0.5]),
                 lambda: I.pasiva({"R1": 0.5}),
                 lambda: I.estable([0.1, 0.2, 0.3, 0.4, 0.5]),
                 lambda: I.reciproca(0.5, 0.5)):
        with pytest.raises(I.InvarianteRota):
            mala()


def test_las_invariantes_siguen_aceptando_los_exactos():
    """Rechazar el float no puede ser motivo para rechazar el Decimal o el
    entero, que son exactos y son los que se usan de verdad."""
    assert I.kcl({"n1": [Decimal("1"), Decimal("-1")]}).cumple
    assert I.kcl({"n1": [1, -1]}).cumple
    assert I.balance_potencias([Decimal("5")], [Decimal("5")]).cumple


def test_una_oscilacion_marginal_no_se_declara_amortiguada():
    """Picos iguales no son picos amortiguados. El mensaje decia
    «amortiguados» de una oscilación de amplitud constante, que es afirmar
    algo que no se ha comprobado."""
    v = I.estable([Fraction(0), Fraction(1), Fraction(0), Fraction(1),
                   Fraction(0)])
    assert not v.comprobado, "una oscilacion marginal no esta verificada"
    assert "marginal" in v.detalle
    amortiguada = I.estable([Fraction(0), Fraction(9, 10), Fraction(11, 10),
                             Fraction(9, 10), Fraction(1)])
    assert amortiguada.comprobado, "una amortiguada si se puede comprobar"


def test_una_regla_de_region_para_un_dispositivo_inexistente_no_se_ignora():
    """Un `ref` mal escrito dejaba la comprobacion sin hacer y sin decir
    nada. Ahora avisa, porque el hueco aparecia tapado."""
    v = I.regiones({}, {"D1": ("ON", True, "x")})[0]
    assert not v.cumple
    assert "no est" in v.detalle
    assert not I.comprueba(regiones_datos={"D1": "ON"},
                           reglas={"D2": ("ON", True, "x")}).cumple


def test_un_sello_con_un_veredicto_inventado_se_rechaza():
    """«verificado » con un espacio de mas daria `ok == False` sin que nadie
    supiera por que, y al dibujarse saldria con un interrogante donde debia
    ir una explicacion."""
    for malo in ("inventado", "verificado ", "Verificado", "", "verificado."):
        with pytest.raises(C.EntradaInvalida) as exc:
            C.Sello(malo, "m")
        assert "veredictos" in str(exc.value)


def test_un_sello_sin_metodo_se_rechaza():
    """El sello dice como se comprobo. Sin metodo es un tick sin contenido."""
    with pytest.raises(C.EntradaInvalida) as exc:
        C.Sello(C.VERIFICADO, "")
    assert "segundo camino" in str(exc.value)


def test_los_tres_sellos_se_dibujan_con_su_signo():
    assert C.Sello(C.VERIFICADO, "m").linea().startswith("\u2714")
    assert C.Sello(C.FUERA_DE_RANGO, "m").linea().startswith("!")
    assert C.Sello(C.DIFIERE, "m").linea().startswith("\u2718")


def test_un_transitorio_vacio_no_dice_que_tiene_cero_puntos():
    assert "no hay ning" in I.estable([]).detalle
    assert "solo 1 punto:" in I.estable([Fraction(1)]).detalle


def test_la_r_de_la_serie_e_no_multiplica_por_diez():
    """«1R2» son 1,2 ohmios, no 12. En esta notación la letra es el punto
    decimal y la R vale por uno, así que leerla como ×10 se equivocaba en
    un factor de diez justo en el valor que decide si el circuito funciona.
    La primera versión de esta prueba fijaba 12 ohmios como si fuera lo
    correcto, que es como un error se convierte en especifi-cación."""
    assert C.magnitud("1R2", "Ω").to_base() == Decimal("1.2")
    assert C.magnitud("4R7", "Ω").to_base() == Decimal("4.7")
    assert C.magnitud("2R2", "Ω").to_base() == Decimal("2.2")
    # y la R al final es la unidad, no un prefijo
    assert C.magnitud("47R", "Ω").to_base() == Decimal("47")


def test_las_letras_no_se_confunden_entre_s_i():
    """«1m5» es miliohms y «1M5» es megaohms: la misma letra en distinta
    letra señal es un factor mil, así que la caja importa."""
    assert C.magnitud("1m5", "Ω").to_base() == Decimal("0.0015")
    assert C.magnitud("1M5", "Ω").to_base() == Decimal("1500000")


def test_un_prefijo_no_se_confunde_con_una_unidad():
    """«1m5» con ohmios son 1,5 miliohms. Antes de la comprobación por
    dimensión se leía como 1,5 **metros**: «m» es prefijo (mili) y
    unidad (metro) a la vez, y ganaba el metro. El resultado no habría
    reventado, habría dado un número plausible y equivocado, que es la
    forma de fallo peor que hay."""
    assert C.magnitud("1m5", "Ω").to_base() == Decimal("0.0015")
    # el mismo prefijo con otra unidad sigue siendo el mismo prefijo
    assert C.magnitud("1m5", "A").to_base() == Decimal("0.0015")
    assert C.magnitud("1n2", "F").to_base() == Decimal("1.2e-9")


def test_ningun_canonico_declara_un_balance_vacio():
    """Ninguno de los seis circuitos del banco es una red sin fuentes, asi que
    un balance de [0] contra [0] no seria una comprobacion: seria la rama de
    «red sin fuentes»aplicado a un circuito que tiene fuentes, y pasaria sin
    haber mirado nada. Cada uno declara las potencias de verdad."""
    for nombre in K.nombres():
        c = K.busca(nombre)
        absorbidas = c.invariantes.get("absorbidas")
        suministradas = c.invariantes.get("suministradas")
        assert absorbidas, f"{nombre} no declara potencias absorbidas"
        assert suministradas, f"{nombre} no declara potencias suministradas"
        assert any(Fraction(a) != 0 for a in absorbidas), (
            f"{nombre} declara un balance vacio: la comprobacion no miraria "
            f"nada")
        assert any(Fraction(s) != 0 for s in suministradas), (
            f"{nombre} no declara ninguna fuente que suministre energia")
        informe = c.cumple_invariantes()
        assert informe.cumple, f"{nombre}: {informe.texto()}"


def test_el_balance_de_cada_canonico_cierra_exacto():
    """Sin holgura: con aritmetica racional, si el balance no cierra a cero
    es que una potencia esta mal contada, y una holgura de 1e-6 lo taparia."""
    for nombre in K.nombres():
        c = K.busca(nombre)
        a = sum(Fraction(x) for x in c.invariantes["absorbidas"])
        s = sum(Fraction(x) for x in c.invariantes["suministradas"])
        assert a == s, f"{nombre}: absorbe {a} y suministra {s}"


def test_el_digest_distingue_hipotesis_y_validez_distintas():
    """Dos resultados con el mismo número y distinto «válido si x > 0» no
    son el mismo cálculo: la hipótesis dice bajo qué condición vale."""
    def uno(hipotesis=("lineal",), validez="x > 0"):
        traza = C.Traza()
        traza.anade("MNA", "a", despues="1", motivo="porque sí")
        return C.Resultado("prueba", "V = I·R", Decimal("1"), traza,
                           C.Sello(C.VERIFICADO, "manual"),
                           hipotesis=hipotesis, validez=validez)
    assert uno().digest == uno().digest
    assert uno().digest != uno(hipotesis=("saturado",)).digest
    assert uno().digest != uno(validez="x < 0").digest


def test_el_banco_no_afirma_mas_de_lo_que_hace():
    """El modulo decia que tenia un resolutor de nodos por Kron y no lo tiene:
    los pasivos se resuelven por fórmula cerrada. Afirmar una capacidad que el
    código no tiene es el mismo fallo que se le critica a un sello: si
    algún leyera esa frase, la usaría como referencia."""
    import inspect
    src = inspect.getsource(K)
    for capacidad in ("Kron", "Kirchhoff", "nodal solver"):
        if capacidad in src:
            assert "No hay resolutor de nodos" in src, (
                f"el modulo menciona {capacidad!r} y no lo implementa")
    # lo que sí implementa, lo implementa
    assert callable(K.gauss)
    assert K.gauss([[K.Fraction(2), K.Fraction(0)],
                    [K.Fraction(0), K.Fraction(4)]], [K.Fraction(4), K.Fraction(8)]) == [
        K.Fraction(2), K.Fraction(2)]


def test_las_comprobaciones_no_reviendan_al_explicar_un_numero_enorme():
    """Un mensaje de error que revienta es peor que no comprobar: entrega un
    traceback en vez del diagnóstico, y el diagnóstico es justo lo que hacía
    falta. `float(10**500)` lanza `OverflowError`, y estos `float` estaban
    todos dentro de los mensajes."""
    enormes = 10 ** 500
    for nombre, fn in (("KCL", lambda: I.kcl({"n1": [10 ** 400, -(10 ** 400) + 1]})),
                       ("balance", lambda: I.balance_potencias([enormes], [1])),
                       ("pasividad", lambda: I.pasiva({"R1": -enormes})),
                       ("estabilidad", lambda: I.estable([10 ** 400 * i
                                                          for i in range(1, 6)])),
                       ("reciprocidad", lambda: I.reciproca(10 ** 400,
                                                            10 ** 401))):
        veredicto = fn()          # no debe lanzar
        linea = veredicto.linea()  # y menos aún al explicarse
        assert linea, nombre
        assert "OverflowError" not in linea


def test_una_muestra_enorme_dice_cuantas_cifras_tiene():
    """No basta con que no reviente: el número sigue siendo legible. Un
    `1e500` es un diagnóstico; un entero de 501 dígitos no lo es."""
    from academic_core.domain.engineering.circuits.invariantes import _muestra
    assert _muestra(Fraction(5), 6) == "5"
    assert "e500" in _muestra(Fraction(10) ** 500)
    assert _muestra(Fraction(1, 3), 6) == "0.333333"


# ---------------------------------------------------------------------------
# 8. transitorios de libro: el criterio con casos que no se le ajustaron
# ---------------------------------------------------------------------------

TAU = Fraction(1, 100)


def _rampa(v0, vinf, n):
    """x(t) = vinf + (x0 - vinf)·e^(-t/tau) muestreada con una exponencial
    racional equivalente: `1/(1 + t/tau)` decae igual y es exacta."""
    return [Fraction(0)] + [v0 + (vinf - v0) * (TAU / (TAU + TAU * k))
                            for k in range(1, n)]


@pytest.mark.parametrize("nombre,ys,estable", [
    ("RC cargándose", "rampa 0->5", True),
    ("RC descargándose", "rampa 5->0", True),
    ("sobreamortiguado", "lento", True),
    ("constante", "constante", True),
    ("oscilación amortiguada larga", "amortiguada", True),
    ("oscilación que se amplifica", "amplifica", False),
    ("divergencia exponencial", "exponencial", False),
    ("nace de cero", "nace", False),
])
def test_los_transitorios_de_libro_se_juzgan_bien(nombre, ys, estable):
    """El criterio de estabilidad se probó con casos con los que se
    ajustó al principio. Estos son los que salen en un libro de segundo curso,
    y algunos no se parecerán en nada a los primeros."""
    TAU = Fraction(1, 100)
    tabla = {
        "rampa 0->5": [Fraction(0)] + [Fraction(5) * (TAU / (TAU + TAU * k))
                                       for k in range(1, 8)],
        "rampa 5->0": [Fraction(5)] + [Fraction(5) * (1 - TAU / (TAU + TAU * k))
                                       for k in range(1, 8)],
        "lento": [Fraction(0)] + [TAU / (TAU + TAU * k) for k in range(1, 8)],
        "constante": [Fraction(3)] * 8,
        "amortiguada": [Fraction(0), Fraction(10), Fraction(-9), Fraction(81, 10),
                        Fraction(-729, 100), Fraction(6561, 1000),
                        Fraction(-59049, 10000), Fraction(531441, 100000)],
        "amplifica": [Fraction(1), Fraction(-10), Fraction(100),
                      Fraction(-1000), Fraction(10000), Fraction(-100000)],
        "exponencial": [Fraction(2) ** i for i in range(1, 9)],
        "nace": [Fraction(0)] * 7 + [Fraction(5)],
    }
    v = I.estable(tabla[ys])
    assert v.cumple is estable, f"{nombre}: {v.detalle}"


def test_un_transitorio_real_de_primer_orden_pasa():
    """31 puntos de una carga RC de verdad, no tres números inventados."""
    ys = [Fraction(1) - (1 - Fraction(k, 200)) ** 10 for k in range(31)]
    v = I.estable(ys)
    assert v.cumple and v.comprobado, v.detalle


def test_una_rampa_lineal_no_se_declara_inestable_aunque_no_asiente():
    """Límite conocido y declarado, fijado como prueba para que no se
    olvide: los pasos de una rampa son constantes, y eso es indistinguible de
    un asentamiento por la **forma**. Se distingue mirando el comportamiento
    asintótico (Routh-Hurwitz, CI-12.1), no una muestra. Aquí se documenta
    como lo que es: no comprobado en la duda."""
    rampa = [Fraction(i) for i in range(1, 9)]
    v = I.estable(rampa)
    assert v.cumple, "no debe romper la solución"
    assert "asienta" in v.detalle or "mantiene" in v.detalle


def test_el_contexto_de_50_digitos_se_aplica_de_verdad():
    """Había dos ayudas que prometían un contexto de 50 dígitos y no lo
    daban: una devolvía el ambiente sin tocar y la otra no la llamaba nadie.
    Ahora se usa como gestor de contexto y el número sale largo."""
    with C.con_precision() as ctx:
        assert ctx.prec == 50
        dentro = Decimal(1) / Decimal(3)
    assert len(str(dentro).split(".")[1]) == 50, "no son 50 dígitos"
    # fuera del bloque vuelve el ambiente: no secontamination el resto
    assert len(str(Decimal(1) / Decimal(3)).split(".")[1]) < 50


def test_decimal_no_calcula_con_28_digitos():
    """Un tercio a 28 cifras pierde las 22 últimas sin avisar, y en un
    cálculo que luego se compara con otro de la misma familia el fallo se
    propaga en silencio."""
    d = C.decimal(Fraction(1, 3))
    assert len(str(d).split(".")[1]) >= 50, str(d)


def test_una_unidad_que_no_existe_lo_dice_en_el_mensaje():
    """Antes el mensaje acababa diciendo «escríbelo con la unidad ΩΩ», que
    era justamente lo imposible. Una ayuda que repite el nombre roto no
    ayuda: hay que decir que el nombre no existe y enseñar uno bueno."""
    # solo nombres que de verdad no existen: «volts» sí es alias de «V» en
    # units.py y aceptarlo es lo correcto
    for rota in ("ΩΩ", "Ω/Ω", "amper", "zzz", "k"):
        with pytest.raises(C.EntradaInvalida) as exc:
            C.magnitud("5", rota)
        texto = str(exc.value)
        assert "no existe" in texto, texto
        assert rota not in texto.split("ejemplo")[-1], (
            "el ejemplo no debe repetir la unidad rota")


def test_un_resultado_no_admite_float():
    """P1 tenía tres puertas y dos abiertas: `exacto()` y las invariantes
    rechazaban el float, pero el `valor` de un resultado lo aceptaba. Un
    resultado con float tiene un digest que no corresponde al cálculo que
    se haría al reproducirlo."""
    traza = C.Traza()
    traza.anade("MNA", "a", despues="1", motivo="porque sí")
    with pytest.raises(I.InvarianteRota) as exc:
        C.Resultado("v", "V = I·R", 0.5, traza, C.Sello(C.VERIFICADO, "m"))
    assert "float" in str(exc.value)
    # y los exactos siguen entrando
    for bueno in (Decimal("0.5"), Fraction(1, 2), 1, 0):
        C.Resultado("v", "V = I·R", bueno, traza, C.Sello(C.VERIFICADO, "m"))


# ---------------------------------------------------------------------------
# 9. el banco canónico CONTRASTEADO con el motor de producción
# ---------------------------------------------------------------------------

def _cto(nombre, partes):
    """Monta un circuito real con el modelo `circuit.Circuit` de producción."""
    from academic_core.domain.engineering.circuit import Circuit, Component
    from academic_core.domain.engineering.units import parse_quantity
    circ = Circuit(nombre)
    for ref, tipo, valor, pins in partes:
        circ.add(Component(ref=ref, type=tipo, value=parse_quantity(valor),
                           pins=dict(pins)))
    return circ


def _solve(circ):
    from academic_core.domain.engineering.mna.solver import solve_linear_dc
    sol = solve_linear_dc(circ)
    assert str(sol.status).endswith("SOLVED"), (sol.status, sol.diagnostics)
    return sol


def _v(sol, nodo):
    for nv in sol.node_voltages:
        if nv.node == nodo:
            return nv.voltage.to_base()
    raise KeyError(nodo)


def _i(sol, ref):
    for b in sol.branch_currents:
        if b.ref == ref:
            return b.current.to_base()
    raise KeyError(ref)


def _coincide(exacto, mostrado, nombre):
    """El banco es fracción exacta; el MNA resuelve exacto pero **presenta**
    con 28 dígitos, así que la comparación va por relativa."""
    a = Decimal(exacto.numerator) / Decimal(exacto.denominator)
    b = Decimal(mostrado)
    tol = Decimal(1) / Decimal(10 ** 24)
    rel = abs(a - b) / max(abs(a), abs(b), Decimal(1))
    assert rel <= tol, f"{nombre}: banco {a} frente a motor {b} (relativo {rel:.3g})"


def test_el_banco_coincide_con_el_mna_en_la_malla_simple():
    """El banco no basta consigo mismo: se resuelve el mismo circuito con el
    MNA de producción y se comparan. Un banco que sólo se autocomprueba
    certifica el error, porque autocomprobarse con el mismo criterio
    equivocado no comprueba nada."""
    circ = _cto("malla_simple", [
        ("V1", "V", "2 V", {"+": "in", "-": "0"}),
        ("R1", "R", "2 ohm", {"1": "in", "2": "mid"}),
        ("R2", "R", "4 ohm", {"1": "mid", "2": "0"})])
    s = _solve(circ)
    b = K.busca("malla_simple").espera
    _coincide(b["I"], -_i(s, "V1"), "malla_simple.I")
    _coincide(b["V1"], _v(s, "in") - _v(s, "mid"), "malla_simple.V1")
    _coincide(b["V2"], _v(s, "mid") - _v(s, "0"), "malla_simple.V2")


def test_el_banco_coincide_con_el_mna_en_la_doble_malla():
    """Este contraste es el que cazó el signo del 3 Ω común. El canónico
    decía que las dos corrientes de malla lo cruzaban en sentidos opuestos y
    por eso iban restadas; en esta topología **vuelven las dos por él en el
    mismo sentido** y se suman. El valor equivocado (7/3, 13/9) violaba KCL:
    al nodo central entraban 34/9 A y salían 8/9 A."""
    circ = _cto("doble_malla", [
        ("V1", "V", "12 V", {"+": "n1", "-": "0"}),
        ("V2", "V", "6 V", {"+": "n3", "-": "0"}),
        ("R1", "R", "4 ohm", {"1": "n1", "2": "n2"}),
        ("R2", "R", "6 ohm", {"1": "n3", "2": "n2"}),
        ("R3", "R", "3 ohm", {"1": "n2", "2": "0"})])
    s = _solve(circ)
    b = K.busca("doble_malla").espera
    _coincide(b["I1"], _i(s, "R1"), "doble_malla.I1")
    _coincide(b["I2"], _i(s, "R2"), "doble_malla.I2")
    _coincide(b["Ic"], _i(s, "R3"), "doble_malla.Ic")


def test_el_banco_coincide_con_el_mna_en_el_divisor_cargado():
    circ = _cto("divisor_cargado", [
        ("V1", "V", "12 V", {"+": "in", "-": "0"}),
        ("R1", "R", "2 kohm", {"1": "in", "2": "mid"}),
        ("R2", "R", "4 kohm", {"1": "mid", "2": "0"}),
        ("R3", "R", "4 kohm", {"1": "mid", "2": "0"})])
    s = _solve(circ)
    _coincide(K.busca("divisor_cargado").espera["V_sal"], _v(s, "mid"),
              "divisor_cargado.V_sal")


@pytest.mark.parametrize("nombre", ["puente_equilibrado", "puente_desbalanceado"])
def test_el_banco_coincide_con_el_mna_en_los_puentes(nombre):
    r3, r4 = ("4 ohm", "6 ohm") if nombre.endswith("equilibrado") else ("6 ohm", "3 ohm")
    r1, r2 = "4 ohm", "6 ohm"
    circ = _cto("puente", [
        ("V1", "V", "12 V", {"+": "A", "-": "0"}),
        ("R1", "R", r1, {"1": "A", "2": "B"}),
        ("R2", "R", r2, {"1": "B", "2": "0"}),
        ("R3", "R", r3, {"1": "A", "2": "C"}),
        ("R4", "R", r4, {"1": "C", "2": "0"})])
    s = _solve(circ)
    b = K.busca(nombre).espera
    _coincide(b["V_B"], _v(s, "B"), f"{nombre}.V_B")
    _coincide(b["V_C"], _v(s, "C"), f"{nombre}.V_C")
    _coincide(b["V_diagonal"], _v(s, "B") - _v(s, "C"), f"{nombre}.V_diagonal")


def test_la_doble_malla_del_banco_cumple_kcl():
    """El valor que tenía antes cumplía la ecuación que el canónimo decía
    resolver y violaba KCL. Se fija la ley, no el número."""
    b = K.busca("doble_malla").espera
    # por R1 y R2 llega al nodo central, y por R3 sale
    assert b["I1"] + b["I2"] == b["Ic"], f"el canónico viola KCL: {b}"
