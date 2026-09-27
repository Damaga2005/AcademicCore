-- 020: F12 Socratic tutor turns. Additive only.
-- No certified table is touched. tutor_turns is an append-only audit log
-- of VERIFIED tutor responses only -- no raw LLM text, no intermediate
-- proposal (see F12-SOCRATIC-TUTOR.md). Immutable via trigger, matching
-- the pattern already used by assessment_evidence (017).

CREATE TABLE IF NOT EXISTS tutor_turns (
    turn_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    question_digest TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    response_type TEXT NOT NULL,
    status TEXT NOT NULL,
    solver_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    provider_model TEXT NOT NULL DEFAULT '',
    provider_error TEXT NOT NULL DEFAULT '',
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tutor_turns_student
    ON tutor_turns(student_id, question_digest, turn_index);

CREATE TRIGGER IF NOT EXISTS trg_tutor_turns_immutable
BEFORE UPDATE ON tutor_turns
BEGIN
    SELECT RAISE(ABORT, 'tutor turns are immutable');
END;
