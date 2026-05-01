CREATE TABLE IF NOT EXISTS test_logging (
    run_id      UUID        PRIMARY KEY,
    test_type   TEXT        NOT NULL,
    top_k       INTEGER,
    total       INTEGER     NOT NULL,
    hits        INTEGER     NOT NULL,
    recall      NUMERIC(6,4) NOT NULL,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
