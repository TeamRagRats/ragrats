ALTER TABLE retrieval_logging ADD COLUMN _new_qid UUID;

UPDATE retrieval_logging rl
SET _new_qid = rl.query_id
FROM (
    SELECT DISTINCT ON (query_id) run_id
    FROM retrieval_logging
    ORDER BY query_id, created_at
) first_row
WHERE rl.run_id = first_row.run_id;

UPDATE retrieval_logging
SET _new_qid = gen_random_uuid()
WHERE _new_qid IS NULL;

INSERT INTO queries (query_id, query_text, source, username)
SELECT rl._new_qid, q.query_text, q.source, q.username
FROM retrieval_logging rl
JOIN queries q ON q.query_id = rl.query_id
WHERE rl._new_qid != rl.query_id;

UPDATE retrieval_logging
SET query_id = _new_qid
WHERE query_id != _new_qid;

ALTER TABLE retrieval_logging DROP COLUMN _new_qid;

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
