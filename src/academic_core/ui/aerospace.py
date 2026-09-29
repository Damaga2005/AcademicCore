# SPDX-License-Identifier: MIT
"""Aerospace orbit view: F16 domain numbers, painted honestly.

OrbitPanel computes circular-orbit state from altitude via the certified
F16 engine (no duplicated formulas). OrbitView paints the rp/ra ellipse
from those same numbers — never invented geometry.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from academic_core.domain.engineering.orbital import (
    EARTH,
    altitude_from_radius_m,
    circular_period_s,
    circular_velocity_m_s,
    escape_velocity_m_s,
    radius_from_altitude_m,
)


class OrbitView(QWidget):
    """2D orbit ellipse from real rp/ra (m)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.last_rp_m: Decimal | None = None
        self.last_ra_m: Decimal | None = None

    def set_orbit(self, rp_m: Decimal, ra_m: Decimal) -> None:
        self.last_rp_m, self.last_ra_m = rp_m, ra_m
        self.update()

    def paintEvent(self, _event) -> None:
        if self.last_rp_m is None or self.last_ra_m is None:
            return
        rp, ra = float(self.last_rp_m), float(self.last_ra_m)
        if not (rp > 0 and ra >= rp):
            return
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        scale = (min(w, h) / 2 - 12) / ra
        a = (rp + ra) / 2 * scale
        c = (ra - rp) / 2 * scale
        b = max((a * a - c * c) ** 0.5, 1.0)
        from academic_core.ui.theme import current_tokens
        tk = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(tk.accent), 2))
        p.drawEllipse(int(cx - a), int(cy - b), int(2 * a), int(2 * b))
        p.setPen(QPen(QColor(tk.secondary), 1))
        body_r = max(float(EARTH.radius_m) * scale, 3.0)
        p.drawEllipse(int(cx - body_r), int(cy - body_r),
                      int(2 * body_r), int(2 * body_r))
        # Focus marker at pericenter side (c from center toward +x).
        p.setPen(QPen(QColor(tk.warning_ink), 3))
        p.drawPoint(int(cx + c), int(cy))
        p.end()


class OrbitPanel(QWidget):
    """Altitude in, circular-orbit state out (Earth, two-body)."""

    def __init__(self, _core, parent=None):
        super().__init__(parent)
        self.last: dict = {}
        layout = QVBoxLayout(self)
        box = QGroupBox("Aerospace — circular Earth orbit (two-body)")
        form = QFormLayout(box)
        self.altitude_km = QLineEdit("420")
        self.altitude_km.setToolTip("Altitude above Earth surface, km >= 0")
        form.addRow("Altitude (km):", self.altitude_km)
        self.btn_compute = QPushButton("Compute orbit")
        self.btn_compute.setProperty("class", "primary")
        self.btn_compute.clicked.connect(self.recompute)
        form.addRow("", self.btn_compute)
        self.result_label = QLabel("No computation yet")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("State:", self.result_label)
        self.orbit_view = OrbitView()
        form.addRow(self.orbit_view)
        layout.addWidget(box)

    def recompute(self) -> None:
        try:
            h_km = Decimal(self.altitude_km.text().strip())
            from academic_core.domain.engineering.orbital.orbits import km_to_m
            r = radius_from_altitude_m(km_to_m(h_km), EARTH.radius_m)
            v = circular_velocity_m_s(r, EARTH.mu_m3_s2)
            t = circular_period_s(r, EARTH.mu_m3_s2)
            vesc = escape_velocity_m_s(r, EARTH.mu_m3_s2)
            h = altitude_from_radius_m(r, EARTH.radius_m)
        except (InvalidOperation, ValueError, ArithmeticError) as exc:
            self.last = {}
            self.result_label.setText(f"error: {type(exc).__name__}")
            return
        self.last = {"r_m": r, "h_m": h, "v_m_s": v, "T_s": t, "vesc_m_s": vesc}
        self.orbit_view.set_orbit(r, r)
        self.result_label.setText(
            f"v = {v / 1000:.3f} km/s · T = {t / 60:.1f} min · "
            f"v_esc = {vesc / 1000:.3f} km/s")
