# SPDX-License-Identifier: MIT
"""ML-14: las calculadoras de señales y sistemas deterministas (§8.2 Q).

Operación ``senales`` (contrato §5.9) con ``calculo``:

biblioteca, eje, convolucion, ventana, conv_digital, regimen, periodica,
periodo, energia, correlacion, densidad, dtft, dft, dft_lineal, eco,
inverso, cascada.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import senales as S
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


def _num(peticion, trace, exacto, metodo, detalle="", aproximado=None, grafica=None,
         avisos=()):
    return _finalizar(peticion, trace, exacto, aproximado=aproximado,
                      sello=V.Seal(V.NUMERIC_ONLY, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


def _serie(nombre, xs, ys) -> C.Serie:
    return C.Serie(nombre, tuple(xs), tuple(ys), ())


def _grafica(series, xl, yl, desc):
    series = tuple(s for s in series if s.ys)
    return C.Graph(series=series, x_label=xl, y_label=yl, description=desc) if series else None


def _lee_senal(d: dict) -> list:
    """Lee {"trozos": [[a,b,v]], "tris": [{t0,T,A}], "exps": [{t0,T,A}],
    "deltas": [{delta,t0}]} como segmentos + deltas."""
    if not isinstance(d, dict):
        raise C.error("BAD_INPUT", "la señal es un diccionario de trozos")
    out: list = []
    for a, b, v in d.get("trozos", []):
        out.append(S.rect(a, b, v))
    for p in d.get("tris", []):
        out.extend(S.tri(p.get("t0", 0), p.get("T", 1), p.get("A", 1)))
    for p in d.get("exps", []):
        out.append(S.exp_causal(p.get("t0", 0), p.get("T", 1), p.get("A", 1)))
    for q in d.get("deltas", []):
        out.append({"delta": q.get("delta", 1), "t0": q.get("t0", 0)})
    if not out:
        raise C.error("BAD_INPUT", "señal vacía: da trozos, tris, exps o deltas")
    return out


def _muestra_analogica(segs, lo: float, hi: float, n=240):
    xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
    return xs, [S._eval_senal([s for s in segs if isinstance(s, S.Segmento)], t) for t in xs]


@_con_discrepancia
def _senales(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "senales")
    calculo = str(e.get("calculo", "biblioteca"))
    trace = Trace()
    conv = peticion.convenciones
    if calculo == "biblioteca":
        r = S.biblioteca(e.get("pulsos", []), trace)
        g = None
        return _ok(peticion, trace,
                   f"E = {r['energia']}, ∫ = {r['integral']}"
                   + (" (solape: energía cruzada)" if r["solapan"] else ""),
                   "biblioteca de pulsos", f"E = {r['energia']}; ∫ = {r['integral']}",
                   grafica=g)
    if calculo == "eje":
        out = S.transforma_eje(e.get("pulso", {}), e.get("a", 1), e.get("b", 0), trace)
        return _ok(peticion, trace, f"t0 = {out['t0']}, T = {out['T']}",
                   "transformación del eje", f"t0 = {out['t0']}; T = {out['T']}")
    if calculo == "convolucion":
        x = _lee_senal(e.get("x", {}))
        h = _lee_senal(e.get("h", {}))
        r = S.convolucion(x, h, trace)
        lineas = [f"[{t['a']}, {'∞)' if t['b'] is None else str(t['b']) + ']'}: {t['expr']}"
                  for t in r["tramos"]]
        texto = "y(t) = " + ("; ".join(lineas) if lineas else f"{r['integral']}·δ(t−{r['desplazamiento_deltas']})")
        texto += f"; ∫y = {r['integral']}"
        xs = [s for s in x if isinstance(s, S.Segmento)]
        lo = min([float(s.a) for s in xs if s.a is not None] or [0.0])
        hi = max([float(s.b) for s in xs if s.b is not None] or [1.0])
        des = float(r["desplazamiento_deltas"])
        _, ys = _muestra_analogica(x, lo - 1, hi + 3)
        g = _grafica([_serie("x(t)", [lo - 1 + (hi - lo + 4) * i / 240 for i in range(241)], ys)],
                     "t", "x", "señal de entrada y convolución por tramos")
        if r["verificado"]:
            return _ok(peticion, trace, texto, "convolución por tramos",
                       f"∫y = ∫x·∫h = {r['integral']}", grafica=g)
        return _num(peticion, trace, texto, "convolución por tramos",
                    f"∫y = ∫x·∫h = {r['integral']} (tramos no constantes: valor numérico)",
                    grafica=g)
    if calculo == "ventana":
        r = S.ventana_movil(_lee_senal(e.get("x", {})), e.get("T", 1), trace)
        lineas = [f"[{t['a']}, {'∞)' if t['b'] is None else str(t['b']) + ']'}: {t['expr']}"
                  for t in r["tramos"]]
        return _ok(peticion, trace, "y(t) = " + "; ".join(lineas) + f"; ∫y = {r['integral']}",
                   "ventana móvil", f"∫y = {r['integral']}")
    if calculo == "conv_digital":
        r = S.conv_lineal(e.get("x", []), e.get("h", []), trace)
        n = len(r["y"])
        g = _grafica([_serie("y[n]", list(range(n)), [float(v) for v in r["y"]])],
                     "n", "y", "convolución digital con sus tres tramos")
        return _ok(peticion, trace, f"y = [{', '.join(str(v) for v in r['y'])}]",
                   "convolución digital", f"Σy = {sum(r['y'])}; N = {n}", grafica=g)
    if calculo == "regimen":
        r = S.salida_exp(e.get("a", "1/2"), e.get("x", []), trace)
        return _ok(peticion, trace, f"y = [{', '.join(str(v) for v in r['y'])}]",
                   "régimen de primer orden", f"y[-1] = {r['y'][-1]}")
    if calculo == "periodica":
        K = int(e.get("K", 5))
        r = S.ck_base(e.get("base", []), e.get("T0", 2), K, trace)
        nul = ", ".join(str(k) for k in r["nulos"]) or "ninguno"
        c0 = r["ck"].get(0, 0j)
        g = _grafica([_serie("|c_k|", list(r["ck"].keys()),
                             [abs(v) for v in r["ck"].values()])],
                     "k", "|c_k|", "espectro de líneas de la periódica")
        return _ok(peticion, trace,
                   f"c_0 = {C.texto_complejo(c0)}; P = {r['potencia']:.6g}; "
                   f"nulos: {nul}",
                   "señal base + TF", f"P = {r['potencia']:.6g} ≤ {r['potencia_tiempo']:.6g}",
                   grafica=g)
    if calculo == "periodo":
        T = S.periodo_comun(e.get("T1", 2), e.get("T2", 3))
        trace.metodo("sen.periodo", "el periodo común es el mcm de los periodos",
                     why="la suma es periódica con el menor múltiplo común (§4.15)")
        return _ok(peticion, trace, f"T = {T}", "mcm de periodos", f"T = {T}")
    if calculo == "energia":
        d = e.get("senal", {})
        segs = [s for s in _lee_senal(d) if isinstance(s, S.Segmento)]
        r = S.energia(segs, trace)
        T0 = e.get("T0")
        if T0 is not None:
            P = Fraction(r["energia"]) / S._Q(T0)
            return _ok(peticion, trace, f"E = {r['energia']}; P = {P}",
                       "energía y potencia", f"P = E/T0 = {P}")
        return _ok(peticion, trace, f"E = {r['energia']}",
                   "energía", f"E = {r['energia']}")
    if calculo == "potencia_sinusoide":
        P = S.potencia_sinusoide(e.get("A", 1), trace)
        return _ok(peticion, trace, f"P = {P}", "potencia de sinusoide", f"P = A²/2 = {P}")
    if calculo == "energia_eco":
        E = S.energia_eco(e.get("Ex", 1), e.get("a", "1/2"), trace)
        return _ok(peticion, trace, f"E_y = {E}", "energía del eco",
                   f"E_y = E_x·(1+a²) = {E}")
    if calculo == "correlacion":
        tipo = str(e.get("tipo", "rect"))
        if tipo == "rect":
            r = S.correlacion_rect(e.get("A", 1), e.get("T", 2),
                                   e.get("taus"))
        elif tipo == "exp":
            r = S.correlacion_exp(e.get("A", 1), e.get("T", 1),
                                  e.get("taus"))
        else:
            raise C.error("BAD_INPUT", "correlación rect o exp")
        trace.metodo("sen.correlacion", "r = x ∗ x*(−t); S = |X|² (Wiener-Khinchin)",
                     why="es la definición determinista de §4.15, fila 6; r(0) = E "
                         "y |r(τ)| ≤ r(0) son el control")
        pico = max(r["r"], key=lambda t: r["r"][t])
        g = _grafica([_serie("r(τ)", sorted(r["r"]), [r["r"][t] for t in sorted(r["r"])])],
                     "τ", "r", "autocorrelación determinista")
        return _ok(peticion, trace,
                   f"r(0) = {r['E']:.6g}; pico en τ = {pico}",
                   "correlación determinista", f"r(0) = E = {r['E']:.6g}", grafica=g)
    if calculo == "densidad":
        Xs = [complex(a[0], a[1]) if isinstance(a, (list, tuple)) else complex(a)
              for a in e.get("X", [])]
        if not Xs:
            raise C.error("BAD_INPUT", "densidad sin espectro X")
        Sq = S.densidad_desde_tf(Xs, trace)
        return _ok(peticion, trace, f"S = [{', '.join(f'{v:.6g}' for v in Sq)}]",
                   "densidad espectral", "S_x = |X|² punto a punto")
    if calculo == "dtft":
        tipo = str(e.get("tipo", "pulso"))
        Fs = [float(v) for v in e.get("F", [0, 0.25])]
        if tipo == "pulso":
            L = int(e.get("L", 4))
            Xs = [S.dtft_pulso(F, L) for F in Fs]
            S.comprobar_dtft(e.get("a", "1/2"), L, trace)
            detalle = f"máximo {L} en F = 0; ceros en k/{L}"
        elif tipo == "exp":
            a_ = S._Q(e.get("a", "1/2"))
            if not abs(float(a_)) < 1:
                raise C.error("BAD_INPUT", "aⁿu[n] solo tiene DTFT con |a| < 1")
            trace.metodo("sen.dtft_exp", "Σ aⁿe^{−j2πFn} es geométrica: 1/(1 − a·e^{−j2πF})",
                         why="con |a| < 1 la serie converge y su suma es cerrada")
            Xs = [S.dtft_exp(F, e.get("a", "1/2")) for F in Fs]
            N = max(1, int(math.ceil(math.log(1e-14) / math.log(abs(float(a_)))))) if a_ else 1
            directa = [sum(float(a_) ** n * cmath.exp(-2j * math.pi * F * n) for n in range(N))
                       for F in Fs]
            if any(abs(x - y) > 1e-9 * max(1.0, abs(y)) for x, y in zip(Xs, directa)):
                raise C.error("DISCREPANT", "la forma cerrada no coincide con la serie")
            trace.verificacion("sen.dtft_exp_serie", f"coincide con la serie sumada hasta n = {N}")
            detalle = f"|H|² = 1/(1+a²−2a·cos2πF)"
        elif tipo == "delta":
            n0 = int(e.get("n0", 0))
            trace.metodo("sen.dtft_delta", "δ[n − n₀] ↦ e^{−j2πFn₀}",
                         why="un retardo de n₀ muestras es una fase lineal en F")
            Xs = [S.dtft_delta(F, n0) for F in Fs]
            if any(abs(X - cmath.exp(-2j * math.pi * F * n0)) > 1e-12 for F, X in zip(Fs, Xs)):
                raise C.error("DISCREPANT", "la DTFT de la delta no es e^{−j2πFn₀}")
            trace.verificacion("sen.dtft_delta_fase", "|X| = 1 y fase −2πFn₀ en cada F")
            detalle = "retardo = fase lineal"
        else:
            raise C.error("BAD_INPUT", "dtft pulso, exp o delta")
        g = _grafica([_serie("|X(F)|", Fs, [abs(X) for X in Xs])],
                     "F", "|X|", "DTFT: módulo en F ∈ [−1, 1]")
        txt = "; ".join(f"F = {F}: {C.texto_complejo(X)}" for F, X in zip(Fs, Xs))
        return _ok(peticion, trace, txt, "DTFT", detalle, grafica=g)
    if calculo == "dft":
        x = [float(v) for v in e.get("x", [])]
        if not x:
            raise C.error("BAD_INPUT", "DFT sin muestras x")
        r = S.comprobar_dft(x, trace)
        X = r["X"]
        g = _grafica([_serie("|X[k]|", list(range(len(X))), [abs(v) for v in X])],
                     "k", "|X|", "DFT con k > N/2 como frecuencia negativa")
        txt = "; ".join(f"X[{k}] = {C.texto_complejo(v)}" for k, v in enumerate(X))
        return _ok(peticion, trace, txt, "DFT",
                   f"X[0] = Σx; Parseval = {r['energia']:.6g}", grafica=g)
    if calculo == "dft_lineal":
        r = S.lineal_vs_circular([float(v) for v in e.get("x", [])],
                                 [float(v) for v in e.get("h", [])], trace)
        return _ok(peticion, trace,
                   f"N = {r['N']}; y = [{', '.join(f'{v:.6g}' for v in r['y'])}]",
                   "circular frente a lineal", f"N = {r['N']} ≥ L1+L2−1")
    if calculo == "eco":
        a, L = e.get("a", "1/2"), int(e.get("L", 4))
        ceros = S.ceros_eco(a, L)
        F = float(e.get("F", 0))
        m = S.modulo_eco(a, L, F)
        trace.metodo("sen.eco_ceros", "L ceros en |z| = |a|^{1/L} por z^L = −a",
                     why="1 + a·z^{−L} = 0 da z^L = −a: módulo y fases (§4.15, fila 9)")
        txt = f"|z| = {abs(ceros[0]):.6g}; |H({F})|² = {m:.6g}"
        g = _grafica([_serie("|H(F)|²", [i / 40 for i in range(41)],
                             [S.modulo_eco(a, L, i / 40) for i in range(41)])],
                     "F", "|H|²", "respuesta del eco en frecuencia")
        return _ok(peticion, trace, txt, "eco", txt, grafica=g)
    if calculo == "inverso":
        h2 = S.inverso_eco(e.get("a", "1/2"), int(e.get("L", 4)), int(e.get("K", 6)))
        trace.metodo("sen.eco_inverso", "h2 = Σ b^k·δ[n−kL] con b = −a",
                     why="la serie geométrica de 1/(1+a·z^{−L}) converge si |b| < 1")
        return _ok(peticion, trace, f"h2 = [{', '.join(str(v) for v in h2)}]",
                   "inverso del eco", f"b = −a; {len(h2)} muestras")
    if calculo == "cascada":
        r = S.cascada_eco(e.get("a", "1/2"), int(e.get("L", 4)),
                          e.get("x", []), int(e.get("K", 12)), trace)
        return _ok(peticion, trace,
                   f"z = [{', '.join(str(v) for v in r['z'])}]; resto = {r['resto']:.3g}",
                   "cascada eco + inverso", f"z = x con resto {r['resto']:.3g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("senales", _senales)
