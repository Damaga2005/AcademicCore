"""Canonical academic domain model (Phase 0 — dataclasses, no ORM yet).

Single academic model: University -> Degree -> AcademicYear -> Semester -> Subject.
One subject hosts Topics/Sections/Concepts/Formulas/Resources/Labs/Assignments/
Exams/Projects/Flashcards. No parallel per-subject systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class University:
    stable_id: str
    name: str


@dataclass
class Degree:
    stable_id: str
    name: str
    university_id: str


@dataclass
class AcademicYear:
    stable_id: str
    label: str  # e.g. "2025-26"
    degree_id: str


@dataclass
class Semester:
    stable_id: str
    index: int
    academic_year_id: str


@dataclass
class Subject:
    stable_id: str  # subject:<slug>
    slug: str
    name: str
    semester_id: str = ""


@dataclass
class Section:
    title: str
    body_ref: str = ""  # pointer into Document AST / CAS, not inline blob


@dataclass
class Topic:
    stable_id: str  # topic:<slug>:tNN
    subject_id: str
    index: str
    title: str
    sections: list[Section] = field(default_factory=list)


@dataclass
class Concept:
    stable_id: str
    topic_id: str
    term: str
    definition_ref: str = ""


@dataclass
class Formula:
    """First-class formula. Never auto-rewritten without provenance."""
    stable_id: str
    latex: str
    source_latex: str  # original representation, immutable
    topic_id: str = ""
    concept_ids: list[str] = field(default_factory=list)
    variables: list[dict] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)  # source_path, section, hash
    version: int = 1


@dataclass
class Resource:
    stable_id: str
    subject_id: str
    kind: str  # pdf, html, md, latex, docx, pptx, image, csv, json, zip, dataset
    cas_hash: str  # sha256 of bytes in CAS
    provenance: dict = field(default_factory=dict)


@dataclass
class Lab:
    stable_id: str
    subject_id: str
    title: str


@dataclass
class Assignment:
    stable_id: str
    subject_id: str
    title: str
    status: str = "draft"  # draft|active|submitted|graded
