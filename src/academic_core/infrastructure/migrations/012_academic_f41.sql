-- 012: F4.1 academic management (ADDITIVE ONLY: no table dropped/recreated,
-- defaults keep every existing row readable). One database, no second DB.
-- Decimal values travel as TEXT; math stays in domain/.

-- subjects: Gestion parity fields
ALTER TABLE subjects ADD COLUMN final_grade TEXT;
ALTER TABLE subjects ADD COLUMN catalog_origin INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subjects ADD COLUMN scheme_rule TEXT NOT NULL DEFAULT 'maximo';
ALTER TABLE subjects ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE subjects ADD COLUMN notes_updated_at TEXT NOT NULL DEFAULT '';
ALTER TABLE subjects ADD COLUMN virtual_classroom TEXT NOT NULL DEFAULT '';
ALTER TABLE subjects ADD COLUMN extra TEXT NOT NULL DEFAULT '{}';

-- people
ALTER TABLE professors ADD COLUMN virtual_classroom TEXT NOT NULL DEFAULT '';
ALTER TABLE subject_staff ADD COLUMN ord INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subject_staff ADD COLUMN email TEXT NOT NULL DEFAULT '';
ALTER TABLE subject_staff ADD COLUMN office TEXT NOT NULL DEFAULT '';
ALTER TABLE subject_staff ADD COLUMN virtual_url TEXT NOT NULL DEFAULT '';

-- planning
ALTER TABLE tasks ADD COLUMN room TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN document_id TEXT NOT NULL DEFAULT '';
ALTER TABLE schedule_series ADD COLUMN stable_id TEXT NOT NULL DEFAULT '';
ALTER TABLE schedule_series ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE study_spaces ADD COLUMN stable_id TEXT NOT NULL DEFAULT '';
ALTER TABLE study_spaces ADD COLUMN created TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_subjects_term ON subjects(term_id);
CREATE INDEX IF NOT EXISTS idx_subjects_state ON subjects(state);
CREATE INDEX IF NOT EXISTS idx_tasks_day ON tasks(day);
CREATE INDEX IF NOT EXISTS idx_tasks_subject ON tasks(subject_id);
CREATE INDEX IF NOT EXISTS idx_series_stable ON schedule_series(stable_id);
CREATE INDEX IF NOT EXISTS idx_spaces_stable ON study_spaces(stable_id);
CREATE INDEX IF NOT EXISTS idx_refs_subject ON resource_refs(subject_id);

-- evaluation (schemes / blocks / components / minimum grade)
CREATE TABLE IF NOT EXISTS assessment_schemes (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  name TEXT NOT NULL,
  ord INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_schemes_subject ON assessment_schemes(subject_id);
CREATE TABLE IF NOT EXISTS assessment_blocks (
  stable_id TEXT PRIMARY KEY,
  scheme_id TEXT NOT NULL REFERENCES assessment_schemes(stable_id),
  name TEXT NOT NULL,
  weight TEXT NOT NULL,
  ord INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS assessment_components (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  scheme_id TEXT NOT NULL REFERENCES assessment_schemes(stable_id),
  block_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'otro',
  weight TEXT NOT NULL,
  score TEXT,
  min_grade TEXT,
  ord INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_components_scheme ON assessment_components(scheme_id);

-- course material (documents live in resources/CAS; this is the relation)
CREATE TABLE IF NOT EXISTS document_groups (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  ord INTEGER NOT NULL DEFAULT 0,
  UNIQUE (subject_id, category, name));
CREATE TABLE IF NOT EXISTS course_documents (
  subject_id TEXT NOT NULL,
  resource_id TEXT NOT NULL REFERENCES resources(stable_id),
  category TEXT NOT NULL DEFAULT 'otros',
  group_id TEXT NOT NULL DEFAULT '',
  filename TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  added_at TEXT NOT NULL DEFAULT '',
  legacy TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (subject_id, resource_id));
CREATE INDEX IF NOT EXISTS idx_course_documents_resource ON course_documents(resource_id);
CREATE TABLE IF NOT EXISTS reading_progress (
  resource_id TEXT PRIMARY KEY,
  last_page INTEGER,
  percent TEXT,
  zoom TEXT NOT NULL DEFAULT '',
  view_mode TEXT NOT NULL DEFAULT '',
  scroll TEXT,
  first_opened TEXT NOT NULL DEFAULT '',
  last_opened TEXT NOT NULL DEFAULT '',
  total_seconds INTEGER NOT NULL DEFAULT 0,
  sessions INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS document_pages (
  resource_id TEXT NOT NULL,
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (resource_id, page));
CREATE TABLE IF NOT EXISTS external_resources (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'other',
  ord INTEGER NOT NULL DEFAULT 0,
  provenance TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_external_subject ON external_resources(subject_id);

-- study-space selections (references, never copies)
CREATE TABLE IF NOT EXISTS study_space_documents (
  space_id TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  section TEXT NOT NULL,
  read INTEGER NOT NULL DEFAULT 0,
  highlighted INTEGER NOT NULL DEFAULT 0,
  ord INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (space_id, resource_id));
CREATE TABLE IF NOT EXISTS study_space_goals (
  space_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (space_id, ord));

-- personal planning
CREATE TABLE IF NOT EXISTS milestones (
  stable_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pendiente',
  day TEXT,
  ord INTEGER NOT NULL DEFAULT 0,
  subject_id TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS quick_notes (
  stable_id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS study_concepts (
  stable_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'no_visto',
  last_review TEXT,
  next_review TEXT);
CREATE TABLE IF NOT EXISTS activity_days (
  day TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL);

-- migration bookkeeping (idempotency + no-loss evidence)
CREATE TABLE IF NOT EXISTS legacy_map (
  source_system TEXT NOT NULL,
  source_table TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  PRIMARY KEY (source_system, source_table, source_id));
CREATE INDEX IF NOT EXISTS idx_legacy_target ON legacy_map(target_id);
CREATE TABLE IF NOT EXISTS legacy_payloads (
  source_system TEXT NOT NULL,
  source_table TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL DEFAULT '',
  deferred_to TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  PRIMARY KEY (source_system, source_table, source_id));
CREATE TABLE IF NOT EXISTS migration_runs (
  run_id TEXT PRIMARY KEY,
  source_system TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  report_digest TEXT NOT NULL,
  mode TEXT NOT NULL,
  started TEXT NOT NULL,
  finished TEXT NOT NULL,
  report TEXT NOT NULL);
