-- 001: academic hierarchy (forward-only; one concern per migration).
CREATE TABLE IF NOT EXISTS universities (
  stable_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS degrees (
  stable_id TEXT PRIMARY KEY, name TEXT NOT NULL, university_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS academic_years (
  stable_id TEXT PRIMARY KEY, label TEXT NOT NULL, degree_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terms (
  stable_id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL,
  idx INTEGER NOT NULL, academic_year_id TEXT NOT NULL,
  start TEXT, end TEXT);
CREATE TABLE IF NOT EXISTS subjects (
  stable_id TEXT PRIMARY KEY, code TEXT NOT NULL DEFAULT '', name TEXT NOT NULL,
  acronym TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
  credits REAL NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'obligatoria',
  course INTEGER NOT NULL DEFAULT 0, term_id TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'pendiente');
CREATE TABLE IF NOT EXISTS professors (
  stable_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
  office TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS subject_staff (
  subject_id TEXT NOT NULL, professor_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'docente',
  groups TEXT NOT NULL DEFAULT '', PRIMARY KEY (subject_id, professor_id));
CREATE TABLE IF NOT EXISTS topics (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL,
  idx TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS id_counters (
  kind TEXT PRIMARY KEY, last_n INTEGER NOT NULL DEFAULT 0);
