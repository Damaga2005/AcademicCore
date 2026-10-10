# SPDX-License-Identifier: MIT
"""UX IA 2026 route table contracts (pure, no Qt)."""

from __future__ import annotations

from academic_core.ui import routes


def test_legacy_keys_resolve_to_known_routes():
    for key, rid in routes.LEGACY.items():
        r = routes.resolve(key)
        assert r is not None and r.id == rid, key
    assert routes.resolve("nope") is None


def test_every_page_of_the_ia_is_reachable():
    targets = {r.target for r in routes.ROUTES}
    assert targets == {"dashboard", "overview", "activities", "grades", "planning", "mastery", "library",
                       "documents", "math", "exercises", "sessions", "plan", "circuits", "analysis",
                       "lab", "digital", "aerospace", "settings"}


def test_areas_and_sections():
    assert [a for a, _ in routes.AREAS] == ["home", "learn", "practice", "engineering", "settings"]
    assert [r.label for r in routes.sections("learn")] == [
        "Resumen", "Actividades", "Notas", "Planificación", "Dominio", "Biblioteca", "Documentos",
        "Matemáticas"]
    assert [r.label for r in routes.sections("practice")] == ["Ejercicios", "Sesiones", "Plan"]
    assert [r.label for r in routes.sections("engineering")] == [
        "Circuitos", "Análisis", "Laboratorio", "Lógica digital", "Aeroespacial"]
    assert routes.sections("home") == ()


def test_area_default_remembers_last_section():
    assert routes.area_default("learn").id == "learn/subject/summary"
    assert routes.area_default("learn", "learn/library").id == "learn/library"
    assert routes.area_default("learn", "engineering/lab").id == "learn/subject/summary"


def test_aerospace_is_its_own_route_not_simulation():
    """Audit H-03: the Aerospace module must not land on the Simulation page."""
    assert routes.resolve("aerospace").target == "aerospace"
    assert routes.resolve("simulation").target == "analysis"


def test_crumbs_only_where_they_orient():
    subject = routes.crumbs(routes.resolve("learn/subject/grades"), "Circuitos I")
    assert [t for t, _ in subject] == ["Aprender", "Circuitos I", "Notas"]
    assert subject[-1][1] is None and subject[0][1] == "learn/subject/summary"
    assert [t for t, _ in routes.crumbs(routes.resolve("engineering/lab"))] == ["Circuitos electrónicos", "Laboratorio"]
    assert [t for t, _ in routes.crumbs(routes.resolve("practice/sessions"))] == ["Practicar", "Sesiones"]
    assert routes.crumbs(routes.resolve("home")) == [("Inicio", None)]


def test_goto_entries_cover_every_section():
    labels = [label for label, _ in routes.goto_entries()]
    ids = {rid for _, rid in routes.goto_entries()}
    assert ids == {r.id for r in routes.ROUTES}
    assert "Ir a Circuitos electrónicos: Lógica digital" in labels


def test_history_back_forward_and_truncation():
    h = routes.History()
    for rid in ("home", "learn/library", "learn/library", "settings"):
        h.push(rid)
    assert h.current == "settings" and not h.can_forward()
    assert h.back() == "learn/library" and h.back() == "home" and h.back() is None
    assert h.forward() == "learn/library"
    h.push("practice/exercises")  # new branch drops the forward stack
    assert not h.can_forward() and h.current == "practice/exercises"


def test_history_limit():
    h = routes.History(limit=3)
    for rid in ("home", "settings", "learn/library", "practice/exercises"):
        h.push(rid)
    assert h.back() == "learn/library" and h.back() == "settings" and h.back() is None
