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
  2⁻ᵐ from backtracking, the step peak, the node voltages, the residual
  norms and the two convergence tests (res_ok, step_ok), as the solver
  evaluated them.
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
"""

from __future__ import annotations

import re

from academic_core.domain.engineering.circuit import Circuit, CircuitError, Component
from academic_core.domain.engineering.mna.nonlinear import NonlinearStatus, solve_nonlinear_dc
from academic_core.domain.engineering.units import Quantity, UnitError, parse_quantity
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid
from academic_core.errors import UnsupportedError, ValidationError

OPERATION = "engineering.nonlinear-dc"
MAX_SPEC = 20_000
MAX_LINES = 200  # one INPUT per line (execution-trace/1 texts are <= 512 characters)
MAX_LINE = 500
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


def parse_circuit_spec(spec: str) -> Circuit:
    if not isinstance(spec, str) or len(spec) > MAX_SPEC:
        raise _invalid("INVALID_INPUT", f"the circuit must be text of at most {MAX_SPEC} characters")
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
    def __init__(self):
        self.nodes: tuple = ()
        self.start = None
        self.iterations: list = []

    def newton_start(self, nodes, x, kcl, aux, scale):
        self.nodes, self.start = tuple(nodes), (tuple(x), kcl, aux, scale)

    def newton_iteration(self, it, alpha, halvings, step_peak, x, kcl, aux, scale, res_ok, step_ok):
        self.iterations.append((it, alpha, halvings, step_peak, tuple(x), kcl, aux, scale, res_ok, step_ok))


def _voltages(nodes, x) -> tuple:
    return tuple((f"V.{n}", TraceValue.of_number(v, "V")) for n, v in list(zip(nodes, x))[:MAX_NODES_SHOWN])


def explain_nonlinear_dc(spec: str) -> ExecutionTrace:
    if not isinstance(spec, str) or len(spec) > MAX_SPEC:
        raise _invalid("INVALID_INPUT", f"the circuit must be text of at most {MAX_SPEC} characters")
    lines = spec.splitlines()
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE for line in lines):
        raise _invalid("INVALID_INPUT", f"the circuit must have at most {MAX_LINES} lines of {MAX_LINE} characters")
    rec = TraceRecorder(OPERATION)
    ids = [rec.input(f"circuit.{k + 1:03d}", TraceValue.of_text(line), f"Línea {k + 1} del circuito")
           for k, line in enumerate(lines)]
    try:
        circuit = parse_circuit_spec(spec)
        read = rec.event(EventKind.STEP, "Leer el circuito", refs=tuple(ids[-64:]), formula=circuit.name,
                         why="La netlist (con los parámetros de dispositivo) se convierte en el modelo Circuit certificado.",
                         values=(("components", TraceValue.of_text(", ".join(c.ref for c in circuit.components)[:512])),
                                 ("nets", TraceValue.of_text(", ".join(sorted(circuit.nets))[:512]))))
        obs = _Observer()
        result = solve_nonlinear_dc(circuit, observer=obs)
        prev = read
        if obs.start is not None:
            x0, kcl, aux, scale = obs.start
            prev = rec.event(EventKind.STEP, "Punto de partida", refs=(read,), formula="x₀ = 0 (vector nulo determinista)",
                             why="El solver parte del vector nulo y mide el residuo inicial F(x₀) por bloques.",
                             values=(("kcl_residual", TraceValue.of_number(kcl, "A")),
                                     ("aux_residual", TraceValue.of_number(aux, "V")),
                                     ("scale", TraceValue.of_number(scale)), *_voltages(obs.nodes, x0)))
        for it, alpha, halvings, peak, x, kcl, aux, scale, res_ok, step_ok in obs.iterations:
            prev = rec.event(
                EventKind.STEP, f"Iteración {it} de Newton", refs=(prev,),
                formula="J(x)·Δx = −F(x);  x ← x + α·Δx",
                why=("Newton amortiguado: se resuelve el sistema lineal con el jacobiano y se reduce α a la mitad "
                     "hasta que el residuo disminuye (backtracking)."),
                values=(("alpha", TraceValue.of_number(alpha)), ("halvings", TraceValue.of_number(halvings)),
                        ("step_peak", TraceValue.of_number(peak)), ("kcl_residual", TraceValue.of_number(kcl, "A")),
                        ("aux_residual", TraceValue.of_number(aux, "V")), ("scale", TraceValue.of_number(scale)),
                        ("res_ok", TraceValue.of_text("sí" if res_ok else "no")),
                        ("step_ok", TraceValue.of_text("sí" if step_ok else "no")), *_voltages(obs.nodes, x)))
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
    except (ValueError, ArithmeticError) as exc:
        rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))
    return rec.finish()


def replay_nonlinear_dc(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    lines = [v.text for name, v in trace.inputs if name.startswith("circuit.")]
    return explain_nonlinear_dc("\n".join(lines) + "\n")
