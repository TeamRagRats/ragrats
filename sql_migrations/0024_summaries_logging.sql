CREATE TABLE IF NOT EXISTS summaries_logging (
    id SERIAL PRIMARY KEY
);

ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS summary_type  TEXT        NOT NULL DEFAULT '';
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS entity_key    TEXT        NOT NULL DEFAULT '';
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS voyage_key    TEXT;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS run_id        UUID        REFERENCES import_runs(run_id);
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS batch_idx     INT         NOT NULL DEFAULT 0;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS started_at    TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS finished_at   TIMESTAMPTZ;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS duration_ms   INT;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS status        TEXT        NOT NULL DEFAULT 'pending';
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS input_tokens  INT;
ALTER TABLE summaries_logging ADD COLUMN IF NOT EXISTS output_tokens INT;

CREATE UNIQUE INDEX IF NOT EXISTS summaries_logging_type_key ON summaries_logging (summary_type, entity_key);
