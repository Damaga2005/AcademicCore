# SPDX-License-Identifier: MIT
"""E0.1 step log: what the symbolic engine really did, in order.

Every rule application appends one ``Step``:

- ``operation``: the family of the rule (derivada, integral, ecuación,
  simplificación, …)
- ``rule``: the registered rule that was applied
- ``before``: the expression it was applied to
- ``after``: what the rule produced
- ``substitution``: the concrete values bound by the rule, e.g.
  ``n = 2`` or ``u = x^2 + 1``
- ``explanation``: the rule statement
- ``uses``: indices of the earlier steps whose results this step consumes

The log only records; it never computes. ``merge`` appends the steps of a
scratch log when a tentative strategy (substitution, integration by parts)
succeeded. The steps of strategies that failed are discarded, never shown. It is bounded by ``MAX_STEPS``.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.engineering.symbolic.expr import invalid

MAX_STEPS = 2000
MAX_FIELD = 500  # every recorded text must fit an execution-trace/1 string (512)


@dataclass(frozen=True)
class Step:
    index: int
    operation: str
    rule: str
    before: str
    after: str
    substitution: str = ""
    explanation: str = ""
    uses: tuple[int, ...] = ()


class StepLog:
    def __init__(self):
        self.steps: list[Step] = []

    def add(self, operation: str, rule: str, before: str, after: str, *, substitution: str = "",
            explanation: str = "", uses=()) -> int:
        if len(self.steps) >= MAX_STEPS:
            raise invalid("EXPRESSION_LIMIT", f"more than {MAX_STEPS} steps")
        for name, v in (("rule", rule), ("before", before), ("after", after), ("substitution", substitution),
                        ("explanation", explanation)):
            if len(v) > MAX_FIELD:
                raise invalid("EXPRESSION_LIMIT", f"step {name} longer than {MAX_FIELD} characters")
        index = len(self.steps)
        self.steps.append(Step(index, operation, rule, before, after, substitution, explanation,
                               tuple(u for u in uses if u is not None and u >= 0)))
        return index

    def merge(self, other: "StepLog") -> int:
        """Append the steps of a scratch log that succeeded; returns the index offset."""
        offset = len(self.steps)
        if offset + len(other.steps) > MAX_STEPS:
            raise invalid("EXPRESSION_LIMIT", f"more than {MAX_STEPS} steps")
        for st in other.steps:
            self.steps.append(Step(st.index + offset, st.operation, st.rule, st.before, st.after,
                                   st.substitution, st.explanation, tuple(u + offset for u in st.uses)))
        return offset
