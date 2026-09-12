-- 003: planning — assignments/exams/projects/labs/tasks/deadlines/series/refs.
CREATE TABLE IF NOT EXISTS assignments (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, title TEXT NOT NULL,
  requirements TEXT NOT NULL DEFAULT '', resources TEXT NOT NULL DEFAULT '[]',
  workspace TEXT NOT NULL DEFAULT '', files TEXT NOT NULL DEFAULT '[]',
  report_ref TEXT NOT NULL DEFAULT '', rubric TEXT NOT NULL DEFAULT '',
  submission TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft');
CREATE TABLE IF NOT EXISTS exams (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, title TEXT NOT NULL,
  day TEXT, duration_min INTEGER NOT NULL DEFAULT 0, session TEXT NOT NULL DEFAULT '',
  allowed_resources TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS projects (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', milestones TEXT NOT NULL DEFAULT '[]',
  links TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS labs (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tasks (
  stable_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'tarea_general', day TEXT, start TEXT NOT NULL DEFAULT '',
  end TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'media',
  state TEXT NOT NULL DEFAULT 'pendiente', notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS deadlines (
  id INTEGER PRIMARY KEY AUTOINCREMENT, target_id TEXT NOT NULL,
  due TEXT NOT NULL, label TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS schedule_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id TEXT NOT NULL,
  kind TEXT NOT NULL, weekday INTEGER NOT NULL, start TEXT NOT NULL,
  end TEXT NOT NULL, first_day TEXT NOT NULL, last_day TEXT NOT NULL,
  interval_weeks INTEGER NOT NULL DEFAULT 1, room TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS resource_refs (
  resource_id TEXT NOT NULL, subject_id TEXT NOT NULL,
  relationship TEXT NOT NULL DEFAULT 'material', title TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '', PRIMARY KEY (resource_id, subject_id));
