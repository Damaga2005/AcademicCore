# SPDX-License-Identifier: MIT
"""Dialog motion: one bounded pop-in (UI only, no engine involved)."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation

# Motion tokens (DESIGN-SYSTEM-2026 §2.4), milliseconds.
FAST, BASE, SLOW = 100, 140, 180


def reduced_motion() -> bool:
    """True when the user turned animations off (Windows setting or env override)."""
    if os.environ.get("ACORE_REDUCE_MOTION") == "1":
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        enabled = ctypes.c_int(1)
        SPI_GETCLIENTAREAANIMATION = 0x1042
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
        return not enabled.value
    except Exception:
        return False


def duration(token_ms: int) -> int:
    """Token duration, or 0 when motion is reduced."""
    return 0 if reduced_motion() else token_ms


def pop_in(dialog, duration_ms: int = 150) -> QPropertyAnimation:
    """Bounded dialog appearance (opacity fade, OutCubic, no bounce).

    Deviation from the literal `.98 → 1.00` scale: Qt geometry animation
    on laid-out dialogs causes relayout jitter; a 150 ms fade communicates
    the same appearance transition inside the same motion budget.
    """
    anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.85)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    dialog._pop_anim = anim  # keep alive for the dialog lifetime
    return anim
