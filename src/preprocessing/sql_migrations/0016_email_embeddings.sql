CREATE TABLE IF NOT EXISTS email_embeddings (
    email_id     UUID PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    voyage_key   TEXT NOT NULL,
    embedding    vector(2560) NOT NULL,
    model        TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS email_embeddings_voyage_idx ON email_embeddings (voyage_key);
-- NOTE: pgvector ANN indexes (hnsw/ivfflat) are limited to 2000 dimensions.
-- Qwen3-Embedding-4B uses 2560 dimensions, so no ANN index is created here.
-- Exact cosine search (<=>) still works via sequential scan.
