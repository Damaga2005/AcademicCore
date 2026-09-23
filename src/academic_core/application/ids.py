# SPDX-License-Identifier: MIT
"""Stable-id allocation for F4.1 use cases (persisted per-kind counters)."""

from __future__ import annotations

from academic_core.domain.identity import GENERAL_SCOPE, IdAllocator


def scope_of(subject_id: str) -> str:
    """Subject slug used as id scope; ``general`` when there is no subject."""
    return subject_id.split(":", 1)[1] if subject_id and ":" in subject_id else GENERAL_SCOPE


def allocate(academic, kind: str, subject_id: str = "") -> str:
    """Allocate the next id of ``kind`` and persist the counter.

    ``academic`` is the AcademicRepository (owner of ``id_counters``)."""
    alloc = IdAllocator(academic.load_counters())
    sid = alloc.allocate(kind, scope_of(subject_id))
    academic.save_counters(alloc.snapshot())
    return sid
