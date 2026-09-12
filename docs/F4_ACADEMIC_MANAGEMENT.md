# F4 Academic Management (canonical model + use cases + rules)

## Model
University → Degree → AcademicYear (dates+state) → Term (generic kind, dates,
state `pendiente/actual/superado`) → Subject (code/name/acronym/credits/kind/
course/state + prerequisites M2M) → Topics (ordered, described) |
ResourceReferences | Assignments (draft/active/submitted/graded/archived) |
Exams/Projects/Labs (planned/active/submitted/graded/cancelled/archived +
weight/score/notes) | Tasks (8 kinds, states, priority, description/location/
validated-link/reminder) | Deadlines (per activity + implicit task-day/exam-day)
| Grades: F1 0–10 engine (untouched) + generic gradebook (scales/weights/
optional/partial).

## Use cases (application layer)
AcademicService (CRUD + safe deletes), ResultsService (record/compute),
ScheduleService, AcademicQueries (tree/activities/upcoming/overdue/pending/
exams/grades), AcademicIO (JSON export/import, id-preserving, validated),
BackupService, IngestionService, DocumentService. UI talks ONLY to
`AcademicApp` facade.

## Rules
- Stable ids everywhere (F1 policy); counters persisted; reopen-safe.
- Decimal for all grade math; no floats cross the boundary.
- Delete guards: children block parents (IntegrityError); deadlines cascade
  with their activity; exam-tasks with study spaces are protected.
- Partial results are explicit (`en_progreso` + evaluated/total weights).
- Links validated (http(s)), never fetched. No secrets in SQLite/exports.
- Additive migrations only (008); F3 bases upgrade without data loss.

## Persistence / migrations
`008_academic_f4.sql`: ADD COLUMNs with defaults + `gradebook` +
`prerequisites`. Reopen-tested; rerun-safe via schema_version.

## UI
Tree University→Subject + workspace tabs (Overview/Activities/Grades/
Planning/Resources) + CRUD dialogs + JSON export/import. Offscreen-tested.

## Limits of F4
No RAG/embeddings/AI/KB, no OneDrive/sync, no engineering/simulation/GUM,
no exam generation/correction, no adaptive/flashcards engine, no installer,
no plugins. Interfaces for those arrive with their phases.
