ALTER TABLE test_retrieval_run_logging
    DROP CONSTRAINT test_retrieval_run_logging_pkey,
    ADD COLUMN question_type TEXT NOT NULL DEFAULT 'extractive'
        CHECK (question_type IN ('extractive', 'investigative')),
    ADD PRIMARY KEY (run_id, question_type);
