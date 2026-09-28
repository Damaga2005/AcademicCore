-- 021: F13 cloud sync status (offline-first). Additive only.
-- No certified table is touched. sync_status tracks runtime sync state per
-- resource (synced/pending/offline/conflict/error) WITHOUT contaminating
-- canonical digests. cloud_sync_meta stores last_sync_ms and anchors.

CREATE TABLE IF NOT EXISTS sync_status (
    resource_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_ms INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cloud_sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
