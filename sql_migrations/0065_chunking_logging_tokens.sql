-- Per-thread token observability for late embedding (step_06_embedding/email_late).
ALTER TABLE chunking_logging ADD COLUMN IF NOT EXISTS total_tokens INTEGER;

ALTER TABLE chunking_logging ADD COLUMN IF NOT EXISTS truncated BOOLEAN NOT NULL DEFAULT FALSE;
