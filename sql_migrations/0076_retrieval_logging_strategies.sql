-- Track which chunk strategies a retrieval call filtered to, alongside source_types.
ALTER TABLE retrieval_logging ADD COLUMN strategies text[];
