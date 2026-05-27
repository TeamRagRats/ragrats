-- Generation test: add category + chunks/flags columns, drop old PK on run_logging
-- (run_id was PK → changed to composite (run_id, category) so one row per category per run).
-- Clears old test results since they are incompatible with the new schema.

TRUNCATE test_generation_accuracy_logging;
TRUNCATE test_generation_run_logging;

ALTER TABLE test_generation_accuracy_logging
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS chunks   JSONB;

ALTER TABLE test_generation_run_logging
    DROP CONSTRAINT IF EXISTS test_generation_run_logging_pkey;

ALTER TABLE test_generation_run_logging
    ADD COLUMN IF NOT EXISTS category TEXT    NOT NULL DEFAULT 'all',
    ADD COLUMN IF NOT EXISTS flags    JSONB;

ALTER TABLE test_generation_run_logging
    ADD PRIMARY KEY (run_id, category);
