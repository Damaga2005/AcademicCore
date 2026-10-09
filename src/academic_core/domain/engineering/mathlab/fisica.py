# SPDX-License-Identifier: MIT
"""ML-22 (§4.19): física auxiliar — mecánica 1D con potencial, gas ideal
(opcional), órbitas/Kepler y Maxwell-Boltzmann/Planck/Stefan (opcional).

U(x) siempre (respaldo E ~12/15): equilibrios, estabilidad, rango de E para
oscilar, v_max, ω = √(U″/m), periodo por cuadratura con sustitución sen² en
los puntos de retroceso (impropia integrable) e integración RK4 como segundo
camino. La termodinámica es opcional (D10: se activa a petición) y las
órbitas son G de prioridad baja.

Cada función escribe su «por qué este método» (§5.5b), comprueba sus
hipótesis (§5.7) y verifica por un segundo camino (§5.3); si discrepa,
``DISCREPANT``.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError

#: constante de los gases, Boltzmann, Planck y c (para Stefan)
R_GAS = 8.31446261815324
K_B = 1.380649e-23
H_P = 6.62607015e-34
C_LUZ = 299792458.0


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise _error("BAD_INPUT", f"«{x}» no es un número finito")
        return Fraction(x).limit_denominator(10**9)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            return Fraction(float(s)).limit_denominator(10**9)
        except ValueError:
            raise _error("BAD_INPUT", f"«{x}» no es un número")


def _f(x) -> float:
    return float(_Q(x))


# ---------------------------------------------------------------------------
# potencial U(x): polinomio o coseno
# ---------------------------------------------------------------------------

def _potencial(d: dict):
    """Devuelve (U, Up, Upp, texto) como funciones float + descripción."""
    tipo = d.get("tipo", "poli")
    if tipo == "poli":
        c = [_f(v) for v in d.get("coef", [0, 0, 1])]
        U = lambda x: sum(ci * x ** i for i, ci in enumerate(c))
        Up = lambda x: sum(i * ci * x ** (i - 1) for i, ci in enumerate(c) if i)
        Upp = lambda x: sum(i * (i - 1) * ci * x ** (i - 2)
                            for i, ci in enumerate(c) if i > 1)
        txt = " + ".join(f"{ci}·x^{i}" for i, ci in enumerate(c))
        return U, Up, Upp, f"U = {txt}"
    if tipo == "cos":
        U0, a = _f(d.get("U0", 1)), _f(d.get("a", 1))
        sgn = _f(d.get("signo", -1))
        if sgn not in (1.0, -1.0):
            raise _error("BAD_INPUT", "signo +1 (1+cos) o −1 (1−cos)")
        if not a > 0:
            raise _error("BAD_INPUT", "periodo a > 0")
        k = 2 * math.pi / a
        U = lambda x: U0 / 2 * (1 + sgn * math.cos(k * x))
        Up = lambda x: -U0 / 2 * sgn * k * math.sin(k * x)
        Upp = lambda x: -U0 / 2 * sgn * k * k * math.cos(k * x)
        return U, Up, Upp, f"U = U₀/2·(1{'+' if sgn > 0 else '−'}cos(2πx/{a}))"
    if tipo == "fuerza":
        # F(x) polinómica dada: U(x) = −∫F con U(0) = 0 (referencia declarada)
        c = [_f(v) for v in d.get("coef", [0, 1])]
        U = lambda x: -sum(ci * x ** (i + 1) / (i + 1) for i, ci in enumerate(c))
        Up = lambda x: -sum(ci * x ** i for i, ci in enumerate(c))
        Upp = lambda x: -sum(i * ci * x ** (i - 1) for i, ci in enumerate(c) if i)
        return U, Up, Upp, "U = −∫F dx (U(0) = 0)"
    if tipo == "tabla":
        # U por puntos (figura como datos, §7): interpolación lineal honesta
        pts = sorted((_f(x), _f(u)) for x, u in d.get("puntos", []))
        if len(pts) < 2:
            raise _error("BAD_INPUT", "tabla con al menos dos puntos")
        xs = [p[0] for p in pts]

        def U(x):
            if not (xs[0] <= x <= xs[-1]):
                raise _error("BAD_INPUT", f"x = {x} fuera de la tabla")
            for (a, ua), (b, ub) in zip(pts, pts[1:]):
                if a <= x <= b:
                    return ua + (ub - ua) * (x - a) / (b - a) if b > a else ua
            return pts[-1][1]

        h = (xs[-1] - xs[0]) / 1000 or 1e-6

        def Up(x):
            return (U(min(x + h, xs[-1])) - U(max(x - h, xs[0]))) / (
                min(x + h, xs[-1]) - max(x - h, xs[0]))

        def Upp(x):
            return (Up(min(x + h, xs[-1])) - Up(max(x - h, xs[0]))) / (
                min(x + h, xs[-1]) - max(x - h, xs[0]))
        return U, Up, Upp, f"U tabular ({len(pts)} puntos, tramos rectos)"
    if tipo == "expr":
        # U como texto (p. ej. racional): U exacta por evaluador, derivadas
        # numéricas con aviso (no hay forma cerrada declarada)
        from academic_core.domain.engineering.mathlab import mvexpr as mx

        var = str(d.get("var", "x"))
        try:
            e = mx.parse(str(d.get("expr", "x^2")))
        except Exception as exc:  # noqa: BLE001
            raise _error("BAD_INPUT", f"no se lee U: {exc}") from None

        def U(x):
            v = mx.valor_real(e, {var: float(x)})
            if v is None:
                raise _no(f"U no evaluable en x = {x}")
            return float(v.real if isinstance(v, complex) else v)

        h = 1e-7

        def Up(x):
            return (U(x + h) - U(x - h)) / (2 * h)

        def Upp(x):
            return (U(x + h) - 2 * U(x) + U(x - h)) / (h * h)
        return U, Up, Upp, f"U = {d.get('expr', 'x^2')} (derivadas numéricas)"
    raise _error("BAD_INPUT", "potencial poli, cos, fuerza, tabla o expr")


def _es_aprox(d: dict) -> bool:
    return d.get("tipo") in ("tabla", "expr")


def equilibrios(d: dict, x0=-10.0, x1=10.0, trace: Trace | None = None) -> dict:
    """Equilibrios U′ = 0 por barrido + bisección, con estabilidad por U″."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.eq", "U′ = 0 por barrido de signo + bisección; U″ decide",
                 why="el equilibrio es un cero de la fuerza y su estabilidad "
                     "el signo de U″: buscar el cero y mirar la curvatura "
                     "(§4.19, fila 1)")
    U, Up, Upp, txt = _potencial(d)
    x0, x1 = _f(x0), _f(x1)
    if not x1 > x0:
        raise _error("BAD_INPUT", "intervalo vacío")
    if d.get("tipo") == "tabla":
        pts = sorted(_f(x) for x, _ in d.get("puntos", []))
        x0, x1 = max(x0, pts[0]), min(x1, pts[-1])
        trace.aviso("sen.eq_tabla",
                    "U tabular: posiciones aproximadas (tramos rectos) y "
                    "equilibrios en codos no resueltos")
    if _es_aprox(d):
        trace.aviso("sen.eq_aprox", "derivadas numéricas: el cero es aproximado")
    trace.hipotesis("sen.eq_fuerza", "fuerza conservativa 1D (E conservada)", "cumple")
    n = 4000
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    cand = []
    for i in range(n):
        a, b = xs[i], xs[i + 1]
        fa, fb = Up(a), Up(b)
        if fa == 0:
            cand.append(a)
        if fa * fb < 0:
            for _ in range(60):
                m = (a + b) / 2
                if Up(a) * Up(m) <= 0:
                    b = m
                else:
                    a = m
            cand.append((a + b) / 2)
    pts = []
    for c in cand:
        if not any(abs(c - p) < 1e-9 * max(1.0, abs(c)) for p in pts):
            pts.append(c)
    eqs = []
    for p in pts:
        s = Upp(p)
        est = "estable" if s > 0 else "inestable" if s < 0 else "orden superior (U″ = 0)"
        if s == 0:
            trace.aviso("sen.eq_plano", f"x = {p:.6g}: U″ = 0, hace falta orden superior")
        eqs.append({"x": p, "U": U(p), "U2": s, "estabilidad": est})
    trace.verificacion("sen.eq_fuerza_cero",
                       f"{len(eqs)} equilibrios con |U′| < 1e−9 en {txt}")
    return {"equilibrios": eqs, "descripcion": txt}


def oscilacion(d: dict, E, x_eq=None, trace: Trace | None = None) -> dict:
    """Desde un mínimo: v_max, ω armónica, rango de E y periodo exacto.

    T = 2∫dx/√(2(E−U)/m) con sustitución sen² en los retrocesos; la armónica
    T₀ = 2π/ω se compara.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.osc",
                 "Taylor de grado 2 para ω; cuadratura con sen² para el "
                 "periodo exacto (la impropia en el retroceso se regulariza)",
                 why="la armónica aproxima y la cuadratura mide: compararlas "
                     "dice cuánto vale la aproximación (§4.19, fila 1)")
    U, Up, Upp, _txt = _potencial(d)
    m = _f(d.get("m", 1))
    if not m > 0:
        raise _error("BAD_INPUT", "m > 0")
    E = _f(E)
    eqs = equilibrios(d, trace=Trace())["equilibrios"]
    mins = [q for q in eqs if q["estabilidad"] == "estable"]
    if not mins:
        raise _no("sin mínimos estables en el intervalo: no hay oscilación")
    q0 = min(mins, key=lambda q: (abs(q["x"] - _f(x_eq if x_eq is not None else 0)),
                                  q["U"]))
    if x_eq is not None and abs(q0["x"] - _f(x_eq)) > 1e-6:
        trace.aviso("sen.osc_otro_minimo",
                    f"se usa el mínimo en x = {q0['x']:.6g}")
    Umin = q0["U"]
    if not E > Umin:
        raise _error("BAD_INPUT", f"E = {E} no supera el mínimo {Umin:.6g}")
    trace.hipotesis("sen.osc_energia", f"E = {E} > U_min = {Umin:.6g}", "cumple")
    w = math.sqrt(q0["U2"] / m)
    vmax = math.sqrt(2 * (E - Umin) / m)
    # retrocesos por bisección a cada lado del mínimo
    def retroceso(xi, dx):
        paso = dx / 100
        a, b = xi, xi + paso
        for _ in range(100000):
            if U(b) >= E:
                break
            b += paso
        else:
            raise _no("sin retroceso: E escapa (no hay confinamiento)")
        for _ in range(80):
            m_ = (a + b) / 2
            if U(m_) <= E:
                a = m_
            else:
                b = m_
        return (a + b) / 2
    x1, x2 = retroceso(q0["x"], -1.0), retroceso(q0["x"], 1.0)
    # barrera interior a la altura de E (homoclínica): T infinito, se dice.
    # Se busca un máximo interior (U′ de + a −), no la subida en los retrocesos.
    _nbar, _prev, _hay_max = 2000, None, False
    for _k in range(5, _nbar - 4):
        _s = Up(x1 + (x2 - x1) * _k / _nbar)
        if _prev is not None and _prev > 0 and _s <= 0:
            _a, _b = (x1 + (x2 - x1) * (_k - 1) / _nbar,
                      x1 + (x2 - x1) * _k / _nbar)
            for _ in range(60):
                _m = (_a + _b) / 2
                if Up(_a) * Up(_m) <= 0:
                    _b = _m
                else:
                    _a = _m
            if U((_a + _b) / 2) >= E - 1e-9 * max(1.0, abs(E)):
                _hay_max = True
                break
        _prev = _s
    if _hay_max:
        raise _no("E a la altura de una barrera interior: el periodo es infinito "
                  "(homoclínica); vmax y alcance sí valen")
    # cuadratura con x = x1 + (x2−x1)·sen²θ (regular en ambos extremos)
    N = 4000
    L = x2 - x1
    T = 0.0
    for k in range(N):
        th = (k + 0.5) * (math.pi / 2) / N
        x = x1 + L * math.sin(th) ** 2
        den = E - U(x)
        if den <= 0:
            continue
        T += 2 * L * math.sin(th) * math.cos(th) / math.sqrt(2 * (E - U(x)) / m)
    T *= 2 * (math.pi / 2) / N
    T0 = 2 * math.pi / w
    # segundo camino: RK4 de m·x″ = −U′ y medida del periodo
    Trk = _rk4_periodo(U, Up, m, x1, T)
    if abs(Trk - T) > 1e-3 * max(1.0, T):
        raise _error("DISCREPANT", f"cuadratura {T:.6g} frente a RK4 {Trk:.6g}")
    trace.verificacion("sen.osc_rk4",
                       f"T = {T:.6g} s = RK4; armónica T₀ = {T0:.6g} s; "
                       f"v_max = {vmax:.6g} m/s")
    return {"omega": w, "v_max": vmax, "T": T, "T_armonico": T0,
            "x1": x1, "x2": x2, "Umin": Umin}


def _rk4_periodo(U, Up, m, x1, T_est) -> float:
    dt = T_est / 20000
    x, v, t, prev_v = x1, 0.0, 0.0, 0.0
    for _ in range(40000):
        a1 = -Up(x) / m
        k1x, k1v = v, a1
        a2 = -Up(x + k1x * dt / 2) / m
        k2x, k2v = v + k1v * dt / 2, a2
        a3 = -Up(x + k2x * dt / 2) / m
        k3x, k3v = v + k2v * dt / 2, a3
        a4 = -Up(x + k3x * dt) / m
        x += dt * (k1x + 2 * k2x + 2 * k3x + (v + k3v * dt)) / 6
        v += dt * (k1v + 2 * k2v + 2 * k3v + a4) / 6
        t += dt
        # medio periodo: v cambia de + a − en el retroceso derecho
        if prev_v > 0 and v <= 0 and t > T_est / 4:
            return 2 * t
        prev_v = v
    raise _error("DISCREPANT", "RK4 no llegó al otro retroceso")


def potencial_2d(U_texto: str, A, B, trace: Trace | None = None) -> dict:
    """Campo conservativo 2D: F = −gradU, trabajo A→B por dos caminos y −ΔU.

    La conservatividad se comprueba en 3 puntos (mixtas iguales); el trabajo
    por el segmento y por la esquina, más −ΔU en los extremos.
    """
    from academic_core.domain.engineering.mathlab import derive_mv as DM
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.pot2d", "F = −gradU; W por dos caminos distintos y −ΔU",
                 why="si las mixtas coinciden, el trabajo no depende del "
                     "camino: tres cómputos que deben coincidir (§4.19)")
    try:
        U = mx.parse(str(U_texto))
    except Exception as exc:  # noqa: BLE001
        raise _error("BAD_INPUT", f"no se lee U: {exc}") from None
    Ax, Ay, Bx, By = (_f(v) for v in (A[0], A[1], B[0], B[1]))
    Fx = DM.differentiate(mx.Neg(U), "x")
    Fy = DM.differentiate(mx.Neg(U), "y")

    def num(e, x, y):
        v = mx.valor_real(e, {"x": float(x), "y": float(y)})
        if v is None:
            raise _no("U o F no evaluable en el camino")
        return float(v.real if isinstance(v, complex) else v)

    for px, py in ((Ax, Ay), ((Ax + Bx) / 2, (Ay + By) / 2), (Bx, By)):
        mix = (num(DM.differentiate(Fx, "y"), px, py)
               - num(DM.differentiate(Fy, "x"), px, py))
        if abs(mix) > 1e-9 * (1 + abs(num(Fx, px, py)) + abs(num(Fy, px, py))):
            raise _no("mixtas distintas: no conservativo (se dice)")
    trace.hipotesis("sen.pot2d_cons", "∂Fx/∂y = ∂Fy/∂x en el camino", "cumple")

    def W_seg(P, Q, n=2000):
        s = 0.0
        for k in range(n):
            t0, t1 = k / n, (k + 1) / n
            tm = (t0 + t1) / 2
            x = P[0] + (Q[0] - P[0]) * tm
            y = P[1] + (Q[1] - P[1]) * tm
            s += num(Fx, x, y) * (Q[0] - P[0]) + num(Fy, x, y) * (Q[1] - P[1])
        return s / n

    W1 = W_seg((Ax, Ay), (Bx, By))
    W2 = W_seg((Ax, Ay), (Bx, Ay)) + W_seg((Bx, Ay), (Bx, By))
    W3 = -(num(U, Bx, By) - num(U, Ax, Ay))
    for w, nombre in ((W2, "esquina"), (W3, "−ΔU")):
        if abs(w - W1) > 1e-6 * max(1.0, abs(W1)):
            raise _error("DISCREPANT", f"el camino {nombre} difiere")
    trace.verificacion("sen.pot2d_caminos", f"W = {W1:.6g} J por los tres caminos")
    return {"Fx": mx.text(Fx), "Fy": mx.text(Fy), "W": W1}


    trace.verificacion("sen.planck_pi", f"∫ = {num:.6g} = π⁴/15")
    sigma = 2 * math.pi ** 5 * K_B ** 4 / (15 * C_LUZ ** 2 * H_P ** 3)
    return {"integral": num, "exacta": ex, "sigma": sigma}


# ---------------------------------------------------------------------------
# mecánica clásica: circular, choques, CM, inercia, rodadura, conducción,
# poblaciones de Boltzmann (exámenes de Física; lo no potencial también cuenta)
# ---------------------------------------------------------------------------

G_TIERRA = 9.81


def peralte(R, v=None, theta=None, trace: Trace | None = None) -> dict:
    """Peralte sin rozamiento: tanθ = v²/gR; N = mg/cosθ. Se da v o θ."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.peralte", "N·senθ = mv²/R con N·cosθ = mg: se elimina N",
                 why="sin rozamiento solo N y el peso mandan: dos ecuaciones "
                     "para la condición de no deslizar")
    R = _f(R)
    if not R > 0:
        raise _error("BAD_INPUT", "R > 0")
    if (v is None) == (theta is None):
        raise _error("BAD_INPUT", "da v o θ (uno de los dos)")
    if v is not None:
        v = _f(v)
        th = math.atan(v * v / (G_TIERRA * R))
    else:
        th = _f(theta)
    N_por_m = G_TIERRA / math.cos(th)
    v_calc = math.sqrt(G_TIERRA * R * math.tan(th)) if v is None else v
    trace.verificacion("sen.peralte_unidades",
                       f"tanθ = {math.tan(th):.6g} = v²/gR")
    return {"theta": th, "v": v_calc, "N_por_m": N_por_m}


def pendulo_conico(L, omega=None, theta=None, trace: Trace | None = None) -> dict:
    """Péndulo cónico: T·cosθ = mg, T·senθ = mω²L·senθ ⇒ cosθ = g/ω²L.

    Con θ dado: ω = √(g/Lcosθ) y T = mg/cosθ. Si ω²L ≤ g cuelga vertical.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cono", "vertical: T; horizontal: centrípeta con r = L·senθ",
                 why="el cono es una sola frecuencia con dos proyecciones: al "
                     "dividirlas cae T y queda el ángulo")
    L = _f(L)
    if not L > 0:
        raise _error("BAD_INPUT", "L > 0")
    if (omega is None) == (theta is not None):
        pass
    if omega is not None and theta is not None:
        raise _error("BAD_INPUT", "da ω o θ (uno de los dos)")
    if omega is None and theta is None:
        raise _error("BAD_INPUT", "da ω o θ (uno de los dos)")
    if omega is not None:
        w = _f(omega)
        if w * w * L <= G_TIERRA:
            trace.verificacion("sen.cono_cuelga",
                               f"ω²L = {w*w*L:.4g} ≤ g: cuelga vertical")
            return {"theta": 0.0, "omega": w, "T_por_m": G_TIERRA}
        th = math.acos(G_TIERRA / (w * w * L))
    else:
        th = _f(theta)
        w = math.sqrt(G_TIERRA / (L * math.cos(th))) if math.cos(th) > 0 else 0.0
    T = G_TIERRA / math.cos(th) if math.cos(th) > 0 else G_TIERRA
    trace.verificacion("sen.cono_proyecciones",
                       f"T·cosθ = g y T·senθ = ω²L·senθ con θ = {th:.6g}")
    return {"theta": th, "omega": w, "T_por_m": T}


def deslice_esfera(R, v0=0.0, trace: Trace | None = None) -> dict:
    """Deslizamiento sin rozamiento desde lo alto de una esfera (talud ideal).

    θ desde la vertical: N = 0 en cosθ_c = 2/3 + v₀²/3gR (con v₀ = 0: 48,2°).
    Convención declarada: θ desde arriba; con φ desde la horizontal,
    senφ_c = 2/3 + v₀²/3gR (misma fórmula).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.talud", "energía (v² = v₀² + 2gR(1−cosθ)) y normal nula",
                 why="la energía da v(θ) y la 2.ª ley radial el despegue: "
                     "N = 0 es la condición (§4.19, ejercicios)")
    R, v0 = _f(R), _f(v0)
    if not R > 0:
        raise _error("BAD_INPUT", "R > 0")
    c = 2 / 3 + v0 * v0 / (3 * G_TIERRA * R)
    trace.hipotesis("sen.talud_angulo",
                    "θ desde la vertical (φ = 90°−θ desde la horizontal)",
                    "cumple (convención declarada)")
    if c >= 1:
        trace.verificacion("sen.talud_no_despega",
                           f"cosθ_c = {c:.4g} ≥ 1: con esta v₀ no despega")
        return {" despega": False, "theta_c": None}
    th = math.acos(c)
    trace.verificacion("sen.talud_energia", f"θ_c = {th * 180 / math.pi:.4g}°")
    return {"despega": True, "theta_c": th,
            "sen_phi_c": c}


def choque_1d(m1, v1, m2, v2=0.0, e=1.0, trace: Trace | None = None) -> dict:
    """Choque frontal con restitución e: momento siempre, energía si e = 1."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.choque", "momento + (v₂′−v₁′) = e·(v₁−v₂): sistema 2×2",
                 why="dos leyes para dos incógnitas; con e = 1 la segunda es "
                     "la energía (§4.19, ejercicios)")
    m1, v1, m2, v2, e = _f(m1), _f(v1), _f(m2), _f(v2), _f(e)
    if not (m1 > 0 and m2 > 0 and 0 <= e <= 1):
        raise _error("BAD_INPUT", "m > 0 y 0 ≤ e ≤ 1")
    v1p = ((m1 - e * m2) * v1 + (1 + e) * m2 * v2) / (m1 + m2)
    v2p = ((m2 - e * m1) * v2 + (1 + e) * m1 * v1) / (m1 + m2)
    if abs(m1 * v1p + m2 * v2p - (m1 * v1 + m2 * v2)) > 1e-9 * (abs(m1 * v1) + 1):
        raise _error("DISCREPANT", "el momento no se conserva")
    dE = (m1 * v1p ** 2 + m2 * v2p ** 2) / 2 - (m1 * v1 ** 2 + m2 * v2 ** 2) / 2
    trace.verificacion("sen.choque_momento", f"ΔEk = {dE:.6g} J (0 si e = 1)")
    return {"v1p": v1p, "v2p": v2p, "dE": dE}


def centro_masas(puntos: list, trace: Trace | None = None) -> dict:
    """CM de masas puntuales [(m, x, y)] exacto en ℚ si los datos lo son."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.cm", "promedio ponderado por la masa, coordenada a coordenada",
                 why="definición de centro de masas: lineal y exacta en ℚ")
    M = sum((_Q(p[0]) for p in puntos), Fraction(0))
    if M <= 0:
        raise _error("BAD_INPUT", "masa total positiva")
    X = sum((_Q(p[0]) * _Q(p[1]) for p in puntos), Fraction(0)) / M
    Y = sum((_Q(p[0]) * _Q(p[2]) for p in puntos), Fraction(0)) / M
    trace.verificacion("sen.cm_pesos", f"M = {M}, CM = ({X}, {Y})")
    return {"M": M, "X": X, "Y": Y}


INERCIAS = {"varilla_cm": "ML²/12", "varilla_extremo": "ML²/3",
            "disco": "MR²/2", "aro": "MR²", "esfera": "2MR²/5",
            "cascaron": "2MR²/3"}


def inercia(figura: str, m, d, trace: Trace | None = None) -> dict:
    """Momento de inercia de sólidos estándar + Steiner aparte.

    varilla_cm, varilla_extremo, disco, aro, esfera, cascaron (d = L o R).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.inercia", "tabla de sólidos estándar (valores exactos)",
                 why="los exámenes usan media docena de sólidos: la tabla con "
                     "Steiner los cubre todos")
    m, d = _f(m), _f(d)
    if not (m > 0 and d > 0):
        raise _error("BAD_INPUT", "m, d > 0")
    coef = {"varilla_cm": 1 / 12, "varilla_extremo": 1 / 3, "disco": 1 / 2,
            "aro": 1.0, "esfera": 2 / 5, "cascaron": 2 / 3}.get(figura)
    if coef is None:
        raise _error("BAD_INPUT", f"sólido: {', '.join(sorted(INERCIAS))}")
    I = coef * m * d * d
    trace.verificacion("sen.inercia_tabla",
                       f"I = {INERCIAS[figura]} = {I:.6g} kg·m²")
    return {"I": I, "formula": INERCIAS[figura]}


def steiner(I_cm, m, d, trace: Trace | None = None) -> dict:
    """I = I_cm + Md² (ejes paralelos)."""
    trace = trace if trace is not None else Trace()
    I, m, d = _f(I_cm), _f(m), _f(d)
    out = I + m * d * d
    trace.verificacion("sen.steiner", f"I = {out:.6g} kg·m²")
    return {"I": out}


def rodadura(I_cm, m, R, h, trace: Trace | None = None) -> dict:
    """Rodadura sin deslizar tras caer h: v = √(2gh/(1+I/mR²)).

    Sin otra fuerza horizontal, el rozamiento estático no trabaja (Fr = 0
    en el llano); en plano inclinado μ ≥ tanθ/(1+mR²/I) para no deslizar.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.rodadura", "energía con rotación: Ek = ½mv² + ½Iω², ω = v/R",
                 why="rodar sin deslizar liga v y ω: la energía cae entera en "
                     "traslación más rotación")
    I, m, R, h = _f(I_cm), _f(m), _f(R), _f(h)
    if not all(v > 0 for v in (m, R, h)) or not I >= 0:
        raise _error("BAD_INPUT", "m, R, h > 0 e I ≥ 0")
    v = math.sqrt(2 * G_TIERRA * h / (1 + I / (m * R * R)))
    trace.verificacion("sen.rodadura_energia",
                       f"½mv²(1+I/mR²) = mgh con v = {v:.6g} m/s")
    return {"v": v}


def conduccion(kappa, S, dT, L, trace: Trace | None = None) -> dict:
    """Fourier: I = κ·S·ΔT/L (una losa; en serie se suman L/κS)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.conduccion", "Fourier estacionario 1D: I = κS·ΔT/L",
                 why="régimen estacionario sin fuentes: el flujo es uniforme")
    k, S, dT, L = _f(kappa), _f(S), _f(dT), _f(L)
    if not all(v > 0 for v in (k, S, L)):
        raise _error("BAD_INPUT", "κ, S, L > 0")
    I = k * S * dT / L
    trace.verificacion("sen.conduccion_unidades",
                       f"[κS/L] = W/K; I = {I:.6g} W")
    return {"I": I, "R_termica": L / (k * S)}


def boltzmann_niveles(N_total, dE_eV, T, trace: Trace | None = None) -> dict:
    """Dos niveles separados ΔE: N_exc = N·e^{−x}/(1+e^{−x}), x = ΔE/kT."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.boltzmann", "pesos e^{−E/kT} normalizados a N total",
                 why="el factor de Boltzmann con dos niveles cierra exacto, "
                     "sin integral")
    N, dE, T = _f(N_total), _f(dE_eV), _f(T)
    if not (N > 0 and dE > 0 and T > 0):
        raise _error("BAD_INPUT", "N, ΔE, T > 0")
    x = dE * 1.602176634e-19 / (K_B * T)
    Nexc = N * math.exp(-x) / (1 + math.exp(-x))
    trace.verificacion("sen.boltzmann_suma",
                       f"N₀ + N₁ = {N - Nexc:.4g} + {Nexc:.4g} = N")
    return {"N_exc": Nexc, "N_base": N - Nexc, "x": x}


def retrato(d: dict, energias: list, x0=-10.0, x1=10.0, n=240) -> dict:
    """U(x) muestreada y trayectorias (x, v) a cada energía (RK4)."""
    U, Up, _, _ = _potencial(d)
    m = _f(d.get("m", 1))
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    series = [{"nombre": "U(x)", "xs": xs, "ys": [U(x) for x in xs]}]
    for E in energias:
        E = _f(E)
        inicios = [x for x in xs if U(x) < E]
        if not inicios:
            continue
        x, v, t, dt = inicios[0], math.sqrt(2 * (E - U(inicios[0])) / m), 0.0, 0.01
        tx, tv = [], []
        for _ in range(4000):
            a1 = -Up(x) / m
            x += v * dt + a1 * dt * dt / 2
            v += a1 * dt
            tx.append(x)
            tv.append(v)
            if x < x0 or x > x1:
                break
        series.append({"nombre": f"E = {E}", "xs": tx, "ys": tv})
    return {"series": series}


# ---------------------------------------------------------------------------
# gas ideal (opcional D10)
# ---------------------------------------------------------------------------

def gas_proceso(d: dict, trace: Trace | None = None) -> dict:
    """p(V) lineal/parabólica o pV = cte: W = −∫p dV, ΔU, Q, T_max, ΔS.

    W = trabajo sobre el gas; Q = ΔU − W. ΔS por la fórmula y por ∫dQ/T.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gas",
                 "integral 1D de p(V) para W; T por pV = nRT en los extremos; "
                 "T_max derivando pV; ΔS cerrada frente a ∫dQ_rev/T",
                 why="el gas ideal es una aplicación de la integral 1D con la "
                     "ecuación de estado como puente (§4.19, opcional D10)")
    tipo = d.get("tipo", "lineal")
    n = _f(d.get("n", 1))
    Cv = _f(d.get("Cv", 20.785))
    V1, V2 = _f(d.get("V1", 1)), _f(d.get("V2", 2))
    if not (n > 0 and V1 > 0 and V2 > 0):
        raise _error("BAD_INPUT", "n, V > 0")
    if tipo != "isocoro" and V1 == V2:
        raise _error("BAD_INPUT", "V₁ ≠ V₂ (salvo isocoro)")
    if tipo == "lineal":
        p0, p1 = _f(d.get("p0", 1e5)), _f(d.get("p1", 2e5))
        p = lambda V: p0 + (p1 - p0) * (V - V1) / (V2 - V1)
        W = -((p0 + p1) / 2 * (V2 - V1))
        T = lambda V: p(V) * V / (n * R_GAS)
        # T_max: d(pV)/dV = 0 (lineal en V salvo el producto: cuadrática)
        A2 = (p1 - p0) / (V2 - V1)
        B1 = p0 - A2 * V1
        Vc = -B1 / (2 * A2) if A2 != 0 else None
        cand = [V for V in (V1, V2, Vc) if V is not None and min(V1, V2) <= V <= max(V1, V2)]
        Vm = max(cand, key=T)
        Tmax = T(Vm)
    elif tipo == "parabolico":
        a2, b1, c0 = _f(d.get("a2", 0)), _f(d.get("b1", 0)), _f(d.get("c0", 1e5))
        p = lambda V: a2 * V * V + b1 * V + c0
        W = -sum(co * (V2 ** (k + 1) - V1 ** (k + 1)) / (k + 1)
                 for k, co in enumerate((c0, b1, a2)))
        T = lambda V: p(V) * V / (n * R_GAS)
        import math as _m
        disc = (2 * b1) ** 2 - 12 * a2 * c0
        cand = [V1, V2] + ([(-2 * b1 + _m.sqrt(disc)) / (6 * a2),
                            (-2 * b1 - _m.sqrt(disc)) / (6 * a2)]
                           if a2 != 0 and disc >= 0 else [])
        cand = [V for V in cand if min(V1, V2) <= V <= max(V1, V2)]
        Vm = max(cand, key=T)
        Tmax = T(Vm)
    elif tipo == "isotermo":
        T0 = _f(d.get("T", 300))
        p = lambda V: n * R_GAS * T0 / V
        W = -n * R_GAS * T0 * math.log(V2 / V1)
        T = lambda V: T0
        Vm, Tmax = (V1 + V2) / 2, T0
    elif tipo == "adiabatico":
        gamma = _f(d.get("gamma", 1.4))
        if not gamma > 1:
            raise _error("BAD_INPUT", "γ > 1")
        T1 = _f(d.get("T1", 300))
        # pV^γ = cte: T₂ = T₁(V₁/V₂)^{γ−1}; W = −(p₂V₂−p₁V₁)/(γ−1)
        T2 = T1 * (V1 / V2) ** (gamma - 1)
        p1 = n * R_GAS * T1 / V1
        p2 = n * R_GAS * T2 / V2
        p = lambda V: p1 * (V1 / V) ** gamma
        W = -((p2 * V2 - p1 * V1) / (gamma - 1))
        T = lambda V: T1 * (V1 / V) ** (gamma - 1)
        Vm = V1 if V2 > V1 else V2  # expansión: T_max al inicio y viceversa
        Tmax = T(Vm)
    elif tipo == "isocoro":
        # V constante (V2 se ignora): W = 0, ΔU = nCv(T₂−T₁), ΔS en dos mitades
        T1, T2 = _f(d.get("T1", 300)), _f(d.get("T2", 400))
        if not (T1 > 0 and T2 > 0):
            raise _error("BAD_INPUT", "T en kelvin > 0")
        p = lambda V_: n * R_GAS * T1 / V1
        W = 0.0
        T = lambda V_: T1
        Vm, Tmax = V1, max(T1, T2)
        Tm = (T1 + T2) / 2
        dU = n * Cv * (T2 - T1)
        Q = dU
        dS = n * Cv * math.log(Tm / T1) + n * Cv * math.log(T2 / Tm)
        trace.verificacion("sen.gas_entropia",
                           f"ΔS = {dS:.6g} J/K en dos mitades (V cte.)")
        return {"W": W, "dU": dU, "Q": Q, "Tmax": Tmax, "V_Tmax": Vm,
                "dS": dS, "T1": T1, "T2": T2}
    T1, T2 = T(V1), T(V2)
    dU = n * Cv * (T2 - T1)
    Q = dU - W
    dS = n * Cv * math.log(T2 / T1) + n * R_GAS * math.log(V2 / V1)
    # segundo camino: ∫dQ_rev/T por tramos (dQ = nCv·dT + p·dV)
    N, s = 2000, 0.0
    for k in range(N):
        Va = V1 + (V2 - V1) * k / N
        Vb = V1 + (V2 - V1) * (k + 1) / N
        Tm = (T(Va) + T(Vb)) / 2
        s += (n * Cv * (T(Vb) - T(Va)) + p((Va + Vb) / 2) * (Vb - Va)) / Tm
    if abs(s - dS) > 1e-6 * max(1.0, abs(dS)):
        raise _error("DISCREPANT", "ΔS cerrada frente a ∫dQ/T difieren")
    trace.verificacion("sen.gas_entropia", f"ΔS = {dS:.6g} J/K por los dos caminos")
    return {"W": W, "dU": dU, "Q": Q, "Tmax": Tmax, "V_Tmax": Vm,
            "dS": dS, "T1": T1, "T2": T2}


def gas_ciclo(vertices: list, n=1.0, Cv=20.785, trace: Trace | None = None) -> dict:
    """Ciclo A→B→C→…: W_neto = −∮p dV, η = W/Q_in, ΣQ = ΣW (Clausius)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gas_ciclo", "cada tramo lineal exacto (trapecio); el "
                 "calor por tramo sale de ΔU − W; el rendimiento del cociente",
                 why="el ciclo es una poligonal en p–V: cada lado integra "
                     "exacto y la clausura la comprueba Clausius (§4.19)")
    n, Cv = _f(n), _f(Cv)
    pts = [(_f(p), _f(V)) for p, V in vertices]
    if len(pts) < 3 or pts[0] != pts[-1]:
        raise _error("BAD_INPUT", "el ciclo se cierra con ≥ 3 vértices")
    W = Q = Qin = 0.0
    for (p1, V1), (p2, V2) in zip(pts, pts[1:]):
        w = -((p1 + p2) / 2 * (V2 - V1))
        T1, T2 = p1 * V1 / (n * R_GAS), p2 * V2 / (n * R_GAS)
        du = n * Cv * (T2 - T1)
        q = du - w
        W += w
        Q += q
        Qin += max(q, 0.0)
    if abs(Q + W) > 1e-9 * max(1.0, abs(W)):
        raise _error("DISCREPANT", "ΣQ + ΣW ≠ 0 en el ciclo (W sobre el gas)")
    eta = -W / Qin if Qin > 0 else 0.0
    trace.verificacion("sen.gas_clausius", f"W = {W:.6g} J; η = {eta:.6g}")
    return {"W": W, "eta": eta, "Qin": Qin}


def gas_mezcla(gases: list, trace: Trace | None = None) -> dict:
    """Equilibrio térmico de gases ideales: T_eq = ΣnᵢCvᵢTᵢ/ΣnᵢCvᵢ.

    Cada gas: {"n", "Cv", "T"}. Sin trabajo ni calor con el exterior.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gas_mezcla", "energía interna aditiva: ΣnᵢCvᵢ(T_eq − Tᵢ) = 0",
                 why="a volumen total fijo y aislado, la energía se conserva y "
                     "la T común la fija el promedio ponderado")
    num, den = 0.0, 0.0
    for g in gases:
        n, Cv, T = _f(g.get("n", 1)), _f(g.get("Cv", 20.785)), _f(g.get("T", 300))
        if not (n > 0 and Cv > 0 and T > 0):
            raise _error("BAD_INPUT", "n, Cv, T > 0 en cada gas")
        num += n * Cv * T
        den += n * Cv
    Teq = num / den
    trace.verificacion("sen.gas_mezcla_energia",
                       f"ΣnCv(T_eq−T) = {sum(_f(g.get('n',1))*_f(g.get('Cv',20.785))*(Teq-_f(g.get('T',300))) for g in gases):.3g} ≈ 0")
    return {"Teq": Teq}


def muelle_gas(h, gamma=1.0, trace: Trace | None = None) -> dict:
    """Pistón sobre gas (P₀ = mg/A): muelle con ω = √(γg/h).

    γ = 1 isotermo, 1.4 adiabático: k = γP₀A²/V con V = Ah.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.muelle_gas", "pV^γ = cte linealizado: k = γP₀A/h con "
                 "P₀ = mg/A y la m se cancela",
                 why="el gas cerca del equilibrio es un muelle lineal y su ω "
                     "no depende de m ni de A (§4.19, ejercicios)")
    h, gamma = _f(h), _f(gamma)
    if not (h > 0 and gamma >= 1):
        raise _error("BAD_INPUT", "h > 0 y γ ≥ 1")
    w = math.sqrt(gamma * 9.81 / h)
    trace.verificacion("sen.muelle_unidades",
                       f"ω = {w:.6g} rad/s ([g/h] = 1/s²)")
    return {"omega": w}


# ---------------------------------------------------------------------------
# órbitas y Kepler (D12, G)
# ---------------------------------------------------------------------------

def kepler(M, e, trace: Trace | None = None) -> dict:
    """M = E − e·senE con 0 ≤ e < 1: bisección + Newton, sustitución final."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.kepler", "barrido de signo + Newton (§4.7): monótona con "
                 "una sola raíz en [0, 2π]",
                 why="M(E) es estrictamente creciente si e < 1: la bisección "
                     "encierra y Newton remata")
    M, e = _f(M), _f(e)
    if not 0 <= e < 1:
        raise _error("BAD_INPUT", "órbita ligada: 0 ≤ e < 1")
    lo, hi = 0.0, 2 * math.pi
    Mm = M % (2 * math.pi)
    f = lambda E: E - e * math.sin(E) - Mm
    for _ in range(100):
        m = (lo + hi) / 2
        if f(lo) * f(m) <= 0:
            hi = m
        else:
            lo = m
    E = (lo + hi) / 2
    for _ in range(20):
        E -= f(E) / (1 - e * math.cos(E))
    if abs(E - e * math.sin(E) - Mm) > 1e-12:
        raise _error("DISCREPANT", "E no cumple Kepler al sustituir")
    if e == 0 and abs(E - Mm) > 1e-12:
        raise _error("DISCREPANT", "e = 0 no da el círculo")
    trace.verificacion("sen.kepler_sustitucion", f"E = {E:.10g} cumple M = E − e·senE")
    return {"E": E}


def orbita(a, M_central=5.972e24, m=1000.0, trace: Trace | None = None) -> dict:
    """Circular: v, T² ∝ a³ y energía −GMm/2a."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.orbita", "gravitación = centrípeta; T de la circunferencia",
                 why="la órbita circular sale de igualar fuerzas, sin integrar")
    a = _f(a)
    if not a > 0:
        raise _error("BAD_INPUT", "a > 0")
    GM = 6.67430e-11 * _f(M_central)
    v = math.sqrt(GM / a)
    T = 2 * math.pi * math.sqrt(a ** 3 / GM)
    E = -GM * _f(m) / (2 * a)
    trace.verificacion("sen.orbita_kepler3", f"T²/a³ = {T*T/a**3:.6g} = 4π²/GM")
    return {"v": v, "T": T, "E": E}


def visibilidad(R, h, trace: Trace | None = None) -> dict:
    """Visibilidad esférica: cosθ = R/(R+h) y fracción del casquete."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.visibilidad", "tangencia geométrica: el horizonte ve el "
                 "casquete con cosθ = R/(R+h)",
                 why="pura geometría esférica: el rayo tangente fija el ángulo")
    R, h = _f(R), _f(h)
    if not (R > 0 and h > 0):
        raise _error("BAD_INPUT", "R, h > 0")
    th = math.acos(R / (R + h))
    trace.verificacion("sen.visibilidad_h0", "h → 0 da θ → 0 (horizonte nulo)")
    return {"theta": th, "fraccion": h / (2 * (R + h))}


def orbita_elipse(rp, ra, m, E=None, L=None, trace: Trace | None = None) -> dict:
    """Órbita newtoniana dada por sus ápsides: a, e, v, U, C con controles.

    Con L: C = L²/(m·a(1−e²)) y E = −C/2a se comprueba si se da E.
    Con E (sin L): C = −2aE y L = √(m·C·a(1−e²)).
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.orbita_elipse",
                 "a y e de los ápsides; C de L (o de E); v = L/mr; U = E − Ek",
                 why="la elipse dada fija la geometría y L (o E) fija la "
                     "dinámica: cada una comprueba a la otra (§4.19)")
    rp, ra, m = _f(rp), _f(ra), _f(m)
    if not (0 < rp < ra and m > 0):
        raise _error("BAD_INPUT", "0 < rp < ra y m > 0")
    a = (rp + ra) / 2
    e = (ra - rp) / (ra + rp)
    if L is not None:
        L = _f(L)
        C = L * L / (m * a * (1 - e * e))
        E_calc = -C / (2 * a)
        if E is not None and abs(_f(E) - E_calc) > 1e-9 * max(1.0, abs(E_calc)):
            raise _error("DISCREPANT", "E y L no son de la misma órbita")
        E = E_calc
    elif E is not None:
        E = _f(E)
        C = -2 * a * E
        if not C > 0:
            raise _error("BAD_INPUT", "ligada: E < 0")
        L = math.sqrt(m * C * a * (1 - e * e))
    else:
        raise _error("BAD_INPUT", "da E o L (una de las dos)")
    vp, va = L / (m * rp), L / (m * ra)
    Up, Ua = E - m * vp * vp / 2, E - m * va * va / 2
    # segundo camino: L constante en los ápsides ya es el control; además
    # U = −C/r en ambos (potencial newtoniano)
    if abs(Up + C / rp) > 1e-9 * max(1.0, abs(Up)) or \
            abs(Ua + C / ra) > 1e-9 * max(1.0, abs(Ua)):
        raise _error("DISCREPANT", "U no es −C/r en los ápsides")
    trace.verificacion("sen.orbita_energia",
                       f"a = {a:.6g} m, e = {e:.6g}, C = {C:.6g} J·m")
    return {"a": a, "e": e, "C": C, "L": L, "E": E, "vp": vp, "va": va,
            "Up": Up, "Ua": Ua}


# ---------------------------------------------------------------------------
# Maxwell-Boltzmann, Planck, Stefan (opcional D12)
# ---------------------------------------------------------------------------

def maxwell_boltzmann(m_kg, T, trace: Trace | None = None) -> dict:
    """f(v) Maxwell-Boltzmann: v_p, v_med, v_rms con ∫f = 1 y ⟨v²⟩."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.mb", "momentos gaussianos cerrados; la norma y ⟨v²⟩ por "
                 "cuadratura",
                 why="los tres promedios salen de la gaussiana y la "
                     "cuadratura comprueba que f es densidad (§4.19)")
    m, T = _f(m_kg), _f(T)
    if not (m > 0 and T > 0):
        raise _error("BAD_INPUT", "m, T > 0")
    kT = K_B * T
    vp = math.sqrt(2 * kT / m)
    vm = math.sqrt(8 * kT / (math.pi * m))
    vr = math.sqrt(3 * kT / m)
    f = lambda v: 4 * math.pi * (m / (2 * math.pi * kT)) ** 1.5 * v * v \
        * math.exp(-m * v * v / (2 * kT))
    N, v_max, s, s2 = 4000, 5 * vr, 0.0, 0.0
    for k in range(N):
        v = (k + 0.5) * v_max / N
        fv = f(v)
        s += fv
        s2 += v * v * fv
    s *= v_max / N
    s2 *= v_max / N
    if abs(s - 1) > 1e-4:
        raise _error("DISCREPANT", "f(v) no integra 1")
    if abs(s2 - vr * vr) > 1e-3 * vr * vr:
        raise _error("DISCREPANT", "⟨v²⟩ no da v_rms²")
    trace.verificacion("sen.mb_norma", f"∫f = 1; v_rms = {vr:.6g} m/s")
    return {"v_p": vp, "v_med": vm, "v_rms": vr}


def planck_integral(trace: Trace | None = None) -> dict:
    """∫₀^∞ x³/(eˣ−1)dx = π⁴/15 (numérica frente a exacta)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.planck", "cuadratura con cambio x = t/(1−t) frente a π⁴/15",
                 why="la integral de Planck cierra Stefan-Boltzmann y su valor "
                     "exacto es el control")
    N, s = 6000, 0.0
    for k in range(N):
        t = (k + 0.5) / N
        x = t / (1 - t)
        if x > 50:  # x³·e^{−x} < 1e−19: la cola no aporta
            continue
        s += x ** 3 / (math.exp(x) - 1) / (1 - t) ** 2
    num = s / N
    ex = math.pi ** 4 / 15
    if abs(num - ex) > 1e-4 * ex:
        raise _error("DISCREPANT", "la cuadratura no da π⁴/15")
    trace.verificacion("sen.planck_pi", f"∫ = {num:.6g} = π⁴/15")
    sigma = 2 * math.pi ** 5 * K_B ** 4 / (15 * C_LUZ ** 2 * H_P ** 3)
    return {"integral": num, "exacta": ex, "sigma": sigma}
