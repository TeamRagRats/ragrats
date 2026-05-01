ALTER TABLE docling DROP COLUMN IF EXISTS docling_document;
ALTER TABLE docling ADD COLUMN IF NOT EXISTS markdown TEXT;
ALTER TABLE docling ADD COLUMN IF NOT EXISTS docling_document JSONB;
ALTER TABLE docling ADD COLUMN IF NOT EXISTS char_count INTEGER;
ALTER TABLE docling ADD COLUMN IF NOT EXISTS token_count INTEGER;
ALTER TABLE docling ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS docling_logging (
    sha256          CHAR(64) PRIMARY KEY,
    file_path       TEXT,
    file_type       TEXT,
    file_size_bytes BIGINT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    status          TEXT NOT NULL CHECK (status IN ('pending','done','error','skipped')),
    error_message   TEXT,
    char_count      INTEGER,
    token_count     INTEGER,
    gpu_util_pct    INTEGER,
    gpu_mem_pct     NUMERIC(5,2),
    ram_pct         NUMERIC(5,2),
    batch_idx       INTEGER,
    run_id          UUID REFERENCES runs_logging(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS docling_logging_status_idx ON docling_logging(status);
CREATE INDEX IF NOT EXISTS docling_logging_run_idx    ON docling_logging(run_id);
