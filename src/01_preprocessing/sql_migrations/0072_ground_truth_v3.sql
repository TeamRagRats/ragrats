-- Ground truth v3: strategy-agnostic QA pairs keyed by (source_type, source_id, chunk_index).
-- Covers 6 categories: fact_single, summary, multi_context, reasoning, unanswerable, generic.
-- Keyed by source_id (email_id or sha256) so all embedding strategies share the same ground truth.

CREATE TABLE IF NOT EXISTS ground_truth_v3 (
    question_id  TEXT PRIMARY KEY,
    question     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    category     TEXT NOT NULL CHECK (category IN (
        'fact_single', 'summary', 'multi_context', 'reasoning',
        'unanswerable', 'generic'
    )),
    source_hint  TEXT,
    source_type  TEXT NOT NULL CHECK (source_type IN ('email', 'attachment')),
    source_id    TEXT NOT NULL,   -- email_id (UUID as text) or sha256
    chunk_index  INTEGER,         -- NULL for emails, N for attachment chunks
    voyage_key   TEXT NOT NULL,
    vessel_name  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gt_v3_voyage_idx ON ground_truth_v3 (voyage_key);
CREATE INDEX IF NOT EXISTS gt_v3_source_idx ON ground_truth_v3 (source_type, source_id);
