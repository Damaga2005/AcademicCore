-- 018: F10 mastery states + observations. Additive only.
-- No certified table is touched. mastery_states materializes posteriors
-- per (student, level, ref); mastery_observations is the append-only
-- evidence set that rebuilds them (INSERT OR IGNORE by PK = idempotent
-- and concurrent-double-apply safe).

CREATE TABLE IF NOT EXISTS mastery_states (
    student_id TEXT NOT NULL,
    level TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    alpha TEXT NOT NULL,
    beta TEXT NOT NULL,
    model_version TEXT NOT NULL,
    config_version INTEGER NOT NULL,
    obs_count INTEGER NOT NULL,
    members_json TEXT NOT NULL DEFAULT '[]',
    updated_at_ms INTEGER NOT NULL,
    PRIMARY KEY (student_id, level, ref_id)
);

CREATE TABLE IF NOT EXISTS mastery_observations (
    student_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    concept_ref TEXT NOT NULL,
    topic_ref TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    alpha_delta TEXT NOT NULL,
    beta_delta TEXT NOT NULL,
    obs_digest TEXT NOT NULL,
    question_digest TEXT NOT NULL,
    engine TEXT NOT NULL,
    applied_at_ms INTEGER NOT NULL,
    PRIMARY KEY (student_id, session_id, item_id, concept_ref)
);

CREATE INDEX IF NOT EXISTS idx_mastery_obs_concept
    ON mastery_observations(student_id, concept_ref);
