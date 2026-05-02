DROP TABLE IF EXISTS test_logging;

TRUNCATE test_generation_accuracy_logging;
TRUNCATE test_chunk_retrieval_logging;
TRUNCATE test_voyage_key_logging;

CREATE TABLE IF NOT EXISTS test_retrieval_run_logging (
    run_id      UUID            PRIMARY KEY,
    test_type   TEXT            NOT NULL,
    top_k       INTEGER         NOT NULL,
    total       INTEGER         NOT NULL,
    hits        INTEGER         NOT NULL,
    recall      NUMERIC(6,4)    NOT NULL,
    run_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS test_generation_run_logging (
    run_id          UUID            PRIMARY KEY,
    total           INTEGER         NOT NULL,
    judge_hits      INTEGER         NOT NULL,
    avg_cosine      NUMERIC(6,4)    NOT NULL,
    avg_judge_score NUMERIC(4,2)    NOT NULL,
    run_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
