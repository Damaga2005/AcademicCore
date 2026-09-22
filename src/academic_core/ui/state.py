# SPDX-License-Identifier: MIT
"""F15 UI states (IDLE / RUNNING / SUCCESS / WARNING / ERROR).

Single enum; no scattered boolean flags.
"""

from __future__ import annotations

from enum import Enum


class UiState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
