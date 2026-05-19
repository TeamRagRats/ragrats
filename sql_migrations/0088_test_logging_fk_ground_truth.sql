-- Drop FK constraint on test_retrieval_chunk_logging so it can accept question_ids
-- from any ground truth table (ground_truth, ground_truth_v3, etc.).

ALTER TABLE test_retrieval_chunk_logging
    DROP CONSTRAINT test_chunk_retrieval_logging_question_id_fkey;
