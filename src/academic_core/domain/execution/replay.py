# SPDX-License-Identifier: MIT
"""E0 replay verification: ``original → replay → reproduced → compare/digest``.

Replay re-executes the *real* resolver from the inputs recorded in the
trace. The replayer is supplied by the integration (``equation.py``,
``digital.py``), so there is no second solver here. The reproduced trace
must equal the original event for event:

- a modified, lost or extra event is caught
- a changed value, unit or order is caught
- a different outcome or verification is caught

The verdict names the first difference path. Metadata is ignored because
it is not semantic.

Verdicts reuse the F8-N/F8-Q vocabulary: ``EQUIVALENT`` / ``RESULT_DIFFERS``.
Schema incompatibility is caught earlier, when the trace is decoded
(``VersionMismatchError`` / ``INVALID_SCHEMA``).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from academic_core.domain.execution.model import ExecutionTrace, _invalid
from academic_core.errors import IntegrationError

EQUIVALENT = "EQUIVALENT"
RESULT_DIFFERS = "RESULT_DIFFERS"


@dataclass(frozen=True)
class ReplayReport:
    status: str  # EQUIVALENT / RESULT_DIFFERS
    first_difference: str  # "" when equivalent, else a path such as "events[4].result"
    original_digest: str
    replayed_digest: str

    @property
    def equivalent(self) -> bool:
        return self.status == EQUIVALENT


def first_difference(a: ExecutionTrace, b: ExecutionTrace) -> str:
    """Path of the first semantic difference ('' if none). Metadata is not compared.

    Order: operation, inputs, then events (the most precise place), then
    the event count, then the outcome / verification / result summaries.
    """
    if a.operation != b.operation:
        return "operation"
    for k, (x, y) in enumerate(zip(a.inputs, b.inputs)):
        if x != y:
            return f"inputs[{k}]"
    if len(a.inputs) != len(b.inputs):
        return f"inputs (count {len(a.inputs)} != {len(b.inputs)})"
    for k, (x, y) in enumerate(zip(a.events, b.events)):
        if x != y:
            fx, fy = vars(x), vars(y)
            for f in fields(x):
                if fx[f.name] != fy[f.name]:
                    return f"events[{k}].{f.name}"
    if len(a.events) != len(b.events):
        return f"events (count {len(a.events)} != {len(b.events)})"
    for name, x, y in (("outcome", a.outcome, b.outcome), ("verification", a.verification, b.verification),
                       ("result", a.result, b.result)):
        if x != y:
            return name
    return ""


def compare(original: ExecutionTrace, replayed: ExecutionTrace) -> ReplayReport:
    for t in (original, replayed):
        if not isinstance(t, ExecutionTrace):
            raise _invalid("INVALID_TRACE", f"expected ExecutionTrace, got {type(t).__name__}")
    diff = first_difference(original, replayed)
    da, db = original.digest(), replayed.digest()
    if not diff and da != db:  # cannot happen for valid traces; kept as a guard
        diff = "digest"
    return ReplayReport(RESULT_DIFFERS if diff else EQUIVALENT, diff, da, db)


def replay(original: ExecutionTrace, replayer) -> ReplayReport:
    """Re-execute with ``replayer(original) -> ExecutionTrace`` and compare."""
    if not isinstance(original, ExecutionTrace):
        raise _invalid("INVALID_TRACE", f"expected ExecutionTrace, got {type(original).__name__}")
    return compare(original, replayer(original))


def verify_replay(original: ExecutionTrace, replayer) -> ExecutionTrace:
    """Like ``replay`` but raises ``IntegrationError REPLAY_MISMATCH`` (AC-INT-001) on difference."""
    report = replay(original, replayer)
    if not report.equivalent:
        raise IntegrationError(f"REPLAY_MISMATCH: first difference at {report.first_difference}")
    return original
