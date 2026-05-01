-- Fix embedding dimension: 2560 → 2556 (actual Qwen3-Embedding-4B output size).
-- Also adds model column to record which embedding model generated each vector.

DROP INDEX IF EXISTS chunks_embedding_hnsw_idx;

ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(2556);

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS model TEXT;

CREATE INDEX chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
