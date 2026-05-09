-- Add thread_id to chunks so retrieval can group/filter by thread without re-joining emails.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS thread_id UUID;

CREATE INDEX IF NOT EXISTS chunks_thread_id_idx ON chunks (thread_id) WHERE thread_id IS NOT NULL;
