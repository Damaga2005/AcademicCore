# SPDX-License-Identifier: MIT
"""F4.2 preferences: validation, limits, None, JSON canonical, legacy."""
import pytest

from academic_core.application.personal import (
    ABANDONED_SUBJECT_DAYS,
    EXAM_REMINDER_DAYS,
    TARGET_AVERAGE,
    THEME,
    WIDGETS_HIDDEN,
    WIDGETS_ORDER,
    PreferencesService,
    normalize_legacy,
)
from academic_core.errors import AcademicManagementError


def _prefs(core):
    return PreferencesService(core.personal)


def _core(tmp_path, tag="data"):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_valid_values_and_limits(tmp_path):
    prefs = _prefs(_core(tmp_path))
    prefs.update(THEME, "oscuro")
    prefs.update(EXAM_REMINDER_DAYS, 7)
    prefs.update(ABANDONED_SUBJECT_DAYS, 14)
    prefs.update(TARGET_AVERAGE, "7.5")
    prefs.update(WIDGETS_ORDER, ["calendario", "recordatorios"])
    assert prefs.get(THEME) == "oscuro"
    assert prefs.get(EXAM_REMINDER_DAYS) == 7
    assert str(prefs.get(TARGET_AVERAGE)) == "7.5"
    assert prefs.get(WIDGETS_ORDER) == ["calendario", "recordatorios"]
    assert prefs.get(WIDGETS_HIDDEN, "dflt") == "dflt"
    assert prefs.all()[THEME] == "oscuro"


def test_none_clears_and_negatives_rejected(tmp_path):
    prefs = _prefs(_core(tmp_path))
    prefs.update(TARGET_AVERAGE, "8")
    prefs.update(TARGET_AVERAGE, None)
    assert prefs.get(TARGET_AVERAGE) is None
    prefs.update(TARGET_AVERAGE, "")
    assert prefs.get(TARGET_AVERAGE) is None
    for key, bad in ((EXAM_REMINDER_DAYS, 0), (EXAM_REMINDER_DAYS, -3),
                     (ABANDONED_SUBJECT_DAYS, -1), (THEME, "azul"),
                     (TARGET_AVERAGE, "11"), (TARGET_AVERAGE, "-1"),
                     (TARGET_AVERAGE, "siete"), (WIDGETS_ORDER, "no-lista"),
                     (WIDGETS_ORDER, ["ok", 7]), (WIDGETS_ORDER, [""]),
                     (EXAM_REMINDER_DAYS, "siete"), (EXAM_REMINDER_DAYS, True)):
        with pytest.raises(AcademicManagementError) as e:
            prefs.update(key, bad)
        assert e.value.code == "AC-ACD-004"
    with pytest.raises(AcademicManagementError) as e:
        prefs.update("f42.inventada", 1)
    assert e.value.code == "AC-ACD-002"
    with pytest.raises(AcademicManagementError):
        prefs.get("f42.inventada")


def test_widgets_empty_and_canonical_serialization(tmp_path):
    prefs = _prefs(_core(tmp_path))
    prefs.update(WIDGETS_ORDER, [])
    assert prefs.get(WIDGETS_ORDER) == []
    prefs.update(WIDGETS_HIDDEN, ["b", "a", "b"])
    assert prefs.get(WIDGETS_HIDDEN) == ["b", "a"]  # deduped, order kept
    raw = prefs.personal.setting(WIDGETS_HIDDEN)
    assert raw == '["b","a"]'  # canonical JSON, never CSV
    import json
    assert json.loads(raw) == ["b", "a"]
    prefs.personal.set_setting(WIDGETS_ORDER, "not-json{{{")
    with pytest.raises(AcademicManagementError) as e:
        prefs.get(WIDGETS_ORDER)
    assert e.value.code == "AC-ACD-004"


def test_legacy_normalization_is_read_only(tmp_path):
    core = _core(tmp_path)
    legacy = {"gestion.tema": "oscuro", "gestion.dias_aviso_examen": "7",
              "gestion.dias_asignatura_abandonada": "14",
              "gestion.widgets_orden": "recordatorios, calendario",
              "gestion.widgets_ocultos": ""}
    values, skipped = normalize_legacy(legacy)
    assert values == {THEME: "oscuro", EXAM_REMINDER_DAYS: 7,
                      ABANDONED_SUBJECT_DAYS: 14,
                      WIDGETS_ORDER: ["recordatorios", "calendario"]}
    assert skipped == []
    assert legacy["gestion.widgets_orden"] == "recordatorios, calendario"  # unmutated
    bad, skipped = normalize_legacy({"gestion.tema": "azul",
                                     "gestion.dias_aviso_examen": "cero",
                                     "gestion.widgets_orden": "a,b"})
    assert bad == {WIDGETS_ORDER: ["a", "b"]}
    assert sorted(skipped) == ["gestion.dias_aviso_examen", "gestion.tema"]


def test_serialization_deterministic(tmp_path):
    prefs = _prefs(_core(tmp_path))
    prefs.update(WIDGETS_ORDER, ["zeta", "alfa"])
    first = prefs.personal.setting(WIDGETS_ORDER)
    prefs.update(WIDGETS_ORDER, ["zeta", "alfa"])
    assert prefs.personal.setting(WIDGETS_ORDER) == first == '["zeta","alfa"]'
