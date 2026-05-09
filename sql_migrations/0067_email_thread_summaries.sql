CREATE TABLE email_thread_summaries (
    email_id     UUID PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    thread_id    UUID NOT NULL,
    voyage_key   TEXT NOT NULL,
    prior_count  INTEGER NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    log          TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    llm_input    TEXT
);

CREATE INDEX email_thread_summaries_thread_idx ON email_thread_summaries (thread_id);
CREATE INDEX email_thread_summaries_voyage_idx ON email_thread_summaries (voyage_key);
CREATE INDEX email_thread_summaries_prior_count_idx ON email_thread_summaries (prior_count);
