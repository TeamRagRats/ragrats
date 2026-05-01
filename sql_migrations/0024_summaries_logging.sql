ALTER TABLE summaries_logging RENAME TO email_attach_logging_legacy;

CREATE TABLE summaries_logging (
    id            SERIAL PRIMARY KEY,
    summary_type  TEXT        NOT NULL,
    entity_key    TEXT        NOT NULL,
    voyage_key    TEXT,
    run_id        UUID        REFERENCES runs_logging(run_id) ON DELETE SET NULL,
    batch_idx     INT         NOT NULL DEFAULT 0,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    duration_ms   INT,
    status        TEXT        NOT NULL DEFAULT 'pending',
    error_message TEXT,
    input_tokens  INT,
    output_tokens INT,
    UNIQUE (summary_type, entity_key)
);
