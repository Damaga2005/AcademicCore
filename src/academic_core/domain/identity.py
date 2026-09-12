"""Stable identity scheme for Academic Core.

Format: <kind>:<subject-slug>[:<scope>]:<number|slug>
Examples:
  subject:sistemes-de-mesura
  topic:sistemes-de-mesura:t03
  concept:sistemes-de-mesura:c:00421
  formula:sistemes-de-mesura:f:002847
  resource:sistemes-de-mesura:r:00192
  lab:sistemes-de-mesura:lab:00006
  assignment:sistemes-de-mesura:a:00003

Rules:
- IDs are assigned once at INGEST/creation, stored in SQLite, never derived
  from volatile paths or rowids.
- Reindexing, format conversion, migration or sync MUST preserve IDs.
- Content addressing (sha256) is separate from identity: hash verifies bytes,
  ID verifies lineage.
"""

from __future__ import annotations

import re

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PATTERNS = {
    "subject": re.compile(rf"^subject:{SLUG}$"),
    "topic": re.compile(rf"^topic:{SLUG}:t\d{{2}}$"),
    "concept": re.compile(rf"^concept:{SLUG}:c:\d{{5}}$"),
    "formula": re.compile(rf"^formula:{SLUG}:f:\d{{6}}$"),
    "resource": re.compile(rf"^resource:{SLUG}:r:\d{{5}}$"),
    "lab": re.compile(rf"^lab:{SLUG}:lab:\d{{5}}$"),
    "assignment": re.compile(rf"^assignment:{SLUG}:a:\d{{5}}$"),
}

KINDS = tuple(_PATTERNS)


def validate(stable_id: str) -> str:
    """Return kind if valid, else raise ValueError."""
    for kind, rx in _PATTERNS.items():
        if rx.match(stable_id):
            return kind
    raise ValueError(f"Invalid stable id: {stable_id!r}")


def make(kind: str, subject: str, code: str = "") -> str:
    prefix = {"subject": "subject", "topic": "topic", "concept": "concept",
              "formula": "formula", "resource": "resource", "lab": "lab",
              "assignment": "assignment"}[kind]
    if kind == "subject":
        sid = f"{prefix}:{subject}"
    elif kind == "topic":
        sid = f"{prefix}:{subject}:{code}"
    elif kind == "concept":
        sid = f"{prefix}:{subject}:c:{code}"
    elif kind == "formula":
        sid = f"{prefix}:{subject}:f:{code}"
    elif kind == "resource":
        sid = f"{prefix}:{subject}:r:{code}"
    elif kind == "lab":
        sid = f"{prefix}:{subject}:lab:{code}"
    elif kind == "assignment":
        sid = f"{prefix}:{subject}:a:{code}"
    else:  # pragma: no cover
        raise ValueError(kind)
    validate(sid)
    return sid
