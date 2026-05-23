-- Consolidate per-knob config columns on test_retrieval_run_logging into a
-- single JSONB `flags` blob, matching the pattern already in use on
-- test_retrieval_chunk_logging. Aggregate-metric columns (run_id, test_type,
-- question_type, total, thread_hits, thread_recall, email_hits, email_recall,
-- run_at) stay as first-class columns for easy SQL aggregation.
--
-- All statements are idempotent so this is a no-op on dev DBs where the
-- equivalent schema change was already applied manually, and a real change
-- on fresh / CI / teammate envs.
--
-- NOTE: any historical rows pre-dating this migration will have flags = NULL.
-- We do not backfill from the dropped columns — they only existed in code
-- before this consolidation and the historical config can still be inferred
-- from the matching test_retrieval_chunk_logging.flags row (joined on run_id)
-- where one exists.

ALTER TABLE test_retrieval_run_logging
    ADD COLUMN IF NOT EXISTS flags JSONB;

ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS top_k;
ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS strategy;
ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS lexical;
ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS reranker;
ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS reformulator;
ALTER TABLE test_retrieval_run_logging DROP COLUMN IF EXISTS ef;
