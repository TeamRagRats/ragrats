CREATE TABLE IF NOT EXISTS voyage_key_retrieval_testing (
    id              SERIAL          PRIMARY KEY,
    run_id          UUID            NOT NULL DEFAULT gen_random_uuid(),
    question_id     TEXT            NOT NULL REFERENCES ground_truth(question_id),
    top_k           INTEGER         NOT NULL,
    expected_key    TEXT            NOT NULL,
    returned_keys   TEXT[]          NOT NULL,
    hit             BOOLEAN         NOT NULL,
    winner_rank     INTEGER,
    vote_counts     JSONB           NOT NULL,
    tested_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS vkrt_run_id_idx      ON voyage_key_retrieval_testing(run_id);
CREATE INDEX IF NOT EXISTS vkrt_question_id_idx ON voyage_key_retrieval_testing(question_id);
CREATE INDEX IF NOT EXISTS vkrt_hit_idx         ON voyage_key_retrieval_testing(hit);
