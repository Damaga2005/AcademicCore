-- 009: F5 authoring (additive): lifecycle per authored resource + academic links.
CREATE TABLE IF NOT EXISTS authored (
  resource_id TEXT PRIMARY KEY,
  lifecycle TEXT NOT NULL DEFAULT 'DRAFT',
  template TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS doc_links (
  resource_id TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  PRIMARY KEY (resource_id, target_kind, target_id));
