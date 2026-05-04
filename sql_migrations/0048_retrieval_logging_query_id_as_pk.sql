-- Deduplicate: rows that share a query_id (from the DISTINCT backfill in 0043)
-- get fresh query rows so every retrieval row has a unique query_id.
DO $$
DECLARE
    r RECORD;
    new_qid UUID;
BEGIN
    FOR r IN
        WITH first_per_query AS (
            SELECT DISTINCT ON (query_id) run_id
            FROM retrieval_logging
            ORDER BY query_id, created_at
        )
        SELECT rl.run_id, q.query_text, q.source, q.username
        FROM retrieval_logging rl
        JOIN queries q ON q.query_id = rl.query_id
        WHERE rl.run_id NOT IN (SELECT run_id FROM first_per_query)
    LOOP
        INSERT INTO queries (query_text, source, username)
        VALUES (r.query_text, r.source, r.username)
        RETURNING query_id INTO new_qid;

        UPDATE retrieval_logging SET query_id = new_qid WHERE run_id = r.run_id;
    END LOOP;
END $$;

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
