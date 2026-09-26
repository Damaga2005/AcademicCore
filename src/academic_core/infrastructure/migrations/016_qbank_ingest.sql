-- 016: D7 question-bank ingestion. Additive only.
-- No certified table is touched. qbank_banks/questions materialize D6 banks
-- (bank owns its question set); formulas persists academic.Formula rows
-- created from explicit D7 catalogs (no parallel Knowledge Core: concepts
-- keep living in study_concepts, resources in F2, documents in F3).

CREATE TABLE IF NOT EXISTS qbank_banks (
    bank_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content_version INTEGER NOT NULL,
    digest TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    provenance TEXT NOT NULL DEFAULT '{}',
    ingested_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS qbank_questions (
    question_id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL REFERENCES qbank_banks(bank_id),
    content_version INTEGER NOT NULL,
    digest TEXT NOT NULL,
    qtype TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_qbank_questions_bank
    ON qbank_questions(bank_id, question_id);

CREATE TABLE IF NOT EXISTS formulas (
    stable_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL DEFAULT '',
    latex TEXT NOT NULL,
    source_latex TEXT NOT NULL,
    concept_ids TEXT NOT NULL DEFAULT '[]',
    variables TEXT NOT NULL DEFAULT '[]',
    units TEXT NOT NULL DEFAULT '[]',
    provenance TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1
);
