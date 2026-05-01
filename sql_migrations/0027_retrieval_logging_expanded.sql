ALTER TABLE retrieval_logging ADD COLUMN IF NOT EXISTS chunks_expanded_returned INTEGER;
ALTER TABLE retrieval_logging ADD COLUMN IF NOT EXISTS chunks_expanded JSONB;
