"""F8-Q.4 DigitalTrace serialization (``digital-trace/1``) + replay + determinism.

Sections: schema / canonical form / Decimal policy / strict decoding /
limits / security / digest / replay / determinism (incl. separate
processes) / golden fixtures / properties.
Deterministic generation only (LCG, no RNG module, no hypothesis).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.digital import (
    DIGITAL_TRACE_FORMAT,
    DIGITAL_TRACE_SCHEMA,
    DIGITAL_TRACE_VERSION,
    MAX_EVENTS,
    MAX_PROBES,
    MAX_TRACE_CHANNELS,
    MAX_TRACE_DEPTH,
    MAX_TRACE_ITEMS,
    MAX_TRACE_JSON_BYTES,
    MAX_TRACE_NOOPS,
    MAX_TRACE_SAMPLES,
    MAX_TRACE_STRING,
    TRACE_CANONICAL_VERSION,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    DigitalSimulator,
    DigitalTrace,
    GateKind,
    LogicState,
    PatternStimulus,
    PulseStimulus,
    ToggleStimulus,
    TraceChannel,
    TraceSample,
    canonical_time,
    replay_trace,
    verify_replay,
)
from academic_core.domain.engineering.digital import replay as replay_mod
from academic_core.errors import IntegrationError, SerializationError, ValidationError, VersionMismatchError

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
DIGITAL_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "digital"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "digital_trace"


# =============================================================== builders

def _sim_trace(circuit):
    sim = DigitalSimulator(circuit)
    sim.run()
    return sim.trace()


def build_empty():
    """No probes: a window and no channels."""
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(PulseStimulus("pA", "A", D("0.5"), D("0.25")))
    return _sim_trace(c)


def build_one_channel():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("tA", "A", H, D("0.1"), D("0.25"), 4))
    c.add_probe(DigitalProbe("a", "A"))
    return _sim_trace(c)


def build_multi_channel():
    c = DigitalCircuit()
    for x in ("A", "B", "Y", "Z"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("and1", GateKind.AND, ("A", "B"), "Y"))
    c.add_component(DigitalComponent("nor1", GateKind.NOR, ("A", "B"), "Z"))
    c.add_stimulus(ToggleStimulus("tA", "A", H, D(0), D(1), 4))
    c.add_stimulus(ToggleStimulus("tB", "B", H, D("0.5"), D(2), 2))
    for p, net in (("ch_a", "A"), ("ch_b", "B"), ("ch_y", "Y"), ("ch_z", "Z")):
        c.add_probe(DigitalProbe(p, net))
    return _sim_trace(c)


def build_same_timestamp():
    """XOR(A,B,C) with all inputs rising at t=1: Y goes HIGH, LOW, HIGH at t=1."""
    c = DigitalCircuit()
    for x in ("A", "B", "C", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x3", GateKind.XOR, ("A", "B", "C"), "Y"))
    for sid, net in (("sA", "A"), ("sB", "B"), ("sC", "C")):
        c.add_stimulus(PatternStimulus(sid, net, D(1), D(1), (H,)))
    c.add_probe(DigitalProbe("y", "Y"))
    return _sim_trace(c)


def build_noop():
    c = DigitalCircuit()
    c.add_net("A", H)
    c.add_stimulus(PatternStimulus("p", "A", D(0), D(1), (H, H, L, L, L, H)))
    c.add_probe(DigitalProbe("a", "A"))
    return _sim_trace(c)


def build_repeated_probe_net():
    """Several probes on one net, a gate reading one net on repeated pins."""
    c = DigitalCircuit()
    for x in ("A", "B", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x", GateKind.XOR, ("A", "A", "B"), "Y"))  # = B
    c.add_stimulus(ToggleStimulus("tA", "A", H, D(0), D("0.5"), 3))
    c.add_stimulus(PatternStimulus("pB", "B", D("0.25"), D("0.5"), (H, H, L)))
    for p in ("y_1", "y_2", "y_3"):
        c.add_probe(DigitalProbe(p, "Y"))
    c.add_probe(DigitalProbe("a", "A"))
    return _sim_trace(c)


def build_mixed():
    c = DigitalCircuit()
    for x in ("A", "B", "C", "D", "P", "Q", "R", "S", "T"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("g1", GateKind.NAND, ("A", "B", "A"), "P"))
    c.add_component(DigitalComponent("g2", GateKind.XNOR, ("P", "C", "D", "C"), "Q"))
    c.add_component(DigitalComponent("g3", GateKind.NOR, ("Q", "A", "D"), "R"))
    c.add_component(DigitalComponent("g4", GateKind.XOR, ("P", "Q", "R", "B", "B", "C", "D", "A"), "S"))
    c.add_component(DigitalComponent("g5", GateKind.NOT, ("S",), "T"))
    c.add_stimulus(ToggleStimulus("tA", "A", H, D(0), D("0.5"), 9))
    c.add_stimulus(PatternStimulus("pB", "B", D(0), D("0.5"), (H, H, L, H, L, L, H, L, H)))
    c.add_stimulus(ToggleStimulus("tC", "C", H, D(0), D("1.0"), 5))
    c.add_stimulus(PatternStimulus("pD", "D", D("0.5"), D("1.0"), (H, L, H, H)))
    for p, net in (("ch_P", "P"), ("ch_S", "S"), ("ch_T", "T"), ("ch_A", "A"), ("ch_A2", "A")):
        c.add_probe(DigitalProbe(p, net))
    return _sim_trace(c)


GOLDEN = {
    "empty": build_empty,
    "one_channel": build_one_channel,
    "multi_channel": build_multi_channel,
    "same_timestamp": build_same_timestamp,
    "noop_count": build_noop,
    "repeated_probe_net": build_repeated_probe_net,
}

# SHA-256 of each fixture's canonical bytes: pins the digital-trace/1 contract.
GOLDEN_DIGESTS = {
    "empty": "5deef8f46e0a605cac627023c850f2f935adce99d4c5b6985121cbfca3d25fa4",
    "one_channel": "bc9a4019eebdbeee1a2c19cfbd89f464fbc855b573ea96d022a8c73acd57008b",
    "multi_channel": "ac1d2db083af25fa50d1377db974e6326ff4348335e08ae1e2d013f4e2dd3780",
    "same_timestamp": "2f980d9e7f67aa227884f09b816f15076ab23c798d5a240124548a8c3cf0f66f",
    "noop_count": "d98003e0aa278c3924dcd1f3b217d4ef7c179e1b0c8888155a964b226487d5a4",
    "repeated_probe_net": "f75764d4916bc912dc89f2acde00117328f2aa2219de9797ce1694545cd63e0c",
}


def _ch(probe_id, net_id, initial, samples, noops=0):
    return TraceChannel(probe_id, net_id, initial,
                        tuple(TraceSample(D(t) if isinstance(t, str) else t, k, s)
                              for k, (t, s) in enumerate(samples)), noops)


def _doc(**over):
    """A valid one-channel document; ``over`` replaces top-level fields."""
    doc = {
        "schema": "digital-trace",
        "version": 1,
        "window": {"start_time": "0", "end_time": "2"},
        "channels": [{"probe_id": "a", "net_id": "A", "initial_state": "LOW",
                      "samples": [{"time": "0.5", "state": "HIGH"}, {"time": "1", "state": "LOW"}],
                      "no_op_count": 3}],
    }
    doc.update(over)
    return doc


def _with_channel(**over):
    doc = _doc()
    doc["channels"][0].update(over)
    return doc


def _with_sample(index=0, **over):
    doc = _doc()
    doc["channels"][0]["samples"][index].update(over)
    return doc


def _walk(node):
    yield node
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _lcg(seed):
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        yield state >> 33


# =============================================================== schema + canonical form

def test_q4_s01_contract_constants():
    assert DIGITAL_TRACE_SCHEMA == "digital-trace" and DIGITAL_TRACE_VERSION == 1
    assert DIGITAL_TRACE_FORMAT == "digital-trace/1"
    assert MAX_TRACE_CHANNELS == MAX_PROBES == 32
    assert MAX_TRACE_NOOPS == MAX_EVENTS
    assert MAX_TRACE_DEPTH == 5 and MAX_TRACE_STRING == 128
    assert MAX_TRACE_SAMPLES == 200_000 and MAX_TRACE_ITEMS == 1_000_000
    assert MAX_TRACE_JSON_BYTES == 16 * 1024 * 1024


def test_q4_s02_to_dict_structure():
    d = build_multi_channel().to_dict()
    assert set(d) == {"schema", "version", "window", "channels"}
    assert d["schema"] == "digital-trace" and d["version"] == 1
    assert set(d["window"]) == {"start_time", "end_time"}
    for ch in d["channels"]:
        assert set(ch) == {"probe_id", "net_id", "initial_state", "samples", "no_op_count"}
        for s in ch["samples"]:
            assert set(s) == {"time", "state"}
    assert [c["probe_id"] for c in d["channels"]] == ["ch_a", "ch_b", "ch_y", "ch_z"]
    # JSON data model only: no float / Decimal / LogicState / tuple / None / bool
    for node in _walk(d):
        assert type(node) in (dict, list, str, int), type(node)


def test_q4_s03_canonical_json_rules():
    tr = build_multi_channel()
    text = tr.to_json()
    assert text == tr.canonical_json()
    assert text == json.dumps(tr.to_dict(), sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False)
    assert " " not in text and "\n" not in text and not text.endswith("\n")
    assert text.isascii() and "\\" not in text  # nothing needs escaping
    assert text.startswith('{"channels":[{"initial_state":"LOW","net_id":"A","no_op_count":0,'
                           '"probe_id":"ch_a","samples":[{"state":"HIGH","time":"0"}')
    assert text.endswith(',"schema":"digital-trace","version":1,"window":{"end_time":"3","start_time":"0"}}')
    assert tr.canonical_bytes() == text.encode("utf-8")
    assert tr.digest() == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(tr.digest()) == 64 and tr.digest() == tr.digest().lower()


def test_q4_s04_empty_trace_document():
    tr = build_empty()
    assert tr.channels == () and tr.end == D("0.75")
    assert tr.to_json() == ('{"channels":[],"schema":"digital-trace","version":1,'
                            '"window":{"end_time":"0.75","start_time":"0"}}')
    assert DigitalTrace.from_json(tr.to_json()) == tr
    assert verify_replay(tr) == tr


def test_q4_s05_legacy_q3r_canonical_is_kept_but_not_hashed():
    tr = build_one_channel()
    assert tr.canonical().startswith(TRACE_CANONICAL_VERSION + "\n")
    assert tr.digest() != hashlib.sha256(tr.canonical().encode("utf-8")).hexdigest()
    assert tr.digest() == hashlib.sha256(tr.canonical_bytes()).hexdigest()


# =============================================================== Decimal policy

@pytest.mark.parametrize("raw, text", [
    ("0", "0"), ("0.000", "0"), ("-0", "0"), ("0E+3", "0"), ("0E-9", "0"),
    ("1", "1"), ("1.0", "1"), ("1.00", "1"), ("1E+0", "1"), ("10E-1", "1"), ("0.1E+1", "1"),
    ("100", "100"), ("1E+2", "100"), ("100.00", "100"), ("3600", "3600"), ("3.6E+3", "3600"),
    ("0.5", "0.5"), ("0.50", "0.5"), ("5E-1", "0.5"), ("0.00100", "0.001"), ("1E-5", "0.00001"),
    ("12.3400", "12.34"), ("1.000000000000000000000000000000000001", "1.000000000000000000000000000000000001"),
])
def test_q4_d01_canonical_time(raw, text):
    assert canonical_time(D(raw)) == text
    assert D(text) == D(raw)  # exact: never through float


def test_q4_d02_equivalent_decimals_one_representation():
    forms = [1, D(1), D("1.0"), D("1.00"), D("1E+0"), D("10E-1"), D("0.1E+1")]
    traces = [DigitalTrace(D("0.0"), D("2.000"), (_ch("a", "A", L, [(t, H)]),)) for t in forms]
    assert len({t.to_json() for t in traces}) == 1
    assert len({t.digest() for t in traces}) == 1
    assert all(t == traces[0] for t in traces)  # Decimal equality, as Q1
    assert '"time":"1"' in traces[0].to_json() and '"start_time":"0"' in traces[0].to_json()
    back = DigitalTrace.from_json(traces[3].to_json())
    assert back.channels[0].samples[0].time == D(1) and str(back.channels[0].samples[0].time) == "1"


def test_q4_d03_high_precision_exact_and_bounded():
    t = D("0." + "0" * 60 + "1")
    assert canonical_time(t) == "0." + "0" * 60 + "1"
    tr = DigitalTrace(D(0), D(1), (_ch("a", "A", L, [(t, H)]),))
    back = DigitalTrace.from_json(tr.to_json())
    assert back.channels[0].samples[0].time == t
    for huge in (D("1E-200"), D("1." + "1" * 200)):
        with pytest.raises(ValidationError, match="TRACE_LIMIT"):
            canonical_time(huge)
    with pytest.raises(ValidationError, match="INVALID_TIME"):
        canonical_time(1.0)  # float never accepted


@pytest.mark.parametrize("bad", ["1.0", "1.50", "01", "00", "0.0", ".5", "1.", "+1", "-1", " 1", "1 ",
                                 "1e0", "1E+2", "0x10", "NaN", "Infinity", "-0", "", "1_000", "١"])
def test_q4_d04_non_canonical_time_text_rejected(bad):
    with pytest.raises(ValidationError, match="INVALID_TIME"):
        DigitalTrace.from_dict(_with_sample(0, time=bad))


def test_q4_d05_time_bounds_and_types():
    with pytest.raises(ValidationError, match="TIME_LIMIT"):
        DigitalTrace.from_dict(_doc(window={"start_time": "0", "end_time": "3600.5"}))
    for bad in (1, 0, None, True, ["1"], {"t": "1"}):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(_with_sample(0, time=bad))
    with pytest.raises(SerializationError, match="INVALID_JSON"):  # JSON number with fraction = float
        DigitalTrace.from_json(json.dumps(_doc()).replace('"0.5"', "0.5"))


# =============================================================== states

@pytest.mark.parametrize("bad", [None, 0, 1, True, False, "low", "high", "Low", "X", "Z", "x", "z",
                                 "H", "L", "0", "1", "LOW ", ["LOW"], {"LOW": 1}, "LogicState.LOW"])
def test_q4_l01_invalid_state(bad):
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        DigitalTrace.from_dict(_with_sample(0, state=bad))
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        DigitalTrace.from_dict(_with_channel(initial_state=bad))


def test_q4_l02_python_level_states_still_strict():
    for bad in (None, 0, 1, "LOW", "X", "Z"):
        with pytest.raises(ValidationError, match="INVALID_STATE"):
            TraceSample(D(1), 0, bad)
        with pytest.raises(ValidationError, match="INVALID_STATE"):
            TraceChannel("a", "A", bad, ())


# =============================================================== strict decoding

@pytest.mark.parametrize("schema", ["digital-trace/1", "digital-trace-internal/0", "Digital-Trace",
                                    "f8n-lab/1", "", None, 1, ["digital-trace"]])
def test_q4_v01_invalid_schema(schema):
    with pytest.raises(ValidationError, match="INVALID_SCHEMA"):
        DigitalTrace.from_dict(_doc(schema=schema))
    doc = _doc()
    del doc["schema"]
    with pytest.raises(ValidationError, match="INVALID_SCHEMA"):
        DigitalTrace.from_dict(doc)


@pytest.mark.parametrize("version", [0, 2, -1, 10**6, "1", True, 1.0, None, [1]])
def test_q4_v02_unknown_version(version):
    with pytest.raises(VersionMismatchError, match="UNSUPPORTED_VERSION") as info:
        DigitalTrace.from_dict(_doc(version=version))
    assert info.value.code == "AC-VER-001"


def test_q4_v03_missing_fields_every_level():
    for key in ("window", "channels"):
        doc = _doc()
        del doc[key]
        with pytest.raises(ValidationError, match="INVALID_TRACE: document missing"):
            DigitalTrace.from_dict(doc)
    for key in ("start_time", "end_time"):
        doc = _doc()
        del doc["window"][key]
        with pytest.raises(ValidationError, match="window missing"):
            DigitalTrace.from_dict(doc)
    for key in ("probe_id", "net_id", "initial_state", "samples", "no_op_count"):
        doc = _doc()
        del doc["channels"][0][key]
        with pytest.raises(ValidationError, match=r"channels\[0\] missing"):
            DigitalTrace.from_dict(doc)
    for key in ("time", "state"):
        doc = _doc()
        del doc["channels"][0]["samples"][1][key]
        with pytest.raises(ValidationError, match=r"samples\[1\] missing"):
            DigitalTrace.from_dict(doc)


def test_q4_v04_extra_fields_rejected_every_level():
    for where in ((), ("window",), ("channels", 0), ("channels", 0, "samples", 0)):
        for extra in ("sequence", "channel_id", "__class__", "comment"):
            doc = _doc()
            node = doc
            for step in where:
                node = node[step]
            node[extra] = 1
            with pytest.raises(ValidationError, match="unknown field"):
                DigitalTrace.from_dict(doc)


def test_q4_v05_wrong_container_types():
    for bad in ([], "x", 1, None, ((),)):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(bad)
    for bad in ([], "0", None, [["start_time", "0"]]):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(_doc(window=bad))
    for bad in ({}, "a", None, ({"probe_id": "a"},)):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(_doc(channels=bad))
    for bad in ({}, "s", None, 1, ({"time": "1", "state": "HIGH"},)):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(_with_channel(samples=bad))
    for bad in ("3", 3.0, None, True, -1, [3]):
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(_with_channel(no_op_count=bad))


@pytest.mark.parametrize("bad", ["", "1abc", "a b", "a/b", "aé", "a" * 65, "-a", "a\n", "ü"])
def test_q4_v06_invalid_ids(bad):
    for field in ("probe_id", "net_id"):
        with pytest.raises(ValidationError, match="INVALID_ID"):
            DigitalTrace.from_dict(_with_channel(**{field: bad}))
    for field in ("probe_id", "net_id"):
        for wrong in (1, None, ["a"], True):
            with pytest.raises(ValidationError, match="INVALID_TRACE"):
                DigitalTrace.from_dict(_with_channel(**{field: wrong}))


def test_q4_v07_duplicate_and_unsorted_channels():
    doc = _doc()
    doc["channels"].append(copy.deepcopy(doc["channels"][0]))
    with pytest.raises(ValidationError, match="DUPLICATE_PROBE"):
        DigitalTrace.from_dict(doc)
    doc = _doc()
    second = copy.deepcopy(doc["channels"][0])
    second["probe_id"] = "Z_before_a"  # uppercase sorts before lowercase: order is plain code-point order
    doc["channels"].append(second)
    with pytest.raises(ValidationError, match="sorted by probe_id"):
        DigitalTrace.from_dict(doc)
    doc["channels"].reverse()
    tr = DigitalTrace.from_dict(doc)
    assert [c.probe_id for c in tr.channels] == ["Z_before_a", "a"]


def test_q4_v08_impossible_samples():
    cases = [
        _with_channel(initial_state="HIGH"),  # first sample HIGH is no transition
        _with_sample(1, state="HIGH"),  # HIGH -> HIGH
        _with_sample(1, time="0.25"),  # time goes backwards
        _with_sample(1, time="2.5"),  # after window end
        _doc(window={"start_time": "0.75", "end_time": "2"}),  # sample before window start
        _doc(window={"start_time": "2", "end_time": "1"}),  # inverted window
    ]
    for doc in cases:
        with pytest.raises(ValidationError, match="INVALID_TRACE"):
            DigitalTrace.from_dict(doc)


def test_q4_v09_same_net_channels_must_agree():
    doc = _doc()
    other = copy.deepcopy(doc["channels"][0])
    other["probe_id"] = "b"
    doc["channels"].append(other)
    assert len(DigitalTrace.from_dict(doc).channels) == 2  # identical content: fine
    for field, value in (("no_op_count", 4), ("initial_state", "HIGH"),
                         ("samples", [{"time": "0.5", "state": "HIGH"}])):
        bad = copy.deepcopy(doc)
        bad["channels"][1][field] = value
        if field == "initial_state":
            bad["channels"][1]["samples"] = [{"time": "1", "state": "LOW"}]
        with pytest.raises(ValidationError, match="disagree"):
            DigitalTrace.from_dict(bad)
    with pytest.raises(ValidationError, match="disagree"):  # the invariant lives in the model
        DigitalTrace(D(0), D(1), (_ch("a", "N", L, []), _ch("b", "N", H, [])))


def test_q4_v10_json_layer_strictness():
    good = json.dumps(_doc())
    assert DigitalTrace.from_json(good) == DigitalTrace.from_json(good.encode("utf-8"))
    assert DigitalTrace.from_json(json.dumps(_doc(), indent=2)) == DigitalTrace.from_json(good)  # any JSON layout
    bad_inputs = [
        good[:-1],  # truncated
        good + "x",
        good.replace('"version": 1', '"version": 1, "version": 1'),  # duplicate key
        good.replace('"no_op_count": 3', '"no_op_count": NaN'),
        good.replace('"no_op_count": 3', '"no_op_count": Infinity'),
        good.replace('"no_op_count": 3', '"no_op_count": -Infinity'),
        good.replace('"no_op_count": 3', '"no_op_count": 3.0'),
        good.replace('"no_op_count": 3', '"no_op_count": 3e0'),
        good.replace('"no_op_count": 3', '"no_op_count": ' + "9" * 21),
        "﻿" + good,  # BOM
        "",
        "{'schema': 'digital-trace'}",  # Python literal, not JSON
    ]
    for text in bad_inputs:
        with pytest.raises(SerializationError) as info:
            DigitalTrace.from_json(text)
        assert info.value.code == "AC-SER-001"
    for raw in (b"\xff\xfe{}", b'{"schema":"\xc3"}'):
        with pytest.raises(SerializationError, match="UTF-8"):
            DigitalTrace.from_json(raw)
    for wrong in (None, 1, {"schema": "digital-trace"}, ["{}"]):
        with pytest.raises(SerializationError, match="expected str or bytes"):
            DigitalTrace.from_json(wrong)


# =============================================================== limits

def test_q4_m01_byte_limit():
    text = '{"schema":"' + "a" * MAX_TRACE_JSON_BYTES + '"}'
    for payload in (text, text.encode("ascii"), bytearray(text.encode("ascii"))):
        with pytest.raises(SerializationError, match="TRACE_LIMIT"):
            DigitalTrace.from_json(payload)
    multibyte = "é" * (MAX_TRACE_JSON_BYTES // 2 + 1)  # few characters, too many bytes
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        DigitalTrace.from_json(multibyte)


def test_q4_m02_depth_limit():
    for text in ("[" * 100_000, "{\"a\":" * 50_000, '{"a":[[[[[1]]]]]}', '[[[[[[]]]]]]'):
        with pytest.raises(SerializationError, match="TRACE_LIMIT"):
            DigitalTrace.from_json(text)
    # brackets inside strings are data, not nesting
    doc = _doc(schema="[[[[[[[[[[")
    with pytest.raises(ValidationError, match="INVALID_SCHEMA"):
        DigitalTrace.from_json(json.dumps(doc))


def test_q4_m03_item_limit():
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        DigitalTrace.from_json("[" + "0," * MAX_TRACE_ITEMS + "0]")


def test_q4_m04_channel_and_sample_limits():
    doc = _doc()
    base = doc["channels"][0]
    doc["channels"] = [dict(copy.deepcopy(base), probe_id=f"p{k:02d}") for k in range(MAX_TRACE_CHANNELS + 1)]
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        DigitalTrace.from_dict(doc)
    many = [{"time": "1", "state": "HIGH" if k % 2 == 0 else "LOW"} for k in range(MAX_TRACE_SAMPLES + 1)]
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        DigitalTrace.from_dict(_with_channel(samples=many))
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        DigitalTrace.from_dict(_with_channel(no_op_count=MAX_TRACE_NOOPS + 1))
    assert DigitalTrace.from_dict(_with_channel(no_op_count=MAX_TRACE_NOOPS)).channels[0].noop_count == MAX_EVENTS
    for field in ("probe_id", "net_id"):
        with pytest.raises(ValidationError, match="TRACE_LIMIT"):
            DigitalTrace.from_dict(_with_channel(**{field: "a" * (MAX_TRACE_STRING + 1)}))
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        DigitalTrace.from_dict(_with_sample(0, time="0." + "1" * MAX_TRACE_STRING))


def test_q4_m05_encoder_refuses_what_decoder_refuses():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.0001"), 7000))
    for k in range(MAX_PROBES):
        c.add_probe(DigitalProbe(f"p{k:02d}", "A"))  # 32 x 7000 = 224 000 samples
    tr = _sim_trace(c)
    assert tr.transition_count > MAX_TRACE_SAMPLES
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        tr.to_json()
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        tr.digest()
    replayed = replay_trace(tr)  # replay itself is not bound by the wire limits
    assert replayed == tr
    big_noops = DigitalTrace(D(0), D(1), (_ch("a", "A", L, [], MAX_TRACE_NOOPS + 1),))
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        big_noops.to_dict()


def test_q4_m06_largest_simulated_trace_round_trips():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.0001"), 6000))
    for k in range(MAX_PROBES):
        c.add_probe(DigitalProbe(f"p{k:02d}", "A"))  # 192 000 samples
    tr = _sim_trace(c)
    text = tr.to_json()
    assert len(text) < MAX_TRACE_JSON_BYTES
    back = DigitalTrace.from_json(text)
    assert back == tr and back.digest() == tr.digest()


# =============================================================== security

def test_q4_x01_malicious_payloads_are_only_data(monkeypatch):
    import builtins

    calls = []
    for name in ("eval", "exec", "compile"):
        original = getattr(builtins, name)
        monkeypatch.setattr(builtins, name, lambda *a, _n=name, _o=original, **k: (calls.append(_n), _o(*a, **k))[1])
    payloads = [
        _with_channel(probe_id="__import__('os').system('echo pwned')"),
        _with_channel(net_id="eval(1)"),
        _with_sample(0, state="__import__('os')"),
        _with_sample(0, time="__import__('os')"),
        _doc(schema="!!python/object/apply:os.system"),
        _doc(**{"__class__": "DigitalTrace"}),
        _with_channel(**{"__reduce__": ["os.system", ["id"]]}),
        _doc(channels=[{"py/object": "academic_core.errors.IntegrationError"}]),
    ]
    for doc in payloads:
        with pytest.raises((ValidationError, VersionMismatchError)):
            DigitalTrace.from_json(json.dumps(doc))
    for raw in (b"\x80\x04\x95\x10\x00\x00\x00", b"cos\nsystem\n(S'id'\ntR."):  # pickle streams
        with pytest.raises(SerializationError):
            DigitalTrace.from_json(raw)
    assert calls == []


def test_q4_x02_codec_and_replay_source_policy():
    banned_calls = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "globals", "locals",
                    "vars", "open", "print", "id", "hash", "input", "breakpoint"}
    banned_modules = {"pickle", "marshal", "shelve", "importlib", "subprocess", "os", "sys", "io",
                      "pathlib", "time", "datetime", "random", "uuid", "yaml", "copyreg"}
    for name in ("serialization.py", "replay.py", "trace.py"):
        tree = ast.parse((DIGITAL_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (name, node.func.id)
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_modules, name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned_modules, name


def test_q4_x03_error_codes_are_d2():
    probes = [
        (lambda: DigitalTrace.from_json("{"), SerializationError, "AC-SER-001"),
        (lambda: DigitalTrace.from_dict(_doc(version=9)), VersionMismatchError, "AC-VER-001"),
        (lambda: DigitalTrace.from_dict(_doc(schema="x")), ValidationError, "AC-VAL-001"),
        (lambda: DigitalTrace.from_dict(_with_sample(0, state="X")), ValidationError, "AC-VAL-001"),
    ]
    for fn, cls, code in probes:
        with pytest.raises(cls) as info:
            fn()
        assert info.value.code == code and isinstance(info.value, ValueError)
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        replay_trace("not a trace")


# =============================================================== digest

def test_q4_h01_digest_moves_with_every_observable():
    base = DigitalTrace.from_dict(_doc())
    mutations = [
        lambda d: d["window"].update(end_time="3"),
        lambda d: d["window"].update(start_time="0.25"),
        lambda d: d["channels"][0].update(probe_id="b"),
        lambda d: d["channels"][0].update(net_id="B"),
        lambda d: d["channels"][0].update(no_op_count=4),
        lambda d: d["channels"][0]["samples"][0].update(time="0.75"),
        lambda d: d["channels"][0].update(initial_state="HIGH",
                                          samples=[{"time": "0.5", "state": "LOW"}, {"time": "1", "state": "HIGH"}]),
        lambda d: d["channels"][0]["samples"].pop(),
    ]
    digests = {base.digest()}
    for mutate in mutations:
        doc = _doc()
        mutate(doc)
        digests.add(DigitalTrace.from_dict(doc).digest())
    assert len(digests) == len(mutations) + 1


def test_q4_h02_digest_ignores_runtime_sequence():
    a = DigitalTrace(D(0), D(2), (TraceChannel("a", "A", L, (TraceSample(D(1), 7, H), TraceSample(D(1), 90, L))),))
    b = DigitalTrace(D(0), D(2), (TraceChannel("a", "A", L, (TraceSample(D(1), 0, H), TraceSample(D(1), 1, L))),))
    assert a == b and a.digest() == b.digest() and a.to_json() == b.to_json()
    assert a.channels[0].samples[0].sequence == 7  # kept as metadata
    assert "sequence" not in a.to_json()


# =============================================================== same timestamp + no-op

def test_q4_t01_same_timestamp_high_low_high_preserved():
    tr = build_same_timestamp()
    ch = tr.channel("y")
    assert [(str(s.time), s.state) for s in ch.samples] == [("1", H), ("1", L), ("1", H)]
    assert '"samples":[{"state":"HIGH","time":"1"},{"state":"LOW","time":"1"},{"state":"HIGH","time":"1"}]' \
        in tr.to_json()
    back = DigitalTrace.from_json(tr.to_json())
    assert [(s.time, s.state) for s in back.channel("y").samples] == [(D(1), H), (D(1), L), (D(1), H)]
    assert [s.sequence for s in back.channel("y").samples] == [0, 1, 2]
    replayed = verify_replay(back)
    assert [(s.time, s.state) for s in replayed.channel("y").samples] == [(D(1), H), (D(1), L), (D(1), H)]
    assert replayed.channel("y").state_at(D(1)) is H


def test_q4_t02_same_timestamp_order_is_significant():
    doc = _doc(window={"start_time": "0", "end_time": "1"})
    doc["channels"][0]["samples"] = [{"time": "1", "state": s} for s in ("HIGH", "LOW", "HIGH")]
    tr = DigitalTrace.from_dict(doc)
    doc["channels"][0]["initial_state"] = "HIGH"
    doc["channels"][0]["samples"] = [{"time": "1", "state": s} for s in ("LOW", "HIGH", "LOW")]
    flipped = DigitalTrace.from_dict(doc)
    assert tr != flipped and tr.digest() != flipped.digest()
    doc["channels"][0]["samples"] = [{"time": "1", "state": s} for s in ("LOW", "LOW", "HIGH")]
    with pytest.raises(ValidationError, match="non-transition"):  # no collapsing/reordering on input
        DigitalTrace.from_dict(doc)


def test_q4_n01_noop_count_serialized_and_replayed():
    tr = build_noop()
    ch = tr.channel("a")
    assert ch.noop_count == 4 and [(s.time, s.state) for s in ch.samples] == [(D(2), L), (D(5), H)]
    assert '"no_op_count":4' in tr.to_json()
    back = DigitalTrace.from_json(tr.to_json())
    assert back.channel("a").noop_count == 4
    replayed = verify_replay(back)
    assert replayed.channel("a").noop_count == 4 and replayed == tr


def test_q4_n02_noops_shared_by_same_net_probes():
    tr = DigitalTrace.from_dict({
        "schema": "digital-trace", "version": 1, "window": {"start_time": "0", "end_time": "5"},
        "channels": [{"probe_id": p, "net_id": "N", "initial_state": "HIGH", "no_op_count": 7,
                      "samples": [{"time": "5", "state": "LOW"}]} for p in ("p1", "p2", "p3")]})
    replayed = verify_replay(tr)
    assert [c.noop_count for c in replayed.channels] == [7, 7, 7]


# =============================================================== immutability

def test_q4_i01_decoded_trace_is_immutable():
    tr = DigitalTrace.from_json(json.dumps(_doc()))
    ch, s = tr.channels[0], tr.channels[0].samples[0]
    assert isinstance(tr.channels, tuple) and isinstance(ch.samples, tuple)
    for obj, attr, value in ((tr, "end", D(9)), (tr, "channels", ()), (ch, "probe_id", "z"), (ch, "net_id", "Z"),
                             (ch, "initial", H), (ch, "noop_count", 0), (ch, "samples", ()),
                             (s, "state", L), (s, "time", D(0))):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, value)
    with pytest.raises(TypeError):
        tr.channels[0] = ch  # type: ignore[index]


def test_q4_i02_no_aliasing_with_input_or_output():
    doc = _doc()
    tr = DigitalTrace.from_dict(doc)
    before = tr.to_json()
    doc["channels"][0]["samples"].clear()
    doc["window"]["end_time"] = "9"
    assert tr.to_json() == before
    out = tr.to_dict()
    out["channels"][0]["samples"].append({"time": "2", "state": "HIGH"})
    out["window"]["start_time"] = "1"
    assert tr.to_json() == before and tr.to_dict() != out


# =============================================================== replay

@pytest.mark.parametrize("builder", [*GOLDEN.values(), build_mixed])
def test_q4_r01_full_pipeline(builder):
    """simulation -> trace -> serialize -> deserialize -> replay -> trace'."""
    trace = builder()
    text = trace.to_json()
    decoded = DigitalTrace.from_json(text)
    replayed = replay_trace(decoded)
    assert decoded == trace and replayed == trace
    assert decoded.digest() == replayed.digest() == trace.digest()
    assert replayed.to_json() == text
    assert verify_replay(decoded) == trace


def test_q4_r02_replay_non_zero_window_start():
    tr = DigitalTrace(D("2.5"), D(10), (_ch("a", "A", H, [("2.5", L), ("7", H)], 2),
                                        _ch("b", "B", L, [], 1)))
    replayed = verify_replay(tr)
    assert replayed.start == D("2.5") and replayed.end == D(10)
    assert replayed.channel("b").noop_count == 1 and replayed.channel("a").noop_count == 2


def test_q4_r03_replay_window_without_events():
    tr = DigitalTrace(D(1), D(4), (_ch("a", "A", L, []),))
    assert verify_replay(tr) == tr
    assert verify_replay(DigitalTrace(D(3), D(3), ())) == DigitalTrace(D(3), D(3), ())


def test_q4_r04_verify_replay_detects_mismatch(monkeypatch):
    tr = build_one_channel()
    other = build_noop()
    monkeypatch.setattr(replay_mod, "replay_trace", lambda _t: other)
    with pytest.raises(IntegrationError, match="REPLAY_MISMATCH") as info:
        verify_replay(tr)
    assert info.value.code == "AC-INT-001"


def test_q4_r05_replay_does_not_touch_input():
    tr = build_repeated_probe_net()
    snapshot = tr.to_json()
    replay_trace(tr)
    assert tr.to_json() == snapshot


# =============================================================== determinism

def test_q4_z01_repeated_runs_identical():
    runs = [build_mixed() for _ in range(5)]
    assert all(r == runs[0] for r in runs)
    assert len({r.to_json() for r in runs}) == 1
    assert len({r.canonical_bytes() for r in runs}) == 1
    assert len({r.digest() for r in runs}) == 1
    assert len({replay_trace(r).to_json() for r in runs}) == 1


_CHILD = """
import sys
sys.path.insert(0, {src!r})
sys.path.insert(0, {tests!r})
import test_f8q4_digital_trace_serialization as m
from academic_core.domain.engineering.digital import DigitalTrace, replay_trace
tr = m.build_mixed()
back = DigitalTrace.from_json(tr.to_json())
print(tr.digest(), replay_trace(back).digest(), m.build_same_timestamp().digest())
"""


def test_q4_z02_separate_processes_and_hash_seeds():
    src = str(DIGITAL_DIR.parents[3])
    code = _CHILD.format(src=src, tests=str(Path(__file__).resolve().parent))
    outputs = set()
    for seed in ("0", "1", "12345", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             timeout=120, check=True)
        outputs.add(res.stdout.strip())
    assert len(outputs) == 1
    here = f"{build_mixed().digest()} {build_mixed().digest()} {build_same_timestamp().digest()}"
    assert outputs == {here}


# =============================================================== golden fixtures

@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_q4_g01_golden_fixture(name):
    raw = (FIXTURES / f"{name}.json").read_bytes()
    trace = GOLDEN[name]()
    assert raw == trace.canonical_bytes() + b"\n"  # fixture file = canonical bytes + one newline
    decoded = DigitalTrace.from_json(raw)
    assert decoded == trace
    assert decoded.to_json().encode("utf-8") + b"\n" == raw
    assert hashlib.sha256(raw.rstrip(b"\n")).hexdigest() == GOLDEN_DIGESTS[name] == trace.digest()
    assert verify_replay(decoded) == trace
    assert json.loads(raw)["schema"] == "digital-trace" and json.loads(raw)["version"] == 1


def test_q4_g02_golden_set_is_complete():
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(GOLDEN)
    rep = DigitalTrace.from_json((FIXTURES / "repeated_probe_net.json").read_bytes())
    assert {c.net_id for c in rep.channels} == {"A", "Y"} and len(rep.channels) == 4
    assert DigitalTrace.from_json((FIXTURES / "empty.json").read_bytes()).channels == ()


# =============================================================== properties

_TIME_FORMS = (lambda t: t, lambda t: t + D("0.000"), lambda t: D(str(t) + "E+0") if "E" not in str(t) else t,
               lambda t: t.normalize() if t != 0 else t)


def _random_trace(rng):
    """Valid trace with shared nets, same-time glitches, mixed Decimal spellings."""
    nxt = lambda n: next(rng) % n  # noqa: E731
    start = D(nxt(4)) / 4
    nets = {}
    for k in range(1 + nxt(4)):
        initial = H if nxt(2) else L
        t, state, samples = start, initial, []
        for _ in range(nxt(9)):
            t = t + D(nxt(3)) / 8  # 0 increment -> same-timestamp transitions
            state = L if state is H else H
            samples.append((_TIME_FORMS[nxt(len(_TIME_FORMS))](t), state))
        nets[f"n{k}"] = (initial, samples, nxt(5))
    end = max([start] + [s[-1][0] for _, s, _ in nets.values() if s]) + D(nxt(3)) / 2
    probes = sorted({f"p{nxt(40):02d}" for _ in range(1 + nxt(6))})
    channels = []
    for pid in probes:
        net = f"n{nxt(len(nets))}"
        initial, samples, noops = nets[net]
        channels.append(_ch(pid, net, initial, samples, noops))
    return DigitalTrace(start, end, tuple(channels))


def test_q4_p01_round_trip_properties():
    rng = _lcg(20260922)
    for _ in range(300):
        trace = _random_trace(rng)
        text = trace.to_json()
        back = DigitalTrace.from_json(text)
        assert back == trace  # deserialize(serialize(t)) == t
        assert back.digest() == trace.digest()  # digest(t) == digest(roundtrip(t))
        assert replay_trace(back) == trace  # replay(roundtrip(t)) == t
        assert back.to_json() == text  # serialize(deserialize(serialize(t))) == serialize(t)
        for ch, bch in zip(trace.channels, back.channels):
            # order (incl. same-timestamp runs) and exact Decimal values preserved
            assert [(s.time, s.state) for s in ch.samples] == [(s.time, s.state) for s in bch.samples]
            assert all(D(canonical_time(s.time)) == s.time for s in ch.samples)
            assert ch.noop_count == bch.noop_count and ch.initial is bch.initial


def test_q4_p02_simulation_properties():
    rng = _lcg(7)
    kinds = (GateKind.AND, GateKind.OR, GateKind.XOR, GateKind.NAND, GateKind.NOR, GateKind.XNOR)
    for case in range(40):
        c = DigitalCircuit()
        inputs = [f"i{k}" for k in range(2 + next(rng) % 3)]
        for x in inputs + ["y", "z"]:
            c.add_net(x, H if next(rng) % 2 else L)
        c.add_component(DigitalComponent("g", kinds[case % 6], tuple(inputs + inputs[:1]), "y"))
        c.add_component(DigitalComponent("n", GateKind.NOT, ("y",), "z"))
        for k, x in enumerate(inputs):
            states = tuple(H if next(rng) % 2 else L for _ in range(1 + next(rng) % 6))
            c.add_stimulus(PatternStimulus(f"s{k}", x, D(next(rng) % 3) / 2, D(1) / 2, states))
        c.add_probe(DigitalProbe("y", "y"))
        c.add_probe(DigitalProbe("z", "z"))
        c.add_probe(DigitalProbe("zz", "z"))
        c.add_probe(DigitalProbe(inputs[0], inputs[0]))
        trace = _sim_trace(c)
        back = DigitalTrace.from_json(trace.to_json())
        assert back == trace and replay_trace(back) == trace
        assert back.digest() == trace.digest() and back.to_json() == trace.to_json()
