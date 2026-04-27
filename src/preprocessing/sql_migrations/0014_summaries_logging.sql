CREATE TABLE IF NOT EXISTS summaries_logging (
    email_id        UUID PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    voyage_key      TEXT,
    attach_count    INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    status          TEXT NOT NULL CHECK (status IN ('pending','ok','error')),
    error_message   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    batch_idx       INTEGER,
    run_id          UUID REFERENCES import_runs(run_id) ON DELETE SET NULL
);
