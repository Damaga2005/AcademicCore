-- 017: F9 attempt snapshots + correction evidence. Additive only.
-- No certified table is touched. assessment_item_snapshots freezes the
-- examined questions per session (later bank edits never rewrite history);
-- assessment_evidence stores one deterministic CorrectionResult per
-- submitted item. Both are append-only (immutability triggers).

CREATE TABLE IF NOT EXISTS assessment_item_snapshots (
    session_id TEXT NOT NULL REFERENCES assessment_sessions(stable_id),
    item_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    content_version INTEGER NOT NULL,
    question_digest TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, item_id)
);

CREATE TABLE IF NOT EXISTS assessment_evidence (
    session_id TEXT NOT NULL REFERENCES assessment_sessions(stable_id),
    item_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    qtype TEXT NOT NULL,
    is_correct INTEGER NULL,
    ratio TEXT NULL,
    score TEXT NOT NULL,
    reason TEXT NOT NULL,
    engine TEXT NOT NULL,
    given_normalized TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_assessment_evidence_session
    ON assessment_evidence(session_id, item_id);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_immutable
BEFORE UPDATE ON assessment_item_snapshots
BEGIN
    SELECT RAISE(ABORT, 'assessment snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_evidence_immutable
BEFORE UPDATE ON assessment_evidence
BEGIN
    SELECT RAISE(ABORT, 'assessment evidence is immutable');
END;
