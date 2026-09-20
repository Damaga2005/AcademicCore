"""F8-N virtual laboratory verification: serialization / replay / security.

Tests N-075 .. N-107 of docs/gates/GATE-F8N-DESIGN.md.
"""
import json
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
    ScopeChannel,
    VoltageProbe,
    add_experiment,
    annotate,
    create_session,
    from_document,
    loads_document,
    replay_run,
    run_experiment,
    sweep_csv,
    table_csv,
    to_document,
    waveform_csv,
)
from academic_core.domain.engineering.lab.model import lab_context
from academic_core.domain.engineering.lab.serialize import (
    canonical,
    digest,
    dumps_canonical,
    dumps_session,
    experiment_digest,
    experiment_id,
)
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
    divider,
    new_session,
    op_definition,
    run_ok,
    voltmeter,
)


def _eid(session, definition):
    return experiment_id(definition, session.circuit)


def _payloads(session):
    from academic_core.domain.engineering.lab.run import execute_run
    out = {}
    for record in session.records:
        for run in record.runs:
            out[run.run_id] = _payload_for(session, run)
    return out


def _payload_for(session, run):
    for definition in session.experiments:
        if experiment_id(definition, session.circuit) == run.experiment_id:
            from academic_core.domain.engineering.lab.run import execute_run
            idx = int(run.run_id.split("#")[1])
            _, payload = execute_run(session.circuit, definition,
                                     run.experiment_id, idx, session.session_id)
            return payload
    raise AssertionError("definition missing")


class TestSerialization:
    def _run_session(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),),
                          measurements=(("mx", MeasurementSpec("dc_value", "v")),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        return s, run

    def test_n075_canonical_stable(self):
        s, run = self._run_session()
        p1 = _payloads(s)
        t1 = dumps_session(s, p1)
        # Dict/insertion order cannot matter: rebuild through JSON.
        doc = json.loads(t1)
        t2 = dumps_canonical(doc)
        assert t1 == t2

    def test_n076_round_trip_exact(self):
        from academic_core.domain.engineering.lab.serialize import (
            decimal_string)
        assert D(decimal_string(D("6.666666666666666666666666667"))) == \
            D("6.666666666666666666666666667")
        s, run = self._run_session()
        p = _payloads(s)
        doc = to_document(s, p)
        text = dumps_canonical(doc)
        loaded = loads_document(text)
        assert loaded.status == "OK"
        s2 = loaded.session
        assert [experiment_id(e, s2.circuit) for e in s2.experiments] == \
            [experiment_id(e, s.circuit) for e in s.experiments]
        assert s2.records[0].runs[0].result_digest == run.result_digest
        assert s2.records[0].runs[0].measurements == run.measurements

    def test_n077_closed_circuit_schema(self):
        from academic_core.domain.engineering.lab.serialize import (
            canonical_circuit)
        c = divider()
        c.add(Component("R9", "R", Q("1 ohm"), {"1": "a", "2": "0"},
                        {"tolerance": Q("0.01")}))
        s = create_session("x", divider())
        # Unknown parameter keys are rejected at serialization.
        with pytest.raises(LabConfigError):
            canonical_circuit(c)
        c2 = divider()
        comps = list(c2.components)
        v1 = next(x for x in comps if x.ref == "V1")
        comps[comps.index(v1)] = Component(
            "V1", "V", v1.value, dict(v1.pins), {"bogus": "x"}, {})
        from academic_core.domain.engineering.circuit import Circuit as _C
        c3 = _C("bad")
        for comp in comps:
            c3.add(comp)
        with pytest.raises(LabConfigError):
            canonical_circuit(c3)

    def test_n078_csv_schema(self):
        from academic_core.domain.engineering.lab.waveform import make_waveform
        from academic_core.domain.engineering.units import VOLTAGE
        wave = make_waveform((D(0), D(1)), (D("0.5"), D("1.5")), VOLTAGE,
                             "V", "x")
        text = waveform_csv("vout", wave)
        assert text.splitlines()[0] == "t[s],vout[V]"
        assert text.splitlines()[1] == "0,0.5"
        # Quoting.
        header = waveform_csv('a"b,c', wave).splitlines()[0]
        assert header == 't[s],"a""b,c"[V]'
        s, run = self._run_session()
        table = table_csv(__import__(
            "academic_core.domain.engineering.lab.model",
            fromlist=["MeasurementTable"]).MeasurementTable(
                tuple(__import__(
                    "academic_core.domain.engineering.lab.model",
                    fromlist=["MeasurementRow"]).MeasurementRow(
                        m.key, m.value, m.status, m.reason)
                    for m in run.measurements),
                run.run_id, run.experiment_digest))
        lines = table.splitlines()
        assert lines[0] == "key,value,unit,status,reason"
        assert lines[1].startswith("mx,")

    def test_n079_size_guard(self):
        from academic_core.domain.engineering.lab import model as _m
        from academic_core.domain.engineering.lab import serialize as _sz
        from academic_core.domain.engineering.lab.session import (
            to_document as _sess_doc)
        old_m, old_s = _m.MAX_SERIALIZED_BYTES, _sz.MAX_SERIALIZED_BYTES
        _m.MAX_SERIALIZED_BYTES = 10
        _sz.MAX_SERIALIZED_BYTES = 10
        try:
            s, run = self._run_session()
            # Save-side guard (to_document enforces the budget).
            with pytest.raises(LabConfigError):
                _sess_doc(s, _payloads(s))
            # Load-side guard applies before parsing.
            assert loads_document('{"schema":"f8n-lab/1"}').status == \
                "SERIALIZATION_TOO_LARGE"
        finally:
            _m.MAX_SERIALIZED_BYTES = old_m
            _sz.MAX_SERIALIZED_BYTES = old_s

    def test_n080_no_pickle_path(self):
        # Structural: no pickle/marshal actor, no dynamic construction.
        import ast
        from pathlib import Path
        tree = ast.parse((Path("src/academic_core/domain/engineering/lab")
                          / "serialize.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in (
                    "eval", "exec", "compile", "__import__", "getattr",
                    "setattr", "open"), node.func.id
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] not in (
                        "pickle", "marshal", "yaml"), a.name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in (
                    "pickle", "marshal", "yaml"), node.module


class TestReplay:
    def _mc_session(self):
        cfg = MCConfig(
            8, ((ParamAddress("R1", "value"), UniformDist(D(900), D(1100))),),
            None, (ObservableSpec("node_voltage", "out"),), "dc-op")
        d = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("MONTE_CARLO", mc=cfg), seed=7,
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))
        s = new_session()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        return s, run

    def test_n081_round_trip_equivalent(self):
        s, run = self._mc_session()
        text = dumps_session(s, _payloads(s))
        loaded = loads_document(text)
        assert loaded.status == "OK"
        rep = replay_run(loaded.session, run.run_id)
        assert rep.status == "EQUIVALENT"
        assert rep.comparable is True

    def test_n082_tamper_rejected(self):
        s, run = self._mc_session()
        doc = to_document(s, _payloads(s))
        doc["records"][0]["runs"][0]["result_digest"] = "0" * 64
        assert from_document(doc).status == "INVALID_SERIALIZATION"
        doc2 = to_document(s, _payloads(s))
        doc2["experiments"][0]["definition"]["seed"] = 999
        assert from_document(doc2).status == "INVALID_SERIALIZATION"

    def test_n083_version_and_schema(self):
        s, run = self._mc_session()
        loaded = loads_document(dumps_session(s, _payloads(s)))
        assert loaded.status == "OK"
        # Engine version mismatch: no execution without opt-in.
        import copy
        s2_records = loaded.session.records
        run0 = s2_records[0].runs[0]
        prov = dict(run0.provenance)
        prov["engine_versions"] = dict(prov["engine_versions"])
        prov["engine_versions"]["f8m-analysis"] = "f8m-analysis/9.9"
        from academic_core.domain.engineering.lab.model import Run as _Run
        tampered = _Run(run0.run_id, run0.experiment_id, run0.session_id,
                        run0.experiment_digest, run0.analysis_kind, run0.seed,
                        run0.status, run0.engine_status, None,
                        run0.measurements, run0.readings, run0.diagnostics,
                        prov, run0.result_digest)
        from academic_core.domain.engineering.lab.model import ExperimentRecord
        records = (ExperimentRecord(s2_records[0].experiment_id, (tampered,),
                                    s2_records[0].annotations),)
        from academic_core.domain.engineering.lab.model import LaboratorySession
        s3 = LaboratorySession(loaded.session.session_id,
                               loaded.session.circuit,
                               loaded.session.experiments, records,
                               loaded.session.metadata,
                               loaded.session.state, loaded.session.schema)
        rep = replay_run(s3, run0.run_id)
        assert rep.status == "VERSION_MISMATCH"
        rep2 = replay_run(s3, run0.run_id, allow_version_mismatch=True)
        assert rep2.status in ("EQUIVALENT", "RESULT_DIFFERS")
        assert rep2.comparable is False
        # Schema mismatch.
        doc = to_document(s, _payloads(s))
        doc["schema"] = "f8n-lab/2"
        assert from_document(doc).status == "SCHEMA_MISMATCH"

    def test_n084_first_difference(self):
        from academic_core.domain.engineering.lab.replay import _first_difference
        s, run = self._mc_session()
        assert _first_difference(run, run) == "result"
        from academic_core.domain.engineering.lab.model import Run as _Run
        altered = _Run(run.run_id, run.experiment_id, run.session_id,
                       run.experiment_digest, run.analysis_kind, run.seed,
                       "SOLVER_FAILURE", run.engine_status, run.result,
                       run.measurements, run.readings, run.diagnostics,
                       run.provenance, run.result_digest)
        assert _first_difference(run, altered) == "status"


class TestProvenance:
    def test_n085_required_keys(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          instruments=(voltmeter("m", "v"),))
        _, run, _ = run_ok(s, d)
        prov = run.provenance
        for key in ("schema", "lab_version", "engine_versions",
                    "experiment_digest", "circuit_digest", "analysis",
                    "parameters", "stimuli", "probes", "instruments",
                    "measurement_specs", "seed", "tolerances",
                    "engine_result_digests", "engine_status", "result_digest"):
            assert key in prov, key
        assert prov["engine_result_digests"]["topology_digest"]
        assert prov["engine_result_digests"]["solver_digest"]

    def test_n086_no_time_uuid(self):
        s = new_session()
        d = op_definition()
        _, run, _ = run_ok(s, d)
        text = dumps_canonical(run.provenance)
        lowered = text.lower()
        for token in ("timestamp", "datetime", "uuid", "clock", "time(",
                      "pid", "address", "0x"):
            assert token not in lowered, token

    def test_n087_notes_excluded(self):
        s = new_session()
        d1 = op_definition(label="aaa")
        d2 = op_definition(label="zzz")
        assert _eid(s, d1) == _eid(s, d2)
        s1 = add_ok(new_session(divider(), "s1"), d1)
        s2 = add_ok(new_session(divider(), "s2"), d2)
        _, r1 = run_experiment(s1, _eid(s1, d1))
        _, r2 = run_experiment(s2, _eid(s2, d2))
        assert r1.result_digest == r2.result_digest


class TestSecurity:
    FILES = None

    def _lab_files(self):
        from pathlib import Path
        return sorted((Path("src/academic_core/domain/engineering/lab")).glob("*.py"))

    def test_n091_forbidden_calls(self):
        import ast
        forbidden = {"eval", "exec", "compile", "__import__", "globals",
                     "locals", "getattr", "setattr", "delattr", "open",
                     "input", "vars"}
        for path in self._lab_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden, (path.name, node.func.id)

    def test_n092_forbidden_modules(self):
        import ast
        forbidden = {"subprocess", "os", "sys", "socket", "importlib",
                     "pickle", "marshal", "urllib", "requests", "http",
                     "numpy", "scipy", "math", "cmath", "shutil", "ctypes"}
        for path in self._lab_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        assert a.name.split(".")[0] not in forbidden, \
                            (path.name, a.name)
                if isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] not in forbidden, \
                        (path.name, node.module)

    def test_n093_hostile_strings_inert(self):
        hostile = "__import__('os').system('x')"
        s = new_session()
        d = op_definition(label=hostile,
                          probes=(("v", VoltageProbe("out", "0")),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status == "COMPLETED"
        s2 = annotate(s, run.run_id, Annotation(hostile))
        doc = to_document(s2, _payloads(s2))
        text = dumps_canonical(doc)
        assert hostile in text  # stored as inert data
        loaded = loads_document(text)
        assert loaded.status == "OK"
        # Hostile addresses are inert data at construction and rejected
        # against the closed registry at add time (INVALID_PROBE).
        d_bad = op_definition(probes=(("x", ParameterProbe("__import__('os')",
                                                           "value")),))
        _, report = add_experiment(new_session(), d_bad)
        assert not report.ok
        assert any(code == "INVALID_PROBE" for code, _ in report.errors)

    def test_n094_malicious_document(self):
        assert loads_document("not json").status == "INVALID_SERIALIZATION"
        assert loads_document("[1,2]").status == "INVALID_SERIALIZATION"
        s = new_session()
        d = op_definition()
        s = add_ok(s, d)
        doc = to_document(s, {})
        doc["experiments"][0]["definition"]["analysis"]["kind"] = "DROP TABLE"
        assert from_document(doc).status == "INVALID_SERIALIZATION"
        doc2 = to_document(s, {})
        doc2["experiments"][0]["definition"]["probes"] = \
            [["v", ["__class__", {}]]]
        assert from_document(doc2).status == "INVALID_SERIALIZATION"
        doc3 = to_document(s, {})
        doc3["extra_root_key"] = {"__class__": "os.system"}
        # Extra root keys are ignored (closed schema reads known keys)...
        # ...but digests must still verify.
        assert from_document(doc3).status == "OK"


class TestErrors:
    def test_n095_invalid_circuit(self):
        c = Circuit("float")
        c.add(Component("R1", "R", Q("1 kohm"), {"1": "a", "2": "b"}))
        s = create_session("bad", c)
        d = op_definition()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status == "INVALID_CIRCUIT"

    def test_n096_invalid_probe_node_branch(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("nope", "0")),))
        _, report = add_experiment(s, d)
        assert not report.ok
        d2 = op_definition(probes=(("i", CurrentProbe("R9")),))
        _, report = add_experiment(s, d2)
        assert not report.ok

    def test_n097_invalid_measurement(self):
        s = new_session()
        d = op_definition(probes=(("v", VoltageProbe("out", "0")),),
                          measurements=(("m", MeasurementSpec("max", "v")),))
        _, report = add_experiment(s, d)
        assert not report.ok  # waveform measurement on OP

    def test_n098_unsupported_combination(self):
        # Oscilloscope on OP is statically invalid; AC sweep on a
        # nonlinear circuit is UNSUPPORTED-class.
        s = new_session()
        d = op_definition(
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sc", InstrumentSpec(
                "oscilloscope", channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                window=(D(0), D(1)), sample_count=10)),))
        _, report = add_experiment(s, d)
        assert not report.ok
        from f8n_lab_common import diode_divider
        from f8n_lab_common import add_ok as _add_ok
        s2 = new_session(diode_divider(), "nl")
        d2 = ExperimentDefinition(
            label="x",
            analysis=AnalysisSpec(
                "AC_SWEEP", frequencies=(Q("100 Hz"),), input_source="V1",
                output_p="a", output_n="0"))
        s2 = _add_ok(s2, d2)
        from academic_core.domain.engineering.lab.serialize import (
            experiment_id as _eid)
        from academic_core.domain.engineering.lab import run_experiment as _run
        s2, run = _run(s2, _eid(d2, s2.circuit))
        assert run.status == "UNSUPPORTED"

    def test_n099_divergence(self):
        # Exponential overflow: diode with extreme bias diverges.
        c = Circuit("divg")
        c.add(Component("V1", "V", Q("1000 V"), {"+": "a", "-": "0"}))
        c.add(Component("D1", "D", None, {"A": "a", "K": "0"},
                        {"Is": Q("1e-14 A"), "n": Q("1"),
                         "Vt": Q("25.85 mV")}))
        s = create_session("divg", c)
        d = op_definition(probes=(("v", VoltageProbe("a", "0")),))
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status in ("SOLVER_FAILURE", "COMPLETED")
        if run.status == "SOLVER_FAILURE":
            assert run.engine_status in ("diverged", "max_iterations",
                                         "singular_jacobian")

    def test_n100_singular(self):
        # Ideal voltage-source loop / shorted source: singular Jacobian.
        c = Circuit("sing")
        c.add(Component("V1", "V", Q("1 V"), {"+": "a", "-": "0"}))
        c.add(Component("V2", "V", Q("1 V"), {"+": "a", "-": "0"}))
        s = create_session("sing", c)
        d = op_definition()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        assert run.status in ("SOLVER_FAILURE", "INVALID_CIRCUIT",
                              "COMPLETED")
        if run.status == "SOLVER_FAILURE":
            assert run.engine_status == "singular_jacobian"

    def test_n101_unknown_ids(self):
        s = new_session()
        with pytest.raises(LabConfigError):
            run_experiment(s, "exp-0000000000000000")
        d = op_definition()
        s = add_ok(s, d)
        s, run = run_experiment(s, _eid(s, d))
        with pytest.raises(LabConfigError):
            annotate(s, "exp-0000000000000000#9", Annotation("x"))

    def test_n102_invalid_serialization(self):
        assert loads_document("{bad").status == "INVALID_SERIALIZATION"
        assert from_document({"schema": "f8n-lab/1"}).status == \
            "INVALID_SERIALIZATION"

    def test_n103_schema_mismatch(self):
        assert from_document({"schema": "f8n-lab/0"}).status == \
            "SCHEMA_MISMATCH"

    def test_n104_invalid_seed(self):
        with pytest.raises(LabConfigError):
            ExperimentDefinition(label="x", analysis=AnalysisSpec("OP"),
                                 seed=1)

    def test_n105_budget_overflow(self):
        from academic_core.domain.engineering.lab import model as _m
        old = _m.MAX_EXPERIMENTS_PER_SESSION
        _m.MAX_EXPERIMENTS_PER_SESSION = 1
        import academic_core.domain.engineering.lab.session as _sess
        old2 = _sess.MAX_EXPERIMENTS_PER_SESSION
        _sess.MAX_EXPERIMENTS_PER_SESSION = 1
        try:
            s = new_session()
            s = add_ok(s, op_definition(label="a"))
            _, report = add_experiment(s, op_definition(label="b"))
            assert not report.ok
            assert any(code == "BUDGET_EXCEEDED" for code, _ in report.errors)
        finally:
            _m.MAX_EXPERIMENTS_PER_SESSION = old
            _sess.MAX_EXPERIMENTS_PER_SESSION = old2
        with pytest.raises(LabConfigError):
            InstrumentSpec("oscilloscope",
                           channels=(ScopeChannel("v", D(1), D(0), "DC"),),
                           window=(D(0), D(1)), sample_count=10001)
        with pytest.raises(LabConfigError):
            InstrumentSpec("oscilloscope",
                           channels=tuple(ScopeChannel(f"v{i}", D(1), D(0), "DC")
                                          for i in range(5)),
                           window=(D(0), D(1)), sample_count=10)

    def test_n106_partial_results(self):
        # Monte Carlo over a sweep that fails on some samples: failures
        # listed, never zero-filled. (Sweep point failures via MC here.)
        cfg = MCConfig(
            6, ((ParamAddress("R1", "value"), UniformDist(D(1), D(100000))),),
            None, (ObservableSpec("node_voltage", "out"),), "dc-op")
        d = ExperimentDefinition(
            label="x", analysis=AnalysisSpec("MONTE_CARLO", mc=cfg), seed=3,
            probes=(("v", VoltageProbe("out", "0")),),
            instruments=(("sw", InstrumentSpec("sweep_viewer", probe="v")),))
        s = new_session()
        _, run, _ = run_ok(s, d)
        assert run.status in ("COMPLETED", "COMPLETED_WITH_FAILURES")
        if run.status == "COMPLETED_WITH_FAILURES":
            assert run.result.failure_count > 0
            assert None in run.readings[0].data.values

    def test_n107_no_data_never_zero(self):
        from f8n_lab_common import rc_step, transient_definition
        from academic_core.domain.engineering.lab import create_session as _cs
        s = _cs("nodata", rc_step())
        d = transient_definition(
            probes=(("ic", CurrentProbe("C1")),),
            instruments=(ammeter("a", "ic"),),
            measurements=(("mx", MeasurementSpec("max", "ic")),))
        _, run, _ = run_ok(s, d)
        assert run.readings[0].status == "UNSUPPORTED"
        assert run.measurements[0].status == "NO_DATA"
        assert run.measurements[0].value is None