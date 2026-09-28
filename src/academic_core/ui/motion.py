# SPDX-License-Identifier: MIT
"""Dialog motion: one bounded pop-in (UI only, no engine involved)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation


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
