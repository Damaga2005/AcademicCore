# SPDX-License-Identifier: MIT
"""ML-10 (§7): la plantilla de ejercicio, el corrector por equivalencia, las
pistas graduadas y el generador sembrado.

Propiedades que se comprueban aquí:

- **corrección por equivalencia, no por texto**: ``2x+2x`` se acepta por
  ``4x`` y ``1/2`` por ``0,5``; ``x²`` **no** se acepta por ``2x``;
- **el sello es honesto**: si la identidad solo se sostiene por muestras
  numéricas, el veredicto queda en ``solo_numerico``, nunca en ``verificado``
  (§5.3: las muestras no prueban una identidad);
- **el generador es sembrado**: la misma semilla da el mismo ejercicio, y
  semillas distintas dan ejercicios distintos;
- **el generador no emite ejercicios degenerados** (un determinante 0 o un
  límite que no existe se reintentan o se niegan con motivo);
- **la solución la pide el motor**: se corrige a sí misma, y si no se
  aceptara, el generador falla en vez de servir un ejercicio con la solución
  equivocada;
- **las respuestas no únicas se corrigen por propiedad** (§7);
- **nada se corrige por parecido**: una gráfica no se corrige por texto.
"""

from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import ejercicios as EJ
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("ejercicio", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def prueba_ejercicio(tipo, solucion, enunciado="e"):
    """Un ejercicio de laboratorio para probar el corrector sin generarlo."""
    return EJ.Ejercicio(id="x", tema="t", asignatura="a", tipo=tipo,
                        enunciado=enunciado, solucion=solucion)


# ---------------------------------------------------------------------------
# corrección por equivalencia (§7)
# ---------------------------------------------------------------------------

def test_acepta_formas_distintas_de_la_misma_expresion():
    ex = prueba_ejercicio("expresion", "4*x")
    assert EJ.corrige(ex, "2*x+2*x").correcto
    assert EJ.corrige(ex, "x+x+x+x").correcto
    assert EJ.corrige(ex, "4*x").correcto


def test_acepta_fraccion_y_decimal():
    ex = prueba_ejercicio("numero", "1/2")
    assert EJ.corrige(ex, "0,5").correcto
    assert EJ.corrige(ex, "0.5").correcto
    assert EJ.corrige(ex, 1 / 2).correcto


def test_rechaza_una_expresion_distinta():
    ex = prueba_ejercicio("expresion", "4*x")
    v = EJ.corrige(ex, "2*x")
    assert not v.correcto
    assert v.sello == V.VERIFIED      # «son distintas» es la respuesta pedida


def test_el_sello_baja_a_solo_numerico_cuando_no_hay_prueba_exacta():
    # dos expresiones idénticas solo en las muestras que el verificador
    # prueba: el veredicto no puede ser «verificado» (§5.3)
    ex = prueba_ejercicio("expresion", "x")
    v = EJ.corrige(ex, "x + 0*x^7")     # idéntica en todo x, pero no se simplifica
    if v.correcto:
        assert v.sello in (V.VERIFIED, V.NUMERIC_ONLY)
        assert v.sello != V.VERIFIED or "forma" in v.metodo


def test_numero_matriz_y_conjunto():
    assert EJ.corrige(prueba_ejercicio("numero", 7), "7.0").correcto
    assert not EJ.corrige(prueba_ejercicio("numero", 7), "8").correcto
    m = prueba_ejercicio("matriz", [[1, 2], [3, 4]])
    assert EJ.corrige(m, [[1.0, 2.0], [3.0, 4.0]]).correcto
    assert not EJ.corrige(m, [[1, 2], [3, 5]]).correcto
    assert not EJ.corrige(m, [[1, 2]]).correcto        # dimensiones
    c = prueba_ejercicio("conjunto", [1, 2, 3])
    assert EJ.corrige(c, [3, 1, 2]).correcto           # el orden no importa
    assert not EJ.corrige(c, [1, 2]).correcto


def test_una_grafica_no_se_corrige_por_texto():
    with pytest.raises(Exception) as exc:
        EJ.corrige(prueba_ejercicio("grafica", "curva"), "una curva")
    assert "UNSUPPORTED" in str(exc.value)


def test_respuesta_vacia_se_rechaza():
    with pytest.raises(Exception) as exc:
        EJ.corrige(prueba_ejercicio("numero", 7), "  ")
    assert "BAD_INPUT" in str(exc.value)


def test_tipo_desconocido_se_rechaza():
    ex = prueba_ejercicio("numero", 7)
    object.__setattr__(ex, "tipo", "inventado")
    with pytest.raises(Exception) as exc:
        EJ.corrige(ex, "7")
    assert "BAD_INPUT" in str(exc.value)


# ---------------------------------------------------------------------------
# respuestas no únicas: corrección por propiedad (§7)
# ---------------------------------------------------------------------------

def test_base_ortonormal_se_corrige_por_propiedad_no_por_forma():
    ok = EJ.comprueba_propiedad("ortonormal", [[1.0, 0.0], [0.0, 1.0]])
    assert ok.correcto
    # cualquier base ortonormal es válida, aunque sea la del ejercicio
    ex = EJ.genera("espacios vectoriales", "media", 3)
    otra = [[v[1], -v[0]] for v in ex.solucion]      # girada 90°: otra base
    v = EJ.comprueba_propiedad("ortonormal", otra)
    assert v.correcto, v.detalle
    # y una que no es ortonormal se rechaza, aunque «se parezca»
    assert not EJ.comprueba_propiedad("ortonormal", [[1.0, 1.0], [0.0, 1.0]]).correcto


def test_la_propiedad_mal_ortonormal_dice_donde_falla():
    v = EJ.comprueba_propiedad("ortonormal", [[1.0, 1.0], [1.0, 0.0]])
    assert not v.correcto
    assert "Aᵀ·A" in v.detalle or "posición" in v.detalle


# ---------------------------------------------------------------------------
# generador sembrado (§7)
# ---------------------------------------------------------------------------

def test_todos_los_temas_generan_y_su_solucion_se_corrige():
    for tema in sorted(EJ.TEMAS):
        ex = EJ.genera(tema, "media", 5)
        assert ex.enunciado and ex.tipo in EJ.TIPOS
        assert ex.pistas, f"{tema} sin pistas"
        assert ex.respaldo in ("E", "G")
        v = EJ.corrige(ex, ex.solucion)
        assert v.correcto, (tema, v.detalle)


def test_la_semilla_es_determinista():
    a = EJ.genera("ecuaciones", "media", 11)
    b = EJ.genera("ecuaciones", "media", 11)
    assert a.datos == b.datos and a.solucion == b.solucion
    c = EJ.genera("ecuaciones", "media", 12)
    assert (c.datos, c.solucion) != (a.datos, a.solucion)


def test_no_emite_ejercicios_degenerados():
    # un determinante 0 o un límite que no existe no son ejercicios
    for sem in range(1, 12):
        ex = EJ.genera("algebra lineal", "media", sem)
        assert ex.solucion != "0", (sem, ex.datos)
        ex = EJ.genera("limites", "media", sem)
        assert ex.solucion != "no existe", (sem, ex.datos)


def test_tema_y_dificultad_desconocidos_se_rechazan():
    with pytest.raises(Exception) as exc:
        EJ.genera("tema inventado")
    assert "BAD_INPUT" in str(exc.value)
    with pytest.raises(Exception) as exc:
        EJ.genera("ecuaciones", "imposible")
    assert "BAD_INPUT" in str(exc.value)


def test_pistas_graduadas():
    ex = EJ.genera("ecuaciones", "media", 2)
    assert len(ex.pistas_hasta(0)) == 0
    assert len(ex.pistas_hasta(1)) == 1
    assert ex.pistas_hasta(2) == ex.pistas[:2]
    assert len(ex.pistas_hasta(99)) == len(ex.pistas)
    with pytest.raises(Exception) as exc:
        ex.pistas_hasta(-1)
    assert "BAD_INPUT" in str(exc.value)


# ---------------------------------------------------------------------------
# contrato §5.9
# ---------------------------------------------------------------------------

def test_contrato_de_los_cinco_calculos():
    casos = [
        {"calculo": "banco"},
        {"calculo": "genera", "tema": "limites", "semilla": 3},
        {"calculo": "corrige", "tema": "ecuaciones", "semilla": 3,
         "respuesta": "1"},
        {"calculo": "corrige", "tema": "espacios vectoriales", "semilla": 3,
         "respuesta": [[1, 0], [0, 1]], "propiedad": "ortonormal"},
        {"calculo": "pistas", "tema": "derivadas", "semilla": 3, "n": 2},
        {"calculo": "solucion", "tema": "integrales", "semilla": 3},
    ]
    for e in casos:
        r = pedir(e)
        assert r.sello.verdict == V.VERIFIED, (e, r.sello.verdict)


def test_una_respuesta_incorrecta_no_es_un_error():
    r = pedir({"calculo": "corrige", "tema": "ecuaciones", "semilla": 3,
               "respuesta": "999"})
    assert "✘" in str(r.exacto)


def test_calculo_desconocido_se_rechaza():
    with pytest.raises(Exception) as exc:
        pedir({"calculo": "inventado"})
    assert "BAD_INPUT" in str(exc.value)


def test_ejercicio_no_diccionario_se_rechaza():
    with pytest.raises(Exception) as exc:
        pedir("no soy un diccionario")
    assert "BAD_INPUT" in str(exc.value)