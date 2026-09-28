# SPDX-License-Identifier: MIT
"""Aerospace view contracts: every number from the F16 domain engine."""

from __future__ import annotations

import os
from decimal import Decimal


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_orbit_panel_matches_domain(qtbot, tmp_path):
    from academic_core.domain.engineering.orbital import EARTH, circular_velocity_m_s
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel.altitude_km.setText("420")
    panel.recompute()
    expected = circular_velocity_m_s(EARTH.radius_m + Decimal("420000"), EARTH.mu_m3_s2)
    assert abs(panel.last["v_m_s"] - expected) < Decimal("1E-9")
    assert "7.6" in panel.result_label.text()  # km/s, real value


def test_orbit_panel_rejects_bad_input(qtbot, tmp_path):
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel.altitude_km.setText("-5")
    panel.recompute()
    assert "error" in panel.result_label.text().lower()
    assert panel.last == {}


def test_orbit_view_uses_real_apsides(qtbot, tmp_path):
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(_core(tmp_path))
    qtbot.addWidget(panel)
    panel.altitude_km.setText("420")
    panel.recompute()
    rp, ra = panel.orbit_view.last_rp_m, panel.orbit_view.last_ra_m
    assert rp is not None and ra is not None and rp <= ra
    assert abs(rp - panel.last["r_m"]) < Decimal("1")
