# SPDX-License-Identifier: MIT
"""ML-16: las calculadoras de campos y ondas (§8.2 T).

Operación ``campos`` (contrato §5.9) con ``calculo``:

carga, gauss, conductores, v_dado, maxwell, guia, completar, perfil,
coulomb, biot_savart, condensador, faraday, poynting, friis, ruido, array.
"""

from __future__ import annotations

import math

from academic_core.domain.engineering.mathlab import campos as F
from academic_core.domain.engineering.mathlab import contract as C
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


@_con_discrepancia
def _campos(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "campos")
    calculo = str(e.get("calculo", "carga"))
    trace = Trace()

    if calculo == "carga":
        tipo = str(e.get("tipo", "arco"))
        if tipo == "arco":
            r = F.carga_arco(e.get("a", 1), e.get("R", 1),
                             e.get("t1", 0), e.get("t2"),
                             e.get("m", 2), e.get("densidad", "seno"), trace)
            txt = f"Q = {r['Q']:.6g} C; E(O) = ({r['Ex']:.4g}, {r['Ey']:.4g}) V/m; V(O) = {r['V0']:.6g} V"
            return _ok(peticion, trace, txt, "carga del arco",
                       f"Q = {r['Q']:.6g} C por primitiva y cuadratura")
        elif tipo == "cilindro":
            r = F.carga_cilindro(e.get("a", 1), e.get("R1", 0),
                                 e.get("R2", 1), e.get("L", 1), trace)
        elif tipo == "esfera":
            r = F.carga_esfera(e.get("a", 1), e.get("R", 1),
                               e.get("n", 2), trace)
        elif tipo == "placa":
            r = F.carga_placa(e.get("a", 1), e.get("x0", 0), e.get("x1", 1),
                              e.get("y0", 0), e.get("y1", 1), trace)
        elif tipo == "segmento":
            r = F.segmento(e.get("Q", "1e-9"), e.get("L", 1),
                           e.get("d", 1), trace)
            return _ok(peticion, trace, f"E = {r['E']:.6g} V/m",
                       "hilo finito en la mediatriz",
                       f"E = {r['E']:.6g} V/m (→ hilo infinito si L ≫ d)")
        else:
            raise C.error("BAD_INPUT", "carga arco, cilindro, esfera, placa o segmento")
        return _ok(peticion, trace, f"Q = {r['Q']:.6g} C",
                   "carga con densidad no uniforme", f"Q = {r['Q']:.6g} C")
    if calculo == "gauss":
        tipo = str(e.get("tipo", "esfera"))
        if tipo == "esfera":
            r = F.gauss_esfera(e.get("Q", "1e-9"), e.get("R", "0.1"), trace)
            Rs = [r["W"]]
            g = None
            return _ok(peticion, trace,
                       f"E fuera = {r['E']['fuera']}; V(R) = {r['V']['dentro']}; "
                       f"W = {r['W']:.6g} J",
                       "Gauss esférico", f"W por ½ΣQV y por (ε₀/2)∫E²", grafica=g)
        if tipo == "rho":
            r = F.gauss_esfera_rho(e.get("a", 1), e.get("R", 1),
                                   e.get("n", 1), trace)
            return _ok(peticion, trace,
                       f"Q = {r['Q']:.6g} C; E dentro ∝ {r['E_in']}",
                       "Gauss con ρ = a·rⁿ", f"∇·E = ρ/ε₀ comprobado")
        if tipo == "cilindro":
            r = F.gauss_cilindro(e.get("lambda", "1e-9"),
                                 e.get("r0", 1), trace)
            return _ok(peticion, trace, f"E = {r['E']}; V: {r['V']}",
                       "Gauss cilíndrico", "referencia en r₀ (V(∞) = 0 no vale)",
                       avisos=("V(∞) = 0 no vale en el cilindro infinito",))
        if tipo == "plano":
            r = F.gauss_plano(e.get("sigma", "1e-9"), trace)
            return _ok(peticion, trace, f"E = ±{r['E_mas']:.6g} V/m",
                       "Gauss plano", f"E = σ/2ε₀ a cada lado")
        raise C.error("BAD_INPUT", "gauss esfera, rho, cilindro o plano")
    if calculo == "conductores":
        t = e.get("tierra", False)
        tierra = t if isinstance(t, str) else bool(t)
        r = F.esferas_concentricas(e.get("R1", 1), e.get("R2", 2),
                                   e.get("R3", 3), e.get("Q1", 0),
                                   e.get("Q2", 0), tierra, trace)
        return _ok(peticion, trace,
                   f"inducidas: {r['q_interior_cascara']} en R₂, "
                   f"{r['q_exterior']} en R₃; V(R₁) = {r['V_R1']:.6g} V",
                   "conductores concéntricos",
                   f"V(R₃) = {r['V_R3']:.6g} V")
    if calculo == "v_dado":
        r = F.v_dado(e.get("V", "x^2+y^2+4"), e.get("caja", [0, 1, 0, 1, 0, 1]),
                     trace)
        return _ok(peticion, trace, f"q = {r['carga']} (∭ρ y ε₀∯E·dS)",
                   "V dado", f"q = {r['carga']} por los dos lados de Gauss")
    if calculo == "maxwell":
        r = F.maxwell_plana(e.get("E0", 3), e.get("B0", "1e-8"),
                            e.get("k", 1), e.get("omega", "3e8"), trace)
        return _ok(peticion, trace, f"c = ω/k = E₀/B₀ = {r['c']:.6g} m/s",
                   "Maxwell por sustitución", f"c = {r['c']:.6g} m/s")
    if calculo == "guia":
        r = F.maxwell_guia(e.get("E0", 1), e.get("a", "0.1"),
                           e.get("omega", "2e10"), trace)
        return _ok(peticion, trace,
                   f"β = {r['beta']:.6g} rad/m; P = {r['P']:.6g} W/m",
                   "modo guiado TE", f"β² = ω²/c² − (π/a)²; P por Poynting")
    if calculo == "completar":
        r = F.completar_By(e.get("Bx", [[1, 0, 2]]), trace)
        txt = " + ".join(f"{c}·x^{i}y^{j}" for i, j, c in r["By"]) or "0"
        return _ok(peticion, trace, f"By = {txt}", "completar con ∇·B = 0",
                   "función de integración cero (sin campos estáticos)")
    if calculo == "perfil":
        r = F.perfil_onda(e.get("tipo", "gauss"), e.get("E0", 1),
                          e.get("alpha", 2), e.get("beta", 1),
                          e.get("sensores", [0, 5]), trace)
        tr = "; ".join(f"x = {t['x']}: pico en t = {t['t_pico']:.4g} s"
                       for t in r["trazas"])
        npts = 200
        xs = [-4 + 8 * i / npts for i in range(npts + 1)]
        al, be = float(e.get("alpha", 2)), float(e.get("beta", 1))
        fg = (lambda u: math.exp(-u * u)) if e.get("tipo", "gauss") == "gauss" \
            else (lambda u: 1 / math.cosh(u) ** 2)
        g = _grafica([_serie("perfil", xs, [fg(al * x) for x in xs])],
                     "x (t = 0)", "f", "perfil arbitrario con sus trazas")
        return _ok(peticion, trace,
                   f"v = {r['v']:.6g} m/s hacia {r['direccion']}; {tr}",
                   "perfil de onda", f"E por área = {r['energia']:.6g} J/m²",
                   grafica=g)
    if calculo == "coulomb":
        tipo = str(e.get("tipo", "anillo"))
        if tipo == "anillo":
            r = F.e_anillo(e.get("Q", "1e-9"), e.get("R", 1),
                           e.get("z", 1), trace)
        elif tipo == "disco":
            r = F.e_disco(e.get("sigma", "1e-9"), e.get("R", 1),
                          e.get("z", "0.1"), trace)
        else:
            raise C.error("BAD_INPUT", "coulomb anillo o disco")
        return _ok(peticion, trace, f"E = {r['E']:.6g} V/m",
                   "Coulomb por integración", f"E = {r['E']:.6g} V/m")
    if calculo == "biot_savart":
        tipo = str(e.get("tipo", "espira"))
        if tipo == "espira":
            r = F.b_espira(e.get("I", 1), e.get("R", 1),
                           e.get("z", 0), trace)
            return _ok(peticion, trace, f"B = {r['B']:.6g} T",
                       "Biot-Savart en la espira", f"B = {r['B']:.6g} T")
        if tipo == "hilo":
            r = F.b_hilo(e.get("I", 1), e.get("r", 1), trace)
            return _ok(peticion, trace, f"B = {r['B']:.6g} T",
                       "Ampère en el hilo", "∮B·dl = μ₀I")
        if tipo == "coaxial":
            r = F.b_coaxial(e.get("I", 1), e.get("a", 1), e.get("b", 2),
                            e.get("r", "1.5"), e.get("central", "hilo"),
                            e.get("c"), trace)
            return _ok(peticion, trace,
                       f"B = {r['B']:.6g} T (I_enc = {r['I_enc']:.4g} A)",
                       "Ampère en el coaxial", "corriente encerrada parcial")
        if tipo == "poligono":
            r = F.b_poligono(e.get("I", 1), e.get("a", 1),
                             e.get("N", 6), trace)
            ns = list(range(3, 13))
            Bs = [F.b_poligono(e.get("I", 1), e.get("a", 1), N,
                               Trace())["B"] for N in ns]
            g = _grafica([_serie("B(N)", ns, Bs)], "N", "B (T)",
                         "polígono → círculo con N → ∞")
            return _ok(peticion, trace,
                       f"B = {r['B']:.6g} T; límite {r['limite']:.6g} T",
                       "polígono → espira", f"N → ∞ reproduce el círculo",
                       grafica=g)
        raise C.error("BAD_INPUT", "biot_savart espira, hilo o poligono")
    if calculo == "condensador":
        tipo = str(e.get("tipo", "plano"))
        if tipo == "plano":
            r = F.c_plano(e.get("eps_r", 1), e.get("A", 1),
                          e.get("d", "0.01"), trace)
        elif tipo == "esferico":
            r = F.c_esferico(e.get("eps_r", 1), e.get("R1", 1),
                             e.get("R2", 2), trace)
        elif tipo == "cilindrico":
            r = F.c_cilindrico(e.get("eps_r", 1), e.get("L", 1),
                               e.get("R1", 1), e.get("R2", 2), trace)
        elif tipo == "serie":
            r = F.c_serie(e.get("caps", [1, 2]), trace)
        elif tipo == "diel":
            r = F.diel_plano(e.get("Q", "1e-9"), e.get("A", 1),
                             e.get("capas", [{"d": 1, "eps_r": 2}]), trace)
            return _ok(peticion, trace,
                       f"C = {r['C']:.6g} F; V = {r['V']:.6g} V; "
                       f"D = {r['D']:.4g} C/m²",
                       "plano con dieléctricos", f"C por V y por serie")
        else:
            raise C.error("BAD_INPUT", "condensador plano, esferico, cilindrico, serie o diel")
        return _ok(peticion, trace, f"C = {r['C']:.6g} F",
                   "condensadores", f"C = {r['C']:.6g} F")
    if calculo == "faraday":
        r = F.faraday(e.get("B0", 1), e.get("f", 50), e.get("N", 100),
                      e.get("A", "0.01"), e.get("theta", 0), trace)
        return _ok(peticion, trace,
                   f"ε = {r['fem_amp']:.6g}·cos(ωt) V (Lenz)",
                   "inducción de Faraday", f"V = Wb/s; signo de Lenz")
    if calculo == "mutua":
        r = F.mutua_solenoide_bobina(e.get("N", 1000), e.get("Nb", 10),
                                     e.get("a", "0.1"), e.get("L", 1),
                                     e.get("alpha", 0), trace)
        return _ok(peticion, trace, f"M = {r['M']:.6g} H",
                   "inductancia mutua", f"M = Φ/I = {r['M']:.6g} H")
    if calculo == "poynting":
        r = F.poynting_condensador(e.get("I", 1), e.get("R", "0.1"),
                                   e.get("d", "0.01"), e.get("t", 2), trace)
        return _ok(peticion, trace, f"∮S·dA = dU/dt = {r['dU_dt']:.6g} W",
                   "balance de Poynting", f"∮S·dA = {r['flujo']:.6g} W")
    if calculo == "friis":
        r = F.friis(e.get("Pt", 10), e.get("Gt_dB", 20), e.get("Gr_dB", 15),
                    e.get("lam", "0.1"), e.get("R", 1000), trace)
        return _ok(peticion, trace,
                   f"Pr = {r['Pr']:.6g} W = {r['Pr_dB']:.6g} dBW",
                   "enlace Friis", "lineal frente a dB")
    if calculo == "ruido":
        r = F.ruido_sistema(e.get("G_dB", 40), e.get("T_sys", 100))
        return _ok(peticion, trace, f"G/T = {r['G_T']:.6g} dB/K",
                   "ruido del sistema", f"G/T = {r['G_T']:.6g} dB/K")
    if calculo == "array":
        r = F.array_factores(e.get("N", 4), e.get("d", "0.5"),
                             e.get("lam", 1), e.get("theta"))
        return _ok(peticion, trace,
                   f"AF = {r['AF']:.6g}; ancho ≈ {r['ancho']:.6g}",
                   "factor de array", f"N = {e.get('N', 4)}: lóbulo ≈ λ/Nd")
    if calculo == "fuerza_espira":
        r = F.fuerza_espira(e.get("I_hilo", 10), e.get("I_esp", 1),
                            e.get("a", "0.15"), e.get("b", "0.08"),
                            e.get("x", "0.1"), trace)
        return _ok(peticion, trace, f"F = {r['F']:.6g} N hacia el hilo",
                   "fuerza sobre espira", f"B: {r['B_x']:.4g} → {r['B_xa']:.4g} T")
    if calculo == "fuera_eje":
        r = F.b_espira_fuera_eje(e.get("I", 7), e.get("R", "0.2"),
                                 e.get("rho", 0), e.get("z", "0.2"),
                                 int(e.get("n", 720)), trace)
        Bx, By, Bz = r["B"]
        return _num(peticion, trace,
                    f"B = ({Bx:.6g}, {By:.6g}, {Bz:.6g}) T ± {r['error']:.2g}",
                    "Biot-Savart numérico",
                    f"sin forma elemental: error estimado {r['error']:.2g} T")
    if calculo == "mutua_neumann":
        r = F.mutua_neumann(e.get("loop1", []), e.get("loop2", []),
                            int(e.get("n", 40)), trace)
        return _num(peticion, trace, f"M = {r['M']:.6g} H ± {r['error']:.2g}",
                    "Neumann numérica",
                    f"sin simetría: error estimado {r['error']:.2g} H")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("campos", _campos)
