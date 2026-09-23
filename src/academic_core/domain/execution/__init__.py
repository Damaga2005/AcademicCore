# SPDX-License-Identifier: MIT
"""E0 Explainable Execution: the transversal ``ExecutionTrace`` core (model, codec, replay).

Integrations live in submodules and are imported explicitly:
``execution.equation`` (engineering equation resolver) and
``execution.digital`` (F8-Q Logic Analyzer). Engines never import this
package, so there is no dependency cycle.
"""

from academic_core.domain.execution.codec import (
    MAX_DEPTH,
    MAX_ITEMS,
    MAX_JSON_BYTES,
    canonical_decimal,
    semantic_json,
)
from academic_core.domain.execution.model import (
    FORMAT,
    MAX_EVENTS,
    MAX_INPUTS,
    MAX_METADATA,
    MAX_NUMBER_DIGITS,
    MAX_REFS,
    MAX_STRING,
    MAX_VALUES,
    SCHEMA,
    VERSION,
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
)
from academic_core.domain.execution.verification import verification_kind
from academic_core.domain.execution.replay import (
    EQUIVALENT,
    RESULT_DIFFERS,
    ReplayReport,
    compare,
    first_difference,
    replay,
    verify_replay,
)

__all__ = [
    "EQUIVALENT",
    "FORMAT",
    "MAX_DEPTH",
    "MAX_EVENTS",
    "MAX_INPUTS",
    "MAX_ITEMS",
    "MAX_JSON_BYTES",
    "MAX_METADATA",
    "MAX_NUMBER_DIGITS",
    "MAX_REFS",
    "MAX_STRING",
    "MAX_VALUES",
    "RESULT_DIFFERS",
    "SCHEMA",
    "VERSION",
    "CheckStatus",
    "EventKind",
    "ExecutionTrace",
    "Outcome",
    "ReplayReport",
    "TraceCheck",
    "TraceError",
    "TraceEvent",
    "TraceRecorder",
    "TraceValue",
    "Verification",
    "VerificationStatus",
    "canonical_decimal",
    "compare",
    "first_difference",
    "verification_kind",
    "replay",
    "semantic_json",
    "verify_replay",
]
