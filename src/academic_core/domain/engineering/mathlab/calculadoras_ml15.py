# SPDX-License-Identifier: MIT
"""ML-15: las calculadoras de fasores y polarización (§8.2 S).

Operación ``polarizacion`` (contrato §5.9) con ``calculo``:

fasor, inverso, onda_plana, medios, polarizacion, jones, diseno, plf,
fresnel, multicapa, antirreflejante.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import polarizacion as P
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


def _cplx(v) -> complex:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return complex(float(v[0]), float(v[1]))
    return complex(v)


@_con_discrepancia
def _polarizacion(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "polarizacion")
    calculo = str(e.get("calculo", "fasor"))
    trace = Trace()
    conv = peticion.convenciones
    ref = "sen" if conv.get("signo_exponencial") == "e^{-iwt}" else "cos"
    signo = "-" if conv.get("signo_exponencial") == "e^{-iwt}" else "+"
    pico = conv.get("valor_efectivo", "pico")
    if pico not in ("", "pico", "V_ef"):
        raise C.error("BAD_CONVENTION", "valor_efectivo pico o V_ef")

    if calculo == "fasor":
        pares = [(a, f) for a, f in e.get("suma", [])]
        if not pares:
            raise C.error("BAD_INPUT", "fasor sin suma [[A, fase], …]")
        r = P.suma_fasores(pares, trace)
        w = e.get("omega")
        texto = f"A = {r['A']:.6g}, φ = {r['phi']:.6g} rad"
        if r["exacto"] is not None:
            re_e, im_e = (str(v) for v in r["exacto"])
            texto += f" (rectangular exacto {re_e}{'+' if not im_e.startswith('-') else ''}{im_e}j)"
        g = None
        if w is not None:
            ww = P._angulo(w)[1]
            xs = [i / 40 for i in range(81)]
            ys = [r["A"] * math.cos(ww * t + r["phi"]) for t in xs]
            g = _grafica([_serie("x(t)", xs, ys)], "t", "x",
                         "senoidal suma reconstruida en el tiempo")
        return _ok(peticion, trace, texto, "suma de fasores",
                   f"A = {r['A']:.6g}; φ = {r['phi']:.6g}", grafica=g)
    if calculo == "inverso":
        r = P.problema_inverso(e.get("omega", "2*pi"), e.get("muestras", []),
                               e.get("conocido", 8), trace)
        return _ok(peticion, trace,
                   f"A = {r['A']:.6g}, φ₁ = {r['phi']:.6g} rad",
                   "problema inverso", f"P = {r['P']:.6g}; Q = {r['Q']:.6g}")
    if calculo == "convenciones_fasor":
        A, phi, w = (float(e.get("A", 5)), P._angulo(e.get("fase", "pi/4"))[1],
                     P._angulo(e.get("omega", "2*pi"))[1])
        ts = [0.0, 0.1, 0.37]
        trace.metodo("sen.fasor_convenciones",
                     "se calcula x(t) con la convención declarada y con la "
                     "contraria (fase con el signo cambiado): la onda física "
                     "coincide muestra a muestra",
                     why="la convención cambia la escritura, no la onda (§5.11)")
        for t in ts:
            a = P.senal_tiempo(A, phi, w, t, "cos", "+")
            b = P.senal_tiempo(A, -phi, w, t, "cos", "-")
            if abs(a - b) > 1e-12 * max(1.0, abs(a)):
                raise C.error("DISCREPANT", f"las convenciones difieren en t = {t}")
        trace.verificacion("sen.fasor_convenciones_ok",
                           f"x(t) idéntica con e^+ y con e^− (A = {A:.6g})")
        return _ok(peticion, trace, f"x(t) con {ref}/e^{signo}: A = {A:.6g}",
                   "fasor con convención declarada", f"ref = {ref}, signo = {signo}")
    if calculo == "onda_plana":
        sen = e.get("sensor")
        r = P.onda_plana(e.get("E0", [1, 0]), e.get("n", 1), e.get("f", "3e8"),
                         e.get("direccion", [0, 0, 1]), sen,
                         "pico" if pico in ("", "pico") else "V_ef", trace)
        texto = (f"k = {r['k']:.6g} rad/m; λ = {r['lambda']:.6g} m; "
                 f"η = {r['eta']:.6g} Ω; ⟨S⟩ = {r['S']:.6g} W/m²")
        if r["P"] is not None:
            texto += f"; P = {r['P']:.6g} W en {r['area']:.6g} m²"
        return _ok(peticion, trace, texto, "onda plana",
                   f"⟨S⟩ = |E|²/2η = {r['S']:.6g} W/m²", avisos=r["avisos"])
    if calculo == "medios":
        r = P.medios(e.get("eps_r", 4), e.get("mu_r", 1), e.get("f", "1e9"),
                     e.get("tand"), e.get("sigma"), trace)
        n = r["n_tilde"]
        texto = (f"ñ = {C.texto_complejo(n)}; α = {r['alfa']:.6g} Np/m; "
                 f"β = {r['beta']:.6g} rad/m")
        if r["aprox"] is not None:
            a = r["aprox"]
            texto += (f"; {a['cual']}: α ≈ {a['alfa']:.6g} "
                      f"(error {r['error_rel']:.3g}; {r['condicion']})")
        if e.get("X_dB") is not None:
            d = P.espesor_para_dB(r["alfa"], e["X_dB"])
            texto += f"; d({e['X_dB']} dB) = {d:.6g} m"
        npts = 60
        prof = [i * 3 / (r["beta"] or 1) / npts for i in range(npts + 1)]
        env = [math.exp(-r["alfa"] * z) for z in prof]
        g = _grafica([_serie("e^{−αz}", prof, env)], "z (m)", "envolvente",
                     "atenuación frente a la profundidad")
        return _ok(peticion, trace, texto, "medio con pérdidas",
                   f"α, β exactos frente a aproximados", grafica=g)
    if calculo == "polarizacion":
        r = P.clasifica(e.get("Ax", 1), e.get("Ay", 0), e.get("delta", 0), trace)
        s1, s2 = r["semiejes"]
        npts, xs, ys = 160, [], []
        Ax = float(e.get("Ax", 1))
        Ay = float(e.get("Ay", 0))
        d = P._normaliza_delta(P._angulo(e.get("delta", 0))[1])
        for i in range(npts + 1):
            t = 2 * math.pi * i / npts
            xs.append(Ax * math.cos(t))
            ys.append(Ay * math.cos(t - d))
        g = _grafica([_serie("elipse", xs, ys)], "Ex", "Ey",
                     f"elipse de polarización: {r['tipo']}")
        psi_txt = "—" if r["psi"] is None else f"{r['psi'] * 180 / math.pi:.3g}°"
        return _ok(peticion, trace,
                   f"{r['tipo']}; AR = {'∞' if r['AR'] == float('inf') else f"{r['AR']:.6g}"}; ψ = {psi_txt}; mano {r['mano']}",
                   "polarización por SVD", f"AR por SVD y por tanχ; Stokes {r['stokes'][0]:.4g}",
                   grafica=g)
    if calculo == "jones":
        els = []
        for q in e.get("elementos", []):
            t = q.get("tipo", "retardador")
            if t == "retardador":
                els.append(P.retardador(q.get("delta", "pi/2"), q.get("phi", 0), Trace()))
            elif t == "polarizador":
                els.append(P.polarizador(q.get("theta", 0)))
            else:
                raise C.error("BAD_INPUT", f"elemento Jones desconocido: {t}")
        ent_raw = e.get("entrada", [1, 0])
        if not isinstance(ent_raw, (list, tuple)) or len(ent_raw) != 2:
            raise C.error("BAD_INPUT", "entrada Jones [Ex, Ey]")
        ent = (_cplx(ent_raw[0]), _cplx(ent_raw[1]))
        r = P.cascada(els, ent, trace)
        s = r["salida"]
        return _ok(peticion, trace,
                   f"E = ({C.texto_complejo(s[0])}, "
                   f"{C.texto_complejo(s[1])}); |E|² = {r['pot_out']:.6g}",
                   "cascada de Jones", f"|E|²: {r['pot_in']:.6g} → {r['pot_out']:.6g}")
    if calculo == "diseno":
        r = P.disenar_cadena(e.get("AR", "3.73"), e.get("psi", "pi/4"), trace)
        return _ok(peticion, trace,
                   f"φ₁ = {r['phi1'] * 180 / math.pi:.3g}°, "
                   f"φ₂ = {r['phi2'] * 180 / math.pi:.3g}°; AR = {r['AR']:.5g}",
                   "diseño λ/4 + λ/2", f"AR = {r['AR']:.5g}")
    if calculo == "plf":
        v = P.plf(e.get("e1", [1, 0]), e.get("e2", [1, 0]), trace)
        return _ok(peticion, trace, f"PLF = {v:.6g}", "desajuste de polarización",
                   f"PLF = |ê₁·ê₂*|² = {v:.6g}")
    if calculo == "fresnel":
        n1, n2, ti, pol = (e.get("n1", 1), e.get("n2", "1.5"),
                           e.get("theta_i", 0), e.get("pol", "s"))
        r = P.fresnel(n1, n2, ti, pol, trace)
        ang = P.angulos(n1, n2)
        txt_c = "—" if ang["critico"] is None else f"{ang['critico'] * 180 / math.pi:.4g}°"
        texto = (f"r = {C.texto_complejo(r['r'])}; R = {r['R']:.6g}; "
                 f"T = {r['T']:.6g}; θ_B = {ang['brewster'] * 180 / math.pi:.4g}°; "
                 f"θ_c = {txt_c}")
        npts = 90
        xs = [i * math.pi / 2 / npts for i in range(npts + 1)]
        Rs = [P.fresnel(n1, n2, x, pol, Trace())["R"] for x in xs]
        series = [_serie(f"R_{pol}(θ)", [x * 180 / math.pi for x in xs], Rs)]
        g = _grafica(series, "θi (°)", "R", "reflectancia con Brewster y ángulo crítico")
        return _ok(peticion, trace, texto, "Fresnel",
                   f"R + T = 1; rama Im(cosθt) ≥ 0", grafica=g)
    if calculo == "multicapa":
        r = P.multicapa(e.get("ns", [1, "1.5", 1]), e.get("ds", ["0.1"]),
                        e.get("lambda0", 1), e.get("theta0", 0),
                        e.get("pol", "s"), trace)
        return _ok(peticion, trace,
                   f"R = {r['R']:.6g}; T = {r['T']:.6g}",
                   "multicapa", f"det = 1 por capa; R + T = 1")
    if calculo == "antirreflejante":
        r = P.antirreflejante(e.get("n1", 1), e.get("n2", "2.25"), trace)
        return _ok(peticion, trace,
                   f"n_f = {r['n_f']:.6g}; d = {r['d_sobre_lambda']:.6g}·λ₀",
                   "antirreflejante λ/4", f"n_f = √(n₁·n₂) = {r['n_f']:.6g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("polarizacion", _polarizacion)
