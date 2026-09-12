-- 005: resources — canonical metadata, versions (append-only), provenance.
CREATE TABLE IF NOT EXISTS resources (
  stable_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  current_version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS resource_versions (
  stable_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  size INTEGER NOT NULL,
  origin TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  original_filename TEXT NOT NULL DEFAULT '',
  imported_at TEXT NOT NULL,
  adapter TEXT NOT NULL DEFAULT '',
  adapter_version TEXT NOT NULL DEFAULT '',
  extraction_status TEXT NOT NULL DEFAULT 'ok',
  parent_version INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (stable_id, version));
CREATE INDEX IF NOT EXISTS idx_versions_hash ON resource_versions(content_hash);
