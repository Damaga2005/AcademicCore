"""MATH_LAB ML-1: pruebas del bloque 0 ya implementado.

Cubre los cinco módulos escritos en esta fase:

- ``integer``    suma, resta, producto y división larga con llevadas
- ``fractions``  simplificar, operar, comparar, decimal exacto y periódico
- ``divisibility`` mcd, mcm, factorización, σ(n), perfectos, criba, DNI
- ``bases``      conversión de bases, máscaras, IPv4
- ``polynomials`` división, Ruffini, raíces racionales, identidades

Por qué estas pruebas existen
----------------------------

Cuatro de ellas son **pruebas de convención**, y no son decorativas: esta fase
tuvo cuatro bugs seguidos en ``polynomials.py`` que ningún test detectaba, todos
por la misma causa, leer la lista de coeficientes en el orden equivocado.

1. ``test_la_lista_de_coeficientes_es_ascendente`` fija que ``p[i]`` es el
   coeficiente de ``x**i`` y que ``normalizar`` quita los ceros **altos**. Con
   la convención inversa, ``normalizar`` borraba el grado: ``x^3 - 2x^2 + x``
   se leía como ``x^2 - 2x + 1``.
2. ``test_el_divisor_de_x_menos_r`` fija que ``x - r`` es ``[-r, 1]`` en orden
   ascendente, no ``[1, -r]``: con el orden equivocado se dividía por ``1 - x``
   y Ruffini y la división larga discrepaban.
3. ``test_ruffini_coincide_con_la_division_larga`` es la comprobación cruzada
   que la propia calculadora hace y que aquí se vuelve a exigir.
4. ``test_la_division_cubre_todos_los_grados_del_cociente`` fija que el bucle
   recorre ``n - m + 1`` coeficientes; con ``m - 1`` pasos el cociente salía
   truncado.

Se prueba además lo que §5.3 exige: cada resultado tiene un segundo camino, y
cuando dos caminos discrepan el sello lo dice.

Sin Qt y determinista: LCG explícito, nunca el módulo ``random``.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import bases
from academic_core.domain.engineering.mathlab import divisibility as DIV
from academic_core.domain.engineering.mathlab import fractions as FR
from academic_core.domain.engineering.mathlab import integer as INT
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import polynomials as PO
from academic_core.domain.engineering.mathlab import trace as TR
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.errors import UnsupportedError, ValidationError

T = TR.Trace


# ===========================================================================
# integer: operaciones en columna (§4.0, §8.2 A)
# ===========================================================================


@pytest.mark.parametrize("a,b,esperado", [
    (345, 278, 623), (9, 1, 10), (5, 5, 10), (0, 0, 0), (999, 1, 1000),
    (499, 501, 1000), (123, 0, 123), (7, 13, 20),
])
def test_suma_en_columna(a, b, esperado):
    assert INT.sumar(a, b, T()) == esperado


def test_la_suma_nombra_la_llevada():
    """Sin esto, un alumno solo ve el resultado y no aprende el(arrastre)."""
    traza = T()
    assert INT.sumar(345, 278, traza) == 623
    columnas = [s for s in traza.steps if s.rule == "suma.columna"]
    assert len(columnas) == 3
    assert "se lleva 1" in columnas[0].why
    assert "5 + 8" in columnas[0].why
    assert "6" in columnas[-1].why          # la última columna no lleva


@pytest.mark.parametrize("a,b,esperado", [
    (5234, 1879, 3355), (1000, 1, 999), (10, 10, 0), (7, 0, 7), (100, 99, 1),
])
def test_resta_en_columna(a, b, esperado):
    assert INT.restar(a, b, T()) == esperado


def test_la_resta_nombra_el_prestamo():
    traza = T()
    assert INT.restar(5234, 1879, traza) == 3355
    prestamos = [s for s in traza.steps if s.rule == "resta.prestamo"]
    assert len(prestamos) == 3
    assert "se pide 1 a la columna de la izquierda" in prestamos[0].why


def test_los_signos_se_explican_en_vez_de_reordenarse_en_silencio():
    traza = T()
    assert INT.sumar(5, -3, traza) == 2
    assert any(s.rule == "suma.signos_distintos" for s in traza.steps)
    traza2 = T()
    assert INT.sumar(-5, 3, traza2) == -2
    assert any(s.rule == "suma.signos_distintos" for s in traza2.steps)


@pytest.mark.parametrize("a,b,esperado", [
    (345, 278, 95910), (0, 5, 0), (1, 1, 1), (12, 12, 144), (-3, 4, -12),
])
def test_producto_en_columna(a, b, esperado):
    assert INT.multiplicar(a, b, T()) == esperado


def test_el_producto_descompone_un_producto_parcial_por_cifra():
    traza = T()
    assert INT.multiplicar(345, 278, traza) == 95910
    parciales = [s for s in traza.steps if s.rule == "producto.parcial"]
    assert len(parciales) == 3              # 278 tiene tres cifras
    assert "8" in parciales[0].label


@pytest.mark.parametrize("dividendo,divisor,cociente,resto", [
    (7453, 47, 158, 27), (84, 7, 12, 0), (7, 2, 3, 1), (100, 7, 14, 2),
    (9, 3, 3, 0), (5, 8, 0, 5), (123456, 789, 156, 372),
])
def test_division_larga(dividendo, divisor, cociente, resto):
    d = INT.dividir(dividendo, divisor, T())
    assert (d.cociente, d.resto) == (cociente, resto)
    assert d.exacta is (resto == 0)


def test_la_division_larga_cumple_la_identidad_del_algoritmo():
    """cociente · divisor + resto = dividendo, con 0 ≤ resto < divisor (§5.3)."""
    for dividendo, divisor in [(7453, 47), (7, 2), (123456, 789), (100, 7)]:
        d = INT.dividir(dividendo, divisor, T())
        assert d.verificador == dividendo
        assert 0 <= d.resto < divisor


def test_la_division_larga_muestra_cada_cifra_del_cociente():
    traza = T()
    INT.dividir(7453, 47, traza)
    digitos = [s for s in traza.steps if s.rule == "division.digito"]
    assert [s.piece for s in digitos] == ["columna 2 de la izquierda",
                                          "columna 3 de la izquierda",
                                          "columna 4 de la izquierda"]
    # cada cifra se justifica con la desigualdad que la define
    for s in digitos:
        assert "≤" in s.conditions[0] and "<" in s.conditions[0]


def test_dividir_entre_cero_se_rechaza_en_castellano():
    with pytest.raises(ValidationError) as exc:
        INT.dividir(5, 0, T())
    assert "cero" in str(exc.value)


def test_un_float_no_se_trunca_en_silencio():
    """3.0 como dividendo es un error o un redondeo ya hecho, nunca una suposición."""
    with pytest.raises(ValidationError):
        INT.dividir(3.0, 2, T())
    with pytest.raises(ValidationError):
        INT.sumar(1.5, 2, T())


def test_la_comprobacion_del_ordenador_coincide():
    """El segundo camino: la aritmética exacta del host, no la nuestra."""
    assert INT.verificar(INT.sumar(345, 278, T()), 345 + 278).verdict == V.VERIFIED
    assert INT.verificar(INT.restar(5234, 1879, T()), 5234 - 1879).verdict == V.VERIFIED
    assert INT.verificar(INT.multiplicar(345, 278, T()), 345 * 278).verdict == V.VERIFIED


# ===========================================================================
# fractions
# ===========================================================================


def test_mcd_con_la_combinacion_lineal_que_lo_demuestra():
    """La identidad a·s + b·t = mcd es la prueba, no un adorno."""
    traza = T()
    assert FR.mcd(462, 1071, traza) == 21
    pasos = [s for s in traza.steps if s.rule == "mcd.paso"]
    assert pasos[0].label == "1071 = 2·462 + 147"
    assert pasos[0].piece == "división euclídea, cociente 2"
    combinacion = [s for s in traza.steps if s.rule == "mcd.combinacion"]
    assert len(combinacion) == 1
    # y la combinación reproduce de verdad el valor
    assert 1071 * -3 + 462 * 7 == 21


@pytest.mark.parametrize("a,b,esperado", [
    (462, 1071, 21), (12, 18, 6), (17, 5, 1), (100, 75, 25), (7, 7, 7),
])
def test_mcd(a, b, esperado):
    assert FR.mcd(a, b, T()) == esperado


@pytest.mark.parametrize("n,d,esperado", [
    (6, 8, "3/4"), (4, 6, "2/3"), (100, 10, "10"), (3, 9, "1/3"), (0, 5, "0"),
    (-6, 8, "-3/4"),
])
def test_simplificar(n, d, esperado):
    assert FR.texto(FR.simplificar(n, d, T())) == esperado


def test_simplificar_avisa_cuando_no_hay_nada_que_quitar():
    traza = T()
    assert FR.texto(FR.simplificar(3, 7, traza)) == "3/7"
    assert any("irreducible" in s.label for s in traza.steps)


@pytest.mark.parametrize("a,b,op,esperado", [
    (Fraction(2, 3), Fraction(1, 2), "+", "7/6"),
    (Fraction(3, 4), Fraction(1, 4), "-", "1/2"),
    (Fraction(3, 4), Fraction(2, 9), "*", "1/6"),
    (Fraction(3, 4), Fraction(2, 9), "/", "27/8"),
    (Fraction(1, 2), Fraction(1, 2), "+", "1"),
])
def test_operar_fracciones(a, b, op, esperado):
    assert FR.texto(FR.operar(a, b, op, T())) == esperado


def test_la_operacion_de_fracciones_no_pasa_por_un_float():
    """Un solo float destruiría la exactitud; el resultado se reduce exacto."""
    assert FR.operar(Fraction(1, 3), Fraction(1, 6), "+", T()) == Fraction(1, 2)


def test_dividir_por_la_fraccion_cero_se_rechaza():
    with pytest.raises(ValidationError):
        FR.operar(Fraction(1, 2), Fraction(0, 1), "/", T())


@pytest.mark.parametrize("a,b,esperado", [
    (Fraction(2, 3), Fraction(5, 8), 1),
    (Fraction(1, 2), Fraction(1, 2), 0),
    (Fraction(1, 3), Fraction(1, 2), -1),
    (Fraction(-1, 2), Fraction(1, 2), -1),
])
def test_comparar_por_multiplicacion_cruzada(a, b, esperado):
    assert FR.comparar(a, b, T()) == esperado


@pytest.mark.parametrize("f,texto_esperado,termina,periodo", [
    (Fraction(1, 2), "0.5", True, None),
    (Fraction(1, 8), "0.125", True, None),
    (Fraction(4, 25), "0.16", True, None),
    (Fraction(-3, 4), "0.75", True, None),
    (Fraction(5, 1), "5", True, None),
    (Fraction(1, 3), r"0,\overline{3}", False, (3,)),
    (Fraction(1, 7), r"0,\overline{142857}", False, (1, 4, 2, 8, 5, 7)),
    (Fraction(22, 7), r"3,\overline{142857}", False, (1, 4, 2, 8, 5, 7)),
    (Fraction(2, 11), r"0,\overline{18}", False, (1, 8)),
])
def test_decimal_exacto_o_periodico(f, texto_esperado, termina, periodo):
    d = FR.decimal_exacto(f, T())
    assert d.exacto == texto_esperado
    assert d.termina is termina
    assert d.periodo == periodo


def test_el_periodico_tiene_preperiodo_cuando_el_denominador_lo_exige():
    """1/6 = 0,1(6): el 2 del denominador alarga el preperiodo antes del ciclo."""
    d = FR.decimal_exacto(Fraction(1, 6), T())
    assert d.preperiodo == 1 and d.periodo == (6,)
    d2 = FR.decimal_exacto(Fraction(1, 12), T())
    assert d2.preperiodo == 2 and d2.periodo == (3,)


def test_el_periodo_se_encuentra_por_orden_multiplicativo_y_no_contando_cifras():
    """La longitud del periodo es una prueba, no una observación de dígitos."""
    traza = T()
    FR.decimal_exacto(Fraction(1, 7), traza)
    pasos = [s for s in traza.steps if s.rule == "decimal.orden"]
    assert len(pasos) == 5          # 10^1..10^5 no dan 1; 10^6 sí
    metodos = [s for s in traza.steps if s.kind == TR.METODO]
    assert any("orden de 10" in s.why for s in metodos)


def test_una_fraccion_impropia_da_entero_y_decimales():
    d = FR.decimal_exacto(Fraction(7, 2), T())
    assert d.entero == 3 and d.exacto == "3.5"


# ===========================================================================
# divisibility
# ===========================================================================


@pytest.mark.parametrize("n,esperado", [
    (360, "2^3 · 3^2 · 5"), (12, "2^2 · 3"), (97, "97"), (1024, "2^10"),
    (1, "1"), (49, "7^2"), (2 * 3 * 5 * 7, "2 · 3 · 5 · 7"),
])
def test_factorizacion_en_primos(n, esperado):
    assert DIV.factorizar(n, T()).texto == esperado


def test_el_arbol_de_factores_se_construye_como_dato():
    """§4.0 lo pide como gráfica, así que tiene que ser un árbol y no un texto."""
    arbol = DIV.factorizar(12, T())
    assert (arbol.numero, arbol.primo) == (12, False)
    assert [h.numero for h in arbol.hijos] == [2, 6]
    assert all(h.primo for h in arbol.hijos[:1])
    # 6 = 2 · 3, y ambos hijos son primos
    hoja_6 = arbol.hijos[1]
    assert [h.numero for h in hoja_6.hijos] == [2, 3]


def test_la_factorizacion_se_verifica_reconstruyendo_el_numero():
    traza = T()
    DIV.factorizar(360, traza)
    final = [s for s in traza.steps if s.rule == "factorizar.resultado"][0]
    assert "360" in final.why and "2^3" in final.why


@pytest.mark.parametrize("a,b,esperado", [(12, 18, 36), (4, 6, 12), (5, 7, 35),
                                           (0, 5, 0), (1, 1, 1)])
def test_mcm(a, b, esperado):
    assert DIV.mcm(a, b, T()) == esperado


@pytest.mark.parametrize("n,sigma", [(6, 12), (28, 56), (97, 98), (27, 40),
                                     (1, 1), (12, 28), (360, 1170)])
def test_sigma_suma_de_divisores(n, sigma):
    assert DIV.sigma(n, T()) == sigma


@pytest.mark.parametrize("n,perfecto", [(6, True), (28, True), (496, True),
                                        (8128, True), (27, False), (15, False),
                                        (97, False), (1, False)])
def test_numeros_perfectos(n, perfecto):
    es, total, propios = DIV.es_numero_perfecto(n, T())
    assert es is perfecto
    assert propios == total - n          # los divisores propios no incluyen el n


def test_criba_de_eratostenes():
    assert DIV.criba(30, T()) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert DIV.criba(2, T()) == [2]


def test_la_criba_dice_cuantos_tacha():
    """§4.0 v2 pide primalidad «con su coste contado»: sin el recuento no cuenta."""
    traza = T()
    DIV.criba(30, traza)
    resultado = [s for s in traza.steps if s.rule == "criba.resultado"][0]
    assert any("tachados" in c for c in resultado.conditions)
    assert "2^" in resultado.why or "divisiones" in resultado.why


@pytest.mark.parametrize("n,primo,divisiones", [
    (2, True, 1), (7, True, 0), (97, True, 4), (1009, True, 15),
    (9, False, 1), (91, False, 3), (4, False, 1), (1, False, 0),
])
def test_es_primo_con_el_numero_de_divisiones(n, primo, divisiones):
    es, cuenta = DIV.es_primo(n, T())
    assert es is primo and cuenta == divisiones


def test_los_dos_metodos_de_primalidad_coinciden():
    """§5.5b: dos caminos exactos, y la elección se justifica por el coste."""
    for n in (2, 3, 7, 9, 97, 91, 1009, 1000003):
        resultado = DIV.comparar_primalidad(n, T())
        assert resultado["es_primo"] == resultado["por_criba"], n


def test_comparar_primalidad_explica_el_por_que():
    traza = T()
    DIV.comparar_primalidad(1009, traza)
    metodos = [s for s in traza.steps if s.rule == "primalidad.comparacion"]
    assert metodos and "coste" in metodos[0].why


@pytest.mark.parametrize("dni,letra", [
    ("12345678", "Z"), ("1234567Z", "L"), ("00000000", "T"), ("99999999", "R"),
    ("12a", "N"),
])
def test_letra_del_dni(dni, letra):
    assert DIV.letra_dni(dni, T()) == letra


def test_un_dni_imposible_se_rechaza_en_vez_de_rellenarse():
    with pytest.raises(ValidationError):
        DIV.letra_dni("123456789", T())
    with pytest.raises(ValidationError):
        DIV.letra_dni("abcdefgh", T())


def test_la_letra_del_dni_usa_el_resto_mod_23():
    traza = T()
    DIV.letra_dni("12345678", traza)
    paso = [s for s in traza.steps if s.rule == "dni.letra"][0]
    assert "12345678 mod 23" in paso.before
    assert paso.after == "Z"


# ===========================================================================
# bases
# ===========================================================================


@pytest.mark.parametrize("n,base,esperado", [
    (255, 16, "FF"), (255, 2, "11111111"), (100, 8, "144"), (100, 10, "100"),
    (-5, 2, "-101"), (0, 2, "0"), (7, 8, "7"), (4095, 2, "111111111111"),
])
def test_convertir_a_base(n, base, esperado):
    assert bases.a_base(n, base, T()) == esperado


@pytest.mark.parametrize("n", [0, 1, 7, 100, 255, 4095, 123456, -5, 2 ** 40])
def test_la_conversion_hace_ida_y_vuelta(n):
    for base in (2, 8, 10, 16):
        assert bases.de_base(bases.a_base(n, base, T()), base, T()) == n


def test_la_conversion_muestra_las_divisiones_successivas():
    traza = T()
    bases.a_base(10, 2, traza)
    pasos = [s for s in traza.steps if s.rule == "base.division"]
    assert [s.after.split(",")[0] for s in pasos] == ["dígito 0", "dígito 1", "dígito 0", "dígito 1"]


def test_un_digito_que_no_existe_en_la_base_se_dice_y_donde():
    with pytest.raises(ValidationError) as exc:
        bases.de_base("19", 8, T())
    assert "«9» no existe en base 8" in str(exc.value)
    assert "posición 2" in str(exc.value)


@pytest.mark.parametrize("operacion,a,b,esperado", [
    ("and", 0b1100, 0b1010, 0b1000),
    ("or", 0b1100, 0b1010, 0b1110),
    ("xor", 0b1100, 0b1010, 0b0110),
])
def test_mascaras_de_bits(operacion, a, b, esperado):
    funcion = {"and": bases.mascara_y, "or": bases.mascara_o,
               "xor": bases.mascara_xor}[operacion]
    assert funcion(a, b, T()) == esperado


def test_cada_operacion_de_bits_explica_su_regla():
    traza = T()
    bases.mascara_xor(0b1100, 0b1010, traza)
    paso = [s for s in traza.steps if s.rule == "bits.xor"][0]
    assert "difieren" in paso.why and "simétrica" in paso.why


def test_desplazamiento_equivale_a_multiplicar_por_dos():
    assert bases.desplazar(5, 3, True, T()) == 40 == 5 * 2 ** 3
    assert bases.desplazar(20, 2, False, T()) == 5 == 20 // 4


@pytest.mark.parametrize("direccion,prefijo,red,difusion,hosts", [
    (0xC0A80164, 24, "192.168.1.0", "192.168.1.255", 254),
    (0xC0A80164, 26, "192.168.1.64", "192.168.1.127", 62),
    (0xC0A80164, 30, "192.168.1.100", "192.168.1.103", 2),
    (0xC0A80100, 25, "192.168.1.0", "192.168.1.127", 126),
])
def test_red_ipv4(direccion, prefijo, red, difusion, hosts):
    r = bases.red_ipv4(direccion, prefijo, T())
    assert r.red == int(red.replace(".", "")) & 0xFFFFFFFF or bases._ipv4(r.red) == red
    assert bases._ipv4(r.difusion) == difusion
    assert r.hosts == hosts


def test_un_slash_32_no_tiene_hosts_utiles():
    r = bases.red_ipv4(0xC0A80164, 32, T())
    assert r.hosts == 0
    assert "sin hosts útiles" in r.texto


def test_el_calculo_de_hosts_justifica_el_dos_que_se_restan():
    traza = T()
    r = bases.red_ipv4(0xC0A80164, 24, traza)
    paso = [s for s in traza.steps if s.rule == "ipv4.hosts"][0]
    assert "2^8 − 2 = 254" in paso.why or "2^" in paso.why
    assert r.hosts == 254


def test_la_red_se_verifica_reconstruyendo_la_direccion():
    """§5.3: AND con la máscara devuelve la red, y 2^(32−p) − 2 se recalcula."""
    sello = bases.verificar_mascara(0xC0A80164, 24, T())
    assert sello.verdict == V.VERIFIED
    assert bases.verificar_mascara(0xC0A80164, 30, T()).verdict == V.VERIFIED


def test_un_prefijo_imposible_se_rechaza():
    with pytest.raises(ValidationError):
        bases.red_ipv4(0xC0A80164, 33, T())


# ===========================================================================
# polynomials — y las cuatro pruebas de convención
# ===========================================================================


def test_la_lista_de_coeficientes_es_ascendente():
    """p[i] es el coeficiente de x^i. Con el orden inverso se pierde el grado."""
    assert PO.representar([Fraction(0), Fraction(0), Fraction(1)]) == "x^2"
    assert PO.desde_texto("x^3-2x^2+x", "x", T()) == [Fraction(0), Fraction(1),
                                                    Fraction(-2), Fraction(1)]
    assert PO.representar(PO.desde_texto("x^3-2x^2+x", "x", T())) == "x^3 - 2*x^2 + x"


def test_normalizar_quita_los_ceros_altos_y_conserva_los_bajos():
    assert PO.normalizar([Fraction(0), Fraction(0), Fraction(0)]) == []
    assert PO.normalizar([Fraction(0), Fraction(0), Fraction(1)]) == [
        Fraction(0), Fraction(0), Fraction(1)]   # x^2, no 1


def test_el_divisor_de_x_menos_r():
    """En orden ascendente, x − r es [-r, 1]. Al revés se divide por 1 − x."""
    d = PO.dividir(PO.desde_texto("x^2-1", "x", T()), [Fraction(-1), Fraction(1)],
                   "x", T())
    assert d.exacta and PO.representar(d.cociente) == "x + 1"


def test_la_division_cubre_todos_los_grados_del_cociente():
    """El cociente tiene n − m + 1 coeficientes, no m − 1."""
    d = PO.dividir(PO.desde_texto("x^3-2x^2+x", "x", T()), [Fraction(-1), Fraction(1)],
                   "x", T())
    assert PO.representar(d.cociente) == "x^2 - x"
    assert d.exacta


def test_ruffini_coincide_con_la_division_larga():
    """La comprobación cruzada que la calculadora hace, exigida otra vez aquí."""
    for texto, raiz in [("x^2-1", 1), ("x^3-2x^2+x", 1), ("x^3+1", -1),
                        ("x^3+1", 1), ("2x^2+3x+1", -1), ("x^4-1", 1)]:
        p = PO.desde_texto(texto, "x", T())
        por_ruffini = PO.ruffini(p, raiz, "x", T())
        por_division = PO.dividir(p, [-Fraction(raiz), Fraction(1)], "x", T())
        assert por_ruffini.cociente == por_division.cociente, texto


@pytest.mark.parametrize("texto,divisor,cociente,exacto", [
    ("x^2-1", [Fraction(-1), Fraction(1)], "x + 1", True),
    ("x^3-2x^2+x", [Fraction(-1), Fraction(1)], "x^2 - x", True),
    ("x^3+1", [Fraction(1), Fraction(1)], "x^2 - x + 1", True),
    ("2x^2+3x+1", [Fraction(1), Fraction(1)], "2*x + 1", True),
    ("x^3+1", [Fraction(2), Fraction(0), Fraction(1)], "x", False),
    ("x^2", [Fraction(1)], "x^2", True),
    # (x^2 - 3x + 2) = (x-1)(x-2), y el cociente es x - 3
    ("x^3-6x^2+11x-6", [Fraction(2), Fraction(-3), Fraction(1)], "x - 3", True),
])
def test_division_de_polinomios(texto, divisor, cociente, exacto):
    """Cada divisor va explícito: (x−1) y (x+1) dan cocientes distintos."""
    d = PO.dividir(PO.desde_texto(texto, "x", T()), divisor, "x", T())
    assert PO.representar(d.cociente) == cociente
    assert d.exacta is exacto


def test_la_division_se_verifica_con_la_identidad_euclidea():
    """dividendo = cociente · divisor + resto, reconstruido exactamente."""
    for texto, divisor in [("x^3+1", [Fraction(2), Fraction(0), Fraction(1)]),
                           ("x^2-1", [Fraction(-1), Fraction(1)]),
                           ("x^4-1", [Fraction(1), Fraction(0), Fraction(0),
                                      Fraction(1)])]:
        d = PO.dividir(PO.desde_texto(texto, "x", T()), divisor, "x", T())
        assert PO.verificar(d).verdict == V.VERIFIED, texto


def test_el_resto_de_ruffini_es_el_valor_del_polinomio():
    """La última fila de la tabla es P(r), y por eso se anula si r es raíz."""
    traza = T()
    d = PO.ruffini(PO.desde_texto("x^2-2x+1", "x", T()), 1, "x", traza)
    assert d.exacta and not d.resto
    paso = [s for s in traza.steps if s.rule == "polinomio.ruffini.resto"][0]
    assert "P(1)" in paso.conditions[0]
    # y con un r que no es raíz, el resto es P(r) y no vale cero
    d2 = PO.ruffini(PO.desde_texto("x^2-1", "x", T()), 2, "x", T())
    assert not d2.exacta and PO.representar(d2.resto) == "3"   # P(2) = 4 - 1


def test_ruffini_explica_por_que_usa_la_tabla():
    traza = T()
    PO.dividir_por_lineal(PO.desde_texto("x^2-1", "x", T()), 1, "x", traza)
    metodo = [s for s in traza.steps if s.rule == "polinomio.ruffini.metodo"][0]
    assert "sin escribir potencias de x" in metodo.why
    # §5.5b: el método rechazado dice por qué no
    assert metodo.alternatives
    # el método rechazado es confiar en la tabla sin comprobarla
    assert any("confiar" in nombre and "arrastre" in motivo
               for nombre, motivo in metodo.alternatives)


@pytest.mark.parametrize("texto,esperado", [
    ("x^2-5x+6", [Fraction(2), Fraction(3)]),
    ("x^2+1", []),
    ("x^2-2", []),
    ("2x^2-8", [Fraction(-2), Fraction(2)]),
    ("x^3-x", [Fraction(-1), Fraction(0), Fraction(1)]),
    ("x^2-2x+1", [Fraction(1)]),
    ("x^2-x-1", []),
    ("x^3+2x^2-5x-6", [Fraction(-3), Fraction(-1), Fraction(2)]),
])
def test_raices_racionales(texto, esperado):
    assert PO.raices_racionales(PO.desde_texto(texto, "x", T()), T()) == esperado


def test_sin_raices_racionales_se_dice_con_prueba_y_no_es_un_fallo():
    """«No tiene raíces racionales» no significa «no tiene raíces reales»."""
    traza = T()
    assert PO.raices_racionales(PO.desde_texto("x^2+1", "x", T()), traza) == []
    paso = [s for s in traza.steps if s.rule == "polinomio.raices.ninguna"][0]
    assert "no tiene" in paso.why and "no significa" in paso.why


def test_el_teorema_de_la_raiz_racional_declara_su_candidato_finito():
    traza = T()
    PO.raices_racionales(PO.desde_texto("2x^2-8", "x", T()), traza)
    metodo = [s for s in traza.steps if s.kind == TR.METODO][0]
    assert "término independiente" in metodo.why
    assert "candidatos" in metodo.why
    # 2x^2 - 8: the independent term is -8 and the leading coefficient 2, and the
    # explanation printed them the other way round
    assert "independiente (-8)" in metodo.why and "principal (2)" in metodo.why


@pytest.mark.parametrize("texto,esperado", [
    ("x^3-6x^2+11x-6", ["(x - 1)", "(x - 2)", "(x - 3)"]),
    ("2x^2-8", ["(x + 2)", "(x - 2)", "2"]),
    ("x^3+2x^2-5x-6", ["(x + 3)", "(x + 1)", "(x - 2)"]),
    ("x^2+1", ["x^2 + 1"]),
])
def test_factorizar_polinomios(texto, esperado):
    assert [f for f, _ in PO.factorizar(PO.desde_texto(texto, "x", T()), "x", T())] == esperado


def test_un_cubico_sin_raiz_racional_no_se_factoriza_de_mas():
    """§5.4: el motor dice lo que no sabe, en vez de emitir una factorización falsa."""
    factores = [f for f, _ in PO.factorizar(PO.desde_texto("x^3+x+1", "x", T()), "x", T())]
    assert factores == ["x^3 + x + 1"]


def test_identidades_notables():
    """La identidad se **verifica** por formas normales, no se reconoce por aspecto.

    Dentro de una familia las dos ramas son identidades ambas (``(a+b)^2`` y
    ``(a-b)^2`` son las dos verdade para todo ``a``, ``b``), así que la primera
    que coincide gana. Lo que la calculadora afirma es que la expansión es
    correcta, no cuál de las dos formas escribió el alumno: para eso está
    ``forma``, que sí decide la familia.
    """
    a, b = mx.parse("x"), mx.parse("1")
    assert PO.identidades(a, b, "x", T(), "cuadrado") == "(a + b)^2 = a^2 + 2ab + b^2"
    assert PO.identidades(a, b, "x", T(), "producto") == "(a + b)(a - b) = a^2 - b^2"
    # y funciona con expresiones escritas al revés, porque compara formas normales
    assert PO.identidades(mx.parse("2"), mx.parse("y"), "x", T(), "cuadrado").startswith(
        "(a + b)^2")


def test_una_forma_desconocida_se_rechaza():
    with pytest.raises(ValidationError):
        PO.identidades(mx.parse("x"), mx.parse("1"), "x", T(), "tercera")


@pytest.mark.parametrize("a,b,esperado", [
    ("x+1", "x-1", "x^2 - 1"),
    ("x", "1", "x"),
    ("2x", "x", "2*x^2"),
    ("x", "x", "x^2"),
    ("x+1", "x+1", "x^2 + 2*x + 1"),
])
def test_producto_de_polinomios(a, b, esperado):
    producto = PO.multiplicar(PO.desde_texto(a, "x", T()), PO.desde_texto(b, "x", T()),
                              "x", T())
    assert PO.representar(producto) == esperado


def test_suma_de_polinomios():
    assert PO.representar(PO.sumar(PO.desde_texto("x+1", "x", T()),
                                   PO.desde_texto("2x", "x", T()), 1, "x", T())) == "3*x + 1"
    assert PO.representar(PO.sumar(PO.desde_texto("x+1", "x", T()),
                                   PO.desde_texto("2x", "x", T()), -1, "x", T())) == "-x + 1"


def test_evaluar_por_el_horner():
    assert PO.evaluar(PO.desde_texto("x^2-2x+1", "x", T()), Fraction(3)) == 4
    assert PO.evaluar(PO.desde_texto("x^2-5x+6", "x", T()), Fraction(2)) == 0


def test_un_polinomio_con_irrat_o_funcion_se_rechaza():
    """El coeficiente tiene que ser racional: si no, no es un polinomio de ML-1."""
    with pytest.raises(ValidationError):
        PO.desde_texto("sin(x)", "x", T())
    with pytest.raises(ValidationError):
        PO.desde_texto("pi*x", "x", T())
    with pytest.raises(ValidationError):
        PO.desde_texto("x+y", "x", T())


def test_la_lectura_del_polinomio_explica_la_representacion():
    traza = T()
    PO.desde_texto("2x^2+x", "x", traza)
    paso = [s for s in traza.steps if s.rule == "polinomio.lectura"][0]
    assert "coeficientes" in paso.why


def test_las_bases_llegan_a_36():
    """0-9 y A-Z: de 2 a 36 (antes se paraba en 16), contrastado con int()."""
    from academic_core.domain.engineering.mathlab import bases as B

    for base in (17, 20, 32, 36):
        for n in (0, 35, 12345678, -999):
            texto = B.a_base(n, base)
            assert int(texto, base) == n and B.de_base(texto, base) == n
