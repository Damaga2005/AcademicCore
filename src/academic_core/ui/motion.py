# SPDX-License-Identifier: MIT
"""Functional motion (UI only, no engine involved).

Every animation here says something: a dialog appearing, the context changing (page), a state
changing (status pill). All of them are one-shot, 100-180 ms, ease-out with no overshoot, and all
of them collapse to nothing when the user asked for reduced motion. Nothing loops.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect

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
    anim.setDuration(duration(duration_ms))
    anim.setStartValue(0.85)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    dialog._pop_anim = anim  # keep alive for the dialog lifetime
    return anim


def _fade(widget, start: float, ms: int) -> QPropertyAnimation | None:
    """Opacity ``start`` -> 1 on a child widget; the effect is removed when done (no idle cost)."""
    ms = duration(ms)
    if ms == 0 or widget.graphicsEffect() is not None:
        return None
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", effect)
    anim.setDuration(ms)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _done() -> None:
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
    anim.finished.connect(_done)
    anim.start()
    widget._fade_anim = anim
    return anim


def fade_in(widget, ms: int = SLOW) -> QPropertyAnimation | None:
    """The context changed (a new page): the incoming content eases in instead of snapping."""
    return _fade(widget, 0.0, ms)


def flash(widget, ms: int = BASE) -> QPropertyAnimation | None:
    """A state changed (status pill): a brief settle so the change is noticed, not a loop."""
    return _fade(widget, 0.35, ms)
