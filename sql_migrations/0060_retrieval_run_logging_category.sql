ALTER TABLE test_retrieval_run_logging
    DROP CONSTRAINT test_retrieval_run_logging_question_type_check;

ALTER TABLE test_retrieval_run_logging
    ADD CONSTRAINT test_retrieval_run_logging_question_type_check
    CHECK (question_type IN ('extractive', 'investigative', 'logistics_cargo', 'commercial_terms', 'incident_decision'));
