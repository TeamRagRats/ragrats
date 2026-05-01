-- Replace sliced email chunks with direct email_attach_summaries inserts.
-- One chunk per email summary, no slicing.

-- 1. Delete existing sliced email chunks
DELETE FROM chunks WHERE source_type = 'email';

-- 2. Drop old source_type check
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

-- 3. Add new check with email_summaries instead of email
ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY['email_summaries', 'voyage', 'thread_summaries', 'phase']));

-- 4. Insert email_attach_summaries as single chunks (no slicing)
INSERT INTO chunks (source_type, source_id, voyage_key, strategy, chunk_index, text, char_count)
SELECT
    'email_summaries',
    email_id::text,
    voyage_key,
    'late',
    0,
    summary,
    LENGTH(summary)
FROM email_attach_summaries
WHERE status = 'ok'
  AND summary IS NOT NULL
  AND TRIM(summary) <> ''
ON CONFLICT (source_type, source_id, strategy, chunk_index) DO NOTHING;
