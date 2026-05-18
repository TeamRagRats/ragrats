-- Log which retrieval configuration produced each test run result.
ALTER TABLE test_retrieval_run_logging
    ADD COLUMN IF NOT EXISTS strategy     TEXT,
    ADD COLUMN IF NOT EXISTS bm25         BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reranker     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reformulator BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ef           INTEGER;
