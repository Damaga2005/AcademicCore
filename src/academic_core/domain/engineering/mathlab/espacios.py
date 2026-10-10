# SPDX-License-Identifier: MIT
"""ML-3 (carpeta de Álgebra Lineal): subespacios como los del curso.

Un subespacio se da por generadores o por ecuaciones homogéneas; todo lo demás
sale de ahí con Gauss exacto sobre ℚ: base y dimensión, pertenencia y
coordenadas, paso de ecuaciones a generadores y vuelta, suma e intersección con
Grassmann comprobado, cambio de base por la canónica, matriz en otra base,
núcleo/imagen y antiimágenes, proyección ortogonal con Gram-Schmidt, comple-
mento ortogonal y distancia, invariantes, independencia con un parámetro (deter-
minante interpolado exacto) y valores singulares exactos.

Cada resultado lleva traza con «por qué» y un segundo camino independiente;
lo que no sale exacto se rechaza con su motivo (§5.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _fracs(vects) -> list[list[Fraction]]:
    """Vectores a Fractions; filas de igual longitud y no vacías."""
    try:
        M = [[Fraction(str(x)) for x in v] for v in vects]
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise _error("BAD_INPUT", f"vectores con entradas no numéricas exactas: {exc}") from None
    if not M or any(len(f) != len(M[0]) for f in M) or not M[0]:
        raise _error("BAD_INPUT", "lista de vectores no vacía y todos de igual dimensión")
    return M


def _K():
    from academic_core.domain.engineering.mathlab import lineal as L

    return L.cuerpo("Q")


def _a_matriz(M: list[list[Fraction]]):
    K = _K()
    return [[K.de(x) for x in fila] for fila in M]


def rango_de(gens) -> int:
    """Dimensión del generado."""
    from academic_core.domain.engineering.mathlab import lineal as L

    M = _fracs(gens)
    return L.rango(_a_matriz(M), _K())


def independientes(gens) -> bool:
    """Rango igual al número de vectores."""
    M = _fracs(gens)
    return rango_de(M) == len(M)


def base_de(gens, trace: Trace | None = None) -> tuple[list[list[Fraction]], int]:
    """Base del generado (generadores independientes) y dimensión."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    M = _fracs(gens)
    base = []
    for v in M:
        if L.rango(_a_matriz(base + [v]), _K()) > len(base):
            base.append(v)
    trace.regla("espacios.base", f"dim = {len(base)}",
                why="se queda cada vector que sube el rango (Gauss exacto)")
    for v in M:
        if _coordenadas_crudas(v, base) is None:
            raise _error("INTERNAL", "un generador no está en la base hallada")
    trace.verificacion("espacios.base_sub", "todo generador es combinación de la base")
    return base, len(base)


def _coordenadas_crudas(v: list[Fraction], base: list[list[Fraction]]):
    """Coordenadas de v en la base (lista de vectores) o None si no pertenece."""
    from academic_core.domain.engineering.mathlab import lineal as L

    if not base:
        return [] if all(x == 0 for x in v) else None
    n = len(base[0])
    A = [[base[j][i] for j in range(len(base))] for i in range(n)]
    sistema = L.resolver_sistema(_a_matriz(A), [L.cuerpo("Q").de(x) for x in v], _K())
    if sistema.particular is None:
        return None
    return [Fraction(x) for x in sistema.particular]


def contiene(v, base) -> bool:
    """v pertenece al generado de la base."""
    vv = [Fraction(str(x)) for x in v]
    B, _ = base_de(base)
    return _coordenadas_crudas(vv, B) is not None


def coordenadas(v, base, trace: Trace | None = None) -> list[Fraction]:
    """Coordenadas de v en una base; fuera del subespacio, con su motivo."""
    trace = trace if trace is not None else Trace()
    vv = [Fraction(str(x)) for x in v]
    B, _ = base_de(base, trace)
    c = _coordenadas_crudas(vv, B)
    if c is None:
        raise _error("NOT_IN", f"{vv} no pertenece al subespacio generado")
    trace.regla("espacios.coordenadas", f"coords = ({', '.join(str(x) for x in c)})",
                why="sistema lineal exacto con la base por columnas")
    for i in range(len(vv)):
        if sum(B[j][i] * c[j] for j in range(len(B))) != vv[i]:
            raise _error("INTERNAL", "las coordenadas no reconstruyen el vector")
    trace.verificacion("espacios.coords_sub", "combinación sustituida da el vector")
    return c


def ecuaciones_a_generadores(ecuaciones, vars: list[str],
                             trace: Trace | None = None) -> list[list[Fraction]]:
    """Ecuaciones lineales homogéneas → base del subespacio solución."""
    from academic_core.domain.engineering.mathlab import lineal as L
    from academic_core.domain.engineering.mathlab import varias as MV

    trace = trace if trace is not None else Trace()
    filas = []
    for e in ecuaciones:
        expr = mx.parse(str(e)) if isinstance(e, str) else e
        r = MV._lin(expr, set(vars))
        if r is None:
            raise _no(f"«{mx.text(expr)}» no es lineal en {', '.join(vars)}")
        if r[1] != 0:
            raise _error("NOT_SUBSPACE", f"«{mx.text(expr)}» no es homogénea: no define "
                                        "un subespacio")
        filas.append([r[0].get(v, Fraction(0)) for v in vars])
    base = L.nucleo(_a_matriz(filas), _K(), trace)
    trace.regla("espacios.ecuaciones", f"base con {len(base)} vectores",
                why="las soluciones de un sistema homogéneo son el núcleo")
    return [[Fraction(x) for x in u] for u in base]


def generadores_a_ecuaciones(gens, vars: list[str],
                             trace: Trace | None = None) -> list[mx.Expr]:
    """Generadores → ecuaciones cartesianas (núcleo de la matriz por filas)."""
    from academic_core.domain.engineering.mathlab import lineal as L
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    M = _fracs(gens)
    if len(vars) != len(M[0]):
        raise _error("BAD_INPUT", "tantas variables como dimensión ambiente")
    ecs = L.nucleo(_a_matriz(M), _K(), trace)
    salida = []
    for c in ecs:
        total: mx.Expr = mx.Num(Fraction(0))
        for coef, v in zip(c, vars):
            if coef != 0:
                total = mx.Add(total, mx.Mul(LM._num(Fraction(coef)), mx.Sym(v)))
        salida.append(LM._limpio(total))
    trace.regla("espacios.cartesianas", f"{len(salida)} ecuaciones independientes",
                why="c·v = 0 para todo generador v: el núcleo de la matriz por filas")
    for e, c in zip(salida, ecs):
        for g in M:
            if sum(c[i] * g[i] for i in range(len(g))) != 0:
                raise _error("INTERNAL", "una ecuación no anula un generador")
    trace.verificacion("espacios.cart_sub", "cada ecuación se anula en cada generador")
    return salida


@dataclass(frozen=True)
class SumaInterseccion:
    base_suma: tuple
    base_int: tuple
    dim_f: int
    dim_g: int
    dim_suma: int
    dim_int: int
    directa: bool
    suma_total: bool

    def texto(self) -> str:
        return (f"dim F = {self.dim_f}, dim G = {self.dim_g}; "
                f"dim(F+G) = {self.dim_suma}, dim(F∩G) = {self.dim_int}"
                + ("; suma directa" if self.directa else "")
                + ("; F+G = todo el espacio" if self.suma_total else ""))


def suma_interseccion(F, G, trace: Trace | None = None) -> SumaInterseccion:
    """Bases de F+G y F∩G con Grassmann comprobado: dimF + dimG − dimI = dimS."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    F, G = _fracs(F), _fracs(G)
    if len(F[0]) != len(G[0]):
        raise _error("BAD_INPUT", "F y G tienen que vivir en el mismo ambiente")
    n = len(F[0])
    dim_f, dim_g = rango_de(F), rango_de(G)
    base_suma, dim_suma = base_de(F + G, trace)
    trace.regla("espacios.suma", f"base de F+G con {dim_suma} vectores",
                why="juntar generadores y quedarse los independientes")
    # F∩G: núcleo de [F | −G] por columnas; la parte en F da el vector común
    k, m = len(F), len(G)
    A = [[(F[j][i] if j < k else -G[j - k][i]) for j in range(k + m)] for i in range(n)]
    ker = L.nucleo(_a_matriz(A), _K(), trace)
    comunes = []
    for w in ker:
        a = [Fraction(x) for x in w[:k]]
        comunes.append([sum(a[j] * F[j][i] for j in range(k)) for i in range(n)])
    base_int, dim_int = base_de(comunes, trace) if comunes else ([], 0)
    trace.regla("espacios.interseccion", f"base de F∩G con {dim_int} vectores",
                why="F·a = G·b por el núcleo de [F|−G]; la parte en F es el vector común")
    if dim_f + dim_g - dim_int != dim_suma:
        raise _error("INTERNAL", "Grassmann no cuadra")
    for v in base_int:
        if _coordenadas_crudas(v, base_de(F)[0]) is None or \
                _coordenadas_crudas(v, base_de(G)[0]) is None:
            raise _error("INTERNAL", "un vector de F∩G no está en F o en G")
    trace.verificacion("espacios.grassmann",
                       f"{dim_f} + {dim_g} − {dim_int} = {dim_suma} (Grassmann)")
    return SumaInterseccion(tuple(tuple(u) for u in base_suma),
                            tuple(tuple(u) for u in base_int),
                            dim_f, dim_g, dim_suma, dim_int,
                            dim_int == 0, dim_suma == n)


def cambio_base_coords(c1, B1, B2, trace: Trace | None = None) -> list[Fraction]:
    """Coordenadas en B1 → coordenadas en B2 pasando por la canónica."""
    trace = trace if trace is not None else Trace()
    B1, B2 = _fracs(B1), _fracs(B2)
    c1 = [Fraction(str(x)) for x in c1]
    if not (len(B1) == len(B2) and all(len(b) == len(B1) for b in B1 + B2)
            and len(c1) == len(B1)):
        raise _error("BAD_INPUT", "bases cuadradas del mismo tamaño que las coords")
    v = [sum(B1[j][i] * c1[j] for j in range(len(B1))) for i in range(len(B1[0]))]
    trace.regla("espacios.por_canonica", "v en canónicas = B1·c1",
                why="se pasa por la base canónica: es el camino que no falla")
    c2 = coordenadas(v, B2, trace)
    if [sum(B2[j][i] * c2[j] for j in range(len(B2))) for i in range(len(B2[0]))] != v:
        raise _error("INTERNAL", "el cambio de base no reconstruye el vector")
    trace.verificacion("espacios.cambio_sub", "B2·c2 = v comprobado")
    return c2


def matriz_en_base(A, P, trace: Trace | None = None) -> list[list[Fraction]]:
    """P⁻¹·A·P con la traza y el determinante preservados (verificado)."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    A, P = _fracs(A), _fracs(P)
    n = len(A)
    if any(len(f) != n for f in A + P) or len(P) != n:
        raise _error("BAD_INPUT", "matriz y base cuadradas del mismo tamaño")
    K = _K()
    try:
        inv = L.inversa(_a_matriz(P), K, trace)
    except Exception as exc:
        raise _error("NOT_A_BASE", f"las columnas no forman base ({exc})") from None
    B = L.producto(L.producto([[Fraction(x) for x in fila] for fila in inv],
                               [[Fraction(x) for x in fila] for fila in A], K),
                   [[Fraction(x) for x in fila] for fila in P], K)
    B = [[Fraction(x) for x in fila] for fila in B]
    trace.regla("espacios.matriz_base", "B = P⁻¹·A·P",
                why="cambio de base en un endomorfismo: coordenadas nuevas a ambos lados")
    if sum(B[i][i] for i in range(n)) != sum(A[i][i] for i in range(n)):
        raise _error("INTERNAL", "la traza no se preserva")
    if L.determinante(_a_matriz(B), K) != L.determinante(_a_matriz(A), K):
        raise _error("INTERNAL", "el determinante no se preserva")
    trace.verificacion("espacios.semejanza", "traza y determinante iguales")
    return B


def aplicacion_desde_base(imagenes, B=None, trace: Trace | None = None) -> list[list[Fraction]]:
    """Matriz canónica de f dada por las imágenes de una base (canónica si no se da)."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    F = _fracs(imagenes)
    if B is None:
        M = [[F[j][i] for j in range(len(F))] for i in range(len(F[0]))]
        trace.regla("espacios.aplicacion", "columnas = imágenes de la canónica",
                    why="f(eⱼ) es la columna j en bases canónicas")
        return M
    B = _fracs(B)
    K = _K()
    try:
        inv = L.inversa(_a_matriz(B), K, trace)
    except Exception as exc:
        raise _error("NOT_A_BASE", f"el dominio no es base ({exc})") from None
    Fcol = [[F[j][i] for j in range(len(F))] for i in range(len(F[0]))]
    M = L.producto([[Fraction(x) for x in fila] for fila in Fcol],
                   [[Fraction(x) for x in fila] for fila in inv], K)
    M = [[Fraction(x) for x in fila] for fila in M]
    trace.regla("espacios.aplicacion_base", "M = F·B⁻¹",
                why="imagen por coordenadas en la base del dominio")
    for b, fb in zip(B, F):
        col = [sum(M[i][j] * b[j] for j in range(len(b))) for i in range(len(M))]
        if col != [Fraction(x) for x in fb]:
            raise _error("INTERNAL", "M no lleva un vector de la base a su imagen")
    trace.verificacion("espacios.aplic_sub", "M·b = f(b) en cada vector de la base")
    return M


def nucleo_imagen(M, trace: Trace | None = None):
    """Núcleo, imagen (columnas independientes) y rango, con rango-nulidad."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    M = _fracs(M)
    m, n = len(M), len(M[0])
    ker = [[Fraction(x) for x in u] for u in L.nucleo(_a_matriz(M), _K(), trace)]
    cols = [[M[i][j] for i in range(m)] for j in range(n)]
    ima, rango = base_de(cols, trace)
    if rango + len(ker) != n:
        raise _error("INTERNAL", "rango + dim Ker ≠ nº columnas")
    for k in ker:
        if [sum(M[i][j] * k[j] for j in range(n)) for i in range(m)] != [Fraction(0)] * m:
            raise _error("INTERNAL", "un vector del núcleo no se anula")
    trace.verificacion("espacios.rango_nulidad", f"{rango} + {len(ker)} = {n}")
    return ker, ima, rango


def antiimagen(M, w, trace: Trace | None = None):
    """Una anti-imagen particular más el núcleo; incompatible, con su motivo."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    M = _fracs(M)
    w = [Fraction(str(x)) for x in w]
    if len(w) != len(M):
        raise _error("BAD_INPUT", "el vector no vive en el codominio")
    K = _K()
    sistema = L.resolver_sistema(_a_matriz(M), [K.de(x) for x in w], K, trace)
    if sistema.particular is None:
        raise _error("NO_PREIMAGE", f"{w} no tiene anti-imagen (incompatible)")
    p = [Fraction(x) for x in sistema.particular]
    ker, _, _ = nucleo_imagen(M, trace)
    if [sum(M[i][j] * p[j] for j in range(len(p))) for i in range(len(M))] != w:
        raise _error("INTERNAL", "la particular no cumple M·x = w")
    trace.regla("espacios.antiimagen", "particular + Ker",
                why="todas las anti-imágenes difieren en el núcleo")
    trace.verificacion("espacios.anti_sub", "M·p = w sustituido")
    return p, ker


def proyeccion(v, H, trace: Trace | None = None):
    """Proyección ortogonal sobre ⟨H⟩ (Gram-Schmidt dentro), resto y ‖resto‖²."""
    from academic_core.domain.engineering.mathlab import algebra as AL

    trace = trace if trace is not None else Trace()
    v = [Fraction(str(x)) for x in v]
    H = _fracs(H)
    if len(H[0]) != len(v):
        raise _error("BAD_INPUT", "el vector y el subespacio no conviven")
    try:
        orto = AL.gram_schmidt([[Fraction(x) for x in u] for u in H], trace)
    except Exception as exc:
        raise _error("DEPENDENT", f"la base no es libre ({exc})") from None
    proy = [Fraction(0)] * len(v)
    for u in orto:
        num = sum(v[i] * u[i] for i in range(len(v)))
        den = sum(u[i] * u[i] for i in range(len(v)))
        proy = [proy[i] + num * u[i] / den for i in range(len(v))]
    comp = [v[i] - proy[i] for i in range(len(v))]
    d2 = sum(c * c for c in comp)
    trace.regla("espacios.proyeccion", "pr = Σ(v·uᵢ)/(uᵢ·uᵢ)·uᵢ con base ortogonal",
                why="Gram-Schmidt dentro: con base ortogonal cada coeficiente va solo")
    for u in orto:
        if sum(comp[i] * u[i] for i in range(len(v))) != 0:
            raise _error("INTERNAL", "el resto no es ortogonal al subespacio")
    if [proy[i] + comp[i] for i in range(len(v))] != v:
        raise _error("INTERNAL", "pr + resto ≠ v")
    trace.verificacion("espacios.proy_orto", "resto ⊥ cada uᵢ y pr + resto = v")
    return proy, comp, d2


def complemento_ortogonal(H, trace: Trace | None = None) -> list[list[Fraction]]:
    """H⊥ como núcleo de la matriz por filas, con dims que suman el ambiente."""
    from academic_core.domain.engineering.mathlab import lineal as L

    trace = trace if trace is not None else Trace()
    H = _fracs(H)
    n = len(H[0])
    base = [[Fraction(x) for x in u] for u in L.nucleo(_a_matriz(H), _K(), trace)]
    if len(base) + rango_de(H) != n:
        raise _error("INTERNAL", "dim H + dim H⊥ ≠ ambiente")
    for u in base:
        for h in H:
            if sum(u[i] * h[i] for i in range(n)) != 0:
                raise _error("INTERNAL", "H⊥ no es ortogonal a H")
    trace.regla("espacios.ortogonal", f"dim H⊥ = {len(base)}",
                why="x ⊥ cada generador: sistema homogéneo exacto")
    trace.verificacion("espacios.orto_sub", "ortogonalidad y dimensiones comprobadas")
    return base


def distancia(v, H, trace: Trace | None = None):
    """Resto ortogonal y distancia al cuadrado a ⟨H⟩."""
    trace = trace if trace is not None else Trace()
    _, comp, d2 = proyeccion(v, H, trace)
    trace.regla("espacios.distancia", f"d² = {d2}",
                why="la distancia al subespacio es la norma del resto ortogonal")
    return comp, d2


def invariante(M, F, trace: Trace | None = None) -> bool:
    """f(F) ⊆ F: cada imagen de la base sigue en F (False vale como respuesta)."""
    trace = trace if trace is not None else Trace()
    M = _fracs(M)
    n = len(M)
    if any(len(f) != n for f in M):
        raise _error("BAD_INPUT", "el endomorfismo es n×n y F vive en ℚⁿ")
    if isinstance(F, dict):
        if "generadores" in F:
            base, _ = base_de(F["generadores"], trace)
        elif "ecuaciones" in F:
            base = ecuaciones_a_generadores(F["ecuaciones"], F["vars"], trace)
        else:
            raise _error("BAD_INPUT", "subespacio como {'generadores': ...} o "
                                     "{'ecuaciones': ..., 'vars': ...}")
    else:
        base, _ = base_de(F, trace)
    for b in base:
        fb = [sum(M[i][j] * b[j] for j in range(n)) for i in range(n)]
        if _coordenadas_crudas(fb, base) is None:
            trace.regla("espacios.invariante", f"f({b}) = {fb} se sale de F",
                        why="un vector de la base sale: F no es invariante")
            return False
    trace.regla("espacios.invariante", "toda imagen de la base sigue en F",
                why="basta comprobar la base por linealidad")
    trace.verificacion("espacios.inv_sub", "pertenencia sustituida vector a vector")
    return True


def discusion_parametro(matriz, parametro: str, trace: Trace | None = None):
    """Rango de una cuadrada con UN parámetro afín: det interpolado y sus ceros.

    det(p) es polinomio (grado ≤ n) y se interpola exacto con n+1 valores;
    donde no se anula el rango es n; en cada cero racional se calcula aparte.
    Más de un parámetro o entradas no polinómicas, con su motivo.
    """
    from academic_core.domain.engineering.mathlab import calculo_extra as CX
    from academic_core.domain.engineering.mathlab import lineal as L
    from academic_core.domain.engineering.mathlab import raices as RZ

    trace = trace if trace is not None else Trace()
    n = len(matriz)
    if n == 0 or any(len(f) != n for f in matriz):
        raise _error("BAD_INPUT", "matriz cuadrada no vacía")
    nombres = {parametro}
    polys = []
    for fila in matriz:
        prow = []
        for e in fila:
            expr = mx.parse(str(e), nombres=nombres)
            if mx.variables(expr) - nombres:
                raise _no("más de un parámetro: la discusión es uniparamétrica")
            p = RZ._polinomio_de(expr, parametro)
            if p is None:
                raise _no(f"«{e}» no es polinómica en {parametro}")
            prow.append(p)
        polys.append(prow)
    grado = max((len(RZ._recorta(p)) - 1 for fila in polys for p in fila), default=0)
    if grado > 1:
        trace.aviso("espacios.grado", f"entradas de grado {grado}: el determinante puede "
                                      f"llegar a grado {n * grado}")
    dmax = n * max(grado, 1)

    def det_en(t: Fraction) -> Fraction:
        M = [[sum(c * t ** k for k, c in enumerate(p)) for p in fila] for fila in polys]
        return L.determinante(_a_matriz(M), _K())

    puntos = [(Fraction(t), det_en(Fraction(t))) for t in range(dmax + 1)]
    det_poli = CX.lagrange([(float(x), float(y)) for x, y in puntos])
    for t in (dmax + 1, dmax + 2):
        if abs(float(mx.valor_real(det_poli, {"x": float(t)})) - float(det_en(Fraction(t)))) \
                > 1e-9 * max(1.0, abs(float(det_en(Fraction(t))))):
            raise _no("el determinante no es el polinomio interpolado: grado mayor "
                      "del previsto")
    trace.regla("espacios.det_param", f"det = {mx.text(det_poli)}",
                why=f"polinomio de grado ≤ {dmax}: {dmax + 1} valores lo fijan")
    coefs = RZ._polinomio_de(det_poli, "x")
    if coefs is None or all(c == 0 for c in RZ._recorta(coefs) or [Fraction(0)]):
        raise _no("determinante idénticamente nulo: el rango se discute por menores "
                  "(no implementado)")
    raices = RZ.raices_polinomio(coefs).raices
    ceros = []
    for r in raices:
        q = mx.exact_value(r.valor) if r.exacta else None
        if q is None:
            raise _no("cero no racional del determinante: el caso no se decide exacto")
        ceros.append(Fraction(q))
    casos = []
    if ceros:
        cond = " y ".join(f"{parametro} ≠ {c}" for c in sorted(ceros))
        casos.append((cond, n))
        for c in sorted(ceros):
            M = [[sum(cf * c ** k for k, cf in enumerate(p)) for p in fila] for fila in polys]
            casos.append((f"{parametro} = {c}", rango_de(M)))
            trace.regla("espacios.caso_param", f"{parametro} = {c}: rango {casos[-1][1]}",
                        why="sustitución exacta y rango por Gauss")
    else:
        casos.append((f"para todo {parametro}", n))
    trace.verificacion("espacios.det_ceros", "ceros del determinante sustituidos aparte")
    return casos


def valores_singulares(A, trace: Trace | None = None) -> list[mx.Expr]:
    """σᵢ = √λᵢ de AᵀA exactos (2×2 siempre; 3×3 con espectro racional)."""
    from academic_core.domain.engineering.mathlab import algebra as AL
    from academic_core.domain.engineering.mathlab import limite as LM

    trace = trace if trace is not None else Trace()
    A = _fracs(A)
    m, n = len(A), len(A[0])
    AtA = [[sum(A[k][i] * A[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    vals = AL.autovalores(AtA, trace)
    if any(isinstance(v, tuple) for v in vals):
        raise _error("INTERNAL", "AᵀA simétrica con espectro complejo")
    sigmas = []
    for v in vals:
        if isinstance(v, Fraction):
            if v < 0:
                raise _error("INTERNAL", "autovalor negativo en AᵀA")
            rn, rd = math.isqrt(v.numerator), math.isqrt(v.denominator)
            s = mx.Num(Fraction(rn, rd)) if rn * rn == v.numerator and \
                rd * rd == v.denominator else mx.Root(2, mx.Num(v))
        else:
            s = mx.Root(2, v)
        sigmas.append(LM._limpio(s))
    sigmas.sort(key=lambda s: float(mx.valor_real(s, {})), reverse=True)
    trace.regla("espacios.singulares", f"σ = {', '.join(mx.text(s) for s in sigmas)}",
                why="AᵀA simétrica semidefinida: σᵢ = √λᵢ ≥ 0")
    for s, v in zip(sigmas, sorted(vals, key=lambda z: float(mx.valor_real(
            z if not isinstance(z, Fraction) else mx.Num(z), {})), reverse=True)):
        if abs(float(mx.valor_real(s, {})) ** 2 - float(mx.valor_real(
                v if not isinstance(v, Fraction) else mx.Num(v), {}))) > 1e-9:
            raise _error("INTERNAL", "σ² ≠ λ")
    trace.verificacion("espacios.sigma2", "σᵢ² = λᵢ comprobado")
    return sigmas
