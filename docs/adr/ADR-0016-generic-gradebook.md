# ADR-0016 — Generic gradebook beside the F1 0–10 engine

Date: 2026-09-12 · Status: Accepted

## Context
F1 ports the Gestion 0–10 weighted-component engine (Decimal, `maximo`,
final override) with equivalence gates. F4 needs scales beyond 0–10
(0–20/0–100/letters/pass-fail), optional activities, and honest partial
states — none of which the F1 engine models.

## Decision
- New `domain/results.py`: Scale (numeric min/max | letter→ratio map |
  pass_fail) + Grade (Decimal value/weight, optional) + `compute()` to a
  0..1 ratio with explicit `planned_required_weight` for partial honesty.
  All-Decimal, order-independent, no floats.
- The F1 engine (`domain/grading.py` + `grade_schemes` tables) is UNTOUCHED
  and keeps its gates; both verdicts display side by side in the UI.
  Convergence (if ever) needs its own ADR, not drift.
- Persistence: new `gradebook` table (values TEXT + scale payload); F1
  grading tables unchanged. Previous phases' DBs upgrade additively.

## Consequence
Two truthful numbers instead of one forced unification. `percent()` applies
HALF_UP only at the display boundary.
