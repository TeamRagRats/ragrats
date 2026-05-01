-- Insert fixture_summaries directly into chunks table.
-- One chunk per fixture summary, no slicing.

-- 1. Drop old source_type check
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

-- 2. Add new check including fixture_summaries
ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY['email_summaries', 'voyage', 'thread_summaries', 'phase', 'fixture_summaries']));

-- 3. Insert fixture summaries as single chunks
INSERT INTO chunks (source_type, source_id, voyage_key, strategy, chunk_index, text, char_count)
SELECT
    'fixture_summaries',
    voyage_key,
    voyage_key,
    'late',
    0,
    summary,
    LENGTH(summary)
FROM fixture_summaries
WHERE status = 'ok'
  AND summary IS NOT NULL
  AND TRIM(summary) <> ''
ON CONFLICT (source_type, source_id, strategy, chunk_index) DO NOTHING;
