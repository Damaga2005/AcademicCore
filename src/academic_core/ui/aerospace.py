# SPDX-License-Identifier: MIT
"""Aerospace workspace: F16 domain numbers, painted and listed honestly.

Context (central body) -> Inputs (altitude) -> Tool (compute) ->
Visualization (orbit view) -> Results (metrics with units) -> Runs (history
and deterministic replay). ``OrbitPanel`` computes circular-orbit state via
the certified F16 engine (no duplicated formulas); ``OrbitView`` paints the
rp/ra ellipse from those same numbers, never invented geometry.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from academic_core.domain.engineering.orbital import (
    EARTH,
    altitude_from_radius_m,
    circular_period_s,
    circular_velocity_m_s,
    escape_velocity_m_s,
    radius_from_altitude_m,
)
from academic_core.ui.state import UiState
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workspace import KeyValueList, Metric, Panel

PRESETS = (("LEO 420", "420", "420 km: low Earth orbit (ISS-class altitude)"),
           ("MEO 20 200", "20200", "20 200 km: navigation satellites (GPS-class altitude)"),
           ("GEO 35 786", "35786", "35 786 km: geostationary orbit"))


def _spaced(value: Decimal, places: int = 0) -> str:
    """Thousands separated with spaces: 35 786."""
    return f"{value:,.{places}f}".replace(",", " ")


class OrbitView(QWidget):
    """2D orbit from real rp/ra (m): Earth to scale, orbit ring, altitude marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setAccessibleName("Orbit view")
        self.setAccessibleDescription("Earth and the orbit drawn to scale from the computed radius")
        self.last_rp_m: Decimal | None = None
        self.last_ra_m: Decimal | None = None

    def set_orbit(self, rp_m: Decimal, ra_m: Decimal) -> None:
        self.last_rp_m, self.last_ra_m = rp_m, ra_m
        altitude = (rp_m - EARTH.radius_m) / Decimal(1000)
        self.setToolTip(f"Altitude {_spaced(altitude)} km, to scale")
        self.update()

    def paintEvent(self, _event) -> None:
        if self.last_rp_m is None or self.last_ra_m is None:
            from academic_core.ui.theme import current_tokens
            p = QPainter(self)
            p.setPen(QColor(current_tokens().secondary))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "Compute an orbit to see it here.")
            p.end()
            return
        rp, ra = float(self.last_rp_m), float(self.last_ra_m)
        if not (rp > 0 and ra >= rp):
            return
        from academic_core.ui.theme import current_tokens
        tk = current_tokens()
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        scale = (min(w, h) / 2 - 24) / ra
        a = (rp + ra) / 2 * scale
        c = (ra - rp) / 2 * scale
        b = max((a * a - c * c) ** 0.5, 1.0)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body_r = max(float(EARTH.radius_m) * scale, 3.0)
        p.setPen(QPen(QColor(tk.secondary), 1))
        p.setBrush(QColor(tk.info_bg))
        p.drawEllipse(QPointF(cx, cy), body_r, body_r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(tk.accent), 2))
        p.drawEllipse(QRectF(cx - a, cy - b, 2 * a, 2 * b))
        # Altitude marker: surface -> orbit along +x, labelled with the real number.
        x0, x1 = cx + body_r, cx + a + c
        if x1 - x0 > 6:
            p.setPen(QPen(QColor(tk.warning_ink), 2))
            p.drawLine(QPointF(x0, cy), QPointF(x1, cy))
        p.setPen(QPen(QColor(tk.warning_ink), 1))
        p.setBrush(QColor(tk.accent))
        p.drawEllipse(QPointF(x1, cy), 5, 5)
        p.setPen(QColor(tk.ink))
        altitude = (self.last_rp_m - EARTH.radius_m) / Decimal(1000)
        p.drawText(QRectF(8, 6, w - 16, 20), int(Qt.AlignmentFlag.AlignLeft),
                   f"h = {_spaced(altitude)} km   ·   scale: Earth R = {_spaced(EARTH.radius_m / 1000)} km")
        if body_r > 40:
            p.setPen(QColor(tk.secondary))
            p.drawText(QRectF(cx - body_r, cy - 10, 2 * body_r, 20),
                       int(Qt.AlignmentFlag.AlignCenter), EARTH.name)
        p.end()


class OrbitPanel(QWidget):
    """Altitude in, circular-orbit state out (Earth, two-body)."""

    def __init__(self, _core, parent=None):
        super().__init__(parent)
        self.last: dict = {}
        self._runs: list[dict] = []
        self.state = UiState.IDLE

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # -- left: context, inputs + tool, runs ----------------------------------
        left = QVBoxLayout()
        left.setSpacing(16)
        ctx = Panel("Central body")
        self.body_facts = KeyValueList()
        self.body_facts.set_rows([
            ("Body", EARTH.name),
            ("Radius", f"{_spaced(EARTH.radius_m / 1000, 3)} km"),
            ("μ", f"{EARTH.mu_m3_s2:.6e} m³/s²"),
            ("Model", "Two-body, circular"),
        ])
        ctx.setToolTip(str(EARTH.provenance))
        ctx.add(self.body_facts)
        left.addWidget(ctx)

        inputs = Panel("Orbit")
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("Altitude")
        label.setProperty("role", "key")
        self.altitude_km = QLineEdit("420")
        self.altitude_km.setToolTip("Altitude above Earth surface, km >= 0")
        self.altitude_km.setAccessibleName("Altitude in kilometres")
        self.altitude_km.returnPressed.connect(self.recompute)
        unit = QLabel("km")
        unit.setProperty("role", "metric-unit")
        row.addWidget(label)
        row.addWidget(self.altitude_km, 1)
        row.addWidget(unit)
        inputs.body.addLayout(row)
        presets = QGridLayout()
        presets.setSpacing(6)
        self.preset_buttons: list[QPushButton] = []
        for i, (text, value, tip) in enumerate(PRESETS):
            b = QPushButton(text)
            b.setProperty("class", "subtle")
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, v=value: self._preset(v))
            self.preset_buttons.append(b)
            presets.addWidget(b, i // 2, i % 2)
        presets.setColumnStretch(2, 1)
        inputs.body.addLayout(presets)
        tool = QHBoxLayout()
        self.btn_compute = QPushButton("Compute orbit")
        self.btn_compute.setProperty("class", "primary")
        self.btn_compute.clicked.connect(self.recompute)
        self.status = QLabel("IDLE")
        apply_status_style(self.status, UiState.IDLE)
        tool.addWidget(self.btn_compute)
        tool.addWidget(self.status)
        tool.addStretch(1)
        inputs.body.addLayout(tool)
        left.addWidget(inputs)

        runs = Panel("Runs")
        self.btn_replay = QPushButton("Replay")
        self.btn_replay.setProperty("class", "subtle")
        self.btn_replay.setToolTip("Recompute the selected run and compare it with the stored values")
        self.btn_replay.setEnabled(False)
        self.btn_replay.clicked.connect(self.replay)
        runs.actions.addWidget(self.btn_replay)
        self.history_list = QListWidget()
        self.history_list.setAccessibleName("Runs this session")
        self.history_list.setMaximumHeight(140)
        self.history_list.currentRowChanged.connect(self._history_selected)
        runs.add(self.history_list)
        self.runs_hint = QLabel("Runs from this session appear here.")
        self.runs_hint.setObjectName("CardStatus")
        runs.add(self.runs_hint)
        left.addWidget(runs)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(320)
        root.addWidget(left_w)

        # -- right: visualization + results --------------------------------------
        right = QVBoxLayout()
        right.setSpacing(16)
        view_panel = Panel("Orbit view")
        self.orbit_view = OrbitView()
        view_panel.add(self.orbit_view, 1)
        right.addWidget(view_panel, 1)

        results = Panel("Results")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.metrics = {
            "r": Metric("Orbital radius", "km"), "h": Metric("Altitude", "km"),
            "v": Metric("Circular velocity", "km/s"), "T": Metric("Period", "min"),
            "vesc": Metric("Escape velocity", "km/s"),
        }
        for i, m in enumerate(self.metrics.values()):
            grid.addWidget(m, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        results.body.addLayout(grid)
        self.result_label = QLabel("No computation yet")
        self.result_label.setObjectName("CardStatus")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        results.add(self.result_label)
        right.addWidget(results)
        root.addLayout(right, 1)

    # -- computation (certified engine only) ---------------------------------------
    @staticmethod
    def solve(h_km: Decimal) -> dict:
        """Circular-orbit state for an altitude in km (raises on invalid input)."""
        from academic_core.domain.engineering.orbital.orbits import km_to_m
        r = radius_from_altitude_m(km_to_m(h_km), EARTH.radius_m)
        return {"r_m": r, "h_m": altitude_from_radius_m(r, EARTH.radius_m),
                "v_m_s": circular_velocity_m_s(r, EARTH.mu_m3_s2),
                "T_s": circular_period_s(r, EARTH.mu_m3_s2),
                "vesc_m_s": escape_velocity_m_s(r, EARTH.mu_m3_s2)}

    def _preset(self, value: str) -> None:
        self.altitude_km.setText(value)
        self.recompute()

    def recompute(self) -> None:
        text = self.altitude_km.text().strip()
        try:
            state = self.solve(Decimal(text))
        except (InvalidOperation, ValueError, ArithmeticError):
            self.last = {}
            for m in self.metrics.values():
                m.clear()
            self.result_label.setText("error: enter the altitude as a number of km, zero or more")
            self._set_state(UiState.ERROR, "ERROR")
            return
        self.last = state
        self._show(state)
        self._remember(text, state)
        self._set_state(UiState.SUCCESS, "SUCCESS")

    def _show(self, s: dict) -> None:
        self.orbit_view.set_orbit(s["r_m"], s["r_m"])
        km = Decimal(1000)
        self.metrics["r"].set_value(_spaced(s["r_m"] / km, 1))
        self.metrics["h"].set_value(_spaced(s["h_m"] / km, 1))
        self.metrics["v"].set_value(f"{s['v_m_s'] / km:.3f}")
        self.metrics["T"].set_value(_spaced(s["T_s"] / 60, 1))
        self.metrics["vesc"].set_value(f"{s['vesc_m_s'] / km:.3f}")
        self.result_label.setText(
            f"v = {s['v_m_s'] / km:.3f} km/s · T = {s['T_s'] / 60:.1f} min · "
            f"v_esc = {s['vesc_m_s'] / km:.3f} km/s")

    # -- runs + replay ----------------------------------------------------------------
    def _remember(self, altitude_text: str, state: dict) -> None:
        if self._runs and self._runs[-1]["altitude"] == altitude_text:
            return
        self._runs.append({"altitude": altitude_text, "state": state})
        km = Decimal(1000)
        self.history_list.addItem(QListWidgetItem(
            f"{altitude_text} km → {state['v_m_s'] / km:.3f} km/s · {state['T_s'] / 60:.1f} min"))
        self.history_list.setCurrentRow(self.history_list.count() - 1)
        self.runs_hint.hide()

    def _history_selected(self, row: int) -> None:
        self.btn_replay.setEnabled(0 <= row < len(self._runs))

    def replay(self) -> None:
        """Recompute the selected run from its input and compare exactly."""
        row = self.history_list.currentRow()
        if not 0 <= row < len(self._runs):
            return
        run = self._runs[row]
        self.altitude_km.setText(run["altitude"])
        again = self.solve(Decimal(run["altitude"]))
        self.last = again
        self._show(again)
        same = again == run["state"]
        self._set_state(UiState.SUCCESS if same else UiState.WARNING,
                        "EQUIVALENT" if same else "DIFFERENT")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)
