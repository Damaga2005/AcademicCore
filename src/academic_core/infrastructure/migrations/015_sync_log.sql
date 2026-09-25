-- 015: F13-ext sync log + state. Additive only.
-- No F4.x table is touched. sync_state tracks per-resource versioning
-- without altering existing tables; sync_log is append-only audit.

CREATE TABLE IF NOT EXISTS sync_state (
    resource_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    version_ms INTEGER NOT NULL,
    version_device TEXT NOT NULL,
    digest TEXT NOT NULL,
    updated_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    event_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL,
    local_version TEXT NOT NULL,
    remote_version TEXT NOT NULL,
    winner TEXT NOT NULL,
    conflict INTEGER NOT NULL,
    result TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    digest_before TEXT NOT NULL DEFAULT '',
    digest_after TEXT NOT NULL DEFAULT '',
    protocol_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_log_resource
    ON sync_log(resource_id, timestamp_ms);
