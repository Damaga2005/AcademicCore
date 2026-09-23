# SPDX-License-Identifier: MIT
"""Personal planning records (F4.1, pure): milestones, quick notes and the
preserved spaced-repetition concept records.

- Milestone  <- Gestion `Hito` (certifications / personal projects).
  Optionally tied to a subject (F4.1 extension; Gestion hitos were global).
- QuickNote  <- Gestion `NotaRapida` (global scratch pad, 1000 chars).
- StudyConcept <- Gestion `Concepto`: DATA ONLY. The review scheduling
  (0/3/18 days) belongs to F11 (SRS); F4.1 preserves the records and their
  dates so F11 starts from real history instead of an empty table.

No Qt. No SQLite. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate

MILESTONE_STATES = ("pendiente", "en_progreso", "hecho")
NEXT_MILESTONE_STATE = {"pendiente": "en_progreso", "en_progreso": "hecho",
                        "hecho": "pendiente"}
CONCEPT_STATES = ("no_visto", "flojo", "dominado")
QUICK_NOTE_MAX = 1000


@dataclass
class Milestone:
    stable_id: str  # milestone:<slug>
    name: str
    state: str = "pendiente"
    day: date | None = None
    order: int = 0
    subject_id: str = ""

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "milestone":
            raise DomainError(f"bad id: {self.stable_id}")
        self.name = (self.name or "").strip()
        if not self.name:
            raise DomainError("Milestone.name is required")
        if self.state not in MILESTONE_STATES:
            raise DomainError(f"Milestone.state must be one of {MILESTONE_STATES}")
        if self.subject_id and validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")

    def cycled(self) -> "Milestone":
        """Dashboard click: pendiente -> en_progreso -> hecho -> pendiente."""
        return Milestone(self.stable_id, self.name, NEXT_MILESTONE_STATE[self.state],
                         self.day, self.order, self.subject_id)


@dataclass
class QuickNote:
    stable_id: str  # note:<slug>
    text: str
    created: str = ""  # ISO timestamp, metadata only

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "note":
            raise DomainError(f"bad id: {self.stable_id}")
        self.text = (self.text or "").strip()
        if not self.text:
            raise DomainError("QuickNote.text is required")
        if len(self.text) > QUICK_NOTE_MAX:
            raise DomainError(f"QuickNote.text max {QUICK_NOTE_MAX} chars")


@dataclass
class StudyConcept:
    stable_id: str  # concept:<s>:c:NNNNN
    subject_id: str
    name: str
    state: str = "no_visto"
    last_review: date | None = None
    next_review: date | None = None

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "concept":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not (self.name or "").strip():
            raise DomainError("StudyConcept.name is required")
        if self.state not in CONCEPT_STATES:
            raise DomainError(f"StudyConcept.state must be one of {CONCEPT_STATES}")


def due_concepts(concepts: list[StudyConcept], today: date) -> list[StudyConcept]:
    """Read-only query kept for the Home "repaso hoy" counter (Gestion
    parity). Scheduling/re-rating stays in F11."""
    return sorted((c for c in concepts if c.next_review is not None and c.next_review <= today),
                  key=lambda c: (c.next_review, c.stable_id))
