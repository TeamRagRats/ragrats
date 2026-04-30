CREATE TABLE thread_summaries (
    thread_id    UUID PRIMARY KEY,
    voyage_key   TEXT NOT NULL,
    subject      TEXT,
    email_count  INTEGER,
    summary      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    log          TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX thread_summaries_voyage_idx ON thread_summaries (voyage_key);
