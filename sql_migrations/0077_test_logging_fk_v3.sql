-- Re-point voyage_key and chunk retrieval test logging FKs from ground_truth_v2 to ground_truth_v3.
-- v3 is strategy-agnostic and uses the four-class KYR taxonomy; v2 rows are no longer used by the tests.

TRUNCATE test_voyage_key_logging;
TRUNCATE test_chunk_retrieval_logging;

ALTER TABLE test_voyage_key_logging
    DROP CONSTRAINT test_voyage_key_logging_question_id_fkey;
ALTER TABLE test_voyage_key_logging
    ADD CONSTRAINT test_voyage_key_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth_v3(question_id);

ALTER TABLE test_chunk_retrieval_logging
    DROP CONSTRAINT test_chunk_retrieval_logging_question_id_fkey;
ALTER TABLE test_chunk_retrieval_logging
    ADD CONSTRAINT test_chunk_retrieval_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth_v3(question_id);
