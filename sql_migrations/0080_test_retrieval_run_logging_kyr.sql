-- Switch test_retrieval_run_logging.question_type to the four-class Know Your RAG
-- taxonomy used by ground_truth_v3 (fact_single, summary, reasoning, unanswerable).
-- Drops the legacy categories (extractive, investigative, etc.).

DELETE FROM test_retrieval_run_logging
 WHERE question_type IN ('extractive', 'investigative', 'logistics_cargo',
                         'commercial_terms', 'incident_decision');

ALTER TABLE test_retrieval_run_logging
    DROP CONSTRAINT IF EXISTS test_retrieval_run_logging_question_type_check;

ALTER TABLE test_retrieval_run_logging
    ADD CONSTRAINT test_retrieval_run_logging_question_type_check
    CHECK (question_type IN ('fact_single', 'summary', 'reasoning', 'unanswerable'));

ALTER TABLE test_retrieval_run_logging
    ALTER COLUMN question_type DROP DEFAULT;
