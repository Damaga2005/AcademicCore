# SPDX-License-Identifier: MIT
"""F12 Socratic tutor contracts (domain, pure).

Axiom (binding, see F12-SOCRATIC-TUTOR.md)::

    LLM = asistencia | Validator = control | Solver = autoridad
    Verification = verdad academica

The only claim verifier is the existing F9 comparator
(``academic_core.domain.correction.correct_answer``), which already
dispatches all seven D6 ``qtype`` values. F12 owns no second evaluation
engine: a claim's ``answer`` payload is shaped exactly like an F9 answer
and is corrected the same way a student's answer would be.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from academic_core.domain import question_bank as QB
from academic_core.domain.correction import correct_answer
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicCoreError

TUTOR_SCHEMA = "f12-tutor-response/1"
TURN_TAG = "f12-tutor-turn/1"

RESPONSE_TYPES = (
    "hint", "question", "explanation",
    "verification_request", "correction_guidance", "refusal",
)

# Socratic reveal ladder (prompt §10): earlier stages may never carry a
# final-answer claim. Stage is derived from how many prior turns this
# (student, question) pair already has -- no separate policy state store.
SOCRATIC_LADDER = (
    "question", "hint", "smaller_hint",
    "targeted_question", "partial_explanation", "full_solution",
)

STATUSES = ("verified", "unverified", "rejected")

MAX_MESSAGE = 2000
MAX_STEPS = 20
MAX_STEP_LEN = 500
MAX_CLAIMS = 10


def _dom(msg: str) -> DomainError:
    return DomainError(msg, code="AC-DOM-001")


@dataclass(frozen=True)
class Claim:
    """One verifiable academic assertion inside a tutor proposal."""

    claim_type: str  # only "final_answer" is routed to a solver in F12
    qtype: str
    answer: dict
    verification_required: bool = True

    def __post_init__(self) -> None:
        if self.claim_type != "final_answer":
            raise _dom(f"unknown claim_type: {self.claim_type!r}")
        if self.qtype not in QB.QUESTION_TYPES:
            raise _dom(f"bad qtype: {self.qtype!r}")
        if not isinstance(self.answer, dict):
            raise _dom("claim answer must be a dict")
        if not isinstance(self.verification_required, bool):
            raise _dom("verification_required must be bool")


@dataclass(frozen=True)
class TutorProposal:
    """LLM output after schema/type/size validation (not yet verified)."""

    schema_version: str
    response_type: str
    message: str
    steps: tuple
    claims: tuple

    def __post_init__(self) -> None:
        if self.schema_version != TUTOR_SCHEMA:
            raise _dom(f"unsupported schema_version: {self.schema_version!r}")
        if self.response_type not in RESPONSE_TYPES:
            raise _dom(f"unknown response_type: {self.response_type!r}")
        if not isinstance(self.message, str) or not self.message.strip():
            raise _dom("message must be non-empty text")
        if len(self.message) > MAX_MESSAGE:
            raise _dom("message exceeds size limit")
        if len(self.steps) > MAX_STEPS:
            raise _dom("too many steps")
        for s in self.steps:
            if not isinstance(s, str) or not s or len(s) > MAX_STEP_LEN:
                raise _dom("bad step text")
        if len(self.claims) > MAX_CLAIMS:
            raise _dom("too many claims")


@dataclass(frozen=True)
class VerifiedResponse:
    """The only object a caller may present as the tutor's answer."""

    status: str  # verified | unverified | rejected
    response_type: str
    message: str
    steps: tuple
    evidence: tuple  # ((claim_index, reason, is_correct|None), ...)
    schema_version: str = TUTOR_SCHEMA
    solver_version: str = "f9-correct/1"
    provider_error: str = ""  # LLM_UNAVAILABLE | LLM_TIMEOUT | PROVIDER_ERROR

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise _dom(f"bad status: {self.status!r}")


def parse_proposal(raw: object) -> TutorProposal:
    """Strict schema validation. Reject unknown/missing/mistyped fields."""
    if not isinstance(raw, dict):
        raise _dom("proposal must be a JSON object")
    allowed = {"schema_version", "response_type", "message", "steps", "claims"}
    required = {"schema_version", "response_type", "message"}
    keys = set(raw)
    if keys - allowed:
        raise _dom(f"unknown fields: {sorted(keys - allowed)}")
    if required - keys:
        raise _dom(f"missing fields: {sorted(required - keys)}")
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        raise _dom("steps must be a list")
    claims_raw = raw.get("claims", [])
    if not isinstance(claims_raw, list):
        raise _dom("claims must be a list")
    claims = tuple(_claim_from_dict(c) for c in claims_raw)
    return TutorProposal(
        schema_version=raw["schema_version"], response_type=raw["response_type"],
        message=raw["message"], steps=tuple(steps), claims=claims)


def _claim_from_dict(c: object) -> Claim:
    if not isinstance(c, dict):
        raise _dom("claim must be a JSON object")
    allowed = {"claim_type", "qtype", "answer", "verification_required"}
    if set(c) - allowed:
        raise _dom(f"unknown claim fields: {sorted(set(c) - allowed)}")
    if not {"claim_type", "qtype", "answer"} <= set(c):
        raise _dom("claim missing required fields")
    return Claim(claim_type=c["claim_type"], qtype=c["qtype"],
                answer=c["answer"],
                verification_required=c.get("verification_required", True))


def policy_stage(attempts_so_far: int) -> str:
    """Deterministic stage from prior-turn count. No mutable policy state."""
    idx = min(max(attempts_so_far, 0), len(SOCRATIC_LADDER) - 1)
    return SOCRATIC_LADDER[idx]


def allows_final_claim(stage: str) -> bool:
    return SOCRATIC_LADDER.index(stage) >= SOCRATIC_LADDER.index("partial_explanation")


def enforce_policy(proposal: TutorProposal, stage: str) -> None:
    """Refuse a final-answer claim earlier than the ladder allows."""
    if not allows_final_claim(stage) and any(
            c.claim_type == "final_answer" for c in proposal.claims):
        raise DomainError(
            f"policy forbids a final_answer claim at stage {stage!r}",
            code="AC-TUT-004")


def verify_claims(question: object, claims: tuple[Claim, ...]) -> tuple[str, tuple]:
    """Route every claim through the existing F9 comparator (no new engine).

    verdict.is_correct True/False/None maps to verified/rejected/unverified;
    the worst outcome across claims wins (a single false claim rejects the
    whole response; an unresolvable one only downgrades to unverified).
    """
    if not claims:
        return "verified", ()
    order = {"verified": 0, "unverified": 1, "rejected": 2}
    worst = "verified"
    evidence = []
    for i, c in enumerate(claims):
        if not c.verification_required:
            evidence.append((i, "skipped", None))
            continue
        try:
            verdict = correct_answer(question, c.answer)
        except AcademicCoreError as e:
            evidence.append((i, f"malformed_claim:{e}", False))
            worst = "rejected"
            continue
        evidence.append((i, verdict.reason, verdict.is_correct))
        status = ("verified" if verdict.is_correct is True else
                  "unverified" if verdict.is_correct is None else "rejected")
        if order[status] > order[worst]:
            worst = status
    return worst, tuple(evidence)


def build_response(proposal: TutorProposal, question: object,
                    stage: str) -> VerifiedResponse:
    """Authority chain: proposal -> policy -> solver verification -> result."""
    enforce_policy(proposal, stage)
    if proposal.response_type == "refusal":
        status, evidence = "verified", ()  # asserts nothing to verify
    else:
        status, evidence = verify_claims(question, proposal.claims)
    return VerifiedResponse(status=status, response_type=proposal.response_type,
                            message=proposal.message, steps=proposal.steps,
                            evidence=evidence)


def turn_digest(student_id: str, question_digest: str, turn_index: int,
                response: VerifiedResponse) -> str:
    """Reproducible id for one persisted turn (no timestamps inside)."""
    body = QB.dumps_canonical({
        "student_id": student_id, "question_digest": question_digest,
        "turn_index": turn_index, "status": response.status,
        "response_type": response.response_type,
        "message": response.message,
    })
    raw = body.encode("utf-8")
    return hashlib.sha256(TURN_TAG.encode() + b"\x00" + raw).hexdigest()
