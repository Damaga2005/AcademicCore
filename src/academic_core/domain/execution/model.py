# SPDX-License-Identifier: MIT
"""E0 ExecutionTrace model: an immutable, validated record of a REAL execution.

A resolver running for real emits facts through a ``TraceRecorder``. The
result is a frozen ``ExecutionTrace``. Explanations are only renderings of
that trace: nothing here recomputes a solution.

Identity and order:

- Event ids are ``e1``, ``e2``, … in emission order, so they are
  deterministic and positional. No random ids, clocks, ``id()`` or
  ``hash()`` are involved.
- ``refs`` may only point to *earlier* events. That gives causality:
  ``refs`` says which earlier facts an event consumed, and the reverse
  view (``consumers``) says who consumed a value. The graph is a DAG by
  construction, so it has no cycles.

Values: ``TraceValue`` is either an exact ``Decimal`` with a unit symbol
and the 7-exponent SI dimension (straight from ``Quantity``, never a
float), or a text value (e.g. ``HIGH``, a digest, a channel list).

Outcome and verification:

- ``SUCCESS`` means exactly one RESULT event and no ERROR. ``FAILED``
  means at least one ERROR event.
- CHECK events carry a structured ``TraceCheck``: what was checked, the
  actual value, the expected value, an optional tolerance, and the status.
- ``verification`` summarises them. It is validated against the events,
  so a failed check can never be hidden.

``metadata`` holds diagnostic key/values only. It is excluded from the
digest (see ``codec.py``).

Errors (D2, no new codes): invalid traces raise ``ValidationError``
(AC-VAL-001) with a reason token. ``TraceError`` records a failure of the
traced execution using the failing exception's D2 code.

Pure domain: stdlib + ``academic_core.errors`` only. No logging, IO, Qt,
clock or RNG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from academic_core.errors import AcademicCoreError, ValidationError

SCHEMA = "execution-trace"
VERSION = 1
FORMAT = f"{SCHEMA}/{VERSION}"

MAX_EVENTS = 10_000
MAX_INPUTS = 256
MAX_REFS = 64
MAX_VALUES = 64
MAX_STRING = 512  # titles, reasons, messages, text values, formulas
MAX_NAME = 64  # input / value names, metadata keys, unit symbols
MAX_METADATA = 32
MAX_NUMBER_DIGITS = 200  # significant digits + |exponent| of a traced Decimal

_ID_RE = re.compile(r"e[1-9][0-9]{0,5}\Z")
_OPERATION_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.:\-]{0,95}\Z")  # e.g. "transitions.<64-char probe id>"
_CODE_RE = re.compile(r"AC-[A-Z]{3}-[0-9]{3}\Z")
_REASON_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_PATH = re.compile(r"(?:[A-Za-z]:\\|/)(?:[^\s/\\:]+[/\\])+[^\s/\\]*")


def _invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


def _text(value: object, what: str, limit: int = MAX_STRING, empty: bool = True) -> str:
    if not isinstance(value, str):
        raise _invalid("INVALID_TRACE", f"{what} must be text, got {type(value).__name__}")
    if len(value) > limit:
        raise _invalid("TRACE_LIMIT", f"{what} longer than {limit} characters")
    if not empty and not value:
        raise _invalid("INVALID_TRACE", f"{what} must not be empty")
    if _CONTROL.search(value):
        raise _invalid("INVALID_TRACE", f"{what} contains control characters")
    return value


def _name(value: object, what: str) -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise _invalid("INVALID_ID", f"{what} {str(value)[:MAX_NAME]!r} must match {_NAME_RE.pattern}")
    return value


def safe_message(text: str) -> str:
    """Engine messages without absolute paths or control characters, bounded."""
    cleaned = _PATH.sub("<path>", _CONTROL.sub(" ", str(text)))
    return cleaned[:MAX_STRING]


class EventKind(str, Enum):
    INPUT = "INPUT"  # an input of the operation, as received
    NORMALIZATION = "NORMALIZATION"  # an input turned into an engine value (e.g. text -> Quantity)
    VALUE = "VALUE"  # a constant/value the engine read (literal, unit, observed fact)
    STEP = "STEP"  # an operation the engine applied, producing a value
    DECISION = "DECISION"  # a choice the engine made (e.g. which edge triggered)
    CHECK = "CHECK"  # a verification with a structured TraceCheck
    RESULT = "RESULT"  # the final result
    WARNING = "WARNING"  # something notable that did not stop execution
    ERROR = "ERROR"  # the failure that stopped execution


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Outcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class VerificationStatus(str, Enum):
    PASS = "PASS"  # every applicable check passed
    FAIL = "FAIL"  # at least one check failed
    NONE = "NONE"  # no applicable check


@dataclass(frozen=True)
class TraceValue:
    """Exact number (+unit, +SI dimension) or text. Exactly one of the two."""

    number: Decimal | None = None
    unit: str = ""
    dimension: tuple[int, ...] = ()
    text: str | None = None

    def __post_init__(self):
        if (self.number is None) == (self.text is None):
            raise _invalid("INVALID_VALUE", "a value is either a number or a text")
        if self.text is not None:
            _text(self.text, "text value")
            if self.unit or self.dimension:
                raise _invalid("INVALID_VALUE", "a text value has no unit or dimension")
            return
        if isinstance(self.number, bool) or not isinstance(self.number, Decimal):
            raise _invalid("INVALID_VALUE", f"number must be Decimal, got {type(self.number).__name__}")
        if not self.number.is_finite():
            raise _invalid("INVALID_VALUE", "number must be finite")
        _, digits, exp = self.number.as_tuple()
        if len(digits) + abs(exp) > MAX_NUMBER_DIGITS:
            raise _invalid("TRACE_LIMIT", f"number needs more than {MAX_NUMBER_DIGITS} digits")
        _text(self.unit, "unit", MAX_NAME)
        if not isinstance(self.dimension, tuple) or self.dimension and (
                len(self.dimension) != 7 or any(isinstance(e, bool) or not isinstance(e, int) or not -64 <= e <= 64
                                                for e in self.dimension)):
            raise _invalid("INVALID_VALUE", "dimension must be () or 7 integer SI exponents in -64..64")

    @classmethod
    def of_text(cls, text: str) -> "TraceValue":
        return cls(text=text)

    @classmethod
    def of_number(cls, number: Decimal | int, unit: str = "", dimension: tuple[int, ...] = ()) -> "TraceValue":
        if isinstance(number, int) and not isinstance(number, bool):
            number = Decimal(number)
        return cls(number=number, unit=unit, dimension=dimension)

    @classmethod
    def of_quantity(cls, quantity) -> "TraceValue":
        """Exact value in its stated unit (``Quantity.value``, ``unit.display``, SI dimension)."""
        return cls(number=quantity.value, unit=quantity.unit.display, dimension=tuple(quantity.dimension))

    @property
    def is_number(self) -> bool:
        return self.number is not None


@dataclass(frozen=True)
class TraceCheck:
    what: str
    actual: TraceValue
    expected: TraceValue
    status: CheckStatus
    tolerance: TraceValue | None = None
    detail: str = ""

    def __post_init__(self):
        _text(self.what, "check.what", empty=False)
        for name, value in (("actual", self.actual), ("expected", self.expected)):
            if not isinstance(value, TraceValue):
                raise _invalid("INVALID_TRACE", f"check.{name} must be a TraceValue")
        if self.tolerance is not None and not isinstance(self.tolerance, TraceValue):
            raise _invalid("INVALID_TRACE", "check.tolerance must be a TraceValue or None")
        if not isinstance(self.status, CheckStatus):
            raise _invalid("INVALID_TRACE", f"check.status must be a CheckStatus, got {self.status!r}")
        _text(self.detail, "check.detail")


@dataclass(frozen=True)
class TraceError:
    """D2 failure record: code (AC-XXX-NNN), reason token, UI-safe message."""

    code: str
    reason: str
    message: str

    def __post_init__(self):
        if not isinstance(self.code, str) or not _CODE_RE.fullmatch(self.code):
            raise _invalid("INVALID_TRACE", f"error code {str(self.code)[:16]!r} is not a D2 code")
        if not isinstance(self.reason, str) or not _REASON_RE.fullmatch(self.reason):
            raise _invalid("INVALID_TRACE", f"error reason {str(self.reason)[:64]!r} is not a token")
        _text(self.message, "error.message")

    @classmethod
    def from_exception(cls, exc: BaseException) -> "TraceError":
        """Map through D2: the exception's own ``AC-*`` code, else AC-VAL-001 for
        value errors (e.g. ``UnitError``, ``EquationError``), else AC-APP-000."""
        code = exc.code if isinstance(exc, AcademicCoreError) else ""
        if not _CODE_RE.fullmatch(code):
            code = "AC-VAL-001" if isinstance(exc, (ValueError, ArithmeticError)) else "AC-APP-000"
        text = str(exc)
        head = text.split(":", 1)[0].strip()
        if _REASON_RE.fullmatch(head):
            reason, message = head, text.split(":", 1)[1].strip() if ":" in text else text
        else:
            reason = re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).upper()[:64]
            if not _REASON_RE.fullmatch(reason):
                reason = "EXECUTION_ERROR"
            message = text
        return cls(code, reason, safe_message(message or reason))


@dataclass(frozen=True)
class TraceEvent:
    event_id: str
    kind: EventKind
    title: str
    refs: tuple[str, ...] = ()
    formula: str | None = None
    why: str | None = None
    values: tuple[tuple[str, TraceValue], ...] = ()
    result: TraceValue | None = None
    check: TraceCheck | None = None
    error: TraceError | None = None

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not _ID_RE.fullmatch(self.event_id):
            raise _invalid("INVALID_ID", f"event id {str(self.event_id)[:16]!r} must be e1, e2, …")
        if not isinstance(self.kind, EventKind):
            raise _invalid("INVALID_TRACE", f"kind must be an EventKind, got {self.kind!r}")
        _text(self.title, "title", empty=False)
        if not isinstance(self.refs, tuple) or len(self.refs) > MAX_REFS:
            raise _invalid("TRACE_LIMIT" if isinstance(self.refs, tuple) else "INVALID_TRACE",
                           f"refs must be a tuple of at most {MAX_REFS} event ids")
        for r in self.refs:
            if not isinstance(r, str) or not _ID_RE.fullmatch(r):
                raise _invalid("INVALID_REF", f"bad reference {str(r)[:16]!r}")
        if len(set(self.refs)) != len(self.refs):
            raise _invalid("INVALID_REF", f"{self.event_id} references an event twice")
        for name, value in (("formula", self.formula), ("why", self.why)):
            if value is not None:
                _text(value, name, empty=False)
        if not isinstance(self.values, tuple) or len(self.values) > MAX_VALUES:
            raise _invalid("TRACE_LIMIT" if isinstance(self.values, tuple) else "INVALID_TRACE",
                           f"values must be a tuple of at most {MAX_VALUES} (name, TraceValue) pairs")
        seen = set()
        for item in self.values:
            if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[1], TraceValue):
                raise _invalid("INVALID_TRACE", "each value must be a (name, TraceValue) pair")
            _name(item[0], "value name")
            if item[0] in seen:
                raise _invalid("INVALID_TRACE", f"{self.event_id} repeats value {item[0]!r}")
            seen.add(item[0])
        if self.result is not None and not isinstance(self.result, TraceValue):
            raise _invalid("INVALID_TRACE", "result must be a TraceValue or None")
        if (self.kind is EventKind.CHECK) != isinstance(self.check, TraceCheck) or (
                self.check is not None and not isinstance(self.check, TraceCheck)):
            raise _invalid("INVALID_TRACE", f"{self.event_id}: a CHECK event (and only it) carries a TraceCheck")
        if (self.kind is EventKind.ERROR) != isinstance(self.error, TraceError) or (
                self.error is not None and not isinstance(self.error, TraceError)):
            raise _invalid("INVALID_TRACE", f"{self.event_id}: an ERROR event (and only it) carries a TraceError")
        if self.kind is EventKind.RESULT and self.result is None:
            raise _invalid("INVALID_TRACE", f"{self.event_id}: a RESULT event needs a result")

    def value(self, name: str) -> TraceValue:
        for n, v in self.values:
            if n == name:
                return v
        raise _invalid("UNKNOWN_VALUE", f"{self.event_id} has no value {name!r}")


@dataclass(frozen=True)
class Verification:
    status: VerificationStatus
    checks: int
    failed: int

    def __post_init__(self):
        if not isinstance(self.status, VerificationStatus):
            raise _invalid("INVALID_TRACE", "verification.status must be a VerificationStatus")
        for name, v in (("checks", self.checks), ("failed", self.failed)):
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_EVENTS:
                raise _invalid("INVALID_TRACE", f"verification.{name} must be 0..{MAX_EVENTS}")

    @classmethod
    def of(cls, events) -> "Verification":
        checks = [e.check for e in events if e.kind is EventKind.CHECK]
        failed = sum(1 for c in checks if c.status is CheckStatus.FAIL)
        applicable = sum(1 for c in checks if c.status is not CheckStatus.NOT_APPLICABLE)
        status = (VerificationStatus.FAIL if failed else
                  VerificationStatus.PASS if applicable else VerificationStatus.NONE)
        return cls(status, len(checks), failed)


@dataclass(frozen=True)
class ExecutionTrace:
    """Immutable record of one real execution (``execution-trace/1``)."""

    operation: str
    inputs: tuple[tuple[str, TraceValue], ...]
    events: tuple[TraceEvent, ...]
    result: TraceValue | None
    outcome: Outcome
    verification: Verification
    metadata: tuple[tuple[str, str], ...] = field(default=())

    schema = SCHEMA
    version = VERSION

    def __post_init__(self):
        if not isinstance(self.operation, str) or not _OPERATION_RE.fullmatch(self.operation):
            raise _invalid("INVALID_TRACE", f"operation {str(self.operation)[:64]!r} must match "
                           f"{_OPERATION_RE.pattern}")
        if not isinstance(self.inputs, tuple) or len(self.inputs) > MAX_INPUTS:
            raise _invalid("TRACE_LIMIT", f"inputs must be a tuple of at most {MAX_INPUTS}")
        names = []
        for item in self.inputs:
            if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[1], TraceValue):
                raise _invalid("INVALID_TRACE", "each input must be a (name, TraceValue) pair")
            names.append(_name(item[0], "input name"))
        if len(set(names)) != len(names):
            raise _invalid("INVALID_TRACE", "input names must be unique")
        if not isinstance(self.events, tuple) or not all(isinstance(e, TraceEvent) for e in self.events):
            raise _invalid("INVALID_TRACE", "events must be a tuple of TraceEvent")
        if len(self.events) > MAX_EVENTS:
            raise _invalid("TRACE_LIMIT", f"more than {MAX_EVENTS} events")
        position = {}
        for k, e in enumerate(self.events):
            if e.event_id != f"e{k + 1}":
                raise _invalid("INVALID_ORDER", f"event #{k + 1} has id {e.event_id!r}; ids follow emission order")
            for r in e.refs:
                if r not in position:
                    raise _invalid("INVALID_REF", f"{e.event_id} references {r!r}, which is not an earlier event")
            position[e.event_id] = k
        inputs = dict(self.inputs)
        input_events = [e for e in self.events if e.kind is EventKind.INPUT]
        if len(input_events) != len(self.inputs):
            raise _invalid("INVALID_TRACE", "every input needs exactly one INPUT event")
        for e in input_events:
            if len(e.values) != 1 or inputs.get(e.values[0][0]) != e.values[0][1]:
                raise _invalid("INVALID_TRACE", f"{e.event_id}: INPUT event disagrees with the inputs")
        results = [e for e in self.events if e.kind is EventKind.RESULT]
        errors = [e for e in self.events if e.kind is EventKind.ERROR]
        if not isinstance(self.outcome, Outcome):
            raise _invalid("INVALID_TRACE", f"outcome must be an Outcome, got {self.outcome!r}")
        if self.outcome is Outcome.SUCCESS:
            if errors or len(results) != 1:
                raise _invalid("INVALID_TRACE", "SUCCESS needs exactly one RESULT event and no ERROR")
            if self.result != results[0].result:
                raise _invalid("INVALID_TRACE", "result disagrees with the RESULT event")
        else:
            if not errors or results or self.result is not None:
                raise _invalid("INVALID_TRACE", "FAILED needs an ERROR event, no RESULT and no result")
        if not isinstance(self.verification, Verification) or self.verification != Verification.of(self.events):
            raise _invalid("INVALID_TRACE", "verification summary disagrees with the CHECK events")
        if not isinstance(self.metadata, tuple) or len(self.metadata) > MAX_METADATA:
            raise _invalid("TRACE_LIMIT", f"metadata must be a tuple of at most {MAX_METADATA} pairs")
        keys = []
        for item in self.metadata:
            if not isinstance(item, tuple) or len(item) != 2:
                raise _invalid("INVALID_TRACE", "metadata items must be (key, text) pairs")
            keys.append(_name(item[0], "metadata key"))
            _text(item[1], "metadata value")
        if keys != sorted(set(keys)):
            raise _invalid("INVALID_TRACE", "metadata keys must be unique and sorted")

    # -- navigation (read-only; answers "who produced / who consumed") --------
    def event(self, event_id: str) -> TraceEvent:
        if isinstance(event_id, str) and _ID_RE.fullmatch(event_id):
            k = int(event_id[1:]) - 1
            if k < len(self.events):
                return self.events[k]
        raise _invalid("UNKNOWN_EVENT", f"no event {str(event_id)[:16]!r}")

    def consumers(self, event_id: str) -> tuple[str, ...]:
        self.event(event_id)
        return tuple(e.event_id for e in self.events if event_id in e.refs)

    def checks(self) -> tuple[TraceEvent, ...]:
        return tuple(e for e in self.events if e.kind is EventKind.CHECK)

    # -- execution-trace/1 (implementation in codec.py) ------------------------
    def to_dict(self) -> dict:
        from academic_core.domain.execution.codec import trace_to_dict

        return trace_to_dict(self)

    def to_json(self) -> str:
        from academic_core.domain.execution.codec import trace_to_json

        return trace_to_json(self)

    def digest(self) -> str:
        from academic_core.domain.execution.codec import trace_digest

        return trace_digest(self)

    @classmethod
    def from_dict(cls, data: object) -> "ExecutionTrace":
        from academic_core.domain.execution.codec import trace_from_dict

        return trace_from_dict(data)

    @classmethod
    def from_json(cls, text: object) -> "ExecutionTrace":
        from academic_core.domain.execution.codec import trace_from_json

        return trace_from_json(text)


class TraceRecorder:
    """Collects facts while a resolver really runs; ``finish()`` freezes them.

    It is only a builder. Every fact is validated when it is added, and
    again when the ``ExecutionTrace`` is built.
    """

    def __init__(self, operation: str):
        if not isinstance(operation, str) or not _OPERATION_RE.fullmatch(operation):
            raise _invalid("INVALID_TRACE", f"operation {str(operation)[:64]!r} must match {_OPERATION_RE.pattern}")
        self.operation = operation
        self._inputs: list[tuple[str, TraceValue]] = []
        self._events: list[TraceEvent] = []
        self._metadata: dict[str, str] = {}

    @property
    def last(self) -> str | None:
        return self._events[-1].event_id if self._events else None

    def event(self, kind: EventKind, title: str, *, refs=(), formula=None, why=None, values=(),
              result=None, check=None, error=None) -> str:
        if len(self._events) >= MAX_EVENTS:
            raise _invalid("TRACE_LIMIT", f"more than {MAX_EVENTS} events")
        event = TraceEvent(f"e{len(self._events) + 1}", kind, title, tuple(refs), formula, why,
                           tuple(values), result, check, error)
        known = {e.event_id for e in self._events}
        for r in event.refs:
            if r not in known:
                raise _invalid("INVALID_REF", f"{event.event_id} references {r!r}, which is not an earlier event")
        self._events.append(event)
        return event.event_id

    def input(self, name: str, value: TraceValue, title: str | None = None) -> str:
        if len(self._inputs) >= MAX_INPUTS:
            raise _invalid("TRACE_LIMIT", f"more than {MAX_INPUTS} inputs")
        _name(name, "input name")
        if any(n == name for n, _ in self._inputs):
            raise _invalid("INVALID_TRACE", f"input {name!r} recorded twice")
        eid = self.event(EventKind.INPUT, title or f"Entrada {name}", values=((name, value),))
        self._inputs.append((name, value))
        return eid

    def check(self, what: str, actual: TraceValue, expected: TraceValue, passed: bool | None, *,
              refs=(), tolerance: TraceValue | None = None, detail: str = "", title: str | None = None) -> str:
        status = CheckStatus.NOT_APPLICABLE if passed is None else CheckStatus.PASS if passed else CheckStatus.FAIL
        return self.event(EventKind.CHECK, title or f"Comprobación: {what}", refs=refs,
                          check=TraceCheck(what, actual, expected, status, tolerance, detail))

    def fail(self, exc: BaseException, title: str, *, refs=()) -> str:
        return self.event(EventKind.ERROR, title, refs=refs, error=TraceError.from_exception(exc))

    def metadata(self, key: str, value: str) -> None:
        _name(key, "metadata key")
        self._metadata[key] = _text(value, "metadata value")

    def finish(self) -> ExecutionTrace:
        events = tuple(self._events)
        results = [e for e in events if e.kind is EventKind.RESULT]
        failed = any(e.kind is EventKind.ERROR for e in events)
        return ExecutionTrace(
            self.operation, tuple(self._inputs), events,
            None if failed or len(results) != 1 else results[0].result,
            Outcome.FAILED if failed else Outcome.SUCCESS,
            Verification.of(events),
            tuple(sorted(self._metadata.items())))
