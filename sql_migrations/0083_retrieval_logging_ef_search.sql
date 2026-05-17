-- Record the HNSW ef_search value used in step 1 (voyage-key voting) and
-- step 2 (anchor retrieval) for each query. Both are nullable: NULL means
-- the step was skipped (e.g. step 1 skipped via --no-voyage-key).
ALTER TABLE retrieval_logging
    ADD COLUMN IF NOT EXISTS ef_search_1 INTEGER,
    ADD COLUMN IF NOT EXISTS ef_search_2 INTEGER;
