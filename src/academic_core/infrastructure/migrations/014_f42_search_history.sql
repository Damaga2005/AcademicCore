-- 014: F4.2 search history (favourites + recents). Additive only.
-- No F4.1 table is touched. Rows are referenced by (kind, ref); stable ids
-- of the underlying entities live in their own tables.

CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    title TEXT NOT NULL,
    created TEXT NOT NULL,
    UNIQUE(kind, ref)
);

CREATE TABLE IF NOT EXISTS recent_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    accessed TEXT NOT NULL,
    UNIQUE(kind, ref)
);

CREATE INDEX IF NOT EXISTS idx_recent_searches_accessed
    ON recent_searches(accessed DESC, kind ASC, ref ASC);
