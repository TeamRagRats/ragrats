-- Split the single "source/hit" recall metric into two: thread-level (the old
-- behavior) and email-level (strict — chunk's parent email must equal the
-- ground_truth source_id). Both are tracked per question and per run.
--
-- Renames in test_retrieval_chunk_logging are safe: only chunk_retrieval and
-- e2e_retrieval write to that table, both updated in the same change.
-- Renames in test_retrieval_run_logging affect voyage_key_retrieval too, which
-- writes voyage-key hits into thread_hits/thread_recall after this migration —
-- the column name is now generic across test_type.

ALTER TABLE test_retrieval_chunk_logging RENAME COLUMN hit TO thread_hit;
ALTER TABLE test_retrieval_chunk_logging RENAME COLUMN source_rank TO thread_rank;

ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN email_hit BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE test_retrieval_chunk_logging
    ALTER COLUMN email_hit DROP DEFAULT;

ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN email_rank INTEGER;

DROP INDEX IF EXISTS chunk_log_hit_idx;
CREATE INDEX chunk_log_thread_hit_idx ON test_retrieval_chunk_logging(thread_hit);
CREATE INDEX chunk_log_email_hit_idx  ON test_retrieval_chunk_logging(email_hit);

ALTER TABLE test_retrieval_run_logging RENAME COLUMN hits   TO thread_hits;
ALTER TABLE test_retrieval_run_logging RENAME COLUMN recall TO thread_recall;

ALTER TABLE test_retrieval_run_logging
    ADD COLUMN email_hits   INTEGER;
ALTER TABLE test_retrieval_run_logging
    ADD COLUMN email_recall NUMERIC(6,4);
