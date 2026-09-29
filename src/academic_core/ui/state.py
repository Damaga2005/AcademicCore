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


def set_busy(state: UiState, *buttons) -> None:
    """While RUNNING the actions that would start another run are locked; they come back after.

    Only buttons this function disabled are re-enabled, so a button that was disabled for another
    reason (nothing to replay yet) is never switched on by accident.
    """
    for b in buttons:
        if state == UiState.RUNNING:
            if b.isEnabled():
                b.setEnabled(False)
                b.setProperty("busyLocked", True)
        elif b.property("busyLocked"):
            b.setProperty("busyLocked", False)
            b.setEnabled(True)
