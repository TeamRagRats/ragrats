-- BM25/lexical retrieval support: persistent tsvector + partial GIN index.
-- Used by src/02_retrieval/BM25/ for hybrid retrieval (vector + BM25 via RRF).
--
-- Tokenizer is 'simple' on purpose: the corpus is full of proper nouns
-- (vessel names, port names, voyage keys) where stemming would hurt recall.
--
-- A STORED GENERATED column auto-populates existing rows on ALTER and stays
-- in sync on INSERT/UPDATE — no trigger needed. Values are computed only for
-- strategy='context' rows; everything else stores NULL, costing ~nothing.
-- The GIN index is partial (strategy='context') so it only carries the rows
-- the BM25 retriever actually queries.

ALTER TABLE chunks
    ADD COLUMN text_tsv tsvector
    GENERATED ALWAYS AS (
        CASE WHEN strategy = 'context' THEN to_tsvector('simple', text) ELSE NULL END
    ) STORED;

CREATE INDEX chunks_text_tsv_gin
    ON chunks USING gin (text_tsv)
    WHERE strategy = 'context';
