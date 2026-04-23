CREATE TABLE IF NOT EXISTS emails (
    email_id        UUID PRIMARY KEY,
    voyage_key      TEXT NOT NULL,
    thread_id       UUID NOT NULL,
    eml_path        TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('in','out')),
    mailbox         TEXT,
    subject         TEXT,
    from_addr       TEXT,
    to_addr         TEXT[],
    sent_at         TIMESTAMPTZ,
    body_text       TEXT,
    body_html       TEXT,
    body_cleaned    TEXT,
    has_attachment  BOOLEAN NOT NULL DEFAULT FALSE,
    raw_headers     JSONB,
    email_json      JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS emails_voyage_idx  ON emails(voyage_key);
CREATE INDEX IF NOT EXISTS emails_thread_idx  ON emails(thread_id);
CREATE INDEX IF NOT EXISTS emails_sent_at_idx ON emails(sent_at);

CREATE TABLE IF NOT EXISTS docling (
    sha256          CHAR(64) PRIMARY KEY,
    utf8_text       TEXT NOT NULL,
    llm_attachment  TEXT,
    processed_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id              BIGSERIAL PRIMARY KEY,
    email_id        UUID NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    voyage_key      TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_type       TEXT,
    size_bytes      BIGINT,
    sha256          CHAR(64),
    docling_sha256  CHAR(64) REFERENCES docling(sha256)
);
CREATE INDEX IF NOT EXISTS attachments_email_idx   ON attachments(email_id);
CREATE INDEX IF NOT EXISTS attachments_sha256_idx  ON attachments(sha256);
CREATE INDEX IF NOT EXISTS attachments_docling_idx ON attachments(docling_sha256);

CREATE TABLE IF NOT EXISTS import_runs (
    run_id          UUID PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS step_timings (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID REFERENCES import_runs(run_id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    rows_in         BIGINT,
    rows_out        BIGINT,
    errors          BIGINT DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS file_counters (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID REFERENCES import_runs(run_id) ON DELETE CASCADE,
    voyage_key      TEXT NOT NULL,
    n_emails        BIGINT DEFAULT 0,
    n_threads       BIGINT DEFAULT 0,
    n_attachments   BIGINT DEFAULT 0,
    n_bytes         BIGINT DEFAULT 0,
    n_errors        BIGINT DEFAULT 0,
    wall_time_ms    BIGINT DEFAULT 0
);
