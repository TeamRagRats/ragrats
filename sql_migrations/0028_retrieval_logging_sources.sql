ALTER TABLE retrieval_logging ADD COLUMN IF NOT EXISTS retrieved_source_types TEXT[];
ALTER TABLE retrieval_logging ADD COLUMN IF NOT EXISTS retrieved_source_ids TEXT[];
