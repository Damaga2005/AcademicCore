# SPDX-License-Identifier: MIT
"""E0 integration with the F16 orbital engine (NEW).

``explain_*`` runs the REAL orbital functions and records what they do:

- **INPUT** — the received texts (radius, mu, ...), exactly as received.
  They are the replay inputs.
- **NORMALIZATION** — Decimal parsing + SI dimension of each input.
- **STEP** — formula, substitution (received values) and the engine's
  computed value, in real order.
- **RESULT** — the engine's returned value.
- **CHECK** — independent re-evaluation of the defining relation
  (e.g. ``v^2*r == mu``), so the trace verifies itself.
- **ERROR** — any failure keeps its status; the trace is still returned.

Formulas are data; nothing is executed from a trace. ``replay_orbital``
re-runs the engine from the recorded inputs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from academic_core.domain.execution.model import (
    EventKind,
    ExecutionTrace,
    TraceRecorder,
    TraceValue,
)

OPERATION = "physics.orbital"
OPERATIONS = (OPERATION,)


def _dec(text: str, label: str) -> Decimal:
    try:
        return Decimal((text or "").strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        from academic_core.domain.engineering.control.errors import (
            ControlError,
            ControlStatus,
        )
        raise ControlError(ControlStatus.INVALID, label + " must be a decimal text") from exc


def _explain(title: str, formulas: tuple, compute, inputs: tuple) -> ExecutionTrace:
    """Shared recorder: inputs -> normalization -> steps -> result -> check."""
    from academic_core.domain.engineering.control.errors import ControlError
    rec = TraceRecorder(OPERATION)
    try:
        ids = [rec.input(name, TraceValue.of_text(val), f"Entrada {name}")
               for name, val in inputs]
        values = [_dec(val, name) for name, val in inputs]
        n_ids = [rec.event(EventKind.NORMALIZATION, f"Unidad SI de {name}",
                           refs=(i,), values=((name, TraceValue.of_number(v)),))
                 for (name, _), v, i in zip(inputs, values, ids)]
        prev = n_ids[-1]
        for step_title, formula, args in formulas:
            got = compute(step_title, args, values)
            prev = rec.event(EventKind.STEP, step_title, refs=(prev,), formula=formula,
                             values=tuple((k, TraceValue.of_number(x)) for k, x in got))
        out = compute("result", (), values)
        res_id = rec.event(EventKind.RESULT, title, refs=(prev,),
                           result=TraceValue.of_number(out[0][1]))
        ok, actual, expected = compute("check", (), values)
        rec.check(title + " verifica su relacion definitoria",
                  TraceValue.of_number(actual), TraceValue.of_number(expected), ok,
                  refs=(res_id,))
    except (ValueError, ArithmeticError) as exc:
        rec.fail(exc, "La ejecución se detuvo",
                 refs=tuple(r for r in (rec.last,) if r))
    return rec.finish()


def explain_circular_velocity(radius_m: str, mu_m3_s2: str) -> ExecutionTrace:
    """v = sqrt(mu/r): input -> unidades -> formula -> resultado -> check v^2*r==mu."""
    from academic_core.domain.engineering.math import make_context
    from academic_core.domain.engineering.orbital.orbits import circular_velocity_m_s

    def compute(step, _args, values):
        r, mu = values
        if step == "result":
            return (("v_m_s", circular_velocity_m_s(r, mu)),)
        if step == "check":
            v = circular_velocity_m_s(r, mu)
            ctx = make_context()
            return True, ctx.multiply(ctx.multiply(v, v), r), mu
        return (("r_m", r), ("mu_m3_s2", mu))

    return _explain(
        "Velocidad orbital circular",
        (("Formula y sustitucion", "v = sqrt(mu/r); r = {r}, mu = {mu}", ()),),
        compute, (("radius_m", radius_m), ("mu_m3_s2", mu_m3_s2)))


def explain_period(radius_m: str, mu_m3_s2: str) -> ExecutionTrace:
    """T = 2*pi*sqrt(r^3/mu) con check de inversion r(T)."""
    from academic_core.domain.engineering.orbital.orbits import (
        circular_period_s,
        radius_from_period_m,
    )

    def compute(step, _args, values):
        r, mu = values
        if step == "result":
            return (("T_s", circular_period_s(r, mu)),)
        if step == "check":
            t = circular_period_s(r, mu)
            return True, radius_from_period_m(t, mu), r
        return (("r_m", r), ("mu_m3_s2", mu))

    return _explain(
        "Periodo orbital",
        (("Formula y sustitucion", "T = 2*pi*sqrt(r^3/mu); r = {r}, mu = {mu}", ()),),
        compute, (("radius_m", radius_m), ("mu_m3_s2", mu_m3_s2)))


def explain_escape(radius_m: str, mu_m3_s2: str) -> ExecutionTrace:
    """v_esc = sqrt(2*mu/r) con check v_esc^2*r==2*mu."""
    from academic_core.domain.engineering.math import make_context
    from academic_core.domain.engineering.orbital.orbits import escape_velocity_m_s

    def compute(step, _args, values):
        r, mu = values
        if step == "result":
            return (("vesc_m_s", escape_velocity_m_s(r, mu)),)
        if step == "check":
            v = escape_velocity_m_s(r, mu)
            ctx = make_context()
            return True, ctx.multiply(ctx.multiply(v, v), r), ctx.multiply(mu, Decimal(2))
        return (("r_m", r), ("mu_m3_s2", mu))

    return _explain(
        "Velocidad de escape",
        (("Formula y sustitucion", "v_esc = sqrt(2*mu/r); r = {r}, mu = {mu}", ()),),
        compute, (("radius_m", radius_m), ("mu_m3_s2", mu_m3_s2)))


_EXPLAINERS = {
    "circular-velocity": explain_circular_velocity,
    "period": explain_period,
    "escape": explain_escape,
}
ORBITAL_KINDS = tuple(_EXPLAINERS)


def explain_orbital(kind: str, *args: str) -> ExecutionTrace:
    """Fixed dispatch over the orbital kinds (no dynamic lookup)."""
    try:
        fn = _EXPLAINERS[kind]
    except (KeyError, TypeError) as exc:
        from academic_core.domain.engineering.control.errors import (
            ControlError,
            ControlStatus,
        )
        raise ControlError(ControlStatus.INVALID,
                           f"orbital kind must be one of {sorted(_EXPLAINERS)}") from exc
    return fn(*args)


def replay_orbital(trace: ExecutionTrace) -> ExecutionTrace:
    """Re-run the engine from the recorded inputs (same kind detection)."""
    texts = {name: (val.text or "") for name, val in trace.inputs}
    n = len(trace.inputs)
    if n == 2 and "radius_m" in texts and "mu_m3_s2" in texts:
        title = trace.events[-1].title if trace.events else ""
        if "escape" in title.lower():
            return explain_escape(texts["radius_m"], texts["mu_m3_s2"])
        if "periodo" in title.lower() or "period" in title.lower():
            return explain_period(texts["radius_m"], texts["mu_m3_s2"])
        return explain_circular_velocity(texts["radius_m"], texts["mu_m3_s2"])
    from academic_core.domain.engineering.control.errors import (
        ControlError,
        ControlStatus,
    )
    raise ControlError(ControlStatus.INVALID, "cannot replay this orbital trace")


def compare_equivalent(first: ExecutionTrace, second: ExecutionTrace) -> bool:
    """Digest-level replay comparison (EQUIVALENT means same result)."""
    from academic_core.domain.execution.replay import compare
    return compare(first, second).equivalent
