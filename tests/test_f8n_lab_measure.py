"""F8-N virtual laboratory verification: measurements / transient / AC.

Tests N-037 .. N-058 of docs/gates/GATE-F8N-DESIGN.md.
"""
from decimal import Decimal as D

import pytest

from academic_core.domain.engineering.lab import (
    AnalysisKind,
    AnalysisSpec,
    CurrentProbe,
    ExperimentDefinition,
    InstrumentKind,
    InstrumentSpec,
    LabConfigError,
    MeasurementKind,
    MeasurementSpec,
    ScopeChannel,
    TriggerSpec,
    VoltageProbe,
    add_experiment,
    function_generator,
)
from academic_core.domain.engineering.lab import model as _model
from academic_core.domain.engineering.lab.measure import (
    measure_max_min_pp,
    measure_mean,
    measure_rms,
)
from academic_core.domain.engineering.lab.model import lab_context
from academic_core.domain.engineering.lab.serialize import experiment_id
from academic_core.domain.engineering.lab.waveform import make_waveform
from academic_core.domain.engineering.units import VOLTAGE, parse_quantity as Q
from f8n_lab_common import (
    add_ok,
    ammeter,
    divider,
    new_session,
    op_definition,
    rc_ac,
    rc_step,
    run_ok,
    transient_config,
    transient_definition,
    voltmeter,
)


def _eid(session, definition):
    return experiment_id(definition, session.circuit)


def _ramp():
    # x = t on [0, 1]: 11 samples.
    ts = tuple(D(i) / D(10) for i in range(11))
    return make_waveform(ts, ts, VOLTAGE, "V", "ramp")


class TestWaveformMeasurements:
    def test_n037_max_min_pp(self):
        wave = make_waveform((D(0), D(1), D(2)), (D(0), D(3), D(1)),
                             VOLTAGE, "V", "trap")
        assert measure_max_min_pp("r", "m", wave, "max").value.value == D(3)
        assert measure_max_min_pp("r", "m", wave, "min").value.value == D(0)
        assert measure_max_min_pp("r", "m", wave, "pp").value.value == D(3)
        # Window ends inside segments use interpolated values (exact PL).
        res = measure_max_min_pp("r", "m", wave, "max", (D("0.5"), D("1.5")))
        assert res.value.value == D(3)
        res = measure_max_min_pp("r", "m", wave, "min", (D("0.5"), D("1.5")))
        assert res.value.value == D("1.5")
        bad = measure_max_min_pp("r", "m", wave, "max", (D(2), D(1)))
        assert bad.status == "INVALID_MEASUREMENT"

    def test_n038_mean_ramp(self):
        res = measure_mean("r", "m", _ramp())
        assert res.status == "OK"
        assert res.value.value == D("0.5")

    def test_n039_rms_ramp_constant(self):
        from academic_core.domain.engineering.lab.measure import measure_rms
        res = measure_rms("r", "m", _ramp())
        with lab_context():
            expect = (D(1) / D(3)).sqrt()
        assert res.value.value == expect
        const = make_waveform((D(0), D(1)), (D(2), D(2)), VOLTAGE, "V", "c")
        res = measure_rms("r", "m", const)
        assert res.value.value == D(2)

    def test_n040_rms_pl_exactness(self):
        # Discrete-sample RMS sqrt(mean(x^2)) differs from exact PL RMS on
        # coarse grids; the lab implements the exact PL integral.
        wave = make_waveform((D(0), D(1)), (D(0), D(1)), VOLTAGE, "V", "r")
        res = measure_rms("r", "m", wave)
        discrete = ((D(0) ** 2 + D(1) ** 2) / D(2)).sqrt()
        assert res.value.value != discrete
        with lab_context():
            assert res.value.value == (D(1) / D(3)).sqrt()

    def test_n041_crossings(self):
        from academic_core.domain.engineering.lab.measure import measure_crossings
        wave = make_waveform((D(0), D(1), D(2), D(3)), (D(0), D(2), D(0), D(2)),
                             VOLTAGE, "V", "tri")
        up = measure_crossings("r", "m", wave, D(1), "rising")
        assert up.value.value == 2
        down = measure_crossings("r", "m", wave, D(1), "falling")
        assert down.value.value == 1
        either = measure_crossings("r", "m", wave, D(1), "either")
        assert either.value.value == 3
        # Sample exactly on the level belongs to the ending segment only.
        exact = make_waveform((D(0), D(1), D(2)), (D(0), D(1), D(2)),
                              VOLTAGE, "V", "e")
        one = measure_crossings("r", "m", exact, D(1), "rising")
        assert one.value.value == 1

    def test_n042_period_frequency(self):
        from academic_core.domain.engineering.lab import measure as _mm
        wave = make_waveform((D(0), D(1), D(2), D(3), D(4)),
                             (D(0), D(2), D(0), D(2), D(0)),
                             VOLTAGE, "V", "tri")
        per = _mm.measure_period_frequency("r", "m", wave, "period", D(1))
        assert per.status == "OK"
        assert per.value.value == D(2)
        fr = _mm.measure_period_frequency("r", "m", wave, "frequency", D(1))
        assert fr.value.value == D("0.5")
        flat = make_waveform((D(0), D(1)), (D(1), D(1)), VOLTAGE, "V", "f")
        und = _mm.measure_period_frequency("r", "m", flat, "frequency", D(1))
        assert und.status == "UNDEFINED"
        assert und.value is None

    def test_n043_hysteresis(self):
        from academic_core.domain.engineering.lab.waveform import crossings
        wave = make_waveform((D(0), D(1), D(2), D(3), D(4), D(5)),
                             (D(0), D("1.1"), D("0.9"), D("1.1"), D("0.9"), D("1.1")),
                             VOLTAGE, "V", "chatter")
        plain = crossings(wave, D(1), "rising")
        assert len(plain) == 3
        quiet = crossings(wave, D(1), "rising", D("0.5"))
        assert len(quiet) == 1

    def test_n044_rise_time(self):
        from academic_core.domain.engineering.lab import measure as _mm
        wave = make_waveform((D(0), D(10)), (D(0), D(1)), VOLTAGE, "V", "ramp")
        res = _mm.measure_rise_fall("r", "m", wave, "rise_time",
                                    D("0.1"), D("0.9"), D(0), D(1))
        assert res.status == "OK"
        assert res.value.value == D(8)
        auto = _mm.measure_rise_fall("r", "m", wave, "rise_time",
                                     D("0.1"), D("0.9"), auto_levels=True)
        assert auto.value.value == D(8)
        missing = _mm.measure_rise_fall("r", "m", wave, "rise_time",
                                        D("0.1"), D("0.9"), D(0), D(1),
                                        window=(D(0), D(1)))
        # Window [0,1] holds 0..0.1: the high edge is missing.
        assert missing.status == "UNDEFINED"
        bad = _mm.measure_rise_fall("r", "m", wave, "rise_time",
                                    D("0.9"), D("0.1"), D(0), D(1))
        assert bad.status == "INVALID_MEASUREMENT"

    def test_n045_fall_time(self):
        from academic_core.domain.engineering.lab import measure as _mm
        wave = make_waveform((D(0), D(10)), (D(1), D(0)), VOLTAGE, "V", "f")
        res = _mm.measure_rise_fall("r", "m", wave, "fall_time",
                                    D("0.1"), D("0.9"), D(0), D(1))
        assert res.status == "OK"
        assert res.value.value == D(8)

    def test_n046_overshoot(self):
        from academic_core.domain.engineering.lab import measure as _mm
        wave = make_waveform((D(0), D(1), D(2)), (D(0), D("1.2"), D(1)),
                             VOLTAGE, "V", "step")
        res = _mm.measure_overshoot("r", "m", wave)
        assert res.status == "OK"
        assert res.value.value == D("0.2")
        flat = make_waveform((D(0), D(1)), (D(1), D(1)), VOLTAGE, "V", "f")
        zero = _mm.measure_overshoot("r", "m", flat)
        assert zero.status == "UNDEFINED"  # zero swing
        clean = make_waveform((D(0), D(1)), (D(0), D(1)), VOLTAGE, "V", "c")
        none = _mm.measure_overshoot("r", "m", clean)
        assert none.value.value == 0  # true zero: no overshoot
        falling = make_waveform((D(0), D(1), D(2)), (D(1), D("-0.2"), D(0)),
                                VOLTAGE, "V", "fs")
        res = _mm.measure_overshoot("r", "m", falling)
        assert res.value.value == D("0.2")

    def test_n047_settling(self):
        from academic_core.domain.engineering.lab import measure as _mm
        # Boundary touches at t=1.2 (exit), 4.8 (entry), 5.1 (exit),
        # 7.8 (entry, stays): t_s = 7.8.
        wave = make_waveform((D(0), D(1), D(3), D(5), D(6), D(8)),
                             (D(1), D(1), D(2), D(1), D(2), D(1)),
                             VOLTAGE, "V", "st")
        res = _mm.measure_settling("r", "m", wave, D(1), abs_band=D("0.1"))
        assert res.status == "OK"
        assert res.value.value == D("7.8")
        inside = make_waveform((D(0), D(4)), (D(1), D(1)), VOLTAGE, "V", "i")
        res = _mm.measure_settling("r", "m", inside, D(1), abs_band=D("0.1"))
        assert res.value.value == 0
        never = make_waveform((D(0), D(4)), (D(0), D(5)), VOLTAGE, "V", "n")
        res = _mm.measure_settling("r", "m", never, D(0), abs_band=D("0.1"))
        assert res.status == "UNDEFINED"
        both = _mm.measure_settling("r", "m", inside, D(1), tol=D("0.02"),
                                    abs_band=D("0.1"))
        assert both.status == "INVALID_MEASUREMENT"

    def test_n048_invalid_specs(self):
        from academic_core.domain.engineering.lab import create_session as _cs
        from f8n_lab_common import rc_step, transient_definition
        bad_window = MeasurementSpec("max", "v", window=(D(1), D(0)))
        s2 = _cs("w", rc_step())
        d2 = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("m", bad_window),))
        _, report = add_experiment(s2, d2)
        assert not report.ok
        with pytest.raises(LabConfigError):
            MeasurementSpec("bogus", "v")

    def test_n049_failure_never_zero(self):
        from academic_core.domain.engineering.lab import measure as _mm
        flat = make_waveform((D(0), D(1)), (D(1), D(1)), VOLTAGE, "V", "f")
        for res in (_mm.measure_period_frequency("r", "m", flat, "frequency", D(1)),
                    _mm.measure_overshoot("r", "m", flat),
                    _mm.measure_settling("r", "m", flat, D(9), abs_band=D("0.1"))):
            assert res.value is None
            assert res.status == "UNDEFINED"

    def test_n050_ac_measurements(self):
        from decimal import Decimal as _D
        from academic_core.domain.engineering.lab import measure as _mm
        from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
        h = DecimalComplex(_D(3), _D(4))  # |H| = 5
        g = _mm.measure_ac("r", "m", "ac_gain", h, _D(1000))
        assert g.value.value == 5
        db = _mm.measure_ac("r", "m", "ac_gain_db", h, _D(1000))
        with lab_context():
            expect = 20 * (D(5).ln() / D(10).ln())
        assert abs(db.value.value - expect) < D("1e-40")
        ph = _mm.measure_ac("r", "m", "ac_phase", h, _D(1000))
        with lab_context():
            from academic_core.domain.engineering.ac.phasors import phase
            assert ph.value.value == phase(h)
        zero = _mm.measure_ac("r", "m", "ac_gain", DecimalComplex(_D(0), _D(0)),
                              _D(1000))
        assert zero.status == "UNDEFINED" and zero.value is None
        amp = _mm.measure_ac_amplitude("r", "m", h, "peak", VOLTAGE, "V")
        assert amp.value.value == 5
        rms = _mm.measure_ac_amplitude("r", "m", h, "rms", VOLTAGE, "V")
        with lab_context():
            assert rms.value.value == 5 / D(2).sqrt()
        nobasis = _mm.measure_ac_amplitude("r", "m", h, None, VOLTAGE, "V")
        assert nobasis.status == "INVALID_MEASUREMENT"

    def test_n051_ac_amplitude_ratio(self):
        from academic_core.domain.engineering.lab import measure as _mm
        from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
        h = DecimalComplex(D(1), D(0))
        peak = _mm.measure_ac_amplitude("r", "m", h, "peak", VOLTAGE, "V")
        rms = _mm.measure_ac_amplitude("r", "m", h, "rms", VOLTAGE, "V")
        with lab_context():
            assert peak.value.value / rms.value.value == D(2).sqrt()

    def test_n052_bandwidth(self):
        from academic_core.domain.engineering.lab import measure as _mm
        from academic_core.domain.engineering.lab import BodeData
        assert _mm.measure_bandwidth("r", "m", None).status == "UNDEFINED"
        bw = BodeData((), D(100), D(1000), D("-3"), "x")
        res = _mm.measure_bandwidth("r", "m", bw)
        assert res.value.value == D(900)


# ---------------------------------------------------------------------------
# Transient family (N-053 .. N-058)
# ---------------------------------------------------------------------------

class TestTransient:
    def _rc_run(self, sid="rc"):
        from academic_core.domain.engineering.lab import create_session as _cs
        s = _cs(sid, rc_step())
        d = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("mx", MeasurementSpec("max", "v")),
                          ("mn", MeasurementSpec("min", "v"))))
        return run_ok(s, d)

    def test_n053_rc_step_bound(self):
        _, run, _ = self._rc_run()
        assert run.status == "COMPLETED"
        mx = next(m for m in run.measurements if m.key == "mx")
        assert mx.status == "OK"
        assert mx.value.value <= 1  # step 0 -> 1 never overshoots RC charge
        assert mx.value.value > D("0.98")  # edge at 1 ms, 4 tau by 5 ms

    def test_n054_waveform_exact_copy(self):
        from academic_core.domain.engineering.mna.transient import solve_transient
        _, run, _ = self._rc_run("copy")
        direct = solve_transient(rc_step(), transient_config())
        assert tuple(run.result.times) == tuple(direct.times)
        assert tuple(run.result.node_trajectories["out"]) == \
            tuple(direct.node_trajectories["out"])

    def test_n055_function_generator_sine(self):
        from academic_core.domain.engineering.lab.stimulus import stimulus_wave_dict
        stim = function_generator("V1", "sine", amplitude=Q("1 V"),
                                  offset=Q("0 V"), frequency=D(50))
        assert stim.kind == "SINE"
        wave = stimulus_wave_dict(stim)
        assert wave["type"] == "sine"
        with lab_context():
            assert wave["td"] == 0
        lag = function_generator("V1", "sine", amplitude=Q("1 V"),
                                 offset=Q("0 V"), frequency=D(50),
                                 phase_lag=D(90))
        with lab_context():
            assert lag.td == D(90) / (D(360) * D(50))
        with pytest.raises(LabConfigError):
            function_generator("V1", "sine", amplitude=Q("1 V"),
                               offset=Q("0 V"), frequency=D(50),
                               phase_lag=D(-10))
        with pytest.raises(LabConfigError):
            function_generator("V1", "triangle", amplitude=D(1))

    def test_n056_pulse_duty(self):
        stim = function_generator("V1", "pulse", amplitude=Q("1 V"),
                                  offset=Q("0 V"), frequency=D(1000),
                                  duty=D("0.2"))
        assert stim.kind == "PULSE"
        with lab_context():
            assert stim.period == D("0.001")
            assert stim.width == D("0.2") * D("0.001")
        sq = function_generator("V1", "square", amplitude=Q("1 V"),
                                offset=Q("0 V"), frequency=D(1000))
        with lab_context():
            assert sq.width == D("0.5") * D("0.001")
        with pytest.raises(LabConfigError):
            function_generator("V1", "pulse", amplitude=Q("1 V"),
                               offset=Q("0 V"), frequency=D(1000),
                               duty=D("0.0001"), rise=D("0.01"), fall=D("0.01"))

    def test_n057_failed_transient_no_waveform(self):
        # Floating circuit: the engine cannot solve; the run is appended
        # as failed and every measurement is NO_DATA (never 0).
        from academic_core.domain.engineering.lab import create_session as _cs
        from academic_core.domain.engineering.circuit import Circuit, Component
        c = Circuit("float")
        c.add(Component("R1", "R", Q("1 kohm"), {"1": "a", "2": "b"}))
        s = _cs("float-tran", c)
        d = transient_definition(
            probes=(("v", VoltageProbe("a", "b")),),
            measurements=(("mx", MeasurementSpec("max", "v")),))
        s = add_ok(s, d)
        from academic_core.domain.engineering.lab import run_experiment as _run
        s, run = _run(s, experiment_id(d, s.circuit))
        assert run.status in ("INVALID_CIRCUIT", "SOLVER_FAILURE")
        assert all(m.status == "NO_DATA" for m in run.measurements)
        assert run.readings == ()

    def _sine_rc(self, sid):
        from academic_core.domain.engineering.lab import create_session as _cs
        from academic_core.domain.engineering.circuit import Circuit, Component
        c = Circuit("sine")
        c.add(Component("V1", "V", Q("0 V"), {"+": "in", "-": "0"},
                        {"wave": {"type": "sine", "vo": Q("0 V"),
                                  "va": Q("1 V"), "freq": D(100), "td": D(0)}}))
        c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
        c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"}))
        return _cs(sid, c)

    def _sine_def(self, slope, level="0.3"):
        from academic_core.domain.engineering.mna.transient import TransientConfig
        return ExperimentDefinition(
            label="trig",
            analysis=AnalysisSpec("TRANSIENT", transient=TransientConfig(
                "TR", D("0.03"), D("0.00005"), D("1E-12"), D("0.0005"),
                D("1E-4"), D("1E-6"))),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope",
                channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                trigger=TriggerSpec("v", D(level), slope, D("0.0002"),
                                    D("0.002")), sample_count=50)),))

    def test_n058_trigger(self):
        from academic_core.domain.engineering.lab import create_session as _cs
        # Rising trigger on the RC charge (crosses 0.5 at ~0.69 ms).
        s = _cs("trig", rc_step())
        d = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope",
                channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                trigger=TriggerSpec("v", D("0.5"), "rising", D("0.0001"),
                                    D("0.002")), sample_count=50)),))
        _, run, _ = run_ok(s, d)
        reading = run.readings[0]
        assert reading.status == "OK"
        assert reading.data.trigger_time is not None
        # Falling + either triggers on a sine-driven RC.
        for slope in ("falling", "either"):
            s2 = self._sine_rc(f"sine-{slope}")
            _, run2, _ = run_ok(s2, self._sine_def(slope))
            assert run2.readings[0].status == "OK", slope
            assert run2.readings[0].data.trigger_time is not None
        # No crossing -> NO_TRIGGER, no data.
        d2 = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope",
                channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                trigger=TriggerSpec("v", D("5"), "rising", D("0.0001"),
                                    D("0.002")), sample_count=50)),))
        s2 = _cs("trig2", rc_step())
        _, run2, _ = run_ok(s2, d2)
        assert run2.readings[0].status == "NO_TRIGGER"
        # Window outside the span -> OUT_OF_RANGE.
        d3 = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("scope", InstrumentSpec(
                "oscilloscope",
                channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                window=(D(0), D(99)), sample_count=50)),))
        s3 = _cs("trig3", rc_step())
        _, run3, _ = run_ok(s3, d3)
        assert run3.readings[0].status == "OUT_OF_RANGE"
