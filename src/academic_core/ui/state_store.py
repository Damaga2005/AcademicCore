# SPDX-License-Identifier: MIT
"""UI-owned persistence: window/route state and recently opened sections.

Certified data (subjects, deadlines, search history) stays in the
application layer; this only remembers where the user was.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSettings

RECENT_ROUTES_KEY = "shell/recent_routes"
RECENT_ROUTES_LIMIT = 8


def shell_settings() -> QSettings:
    """The app's QSettings, or an .ini in ACORE_DATA_DIR when set
    (tests and portable runs stay isolated from the user's registry)."""
    data_dir = os.environ.get("ACORE_DATA_DIR")
    if data_dir:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        return QSettings(str(Path(data_dir) / "ui-state.ini"), QSettings.Format.IniFormat)
    return QSettings("Academic Core", "Academic Core")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # microseconds: orders same-second visits


def recent_routes(settings: QSettings | None = None) -> list[dict]:
    """``[{"route": id, "label": text, "at": iso}]``, newest first."""
    raw = (settings or shell_settings()).value(RECENT_ROUTES_KEY, "[]")
    try:
        items = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("route") and i.get("label")
            and i.get("at")]


def push_recent_route(route_id: str, label: str, at: str | None = None,
                      settings: QSettings | None = None) -> None:
    """Remember a section the user opened (deduplicated, newest first)."""
    st = settings or shell_settings()
    items = [i for i in recent_routes(st) if i["route"] != route_id]
    items.insert(0, {"route": route_id, "label": label, "at": at or now_iso()})
    st.setValue(RECENT_ROUTES_KEY, json.dumps(items[:RECENT_ROUTES_LIMIT]))
