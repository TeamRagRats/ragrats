CREATE TABLE embedding_logging (
    id            SERIAL PRIMARY KEY,
    run_id        UUID        REFERENCES import_runs(run_id) ON DELETE SET NULL,
    batch_idx     INT         NOT NULL,
    n_chunks      INT,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    duration_ms   INT,
    status        TEXT        NOT NULL DEFAULT 'pending',
    error_message TEXT,
    model         TEXT,
    UNIQUE (run_id, batch_idx)
);
