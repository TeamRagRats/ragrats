CREATE TABLE IF NOT EXISTS test_chunk_retrieval_logging (
    id                  SERIAL          PRIMARY KEY,
    run_id              UUID            NOT NULL,
    question_id         TEXT            NOT NULL REFERENCES ground_truth(question_id),
    top_k               INTEGER         NOT NULL,
    expected_source_id  TEXT            NOT NULL,
    returned_source_ids TEXT[]          NOT NULL,
    hit                 BOOLEAN         NOT NULL,
    source_rank         INTEGER,
    tested_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS crt_run_id_idx      ON test_chunk_retrieval_logging(run_id);
CREATE INDEX IF NOT EXISTS crt_question_id_idx ON test_chunk_retrieval_logging(question_id);
CREATE INDEX IF NOT EXISTS crt_hit_idx         ON test_chunk_retrieval_logging(hit);
