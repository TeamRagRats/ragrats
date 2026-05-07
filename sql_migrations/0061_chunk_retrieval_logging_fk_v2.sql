TRUNCATE test_chunk_retrieval_logging;

ALTER TABLE test_chunk_retrieval_logging
    DROP CONSTRAINT test_chunk_retrieval_logging_question_id_fkey;

ALTER TABLE test_chunk_retrieval_logging
    ADD CONSTRAINT test_chunk_retrieval_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth_v2(question_id);
