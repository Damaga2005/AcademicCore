# Domain Model (canonical, single academic model)

```
University → Degree → AcademicYear → Semester → Subject
Subject → Topics → Sections → {Concepts, Formulas, Examples, Exercises}
Subject → Resources | Labs | Assignments | Exams | Projects | Flashcards
```

- `src/academic_core/domain/academic.py`: dataclasses v0 (ORM in Phase 1).
- `src/academic_core/domain/identity.py`: stable ID grammar + validators.
- `src/academic_core/domain/status.py`: IMPLEMENTED|VERIFIED|BENCHMARKED|
  SIMULATED|VISUAL_ONLY|EXPERIMENTAL — no "equivalent to X" without proof.
- Formula: `{id, latex, source_latex, variables, units, topic, concepts,
  provenance{source_path, section, hash}, version}`. Source LaTeX immutable.
