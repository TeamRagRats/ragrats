-- Per-thread token observability for late chunking (step_05_chunking/email_late).
ALTER TABLE chunking_logging ADD COLUMN IF NOT EXISTS total_tokens INTEGER;

ALTER TABLE chunking_logging ADD COLUMN IF NOT EXISTS truncated BOOLEAN NOT NULL DEFAULT FALSE;
