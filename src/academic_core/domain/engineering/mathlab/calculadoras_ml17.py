# SPDX-License-Identifier: MIT
"""ML-17: discreta, modular, códigos e información (§8.2 J–M).

Operaciones ``discreta`` (bloque 8), ``codigos`` (bloques 9–10) e
``informacion`` (bloque 11). El cifrado clásico (E) y ℤₙ van primero;
GF(2ᵐ) al final (§10). Aviso fijo: material pedagógico, nunca real.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import codigos as K
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import discreta as D
from academic_core.domain.engineering.mathlab import informacion as N
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.calculators import _finalizar, con_discrepancia
from academic_core.domain.engineering.mathlab.trace import Trace


def _dict(peticion: C.Peticion, que: str) -> dict:
    e = peticion.entrada
    if not isinstance(e, dict):
        raise C.error("BAD_INPUT", f"se espera un diccionario para «{que}»")
    return e


def _ok(peticion, trace, exacto, metodo, detalle="", aproximado=None, grafica=None,
        avisos=()):
    return _finalizar(peticion, trace, exacto, aproximado=aproximado,
                      sello=V.Seal(V.VERIFIED, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


def _serie(nombre, xs, ys) -> C.Serie:
    return C.Serie(nombre, tuple(xs), tuple(ys), ())


def _grafica(series, xl, yl, desc):
    series = tuple(s for s in series if s.ys)
    return C.Graph(series=series, x_label=xl, y_label=yl, description=desc) if series else None


@_con_discrepancia
def _discreta(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "discreta")
    calculo = str(e.get("calculo", "logica"))
    trace = Trace()

    if calculo == "logica":
        r = D.tabla_verdad(e.get("formula", "p -> q"), trace)
        n1 = sum(1 for _, v in r["filas"] if v)
        g = _grafica([_serie("V/F", list(range(len(r["filas"]))),
                             [1 if v else 0 for _, v in r["filas"]])],
                     "valoración", "V", "tabla de verdad")
        return _ok(peticion, trace,
                   f"{n1}/{len(r['filas'])} verdaderas en {r['vars']}",
                   "tabla de verdad", f"{n1} de {len(r['filas'])}", grafica=g)
    if calculo == "equivalencia":
        r = D.equivalencia(e.get("f", "p -> q"), e.get("g", "no p o q"), trace)
        return _ok(peticion, trace,
                   "equivalentes" if r["equivalentes"] else "NO equivalentes",
                   "equivalencia por tablas", "")
    if calculo == "cuantificador":
        r = D.negar_cuantificador(e.get("cuant", "forall"), e.get("var", "x"),
                                  e.get("matriz", "P(x)"), trace)
        return _ok(peticion, trace, r["negacion"], "negación de cuantificadores",
                   r["negacion"])
    if calculo == "conjuntos":
        r = D.operacion_conjuntos(e.get("a", []), e.get("b", []),
                                  e.get("op", "union"), trace)
        return _ok(peticion, trace,
                   f"{r['elementos']} (|·| = {r['cardinal']})",
                   "conjuntos por enumeración", f"cardinal {r['cardinal']}")
    if calculo == "potencia":
        r = D.potencia_n(e.get("n", 3), trace)
        return _ok(peticion, trace, f"2^{e.get('n', 3)} = {r['cardinal']}",
                   "conjunto potencia", f"{r['cardinal']} subconjuntos")
    if calculo == "binomio":
        r = D.binomio_termino(e.get("n", 5), e.get("k", 2), trace)
        return _ok(peticion, trace, f"C = {r['C']}", "binomio exacto",
                   f"C = {r['C']}")
    if calculo == "vandermonde":
        r = D.vandermonde(e.get("r", 3), e.get("s", 4), e.get("n", 2), trace)
        return _ok(peticion, trace, f"Σ = {r['suma']}", "Vandermonde sumando",
                   f"Σ = {r['suma']}")
    if calculo == "recurrencia":
        r = D.recurrencia_lineal(e.get("a", 1), e.get("b", 1), e.get("c", 0),
                                 e.get("f0", 0), e.get("f1", 1),
                                 e.get("n", 10), trace)
        txt = f"f = {r['f_n']}"
        if r["raices"] is not None:
            txt += f" (r = {r['raices'][0]:.6g}, {r['raices'][1]:.6g})"
        return _ok(peticion, trace, txt, "recurrencia lineal",
                   f"f = {r['f_n']}")
    if calculo == "maestro":
        r = D.teorema_maestro(e.get("a", 2), e.get("b", 2), e.get("f", "n"),
                              trace)
        return _ok(peticion, trace, r["caso"], "teorema maestro", r["caso"])
    if calculo == "ruina":
        r = D.ruina(e.get("p", "1/2"), e.get("N", 10), trace)
        return _ok(peticion, trace,
                   f"p = {[f'{float(v):.6g}' for v in r['p_k']]}",
                   "ruina del jugador", "recurrencia comprobada")
    if calculo == "sumatorio":
        kw = {k: v for k, v in e.items() if k in ("a1", "d", "r")}
        r = D.cerrar_sumatorio(e.get("tipo", "aritmetica"), e.get("n", 10),
                               trace, **kw)
        return _ok(peticion, trace, f"Σ = {r['suma']} ({r['dominante']})",
                   "sumatorio cerrado", f"Σ = {r['suma']}")
    if calculo == "mochila":
        r = D.mochila(e.get("pesos", []), e.get("valores", []),
                      e.get("cap", 0), trace)
        return _ok(peticion, trace, f"óptimo = {r['optimo']}",
                   "mochila por PD", f"PD = fuerza bruta = {r['optimo']}")
    if calculo == "cambio":
        r = D.cambio_monedas(e.get("cantidad", 0), e.get("sistema", [1]),
                             trace)
        vero = "óptimo" if len(r["voraz"]) == r["optimo_pd"] else "NO óptimo"
        return _ok(peticion, trace,
                   f"voraz {len(r['voraz'])} vs PD {r['optimo_pd']}: {vero}",
                   "cambio voraz frente a PD", vero)
    if calculo == "tiempo_real":
        r = D.tiempo_real(e.get("tareas", []), trace)
        return _ok(peticion, trace,
                   f"U = {r['U']:.4g}; planificable: {r['planificable']}",
                   "tiempo real", f"RTA = {r['rta']}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


@_con_discrepancia
def _codigos(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "codigos")
    calculo = str(e.get("calculo", "cesar"))
    trace = Trace()

    if calculo == "cesar":
        r = K.cesar(e.get("texto", "HOLA"), e.get("k", 3), trace)
        return _ok(peticion, trace, r["cifrado"], "César",
                   f"k = {r['k']}; descifrar(cifrar(x)) = x")
    if calculo == "afin":
        r = K.afin(e.get("texto", "HOLA"), e.get("a", 5), e.get("b", 8),
                   trace)
        return _ok(peticion, trace, r["cifrado"], "afín",
                   f"a⁻¹ = {r['a_inv']}")
    if calculo == "vigenere":
        r = K.vigenere(e.get("texto", "HOLA"), e.get("clave", "CLAVE"), trace)
        return _ok(peticion, trace, r["cifrado"], "Vigenère",
                   "clave repetida; ida y vuelta")
    if calculo == "hill":
        r = K.hill(e.get("texto", "HOLA"), e.get("matriz", [[3, 3], [2, 5]]),
                   trace)
        return _ok(peticion, trace, r["cifrado"], "Hill",
                   "A·A⁻¹ = I (mod 26)")
    if calculo == "tabla_zn":
        r = K.tabla_zn(e.get("n", 5), trace)
        return _ok(peticion, trace,
                   f"ℤ_{e.get('n', 5)} {'cuerpo' if r['cuerpo'] else 'no cuerpo'}",
                   "tablas de ℤₙ", "")
    if calculo == "hash":
        r = K.hash_cumple(e.get("m", 365), e.get("claves", list(range(23))),
                          trace)
        return _ok(peticion, trace,
                   f"colisiones = {r['colisiones']}; P = {r['P']:.4g}",
                   "hash y cumpleaños", f"Monte Carlo {r['montecarlo']:.4g}")
    if calculo == "gf2m":
        r = K.gf2m_tabla(e.get("m", 3), e.get("poli"), trace)
        return _ok(peticion, trace,
                   f"orden {r['orden']}" +
                   (" (primitivo)" if r["primitivo"] else ""),
                   "tabla de GF(2ᵐ)", f"u·u⁻¹ = 1 comprobado")
    if calculo == "poli_gfp":
        r = K.poli_gfp(e.get("coefs", [1, 1, 1]), e.get("p", 2), trace)
        return _ok(peticion, trace,
                   "irreducible" if r["irreducible"] else "reducible",
                   "Rabin sobre GF(p)", "")
    if calculo == "codigo":
        r = K.codigo_lineal(e.get("G", [[1, 0, 0, 1, 1, 0, 1]]), trace)
        return _ok(peticion, trace,
                   f"[{r['n']},{r['k']},{r['d']}] detecta {r['detecta']} "
                   f"corrige {r['corrige']}",
                   "código lineal", f"G·Hᵀ = 0; {2 ** r['k']} palabras")
    if calculo == "sindrome":
        r = K.sindrome(e.get("H", []), e.get("r", []), trace)
        if r["corrige"] is None:
            return _ok(peticion, trace, "s = 0: sin errores",
                       "síndrome", "s = 0")
        return _ok(peticion, trace, f"bit {r['corrige']} invertido",
                   "síndrome", f"s = {r['sindrome']}")
    if calculo == "crc":
        r = K.crc(e.get("mensaje", [1, 1, 0, 1]), e.get("generador", [1, 0, 1, 1]),
                  trace)
        return _ok(peticion, trace, f"CRC = {r['crc']}; trama con resto 0",
                   "CRC por división", f"CRC = {r['crc']}")
    if calculo == "paridad":
        r = K.paridad(e.get("bits", [1, 0, 1]), trace)
        return _ok(peticion, trace, f"palabra {r['palabra']}",
                   "bit de paridad", "")
    if calculo == "checksum":
        r = K.checksum16(e.get("palabras", [0x4500]), trace)
        return _ok(peticion, trace, f"checksum = {r['checksum']:#06x}",
                   "checksum Internet", "")
    if calculo == "shamir_reparto":
        r = K.shamir_reparto(e.get("t", 2), e.get("n", 3), e.get("p", 11),
                             e.get("secreto", 5), int(e.get("semilla", 7)),
                             trace)
        return _ok(peticion, trace, f"partes = {r['partes']}",
                   "Shamir reparte", f"grado {e.get('t', 2) - 1}",
                   avisos=(K.AVISO_PEDAGOGICO,))
    if calculo == "shamir_reconstruye":
        r = K.shamir_reconstruye(e.get("partes", []), e.get("p", 11),
                                 e.get("t", 2), trace)
        return _ok(peticion, trace, f"secreto = {r['secreto']}",
                   "Shamir reconstruye", f"secreto = {r['secreto']}",
                   avisos=(K.AVISO_PEDAGOGICO,))
    if calculo == "rsa":
        r = K.rsa(e.get("p", 61), e.get("q", 53), e.get("e", 17),
                  e.get("m", 65), trace)
        return _ok(peticion, trace, f"c = {r['c']}; m = {r['m2']}",
                   "RSA pedagógico", f"d = {r['d']}",
                   avisos=(r["aviso"],))
    if calculo == "dh":
        r = K.diffie_hellman(e.get("p", 23), e.get("g", 5), e.get("a", 6),
                             e.get("b", 15), trace)
        return _ok(peticion, trace, f"secreto = {r['s']}",
                   "Diffie-Hellman", f"A = {r['A']}, B = {r['B']}",
                   avisos=(r["aviso"],))
    if calculo == "k_anonimato":
        r = K.k_anonimato(e.get("registros", []), e.get("quasis", []), trace)
        return _ok(peticion, trace, f"k = {r['k']} ({r['clases']} clases)",
                   "k-anonimato", f"k = {r['k']}",
                   avisos=(K.AVISO_PEDAGOGICO,))
    if calculo == "dp":
        r = K.dp_laplace(e.get("datos", [1, 2, 3]), e.get("sensibilidad", 1),
                         e.get("epsilon", 1), int(e.get("semilla", 1)), trace)
        return _ok(peticion, trace, f"b = {r['b']:.4g}",
                   "privacidad diferencial", f"error esperado {r['b']:.4g}",
                   avisos=(r["aviso"],))
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


@_con_discrepancia
def _informacion(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "informacion")
    calculo = str(e.get("calculo", "entropia"))
    trace = Trace()

    if calculo == "entropia":
        r = N.entropia(e.get("probs", ["1/2", "1/2"]), trace)
        ps = e.get("probs", ["1/2", "1/2"])
        g = _grafica([_serie("p", list(range(len(ps))),
                             [float(Fraction(str(v))) for v in ps])],
                     "símbolo", "p", "distribución de la fuente")
        return _ok(peticion, trace, f"H = {r['H']:.6g} bits",
                   "entropía", f"H = {r['H']:.6g} bits", grafica=g)
    if calculo == "conjunta":
        r = N.conjunta(e.get("tabla", [["1/2", "0"], ["0", "1/2"]]), trace)
        return _ok(peticion, trace,
                   f"H(X,Y) = {r['Hxy']:.6g}; I = {r['I']:.6g} bits",
                   "entropía conjunta", f"I ≥ 0 y cadena comprobadas")
    if calculo == "divergencia":
        r = N.divergencia(e.get("p", ["1/2", "1/2"]),
                          e.get("q", ["1/4", "3/4"]), trace)
        return _ok(peticion, trace, f"D = {r['D']:.6g} bits",
                   "divergencia KL", f"H(p,q) = {r['H_cruz']:.6g}")
    if calculo == "kraft":
        r = N.kraft(e.get("longitudes", [2, 2, 2, 2]), trace)
        return _ok(peticion, trace,
                   f"K = Σ2^(−lᵢ) = {r['K']}: "
                   + ("hay código prefijo" + (" (completo)" if r["K"] == 1 else "")
                      if r["prefijo_posible"] else "NO hay código prefijo (K > 1)"),
                   "desigualdad de Kraft", f"K = {float(r['K']):.6g}")
    if calculo == "capacidad":
        r = N.capacidad(e.get("tipo", "BSC"), e.get("param", "0.1"), trace)
        return _ok(peticion, trace, f"C = {r['C']:.6g}",
                   "capacidad de canal", f"C = {r['C']:.6g}")
    if calculo == "huffman_check":
        from academic_core.domain.engineering.mathlab import grafos as G

        probs = e.get("probs", {"a": "1/2", "b": "1/4", "c": "1/4"})
        h = G.huffman(probs, trace)
        H = N.entropia(list(probs.values()), Trace())["H"]
        L = float(h.longitud_media)
        det = f"H = {H:.6g}; L̄ = {L:.6g}"
        if not H - 1e-9 <= L < H + 1 + 1e-9:
            raise C.error("DISCREPANT", "H ≤ L̄ < H+1 falla")
        return _ok(peticion, trace, det, "Huffman frente a entropía", det)
    if calculo == "clave":
        r = N.coste_clave(e.get("bits", 128), e.get("tasa", "1e9"), trace)
        return _ok(peticion, trace,
                   f"2^{e.get('bits', 128)} claves; ~{r['tiempo_medio_s']:.3g} s",
                   "coste en bits", f"cumpleaños 2^{r['cumpleanos_bits']}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("discreta", _discreta)
C.registrar("codigos", _codigos)
C.registrar("informacion", _informacion)
