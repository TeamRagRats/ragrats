-- Rename the `bm25 BOOLEAN` column on test_retrieval_run_logging to a
-- nullable text `lexical` so we can distinguish between the two lexical
-- retrievers (tsrank vs real BM25 via pg_search). NULL means pure vector.
--
-- Historical rows had `bm25=TRUE` whenever any lexical retriever was used,
-- but the only lexical path that existed at the time was ts_rank — so
-- TRUE backfills to 'tsrank' and FALSE backfills to NULL.
--
-- The bm25 column may not exist on every environment (some installs were
-- bootstrapped from a recreated logging table that never had it), so the
-- backfill + drop are guarded by an information_schema check.

ALTER TABLE test_retrieval_run_logging
    ADD COLUMN IF NOT EXISTS lexical TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'test_retrieval_run_logging' AND column_name = 'bm25'
    ) THEN
        UPDATE test_retrieval_run_logging
        SET lexical = 'tsrank'
        WHERE bm25 = TRUE AND lexical IS NULL;

        ALTER TABLE test_retrieval_run_logging DROP COLUMN bm25;
    END IF;
END $$;
