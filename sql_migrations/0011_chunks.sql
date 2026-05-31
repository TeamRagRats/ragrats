-- Enables pgvector and creates the chunks table for embedding-based retrieval.
-- source_type distinguishes email vs voyage chunks; source_id is email_id or voyage_key.
-- Embedding dimension 2560 matches Qwen3-Embedding-4B hidden size.
-- HNSW index is created now but will be empty until run_embeddings fills the table.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- unique id per chunk, auto-generated
    source_type TEXT NOT NULL CHECK (source_type IN ('email', 'voyage')), -- which type of summary the chunk comes from
    source_id   TEXT NOT NULL,   -- email_id (UUID as text) or voyage_key
    voyage_key  TEXT NOT NULL,   -- always set, so retrieval can be filtered to a single voyage
    chunk_index INTEGER NOT NULL, -- the order of chunks within the same source (email = always 0)
    text        TEXT NOT NULL,   -- the paragraph text itself
    embedding   halfvec(2560),   -- Qwen3-Embedding-4B vector, NULL until run_embeddings runs
    char_count  INTEGER,         -- number of characters in the text, for observability
    UNIQUE (source_type, source_id, chunk_index) -- prevents duplicates on re-ingestion
);

CREATE INDEX IF NOT EXISTS chunks_source_idx  ON chunks (source_type, source_id);
CREATE INDEX IF NOT EXISTS chunks_voyage_idx  ON chunks (voyage_key);

-- m = 16: number of connections per node in the HNSW graph. Higher = better recall, more RAM.
-- ef_construction = 64: number of candidates considered at INSERT. Higher = better graph quality, slower insertion.
-- Both are default values and fit our data size.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
