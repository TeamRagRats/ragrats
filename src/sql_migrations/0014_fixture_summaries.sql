CREATE TABLE IF NOT EXISTS fixture_summaries (
    voyage_key   TEXT PRIMARY KEY,
    summary      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    log          TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
