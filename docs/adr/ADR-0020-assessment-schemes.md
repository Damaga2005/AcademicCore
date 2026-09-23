# ADR-0020 — Assessment schemes/blocks/components with Decimal (F4.1)

Date: 2026-09-23 · Status: Accepted

## Context
F1 `grade_components` cannot express block weights (weight = sum of
members, CONFLICTS §B) nor minimum grades; Gestion supports both.

## Decision
`domain/evaluation.py` (AssessmentScheme/Block/Component, MinGrade,
WeightedResult) with new tables `assessment_*`, reusing
`grading.aggregate` (ROUND_HALF_UP, ADR-0011). `evaluate_subject`
reproduces Gestion `calcular_estado_notas`; floats are refused at the
boundary (legacy REAL converted with `str(float)`). F1 GradingService and
ADR-0016 gradebook stay untouched.

## Consequence
Equivalence is proven against 400 cases produced by the real Gestion code
(state, grade within 1e-4, items, min-grade flag, applied scheme).
