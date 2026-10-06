# SPDX-License-Identifier: MIT
"""ML-12 (§5.11): cada cálculo con la convención declarada y con la contraria."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML


def _calc(entrada, **convenciones):
    return ML.calcular(ML.Peticion("convencion", entrada,
                                   convenciones=ML.ConvencionConjunto.of(**convenciones)))


def test_trampa_cien_veces_inferior():
    r = _calc({"tipo": "db", "razon": 0.01, "magnitud": "amplitud"}, db="20log10")
    assert r.exacto.startswith("-40 dB") and "-20 dB" in r.exacto
    malo = _calc({"tipo": "db", "razon": 0.01, "magnitud": "amplitud"}, db="10log10")
    assert "revisa el enunciado" in malo.exacto


def test_potencia_igual_con_ef_y_pico():
    r = _calc({"tipo": "valor_efectivo", "valor": 10, "R": 50}, valor_efectivo="pico")
    assert "P = 1 W con las dos" in r.exacto


def test_desviacion_relacion_exacta():
    r = _calc({"tipo": "desviacion_tipica", "datos": [1, 2, 3, 4]}, desviacion_tipica="n-1")
    assert "s² = 5/3" in r.exacto and "s² = 5/4" in r.exacto


@pytest.mark.parametrize("a,n,euclideo,c", [(-7, 3, 2, -1), (7, -3, 1, 1), (-7, -3, 2, -1),
                                            (7, 3, 1, 1)])
def test_resto(a, n, euclideo, c):
    r = _calc({"tipo": "resto_division", "a": a, "n": n}, resto_division="no_negativo")
    assert r.exacto.startswith(f"{euclideo} (no_negativo); con con_signo: {c}.")


def test_interes_y_chauvenet():
    r = _calc({"tipo": "finanzas", "tasa": "0.12", "periodos": 12}, finanzas="nominal")
    assert "i = 0.12682503" in r.exacto
    r = _calc({"tipo": "chauvenet", "datos": [10.1, 10.0, 9.9, 10.2, 10.0, 9.8, 10.1, 12.5]},
              chauvenet="fijo_3")
    assert "NO coinciden" in r.exacto


def test_convencion_en_la_entrada_se_imprime_y_sin_ella_se_pide():
    r = ML.calcular(ML.Peticion("convencion", {"tipo": "base_logaritmos", "x": 8,
                                               "convencion": "log2"}))
    assert r.convenciones.get("base_logaritmos") == "log2"
    assert sum(s.kind == "convencion" for s in r.traza.steps) == 1
    with pytest.raises(Exception, match="BAD_CONVENTION"):
        ML.calcular(ML.Peticion("convencion", {"tipo": "db", "razon": 2}))
