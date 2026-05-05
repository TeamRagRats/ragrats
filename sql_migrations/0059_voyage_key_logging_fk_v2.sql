TRUNCATE test_voyage_key_logging;

ALTER TABLE test_voyage_key_logging
    DROP CONSTRAINT test_voyage_key_logging_question_id_fkey;

ALTER TABLE test_voyage_key_logging
    ADD CONSTRAINT test_voyage_key_logging_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES ground_truth_v2(question_id);
