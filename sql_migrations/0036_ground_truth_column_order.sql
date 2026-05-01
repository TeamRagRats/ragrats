TRUNCATE test_voyage_key_logging, test_chunk_retrieval_logging, test_logging;

DROP TABLE IF EXISTS ground_truth CASCADE;

CREATE TABLE ground_truth (
    question_id         TEXT         PRIMARY KEY,
    question            TEXT         NOT NULL,
    ground_truth_answer TEXT         NOT NULL,
    difficulty          TEXT         NOT NULL DEFAULT 'medium'
                                     CHECK (difficulty IN ('easy', 'medium', 'hard')),
    source_id           TEXT,
    source_chunk_id     UUID         NOT NULL REFERENCES chunks(chunk_id),
    voyage_key          TEXT         NOT NULL,
    generated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ground_truth_voyage_key_idx ON ground_truth(voyage_key);

ALTER TABLE test_voyage_key_logging
    ADD CONSTRAINT test_voyage_key_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth(question_id);

ALTER TABLE test_chunk_retrieval_logging
    ADD CONSTRAINT test_chunk_retrieval_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth(question_id);
