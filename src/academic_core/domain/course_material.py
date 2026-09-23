# SPDX-License-Identifier: MIT
"""Course material (F4.1, pure): documents in the subject context.

Documents are Resources (F2 CAS + versions + provenance, F3/F3.1 AST) —
this module never holds bytes. It adds the *academic* relation that
Gestion-Academica had and AcademicCore lacked:

    Subject ──< CourseDocument >── Resource   (category, group, tags)
    Subject ──< DocumentGroup                 (free subgroup per category)
    Subject ──< ExternalResource              (URL only, never fetched)
    StudySpace ──< StudySpaceDocument >── Resource  (selection for study)
    StudySpace ──< StudySpaceGoal

No filesystem. No network (URL host parsing is string-only, no urllib).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from academic_core.domain.entities import DomainError, _check_url
from academic_core.domain.identity import validate

# Gestion fixed categories (teoria/examenes/laboratorios/otros) + the F4.1
# subject tabs (guía docente, apuntes, problemas). Gestion values map 1:1.
DOC_CATEGORIES = ("guia_docente", "teoria", "apuntes", "problemas",
                  "examenes", "laboratorios", "otros")
GESTION_CATEGORIES = ("teoria", "examenes", "laboratorios", "otros")
STUDY_SECTIONS = ("examenes_anteriores", "teoria", "ejercicios", "laboratorio")
BLOB_STATES = ("stored", "missing")

_WS = re.compile(r"\s+")
_HOST = re.compile(r"^https?://(?:[^@/\s]*@)?([^:/?#\s]+)", re.IGNORECASE)

# Known study-material providers. Detection is by host suffix only; nothing
# is ever fetched (no SSRF surface: URLs are opaque, validated strings).
PROVIDERS = (("wuolah", ("wuolah.com",)), ("studocu", ("studocu.com",)),
             ("drive", ("drive.google.com", "docs.google.com")),
             ("github", ("github.com",)), ("youtube", ("youtube.com", "youtu.be")))


def normalize_name(name: str) -> str:
    """Gestion group-name normalization: trim + collapse inner whitespace."""
    return _WS.sub(" ", name or "").strip()


def url_host(url: str) -> str:
    m = _HOST.match((url or "").strip())
    return m.group(1).lower().rstrip(".") if m else ""


def provider_of(url: str) -> str:
    host = url_host(url)
    for name, suffixes in PROVIDERS:
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return name
    return "other"


def split_tags(raw: str | None) -> tuple[str, ...]:
    """Gestion stored tags as one comma-separated string."""
    if not raw:
        return ()
    return tuple(t.strip() for t in raw.split(",") if t.strip())


@dataclass
class DocumentGroup:
    stable_id: str  # docgroup:<s>:grp:NNNNN
    subject_id: str
    category: str
    name: str
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "docgroup":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if self.category not in DOC_CATEGORIES:
            raise DomainError(f"category must be one of {DOC_CATEGORIES}")
        self.name = normalize_name(self.name)
        if not self.name:
            raise DomainError("DocumentGroup.name is required")


@dataclass
class CourseDocument:
    """A resource placed in a subject's documentation."""
    subject_id: str
    resource_id: str
    category: str = "otros"
    group_id: str = ""
    filename: str = ""
    tags: tuple[str, ...] = ()
    added_at: str = ""  # ISO, metadata only (never part of digests)
    legacy: dict = field(default_factory=dict)  # lossless source metadata

    def __post_init__(self) -> None:
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if validate(self.resource_id) != "resource":
            raise DomainError(f"bad resource_id: {self.resource_id}")
        if self.category not in DOC_CATEGORIES:
            raise DomainError(f"category must be one of {DOC_CATEGORIES}")
        if self.group_id and validate(self.group_id) != "docgroup":
            raise DomainError(f"bad group_id: {self.group_id}")
        self.tags = tuple(dict.fromkeys(t.strip() for t in self.tags if t.strip()))


@dataclass
class ReadingProgress:
    """Viewer state ("continúa donde lo dejaste"), per resource."""
    resource_id: str
    last_page: int | None = None
    percent: str | None = None  # Decimal text 0..100
    zoom: str = ""
    view_mode: str = ""
    scroll: str | None = None
    first_opened: str = ""
    last_opened: str = ""
    total_seconds: int = 0
    sessions: int = 0

    def __post_init__(self) -> None:
        if validate(self.resource_id) != "resource":
            raise DomainError(f"bad resource_id: {self.resource_id}")
        if self.last_page is not None and self.last_page < 1:
            raise DomainError("last_page is 1-based")
        if self.total_seconds < 0 or self.sessions < 0:
            raise DomainError("counters must be >= 0")


@dataclass
class ExternalResource:
    """Wuolah/Studocu/Drive/... link of a subject. URL-only by design."""
    stable_id: str  # link:<s>:lnk:NNNNN
    subject_id: str
    name: str
    url: str
    kind: str = ""  # free label ("apuntes", "repositorio"...)
    order: int = 0
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "link":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not self.name.strip():
            raise DomainError("ExternalResource.name is required")
        if not self.url.strip():
            raise DomainError("ExternalResource.url is required")
        _check_url(self.url, "ExternalResource.url")
        if len(self.url) > 2000:
            raise DomainError("ExternalResource.url too long")
        self.url = self.url.strip()

    @property
    def provider(self) -> str:
        return provider_of(self.url)


@dataclass
class StudySpaceDocument:
    """Reference (never a copy) of a resource inside a study space."""
    space_id: str
    resource_id: str
    section: str = "teoria"
    read: bool = False
    highlighted: bool = False
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.space_id) != "space":
            raise DomainError(f"bad space_id: {self.space_id}")
        if validate(self.resource_id) != "resource":
            raise DomainError(f"bad resource_id: {self.resource_id}")
        if self.section not in STUDY_SECTIONS:
            raise DomainError(f"section must be one of {STUDY_SECTIONS}")


@dataclass
class StudySpaceGoal:
    space_id: str
    text: str
    done: bool = False
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.space_id) != "space":
            raise DomainError(f"bad space_id: {self.space_id}")
        self.text = (self.text or "").strip()
        if not self.text:
            raise DomainError("StudySpaceGoal.text is required")


@dataclass(frozen=True)
class SpaceProgress:
    total: int
    read: int
    goals: int
    goals_done: int

    @property
    def percent(self) -> int:
        # Gestion: round((read / total) * 100); integer percent.
        return round(self.read * 100 / self.total) if self.total else 0


def space_progress(docs: list[StudySpaceDocument], goals: list[StudySpaceGoal]) -> SpaceProgress:
    return SpaceProgress(len(docs), sum(1 for d in docs if d.read),
                         len(goals), sum(1 for g in goals if g.done))
