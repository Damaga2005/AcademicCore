# SPDX-License-Identifier: MIT
"""F4.2 search history use cases: favourites + recents (no UI, no FTS here)."""

from __future__ import annotations

from datetime import datetime, timezone

from academic_core.domain import planning as PL
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicManagementError


def _err(msg: str, code: str = "AC-ACD-001") -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SearchHistoryService:
    """Favourite and recent searches over SearchHistoryRepository."""

    def __init__(self, history):
        self.history = history

    # -- favourites ------------------------------------------------------
    def add_favourite(self, kind: str, ref: str, title: str,
                      created: str = "") -> bool:
        """Insert; an existing (kind, ref) is a no-op. Returns True if added."""
        try:
            s = PL.SavedSearch(kind, ref, title, created or _now())
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        return self.history.add_favourite(s)

    def is_favourite(self, kind: str, ref: str) -> bool:
        return self.history.is_favourite(kind, ref)

    def list_favourites(self) -> list[PL.SavedSearch]:
        return self.history.favourites()

    def remove_favourite(self, kind: str, ref: str) -> bool:
        """Delete; a missing row is idempotent. Returns True if removed."""
        return self.history.remove_favourite(kind, ref)

    # -- recents -----------------------------------------------------------
    def record_recent(self, kind: str, ref: str, label: str, url: str,
                      accessed: str = "") -> bool:
        """Upsert by (kind, ref); the repository trims to the newest 15.
        Returns True only when the stored row actually changed."""
        try:
            r = PL.RecentSearch(kind, ref, label, url, accessed or _now())
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        return self.history.record_recent(r)

    def list_recents(self) -> list[PL.RecentSearch]:
        return self.history.recents()
