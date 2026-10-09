# SPDX-License-Identifier: MIT
"""ML-22: las calculadoras de física auxiliar (§8.2 U).

Operación ``fisica`` (contrato §5.9) con ``calculo``:

equilibrio, oscilacion, retrato, potencial_2d, gas, mezcla, muelle, ciclo,
kepler, orbita, elipse, visibilidad, maxwell_boltzmann, planck.
"""

from __future__ import annotations

import math

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import fisica as F
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
def _fisica(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "fisica")
    calculo = str(e.get("calculo", "equilibrio"))
    trace = Trace()
    pot = e.get("potencial", {"tipo": "poli", "coef": [0, 0, 1], "m": 1})

    if calculo == "equilibrio":
        r = F.equilibrios(pot, e.get("x0", -10), e.get("x1", 10), trace)
        lineas = [f"x = {q['x']:.6g} ({q['estabilidad']})" for q in r["equilibrios"]]
        U, _, _, _ = F._potencial(pot)
        xs = [e.get("x0", -10) + (e.get("x1", 10) - e.get("x0", -10)) * i / 240
              for i in range(241)]
        g = _grafica([_serie("U(x)", xs, [U(x) for x in xs])], "x", "U",
                     "potencial con sus equilibrios")
        return _ok(peticion, trace, "; ".join(lineas) or "sin equilibrios",
                   "equilibrios de U(x)", f"{len(r['equilibrios'])} puntos", grafica=g)
    if calculo == "oscilacion":
        r = F.oscilacion(pot, e.get("E", 1), e.get("x_eq"), trace)
        return _ok(peticion, trace,
                   f"ω = {r['omega']:.6g} rad/s; v_max = {r['v_max']:.6g} m/s; "
                   f"T = {r['T']:.6g} s (armónica {r['T_armonico']:.6g} s)",
                   "oscilación desde U(x)", f"T por cuadratura = RK4 = {r['T']:.6g} s")
    if calculo == "potencial_2d":
        r = F.potencial_2d(e.get("U", "x*y^2"), e.get("A", [0, 0]),
                           e.get("B", [1, 1]), trace)
        return _ok(peticion, trace,
                   f"F = ({r['Fx']}, {r['Fy']}); W = {r['W']:.6g} J",
                   "potencial 2D", f"W por dos caminos y −ΔU = {r['W']:.6g} J")
    if calculo == "retrato":
        r = F.retrato(pot, e.get("energias", [1]), e.get("x0", -10),
                      e.get("x1", 10))
        series = [_serie(s["nombre"], s["xs"], s["ys"]) for s in r["series"]]
        return _ok(peticion, trace, f"{len(series) - 1} niveles de energía",
                   "retrato de fases", "trayectorias (x, v) por RK4",
                   grafica=_grafica(series, "x", "v/U", "retrato de fases"))
    if calculo == "gas":
        d = dict(e.get("proceso", {"tipo": "lineal"}))
        r = F.gas_proceso(d, trace)
        return _ok(peticion, trace,
                   f"W = {r['W']:.6g} J; ΔU = {r['dU']:.6g} J; Q = {r['Q']:.6g} J; "
                   f"T_max = {r['Tmax']:.6g} K; ΔS = {r['dS']:.6g} J/K",
                   "proceso de gas ideal", f"ΔS por dos caminos = {r['dS']:.6g} J/K")
    if calculo == "mezcla":
        r = F.gas_mezcla(e.get("gases", []), trace)
        return _ok(peticion, trace, f"T_eq = {r['Teq']:.6g} K",
                   "mezcla de gases ideales", f"T_eq = {r['Teq']:.6g} K")
    if calculo == "muelle":
        r = F.muelle_gas(e.get("h", 3), e.get("gamma", 1), trace)
        return _ok(peticion, trace, f"ω = {r['omega']:.6g} rad/s",
                   "muelle de gas", f"ω = √(γg/h) = {r['omega']:.6g} rad/s")
    if calculo == "ciclo":
        r = F.gas_ciclo(e.get("vertices", []), e.get("n", 1),
                        e.get("Cv", 20.785), trace)
        ps = [p for p, _ in e["vertices"]]
        Vs = [V for _, V in e["vertices"]]
        g = _grafica([_serie("ciclo", Vs, ps)], "V", "p", "diagrama p–V del ciclo")
        return _ok(peticion, trace,
                   f"W = {r['W']:.6g} J; η = {r['eta']:.6g}",
                   "ciclo termodinámico", f"Clausius ΣQ + ΣW = 0", grafica=g)
    if calculo == "kepler":
        r = F.kepler(e.get("M", 1), e.get("e", "0.5"), trace)
        return _ok(peticion, trace, f"E = {r['E']:.10g} rad",
                   "ecuación de Kepler", f"M = E − e·senE verificado")
    if calculo == "orbita":
        r = F.orbita(e.get("a", "6.671e6"), e.get("M", "5.972e24"),
                     e.get("m", 1000), trace)
        return _ok(peticion, trace,
                   f"v = {r['v']:.6g} m/s; T = {r['T']:.6g} s",
                   "órbita circular", f"T²/a³ = 4π²/GM")
    if calculo == "visibilidad":
        r = F.visibilidad(e.get("R", "6.371e6"), e.get("h", "5e5"), trace)
        return _ok(peticion, trace,
                   f"θ = {r['theta'] * 180 / math.pi:.4g}°; "
                   f"fracción {r['fraccion']:.6g}",
                   "visibilidad esférica", f"cosθ = R/(R+h)")
    if calculo == "elipse":
        r = F.orbita_elipse(e.get("rp", 2), e.get("ra", 6), e.get("m", 2),
                            e.get("E"), e.get("L"), trace)
        return _ok(peticion, trace,
                   f"a = {r['a']:.6g} m; e = {r['e']:.6g}; C = {r['C']:.6g} J·m",
                   "órbita elíptica dada", f"E = −C/2a y U = −C/r comprobados")
    if calculo == "maxwell_boltzmann":
        r = F.maxwell_boltzmann(e.get("m", "9.11e-31"), e.get("T", 300), trace)
        return _ok(peticion, trace,
                   f"v_p = {r['v_p']:.6g}; v_med = {r['v_med']:.6g}; "
                   f"v_rms = {r['v_rms']:.6g} m/s",
                   "Maxwell-Boltzmann", "∫f = 1 y ⟨v²⟩ comprobados")
    if calculo == "planck":
        r = F.planck_integral(trace)
        return _ok(peticion, trace,
                   f"∫ = {r['integral']:.6g} = π⁴/15; σ = {r['sigma']:.6g} W/m²K⁴",
                   "Planck y Stefan", "σ = 2π⁵k⁴/15c²h³")
    if calculo == "circular":
        sub = str(e.get("tipo", "peralte"))
        if sub == "peralte":
            r = F.peralte(e.get("R", 100), e.get("v"), e.get("theta"), trace)
            return _ok(peticion, trace,
                       f"θ = {r['theta'] * 180 / math.pi:.4g}°; v = {r['v']:.6g} m/s",
                       "peralte sin rozamiento", f"tanθ = v²/gR")
        if sub == "cono":
            r = F.pendulo_conico(e.get("L", 1), e.get("omega"), e.get("theta"),
                                 trace)
            return _ok(peticion, trace,
                       f"θ = {r['theta'] * 180 / math.pi:.4g}°; T/m = {r['T_por_m']:.6g} N/kg",
                       "péndulo cónico", "T·cosθ = mg, T·senθ = mω²L·senθ")
        if sub == "talud":
            r = F.deslice_esfera(e.get("R", "2.5"), e.get("v0", 0), trace)
            if not r["despega"]:
                return _ok(peticion, trace, "no despega con esa v₀",
                           "deslizamiento esférico", f"cosθ_c ≥ 1")
            return _ok(peticion, trace,
                       f"θ_c = {r['theta_c'] * 180 / math.pi:.4g}° desde arriba",
                       "deslizamiento esférico", "N = 0 en el despegue")
        raise C.error("BAD_INPUT", "circular peralte, cono o talud")
    if calculo == "choque":
        r = F.choque_1d(e.get("m1", 1), e.get("v1", 2), e.get("m2", 3),
                        e.get("v2", 0), e.get("e", 1), trace)
        return _ok(peticion, trace,
                   f"v₁′ = {r['v1p']:.6g}; v₂′ = {r['v2p']:.6g} m/s",
                   "choque frontal", f"ΔEk = {r['dE']:.6g} J")
    if calculo == "cm":
        r = F.centro_masas(e.get("puntos", []), trace)
        return _ok(peticion, trace, f"CM = ({r['X']}, {r['Y']}); M = {r['M']}",
                   "centro de masas", f"M = {r['M']}")
    if calculo == "inercia":
        r = F.inercia(e.get("figura", "esfera"), e.get("m", 3),
                      e.get("d", "0.2"), trace)
        I = r["I"]
        if e.get("eje") is not None:
            r2 = F.steiner(I, e.get("m", 3), e.get("eje"), trace)
            I = r2["I"]
        return _ok(peticion, trace, f"I = {I:.6g} kg·m² ({r['formula']})",
                   "inercia + Steiner", f"I = {I:.6g} kg·m²")
    if calculo == "rodadura":
        r = F.rodadura(e.get("I", "0.5"), e.get("m", 1), e.get("R", 1),
                       e.get("h", 2), trace)
        return _ok(peticion, trace, f"v = {r['v']:.6g} m/s",
                   "rodadura sin deslizar", "Ek tras+rot = mgh")
    if calculo == "conduccion":
        r = F.conduccion(e.get("kappa", 401), e.get("S", "1e-4"),
                         e.get("dT", 50), e.get("L", "0.12"), trace)
        return _ok(peticion, trace, f"I = {r['I']:.6g} W",
                   "conducción de Fourier", f"R = {r['R_termica']:.6g} K/W")
    if calculo == "boltzmann":
        r = F.boltzmann_niveles(e.get("N", "1e10"), e.get("dE_eV", "0.5"),
                                e.get("T", 350), trace)
        return _ok(peticion, trace, f"N_exc = {r['N_exc']:.6g}",
                   "poblaciones de Boltzmann", f"x = ΔE/kT = {r['x']:.4g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("fisica", _fisica)
