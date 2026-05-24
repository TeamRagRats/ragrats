-- Allow an aggregate 'total' row in test_retrieval_run_logging so voyage-key
-- runs can record one score across all answerable categories (fact_single +
-- summary + reasoning). 'unanswerable' is kept in the allowed set so historical
-- rows stay valid, but the test no longer writes it.

ALTER TABLE test_retrieval_run_logging
    DROP CONSTRAINT IF EXISTS test_retrieval_run_logging_question_type_check;

ALTER TABLE test_retrieval_run_logging
    ADD CONSTRAINT test_retrieval_run_logging_question_type_check
    CHECK (question_type IN ('fact_single', 'summary', 'reasoning', 'unanswerable', 'total'));
