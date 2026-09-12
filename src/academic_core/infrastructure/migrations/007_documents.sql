-- 007: document derivations (Resource -> Document AST, value objects).
-- Keyed by (resource_id, resource_version, parser): a resource may hold
-- several derivations (html/md/pdf backends) without identity churn.
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  resource_id TEXT NOT NULL,
  resource_version INTEGER NOT NULL,
  parser TEXT NOT NULL,
  parser_version TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  ast_json TEXT NOT NULL,
  warnings TEXT NOT NULL DEFAULT '[]',
  UNIQUE (resource_id, resource_version, parser));
