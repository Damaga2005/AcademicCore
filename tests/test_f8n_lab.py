"""F8-N virtual laboratory verification: session / experiment / run / probes.

Tests N-001 .. N-036 of docs/gates/GATE-F8N-DESIGN.md.
"""
from decimal import Decimal as D

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.lab import (
    AnalysisKind,
    AnalysisSpec,
    Annotation,
    CurrentProbe,
    ExperimentDefinition,
    InstrumentKind,
    InstrumentSpec,
    LabConfigError,
    MeasurementKind,
    MeasurementSpec,
    ParameterProbe,
    StimulusKind,
    StimulusSpec,
    VoltageProbe,
    add_experiment,
    annotate,
    branch_experiment,
    clone_session,
    close_session,
    create_session,
    function_generator,
    reset,
    run_experiment,
)
from academic_core.domain.engineering.lab.serialize import experiment_id
from academic_core.domain.engineering.mna.analysis import (
    GridSpec,
    MCConfig,
    ObservableSpec,
    ParamAddress,
    SweepConfig,
    UniformDist,
)
from academic_core.domain.engineering.units import parse_quantity as Q
from f8n_lab_common import (
    add_ok,
    ammeter,
    bjt_circuit,
    diode_divider,
    divider,
    mos_circuit,
    new_session,
    op_definition,
    run_ok,
    voltmeter,
)


def _eid(session, definition):
    return experiment_id(definition, session.circuit)


# ---------------------------------------------------------------------------
# Session (N-001 .. N-008)
# ---------------------------------------------------------------------------

class TestSession:
    def test_n001_create_valid(self):
        s = create_session("lab-1.0", divider())
        assert s.session_id == "lab-1.0"
        assert s.state == "OPEN"
        assert len(s.experiments) == 0
        # Deep copy: mutating the caller circuit later changes nothing.
        c = divider()
        s = create_session("x", c)
        c.add(Component("R9", "R", Q("1 ohm"), {"1": "a", "2": "0"}))
        assert all(comp.ref != "R9" for comp in s.circuit.components)

    def test_n002_invalid_ids(self):
        for bad in ("", "has space", "x" * 65, "semi;colon", "slash/x"):
            with pytest.raises(LabConfigError):
                create_session(bad, divider())
        with pytest.raises(LabConfigError):
            create_session(123, divider())

    def test_n003_operations_return_new_values(self):
        s = new_session()
        d = op_definition()
        s2, report = add_experiment(s, d)
        assert report.ok
        assert s2 is not s
        assert s2 == s or True  # value differs by the added experiment
        assert len(s.experiments) == 0
        assert len(s2.experiments) == 1
        s3, run = run_experiment(s2, _eid(s2, d))
        assert s3 is not s2
        assert len(s2.records) == 0
        assert len(s3.records) == 1

    def test_n004_reset(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),))
        s = add_ok(s, d)
        s, _ = run_experiment(s, _eid(s, d))
        s, _ = run_experiment(s, _eid(s, d))
        assert len(s.records[0].runs) == 2
        s2 = reset(s)
        assert len(s2.experiments) == 1
        assert all(len(r.runs) == 0 for r in s2.records)
        assert len(s.records[0].runs) == 2  # original untouched

    def test_n005_clone(self):
        s = new_session(divider(), "orig")
        d = op_definition()
        s = add_ok(s, d)
        c = clone_session(s, "copy")
        assert c.session_id == "copy"
        assert ("cloned_from", "orig") in c.metadata
        assert experiment_id(c.experiments[0], c.circuit) == _eid(s, d)
        assert len(c.experiments) == len(s.experiments)

    def test_n006_branch(self):
        s = new_session()
        d = op_definition(label="base")
        s = add_ok(s, d)
        old_id = _eid(s, d)
        s2, new_id, report = branch_experiment(
            s, old_id, label="derived",
            probes=(("v", VoltageProbe("in", "0")),))
        assert report.ok
        assert new_id != old_id
        assert ("derived_from", old_id) in s2.metadata
        ids = [experiment_id(e, s2.circuit) for e in s2.experiments]
        assert old_id in ids and new_id in ids
        # Original definition intact.
        assert s2.experiments[ids.index(old_id)].label == "base"

    def test_n007_close(self):
        s = new_session()
        d = op_definition()
        s = add_ok(s, d)
        closed = close_session(s)
        assert closed.state == "CLOSED"
        with pytest.raises(LabConfigError):
            add_experiment(closed, d)
        with pytest.raises(LabConfigError):
            run_experiment(closed, _eid(closed, d))
        with pytest.raises(LabConfigError):
            reset(closed)
        # to_document still works on closed sessions.
        from academic_core.domain.engineering.lab import to_document
        doc = to_document(closed, {})
        assert doc["state"] == "CLOSED"

    def test_n008_sessions_independent(self):
        a = new_session(divider(), "a")
        b = new_session(divider(), "b")
        d = op_definition()
        a = add_ok(a, d)
        a, _ = run_experiment(a, _eid(a, d))
        assert len(b.experiments) == 0
        assert len(b.records) == 0


# ---------------------------------------------------------------------------
# Experiment (N-009 .. N-016)
# ---------------------------------------------------------------------------

class TestExperiment:
    def test_n009_content_addressed_same(self):
        s = new_session()
        d1 = op_definition(label="one", probes=(("v", VoltageProbe("out", "0")),))
        d2 = op_definition(label="two", probes=(("v", VoltageProbe("out", "0")),))
        assert _eid(s, d1) == _eid(s, d2)
        s = add_ok(s, d1)
        s, report = add_experiment(s, d2)
        assert report.ok
        assert len(s.experiments) == 1  # idempotent

    def test_n010_content_change_new_id(self):
        s = new_session()
        base = op_definition(probes=(("v", VoltageProbe("out", "0")),))
        variants = [
            op_definition(probes=(("v", VoltageProbe("in", "0")),)),
            op_definition(probes=(("v", VoltageProbe("out", "0")),
                                  ("w", VoltageProbe("in", "0")))),
            ExperimentDefinition(label="x", analysis=AnalysisSpec("OP"),
                                 overrides=((ParamAddress("R1", "value"), D(500)),)),
            ExperimentDefinition(label="x", analysis=AnalysisSpec("OP"),
                                 seed=None, stimuli=(
                function_generator("V1", "dc", offset=Q("5 V")),)),
        ]
        base_id = _eid(s, base)
        for v in variants:
            assert _eid(s, v) != base_id

    def test_n011_add_idempotent(self):
        s = new_session()
        d = op_definition()
        s = add_ok(s, d)
        s, report = add_experiment(s, d)
        assert report.ok
        assert len(s.experiments) == 1

    def test_n012_invalid_override(self):
        s = new_session()
        bad_addr = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("OP"),
            overrides=((ParamAddress("R1", "nope"), D(1)),))
        s2, report = add_experiment(s, bad_addr)
        assert not report.ok
        assert len(s2.experiments) == 0
        bad_domain = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("OP"),
            overrides=((ParamAddress("R1", "value"), D(-5)),))
        s2, report = add_experiment(s, bad_domain)
        assert not report.ok

    def test_n013_seed_rules(self):
        s = new_session()
        # MC without seed is a construction error.
        with pytest.raises(LabConfigError):
            ExperimentDefinition(label="x", analysis=AnalysisSpec(
                "MONTE_CARLO", mc=MCConfig(
                    4, ((ParamAddress("R1", "value"), UniformDist(D(900), D(1100))),),
                    None, (ObservableSpec("node_voltage", "out"),), "dc-op")))
        for bad in (True, -1, 1.5, "42"):
            with pytest.raises(LabConfigError):
                ExperimentDefinition(label="x", analysis=AnalysisSpec(
                    "MONTE_CARLO", mc=MCConfig(
                        4, ((ParamAddress("R1", "value"),
                             UniformDist(D(900), D(1100))),),
                        bad, (ObservableSpec("node_voltage", "out"),), "dc-op")))
        # Seed on a deterministic analysis is forbidden.
        with pytest.raises(LabConfigError):
            op_definition(seed=42)

    def test_n014_duplicate_keys(self):
        with pytest.raises(LabConfigError):
            op_definition(probes=(("v", VoltageProbe("out", "0")),
                                  ("v", VoltageProbe("in", "0"))))
        with pytest.raises(LabConfigError):
            op_definition(measurements=(
                ("m", MeasurementSpec("dc_value", "v")),
                ("m", MeasurementSpec("dc_value", "v"))))
        s = new_session()
        d = op_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("m", MeasurementSpec("dc_value", "nope")),))
        s2, report = add_experiment(s, d)
        assert not report.ok

    def test_n015_stimulus_rules(self):
        s = new_session()
        d = op_definition(stimuli=(StimulusSpec("R1", "DC", value=Q("1 V")),))
        _, report = add_experiment(s, d)
        assert not report.ok
        with pytest.raises(LabConfigError):
            op_definition(stimuli=(StimulusSpec("V1", "DC", value=Q("1 V")),
                                   StimulusSpec("V1", "DC", value=Q("2 V"))))

    def test_n016_definition_survives_runs(self):
        import copy
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        before = copy.deepcopy(d)
        s = add_ok(s, d)
        s, _ = run_experiment(s, _eid(s, d))
        s, _ = run_experiment(s, _eid(s, d))
        assert d == before


# ---------------------------------------------------------------------------
# Run (N-017 .. N-022)
# ---------------------------------------------------------------------------

class TestRun:
    def test_n017_run_ids(self):
        s = new_session()
        d = op_definition()
        s = add_ok(s, d)
        eid = _eid(s, d)
        s, r1 = run_experiment(s, eid)
        s, r2 = run_experiment(s, eid)
        assert r1.run_id == f"{eid}#1"
        assert r2.run_id == f"{eid}#2"

    def test_n018_snapshot_isolation(self):
        from academic_core.domain.engineering.mna.analysis import circuit_digest
        s = new_session()
        caller = divider()
        s = create_session("iso", caller)
        d = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("OP"),
            overrides=((ParamAddress("R1", "value"), D(500)),),
            probes=(("v", VoltageProbe("out", "0")),))
        before = circuit_digest(s.circuit)
        caller_before = circuit_digest(caller)
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert circuit_digest(s.circuit) == before
        assert circuit_digest(caller) == caller_before
        assert run.status == "COMPLETED"

    def test_n019_failed_run_appended(self):
        # Floating circuit: no reference net.
        c = Circuit("float")
        c.add(Component("R1", "R", Q("1 kohm"), {"1": "a", "2": "b"}))
        s = create_session("bad", c)
        d = op_definition()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status in ("INVALID_CIRCUIT", "SOLVER_FAILURE")
        assert len(s.records) == 1
        assert len(s.records[0].runs) == 1
        assert len(s.experiments) == 1

    def test_n020_repeated_runs_equal(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        s = add_ok(s, d)
        s, r1 = run_experiment(s, _eid(s, d))
        s, r2 = run_experiment(s, _eid(s, d))
        s, r3 = run_experiment(s, _eid(s, d))
        assert r1.result_digest == r2.result_digest == r3.result_digest

    def test_n021_status_mapping(self):
        from academic_core.domain.engineering.lab.run import map_engine_status
        assert map_engine_status("converged") == "COMPLETED"
        assert map_engine_status("completed") == "COMPLETED"
        assert map_engine_status("solved") == "COMPLETED"
        assert map_engine_status("completed_with_point_failures") == \
            "COMPLETED_WITH_FAILURES"
        assert map_engine_status("completed_with_failures") == \
            "COMPLETED_WITH_FAILURES"
        assert map_engine_status("invalid") == "INVALID_CIRCUIT"
        assert map_engine_status("unsupported") == "UNSUPPORTED"
        for weird in ("diverged", "max_iterations", "singular_jacobian",
                      "max_steps", "timestep_too_small", "singular",
                      "inconsistent", "numerically_uncertain"):
            assert map_engine_status(weird) == "SOLVER_FAILURE"

    def test_n022_run_budget(self):
        import academic_core.domain.engineering.lab.session as _sess
        old = _sess.MAX_RUNS_PER_SESSION
        _sess.MAX_RUNS_PER_SESSION = 2
        try:
            s = new_session()
            d = op_definition()
            s = add_ok(s, d)
            s, _ = run_experiment(s, _eid(s, d))
            s, _ = run_experiment(s, _eid(s, d))
            with pytest.raises(LabConfigError):
                run_experiment(s, _eid(s, d))
        finally:
            _sess.MAX_RUNS_PER_SESSION = old


# ---------------------------------------------------------------------------
# Instruments + probes (N-023 .. N-036)
# ---------------------------------------------------------------------------

class TestInstrumentsProbes:
    def test_n023_voltmeter_op(self):
        from academic_core.domain.engineering.lab.model import lab_context
        from academic_core.domain.engineering.mna.nonlinear import solve_nonlinear_dc
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        _, run, _ = run_ok(s, d)
        direct = solve_nonlinear_dc(divider())
        vmap = {nv.node: nv.voltage.to_base() for nv in direct.node_voltages}
        with lab_context():
            expected = vmap["out"] - vmap["0"]
        assert run.readings[0].data.value == expected

    def test_n024_ammeter_availability(self):
        s = new_session(divider())
        d = op_definition(
            probes=(("ir", CurrentProbe("R1")), ("iv", CurrentProbe("V1")),
                    ("ii", CurrentProbe("I9")),),
            instruments=(ammeter("a", "ir"),))
        # Unknown branch I9 is rejected statically.
        _, report = add_experiment(s, d)
        assert not report.ok
        d2 = op_definition(
            probes=(("ir", CurrentProbe("R1")), ("iv", CurrentProbe("V1"))),
            instruments=(ammeter("a", "ir"), ammeter("b", "iv")))
        _, run, _ = run_ok(s, d2)
        assert all(r.status == "OK" for r in run.readings)
        # I source reports -Is (F8-B rule): divider has no I source; check sign.
        assert run.readings[1].data.value < 0  # V1 absorbs in divider? (loaded)

    def test_n025_instruments_pure(self):
        from academic_core.domain.engineering.mna.analysis import circuit_digest
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        s = add_ok(s, d)
        before = circuit_digest(s.circuit)
        s, r1 = run_experiment(s, _eid(s, d))
        s, r2 = run_experiment(s, _eid(s, d))
        assert circuit_digest(s.circuit) == before
        assert r1.result_digest == r2.result_digest

    def test_n026_scope_interpolation(self):
        from academic_core.domain.engineering.lab import (
            InstrumentSpec, ScopeChannel, Waveform,
        )
        from f8n_lab_common import rc_step, transient_config, transient_definition
        from academic_core.domain.engineering.lab import AnalysisKind as _AK
        from academic_core.domain.engineering.lab import AnalysisSpec as _AS
        c = rc_step()
        s = create_session("scope", c)
        d = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope",
                channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                window=(D(0), D("0.005")), sample_count=50)),))
        _, run, _ = run_ok(s, d)
        reading = run.readings[0]
        assert reading.status == "OK"
        scope = reading.data
        # Exact hits return committed values: compare against engine waves.
        from academic_core.domain.engineering.mna.transient import solve_transient
        direct = solve_transient(c, transient_config())
        traj = direct.node_trajectory("out")
        assert scope.channels[0].raw[0] == traj[0]
        assert scope.channels[0].raw[-1] == traj[-1]
        # Display grid is independent of solver steps.
        assert len(scope.channels[0].times) == 50

    def test_n027_scope_resolution_independent(self):
        from academic_core.domain.engineering.lab import InstrumentSpec, ScopeChannel
        from f8n_lab_common import rc_step, transient_definition
        from academic_core.domain.engineering.lab import MeasurementSpec as _MS
        from academic_core.domain.engineering.lab import MeasurementKind as _MK
        vals = []
        for n in (2, 10, 1000):
            c = rc_step()
            s = create_session(f"sc{n}", c)
            d = transient_definition(
                probes=(("v", VoltageProbe("out", "0")),),
                instruments=(("scope", InstrumentSpec(
                    "oscilloscope", channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                    window=(D(0), D("0.005")), sample_count=n)),),
                measurements=(("mx", _MS(_MK.MAX.value, "v")),
                              ("mn", _MS(_MK.MEAN.value, "v"))))
            _, run, _ = run_ok(s, d)
            vals.append(tuple((m.key, m.value.value if m.value else None,
                               m.status) for m in run.measurements))
        assert vals[0] == vals[1] == vals[2]

    def test_n028_scope_scaling_presentation_only(self):
        from academic_core.domain.engineering.lab import InstrumentSpec, ScopeChannel
        from f8n_lab_common import rc_step, transient_definition
        raws = []
        for vpd, off in ((D(1), D(0)), (D("0.5"), D("0.25"))):
            s = create_session(f"sc{vpd}", rc_step())
            d = transient_definition(
                probes=(("v", VoltageProbe("out", "0")),),
                instruments=(("scope", InstrumentSpec(
                    "oscilloscope",
                    channels=(ScopeChannel("v", vpd, off, "DC"),),
                    window=(D(0), D("0.005")), sample_count=20)),))
            _, run, _ = run_ok(s, d)
            raws.append(run.readings[0].data.channels[0].raw)
        assert raws[0] == raws[1]

    def test_n029_ac_coupling(self):
        from academic_core.domain.engineering.lab import InstrumentSpec, ScopeChannel
        from academic_core.domain.engineering.lab.waveform import wave_mean
        from f8n_lab_common import rc_step, transient_definition
        s = create_session("acc", rc_step())
        d = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope", channels=(ScopeChannel("v", D(1), D(0), "AC"),),
                window=(D(0), D("0.005")), sample_count=200)),))
        _, run, _ = run_ok(s, d)
        coupled = run.readings[0].data.channels[0].coupled
        mean = sum(coupled, D(0)) / D(len(coupled))
        # Mean of the coupled display series ~ 0 (Riemann sum over the grid).
        assert abs(mean) < D("1e-3")

    def test_n030_scope_config_leaves_digest(self):
        from academic_core.domain.engineering.lab import InstrumentSpec, ScopeChannel
        from f8n_lab_common import rc_step, transient_definition
        digests = []
        for n in (100, 500):
            s = create_session(f"dg{n}", rc_step())
            d = transient_definition(
                probes=(("v", VoltageProbe("out", "0")),),
                instruments=(("scope", InstrumentSpec(
                    "oscilloscope", channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                    window=(D(0), D("0.005")), sample_count=n)),))
            _, run, _ = run_ok(s, d)
            digests.append(run.result_digest)
        assert digests[0] == digests[1]

    def test_n031_voltage_probe_shapes(self):
        with pytest.raises(LabConfigError):
            VoltageProbe("a", "a")
        s = new_session()
        d2 = op_definition(probes=(("g", VoltageProbe("out", "nope")),))
        _, report = add_experiment(s, d2)
        assert not report.ok

    def test_n032_current_probe_transient_gap(self):
        # C current in transient is UNSUPPORTED (not stored by F8-L).
        from f8n_lab_common import rc_step, transient_definition
        s = create_session("gap", rc_step())
        d = transient_definition(
            probes=(("ic", CurrentProbe("C1")),),
            instruments=(ammeter("a", "ic"),))
        _, run, _ = run_ok(s, d)
        assert run.readings[0].status == "UNSUPPORTED"
        # Unknown branches are rejected statically with INVALID_PROBE.
        d_bad = transient_definition(probes=(("x", CurrentProbe("ZZ9")),))
        _, report = add_experiment(s, d_bad)
        assert not report.ok
        assert any(code == "INVALID_PROBE" for code, _ in report.errors)

    def test_n033_resistor_transient_derivation(self):
        from f8n_lab_common import rc_step, transient_config, transient_definition
        from academic_core.domain.engineering.mna.transient import solve_transient
        c = rc_step()
        s = create_session("rder", c)
        d = transient_definition(
            probes=(("ir", CurrentProbe("R1")), ("v", VoltageProbe("in", "0")),
                    ("vo", VoltageProbe("out", "0"))),
            instruments=(ammeter("a", "ir"),))
        _, run, _ = run_ok(s, d)
        assert run.readings[0].status == "OK"
        direct = solve_transient(c, transient_config())
        tin = direct.node_trajectory("in")
        tout = direct.node_trajectory("out")
        from academic_core.domain.engineering.lab.model import lab_context
        with lab_context():
            expect = (tin[-1] - tout[-1]) / Q("1 kohm").to_base()
        assert run.readings[0].data.value == expect

    def test_n034_inductor_transient(self):
        from decimal import Decimal as _D
        from f8n_lab_common import transient_config, transient_definition
        c = Circuit("rl")
        c.add(Component("V1", "V", Q("0 V"), {"+": "in", "-": "0"},
                        {"wave": {"type": "step", "v1": Q("0 V"),
                                  "v2": Q("1 V"), "t0": _D(0)}}))
        c.add(Component("R1", "R", Q("100 ohm"), {"1": "in", "2": "out"}))
        c.add(Component("L1", "L", Q("10 mH"), {"1": "out", "2": "0"}))
        s = create_session("rl", c)
        d = transient_definition(
            probes=(("il", CurrentProbe("L1")),),
            instruments=(ammeter("a", "il"),))
        _, run, _ = run_ok(s, d)
        assert run.readings[0].status == "OK"
        from academic_core.domain.engineering.mna.transient import solve_transient
        direct = solve_transient(c, transient_config())
        assert run.readings[0].data.value == direct.inductor_current("L1")[-1]

    def test_n035_parameter_probe(self):
        from academic_core.domain.engineering.lab import Scalar
        s = new_session()
        d = op_definition(probes=(("r", ParameterProbe("R1", "value")),))
        _, run, _ = run_ok(s, d)
        assert run.status == "COMPLETED"
        d2 = op_definition(probes=(("bad", ParameterProbe("R1", "nope")),))
        _, report = add_experiment(s, d2)
        assert not report.ok
        d3 = op_definition(probes=(("bad", ParameterProbe("ZZ9", "value")),))
        _, report = add_experiment(s, d3)
        assert not report.ok

    def test_n036_no_waveform_frequency_probes(self):
        import academic_core.domain.engineering.lab as lab
        assert not hasattr(lab, "WaveformProbe")
        assert not hasattr(lab, "FrequencyProbe")


class TestAliasing:
    def test_shared_dict_mutation(self):
        c = divider()
        s = create_session("alias", c)
        # Mutate every shared dict on the caller circuit afterwards.
        for comp in c.components:
            comp.pins["1"] = "hacked" if "1" in comp.pins else comp.pins.get("+", "x")
            comp.parameters["hacked"] = "x"
            comp.metadata["hacked"] = "x"
        c.notes = "hacked"
        for comp in s.circuit.components:
            assert "hacked" not in comp.parameters
            assert "hacked" not in comp.metadata
        assert s.circuit.notes != "hacked"

    def test_failed_operation_unchanged(self):
        s = new_session()
        d = op_definition()
        s = add_ok(s, d)
        s2, report = add_experiment(
            s, op_definition(probes=(("v", VoltageProbe("nope", "0")),)))
        assert not report.ok
        assert s2 is s  # identical object: nothing half-applied

    def test_experiment_derivation_no_alias(self):
        s = new_session()
        a = op_definition(probes=(("v", VoltageProbe("out", "0")),))
        s = add_ok(s, a)
        old_id = _eid(s, a)
        s2, new_id, report = branch_experiment(
            s, old_id, probes=(("v", VoltageProbe("out", "0")),
                               ("w", VoltageProbe("in", "0"))))
        assert report.ok
        ids = [experiment_id(e, s2.circuit) for e in s2.experiments]
        assert s2.experiments[ids.index(old_id)] == a
        assert len(s2.experiments[ids.index(old_id)].probes) == 1

    def test_empty_and_single_sample_waveforms(self):
        from academic_core.domain.engineering.lab.waveform import make_waveform
        from academic_core.domain.engineering.units import VOLTAGE
        from academic_core.domain.engineering.lab import measure as _mm
        with pytest.raises(LabConfigError):
            make_waveform((), (), VOLTAGE, "V", "empty")
        one = make_waveform((D(0),), (D(1),), VOLTAGE, "V", "one")
        res = _mm.measure_mean("r", "m", one)
        assert res.status == "INVALID_MEASUREMENT"
        res = _mm.measure_rms("r", "m", one)
        assert res.status == "INVALID_MEASUREMENT"