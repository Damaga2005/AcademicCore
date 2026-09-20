"""F8-N virtual laboratory verification: VLAB end-to-end + references.

VLAB-001 .. VLAB-006, measurement references, N-088 .. N-090 of
docs/gates/GATE-F8N-DESIGN.md. Expected values are analytic; every
comparison records expected / actual / absolute error / relative error /
tolerance.
"""
from decimal import Decimal as D

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.lab import (
    AnalysisKind,
    AnalysisSpec,
    CurrentProbe,
    ExperimentDefinition,
    InstrumentKind,
    InstrumentSpec,
    MeasurementKind,
    MeasurementSpec,
    ScopeChannel,
    VoltageProbe,
    create_session,
    function_generator,
    replay_run,
    run_experiment,
)
from academic_core.domain.engineering.lab.model import lab_context
from academic_core.domain.engineering.lab.serialize import (
    dumps_session,
    experiment_id,
    loads_document,
    to_document,
)
from academic_core.domain.engineering.mna.analysis import (
    GridSpec,
    MCConfig,
    ObservableSpec,
    ParamAddress,
    SweepConfig,
    UniformDist,
    WorstCaseConfig,
)
from academic_core.domain.engineering.mna.transient import TransientConfig
from academic_core.domain.engineering.units import parse_quantity as Q
from f8n_lab_common import (
    add_ok,
    ammeter,
    divider,
    new_session,
    op_definition,
    rc_ac,
    run_ok,
    transient_tight_config,
    voltmeter,
)


def _eid(session, definition):
    return experiment_id(definition, session.circuit)


def _rc_vlab():
    # RC step 0 -> 1 V with the edge at t0 = 1 ms (DEVIATION D-V2: the
    # design gate writes t0 = 0, but the certified engine initializes
    # the capacitor from the DC operating point at t = 0, where the
    # source already reads v2 -- the visible edge needs t0 > 0).
    c = Circuit("vlab2")
    c.add(Component("V1", "V", Q("0 V"), {"+": "in", "-": "0"},
                    {"wave": {"type": "step", "v1": Q("0 V"), "v2": Q("1 V"),
                              "t0": D("0.001")}}))
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "in", "2": "out"}))
    c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"}))
    return c


def _report(expected, actual, tolerance):
    with lab_context():
        abs_err = abs(actual - expected)
        rel_err = abs_err / abs(expected) if expected != 0 else abs_err
    return {"expected": expected, "actual": actual, "abs_err": abs_err,
            "rel_err": rel_err, "tolerance": tolerance,
            "pass": rel_err <= tolerance}


class TestVLAB:
    def test_vlab001_resistive(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),
                                  ("i", CurrentProbe("R1"))),
                          instruments=(voltmeter("m", "v"), ammeter("a", "i")))
        _, run, _ = run_ok(s, d)
        by_key = {r.key: r for r in run.readings}
        with lab_context():
            v_expect = D(20) / D(3)
            i_expect = D(10) / D(3000)
        v_rep = _report(v_expect, by_key["m"].data.value, D("1E-40"))
        i_rep = _report(i_expect, by_key["a"].data.value, D("1E-40"))
        assert v_rep["pass"], v_rep
        assert i_rep["pass"], i_rep
        assert run.status == "COMPLETED"

    def test_vlab002_rc_transient(self):
        from academic_core.domain.engineering.mna.transient import (
            solve_transient)
        t0, rc, tstop = D("0.001"), D("0.001"), D("0.006")
        s = create_session("vlab2", _rc_vlab())
        d = ExperimentDefinition(
            label="vlab2",
            analysis=AnalysisSpec("TRANSIENT",
                                  transient=transient_tight_config("0.006")),
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(
                ("mx", MeasurementSpec("max", "v")),
                ("mn", MeasurementSpec("min", "v")),
                ("pp", MeasurementSpec("pp", "v")),
                ("mean", MeasurementSpec("mean", "v",
                                         window=(t0, tstop))),
                ("rms", MeasurementSpec("rms", "v", window=(t0, tstop))),
                ("rise", MeasurementSpec("rise_time", "v", low_frac=D("0.1"),
                                         high_frac=D("0.9"), v_low=D(0),
                                         v_high=D(1),
                                         window=(t0, tstop))),
                ("stl", MeasurementSpec("settling_time", "v", v_final=D(1),
                                        tol=D("0.02"), window=(t0, tstop))),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status == "COMPLETED"
        direct = solve_transient(_rc_vlab(), transient_tight_config("0.006"))
        # (i) waveform vs analytic within the certified error bound.
        with lab_context():
            worst = D(0)
            for t, v in zip(direct.times, direct.node_trajectory("out")):
                a = D(0) if t < t0 else D(1) - (-(t - t0) / rc).exp()
                e = abs(v - a)
                if e > worst:
                    worst = e
        assert worst <= D("1E-5"), worst
        got = {m.key: m for m in run.measurements}
        assert all(m.status == "OK" for m in run.measurements)
        # (ii) rise 10-90 = RC ln 9; settling (2 %) = RC ln 50.
        with lab_context():
            rise_expect = rc * (D(9).ln())
            stl_expect = rc * (D(50).ln())
            t5 = D(5) * rc
            mean_expect = 1 - (1 - (-t5 / rc).exp()) * rc / t5
            sq = 1 - 2 * (1 - (-t5 / rc).exp()) * rc / t5 \
                + (1 - (-(2 * t5) / rc).exp()) * rc / (2 * t5)
            rms_expect = sq.sqrt()
        for key, expect in (("rise", rise_expect), ("stl", stl_expect),
                            ("mean", mean_expect), ("rms", rms_expect)):
            rep = _report(expect, got[key].value.value, D("1E-3"))
            assert rep["pass"], (key, rep)
        # Scope reading equals interpolation of the same samples.
        from academic_core.domain.engineering.lab import (
            InstrumentSpec as _IS, ScopeChannel as _SC)
        d2 = ExperimentDefinition(
            label="scope",
            analysis=AnalysisSpec("TRANSIENT",
                                  transient=transient_tight_config("0.006")),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sc", _IS(
                "oscilloscope", channels=(_SC("v", D(1), D(0), "DC"),),
                window=(t0, tstop), sample_count=64)),))
        s2 = add_ok(create_session("vlab2s", _rc_vlab()), d2)
        s2, run2 = run_experiment(s2, _eid(s2, d2))
        from academic_core.domain.engineering.lab.waveform import (
            interpolate, make_waveform)
        from academic_core.domain.engineering.units import VOLTAGE
        wave = make_waveform(tuple(direct.times),
                             tuple(direct.node_trajectory("out")),
                             VOLTAGE, "V", "v")
        grid = run2.readings[0].data.channels[0].times
        raw = run2.readings[0].data.channels[0].raw
        for t, v in zip(grid, raw):
            assert v == interpolate(wave, t)

    def test_vlab003_ac_divider(self):
        from academic_core.domain.engineering.ac.bode import magnitude_db
        from academic_core.domain.engineering.ac.phasors import (
            magnitude, phase)
        s = new_session(rc_ac(), "vlab3")
        d = ExperimentDefinition(
            label="vlab3",
            analysis=AnalysisSpec("AC_POINT", frequency=Q("1kHz")),
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("g", MeasurementSpec("ac_gain", "v")),
                          ("db", MeasurementSpec("ac_gain_db", "v")),
                          ("ph", MeasurementSpec("ac_phase", "v"))))
        _, run, _ = run_ok(s, d)
        assert run.status == "COMPLETED"
        with lab_context():
            wrc = 2 * D("3.14159265358979323846264338327950288419716939937510") \
                * D(1000) * D(1000) * D("0.000001")
            mag_expect = 1 / (1 + wrc * wrc).sqrt()
            from academic_core.domain.engineering.math.trig import decimal_atan2
            ph_expect = -decimal_atan2(wrc, D(1), __import__(
                "academic_core.domain.engineering.math.trig",
                fromlist=["make_context"]).make_context())
            db_expect = magnitude_db(mag_expect).value
        got = {m.key: m.value.value for m in run.measurements}
        for key, expect in (("g", mag_expect), ("db", db_expect),
                            ("ph", ph_expect)):
            rep = _report(expect, got[key], D("1E-40"))
            assert rep["pass"], (key, rep)

    def test_vlab004_dc_sweep(self):
        cfg = SweepConfig(ParamAddress("V1", "value"),
                          GridSpec.linear(D(0), D(10), D(2)),
                          (ObservableSpec("node_voltage", "out"),))
        d = ExperimentDefinition(
            label="vlab4", analysis=AnalysisSpec("DC_SWEEP", sweep=cfg),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))
        s = new_session()
        _, run, _ = run_ok(s, d)
        from academic_core.domain.engineering.mna.analysis import (
            solve_dc_sweep)
        direct = solve_dc_sweep(divider(), cfg)
        assert run.result.to_dict() == direct.to_dict()
        reading = run.readings[0]
        for axis_v, val, point in zip(reading.data.axis,
                                      reading.data.values, direct.points):
            params = dict(point.parameters)
            assert axis_v == params["V1.value"]
            assert val == point.observables["node_voltage:out"]

    def test_vlab005_monte_carlo(self):
        def _mc(seed):
            cfg = MCConfig(
                8, ((ParamAddress("R1", "value"),
                     UniformDist(D(900), D(1100))),),
                None, (ObservableSpec("node_voltage", "out"),), "dc-op")
            return ExperimentDefinition(
                label="vlab5", analysis=AnalysisSpec("MONTE_CARLO", mc=cfg),
                seed=seed,
                probes=(("v", VoltageProbe("out", "0")),))
        digests, plans, stats = [], [], []
        for i in range(3):
            s = new_session(divider(), f"mc{i}")
            _, run, _ = run_ok(s, _mc(42))
            digests.append(run.result_digest)
            plans.append(run.result.plan_digest)
            stats.append(run.result.statistics)
        assert digests[0] == digests[1] == digests[2]
        assert plans[0] == plans[1] == plans[2]
        assert stats[0] == stats[1] == stats[2]
        s = new_session(divider(), "mcX")
        _, runx, _ = run_ok(s, _mc(43))
        assert runx.result.plan_digest != plans[0]

    def test_vlab006_replay(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        from academic_core.domain.engineering.lab.run import execute_run
        _, payload = execute_run(s.circuit, d, run.experiment_id, 1,
                                 s.session_id)
        text = dumps_session(s, {run.run_id: payload})
        loaded = loads_document(text)
        assert loaded.status == "OK"
        rep = replay_run(loaded.session, run.run_id)
        assert rep.status == "EQUIVALENT"
        from academic_core.domain.engineering.lab.serialize import (
            dumps_canonical)
        doc = to_document(loaded.session, {run.run_id: payload})
        doc["records"][0]["runs"][0]["result_digest"] = "f" * 64
        assert loads_document(dumps_canonical(doc)).status == \
            "INVALID_SERIALIZATION"


class TestMeasurementReferences:
    def test_sine_rms_pl_bound(self):
        # A sin(wt) over one period, 1000 samples/period (PL): rms = A/2^0.5
        # up to the PL-model error of order (w h)^2 ~= 4e-5.
        from academic_core.domain.engineering.lab import measure as _mm
        from academic_core.domain.engineering.lab.waveform import make_waveform
        from academic_core.domain.engineering.units import VOLTAGE
        import math
        n = 1000
        ts = tuple(D(i) / D(n) for i in range(n + 1))
        with lab_context():
            xs = tuple(D(math.sin(2 * math.pi * i / n)) for i in range(n + 1))
        wave = make_waveform(ts, xs, VOLTAGE, "V", "sine")
        res = _mm.measure_rms("r", "m", wave)
        with lab_context():
            expect = 1 / D(2).sqrt()
            rel = abs(res.value.value - expect) / expect
        assert rel < D("1E-3"), rel

    def test_ac_gain_closed_form(self):
        from academic_core.domain.engineering.lab import measure as _mm
        from academic_core.domain.engineering.math.decimal_complex import (
            DecimalComplex)
        with lab_context():
            x = D("2.5")
            h = DecimalComplex(D(1) / (D(1) + x * x),
                               -x / (D(1) + x * x))
            from academic_core.domain.engineering.ac.phasors import (
                magnitude, phase)
            from academic_core.domain.engineering.ac.bode import magnitude_db
            g = _mm.measure_ac("r", "m", "ac_gain", h, D(1000))
            assert g.value.value == magnitude(h)
            db = _mm.measure_ac("r", "m", "ac_gain_db", h, D(1000))
            assert db.value.value == magnitude_db(magnitude(h)).value
            ph = _mm.measure_ac("r", "m", "ac_phase", h, D(1000))
            assert ph.value.value == phase(h)


class TestDeterminism:
    def _all_kinds(self):
        from f8n_lab_common import (
            rc_step, transient_config, transient_definition)
        from academic_core.domain.engineering.mna.sensitivity import (
            SensitivityConfig)
        div = divider()
        cfgs = []
        cfgs.append(("OP", div, op_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(voltmeter("m", "v"),),
            measurements=(("d", MeasurementSpec("dc_value", "v")),))))
        cfgs.append(("AC_POINT", rc_ac(), ExperimentDefinition(
            label="a", analysis=AnalysisSpec("AC_POINT", frequency=Q("1kHz")),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(voltmeter("m", "v"),),
            measurements=(("g", MeasurementSpec("ac_gain", "v")),))))
        cfgs.append(("TRANSIENT", rc_step(), transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("mx", MeasurementSpec("max", "v")),))))
        sweep = SweepConfig(ParamAddress("V1", "value"),
                            GridSpec.linear(D(0), D(10), D(10)),
                            (ObservableSpec("node_voltage", "out"),))
        cfgs.append(("M1", div, ExperimentDefinition(
            label="m1", analysis=AnalysisSpec("DC_SWEEP", sweep=sweep),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        cfgs.append(("M2", div, ExperimentDefinition(
            label="m2",
            analysis=AnalysisSpec(
                "PARAM_SWEEP",
                param_sweep=__import__(
                    "academic_core.domain.engineering.mna.analysis",
                    fromlist=["ParamSweepConfig"]).ParamSweepConfig(
                        "grid", ParamAddress("R1", "value"),
                        GridSpec.log(D(100), D(10000), 3), (), (),
                        (ObservableSpec("node_voltage", "out"),), False)),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        cfgs.append(("M3", div, ExperimentDefinition(
            label="m3",
            analysis=AnalysisSpec(
                "CORNERS",
                corners=WorstCaseConfig(
                    ((ParamAddress("R1", "value"), D(900), D(1100)),),
                    (ObservableSpec("node_voltage", "out"),), False)),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        cfgs.append(("M4", div, ExperimentDefinition(
            label="m4",
            analysis=AnalysisSpec(
                "SENS_DC",
                sens=SensitivityConfig(
                    (ParamAddress("R1", "value"),),
                    (ObservableSpec("node_voltage", "out"),), True)),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        cfgs.append(("M4-AC", rc_ac(), ExperimentDefinition(
            label="m4ac",
            analysis=AnalysisSpec(
                "SENS_AC",
                sens_ac=__import__(
                    "academic_core.domain.engineering.mna.sensitivity",
                    fromlist=["ACSensitivityConfig"]).ACSensitivityConfig(
                        "1kHz", (ParamAddress("R1", "value"),),
                        (ObservableSpec("node_voltage", "out"),))),
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        cfgs.append(("M5", div, ExperimentDefinition(
            label="m5",
            analysis=AnalysisSpec(
                "MONTE_CARLO",
                mc=MCConfig(
                    4, ((ParamAddress("R1", "value"),
                         UniformDist(D(900), D(1100))),),
                    None, (ObservableSpec("node_voltage", "out"),), "dc-op")),
            seed=11,
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))))
        return cfgs

    def test_n088_triple_determinism(self):
        from academic_core.domain.engineering.lab.run import execute_run
        for name, circuit, definition in self._all_kinds():
            first = None
            for trial in range(3):
                # Same inputs (including session_id) -> identical outputs.
                s = create_session(f"det-{name}", circuit)
                s = add_ok(s, definition)
                s, run = run_experiment(s, _eid(s, definition))
                _, payload = execute_run(s.circuit, definition,
                                         run.experiment_id, 1,
                                         s.session_id)
                text = dumps_session(s, {run.run_id: payload})
                signature = (run.result_digest, run.status,
                             tuple((m.key, m.status,
                                    m.value.value if m.value else None)
                                   for m in run.measurements),
                             text)
                if first is None:
                    first = signature
                assert signature == first, name

    def test_n089_insertion_order_invariance(self):
        from academic_core.domain.engineering.mna.analysis import (
            ParamAddress as _A)
        s = new_session()
        d1 = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("OP"),
            overrides=((_A("R1", "value"), D(500)),
                       (_A("R2", "value"), D(600))),
            stimuli=(function_generator("V1", "dc", offset=Q("5 V")),),
            probes=(("a", VoltageProbe("in", "0")),
                    ("b", VoltageProbe("out", "0"))))
        d2 = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("OP"),
            overrides=((_A("R2", "value"), D(600)),
                       (_A("R1", "value"), D(500))),
            stimuli=(function_generator("V1", "dc", offset=Q("5 V")),),
            probes=(("b", VoltageProbe("out", "0")),
                    ("a", VoltageProbe("in", "0"))))
        assert _eid(s, d1) == _eid(s, d2)

    def test_n090_ambient_context_no_effect(self):
        from decimal import Context, localcontext
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        _, run_base, _ = run_ok(s, d)
        with localcontext(Context(prec=10, rounding="ROUND_DOWN")):
            s2 = new_session(divider(), "amb")
            _, run_alt, _ = run_ok(s2, d)
        assert run_alt.result_digest == run_base.result_digest
        assert run_alt.readings[0].data.value == \
            run_base.readings[0].data.value


class TestRegressionMarkers:
    def test_n109_float_free(self):
        import ast
        from pathlib import Path
        for path in sorted((Path("src/academic_core/domain/engineering/lab")
                            ).glob("*.py")):
            src = path.read_text(encoding="utf-8")
            assert "float(" not in src, path.name
            tree = ast.parse(src)
            for node in ast.walk(tree):
                assert not (isinstance(node, ast.Constant)
                            and isinstance(node.value, float)), path.name

    def test_n110_dependency_direction(self):
        # lab -> engines only: no engine module may import lab/.
        import ast
        from pathlib import Path
        base = Path("src/academic_core/domain/engineering")
        offenders = []
        for path in sorted(base.rglob("*.py")):
            if "lab" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if "lab" in a.name.split("."):
                            offenders.append((str(path), a.name))
                elif isinstance(node, ast.ImportFrom):
                    mod = (node.module or "")
                    if "lab" in mod.split(".") or \
                            any("lab" == a.name for a in node.names):
                        offenders.append((str(path), mod))
        assert not offenders, offenders

    def test_n108_f8_suites_green(self):
        import subprocess
        import sys
        files = ["tests/test_f8h_nonlinear_dc.py", "tests/test_f8i_bjt.py",
                 "tests/test_f8i_nonlinear_bjt.py",
                 "tests/test_f8j_small_signal_ac.py",
                 "tests/test_f8k_additional_semiconductors.py",
                 "tests/test_f8l_transient.py", "tests/test_f8m_analysis.py"]
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-m", "not slow"] + files,
            capture_output=True, text=True, timeout=1200)
        assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]

    def test_n110_git_clean_certified(self):
        import subprocess
        try:
            proc = subprocess.run(
                ["git", "status", "--short", "--",
                 "src/academic_core/domain/engineering/mna",
                 "src/academic_core/domain/engineering/ac",
                 "src/academic_core/domain/engineering/circuit.py",
                 "src/academic_core/domain/engineering/units.py"],
                capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            pytest.skip("git unavailable")
        assert proc.returncode == 0
        assert proc.stdout.strip() == "", proc.stdout


class TestBenchmarks:
    def test_bench_diagnostic(self):
        # Diagnostic only: counts + wall time printed, never asserted.
        import time
        from academic_core.domain.engineering.lab.run import execute_run
        t0 = time.perf_counter()
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),),
                          measurements=(("x", MeasurementSpec("dc_value", "v")),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        _, payload = execute_run(s.circuit, d, run.experiment_id, 1,
                                 s.session_id)
        text = dumps_session(s, {run.run_id: payload})
        dt = time.perf_counter() - t0
        print(f"\n[bench] session+OP+measure+serialize: {dt:.3f}s, "
              f"{len(text)} bytes, digest {run.result_digest[:16]}")
        assert run.status == "COMPLETED"

    def test_bench_families_diagnostic(self):
        # Diagnostic only: per-family counts/sizes, no time assertions.
        import time
        from academic_core.domain.engineering.lab.run import execute_run
        from f8n_lab_common import rc_step, transient_config, transient_definition
        rows = []
        s = create_session("bench-tr", rc_step())
        d = transient_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            measurements=(("mx", MeasurementSpec("max", "v")),
                          ("rms", MeasurementSpec("rms", "v"))))
        t0 = time.perf_counter()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        _, payload = execute_run(s.circuit, d, run.experiment_id, 1,
                                 s.session_id)
        n_samples = len(run.result.times)
        text = dumps_session(s, {run.run_id: payload})
        rows.append(f"transient: {n_samples} samples, {len(text)} bytes, "
                    f"{time.perf_counter() - t0:.3f}s")
        cfg = MCConfig(
            4, ((ParamAddress("R1", "value"), UniformDist(D(900), D(1100))),),
            None, (ObservableSpec("node_voltage", "out"),), "dc-op")
        dm = ExperimentDefinition(
            label="m", analysis=AnalysisSpec("MONTE_CARLO", mc=cfg), seed=1,
            probes=(("v", VoltageProbe("out", "0")),))
        t0 = time.perf_counter()
        s2 = add_ok(new_session(divider(), "bench-mc"), dm)
        s2, run2 = run_experiment(s2, _eid(s2, dm))
        _, payload2 = execute_run(s2.circuit, dm, run2.experiment_id, 1,
                                  s2.session_id)
        text2 = dumps_session(s2, {run2.run_id: payload2})
        rows.append(f"montecarlo(4): {len(text2)} bytes, "
                    f"{time.perf_counter() - t0:.3f}s")
        print("\n[bench] " + " | ".join(rows))
        assert run.status == "COMPLETED" and run2.status == "COMPLETED"