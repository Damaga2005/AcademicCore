# Relation diagram (Phase 1)

```
University 1──* Degree 1──* AcademicYear 1──* Term 1──* Subject
Subject 1──* Topic                        Professor *──* Subject (SubjectStaff, role+groups)
Subject 1──* ResourceReference ──> resource:<id>  (bytes owned by future Resource Engine)
Subject 1──* Assignment 1──* Deadline     Subject 1──* Exam
Subject 1──* Project                      Subject 1──* Lab
Subject 1──* Task ──(exam kinds)──> StudySpace (auto-created, refs only)
Task/Assignment/Exam 1──* Deadline        Subject 1──* ScheduleSeries (value object)
Subject+Scheme 1──* GradeComponent (+blocks) ──> FinalVerdict (computed, not stored)
Subject 1──* StudySession                 Tag / Bookmark / Annotation ──> any target id
```

Cardinality notes: Degree/Year/Term chain is strict (no orphan subjects —
`term_id` required at creation). Staff is the only M2M. Annotations and
bookmarks use renderer-agnostic locators (no PDF-viewer coupling).
StudySpaces reference resources; they never copy bytes.
