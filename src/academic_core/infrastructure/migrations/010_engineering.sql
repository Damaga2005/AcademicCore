-- 010: F6 engineering (additive): projects, circuits (canonical netlist),
-- calculations (digest-keyed, reproducible). Values travel as TEXT (Decimal).
CREATE TABLE IF NOT EXISTS engineering_projects (
  name TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL DEFAULT '',
  topic_id TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS circuits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project TEXT NOT NULL,
  name TEXT NOT NULL,
  netlist TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  UNIQUE (project, name));
CREATE TABLE IF NOT EXISTS calculations (
  digest TEXT PRIMARY KEY,
  project TEXT NOT NULL DEFAULT '',
  circuit TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  equation TEXT NOT NULL,
  inputs TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT NOT NULL,
  engine TEXT NOT NULL,
  timestamp TEXT NOT NULL);
