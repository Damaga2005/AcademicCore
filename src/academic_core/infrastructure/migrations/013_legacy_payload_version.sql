-- 013: F4.1 closure — legacy_payloads records which migrator version
-- preserved each row (additive; existing rows keep '' = pre-closure run).
ALTER TABLE legacy_payloads ADD COLUMN migration_version TEXT NOT NULL DEFAULT '';
