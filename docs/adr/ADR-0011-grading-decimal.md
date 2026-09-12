# ADR-0011 — Grading numerics: Decimal + ROUND_HALF_UP (divergence from legacy)

Date: 2026-09-12 · Status: Accepted

## Context
Gestion-Academica computes grades with Python `float` + `round()` (banker's
rounding, half-even). Phase 1 brief demands adequate numeric types and no
float evaluation errors.

## Decision
Domain grading uses `Decimal` with `ROUND_HALF_UP`, weights/scores/finals
travelling as strings from UI to SQLite. Semantics otherwise identical
(scored-only mean, `maximo` winner, final override, 100%-weight evaluated
rule, 5.0 pass mark).

## Consequence
Max deviation vs legacy: 0.005 (porcentaje) / 0.00005 (media). Equivalence
tests pin agreement within tolerance and exactness on typical cases
(`tests/test_grading.py`). A pass/fail flip from rounding alone is
impossible unless the true value lies within that epsilon of 5.0.
