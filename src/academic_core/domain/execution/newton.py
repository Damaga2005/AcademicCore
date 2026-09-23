# SPDX-License-Identifier: MIT
"""E0.1 integration with the certified F8-N damped Newton DC solver.

``explain_nonlinear_dc(spec)`` runs ``solve_nonlinear_dc`` once, with its
optional observer, and records the iteration exactly as the solver
performed it. No iteration is invented or skipped:

- **INPUT**: the circuit as text, one input per line (``circuit.001``,
  …). This is the Phase-6 netlist, plus one ``.param REF name=value …``
  line per component that carries device parameters. These are the
  replay inputs.
- **STEP "Leer el circuito"**: components and nets of the circuit that was
  built.
- **STEP "Punto de partida"**: x₀ (the node voltages) and the initial
  residual norms (KCL block, auxiliary block), as the solver computed them.
- **STEP "Iteración k"**, one per accepted Newton step: the damping α =
  2⁻ᵐ from backtracking, the step peak ‖αΔx‖∞, the node voltages, the
  residual norms and the two convergence tests (res_ok, step_ok), as the
  solver evaluated them. E0.1-R+: also x_k, F(x_k), the Jacobian J(x_k)
  the solver really factorised, and Δx, value by value up to 4 unknowns;
  above that the event says the detail is omitted (display bound). Nothing
  is recomputed here.
- **DECISION**: why the solver stopped (converged, or not).
- **RESULT**: the node voltages of the converged operating point.
- **ERROR**: any non-CONVERGED status, with the solver's own status as
  the reason token and its last diagnostic as the message. It is a D2
  ``UnsupportedError`` for UNSUPPORTED, else a ``ValidationError``.
- **CHECK**:
  - the solver's own conservation checks (KCL, KVL, power balance
    against its tolerance)
  - the iteration count in provenance equals the number of observed
    iterations
  - continuity: x_(k+1) of each iteration is the x_k of the next

Input limits are configurable (``max_lines``, ``max_line_length``,
``max_total_chars``) within the execution-trace/1 transport ceilings.
"""

from __future__ import annotations

import re

from academic_core.domain.engineering.circuit import Circuit, CircuitError, Component
from academic_core.domain.engineering.mna.nonlinear import NonlinearStatus, solve_nonlinear_dc
from academic_core.domain.engineering.units import Quantity, UnitError, parse_quantity
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.errors import UnsupportedError, ValidationError

OPERATION = "engineering.nonlinear-dc"
# Input limits (E0.1-R+ L5). They protect the transport, not the solver: each netlist line is one
# execution-trace/1 INPUT (text <= 512 characters, at most 256 inputs). The defaults are safe; callers may
# change them within the ceilings, never beyond.
MAX_SPEC = 20_000
MAX_LINES = 200
MAX_LINE = 500
CEILING_LINES = 250  # MAX_INPUTS (256) minus headroom
CEILING_LINE = 512  # MAX_STRING of execution-trace/1
CEILING_TOTAL = CEILING_LINES * (CEILING_LINE + 1)
MAX_VECTOR_SHOWN = 4  # x_k, F, Δx and J are listed value by value up to 4 unknowns
_PARAM_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,15}\Z")
MAX_NODES_SHOWN = 32


def circuit_spec(circuit: Circuit) -> str:
    """Netlist + ``.param`` lines. Refused if a parameter is not a Quantity."""
    lines = [circuit.to_netlist().rstrip("\n").removesuffix(".end").rstrip("\n")]
    for c in sorted(circuit.components, key=lambda c: c.ref.upper()):
        if not c.parameters:
            continue
        parts = []
        for name in sorted(c.parameters):
            q = c.parameters[name]
            if not isinstance(q, Quantity):
                raise _invalid("UNSUPPORTED_PARAMETER", f"{c.ref}.{name} is not a quantity; it cannot be written as text")
            parts.append(f"{name}={q.compact()}")
        lines.append(f".param {c.ref.upper()} " + " ".join(parts))
    lines.append(".end")
    return "\n".join(lines) + "\n"


def parse_circuit_spec(spec: str, max_total_chars: int = MAX_SPEC) -> Circuit:
    if not isinstance(spec, str) or len(spec) > min(max_total_chars, CEILING_TOTAL):
        raise _invalid("INVALID_INPUT", f"the circuit must be text of at most {max_total_chars} characters")
    netlist, params = [], {}
    for line in spec.splitlines():
        if line.strip().lower().startswith(".param"):
            parts = line.split()
            if len(parts) < 3:
                raise _invalid("INVALID_INPUT", f"malformed .param line {line[:40]!r}")
            ref = parts[1].upper()
            if ref in params:
                raise _invalid("INVALID_INPUT", f".param {ref} given twice")
            values = {}
            for item in parts[2:]:
                name, sep, val = item.partition("=")
                if not sep or not _PARAM_RE.fullmatch(name) or name in values:
                    raise _invalid("INVALID_INPUT", f"bad parameter {item[:32]!r}")
                try:
                    values[name] = parse_quantity(val)
                except UnitError:
                    raise _invalid("INVALID_INPUT", f"bad parameter value {item[:32]!r}") from None
            params[ref] = values
        else:
            netlist.append(line)
    try:
        base = Circuit.from_netlist("\n".join(netlist))
    except CircuitError as exc:
        raise _invalid("INVALID_INPUT", str(exc)) from None
    known = {c.ref.upper() for c in base.components}
    unknown = sorted(set(params) - known)
    if unknown:
        raise _invalid("INVALID_INPUT", f".param for unknown components: {', '.join(unknown)}")
    circuit = Circuit(base.name)
    for c in base.components:
        circuit.add(Component(c.ref, c.type, c.value, dict(c.pins), dict(params.get(c.ref.upper(), {}))))
    return circuit


class _Observer:
    """Keeps the immutable snapshots the solver hands over (tuples of Decimal)."""

    def __init__(self):
        self.nodes: tuple = ()
        self.unknowns: tuple = ()
        self.start = None
        self.iterations: list = []

    def newton_start(self, nodes, x, kcl, aux, scale, *, unknowns=(), residual=()):
        self.nodes, self.unknowns = tuple(nodes), tuple(unknowns)
        self.start = (tuple(x), kcl, aux, scale, tuple(residual))

    def newton_iteration(self, it, alpha, halvings, step_peak, x, kcl, aux, scale, res_ok, step_ok, *,
                         x_prev=(), residual_prev=(), jacobian=(), dx=(), residual=()):
        self.iterations.append(dict(it=it, alpha=alpha, halvings=halvings, peak=step_peak, x=tuple(x), kcl=kcl,
                                    aux=aux, scale=scale, res_ok=res_ok, step_ok=step_ok, x_prev=tuple(x_prev),
                                    f_prev=tuple(residual_prev), jac=tuple(jacobian), dx=tuple(dx),
                                    f=tuple(residual)))


def _voltages(nodes, x) -> tuple:
    return tuple((f"V.{n}", TraceValue.of_number(v, "V")) for n, v in list(zip(nodes, x))[:MAX_NODES_SHOWN])


def _vectors(labels: tuple, facts: dict) -> tuple:
    """x_k, F(x_k), J(x_k) and Δx exactly as the solver used them (bounded display)."""
    n = len(facts["x_prev"])
    if not labels or n > MAX_VECTOR_SHOWN:
        return (("jacobian", TraceValue.of_text(
            f"detalle omitido: sistema {n}×{n} mayor que {MAX_VECTOR_SHOWN}×{MAX_VECTOR_SHOWN} (límite de visualización)")),)
    labels = tuple(re.sub(r"[^A-Za-z0-9_:\-]", "_", lab).strip("_") or "u" for lab in labels)
    out = []
    for name, vec in (("x_k", facts["x_prev"]), ("F_k", facts["f_prev"]), ("dx", facts["dx"])):
        out += [(f"{name}.{lab}", TraceValue.of_number(v)) for lab, v in zip(labels, vec)]
    out += [(f"J.{labels[i]}.{labels[j]}", TraceValue.of_number(facts["jac"][i][j]))
            for i in range(n) for j in range(n)]
    return tuple(out)


def check_limits(max_lines: int, max_line_length: int, max_total_chars: int) -> None:
    for name, v, ceiling in (("max_lines", max_lines, CEILING_LINES), ("max_line_length", max_line_length, CEILING_LINE),
                             ("max_total_chars", max_total_chars, CEILING_TOTAL)):
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= ceiling:
            raise _invalid("INVALID_LIMIT", f"{name} must be 1..{ceiling} (execution-trace/1 transport ceiling)")


def explain_nonlinear_dc(spec: str, *, max_lines: int = MAX_LINES, max_line_length: int = MAX_LINE,
                         max_total_chars: int = MAX_SPEC) -> ExecutionTrace:
    """Trace one real F8-N solve. The input limits are configurable within the transport ceilings."""
    check_limits(max_lines, max_line_length, max_total_chars)
    if not isinstance(spec, str) or len(spec) > max_total_chars:
        raise _invalid("INVALID_INPUT", f"the circuit must be text of at most {max_total_chars} characters")
    lines = spec.splitlines()
    if len(lines) > max_lines or any(len(line) > max_line_length for line in lines):
        raise _invalid("INVALID_INPUT",
                       f"the circuit must have at most {max_lines} lines of {max_line_length} characters")
    rec = TraceRecorder(OPERATION)
    ids = [rec.input(f"circuit.{k + 1:03d}", TraceValue.of_text(line), f"Línea {k + 1} del circuito")
           for k, line in enumerate(lines)]
    try:
        circuit = parse_circuit_spec(spec, max_total_chars=max_total_chars)
        read = rec.event(EventKind.STEP, "Leer el circuito", refs=tuple(ids[-64:]), formula=circuit.name,
                         why="La netlist (con los parámetros de dispositivo) se convierte en el modelo Circuit certificado.",
                         values=(("components", TraceValue.of_text(", ".join(c.ref for c in circuit.components)[:512])),
                                 ("nets", TraceValue.of_text(", ".join(sorted(circuit.nets))[:512]))))
        obs = _Observer()
        result = solve_nonlinear_dc(circuit, observer=obs)
        prev = read
        if obs.start is not None:
            x0, kcl, aux, scale, _f0 = obs.start
            prev = rec.event(EventKind.STEP, "Punto de partida", refs=(read,), formula="x₀ = 0 (vector nulo determinista)",
                             why="El solver parte del vector nulo y mide el residuo inicial F(x₀) por bloques.",
                             values=(("kcl_residual", TraceValue.of_number(kcl, "A")),
                                     ("aux_residual", TraceValue.of_number(aux, "V")),
                                     ("scale", TraceValue.of_number(scale)), *_voltages(obs.nodes, x0)))
        for f in obs.iterations:
            prev = rec.event(
                EventKind.STEP, f"Iteración {f['it']} de Newton", refs=(prev,),
                formula="x_k, F(x_k), J(x_k) → resolver J·Δx = −F → x_(k+1) = x_k + α·Δx",
                why=("Newton amortiguado: se resuelve el sistema lineal con el jacobiano real y se reduce α a la mitad "
                     "hasta que el residuo disminuye (backtracking). ‖F‖ son las normas por bloques (KCL, auxiliar) "
                     "en x_(k+1); ‖αΔx‖∞ es step_peak. Parada: res_ok y step_ok."),
                values=(("alpha", TraceValue.of_number(f["alpha"])), ("halvings", TraceValue.of_number(f["halvings"])),
                        ("step_peak", TraceValue.of_number(f["peak"])), ("kcl_residual", TraceValue.of_number(f["kcl"], "A")),
                        ("aux_residual", TraceValue.of_number(f["aux"], "V")), ("scale", TraceValue.of_number(f["scale"])),
                        ("res_ok", TraceValue.of_text("sí" if f["res_ok"] else "no")),
                        ("step_ok", TraceValue.of_text("sí" if f["step_ok"] else "no")), *_voltages(obs.nodes, f["x"]),
                        *_vectors(obs.unknowns, f))[:64])
        converged = result.status is NonlinearStatus.CONVERGED
        decision = rec.event(
            EventKind.DECISION, "Criterio de parada", refs=(prev,),
            why=("Convergencia: residuo dentro de tolerancia (res_ok) y paso pequeño (step_ok)." if converged else
                 "El solver se detuvo sin certificar la convergencia."),
            values=(("status", TraceValue.of_text(result.status.value)),
                    ("iterations", TraceValue.of_number(len(obs.iterations)))))
        if not converged:
            error = UnsupportedError if result.status is NonlinearStatus.UNSUPPORTED else ValidationError
            raise error(f"{result.status.name}: {'; '.join(result.diagnostics[-1:])}"[:400])
        res = rec.event(EventKind.RESULT, "Punto de operación", refs=(decision,),
                        formula=", ".join(f"V({nv.node}) = {nv.voltage.format()}" for nv in result.node_voltages)[:512],
                        values=tuple((f"V.{nv.node}", TraceValue.of_quantity(nv.voltage))
                                     for nv in result.node_voltages[:MAX_NODES_SHOWN]),
                        result=TraceValue.of_text(f"CONVERGED en {len(obs.iterations)} iteraciones"))
        cc = result.conservation_checks
        if cc is not None:
            rec.check("conservación (KCL, KVL, balance de potencia) del solver", TraceValue.of_text(
                f"kcl={cc.kcl_max_residual}; kvl={cc.kvl_max_residual}; power={cc.power_balance_residual}"[:512]),
                TraceValue.of_text(f"≤ {cc.tolerance}"), cc.passed, refs=(res,),
                tolerance=TraceValue.of_text(cc.tolerance), title="Comprobación: leyes de Kirchhoff")
        reported = result.provenance.get("iterations")
        rec.check("iteraciones en la procedencia = iteraciones observadas",
                  TraceValue.of_number(len(obs.iterations)), TraceValue.of_text(str(reported)),
                  reported == len(obs.iterations), refs=(res,), title="Comprobación: iteraciones completas")
        chained = all(a["x"] == b["x_prev"][:len(a["x"])] for a, b in zip(obs.iterations, obs.iterations[1:]))
        rec.check("x_(k+1) de cada iteración = x_k de la siguiente", TraceValue.of_text("sí" if chained else "no"),
                  TraceValue.of_text("sí"), chained if len(obs.iterations) > 1 else None, refs=(res,),
                  title="Comprobación: continuidad de las iteraciones")
    except (ValueError, ArithmeticError) as exc:
        rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))
    return rec.finish()


def explain_nonlinear_circuit(circuit: Circuit, **limits) -> ExecutionTrace:
    """Trace a ``Circuit`` object through its exact text form (refused if it cannot be written as text)."""
    return explain_nonlinear_dc(circuit_spec(circuit), **limits)


def replay_nonlinear_dc(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    lines = [v.text for name, v in trace.inputs if name.startswith("circuit.")]
    # the recorded trace is already bounded; replay accepts anything within the transport ceilings
    return explain_nonlinear_dc("\n".join(lines) + "\n", max_lines=CEILING_LINES, max_line_length=CEILING_LINE,
                                max_total_chars=CEILING_TOTAL)
