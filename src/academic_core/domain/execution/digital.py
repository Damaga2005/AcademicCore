# SPDX-License-Identifier: MIT
"""E0 integration with the certified F8-Q digital engine + Logic Analyzer.

``explain_capture(circuit, config)`` runs the REAL certified path,
``LogicAnalyzer.capture`` (the Q1–Q3R simulator, then the Q5 analyzer),
exactly once. It records only facts that path produced or that the
circuit declares. There is no second simulator, and gates are never
re-evaluated to produce a result.

- **INPUT** — the replay inputs: optional context (e.g. the demo circuit
  key given by the application), then the capture configuration as
  canonical text.
- **VALUE** — the circuit as declared: nets with their initial state,
  gates (kind, pins, output), stimuli and probes. Large circuits are
  summarised, with a WARNING.
- **STEP "Simulación"** — the horizon, the source window, and the
  transitions per channel, taken from the simulator's ``DigitalTrace``.
- **STEP per transition** — ``channel: previous → new at t``, taken from
  the captured (or searched) trace, same-time order included. Each one
  refs the element that drives the net (gate or stimulus, from the
  circuit topology) and the channel's previous transition. Detail is
  capped at ``MAX_DETAILED_TRANSITIONS``; any overflow is stated in a
  WARNING, never hidden.
- **DECISION** — the trigger: the edge that fired, where and why, or
  ``NOT_TRIGGERED`` and why.
- **RESULT** — capture status, window, captured-trace digest.
- **CHECK**:
  - Q4 replay of the captured trace (``verify_replay``)
  - digest after a JSON round trip
  - ``verify_capture`` (re-analysis of the replayed source)
  - truth-table consistency per observed gate: at every settled instant,
    the certified ``DigitalComponent.evaluate`` of the observed inputs
    must equal the observed output. If an input is not observed the
    check is ``NOT_APPLICABLE``, with the reason.
- **ERROR** — a failed capture, with its D2 code.

``replay_capture(trace, circuit_factory)`` rebuilds the configuration
from the recorded inputs, asks the factory for a fresh circuit, re-runs,
and ``replay.compare`` checks the result. The factory is the
application's demo factory, or (E0.1) a ``digital-circuit/1`` document
whose digest is recorded as the ``circuit_digest`` context input.

E0.1 pedagogical mode (``pedagogical=True``, off by default, so E0
traces are byte-identical) adds the input ``mode = pedagogical`` and, after
the transitions, one causal STEP per detailed transition:

- **stimulus-driven net**: the stimulus edge that schedules exactly this
  (time, state), taken from the stimulus's declared ``edges()``.
- **gate-driven net**: the settled states of the gate inputs at that
  instant, read from the captured trace, and the certified
  ``DigitalComponent.evaluate`` of them. It refs the input transitions at
  the same instant, which are the causes. Same-instant intermediate
  transitions (zero-delay glitches) are stated as such: the engine does
  not expose its internal delta-cycle evaluation, so no cause is invented
  for them.
- An unprobed input net with no driver keeps its declared initial state
  (a topology fact). If an input net is not probed and is driven, a
  WARNING says the cause is not observable. The explanation never fills
  the gap.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.digital import (
    MAX_EVENTS,
    CaptureConfig,
    CaptureStatus,
    DigitalCircuit,
    DigitalTrace,
    LogicAnalyzer,
    TriggerConfig,
    TriggerEdge,
    canonical_time,
    verify_capture,
    verify_replay,
)
from academic_core.domain.execution.model import (
    EventKind,
    ExecutionTrace,
    TraceRecorder,
    TraceValue,
    _invalid,
)

OPERATION = "digital.logic-analyzer"
CONFIG_INPUTS = ("channels", "start", "end", "trigger_channel", "edge", "pre_trigger", "post_trigger",
                 "max_events")
MAX_DETAILED_TRANSITIONS = 512
MAX_CIRCUIT_DETAIL = 96  # nets + gates + stimuli + probes described one by one
MAX_TRUTH_CHECKS = 64
MAX_CAUSAL = 256  # causal explanations in pedagogical mode
MODE_INPUT = "mode"
TIME = (0, 0, 1, 0, 0, 0, 0)  # SI exponents (kg, m, s, A, K, mol, cd) of seconds


def _t(value: Decimal) -> TraceValue:
    return TraceValue.of_number(value, "s", TIME)


def _txt(value: object) -> TraceValue:
    return TraceValue.of_text(str(value))


def config_inputs(config: CaptureConfig, max_events: int) -> tuple[tuple[str, str], ...]:
    """The capture configuration as canonical text (replay inputs)."""
    trig = config.trigger
    return (("channels", ",".join(config.channels)), ("start", canonical_time(config.start)),
            ("end", canonical_time(config.end)), ("trigger_channel", trig.channel if trig else ""),
            ("edge", trig.edge.value if trig else ""),
            ("pre_trigger", canonical_time(trig.pre_trigger) if trig else ""),
            ("post_trigger", canonical_time(trig.post_trigger) if trig else ""),
            ("max_events", str(max_events)))


def config_from_inputs(values: dict[str, str]) -> tuple[CaptureConfig, int]:
    trigger = None
    if values["trigger_channel"]:
        trigger = TriggerConfig(values["trigger_channel"], TriggerEdge(values["edge"]),
                                Decimal(values["pre_trigger"]), Decimal(values["post_trigger"]))
    config = CaptureConfig(tuple(values["channels"].split(",")), Decimal(values["start"]),
                           Decimal(values["end"]), trigger)
    return config, int(values["max_events"])


def _describe_circuit(rec: TraceRecorder, circuit: DigitalCircuit) -> dict[str, str]:
    """VALUE events for the declared circuit. Returns driver id -> event id."""
    nets, gates, stimuli, probes = circuit.nets(), circuit.components(), circuit.stimuli(), circuit.probes()
    ids: dict[str, str] = {}
    if len(nets) + len(gates) + len(stimuli) + len(probes) > MAX_CIRCUIT_DETAIL:
        rec.event(EventKind.VALUE, "Circuito (resumen)",
                  values=(("nets", TraceValue.of_number(len(nets))), ("gates", TraceValue.of_number(len(gates))),
                          ("stimuli", TraceValue.of_number(len(stimuli))),
                          ("probes", TraceValue.of_number(len(probes)))))
        rec.event(EventKind.WARNING, "Circuito resumido",
                  why=f"Tiene más de {MAX_CIRCUIT_DETAIL} elementos; se describe por recuento.")
        return ids
    for net in nets:
        rec.event(EventKind.VALUE, f"Red {net.net_id} (estado inicial {net.state.name})",
                  values=(("net", _txt(net.net_id)), ("initial", _txt(net.state.name))))
    for g in gates:
        pins = ", ".join(g.inputs)
        formula = f"{g.output} = {g.kind.value}({pins})"
        ids[g.component_id] = rec.event(
            EventKind.VALUE, f"Puerta {g.component_id}: {g.kind.value} de {g.arity} entrada(s)",
            formula=formula if len(formula) <= 512 else f"{g.output} = {g.kind.value}(… {g.arity} pines)",
            values=(("kind", _txt(g.kind.value)), ("output", _txt(g.output)),
                    ("arity", TraceValue.of_number(g.arity))))
    for s in stimuli:
        edges = s.edges()
        ids[s.stimulus_id] = rec.event(
            EventKind.VALUE, f"Estímulo {s.stimulus_id} ({type(s).__name__}) en {s.net_id}",
            values=(("net", _txt(s.net_id)), ("edges", TraceValue.of_number(len(edges))),
                    ("first_edge", _t(edges[0][0]) if edges else _txt("-"))))
    for p in probes:
        rec.event(EventKind.VALUE, f"Sonda {p.probe_id} → red {p.net_id}",
                  values=(("probe", _txt(p.probe_id)), ("net", _txt(p.net_id))))
    return ids


def _truth_checks(rec: TraceRecorder, circuit: DigitalCircuit, source: DigitalTrace, refs) -> None:
    observed = {c.net_id: c for c in source.channels}
    gates = [g for g in circuit.components() if g.output in observed]
    for g in gates[:MAX_TRUTH_CHECKS]:
        missing = sorted({n for n in g.inputs if n not in observed})
        what = f"tabla de verdad de {g.component_id} ({g.kind.value})"
        if missing:
            rec.check(what, _txt("-"), _txt("-"), None, refs=refs,
                      detail=f"entradas no observadas: {', '.join(missing)[:400]}")
            continue
        nets = sorted({g.output, *g.inputs})
        # linear sweep over the observed transitions, in time order (per-net order kept)
        pending = sorted((s.time, net, k, s.state) for net in nets for k, s in enumerate(observed[net].samples))
        state = {net: observed[net].initial for net in nets}
        instants, mismatch, i = 0, None, 0
        times = [source.start] + [t for t, *_ in pending]
        for t in sorted(set(times)):
            while i < len(pending) and pending[i][0] == t:
                state[pending[i][1]] = pending[i][3]
                i += 1
            instants += 1
            if mismatch is None and g.evaluate(tuple(state[n] for n in g.inputs)) is not state[g.output]:
                mismatch = t
        ok = mismatch is None
        rec.check(what, TraceValue.of_number(instants if ok else 0),
                  TraceValue.of_number(instants), ok, refs=refs,
                  detail=("salida = función certificada en todos los instantes estables" if ok
                          else f"discrepancia en t = {canonical_time(mismatch)} s"))
    if len(gates) > MAX_TRUTH_CHECKS:
        rec.event(EventKind.WARNING, "Comprobaciones de tabla de verdad limitadas", refs=refs,
                  why=f"Solo se comprueban las {MAX_TRUTH_CHECKS} primeras puertas observadas de {len(gates)}.")


def explain_capture(circuit: DigitalCircuit, config: CaptureConfig, *, context=(),
                    max_events: int = MAX_EVENTS, pedagogical: bool = False) -> ExecutionTrace:
    """Capture for real with ``LogicAnalyzer`` and return the ExecutionTrace of that run."""
    if not isinstance(circuit, DigitalCircuit) or not isinstance(config, CaptureConfig):
        raise _invalid("INVALID_INPUT", "explain_capture needs a DigitalCircuit and a CaptureConfig")
    if any(name == MODE_INPUT for name, _ in context):
        raise _invalid("INVALID_INPUT", f"{MODE_INPUT!r} is a reserved context name")
    rec = TraceRecorder(OPERATION)
    ctx_ids = [rec.input(name, _txt(value), f"Contexto {name}") for name, value in context]
    if pedagogical:
        ctx_ids.append(rec.input(MODE_INPUT, _txt("pedagogical"), "Modo pedagógico (causalidad)"))
    cfg_ids = [rec.input(name, _txt(value), f"Configuración {name}")
               for name, value in config_inputs(config, max_events)]
    drivers = _describe_circuit(rec, circuit)
    try:
        result = LogicAnalyzer(max_events).capture(circuit, config)  # the certified path, run once
    except (ValueError, ArithmeticError) as exc:
        rec.fail(exc, "La captura se detuvo", refs=tuple(cfg_ids))
        return rec.finish()
    source = result.source
    sim_id = rec.event(
        EventKind.STEP, "Simulación dirigida por eventos", refs=tuple(ctx_ids + cfg_ids),
        why="El motor F8-Q procesa los eventos en orden canónico (tiempo, secuencia, id) hasta el horizonte; "
            "solo las transiciones reales quedan registradas en su DigitalTrace.",
        values=(("horizon", _t(config.horizon)), ("source_start", _t(source.start)),
                ("source_end", _t(source.end)))
        + tuple((f"transitions.{c.probe_id}", TraceValue.of_number(len(c.samples))) for c in source.channels))
    shown = result.trace if result.trace is not None else source
    label = "capturada" if result.trace is not None else "examinada (sin captura)"
    detailed, trigger_event, total = 0, None, sum(len(c.samples) for c in shown.channels)
    transition_ids: dict[tuple[str, int], str] = {}  # (probe_id, sample index) -> event id
    for ch in shown.channels:
        driver = circuit.driver(ch.net_id)
        why = (f"La red {ch.net_id} la maneja {driver}." if driver else
               f"La red {ch.net_id} no tiene driver declarado.")
        samples, previous, prev_id, k = ch.samples, ch.initial, None, 0
        while k < len(samples) and detailed < MAX_DETAILED_TRANSITIONS:
            end = k  # samples are time-ordered: equal times form one contiguous run
            while end < len(samples) and samples[end].time == samples[k].time:
                end += 1
            for rank in range(end - k):
                if detailed >= MAX_DETAILED_TRANSITIONS:
                    break
                s = samples[k + rank]
                prev_id = rec.event(
                    EventKind.STEP,
                    f"{ch.probe_id}: {previous.name} → {s.state.name} en t = {canonical_time(s.time)} s",
                    refs=tuple(r for r in (drivers.get(driver), prev_id, sim_id) if r), why=why,
                    values=(("time", _t(s.time)), ("previous", _txt(previous.name)), ("new", _txt(s.state.name)),
                            ("same_time", _txt(f"{rank + 1}/{end - k}"))),
                    result=_txt(s.state.name))
                transition_ids[(ch.probe_id, k + rank)] = prev_id
                if result.trace is not None and ch.probe_id == result.trigger_channel and \
                        k + rank == result.trigger_index:
                    trigger_event = prev_id
                detailed += 1
                previous = s.state
            k = end
    if detailed < total:
        rec.event(EventKind.WARNING, "Transiciones no detalladas", refs=(sim_id,),
                  why=f"Se detallan {detailed} de {total} transiciones de la traza {label}; "
                      "la traza completa está en digital-trace/1 (ver digest del resultado).")
    if pedagogical:
        _causality(rec, circuit, shown, transition_ids, drivers)
    if config.trigger is not None:
        trig = config.trigger
        armed = f"[{canonical_time(config.start)}, {canonical_time(config.end)}] s"
        if result.status is CaptureStatus.TRIGGERED:
            rec.event(EventKind.DECISION, f"Disparo {result.trigger_edge.value} en {trig.channel}",
                      refs=tuple(r for r in (trigger_event, sim_id) if r),
                      why=f"Primera transición {trig.edge.value} del canal {trig.channel} dentro de la ventana de "
                          f"armado {armed}; el estado inicial nunca dispara.",
                      values=(("edge", _txt(trig.edge.value)), ("fired", _txt(result.trigger_edge.value)),
                              ("time", _t(result.trigger_time)),
                              ("index", TraceValue.of_number(result.trigger_index)),
                              ("pre_trigger", _t(trig.pre_trigger)), ("post_trigger", _t(trig.post_trigger))))
        else:
            rec.event(EventKind.DECISION, f"Sin disparo en {trig.channel}", refs=(sim_id,),
                      why=f"Ninguna transición {trig.edge.value} de {trig.channel} dentro de {armed}: "
                          "NOT_TRIGGERED es un resultado, no un error.",
                      values=(("edge", _txt(trig.edge.value)),))
    values = [("status", _txt(result.status.value)), ("transitions", TraceValue.of_number(total))]
    if result.trace is not None:
        values += [("window_start", _t(result.trace.start)), ("window_end", _t(result.trace.end)),
                   ("trace_digest", _txt(result.trace.digest()))]
    result_id = rec.event(EventKind.RESULT, f"Captura {result.status.value}", refs=(rec.last,),
                          values=tuple(values), result=_txt(result.status.value))
    if result.trace is not None:
        digest = result.trace.digest()
        try:
            replayed = verify_replay(result.trace).digest()
        except (ValueError, ArithmeticError) as exc:
            replayed = f"error {type(exc).__name__}"
        rec.check("reproducción digital-trace/1 (verify_replay)", _txt(replayed), _txt(digest),
                  replayed == digest, refs=(result_id,))
        round_trip = DigitalTrace.from_json(result.trace.to_json()).digest()
        rec.check("digest tras ida y vuelta JSON", _txt(round_trip), _txt(digest), round_trip == digest,
                  refs=(result_id,))
    try:
        verify_capture(result)
        verified = "EQUIVALENT"
    except (ValueError, ArithmeticError):
        verified = "RESULT_DIFFERS"
    rec.check("re-análisis tras replay (verify_capture)", _txt(verified), _txt("EQUIVALENT"),
              verified == "EQUIVALENT", refs=(result_id,))
    _truth_checks(rec, circuit, source, (result_id,))
    return rec.finish()


def replay_capture(trace: ExecutionTrace, circuit_factory) -> ExecutionTrace:
    """Re-run from the recorded inputs; ``circuit_factory(context: dict) -> DigitalCircuit``."""
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    recorded = {n: v.text for n, v in trace.inputs}
    if any(recorded.get(n) is None for n in CONFIG_INPUTS):
        raise _invalid("INVALID_TRACE", "the trace lacks the capture configuration inputs")
    mode = recorded.get(MODE_INPUT)
    if mode not in (None, "pedagogical"):
        raise _invalid("INVALID_TRACE", f"unknown mode {mode[:32]!r}")
    context = tuple((n, recorded[n]) for n, _ in trace.inputs if n not in CONFIG_INPUTS and n != MODE_INPUT)
    config, max_events = config_from_inputs(recorded)
    return explain_capture(circuit_factory(dict(context)), config, context=context, max_events=max_events,
                           pedagogical=mode == "pedagogical")


def _settled(samples, initial, t) -> tuple:
    """(state after every sample with time <= t, indices of the samples exactly at t)."""
    state, at = initial, []
    for i, s in enumerate(samples):
        if s.time > t:
            break
        state = s.state
        if s.time == t:
            at.append(i)
    return state, at


def _causality(rec: TraceRecorder, circuit: DigitalCircuit, shown: DigitalTrace,
               transition_ids: dict, drivers: dict) -> None:
    """Pedagogical causal steps: why each detailed transition happened (observed facts only)."""
    by_net: dict[str, object] = {}
    for c in shown.channels:
        by_net.setdefault(c.net_id, c)
    gates = {g.component_id: g for g in circuit.components()}
    stimuli = {s.stimulus_id: s for s in circuit.stimuli()}
    done = 0
    pending = sorted(transition_ids.items(), key=lambda kv: int(kv[1][1:]))  # emission order
    for (probe_id, index), event_id in pending:
        if done >= MAX_CAUSAL:
            rec.event(EventKind.WARNING, "Causalidad limitada",
                      why=f"Solo se explican las {MAX_CAUSAL} primeras transiciones detalladas.")
            return
        ch = next(c for c in shown.channels if c.probe_id == probe_id)
        s = ch.samples[index]
        driver = circuit.driver(ch.net_id)
        when = canonical_time(s.time)
        if driver in stimuli:
            stim = stimuli[driver]
            scheduled = (s.time, s.state) in stim.edges()
            rec.event(EventKind.STEP if scheduled else EventKind.WARNING,
                      f"Causa de {probe_id} → {s.state.name} en t = {when} s: estímulo {driver}",
                      refs=tuple(r for r in (event_id, drivers.get(driver)) if r),
                      why=(f"El estímulo {type(stim).__name__} {driver} programa el flanco {s.state.name} en "
                           f"t = {when} s sobre la red {ch.net_id}." if scheduled else
                           f"El estímulo {driver} no declara ese flanco; no se inventa una causa."),
                      values=(("driver", _txt(driver)), ("kind", _txt("stimulus")), ("time", _t(s.time)),
                              ("new", _txt(s.state.name))),
                      result=_txt(s.state.name))
            done += 1
            continue
        gate = gates.get(driver)
        if gate is None:
            continue
        last_at_t = index + 1 >= len(ch.samples) or ch.samples[index + 1].time != s.time
        if not last_at_t:
            rec.event(EventKind.WARNING, f"{probe_id} → {s.state.name} en t = {when} s: transición transitoria",
                      refs=tuple(r for r in (event_id, drivers.get(driver)) if r),
                      why=("Estado intermedio de tiempo cero (delta): en el mismo instante la salida vuelve a cambiar. "
                           "El motor no expone su evaluación interna delta a delta, así que no se inventa la causa."),
                      values=(("driver", _txt(driver)), ("time", _t(s.time))))
            done += 1
            continue
        # an unprobed net with no driver never changes (topology fact): its state is its declared initial state
        constant = {n: circuit.net(n).state for n in gate.inputs if n not in by_net and circuit.driver(n) is None}
        missing = sorted({n for n in gate.inputs if n not in by_net and n not in constant})
        if missing:
            rec.event(EventKind.WARNING, f"Causa de {probe_id} en t = {when} s no observable",
                      refs=tuple(r for r in (event_id, drivers.get(driver)) if r),
                      why=f"Entradas de {driver} sin sonda: {', '.join(missing)[:300]}. No se inventa la causa.",
                      values=(("driver", _txt(driver)),))
            done += 1
            continue
        states, causes, changed = [], [], []
        for net in gate.inputs:
            if net in constant:
                states.append(constant[net])
                continue
            c = by_net[net]
            state, at = _settled(c.samples, c.initial, s.time)
            states.append(state)
            for i in at:
                ref = transition_ids.get((c.probe_id, i))
                if ref and ref not in causes and int(ref[1:]) < int(event_id[1:]):
                    causes.append(ref)
                if net not in changed:
                    changed.append(net)
        evaluated = gate.evaluate(tuple(states))
        pins = ", ".join(f"{n}={st.name}" for n, st in zip(gate.inputs, states))
        if len(pins) > 300:
            pins = pins[:297] + "…"
        trigger = (f"al cambiar {', '.join(changed)[:120]} en t = {when} s" if changed
                   else "en el arranque del simulador (evaluación inicial)")
        rec.event(
            EventKind.STEP, f"Causa de {probe_id} → {s.state.name} en t = {when} s: puerta {driver}",
            refs=tuple(dict.fromkeys(r for r in (event_id, *causes[:32], drivers.get(driver)) if r)),
            formula=f"{gate.output} = {gate.kind.value}({pins})",
            why=(f"Retardo cero: {trigger}, la puerta {gate.kind.value} se re-evalúa con las entradas estables "
                 f"y su salida pasa a {evaluated.name}."),
            values=(("driver", _txt(driver)), ("kind", _txt(gate.kind.value)), ("time", _t(s.time)),
                    ("inputs", _txt(pins)), ("evaluated", _txt(evaluated.name)), ("observed", _txt(s.state.name)),
                    ("consistent", _txt("sí" if evaluated is s.state else "no"))),
            result=_txt(evaluated.name))
        done += 1
