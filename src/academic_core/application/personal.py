# SPDX-License-Identifier: MIT
"""F4.2 preferences: validated settings under the ``f42.*`` namespace.

Wraps `PersonalRepository.set_setting/setting` (no new table). Widget lists
persist as canonical JSON UTF-8 (never CSV); scalars persist as plain text.
Legacy ``gestion.*`` values are only *read* by `normalize_legacy()` into
validated F4.2 objects — Gestion is never mutated.
"""

from __future__ import annotations

import json

from academic_core.domain import evaluation as EV
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicManagementError

THEME = "f42.theme"
EXAM_REMINDER_DAYS = "f42.exam_reminder_days"
ABANDONED_SUBJECT_DAYS = "f42.abandoned_subject_days"
WIDGETS_ORDER = "f42.widgets_order"
WIDGETS_HIDDEN = "f42.widgets_hidden"
TARGET_AVERAGE = "f42.target_average"

THEMES = ("claro", "oscuro")
ALL_KEYS = (THEME, EXAM_REMINDER_DAYS, ABANDONED_SUBJECT_DAYS, WIDGETS_ORDER,
            WIDGETS_HIDDEN, TARGET_AVERAGE)


def _err(msg: str, code: str = "AC-ACD-001") -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _check_days(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            ivalue = int(str(value).strip())
        except (ValueError, TypeError):
            raise _err(f"{name} must be an integer >= 1", "AC-ACD-004") from None
        value = ivalue
    if value < 1:
        raise _err(f"{name} must be an integer >= 1", "AC-ACD-004")
    return value


def _check_widgets(value, name: str) -> list[str]:
    items = value if isinstance(value, list) else None
    if items is None:
        raise _err(f"{name} must be a list of strings", "AC-ACD-004")
    out: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise _err(f"{name} must be a list of strings", "AC-ACD-004")
        if item.strip() not in out:
            out.append(item.strip())
    return out


def _canonical_json(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=False)


def normalize_legacy(raw: dict) -> tuple[dict, list[str]]:
    """Validate legacy ``gestion.*`` settings into F4.2 values (pure).

    Returns (values, skipped): invalid legacy entries are listed in
    `skipped`, never raised, never written back. Nothing is mutated.
    """
    values: dict[str, object] = {}
    skipped: list[str] = []
    get = raw.get
    if get("gestion.tema") in THEMES:
        values[THEME] = get("gestion.tema")
    elif get("gestion.tema") is not None:
        skipped.append("gestion.tema")
    for legacy_key, f42_key in (("gestion.dias_aviso_examen", EXAM_REMINDER_DAYS),
                                ("gestion.dias_asignatura_abandonada",
                                 ABANDONED_SUBJECT_DAYS)):
        raw_value = get(legacy_key)
        if raw_value is None:
            continue
        try:
            values[f42_key] = _check_days(raw_value, f42_key)
        except AcademicManagementError:
            skipped.append(legacy_key)
    for legacy_key, f42_key in (("gestion.widgets_orden", WIDGETS_ORDER),
                                ("gestion.widgets_ocultos", WIDGETS_HIDDEN)):
        raw_value = get(legacy_key)
        if raw_value is None or raw_value == "":
            continue
        try:
            values[f42_key] = _check_widgets(
                [w.strip() for w in str(raw_value).split(",") if w.strip()], f42_key)
        except AcademicManagementError:
            skipped.append(legacy_key)
    return values, skipped


class PreferencesService:
    """Validated read/write of the ``f42.*`` namespace."""

    def __init__(self, personal):
        self.personal = personal

    def get(self, key: str, default=None):
        self._check_key(key)
        raw = self.personal.setting(key)
        if raw is None:
            return default
        return self._parse(key, raw)

    def all(self) -> dict:
        out = {}
        for key in ALL_KEYS:
            value = self.get(key)
            if value is not None:
                out[key] = value
        return out

    def update(self, key: str, value) -> None:
        self._check_key(key)
        self.personal.set_setting(key, self._serialize(key, value))

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _check_key(key: str) -> None:
        if key not in ALL_KEYS:
            raise _err(f"unknown preference: {key}", "AC-ACD-002")

    @staticmethod
    def _serialize(key: str, value) -> str:
        if key == THEME:
            if value not in THEMES:
                raise _err("theme must be 'claro' or 'oscuro'", "AC-ACD-004")
            return value
        if key in (EXAM_REMINDER_DAYS, ABANDONED_SUBJECT_DAYS):
            return str(_check_days(value, key))
        if key in (WIDGETS_ORDER, WIDGETS_HIDDEN):
            return _canonical_json(_check_widgets(value, key))
        if key == TARGET_AVERAGE:
            if value is None or value == "":
                return ""
            try:
                return str(EV.to_decimal(value, "target_average", low=0, high=10))
            except DomainError as e:
                raise _err(str(e), "AC-ACD-004") from e
        raise _err(f"unknown preference: {key}", "AC-ACD-002")  # pragma: no cover

    @staticmethod
    def _parse(key: str, raw: str):
        try:
            if key == THEME:
                if raw not in THEMES:
                    raise ValueError(raw)
                return raw
            if key in (EXAM_REMINDER_DAYS, ABANDONED_SUBJECT_DAYS):
                return _check_days(int(raw), key)
            if key in (WIDGETS_ORDER, WIDGETS_HIDDEN):
                parsed = json.loads(raw)
                return _check_widgets(parsed, key)
            if key == TARGET_AVERAGE:
                if raw == "":
                    return None
                return EV.to_decimal(raw, "target_average", low=0, high=10)
        except (ValueError, DomainError, AcademicManagementError) as e:
            raise _err(f"stored preference {key} is corrupt: {e}", "AC-ACD-004") from e
        raise _err(f"unknown preference: {key}", "AC-ACD-002")  # pragma: no cover
