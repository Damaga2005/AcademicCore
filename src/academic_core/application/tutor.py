# SPDX-License-Identifier: MIT
"""F12 Socratic tutor service (application): orchestrates, never authorizes.

Context (F9 evidence, F10 mastery snapshot, F11 plan) is passed in
already resolved by the caller -- this service never recomputes mastery,
never re-plans, and never re-corrects; it only asks an ``LLMProvider``
for a structured proposal, validates/verifies it against the existing
F9 solver (``domain.tutor``), and persists the minimal verified record.
"""

from __future__ import annotations

import json

from academic_core.domain import tutor as T
from academic_core.errors import AcademicCoreError
from academic_core.infrastructure.llm import LLMRequest

SYSTEM_POLICY = (
    "Eres un tutor socratico. Nunca reveles la solucion completa salvo "
    "que la etapa de la politica lo permita explicitamente. Responde "
    "EXCLUSIVAMENTE con un objeto JSON valido segun el schema indicado; "
    "no incluyas texto fuera del JSON."
)


class TutorService:
    def __init__(self, provider, tutor_repo):
        self.provider = provider
        self.repo = tutor_repo

    def get_response(self, *, student_id: str, question: object,
                      question_digest: str,
                      attempt_evidence: dict | None = None,
                      mastery_snapshot: dict | None = None,
                      adaptive_plan: dict | None = None,
                      now_ms: int = 0) -> T.VerifiedResponse:
        turn_index = self.repo.turn_count(student_id, question_digest)
        stage = T.policy_stage(turn_index)
        meta = self.provider.metadata()
        if not meta.available:
            response = self._static_response(attempt_evidence, "LLM_UNAVAILABLE")
            self._persist(student_id, question_digest, turn_index, response,
                          meta.provider, meta.model, now_ms)
            return response

        request = LLMRequest(
            system_policy=SYSTEM_POLICY,
            context=self._build_context(question, attempt_evidence,
                                        mastery_snapshot, adaptive_plan),
            task=f"Socratic stage: {stage}. Guide the student without "
                 f"skipping ahead of this stage.")
        raw = self.provider.generate(request)
        if not raw.available:
            response = self._static_response(attempt_evidence, raw.error_code)
            self._persist(student_id, question_digest, turn_index, response,
                          raw.provider, raw.model, now_ms)
            return response

        response = self._validate_and_verify(raw.raw_text, question, stage)
        self._persist(student_id, question_digest, turn_index, response,
                      raw.provider, raw.model, now_ms)
        return response

    def _validate_and_verify(self, raw_text: str, question: object,
                              stage: str) -> T.VerifiedResponse:
        try:
            payload = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return T.VerifiedResponse(status="rejected", response_type="refusal",
                                      message="INVALID_LLM_OUTPUT", steps=(),
                                      evidence=())
        try:
            proposal = T.parse_proposal(payload)
            return T.build_response(proposal, question, stage)
        except AcademicCoreError as e:
            token = ("SAFETY_REJECTED" if getattr(e, "code", "") == "AC-TUT-004"
                     else "SCHEMA_VALIDATION_FAILED")
            return T.VerifiedResponse(status="rejected", response_type="refusal",
                                      message=token, steps=(), evidence=())

    def _build_context(self, question, attempt_evidence, mastery_snapshot,
                        adaptive_plan) -> str:
        body = {
            "question_id": getattr(question, "question_id", ""),
            "qtype": getattr(question, "qtype", ""),
            "attempt_evidence": attempt_evidence or {},
            "mastery_snapshot": mastery_snapshot or {},
            "adaptive_plan": adaptive_plan or {},
        }
        return json.dumps(body, ensure_ascii=False, sort_keys=True)

    def _static_response(self, attempt_evidence: dict | None,
                          error_code: str) -> T.VerifiedResponse:
        """LLM=OFF / provider failure: safe, verifiable, no invented content."""
        reason = (attempt_evidence or {}).get("reason", "")
        message = ("Revisa el concepto asociado a esta pregunta"
                   + (f" (motivo del intento anterior: {reason})" if reason else "")
                   + ". Vuelve a intentarlo paso a paso.")
        return T.VerifiedResponse(status="verified", response_type="hint",
                                  message=message, steps=(), evidence=(),
                                  provider_error=error_code)

    def _persist(self, student_id: str, question_digest: str, turn_index: int,
                response: T.VerifiedResponse, provider_name: str,
                provider_model: str, now_ms: int) -> str:
        digest = T.turn_digest(student_id, question_digest, turn_index, response)
        self.repo.save_turn(
            turn_id=digest, student_id=student_id,
            question_digest=question_digest, turn_index=turn_index,
            response_type=response.response_type, status=response.status,
            solver_version=response.solver_version,
            schema_version=response.schema_version,
            provider_name=provider_name, provider_model=provider_model,
            provider_error=response.provider_error, created_at_ms=now_ms)
        return digest
