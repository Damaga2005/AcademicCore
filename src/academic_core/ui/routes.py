# SPDX-License-Identifier: MIT
"""Product routes (UX IA 2026): pure data + history, no Qt.

``area[/section[/item]]`` is the single source of truth for navigation.
Legacy keys used by the dashboard, Go menu and modules dialog
(``overview``, ``lab``, ``logic`` ...) resolve to routes here, so the 13
pinned pages are reached through one table instead of tab-title strings.
"""

from __future__ import annotations

from dataclasses import dataclass

AREAS: tuple[tuple[str, str], ...] = (
    ("home", "Inicio"),
    ("learn", "Aprender"),
    ("practice", "Practicar"),
    ("engineering", "Circuitos electrónicos"),
    ("settings", "Ajustes"),
)


@dataclass(frozen=True)
class Route:
    id: str
    area: str
    label: str
    target: str  # page key resolved by the main window
    section: bool = True  # shown in the contextual section bar
    needs_subject: bool = False


ROUTES: tuple[Route, ...] = (
    Route("home", "home", "Inicio", "dashboard", section=False),
    Route("learn/subject/summary", "learn", "Resumen", "overview", needs_subject=True),
    Route("learn/subject/activities", "learn", "Actividades", "activities", needs_subject=True),
    Route("learn/subject/grades", "learn", "Notas", "grades", needs_subject=True),
    Route("learn/subject/planning", "learn", "Planificación", "planning", needs_subject=True),
    Route("learn/mastery", "learn", "Dominio", "mastery"),
    Route("learn/library", "learn", "Biblioteca", "library"),
    Route("learn/documents", "learn", "Documentos", "documents"),
    Route("learn/math", "learn", "Matemáticas", "math"),
    Route("practice/exercises", "practice", "Ejercicios", "exercises"),
    Route("practice/sessions", "practice", "Sesiones", "sessions"),
    Route("practice/plan", "practice", "Plan", "plan"),
    Route("engineering/circuits", "engineering", "Circuitos", "circuits"),
    Route("engineering/analysis", "engineering", "Análisis", "analysis"),
    Route("engineering/lab", "engineering", "Laboratorio", "lab"),
    Route("engineering/digital-logic", "engineering", "Lógica digital", "digital"),
    Route("engineering/aerospace", "engineering", "Aeroespacial", "aerospace"),
    Route("settings", "settings", "Ajustes", "settings", section=False),
)

_BY_ID = {r.id: r for r in ROUTES}

# Keys accepted by navigate_to()/_navigate() before the shell existed.
LEGACY: dict[str, str] = {
    "home": "home",
    "overview": "learn/subject/summary",
    "activities": "learn/subject/activities",
    "grades": "learn/subject/grades",
    "planning": "learn/subject/planning",
    "resources": "learn/library",
    "documents": "learn/documents",
    "math": "learn/math",
    "exercises": "practice/exercises",
    "sessions": "practice/sessions",
    "plan": "practice/plan",
    "mastery": "learn/mastery",
    "engineering": "engineering/circuits",
    "simulation": "engineering/analysis",
    "lab": "engineering/lab",
    "logic": "engineering/digital-logic",
    "aerospace": "engineering/aerospace",
    "settings": "settings",
}

_AREA_LABEL = dict(AREAS)


def area_label(area: str) -> str:
    return _AREA_LABEL.get(area, area)


def resolve(key: str) -> Route | None:
    """Route for a route id, a legacy key or an area name; None if unknown."""
    if key in _BY_ID:
        return _BY_ID[key]
    if key in LEGACY:
        return _BY_ID[LEGACY[key]]
    if key in _AREA_LABEL:
        return area_default(key)
    return None


def sections(area: str) -> tuple[Route, ...]:
    """Routes of ``area`` shown in the contextual section bar."""
    return tuple(r for r in ROUTES if r.area == area and r.section)


def area_default(area: str, last: str | None = None) -> Route:
    """Landing route of an area: the last visited section, else its first."""
    if last and last in _BY_ID and _BY_ID[last].area == area:
        return _BY_ID[last]
    return next(r for r in ROUTES if r.area == area)


def crumbs(route: Route, subject: str | None = None) -> list[tuple[str, str | None]]:
    """Breadcrumb trail ``[(text, route_id|None)]``.

    Only areas with several sections carry a section tail; a subject
    context is inserted for the subject routes. The last item is text.
    """
    trail: list[tuple[str, str | None]] = [(area_label(route.area), area_default(route.area).id)]
    if len(sections(route.area)) > 1:
        if route.needs_subject:
            trail.append((subject or "Sin asignatura", "learn/subject/summary"))
        trail.append((route.label, None))
    else:
        trail[0] = (trail[0][0], None)
    return trail


def goto_entries() -> list[tuple[str, str]]:
    """``(label, route_id)`` for the command palette's "Go to" group."""
    out = []
    for r in ROUTES:
        if r.section or r.id in ("home", "settings"):
            prefix = "" if r.id in ("home", "settings") else f"{area_label(r.area)}: "
            out.append((f"Ir a {prefix}{r.label}", r.id))
    return out


class History:
    """Back/forward stack of route ids (consecutive duplicates collapse)."""

    def __init__(self, limit: int = 100) -> None:
        self._items: list[str] = []
        self._pos = -1
        self._limit = limit

    @property
    def current(self) -> str | None:
        return self._items[self._pos] if self._pos >= 0 else None

    def push(self, route_id: str) -> None:
        if route_id == self.current:
            return
        del self._items[self._pos + 1:]
        self._items.append(route_id)
        if len(self._items) > self._limit:
            self._items.pop(0)
        self._pos = len(self._items) - 1

    def can_back(self) -> bool:
        return self._pos > 0

    def can_forward(self) -> bool:
        return self._pos < len(self._items) - 1

    def back(self) -> str | None:
        if not self.can_back():
            return None
        self._pos -= 1
        return self._items[self._pos]

    def forward(self) -> str | None:
        if not self.can_forward():
            return None
        self._pos += 1
        return self._items[self._pos]
