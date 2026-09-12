# GESTION-ACADEMICA — F4 reuse map (concept → AcademicCore → verdict → why)

| Componente origen | Destino F4 | Tipo | Justificación |
|---|---|---|---|
| Jerarquía Año→Cuatrimestre→Asignatura + estados periodo | University/Degree/Year(con fechas+estado)/Term(genérico) | ADAPT | Concepto sano; F4 añade fechas y generalidad |
| Asignatura (siglas unique-nullable, ECTS, tipo, estados, catálogo optativas, prerrequisitos, notas libres) | Subject + services + safe-delete guards | ADAPT | Reglas probadas; identidad global en vez de rowid |
| Profesor 1:N + validadores email/URL + orden | Professor global + SubjectStaff + mismos validadores | ADAPT | Expresividad + identidad persistente |
| TareaEvento (tipos, prioridad, completada→estado, aula/ubicación/descripción/recordatorio/link validado) | Task extendido (description/location/link/reminder_days) | ADAPT | Campos probados; subject obligatorio (divergencia §1) |
| Tipos examen que autocrean EspacioEstudio | exam-task → StudySpace (F1, intacto) | REUSE_CONCEPT | Ya portado; F4 añade consultas planning |
| EspacioEstudio (refs, secciones, progreso) | StudySpace/StudySession (F1, intacto) | REUSE_CONCEPT | Sin cambios en F4 |
| Componentes/Esquemas/Bloques/nota_final/maximo | domain/grading (F1, intacto) | REUSE_CONCEPT | Sin cambios; gradebook genérico coexiste |
| Horarios/conflictos/expansión | domain/schedule (F1, intacto) | REUSE_CONCEPT | Sin cambios |
| Repaso 0/3/18, racha, hitos, notificaciones | entities (F1, intacto) | REUSE_CONCEPT | Delivery sigue fuera del dominio |
| Flask/routes/templates/Jinja/pywebview/auth-web | — | DO_NOT_MIGRATE | Arquitectura web incompatible |
| SQLAlchemy/Alembic/models.py | — | DO_NOT_MIGRATE | Repos explícitos sqlite3 |
| Scrapers Wuolah/Studocu, guías docentes UPC | — | DO_NOT_MIGRATE | Frágiles y fuera de alcance |
| Apartado legacy, pdf.js vendorizado, backup-zip | — | DO_NOT_MIGRATE | Deuda / fases propias |
| Gradebook genérico (escalas, pesos, opcionales, SubjectResult) | `domain/results.py` + `gradebook` table (nuevo) | REWRITE | No existe equivalente (Float 0–10 no sirve) |
| Consultas planning (upcoming/overdue/pending) | `application/queries.py` (nuevo) | REWRITE | Lógica dispersa en routes; centralizar |
| Import/export académico JSON | `application/academic_io.py` (nuevo) | REWRITE | Backup F1 es snapshot; esto es interoperabilidad |
| Borrado seguro + integridad | guards en repos (nuevo) | REWRITE | FKs ausentes en origen y en F1–F3 |
