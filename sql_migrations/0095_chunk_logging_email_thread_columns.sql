-- Make test_retrieval_chunk_logging self-describing at the email and thread
-- level. expected_source was a formatted string ("email_thread:<uuid>") and
-- returned_source_ids held the raw chunk source_ids (email_id for email
-- chunks, sha256 for attachments) -- neither lined up with the new
-- thread/email recall metrics. Replace both with resolved columns so a row
-- shows expected vs. returned at both levels directly, no joins needed.
--
-- expected_email / expected_thread are nullable: unanswerable ground_truth
-- rows have no expected source. The returned_*_ids arrays are NOT NULL but
-- may contain NULL elements for chunks we can't resolve (e.g. an attachment
-- whose sha256 isn't in the attachments map).

ALTER TABLE test_retrieval_chunk_logging DROP COLUMN expected_source;
ALTER TABLE test_retrieval_chunk_logging DROP COLUMN returned_source_ids;

ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN expected_email     TEXT;
ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN expected_thread    TEXT;
ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN returned_email_ids  TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE test_retrieval_chunk_logging
    ALTER COLUMN returned_email_ids DROP DEFAULT;
ALTER TABLE test_retrieval_chunk_logging
    ADD COLUMN returned_thread_ids TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE test_retrieval_chunk_logging
    ALTER COLUMN returned_thread_ids DROP DEFAULT;
