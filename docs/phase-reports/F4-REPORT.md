# F4-REPORT — Academic Management Engine

Date: 2026-09-12 · Base: F3 `bc67c76` (123 passed, 2 skipped → 145 + 2 kept)

## Pre-work (before code)
Full F1–F3 inspection + Gestion reference audit (fields, states, validators,
problems) → `GESTION-ACADEMICA-F4-AUDIT.md` + `GESTION-ACADEMICA-F4-REUSE-MAP.md`
(9 REUSE_CONCEPT, 4 ADAPT, 4 REWRITE, 7 DO_NOT_MIGRATE) + `F4-PLAN.md`.
Decisions: keep F1 assignment states; Task requires subject; Professor
global+SubjectStaff; generic gradebook beside F1 engine; dates+states on
periods; repo-layer delete guards.

## Built
- `domain/results.py`: Scale/Grade/SubjectResult, all-Decimal, partial
  honesty via planned weight, order-independent (ADR-0016).
- Entities additively extended (task description/location/link/reminder,
  exam/project/lab status+weight/score/notes, topic description, period
  states); old constructors still valid (defaults).
- Migration `008_academic_f4` (additive) + `GradebookRepository` +
  `prerequisites` + delete guards (`IntegrityError`) + deadline cascades.
- `AcademicQueries` (tree/activities/upcoming/overdue/pending/exams/grades),
  `ResultsService`, `AcademicIO` (JSON, id-preserving, validate-then-write),
  `AcademicApp` facade (sole UI wiring point).
- `ui/` package: tree navigation, workspace tabs, CRUD dialogs, JSON io,
  Resources tab on facade; `app.py` thin entry.
- Tests: results(5) queries(3) integrity(5) io(3) ui-academic(3) perf(1);
  arch extended (ui⊄infra, no Flask); security via integrity/io guards.

## Debt / limits
F1 scheme block-`%` (unchanged), exam-task↔task duplication by design
(planning item vs assessment event), tree() is N+1 queries (fine at desktop
scale; perf-measured), no GPA system (not required), no visual calendar.
