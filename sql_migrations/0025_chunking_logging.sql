CREATE TABLE chunking_logging (
    id            SERIAL PRIMARY KEY,
    source_type   TEXT        NOT NULL,
    source_id     TEXT        NOT NULL,
    voyage_key    TEXT,
    run_id        UUID        REFERENCES runs_logging(run_id) ON DELETE SET NULL,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    duration_ms   INT,
    status        TEXT        NOT NULL DEFAULT 'pending',
    n_chunks      INT,
    char_count    INT,
    error_message TEXT,
    UNIQUE (source_type, source_id)
);
