ALTER TABLE generation_logging DROP CONSTRAINT IF EXISTS generation_logging_retrieval_run_id_fkey;

CREATE TABLE retrieval_logging_new (
    query_id                 UUID PRIMARY KEY REFERENCES queries(query_id),
    query_text               TEXT NOT NULL,
    source_types             TEXT[],
    top_k_1                  INTEGER NOT NULL,
    top_k_2                  INTEGER NOT NULL,
    winning_keys             TEXT[] NOT NULL,
    key_vote_counts          JSONB,
    step1_ms                 INTEGER,
    step2_ms                 INTEGER,
    total_ms                 INTEGER,
    chunks_returned          INTEGER,
    chunks                   JSONB,
    chunks_expanded_returned INTEGER,
    chunks_expanded          JSONB,
    retrieved_source_types   TEXT[],
    retrieved_source_ids     TEXT[],
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO retrieval_logging_new
SELECT
    rl.query_id,
    q.query_text,
    rl.source_types,
    rl.top_k_1,
    rl.top_k_2,
    rl.winning_keys,
    rl.key_vote_counts,
    rl.step1_ms,
    rl.step2_ms,
    rl.total_ms,
    rl.chunks_returned,
    rl.chunks,
    rl.chunks_expanded_returned,
    rl.chunks_expanded,
    rl.retrieved_source_types,
    rl.retrieved_source_ids,
    rl.created_at
FROM retrieval_logging rl
JOIN queries q ON rl.query_id = q.query_id;

DROP TABLE retrieval_logging;
ALTER TABLE retrieval_logging_new RENAME TO retrieval_logging;
