-- 019: F11 adaptive plans. Additive only.
-- No certified table is touched. adaptive_plans persists deterministic
-- practice plans (idempotent by plan_id = deterministic digest of the
-- inputs); selections/rationale are JSON snapshots for reproducibility.

CREATE TABLE IF NOT EXISTS adaptive_plans (
    plan_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    subject_id TEXT NOT NULL DEFAULT '',
    config_version INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    bank_digest TEXT NOT NULL,
    selections_json TEXT NOT NULL,
    rationale_json TEXT NOT NULL,
    mastery_snapshot_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    plan_digest TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_adaptive_plans_student
    ON adaptive_plans(student_id, created_at_ms);
