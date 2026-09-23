# SPDX-License-Identifier: MIT
"""E0.2 explainable analog engineering: linear MNA, DC sweep, AC, transient, TF, Virtual Lab.

Every trace is built from ONE real execution of a certified engine. Its
facts come from what that engine exposes, and nothing is re-solved:

- **Linear DC** (``engineering.linear-dc``): ``solve_linear_dc(...,
  observer=...)`` hands over the exact MNA system it solves (unknown
  labels, the matrix A and the right-hand side b as ``Fraction``) and
  the Gauss–Jordan outcome (status, rank, x). A trace shows the
  unknowns, A and b (value by value up to ``MAX_MATRIX``; above that it
  says the detail is omitted), the solution, and each node row of
  A·x = b as its KCL equation (the terms A_ij·x_j of the observed row,
  never an invented per-element split). CHECK: A·x = b in exact rational
  arithmetic (SYMBOLIC), the solver's conservation checks (NUMERIC), and
  that the reported voltages are the solution (NUMERIC: Fraction →
  Decimal).
- **DC sweep** (``engineering.dc-sweep``): the certified
  ``solve_dc_sweep`` result, one STEP per point: value, status, Newton
  iterations, warm/cold start, voltages and observables. Per-iteration
  Newton internals of each point are not exposed by the sweep; the trace
  says so.
- **AC** (``engineering.ac``): the certified ``solve_ac`` solution at one
  frequency: f, ω, the complex node phasors, and |V| and ∠V via the
  engine's own ``phasors.magnitude``/``phase``. CHECK: the solver's KCL
  and KVL residuals. The complex MNA matrix is not exposed: WARNING
  "MNA matrix unavailable".
- **Transient** (``engineering.transient``): the certified
  ``solve_transient`` committed history: time, node states, inductor
  currents, and the aggregate step statistics. Per-step internals
  (Newton, LTE, rejected steps) are only reported as aggregates by the
  engine: WARNING, not reconstructed.
- **Transfer function** (``control.tf-point``): ``TransferFunctionTF.
  evaluate(jω)``, its ``modulus()`` and the margins module's own phase
  (``_wrapped_phase_deg``).
- **Virtual Lab run** (``lab.run``): the certified ``Run`` a Virtual Lab
  experiment produced (result wrapped unchanged): status, readings,
  measurements and the engine result facts above for OP, DC_SWEEP,
  AC_POINT and TRANSIENT. For other kinds the detailed explanation is
  UNSUPPORTED, and the trace says so.

Circuits are text (the F8-H netlist + ``.param`` form of
``execution.newton``), one INPUT per line, so every trace except the
Virtual Lab one replays from its inputs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

from academic_core.domain.execution import newton as nwt
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.domain.execution.verification import NONE, NUMERIC, SYMBOLIC, labelled
from academic_core.errors import UnsupportedError, ValidationError

LINEAR_DC = "engineering.linear-dc"
DC_SWEEP = "engineering.dc-sweep"
AC = "engineering.ac"
TRANSIENT = "engineering.transient"
TF_POINT = "control.tf-point"
LAB_RUN = "lab.run"
OPERATIONS = (LINEAR_DC, DC_SWEEP, AC, TRANSIENT, TF_POINT)
MAX_MATRIX = 6  # A and b listed value by value up to 6 unknowns
MAX_ROWS = 16  # KCL rows shown one by one
MAX_POINTS = 128  # sweep points / transient samples shown one by one
MAX_ENTITIES = 24  # node voltages / phasors listed per event
STATUS_ERROR = {"unsupported": UnsupportedError}


def _frac(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _dec(v) -> TraceValue:
    """A Decimal as a bounded number (canonical, ≤ 200 digits) or its text."""
    try:
        return TraceValue.of_number(v)
    except ValueError:
        return TraceValue.of_text(str(v)[:512])


def _circuit(rec: TraceRecorder, spec: str, limits: dict) -> tuple:
    nwt.check_limits(limits.get("max_lines", nwt.MAX_LINES), limits.get("max_line_length", nwt.MAX_LINE),
                     limits.get("max_total_chars", nwt.MAX_SPEC))
    total = limits.get("max_total_chars", nwt.MAX_SPEC)
    if not isinstance(spec, str) or len(spec) > total:
        raise _invalid("INVALID_INPUT", f"the circuit must be text of at most {total} characters")
    lines = spec.splitlines()
    if len(lines) > limits.get("max_lines", nwt.MAX_LINES) or any(
            len(x) > limits.get("max_line_length", nwt.MAX_LINE) for x in lines):
        raise _invalid("INVALID_INPUT", "the circuit exceeds the configured line limits")
    return tuple(rec.input(f"circuit.{k + 1:03d}", TraceValue.of_text(line), f"Línea {k + 1} del circuito")
                 for k, line in enumerate(lines))


def _spec_of(trace: ExecutionTrace) -> str:
    return "\n".join(v.text for n, v in trace.inputs if n.startswith("circuit.")) + "\n"


def _read(rec: TraceRecorder, ids: tuple, spec: str, total: int):
    circuit = nwt.parse_circuit_spec(spec, max_total_chars=total)
    read = rec.event(EventKind.STEP, "Leer el circuito", refs=ids[-64:], formula=circuit.name,
                     why="La netlist (con los parámetros de dispositivo) se convierte en el modelo Circuit certificado.",
                     values=(("components", TraceValue.of_text(", ".join(c.ref for c in circuit.components)[:512])),
                             ("nets", TraceValue.of_text(", ".join(sorted(circuit.nets))[:512]))))
    for c in sorted(circuit.components, key=lambda c: c.ref.upper())[:64]:
        pins = ", ".join(f"{p}={n}" for p, n in c.pins.items())
        rec.event(EventKind.VALUE, f"Componente {c.ref.upper()} ({c.type.upper()})", refs=(read,),
                  formula=f"{c.ref.upper()}: {pins}"[:512],
                  values=(("type", TraceValue.of_text(c.type.upper())), ("pins", TraceValue.of_text(pins[:512])),
                          ("value", TraceValue.of_text(c.value.compact() if c.value is not None else "-"))))
    return circuit, read


def _fail(rec: TraceRecorder, exc: BaseException) -> None:
    rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))


def _status_error(status: str, diagnostics: tuple) -> Exception:
    error = STATUS_ERROR.get(status, ValidationError)
    return error(f"{status.upper()}: {'; '.join(diagnostics[-1:])}"[:400])


# ---------------------------------------------------------------- linear DC

class _LinearObserver:
    def __init__(self):
        self.system = None
        self.outcome = None

    def mna_system(self, unknowns, matrix, rhs):
        self.system = (tuple(unknowns), tuple(matrix), tuple(rhs))

    def linear_outcome(self, status, rank, solution):
        self.outcome = (status, rank, solution)


def explain_linear_dc(spec: str, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.solver import solve_linear_dc

    rec = TraceRecorder(LINEAR_DC)
    ids = _circuit(rec, spec, limits)
    try:
        circuit, read = _read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        obs = _LinearObserver()
        result = solve_linear_dc(circuit, observer=obs)
        if obs.system is None:
            rec.event(EventKind.WARNING, "MNA matrix unavailable", refs=(read,),
                      why="El solver rechazó el circuito antes de ensamblar el sistema; no hay matriz que mostrar.")
            raise _status_error(result.status.value, result.diagnostics)
        labels, matrix, rhs = obs.system
        n = len(labels)
        unk = rec.event(EventKind.STEP, "Incógnitas y ecuaciones", refs=(read,),
                        formula=f"{n} incógnitas: tensiones de nodo y corrientes auxiliares; {n} ecuaciones",
                        why=("MNA: una ecuación KCL por nodo (salvo la referencia) y una restricción por cada "
                             "fuente de tensión, transformador o inductor."),
                        values=tuple((f"x{k}", TraceValue.of_text(lab)) for k, lab in enumerate(labels[:64])))
        if n <= MAX_MATRIX:
            values = tuple((f"A.{i}.{j}", TraceValue.of_text(_frac(matrix[i][j]))) for i in range(n) for j in range(n))
            values += tuple((f"b.{i}", TraceValue.of_text(_frac(rhs[i]))) for i in range(n))
        else:
            values = (("matrix", TraceValue.of_text(
                f"detalle omitido: {n}×{n} mayor que {MAX_MATRIX}×{MAX_MATRIX} (límite de visualización)")),)
        sys_id = rec.event(EventKind.STEP, "Sistema MNA A·x = b", refs=(unk,), formula="A·x = b",
                           why="Matriz y vector que el solver certificado resolvió (fracciones exactas).",
                           values=values[:64])
        status, rank, solution = obs.outcome
        solve_id = rec.event(EventKind.STEP, "Resolución exacta (Gauss–Jordan sobre racionales)", refs=(sys_id,),
                             why="Eliminación exacta sin redondeo; el pivote nulo detecta la singularidad.",
                             values=(("status", TraceValue.of_text(status)), ("rank", TraceValue.of_number(rank)),
                                     ("size", TraceValue.of_number(n))))
        if solution is None:
            raise _status_error(result.status.value, result.diagnostics)
        sol_id = rec.event(EventKind.STEP, "Solución x", refs=(solve_id,),
                           values=tuple((f"x{k}.{nwt._label(lab)}"[:90], TraceValue.of_text(_frac(v)))
                                        for k, (lab, v) in enumerate(zip(labels, solution)))[:64])
        node_rows = [k for k, lab in enumerate(labels) if lab.startswith("V(")]
        kcl_ids = []
        for i in node_rows[:MAX_ROWS]:
            terms = [(labels[j], matrix[i][j], solution[j]) for j in range(n) if matrix[i][j] != 0]
            text = " + ".join(f"({_frac(a)})·{lab}" for lab, a, _x in terms) or "0"
            residual = sum((a * x for _lab, a, x in terms), Fraction(0)) - rhs[i]
            kcl_ids.append(rec.event(
                EventKind.STEP, f"KCL en el nodo {labels[i][2:-1]}", refs=(sol_id,),
                formula=f"{text} = {_frac(rhs[i])}"[:512],
                why="Fila del sistema MNA observado: es la ecuación KCL de ese nodo tal como la montó el solver.",
                values=tuple((f"term.{j}", TraceValue.of_text(_frac(a * x))) for j, (_l, a, x) in enumerate(terms[:60]))
                + (("residual", TraceValue.of_text(_frac(residual))),)))
        if len(node_rows) > MAX_ROWS:
            rec.event(EventKind.WARNING, "Filas KCL no detalladas", refs=(sol_id,),
                      why=f"Se detallan {MAX_ROWS} de {len(node_rows)} nodos.")
        if result.status.value != "solved":
            raise _status_error(result.status.value, result.diagnostics)
        res = rec.event(EventKind.RESULT, "Punto de operación DC", refs=(sol_id, *kcl_ids[:8]),
                        formula=", ".join(f"V({nv.node}) = {nv.voltage.format()}" for nv in result.node_voltages)[:512],
                        values=tuple((f"V.{nwt._label(nv.node)}", TraceValue.of_quantity(nv.voltage))
                                     for nv in result.node_voltages[:32]),
                        result=TraceValue.of_text(f"SOLVED ({n} incógnitas)"))
        exact = all(sum((matrix[i][j] * solution[j] for j in range(n)), Fraction(0)) == rhs[i] for i in range(n))
        rec.check("A·x = b en aritmética racional exacta", TraceValue.of_text("sí" if exact else "no"),
                  TraceValue.of_text("sí"), exact, refs=(res,),
                  detail=labelled("A, x y b tal como los usó el solver", SYMBOLIC), title="Comprobación: sistema MNA")
        index = {lab: k for k, lab in enumerate(labels)}
        worst = Decimal(0)
        with localcontext() as ctx:
            ctx.prec = 60
            for nv in result.node_voltages:
                k = index.get(f"V({nv.node})")
                if k is not None:
                    x = solution[k]
                    worst = max(worst, abs(nv.voltage.to_base() - Decimal(x.numerator) / Decimal(x.denominator)))
        rec.check("tensiones del resultado = solución x", TraceValue.of_number(+worst), TraceValue.of_number(Decimal(0)),
                  worst <= Decimal("1e-25"), refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-25")),
                  detail=labelled("conversión Fraction → Decimal del solver", NUMERIC),
                  title="Comprobación: el resultado es la solución")
        cc = result.conservation_checks
        if cc is not None:
            rec.check("conservación (KCL, KVL, potencia) del solver", TraceValue.of_text(
                f"kcl={cc.kcl_max_residual}; kvl={cc.kvl_max_residual}; power={cc.power_balance_residual}"[:512]),
                TraceValue.of_text(f"≤ {cc.tolerance}"), cc.passed, refs=(res,), tolerance=TraceValue.of_text(cc.tolerance),
                detail=labelled("residuos calculados por el solver frente a su tolerancia", NUMERIC),
                title="Comprobación: leyes de Kirchhoff")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- DC sweep

def _decimal(text: str, what: str) -> Decimal:
    try:
        v = Decimal(text)
    except (InvalidOperation, TypeError):
        raise _invalid("INVALID_INPUT", f"{what} must be a decimal number") from None
    if not v.is_finite():
        raise _invalid("INVALID_INPUT", f"{what} must be finite")
    return v


def _sweep_points(rec: TraceRecorder, result, prev: str) -> list:
    ids = []
    for p in result.points[:MAX_POINTS]:
        values = [("status", TraceValue.of_text(p.status.value)), ("init_mode", TraceValue.of_text(p.init_mode)),
                  ("warm_start", TraceValue.of_text("sí" if p.warm_start_used else "no")),
                  ("fallback", TraceValue.of_text("sí" if p.fallback_used else "no")),
                  ("iterations", TraceValue.of_number(p.iterations) if p.iterations is not None
                   else TraceValue.of_text("-"))]
        values += [(f"param.{nwt._label(k)}", _dec(v)) for k, v in p.parameters][:4]
        values += [(f"V.{nwt._label(k)}", _dec(v)) for k, v in sorted(p.node_voltages.items())][:MAX_ENTITIES]
        values += [(f"obs.{nwt._label(k)}", _dec(v)) for k, v in sorted(p.observables.items())][:16]
        ids.append(rec.event(
            EventKind.STEP if p.ok else EventKind.WARNING, f"Punto {p.index}: {p.label}"[:512], refs=(prev,),
            why=("Punto de operación resuelto por Newton (F8-H) con el parámetro fijado."
                 if p.ok else f"El punto no convergió: {p.diagnostic or p.status.value}"[:512]),
            values=tuple(values[:64])))
        prev = ids[-1]
    if len(result.points) > MAX_POINTS:
        rec.event(EventKind.WARNING, "Puntos no detallados", refs=(prev,),
                  why=f"Se detallan {MAX_POINTS} de {len(result.points)} puntos.")
    return ids


def explain_dc_sweep(spec: str, source: str, start: str, stop: str, step: str, observe: str = "",
                     **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.analysis import (
        GridSpec,
        ObservableSpec,
        ParamAddress,
        SweepConfig,
        solve_dc_sweep,
    )

    rec = TraceRecorder(DC_SWEEP)
    ids = _circuit(rec, spec, limits)
    for name, v in (("source", source), ("start", start), ("stop", stop), ("step", step), ("observe", observe)):
        if not isinstance(v, str):
            raise _invalid("INVALID_INPUT", f"{name} must be text")
        rec.input(name, TraceValue.of_text(v), f"Barrido: {name}")
    try:
        circuit, read = _read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        nodes = tuple(n.strip() for n in observe.split(",") if n.strip())
        config = SweepConfig(ParamAddress(source, "value"),
                             GridSpec.linear(_decimal(start, "start"), _decimal(stop, "stop"), _decimal(step, "step")),
                             tuple(ObservableSpec("node_voltage", n) for n in nodes))
        grid = rec.event(EventKind.STEP, "Barrido DC", refs=(read,),
                         formula=f"{source}.value = {start} … {stop} (paso {step})",
                         why=("El motor F8-M fija el valor de la fuente en cada punto de la rejilla y resuelve el "
                              "punto de operación; puede reutilizar la solución anterior (arranque en caliente)."))
        result = solve_dc_sweep(circuit, config)
        points = _sweep_points(rec, result, grid)
        rec.event(EventKind.WARNING, "Iteraciones internas por punto no expuestas", refs=(grid,),
                  why="El barrido informa del número de iteraciones de cada punto, no de cada iteración; "
                      "para verlas, explicar un punto con F8-H (engineering.nonlinear-dc).")
        if result.status.value not in ("completed",):
            raise _status_error(result.status.value, result.diagnostics or ("sweep did not complete",))
        res = rec.event(EventKind.RESULT, "Barrido completado", refs=tuple(points[-8:]) or (grid,),
                        values=(("points", TraceValue.of_number(len(result.points))),
                                ("digest", TraceValue.of_text(result.digest or "-"))),
                        result=TraceValue.of_text(f"{result.status.value}: {len(result.points)} puntos"))
        ok = all(p.ok for p in result.points)
        rec.check("todos los puntos convergieron", TraceValue.of_number(sum(1 for p in result.points if p.ok)),
                  TraceValue.of_number(len(result.points)), ok, refs=(res,),
                  detail=labelled("estado de cada punto informado por el motor", SYMBOLIC), title="Comprobación: puntos")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- AC

def _phasor_values(prefix: str, items) -> tuple:
    from academic_core.domain.engineering.ac.phasors import fmt_cartesian, magnitude, phase

    out = []
    for name, z in items[:MAX_ENTITIES // 2]:
        out += [(f"{prefix}.{nwt._label(name)}", TraceValue.of_text(fmt_cartesian(z)[:512])),
                (f"|{prefix}|.{nwt._label(name)}".replace("|", "abs_", 1).replace("|", ""), _dec(magnitude(z))),
                (f"arg_{prefix}.{nwt._label(name)}", _dec(phase(z)))]
    return tuple(out[:64])


def _ac_events(rec: TraceRecorder, sol, prev: str) -> str:
    op = sol.operating_point
    op_id = rec.event(EventKind.STEP, "Punto de operación AC", refs=(prev,),
                      formula="s = jω, ω = 2π·f; fasores de pico, convención e^(+jωt)",
                      values=(("f", TraceValue.of_quantity(op.frequency)), ("omega", _dec(op.omega)),
                              ("reference", TraceValue.of_text(op.reference_node))))
    nodes = [(nv.node, nv.phasor) for nv in sol.node_voltages]
    ph = rec.event(EventKind.STEP, "Fasores de nodo", refs=(op_id,),
                   formula="V = Re + j·Im;  |V| y ∠V (rad) con phasors.magnitude/phase del motor",
                   why="Solución compleja que el motor calculó; módulo y fase derivados con sus propias funciones.",
                   values=_phasor_values("V", nodes))
    if sol.branch_currents:
        ph = rec.event(EventKind.STEP, "Corrientes de rama", refs=(ph,),
                       values=_phasor_values("I", [(bc.ref, bc.current) for bc in sol.branch_currents]))
    return ph


def explain_ac(spec: str, frequency: str, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.ac.solver import solve_ac

    rec = TraceRecorder(AC)
    ids = _circuit(rec, spec, limits)
    if not isinstance(frequency, str):
        raise _invalid("INVALID_INPUT", "frequency must be text such as '1 kHz'")
    rec.input("frequency", TraceValue.of_text(frequency), "Frecuencia")
    try:
        circuit, read = _read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        sol = solve_ac(circuit, frequency)
        rec.event(EventKind.WARNING, "MNA matrix unavailable", refs=(read,),
                  why="La solución AC no expone la matriz compleja que resolvió; no se reconstruye.")
        if sol.status.value != "solved":
            raise _status_error(sol.status.value, sol.diagnostics)
        last = _ac_events(rec, sol, read)
        res = rec.event(EventKind.RESULT, "Solución AC", refs=(last,), values=(("digest", TraceValue.of_text(sol.digest)),),
                        result=TraceValue.of_text(f"SOLVED a {frequency}"))
        for name, value in (("KCL", sol.kcl_max_residual), ("KVL", sol.kvl_max_residual)):
            rec.check(f"residuo {name} máximo del solver", _dec(value) if value is not None else TraceValue.of_text("-"),
                      TraceValue.of_number(Decimal(0)), None if value is None else value <= Decimal("1e-20"),
                      refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-20")),
                      detail=labelled(f"residuo {name} calculado por el motor sobre la solución compleja",
                                      NUMERIC if value is not None else NONE), title=f"Comprobación: {name}")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- transient

def _transient_events(rec: TraceRecorder, result, prev: str) -> str:
    nets = sorted(result.node_trajectories)[:MAX_ENTITIES]
    inductors = sorted(result.inductor_currents)[:8]
    for k, t in enumerate(result.times[:MAX_POINTS]):
        values = [("t", TraceValue.of_number(t, "s"))]
        values += [(f"V.{nwt._label(n)}", _dec(result.node_trajectories[n][k])) for n in nets]
        values += [(f"I.{nwt._label(r)}", _dec(result.inductor_currents[r][k])) for r in inductors]
        prev = rec.event(EventKind.STEP, f"Paso aceptado {k}: t = {t} s", refs=(prev,),
                         why="Estado comprometido por el integrador en este instante (historia del motor).",
                         values=tuple(values[:64]))
    if len(result.times) > MAX_POINTS:
        prev = rec.event(EventKind.WARNING, "Instantes no detallados", refs=(prev,),
                         why=f"Se detallan {MAX_POINTS} de {len(result.times)} instantes comprometidos.")
    stats = result.stats or {}
    prev = rec.event(EventKind.STEP, "Estadísticas del integrador", refs=(prev,),
                     values=tuple((nwt._label(str(k)), TraceValue.of_text(str(v)[:512])) for k, v in sorted(stats.items()))[:64])
    rec.event(EventKind.WARNING, "Detalle interno por paso no expuesto", refs=(prev,),
              why=("El motor informa de Newton, LTE y pasos rechazados solo como agregados; la actualización "
                   "interna de cada paso no se reconstruye."))
    return prev


def explain_transient(spec: str, method: str, tstop: str, h_init: str, h_min: str, h_max: str,
                      reltol: str = "1e-3", abstol: str = "1e-6", adaptive: bool = True, **limits) -> ExecutionTrace:
    from academic_core.domain.engineering.mna.transient import TransientConfig, solve_transient

    rec = TraceRecorder(TRANSIENT)
    ids = _circuit(rec, spec, limits)
    fields = (("method", method), ("tstop", tstop), ("h_init", h_init), ("h_min", h_min), ("h_max", h_max),
              ("reltol", reltol), ("abstol", abstol))
    for name, v in fields:
        if not isinstance(v, str):
            raise _invalid("INVALID_INPUT", f"{name} must be text")
        rec.input(name, TraceValue.of_text(v), f"Transitorio: {name}")
    if not isinstance(adaptive, bool):
        raise _invalid("INVALID_INPUT", "adaptive must be a bool")
    rec.input("adaptive", TraceValue.of_text("true" if adaptive else "false"), "Transitorio: paso adaptativo")
    try:
        circuit, read = _read(rec, ids, spec, limits.get("max_total_chars", nwt.MAX_SPEC))
        config = TransientConfig(method, *(_decimal(v, n) for n, v in fields[1:]), adaptive=adaptive)
        cfg = rec.event(EventKind.STEP, "Configuración del integrador", refs=(read,),
                        formula=f"método {config.method}, t ∈ [0, {config.tstop}] s",
                        why="Integración implícita del sistema DAE con el método elegido.")
        result = solve_transient(circuit, config)
        if result.status.value != "completed":
            raise _status_error(result.status.value, result.diagnostics)
        last = _transient_events(rec, result, cfg)
        res = rec.event(EventKind.RESULT, "Transitorio completado", refs=(last,),
                        values=(("samples", TraceValue.of_number(len(result.times))),),
                        result=TraceValue.of_text(f"COMPLETED: {len(result.times)} instantes"))
        increasing = all(a < b for a, b in zip(result.times, result.times[1:]))
        rec.check("instantes estrictamente crecientes y t_final = tstop",
                  TraceValue.of_number(result.times[-1], "s") if result.times else TraceValue.of_text("-"),
                  TraceValue.of_number(config.tstop, "s"),
                  increasing and bool(result.times) and result.times[-1] == config.tstop, refs=(res,),
                  detail=labelled("comparación exacta de los instantes del motor", SYMBOLIC),
                  title="Comprobación: historia temporal")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- transfer function at one frequency

def explain_tf_point(numerator: str, denominator: str, omega: str) -> ExecutionTrace:
    from academic_core.domain.engineering.control.margins import _wrapped_phase_deg
    from academic_core.domain.engineering.control.tf import make_tf
    from academic_core.domain.engineering.math import DecimalComplex
    from academic_core.domain.execution.control import _coeffs, _poly_text

    rec = TraceRecorder(TF_POINT)
    n_id = rec.input("numerator", TraceValue.of_text(numerator if isinstance(numerator, str) else ""), "Numerador")
    d_id = rec.input("denominator", TraceValue.of_text(denominator if isinstance(denominator, str) else ""),
                     "Denominador")
    w_id = rec.input("omega", TraceValue.of_text(omega if isinstance(omega, str) else ""), "ω (rad/s)")
    try:
        num, den = _coeffs(numerator, "numerator"), _coeffs(denominator, "denominator")
        w = _decimal(omega, "omega")
        loop = make_tf(num, den)
        tf = rec.event(EventKind.STEP, "Función de transferencia", refs=(n_id, d_id),
                       formula=f"H(s) = ({_poly_text(num)}) / ({_poly_text(den)})")
        value = loop.evaluate(DecimalComplex(Decimal(0), w))
        ev = rec.event(EventKind.STEP, "Evaluación en s = jω", refs=(tf, w_id), formula=f"H(j·{omega})",
                       why="TransferFunctionTF.evaluate del motor (aritmética compleja Decimal).",
                       values=(("re", _dec(value.re)), ("im", _dec(value.im))))
        mag = value.modulus()
        ph = _wrapped_phase_deg(value)
        res = rec.event(EventKind.RESULT, "Módulo y fase", refs=(ev,),
                        formula="|H| = modulus();  ∠H = atan2(Im, Re) en grados (motor F8-P)",
                        values=(("magnitude", _dec(mag)), ("phase_deg", _dec(ph))),
                        result=TraceValue.of_text(f"|H| = {mag}; ∠H = {ph}°"[:512]))
        with localcontext() as ctx:
            ctx.prec = 80
            err = abs(mag * mag - (value.re * value.re + value.im * value.im))
            scale = max(Decimal(1), mag * mag)
            rel = +(err / scale)
        with localcontext() as ctx:
            ctx.prec = 6
            rel = +rel
        rec.check("|H|² = Re² + Im²", TraceValue.of_number(rel), TraceValue.of_number(Decimal(0)),
                  rel <= Decimal("1e-40"), refs=(res,), tolerance=TraceValue.of_number(Decimal("1e-40")),
                  detail=labelled("con los valores que devolvió el motor", NUMERIC), title="Comprobación: módulo")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- Virtual Lab run

def explain_lab_run(run) -> ExecutionTrace:
    """Explain a certified Virtual Lab ``Run`` from the facts it carries (nothing is re-run here).

    Replay goes through the certified lab replay (``replay_run``: result
    digest), not through this trace."""
    from academic_core.domain.engineering.lab.model import Run

    if not isinstance(run, Run):
        raise _invalid("INVALID_INPUT", "expected a Virtual Lab Run")
    rec = TraceRecorder(LAB_RUN)
    for name, v in (("run_id", run.run_id), ("analysis", run.analysis_kind), ("experiment_digest", run.experiment_digest),
                    ("result_digest", run.result_digest or "-")):
        rec.input(name, TraceValue.of_text(str(v)[:512]), f"Run: {name}")
    try:
        head = rec.event(EventKind.STEP, f"Experimento {run.analysis_kind}", refs=(rec.last,),
                         why="Run certificado del Laboratorio Virtual (F8-N): el resultado del motor se envuelve sin cambios.",
                         values=(("status", TraceValue.of_text(str(run.status))),
                                 ("engine_status", TraceValue.of_text(str(run.engine_status)))))
        prev = head
        result = run.result
        kind = run.analysis_kind
        if result is not None and kind == "OP":
            prev = rec.event(EventKind.STEP, "Punto de operación (F8-H)", refs=(prev,),
                             values=(("iterations", TraceValue.of_text(str((result.system_summary or {})
                                                                            .get("iterations", "-")))),)
                             + tuple((f"V.{nwt._label(nv.node)}", TraceValue.of_quantity(nv.voltage))
                                     for nv in result.node_voltages[:32]))
        elif result is not None and kind == "DC_SWEEP":
            points = _sweep_points(rec, result, prev)
            prev = points[-1] if points else prev
        elif result is not None and kind == "AC_POINT" and result.operating_point is not None:
            prev = _ac_events(rec, result, prev)
        elif result is not None and kind == "TRANSIENT":
            prev = _transient_events(rec, result, prev)
        else:
            prev = rec.event(EventKind.WARNING, f"Explicación detallada no disponible para {kind}", refs=(prev,),
                             why="UNSUPPORTED: se muestran solo el estado, las lecturas y las mediciones del run.")
        for r in run.readings[:32]:
            prev = rec.event(EventKind.VALUE, f"Lectura {r.key}", refs=(prev,),
                             values=(("instrument", TraceValue.of_text(str(r.kind))),
                                     ("status", TraceValue.of_text(str(r.status))),
                                     ("reason", TraceValue.of_text(str(r.reason)[:512] or "-"))))
        for m in run.measurements[:32]:
            prev = rec.event(EventKind.VALUE, f"Medición {m.key}", refs=(prev,),
                             values=(("value", TraceValue.of_text(str(m.value)[:512])),
                                     ("status", TraceValue.of_text(str(m.status)))))
        if run.status not in ("COMPLETED", "COMPLETED_WITH_FAILURES"):
            raise _status_error(str(run.status).lower(), tuple(run.diagnostics) or ("run failed",))
        res = rec.event(EventKind.RESULT, "Run del laboratorio", refs=(prev,), result=TraceValue.of_text(
            f"{run.status}: {kind}, digest {run.result_digest[:16]}…"))
        rec.check("el run se completó sin fallos parciales", TraceValue.of_text(str(run.status)),
                  TraceValue.of_text("COMPLETED"), run.status == "COMPLETED", refs=(res,),
                  detail=labelled("estado del run certificado (COMPLETED_WITH_FAILURES no se presenta como éxito "
                                  "pleno)", SYMBOLIC), title="Comprobación: estado del run")
    except (ValueError, ArithmeticError) as exc:
        _fail(rec, exc)
    return rec.finish()


# ---------------------------------------------------------------- replay

def replay_analog(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation not in OPERATIONS:
        raise _invalid("INVALID_TRACE", "not an E0.2 analog trace")
    inputs = {n: v.text for n, v in trace.inputs}
    wide = dict(max_lines=nwt.CEILING_LINES, max_line_length=nwt.CEILING_LINE, max_total_chars=nwt.CEILING_TOTAL)
    if trace.operation == TF_POINT:
        return explain_tf_point(inputs["numerator"], inputs["denominator"], inputs["omega"])
    spec = _spec_of(trace)
    if trace.operation == LINEAR_DC:
        return explain_linear_dc(spec, **wide)
    if trace.operation == DC_SWEEP:
        return explain_dc_sweep(spec, inputs["source"], inputs["start"], inputs["stop"], inputs["step"],
                                inputs["observe"], **wide)
    if trace.operation == AC:
        return explain_ac(spec, inputs["frequency"], **wide)
    return explain_transient(spec, inputs["method"], inputs["tstop"], inputs["h_init"], inputs["h_min"], inputs["h_max"],
                             inputs["reltol"], inputs["abstol"], inputs["adaptive"] == "true", **wide)
