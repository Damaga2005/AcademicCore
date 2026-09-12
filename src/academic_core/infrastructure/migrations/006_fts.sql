-- 006: FTS5 derived index over extracted text (rebuildable, never canonical).
-- Plain content table (not external-content): rebuilds stay explicit and auditable.
CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
  stable_id UNINDEXED, kind UNINDEXED, title, body, tokenize='unicode61');
