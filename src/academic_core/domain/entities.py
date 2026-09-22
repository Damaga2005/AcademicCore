"""Canonical academic domain entities (Phase 1).

ONE model for everything: Gestion behavior, resources, assignments, projects
and labs all reference these entities — no parallel per-area models.

Justification per entity (why it exists, not which legacy table it mirrors):
- University/Degree/AcademicYear/Term/Subject: the single hierarchy that lets
  many courses/years/degrees coexist without duplicated systems.
- Topic/Section: subject content structure; sections point at Document AST
  blocks (Phase 3), never inline blobs.
- Professor/SubjectStaff: people associated to subjects, schedules,
  assignments, exams and resources (M2M with role).
- ResourceReference: stable pointer from a subject to a resource managed
  later by the Resource Engine (relationship + minimal metadata only).
- Assignment: rich coursework object (requirements/workspace/files/report/
  rubric/submission/status) ready for TFG/TFM without a second system.
- Exam: time-boxed assessment event, distinct from Assignment (convocatoria,
  duration, allowed resources, result).
- Project: long-lived work container (docs/code/circuits/datasets/milestones).
- Lab: practical session container; instruments/simulations attach in Phase 8.
- Task/Deadline: dated planning items; Task types mirror proven planning
  needs (exam kinds auto-create a StudySpace), Deadline is the due instant
  an Assignment/Task/Exam must meet.
- Grade/GradeComponent/GradeScheme: evaluation records (pure Decimal math in
  domain/grading.py; these are the records).
- Tag/Bookmark/Annotation: cross-cutting marks; Annotation targets any
  resource/document conceptually (no PDF-viewer coupling).
- StudySpace/StudySession/Notification: study planning + streak domain;
  delivery (winotify/Qt) belongs to infrastructure/UI, never here.

Invariants raise DomainError. No Qt. No SQLAlchemy. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re

from academic_core.domain.identity import slugify, validate
from academic_core.errors import AcademicCoreError


class DomainError(AcademicCoreError):
    """Broken domain invariant."""


_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _check_url(value: str, field_name: str) -> str:
    if value and not _URL_RE.match(value.strip()):
        raise DomainError(f"{field_name} must be an http(s) URL")
    return value


# Shared lifecycle for dated academic activities (exam/project/lab).
# F1 Assignment states (draft/active/submitted/graded/archived) are kept as
# the reference vocabulary; activities share the same explicit machine.
ACTIVITY_STATES = ("planned", "active", "submitted", "graded", "cancelled", "archived")
PERIOD_STATES = ("pendiente", "actual", "superado")



# ---------------------------------------------------------------- hierarchies

@dataclass
class University:
    stable_id: str  # university:<slug>
    name: str

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "university":
            raise DomainError(f"bad id: {self.stable_id}")
        if not self.name.strip():
            raise DomainError("University.name is required")


@dataclass
class Degree:
    stable_id: str  # degree:<slug>
    name: str
    university_id: str

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "degree":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.university_id) != "university":
            raise DomainError(f"bad university_id: {self.university_id}")
        if not self.name.strip():
            raise DomainError("Degree.name is required")


@dataclass
class AcademicYear:
    stable_id: str  # year:<label-slug>, e.g. year:2025-26
    label: str  # e.g. "2025-26"
    degree_id: str
    state: str = "pendiente"

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "year":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.degree_id) != "degree":
            raise DomainError(f"bad degree_id: {self.degree_id}")
        if self.state not in PERIOD_STATES:
            raise DomainError(f"Year.state must be one of {PERIOD_STATES}")


TERM_KINDS = ("semestre", "cuatrimestre", "trimestre", "anual", "otro")


@dataclass
class Term:
    """Generic academic period — never hardcodes semester/cuatrimestre."""
    stable_id: str  # term:<slug>
    label: str
    kind: str  # one of TERM_KINDS
    index: int  # 1-based position inside the year
    academic_year_id: str
    start: date | None = None
    end: date | None = None
    state: str = "pendiente"

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "term":
            raise DomainError(f"bad id: {self.stable_id}")
        if self.kind not in TERM_KINDS:
            raise DomainError(f"Term.kind must be one of {TERM_KINDS}")
        if self.index < 1:
            raise DomainError("Term.index is 1-based")
        if validate(self.academic_year_id) != "year":
            raise DomainError(f"bad academic_year_id: {self.academic_year_id}")
        if self.start and self.end and self.end < self.start:
            raise DomainError("Term.end before Term.start")
        if self.state not in PERIOD_STATES:
            raise DomainError(f"Term.state must be one of {PERIOD_STATES}")


SUBJECT_TYPES = ("obligatoria", "optativa", "tfg", "tfm", "otra")
SUBJECT_STATES = ("cursando", "superada", "pendiente", "no_superada", "no_elegida")


@dataclass
class Subject:
    stable_id: str  # subject:<slug>
    code: str  # e.g. "230002" (may be "")
    name: str
    acronym: str  # validated uppercase token when present
    description: str = ""
    credits: float = 0.0
    kind: str = "obligatoria"
    course: int = 0  # year within degree, 0 = unspecified
    term_id: str = ""
    state: str = "pendiente"

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "subject":
            raise DomainError(f"bad id: {self.stable_id}")
        if not self.name.strip():
            raise DomainError("Subject.name is required")
        if self.kind not in SUBJECT_TYPES:
            raise DomainError(f"Subject.kind must be one of {SUBJECT_TYPES}")
        if self.state not in SUBJECT_STATES:
            raise DomainError(f"Subject.state must be one of {SUBJECT_STATES}")
        if self.acronym and not slugify(self.acronym).replace("-", "").isalnum():
            raise DomainError(f"bad acronym: {self.acronym}")
        if self.credits < 0:
            raise DomainError("Subject.credits must be >= 0")
        if self.term_id and validate(self.term_id) != "term":
            raise DomainError(f"bad term_id: {self.term_id}")


@dataclass
class Topic:
    stable_id: str  # topic:<slug>:tNN (canonical); legacy topic:<slug>:NN also valid
    subject_id: str
    index: str  # "03"
    title: str
    description: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "topic":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not self.title.strip():
            raise DomainError("Topic.title is required")


@dataclass
class Section:
    title: str
    body_ref: str = ""  # pointer into Document AST / CAS


# -------------------------------------------------------------------- people

@dataclass
class Professor:
    stable_id: str  # professor:<slug>
    name: str
    email: str = ""
    office: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "professor":
            raise DomainError(f"bad id: {self.stable_id}")
        if not self.name.strip():
            raise DomainError("Professor.name is required")


@dataclass
class SubjectStaff:
    subject_id: str
    professor_id: str
    role: str = "docente"  # docente|coordinador|invitado
    groups: str = ""

    def __post_init__(self) -> None:
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if validate(self.professor_id) != "professor":
            raise DomainError(f"bad professor_id: {self.professor_id}")


# ---------------------------------------------------------------- resources

@dataclass
class ResourceReference:
    """Stable link subject -> resource. The physical bytes belong to the
    future Resource Engine; this record carries relationship + metadata only."""
    resource_id: str  # resource:<s>:r:NNNNN (may pre-exist the bytes)
    subject_id: str
    relationship: str = "material"  # material|bibliografia|dataset|enlace|otro
    title: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        if validate(self.resource_id) != "resource":
            raise DomainError(f"bad resource_id: {self.resource_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")


# ------------------------------------------------------- assignments / exams

ASSIGNMENT_STATES = ("draft", "active", "submitted", "graded", "archived")


@dataclass
class Assignment:
    stable_id: str
    subject_id: str
    title: str
    requirements: str = ""
    resources: list[str] = field(default_factory=list)  # resource stable_ids
    workspace: str = ""  # path/URI managed by later phases
    files: list[str] = field(default_factory=list)
    report_ref: str = ""
    rubric: str = ""
    submission: str = ""
    status: str = "draft"

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "assignment":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not self.title.strip():
            raise DomainError("Assignment.title is required")
        if self.status not in ASSIGNMENT_STATES:
            raise DomainError(f"Assignment.status must be one of {ASSIGNMENT_STATES}")


@dataclass
class Exam:
    stable_id: str
    subject_id: str
    title: str
    day: date | None = None
    duration_min: int = 0
    session: str = ""  # convocatoria: ordinaria|extraordinaria|parcial|...
    allowed_resources: str = ""
    result: str = ""  # free text in F1; structured grading arrives later
    status: str = "planned"
    weight: str | None = None  # Decimal text 0..100, share of subject result
    score: str | None = None  # recorded mark, interpreted by results.Scale
    notes: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "exam":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.duration_min < 0:
            raise DomainError("Exam.duration_min must be >= 0")
        if self.status not in ACTIVITY_STATES:
            raise DomainError(f"Exam.status must be one of {ACTIVITY_STATES}")


@dataclass
class Project:
    stable_id: str
    subject_id: str
    title: str
    description: str = ""
    milestones: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # resource/doc/circuit refs
    status: str = "planned"
    weight: str | None = None
    score: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "project":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.status not in ACTIVITY_STATES:
            raise DomainError(f"Project.status must be one of {ACTIVITY_STATES}")


@dataclass
class Lab:
    stable_id: str
    subject_id: str
    title: str
    description: str = ""
    day: date | None = None
    status: str = "planned"
    score: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "lab":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.status not in ACTIVITY_STATES:
            raise DomainError(f"Lab.status must be one of {ACTIVITY_STATES}")


# ------------------------------------------------------------- tasks / plan

TASK_TYPES = (
    "examen", "examen_parcial", "examen_final", "recuperacion",
    "entrega", "tarea_general", "tutoria", "evento",
)
EXAM_TASK_TYPES = ("examen", "examen_parcial", "examen_final", "recuperacion")
TASK_PRIORITIES = ("alta", "media", "baja")
TASK_STATES = ("pendiente", "hecha", "cancelada")


@dataclass
class Task:
    stable_id: str
    subject_id: str
    title: str
    kind: str = "tarea_general"
    day: date | None = None
    start: str = ""  # "HH:MM" or ""
    end: str = ""  # "HH:MM" or ""
    priority: str = "media"
    state: str = "pendiente"
    notes: str = ""
    description: str = ""
    location: str = ""
    link: str = ""
    reminder_days: int | None = None

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "task":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.kind not in TASK_TYPES:
            raise DomainError(f"Task.kind must be one of {TASK_TYPES}")
        if self.priority not in TASK_PRIORITIES:
            raise DomainError(f"Task.priority must be one of {TASK_PRIORITIES}")
        if self.state not in TASK_STATES:
            raise DomainError(f"Task.state must be one of {TASK_STATES}")
        if (self.start or self.end) and not (self.start and self.end):
            raise DomainError("Task start/end must both be set or both empty")
        if self.start and self.end and self.end <= self.start:
            raise DomainError("Task end must be after start")
        _check_url(self.link, "Task.link")
        if self.reminder_days is not None and self.reminder_days < 0:
            raise DomainError("Task.reminder_days must be >= 0")

    @property
    def is_exam(self) -> bool:
        return self.kind in EXAM_TASK_TYPES


@dataclass
class Deadline:
    target_id: str  # assignment|task|exam stable_id
    due: datetime
    label: str = ""

    def __post_init__(self) -> None:
        validate(self.target_id)  # any entity kind may carry a deadline


# ------------------------------------------------------------------ grading

@dataclass
class GradeComponent:
    name: str
    kind: str  # teoria|parcial|examen_final|laboratorio|otro|bloque
    weight: str  # Decimal as string, 0..100 — strings keep SQLite exact
    score: str | None = None  # Decimal as string 0..10 or None (unevaluated)

    def __post_init__(self) -> None:
        from decimal import Decimal, InvalidOperation
        try:
            w, s = Decimal(self.weight), Decimal(self.score) if self.score else None
        except InvalidOperation as e:
            raise DomainError(f"bad decimal: {e}")
        if not (Decimal(0) <= w <= Decimal(100)):
            raise DomainError("GradeComponent.weight must be 0..100")
        if s is not None and not (Decimal(0) <= s <= Decimal(10)):
            raise DomainError("GradeComponent.score must be 0..10")


@dataclass
class Grade:
    subject_id: str
    scheme: str  # evaluation scheme name ("continua", "final", ...)
    final: str | None = None  # manual override as Decimal string
    components: list[GradeComponent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")


# ------------------------------------------------------------- marks / study

@dataclass
class Tag:
    stable_id: str  # tag:<slug>
    label: str

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "tag":
            raise DomainError(f"bad id: {self.stable_id}")


@dataclass
class Bookmark:
    target_id: str  # any resource/document id
    title: str
    locator: str = ""  # page/section anchor, renderer-agnostic

    def __post_init__(self) -> None:
        validate(self.target_id)


@dataclass
class Annotation:
    target_id: str
    body: str
    color: str = "yellow"
    locator: str = ""
    created: datetime | None = None

    def __post_init__(self) -> None:
        validate(self.target_id)
        if not self.body.strip():
            raise DomainError("Annotation.body is required")


STUDY_SPACE_SECTIONS = ("examenes_anteriores", "teoria", "ejercicios", "laboratorio")
SPACED_INTERVALS = {"no_visto": 0, "flojo": 3, "dominado": 18}


@dataclass
class StudySpace:
    subject_id: str
    exam_task_id: str  # the Task that auto-created it
    title: str
    refs: list[str] = field(default_factory=list)  # resource ids, never copies

    def __post_init__(self) -> None:
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if validate(self.exam_task_id) != "task":
            raise DomainError(f"bad exam_task_id: {self.exam_task_id}")


@dataclass
class StudySession:
    subject_id: str
    day: date
    minutes: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.minutes < 0:
            raise DomainError("StudySession.minutes must be >= 0")


@dataclass
class Notification:
    title: str
    body: str = ""
    due: datetime | None = None
    read: bool = False

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainError("Notification.title is required")
