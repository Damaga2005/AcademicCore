# F4-PLAN — Academic Management Engine

Date: 2026-09-12 · Base: F3 `bc67c76` (123 passed, 2 skipped; tree clean)

## Pre-work (done, before any code)
- Full inspection F1–F3 + Gestion reference (fields, states, validators).
- `GESTION-ACADEMICA-F4-AUDIT.md` + `GESTION-ACADEMICA-F4-REUSE-MAP.md`.
- Decisions (no silent patches): keep F1 assignment states; Task requires
  subject; Professor global+SubjectStaff; generic gradebook coexists with F1
  0–10 engine; terms/years gain dates+state; repo-layer delete guards.

## New code (no F5)
- `domain/results.py`: Scale (numeric min/max | letter map | pass_fail),
  Grade (Decimal value, weight, optional, date, notes), normalize→ratio,
  WeightedGrade math, SubjectResult (overall/evaluated/total/state),
  all-Decimal, no floats. ADR-0016.
- Entities (additive): Task += description/location/link/reminder_days;
  Exam/Project/Lab += status/weight/score/notes; Topic += description;
  Term/AcademicYear += state (+dates already on Term).
- Migration `008_academic_f4.sql` (ADD COLUMNs with defaults + `gradebook`
  table + `prerequisites` table); additive over F3 bases; reopen-tested.
- Repos: delete_* guards (children block parent delete → IntegrityError),
  gradebook CRUD, prerequisites CRUD, extended field mapping.
- `application/queries.py`: subjects_by_term, activities_by_subject,
  upcoming/overdue deadlines, grades_by_subject, pending_assignments,
  upcoming_exams, planning_summary. UI never touches repos/SQL.
- `application/facade.py`: `AcademicApp` wiring (db+repos+services+queries+
  io); UI imports application+domain only.
- `application/academic_io.py`: JSON export/import (schema_version,
  id-preserving, validated, error list, no cloud).
- UI `ui/` package: tree navigation University→Subject, subject detail
  (Topics/Resources/Assignments/Exams/Projects/Labs/Tasks/Grades), planning
  view, CRUD dialogs; `app.py` becomes thin entry. No Qt Designer.
- Arch tests: domain⊄{Qt,SQLAlchemy}; application⊄widgets; ui⊄{infrastructure,
  sqlite3}; no Flask anywhere; facade is the only wiring point.

## Tests
`test_results.py` (scales/weights/optional/rounding/edge), `test_queries.py`,
`test_academic_io.py`, `test_integrity.py` (guards/orphans/dupes/invalid),
`test_ui_academic.py` (navigation+CRUD offscreen), `test_academic_perf.py`
(tree load, deadline/grade queries, reopen), security via integrity+io
(malicious strings/IDs/paths/SQL). Full gate F0–F4 in one run.
