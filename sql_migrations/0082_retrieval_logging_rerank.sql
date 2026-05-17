-- Track Qwen3-Reranker-8B usage on each retrieval call.
-- The `chunks` JSONB column already stores the final ordered list; when
-- `reranked = TRUE`, the `similarity` field inside each chunk is the
-- rerank relevance score (same overload as BM25 -> ts_rank).
ALTER TABLE retrieval_logging
    ADD COLUMN IF NOT EXISTS reranked     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS rerank_model TEXT,
    ADD COLUMN IF NOT EXISTS rerank_pool  INTEGER,
    ADD COLUMN IF NOT EXISTS rerank_ms    INTEGER;
