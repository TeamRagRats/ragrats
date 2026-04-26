-- Enables pgvector and creates the chunks table for embedding-based retrieval.
-- source_type distinguishes email vs voyage chunks; source_id is email_id or voyage_key.
-- Embedding dimension 2560 matches Qwen3-Embedding-4B hidden size.
-- HNSW index is created now but will be empty until run_embeddings fills the table.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- unik id per chunk, auto-genereret
    source_type TEXT NOT NULL CHECK (source_type IN ('email', 'voyage')), -- hvilken type summary chunken kommer fra
    source_id   TEXT NOT NULL,   -- email_id (UUID som text) eller voyage_key
    voyage_key  TEXT NOT NULL,   -- altid sat, så man kan filtrere retrieval til én voyage
    chunk_index INTEGER NOT NULL, -- rækkefølgen af chunks inden for samme source (email = altid 0)
    text        TEXT NOT NULL,   -- selve afsnittets tekst
    embedding   vector(2560),    -- Qwen3-Embedding-4B vektor, NULL indtil run_embeddings kører
    char_count  INTEGER,         -- antal tegn i teksten, til observability
    created_at  TIMESTAMPTZ DEFAULT now(), -- hvornår chunken blev indsat
    UNIQUE (source_type, source_id, chunk_index) -- forhindrer dubletter ved genindkørsel
);

CREATE INDEX IF NOT EXISTS chunks_source_idx  ON chunks (source_type, source_id);
CREATE INDEX IF NOT EXISTS chunks_voyage_idx  ON chunks (voyage_key);

-- m = 16: antal forbindelser per node i HNSW-grafen. Højere = bedre recall, mere RAM.
-- ef_construction = 64: antal kandidater overvejet ved INSERT. Højere = bedre grafkvalitet, langsommere indsætning.
-- Begge er standardværdier og passer til vores datastørrelse.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
