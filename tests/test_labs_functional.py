# SPDX-License-Identifier: MIT
"""Functional labs (blocks A-C): project circuits, conservation seal, Bode, Thevenin, all components,
ngspice oracle and elliptical orbits. Everything comes from the engines; nothing is re-derived here."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    return app


def _add(core, circuit, ctype, nets, value=None, **over):
    eng = core.engineering
    spec = eng.component_spec(ctype)
    raw = {p.key: p.default for p in spec.params}
    raw.update(over)
    eng.add_component("P", circuit, ctype, eng.next_ref(eng.repo.load_circuit("P", circuit), ctype),
                      spec.value_default if value is None else value,
                      dict(zip([pin for pin, _ in spec.pins], nets)), eng.make_parameters(ctype, raw))


def _op(core, name, node, verify=False):
    sim = core.simulation
    circuit = core.engineering.repo.load_circuit("P", name)
    plan = sim.plan_project(circuit, "OP", node, "V1")
    plan.pop("circuit")
    return sim.run_analysis("t-" + name, circuit, verify=verify, **plan)


# -- block A: conservation card -----------------------------------------------------------------
def test_op_carries_the_engines_conservation_checks(core):
    d = core.simulation.demo_divider()
    plan = core.simulation.plan_project(d, "OP", "n2", "V1")
    plan.pop("circuit")
    cons = core.simulation.run_analysis("a1", d, **plan).run.conservation
    assert cons is not None and cons.passed is True and cons.kcl and cons.power_balance


def test_transient_has_no_verdict_and_says_so(core):
    d = core.simulation.demo_rc_step()
    plan = core.simulation.plan_project(d, "TRANSIENT", "out", "V1", "0.005 s")
    plan.pop("circuit")
    assert core.simulation.run_analysis("a2", d, **plan).run.conservation is None


def test_ac_sweep_on_a_project_circuit_uses_a_stimulus_not_a_copy(core):
    d = core.simulation.demo_rc_ac()
    before = d.to_netlist()
    plan = core.simulation.plan_project(d, "AC_SWEEP", "out", "V1")
    assert plan["circuit"] is d and plan["stimuli"] and d.to_netlist() == before


# -- block B: Thevenin / Norton -------------------------------------------------------------------
def test_divider_thevenin_norton_is_exact(core):
    r = core.engineering.one_port(core.simulation.demo_divider(), "n2", "0")
    assert r.ok and r.equivalent and (r.v_th, r.r_th, r.loads_passed, r.loads_total) == ("2.5 V", "500 Ω", 6, 6)


def test_thevenin_refuses_outside_its_domain_with_a_reason(core):
    r = core.engineering.one_port(core.simulation.demo_rc_ac(), "out", "0")
    assert not r.ok and r.status == "unsupported" and "C1" in r.diagnostics[0]


# -- block C: every component, persisted with its model --------------------------------------------
def test_all_fifteen_component_types_are_offered(core):
    assert [t for t, _ in core.engineering.component_types()] == list("RCLVIDQMJEGHFOT")


def test_model_parameters_survive_storage(core):
    core.engineering.create_project("P")
    for t, nets, v in (("V", ["a", "0"], "5 V"), ("R", ["a", "k"], "1 kohm")):
        _add(core, "dio", t, nets, v)
    _add(core, "dio", "D", ["k", "0"])
    diode = next(c for c in core.engineering.repo.load_circuit("P", "dio").components if c.type == "D")
    assert set(diode.parameters) == {"Is", "n", "Vt"}


def test_storage_keeps_the_plain_netlist_format(core):
    from academic_core.domain.engineering.circuit import Circuit
    plain = core.simulation.demo_divider()
    assert plain.to_storage() == plain.to_netlist()  # no model data: byte-for-byte the old form
    assert Circuit.from_storage(plain.to_netlist(), "divider").to_netlist() == plain.to_netlist()


def test_student_built_semiconductor_circuits_solve_and_conserve(core):
    core.engineering.create_project("P")
    for t, nets, v in (("V", ["vcc", "0"], "12 V"), ("V", ["vin", "0"], "0.7 V"),
                       ("R", ["vcc", "c"], "2 kohm"), ("R", ["vin", "b"], "10 kohm")):
        _add(core, "ce", t, nets, v)
    _add(core, "ce", "Q", ["c", "b", "0"])
    for t, nets, v in (("V", ["vdd", "0"], "5 V"), ("V", ["g", "0"], "3 V"), ("R", ["vdd", "d"], "2 kohm")):
        _add(core, "mos", t, nets, v)
    _add(core, "mos", "M", ["d", "g", "0", "0"])
    for name, node in (("ce", "c"), ("mos", "d")):
        run = _op(core, name, node).run
        assert run.status == "COMPLETED" and run.conservation.passed is True


def test_missing_control_parameter_is_refused(core):
    with pytest.raises(ValueError):
        core.engineering.make_parameters("E", {"cp": "", "cn": "0"})


# -- block C: ngspice as an independent oracle -------------------------------------------------------
def _ngspice_available():
    try:
        from academic_core.infrastructure.ngspice import NgSpiceBackend
        return NgSpiceBackend().detect().available
    except Exception:
        return False


@pytest.mark.skipif(not _ngspice_available(), reason="ngspice not available in this environment")
def test_ngspice_agrees_with_the_exact_engine_on_a_diode(core):
    core.engineering.create_project("P")
    for t, nets, v in (("V", ["a", "0"], "5 V"), ("R", ["a", "k"], "1 kohm")):
        _add(core, "dio", t, nets, v)
    _add(core, "dio", "D", ["k", "0"])
    oracle = _op(core, "dio", "k", verify=True).run.oracle
    assert oracle.status == "match" and oracle.nodes >= 2


def test_oracle_refuses_what_spice_cannot_express_faithfully(core):
    from academic_core.application.oracle import to_spice
    core.engineering.create_project("P")
    for t, nets, v in (("V", ["vdd", "0"], "5 V"), ("R", ["vdd", "d"], "2 kohm")):
        _add(core, "mos", t, nets, v)
    _add(core, "mos", "M", ["d", "vdd", "0", "0"])
    netlist, reason = to_spice(core.engineering.repo.load_circuit("P", "mos"))
    assert netlist is None and "M" in reason


# -- block C: elliptical orbits -----------------------------------------------------------------------
def test_elliptical_orbit_conserves_angular_momentum_and_is_gto_shaped(qtbot):
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(None)
    qtbot.addWidget(panel)
    panel.altitude_km.setText("500")
    panel.apogee_km.setText("35786")
    panel.recompute()
    s = panel.last
    assert s["elliptic"] and Decimal("0.7") < s["e"] < Decimal("0.75")
    assert abs(s["v_m_s"] * s["r_m"] - s["va_m_s"] * s["ra_m"]) < Decimal("1E-9") * s["v_m_s"] * s["r_m"]
    assert 630 < s["T_s"] / 60 < 640  # about 10.6 h, the GTO period
    assert panel.orbit_view.last_ra_m == s["ra_m"]
    panel.apogee_km.setText("100")  # below the perigee: refused, never clamped
    panel.recompute()
    assert panel.last == {} and "apogeo" in panel.result_label.text()


def test_circular_orbit_is_unchanged_when_apogee_is_blank(qtbot):
    from academic_core.ui.aerospace import OrbitPanel
    panel = OrbitPanel(None)
    qtbot.addWidget(panel)
    panel.altitude_km.setText("420")
    panel.recompute()
    assert not panel.last.get("elliptic") and panel.metrics["r"].label.text() == "Radio orbital"
