-- Step 9 — LLM Extraction. Mirror of the docling step:
--   llm_load_queue   (VIEW)   — pending source rows joined to attachment metadata
--   llm_structured   (TABLE)  — restructured / classified output, keyed by sha256
--   llm_logging      (TABLE)  — per-file status + timing + GPU/RAM snapshot
CREATE OR REPLACE VIEW llm_load_queue AS
SELECT DISTINCT ON (d.sha256)
       d.sha256,
       d.markdown,
       d.char_count,
       d.token_count,
       a.email_id,
       a.voyage_key,
       a.file_path,
       a.file_type
FROM   docling d
JOIN   attachments a ON a.sha256 = d.sha256
WHERE  d.markdown IS NOT NULL
  AND  TRIM(d.markdown) <> ''
ORDER BY d.sha256;

CREATE TABLE IF NOT EXISTS llm_structured (
    sha256             CHAR(64) PRIMARY KEY REFERENCES docling(sha256) ON DELETE CASCADE,
    mode               TEXT NOT NULL CHECK (mode IN ('full','classify')),
    document_type      TEXT,
    structured_md      TEXT,
    input_token_count  INTEGER NOT NULL DEFAULT 0,
    output_token_count INTEGER NOT NULL DEFAULT 0,
    model_name         TEXT NOT NULL,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_logging (
    sha256          CHAR(64) PRIMARY KEY,
    file_path       TEXT,
    file_type       TEXT,
    char_count      INTEGER,
    size_category   TEXT,
    mode            TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    status          TEXT NOT NULL CHECK (status IN ('pending','done','error','skipped')),
    error_message   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    gpu_util_pct    INTEGER,
    gpu_mem_pct     NUMERIC(5,2),
    ram_pct         NUMERIC(5,2),
    batch_idx       INTEGER,
    run_id          UUID REFERENCES runs_logging(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS llm_logging_status_idx ON llm_logging(status);
CREATE INDEX IF NOT EXISTS llm_logging_run_idx    ON llm_logging(run_id);
