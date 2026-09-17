"""Stable identity scheme for Academic Core (Phase 1 — extended kinds).

Grammar: <kind>:<subject-slug>[:<scope>]:<number|slug>, plus root kinds
(university/degree/year/term/subject/professor/...) with plain slugs.

Root (no subject scope):  university:<slug>  degree:<slug>  year:<label>
term:<slug>  professor:<slug>  tag:<slug>
Scoped: subject:<slug>  topic:<s>:tNN  concept:<s>:c:NNNNN
formula:<s>:f:NNNNNN  resource:<s>:r:NNNNN  lab:<s>:lab:NNNNN
assignment:<s>:a:NNNNN  project:<s>:p:NNNNN  exam:<s>:e:NNNNN
task:<s>:task:NNNNN

Policy (full text in docs/domain/ID-POLICY.md):
- Assigned once at creation/INGEST, stored as SQLite PRIMARY KEY.
- Never derived from SQL rowids, filesystem paths, or volatile data.
- Reindex/conversion/migration/sync MUST preserve them byte-for-byte.
- Content hash (sha256) is a separate concern: hash verifies bytes,
  stable_id verifies lineage.
- Deterministic when a natural key exists (slug codes); otherwise allocated
  from a persisted per-kind counter (see IdAllocator in this module).
"""

from __future__ import annotations

import re
from unicodedata import combining, normalize

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PATTERNS = {
    "university": re.compile(rf"^university:{SLUG}$"),
    "degree": re.compile(rf"^degree:{SLUG}$"),
    "year": re.compile(rf"^year:[a-z0-9]+(?:-[a-z0-9]+)*$"),
    "term": re.compile(rf"^term:{SLUG}$"),
    "professor": re.compile(rf"^professor:{SLUG}$"),
    "tag": re.compile(rf"^tag:{SLUG}$"),
    "subject": re.compile(rf"^subject:{SLUG}$"),
    "topic": re.compile(rf"^topic:{SLUG}:t\d{{2}}$"),
    "concept": re.compile(rf"^concept:{SLUG}:c:\d{{5}}$"),
    "formula": re.compile(rf"^formula:{SLUG}:f:\d{{6}}$"),
    "resource": re.compile(rf"^resource:{SLUG}:r:\d{{5}}$"),
    "lab": re.compile(rf"^lab:{SLUG}:lab:\d{{5}}$"),
    "assignment": re.compile(rf"^assignment:{SLUG}:a:\d{{5}}$"),
    "project": re.compile(rf"^project:{SLUG}:p:\d{{5}}$"),
    "exam": re.compile(rf"^exam:{SLUG}:e:\d{{5}}$"),
    "task": re.compile(rf"^task:{SLUG}:task:\d{{5}}$"),
    "assessment": re.compile(rf"^assessment:{SLUG}:as:\d{{5}}$"),
    "session": re.compile(rf"^session:{SLUG}:sess:\d{{5}}$"),
}

KINDS = tuple(_PATTERNS)

# Kinds that live under a subject scope and need the subject slug.
_SCOPED = {
    "topic": "t", "concept": "c", "formula": "f", "resource": "r",
    "lab": "lab", "assignment": "a", "project": "p", "exam": "e",
    "task": "task", "assessment": "as", "session": "sess",
}


def validate(stable_id: str) -> str:
    """Return kind if valid, else raise ValueError."""
    for kind, rx in _PATTERNS.items():
        if rx.match(stable_id):
            return kind
    raise ValueError(f"Invalid stable id: {stable_id!r}")


def slugify(text: str) -> str:
    """Deterministic slug: NFKD strip accents, lowercase, non-alnum -> '-'."""
    ascii_ = "".join(c for c in normalize("NFKD", text.strip()) if not combining(c))
    out = re.sub(r"[^a-z0-9]+", "-", ascii_.lower())
    out = re.sub(r"-{2,}", "-", out).strip("-")
    if not out:
        raise ValueError("Cannot slugify empty text")
    return out


def make(kind: str, subject: str, code: str = "") -> str:
    """Build a stable id. Root kinds ignore `code`; scoped kinds require it,
    except subject/topic kept backward compatible with Phase 0 callers."""
    if kind in ("university", "degree", "year", "term", "professor", "tag"):
        sid = f"{kind}:{subject}"
    elif kind == "subject":
        sid = f"subject:{subject}"
    elif kind == "topic":
        sid = f"topic:{subject}:{code}"
    elif kind in _SCOPED:
        sid = f"{kind}:{subject}:{_SCOPED[kind]}:{code}"
    else:
        raise ValueError(f"Unknown kind: {kind}")
    validate(sid)
    return sid


class IdAllocator:
    """Per-kind sequential allocator backed by caller-provided persistence.

    Pass `next_counters` (dict kind->last used int) loaded from SQLite and
    call `persist` hook after allocation. Deterministic for fixed slugs via
    `make()`; sequential for entities without natural keys. Widths follow the
    grammar (5 digits; formulas 6; topics 2).
    """

    _WIDTHS = {"topic": 2, "formula": 6}

    def __init__(self, counters: dict[str, int] | None = None):
        self.counters: dict[str, int] = dict(counters or {})

    def allocate(self, kind: str, subject: str = "") -> str:
        width = self._WIDTHS.get(kind, 5)
        n = self.counters.get(kind, 0) + 1
        self.counters[kind] = n
        code = str(n).zfill(width)
        if kind in _SCOPED or kind in ("topic",):
            return make(kind, subject, code)
        return make(kind, code)

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
