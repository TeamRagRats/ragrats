-- Enables pgvector and creates the chunks table for embedding-based retrieval.
-- source_type distinguishes email vs voyage chunks; source_id is email_id or voyage_key.
-- Embedding dimension 2560 matches Qwen3-Embedding-4B hidden size.
-- HNSW index is created now but will be empty until run_embeddings fills the table.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL CHECK (source_type IN ('email', 'voyage')),
    source_id   TEXT NOT NULL,
    voyage_key  TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector(2560),
    char_count  INTEGER,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_type, source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_source_idx  ON chunks (source_type, source_id);
CREATE INDEX IF NOT EXISTS chunks_voyage_idx  ON chunks (voyage_key);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
