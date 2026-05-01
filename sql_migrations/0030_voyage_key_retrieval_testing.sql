CREATE TABLE IF NOT EXISTS test_voyage_key_logging (
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

CREATE INDEX IF NOT EXISTS vkrt_run_id_idx      ON test_voyage_key_logging(run_id);
CREATE INDEX IF NOT EXISTS vkrt_question_id_idx ON test_voyage_key_logging(question_id);
CREATE INDEX IF NOT EXISTS vkrt_hit_idx         ON test_voyage_key_logging(hit);
