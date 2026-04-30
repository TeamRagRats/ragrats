CREATE TABLE IF NOT EXISTS retrieval_logging (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query           TEXT NOT NULL,
    source_types    TEXT[],
    top_k_1         INTEGER NOT NULL,
    top_k_2         INTEGER NOT NULL,
    winning_keys    TEXT[] NOT NULL,
    key_vote_counts JSONB,
    step1_ms        INTEGER,
    step2_ms        INTEGER,
    total_ms        INTEGER,
    chunks_returned INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
