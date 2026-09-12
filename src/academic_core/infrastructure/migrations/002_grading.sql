-- 002: grading records (Decimal values travel as TEXT; math stays in domain/).
CREATE TABLE IF NOT EXISTS grade_schemes (
  subject_id TEXT NOT NULL, scheme TEXT NOT NULL, final TEXT,
  PRIMARY KEY (subject_id, scheme));
CREATE TABLE IF NOT EXISTS grade_components (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id TEXT NOT NULL,
  scheme TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  weight TEXT NOT NULL, score TEXT, block TEXT);
