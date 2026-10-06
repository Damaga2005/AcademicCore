# SPDX-License-Identifier: MIT
"""T-20/T-24: every rewrite objective reachable from the calculator (2026-10-06)."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.domain.engineering.mathlab import verify as V


def _t(expr, objetivo):
    return ML.calcular(ML.Peticion("transformar", {"expr": expr, "objetivo": objetivo}))


@pytest.mark.parametrize("expr,objetivo,esperado", [
    ("sin(x)*cos(3*x)", "producto_a_suma", "-1/2·sen(2·x) + 1/2·sen(4·x)"),
    ("cos(x)^4", "potencias", "1/2·cos(2·x) + 1/8·cos(4·x) + 3/8"),
    ("sin(x)^3", "potencias", "-1/4·sen(3·x) + 3/4·sen(x)"),
    ("sin(x)+sin(3*x)", "suma_a_producto", "2·sen(2·x)·cos(x)"),
    ("sin(x+y)", "expandir", "sen(x)·cos(y) + cos(x)·sen(y)"),
])
def test_la_forma_es_la_de_los_libros(expr, objetivo, esperado):
    assert _t(expr, objetivo).exacto == esperado


@pytest.mark.parametrize("objetivo", [n for n, o in T.OBJETIVOS.items() if o.es_reescritura])
def test_todo_objetivo_de_reescritura_tiene_operacion_y_conserva_el_valor(objetivo):
    for expr in ("sin(x)^2*cos(3*x)", "sinh(2*x)", "cos(x)+cos(2*x)", "tan(x)"):
        r = _t(expr, objetivo)
        ok, _m, _d = V.numeric_agreement(r.exacto_expr, mx.parse(expr))
        assert ok, (objetivo, expr, r.exacto)
        assert r.sello.verdict != V.DISCREPANT


def test_un_objetivo_que_no_reescribe_se_rechaza_con_la_lista():
    with pytest.raises(Exception) as exc:
        _t("x", "derivar")
    assert "expandir" in str(exc.value)
