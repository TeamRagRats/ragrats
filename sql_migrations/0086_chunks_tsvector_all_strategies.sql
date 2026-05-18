-- Extend BM25/lexical retrieval to cover all four chunk strategies.
--
-- Migration 0081 restricted text_tsv to strategy='context' only. This
-- migration widens the generated column and its GIN index to also include
-- 'plain', 'late', and 'summary' so that BM25 retrieval can run across any
-- combination of strategies.
--
-- The column is STORED GENERATED so Postgres recomputes it for all existing
-- rows immediately on ALTER — no backfill job needed.

-- Drop the old partial index first (cannot ALTER a generated column directly
-- while an index depends on its expression; drop+recreate is the safe path).
DROP INDEX IF EXISTS chunks_text_tsv_gin;

-- Widen the generated expression to include all four strategies.
ALTER TABLE chunks
    DROP COLUMN text_tsv;

ALTER TABLE chunks
    ADD COLUMN text_tsv tsvector
    GENERATED ALWAYS AS (
        CASE
            WHEN strategy IN ('context', 'plain', 'late', 'summary')
            THEN to_tsvector('simple', text)
            ELSE NULL
        END
    ) STORED;

-- Recreate the GIN index covering all four strategies.
CREATE INDEX chunks_text_tsv_gin
    ON chunks USING gin (text_tsv)
    WHERE strategy IN ('context', 'plain', 'late', 'summary');
