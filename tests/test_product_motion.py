# SPDX-License-Identifier: MIT
"""Dialog motion contracts: functional microinteraction only.

Scale .98 → 1.00, 120–180 ms, no bounce/elastic/confetti.
Communicates appearance, nothing else.
"""

from __future__ import annotations


def test_pop_uses_bounded_easing(qtbot):
    from PySide6.QtCore import QEasingCurve
    from academic_core.ui.motion import pop_in
    from PySide6.QtWidgets import QDialog
    dlg = QDialog()
    qtbot.addWidget(dlg)
    anim = pop_in(dlg)
    assert 120 <= anim.duration() <= 180
    assert anim.easingCurve().type() in (
        QEasingCurve.Type.OutCubic, QEasingCurve.Type.OutQuad,
        QEasingCurve.Type.Linear)
    assert anim.easingCurve().type() not in (
        QEasingCurve.Type.OutBounce, QEasingCurve.Type.OutElastic,
        QEasingCurve.Type.InBounce, QEasingCurve.Type.InElastic)


def test_pop_fades_to_full_opacity(qtbot):
    from academic_core.ui.motion import pop_in
    from PySide6.QtWidgets import QDialog
    dlg = QDialog()
    qtbot.addWidget(dlg)
    anim = pop_in(dlg)
    assert anim.startValue() < 1.0 <= anim.endValue()
