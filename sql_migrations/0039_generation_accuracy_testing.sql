CREATE TABLE IF NOT EXISTS test_generation_accuracy_logging (
    id                  SERIAL          PRIMARY KEY,
    run_id              UUID            NOT NULL,
    question_id         TEXT            NOT NULL REFERENCES ground_truth(question_id),
    generated_answer    TEXT            NOT NULL,
    ground_truth_answer TEXT            NOT NULL,
    cosine_similarity   NUMERIC(6,4)    NOT NULL,
    judge_score         INTEGER,
    judge_reasoning     TEXT,
    generation_ms       INTEGER,
    tested_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS gat_run_id_idx      ON test_generation_accuracy_logging(run_id);
CREATE INDEX IF NOT EXISTS gat_question_id_idx ON test_generation_accuracy_logging(question_id);
