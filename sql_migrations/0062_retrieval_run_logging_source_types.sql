ALTER TABLE test_retrieval_run_logging
    ADD COLUMN source_types TEXT[] NOT NULL DEFAULT '{all}'::text[];
