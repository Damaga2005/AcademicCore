-- 008: F4 academic management (additive ONLY over F3 bases; defaults keep
-- existing rows readable; no table is dropped or recreated).
ALTER TABLE academic_years ADD COLUMN state TEXT NOT NULL DEFAULT 'pendiente';
ALTER TABLE terms ADD COLUMN state TEXT NOT NULL DEFAULT 'pendiente';
ALTER TABLE topics ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN location TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN link TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN reminder_days INTEGER;
ALTER TABLE exams ADD COLUMN status TEXT NOT NULL DEFAULT 'planned';
ALTER TABLE exams ADD COLUMN weight TEXT;
ALTER TABLE exams ADD COLUMN score TEXT;
ALTER TABLE exams ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'planned';
ALTER TABLE projects ADD COLUMN weight TEXT;
ALTER TABLE projects ADD COLUMN score TEXT;
ALTER TABLE projects ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE labs ADD COLUMN day TEXT;
ALTER TABLE labs ADD COLUMN status TEXT NOT NULL DEFAULT 'planned';
ALTER TABLE labs ADD COLUMN score TEXT;
ALTER TABLE labs ADD COLUMN notes TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS gradebook (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  scale_kind TEXT NOT NULL,
  scale_low TEXT NOT NULL DEFAULT '0',
  scale_high TEXT NOT NULL DEFAULT '10',
  letters TEXT NOT NULL DEFAULT '[]',
  weight TEXT NOT NULL,
  optional INTEGER NOT NULL DEFAULT 0,
  date TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  UNIQUE (subject_id, key));
CREATE TABLE IF NOT EXISTS prerequisites (
  subject_id TEXT NOT NULL,
  requires_id TEXT NOT NULL,
  PRIMARY KEY (subject_id, requires_id));
