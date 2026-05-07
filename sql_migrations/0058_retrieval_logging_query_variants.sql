ALTER TABLE retrieval_logging
    ADD COLUMN IF NOT EXISTS query_variants JSONB;
