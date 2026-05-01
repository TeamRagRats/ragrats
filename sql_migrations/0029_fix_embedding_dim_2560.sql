-- Correct embedding dimension back to 2560 (actual Qwen3-Embedding-4B output size).
-- Migration 0028 incorrectly set it to 2556.

DROP INDEX IF EXISTS chunks_embedding_hnsw_idx;

ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(2560);

CREATE INDEX chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
