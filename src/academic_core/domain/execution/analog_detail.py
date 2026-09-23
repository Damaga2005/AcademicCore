# SPDX-License-Identifier: MIT
"""E0.3 explainable engineering completeness: the internals E0.2 declared unavailable.

Every trace is ONE real execution of a certified engine with its optional
observer attached (E0.3 engine contract: ``observer=None`` is inert). The
trace only shows what the engine handed to the observer; nothing is
re-solved or reconstructed. The E0.2 traces (``engineering.ac``,
``engineering.dc-sweep``, ``engineering.transient``, ``control.tf-point``,
``lab.run``) are unchanged; these are new operations.

- **AC with its complex MNA system** (``engineering.ac-mna``): ``solve_ac``
  (F8-D3) or ``solve_small_signal_ac`` (F8-J) hand over the unknown labels,
  A(jω) and b(jω) exactly as they are passed to the complex linear solver,
  and the solver outcome (status, mode, rank, x, residual norm, backward
  error). Steps: unknowns → A → b → the observed equation of each row →
  resolution → x → |x| and ∠x (the engine's ``phasors.magnitude/phase``).
  A is listed entry by entry up to ``MAX_MATRIX_FULL`` unknowns
  (``matrix_detail = FULL``); above that ``matrix_detail = OMITTED`` with
  its size, non-zero count and SHA-256 digest. CHECK: A·x = b (SYMBOLIC in
  exact rational mode, NUMERIC otherwise), |x|² = Re² + Im² (NUMERIC), the
  engine's KCL/KVL residuals (NUMERIC) and that the observed x is the
  reported solution (SYMBOLIC).
- **DC sweep point by point** (``engineering.dc-sweep-detail``): every
  point's Newton attempts as the sweep ran them: the initial guess the
  driver really handed over (warm: the previous point's solution; cold:
  the solver's zero vector), each Newton iteration (α, backtracking,
  residual norms, res_ok/step_ok, node voltages), the final state. All
  points are kept; grids above ``MAX_DETAIL_POINTS`` are refused before
  solving (the trace never drops a point).
- **Transient step by step** (``engineering.transient-detail``): the
  integration method, order and LTE constant the engine uses, x(0) and the
  dynamic states at t = 0, then every attempt in order: accepted steps
  (t_n, Δt, t_(n+1), x_n, predictor, x_(n+1), α and ‖F‖ of each Newton
  iteration, the LTE estimate of each dynamic state, the committed dynamic
  states (v_C, i_C / i_L, v_L), the methods used, the next Δt), rejected
  attempts (cause, Δt tried, retry Δt, LTE data) and the attempt that stops
  the integrator when it fails.
- **AC sweep** (``engineering.ac-sweep``): ``frequency_response`` (one
  independent D3 solve per frequency) point by point: f, status, H, |H|,
  ∠H. Each point is a direct complex solve: there are no internal
  iterations ("internal iteration details unavailable").
- **Transfer function** (``control.tf-analysis``): numerator, denominator,
  the engine's ``tf_to_zpk`` gain / zeros / poles when it provides them,
  ``evaluate(jω)`` in both forms, modulus and phase.
- **Virtual Lab run detail** (``lab.run-detail``): re-executes the run's
  engine on the run's own working circuit with the observer attached and
  CHECKs that the observed result is the recorded one (OP, DC_SWEEP,
  AC_POINT, TRANSIENT); AC_SWEEP is explained from the recorded sweep.
  Other kinds are UNSUPPORTED (declared). Replay stays the lab's own
  (result digest).

Boundedness: A(jω) is listed up to ``MAX_MATRIX_FULL`` unknowns; sweeps keep
every point up to ``MAX_DETAIL_POINTS`` (larger grids are refused before
solving). Optional detail events (Newton iterations of sweep points,
transient attempts) share a deterministic budget of ``MAX_DETAIL_EVENTS``
events and ``MAX_DETAIL_BYTES`` conservatively estimated bytes, which the
mandatory per-point events are charged against too; when it is exhausted the
trace carries one explicit WARNING ``TRACE_TRUNCATED`` with the number of
omitted events, and the summaries and CHECKs still cover the whole run. The
serialized trace therefore stays below the 8 MiB execution-trace/1 limit.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.execution import analog as ana
from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.domain.execution.verification import NONE, NUMERIC, SYMBOLIC, labelled
from academic_core.errors import UnsupportedError, ValidationError

AC_MNA = "engineering.ac-mna"
DC_SWEEP_DETAIL = "engineering.dc-sweep-detail"
TRANSIENT_DETAIL = "engineering.transient-detail"
AC_SWEEP = "engineering.ac-sweep"
TF_ANALYSIS = "control.tf-analysis"
LAB_DETAIL = "lab.run-detail"
OPERATIONS = (AC_MNA, DC_SWEEP_DETAIL, TRANSIENT_DETAIL, AC_SWEEP, TF_ANALYSIS)
AC_ENGINES = ("ac", "small-signal")

MAX_MATRIX_FULL = 8  # A(jω) entry by entry up to 8×8 (64 values per event); above: OMITTED + digest
MAX_VECTOR = 32  # x, |x|, ∠x listed per unknown up to 32 unknowns (2 values each)
MAX_DETAIL_POINTS = 500  # DC / AC sweep points: all are kept; larger grids are refused before solving
MAX_DETAIL_EVENTS = 4000  # optional detail events (iterations, transient attempts)
MAX_DETAIL_BYTES = 5_000_000  # conservative estimate of the serialized per-point/per-step events (codec: 8 MiB)
MAX_STATE = 6  # transient x_n / predictor / x_(n+1) listed per unknown up to 6 unknowns
MAX_LTE = 4  # LTE rows (4 values each) and dynamic states (2 values each) per transient event
TRUNCATED = "TRACE_TRUNCATED"
CX_TOL = Decimal("1e-40")  # |x|² = Re² + Im² (engine working precision: 50 digits)
AXB_TOL = Decimal("1e-30")  # A·x = b relative residual in HIGH_PRECISION mode
ZPK_TOL = Decimal("1e-20")  # H(jω) polynomial form vs ZPK form (root finding is iterative)
METHODS = {"BE": "Euler implícito (Backward Euler)", "TR": "Trapezoidal", "BDF2": "BDF2 (Gear, orden 2)"}


# ---------------------------------------------------------------- shared helpers

def _num(v) -> TraceValue:
    if isinstance(v, Fraction):
        return TraceValue.of_text(ana._frac(v))
    if v is None:
        return TraceValue.of_text("-")
    return ana._dec(v)


def _part(v) -> str:
    return ana._frac(v) if isinstance(v, Fraction) else str(v)


def _cx(z) -> str:
    """A complex entry as the engine holds it (Re, Im), exact text."""
    return f"{_part(z.re)} + j·({_part(z.im)})"[:512]


def _digest(rows) -> str:
    text = ";".join(",".join(_cx(z) for z in row) for row in rows)
    return hashlib.sha256(text.encode()).hexdigest()


def _lab(text: str) -> str:
    return nwt._label(text)


def _six(v: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 6
        return +v


class _Budget:
    """Deterministic budget for optional detail events (events and estimated bytes)."""

    def __init__(self):
        self.limits = (MAX_DETAIL_EVENTS, MAX_DETAIL_BYTES)
        self.events, self.size, self.omitted = MAX_DETAIL_EVENTS, MAX_DETAIL_BYTES, 0

    @staticmethod
    def _cost(title: str, values: tuple, texts: tuple) -> int:
        cost = 200 + len(title) + sum(len(t or "") for t in texts)  # event envelope, title, formula, why
        return cost + sum(len(n) + len(v.text or "") + len(str(v.number or "")) + 60 for n, v in values)

    def charge(self, title: str, values: tuple = (), *texts: str) -> None:
        """A mandatory event (point summary, initial guess): always emitted, its size is charged."""
        self.size -= self._cost(title, values, texts)

    def take(self, title: str, values: tuple = (), *texts: str) -> bool:
        """An optional detail event: emitted only while the budget lasts."""
        cost = self._cost(title, values, texts)
        if self.events <= 0 or cost > self.size:
            self.omitted += 1
            return False
        self.events -= 1
        self.size -= cost
        return True

    def close(self, rec: TraceRecorder, prev: str) -> str:
        if not self.omitted:
            return prev
        return rec.event(
            EventKind.WARNING, TRUNCATED, refs=(prev,),
            why=(f"Se alcanzó el límite de detalle de la traza ({self.limits[0]} eventos / {self.limits[1]} bytes "
                 "estimados): los eventos de detalle restantes se omiten. Los resúmenes y las comprobaciones cubren "
                 "la ejecución completa."),
            values=(("omitted_events", TraceValue.of_number(self.omitted)),
                    ("event_limit", TraceValue.of_number(self.limits[0])),
                    ("byte_limit", TraceValue.of_number(self.limits[1]))))


def _text_inputs(rec: TraceRecorder, fields: tuple, what: str) -> None:
    for name, v in fields:
        if not isinstance(v, str):
            raise _invalid("INVALID_INPUT", f"{name} must be text")
        rec.input(name, TraceValue.of_text(v), f"{what}: {name}")


# ---------------------------------------------------------------- AC with its complex MNA system

class _ACObserver:
    def __init__(self):
        self.system = None
        self.outcome = None

    def ac_system(self, unknowns, matrix, rhs, kind, frequency_hz, omega):
        self.system = (tuple(unknowns), tuple(matrix), tuple(rhs), kind, frequency_hz, omega)

    def ac_outcome(self, status, mode, rank, solution, residual_norm, backward_error):
        self.outcome = (status, mode, rank, solution, residual_norm, backward_error)


def _equation(labels: tuple, row: tuple, b) -> str:
    terms = [f"({_cx(a)})·{labels[j]}" for j, a in enumerate(row) if not a.is_zero_exact()]
    return (" + ".join(terms) or "0") + f" = {_cx(b)}"


def _axb(matrix: tuple, rhs: tuple, x: tuple, exact: bool) -> tuple:
    """max_i |(A·x − b)_i| relative to the row scale, from the observed A, b and x (exact or 80 digits)."""
    if exact:
        worst = Fraction(0)
        for row, b in zip(matrix, rhs):
            re = sum((a.re * v.re - a.im * v.im for a, v in zip(row, x)), Fraction(0)) - b.re
            im = sum((a.re * v.im + a.im * v.re for a, v in zip(row, x)), Fraction(0)) - b.im
            worst = max(worst, abs(re), abs(im))
        return worst, worst == 0
    worst = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 80
        for row, b in zip(matrix, rhs):
            re = sum((Decimal(a.re) * v.re - Decimal(a.im) * v.im for a, v in zip(row, x)), Decimal(0)) - b.re
            im = sum((Decimal(a.re) * v.im + Decimal(a.im) * v.re for a, v in zip(row, x)), Decimal(0)) - b.im
            scale = max([Decimal(1), abs(b.re), abs(b.im)] + [abs(a.re) * abs(v.re) + abs(a.im) * abs(v.im)
                                                                + abs(a.re) * abs(v.im) + abs(a.im) * abs(v.re)
                                                                for a, v in zip(row, x)])
            worst = max(worst, (abs(re) + abs(im)) / scale)
    return _six(worst), worst <= AXB_TOL


def _modulus_check(values: list) -> Decimal:
    worst = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 80
        for mag, re, im in values:
            re, im = (Decimal(re.numerator) / Decimal(re.denominator) if isinstance(re, Fraction) else re,
                      Decimal(im.numerator) / Decimal(im.denominator) if isinstance(im, Fraction) else im)
            worst = max(worst, abs(mag * mag - (re * re + im * im)) / max(Decimal(1), mag * mag))
    return _six(worst)


def _ac_detail(rec: TraceRecorder, circuit, frequency, engine: str, read: str):
    """Run the AC engine once with the observer; emit the 9 pedagogical steps. Returns (solution, result event)."""
    from academic_core.domain.engineering.ac.phasors import magnitude, phase

    obs = _ACObserver()
    if engine == "ac":
        from academic_core.domain.engineering.ac.solver import solve_ac
        sol = solve_ac(circuit, frequency, observer=obs)
    else:
        from academic_core.domain.engineering.ac.small_signal import solve_small_signal_ac
        sol = solve_small_signal_ac(circuit, frequency, observer=obs)
    if obs.system is None:
        rec.event(EventKind.WARNING, "MNA matrix unavailable", refs=(read,),
                  why="El motor rechazó el circuito antes de ensamblar el sistema complejo; no se reconstruye.")
        raise ana._status_error(sol.status.value, sol.diagnostics or ("no system assembled",))
    labels, matrix, rhs, kind, f_hz, omega = obs.system
    n = len(labels)
    names = tuple(_lab(u) for u in labels)
    op = rec.event(EventKind.STEP, "Punto de operación AC", refs=(read,),
                   formula="s = jω, ω = 2π·f; fasores de pico, convención e^(+jωt)",
                   why=f"Frecuencia y pulsación con las que el motor ({engine}) ensambló el sistema.",
                   values=(("f", TraceValue.of_number(f_hz, "Hz")), ("omega", ana._dec(omega)),
                           ("engine", TraceValue.of_text("F8-D3 solve_ac" if engine == "ac" else
                                                         "F8-J solve_small_signal_ac")),
                           ("arithmetic", TraceValue.of_text(kind))))
    unk = rec.event(EventKind.STEP, "1. Incógnitas", refs=(op,),
                    formula="x = [tensiones de nodo; corrientes auxiliares de fuentes de tensión]",
                    why="Etiquetas de cada columna del sistema, leídas de los índices del propio problema.",
                    values=tuple((f"u.{k}", TraceValue.of_text(lab)) for k, lab in enumerate(labels[:64])))
    full = n <= MAX_MATRIX_FULL
    nonzero = sum(1 for row in matrix for a in row if not a.is_zero_exact())
    meta = (("matrix_detail", TraceValue.of_text("FULL" if full else "OMITTED")), ("size", TraceValue.of_number(n)),
            ("nonzero", TraceValue.of_number(nonzero)), ("digest", TraceValue.of_text(_digest(matrix))))
    a_id = rec.event(
        EventKind.STEP, "2. Matriz MNA compleja A(jω)" if full else "2. Matriz MNA compleja A(jω) (detalle omitido)",
        refs=(unk,), formula="A(jω)·x(jω) = b(jω)",
        why=("La matriz exacta que el motor pasó al resolvedor complejo (entradas Re + j·Im)." if full else
             f"Sistema {n}×{n} mayor que {MAX_MATRIX_FULL}×{MAX_MATRIX_FULL}: se registran tamaño, no nulos y digest "
             "SHA-256 de la matriz observada."),
        values=(tuple((f"A.{i}.{j}", TraceValue.of_text(_cx(matrix[i][j]))) for i in range(n) for j in range(n))
                if full else meta))
    a_id = rec.event(EventKind.VALUE, "Matriz: metadatos", refs=(a_id,),
                     why="Detalle mostrado (FULL / OMITTED), dimensión, entradas no nulas y SHA-256 de A observada.",
                     values=meta)
    b_full = n <= 64
    b_id = rec.event(EventKind.STEP, "3. Vector de excitación b(jω)", refs=(a_id,),
                     why="Término independiente observado (fuentes independientes).",
                     values=(tuple((f"b.{i}", TraceValue.of_text(_cx(v))) for i, v in enumerate(rhs)) if b_full else
                             (("detail", TraceValue.of_text("OMITTED")), ("digest", TraceValue.of_text(_digest((rhs,)))))))
    prev = b_id
    if full:
        for i in range(n):
            prev = rec.event(EventKind.STEP, f"4. Ecuación {i + 1}: fila de {labels[i]}"[:512], refs=(prev,),
                             formula=_equation(labels, matrix[i], rhs[i])[:512],
                             why="Contribuciones observadas: los coeficientes no nulos de la fila i de A(jω) y b_i.")
    else:
        prev = rec.event(EventKind.STEP, "4. Ecuaciones (detalle omitido)", refs=(prev,),
                         why=f"Las {n} filas no se listan una a una (límite {MAX_MATRIX_FULL}); ver digest de A.")
    status, mode, rank, x, res_norm, backward = obs.outcome
    solve_id = rec.event(EventKind.STEP, "5. Resolución del sistema complejo", refs=(prev,),
                         why="Resultado del resolvedor lineal complejo del motor (F8-D2).",
                         values=(("status", TraceValue.of_text(status)), ("numeric_mode", TraceValue.of_text(mode)),
                                 ("rank", TraceValue.of_number(rank) if rank is not None else TraceValue.of_text("-")),
                                 ("residual_norm", _num(res_norm)), ("backward_error", _num(backward))))
    if sol.status.value != "solved" or x is None:
        raise ana._status_error(sol.status.value, sol.diagnostics)
    shown = min(n, MAX_VECTOR)
    x_id = rec.event(EventKind.STEP, "6. Vector solución x(jω)", refs=(solve_id,),
                     why="La solución que devolvió el resolvedor, entrada por entrada (Re, Im).",
                     values=tuple(v for k in range(shown) for v in ((f"re.{names[k]}", _num(x[k].re)),
                                                                     (f"im.{names[k]}", _num(x[k].im)))))
    mags = [(magnitude(x[k]), x[k].re, x[k].im) for k in range(n)]
    m_id = rec.event(EventKind.STEP, "7. Magnitud |x|", refs=(x_id,), formula="|x| = √(Re² + Im²)",
                     why="Módulo de cada incógnita con phasors.magnitude del motor.",
                     values=tuple((f"abs.{names[k]}", ana._dec(mags[k][0])) for k in range(shown)))
    p_id = rec.event(EventKind.STEP, "8. Fase ∠x", refs=(m_id,), formula="∠x = atan2(Im, Re) en (−π, π] (rad)",
                     why="Fase de cada incógnita con phasors.phase del motor.",
                     values=tuple((f"arg.{names[k]}", ana._dec(phase(x[k]))) for k in range(shown)))
    res = rec.event(EventKind.RESULT, "Solución AC", refs=(p_id,),
                    values=(("digest", TraceValue.of_text(sol.digest or "-")), ("unknowns", TraceValue.of_number(n))),
                    result=TraceValue.of_text(f"SOLVED a {f_hz} Hz"))
    exact = mode == "exact"
    worst, ok = _axb(matrix, rhs, x, exact)
    rec.check("A·x = b con A, b y x observados", _num(worst), TraceValue.of_number(Decimal(0)), ok, refs=(res,),
              tolerance=None if exact else TraceValue.of_number(AXB_TOL),
              detail=labelled("aritmética racional exacta" if exact else
                              "residuo relativo máximo por fila, 80 dígitos", SYMBOLIC if exact else NUMERIC),
              title="9. Comprobación: A·x = b")
    rel = _modulus_check(mags)
    rec.check("|x|² = Re² + Im² para cada incógnita", TraceValue.of_number(rel), TraceValue.of_number(Decimal(0)),
              rel <= CX_TOL, refs=(res,), tolerance=TraceValue.of_number(CX_TOL),
              detail=labelled("módulos del motor frente a Re² + Im² (80 dígitos)", NUMERIC),
              title="9. Comprobación: magnitud")
    node_of = {nv.node: nv.phasor for nv in sol.node_voltages}
    same = all(node_of.get(lab[2:-1]) == x[k] for k, lab in enumerate(labels) if lab.startswith("V("))
    rec.check("x observado = fasores de nodo del resultado", TraceValue.of_text("sí" if same else "no"),
              TraceValue.of_text("sí"), same, refs=(res,),
              detail=labelled("igualdad exacta de los valores observados y los publicados", SYMBOLIC),
              title="9. Comprobación: la solución observada es la publicada")
    for name, value in (("KCL", sol.kcl_max_residual), ("KVL", sol.kvl_max_residual)):
        if value is None:
            continue
        rec.check(f"residuo {name} máximo del solver", ana._dec(value), TraceValue.of_number(Decimal(0)),
                  value <= Decimal("1e-20"), refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-20")),
                  detail=labelled(f"residuo {name} calculado por el motor", NUMERIC), title=f"9. Comprobación: {name}")
    return sol, res


def explain_ac_mna(spec: str, frequency: str, engine: str = "ac", **limits) -> ExecutionTrace:
    rec = TraceRecorder(AC_MNA)
    ids = ana._circuit(rec, spec, limits)
    _text_inputs(rec, (("frequency", frequency), ("engine", engine)), "AC")
    try:
        if engine not in AC_ENGINES:
            raise _invalid("INVALID_INPUT", f"engine must be one of {', '.join(AC_ENGINES)}")
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        _ac_detail(rec, circuit, frequency, engine, read)
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- DC sweep point by point

class _SweepObserver:
    """Sweep driver calls + the Newton calls of each attempt, grouped per attempt (immutable snapshots)."""

    def __init__(self):
        self.attempts: list = []
        self.unknowns: tuple = ()
        self.nodes: tuple = ()

    def sweep_attempt(self, index, label, parameters, attempt, x_init):
        self.attempts.append(dict(index=index, label=label, params=tuple(parameters), kind=attempt,
                                  x_init=None if x_init is None else tuple(x_init), start=None, iterations=[],
                                  failure=None, end=None))

    def sweep_attempt_end(self, index, attempt, status, iterations, x_final):
        self.attempts[-1]["end"] = (status, iterations, x_final)

    def newton_start(self, nodes, x, kcl, aux, scale, *, unknowns=(), **_facts):
        self.nodes, self.unknowns = tuple(nodes), tuple(unknowns)
        self.attempts[-1]["start"] = (tuple(x), kcl, aux)

    def newton_iteration(self, it, alpha, halvings, step_peak, x, kcl, aux, scale, res_ok, step_ok, **_facts):
        self.attempts[-1]["iterations"].append((it, alpha, halvings, step_peak, tuple(x), kcl, aux, res_ok, step_ok))

    def newton_failed(self, it, reason, trials):
        self.attempts[-1]["failure"] = (it, reason)


def _vector(prefix: str, labels: tuple, vec: tuple, limit: int = 16) -> tuple:
    return tuple((f"{prefix}.{_lab(lab)}", ana._dec(v)) for lab, v in list(zip(labels, vec))[:limit])


def _sweep_detail(rec: TraceRecorder, circuit, config, read: str, budget: _Budget):
    from academic_core.domain.engineering.mna.analysis import expand_grid, solve_dc_sweep

    try:
        count = len(expand_grid(config.grid))
    except ValueError:
        count = 0  # the engine reports the grid error itself below
    if count > MAX_DETAIL_POINTS:
        raise _invalid("INVALID_LIMIT", f"the detailed sweep keeps every point: at most {MAX_DETAIL_POINTS} points "
                                        f"(grid has {count})")
    grid = rec.event(EventKind.STEP, "Barrido DC", refs=(read,),
                     formula=f"{config.target.key} recorre {count} valores; arranque en caliente: "
                             f"{'sí' if config.warm_start else 'no'}",
                     why=("El motor F8-M fija el parámetro en cada punto y resuelve el punto de operación con Newton "
                          "(F8-H). Con arranque en caliente, el punto k parte de la solución del punto k−1 si convergió."),
                     values=(("points", TraceValue.of_number(count)),
                             ("warm_start", TraceValue.of_text("sí" if config.warm_start else "no"))))
    obs = _SweepObserver()
    result = solve_dc_sweep(circuit, config, observer=obs)
    prev, points = grid, []
    by_index: dict = {}
    for a in obs.attempts:
        by_index.setdefault(a["index"], []).append(a)
    previous_final = None
    warm_ok = True
    iters_ok = True
    for p in result.points:
        attempts = by_index.get(p.index, [])
        for a in attempts:
            warm = a["x_init"] is not None
            if warm and a["x_init"] != previous_final:
                warm_ok = False
            values = [("attempt", TraceValue.of_text(a["kind"])),
                      ("initial_guess", TraceValue.of_text("solución del punto anterior" if warm else
                                                           "vector nulo del solver (arranque en frío)"))]
            values += list(_vector("x0", obs.unknowns, a["x_init"])) if warm else []
            title = f"Punto {p.index} · arranque {'en caliente' if warm else 'en frío'}"
            formula = "x₀ = x*(punto k−1)" if warm else "x₀ = 0"
            why = ("El driver del barrido entrega al solver la solución convergida del punto anterior." if warm else
                   "El driver del barrido no reutiliza ninguna solución: parte del cero.")
            budget.charge(title, tuple(values[:64]), formula, why)
            prev = rec.event(EventKind.STEP, title, refs=(prev,), formula=formula, why=why, values=tuple(values[:64]))
            for it, alpha, halvings, peak, x, kcl, aux, res_ok, step_ok in a["iterations"]:
                v = (("alpha", TraceValue.of_number(alpha)), ("halvings", TraceValue.of_number(halvings)),
                     ("step_peak", TraceValue.of_number(peak)), ("kcl_residual", TraceValue.of_number(kcl, "A")),
                     ("aux_residual", TraceValue.of_number(aux, "V")),
                     ("res_ok", TraceValue.of_text("sí" if res_ok else "no")),
                     ("step_ok", TraceValue.of_text("sí" if step_ok else "no"))) + _vector("V", obs.nodes, x)
                title = f"Punto {p.index} · iteración {it} de Newton"
                formula = "x_(k+1) = x_k + α·Δx con J(x_k)·Δx = −F(x_k)"
                if budget.take(title, v, formula):
                    prev = rec.event(EventKind.STEP, title, refs=(prev,), formula=formula, values=v)
            if a["failure"] is not None:
                prev = rec.event(EventKind.WARNING, f"Punto {p.index} · intento {a['kind']} fallido", refs=(prev,),
                                 why=f"El solver informa: {a['failure'][1]}"[:512])
        final = attempts[-1] if attempts else None
        if final is not None and p.iterations is not None and len(final["iterations"]) != p.iterations:
            iters_ok = False
        values = [("status", TraceValue.of_text(p.status.value)), ("init_mode", TraceValue.of_text(p.init_mode)),
                  ("attempts", TraceValue.of_number(len(attempts))),
                  ("iterations", TraceValue.of_number(p.iterations) if p.iterations is not None
                   else TraceValue.of_text("-"))]
        values += [(f"param.{_lab(k)}", ana._dec(v)) for k, v in p.parameters][:4]
        values += [(f"V.{_lab(k)}", ana._dec(v)) for k, v in sorted(p.node_voltages.items())][:ana.MAX_ENTITIES]
        values += [(f"obs.{_lab(k)}", ana._dec(v)) for k, v in sorted(p.observables.items())][:16]
        title = f"Punto {p.index}: {p.label}"[:512]
        why = ("Estado final del punto (solución convergida)." if p.ok else
               f"El punto no convergió: {p.diagnostic or p.status.value}"[:512])
        budget.charge(title, tuple(values[:64]), why)
        prev = rec.event(EventKind.STEP if p.ok else EventKind.WARNING, title, refs=(prev,), why=why,
                         values=tuple(values[:64]))
        points.append(prev)
        previous_final = final["end"][2] if final is not None and final["end"] is not None and p.ok else None
    prev = budget.close(rec, prev)
    return result, points, prev, dict(warm_ok=warm_ok, iters_ok=iters_ok, attempts=obs.attempts)


def _sweep_checks(rec: TraceRecorder, result, facts: dict, res: str) -> None:
    rec.check("puntos en la traza = puntos del motor", TraceValue.of_number(len(result.points)),
              TraceValue.of_number(len({a["index"] for a in facts["attempts"]}) if facts["attempts"] else 0),
              len(result.points) == len({a["index"] for a in facts["attempts"]}), refs=(res,),
              detail=labelled("todos los puntos se conservan (conteo exacto)", SYMBOLIC),
              title="Comprobación: todos los puntos")
    warm = [a for a in facts["attempts"] if a["x_init"] is not None]
    rec.check("cada arranque en caliente parte de la solución anterior observada",
              TraceValue.of_text("sí" if facts["warm_ok"] else "no"), TraceValue.of_text("sí"),
              facts["warm_ok"] if warm else None, refs=(res,),
              detail=labelled("igualdad exacta de x₀ y la solución final del punto anterior",
                              SYMBOLIC if warm else NONE), title="Comprobación: arranque en caliente")
    rec.check("iteraciones observadas = iteraciones informadas por el barrido",
              TraceValue.of_text("sí" if facts["iters_ok"] else "no"), TraceValue.of_text("sí"), facts["iters_ok"],
              refs=(res,), detail=labelled("igualdad exacta de enteros por punto", SYMBOLIC),
              title="Comprobación: iteraciones por punto")
    ok = all(p.ok for p in result.points)
    rec.check("todos los puntos convergieron", TraceValue.of_number(sum(1 for p in result.points if p.ok)),
              TraceValue.of_number(len(result.points)), ok, refs=(res,),
              detail=labelled("estado de cada punto informado por el motor", SYMBOLIC), title="Comprobación: puntos")


def explain_dc_sweep_detail(spec: str, source: str, start: str, stop: str, step: str, observe: str = "",
                            warm_start: bool = True, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.analysis import GridSpec, ObservableSpec, ParamAddress, SweepConfig

    rec = TraceRecorder(DC_SWEEP_DETAIL)
    ids = ana._circuit(rec, spec, limits)
    _text_inputs(rec, (("source", source), ("start", start), ("stop", stop), ("step", step), ("observe", observe)),
                 "Barrido")
    if not isinstance(warm_start, bool):
        raise _invalid("INVALID_INPUT", "warm_start must be a bool")
    rec.input("warm_start", TraceValue.of_text("true" if warm_start else "false"), "Barrido: arranque en caliente")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        nodes = tuple(n.strip() for n in observe.split(",") if n.strip())
        config = SweepConfig(ParamAddress(source, "value"),
                             GridSpec.linear(ana._decimal(start, "start"), ana._decimal(stop, "stop"),
                                             ana._decimal(step, "step")),
                             tuple(ObservableSpec("node_voltage", n) for n in nodes), warm_start=warm_start)
        result, points, last, facts = _sweep_detail(rec, circuit, config, read, _Budget())
        if result.status.value != "completed":
            raise ana._status_error(result.status.value, result.diagnostics or ("sweep did not complete",))
        res = rec.event(EventKind.RESULT, "Barrido completado", refs=(last,),
                        values=(("points", TraceValue.of_number(len(result.points))),
                                ("digest", TraceValue.of_text(result.digest or "-"))),
                        result=TraceValue.of_text(f"{result.status.value}: {len(result.points)} puntos"))
        _sweep_checks(rec, result, facts, res)
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- transient step by step

class _TransientObserver:
    def __init__(self):
        self.start = None
        self.attempts: list = []

    def transient_start(self, method, order, lte_constant, adaptive, unknowns, x0, dynamic, tstop, h_init, h_min,
                        h_max, reltol, abstol):
        self.start = dict(method=method, order=order, c=lte_constant, adaptive=adaptive, unknowns=tuple(unknowns),
                          x0=tuple(x0), dynamic=tuple(dynamic), tstop=tstop, h_init=h_init, h_min=h_min,
                          h_max=h_max, reltol=reltol, abstol=abstol)

    def transient_reject(self, cause, t_n, h, t_next, retry_h, e_max, lte, iterations, newton=()):
        self.attempts.append(("reject", dict(cause=cause, t_n=t_n, h=h, t_next=t_next, retry_h=retry_h, e_max=e_max,
                                             lte=tuple(lte), iterations=iterations, newton=tuple(newton))))

    def transient_accept(self, index, t_n, h, t_next, x_n, predictor, x_next, iterations, kcl, aux, e_max, lte,
                         methods, next_h, forced, dynamic, newton=()):
        self.attempts.append(("accept", dict(index=index, t_n=t_n, h=h, t_next=t_next, x_n=tuple(x_n),
                                             predictor=tuple(predictor), x_next=tuple(x_next), iterations=iterations,
                                             kcl=kcl, aux=aux, e_max=e_max, lte=tuple(lte), methods=tuple(methods),
                                             next_h=next_h, forced=forced, dynamic=tuple(dynamic),
                                             newton=tuple(newton))))


_STEP_FORMULA = "x_pred por extrapolación; Newton en t_(n+1); E = máx LTE normalizado; aceptar si E ≤ 1"
_STEP_WHY = ("Paso comprometido por el integrador: estado previo, predicción, corrector (Newton), error local estimado "
             "para cada estado dinámico y el Δt que el controlador eligió para el siguiente paso. En BDF2/TR el "
             "arranque puede usar BE (methods).")
_CAUSE = {"residual_nonfinite": "residuo no finito en la predicción y en x_n",
          "newton_failed": "Newton no convergió en el paso",
          "lte_nonfinite": "estimación LTE no finita",
          "lte": "error local de truncamiento E > 1",
          "singular_jacobian": "jacobiano singular"}


def _lte_values(lte: tuple) -> tuple:
    out = []
    for ref, kind, y_old, y_pred, y_new, e in lte[:MAX_LTE]:
        name = f"{kind}.{_lab(ref)}"
        out += [(f"y_old.{name}", ana._dec(y_old)), (f"y_pred.{name}", ana._dec(y_pred)),
                (f"y_new.{name}", ana._dec(y_new)), (f"E.{name}", _num(e))]
    return tuple(out)


def _newton_values(newton: tuple) -> tuple:
    """The Newton iterations of one attempt as the integrator ran them: α and the residual norm per iteration."""
    if not newton:
        return ()
    alphas = ", ".join(str(n[1]) for n in newton)
    norms = ", ".join(str(max(n[3], n[4])) for n in newton)
    return (("newton_alpha", TraceValue.of_text(alphas[:512])), ("newton_residual", TraceValue.of_text(norms[:512])))


def _dynamic_values(dynamic: tuple) -> tuple:
    out = []
    for ref, kind, a, b in dynamic[:MAX_LTE]:
        names = ("v", "i") if kind == "C" else ("i", "v")
        out += [(f"{names[0]}.{kind}.{_lab(ref)}", ana._dec(a)), (f"{names[1]}.{kind}.{_lab(ref)}", ana._dec(b))]
    return tuple(out)


def _transient_detail(rec: TraceRecorder, circuit, config, read: str, budget: _Budget):
    from academic_core.domain.engineering.mna.transient import solve_transient

    obs = _TransientObserver()
    result = solve_transient(circuit, config, observer=obs)
    prev = read
    if obs.start is None:
        rec.event(EventKind.WARNING, "integration method details unavailable", refs=(read,),
                  why="El motor se detuvo antes de iniciar la integración; no hay pasos que mostrar.")
        raise ana._status_error(result.status.value, result.diagnostics)
    s = obs.start
    labels = s["unknowns"]
    cfg = rec.event(
        EventKind.STEP, f"Método de integración: {METHODS.get(s['method'], s['method'])}", refs=(read,),
        formula=f"orden p = {s['order']}; LTE ≈ |y_(n+1) − y_pred| / C con C = {s['c']}; "
                f"paso {'adaptativo' if s['adaptive'] else 'fijo'}",
        why=("Datos expuestos por el integrador F8-L: método, orden, constante del estimador LTE (predictor frente a "
             "corrector) y cotas de Δt."),
        values=(("method", TraceValue.of_text(s["method"])), ("order", TraceValue.of_number(s["order"])),
                ("lte_constant", ana._dec(s["c"])), ("adaptive", TraceValue.of_text("sí" if s["adaptive"] else "no")),
                ("tstop", ana._dec(s["tstop"])), ("h_init", ana._dec(s["h_init"])), ("h_min", ana._dec(s["h_min"])),
                ("h_max", ana._dec(s["h_max"])), ("reltol", ana._dec(s["reltol"])), ("abstol", ana._dec(s["abstol"]))))
    dyn = []
    for ref, kind, a, b in s["dynamic"][:12]:
        names = ("v", "i") if kind == "C" else ("i", "v")
        dyn += [(f"{names[0]}.{kind}.{_lab(ref)}", ana._dec(a)), (f"{names[1]}.{kind}.{_lab(ref)}", ana._dec(b))]
    prev = rec.event(EventKind.STEP, "Estado inicial t = 0", refs=(cfg,),
                     why=("Solución DC de t = 0 que calculó el motor (condiciones iniciales) y estado dinámico de cada "
                          "condensador (v_C, i_C) y bobina (i_L, v_L)."),
                     values=(_vector("x0", labels, s["x0"], MAX_VECTOR) + tuple(dyn))[:64])
    counts = dict(accept=0, reject=0, newton=0)
    decisions_ok = True
    chain_ok = True
    last_x = s["x0"]
    for kind, a in obs.attempts:
        counts[kind] += 1
        counts["newton"] += a["iterations"]
        if kind == "accept":
            chain_ok = chain_ok and a["x_n"] == last_x
            last_x = a["x_next"]
            if s["adaptive"] and not a["forced"] and a["e_max"] is not None and a["e_max"] > 1:
                decisions_ok = False
            n = min(len(labels), MAX_STATE)
            values = (("t_n", ana._dec(a["t_n"])), ("dt", ana._dec(a["h"])), ("t_next", ana._dec(a["t_next"])),
                      ("methods", TraceValue.of_text(", ".join(a["methods"]))),
                      ("newton_iterations", TraceValue.of_number(a["iterations"])),
                      ("kcl_residual", ana._dec(a["kcl"])), ("aux_residual", ana._dec(a["aux"])),
                      ("E_max", _num(a["e_max"])),
                      ("decision", TraceValue.of_text("aceptado (paso final forzado)" if a["forced"] else "aceptado")),
                      ("next_dt", _num(a["next_h"]))) + _newton_values(a["newton"])
            values += _vector("x_n", labels, a["x_n"], n) + _vector("pred", labels, a["predictor"], n)
            values += _vector("x_next", labels, a["x_next"], n) + _lte_values(a["lte"])
            values += _dynamic_values(a["dynamic"])
            title = f"Paso {a['index']}: t = {a['t_n']} → {a['t_next']} s"[:512]  # index of t_(n+1) in times
            if budget.take(title, values[:64], _STEP_FORMULA, _STEP_WHY):
                prev = rec.event(EventKind.STEP, title, refs=(prev,), formula=_STEP_FORMULA, why=_STEP_WHY,
                                 values=values[:64])
        else:
            if a["cause"] == "lte" and a["e_max"] is not None and a["e_max"] <= 1:
                decisions_ok = False
            stop = a["retry_h"] is None
            values = (("cause", TraceValue.of_text(a["cause"])), ("t_n", ana._dec(a["t_n"])),
                      ("dt_tried", ana._dec(a["h"])), ("t_next", ana._dec(a["t_next"])),
                      ("retry_dt", _num(a["retry_h"])), ("E_max", _num(a["e_max"])),
                      ("newton_iterations", TraceValue.of_number(a["iterations"])),
                      ("decision", TraceValue.of_text("la integración se detiene" if stop else "rechazado")))
            values += _newton_values(a["newton"]) + _lte_values(a["lte"])
            title = (f"Intento fallido en t = {a['t_n']} s (Δt = {a['h']}): la integración se detiene" if stop else
                     f"Intento rechazado en t = {a['t_n']} s (Δt = {a['h']})")[:512]
            why = (f"El integrador no puede continuar: {_CAUSE.get(a['cause'], a['cause'])} y no hay Δt admisible."
                   if stop else
                   f"El integrador rechaza el intento: {_CAUSE.get(a['cause'], a['cause'])}; la historia comprometida "
                   "no cambia y se reintenta con retry_dt.")
            if budget.take(title, values[:64], why):
                prev = rec.event(EventKind.DECISION, title, refs=(prev,), why=why, values=values[:64])
    prev = budget.close(rec, prev)
    return result, prev, dict(counts=counts, decisions_ok=decisions_ok, chain_ok=chain_ok, obs=obs)


def _transient_checks(rec: TraceRecorder, result, config, facts: dict, res: str) -> None:
    counts, obs = facts["counts"], facts["obs"]
    stats = result.stats or {}
    accepts = [a for k, a in obs.attempts if k == "accept"]
    same_t = [a["t_next"] for a in accepts] == list(result.times[1:])
    rec.check("pasos observados = instantes comprometidos del motor", TraceValue.of_number(counts["accept"]),
              TraceValue.of_number(len(result.times) - 1), same_t, refs=(res,),
              detail=labelled("igualdad exacta de los t_(n+1) observados y result.times", SYMBOLIC),
              title="Comprobación: secuencia temporal")
    labels = obs.start["unknowns"]
    same_x = all(a["x_next"][k] == result.node_trajectories[lab[2:-1]][i + 1]
                 for i, a in enumerate(accepts) for k, lab in enumerate(labels) if lab.startswith("V("))
    rec.check("estados observados = trayectorias del motor", TraceValue.of_text("sí" if same_x else "no"),
              TraceValue.of_text("sí"), same_x, refs=(res,),
              detail=labelled("igualdad exacta de x_(n+1) y node_trajectories", SYMBOLIC),
              title="Comprobación: secuencia de estados")
    rec.check("x_n de cada paso = x_(n+1) del anterior", TraceValue.of_text("sí" if facts["chain_ok"] else "no"),
              TraceValue.of_text("sí"), facts["chain_ok"], refs=(res,),
              detail=labelled("igualdad exacta de los vectores observados", SYMBOLIC),
              title="Comprobación: continuidad")
    rec.check("rechazos observados = rechazos del motor", TraceValue.of_number(counts["reject"]),
              TraceValue.of_number(stats.get("rejected", 0)), counts["reject"] == stats.get("rejected"), refs=(res,),
              detail=labelled("igualdad exacta de enteros (stats.rejected)", SYMBOLIC),
              title="Comprobación: rechazos")
    rec.check("iteraciones de Newton observadas = stats.newton_total", TraceValue.of_number(counts["newton"]),
              TraceValue.of_number(stats.get("newton_total", 0)), counts["newton"] == stats.get("newton_total"),
              refs=(res,), detail=labelled("igualdad exacta de enteros", SYMBOLIC),
              title="Comprobación: iteraciones de Newton")
    rec.check("cada decisión LTE es coherente con E (aceptado ⇒ E ≤ 1, rechazado por LTE ⇒ E > 1)",
              TraceValue.of_text("sí" if facts["decisions_ok"] else "no"), TraceValue.of_text("sí"),
              facts["decisions_ok"] if obs.start["adaptive"] else None, refs=(res,),
              detail=labelled("comparación exacta de los E observados con 1",
                              SYMBOLIC if obs.start["adaptive"] else NONE),
              title="Comprobación: decisiones del control de paso")
    increasing = all(a < b for a, b in zip(result.times, result.times[1:]))
    rec.check("instantes estrictamente crecientes y t_final = tstop",
              TraceValue.of_number(result.times[-1], "s"), TraceValue.of_number(config.tstop, "s"),
              increasing and result.times[-1] == config.tstop, refs=(res,),
              detail=labelled("comparación exacta de los instantes del motor", SYMBOLIC),
              title="Comprobación: historia temporal")


def explain_transient_detail(spec: str, method: str, tstop: str, h_init: str, h_min: str, h_max: str,
                             reltol: str = "1e-3", abstol: str = "1e-6", adaptive: bool = True,
                             **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.transient import TransientConfig

    rec = TraceRecorder(TRANSIENT_DETAIL)
    ids = ana._circuit(rec, spec, limits)
    fields = (("method", method), ("tstop", tstop), ("h_init", h_init), ("h_min", h_min), ("h_max", h_max),
              ("reltol", reltol), ("abstol", abstol))
    _text_inputs(rec, fields, "Transitorio")
    if not isinstance(adaptive, bool):
        raise _invalid("INVALID_INPUT", "adaptive must be a bool")
    rec.input("adaptive", TraceValue.of_text("true" if adaptive else "false"), "Transitorio: paso adaptativo")
    try:
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        config = TransientConfig(method, *(ana._decimal(v, n) for n, v in fields[1:]), adaptive=adaptive)
        result, last, facts = _transient_detail(rec, circuit, config, read, _Budget())
        if result.status.value != "completed":
            raise ana._status_error(result.status.value, result.diagnostics)
        res = rec.event(EventKind.RESULT, "Transitorio completado", refs=(last,),
                        values=(("samples", TraceValue.of_number(len(result.times))),
                                ("accepted", TraceValue.of_number(facts["counts"]["accept"])),
                                ("rejected", TraceValue.of_number(facts["counts"]["reject"]))),
                        result=TraceValue.of_text(f"COMPLETED: {len(result.times)} instantes"))
        _transient_checks(rec, result, config, facts, res)
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- AC sweep point by point

def _ac_sweep_points(rec: TraceRecorder, sweep, prev: str):
    rows = []
    for k, p in enumerate(sweep.points):
        values = [("f", TraceValue.of_number(p.frequency.to_base(), "Hz")),
                  ("status", TraceValue.of_text(p.status.value))]
        value = p.value.value if p.value is not None else None  # TransferFunction / ImpedanceValue phasor
        if value is not None:
            mag, arg = p.value.magnitude(), p.value.phase()
            rows.append((mag, value.re, value.im))
            values += [("re_H", _num(value.re)), ("im_H", _num(value.im)), ("abs_H", ana._dec(mag)),
                       ("arg_H", ana._dec(arg))]
        title = f"Frecuencia {k}: {p.frequency.format()}"[:512]
        prev = rec.event(EventKind.STEP if value is not None else EventKind.WARNING, title, refs=(prev,),
                         why=("Punto independiente: solve_ac a esta frecuencia y la cantidad pedida sobre su "
                              "solución (H = salida/entrada)." if value is not None else
                              f"Punto no resuelto: {p.diagnostic}"[:512]),
                         values=tuple(values))
    return prev, rows


def _ac_sweep_checks(rec: TraceRecorder, sweep, frequencies, rows: list, res: str) -> None:
    same = [p.frequency.to_base() for p in sweep.points] == [f.to_base() for f in frequencies]
    rec.check("frecuencias en la traza = frecuencias pedidas, en orden", TraceValue.of_number(len(sweep.points)),
              TraceValue.of_number(len(frequencies)), same, refs=(res,),
              detail=labelled("igualdad exacta de la secuencia de frecuencias", SYMBOLIC),
              title="Comprobación: secuencia de frecuencias")
    rel = _modulus_check(rows)
    rec.check("|H|² = Re² + Im² en cada punto", TraceValue.of_number(rel), TraceValue.of_number(Decimal(0)),
              rel <= CX_TOL if rows else None, refs=(res,), tolerance=TraceValue.of_number(CX_TOL),
              detail=labelled("módulos del motor frente a Re² + Im² (80 dígitos)", NUMERIC if rows else NONE),
              title="Comprobación: magnitud")
    solved = sum(1 for p in sweep.points if p.value is not None)
    rec.check("todos los puntos resueltos", TraceValue.of_number(solved), TraceValue.of_number(len(sweep.points)),
              solved == len(sweep.points), refs=(res,),
              detail=labelled("estado de cada punto informado por el motor", SYMBOLIC), title="Comprobación: puntos")


def _parse_frequencies(text: str) -> list:
    from academic_core.domain.engineering.units import FREQUENCY, UnitError, parse_quantity

    items = [t.strip() for t in text.split(",") if t.strip()]
    if not items or len(items) > MAX_DETAIL_POINTS:
        raise _invalid("INVALID_LIMIT", f"give 1..{MAX_DETAIL_POINTS} frequencies separated by commas")
    out = []
    for t in items:
        try:
            q = parse_quantity(t)
        except UnitError:
            raise _invalid("INVALID_INPUT", f"bad frequency {t[:32]!r}") from None
        if q.dimension != FREQUENCY:
            raise _invalid("INVALID_INPUT", f"{t[:32]!r} is not a frequency")
        out.append(q)
    return out


def explain_ac_sweep(spec: str, source: str, output_p: str, output_n: str, frequencies: str,
                     **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.ac.response import ResponseDefinition, frequency_response, voltage_between

    rec = TraceRecorder(AC_SWEEP)
    ids = ana._circuit(rec, spec, limits)
    _text_inputs(rec, (("source", source), ("output_p", output_p), ("output_n", output_n),
                       ("frequencies", frequencies)), "Barrido AC")
    try:
        freqs = _parse_frequencies(frequencies)
        circuit, read = ana._read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        src = {c.ref.upper(): c for c in circuit.components}.get(source.upper())
        if src is None or src.type.upper() not in ("V", "I"):
            raise _invalid("INVALID_INPUT", f"input source {source[:16]!r} must be a V/I source of the circuit")
        plus, minus = src.pins.get("+", src.pins.get("1", "")), src.pins.get("-", src.pins.get("2", ""))
        definition = ResponseDefinition("transfer", (voltage_between(plus, minus),
                                                     voltage_between(output_p, output_n), src.ref))
        cfg = rec.event(EventKind.STEP, "Barrido en frecuencia", refs=(read,),
                        formula=f"H(jω) = V({output_p}, {output_n}) / V({plus}, {minus}) con {src.ref} como entrada",
                        why=("frequency_response (F8-D5): para cada frecuencia, un punto de operación AC nuevo, una "
                             "resolución D3 independiente y la función de transferencia de red sobre su solución."),
                        values=(("points", TraceValue.of_number(len(freqs))),))
        sweep = frequency_response(circuit, definition, freqs)
        last, rows = _ac_sweep_points(rec, sweep, cfg)
        last = rec.event(EventKind.WARNING, "internal iteration details unavailable", refs=(last,),
                         why=("Cada punto es una resolución directa del sistema complejo (sin iteraciones). La matriz "
                              "A(jω) de un punto concreto se explica con engineering.ac-mna a esa frecuencia."))
        res = rec.event(EventKind.RESULT, "Respuesta en frecuencia", refs=(last,),
                        values=(("points", TraceValue.of_number(len(sweep.points))),
                                ("digest", TraceValue.of_text(sweep.digest))),
                        result=TraceValue.of_text(f"{sweep.status}: {len(sweep.points)} frecuencias"))
        _ac_sweep_checks(rec, sweep, freqs, rows, res)
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- transfer function (polynomial + ZPK forms)

def explain_tf_analysis(numerator: str, denominator: str, omega: str) -> ExecutionTrace:
    from academic_core.domain.engineering.control.errors import ControlError
    from academic_core.domain.engineering.control.margins import _wrapped_phase_deg
    from academic_core.domain.engineering.control.tf import make_tf, tf_to_zpk
    from academic_core.domain.engineering.math import DecimalComplex
    from academic_core.domain.execution.control import _coeffs, _poly_text

    rec = TraceRecorder(TF_ANALYSIS)
    _text_inputs(rec, (("numerator", numerator), ("denominator", denominator), ("omega", omega)), "H(s)")
    try:
        num, den = _coeffs(numerator, "numerator"), _coeffs(denominator, "denominator")
        w = ana._decimal(omega, "omega")
        h = make_tf(num, den)
        tf = rec.event(EventKind.STEP, "Función de transferencia", refs=(rec.last,),
                       formula=f"H(s) = ({_poly_text(num)}) / ({_poly_text(den)})",
                       why="Coeficientes (potencias descendentes) del TransferFunctionTF del motor.",
                       values=(tuple((f"num.{k}", ana._dec(c)) for k, c in enumerate(h.num.coeffs))
                               + tuple((f"den.{k}", ana._dec(c)) for k, c in enumerate(h.den.coeffs)))[:64])
        zpk = None
        try:
            zpk = tf_to_zpk(h)
        except ControlError as exc:
            zp = rec.event(EventKind.WARNING, "Polos y ceros no disponibles", refs=(tf,),
                           why=f"tf_to_zpk del motor no los proporciona: {exc}"[:512])
        if zpk is not None:
            zp = rec.event(
                EventKind.STEP, "Polos y ceros (tf_to_zpk del motor)", refs=(tf,),
                formula="H(s) = k·Π(s − z_i) / Π(s − p_j)",
                why="Raíces que calculó el motor (Durand–Kerner) y la ganancia k = a_m / b_n.",
                values=((("gain", ana._dec(zpk.gain)),)
                        + tuple((f"zero.{k}", TraceValue.of_text(_cx(z))) for k, z in enumerate(zpk.zeros))
                        + tuple((f"pole.{k}", TraceValue.of_text(_cx(p))) for k, p in enumerate(zpk.poles)))[:64])
        s = DecimalComplex(Decimal(0), w)
        value = h.evaluate(s)
        ev = rec.event(EventKind.STEP, "Evaluación en s = jω", refs=(zp,), formula=f"H(j·{omega}) = N(jω)/D(jω)",
                       why="TransferFunctionTF.evaluate del motor (aritmética compleja Decimal).",
                       values=(("re", ana._dec(value.re)), ("im", ana._dec(value.im))))
        z_value = None
        if zpk is not None:
            z_value = zpk.evaluate(s)
            ev = rec.event(EventKind.STEP, "Evaluación en forma ZPK", refs=(ev,),
                           formula="k·Π(jω − z_i) / Π(jω − p_j)", why="ZPK.evaluate del motor.",
                           values=(("re", ana._dec(z_value.re)), ("im", ana._dec(z_value.im))))
        mag = value.modulus()
        ph = _wrapped_phase_deg(value)
        res = rec.event(EventKind.RESULT, "Módulo y fase", refs=(ev,),
                        formula="|H| = modulus();  ∠H en grados (motor F8-P)",
                        values=(("magnitude", ana._dec(mag)), ("phase_deg", ana._dec(ph))),
                        result=TraceValue.of_text(f"|H| = {mag}; ∠H = {ph}°"[:512]))
        rel = _modulus_check([(mag, value.re, value.im)])
        rec.check("|H|² = Re² + Im²", TraceValue.of_number(rel), TraceValue.of_number(Decimal(0)), rel <= CX_TOL,
                  refs=(res,), tolerance=TraceValue.of_number(CX_TOL),
                  detail=labelled("con los valores que devolvió el motor", NUMERIC), title="Comprobación: módulo")
        if z_value is not None:
            with localcontext() as ctx:
                ctx.prec = 80
                diff = (abs(value.re - z_value.re) + abs(value.im - z_value.im)) / max(Decimal(1), mag)
            diff = _six(diff)
            rec.check("H(jω) polinómica = H(jω) en forma ZPK", TraceValue.of_number(diff),
                      TraceValue.of_number(Decimal(0)), diff <= ZPK_TOL, refs=(res,),
                      tolerance=TraceValue.of_number(ZPK_TOL),
                      detail=labelled("dos evaluaciones del motor (las raíces son aproximadas)", NUMERIC),
                      title="Comprobación: forma ZPK")
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- Virtual Lab run, re-observed

def _find_run(session, run_id: str):
    from academic_core.domain.engineering.lab.model import LaboratorySession
    from academic_core.domain.engineering.lab.serialize import experiment_id

    if not isinstance(session, LaboratorySession):
        raise _invalid("INVALID_INPUT", "expected a Virtual Lab session")
    target = next((r for record in session.records for r in record.runs if r.run_id == run_id), None)
    if target is None:
        raise _invalid("UNKNOWN_RUN", f"{str(run_id)[:64]!r}")
    definition = next((e for e in session.experiments if experiment_id(e, session.circuit) == target.experiment_id),
                      None)
    return target, definition


def _same_result(kind: str, observed, recorded) -> bool:
    if kind == "OP":
        return (observed.status == recorded.status and observed.node_voltages == recorded.node_voltages
                and (observed.provenance or {}).get("solver_digest") == (recorded.provenance or {}).get("solver_digest"))
    if kind == "TRANSIENT":
        return (observed.status == recorded.status and observed.times == recorded.times
                and observed.node_trajectories == recorded.node_trajectories
                and observed.inductor_currents == recorded.inductor_currents and observed.stats == recorded.stats)
    return observed.digest == recorded.digest


def explain_lab_run_detail(session, run_id: str) -> ExecutionTrace:
    """Re-observe a Virtual Lab run: same engine, same working circuit, observer attached; CHECK = recorded run."""
    from academic_core.domain.engineering.lab.run import working_circuit
    from academic_core.domain.engineering.mna.analysis import dc_equivalent, solve_point

    run, definition = _find_run(session, run_id)
    rec = TraceRecorder(LAB_DETAIL)
    for name, v in (("run_id", run.run_id), ("analysis", run.analysis_kind),
                    ("result_digest", run.result_digest or "-")):
        rec.input(name, TraceValue.of_text(str(v)[:512]), f"Run: {name}")
    kind = run.analysis_kind
    try:
        head = rec.event(EventKind.STEP, f"Experimento {kind} (detalle)", refs=(rec.last,),
                         why=("Se vuelve a ejecutar el mismo motor sobre el circuito de trabajo del run (instantánea "
                              "del experimento) con el observador activado; al final se comprueba que el resultado "
                              "observado es el registrado."),
                         values=(("status", TraceValue.of_text(str(run.status))),
                                 ("engine_status", TraceValue.of_text(str(run.engine_status)))))
        if run.result is None or definition is None:
            raise ValidationError(f"{str(run.status)}: the run has no engine result to explain")
        analysis = definition.analysis
        if kind == "AC_SWEEP":
            last, rows = _ac_sweep_points(rec, run.result.sweep, head)
            last = rec.event(EventKind.WARNING, "internal iteration details unavailable", refs=(last,),
                             why="Cada frecuencia es una resolución directa (sin iteraciones); datos del run registrado.")
            res = rec.event(EventKind.RESULT, "Respuesta en frecuencia del run", refs=(last,),
                            values=(("points", TraceValue.of_number(len(run.result.sweep.points))),),
                            result=TraceValue.of_text(f"{run.status}: {kind}"))
            rel = _modulus_check(rows)
            rec.check("|H|² = Re² + Im² en cada punto", TraceValue.of_number(rel), TraceValue.of_number(Decimal(0)),
                      rel <= CX_TOL if rows else None, refs=(res,), tolerance=TraceValue.of_number(CX_TOL),
                      detail=labelled("módulos del motor frente a Re² + Im²", NUMERIC if rows else NONE),
                      title="Comprobación: magnitud")
            return rec.finish()
        if kind not in ("OP", "DC_SWEEP", "AC_POINT", "TRANSIENT"):
            rec.event(EventKind.WARNING, f"Explicación detallada no disponible para {kind}", refs=(head,),
                      why="El motor de este análisis no expone observaciones internas por paso.")
            raise UnsupportedError(f"UNSUPPORTED: detailed explanation not available for {kind}")
        working = working_circuit(session.circuit, definition)
        read = rec.event(EventKind.STEP, "Circuito de trabajo del run", refs=(head,),
                         formula=working.name,
                         values=(("components", TraceValue.of_text(", ".join(c.ref for c in working.components)[:512])),
                                 ("nets", TraceValue.of_text(", ".join(sorted(working.nets))[:512]))))
        if kind == "OP":
            obs = nwt._Observer()
            observed, _state = solve_point(working, observer=obs)
            nwt._newton_events(rec, dc_equivalent(working), read, observed, obs)
        elif kind == "DC_SWEEP":
            observed, _points, last, facts = _sweep_detail(rec, working, analysis.sweep, read, _Budget())
            res = rec.event(EventKind.RESULT, "Barrido del run", refs=(last,),
                            values=(("points", TraceValue.of_number(len(observed.points))),),
                            result=TraceValue.of_text(f"{observed.status.value}: {len(observed.points)} puntos"))
            _sweep_checks(rec, observed, facts, res)
        elif kind == "AC_POINT":
            observed, _res = _ac_detail(rec, working, analysis.frequency, "small-signal", read)
        else:
            observed, last, facts = _transient_detail(rec, working, analysis.transient, read, _Budget())
            if observed.status.value != "completed":
                raise ana._status_error(observed.status.value, observed.diagnostics)
            res = rec.event(EventKind.RESULT, "Transitorio del run", refs=(last,),
                            values=(("samples", TraceValue.of_number(len(observed.times))),),
                            result=TraceValue.of_text(f"COMPLETED: {len(observed.times)} instantes"))
            _transient_checks(rec, observed, analysis.transient, facts, res)
        same = _same_result(kind, observed, run.result)
        rec.check("el resultado observado es el del run registrado", TraceValue.of_text("sí" if same else "no"),
                  TraceValue.of_text("sí"), same, refs=(rec.last,),
                  detail=labelled("igualdad exacta (digest del motor, o estados y estadísticas)", SYMBOLIC),
                  title="Comprobación: mismo resultado que el run")
    except (ValueError, ArithmeticError) as exc:
        ana._fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- replay

def replay_detail(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation not in OPERATIONS:
        raise _invalid("INVALID_TRACE", "not an E0.3 detail trace")
    inputs = {n: v.text for n, v in trace.inputs}
    wide = dict(max_lines=nwt.CEILING_LINES, max_line_length=nwt.CEILING_LINE, max_total_chars=nwt.CEILING_TOTAL)
    if trace.operation == TF_ANALYSIS:
        return explain_tf_analysis(inputs["numerator"], inputs["denominator"], inputs["omega"])
    spec = ana._spec_of(trace)
    if trace.operation == AC_MNA:
        return explain_ac_mna(spec, inputs["frequency"], inputs["engine"], **wide)
    if trace.operation == DC_SWEEP_DETAIL:
        return explain_dc_sweep_detail(spec, inputs["source"], inputs["start"], inputs["stop"], inputs["step"],
                                       inputs["observe"], inputs["warm_start"] == "true", **wide)
    if trace.operation == AC_SWEEP:
        return explain_ac_sweep(spec, inputs["source"], inputs["output_p"], inputs["output_n"], inputs["frequencies"],
                                **wide)
    return explain_transient_detail(spec, inputs["method"], inputs["tstop"], inputs["h_init"], inputs["h_min"],
                                    inputs["h_max"], inputs["reltol"], inputs["abstol"], inputs["adaptive"] == "true",
                                    **wide)
