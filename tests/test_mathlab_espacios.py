# SPDX-License-Identifier: MIT
"""Espacios vectoriales como en la carpeta de Álgebra Lineal (exámenes UPC):
suma e intersección con Grassmann, cambios de base por la canónica, proyección
ortogonal, núcleo/imagen, antiimágenes, matriz en otra base, invariantes,
independencia con parámetros y valores singulares. Todo exacto sobre ℚ con
segundo camino; lo no exacto, con su motivo.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx


def test_suma_interseccion_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    F = EV.ecuaciones_a_generadores(["x+z", "y-t"], ["x", "y", "z", "t"])
    G = [[1, 1, 0, 0], [1, 0, 1, 0], [2, 1, 1, 0]]
    r = EV.suma_interseccion(F, G)
    assert (r.dim_suma, r.dim_int) == (4, 0)
    assert r.directa and r.suma_total


def test_ecuaciones_generadores_ida_y_vuelta():
    from academic_core.domain.engineering.mathlab import espacios as EV

    F = EV.ecuaciones_a_generadores(["x+z", "y-t"], ["x", "y", "z", "t"])
    assert len(F) == 2
    ecs = EV.generadores_a_ecuaciones(F, ["x", "y", "z", "t"])
    assert len(ecs) == 2
    F2 = EV.ecuaciones_a_generadores([mx.text(e) for e in ecs], ["x", "y", "z", "t"])
    assert len(F2) == 2


def test_cambio_base_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    # v dado por sus coords (1,3) en B1: v canónico = B1·c1 = (7,5);
    # coords en B2 = B2⁻¹·(7,5) = (1/5, 11/5)
    B1 = [[1, 2], [2, 1]]
    B2 = [[2, 3], [3, 2]]
    c2 = EV.cambio_base_coords([Fraction(1), Fraction(3)], B1, B2)
    assert c2 == [Fraction(1, 5), Fraction(11, 5)]


def test_proyeccion_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    proy, comp, d2 = EV.proyeccion([2, 1, -1, -2], [[0, 1, 0, 2], [0, 2, 0, 1]])
    assert proy == [Fraction(0), Fraction(1), Fraction(0), Fraction(-2)]
    assert d2 == Fraction(5)


def test_complemento_y_distancia_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    F = EV.complemento_ortogonal([[1, 2, 1, 3]])
    assert len(F) == 3
    d2 = EV.distancia([2, 1, 3, 1], F)[1]
    assert d2 == Fraction(20, 3)


def test_nucleo_imagen_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    M = [[2, -1, 0], [1, -1, 0], [4, -3, 0]]
    ker, ima, rango = EV.nucleo_imagen(M)
    assert len(ker) == 1 and ker[0] == [Fraction(0), Fraction(0), Fraction(1)]
    assert rango == 2
    assert EV.contiene([1, 0, 1], ima) and EV.contiene([1, 1, 3], ima)


def test_antiimagen_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    M = [[1, 1, 1], [2, 0, -1]]
    p, ker = EV.antiimagen(M, [2, 0])
    assert p == [Fraction(0), Fraction(2), Fraction(0)]
    assert len(ker) == 1
    k = ker[0]
    assert [M[0][0] * k[0] + M[0][1] * k[1] + M[0][2] * k[2],
            M[1][0] * k[0] + M[1][1] * k[1] + M[1][2] * k[2]] == [0, 0]
    assert k[0] * 2 == k[2] and k[1] * 2 == -3 * k[2]


def test_matriz_en_base_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    A = [[1, -4], [4, 1]]
    B = EV.matriz_en_base(A, [[-1, 3], [3, -1]])
    assert B == [[Fraction(-2), Fraction(5)], [Fraction(-5), Fraction(4)]]


def test_invariante_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    def mat(a):
        return [[1, a, -1], [2, -1, -1], [1, 3, 2]]

    assert EV.invariante(mat(0), {"ecuaciones": ["x-y"], "vars": ["x", "y", "z"]})
    assert not EV.invariante(mat(1), {"ecuaciones": ["x-y"], "vars": ["x", "y", "z"]})


def test_independencia_parametro():
    from academic_core.domain.engineering.mathlab import espacios as EV

    casos = EV.discusion_parametro([["a", "1"], ["1", "1"]], "a")
    assert ("a != 1", 2) in casos and ("a = 1", 1) in casos
    with pytest.raises(Exception, match="parámetro"):
        EV.discusion_parametro([["a", "b"], ["1", "1"]], "a")


def test_independencia_numerica_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    assert not EV.independientes([[2, 1, -3], [1, 0, -4], [1, 1, 1]])
    assert EV.independientes([[2, 1, -3], [1, 0, -4], [0, 1, 1]])


def test_subespacio_matrices_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    base = [[1, -1, 1, 1], [1, 1, -1, 1]]
    assert EV.coordenadas([6, 0, 0, 6], base) == [Fraction(3), Fraction(3)]


def test_subespacio_polinomios_examen():
    from academic_core.domain.engineering.mathlab import espacios as EV

    base, dim = EV.base_de([[0, -1, 0], [0, -2, 1], [0, 3, 3]])
    assert dim == 2 and len(base) == 2


def test_valores_singulares():
    from academic_core.domain.engineering.mathlab import espacios as EV

    vals = EV.valores_singulares([[3, 0], [0, 4]])
    assert sorted(float(mx.valor_real(v, {})) for v in vals) == [3.0, 4.0]


def test_rechazos_honestos():
    from academic_core.domain.engineering.mathlab import espacios as EV

    with pytest.raises(Exception, match="no pertenece|fuera del subespacio"):
        EV.coordenadas([1, 0], [[1, 1]])
    with pytest.raises(Exception, match="sin anti-imagen|incompatible"):
        EV.antiimagen([[1, 0], [0, 0]], [0, 1])


def test_examenes_reales():
    """Casos de los exámenes de la carpeta de Álgebra Lineal."""
    from academic_core.domain.engineering.mathlab import espacios as EV
    from academic_core.domain.engineering.mathlab.trace import Trace

    # Parcial 2018 - Problema 1: F por ecuaciones, G por generadores
    F = EV.ecuaciones_a_generadores(["x - 2*y + z", "2*x - y - t"],
                                    ["x", "y", "z", "t"], Trace())
    assert len(F) == 2
    G = [[2, -1, 0, 3], [3, -1, 1, 4]]
    r = EV.suma_interseccion(F, G, Trace())
    # F∩G ≠ {0}: el vector (0,-1,-2,1) = 3*(2,-1,0,3) - 2*(3,-1,1,4) está en ambos
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (2, 2, 3, 1)
    assert not r.directa and not r.suma_total

    # Parcial 2018 - Problema 2: cambio de base
    B1 = [[1, 0, 0], [1, 1, 0], [1, 1, 1]]
    B2 = [[1, 1, 1], [0, 1, 1], [0, 0, 1]]
    c2 = EV.cambio_base_coords([Fraction(4), Fraction(3), Fraction(2)], B1, B2, Trace())
    assert c2 == [Fraction(9), Fraction(-4), Fraction(-3)]

    # Parcial 2019 - Problema 1: Col(A), Nul(A) para a=1
    ker, ima, rango = EV.nucleo_imagen([[1, 1, 1], [1, 2, 2], [3, 3, 3]], Trace())
    assert rango == 2 and len(ker) == 1 and len(ima) == 2

    # Parcial 2020 - Problema 2: F+G, F∩G en polinomios (como subespacios de R³)
    r = EV.suma_interseccion([[1, 0, 3], [0, 1, 0]],  # F = ⟨x²+3, x⟩
                              [[1, 2, 0], [0, 2, -1]],  # G = ⟨x²+2x, 2x-1⟩
                              Trace())
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (2, 2, 3, 1)

    # Parcial 2021 - Problema 1: F por ecuaciones + G por generadores en R⁴
    F = EV.ecuaciones_a_generadores(["x + y + z", "x - y + 3*t"],
                                    ["x", "y", "z", "t"], Trace())
    assert len(F) == 2
    r = EV.suma_interseccion(F, [[-1, 1, 1, 1], [2, 1, -2, 0]], Trace())
    # F∩G ≠ {0}: el vector (-3,0,3,1) está en ambos
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (2, 2, 3, 1)

    # Segundo Parcial 2018 - Problema 1: S = Col(M), M 4×2
    M_cols = [[1, 0, 0, 2], [2, 1, 1, 1]]
    orto = EV.complemento_ortogonal(M_cols, Trace())
    assert len(orto) == 2
    proy, comp, d2 = EV.proyeccion([1, 2, 3, 4], M_cols, Trace())
    assert proy == [Fraction(3), Fraction(1), Fraction(1), Fraction(3)]
    assert d2 == Fraction(10)
    ker, ima, rango = EV.nucleo_imagen([[1, 2], [0, 1], [0, 1], [2, 1]], Trace())
    assert rango == 2 and len(ker) == 0 and len(ima) == 2

    # Segundo Parcial 2018 - Problema 2: φ con parámetro
    # F = {(x,y,z) : x + y - z = 0} invariante solo si a = 0
    assert EV.invariante([[0, 1, 0], [0, -1, 1], [0, 0, 1]],
                         {"ecuaciones": ["x + y - z"], "vars": ["x", "y", "z"]}, Trace())
    assert not EV.invariante([[1, 0, 0], [0, -1, 1], [0, 0, 1]],
                             {"ecuaciones": ["x + y - z"], "vars": ["x", "y", "z"]}, Trace())

    # Segundo Parcial 2019 - Problema 1: f con imágenes dadas
    M = EV.aplicacion_desde_base([[1, -1], [2, 6], [0, 2]], None, Trace())
    assert M == [[1, 2, 0], [-1, 6, 2]]

    # Final 2020 - Problema 1: F+G, F∩G en polinomios (como subespacios de R⁴)
    r = EV.suma_interseccion([[1, 0, 0, -1], [0, 1, 0, -1], [0, 0, 1, -1]],  # F
                              [[-1, 0, 4, 2], [1, 0, 1, 2]],  # G
                              Trace())
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (3, 2, 4, 1)

    # Final 2021 - Problema 1: S+T, S∩T en R⁴
    r = EV.suma_interseccion([[2, 2, 1, 0], [0, -1, 0, 1]],  # S
                              [[1, 1, 1, 1], [1, -1, 0, 1]],  # T
                              Trace())
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (2, 2, 3, 1)

    # Final 2022 - Problema 1: Im f + F (a=0)
    r = EV.suma_interseccion([[1, 1, 2], [0, -1, 0]],  # Im f
                              [[1, 0, 1], [0, 1, -1]],  # F
                              Trace())
    assert (r.dim_f, r.dim_g, r.dim_suma, r.dim_int) == (2, 2, 3, 1)

    # Final 07-17 - Problema 1: Coordenadas en base de polinomios
    c = EV.cambio_base_coords([Fraction(1), Fraction(2), Fraction(3)],
                              [[1, 1, 0], [0, 1, 1], [1, 1, 1]],
                              [[1, 0, 0], [0, 1, 0], [0, 0, 1]], Trace())
    assert c == [Fraction(4), Fraction(6), Fraction(5)]

    # Final 07-17 - Problema 3: Antiimágenes
    p, ker = EV.antiimagen([[1, 1, 2, 1], [1, 0, 1, 1], [2, 0, -1, -1]],
                           [6, 1, 0], Trace())
    assert p == [Fraction(1, 3), Fraction(13, 3), Fraction(2, 3), Fraction(0)]
    assert len(ker) == 1

    # Final 07-17 - Problema 4: Subespacio invariante
    # F = {(x,y,z) : x-z = 0} invariante solo si a = 1
    assert EV.invariante([[1, 1, 1], [1, -1, 0], [0, 1, 2]],
                         {"ecuaciones": ["x - z"], "vars": ["x", "y", "z"]}, Trace())
    assert not EV.invariante([[1, 1, 1], [0, -1, 0], [0, 0, 2]],
                             {"ecuaciones": ["x - z"], "vars": ["x", "y", "z"]}, Trace())

    # Coordenadas en subespacio de ℝ⁴
    c = EV.coordenadas([6, 0, 0, 6], [[1, -1, 1, 1], [1, 1, -1, 1]], Trace())
    assert c == [Fraction(3), Fraction(3)]


def test_calculadora_espacios():
    import academic_core.domain.engineering.mathlab as ML

    casos = [
        {"calculo": "suma_interseccion",
         "F": [[1, 0, 1, 0], [0, 1, 0, 1]],
         "G": [[1, 1, 0, 0], [1, 0, 1, 0]]},
        {"calculo": "ecuaciones", "ecuaciones": ["x+z", "y-t"],
         "vars": ["x", "y", "z", "t"]},
        {"calculo": "cartesianas", "generadores": [[1, 0, 1, 0], [0, 1, 0, 1]],
         "vars": ["x", "y", "z", "t"]},
        {"calculo": "cambio_base", "coords": [1, 3], "B1": [[1, 2], [2, 1]],
         "B2": [[2, 3], [3, 2]]},
        {"calculo": "matriz_base", "matriz": [[1, -4], [4, 1]],
         "base": [[-1, 3], [3, -1]]},
        {"calculo": "aplicacion", "imagenes": [[1, 0], [0, 1]]},
        {"calculo": "nucleo_imagen", "matriz": [[2, -1, 0], [1, -1, 0], [4, -3, 0]]},
        {"calculo": "antiimagen", "matriz": [[1, 1, 1], [2, 0, -1]], "w": [2, 0]},
        {"calculo": "proyeccion", "v": [2, 1, -1, -2],
         "H": [[0, 1, 0, 2], [0, 2, 0, 1]]},
        {"calculo": "ortogonal", "H": [[1, 2, 1, 3]]},
        {"calculo": "distancia", "v": [2, 1, 3, 1], "H": [[1, 2, 1, 3]]},
        {"calculo": "invariante", "matriz": [[1, 0, 0], [0, 1, 0], [0, 0, 0]],
         "F": {"generadores": [[1, 0, 0], [0, 1, 0]]}},
        {"calculo": "parametro", "matriz": [["a", 1], [1, 1]], "parametro": "a"},
        {"calculo": "singulares", "matriz": [[3, 0], [0, 4]]},
    ]
    for entrada in casos:
        r = ML.calcular(ML.Peticion("espacios", entrada))
        assert r.sello.verdict == "verificado", (entrada["calculo"], r.exacto)
