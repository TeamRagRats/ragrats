TRUNCATE ground_truth CASCADE;

DROP INDEX IF EXISTS ground_truth_status_idx;

ALTER TABLE ground_truth DROP COLUMN IF EXISTS status;
ALTER TABLE ground_truth DROP COLUMN IF EXISTS email_time;
ALTER TABLE ground_truth RENAME COLUMN voyage_path TO eml_path;
ALTER TABLE ground_truth ALTER COLUMN source_email_id SET NOT NULL;
ALTER TABLE ground_truth ALTER COLUMN thread_id SET NOT NULL;
