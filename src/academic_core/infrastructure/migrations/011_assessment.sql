-- 011: F9 Assessment subsystem persistence (additive): assessments,
-- assessment_sessions, assessment_responses, assessment_results.
-- Exact Decimal values travel as TEXT. Zero float conversion.

CREATE TABLE IF NOT EXISTS assessments (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  items_json TEXT NOT NULL,
  duration_min INTEGER NOT NULL DEFAULT 0,
  attempts_allowed INTEGER NOT NULL DEFAULT 1,
  policy_json TEXT NOT NULL,
  shuffle_items INTEGER NOT NULL DEFAULT 0,
  master_seed INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_sessions (
  stable_id TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL REFERENCES assessments(stable_id),
  student_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  expires_at TEXT,
  submitted_at TEXT,
  item_order_json TEXT NOT NULL,
  seed_used INTEGER,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_responses (
  session_id TEXT NOT NULL REFERENCES assessment_sessions(stable_id) ON DELETE CASCADE,
  item_id TEXT NOT NULL,
  answer TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  PRIMARY KEY (session_id, item_id)
);

CREATE TABLE IF NOT EXISTS assessment_results (
  session_id TEXT PRIMARY KEY REFERENCES assessment_sessions(stable_id) ON DELETE CASCADE,
  assessment_id TEXT NOT NULL,
  student_id TEXT NOT NULL,
  total_score TEXT NOT NULL,
  max_possible TEXT NOT NULL,
  percentage TEXT NOT NULL,
  passed INTEGER NOT NULL,
  item_scores_json TEXT NOT NULL,
  evaluated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assessments_subject ON assessments(subject_id);
CREATE INDEX IF NOT EXISTS idx_sessions_assessment ON assessment_sessions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student ON assessment_sessions(student_id);

-- Enforce terminal session protection at database engine level:
CREATE TRIGGER IF NOT EXISTS trg_prevent_response_on_terminal_session
BEFORE INSERT ON assessment_responses
FOR EACH ROW
WHEN (SELECT status FROM assessment_sessions WHERE stable_id = NEW.session_id) IN ('SUBMITTED', 'EXPIRED', 'CANCELLED')
BEGIN
  SELECT RAISE(ABORT, 'Cannot record response: session is in terminal status');
END;

-- Enforce student response immutability at database engine level:
CREATE TRIGGER IF NOT EXISTS trg_response_immutable
BEFORE UPDATE ON assessment_responses
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'StudentResponse is immutable and cannot be updated');
END;

-- Enforce assessment result immutability at database engine level:
CREATE TRIGGER IF NOT EXISTS trg_result_immutable
BEFORE UPDATE ON assessment_results
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'AssessmentResult is immutable and cannot be updated');
END;
