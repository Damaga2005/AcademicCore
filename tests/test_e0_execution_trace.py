"""E0 Explainable Execution -- ExecutionTrace test suite.

Sections:

- model and immutability, validation, event kinds, order and causality,
  references
- formulas, Decimal / Quantity / Unit, checks, D2 errors
- determinism (including separate processes), serialization and
  canonical JSON, malformed input, limits, digest, tampering, replay
- renderer, no mutation
- engineering integration, F8-Q integration, application and UI
- security / AST, properties, golden fixture

Deterministic generation only (LCG, no RNG module, no hypothesis).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.application.explain_render import QUESTIONS, build_view, render_markdown, render_text
from academic_core.domain.engineering import calc as calc_mod
from academic_core.domain.engineering import equations as eq_mod
from academic_core.domain.engineering.calc import LIBRARY, calculate
from academic_core.domain.engineering.digital import (
    CaptureConfig,
    CaptureStatus,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    GateKind,
    LogicAnalyzer,
    LogicState,
    PatternStimulus,
    ToggleStimulus,
    TriggerConfig,
    TriggerEdge,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.domain.execution import (
    EQUIVALENT,
    MAX_EVENTS,
    MAX_REFS,
    MAX_STRING,
    MAX_VALUES,
    RESULT_DIFFERS,
    CheckStatus,
    EventKind,
    ExecutionTrace,
    Outcome,
    TraceCheck,
    TraceError,
    TraceEvent,
    TraceRecorder,
    TraceValue,
    Verification,
    VerificationStatus,
    canonical_decimal,
    compare,
    first_difference,
    replay,
    semantic_json,
    verify_replay,
)
from academic_core.domain.execution import digital as dig
from academic_core.domain.execution import equation as eqn
from academic_core.domain.execution import model as model_mod
from academic_core.errors import IntegrationError, SerializationError, ValidationError, VersionMismatchError

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
EXEC = SRC / "domain" / "execution"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "execution_trace"
D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
DIVIDER = ({"Vi": "12 V", "R1": "1 kohm", "R2": "2 kohm"}, "Vout = Vi * R2 / (R1 + R2)", "voltage")


def divider():
    return eqn.explain_equation(*DIVIDER)


def half_adder():
    c = DigitalCircuit()
    for x in ("A", "B", "S", "C"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("xor_s", GateKind.XOR, ("A", "B"), "S"))
    c.add_component(DigitalComponent("and_c", GateKind.AND, ("A", "B"), "C"))
    c.add_stimulus(ToggleStimulus("clkA", "A", H, D("0.5"), D("0.5"), 8))
    c.add_stimulus(ToggleStimulus("clkB", "B", H, D(1), D(1), 4))
    for p, net in (("a", "A"), ("b", "B"), ("sum", "S"), ("carry", "C")):
        c.add_probe(DigitalProbe(p, net))
    return c


def xor3():
    c = DigitalCircuit()
    for x in ("A", "B", "C", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x3", GateKind.XOR, ("A", "B", "C"), "Y"))
    for sid, net in (("sA", "A"), ("sB", "B"), ("sC", "C")):
        c.add_stimulus(PatternStimulus(sid, net, D(1), D(1), (H, L)))
    c.add_probe(DigitalProbe("y", "Y"))
    c.add_probe(DigitalProbe("a", "A"))
    return c


HA_CONFIG = CaptureConfig(("a", "b", "carry", "sum"), D(0), D(3),
                          TriggerConfig("carry", TriggerEdge.RISING, D("0.5"), D("0.5")))


def capture_trace():
    return dig.explain_capture(half_adder(), HA_CONFIG, context=(("demo", "half_adder"),))


def _lcg(seed):
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        yield state >> 33


def _doc(trace=None):
    return json.loads((trace or divider()).to_json())


# =============================================================== model / immutability / validation

def test_e0_m01_trace_value_rules():
    assert TraceValue.of_number(3).number == D(3)
    q = parse_quantity("2.50 kohm")
    v = TraceValue.of_quantity(q)
    assert (v.number, v.unit, v.dimension) == (D("2.50"), q.unit.display, tuple(q.dimension))
    bad = [dict(), dict(number=D(1), text="x"), dict(number=1.5), dict(number=True), dict(number=D("NaN")),
           dict(number=D("Infinity")), dict(number=D("1E-500")), dict(text="x", unit="V"),
           dict(number=D(1), dimension=(1, 2)), dict(number=D(1), dimension=(1.0,) * 7),
           dict(text="a\x00b"), dict(text="x" * (MAX_STRING + 1)), dict(number=D(1), unit="u" * 65)]
    for kwargs in bad:
        with pytest.raises(ValidationError):
            TraceValue(**kwargs)


def test_e0_m02_event_rules():
    ok = TraceEvent("e1", EventKind.STEP, "t")
    assert ok.refs == ()
    chk = TraceCheck("x", TraceValue.of_text("a"), TraceValue.of_text("a"), CheckStatus.PASS)
    err = TraceError("AC-VAL-001", "BAD", "m")
    bad = [
        dict(event_id="x1", kind=EventKind.STEP, title="t"),
        dict(event_id="e0", kind=EventKind.STEP, title="t"),
        dict(event_id="e1", kind="STEP", title="t"),
        dict(event_id="e1", kind=EventKind.STEP, title=""),
        dict(event_id="e2", kind=EventKind.STEP, title="t", refs=("e1", "e1")),
        dict(event_id="e2", kind=EventKind.STEP, title="t", refs=["e1"]),
        dict(event_id="e2", kind=EventKind.STEP, title="t", refs=("x",)),
        dict(event_id="e99", kind=EventKind.STEP, title="t", refs=tuple(f"e{k}" for k in range(1, MAX_REFS + 2))),
        dict(event_id="e1", kind=EventKind.CHECK, title="t"),
        dict(event_id="e1", kind=EventKind.STEP, title="t", check=chk),
        dict(event_id="e1", kind=EventKind.ERROR, title="t"),
        dict(event_id="e1", kind=EventKind.STEP, title="t", error=err),
        dict(event_id="e1", kind=EventKind.RESULT, title="t"),
        dict(event_id="e1", kind=EventKind.STEP, title="t", values=(("a", TraceValue.of_text("1")),) * 2),
        dict(event_id="e1", kind=EventKind.STEP, title="t", values=(("1bad", TraceValue.of_text("1")),)),
        dict(event_id="e1", kind=EventKind.STEP, title="t",
             values=tuple((f"v{k}", TraceValue.of_text("1")) for k in range(MAX_VALUES + 1))),
        dict(event_id="e1", kind=EventKind.STEP, title="t", formula=""),
    ]
    for kwargs in bad:
        with pytest.raises(ValidationError):
            TraceEvent(**kwargs)
    for code, reason in (("AC-VAL-1", "X"), ("AC-VAL-001", "lower"), ("XX-VAL-001", "X")):
        with pytest.raises(ValidationError):
            TraceError(code, reason, "m")


def test_e0_m03_trace_invariants():
    t = divider()
    base = dict(operation=t.operation, inputs=t.inputs, events=t.events, result=t.result, outcome=t.outcome,
                verification=t.verification, metadata=t.metadata)

    def build(**over):
        return ExecutionTrace(**{**base, **over})
    assert build() == t
    swapped = list(t.events)
    swapped[5], swapped[6] = swapped[6], swapped[5]
    cases = [
        dict(operation="Bad Op"),
        dict(events=tuple(swapped)),  # ids out of order
        dict(events=t.events[:-1]),  # verification no longer matches
        dict(result=TraceValue.of_number(9, "V")),  # result disagrees with RESULT event
        dict(outcome=Outcome.FAILED),
        dict(inputs=t.inputs[:-1]),  # INPUT events without input
        dict(inputs=t.inputs[:-1] + ((t.inputs[-1][0], TraceValue.of_text("13 V")),)),
        dict(verification=Verification(VerificationStatus.PASS, 2, 1)),
        dict(metadata=(("b", "1"), ("a", "2"))),
        dict(metadata=(("a", "1"), ("a", "2"))),
        dict(events=list(t.events)),
    ]
    for over in cases:
        with pytest.raises(ValidationError):
            build(**over)
    forward = TraceEvent("e1", EventKind.STEP, "t", refs=("e2",))
    with pytest.raises(ValidationError, match="INVALID_REF"):
        ExecutionTrace("x.y", (), (forward,), None, Outcome.FAILED, Verification.of(()))


def test_e0_m04_immutable():
    t = divider()
    for obj, attr in ((t, "events"), (t, "result"), (t.events[0], "title"), (t.events[-1], "check"),
                      (t.events[-1].check, "status"), (t.result, "number"), (t.verification, "failed")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, None)
    assert isinstance(t.events, tuple) and isinstance(t.events[0].values, tuple)
    with pytest.raises(TypeError):
        t.events[0] = t.events[1]  # type: ignore[index]


def test_e0_m05_recorder_rules(monkeypatch):
    rec = TraceRecorder("demo.op")
    rec.input("x", TraceValue.of_text("1"))
    with pytest.raises(ValidationError, match="recorded twice"):
        rec.input("x", TraceValue.of_text("2"))
    with pytest.raises(ValidationError, match="INVALID_REF"):
        rec.event(EventKind.STEP, "s", refs=("e9",))
    rec.event(EventKind.RESULT, "r", refs=("e1",), result=TraceValue.of_text("ok"))
    t = rec.finish()
    assert t.outcome is Outcome.SUCCESS and t.result == TraceValue.of_text("ok")
    with pytest.raises(ValidationError):
        TraceRecorder("Bad Op")
    monkeypatch.setattr(model_mod, "MAX_EVENTS", 3)
    small = TraceRecorder("demo.op")
    for k in range(3):
        small.event(EventKind.STEP, f"s{k}")
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        small.event(EventKind.STEP, "one more")


# =============================================================== kinds / order / causality / references

def test_e0_k01_every_event_kind_comes_from_a_real_run():
    kinds = set()
    for t in (divider(), eqn.explain_equation({"G": "10"}, "Rg = 49.4 * kohm / (G - 1)"),
              eqn.explain_equation({"V": "5 V", "R": "1 kohm", "X": "3 V"}, "I = V / R"),
              eqn.explain_equation({"V": "5 V", "R": "0 ohm"}, "I = V / R"), capture_trace()):
        kinds |= {e.kind for e in t.events}
    assert kinds == set(EventKind)


def test_e0_c01_causality_and_references():
    t = divider()
    by_title = {e.title: e for e in t.events}
    norm = {e.formula: e.event_id for e in t.events if e.kind is EventKind.NORMALIZATION}
    product, total, quotient = by_title["Producto"], by_title["Suma"], by_title["Cociente"]
    assert product.refs == (norm["Vi"], norm["R2"])  # what it consumed (engine operand order)
    assert total.refs == (norm["R1"], norm["R2"])
    assert quotient.refs == (product.event_id, total.event_id)
    # a variable read is a reference to its NORMALIZATION, never a copied event
    assert sum(1 for e in t.events if e.formula == "R2") == 1
    assert t.consumers(norm["R2"]) == (product.event_id, total.event_id)  # who consumed R2
    result = next(e for e in t.events if e.kind is EventKind.RESULT)
    assert result.refs == (quotient.event_id,)  # what produced the result
    assert set(t.consumers(result.event_id)) == {e.event_id for e in t.checks()}  # which checks verified it
    for k, e in enumerate(t.events):  # everything consumed happened first
        assert all(int(r[1:]) < k + 1 for r in e.refs)


def test_e0_c02_navigation_errors():
    t = divider()
    with pytest.raises(ValidationError, match="UNKNOWN_EVENT"):
        t.event("e999")
    with pytest.raises(ValidationError, match="UNKNOWN_EVENT"):
        t.consumers("nope")


# =============================================================== formulas / units / checks / errors

def test_e0_f01_formulas_are_text_of_the_parsed_source():
    t = divider()
    formulas = [e.formula for e in t.events if e.kind is EventKind.STEP]
    assert formulas == ["Vout = Vi * R2 / (R1 + R2)", "Vi * R2", "R1 + R2", "Vi * R2 / (R1 + R2)"]
    f = eqn.explain_equation({"B": "3950", "T": "298.15", "T0": "298.15", "R0": "10 kohm"},
                             "R = R0 * exp(B * (1 / T - 1 / T0))")
    assert any(e.title == "Función exp" and e.formula == "exp(B * (1 / T - 1 / T0))" for e in f.events)


def test_e0_u01_exact_decimal_quantity_unit():
    t = eqn.explain_equation({"V": "1 V", "R": "3 ohm"}, "I = V / R", "current")
    official = calculate({"V": parse_quantity("1 V"), "R": parse_quantity("3 ohm")}, "I = V / R", at="x").value
    assert t.result.number == official.value and t.result.unit == official.unit.display
    assert len(canonical_decimal(t.result.number)) > 20  # full engine precision kept, never a float
    step = next(e for e in divider().events if e.title == "Suma")
    assert (step.result.number, step.result.unit, step.result.dimension) == (D(3), "kΩ", (1, 2, -3, -2, 0, 0, 0))
    back = ExecutionTrace.from_json(t.to_json())
    assert back.result.number == official.value

    def floats(node):
        if isinstance(node, dict):
            return any(floats(v) for v in node.values())
        if isinstance(node, list):
            return any(floats(v) for v in node)
        return isinstance(node, float)
    assert not floats(t.to_dict())


def test_e0_u02_canonical_decimal():
    for raw, text in (("2.50", "2.5"), ("-0.000", "0"), ("1E+3", "1000"), ("-1.2300", "-1.23"), ("1E-5", "0.00001"),
                      ("123", "123")):
        assert canonical_decimal(D(raw)) == text
    traces = []
    for spelling in ("2.50", "2.5", "25E-1"):
        rec = TraceRecorder("x.y")
        rec.input("v", TraceValue.of_number(D(spelling), "V"))
        rec.event(EventKind.RESULT, "r", refs=("e1",), result=TraceValue.of_number(D(spelling), "V"))
        traces.append(rec.finish())
    assert len({t.to_json() for t in traces}) == 1  # numerically equal -> one representation
    with pytest.raises(ValidationError, match="SUCCESS needs exactly one RESULT"):
        TraceRecorder("x.y").finish()  # a run that produced neither result nor error is not a trace


def test_e0_k02_checks_pass_fail_are_never_hidden():
    ok = divider()
    assert ok.verification.status is VerificationStatus.PASS and ok.verification.failed == 0
    bad = eqn.explain_equation({"I": "0.005 A", "R": "1000 ohm"}, "V = I * R", "current")  # wrong expectation
    assert bad.outcome is Outcome.SUCCESS and bad.verification.status is VerificationStatus.FAIL
    failed = [e.check for e in bad.checks() if e.check.status is CheckStatus.FAIL]
    assert failed and failed[0].actual == TraceValue.of_text("voltage") and failed[0].expected.text == "current"
    assert "FAIL: dimensión del resultado" in render_text(build_view(bad))
    doc = _doc(bad)
    doc["verification"]["status"] = "PASS"
    doc["verification"]["failed"] = 0
    with pytest.raises(ValidationError, match="verification"):
        ExecutionTrace.from_dict(doc)  # a failed check cannot be hidden by editing the summary


def test_e0_e01_failures_keep_d2_codes_and_where():
    zero = eqn.explain_equation({"V": "5 V", "R": "0 ohm"}, "I = V / R")
    err = next(e for e in zero.events if e.kind is EventKind.ERROR)
    assert zero.outcome is Outcome.FAILED and zero.result is None
    assert err.error.code == "AC-VAL-001" and "division by zero" in err.error.message
    assert {zero.event(r).formula for r in err.refs} == {"V", "R"}  # the operands ready when it stopped
    unknown = eqn.explain_equation({"R": "1 kohm"}, "I = Q / R")
    assert next(e for e in unknown.events if e.kind is EventKind.ERROR).error.message == "unknown variable: Q"
    unit = eqn.explain_equation({"R": "1 bananas"}, "I = R")
    assert unit.outcome is Outcome.FAILED
    bad_probe = dig.explain_capture(half_adder(), CaptureConfig(("ghost",), D(0), D(1)))
    e = next(e for e in bad_probe.events if e.kind is EventKind.ERROR)
    assert (e.error.code, e.error.reason) == ("AC-VAL-001", "UNKNOWN_PROBE")
    budget = dig.explain_capture(half_adder(), CaptureConfig(("a",), D(0), D(3)), max_events=3)
    assert next(e for e in budget.events if e.kind is EventKind.ERROR).error.code == "AC-DOM-001"


def test_e0_e02_messages_are_ui_safe():
    exc = ValueError("cannot open /home/secret/user/data.db or C:\\Users\\me\\x.txt\x00now")
    msg = TraceError.from_exception(exc).message
    assert "/home/secret" not in msg and "C:\\Users" not in msg and "\x00" not in msg and "<path>" in msg


# =============================================================== determinism

def test_e0_d01_same_execution_same_trace():
    runs = [divider() for _ in range(3)] + [eqn.explain_equation(dict(reversed(DIVIDER[0].items())), *DIVIDER[1:])]
    assert all(r == runs[0] for r in runs) and len({r.to_json() for r in runs}) == 1
    caps = [capture_trace() for _ in range(3)]
    assert all(c == caps[0] for c in caps) and len({c.digest() for c in caps}) == 1


_CHILD = """
import sys
sys.path.insert(0, {src!r}); sys.path.insert(0, {tests!r})
import test_e0_execution_trace as m
print(m.divider().digest(), m.capture_trace().digest(), m.divider().to_json() == m.divider().to_json())
"""


def test_e0_d02_separate_processes_and_hash_seeds():
    code = _CHILD.format(src=str(ROOT / "src"), tests=str(ROOT / "tests"))
    outs = set()
    for seed in ("0", "1", "777", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                timeout=180, check=True).stdout.strip().splitlines()[-1])
    assert outs == {f"{divider().digest()} {capture_trace().digest()} True"}


# =============================================================== serialization / canonical JSON

def test_e0_s01_round_trip_and_canonical_form():
    for t in (divider(), capture_trace(), eqn.explain_equation({"V": "5 V", "R": "0 ohm"}, "I = V / R")):
        text = t.to_json()
        back = ExecutionTrace.from_json(text)
        assert back == t and back.to_json() == text and back.digest() == t.digest()
        assert ExecutionTrace.from_json(text.encode("utf-8")) == t
        assert text == json.dumps(t.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                  allow_nan=False)
        assert text.isascii() and "\n" not in text and not text.endswith(" ")
    doc = _doc()
    assert doc["schema"] == "execution-trace" and doc["version"] == 1
    assert set(doc) == {"schema", "version", "operation", "inputs", "events", "result", "outcome",
                        "verification", "metadata"}
    assert doc["result"] == {"number": "8", "unit": "V", "dimension": [1, 2, -3, -1, 0, 0, 0]}


@pytest.mark.parametrize("mutate, error", [
    (lambda d: d.update(schema="digital-trace"), "INVALID_SCHEMA"),
    (lambda d: d.pop("events"), "missing"),
    (lambda d: d.update(extra=1), "unknown field"),
    (lambda d: d["events"][0].update(extra=1), "unknown field"),
    (lambda d: d["events"][0].pop("why"), "missing"),
    (lambda d: d["events"][5].update(kind="MAGIC"), "kind"),
    (lambda d: d["events"][13]["check"].update(status="MAYBE"), "status"),
    (lambda d: d["result"].update(number="8.0"), "canonical"),
    (lambda d: d["result"].update(number="8e0"), "canonical"),
    (lambda d: d["result"].update(number="-0"), "canonical"),
    (lambda d: d["result"].update(number=8), "string"),
    (lambda d: d["result"].update(number="8", text="x"), "unknown field"),
    (lambda d: d["events"][2].update(refs="e1"), "array"),
    (lambda d: d["events"][9].update(refs=["e99"]), "INVALID_REF"),
    (lambda d: d["events"][9].update(id="e42"), "INVALID_ORDER"),
    (lambda d: d.update(metadata=[]), "metadata"),
    (lambda d: d.update(outcome="MAYBE"), "outcome"),
    (lambda d: d["verification"].update(checks=True), "integer"),
    (lambda d: d["events"].reverse(), "INVALID_ORDER"),
    ([], "document must be an object"),
])
def test_e0_s02_malformed_documents(mutate, error):
    if callable(mutate):
        doc = _doc()
        mutate(doc)
    else:
        doc = mutate
    with pytest.raises(ValidationError, match=error):
        ExecutionTrace.from_dict(doc)


def test_e0_s03_versions_json_layer_duplicate_keys_floats_nan():
    doc = _doc()
    for version in (2, 0, "1", True, None):
        with pytest.raises(VersionMismatchError) as info:
            ExecutionTrace.from_dict(dict(doc, version=version))
        assert info.value.code == "AC-VER-001"
    good = json.dumps(doc)
    for text in (good[:-3], good + "x", good.replace('"version": 1', '"version": 1, "version": 1'),
                 good.replace('"number": "8"', '"number": 8.0'), good.replace('"checks": 2', '"checks": NaN'),
                 good.replace('"checks": 2', '"checks": Infinity'), good.replace('"checks": 2', '"checks": -Infinity'),
                 good.replace('"checks": 2', '"checks": 1' + "0" * 20), "\ufeff" + good, "", "{'a': 1}"):
        with pytest.raises(SerializationError) as info:
            ExecutionTrace.from_json(text)
        assert info.value.code == "AC-SER-001"
    for raw in (b"\xff\xfe", 1, None, ["x"]):
        with pytest.raises(SerializationError):
            ExecutionTrace.from_json(raw)


# =============================================================== limits

def test_e0_l01_limits(monkeypatch):
    from academic_core.domain.execution import codec
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        ExecutionTrace.from_json('{"a":"' + "x" * codec.MAX_JSON_BYTES + '"}')
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        ExecutionTrace.from_json("[" * 100_000)
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        ExecutionTrace.from_json('{"a":[[[[[[[[1]]]]]]]]}')
    monkeypatch.setattr(codec, "MAX_ITEMS", 50)
    with pytest.raises(SerializationError, match="TRACE_LIMIT"):
        ExecutionTrace.from_json(divider().to_json())
    monkeypatch.undo()
    doc = _doc()
    doc["events"] = [dict(doc["events"][6], id=f"e{k + 1}", refs=[]) for k in range(MAX_EVENTS + 1)]
    with pytest.raises(ValidationError, match="TRACE_LIMIT"):
        ExecutionTrace.from_dict(doc)
    for mutate in (lambda d: d["events"][5].update(title="t" * (MAX_STRING + 1)),
                   lambda d: d["events"][9].update(refs=[f"e{k}" for k in range(1, 70)]),
                   lambda d: d["events"][5].update(values=[{"name": f"v{k}", "value": {"text": "1"}}
                                                           for k in range(MAX_VALUES + 1)]),
                   lambda d: d.update(metadata={f"k{k:02d}": "v" for k in range(40)}),
                   lambda d: d["result"].update(number="1" + "0" * 250),
                   lambda d: d["events"][5].update(formula="f" * (MAX_STRING + 1))):
        doc = _doc()
        mutate(doc)
        with pytest.raises(ValidationError):
            ExecutionTrace.from_dict(doc)


def test_e0_l02_large_capture_is_bounded_and_says_so():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.001"), 3000))
    c.add_probe(DigitalProbe("a", "A"))
    t = dig.explain_capture(c, CaptureConfig(("a",), D(0), D(10)))
    steps = [e for e in t.events if e.kind is EventKind.STEP and e.title.startswith("a:")]
    assert len(steps) == dig.MAX_DETAILED_TRANSITIONS
    warn = next(e for e in t.events if e.title == "Transiciones no detalladas")
    assert "512 de 3000" in warn.why
    assert ExecutionTrace.from_json(t.to_json()) == t


# =============================================================== digest

def test_e0_h01_digest_covers_semantics_not_metadata():
    rec = TraceRecorder("x.y")
    rec.input("v", TraceValue.of_number(1, "V"))
    rec.event(EventKind.RESULT, "r", refs=("e1",), result=TraceValue.of_number(1, "V"))
    plain = rec.finish()
    rec.metadata("host_note", "diagnostic only")
    noted = rec.finish()
    assert plain.digest() == noted.digest() and plain.to_json() != noted.to_json()
    assert "host_note" not in semantic_json(noted)
    assert plain.digest() == hashlib.sha256(semantic_json(plain).encode("utf-8")).hexdigest()
    base = divider().digest()
    for mutate in (lambda d: d["events"][9]["result"].update(number="24001"),
                   lambda d: d["events"][9]["result"].update(unit="mV"),
                   lambda d: d["events"][9].update(title="Otra cosa"),
                   lambda d: d["events"][5].update(why="otro motivo")):
        doc = _doc()
        mutate(doc)
        assert ExecutionTrace.from_dict(doc).digest() != base


# =============================================================== tampering / replay

def test_e0_r01_replay_equation_and_digital_equivalent():
    t = divider()
    report = replay(t, eqn.replay_equation)
    assert report.status == EQUIVALENT and report.original_digest == report.replayed_digest == t.digest()
    assert verify_replay(t, eqn.replay_equation) is t
    c = capture_trace()
    assert replay(c, lambda tr: dig.replay_capture(tr, lambda ctx: half_adder())).equivalent
    failed = eqn.explain_equation({"V": "5 V", "R": "0 ohm"}, "I = V / R")
    assert replay(failed, eqn.replay_equation).equivalent  # failures replay too


def test_e0_r02_replay_detects_tampering():
    t = divider()
    cases = {
        "events[9].result": lambda d: d["events"][9]["result"].update(number="24001"),  # changed value
        "events[10].result": lambda d: d["events"][10]["result"].update(unit="Ω"),  # changed unit
        "events[5].title": lambda d: d["events"][5].update(title="Otro"),  # changed text
    }
    for path, mutate in cases.items():
        doc = _doc(t)
        mutate(doc)
        forged = ExecutionTrace.from_dict(doc)
        report = replay(forged, eqn.replay_equation)
        assert report.status == RESULT_DIFFERS and report.first_difference == path
        with pytest.raises(IntegrationError, match="REPLAY_MISMATCH"):
            verify_replay(forged, eqn.replay_equation)
    # lost event (kept internally consistent): replay still notices
    doc = _doc(t)
    doc["events"] = doc["events"][:-1]
    doc["verification"] = {"status": "PASS", "checks": 1, "failed": 0}
    shorter = ExecutionTrace.from_dict(doc)
    assert replay(shorter, eqn.replay_equation).first_difference == "events (count 14 != 15)"
    # changed input: replay recomputes from it, the recorded facts no longer match
    doc = _doc(t)
    doc["inputs"][4]["value"]["text"] = "13 V"
    doc["events"][4]["values"][0]["value"]["text"] = "13 V"
    assert replay(ExecutionTrace.from_dict(doc), eqn.replay_equation).first_difference == "events[8].result"
    # reordered events are refused outright
    doc = _doc(t)
    doc["events"][6], doc["events"][7] = doc["events"][7], doc["events"][6]
    with pytest.raises(ValidationError, match="INVALID_ORDER"):
        ExecutionTrace.from_dict(doc)


def test_e0_r03_compare_paths_and_wrong_operation():
    a, b = divider(), eqn.explain_equation({"Vi": "12 V", "R1": "1 kohm", "R2": "3 kohm"}, *DIVIDER[1:])
    assert first_difference(a, a) == "" and first_difference(a, b).startswith(("inputs", "result", "verification"))
    assert compare(a, b).status == RESULT_DIFFERS
    with pytest.raises(ValidationError):
        eqn.replay_equation(capture_trace())
    with pytest.raises(ValidationError):
        dig.replay_capture(a, lambda ctx: half_adder())
    with pytest.raises(ValidationError):
        compare(a, "x")


# =============================================================== renderer / no mutation

def test_e0_v01_renderer_answers_the_seven_questions_from_the_trace(monkeypatch):
    t = divider()
    snapshot = t.to_json()

    def forbidden(*_a, **_k):
        raise AssertionError("the renderer must not recompute")
    monkeypatch.setattr(eq_mod, "evaluate", forbidden)
    monkeypatch.setattr(calc_mod, "calculate", forbidden)
    view = build_view(t)
    assert [s.question for s in view.sections] == [q for _, q in QUESTIONS]
    text = render_text(view)
    for needle in ("¿Qué recibimos?", "Vi = 12 V", "Vi * R2 / (R1 + R2) = 8 V", "R1 + R2 = 3 kΩ",
                   "PASS: igual al cálculo certificado", "Resultado Vout: 8 V", view.digest):
        assert needle in text, needle
    step = next(s for s in view.steps if s.title == "Cociente")
    assert step.consumed == ("e10 = 24000 derived", "e11 = 3 kΩ") and step.result == "8 V"
    assert t.to_json() == snapshot  # never mutated
    md = render_markdown(view)
    assert md.startswith("# Explicación: engineering.equation") and "## ¿Qué comprobamos?" in md
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.outcome = "X"
    with pytest.raises(ValidationError):
        build_view("not a trace")


def test_e0_v02_malicious_text_is_only_data(monkeypatch):
    import builtins
    calls = []
    for name in ("eval", "exec", "compile"):
        original = getattr(builtins, name)
        monkeypatch.setattr(builtins, name, lambda *a, _n=name, _o=original, **k: (calls.append(_n), _o(*a, **k))[1])
    rec = TraceRecorder("x.y")
    rec.input("v", TraceValue.of_text("__import__('os').system('echo pwned')"))
    rec.event(EventKind.RESULT, "<script>alert(1)</script> *x* [l](http://e)", refs=("e1",),
              formula="__import__('os').system('rm -rf /')", result=TraceValue.of_text("`$(id)`"))
    t = ExecutionTrace.from_json(rec.finish().to_json())
    md = render_markdown(build_view(t))
    assert "<script>" not in md and "\\<script\\>" in md and "\\[l\\]" in md
    assert "__import__('os').system('rm -rf /')" in render_text(build_view(t))  # shown, never run
    assert calls == []


# =============================================================== engineering integration

@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_e0_i01_every_library_equation_traces_the_real_result(key):
    defaults = dict(calc_mod.LIBRARY_DEFAULTS.get(key, {}))
    samples = {"V": "5 V", "I": "0.5 A", "R": "1000 ohm", "C": "1 uF", "L": "2 H", "T": "0.01 s", "Vi": "12 V",
               "R1": "1 kohm", "R2": "2 kohm", "Vs": "5 V", "K": "2", "eps": "0.001"}
    source = LIBRARY[key]["source"]
    names = {tok for kind, tok in eq_mod._tokenize(source.partition("=")[2]) if kind == "name"}
    inputs = defaults or {n: samples[n] for n in sorted(names) if n in samples}
    t = eqn.explain_equation(inputs, source, LIBRARY[key]["dim"])
    assert t.outcome is Outcome.SUCCESS, (key, [e.error for e in t.events if e.error])
    official = calculate({k: parse_quantity(v) for k, v in inputs.items()}, source, at="x").value
    assert t.result == TraceValue.of_quantity(official)
    assert t.verification.status is VerificationStatus.PASS, key
    assert replay(t, eqn.replay_equation).equivalent


def test_e0_i02_observer_does_not_change_the_engine():
    env = {"Vi": parse_quantity("12 V"), "R1": parse_quantity("1 kohm"), "R2": parse_quantity("2 kohm")}
    eq = eq_mod.parse_equation(DIVIDER[1])
    seen = []

    class Spy:
        def leaf(self, *a):
            seen.append(("leaf", a[0], a[1]))

        def operation(self, *a):
            seen.append(("op", a[0], a[1]))
    assert eq_mod.evaluate(eq, env, observer=Spy()) == eq_mod.evaluate(eq, env)
    assert seen == [("leaf", "variable", "Vi"), ("leaf", "variable", "R2"), ("op", "*", "Vi * R2"),
                    ("leaf", "variable", "R1"), ("leaf", "variable", "R2"), ("op", "+", "R1 + R2"),
                    ("op", "/", "Vi * R2 / (R1 + R2)")]


# =============================================================== F8-Q integration

def test_e0_q01_capture_trace_records_the_real_capture(monkeypatch):
    calls = {"capture": 0}
    original = LogicAnalyzer.capture

    def counting(self, circuit, config):
        calls["capture"] += 1
        return original(self, circuit, config)
    monkeypatch.setattr(LogicAnalyzer, "capture", counting)
    t = capture_trace()
    assert calls["capture"] == 1  # the certified path, run once; no second simulator
    monkeypatch.undo()
    real = LogicAnalyzer().capture(half_adder(), HA_CONFIG)
    assert real.status is CaptureStatus.TRIGGERED
    decision = next(e for e in t.events if e.kind is EventKind.DECISION)
    assert decision.value("time").number == real.trigger_time
    assert decision.value("index").number == real.trigger_index and decision.value("fired").text == "RISING"
    trig_step = t.event(decision.refs[0])
    assert trig_step.title == "carry: LOW → HIGH en t = 1.5 s"
    detailed = [(e.value("time").number, e.value("new").text) for e in t.events
                if e.kind is EventKind.STEP and e.title.startswith("sum:")]
    assert detailed == [(s.time, s.state.name) for s in real.trace.channel("sum").samples]
    result = next(e for e in t.events if e.kind is EventKind.RESULT)
    assert result.value("trace_digest").text == real.trace.digest() and t.result.text == "TRIGGERED"
    assert t.event(trig_step.refs[0]).title.startswith("Puerta and_c")  # attributed to its driver
    statuses = {e.check.what: e.check.status for e in t.checks()}
    assert statuses["tabla de verdad de and_c (AND)"] is CheckStatus.PASS
    assert statuses["tabla de verdad de xor_s (XOR)"] is CheckStatus.PASS
    assert statuses["re-análisis tras replay (verify_capture)"] is CheckStatus.PASS
    assert t.verification.status is VerificationStatus.PASS


def test_e0_q02_same_timestamp_not_triggered_and_not_applicable():
    t = dig.explain_capture(xor3(), CaptureConfig(("a", "y"), D(0), D(3),
                                                  TriggerConfig("y", TriggerEdge.FALLING, D(0), D(0))))
    ys = [e for e in t.events if e.kind is EventKind.STEP and e.title.startswith("y:")]
    assert [e.value("same_time").text for e in ys] == ["1/3", "2/3", "3/3"]
    assert t.event(next(e for e in t.events if e.kind is EventKind.DECISION).refs[0]) is ys[1]
    tt = next(e.check for e in t.checks() if e.check.what.startswith("tabla de verdad"))
    assert tt.status is CheckStatus.NOT_APPLICABLE and "B, C" in tt.detail
    nt = dig.explain_capture(half_adder(), CaptureConfig(("a", "carry"), D(50), D(60),
                                                         TriggerConfig("carry", TriggerEdge.RISING, D(0), D(0))))
    assert nt.outcome is Outcome.SUCCESS and nt.result.text == "NOT_TRIGGERED"
    assert any(e.title == "Sin disparo en carry" for e in nt.events)


def test_e0_q03_f8q_certified_modules_untouched():
    out = subprocess.run(["git", "diff", "--name-only", "0cf3554", "--", "src/academic_core/domain/engineering/digital"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 or out.stdout.strip() == ""


# =============================================================== application / UI

def test_e0_a01_application_service(tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    view = core.explain.explain_exercise("voltage-divider", DIVIDER[0])
    assert view.outcome == "SUCCESS" and view.verification == "PASS" and view.digest == divider().digest()
    assert core.explain.replay(view.trace_json).status == "EQUIVALENT"
    assert core.explain.load(view.trace_json) == view
    cap = core.explain.explain_capture(AnalyzerRequest("xor3_glitch", ("a", "y"), "0", "4", "y", "BOTH", "0", "1"))
    assert cap.operation == "digital.logic-analyzer" and core.explain.replay(cap.trace_json).status == "EQUIVALENT"
    doc = json.loads(view.trace_json)
    doc["operation"] = "unknown.op"
    with pytest.raises(ValidationError, match="UNSUPPORTED_OPERATION"):
        core.explain.replay(json.dumps(doc))
    from academic_core.errors import ConfigurationError
    with pytest.raises(ConfigurationError):
        core.explain.explain_exercise("nope", {})
    assert isinstance(core.digital, DigitalAnalysisService)


def test_e0_a02_ui_explain_button(qtbot, tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.exercises import ExercisePanel
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    panel = ExercisePanel(core)
    qtbot.addWidget(panel)
    panel.selector.setCurrentText("ohm-v")
    panel.inputs.setPlainText("I=0.005 A; R=1000 ohm")
    panel.btn_explain.click()
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)
    text = panel.output.toPlainText()
    assert panel.state.value == "SUCCESS" and "¿Qué recibimos?" in text and "Resultado V: 5 V" in text
    assert panel.explanation.digest == eqn.explain_equation({"I": "0.005 A", "R": "1000 ohm"}, "V = I * R",
                                                            "voltage").digest()


# =============================================================== security / architecture

def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    return tree, mods


E0_FILES = sorted(EXEC.glob("*.py")) + [SRC / "application" / "explain_service.py",
                                        SRC / "application" / "explain_render.py"]


def test_e0_x01_no_dynamic_execution():
    banned_mods = {"pickle", "marshal", "shelve", "subprocess", "importlib", "pkgutil", "ctypes"}
    for f in E0_FILES + [SRC / "domain" / "engineering" / "equations.py"]:
        tree, mods = _imports(f)
        assert not {m.split(".")[0] for m in mods} & banned_mods, f.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("eval", "exec", "compile", "__import__", "getattr", "setattr"), f.name
        assert "shell=True" not in f.read_text(encoding="utf-8") and "os.system" not in f.read_text(encoding="utf-8")


def test_e0_x02_boundaries_and_no_cycles():
    for f in EXEC.glob("*.py"):
        _, mods = _imports(f)
        top = {m.split(".")[0] for m in mods}
        assert not top & {"PySide6", "logging", "time", "datetime", "random", "uuid", "os", "sys", "io", "pathlib",
                          "threading"}, f.name
        assert not any(m.startswith(("academic_core.application", "academic_core.ui",
                                     "academic_core.infrastructure")) for m in mods), f.name
    core = {"model.py", "codec.py", "replay.py", "__init__.py"}
    for f in EXEC.glob("*.py"):
        if f.name in core:  # the transversal core depends on no engine
            _, mods = _imports(f)
            assert not any(m.startswith("academic_core.domain.engineering") for m in mods), f.name
    for f in (SRC / "domain").rglob("*.py"):  # engines never import E0: no cycle
        if EXEC in f.parents:
            continue
        _, mods = _imports(f)
        assert not any(m.startswith("academic_core.domain.execution") for m in mods), f
    _, render_mods = _imports(SRC / "application" / "explain_render.py")
    assert not any(m.startswith("academic_core.domain.engineering") for m in render_mods)  # renders, never solves
    for name in ("explain_service.py", "explain_render.py"):
        _, mods = _imports(SRC / "application" / name)
        assert not any(m.startswith(("PySide6", "academic_core.ui")) for m in mods)
    _, ui_mods = _imports(SRC / "ui" / "exercises.py")
    assert not any(m.startswith("academic_core.domain") for m in ui_mods)  # no pedagogy in widgets


# =============================================================== properties

def _random_expression(rng, depth=0):
    nxt = lambda n: next(rng) % n  # noqa: E731
    if depth > 2 or nxt(3) == 0:
        return ("R1", "R2", "Vi", "2", "0.5")[nxt(5)]
    op = ("+", "*", "/")[nxt(3)]
    left, right = _random_expression(rng, depth + 1), _random_expression(rng, depth + 1)
    if op == "+":
        return f"({left} + {left})" if nxt(2) else f"{left} * 2"
    return f"({left} {op} {right})"


def test_e0_p01_properties_round_trip_digest_order_refs():
    rng = _lcg(20260922)
    inputs = {"R1": "1.5 kohm", "R2": "2.25 kohm", "Vi": "12 V"}
    for _ in range(80):
        source = f"Y = {_random_expression(rng)}"
        t = eqn.explain_equation(inputs, source)
        back = ExecutionTrace.from_json(t.to_json())
        assert back == t and back.digest() == t.digest() and back.to_json() == t.to_json()
        assert replay(t, eqn.replay_equation).equivalent
        for k, e in enumerate(t.events):
            assert e.event_id == f"e{k + 1}" and all(int(r[1:]) <= k for r in e.refs)
        if t.outcome is Outcome.SUCCESS:
            env = {k: parse_quantity(v) for k, v in inputs.items()}
            official = eq_mod.evaluate(eq_mod.parse_equation(source), env)
            assert t.result == TraceValue.of_quantity(official)


# =============================================================== golden

def test_e0_g01_golden_voltage_divider():
    raw = (FIXTURES / "voltage_divider.json").read_bytes()
    t = divider()
    assert raw == t.to_json().encode("utf-8") + b"\n"
    assert hashlib.sha256(semantic_json(t).encode("utf-8")).hexdigest() == t.digest() == "57ec3ab4318964831e1798a34a0b71437fd8ccc6c46adbd08b5a5f511cba60c7"
    assert ExecutionTrace.from_json(raw) == t
    assert copy.deepcopy(t) == t
