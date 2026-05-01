-- Replace source_type 'thread' with 'thread_summaries' and insert thread summaries
-- directly as single chunks (no slicing — full summary as one chunk per thread).

-- 1. Delete existing thread chunks first (before constraint change)
DELETE FROM chunks WHERE source_type = 'thread';

-- 2. Drop old source_type check
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

-- 3. Add new check with thread_summaries instead of thread
ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY['email', 'voyage', 'thread_summaries', 'phase']));

-- 4. Insert thread summaries as single chunks (no slicing)
INSERT INTO chunks (source_type, source_id, voyage_key, strategy, chunk_index, text, char_count)
SELECT
    'thread_summaries',
    thread_id::text,
    voyage_key,
    'late',
    0,
    summary,
    LENGTH(summary)
FROM thread_summaries
WHERE status = 'ok'
  AND summary IS NOT NULL
  AND TRIM(summary) <> ''
ON CONFLICT (source_type, source_id, strategy, chunk_index) DO NOTHING;
