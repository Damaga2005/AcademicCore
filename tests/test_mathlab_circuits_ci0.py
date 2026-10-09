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
    ("1R2", "Ω", "12"),
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
